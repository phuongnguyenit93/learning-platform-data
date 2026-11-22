# Content-Type và Accept trong tài liệu

## 1. Mục tiêu và bối cảnh

Khi một HTTP client gọi REST API, hai header thường quyết định cách dữ liệu được trao đổi là **`Content-Type`** và **`Accept`**. Chúng đều liên quan đến media type, nhưng mô tả hai chiều khác nhau:

- `Content-Type` cho biết **body của message hiện tại được biểu diễn theo định dạng nào**.
- `Accept` cho biết **client có thể nhận những media type nào trong response**.

Nếu nhầm hai header này, request có thể bị server từ chối, server chọn response representation không như mong đợi hoặc tài liệu API mô tả sai hợp đồng. Đây là nội dung thuộc chương **HTTP operation** của `SPRING_REST_DOCS`.

Module `SPRING_REST_DOCS` hướng tới việc tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; sau đó biên soạn bằng Asciidoctor/Markdown và tích hợp vào build, CI.

Sau bài học, bạn có thể:

- Phân biệt vai trò của `Content-Type` và `Accept` trong request/response.
- Đọc media type, subtype, parameter, charset và wildcard trong header.
- Liên hệ `consumes`/`produces` với quá trình chọn handler và content negotiation trong Spring MVC.
- Viết test cho JSON, XML, `406 Not Acceptable` và `415 Unsupported Media Type`.
- Sinh snippet `http-request`, `http-response`, `request-headers` và các bảng payload từ test.
- Tích hợp các ví dụ vào tài liệu và phát hiện thay đổi hợp đồng trong CI.

## 2. `Content-Type`: body hiện tại có định dạng gì?

Header `Content-Type` khai báo **media type của representation trong message body**. Ví dụ client gửi JSON:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json

{"title":"Spring in Action","price":199000}
~~~

Ở đây, `application/json` mô tả định dạng body mà client gửi. Server dựa vào thông tin này cùng cấu hình handler/converter để diễn giải payload.

Nếu body là XML:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/xml

<book><title>Spring in Action</title></book>
~~~

Media type đã thay đổi; payload phải thực sự phù hợp với định dạng được khai báo. Chỉ đổi header từ `application/json` thành `application/xml` mà vẫn giữ body JSON không làm JSON biến thành XML.

### 2.1. Media type có cấu trúc ra sao?

Một media type thông dụng có dạng:

~~~text
type/subtype; parameter=value
~~~

Ví dụ:

~~~http
Content-Type: application/json; charset=UTF-8
~~~

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Type | `application` | Nhóm media type cấp cao. |
| Subtype | `json` | Dạng representation cụ thể. |
| Parameter | `charset=UTF-8` | Tham số bổ sung theo cú pháp media type. |

Các ví dụ thường gặp:

| Media type | Dạng dữ liệu | Tình huống |
| --- | --- | --- |
| `application/json` | JSON | API trao đổi object, array, dữ liệu nghiệp vụ. |
| `application/problem+json` | Problem Details dạng JSON | Biểu diễn lỗi HTTP theo hợp đồng Problem Details. |
| `application/xml` | XML | API cần trao đổi XML. |
| `application/x-www-form-urlencoded` | Form URL-encoded | Form có các cặp tên/giá trị trong body. |
| `multipart/form-data` | Multipart | Upload file và các trường form. |
| `text/plain` | Văn bản thuần | API nhận/trả nội dung text. |
| `application/octet-stream` | Byte stream | Nội dung nhị phân không gắn định dạng đặc thù. |

**Lưu ý về charset:** JSON trao đổi qua HTTP hiện đại được định nghĩa bằng UTF-8; không cần thêm `charset=UTF-8` trong mọi request JSON. Một số framework có thể sinh tham số charset trong header hoặc biểu diễn khác tùy converter/cấu hình. Hãy kiểm tra media type theo hợp đồng thực tế thay vì bắt buộc một chuỗi header cứng không cần thiết.

### 2.2. Khi nào request cần `Content-Type`?

Một request có body thường cần chỉ rõ định dạng để server biết cách đọc body. Ví dụ:

- `POST` gửi JSON: `Content-Type: application/json`.
- `PUT` gửi XML: `Content-Type: application/xml`.
- Upload file: `Content-Type: multipart/form-data; boundary=...` do client multipart tạo.
- Form URL-encoded: `Content-Type: application/x-www-form-urlencoded`.

Một request `GET` không có body thường không cần `Content-Type`. Không nên thêm header này vào mọi request theo thói quen; nó có ý nghĩa khi body cần được diễn giải.

## 3. `Accept`: client muốn nhận representation nào?

`Accept` là request header dùng trong **content negotiation**. Client liệt kê media type mà nó có thể xử lý:

~~~http
GET /api/books/42 HTTP/1.1
Accept: application/json
~~~

Nghĩa là client ưu tiên hoặc chấp nhận response dạng JSON. Nếu API cung cấp nhiều representation, server có thể chọn một dạng phù hợp. Header `Accept` không khẳng định server chắc chắn sẽ trả JSON: API phải hỗ trợ representation đó, và quá trình chọn còn phụ thuộc các điều kiện khác.

### 3.1. Một số dạng giá trị `Accept`

| Giá trị | Ý nghĩa |
| --- | --- |
| `application/json` | Chỉ định dạng JSON. |
| `application/xml` | Chỉ định dạng XML. |
| `application/json, application/xml` | Client chấp nhận JSON hoặc XML; server chọn theo quy tắc content negotiation và ưu tiên. |
| `application/*` | Chấp nhận các subtype thuộc type `application`. |
| `*/*` | Chấp nhận mọi media type. |
| `application/json;q=1.0, application/xml;q=0.8` | Cùng liệt kê hai lựa chọn và nêu trọng số ưu tiên tương đối. |

Tham số `q` (quality value) có giá trị từ `0` đến `1`, biểu thị mức ưu tiên của media range trong quá trình thương lượng. Nếu client không gửi `Accept`, server áp dụng hành vi mặc định theo HTTP và framework/cấu hình; không nên tự suy diễn client chỉ chấp nhận JSON.

Ví dụ:

~~~http
GET /api/books/42 HTTP/1.1
Accept: application/xml;q=0.9, application/json;q=1.0
~~~

Client ưu tiên JSON cao hơn XML. Nếu endpoint chỉ cung cấp XML, kết quả còn phụ thuộc cách Spring cấu hình handler/converter và negotiation; API có thể từ chối representation không được chấp nhận thay vì tự động trả JSON.

### 3.2. `Accept` không phải `Content-Type`

| Câu hỏi | Header trả lời | Ví dụ |
| --- | --- | --- |
| “Tôi đang gửi body theo định dạng nào?” | `Content-Type` | `Content-Type: application/json` |
| “Tôi chấp nhận nhận response theo định dạng nào?” | `Accept` | `Accept: application/xml` |

Một request có thể gửi JSON nhưng yêu cầu response XML:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/xml

{"title":"Spring in Action"}
~~~

Đây là trường hợp hoàn toàn hợp lý nếu API nhận JSON và cung cấp response XML. Hai header không bắt buộc có cùng giá trị vì chúng mô tả hai chiều khác nhau.

## 4. Content negotiation và Spring MVC

Spring MVC sử dụng cơ chế chuyển đổi message (HTTP message converters) để đọc request body và ghi response body. Media type của request và các điều kiện mapping ảnh hưởng đến việc lựa chọn handler/converter.

### 4.1. `consumes`: giới hạn định dạng request body

Ví dụ controller:

~~~java
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<BookResponse> create(
        @RequestBody CreateBookRequest request) {
    BookResponse created = bookService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

`consumes` khai báo media type của **request body** mà mapping chấp nhận. Trong ví dụ, endpoint yêu cầu `application/json`. Nếu client gửi một body XML vào mapping chỉ nhận JSON, framework thường trả `415 Unsupported Media Type`, tùy cấu hình handler và converter.

### 4.2. `produces`: giới hạn định dạng response

`produces` khai báo media type mà handler có thể tạo ra. Spring có thể so sánh yêu cầu từ `Accept` với các media type endpoint hỗ trợ. Nếu không có representation phù hợp, request có thể nhận `406 Not Acceptable`.

Ví dụ endpoint chỉ hỗ trợ JSON:

~~~java
@GetMapping(
    path = "/api/books/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse get(@PathVariable long id) {
    return bookService.get(id);
}
~~~

Client gọi với `Accept: application/json` thì phù hợp. Client yêu cầu `Accept: application/xml` có thể bị từ chối với `406` nếu endpoint không có converter/representation XML tương ứng và negotiation được cấu hình theo hành vi đó.

**Không nhầm `consumes` với `produces`:**

- `consumes` kiểm soát loại nội dung request mapping có thể nhận.
- `produces` kiểm soát loại nội dung response mapping có thể cung cấp.
- `Content-Type` mô tả body của request đang gửi.
- `Accept` diễn đạt media type response client chấp nhận.

### 4.3. Converter và lớp xử lý

Một số converter thường gặp:

| Converter (khái quát) | Định dạng | Ghi chú |
| --- | --- | --- |
| Jackson JSON converter | JSON | Có mặt trong nhiều ứng dụng Spring Boot web khi dependency tương ứng được cấu hình. |
| XML converter | XML | Cần dependency/cấu hình hỗ trợ XML, ví dụ Jackson XML hoặc converter khác tương thích. |
| String converter | Text | Dùng cho dữ liệu dạng chuỗi. |
| Resource/byte-array converter | Binary/resource | Dùng cho nội dung file hoặc dữ liệu byte. |
| Form converter | Form/multipart | Xử lý form data, multipart và các kiểu request phù hợp. |

Việc có một converter trên classpath không đồng nghĩa endpoint luôn hỗ trợ mọi media type. Kết quả còn phụ thuộc mapping `consumes`/`produces`, kiểu dữ liệu, cấu hình converter và thứ tự ưu tiên.

## 5. Phân biệt lỗi `400`, `406` và `415`

Ba status sau thường xuất hiện trong bài test media type:

| Status | Tình huống điển hình | Header liên quan |
| --- | --- | --- |
| `400 Bad Request` | Body không parse được hoặc nội dung/đầu vào không hợp lệ theo contract | Có thể là `Content-Type` hợp lệ nhưng JSON sai cú pháp. |
| `406 Not Acceptable` | Client yêu cầu representation qua `Accept` nhưng server không cung cấp dạng phù hợp | `Accept` |
| `415 Unsupported Media Type` | Server không hỗ trợ media type của body request hoặc định dạng content coding theo ngữ cảnh | `Content-Type` |

Ví dụ:

**415:** API nhận JSON nhưng client gửi XML:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/xml
Accept: application/json

<book><title>Spring</title></book>
~~~

**406:** API chỉ cung cấp JSON nhưng client chỉ chấp nhận XML:

~~~http
GET /api/books/42 HTTP/1.1
Accept: application/xml
~~~

**400:** Media type phù hợp nhưng JSON sai cú pháp:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":
~~~

Đây là các tình huống minh họa; cách ánh xạ lỗi thực tế phụ thuộc exception handler, converter và cấu hình ứng dụng. Không nên chỉ kiểm tra status nếu hợp đồng còn quy định error code, response body, hoặc headers cụ thể.

## 6. Tạo test MockMvc để kiểm chứng `Content-Type` và `Accept`

### 6.1. Chuẩn bị project

Ví dụ dùng Spring Boot 3.x, Spring MVC, Java 17+ và JUnit 5. Dependencies Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Giả sử endpoint `POST /api/books` nhận JSON và trả `201 Created` với JSON body. Dự án cần có controller/service và dữ liệu test tương ứng; Spring REST Docs **không tạo endpoint hay fixture**.

### 6.2. Test request JSON, response JSON

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
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class BookMediaTypeDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentCreateBookJson() throws Exception {
        mockMvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"Spring in Action","price":199000}
                    """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(header().exists(HttpHeaders.LOCATION))
            .andExpect(jsonPath("$.title").value("Spring in Action"))
            .andDo(document("books-create-json",
                requestHeaders(
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Media type của JSON request body"),
                    headerWithName(HttpHeaders.ACCEPT)
                        .description("Media type response client chấp nhận")
                ),
                requestFields(
                    fieldWithPath("title").description("Tên sách"),
                    fieldWithPath("price").description("Giá sách")
                ),
                responseHeaders(
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Media type của response"),
                    headerWithName(HttpHeaders.LOCATION)
                        .description("URI của tài nguyên vừa được tạo")
                ),
                responseFields(
                    fieldWithPath("id").description("Mã sách mới"),
                    fieldWithPath("title").description("Tên sách"),
                    fieldWithPath("price").description("Giá sách")
                )
            ));
    }
}
~~~

Phân tích:

1. `contentType(MediaType.APPLICATION_JSON)` gửi request body dạng JSON và tạo header `Content-Type` tương ứng.
2. `accept(MediaType.APPLICATION_JSON)` yêu cầu response dạng JSON qua header `Accept`.
3. `andExpect(status().isCreated())` xác nhận status `201`.
4. `content().contentTypeCompatibleWith(...)` kiểm tra response media type tương thích JSON.
5. `requestHeaders(...)` và `responseHeaders(...)` sinh bảng mô tả header ở hai chiều.
6. `requestFields(...)` và `responseFields(...)` mô tả payload request/response. Các descriptor trong chế độ thông thường còn kiểm tra độ khớp của field với payload.
7. `andDo(document(...))` nằm sau assertion; nếu assertion fail, bước document cuối chuỗi không được thực hiện.

Ví dụ giả định server trả `Location` và response có ba field `id`, `title`, `price`. Nếu API thật trả schema khác, phải cập nhật assertion/descriptor theo hợp đồng thực tế, không copy ví dụ như thể Spring Boot tự tạo các field đó.

### 6.3. Thêm test `415 Unsupported Media Type`

Giả sử endpoint `POST /api/books` khai báo `consumes = application/json` và không chấp nhận XML:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
void documentUnsupportedRequestMediaType() throws Exception {
    mockMvc.perform(post("/api/books")
            .contentType(MediaType.APPLICATION_XML)
            .accept(MediaType.APPLICATION_JSON)
            .content("<book><title>Spring</title></book>"))
        .andExpect(status().isUnsupportedMediaType())
        .andDo(document("books-create-unsupported-media-type"));
}
~~~

Đây là test dựa trên cấu hình endpoint cụ thể. Nếu ứng dụng có converter/mapping nhận XML hoặc exception handler biến đổi status, kết quả cần được điều chỉnh theo hành vi thật. Snippet response của operation này giúp người đọc nhận biết server phản hồi thế nào khi client gửi sai media type.

### 6.4. Thêm test `406 Not Acceptable`

Giả sử endpoint `GET /api/books/42` chỉ khai báo `produces = application/json`, không có representation XML:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@Test
void documentNotAcceptableResponseType() throws Exception {
    mockMvc.perform(get("/api/books/42")
            .accept(MediaType.APPLICATION_XML))
        .andExpect(status().isNotAcceptable())
        .andDo(document("books-get-not-acceptable"));
}
~~~

Để test này đúng, phải bảo đảm ứng dụng không có converter/handler khác có thể trả XML và không có exception handler đổi status. Một test `406` không nên được thêm chỉ vì muốn có đủ ví dụ; chỉ tài liệu hóa nhánh API thực sự hỗ trợ/định nghĩa.

## 7. Các snippet liên quan và cách đọc

Khi ghi operation bằng `document("books-create-json")`, snippet mặc định phổ biến gồm:

~~~text
build/generated-snippets/
└── books-create-json/
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    └── response-body.adoc
~~~

Do test có khai báo thêm descriptor, các snippet bảng cũng có thể được tạo:

~~~text
    ├── request-headers.adoc
    ├── response-headers.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
~~~

Danh sách file thực tế tùy cấu hình snippet và API descriptor đã dùng. Ý nghĩa:

| Snippet | Dùng để trả lời |
| --- | --- |
| `http-request.adoc` | Request gồm method, URI, headers và body như thế nào? |
| `http-response.adoc` | Response status, headers và body thực tế là gì? |
| `request-headers.adoc` | `Content-Type`/`Accept` được giải thích ra sao? |
| `response-headers.adoc` | Server trả `Content-Type` nào, có `Location` không? |
| `request-fields.adoc` | Field JSON gửi lên gồm những gì? |
| `response-fields.adoc` | Field JSON trả về gồm những gì? |
| `curl-request.adoc`/`httpie-request.adoc` | Có thể thử lại request bằng công cụ CLI nào? |

**Không có snippet mặc định riêng tên “content-types.adoc” hay “accept.adoc”.** Hai header được thể hiện trong `http-request`/`http-response` và bảng `request-headers`/`response-headers` nếu test khai báo descriptor.

### 7.1. Ví dụ request snippet

Nội dung `http-request.adoc` minh họa:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Spring in Action","price":199000}
~~~

Lệnh tương đương có thể xuất hiện trong snippet CLI:

~~~bash
curl 'https://api.example.com/api/books' -i -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"title":"Spring in Action","price":199000}'
~~~

Đây chỉ là **ví dụ định dạng**. URL host, thứ tự header, body formatting và flag CLI phụ thuộc cấu hình/tên template. Đối chiếu file thật được sinh sau test để biết chính xác.

### 7.2. Ví dụ response snippet

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/books/102

{"id":102,"title":"Spring in Action","price":199000}
~~~

Trong một ví dụ khác, client yêu cầu XML và server không hỗ trợ có thể nhận `406`. Không nên đưa JSON body vào mọi snippet response; body tùy status và hợp đồng endpoint.

## 8. `Content-Type` trong multipart và form requests

### 8.1. `application/x-www-form-urlencoded`

Khi gửi form dữ liệu đơn giản:

~~~http
POST /api/login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan&remember=true
~~~

Đây là form body đã encode. Không dùng `requestFields(...)` như thể body là JSON; với Spring REST Docs, dùng `formParameters(...)` để mô tả field của form khi phù hợp.

### 8.2. `multipart/form-data`

Upload file thường dùng multipart:

~~~http
POST /api/files HTTP/1.1
Content-Type: multipart/form-data; boundary=----ExampleBoundary

------ExampleBoundary
Content-Disposition: form-data; name="description"

cover of the book
------ExampleBoundary
Content-Disposition: form-data; name="file"; filename="cover.png"
Content-Type: image/png

(binary bytes)
------ExampleBoundary--
~~~

Boundary là một phần cấu trúc của multipart body; HTTP client/browser tạo giá trị phù hợp và gắn boundary vào `Content-Type`. **Không tự đặt header `Content-Type: multipart/form-data` mà bỏ boundary** khi tự dựng request bằng tay; để HTTP client tạo boundary đúng. Với MockMvc/WebTestClient, dùng API multipart được cung cấp và kiểm thử các part theo hợp đồng.

### 8.3. Binary data và content coding

Không được đồng nhất media type với content encoding. `Content-Type` mô tả định dạng representation; `Content-Encoding` mô tả cơ chế mã hóa/nén representation, ví dụ gzip. Với tải file, cần phân biệt `application/octet-stream`, media type cụ thể như `image/png` và content coding được sử dụng.

## 9. Descriptor và quy tắc kiểm chứng header

### 9.1. `requestHeaders(...)`

Ví dụ:

~~~java
requestHeaders(
    headerWithName(HttpHeaders.CONTENT_TYPE)
        .description("Media type của request body"),
    headerWithName(HttpHeaders.ACCEPT)
        .description("Media type response client chấp nhận")
)
~~~

Trong cơ chế thông thường, các header descriptor **không optional** cần hiện diện trong request; header khác chưa mô tả không tự động khiến snippet fail. Có thể đánh dấu `.optional()` khi header thực sự có thể vắng mặt.

### 9.2. `responseHeaders(...)`

Ví dụ:

~~~java
responseHeaders(
    headerWithName(HttpHeaders.CONTENT_TYPE)
        .description("Media type của response body"),
    headerWithName(HttpHeaders.LOCATION)
        .description("URI tài nguyên mới")
        .optional()
)
~~~

Header `Location` chỉ optional nếu contract/test case đang tài liệu hóa cho phép nó vắng mặt. Nếu contract yêu cầu `Location` trong `201 Created`, hãy để descriptor bắt buộc và thêm assertion kiểm tra giá trị.

### 9.3. Optional và relaxed

- `.optional()` cho phép một header không xuất hiện ở một response/request cụ thể.
- `relaxedRequestHeaders(...)` hoặc `relaxedResponseHeaders(...)` có thể bỏ qua các header chưa được mô tả trong bảng; vẫn cần mô tả và kiểm tra các header mà tài liệu yêu cầu.
- Header descriptor mô tả sự hiện diện/ý nghĩa, không kiểm chứng chính xác giá trị header. Dùng `header().string(...)`, `expectHeader()` hoặc assertion tương ứng để kiểm tra giá trị.

Tương tự, descriptor payload không thể chứng minh dữ liệu nghiệp vụ đúng. Dùng assertion riêng cho status, header value, body content và các ràng buộc domain.

## 10. WebTestClient và REST Assured

Spring REST Docs có module tích hợp cho nhiều loại client. Cú pháp khác nhau, nhưng nguyên tắc vẫn là cấu hình `Content-Type`/`Accept` trên request, xác nhận response và ghi operation.

### 10.1. WebTestClient

Ví dụ với client đã được cấu hình REST Docs:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.post()
    .uri("/api/books")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue("""
        {"title":"Spring in Action","price":199000}
        """)
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.title").isEqualTo("Spring in Action")
    .consumeWith(document("books-create-webtestclient"));
~~~

`contentType(...)` đặt định dạng body được gửi; `accept(...)` nêu định dạng response mong muốn. `expectHeader().contentTypeCompatibleWith(...)` xác nhận response media type. Module tích hợp tương ứng là `spring-restdocs-webtestclient`, cần cấu hình đúng client/documentation context theo loại ứng dụng.

### 10.2. REST Assured

REST Assured hỗ trợ các hàm thiết lập media type:

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

given(spec)
    .filter(document("books-create-restassured"))
    .contentType("application/json")
    .accept("application/json")
    .body("""
        {"title":"Spring in Action","price":199000}
        """)
.when()
    .post("/api/books")
.then()
    .statusCode(201)
    .contentType("application/json");
~~~

`contentType(...)` và `accept(...)` cùng biểu diễn hai chiều request/response. Module tích hợp là `spring-restdocs-restassured`; `spec` cần được thiết lập cho server test và REST Docs. Filter có thể ghi operation khi request thực hiện trước assertion `then()`; chỉ publish tài liệu khi toàn bộ test PASS.

## 11. Biên soạn tài liệu Asciidoctor và CI

Một trang tài liệu có thể include các snippet để giải thích request media type và response:

~~~asciidoc
= Books API

== Tạo sách bằng JSON

Client gửi request body có media type application/json và chấp nhận response application/json.

=== HTTP request
include::{snippets}/books-create-json/http-request.adoc[]

=== Request headers
include::{snippets}/books-create-json/request-headers.adoc[]

=== Request fields
include::{snippets}/books-create-json/request-fields.adoc[]

=== HTTP response
include::{snippets}/books-create-json/http-response.adoc[]

=== Response headers
include::{snippets}/books-create-json/response-headers.adoc[]

=== Response fields
include::{snippets}/books-create-json/response-fields.adoc[]

== Media type request không được hỗ trợ

include::{snippets}/books-create-unsupported-media-type/http-response.adoc[]

== Response representation không được chấp nhận

include::{snippets}/books-get-not-acceptable/http-response.adoc[]
~~~

Thuộc tính Asciidoctor `snippets` phải được build cấu hình trỏ đúng output directory (ví dụ `build/generated-snippets`). Nếu dùng Markdown, cần một template/converter hoặc bước nhúng snippet tương ứng; cú pháp `include::{snippets}/...[]` không tự chạy trong mọi Markdown renderer.

Luồng CI nên như sau:

~~~mermaid
flowchart TD
    A["Chạy HTTP tests"] --> B["Assert status + Content-Type + payload"]
    B --> C{"Test pass?"}
    C -->|Không| D["Fail pipeline"]
    C -->|Có| E["Spring REST Docs sinh snippets"]
    E --> F["Asciidoctor/Markdown build"]
    F --> G{"Tài liệu render thành công?"}
    G -->|Không| D
    G -->|Có| H["Publish artifact"]
~~~

Tác vụ build tài liệu cần phụ thuộc vào task test sinh snippet. Kiểm soát output directory và artifacts để tránh include snippet cũ sau khi test thất bại hoặc operation không còn được chạy.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `415 Unsupported Media Type` | `Content-Type` của request không được endpoint/converter hỗ trợ | Kiểm tra `consumes` và media type/body đã gửi. |
| `406 Not Acceptable` | Giá trị `Accept` không phù hợp representation API cung cấp | Kiểm tra `produces`, converters và nội dung `Accept`. |
| `400 Bad Request` với request JSON | Body sai cú pháp hoặc không deserialize/validate được | Xác minh payload, Content-Type và error handling. |
| Request gửi JSON nhưng server đọc sai | Thiếu/sai `Content-Type` hoặc body không phù hợp | Đặt `contentType(APPLICATION_JSON)` và gửi JSON hợp lệ. |
| Server trả XML dù client muốn JSON | `Accept` không rõ, endpoint không hỗ trợ JSON hoặc negotiation cấu hình khác dự kiến | Assert response media type và kiểm tra mapping/converter. |
| Test chỉ kiểm tra `Accept` mà không xác nhận response | Nhầm request preference với response representation thực tế | Assert `Content-Type` response. |
| `request-headers.adoc` không xuất hiện | Chưa khai báo `requestHeaders(...)` | Thêm descriptor trong `document(...)`. |
| `response-headers.adoc` không xuất hiện | Chưa khai báo `responseHeaders(...)` | Thêm descriptor cho header cần mô tả. |
| Test fail vì thiếu field response | Payload có field chưa mô tả hoặc descriptor không khớp | Cập nhật descriptor; chỉ relaxed khi có chủ đích. |
| Multipart request bị lỗi boundary | Tự đặt Content-Type nhưng không tạo boundary hợp lệ | Để HTTP client multipart builder tạo header/boundary. |
| Test flaky do charset/header string | So sánh chuỗi header quá cứng trong khi media type có parameter | Dùng assertion tương thích media type khi contract cho phép. |
| CI vẫn publish snippet cũ | Build docs không phụ thuộc test hoặc output tồn dư | Ràng buộc task và artifact theo lần chạy test hiện hành. |

## 13. Bài thực hành

Xây dựng tài liệu cho API catalog có hai representation JSON/XML (nếu ứng dụng hỗ trợ XML):

1. `POST /api/products` nhận JSON; `Content-Type: application/json`, `Accept: application/json`; trả `201 Created`, `Location` và JSON body.
2. `GET /api/products/42` nhận `Accept: application/json`; trả `200 OK` và JSON.
3. `GET /api/products/42` với `Accept: application/xml`; trả XML nếu API hỗ trợ, hoặc `406 Not Acceptable` nếu contract chỉ cung cấp JSON.
4. `POST /api/products` với `Content-Type: application/xml`; trả `415 Unsupported Media Type` nếu endpoint chỉ nhận JSON.
5. Ghi descriptor cho request/response headers, body fields; sử dụng identifier riêng cho từng operation.

Sau khi sinh snippet:

- Mở `http-request.adoc` để xem `Content-Type` và `Accept` đã được ghi đúng không.
- Mở `request-headers.adoc` và `response-headers.adoc` để đọc bảng mô tả.
- Đối chiếu `http-response.adoc` với status/`Content-Type` response của từng test.
- Thử thêm `charset` vào media type và xác nhận assertion tương thích có phù hợp contract.
- Biên soạn tài liệu Asciidoctor và chạy pipeline có phụ thuộc test.

**Tiêu chí hoàn thành:** giải thích đúng vai trò của hai header; test thành công và thất bại media type; sinh snippet phản ánh request/response thật; mô tả được các headers và payload; CI không phát hành tài liệu nếu test hoặc bước render lỗi.

## Tài liệu tham khảo

- [Spring Framework — Mapping Requests: Consumes and Produces](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [RFC 9110 — HTTP Semantics: Content-Type](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.3)
- [RFC 9110 — HTTP Semantics: Accept](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.1)
