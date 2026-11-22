# Phân biệt khả năng định dạng của Asciidoctor và Markdown

## Mục tiêu bài học

Spring REST Docs tạo snippet từ các bài kiểm thử HTTP. Nhóm phát triển có thể biên soạn tài liệu bằng **AsciiDoc và Asciidoctor** hoặc bằng **Markdown** tùy hệ sinh thái tài liệu của dự án. Hai định dạng đều hỗ trợ heading, đoạn văn, danh sách, bảng và code block, nhưng khác nhau ở khả năng dựng tài liệu, cú pháp mở rộng và cách đưa snippet vào trang.

Bài học thuộc chương **Markdown** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi tích hợp vào build và CI.

Sau bài học, bạn có thể:

- Phân biệt Markdown, các biến thể Markdown và AsciiDoc.
- Hiểu vai trò của Asciidoctor trong việc xử lý tài liệu AsciiDoc.
- So sánh include, attributes, admonitions, cross-reference, table và code block.
- Chọn định dạng snippet phù hợp với công cụ render và nền tảng xuất bản.
- Tránh dùng cú pháp Asciidoctor trong Markdown thuần mà không có bộ xử lý tương ứng.
- Thiết kế pipeline test → snippet → assemble → render → publish.
- Giữ nội dung REST Docs được kiểm chứng trong khi tận dụng khả năng trình bày của định dạng tài liệu.

## 1. Markdown, AsciiDoc và Asciidoctor là gì?

**Markdown** là một họ cú pháp đánh dấu văn bản nhẹ. Các chuẩn và biến thể phổ biến gồm CommonMark, GitHub Flavored Markdown (GFM) và Markdown mở rộng của từng static site generator. Vì vậy, không phải mọi nền tảng Markdown đều hỗ trợ cùng một cú pháp.

**AsciiDoc** là ngôn ngữ đánh dấu tài liệu, có cú pháp phong phú hơn cho tài liệu kỹ thuật và sách. File thường có phần mở rộng **.adoc** hoặc **.asciidoc**.

**Asciidoctor** là bộ xử lý dùng để chuyển AsciiDoc thành HTML, DocBook và các định dạng được hỗ trợ qua hệ sinh thái công cụ. Asciidoctor hiểu các tính năng như include directive, document attributes, cross-reference, admonition block, source block và nhiều cấu trúc tài liệu khác.

Có thể hình dung:

~~~text
Markdown source -- Markdown renderer / site generator --> HTML hoặc site

AsciiDoc source -- Asciidoctor --------------------------> HTML / DocBook
                         |
                         +-- extensions / converters ----> định dạng khác
~~~

File .md không tự chạy qua Asciidoctor chỉ vì cả hai cùng chứa heading và code block. Tương tự, file .adoc không trở thành Markdown khi đổi phần mở rộng.

## 2. Những cú pháp cơ bản có vẻ giống nhau

Cả hai định dạng đều biểu diễn được các thành phần quen thuộc:

| Thành phần | Markdown thường gặp | AsciiDoc thường gặp |
| --- | --- | --- |
| Heading cấp 1 | # Tiêu đề | = Tiêu đề |
| Heading cấp 2 | ## Mục | == Mục |
| In đậm | **nội dung** | **nội dung** |
| In nghiêng | *nội dung* | __nội dung__ |
| Inline code | Dấu backtick bao quanh | Dấu backtick bao quanh |
| Unordered list | - mục | * mục |
| Ordered list | 1. mục | . mục |
| Link | [Spring](https://spring.io) | https://spring.io[Spring] |
| Code block | Fenced code block | Source block hoặc literal block |

Ví dụ cùng một đoạn hướng dẫn.

**Markdown**

~~~~markdown
# Orders API

API tạo và tra cứu đơn hàng.

## Tạo đơn hàng

Gửi request **POST** để tạo đơn.

~~~http
POST /api/orders
Content-Type: application/json
~~~
~~~~

**AsciiDoc**

~~~~asciidoc
= Orders API

API tạo và tra cứu đơn hàng.

== Tạo đơn hàng

Gửi request *POST* để tạo đơn.

[source,http]
----
POST /api/orders
Content-Type: application/json
----
~~~~

Phần cú pháp cơ bản có thể chuyển đổi tương đối dễ, nhưng các tính năng tài liệu nâng cao không có ánh xạ một-một.

## 3. So sánh các khả năng định dạng quan trọng

| Khả năng | AsciiDoc/Asciidoctor | Markdown |
| --- | --- | --- |
| Heading, paragraph, list | Có | Có |
| Fenced/source code block | Source block và tùy chọn highlight | Có ở nhiều flavor; cách highlight tùy renderer |
| Table | Nhiều kiểu bảng và cấu trúc cell | Pipe table phổ biến trong GFM; CommonMark cốt lõi không định nghĩa pipe table |
| Include file | Có directive include | Không có cú pháp include file chuẩn trong CommonMark |
| Document attributes/variables | Có attributes như :toc: và {attribute} | Không có cơ chế biến thống nhất trong Markdown chuẩn |
| Cross-reference nội bộ | Có anchor và xref | Thường dùng heading anchor/link; quy tắc anchor tùy renderer |
| Admonition | Có block NOTE, TIP, WARNING | Thường cần blockquote, HTML hoặc extension |
| Conditional content | Có conditional directives theo attribute | Tùy plugin/generator |
| Footnote | Có | Tùy flavor/extension |
| Bibliography/index | Có hỗ trợ qua hệ sinh thái AsciiDoc | Thường dựa plugin hoặc generator |
| Nhiều trang/sách | Hỗ trợ cấu trúc tài liệu dài | Làm được qua site generator; Markdown tự thân không quy định toàn bộ site |

Sự khác biệt có ý nghĩa khi tài liệu REST API lớn dần. AsciiDoc thường thuận tiện khi cần include snippet, attributes dùng chung, cross-reference và cấu trúc sách. Markdown thường thuận tiện khi dự án đã dùng GitHub, GitLab, wiki hoặc static site generator dựa trên Markdown.

## 4. Include snippet: điểm khác biệt dễ gặp nhất

Spring REST Docs sinh snippet theo template mặc định của phiên bản và cấu hình dự án. Với AsciiDoc, trang tài liệu có thể include snippet bằng:

~~~asciidoc
== HTTP request

include::{snippets}/orders-create/http-request.adoc[]

== Request fields

include::{snippets}/orders-create/request-fields.adoc[]

== HTTP response

include::{snippets}/orders-create/http-response.adoc[]

== Response fields

include::{snippets}/orders-create/response-fields.adoc[]
~~~

Thuộc tính {snippets} thường được cấu hình trong build để trỏ đến thư mục snippet. Asciidoctor xử lý include khi render tài liệu; đây không phải cú pháp Markdown thuần.

Với Markdown, không có include directive file phổ quát. Các lựa chọn gồm:

1. Dùng plugin/include directive của static site generator đang chạy.
2. Sinh snippet ở template Markdown nếu REST Docs version hỗ trợ, rồi dùng build-time assembly ghép fragment vào trang.
3. Chuyển đổi tài liệu/snippet sang định dạng phù hợp qua một bước build có kiểm tra.
4. Dùng Asciidoctor làm bộ xử lý cuối nếu cần các tính năng include và cấu trúc của AsciiDoc.

Không để dòng include::{snippets}/...[] trong .md rồi kỳ vọng CommonMark hoặc mọi Markdown renderer tự đọc file. Renderer có thể hiển thị nguyên dòng đó, bỏ qua hoặc xử lý theo extension riêng.

## 5. Attributes so với biến/template của Markdown

AsciiDoc có **document attributes**. Ví dụ:

~~~asciidoc
:doctype: book
:toc: left
:sectnums:
:snippets: build/generated-snippets

include::{snippets}/orders-get/http-response.adoc[]
~~~

Tài liệu có thể tham chiếu attribute bằng {snippets} hoặc cấu hình attribute từ build script/command line.

Markdown chuẩn không có cơ chế variables thống nhất. Một số công cụ có front matter hoặc template variables, ví dụ:

~~~yaml
---
title: Orders API
description: Tài liệu endpoint quản lý đơn hàng
---
~~~

Front matter thường là metadata cho static site generator; nó không phải phần bắt buộc của CommonMark và không tự tạo biến dùng chung trên mọi nền tảng.

Nếu dự án Markdown cần biến như baseUrl, version hoặc snippetsDir, hãy chọn cơ chế cụ thể của generator hoặc truyền dữ liệu trong bước assembly. Ghi rõ generator/version trong build documentation để người khác có thể tái tạo.

## 6. Table: cấu trúc linh hoạt và giới hạn renderer

### 6.1. Bảng Markdown

GFM hỗ trợ pipe table dễ viết:

~~~markdown
| Path | Type | Description |
| --- | --- | --- |
| customerId | Number | Mã khách hàng |
| description | String | Mô tả đơn hàng |
~~~

Pipe table không thuộc cú pháp CommonMark cốt lõi. Nếu Markdown renderer không hỗ trợ table extension, bảng có thể hiển thị thành paragraph hoặc văn bản.

Khi custom template sinh bảng Markdown:

- Escape pipe trong nội dung cell.
- Giữ số cột nhất quán.
- Chuyển nội dung dài nhiều dòng sang đoạn văn bên dưới.
- Giữ code span và HTML theo quy tắc renderer.
- Kiểm tra bảng sau khi render, không chỉ kiểm tra file source.

### 6.2. Bảng AsciiDoc

AsciiDoc hỗ trợ bảng với nhiều cách bố trí cell và cấu hình:

~~~asciidoc
[cols="1,1,3", options="header"]
|===
|Path |Type |Description

|customerId
|Number
|Mã khách hàng

|description
|String
|Mô tả đơn hàng
|===
~~~

AsciiDoc table có thể phù hợp hơn với bảng nhiều cột, cell phức tạp hoặc tài liệu cần điều khiển layout chi tiết. Tuy nhiên, syntax phức tạp hơn cũng cần người biên soạn hiểu cách parser xử lý delimiter và nested block.

## 7. Admonition và nội dung cảnh báo

AsciiDoc có cú pháp admonition chuyên biệt:

~~~asciidoc
[IMPORTANT]
====
Không đưa access token thật vào snippet được xuất bản.
====

[TIP]
====
Dùng fixture kiểm thử riêng cho giá trị cookie và token.
====
~~~

Trong Markdown, có thể dùng blockquote:

~~~markdown
> **Quan trọng**
>
> Không đưa access token thật vào snippet được xuất bản.
~~~

Một số renderer hỗ trợ extension admonition riêng, nhưng cách hiển thị không giống nhau. Nếu dùng Markdown, hãy chọn kiểu cảnh báo mà nền tảng xuất bản hỗ trợ hoặc giữ nội dung ở blockquote thông thường để tăng tính tương thích.

## 8. Cross-reference và liên kết giữa các phần

AsciiDoc hỗ trợ anchor và cross-reference:

~~~asciidoc
[[create-order]]
== Tạo đơn hàng

Xem thêm <<list-orders,Lấy danh sách đơn hàng>>.

[[list-orders]]
== Lấy danh sách đơn hàng
~~~

Markdown thường dùng link tới anchor:

~~~markdown
## Tạo đơn hàng

Xem thêm [Lấy danh sách đơn hàng](#lay-danh-sach-don-hang).

## Lấy danh sách đơn hàng
~~~

Anchor tự sinh từ heading có thể khác giữa GitHub, GitLab và các static site generator. Với link quan trọng, kiểm tra ID thực tế sau render hoặc khai báo anchor theo cơ chế riêng của nền tảng.

AsciiDoc có cơ chế xref được xử lý trong quá trình build, thuận tiện khi tài liệu được chia thành nhiều file hoặc nhiều chapter. Markdown có thể làm việc này qua relative link, nhưng việc kiểm tra link và xử lý version thường thuộc generator.

## 9. Code block và syntax highlighting

Markdown thường dùng fenced code block:

~~~~markdown
~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk());
~~~
~~~~

AsciiDoc thường dùng source block:

~~~~asciidoc
[source,java]
----
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk());
----
~~~~

Cả hai cách đều có thể hiển thị code. Việc tô màu phụ thuộc renderer, cấu hình highlighter và ngôn ngữ được nhận diện. Khi code chứa fence dài hoặc chuỗi delimiter trùng, chọn delimiter ngoài dài hơn để không đóng block sớm.

Với REST Docs, code sample thường lấy từ HTTP snippet như http-request hoặc http-response; không cần copy lại request/response vào code block thủ công nếu snippet đã cung cấp đầy đủ nội dung.

## 10. Chọn định dạng nào cho Spring REST Docs?

Không có một lựa chọn đúng cho mọi dự án. Chọn theo nhu cầu xuất bản và năng lực build hiện có:

| Tiêu chí | Nghiêng về AsciiDoc/Asciidoctor | Nghiêng về Markdown |
| --- | --- | --- |
| Include snippet trực tiếp | Cần include directive tích hợp | Có generator/plugin include hoặc build assembly sẵn |
| Tài liệu dài, nhiều chapter | Cần TOC, attributes, xref, admonitions | Site generator đã quản lý navigation và link |
| Nền tảng xuất bản | Hệ thống hiện tại hỗ trợ AsciiDoc/Asciidoctor | Git hosting, docs site hoặc wiki ưu tiên Markdown |
| Template REST Docs | Dùng template AsciiDoc hiện có | REST Docs version/template Markdown đã được xác nhận |
| Tùy biến table/layout | Cần layout bảng phức tạp | Bảng đơn giản, renderer hỗ trợ đúng flavor |
| Vận hành CI | Có task Asciidoctor trong build | Có test → assembly → Markdown renderer |

Một quy trình AsciiDoc có thể tương đối trực tiếp:

~~~text
HTTP tests
   |
   v
Spring REST Docs snippets (.adoc)
   |
   v
AsciiDoc pages + include directives
   |
   v
Asciidoctor
   |
   v
HTML / documentation artifact
~~~

Một quy trình Markdown thường cần bước assembly hoặc plugin:

~~~text
HTTP tests
   |
   v
Spring REST Docs snippets (Markdown template or converted)
   |
   v
Markdown include plugin / build-time assembly
   |
   v
Markdown site generator
   |
   v
HTML / documentation artifact
~~~

Hãy xác nhận REST Docs version hỗ trợ template format nào. Không giả định mọi phiên bản đều có cùng API Markdown, cùng tên snippet hoặc cùng phần mở rộng file.

## 11. Ví dụ lựa chọn cho một operation

Giả sử test tạo đơn hàng có document identifier orders-create, cùng các descriptor:

~~~java
document("orders-create",
    requestFields(
        fieldWithPath("customerId")
            .description("Mã khách hàng"),
        fieldWithPath("description")
            .description("Mô tả đơn hàng")
    ),
    responseFields(
        fieldWithPath("id")
            .description("Mã đơn hàng"),
        fieldWithPath("status")
            .description("Trạng thái đơn hàng")
    )
)
~~~

Nếu dùng AsciiDoc, trang có thể include:

~~~asciidoc
== Tạo đơn hàng

=== Request

include::{snippets}/orders-create/http-request.adoc[]

=== Request fields

include::{snippets}/orders-create/request-fields.adoc[]

=== Response

include::{snippets}/orders-create/http-response.adoc[]

=== Response fields

include::{snippets}/orders-create/response-fields.adoc[]
~~~

Nếu dùng Markdown, có thể chọn build-time assembly:

~~~text
build/generated-snippets/orders-create/
  http-request.md
  request-fields.md
  http-response.md
  response-fields.md

build/docs-markdown/orders-create.md
~~~

Tác vụ assembly cần kiểm tra đủ bốn file, ghép theo thứ tự và ghi output UTF-8. Nếu snippet thực tế vẫn là .adoc, phải dùng Asciidoctor hoặc bước chuyển đổi đã kiểm tra trước khi ghép Markdown.

## 12. Các lỗi chuyển đổi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Markdown hiển thị nguyên include directive | Asciidoctor directive chạy qua Markdown renderer | Chọn Asciidoctor hoặc Markdown include plugin |
| Pipe table không render | Markdown flavor không hỗ trợ table extension | Dùng renderer hỗ trợ GFM hoặc đổi sang cấu trúc tương thích |
| Admonition mất kiểu cảnh báo | Markdown renderer không có extension admonition | Dùng blockquote hoặc bật plugin phù hợp |
| Cross-reference gãy | Anchor tự sinh khác giữa các renderer | Kiểm tra heading ID hoặc khai báo anchor rõ |
| Attribute {snippets} không được thay thế | Markdown renderer không hiểu AsciiDoc attributes | Dùng cấu hình generator hoặc build assembly |
| Code block không tô màu | Thiếu language tag/highlighter | Khai báo ngôn ngữ và bật syntax highlighting |
| Include file không tồn tại trong CI | Test chưa chạy hoặc path khác working directory | Nối dependency và dùng path dựa trên build directory |
| File .adoc được đổi tên thành .md nhưng không render | Chỉ đổi extension, cú pháp vẫn là AsciiDoc | Sinh template Markdown hoặc chuyển đổi có kiểm soát |
| Nội dung khác nhau giữa local và CI | Khác version renderer/plugin hoặc cấu hình | Pin version và dùng cùng build task |

## 13. Bài thực hành

Tạo tài liệu cho hai operation:

~~~text
POST /api/orders
GET /api/orders/{orderId}
~~~

Yêu cầu:

1. Viết MockMvc test và dùng document(...) để sinh request/response, parameter và field snippets.
2. Dựng một bản tài liệu bằng AsciiDoc, sử dụng attributes và include directives.
3. Dựng một bản Markdown bằng cơ chế include của generator hoặc build-time assembly.
4. So sánh cách trình bày table, source block, admonition và cross-reference ở hai bản.
5. Ghi rõ phiên bản REST Docs, template format và Markdown renderer.
6. Làm CI thất bại khi snippet bắt buộc thiếu hoặc link nội bộ không hợp lệ.
7. Đối chiếu nội dung request/response giữa hai bản để bảo đảm không thay đổi contract.

**Tiêu chí hoàn thành:** hai pipeline render được tài liệu; snippet xuất phát từ cùng test; include/attributes/cross-reference hoạt động theo đúng processor; field table và HTTP exchange không mâu thuẫn; CI kiểm tra output trước khi publish.

## Ghi nhớ

AsciiDoc và Markdown cùng hỗ trợ cấu trúc văn bản cơ bản nhưng có khả năng mở rộng khác nhau. **Asciidoctor** xử lý include, attributes, xref và admonition của AsciiDoc; Markdown phụ thuộc flavor và renderer, không có cú pháp include file chuẩn trong CommonMark. Với Spring REST Docs, hãy chọn định dạng snippet và công cụ render theo nền tảng xuất bản: AsciiDoc thuận tiện khi cần include/attributes trực tiếp; Markdown phù hợp khi dự án có generator hoặc build assembly rõ ràng. Pin version, kiểm tra fragment và so sánh output sau render để bảo đảm tài liệu vẫn phản ánh đúng test HTTP.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Asciidoctor Documentation](https://docs.asciidoctor.org/), [Asciidoctor Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/), [CommonMark Specification](https://commonmark.org/) và [GitHub Flavored Markdown Specification](https://github.github.com/gfm/).
