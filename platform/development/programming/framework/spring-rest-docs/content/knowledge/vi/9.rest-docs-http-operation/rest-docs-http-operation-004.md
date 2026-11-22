# Snippet `httpie-request` và lựa chọn công cụ dòng lệnh

## 1. Mục tiêu và bối cảnh

Trong chương **HTTP operation** của `SPRING_REST_DOCS`, mỗi lần bài kiểm thử gửi request và nhận response có thể tạo ra những mảnh tài liệu (snippet) dựa trên chính lần trao đổi HTTP đó. Nếu `http-request.adoc` trình bày request theo dạng văn bản HTTP và `curl-request.adoc` trình bày lệnh `curl`, thì **`httpie-request.adoc` sinh ví dụ lệnh HTTPie** để người đọc dễ gọi lại API từ terminal.

Bài học này phục vụ mục tiêu của Spring REST Docs: **tạo tài liệu REST API có thể kiểm chứng** từ kiểm thử MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; sau đó đưa tài liệu Asciidoctor/Markdown vào build và CI.

Sau bài này, bạn sẽ biết:

- `httpie-request` là gì, được tạo khi nào và nằm ở đâu trong kết quả kiểm thử.
- Cách đọc lệnh HTTPie, phân biệt HTTP method, URL, request headers, query parameters và JSON body.
- Cách kiểm chứng request bằng MockMvc rồi sinh `httpie-request.adoc` và các snippet bổ trợ.
- Cách lựa chọn HTTPie, `curl` hoặc biểu diễn HTTP thuần cho từng đối tượng đọc tài liệu.
- Cách chạy thử lệnh trên môi trường thật, tránh rò rỉ secret và cập nhật tài liệu trong CI.

> **Lưu ý:** lệnh HTTPie trong snippet là **cách biểu diễn một HTTP request đã được test thực hiện**. Lệnh đó không tự khởi động server, không tự tạo fixture, không xác thực thay người dùng, và không bảo đảm response khi chạy ở môi trường khác sẽ giống hệt response trong test.

## 2. `httpie-request` xuất hiện như thế nào?

Spring REST Docs ghi lại một **HTTP operation**, gồm request và response. Với cấu hình phổ biến, khi test gọi `document("identifier")`, REST Docs tạo các snippet trong thư mục đặt theo identifier:

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

Đây là **sáu snippet mặc định** của Spring REST Docs khi chưa tùy chỉnh tập snippet. Tên thư mục gốc phụ thuộc cấu hình output directory và công cụ build (ví dụ Gradle thường dùng `build/generated-snippets`, Maven có thể dùng `target/generated-snippets`).

| Snippet | Câu hỏi được trả lời |
| --- | --- |
| **`httpie-request.adoc`** | “Tôi có thể thử request bằng lệnh `http` của HTTPie như thế nào?” |
| `curl-request.adoc` | “Lệnh `curl` tương đương để gửi request là gì?” |
| `http-request.adoc` | “Request có method, URI, header và body như thế nào?” |
| `http-response.adoc` | “Response thực tế trong test trả status, header và body nào?” |
| `request-body.adoc` | “Chỉ riêng nội dung request body là gì?” |
| `response-body.adoc` | “Chỉ riêng nội dung response body là gì?” |

Những snippet bảng như `request-fields.adoc`, `request-headers.adoc` hoặc `query-parameters.adoc` được sinh khi bài test khai báo descriptor phù hợp, không chỉ vì đã tạo `httpie-request`.

~~~mermaid
flowchart LR
    A["HTTP test: MockMvc / WebTestClient / REST Assured"] --> B["HTTP operation"]
    B --> C["document(identifier)"]
    C --> D["httpie-request.adoc"]
    C --> E["curl-request.adoc"]
    C --> F["http-request.adoc"]
    C --> G["http-response.adoc"]
    D --> H["Tài liệu API"]
    E --> H
    F --> H
    G --> H
~~~

Trong ví dụ MockMvc, ta sẽ đặt `document(...)` sau các assertion. Cách này giúp snippet được ghi sau khi những điều kiện mong đợi đã vượt qua kiểm tra; pipeline chỉ xuất bản khi **toàn bộ bài kiểm thử liên quan thành công**.

## 3. HTTPie là gì và dùng cú pháp nào?

[HTTPie](https://httpie.io/) là HTTP client dòng lệnh, được thiết kế để gọi và khám phá API với cú pháp khá gần cách con người mô tả một request. Command thường là `http` (hoặc `https` nếu môi trường cài đặt cung cấp shortcut đó).

Một lệnh gọi tài nguyên đơn giản:

~~~bash
http GET https://api.example.com/api/books/42 Accept:application/json
~~~

Các thành phần:

| Thành phần | Giá trị | Ý nghĩa |
| --- | --- | --- |
| Lệnh thực thi | `http` | CLI của HTTPie đã được cài trên máy. |
| Method | `GET` | HTTP method gửi lên server; viết tường minh giúp tài liệu rõ ràng. |
| URL | `https://api.example.com/api/books/42` | Scheme, host, path và query string nếu có. |
| Header | `Accept:application/json` | Yêu cầu media type cho response. |

Dùng `http --version` để kiểm tra công cụ đã được cài hay chưa. Những ví dụ trong bài minh họa HTTPie CLI phổ biến; tùy phiên bản HTTPie và shell, dấu nháy, flag hoặc format có thể khác đôi chút.

### 3.1. Các ký hiệu request item quan trọng

HTTPie sử dụng các dấu phân cách có ý nghĩa khác nhau:

| Cú pháp | Ví dụ | HTTPie xử lý |
| --- | --- | --- |
| `Name:Value` | `Accept:application/json` | Header request. |
| `field=value` | `title='Spring in Action'` | Trường dữ liệu; mặc định thuộc JSON object khi gửi body có cấu trúc. |
| `field:=json` | `price:=199000`, `available:=true` | Giá trị JSON thô: số, boolean, null, object hoặc array theo cú pháp JSON hợp lệ. |
| `name==value` | `page==0`, `size==10` | Tham số query string trên URL. |
| `field@file` | `cover@cover.png` | Tệp gửi dạng form/multipart khi dùng chế độ phù hợp. |
| `--raw` | `--raw='{"title":"Spring"}'` | Toàn bộ request body thô, không dùng cùng structured data fields. |
| `--form` hoặc `-f` | `--form POST ...` | Gửi dữ liệu dạng form thay cho JSON mặc định. |

**Ví dụ có kiểu dữ liệu khác nhau:**

~~~bash
http POST https://api.example.com/api/books \
  title='Spring in Action' \
  price:=199000 \
  available:=true \
  tags:='["java","spring"]'
~~~

Theo cú pháp HTTPie, `title` là chuỗi; `price` là số, `available` là boolean, `tags` là mảng. Dấu `:=` không phải cách viết đẹp hơn của dấu `=`: nếu thay `price:=199000` bằng `price=199000`, JSON gửi đi có thể đổi từ số thành **chuỗi**.

Đối với câu lệnh trên, body JSON tương ứng về cấu trúc là:

~~~json
{
  "title": "Spring in Action",
  "price": 199000,
  "available": true,
  "tags": ["java", "spring"]
}
~~~

Các trường được HTTPie tuần tự hóa theo định dạng đã chọn. Dù JSON tương đương về ý nghĩa, thứ tự property hoặc khoảng trắng có thể khác request gốc; muốn giữ **byte của body**, hãy sử dụng cách gửi dữ liệu thô phù hợp.

### 3.2. Method mặc định

HTTPie thường tự chọn:

- `GET` khi không có request body;
- `POST` khi có dữ liệu body.

Tài liệu API vẫn nên **viết method tường minh**: `http GET ...`, `http POST ...`, `http PATCH ...`. Điều đó tránh việc người đọc thêm một data field và vô tình làm thay đổi method của request.

## 4. Đọc snippet `httpie-request` của một operation

Giả sử ứng dụng cung cấp `POST /api/books` với request:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: docs-001

{"title":"Spring in Action","price":199000}
~~~

Một lệnh HTTPie **viết minh họa** cho request trên:

~~~bash
http POST https://api.example.com/api/books \
  Content-Type:application/json \
  Accept:application/json \
  X-Request-Id:docs-001 \
  --raw='{"title":"Spring in Action","price":199000}'
~~~

Đây là lệnh HTTPie hợp lệ theo cú pháp thông dụng; **không cam kết từng dấu nháy, thứ tự đối số hay cách biểu diễn body giống hệt snippet Spring REST Docs sinh ra**. REST Docs có thể chọn cách truyền raw request body hoặc một hình thức dòng lệnh khác theo formatter/template và phiên bản. Khi cần nội dung chính xác, hãy mở `httpie-request.adoc` được tạo bởi bài test.

Có thể chuyển lệnh trên sang cách tạo JSON từ các data item:

~~~bash
http POST https://api.example.com/api/books \
  Accept:application/json \
  X-Request-Id:docs-001 \
  title='Spring in Action' \
  price:=199000
~~~

HTTPie mặc định dùng JSON với các data item có cấu trúc, trừ khi được cấu hình khác. Hai lệnh có thể tạo payload **tương đương về ý nghĩa** trong trường hợp này, nhưng không nên tự cho rằng body, headers và bytes giống nhau trong mọi trường hợp. Nếu API yêu cầu chữ ký dựa trên body, giữ nguyên đúng định dạng mà client cần gửi.

### Vì sao đôi khi cần `--raw`?

Một số request body khó hoặc không phù hợp để biểu diễn bằng `field=value`, ví dụ JSON top-level là array hoặc chuỗi, dữ liệu XML, plain text, body có khoảng trắng đặc biệt hay payload đã được ký. Dùng `--raw`, pipe từ stdin hoặc truyền body từ file sẽ rõ ràng hơn.

Với file JSON đã chuẩn bị, HTTPie hỗ trợ đọc request body từ file:

~~~bash
http POST https://api.example.com/api/books \
  Content-Type:application/json \
  @book.json
~~~

`@book.json` ở đây là **raw body từ file**, khác với request item `cover@cover.png` dùng upload file. File `book.json` cần tồn tại trong môi trường chạy lệnh. Không có file nào được Spring REST Docs tự tạo bằng cách sinh một lệnh như trên.

## 5. Viết HTTP test MockMvc để sinh snippet

### 5.1. Chuẩn bị

Ví dụ sử dụng Spring Boot 3.x, Spring MVC, JUnit 5 và Java 17 trở lên. Dự án cần dependency test cho Spring Boot và Spring REST Docs MockMvc.

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Nên để Spring Boot dependency management/BOM chọn phiên bản thư viện phù hợp với dự án.

Giả sử endpoint `POST /api/books` đã tồn tại, tiếp nhận JSON có `title` và `price`, trả `201 Created` khi tạo mới thành công. Đây là hợp đồng **minh họa**; Spring REST Docs không tự tạo controller, dữ liệu hoặc server.

### 5.2. Ví dụ kiểm thử

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
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
            .andDo(document("books-create",
                requestFields(
                    fieldWithPath("title").description("Tên sách"),
                    fieldWithPath("price").description("Giá sách tính bằng VND")
                )
            ));
    }
}
~~~

Giải thích:

1. `post("/api/books")` tạo HTTP request với method `POST` và path `/api/books`.
2. `contentType(...)`, `accept(...)`, `header(...)` và `content(...)` cung cấp headers/body thực tế.
3. `andExpect(status().isCreated())` kiểm tra response trả `201` trước khi tạo tài liệu.
4. `document("books-create", ...)` ghi lại operation và sinh các snippet mặc định, bao gồm `httpie-request.adoc`.
5. `requestFields(...)` sinh bảng mô tả field trong `request-fields.adoc`; những descriptor này cũng có tác dụng kiểm chứng payload được tài liệu hóa.
6. `@AutoConfigureRestDocs(...)` dùng hostname ví dụ `api.example.com` để trình bày URI trong tài liệu; nó **không** triển khai endpoint tại host đó.

Sau khi chạy test thành công, có thể kiểm tra:

~~~text
build/generated-snippets/books-create/httpie-request.adoc
build/generated-snippets/books-create/curl-request.adoc
build/generated-snippets/books-create/http-request.adoc
build/generated-snippets/books-create/http-response.adoc
build/generated-snippets/books-create/request-fields.adoc
~~~

Các snippet này nằm chung identifier nên cùng mô tả **một operation**. Nếu dự án tùy chỉnh tập snippet mặc định, một hoặc nhiều file có thể không xuất hiện.

> **Không trộn “ví dụ diễn giải” và “đầu ra test”:** lệnh HTTPie minh họa trong bài giúp hiểu cú pháp; `httpie-request.adoc` trên đĩa mới là nội dung mà cấu hình dự án đã sinh.

## 6. `GET`, query string và lựa chọn cú pháp HTTPie

Với endpoint `GET /api/books?page=0&size=10`, một lệnh HTTPie dễ đọc là:

~~~bash
http GET 'https://api.example.com/api/books?page=0&size=10' \
  Accept:application/json
~~~

HTTPie còn hỗ trợ cách khai báo query parameters bằng request items:

~~~bash
http GET https://api.example.com/api/books \
  page==0 \
  size==10 \
  Accept:application/json
~~~

Hai lệnh sẽ gửi query parameter `page=0` và `size=10`. Tuy nhiên, **không thêm `page==0` vào lệnh đã có `?page=0`** nếu không muốn tạo tham số lặp lại.

Trong bài kiểm thử MockMvc, có thể sử dụng `queryParam(...)` để làm rõ query string và tạo bảng mô tả tương ứng. Đoạn sau được đặt bên trong cùng lớp test đã cấu hình ở mục trước (thêm các static import nếu cần):

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

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

Kết quả thường có:

~~~text
build/generated-snippets/books-list/httpie-request.adoc
build/generated-snippets/books-list/query-parameters.adoc
~~~

`httpie-request` giúp **gửi request**, còn `query-parameters` giải thích **ý nghĩa tham số** và tính bắt buộc của từng tham số. Không nên coi lệnh CLI là bảng mô tả hợp đồng API đầy đủ.

### URI path parameter

Với `GET /api/books/42`, request dùng URI cụ thể:

~~~bash
http GET https://api.example.com/api/books/42
~~~

Trong tài liệu giới thiệu endpoint, bạn có thể viết mẫu `/api/books/{id}`; nhưng lệnh có khả năng chạy lại phải chứa một giá trị thực tế như `42`. Muốn sinh `path-parameters.adoc` bằng MockMvc, cần dùng request builder hỗ trợ giữ URI template cùng descriptor `pathParameters(...)`.

## 7. Lựa chọn HTTPie, `curl` hay request HTTP thuần

Không có một công cụ dòng lệnh phù hợp tối ưu cho mọi người đọc tài liệu. Spring REST Docs tạo cả `httpie-request` và `curl-request` để nhóm tài liệu có thể phục vụ các nhu cầu khác nhau từ cùng một operation.

| Tiêu chí | HTTPie (`http`) | `curl` | `http-request` thuần |
| --- | --- | --- | --- |
| Đối tượng | Developer muốn thử API và đọc JSON bằng terminal | Developer, vận hành, script và môi trường tự động hóa | Người đọc muốn hiểu chính xác cấu trúc HTTP |
| Cú pháp | Gọn với headers, query, JSON object | Rất linh hoạt; tùy chọn `-X`, `-H`, `-d`... | Dòng request và các headers/body |
| JSON | `field=value`, `field:=json`, `--raw` | Truyền body qua `--data`/`--data-binary` hoặc file | Hiển thị payload đã được ghi nhận |
| Trình bày output | Mặc định hướng đến phản hồi dễ đọc; có format và màu | Thường in response body, tùy chọn để in headers | Chỉ là tài liệu, không phải lệnh thực thi |
| Dùng trong automation | Hỗ trợ với flag kiểm tra status và kiểm soát output | Rất phổ biến trong shell và nhiều môi trường build | Không chạy trực tiếp |
| Yêu cầu cài đặt | Cần HTTPie CLI | Cần `curl` phù hợp môi trường | Không cần CLI để đọc |
| Bảo toàn byte request | Tùy cách dựng body và tùy chọn `--raw`/file | Tùy cách truyền body, encoding và flags | Chỉ mô tả request do REST Docs biểu diễn |

**Nên chọn HTTPie khi:**

- Tài liệu hướng dẫn developer thử các API JSON theo cách dễ đọc và dễ sửa tham số.
- Người đọc thường thao tác terminal, muốn quan sát response ngay và được hỗ trợ format.
- Mục tiêu là khám phá API hoặc tái hiện operation một cách tương đương về ngữ nghĩa.

**Nên chọn `curl` khi:**

- Môi trường của nhóm đã dùng `curl` trong shell script hoặc CI.
- Tài liệu cần ví dụ tương thích với số lượng lớn môi trường có sẵn `curl`.
- Cần các tùy chọn cụ thể cho chuyển dữ liệu, chẩn đoán kết nối hay automation.

**Nên đưa cả hai vào tài liệu khi** nhóm người dùng có cả developer thích HTTPie và nhóm vận hành quen `curl`. Hai snippet tự sinh giúp duy trì hai ví dụ từ cùng test, hạn chế sai lệch giữa các lệnh.

Không nên khẳng định HTTPie **luôn** tạo request byte-for-byte giống `curl`. Hai client có thể khác nhau ở headers mặc định, User-Agent, Content-Length, Accept-Encoding, thứ tự headers, JSON serialization hoặc cách xử lý redirect. Hợp đồng API thường yêu cầu tương đương về **method, URI, headers liên quan và nội dung payload**, không phải mọi byte đều trùng.

## 8. Kiểm soát kết quả và debug bằng HTTPie

HTTPie không chỉ gửi request mà còn có tùy chọn kiểm tra HTTP exchange và kết quả trên dòng lệnh:

| Tùy chọn | Công dụng |
| --- | --- |
| `--headers` hoặc `-h` | In response headers. |
| `--body` hoặc `-b` | In response body. |
| `--verbose` hoặc `-v` | Hiển thị request và response để debug. |
| `--print=Hh` | Chọn in request headers (`H`) và response headers (`h`). |
| `--print=HhBb` | In request headers/body cùng response headers/body. |
| `--offline` | Dựng và in request mà **không gửi mạng**; thích hợp kiểm tra cú pháp. |
| `--check-status` | Dùng HTTP status để quyết định exit code, hữu ích trong script. |
| `--follow` | Theo redirect khi cần; cần hiểu ảnh hưởng tới method và đích chuyển hướng. |

Ví dụ kiểm tra cú pháp request mà chưa gọi server:

~~~bash
http --offline POST https://api.example.com/api/books \
  Content-Type:application/json \
  title='Spring in Action' price:=199000
~~~

Lệnh `--offline` sẽ tạo request để kiểm tra ngay trên máy, không thực hiện tác vụ tạo sách. Nó chỉ kiểm chứng **cú pháp CLI**, không xác nhận endpoint tồn tại hay API đúng hợp đồng.

Để xem cả request và response khi gọi một server thật:

~~~bash
http --print=HhBb GET http://localhost:8080/api/books/42
~~~

Để dùng trong script và nhận exit code phản ánh HTTP error:

~~~bash
http --check-status GET http://localhost:8080/api/books/42
~~~

HTTPie thông thường có thể trả exit code thành công dù HTTP response báo lỗi nếu không bật kiểm tra status. Khi dùng `--check-status`, HTTPie trả mã lỗi cho các trạng thái HTTP lỗi (và cho redirect chưa được follow theo hành vi CLI); việc kiểm chứng nghiệp vụ vẫn cần đọc status và payload.

### Không nhầm exit code với assertion của Spring REST Docs

- `.andExpect(status().isOk())` trong MockMvc xác nhận status cụ thể do test yêu cầu.
- `--check-status` trong HTTPie chỉ giúp script phát hiện **nhóm status lỗi**.
- Một response `200` chứa dữ liệu sai vẫn có thể khiến cả `curl` và HTTPie hoàn thành bình thường. Khi cần độ tin cậy, kết hợp test có assertions về headers/body hoặc kiểm tra JSON phù hợp.

## 9. Tái hiện request trên môi trường thật

Snippet được sinh từ test có thể chứa URL mô tả như `https://api.example.com`. Đặc biệt với MockMvc, bài test có thể chạy **trong tiến trình**, không mở một cổng HTTP ở hostname đó.

Muốn thử bằng HTTPie, hãy chuẩn bị một server thực tế có thể truy cập:

~~~bash
http GET http://localhost:8080/api/books/42 Accept:application/json
~~~

Nếu không có server tại `localhost:8080`, lệnh sẽ báo lỗi kết nối. Việc đổi URL khi thử là bình thường, nhưng cần phân biệt URL minh họa với URI thực sự từng được test.

Những yếu tố làm kết quả thay đổi:

| Yếu tố | Trong test | Khi chạy HTTPie ngoài test |
| --- | --- | --- |
| Server | Có thể là MockMvc không dùng socket | Cần host/port hoạt động |
| Database | Fixture được nạp và rollback/reset | Có dữ liệu hiện tại của môi trường |
| Authentication | Có thể dùng mock user/security context | Cần credential hợp lệ |
| Tài nguyên tạo mới | Fixture/ID có thể cố định | Có thể tạo ID mới hoặc xảy ra xung đột |
| Clock/timestamp | Có thể được cố định trong test | Giá trị có thể thay đổi |
| Headers | Client test/REST Docs ghi một tập header | HTTPie có thêm header mặc định riêng |
| Response | Có assertion kiểm tra các điều kiện đã định nghĩa | Kết quả phụ thuộc vào môi trường và dữ liệu |

Ví dụ, `POST` tạo sách có thể trả `201` ở test nhưng trả `409 Conflict` khi chạy lại nếu sách đó đã tồn tại theo quy tắc nghiệp vụ. Đây có thể là khác biệt trạng thái dữ liệu, chưa đủ để kết luận snippet sai.

Muốn tài liệu **tái hiện được**, hãy cung cấp thêm hướng dẫn môi trường, tài khoản thử, dữ liệu tiên quyết và thứ tự thao tác cần thiết. Không đặt credential thật vào tài liệu.

## 10. Header xác thực, cookie và dữ liệu nhạy cảm

Một lệnh HTTPie có thể thêm header như sau:

~~~bash
http GET https://api.example.com/api/books/42 \
  'Authorization:Bearer <access-token>'
~~~

`<access-token>` ở đây chỉ là **placeholder**. Nó phải được thay bằng token thử nghiệm hợp lệ ở nơi sử dụng. Shell và history có thể lưu nguyên văn lệnh đã nhập; tránh dán token thật vào tài liệu, log CI hoặc lịch sử command có thể được chia sẻ.

Nếu test chứa dữ liệu nhạy cảm, dùng fixture giả hoặc request preprocessor của Spring REST Docs để xóa/chuẩn hóa phần xuất hiện trong snippet:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

// Ví dụ thay cho lời gọi .andDo(document(...)) trong một test:
.andDo(document("books-create",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie")
    )
));
~~~

Đây là ví dụ **thay thế lời gọi `document(...)`**, không phải lời gọi thêm vào test đã có cùng identifier. Nếu test còn dùng `requestFields(...)` hoặc những descriptor khác, cần đưa chúng vào cùng lời gọi `document(...)` này.

Điểm cần nhớ:

1. Loại header xác thực khỏi snippet giúp không phơi bày giá trị bí mật, nhưng lệnh được sinh có thể **không chạy được đối với endpoint cần authentication**. Cần giải thích cách người đọc thêm credential hợp lệ.
2. Khi muốn giữ header trong lệnh mẫu, nên thay giá trị bằng placeholder an toàn thay vì đưa token thật vào fixture. Chú ý khác biệt giữa request đã xử lý và request được biểu diễn trong tài liệu.
3. Không commit session files HTTPie có chứa token/cookie. HTTPie có hỗ trợ `--session`, nhưng file session có thể chứa thông tin xác thực, nên phải được quản lý như dữ liệu nhạy cảm.
4. Tránh dùng chế độ bỏ kiểm tra TLS chỉ để “cho lệnh chạy”; sửa chứng chỉ hoặc môi trường tin cậy thay vì hạ mức bảo vệ.
5. Các method `POST`, `PUT`, `PATCH` và `DELETE` có thể thay đổi dữ liệu. Hướng dẫn dùng tài nguyên thử và môi trường cho phép thực hành.

## 11. Chuẩn hóa URL và nội dung snippet

Trong ví dụ MockMvc phía trên:

~~~java
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
~~~

Các thuộc tính giúp REST Docs trình bày URI trong snippet theo hostname, scheme và port mong muốn. Chúng **không đổi cách ứng dụng test xử lý request** và không bảo đảm `api.example.com` là server có thật.

Khi cần trình bày hostname công khai khác với hostname trong operation, có thể dùng preprocessor `modifyUris()` cho bản ghi request được tài liệu hóa:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

// Ví dụ thay cho document(...) tại cuối chuỗi test:
.andDo(document("books-list",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.com")
            .removePort()
    )
));
~~~

Nếu `books-list` cần sinh bảng `query-parameters.adoc` như mục 6, hãy giữ `queryParameters(...)` trong cùng lời gọi `document(...)`. Cấu hình ví dụ trên không phải yêu cầu dùng đồng thời annotation và preprocessor; dự án có thể chọn cách phù hợp để bảo đảm URI thống nhất.

Spring REST Docs cũng cho phép tùy chỉnh template snippet hoặc tập snippet mặc định. Khi chỉ muốn giữ các ví dụ CLI cần thiết, có thể cấu hình snippet mặc định qua `RestDocumentationConfigurer` với các snippet như `CliDocumentation.httpieRequest()` hoặc `CliDocumentation.curlRequest()`. Việc thay đổi default snippets ảnh hưởng các file tự động sinh, nên cần cập nhật những lệnh `include` trong tài liệu theo đúng tập file còn lại.

## 12. WebTestClient và REST Assured

HTTPie snippet không chỉ dùng được với MockMvc. Spring REST Docs có module tích hợp WebTestClient và REST Assured; miễn client được cấu hình ghi operation đúng, nó có thể sinh các snippet request, response và CLI.

### 12.1. WebTestClient

Ví dụ cho client đã được cấu hình Spring REST Docs:

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

`expectStatus().isOk()` xác nhận response `200`, còn `consumeWith(document(...))` tạo các snippet cho operation với identifier `books-list-webtestclient`. Tích hợp tương ứng sử dụng `spring-restdocs-webtestclient` và cấu hình REST Docs trên client.

### 12.2. REST Assured

Với REST Assured, Spring REST Docs ghi operation qua **filter**:

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

// spec đã được cấu hình base URI/port và Spring REST Docs.
given(spec)
    .filter(document("books-list-restassured"))
    .accept("application/json")
.when()
    .get("/api/books?page=0&size=10")
.then()
    .statusCode(200);
~~~

Tích hợp này cần `spring-restdocs-restassured` và cấu hình filter/context output phù hợp. Filter có thể ghi snippet khi request được thực hiện, trước khi assertion `statusCode(200)` hoàn thành. Vì vậy, **phải yêu cầu test PASS trong CI** trước khi coi tài liệu hợp lệ.

### 12.3. So sánh cách gắn tài liệu

| Client | Cách gửi request | Cách ghi operation |
| --- | --- | --- |
| MockMvc | `mockMvc.perform(get(...))` | `.andDo(document("..."))` |
| WebTestClient | `webTestClient.get().uri(...).exchange()` | `.expectBody().consumeWith(document("..."))` |
| REST Assured | `given(spec).when().get(...)` | Filter `document("...")` trong request specification |

Không nên lấy một dòng `http POST ...` viết tay rồi nhận đó là output kiểm chứng của REST Docs. Phải chạy test và kiểm tra đúng file `httpie-request.adoc` mà operation sinh ra.

## 13. Đưa `httpie-request` vào Asciidoctor/Markdown

Một tài liệu API bằng Asciidoctor có thể đưa trực tiếp snippet HTTPie vào phần hướng dẫn dùng endpoint:

~~~asciidoc
= Books API

== Tạo sách

Gửi POST /api/books để tạo một cuốn sách.

=== Thử bằng HTTPie
include::{snippets}/books-create/httpie-request.adoc[]

=== Thử bằng curl
include::{snippets}/books-create/curl-request.adoc[]

=== Request fields
include::{snippets}/books-create/request-fields.adoc[]

=== Response
include::{snippets}/books-create/http-response.adoc[]

== Danh sách sách

=== Thử bằng HTTPie
include::{snippets}/books-list/httpie-request.adoc[]

=== Query parameters
include::{snippets}/books-list/query-parameters.adoc[]
~~~

Thuộc tính `snippets` phải được cấu hình trỏ tới output directory thực tế (ví dụ `build/generated-snippets`) trong quá trình Asciidoctor render. Một file `.adoc` có lệnh include như trên sẽ không tự biết nơi tìm snippet nếu build chưa định nghĩa attribute.

Nếu muốn soạn tài liệu bằng **Markdown**, cần chọn template Markdown hoặc bước chuyển đổi/nhúng snippet tương ứng. Markdown renderer thông thường **không tự hiểu** chỉ thị Asciidoctor `include::{snippets}/...[]`. Mục tiêu vẫn là lấy ví dụ từ bài test thay vì duy trì riêng những lệnh HTTPie dễ lỗi thời.

### Gắn vào build và CI

~~~mermaid
flowchart TD
    A["Chạy HTTP tests"] --> B{"Assertions đạt?"}
    B -->|Không| C["Pipeline thất bại"]
    B -->|Có| D["Sinh httpie-request và snippets khác"]
    D --> E["Biên soạn Asciidoctor/Markdown"]
    E --> F{"Include và render thành công?"}
    F -->|Không| C
    F -->|Có| G["Publish tài liệu"]
~~~

Cấu hình tác vụ build tài liệu **phụ thuộc vào test** để snippet được sinh trong lần chạy hiện tại. Tránh trường hợp một `httpie-request.adoc` từ lần build trước vẫn được include khi test mới không chạy hoặc không còn sinh đúng identifier.

Khi endpoint thay đổi (method, path, header, request body), sửa code và test tương ứng; chạy lại test, rồi để Spring REST Docs cập nhật snippet. Đây là lợi ích chính của cách viết tài liệu có kiểm chứng so với việc copy một lệnh HTTPie rồi chỉnh thủ công trên website.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không thấy `httpie-request.adoc` | Thiếu `document(...)`, test dừng trước điểm ghi, sai identifier/output directory hoặc đã tắt snippet mặc định | Kiểm tra test, cấu hình REST Docs và thư mục theo identifier. |
| Lệnh `http` không chạy | Chưa cài HTTPie CLI hoặc PATH không chứa command | Cài HTTPie CLI theo môi trường, kiểm tra `http --version`. |
| `http POST ...` trả `401` | Endpoint cần authentication; test giả lập user hoặc snippet đã mask header | Dùng credential thử hợp lệ; không đưa token thật vào source/docs. |
| Body số bị chuyển thành chuỗi | Dùng `price=199000` thay cho `price:=199000` | Dùng `:=` cho giá trị JSON dạng number/boolean/array/object. |
| API nhận form thay cho JSON | Dùng `--form` hoặc headers/body chưa phù hợp | Kiểm tra `Content-Type` và cách truyền data item. |
| Query parameters thiếu hoặc bị lặp | Nhầm `=` với `==` hoặc thêm tham số lên URL đã chứa query | Kiểm tra `http-request`; chỉ dùng một cách tạo query cho mỗi tham số cần thiết. |
| Lệnh lỗi trên PowerShell | Dấu `\` nối dòng, dấu nháy hoặc cú pháp shell không phù hợp | Dùng lệnh một dòng hoặc chuyển đổi dấu nối dòng/escape cho shell hiện tại. |
| `--offline` không trả dữ liệu sách | Tùy chọn này không gửi request | Bỏ `--offline` khi muốn gọi server thực tế. |
| Lệnh chạy lại được `409` thay vì `201` | Dữ liệu đã tồn tại hoặc trạng thái server thay đổi | Kiểm tra fixture, môi trường và hợp đồng API. |
| CI báo thành công dù HTTP response lỗi | Chưa dùng `--check-status` trong script, hoặc không có assertion phù hợp trong test | Thêm kiểm tra status, headers/body và điều kiện fail của pipeline. |
| Tài liệu chứa secret hoặc cookie thật | Dùng fixture thật hoặc chưa mask trước khi sinh snippet | Dùng dữ liệu giả, preprocessing hoặc placeholder an toàn. |
| Trang tài liệu tham chiếu snippet cũ | Build không chạy lại test hoặc include sai identifier | Buộc build phụ thuộc test, quản lý output dir và xác nhận file vừa được sinh. |

## 15. Bài thực hành

Hãy viết tài liệu cho API đơn hàng gồm ba HTTP operations giả định:

| Operation | Kết quả mong đợi | Identifier |
| --- | --- | --- |
| `GET /api/orders?page=0&size=5` | `200 OK` | `orders-list` |
| `POST /api/orders` với JSON `productId` và `quantity` | `201 Created` | `orders-create` |
| `GET /api/orders/101` | `200 OK` | `orders-get-one` |

Yêu cầu thực hiện:

1. Viết test riêng cho ba operation bằng MockMvc, WebTestClient hoặc REST Assured; kiểm tra HTTP status và các trường response quan trọng.
2. Gắn `document(...)` bằng identifier tương ứng và chạy test. Mở ba tệp `httpie-request.adoc` vừa sinh.
3. Với operation tạo đơn, kiểm tra sự khác biệt giữa `quantity=2` và `quantity:=2` trong HTTPie; xem payload có phù hợp JSON schema API không.
4. Với operation liệt kê, thử hai kiểu query: URL chứa `?page=0&size=5` và HTTPie request items `page==0 size==5`. Kiểm tra request được gửi.
5. So sánh cùng một operation trong `httpie-request.adoc`, `curl-request.adoc` và `http-request.adoc`. Giải thích phần nào tương đương và phần nào có thể khác do client.
6. Chạy `--offline` để xem request được dựng, sau đó chỉ gọi server local/staging có dữ liệu thử. So sánh response thật với assertion của test.
7. Include các snippet vào tài liệu Asciidoctor và cấu hình CI chạy test trước khi biên soạn/publish.

**Tiêu chí hoàn thành:** bạn đọc được lệnh HTTPie, chọn đúng method/URL/header/query/body, tạo snippet từ operation đã kiểm chứng, lựa chọn HTTPie hoặc `curl` theo nhu cầu người đọc và biết cách quản lý khác biệt môi trường lẫn dữ liệu nhạy cảm khi tái hiện request.

## Tài liệu tham khảo

- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs — Configuring Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [HTTPie CLI — Usage](https://httpie.io/docs/cli/usage)
- [HTTPie CLI — Request Items](https://httpie.io/docs/cli/request-items)
- [HTTPie CLI — Raw JSON](https://httpie.io/docs/cli/raw-json)
- [HTTPie CLI — Offline Mode](https://httpie.io/docs/cli/offline-mode)
