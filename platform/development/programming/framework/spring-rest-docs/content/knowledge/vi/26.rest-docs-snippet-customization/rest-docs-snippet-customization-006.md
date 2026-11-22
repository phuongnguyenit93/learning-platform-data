# Tùy chỉnh template cho fields và parameters

## 1. Vì sao fields và parameters cần template riêng?

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Test mô tả request, response, payload, tham số, header và hypermedia links bằng descriptor. Spring REST Docs dùng descriptor để sinh snippet, sau đó ghép chúng vào Asciidoctor/Markdown và quy trình build, CI.

Hai nhóm snippet fields và parameters xuất hiện ở hầu hết API:

- **Fields** mô tả cấu trúc payload JSON/XML: đường dẫn, kiểu dữ liệu, mô tả và metadata bổ sung.
- **Parameters** mô tả các giá trị trong URL: path parameters và query parameters, cùng ý nghĩa, tính bắt buộc hoặc định dạng.

Template mặc định cung cấp bảng cơ bản. Dự án có thể cần thêm cột Constraints, Example, Format, Default, Required hoặc Since để người dùng API hiểu cách gửi dữ liệu.

Mỗi loại snippet có template riêng. Thay request-fields không làm thay đổi path-parameters hay query-parameters. Cần chọn đúng template theo loại snippet test tạo ra.

## 2. Nhận diện các snippet fields và parameters

| API tạo snippet | File đầu ra Asciidoctor | Template nguồn |
| --- | --- | --- |
| requestFields(...) | request-fields.adoc | request-fields.snippet |
| responseFields(...) | response-fields.adoc | response-fields.snippet |
| pathParameters(...) | path-parameters.adoc | path-parameters.snippet |
| queryParameters(...) | query-parameters.adoc | query-parameters.snippet |
| formParameters(...) | form-parameters.adoc | form-parameters.snippet |

Khi dùng Markdown, phần mở rộng đầu ra do TemplateFormat quy định. Tên template nguồn vẫn theo loại snippet và có phần mở rộng .snippet.

Template override nằm trên test classpath tại package org/springframework/restdocs/templates/{format-id}. Với Asciidoctor:

~~~text
src/test/resources/
└── org/springframework/restdocs/templates/asciidoctor/
    ├── request-fields.snippet
    ├── response-fields.snippet
    ├── path-parameters.snippet
    └── query-parameters.snippet
~~~

Chỉ tạo các file override cần thiết. Những snippet khác tiếp tục dùng template mặc định của phiên bản Spring REST Docs đang sử dụng.

## 3. Snippet-level và descriptor-level attributes

Khi tùy chỉnh bảng, xác định metadata thuộc phạm vi nào:

| Phạm vi | Gắn vào đâu | Ví dụ |
| --- | --- | --- |
| Snippet-level | Map attributes truyền cho requestFields, pathParameters hoặc queryParameters | Tiêu đề, API version, ghi chú chung |
| Descriptor-level | attributes(...) trên FieldDescriptor hoặc ParameterDescriptor | Constraint, example, unit, format, default |

Ví dụ bảng request fields có tiêu đề “Tạo đơn hàng” ở cấp snippet; field quantity có constraint “Phải lớn hơn 0” ở cấp descriptor. Template đọc cả hai phạm vi để trình bày đúng.

Attributes là metadata do test cung cấp. Spring REST Docs không tự đọc Bean Validation hay cấu hình controller để suy ra mọi ràng buộc. Nếu muốn công bố ràng buộc, test phải truyền chúng hoặc dùng helper riêng.

## 4. Tùy chỉnh template cho request fields

### 4.1. Truyền metadata trong test

Sử dụng requestFields(...) với map attributes ở cấp snippet và attributes trên từng field:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

requestFields(
        attributes(
                key("title").value("Các trường khi tạo đơn hàng"),
                key("api-version").value("v1"),
                key("note").value("Số lượng phải là số nguyên dương")),
        fieldWithPath("productId")
                .description("Mã sản phẩm")
                .attributes(
                        key("format").value("UUID"),
                        key("example").value("a4f8c960-1c2d-4e9b-8b35-0f8f3c1b5a20")),
        fieldWithPath("quantity")
                .description("Số lượng đặt mua")
                .attributes(
                        key("constraints").value("Lớn hơn hoặc bằng 1"),
                        key("example").value("2")))
~~~

title, api-version và note thuộc snippet. format, constraints và example gắn với descriptor của field tương ứng.

### 4.2. Template request-fields

Tạo file src/test/resources/org/springframework/restdocs/templates/asciidoctor/request-fields.snippet:

~~~mustache
{{#title}}
.{{title}}
{{/title}}
{{#api-version}}
Phiên bản API: {{api-version}}
{{/api-version}}
{{#note}}
NOTE: {{note}}
{{/note}}

|===
|Path|Type|Description|Constraints|Format|Example
{{#fields}}
|{{path}}
|{{type}}
|{{description}}
|{{constraints}}
|{{format}}
|{{example}}
{{/fields}}
|===
~~~

Section title, api-version và note chỉ hiển thị khi có giá trị. Section fields lặp qua từng field descriptor. Các placeholder trong section đọc metadata đã gắn vào descriptor.

Bắt đầu từ template mặc định của đúng phiên bản Spring REST Docs rồi sửa bảng. Cách này giữ được những biến chuẩn mà template đang dùng, chẳng hạn trạng thái field optional hoặc metadata đặc thù.

## 5. Tùy chỉnh template cho response fields

Request và response fields có template riêng. Có thể tái sử dụng quy ước cột nhưng nội dung cần phù hợp ngữ cảnh.

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

responseFields(
        attributes(
                key("title").value("Thông tin đơn hàng trả về"),
                key("api-version").value("v1")),
        fieldWithPath("id")
                .description("Mã đơn hàng")
                .attributes(key("format").value("UUID")),
        fieldWithPath("status")
                .description("Trạng thái đơn hàng")
                .attributes(key("example").value("PENDING")),
        fieldWithPath("total")
                .description("Tổng tiền")
                .attributes(key("unit").value("VND")))
~~~

Tạo template response-fields.snippet riêng để định dạng response fields. Có thể dùng các cột Path, Type, Description, Format, Example và Unit. Bảo đảm mỗi placeholder có attribute tương ứng hoặc được xử lý như giá trị tùy chọn.

Không sao chép nguyên template request-fields sang response-fields mà quên đổi tiêu đề hoặc metadata. Người đọc cần phân biệt field client gửi với field server trả về.

## 6. Tùy chỉnh template cho path parameters

Path parameters là biến nằm trong URI template, ví dụ /api/orders/{orderId}. Spring REST Docs cung cấp pathParameters(...) với overload nhận map attributes ở cấp snippet:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

pathParameters(
        attributes(
                key("title").value("Tham số đường dẫn của API đơn hàng"),
                key("api-version").value("v1")),
        parameterWithName("orderId")
                .description("Mã đơn hàng")
                .attributes(
                        key("format").value("UUID"),
                        key("example").value("d2f89a10-1bc8-44b0-8c48-7a2f58a1bd01")))
~~~

title và api-version áp dụng cho cả snippet path-parameters; format và example thuộc parameter orderId.

### Ví dụ MockMvc

~~~java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/orders/{orderId}", "d2f89a10-1bc8-44b0-8c48-7a2f58a1bd01"))
        .andExpect(status().isOk())
        .andDo(document("orders-get",
                pathParameters(
                        attributes(key("title").value("Tham số đường dẫn đơn hàng")),
                        parameterWithName("orderId")
                                .description("Mã đơn hàng")
                                .attributes(key("format").value("UUID")))));
~~~

Với MockMvc và Spring Framework 6.1 trở xuống, để path parameters sẵn có cho REST Docs, cần dựng request bằng RestDocumentationRequestBuilders thay vì MockMvcRequestBuilders. Với phiên bản mới hơn, kiểm tra hướng dẫn tương ứng của phiên bản framework đang dùng.

### Template path-parameters

Tạo file path-parameters.snippet:

~~~mustache
{{#title}}
.{{title}}
{{/title}}
{{#api-version}}
Phiên bản API: {{api-version}}
{{/api-version}}
|===
|Name|Description|Format|Example
{{#parameters}}
|{{name}}
|{{description}}
|{{format}}
|{{example}}
{{/parameters}}
|===
~~~

Model template của parameter snippet không giống hệt field snippet. Đối chiếu với template mặc định path-parameters.snippet đúng phiên bản để giữ các biến chuẩn đang được dùng và cách biểu diễn trạng thái parameter.

## 7. Tùy chỉnh template cho query parameters

Query parameters nằm sau dấu ? trong URL, ví dụ /api/orders?status=PAID&page=0. Dùng queryParameters(...) để mô tả:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.snippet.Attributes.attributes;
import static org.springframework.restdocs.snippet.Attributes.key;

queryParameters(
        attributes(
                key("title").value("Bộ lọc và phân trang đơn hàng"),
                key("note").value("page bắt đầu từ 0; size tối đa 100")),
        parameterWithName("status")
                .description("Lọc theo trạng thái")
                .attributes(
                        key("example").value("PAID"),
                        key("allowed-values").value("PENDING, PAID, CANCELLED")),
        parameterWithName("page")
                .description("Số trang")
                .attributes(
                        key("default").value("0"),
                        key("constraints").value("Lớn hơn hoặc bằng 0")),
        parameterWithName("size")
                .description("Số phần tử mỗi trang")
                .attributes(
                        key("default").value("20"),
                        key("constraints").value("Từ 1 đến 100")))
~~~

title và note mô tả nhóm query parameters. Mỗi parameter có metadata riêng về ví dụ, giá trị cho phép, mặc định và giới hạn.

### Gọi queryParameters trong MockMvc

~~~java
mockMvc.perform(get("/api/orders")
                .queryParam("status", "PAID")
                .queryParam("page", "0")
                .queryParam("size", "20"))
        .andExpect(status().isOk())
        .andDo(document("orders-search",
                queryParameters(
                        attributes(
                                key("title").value("Bộ lọc và phân trang đơn hàng"),
                                key("note").value("page bắt đầu từ 0")),
                        parameterWithName("status").description("Lọc theo trạng thái"),
                        parameterWithName("page").description("Số trang"),
                        parameterWithName("size").description("Số phần tử mỗi trang"))));
~~~

### Template query-parameters

Tạo file query-parameters.snippet:

~~~mustache
{{#title}}
.{{title}}
{{/title}}
{{#note}}
NOTE: {{note}}
{{/note}}
|===
|Name|Description|Default|Constraints|Example|Allowed values
{{#parameters}}
|{{name}}
|{{description}}
|{{default}}
|{{constraints}}
|{{example}}
|{{allowed-values}}
{{/parameters}}
|===
~~~

Query template có thể dùng chung một số cột với path parameters, nhưng default, allowed values và constraints thường hữu ích hơn với bộ lọc và phân trang.

## 8. Bổ sung metadata cho parameter descriptor

ParameterDescriptor cũng có thể nhận attributes. Một số key do nhóm quy ước:

| Key | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| format | Định dạng hoặc kiểu biểu diễn | UUID, ISO-8601 |
| example | Giá trị request minh họa | PAID |
| default | Giá trị mặc định của API | 20 |
| constraints | Giới hạn giá trị | 1 đến 100 |
| allowed-values | Tập giá trị chấp nhận | PENDING, PAID, CANCELLED |
| since | Phiên bản bắt đầu hỗ trợ | v2 |

Đây là metadata phục vụ template, không phải kiểm tra runtime tự động. Spring REST Docs kiểm tra parameter thực tế so với descriptor theo quy tắc snippet; nội dung default hoặc allowed-values phải được kiểm chứng từ hợp đồng API và test riêng nếu cần.

## 9. Required, optional và ignored trong bảng parameters

Template tùy chỉnh cần giữ thông tin trạng thái parameter mà descriptor cung cấp:

- optional() đánh dấu parameter có thể không xuất hiện trong request hợp lệ.
- ignored() bỏ parameter khỏi snippet và khỏi kiểm tra strict tương ứng.
- Chế độ relaxed cho path/query parameters cho phép request có parameter chưa mô tả mà không làm test thất bại.

Ví dụ query parameter tùy chọn:

~~~java
parameterWithName("sort")
        .optional()
        .description("Thứ tự sắp xếp kết quả")
~~~

Không nhầm optional() với giá trị mặc định. Parameter có thể tùy chọn nhưng server vẫn có default; hai ý nghĩa nên có metadata riêng nếu tài liệu cần thể hiện.

Nếu template bỏ mất placeholder liên quan trạng thái optional hoặc ignored, người đọc có thể hiểu sai hợp đồng. Bắt đầu từ template mặc định để giữ các biểu diễn trạng thái đó, rồi thêm cột mới.

## 10. Tùy chỉnh cho nhiều format

Template override được tra cứu theo template format ID. Với Asciidoctor:

~~~text
org/springframework/restdocs/templates/asciidoctor/
~~~

Với Markdown:

~~~text
org/springframework/restdocs/templates/markdown/
~~~

Nếu dự án hỗ trợ cả hai định dạng, cần template tương ứng cho từng snippet:

~~~text
templates/
├── asciidoctor/
│   ├── request-fields.snippet
│   ├── path-parameters.snippet
│   └── query-parameters.snippet
└── markdown/
    ├── request-fields.snippet
    ├── path-parameters.snippet
    └── query-parameters.snippet
~~~

Không sao chép template Asciidoctor sang Markdown mà không đổi cú pháp bảng và nội dung đầu ra. Phần mở rộng snippet phụ thuộc format đang cấu hình; cập nhật include hoặc bước nhúng tài liệu cho đúng file được sinh.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Request fields tùy chỉnh nhưng path parameters vẫn mặc định | Chỉ override request-fields.snippet | Tạo path-parameters.snippet riêng |
| Query parameters không có cột mới | Template query chưa đọc attributes | Bổ sung placeholder trong query-parameters.snippet |
| Metadata cấp snippet không xuất hiện | Chưa truyền map attributes vào snippet constructor | Dùng overload nhận attributes của snippet tương ứng |
| Metadata field/parameter không hiển thị | Chưa gắn attributes hoặc sai key | Đối chiếu descriptor và Mustache placeholder |
| Template không được áp dụng | Sai format ID hoặc tên file | Kiểm tra classpath và tên snippet |
| Parameter thực tế chưa được mô tả | Descriptor thiếu parameter trong chế độ strict | Bổ sung descriptor hoặc dùng relaxed có chủ ý |
| Parameter optional bị hiểu là required | Template bỏ mất thông tin trạng thái | Giữ placeholder trạng thái từ template mặc định |
| Path parameter không được nhận diện trong MockMvc | Dùng request builder không cung cấp URI template parameters ở framework cũ | Dùng RestDocumentationRequestBuilders theo hướng dẫn phiên bản |
| Include lỗi sau khi đổi Markdown | Phần mở rộng snippet thay đổi theo format | Cập nhật include và task tài liệu |

## 12. Bài thực hành

1. Override request-fields.snippet để thêm Constraints và Example.
2. Override response-fields.snippet với title và cột Unit cho giá trị tiền tệ.
3. Tạo path-parameters.snippet có Format và Example; truyền attributes ở cả snippet-level và parameter-level.
4. Tạo query-parameters.snippet có Default, Constraints và Allowed values.
5. Viết test cho query parameter optional và bảo đảm template thể hiện đúng trạng thái.
6. Chuyển template format sang Markdown, tạo bản template Markdown và xác nhận phần mở rộng include.
7. Chạy documentation tests rồi build Asciidoctor/Markdown; kiểm tra diff của các snippet.

**Tiêu chí hoàn thành:** xác định đúng template theo loại snippet; truyền attributes ở cấp snippet và descriptor; tùy chỉnh riêng fields, path parameters và query parameters; giữ thông tin optional/ignored; đồng bộ output với định dạng tài liệu.

## 13. Checklist trước khi commit

- [ ] Override đúng template cho request-fields, response-fields, path-parameters và query-parameters cần tùy chỉnh.
- [ ] Template đặt trong đúng thư mục theo format ID.
- [ ] Attributes cấp snippet được truyền qua overload phù hợp.
- [ ] Attributes cấp descriptor được gắn vào đúng field hoặc parameter.
- [ ] Placeholder Mustache khớp key attributes.
- [ ] Template giữ trạng thái optional/ignored và các thông tin chuẩn cần thiết.
- [ ] Parameter thực tế được mô tả hoặc xử lý bằng relaxed mode có chủ ý.
- [ ] Template Asciidoctor/Markdown có cú pháp và phần mở rộng phù hợp.
- [ ] Test sinh snippet trước khi biên soạn tài liệu trong CI.

**Ghi nhớ:** Fields và parameters có template riêng vì mỗi loại mô tả một phần khác nhau của hợp đồng API. Dùng snippet-level attributes cho ngữ cảnh chung, descriptor-level attributes cho từng field/parameter, rồi tùy chỉnh đúng request-fields, response-fields, path-parameters và query-parameters để tạo bảng nhất quán mà vẫn giữ khả năng kiểm chứng của Spring REST Docs.

## Tài liệu tham khảo

- Spring REST Docs - Customizing the Output: https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html
- Spring REST Docs - Path Parameters: https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html
- Spring REST Docs - Request and Response Payloads: https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html
- Spring REST Docs API - RequestDocumentation: https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html
