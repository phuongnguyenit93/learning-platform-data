# Kiểm tra dữ liệu đầu vào và bảo vệ giao tiếp qua API

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Bảo mật.  
> **Mục tiêu:** thiết kế API coi mọi dữ liệu đi qua ranh giới tin cậy là không đáng tin cho đến khi được xác thực, kiểm tra, phân quyền và xử lý theo hợp đồng rõ ràng.

## 1. Bài toán trong hệ thống microservices

Một hệ thống thương mại điện tử có **API Gateway**, **Order Service**, **Payment Service**, **Inventory Service** và **Notification Service**. Client gửi yêu cầu tạo đơn qua Gateway, Order gọi Inventory và Payment, cuối cùng phát sự kiện cho Notification.

Nếu Order chỉ kiểm tra rằng request là JSON hợp lệ, kẻ tấn công hoặc client bị lỗi vẫn có thể gửi:

- **quantity = -5** để tạo số lượng không hợp lệ.
- **price = 0.01** hoặc **discount = 100%** nhằm khiến server sử dụng giá do client tự đặt.
- **customerId** của người khác để thử truy cập dữ liệu ngoài quyền.
- Một chuỗi cực dài hoặc JSON lồng sâu làm tăng CPU, RAM và chi phí parse.
- **callbackUrl** trỏ đến địa chỉ nội bộ để thử tấn công SSRF.
- Token đã hết hạn, sai đối tượng nhận (**audience**) hoặc thiếu scope.
- Payload mang mã SQL/HTML, path traversal hoặc nội dung khác có thể gây hại nếu đưa thẳng tới tầng lưu trữ, hệ điều hành hay giao diện.

Ngay cả khi traffic dùng HTTPS, các vấn đề này vẫn tồn tại: **HTTPS bảo vệ dữ liệu trên đường truyền**, không chứng minh dữ liệu nghiệp vụ là đúng hoặc người gọi được phép làm hành động đó.

Nguyên tắc cốt lõi:

**Mỗi ranh giới API phải tự thực thi các điều kiện tin cậy cần thiết; không mặc định một thành phần bên ngoài đã làm đủ.**

Gateway là điểm kiểm soát hữu ích, nhưng Order Service vẫn cần xác thực identity phù hợp, kiểm tra quyền trên tài nguyên, kiểm tra payload, và không tin rằng mọi thông tin chuyển tiếp từ upstream đều chính xác.

## 2. Mô hình các lớp bảo vệ

Một API an toàn cần nhiều lớp độc lập cùng hỗ trợ nhau:

| Lớp | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| **Transport security** | Dữ liệu đi giữa các bên có được mã hóa và bảo vệ tính toàn vẹn? | HTTPS/TLS, mTLS khi cần |
| **Authentication** | Bên gọi là ai, token/chứng thực có hợp lệ? | OAuth 2.0 access token, OIDC, workload identity |
| **Authorization** | Bên gọi được phép thực hiện thao tác này trên đối tượng này? | Scope, role, ownership, tenant boundary |
| **Structural validation** | Payload có đúng cấu trúc, kiểu, kích thước, format? | DTO, JSON Schema, Bean Validation |
| **Business validation** | Nội dung có hợp lệ theo trạng thái và quy tắc nghiệp vụ? | Số lượng dương, trạng thái đơn cho phép thanh toán |
| **Safe data handling** | Dữ liệu có được sử dụng an toàn ở hệ tiếp theo? | Prepared SQL, output encoding, safe file paths |
| **Abuse protection** | Hệ thống có chịu được request quá lớn, quá nhiều, lặp lại? | Body-size limit, rate limiting, deadline, quota |
| **Monitoring & response** | Hành vi bất thường có được phát hiện và xử lý? | Audit event, metric, cảnh báo, trace |

Các lớp **không thay thế nhau**. Một JWT hợp lệ không bảo đảm chủ token sở hữu đơn hàng. Regex kiểm tra chuỗi không thay thế tham số hóa SQL. mTLS xác thực danh tính workload nhưng không thay thế phân quyền nghiệp vụ.

~~~mermaid
flowchart LR
    U[Web / Mobile / Partner] --> TLS[HTTPS + Gateway]
    TLS --> AUTHN[Xác thực token]
    AUTHN --> AUTHZ[Phân quyền request / resource]
    AUTHZ --> VAL[Kiểm tra DTO và nghiệp vụ]
    VAL --> APP[Order Service]
    APP --> OUT[Outbound client có TLS + identity + timeout]
    OUT --> PAY[Payment Service]
    APP --> EVT[Event payload validation]
    EVT --> NOTI[Notification Service]
~~~

Đây là dòng logic minh họa, không bắt buộc mỗi bước thuộc một server riêng. Những bước kiểm soát có thể diễn ra lặp lại ở Gateway, service và consumer.

## 3. Threat model và ranh giới tin cậy

Trước khi viết validation, hãy trả lời:

1. **Ai có thể gửi dữ liệu?** Người dùng, ứng dụng đối tác, service nội bộ, batch worker, webhook hay message consumer.
2. **Dữ liệu đi qua đâu?** Header, path parameter, query string, JSON body, multipart, cookie, gRPC metadata, message queue hoặc event.
3. **Tài nguyên nào cần bảo vệ?** Đơn hàng, thanh toán, thông tin cá nhân, token, file, database, các service nội bộ.
4. **Quyền nào liên quan?** Đọc, tạo, sửa, hủy; quyền theo chủ sở hữu, tổ chức/tenant, vai trò hay tình trạng tài nguyên.
5. **Nếu kiểm tra thất bại, API cần xử lý thế nào?** Trả 400, 401, 403, 404, 409, 413, 415, 429 hay 503 tùy nguyên nhân; không có một status dùng cho mọi lỗi.

**Trust boundary** không chỉ nằm giữa internet và Gateway. Nó xuất hiện tại mọi nơi dữ liệu đổi chủ thể kiểm soát: Order nhận JSON, Payment nhận REST request, consumer nhận event từ broker, worker đọc object storage, service xử lý callback của nhà cung cấp.

Ngay cả dữ liệu sinh ra từ service cùng hệ thống có thể lỗi do bug, deployment lệch phiên bản, cấu hình sai hoặc tài khoản service bị xâm nhập. Nội bộ không mặc nhiên là trusted.

## 4. Kiểm tra dữ liệu đầu vào: hợp đồng rõ ràng

### 4.1. Kiểm tra cấu trúc trước

Request phải được bind vào **DTO dành riêng cho API**, thay vì bind thẳng vào entity ORM hoặc domain aggregate. Một DTO nên mô tả đúng những field mà caller được phép nhập.

Các điều kiện phổ biến:

| Loại dữ liệu | Điều kiện kiểm tra | Sai lầm thường gặp |
| --- | --- | --- |
| Chuỗi | Không rỗng khi bắt buộc, giới hạn độ dài, format cho định danh | Chỉ kiểm tra non-null, cho phép chuỗi toàn khoảng trắng |
| Số nguyên | Min/max, không âm khi phù hợp, tránh overflow | Dùng số âm hoặc cực lớn mà không giới hạn |
| Tiền | Decimal chính xác, scale/currency rõ ràng | Dùng floating point hoặc tin giá client gửi |
| Ngày giờ | ISO 8601, time zone, khoảng thời gian hợp lý | Dựa vào giờ máy khách hoặc định dạng tùy ý |
| UUID/ID | Kiểu và format, kiểm tra sự tồn tại sau bind | Coi ID hợp lệ về format là được phép truy cập |
| Enum | Tập giá trị đóng; từ chối trạng thái không được hỗ trợ | Có nhánh mặc định âm thầm chuyển sang trạng thái khác |
| Danh sách | Giới hạn số phần tử; kiểm tra từng phần tử | List 100.000 item tiêu thụ RAM và database query |
| Object lồng nhau | Giới hạn độ sâu, kích thước; kiểm tra đệ quy | Nested DTO bỏ qua validation |
| File | Loại file, kích thước, nội dung, tên an toàn | Tin extension hoặc Content-Type do client khai báo |
| URL | Chỉ cho phép scheme, host và đích được phép | Biến server thành proxy đến mạng nội bộ |

**Allowlist theo domain** thường tốt hơn một blacklist chung chung. Chẳng hạn SKU chỉ cho phép chữ in hoa, số, dấu gạch ngang và dấu gạch dưới nếu đó thực sự là quy tắc sản phẩm; không cần áp regex này cho tên người dùng hay địa chỉ.

### 4.2. Kiểm tra nghiệp vụ sau khi bind

Cấu trúc hợp lệ chưa đủ:

- Số lượng từ 1 đến 100 là hợp lệ về kiểu, nhưng phải kiểm tra SKU tồn tại và số lượng có thể đặt.
- Mã giảm giá đúng format nhưng có thể hết hạn, không áp dụng cho sản phẩm hoặc đã hết lượt.
- Đơn hàng có trạng thái **PAID** không thể được thanh toán lại như đơn **PENDING**.
- Người dùng có quyền **orders.read** không tự động được đọc mọi orderId; service phải kiểm tra chủ sở hữu hoặc tenant.
- Giá bán, số tiền phải thu, phí và quyền giảm giá phải đến từ nguồn nghiệp vụ đáng tin, không nhận con số do client tự quyết.

Phân biệt rõ:

- **Syntactic validation:** dữ liệu có đúng shape, type, format?
- **Semantic/business validation:** dữ liệu có hợp lệ trong ngữ cảnh hiện tại?
- **Authorization:** chủ thể có được phép thực hiện thao tác trên tài nguyên đó?

Ví dụ **orderId** có thể là UUID hợp lệ nhưng thuộc tenant khác; đây là bài toán phân quyền mức đối tượng, không phải lỗi kiểu dữ liệu.

### 4.3. Normalization và canonicalization

Nếu cần chuẩn hóa dữ liệu, xác định thứ tự và giới hạn rõ ràng:

1. Giải mã theo protocol một lần tại tầng tương ứng.
2. Chuẩn hóa các field được phép theo quy tắc domain, ví dụ trim **displayName** khi nghiệp vụ yêu cầu.
3. Validate **giá trị canonical cuối cùng** mà nghiệp vụ sẽ sử dụng.
4. Lưu và ghi log theo chính sách rõ ràng; không âm thầm sửa dữ liệu quan trọng.

Tránh decode nhiều lần khiến chuỗi dạng phần trăm, slash hoặc dot-dot vượt qua kiểm tra path. Với file path, phải resolve về thư mục gốc được cấp phép và kiểm tra đường dẫn thực sau chuẩn hóa. Với username/email quốc tế, thay đổi Unicode hoặc chữ hoa/thường có thể làm thay đổi danh tính; dùng quy tắc canonical nhất quán thay vì tự ý normalize mọi chuỗi.

## 5. Ví dụ Java/Spring Boot: DTO và Bean Validation

Trong Spring Boot 3.x, dùng **Jakarta Bean Validation** cùng DTO, đặt các giới hạn cơ bản sát entrypoint. Ví dụ client tạo đơn chỉ gửi sản phẩm và số lượng; service tự tính giá.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import jakarta.validation.constraints.Pattern;

import java.util.List;

public record CreateOrderRequest(
    @NotNull
    @Size(min = 1, max = 50)
    List<@Valid OrderLineRequest> items,

    @NotBlank
    @Size(max = 120)
    String deliveryNote
) {}

public record OrderLineRequest(
    @NotBlank
    @Pattern(regexp = "[A-Z0-9_-]{1,40}")
    String sku,

    @NotNull
    @Min(1)
    @Max(100)
    Integer quantity
) {}
~~~

**Lưu ý:** Ví dụ đặt **deliveryNote** bắt buộc để minh họa; sản phẩm thật có thể cho phép ghi chú rỗng và chỉ giới hạn độ dài. DTO phải phản ánh API contract thực tế.

Controller kiểm tra dữ liệu và lấy identity từ principal đã xác thực:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public OrderResponse createOrder(
            @Valid @RequestBody CreateOrderRequest request,
            @AuthenticationPrincipal Jwt principal
    ) {
        // Service xác định giá/tồn kho và quyền truy cập theo principal.
        return orderService.createForUser(principal.getSubject(), request);
    }
}
~~~

Trong ví dụ, **OrderService** và **OrderResponse** đại diện cho lớp nghiệp vụ và DTO trả về của ứng dụng. Service thực hiện kiểm tra còn hàng, tính tổng tiền, và giới hạn truy cập theo principal; ví dụ controller không thay thế những kiểm tra đó.

Các điểm chính:

- **@Valid** yêu cầu validation của DTO đầu vào; phần tử **List<@Valid OrderLineRequest>** được kiểm tra lồng nhau.
- **@NotNull, @Size, @Pattern, @Min, @Max** giới hạn cấu trúc, độ dài và giá trị.
- **@PreAuthorize** kiểm tra scope thao tác; cần bật method security khi dùng annotation.
- **principal.getSubject()** lấy identity từ token đã được xác minh, không tin trường userId mà client tự gửi.
- Service vẫn phải kiểm tra quyền mức tài nguyên/tenant. Scope **orders.write** không chứng minh mọi đối tượng thuộc người gọi.
- Tên trường, giới hạn, permission và lỗi phản hồi là một phần của API contract cần được test.

Spring Boot cần dependency hỗ trợ validation (thường **spring-boot-starter-validation**). Nếu bean validation không được kích hoạt theo cấu hình thực tế, annotation đơn lẻ không đảm bảo request đã bị chặn.

### 5.1. Chặn mass assignment

**Mass assignment** xảy ra khi ứng dụng map mọi field client gửi trực tiếp vào entity có field nhạy cảm như **ownerId**, **role**, **status**, **approved**, **totalAmount**.

Ví dụ API cập nhật hồ sơ chỉ cho sửa **displayName** và **avatarUrl**, không cho sửa **role=ADMIN** dù JSON có field đó. Cách bảo vệ:

- Dùng request DTO có danh sách field chính xác được phép chỉnh.
- Ánh xạ từng field hợp lệ vào entity trong service.
- Đối với PATCH, kiểm soát field cho phép và phân biệt **không được gửi**, **null** và **giá trị mới**.
- Không copy toàn bộ request vào entity bằng mapper thiếu cấu hình cho field nhạy cảm.
- Cân nhắc từ chối unknown fields nếu hợp đồng API yêu cầu phát hiện client gửi nhầm, đồng thời có chính sách versioning rõ ràng.

Không dùng mỗi annotation **@JsonIgnore** trên entity như tuyến phòng thủ duy nhất.

## 6. Phân loại và phản hồi lỗi validation

API nên trả lỗi có cấu trúc, ổn định và an toàn. Ví dụ cho payload có quantity âm:

~~~json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Invalid request",
  "status": 400,
  "detail": "Request payload failed validation",
  "errors": [
    { "field": "items[0].quantity", "message": "must be greater than or equal to 1" }
  ],
  "requestId": "f34822ab"
}
~~~

**type** trong ví dụ là URL minh họa, không cần tồn tại trong ứng dụng thử nghiệm. Có thể dựa trên định dạng **Problem Details (RFC 9457)**. Thông báo nên giúp client sửa lỗi, đồng thời tránh lộ SQL, stack trace, filesystem path, secret, token, cấu hình nội bộ hoặc toàn bộ payload chứa dữ liệu cá nhân.

Bảng quy ước tham khảo:

| Tình huống | HTTP status thường phù hợp | Ghi chú |
| --- | --- | --- |
| JSON sai cú pháp hoặc DTO validation fail | **400 Bad Request** | Khác với lỗi nghiệp vụ mức trạng thái |
| Thiếu token hoặc token không hợp lệ | **401 Unauthorized** | Có cơ chế challenge phù hợp |
| Đã xác thực nhưng thiếu quyền | **403 Forbidden** | Một số API che giấu tài nguyên có thể trả 404 có chủ đích |
| Resource không tồn tại/không được tiết lộ | **404 Not Found** | Không làm lộ quyền sở hữu của tenant khác |
| Xung đột phiên bản hoặc trạng thái | **409 Conflict** | Ví dụ cập nhật đơn hàng từ version cũ |
| Body vượt giới hạn | **413 Content Too Large** | Chặn trước khi tiêu thụ quá nhiều bộ nhớ |
| Media type không được hỗ trợ | **415 Unsupported Media Type** | Ví dụ endpoint chỉ nhận application/json |
| Vượt quota/rate limit | **429 Too Many Requests** | Có thể kèm Retry-After |
| Dependency không đáp ứng tạm thời | **503 Service Unavailable** | Không ghi nhận giả là lỗi validation của client |

Với input sai, **400** thường đủ nhất quán. Một số API dùng **422 Unprocessable Content** cho payload đúng cú pháp nhưng sai quy tắc nội dung; cần chọn một contract và dùng nhất quán, không trộn ngẫu nhiên.

## 7. Xác thực API: ai đang gọi?

### 7.1. Client-facing APIs

Đối với web/mobile/partner, mô hình phổ biến:

- **OAuth 2.0** để cấp và sử dụng quyền truy cập qua access token.
- **OpenID Connect** nếu cần xác thực người dùng và truyền thông tin identity.
- **JWT access token** hoặc opaque token; chọn theo nhu cầu revocation, latency và mô hình tin cậy.

Resource server cần kiểm tra ít nhất:

1. Chữ ký hoặc introspection với nguồn cấp token đáng tin.
2. **issuer (iss)** có đúng nhà cấp token được chấp nhận?
3. **audience (aud)** có chứa định danh API đang nhận?
4. **expiration (exp)**, **not-before (nbf)** và clock skew hợp lý.
5. Scope/quyền cần thiết cho endpoint.
6. Điều kiện thu hồi và vòng đời token phù hợp với mô hình chọn.
7. Thuật toán và key nằm trong tập được cấu hình; không tin thuật toán/key do token tự yêu cầu một cách tùy tiện.

Không dùng **ID token** như access token cho API. Không chỉ decode JWT rồi tin vào các claim vì dữ liệu đã đọc ra trông hợp lệ.

### 7.2. Service-to-service APIs

Order gọi Payment có thể sử dụng **workload identity** với token được cấp cho Order, hoặc mTLS với danh tính client được xác thực. Payment phải xác định:

- Call đến từ workload nào và workload có được phép gọi endpoint không?
- Token có được cấp cho đúng Payment API không?
- Lời gọi đang thao tác thay mặt người dùng nào, nếu có? Đây là **delegation** cần thiết kế tường minh, không tự copy token người dùng sang mọi downstream.
- Request có cần thêm phân quyền theo tenant, merchant, orderId, amount hoặc workflow state?

**mTLS** vừa mã hóa vừa xác thực danh tính hai phía theo chứng chỉ, nhưng không tự biết business role, owner của giao dịch hoặc quyền của người dùng cuối.

Ví dụ Order có quyền gọi **POST /payments**, nhưng Payment vẫn phải đối chiếu số tiền/đơn hàng với nguồn đáng tin và tránh xử lý trùng.

## 8. Cấu hình Spring Security cho Resource Server

Một API stateless chỉ sử dụng **Bearer token trong Authorization header**, không dựa trên cookie/session để xác thực request, có thể bắt đầu với:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
~~~

**Giới hạn của cấu hình minh họa:**

- Chỉ áp dụng cách **disable CSRF** khi xác thực thực sự bằng token ngoài cookie và ứng dụng không dựa vào ambient browser credentials. Nếu dùng session/cookie để xác thực, phải giữ hoặc thiết kế bảo vệ CSRF tương ứng.
- Cấu hình issuer giúp decoder xác thực issuer và token theo cơ chế thư viện, nhưng **ứng dụng phải cấu hình kiểm tra audience** cho chính API nếu chưa có sẵn theo phiên bản/configuration. Không giả định audience mặc định đã được kiểm tra.
- Cần cấu hình nguồn JWKS/identity provider tin cậy, xử lý rotation key, TLS và các lỗi identity provider.
- **@EnableMethodSecurity** hỗ trợ annotation phân quyền tại method; kiểm tra quyền trong domain/service vẫn cần thiết.
- Nếu API có endpoint public khác, định nghĩa tường minh và giới hạn thông tin lộ ra. Không dùng wildcard permitAll rộng chỉ để test.
- CORS, security headers, session, OAuth scopes và cơ chế báo lỗi cần được điều chỉnh theo client thực tế.

### 8.1. Authorization theo resource và tenant

**Broken Object Level Authorization (BOLA)** là lỗi khi API chỉ kiểm tra rằng caller đăng nhập, rồi đọc tài nguyên theo ID do caller cung cấp.

Ví dụ không an toàn: service gọi repository tìm **orderId** rồi trả kết quả ngay cho bất kỳ token hợp lệ.

Cách phù hợp:

- Query dữ liệu theo **orderId + ownerId/tenantId** hoặc kiểm tra policy trước khi tiết lộ dữ liệu.
- Kiểm tra cả **read**, **update**, **cancel**, **export**; phân quyền một lần ở list API không đủ cho detail API.
- Quy tắc **tenant isolation** phải được thực thi ở service/data layer, không dựa vào header **X-Tenant-Id** do client tự khai.
- Phân biệt quyền mức chức năng (**function-level authorization**) và quyền mức đối tượng.
- Kiểm tra cả field-level authorization: người được sửa địa chỉ không đương nhiên được sửa trạng thái thanh toán.

Với service A gọi service B, cần thiết kế rõ service identity và end-user context. Không chuyển tiếp tùy tiện một header **X-User-Id** không được ký hoặc chứng minh nguồn gốc rồi coi đó là identity đáng tin.

## 9. Bảo vệ kênh giao tiếp

### 9.1. HTTPS, TLS và certificate verification

- Dùng HTTPS/TLS cho traffic đi qua mạng, bao gồm east-west traffic khi mô hình đe dọa yêu cầu.
- Ưu tiên TLS 1.3, duy trì TLS 1.2 an toàn nơi cần tương thích; loại bỏ phiên bản/cipher yếu.
- Client phải xác minh hostname và chain chứng chỉ; **không tắt certificate verification** khi gặp lỗi môi trường.
- Với reverse proxy hoặc Gateway terminate TLS, kiểm tra cách bảo vệ đoạn kết nối tiếp theo tới service; thiết kế lại mã hóa nếu trust boundary yêu cầu.
- Chỉ tin **Forwarded/X-Forwarded-For/X-Forwarded-Proto** từ proxy được kiểm soát. Header này do client tự gửi nếu proxy không xóa/ghi đè sẽ gây sai identity, scheme, IP hoặc redirect.
- Quản lý private key/chứng chỉ tập trung, luân chuyển trước khi hết hạn; không commit khóa vào source.

### 9.2. mTLS và service mesh

mTLS hữu ích để nhận dạng hai workload và bảo vệ traffic giữa service. Service mesh có thể cung cấp chính sách mTLS và luân chuyển certificate, nhưng ứng dụng vẫn phải kiểm tra chính sách nghiệp vụ.

Không đưa ra kết luận “đã ở private VPC thì không cần TLS” nếu dữ liệu nhạy cảm, nhiều team chia sẻ hạ tầng hoặc threat model có lateral movement.

### 9.3. Header, cookie, CORS và CSRF

- **Authorization** bearer token phải được coi là secret; không ghi nguyên token vào logs hoặc chuyển tiếp tràn lan.
- **CORS** là cơ chế trình duyệt kiểm soát JavaScript đọc response khác origin, không phải lớp xác thực API. Đặt allowlist origin chính xác khi dùng browser; không dùng wildcard kèm credentials.
- Nếu xác thực bằng cookie, dùng **Secure**, **HttpOnly**, **SameSite** phù hợp và bảo vệ CSRF cho thao tác thay đổi trạng thái.
- Nếu API stateless dùng Authorization bearer, CSRF có thể ít liên quan hơn, nhưng XSS trong ứng dụng web vẫn có thể đánh cắp token hoặc thực hiện hành động thay người dùng.
- Cẩn trọng với header injection, response splitting và redirect destination do client điều khiển.
- Dùng HSTS ở điểm phục vụ HTTPS công khai khi phù hợp với domain và kế hoạch triển khai.

## 10. Tránh injection và xử lý dữ liệu nguy hiểm

Input validation là một lớp, còn **safe sink handling** quyết định dữ liệu có thực sự an toàn khi được sử dụng.

### 10.1. SQL/NoSQL injection

Không nối chuỗi input trực tiếp vào query:

~~~java
// KHÔNG AN TOÀN: input có thể làm thay đổi cấu trúc câu SQL.
String sql = "SELECT * FROM orders WHERE id = '" + orderId + "'";
~~~

Hãy dùng truy vấn có tham số:

~~~java
String sql = "SELECT * FROM orders WHERE id = ?";
Order order = jdbcTemplate.queryForObject(
    sql,
    orderMapper,
    orderId
);
~~~

Giá trị có thể parameterize, nhưng **tên bảng, cột, ORDER BY field** không thể tùy tiện nhận từ user rồi bind như giá trị. Với sort field, map từ một allowlist cố định. Với NoSQL, tránh cho user cung cấp raw operator/query object nếu API không có lý do chính đáng.

### 10.2. XSS và output encoding

Chuỗi như tên hiển thị hoặc ghi chú đơn hàng có thể chứa ký tự HTML. Giữ dữ liệu dạng text và **encode theo đúng output context** khi render vào HTML, attribute, JavaScript hoặc URL. Không tự viết regex “xóa dấu nhỏ hơn” làm giải pháp XSS tổng quát; dùng API render text an toàn hoặc thư viện sanitize đúng mục tiêu khi thật sự cho phép rich HTML.

### 10.3. Path traversal

Không ghép trực tiếp input vào đường dẫn file như **uploads/ + filename**. Dùng tên file do server tạo, resolve trong thư mục được phép, kiểm tra path canonical và quyền filesystem. Với file upload, xác minh kích thước, định dạng thực, scan malware khi threat model yêu cầu, và lưu ở vùng không thể thực thi code.

### 10.4. SSRF và URL do client cung cấp

Nếu service fetch URL bên ngoài theo request của client, kẻ tấn công có thể truy cập metadata endpoint, localhost, private IP, hoặc host nội bộ.

Ưu tiên **server-defined destination** hoặc allowlist host/scheme/port. Không tin regex đơn giản trên raw URL; phải parse chuẩn, chống redirect sang đích cấm, kiểm tra DNS/IP đích trong bối cảnh mạng và giới hạn timeout, response size, tốc độ. Nếu nghiệp vụ không cần URL tùy ý, **đừng xây endpoint fetch URL tùy ý**.

### 10.5. Deserialization, content type và kích thước

- Chỉ nhận các media type được thiết kế, ví dụ **application/json**, không để serializer suy đoán kiểu tùy ý ngoài hợp đồng.
- Giới hạn kích thước HTTP body, số phần tử array, độ sâu JSON, multipart size và chi phí giải nén.
- Không bật polymorphic deserialization rộng rãi từ type name do user kiểm soát.
- Kiểm tra content type thực tế của file và dữ liệu thay vì chỉ tin filename/Content-Type header.
- Giới hạn concurrency và timeout parse/IO để một request bất thường không chiếm trọn tài nguyên.

## 11. API Gateway: vai trò và giới hạn

Gateway có thể tập trung:

- TLS termination, xác thực token ban đầu và định tuyến.
- Throttling/rate limiting theo client, API key hoặc tenant.
- Giới hạn request size, loại method/content type, một số quy tắc WAF.
- Chuẩn hóa tracing, correlation ID và route metadata.
- Chính sách CORS chung cho browser API.

Tuy nhiên service phía sau vẫn phải:

- Xác minh danh tính/ủy quyền phù hợp theo trust architecture, hoặc xác minh danh tính gateway bằng cơ chế tin cậy rõ ràng.
- Kiểm tra quyền mức tài nguyên, state transition và giá trị nghiệp vụ.
- Validate event/job/internal API không đi qua Gateway.
- Bảo vệ trực tiếp các đường giao tiếp nội bộ và downstream.

Không dùng suy luận “chỉ Gateway mới truy cập được service” làm lý do bỏ toàn bộ authorization; thay đổi mạng, cấu hình mesh hoặc service account có thể làm mở rộng access ngoài dự kiến.

## 12. Giao tiếp outbound: giữ hợp đồng đến downstream

Một request từ Order sang Payment không tự động an toàn vì đã được Order xác thực. Payment cần một contract riêng:

- Order gửi dữ liệu thanh toán đã được tính và kiểm tra bởi nguồn nghiệp vụ đáng tin.
- Payment xác thực danh tính của Order và quyền gọi.
- Payment kiểm tra **orderId, amount, currency, merchantId** và quan hệ giữa chúng.
- HTTP client dùng TLS verification, connect timeout, response timeout, giới hạn connection và retry có kiểm soát.
- Không retry mù thao tác có side effect. Sử dụng **idempotency key**, lưu trạng thái xử lý và khả năng đối soát.
- Chỉ forward các header được phép, không chuyển tiếp mọi header từ client.
- Response của downstream cũng cần parse và validate theo contract; không đưa dữ liệu trả về thẳng vào DB hoặc HTML mà thiếu kiểm soát.

Ví dụ failure mode: Order timeout sau khi Payment đã trừ tiền. Retry không có idempotency key có thể trừ lần hai. Bảo vệ giao tiếp API bao gồm tính toàn vẹn **nghiệp vụ và trạng thái**, không chỉ xác thực kết nối.

## 13. Chống replay và request trùng

Các API có side effect như tạo thanh toán, đặt hàng hoặc hoàn tiền cần phân biệt:

- **Retry hợp lệ:** client không biết lần gọi trước đã thành công hay chưa.
- **Replay độc hại:** attacker cố gửi lại request/token/signature cũ để lặp thao tác.
- **Duplicate delivery:** message broker hoặc webhook có thể giao nhiều lần theo cơ chế at-least-once.

Biện pháp theo ngữ cảnh:

1. Idempotency key theo caller và operation, ràng buộc với hash payload/các trường nghiệp vụ quan trọng.
2. Lưu kết quả xử lý có TTL/chính sách lưu rõ ràng và đồng bộ khi có concurrency.
3. Với webhook đã ký, xác minh signature bằng secret/public key chính xác, timestamp trong cửa sổ chấp nhận, nonce/event ID để chống replay.
4. Không dùng duy nhất timestamp nếu thiếu cơ chế phát hiện gửi trùng trong cửa sổ hợp lệ.
5. Không lưu hoặc log raw secret trong quá trình debug.

Idempotency không thay thế authorization. Kẻ tấn công có token hợp lệ nhưng thiếu quyền vẫn không thể dùng key cũ để lặp giao dịch của người khác.

## 14. Event-driven và asynchronous API cũng cần validation

Trong microservices, dữ liệu thường đi qua Kafka/RabbitMQ/SQS hoặc webhook. Consumer phải xem message là **untrusted input** với contract/version rõ ràng, dù producer là nội bộ.

Ví dụ event **OrderPaid**:

~~~json
{
  "eventId": "c9be09be-51de-4a81-8fb3-32bd49495fea",
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "occurredAt": "2026-11-12T02:00:00Z",
  "orderId": "7dde5db1-b3d2-45dc-a2a9-a5f5b62059d2",
  "paymentId": "20a7cc77-7c2e-41c2-ae42-3fc6fb5dd299",
  "currency": "VND",
  "amountMinor": 150000
}
~~~

Consumer cần:

- Xác định schema version được hỗ trợ; reject hoặc route DLQ đúng quy tắc khi payload sai.
- Kiểm tra **eventId** và deduplicate nếu hành động không được lặp.
- Kiểm tra semantics: orderId/paymentId có tồn tại, trạng thái có cho phép tiếp tục không.
- Không tin **amountMinor** từ một event bất kỳ để thay đổi ledger nếu event không thuộc nguồn đáng tin đã được xác thực.
- Giới hạn kích thước message và số lần retry; phân biệt lỗi schema không thể tự hết với lỗi downstream tạm thời.
- Không vô hạn requeue message độc hại gây poison-message loop.

Schema registry/Protobuf/Avro giúp kiểm soát shape và compatibility, nhưng **không** tự thực hiện business authorization.

## 15. Secrets, tokens và dữ liệu nhạy cảm

Một API có validation tốt vẫn có thể rò rỉ thông tin khi:

- Ghi **Authorization**, access token, cookie, password, secret hoặc toàn bộ request chứa PII vào logs.
- Trả stack trace, nội dung SQL hoặc đường dẫn nội bộ trong response lỗi.
- Lưu secret trong source code, image hoặc cấu hình công khai.
- Dùng chung một service credential giữa mọi microservice.
- Truyền token user sang các service không cần biết identity đó.

Nên quản lý secret qua secret manager hoặc cơ chế cấp phát được kiểm soát, giới hạn permission, xoay vòng, và có quy trình thu hồi. Mỗi service chỉ nhận quyền cần thiết.

Với tracing/logging, dùng **requestId**, **traceId**, **service**, **route template**, **outcome**, **error category**. Tránh đưa số thẻ, mật khẩu, token, dữ liệu sức khỏe hoặc payload raw vào metric labels và log mặc định. Khi cần lưu audit, định nghĩa rõ retention, access control và loại thông tin được phép ghi.

## 16. Rate limiting, resource limits và chống lạm dụng

Không có validation nào đủ nếu API nhận một triệu request hợp lệ mỗi phút từ một client. Cần kế hoạch capacity và abuse prevention:

| Cơ chế | Bảo vệ | Đánh đổi |
| --- | --- | --- |
| **Rate limiting** | Giới hạn tốc độ theo client/tenant/route | Cần chọn key đáng tin và công bằng |
| **Body size limit** | Tránh parse payload cực lớn | Cần ngoại lệ rõ ràng cho upload hợp lệ |
| **Max concurrent requests/Bulkhead** | Tránh một downstream chiếm hết worker/connection | Khi đầy phải có fast-fail/fallback đúng nghiệp vụ |
| **Timeout/deadline** | Giới hạn thời gian chờ downstream | Timeout không chứng minh thao tác có side effect đã bị hủy |
| **Pagination/limits** | Tránh query hoặc response không giới hạn | Cần cursor/filter đáng tin, giới hạn max page size |
| **Cost-based quota** | Tránh API tìm kiếm/nhiệm vụ nặng bị lạm dụng | Khó ước lượng chi phí chính xác |
| **Caching** | Giảm nhu cầu gọi downstream | Phải tách cache key theo tenant/authorization khi có dữ liệu cá nhân |

**Rate limit** không phải **authorization**. Một caller có thể đang dưới quota mà vẫn yêu cầu dữ liệu không thuộc quyền. Ngược lại, request hợp lệ cũng có thể bị 429 khi đã vượt quota.

## 17. Thiết kế thông báo lỗi không làm lộ hệ thống

Khi API từ chối request, cần cân bằng khả năng sửa lỗi và bảo mật:

- Client biết **field** nào sai và điều kiện công khai nào không đạt.
- Không trả raw exception, stack trace, database query, file path, token, nội dung secret.
- Đối với tài nguyên của người dùng khác, cân nhắc phản hồi 404 thay vì 403 nếu cần tránh lộ việc resource tồn tại; vẫn ghi audit nội bộ.
- Tránh phân biệt chi tiết “email tồn tại” / “email không tồn tại” trong luồng reset mật khẩu; cần chính sách chống account enumeration.
- Dùng mã lỗi ổn định và **requestId** để hỗ trợ khách hàng và điều tra.
- Log phía server giữ nguyên nhân theo lớp, nhưng redact dữ liệu cá nhân và secret.

Ví dụ một handler trong Spring MVC có thể chuyển **MethodArgumentNotValidException** sang Problem Details. Lỗi phát sinh ở parse JSON (**HttpMessageNotReadableException**) cần handler riêng hoặc cơ chế mặc định tương đương để trả 400 nhất quán.

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.List;
import java.util.Map;

@RestControllerAdvice
public class ApiValidationErrorHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail invalidRequest(MethodArgumentNotValidException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        problem.setTitle("Invalid request");
        problem.setDetail("Request payload failed validation");

        List<Map<String, String>> errors =
            ex.getBindingResult().getFieldErrors().stream()
                .map(error -> Map.of(
                    "field", error.getField(),
                    "message", error.getDefaultMessage() == null
                        ? "invalid value" : error.getDefaultMessage()
                ))
                .toList();

        problem.setProperty("errors", errors);
        return problem;
    }
}
~~~

Khi công khai message từ Bean Validation, chỉ dùng các ràng buộc và message do ứng dụng kiểm soát; tránh đưa nội dung lỗi do hệ thống downstream hoặc user nhập trực tiếp vào response. Ví dụ này cũng chưa thêm **requestId**, parse-error handling và xử lý quyền, cần được cấu hình trong API thực.

## 18. Cách kiểm thử theo ma trận bảo mật

Validation phải được kiểm thử cả ở **entrypoint**, đường đi qua Gateway, và các đường gọi nội bộ. Những ca nên có:

| Kiểm thử | Request/điều kiện | Kỳ vọng |
| --- | --- | --- |
| Field bắt buộc | Thiếu items | 400, không tạo order |
| Giá trị biên | quantity=0, quantity=101 | 400, điều kiện rõ |
| Danh sách lớn | items có quá 50 phần tử | 400 hoặc giới hạn body phù hợp |
| Schema sai | Sai kiểu, JSON không hợp lệ | 400, không có stack trace |
| Unknown fields | Thêm role/price/admin | Không có tác dụng; reject nếu contract yêu cầu |
| SQL/XSS | Chuỗi chứa ký tự đặc biệt | Không thay đổi query hoặc thực thi script |
| Token thiếu | Không có Authorization | 401 |
| Token sai/hết hạn | Signature, issuer, audience, exp không hợp lệ | 401 |
| Thiếu scope | Token hợp lệ nhưng thiếu orders.write | 403 |
| Sai chủ sở hữu | User A gọi orderId của User B | Từ chối, không rò rỉ dữ liệu |
| Cross-tenant | Tenant X dùng resource Tenant Y | Từ chối tại service/data layer |
| Replay request | Gửi cùng idempotency key nhiều lần | Không tạo side effect trùng |
| Downstream timeout | Payment trả chậm | Response/trạng thái đúng; không double charge |
| Broken TLS | Certificate hostname sai | Client từ chối kết nối |
| Forged proxy header | Client tự đặt X-Forwarded-* | Không thay đổi identity/source trust |
| Event lỗi | SchemaVersion không hỗ trợ hoặc eventId lặp | DLQ/deduplicate theo contract |
| Overload | Burst request, body lớn | Giới hạn tài nguyên và status thích hợp |

Ưu tiên thêm **integration test** cho đường authn/authz thực tế, ví dụ một token hợp lệ nhưng thiếu scope, token của user khác, và một resource thuộc tenant khác. Unit test validator cho thấy logic field hoạt động nhưng **không chứng minh** SecurityFilterChain, Gateway và data-scoping đã được cấu hình đúng.

Với OAuth/JWT, test không chỉ mock “đã đăng nhập”; cần ít nhất một tuyến integration kiểm tra chữ ký/issuer/audience thật với test key hoặc authorization server mô phỏng.

## 19. Kịch bản thực hành: bảo vệ Create Order từ đầu đến cuối

Giả sử request:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: create-order-req-017
~~~

~~~json
{
  "items": [
    { "sku": "BOOK-101", "quantity": 2 },
    { "sku": "JAVA-021", "quantity": 1 }
  ],
  "deliveryNote": "Giao giờ hành chính"
}
~~~

**Đường xử lý đề xuất:**

1. **Edge/Gateway:** chấp nhận TLS, giới hạn body size và request rate, chuyển request đến Order.
2. **Authentication:** Order hoặc trust layer kiểm tra access token; issuer/audience/time/signature phải hợp lệ.
3. **Authorization:** kiểm tra caller có quyền **orders.write**. Tenant/user identity lấy từ nguồn xác thực.
4. **Parsing/DTO validation:** JSON hợp lệ, danh sách 1–50 phần tử, SKU đúng format, quantity 1–100.
5. **Business validation:** SKU đang bán, số lượng được phép, giá được tính tại server, không tin totalAmount do client gửi.
6. **Resource authorization:** cart, address, voucher thuộc quyền caller/tenant.
7. **Idempotency:** nhận diện request trùng trong phạm vi chủ thể và operation; không tạo order thứ hai khi retry.
8. **Outbound calls:** Inventory/Payment nhận request với TLS, identity và contract riêng, timeout cùng retry policy an toàn.
9. **Persistence:** dùng truy vấn tham số hóa, transaction và cơ chế xử lý nhất quán cho trạng thái đơn.
10. **Response:** chỉ trả dữ liệu được phép, mã lỗi có cấu trúc, không lộ token/payment secret.
11. **Observability:** ghi outcome, trace, số lần validation failure, auth rejection, abuse rejection và dependency error.

**Một điểm cần nhớ:** nếu bước 4 thành công nhưng bước 6 thất bại, request vẫn phải bị chặn. Không được coi một payload đúng format là một thao tác được phép.

## 20. Những sai lầm thường gặp

1. **Chỉ validate ở Gateway:** event, batch hoặc internal caller có thể không đi qua Gateway; service vẫn cần kiểm tra của riêng mình.
2. **Dùng entity ORM làm request DTO:** client có thể thay đổi field quan trọng qua mass assignment.
3. **Chỉ kiểm tra JWT có thể decode:** bỏ qua chữ ký, issuer, audience, expiry hoặc scope.
4. **Phân quyền route nhưng quên resource:** bất kỳ người đăng nhập nào cũng đọc được orderId của người khác.
5. **Tin header từ proxy do client khai:** gây sai xác định nguồn request, HTTPS status hoặc identity.
6. **Dùng regex thay thế escaping/parameterized query:** vẫn có SQL injection/XSS khi đưa dữ liệu tới sink nguy hiểm.
7. **Tắt TLS verification để “sửa nhanh” lỗi certificate:** mở nguy cơ MITM.
8. **CORS allow-all với credentials:** tạo truy cập browser ngoài ý muốn; CORS cũng không thay auth.
9. **Tắt CSRF cho ứng dụng xác thực bằng cookie:** làm mất một lớp bảo vệ request thay đổi trạng thái.
10. **Không giới hạn body/array/JSON depth:** request vẫn đúng định dạng nhưng gây quá tải tài nguyên.
11. **Tin dữ liệu từ service nội bộ hoàn toàn:** producer lỗi hoặc bị xâm nhập làm hỏng consumer.
12. **Log nguyên token hoặc dữ liệu cá nhân:** tạo kênh rò rỉ không cần tấn công API trực tiếp.
13. **Retry thao tác thanh toán không có idempotency:** timeout có thể dẫn đến giao dịch trùng.
14. **Quá nhiều thông tin trong lỗi 4xx/5xx:** lộ stack trace, SQL, đường dẫn, endpoint nội bộ.
15. **Dùng kết quả validation cũ khi trạng thái thay đổi:** cần kiểm tra bất biến domain trong transaction hoặc có cơ chế chống race/TOCTOU.

## 21. Quy trình áp dụng trong dự án

Khi bắt đầu bảo vệ một API microservice, thực hiện theo thứ tự:

1. **Liệt kê endpoint và contract:** method, path, request/response DTO, field bắt buộc, chiều dài, giới hạn array và body.
2. **Đánh dấu trust boundary:** public ingress, service-to-service, webhook, broker consumer, file ingestion.
3. **Định nghĩa authn/authz:** issuer, audience, scope, owner/tenant policy, workload identity.
4. **Tách validation:** structural ở DTO, business invariant ở domain/service, policy ở authz/service.
5. **Rà soát sinks:** SQL, HTML, shell, file path, URL fetch, message publishing, logs.
6. **Bảo vệ outbound:** TLS, xác minh chứng chỉ, service identity, timeout, concurrency, retry/idempotency.
7. **Giới hạn abuse:** body, pagination, rate, quota, queue, file size, request deadline.
8. **Chuẩn hóa lỗi và audit:** status, Problem Details, correlation ID, redact secret.
9. **Kiểm thử security matrix:** sai input, sai token, cross-tenant, resource ownership, replay, overload và downstream timeout.
10. **Giám sát:** tỷ lệ 400/401/403/413/429, authz denial, lỗi 5xx, latency, cảnh báo bất thường và audit truy cập nhạy cảm.

Mọi thay đổi policy cần có kiểm thử hồi quy. Nếu một endpoint mới được công khai, hệ thống phải bảo đảm rule mặc định **deny by default** cho API cần xác thực, thay vì chỉ bảo vệ một danh sách endpoint đã biết.

## 22. Câu hỏi tự kiểm tra

**1. Nếu payload JSON đúng schema và token hợp lệ, API đã an toàn chưa?**  
Chưa. Phải kiểm tra quyền đối với object/tenant, quy tắc nghiệp vụ, giới hạn tài nguyên và cách dữ liệu được sử dụng.

**2. Tại sao không nhận totalAmount từ client rồi validate số dương?**  
Vì totalAmount là dữ liệu nghiệp vụ cần được tính từ giá/sản phẩm/khuyến mãi do server kiểm soát. Một số dương vẫn có thể là số tiền gian lận.

**3. mTLS có thay thế authorization mức đơn hàng không?**  
Không. mTLS cho biết workload gọi là ai; nó không xác định workload hoặc người dùng cuối có quyền thao tác orderId cụ thể.

**4. Tại sao cần kiểm tra audience của JWT?**  
Để ngăn token được cấp cho API khác bị dùng nhầm tại API này, ngay cả khi token được ký bởi issuer đáng tin.

**5. CORS có chặn attacker gửi HTTP request trực tiếp không?**  
Không. CORS chủ yếu là chính sách trình duyệt đối với JavaScript cross-origin; server vẫn cần xác thực, phân quyền và kiểm tra request.

**6. Cách chống injection đáng tin khi truy vấn database là gì?**  
Dùng truy vấn tham số hóa/ORM an toàn và allowlist cho cấu trúc query động; validate input là lớp bổ trợ.

**7. Tại sao webhook và event từ broker cần kiểm tra lại?**  
Vì chúng vượt qua trust boundary riêng, có thể sai schema, trùng lặp, giả mạo hoặc mang dữ liệu không phù hợp quy tắc nghiệp vụ.

**8. Khi timeout xảy ra trong POST /payments, có thể giả định payment chưa được thực hiện?**  
Không. Phải có idempotency, khả năng truy vấn trạng thái và đối soát để tránh tạo hoặc ghi nhận giao dịch trùng.

## Tài liệu tham khảo

- OWASP API Security Top 10 (2023): https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- OWASP Input Validation Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
- OWASP REST Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP SSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- Spring Framework — Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Security — OAuth 2.0 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068

**Ghi nhớ:** API an toàn cần kiểm tra **dữ liệu gì được gửi**, **ai gửi**, **người đó được làm gì**, **dữ liệu được dùng ở đâu**, và **điều gì xảy ra khi hệ thống bị lỗi hoặc quá tải**. Những câu hỏi này phải được trả lời ở từng ranh giới tin cậy của hệ thống microservices.
