# Xác thực người dùng và phân biệt OAuth 2.0 với OpenID Connect

> **Chủ đề:** Software Architecture · Microservices · Bảo mật  
> **Trọng tâm:** Xác định ai đang đăng nhập, ai được phép gọi API và vì sao OAuth 2.0 không đồng nghĩa với OpenID Connect (OIDC). Từ đó thiết kế xác thực và phân quyền nhất quán qua API Gateway và nhiều microservice.

## 1. Đặt vấn đề: “Người dùng là ai?” và “Được phép làm gì?” là hai câu hỏi khác nhau

Một hệ thống microservices có thể gồm Account Service, Order Service, Inventory Service và Payment Service. Người dùng đăng nhập một lần ở giao diện web nhưng yêu cầu của họ đi qua nhiều dịch vụ. Một thiết kế bảo mật cần giải quyết ít nhất hai bài toán:

- **Authentication — xác thực danh tính:** Xác định một chủ thể (người dùng hoặc service) là ai và mức độ tin cậy của kết quả xác thực. Ví dụ: Alice đăng nhập qua nhà cung cấp danh tính và ứng dụng nhận bằng chứng đáng tin cậy về danh tính Alice.
- **Authorization — cấp quyền/truy cập:** Quyết định một chủ thể đã được nhận diện có được thực hiện hành động cụ thể trên tài nguyên cụ thể không. Ví dụ: Alice có thể xem đơn hàng của chính mình nhưng không thể xem đơn của Bob, dù cả hai đều đăng nhập hợp lệ.

Hai việc liên quan nhưng không thay thế nhau. **Đã đăng nhập không có nghĩa là được truy cập mọi API.** Có access token hợp lệ cũng không mặc nhiên chứng minh ứng dụng đã xác thực người dùng theo giao thức đăng nhập.

Trong thực tế cần phân biệt thêm:

- **Identity:** Danh tính ổn định mà hệ thống tin tưởng, chẳng hạn bộ đôi **issuer + subject**.
- **Session:** Phiên đăng nhập giữa trình duyệt và ứng dụng, thường được biểu diễn bằng cookie an toàn hoặc cơ chế tương đương.
- **Permission:** Quy tắc được phép làm gì, trên tài nguyên nào và dưới ngữ cảnh nào.
- **Credential/token:** Bằng chứng kỹ thuật dùng trong một bước giao tiếp. Token là thông tin nhạy cảm, không phải “quyền truy cập vô hạn”.

## 2. OAuth 2.0 giải quyết bài toán gì?

**OAuth 2.0 là framework ủy quyền:** cho phép một client được cấp **quyền truy cập có giới hạn** tới một resource server, thông qua authorization server, thay vì client nhận trực tiếp mật khẩu của resource owner.

Ví dụ: một ứng dụng quản lý lịch được cấp quyền đọc lịch của người dùng. Ứng dụng nhận **access token** phù hợp để gọi Calendar API. Quyền này có thể chỉ bao gồm lịch, một số scope và một thời hạn nhất định. OAuth 2.0 thiết kế việc **cấp quyền để gọi tài nguyên**; bản thân OAuth 2.0 không định nghĩa một chuẩn đầy đủ để client xác nhận người dùng vừa đăng nhập là ai.

### Các vai trò chính

| Vai trò | Trách nhiệm | Ví dụ |
|---|---|---|
| **Resource Owner** | Chủ thể có khả năng cho phép truy cập tài nguyên theo mô hình áp dụng | Người dùng sở hữu lịch; trong một số grant không có người dùng tương tác |
| **Client** | Ứng dụng yêu cầu quyền truy cập | Web app, mobile app, backend job |
| **Authorization Server (AS)** | Xác thực/chấp thuận theo chính sách và cấp token | Hệ thống Identity Provider/Authorization Server |
| **Resource Server (RS)** | API bảo vệ dữ liệu và kiểm tra quyền truy cập | Order API, Calendar API |
| **Access Token** | Thông tin biểu diễn quyền truy cập được cấp cho client | Bearer token gửi đến API |

OAuth 2.0 có các cơ chế ủy quyền khác nhau, ví dụ **Authorization Code + PKCE** cho ứng dụng có người dùng tương tác và **Client Credentials** cho giao tiếp máy với máy. Không phải grant nào cũng có người dùng cuối. Vì vậy **có access token không đồng nghĩa với có một người dùng đã đăng nhập**.

OAuth dùng khái niệm **scope** để biểu diễn phạm vi quyền được xin/cấp, ví dụ **orders.read**; cách áp dụng quyền cụ thể còn phụ thuộc resource server và chính sách nghiệp vụ.

## 3. OpenID Connect bổ sung điều gì?

**OpenID Connect (OIDC)** là lớp giao thức danh tính xây trên OAuth 2.0 để client có thể **xác thực người dùng cuối** và nhận thông tin danh tính theo cách chuẩn hóa.

OIDC thêm những khái niệm quan trọng:

- **OpenID Provider (OP):** bên thực hiện xác thực và phát thông tin danh tính; đồng thời hoạt động như một authorization server.
- **Relying Party (RP):** ứng dụng dựa vào kết quả xác thực của OP.
- **ID Token:** token định dạng JWT chứa các claim về sự kiện xác thực và chủ thể, được phát cho client/RP; ví dụ **iss**, **sub**, **aud**, **exp**, **iat**.
- **Scope openid:** dấu hiệu yêu cầu một giao dịch OIDC thay vì chỉ OAuth thông thường; có thể xin thêm **profile**, **email** tùy yêu cầu và sự đồng ý/chính sách.
- **UserInfo Endpoint:** endpoint có thể cung cấp claim bổ sung về người dùng khi được phép; client phải kiểm tra **sub** từ UserInfo khớp với ID Token.
- **Discovery/JWKS:** cơ chế công bố cấu hình nhà cung cấp và public keys để xác minh chữ ký.

Ví dụ ứng dụng quản trị cần biết người dùng đang đăng nhập. Ứng dụng dùng **OIDC Authorization Code Flow**; sau khi xác thực ở OP, RP nhận **ID Token**, xác thực ID Token và tạo phiên đăng nhập riêng. Khi RP cần gọi API, nó dùng **access token** phù hợp cho API đó.

**Kết luận cần nhớ:** **OAuth 2.0 = ủy quyền truy cập tài nguyên**; **OIDC = chuẩn hóa xác thực đăng nhập và danh tính người dùng trên nền OAuth 2.0**. Một ứng dụng dùng OIDC thường cũng dùng các thành phần của OAuth 2.0, nhưng không thể dùng một luồng OAuth bất kỳ để tự kết luận danh tính.

## 4. Bảng so sánh OAuth 2.0 và OpenID Connect

| Tiêu chí | OAuth 2.0 | OpenID Connect |
|---|---|---|
| Câu hỏi chính | Client được phép truy cập tài nguyên nào? | Người dùng đã xác thực là ai, qua OP nào? |
| Mục tiêu | Delegated authorization | Federated authentication/identity |
| Đối tượng sử dụng | Client và Resource Server | Relying Party và OpenID Provider |
| Bằng chứng tiêu biểu | Access token | ID token; access token vẫn dùng cho API |
| Có bắt buộc người dùng tương tác? | Không; Client Credentials là ví dụ | Thường có người dùng cuối được xác thực |
| Token phải là JWT? | Access token có thể opaque hoặc JWT; tùy profile/AS | ID Token là JWT theo OIDC |
| Scope tiêu biểu | orders.read, payments.create | openid, profile, email |
| Cách resource server sử dụng | Xác minh token dành cho API và kiểm tra quyền | Không được tự dùng ID Token làm quyền gọi API |
| Thông tin danh tính chuẩn hóa | Không đủ để định nghĩa đăng nhập | ID Token, UserInfo, các claim và quy tắc xác minh |
| Rủi ro hiểu sai | Coi access token là bằng chứng đăng nhập | Coi ID token là access token cho mọi service |

Một access token đôi khi chứa **sub** và thông tin người dùng. Điều đó **không biến access token thành ID Token**: mục đích, audience, bên nhận và quy tắc xác thực khác nhau.

## 5. Ba loại token thường gặp

### 5.1. ID Token — dành cho client/Relying Party

ID Token giúp RP xác định sự kiện đăng nhập đã được OP xác thực và đối tượng tương ứng. Ví dụ **payload minh họa**, không phải token JWT được ký thật:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-7342",
  "aud": "web-client",
  "exp": 1730003600,
  "iat": 1730000000,
  "nonce": "random-login-nonce",
  "auth_time": 1729999980
}
~~~

- **iss:** nhà phát hành/OP; phải khớp cấu hình tin cậy.
- **sub:** định danh chủ thể tại issuer. Để lưu identity nội bộ, có thể dùng **(iss, sub)**, tránh nhận email làm khóa chính vì email có thể thay đổi.
- **aud:** client được phát token; RP phải kiểm tra có client_id của chính nó.
- **exp/iat:** thời điểm hết hạn/phát hành, kiểm tra trong giới hạn clock skew hợp lý.
- **nonce:** nếu client gửi nonce trong authorization request thì phải kiểm tra nonce nhận lại để chống replay/mix-up theo mô hình áp dụng.
- **auth_time/amr/acr:** thông tin thời điểm/phương thức/mức xác thực nếu có và được OP hỗ trợ; chỉ dựa vào đó sau khi kiểm tra hợp đồng và chính sách.

**ID Token không được gửi như Bearer để truy cập Order API**. Audience của ID Token thường là client, không phải Order API.

### 5.2. Access Token — dành cho Resource Server

Access token biểu diễn quyền truy cập API đã được cấp. Nội dung có thể là **opaque string** cần introspection hoặc **JWT** mà resource server tự xác thực chữ ký và claims theo cấu hình tin cậy.

Ví dụ payload minh họa của một JWT access token:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-7342",
  "aud": ["orders-api"],
  "scope": "orders.read orders.create",
  "exp": 1730001800,
  "iat": 1730000000,
  "client_id": "web-bff"
}
~~~

Các claim chính xác phụ thuộc profile/provider. Không phải access token JWT nào cũng dùng **scope** hoặc **client_id** theo một định dạng cố định; resource server cần cấu hình mapping rõ ràng. API phải xác nhận token **được phát cho chính API đó** và có quyền thích hợp.

Với **Bearer token**, ai nắm được token hợp lệ có thể trình nó trong phạm vi quyền cho phép. Do đó token cần bảo vệ khi truyền/lưu/log; các cơ chế proof-of-possession như mTLS-bound hoặc DPoP có thể giảm rủi ro nếu toàn bộ hệ thống hỗ trợ và cấu hình đúng.

### 5.3. Refresh Token — dùng xin access token mới

Refresh token giúp client xin access token mới mà không bắt người dùng xác thực lại mỗi lần token hết hạn, nếu AS cho phép. Đây là bí mật nhạy cảm, không gửi cho resource server và không mặc định cấp cho mọi loại client. Với public client, cần áp dụng biện pháp bảo vệ như **refresh token rotation** hoặc cơ chế ràng buộc sender theo chính sách/provider; nếu token bị tái sử dụng trái phép có thể cần vô hiệu hóa cả token family.

Phân biệt **thời hạn access token**, **thời hạn refresh token** và **thời hạn session**: hết hạn một token không luôn đồng nghĩa người dùng đã logout khỏi ứng dụng hoặc OP.

## 6. Luồng đăng nhập phổ biến: Authorization Code + PKCE với OIDC

Ví dụ một web app dùng backend/BFF đăng nhập qua OP. Ứng dụng đăng ký **client_id** và một hoặc nhiều **redirect_uri** chính xác. Mỗi phiên bắt đầu đăng nhập tạo **state**, **nonce** và **code_verifier** đủ ngẫu nhiên; tính **code_challenge = BASE64URL(SHA256(code_verifier))**, dùng phương thức **S256**.

~~~text
Browser          Web App / BFF           OpenID Provider
   |                    |                        |
   |--- GET /login ---->|                        |
   |                    |-- sinh state, nonce, PKCE
   |<--- redirect -------|                        |
   |---------------- authorize?response_type=code,
   |                  scope=openid profile,
   |                  client_id, redirect_uri,
   |                  state, nonce,
   |                  code_challenge, method=S256 -->|
   |<----------- Login / Consent tại OP ----------|
   |<--- redirect về callback?code=...&state=... --|
   |--- callback ------>|                        |
   |                    |-- kiểm tra state        |
   |                    |-- POST token: code, code_verifier,
   |                    |   redirect_uri; client auth nếu áp dụng
   |                    |----------------------->|
   |                    |<-- ID Token, access token, ... |
   |                    |-- xác minh ID Token     |
   |                    |-- tạo session riêng     |
   |<--- Set-Cookie: session an toàn -------------|
   |--- GET /orders với session cookie ---------->|
~~~

Trình tự quan trọng:

1. **Bắt đầu login:** RP chuyển browser tới **authorization endpoint** của đúng issuer; yêu cầu scope **openid** để dùng OIDC.
2. **Xác thực tại OP:** OP xác thực người dùng (mật khẩu, passkey, MFA... theo cấu hình) và xử lý consent nếu cần. Ứng dụng không cần tự thu mật khẩu của OP.
3. **Nhận authorization code:** OP redirect về redirect URI đã đăng ký kèm **code** và **state**. App kiểm tra **state** khớp yêu cầu ban đầu trước khi đổi code.
4. **Đổi code lấy token:** backend/client đổi code tại **token endpoint**, kèm **code_verifier** phù hợp. PKCE làm code bị đánh cắp khó bị đổi thành token khi thiếu verifier.
5. **Kiểm tra ID Token:** xác minh chữ ký, issuer, audience, hạn, nonce và điều kiện bổ sung theo giao thức.
6. **Thiết lập phiên:** app thiết lập session an toàn cho browser. Việc dùng session cookie hay token trong browser phụ thuộc kiến trúc; BFF thường giữ token phía server để giảm tiếp xúc trực tiếp của browser với token.

**State và nonce có mục đích khác nhau:** state liên kết response redirect với yêu cầu login và giúp chống CSRF ở callback; nonce liên kết sự kiện xác thực/ID Token với yêu cầu OIDC và chống replay ở mức token. **PKCE** bảo vệ bước đổi authorization code. Không được thay thế một cơ chế bằng cơ chế còn lại.

**Redirect URI** nên được đối chiếu chính xác theo quy tắc đăng ký; tránh wildcard không cần thiết hoặc open redirect có thể làm rò rỉ code. Không truyền access token qua query string hoặc tự lưu token vào URL.

## 7. Kiến trúc microservices: Ai xác thực, ai kiểm tra quyền?

Một kiến trúc thường gặp:

~~~text
                         +----------------------+
                         |  OpenID Provider /   |
                         |  Authorization Server|
                         +-----------+----------+
                                     ^
                                     | OIDC login / OAuth token
                                     |
Browser / Mobile --> Frontend / BFF / Client
                             |
                             | Access token cho API
                             v
                      +-------------+
                      | API Gateway |
                      | routing, TLS |
                      +------+------+
                             |
                    +--------+----------+
                    |                   |
                    v                   v
              +-----------+       +------------+
              | Order API | ----> | Payment API|
              | Resource  |       | Resource   |
              | Server    |       | Server     |
              +-----------+       +------------+
~~~

**OpenID Provider/Authorization Server** là nơi phát token và thực hiện xác thực người dùng theo chính sách danh tính. Nó có thể là một sản phẩm IAM tập trung, nhưng không nhất thiết là service duy nhất quyết định mọi quyền nghiệp vụ.

**Frontend/BFF/client** chủ động bắt đầu login, giữ trạng thái OIDC và xử lý session/tokens phù hợp loại client. Với BFF, browser thường chỉ dùng session cookie trong giao tiếp với BFF.

**API Gateway** có thể kiểm tra sơ bộ Bearer token, rate limiting, tuyến đường, TLS và chính sách coarse-grained. Tuy nhiên gateway không phải biên bảo mật duy nhất: **microservice có tài nguyên phải tự xác minh danh tính gọi vào và thực thi authorization của mình** hoặc nằm trong một kiến trúc kiểm soát tin cậy tương đương được thiết kế và vận hành chặt chẽ. Chỉ tin header **X-User-Id** do client tùy ý gửi là lỗ hổng.

**Resource Server** (Order/Payment) xác minh access token phù hợp audience của API, map authority đúng chuẩn, kiểm tra scope và điều kiện nghiệp vụ như ownership, tenant, trạng thái đơn. Service chỉ được tin identity header từ gateway khi có mTLS/chính sách hạ tầng chặn giả mạo, kiểm soát đường truy cập và bảo đảm nguồn phát hành header.

**Giao tiếp service-to-service** có thể dùng **Client Credentials**, token exchange hoặc on-behalf-of/delegation tùy nhu cầu giữ ngữ cảnh người dùng. Không mặc nhiên gửi ID Token của browser tới mọi service.

## 8. Xác minh token: Điều kiện tối thiểu cho từng nơi nhận

### 8.1. RP xác minh ID Token

Ứng dụng đăng nhập bằng OIDC cần tối thiểu:

1. Xác định **issuer tin cậy** từ cấu hình/Discovery đúng nguồn, không chọn issuer theo một URL tùy ý từ client.
2. Xác minh **chữ ký JWT** với thuật toán được cho phép và khóa public của issuer; sử dụng JWKS với cơ chế làm mới khi quay khóa.
3. Kiểm tra **iss** bằng issuer đã cấu hình.
4. Kiểm tra **aud** bao gồm **client_id** của RP; áp dụng kiểm tra **azp** khi trường hợp yêu cầu và provider/spec áp dụng.
5. Kiểm tra **exp**, **iat**, sai lệch đồng hồ và các điều kiện tuổi xác thực nếu RP có yêu cầu.
6. Đối chiếu **nonce** nếu nonce đã được gửi.
7. Với các flow/hợp đồng áp dụng, kiểm tra thêm các claim cần thiết như **auth_time**, **acr**, **amr**, **at_hash** theo quy tắc của flow và chính sách.

Không được chỉ **Base64 decode** payload rồi tin thông tin trong đó. Decode là đọc dữ liệu, **không xác thực chữ ký hoặc nguồn gốc**. Token nhận từ một issuer bất kỳ không tự trở thành hợp lệ cho client.

### 8.2. API xác minh Access Token

Resource server cần phân biệt hai dạng:

- **JWT access token:** xác minh chữ ký/thuật toán, issuer, token lifetime, **audience đúng cho API**, các điều kiện token type/profile nếu áp dụng, cùng scope/role. Kỹ thuật kiểm tra JWT không cho phép bỏ qua audience chỉ vì chữ ký hợp lệ.
- **Opaque access token:** tra cứu qua **token introspection** hoặc cơ chế đáng tin cậy tương ứng tại AS, kiểm tra token active, resource/audience, phạm vi quyền và cache theo chính sách.

**ID Token có aud = web-client** không được API coi là access token hợp lệ cho aud = orders-api, kể cả khi cùng issuer và có claim **sub**. Phân biệt token type/audience là biện pháp chống **token substitution** và **confused deputy**.

### 8.3. Phản hồi HTTP rõ ràng

- **401 Unauthorized:** thiếu hoặc không chấp nhận được thông tin xác thực cho resource. Với Bearer, API có thể dùng **WWW-Authenticate: Bearer** kèm thông tin lỗi phù hợp và hạn chế tiết lộ.
- **403 Forbidden:** chủ thể đã được xác thực nhưng không được phép thực hiện hành động trong ngữ cảnh yêu cầu.
- Không trả dữ liệu tài nguyên khi chỉ có token đúng chữ ký nhưng sai audience/scope/tenant.

Tùy chính sách bảo vệ thông tin, API có thể che giấu sự tồn tại của tài nguyên bằng 404 cho người không được phép; hành vi này phải nhất quán, không thay thế kiểm tra authorization.

## 9. Spring Boot/Spring Security: API là Resource Server

Giả sử một Order Service dùng Spring Boot 3 / Spring Security 6 và nhận JWT access token của issuer tin cậy. Cấu hình điển hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
~~~

Cần dependency **spring-boot-starter-oauth2-resource-server** và hỗ trợ JWT tương ứng. Cấu hình **issuer-uri** giúp resource server xác định metadata/JWKS và kiểm tra issuer theo Spring Security; ứng dụng thực tế cần **bổ sung audience validation** và mapping quyền phù hợp hợp đồng token.

Ví dụ bảo vệ endpoint:

~~~java
@Configuration
@EnableWebSecurity
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable()) // Chỉ phù hợp API stateless dùng Bearer,
                                         // không dùng cookie tự gửi cho endpoint này.
            .sessionManagement(sm ->
                sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/orders/**")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đây là ví dụ minh họa về cấu hình, không thay thế policy production. **CSRF không nên bị tắt máy móc** đối với ứng dụng sử dụng cookie/session browser hoặc kết hợp cookie với API. Nếu cùng ứng dụng chứa BFF có session cookie, phải thiết kế security chain và CSRF phù hợp từng endpoint.

Spring thường ánh xạ scope JWT thành authority dạng **SCOPE_...**, nhưng claim, delimiter và cách mapping có thể khác provider. Quyền ở đây còn cần xác thực ownership ở tầng nghiệp vụ:

~~~java
@GetMapping("/orders/{id}")
OrderDto getOrder(@PathVariable UUID id, JwtAuthenticationToken auth) {
    String subject = auth.getToken().getSubject();
    Order order = orders.findById(id).orElseThrow(NotFoundException::new);

    if (!order.ownerIdentity().equals(subject)) {
        throw new AccessDeniedException("No access to this order");
    }
    return orderMapper.toDto(order);
}
~~~

Đoạn trên giả định **subject** đã được gắn đúng với owner trong cùng issuer/tenant. Nếu nhiều issuer hoặc tenant, cần so sánh **issuer + subject + tenant**, không dùng riêng **sub** vì hai issuer có thể cùng một giá trị sub. Trong hệ thống thật thường gom quy tắc này vào authorization policy/service để tránh lặp và kiểm soát dữ liệu rò rỉ.

Để kiểm tra **audience**, có thể cấu hình một **OAuth2TokenValidator<Jwt>** có điều kiện **jwt.getAudience().contains("orders-api")**, kết hợp với validator mặc định kiểm tra issuer/expiration; thư viện và API cấu hình cụ thể tùy phiên bản. Không chấp nhận token dành cho một API khác chỉ vì chữ ký từ cùng OP hợp lệ.

## 10. Chọn luồng phù hợp cho từng loại client

| Kịch bản | Cơ chế phù hợp | Điểm cần bảo vệ |
|---|---|---|
| Web app có backend/BFF | **OIDC Authorization Code + PKCE**, session cookie phía browser | Client secret nếu có được giữ ở backend, state/nonce/PKCE, cookie Secure/HttpOnly/SameSite, CSRF |
| SPA thuần trên browser | **OIDC Authorization Code + PKCE** cho public client | Không chứa client secret trong JavaScript; hạn chế lưu token dài hạn, bảo vệ XSS, CORS đúng |
| Native/mobile app | **OIDC Authorization Code + PKCE** qua system browser và redirect phù hợp | Lưu token trong secure storage, bảo vệ deep link/app link, không nhúng secret |
| Backend job gọi API | **OAuth 2.0 Client Credentials** | Xác thực danh tính máy, scope nhỏ, audience đúng; không tự coi là end-user |
| Service B thay mặt user gọi Service C | Token exchange/on-behalf-of nếu AS/hợp đồng hỗ trợ | Delegation được giới hạn, audience C, quyền không tự động leo thang |
| API nội bộ chỉ dùng mTLS | Mutual TLS cho danh tính workload, kết hợp authorization thích hợp | Xác minh service identity, không mặc định đồng nhất với user login |

**Authorization Code + PKCE** là hướng dùng phổ biến cho public client và cũng là biện pháp bảo vệ có ích cho confidential client. Những phương pháp cũ như **Implicit Flow** hoặc trao trực tiếp **username/password cho ứng dụng thứ ba (Resource Owner Password Credentials)** không nên được chọn cho thiết kế mới. OIDC login không yêu cầu ứng dụng tự quản lý mật khẩu của OP.

## 11. Hai luồng khác nhau trong cùng hệ thống

### 11.1. Người dùng đăng nhập và xem đơn hàng

~~~text
1. Alice mở web app, chưa có session.
2. Web app chuyển Alice sang OP dùng OIDC.
3. OP xác thực Alice, trả authorization code về callback.
4. RP đổi code lấy token, xác minh ID Token:
   issuer=https://id.example.com, sub=user-7342, aud=web-client.
5. RP tạo session cho Alice.
6. BFF gọi Order API bằng access token:
   aud=orders-api, scope=orders.read, sub=user-7342.
7. Order API xác minh access token và kiểm tra đơn thuộc Alice.
8. API trả thông tin đơn được phép xem.
~~~

**Bước 4 trả lời “Alice là ai?”**; **bước 6–7 trả lời “Yêu cầu này có được truy cập đơn đó không?”**. Đó là nơi OIDC và OAuth 2.0 phối hợp nhưng đảm nhiệm hai trách nhiệm tách biệt.

### 11.2. Billing Worker tự chạy tác vụ đối soát

~~~text
1. Billing Worker có workload/client identity riêng.
2. Worker xin access token tại AS bằng Client Credentials.
3. AS cấp token cho aud=billing-api, scope=billing.reconcile.
4. Worker gọi Billing API với Bearer token.
5. Billing API xác minh issuer, audience, token lifetime,
   client identity và scope; áp dụng policy nghiệp vụ.
~~~

Ở luồng này **không có phiên đăng nhập người dùng cuối**, không cần ID Token để “xác thực user”, và không nên gán mọi hành động cho một người dùng giả. Audit nên ghi service principal thực thi, job ID và nguồn kích hoạt.

## 12. Token propagation và service-to-service authorization

Khi Order API gọi Payment API, có nhiều lựa chọn; chọn theo trách nhiệm nghiệp vụ:

**A. Giao tiếp bằng danh tính của service.** Order API xin access token Client Credentials có **aud=payment-api** và quyền hạn chế như **payments.reserve**. Payment API nhận diện Order Service là caller. Nếu cần ghi nhận người dùng đã khởi tạo thao tác, truyền một **business actor reference** đã được xác minh qua cơ chế tin cậy và lưu vào audit; không dùng header giả mạo như chứng minh xác thực.

**B. Giao tiếp thay mặt user.** Order API đổi token hoặc nhận delegated token được AS cấp cho **payment-api**, có audience/scope cần thiết và thông tin actor. Không tự chuyển một token aud=orders-api thành token cho Payment API bằng cách gửi y nguyên. Phải có cơ chế delegation được AS và hai service thống nhất.

**C. Yêu cầu không cần gọi đồng bộ.** Một message mô tả giao dịch có actor, correlation ID và quyền/ngữ cảnh tối thiểu cần lưu bền vững. Consumer xác minh nguồn gốc message qua cơ chế transport/workload, kiểm tra policy tại thời điểm xử lý theo hợp đồng; không mặc định dùng lại access token ngắn hạn của user đã hết hạn trong queue.

Nguyên tắc **least privilege** áp dụng cả người dùng lẫn service: mỗi token chỉ dành cho đối tượng nhận và scope cần thiết. Không truyền refresh token tới microservice nhận tài nguyên. Không log token để debug.

## 13. Scope, role, tenant và quyền sở hữu tài nguyên

Một ứng dụng có thể phân quyền ở nhiều tầng:

- **Scope:** quyền đã được AS cấp cho client/token, ví dụ **orders.read**, **orders.write**.
- **Role:** nhóm quyền nghiệp vụ, ví dụ **CUSTOMER**, **SUPPORT**, **ADMIN**. Không có chuẩn chung rằng mọi provider đặt role ở cùng một claim.
- **Tenant/organization:** không gian dữ liệu/cấu hình mà chủ thể được phép truy cập; cần được xác minh từ nguồn đáng tin cậy, không nhận nguyên tenant ID do client tự yêu cầu.
- **Ownership/resource policy:** kiểm tra một đơn hàng cụ thể có thuộc user hay nằm trong phạm vi công việc được ủy quyền hay không.
- **ABAC/policy:** xét thêm thuộc tính như trạng thái đơn, hạn mức, khu vực hoặc giao dịch đang bị khóa.

Ví dụ Alice có access token hợp lệ với scope **orders.read** nhưng gửi:

~~~http
GET /orders/ORDER-OF-BOB
Authorization: Bearer <access-token>
~~~

Nếu chỉ kiểm tra **orders.read** mà bỏ qua owner/tenant, API có nguy cơ **BOLA/IDOR** (truy cập trái phép đối tượng). Hệ thống phải kiểm tra object-level authorization sau khi xác minh token. Một role ADMIN trong token cũng cần được giới hạn theo đúng tenant/scope và chính sách sản phẩm.

Để tránh phân quyền rải rác thiếu nhất quán, nên định nghĩa authorization policy rõ ràng, kiểm tra ở mỗi resource server và có test âm tính cho người không đủ quyền.

## 14. Session, logout và vòng đời token

**Đăng nhập OIDC** và **phiên ứng dụng** không nhất thiết có cùng vòng đời:

- **RP session:** session giữa browser và ứng dụng. Có thể sống trong cookie HttpOnly/Secure/SameSite do backend quản lý; cần session fixation protection và timeout.
- **OP session:** phiên đăng nhập tại provider; RP không kiểm soát hoàn toàn.
- **Access token:** hết hạn nhanh hơn và cần cấp lại theo chính sách.
- **Refresh token:** có thể cấp lại token, có quy tắc rotation/revocation, giữ bí mật ở thành phần được phép.
- **Logout:** có thể chỉ xóa RP session, có thể yêu cầu logout tại OP, và có thể cần cơ chế OIDC front-channel/back-channel logout nếu OP/RP hỗ trợ.

**Xóa cookie local không tự động thu hồi mọi access token đã phát.** Với JWT tự xác minh offline, resource server thường chỉ thấy token hết hạn theo **exp**; nếu cần thu hồi tức thời phải thiết kế thời hạn ngắn, introspection, denylist hoặc cơ chế khác. Với opaque token, introspection hỗ trợ quyết định token có còn active không nhưng tạo phụ thuộc availability và cache TTL.

Đăng nhập lại không được tự động mở quyền cao hơn chỉ vì user đã có session; các hành động nhạy cảm có thể cần **step-up authentication** (MFA hoặc auth_time/acr phù hợp), kiểm tra quyền lại và lập audit.

## 15. Rủi ro bảo mật thường gặp và cách phòng tránh

| Lỗi thiết kế | Hậu quả | Cách xử lý |
|---|---|---|
| API chấp nhận ID Token thay access token | Token dành cho RP bị dùng sai mục đích tại API | Kiểm tra token purpose/type và **audience** đúng resource server |
| Chỉ decode JWT mà không verify | Token giả mạo có thể được tin | Kiểm tra chữ ký, algorithm allowlist, issuer, exp, aud |
| Tin mọi JWT từ cùng issuer | Token cho API khác có thể bị lạm dụng | Kiểm tra audience cụ thể và scope |
| Chỉ kiểm tra scope, bỏ qua owner/tenant | User đọc/sửa dữ liệu người khác | Object-level/tenant authorization cho mọi thao tác |
| Tin header X-User-Id từ Internet | User tự nhận danh tính bất kỳ | Chỉ dùng identity đã xác minh; xóa/ghi đè header tại trust boundary |
| Client secret nhúng trong SPA/mobile | Secret bị trích xuất | Dùng public client + PKCE, lưu secret tại backend nếu có |
| Bỏ state, nonce, PKCE | CSRF/replay/code injection | Tạo và kiểm tra giá trị per-login đúng vai trò |
| Redirect URI wildcard hoặc open redirect | Code/token rò rỉ tới domain khác | Allowlist URI chính xác, chặn open redirect |
| Log URL/token hoặc lưu token tùy tiện | Rò rỉ Bearer credential | Redact log, TLS, secure cookie/storage, giảm thời hạn |
| Token access quá rộng hoặc quá lâu | Lộ token gây tác động lớn | Scope/audience nhỏ, lifetime giới hạn, rotation/revocation |
| Gateway là nơi duy nhất kiểm tra | Internal request vượt gateway có thể bypass policy | Resource server cũng xác minh/authorize; mTLS/network policy |
| Sai ánh xạ role/scope từ provider | Cấp quyền thiếu hoặc thừa | Mapping có hợp đồng, test role/tenant thực tế |
| Cho phép mọi thuật toán/JWKS tùy ý | Algorithm/key confusion | Pin issuer và algorithm, JWKS từ metadata tin cậy |
| Coi CORS là authorization | API vẫn bị truy cập bởi non-browser client | Dựa vào token + server-side policy; cấu hình CORS chỉ cho browser |

Những lỗ hổng này không được giải quyết chỉ bằng HTTPS hoặc vì hệ thống đang chạy trong private VPC. Network segmentation và TLS bảo vệ kênh truyền; authorization vẫn phải quyết định quyền trên từng tài nguyên.

## 16. Discovery, key rotation và khả năng vận hành

OIDC provider thường công bố metadata qua đường dẫn **.well-known/openid-configuration**, trong đó có issuer, authorization endpoint, token endpoint, JWKS URI và tính năng hỗ trợ. Resource server hoặc RP chỉ tải metadata của issuer đã được **tin cậy và cấu hình trước**, không truy vấn một issuer URL tùy ý theo input không kiểm soát.

Khi OP quay khóa ký:

1. Token có header **kid** để gợi ý khóa ký; bộ xác minh chọn khóa từ **JWKS tin cậy**.
2. Bộ nhớ đệm JWKS cần refresh đúng chính sách và có cơ chế cập nhật khi xuất hiện kid mới.
3. Bộ xác minh vẫn kiểm tra chữ ký/algorithm/issuer/audience; không tải public key từ header tùy ý rồi tự tin tưởng.
4. Hệ thống cần cân nhắc outage khi resource server khởi động, khi provider offline hoặc khi cache hết hạn.

Việc xác minh JWT có thể thực hiện tại chỗ nếu đã có khóa và metadata hợp lệ; với opaque token cần introspection hoặc cơ chế tương đương. Mỗi cách có đánh đổi giữa khả năng thu hồi tức thời, phụ thuộc thời gian thực vào AS và chi phí vận hành.

Các chỉ số hữu ích: tỷ lệ 401/403 theo API, lỗi JWKS/discovery, login callback failure, nonce/state mismatch, token audience mismatch, số refresh-token reuse/revocation, độ trễ introspection, policy deny, truy cập cross-tenant bị chặn. Ghi log **requestId, issuer, subject đã xử lý theo chính sách dữ liệu, client_id, audience và quyết định authorization**; không ghi nguyên token hay thông tin nhạy cảm.

## 17. Kịch bản kiểm thử cho hệ microservices

| Kịch bản | Kết quả mong đợi |
|---|---|
| RP nhận ID Token đúng chữ ký, issuer, aud, exp, nonce | Tạo session cho đúng user |
| RP nhận ID Token đúng chữ ký nhưng aud của client khác | Từ chối đăng nhập |
| RP nhận ID Token thiếu/sai nonce đã yêu cầu | Từ chối, không tạo session |
| Authorization callback có state không khớp | Từ chối callback |
| Authorization code bị dùng lại hoặc code_verifier sai | Token exchange thất bại |
| Order API nhận access token đúng aud và orders.read, user sở hữu order | Cho phép đọc |
| Order API nhận ID Token aud=web-client | Trả 401/invalid token |
| Order API nhận access token của payments-api | Từ chối vì audience sai |
| Token hết hạn, sai issuer hoặc chữ ký | Từ chối |
| Access token hợp lệ nhưng thiếu orders.read | Trả 403 |
| Có orders.read nhưng order thuộc user/tenant khác | Từ chối; không lộ dữ liệu |
| Service dùng Client Credentials gọi API cho machine | Đánh giá service identity/scope, không giả lập user login |
| Token do OP quay khóa nhưng khóa mới hợp lệ | JWKS refresh cho xác minh đúng |
| Refresh token cũ bị sử dụng sau rotation trái phép | Chính sách reuse detection/revocation hoạt động |
| Gateway bị bypass qua internal route | Resource server vẫn thực thi policy |
| User logout khỏi RP khi access token còn hạn | RP session bị vô hiệu; quyền dùng token còn lại theo chính sách thu hồi đã công bố |

Nên có **test tích hợp với Identity Provider cấu hình gần production**, đồng thời test callback/PKCE/state/nonce, JWT signature/claims, audience mismatch và authorization theo tenant/ownership. Dùng token mẫu tự tạo hoặc mock đúng contract; không dùng token thật trong log và fixture công khai.

## 18. Hướng dẫn ra quyết định khi thiết kế

1. **Cần xác thực người dùng đăng nhập?** Dùng **OIDC** với OP tin cậy, Authorization Code + PKCE; xác minh ID Token tại RP và tạo session thích hợp.
2. **Cần client gọi API được bảo vệ?** Dùng **OAuth 2.0 access token** dành cho resource server, kiểm tra signature/introspection, issuer, audience, hạn và quyền.
3. **Không có người dùng, chỉ service gọi service?** Cân nhắc **Client Credentials** hoặc workload identity/mTLS theo kiến trúc; audit theo danh tính máy.
4. **Service gọi thay mặt user?** Xác định rõ delegation, audience và quyền của downstream API; dùng token exchange/on-behalf-of khi được hỗ trợ, không gửi bừa token của service khác.
5. **Microservice có tài nguyên riêng?** Thực hiện authorization tại biên tài nguyên, bao gồm tenant/ownership; gateway không tự quyết định toàn bộ nghiệp vụ.
6. **Browser cần giữ phiên?** Chọn BFF/session an toàn hoặc public client với PKCE theo rủi ro; bảo vệ CSRF/XSS và token storage.
7. **Nhiều issuer/tenant?** Cấu hình allowlist issuer, mapping identity dạng **(issuer, subject)**, audience riêng, tenant policy và test cross-tenant.
8. **Cần thu hồi quyền nhanh?** Thiết kế lifetime, introspection/denylist/rotation và quy tắc session/logout một cách nhất quán.

### Hai câu tự kiểm tra

- **“Token này được phát cho ai sử dụng?”** Nếu câu trả lời là **web-client**, đó không tự động là token Order API được chấp nhận; phải xem đúng loại token, audience và hợp đồng.
- **“Danh tính đã xác thực có đủ để truy cập tài nguyên này chưa?”** Chưa. API còn cần kiểm tra scope/role, tenant, owner và điều kiện nghiệp vụ tương ứng.

Một thiết kế microservices đúng dùng **OIDC để xác thực người dùng ở Relying Party**, **OAuth 2.0 để cấp quyền gọi API**, và **authorization tại từng resource server** để bảo vệ dữ liệu. Ba phần này phối hợp nhưng có ranh giới tin cậy và trách nhiệm riêng.
