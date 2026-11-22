# Snippet `http-request` và thông tin phương thức HTTP

## 1. Mục tiêu và bối cảnh

Trong Spring REST Docs, một **HTTP operation** là lần trao đổi HTTP được ghi nhận khi bài kiểm thử gửi request đến API và nhận response. Từ operation đó, Spring REST Docs tạo các **snippet**: những mảnh tài liệu có thể đưa vào trang hướng dẫn API bằng Asciidoctor hoặc một quy trình Markdown được cấu hình riêng.

Bài học này tập trung vào snippet `http-request.adoc`: nó trình bày request thực tế mà bài kiểm thử đã thực hiện, đặc biệt là **phương thức HTTP** (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`...), đường dẫn, query string, header và body. Đây là một phần cốt lõi của `SPRING_REST_DOCS`: tạo tài liệu REST API có thể kiểm chứng từ bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured, rồi đưa snippet vào tài liệu và quy trình build/CI.

Sau bài học, bạn có thể:

- Đọc dòng đầu của một HTTP request và giải thích ý nghĩa phương thức HTTP.
- Sinh `http-request.adoc` bằng bài kiểm thử MockMvc có assertion.
- Phân biệt `http-request` với snippet mô tả từng trường, header hoặc tham số.
- Đưa snippet vào tài liệu Asciidoctor và phát hiện tài liệu không còn khớp với API qua lần chạy kiểm thử.

## 2. `http-request` thể hiện điều gì?

Xét request biểu diễn ở dạng HTTP/1.1:

~~~http
POST /api/users HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: req-001

{"name":"Lan","email":"lan@example.com"}
~~~

Đây là ví dụ minh họa; thứ tự header, `Host`, `Content-Length`, charset và cách xuống dòng có thể thay đổi theo client, cấu hình và preprocessor.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| HTTP method | `POST` | Hành động mà client yêu cầu thực hiện trên tài nguyên. |
| Request target | `/api/users` | Đường dẫn và, nếu có, query string đến tài nguyên. |
| Phiên bản HTTP | `HTTP/1.1` | Cách snippet biểu diễn HTTP request; không phải một trường nghiệp vụ. |
| Request header | `Content-Type: application/json` | Định dạng body được gửi đi. |
| Request header | `Accept: application/json` | Định dạng response client mong muốn. |
| Request body | JSON chứa `name`, `email` | Dữ liệu gửi tới endpoint. |

**Điểm cần nhớ:** phương thức HTTP trong snippet được lấy từ **request mà bài kiểm thử gửi**, chẳng hạn `post("/api/users")` hoặc `get("/api/users")`. Spring REST Docs không tự suy ra method từ tên mục tài liệu, tên hàm kiểm thử hoặc `@PostMapping`. Nếu dùng nhầm method, kiểm thử thường nhận status không mong đợi (chẳng hạn `405 Method Not Allowed`) và assertion sẽ báo lỗi.

Snippet `http-request.adoc` giúp người đọc nhìn thấy **request hoàn chỉnh**. Nó không tự giải thích ý nghĩa nghiệp vụ của từng trường, enum hoặc quy tắc xác thực; các nội dung đó nên được viết bằng diễn giải và các snippet chuyên biệt.

> **Lưu ý về giao thức:** dòng `METHOD /path HTTP/1.1` là biểu diễn văn bản thuận tiện để đọc tài liệu. HTTP/2 và HTTP/3 có cách truyền method/đường dẫn khác trên wire; đừng coi định dạng snippet là bằng chứng rằng production server chỉ hỗ trợ HTTP/1.1.

## 3. Hiểu đúng phương thức HTTP

Cùng một đường dẫn có thể hỗ trợ nhiều operation khác nhau; **method + đường dẫn** mới xác định loại request mà API phải xử lý.

| Method | Ý nghĩa thường gặp trong REST API | Body request | Đặc tính HTTP cần lưu ý |
| --- | --- | --- | --- |
| `GET` | Đọc một hoặc nhiều tài nguyên | Thường không dùng | Safe, idempotent |
| `HEAD` | Lấy metadata/headers tương ứng với tài nguyên, không lấy response body | Thường không dùng | Safe, idempotent |
| `POST` | Tạo tài nguyên hoặc thực hiện hành động | Thường có với thao tác tạo | Không mặc định idempotent |
| `PUT` | Tạo/thay thế trạng thái tài nguyên tại URI xác định | Thường có | Idempotent theo ngữ nghĩa HTTP |
| `PATCH` | Áp dụng thay đổi một phần | Thường có | Không được bảo đảm idempotent; tùy thiết kế |
| `DELETE` | Yêu cầu xóa tài nguyên | Thường không dùng | Idempotent theo ngữ nghĩa HTTP |
| `OPTIONS` | Hỏi khả năng giao tiếp mà endpoint hỗ trợ | Thường không dùng | Safe, idempotent |

*Safe* nghĩa là method được định nghĩa với ngữ nghĩa chỉ đọc từ góc nhìn client; *idempotent* nghĩa là gửi lại một request giống nhau nhiều lần có cùng hiệu ứng dự kiến lên trạng thái server như gửi một lần. Idempotent **không** có nghĩa response nào cũng có cùng status: ví dụ lần `DELETE` đầu có thể trả `204`, lần sau trả `404` tùy hợp đồng API.

Hãy tách rõ hai thông tin khi viết tài liệu:

1. **Method thực tế**: xuất hiện ngay trên dòng đầu `http-request` và phải được bài kiểm thử thực hiện.
2. **Quy tắc nghiệp vụ**: ví dụ “`POST /api/users` tạo người dùng và trả `201 Created` kèm `Location`”, cần viết thành lời và xác nhận bằng assertion phù hợp.

## 4. Tạo snippet bằng MockMvc

### 4.1. Chuẩn bị kiểm thử

Ví dụ dưới đây theo kiểu cấu hình quen thuộc với **Spring Boot 3.x, JUnit 5, Java 17+**. Dự án cần Spring MVC, Spring Boot Test và dependency test `spring-restdocs-mockmvc`. Nếu sử dụng BOM/dependency management của Spring Boot, để BOM quản lý phiên bản thư viện tương thích.

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Giả sử ứng dụng đã có endpoint `POST /api/users` nhận JSON và trả `201 Created` khi tạo thành công. Annotation `@AutoConfigureRestDocs` tích hợp REST Docs với MockMvc được Spring Boot tự cấu hình và xác định nơi ghi snippet.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class UserApiDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentCreateUser() throws Exception {
        mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", "req-001")
                .content("""
                    {"name":"Lan","email":"lan@example.com"}
                    """))
            .andExpect(status().isCreated())
            .andDo(document("users-create"));
    }
}
~~~

Luồng thực hiện:

~~~mermaid
flowchart LR
    A["MockMvc: POST /api/users"] --> B["Ứng dụng xử lý request"]
    B --> C["Kiểm tra status 201"]
    C --> D["document('users-create')"]
    D --> E["generated-snippets/users-create/http-request.adoc"]
~~~

- `post("/api/users")` quyết định HTTP method và request target được ghi nhận.
- `contentType(...)`, `accept(...)`, `header(...)` và `content(...)` cung cấp dữ liệu request thực tế.
- `andExpect(status().isCreated())` kiểm chứng hành vi trước khi tài liệu được sinh trong chuỗi lệnh này.
- `document("users-create")` chỉ định **identifier** để nhóm các snippet của operation. Identifier nên ổn định và có nghĩa nghiệp vụ.

Sau khi chạy test thành công, vị trí khai báo trong ví dụ có thể chứa:

~~~text
build/generated-snippets/
└── users-create/
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    └── response-body.adoc
~~~

Đây là **sáu snippet mặc định** với cấu hình Spring REST Docs thông thường. Nếu đổi danh sách snippet mặc định, định dạng template hoặc output directory, tập tin thực tế có thể khác.

### 4.2. Đọc kết quả `http-request.adoc`

Với test phía trên, nội dung HTTP request **có thể** có dạng:

~~~http
POST /api/users HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: req-001
Host: localhost:8080

{"name":"Lan","email":"lan@example.com"}
~~~

Phương thức `POST` là thông tin quan trọng nhất của ví dụ: nó mô tả operation tạo người dùng. Header `Host` và các giá trị phụ thuộc môi trường chỉ mang tính minh họa. Khi cần biết chính xác cấu hình hiện tại, hãy **mở snippet vừa được test sinh ra**.

So sánh nhanh các snippet liên quan:

| Snippet | Trả lời câu hỏi nào? |
| --- | --- |
| `http-request.adoc` | Client đã gửi request HTTP đầy đủ như thế nào? |
| `http-response.adoc` | Server đã trả status, headers và response body nào? |
| `curl-request.adoc` | Có thể gọi lại operation bằng lệnh `curl` nào? |
| `httpie-request.adoc` | Có thể gọi lại operation bằng lệnh HTTPie nào? |
| `request-body.adoc` | Body request là gì, tách khỏi phần method và headers? |
| `response-body.adoc` | Body response là gì? |

## 5. Thay đổi HTTP method và ghi nhận query parameters

Giả sử API còn có `GET /api/users?page=0&size=10` trả danh sách. Ta viết một test riêng và dùng identifier khác:

~~~java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void documentListUsers() throws Exception {
    mockMvc.perform(get("/api/users")
            .queryParam("page", "0")
            .queryParam("size", "10")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(document("users-list",
            queryParameters(
                parameterWithName("page").description("Chỉ số trang, bắt đầu từ 0"),
                parameterWithName("size").description("Số phần tử trong mỗi trang")
            )));
}
~~~

Đoạn mã này đặt bên trong cùng lớp kiểm thử đã cấu hình ở mục trước; các import chỉ minh họa phần cần bổ sung.

Snippet `users-list/http-request.adoc` sẽ thể hiện request line tương ứng, ví dụ:

~~~http
GET /api/users?page=0&size=10 HTTP/1.1
Accept: application/json
Host: localhost:8080
~~~

Khi chuyển từ `POST` sang `GET`, method và request target thay đổi trực tiếp trong `http-request`. Đồng thời, lời gọi `queryParameters(...)` tạo thêm snippet `query-parameters.adoc` mô tả ý nghĩa và ràng buộc các tham số. Nên dùng `queryParam(...)` trong MockMvc khi muốn query string xuất hiện rõ ràng trên URI, thay vì giả định mọi tham số của `param(...)` đều được biểu diễn trên request line.

Với path variables, cần phân biệt:

- `GET /api/users/42`: request target thực tế chứa giá trị `42`.
- `GET /api/users/{id}`: mẫu endpoint trong tài liệu, dùng giải thích ý nghĩa `id`.

Khi tạo `path-parameters.adoc` bằng MockMvc, sử dụng các request builder hỗ trợ URI template của Spring REST Docs (ví dụ `RestDocumentationRequestBuilders.get("/api/users/{id}", 42)`) và `pathParameters(...)` để liên kết đúng tên biến.

## 6. Bổ sung mô tả, nhưng giữ `http-request` làm nguồn minh họa

Chỉ có HTTP request thô chưa đủ để người dùng API biết field nào bắt buộc, dữ liệu hợp lệ ra sao hoặc header được dùng vào việc gì. Có thể thêm các snippet chuyên biệt ngay tại lời gọi `document(...)`.

Ví dụ mở rộng test tạo người dùng bằng đoạn dưới đây, với các static import:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

// Thay .andDo(document("users-create")) trong test tạo người dùng bằng:
.andDo(document("users-create",
    requestHeaders(
        headerWithName("X-Request-Id")
            .description("Mã theo dõi request từ client")
    ),
    requestFields(
        fieldWithPath("name").description("Tên hiển thị"),
        fieldWithPath("email").description("Địa chỉ email hợp lệ")
    )
));
~~~

Khi đó Spring REST Docs giữ các snippet mặc định, đồng thời bổ sung `request-headers.adoc` và `request-fields.adoc`. Các descriptor cũng đóng vai trò **kiểm chứng hợp đồng**: nếu payload có trường chưa được mô tả hoặc trường được khai báo không tồn tại theo quy tắc kiểm tra tương ứng, bước sinh snippet có thể khiến bài test thất bại. Tính chất này giúp tài liệu bám sát request được kiểm thử.

Cần phân biệt rõ phạm vi:

- `http-request`: minh họa **một request cụ thể**, gồm method, URI, headers và body.
- `requestHeaders`: bảng giải thích các request header có liên quan.
- `requestFields`: bảng field của JSON/XML request body.
- `queryParameters` và `pathParameters`: bảng tham số trên URI.
- `responseFields`: bảng field trong response body, độc lập với method request.

Những snippet trên chỉ ghi nhận hành vi **được test thực hiện**. Ví dụ duy nhất cho `POST` không thay thế việc viết test và tài liệu cho `GET`, `PUT` hoặc `DELETE` nếu API hỗ trợ những operation đó.

## 7. Dùng cùng nguyên tắc với WebTestClient và REST Assured

Phương thức HTTP vẫn đến từ request đang được test, bất kể dùng client nào:

| Công cụ test | Cách chọn HTTP method | Nơi gắn thao tác sinh tài liệu |
| --- | --- | --- |
| **MockMvc** | `perform(post(...))`, `perform(get(...))` | `.andDo(document("identifier"))` |
| **WebTestClient** | `webTestClient.get().uri(...)`, `post()`... | `.expectBody().consumeWith(document("identifier"))` sau khi exchange/assertion |
| **REST Assured** | `given()...when().post(...)`, `get(...)`... | Filter REST Docs `document("identifier")` được cấu hình cho request specification |

Ví dụ ngắn với một **WebTestClient đã được cấu hình Spring REST Docs**:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
    .uri("/api/users?page=0&size=10")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("users-list-webtestclient"));
~~~

Với REST Assured, sử dụng module `spring-restdocs-restassured` và cấu hình filter REST Docs trên request specification trước khi gửi request. Cả hai công cụ vẫn sinh `http-request` từ operation được ghi nhận. Phần thiết lập extension/filter, output directory và request specification phụ thuộc framework test và phiên bản Spring REST Docs được dự án chọn.

## 8. Kiểm soát dữ liệu xuất hiện trong request mẫu

Request tạo bởi test đôi khi chứa host nội bộ, token, cookie, ID ngẫu nhiên hoặc body khó đọc. Những yếu tố này ảnh hưởng tài liệu ngay cả khi API xử lý đúng.

**Tiền xử lý (preprocessing)** giúp chỉnh cách dữ liệu được trình bày trong snippet, ví dụ format JSON hoặc ẩn header nhạy cảm. Nó không thay đổi request mà ứng dụng đã xử lý.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

// Giữ nguyên request test; chỉ làm sạch request khi tạo tài liệu:
.andDo(document("users-create",
    preprocessRequest(
        removeHeaders("Authorization"),
        prettyPrint()
    )
));
~~~

Đoạn này là **phương án thay thế** cho lời gọi `.andDo(...)`, không được ghép thêm một lời gọi thứ hai cùng identifier. Nếu tài liệu cần mô tả header `Authorization` thì nên mô tả yêu cầu xác thực riêng và dùng cách thay/mask giá trị an toàn, bởi loại bỏ header khỏi request được ghi nhận có thể xung đột với descriptor `requestHeaders(...)` bắt buộc.

Với MockMvc, muốn snippet có host, scheme và port công khai, cấu hình URI trong REST Docs (chẳng hạn các thuộc tính `uriHost`, `uriScheme`, `uriPort` của `@AutoConfigureRestDocs` ở phiên bản Spring Boot tương ứng). Với client chạy trên server thật, REST Docs cũng hỗ trợ preprocessor chỉnh URI cho tài liệu. Hãy dùng hostname giả lập như `api.example.com`; không đưa access token hay cookie thật vào source/test fixture.

## 9. Đưa snippet vào tài liệu và CI

Spring REST Docs mặc định sinh snippet **Asciidoctor** (`*.adoc`). Trong một tệp Asciidoctor, có thể include nội dung đã được test sinh:

~~~asciidoc
= Users API

== Tạo người dùng

Gửi POST /api/users với tên và email hợp lệ.

=== HTTP request
include::{snippets}/users-create/http-request.adoc[]

=== HTTP response
include::{snippets}/users-create/http-response.adoc[]

== Danh sách người dùng

=== HTTP request
include::{snippets}/users-list/http-request.adoc[]

=== Query parameters
include::{snippets}/users-list/query-parameters.adoc[]
~~~

Thuộc tính Asciidoctor `snippets` phải được build cấu hình trỏ đến thư mục sinh snippet (trong ví dụ là `build/generated-snippets`). Không gán một đường dẫn tương đối cố định cho mọi dự án: vị trí thực tế phụ thuộc nơi tệp `.adoc` nằm và cách build plugin gọi Asciidoctor.

Luồng build/CI thông dụng:

~~~mermaid
flowchart LR
    A["Chạy HTTP tests"] --> B["Sinh snippet"]
    B --> C["Asciidoctor include snippet"]
    C --> D["Xuất tài liệu HTML/PDF"]
    D --> E["Đóng gói hoặc publish"]
~~~

Hãy thiết lập tác vụ sinh tài liệu **phụ thuộc vào** tác vụ test để include không đọc snippet cũ. Nếu muốn biên soạn tài liệu bằng Markdown, cần cấu hình format/template và quy trình xử lý tương ứng; không nên mặc định include thẳng `*.adoc` vào Markdown mà kỳ vọng mọi trình render đều hiểu cú pháp Asciidoctor.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không thấy `http-request.adoc` | Chưa cấu hình REST Docs, không gọi `document(...)`, test thất bại trước bước document hoặc tìm sai output directory | Xác minh cấu hình, chạy đúng test và kiểm tra thư mục theo identifier. |
| Snippet hiện `GET` dù tài liệu nói `POST` | Code test thực sự gọi `get(...)` hoặc include nhầm identifier | Mở test và request line, sửa method/identifier phù hợp endpoint. |
| Method sai khiến test nhận `405` | Request method không được endpoint cho phép | Đối chiếu mapping API và assertion; không sửa tài liệu để che lỗi test. |
| Thiếu query string | Test đưa dữ liệu vào `param(...)` nhưng không tạo query trên URL như kỳ vọng | Sử dụng `queryParam(...)` hoặc URI có query cụ thể. |
| Không có bảng field/header | `http-request` không tự sinh bảng mô tả | Khai báo `requestFields(...)`, `requestHeaders(...)` hoặc `queryParameters(...)`. |
| Request mẫu chứa token hoặc dữ liệu nhạy cảm | Test fixture dùng dữ liệu thật hoặc chưa tiền xử lý | Dùng dữ liệu giả, mask/thay header và body trước khi sinh tài liệu. |
| Trang tài liệu thiếu snippet khi build | Asciidoctor chạy trước test, `snippets` trỏ sai thư mục, hoặc identifier khác | Kiểm tra thứ tự các tác vụ build và đường dẫn include. |

## 11. Bài thực hành

Với một API mẫu quản lý sách, hãy viết ba HTTP tests độc lập:

1. `POST /api/books` gửi JSON, kỳ vọng `201 Created`, ghi vào `books-create/http-request.adoc`.
2. `GET /api/books?page=0&size=5`, kỳ vọng `200 OK`, mô tả hai tham số và ghi vào `books-list/http-request.adoc`.
3. `DELETE /api/books/42`, kỳ vọng status theo hợp đồng API (ví dụ `204 No Content`), ghi vào `books-delete/http-request.adoc`.

Sau đó mở từng `http-request.adoc` và kiểm tra ba dòng request đầu tiên lần lượt bắt đầu bằng `POST`, `GET`, `DELETE`. Thêm vào tài liệu Asciidoctor, chạy lại test, rồi cố ý sửa method ở một test để thấy assertion phát hiện khác biệt.

**Tiêu chí hoàn thành:** mỗi operation có một identifier riêng, một assertion phù hợp, snippet thể hiện chính xác HTTP method và URI được gọi, tài liệu include đúng tập tin, và CI chỉ xuất bản tài liệu sau khi các bài kiểm thử liên quan thành công.

## Tham khảo chính thức

- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Customizing requests and responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
