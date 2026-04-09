from __future__ import annotations

import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs" / "08_Presentacion_Ejecutiva_360Collect_V3.pptx"


SLIDES = [
    {
        "title": "360Collect V3",
        "subtitle": "La plataforma que convierte la cobranza en una operación inteligente, trazable y omnicanal.",
        "bullets": [
            "No es un sistema más. Es una capacidad operativa para recuperar más, decidir antes y controlar mejor.",
            "Integra estrategia, ejecución, supervisión, canales y trazabilidad en un solo flujo.",
            "El mensaje para comité no es “lo quiero”; es “lo necesito urgentemente”.",
        ],
        "tag": "Mensaje de apertura",
    },
    {
        "title": "El problema que hoy cuesta dinero",
        "subtitle": "La cobranza tradicional ya no escala al ritmo del negocio.",
        "bullets": [
            "Listas largas sin prioridad inteligente: el equipo trabaja volumen, no valor.",
            "Un mismo cliente se trata por producto, no por visión consolidada ni cabeza de mora.",
            "La estrategia vive en manuales y hojas; no en la pantalla del gestor.",
            "Supervisión opera en modo reactivo y dirección recibe visibilidad tardía.",
        ],
        "tag": "Dolor actual",
    },
    {
        "title": "El costo de seguir igual",
        "subtitle": "Cada día sin decisión operativa inteligente erosiona recuperación y control.",
        "bullets": [
            "Menor recuperación por contacto tardío o mal dirigido.",
            "Mayor costo operativo por insistir en cuentas con baja probabilidad y descuidar las de alto potencial.",
            "Más dependencia de revisión manual y mayor desgaste supervisor.",
            "Menor trazabilidad frente a auditoría, control interno y comité.",
        ],
        "tag": "Riesgo de no actuar",
    },
    {
        "title": "Qué hace diferente a 360Collect V3",
        "subtitle": "Pasa de registrar gestiones a orquestar decisiones.",
        "bullets": [
            "Ordena la cartera por estrategia, subgrupo, placement, cartera y cabeza de mora.",
            "Opera por roles reales: Admin, Collector, Supervisor y Auditor.",
            "Integra revisión supervisor, callbacks, promesas, HMR y omnicanalidad en el mismo flujo.",
            "Hace visible dónde está cada cliente, quién lo trabaja, bajo qué regla y con qué resultado.",
        ],
        "tag": "Propuesta de valor",
    },
    {
        "title": "IA y Machine Learning con impacto operativo",
        "subtitle": "La inteligencia no se queda en un dashboard; entra a la cola de trabajo.",
        "bullets": [
            "Prioriza cuentas según probabilidad de pago, riesgo y oportunidad de recuperación.",
            "Sugiere canal óptimo, siguiente mejor acción y discurso de contacto.",
            "Permite detectar ruptura probable de promesa y aislar casos que requieren control supervisor.",
            "Ayuda a mover la operación desde intuición manual hacia decisión asistida y repetible.",
        ],
        "tag": "AI + ML aplicado",
    },
    {
        "title": "Qué cambia en la práctica",
        "subtitle": "De una cola manual a una operación industrial de cobranza.",
        "bullets": [
            "El gestor deja de navegar miles de casos sin foco y trabaja colas concretas, visibles y accionables.",
            "El supervisor controla excepciones, productividad y acuerdos fuera de política en tiempo real.",
            "El administrador asigna grupos, carteras y placements con trazabilidad operativa.",
            "Dirección gana disciplina de ejecución sin inflar estructura ni depender de conciliaciones manuales.",
        ],
        "tag": "Transformación operativa",
    },
    {
        "title": "Por qué se pone por encima de muchas alternativas",
        "subtitle": "El mercado ya vende omnicanalidad, workflow y analytics. La ventaja aquí es velocidad y control.",
        "bullets": [
            "Suites como Finvi o QUALCO ya posicionan collections con omnicanalidad, automatización y analytics.",
            "360Collect V3 suma algo crítico: ajuste fino al manual local, control total del producto y demo funcional inmediata.",
            "No depende del roadmap del proveedor para cambiar reglas, subgrupos, placements o estrategia operativa.",
            "Pasa más rápido de concepto a operación medible.",
        ],
        "tag": "Diferenciación",
    },
    {
        "title": "Beneficios que importan a dirección",
        "subtitle": "Esto no es una mejora cosmética; es una palanca de productividad y gobierno.",
        "bullets": [
            "Más recuperación con mejor priorización y contacto oportuno.",
            "Más velocidad para ejecutar estrategia sin fricción operativa.",
            "Más trazabilidad para auditoría, comité y control interno.",
            "Más capacidad para escalar omnicanalidad con disciplina operativa.",
        ],
        "tag": "Beneficios ejecutivos",
    },
    {
        "title": "Cómo empezar sin fricción",
        "subtitle": "La ruta recomendada es rápida, medible y de bajo riesgo.",
        "bullets": [
            "1. Demo ejecutiva por roles y caso completo de punta a punta.",
            "2. Piloto controlado en una estrategia prioritaria.",
            "3. Medición de recuperación, promesas, contactos efectivos y productividad.",
            "4. Escalamiento gradual de canales, reglas y automatizaciones.",
        ],
        "tag": "Ruta de adopción",
    },
    {
        "title": "Cierre para comité",
        "subtitle": "La decisión no es tecnológica. Es estratégica.",
        "bullets": [
            "Hoy no se necesita otro sistema para guardar gestiones.",
            "Se necesita una plataforma que indique a quién gestionar primero, con qué estrategia, por qué canal y bajo qué control.",
            "Eso es exactamente lo que 360Collect V3 empieza a resolver desde ahora.",
            "La pregunta ya no es si sería útil. La pregunta es cuánto seguimos perdiendo por no operarlo plenamente.",
        ],
        "tag": "Llamado a decisión",
    },
]


def p(text: str, level: int = 0, bold: bool = False, size: int = 2200, color: str = "1F2937") -> str:
    bullet = ""
    if level >= 0:
        bullet = f'<a:buChar char="•"/>'
    else:
        bullet = "<a:buNone/>"
    bold_attr = ' b="1"' if bold else ""
    return (
        "<a:p>"
        f"<a:pPr lvl=\"{max(level, 0)}\">{bullet}</a:pPr>"
        f"<a:r><a:rPr lang=\"es-SV\" sz=\"{size}\"{bold_attr} dirty=\"0\" smtClean=\"0\">"
        f"<a:solidFill><a:srgbClr val=\"{color}\"/></a:solidFill>"
        "</a:rPr>"
        f"<a:t>{escape(text)}</a:t></a:r>"
        "</a:p>"
    )


def textbox(shape_id: int, name: str, x: int, y: int, cx: int, cy: int, paragraphs: list[str]) -> str:
    return f"""
    <p:sp>
      <p:nvSpPr>
        <p:cNvPr id="{shape_id}" name="{escape(name)}"/>
        <p:cNvSpPr txBox="1"/>
        <p:nvPr/>
      </p:nvSpPr>
      <p:spPr>
        <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        <a:noFill/>
        <a:ln><a:noFill/></a:ln>
      </p:spPr>
      <p:txBody>
        <a:bodyPr wrap="square" rtlCol="0" anchor="t"/>
        <a:lstStyle/>
        {''.join(paragraphs)}
      </p:txBody>
    </p:sp>
    """


def accent_bar(shape_id: int) -> str:
    return f"""
    <p:sp>
      <p:nvSpPr>
        <p:cNvPr id="{shape_id}" name="Accent Bar"/>
        <p:cNvSpPr/>
        <p:nvPr/>
      </p:nvSpPr>
      <p:spPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="12192000" cy="685800"/></a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        <a:solidFill><a:srgbClr val="0E7490"/></a:solidFill>
        <a:ln><a:noFill/></a:ln>
      </p:spPr>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>
    </p:sp>
    """


def footer_tag(shape_id: int, tag: str) -> str:
    return textbox(
        shape_id,
        "Footer Tag",
        457200,
        6299200,
        3200400,
        411480,
        [p(tag, level=-1, bold=True, size=1600, color="0E7490")],
    )


def slide_xml(index: int, slide: dict) -> str:
    bullet_paragraphs = [p(item, level=0, size=2200, color="334155") for item in slide["bullets"]]
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
      {accent_bar(2)}
      {textbox(3, "Title", 457200, 960120, 10363200, 685800, [p(slide["title"], level=-1, bold=True, size=3000, color="0F172A")])}
      {textbox(4, "Subtitle", 457200, 1714500, 10363200, 822960, [p(slide["subtitle"], level=-1, size=1800, color="0E7490")])}
      {textbox(5, "Body", 685800, 2608580, 10439400, 3200400, bullet_paragraphs)}
      {footer_tag(6, slide["tag"])}
      {textbox(7, "Footer Brand", 9500000, 6400000, 2057400, 320040, [p("360Collect V3", level=-1, bold=True, size=1400, color="64748B")])}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""


SLIDE_LAYOUT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             type="blank" preserve="1">
  <p:cSld name="Blank">
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>"""


SLIDE_MASTER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld name="Office Theme">
    <p:bg><p:bgPr><a:solidFill><a:srgbClr val="F8FAFC"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst>
    <p:sldLayoutId id="2147483649" r:id="rId1"/>
  </p:sldLayoutIdLst>
  <p:txStyles>
    <p:titleStyle/>
    <p:bodyStyle/>
    <p:otherStyle/>
  </p:txStyles>
</p:sldMaster>"""


THEME = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="360Collect Theme">
  <a:themeElements>
    <a:clrScheme name="360Collect">
      <a:dk1><a:srgbClr val="0F172A"/></a:dk1>
      <a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="334155"/></a:dk2>
      <a:lt2><a:srgbClr val="E2E8F0"/></a:lt2>
      <a:accent1><a:srgbClr val="0E7490"/></a:accent1>
      <a:accent2><a:srgbClr val="14B8A6"/></a:accent2>
      <a:accent3><a:srgbClr val="1D4ED8"/></a:accent3>
      <a:accent4><a:srgbClr val="F59E0B"/></a:accent4>
      <a:accent5><a:srgbClr val="EF4444"/></a:accent5>
      <a:accent6><a:srgbClr val="22C55E"/></a:accent6>
      <a:hlink><a:srgbClr val="2563EB"/></a:hlink>
      <a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Office">
      <a:majorFont><a:latin typeface="Aptos Display"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>
      <a:minorFont><a:latin typeface="Aptos"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Office">
      <a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>
      <a:lnStyleLst><a:ln w="9525" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>
      <a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
      <a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
  <a:objectDefaults/>
  <a:extraClrSchemeLst/>
</a:theme>"""


def content_types_xml(slide_count: int) -> str:
    overrides = "\n".join(
        f'  <Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(1, slide_count + 1)
    )
    slide_layout_overrides = '  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
{slide_layout_overrides}
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
{overrides}
</Types>"""


def root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


def app_xml(slide_count: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
            xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Office PowerPoint</Application>
  <PresentationFormat>On-screen Show (16:9)</PresentationFormat>
  <Slides>{slide_count}</Slides>
  <Notes>0</Notes>
  <HiddenSlides>0</HiddenSlides>
  <MMClips>0</MMClips>
  <ScaleCrop>false</ScaleCrop>
  <HeadingPairs>
    <vt:vector size="2" baseType="variant">
      <vt:variant><vt:lpstr>Slides</vt:lpstr></vt:variant>
      <vt:variant><vt:i4>{slide_count}</vt:i4></vt:variant>
    </vt:vector>
  </HeadingPairs>
  <TitlesOfParts>
    <vt:vector size="{slide_count}" baseType="lpstr">
      {''.join(f'<vt:lpstr>Slide {i}</vt:lpstr>' for i in range(1, slide_count + 1))}
    </vt:vector>
  </TitlesOfParts>
  <Company>360Collect</Company>
  <LinksUpToDate>false</LinksUpToDate>
  <SharedDoc>false</SharedDoc>
  <HyperlinksChanged>false</HyperlinksChanged>
  <AppVersion>16.0000</AppVersion>
</Properties>"""


def core_xml() -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:dcmitype="http://purl.org/dc/dcmitype/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>360Collect V3 - Presentación Ejecutiva</dc:title>
  <dc:subject>Cobranza con inteligencia artificial y machine learning</dc:subject>
  <dc:creator>Codex</dc:creator>
  <cp:keywords>360Collect, cobranza, IA, machine learning, ejecutivo</cp:keywords>
  <dc:description>Presentación ejecutiva para comité y alta dirección.</dc:description>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>"""


def presentation_xml(slide_count: int) -> str:
    sld_ids = "\n".join(
        f'    <p:sldId id="{256 + i}" r:id="rId{i + 1}"/>'
        for i in range(slide_count)
    )
    master_rel_id = slide_count + 1
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                saveSubsetFonts="1" autoCompressPictures="0">
  <p:sldMasterIdLst>
    <p:sldMasterId id="2147483648" r:id="rId{master_rel_id}"/>
  </p:sldMasterIdLst>
  <p:sldIdLst>
{sld_ids}
  </p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
  <p:defaultTextStyle/>
</p:presentation>"""


def presentation_rels_xml(slide_count: int) -> str:
    slide_rels = "\n".join(
        f'  <Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, slide_count + 1)
    )
    master_rel_id = slide_count + 1
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{slide_rels}
  <Relationship Id="rId{master_rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
</Relationships>"""


def slide_master_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>"""


def slide_layout_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>"""


def slide_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>"""


def build_pptx() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()

    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        slide_count = len(SLIDES)
        zf.writestr("[Content_Types].xml", content_types_xml(slide_count))
        zf.writestr("_rels/.rels", root_rels_xml())
        zf.writestr("docProps/app.xml", app_xml(slide_count))
        zf.writestr("docProps/core.xml", core_xml())
        zf.writestr("ppt/presentation.xml", presentation_xml(slide_count))
        zf.writestr("ppt/_rels/presentation.xml.rels", presentation_rels_xml(slide_count))
        zf.writestr("ppt/slideMasters/slideMaster1.xml", SLIDE_MASTER)
        zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", slide_master_rels_xml())
        zf.writestr("ppt/slideLayouts/slideLayout1.xml", SLIDE_LAYOUT)
        zf.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", slide_layout_rels_xml())
        zf.writestr("ppt/theme/theme1.xml", THEME)

        for index, slide in enumerate(SLIDES, start=1):
            zf.writestr(f"ppt/slides/slide{index}.xml", slide_xml(index, slide))
            zf.writestr(f"ppt/slides/_rels/slide{index}.xml.rels", slide_rels_xml())


if __name__ == "__main__":
    build_pptx()
    print(os.fspath(OUTPUT))
