# Snippet `curl-request` để tái hiện request

## 1. Mục tiêu và vị trí trong HTTP operation

Khi một REST API đã có bài kiểm thử HTTP, người đọc tài liệu thường muốn **thử lại chính request đã được kiểm thử** bằng một công cụ dòng lệnh. Trong Spring REST Docs, snippet `curl-request.adoc` giải quyết nhu cầu đó: nó trình bày một lệnh `curl` được tạo từ thông tin request mà bài test thực sự thực hiện.

Đây là nội dung của chương **HTTP operation** trong `SPRING_REST_DOCS`. Mục tiêu của module là tạo tài liệu REST API có thể kiểm chứng từ kiểm thử HTTP qua **MockMvc, WebTestClient hoặc REST Assured**; sinh các snippet cho request, response, payload, tham số và header; sau đó biên soạn tài liệu Asciidoctor/Markdown và tích hợp vào build, CI.

Sau bài học, bạn có thể:

- Giải thích thành phần của snippet `curl-request` và quan hệ với HTTP operation.
- Tạo `curl-request.adoc` từ một test MockMvc có assertion rõ ràng.
- Đọc và hiệu chỉnh URL, method, headers, query string và body trong lệnh `curl`.
- Phân biệt **tái hiện cú pháp request** với **tái hiện đúng kết quả** trong một môi trường khác.
- Dùng snippet trong tài liệu Asciidoctor, xử lý dữ liệu nhạy cảm và cấu hình pipeline cập nhật tự động.

> **Phạm vi:** `curl-request` là mẫu lệnh phục vụ tài liệu và thao tác thủ công. Nó không phải bản ghi nguyên vẹn mọi byte trên mạng, không tự cung cấp dữ liệu môi trường, và không thay thế bài kiểm thử tự động xác nhận response.

## 2. `curl-request` được sinh từ đâu?

Một **HTTP operation** trong Spring REST Docs gồm thông tin request và response thu được từ bài kiểm thử. Từ đó, REST Docs có thể tạo một số snippet mặc định, thường gồm:

| Snippet | Mục đích |
| --- | --- |
| `curl-request.adoc` | Lệnh `curl` biểu diễn request để người đọc dễ thử lại. |
| `httpie-request.adoc` | Lệnh tương đương theo cú pháp HTTPie. |
| `http-request.adoc` | Biểu diễn HTTP request dưới dạng method, URI, headers và body. |
| `http-response.adoc` | Biểu diễn status line, response headers và body. |
| `request-body.adoc` | Chỉ nội dung body của request. |
| `response-body.adoc` | Chỉ nội dung body của response. |

Danh sách trên áp dụng cho cấu hình snippet mặc định thông dụng; nó có thể thay đổi nếu dự án tùy chỉnh snippet được sinh, template hoặc đường dẫn đầu ra. Các snippet mô tả theo bảng như `request-fields.adoc`, `request-headers.adoc` và `query-parameters.adoc` chỉ xuất hiện khi khai báo các descriptor tương ứng.

Luồng hình thành một snippet `curl-request`:

~~~mermaid
flowchart LR
    A["HTTP test gửi request"] --> B["Endpoint trả response"]
    B --> C["Test kiểm chứng kết quả"]
    C --> D["REST Docs ghi HTTP operation"]
    D --> E["curl-request.adoc"]
    E --> F["Trang tài liệu API"]
    F --> G["Người đọc thử lại bằng curl"]
~~~

Trong ví dụ kiểm thử MockMvc, bước `document(...)` nên đặt sau những assertion quan trọng. Nhờ vậy, nếu assertion không đạt, đoạn sinh snippet ở cuối chuỗi lệnh không được thực hiện. Với những client test khác, thời điểm ghi operation và chạy assertion có thể khác; pipeline vẫn phải yêu cầu **toàn bộ test đạt**.

## 3. Đọc một lệnh `curl`

Giả sử API có endpoint tạo sách:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: docs-001

{"title":"Spring in Action","price":199000}
~~~

Một snippet `curl-request.adoc` **minh họa** có thể biểu diễn như sau:

~~~bash
curl 'https://api.example.com/api/books' -i -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'X-Request-Id: docs-001' \
  -d '{"title":"Spring in Action","price":199000}'
~~~

Cú pháp, thứ tự các tùy chọn, dấu nháy, cách xuống dòng và lựa chọn `-d`/`--data` là **mang tính minh họa**. File thật phụ thuộc phiên bản, template `curl-request`, client test và preprocessor đang dùng. Hãy mở snippet được sinh sau khi chạy test để xem chính xác.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `curl` | `curl 'https://...'` | Gửi request HTTP tới URL được chỉ định. |
| URL | `https://api.example.com/api/books` | Scheme, host, cổng nếu có và request target. |
| `-i` | `-i` | In response headers trong đầu ra, tiện quan sát status và headers. |
| `-X POST` | `-X POST` | Chỉ định HTTP method. |
| `-H` | `-H 'Accept: application/json'` | Bổ sung một request header; có thể xuất hiện nhiều lần. |
| `-d` | `-d '{"title":...}'` | Gửi dữ liệu request body, phù hợp với JSON nhỏ trong ví dụ. |
| `\` cuối dòng | Dấu gạch chéo ngược | Ký hiệu nối dòng trong shell kiểu POSIX; không phải ký tự của HTTP request. |

**Phân biệt `-i` và `-I`:** `-i` cho in response headers cùng nội dung response; `-I` (chữ I viết hoa) yêu cầu tải **chỉ headers**, thường gửi một request `HEAD`. Không thay `-i` bằng `-I` một cách máy móc, vì làm vậy có thể thay đổi operation cần thử.

### Dữ liệu body và phương thức HTTP

Một số điểm quan trọng khi đọc hoặc chỉnh lệnh:

- `-X POST` chỉ rõ method; `-d` cũng khiến `curl` thông thường sử dụng `POST` nếu không ghi rõ method, nhưng nên giữ method tường minh khi tài liệu hóa API.
- `-d` truyền dữ liệu request, nhưng cách xử lý byte và file khác với `--data-binary`. Khi payload cần bảo toàn chính xác ký tự xuống dòng hoặc dữ liệu dạng tệp, chọn tùy chọn thích hợp.
- `Content-Type: application/json` mô tả cách server nên diễn giải body. Chỉ dùng `-d` không tự bảo đảm gửi đúng media type JSON theo hợp đồng API.
- `Accept: application/json` cho biết định dạng response client mong muốn; khác vai trò với `Content-Type`.
- Body có thể rỗng với `GET`/`DELETE`, nhưng phương thức HTTP không tự quyết định mọi quy tắc body của một API cụ thể.

### Query string phải nằm trên URL

Với endpoint danh sách, một lệnh minh họa là:

~~~bash
curl 'https://api.example.com/api/books?page=0&size=10' -i -X GET \
  -H 'Accept: application/json'
~~~

Hai query parameter `page` và `size` nằm trên URL. Ký tự `&` cần được bảo vệ bởi dấu nháy trong nhiều shell, vì để trần có thể khiến shell hiểu thành toán tử. Với giá trị chứa khoảng trắng, dấu `&` hoặc ký tự đặc biệt, cần encode URL phù hợp thay vì ghép chuỗi tùy tiện. Nếu nhập tham số bằng tay, `curl --get --data-urlencode 'search=Spring REST Docs'` có thể hỗ trợ encode an toàn cho query string.

## 4. Tạo `curl-request.adoc` bằng MockMvc

### 4.1. Phụ thuộc và giả định

Ví dụ bên dưới dùng Spring Boot 3.x, Spring MVC, JUnit 5 và Java 17 trở lên. Dự án cần dependency kiểm thử của Spring Boot và module MockMvc tích hợp REST Docs:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Giả sử ứng dụng đã có endpoint `POST /api/books` tiếp nhận JSON:

~~~json
{
  "title": "Spring in Action",
  "price": 199000
}
~~~

và, khi tạo thành công, trả `201 Created`. Đây là hợp đồng **giả định để minh họa**, không phải endpoint được Spring REST Docs tự tạo. Test fixture phải chuẩn bị dữ liệu và trạng thái phù hợp.

### 4.2. Kiểm thử đầy đủ

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
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
class BookApiDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentCreateBook() throws Exception {
        mockMvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", "docs-001")
                .content("""
                    {"title":"Spring in Action","price":199000}
                    """))
            .andExpect(status().isCreated())
            .andDo(document("books-create"));
    }
}
~~~

Các điểm cần quan sát:

1. `post("/api/books")` quyết định request method và request target.
2. `contentType(...)`, `accept(...)` và `header(...)` thể hiện các request headers được sử dụng.
3. `content(...)` xác định JSON body của operation; REST Docs ghi nhận body này để tạo lệnh `curl`.
4. `andExpect(status().isCreated())` buộc HTTP test xác nhận kết quả `201` trước khi chạy `document(...)`.
5. `document("books-create")` là identifier dùng làm tên thư mục chứa các snippet của operation.
6. `@AutoConfigureRestDocs(...)` chỉ định output directory và các giá trị scheme, host, port được sử dụng khi **trình bày URI trong tài liệu**. Giá trị `api.example.com` là host minh họa; nó không được test này tự triển khai thành một server đang chạy.

Cấu hình ở trên dùng cơ chế tự cấu hình MockMvc của Spring Boot tương thích. Với dự án cấu hình REST Docs thủ công, cần cung cấp extension/configurer tương ứng thay cho annotation này.

### 4.3. Kiểm tra file đầu ra

Sau khi chạy test thành công, một cấu trúc thường gặp là:

~~~text
build/generated-snippets/
└── books-create/
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    └── response-body.adoc
~~~

Mở trực tiếp file:

~~~text
build/generated-snippets/books-create/curl-request.adoc
~~~

Bên trong sẽ có lệnh `curl` tương ứng request mà MockMvc đã gửi, dưới dạng do template hiện hành sinh ra. Đừng coi nội dung cụ thể trong ví dụ minh họa ở mục trước là một kết quả byte-for-byte được bảo đảm.

**Cảnh báo về tính khả thi khi chạy lại:** test `MockMvc` gửi request trong môi trường kiểm thử Spring, không nhất thiết khởi động HTTP server thật trên `api.example.com` hoặc cổng `443`. Vì vậy, dù lệnh `curl` hợp lệ về cú pháp, bạn chỉ thực sự chạy lại được khi thay URL bằng một endpoint **đang có thể truy cập**, có dữ liệu và quyền phù hợp.

## 5. Sinh snippet cho `GET` với query parameter

Giả sử API có operation `GET /api/books?page=0&size=10` trả `200 OK`. Bên trong lớp test trên, có thể bổ sung:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

// Method đặt trong class BookApiDocumentationTest
@Test
void documentListBooks() throws Exception {
    mockMvc.perform(get("/api/books")
            .queryParam("page", "0")
            .queryParam("size", "10")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(document("books-list",
            queryParameters(
                parameterWithName("page")
                    .description("Chỉ số trang, bắt đầu từ 0"),
                parameterWithName("size")
                    .description("Số sách tối đa trong một trang")
            )
        ));
}
~~~

Lệnh trong `books-list/curl-request.adoc` có thể có hình thức:

~~~bash
curl 'https://api.example.com/api/books?page=0&size=10' -i -X GET \
  -H 'Accept: application/json'
~~~

Snippet `query-parameters.adoc` bổ sung một bảng giải thích ý nghĩa các tham số. Hai loại snippet phục vụ mục đích khác nhau: `curl-request` cho người đọc cách gửi request; `query-parameters` giúp hiểu vì sao và giá trị nào được chấp nhận.

Trong MockMvc, nên dùng `queryParam(...)` hoặc một URI có query string rõ ràng khi muốn query xuất hiện trên URL. Không nên mặc định rằng mọi `param(...)` đều được biểu diễn thành query string giống nhau trong snippet.

### Path variable trong URL

Một request cụ thể tới sách `42` có thể hiển thị:

~~~bash
curl 'https://api.example.com/api/books/42' -i -X GET
~~~

Ký hiệu `/api/books/{id}` thường là **mẫu URI**, còn `/api/books/42` là **URI thật được test gọi**. Nếu muốn sinh bảng `path-parameters`, dùng request builder có giữ thông tin URI template tương ứng cùng descriptor `pathParameters(...)`. `curl-request` vẫn phải biểu diễn một URL cụ thể để người đọc có thể thử lại.

## 6. Phân biệt khả năng tái hiện request và kết quả response

Cần hiểu đúng “tái hiện” trong tên bài học: `curl-request` cố gắng diễn đạt **cách gửi một request tương ứng**. Nó không thể bảo đảm nhận được cùng status, header hoặc body khi chạy ở môi trường khác.

| Yếu tố | Điều test có | Điều cần chuẩn bị khi chạy `curl` |
| --- | --- | --- |
| HTTP server | MockMvc có thể chạy trong ứng dụng kiểm thử, không mở cổng | Một server thật hoặc địa chỉ dịch vụ có thể truy cập |
| URL | Host/scheme/port đặt theo cấu hình tài liệu | URL hợp lệ với local, staging hoặc môi trường dùng để thử |
| Dữ liệu | Test fixture có thể đã nạp sẵn sách/người dùng | Dữ liệu tương ứng tồn tại hoặc có bước tạo trước |
| Authentication | Test có thể giả lập người dùng hoặc security context | Cookie, token hay thông tin xác thực hợp lệ theo môi trường |
| Trạng thái | Test có thể rollback hoặc reset database | Môi trường thực tế có thể đã bị thay đổi bởi request trước |
| Thời gian | Test có clock hoặc ID cố định | Timestamp, ID và thứ tự dữ liệu có thể biến thiên |
| Response | Test assertion kiểm chứng điều kiện cụ thể | Kiểm tra status, headers, body của lần gọi thật |

Ví dụ, một lệnh `POST` tạo sách có thể trả `201` ở lần gọi đầu và `409 Conflict` ở lần tiếp theo nếu hệ thống cấm tạo trùng mã/tên sách. Lệnh tái hiện vẫn đúng về mặt cách gửi request; **kết quả khác** vì trạng thái hệ thống thay đổi.

Việc tài liệu hóa nên có hai lớp:

- **Thao tác:** `curl-request` hiển thị method, URI, headers, body đã test.
- **Hợp đồng:** `http-response`, bảng response fields, mô tả status và assertion trong test giải thích kết quả mong đợi.

Để kiểm tra kết quả từ dòng lệnh, `-i` giúp quan sát response headers và body; `-v` hữu ích khi debug kết nối/TLS nhưng có thể in nhiều thông tin nhạy cảm nên cần dùng cẩn trọng.

## 7. Chạy snippet trong môi trường thật

### 7.1. Kiểm tra các tham số trước khi chạy

Giả sử file được sinh chứa URL `https://api.example.com` là host minh họa. Để thử local, có thể đổi thành:

~~~bash
curl 'http://localhost:8080/api/books?page=0&size=10' -i -X GET \
  -H 'Accept: application/json'
~~~

Đây là thao tác **chỉnh lệnh khi dùng tài liệu**, không sửa snippet đã sinh để giả vờ rằng test gọi localhost. Nếu muốn các snippet của cả tài liệu cùng trình bày host công khai, hãy cấu hình REST Docs cho phù hợp ở nguồn sinh tài liệu.

Trước khi chạy lệnh `POST`, hãy kiểm tra:

1. URL đang trỏ đến đúng môi trường và endpoint.
2. Method đúng với operation được tài liệu hóa.
3. Query string, request headers và JSON body phù hợp.
4. Mọi placeholder như `{token}` hoặc `{id}` đã được thay bằng giá trị hợp lệ.
5. Request có tạo, cập nhật hoặc xóa dữ liệu không; dùng dữ liệu thử nghiệm khi cần.
6. Tài khoản hoặc token có quyền cần thiết.

### 7.2. Xem status và response

Ví dụ ở môi trường local:

~~~bash
curl 'http://localhost:8080/api/books/42' -i -X GET \
  -H 'Accept: application/json'
~~~

Đầu ra có thể gồm:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"id":42,"title":"Spring in Action","price":199000}
~~~

Kết quả này chỉ là minh họa. Để xác định lệnh đã thành công về nghiệp vụ, không thể chỉ dựa vào process exit code của `curl`: mặc định `curl` có thể trả exit code thành công ngay cả khi server phản hồi HTTP `404` hoặc `500`. Nên **kiểm tra status HTTP**, headers và body; khi cần tự động hóa, cân nhắc `--fail-with-body` trên các phiên bản `curl` hỗ trợ (tùy chọn này khiến nhiều HTTP error phản ánh qua exit code nhưng vẫn cần kiểm tra yêu cầu nghiệp vụ).

### 7.3. Dùng file cho JSON dài

Với body JSON nhiều dòng, gửi từ một file giúp dễ quản lý và tránh lỗi escape trong shell:

~~~json
{
  "title": "Spring in Action",
  "price": 199000
}
~~~

Giả sử nội dung trên được lưu tại `book.json`, lệnh gửi là:

~~~bash
curl 'http://localhost:8080/api/books' -i -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '@book.json'
~~~

`--data-binary '@book.json'` đọc body từ file và giữ byte theo nội dung file. File `book.json` là tệp thực hành do người học tự chuẩn bị; Spring REST Docs không tự sinh file body này trong ví dụ.

### 7.4. Khác biệt giữa các shell

Snippet `curl` thường dùng cú pháp phù hợp với shell kiểu POSIX, ví dụ Bash hoặc zsh. Dấu `\` cuối dòng tiếp tục lệnh ở shell đó; không thể dán nguyên xi vào mọi môi trường.

Trên Windows PowerShell, nên gọi rõ `curl.exe` để tránh nhầm với alias `curl` trỏ tới `Invoke-WebRequest` trong Windows PowerShell 5.1. Ví dụ một lệnh một dòng:

~~~powershell
curl.exe -i -X GET "http://localhost:8080/api/books?page=0&size=10" -H "Accept: application/json"
~~~

Với `POST` chứa JSON có nhiều dấu nháy kép, dùng file `book.json` và `--data-binary "@book.json"` sẽ dễ kiểm soát hơn việc copy cú pháp shell Unix vào PowerShell:

~~~powershell
curl.exe -i -X POST "http://localhost:8080/api/books" -H "Content-Type: application/json" --data-binary "@book.json"
~~~

Đừng nhầm sự khác nhau về dấu nháy/escape giữa các terminal với một thay đổi trong HTTP method hoặc hợp đồng endpoint.

## 8. URI hiển thị trong tài liệu và URL thực của test

Trong MockMvc, một request `post("/api/books")` có thể chạy hoàn toàn trong tiến trình test. Nếu không cấu hình thêm, REST Docs thường dùng một URI cơ sở dành cho môi trường test khi tạo request snippet. Với các ví dụ công khai, nên chỉnh URI được **trình bày** cho ổn định, chẳng hạn:

~~~java
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
~~~

Các thuộc tính này làm ví dụ tài liệu dễ hiểu hơn, nhưng không chứng minh rằng endpoint tại `https://api.example.com` đã được triển khai và truy cập được.

Nếu dùng client chạy trên HTTP server thật, REST Docs có thể ghi nhận host/port cụ thể của môi trường kiểm thử. Preprocessor có thể giúp chuẩn hóa URI hiển thị trong request snippet. Ví dụ:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

// Bên trong chuỗi MockMvc, thay lời gọi document(...) hiện có:
.andDo(document("books-list",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.com")
            .removePort()
    )
));
~~~

Đây là một **ví dụ thay thế** cho lời gọi `document(...)` trước đó. Nếu test còn sinh `query-parameters.adoc` hoặc các snippet mô tả khác, hãy giữ các descriptor cần thiết trong cùng lời gọi `document(...)`.

Một quy tắc hữu ích: URL trong snippet nên phù hợp với **môi trường tài liệu muốn hướng dẫn**, đồng thời phải ghi rõ host mẫu hoặc yêu cầu người đọc thay bằng môi trường có thể truy cập. Không cấu hình một hostname/port chỉ để làm lệnh trông “đẹp” mà không giải thích cách chạy.

## 9. Authentication và dữ liệu nhạy cảm

Snippet `curl-request` có thể chứa toàn bộ request headers và body được test gửi. Nếu test sử dụng dữ liệu thật, tài liệu sinh ra có nguy cơ tiết lộ token, API key, cookie, thông tin người dùng hoặc trường dữ liệu riêng tư.

**Nguyên tắc đầu tiên:** chỉ dùng fixture giả và secret placeholder trong test tài liệu hóa. Ví dụ minh họa:

~~~http
Authorization: Bearer <access-token>
~~~

Dòng trên là một placeholder mang tính hướng dẫn. Người đọc cần thay bằng token hợp lệ khi thực hành; không có nghĩa Spring REST Docs tự cấp token hoặc tự đổi token thật thành giá trị mẫu.

Khi cần, dùng `preprocessRequest(...)` để **loại bỏ hoặc thay thế dữ liệu được đưa vào snippet**. Ví dụ bỏ header không phù hợp để công khai:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

// Thay lời gọi document(...) cuối test bằng:
.andDo(document("books-create",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie")
    )
));
~~~

Cần lưu ý:

- Nếu lệnh đã bị bỏ header xác thực, nó **không còn là bản sao đầy đủ của request đã gửi** và có thể trả `401` khi chạy lại; tài liệu cần hướng dẫn người đọc bổ sung cách xác thực hợp lệ.
- Khi muốn vừa giữ cấu trúc vừa tránh công khai secret, cân nhắc dùng fixture token giả và cơ chế mask/replace giá trị trong snippet. Đảm bảo token được thay thế không bị nhầm với token thật.
- Đừng ghi token vào tài liệu, artifact CI hoặc log công khai.
- Không dùng `-k`/`--insecure` để vượt kiểm tra TLS chỉ vì snippet gặp lỗi chứng chỉ; nên sửa cấu hình chứng chỉ tin cậy trong môi trường thử.
- Lệnh `POST`, `PUT`, `PATCH`, `DELETE` có thể thay đổi dữ liệu. Chạy thử trên môi trường và tài nguyên phù hợp, tránh tác động ngoài dự kiến.

`preprocessRequest` chỉ xử lý **bản ghi dùng để sinh snippet**, không thay đổi request mà controller đã xử lý và không thay thế assertion. Khi cần chứng minh hệ thống xác thực đúng, hãy viết test xác thực/phân quyền riêng.

## 10. WebTestClient và REST Assured cũng sinh được `curl-request`

Dù khác cú pháp test, Spring REST Docs vẫn lấy thông tin operation để tạo snippet `curl-request.adoc` khi client được tích hợp đúng cách.

### 10.1. WebTestClient

Với `WebTestClient` **đã cấu hình Spring REST Docs**, một operation đọc danh sách có thể trông như sau:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
    .uri("/api/books?page=0&size=10")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("books-list-webtestclient"));
~~~

Sau khi test đạt, kiểm tra snippet tại đường dẫn tương ứng với output directory của WebTestClient và identifier `books-list-webtestclient`. Module tích hợp được dùng là `spring-restdocs-webtestclient`; cách thiết lập REST Docs với WebTestClient phụ thuộc kiểu test và version Spring sử dụng.

### 10.2. REST Assured

REST Assured ghi operation thông qua **filter** do Spring REST Docs cung cấp. Ví dụ với một `RequestSpecification` đã cấu hình server và REST Docs:

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

// spec phải được cấu hình sẵn cho server test và Spring REST Docs.
given(spec)
    .filter(document("books-list-restassured"))
    .accept("application/json")
.when()
    .get("/api/books?page=0&size=10")
.then()
    .statusCode(200);
~~~

Sử dụng module `spring-restdocs-restassured` và thiết lập `RestAssuredRestDocumentationConfigurer` hoặc cách cấu hình được version đang dùng hỗ trợ. Filter thực hiện ghi operation khi gửi request; assertion `statusCode(200)` diễn ra ở phần `then()`. Vì vậy, pipeline phải xác nhận toàn bộ test thành công trước khi xuất bản tài liệu.

### 10.3. Đối chiếu các client

| HTTP test client | Chọn operation | Điểm sinh tài liệu |
| --- | --- | --- |
| MockMvc | `perform(post("/api/books"))` | `andDo(document("books-create"))` |
| WebTestClient | `webTestClient.get().uri(...)` | `expectBody().consumeWith(document("..."))` |
| REST Assured | `given(spec)...when().get(...)` | Filter `document("...")` trên request |

Điểm chung: **lệnh `curl` phải xuất phát từ request đã được thực thi trong test**, không phải từ một cURL mẫu nhập tay rồi nhận là REST Docs tự sinh.

## 11. Đưa `curl-request` vào tài liệu Asciidoctor

Theo cấu hình mặc định thông dụng, Spring REST Docs xuất snippet với đuôi `.adoc`. Một trang Asciidoctor có thể include nhiều operation:

~~~asciidoc
= Books API

== Tạo sách

Gửi POST /api/books với title và price hợp lệ.

=== Thử bằng curl

include::{snippets}/books-create/curl-request.adoc[]

=== HTTP response

include::{snippets}/books-create/http-response.adoc[]

== Liệt kê sách

=== Thử bằng curl

include::{snippets}/books-list/curl-request.adoc[]

=== Query parameters

include::{snippets}/books-list/query-parameters.adoc[]
~~~

Thuộc tính Asciidoctor `snippets` cần được build định nghĩa tới đường dẫn snippet tương ứng, ví dụ `build/generated-snippets`. Đường dẫn tuyệt đối hay tương đối phải phù hợp với cấu hình build và vị trí tài liệu nguồn.

Khi biên soạn tài liệu Markdown, cú pháp `include::{snippets}/...[]` không tự hoạt động với mọi Markdown renderer. Dự án cần một bước chuyển đổi hoặc cơ chế template/nhúng tương ứng. Mục tiêu là **dùng nội dung snippet đã được test sinh**, thay vì duy trì một lệnh `curl` viết tay dễ lỗi thời.

### Tích hợp build và CI

~~~mermaid
flowchart TD
    A["HTTP tests"] --> B{"Assertions pass?"}
    B -->|Không| C["CI fail, không publish"]
    B -->|Có| D["Sinh curl-request và snippets khác"]
    D --> E["Biên soạn Asciidoctor/Markdown"]
    E --> F{"Build tài liệu pass?"}
    F -->|Không| C
    F -->|Có| G["Đóng gói hoặc publish tài liệu"]
~~~

Cần cấu hình tác vụ tài liệu phụ thuộc vào tác vụ test sinh snippet, đồng thời fail khi test hoặc include không hợp lệ. Nếu dùng output directory có snippet cũ, việc include một tệp còn sót có thể làm tài liệu “trông như vẫn mới”. Hãy kiểm soát artifacts, dependencies và phạm vi test để bản tài liệu build từ kết quả kiểm thử hiện hành.

Một thay đổi đường dẫn endpoint, method hoặc JSON body nên được phản ánh qua **cập nhật test + assertion + snippet được sinh lại**. Chỉ sửa dòng `curl` viết tay trên trang tài liệu sẽ bỏ qua lợi ích kiểm chứng của Spring REST Docs.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Không có `curl-request.adoc` | Chưa gắn `document(...)`, test dừng trước điểm ghi, output directory/identifier sai hoặc tùy chỉnh snippet mặc định | Xác minh test được chạy thành công và xem đúng thư mục snippet. |
| `curl` gọi host không tồn tại | MockMvc test không có HTTP server tại URL trình bày; host được cấu hình làm ví dụ | Thay host bằng server thật hoặc chỉ rõ URL môi trường thử. |
| Lệnh trả `401` khi chạy lại | Test dùng mock security/session, header xác thực bị mask hoặc người dùng thiếu token | Cấp thông tin xác thực phù hợp, không đưa secret vào tài liệu. |
| Method không đúng kỳ vọng | Test gọi nhầm `get`/`post` hoặc include sai identifier | Kiểm tra builder, assertion và `http-request.adoc` của đúng operation. |
| Body JSON bị lỗi khi copy | Sai dấu nháy/escape giữa Bash, PowerShell và CMD | Dùng file JSON với `--data-binary @file` hoặc chuyển cú pháp đúng shell. |
| Query parameter mất hoặc biến dạng | URI/query string chưa được tạo đúng, shell diễn giải dấu `&` hoặc giá trị chưa encode | Dùng `queryParam(...)` trong test; bao URL bằng dấu nháy và encode giá trị khi chạy. |
| `curl` trả exit code 0 nhưng HTTP `404` | `curl` mặc định phân biệt lỗi transport với HTTP error | Quan sát status từ `-i`, hoặc dùng xử lý HTTP status phù hợp automation. |
| `POST` đầu tiên được `201`, lần sau `409` | Tài nguyên đã tồn tại hoặc dữ liệu thử nghiệm thay đổi | Reset fixture hoặc dùng dữ liệu phù hợp, ghi rõ tính không idempotent. |
| Lệnh có token hoặc cookie thật | Fixture nhạy cảm hoặc preprocessing chưa được cấu hình | Thay dữ liệu test bằng dữ liệu giả, mask hoặc loại bỏ trước khi tạo snippet. |
| Trang docs dùng lệnh cURL cũ | Build tài liệu không phụ thuộc test; include tệp từ lần build trước | Làm rõ dependencies, source của snippet và điều kiện fail trong CI. |

## 13. Thực hành có kiểm chứng

Giả sử bạn xây dựng API sách với các endpoint sau:

| Operation | Expected status | Identifier nên dùng |
| --- | --- | --- |
| `POST /api/books` với JSON `title`, `price` | `201 Created` | `books-create` |
| `GET /api/books?page=0&size=10` | `200 OK` | `books-list` |
| `GET /api/books/42` | `200 OK` | `books-get-one` |
| `DELETE /api/books/42` | `204 No Content` | `books-delete` |

Thực hiện các bước:

1. Viết test riêng cho từng operation. Assert đúng status; bổ sung body/header assertions khi hợp đồng yêu cầu.
2. Gắn `document(...)` với identifier riêng. Chạy test và kiểm tra bốn tệp `curl-request.adoc`.
3. Đối chiếu `curl-request` và `http-request` của từng operation: method, URI, query, headers và body có tương ứng không?
4. Chọn một server local/staging có dữ liệu thử nghiệm, điều chỉnh URL/credential theo môi trường rồi thử lại ít nhất một lệnh `GET` và một lệnh `POST`.
5. So sánh response thật với `http-response` và assertions của test; giải thích bất kỳ khác biệt nào do môi trường/dữ liệu.
6. Include snippets vào Asciidoctor; xác nhận build/CI không publish khi test thất bại hoặc thiếu snippet.

### Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể **giải thích từng phần của một lệnh `curl`**, sinh snippet từ test thay vì tự viết, chạy lại request trên server có thể truy cập, phân biệt khác biệt môi trường với lỗi hợp đồng API, và tích hợp snippet vào tài liệu được tạo sau khi test đạt.

## Tài liệu tham khảo

- [Spring REST Docs Reference — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs Reference — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/)
- [curl — Everything curl](https://everything.curl.dev/)
- [curl command-line options](https://curl.se/docs/manpage.html)
