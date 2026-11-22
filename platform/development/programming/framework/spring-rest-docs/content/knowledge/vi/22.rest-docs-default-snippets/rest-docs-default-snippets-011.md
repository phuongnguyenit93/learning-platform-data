# Liên kết snippet theo operation directory

## Mục tiêu học tập

Trong module **SPRING_REST_DOCS**, mỗi bài kiểm thử HTTP có thể tạo nhiều snippet như http-request, http-response, path-parameters, request-fields, response-fields, request-headers hoặc response-cookies. Để Asciidoctor biên soạn đúng tài liệu, các snippet cần được đặt trong một thư mục có thể dự đoán và file AsciiDoc phải include đúng đường dẫn.

Spring REST Docs tổ chức snippet theo **operation identifier**. Khi test gọi document với một operation ID, REST Docs tạo thư mục tương ứng bên dưới thư mục generated-snippets. Mọi snippet được tạo trong operation đó nằm cùng thư mục. Tài liệu nguồn sau đó include từng snippet bằng đường dẫn gồm thư mục gốc, operation ID và tên snippet.

Sau bài này, bạn có thể:

- Giải thích quan hệ giữa operation ID, operation directory và snippet file.
- Đặt operation ID ổn định, duy nhất và dễ đọc.
- Include snippet trong AsciiDoc bằng attribute snippets.
- Tổ chức nhiều operation cho cùng endpoint hoặc nhiều biến thể response.
- Tránh tên operation trùng gây ghi đè hoặc làm tài liệu lấy nhầm snippet.
- Đồng bộ snippet output directory giữa test, Asciidoctor, Gradle/Maven và CI.
- Chẩn đoán lỗi include path, thiếu snippet và snippet cũ.

## 1. Operation directory là gì?

Khi test tài liệu hóa một HTTP exchange:

```java
mockMvc.perform(get("/api/products/{id}", 501))
    .andDo(document("products-get"));
```

Chuỗi products-get là **operation identifier**. REST Docs dùng identifier này để tạo thư mục con bên trong output directory của snippet.

Với Gradle, cấu trúc mặc định thường là:

```text
build/
└── generated-snippets/
    └── products-get/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── httpie-request.adoc
        └── request-parameters.adoc
```

Với Maven, thư mục output thường ở target/generated-snippets:

```text
target/
└── generated-snippets/
    └── products-get/
        ├── http-request.adoc
        ├── http-response.adoc
        └── request-parameters.adoc
```

Các file cụ thể phụ thuộc những snippet test đã yêu cầu tạo. REST Docs không nhất thiết sinh tất cả các loại snippet cho mọi operation.

**Ba thành phần cần phân biệt:**

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Snippet output root | build/generated-snippets | Thư mục gốc chứa các operation |
| Operation ID/directory | products-get | Nhóm snippet của một HTTP operation |
| Snippet file | http-response.adoc | Một phần tài liệu được tạo từ test |

Operation directory giúp giữ các snippet thuộc cùng một test operation cạnh nhau, tránh một thư mục phẳng chứa nhiều file trùng tên như http-request.adoc của mọi endpoint.

## 2. Operation ID quyết định đường dẫn include

Ví dụ test:

```java
this.mockMvc.perform(get("/api/products/{id}", 501)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("products-get",
        pathParameters(
            parameterWithName("id")
                .description("Mã sản phẩm.")
        ),
        responseFields(
            fieldWithPath("id")
                .description("Mã sản phẩm."),
            fieldWithPath("name")
                .description("Tên sản phẩm.")
        )));
```

Test trên dùng operation ID products-get và tạo những snippet tương ứng trong:

```text
build/generated-snippets/products-get/
```

File AsciiDoc include đúng thư mục:

```asciidoc
== GET /api/products/{id}

=== Path parameters
include::{snippets}/products-get/path-parameters.adoc[]

=== Response fields
include::{snippets}/products-get/response-fields.adoc[]

=== HTTP response
include::{snippets}/products-get/http-response.adoc[]
```

Attribute snippets đại diện cho **thư mục gốc** generated-snippets; phần products-get là operation directory; phần còn lại là tên snippet. Không include trực tiếp từ project root nếu task đã cung cấp attribute snippets.

## 3. Attribute snippets và vị trí thư mục gốc

Extension Asciidoctor của Spring REST Docs cung cấp attribute snippets để tham chiếu thư mục snippet. Trong cấu hình Gradle điển hình, task Asciidoctor sử dụng extension và đọc output directory mà test đã ghi.

Ví dụ cấu hình Gradle:

```groovy
ext {
    snippetsDir = file('build/generated-snippets')
}

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn test
}
```

Khi dùng Spring REST Docs Asciidoctor extension trên classpath của task, tài liệu có thể include:

```asciidoc
include::{snippets}/products-get/http-request.adoc[]
```

Ở đây có hai cấu hình liên quan nhưng khác nhiệm vụ:

- REST Docs test context quyết định nơi ghi snippet.
- Asciidoctor extension/attribute quyết định nơi tài liệu tìm snippet.

Chỉ khai báo một biến Gradle snippetsDir không tự thay đổi nơi REST Docs test ghi file. Cần cấu hình output directory cho test context và đồng bộ input của Asciidoctor.

### 3.1. Maven

Với Maven, plugin và cấu hình test thường dùng target/generated-snippets làm output. Asciidoctor Maven Plugin phải đọc cùng thư mục đó và extension REST Docs phải có mặt trên classpath biên soạn.

Ví dụ include trong tài liệu nguồn vẫn có dạng tương đối:

```asciidoc
include::{snippets}/products-get/http-request.adoc[]
```

Không cần ghi target/ vào mọi include nếu attribute snippets đã được thiết lập trỏ đến target/generated-snippets. Cách làm này giúp tài liệu nguồn ít phụ thuộc vào build tool hơn.

### 3.2. Đổi output directory

Nếu dự án cấu hình snippet sang một thư mục riêng, ví dụ:

```text
build/api-doc-snippets/
```

thì tất cả thành phần phải thống nhất:

1. REST Docs test ghi vào build/api-doc-snippets.
2. Task test khai báo đúng output directory.
3. Task Asciidoctor khai báo build/api-doc-snippets là input.
4. Attribute snippets trỏ tới build/api-doc-snippets.
5. CI lưu/truyền đúng thư mục nếu test và tài liệu chạy ở job khác nhau.

Nếu một bước vẫn trỏ tới build/generated-snippets cũ, test có thể chạy thành công nhưng Asciidoctor báo không tìm thấy file.

## 4. Đặt operation ID ổn định

Operation ID nên phản ánh tài nguyên và hành động, không phụ thuộc vào thứ tự test chạy hoặc tên class test:

| HTTP operation | Operation ID gợi ý |
| --- | --- |
| GET /api/products | products-list |
| GET /api/products/{id} | products-get |
| POST /api/products | products-create |
| PUT /api/products/{id} | products-update |
| DELETE /api/products/{id} | products-delete |
| POST /api/products/{id}/images | products-image-upload |

Một quy ước đặt ID hữu ích:

- Dùng chữ thường và dấu gạch ngang.
- Dùng tên tài nguyên nhất quán với tài liệu API.
- Thể hiện hành động hoặc biến thể response khi cần.
- Không dùng tên mơ hồ như test1, sample hoặc operationA.
- Không đưa dữ liệu động như ID thực tế, timestamp hoặc username vào operation ID.

ID nên ổn định qua các lần chạy để đường dẫn include trong tài liệu không phải thay đổi theo dữ liệu test.

## 5. Một endpoint có thể có nhiều operation

Cùng một URL có thể có nhiều tình huống cần tài liệu hóa:

| Endpoint | Tình huống | Operation ID |
| --- | --- | --- |
| GET /api/products/{id} | Tìm thấy sản phẩm | products-get |
| GET /api/products/{id} | Không tìm thấy | products-get-not-found |
| GET /api/products/{id} | Không có quyền truy cập | products-get-forbidden |

Ví dụ test cho trường hợp không tìm thấy:

```java
this.mockMvc.perform(get("/api/products/{id}", 9999))
    .andExpect(status().isNotFound())
    .andDo(document("products-get-not-found",
        responseFields(
            fieldWithPath("code")
                .description("Mã lỗi."),
            fieldWithPath("message")
                .description("Thông điệp lỗi.")
        )));
```

Các snippet được tách:

```text
generated-snippets/
├── products-get/
│   ├── http-response.adoc
│   └── response-fields.adoc
└── products-get-not-found/
    ├── http-response.adoc
    └── response-fields.adoc
```

Tách operation ID giúp mỗi tình huống có bộ snippet riêng. Tài liệu nguồn có thể trình bày hai trường hợp trong cùng một trang:

```asciidoc
== Lấy sản phẩm
include::{snippets}/products-get/http-response.adoc[]
include::{snippets}/products-get/response-fields.adoc[]

== Không tìm thấy sản phẩm
include::{snippets}/products-get-not-found/http-response.adoc[]
include::{snippets}/products-get-not-found/response-fields.adoc[]
```

Không nên dùng cùng operation ID cho hai test có response khác nhau nếu muốn giữ hai bộ snippet riêng.

## 6. Tránh operation ID trùng và ghi đè snippet

Một operation directory có thể được nhiều lần gọi document ghi vào. Nếu hai test cùng dùng products-get nhưng tạo payload hoặc descriptor khác nhau, những file cùng tên trong thư mục đó có thể bị ghi lại theo lần test chạy sau. Kết quả tài liệu phụ thuộc thứ tự thực thi.

Ví dụ không nên:

```java
// Test thành công
.andDo(document("products-get", responseFields(...)));

// Test lỗi nhưng dùng cùng operation ID
.andDo(document("products-get", responseFields(...)));
```

Nên đặt ID riêng:

```java
.andDo(document("products-get", responseFields(...)));

.andDo(document("products-get-not-found", responseFields(...)));
```

Quy tắc:

- Mỗi bộ HTTP exchange có nội dung tài liệu khác nhau nên có operation ID riêng.
- Nếu nhiều test cùng bổ sung snippet cho một operation, chỉ làm vậy khi có chủ đích và descriptor/body không xung đột.
- Không để test chạy song song ghi cùng file snippet.
- Với test parameterized, không dùng giá trị tham số thực tế để tạo ID động; chọn ID ổn định theo tình huống được tài liệu hóa.

## 7. Tổ chức tài liệu nguồn theo nhóm operation

Trong dự án có nhiều endpoint, có thể chia AsciiDoc thành các trang theo resource:

```text
src/docs/asciidoc/
├── index.adoc
├── products.adoc
├── orders.adoc
└── accounts.adoc
```

Ví dụ products.adoc:

```asciidoc
= Products API

== Liệt kê sản phẩm
include::{snippets}/products-list/http-request.adoc[]
include::{snippets}/products-list/http-response.adoc[]

== Xem chi tiết sản phẩm
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/http-response.adoc[]

== Tạo sản phẩm
include::{snippets}/products-create/http-request.adoc[]
include::{snippets}/products-create/http-response.adoc[]
```

index.adoc có thể include các trang:

```asciidoc
= API Reference

include::products.adoc[]
include::orders.adoc[]
include::accounts.adoc[]
```

Tài liệu nguồn được tổ chức theo nhóm người đọc dễ tìm; generated-snippets vẫn được tổ chức theo operation ID. Hai cấu trúc này phục vụ mục đích khác nhau:

| Cấu trúc | Tổ chức theo | Mục tiêu |
| --- | --- | --- |
| src/docs/asciidoc | Chương, resource, chủ đề | Điều hướng và diễn giải cho người đọc |
| generated-snippets | Operation ID | Gom output sinh ra từ mỗi test exchange |

Không cần ép cấu trúc tài liệu nguồn phải giống hệt cấu trúc generated-snippets.

## 8. Link snippet theo operation trong AsciiDoc

Một include path đầy đủ có cấu trúc:

```text
{snippets}/<operation-id>/<snippet-name>.adoc
```

Ví dụ:

| Nội dung cần đưa vào trang | Include |
| --- | --- |
| HTTP request | {snippets}/products-create/http-request.adoc |
| HTTP response | {snippets}/products-create/http-response.adoc |
| Request fields | {snippets}/products-create/request-fields.adoc |
| Response fields | {snippets}/products-create/response-fields.adoc |
| Path parameters | {snippets}/products-get/path-parameters.adoc |
| Request headers | {snippets}/products-create/request-headers.adoc |
| Response cookies | {snippets}/login/response-cookies.adoc |

Chỉ include snippet mà test thực sự tạo. Nếu operation không gọi requestFields thì không có request-fields.adoc. Nếu endpoint không trả cookie thì không có response-cookies.adoc.

### 8.1. Dùng attribute để giảm lặp

Có thể khai báo attribute cho operation khi trang chỉ tập trung vào một operation:

```asciidoc
:operation: products-create

== Request
include::{snippets}/{operation}/http-request.adoc[]

== Response
include::{snippets}/{operation}/http-response.adoc[]

== Request fields
include::{snippets}/{operation}/request-fields.adoc[]
```

Attribute operation chỉ là biến AsciiDoc giúp giảm lặp đường dẫn. Nó không tạo operation directory và không ảnh hưởng tới test; tên vẫn phải khớp document("products-create").

## 9. Khi dùng custom snippet template

REST Docs cho phép tùy chỉnh template của snippet. Dù nội dung template thay đổi, quy tắc tổ chức theo operation directory vẫn giữ nguyên: output của operation nằm trong thư mục tương ứng và file có tên snippet được cấu hình.

Nếu tạo custom snippet với tên, ví dụ operation-summary, đường dẫn include phải dùng đúng tên file được task tạo:

```asciidoc
include::{snippets}/products-create/operation-summary.adoc[]
```

Không đoán tên file từ tên template. Kiểm tra thư mục output sau khi test để biết chính xác tên snippet đã sinh và cấu hình output của custom snippet. Nếu tên template hoặc tên snippet được override, cập nhật include tương ứng.

## 10. Multi-module project và CI

### 10.1. Nhiều module Gradle

Với multi-module project, mỗi module có thể có thư mục build/generated-snippets riêng. Ví dụ:

```text
project/
├── catalog-service/
│   └── build/generated-snippets/
│       ├── products-list/
│       └── products-create/
├── order-service/
│   └── build/generated-snippets/
│       ├── orders-list/
│       └── orders-create/
└── api-docs/
    └── src/docs/asciidoc/
```

Nếu module api-docs biên soạn tài liệu từ snippet của module khác, cần đưa các thư mục output đó vào workspace của task và thiết lập attribute/base path cho từng nguồn. Ví dụ:

```asciidoc
:catalog-snippets: ../catalog-service/build/generated-snippets
:order-snippets: ../order-service/build/generated-snippets

include::{catalog-snippets}/products-list/http-response.adoc[]
include::{order-snippets}/orders-list/http-response.adoc[]
```

Đường dẫn tương đối cần được xác minh theo base directory thực tế của Asciidoctor task. Trong cấu hình phức tạp, truyền attribute bằng đường dẫn tuyệt đối đã được build script giải quyết thay vì tự đoán tương đối.

### 10.2. CI chia test và documentation thành hai job

Nếu test và Asciidoctor chạy ở hai job:

1. Job test chạy HTTP documentation tests.
2. Job test lưu toàn bộ generated-snippets như artifact.
3. Job documentation tải artifact vào đúng snippet output root.
4. Asciidoctor đọc attribute snippets trỏ đến vị trí đã tải.
5. Job documentation kiểm tra các operation directory và file include cần thiết có tồn tại.

Không chỉ truyền một vài file rời rạc nếu tài liệu dùng nhiều operation; truyền toàn bộ thư mục generated-snippets để giữ nguyên cấu trúc.

### 10.3. Tránh artifact chồng lấn

Nếu nhiều job tạo snippet cho cùng operation ID và cùng lưu chung một thư mục, file có thể ghi đè nhau. Nên tổ chức mỗi module/job vào output root riêng hoặc bảo đảm operation ID không trùng và bước hợp nhất artifact có quy tắc rõ.

## 11. Kiểm tra operation directory

Sau khi chạy test:

PowerShell:

```powershell
Get-ChildItem -Recurse build/generated-snippets
```

Linux/macOS:

```bash
find build/generated-snippets -type f
```

Với operation products-create, kiểm tra:

- Thư mục products-create tồn tại.
- Các snippet cần include đã được tạo.
- Tên file snippet đúng chính tả và đúng extension.
- Timestamp/file content thuộc lần test vừa chạy.
- Không có test khác ghi đè cùng thư mục.

Có thể kiểm tra nhanh đường dẫn cụ thể:

```powershell
Test-Path build/generated-snippets/products-create/http-request.adoc
Test-Path build/generated-snippets/products-create/response-fields.adoc
```

Lệnh kiểm tra phải phù hợp với snippet thực sự được test tạo. Ví dụ operation không có response body sẽ không có response-fields.adoc.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Asciidoctor báo include file không tồn tại | Operation ID hoặc snippet name sai | Đối chiếu document(...) với cây thư mục output |
| Thư mục operation không xuất hiện | Test chưa chạy, test không gọi document hoặc output root khác | Chạy test đúng task và kiểm tra output directory |
| Snippet nằm trong target nhưng include tìm ở build | Maven/Gradle path bị trộn | Đồng bộ attribute snippets với test output |
| Include trỏ đúng operation nhưng sai file | Test không tạo snippet loại đó | Kiểm tra descriptor/action thực tế trong test |
| Một operation có response không mong muốn | Nhiều test dùng chung ID và ghi đè | Tách operation ID cho từng tình huống |
| Tài liệu local chạy nhưng CI lỗi | Artifact không giữ cây thư mục hoặc tải sai vị trí | Upload/download nguyên thư mục và sửa attribute |
| Snippet cũ vẫn được include | Output cũ còn sau khi test thay đổi | Chạy clean và xác minh output của lần build mới |
| Multi-module include sai đường dẫn | Base directory của Asciidoctor khác dự kiến | In/kiểm tra đường dẫn đã resolve và đặt attribute rõ |
| Custom snippet không tìm thấy | Tên file output khác tên include | Kiểm tra template/snippet configuration và output thật |
| Test song song có nội dung snippet không ổn định | Hai test ghi cùng operation directory | Dùng ID riêng hoặc điều phối ghi output |

## 13. Bài thực hành

1. Tạo test GET /api/products/{id} với operation ID products-get.
2. Xác minh thư mục generated-snippets/products-get được tạo.
3. Tạo products.adoc và include http-request.adoc, http-response.adoc của operation đó.
4. Tạo test products-get-not-found và sử dụng ID riêng.
5. Include response-fields của cả hai trường hợp vào hai section khác nhau.
6. Đổi output root sang một thư mục riêng; đồng bộ test context, task output/input và attribute snippets.
7. Chạy clean test asciidoctor, kiểm tra cây thư mục và tài liệu HTML.
8. (Nâng cao) Chuyển snippet sang job CI artifact rồi chạy Asciidoctor ở job riêng.

**Câu hỏi tự đánh giá**

1. Operation ID được dùng để xác định phần nào trong cây generated-snippets?
2. Attribute snippets đại diện cho thư mục nào?
3. Vì sao file AsciiDoc cần cả operation ID và snippet name trong include path?
4. Khi cùng endpoint có response thành công và response lỗi, có nên dùng chung ID không?
5. Vì sao test dùng cùng operation ID có thể ghi đè snippet?
6. Thư mục source AsciiDoc và generated-snippets khác nhau ở mục tiêu nào?
7. Multi-module CI cần truyền artifact theo cách nào để giữ nguyên include path?
8. Làm thế nào xác định một snippet không tồn tại do sai include hay do test chưa tạo nó?

## Tài liệu tham khảo chính thức

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): cấu hình output directory, chạy test và dùng Asciidoctor để include snippet.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): operation, snippet và quy trình tài liệu hóa.
- [Spring REST Docs — Asciidoctor](https://docs.spring.io/spring-restdocs/reference/getting-started/documentation-snippets.html): tích hợp snippet với Asciidoctor và attribute.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): khai báo input/output và quan hệ task.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): tổ chức task và dependency giữa các module.
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): vòng đời test và build output.

**Kết luận thực hành:** Dùng operation ID ổn định để nhóm tất cả snippet của một HTTP exchange vào cùng thư mục. Trong AsciiDoc, include theo cấu trúc thư mục gốc snippets, operation ID và tên snippet. Giữ ID duy nhất cho các tình huống có output khác nhau, đồng bộ output root giữa test và Asciidoctor, và truyền nguyên cấu trúc thư mục qua CI để đường dẫn include luôn trỏ đúng file được test tạo ra.
