# Status, header và body trong response

## 1. Mục tiêu bài học

Trong một **HTTP operation**, phía client gửi request và phía server trả về **HTTP response**. Một response gồm ba thông tin cần đọc cùng nhau:

1. **Status code:** server thông báo kết quả xử lý request.
2. **Response headers:** metadata về biểu diễn dữ liệu, cache, chuyển hướng, tài nguyên mới hoặc điều kiện xử lý.
3. **Response body:** nội dung được trả về, nếu loại response đó được phép và có payload.

Đây là phần kiến thức của chương **HTTP operation** trong module `SPRING_REST_DOCS`. Mục tiêu xuyên suốt là tạo tài liệu REST API **có thể kiểm chứng** từ các bài kiểm thử HTTP sử dụng **MockMvc, WebTestClient hoặc REST Assured**; sinh snippet cho request, response, payload, tham số và headers; rồi biên soạn tài liệu Asciidoctor/Markdown trong build và CI.

Sau bài học, bạn có thể:

- Phân tích status line, response headers và body từ `http-response.adoc`.
- Phân biệt response `200`, `201`, `202`, `204`, `304` và các trường hợp `4xx`/`5xx`.
- Kiểm chứng status, header và payload bằng assertion độc lập, sau đó sinh `response-headers.adoc` và `response-fields.adoc`.
- Hiểu lúc nào response phải **không có body**, bất kể bài test có muốn mô tả thêm dữ liệu hay không.
- Dùng `responseFields(...)`, `optional()`, `ignored()`, `relaxedResponseFields(...)` có chủ đích.
- Tích hợp snippet thực tế vào Asciidoctor và bảo đảm tài liệu chỉ được phát hành sau khi test đạt.

> Spring REST Docs ghi lại **response mà HTTP test nhận được**; nó không tự đoán kết quả từ tên method controller hay bản mô tả API. Một snippet được tạo ra chưa chứng minh nghiệp vụ đúng nếu bài test thiếu assertion phù hợp.

## 2. Cấu trúc một HTTP response

Giả sử endpoint `GET /api/orders/101` trả một đơn hàng. Một response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v3"
Cache-Control: private, max-age=60

{"id":101,"state":"PAID","amount":250000,"items":[{"sku":"BOOK-42","quantity":2}]}
~~~

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| HTTP version hiển thị | `HTTP/1.1` | Cách biểu diễn response trong snippet; không mặc định nói rằng production chỉ hỗ trợ HTTP/1.1. |
| Status code | `200` | Mã số phân loại kết quả của request. |
| Reason phrase | `OK` | Cụm từ mô tả trong cú pháp HTTP/1.1; không phải dữ liệu nghiệp vụ để assertion dựa vào. |
| `Content-Type` | `application/json` | Media type của representation trong body. |
| `ETag` | `"order-v3"` | Validator dùng trong cache và các request có điều kiện khi API hỗ trợ. |
| `Cache-Control` | `private, max-age=60` | Chính sách cache được server công bố. |
| Dòng trống | Sau headers | Ngăn cách phần headers với body trong biểu diễn HTTP/1.1. |
| Response body | JSON của đơn hàng | Dữ liệu API trả cho người gọi. |

Ví dụ trên chỉ nhằm giải thích cấu trúc. Thứ tự header, sự xuất hiện của `Date`/`Content-Length`, charset, định dạng JSON và reason phrase tùy client/server, cấu hình và preprocessors. Nếu test sử dụng HTTP/2 hoặc HTTP/3, protocol không truyền status line `HTTP/1.1 200 OK` như bản văn bản minh họa; giá trị status được biểu diễn theo cơ chế protocol tương ứng.

**Ba thành phần này có quan hệ nhưng không thay thế nhau:** `200 OK` không tự chứng minh body đúng schema; `Content-Type: application/json` không tự chứng minh JSON chứa đúng dữ liệu; một JSON có vẻ hợp lệ không chứng minh server trả status thích hợp.

## 3. Nhóm HTTP status và ý nghĩa nghiệp vụ

| Nhóm | Ý nghĩa HTTP | Ví dụ hay gặp |
| --- | --- | --- |
| `1xx` | Thông tin/protocol đang tiếp diễn | `100 Continue`, `101 Switching Protocols` |
| `2xx` | Request được xử lý thành công theo ngữ nghĩa cụ thể | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` |
| `3xx` | Chuyển hướng hoặc sử dụng lại biểu diễn/cơ chế cache | `301`, `302`, `304 Not Modified`, `307`, `308` |
| `4xx` | Request không được chấp nhận hoặc không thể đáp ứng do điều kiện phía client | `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found` |
| `5xx` | Server hoặc một tầng xử lý server không đáp ứng được request | `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable` |

Nhóm status là định hướng ban đầu; **ngữ nghĩa chính xác nằm ở mã cụ thể và hợp đồng API**.

### 3.1. Các status cần phân biệt

| Status | Ví dụ sử dụng | Điểm cần assert/tài liệu hóa |
| --- | --- | --- |
| `200 OK` | Lấy một đơn hàng thành công | Body và `Content-Type` nếu response có representation. |
| `201 Created` | Tạo một đơn hàng mới | Status, `Location` nếu API quy định, body chứa ID nếu có. |
| `202 Accepted` | Gửi tác vụ xử lý bất đồng bộ | Chỉ bảo đảm được chấp nhận xử lý; mô tả cách kiểm tra tiến độ. |
| `204 No Content` | Xóa thành công, không trả body | Status `204` và response body rỗng. |
| `304 Not Modified` | Request có điều kiện và biểu diễn chưa đổi | Header cache/validator phù hợp, **không có response body**. |
| `400 Bad Request` | Tham số/body sai cú pháp hoặc không hợp lệ theo hợp đồng | Status và thông tin lỗi an toàn, dễ hiểu. |
| `401 Unauthorized` | Request thiếu/xác thực không hợp lệ | Yêu cầu xác thực, `WWW-Authenticate` khi áp dụng. |
| `403 Forbidden` | Server từ chối thực hiện request | Quy tắc phân quyền, có thể cố ý hạn chế thông tin lỗi. |
| `404 Not Found` | URI/tài nguyên được yêu cầu không tìm thấy | Status và payload lỗi theo hợp đồng. |
| `409 Conflict` | Trùng mã hoặc xung đột trạng thái | Mã lỗi/chi tiết xung đột để client xử lý. |
| `422 Unprocessable Content` | Dữ liệu có cấu trúc hiểu được nhưng không thể xử lý về ngữ nghĩa | Error fields và thông điệp theo thiết kế API. |
| `429 Too Many Requests` | Đạt giới hạn tốc độ | `Retry-After` nếu server cung cấp. |
| `500 Internal Server Error` | Lỗi server không cụ thể hơn | Body lỗi an toàn; không tiết lộ stack trace/secret. |
| `503 Service Unavailable` | Dịch vụ tạm không sẵn sàng | `Retry-After` nếu có; mô tả khả năng thử lại. |

**Hai nhầm lẫn phổ biến:**

- `201` cho biết đã tạo tài nguyên; `202` chỉ cho biết yêu cầu đã được chấp nhận, **không cam kết tác vụ phía sau hoàn tất**.
- `204` là thành công **không có response body**. Không vì muốn tài liệu “đầy đủ” mà thêm JSON vào một response `204`.

Một endpoint `POST` có thể trả `200`, `201` hoặc `202` tùy hợp đồng API. Spring REST Docs không ép mọi `POST` trả `201`. Tương tự, cùng một `DELETE` được gọi lặp lại có thể trả `204` ở lần đầu và `404` ở lần sau, tùy chính sách endpoint; điều đó không tự phủ định tính idempotent của method theo ngữ nghĩa HTTP.

### 3.2. “Lỗi” không đồng nghĩa chỉ nhìn vào status

Một test có thể trả `200` nhưng JSON thiếu trường quan trọng, `Location` sai hoặc giá trị `amount` không đúng. Do đó, nếu mục tiêu là tạo tài liệu API có thể kiểm chứng, luôn xem xét ba lớp assertion:

1. **Status**: thuộc nhóm/mã đúng hợp đồng.
2. **Headers**: media type, location, validator hoặc chính sách cache phù hợp.
3. **Body**: tồn tại hay rỗng, có đúng schema, kiểu dữ liệu và giá trị quan trọng.

## 4. Đọc và tài liệu hóa response headers

HTTP response header là metadata về cách client nên xử lý response. Một số header cần hiểu:

| Header | Mục đích | Ví dụ và lưu ý |
| --- | --- | --- |
| `Content-Type` | Media type của body, nếu có | `application/json`, `application/problem+json`, `text/plain`. |
| `Location` | Định vị tài nguyên mới hoặc đích chuyển hướng | `/api/orders/102` hoặc URI tuyệt đối; được dùng theo ngữ nghĩa status. |
| `ETag` | Validator của một representation | Ví dụ `"order-v3"`; dấu nháy là một phần cú pháp ETag. |
| `Last-Modified` | Thời điểm thay đổi representation | Có thể dùng với request có điều kiện `If-Modified-Since`. |
| `Cache-Control` | Chỉ thị chính sách cache | `no-store`, `private, max-age=60`. |
| `Vary` | Cho cache biết header request nào ảnh hưởng representation | Ví dụ `Vary: Accept-Language`. |
| `WWW-Authenticate` | Challenge cho cơ chế xác thực | Quan trọng với `401` theo HTTP authentication. |
| `Retry-After` | Gợi ý thời điểm/thời gian chờ trước khi thử lại | Có thể đi kèm `429` hoặc `503`. |
| `Content-Disposition` | Cách xử lý nội dung đính kèm/tải xuống | Ví dụ tải file; cần kiểm tra filename/encoding an toàn. |
| `Content-Length` | Kích thước body được truyền theo cơ chế tương ứng | Có thể vắng mặt; không nên khẳng định luôn có. |
| `Set-Cookie` | Yêu cầu client lưu cookie | Không đưa session cookie thật vào snippet công khai. |

HTTP field names không phân biệt chữ hoa/thường theo ngữ nghĩa giao thức, nhưng giá trị và quy tắc gộp của từng field khác nhau. Một số response có nhiều header cùng tên; ví dụ **không thể tùy tiện gộp `Set-Cookie` bằng dấu phẩy** như nhiều header dạng danh sách.

### 4.1. `Content-Type` và content negotiation

Client có thể gửi:

~~~http
GET /api/orders/101 HTTP/1.1
Accept: application/json
~~~

Server trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":101,"state":"PAID"}
~~~

`Accept` thuộc **request**; `Content-Type` thuộc **response**. Chúng có vai trò khác nhau. Nếu API hỗ trợ nhiều định dạng, server có thể chọn một representation dựa trên `Accept`; test nên kiểm tra response thực tế chứ không chỉ suy ra từ request header.

Trong MockMvc, `content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)` phù hợp khi API có thể gửi `application/json;charset=UTF-8` hoặc dạng media type tương thích. Nếu hợp đồng yêu cầu một media type chính xác, assertion cần phản ánh yêu cầu đó. Với `application/problem+json`, nên dùng media type thích hợp cho Problem Details, thay vì mặc định mọi lỗi phải trả `application/json`.

### 4.2. `Location` và `201 Created`

Response khi tạo tài nguyên có thể là:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/102
Content-Type: application/json

{"id":102,"state":"PENDING"}
~~~

Đây là ví dụ hợp đồng cụ thể: API tạo đơn hàng và trả URI tương đối trong `Location`. Một API có thể trả URI tuyệt đối hoặc có quy định riêng cho payload. Test cần khẳng định giá trị theo **hợp đồng thực tế**, không gán cứng một giả định cho mọi API.

### 4.3. `ETag` và response có điều kiện

Một request đọc tài nguyên có thể nhận:

~~~http
HTTP/1.1 200 OK
ETag: "order-v3"
Content-Type: application/json

{"id":101,"state":"PAID"}
~~~

Sau đó client gửi:

~~~http
GET /api/orders/101 HTTP/1.1
If-None-Match: "order-v3"
~~~

Nếu validator vẫn khớp theo quy tắc endpoint, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "order-v3"
Cache-Control: private, max-age=60
~~~

`304` cho biết client có thể dùng lại biểu diễn đã lưu theo ngữ nghĩa HTTP cache; nó **không mang response body**. Đây là một HTTP operation khác với `GET` thông thường trả `200`. Cần test riêng cho cả hai nhánh nếu API hỗ trợ conditional request.

## 5. Response body: dạng dữ liệu, kiểu trường và trường hợp rỗng

### 5.1. JSON object và JSON array

Một response JSON object minh họa:

~~~json
{
  "id": 101,
  "state": "PAID",
  "amount": 250000,
  "items": [
    {
      "sku": "BOOK-42",
      "quantity": 2
    }
  ]
}
~~~

Để tài liệu hóa field trong response JSON, Spring REST Docs dùng `responseFields(...)` với đường dẫn:

| JSON path của REST Docs | Kiểu dữ liệu minh họa | Diễn giải |
| --- | --- | --- |
| `id` | number | Mã đơn hàng. |
| `state` | string | Trạng thái nghiệp vụ. |
| `amount` | number | Tổng tiền theo đơn vị mà API công bố. |
| `items` | array | Danh sách dòng hàng. |
| `items[].sku` | string | Mã sản phẩm trên mỗi dòng. |
| `items[].quantity` | number | Số lượng trên mỗi dòng. |

`items[].sku` là cú pháp field path của REST Docs cho phần tử mảng, **khác với JSONPath assertion `$.items[0].sku`** vốn nhắm phần tử tại một chỉ số cụ thể. Nếu response là JSON array ngay ở root, đường dẫn phù hợp có thể là `[]` và `[].id`.

Với body XML, REST Docs cần media type tương thích `application/xml` để diễn giải và mô tả field theo XPath. Nếu API trả binary/stream hoặc dữ liệu không phải JSON/XML, cần cân nhắc snippet body và cách mô tả riêng; không giả định `responseFields(...)` luôn diễn giải được payload.

### 5.2. Body vắng mặt

Các trường hợp HTTP cần chú ý:

- `204 No Content`: không có response body.
- `304 Not Modified`: không có response body.
- Request `HEAD`: response không có body, dù có thể chứa metadata mô tả response mà `GET` tương ứng sẽ trả.
- Một response `200` có thể hợp lệ với body rỗng theo hợp đồng; đừng đánh đồng status `200` với sự hiện diện của JSON.

Vì vậy, với response không có body, hãy assert body rỗng và **không dùng `responseFields(...)` để mô tả một JSON không tồn tại**. Tài liệu có thể chỉ include `http-response.adoc` hoặc mô tả bằng văn bản.

### 5.3. Response lỗi và Problem Details

Với `GET /api/orders/999`, một API có thể trả lỗi theo [Problem Details for HTTP APIs (RFC 9457)](https://www.rfc-editor.org/rfc/rfc9457.html):

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Order 999 was not found",
  "instance": "/api/orders/999"
}
~~~

Body trên **chỉ là hợp đồng ví dụ**, không được Spring REST Docs tự sinh, và cũng không phải format mặc định được bảo đảm ở mọi ứng dụng Spring Boot. Những thành viên chuẩn như `type`, `title`, `status`, `detail` và `instance` có ý nghĩa theo RFC; API có thể có extension fields hoặc dùng format lỗi riêng. Test và mô tả phải theo response thật.

Không đưa stack trace, token, query chứa secret hay thông tin nội bộ vào error body công khai. Một tài liệu có kiểm chứng cần test nhánh lỗi đúng với hành vi mong đợi, không chỉ ví dụ thành công.

## 6. Các snippet response trong Spring REST Docs

Một HTTP test được ghi bằng `document("identifier")` có thể sinh sáu snippet mặc định; khi thêm descriptor phù hợp, sẽ có snippet dạng bảng:

| Snippet | Nội dung |
| --- | --- |
| `http-response.adoc` | Status line, response headers và body trong một biểu diễn HTTP. |
| `response-body.adoc` | Chỉ body phản hồi đã ghi nhận. |
| `response-headers.adoc` | Bảng mô tả headers được khai báo qua `responseHeaders(...)`. |
| `response-fields.adoc` | Bảng mô tả các field trong payload qua `responseFields(...)`. |
| `http-request.adoc` | Method, URL, headers và body của request tương ứng. |
| `curl-request.adoc` | Lệnh `curl` để thử request tương ứng. |
| `httpie-request.adoc` | Lệnh HTTPie để thử request tương ứng. |
| `request-body.adoc` | Body của request tương ứng. |

Sáu snippet mặc định gồm `curl-request`, `httpie-request`, `http-request`, `http-response`, `request-body` và `response-body`. Hai snippet bảng `response-headers` và `response-fields` chỉ xuất hiện nếu test khai báo các descriptor hoặc dự án có cấu hình tạo chúng tương ứng.

**Không có snippet mặc định tự liệt kê mọi status mà endpoint có thể trả.** Một `http-response` ghi **một response của một operation**. Nếu endpoint có cả `200` và `404`, hãy tạo test với identifier khác nhau, rồi biên soạn chúng thành các mục tài liệu.

## 7. Ví dụ hoàn chỉnh bằng MockMvc: xác nhận status, headers và JSON body

### 7.1. Điều kiện ban đầu

Ví dụ dành cho **Spring Boot 3.x, Spring MVC, JUnit 5 và Java 17+**, với dependency:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Nếu dự án dùng dependency management của Spring Boot, để cơ chế đó quản lý phiên bản tương thích.

**Giả định:** ứng dụng đã có endpoint `GET /api/orders/101`, fixture tạo sẵn đơn hàng `101`, và response đúng với JSON ở mục 5.1. Response còn chứa:

~~~http
Content-Type: application/json
ETag: "order-v3"
Cache-Control: private, max-age=60
~~~

Đây là điều kiện của ví dụ, **không phải hành vi tự có của REST Docs**. Nếu ứng dụng không tự cung cấp header/cache validator hoặc fixture, test dưới đây sẽ thất bại và phải cập nhật theo hợp đồng thật.

### 7.2. Test có đầy đủ ba lớp assertion

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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderResponseDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentOrderFound() throws Exception {
        mockMvc.perform(get("/api/orders/101")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(header().string(HttpHeaders.ETAG, "\"order-v3\""))
            .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "private, max-age=60"))
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.state").value("PAID"))
            .andExpect(jsonPath("$.amount").value(250000))
            .andExpect(jsonPath("$.items[0].sku").value("BOOK-42"))
            .andExpect(jsonPath("$.items[0].quantity").value(2))
            .andDo(document("orders-get-success",
                responseHeaders(
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Media type của response body"),
                    headerWithName(HttpHeaders.ETAG)
                        .description("Validator của biểu diễn đơn hàng"),
                    headerWithName(HttpHeaders.CACHE_CONTROL)
                        .description("Chính sách cache của response")
                ),
                responseFields(
                    fieldWithPath("id").description("Mã đơn hàng"),
                    fieldWithPath("state").description("Trạng thái đơn hàng"),
                    fieldWithPath("amount")
                        .description("Tổng tiền tính theo VND"),
                    fieldWithPath("items").description("Danh sách dòng hàng"),
                    fieldWithPath("items[].sku").description("Mã sản phẩm"),
                    fieldWithPath("items[].quantity")
                        .description("Số lượng sản phẩm")
                )
            ));
    }
}
~~~

Điểm quan trọng:

1. `status().isOk()` xác nhận chính xác `200`.
2. `contentTypeCompatibleWith(...)` kiểm tra response media type; `header().string(...)` kiểm chứng các giá trị `ETag` và `Cache-Control` theo hợp đồng minh họa.
3. `jsonPath(...)` xác nhận những giá trị quan trọng của JSON, độc lập với phần mô tả bảng field.
4. `responseHeaders(...)` sinh `response-headers.adoc` để **giải thích** các headers; descriptor header không thay thế assertion về giá trị header.
5. `responseFields(...)` sinh `response-fields.adoc`, đồng thời kiểm tra sự khớp của danh sách field với payload theo chế độ thông thường.
6. `document("orders-get-success", ...)` dùng identifier ổn định để nhóm snippet của operation.
7. `andDo(...)` đứng sau các `andExpect(...)`: khi assertion thất bại, đoạn document cuối chuỗi này không chạy.

Nếu response được tạo với dữ liệu biến thiên như timestamp, ID hoặc `ETag` không cố định, hãy dùng fixture ổn định hoặc assertion đúng đặc tính contract, thay vì phụ thuộc vào giá trị tình cờ của môi trường.

### 7.3. Cấu trúc file và nội dung sinh ra

Sau khi test thành công, output thông thường là:

~~~text
build/generated-snippets/
└── orders-get-success/
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    ├── response-headers.adoc
    └── response-fields.adoc
~~~

Bốn snippet liên quan trực tiếp đến bài học có vai trò:

- `http-response.adoc` cho biết response thực tế được ghi.
- `response-body.adoc` tách body riêng để trình bày.
- `response-headers.adoc` giải thích các header mà test đã mô tả.
- `response-fields.adoc` giải thích schema của JSON đã được mô tả.

Nội dung **minh họa** của `orders-get-success/http-response.adoc`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v3"
Cache-Control: private, max-age=60

{"id":101,"state":"PAID","amount":250000,"items":[{"sku":"BOOK-42","quantity":2}]}
~~~

Thứ tự header, định dạng JSON, reason phrase và các headers bổ sung có thể khác. Muốn biết **chính xác** test đã sinh gì, hãy mở file trong thư mục output sau khi chạy test.

## 8. Tạo tài liệu cho các kết quả khác nhau

### 8.1. `201 Created`: status, `Location` và body

Giả sử `POST /api/orders` với JSON hợp lệ trả `201 Created`, `Location: /api/orders/102` và body:

~~~json
{"id":102,"state":"PENDING"}
~~~

Bên trong lớp test đã cấu hình ở mục 7, thêm static import:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
~~~

Và một method kiểm thử riêng:

~~~java
@Test
void documentOrderCreated() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {"productId":"BOOK-42","quantity":1}
                """))
        .andExpect(status().isCreated())
        .andExpect(header().string(HttpHeaders.LOCATION, "/api/orders/102"))
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(102))
        .andExpect(jsonPath("$.state").value("PENDING"))
        .andDo(document("orders-create",
            responseHeaders(
                headerWithName(HttpHeaders.LOCATION)
                    .description("URI của đơn hàng mới"),
                headerWithName(HttpHeaders.CONTENT_TYPE)
                    .description("Định dạng response body")
            ),
            responseFields(
                fieldWithPath("id").description("Mã đơn hàng mới"),
                fieldWithPath("state").description("Trạng thái khởi tạo")
            )
        ));
}
~~~

Mã `102` phải xuất phát từ fixture hoặc cơ chế tạo ID có thể dự đoán của **ứng dụng trong test**. Nếu ID do cơ sở dữ liệu cấp động, hãy thiết kế fixture và assertion thích hợp để test không phụ thuộc vào thứ tự chạy; đừng mô tả ID giả như response thật.

**Điểm kiểm chứng:** status `201` thể hiện việc tạo thành công; header `Location` và body theo hợp đồng minh họa giúp client tìm lại tài nguyên mới. Không coi `Location` hoặc body là mặc định bắt buộc ở mọi API tạo tài nguyên mà không đọc hợp đồng cụ thể.

### 8.2. `204 No Content`: không có body để mô tả

Giả sử `DELETE /api/orders/101` trả `204` và body rỗng. Thêm import:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
~~~

Test:

~~~java
@Test
void documentOrderDeleted() throws Exception {
    mockMvc.perform(delete("/api/orders/101"))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""))
        .andDo(document("orders-delete"));
}
~~~

Snippet `http-response.adoc` có thể tương tự:

~~~http
HTTP/1.1 204 No Content
~~~

Nếu server gửi headers hợp lệ, chúng vẫn có thể xuất hiện trong snippet. **Không khai báo `responseFields(...)`** cho một JSON không tồn tại. `response-body.adoc` có thể rỗng; không nên hiểu việc file tồn tại là chứng cứ response có payload.

### 8.3. `304 Not Modified`: status và validator

Nếu ứng dụng hỗ trợ ETag và conditional request, có thể kiểm thử:

~~~java
@Test
void documentOrderNotModified() throws Exception {
    mockMvc.perform(get("/api/orders/101")
            .header(HttpHeaders.IF_NONE_MATCH, "\"order-v3\""))
        .andExpect(status().isNotModified())
        .andExpect(header().string(HttpHeaders.ETAG, "\"order-v3\""))
        .andExpect(content().string(""))
        .andDo(document("orders-not-modified",
            responseHeaders(
                headerWithName(HttpHeaders.ETAG)
                    .description("ETag của representation đã được xác thực")
            )
        ));
}
~~~

Đây là ví dụ có **điều kiện tiên quyết**: endpoint phải được triển khai với cơ chế validator phù hợp. Nếu endpoint bỏ qua `If-None-Match` và trả `200`, không sửa mong đợi thành `304` chỉ để làm tài liệu đẹp hơn.

Với `304`, response không có body; không sinh bảng `response-fields` cho trường hợp này. Tương tự, khi kiểm thử `HEAD` cần phân biệt metadata có thể được trả về với **response body không được gửi**.

### 8.4. `404 Not Found`: status và body lỗi

Giả sử API trả Problem Details cụ thể như mục 5.3, có thể bổ sung:

~~~java
@Test
void documentOrderNotFound() throws Exception {
    mockMvc.perform(get("/api/orders/999")
            .accept(MediaType.APPLICATION_PROBLEM_JSON))
        .andExpect(status().isNotFound())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
        .andExpect(jsonPath("$.status").value(404))
        .andExpect(jsonPath("$.title").value("Order not found"))
        .andDo(document("orders-get-not-found",
            responseFields(
                fieldWithPath("type").description("URI loại vấn đề"),
                fieldWithPath("title").description("Tiêu đề lỗi"),
                fieldWithPath("status").description("HTTP status code"),
                fieldWithPath("detail").description("Giải thích lỗi"),
                fieldWithPath("instance")
                    .description("Đường dẫn occurrence của vấn đề")
            )
        ));
}
~~~

Nếu ứng dụng thực tế không trả Problem Details hoặc không trả đủ những field này, hãy thay test và descriptor theo **response thật**. `APPLICATION_PROBLEM_JSON` và schema minh họa không phải nghĩa vụ tự động của REST Docs.

Tách `orders-get-success` và `orders-get-not-found` thành **hai identifier** để không ghi đè snippet hai nhánh `200` và `404` của cùng endpoint.

## 9. Descriptor response: strict, optional, ignored, relaxed

### 9.1. `responseHeaders(...)` kiểm tra header được khai báo

REST Docs sử dụng:

~~~java
responseHeaders(
    headerWithName(HttpHeaders.CONTENT_TYPE)
        .description("Media type của response body"),
    headerWithName(HttpHeaders.ETAG)
        .description("Validator dùng cho cache")
        .optional()
)
~~~

Theo cơ chế thông thường:

- Header được mô tả và **không đánh dấu optional** phải hiện diện trong response, nếu thiếu sẽ làm bước sinh snippet thất bại.
- Header `.optional()` có thể vắng mặt.
- **Header khác chưa được khai báo** không mặc nhiên làm thất bại snippet `response-headers`. Bảng chỉ chứa các header được mô tả.

Ví dụ, nếu API trả thêm `Date` thì bảng `response-headers` không buộc bạn phải liệt kê `Date` trừ khi muốn giải thích nó. Để kiểm chứng **giá trị** `ETag` hoặc `Location`, cần assertion `header().string(...)` thích hợp; descriptor chỉ mô tả sự có mặt và ý nghĩa.

### 9.2. `responseFields(...)` kiểm tra cấu trúc payload

Ví dụ:

~~~java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("state").description("Trạng thái"),
    fieldWithPath("amount").description("Tổng tiền"),
    fieldWithPath("items").description("Danh sách dòng hàng"),
    fieldWithPath("items[].sku").description("Mã hàng"),
    fieldWithPath("items[].quantity").description("Số lượng")
)
~~~

Trong chế độ thường (*strict*), nếu response có field không được mô tả hoặc một field **bắt buộc đã mô tả** không có trong payload, bước tạo snippet báo lỗi. Nhờ vậy, khi response schema thay đổi, test có thể cảnh báo tài liệu đã lạc hậu.

Các biến thể cần hiểu rõ:

| Công cụ | Khi sử dụng | Ảnh hưởng |
| --- | --- | --- |
| `.optional()` | Field đôi khi không xuất hiện | Không fail chỉ vì field đó vắng mặt. |
| `.ignored()` | Field có mặt nhưng không cần đưa vào bảng | Không hiển thị field trong snippet và tránh lỗi field chưa mô tả. |
| `relaxedResponseFields(...)` | Chỉ muốn mô tả một phần payload | Bỏ qua field **bổ sung chưa mô tả**, nhưng vẫn yêu cầu các descriptor không optional phải thỏa. |
| `subsectionWithPath("items")` | Chỉ muốn mô tả tổng quan một phần cây payload | Các field con trong subtree đó được coi là đã tài liệu hóa khi dùng descriptor subsection. |
| `fieldWithPath("items[].sku")` | Mô tả field trong phần tử array | Dùng đường dẫn theo cú pháp JSON field path của REST Docs. |

Ví dụ một field tùy chọn:

~~~java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("state").description("Trạng thái"),
    fieldWithPath("note").description("Ghi chú tùy chọn").optional()
)
~~~

Đoạn trên minh họa **descriptor**, không thay trực tiếp được danh sách đầy đủ của ví dụ lớn nếu response còn `amount` và `items` nhưng chưa mô tả. Trong strict mode, những field đó sẽ làm test thất bại.

### 9.3. Descriptor không kiểm chứng giá trị nghiệp vụ

`fieldWithPath("amount").description("Tổng tiền tính theo VND")` không tự khẳng định amount lớn hơn 0, khớp tổng tiền các dòng hàng hoặc là đơn vị VND thực sự. `fieldWithPath("state")` cũng không tự chứng minh state thuộc enum hợp lệ.

Cần thêm assertion nghiệp vụ như `jsonPath("$.amount").value(250000)`, test giới hạn/validation, hoặc dùng validator phù hợp. Nên tránh chuyển toàn bộ `responseFields(...)` sang relaxed mode chỉ để test xanh khi API thay đổi, vì việc đó có thể che giấu schema drift.

## 10. Preprocess response: trình bày rõ ràng và bảo vệ dữ liệu

Snippet được sinh từ HTTP test có thể chứa header biến thiên, cookie, trace ID, timestamp hoặc body JSON khó đọc. Spring REST Docs hỗ trợ **preprocessResponse(...)** để biến đổi **bản ghi sử dụng trong tài liệu**.

Ví dụ thay lời gọi `.andDo(document(...))` cuối chuỗi test bằng cấu hình format JSON và loại header nhạy cảm:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;

// Trong test đã có các .andExpect(...):
.andDo(document("orders-get-success",
    preprocessResponse(
        modifyHeaders()
            .remove("Set-Cookie")
            .remove("X-Internal-Trace"),
        prettyPrint()
    ),
    responseHeaders(
        headerWithName(HttpHeaders.CONTENT_TYPE)
            .description("Media type của JSON response"),
        headerWithName(HttpHeaders.ETAG)
            .description("Validator của representation"),
        headerWithName(HttpHeaders.CACHE_CONTROL)
            .description("Chính sách cache")
    ),
    responseFields(
        fieldWithPath("id").description("Mã đơn hàng"),
        fieldWithPath("state").description("Trạng thái"),
        fieldWithPath("amount").description("Tổng tiền"),
        fieldWithPath("items").description("Danh sách dòng hàng"),
        fieldWithPath("items[].sku").description("Mã hàng"),
        fieldWithPath("items[].quantity").description("Số lượng")
    )
));
~~~

Đây là **cách thay thế lời gọi `document(...)`**, không ghép thêm một lời gọi thứ hai với cùng identifier. Nó giả định các assertion về `ETag` và `Cache-Control` đã đạt, và những header này vẫn hiện diện trong bản ghi sau preprocess.

Các nguyên tắc quan trọng:

- Dùng **fixture giả** từ đầu; không đưa cookie, token hay dữ liệu cá nhân thật vào HTTP test phục vụ tài liệu công khai.
- `prettyPrint()` giúp đọc JSON rõ hơn nhưng không sửa logic ứng dụng và không thay thế assertion.
- Nếu xóa một header khỏi response được tài liệu hóa, đừng đồng thời khai báo header đó là bắt buộc trong `responseHeaders(...)`, trừ khi cấu hình khác đáp ứng descriptor.
- Khi cần giữ header để giải thích ý nghĩa nhưng che giá trị, cân nhắc `modifyHeaders().set("X-Trace-Id", "example-trace")` trên header thực sự tồn tại.
- Preprocessor không thay đổi **response gốc** mà ứng dụng đã trả trong bài test; không thể dùng kết quả đã mask như bằng chứng server đã gửi giá trị mới.
- Với body chứa dữ liệu biến thiên, ưu tiên fixture ổn định hoặc preprocessor có chủ đích; không dùng thay thế nội dung để che sai hợp đồng API.

## 11. WebTestClient và REST Assured

Spring REST Docs có tích hợp cho nhiều HTTP test client. Cách sinh snippet khác nhau ở cú pháp, nhưng cả ba đều ghi một **HTTP operation**.

### 11.1. WebTestClient

Giả sử `webTestClient` đã tích hợp Spring REST Docs, và endpoint `GET /api/orders/101` trả `200` với JSON và `ETag` theo hợp đồng:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
    .uri("/api/orders/101")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader().valueEquals(HttpHeaders.ETAG, "\"order-v3\"")
    .expectBody()
    .jsonPath("$.id").isEqualTo(101)
    .jsonPath("$.state").isEqualTo("PAID")
    .consumeWith(document("orders-get-webtestclient",
        responseHeaders(
            headerWithName(HttpHeaders.ETAG)
                .description("Validator của representation")
        ),
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng"),
            fieldWithPath("state").description("Trạng thái"),
            fieldWithPath("amount").description("Tổng tiền"),
            fieldWithPath("items").description("Danh sách dòng hàng"),
            fieldWithPath("items[].sku").description("Mã hàng"),
            fieldWithPath("items[].quantity").description("Số lượng")
        )
    ));
~~~

Đoạn code giả định response có đúng payload đã nêu ở mục 5.1 và client đã được cấu hình REST Docs. Module tích hợp là `spring-restdocs-webtestclient`; cần cấu hình extension/configurer phù hợp với Spring WebFlux hoặc cách bind client trong dự án.

### 11.2. REST Assured

Với REST Assured, Spring REST Docs dùng **filter** ghi operation. Ví dụ với `RequestSpecification` `spec` đã được cấu hình base URL, port và REST Docs:

~~~java
import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

// spec: RequestSpecification đã cấu hình cho server test và REST Docs.
given(spec)
    .filter(document("orders-get-restassured",
        responseHeaders(
            headerWithName("ETag").description("Validator của đơn hàng")
        )
    ))
    .accept("application/json")
.when()
    .get("/api/orders/101")
.then()
    .statusCode(200)
    .header("ETag", "\"order-v3\"")
    .body("id", equalTo(101))
    .body("state", equalTo("PAID"));
~~~

Tích hợp dùng module `spring-restdocs-restassured` và cấu hình filter tương ứng. Filter ghi operation trong quá trình thực hiện request, có thể **trước các assertion ở `then()`**; vì vậy chỉ coi tài liệu hợp lệ và publish khi **toàn bộ test/pipeline PASS**.

### 11.3. So sánh vị trí kiểm chứng và ghi tài liệu

| Client | Kiểm chứng status/header/body | Ghi snippet |
| --- | --- | --- |
| MockMvc | `andExpect(status...)`, `header(...)`, `jsonPath(...)` | `andDo(document("..."))` |
| WebTestClient | `expectStatus(...)`, `expectHeader(...)`, `expectBody()` | `consumeWith(document("..."))` |
| REST Assured | `then().statusCode(...)`, `header(...)`, `body(...)` | Filter `document("...")` |

Cả ba client không nhất thiết có cùng header mặc định hoặc transport behavior. Đừng yêu cầu output byte-for-byte giống nhau nếu mục tiêu chỉ là kiểm chứng hợp đồng REST API.

## 12. Biên soạn tài liệu Asciidoctor/Markdown

Một trang Asciidoctor có thể trình bày rõ từng status được test:

~~~asciidoc
= Orders API

== Lấy một đơn hàng

=== Thành công: 200 OK

HTTP request:
include::{snippets}/orders-get-success/http-request.adoc[]

HTTP response:
include::{snippets}/orders-get-success/http-response.adoc[]

Response headers:
include::{snippets}/orders-get-success/response-headers.adoc[]

Response fields:
include::{snippets}/orders-get-success/response-fields.adoc[]

=== Không tìm thấy: 404 Not Found

include::{snippets}/orders-get-not-found/http-response.adoc[]
include::{snippets}/orders-get-not-found/response-fields.adoc[]

== Tạo đơn hàng: 201 Created

include::{snippets}/orders-create/http-response.adoc[]
include::{snippets}/orders-create/response-headers.adoc[]

== Xóa đơn hàng: 204 No Content

include::{snippets}/orders-delete/http-response.adoc[]

== Chưa thay đổi: 304 Not Modified

include::{snippets}/orders-not-modified/http-response.adoc[]
~~~

Thuộc tính Asciidoctor `snippets` phải được build cấu hình trỏ đúng thư mục sinh snippet (ví dụ `build/generated-snippets`). Nếu source tài liệu ở thư mục khác, đường dẫn tương đối và cấu hình plugin cần được xác định cho phù hợp.

Với Markdown renderer thuần, cú pháp `include::{snippets}/...[]` không tự động hoạt động. Nếu muốn biên soạn Markdown, phải có template hoặc bước chuyển đổi/nhúng tương ứng. Trọng tâm là **lấy dữ liệu từ HTTP test vừa chạy**.

### 12.1. Pipeline bảo đảm tài liệu được kiểm chứng

~~~mermaid
flowchart TD
    A["Chạy HTTP tests"] --> B{"Status/header/body assertions pass?"}
    B -->|Không| C["CI fail, không publish"]
    B -->|Có| D["Spring REST Docs tạo snippets"]
    D --> E["Asciidoctor/Markdown build"]
    E --> F{"Include và render thành công?"}
    F -->|Không| C
    F -->|Có| G["Đóng gói hoặc publish tài liệu"]
~~~

Cấu hình task build tài liệu phụ thuộc vào test sinh snippet và để pipeline thất bại khi test fail hoặc snippet thiếu. **Snippet cũ còn sót** từ lần chạy trước có thể khiến trang tài liệu trông hợp lệ khi operation hiện tại không còn chạy; dự án cần kiểm soát output directory, dependencies và artifacts để chỉ xuất bản theo lần kiểm thử hiện hành.

### 12.2. Mức kiểm chứng nào là đủ?

- Assert **status** cho từng nhánh quan trọng.
- Assert **headers thiết yếu** và các giá trị nghiệp vụ có liên quan: `Location`, `ETag`, media type, cache policy nếu thuộc hợp đồng.
- Assert **body** và schema tương ứng; không mô tả field JSON ở status không có body.
- Viết riêng test cho **happy path**, **resource not found**, validation error, conflict và các nhánh có điều kiện nếu API hỗ trợ.
- Sinh snippet từng trường hợp với identifier ổn định; đưa vào một trang tài liệu giải thích cách client nhận biết và xử lý kết quả.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `http-response.adoc` hiển thị `404` thay vì `200` | Fixture không có tài nguyên, URL sai, hoặc endpoint không khớp | Sửa fixture/request; thêm `status().isOk()` để phát hiện sớm. |
| Có `200` nhưng JSON sai field/giá trị | Test chỉ kiểm tra status | Thêm `jsonPath(...)` và `responseFields(...)`. |
| `response-headers.adoc` không được sinh | Thiếu `responseHeaders(...)` | Khai báo các header cần mô tả khi gọi `document(...)`. |
| Test báo thiếu header trong snippet | Header descriptor bắt buộc nhưng server không trả | Kiểm tra hợp đồng, response thực tế và preprocessing. |
| Header `Date` hoặc `Server` không có trong bảng | Các header đó chưa được khai báo trong descriptor | Chỉ thêm khi thực sự cần giải thích hợp đồng; bảng không tự liệt kê mọi header. |
| `response-fields.adoc` báo field chưa được mô tả | JSON có field mới, path sai hoặc descriptor thiếu | Cập nhật schema/descriptor; chỉ dùng relaxed mode có chủ đích. |
| `204`/`304` xuất hiện cùng JSON body | Nhầm snippet hoặc endpoint vi phạm ngữ nghĩa HTTP | Kiểm tra đúng identifier và loại body khỏi response theo hợp đồng. |
| Status `201` nhưng `Location` sai | Test thiếu assertion header, URI bị build sai | Assert `Location` cụ thể hoặc theo pattern phù hợp. |
| `Content-Type` không giống mong đợi | API đổi representation hoặc có media type khác | Dùng assertion phù hợp và cập nhật hợp đồng, tránh gán cứng không cần thiết. |
| Response lỗi lộ stack trace/secret | Exception handler trả nội dung nội bộ | Sửa error handler, fixture và quy trình sinh tài liệu. |
| `ETag` không ổn định khiến test flaky | Test data hoặc validator phụ thuộc dữ liệu biến thiên | Dùng fixture ổn định và assertion đúng contract validator. |
| CI publish snippet cũ dù test fail | Task tài liệu không phụ thuộc test, output tồn dư | Cấu hình dependencies/outputs, fail pipeline khi test hoặc include lỗi. |

## 14. Bài thực hành

Giả sử bạn xây dựng API kho hàng với các HTTP operation:

| Request | Status kỳ vọng | Headers/body cần kiểm tra | Identifier |
| --- | --- | --- | --- |
| `GET /api/inventory/42` | `200 OK` | `Content-Type` JSON, body `sku`/`available`/`quantity` | `inventory-get` |
| `POST /api/inventory` | `201 Created` | `Location`, body ID mới | `inventory-create` |
| `DELETE /api/inventory/42` | `204 No Content` | Body rỗng | `inventory-delete` |
| `GET /api/inventory/999` | `404 Not Found` | Body lỗi theo schema đã chọn | `inventory-not-found` |
| `GET /api/inventory/42` với `If-None-Match` | `304 Not Modified` nếu validator khớp | `ETag`, body rỗng | `inventory-not-modified` |

Thực hiện:

1. Chuẩn bị API và fixture ổn định; viết test cho ít nhất bốn nhánh đầu, bổ sung nhánh `304` nếu API hỗ trợ conditional request.
2. Assert status, headers có ý nghĩa và body đúng schema. Dùng `content().string("")` để kiểm tra trường hợp không body khi dùng MockMvc.
3. Gắn `document(...)` bằng identifier độc lập. Với `200`, `201` và `404`, sinh `response-fields.adoc` từ descriptor phù hợp; với `204`/`304` không mô tả JSON body.
4. Cố tình thêm một field vào response `200` mà chưa khai báo trong `responseFields(...)` để quan sát lỗi strict; sau đó cập nhật tài liệu cho khớp.
5. Mở `http-response.adoc`, `response-headers.adoc` và `response-fields.adoc`. Giải thích sự khác biệt giữa **bản ghi response** và **bảng mô tả hợp đồng**.
6. Thử thêm `prettyPrint()` trong `preprocessResponse(...)` và xác nhận assertion trên response thật vẫn như trước.
7. Include các snippet trong Asciidoctor, chạy pipeline và kiểm tra rằng tài liệu không được publish nếu một assertion thất bại.

**Tiêu chí hoàn thành:** bạn giải thích được status, headers và body của mỗi response; không mô tả body cho status không có body; tạo đúng các snippet từ test đã kiểm chứng; và nối quá trình sinh tài liệu vào build/CI để giảm sai lệch giữa API và tài liệu.

## Tài liệu tham khảo

- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
