# Lỗi encoding hoặc ký tự Unicode trong tài liệu

## 1. Nhận diện lỗi encoding và lỗi hiển thị font

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ HTTP tests với MockMvc, WebTestClient hoặc REST Assured. Test sinh các snippet request, response, fields, headers, parameters và links; Asciidoctor ghép các snippet với nội dung biên soạn để tạo HTML hoặc PDF. Ký tự Unicode có thể đi qua nhiều lớp: file nguồn, JVM, HTTP payload, generated snippet, Asciidoctor processor, HTML browser và PDF renderer.

Những biểu hiện thường gặp:

- Tiếng Việt thành chuỗi ký tự sai như `TÃ i liá»‡u` hoặc `á»`.
- Ký tự có dấu hiển thị thành ô vuông, dấu hỏi hoặc bị mất.
- HTML đúng nhưng PDF lỗi dấu tiếng Việt.
- Snippet chứa ký tự lạ dù response trong test đúng.
- Tên file/đường dẫn có Unicode hoạt động trên máy này nhưng lỗi trên máy khác.
- Nội dung copy từ PDF bị mất dấu hoặc thứ tự ký tự không đúng.

Trước khi sửa, phân biệt hai nhóm nguyên nhân:

| Nhóm lỗi | Biểu hiện | Nguyên nhân thường gặp |
| --- | --- | --- |
| Encoding/charset | Byte được giải mã sai, chữ biến thành mojibake như `Tiáº¿ng Viá»‡t`. | File không phải UTF-8 nhưng được đọc như UTF-8, thiếu charset hoặc process dùng encoding khác. |
| Font/glyph/rendering | Chữ thành ô vuông, dấu bị mất hoặc font thay thế. | Font không có glyph, PDF backend không tìm thấy font, font không được nhúng hoặc fallback không phù hợp. |

UTF-8 giải quyết cách mã hóa byte; nó không tự cung cấp glyph cho font. Ngược lại, cài font tiếng Việt không sửa được một file đã bị giải mã sai.

## 2. Chuẩn hóa file nguồn về UTF-8

Các file `.adoc`, `.md`, `.java`, `.properties`, YAML và JSON có chứa tiếng Việt nên được lưu bằng UTF-8. Kiểm tra encoding thực tế của file thay vì chỉ nhìn chữ trong editor; một editor có thể tự đoán encoding và hiển thị đúng dù file không được lưu theo chuẩn repository.

Trong IDE:

- Kiểm tra encoding của project và từng file.
- Chuyển đổi file sang UTF-8 bằng chức năng convert/reopen with encoding phù hợp.
- Tránh lưu UTF-8 BOM nếu toolchain hoặc script xử lý file không mong đợi BOM; chọn một quy ước nhất quán cho repository.
- Bảo đảm Git diff hiển thị tiếng Việt đúng sau khi lưu.

Ví dụ file AsciiDoc:

```asciidoc
= Tài liệu API cửa hàng

== Tạo đơn hàng

Client gửi thông tin khách hàng và danh sách sản phẩm.
Server trả về mã đơn hàng cùng trạng thái xử lý.
```

Nếu đoạn văn trên hiển thị sai ngay trong source file hoặc khi `git diff`, xử lý encoding file trước khi chạy test/Asciidoctor.

## 3. Giữ UTF-8 nhất quán trong Git và môi trường làm việc

Git thường lưu nội dung file dưới dạng byte và không tự chuyển encoding văn bản theo hệ điều hành. Vì vậy, nhóm nên quy định source files là UTF-8 và review thay đổi có chứa Unicode.

Các kiểm tra hữu ích:

- Mở cùng file bằng editor trên Windows và Linux để so sánh.
- Kiểm tra `git diff` sau khi sửa; nếu toàn bộ tiếng Việt thành ký tự lạ, không commit.
- Tránh chuyển file qua công cụ trung gian tự đổi encoding.
- Với script tạo tài liệu, chỉ định encoding khi đọc/ghi file thay vì dựa vào locale mặc định.
- Dùng tên file/operation identifier ASCII ổn định; nội dung mô tả vẫn có thể dùng Unicode.

Trên PowerShell, khi đọc/ghi file bằng script, chỉ định encoding tường minh. Ví dụ đọc UTF-8:

```powershell
Get-Content -LiteralPath .\src\docs\asciidoc\index.adoc -Encoding UTF8
```

Khi ghi nội dung từ script, chọn API/parameter UTF-8 rõ ràng và xác minh byte/output sau khi ghi. Cú pháp encoding có thể khác giữa Windows PowerShell 5.1 và PowerShell mới; đừng giả định mọi lệnh `Set-Content` có cùng default.

## 4. Kiểm tra encoding của Java/JVM và test fixtures

Java source hiện đại mặc định thường được xử lý theo UTF-8 bởi toolchain/build được cấu hình phù hợp, nhưng vẫn nên khai báo encoding rõ ràng để build không phụ thuộc môi trường.

Ví dụ Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Ví dụ Maven Compiler Plugin:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
```

Nếu test đọc fixture JSON/XML từ `src/test/resources`, kiểm tra encoding của fixture và cách test đọc resource. Tránh dùng `new String(bytes)` mà không chỉ định charset vì kết quả phụ thuộc default charset của JVM:

```java
String json = new String(bytes, StandardCharsets.UTF_8);
```

Khi ghi file:

```java
Files.writeString(path, json, StandardCharsets.UTF_8);
```

Nếu test gửi JSON tiếng Việt, kiểm tra `Content-Type` có charset/MediaType đúng và serializer tạo body đúng. Ví dụ response:

```json
{
  "title": "Tài liệu Spring REST Docs",
  "description": "Hướng dẫn tạo tài liệu có kiểm chứng"
}
```

Hãy assert giá trị sau khi parse response hoặc kiểm tra raw body bytes nếu nghi ngờ charset. Không dựa duy nhất vào log console vì console có thể dùng encoding khác với HTTP payload.

## 5. Phân biệt charset HTTP với encoding của file snippet

HTTP request/response có thể khai báo media type và charset. Ví dụ:

```http
Content-Type: application/json
Accept: application/json
```

JSON hiện đại thường được trao đổi bằng UTF-8; không nên tự thêm `charset` vào mọi Content-Type nếu API/framework không yêu cầu. Điều quan trọng là client/server serialize và decode cùng một encoding theo contract.

Spring REST Docs ghi lại request/response đã được test client và operation xử lý. Nếu raw response bytes đúng UTF-8 nhưng snippet hiển thị sai, kiểm tra bước đọc/ghi snippet hoặc tool mở file. Nếu raw response đã sai, tìm lỗi ở serializer, message converter, fixture hoặc cách test decode body.

Đối với XML, charset có thể xuất hiện trong HTTP Content-Type và XML declaration. Hai khai báo phải nhất quán với byte encoding thực tế; không chỉ sửa declaration trong tài liệu để che giấu bytes sai.

## 6. Kiểm tra generated snippets trước Asciidoctor

Sau khi test chạy, mở trực tiếp các file trong generated snippets, ví dụ:

```text
build/generated-snippets/books-get/
  http-request.adoc
  http-response.adoc
  response-fields.adoc
```

Kiểm tra riêng:

- `http-request.adoc` nếu request body/header có tiếng Việt.
- `http-response.adoc` nếu response JSON/XML có tiếng Việt.
- `request-fields.adoc` và `response-fields.adoc` nếu description chứa dấu.
- `links.adoc` nếu title/description relation có Unicode.

Nếu source file và raw payload đúng nhưng generated snippet sai, khoanh vùng ở REST Docs operation/preprocessor/template hoặc bước ghi/đọc file. Nếu snippet đúng nhưng HTML sai, chuyển sang kiểm tra Asciidoctor và output HTML.

Không sửa trực tiếp file trong `build/generated-snippets` hoặc `target/generated-snippets`; test sẽ tạo lại chúng. Nếu template sinh nội dung sai, sửa nguồn test/template hoặc preprocessing rồi chạy lại test.

## 7. Kiểm tra charset trong HTML output

HTML cần khai báo charset đúng để browser giải mã bytes. HTML5 thường dùng:

```html
<meta charset="UTF-8">
```

Asciidoctor HTML converter thường tạo metadata phù hợp, nhưng nếu dự án dùng custom template, layout hoặc bước hậu xử lý, hãy kiểm tra thẻ meta trong HTML cuối cùng. Đồng thời kiểm tra HTTP response header khi publish web server có trả `Content-Type: text/html; charset=UTF-8` hay không.

Các bước kiểm tra:

1. Mở HTML output dưới dạng text và tìm `<meta charset`.
2. Kiểm tra file bytes thực sự là UTF-8.
3. Mở bằng browser và xem tiếng Việt.
4. Nếu local đúng nhưng portal sai, kiểm tra response header và proxy/CDN có thay charset không.
5. Kiểm tra CSS font-family và fallback nếu ký tự thành ô vuông nhưng source text đúng.

Nếu HTML source chứa chuỗi `Tài liệu API` đúng nhưng browser hiển thị `TÃ i liá»‡u`, nghi ngờ charset declaration/header hoặc byte encoding không khớp. Nếu source đúng, browser charset đúng nhưng một vài glyph thành ô vuông, nghi ngờ font.

## 8. PDF: cấu hình font có glyph tiếng Việt

PDF không giống HTML: PDF renderer cần font có đủ glyph và phải tìm thấy font files. Với Asciidoctor PDF, cấu hình font catalog trong theme hoặc cấu hình backend theo hướng dẫn phiên bản đang dùng.

Ví dụ cấu trúc theme minh họa:

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

Đây là ví dụ khung: đường dẫn font phải tồn tại theo cách Asciidoctor PDF theme loader phân giải trong dự án. Cần chọn phiên bản font có glyph tiếng Việt, đặt font files trong repository/artifact được quản lý và xác minh output. Không copy tên font vào theme rồi giả định renderer tự tìm được font đã cài trên desktop.

Với nội dung tiếng Việt, Noto Sans hoặc font Unicode phù hợp thường là lựa chọn tốt; monospace font cũng cần glyph cho ký tự xuất hiện trong code. Font catalog và fallback phải khớp cấu trúc theme của phiên bản Asciidoctor PDF đang sử dụng.

## 9. Nhúng font và kiểm tra glyph trong PDF

Sau khi render PDF:

- Mở PDF ở ít nhất một viewer phổ biến.
- Phóng to những đoạn có dấu tiếng Việt và ký tự đặc biệt.
- Kiểm tra font embedding bằng công cụ PDF phù hợp, ví dụ `pdffonts` nếu có Poppler.
- Dùng `pdftotext` để trích nội dung và tìm các cụm tiếng Việt quan trọng.
- So sánh ảnh render trang với nội dung trích xuất nếu nghi ngờ encoding/font mapping.

Ví dụ:

```bash
pdffonts build/docs/asciidoc/pdf/api.pdf
pdftotext build/docs/asciidoc/pdf/api.pdf - | grep "Tài liệu API"
```

`pdffonts` cho biết thông tin font và trạng thái embedding theo khả năng công cụ. `pdftotext` kiểm tra lớp text có thể trích xuất; cả hai không thay thế việc mở PDF để xem glyph và layout thực tế.

Nếu PDF hiển thị đúng nhưng copy text bị lỗi, có thể vấn đề nằm ở font encoding/ToUnicode mapping. Nếu text extraction đúng nhưng hình ảnh trang có ô vuông, tập trung vào glyph/font rendering. Chẩn đoán dựa trên cả visual output và extracted text.

## 10. Unicode normalization: NFC và NFD

Một ký tự tiếng Việt có dấu đôi khi được biểu diễn bằng một code point dựng sẵn hoặc bằng ký tự nền cộng combining mark. Hai chuỗi có thể nhìn giống nhau nhưng byte/code point khác nhau. Đây là vấn đề Unicode normalization, không nhất thiết là lỗi charset.

Ví dụ khái niệm:

- NFC thường dùng dạng composed khi có thể.
- NFD biểu diễn một số ký tự bằng base character và combining mark.

Hệ điều hành, filesystem hoặc công cụ tìm kiếm có thể xử lý hai dạng khác nhau. Điều này đặc biệt đáng chú ý với tên file hoặc so sánh chuỗi chính xác.

Với nội dung tài liệu, nên thống nhất normalization (thường NFC) trong quy trình tạo nguồn nếu có nhiều công cụ sinh nội dung. Không normalize mù quáng payload nghiệp vụ hoặc dữ liệu người dùng nếu normalization làm thay đổi semantics/identifier. Chỉ chuẩn hóa nơi phù hợp, chẳng hạn source text và metadata hiển thị.

Ví dụ Java:

```java
String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
```

Nếu tên file operation hoặc snippet identifier chứa Unicode, cân nhắc dùng identifier ASCII ổn định để tránh khác biệt normalization giữa filesystem. Nội dung mô tả tiếng Việt vẫn có thể dùng đầy đủ dấu.

## 11. Kiểm tra terminal và log CI

Terminal có thể hiển thị sai dù file trên đĩa đúng. Ví dụ Windows PowerShell, console host, CI runner hoặc log collector có code page khác nhau. Vì vậy:

- Đừng kết luận file hỏng chỉ dựa trên console output.
- Đọc file bằng editor hỗ trợ UTF-8 hoặc kiểm tra byte encoding.
- Kiểm tra output redirect vào file riêng với encoding rõ ràng.
- Nếu CI artifact đúng nhưng log sai, xử lý encoding log/console riêng.
- Tránh để log debug chứa toàn bộ request/response có dữ liệu nhạy cảm.

Trên Windows, PowerShell 5.1 và PowerShell mới có default encoding khác nhau ở một số cmdlet. Script build/QA nên chỉ định encoding thay vì phụ thuộc default của shell.

## 12. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Source `.adoc` đã sai dấu | File lưu bằng encoding khác UTF-8 hoặc bị chuyển đổi sai. | Convert source về UTF-8 và kiểm tra Git diff. |
| Source đúng, snippet sai | Test fixture/response decode sai hoặc snippet writer/template/preprocessor. | Kiểm tra raw bytes, charset và generated file. |
| Snippet đúng, HTML sai mojibake | HTML bytes và charset declaration/HTTP header không khớp. | Kiểm tra UTF-8 bytes, `<meta charset>` và response header. |
| HTML đúng, PDF thành ô vuông | Font thiếu glyph hoặc fallback không hoạt động. | Cấu hình font Unicode trong Asciidoctor PDF theme. |
| PDF đúng mắt nhưng copy text lỗi | Font ToUnicode mapping hoặc text extraction. | Kiểm tra font embedding và PDF text extraction. |
| Chỉ lỗi trên CI | Locale, default charset, font files hoặc path khác local. | Khai báo UTF-8/font trong build và đóng gói font cần thiết. |
| Một số tên file không tìm thấy | NFC/NFD khác nhau hoặc case sensitivity. | Dùng tên ASCII ổn định hoặc chuẩn hóa tên file có kiểm soát. |
| Log hiển thị sai nhưng artifact đúng | Console/code page/log collector. | Kiểm tra artifact trực tiếp và cấu hình encoding log. |
| Chỉ một số ký tự lỗi | Font không có glyph cho ký tự cụ thể. | Kiểm tra glyph coverage/fallback của font. |

## 13. Checklist thực hành

- [ ] Source `.adoc`, `.md`, `.java`, JSON/XML fixtures được lưu bằng UTF-8.
- [ ] Git diff và editor hiển thị tiếng Việt đúng.
- [ ] Java/build encoding được khai báo rõ ràng khi cần.
- [ ] Test fixture và HTTP payload được serialize/decode bằng charset đúng.
- [ ] Generated snippets đã được mở và kiểm tra trực tiếp.
- [ ] HTML output có UTF-8 charset declaration và publish header phù hợp.
- [ ] CSS font/fallback hỗ trợ glyph cần thiết nếu HTML có ô vuông.
- [ ] Asciidoctor PDF theme dùng font có glyph tiếng Việt và font files tồn tại trong CI.
- [ ] PDF được kiểm tra bằng viewer, font inspection và text extraction.
- [ ] Đã phân biệt encoding sai với font thiếu glyph.
- [ ] Unicode normalization được thống nhất ở source/filename khi cần.
- [ ] CI không phụ thuộc font hoặc locale chỉ có trên máy developer.

Lỗi encoding hoặc Unicode trong tài liệu cần được xử lý tại đúng lớp phát sinh. Nếu source và snippet đã sai byte, sửa encoding/charset của file hoặc payload. Nếu HTML source đúng nhưng browser sai, kiểm tra charset declaration và response header. Nếu HTML đúng nhưng PDF lỗi dấu, kiểm tra font catalog, glyph coverage và embedding. Duy trì UTF-8 xuyên suốt, đóng gói font cần thiết và xác minh cả artifact trực quan lẫn text extraction giúp tài liệu Spring REST Docs hiển thị tiếng Việt nhất quán trên máy developer và CI.

## Tài liệu tham khảo

- [The Unicode Standard – Unicode FAQ](https://www.unicode.org/faq/)
- [W3C – Declaring Character Encodings in HTML](https://www.w3.org/International/questions/qa-html-encoding-declarations)
- [Java – StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Asciidoctor PDF – Fonts](https://docs.asciidoctor.org/pdf-converter/latest/theme/fonts/)
- [Asciidoctor PDF – Themes](https://docs.asciidoctor.org/pdf-converter/latest/theme/)
