# Encoding or Unicode Character Errors in Documentation

## 1. Recognizing Encoding Errors vs. Font Rendering Errors

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests produce request, response, field, header, parameter, and link snippets; Asciidoctor combines those snippets with authored content to produce HTML or PDF. Unicode characters can pass through multiple layers: source files, the JVM, HTTP payloads, generated snippets, the Asciidoctor processor, the HTML browser, and the PDF renderer.

Common symptoms:

- Vietnamese text turns into garbled sequences such as `TÃ i liá»‡u` or `á»`.
- Accented characters appear as boxes, question marks, or disappear entirely.
- HTML looks right, while PDF breaks Vietnamese diacritics.
- Snippets contain strange characters even though the response in the test is right.
- Filenames or paths containing Unicode work on one machine yet fail on another.
- Text copied from PDF loses diacritics or scrambles character ordering.

Before fixing, distinguish two categories of causes:

| Error category | Symptom | Common cause |
| --- | --- | --- |
| Encoding/charset | Bytes are decoded wrongly, turning text into mojibake like `Tiáº¿ng Viá»‡t`. | File is not UTF-8 yet is read as UTF-8, missing charset, or process uses a different encoding. |
| Font/glyph/rendering | Characters turn into boxes, diacritics disappear, or fallback fonts trigger. | Font lacks glyphs, PDF backend cannot locate font, font is not embedded, or fallback is unsuitable. |

UTF-8 solves how bytes are encoded; it does not supply glyphs to a font. Conversely, installing Vietnamese fonts will not fix a file whose bytes were already decoded with the wrong encoding.

## 2. Standardizing Source Files on UTF-8

`.adoc`, `.md`, `.java`, `.properties`, YAML, and JSON files containing Vietnamese text should be saved in UTF-8. Check the actual file encoding rather than relying on how text looks in an editor; an editor may guess the encoding and display it correctly even though the file is not saved according to the repository standard.

In your IDE:

- Check both project-level and per-file encodings.
- Convert files to UTF-8 using the appropriate convert/reopen-with-encoding action.
- Avoid saving a UTF-8 BOM if toolchains or file-processing scripts do not expect one; pick one consistent convention for the repository.
- Confirm `git diff` displays Vietnamese text properly after saving.

AsciiDoc file example:

```asciidoc
= Tài liệu API cửa hàng

== Tạo đơn hàng

Client gửi thông tin khách hàng và danh sách sản phẩm.
Server trả về mã đơn hàng cùng trạng thái xử lý.
```

If the paragraph above renders wrongly inside the source file itself or in `git diff`, fix the file encoding before running tests or Asciidoctor.

## 3. Keeping UTF-8 Consistent in Git and Working Environments

Git typically stores file contents as raw bytes without automatically converting text encodings across operating systems. Therefore, the team should standardize source files on UTF-8 and review changes containing Unicode.

Helpful checks:

- Open the same file in editors on Windows and Linux to compare.
- Inspect `git diff` after editing; if all Vietnamese text turns into strange characters, do not commit.
- Avoid passing files through intermediate tools that silently re-encode text.
- For documentation-generation scripts, specify encoding explicitly when reading/writing files rather than relying on the system default locale.
- Use stable ASCII filenames and operation identifiers; descriptive prose can still use full Unicode.

In PowerShell, when reading or writing files via scripts, specify the encoding explicitly. Example reading UTF-8:

```powershell
Get-Content -LiteralPath .\src\docs\asciidoc\index.adoc -Encoding UTF8
```

When writing content from a script, choose an explicit UTF-8 API/parameter and verify the output bytes afterward. Encoding flags and defaults can differ between Windows PowerShell 5.1 and newer PowerShell versions; never assume every `Set-Content` call shares the same default.

## 4. Checking Java/JVM Encoding and Test Fixtures

Modern Java sources are usually processed as UTF-8 by properly configured toolchains and builds, yet it is still good practice to declare encoding explicitly so builds do not depend on environment defaults.

Gradle example:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Maven Compiler Plugin example:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
```

If tests read JSON/XML fixtures from `src/test/resources`, check both the fixture encoding and how the test reads the resource. Avoid `new String(bytes)` without specifying a charset, because the outcome depends on the JVM default charset:

```java
String json = new String(bytes, StandardCharsets.UTF_8);
```

When writing files:

```java
Files.writeString(path, json, StandardCharsets.UTF_8);
```

If a test sends Vietnamese JSON, check that `Content-Type` has the right charset/MediaType and that the serializer produces the right body. Example response:

```json
{
  "title": "Tài liệu Spring REST Docs",
  "description": "Hướng dẫn tạo tài liệu có kiểm chứng"
}
```

Assert parsed response values or inspect raw body bytes if a charset issue is suspected. Do not rely solely on console logs, because the console may use a different encoding from the HTTP payload.

## 5. Distinguishing HTTP Charset from Snippet File Encoding

HTTP requests and responses can declare a media type and charset. For example:

```http
Content-Type: application/json
Accept: application/json
```

Modern JSON is typically exchanged in UTF-8; do not blindly force `charset` onto every `Content-Type` if the API/framework does not require it. What matters is that client and server serialize and decode using the same encoding per contract.

Spring REST Docs records the request/response processed by the test client and operation. If raw response bytes are valid UTF-8 yet the snippet displays garbled text, check the snippet read/write step or the viewer opening the file. If the raw response is already corrupted, look for the bug in the serializer, message converter, fixture, or how the test decodes the body.

For XML, a charset may appear in both the HTTP `Content-Type` and the XML declaration. Both declarations must match the actual byte encoding; never change only the declaration in documentation to mask bad bytes.

## 6. Checking Generated Snippets Before Asciidoctor

After tests run, open the files inside generated snippets directly, for example:

```text
build/generated-snippets/books-get/
  http-request.adoc
  http-response.adoc
  response-fields.adoc
```

Inspect individually:

- `http-request.adoc` if the request body or headers contain Vietnamese text.
- `http-response.adoc` if the response JSON/XML contains Vietnamese text.
- `request-fields.adoc` and `response-fields.adoc` if descriptions contain diacritics.
- `links.adoc` if relation titles or descriptions contain Unicode.

If source files and raw payloads are valid yet generated snippets are garbled, isolate the issue to the REST Docs operation, preprocessor, template, or file read/write step. If snippets are right while HTML is broken, move on to inspecting Asciidoctor and HTML output.

Do not edit files directly in `build/generated-snippets` or `target/generated-snippets`; tests will regenerate them. If a template produces broken content, fix the test source, template, or preprocessing and re-run the tests.

## 7. Checking Charset in HTML Output

HTML must declare the proper charset so browsers decode bytes accurately. HTML5 typically uses:

```html
<meta charset="UTF-8">
```

The Asciidoctor HTML converter normally generates appropriate metadata, but if the project uses a custom template, layout, or post-processing step, inspect the meta tag in the final HTML. Also check whether the web server returns `Content-Type: text/html; charset=UTF-8` in its HTTP response header when published.

Verification steps:

1. Open the HTML output as plain text and look for `<meta charset`.
2. Confirm the file bytes are actually UTF-8.
3. Open it in a browser and check Vietnamese rendering.
4. If it renders properly locally yet breaks on the portal, check whether response headers or a proxy/CDN alter the charset.
5. Check CSS `font-family` and fallbacks if characters render as boxes while source text is valid.

If the HTML source contains the exact string `Tài liệu API` yet the browser renders `TÃ i liá»‡u`, suspect a mismatch between the charset declaration/header and the byte encoding. If the source is right and the browser charset is right, yet certain glyphs turn into boxes, suspect the font.

## 8. PDF: Configuring Fonts with Vietnamese Glyphs

PDF differs from HTML: the PDF renderer needs fonts containing all required glyphs and must be able to locate the font files. With Asciidoctor PDF, configure the font catalog in your theme or backend settings according to your version's documentation.

Illustrative theme structure:

```yaml
extends: default
font:
  catalog:
    Noto Sans:
      normal: NotoSans-Regular.ttf
      bold: NotoSans-Bold.ttf
      italic: NotoSans-Italic.ttf
      bold_italic: NotoSans-BoldItalic.ttf
    Noto Sans Mono:
      normal: NotoSansMono-Regular.ttf
      bold: NotoSansMono-Bold.ttf
      italic: NotoSansMono-Regular.ttf
      bold_italic: NotoSansMono-Regular.ttf
  fallbacks:
    - Noto Sans
base:
  font-family: Noto Sans
code:
  font-family: Noto Sans Mono
```

This is a skeleton example: font paths must exist as resolved by the Asciidoctor PDF theme loader in your project. Choose font builds that include Vietnamese glyphs, store the font files in the repository or a managed artifact, and verify the output. Do not copy font names into a theme assuming the renderer will automatically find fonts installed on a desktop machine.

For Vietnamese content, Noto Sans or another suitable Unicode font is typically a good choice; the monospace font must also support any characters appearing in code blocks. The font catalog and fallbacks must match the theme schema of the Asciidoctor PDF version in use.

## 9. Embedding Fonts and Inspecting Glyphs in PDF

After rendering the PDF:

- Open the PDF in at least one common viewer.
- Zoom in on sections containing Vietnamese diacritics and special characters.
- Inspect font embedding with an appropriate PDF tool, such as `pdffonts` if Poppler is available.
- Use `pdftotext` to extract text and search for key Vietnamese phrases.
- Compare rendered page visuals against extracted text if an encoding or font-mapping bug is suspected.

Example:

```bash
pdffonts build/docs/asciidoc/pdf/api.pdf
pdftotext build/docs/asciidoc/pdf/api.pdf - | grep "Tài liệu API"
```

`pdffonts` reports font metadata and embedding status according to the tool's capabilities. `pdftotext` checks the extractable text layer; neither replaces opening the PDF to inspect actual glyphs and layout.

If the PDF looks right visually yet copying text breaks, the issue may lie in font encoding or `ToUnicode` mappings. If text extraction is accurate yet page visuals show boxes, focus on glyph/font rendering. Diagnose using both visual output and extracted text.

## 10. Unicode Normalization: NFC and NFD

A Vietnamese accented character can be represented either as a single precomposed code point or as a base character plus a combining mark. Two strings may look identical while having different bytes and code points. This is a Unicode normalization issue, not necessarily a charset error.

Conceptual summary:

- NFC generally uses composed forms where available.
- NFD represents certain characters as a base character followed by combining marks.

Operating systems, filesystems, or search tools may treat these two forms differently. This is especially noticeable with filenames or exact string comparisons.

For documentation content, standardize on one normalization form (typically NFC) in the authoring pipeline when multiple tools generate content. Do not blindly normalize business payloads or user data if normalization alters semantics or identifiers. Normalize only where appropriate, such as prose source text and display metadata.

Java example:

```java
String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
```

If operation filenames or snippet identifiers contain Unicode, consider using stable ASCII identifiers to avoid normalization differences across filesystems. Descriptive Vietnamese prose can still use full diacritics.

## 11. Checking Terminals and CI Logs

Terminals can display garbled text even when the file on disk is intact. For instance, Windows PowerShell, console hosts, CI runners, or log collectors may use different code pages. Therefore:

- Never conclude a file is corrupted based solely on console output.
- Inspect the file in a UTF-8-capable editor or check raw byte encoding.
- Redirect output to a dedicated file with an explicit encoding to verify.
- If the CI artifact is intact while logs are garbled, fix log/console encoding separately.
- Avoid printing full requests/responses containing sensitive data in debug logs.

On Windows, PowerShell 5.1 and newer PowerShell versions have different default encodings on certain cmdlets. Build/QA scripts should specify encoding explicitly instead of relying on shell defaults.

## 12. Diagnosing by Symptom

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Source `.adoc` already has broken diacritics | File saved with a non-UTF-8 encoding or misconverted. | Convert source to UTF-8 and inspect `git diff`. |
| Source is right, snippet is broken | Test fixture/response decoded wrongly, or snippet writer/template/preprocessor issue. | Check raw bytes, charset, and generated file. |
| Snippet is right, HTML shows mojibake | HTML bytes mismatch charset declaration or HTTP header. | Verify UTF-8 bytes, `<meta charset>`, and response headers. |
| HTML is right, PDF shows boxes | Font lacks glyphs or fallback is not active. | Configure Unicode fonts in the Asciidoctor PDF theme. |
| PDF looks right, copy-paste text breaks | Font `ToUnicode` mapping or text extraction issue. | Check font embedding and PDF text extraction. |
| Fails only in CI | Locale, default charset, font files, or paths differ from local. | Declare UTF-8/fonts in build and bundle required font files. |
| Some filenames are not found | NFC/NFD differences or case sensitivity. | Use stable ASCII names or normalize filenames carefully. |
| Logs look garbled while artifact is fine | Console/code page/log collector encoding. | Inspect the artifact directly and configure log encoding. |
| Only specific characters fail | Font lacks glyphs for those specific characters. | Check font glyph coverage and fallbacks. |

## 13. Practical Checklist

- [ ] Source `.adoc`, `.md`, `.java`, and JSON/XML fixtures are saved in UTF-8.
- [ ] `git diff` and editors display Vietnamese text properly.
- [ ] Java/build encoding is explicitly declared where needed.
- [ ] Test fixtures and HTTP payloads are serialized/decoded with the right charset.
- [ ] Generated snippets have been opened and inspected directly.
- [ ] HTML output contains a UTF-8 charset declaration and appropriate publish headers.
- [ ] CSS font/fallback supports needed glyphs if HTML shows boxes.
- [ ] Asciidoctor PDF theme uses fonts with Vietnamese glyphs and font files exist in CI.
- [ ] PDF has been verified with a viewer, font inspection, and text extraction.
- [ ] Distinguished encoding errors from missing font glyphs.
- [ ] Unicode normalization is consistent on sources/filenames when needed.
- [ ] CI does not rely on fonts or locales installed only on developer machines.

Encoding or Unicode errors in documentation must be fixed at the exact layer where they occur. If sources and snippets already have corrupted bytes, fix file or payload encoding/charsets. If HTML sources are valid yet the browser garbles text, inspect the charset declaration and response headers. If HTML renders fine while PDF breaks diacritics, check the font catalog, glyph coverage, and embedding. Maintaining UTF-8 end-to-end, bundling required fonts, and verifying both visual artifacts and extracted text ensures Spring REST Docs documentation renders Vietnamese consistently on both developer workstations and CI.

## References

- [The Unicode Standard – Unicode FAQ](https://www.unicode.org/faq/)
- [W3C – Declaring Character Encodings in HTML](https://www.w3.org/International/questions/qa-html-encoding-declarations)
- [Java – StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Asciidoctor PDF – Fonts](https://docs.asciidoctor.org/pdf-converter/latest/theme/fonts/)
- [Asciidoctor PDF – Themes](https://docs.asciidoctor.org/pdf-converter/latest/theme/)
