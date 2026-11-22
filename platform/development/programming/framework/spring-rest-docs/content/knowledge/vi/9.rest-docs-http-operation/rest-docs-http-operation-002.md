# Snippet `http-response` và status code trả về

## 1. Mục tiêu bài học

Trong chương **HTTP operation** của `SPRING_REST_DOCS`, mỗi bài kiểm thử HTTP có thể ghi nhận một cặp **request–response**. Request mô tả client đã gửi gì; response cho biết server thực sự trả về **mã trạng thái HTTP, header và body** nào. Spring REST Docs sử dụng dữ liệu đã ghi nhận để sinh tài liệu API, trong đó `http-response.adoc` là snippet thể hiện nguyên một phản hồi HTTP ở dạng dễ đọc.

Chủ đề này thuộc quy trình **tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử** bằng MockMvc, WebTestClient hoặc REST Assured. Sau khi sinh các snippet request, response, payload, tham số và header, nhóm phát triển có thể đưa chúng vào Asciidoctor hoặc quy trình Markdown được cấu hình tương ứng, chạy tự động trong build/CI.

Sau bài học, bạn sẽ có thể:

- Đọc một `http-response` và xác định status code, reason phrase, headers và body.
- Hiểu nhóm mã `1xx` đến `5xx`, đặc biệt `200`, `201`, `202`, `204`, `400`, `404` và `500`.
- Viết test kiểm chứng status, header và body trước khi tạo snippet.
- Phân biệt `http-response` với `http-request`, `response-body`, `response-headers` và `response-fields`.
- Biên soạn tài liệu từ snippet đã sinh và kiểm soát việc cập nhật tài liệu trong CI.

## 2. Cấu trúc của snippet `http-response`

Giả sử một request `GET /api/books/42` thành công và API trả về sách có mã `42`. Nội dung `http-response.adoc` được Spring REST Docs sinh **có thể** giống ví dụ sau:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"id":42,"title":"Spring in Action"}
~~~

Đây là **ví dụ minh họa**, không phải nội dung được bảo đảm xuất hiện từng ký tự ở mọi hệ thống. Thứ tự và sự hiện diện của các header, charset, `Content-Length`, reason phrase hay cách format JSON phụ thuộc response thực tế và cấu hình xử lý snippet.

| Thành phần | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Dòng trạng thái | `HTTP/1.1 200 OK` | Phiên bản HTTP biểu diễn trong snippet, status code `200` và reason phrase `OK`. |
| Status code | `200` | Giá trị số quan trọng nhất để phân loại kết quả HTTP. |
| Reason phrase | `OK` | Cụm từ hỗ trợ người đọc; không nên dựa vào nó để kiểm chứng logic. |
| Response header | `Content-Type: application/json` | Định dạng biểu diễn của response body. |
| Response header | `Cache-Control: no-store` | Chỉ thị cache mà server gửi. |
| Dòng trống | Giữa headers và body | Ranh giới hiển thị giữa metadata và payload. |
| Response body | `{"id":42,"title":"Spring in Action"}` | Nội dung API trả về trong operation đã được test. |

**Điểm mấu chốt:** `http-response` ghi lại **response thực tế của một operation kiểm thử**. Spring REST Docs không suy luận response từ `@ResponseStatus`, tên phương thức controller, mã được viết trong tài liệu hay nội dung dự kiến của developer. Nếu test thực sự nhận `404`, snippet sẽ thể hiện `404`; chỉ khi assertion yêu cầu `200` thì bài kiểm thử mới phát hiện sai lệch.

Ngoài ra, bản thân response HTTP **không chứa HTTP method của request**. Để biết `200 OK` này ứng với `GET`, `POST` hay method khác, cần xem bài test, phần mô tả endpoint hoặc snippet `http-request` đi kèm.

### Status line và phiên bản HTTP

Dạng `HTTP/1.1 200 OK` phổ biến trong tài liệu REST Docs là **cách biểu diễn dễ đọc**. Trên HTTP/2 và HTTP/3, response được mã hóa bằng cơ chế khác, sử dụng giá trị status tương ứng với pseudo-header `:status` và không có reason phrase theo mô hình dòng trạng thái HTTP/1.1. Do đó, không nên suy diễn hạ tầng production chỉ chạy HTTP/1.1 chỉ vì snippet có dòng trên.

Đối với kiểm thử tự động, hãy xác nhận **mã số** (ví dụ `200`), **header cần thiết** và **cấu trúc body**. Reason phrase chỉ mang tính hỗ trợ hiển thị.

## 3. Hiểu các nhóm HTTP status code

Status code là số nguyên ba chữ số. Chữ số đầu cho biết nhóm kết quả:

| Nhóm | Ý nghĩa khái quát | Ví dụ |
| --- | --- | --- |
| `1xx` | Phản hồi thông tin, quá trình xử lý giao thức đang tiếp diễn | `100 Continue`, `101 Switching Protocols` |
| `2xx` | Request đã được xử lý thành công theo ngữ nghĩa của status | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` |
| `3xx` | Điều hướng, dùng cache hoặc thực hiện thêm bước để lấy tài nguyên | `301 Moved Permanently`, `302 Found`, `304 Not Modified`, `307 Temporary Redirect` |
| `4xx` | Request từ client không thể được đáp ứng theo điều kiện hiện tại | `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found` |
| `5xx` | Server hoặc tầng xử lý trung gian gặp vấn đề khi đáp ứng request | `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable` |

Không nên diễn dịch “`2xx` là request không có vấn đề gì” quá rộng. Ví dụ, `202 Accepted` xác nhận đã **chấp nhận yêu cầu xử lý**, chưa chứng minh công việc bất đồng bộ hoàn tất. Tương tự, `304 Not Modified` thuộc nhóm `3xx` nhưng nhằm tái sử dụng bản lưu trong cache, không đơn thuần là chuyển hướng sang URL khác.

### Các status thường xuất hiện trong REST API

| Status | Tình huống thường gặp | Điều nên kiểm chứng thêm |
| --- | --- | --- |
| `200 OK` | Lấy tài nguyên thành công; cập nhật hoặc thao tác khác có response body | `Content-Type` và các field quan trọng của body. |
| `201 Created` | Tạo mới tài nguyên thành công | ID tài nguyên, body nếu API có trả, và `Location` nếu hợp đồng quy định. |
| `202 Accepted` | Tiếp nhận tác vụ xử lý bất đồng bộ | Mã tác vụ, endpoint kiểm tra tiến độ hoặc cơ chế callback nếu có. |
| `204 No Content` | Xóa/cập nhật thành công và không trả body | Xác nhận status `204` và body rỗng. |
| `301/308` | Chuyển hướng lâu dài | Header `Location`, ý nghĩa của chuyển hướng đối với method. |
| `302/307` | Chuyển hướng tạm thời | Header `Location`; lưu ý `307` yêu cầu bảo toàn method khi redirect. |
| `304 Not Modified` | Kiểm tra điều kiện cache cho thấy biểu diễn chưa đổi | Header cache liên quan; response không có body. |
| `400 Bad Request` | Request sai cú pháp hoặc dữ liệu đầu vào không đạt hợp đồng | Mã lỗi, thông điệp và thông tin field lỗi nếu API định nghĩa. |
| `401 Unauthorized` | Thiếu hoặc không hợp lệ thông tin xác thực | Cách client xác thực lại; header `WWW-Authenticate` khi áp dụng. |
| `403 Forbidden` | Server từ chối cho phép truy cập | Hợp đồng phân quyền, định dạng thông báo lỗi. |
| `404 Not Found` | Không tìm thấy tài nguyên tại URI được gọi | Cấu trúc lỗi, chính sách có/không tiết lộ sự tồn tại tài nguyên. |
| `409 Conflict` | Xung đột với trạng thái hiện tại của tài nguyên | Nguyên nhân xung đột và hướng xử lý của client. |
| `415 Unsupported Media Type` | Request body có media type không được hỗ trợ | `Content-Type` request được API chấp nhận. |
| `422 Unprocessable Content` | Nội dung request hiểu được nhưng không thể xử lý theo ngữ nghĩa | Chi tiết lỗi nghiệp vụ hoặc validation theo hợp đồng API. |
| `429 Too Many Requests` | Quá giới hạn tốc độ/tần suất | `Retry-After` nếu server cung cấp. |
| `500 Internal Server Error` | Lỗi máy chủ không được mô tả cụ thể hơn | Thông tin lỗi an toàn, không để lộ stack trace/secret. |
| `503 Service Unavailable` | Dịch vụ tạm không sẵn sàng | `Retry-After` nếu có, hướng xử lý retry của client. |

Mã nào “đúng” phải dựa vào **hợp đồng API**. Một API tạo mới có thể trả `201`, nhưng một endpoint xử lý tác vụ bất đồng bộ có thể trả `202`; không có quy tắc chung rằng mọi `POST` đều phải trả `201`.

### Những điểm dễ nhầm lẫn

1. **`200` và `204`:** cả hai đều báo thành công, nhưng `204` không có response body. Đừng viết tài liệu cho `204` với một payload JSON.
2. **`201` và `202`:** `201` thông báo tài nguyên đã được tạo; `202` chỉ thông báo request đã được chấp nhận xử lý.
3. **`401` và `403`:** `401` liên quan xác thực; `403` liên quan việc server từ chối thực hiện request. API có thể chủ động dùng `404` để tránh tiết lộ một tài nguyên.
4. **`400` và `422`:** ranh giới phụ thuộc thiết kế API và hợp đồng công bố; cần nhất quán thay vì lựa chọn theo cảm tính.
5. **`204`, `304` và response của `HEAD`:** không chứa response body theo ngữ nghĩa HTTP. Các trường hợp này không nên sinh bảng `responseFields` mô tả một payload tưởng tượng.
6. **`500` không mặc định là nhánh lỗi cần được ghi làm ví dụ nghiệp vụ:** hãy chỉ tài liệu hóa tình huống có kiểm soát và có hợp đồng rõ ràng, đồng thời bảo đảm response không rò rỉ thông tin nội bộ.

## 4. Sinh `http-response` bằng MockMvc

### 4.1. Chuẩn bị dự án

Ví dụ dùng Spring Boot 3.x, JUnit 5 và Java 17 trở lên, với ứng dụng Spring MVC đã có endpoint `GET /api/books/{id}`. Dependency test minh họa trong Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Giả sử dữ liệu test ổn định và request `GET /api/books/42` trả `200 OK` cùng JSON gồm **đúng hai trường** `id` và `title` như sau:

~~~json
{"id":42,"title":"Spring in Action"}
~~~

Endpoint thực tế hoặc test fixture phải bảo đảm dữ liệu này tồn tại. Spring REST Docs **không tự tạo endpoint hay dữ liệu giả**. Việc quản lý version Spring REST Docs nên theo dependency management/BOM của dự án.

### 4.2. Bài kiểm thử và snippet đầu tiên

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class BookApiDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentGetBookSuccess() throws Exception {
        mockMvc.perform(get("/api/books/42")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title").value("Spring in Action"))
            .andDo(document("books-get-one",
                responseHeaders(
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Media type của response body")
                ),
                responseFields(
                    fieldWithPath("id").description("Mã định danh sách"),
                    fieldWithPath("title").description("Tên sách")
                )
            ));
    }
}
~~~

Trong ví dụ này:

- `@AutoConfigureRestDocs(outputDir = "build/generated-snippets")` thiết lập vị trí tạo snippet cho MockMvc khi dùng cơ chế tích hợp REST Docs của Spring Boot.
- `get("/api/books/42")` kích hoạt operation cần tài liệu hóa; server được test sẽ quyết định response.
- `andExpect(status().isOk())` kiểm chứng status **200**; `contentTypeCompatibleWith` và `jsonPath` kiểm chứng thêm các phần quan trọng của hợp đồng response.
- `andDo(document("books-get-one", ...))` ghi operation và tạo snippet theo identifier `books-get-one`.
- `responseHeaders(...)` mô tả header `Content-Type`; `responseFields(...)` mô tả hai trường JSON và kiểm chứng tính khớp của mô tả payload với response theo chế độ thông thường.

Vì `andDo(...)` đứng sau các `andExpect(...)` trong chuỗi lệnh này, nếu một assertion thất bại thì bước sinh tài liệu ở cuối chuỗi **không được thực hiện**. Đó là cách phổ biến để buộc tài liệu chỉ được cập nhật khi hành vi được mong đợi đã được kiểm chứng.

### 4.3. Các tệp được sinh và ví dụ `http-response.adoc`

Khi test chạy thành công, thư mục sau thường xuất hiện:

~~~text
build/generated-snippets/
└── books-get-one/
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    ├── response-headers.adoc
    └── response-fields.adoc
~~~

Sáu tệp đầu là các snippet mặc định trong cấu hình Spring REST Docs phổ biến. Hai tệp cuối được tạo nhờ `responseHeaders(...)` và `responseFields(...)`. Danh sách có thể thay đổi nếu dự án tùy chỉnh snippet mặc định hoặc template.

Nội dung `books-get-one/http-response.adoc` có thể hiện như sau:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"Spring in Action"}
~~~

Không nên sao chép ví dụ minh họa này để thay cho snippet thực tế: hãy mở `http-response.adoc` sau khi chạy kiểm thử. Spring REST Docs có thể thêm header khác, định dạng body khác, hoặc đổi phần biểu diễn theo request/response preprocessor.

## 5. Kiểm chứng response khi tạo tài nguyên: `201 Created`

Tình huống `POST /api/books` minh họa rõ sự kết hợp giữa **status**, **header** và **body**. Giả sử hợp đồng API quy định:

- Request gửi JSON tên sách.
- Nếu tạo thành công, API trả `201 Created`.
- Header `Location` chứa URI của tài nguyên mới: `/api/books/43`.
- Body trả JSON `{"id":43,"title":"Spring in Action"}`.

Có thể bổ sung test sau **bên trong cùng lớp** `BookApiDocumentationTest` ở trên. Thêm các static import:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
~~~

Và method:

~~~java
@Test
void documentCreateBook() throws Exception {
    mockMvc.perform(post("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {"title":"Spring in Action"}
                """))
        .andExpect(status().isCreated())
        .andExpect(header().string(HttpHeaders.LOCATION, "/api/books/43"))
        .andExpect(jsonPath("$.id").value(43))
        .andExpect(jsonPath("$.title").value("Spring in Action"))
        .andDo(document("books-create",
            responseHeaders(
                headerWithName(HttpHeaders.LOCATION)
                    .description("URI của sách vừa được tạo"),
                headerWithName(HttpHeaders.CONTENT_TYPE)
                    .description("Media type của body phản hồi")
            ),
            responseFields(
                fieldWithPath("id").description("Mã sách mới"),
                fieldWithPath("title").description("Tên sách")
            )
        ));
}
~~~

Snippet `books-create/http-response.adoc` minh họa:

~~~http
HTTP/1.1 201 Created
Location: /api/books/43
Content-Type: application/json

{"id":43,"title":"Spring in Action"}
~~~

Giá trị `43` chỉ là dữ liệu test. Khi ứng dụng sử dụng ID tự tăng hoặc dữ liệu động, cần chuẩn bị fixture ổn định và viết assertion phù hợp; không nên để kiểm thử phụ thuộc vào một ID được cấp ngẫu nhiên rồi cố định nó trong tài liệu.

**Lưu ý:** `201 Created` không bắt buộc mọi API phải trả đúng hai field trên; đây là hợp đồng giả định của ví dụ. Tài liệu luôn phải theo response được endpoint thực sự trả về.

## 6. Phản hồi không có body: `204 No Content`

Giả sử `DELETE /api/books/42` trả `204` khi xóa thành công và **không có body**. Test có thể viết:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;

// Đặt method dưới đây vào lớp BookApiDocumentationTest
@Test
void documentDeleteBook() throws Exception {
    mockMvc.perform(delete("/api/books/42"))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""))
        .andDo(document("books-delete"));
}
~~~

Ví dụ nội dung `books-delete/http-response.adoc`:

~~~http
HTTP/1.1 204 No Content
~~~

Response thực tế có thể có các header hợp lệ, nhưng phải giữ quy tắc **không có response body**. Đừng cấu hình `responseFields(...)` để mô tả một object JSON cho response `204`.

Cũng cần phân biệt idempotency của `DELETE` với tính đồng nhất của response: gửi cùng một yêu cầu xóa nhiều lần có thể không có thêm hiệu ứng lên trạng thái tài nguyên, nhưng status các lần gọi có thể khác nhau theo hợp đồng API (chẳng hạn `204` rồi `404`).

## 7. Tài liệu hóa nhánh lỗi: `404 Not Found`

Một endpoint chỉ có ví dụ `200` chưa cho người dùng API biết chuyện gì xảy ra khi truy cập tài nguyên không tồn tại. Hãy tạo operation **riêng** cho nhánh lỗi.

Giả sử `GET /api/books/9999` trả status `404` và body theo hợp đồng riêng của API:

~~~json
{"code":"BOOK_NOT_FOUND","message":"Book not found"}
~~~

Test bổ sung có thể là:

~~~java
@Test
void documentBookNotFound() throws Exception {
    mockMvc.perform(get("/api/books/9999")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isNotFound())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.code").value("BOOK_NOT_FOUND"))
        .andExpect(jsonPath("$.message").value("Book not found"))
        .andDo(document("books-get-not-found",
            responseFields(
                fieldWithPath("code").description("Mã lỗi nghiệp vụ"),
                fieldWithPath("message").description("Thông báo lỗi cho client")
            )
        ));
}
~~~

Snippet minh họa:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"BOOK_NOT_FOUND","message":"Book not found"}
~~~

Body lỗi này **chỉ là hợp đồng ví dụ**, không phải định dạng lỗi mặc định của Spring Boot hay Spring REST Docs. Ứng dụng thực tế có thể trả [Problem Details (RFC 9457)](https://www.rfc-editor.org/rfc/rfc9457.html) với media type `application/problem+json`, một cấu trúc riêng hoặc thậm chí không có body theo thiết kế. Luôn dựa vào phản hồi thật và kiểm chứng nó trong test.

Nên tạo identifier khác nhau cho từng tình huống (`books-get-one` và `books-get-not-found`), để không làm các snippet của hai kết quả ghi đè nhau.

## 8. `http-response` khác những snippet nào?

| Snippet | Nội dung chính | Khi sử dụng |
| --- | --- | --- |
| `http-request.adoc` | Method, URI, request headers và request body | Chứng minh client gửi gì. |
| **`http-response.adoc`** | Status line, response headers và response body | Minh họa phản hồi HTTP hoàn chỉnh. |
| `response-body.adoc` | Chỉ nội dung body của response | Trình bày một payload dài tách khỏi header. |
| `response-headers.adoc` | Bảng mô tả header đã khai báo qua `responseHeaders(...)` | Giải thích ý nghĩa `Location`, `ETag`, `Content-Type`... |
| `response-fields.adoc` | Bảng mô tả các trường payload đã khai báo qua `responseFields(...)` | Giải thích schema JSON/XML trả về. |
| `curl-request.adoc` | Lệnh `curl` có thể gọi lại request | Cho phép người đọc tái hiện request. |

**Không có snippet mặc định “status-codes.adoc” tự liệt kê tất cả status mà một endpoint có thể trả.** `http-response` chứa **một status của một lần chạy test**. Để tài liệu hóa nhiều kết quả như `200`, `404`, `409`, hãy tạo test riêng cho từng trường hợp rồi biên soạn các trường hợp đó thành các mục tài liệu.

Một chuỗi mô tả hợp đồng có thể diễn giải như sau:

~~~mermaid
flowchart TD
    A["Test gửi request HTTP"] --> B["Ứng dụng trả status, header, body"]
    B --> C{"Assertions có đạt?"}
    C -->|Không| D["Test thất bại"]
    C -->|Có| E["Spring REST Docs ghi HTTP operation"]
    E --> F["http-response.adoc"]
    E --> G["response-headers.adoc"]
    E --> H["response-fields.adoc"]
    F --> I["Tài liệu Asciidoctor"]
    G --> I
    H --> I
~~~

Sơ đồ minh họa luồng test theo cách sắp xếp `andExpect(...)` trước `andDo(...)` trong ví dụ MockMvc; điểm kích hoạt sinh tài liệu có thể được tích hợp khác nhau giữa các HTTP test client.

### Kiểm chứng payload bằng `responseFields`

Ví dụ:

~~~java
responseFields(
    fieldWithPath("id").description("Mã sách"),
    fieldWithPath("title").description("Tên sách")
)
~~~

Trong chế độ thông thường, REST Docs yêu cầu các field được mô tả phù hợp với payload và báo lỗi nếu xuất hiện field không được mô tả. Điều này giúp phát hiện response schema thay đổi ngoài dự kiến. Nếu cố tình chỉ trình bày một phần payload, `relaxedResponseFields(...)` cho phép bỏ qua field bổ sung; tuy nhiên không nên dùng tùy tiện vì có thể che giấu thay đổi trong hợp đồng API.

Với response `204` hoặc response hoàn toàn không có body, không sử dụng `responseFields(...)`. Với JSON dạng mảng, phải dùng các path descriptor phù hợp cấu trúc thực tế (chẳng hạn `[].id` khi top-level là mảng), thay vì giả định mọi response đều có object gốc.

## 9. Sử dụng WebTestClient và REST Assured

Spring REST Docs hoạt động với nhiều HTTP test client. **Status luôn là giá trị server trả**, còn cấu hình ghi tài liệu phụ thuộc công cụ.

### 9.1. WebTestClient

Ví dụ dưới đây giả sử `webTestClient` đã được cấu hình tích hợp Spring REST Docs và có endpoint `GET /api/books/42`:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
    .uri("/api/books/42")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(42)
    .consumeWith(document("books-get-webtestclient"));
~~~

`expectStatus().isOk()` xác nhận `200` và `consumeWith(document(...))` ghi operation thành snippet. Với WebTestClient, dependency/tích hợp tương ứng là `spring-restdocs-webtestclient`. Cần thiết lập client/REST Docs phù hợp với kiểu kiểm thử Spring WebFlux hoặc Spring MVC mà dự án dùng.

### 9.2. REST Assured

REST Assured dùng **filter** của Spring REST Docs để ghi HTTP operation. Minh họa ý tưởng với một request specification đã được cấu hình:

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

// "spec" là RequestSpecification đã cấu hình base URI, port và REST Docs.
given(spec)
    .filter(document("books-get-restassured"))
    .accept("application/json")
.when()
    .get("/api/books/42")
.then()
    .statusCode(200);
~~~

Module tích hợp là `spring-restdocs-restassured`. Filter ghi operation khi request được thực hiện; assertion `statusCode(200)` diễn ra sau khi nhận response. Vì vậy, CI vẫn phải coi **test assertion thành công** là điều kiện để phát hành tài liệu, thay vì suy diễn rằng cứ có snippet là API đã thỏa hợp đồng. Đối với REST Assured, cần cấu hình `RestAssuredRestDocumentationConfigurer` hoặc cơ chế REST Docs tương ứng theo phiên bản dự án để xác định context/output.

### 9.3. Đối chiếu nhanh

| Client | Kiểm tra status | Sinh tài liệu |
| --- | --- | --- |
| MockMvc | `.andExpect(status().isOk())` | `.andDo(document("..."))` |
| WebTestClient | `.expectStatus().isOk()` | `.expectBody().consumeWith(document("..."))` |
| REST Assured | `.then().statusCode(200)` | Filter `document("...")` trong request specification |

Các API kiểm thử này khác nhau về cú pháp nhưng đều hướng tới cùng mục tiêu: **response được trình bày phải xuất phát từ lời gọi HTTP thực tế**.

## 10. Làm sạch và ổn định response trước khi sinh tài liệu

Response thực tế có thể chứa `Date`, `Set-Cookie`, correlation ID, timestamp, ID động, trace ID hoặc JSON khó đọc. Nếu để nguyên giá trị biến thiên, tài liệu dễ nhiễu và khó review.

Spring REST Docs có **response preprocessors** để thay đổi **cách response xuất hiện trong snippet**, không thay đổi response server đã trả hoặc giá trị assertion kiểm chứng.

Ví dụ, thay lời gọi `.andDo(document(...))` cuối cùng bằng cấu hình vừa xử lý request/response vừa khai báo snippets:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

// Ví dụ đặt sau các .andExpect(...) trong test GET:
.andDo(document("books-get-one",
    preprocessRequest(),
    preprocessResponse(
        removeHeaders("Date", "Set-Cookie"),
        prettyPrint()
    ),
    responseFields(
        fieldWithPath("id").description("Mã sách"),
        fieldWithPath("title").description("Tên sách")
    )
));
~~~

Đây là **ví dụ thay thế** cho một lời gọi `document(...)` trong test; không ghép một lời gọi mới cùng identifier vào test vốn đã có lời gọi tài liệu hóa.

Một số nguyên tắc:

- Sử dụng dữ liệu test giả/ổn định ngay từ nguồn. Không đưa token hoặc cookie thật vào fixture và báo cáo.
- Chỉ ẩn hoặc chuẩn hóa dữ liệu cần thiết. Nếu header được loại bỏ, không đồng thời yêu cầu `responseHeaders(...)` mô tả header đó như một header hiện diện.
- `prettyPrint()` làm JSON dễ đọc hơn, nhưng không thay thế assertion về cấu trúc/nội dung.
- Đối với status `204`, không ép thêm response body chỉ để tài liệu trông “đủ”.
- Nếu preprocessing thay đổi URI, hostname hay định dạng body được trình bày, giải thích rõ đó là **biểu diễn dùng trong tài liệu**.

## 11. Biên soạn Asciidoctor và tích hợp build/CI

Mặc định Spring REST Docs thường xuất các snippet `*.adoc` để đưa vào Asciidoctor. Một trang tài liệu có thể nhóm tình huống thành công và lỗi như sau:

~~~asciidoc
= Books API

== Xem một cuốn sách

=== Thành công — 200 OK

HTTP request:
include::{snippets}/books-get-one/http-request.adoc[]

HTTP response:
include::{snippets}/books-get-one/http-response.adoc[]

Response fields:
include::{snippets}/books-get-one/response-fields.adoc[]

=== Không tìm thấy — 404 Not Found

include::{snippets}/books-get-not-found/http-response.adoc[]

== Tạo sách — 201 Created

include::{snippets}/books-create/http-response.adoc[]

include::{snippets}/books-create/response-headers.adoc[]

== Xóa sách — 204 No Content

include::{snippets}/books-delete/http-response.adoc[]
~~~

Thuộc tính `snippets` phải được build cấu hình tới đúng thư mục sinh snippet (trong ví dụ: `build/generated-snippets`). Đường dẫn cụ thể phụ thuộc vị trí source Asciidoctor, cách dự án định nghĩa attribute và hệ thống build.

Quy trình khuyến nghị:

~~~mermaid
flowchart LR
    A["Build/CI"] --> B["Chạy HTTP tests và assertions"]
    B --> C["Sinh snippets"]
    C --> D["Asciidoctor include các snippets"]
    D --> E["Xuất HTML/PDF hoặc tài liệu đóng gói"]
    E --> F["Publish khi pipeline PASS"]
~~~

Để tránh tài liệu dùng snippet cũ, hãy cấu hình tác vụ Asciidoctor **phụ thuộc vào** tác vụ kiểm thử tạo snippet và cấu hình đúng đầu vào/đầu ra của các tác vụ. Trên CI, cần coi test fail, snippet thiếu, include path sai hoặc tài liệu build lỗi là pipeline fail theo hợp đồng của dự án.

Nếu muốn viết tài liệu bằng Markdown, cần cấu hình template/output hoặc quy trình chuyển đổi phù hợp. Không nên mặc định cú pháp Asciidoctor `include::{snippets}/...[]` sẽ được một Markdown renderer thuần hỗ trợ.

**Cẩn thận với trạng thái “xanh giả”:** snippet còn sót từ lần chạy trước có thể được include dù test hiện tại không chạy. Dự án nên bố trí output dir, dependencies và điều kiện fail rõ ràng để build tài liệu phản ánh lần test hiện tại.

## 12. Khắc phục lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không xuất hiện `http-response.adoc` | Thiếu tích hợp REST Docs, test dừng trước `document(...)`, hoặc sai output directory | Kiểm tra cấu hình, log test, identifier và nơi chứa snippet. |
| Snippet hiển thị `404` thay vì `200` | Dữ liệu test không tồn tại, URI sai hoặc endpoint xử lý khác dự kiến | Kiểm tra fixture, request và assertion `status().isOk()`. |
| Tài liệu ghi `201` nhưng test nhận `200` | Mô tả viết tay đã lệch khỏi API | Chốt lại hợp đồng endpoint; cập nhật code/test và tài liệu một cách nhất quán. |
| Thấy `204` nhưng có JSON body trong trang tài liệu | Include nhầm snippet hoặc ví dụ viết tay không đúng | Dùng đúng identifier; loại bỏ payload không hợp lệ khỏi phần mô tả `204`. |
| `response-fields.adoc` không được sinh | Chỉ gọi `document(...)` mà chưa khai báo `responseFields(...)` | Thêm descriptor trong lời gọi `document(...)`. |
| Test sinh snippet thất bại vì field chưa được mô tả | Response body có field mới hoặc descriptor sai path | Cập nhật bảng field theo contract thực tế; cân nhắc `relaxedResponseFields` chỉ khi có chủ đích. |
| Header `Location` không được ghi trong snippet | API chưa trả header, test nhầm nhánh hoặc preprocessing loại bỏ header | Assertion với `header().string(...)`; kiểm tra filter/preprocessor. |
| Snippet không ổn định theo mỗi lần chạy | Timestamp, ID, random values, headers động | Sử dụng fixtures ổn định và response preprocessing. |
| Build tài liệu thành công dù HTTP test lỗi | Pipeline cho phép publish từ snippet cũ hoặc không phụ thuộc test | Buộc build tài liệu phụ thuộc test và chỉ publish khi toàn bộ pipeline PASS. |

## 13. Bài thực hành và tiêu chí hoàn thành

Xây dựng tài liệu cho một REST API quản lý đơn hàng với các operation có dữ liệu kiểm thử xác định:

1. **`GET /api/orders/101` → `200 OK`:** kiểm chứng status, `Content-Type` và các field `id`, `status` trong response; sinh `orders-get-success/http-response.adoc`.
2. **`POST /api/orders` → `201 Created`:** kiểm chứng status và `Location`, cùng payload tạo đơn theo hợp đồng; sinh `orders-create/http-response.adoc`.
3. **`DELETE /api/orders/101` → `204 No Content`:** kiểm chứng body rỗng; sinh `orders-delete/http-response.adoc`.
4. **`GET /api/orders/999` → `404 Not Found`:** kiểm chứng mã lỗi nghiệp vụ và response fields; sinh `orders-get-not-found/http-response.adoc`.

Mở bốn tệp `http-response.adoc` và đối chiếu từng status line. Biên soạn Asciidoctor include đúng snippet; sau đó cố ý thay đổi expectation trong một test (chẳng hạn yêu cầu `201` cho endpoint thực tế trả `200`) để xác nhận test thất bại và pipeline không phát hành tài liệu lệch hợp đồng.

**Hoàn thành bài** khi bạn giải thích được status line và body, viết assertion chính xác cho từng trạng thái, phân biệt các snippet có liên quan, sử dụng identifier độc lập cho từng kết quả và cấu hình tài liệu chỉ build/publish sau khi test đạt.

## Tài liệu tham khảo

- [Spring REST Docs Reference — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/)
- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)
- [Problem Details for HTTP APIs — RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html)
