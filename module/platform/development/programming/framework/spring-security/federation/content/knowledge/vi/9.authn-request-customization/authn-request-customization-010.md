# Tùy chỉnh kho lưu AuthnRequest khi triển khai nhiều nút

> **Chủ đề:** Spring Security – federation · **Nhóm:** Tùy chỉnh AuthnRequest. Bài này giải thích cách lưu và khôi phục **SAML 2.0 AuthnRequest đang chờ xác thực** khi ứng dụng Spring Security Servlet chạy trên nhiều instance/pod. Trọng tâm là sự khác biệt giữa lưu trong `HttpSession` dùng chung và lưu trực tiếp trong distributed cache, cách triển khai tương ứng theo phiên bản Spring Security, bảo vệ login transaction trước replay/login injection, kiểm thử khi callback đến nút khác và xử lý Redis/session lỗi. Ví dụ Java tự chạy dùng **JDK 17+**, còn các cấu hình Spring cần ứng dụng và dependency tương thích.

## 1. Mục tiêu và tình huống đặt ra

Một ứng dụng SP (Service Provider) cho người dùng đăng nhập thông qua SAML Identity Provider (IdP). Hệ thống chạy sau load balancer với hai nút:

```text
Browser                      Load balancer                 Spring SP
   |                               |                          |
   | GET /saml2/authenticate/corp  |                          |
   |------------------------------>|---- chuyển tới POD A ---->|
   |                               |                          |
   |                               |        POD A:
   |                               |        - tạo AuthnRequest ID=_r1
   |                               |        - lưu pending request
   |<------------------------------|<--- Redirect sang IdP    |
   |                                                           
   | Browser xác thực ở IdP; IdP trả SAMLResponse                 
   | POST /login/saml2/sso/corp  |                            
   |---------------------------->|---- chuyển tới POD B ---->|
   |                               |        POD B:
   |                               |        - tìm pending _r1?
   |                               |        - xác thực response?
```

Nếu pending request chỉ nằm trong **bộ nhớ local của POD A**, POD B không tìm thấy nó. Hậu quả có thể là `InResponseTo` không khớp, không resolve được registration, login thất bại hoặc ứng dụng cố gắng “chữa” bằng cách bỏ kiểm tra giao dịch. Bỏ xác minh correlation để tránh lỗi routing là **sai lầm bảo mật**.

Một thiết kế tốt phải giúp callback ở POD B tìm lại đúng transaction, **đồng thời vẫn biết response đó thuộc lần đăng nhập mà browser/SP đã khởi tạo**, không chỉ tìm một record bất kỳ có ID do người gửi cung cấp.

### Sau bài này người học có thể

1. Phân biệt `HttpSession`, `Saml2AuthenticationRequestRepository`, `RequestCache` và kho phiên người dùng sau login.
2. Lựa chọn giữa **Spring Session + Redis** (chia sẻ `HttpSession`) và **custom/distributed request repository**; biết khi nào sticky session không đủ.
3. Hiểu hợp đồng `saveAuthenticationRequest`, `loadAuthenticationRequest` và `removeAuthenticationRequest`.
4. Xác định khóa lookup, TTL, one-time consumption, collision, cookie binding và replay handling trong multi-node.
5. Áp dụng cấu hình Spring Security 6.x cho một bài toán thực tế và hiểu giới hạn API theo phiên bản.
6. Kiểm tra happy path, replay, cookie mất, cross-pod callbacks, multi-tab, outage và isolation theo tenant.

## 2. Pending AuthnRequest trong SAML2 là gì?

Trong SP-initiated Web SSO, request filter của Spring Security tạo thông điệp `<samlp:AuthnRequest>` rồi đưa nó tới IdP thông qua browser. IdP xác thực user và trả `<samlp:Response>` đến SP Assertion Consumer Service (ACS). Response thường chứa `InResponseTo` tham chiếu ID request đã phát.

Ví dụ rút gọn về ý nghĩa:

```text
SP tạo: AuthnRequest ID="_req_a01"
  Issuer = https://portal.example.org/sp
  Destination = https://login.example.org/saml/sso
  ACS = https://portal.example.org/login/saml2/sso/corp

IdP trả: SAMLResponse InResponseTo="_req_a01"
  Issuer = https://login.example.org/idp
  assertion dành cho SP entityID / ACS đã đăng ký
```

Để xử lý response, SP cần nhớ thông tin request trước đó: registration, giá trị cần đối chiếu, RelayState/context và các thông tin đã lưu trong `AbstractSaml2AuthenticationRequest`. Đây là **pending authentication state**. Nó không phải SAML assertion đã xác thực, không phải access token và không phải quyền truy cập của người dùng.

### 2.1. Tại sao phải lưu request?

- **Correlation:** so `InResponseTo` của response với AuthnRequest đã phát, tránh nhận response cho giao dịch khác.
- **Chọn cấu hình IdP/SP:** callback cần xác định đúng `RelyingPartyRegistration` và bộ khóa tin cậy để verify signature/issuer.
- **Ràng buộc transaction:** khi dùng `HttpSession`, state gắn với browser session trước login; request không được chấp nhận chỉ vì kẻ khác cung cấp một RelayState/ID có trong store.
- **Hạn chế tái sử dụng:** request đã xử lý không nên chấp nhận lại; phải quyết định TTL, one-time semantics và cơ chế chống replay theo policy.
- **Khôi phục luồng:** thực hiện redirect hợp lệ sau authentication mà không nhầm với saved request hoặc lời khai từ client.

### 2.2. Bốn kho khác nhau

| Kho / thành phần | Dữ liệu | Mục đích |
| --- | --- | --- |
| `Saml2AuthenticationRequestRepository` | `AbstractSaml2AuthenticationRequest` chờ SAML response | Correlate và truy xuất SAML request |
| `HttpSession` / Spring Session | Thuộc tính phiên browser, có thể bao gồm pending SAML state và SecurityContext sau login | Giữ phiên xuyên request và giữa các instance khi dùng shared session |
| `RequestCache` | Request URL user muốn mở trước khi login, ví dụ `/reports` | Điều hướng về trang ban đầu sau login |
| `SecurityContextRepository` | `Authentication` / `SecurityContext` đã được xác thực | Nhận diện user ở các request tiếp theo |

**Đừng dùng `RequestCache` hoặc `SecurityContextRepository` để thay `Saml2AuthenticationRequestRepository`.** Các lớp lưu dữ liệu có mục đích khác nhau. Một triển khai có thể dùng Redis cho cả session và cache, nhưng không được trộn lẫn key, thời gian sống hay trust boundary của chúng.

## 3. Ai đọc và ai ghi Saml2AuthenticationRequestRepository?

Luồng Spring Security Servlet thường là:

```text
GET /saml2/authenticate/{registrationId}
    |
    v
Saml2WebSsoAuthenticationRequestFilter
    |
    v
Saml2AuthenticationRequestResolver
    |
    v
AbstractSaml2AuthenticationRequest
    |
    +--> repository.saveAuthenticationRequest(...)
    |
    +--> HTTP Redirect/POST SAMLRequest tới IdP

IdP xác thực rồi chuyển browser về SP ACS

POST /login/saml2/sso/{registrationId}
    |
    v
Saml2WebSsoAuthenticationFilter
    |
    v
Saml2AuthenticationTokenConverter
    |
    +--> repository.loadAuthenticationRequest(...)
    +--> repository.removeAuthenticationRequest(...)
    |
    v
SAML authentication provider:
  signature/trust + issuer + audience + recipient + time
  + InResponseTo/subject confirmation + protocol checks
    |
    v
Authentication / SecurityContext hoặc rejection
```

Đây là **luồng khái niệm**. Chi tiết thời điểm gọi `load` và `remove` hoặc quy tắc fallback phụ thuộc version/converter. Không tự giả định rằng bản framework nào cũng tiêu thụ pending request ở cùng một thời điểm hoặc sẵn có replay cache liên nút. Khi tùy biến repository, phải thử theo source/Javadoc của phiên bản đang chạy.

### 3.1. Interface thực tế

Trong Spring Security 6.3–6.5, interface thuộc package:

```java
org.springframework.security.saml2.provider.service.web
    .Saml2AuthenticationRequestRepository<T>
```

Với `T extends AbstractSaml2AuthenticationRequest`, có ba phương thức:

```java
T loadAuthenticationRequest(HttpServletRequest request);

void saveAuthenticationRequest(
        T authenticationRequest,
        HttpServletRequest request,
        HttpServletResponse response);

T removeAuthenticationRequest(
        HttpServletRequest request,
        HttpServletResponse response);
```

Đây là **chữ ký interface trích riêng để học**, không phải class Java biên dịch độc lập: cần imports từ Jakarta Servlet/Spring Security và khai báo `T` trong interface. Ý nghĩa:

- `save` nhận prepared AuthnRequest và HTTP context để lưu state.
- `load` tìm pending request phù hợp với HTTP callback; trả `null` nếu không có.
- `remove` xóa và trả pending request; với cache chia sẻ nên bảo đảm ngữ nghĩa tiêu thụ nhất quán khi có concurrency.
- Không thêm một biến `static Map` local rồi gọi đó là multi-node repository; mỗi JVM có bộ nhớ riêng.

### 3.2. Thành phần mặc định

`HttpSessionSaml2AuthenticationRequestRepository` lưu pending request trong `HttpSession`. Nó có ưu điểm bảo mật: khi attacker tạo một SAML login request ở **session attacker**, browser của nạn nhân dùng **session khác** sẽ không tự tải được pending request đó. Điều này hỗ trợ chống login fixation/login injection.

Tuy vậy, một `HttpSession` **chỉ nằm ở memory của một node** sẽ không tự chia sẻ dữ liệu sang node khác. Cần bảo đảm callback nhìn được session đúng thông qua **sticky session**, **session replication** hoặc **shared session store**. Trong các hệ thống có auto-scaling/failover, shared store thường linh hoạt hơn sticky routing thuần.

## 4. Ba kiến trúc nhiều nút và đánh đổi

| Kiến trúc | Pending AuthnRequest ở đâu? | Callback POD B đọc được khi POD A tạo? | Rủi ro/vận hành |
| --- | --- | --- | --- |
| Local Servlet HttpSession + sticky routing | RAM của POD A | Thường không, chỉ khi callback được route lại POD A | Pod chết → mất pending request; không đảm bảo khi đổi route |
| **Spring Session backed by Redis** + `HttpSessionSaml2AuthenticationRequestRepository` | Redis-backed browser session | **Có**, nếu browser gửi đúng session cookie và các node dùng cùng store | Cần cookie/serialization/TTL/Redis availability đúng |
| **Distributed cache AuthnRequest repository** | Redis/cluster cache theo state/request key | Có thể có dù session cookie mất | Phải thiết kế browser binding, TTL/atomic consume; dễ tạo login injection nếu lookup chỉ theo RelayState |

**Điểm quyết định:** một custom request repository chỉ chia sẻ **pending AuthnRequest**, không tự làm `SecurityContext` và các dữ liệu session khác được chia sẻ. Nếu sau login POD B tạo session mới nhưng request tiếp theo đi POD A, app vẫn cần shared session hoặc session affinity để giữ phiên authenticated.

**Không phải mọi ứng dụng đều cần viết custom repository.** Nếu mục tiêu là cross-pod callback trong khi browser vẫn mang cookie session bình thường, **chia sẻ HttpSession qua Spring Session** thường giữ được cơ chế correlation theo session và cần ít thay đổi SAML code. Khi cookie không đi qua cross-site POST hoặc hệ thống chủ ý không có session, có thể cân nhắc distributed request cache, nhưng phải giải bài toán login binding riêng.

## 5. Lựa chọn A: chia sẻ HttpSession bằng Spring Session + Redis

### 5.1. Ý tưởng

```text
                         ┌─────────────────────┐
Browser ───> LoadBalancer│                     │
                         │  POD A / POD B      │
                         │  Spring Security    │
                         └────────┬────────────┘
                                  │
                             Redis Session
                                  │
                     ┌────────────▼───────────┐
                     │ sessionId = S-browser  │
                     │ pending AuthnRequest   │
                     │ SecurityContext ...    │
                     └────────────────────────┘

Request bắt đầu ở POD A:
  HttpSession[S-browser].pending = AuthnRequest(_req_A)

Callback đến POD B, browser gửi cùng session cookie:
  Spring Session nạp S-browser từ Redis
  HttpSessionSaml2AuthenticationRequestRepository tìm được _req_A
  SAMLResponse hợp lệ -> Authentication/session
```

Spring Session thay phần lưu `HttpSession` của servlet container bằng triển khai được backing bởi Redis. Code Spring Security vẫn đọc/ghi `HttpSession`; chỉ có backend session thay đổi. Điều này giúp **giữ biên browser-session của mặc định** trong một topology nhiều pod.

### 5.2. Dependency Maven

Trong project Spring Boot Servlet dùng Spring Security SAML2, thêm dependency quản lý bởi Spring Boot BOM phù hợp:

```xml
<dependencies>
    <!-- Spring Security / SAML2 service provider đã được project cấu hình -->
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-saml2-service-provider</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
</dependencies>
```

Đây là **fragment `pom.xml`**, không phải POM hoàn chỉnh. Trong thực tế cần `spring-boot-starter-web`, `spring-boot-starter-security` và các dependency/OpenSAML repository tương thích với Spring Boot/Spring Security hiện tại. Không đặt phiên bản ngẫu nhiên; để BOM quản lý các bản Spring tương thích.

### 5.3. application.yml ví dụ

```yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
  session:
    redis:
      namespace: "portal:sessions"

server:
  servlet:
    session:
      timeout: 30m
```

YAML này **chỉ minh họa cấu hình kết nối và namespace**, không cung cấp cụm Redis production. Cần cấu hình TLS, authentication/secret management, high availability, namespace riêng môi trường, chính sách serialization và timeout theo hạ tầng. `server.servlet.session.timeout` là thời gian idle session trong ví dụ, không phải TTL riêng cho mọi pending AuthnRequest.

Các pod phải thống nhất:

- Cùng Redis cluster/database hoặc backend session được thiết kế để chia sẻ, cùng namespace/serializer tương thích.
- Cùng SAML `RelyingPartyRegistration`, IdP metadata/certificates và public SP entityID/ACS; không để POD A phát registration mà POD B không biết.
- Same public HTTPS origin và session cookie name/scope/path phù hợp, không trả internal hostname cho browser.
- Phương án xử lý key rotation, deployment rolling upgrade và format serialization khi nhiều bản ứng dụng cùng chạy.
- Synchronized session expiration/logout và lỗi khi Redis không sẵn sàng.

### 5.4. Filter chain không cần viết lại request repository

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlWebSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

Đây là một **class Spring Security đầy đủ về source**, nhưng ứng dụng phải có registration SAML, Spring Boot web/security dependencies, Redis và IdP đã được cấu hình; class này không phải chương trình `main` để chạy bằng `javac` thuần.

Ý chính: giữ `HttpSessionSaml2AuthenticationRequestRepository` mặc định; Spring Session làm `HttpSession` có thể đọc trên mọi pod. Khi request bắt đầu ở A và callback sang B **với cùng session cookie**, pending request có thể tìm lại được. Đây là lựa chọn thực tế đầu tiên cần đánh giá trước khi thay hẳn cơ chế request state.

### 5.5. Kiểm tra thật thay vì chỉ đọc YAML

1. Bật hai pod A/B, cùng dùng Redis Session store.
2. Bắt đầu login tại POD A; ghi **request correlation ID không nhạy cảm** và backend key/namespace test đã ẩn session ID.
3. Điều hướng POST ACS tới POD B trong môi trường test; browser phải gửi session cookie tương ứng.
4. Xác nhận response không bị từ chối vì mất request, rồi xác nhận sau login có thể truy cập resource tại cả A/B.
5. Tắt POD A sau khi request bắt đầu để xác minh failover, kiểm tra Redis availability và timeouts.
6. Thử chạy hai phiên bản app trong rolling deployment để phát hiện lỗi serialization và cấu hình registration lệch.

**Giới hạn của phương án A:** nếu browser **không gửi session cookie** trên cross-site SAML POST, POD B không thể chọn session đúng dù Redis đang hoạt động. Đây là vấn đề browser/session binding, không phải “Redis không đồng bộ”.

## 6. SameSite và sự cố callback không mang session cookie

### 6.1. Vì sao SameSite ảnh hưởng SAML?

Trong flow phổ biến, browser rời SP sang IdP rồi quay lại SP bằng **cross-site POST** mang `SAMLResponse`. Với cookie SP có `SameSite=Lax` hoặc `Strict`, browser có thể không gửi cookie ấy trên POST. Khi đó:

```text
POD A tạo session S42 và lưu AuthnRequest(_req_42) vào Redis.
Browser lưu cookie SESSION=S42.
IdP chuyển browser POST SAMLResponse đến ACS SP.
Cookie SESSION=S42 bị browser chặn vì cross-site POST.
POD B nhận POST nhưng không có session S42.
Repository mặc định không tìm được _req_42.
```

Vì vậy cần kiểm tra cả:

- Cookie thực tế trong `Set-Cookie`: `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`.
- Browser có gửi `Cookie` header ở POST ACS không?
- Proxy có thay đổi scheme/host/cookie attributes không?
- Browser và IdP/SP có cùng site theo định nghĩa schemeful same-site hay thật sự cross-site? Không chỉ so subdomain bằng mắt.
- Reverse proxy/ingress được cấu hình tin cậy để tính `{baseUrl}`/ACS và cookie security.

### 6.2. Chiến lược cookie phù hợp

Tùy browser, cơ chế IdP và yêu cầu ứng dụng, cookie cần dùng cho cross-site POST có thể phải đặt `SameSite=None; Secure`. Điều này **không tự chặn CSRF**, nên các endpoint nghiệp vụ phải giữ CSRF protection và các chính sách khác. `HttpOnly` giúp giảm rủi ro JavaScript đọc cookie nhưng không ngăn XSS thực hiện thao tác thay user.

Trong một ứng dụng dùng Spring Session, có thể cấu hình `DefaultCookieSerializer` tùy phiên bản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setUseSecureCookie(true);
        serializer.setUseHttpOnlyCookie(true);
        serializer.setSameSite("None");
        return serializer;
    }
}
```

Đây là **ví dụ chính sách cookie cho trường hợp cần POST cross-site**, không phải thiết lập bắt buộc cho mọi SP. Kiểm tra phiên bản Spring Session, SameSite behavior trên browser thật và CSRF/HTTPS trước khi dùng. Nếu ứng dụng muốn `SameSite=Strict` bằng chính sách nội bộ, nó phải thiết kế state khác mà vẫn giữ phòng vệ login fixation, chứ không thể bỏ correlation.

## 7. Lựa chọn B: distributed cache riêng cho AuthnRequest

### 7.1. Khi nào cân nhắc?

- Hệ thống cần truy xuất request ngoài `HttpSession` (ví dụ phiên không có cookie ở callback).
- Có yêu cầu active-active hoặc cache state độc lập với session lifecycle.
- Một giải pháp xử lý nhiều AuthnRequest đồng thời/multi-tab mà session repository mặc định không đáp ứng theo kiểm thử.
- Ứng dụng dùng Spring Security 6.5+ với `CacheSaml2AuthenticationRequestRepository` hoặc tự triển khai `Saml2AuthenticationRequestRepository` ở version cũ.

Tuy nhiên, **dữ liệu pending request được chia sẻ không đồng nghĩa browser hiện tại được phép dùng request đó**. Nếu dùng `RelayState`/`InResponseTo` làm lookup key duy nhất, attacker có thể tạo request ở browser của mình rồi khiến browser của nạn nhân gửi response khớp khóa đó. Spring Security chính thức lưu ý cache ngoài session có thể mất cơ chế chống login fixation tự nhiên của session. Cần quyết định trust model và biện pháp ràng buộc browser/transaction trước khi chọn.

### 7.2. Spring Security 6.5+: CacheSaml2AuthenticationRequestRepository

**Phiên bản rất quan trọng:** `CacheSaml2AuthenticationRequestRepository` được giới thiệu từ **Spring Security 6.5**. Không thể dùng class này trực tiếp trong project Spring Security 6.3. Javadoc 6.5 ghi rõ cache **mặc định ở memory**, không phù hợp nhiều node; phải cấu hình một `org.springframework.cache.Cache` **backed by a distributed store**.

Ví dụ class dành cho **Spring Security 6.5+**, giả định ứng dụng đã cung cấp `CacheManager` có cache tên `samlAuthnRequests`:

```java
import java.util.Objects;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.web.CacheSaml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.web.Saml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.authentication.AbstractSaml2AuthenticationRequest;

@Configuration
public class SharedSamlAuthnRequestConfiguration {

    @Bean
    Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>
    authenticationRequestRepository(CacheManager cacheManager) {

        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("samlAuthnRequests"),
                "Distributed SAML request cache must be configured");

        CacheSaml2AuthenticationRequestRepository repository =
                new CacheSaml2AuthenticationRequestRepository();
        repository.setCache(cache);
        return repository;
    }
}
```

**Điều kiện áp dụng:**

- Class là **Spring configuration**, không có `main` để chạy độc lập; cần Spring Security **6.5+** và một `CacheManager` thực sự dùng Redis hoặc distributed backend.
- Chỉ xuất hiện `getCache("samlAuthnRequests")` **không đảm bảo** cache distributed. Một `ConcurrentMapCacheManager` local vẫn làm mỗi pod giữ bản riêng; xác minh bean/runtime và test cross-pod.
- Bean cache cần TTL ngắn và chính sách serialization xác định cho `AbstractSaml2AuthenticationRequest`/các subtype. Kiểm tra serializer cụ thể và versioning khi rolling deploy; đừng giả định mọi object của framework tự động tương thích với JSON hoặc JDK serialization.
- `CacheSaml2AuthenticationRequestRepository` có cơ chế lookup theo state/RelayState trong các phiên bản tài liệu nêu; cần đánh giá login injection/browser binding độc lập. Đây **không phải** cơ chế bảo mật cao hơn session-bound mặc định.
- Không tự tạo thêm một request repository bean mâu thuẫn khác. Đảm bảo DSL/SAML filters dùng **cùng một instance** cho cả save và load/remove.

Ví dụ cấu hình Redis cache ở Spring Boot (fragment YAML, cần dependency/cache manager và Redis thực tế):

```yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
  cache:
    type: redis
    cache-names: samlAuthnRequests
    redis:
      time-to-live: 5m
```

`spring.cache.redis.time-to-live` thường ảnh hưởng tới cấu hình Redis cache manager cho các cache tương ứng, nên nếu dự án có nhiều loại cache với TTL khác nhau, cần **cấu hình riêng** cache `samlAuthnRequests` thay vì vô tình đặt TTL chung. Đoạn YAML không mô tả keyspace isolation, TLS/auth, serializer hay rule tiêu thụ một lần. Không dùng sample với default memory cache cho một cluster.

### 7.3. Với Spring Security 6.3–6.4: tự triển khai interface có kiểm soát

Khi chưa có `CacheSaml2AuthenticationRequestRepository`, một giải pháp là viết implementation của `Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>`. Đây là bài toán có bề mặt bảo mật lớn; trước tiên nên cân nhắc Spring Session nếu yêu cầu vẫn cho browser mang cookie. Nếu phải viết repository, định nghĩa hợp đồng dữ liệu rõ ràng:

| Thành phần | Trách nhiệm |
| --- | --- |
| Key cache | Opaque random state/ID đủ entropy, scope cho registration/tenant; không suy đoán từ email/username |
| Value | Thông tin prepared request cần lưu `AbstractSaml2AuthenticationRequest` và context được bảo vệ |
| Save | Ghi với TTL, giới hạn cardinality; tránh ghi đè một transaction khác |
| Load | Xác định pending transaction một cách nhất quán, kiểm tra session/browser binding nếu có |
| Remove | Tiêu thụ một lần, atomic đối với cùng key trên nhiều pod |
| Expiry | Giới hạn cửa sổ chờ login và dọn storage; không giữ request vô hạn |
| Availability | Khi cache không truy cập được, xử lý thất bại có kiểm soát, không tự cho login qua |
| Multi-tenant | Không để ID/issuer/registration của tenant A lấy được request của tenant B |
| Serialization | Version-compatible; không lưu keys/private material hoặc thông tin không cần thiết |
| Telemetry | Log event/correlation ID, không log SAMLResponse/cookie/secret/raw state |

Pseudocode **kiến trúc**, không phải implementation Java/Spring có thể copy chạy:

```text
SAVE(pendingRequest, browserContext):
    assert registration is trusted
    state := cryptographically-random, short opaque key
    record := {
        requestId, registrationId, expectedIdpIssuer,
        createdAt, expiresAt, browserBinding,
        preparedRequest
    }
    sharedStore.PUT_IF_ABSENT(state, record, TTL)
    return state for protocol RelayState

LOAD(callback):
    state := validated opaque RelayState or secured lookup context
    record := sharedStore.READ(state)
    if missing, expired, wrong browserBinding/registration: REJECT
    return preparedRequest for SAML validation

REMOVE(callback):
    apply one-time atomic consume semantics across pods
    return consumed preparedRequest or null
```

Trong triển khai thực, Spring Security kiểm soát thời điểm gọi `load`/`remove`; không thể tự ý quyết định “validate rồi remove” mà trái contract filter. Cần kiểm tra lifecycle cụ thể của version. Một record bị consume sớm bởi callback không hợp lệ có thể gây **denial of service** cho login đang chờ; consume muộn nhưng không atomic có thể cho replay race. Phải cân bằng an toàn, khả năng retry khi lỗi và tính năng one-time theo threat model.

### 7.4. Ràng buộc browser là phần khó nhất

Giả sử:

```text
Attacker Browser A   -> SP tạo Request ID=_attack
                       RelayState=R_attack
                       sharedStore[R_attack] = pending(_attack)

Victim Browser B     -> POST SAMLResponse with RelayState=R_attack
                       to SP ACS
```

Nếu SP chỉ lookup `R_attack` và thấy một request hợp lệ, nó **không biết request ấy được phát cho Browser A chứ không phải B**. Signed SAMLResponse đúng issuer/audience cũng không tự chứng minh B đã chủ động login. Đó là một dạng **login CSRF/login fixation/session confusion**; thường dẫn tới nạn nhân bị đăng nhập vào danh tính không mong muốn, và trong một số app tạo vấn đề account linking.

Các cơ chế giảm thiểu cần được thiết kế **cùng nhau**:

1. Giữ browser/session binding khi có thể: một cookie nonce/transaction riêng với thuộc tính tương thích callback, hoặc dùng session thật. Chỉ tin cookie theo chính sách ký/bảo vệ và kiểm tra thời hạn.
2. Dùng RelayState đủ entropy, ngắn hạn, one-time; **không coi bí mật của RelayState là bằng chứng duy nhất** browser đã khởi tạo login nếu nó có thể bị attacker điều khiển/chuyển tiếp.
3. Liên kết request ID, registration, tenant, IdP issuer và session correlation với request của browser.
4. Kiểm tra `InResponseTo` và signed SAMLResponse/assertion, audience, recipient, ACS, issuer, subject confirmation và hạn trong authentication provider chuẩn.
5. Áp dụng anti-replay (response/assertion IDs) với shared/atomic store theo chính sách; đừng mặc định chỉ xoá pending request là đủ.
6. Giới hạn trạng thái pending mỗi browser, request size và số pending keys để tránh tấn công cache bloat/DoS.
7. Nếu không thể thiết lập browser binding đủ mạnh dưới chính sách cookie/browser hiện có, **không khẳng định distributed lookup theo state là tương đương bảo mật với session-bound repository**.

## 8. Thiết kế key, TTL, one-time và consistency

### 8.1. Khóa lưu an toàn

Một khóa `state` tốt là opaque random value, đủ entropy, không lộ user ID/email, không có ý nghĩa nghiệp vụ. Nếu sử dụng request ID hoặc RelayState, phải kiểm tra nguồn, tính duy nhất và scope; không chấp nhận state có ký tự/độ dài bất thường.

**Đừng key theo email hoặc tenant đơn thuần.** Hai lần login cùng user sẽ ghi đè nhau và một tenant có thể ảnh hưởng transaction khác. Nên tách môi trường, phiên bản, registration và state trong namespace storage hợp lý.

Ví dụ keyspace minh họa:

```text
saml:pending:v1:prod:<registrationId>:<opaqueState>
```

Các thành phần trong dấu `<...>` là ký hiệu ví dụ, không phải tên trường đặc biệt của Redis/Spring. Namespace phải được chuẩn hóa/trusted để không gây cache key injection. Các bản ghi không nên chứa raw session ID trong logs.

### 8.2. TTL và giờ hệ thống

Ví dụ chính sách cho một môi trường (cần tuning theo IdP/user experience thực):

| Tham số | Giá trị **minh họa** | Giải thích |
| --- | --- | --- |
| Pending AuthnRequest TTL | 5 phút | Cửa sổ tối đa tìm lại một request chưa hoàn tất |
| Max pending requests per browser | 3 | Hạn chế multi-tab/DoS nhưng vẫn hỗ trợ một số login đồng thời |
| SAML clock skew allowance | 60 giây | Bù lệch đồng hồ nhỏ; không để kéo dài acceptance tùy tiện |
| Redis record expiry | Không sau thời điểm policy cho phép | Không giữ request stale nhiều giờ hoặc vô hạn |
| Authentication session timeout | 30 phút idle (ví dụ riêng) | Phiên user sau login khác pending request TTL |

TTL pending **không phải** session timeout, và session timeout **không phải** thời hạn SAML assertion. Khi IdP yêu cầu MFA phức tạp có thể tốn thời gian, cần cân bằng TTL với UX và anti-replay. Mọi SP pod/IdP nên đồng bộ NTP; không dùng clock skew lớn để che lệch giờ.

### 8.3. Atomic consume và nhiều callback đồng thời

Nếu hai pod đọc cùng key:

```text
POD A: GET(state) -> exists
POD B: GET(state) -> exists
POD A: DELETE(state) -> success
POD B: DELETE(state) -> success/ignored
```

Cả hai có thể nghĩ mình có quyền xử lý request nếu load/remove không atomic. Với backend hỗ trợ, dùng thao tác consume một lần như Redis `GETDEL` (Redis 6.2+) hoặc Lua/transaction phù hợp; nhưng **thời điểm consume phải tuân thủ lifecycle của Spring Security** để không phá validation và không tạo DoS. Chỉ tiêu thụ pending state **không thay thế** anti-replay assertion/response theo protocol.

Khi request đã hết TTL, `load`/`remove` phải cho trạng thái không tồn tại/expired theo policy và từ chối authentication tương ứng. Không tự tạo lại request “để khớp” khi callback tới mà không có record.

### 8.4. Consistency và failover

- Các pod phải cùng biết registration và IdP trust/certificates; Redis chung chưa đủ nếu mỗi pod cấu hình khác.
- Hệ thống cache có thể có replication lag, failover, eviction và split-brain; kiểm tra **read-after-write** và atomicity guarantees của backend.
- Không dùng cache có eviction quá mạnh cho pending login mà không quan sát tỷ lệ `request not found`.
- Lưu object Java cần serializer tương thích giữa rolling deployment. Mã hóa dữ liệu at rest/in transit, giới hạn ACL Redis, không để Internet truy cập thẳng cache.
- Khi cache hỏng, fail closed cho authentication state bị thiếu; có thể cho phép người dùng bắt đầu lại login với thông báo phù hợp.
- Test callback đi đến pod khác, sau rolling restart và khi Redis primary failover để đánh giá hành vi thật.

## 9. Cách phối hợp request repository với SAML validation

Dù pending request đã được khôi phục chính xác, SP vẫn phải xác minh **SAMLResponse**:

| Kiểm tra | Mục tiêu |
| --- | --- |
| Trusted IdP signing certificate/issuer | Response/assertion đến từ IdP được cấu hình, không từ key do browser đưa |
| XML signature trên dữ liệu thực dùng | Tránh signature wrapping/đọc assertion không nằm trong chữ ký |
| `AudienceRestriction` / SP entityID | Assertion dành cho chính SP |
| `Destination` và `Recipient`/ACS | Response được gửi về endpoint SP phù hợp |
| `InResponseTo` | Response trả cho AuthnRequest đã phát/đã lưu |
| `NotBefore` / `NotOnOrAfter` | Assertion và subject confirmation còn hiệu lực |
| Registration/tenant/account mapping | Không nhầm dữ liệu từ IdP A sang tenant B |
| Response/assertion replay handling | Không chấp nhận lại bằng chứng đã dùng |
| Authorization sau login | Chỉ cấp quyền theo policy endpoint/role/tenant/object |

**Không tự chuyển `Saml2AuthenticationRequestRepository` thành authentication provider.** Repository xử lý pending request và correlation; signature verification thuộc Spring Security/OpenSAML provider. Khi tùy biến response validation, giữ các kiểm tra mặc định thay vì replace bằng một validator “cho qua” để tương thích cache.

Đối với unsolicited IdP-initiated response, `InResponseTo` có thể không tồn tại. Nếu ứng dụng không cần luồng này, nên từ chối theo policy. Nếu cần, thiết kế riêng browser binding, recipient/issuer validation và replay protection; không để việc cache lookup thất bại trở thành điều kiện tự động chấp nhận unsolicited response.

## 10. Java 17 thực hành: shared state giữa hai nút và atomic consume

Đoạn demo sau **chạy bằng Java 17 thuần**, mô phỏng hai nút dùng chung một store trong một tiến trình. Nó kiểm tra **browser binding**, thời hạn và consume một lần bằng `ConcurrentHashMap.remove(key, expectedValue)`; không tạo/giải mã XML, không kiểm tra chữ ký SAML, không kết nối Redis hay chạy hai JVM thật. Ý nghĩa của nó là **logic phân phối pending state**, không phải giải pháp SAML repository production.

Lưu `MultiNodeAuthnRequestDemo.java`:

```java
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;

public class MultiNodeAuthnRequestDemo {

    record PendingRequest(
            String requestId,
            String registrationId,
            String browserBinding,
            Instant expiresAt) {}

    static final class SharedStore {
        private final ConcurrentHashMap<String, PendingRequest> pending =
                new ConcurrentHashMap<>();

        void save(String key, PendingRequest request) {
            if (pending.putIfAbsent(key, request) != null) {
                throw new IllegalStateException("Duplicate pending key");
            }
        }

        boolean consume(String key, String registrationId,
                        String browserBinding, Instant now) {
            PendingRequest original = pending.get(key);
            if (original == null) {
                return false;
            }
            if (!original.registrationId().equals(registrationId)
                    || !original.browserBinding().equals(browserBinding)
                    || !now.isBefore(original.expiresAt())) {
                return false;
            }
            return pending.remove(key, original);
        }
    }

    static final class Node {
        private final SharedStore store;

        Node(SharedStore store) {
            this.store = store;
        }

        void begin(String key, PendingRequest request) {
            store.save(key, request);
        }

        boolean finish(String key, String registrationId,
                       String browserBinding, Instant now) {
            return store.consume(key, registrationId, browserBinding, now);
        }
    }

    public static void main(String[] args) {
        SharedStore shared = new SharedStore();
        Node podA = new Node(shared);
        Node podB = new Node(shared);
        Instant now = Instant.parse("2026-11-07T03:00:00Z");

        podA.begin("state-1", new PendingRequest(
                "_req_1", "corp", "browser-1", now.plusSeconds(300)));
        System.out.println("wrong browser: "
                + podB.finish("state-1", "corp", "browser-2", now));
        System.out.println("wrong registration: "
                + podB.finish("state-1", "partner", "browser-1", now));
        System.out.println("cross-pod success: "
                + podB.finish("state-1", "corp", "browser-1", now));
        System.out.println("replay: "
                + podA.finish("state-1", "corp", "browser-1", now));

        podA.begin("state-2", new PendingRequest(
                "_req_2", "corp", "browser-1", now.minusSeconds(1)));
        System.out.println("expired: "
                + podB.finish("state-2", "corp", "browser-1", now));
    }
}
```

Chạy:

```bash
javac MultiNodeAuthnRequestDemo.java
java MultiNodeAuthnRequestDemo
```

Stdout **chính xác**:

```text
wrong browser: false
wrong registration: false
cross-pod success: true
replay: false
expired: false
```

Giải thích:

- `wrong browser=false`: callback mang browser binding khác không được consume pending state.
- `wrong registration=false`: đúng key nhưng sai registration vẫn bị từ chối.
- `cross-pod success=true`: POD A save, POD B consume từ **cùng** `SharedStore`.
- `replay=false`: record đã xóa nên lần thứ hai không thể consume.
- `expired=false`: chưa hết hạn và đã hết hạn được phân biệt tại thời điểm kiểm tra. Demo để record expired trong map nhằm giữ code ngắn; production phải có TTL eviction.

**Đặc biệt quan trọng:** `browserBinding` chỉ là String mô phỏng một ràng buộc đã tin; attacker có thể đoán/đặt các giá trị trong demo, không có cryptographic validation. `ConcurrentHashMap` chỉ chia sẻ trong **một JVM**; không dùng thay Redis trong cluster. Check-then-remove không diễn tả chính xác lifecycle thực tế của mọi Spring Security repository, và bản demo không kiểm tra signed `SAMLResponse`/`InResponseTo`/audience/time conditions theo SAML. Không đưa thẳng code này vào filter SAML production.

## 11. Kiểm thử multi-node nên có gì?

### 11.1. Happy path thật sự xuyên pod

Tạo môi trường test có:

- Hai instance SP cùng registration/keys, sau cùng load balancer và public HTTPS origin.
- IdP test phát ký SAML Response/Assertion hợp lệ, cùng ACS URL/metadata đã đăng ký.
- Redis/session hoặc cache chung, với namespaces và TTL theo config test.
- Cơ chế định tuyến kiểm soát được để cố tình cho `/saml2/authenticate/corp` đến POD A và ACS POST đến POD B.

Test:

```text
Given  POD A and POD B share the intended repository
When   the browser begins SP-initiated SSO on POD A
And    valid SAMLResponse reaches ACS on POD B
Then   B finds correct pending request and validates response
And    user obtains an authorized session that works on both pods
```

Quan sát bằng log **không chứa raw SAML payload**. Ghi `nodeId`, `registrationId`, correlation ID, result/error code, latency và backend availability. Không đưa session cookie, RelayState bí mật, full SAMLResponse vào log/traces.

### 11.2. Ma trận kiểm thử âm tính

| Tình huống | Kỳ vọng |
| --- | --- |
| Request tạo ở A, callback đến B | PASS nếu browser/session và storage đúng |
| A chết sau khi gửi request, B nhận callback | PASS hoặc fail an toàn theo HA policy, không bypass validation |
| Browser không gửi session cookie | Session-bound repo không tìm state; xử lý rõ lý do, không tự nhận unsolicited response |
| Callback dùng request ID chưa từng tạo | Reject |
| `InResponseTo` là ID request đã consumed | Reject |
| Cùng response replay trên A và B đồng thời | Một lần hoặc zero lần thành công theo policy; tuyệt đối không hai session nhờ replay |
| RelayState bị đổi, rỗng, dài hoặc có format sai | Reject hoặc xử lý theo policy, không lookup tùy ý |
| SAML signature không hợp lệ | Reject dù cache tìm được pending request |
| Issuer/Audience/Recipient/ACS sai | Reject dù cache tìm được pending request |
| Registration/tenant A nhưng state của tenant B | Reject, không ánh xạ lẫn user |
| TTL pending hết trong khi IdP đang MFA | Reject với lỗi có thể khởi động lại login; không tăng TTL vô hạn |
| Redis outage trên save | Không phát request được coi là đã lưu thành công |
| Redis outage trên load/remove | Fail closed; không bỏ transaction correlation |
| Cache eviction sớm | Login thất bại có thể chẩn đoán; không auto-disable verification |
| Hai tab login cùng một browser | Không trộn request ID/registration; kiểm tra behavior repository cụ thể |
| Cross-version rolling deployment | Serializer tương thích hoặc fail an toàn có ghi nhận |
| Session đã logout/invalidated | Không tái sử dụng pending state một cách trái policy |
| Cookie `SameSite=Lax`/`Strict` với cross-site POST | Test browser đúng; xử lý policy session/cookie có chủ đích |
| Cookie của attacker và victim khác nhau | Không chấp nhận request của attacker cho browser victim |
| Dùng default in-memory cache của `CacheSaml2AuthenticationRequestRepository` | Cross-pod test FAIL theo dự kiến; phải cung cấp distributed `Cache` |
| Khi app user đã authenticated sang pod khác | Session/SecurityContext còn tồn tại, không chỉ pending SAML state |

### 11.3. Race test một lần và song song

Dùng một response test đã ký hợp lệ, đưa hai callback **đồng thời** đến POD A/B. Xác minh không có hai authentication thành công trái policy; kiểm tra bản ghi pending được consume nhất quán và replay detection tại SAML layer. Với real Spring Security version, nếu `removeAuthenticationRequest` được gọi sau/bên trong converter, cần quan sát timing để xác định atomicity. Không dựa vào test gọi phương thức repository đơn lẻ mà bỏ qua filter/provider end-to-end.

### 11.4. Test session binding độc lập

Thực hiện hai browser profile A và B, mỗi profile có session cookie riêng. Browser A bắt đầu login, sau đó thử chuyển response/state tương ứng sang B trong môi trường test. Thiết kế session-bound phải từ chối, trong khi một cache chỉ dựa vào RelayState có thể cho kết quả khác. Đây là bài test bảo mật cần chạy **trước** khi chấp nhận thay repository mặc định.

## 12. Sự cố phổ biến và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Login chỉ chạy khi sticky session bật | Request state chỉ ở local session/JVM | Chia sẻ `HttpSession` hoặc repository phù hợp |
| Đã dùng Redis nhưng callback vẫn mất request | Browser không gửi session cookie, sai Redis namespace, serializer, timeout | Browser network POST ACS, `Set-Cookie`, pod config, Redis availability |
| POD A save được, POD B read không thấy | Redis khác cluster/database/namespace hoặc cache local | Kiểm tra `CacheManager` bean/runtime, logs/cache TTL |
| `CacheSaml2AuthenticationRequestRepository` chạy 1 pod nhưng fail 2 pod | Chưa gọi `setCache(distributedCache)` | Javadoc: default cache là in-memory |
| SAMLResponse ký hợp lệ nhưng `InResponseTo` sai | Request hết TTL, state nhầm tab/session, registration lệch | Correlation logs, request repository, TTL, same browser |
| Sau login POD B, request kế tiếp POD A yêu cầu login lại | Chỉ AuthnRequest được chia sẻ, authenticated session còn local | Spring Session/shared `SecurityContext` hoặc affinity |
| `SameSite=None` mà cookie vẫn không gửi | Thiếu `Secure`, browser third-party cookie policy, wrong domain/path | Cookie attributes và browser console/network |
| Redis timeout gây nhiều login fail | Dependency outage/latency | Circuit breaker/error budget, HA Redis, fail closed |
| Tăng TTL quá mức giúp login nhưng replay risk tăng | Không giải quyết nguyên nhân state/cookie | Điều tra SameSite, IdP MFA time, expiration policy |
| Hai nút dùng SP entityID/ACS khác | Configuration drift | So metadata và boot config, release process |
| Ứng dụng lỗi deserialize pending object sau rollout | Java/framework serialization compatibility | Versioning/serializer, rollout test, migration policy |
| Login vào tài khoản không mong muốn sau đổi repo | Mất browser binding, chỉ lookup theo state | Login CSRF/fixation review, restore binding |
| Bị cache bloat vì quá nhiều yêu cầu | Không giới hạn pending requests/key size | Quota, TTL, rate limit và monitoring |
| 404 tại ACS sau đổi proxy | Routing/`SecurityFilterChain` sai | Ingress path, public ACS, matcher/filter chain |
| 403 tại POST ACS | CSRF endpoint matcher/cookie/authorization | Không tắt toàn bộ CSRF, dùng cấu hình SAML callback đúng |
| Replay trên 2 pod vẫn qua | Consume không atomic hoặc thiếu replay detection | Load test, Redis atomic op, SAML replay policy |

### 12.1. Quan sát và alert

Ghi các event đã tối thiểu hóa dữ liệu:

```text
event=saml_pending_request_saved
node=pod-a
registration=corp
request_correlation_id=<redacted-id>
backend=redis
result=success
timestamp=...

event=saml_pending_request_missing
node=pod-b
registration=corp
reason=NOT_FOUND_OR_EXPIRED
backend=redis
timestamp=...
```

Đây là **mẫu schema log**, không phải log thật. Không ghi `SAMLRequest`/`SAMLResponse`/assertion, session cookie, SP private signing key hoặc secret RelayState ở production. Một request ID/RelayState có thể được dùng để liên kết giao dịch, nên log fingerprint/ID nội bộ được xử lý giảm nhạy cảm, có retention và kiểm soát quyền.

Theo dõi tỉ lệ `pending NOT_FOUND`, `InResponseTo mismatch`, latency Redis, eviction/TTL expiry, save/load/remove errors, session loss sau rolling restart, replay attempts, số pending keys bất thường, login success per pod và số lần callback sang khác pod.

## 13. Chọn giải pháp theo yêu cầu

| Yêu cầu | Lựa chọn nên đánh giá trước | Vì sao |
| --- | --- | --- |
| Hai pod, browser giữ session cookie ở callback | Spring Session shared `HttpSession` | Giữ ràng buộc session và ít sửa SAML code |
| Chỉ muốn tránh pod failover | Shared session hoặc affinity + failover policy | Không cần custom state parser |
| SAML POST cross-site không gửi cookie | Xem SameSite/browser policy; thiết kế state/cookie phù hợp | Redis-backed session vẫn cần cookie để tìm đúng session |
| Muốn giữ `SameSite=Strict` mọi nơi | Distributed cache + thiết kế browser binding riêng | Đổi trust model; cần security review và test login injection |
| Spring Security 6.5+ đã có distributed `Cache` | `CacheSaml2AuthenticationRequestRepository#setCache(...)` | API được framework cung cấp, nhưng phải bảo đảm cache shared |
| Spring Security 6.3–6.4, không thể dùng session | Custom `Saml2AuthenticationRequestRepository` | Cần tự đảm bảo lifecycle, browser binding, atomicity, serialization |
| Sau login cũng cần session hoạt động qua mọi pod | Spring Session/shared authenticated session | Custom pending repo một mình không giải quyết |
| Multi-region active-active | Backend hỗ trợ consistency/atomic consume, chiến lược routing và failover rõ | Eventual consistency có thể làm replay hoặc mất request |

**Không có một lựa chọn đúng cho mọi hệ thống.** Quy tắc là giữ security properties của SAML transaction trong khi giải yêu cầu multi-node. Nếu đổi từ session-bound sang lookup theo state, cần ghi rõ **khả năng phòng chống login fixation thay đổi thế nào** và kiểm thử tương ứng.

## 14. Checklist review trước production

- [ ] Đã chọn mô hình: shared HttpSession, sticky session, distributed pending cache hoặc phối hợp; mỗi lựa chọn có lý do và threat model.
- [ ] `Saml2WebSsoAuthenticationRequestFilter` và callback converter/filter dùng **cùng repository**; không có bean cấu hình mâu thuẫn.
- [ ] Multi-node test A → B và failover đã chạy với IdP test; sau login `SecurityContext` cũng hoạt động trên mọi pod.
- [ ] Nếu dùng Spring Session, tất cả pods cùng backend, namespace, serializer, session cookie và trusted proxy config.
- [ ] Nếu dùng `CacheSaml2AuthenticationRequestRepository`, phiên bản **>= 6.5** và `setCache(...)` trỏ distributed cache thật; default in-memory không được coi là cluster.
- [ ] Pending request có TTL, key entropy và giới hạn tài nguyên; xử lý cache lỗi fail closed.
- [ ] Browser/session binding được giữ hoặc thay thế bằng cơ chế có security review; không trust RelayState/`InResponseTo` đơn độc.
- [ ] SAML signed response/assertion được validate bằng trusted IdP key; issuer/audience/recipient/time/request correlation và chống replay hoạt động.
- [ ] Atomic consume/race kiểm thử khi hai pod nhận callback đồng thời; kiểm thử cùng state nhiều lần.
- [ ] Cookie `Secure`, `HttpOnly`, `SameSite`/Domain/Path hoạt động trên browser và POST ACS thực tế; CSRF không bị tắt toàn ứng dụng.
- [ ] Mọi SP pod có registration/IdP signing cert/ACS/entityID đồng nhất và đã thử rolling key rotation.
- [ ] Serialization, TTL, data privacy, Redis authentication/TLS/ACL, monitoring và cleanup phù hợp production.
- [ ] Không log raw SAML payload, session cookie, secrets hoặc các credential có thể bị replay.
- [ ] Có test âm tính cho lost cookie, expired/missing request, wrong tenant, signature invalid, replay, multi-tab và Redis outage.

## 15. Câu hỏi ôn tập

**1. Vì sao AuthnRequest tạo ở POD A có thể không tìm được khi response đến POD B?**  
Vì `HttpSession` local hoặc cache in-memory của A không tự chia sẻ state sang B. Cần shared session hoặc distributed repository, đồng thời phải giữ browser/transaction binding.

**2. Spring Session Redis có tự yêu cầu sửa `Saml2WebSsoAuthenticationRequestFilter` không?**  
Thường không. Spring Session thay backend `HttpSession`, nên `HttpSessionSaml2AuthenticationRequestRepository` vẫn có thể được sử dụng.

**3. Chia sẻ Redis session đã đủ nếu browser không gửi cookie trên POST ACS?**  
Chưa đủ. SP cần cookie/session identifier để tìm đúng session; hãy kiểm tra SameSite/HTTPS/browser thay vì bỏ `InResponseTo`.

**4. CacheSaml2AuthenticationRequestRepository có dùng mặc định cho cluster không?**  
Không. Class từ Spring Security 6.5; cache mặc định in-memory. Cần inject distributed `Cache` bằng `setCache(...)` và kiểm tra cross-pod.

**5. Vì sao lookup theo RelayState có thể làm tăng rủi ro login fixation?**  
RelayState chỉ giúp tìm record; nó không tự chứng minh callback browser là browser đã bắt đầu login. Attacker có thể cố chuyển response/state giữa hai browser.

**6. `loadAuthenticationRequest` và `removeAuthenticationRequest` giống nhau không?**  
Không. `load` xem record; `remove` xóa/trả record. Với cache chia sẻ cần one-time behavior/correct concurrency theo lifecycle framework.

**7. Nếu lấy được pending request từ Redis, SP có thể bỏ signature validation không?**  
Không. Pending state chứng minh có giao dịch được tạo; SAMLResponse vẫn phải được xác thực bằng IdP trust và protocol conditions.

**8. Custom repository có tự khiến phiên authenticated sau login hoạt động xuyên pod không?**  
Không. Nó chỉ quản lý pending AuthnRequest. Phiên user và `SecurityContext` cần shared session hoặc phương án riêng.

**9. Test quan trọng nhất của multi-node là gì?**  
Cố ý gửi AuthnRequest qua POD A và SAMLResponse callback qua POD B; sau đó thử replay, lost cookie, wrong browser binding và callback song song.

**10. Vì sao TTL request không thể được đặt bằng session lifetime một cách máy móc?**  
Pending request chỉ cần sống trong cửa sổ đăng nhập ngắn, còn authenticated session có thể tồn tại lâu hơn. TTL dài làm tăng bề mặt lạm dụng, TTL ngắn quá khiến login/MFA thất bại.

## 16. Tài liệu chính thức

- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): trách nhiệm request filter, thay `Saml2AuthenticationRequestRepository` và cảnh báo cache theo RelayState.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): luồng request, callback, registration và provider.
- [Spring Security 6.5 — Saml2AuthenticationRequestRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationRequestRepository.html): hợp đồng `save`/`load`/`remove`.
- [Spring Security 6.5 — CacheSaml2AuthenticationRequestRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/web/CacheSaml2AuthenticationRequestRepository.html): class được giới thiệu từ 6.5, `setCache` và cảnh báo default memory cache.
- [Spring Session — Spring Boot Redis Guide](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): dùng Redis để chia sẻ `HttpSession`.
- [Spring Session — Spring Session and Spring Security](https://docs.spring.io/spring-session/reference/guides/java-security.html): Spring Session thay `HttpSession` và tương tác `SecurityContext`.
- [Spring Session — API / DefaultCookieSerializer](https://docs.spring.io/spring-session/reference/api.html): tên cookie, `Secure`, `HttpOnly` và `SameSite`.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `AuthnRequest`, `Response`, `InResponseTo` và conditions.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): replay, trust và callback validation.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet): cookie security, lifecycle, fixation và hijacking.

**Kết luận thực hành:** Khi `SAMLResponse` có thể quay về pod khác, SP phải tìm lại đúng **pending AuthnRequest** mà browser đã khởi tạo. **Spring Session + shared HttpSession** thường giữ được ràng buộc browser tốt nhất khi cookie hoạt động. **Distributed request cache** có thể giải một số vấn đề vận hành/POST cross-site nhưng đòi đánh giá kỹ login fixation, TTL, one-time atomic consumption, serializer và SAML validation. Mục tiêu không chỉ là “POD B tìm được request”: phải **khôi phục đúng giao dịch và chỉ đăng nhập sau khi toàn bộ bằng chứng SAML hợp lệ**.