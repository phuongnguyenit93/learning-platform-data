# Tenant authority trong Spring Security

**Chương:** Spring Security authorities  
**Chủ đề:** Tenant authority  
**Phạm vi module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS — mô hình tin cậy và vòng đời token bảo mật, xác thực và phân quyền bằng access token/refresh token, JWT/opaque token trong OAuth 2.0/OIDC.

## 1. Tenant authority giải quyết vấn đề gì?

Trong hệ thống **multi-tenant** (đa khách hàng/tổ chức), nhiều tenant dùng chung một ứng dụng nhưng dữ liệu và quyền của họ phải được cách ly. Một người có thể là quản trị viên tại tenant A, chỉ được đọc tại tenant B và không có quyền gì tại tenant C.

**Tenant authority** là cách biểu diễn **quyền thực hiện một hành động trong ngữ cảnh tenant cụ thể** để Spring Security tham gia quyết định cho phép hoặc từ chối truy cập. Đây là mô hình thiết kế của ứng dụng trên nền **GrantedAuthority**, không phải một kiểu authority hay một claim JWT chuẩn được Spring Security định nghĩa sẵn.

Ví dụ:

| Người dùng | Tenant | Quyền | Kết quả mong muốn |
|---|---|---|---|
| An | tenant-a | orders:read, orders:write | Xem và sửa đơn hàng thuộc tenant-a |
| An | tenant-b | orders:read | Chỉ xem đơn hàng thuộc tenant-b |
| An | tenant-c | Không có | Không truy cập dữ liệu tenant-c |
| Bình | tenant-a | orders:read | Chỉ xem đơn hàng thuộc tenant-a |

Nếu chỉ kiểm tra authority chung như **ROLE_ADMIN** hoặc **SCOPE_orders.write**, ứng dụng có nguy cơ cho phép An dùng quyền tại tenant A để sửa dữ liệu tenant B. Hai điều kiện cần được đáp ứng đồng thời:

1. Chủ thể có **quyền thao tác** phù hợp trong tenant đang được yêu cầu.
2. **Đối tượng dữ liệu** thực sự thuộc tenant đã được phép truy cập.

Mục tiêu sau bài học: phân biệt identity, role, scope và tenant authority; chọn cách biểu diễn quyền trong token; ánh xạ claims thành authorities; thực thi kiểm soát tenant ở HTTP, service và database; kiểm thử ngăn truy cập chéo tenant.

## 2. Các khái niệm không được đánh đồng

| Khái niệm | Trả lời câu hỏi | Ví dụ | Điều cần nhớ |
|---|---|---|---|
| Authentication | Ai đang gọi API? | subject = user-123 | Xác thực thành công chưa đồng nghĩa có quyền đọc dữ liệu |
| Tenant identity | Đang thao tác trong tenant nào? | tid = tenant-a | Phải có nguồn đáng tin và ràng buộc với tài nguyên |
| Role | Trong tenant đó, chủ thể đảm nhiệm vai trò gì? | ADMIN, VIEWER | Vai trò có thể khác nhau giữa các tenant |
| Permission / authority | Chủ thể được thực hiện hành động nào? | TENANT_ORDERS_READ | Spring Security kiểm tra GrantedAuthority, chuỗi tên do ứng dụng quy định |
| OAuth 2.0 scope | Access token được cấp phạm vi ủy quyền nào? | SCOPE_orders.read | Scope có thể là phạm vi API chung, không tự mang ngữ cảnh tenant |
| Resource ownership | Bản ghi thuộc tenant nào? | orders.tenant_id = tenant-a | Phải kiểm tra tại nơi truy xuất dữ liệu |

Trong Spring Security:

- **Authentication** chứa principal và tập **GrantedAuthority** đã được ánh xạ.
- **hasAuthority('TENANT_ORDERS_READ')** so khớp nguyên văn một authority.
- **hasRole('ADMIN')** theo quy ước mặc định tìm authority **ROLE_ADMIN**. Role không tự gắn tenant.
- **JwtGrantedAuthoritiesConverter** mặc định có thể ánh xạ scope của JWT thành các authority mang tiền tố **SCOPE_**; nó không tự hiểu claim **tid** hay permission riêng của tenant.

Vì vậy, một authority như **TENANT_ORDERS_READ** chỉ có ý nghĩa *trong tenant hiện hành* khi ứng dụng đồng thời kiểm tra tenant hiện hành. Nếu bỏ bước này, tên authority nghe có vẻ an toàn nhưng vẫn có thể dẫn tới leo thang quyền giữa các tenant.

## 3. Mô hình tin cậy: token chứng minh gì, ứng dụng còn phải kiểm tra gì?

Một kiến trúc thường gặp:

~~~mermaid
flowchart TD
    A[Client gửi access token] --> B[Spring Security Resource Server]
    B --> C{JWT hợp lệ hoặc opaque token active?}
    C -->|Không| D[401 Unauthorized]
    C -->|Có| E[Đọc claims đã được xác thực]
    E --> F[Ánh xạ scope và tenant permissions thành authorities]
    F --> G{Có permission và tenant phù hợp?}
    G -->|Không| H[403 Forbidden]
    G -->|Có| I[Truy vấn dữ liệu theo tenant_id + resource_id]
    I --> J{Có bản ghi thuộc tenant?}
    J -->|Không| K[404 Not Found]
    J -->|Có| L[Trả dữ liệu được phép]
~~~

**Ranh giới tin cậy quan trọng:**

1. **Authorization Server / Identity Provider** xác thực người dùng, xác định tenant membership và quyền, phát hành access token cho API phù hợp.
2. **Resource Server** xác thực nguồn và tính hợp lệ của token trước khi tin các claims: chữ ký JWT hoặc kết quả introspection của opaque token, issuer, audience, thời hạn và các yêu cầu khác.
3. **Ứng dụng nghiệp vụ** đối chiếu quyền của người dùng với tenant trên đường dẫn/ngữ cảnh và tenant sở hữu tài nguyên. Token hợp lệ vẫn có thể bị từ chối truy cập.
4. **Database hoặc lớp repository** giới hạn dữ liệu theo tenant. Quy tắc này là lớp bảo vệ độc lập với bộ lọc HTTP.

Không dùng tenant ID từ URL, header **X-Tenant-Id**, request body hoặc query parameter như bằng chứng người dùng thuộc tenant đó. Những giá trị này chỉ là **tenant được yêu cầu**; chúng phải được kiểm tra với quyền lấy từ nguồn tin cậy. Không giải mã payload JWT rồi tin ngay khi chưa xác minh token.

### Ví dụ luồng truy cập

An có access token cho **tenant-a**, quyền **orders:read**. Khi gọi:

~~~http
GET /api/tenants/tenant-a/orders/70e50b36-9e0d-48ad-9dc4-7b522667d3e9
Authorization: Bearer <access-token>
~~~

Resource Server xác thực token, Spring Security thấy quyền đọc, ứng dụng xác nhận **tid = tenant-a**, và repository tìm đơn hàng bằng **cả order_id lẫn tenant_id**. Nếu An thay đường dẫn thành **tenant-b**, yêu cầu phải bị từ chối dù access token còn hiệu lực và vẫn có authority đọc đơn hàng.

## 4. Thiết kế claims cho access token

Một lựa chọn đơn giản, dễ kiểm tra là **mỗi access token được cấp cho một active tenant**. Payload minh họa dưới đây là dữ liệu *sau khi token đã được xác thực*, không phải mẫu token có thể tự sửa ở client:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000900,
  "tid": "tenant-a",
  "tenant_permissions": ["orders:read", "orders:write"],
  "scope": "orders.api"
}
~~~

Các trường chính:

| Claim | Ý nghĩa | Nơi xử lý |
|---|---|---|
| iss | Bên phát hành token được tin cậy | Cấu hình/validator của Resource Server |
| aud | API đích được phép sử dụng token | Audience validator, phải khớp API hiện tại |
| sub | Định danh chủ thể | Principal và audit |
| iat, nbf, exp | Thời điểm phát hành, bắt đầu hiệu lực, hết hạn | Token validator; có dung sai đồng hồ phù hợp |
| tid | Tenant hiện hành đã được bên phát hành xác nhận | Kiểm tra bằng tenant của yêu cầu |
| tenant_permissions | Quyền trong tenant thuộc claim tid | Converter / dịch vụ phân quyền |
| scope | Phạm vi OAuth 2.0 được cấp cho client | Mapping SCOPE_ hoặc policy riêng |

**tid** và **tenant_permissions** là claims tùy biến; đặt tên và định nghĩa chính xác trong hợp đồng giữa Authorization Server và Resource Server. Tenant ID nên là định danh ổn định, không dùng tên hiển thị dễ đổi hoặc có khả năng trùng. Permission cũng cần một danh mục tên được định nghĩa trước.

Chỉ Authorization Server đáng tin mới được quyết định tenant membership và quyền tương ứng. Client có thể *yêu cầu* chọn tenant khi đăng nhập/đổi tenant, nhưng máy chủ phải xác minh membership trước khi cấp token có claim **tid** mới. Không nên để API nhận bất kỳ giá trị **tid** do client gửi rồi tự thêm authorities tương ứng.

### Một người có nhiều tenant

Có hai cách thiết kế thông dụng:

| Thiết kế | Cách vận hành | Rủi ro/cân nhắc |
|---|---|---|
| Một active tenant trên mỗi access token | Chuyển tenant qua luồng cấp token/đổi token có kiểm tra membership; **tid** và permissions ứng với duy nhất tenant đó | Kiểm tra quyền đơn giản, nhưng cần quy trình đổi tenant |
| Một token chứa quyền của nhiều tenant | Claim có cấu trúc gắn từng tenant với permission riêng; mỗi request chọn tenant và kiểm tra đúng nhánh | Cần bộ kiểm tra theo tenant, token lớn và dễ sai khi gộp quyền |

Nếu token có quyền **tenant-a:orders:write** và **tenant-b:orders:read**, tuyệt đối không gộp thành một authority chung **TENANT_ORDERS_WRITE** rồi sử dụng authority ấy cho mọi tenant. Với phương án nhiều tenant, chính sách phải tra theo khóa tenant cụ thể, ví dụ **permissions[requestedTenantId]**, trước khi ra quyết định.

## 5. Triển khai với Spring Security 6 và OAuth 2.0 Resource Server

Ví dụ dưới đây sử dụng **JWT access token** cho một active tenant. Giả định Resource Server đã cấu hình **JwtDecoder**, trusted issuer và bộ kiểm tra audience cho **orders-api**; phần ví dụ tập trung vào việc chuyển claims đã xác thực thành authorities.

### 5.1. Ánh xạ permissions thành GrantedAuthority

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(registry -> registry
                .requestMatchers("/api/tenants/**").authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(jwt -> jwt.jwtAuthenticationConverter(tenantJwtConverter())))
            .build();
    }

    @Bean
    Converter<Jwt, ? extends AbstractAuthenticationToken> tenantJwtConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

        return jwt -> {
            Collection<GrantedAuthority> authorities =
                new ArrayList<>(scopeConverter.convert(jwt));

            String tokenTenantId = jwt.getClaimAsString("tid");
            List<String> permissions =
                jwt.getClaimAsStringList("tenant_permissions");

            // Chỉ cấp tenant authority khi token có ngữ cảnh tenant.
            if (tokenTenantId != null && !tokenTenantId.isBlank()
                    && permissions != null) {
                for (String permission : permissions) {
                    switch (permission) {
                        case "orders:read" ->
                            authorities.add(new SimpleGrantedAuthority(
                                "TENANT_ORDERS_READ"));
                        case "orders:write" ->
                            authorities.add(new SimpleGrantedAuthority(
                                "TENANT_ORDERS_WRITE"));
                        default -> {
                            // Quyền ngoài danh mục không được tự động cấp.
                        }
                    }
                }
            }

            return new JwtAuthenticationToken(
                jwt, authorities, jwt.getSubject());
        };
    }
}
~~~

Converter có ba lựa chọn có chủ đích:

- Giữ mapping scope theo mặc định (**SCOPE_...**) để các chính sách API chung vẫn có thể dùng scope; permission tenant được bổ sung với tên riêng.
- Chỉ chấp nhận các permission có trong **allowlist**. Không gắn nguyên văn bất kỳ chuỗi claim nào thành authority đặc quyền, đặc biệt khi nguồn token không được kiểm soát chặt.
- Không coi authority **TENANT_ORDERS_READ** là quyền xuyên mọi tenant. Đây chỉ là quyền trong **tid** của access token; điều kiện tenant vẫn cần được thực thi tại service.

Đoạn code minh họa tập trung vào ánh xạ quyền. Khi triển khai thật, phải cấu hình decoder/validator kiểm tra chữ ký, thuật toán được chấp nhận, **iss**, **aud**, **exp**, **nbf** và những yêu cầu riêng của tổ chức. **issuer-uri** giúp Resource Server tìm cấu hình/khoá công khai phù hợp, nhưng **audience** vẫn cần được xác minh rõ ràng cho API được bảo vệ. Không dùng ID token của OIDC hoặc refresh token thay cho access token tại API.

### 5.2. Kiểm tra tenant được yêu cầu

Tạo một thành phần chính sách trả về false nếu principal không phải JWT authentication hoặc claim **tid** không trùng với tenant trong yêu cầu:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("tenantGuard")
public class TenantGuard {

    public boolean matches(Authentication authentication, String requestedTenantId) {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        String tokenTenantId = jwtAuth.getToken().getClaimAsString("tid");
        return tokenTenantId != null
            && !tokenTenantId.isBlank()
            && tokenTenantId.equals(requestedTenantId);
    }
}
~~~

Áp dụng chính sách khi truy cập dữ liệu:

~~~java
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('TENANT_ORDERS_READ') " +
        "and @tenantGuard.matches(authentication, #tenantId)")
    public Order read(@P("tenantId") String tenantId, UUID orderId) {
        return repository.findByTenantIdAndId(tenantId, orderId)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Trong ví dụ, **Order** và **OrderRepository** là các kiểu nghiệp vụ của ứng dụng; repository cần cung cấp truy vấn có cả **tenantId** và **orderId**. Chú thích **@P("tenantId")** giúp Spring Security biết tên tham số để biểu thức **#tenantId** hoạt động ổn định dù cách biên dịch không giữ tên tham số.

Ba tầng kiểm soát có vai trò khác nhau:

1. HTTP yêu cầu đã xác thực trước khi đi vào API tenant.
2. **@PreAuthorize** yêu cầu cả quyền đọc lẫn claim **tid** trùng tenant đang gọi. Đối với thao tác ghi, dùng permission **TENANT_ORDERS_WRITE** tương ứng.
3. Repository truy vấn theo **tenant_id** và **id**, do đó không thể trả về đơn hàng của tenant khác chỉ vì client biết ID bản ghi.

Nếu chỉ gọi **findById(orderId)** rồi mới so sánh sau khi đã tải dữ liệu, hệ thống dễ bỏ sót kiểm tra ở các nhánh khác, phát sinh rò rỉ log/cache hoặc lỗi kiểm soát truy cập. Nên đưa điều kiện tenant vào truy vấn ngay từ đầu; database row-level security có thể bổ sung một lớp bảo vệ khi hệ thống đủ phức tạp.

### 5.3. HTTP status và lỗi phải xử lý

| Tình huống | Phản hồi thường gặp | Ý nghĩa |
|---|---|---|
| Không có token, token sai chữ ký/hết hạn, token bị từ chối | 401 | Không có xác thực hợp lệ cho API |
| Token hợp lệ nhưng thiếu authority hoặc tid không khớp tenant yêu cầu | 403 | Đã xác thực nhưng không được phép thực hiện hành động |
| Được phép truy vấn tenant, nhưng bản ghi không tồn tại trong tenant đó | 404 | Không tìm thấy tài nguyên trong phạm vi được phép |

Có hệ thống chủ động dùng **404** cho một số truy cập bị cấm để hạn chế tiết lộ sự tồn tại của tài nguyên; cần có chính sách nhất quán và tránh ghi dữ liệu nhạy cảm trong phản hồi lỗi.

## 6. Những biến thể thường gặp

### 6.1. Authority chứa tenant ID ngay trong tên

Một số ứng dụng biểu diễn quyền dưới dạng **TENANT_tenant-a_ORDERS_READ**. Cách này có thể phù hợp với tập tenant nhỏ và việc kiểm tra đã được đóng gói cẩn thận. Tuy nhiên, ứng dụng phải chuẩn hóa tenant ID và cấu trúc tên để tránh đụng độ/nhầm lẫn, phải đảm bảo chỉ phát hành authority từ entitlement đã xác minh, và vẫn kiểm tra tài nguyên thực sự thuộc tenant tương ứng.

Với hệ thống có nhiều tenant hoặc quyền thay đổi thường xuyên, việc nhét mọi cặp tenant–permission vào một tập chuỗi authorities thường làm token lớn, khó thu hồi và dễ vô tình gộp quyền. Thiết kế **active tenant + permission** hoặc **policy service nhận tenantId và permission** thường dễ kiểm soát hơn.

### 6.2. Opaque access token

Opaque token không chứa payload JWT mà Resource Server tự xác minh chữ ký được. Server thường dùng **introspection endpoint** của Authorization Server để xác nhận token còn active và nhận về các thuộc tính cần thiết. Sau introspection, ứng dụng vẫn phải kiểm tra tenant, permission và tenant của bản ghi như với JWT.

**JwtAuthenticationToken** và converter ở trên là ví dụ riêng cho JWT; khi dùng opaque token phải cấu hình **OpaqueTokenIntrospector** và ánh xạ principal/authorities tương ứng. Không giả định rằng đổi loại token sẽ tự giải quyết bài toán phân quyền tenant.

### 6.3. RBAC, ABAC và policy ở cấp đối tượng

- **RBAC**: role trong tenant được ánh xạ thành permission, ví dụ TENANT_ADMIN → orders:read và orders:write.
- **ABAC**: quyết định phụ thuộc thuộc tính bổ sung, ví dụ tenant, phòng ban, trạng thái đơn hàng, chủ sở hữu, thời gian.
- **Resource-based authorization**: một người có thể đọc một đơn hàng cụ thể nhưng không có quyền đọc mọi đơn hàng trong tenant.

Tenant authority là một điều kiện trong quyết định phân quyền; nó không thay thế rule nghiệp vụ ở cấp đối tượng. Nếu dữ liệu phân quyền thay đổi tức thời hoặc logic quá phức tạp, đưa quyết định vào service/policy engine có thể phù hợp hơn việc cố mã hóa toàn bộ chính sách trong JWT.

## 7. Vòng đời token và sự thay đổi quyền tenant

Tenant authority chịu tác động trực tiếp từ vòng đời access token:

| Giai đoạn | Trách nhiệm cần thực hiện |
|---|---|
| Đăng nhập / chọn tenant | Xác thực người dùng; tra membership và quyền của tenant được chọn từ nguồn đáng tin |
| Phát hành token | Gắn **tid**, permission tối thiểu, **aud** chính xác, issuer và thời gian sống hợp lý; ký JWT hoặc quản lý opaque token |
| Tiếp nhận token | Xác thực chữ ký hoặc introspection; kiểm tra issuer, audience, hạn dùng và trạng thái hợp lệ |
| Ánh xạ & quyết định | Chuyển claims đã xác thực thành authorities; đối chiếu tenant hiện hành với tenant được yêu cầu |
| Truy cập dữ liệu | Mọi truy vấn/sửa đổi bám tenant_id; áp dụng thêm kiểm tra cấp bản ghi |
| Thu hồi membership / giảm quyền | Không tiếp tục cấp token với quyền cũ; cân nhắc token TTL ngắn, kiểm tra quyền hiện thời, token version hoặc cơ chế thu hồi/introspection |
| Đổi tenant | Cấp token mới cho active tenant hợp lệ hoặc đánh giá lại quyền từng tenant; không đổi tenant chỉ bằng sửa header |

**JWT đã phát hành thường tiếp tục có hiệu lực đến khi hết hạn** nếu API chỉ kiểm tra chữ ký/thời gian và không có cơ chế thu hồi bổ sung. Khi người dùng bị xóa khỏi tenant hoặc hạ quyền, chính sách cần xác định độ trễ chấp nhận được: access token ngắn hạn, denylist theo **jti** (nếu hạ tầng hỗ trợ), token version, kiểm tra membership tại server ở hành động nhạy cảm, hoặc opaque token có introspection. Không khẳng định rằng xóa vai trò trong database sẽ tự làm JWT cũ mất hiệu lực.

**Refresh token** chỉ phục vụ nhận access token mới tại Authorization Server. Phải lưu trữ và bảo vệ phù hợp, cân nhắc rotation và phát hiện reuse; khi refresh hoặc đổi tenant phải xác minh membership mới nhất. Refresh token không dùng làm bearer token để truy cập API nghiệp vụ.

Để giảm hậu quả token bị đánh cắp hoặc phát lại:

- Dùng TLS; tránh ghi access token, refresh token hoặc toàn bộ claims nhạy cảm vào log.
- Giữ access token ngắn hạn và cấp theo nguyên tắc ít quyền nhất; cân nhắc DPoP/mTLS nếu hạ tầng hỗ trợ ràng buộc token với bên gửi.
- Với ứng dụng trình duyệt, cân nhắc BFF hoặc session cookie **HttpOnly, Secure, SameSite** và kiểm soát CSRF khi dùng cookie; đánh giá kỹ rủi ro lưu token trong JavaScript-accessible storage.
- Không dùng token dành cho API khác (**aud** khác), token của issuer không tin cậy hoặc ID token OIDC để vượt qua kiểm tra quyền.
- Gắn tenant vào cache key, job, event và tác vụ bất đồng bộ; không để tenant context của request trước lan sang request/tác vụ sau.

## 8. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Chỉ kiểm tra **authenticated()** | Mọi người đã đăng nhập có thể tới endpoint tenant | Kiểm tra permission và tenant |
| Chỉ kiểm tra **hasAuthority('TENANT_ORDERS_READ')** | Quyền đọc tenant A có thể bị dùng cho tenant B | So **tid** với tenant yêu cầu và giới hạn query |
| Tin **X-Tenant-Id** hoặc tenant trong path như membership | Client tự chọn tenant khác | Xác minh quyền từ token tin cậy hoặc kho entitlement |
| Giải mã JWT nhưng bỏ qua verify signature, issuer, audience, expiry | Token giả/cấp cho API khác được tin | Dùng Resource Server và validators đúng |
| Gộp quyền nhiều tenant vào authority chung | Leo thang quyền ngang tenant | Ràng buộc mỗi permission với đúng tenant |
| Truy vấn bản ghi chỉ bằng ID | Rò rỉ dữ liệu chéo tenant khi quên kiểm tra | Query theo **tenant_id + resource_id** |
| Chuyển role thành authority không có allowlist | Claim ngoài hợp đồng có thể tạo quyền đặc biệt | Map qua danh mục permission được cho phép |
| Dựa vào JWT dài hạn sau khi thu hồi quyền | Quyền cũ vẫn được chấp nhận | Chiến lược TTL/thu hồi và kiểm tra quyền động |
| Tưởng **SCOPE_** đồng nghĩa quyền tenant | Scope chung bị dùng cho dữ liệu tenant cụ thể | Phân biệt scope API và quyền tenant |

## 9. Kịch bản kiểm thử nên có

Giả sử token của An có **tid = tenant-a**, **tenant_permissions = [orders:read]** và audience hợp lệ cho orders-api.

| Test | Request / điều kiện | Kết quả mong đợi |
|---|---|---|
| Cùng tenant, đủ quyền | GET đơn hàng thuộc tenant-a | Cho phép (200 nếu tồn tại) |
| Khác tenant, cùng permission | GET dưới đường dẫn tenant-b | Từ chối (thường 403) |
| Cùng tenant, thiếu quyền ghi | PUT đơn hàng tenant-a | 403 |
| Tài nguyên ID thuộc tenant khác | GET đường dẫn tenant-a với order ID của tenant-b | 404 do query lọc tenant |
| Không có token | GET endpoint bảo vệ | 401 |
| Token hết hạn / chữ ký sai | GET endpoint bảo vệ | 401 |
| Audience không dành cho orders-api | GET endpoint bảo vệ | 401 |
| Claim tid bị thiếu hoặc rỗng | GET endpoint tenant | Không có tenant authority hoặc bị tenant guard chặn |
| Permission không nhận diện | Claim chứa orders:superadmin | Không tự cấp authority mới |
| Đã mất membership nhưng JWT chưa hết hạn | Gọi API sau khi bị hạ quyền | Tuân theo chính sách thu hồi đã thiết kế; test rõ độ trễ |
| Chuyển tenant hợp lệ | Đổi từ tenant-a sang tenant-b | Chỉ quyền được phê duyệt cho tenant-b được áp dụng |
| Cache/async job | Hai tenant có ID bản ghi trùng nhau | Không dùng lẫn dữ liệu hoặc tenant context |

Cần bổ sung kiểm thử tích hợp với **Spring Security Test**, token hợp lệ đã ký hoặc decoder/introspector giả lập phù hợp, cùng repository/database thật hoặc test database để chứng minh truy vấn bị giới hạn bởi tenant. Kiểm thử chỉ mock mỗi **hasAuthority** sẽ không phát hiện lỗi cách ly dữ liệu ở repository.

## 10. Bài toán tự kiểm tra

**Tình huống:** Một token hợp lệ chứa quyền đọc cho tenant A và quyền ghi cho tenant B. Nhóm phát triển gộp tất cả permissions thành **TENANT_ORDERS_READ** và **TENANT_ORDERS_WRITE**, rồi dùng **@PreAuthorize("hasAuthority('TENANT_ORDERS_WRITE')")** cho mọi URL **/api/tenants/{tenantId}/orders**.

**Câu hỏi:** Người dùng có thể thực hiện thao tác không được phép nào? Sửa thiết kế như thế nào?

**Gợi ý trả lời:** Vì authority ghi đã bị gộp, request ghi vào tenant A cũng có thể vượt qua kiểm tra dù người dùng chỉ có quyền ghi tại B. Cần kiểm tra permission **trong ngữ cảnh tenant được yêu cầu**, dùng access token theo active tenant hoặc policy kiểm tra mapping tenant → permissions; đồng thời mọi lệnh cập nhật phải lọc theo tenant_id của dữ liệu.

### Ghi nhớ

**Một access token hợp lệ không đồng nghĩa có quyền truy cập mọi tenant.** Spring Security authorities trả lời câu hỏi chủ thể có loại quyền nào; thiết kế tenant authority phải bổ sung câu hỏi quyền ấy **được áp dụng ở tenant nào** và **tài nguyên nào thực sự thuộc tenant đó**. Ba kiểm soát — token đáng tin, permission đúng tenant và truy cập dữ liệu có ràng buộc tenant — phải xuất hiện cùng nhau để chống truy cập chéo tenant.
