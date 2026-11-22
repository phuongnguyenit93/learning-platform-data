# Luồng từ test đến snippet, Asciidoctor hoặc Markdown

Spring REST Docs tổ chức quá trình tạo tài liệu API theo một luồng có thể tái tạo: **kiểm thử HTTP thực thi request, kiểm tra response, ghi nhận operation, sinh snippet, rồi biên soạn các snippet cùng phần giải thích thành tài liệu hoàn chỉnh**. Mỗi bước có đầu vào và kết quả riêng. Khi nối chúng đúng thứ tự, ví dụ HTTP và bảng mô tả có thể truy ngược về bài kiểm thử; khi một bước bị bỏ qua hoặc dùng output cũ, trang tài liệu có thể trông đầy đủ nhưng không phản ánh mã nguồn hiện tại.

Bài học thuộc chương **Mô hình tài liệu** của module `SPRING_REST_DOCS`. Module thực hành tạo tài liệu REST API có thể kiểm chứng bằng Spring REST Docs qua **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; sau đó biên soạn **Asciidoctor/Markdown** và kết nối vào build, CI. Bài này đi xuyên suốt toàn bộ chuỗi từ test đến trang tài liệu, chỉ ra vai trò của từng bước, cách cấu hình phụ thuộc và những lỗi thường gặp khi tích hợp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả đầu vào/đầu ra của từng bước: HTTP test, assertion, descriptor, snippet, trang nguồn và tài liệu đã render.
2. Viết một operation test sử dụng Spring REST Docs để tạo snippet từ request và response.
3. Cấu hình output directory và identifier để tài liệu nguồn tìm được đúng snippet.
4. Biên soạn tài liệu với Asciidoctor bằng include, hoặc tổ chức một pipeline tạo Markdown phù hợp.
5. Thiết lập quan hệ task để test chạy trước bước render và output cũ không che giấu lỗi.
6. Chẩn đoán lỗi từ request test đến file output và include trong trang tài liệu.
7. Xác định phần nào được kiểm chứng tự động và phần nào vẫn cần review nội dung.

## 2. Nhìn tổng thể luồng xử lý

Một quy trình Spring REST Docs có thể biểu diễn như sau:

```text
Source code + test + descriptor + tài liệu nguồn
                     │
                     ▼
             Biên dịch test
                     │
                     ▼
              Chạy HTTP test
                     │
          ┌──────────┴───────────┐
          ▼                      ▼
   Assertions              Request/response
 status, header, JSON        được ghi nhận
          │                      │
          └──────────┬───────────┘
                     ▼
             document(identifier)
                     │
                     ▼
             generated-snippets/
                     │
             ┌───────┴────────┐
             ▼                ▼
       Asciidoctor       Pipeline Markdown
       include adoc      chuyển đổi/chèn snippet
             │                │
             └───────┬────────┘
                     ▼
             HTML / PDF / site
                     │
                     ▼
             Kiểm tra và công bố
```

Có thể chia chuỗi này thành sáu bước:

| Bước | Đầu vào | Kết quả | Câu hỏi cần kiểm tra |
| --- | --- | --- | --- |
| 1. Chuẩn bị test | Fixture, cấu hình ứng dụng, request dự kiến | Môi trường test xác định | Test đang chạy qua những thành phần nào? |
| 2. Gửi request và nhận response | MockMvc, WebTestClient hoặc REST Assured | Tương tác HTTP thực tế trong test | Request và response có đúng tình huống? |
| 3. Assertion và descriptor | Kết quả HTTP và quy tắc hợp đồng | Kiểm tra hành vi và mô tả cấu trúc | Những điều gì được bảo vệ bởi assertion? |
| 4. Sinh snippet | Operation đã ghi nhận và descriptor | Thư mục snippet theo identifier | File nào được tạo, nằm ở đâu? |
| 5. Biên soạn tài liệu | Snippet, AsciiDoc/Markdown, phần viết tay | Trang HTML/PDF/site hoặc Markdown | Include có đúng và nội dung có đủ ngữ cảnh? |
| 6. Build và CI | Source, test, cấu hình task | Kết quả có thể tái tạo | Build sạch có chạy test trước render không? |

**Không phải mọi bước đều do Spring REST Docs tự thực hiện.** Thư viện tích hợp việc ghi nhận operation và sinh snippet. Người phát triển vẫn phải viết test, assertion, descriptor, tài liệu nguồn và cấu hình build phù hợp.

## 3. Bước 1 — Chuẩn bị HTTP test có thể lặp lại

Muốn có snippet đáng tin cậy, trước tiên phải có một lần gọi HTTP rõ ràng và lặp lại được. Test cần kiểm soát dữ liệu đầu vào, trạng thái ứng dụng, cấu hình và các phụ thuộc ảnh hưởng tới response.

Ví dụ API đọc sản phẩm:

- `GET /api/products/{productId}` trả thông tin khi sản phẩm tồn tại.
- Sản phẩm `7` là fixture đã chuẩn bị với tên `Sổ tay` và giá `45000`.
- Nếu mã không tồn tại, endpoint trả `404` theo hợp đồng ví dụ.

Một fixture có thể được thiết lập trong test hoặc thông qua repository test. Điều quan trọng là kết quả không phụ thuộc vào việc test khác đã chạy trước đó hay dữ liệu ngẫu nhiên trên môi trường.

### 3.1. Chọn phạm vi của test

Spring REST Docs hỗ trợ các cách tiếp cận khác nhau:

| Công cụ | Phạm vi thường gặp | Điểm cần quyết định |
| --- | --- | --- |
| MockMvc standalone | Controller và cấu hình MVC được dựng trong test | Có cần thêm filter, converter, controller advice hoặc security không? |
| MockMvc với application context | Spring MVC stack dựa trên context test | Context có đại diện đủ các cấu hình liên quan không? |
| WebTestClient | WebFlux hoặc MVC, bind in-memory hay kết nối server | Test đang bind trực tiếp ứng dụng hay gọi HTTP qua server? |
| REST Assured | Thường gọi tới server đang chạy; cũng có hỗ trợ mock MVC/WebTestClient qua module phù hợp | Test có bao phủ đúng tầng HTTP, fixture và lifecycle server không? |

Phạm vi test quyết định nội dung có thể khẳng định. MockMvc standalone có thể chứng minh controller được dựng đã trả một response trong cấu hình đó; nó không tự kiểm tra database, bảo mật production hoặc mạng. Khi cần chứng minh những thành phần này, hãy chọn test phù hợp và mô tả đúng phạm vi.

### 3.2. Dữ liệu test phải an toàn và ổn định

Dùng fixture giả, ID cố định khi phù hợp, thời gian có thể kiểm soát và dữ liệu độc lập giữa các test. Không dùng token thật, mật khẩu, cookie phiên hay dữ liệu cá nhân trong request/response sẽ xuất ra snippet. Nếu response chứa giá trị động, quyết định rõ có nên chuẩn hóa chúng bằng preprocessor trước khi công bố.

## 4. Bước 2 — Gửi request và nhận response bằng một trong các test client

Các test client khác nhau về cách gửi request, nhưng luồng khái quát là giống nhau:

```text
Test setup
   │
   ▼
HTTP request
   │
   ▼
Ứng dụng được kiểm thử
   │
   ▼
HTTP response
   │
   ├── status
   ├── headers
   └── body
```

### 4.1. MockMvc

MockMvc kiểm thử Spring MVC mà không cần khởi động HTTP server thật. Ví dụ request đọc sản phẩm:

```java
mockMvc.perform(
        get("/api/products/{productId}", 7L)
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(7));
```

Để Spring REST Docs trích xuất path parameter từ URI template, dùng request builder tương ứng của Spring REST Docs:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
```

Khi request là `GET /api/products/{productId}`, URI template giúp `pathParameters(...)` xác định biến `productId`. Nếu dùng builder không giữ template, phần tài liệu hóa path parameter có thể không hoạt động như mong muốn.

### 4.2. WebTestClient

WebTestClient có thể bind tới ứng dụng WebFlux/MVC trong test hoặc tới server đang chạy, tùy cách thiết lập. Spring REST Docs tích hợp qua cấu hình WebTestClient tương ứng, ví dụ:

```java
client
    .get()
    .uri("/api/products/{id}", 7L)
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("products-get-success"));
```

Đoạn này minh họa vị trí gọi snippet sau khi response được xác nhận; để sử dụng trong dự án cần cấu hình WebTestClient với filter/documentation configuration của Spring REST Docs và import extension/API tương ứng. Cú pháp chi tiết phụ thuộc phiên bản Spring REST Docs và cách bind test client. Cần kiểm tra test client đã được tích hợp bộ ghi nhận tài liệu, không chỉ gọi `consumeWith(document(...))` một cách độc lập.

### 4.3. REST Assured

Với REST Assured, test thường mô tả request/response theo dạng fluent:

```java
given()
    .accept("application/json")
.when()
    .get("/api/products/{id}", 7)
.then()
    .statusCode(200);
```

Để tạo snippet, cần dùng tích hợp Spring REST Docs phù hợp với REST Assured (ví dụ filter của REST Docs) và gắn filter vào request specification. Cách tích hợp cụ thể khác với MockMvc; không thể chỉ thay tên request builder rồi giữ nguyên cấu hình của MockMvc.

**Nguyên tắc:** test client gửi request, nhận response và được cấu hình để ghi nhận operation; assertion xác nhận kết quả; Spring REST Docs mới có dữ liệu cần thiết để sinh snippet.

## 5. Bước 3 — Kết hợp assertion và descriptor

Một test tài liệu hóa tốt có ít nhất hai trách nhiệm: kiểm tra hành vi quan trọng và mô tả các thành phần sẽ xuất hiện trong tài liệu.

Ví dụ phần assertion:

```java
.andExpect(status().isOk())
.andExpect(jsonPath("$.id").value(7))
.andExpect(jsonPath("$.name").value("Sổ tay"))
.andExpect(jsonPath("$.price").value(45000))
```

Phần descriptor:

```java
.andDo(document("products-get-success",
    pathParameters(
        parameterWithName("productId")
            .description("Mã sản phẩm cần tra cứu")
    ),
    responseFields(
        fieldWithPath("id")
            .type(JsonFieldType.NUMBER)
            .description("Mã sản phẩm"),
        fieldWithPath("name")
            .type(JsonFieldType.STRING)
            .description("Tên hiển thị"),
        fieldWithPath("price")
            .type(JsonFieldType.NUMBER)
            .description("Giá sản phẩm")
    )
));
```

Hai phần kiểm tra những điều khác nhau:

| Cơ chế | Kiểm tra | Không tự kiểm tra |
| --- | --- | --- |
| `status().isOk()` | HTTP status của lần chạy | Mọi status có thể có |
| `jsonPath("$.price").value(45000)` | Giá trị price của fixture | Công thức giá cho mọi sản phẩm |
| `responseFields(...)` | Cấu trúc field được mô tả và tính khớp với payload theo chế độ tài liệu hóa | Toàn bộ quy tắc nghiệp vụ của field |
| `pathParameters(...)` | Mô tả biến path được gửi | Ý nghĩa nghiệp vụ đầy đủ của mã sản phẩm |

Ở chế độ mô tả nghiêm ngặt, descriptor payload thường phát hiện field không được tài liệu hóa hoặc field bắt buộc bị thiếu. `optional()` dùng cho field thật sự có thể vắng mặt; `relaxedResponseFields(...)` cho phép chỉ mô tả một phần. Không sử dụng chúng chỉ để né một test đang báo lỗi.

### 5.1. Tạo operation riêng cho các tình huống khác nhau

Cùng route có thể trả `200` và `404`. Hãy tạo test và identifier riêng:

```java
document("products-get-success", ...);
document("products-get-not-found", ...);
```

Không dùng một identifier chung nếu nội dung request/response khác nhau. Nếu làm vậy, các test có thể ghi đè cùng file snippet và trang tài liệu không còn xác định được ví dụ thuộc tình huống nào.

## 6. Bước 4 — Sinh snippet vào output directory

Mỗi lời gọi `document("identifier", ...)` gắn snippet vào một thư mục có tên identifier bên dưới output directory đã cấu hình.

Ví dụ:

```text
build/generated-snippets/
├── products-get-success/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── curl-request.adoc
│   ├── httpie-request.adoc
│   ├── path-parameters.adoc
│   └── response-fields.adoc
└── products-get-not-found/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    └── path-parameters.adoc
```

Danh sách trên là ví dụ về những snippet thường được tạo; file cụ thể còn phụ thuộc cấu hình và descriptor được yêu cầu. Một GET không có body không cần có bảng request fields. Nếu test không khai báo response field descriptor, không nên giả định file `response-fields.adoc` đã được tạo.

### 6.1. Một snippet đại diện cho điều gì?

| Snippet | Nguồn | Mục đích |
| --- | --- | --- |
| `http-request.adoc` | Request đã ghi nhận | Hiển thị method, URI, header và body |
| `http-response.adoc` | Response đã ghi nhận | Hiển thị status, header và body |
| `curl-request.adoc` | Request đã ghi nhận | Cung cấp lệnh cURL mẫu |
| `path-parameters.adoc` | `pathParameters(...)` | Mô tả biến đường dẫn |
| `query-parameters.adoc` | `queryParameters(...)` | Mô tả query string |
| `request-headers.adoc` | `requestHeaders(...)` | Mô tả header đầu vào |
| `response-headers.adoc` | `responseHeaders(...)` | Mô tả header đầu ra |
| `request-fields.adoc` | `requestFields(...)` | Mô tả payload đầu vào |
| `response-fields.adoc` | `responseFields(...)` | Mô tả payload đầu ra |

Snippet là **mảnh tài liệu**, không phải trang API hoàn chỉnh. Nó không tự giải thích tại sao client cần gọi endpoint hoặc cách xử lý lỗi.

### 6.2. Làm đẹp và chuẩn hóa snippet

Spring REST Docs hỗ trợ preprocessors như `preprocessRequest(prettyPrint())` và `preprocessResponse(prettyPrint())` để làm ví dụ dễ đọc. Có thể chuẩn hóa hostname hoặc thay dữ liệu động khi cần. Tuy vậy:

- Assertion phải kiểm tra response thực tế theo mục tiêu test.
- Preprocessor chỉ thay đổi bản hiển thị được ghi ra snippet.
- Không được che status, field hoặc kiểu dữ liệu đang cần kiểm chứng.
- Phải kiểm tra output cuối cùng không có token, cookie, thông tin cá nhân hoặc địa chỉ nội bộ.

## 7. Bước 5A — Biên soạn Asciidoctor bằng include

Asciidoctor có directive `include::...[]` để chèn snippet vào tài liệu tại thời điểm biên soạn. Ví dụ file `products.adoc`:

```asciidoc
[[products-get]]
=== Tra cứu sản phẩm

Sử dụng endpoint này để đọc thông tin của một sản phẩm
theo mã định danh. Nếu mã không tồn tại, API trả HTTP 404.

==== Request

include::{snippets}/products-get-success/http-request.adoc[]

==== Path parameters

include::{snippets}/products-get-success/path-parameters.adoc[]

==== Response thành công

include::{snippets}/products-get-success/http-response.adoc[]

==== Response fields

include::{snippets}/products-get-success/response-fields.adoc[]

==== Không tìm thấy

include::{snippets}/products-get-not-found/http-response.adoc[]
```

Trong ví dụ:

- `{snippets}` là attribute trỏ tới output directory.
- `products-get-success` là identifier dùng trong test.
- `http-request.adoc` là tên snippet cần chèn.

Asciidoctor sẽ đọc các file này khi render trang. Nếu identifier hoặc file không tồn tại, include không thể được giải quyết; cấu hình build nên làm cho lỗi này có thể phát hiện trong CI.

### 7.1. Ghép trang tài liệu lớn

Một file điểm vào có thể tổ chức nhiều phần:

```asciidoc
= API Reference
:toc: left
:toclevels: 3

include::introduction.adoc[]

include::products.adoc[]

include::orders.adoc[]

include::errors.adoc[]
```

Trong đó `products.adoc` lại include snippet của các operation sản phẩm. Có hai cấp ghép nội dung:

1. Ghép các trang resource vào tài liệu tổng.
2. Ghép snippet test vào từng trang resource.

Cấu trúc hai cấp giúp phần diễn giải nghiệp vụ được quản lý như source tài liệu, còn ví dụ HTTP/bảng field được sinh từ test.

## 8. Bước 5B — Tổ chức pipeline tạo Markdown

Cú pháp `include::{snippets}/...[]` là directive của Asciidoctor, **không phải tính năng mặc định của Markdown**. Nếu chọn Markdown làm định dạng đích, cần có một cơ chế rõ ràng để đưa snippet vào nội dung Markdown.

Một số hướng thường dùng:

| Hướng | Cách hoạt động | Điểm cần kiểm soát |
| --- | --- | --- |
| AsciiDoc là nguồn chuẩn | Viết trang bằng AsciiDoc, dùng include snippet rồi render sang HTML/PDF | Đảm bảo output format và giao diện phù hợp nhu cầu |
| Sinh Markdown từ snippet | Sau test, bước build đọc output snippet và chèn vào template Markdown | Xác định mapping file, thứ tự và escaping code/table |
| Template snippet tùy chỉnh | Dùng template phù hợp với định dạng đầu ra của dự án | Template phải được cấu hình và kiểm tra cùng phiên bản REST Docs |
| Công cụ include Markdown | Dùng plugin/preprocessor được dự án chọn để chèn file | Cần kiểm tra tool có chạy trong CI và xử lý lỗi file thiếu |

Một pipeline Markdown có thể minh họa:

```text
HTTP test
    │
    ▼
generated-snippets/*.adoc hoặc dữ liệu snippet
    │
    ▼
Bước chuyển đổi/chèn được dự án cấu hình
    │
    ├── Chuyển bảng field sang Markdown table
    ├── Chuyển HTTP request/response thành fenced code block
    └── Giữ đường dẫn/identifier để truy vết nguồn
    │
    ▼
Markdown hoàn chỉnh
    │
    ▼
Markdown renderer/site generator
```

Không nên đơn giản đổi đuôi `.adoc` thành `.md` rồi giả định cú pháp tương thích. Bảng, block source, attribute và include có thể có quy tắc khác nhau. Hãy xác định pipeline cụ thể, kiểm tra đầu ra và dùng một ví dụ end-to-end trong CI.

## 9. Bước 6 — Nối các bước vào build và CI

Mục tiêu là đảm bảo **test tạo snippet chạy trước tài liệu**, và trang được render từ output của chính lần build đó.

### 9.1. Ví dụ Gradle

Ví dụ Groovy DSL sau minh họa dependency cơ bản khi dự án đã cấu hình task `test`, plugin Asciidoctor và dependency Spring REST Docs phù hợp:

```groovy
plugins {
    id 'org.asciidoctor.jvm.convert' version '4.0.2'
}

def snippetsDir = file("$buildDir/generated-snippets")

tasks.named("test") {
    outputs.dir snippetsDir
}

tasks.named("asciidoctor") {
    dependsOn tasks.named("test")
    inputs.dir snippetsDir
    attributes "snippets": snippetsDir
}
```

Đây là ví dụ khung; cấu hình hoàn chỉnh còn phụ thuộc plugin, cấu hình dependency và test engine của dự án. Nhiều dự án khai báo configuration riêng cho extension của Spring REST Docs Asciidoctor. Điều cần bảo đảm là:

- Test thực sự được chạy.
- Snippet được ghi vào `snippetsDir` đã khai báo.
- Task Asciidoctor phụ thuộc test.
- Attribute `snippets` trỏ đúng thư mục.
- Khi test thất bại hoặc snippet bị thiếu, build không tiếp tục xuất bản trang sai.

Nếu test suite tài liệu hóa chạy bằng task khác, ví dụ `integrationTest`, hãy phụ thuộc đúng task đó thay vì luôn mặc định `test`.

### 9.2. Với Maven

Maven thường đưa snippet vào `target/generated-snippets` theo cấu hình thông dụng. Cần nối plugin test và plugin Asciidoctor với lifecycle sao cho test chạy và sinh snippet trước khi biên soạn tài liệu.

Đừng sao chép nguyên cấu hình Gradle sang Maven. Hãy kiểm tra ba điểm: phase nào chạy test, output directory nào được dùng và plugin biên soạn nhận attribute `snippets` từ đâu. Build phải chạy được từ trạng thái sạch mà không cần snippet được tạo thủ công trước đó.

### 9.3. Mẫu pipeline CI

```text
Checkout source
      │
      ▼
Clean generated output
      │
      ▼
Compile + run documentation tests
      │
      ├── Assertion/descriptor failure ──► Fail
      │
      ▼
Verify generated snippets
      │
      ▼
Render Asciidoctor hoặc tạo Markdown
      │
      ├── Missing include/render failure ──► Fail
      │
      ▼
Review output và dữ liệu công khai
      │
      ▼
Publish artifact/documentation site
```

CI nên chạy từ checkout sạch hoặc làm sạch đúng output directory sinh tự động. Nếu test bị skip nhưng snippet từ lần chạy trước vẫn còn, bước render có thể thành công và tạo ấn tượng sai rằng tài liệu đã được tạo từ code hiện tại.

### 9.4. CI xác minh được điều gì?

CI có thể xác minh test đã chạy, assertion pass, descriptor phù hợp, snippet được tạo, include hợp lệ và trang render thành công. CI không tự xác nhận mọi quy tắc nghiệp vụ đã viết đúng. Những nội dung như ý nghĩa trạng thái, giới hạn tiền, quyền truy cập và chính sách retry vẫn cần người hiểu hợp đồng review và cần test phù hợp nếu có thể tự động kiểm chứng.

## 10. Theo dõi và chẩn đoán lỗi theo từng bước

Một chuỗi nhiều bước giúp khoanh vùng lỗi nhanh hơn. Đừng chỉ nhìn thông báo cuối cùng từ task render.

| Triệu chứng | Bước cần xem | Nguyên nhân phổ biến | Hành động |
| --- | --- | --- | --- |
| Không tạo được snippet directory | Test / cấu hình REST Docs | Test chưa chạy hoặc chưa cài filter/extension | Xác minh test discovery và cấu hình test client |
| Không có `http-response.adoc` | Ghi nhận operation | `document(...)` chưa được gọi hoặc request lỗi trước đó | Kiểm tra flow test và log |
| Không tạo bảng path parameter | Builder / descriptor | Request builder không giữ URI template | Dùng builder REST Docs phù hợp |
| `response-fields.adoc` lỗi | Descriptor validation | Field chưa mô tả, field bắt buộc thiếu hoặc payload khác | Đối chiếu hợp đồng và response |
| Include báo thiếu file | Tài liệu nguồn | Identifier/filename sai hoặc task test chưa tạo snippet | Đối chiếu `document(...)` với include |
| Trang render được nhưng nội dung cũ | Build output | Snippet cũ tồn dư | Clean output và chạy test lại |
| Markdown hiển thị nguyên directive include | Markdown pipeline | Renderer không hỗ trợ cú pháp Asciidoctor | Dùng bước chuyển đổi/chèn tương ứng |
| Task Asciidoctor chạy trước test | Build dependency | Thiếu `dependsOn` hoặc phụ thuộc sai task | Nối đúng task tạo snippet |
| Snippet chứa host/token nhạy cảm | Preprocessor/fixture | Request test dùng dữ liệu môi trường | Dùng fixture an toàn và chuẩn hóa output |
| Build pass nhưng quy tắc nghiệp vụ sai | Review/test coverage | Assertion chưa bao phủ quy tắc hoặc nội dung viết tay lỗi | Bổ sung test và review hợp đồng |

### 10.1. Ví dụ chẩn đoán thiếu snippet

Giả sử trang có:

```asciidoc
include::{snippets}/products-get-success/response-fields.adoc[]
```

Nhưng build báo không tìm thấy file. Kiểm tra theo thứ tự:

1. Test có gọi `document("products-get-success", ...)` không?
2. Có khai báo `responseFields(...)` cho operation đó không?
3. Test có pass và hoàn thành đoạn ghi tài liệu không?
4. Output directory thực tế là `build/generated-snippets` hay đường dẫn khác?
5. Attribute `snippets` có trỏ đúng output directory không?
6. Tên file có chính xác `response-fields.adoc` không?

Nếu test không khai báo descriptor `responseFields(...)`, file bảng field có thể không được tạo. Sửa include sang file khác chỉ để build qua sẽ che giấu việc nội dung tài liệu không còn đáp ứng yêu cầu.

## 11. Thay đổi hợp đồng và tái tạo tài liệu

Giả sử response sản phẩm thay đổi từ:

```json
{
  "id": 7,
  "name": "Sổ tay",
  "price": 45000
}
```

thành:

```json
{
  "id": 7,
  "name": "Sổ tay",
  "unitPrice": 45000,
  "currency": "VND"
}
```

Một chuỗi cập nhật đúng gồm:

1. Xác nhận schema mới là thay đổi hợp đồng được chấp nhận.
2. Sửa controller/DTO hoặc logic response.
3. Sửa assertion để kiểm tra các field và giá trị quan trọng.
4. Cập nhật descriptor `responseFields(...)` theo schema mới.
5. Chạy test để sinh lại snippet.
6. Cập nhật phần viết tay giải thích `unitPrice` và `currency`.
7. Render trang tài liệu và kiểm tra mọi include.
8. Đánh giá tương thích với client đang dùng schema cũ.

Nếu chỉ sửa descriptor mà không sửa assertion, test có thể xác nhận cấu trúc mà bỏ sót giá trị nghiệp vụ. Nếu chỉ sửa JSON trong source tài liệu, snippet sẽ vẫn được tạo từ response test; hai phần sẽ không còn nhất quán.

## 12. Bài thực hành end-to-end

Hãy xây dựng tài liệu cho hai operation của API sản phẩm:

- `GET /api/products/{id}`: thành công trả `200` cùng dữ liệu sản phẩm; không tìm thấy trả `404`.
- `POST /api/products`: tạo sản phẩm thành công trả `201`, header `Location` và JSON; request không hợp lệ trả `400` cùng schema lỗi.

### Nhiệm vụ

1. Chuẩn bị fixture có ID và dữ liệu cố định.
2. Viết HTTP test bằng MockMvc, WebTestClient hoặc REST Assured. Chọn công cụ đúng với stack và phạm vi cần kiểm chứng.
3. Trong mỗi test, kiểm tra status và các giá trị nghiệp vụ quan trọng.
4. Gọi `document(...)` với identifier riêng cho từng tình huống.
5. Khai báo descriptor cho path/query parameter, request/response header và request/response field khi thành phần đó thuộc hợp đồng.
6. Chạy test, kiểm tra output directory và xác nhận các snippet dự kiến tồn tại.
7. Tạo trang AsciiDoc với include cho mẫu request/response, các bảng field và các case lỗi.
8. Nếu chọn Markdown, xây dựng bước chuyển đổi hoặc chèn snippet rõ ràng và chạy thử renderer.
9. Nối task biên soạn với test tạo snippet; chạy toàn bộ quy trình từ output sạch.
10. Thử đổi identifier trong test mà chưa sửa trang, xác nhận include lỗi; sau đó cập nhật cả hai và chạy lại.

### Tiêu chí hoàn thành

- Test chạy từ dữ liệu có thể tái tạo.
- Assertion bảo vệ status và giá trị quan trọng.
- Mỗi tình huống có identifier phù hợp, không trùng output.
- Snippet được sinh từ đúng test và nằm trong output directory được cấu hình.
- Trang tài liệu include đúng file, có diễn giải nghiệp vụ và phân biệt response thành công/lỗi.
- Build sạch chạy test trước render và không phụ thuộc output cũ.
- Nội dung xuất bản không chứa dữ liệu nhạy cảm.

## 13. Ghi nhớ

- Luồng chính của Spring REST Docs là **HTTP test → assertion/descriptor → operation → snippet → Asciidoctor hoặc pipeline Markdown → build/CI**.
- Test client tạo request và nhận response; assertion xác nhận hành vi; descriptor mô tả cấu trúc; `document(identifier, ...)` liên kết operation với output snippet.
- Asciidoctor có thể include trực tiếp snippet; Markdown cần một cơ chế chuyển đổi/chèn tương thích với renderer đang dùng.
- Task biên soạn phải phụ thuộc test tạo snippet, output phải có thể tái tạo từ trạng thái sạch và identifier/include phải nhất quán.
- Build pass chứng minh các bước tự động trong phạm vi đã chạy; độ tin cậy của hợp đồng vẫn phụ thuộc chất lượng assertion, descriptor, phạm vi test và review nghiệp vụ.
