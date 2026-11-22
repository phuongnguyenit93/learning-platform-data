# Resource Server khác OAuth2 Client và Authorization Server ở trách nhiệm nào?

Trong một hệ thống dùng OAuth 2.0, **Resource Server**, **OAuth2 Client** và **Authorization Server** là ba *vai trò* có trách nhiệm khác nhau. Phân biệt đúng ba vai trò giúp trả lời những câu hỏi thiết kế quan trọng: ai cho người dùng đăng nhập, ai cấp access token, ai mang token đi gọi API và ai quyết định một yêu cầu API có được truy cập dữ liệu hay không.

Trong Spring Security, cấu hình `oauth2ResourceServer()`, `oauth2Login()/oauth2Client()` và một Authorization Server giải quyết các phần khác nhau của luồng này. Một ứng dụng có thể đảm nhiệm nhiều vai trò, nhưng không vì vậy mà trách nhiệm của chúng trở thành một.

## 1. Nhìn tổng thể ba vai trò

Giả sử hệ thống bán hàng có:

- **Shop Web**: ứng dụng mà người dùng sử dụng để xem đơn hàng.
- **Identity Server**: nơi người dùng xác thực và ứng dụng xin quyền truy cập.
- **Orders API**: dịch vụ chứa dữ liệu đơn hàng và cung cấp endpoint `GET /api/orders/42`.

Trong kịch bản này:

| Vai trò OAuth 2.0 | Thành phần ví dụ | Trách nhiệm cốt lõi |
| --- | --- | --- |
| **OAuth2 Client** | Shop Web | Yêu cầu quyền truy cập, nhận/quản lý access token theo grant phù hợp và **gửi token** khi gọi API. |
| **Authorization Server (AS)** | Identity Server | Xác thực chủ thể khi luồng yêu cầu; xử lý ủy quyền và **phát hành token** cho client. |
| **Resource Server (RS)** | Orders API | **Bảo vệ tài nguyên/API**: tiếp nhận access token, xác minh tính hợp lệ và kiểm tra quyền trước khi trả dữ liệu. |

**Resource Owner** (thường là người dùng sở hữu dữ liệu) là một vai trò khác trong mô hình OAuth. Người dùng có thể tương tác với Client và Authorization Server, nhưng bản thân người dùng không phải một trong ba loại server/client đang so sánh.

Một luồng Authorization Code với PKCE điển hình:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as OAuth2 Client (Shop Web)
    participant A as Authorization Server
    participant R as Resource Server (Orders API)

    U->>C: Mở ứng dụng / yêu cầu xem đơn hàng
    C-->>U: Chuyển hướng đến Authorization Server
    U->>A: Đăng nhập, đồng ý cấp quyền khi cần
    A-->>C: Trả authorization code qua redirect
    C->>A: Đổi code lấy token (với PKCE)
    A-->>C: Access token (+ ID token nếu dùng OIDC)
    C->>R: GET /api/orders/42 + Bearer access_token
    R->>R: Xác minh token, scope và quyền trên đơn hàng
    R-->>C: Dữ liệu hoặc lỗi 401/403
    C-->>U: Hiển thị kết quả
~~~

Sơ đồ trên mô tả một trường hợp có người dùng. Với luồng `client_credentials` giữa các dịch vụ, Client có thể xin token trực tiếp từ Authorization Server mà không có bước đăng nhập người dùng; Resource Server vẫn thực hiện trách nhiệm kiểm tra token và bảo vệ API.

## 2. Resource Server: nhận token để bảo vệ tài nguyên

**Resource Server là API/dịch vụ sở hữu tài nguyên được bảo vệ**, ví dụ đơn hàng, hồ sơ khách hàng hoặc tài liệu nội bộ. Một request đến Resource Server thường chứa:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJ...
~~~

Ở mức khái niệm, Resource Server cần:

1. **Lấy access token** từ request, thông dụng nhất là header `Authorization: Bearer ...`.
2. **Xác minh token** theo định dạng/cơ chế hệ thống chọn: chữ ký, issuer, thời hạn, audience đối với JWT; hoặc hỏi Authorization Server qua introspection đối với opaque token.
3. **Chuyển thông tin xác thực thành principal/authorities**, chẳng hạn scope `orders.read` trở thành authority `SCOPE_orders.read` theo cấu hình mặc định của Spring Security với JWT.
4. **Kiểm tra quyền ở API và dữ liệu cụ thể**: caller có được đọc đơn hàng không, đơn hàng đó có thuộc tenant/người dùng được phép không.
5. **Trả tài nguyên hoặc từ chối truy cập**. Thông thường thiếu token hoặc token không hợp lệ dẫn đến HTTP 401; token hợp lệ nhưng thiếu quyền dẫn đến HTTP 403.

Resource Server **không có trách nhiệm cấp access token** hay điều hướng người dùng tới màn hình đăng nhập. Nó có thể biết danh tính caller qua các claim đã được xác minh, nhưng điều đó khác với việc tự thực hiện đăng nhập, lấy mật khẩu hay phát hành phiên đăng nhập cho ứng dụng phía người dùng.

### Resource Server cần tin vào điều gì?

Khi dùng JWT, Resource Server cần tin vào **khóa/issuer được cấu hình**, chứ không đơn thuần tin vào nội dung JSON bên trong token. Bất kỳ ai cũng có thể giải mã phần payload của JWT; việc đọc được claim không chứng minh token do đúng Authorization Server phát hành.

Các kiểm tra thường gặp:

| Kiểm tra | Ý nghĩa |
| --- | --- |
| Chữ ký và thuật toán | JWT được ký hợp lệ bởi khóa tin cậy, không chấp nhận thuật toán ngoài chính sách. |
| `iss` (issuer) | Token đến từ Authorization Server được cho phép. |
| `exp`, `nbf` | Token chưa hết hạn và đã có hiệu lực; có thể tính đến độ lệch đồng hồ hợp lý. |
| `aud` (audience) | Token được cấp để dùng cho API này, tránh dùng nhầm token của API khác. |
| Scope/authority | Token cho phép loại hành động mà endpoint yêu cầu, ví dụ `orders.read`. |
| Quyền nghiệp vụ | Caller chỉ được truy cập đơn hàng hoặc tenant mà họ có quyền, kể cả khi có scope hợp lệ. |

Việc xác minh JWT là điều kiện cần để tin vào các claim, nhưng **JWT hợp lệ không tự động cho phép truy cập mọi tài nguyên**. Kiểm tra scope và quyền đối tượng là phần riêng của authorization trên Resource Server.

### JWT và opaque token: trách nhiệm không đổi, cách xác minh khác nhau

| JWT access token | Opaque access token |
| --- | --- |
| Có thể chứa claim đọc được; Resource Server xác minh chữ ký bằng khóa công khai/JWK tin cậy. | Là chuỗi tham chiếu; Resource Server thường gọi **introspection endpoint** để lấy trạng thái/thuộc tính token. |
| Có thể xác minh cục bộ sau khi lấy/cập nhật khóa phù hợp. | Phụ thuộc vào khả năng truy cập introspection (hoặc cơ chế cache nếu hệ thống áp dụng). |
| Việc thu hồi trước hạn không được phản ánh tự động chỉ nhờ kiểm tra chữ ký và `exp`. | Introspection có thể trả trạng thái không còn active theo chính sách của Authorization Server. |
| Vẫn phải kiểm tra issuer, thời hạn, audience và quyền theo thiết kế. | Vẫn phải kiểm tra tính active, client/subject/scope và phạm vi sử dụng theo thiết kế. |

**Token là JWT hay opaque không quyết định vai trò của dịch vụ**: nếu dịch vụ tiếp nhận access token để bảo vệ API thì nó đang đóng vai Resource Server.

## 3. OAuth2 Client: xin và sử dụng quyền truy cập

**OAuth2 Client là ứng dụng yêu cầu quyền để gọi một tài nguyên được bảo vệ.** Ví dụ Shop Web muốn đọc đơn hàng thay mặt người dùng; nó sử dụng một grant được Authorization Server hỗ trợ để nhận access token, sau đó gửi token tới Orders API.

Tùy kiểu ứng dụng và luồng, OAuth2 Client có thể:

- Chuyển người dùng đến Authorization Server để xác thực và cấp quyền, xử lý redirect và authorization code, sử dụng PKCE khi thích hợp.
- Trao đổi authorization code hoặc dùng `client_credentials` để nhận access token.
- Giữ thông tin token an toàn, gửi access token trong request đến Resource Server và xin token mới/refresh khi được phép.
- Kết nối access token với lời gọi HTTP đầu ra, chẳng hạn khi backend Shop Web gọi Orders API bằng `WebClient`.
- Nếu sử dụng **OpenID Connect (OIDC)** để đăng nhập, tiếp nhận và xác minh **ID token** theo quy tắc OIDC, rồi thiết lập trạng thái đăng nhập của ứng dụng.

Điều quan trọng là Client **không quyết định token có hợp lệ đối với Orders API hay không**. Client có thể gửi request với token, nhưng Resource Server phải tự kiểm tra. Authorization Server là thành phần phát hành token, chứ Client không tự tạo ra access token đáng tin cậy.

### OAuth2 Client và đăng nhập OIDC không phải một khái niệm

**OAuth 2.0** chủ yếu giải quyết *ủy quyền truy cập tài nguyên*; **OpenID Connect** bổ sung lớp *xác thực danh tính* trên nền OAuth 2.0. Vì thế:

- **Access token** dành cho việc gọi Resource Server; đối tượng đích và quyền được xác định theo thiết kế của API.
- **ID token** dành cho **OIDC Client** để biết kết quả xác thực người dùng; audience của nó thường là `client_id`.
- Một API không nên dùng ID token thay access token chỉ vì ID token cũng là JWT và chứa `sub` hoặc tên người dùng.
- Một OAuth2 Client có thể hoạt động không cần OIDC, chẳng hạn service gọi service bằng `client_credentials`.

Trong Spring Security, `oauth2Login()` tập trung vào đăng nhập tương tác qua OAuth 2.0/OIDC và thông thường thiết lập principal/phiên cho ứng dụng web. `oauth2Client()` cung cấp hỗ trợ quản lý authorized client/token cho các lời gọi đến dịch vụ khác. Chúng liên quan nhau nhưng giải quyết các nhu cầu khác với `oauth2ResourceServer()`.

## 4. Authorization Server: cấp token dựa trên xác thực và chính sách

**Authorization Server** là nơi Client đề nghị nhận quyền truy cập và nơi token được phát hành. Tùy loại grant và chính sách, Authorization Server có thể:

- Nhận diện Client, kiểm tra `client_id`, phương thức xác thực Client và redirect URI theo cấu hình.
- Xác thực người dùng khi cần; xử lý đăng nhập, yêu cầu consent khi thích hợp.
- Tiếp nhận/kiểm tra authorization request, authorization code, PKCE và các grant được hỗ trợ.
- Đánh giá phạm vi được cấp rồi **phát hành access token**; có thể phát hành refresh token; nếu hỗ trợ OIDC, có thể phát hành **ID token**.
- Công bố metadata, khóa công khai (JWKS) và hỗ trợ introspection/revocation tùy khả năng triển khai.
- Quản lý vòng đời token và chính sách liên quan đến Client, người dùng, scope, audience.

Authorization Server thường **không sở hữu nghiệp vụ** “đơn hàng số 42 có được hiển thị hay không”. Nó có thể cấp scope `orders.read`, nhưng Orders API vẫn phải kiểm tra quyền truy cập vào đơn hàng cụ thể.

Authorization Server cũng không đồng nghĩa với “đăng nhập”. Trong `client_credentials`, nó có thể cấp access token sau khi xác thực **Client**, hoàn toàn không có người dùng cuối đăng nhập.

**Spring Authorization Server** hoặc một Identity Provider chuyên dụng có thể đảm nhiệm vai trò này. Chỉ thêm cấu hình Resource Server vào ứng dụng Spring Boot **không biến nó thành Authorization Server** và không tự tạo endpoint `/oauth2/token` để phát token.

## 5. Bảng đối chiếu: ai chịu trách nhiệm việc gì?

| Việc cần thực hiện | OAuth2 Client | Authorization Server | Resource Server |
| --- | --- | --- | --- |
| Khởi tạo luồng xin quyền/token | **Có** | Tiếp nhận, xử lý | Không |
| Xác thực người dùng trong luồng đăng nhập | Dẫn hướng/tiếp nhận kết quả | **Có**, trực tiếp hoặc qua cơ chế xác thực được tích hợp | Không phải chức năng chính |
| Phát hành, ký access token | Không | **Có** | Không |
| Gửi access token khi gọi API | **Có** | Không phải vai trò chính | **Nhận** token |
| Xác minh access token trước khi trả API | Không thay API quyết định | Cung cấp khóa hoặc introspection theo thiết kế | **Có** |
| Thực thi scope của endpoint | Có thể xin scope | Cấp scope được phép | **Có** |
| Kiểm tra quyền vào từng bản ghi nghiệp vụ | Không thay API quyết định | Thường không | **Có** |
| Quản lý token khi gọi API khác | **Có** | Phát/refresh theo chính sách | Thường không |
| Trả dữ liệu từ endpoint nghiệp vụ | Thường hiển thị hoặc tiêu thụ dữ liệu | Thường không | **Có** |
| Trả ID token trong OIDC | Nhận, xác minh cho login | **Phát hành** | Không dùng làm access token |

“Có”, “không” trong bảng thể hiện **trách nhiệm của vai trò**, không phải ranh giới bắt buộc về số tiến trình triển khai. Một hệ thống có thể đặt nhiều vai trò trong cùng một ứng dụng, hoặc một ứng dụng vừa là Resource Server cho API vào, vừa là OAuth2 Client khi gọi API ra.

## 6. Ví dụ triển khai Resource Server với Spring Security

Ví dụ Orders API sử dụng **JWT access token** phát hành bởi một Authorization Server đã có sẵn. Với Spring Boot, thêm dependency Resource Server:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Cấu hình issuer của bên phát hành:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/shop
~~~

Khi dùng `issuer-uri`, Spring Security có thể sử dụng metadata của issuer để tìm khóa công khai phù hợp và kiểm tra JWT theo cấu hình mặc định, bao gồm chữ ký, thời hạn và issuer. Việc kiểm tra **audience mà API mong đợi** cần được cấu hình rõ theo yêu cầu bảo mật của hệ thống; không nên mặc định cho rằng mọi token cùng issuer đều dành cho Orders API.

Ví dụ yêu cầu scope tương ứng cho các thao tác đọc/ghi:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đoạn cấu hình minh họa **API chỉ nhận Bearer token**, nên ví dụ tắt CSRF và sử dụng session stateless. Nếu cùng ứng dụng còn phục vụ website đăng nhập bằng cookie, cần xem xét CSRF, session và phạm vi `SecurityFilterChain` riêng cho luồng đó; không nên áp dụng máy móc cấu hình API cho toàn bộ website.

Đối với JWT có claim `scope` hoặc `scp` phù hợp, Spring Security mặc định ánh xạ scope thành authority có tiền tố `SCOPE_`. Ví dụ scope `orders.read` tương ứng `SCOPE_orders.read`. Nếu Authorization Server dùng claim hoặc quy ước khác, ứng dụng cần cấu hình cách ánh xạ authorities cho phù hợp.

Lời gọi thử nghiệm:

~~~bash
curl -i https://orders.example.test/api/orders/42 \
  -H "Authorization: Bearer $ACCESS_TOKEN"
~~~

Với API này, các trường hợp điển hình là:

| Request | Kết quả điển hình |
| --- | --- |
| Không có token hoặc token hết hạn/chữ ký không hợp lệ | **401 Unauthorized**; Resource Server không xác thực được caller. |
| Token hợp lệ nhưng thiếu scope `orders.read` | **403 Forbidden**; caller chưa được cấp quyền gọi endpoint. |
| Token hợp lệ, có `orders.read`, nhưng đơn hàng 42 thuộc người khác | **403 Forbidden** hoặc **404 Not Found** theo chính sách không tiết lộ tài nguyên. |
| Token hợp lệ, đủ scope và đủ quyền nghiệp vụ | **200 OK** kèm dữ liệu nếu đơn hàng tồn tại. |

Scope ở filter chain chỉ là **lớp kiểm tra đầu tiên**. Ví dụ `hasAuthority("SCOPE_orders.read")` không tự kiểm tra ownership của `orderId = 42`; phải có logic nghiệp vụ, phương thức được bảo vệ hoặc chính sách phân quyền đối tượng bổ sung.

### Nếu access token là opaque token

Ứng dụng vẫn là Resource Server nhưng đổi sang cơ chế introspection, ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
~~~

Và cấu hình `oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(Customizer.withDefaults()))`. Endpoint và phương thức xác thực introspection phải phù hợp Authorization Server thực tế. Đây là thông tin xác minh token dành cho API, **không phải credentials để Orders API tự phát hành token**.

## 7. Ví dụ phía Client và phía Authorization Server

Ở phía Shop Web, các dependency/cấu hình có mục đích khác:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/", "/assets/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .oauth2Client(Customizer.withDefaults())
        .build();
}
~~~

Đây là **minh họa phần bảo mật của ứng dụng web**; để chạy thực tế cần cấu hình `ClientRegistration` (issuer, `client-id`, grant/redirect URI, secret nếu là confidential client) và cơ chế dùng authorized client để gắn access token vào request gửi tới Orders API. `oauth2Login()` không khiến Orders API tự động cho phép truy cập; API vẫn cần Resource Server của riêng mình.

Ở phía Authorization Server, hệ thống Identity Server phải có cấu hình đăng ký Client, grant và scopes, khóa ký/định dạng token cùng các endpoint cần thiết. Có thể triển khai bằng **Spring Authorization Server** hoặc Identity Provider khác. Dù dùng sản phẩm nào, hợp đồng tích hợp cơ bản là:

- Client biết **đăng ký Client, authorization/token endpoints, issuer** và cách xin token.
- Resource Server biết **issuer/khóa công khai hoặc introspection**, quy tắc audience và cách diễn giải scope/claims.
- Authorization Server biết **Client nào được xin quyền gì** và cách phát token được các bên còn lại tin cậy.

## 8. Một ứng dụng có thể vừa là Client vừa là Resource Server

Ví dụ **Backend A**:

1. Nhận `GET /api/profile` kèm access token từ ứng dụng di động. Đối với request đầu vào, Backend A đóng vai **Resource Server**.
2. Backend A cần truy vấn **Reporting API** và dùng `client_credentials` để nhận một access token dành cho Reporting API. Đối với request đi ra, Backend A đóng vai **OAuth2 Client**.
3. Identity Server cấp token cho Client của Backend A và công bố thông tin xác minh cho Reporting API. Nó đóng vai **Authorization Server**.

Điều này là hợp lệ. Tuy nhiên, token của request đầu vào **không tự động được phép chuyển tiếp** tới Reporting API: phải xem xét audience, scope, cách đại diện chủ thể và cơ chế delegation/token exchange nếu nghiệp vụ cần hành động thay mặt người dùng. Mỗi API xác minh token dành riêng cho mình.

Tương tự, một deployment có thể vừa vận hành endpoint phát hành token, vừa bảo vệ API quản trị của chính nó. Khi đó thành phần đó thực hiện **hai vai trò** khác nhau; không nên suy ra mọi endpoint trên Authorization Server đều tự nhiên là Resource Server.

## 9. Những nhầm lẫn thường gặp

**“Resource Server xử lý đăng nhập OAuth2.”** Với Bearer token, Resource Server thông thường chỉ xác minh token nhận được và thiết lập `Authentication` cho request API. Chuyển hướng người dùng đăng nhập và hoàn tất OIDC login là phần của Client và Authorization Server.

**“Resource Server tự cấp JWT nên không cần Authorization Server.”** Một API hoàn toàn có thể tự có cơ chế xác thực và cấp token riêng, nhưng khi nó phát token thì nó đang đảm nhiệm thêm trách nhiệm *phát hành token*. Trong kiến trúc OAuth 2.0, đó không còn đơn thuần là vai trò Resource Server.

**“Đã có JWT đúng chữ ký là được đọc dữ liệu.”** JWT đúng chữ ký còn phải phù hợp issuer, thời gian, audience và các ràng buộc cần thiết. Sau bước xác thực, Resource Server phải kiểm tra authority/scope và quyền nghiệp vụ trên dữ liệu.

**“ID token và access token đều là JWT nên dùng thay nhau được.”** ID token chứng minh kết quả xác thực cho OIDC Client; access token là credential để gọi Resource Server. Hai token có đối tượng nhận và mục đích khác nhau.

**“Chỉ có người dùng mới dùng OAuth2.”** Với `client_credentials`, service cũng có thể là Client. Resource Server kiểm tra access token đại diện cho Client và chỉ cấp đúng quyền được phép.

**“Resource Server có scope thì chắc chắn được lấy mọi bản ghi.”** Scope thường cho biết quyền thao tác ở mức API. Quyền theo user/tenant/owner, trạng thái bản ghi hoặc chính sách tổ chức vẫn cần kiểm tra riêng.

**“Đăng xuất hay thu hồi token ở Authorization Server sẽ khiến mọi JWT vô hiệu ngay lập tức.”** Với JWT xác minh cục bộ, Resource Server có thể tiếp tục chấp nhận token chưa hết hạn nếu không có cơ chế bổ sung về thu hồi token. Cần chọn thời hạn token, introspection hoặc chiến lược thu hồi phù hợp yêu cầu nghiệp vụ.

## 10. Cách nhận diện vai trò khi thiết kế hệ thống

Khi gặp một thành phần trong sơ đồ, hãy hỏi:

1. **Nó xin và gửi access token để truy cập API khác?** → Nó đang là **OAuth2 Client**.
2. **Nó xác thực/ủy quyền và phát hành access token cho Client?** → Nó đang là **Authorization Server**.
3. **Nó nhận access token để quyết định có trả dữ liệu hoặc thực thi nghiệp vụ không?** → Nó đang là **Resource Server**.

Với Spring Security, cách đối chiếu thực hành là:

| Vai trò cần xây | Cơ chế Spring thường dùng | Câu hỏi cấu hình cần trả lời |
| --- | --- | --- |
| Resource Server | `spring-boot-starter-oauth2-resource-server`; `oauth2ResourceServer().jwt()` hoặc `opaqueToken()` | Tin issuer/khóa nào, token dành cho audience nào, kiểm tra authority và quyền dữ liệu ra sao? |
| OAuth2 Client | `spring-boot-starter-oauth2-client`; `oauth2Login()` và/hoặc `oauth2Client()` | Đăng ký Client ở đâu, dùng grant nào, lấy/lưu token và gắn token vào request ra sao? |
| Authorization Server | Spring Authorization Server hoặc Identity Provider | Client nào được phép dùng grant/scope nào, xác thực thế nào, token được phát/ký và công bố ra sao? |

**Điểm phân biệt quyết định:** Authorization Server **cấp** quyền dưới dạng token; OAuth2 Client **xin và mang** token đi sử dụng; Resource Server **kiểm chứng và thực thi** quyền đó khi bảo vệ tài nguyên thực tế. Tách ba câu hỏi này ngay từ đầu sẽ giúp thiết kế đúng ranh giới tin cậy, cấu hình Spring Security đúng chức năng và tránh nhầm lẫn giữa đăng nhập OIDC với việc bảo vệ API bằng OAuth 2.0.
