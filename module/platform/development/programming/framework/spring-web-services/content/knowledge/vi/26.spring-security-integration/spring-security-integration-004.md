# Khác biệt giữa xác minh token với cơ chế lưu mật khẩu của ứng dụng

Trong một ứng dụng **Spring Web Services (Spring-WS)** tích hợp **Spring Security**, hai khái niệm dễ bị nhập làm một là **xác minh token** và **kiểm tra mật khẩu của người dùng**. Cả hai đều có thể dẫn tới một `Authentication` hợp lệ trong `SecurityContextHolder`, nhưng **đầu vào, bí mật được quản lý, thuật toán, chu kỳ sống và mục tiêu bảo vệ khác nhau**.

- **Kiểm tra mật khẩu** diễn ra khi một người dùng chứng minh rằng họ biết thông tin đăng nhập dài hạn. Hệ thống thường lưu *hash một chiều có salt và work factor*, ví dụ bcrypt, Argon2, scrypt hoặc PBKDF2; khi đăng nhập, `PasswordEncoder.matches(rawPassword, storedHash)` xác minh mật khẩu.
- **Xác minh access token** diễn ra khi client đã nhận một credential ngắn hạn từ hệ thống cấp phát hợp lệ và gửi nó đến SOAP service. Resource Server kiểm **JWT signature, issuer, audience, thời gian và policy** hoặc dùng **introspection** đối với opaque token. **Không cần, và thường không được, đem token ra so với password hash của user.**

Bài thuộc chương **Tích hợp Spring Security** của module `SPRING_WEB_SERVICES`. Bối cảnh là dịch vụ SOAP thiết kế **contract-first** qua XSD/WSDL, JAXB, `@Endpoint` và `WebServiceTemplate`, đồng thời có SOAP Fault, interceptor, XML security, WS-Security, TLS/mTLS, chứng chỉ và kiểm thử tương thích. Một hệ thống có thể sử dụng HTTP Bearer token để xác thực ở lớp Servlet, WS-Security để bảo vệ SOAP message, mật khẩu để đăng nhập tại Identity Provider hoặc tại authentication service, và authorization ở tầng nghiệp vụ. **Đây là những lớp bổ sung cho nhau, không mặc nhiên thay thế nhau.**

Ví dụ dùng **Java 17+, Spring Security 6+/7 (Servlet), Spring Boot tương thích và Spring-WS 4.x**. Một số class/property thay đổi qua major versions; ví dụ ghi rõ API sử dụng và các phần application code giả định. Các địa chỉ `example.test`, issuer/audience và dữ liệu người dùng chỉ để minh họa, không phải cấu hình production.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **authentication, token verification, password hashing và authorization** khác nhau thế nào.
2. Phân biệt **JWT đã parse** với **JWT đã verify và validate**; hiểu `JwtDecoder`, JWKS, `iss`, `aud`, `exp`, `nbf`, `scope` và `kid`.
3. Mô tả kiểm **opaque token bằng introspection** và điểm mạnh/yếu khi cần revocation.
4. Thiết kế `SecurityFilterChain` cho HTTP SOAP endpoint, không nhầm URL authorization với SOAP operation authorization.
5. Sử dụng `PasswordEncoder`/`DelegatingPasswordEncoder`/`DaoAuthenticationProvider` đúng mục đích khi quản lý mật khẩu người dùng.
6. Lý giải vì sao password hash không thể dùng để giải mã JWT, và vì sao `WS-Security UsernameToken PasswordDigest` không tương đương bcrypt hash.
7. Phân biệt HTTP `Authorization: Bearer`, SOAP `wsse:UsernameToken`, XML Signature và mTLS.
8. Đưa principal đã xác thực tới use case, áp **authorization trên từng tài nguyên**, tránh tin `buyerId` hoặc `username` do SOAP caller tự khai.
9. Xử lý phân biệt **HTTP 401/403**, SOAP Fault, lỗi TLS và response từ Identity Provider.
10. Thiết kế các test token giả, token hết hạn, JWKS rotation, password reset, SOAP authorization, concurrent context và replay.

## 1. Bốn câu hỏi bảo mật khác nhau

Trước khi cấu hình Spring, cần biết cơ chế nào trả lời câu hỏi nào:

| Câu hỏi | Lớp | Ví dụ |
| --- | --- | --- |
| **Bạn đang chứng minh điều gì?** | Authentication | Mật khẩu đúng; access token hợp lệ; mTLS cert thuộc partner A |
| **Chứng cứ đó còn đáng tin không?** | Verification/validation | JWT signature, issuer, audience, expiry; password hash match |
| **Bạn được phép làm gì?** | Authorization | Principal được quyền `orders:submit`, được sửa đơn này không |
| **Thông điệp có bị sửa/đọc trộm không?** | Channel/message security | HTTPS, WS-Security signature/encryption |

Một bearer token có `scope=orders.write` đã được xác minh **chưa chứng minh** caller được sửa mọi đơn hàng. Một mật khẩu đúng cũng **chưa chứng minh** user được đọc tài liệu của tenant khác. Và một SOAP Body đã ký bằng X.509 hợp lệ **không tự tạo authority** nếu ứng dụng chưa map signer identity sang account/partner được cho phép.

### 1.1. Hai lần xác thực thường nằm ở hai nơi

~~~mermaid
flowchart LR
    U["Người dùng / client"] -->|"Credentials / MFA"| I["Identity Provider / Authentication Service"]
    I -->|"Đăng nhập thành công → access token"| U
    U -->|"SOAP HTTP request + Bearer token"| R["Spring Security Resource Server"]
    R -->|"Verified principal/scopes"| E["Spring-WS @Endpoint"]
    E --> A["Application authorization"]
    A --> B["Business service"]
    I -. "Password hash DB hoặc external IdP" .-> H["Credential storage"]
~~~

**Không bắt SOAP Resource Server kết nối bảng `users.password_hash` trên từng request** chỉ để xử lý JWT đã được Identity Provider cấp. Ngược lại, nếu chính application cung cấp chức năng đăng nhập username/password, nó cần `PasswordEncoder` hoặc một identity provider tin cậy để xác minh credentials lúc đăng nhập.

### 1.2. Từ chứng cứ đến principal

Cả `UsernamePasswordAuthenticationToken` lẫn `JwtAuthenticationToken` có thể triển khai giao diện `Authentication`, nhưng:

- `UsernamePasswordAuthenticationToken` có thể bắt đầu là **unauthenticated login attempt** với raw password; `AuthenticationProvider` xác minh và tạo result đã authenticated.
- `JwtAuthenticationToken` thường đại diện **JWT được Resource Server xác minh**, với principal từ claims và authorities được mapper tạo.
- `BearerTokenAuthentication` có thể đại diện opaque token đã introspection thành công.
- Principal từ X.509 hoặc WS-Security có thể đến qua authentication provider/handler khác tùy integration.

**Không khởi tạo `UsernamePasswordAuthenticationToken.authenticated(...)` từ một `username` trong SOAP Body để tự nhận đã xác thực.** Chỉ lớp đã **thật sự kiểm chứng** credential và trust mới được tạo trạng thái authenticated phù hợp.

## 2. Hai quy trình dễ nhầm nhất

### 2.1. Quy trình đăng nhập bằng mật khẩu

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client đăng nhập
    participant F as Spring Security login filter
    participant P as DaoAuthenticationProvider
    participant U as UserDetailsService
    participant DB as User DB
    C->>F: username + raw password qua TLS
    F->>P: UsernamePasswordAuthenticationToken
    P->>U: loadUserByUsername(username)
    U->>DB: SELECT password_hash, status, authorities
    DB-->>U: UserDetails / {bcrypt}...
    P->>P: passwordEncoder.matches(raw, stored)
    alt Đúng và account hợp lệ
        P-->>F: Authenticated principal
        F-->>C: Session hoặc bước cấp token theo hệ thống
    else Sai
        P-->>F: Authentication failure
        F-->>C: Kết quả đăng nhập thất bại
    end
~~~

Nếu hệ thống dùng OAuth2 Authorization Server bên ngoài, quy trình xác minh mật khẩu có thể diễn ra **ở IdP**, không phải chính SOAP service. Mật khẩu thường **không được gửi trong mỗi SOAP operation** khi SOAP endpoint chỉ yêu cầu Bearer access token.

### 2.2. Quy trình gọi SOAP với access token

~~~mermaid
sequenceDiagram
    autonumber
    participant C as SOAP Client
    participant F as Spring Security Filter Chain
    participant V as JWT Decoder / Introspector
    participant E as Spring-WS Endpoint
    participant S as Application service
    C->>F: POST /ws/orders + Authorization Bearer ...
    F->>V: Verify signature/claims hoặc introspect
    alt Token hợp lệ
        V-->>F: Principal + authorities
        F->>E: SOAP Envelope qua MessageDispatcher
        E->>S: Authorize principal + order resource
        S-->>C: SOAP response
    else Token sai/hết hạn
        V-->>F: Authentication failure
        F-->>C: HTTP 401, có thể không có SOAP Fault
    end
~~~

Trong mô hình này, Resource Server **không nhận raw password**, không gọi `passwordEncoder.matches`, và không tự cấp token. Nó chỉ chấp nhận **chứng cứ ngắn hạn** đã được hệ thống cấp phát đáng tin phát hành và kiểm chứng theo cấu hình.

## 3. Access token là gì và không phải là gì?

### 3.1. JWT: ba phần, nhưng decode không đồng nghĩa verify

Một JWT compact dạng JWS thường có:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Ví dụ **payload minh họa, KHÔNG phải token hợp lệ**:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["urn:example:orders:soap"],
  "exp": 1893456000,
  "nbf": 1893452400,
  "scope": "orders.read orders.submit",
  "tenant": "tenant-a"
}
~~~

`Base64URL` là **encoding, không phải encryption**. Bất kỳ ai có bearer token dạng JWT có thể đọc header/payload nếu chúng không được mã hóa bằng cơ chế khác. **Không đưa mật khẩu, số thẻ, private key hoặc PII không cần thiết vào claims.**

Cả ba phần có thể được split/decode thành JSON mà **chưa kiểm signature**. Vì vậy:

~~~java
// SAI: parse payload base64 rồi tin "sub", "role", "tenant"
// mà không verify signature, issuer, audience, expiry.
String subject = decodeBase64JwtPayload(rawBearerToken).get("sub");
~~~

`decodeBase64JwtPayload` ở đây là pseudocode anti-pattern. Nếu attacker sửa `"scope":"admin"` rồi tự encode lại payload, code kiểu này có thể cho phép leo quyền. Chỉ dùng output từ **JwtDecoder đã xác minh và validate** theo cấu hình đúng.

### 3.2. Những thông tin cần kiểm khi xác minh JWT

| Kiểm tra | Ý nghĩa | Không được bỏ qua |
| --- | --- | --- |
| Chữ ký/JWS algorithm | Token do issuer/khóa tin cậy ký và không bị sửa | Không chấp nhận `alg=none` hoặc thuật toán không cho phép |
| `iss` | Issuer chính xác mà service tin | Không cho token từ issuer bất kỳ |
| `aud` | Token được cấp cho **dịch vụ này** | Không nhận token dành cho API khác |
| `exp` | Token chưa hết hạn | Thực thi time validation + clock skew được kiểm soát |
| `nbf` | Token chưa bị dùng quá sớm | Tương tự |
| `sub` / client identity | Chủ thể của token | Không đồng nhất user và machine client |
| `scope`/`scp`/roles | Quyền đã được issuer gán | Map authorities theo policy, không tự tin mọi claim |
| `kid`/JWKS | Chọn public key hợp lệ để verify | Không fetch arbitrary key URL do token header gợi ý |
| `typ`/token use | Đúng loại token (access token) theo profile | Không chấp nhận ID Token làm access token |
| `jti`/revocation | Định danh/token state nếu policy yêu cầu | Signature hợp lệ không chứng minh chưa bị thu hồi |

**Không tự dùng `jwt.header.jku` hoặc `x5u` để tải key từ URL do caller gợi ý**. JWKS location phải do trusted issuer/configuration quyết định để tránh SSRF và key confusion. Nếu cùng công ty có nhiều issuers, dùng resolver theo **allowlist**, mỗi issuer có signer/validation policy riêng; không động chấp nhận issuer bất kỳ từ claim chưa tin.

### 3.3. JWT signature khác password hash

JWT signature thường là **MAC hoặc chữ ký bất đối xứng** kiểm bằng cryptographic key, thực hiện đủ nhanh cho nhiều requests. Password hashing là **KDF/hash chậm có salt/work factor** dành cho low-entropy human password, giúp chống dò mật khẩu khi database rò rỉ. Dùng bcrypt để “verify JWT” là sai mô hình; dùng SHA-256 thô thay bcrypt/Argon2 để “lưu mật khẩu” cũng sai mô hình.

### 3.4. Token bị đánh cắp vẫn có thể bị dùng lại

Bearer token có đặc tính: **ai cầm token có thể dùng token** nếu chưa bị ràng buộc thêm. Một chữ ký hợp lệ không ngăn token bị replay trước `exp`. Phòng vệ: TLS, short TTL, audience tối thiểu, không log token, secure storage, revocation/introspection khi cần, có thể sender-constrained tokens (mTLS-bound/DPoP) nếu profile hỗ trợ. Không mặc định `jti` hiện diện là hệ thống đang enforce one-time-use.


## 4. JWT validation so với opaque token introspection

### 4.1. JWT được xác minh cục bộ

Spring Security Resource Server dùng `JwtDecoder` (thường Nimbus) để xác minh signature và claims. Với issuer/JWKS được cấu hình đúng, service có thể kiểm **cục bộ** trên request (sau khi đã lấy/cached public keys) mà không cần gọi IdP cho từng token.

Ưu điểm: latency thấp và giảm dependency trực tiếp lên IdP ở runtime. Nhược điểm: một JWT chưa hết hạn có thể tiếp tục hợp lệ dù account bị khóa/token bị thu hồi, trừ khi hệ thống có thêm revocation check, ngắn TTL, back-channel hoặc sender constraints. Public key rotation cần JWKS caching/refresh và chính sách chuyển đổi.

### 4.2. Opaque token được introspect

Opaque token thường là một chuỗi khó đoán, nội dung **không giải nghĩa được tại Resource Server**. Resource Server gửi token tới **introspection endpoint của IdP** qua HTTPS với client credentials bảo vệ; nhận thông tin như `active`, `sub`, `scope`, `exp` theo RFC 7662 và policy.

~~~text
Bearer <opaque-token>
        │
        ▼
Resource Server → HTTPS introspection → Authorization Server
                          │
                          ▼
                  active, subject, scope
~~~

Ưu điểm: trung tâm cấp token có thể quyết định **active/revoked** tại thời điểm introspection. Nhược điểm: latency, availability, rate limits và secret của introspection client; cache introspection results tăng hiệu năng nhưng có thể tạo cửa sổ chấp nhận token đã bị thu hồi. **Không** tự gửi opaque token đến mọi endpoint IdP, chỉ đến URI đã được cấu hình đáng tin.

### 4.3. Bảng so sánh

| Tiêu chí | JWT xác minh cục bộ | Opaque token introspection | PasswordEncoder |
| --- | --- | --- | --- |
| Đầu vào | Signed access JWT | Opaque bearer credential | Raw password của user |
| Kiểm chứng | Signature/claims/JWKS | Authorization Server `active` + metadata | `matches(raw, storedHash)` |
| Nguồn trust | Issuer keys + validators | Introspection endpoint + credentials | Password hash store + account state |
| Có cần DB user password? | **Không** | **Không** | Có nếu app tự quản lý local credentials |
| Có gọi IdP mỗi request? | Thường không | Thường có, trừ cache/config | Không; có thể truy DB user |
| Có chi phí cố ý chậm? | Không | Phụ thuộc network | Có, work factor |
| Chống token revoke tức thì? | Cần bổ sung | Theo introspection state/cache | Không liên quan |
| Phù hợp SOAP HTTP bearer? | Có | Có | Không dùng để verify bearer token |
| Lưu ở client | Access token tạm thời | Access token tạm thời | Password không được cache tùy tiện |

**Lưu ý:** Spring Security hỗ trợ introspection **ngay cả với token định dạng JWT** nếu policy muốn kiểm trạng thái tập trung. Cách *xác minh* token là một lựa chọn thiết kế độc lập với việc token có thể parse thành JWT hay không.

## 5. Spring Security Resource Server bảo vệ HTTP SOAP endpoint

Vì Spring-WS trên Servlet nhận HTTP tại `MessageDispatcherServlet`, Spring Security `FilterChainProxy` có thể xác thực bearer token **trước khi request tới SOAP dispatcher**. `SecurityFilterChain` xử lý HTTP path/method/header, không tự biết operation nằm trong SOAP Body.

### 5.1. Dependencies và cấu hình issuer/audience

Với Spring Boot tương thích Spring Security 6+/7, cần các starter/module liên quan:

~~~text
spring-boot-starter-webservices
spring-boot-starter-security
spring-boot-starter-oauth2-resource-server
~~~

Dòng trên là **tên dependency**, không phải tệp Gradle/Maven hoàn chỉnh. Khi kiểm JWT, Spring Security cần resource-server và JOSE/JWT support (Boot starter thường gom các dependency tương ứng). Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
          audiences:
            - urn:example:orders:soap
~~~

`issuer-uri` phải khớp claim `iss`; `audiences` giới hạn token dành cho SOAP API này. Tài liệu Spring Security xác nhận `issuer-uri` cấu hình kiểm issuer và timestamp claims, còn audience validation cần cấu hình tường minh khi có yêu cầu. Nếu service không thể truy metadata IdP khi startup, có thể cấu hình **cả** `issuer-uri` và `jwk-set-uri` đã được duyệt để không phụ thuộc discovery ngay lúc khởi tạo; không loại bỏ issuer check vì có JWKS URI.

**Các URL ở trên chỉ là placeholders**; không đưa bí mật signing/private key của issuer vào Resource Server. Với JWT bất đối xứng, Resource Server dùng **public key** từ JWKS, còn private signing key ở Authorization Server/HSM.

### 5.2. SecurityFilterChain scoped cho /ws/**

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SoapHttpSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain soapApiChain(HttpSecurity http)
            throws Exception {

        http.securityMatcher("/ws/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
        return http.build();
    }
}
~~~

**Giả định của ví dụ:** ứng dụng có SOAP API **stateless chỉ nhận bearer token**, không dùng browser cookie/session authentication trên `/ws/**`; khi đó việc tắt CSRF **trong chain này** có thể phù hợp. **Không sao chép `csrf.disable()` sang toàn bộ ứng dụng** có browser login/cookies. Nếu cần đọc WSDL public qua GET, tạo **matcher cho đúng đường dẫn và phương thức**, không cho mở mọi `/ws/**`.

`http.securityMatcher("/ws/**")` phải khớp **servlet mapping thật** (ví dụ `/ws/*`). Nếu SOAP servlet ở `/soap/*` hoặc `/services/*`, cần điều chỉnh chain. Có nhiều filter chains thì kiểm **thứ tự @Order** để request không lọt qua chain khác.

### 5.3. HTTP Authorization header khác SOAP Header

Một SOAP HTTP call có thể trông như:

~~~http
POST /ws/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1:SubmitOrder"
~~~

Token nằm trong **HTTP header**; SOAP Body có XML contract-first và có thể có SOAP Header riêng. Spring Security Resource Server lấy bearer token từ HTTP request theo cấu hình mặc định; **không tự lấy `<wsse:BinarySecurityToken>` hoặc `<ord:AccessToken>` từ SOAP XML**. Nếu đối tác chỉ hỗ trợ WS-Security Header, cần integration riêng (mục 10).

Không gửi access token trong URL query string: nó dễ rò qua logs, browser history, referrer và tracing. Với HTTPS, vẫn cần loại token khỏi HTTP access logs, observability, exception diagnostic và test snapshots.

### 5.4. Token authorities thường không phải ROLE_

Spring Security thường ánh xạ `scope`/`scp` từ JWT thành authorities có prefix `SCOPE_`, ví dụ `orders.submit` → `SCOPE_orders.submit`. **Không tự kiểm `hasRole("ADMIN")`** nếu access token thực chỉ cung cấp `scope` trừ khi có converter ánh xạ roles đáng tin:

~~~java
// URL-based rule, KHÔNG phân biệt hai SOAP operations cùng /ws/orders:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/ws/**")
    .hasAuthority("SCOPE_orders.submit"));
~~~

Dòng trên chỉ minh họa syntax; nếu cùng URL có cả `GetOrder` và `SubmitOrder`, áp rule này cho mọi operation sẽ sai quyền. Ví dụ cấu hình chính ở mục 5.2 chỉ đòi bearer hợp lệ; phân quyền operation ở **service layer** trong mục 6.

### 5.5. Authentication state sau khi JWT được chấp nhận

Khi bearer filter hoàn thành, `SecurityContextHolder` chứa `Authentication` (ví dụ `JwtAuthenticationToken`). `@Endpoint` có thể đọc qua `SecurityContextHolder.getContext().getAuthentication()`, hoặc tốt hơn truyền identity/authority vào application service. **Không tạo Authentication dựa trên field `callerId` trong Body**. Phải phân biệt token của người dùng và **client credentials token** đại diện service/machine; `sub` và `client_id` có semantics khác nhau theo issuer profile.

## 6. Một SOAP URL có nhiều operations: authorization phải sâu hơn

Một endpoint WSDL document/literal thường nhận nhiều SOAP operations tại cùng HTTP URL:

~~~text
POST /ws/orders
  Body root {urn:example:orders:v1}GetOrderRequest

POST /ws/orders
  Body root {urn:example:orders:v1}SubmitOrderRequest

POST /ws/orders
  Body root {urn:example:orders:v1}CancelOrderRequest
~~~

`SecurityFilterChain.requestMatchers("/ws/orders")` thấy **cùng đường dẫn** ở cả ba request. **Nó không tự đọc payload QName** hay hiểu `wsa:Action`/SOAPAction để suy ra quyền trên operation; đừng coi một authorization rule ở filter là đã phân quyền các methods trong `@Endpoint`.

### 6.1. Tách xác thực ở biên và cấp quyền ở service

~~~mermaid
flowchart TD
    A["HTTP Authorization Bearer"] --> B["Resource Server: JWT/opaque verification"]
    B --> C{"Principal hợp lệ?"}
    C -- "Không" --> X["HTTP 401 / 403 theo nguyên nhân"]
    C -- "Có" --> D["Spring-WS @PayloadRoot + JAXB"]
    D --> E["Application service + @PreAuthorize"]
    E --> F{"Scope và quyền resource?"}
    F -- "Không" --> Y["AccessDenied → status/Fault theo contract"]
    F -- "Có" --> G["Order business logic"]
~~~

Một thiết kế có thể cho phép các scopes:

| Operation | Authority yêu cầu | Quyền dữ liệu bổ sung |
| --- | --- | --- |
| `GetOrder` | `SCOPE_orders.read` | Order thuộc tenant của principal |
| `SubmitOrder` | `SCOPE_orders.submit` | Client được phép tạo đơn cho buyer này |
| `CancelOrder` | `SCOPE_orders.cancel` | Order có thể hủy và thuộc phạm vi caller |

### 6.2. Ví dụ method-level authorization

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final OrderRepository repository;
    private final OrderOwnershipPolicy ownership;

    public OrderApplicationService(
            OrderRepository repository,
            OrderOwnershipPolicy ownership) {
        this.repository = repository;
        this.ownership = ownership;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderResult getOrder(
            String orderId, CallerIdentity caller) {

        // Check authorization trên dữ liệu cụ thể,
        // không chỉ dựa vào scope chung.
        if (!ownership.canRead(caller, orderId)) {
            throw new OrderAccessDeniedException();
        }

        return repository.findVisibleOrder(orderId, caller.tenantId());
    }
}
~~~

`OrderRepository`, `OrderOwnershipPolicy`, `OrderResult`, `CallerIdentity` và `OrderAccessDeniedException` là **application types giả định**. Cần bật `@EnableMethodSecurity` ở configuration (và xử lý proxy/self-invocation đúng cách) để `@PreAuthorize` thực sự được kiểm. Method gọi từ `@Endpoint` nên đi qua **Spring bean proxy**; tự gọi method annotated từ chính class thường không kích hoạt Spring AOP method-security advice.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodAuthorizationConfig {}
~~~

**Không tạo `CallerIdentity` từ `request.getBuyerId()` mà không đối chiếu principal đã xác thực.** Identity phải đến từ `Authentication` được tạo bởi verifier, có issuer/tenant/client identity đáng tin, rồi được application mapper kiểm tra.

### 6.3. Principal và quyền tài nguyên

Một JWT `tenant=tenant-a` là claim được issuer ký, nhưng việc tin claim đó vẫn phụ thuộc **issuer identity và policy**. Trong môi trường multi-tenant, không cho caller tự sửa tenant trong XML Body để thay quyền. Authorization có thể cần truy vấn DB kiểm entity ownership, principal status hoặc entitlement thay đổi theo thời gian; việc token signature hợp lệ không loại trừ những bước đó.

### 6.4. Khi dùng @Endpoint và SOAP Fault

`@Endpoint` có thể bắt `AccessDeniedException` hoặc để Spring Security/WS exception handling xử lý theo cấu hình. Không giả định Spring Security Servlet `AccessDeniedHandler` sẽ tự chuyển mọi exception phát sinh trong SOAP business service thành typed SOAP Fault: `ExceptionTranslationFilter` chỉ xử lý các authentication/authorization exceptions đi qua filter chain của Servlet trong phạm vi của nó; Spring-WS có exception resolvers/interceptors riêng.

Cần định nghĩa một **error contract an toàn**, chẳng hạn `ORDER_ACCESS_DENIED` trong SOAP Fault Detail khi request đã tới business layer. Không trả chi tiết “order tồn tại nhưng của tenant khác” nếu policy đòi giấu sự tồn tại; đôi khi trả cùng mã cho not-found và forbidden để tránh dò dữ liệu.


## 7. Lưu mật khẩu trong ứng dụng: không lưu “token hash”

Nếu chính ứng dụng **có chức năng đăng nhập bằng mật khẩu**, yêu cầu cơ bản là **không lưu raw password** và **không lưu dạng có thể giải mã ngược** chỉ để tiện xác thực. `PasswordEncoder` của Spring Security tạo **một chiều** một giá trị dành cho việc kiểm password khi đăng nhập.

### 7.1. Vì sao phải dùng thuật toán chậm và có salt?

Mật khẩu do người dùng đặt thường có entropy thấp hơn một khóa ngẫu nhiên 256-bit. Nếu kẻ tấn công lấy bảng `users`, họ có thể thử hàng tỷ mật khẩu phổ biến nếu ứng dụng chỉ dùng `SHA-256(password)`. Bởi vậy:

- **Per-password random salt** khiến cùng mật khẩu có thể cho hash khác nhau và cản rainbow table.
- **Adaptive work factor** (cost/time/memory) khiến thử mỗi phỏng đoán tốn tài nguyên.
- **One-way password verification** cho phép `matches` mà không cần giải mã password.
- **Version/algorithm metadata** tạo điều kiện nâng cấp bcrypt → Argon2/scrypt và tăng work factor.

BCrypt, Argon2id, scrypt và PBKDF2 có đặc điểm triển khai khác nhau; hãy chọn theo threat model, library support và benchmark CPU/memory. Spring Security khuyến nghị hiệu chỉnh work factor theo khả năng máy chủ (tài liệu minh họa mốc verify vào khoảng một giây, không phải SLA bắt buộc cho mọi login). Đừng đặt cost quá cao làm login dễ bị DoS, cũng không dùng cost thấp vĩnh viễn.

### 7.2. Hash trên database là thứ gì?

Ví dụ giá trị **minh họa** của `DelegatingPasswordEncoder`:

~~~text
{bcrypt}$2a$10$dXJ3SW6G7P50lGmMkkmwe.20cQQubK3.HZWzG3YB1tlRy.fqvM/BG
~~~

Phần `{bcrypt}` giúp encoder biết dùng strategy nào; chuỗi bcrypt bên trong mang salt/cost và hash. Giá trị đó không phải JWT, không phải session cookie, không phải access token, và **không nên gửi cho client**. Database có thể lưu:

~~~sql
CREATE TABLE app_user (
    id           VARCHAR(64) PRIMARY KEY,
    login_name   VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(512) NOT NULL,
    enabled      BOOLEAN NOT NULL,
    password_updated_at TIMESTAMP NOT NULL
);
~~~

Đây là **schema minh họa**, cần bổ sung audit/password reset/locking và các indices/constraints theo DB thật. Username cũng là dữ liệu có thể nhạy cảm; không dùng log plaintext passwords hoặc hash đầy đủ trong lỗi SQL.

### 7.3. Dùng PasswordEncoder đúng cách

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration(proxyBeanMethods = false)
public class PasswordStorageConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
~~~

Khi đăng ký user:

~~~java
// Fragment trong service; không hardcode raw password vào code.
String encoded = passwordEncoder.encode(command.rawPassword());
userRepository.saveNewAccount(
    command.loginName(),
    encoded,
    command.otherPublicData());
~~~

Khi xác thực mật khẩu:

~~~java
boolean ok = passwordEncoder.matches(
    suppliedRawPassword,
    storedPasswordHash);
~~~

**Không** làm:

~~~java
// SAI: bcrypt sử dụng salt ngẫu nhiên trên mỗi lần encode.
boolean ok = passwordEncoder.encode(suppliedRawPassword)
    .equals(storedPasswordHash);
~~~

Hai lần encode cùng raw password có thể tạo hai hash khác nhau; `matches` đọc salt/cost từ hash đã lưu và so kết quả theo thuật toán tương ứng.

### 7.4. Hash != encryption

| Cơ chế | Có giải ngược được không? | Key cần giữ | Mục đích |
| --- | --- | --- | --- |
| bcrypt/Argon2 password hash | Không theo thiết kế | Không có decryption key | Xác minh raw password khi login |
| AES encryption | Có, nếu giữ key | Symmetric secret key | Bảo mật dữ liệu phải khôi phục |
| JWT JWS signature | Xác minh chữ ký/MAC, không “giải mã token” | Public verify key hoặc shared MAC key | Xác minh issuer và integrity |
| JWE encrypted token | Có, với decryption key | Recipient key | Confidentiality token content |
| SOAP XML Encryption | Có, với recipient key | Recipient private key/symmetric content key | Che selected SOAP elements |

**Không dùng AES encryption để lưu mật khẩu** theo cách có thể giải ngược chỉ vì ứng dụng muốn so mật khẩu; password nên được hash một chiều. Ngược lại, không dùng bcrypt hash làm “khóa giải mã” một JWT JWE: hai cơ chế có đầu vào và giao thức khác.

### 7.5. Nâng cấp work factor/algorithm

Khi user đăng nhập thành công, có thể kiểm `passwordEncoder.upgradeEncoding(storedHash)` và **rehash raw password mà user vừa cung cấp** trước khi đưa vào persistence với cơ chế cập nhật an toàn. Không thể tự “nâng cấp” một hash bcrypt cũ thành Argon2 mới nếu không có raw password: hash là một chiều.

Cần bảo vệ các bước migration qua login concurrency, account version hoặc compare-and-swap khi ghi `password_hash`, tránh một login cũ ghi đè trạng thái reset password mới. Nếu hash cũ thiếu prefix `{id}`, phải thiết kế migration rõ chứ không gọi `NoOpPasswordEncoder` mặc định để “chữa lỗi”.

### 7.6. Password change/reset không đồng nghĩa revoke token

Khi user đổi mật khẩu hoặc bị khóa account:

- Password hash store phải thay/disable và chặn **future password login**.
- Các **JWT access tokens đã cấp** có thể vẫn còn hiệu lực tới `exp` nếu Resource Server chỉ verify cục bộ, trừ khi có revocation/session version/user-state check.
- Refresh token/session của user cần chính sách revoke riêng.
- Opaque introspection có thể nhanh chóng báo `active=false` khi IdP quản lý được.
- Với sự cố compromise, cần quy trình terminate sessions, rotate relevant credentials, audit, rate limit, MFA tùy rủi ro.

**Đổi password không tự làm một JWT đã ký trở nên sai chữ ký.** Đây là ví dụ điển hình chứng minh password storage và token validation có hai vòng đời khác nhau.

## 8. DaoAuthenticationProvider: kiểm mật khẩu khi thực sự có login

`DaoAuthenticationProvider` dùng `UserDetailsService` để lấy tài khoản và `PasswordEncoder` để kiểm mật khẩu. Nó thường tham gia login bằng username/password, **không thay thế** `JwtDecoder` trong resource server.

### 8.1. Đọc tài khoản và hash đã lưu

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    public DatabaseUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        Account account = accounts.findByLoginName(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Invalid credentials"));

        return User.withUsername(account.loginName())
            .password(account.passwordHash()) // Đã encode trong DB
            .authorities(account.authorities())
            .disabled(!account.enabled())
            .build();
    }
}
~~~

`AccountRepository` và `Account` là application types giả định; cần map đúng account locking/expiry/password freshness, null handling và persistence constraints. `UserDetails.password` ở đây là **hash**, không phải raw password; đừng đưa nó vào DTO trả về cho SOAP client.

### 8.2. Đăng ký DaoAuthenticationProvider

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration(proxyBeanMethods = false)
public class PasswordLoginProviderConfig {

    @Bean
    DaoAuthenticationProvider daoAuthenticationProvider(
            UserDetailsService users,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return provider;
    }
}
~~~

API constructor có `UserDetailsService` minh họa Spring Security 6+/7 phù hợp. Việc bean này được sử dụng bởi một `AuthenticationManager`/login filter nào còn phụ thuộc cách ứng dụng cấu hình. **Chỉ tạo bean không tự tạo SOAP login operation hoặc OAuth2 Authorization Server**.

Spring Security `DaoAuthenticationProvider` xử lý thêm các trạng thái account và có cách hạn chế timing side channel về việc username có tồn tại hay không. Nếu tự viết authentication provider, cần tránh trả lỗi/timing khác biệt cho username có thật và không có thật.

### 8.3. Tại sao không check PasswordEncoder trên mọi SOAP call?

Password hashing được **cố tình làm chậm**. Nếu mỗi SOAP request lại tải account và chạy bcrypt/Argon2 `matches` dù caller đã có access token ngắn hạn, ứng dụng tăng CPU/cơ hội DoS, tạo thêm đường đi cho mật khẩu và làm sai ranh giới trách nhiệm.

Mô hình thích hợp thường là:

~~~text
User authenticates once with password + MFA
      ↓
IdP/session issuer creates short-lived credential
      ↓
SOAP calls carry bearer token over HTTPS
      ↓
Resource Server validates token + authorizes operation
      ↓
Password database is NOT queried for each SOAP call
~~~

Ngoại lệ: legacy SOAP contract **thực sự dùng credentials ở mỗi message** (ví dụ WS-Security UsernameToken hoặc HTTP Basic) thì mỗi lần gọi có thể cần kiểm shared secret/password theo profile. Đó là **một quyết định giao thức khác**, không phải hành vi của JWT Resource Server.

### 8.4. Ngăn tấn công vào chức năng login

- TLS bắt buộc; không chấp nhận credentials qua HTTP rõ.
- Rate limit, backoff và kiểm soát credential stuffing.
- MFA/passwordless khi phù hợp người dùng và rủi ro.
- Password reset token đủ entropy, TTL, single-use và lưu hash/token state thích hợp.
- Không log raw password, password hash hoặc SecurityContext credentials.
- Không nói “username tồn tại nhưng password sai” công khai nếu yêu cầu chống account enumeration.
- `PasswordEncoder` work factor phù hợp hiệu năng; không trả thời gian khác biệt rõ giữa account tồn tại/không tồn tại do code tự viết.
- Sau login, dọn raw credentials khỏi memory ở nơi khả thi; không giữ `String rawPassword` trong singleton field.

## 9. Đối chiếu trực tiếp token verification và password storage

| Câu hỏi | Token verification | Password storage/check |
| --- | --- | --- |
| Ai cấp chứng cứ? | Authorization Server/IdP phát access token | User chọn mật khẩu/IdP đăng ký secret |
| Khi nào diễn ra? | **Mỗi API call** có bearer token (hoặc cache policy) | Login/password change/reset |
| Đầu vào server thấy | Access token ngắn hạn | Raw password lúc login, hash lưu trong DB |
| Thành phần Spring | `BearerTokenAuthenticationFilter`, `JwtDecoder`, `OpaqueTokenIntrospector` | `DaoAuthenticationProvider`, `UserDetailsService`, `PasswordEncoder` |
| Thuật toán | Public-key signature/MAC hoặc introspection | Bcrypt/Argon2/scrypt/PBKDF2 |
| Bí mật cần ở SOAP service? | Public JWKS keys, config trusted issuer hoặc introspection client secret | Không cần nếu SOAP service chỉ là Resource Server |
| Có salt/work factor? | Không theo kiểu password hash | Có, intentionally slow |
| Kiểm hết hạn | `exp/nbf` hoặc introspection state | Account lock/reset/password age policy |
| Xử lý scope | Claim/introspection authorities | Authorities từ account DB sau login |
| Liên quan revoke | JWT cần giải pháp bổ sung; opaque introspection phản ánh active | Đổi hash chặn future login, không tự revoke access tokens |
| Được gửi qua SOAP Body không? | Không nên; HTTP `Authorization` theo resource server | Không nên trong mỗi operation; ngoại lệ giao thức có policy riêng |
| Lưu trên server | JWT thường không cần lưu; có thể có denylist | Lưu `password_hash`, không lưu raw |
| Test chính | Signature/issuer/audience/time/roles/rotation | Correct matches/salt/upgrade/login abuse |

### 9.1. Ba suy luận sai nhưng rất phổ biến

**Sai 1:** “Resource Server đọc JWT rồi dùng bcrypt so token với mật khẩu hash.” Không đúng; token là chứng cứ **do issuer cấp**, không phải mật khẩu người dùng.

**Sai 2:** “JWT có `sub=user-42` nghĩa là password user-42 vừa được kiểm.” Không đúng; JWT chỉ chứng minh issuer đã phát claim/authorization theo quy trình riêng. Với client credentials grant, token có thể đại diện máy thay vì user và không có mật khẩu người dùng.

**Sai 3:** “User đổi password thì mọi JWT bị vô hiệu.” Không tự động; phải có token revocation strategy/issuer session state, không thể đổi chữ ký JWT đã phát.

### 9.2. Sai phạm vi bảo mật có thể dẫn tới sai kiến trúc

Một SOAP server nhận JWT từ partner A **không nên** đòi truy xuất DB password hash của tất cả người dùng ở partner A. Điều đó khiến dữ liệu credential lan ra nhiều hệ thống, tăng blast radius và mâu thuẫn mô hình trust. Server chỉ cần **issuer/keys hoặc introspection**, rồi map principal/permissions sang domain authorization của mình.

Ngược lại, một dịch vụ đăng nhập nội bộ **không nên** tự giải mã JWT để kiểm username/password khi user đang cung cấp raw password: JWT validation không thay password hashing.


## 10. WS-Security UsernameToken: điểm khác đặc biệt của SOAP

Ở SOAP enterprise integration, có đối tác không gửi HTTP bearer token mà dùng `wsse:Security` và `wsse:UsernameToken`. Đây là **giao thức WS-Security riêng**. Cần phân biệt kỹ `PasswordText`, `PasswordDigest`, BCrypt và JWT.

### 10.1. Hai nơi đặt credential khác nhau

**HTTP Bearer token:**

~~~http
POST /ws/orders HTTP/1.1
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: application/soap+xml
~~~

**SOAP WS-Security UsernameToken:**

~~~xml
<soap:Header
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
  <wsse:Security>
    <wsse:UsernameToken>
      <wsse:Username>partner-a</wsse:Username>
      <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">REDACTED</wsse:Password>
    </wsse:UsernameToken>
  </wsse:Security>
</soap:Header>
~~~

Đây là **fragment** SOAP Header, không phải Envelope đầy đủ. `REDACTED` thể hiện vị trí credential phải được che trong tài liệu/logs; trong production, phải dùng HTTPS và policy security phù hợp. `UsernameToken` không tự cấp OAuth2 access token, và Spring Security `oauth2ResourceServer(jwt())` **không tự đọc** `wsse:UsernameToken` trong SOAP XML.

### 10.2. PasswordText không phải password hash

`wsse:PasswordText` có thể mang **plain password** hoặc **password equivalent** theo UsernameToken Profile. Nhưng việc protocol cho phép giá trị “tương đương password” không có nghĩa nên gửi **database password hash** cho đối tác. Nếu lộ một hash được dùng trực tiếp làm shared secret, attacker có thể dùng nó để xác thực mà không cần tìm raw password; nó trở thành **credential bearer-equivalent**.

Nếu dịch vụ chấp nhận raw password từ `PasswordText`, ứng dụng có thể thiết kế custom validation để lấy raw credential và so bằng `PasswordEncoder.matches(raw, storedHash)`, **nhưng** WSS4J callback/AuthenticationProvider phải thực sự hỗ trợ cơ chế đó. Không tự cho rằng callback handler mặc định đã tích hợp BCrypt đúng chỉ vì Spring Security có `PasswordEncoder`.

### 10.3. PasswordDigest theo WS-Security UsernameToken Profile

WS-Security UsernameToken Profile 1.1.1 định nghĩa `PasswordDigest` kiểu:

\[
\mathrm{PasswordDigest}=\mathrm{Base64}\Bigl(\mathrm{SHA1}(\mathrm{NonceBytes}\,\Vert\,\mathrm{CreatedUTF8}\,\Vert\,\mathrm{PasswordUTF8})\Bigr)
\]

Trong đó `NonceBytes` là bytes đã giải Base64 từ `wsse:Nonce`, `CreatedUTF8` là timestamp string mã hóa UTF-8, và `PasswordUTF8` là raw shared password **hoặc password-equivalent secret** đã thỏa thuận. `Nonce` và `Created` giúp kiểm tra replay khi receiver kiểm timestamp freshness và dùng nonce cache. **SHA-1 trong công thức legacy này không phải thuật toán được khuyến nghị để lưu mật khẩu vào database.**

Ví dụ fragment digest (**giá trị chỉ minh họa**):

~~~xml
<wsse:UsernameToken
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
  <wsse:Username>partner-a</wsse:Username>
  <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">BASE64_DIGEST_EXAMPLE</wsse:Password>
  <wsse:Nonce>BASE64_NONCE_EXAMPLE</wsse:Nonce>
  <wsu:Created>2030-01-01T00:00:00Z</wsu:Created>
</wsse:UsernameToken>
~~~

### 10.4. Vì sao bcrypt hash không tự xác minh được PasswordDigest?

Giả sử client biết **mật khẩu thô** `correct-horse-...` và gửi digest từ raw secret. Server chỉ lưu:

~~~text
{bcrypt}$2a$12$...salt+hash...
~~~

Vì BCrypt **không cho giải ngược** ra raw password, server không thể tái tạo `SHA1(nonce+created+rawPassword)` chỉ từ bcrypt hash theo công thức mặc định. Hai loại phép biến đổi không tương đương:

~~~text
Stored DB:
  bcrypt(rawPassword, randomSalt, cost)

Incoming WS-Security:
  Base64(SHA1(nonceBytes || createdBytes || rawPassword))

Không có phép toán tổng quát:
  rawPassword = inverseBcrypt(storedHash)
~~~

Một protocol có thể **thỏa thuận rõ** dùng password equivalent làm shared secret để tạo digest, nhưng lúc đó cả hai phía cần biết **cùng shared secret**; nếu lấy database hash đem cấp cho client thì hash **trở thành secret có thể bị sử dụng lại**, làm hỏng ý nghĩa bảo vệ mật khẩu đăng nhập của user. Vì vậy không “sửa” bằng cách chia sẻ `users.password_hash` cho client hoặc lưu plaintext/reversible password của người dùng chỉ để đáp ứng một WS-Security PasswordDigest legacy profile.

**Hướng thiết kế nên ưu tiên:** OAuth2 Bearer token qua HTTPS ở HTTP layer; hoặc WS-Security X.509 signature / mTLS identity nếu đối tác cần message-level security; hoặc **credential kỹ thuật riêng biệt**, quản trị bằng secret manager và rotation, không dùng chung mật khẩu người dùng. Nếu buộc dùng UsernameToken PasswordDigest, xem xét threat model/replay/cache/secret distribution và xác minh khả năng callback handler.

### 10.5. Wss4jSecurityInterceptor không giống JwtDecoder

Một `Wss4jSecurityInterceptor` có thể cấu hình:

~~~java
// Fragment minh họa; callback phải được hiện thực/cấu hình thật.
Wss4jSecurityInterceptor wss = new Wss4jSecurityInterceptor();
wss.setValidationActions("UsernameToken");
wss.setValidationCallbackHandler(usernameTokenCallbackHandler);
~~~

`usernameTokenCallbackHandler` là bean/handler **do ứng dụng chọn theo protocol và kiểu password**, không phải tên một API có sẵn; cần imports, WSS4J version, nonce/time/replay checks và Spring-WS endpoint registration. Việc xác thực thành công UsernameToken **không đồng nghĩa** một `Authentication` đã được đưa vào `SecurityContextHolder` cho mọi cấu hình. Nếu muốn tích hợp Spring Security authorization, phải map WS-Security principal sang trusted Spring `Authentication` bằng một integration đã xác minh, không lấy username từ Header rồi tự coi authenticated.

### 10.6. Không tự trộn JWT và UsernameToken

Một SOAP request có thể mang cả HTTP Bearer token và WS-Security UsernameToken/X.509. Nếu chính sách chỉ yêu cầu bearer, đừng “bổ sung password” để tăng bảo mật theo cảm tính. Nếu chính sách **yêu cầu cả hai**, xác định:

- Principal từ hai chứng cứ có phải cùng tenant/partner hay không.
- Credential nào là identity chính, cái nào cung cấp integrity/confidentiality.
- Nếu identity xung đột, phải **reject**, không chọn tùy ý cái có quyền cao hơn.
- Thời gian sống, revocation và rotation của mỗi cơ chế khác nhau.
- Error contract không tiết lộ raw credentials/token hoặc thông tin xác thực nội bộ.

## 11. Xác thực bằng certificate, WS-Security và phạm vi của Authorization

Một SOAP partner có thể sử dụng:

| Cơ chế | Đầu vào | Verifier | Thích hợp |
| --- | --- | --- | --- |
| HTTP bearer JWT | HTTP Authorization header | Spring Security `JwtDecoder` | OAuth2 Resource Server |
| HTTP bearer opaque | HTTP Authorization header | Spring Security introspection | Central revocation/state |
| HTTP Basic | HTTP Authorization Basic | HTTP authentication provider | Legacy credential mỗi request; TLS bắt buộc |
| WS-Security UsernameToken | SOAP Header | WSS4J validator/handler | Legacy SOAP contract |
| WS-Security X.509 Signature | SOAP Security Header + signed XML | WSS4J + certificate trust | End-to-end message integrity/authentication |
| TLS client certificate | TLS handshake | TLS stack/Spring X.509 integration nếu cấu hình | Partner/device identity ở transport |
| Spring form login/session | Cookie/Servlet session | Spring Security login/session | Browser-oriented applications |

**Mỗi verifier phải đưa ra identity có nguồn gốc rõ.** Cùng một username string không có nghĩa hai cơ chế đã kiểm chứng như nhau. Identity của mTLS cert có thể đại diện **organization** hoặc machine, còn JWT `sub` đại diện user được ủy quyền. Đừng map chúng sang “ROLE_ADMIN” theo tên được khai trong XML.

### 11.1. Xác thực transport không đồng nghĩa message integrity end-to-end

TLS/mTLS bảo vệ kênh giữa các điểm TLS termination. Nếu SOAP message được forward qua gateway, hệ thống có thể cần WS-Security XML Signature để bảo vệ Body/Headers xuyên nhiều chặng. Ngược lại, XML Signature của Body chưa chắc bảo vệ HTTP Authorization Header; JWT và WS-Security là **hai chứng cứ độc lập** phải được kiểm theo policy.

### 11.2. Authorization luôn thuộc ứng dụng

Bên B đã xác minh chữ ký X.509 của partner A, hoặc JWT do IdP cấp, vẫn cần chính sách:

~~~text
Signer/client: partner-a
SOAP operation: SubmitOrder
Body.buyerId: BUYER-42

Question: partner-a có quyền đặt hàng thay BUYER-42?
Answer: tra policy/entitlement/contract và dữ liệu tin cậy
~~~

Không dùng chỉ `wsu:Id`, `wsa:MessageID`, `SOAPAction` hay `buyerId` để cấp quyền; những trường này phục vụ SOAP protocol/correlation hoặc dữ liệu nghiệp vụ, không phải credential đã được xác minh.

### 11.3. XSD validation không phải authentication

XSD có thể yêu cầu `buyerId` đúng pattern và `amount` là số dương. Nhưng attacker vẫn có thể tạo XML hợp schema. JWT verification/WS-Security xác minh caller/message; XSD validation xác minh **hình dạng dữ liệu**; authorization xác minh **quyền hành động**; business rules xác minh **điều kiện nghiệp vụ**. Phải có đủ các bước theo contract.

## 12. SecurityContextHolder, đa luồng và xử lý bất đồng bộ

### 12.1. SecurityContext là per-request, không phải singleton state

Trong Servlet flow phổ biến, Spring Security gắn `SecurityContext` với request/thread qua `SecurityContextHolder`; kết thúc request cần cleanup theo filter lifecycle. **Không** lưu `Authentication currentCaller` trong mutable field của singleton `@Endpoint` hoặc application service, vì hai SOAP requests đồng thời có thể trộn danh tính.

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public CallerIdentity currentCaller() {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

    if (auth == null || !auth.isAuthenticated()) {
        throw new MissingCallerException();
    }

    return verifiedCallerMapper.map(auth);
}
~~~

`CallerIdentity`, `MissingCallerException`, `verifiedCallerMapper` là application types/bean giả định. **Không** coi `auth.isAuthenticated()` một mình là đủ: có thể có `AnonymousAuthenticationToken` được đánh dấu authenticated về kỹ thuật. Cần kiểm loại principal/phương thức, trusted issuer, authority và scope theo policy. Nếu đăng ký anonymous authentication, nên dùng matcher/`AuthenticationTrustResolver` hoặc business caller mapper xử lý anonymous đúng.

### 12.2. Async tasks không tự nhận ThreadLocal identity

~~~text
Servlet thread A:
  SecurityContext(user-A)
  ↓ gọi @Async / ExecutorService
Worker thread B:
  SecurityContext có thể rỗng, không phù hợp hoặc stale
~~~

Nếu một SOAP call tạo background job, hãy truyền **immutable, giới hạn trường dữ liệu** về authenticated caller vào durable job record, hoặc dùng `DelegatingSecurityContextExecutor`/framework propagation đã được cấu hình đúng. **Không truyền raw bearer token, raw password hoặc private key vào queue** chỉ để “giữ login state”. Ở worker, thực hiện authorization thích hợp trên durable identity và trạng thái hiện tại, nhất là khi công việc tiếp diễn sau token expiry.

### 12.3. Không đặt credentials vào MDC hoặc metrics

Correlation ID, `wsa:MessageID` và business requestId có thể phục vụ tracing, nhưng không phải secrets. Access token, JWT compact string, password/hash, UsernameToken, WS-Security ciphertext/signature và TLS private key không được ghi làm labels hoặc MDC; chúng có thể bị đọc qua dashboards và log export. Khi trace SOAP request, chỉ lưu **hash định danh token một chiều riêng cho telemetry** nếu policy cần, không lưu toàn credential có thể dùng lại.

### 12.4. Concurrent requests và trust context

Hai requests A/B tới cùng `WebServiceTemplate` hoặc `@Endpoint` có thể mang credentials của hai tenant khác nhau. Mọi custom interceptor, callback handler, user mapping và `SecurityContextHolderStrategy` phải tránh shared mutable `currentTenant`. Không gọi `SecurityContextHolder.setStrategyName(MODE_GLOBAL)` để “đơn giản hóa” xử lý đa luồng: global context là nguồn rò identity giữa requests.


## 13. HTTP 401/403, SOAP Fault và lỗi TLS khác nhau thế nào?

Trong SOAP integration, **đừng giả định mọi lỗi đều trả một `<soap:Fault>`**. Khi request bị Spring Security HTTP filter từ chối **trước** `MessageDispatcherServlet`, server thường trả HTTP status theo security entrypoint/handler, và **không tạo SOAP Envelope**.

### 13.1. Failure matrix theo lớp

| Tình huống | Nơi phát hiện | Điều client thường thấy |
| --- | --- | --- |
| Không có bearer token ở URL bắt buộc | Spring Security authentication entrypoint | HTTP `401 Unauthorized`; có thể không có SOAP Fault |
| JWT signature giả, issuer khác | `JwtDecoder`/resource server filter | HTTP 401 |
| JWT quá `exp`, chưa `nbf` | JWT validator | HTTP 401 |
| JWT có `aud` không phải SOAP API | Audience validator | HTTP 401 |
| Token valid nhưng thiếu scope cho HTTP path | Web authorization filter | HTTP `403 Forbidden` |
| Opaque token `active=false` | Introspection provider | HTTP 401 |
| Introspection timeout/IdP unreachable | Authentication infrastructure | Lỗi 5xx/transport theo cấu hình; **không mặc định** là invalid credentials |
| HTTP mTLS handshake fail | TLS stack | Kết nối thất bại **trước SOAP** |
| WS-Security UsernameToken sai | SOAP/WSS4J interceptor | SOAP security Fault hoặc transport failure theo stack |
| X.509 XML Signature sai | WSS4J verifier | SOAP Fault/security error |
| SOAP Body hợp schema nhưng buyerId thuộc tenant khác | Business authorization | Typed SOAP Fault hoặc policy-specific denial |
| SOAP payload sai XSD | `PayloadValidatingInterceptor` | SOAP Client/Sender Fault nếu parser/dispatcher tới được |
| Backend DB lỗi | Business service | Server/Receiver Fault với reason công khai |
| Server đã commit nhưng SOAP response mất | Transport sau commit | Timeout; client phải tra idempotency state |

**401** nói chưa có credential hợp lệ cho HTTP resource; **403** nói principal đã được xác thực nhưng bị từ chối ở HTTP authorization (theo cách cấu hình thường gặp). Không phải mọi HTTP 403 đều do Bearer token: CSRF filter, IP policy, gateway hoặc method-level authorization cũng có thể dẫn tới status khác nhau. Phải kiểm cả header `WWW-Authenticate` theo OAuth2 Bearer semantics, nhưng không tiết lộ token, key hay nội bộ security implementation.

### 13.2. Client Spring-WS cần phân biệt hai đường lỗi

`WebServiceTemplate` có thể báo `SoapFaultClientException` khi server trả SOAP Fault hợp lệ. Nhưng HTTP 401/403 **không có SOAP Envelope** có thể dẫn đến transport/client error tùy sender và configuration; không ép kết quả thành JAXB `SubmitOrderResponse(status="AUTH_FAILED")`.

~~~java
// Khung xử lý, không phải implementation hoàn chỉnh:
try {
    Object response = webServiceTemplate.marshalSendAndReceive(
        endpointUri, requestPayload, soapActionCallback);

    return mapSuccess(response);

} catch (SoapFaultClientException ex) {
    // SOAP Fault: đọc faultCode/reason/detail theo WSDL.
    throw mapSoapFault(ex);

} catch (WebServiceTransportException ex) {
    // HTTP 401/403/500, proxy hoặc transport failure:
    // phân loại an toàn theo provider và status nếu có.
    throw mapTransportError(ex);

} catch (WebServiceIOException ex) {
    // Socket/timeout: không nhất thiết biết server đã xử lý chưa.
    throw mapUnknownOutcome(ex);
}
~~~

`mapSuccess`/`mapSoapFault`/`mapTransportError`/`mapUnknownOutcome` là application methods giả định. `WebServiceTransportException` và `WebServiceIOException` thuộc package `org.springframework.ws.client`; `SoapFaultClientException` thuộc `org.springframework.ws.soap.client`. Cần kiểm loại exception thực tế của message sender, không coi `WebServiceIOException` đồng nghĩa luôn timeout; nó có thể bao nhiều lỗi I/O khác.

### 13.3. Không trả raw thông tin xác thực trong Fault

SOAP Fault/HTTP response không được chứa:

- Token compact/JWT, refresh token, username password, password hash.
- Private signing key, JWKS private material, client secret hoặc KeyStore password.
- Stack trace của `JwtDecoder`/`PasswordEncoder`, JDBC schema, internal hostname.
- Thông tin xác định “account tồn tại nhưng password sai” nếu chống username enumeration.
- Xác định chính xác quyền truy cập của người khác thông qua data existence.

Một public fault có thể mang `UNAUTHORIZED_OPERATION` hoặc `ACCESS_DENIED` và correlation ID; reason/detail được WSDL/XSD xác định và **không thay HTTP 401/403** nếu lỗi xảy ra trước khi SOAP được parse.

### 13.4. Đăng nhập thất bại khác token hết hạn

Một `BadCredentialsException` khi raw password sai thuộc **login flow**, thường có rate-limit và audit riêng. Một `JwtException` do token hết hạn thuộc **Resource Server flow**, thường cần client xin/refresh token qua Authorization Server theo OAuth2 policy. **SOAP server không nhận password để “gia hạn” token** trong lỗi 401 trừ khi contract đã thiết kế một chức năng identity riêng và được bảo vệ.

## 14. Threat model và những lỗ hổng thực tế

### 14.1. Đọc claims mà không verify JWT

~~~text
Attacker tạo token:
  header: {"alg":"none"}
  payload: {"sub":"admin","scope":"orders.cancel"}
  signature: none

Ứng dụng chỉ base64-decode và đọc scope → cấp quyền
~~~

Vấn đề là logic tự viết **không verify chữ ký/allowed algorithms**. Dùng `JwtDecoder` tin issuer, JWKS và validators; không cho client chọn validation key/algorithm. Test phải chứng minh token tự sửa claim bị reject.

### 14.2. Nhận JWT dành cho API khác

JWT có signature hợp lệ của issuer `identity.example.test` nhưng `aud=["urn:example:billing:api"]`. Nếu SOAP Orders API chỉ kiểm `iss` và `exp` mà không kiểm `aud`, một token dành cho Billing có thể bị chấp nhận tại Orders.

Đây là **cross-service token substitution**. Giải pháp: audience validation + quyền operation/resource. Spring Boot có cấu hình `spring.security.oauth2.resourceserver.jwt.audiences`; đừng chỉ dựa vào `scope` hoặc `sub`.

### 14.3. Chỉ đổi hash password rồi bỏ quên sessions

User đã đăng nhập và nhận JWT 15 phút; sau đó admin khóa account hoặc reset mật khẩu. Nếu Resource Server verify JWT cục bộ không truy revocation/user-state, token có thể tiếp tục sử dụng tới expiry. Nếu policy yêu cầu vô hiệu hóa ngay, cần introspection, denylist/token-version checks hoặc cơ chế revocation khác, đồng thời chấm dứt refresh/session. Không biến mọi request thành bcrypt check như một cách vá thiếu revocation policy.

### 14.4. Dùng password hash làm shared SOAP credential

Đối tác yêu cầu `UsernameToken PasswordDigest`. Lập trình viên xuất `{bcrypt}$...` từ database cho đối tác làm “mật khẩu tương đương”. Điều này biến stored password hash thành **credential có thể dùng lại**, làm tăng nguy cơ khi partner bị xâm nhập và tạo liên kết ngoài ý muốn giữa mật khẩu user với tích hợp B2B.

Cần credential kỹ thuật riêng, rotation hoặc đổi sang certificate/message signature/OAuth2 theo hợp đồng; không chia sẻ `password_hash` đăng nhập.

### 14.5. Tin buyerId trong SOAP Body dù token có tenant khác

SOAP request:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-TENANT-B</ord:orderId>
  <ord:buyerId>TENANT-B</ord:buyerId>
</ord:GetOrderRequest>
~~~

Bearer token thuộc `tenant-a`, nhưng application tìm theo buyerId trong Body mà không đối chiếu principal; đó là lỗi **broken object-level authorization (BOLA/IDOR)**. XSD hợp lệ/JWT signature hợp lệ **không giải quyết**; query và use case phải giới hạn dữ liệu theo tenant/entitlement của principal.

### 14.6. Lỗi dùng ThreadLocal/field chung

Một custom interceptor giữ `currentUser` trong field singleton:

~~~text
Thread A nhận token của user-A → currentUser=user-A
Thread B nhận token của user-B → currentUser=user-B
Thread A tiếp tục xử lý → thấy user-B
~~~

Điều này có thể dẫn tới **cross-tenant data leak**. Sử dụng `SecurityContextHolder` theo request/thread do Spring Security quản lý hoặc immutable caller context per call; không lưu principal per call trong mutable field của interceptor.

### 14.7. Callback token hoặc HTTP sender dùng chung sai tenant

Ở SOAP client, một `WebServiceTemplate` thường có thể dùng chung sau cấu hình, nhưng HTTP client custom không được giữ `Authorization: Bearer <token-current-tenant>` trong một mutable default header rồi thay nó trước từng call đồng thời. Nếu token khác nhau theo caller, gắn HTTP Authorization theo **per-request sender/request context an toàn luồng**, hoặc tách clients theo credential profile, không đổi shared config ở hot path.

### 14.8. SSRF và JWKS discovery

Không đọc `jku`/`x5u` trong unverified token rồi mở HTTP request để tải public key; attacker có thể điều hướng tới nội bộ hoặc JWKS tự điều khiển. Trusted IdP issuer/JWKS URLs phải được cấu hình/allowlist, có TLS/hostname validation và chính sách key rotation. Nếu một IdP cho phép `kid` tùy ý, decoder vẫn phải chọn key từ **trusted JWK set**, không từ arbitrary key injection.

### 14.9. Ghi log sai và token replay

Bearer token không nên xuất hiện trong proxy logs, error responses, tracing tags, email hoặc ảnh chụp màn hình. Bởi bearer token có thể dùng lại đến khi hết hiệu lực, việc lộ token **khác với** lộ mật khẩu hash database (password hash cần tấn công offline để đoán raw password, trong khi token đang hoạt động có thể sử dụng trực tiếp). Cả hai đều nhạy cảm nhưng phạm vi ứng phó khác nhau.

## 15. Ma trận kiểm thử và cách chứng minh hệ thống an toàn

### 15.1. Test cases cho Resource Server JWT

| Trường hợp | Kỳ vọng | Điều được kiểm |
| --- | --- | --- |
| JWT được signer tin cậy ký, `aud` đúng, còn hạn | SOAP đến endpoint | Happy path |
| Không có bearer token | HTTP 401 | Filter chạy trước SOAP |
| Token thiếu signature / `alg=none` | 401 | Không chấp nhận unsigned |
| Token bị sửa `scope` | 401 | Signature integrity |
| Token `iss` khác | 401 | Trusted issuer |
| Token `aud` khác | 401 | Cross-service substitution |
| Token `exp` quá hạn | 401 | Expiry |
| Token `nbf` trong tương lai | 401 | Not-before |
| JWKS `kid` chưa biết | Reject hoặc refresh trusted JWKS theo config | Key selection/rotation |
| Issuer/key rotation hợp lệ | Pass sau cache refresh theo policy | Availability/rotation |
| Role claim `admin` không được map | Không tự cấp ROLE_ADMIN | Authority conversion |
| Scope chỉ cho read, request CancelOrder | Deny | Operation-level authorization |
| Scope read nhưng tenant sai | Deny | Object-level authorization |
| JWT user token vs client credentials token | Map đúng subject/client identity | Principal semantics |
| JWT còn hạn nhưng đã revoke | Theo revocation strategy được công bố | Không suy local verify = real-time revoke |
| JWKS endpoint timeout | Theo cache/failure policy | Không tự trust unknown key |

### 15.2. Test cases cho opaque token và password login

| Trường hợp | Kỳ vọng |
| --- | --- |
| Opaque `active=true`, scope phù hợp | Được xác thực và xét quyền |
| Opaque `active=false` | 401 |
| Introspection client secret sai/endpoint lỗi | Infrastructure failure theo policy, không nhầm password login |
| Introspection data không có `sub` | Áp principal mapping policy |
| Hai users cùng raw password | Hash bcrypt khác do salt |
| `matches` với raw password đúng | `true` |
| `matches` với password sai | `false` |
| `encode(raw).equals(storedHash)` | Không dùng làm cách so |
| Hash cũ cần tăng work factor | `upgradeEncoding`/migration sau login đúng |
| User disabled/locked | Login bị từ chối |
| Đổi password thành công | Old password không login; token cũ theo policy revoke riêng |
| Không có account và sai password | Không để lộ username enumeration qua message/timing |
| Đăng nhập lặp nhiều lần | Rate-limit/credential stuffing controls |

### 15.3. Test Java cho PasswordEncoder

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

class PasswordStorageTest {

    private final PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

    @Test
    void hashIsSaltedAndMatchesRawPassword() {
        String raw = "temporary-test-passphrase";

        String first = encoder.encode(raw);
        String second = encoder.encode(raw);

        assertTrue(encoder.matches(raw, first));
        assertTrue(encoder.matches(raw, second));
        assertFalse(encoder.matches("different", first));
        assertNotEquals(first, second);
        assertTrue(first.startsWith("{bcrypt}"));
    }
}
~~~

Test này minh họa behavior của factory mà Spring Security docs mô tả (factory mapping mặc định cho encode tại phiên bản đang dùng). Không hardcode password thực hoặc dùng test value làm production credential. Việc hash khác nhau không thay việc cần đo work factor và theo dõi migration.

### 15.4. Test MockMvc không thay JWT cryptographic test

`spring-security-test` cung cấp `jwt()` RequestPostProcessor có thể đưa `JwtAuthenticationToken` giả lập vào test, giúp kiểm **authorization**:

~~~java
// Pseudocode: cần spring-security-test và MockMvc/SOAP fixture.
MvcResult result = mockMvc.perform(post("/ws/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("scope", "orders.read")
            .subject("user-42")))
        .contentType("text/xml")
        .content(validGetOrderSoapEnvelope))
    .andReturn();

// Assert theo điểm thực thi policy của test fixture:
// - GetOrder thành công có thể trả HTTP 200 + SOAP response.
// - Bị từ chối ở HTTP filter có thể trả 403.
// - Bị từ chối ở operation/resource service có thể là SOAP Fault.
~~~

**Cẩn thận:** `jwt()` trong security test thường **bỏ qua bước verify chữ ký/token thật** bằng cách setup authentication giả. Nó tốt để test policy; **không chứng minh** Resource Server kiểm `iss`/`aud`/`exp`/key rotation. Test token verification cần dùng JWT thực được ký bởi test keys + `JwtDecoder`, hoặc end-to-end HTTP requests qua đúng security filter chain với decoder giả lập theo policy rõ ràng.

Trong ví dụ `jwt()`, biến `result` chỉ minh họa cách gửi request với principal thử nghiệm; **chưa có assertion cụ thể** vì phải dựa vào fixture `GetOrder`, matcher và nơi thực thi policy. HTTP 403 chỉ phù hợp nếu HTTP filter thực sự từ chối; nếu filter chỉ yêu cầu authenticated mà service kiểm `SCOPE_orders.read`/quyền tài nguyên sau SOAP parsing, kết quả bị từ chối có thể là SOAP Fault. Hãy viết assertion riêng cho mỗi nhánh, thay vì áp HTTP 403 cho mọi authorization failure.

### 15.5. Spring-WS test không tự chạy Servlet Security Filter

`MockWebServiceClient` kiểm tra `@Endpoint`/SOAP payload trong ApplicationContext theo Spring-WS test framework, nhưng không nhất thiết đi qua **HTTP Servlet `SecurityFilterChain`**. `MockWebServiceServer` kiểm `WebServiceTemplate` phía client, cũng không tự xác nhận HTTP bearer auth ở server. Vì thế cần bổ sung **HTTP integration test thực** có Spring Security filter chain + MessageDispatcherServlet + issuer validation.

~~~mermaid
flowchart LR
    A["Real HTTP SOAP POST"] --> B["Spring Security Filter Chain"]
    B --> C["MessageDispatcherServlet"]
    C --> D["Spring-WS @Endpoint"]
    D --> E["@PreAuthorize + ownership policy"]
    E --> F["SOAP Response/Fault"]
~~~

Test phải xác minh cả **HTTP status trước SOAP** và **SOAP Fault sau khi vào application**. Một happy-path test bằng MockWebServiceClient có thể pass dù production `/ws/**` đang bị cấu hình anonymous-access nhầm.

### 15.6. SOAP/WS-Security và concurrency tests

- Gửi WS-Security UsernameToken `PasswordText` sai/đúng; bảo đảm password không log.
- Với PasswordDigest, test `Nonce`, `Created`, freshness, replay cache và shared-secret policy; **không dùng bcrypt hash DB như password equivalent**.
- Sửa XML Body đã ký, thiếu signature hoặc cert không trusted: không vào business service.
- Token JWT hợp lệ nhưng `wsse:UsernameToken` thuộc user khác: policy phải reject conflict hoặc chỉ accept cơ chế được chọn.
- Gửi nhiều concurrent requests với hai bearer tokens/tenants khác nhau: không trộn `SecurityContext` hay HTTP headers.
- Retry SOAP command sau response lost: giữ business idempotency key; đổi password không thay transaction result.
- Test client Java/.NET: token thường nằm HTTP header; SOAP WS-Security Header dùng đúng profile nếu cần.


## 16. Thiết kế tổng thể và checklist production

### 16.1. Chọn đúng cơ chế theo người giữ credential

~~~mermaid
flowchart TD
    A{"SOAP caller mang credential gì?"}
    A -- "OAuth2 Bearer JWT" --> B["Spring Security Resource Server JWT"]
    A -- "Opaque Bearer token" --> C["OAuth2 Introspection"]
    A -- "WS-Security UsernameToken" --> D["WSS4J + callback/password policy"]
    A -- "X.509 signed SOAP" --> E["WSS4J Crypto/trust + signed coverage"]
    A -- "mTLS certificate" --> F["TLS + partner identity mapping"]
    A -- "User raw password đăng nhập" --> G["DaoAuthenticationProvider + PasswordEncoder"]
    B --> H["Trusted Authentication/principal"]
    C --> H
    D --> H
    E --> H
    F --> H
    G --> I["Session/token issuance theo IdP/login design"]
    H --> J["Authorize operation + buyer/tenant resource"]
    J --> K["Spring-WS @Endpoint / application service"]
~~~

Sơ đồ mô tả **các con đường lựa chọn hoặc kết hợp có kiểm soát**, không hàm ý cứ nhận một SOAP Header tùy ý là Spring Security tự tạo principal. `@Endpoint` chỉ được dùng sau khi identity evidence được xác minh theo pipeline thực tế.

### 16.2. Ba mô hình tích hợp cụ thể

**Mô hình A — API SOAP cho đối tác dùng OAuth2:** Đối tác lấy access token qua Authorization Server, gửi `Authorization: Bearer` qua HTTPS vào `/ws/**`, Resource Server validate JWT/opaque và service kiểm scope/entitlement. SOAP service **không quản lý mật khẩu của đối tác**.

**Mô hình B — Ứng dụng tự có tài khoản người dùng:** Một login service quản lý `users.password_hash` và `DaoAuthenticationProvider`, xác thực lúc login (có thể qua IdP/MFA), rồi cấp session hoặc gọi hệ thống cấp token. SOAP API tiêu thụ access tokens và **không cần bcrypt match trong mỗi request**.

**Mô hình C — Legacy WS-Security B2B:** Đối tác bắt buộc `UsernameToken` hoặc X.509 Signature trên SOAP Header. WSS4J xác minh theo profile; signer/username được map sang trusted principal. Không sử dụng hash mật khẩu của người dùng làm shared secret. Nếu cần cả bearer và WS-Security signature, document identity consistency policy và test conflict.

### 16.3. Hash của refresh token khác hash của password

Có những hệ thống **lưu hash của opaque refresh token hoặc API key** trong database để không giữ credential dạng rõ. Điều này **không biến token thành password**:

- Refresh token/API key nên là **random high-entropy value** do hệ thống tạo. Có thể lưu một token fingerprint/hash cryptographic hoặc HMAC có keyed secret để so/revoke/tra cứu; cần chống leak, kiểm constant-time khi so secret, TTL, rotation và token family/reuse detection theo policy.
- Password do người dùng nhớ thường **entropy thấp**, nên phải dùng password KDF chậm có salt/work factor; dùng SHA-256(password) đơn giản là không đủ.
- Access JWT đã ký thường được Resource Server **verify cryptographically** mà không lưu bản sao vào database; denylist/token-version là một cơ chế thêm.
- Nếu token được lưu trong database để audit, **không lưu raw bearer token** và không coi password hashing là biện pháp duy nhất thay được mọi token policy.

### 16.4. Checklist security review trước vận hành

1. **Ranh giới vai trò:** SOAP app là Resource Server, login service, Authorization Server hay có nhiều vai trò? Có đang vô tình yêu cầu DB password từ Resource Server?
2. **JWT issuer:** `iss` từ IdP đáng tin và JWKS URL được cấu hình/allowlist; không theo `jku` của token chưa verify?
3. **JWT target:** `aud`, `exp`, `nbf` và token type/use được xác minh đúng yêu cầu SOAP API?
4. **Claim mapping:** `scope`/`scp` được map thành `SCOPE_...` hoặc authorities khác theo policy, không tin free-form role?
5. **Opaque introspection:** TLS, client credentials, timeout, caching và revocation semantics được xác định?
6. **Password DB:** raw password không lưu; `DelegatingPasswordEncoder`/work factor và migration/reset đã thiết kế?
7. **Login security:** account state, rate-limit, MFA, chống username enumeration, session/refresh token revocation?
8. **HTTP SOAP:** security matcher khớp servlet mapping, không cho unauthorized GET WSDL/POST lọt qua chain khác?
9. **CSRF:** chỉ disable nơi thực sự stateless bearer-only, không mở toàn bộ web app dùng cookie?
10. **SOAP authorization:** từng operation, buyer/tenant/order ID được kiểm ngoài token verification?
11. **WS-Security:** UsernameToken/X.509/Signature có callback, trust, signed coverage, Timestamp/replay theo contract?
12. **Identity collision:** nếu đồng thời có HTTP bearer và WS-Security principal, policy quyết định bắt buộc/cách xử lý mâu thuẫn?
13. **TLS/mTLS:** hostname verification, client cert/trust, rotation và secret management?
14. **Fault:** HTTP 401/403, SOAP Fault và TLS failure được phân biệt, không lộ credentials?
15. **Concurrency:** không có mutable principal/token trong singleton endpoint/interceptor; async job chỉ mang identity metadata cần thiết?
16. **Testing:** mock authorization, signed JWT end-to-end, opaque introspection, real HTTP Servlet filter, SOAP endpoint security và Java/.NET interop?
17. **Observability:** log/metrics không giữ raw token/hash/password; correlation ID không được xem là chứng cứ xác thực?
18. **Incident response:** biết cách revoke sessions/refresh tokens, thay keys, chặn JWT còn hạn và khóa account theo mức độ sự cố?

### 16.5. Cây quyết định chẩn đoán lỗi xác thực

~~~text
Không gọi được SOAP service?
  │
  ├── TLS handshake fail
  │     └── Kiểm cert/truststore/mTLS; chưa có SOAP Envelope
  │
  ├── HTTP 401
  │     └── Kiểm bearer, JWT signature, iss, aud, exp, introspection
  │
  ├── HTTP 403
  │     └── Kiểm HTTP authority, CSRF/policy và filter chain
  │
  ├── SOAP WS-Security Fault
  │     └── Kiểm UsernameToken/X.509, signature, trust, Timestamp
  │
  ├── SOAP business AccessDenied Fault
  │     └── Kiểm operation/tenant/resource authorization
  │
  └── SOAP Response
        └── Kiểm business result, idempotency, contract
~~~

Không thử sửa bằng cách tắt CSRF toàn ứng dụng, tắt JWT audience validation hoặc tắt WS-Security signature để “qua test”. Hãy xác định lỗi thuộc **lớp nào**, sau đó sửa cấu hình/giao thức chính xác.


## 17. Bài tập thực hành và tài liệu tham khảo

### 17.1. Bài tập tự kiểm tra

**Bài 1.** Một SOAP Resource Server nhận JWT có `sub=user-42` và `scope=orders.read`. Nó có cần truy bảng `users.password_hash` để xác minh token không? Giải thích vai trò của `JwtDecoder`.

**Bài 2.** Lập trình viên decode payload JWT bằng Base64URL rồi tin `roles=["ADMIN"]`. Có gì sai và cần kiểm những trường nào ngoài signature?

**Bài 3.** Hai users đặt cùng mật khẩu. Vì sao `DelegatingPasswordEncoder.encode(...)` thường tạo hai chuỗi bcrypt khác nhau? So bằng `matches(...)` thế nào?

**Bài 4.** Một JWT của Billing API có signature/issuer hợp lệ nhưng `aud` không chứa Orders SOAP API. Resource Server phải làm gì?

**Bài 5.** Người dùng đổi password và app cập nhật `password_hash`. JWT đã phát 10 phút trước có tự mất hiệu lực không? Nêu ít nhất hai chiến lược revocation.

**Bài 6.** Opaque token bị thu hồi giữa hai request. Introspection giúp kiểm trạng thái ra sao và cache introspection gây trade-off gì?

**Bài 7.** WSDL có ba operation chung `/ws/orders`. Vì sao `requestMatchers("/ws/orders").authenticated()` không đủ để phân quyền `CancelOrder`?

**Bài 8.** Token có `SCOPE_orders.read` và Body request chứa `buyerId=tenant-b` nhưng principal thuộc tenant-a. Cần kiểm gì trước khi gọi repository?

**Bài 9.** Phân biệt HTTP `Authorization: Bearer` với SOAP `wsse:UsernameToken`. Spring Security Resource Server có tự xác minh UsernameToken không?

**Bài 10.** Partner gửi `PasswordDigest` từ raw password và nonce/timestamp; server chỉ lưu hash bcrypt của raw password. Vì sao không thể tái tạo digest từ hash? Có nên xuất database hash làm shared secret không?

**Bài 11.** Một chương trình dùng SOAP XML Signature với X.509 hợp lệ. Điều gì còn thiếu để biết signer có quyền truy cập đơn hàng?

**Bài 12.** Bạn thấy HTTP 401 không có SOAP Envelope. Nên sửa `SoapFaultMappingExceptionResolver` hay kiểm security filter/issuer?

**Bài 13.** Một Servlet SOAP app có form login cho người dùng trên URL khác. Vì sao không tắt CSRF toàn bộ chỉ để dễ gọi stateless SOAP API?

**Bài 14.** Viết unit tests cho `PasswordEncoder` và một end-to-end test với JWT signature thật. Vì sao `MockMvc.jwt()` test không đủ để chứng minh signature verification?

**Bài 15.** Một request đồng thời từ tenant A/B bị custom interceptor lưu token vào field `currentToken`. Mô tả rủi ro và cách thiết kế per-call.

**Bài 16.** Một refresh token ngẫu nhiên 256-bit được lưu dưới dạng SHA-256 fingerprint để lookup/revoke. Khác gì với việc lưu `SHA-256(userPassword)`?

**Bài 17.** Thiết kế test integration đi qua **real HTTP SecurityFilterChain + Spring-WS dispatcher**, kiểm 401 khi token sai, SOAP Fault khi buyer không có quyền và success khi đủ quyền.

### 17.2. Gợi ý trả lời cốt lõi

- **1–2:** JWT xác minh theo key/issuer/claims; Base64URL parse chưa phải verify.
- **3:** BCrypt có random salt; dùng `matches(raw, stored)` chứ không so hai kết quả encode.
- **4–6:** Audience đúng dịch vụ; đổi password và revocation token là hai lifecycle khác nhau; introspection có trade-off latency/cache.
- **7–8:** Một SOAP URL có thể nhiều operations; kiểm scope và quyền trên tài nguyên/tenant từ principal.
- **9–10:** HTTP OAuth2 token và SOAP UsernameToken thuộc hai parser/verifier; legacy UsernameToken digest cần shared secret tương ứng, không suy ngược bcrypt hash.
- **11–13:** X.509 trust không tự cấp authorization; HTTP filter có thể từ chối trước SOAP; CSRF policy phải xét loại client/session.
- **14–17:** Cần test security thật, không chỉ mock; tránh rò token giữa threads; hash token entropy cao khác password KDF; so cả HTTP status lẫn SOAP Fault.

## Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — `JwtDecoder`, issuer/JWKS, timestamps, audience, claims và scope mapping.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html) — introspection, `active`, principal và token revocation.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html) — `PasswordEncoder`, adaptive one-way hashing, DelegatingPasswordEncoder, BCrypt, work factor.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html) — `UserDetailsService`, `PasswordEncoder` và username/password authentication.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html) — `@EnableMethodSecurity`, `@PreAuthorize`, authorization ở service layer.
- [Spring Security — Testing OAuth 2.0 Resource Servers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html) — `jwt()` test helper và các giới hạn của security mock.
- [Spring Web Services Reference 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) — `@Endpoint`, SOAP interceptors, WS-Security, `WebServiceTemplate`.
- [OASIS — WS-Security UsernameToken Profile Version 1.1.1](https://docs.oasis-open.org/wss-m/wss/v1.1.1/os/wss-UsernameTokenProfile-v1.1.1-os.html) — `PasswordText`, `PasswordDigest`, `Nonce`, `Created` và replay.
- [IETF RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519) — JWT claims, issuer, audience, expiry.
- [IETF RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662) — opaque introspection và `active`.
- [IETF RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750) — HTTP Authorization Bearer, 401/403 và bearer token handling.

**Ghi nhớ:** **Xác minh token** là kiểm một credential do issuer cấp trên đường gọi dịch vụ, dùng `JwtDecoder`/public JWKS hoặc introspection. **Lưu mật khẩu** là bảo vệ credential dài hạn ở hệ thống đăng nhập bằng `PasswordEncoder` một chiều có salt/work factor, rồi kiểm `matches` khi cần. Với Spring-WS, OAuth2 Bearer ở HTTP Filter, WS-Security UsernameToken/X.509 ở SOAP Header và quyền operation/resource ở application layer là **ba ranh giới riêng**; không dùng password hash để verify JWT, không chia sẻ hash user làm SOAP shared secret, và luôn kiểm cả lỗi HTTP lẫn SOAP Fault trên tích hợp thực.
