using System.Diagnostics;

var projectRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
var composeFile = Path.Combine(projectRoot, "docker-compose.yml");
var backendDir = Path.Combine(projectRoot, "backend");
var frontendDir = Path.Combine(projectRoot, "frontend");

if (!File.Exists(composeFile))
{
    Console.ForegroundColor = ConsoleColor.Red;
    Console.WriteLine("No se encontro docker-compose.yml en la raiz del proyecto.");
    Console.ResetColor();
    return;
}

Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine("360CollectPlus Launcher");
Console.WriteLine("Este lanzador inicia Docker Compose desde Visual Studio 2022.");
Console.ResetColor();

string? FindExecutableInPath(string command)
{
    try
    {
        var probe = Process.Start(new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = $"/c where {command}",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        });

        if (probe is null)
        {
            return null;
        }

        probe.WaitForExit();
        var output = probe.StandardOutput.ReadToEnd().Trim();
        if (probe.ExitCode == 0 && !string.IsNullOrWhiteSpace(output))
        {
            var candidate = output.Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries)[0].Trim();
            if (!Path.HasExtension(candidate) && File.Exists(candidate + ".exe"))
            {
                candidate += ".exe";
            }
            return candidate;
        }
    }
    catch
    {
    }

    return null;
}

string? FindDockerExecutable()
{
    var candidates = new[]
    {
        "docker",
        @"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
        @"C:\Program Files (x86)\Docker\Docker\resources\bin\docker.exe"
    };

    foreach (var candidate in candidates)
    {
        if (candidate.Equals("docker", StringComparison.OrdinalIgnoreCase))
        {
            var found = FindExecutableInPath("docker");
            if (!string.IsNullOrWhiteSpace(found))
            {
                return found;
            }
        }
        else if (File.Exists(candidate))
        {
            return candidate;
        }
    }

    return null;
}

string? FindPythonExecutable()
{
    var candidates = new[]
    {
        FindExecutableInPath("py"),
        FindExecutableInPath("python"),
        @"C:\Python312\python.exe",
        @"C:\Program Files\Python312\python.exe",
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\Python\Python312\python.exe")
    };

    foreach (var candidate in candidates)
    {
        if (!string.IsNullOrWhiteSpace(candidate) && File.Exists(candidate))
        {
            return candidate;
        }
    }

    return null;
}

string? FindNodeExecutable()
{
    var candidates = new[]
    {
        FindExecutableInPath("node"),
        @"C:\Program Files\nodejs\node.exe"
    };

    foreach (var candidate in candidates)
    {
        if (!string.IsNullOrWhiteSpace(candidate) && File.Exists(candidate))
        {
            return candidate;
        }
    }

    return null;
}

string? FindNpmCommand()
{
    var npmCmd = FindExecutableInPath("npm.cmd");
    if (!string.IsNullOrWhiteSpace(npmCmd) && File.Exists(npmCmd))
    {
        return npmCmd;
    }

    var npm = FindExecutableInPath("npm");
    if (!string.IsNullOrWhiteSpace(npm) && File.Exists(npm))
    {
        return npm;
    }

    var common = @"C:\Program Files\nodejs\npm.cmd";
    return File.Exists(common) ? common : null;
}

void LaunchDetachedTerminal(string title, string workingDirectory, string commandLine)
{
    Process.Start(new ProcessStartInfo
    {
        FileName = "cmd.exe",
        Arguments = $"/k title {title} && cd /d \"{workingDirectory}\" && {commandLine}",
        WorkingDirectory = workingDirectory,
        UseShellExecute = true
    });
}

void LaunchLocalMode()
{
    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.WriteLine("Docker no esta disponible. Intentando modo local con Python y Node.");
    Console.ResetColor();

    var pythonExecutable = FindPythonExecutable();
    var nodeExecutable = FindNodeExecutable();
    var npmCommand = FindNpmCommand();

    if (string.IsNullOrWhiteSpace(pythonExecutable))
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine("No se encontro Python 3.12 para iniciar el backend local.");
        Console.ResetColor();
        return;
    }

    if (string.IsNullOrWhiteSpace(nodeExecutable) || string.IsNullOrWhiteSpace(npmCommand))
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine("No se encontro Node.js o npm para iniciar el frontend local.");
        Console.ResetColor();
        return;
    }

    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.WriteLine("Abriendo una consola para backend y otra para frontend.");
    Console.WriteLine("Si es la primera vez, ejecuta manualmente 'pip install -r requirements.txt' y 'npm install'.");
    Console.ResetColor();

    var backendCommand = pythonExecutable.EndsWith("py.exe", StringComparison.OrdinalIgnoreCase)
        ? $"\"{pythonExecutable}\" -3.12 -m uvicorn main:app --reload"
        : $"\"{pythonExecutable}\" -m uvicorn main:app --reload";

    LaunchDetachedTerminal("360CollectPlus Backend", backendDir, backendCommand);
    LaunchDetachedTerminal("360CollectPlus Frontend", frontendDir, $"\"{npmCommand}\" run dev");

    Console.WriteLine("Modo local lanzado.");
    Console.WriteLine("Backend esperado en http://localhost:8000");
    Console.WriteLine("Frontend esperado en http://localhost:5173");
}

var dockerExecutable = FindDockerExecutable();
if (string.IsNullOrWhiteSpace(dockerExecutable))
{
    LaunchLocalMode();
    return;
}

var psi = new ProcessStartInfo
{
    FileName = "cmd.exe",
    Arguments = $"/c \"\"{dockerExecutable}\" compose up --build\"",
    WorkingDirectory = projectRoot,
    UseShellExecute = false
};

try
{
    using var process = Process.Start(psi);
    if (process is null)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine("No fue posible iniciar Docker Compose.");
        Console.ResetColor();
        return;
    }

    process.WaitForExit();
    Console.WriteLine($"Docker Compose finalizo con codigo {process.ExitCode}.");
}
catch (Exception ex)
{
    Console.ForegroundColor = ConsoleColor.Red;
    Console.WriteLine("No se pudo ejecutar Docker Compose.");
    Console.WriteLine(ex.Message);
    Console.WriteLine("Asegurate de tener Docker Desktop instalado y el comando 'docker' disponible.");
    Console.ResetColor();
}
