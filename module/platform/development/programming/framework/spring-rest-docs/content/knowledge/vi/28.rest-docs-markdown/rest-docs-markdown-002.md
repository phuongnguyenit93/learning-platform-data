# Giới hạn của Markdown so với Asciidoctor

## 1. Mục tiêu và bối cảnh

Spring REST Docs hỗ trợ sinh snippet ở cả định dạng Asciidoctor và Markdown. Điều đó giúp nhóm chọn định dạng phù hợp với hệ thống tài liệu hiện có. Tuy nhiên, **khả năng sinh snippet Markdown không đồng nghĩa Markdown có đầy đủ công cụ biên soạn tài liệu kỹ thuật như Asciidoctor**.

Markdown gọn, phổ biến và được nhiều nền tảng hỗ trợ. Asciidoctor cung cấp hệ thống xử lý tài liệu phong phú hơn: include, attributes, conditional directives, cross references, admonitions, cấu trúc book và các khả năng mở rộng. Khi tài liệu API có nhiều endpoint, module, phiên bản và snippet sinh từ test, khác biệt này ảnh hưởng trực tiếp đến cách tổ chức và build tài liệu.

Bài học thuộc chương **Markdown** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu rồi tích hợp vào build/CI.

Sau bài học, bạn có thể phân biệt Markdown snippet format với hệ thống authoring hoàn chỉnh; so sánh include, attributes, cross references, directives, tables và custom templates; nhận diện giới hạn khi tài liệu lớn; chọn Markdown, Asciidoctor hoặc cách kết hợp; thiết kế pipeline render/publish đáng tin cậy.

> Markdown không phải lựa chọn kém hơn trong mọi tình huống. Nó phù hợp khi nhu cầu tài liệu vừa phải và nền tảng render đã rõ. Asciidoctor có lợi thế khi cần xử lý tài liệu kỹ thuật có cấu trúc, include và tái sử dụng ở quy mô lớn.

## 2. Ba lớp trong quy trình REST Docs

Cần tách ba lớp:

1. **HTTP tests và REST Docs:** thực hiện operation, assertions và ghi nhận request/response.
2. **Snippet templates:** định dạng đầu ra thành Asciidoctor hoặc Markdown.
3. **Authoring/publishing system:** ghép snippet vào trang, xử lý links, cấu trúc tài liệu, render HTML/PDF và publish.

Spring REST Docs hỗ trợ Markdown ở lớp snippet. Công cụ ở lớp thứ ba phụ thuộc hệ thống tài liệu của nhóm.

Ví dụ cấu hình Markdown:

~~~java
documentationConfiguration(restDocumentation)
    .snippets()
    .withTemplateFormat(TemplateFormats.markdown());
~~~

Đổi sang Markdown không thay đổi test, endpoint hay semantics HTTP. Nó chọn template format để render các snippet.

~~~mermaid
flowchart LR
    A["HTTP tests"] --> B["REST Docs operation"]
    B --> C["Snippet templates"]
    C --> D["Markdown hoặc Asciidoctor snippets"]
    D --> E["Authoring / include / navigation"]
    E --> F["Renderer"]
    F --> G["Publish"]
~~~

Vấn đề thường xuất hiện ở bước authoring: Markdown tự thân không cung cấp bộ chỉ thị biên soạn phong phú và thống nhất giữa các renderer.

## 3. So sánh tổng quan

| Khả năng | Markdown | Asciidoctor |
| --- | --- | --- |
| Sinh snippet từ Spring REST Docs | Có qua Markdown template format | Có, là format mặc định. |
| Cú pháp cơ bản | Gọn, dễ đọc trong source | Có cấu trúc tài liệu chuyên dụng. |
| Tables | Phụ thuộc dialect/extension | Có cú pháp bảng tích hợp. |
| Include file | Không có cú pháp chuẩn trong CommonMark | Có directive include. |
| Attributes tái sử dụng | Không có cơ chế chuẩn tương đương | Có document attributes/substitutions. |
| Conditional content | Phụ thuộc plugin/build tooling | Có conditional directives. |
| Cross references | Link Markdown; anchor phụ thuộc renderer | Có anchors và cross references. |
| Admonitions | Phụ thuộc extension/quy ước | Có admonition blocks. |
| Tái sử dụng partials | Phụ thuộc static site generator/plugin | Có include và attributes. |
| Renderer | Nhiều dialect/nền tảng | Asciidoctor toolchain có quy tắc rõ. |
| Onboarding | Thường dễ với người biết Markdown | Cần học thêm AsciiDoc. |
| Tài liệu kỹ thuật lớn | Cần chọn hệ sinh thái hỗ trợ | Phù hợp tài liệu nhiều phần, tái sử dụng. |

Đây không phải giới hạn tuyệt đối của mọi Markdown platform. Static site generator có thể bổ sung include, admonitions, tabs, versioning hoặc cross references. Điểm khác biệt là các tính năng này thuộc hệ sinh thái cụ thể, không phải cú pháp Markdown chuẩn dùng thống nhất ở mọi nơi.

## 4. Giới hạn thứ nhất: include snippet không có chuẩn chung

REST Docs có thể sinh các file:

~~~text
build/generated-snippets/
└── orders-create/
    ├── http-request.md
    ├── http-response.md
    ├── request-body.md
    ├── response-body.md
    └── request-fields.md
~~~

Với Asciidoctor, trang cuối có thể include trực tiếp:

~~~asciidoc
= Orders API

== Tạo đơn hàng

=== HTTP request
include::{snippets}/orders-create/http-request.adoc[]

=== Request fields
include::{snippets}/orders-create/request-fields.adoc[]
~~~

Cú pháp đó là directive của Asciidoctor. Markdown không có cú pháp include chuẩn tương đương mà mọi renderer đều hiểu.

Trang Markdown có thể đánh dấu vị trí cần chèn snippet:

~~~markdown
# Orders API

## Tạo đơn hàng

### HTTP request

<!-- Công cụ build cần ghép orders-create/http-request.md vào đây -->

### Request fields

<!-- Công cụ build cần ghép orders-create/request-fields.md vào đây -->
~~~

Comment không tự đọc file snippet. Cần một công cụ khác thực hiện việc ghép:

- Static site generator có hỗ trợ include/partials.
- Plugin include cho renderer Markdown đang dùng.
- Build task tùy chỉnh đọc snippet và chèn vào trang.
- Bước preprocess tạo Markdown hoàn chỉnh trước khi renderer chạy.

Mỗi lựa chọn có cấu hình, cú pháp và giới hạn riêng. Khi đổi nền tảng docs, include directive của hệ thống cũ có thể không còn hoạt động.

### 4.1. Chi phí bảo trì include tùy chỉnh

Nếu tự viết script ghép snippet, cần xử lý:

- Đường dẫn tương đối và tuyệt đối.
- File không tồn tại hoặc snippet chưa được sinh.
- Include lồng nhau và vòng lặp include.
- Encoding UTF-8.
- Code fence nằm trong snippet.
- Escape nội dung và giữ nguyên newline.
- Thông báo lỗi đủ rõ để CI xác định trang nào thiếu snippet.

Script thay chuỗi đơn giản có thể đủ với tài liệu nhỏ, nhưng dễ hỏng khi có nested partials hoặc nhiều module. Với quy mô lớn, chọn công cụ include đã được dùng và kiểm thử rộng rãi.

## 5. Giới hạn thứ hai: attributes và nội dung tái sử dụng

Asciidoctor hỗ trợ document attributes:

~~~asciidoc
:api-version: v2
:snippets: build/generated-snippets

Tài liệu này mô tả API phiên bản {api-version}.

include::{snippets}/orders-create/http-request.adoc[]
~~~

Khi đổi API version hoặc snippet root, cập nhật attribute tại một nơi. Markdown thuần không có cơ chế biến tài liệu tương đương.

Trong Markdown, nhóm thường dùng front matter hoặc configuration của static site generator, template variables, include/partials hoặc script thay token. Các cơ chế đó không giống nhau giữa Jekyll, Docusaurus, MkDocs, Hugo, VuePress hoặc Git hosting. Vì vậy source Markdown có thể phụ thuộc chặt vào renderer đang dùng.

### 5.1. Tái sử dụng phần mô tả API

Một đoạn giải thích authentication có thể xuất hiện ở nhiều trang. Asciidoctor có thể include cùng một fragment ở nhiều nơi. Trong Markdown, nhóm cần chọn cơ chế partial dùng chung hoặc lặp lại nội dung.

Copy/paste làm nội dung dễ lệch. Nếu dùng partial, cần bảo đảm renderer và local preview hỗ trợ đúng cú pháp đó.

## 6. Giới hạn thứ ba: conditional content và nhiều phiên bản API

Tài liệu API đôi khi cần hiển thị nội dung khác nhau theo phiên bản:

- API v1 dùng field customerName.
- API v2 thay bằng object customer.
- Header chỉ xuất hiện từ phiên bản mới.
- Một operation được deprecated trong bản tiếp theo.

Asciidoctor có conditional directives và attributes:

~~~asciidoc
ifdef::api-v2[]
API v2 sử dụng customer object.
endif::api-v2[]

ifndef::api-v2[]
API v1 sử dụng customerName.
endif::api-v2[]
~~~

Markdown thuần không có conditional directives chuẩn. Có thể dùng template hoặc static site generator để tạo nhiều phiên bản, nhưng logic điều kiện chuyển sang build configuration.

Với nhiều phiên bản, cần quyết định rõ: mỗi version có source page riêng hay một trang có điều kiện; snippet output có tách theo version không; CI build tất cả versions hay chỉ version đang phát triển; link giữa versions có được kiểm tra không; deprecated operation được giữ bao lâu.

Không dùng chung một snippet output directory cho nhiều versions nếu task sau có thể ghi đè task trước.

## 7. Giới hạn thứ tư: cross references và navigation

Markdown hỗ trợ link:

~~~markdown
[Authentication](authentication.md#bearer-token)
~~~

Cách tạo anchor cho heading có thể khác theo renderer, nhất là heading có dấu tiếng Việt, ký tự đặc biệt hoặc heading trùng. Link hoạt động trên một nền tảng chưa chắc hoạt động giống hệt ở nền tảng khác.

Asciidoctor cho phép đặt anchor và tham chiếu bằng ID:

~~~asciidoc
[[bearer-token]]
== Bearer token

Xem thêm <<error-responses,Error responses>>.
~~~

Với tài liệu API lớn, cần duy trì link từ endpoint tới authentication và error conventions; link từ schema tới enum/data type; link giữa operations CRUD; link giữa versions; mục lục và sidebar.

Markdown có thể đáp ứng các nhu cầu đó khi renderer/site generator hỗ trợ. Anchor generation, link validation và sidebar thường thuộc renderer, không thuộc Markdown cơ bản.

## 8. Giới hạn thứ năm: tables, admonitions và cấu trúc tài liệu

Spring REST Docs Markdown templates sử dụng bảng theo dialect **Markdown Extra**. Parser tối giản chỉ hỗ trợ CommonMark có thể không render bảng như mong muốn.

~~~markdown
|Path|Type|Description|
|---|---|---|
|id|Number|Mã đơn hàng|
|status|String|Trạng thái đơn hàng|
~~~

Asciidoctor có bảng tích hợp và hỗ trợ cấu hình cột, span hoặc nội dung phức tạp. Với Markdown, bảng phức tạp có thể khó đọc trong source và không portable giữa renderer.

Admonition là ví dụ khác:

~~~asciidoc
[WARNING]
====
Không gửi access token trong URL query string.
====
~~~

Markdown thuần không có syntax admonition thống nhất. Renderer có thể dùng blockquote, extension hoặc component:

~~~markdown
> **Warning:** Không gửi access token trong URL query string.
~~~

Blockquote hoạt động rộng hơn nhưng semantic role và giao diện cảnh báo có thể không phong phú như admonition block chuyên dụng.

## 9. Giới hạn thứ sáu: custom snippet templates

Spring REST Docs dùng Mustache templates để sinh snippet. Markdown format có template riêng; Asciidoctor format cũng có template riêng.

Nếu muốn thêm cột Constraint vào request-fields, cần:

1. Gắn metadata vào descriptor attributes.
2. Override đúng fields template của format đang dùng.
3. Bảo đảm template đọc attribute.
4. Chạy test xác minh snippet thực tế.
5. Kiểm tra renderer cuối hỗ trợ bảng và cú pháp được sinh.

Không copy nguyên template Asciidoctor sang Markdown vì cú pháp bảng, escaping, code blocks và inline markup khác nhau.

Markdown template còn phải tuân thủ dialect renderer đích hiểu. Nếu template dùng Markdown Extra nhưng site generator chỉ hỗ trợ CommonMark, output có thể sai dù REST Docs sinh file thành công.

## 10. Giới hạn thứ bảy: renderer và portability

Markdown thường được xem là portable, nhưng portability phụ thuộc dialect và extensions:

| Tính năng | Khác biệt có thể gặp |
| --- | --- |
| Tables | Parser có hoặc không có table extension. |
| Heading anchors | Cách tạo slug cho tiếng Việt hoặc heading trùng. |
| Admonitions | Syntax riêng theo plugin/renderer. |
| Tabs | Component riêng, không thuộc Markdown chuẩn. |
| Include | Directive riêng của static site generator. |
| Front matter | Metadata YAML do một số hệ thống hiểu. |
| Code highlighting | Ngôn ngữ/theme phụ thuộc renderer. |
| Relative links | Base URL và path phụ thuộc site build. |

Trước khi chọn Markdown, chốt renderer/site generator, version và danh sách extension. Nên có local preview và CI render bằng cùng cấu hình để tránh khác biệt giữa máy developer và pipeline.

Asciidoctor cũng cần toolchain để render, nhưng document model và directives được định nghĩa tập trung hơn trong Asciidoctor toolchain.

## 11. So sánh một tài liệu API thực tế

Giả sử tài liệu có 80 endpoints, 5 nhóm resource, 3 API versions, authentication fragment dùng chung và nhiều response schemas.

| Nhu cầu | Markdown thuần | Markdown + site generator | Asciidoctor |
| --- | --- | --- | --- |
| Sinh snippet từ REST Docs | Có | Có | Có |
| Ghép snippets tự động | Cần build riêng | Có thể qua partials | Có include |
| Dùng biến version/snippet root | Cần template/build | Có theo generator | Có document attributes |
| Conditional content | Cần preprocess | Có thể qua template/plugin | Có directives |
| Tái sử dụng auth/error fragments | Copy hoặc cơ chế riêng | Có partials | Có includes |
| Navigation lớn | Thủ công | Site generator quản lý | Có cấu trúc book/TOC theo toolchain |
| Renderer nhất quán | Không tự bảo đảm | Phải pin generator/plugins | Pin Asciidoctor toolchain |
| Portability | Phụ thuộc dialect | Phụ thuộc generator | Phụ thuộc Asciidoctor toolchain |

Markdown vẫn khả thi nếu nhóm đã có site generator ổn định, include/partials, versioning và link checker. Nếu chưa có, tổng chi phí tự ghép các tính năng có thể vượt lợi ích source syntax gọn.

## 12. Khi nào nên chọn Markdown?

Markdown phù hợp khi:

- Dự án đã dùng Markdown làm chuẩn.
- Nền tảng Git hosting/static site có renderer rõ ràng.
- Tài liệu đơn giản, ít include lồng nhau.
- Không cần nhiều conditional content hoặc nhiều book versions.
- Contributor quen Markdown và cần review source dễ dàng.
- Đã có plugin/build task đáng tin cậy để ghép snippet.

Nên thử một vertical slice trước: một endpoint request/response, một bảng fields, một link chéo, một custom template và một trang render trong CI. Nếu vòng lặp đó đơn giản, có thể mở rộng.

## 13. Khi nào nên chọn Asciidoctor?

Asciidoctor thường phù hợp khi:

- Tài liệu có nhiều chương, endpoints và fragments tái sử dụng.
- Cần include snippet trực tiếp từ output directory.
- Cần attributes để dùng lại API version, base URL hoặc snippet paths.
- Có nội dung conditional theo version/edition.
- Cần cross references với ID ổn định, admonitions hoặc book structure.
- Nhóm muốn tập trung toolchain tài liệu thay vì tự ghép nhiều plugin Markdown.

Asciidoctor có cú pháp phong phú hơn, nhưng team cần học và duy trì toolchain. Không chuyển định dạng chỉ vì Asciidoctor có nhiều tính năng nếu tài liệu hiện tại đơn giản và Markdown workflow đã hoạt động tốt.

## 14. Mô hình kết hợp

Một nhóm có thể dùng REST Docs Markdown snippets rồi tạo reference docs chính bằng hệ thống Markdown, hoặc dùng Asciidoctor snippets trong một workflow khác. Chỉ nên làm vậy khi pipeline có contract rõ ràng về format từng bước.

~~~mermaid
flowchart TD
    A["HTTP tests"] --> B["REST Docs snippets"]
    B --> C{"Selected output format"}
    C -->|Markdown| D["Markdown snippets"]
    C -->|Asciidoctor| E["Asciidoctor snippets"]
    D --> F["Markdown site generator"]
    E --> G["Asciidoctor build"]
    F --> H["Published API docs"]
    G --> H
~~~

Không sinh cả hai format chỉ để dự phòng nếu không có người duy trì output. Hai định dạng có thể lệch do template tùy chỉnh và renderer khác nhau. Nếu cần song song, cùng một test source phải là nguồn sự thật và CI cần build cả hai.

## 15. Tích hợp lựa chọn format vào CI

CI cần xác nhận không chỉ test pass mà tài liệu thực sự render đúng:

1. Chạy HTTP tests sinh snippets.
2. Kiểm tra output directory và identifiers.
3. Ghép snippets vào trang theo công cụ đã chọn.
4. Render tài liệu với phiên bản toolchain được pin.
5. Chạy link checker và kiểm tra snippet bắt buộc.
6. Review diff generated output.
7. Chỉ publish sau khi tất cả bước thành công.

~~~mermaid
flowchart TD
    A["HTTP tests"] --> B{"Assertions pass?"}
    B -->|No| X["Fail CI"]
    B -->|Yes| C["Generate REST Docs snippets"]
    C --> D["Assemble pages"]
    D --> E["Render Markdown or Asciidoctor"]
    E --> F["Check links, includes and missing snippets"]
    F --> G{"All checks pass?"}
    G -->|No| X
    G -->|Yes| H["Review and publish"]
~~~

Pin version của REST Docs, renderer/site generator, extensions và template overrides. Khi plugin Markdown nâng version và thay đổi anchor/table/include behavior, CI cần phát hiện qua render và link checking.

### 15.1. Ma trận kiểm tra tối thiểu

| Check | Markdown pipeline | Asciidoctor pipeline |
| --- | --- | --- |
| HTTP tests pass | Bắt buộc | Bắt buộc |
| Snippet files exist | Bắt buộc | Bắt buộc |
| Include/partial resolution | Theo generator/plugin | Asciidoctor include processor |
| Table rendering | Kiểm tra Markdown dialect | Kiểm tra Asciidoc table |
| Cross links | Link checker của site | Link validation phù hợp |
| Custom templates | Đúng format ID Markdown | Đúng format ID Asciidoctor |
| UTF-8 | Bắt buộc | Bắt buộc |
| Publish gate | Sau render pass | Sau render pass |

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Markdown snippet sinh thành công nhưng trang rỗng | Chưa có include/ghép file | Cấu hình plugin hoặc build task. |
| Bảng fields vỡ khi deploy | Renderer không hỗ trợ Markdown Extra | Chốt dialect và bật table extension. |
| Local link chạy nhưng production link hỏng | Base URL/relative path khác | Pin cấu hình site, chạy link checker. |
| Nội dung dùng chung bị lệch | Copy/paste hoặc partial không đồng nhất | Dùng partial theo một chuẩn. |
| Nội dung API version cũ xuất hiện | Không có version strategy rõ | Tách source hoặc dùng generator/directives. |
| Warning block hiển thị như quote thường | Renderer không có admonition extension | Dùng syntax hỗ trợ hoặc blockquote rõ. |
| Anchor tiếng Việt không ổn định | Slug phụ thuộc renderer | Đặt anchor thủ công hoặc ID ổn định. |
| Template Markdown khác Asciidoctor | Template format/dialect khác nhau | Duy trì template riêng và test output. |
| CI khác máy developer | Renderer/plugin/locale không được pin | Pin toolchain và dùng cùng lệnh. |
| Chuyển Asciidoctor làm hỏng links | Cú pháp link/anchor khác Markdown | Chuyển đổi có kiểm tra và review. |

## 17. Bài thực hành

Một module API có 20 endpoints, 2 versions, authentication fragment dùng chung, bảng request/response fields và nhiều links chéo.

Thực hiện:

1. Tạo một endpoint REST Docs sinh Markdown snippet và một endpoint sinh Asciidoctor snippet.
2. Ghép từng loại vào trang tài liệu thử nghiệm.
3. Với Markdown, dùng site generator/plugin include và render bảng fields.
4. Với Asciidoctor, dùng attributes cho snippet root/version và include trực tiếp.
5. Tạo đoạn authentication dùng chung; so sánh cách tái sử dụng.
6. Thêm nội dung điều kiện theo API version và kiểm tra cross links.
7. Render cả hai pipeline trong CI, chạy link checker và kiểm tra snippet thiếu.
8. Ghi lại chi phí cấu hình, plugin/build steps và độ dễ review để chọn format cho module.

**Tiêu chí hoàn thành:** giải thích được khác biệt giữa snippet format và authoring system; xác định giới hạn thực tế của Markdown; chọn renderer/extension; ghép snippets ổn định; và chứng minh CI render đúng.

## Tài liệu tham khảo

- [Spring REST Docs — Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html)
- [Spring REST Docs — Working with Markdown](https://docs.spring.io/spring-restdocs/reference/working-with-markdown.html)
- [Asciidoctor — Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/)
- [Asciidoctor — Document Attributes](https://docs.asciidoctor.org/asciidoc/latest/attributes/document-attributes/)
- [CommonMark Specification](https://commonmark.org/)
- [Markdown Extra](https://michelf.ca/projects/php-markdown/extra/)
