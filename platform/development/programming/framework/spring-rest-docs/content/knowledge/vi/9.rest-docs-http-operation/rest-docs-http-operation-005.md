# URI, query string và header trong request

## 1. Mục tiêu và bối cảnh

Trong **HTTP operation** của Spring REST Docs, request không chỉ có phương thức `GET`/`POST` và body mà còn chứa **URI**, **query string** và **HTTP request headers**. Đây là ba nguồn thông tin quyết định tài nguyên được truy cập, các tham số lọc/phân trang và cách client giao tiếp với API.

Bài học nằm trong module `SPRING_REST_DOCS`, với mục tiêu tạo **tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP** bằng MockMvc, WebTestClient hoặc REST Assured. Từ các request và response đã được kiểm thử, Spring REST Docs sinh snippet mô tả payload, tham số và header, rồi được đưa vào tài liệu Asciidoctor hoặc quy trình Markdown, build và CI.

Sau bài học, bạn sẽ có thể:

- Phân tích URI thành scheme, host, port, path và query; giải thích **fragment không được gửi tới server**.
- Phân biệt path variable, query parameter, HTTP header và form parameter.
- Tạo các snippet `path-parameters.adoc`, `query-parameters.adoc` và `request-headers.adoc` trong một bài kiểm thử MockMvc.
- Hiểu khi nào descriptor bắt buộc, `optional()`, `ignored()` hoặc chế độ `relaxed...` phù hợp.
- Tái hiện request bằng `curl`/HTTPie và nhận diện khác biệt do URL encoding, header mặc định, môi trường test.
- Xây dựng tài liệu có thể tái sinh từ test và phát hiện sai lệch trong CI.

## 2. Phân tích URI của một request

Xét một lời gọi đọc đánh giá sách:

~~~http
GET /api/books/42/reviews?page=0&size=10&sort=createdAt%2Cdesc HTTP/1.1
Host: api.example.com
Accept: application/json
X-Request-Id: docs-001
~~~

Với URL đầy đủ, một cách diễn giải là:

~~~text
https://api.example.com:443/api/books/42/reviews?page=0&size=10&sort=createdAt%2Cdesc
|___|   |_____________| |__| |___________________| |_________________________________|
scheme         host       port          path                        query
~~~

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Scheme | `https` | Giao thức truy cập tài nguyên; HTTPS kết hợp HTTP với TLS. |
| Host | `api.example.com` | Máy chủ hoặc tên miền nhận request. |
| Port | `443` | Cổng thường dùng cho HTTPS; nếu là cổng mặc định, URL hiển thị có thể lược bỏ. |
| Path | `/api/books/42/reviews` | Đường dẫn tới tập đánh giá của sách `42`. |
| Path variable | `42` trong mẫu `/api/books/{bookId}/reviews` | Giá trị cụ thể được thay vào mẫu route. |
| Query string | `page=0&size=10&sort=createdAt%2Cdesc` | Các tham số truy vấn sau dấu `?`. |
| Fragment | Ví dụ `#example` | Được client xử lý; **không** thuộc request target gửi tới HTTP server. |

**Một URI có thể có nhiều dạng biểu diễn**: trong mã test thường dùng path tương đối (`/api/books/...`); snippet dạng HTTP request thể hiện request target và headers; snippet `curl-request`/`httpie-request` có thể dùng URL tuyệt đối. Ba cách biểu diễn có thể mô tả **cùng một operation**.

### 2.1. URL, URI và URI template

Trong hướng dẫn API, cần phân biệt:

- **URI thật:** `/api/books/42/reviews` là đường dẫn cụ thể client gửi.
- **URI template:** `/api/books/{bookId}/reviews` mô tả endpoint nhận tham số đường dẫn.
- **URL có query:** `/api/books/42/reviews?page=0&size=10` nêu các điều kiện truy vấn cụ thể.
- **Route/controller mapping:** ví dụ `@GetMapping("/api/books/{bookId}/reviews")` xác định endpoint mà ứng dụng tiếp nhận.

Spring REST Docs tạo snippet từ **request đã chạy trong test**, không tự suy ra toàn bộ hợp đồng URI từ annotation controller. Khi sinh bảng path parameter, request builder phải lưu lại được **tên biến trong URI template**.

### 2.2. Path khác query như thế nào?

Một quy ước REST API thường gặp:

| Mục đích | Ví dụ | Nơi nên đặt |
| --- | --- | --- |
| Truy cập một tài nguyên xác định | `/api/books/42` | Path variable `bookId` |
| Truy cập tập tài nguyên con | `/api/books/42/reviews` | Path |
| Chọn trang kết quả | `?page=0&size=10` | Query |
| Sắp xếp kết quả | `?sort=createdAt,desc` | Query |
| Lọc theo thuộc tính | `?rating=5` | Query |
| Gửi dữ liệu tạo/cập nhật | JSON trong request body | Body, không nên nhồi vào query |
| Chỉ định cách biểu diễn | `Accept: application/json` | Request header |
| Gửi thông tin xác thực | `Authorization: Bearer ...` | Request header, theo sơ đồ xác thực API |

Đây là quy ước thiết kế hữu ích, không phải luật cứng quy định mọi API bắt buộc dùng cùng một cách đặt tham số. Dù chọn cách nào, tài liệu phải mô tả **đúng hợp đồng của endpoint**.

## 3. Query string: cú pháp, encoding và tham số lặp

Query string đứng sau dấu `?` và thường gồm các cặp `name=value` phân cách bằng `&`:

~~~text
/api/books?page=0&size=10&tag=java&tag=spring
~~~

Ở đây:

- `page` có giá trị `0`.
- `size` có giá trị `10`.
- `tag` xuất hiện hai lần, có thể được API diễn giải thành danh sách `["java", "spring"]` theo hợp đồng.
- Thứ tự parameter trong query thường không được xem là ý nghĩa nghiệp vụ, trừ khi endpoint quy định khác.

### 3.1. Những trường hợp cần mô tả rõ

| Trường hợp | Ví dụ | Điều cần xác định trong hợp đồng |
| --- | --- | --- |
| Tham số bắt buộc | `size=10` | Không có `size` thì xử lý ra sao? |
| Tham số tùy chọn | `sort=createdAt,desc` | Bỏ qua thì sắp xếp mặc định là gì? |
| Tham số lặp | `tag=java&tag=spring` | Gộp thành nhiều giá trị hay chỉ nhận một? |
| Tham số không có giá trị | `debug` hoặc `debug=` | API phân biệt “không có”, “rỗng” và “không xuất hiện” không? |
| Kiểu và phạm vi | `page=0`, `size=10` | Chỉ số bắt đầu từ mấy? Giới hạn `size` là bao nhiêu? |
| Chữ hoa/thường | `sort` khác `Sort` | Hệ thống có phân biệt tên tham số không? |
| Ký tự đặc biệt | `q=Spring%20REST%20Docs` | URL encoding và cách giải mã tại server thế nào? |

Tên tham số và value nên được URL-encode theo quy tắc URI, nhất là khi chứa khoảng trắng, dấu `&`, `=` hoặc Unicode. `%20` là cách mã hóa khoảng trắng trong URI; trong quy tắc mã hóa biểu mẫu `application/x-www-form-urlencoded`, dấu `+` thường được diễn giải là khoảng trắng. Đừng giả định mọi API sẽ xử lý `+` và `%20` giống nhau trong mọi bối cảnh.

**Phân biệt giá trị thật và ví dụ hiển thị:** trong test, `queryParam("sort", "createdAt,desc")` diễn tả giá trị sau khi được API client xử lý; biểu diễn trên URL có thể là `createdAt,desc` hoặc một dạng percent-encoded tương đương. Kiểm tra `http-request.adoc` được sinh khi cần đối chiếu chính xác.

### 3.2. Tránh đưa dữ liệu bí mật vào query

Query string dễ xuất hiện trong browser history, access log, reverse proxy, công cụ giám sát và hệ thống cache. Vì vậy, không nên đưa password, access token hoặc dữ liệu cá nhân nhạy cảm vào query string. Dùng cơ chế xác thực và phân quyền thích hợp; trong test tài liệu hóa chỉ dùng dữ liệu giả.

## 4. Request header là gì?

Header là các trường metadata đi kèm HTTP request. Cú pháp minh họa:

~~~http
GET /api/books/42/reviews?page=0 HTTP/1.1
Host: api.example.com
Accept: application/json
Authorization: Bearer <example-token>
X-Request-Id: docs-001
If-None-Match: "v1"
~~~

| Header | Ý nghĩa thường gặp | Khi tài liệu hóa |
| --- | --- | --- |
| `Host` | Authority mà HTTP/1.1 request hướng tới | Thường do HTTP client thiết lập; không nhầm với path variable. |
| `Accept` | Media type của response được client ưu tiên | Ví dụ `application/json`. |
| `Content-Type` | Media type của **request body** | Ví dụ `application/json` khi gửi JSON; không mặc định cần có với GET không body. |
| `Authorization` | Credential theo sơ đồ xác thực | Chỉ giải thích cách dùng; không ghi token thật. |
| `X-Request-Id` | Ví dụ header nghiệp vụ/quan sát dùng để liên kết log | Có thể là header tự quy định; không tự động thuộc chuẩn HTTP. |
| `If-None-Match` | Điều kiện dựa trên ETag phục vụ conditional request | Nếu hợp đồng hỗ trợ cache có điều kiện, cần test nhánh `304`. |
| `If-Match` | Điều kiện cập nhật dựa trên ETag | Có thể phối hợp `PUT`/`PATCH` để kiểm soát cập nhật đồng thời. |
| `Idempotency-Key` | Một số API quy định để hạn chế xử lý lại lệnh có tác dụng phụ | Chỉ dùng khi endpoint thực sự hỗ trợ; mô tả phạm vi và thời hạn key. |

Tên HTTP field nhìn chung **không phân biệt chữ hoa/thường** theo ngữ nghĩa giao thức, ví dụ `Accept` và `accept` là cùng tên header; tuy nhiên giá trị của từng header cần được hiểu theo cú pháp và quy tắc riêng. Một số header cho phép nhiều giá trị hoặc nhiều dòng field tương đương, nhưng không thể gộp bằng dấu phẩy một cách an toàn với mọi header (ví dụ `Set-Cookie`).

### 4.1. `Accept` khác `Content-Type`

- `Accept: application/json`: client mong **nhận response** ở dạng JSON.
- `Content-Type: application/json`: **request body được gửi** là JSON.

Một request `GET` không có body thường chỉ cần `Accept` nếu cần thương lượng media type. Một request `POST` JSON có thể cần cả hai. Không nên thêm `Content-Type` vào mọi GET chỉ để lệnh trong tài liệu trông “đầy đủ”.

### 4.2. Header do test thiết lập và header do HTTP client thêm

MockMvc hoạt động trong môi trường giả lập Servlet, WebTestClient có thể bind vào ứng dụng hoặc server, còn REST Assured có thể gọi qua mạng tới server thật. Vì thế các header mặc định như `Host`, `User-Agent`, `Content-Length` và encoding có thể khác nhau. Header xuất hiện trong snippet cần được xem là **kết quả quan sát của client và cấu hình test cụ thể**, không phải lời cam kết mọi client sẽ gửi y hệt.

## 5. Phân biệt path, query, header và form/body

Việc chọn đúng descriptor rất quan trọng vì Spring REST Docs có các API khác nhau:

| Vị trí thông tin | Request ví dụ | Descriptor | Snippet được sinh |
| --- | --- | --- | --- |
| Path variable | `/api/books/42` với `/api/books/{bookId}` | `pathParameters(parameterWithName("bookId")...)` | `path-parameters.adoc` |
| Query parameter | `?page=0&size=10` | `queryParameters(parameterWithName("page")...)` | `query-parameters.adoc` |
| Request header | `Accept: application/json` | `requestHeaders(headerWithName("Accept")...)` | `request-headers.adoc` |
| Form field | Body `application/x-www-form-urlencoded` | `formParameters(parameterWithName("name")...)` | `form-parameters.adoc` |
| JSON body field | Body `{"name":"Lan"}` | `requestFields(fieldWithPath("name")...)` | `request-fields.adoc` |

**Không dùng `queryParameters` cho JSON body** và cũng không dùng `requestFields` cho `?page=0`. Một parameter xuất hiện trong query string khác với một trường JSON, kể cả khi chúng có cùng tên `page`.

### Query parameter khác form parameter

Ví dụ request tạo tài nguyên bằng form:

~~~http
POST /api/books/search HTTP/1.1
Content-Type: application/x-www-form-urlencoded

title=Spring
~~~

`title` là **form parameter trong request body**, không phải query parameter trên URL. Trong MockMvc, `param(...)` có thể được dùng để gán parameter cho form; còn để ghi query rõ ràng, nên dùng `queryParam(...)` hoặc đưa tham số vào URI. Tài liệu Spring REST Docs khuyến nghị tránh dùng `param(...)` làm nguồn query vì vị trí tham số trở nên mơ hồ.

## 6. Bài kiểm thử MockMvc: URI, query và header trong cùng operation

### 6.1. Giả định và dependency

Ví dụ dùng **Spring Boot 3.x, Spring MVC, JUnit 5 và Java 17+**. Dự án cần starter test cùng module Spring REST Docs dành cho MockMvc:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Giả sử ứng dụng đã triển khai:

~~~text
GET /api/books/{bookId}/reviews
~~~

Hợp đồng minh họa: sách `42` có dữ liệu kiểm thử, endpoint nhận ba query parameters `page`, `size`, `sort` và header `X-Request-Id`, trả `200 OK` với `Content-Type` tương thích JSON. Các giá trị và status là **giả định dành cho bài học**; Spring REST Docs không tự tạo endpoint hoặc fixture.

### 6.2. Một test tự chứa

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
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
class BookReviewDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentListBookReviews() throws Exception {
        mockMvc.perform(get("/api/books/{bookId}/reviews", 42)
                .queryParam("page", "0")
                .queryParam("size", "10")
                .queryParam("sort", "createdAt,desc")
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", "docs-001"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andDo(document("book-reviews-list",
                pathParameters(
                    parameterWithName("bookId")
                        .description("Mã sách cần lấy đánh giá")
                ),
                queryParameters(
                    parameterWithName("page")
                        .description("Trang cần lấy, bắt đầu từ 0"),
                    parameterWithName("size")
                        .description("Số đánh giá tối đa mỗi trang"),
                    parameterWithName("sort")
                        .description("Thứ tự sắp xếp, ví dụ createdAt,desc")
                ),
                requestHeaders(
                    headerWithName(HttpHeaders.ACCEPT)
                        .description("Media type mong muốn của response"),
                    headerWithName("X-Request-Id")
                        .description("Mã theo dõi request từ client")
                )
            ));
    }
}
~~~

Trong lớp kiểm thử này:

1. `RestDocumentationRequestBuilders.get("/api/books/{bookId}/reviews", 42)` ghi lại URI template với biến `bookId`. Lựa chọn builder này tương thích cả các dự án dùng Spring Framework 6.1 trở về trước, nơi `MockMvcRequestBuilders` không cung cấp đủ metadata path parameter cho REST Docs.
2. `queryParam(...)` tạo query string rõ ràng. Những tham số được khai báo trong `queryParameters(...)` có thể được đối chiếu với query thực tế.
3. `accept(...)` và `header(...)` thiết lập request headers mà API nhận.
4. `andExpect(...)` xác nhận kết quả trước khi đến `document(...)`.
5. `document("book-reviews-list", ...)` vừa tạo các snippet mặc định vừa sinh **ba bảng mô tả path, query và headers** từ những descriptor.
6. `@AutoConfigureRestDocs` chọn URI hiển thị trong tài liệu. Host `api.example.com` là ví dụ, không phải server được MockMvc tự chạy.

**Chú ý về test:** ví dụ chỉ assert status và Content-Type; trong dự án thật, nên thêm assertion về cấu trúc response body, sort và pagination phù hợp hợp đồng. Các descriptor của request kiểm chứng **sự hiện diện của metadata** theo quy tắc REST Docs, không tự kiểm chứng thuật toán phân trang/sắp xếp của ứng dụng.

## 7. Snippet được tạo ra và cách đọc chúng

Sau khi test đạt, có thể thấy:

~~~text
build/generated-snippets/
└── book-reviews-list/
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    ├── path-parameters.adoc
    ├── query-parameters.adoc
    └── request-headers.adoc
~~~

Sáu tệp đầu là snippet mặc định phổ biến. Ba tệp cuối do chúng ta khai báo `pathParameters`, `queryParameters` và `requestHeaders`. Tập tệp thực tế có thể thay đổi khi dự án tùy chỉnh default snippets hoặc template.

### 7.1. `http-request.adoc`: request thực tế

Một nội dung **minh họa** có thể là:

~~~http
GET /api/books/42/reviews?page=0&size=10&sort=createdAt%2Cdesc HTTP/1.1
Accept: application/json
X-Request-Id: docs-001
Host: api.example.com
~~~

Dạng percent-encoding của dấu phẩy, thứ tự headers và việc xuất hiện `Host` phụ thuộc cách client xây dựng request và template. Không nên dựa vào ví dụ này để khẳng định file sinh ra phải giống byte-for-byte. Mở chính `http-request.adoc` sau khi chạy test.

### 7.2. `path-parameters.adoc`

Snippet dạng bảng có thể có nội dung tương đương:

| Parameter | Description |
| --- | --- |
| `bookId` | Mã sách cần lấy đánh giá. |

Đây là bảng **mô tả tên biến** trong URI template. Nó không thay `bookId` bằng `42` trong cột tên; `42` là giá trị được sử dụng ở request minh họa.

### 7.3. `query-parameters.adoc`

| Parameter | Description |
| --- | --- |
| `page` | Trang cần lấy, bắt đầu từ 0. |
| `size` | Số đánh giá tối đa mỗi trang. |
| `sort` | Thứ tự sắp xếp, ví dụ `createdAt,desc`. |

Để tài liệu đủ sử dụng, nên nói rõ default, giới hạn trên/dưới, giá trị cho phép, cách xử lý tham số lặp lại và status lỗi với tham số sai. REST Docs chỉ kiểm tra descriptor theo request test, không tự suy diễn các ràng buộc nghiệp vụ này.

### 7.4. `request-headers.adoc`

| Header | Description |
| --- | --- |
| `Accept` | Media type mong muốn của response. |
| `X-Request-Id` | Mã theo dõi request từ client. |

`requestHeaders(...)` kiểm tra rằng các **header đã khai báo và không optional** có trong request. Nó **không buộc toàn bộ header khác cũng phải được liệt kê**. Điều này khác với việc kiểm tra mặc định của `queryParameters(...)` và `pathParameters(...)`, vốn có thể thất bại khi gặp parameter chưa được mô tả.

## 8. Kiểm chứng bằng descriptor: strict, optional, ignored, relaxed

Đây là điểm dễ gây hiểu nhầm khi đưa REST Docs vào CI.

### 8.1. Path và query parameters: kiểm chứng hai chiều

Với `pathParameters(...)` hoặc `queryParameters(...)` theo chế độ thông thường:

- Có parameter **xuất hiện trong request** nhưng không có descriptor phù hợp → bước sinh snippet có thể thất bại.
- Có descriptor parameter **bắt buộc** nhưng parameter không xuất hiện → bước sinh snippet thất bại.
- Descriptor có `.optional()` được phép không xuất hiện trong request.
- Descriptor có `.ignored()` không hiển thị trong snippet, nhưng REST Docs vẫn biết parameter đó đã được khai báo/được phép bỏ khỏi bảng.
- `relaxedPathParameters(...)` hoặc `relaxedQueryParameters(...)` bỏ qua parameter chưa được mô tả; descriptor được khai báo là bắt buộc vẫn phải được đáp ứng.

Ví dụ một query `language` không bắt buộc:

~~~java
queryParameters(
    parameterWithName("page")
        .description("Trang bắt đầu từ 0"),
    parameterWithName("language")
        .description("Mã ngôn ngữ lọc đánh giá, ví dụ vi")
        .optional()
)
~~~

Nếu test chỉ gửi `page`, descriptor `language` vẫn hợp lệ vì được đánh dấu optional. Khi tài liệu hóa một nhánh cụ thể nhưng muốn bỏ qua tham số hệ thống như `trace`, có thể dùng `ignored()`; cần cân nhắc liệu việc ẩn tham số đó có khiến người đọc thiếu kiến thức cần thiết hay không.

### 8.2. Request headers: kiểm tra descriptor được khai báo

Với `requestHeaders(...)`:

- Header descriptor không optional mà **thiếu trong request** → lỗi sinh snippet.
- Header optional có thể không xuất hiện.
- Header bổ sung chưa được khai báo **không mặc nhiên làm test fail**; vì vậy không nên suy ra request chỉ có các headers được liệt kê.

Ví dụ mô tả header tùy chọn:

~~~java
requestHeaders(
    headerWithName(HttpHeaders.ACCEPT)
        .description("Media type của response"),
    headerWithName("X-Request-Id")
        .description("Mã theo dõi request")
        .optional()
)
~~~

Điều này hữu ích với API mà client có thể không gửi `X-Request-Id`. Cần viết rõ ai sinh correlation ID mặc định và khi nào header được dùng để tra cứu log.

### 8.3. Descriptor không tự kiểm tra giá trị nghiệp vụ

Một descriptor như:

~~~java
parameterWithName("size").description("Số mục từ 1 đến 100")
~~~

không tự chứng minh server từ chối `size=1000`. Để kiểm chứng hợp đồng, cần **thêm HTTP tests riêng** cho biên hợp lệ và không hợp lệ, assert status/body/error code tương ứng. Với headers cũng tương tự: mô tả `Accept` là `application/json` không thay thế test trả `406 Not Acceptable` khi client yêu cầu media type không được hỗ trợ.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Test tạo request URI/query/headers"] --> B["Ứng dụng trả response"]
    B --> C{"Assertions status/body đạt?"}
    C -->|Không| D["Test fail"]
    C -->|Có| E["Spring REST Docs xử lý descriptors"]
    E --> F{"Các descriptor hợp lệ?"}
    F -->|Không| D
    F -->|Có| G["Sinh snippets"]
    G --> H["Asciidoctor/CI dựng tài liệu"]
~~~

Đây là trình tự ở ví dụ MockMvc khi `andExpect(...)` đứng trước `andDo(document(...))`. Với REST Assured, filter ghi operation có thể chạy trước assertion cuối; chỉ nên phát hành khi **toàn bộ test suite pass**.

## 9. Các nhầm lẫn thực tế với `queryParam`, `param` và form body

### 9.1. Cách rõ ràng để tạo query trong MockMvc

Nên dùng một trong hai cách sau.

**Cách A: viết query ngay trong URI**:

~~~java
mockMvc.perform(get("/api/books/42/reviews?page=0&size=10"));
~~~

**Cách B: dùng request builder**:

~~~java
mockMvc.perform(get("/api/books/42/reviews")
    .queryParam("page", "0")
    .queryParam("size", "10"));
~~~

Trong code hiện đại, `queryParam` hoặc `queryParams` giúp Spring REST Docs xác định nguồn dữ liệu là **query string**. Tránh dùng `param("page", "0")` cho query khi không rõ đó là query hay form parameter; cách dùng này có thể làm tài liệu không khớp request line kỳ vọng.

### 9.2. Form data nằm ở body

Giả sử một endpoint minh họa tiếp nhận `application/x-www-form-urlencoded`:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// Đoạn method đặt trong lớp đã cấu hình MockMvc và REST Docs:
@Test
void documentFormSearch() throws Exception {
    mockMvc.perform(post("/api/books/search")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("title", "Spring"))
        .andExpect(status().isOk())
        .andDo(document("books-form-search",
            formParameters(
                parameterWithName("title")
                    .description("Tên sách cần tìm")
            )
        ));
}
~~~

Kết quả `form-parameters.adoc` mô tả trường `title` trong form body. `query-parameters.adoc` sẽ không phải snippet thích hợp cho trường hợp này. Lưu ý tên API minh họa có thể không tối ưu về REST design; mục tiêu ở đây là thấy **sự khác biệt vị trí dữ liệu**.

### 9.3. JSON body là một loại khác

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json

{"title":"Spring in Action"}
~~~

Với request này, dùng `requestFields(fieldWithPath("title")...)` để mô tả JSON field, không dùng `formParameters(...)` hoặc `queryParameters(...)`.

## 10. Headers và content negotiation: ví dụ riêng

Giả sử API hỗ trợ JSON response. Một test chỉ rõ client muốn JSON:

~~~java
mockMvc.perform(get("/api/books/42")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andDo(document("books-get-json",
        requestHeaders(
            headerWithName(HttpHeaders.ACCEPT)
                .description("Kiểu response được client chấp nhận")
        )
    ));
~~~

Đoạn này đặt trong class đã cấu hình REST Docs. `Accept` chỉ là request header; nội dung JSON thực tế thuộc response và cần assert riêng, ví dụ qua `jsonPath` hoặc `responseFields`.

Tương tự, khi gửi `POST` có body JSON, cần xác nhận:

~~~java
mockMvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Spring in Action\"}"))
    .andExpect(status().isCreated())
    .andDo(document("books-create-json",
        requestHeaders(
            headerWithName(HttpHeaders.CONTENT_TYPE)
                .description("Media type của request body"),
            headerWithName(HttpHeaders.ACCEPT)
                .description("Media type response mong muốn")
        )
    ));
~~~

Đây là ví dụ cho **một endpoint giả định trả `201`**; muốn test hoàn chỉnh cần chuẩn bị fixture/controller và bổ sung assertion cần thiết về `Location` hoặc response body theo hợp đồng của dự án.

## 11. Làm sạch URI và headers trước khi đưa vào tài liệu

Snippet có thể vô tình làm lộ hostname nội bộ, cookie, token hoặc mã định danh cá nhân. Kiểm thử và tài liệu nên sử dụng dữ liệu giả có chủ đích.

### 11.1. Chuẩn hóa hostname và port

Khi dùng MockMvc với Spring Boot 3.x, có thể cấu hình:

~~~java
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
~~~

Host và port này chỉ ảnh hưởng cách Spring REST Docs **trình bày URI** trong snippet; nó không tự tạo HTTP server tại `api.example.com`. Nếu cần gọi lại bằng `curl` hoặc HTTPie, phải thay bằng URL môi trường thực đang truy cập được.

Với WebTestClient bind vào ứng dụng, có thể cấu hình base URL trên builder dùng cho tài liệu. Với client chạy trên server thật, REST Docs cũng có request preprocessor `modifyUris()` để chuẩn hóa host, scheme và port trong bản ghi dùng sinh snippet.

### 11.2. Thay giá trị secret bằng placeholder

Nếu header `Authorization` thực sự được test gửi và cần được giữ lại trong tài liệu, có thể **thay giá trị chỉ trong snippet**:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

// Thay lời gọi .andDo(document(...)) của một test có Authorization:
.andDo(document("secured-books-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <redacted>")
    ),
    requestHeaders(
        headerWithName(HttpHeaders.AUTHORIZATION)
            .description("Token truy cập của người dùng đã xác thực")
    )
));
~~~

Khi chạy test, request thực tế vẫn dùng credential/fixture theo cấu hình test; preprocessor chỉ làm sạch **bản ghi dùng sinh tài liệu**. Đoạn code giả định test đã gửi `Authorization`, và identifier là minh họa. Nó là một **lời gọi thay thế**, không ghép vào test đã có `document("secured-books-get", ...)`.

Nếu hoàn toàn không muốn lộ header, có thể dùng `modifyHeaders().remove("Authorization")`, nhưng khi đó không đồng thời khai báo `headerWithName("Authorization")` là bắt buộc trong `requestHeaders(...)` vì nó đã bị bỏ khỏi bản ghi đưa vào snippet. Cần diễn giải rõ yêu cầu authentication ngoài lệnh minh họa để người đọc hiểu vì sao request tái hiện có thể bị `401`.

### 11.3. Điều không nên dùng URI/header preprocessing để làm

- Không biến một query string chứa password thật thành “an toàn” chỉ bằng che một phần trên trang tài liệu; hãy **ngăn fixture chứa secret ngay từ đầu**.
- Không ghi rằng URL được test có thể truy cập từ Internet chỉ vì snippet dùng host công khai.
- Không sửa giá trị header trong snippet rồi lấy đó làm bằng chứng hệ thống đã xử lý giá trị đã sửa.
- Không dùng preprocessor để che lỗi hành vi; cần assertions ở lớp test trước khi sinh tài liệu.

## 12. WebTestClient và REST Assured

Cùng một hợp đồng path/query/header có thể được test bằng client khác. Điểm khác nhau là cách xây request và gắn filter hoặc consumer sinh snippet.

### 12.1. WebTestClient

Giả sử `webTestClient` đã được cấu hình tích hợp Spring REST Docs và endpoint GET trả `200`:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
    .uri("/api/books/{bookId}/reviews?page=0&size=10", 42)
    .accept(MediaType.APPLICATION_JSON)
    .header("X-Request-Id", "docs-001")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("book-reviews-webtestclient",
        pathParameters(
            parameterWithName("bookId").description("Mã sách")
        ),
        queryParameters(
            parameterWithName("page").description("Chỉ số trang"),
            parameterWithName("size").description("Số mục mỗi trang")
        ),
        requestHeaders(
            headerWithName("X-Request-Id")
                .description("Mã theo dõi request")
        )
    ));
~~~

URI template được WebTestClient giữ lại để `pathParameters(...)` có thể mô tả `bookId`. Dùng module `spring-restdocs-webtestclient` và cấu hình REST Docs tương ứng với bản Spring đang dùng.

### 12.2. REST Assured

Với REST Assured, request thường được gửi tới một HTTP server thật. Một ví dụ minh họa qua `RequestSpecification` đã cấu hình REST Docs:

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;

// spec: RequestSpecification có cấu hình server test và REST Docs.
given(spec)
    .filter(document("book-reviews-restassured",
        queryParameters(
            parameterWithName("page").description("Chỉ số trang")
        ),
        requestHeaders(
            headerWithName("X-Request-Id")
                .description("Mã theo dõi request")
        )
    ))
    .queryParam("page", "0")
    .header("X-Request-Id", "docs-001")
.when()
    .get("/api/books/42/reviews")
.then()
    .statusCode(200);
~~~

Module tích hợp là `spring-restdocs-restassured`, và filter/documentation context cần được cấu hình theo phiên bản dự án. Trong ví dụ này URI đã chứa **giá trị `42` cụ thể**, nên ta chỉ mô tả query/header; không tự khẳng định filter luôn nắm được tên URI template `bookId` như trong hai client dùng URI template phía trên.

Filter có thể ghi operation khi request được thực hiện, trước lúc assertion `statusCode(200)` chạy. Vì vậy CI phải yêu cầu **test PASS** trước khi xuất bản snippets.

### 12.3. So sánh

| Công cụ | Xây URI và query | Xây header | Tạo snippet |
| --- | --- | --- | --- |
| MockMvc | `get("/path/{id}", id).queryParam(...)` | `accept(...)`, `header(...)` | `.andDo(document(...))` |
| WebTestClient | `.uri("/path/{id}?page=0", id)` | `.accept(...)`, `.header(...)` | `.expectBody().consumeWith(document(...))` |
| REST Assured | `.get("/path")` kết hợp `.queryParam(...)` | `.header(...)`, `.accept(...)` | Filter `document(...)` |

## 13. Biên soạn tài liệu từ các snippet

Trong một tệp Asciidoctor, có thể kết hợp request thô, bảng URI/query/header và response:

~~~asciidoc
= Books API

== Danh sách đánh giá của một cuốn sách

=== HTTP request
include::{snippets}/book-reviews-list/http-request.adoc[]

=== Path parameters
include::{snippets}/book-reviews-list/path-parameters.adoc[]

=== Query parameters
include::{snippets}/book-reviews-list/query-parameters.adoc[]

=== Request headers
include::{snippets}/book-reviews-list/request-headers.adoc[]

=== HTTP response
include::{snippets}/book-reviews-list/http-response.adoc[]

=== Thử bằng curl
include::{snippets}/book-reviews-list/curl-request.adoc[]
~~~

Thuộc tính `snippets` phải được cấu hình để trỏ đến thư mục sinh snippet như `build/generated-snippets`. Đây là ví dụ cho Asciidoctor; nếu dự án xuất tài liệu Markdown, cần cấu hình template/chuyển đổi phù hợp vì Markdown renderer thông thường không hiểu trực tiếp chỉ thị `include::{snippets}/...[]`.

Luồng CI:

~~~mermaid
flowchart LR
    A["HTTP tests + assertions"] --> B["Sinh snippets từ operation"]
    B --> C["Asciidoctor lấy snippets"]
    C --> D["Tạo HTML/PDF hoặc artifact tài liệu"]
    D --> E["Publish khi pipeline PASS"]
~~~

Nên cấu hình tác vụ build tài liệu phụ thuộc vào tác vụ test sinh snippet, kiểm soát output directory và đường dẫn include. Nếu snippet cũ còn sót nhưng test tương ứng đã bị xóa hoặc không chạy, build có thể đưa nội dung lỗi thời vào tài liệu; vì vậy cần bảo đảm artifact phản ánh **lần kiểm thử hiện hành**.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `path-parameters.adoc` không được sinh | Không có `pathParameters(...)` hoặc không giữ metadata URI template | Dùng request builder phù hợp và khai báo descriptor. |
| `pathParameters` báo thiếu `bookId` | Request được tạo từ path có giá trị cứng thay vì URI template | Dùng `RestDocumentationRequestBuilders.get("/.../{bookId}", 42)` trong MockMvc. |
| `query-parameters.adoc` trống hoặc test fail | Dùng `param(...)` khiến nguồn tham số mơ hồ; query không thực sự có trong URI | Dùng `queryParam(...)` hoặc query string trực tiếp trong URI. |
| REST Docs báo query parameter chưa được mô tả | Có parameter trong request nhưng thiếu descriptor ở chế độ strict | Bổ sung mô tả đúng; chỉ dùng `relaxedQueryParameters` khi có chủ đích. |
| Descriptor query thiếu nhưng test vẫn chạy | Có `optional()` hoặc dùng relaxed mode | Kiểm tra ý định tài liệu; không đặt optional cho tham số thực sự bắt buộc. |
| `request-headers.adoc` thiếu header tự động | Chỉ các headers được khai báo descriptor mới có dòng mô tả | Thêm descriptor nếu header quan trọng đối với hợp đồng. |
| Header descriptor tồn tại nhưng header không có | Client test không gửi header hoặc preprocessing đã xóa nó | Sửa request builder/descriptor hoặc giữ header khi mask. |
| `Accept` đúng nhưng response không phải JSON | Kiểm thử chỉ kiểm tra header request | Thêm assertion `Content-Type` và payload response. |
| URL chứa khoảng trắng/dấu `&` gây sai request | Thiếu percent-encoding hoặc shell xử lý ký tự đặc biệt | Dùng URI builder/queryParam hoặc encode và quote URL đúng shell. |
| `curl-request` gọi sai host | URI hiển thị là host mẫu từ cấu hình MockMvc | Dùng server thử thật và giải thích cách thay URL. |
| Header/token bị lộ trên docs | Fixture có secret, thiếu masking | Dùng dữ liệu giả và preprocessing phù hợp trước khi sinh snippet. |
| CI vẫn publish khi test lỗi | Pipeline dùng snippet cũ hoặc không phụ thuộc test | Buộc build docs phụ thuộc test và kiểm soát artifacts. |

## 15. Bài thực hành

Xây dựng tài liệu cho endpoint giả định:

~~~text
GET /api/orders/{orderId}/events?type=PAYMENT&page=0&size=20
~~~

Client gửi headers:

~~~http
Accept: application/json
X-Request-Id: exercise-001
~~~

Bài thực hành gồm các yêu cầu:

1. Viết HTTP test có URI template `{orderId}`, truyền giá trị `101`, query `type`/`page`/`size` và hai headers trên.
2. Assert status `200 OK`, `Content-Type` JSON và ít nhất một trường response quan trọng theo hợp đồng giả định.
3. Tạo `path-parameters.adoc` mô tả `orderId`, `query-parameters.adoc` mô tả ba query params và `request-headers.adoc` mô tả `Accept`, `X-Request-Id`.
4. Thêm trường query tùy chọn `sort` bằng `.optional()`; chạy test không gửi `sort` và kiểm chứng snippet vẫn được sinh.
5. Cố ý gửi một query chưa khai báo, ví dụ `debug=true`, để xem hành vi strict; sau đó bổ sung descriptor hoặc đánh giá việc bỏ qua tham số này.
6. So sánh `http-request.adoc` và `curl-request.adoc` để hiểu request target, host và headers được trình bày thế nào.
7. Include snippets vào Asciidoctor và xác nhận pipeline chỉ publish sau khi test pass.

**Tiêu chí hoàn thành:** phân biệt đúng path/query/header/form/JSON, sinh đủ ba bảng mô tả, hiểu quy tắc strict/optional/ignored, dùng URI template chính xác và giữ được quy trình tài liệu hóa dựa trên bài test chạy thành công.

## Tài liệu tham khảo chính thức

- [Spring REST Docs — Path Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
