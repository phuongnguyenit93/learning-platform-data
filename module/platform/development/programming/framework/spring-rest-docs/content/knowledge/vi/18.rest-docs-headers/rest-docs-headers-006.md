# Content-Type, Location, ETag và Cache-Control

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào build và CI.

Chương **Headers** tìm hiểu metadata ảnh hưởng đến cách client gửi dữ liệu, định vị tài nguyên và lưu cache. Bài này tập trung vào bốn header HTTP:

- `Content-Type`: biểu thị kiểu representation của message body.
- `Location`: cung cấp URI liên quan đến kết quả request, thường là tài nguyên vừa tạo hoặc đích chuyển hướng.
- `ETag`: cung cấp validator cho một representation để client có thể kiểm tra phiên bản.
- `Cache-Control`: quy định chính sách cache cho request hoặc response.

Sau bài học, bạn có thể giải thích đúng bốn header này, phân biệt vai trò ở request với response, kiểm tra giá trị bằng WebTestClient và sinh snippet request/response headers bằng Spring REST Docs.

## 2. Nhìn bốn header trong một giao dịch HTTP

Ví dụ client tạo đơn hàng:

~~~http
POST /api/orders HTTP/1.1
Accept: application/json
Content-Type: application/json

{"productId":"BOOK-01","quantity":2}
~~~

Server có thể trả:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/42
Cache-Control: no-store

{"id":42,"productId":"BOOK-01","quantity":2}
~~~

| Header | Phía gửi | Ý nghĩa |
| --- | --- | --- |
| `Content-Type` | Client và server | Client gửi JSON; server trả JSON. Mỗi message có body riêng và khai báo kiểu nội dung của body đó. |
| `Location` | Server | Cho client biết URI của đơn hàng vừa được tạo. |
| `ETag` | Thường là server | Validator client có thể gửi lại trong `If-Match` hoặc `If-None-Match` ở request sau. |
| `Cache-Control` | Client hoặc server | Diễn đạt chỉ thị cache cho request hoặc response; ý nghĩa phụ thuộc chiều và directive. |

Không phải endpoint nào cũng dùng cả bốn header. REST Docs nên mô tả header thực sự thuộc hợp đồng của operation, thay vì đưa tất cả vào mọi bảng.

## 3. Content-Type: kiểu dữ liệu của message body

`Content-Type` cho biết định dạng representation được gửi trong body. Nó không mô tả định dạng mà client mong muốn nhận; mục đích đó thuộc về `Accept`.

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Spring REST Docs"}
~~~

Response cũng có `Content-Type` riêng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"Spring REST Docs"}
~~~

| Media type | Nội dung |
| --- | --- |
| `application/json` | JSON |
| `application/xml` | XML |
| `text/plain` | Văn bản thuần |
| `text/html` | HTML |
| `application/x-www-form-urlencoded` | Form URL encoded |
| `multipart/form-data` | Form nhiều part, thường có file upload |

### 3.1. Phân biệt Content-Type và Accept

| Header | Câu hỏi được trả lời |
| --- | --- |
| `Content-Type` | Body message hiện tại được mã hóa theo định dạng nào? |
| `Accept` | Client muốn server chọn representation trả về theo định dạng nào? |

Nếu request khai báo `Content-Type: application/json` nhưng endpoint không hỗ trợ media type đó, server có thể trả `415 Unsupported Media Type`. Nếu `Accept` không tương thích với representation server có thể tạo, server có thể trả `406 Not Acceptable`.

### 3.2. Tham số charset

Header có thể chứa tham số media type:

~~~http
Content-Type: text/plain; charset=UTF-8
~~~

Khi test, `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)` phù hợp nếu chỉ cần xác nhận kiểu media tương thích, không yêu cầu so sánh mọi tham số. Chọn assertion chính xác hơn nếu charset hoặc tham số khác là một phần của hợp đồng.

## 4. Location: URI của tài nguyên hoặc đích chuyển hướng

`Location` là response header chứa URI liên quan đến kết quả request. Trường hợp phổ biến là server trả `201 Created` sau khi tạo tài nguyên:

~~~http
HTTP/1.1 201 Created
Location: /api/books/42
Content-Type: application/json
~~~

Client có thể dùng URI này để đọc hoặc thao tác với tài nguyên vừa tạo. `Location` cũng được dùng trong một số response chuyển hướng; khi đó URI cho biết đích mà client cần xem xét tiếp theo.

### 4.1. Mô tả Location trong REST Docs

~~~java
responseHeaders(
    headerWithName("Location")
        .description("URI tương đối của tài nguyên vừa tạo; client có thể dùng URI này để truy vấn tài nguyên.")
)
~~~

Description có ích nên giải thích URI là tuyệt đối hay tương đối, trỏ tới loại tài nguyên nào và client dùng nó ra sao.

### 4.2. Kiểm tra Location với WebTestClient

~~~java
client.post()
    .uri("/api/books")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("title", "Spring REST Docs"))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().valueEquals("Location", "/api/books/42");
~~~

Giá trị mong đợi phải khớp URI do endpoint thực sự tạo. Nếu server dùng URI tuyệt đối, kiểm tra cả scheme/host nếu đó là một phần hợp đồng. Nếu host thay đổi theo môi trường test, REST Docs có thể chuẩn hóa URI trong snippet bằng preprocessor.

## 5. ETag: validator của representation

`ETag` là validator gắn với một representation. Server thường trả ETag để client lưu lại và sử dụng trong request sau.

~~~http
HTTP/1.1 200 OK
ETag: "book-v42"
Content-Type: application/json

{"id":42,"title":"Spring REST Docs"}
~~~

ETag thường được biểu diễn dưới dạng entity-tag có dấu ngoặc kép; server cũng có thể dùng weak validator với tiền tố `W/`, ví dụ `W/"book-v42"`. Giá trị là opaque đối với client: client lưu và gửi lại đúng validator, không tự suy diễn cấu trúc bên trong.

### 5.1. Conditional GET với If-None-Match

Client gửi ETag đã lưu trong `If-None-Match` khi hỏi server representation có thay đổi hay chưa:

~~~http
GET /api/books/42 HTTP/1.1
If-None-Match: "book-v42"
~~~

Nếu validator vẫn khớp theo quy tắc HTTP, server có thể trả `304 Not Modified` mà không gửi lại representation. Client tiếp tục dùng bản đã cache. Nếu representation thay đổi, server trả representation mới cùng ETag mới.

### 5.2. Conditional update với If-Match

Client gửi `If-Match` khi chỉ muốn cập nhật nếu tài nguyên vẫn là phiên bản mà client đã đọc:

~~~http
PUT /api/books/42 HTTP/1.1
If-Match: "book-v42"
Content-Type: application/json

{"title":"Spring REST Docs, bản cập nhật"}
~~~

Nếu validator không còn khớp, server thường trả `412 Precondition Failed`. Cơ chế này giúp tránh ghi đè thay đổi của client khác. `If-Match` và `If-None-Match` là request header; `ETag` thường được server gửi trong response.

### 5.3. Mô tả ETag trong REST Docs

~~~java
responseHeaders(
    headerWithName("ETag")
        .description("Validator của representation hiện tại; client gửi lại trong If-Match hoặc If-None-Match khi thực hiện request có điều kiện.")
)
~~~

Không mô tả ETag như mã tài nguyên hoặc ID nghiệp vụ nếu API không quy định như vậy. Client nên xem giá trị là opaque và gửi lại nguyên trạng.

## 6. Cache-Control: chỉ thị chính sách cache

`Cache-Control` có thể xuất hiện trong request và response. Directive cụ thể quyết định hành vi cache; không nên mô tả mọi giá trị `Cache-Control` như thể chúng có cùng nghĩa.

### 6.1. Một số response directive thường gặp

| Directive | Ý nghĩa khái quát |
| --- | --- |
| `no-store` | Cache không được lưu trữ message theo chỉ thị này. |
| `no-cache` | Cache phải xác nhận lại với origin trước khi sử dụng representation đã lưu; không đồng nghĩa với việc tuyệt đối không được lưu. |
| `private` | Response chỉ dành cho private cache, không dành cho shared cache. |
| `public` | Cho phép shared cache lưu response trong những điều kiện được quy định. |
| `max-age=60` | Freshness lifetime tối đa được chỉ định là 60 giây. |
| `must-revalidate` | Khi representation đã stale, cache phải xác nhận lại trước khi dùng theo directive. |

Ví dụ response không muốn được lưu:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
~~~

Ví dụ response có thể được private cache giữ trong thời gian ngắn:

~~~http
HTTP/1.1 200 OK
Cache-Control: private, max-age=60
~~~

### 6.2. Request directive

Client cũng có thể gửi `Cache-Control` để điều khiển cách cache xử lý request:

~~~http
GET /api/books/42 HTTP/1.1
Cache-Control: no-cache
~~~

Ở đây, client yêu cầu cache xác nhận lại freshness trước khi dùng representation đã lưu theo quy tắc HTTP. Request có `Cache-Control: no-store` thể hiện client không muốn cache lưu request hoặc response tương ứng theo chỉ thị này.

### 6.3. Mô tả Cache-Control trong REST Docs

~~~java
responseHeaders(
    headerWithName("Cache-Control")
        .description("Chính sách cache của response; endpoint này dùng private, max-age=60 để giới hạn cache vào private cache trong 60 giây.")
)
~~~

Mô tả cần nêu các directive thực sự được endpoint dùng và ý nghĩa đối với client/proxy. Nếu chính sách cache thay đổi theo loại tài nguyên, hãy mô tả trong operation tương ứng.

## 7. Descriptor cho bốn header

Các import tĩnh:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
~~~

Ví dụ bảng request header:

~~~java
requestHeaders(
    headerWithName("Content-Type")
        .description("Kiểu nội dung của request body; endpoint yêu cầu application/json."),
    headerWithName("Accept")
        .description("Media type client chấp nhận; endpoint trả application/json.")
)
~~~

Ví dụ bảng response header:

~~~java
responseHeaders(
    headerWithName("Content-Type")
        .description("Kiểu representation của response; endpoint trả application/json."),
    headerWithName("Location")
        .description("URI tương đối của tài nguyên mới được tạo."),
    headerWithName("ETag")
        .description("Validator của representation, dùng cho request có điều kiện."),
    headerWithName("Cache-Control")
        .description("Chính sách cache mà client và cache trung gian phải tuân theo.")
)
~~~

Chỉ truyền những header thực sự tồn tại trong request/response của operation. Descriptor bắt buộc nhưng header không xuất hiện có thể khiến test tài liệu thất bại. Dùng `.optional()` khi header được phép vắng mặt; dùng `.ignored()` khi header cần được bỏ khỏi bảng mô tả theo chủ đích.

## 8. Ví dụ hoàn chỉnh: test GET và POST bằng WebTestClient

Ví dụ dưới đây có hai operation:

- `POST /api/books` nhận JSON và trả `201 Created`, `Location` cùng `Content-Type`.
- `GET /api/books/42` trả JSON cùng `ETag` và `Cache-Control`.

### 8.1. Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient'
}
~~~

Spring Boot thường quản lý phiên bản dependency tương thích. Ví dụ dùng JUnit 5 và WebFlux.

### 8.2. Test và controller

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class StandardHeadersDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new BookController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsCreateBookHeaders() {
        client.post()
            .uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "Spring REST Docs"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().valueEquals(HttpHeaders.LOCATION, "/api/books/42")
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("books/create",
                requestHeaders(
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Kiểu nội dung của request body; endpoint yêu cầu application/json."),
                    headerWithName(HttpHeaders.ACCEPT)
                        .description("Media type client chấp nhận; endpoint trả application/json.")
                ),
                responseHeaders(
                    headerWithName(HttpHeaders.LOCATION)
                        .description("URI tương đối của sách mới được tạo; dùng URI này để truy vấn sách."),
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Kiểu representation của response; endpoint trả application/json.")
                ),
                requestFields(
                    fieldWithPath("title").description("Tên sách")
                ),
                responseFields(
                    fieldWithPath("id").description("Mã sách vừa tạo"),
                    fieldWithPath("title").description("Tên sách")
                )
            ));
    }

    @Test
    void documentsGetBookCachingHeaders() {
        client.get()
            .uri("/api/books/{id}", 42)
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(HttpHeaders.ETAG, "\"book-v42\"")
            .expectHeader().exists(HttpHeaders.CACHE_CONTROL)
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo(42)
            .consumeWith(document("books/get",
                requestHeaders(
                    headerWithName(HttpHeaders.ACCEPT)
                        .description("Media type client chấp nhận; endpoint trả application/json.")
                ),
                responseHeaders(
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Kiểu representation của response; endpoint trả application/json."),
                    headerWithName(HttpHeaders.ETAG)
                        .description("Validator của representation; client gửi lại trong If-None-Match hoặc If-Match khi thực hiện request có điều kiện."),
                    headerWithName(HttpHeaders.CACHE_CONTROL)
                        .description("Chính sách cache của response; private, max-age=60 cho phép private cache lưu representation trong 60 giây.")
                ),
                responseFields(
                    fieldWithPath("id").description("Mã sách"),
                    fieldWithPath("title").description("Tên sách")
                )
            ));
    }

    @RestController
    static class BookController {

        @PostMapping(
            path = "/api/books",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Mono<ResponseEntity<Map<String, Object>>> create(
                @RequestBody Map<String, String> request) {
            Map<String, Object> body = Map.of(
                "id", 42,
                "title", request.get("title")
            );
            return Mono.just(
                ResponseEntity.created(URI.create("/api/books/42"))
                    .body(body)
            );
        }

        @GetMapping(
            path = "/api/books/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Mono<ResponseEntity<Map<String, Object>>> get(
                @PathVariable("id") long id) {
            Map<String, Object> body = Map.of(
                "id", id,
                "title", "Spring REST Docs"
            );
            return Mono.just(
                ResponseEntity.ok()
                    .eTag("\"book-v42\"")
                    .cacheControl(
                        CacheControl.maxAge(Duration.ofSeconds(60)).cachePrivate()
                    )
                    .body(body)
            );
        }
    }
}
~~~

Các assertion và descriptor phản ánh response mà controller tạo ra:

1. POST kiểm tra status `201`, header `Location`, `Content-Type` và JSON body.
2. GET kiểm tra ETag, sự hiện diện của `Cache-Control`, `Content-Type` và JSON body.
3. `requestHeaders(...)` mô tả header client gửi; `responseHeaders(...)` mô tả header server trả.
4. `consumeWith(document(...))` ghi snippet sau khi các assertion quan trọng đã chạy.

Ví dụ chỉ kiểm tra sự hiện diện của `Cache-Control`, còn descriptor ghi giá trị server thực sự trả vào snippet. Nếu directive cụ thể là hợp đồng cần bảo vệ, hãy bổ sung assertion so sánh giá trị theo định dạng được chuẩn hóa của ứng dụng.

## 9. Dùng ETag trong request có điều kiện

Khi đã đọc ETag từ response, test tiếp theo có thể gửi validator đó trong request:

~~~java
client.get()
    .uri("/api/books/42")
    .header(HttpHeaders.IF_NONE_MATCH, "\"book-v42\"")
    .exchange()
    .expectStatus().isNotModified();
~~~

Đoạn trên minh họa trường hợp representation chưa thay đổi và endpoint thực sự xử lý conditional GET. Với update có điều kiện:

~~~java
client.put()
    .uri("/api/books/42")
    .header(HttpHeaders.IF_MATCH, "\"book-v42\"")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("title", "Tiêu đề mới"))
    .exchange()
    .expectStatus().isNoContent();
~~~

Status thành công tùy hợp đồng endpoint. Nếu ETag không khớp, server thường trả `412 Precondition Failed`; test cần xác nhận hành vi thực tế của ứng dụng. Khi tài liệu hóa các operation này, mô tả `If-None-Match`/`If-Match` bằng `requestHeaders(...)`, còn `ETag` bằng `responseHeaders(...)`.

## 10. Descriptor và snippet được sinh

Với hai operation trong ví dụ, snippet tiêu biểu có thể nằm dưới:

~~~text
build/generated-snippets/
└── books/
    ├── create/
    │   ├── http-request.adoc
    │   ├── request-headers.adoc
    │   ├── request-fields.adoc
    │   ├── http-response.adoc
    │   ├── response-headers.adoc
    │   └── response-fields.adoc
    └── get/
        ├── http-request.adoc
        ├── request-headers.adoc
        ├── http-response.adoc
        ├── response-headers.adoc
        └── response-fields.adoc
~~~

Tệp thực tế phụ thuộc loại request/response và descriptor. Asciidoctor có thể ghép chúng:

~~~asciidoc
= Books API
:snippets: build/generated-snippets

== Tạo sách
include::{snippets}/books/create/http-request.adoc[]
include::{snippets}/books/create/request-headers.adoc[]
include::{snippets}/books/create/request-fields.adoc[]
include::{snippets}/books/create/http-response.adoc[]
include::{snippets}/books/create/response-headers.adoc[]

== Đọc sách
include::{snippets}/books/get/http-request.adoc[]
include::{snippets}/books/get/request-headers.adoc[]
include::{snippets}/books/get/http-response.adoc[]
include::{snippets}/books/get/response-headers.adoc[]
include::{snippets}/books/get/response-fields.adoc[]
~~~

Tên operation trong `document("books/create", ...)` và `document("books/get", ...)` phải thống nhất với đường dẫn include.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân và hướng xử lý |
| --- | --- |
| Server trả 415 | `Content-Type` của request không được endpoint hỗ trợ hoặc body không khớp media type khai báo. |
| Server trả 406 | `Accept` yêu cầu representation mà endpoint không thể cung cấp. |
| POST trả 201 nhưng thiếu `Location` | Kiểm tra handler có tạo URI tài nguyên và đưa vào response header hay không. |
| `Location` khác giá trị tài liệu | Kiểm tra URI tương đối/tuyệt đối, context path và base URL; chuẩn hóa snippet nếu host test thay đổi. |
| ETag không khớp assertion | Kiểm tra representation, quy tắc tạo validator và dấu ngoặc kép/weak validator. |
| Conditional GET trả 200 thay vì 304 | Kiểm tra server có xử lý `If-None-Match` và validator có khớp representation hiện tại không. |
| Update có điều kiện không trả 412 | Kiểm tra handler/service thực thi `If-Match` và xử lý xung đột phiên bản. |
| Cache được lưu ngoài dự kiến | Kiểm tra `Cache-Control` ở response thực tế; phân biệt `no-cache` với `no-store` và xác định cache private/shared. |
| REST Docs báo thiếu header | Request/response chưa gửi header descriptor bắt buộc hoặc descriptor đặt sai phía. |
| Snippet không được tạo | Kiểm tra REST Docs filter, operation identifier và callback `consumeWith(document(...))`. |

## 12. Tích hợp Gradle và CI

Khi plugin Asciidoctor và task `asciidoctor` đã được cấu hình, nối task dựng tài liệu với test sinh snippet:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

CI có thể chạy:

~~~bash
./gradlew clean test asciidoctor
~~~

Test xác nhận status, header và payload; REST Docs kiểm tra descriptor và tạo snippet; Asciidoctor ghép tài liệu. Khi hợp đồng `Content-Type`, `Location`, `ETag` hoặc `Cache-Control` thay đổi, cần cập nhật test/descriptor cùng tài liệu. Với Markdown thuần, cần bước build riêng để nhúng hoặc liên kết snippet; cú pháp `include::` là của Asciidoctor.

## 13. Bài thực hành

1. Chạy hai test `books/create` và `books/get`, mở `request-headers.adoc` và `response-headers.adoc`.
2. Đổi `Content-Type` của request POST sang `text/plain` nhưng giữ JSON body; quan sát phản hồi khi endpoint chỉ nhận JSON, rồi khôi phục header đúng.
3. Thay URI `Location` trong controller và xác nhận `expectHeader().valueEquals(...)` phát hiện thay đổi.
4. Đổi ETag từ `"book-v42"` sang `"book-v43"`; kiểm tra test conditional GET dùng validator cũ phản ánh đúng trạng thái representation.
5. Thử `Cache-Control: no-store` và `private, max-age=60`; viết description phân biệt hai chính sách.
6. Thêm test `If-Match`/`If-None-Match`, mô tả request header và response `ETag` trong REST Docs.
7. Dựng Asciidoctor từ snippet mới và cho CI chạy test trước bước dựng tài liệu.

## 14. Ghi nhớ

- `Content-Type` mô tả kiểu body của message; `Accept` mô tả representation client muốn nhận.
- `Location` thường cho biết URI tài nguyên vừa tạo hoặc đích chuyển hướng.
- `ETag` là validator opaque của representation; client có thể gửi lại qua `If-None-Match` hoặc `If-Match` để dùng conditional request.
- `Cache-Control` chứa directive cho cache; cần giải thích đúng sự khác biệt giữa `no-store`, `no-cache`, `private`, `public` và `max-age`.
- Dùng `requestHeaders(...)` cho header client gửi và `responseHeaders(...)` cho header server trả.
- Assertion WebTestClient xác nhận hành vi; descriptor REST Docs mô tả header và kiểm tra hợp đồng trước khi snippet được đưa vào tài liệu.
- Build/CI phải chạy test trước Asciidoctor để tài liệu được tạo từ giao dịch HTTP vừa kiểm chứng.
