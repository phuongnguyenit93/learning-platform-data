# Kiểm tra operation name và thư mục snippet

## Mục tiêu học tập

Trong module **SPRING_REST_DOCS**, mỗi lần gọi `document(...)` gắn một HTTP exchange với một operation identifier. Spring REST Docs dùng identifier này để nhóm các snippet được sinh ra vào một thư mục riêng. Tài liệu AsciiDoc sau đó tham chiếu đúng thư mục và tên file snippet để ghép thành API reference.

Nếu operation name không ổn định, bị trùng hoặc không khớp với đường dẫn include, test có thể ghi đè snippet, Asciidoctor không tìm thấy file hoặc tài liệu lấy nhầm nội dung từ một operation khác. Vì vậy, kiểm tra operation name và cây thư mục snippet là một phần quan trọng của documentation testing.

Sau bài này, bạn có thể:

- Giải thích vai trò của operation identifier trong `document(...)`.
- Phân biệt operation name với tên test method, endpoint URL và snippet name.
- Đặt operation name ổn định, duy nhất và dễ đọc.
- Kiểm tra thư mục snippet được tạo đúng từ test output.
- Phát hiện operation ID trùng và nguy cơ ghi đè khi test chạy song song.
- Đồng bộ snippet output root với Asciidoctor và CI.
- Chẩn đoán lỗi sai operation path, thiếu snippet và snippet cũ.

## 1. Operation name là gì?

Khi dùng Spring REST Docs, test thường gọi:

```java
this.mockMvc.perform(get("/api/products/{id}", 501))
    .andExpect(status().isOk())
    .andDo(document("products-get"));
```

Chuỗi `products-get` là **operation identifier** (cũng thường được gọi là operation name). Nó định danh bộ snippet của HTTP exchange này.

Với output root mặc định thường dùng trong Gradle:

```text
build/generated-snippets/
└── products-get/
    ├── http-request.adoc
    └── http-response.adoc
```

Nếu test khai báo thêm descriptor, thư mục operation có thêm snippet tương ứng:

```java
.andDo(document("products-get",
    pathParameters(
        parameterWithName("id").description("Mã sản phẩm.")
    ),
    responseFields(
        fieldWithPath("id").description("Mã sản phẩm."),
        fieldWithPath("name").description("Tên sản phẩm.")
    )));
```

Khi đó thư mục có thể chứa:

```text
build/generated-snippets/
└── products-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
```

Chỉ các snippet mà test thực sự yêu cầu mới được tạo. `document("products-get")` không tự sinh tất cả các loại snippet.

## 2. Phân biệt operation name với các tên khác

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Test method name | `getProduct_returnsProduct()` | Tên phương thức kiểm thử trong Java |
| Endpoint URL | `GET /api/products/{id}` | Đường dẫn HTTP mà client gọi |
| Operation identifier | `products-get` | Nhóm snippet của exchange |
| Snippet name | `http-response.adoc` | File cụ thể được sinh trong operation directory |
| AsciiDoc include path | `{snippets}/products-get/http-response.adoc` | Đường dẫn tài liệu dùng để include file |

Không có yêu cầu operation name phải trùng test method hoặc endpoint. Nên đặt theo ngữ nghĩa của API operation để tài liệu nguồn có thể tham chiếu ổn định.

Ví dụ, test method có thể là `shouldReturnProductWhenIdExists`, endpoint là `/api/products/{id}`, còn operation ID là `products-get`. Ba tên phục vụ ba mục đích khác nhau.

## 3. Quy tắc đặt operation name

Operation name nên:

- Ổn định qua các lần chạy test.
- Duy nhất cho mỗi bộ request/response cần tài liệu hóa riêng.
- Dễ đọc và phản ánh resource/action hoặc tình huống.
- Không phụ thuộc dữ liệu động như ID ngẫu nhiên, timestamp hoặc username.
- Nhất quán giữa test và AsciiDoc include.

Một quy ước đơn giản:

```text
<resource>-<action>[-<scenario>]
```

Ví dụ:

| HTTP operation/tình huống | Operation name |
| --- | --- |
| GET /api/products | `products-list` |
| GET /api/products/{id} thành công | `products-get` |
| POST /api/products | `products-create` |
| PUT /api/products/{id} | `products-update` |
| DELETE /api/products/{id} | `products-delete` |
| GET /api/products/{id} không tồn tại | `products-get-not-found` |
| POST /api/products/{id}/images | `products-image-upload` |

Tên ngắn, chữ thường và dấu gạch ngang giúp include path dễ đọc. Có thể dùng dấu chấm hoặc cấu trúc thư mục lồng nhau nếu dự án có quy ước, nhưng phải kiểm tra output thực tế và tránh tạo path khó bảo trì.

Không nên dùng:

- `test1`, `sample`, `operationA`: không thể hiện ý nghĩa.
- `products-get-501`: gắn với ID dữ liệu cụ thể.
- `products-get-2026-11-17`: thay đổi theo thời gian.
- Tên test method quá dài: làm đường dẫn tài liệu khó đọc và dễ đổi khi refactor test.

## 4. Một endpoint, nhiều operation name

Cùng một endpoint có thể có nhiều kết quả cần tài liệu hóa:

| Endpoint | Kịch bản | Operation name |
| --- | --- | --- |
| GET /api/products/{id} | Tìm thấy | `products-get` |
| GET /api/products/{id} | Không tìm thấy | `products-get-not-found` |
| GET /api/products/{id} | Không đủ quyền | `products-get-forbidden` |

Ví dụ:

```java
@Test
void getProduct() throws Exception {
    this.mockMvc.perform(get("/api/products/{id}", 501))
        .andExpect(status().isOk())
        .andDo(document("products-get"));
}

@Test
void getProductNotFound() throws Exception {
    this.mockMvc.perform(get("/api/products/{id}", 9999))
        .andExpect(status().isNotFound())
        .andDo(document("products-get-not-found"));
}
```

Hai operation directory được tách riêng:

```text
generated-snippets/
├── products-get/
│   ├── http-request.adoc
│   └── http-response.adoc
└── products-get-not-found/
    ├── http-request.adoc
    └── http-response.adoc
```

Không dùng chung operation name nếu hai test tạo ra response khác nhau và cần giữ hai bộ snippet độc lập.

## 5. Trùng operation name có thể gây ra điều gì?

Mỗi operation directory chứa các file snippet theo tên cố định như `http-request.adoc`, `http-response.adoc`, `response-fields.adoc`. Nếu nhiều test dùng cùng operation ID nhưng tạo nội dung khác nhau, cùng một file có thể bị ghi lại.

Ví dụ:

```java
// Test thành công
.andDo(document("products-get",
    responseFields(
        fieldWithPath("id").description("Mã sản phẩm.")
    )));

// Test not found - dùng nhầm cùng operation ID
.andDo(document("products-get",
    responseFields(
        fieldWithPath("code").description("Mã lỗi.")
    )));
```

Hai response có schema khác nhau nhưng cùng ghi vào `products-get/response-fields.adoc`. Kết quả cuối có thể phụ thuộc test nào chạy sau. Khi chạy song song, xung đột ghi file còn khó dự đoán hơn.

Giải pháp là tách operation ID:

```java
.andDo(document("products-get", successDescriptors));

.andDo(document("products-get-not-found", errorDescriptors));
```

Nếu nhiều test cố ý bổ sung snippet cho cùng một operation, cần bảo đảm chúng không ghi đè file trùng tên và có chiến lược rõ ràng. Với các tình huống HTTP khác nhau, tách ID thường dễ hiểu và an toàn hơn.

## 6. Operation name không quyết định output root

Operation name chỉ xác định thư mục con. Thư mục gốc được cấu hình bởi REST Docs test context hoặc cấu hình build tích hợp.

Ví dụ:

```text
build/generated-snippets/       # Gradle thường dùng
target/generated-snippets/       # Maven thường dùng
```

Nếu output root được tùy chỉnh thành `build/api-snippets`, operation directory sẽ nằm bên dưới root đó:

```text
build/api-snippets/
└── products-get/
    ├── http-request.adoc
    └── http-response.adoc
```

Không nên nhầm operation ID với output directory. Đổi `document("products-get")` không tự chuyển toàn bộ output root sang một vị trí khác.

### 6.1. Đồng bộ test và Asciidoctor

Hai phía phải dùng cùng output root:

1. REST Docs test ghi snippet vào thư mục đã cấu hình.
2. Task Asciidoctor đọc chính thư mục đó.
3. Attribute `snippets` trỏ đến output root.
4. Include path thêm operation ID và snippet name.

Ví dụ include:

```asciidoc
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/http-response.adoc[]
```

Nếu test ghi vào `target/generated-snippets` nhưng Asciidoctor tìm trong `build/generated-snippets`, include sẽ thất bại dù operation name chính xác.

## 7. Kiểm tra operation directory sau khi test chạy

Sau khi chạy documentation test, kiểm tra cây thư mục output.

PowerShell:

```powershell
Get-ChildItem -Recurse build/generated-snippets
```

Linux/macOS:

```bash
find build/generated-snippets -type f
```

Với operation ID `products-get`, kiểm tra thư mục và file:

```powershell
Test-Path build/generated-snippets/products-get
Test-Path build/generated-snippets/products-get/http-request.adoc
Test-Path build/generated-snippets/products-get/http-response.adoc
```

Các lệnh trên là ví dụ cho Gradle output mặc định. Nếu dự án dùng Maven hoặc output root tùy chỉnh, thay bằng đường dẫn thực tế.

Khi kiểm tra, xác nhận:

- Operation directory có đúng tên từ `document(...)`.
- Chỉ các snippet được test yêu cầu mới được kỳ vọng tồn tại.
- File có nội dung của exchange vừa chạy.
- Không có file cũ từ operation đã đổi tên gây nhầm lẫn.
- Không có operation khác dùng chung ID ngoài chủ đích.

## 8. Include snippet theo operation name

Đường dẫn include có cấu trúc:

```text
{snippets}/<operation-name>/<snippet-name>.adoc
```

Ví dụ trang products.adoc:

```asciidoc
= Products API

== Liệt kê sản phẩm
include::{snippets}/products-list/http-request.adoc[]
include::{snippets}/products-list/http-response.adoc[]

== Xem chi tiết sản phẩm
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/http-response.adoc[]

== Không tìm thấy sản phẩm
include::{snippets}/products-get-not-found/http-response.adoc[]
```

Phần operation name trong include phải khớp tuyệt đối với tham số truyền vào `document(...)`. Sai một ký tự, dấu gạch ngang hoặc chữ hoa/thường có thể khiến Asciidoctor không tìm thấy file.

### 8.1. Dùng attribute operation để tránh lặp

Nếu một section include nhiều snippet của cùng operation:

```asciidoc
:operation: products-create

== Request
include::{snippets}/{operation}/http-request.adoc[]

== Response
include::{snippets}/{operation}/http-response.adoc[]

== Request fields
include::{snippets}/{operation}/request-fields.adoc[]
```

Attribute `operation` chỉ là biến AsciiDoc để giảm lặp. Nó không tạo thư mục và không ảnh hưởng đến REST Docs. Giá trị phải khớp operation ID của test.

## 9. Operation name với test parameterized

Parameterized test có thể chạy nhiều dữ liệu nhưng không nhất thiết tạo một operation directory cho mỗi giá trị.

Ví dụ không nên đưa dữ liệu runtime vào ID:

```java
document("products-get-" + productId)
```

Cách này có thể sinh ra rất nhiều thư mục và khiến include path không ổn định. Hãy chọn một operation ID cho một kịch bản tài liệu có ý nghĩa, dùng fixture cố định hoặc tách test nếu các response khác nhau cần tài liệu riêng.

Nếu các lần chạy parameterized chỉ xác minh cùng một schema và cùng một tài liệu, cần bảo đảm chúng không đồng thời ghi cùng snippet file. Có thể chỉ định một test case làm nguồn tạo snippet hoặc tổ chức ID riêng theo nhóm tình huống được tài liệu hóa.

## 10. Operation name trong multi-module và CI

### 10.1. Multi-module

Mỗi module có thể có output root riêng:

```text
project/
├── catalog-service/
│   └── build/generated-snippets/
│       ├── products-list/
│       └── products-get/
├── order-service/
│   └── build/generated-snippets/
│       ├── orders-list/
│       └── orders-get/
└── api-docs/
    └── src/docs/asciidoc/
```

Operation ID có thể trùng giữa hai module nếu chúng ở output root riêng, nhưng khi hợp nhất vào một root chung thì phải tránh trùng path. Có thể thêm prefix module:

- `catalog-products-get`
- `orders-orders-get`

Quan trọng là quy tắc đặt tên phải nhất quán và include path phải trỏ đúng nguồn.

### 10.2. CI chia test và Asciidoctor thành nhiều job

Nếu test và biên soạn tài liệu chạy ở hai job:

1. Job test chạy documentation tests và tạo generated-snippets.
2. Lưu toàn bộ output root dưới dạng artifact, giữ nguyên các operation directory.
3. Job tài liệu tải artifact vào đúng output root đã cấu hình.
4. Asciidoctor include theo operation ID và snippet name.
5. Nếu include lỗi, kiểm tra artifact có giữ cấu trúc thư mục và tên file không.

Không chỉ upload một số file snippet rời rạc nếu tài liệu cần nhiều operation. Giữ nguyên cây thư mục giúp include path không phải viết lại giữa local và CI.

## 11. Chẩn đoán lỗi operation name và thư mục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có operation directory | Test chưa chạy, không gọi document hoặc output root khác | Chạy đúng test task và kiểm tra output root |
| Directory có tên khác dự kiến | Operation ID trong document khác với tên include | Đối chiếu tham số document(...) và AsciiDoc |
| Asciidoctor báo không tìm thấy http-response.adoc | Test chưa tạo snippet đó hoặc include sai tên file | Kiểm tra descriptor và cây output |
| Snippet chứa response của test khác | Hai test dùng chung operation ID và ghi cùng file | Tách ID theo kịch bản |
| Kết quả không ổn định khi chạy song song | Nhiều test ghi cùng operation directory | Dùng ID riêng hoặc điều phối test ghi snippet |
| Include chạy local nhưng lỗi trên CI | Artifact thiếu thư mục con hoặc tải sai root | Lưu/tải nguyên cây generated-snippets |
| Include trỏ tới snippet cũ | Output cũ còn lại sau khi đổi test/operation | Clean output và chạy lại documentation tests |
| Maven có file nhưng Asciidoctor tìm trong build | Nhầm target với build output | Đồng bộ attribute snippets với output Maven |
| Parameterized test sinh quá nhiều folder | ID chứa giá trị runtime | Dùng ID ổn định theo kịch bản |
| Hai module ghi cùng operation path | Hợp nhất chung root nhưng ID trùng | Prefix module hoặc tách output root |

## 12. Quy trình kiểm tra trước khi biên soạn

1. Tìm tất cả lời gọi `document(...)` trong documentation tests của operation.
2. Xác nhận operation ID ổn định, duy nhất cho nội dung exchange đó.
3. Chạy đúng test task để sinh snippet.
4. Kiểm tra operation directory trong output root.
5. Kiểm tra các snippet file mà AsciiDoc sẽ include.
6. Đối chiếu operation ID trong include với test.
7. Chạy Asciidoctor để xác nhận include thành công.
8. Nếu CI chạy riêng job, xác minh artifact giữ nguyên operation directory.

Quy trình này giúp khoanh vùng lỗi: test không sinh snippet, test sinh sai thư mục, include sai tên hoặc artifact không được truyền đầy đủ.

## 13. Bài thực hành

1. Viết test GET /api/products/{id} và gọi `document("products-get")`.
2. Kiểm tra thư mục generated-snippets/products-get và các snippet được tạo.
3. Viết test not-found với `document("products-get-not-found")`.
4. Include hai operation vào products.adoc ở hai section khác nhau.
5. Tạo hai test có response khác nhau nhưng tạm dùng chung operation ID; quan sát nguy cơ ghi đè và sửa bằng ID riêng.
6. Đổi output root sang một thư mục tùy chỉnh; đồng bộ test context, Asciidoctor input và attribute snippets.
7. Thử chạy test song song để xác minh không có hai test ghi cùng file.
8. (Nâng cao) Lưu generated-snippets thành CI artifact rồi biên soạn tài liệu ở job khác.

**Câu hỏi tự đánh giá**

1. Operation identifier được truyền ở đâu trong Spring REST Docs?
2. Operation name khác test method name và endpoint URL như thế nào?
3. Vì sao hai test có response khác nhau không nên dùng chung operation ID?
4. Operation ID có quyết định output root không?
5. Cấu trúc include path gồm những thành phần nào?
6. Parameterized test nên xử lý operation ID ra sao để tránh sinh quá nhiều thư mục?
7. Khi gộp snippet nhiều module vào một root, cần kiểm soát điều gì?
8. Làm thế nào phân biệt lỗi test không sinh snippet với lỗi AsciiDoc include sai?

## Tài liệu tham khảo chính thức

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): cấu hình output directory và tạo snippet từ test.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): operation và snippet generation.
- [Spring REST Docs — Asciidoctor Integration](https://docs.spring.io/spring-restdocs/reference/getting-started/documentation-snippets.html): include snippet và cấu hình Asciidoctor.
- [Spring REST Docs API — MockMvcRestDocumentation](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html): tích hợp document với MockMvc.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): khai báo input/output task.
- [Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): vòng đời test và output build.

**Kết luận thực hành:** Operation name là khóa ổn định để nhóm snippet của một HTTP exchange. Đặt ID rõ nghĩa và riêng cho các tình huống có output khác nhau; kiểm tra operation directory sau test; include đúng `{snippets}/<operation-name>/<snippet-name>.adoc`; đồng bộ output root giữa test, Asciidoctor và CI. Khi các bước này nhất quán, tài liệu luôn tham chiếu đúng snippet được tạo từ test hiện tại.
