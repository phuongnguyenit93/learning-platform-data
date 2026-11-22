# Tránh đưa secret hoặc dữ liệu nhạy cảm vào URI

Trong chương **Thiết kế URI** của module **INTEGRATION_API_REST**, bài này tập trung vào cách định danh resource mà không biến địa chỉ API thành nơi mang mật khẩu, token hoặc thông tin cá nhân. Các ví dụ gắn thiết kế URI với phương thức HTTP, hợp đồng dữ liệu, xác thực, phân quyền, phân trang, cache và kiểm thử trong một API Java/Spring.

Sau bài học, bạn có thể:

- Nhận diện secret và dữ liệu nhạy cảm trong path, query và các thành phần khác của URL.
- Chọn vị trí truyền dữ liệu phù hợp: URI, header hoặc request body.
- Thiết kế lại endpoint đang dùng email, mật khẩu hoặc token trong địa chỉ.
- Đặt yêu cầu cho logging, thông báo lỗi, tài liệu API và các luồng dùng liên kết có chữ ký.

Mọi địa chỉ, email, ID và token trong bài đều là dữ liệu minh họa. Các HTTP message được rút gọn, không hiển thị toàn bộ header đóng khung thông điệp. Các request phải được gửi qua HTTPS.

## 1. URI nên định danh resource bằng dữ liệu nào?

Một URI thường cần được sao chép, lưu lại hoặc xuất hiện trong công cụ vận hành. Vì vậy, hãy thiết kế địa chỉ với giả định rằng nhiều người và nhiều thành phần hơn dự kiến có thể nhìn thấy nó. RFC 9110 cảnh báo cụ thể về việc thông tin cá nhân và dữ liệu nhạy cảm trong URI có thể xuất hiện trên màn hình, bookmark và log. [RFC 9110, mục 17.9](https://www.rfc-editor.org/rfc/rfc9110.html#section-17.9).

Ví dụ:

```text
https://api.example.test/v1/customers/cus_demo_73?view=summary#details
                        └──────── path ─────────┘ └─ query ─┘└fragment┘
```

Trong HTTP request gửi đến máy chủ, request target thường chứa path và query:

```http
GET /v1/customers/cus_demo_73?view=summary HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_DEMO
```

Fragment không được gửi trong HTTP request target. Tuy nhiên, fragment vẫn có thể tồn tại trong URL phía trình duyệt và được mã JavaScript đọc. Chuyển secret sang sau dấu `#` không tạo thành nơi lưu trữ an toàn cho ứng dụng. [RFC 9110, mục 17.11](https://www.rfc-editor.org/rfc/rfc9110.html#section-17.11).

### 1.1. Phân biệt secret và dữ liệu nhạy cảm

**Secret** là giá trị cần giữ bí mật vì việc sở hữu nó có thể cho phép xác thực, truy cập hoặc thực hiện một hành động. **Dữ liệu nhạy cảm** có phạm vi rộng hơn: việc tiết lộ dữ liệu có thể ảnh hưởng quyền riêng tư hoặc hoạt động của tổ chức, dù bản thân nó không phải thông tin đăng nhập.

| Nhóm | Ví dụ | Vấn đề nếu xuất hiện trong URI |
| --- | --- | --- |
| Thông tin xác thực | Mật khẩu, API key, access token, refresh token | Người đọc địa chỉ có thể thu được thông tin truy cập |
| Giá trị khôi phục hoặc xác nhận | Token đặt lại mật khẩu, mã dùng một lần | Có thể bị sử dụng trước chủ thể hợp lệ |
| Thông tin cá nhân | Email, số điện thoại, số giấy tờ | Liên kết một hoạt động với một cá nhân cụ thể |
| Dữ liệu nghiệp vụ cần bảo vệ | Nội dung hồ sơ sức khỏe, điều kiện báo giá riêng | Bộc lộ nội dung nghiệp vụ qua địa chỉ và công cụ vận hành |
| Định danh nội bộ | Mã khách hàng, ID đơn hàng | Có thể cho phép liên kết dữ liệu; cần đánh giá theo ngữ cảnh |

Một giá trị không tự trở thành secret chỉ vì nó là ID. Ngược lại, một ID khó đoán vẫn có thể là dữ liệu cần bảo vệ nếu nó gắn với một cá nhân hoặc một hoạt động nhạy cảm.

Ví dụ, `/v1/orders/ord_demo_73` không chứa mật khẩu, nhưng quyền đọc đơn hàng vẫn phải được kiểm tra. Không được dùng sự khó đoán của ID làm cơ chế phân quyền.

### 1.2. Những cách biểu diễn không che được dữ liệu

Các địa chỉ sau đều cần thiết kế lại:

```text
/v1/orders?access_token=TOKEN_DEMO
/v1/partners?apiKey=KEY_DEMO
/v1/users/an.demo%40example.test
/v1/accounts/reset/TOKEN_DEMO
https://user_demo:password_demo@api.example.test/v1/orders
```

Đưa token vào path thay cho query vẫn đặt token trong URI. Đổi tên `access_token` thành `q`, `data` hoặc `session` cũng không thay đổi bản chất.

Percent-encoding, chẳng hạn `%40` thay cho `@`, phục vụ biểu diễn ký tự. Base64 cũng là cách mã hóa biểu diễn có thể đảo ngược. Cả hai không phải mã hóa bảo mật.

JWT được ký thông thường bảo vệ tính toàn vẹn của thông tin, không mặc nhiên giữ bí mật payload. Không suy luận rằng một chuỗi dài có dấu chấm hoặc một chữ ký đi kèm đã an toàn để đưa vào URL.

## 2. HTTPS không ngăn dữ liệu URI xuất hiện ở nơi khác

HTTPS bảo vệ dữ liệu trên từng kết nối TLS giữa các bên tham gia. Nó không làm cho URI trở nên bí mật đối với thành phần kết thúc TLS hoặc ứng dụng xử lý request.

Ví dụ một hệ thống triển khai như sau:

```text
Ứng dụng khách
    |
    | HTTPS
    v
Gateway kết thúc TLS -----> access log / bộ thu thập sự kiện
    |
    | kết nối nội bộ được bảo vệ
    v
Ứng dụng Java/Spring -----> log ứng dụng / tracing / báo lỗi
```

Trong mô hình này, gateway nhìn thấy request target sau khi giải mã kết nối. Nếu gateway ghi nguyên URI vào access log, token trong query đã đi vào hệ thống log trước khi controller Java được gọi. Bộ lọc che dữ liệu ở controller không sửa được bản log đã tạo ở gateway.

Các tình huống cần xét khi thiết kế API:

| Vị trí | Tình huống minh họa | Hệ quả thiết kế |
| --- | --- | --- |
| Gateway, reverse proxy | Lưu request target để tra lỗi | Không đặt secret trong path hoặc query ngay từ client |
| APM, distributed tracing | Gắn URL vào thuộc tính span | Cấu hình thu thập theo route và danh sách trường được phép |
| Trình duyệt | Người dùng điều hướng đến một URL có thông tin cá nhân | URL có thể nằm trong history, bookmark hoặc ảnh chụp màn hình |
| Công cụ hỗ trợ | Người dùng dán URL vào ticket | Dữ liệu được chuyển sang hệ thống có người đọc và thời hạn lưu khác |
| Trang web và mã analytics | Mã phía client thu thập địa chỉ trang | Hạn chế dữ liệu URL và phạm vi thu thập |
| Cơ chế chuyển hướng | Server tạo `Location` từ địa chỉ đầu vào | Không sao chép tham số nhạy cảm vào liên kết mới |

Một request `fetch` tới API không có nghĩa URL của request đó tự động được thêm vào lịch sử điều hướng của trình duyệt. Cần phân biệt truy cập API nền với điều hướng trang. Dù vậy, request nền vẫn có thể được quan sát qua công cụ phát triển, telemetry hoặc các lớp máy chủ.

Header `Referer` có thể tiết lộ thông tin của URI trang nguồn trong những trường hợp chính sách referrer cho phép. Không phải mọi request đều gửi nguyên URL nguồn; hành vi phụ thuộc chính sách và ngữ cảnh. Bài học thiết kế vẫn là giảm dữ liệu nhạy cảm ngay trong địa chỉ, thay vì phụ thuộc vào việc referrer sẽ bị lược bỏ. [RFC 9110, mục 17.9](https://www.rfc-editor.org/rfc/rfc9110.html#section-17.9).

## 3. Chọn URI, header hay body theo vai trò của dữ liệu

| Dữ liệu | Vị trí phù hợp trong thiết kế minh họa | Lưu ý |
| --- | --- | --- |
| ID resource được phép xuất hiện trong địa chỉ | Path | Kiểm tra quyền đối với chính resource đó |
| Bộ lọc ít nhạy cảm như trạng thái đơn hàng | Query | Đánh giá ngữ cảnh; bộ lọc bình thường ở nơi này có thể nhạy cảm ở nơi khác |
| Bearer access token | Header `Authorization` | Gửi qua HTTPS và không ghi nguyên header vào log |
| API key của tích hợp | Header do hợp đồng quy định, ví dụ `X-API-Key` | Đây vẫn là secret; phải kiểm soát log, thu hồi và vòng đời |
| Email dùng để tìm khách hàng | Body của một POST xử lý tìm kiếm | Cần phân quyền người tìm kiếm và giới hạn kết quả |
| Mật khẩu mới hoặc thông tin cập nhật riêng tư | Body của thao tác phù hợp | Không ghi body vào log theo mặc định |
| Khóa chống lặp nghiệp vụ | Header `Idempotency-Key` theo hợp đồng | Dùng giá trị độc lập, không ghép từ email hoặc số giấy tờ |
| Con trỏ phân trang | Query nếu đã được thiết kế để có thể xuất hiện ở đó | Không nhét dữ liệu cá nhân dạng Base64 vào cursor |

Việc đưa thông tin xác thực ra khỏi URL và sử dụng header hoặc body phù hợp với khuyến nghị thiết kế REST của OWASP. Điều này không thay thế yêu cầu bảo vệ chính header và body. [OWASP REST Security Cheat Sheet, Sensitive information in HTTP requests](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html#sensitive-information-in-http-requests).

Không chuyển mọi thông tin cá nhân sang header tùy ý. Header xác thực có ngữ nghĩa riêng; dữ liệu của một truy vấn hoặc một cập nhật thường thuộc body. Với phiên trình duyệt dùng cookie, cần thiết kế thuộc tính cookie và bảo vệ CSRF phù hợp; không thay cookie bằng token trong query chỉ để đơn giản hóa client.

### 3.1. Sửa endpoint truyền access token qua query

Thiết kế có vấn đề:

```http
GET /v1/orders?status=PAID&access_token=TOKEN_DEMO HTTP/1.1
Host: api.example.test
```

Thiết kế thay thế:

```http
GET /v1/orders?status=PAID&page=0&size=20 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_DEMO
Accept: application/json
```

Resource và điều kiện lọc ít nhạy cảm nằm trong URI. Thông tin xác thực nằm trong header. Máy chủ xác thực token rồi giới hạn tập đơn hàng theo quyền của chủ thể đã xác thực.

Đối với OAuth, không dựa vào ví dụ query parameter trong tài liệu cũ để thiết kế API mới. RFC 9700 quy định client **không được truyền access token trong URI query parameter**, cập nhật thực hành được mô tả trong RFC 6750. [RFC 9700, mục 4.3.2](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.3.2).

Cách sử dụng bearer token qua `Authorization` được mô tả tại [RFC 6750, mục 2.1](https://www.rfc-editor.org/rfc/rfc6750.html#section-2.1).

Hợp đồng API nên từ chối vị trí token qua query, kể cả khi client đồng thời gửi header đúng. Với API mới, có thể quy định request chứa tham số xác thực bị cấm sẽ nhận `400 Bad Request`. Không âm thầm ưu tiên một token rồi bỏ qua token còn lại, vì cách đó giữ lại hành vi rò rỉ ở client và gây mơ hồ khi điều tra.

### 3.2. Dùng ID độc lập thay cho dữ liệu cá nhân

Thiết kế ban đầu:

```text
GET /v1/customers/an.demo%40example.test
```

Thiết kế thay thế:

```text
GET /v1/customers/cus_demo_73
```

ID public nên độc lập với email hoặc số giấy tờ và không chứa thông tin nghiệp vụ cần giữ kín. Không tạo ID bằng cách Base64 email hoặc lấy hash trực tiếp của số điện thoại rồi coi đó là dữ liệu vô danh. Không gian giá trị có thể nhỏ, cho phép đối chiếu hoặc dò đoán.

Hai yêu cầu vẫn phải thực hiện sau khi đổi ID:

1. Kiểm tra người gọi có được đọc `cus_demo_73` trong tổ chức hoặc phạm vi dữ liệu hiện tại hay không.
2. Hạn chế trả các trường riêng tư không cần thiết trong response.

Nếu chức năng chỉ cần dữ liệu của người đang đăng nhập, một resource như `/v1/me` có thể tránh việc client đưa email vào địa chỉ. Máy chủ phải suy ra chủ thể từ ngữ cảnh xác thực đã được kiểm chứng.

## 4. Tìm kiếm bằng dữ liệu nhạy cảm: dùng POST với hợp đồng rõ ràng

Giả sử nhân viên được cấp quyền cần tìm khách hàng theo email.

Thiết kế gây phơi lộ:

```http
GET /v1/customers?email=an.demo%40example.test&page=0&size=20 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_DEMO
```

Một phương án là xử lý tìm kiếm bằng POST:

```http
POST /v1/customer-searches HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_DEMO
Content-Type: application/json
Accept: application/json

{
  "email": "an.demo@example.test",
  "page": 0,
  "size": 20
}
```

Response minh họa:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "items": [
    { "customerId": "cus_demo_73" }
  ],
  "page": 0,
  "hasNext": false
}
```

Các quyết định trong hợp đồng này:

- URI chỉ mô tả chức năng xử lý tìm kiếm.
- Email và tham số phân trang được gửi trong body, không được đưa lại vào URL trang kế tiếp.
- Máy chủ chỉ tìm trong tập khách hàng mà người gọi được phép truy cập.
- Response chỉ trả ID cần thiết cho bước tiếp theo, không lặp lại email tìm kiếm.
- `200 OK` phù hợp khi xử lý và trả kết quả ngay, không tạo resource tìm kiếm có vòng đời lưu trữ.
- Response nhạy cảm được yêu cầu không lưu trữ bằng `Cache-Control: no-store`.

Nếu cần tạo một resource tìm kiếm có thể truy cập về sau, hợp đồng có thể dùng `201 Created` và `Location: /v1/customer-searches/{searchId}`. Khi đó cần định nghĩa quyền sở hữu, thời hạn lưu và việc xóa resource. Mỗi lần đọc kết quả phải kiểm tra quyền; biết `searchId` không tự cho phép truy cập.

### 4.1. Chấp nhận đánh đổi về HTTP

POST là phương thức không được HTTP phân loại là safe hay mặc định idempotent, dù nghiệp vụ tìm kiếm cụ thể không sửa dữ liệu. Vì vậy:

- Không giả định client hoặc proxy có thể tự retry mọi POST an toàn.
- Nếu truy vấn được thiết kế không có tác dụng phụ nghiệp vụ, hãy ghi rõ khả năng gửi lại request trong hợp đồng.
- Không trông chờ cơ chế cache GET và bookmark URL hoạt động giống trước.
- Nếu có phân trang bằng cursor, giữ bộ lọc nhạy cảm trong body; cursor cũng phải được đánh giá về nội dung, phạm vi quyền và thời hạn.
- Không giải quyết bằng cách gửi body trong GET: ngữ nghĩa GET body không được hỗ trợ thống nhất qua các thành phần HTTP.

Việc chọn POST ở đây là quyết định về vị trí dữ liệu và hợp đồng xử lý. Nó không làm response tự có tính bí mật và không biến POST thành phương thức safe theo định nghĩa HTTP.

### 4.2. `no-store` không phải lệnh xóa mọi dấu vết

`Cache-Control: no-store` là chỉ dẫn về việc lưu trữ trong cache HTTP. Nó không tự xóa access log, bản ghi tracing, ảnh chụp màn hình, lịch sử điều hướng hoặc bản sao đã tạo trước đó.

Cần cấu hình cả gateway, ứng dụng và hệ thống quan sát. Chuyển email sang body mà vẫn bật ghi toàn bộ request body trong APM chỉ chuyển nơi rò rỉ.

## 5. Minh họa controller Java/Spring

Ví dụ sau dùng Spring MVC, Spring Security và Jakarta Bean Validation trong ứng dụng Java hỗ trợ `record`. Nó minh họa điểm nhận body và tạo response; không phải một ứng dụng chạy độc lập.

Giả định chuỗi bảo mật đã xác thực bearer token, từ chối truy cập ẩn danh và kiểm tra quyền gọi chức năng tìm kiếm. `CustomerSearchService` là bean nghiệp vụ cần được triển khai để giới hạn dữ liệu theo chủ thể và tổ chức của người gọi.

```java
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/customer-searches")
public class CustomerSearchController {

    private final CustomerSearchService searchService;

    public CustomerSearchController(CustomerSearchService searchService) {
        this.searchService = searchService;
    }

    @PostMapping(
        consumes = "application/json",
        produces = "application/json"
    )
    public ResponseEntity<SearchResult> search(
            @Valid @RequestBody SearchRequest request,
            Authentication authentication) {

        SearchResult result = searchService.searchVisibleTo(
            authentication.getName(),
            request
        );

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(result);
    }

    public record SearchRequest(
        @NotBlank @Email @Size(max = 254) String email,
        @NotNull @Min(0) Integer page,
        @NotNull @Min(1) @Max(100) Integer size
    ) {}

    public record CustomerHit(String customerId) {}

    public record SearchResult(
        List<CustomerHit> items,
        int page,
        boolean hasNext
    ) {}

    public interface CustomerSearchService {
        SearchResult searchVisibleTo(
            String authenticatedSubject,
            SearchRequest request
        );
    }
}
```

`@RequestBody` nhận dữ liệu JSON qua cơ chế chuyển đổi thông điệp của Spring. `@Valid` kích hoạt Bean Validation; cấu hình mặc định chuyển lỗi validation của trường hợp này thành response 400. Cần có bộ triển khai Bean Validation trong ứng dụng. [Spring Framework, @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).

Các chi tiết cần giữ rõ khi triển khai:

- Controller không lấy email bằng `@PathVariable` hoặc `@RequestParam`.
- Chủ thể được lấy từ `Authentication` do chuỗi bảo mật tạo, không lấy từ một header do client tự khai như `X-User-Id`.
- Tên chủ thể phải được diễn giải trong đúng ngữ cảnh hệ thống xác thực. Với nhiều bên phát hành token, lớp bảo mật và dịch vụ phải xác định danh tính cùng phạm vi tổ chức một cách nhất quán.
- `@Email` kiểm tra định dạng theo validator; nó không xác minh chủ sở hữu email hoặc cấp quyền xem dữ liệu.
- Không ghi `request` vào log: `toString()` tự sinh của record có thể chứa email.
- Không có `@RequestParam` không có nghĩa Spring tự từ chối mọi query parameter. Việc chặn tham số như `access_token`, `apiKey` hoặc tham số ngoài hợp đồng cần được triển khai riêng ở lớp phù hợp.

Code này cũng không tự che body ở gateway hay APM. Chính sách quan sát phải được cấu hình ở các lớp thực sự thu thập dữ liệu.

## 6. Mô tả vị trí dữ liệu trong OpenAPI

Đoạn OpenAPI sau thể hiện lựa chọn thiết kế của endpoint tìm kiếm. Dữ liệu mẫu phải là dữ liệu giả; không sao chép token hoặc email thật từ môi trường vận hành.

```yaml
openapi: 3.0.3
info:
  title: Customer Search API
  version: '1.0.0'
servers:
  - url: https://api.example.test
paths:
  /v1/customer-searches:
    post:
      summary: Tìm khách hàng trong phạm vi được cấp quyền
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [email, page, size]
              properties:
                email:
                  type: string
                  format: email
                  minLength: 1
                  maxLength: 254
                  example: an.demo@example.test
                page:
                  type: integer
                  minimum: 0
                  example: 0
                size:
                  type: integer
                  minimum: 1
                  maximum: 100
                  example: 20
      responses:
        '200':
          description: Kết quả trong phạm vi người gọi được phép truy cập
          headers:
            Cache-Control:
              schema:
                type: string
              example: no-store
          content:
            application/json:
              schema:
                type: object
                required: [items, page, hasNext]
                properties:
                  items:
                    type: array
                    items:
                      type: object
                      required: [customerId]
                      properties:
                        customerId:
                          type: string
                          example: cus_demo_73
                  page:
                    type: integer
                    minimum: 0
                  hasNext:
                    type: boolean
        '400':
          description: Body hoặc tham số request không hợp lệ
        '401':
          description: Thiếu thông tin xác thực hoặc token không hợp lệ
          headers:
            WWW-Authenticate:
              schema:
                type: string
              example: 'Bearer realm="rest-api"'
        '403':
          description: Đã xác thực nhưng không có quyền tìm kiếm
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
```

Không khai báo access token thành parameter `in: query`. Khai báo security scheme giúp tài liệu và client hiểu cơ chế xác thực, nhưng không tự cấu hình phân quyền của máy chủ.

Tương tự, schema không tự đảm bảo log đã được che dữ liệu. Cần kết nối hợp đồng API với cấu hình bảo mật và hành vi thực tế của hệ thống.

## 7. Không đưa dữ liệu nhạy cảm trở lại qua log, lỗi hoặc liên kết

Sau khi sửa request, vẫn có thể vô tình tạo lại URI chứa dữ liệu qua các đầu ra khác:

```text
Location: /v1/customer-searches?email=an.demo%40example.test
next: /v1/customers?email=an.demo%40example.test&page=1
error.instance: /v1/orders?access_token=TOKEN_DEMO
```

Không xây dựng `Location`, liên kết `next`, `self` hoặc trường lỗi bằng cách sao chép toàn bộ query đầu vào.

Đối với lỗi validation, trả thông tin đủ giúp client sửa request mà không lặp lại giá trị đã nhận. Ví dụ:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Invalid request",
  "status": 400,
  "detail": "Trường email không đúng định dạng.",
  "requestId": "req_demo_42"
}
```

Đây là response lỗi do ứng dụng thiết kế; controller ở trên chưa bao gồm exception handler để tạo định dạng này. Không đưa rejected value, bearer token hoặc URL đầy đủ vào message lỗi.

Một bản ghi vận hành tối thiểu có thể có dạng:

```json
{
  "event": "customer_search_completed",
  "method": "POST",
  "route": "/v1/customer-searches",
  "status": 200,
  "durationMs": 18,
  "requestId": "req_demo_42"
}
```

Nếu cần ghi danh tính người thao tác cho audit, hãy giới hạn trường được lưu, người được đọc và thời hạn giữ dữ liệu. Bản ghi có ID người dùng vẫn có thể liên kết với cá nhân; không coi nó là dữ liệu vô danh.

Có thể dùng route template như `/v1/customers/{customerId}` trong log thống kê để tránh ghi mọi giá trị path. Tuy nhiên, phải xem cấu hình gateway có ghi thêm request target gốc hay không.

Ưu tiên danh sách trường được phép ghi thay vì cố tìm mọi tên secret bằng một biểu thức chính quy. Che `token` nhưng bỏ sót `refresh_token`, tên khác chữ hoa hoặc một path chứa secret vẫn để lại rò rỉ.

## 8. Trường hợp đặc biệt: liên kết đặt lại mật khẩu và URL có chữ ký

Một số luồng có chủ đích truyền một giá trị có khả năng cấp quyền trong liên kết: URL tải tệp có chữ ký hoặc liên kết khôi phục tài khoản. Trong các luồng đó, bản thân liên kết là dữ liệu nhạy cảm.

Điều này không cho phép đưa access token OAuth vào query của API thông thường. Cần phân biệt cơ chế capability được thiết kế riêng với việc dùng lại token xác thực toàn hệ thống.

### 8.1. Ưu tiên luồng không cần secret trong URI khi khả thi

Với ứng dụng đã đăng nhập và hỗ trợ header xác thực, có thể tải tệp qua:

```http
GET /v1/files/file_demo_91/content HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_DEMO
```

Nếu hạ tầng lưu trữ yêu cầu URL có chữ ký, hãy xác định rõ phạm vi của chữ ký: tệp nào, thao tác nào và thời điểm hết hiệu lực. Người sở hữu liên kết có thể sử dụng nó trong phạm vi đó; không đưa thêm email hay quyền rộng không cần thiết vào liên kết.

Các yêu cầu phải được quyết định theo luồng cụ thể:

- Thời hạn đủ ngắn cho nghiệp vụ và giới hạn resource, phương thức được phép.
- Cách thu hồi hoặc vô hiệu hóa trước hạn nếu hệ thống có hỗ trợ.
- Khả năng dùng một lần khi phù hợp; tải tệp theo range hoặc tải lại có thể cần nhiều request.
- Quy tắc che URL trong log, ticket, analytics và tài liệu.
- Hành vi cache phù hợp với quyền truy cập và độ nhạy của nội dung.
- Với trang HTML xử lý liên kết nhạy cảm, cân nhắc `Referrer-Policy: no-referrer` và hạn chế tài nguyên bên thứ ba.

### 8.2. Liên kết khôi phục tài khoản cần kiểm soát thêm

Một trang nhận token khôi phục từ liên kết có thể chuyển người dùng sang URL sạch sau khi tiếp nhận giá trị. Việc đó giảm sự lan truyền về sau; nó không xóa request đầu tiên khỏi hệ thống log.

Không để GET từ email tự hoàn tất thay đổi mật khẩu hoặc tiêu thụ thao tác quan trọng chỉ vì liên kết được mở. Công cụ quét thư có thể truy cập liên kết trước người dùng. Luồng nên có bước xác nhận phù hợp và xử lý thay đổi bằng request được thiết kế rõ ràng, thường là POST với dữ liệu trong body.

Mã authorization code xuất hiện ở callback OAuth là một trường hợp thuộc giao thức riêng, khác access token dùng để gọi resource API. Không tự sửa giao thức xác thực bằng cách đưa access token vào URL; dùng luồng và thư viện phù hợp, cùng các biện pháp như PKCE theo yêu cầu của luồng.

## 9. Nếu API cũ đã đưa secret vào URI

Thiết kế lại endpoint chưa đủ nếu giá trị cũ vẫn còn hiệu lực và đã được ghi lại. Một kế hoạch chuyển đổi cần giải quyết cả hợp đồng mới và dữ liệu đã phát tán.

1. **Chặn phát sinh mới:** bổ sung cách gửi đúng qua header hoặc body; cập nhật client và giới hạn thời gian hỗ trợ kiểu cũ.
2. **Giảm thu thập ngay tại đầu vào:** điều chỉnh access log và telemetry ở gateway, không chỉ logger trong ứng dụng.
3. **Xử lý secret có khả năng đã lộ:** thu hồi hoặc luân chuyển theo cơ chế token/API key của hệ thống, đồng thời đánh giá phạm vi ảnh hưởng.
4. **Xử lý bản sao lưu trữ:** xác định log, tracing, ticket và bản xuất có liên quan; hạn chế truy cập và xử lý theo chính sách lưu trữ, điều tra của tổ chức.
5. **Kết thúc hỗ trợ vị trí bị cấm:** từ chối request còn truyền secret trong URI và theo dõi số lượng bằng dữ liệu thống kê đã được làm sạch.

Không chuyển hướng từ URL cũ chứa token sang URL mới rồi coi sự cố đã giải quyết. URL cũ đã đến máy chủ; hơn nữa, chuyển hướng không tự biến query token thành `Authorization` header cho client.

## 10. Tiêu chí kiểm thử khi triển khai

Các tình huống sau dùng dữ liệu giả và áp dụng cho hợp đồng minh họa trong bài. Kiểm tra cả request/response và các lớp quan sát có tham gia.

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Token hợp lệ nằm trong `Authorization` | Request được xác thực và tiếp tục kiểm tra quyền |
| Token nằm trong query | Request bị từ chối theo hợp đồng; không echo token trong lỗi |
| Cùng lúc có token ở header và query | Bị từ chối do vị trí bị cấm, không bỏ qua query |
| Không có thông tin xác thực | Trả 401 với challenge phù hợp; không có dữ liệu riêng tư |
| Đã xác thực nhưng thiếu quyền tìm kiếm | Trả 403 theo hợp đồng chức năng |
| Tìm email ngoài phạm vi dữ liệu của người gọi | Không trả dữ liệu ngoài quyền; không tiết lộ sự tồn tại ngoài phạm vi qua thông báo |
| Email sai định dạng hoặc size lớn hơn 100 | Trả 400, không đưa giá trị nhạy cảm vào lỗi |
| Tìm kiếm thành công | Trả 200, có `Cache-Control: no-store`, không lặp email trong URI hoặc liên kết |
| Gọi trực tiếp ID khách hàng thuộc tổ chức khác | Bị từ chối theo chính sách; ID khó đoán không làm thay đổi yêu cầu này |
| Dùng chuỗi đánh dấu giả làm token hoặc email | Chuỗi không xuất hiện ở gateway log, application log, trace và error report |

Kiểm thử controller đơn lẻ không chứng minh toàn bộ đường đi đã an toàn. Ví dụ, một test MVC có thể xác nhận controller không log email, nhưng không quan sát được access log của gateway. Cần kiểm thử tích hợp tại ranh giới thực tế nơi URI, header và body được xử lý.

Khi hoàn thành thiết kế, hãy kiểm tra ba điểm: **URI chỉ chứa dữ liệu được phép xuất hiện trong địa chỉ; thông tin xác thực và dữ liệu riêng tư được truyền đúng vị trí; mọi lớp thu thập dữ liệu đều tuân theo hợp đồng bảo vệ dữ liệu.**