# Không tin header identity từ client

> **Chương:** API gateway  
> **Module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS — mô hình tin cậy và vòng đời token, JWT, opaque token, access/refresh token trong xác thực, phân quyền và OAuth 2.0/OIDC.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao các HTTP header như **X-User-Id**, **X-Role**, **X-Authenticated-User** hoặc **X-Forwarded-User** do client gửi không chứng minh được danh tính.
2. Xác định ranh giới tin cậy giữa client, API gateway, identity provider và dịch vụ phía sau.
3. Thiết kế luồng xác thực access token, kiểm tra claims/scope/audience, loại bỏ header giả và chuyển tiếp ngữ cảnh danh tính một cách an toàn.
4. Phân biệt hai kiến trúc: backend tự kiểm tra access token và backend nhận ngữ cảnh danh tính từ gateway qua kênh đã xác thực.
5. Kiểm thử các tình huống giả mạo danh tính, leo thang quyền, bypass gateway và cấu hình proxy sai.

## 1. Vấn đề: Header có thể do bất kỳ client nào tự đặt

HTTP header là dữ liệu của request. Trên đường đi từ trình duyệt, ứng dụng di động, script hoặc một máy bên ngoài đến API gateway, client có thể tự thêm header với tên và giá trị tùy ý:

~~~http
GET /api/orders/me HTTP/1.1
Host: api.example.com
X-User-Id: 1
X-Role: ADMIN
X-Authenticated-User: alice
~~~

Các chuỗi **1**, **ADMIN**, **alice** trong ví dụ trên chỉ là *lời khai của bên gửi*. Nếu gateway hoặc backend dùng chúng làm danh tính đã xác thực, kẻ tấn công có thể giả làm người dùng khác hoặc tự nhận quyền quản trị.

Một lỗi thường gặp:

~~~text
Client tự đặt X-User-Id: victim
         |
         v
API gateway chuyển nguyên header
         |
         v
Orders Service đọc X-User-Id và trả đơn hàng của victim
~~~

Lỗi không nằm ở tên header; lỗi nằm ở quyết định **tin dữ liệu chưa được chứng thực như một danh tính bảo mật**. Đổi tên thành **X-Internal-User**, **X-Auth-User** hay **X-Verified-Subject** cũng không an toàn nếu client vẫn có thể gửi giá trị đó và hệ thống vẫn tin nó.

### Phân biệt dữ liệu và bằng chứng xác thực

| Thông tin nhận được | Có thể dùng để làm gì? | Điều kiện để tin cậy |
|---|---|---|
| **X-User-Id**, **X-Role** từ Internet | Dữ liệu request không tin cậy; thường phải loại bỏ | Không được dùng trực tiếp làm principal hoặc quyền |
| **Authorization: Bearer ...** | Credential để bắt đầu bước xác thực | Phải xác minh token hợp lệ, đúng issuer, audience, thời hạn và quyền |
| Claim **sub** trong JWT | Định danh chủ thể của token | Chỉ đáng tin sau khi kiểm tra chữ ký, thuật toán, issuer, audience và các ràng buộc liên quan |
| Claim **scope/scp** hoặc quyền trong token | Dữ liệu đầu vào cho phân quyền | Chỉ dùng sau xác thực và ánh xạ theo chính sách API |
| Header identity do gateway tạo | Ngữ cảnh danh tính cho dịch vụ tin cậy | Gateway phải tự xác thực nguồn danh tính, xóa giá trị client gửi; backend xác thực gateway và chặn truy cập bypass |
| **X-Forwarded-For**, **Forwarded**, **X-Forwarded-Proto** | Thông tin proxy về IP/protocol gốc | Chỉ tin chuỗi proxy được quản lý; không thay thế xác thực người dùng |

**Nguyên tắc:** Hệ thống cần xác minh *ai đã xác nhận danh tính và bằng cách nào*, thay vì chỉ xem một request đang chứa tên người dùng nào.

## 2. Ranh giới tin cậy trong kiến trúc API gateway

~~~mermaid
flowchart LR
    C["Client / Internet<br/>Request + header tùy ý"] -->|HTTPS| G["API gateway<br/>Chặn header giả<br/>Xác thực access token"]
    I["Authorization Server / IdP<br/>JWKS hoặc introspection"] -->|Thông tin xác minh| G
    G -->|mTLS / mạng nội bộ có kiểm soát| S["Orders Service<br/>Kiểm tra nguồn + phân quyền"]
    C -.->|"Giả mạo X-Role: ADMIN"| G
~~~

Có ba ranh giới cần phân biệt:

- **Client → Gateway:** Mặc định mọi header do client kiểm soát đều không tin cậy. HTTPS bảo vệ request khi truyền đi, nhưng không biến header tự khai thành bằng chứng danh tính.
- **Gateway → Backend:** Gateway có thể là thành phần thực thi xác thực, nhưng backend cần xác minh request thật sự đến từ gateway đáng tin cậy. Dịch vụ không được mở một đường truy cập khác khiến kẻ tấn công gửi thẳng header identity giả.
- **IdP/Authorization Server → Gateway hoặc Backend:** JWT được xác minh bằng khóa/thuật toán phù hợp; opaque access token được kiểm tra qua cơ chế introspection được bảo vệ. Chỉ sau kiểm tra mới có thể tạo principal, scopes và ngữ cảnh tenant.

Một gateway được đặt ở phía trước tất cả API **chưa đủ** để đảm bảo ranh giới tin cậy. Nếu backend vẫn lộ ra Internet, ingress phụ, load balancer khác hoặc cổng debug chưa khóa, kẻ tấn công có thể bỏ qua gateway.

## 3. Kịch bản tấn công và hậu quả

### 3.1. Mạo danh người dùng (identity spoofing)

Backend lấy ID người dùng từ header để truy vấn dữ liệu:

~~~java
// Sai: người gọi có thể tự đặt X-User-Id.
@GetMapping("/orders/me")
public List<Order> myOrders(@RequestHeader("X-User-Id") String userId) {
    return orderService.findByOwner(userId);
}
~~~

Người dùng A chỉ cần đổi header thành ID của B để yêu cầu dữ liệu B, nếu không có bước kiểm tra khác. Đây có thể trở thành lỗi **broken object level authorization (BOLA/IDOR)**.

### 3.2. Leo thang quyền (privilege escalation)

Một dịch vụ dùng **X-Role: ADMIN** để cho phép thao tác quản trị. Client không có quyền vẫn có thể tự thêm header đó. Ngay cả khi gateway xác thực access token, việc giữ nguyên header quyền từ client vẫn có thể làm hỏng phân quyền.

### 3.3. Nhầm nguồn danh tính giữa các proxy

Hệ thống nhiều lớp CDN → ingress → gateway → service có thể sử dụng cùng tên header. Nếu mỗi lớp **append**, **preserve** hoặc diễn giải header khác nhau, backend có thể chọn nhầm giá trị client đã gắn vào trước đó. Header trùng tên, khác chữ hoa/thường, nhiều giá trị hoặc cách xử lý dấu gạch dưới là các trường hợp phải kiểm thử theo stack thực tế.

### 3.4. Bypass gateway và lạm dụng mạng nội bộ

Một dịch vụ vốn chỉ tin **X-Verified-Subject** từ gateway được mở cổng trực tiếp qua Ingress khác. Kẻ tấn công gọi thẳng dịch vụ và gửi header này, khiến chính sách ở gateway bị bỏ qua. Việc đặt backend trong VPC, subnet riêng hoặc Kubernetes cluster là một lớp kiểm soát hữu ích nhưng không tự chứng minh danh tính thành phần gửi.

## 4. Luồng xử lý an toàn tại gateway

Gateway cần có quy trình rõ ràng, theo đúng thứ tự:

1. **Nhận request và chuẩn hóa header:** chặn request header lỗi, tên header không được hỗ trợ hoặc các dạng mơ hồ có thể gây khác biệt cách hiểu giữa gateway/backend.
2. **Loại bỏ dữ liệu danh tính nội bộ do client cung cấp:** xóa tất cả header nội bộ mà hệ thống định dùng làm principal/quyền, kể cả trường hợp nhiều giá trị. Duy trì danh sách header cho từng ứng dụng, không chỉ một tên phổ biến.
3. **Lấy credential hợp lệ:** ví dụ access token từ **Authorization: Bearer**; giới hạn nơi chấp nhận credential và xử lý trường hợp thiếu/trùng/không đúng định dạng.
4. **Xác thực token:** kiểm tra chữ ký hoặc introspection, issuer, audience, thời gian và các chính sách có liên quan.
5. **Tạo security principal từ kết quả đã xác thực:** lấy định danh người dùng hoặc client, scopes, tenant và các claim đã được cho phép; không lấy từ header identity trước đó.
6. **Áp dụng chính sách tại gateway:** yêu cầu scope, route, quota và các điều kiện thích hợp. Backend vẫn cần kiểm tra quyền trên đối tượng/tài nguyên.
7. **Chuyển tiếp an toàn:** hoặc giữ access token để backend tự xác thực, hoặc tạo header ngữ cảnh mới chỉ qua đường truyền có xác thực gateway; ghi log có chọn lọc, tránh lộ token.

Pseudocode minh họa:

~~~text
handle(request):
    remove_all_inbound_values(request, [
        "X-User-Id",
        "X-Role",
        "X-Authenticated-User",
        "X-Forwarded-User",
        "X-Verified-Subject",
        "X-Verified-Scope"
    ])

    bearer = parse_single_bearer_token(request.Authorization)
    if bearer is missing or invalid_format:
        return 401

    claims = validate_access_token(
        bearer,
        trusted_issuer,
        expected_api_audience,
        allowed_algorithms,
        current_time
    )
    if claims invalid:
        return 401

    if not permitted(claims.scopes, request.method, request.path):
        return 403

    // Chỉ gateway được tạo ngữ cảnh này sau xác thực.
    request["X-Verified-Subject"] = claims.sub
    request["X-Verified-Scope"] = normalize(claims.scopes)

    forward_to_backend_over_authenticated_channel(request)
~~~

Pseudocode mô tả một phương án triển khai; **không đủ** nếu backend tin header từ mọi nguồn. Backend cần xác thực kết nối/danh tính workload của gateway (ví dụ mTLS) và không chấp nhận request đến từ bên ngoài qua đường khác. Nếu backend tự xác thực access token, có thể bỏ các header identity nội bộ và lấy principal trực tiếp từ token.

### Kiểm tra access token cụ thể

Với **JWT access token**, tối thiểu cần:

- Chỉ chấp nhận thuật toán đã cho phép và khóa xác thực gắn với issuer tin cậy; không lấy thuật toán tùy ý từ token để quyết định mức tin cậy.
- Xác minh chữ ký, **iss**, **aud**, **exp**, **nbf** (nếu có), thời gian lệch cho phép ở mức hợp lý và các yêu cầu ứng dụng.
- Hiểu **sub** là chủ thể được issuer định danh; không mặc định nó là một người dùng cuối nếu token cấp cho service/client.
- Kiểm tra **scope/scp**, loại principal và tenant khi API có yêu cầu; không suy quyền quản trị chỉ từ tên người dùng.
- Lưu ý JWT đã ký có thể còn hợp lệ đến khi hết hạn; khi cần thu hồi sớm, sử dụng chiến lược phù hợp như token ngắn hạn, kiểm tra trạng thái hoặc denylist có kiểm soát.

Với **opaque access token**, resource server/gateway không thể tự suy claims từ chuỗi token; phải gọi **introspection** qua kênh bảo mật, xác nhận token đang active cùng issuer/resource/scope và áp dụng chính sách tương ứng.

**ID token của OIDC không thay thế access token cho API.** ID token chủ yếu biểu thị kết quả xác thực tại client OIDC; API cần access token dành cho resource đó, với audience và quyền phù hợp. **Refresh token** dùng xin token mới ở endpoint được thiết kế cho việc này; không dùng như bearer credential gọi API nghiệp vụ.

## 5. Hai chiến lược truyền danh tính đến backend

| Tiêu chí | Backend tự xác thực access token | Gateway tạo trusted identity context |
|---|---|---|
| Nguồn principal | Backend kiểm tra JWT hoặc introspection | Gateway kiểm tra token và tạo ngữ cảnh |
| Điểm mạnh | Backend tự thực thi kiểm tra token, giảm phụ thuộc vào header identity | Hợp với dịch vụ cũ, tập trung một phần tích hợp IdP |
| Yêu cầu an toàn | Mỗi backend xác minh đúng issuer, audience, scope và quyền nghiệp vụ | Gateway phải xóa header client, bảo vệ hop bằng mTLS/workload identity, backend chỉ tin gateway |
| Rủi ro cần chú ý | Cấu hình validator không đồng nhất giữa dịch vụ | Bypass gateway, spoof header nội bộ, thay đổi cấu hình proxy |
| Phù hợp | Dịch vụ hiện đại có OAuth2 Resource Server | Hệ thống đã thống nhất hợp đồng identity context và quản lý ranh giới chặt chẽ |

Cả hai đều yêu cầu **authorization tại nơi sử dụng dữ liệu**. Gateway có thể kiểm tra người gọi được phép truy cập tuyến **GET /orders/**; Orders Service vẫn phải xác minh đơn hàng cụ thể thuộc người gọi hoặc quyền được ủy nhiệm.

Nếu gateway truyền ngữ cảnh thay vì token, nên dùng một hợp đồng rõ ràng gồm các trường được phép, phiên bản, issuer/origin và phạm vi sử dụng. Với nhiều hop hoặc miền tin cậy khác nhau, có thể dùng **signed identity assertion** ngắn hạn, có audience riêng cho backend và bảo vệ replay; chữ ký chỉ có ý nghĩa nếu backend xác minh đầy đủ. Tránh đưa access token hoặc JWT không cần thiết vào log, URL và header tùy biến.

## 6. Ví dụ cấu hình và code Java/Spring Security

### 6.1. Tránh dùng header identity làm principal

Cách viết an toàn hơn với Spring Boot sử dụng **OAuth2 Resource Server JWT** là lấy danh tính từ **Jwt** đã được Spring Security xác thực:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/demo
          audiences: orders-api
~~~

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@Configuration
class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/orders/me")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }
}

@RestController
class MeController {
    @GetMapping("/orders/me")
    Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }
}
~~~

Điều kiện của ví dụ: dự án có dependency **spring-boot-starter-oauth2-resource-server**, IdP phát JWT access token có issuer/audience phù hợp và quyền **orders.read** được chuyển thành authority **SCOPE_orders.read**. Đây là endpoint minh họa để thấy nguồn subject. Một endpoint trả đơn hàng thật còn phải giới hạn dữ liệu theo subject/tenant đã xác thực và chính sách nghiệp vụ.

Kể cả khi request chứa **X-User-Id: administrator**, controller vẫn đọc **jwt.getSubject()** từ access token hợp lệ. Nếu dùng opaque token, cấu hình resource server introspection và lấy principal từ **Authentication** đã xác thực thay vì giả định kiểu **Jwt**.

### 6.2. Vệ sinh header tại reverse proxy

Ví dụ NGINX dưới đây minh họa **xóa** các header danh tính inbound trên đường proxy; dấu nháy kép rỗng khiến NGINX không chuyển tiếp header tương ứng:

~~~nginx
location /api/ {
    proxy_set_header X-User-Id "";
    proxy_set_header X-Role "";
    proxy_set_header X-Authenticated-User "";
    proxy_set_header X-Forwarded-User "";
    proxy_set_header X-Verified-Subject "";
    proxy_set_header X-Verified-Scope "";

    proxy_pass http://orders_backend;
}
~~~

Đây **chỉ là bước vệ sinh header**, không tự thực hiện JWT verification, introspection, authorization hoặc bảo vệ kết nối đến backend. Trong hệ thống thực tế, phải cấu hình thêm bộ xác thực phù hợp tại gateway, rule truy cập trực tiếp backend, TLS/mTLS, danh sách header toàn diện và test theo phiên bản proxy sử dụng. Nếu gateway phải phát hành header ngữ cảnh, thao tác tạo header phải xảy ra **sau xác thực** và không được giữ giá trị client gửi trước đó.

## 7. Kiểm thử bảo mật cần có

Dưới đây là các ca kiểm thử có thể tự động hóa ở gateway và backend. Giả định **GET /api/orders/me** yêu cầu access token hợp lệ với scope **orders.read**, còn **POST /api/admin/reconcile** chỉ dành cho principal có quyền quản trị theo chính sách.

| Ca thử | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Không có token, giả danh user | **X-User-Id: admin**, không gửi Authorization | **401 Unauthorized**, không trả dữ liệu |
| Không có token, giả quyền | **X-Role: ADMIN**, không gửi Authorization | **401 Unauthorized** |
| Token không hợp lệ/hết hạn | Bearer giả, JWT sai chữ ký hoặc hết hạn | **401 Unauthorized** |
| Token hợp lệ, nhưng sai audience | Access token dành cho API khác | **401 Unauthorized** |
| Token hợp lệ, thiếu scope | User token không có quyền admin + **X-Role: ADMIN** | **403 Forbidden**, không nâng quyền |
| Token user A, giả header user B | Bearer A + **X-User-Id: B** | Dữ liệu/subject vẫn thuộc A; chính sách đối tượng được kiểm tra |
| Dùng ID token gọi API | ID token OIDC thay cho access token đúng audience | Bị từ chối theo policy của resource server |
| Gọi thẳng backend | Bỏ qua gateway, gửi **X-Verified-Subject: admin** | Kết nối bị chặn hoặc bị từ chối vì không có danh tính gateway hợp lệ |
| Header nhiều giá trị/tên biến thể | Gửi trùng header, thay chữ hoa/thường hoặc encoding lạ | Không chọn nhầm giá trị từ client |
| Gateway chuyển tiếp | Request hợp lệ qua đường chính thức | Backend nhận principal đúng từ token đã kiểm tra hoặc từ kênh gateway tin cậy |

Ví dụ gọi API để phát hiện lỗi tin header:

~~~bash
# Không có access token: việc giả danh bằng header không được có hiệu lực.
curl -i "https://api.example.com/api/orders/me" \
  -H "X-User-Id: admin" \
  -H "X-Role: ADMIN"

# Có access token người dùng thường: header không được nâng quyền.
curl -i -X POST "https://api.example.com/api/admin/reconcile" \
  -H "Authorization: Bearer <regular-user-access-token>" \
  -H "X-Role: ADMIN" \
  -H "X-Verified-Subject: admin"
~~~

Lưu ý: **401** nghĩa là chưa có xác thực hợp lệ; **403** nghĩa là đã xác thực nhưng không đủ quyền. HTTP status thực tế phụ thuộc policy và quy ước API, nhưng tuyệt đối không được thành công chỉ nhờ header identity giả. Với ca bypass, phải thử bằng đường mạng độc lập đến backend chứ không chỉ gọi lại URL gateway.

### Những câu hỏi khi rà soát hệ thống

- Những header nào đang làm thay đổi **Principal**, user ID, tenant hoặc role trong backend? Ai là bên đầu tiên được phép tạo chúng?
- Gateway có **xóa toàn bộ giá trị inbound** của các header đó trước khi thêm giá trị đã xác minh không?
- Gateway xác thực đúng **access token**, **iss**, **aud**, thời hạn, scope, và chống chấp nhận sai loại token không?
- Backend có thể bị gọi trực tiếp qua Ingress, NodePort, cổng quản trị, service mesh hoặc route khác không?
- Backend có nhận biết được **danh tính workload của gateway** trước khi tin identity context không?
- Có test cho nhiều header trùng tên, case-insensitive names, nhiều proxy hop và tenant crossing không?
- Log/trace có ghi **Authorization**, refresh token, cookie phiên hoặc các dữ liệu nhạy cảm không?

## 8. Ghi nhớ

**Header identity từ client là dữ liệu không tin cậy.** Danh tính và quyền phải đến từ một credential được xác thực hoặc ngữ cảnh do thành phần đáng tin tạo ra sau xác thực. Gateway cần xóa header có thể giả mạo, kiểm tra access token phù hợp với API, truyền ngữ cảnh qua kênh được bảo vệ; backend phải xác thực nguồn, chống bypass và phân quyền đến từng tài nguyên.

Với hệ thống OAuth 2.0/OIDC, hãy luôn phân biệt **access token**, **ID token**, **refresh token**, **JWT** và **opaque token**. Cách token được biểu diễn không thay đổi nguyên tắc cốt lõi: *client không được tự quyết định danh tính mà server sẽ tin*.
