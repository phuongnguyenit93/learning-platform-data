# Opaque token và kiểm tra hiệu lực qua introspection

## 1. Mục tiêu bài học

Bài thuộc nhóm **Token và giao thức** của **Spring Security - fundamentals**. Khi một API nhận `Authorization: Bearer ...`, nó phải xác định token có còn hiệu lực, được phát cho đúng tài nguyên và có quyền thực hiện yêu cầu hay không. Một cách kiểm tra là **OAuth 2.0 Token Introspection**: Resource Server hỏi Authorization Server về trạng thái và thuộc tính của token.

Sau bài này, bạn có thể:

1. Giải thích **opaque access token** là gì, vì sao Resource Server không tự giải mã nó như JWT, và tại sao không thể suy luận quyền từ chuỗi token nhìn thấy.
2. Trình bày vai trò **Client**, **Authorization Server (AS)**, **Resource Server (RS)** và endpoint introspection theo **RFC 7662**.
3. Phân biệt `active: true`, `active: false`, lỗi xác thực của RS khi gọi introspection, lỗi scope và lỗi dịch vụ introspection.
4. Hiểu request `POST` form-encoded tới introspection endpoint, cách RS xác thực với AS, và các thuộc tính `scope`, `sub`, `client_id`, `aud`, `iss`, `exp`.
5. Cấu hình Spring Boot/Spring Security Servlet làm OAuth2 Resource Server dùng opaque-token introspection, ánh xạ scope thành `SCOPE_...` và bảo vệ endpoint.
6. Chạy ví dụ Java 17 + Spring Boot 3.5.12, kiểm tra HTTP 200/401/403; phân biệt kiểm thử thực qua HTTP với việc chỉ mock một introspector.
7. Đánh giá revocation, caching, độ trễ, tính sẵn sàng, TLS, token leakage, audience validation và điểm khác nhau giữa opaque introspection với JWT local verification.

**Phạm vi:** ví dụ runnable dùng **Spring MVC/Servlet** (`HttpSecurity`, `SecurityFilterChain`, `OpaqueTokenIntrospector`). Spring WebFlux có `ReactiveOpaqueTokenIntrospector`, `ServerHttpSecurity` và security context reactive riêng. Nội dung này không yêu cầu bạn tự viết một Authorization Server production.

## 2. Opaque token là gì?

Một **opaque token** là giá trị mà bên nhận không được giả định có thể đọc trực tiếp thành thông tin user/quyền. Nó có thể là chuỗi ngẫu nhiên, chuỗi tham chiếu tới bản ghi của Authorization Server hoặc một định dạng tùy ý mà Resource Server không biết cấu trúc. Ví dụ minh họa:

```text
Authorization: Bearer 7CnV0aQ9w1...random...
```

Dấu ba chấm chỉ minh họa, không phải token thực và không nên dùng chuỗi này để bảo vệ hệ thống.

**Opaque là góc nhìn của Resource Server:** ứng dụng API không đọc token để rút ra `sub`, `scope`, `exp`. Nó gửi token cho dịch vụ đáng tin cậy và nhận thông tin đã được phía phát hành xác nhận. Có thể có token nhìn giống JWT nhưng vẫn được cấu hình **xác minh qua introspection**; phương pháp xác minh và định dạng token là hai quyết định riêng.

### Ai làm gì?

| Thành phần | Trách nhiệm |
| --- | --- |
| **Client** (web/mobile/service) | Có access token hợp lệ và gửi nó trong request tới API |
| **Authorization Server / IdP** | Phát hành, quản lý hiệu lực/thu hồi token; cung cấp introspection endpoint |
| **Resource Server** | Nhận bearer token, xác thực nó qua introspection, xét scope và quyền trên endpoint |
| **Introspection endpoint** | Trả về `active` và các thuộc tính token trong phạm vi RS được phép biết |
| **Người dùng / subject** | Có thể là chủ thể được token đại diện, nhưng OAuth2 client-credentials token có thể không đại diện một user cụ thể |

Opaque token khác **session ID** theo ngữ cảnh sử dụng: session ID thường trỏ tới `HttpSession` của ứng dụng web; opaque OAuth2 access token thường được RS kiểm tra qua AS/introspection theo OAuth2. Cả hai có thể là chuỗi khó đoán, nhưng **protocol, đối tượng tin cậy, scope và cơ chế quản lý** không giống nhau.

**Bearer token là bí mật:** bất kỳ người nào có token hợp lệ có thể cố dùng nó trong phạm vi token cho phép. Hãy coi token như credential, không log, không nhúng vào URL, không gửi cho dịch vụ không tin cậy.

## 3. Luồng kiểm tra hiệu lực qua RFC 7662

Một request bảo vệ tài nguyên đi theo đường:

```text
Client                         Resource Server                Authorization Server
  │                                  │                                │
  │ GET /api/orders                  │                                │
  │ Authorization: Bearer T          │                                │
  ├─────────────────────────────────>│                                │
  │                                  │ POST /introspect               │
  │                                  │ Authorization: Basic RS creds  │
  │                                  │ Content-Type: application/     │
  │                                  │   x-www-form-urlencoded        │
  │                                  │ token=T                        │
  │                                  ├───────────────────────────────>│
  │                                  │                                │ kiểm tra T
  │                                  │        HTTP 200                │ trạng thái,
  │                                  │ {active:true, scope, sub,...}  │ quyền và policy
  │                                  │<───────────────────────────────┤
  │                                  │                                │
  │                                  │ tạo Authentication của request │
  │                                  │ kiểm tra SCOPE_orders.read     │
  │                                  │                                │
  │  HTTP 200 (nếu được phép)         │                                │
  │<─────────────────────────────────┤                                │
```

**Điểm quan trọng:**
- Client gửi token cho **Resource Server** trong `Authorization: Bearer ...`.
- Resource Server gửi token tới **introspection endpoint** bằng một request riêng. RS phải được AS tin cậy và xác thực theo chính sách; ví dụ phổ biến là HTTP Basic với **client ID/secret của Resource Server**. Đây **không** phải password của người dùng.
- AS trả JSON có `active`. RS biến kết quả được chấp nhận thành `Authentication` của **request đang xử lý**, rồi thực hiện authorization như `hasAuthority("SCOPE_orders.read")`.
- Introspection là bước **xác thực hiệu lực token**. `active: true` không tự cho phép mọi API; ứng dụng vẫn cần kiểm tra scope, audience/resource, tenant hoặc quyền nghiệp vụ.
- Không được cấu hình “introspection lỗi thì cho qua” (*fail open*). Nếu RS không thể xác minh token, không được mặc định coi token đó hợp lệ.

### Vì sao cần endpoint riêng?

RS thường không có thông tin để tự xác minh opaque token. Chỉ AS hoặc một dịch vụ xác thực được AS tin cậy mới có thể biết token được phát hành, đã hết hạn, bị thu hồi hay bị chặn bởi policy nào. RFC 7662 tạo cách hỏi chuẩn: **token đang active không, và thuộc tính nào được phép công bố cho RS này?**

## 4. Request introspection: HTTP và quyền của bên gọi

Ví dụ giao tiếp **giữa Resource Server và Authorization Server**, không phải giữa browser và API:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.test
Authorization: Basic <base64-resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>&token_type_hint=access_token
```

Đây là **mẫu giao thức**, các phần trong dấu `<...>` là ký hiệu mô tả, không phải credentials thật. `token_type_hint` là trường **tùy chọn**, gợi ý để AS tối ưu tra cứu; không tự xác nhận token là access token.

Các yêu cầu cần hiểu đúng:

1. RFC 7662 dùng **HTTP POST** với tham số `token` trong body dạng `application/x-www-form-urlencoded`. Không đặt access token vào URL query vì URL thường bị log hoặc lưu vào lịch sử/proxy.
2. Introspection endpoint yêu cầu **TLS và xác minh chứng thư** trong triển khai thật. Ví dụ `http://127.0.0.1` bên dưới chỉ dùng cục bộ để dạy học.
3. RS phải chứng minh được phép truy vấn endpoint, thường qua client credentials. Một AS có thể áp dụng các cơ chế client authentication khác theo policy.
4. AS có quyền giới hạn RS chỉ introspect những token mà RS được phép biết, giúp tránh dịch vụ tùy ý đọc tình trạng token.
5. Phản hồi introspection có thể chứa dữ liệu nhạy cảm (`sub`, username, scopes, tenant...). RS phải giữ riêng tư, tránh đưa toàn bộ response về client hoặc ghi log.
6. 401 ở **introspection endpoint** khi **credentials của RS không hợp lệ** khác với 401 mà **API trả về cho Client** khi bearer token không hợp lệ.

### Hai trường hợp thường bị nhầm

**Token không còn active**, nhưng RS được phép gọi endpoint:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
```

Đây là **kết quả hợp lệ của cuộc gọi introspection**, không phải lỗi HTTP của introspection service. AS không nên kèm `reason=revoked`, `reason=not_found` hoặc thông tin khác cho token không active, vì như vậy có thể làm lộ trạng thái token. RFC 7662 khuyến nghị phản hồi tối giản.

**RS gọi introspection bằng client credentials sai:**

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"error":"invalid_client"}
```

Đây là **lỗi xác thực bên gọi introspection**, không có nghĩa token đích “inactive”. RS phải xử lý như một lỗi không xác minh được, không mặc định cho phép truy cập.

### Introspection endpoint có công khai không?

“Public về mặt URL” không đồng nghĩa công khai dữ liệu. Bên gọi phải được **xác thực và cấp quyền**, không được cho bất kỳ client Internet nào gửi token để dò metadata. Một introspection response có `active:true` vẫn không nên được hiển thị cho end-user chưa được xác thực bằng một endpoint debug.

## 5. Ý nghĩa các trường trong JSON trả về

Theo RFC 7662, `active` là trường cốt lõi. Những trường khác tùy token, authorization server và quyền của RS.

**Ví dụ active token:**

```json
{
  "active": true,
  "sub": "alice",
  "client_id": "orders-web",
  "scope": "orders.read profile.read",
  "token_type": "Bearer",
  "aud": ["orders-api"],
  "iss": "https://idp.example.test",
  "exp": 1910000000,
  "iat": 1909996400
}
```

Các số `exp`/`iat` là ví dụ định dạng timestamp Unix giây; **không** hàm ý token trên là token thật hoặc còn hạn vào lúc bạn đọc. Ý nghĩa:

| Thuộc tính | Ý nghĩa | Kiểm tra cần quan tâm |
| --- | --- | --- |
| `active` | AS xác nhận token còn được chấp nhận theo policy của AS | Nếu thiếu/false/không hợp lệ thì không cấp quyền |
| `sub` | Subject mà token đại diện, nếu có | Không luôn là username hiển thị; client-credentials token có thể khác |
| `client_id` | Client được cấp token | Có phải client hợp lệ cho use case này? |
| `scope` | Các scopes được cấp, thường là chuỗi cách nhau bằng khoảng trắng | Map thành authorities, kiểm tra least privilege |
| `token_type` | Loại token (thường Bearer) | Không thay thế quyết định validation |
| `aud` | Audience/resource dự kiến | Không chấp nhận token phát cho API khác |
| `iss` | Bên phát hành token | Có thuộc trusted issuer/AS theo policy không? |
| `exp` | Hết hạn theo epoch seconds | Kết hợp với `active` và chính sách hết hạn của AS |
| `iat` | Thời điểm phát hành | Dùng nếu nghiệp vụ/policy cần kiểm tra tuổi token |
| `nbf` | Không có hiệu lực trước một thời điểm | Cần policy phù hợp nếu AS trả |

**Không suy diễn:** `active: true` có nghĩa AS xác nhận token active theo policy của AS và RS được phép hỏi. Nó **không tự chứng minh** token có quyền `orders.read`, có đúng `aud` cho API này, hay có quyền đọc đơn hàng ID 123 của tenant hiện tại.

**Audience đặc biệt quan trọng.** Một access token cho API `billing-api` không nên được chấp nhận cho `orders-api` chỉ vì cả hai dùng chung AS. Spring Security mặc định có thể ánh xạ scope và dựa vào AS báo `active`; các quy tắc kiểm tra audience/issuer/tenant đặc thù **phải được thiết kế và kiểm chứng rõ ràng**, không giả định mọi trường introspection đã được kiểm tra theo ứng dụng.

### Active false có thể do nhiều lý do

- Token chưa từng được phát hành hoặc chuỗi ngẫu nhiên.
- Token đã hết hạn.
- Token bị thu hồi/revoked, phiên hoặc consent đã bị vô hiệu theo policy.
- Token không dành cho RS đang introspect và AS không muốn tiết lộ.
- Token không còn hợp lệ do chính sách khác của AS.

Vì những trường hợp này đều có thể là `{"active":false}`, RS **không được đoán nguyên nhân cụ thể** chỉ từ JSON đó.

## 6. Opaque introspection và JWT khác nhau ở điểm nào?

| Tiêu chí | Opaque token + introspection | JWT + local validation |
| --- | --- | --- |
| Token được đọc như thế nào? | RS không giả định tự đọc; hỏi AS | RS giải mã claims và xác minh chữ ký/validity tại chỗ |
| Trạng thái tại thời điểm request | Có thể biết revocation nhanh theo AS nếu introspect mỗi lần | JWT tự chứa thường còn được chấp nhận tới `exp` nếu không có cơ chế revoke khác |
| Độ trễ mỗi request | Có thể thêm network round-trip, TLS, AS processing | Thường không cần gọi AS ở mỗi request |
| Tính sẵn sàng | Phụ thuộc introspection endpoint và mạng (nếu không cache) | Phụ thuộc keys/JWK refresh và policy nhưng xử lý thường local |
| Quyền/claims | Nhận từ AS qua response và kiểm soát RS | Claims nằm trong token, không tự cập nhật trước khi hết hạn |
| Mức lộ dữ liệu từ token | Token opaque không tự bộc lộ claims cho bên cầm token | JWT payload thường có thể đọc được dù có chữ ký |
| Caching | Có thể cache introspection với trade-off stale state | Có thể cache keys/validation metadata |
| Phù hợp | Cần revoke/kiểm soát tập trung, token nhỏ, metadata động | Muốn xác minh local và giảm phụ thuộc gọi AS |

**Không đánh đồng:** dùng JWT vẫn có thể gọi introspection để kiểm tra trạng thái/revocation; Spring Security opaque-token support không đòi chuỗi token “không phải JWT”. Ngược lại, opaque token không tự đảm bảo revoke nhanh nếu bạn cache kết quả quá lâu.

### Chữ ký JWT không đồng nghĩa token còn được phép

Một JWT hợp lệ về chữ ký có thể bị thu hồi theo chính sách của AS trước `exp`. Nếu RS chỉ làm local verification, nó không tự biết revocation đó trừ khi được thiết kế thêm. Introspection cho RS cơ hội hỏi AS về trạng thái hiện tại, nhưng đổi lại phụ thuộc network/availability và có thể phát sinh độ trễ.

## 7. Spring Security xử lý opaque bearer token ra sao?

Với Spring Boot Servlet, các thành phần quan trọng:

- `BearerTokenAuthenticationFilter`: lấy bearer token từ request theo cơ chế phù hợp.
- `OpaqueTokenAuthenticationProvider`: sử dụng `OpaqueTokenIntrospector` để xác minh token.
- `SpringOpaqueTokenIntrospector` (hoặc biến thể dùng `RestClient`/custom): gọi introspection endpoint bằng credentials của RS.
- `OAuth2AuthenticatedPrincipal`: chứa attributes và granted authorities sau introspection.
- `BearerTokenAuthentication`: Authentication tương ứng bearer token đã được chấp nhận.
- `AuthorizationFilter` cùng `authorizeHttpRequests`: kiểm tra quyền sau authentication.

Luồng khái quát:

```text
GET /api/orders
Authorization: Bearer read-token
       │
       ▼
BearerTokenAuthenticationFilter
       │ lấy token
       ▼
OpaqueTokenIntrospector.introspect("read-token")
       │ POST /introspect
       │ kiểm tra active + metadata
       ▼
OAuth2AuthenticatedPrincipal
       │ sub=alice, scope=orders.read
       ▼
BearerTokenAuthentication
       │ authorities=[SCOPE_orders.read]
       ▼
authorizeHttpRequests
       ├─ có SCOPE_orders.read → cho qua
       └─ thiếu scope → từ chối
```

### Map scope thành authority

Khi introspection trả `"scope": "orders.read orders.write"`, Spring Security mặc định có thể ánh xạ thành:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Do đó, rule phù hợp là:

```java
.requestMatchers("/api/orders").hasAuthority("SCOPE_orders.read")
```

**Đây là fragment**, cần nằm trong `authorizeHttpRequests`. `hasRole("ADMIN")` **không tự tương đương** `hasAuthority("SCOPE_orders.read")`. Role và OAuth2 scope là hai hệ quyền; có thể tích hợp nhưng phải có ánh xạ minh bạch.

### Phân biệt 401 và 403 cho Client gọi API

| Request | Kết quả điển hình | Lý do |
| --- | --- | --- |
| Không gửi Bearer | 401 | Chưa được xác thực tại API |
| Token ngẫu nhiên, introspection `active:false` | 401 | Bearer token không hợp lệ |
| Token đã revoke/expired, AS trả inactive | 401 | Authentication không được chấp nhận |
| Token active, thiếu `orders.read` | 403 | Đã xác thực nhưng không có authority |
| Token active, có `orders.read` | 200 | Qua authorization của endpoint |
| Introspection service down/timeout | Không được phép truy cập; mã cuối có thể tùy cấu hình/error handling | Không được fail open |
| Client credentials của RS sai | Introspection endpoint 401; API không được coi token hợp lệ | Lỗi cấu hình/tin cậy giữa các dịch vụ |

**Không quy định cứng 503/401 cho mọi lỗi introspection network.** Spring Security có cách phân loại exceptions và custom handlers khác nhau; kiểm tra kết quả thực ở version đang triển khai. Điều bắt buộc là **không cho phép request nhạy cảm chỉ vì AS đang không phản hồi**.

## 8. Cấu hình Spring Boot tối thiểu với AS thật

Nếu có Authorization Server thực sự cung cấp endpoint introspection, cấu hình production điển hình có ba properties:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://idp.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=orders-resource-server
spring.security.oauth2.resourceserver.opaquetoken.client-secret=REPLACE_VIA_SECRET_MANAGER
```

Các host/giá trị ở đây **chỉ minh họa cách cấu hình**, không phải endpoint/certificate/credentials thực; không lưu client secret thật trong source control. Tại production, cung cấp client secret qua secret manager hoặc biến môi trường thích hợp và cấu hình theo môi trường, bật TLS, kiểm soát DNS/proxy và tin cậy CA.

Cấu hình ứng dụng Java:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders").hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults()))
        .build();
}
```

Đây là **fragment**: cần `@Configuration`, `@Bean`, đúng imports, dependencies Resource Server và các chính sách cho các endpoint khác. Khi khai báo custom `SecurityFilterChain`, Spring Boot không tự tạo chain default cho bạn; phải xác định các route public/protected/fallback phù hợp.

### Dependencies

Với Spring Boot, dùng starter:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
```

Starter kéo các thư viện resource-server cần thiết. Không cần buộc ứng dụng trở thành OAuth2 Client chỉ để nhận bearer token. `spring-boot-starter-oauth2-client` phục vụ các flow khác (login/authorized clients), không phải yêu cầu tối thiểu của một Resource Server kiểm tra opaque token.

### Cần thiết kế thêm gì ngoài ba properties?

- API có bắt buộc `aud=orders-api`, issuer nào, client nào, tenant nào?
- AS bảo đảm response `active:true` có nghĩa token chưa expired, chưa revoked và đúng mục đích với RS này như thế nào?
- Scope từ AS được cấp theo phương pháp nào? Có cần mapping roles/groups/permissions khác không?
- Chạy AS qua TLS và xác thực RS bằng credentials bảo mật ra sao?
- Timeout, retry, circuit breaker, AS overload và chính sách fail-closed?
- Có cache introspection không? Cache trong bao lâu? Revoke latency chấp nhận được?
- Nếu API dùng cả browser cookie và bearer token, CSRF threat model sẽ ra sao?
- Log, metrics và audit phải tránh lộ token đầy đủ thế nào?

## 9. Ví dụ Java 17 runnable với introspection HTTP thật trong môi trường local

Ví dụ cung cấp **một ứng dụng Spring Boot 3.5.12** để người học có thể chạy ngay mà không cần IdP riêng. Bên trong app có **endpoint giả lập AS** tên `/demo-idp/introspect`, được RS gọi bằng HTTP trên loopback. Các token demo là chuỗi cố định để kiểm chứng, không có giá trị bảo mật.

**CẢNH BÁO PHẠM VI:** trong hệ thống thật, introspection endpoint nằm ở **Authorization Server riêng**, được bảo vệ bởi TLS, cơ chế client authentication mạnh và chính sách phân quyền introspection. Không đưa endpoint demo, token demo hay client secret demo ra Internet. App mẫu bind vào `127.0.0.1` và chỉ để học.

Kịch bản:

| Token minh họa | Phản hồi introspection | Danh tính/scopes | API dự kiến |
| --- | --- | --- | --- |
| `read-token` | `active:true` | `sub=alice`, `orders.read` | `GET /api/orders` → 200 |
| `profile-token` | `active:true` | `sub=bob`, `profile.read` | `GET /api/orders` → 403; `/api/me` → 200 |
| `inactive-token` | `active:false` | Không trả metadata | API → 401 |
| `expired-token` | `active:false` | Không trả metadata | API → 401 |
| `revoked-token` | `active:false` | Không trả metadata | API → 401 |
| Không token | Không gọi introspection | — | API → 401 |

Trong demo, AS stub **được lập trình trả inactive** cho các tên token tương ứng; đây không phải bộ mô phỏng đồng hồ hết hạn hay quy trình cấp/phát/thu hồi token thật. Muốn kiểm chứng revocation qua thời gian cần IdP/store thực với token chuyển từ active sang inactive.

### 9.1. Cấu trúc thư mục

```text
opaque-introspection-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/opaque/
    │   │   ├── OpaqueDemoApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   ├── DemoIntrospectionController.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/opaque/
            └── OpaqueTokenIntegrationTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'opaque-introspection-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.5.x cần Java 17+ và Gradle version tương thích. Dùng Gradle 8.4+ hoặc Gradle Wrapper được thiết lập phù hợp. Các class dùng thư viện Spring nên **không thể biên dịch chỉ với `javac` trần** thiếu classpath; Gradle cung cấp dependencies và classpath.

### 9.2. application.properties: URL gọi introspection

**`src/main/resources/application.properties`**

```properties
# Chỉ chạy ở máy cục bộ cho bài học
server.address=127.0.0.1
server.port=8080

# Resource Server kiểm tra token qua demo introspection endpoint
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=http://127.0.0.1:8080/demo-idp/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=resource-client
spring.security.oauth2.resourceserver.opaquetoken.client-secret=resource-secret
```

**Lưu ý:** client ID/secret ở đây thuộc về **Resource Server khi gọi introspection**, không phải access token của người dùng, không phải tài khoản OAuth2 client nhận token và cũng không phải password của Alice. Trong production, đây là bí mật cấu hình server phải được bảo vệ và quay vòng, không hard-code.

### 9.3. Ứng dụng chính

**`src/main/java/com/example/opaque/OpaqueDemoApplication.java`**

```java
package com.example.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueDemoApplication.class, args);
    }
}
```

### 9.4. SecurityFilterChain

**`src/main/java/com/example/opaque/SecurityConfiguration.java`**

```java
package com.example.opaque;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/demo-idp/introspect")
                    .permitAll()
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .csrf(csrf -> csrf
                .ignoringRequestMatchers("/demo-idp/introspect")
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(withDefaults())
            )
            .build();
    }
}
```

**Giải thích từng quyết định:**

1. `/demo-idp/introspect` được cho qua **HTTP authorization của Spring Security** để request Basic từ RS tới endpoint demo tới được controller. **Điều này KHÔNG có nghĩa endpoint introspection public**: controller tự yêu cầu Basic credentials của RS. Đây chỉ là kiến trúc lab chung một process; production phải tách sang AS đáng tin và bảo vệ đúng chuẩn.
2. CSRF chỉ được bỏ qua cho **đúng endpoint demo introspection POST** vì đó là cuộc gọi service-to-service, không dùng cookie browser để chứng minh login. Không tắt CSRF toàn cục tùy tiện nếu ứng dụng cũng dùng cookie/form login cho các luồng khác.
3. `/api/orders` yêu cầu `SCOPE_orders.read`; token active chỉ có `profile.read` không đủ.
4. `/api/me` yêu cầu đã xác thực bằng bearer token hợp lệ, không yêu cầu scope cụ thể.
5. `anyRequest().denyAll()` chặn route chưa phân loại, tránh vô tình lộ controller khác.
6. `oauth2ResourceServer(...opaqueToken(...))` bật Bearer Token authentication dùng introspection, dựa trên ba Boot properties. Không có `jwt()` trong flow này.
7. AS stub dùng `Authorization: Basic`, không dùng Bearer; filter resource server không coi Basic đó là bearer token.
8. Nếu dùng Servlet endpoint làm API thật, cần tiếp tục thiết kế HTTPS, session policy, CSRF/headers, forwarded proxy và giám sát theo tình huống của ứng dụng.

**Chú ý về tính độc lập:** `SecurityConfiguration` ở đây **là một phần của app demo đầy đủ**, khác với fragment production ở mục 8. Không gộp hai SecurityFilterChain trùng điều kiện khi chạy ví dụ.

### 9.5. Introspection endpoint giả lập có xác thực RS

**`src/main/java/com/example/opaque/DemoIntrospectionController.java`**

```java
package com.example.opaque;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoIntrospectionController {

    private static final String EXPECTED_BASIC =
        "Basic " + Base64.getEncoder().encodeToString(
            "resource-client:resource-secret".getBytes(StandardCharsets.UTF_8)
        );

    @PostMapping(
        value = "/demo-idp/introspect",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> introspect(
            @RequestHeader(value = HttpHeaders.AUTHORIZATION,
                           required = false) String authorization,
            @RequestParam("token") String token) {

        if (!Objects.equals(EXPECTED_BASIC, authorization)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_client"));
        }

        if ("read-token".equals(token)) {
            return ResponseEntity.ok(Map.of(
                "active", true,
                "sub", "alice",
                "client_id", "orders-client",
                "scope", "orders.read",
                "token_type", "Bearer",
                "aud", List.of("orders-api"),
                "exp", Instant.now().plusSeconds(600).getEpochSecond()
            ));
        }

        if ("profile-token".equals(token)) {
            return ResponseEntity.ok(Map.of(
                "active", true,
                "sub", "bob",
                "client_id", "profile-client",
                "scope", "profile.read",
                "token_type", "Bearer",
                "aud", List.of("orders-api"),
                "exp", Instant.now().plusSeconds(600).getEpochSecond()
            ));
        }

        return ResponseEntity.ok(Map.of("active", false));
    }
}
```

Điểm cần hiểu:

- AS stub **không cấp token**: nó chỉ giả lập tra hai token active trong kho token và trả inactive cho mọi chuỗi còn lại.
- Dòng `EXPECTED_BASIC` chỉ mô phỏng xác thực client bằng Basic. So sánh chuỗi như vậy **không phải** hệ thống auth server production: không có secret manager, rotation, client authentication mạnh, per-client permission, TLS hoặc lưu trữ token thật.
- `active:false` trả HTTP 200 và **không thêm metadata**. Đây là hành vi đáng nhớ từ RFC 7662. Với Basic credentials sai, stub trả HTTP 401, không tiết lộ token có tồn tại hay không.
- `scope` là chuỗi theo quy ước RFC, không tự là Java `GrantedAuthority`. Spring introspector biến nó thành authority `SCOPE_orders.read` hoặc `SCOPE_profile.read`.
- `exp` được tạo trong tương lai để rõ dạng epoch seconds; stub **không** thật sự quản lý thời gian token, thu hồi hay chuyển trạng thái dynamic. Các token `expired-token`/`revoked-token` ở bảng minh họa luôn nằm trong nhánh inactive.
- Endpoint nằm cùng app với RS chỉ để có ví dụ một process. Trong hệ thống thật, AS/IdP là hệ tin cậy riêng, không được mở introspection cho caller tự do hoặc dùng HTTP không TLS.

### 9.6. API dùng Authentication đã được introspect

**`src/main/java/com/example/opaque/ApiController.java`**

```java
package com.example.opaque;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/orders")
    public String orders(Authentication authentication) {
        return "orders for " + authentication.getName();
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "name", authentication.getName(),
            "authorities", authorities
        );
    }
}
```

`Authentication.getName()` của opaque bearer token thường lấy từ `sub` nếu introspection trả thuộc tính này. Trong ví dụ, `read-token` mang `sub=alice` và `profile-token` mang `sub=bob`.

**Không trả nguyên access token, client secret, toàn bộ raw introspection response hoặc principal attributes nhạy cảm** trong API. Endpoint `/api/me` chỉ trả hai trường minh họa tên và authorities để học cách mapping scope.

### 9.7. Chạy và gửi HTTP request

Máy cần JDK 17+, Gradle tương thích và cổng `8080` đang trống:

```bash
gradle test
gradle bootRun
```

Có thể dùng `./gradlew test` / `./gradlew bootRun` nếu dự án có Gradle Wrapper phù hợp, hoặc `gradlew.bat` trên Windows. `gradle bootRun` khởi chạy server tại `127.0.0.1:8080` trong cấu hình demo.

Terminal khác:

```bash
# Route công khai
curl -i http://127.0.0.1:8080/public

# Không có token
curl -i http://127.0.0.1:8080/api/me

# Token active, đúng scope orders.read
curl -i -H 'Authorization: Bearer read-token' \
    http://127.0.0.1:8080/api/orders

# Token active nhưng chỉ có profile.read
curl -i -H 'Authorization: Bearer profile-token' \
    http://127.0.0.1:8080/api/orders

# Cùng token profile, route chỉ cần authenticated
curl -i -H 'Authorization: Bearer profile-token' \
    http://127.0.0.1:8080/api/me

# Token inactive
curl -i -H 'Authorization: Bearer inactive-token' \
    http://127.0.0.1:8080/api/me

# Token thuộc nhánh expired/revoked của stub
curl -i -H 'Authorization: Bearer revoked-token' \
    http://127.0.0.1:8080/api/me
```

**Kỳ vọng mã HTTP:**

| Request | HTTP | Giải thích |
| --- | :---: | --- |
| `GET /public`, không Bearer | 200 | `permitAll` |
| `GET /api/me`, không Bearer | 401 | Chưa có credentials |
| `GET /api/orders`, `read-token` | 200 | `active:true` và `SCOPE_orders.read` |
| `GET /api/orders`, `profile-token` | 403 | `active:true` nhưng thiếu scope |
| `GET /api/me`, `profile-token` | 200 | Chỉ yêu cầu authenticated |
| `GET /api/me`, `inactive-token` | 401 | AS stub trả `active:false` |
| `GET /api/me`, `expired-token` | 401 | AS stub trả `active:false` |
| `GET /api/me`, `revoked-token` | 401 | AS stub trả `active:false` |

Response body thành công mà code xác định rõ:

```text
GET /public, không token                -> public
GET /api/orders, read-token             -> orders for alice
GET /api/me, profile-token              -> JSON name=bob, authorities chứa SCOPE_profile.read
```

JSON object có thể thay đổi **thứ tự thuộc tính** khi serialization; kiểm tra nội dung thay vì so byte-by-byte string. Body lỗi có thể khác nhau theo exception handling/headers; bảng tập trung vào HTTP status và authorization.

**Dùng curl trên Windows:** mẫu dấu `\` xuống dòng trên phù hợp Unix shell. Với PowerShell, có thể dùng `curl.exe` và đặt lệnh trên **một dòng**, ví dụ:

```powershell
curl.exe -i -H "Authorization: Bearer read-token" http://127.0.0.1:8080/api/orders
```

### 9.8. Thử trực tiếp introspection endpoint

Đây là lời gọi **trực tiếp tới AS stub** (khác với gửi token tới API):

```bash
# Có Basic credentials của Resource Server; active token
curl -i -u resource-client:resource-secret \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'token=read-token' \
    http://127.0.0.1:8080/demo-idp/introspect

# Client credentials sai → 401 ở introspection endpoint
curl -i -u wrong-client:wrong-secret \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'token=read-token' \
    http://127.0.0.1:8080/demo-idp/introspect

# Token không active nhưng client introspection hợp lệ → HTTP 200
curl -i -u resource-client:resource-secret \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'token=inactive-token' \
    http://127.0.0.1:8080/demo-idp/introspect
```

Mẫu phản hồi:

```text
Basic hợp lệ + read-token:
HTTP 200
JSON có active=true, sub=alice, scope=orders.read, aud=[orders-api]

Basic sai + read-token:
HTTP 401
{"error":"invalid_client"}

Basic hợp lệ + inactive-token:
HTTP 200
{"active":false}
```

Đây là **HTTP status từ introspection endpoint**, không phải status HTTP mà API trả cho Client khi bearer token không hợp lệ.

**Không chạy ví dụ bằng token/secret này trên mạng công khai.** Cả mock tokens và Basic credentials đều được hard-code cho mục đích học, và HTTP không mã hóa chỉ chấp nhận được trong môi trường loopback kín.

### 9.9. Integration tests có introspection HTTP thực

Để kiểm tra không chỉ bean giả lập mà cả việc **Resource Server gọi HTTP introspection endpoint**, dùng `@SpringBootTest` với embedded server mở cổng **18080** riêng khi test. Test override URL introspection theo đúng cổng đó; vì vậy request API tại test sẽ **gọi lại AS stub qua HTTP thực**, không phải chỉ một `@MockBean OpaqueTokenIntrospector`.

**`src/test/java/com/example/opaque/OpaqueTokenIntegrationTests.java`**

```java
package com.example.opaque;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT,
    properties = {
        "server.port=18080",
        "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri="
            + "http://127.0.0.1:18080/demo-idp/introspect"
    }
)
class OpaqueTokenIntegrationTests {

    @Autowired
    TestRestTemplate http;

    private ResponseEntity<String> apiGet(String path, String token) {
        HttpHeaders headers = new HttpHeaders();
        if (token != null) {
            headers.setBearerAuth(token);
        }
        return http.exchange(
            path,
            HttpMethod.GET,
            new HttpEntity<>(headers),
            String.class
        );
    }

    @Test
    void publicEndpointRequiresNoToken() {
        ResponseEntity<String> response = apiGet("/public", null);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("public", response.getBody());
    }

    @Test
    void missingBearerIsUnauthorized() {
        assertEquals(
            HttpStatus.UNAUTHORIZED,
            apiGet("/api/me", null).getStatusCode()
        );
    }

    @Test
    void activeTokenWithReadScopeCanReadOrders() {
        ResponseEntity<String> response =
            apiGet("/api/orders", "read-token");

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("orders for alice", response.getBody());
    }

    @Test
    void activeTokenWithoutReadScopeIsForbidden() {
        ResponseEntity<String> response =
            apiGet("/api/orders", "profile-token");

        assertEquals(HttpStatus.FORBIDDEN, response.getStatusCode());
    }

    @Test
    void profileTokenCanUseAuthenticatedEndpoint() {
        ResponseEntity<String> response =
            apiGet("/api/me", "profile-token");

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertTrue(response.getBody().contains("\"bob\""));
        assertTrue(response.getBody().contains("SCOPE_profile.read"));
    }

    @Test
    void inactiveAndRevokedTokensAreUnauthorized() {
        assertEquals(
            HttpStatus.UNAUTHORIZED,
            apiGet("/api/me", "inactive-token").getStatusCode()
        );
        assertEquals(
            HttpStatus.UNAUTHORIZED,
            apiGet("/api/me", "revoked-token").getStatusCode()
        );
        assertEquals(
            HttpStatus.UNAUTHORIZED,
            apiGet("/api/me", "expired-token").getStatusCode()
        );
    }

    @Test
    void introspectionRequiresResourceServerClientCredentials() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBasicAuth("wrong-client", "wrong-secret");
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);

        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("token", "read-token");

        ResponseEntity<String> response = http.postForEntity(
            "/demo-idp/introspect",
            new HttpEntity<>(form, headers),
            String.class
        );

        assertEquals(HttpStatus.UNAUTHORIZED, response.getStatusCode());
    }

    @Test
    void inactiveTokenIntrospectionIsHttp200WithActiveFalse() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBasicAuth("resource-client", "resource-secret");
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);

        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("token", "inactive-token");

        ResponseEntity<String> response = http.postForEntity(
            "/demo-idp/introspect",
            new HttpEntity<>(form, headers),
            String.class
        );

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertTrue(response.getBody().contains("\"active\":false"));
    }
}
```

**Điểm kiểm chứng:**
- Có HTTP server chạy **18080**, Resource Server gọi introspection thật qua loopback cho những `apiGet` có bearer token.
- Token active thiếu scope phải dẫn đến **403**, phân biệt với token inactive dẫn đến **401**.
- Endpoint introspection trả **401** cho client credentials sai và **200 + active:false** cho token inactive.
- Vì cùng dùng embedded Tomcat, request API và request nội bộ tới introspection chạy trên các request threads khác nhau; mô hình lab nhỏ hoạt động nhưng **không** thay thế thiết kế AS độc lập.
- Nếu máy đã dùng cổng 18080, đổi **cả** `server.port` và URI introspection ở annotation test cho phù hợp. Test loại này không nên chạy đồng thời với một process khác dùng cùng cổng.
- Test chưa đo revocation theo thời gian, cache, AS outage, TLS/certificate hoặc performance. Không tự nhận đã kiểm thử những thứ đó.

### 9.10. Vì sao không viết fake introspector trong test là đủ?

Có thể mock `OpaqueTokenIntrospector` để unit test rule nhanh hơn. Nhưng khi mock, bạn **không kiểm chứng**:
- HTTP POST và form body `token`.
- HTTP Basic client authentication của RS.
- Cách parse `active`/`scope` từ JSON của AS.
- TLS, timeout và lỗi network.
- Khả năng endpoint thật tương thích với Spring introspector.

Trong bài này, integration test cố ý có AS stub HTTP riêng trên cùng server để quan sát **request–response introspection**. Với production cần thêm contract/integration test tới test IdP thật hoặc mock server độc lập, đặc biệt các trường hợp active:false, missing scope, exp/aud mismatch, client credential rotation và AS lỗi.

## 10. Tùy biến kiểm tra audience/issuer sau introspection

Một resource server có thể nhận `active:true` từ AS nhưng token đó dành cho một resource khác. Nếu AS bảo đảm chỉ trả active cho RS là audience đúng, hãy viết contract và kiểm thử rõ. Nếu AS trả `aud` trong response và RS có chính sách địa phương, **tự kiểm tra audience** bằng decorator quanh introspector.

**Fragment độc lập về ý tưởng** (không ghép thêm vào demo đang chạy nếu chưa thiết kế lại dependency injection và tests):

```java
OpaqueTokenIntrospector audienceChecked(
        String uri, String clientId, String clientSecret) {

    OpaqueTokenIntrospector delegate =
        SpringOpaqueTokenIntrospector.withIntrospectionUri(uri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();

    return token -> {
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
        Object audience = principal.getAttribute("aud");

        if (!(audience instanceof java.util.Collection<?> values)
                || !values.contains("orders-api")) {
            throw new BadOpaqueTokenException("Invalid token");
        }

        return principal;
    };
}
```

Fragment này cần các imports:
- `org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector`.
- `org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector`.
- `org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException`.
- `org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal`.

Đây là **method minh họa để tạo decorator**, không phải Java file độc lập và không tự đăng ký `@Bean`. Trong app thật, có thể cấu hình một bean `OpaqueTokenIntrospector` dùng các properties/secret của RS để Spring Boot sử dụng. Khi ném `BadOpaqueTokenException`, token bị từ chối theo cơ chế opaque token authentication.

**Đây chỉ là kiểm tra `aud` dạng collection**, còn một AS thực có thể trả `aud` string hoặc collection tùy contract. Cần kiểm tra dạng dữ liệu được bảo đảm bởi IdP, issuer, expiration, token type, tenant và resource-specific permissions khi phù hợp. Đừng áp dụng code máy móc cho mọi provider.

### Khi nào cần custom authority mapping?

Nếu AS trả `roles`/`groups` thay vì OAuth2 `scope` hoặc muốn quy đổi claim riêng thành Spring `GrantedAuthority`, có thể định nghĩa `OpaqueTokenIntrospector`/`OpaqueTokenAuthenticationConverter` phù hợp. Quyền phải xuất phát từ **thuộc tính đã được AS xác minh**, không được lấy từ query param do Client đưa.

Không nên tự đổi mọi role/group thành `ROLE_ADMIN` hoặc cấp `SCOPE_orders.read` cho tất cả active tokens. Hãy review nguồn claim, prefix, tenant và quyền từng endpoint.

## 11. Revocation, caching và độ trễ

### Tại sao introspection hữu ích cho thu hồi token?

Với một opaque reference token, AS có thể thay trạng thái token từ active sang inactive trong token store (ví dụ revoke hoặc tài khoản mất quyền). Khi RS hỏi lại AS, nó nhận kết quả mới.

```text
Thời điểm t0:
AS: token T active=true
RS introspects T → allow nếu scope đủ

Thời điểm t1:
AS: revoke T

Thời điểm t2:
RS introspects T lần nữa → active=false
RS từ chối token (thường API 401)
```

Mức “ngay lập tức” phụ thuộc **RS có introspect lại hay không**, độ nhất quán AS/store và có cache kết quả không. **Introspection không tự bảo đảm zero-latency revocation.**

### Cache introspection: tiết kiệm nhưng stale

Nếu RS introspects mỗi request:
- Có thêm network RTT/CPU và tải lên AS.
- Có thể phát hiện revoke khá nhanh nếu AS luôn có trạng thái mới.
- Nếu AS chậm hoặc down, nhiều request bị ảnh hưởng; cần capacity, timeout, circuit breaker và bảo vệ tránh retry storm.

Nếu RS cache kết quả `active:true` trong 60 giây:
- Giảm request tới AS và latency.
- Nhưng một token bị revoke ở giây thứ 1 có thể vẫn được RS coi active đến khi cache hết, tùy cơ chế invalidation.
- Không bao giờ cache lâu hơn thời hạn token `exp` nếu đã biết; cache key phải gắn đúng token + ngữ cảnh RS/audience/tenant khi cần.
- Dùng cache an toàn cho cả active và inactive results, không lưu token raw vào metrics/logs; phải bảo vệ cache như dữ liệu nhạy cảm.

**Trade-off có thể tính nhẩm:** với 1000 API requests/giây và mỗi request introspection một lần, AS có thể phải xử lý khoảng **1000 introspection calls/giây** trước cache hoặc batching. Cache giảm tải nhưng làm tăng “cửa sổ chấp nhận token đã revoke”.

### Fail-closed khi AS không sẵn sàng

Không làm:

```java
try {
    return delegate.introspect(token);
} catch (Exception ex) {
    // NGUY HIỂM: không được tự cấp quyền vì introspection down
    return unrestrictedPrincipal;
}
```

Đây là **phản ví dụ không hoàn chỉnh, không chạy được độc lập**; mục đích là cảnh báo. Khi không thể xác minh token, **không dựng principal có quyền để vượt qua**. Chọn lỗi phù hợp và làm rõ trong logging/metrics nội bộ, không phơi secret hay raw token.

Tham số vận hành cần đặt theo SLO:
- Thời gian chờ kết nối/read timeout phù hợp.
- Retry có giới hạn, có backoff và không tạo thác lũ khi AS lỗi.
- Circuit breaker và fallback **từ chối truy cập** với thông điệp không tiết lộ nội bộ.
- Theo dõi tỉ lệ introspection success/inactive/error, latency p50/p95/p99, TLS failures, AS availability.
- Tách metric “token inactive” khỏi “client credentials sai” và “AS 5xx/down”.
- Khi cache, ghi nhận hit ratio và revocation propagation delay.

## 12. Kiểm soát an toàn và mối đe dọa

| Nguy cơ | Biện pháp |
| --- | --- |
| Bearer token bị log trong URL/query | Chỉ dùng header `Authorization` tới API, body form POST tới introspection; redact logs |
| Token gửi tới host giả vì SSRF/misconfiguration | URI introspection allowlist/tin cậy, TLS certificate validation, proxy egress policy |
| Client credentials của RS bị lộ | Secret manager, least privilege, rotate, không lưu trong repository |
| Người lạ gọi introspection để dò token | RS client authentication và authorization, hạn chế dữ liệu trả về |
| AS trả active cho token có audience không phù hợp | Kiểm tra AS policy và `aud`/issuer theo contract của resource |
| Quá tin vào `active:true` | Kiểm tra scopes, tenant, owner/resource permission riêng |
| Introspection bị lỗi nhưng RS fail-open | Fail closed và trả lỗi có kiểm soát |
| Cache active quá lâu | TTL phù hợp `exp` và nhu cầu revoke, thiết kế invalidation |
| Token replay | HTTPS, lifetime phù hợp, scope hẹp, token binding/DPoP/mTLS nếu kiến trúc yêu cầu |
| CSRF | Phân tích browser credentials; bearer header gửi chủ động khác ambient cookies |
| XSS và token storage | Giảm script injection, bảo vệ token trên client, CSP/HttpOnly theo kiến trúc |
| Overly broad scopes | Cấp quyền tối thiểu, mapping chính xác `SCOPE_...` |
| Logout bị hiểu nhầm | Xóa token client không nhất thiết revoke tại AS; hỗ trợ revocation endpoint/policy |
| Cross-tenant IDOR | Scope không chứng minh ownership của đơn hàng; thêm object-level authorization |
| Network latency/AS outage | Theo dõi, timeout, AS HA, cache có ràng buộc và fail closed |

### CSRF trong API bearer-token

Nếu client **chủ động** gắn token vào `Authorization: Bearer` và browser không tự động gửi credential này từ nguồn khác, rủi ro CSRF thường khác so với cookie-based session. Nhưng nếu access token được cất trong cookie mà browser tự gửi, CSRF vẫn là vấn đề. Không khẳng định “opaque thì không cần CSRF” hoặc tắt bảo vệ cho mọi endpoint chỉ vì dùng OAuth2.

Ví dụ runnable chỉ tạo endpoint demo introspection POST dùng Basic credentials RS, không có cookie login; CSRF exception được giới hạn ở đúng route demo để minh họa service-to-service.

### Scope không phải object permission

`SCOPE_orders.read` có thể cho phép user **đọc đơn hàng trong phạm vi mà ứng dụng xác định**, không đương nhiên cho xem mọi đơn hàng mọi tenant. Khi request chứa `/api/orders/123`, service phải kiểm tra người gọi được quyền đọc resource 123, owner/tenant và trạng thái. Đó là bảo vệ object-level ở tầng nghiệp vụ, không thể suy ra chỉ từ `active:true` hoặc `scope`.

## 13. Các lỗi thường gặp khi cấu hình Spring Security

| Lỗi | Kết quả | Cách sửa |
| --- | --- | --- |
| Cấu hình `oauth2ResourceServer().jwt()` nhưng AS phát opaque token | RS không thể xác minh opaque token như JWT | Dùng `opaqueToken`/`OpaqueTokenIntrospector` |
| Thiếu `introspection-uri` hoặc client credentials | Không gọi được AS | Cấu hình properties hợp lệ, bảo vệ secret |
| AS inactive nhưng RS vẫn cho vào | Token revoked/expired bị dùng lại | Chỉ cấp Authentication khi introspection hợp lệ |
| HTTP 200 từ AS bị coi là active | Nhầm status với JSON `active` | Kiểm tra `active`; 200 có thể chứa false |
| HTTP 401 từ AS bị coi như “user chưa login” | Bỏ qua lỗi client authentication RS–AS | Theo dõi riêng client credentials, không fail open |
| Token active thiếu scope nhưng API trả 200 | Authorization policy sai | `hasAuthority("SCOPE_orders.read")` hoặc policy tương ứng |
| Dùng `hasRole("orders.read")` thay `hasAuthority("SCOPE_orders.read")` | Sai prefix/hệ quyền | Phân biệt role và scope |
| Không xét audience/issuer | Token dành cho API khác có thể được dùng | Enforce contract và validators cho RS |
| Log toàn bộ introspection body/token | Lộ PII/credential | Redact data, giới hạn retention |
| Cache token active mãi mãi | Revoke không có hiệu lực | TTL, exp-bound, invalidation |
| Mọi lỗi AS đều bật fallback allow | Mất ranh giới bảo vệ API | Fail closed, giám sát outage |
| Gọi introspection bằng GET query token | Token dễ lộ qua logs/history | HTTP POST form body đúng RFC |
| Trả metadata token khi active=false | Có thể tiết lộ trạng thái token | Chỉ trả `{"active":false}` |
| Đặt AS mock cạnh RS trong production | Không có trust boundary rõ | AS riêng, TLS/client auth thật |
| Xem JWT là “luôn stateless” | Bỏ qua revocation/state ở IdP | Phân biệt token format và validation method |
| Chỉ test 200 | Bỏ sót 401/403, client auth, AS outage | Test tích cực, tiêu cực và network |

## 14. Câu hỏi tự kiểm tra

**1. Vì sao Resource Server không tự đọc scope từ opaque token?**

Vì chuỗi token opaque không có định dạng/claims mà Resource Server được phép tin trực tiếp. Nó cần xác minh bằng cơ chế do AS cung cấp, điển hình là RFC 7662 introspection.

**2. Nếu introspection trả HTTP 200 nhưng JSON `{"active":false}`, API có nên cho phép không?**

Không. 200 chỉ nói cuộc gọi introspection được xử lý hợp lệ; token bị báo inactive và phải bị từ chối.

**3. Khi RS gửi client credentials sai đến introspection, AS nên trả gì?**

Thường là HTTP 401 theo OAuth2 client authentication, khác với HTTP 200 + `active:false` cho một token không hợp lệ khi client introspection đã được xác thực đúng.

**4. Token active có `scope=profile.read` có được vào endpoint yêu cầu `SCOPE_orders.read` không?**

Không. `active:true` vượt qua xác thực token, nhưng authorization còn thiếu authority được yêu cầu; thường API trả 403.

**5. `sub` có luôn là địa chỉ email hoặc username của người dùng không?**

Không. `sub` là subject identifier theo issuer/AS và token type; không được tự coi nó là email/tenant ID hoặc có thể hiển thị công khai.

**6. Opaque token có bắt buộc phải là chuỗi ngẫu nhiên và không bao giờ là JWT không?**

Không. “Opaque” mô tả cách RS sử dụng/kiểm chứng token; Spring Security opaque introspector có thể gửi bất kỳ bearer token phù hợp tới AS kể cả chuỗi có định dạng JWT.

**7. Tại sao cache introspection có thể làm token đã revoke còn được chấp nhận?**

Vì RS dùng lại kết quả `active:true` cũ đến khi cache hết hoặc bị invalidated, thay vì hỏi AS ở mọi request.

**8. Nếu introspection endpoint down, có nên mặc định coi token hợp lệ để API tiếp tục hoạt động?**

Không. Đây là fail-open. RS phải không cấp quyền khi không xác minh được; xử lý availability bằng kiến trúc/timeout/monitoring, không bằng cho qua.

**9. Khi nào cần kiểm tra aud?**

Khi token phải bị ràng buộc vào một Resource Server/resource cụ thể. Nếu token dành cho `billing-api` mà RS `orders-api` chấp nhận, có nguy cơ token substitution/cross-resource use.

**10. Vì sao access token không nên đặt trong query string khi gọi introspection?**

URL dễ bị ghi vào proxy/server logs, lịch sử truy cập và hệ thống monitoring. RFC 7662 sử dụng POST với form body và yêu cầu bảo vệ endpoint qua TLS.

**11. Spring Security ánh xạ `scope="orders.read"` thành authority nào theo mặc định?**

Thường là `SCOPE_orders.read`. Rule `hasAuthority("SCOPE_orders.read")` kiểm tra đúng authority này.

**12. Nếu token active và có `orders.read`, có chắc được xem đơn hàng của người khác không?**

Không. Scope không tự chứng minh quyền sở hữu từng bản ghi; vẫn cần authorization theo resource/tenant/owner.

**13. Test `active:false` ở stub có chứng minh revocation thật hoạt động ngay lập tức không?**

Không. Nó chỉ chứng minh RS từ chối một introspection response inactive. Cần AS có thay đổi trạng thái token theo thời gian và đo propagation/cache để kiểm tra revocation thật.

**14. Vì sao Resource Server cần client ID/secret riêng để introspect, trong khi client đã mang bearer token?**

Bởi bearer token xác thực quyền của **client gọi API**, còn client credentials cho introspection xác thực **Resource Server** trước Authorization Server. Đây là hai quan hệ tin cậy khác nhau.

**15. Có thể dùng opaque token mà không cấu hình `SessionCreationPolicy.STATELESS` không?**

Có. OAuth2 Resource Server có thể xử lý bearer token theo request mà không phụ thuộc vào session login. Nếu ứng dụng còn các cơ chế cookie/form login khác, phải thiết kế state/persistence và CSRF rõ ràng; `STATELESS` là một lựa chọn cấu hình riêng, không phải điều kiện định nghĩa opaque token.

## 15. Tóm tắt

- **Opaque token** là token mà Resource Server không tự tin vào cấu trúc/claims nhìn thấy; thường phải hỏi **Authorization Server** để biết trạng thái.
- **RFC 7662** chuẩn hóa `POST` introspection có `token` trong form body, RS authentication và JSON `active`.
- **HTTP 200 + active:false** nghĩa là yêu cầu introspection được xử lý nhưng token không hợp lệ. **HTTP 401 ở introspection** thường là lỗi xác thực/quyền của RS gọi endpoint. **HTTP 401/403 ở API** mang ý nghĩa riêng.
- Với Spring Security, `OpaqueTokenIntrospector` kiểm tra token, kết quả thành `Authentication`; `scope` thường map thành `SCOPE_...` để dùng `hasAuthority`.
- **active true chưa đủ:** phải kiểm tra scopes, audience/issuer, tenant và object-level permissions theo policy.
- Introspection có thể hỗ trợ revoke nhanh nhưng phụ thuộc AS/network và cách cache; **không fail open** khi mất liên lạc.
- Format token (opaque/JWT), phương pháp validation (local/introspection) và chính sách session (stateful/stateless) là **những quyết định khác nhau**.
- Ví dụ local dùng AS stub cùng process chỉ để quan sát luồng thực của Spring Resource Server; production phải dùng AS đáng tin, TLS, bảo vệ client secret và policy hoàn chỉnh.

## 16. Tài liệu tham khảo chính thức

- Spring Security — OAuth 2.0 Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Boot 3.5 — Spring Security Resource Server properties: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- Spring Security — SpringOpaqueTokenIntrospector API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html
- Spring Security — Servlet Resource Server: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
