# Giới hạn độ sâu JSON, kích thước yêu cầu và chi phí xử lý

Một REST API có thể nhận **JSON hoàn toàn đúng cú pháp** nhưng vẫn bị từ chối phục vụ vì dữ liệu quá sâu, quá rộng hoặc khiến hệ thống thực hiện lượng công việc không tương xứng với kích thước yêu cầu. Đây là một phần của **phân quyền và an toàn tài nguyên**: sau khi xác thực người gọi, API vẫn phải quyết định họ được phép tiêu thụ bao nhiêu CPU, bộ nhớ, I/O và công việc phía sau.

Bài học tập trung vào API HTTP dùng Java/Spring, song các nguyên tắc áp dụng tương tự cho Jakarta REST, .NET, Node.js và API gateway. Người học sẽ biết cách lập ngân sách tài nguyên theo endpoint, đặt giới hạn trước khi phân tích JSON, trả mã HTTP nhất quán và kiểm thử các ranh giới.

## 1. Vì sao chỉ kiểm tra `Content-Length` là chưa đủ?

Giả sử `POST /v1/orders` nhận tối đa 1 MiB JSON. Hai yêu cầu dưới đây có thể cùng nhỏ hơn 1 MiB nhưng tạo chi phí rất khác nhau:

~~~json
{"items":[{"sku":"BOOK-42","quantity":2}]}
~~~

~~~json
{"items":[{"sku":"A","quantity":1},{"sku":"B","quantity":1},{"sku":"C","quantity":1}]}
~~~

Yêu cầu thứ hai tuy nhỏ nhưng có nhiều phần tử hơn. Nếu mỗi phần tử gây một truy vấn cơ sở dữ liệu hoặc một lời gọi dịch vụ bên ngoài, chi phí có thể tăng gần theo số phần tử. Tương tự, một chuỗi gồm hàng nghìn dấu `[` mở lồng nhau có thể rất ngắn về byte nhưng làm parser sử dụng ngăn xếp sâu hoặc chạm giới hạn cấu trúc. Ngược lại, một chuỗi đơn dài vài megabyte có độ sâu chỉ bằng một.

Để bảo vệ một API, cần tách ít nhất năm trục giới hạn:

| Trục | Ví dụ lạm dụng | Hậu quả có thể gặp | Giới hạn phù hợp |
| --- | --- | --- | --- |
| **Số byte nhận qua HTTP** | Body 100 MiB, gửi chậm hoặc không khai báo độ dài | Chiếm băng thông, kết nối, bộ đệm | Byte tối đa; thời gian đọc; số kết nối đồng thời |
| **Độ sâu JSON** | Hàng trăm object/array lồng nhau | Parser đệ quy, lỗi stack, tốn CPU | Số mức lồng tối đa |
| **Độ rộng và kích thước token** | Array hàng trăm nghìn phần tử, chuỗi rất dài, số có hàng triệu chữ số | Cấp phát heap, GC, chuyển đổi số tốn kém | Số phần tử, độ dài chuỗi/tên field/số |
| **Số thao tác xử lý** | 100 mục × mỗi mục 5 truy vấn hoặc gọi API | N+1 query, cạn connection pool, tăng độ trễ | Số mục, số truy vấn, batch, concurrency, deadline |
| **Tần suất yêu cầu** | Nhiều yêu cầu hợp lệ nhưng tốn tài nguyên | Cạn worker, làm nghẽn tài nguyên chung | Rate limit, quota, giới hạn đồng thời |

Giới hạn này không thay thế xác thực, phân quyền hoặc kiểm tra dữ liệu nghiệp vụ. Một người dùng có token hợp lệ vẫn có thể vô tình hoặc cố ý gửi yêu cầu gây quá tải. Quy tắc áp dụng cho cả dữ liệu từ trình duyệt, mobile app, tích hợp đối tác lẫn dịch vụ nội bộ.

## 2. Thiết kế ngân sách tài nguyên theo hợp đồng API

Không có một ngưỡng đúng cho mọi endpoint. `POST /v1/orders` thường khác `POST /v1/imports` nhận dữ liệu hàng loạt, trong khi `GET /v1/orders?pageSize=...` còn phát sinh chi phí đọc và truy vấn. Hãy bắt đầu bằng ngân sách được công bố và có thể đo đạc.

**Ví dụ chính sách minh họa** cho `POST /v1/orders`:

| Thuộc tính | Giới hạn ví dụ | Thực thi tại đâu |
| --- | ---: | --- |
| Body sau khi giải mã `Content-Encoding` | 1 MiB = 1.048.576 byte | Ingress/gateway khi giải nén; ứng dụng trước khi deserialize |
| Body truyền trên mạng | 1 MiB nếu không hỗ trợ body nén | Gateway, reverse proxy |
| Mức lồng JSON | 32 | JSON streaming parser |
| Độ dài một chuỗi JSON | 16.384 ký tự theo phép đếm của thư viện | JSON parser |
| Độ dài một literal số | 64 ký tự | JSON parser |
| Số phần tử `items` | 1–100 | Validation/streaming parser |
| `sku` và `quantity` mỗi phần tử | `sku` không rỗng, tối đa 64 ký tự; `quantity` từ 1 đến 1.000 | Validation nghiệp vụ |
| Tải đồng thời, tốc độ, hạn xử lý | Theo tải thực tế và SLO | Gateway, admission control, service, database |

Các số trên **là giả định để thực hành**, không phải giá trị mặc định của HTTP, Jackson hay Spring. Dùng phân bố kích thước request hợp lệ, tải cao điểm, bộ nhớ có sẵn, hiệu năng parser và giới hạn downstream để chọn giá trị triển khai. Với API import lớn, nên dùng upload có kiểm soát hoặc cơ chế bất đồng bộ, thay vì nới mọi endpoint lên cùng một mức.

Đặt rõ đơn vị: 1 MiB = 1.048.576 byte; ký tự Java/JSON không đồng nghĩa byte UTF-8. Ví dụ tiếng Việt có dấu hoặc emoji có thể cần nhiều byte trên mạng. Ngưỡng phần tử `items` chỉ giới hạn số phần tử ở một mảng; nếu payload có nhiều mảng, cần thêm ngân sách tổng số token/phần tử và giới hạn cho từng nhánh.

**Ước lượng chi phí nghiệp vụ:** Với 100 mục, xử lý mỗi mục bằng một truy vấn SQL có thể phát sinh 100 round trip. Nếu gom SKU thành một truy vấn theo tập và một lần ghi theo batch, chi phí thường giảm đáng kể. Giới hạn JSON bảo vệ phần đọc/parse; thiết kế xử lý theo batch và kiểm soát đồng thời bảo vệ giai đoạn sau.

## 3. Đặt kiểm soát theo thứ tự, từ biên mạng đến cơ sở dữ liệu

~~~mermaid
flowchart LR
  C[Client] --> G[Gateway / WAF]
  G --> S[HTTP server / Servlet]
  S --> B[Chặn body quá lớn]
  B --> J[Jackson: độ sâu / token]
  J --> V[DTO + validation]
  V --> A[Authorization + ngân sách nghiệp vụ]
  A --> D[(DB / downstream)]
~~~

Một thiết kế vững phải bảo vệ từng lớp theo tài nguyên lớp đó đang giữ:

1. **Gateway/reverse proxy** từ chối body vượt giới hạn, giới hạn kết nối, tốc độ và thời gian đọc. Nếu hỗ trợ yêu cầu nén, giới hạn cả kích thước trên mạng lẫn **kích thước sau giải nén**; một body gzip nhỏ có thể phình thành hàng chục MiB. Cần quan tâm số luồng HTTP/2 đồng thời và việc client gửi chậm.
2. **HTTP server/Servlet** quản lý request framing, header, timeout, luồng và bộ đệm. `Content-Length` có thể không có ở request dùng `Transfer-Encoding: chunked`; ứng dụng vẫn phải đếm số byte thực tế. Không tự diễn giải hai header framing mâu thuẫn, hãy để proxy/server chuẩn hóa và từ chối yêu cầu không hợp lệ.
3. **Lớp đọc body** đặt trần byte trước khi giao cho Jackson. Tránh đọc toàn bộ một body chưa được giới hạn bằng `String`, `byte[]` hoặc `ContentCachingRequestWrapper`, vì lúc đó việc cấp phát đã xảy ra.
4. **JSON parser** giới hạn lồng nhau và độ dài token trong lúc phân tích. Trần 1 MiB không thay thế trần depth; trần depth cũng không ngăn mảng rộng hoặc nhiều field cùng mức.
5. **Validation và service** kiểm tra schema, số mục, độ dài field, quyền truy cập theo tenant, số truy vấn và chi phí thực thi. Không bind JSON trực tiếp vào entity có các field như `role`, `price`, `tenantId` để client có thể ghi vượt quyền (*mass assignment*).
6. **Tài nguyên chia sẻ** cần giới hạn đồng thời, quota theo định danh/tenant, circuit breaker hoặc deadline cho downstream. Rate limit theo số request đơn thuần có thể không đủ khi mỗi request có chi phí khác nhau.

Ví dụ cấu hình tại NGINX (nếu NGINX là ingress của hệ thống):

~~~nginx
location /v1/orders {
    client_max_body_size 1m;
    client_body_timeout 10s;
    proxy_pass http://orders_backend;
}
~~~

`client_max_body_size` giới hạn kích thước request mà NGINX nhận; `client_body_timeout` bảo vệ khoảng chờ đọc body, **không phải** deadline toàn bộ thao tác xử lý. Hãy xác minh proxy nào giải nén body và lớp nào chịu trách nhiệm giới hạn byte sau giải nén. Chính sách ở gateway không miễn trừ kiểm tra tại ứng dụng, nhất là khi có đường gọi nội bộ bỏ qua gateway.

**Bẫy cấu hình Spring:** `spring.servlet.multipart.max-request-size` dành cho multipart upload; các giới hạn form POST của Tomcat dành cho form parameter. Không nên giả định chúng tự động đặt trần cho mọi body `application/json`. Tương tự, giới hạn kích thước HTTP header là một ngân sách khác với body.

## 4. Ánh xạ vi phạm sang HTTP status và Problem Details

API nên trả phản hồi có cấu trúc, mã ổn định để client phân biệt thao tác sửa dữ liệu với thao tác thử lại. Có thể sử dụng RFC 9457 Problem Details với `Content-Type: application/problem+json`.

| Trường hợp | Mã gợi ý | Cách xử lý |
| --- | --- | --- |
| Body vượt trần byte, kể cả khi `Content-Length` vắng mặt | **413 Content Too Large** | Không parse; trả mã lỗi ổn định; quản lý kết nối còn body chưa đọc |
| JSON sai cú pháp hoặc vượt độ sâu/token mà parser cho phép | **400 Bad Request** | Không thực thi nghiệp vụ; lỗi không chứa payload gốc |
| JSON đúng cú pháp nhưng `items` vượt số lượng hoặc `quantity` ngoài khoảng | **422 Unprocessable Content** | Thống nhất 422/400 theo hợp đồng API; ví dụ bài này dùng 422 |
| `Content-Type` hoặc `Content-Encoding` không được hỗ trợ | **415 Unsupported Media Type** | Từ chối trước khi giải mã |
| Header HTTP vượt giới hạn | **431 Request Header Fields Too Large** | Để ingress/server xử lý |
| Vượt tốc độ/quota | **429 Too Many Requests** | Có thể thêm `Retry-After` khi xác định được thời điểm thử lại |
| Hệ thống tạm quá tải | **503 Service Unavailable** | Giới hạn admission; có thể thêm `Retry-After` |

Một phản hồi 413 mẫu:

~~~http
HTTP/1.1 413 Content Too Large
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Yêu cầu quá lớn",
  "status": 413,
  "detail": "Body JSON vượt giới hạn 1048576 byte.",
  "code": "REQUEST_TOO_LARGE"
}
~~~

Không trả lỗi 500 cho dữ liệu quá sâu được dự đoán trước; đó phải là vi phạm chính sách đầu vào. Không đưa token xác thực, nội dung body, stack trace, SQL hay thông tin nội bộ vào `detail`. Một số proxy tự tạo trang lỗi 413 dạng HTML: nếu yêu cầu client luôn nhận Problem Details thì cần chuẩn hóa response ở lớp ingress hoặc ghi rõ giới hạn của hợp đồng.

## 5. Cấu hình giới hạn JSON ở Jackson

Từ Jackson 2.15, `StreamReadConstraints` cung cấp giới hạn cho luồng parse JSON. Với ứng dụng Spring Boot 3.x tương thích Jackson 2.15+, có thể cấu hình `ObjectMapper` được Spring dùng để deserialize:

~~~java
import com.fasterxml.jackson.core.StreamReadConstraints;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JsonParsingPolicy {
    @Bean
    Jackson2ObjectMapperBuilderCustomizer jsonReadLimits() {
        return builder -> builder.postConfigurer(mapper ->
            mapper.getFactory().setStreamReadConstraints(
                StreamReadConstraints.builder()
                    .maxNestingDepth(32)
                    .maxStringLength(16_384)
                    .maxNumberLength(64)
                    .build()
            )
        );
    }
}
~~~

Giới hạn được kiểm tra trong quá trình parse, trước khi JSON trở thành object Java. Khi vượt ngưỡng, Jackson phát sinh lỗi parse (thường chứa `StreamConstraintsException` ở chuỗi nguyên nhân). Nếu dùng `@RequestBody` trong Spring MVC, exception thường được bọc trong `HttpMessageNotReadableException`; handler có thể chuyển thành HTTP 400 với thông điệp chung. Ví dụ:

~~~java
@RestControllerAdvice
class JsonErrorHandler {
    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ProblemDetail> invalidJson() {
        ProblemDetail error = ProblemDetail.forStatus(400);
        error.setTitle("JSON không hợp lệ");
        error.setDetail("Body sai cú pháp hoặc vượt giới hạn phân tích.");
        error.setProperty("code", "INVALID_JSON");
        return ResponseEntity.badRequest().body(error);
    }
}
~~~

Các import của đoạn advice là `org.springframework.web.bind.annotation.RestControllerAdvice`, `ExceptionHandler`, `org.springframework.http.converter.HttpMessageNotReadableException`, `org.springframework.http.ProblemDetail` và `ResponseEntity`. Trên ứng dụng có nhiều `ObjectMapper`/Jackson `JsonFactory` tự tạo, cần áp chính sách cho **tất cả parser nhận dữ liệu không tin cậy**; cấu hình một mapper không tự động bảo vệ mapper khác.

Lưu ý rằng `maxStringLength` là phép đo của Jackson cho chuỗi trong JSON, không phải trần số byte UTF-8 toàn request. Nếu client gửi nhiều chuỗi ngắn hoặc nhiều object cùng cấp, vẫn cần giới hạn tổng byte, số token và số phần tử. Trong hệ thống cho phép duplicate JSON keys (ví dụ hai khóa `role` khác giá trị), các thành phần có thể diễn giải khác nhau; nên dùng một chính sách xử lý nhất quán, cân nhắc bật phát hiện khóa trùng ở parser và không dựa vào thứ tự khóa để quyết định quyền.

## 6. Chặn body trước khi deserialize trong Spring MVC

Ví dụ tiếp theo minh họa **endpoint JSON đồng bộ, body nhỏ**, chặn tối đa 1 MiB trước khi Jackson chạy. Đây là cách áp dụng trực tiếp tại controller khi chưa có filter dùng chung. Trong hệ thống lớn, đưa phép đếm byte vào filter/ingress có kiểm soát để không quên endpoint mới; chú ý việc exception từ filter xảy ra ngoài phạm vi `@RestControllerAdvice`.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.net.URI;
import java.util.List;
import java.util.UUID;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/orders")
class OrderController {
    static final int MAX_BODY_BYTES = 1_048_576;
    static final int MAX_ITEMS = 100;

    private final ObjectMapper mapper;
    private final OrderService orders;

    OrderController(ObjectMapper mapper, OrderService orders) {
        this.mapper = mapper;
        this.orders = orders;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<?> create(HttpServletRequest request) throws IOException {
        // Chính sách ví dụ: không chấp nhận request body nén.
        String encoding = request.getHeader("Content-Encoding");
        if (encoding != null && !encoding.equalsIgnoreCase("identity")) {
            return problem(415, "UNSUPPORTED_ENCODING",
                    "Content-Encoding không được hỗ trợ.");
        }

        // Kiểm tra sớm khi có Content-Length, nhưng không tin vào header này.
        if (request.getContentLengthLong() > MAX_BODY_BYTES) {
            return tooLarge();
        }

        // readNBytes(MAX + 1) giới hạn lượng byte được giữ trong bộ nhớ.
        // Vẫn chặn được request chunked không khai báo Content-Length.
        byte[] body = request.getInputStream().readNBytes(MAX_BODY_BYTES + 1);
        if (body.length > MAX_BODY_BYTES) {
            return tooLarge();
        }

        final OrderRequest command;
        try {
            command = mapper.readValue(body, OrderRequest.class);
        } catch (JsonProcessingException ex) {
            return problem(400, "INVALID_JSON",
                    "JSON không hợp lệ hoặc vượt giới hạn parser.");
        }

        if (command == null || command.items() == null
                || command.items().isEmpty() || command.items().size() > MAX_ITEMS) {
            return problem(422, "INVALID_ITEMS",
                    "items phải chứa từ 1 đến 100 phần tử.");
        }

        for (OrderItem item : command.items()) {
            if (item == null || item.sku() == null || item.sku().isBlank()
                    || item.sku().length() > 64 || item.quantity() == null
                    || item.quantity() < 1 || item.quantity() > 1_000) {
                return problem(422, "INVALID_ITEM",
                        "sku hoặc quantity không đáp ứng hợp đồng API.");
            }
        }

        // Service kiểm tra quyền theo principal/tenant và xử lý theo batch.
        UUID id = orders.create(command);
        return ResponseEntity.created(URI.create("/v1/orders/" + id)).build();
    }

    private static ResponseEntity<ProblemDetail> tooLarge() {
        return problem(413, "REQUEST_TOO_LARGE",
                "Body JSON vượt giới hạn 1048576 byte.");
    }

    private static ResponseEntity<ProblemDetail> problem(
            int status, String code, String message) {
        ProblemDetail detail = ProblemDetail.forStatus(status);
        detail.setTitle("Yêu cầu bị từ chối");
        detail.setDetail(message);
        detail.setProperty("code", code);
        return ResponseEntity.status(status)
                .contentType(MediaType.parseMediaType("application/problem+json"))
                .body(detail);
    }

    public record OrderRequest(List<OrderItem> items) {}
    public record OrderItem(String sku, Integer quantity) {}
}

// Hợp đồng minh họa; phần triển khai phải kiểm tra authorization.
interface OrderService {
    UUID create(OrderController.OrderRequest command);
}
~~~

Luồng thực thi là: **kiểm tra encoding → byte header nếu có → đọc tối đa MAX+1 byte → parse bằng mapper có giới hạn → validation → authorization và ghi dữ liệu**. Ở thời điểm `readNBytes`, bộ nhớ giữ tối đa khoảng 1 MiB cho mảng byte của request đó; khi deserialize, Jackson còn tạo các object khác. Vì vậy tải đồng thời vẫn phải giới hạn. Cách này cũng không bảo vệ khỏi client gửi rất chậm nếu server/proxy thiếu read timeout.

Ví dụ lấy `HttpServletRequest` trực tiếp để tự đọc body; không dùng đồng thời `@RequestBody OrderRequest` vì Spring sẽ deserialize trước khi code trong method chạy. Với endpoint sử dụng `@RequestBody`, nên kiểm soát byte ở filter hoặc server **trước** `HttpMessageConverter`. Nếu muốn xử lý JSON cỡ lớn và số lượng mục rất nhiều, dùng Jackson streaming (`JsonParser`) để đếm token/phần tử và dừng ngay khi chạm ngưỡng, tránh tạo cả cây `JsonNode` hoặc danh sách object.

Không coi JSON DTO là thực thể tin cậy. `sku` và `quantity` cần xác nhận thêm quyền mua hàng, tình trạng tồn kho và giá từ phía server. Không tin `tenantId`, `userId`, `role` hay `price` do client gửi để quyết định quyền hoặc thanh toán. Parser constraints chỉ là một lớp của hợp đồng an toàn.

## 7. Chống khuếch đại chi phí sau khi parse

Body hợp lệ 200 KiB chứa 100 `items` vẫn có thể gây 100 truy vấn, 100 lời gọi REST hoặc nhiều thao tác ghi giao dịch. Các hướng bảo vệ thực tế:

- **Giới hạn tính phức tạp theo endpoint:** Với một lệnh đặt hàng tối đa 100 mục; với tìm kiếm, giới hạn `pageSize`, số bộ lọc, số field sắp xếp, độ rộng `include` và số quan hệ mở rộng. Không để client yêu cầu `expand=*` không giới hạn.
- **Xử lý batch:** Nạp SKU bằng một truy vấn dạng `WHERE sku IN (...)` hoặc chia batch có kích thước cố định; tránh N+1 query. Áp giới hạn số truy vấn và thời gian chờ xuống DB/API khác.
- **Phân quyền trước tác vụ đắt:** Xác thực, kiểm tra quyền truy cập resource/tenant và admission control sớm nhất có thể; không tải hàng nghìn bản ghi rồi mới phát hiện người gọi không có quyền.
- **Concurrency và quota:** Áp rate limit theo principal/tenant/API key và giới hạn số tác vụ đắt chạy đồng thời. Với import hay phân tích nặng, ghi nhận job vào hàng đợi có quota, trả 202 kèm resource trạng thái nếu hợp đồng hỗ trợ.
- **Deadline và hủy:** Đặt timeout có phân cấp tại gateway, service và downstream; ngừng truy vấn hoặc lời gọi không còn cần thiết khi deadline hết. Không kỳ vọng timeout HTTP sẽ tự động hủy mọi tác vụ đang chạy trong database.

Trong hệ thống đa tenant, một khách hàng có quyền hợp lệ vẫn không được chiếm hết CPU hoặc pool kết nối của những tenant khác. Có thể tính `cost weight` cho mỗi request theo số mục, số phép lọc hay số tác vụ downstream; chỉ dùng công thức được kiểm chứng bằng đo đạc, không tin chi phí ước lượng do client cung cấp.

## 8. Kiểm thử ranh giới và hành vi lỗi

Nên có cả kiểm thử parser ở mức unit lẫn kiểm thử HTTP đi qua ingress thực tế. Bộ ca tối thiểu:

| Test | Kích thích | Kết quả mong đợi |
| --- | --- | --- |
| Byte tại ngưỡng | JSON hợp lệ có kích thước đúng 1.048.576 byte | Không bị từ chối **chỉ vì** kích thước |
| Byte vượt ngưỡng | Body 1.048.577 byte | HTTP 413; không gọi service |
| Không có `Content-Length` | Request HTTP/1.1 chunked lớn hơn ngưỡng | HTTP 413 dựa trên byte thực đọc |
| Depth tại/vượt ngưỡng | JSON lồng 32 và 33 mức theo quy tắc đếm parser | 32 được parser chấp nhận; 33 bị từ chối có kiểm soát |
| Token quá dài | Chuỗi hoặc số dài hơn cấu hình Jackson | HTTP 400; không lộ lỗi nội bộ |
| Mảng rộng | `items` có 100 và 101 phần tử hợp lệ | 100 qua kiểm tra số lượng; 101 trả 422 |
| Encoding | `Content-Encoding: gzip` khi endpoint không hỗ trợ | HTTP 415; không deserialize |
| Bản ghi không hợp lệ | `quantity: -1`, `sku` rỗng, field sai kiểu | HTTP 422 hoặc 400 theo hợp đồng |
| Nhiều request cùng lúc | Tải cao bằng payload hợp lệ lớn | Có admission/rate/concurrency limit; latency và heap trong ngân sách |
| Input đột biến | Nested object, nhiều key, Unicode nhiều byte, duplicate keys | Không treo, không lỗi 500, không lộ stack trace |

Ví dụ trích đoạn kiểm thử với `MockMvc` và `ObjectMapper` đã dùng cấu hình `JsonParsingPolicy`:

~~~java
// Giả sử mockMvc và mapper được inject từ test context.
@Test
void rejectsOversizedBodyBeforeParsing() throws Exception {
    byte[] oversized = new byte[1_048_577];
    Arrays.fill(oversized, (byte) 'x');

    mockMvc.perform(post("/v1/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content(oversized))
        .andExpect(status().is(413))
        .andExpect(jsonPath("$.code").value("REQUEST_TOO_LARGE"));
}

@Test
void jacksonRejectsMoreThan32NestedArrays() {
    String deep = "[".repeat(33) + "0" + "]".repeat(33);
    assertThrows(JsonProcessingException.class, () -> mapper.readTree(deep));
}

@Test
void rejectsUnsupportedCompressedRequest() throws Exception {
    mockMvc.perform(post("/v1/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .header("Content-Encoding", "gzip")
            .content(new byte[] {1, 2, 3}))
        .andExpect(status().is(415));
}
~~~

Các import kiểm thử tương ứng gồm JUnit Jupiter `@Test`/`assertThrows`, `java.util.Arrays`, `JsonProcessingException`, `MediaType`, `MockMvcRequestBuilders.post`, `MockMvcResultMatchers.status` và `jsonPath`. Test depth trên mapper là kiểm tra đúng ràng buộc parser, tránh trường hợp endpoint trả 400 chỉ vì JSON sai schema. Để chứng minh Spring MVC thực sự dùng mapper đó, bổ sung ca HTTP gửi JSON sai độ sâu nhưng đúng ngữ cảnh schema và xác nhận 400.

`MockMvc` không mô phỏng đầy đủ framing chunked, giải nén proxy hoặc slow client. Dùng integration test với server và gateway thật để kiểm tra `Transfer-Encoding: chunked`, `Content-Length` vắng mặt, body nén, timeout, HTTP/2, phản hồi 413 của ingress và tình trạng connection reuse sau khi từ chối body chưa đọc hết.

## 9. Giám sát, hiệu chỉnh và lỗi thường gặp

Theo dõi số lần từ chối theo `endpoint`, HTTP status, `code` và nhóm nguyên nhân; thêm histogram kích thước request được chấp nhận, số phần tử, độ sâu khi có thể thu thập an toàn, độ trễ p95/p99, số yêu cầu đang xử lý, JVM heap/GC và tải downstream. Log **metadata đã lọc**, không log toàn bộ body/token. Nếu sau khi nâng giới hạn tỷ lệ 413 giảm nhưng heap và latency tăng vọt, thay đổi đó chưa chắc cải thiện chất lượng dịch vụ.

Các sai lầm dễ gặp:

- Chỉ kiểm tra `Content-Length`, bỏ qua chunked hoặc body đã giải nén.
- Nâng giới hạn toàn hệ thống để phục vụ một endpoint import hiếm gặp.
- Chặn body sau khi `@RequestBody` đã deserialize xong; cấp phát lớn đã xảy ra.
- Cấu hình Jackson chỉ trên một `ObjectMapper` trong khi endpoint khác dùng mapper khác.
- Trả HTTP 500 hoặc tiết lộ thông điệp exception của parser cho client.
- Chỉ giới hạn byte, để mảng cực rộng gây N+1 query hoặc công việc không giới hạn.
- Chỉ đặt rate limit theo IP trong môi trường nhiều tenant dùng chung NAT và không phân biệt chi phí request.

Khi điều chỉnh ngưỡng, chọn dữ liệu tải thực, bổ sung ca boundary, quan sát hiệu năng dưới concurrent load và triển khai theo từng endpoint. Mục tiêu là ngân sách có thể giải thích và kiểm chứng, không phải một con số lớn đến mức “không bao giờ gặp lỗi 413”.

## 10. Bài tập thực hành

**Bài 1 — Đọc chính sách.** API có giới hạn body 1 MiB, depth 32, `items` tối đa 100 và không hỗ trợ body nén. Hãy xác định mã HTTP và lớp xử lý cho: (a) yêu cầu chunked 1,2 MiB; (b) JSON lồng 40 mảng nhưng chỉ 2 KiB; (c) 101 mục hợp lệ; (d) request nén gzip 30 KiB có `Content-Encoding: gzip`; (e) 100 mục hợp lệ nhưng service bị cạn pool DB. Giải thích tại sao (e) không được sửa chỉ bằng cách tăng trần JSON.

**Bài 2 — Thực thi trong Spring.** Tạo `POST /v1/orders` theo ví dụ, bổ sung `@RestControllerAdvice` cho JSON không hợp lệ, kiểm tra `Content-Type`, giới hạn `items`, và viết test tại các ranh giới 1 MiB, depth 32/33, 100/101 phần tử. Đảm bảo service không được gọi cho mọi payload bị từ chối. Trình bày cách xác minh 413 khi dùng chunked tại ingress thật.

**Bài 3 — Thiết kế chống amplification.** Endpoint `POST /v1/reports` nhận 50 bộ lọc và mỗi bộ lọc tạo một truy vấn. Đề xuất policy có trần số bộ lọc, số bảng được join, hạn xử lý, quota theo tenant và phương án job bất đồng bộ. Viết một test tải chứng minh một tenant không làm chậm nghiêm trọng tenant khác.

**Gợi ý tự kiểm tra:** (a) 413 do trần byte thực nhận; (b) 400 do giới hạn parser; (c) 422 do hợp đồng nghiệp vụ; (d) 415 theo chính sách encoding; (e) là vấn đề quota/concurrency, query batching và bảo vệ downstream, có thể cần 503 nếu tạm quá tải. Trong môi trường cho phép gzip, (d) phải thay bằng bài toán kiểm tra trần **sau giải nén**. Đọc/parse JSON là một phần chi phí, còn mạng, xác thực, truy vấn và ghi dữ liệu cũng phải nằm trong cùng một ngân sách tài nguyên.
