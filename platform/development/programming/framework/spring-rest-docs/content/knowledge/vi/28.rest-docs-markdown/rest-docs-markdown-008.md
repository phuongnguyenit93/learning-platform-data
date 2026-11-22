# Đảm bảo output Markdown dễ đọc trên nền tảng đích

## 1. Mục tiêu và bối cảnh

Spring REST Docs có thể sinh snippet ở định dạng Markdown từ HTTP tests. Tuy nhiên, file có đuôi .md và nội dung đúng cú pháp chưa bảo đảm người đọc sẽ thấy tài liệu như mong muốn. Kết quả còn phụ thuộc **Markdown parser, dialect, renderer, extensions, theme, cấu hình bảo mật và cách host trang**.

Ví dụ, bảng fields do Spring REST Docs sinh có thể dùng cú pháp Markdown Extra. Một nền tảng chỉ bật CommonMark có thể hiển thị bảng như văn bản thô. Link tương đối có thể chạy trong preview cục bộ nhưng hỏng sau khi deploy dưới base path khác. Code fence có thể render đúng ở Git hosting nhưng mất syntax highlighting ở site generator.

Bài học thuộc chương **Markdown** của module **SPRING_REST_DOCS**. Module tạo tài liệu REST API có thể kiểm chứng từ HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown và đưa vào build/CI.

Sau bài này, bạn có thể:

- Chọn và cố định Markdown parser/dialect trên nền tảng đích.
- Kiểm tra bảng, heading, anchors, code fences, links và images.
- Xử lý HTML nhúng, sanitization và giới hạn bảo mật của renderer.
- Giữ encoding UTF-8, newline và tiếng Việt ổn định.
- Tạo preview gần production và tự động kiểm tra output trong CI.
- Phân biệt lỗi snippet generator với lỗi Markdown renderer/site hosting.

> Nguồn sự thật của nội dung API là test và snippet được sinh. Preview/renderer chịu trách nhiệm trình bày. Khi hiển thị sai, hãy xác định lỗi ở bước sinh snippet, assemble trang hay render cuối trước khi sửa source.

## 2. Tách các bước sinh và hiển thị Markdown

Một pipeline tài liệu thường có các bước:

1. HTTP tests chạy và Spring REST Docs ghi operation.
2. Template format Markdown render snippet thành file .md.
3. Build task ghép snippet với nội dung hướng dẫn thành trang.
4. Markdown parser đọc source và tạo cấu trúc nội dung.
5. Renderer/site generator tạo HTML.
6. Theme, CSS, sanitizer và browser quyết định giao diện cuối cùng.

~~~mermaid
flowchart LR
    A["HTTP tests"] --> B["REST Docs operation"]
    B --> C["Markdown snippets"]
    C --> D["Assemble page"]
    D --> E["Markdown parser"]
    E --> F["HTML renderer / theme"]
    F --> G["Target platform"]
~~~

File snippet tồn tại chưa chứng minh trang cuối đã include nó. Trang assemble có nội dung chưa chứng minh parser hỗ trợ dialect. HTML render thành công cũng chưa chứng minh link, anchor hoặc code block hoạt động trên production.

### 2.1. Xác định nền tảng đích trước khi viết template

Trước khi tùy chỉnh Markdown templates, xác định:

- Nền tảng công bố: Git hosting, MkDocs, Docusaurus, Hugo, site generator khác hay hệ thống nội bộ.
- Parser và dialect đang dùng.
- Extensions/plugins được bật.
- Heading anchors và base URL.
- Chính sách raw HTML và embedded content.
- Theme/CSS cho table, code block, tabs và admonitions.
- Cách tạo preview local và production build.

Không chỉ kiểm tra bằng editor. Editor có thể dùng parser khác với renderer production.

## 3. Markdown dialect và bảng do Spring REST Docs sinh

Spring REST Docs Markdown templates sử dụng bảng theo dialect **Markdown Extra**. Ví dụ bảng fields:

~~~markdown
|Path|Type|Description|
|---|---|---|
|id|Number|Mã đơn hàng|
|status|String|Trạng thái đơn hàng|
|total|Number|Tổng tiền theo VND|
~~~

Renderer hỗ trợ Markdown Extra tables sẽ hiển thị bảng ba cột. Nếu parser chỉ hỗ trợ CommonMark tối giản, các dòng có thể xuất hiện như văn bản chứa dấu gạch đứng.

### 3.1. Hướng xử lý tương thích

| Hướng | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| Bật table extension | Nền tảng cho phép cấu hình parser | Pin extension/version trong build. |
| Chọn renderer hỗ trợ Markdown Extra | Muốn giữ snippet mặc định | Test trên nền tảng đích. |
| Override Markdown template | Bị giới hạn vào dialect cụ thể | Kiểm thử output và giữ metadata fields. |

Không chỉnh raw generated snippet thủ công. Snippet sẽ được tạo lại ở lần test sau. Nếu cần dialect khác, thay template hoặc bước chuyển đổi có kiểm soát.

### 3.2. Bảng quá rộng

Bảng fields có thể có description dài, JSON path lồng nhau hoặc nhiều cột. Trên màn hình nhỏ, bảng dễ tràn ngang. Có thể:

- Viết description ngắn, chuyển giải thích dài sang đoạn văn.
- Tránh thêm cột không giúp người đọc.
- Dùng theme có horizontal overflow cho table.
- Chia nhóm field phức tạp theo object.
- Kiểm tra desktop và mobile.

Không cắt bỏ constraint hoặc ý nghĩa field chỉ để bảng gọn. Hãy tổ chức lại nội dung để giữ nguyên hợp đồng API.

## 4. Heading, anchor và mục lục

Heading tạo cấu trúc điều hướng. Nhiều Markdown renderer tự sinh anchor từ heading text, nhưng quy tắc slug có thể khác nhau ở dấu tiếng Việt/Unicode, punctuation, heading trùng, inline code/link và version renderer.

Ví dụ:

~~~markdown
## Tạo đơn hàng
### Request fields
### Response fields
~~~

Link tới heading:

~~~markdown
[Xem phần Request fields](#request-fields)
~~~

Anchor chính xác phải được xác nhận bằng HTML đã render hoặc công cụ docs đang dùng. Không giả định mọi renderer đều loại dấu hoặc tạo slug giống nhau.

### 4.1. Heading trùng nhau

Nếu một trang có nhiều operation cùng heading Request fields, renderer có thể tạo anchor trùng hoặc tự thêm hậu tố. Mục lục có thể trỏ nhầm section.

Nên đặt heading có ngữ cảnh:

~~~markdown
### Tạo đơn hàng — Request fields
### Cập nhật đơn hàng — Request fields
### Xóa đơn hàng — Response
~~~

Hoặc dùng explicit anchor nếu nền tảng hỗ trợ syntax ổn định. Khi đổi heading, kiểm tra lại links nội bộ và navigation sidebar.

### 4.2. Quy tắc heading

- Dùng một H1 làm tiêu đề chính.
- Không nhảy cấp heading tùy tiện.
- Dùng heading theo cấu trúc thông tin, không chỉ theo kích thước.
- Giữ heading ngắn và thể hiện nội dung.
- Kiểm tra mục lục theo đúng cấp.
- Không dựa vào slug ngẫu nhiên từ một đoạn mô tả dài.

Hierarchy tốt hỗ trợ navigation, accessibility và bảo trì.

## 5. Code fences và syntax highlighting

REST Docs snippets có thể chứa HTTP request/response hoặc JSON body. Dùng fenced code blocks với language identifier mà renderer hỗ trợ.

Ví dụ HTTP và JSON:

~~~~markdown
~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
~~~

~~~json
{
  "customerId": 101,
  "items": [
    {
      "sku": "BOOK-42",
      "quantity": 2
    }
  ]
}
~~~
~~~~

Khi nội dung code đã chứa ba dấu backtick hoặc ba dấu tilde liên tiếp, dùng fence bên ngoài dài hơn hoặc delimiter khác. Điều này quan trọng khi trang có ví dụ Markdown chứa code fence.

Các lỗi thường gặp:

- Quên fence đóng làm phần còn lại của trang thành code.
- Language identifier không được renderer nhận diện.
- JSON sai cú pháp nhưng vẫn được tô màu.
- HTTP snippet bị cắt dòng do preprocess.
- Code block trong partial bị lồng sai khi assemble.

### 5.1. Syntax highlighting không kiểm tra cú pháp

Renderer có thể tô màu JSON/Java dù code không compile hoặc JSON không hợp lệ. HTTP snippets phản ánh operation được test, nhưng đoạn code giải thích do người viết thêm vẫn cần kiểm tra riêng.

Dùng identifier như java, json, http, bash hoặc ngôn ngữ renderer hỗ trợ. Nếu không biết identifier, để plain text an toàn hơn dùng nhãn sai.

## 6. Links tương đối và base URL

Markdown hỗ trợ link tương đối:

~~~markdown
[Xem Authentication](authentication.md)
[Xem Orders API](../orders/index.md)
~~~

Link được site generator/browser giải quyết theo vị trí page, permalink và base URL. Khi site deploy dưới subpath như /docs/v2/, link bắt đầu từ root có thể hoạt động khác link tương đối.

Nên kiểm tra:

- Link giữa pages trong source.
- Link tới anchor trong cùng page.
- Link từ operation tới schemas/authentication.
- Link ngoài tới tài liệu tiêu chuẩn.
- Base URL trong preview và production.
- Trailing slash và permalink strategy.
- Link tới file download/image assets.

### 6.1. Snippet path không phải website URL

REST Docs/Asciidoctor include dùng filesystem path lúc build. Website link được browser mở sau khi publish. Không đặt đường dẫn build/generated-snippets/... vào link công khai với kỳ vọng browser truy cập được directory build.

Sau assemble, link của người đọc phải trỏ tới page/asset nằm trong site output. Đường dẫn file generated chỉ dành cho build/preprocessor.

### 6.2. Link checker

Link checker có thể phát hiện file đích không tồn tại, anchor không có trong HTML, relative path sai sau deploy, redirect/external URL lỗi và link tới source path không được publish.

External link có thể bị chặn bởi mạng CI hoặc rate limit. Cấu hình retry/allowlist hợp lý và phân biệt lỗi mạng tạm thời với link hỏng thật.

## 7. Images, diagrams và assets

Khi thêm hình ảnh:

~~~markdown
![Luồng request qua API gateway](images/order-request-flow.png)
~~~

Lưu ý:

- Đặt assets trong source-controlled directory hoặc tạo bằng build.
- Dùng đường dẫn tương đối phù hợp site generator.
- Viết alt text mô tả nội dung có ích.
- Tối ưu kích thước ảnh.
- Kiểm tra ảnh dưới base path production.
- Không dùng đường dẫn filesystem trên máy cá nhân.

Mermaid có thể được một số nền tảng hỗ trợ, nhưng không phải renderer nào cũng bật plugin Mermaid. Xác nhận extension/renderer hỗ trợ và có fallback như SVG/PNG hoặc mô tả văn bản nếu cần.

## 8. Raw HTML và sanitization

Markdown parser có thể cho phép một mức HTML inline/block, nhưng nền tảng host có thể sanitize HTML để giảm rủi ro XSS. Tag/attribute bị lọc có thể làm output khác preview local.

Ví dụ HTML:

~~~html
<details>
  <summary>Chi tiết response</summary>
  Nội dung bổ sung có thể thu gọn.
</details>
~~~

Một số platform hỗ trợ details/summary, một số renderer khác loại bỏ hoặc hiển thị như text. Inline script, event handler và embedded iframe có thể bị chặn hoàn toàn.

Nguyên tắc:

- Không dựa vào JavaScript tùy ý trong Markdown.
- Không chèn HTML không rõ nguồn gốc từ response/user input.
- Không tắt sanitization chỉ để giữ widget trang trí.
- Ưu tiên component/extension được nền tảng hỗ trợ.
- Kiểm tra rendered HTML/DOM sau sanitizer.
- Cung cấp fallback text nếu HTML nâng cao bị loại bỏ.

Nếu snippet chứa dữ liệu API do test tạo, tránh nhúng dữ liệu đó trực tiếp vào raw HTML. Code blocks và escaped text phù hợp hơn để trình bày request/response.

## 9. UTF-8, tiếng Việt và line endings

Tài liệu tiếng Việt cần giữ UTF-8 từ source đến site output. Lỗi encoding có thể xuất hiện ở snippets, preprocessor, build process hoặc renderer.

Kiểm tra:

- Source Markdown lưu UTF-8.
- HTTP response fixture có charset xác định nếu chứa văn bản.
- Build process không dùng encoding mặc định của hệ điều hành.
- Renderer/HTML document dùng UTF-8.
- Line endings LF/CRLF được xử lý ổn định.
- Unicode normalization không làm hỏng tên field hoặc link.
- Search/indexing vẫn tìm được từ có dấu.

Với response API, charset phải theo HTTP Content-Type thực tế; không suy diễn charset từ file Markdown.

### 9.1. Whitespace và line breaks

Markdown có quy tắc riêng cho paragraph, hard line break, list continuation và blockquotes. Một số editor wrap dòng hiển thị mà không thay newline trong file; preprocessor có thể làm mất blank lines.

Kiểm tra assembled page để chắc:

- Heading không dính vào paragraph trước.
- List lồng nhau giữ indentation.
- Code blocks giữ whitespace.
- Table không bị ngắt giữa row.
- Snippet kế tiếp được ngăn cách bằng blank line hợp lý.

## 10. Theme, responsive layout và accessibility

Cùng một Markdown HTML có thể nhìn khác tùy theme CSS. Kiểm tra:

| Thành phần | Điều cần xác nhận |
| --- | --- |
| Heading | Kích thước, hierarchy, anchor. |
| Tables | Overflow, wrapping và header semantics. |
| Code blocks | Contrast, horizontal scroll, copy action. |
| Links | Màu, underline, focus state. |
| Images | Kích thước, alt text và scaling. |
| Admonitions | Icon, màu và text thay thế. |
| Navigation | Sidebar, TOC, active section. |
| Mobile | Không tràn ngang toàn trang. |

Không dùng màu sắc duy nhất để biểu thị error/success. Heading và alt text cần có ý nghĩa; liên kết có label mô tả đích; code block phải đọc được trên màn hình nhỏ.

## 11. Preview giống nền tảng đích

Preview bằng Markdown viewer khác chưa đủ nếu nó dùng parser/theme khác production. Nên dùng chính site generator và cấu hình deploy cho local preview.

Quy trình:

1. Chạy tests sinh Spring REST Docs snippets.
2. Assemble source pages và snippets.
3. Chạy site generator với cùng config/extensions như production.
4. Mở page trên browser ở desktop và mobile widths.
5. Kiểm tra headings, tables, links, images và code highlighting.
6. Kiểm tra HTML sau sanitization nếu host có bước này.
7. Thử navigation từ index/sidebar tới từng operation.

Nếu platform không cung cấp local preview giống production hoàn toàn, ghi lại sai khác và tạo smoke test ở preview environment sau deploy.

## 12. Tự động hóa kiểm tra trong CI

~~~mermaid
flowchart TD
    A["HTTP tests"] --> B["Generate Markdown snippets"]
    B --> C["Assemble pages"]
    C --> D["Validate Markdown syntax"]
    D --> E["Render with pinned platform toolchain"]
    E --> F["Check links, anchors and assets"]
    F --> G["Inspect generated HTML / warnings"]
    G --> H{"All checks pass?"}
    H -->|No| X["Fail CI"]
    H -->|Yes| I["Publish docs"]
~~~

CI nên:

- Pin parser, renderer, extensions và theme version.
- Chạy test sinh snippets trước assemble/render.
- Báo lỗi nếu snippet bắt buộc thiếu.
- Validate Markdown và code fences.
- Kiểm tra broken links/anchors/assets.
- Render toàn bộ site, không chỉ một file.
- Fail nếu có unresolved include markers hoặc warning quan trọng.
- Lưu artifact HTML để review khi pull request thay đổi tài liệu.
- Chỉ publish sau khi tests và rendering pass.

Nâng version có chủ đích, đọc changelog, render lại và review thay đổi hiển thị.

### 12.1. Review source diff và rendered diff

Generated Markdown diff cho thấy text/template thay đổi. Rendered HTML hoặc screenshot preview cho thấy thay đổi thực tế ở bảng, headings, code blocks và links. Hai dạng review bổ sung cho nhau.

Với thay đổi lớn, lưu preview artifact để reviewer kiểm tra. Không cần screenshot cho mọi thay đổi prose; dùng khi template/theme/layout đổi đáng kể.

## 13. Ma trận kiểm tra output

| Hạng mục | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Markdown tables | Render trên parser đích | Bảng đúng cột/header. |
| Headings | Kiểm tra outline | Hierarchy hợp lý. |
| Anchors | Link checker | Mục lục trỏ đúng section. |
| Code fences | Markdown lint/render | Code block đóng/mở đúng. |
| Syntax highlighting | Browser preview | Language identifier hợp lệ. |
| Links | Link checker/browser | Relative/base paths đúng. |
| Images/diagrams | Build/browser | Asset tải được, có alt text. |
| Raw HTML | Kiểm tra sau sanitizer | Nội dung được phép vẫn hiển thị. |
| UTF-8 | Source và HTML | Tiếng Việt không lỗi dấu. |
| Mobile layout | Responsive check | Table/code có scroll hợp lý. |
| Accessibility | Keyboard/outline/contrast | Điều hướng và nội dung dễ tiếp cận. |
| Clean build | Pipeline từ output trống | Kết quả tái tạo ổn định. |

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Bảng fields hiện thành text | Renderer thiếu Markdown Extra table support | Bật extension hoặc override template. |
| Mục lục trỏ sai | Anchor slug khác renderer | Kiểm tra sau render hoặc đặt ID ổn định. |
| Code block nuốt phần còn lại | Fence chưa đóng/lồng sai | Kiểm tra delimiter, dùng fence ngoài dài hơn. |
| Java/JSON không highlight | Language identifier sai/thiếu highlighter | Dùng identifier được hỗ trợ. |
| Link local đúng nhưng deploy sai | Base URL/permalink khác | Preview với production config. |
| Ảnh không tải | Relative path sai hoặc asset không publish | Kiểm tra asset output. |
| HTML details biến mất | Sanitizer loại tag/attribute | Dùng component được hỗ trợ hoặc fallback. |
| Tiếng Việt lỗi dấu | Encoding không nhất quán | Giữ UTF-8 toàn pipeline. |
| Bảng tràn trên mobile | Cột quá rộng/theme thiếu overflow | Điều chỉnh content/theme, giữ đủ thông tin. |
| Markdown lint pass nhưng site sai | Lint không dùng parser/theme đích | Render bằng toolchain production. |
| Preview khác production | Version/plugin/theme không pin | Dùng cấu hình chung. |
| Snippet cũ được render | Output stale hoặc task dependency sai | Clean output và chạy tests trước render. |

## 15. Bài thực hành

Lấy một trang API có ít nhất ba operations, bảng request/response fields, code examples, links chéo và một hình minh họa.

Thực hiện:

1. Xác định nền tảng đích, parser/dialect, renderer và extensions.
2. Chạy REST Docs tests và assemble trang Markdown.
3. Render bảng fields; xác minh Markdown Extra tables được hỗ trợ.
4. Kiểm tra mục lục, headings và anchors, gồm heading trùng/tiếng Việt.
5. Kiểm tra HTTP/JSON code fences và language identifiers.
6. Kiểm tra relative links, base URL, images/diagrams và asset paths.
7. Thử raw HTML được nền tảng cho phép; xác minh sanitization và fallback.
8. Kiểm tra UTF-8, newline, table overflow và responsive layout.
9. Tạo local preview bằng production config và lưu artifact HTML trong CI.
10. Cấu hình link checker, Markdown validation và render gate trước publish.

**Tiêu chí hoàn thành:** trang Markdown hiển thị đúng trên renderer đích; bảng/heading/code/link/image không lỗi; tiếng Việt giữ UTF-8; preview phù hợp production; CI phát hiện lỗi Markdown, link và render trước publish.

## Tài liệu tham khảo

- [Spring REST Docs — Working with Markdown](https://docs.spring.io/spring-restdocs/reference/working-with-markdown.html)
- [Spring REST Docs — Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html)
- [CommonMark Specification](https://commonmark.org/)
- [Markdown Extra](https://michelf.ca/projects/php-markdown/extra/)
- [MkDocs — Writing Your Docs](https://www.mkdocs.org/user-guide/writing-your-docs/)
- [Docusaurus — Markdown Features](https://docusaurus.io/docs/markdown-features)
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
