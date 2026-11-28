# Khi nào cần custom filter

Trong một ứng dụng Spring Security, **custom authentication filter** là một thành phần tham gia vào chuỗi xử lý HTTP trước khi request đi tới controller, thường nhằm **nhận diện một cơ chế xác thực, đọc credential từ request, xác minh bằng dịch vụ đáng tin và đặt Authentication vào SecurityContext**. Tuy nhiên, không phải cơ chế bảo mật tùy biến nào cũng cần tự viết một Servlet Filter.

Bài thuộc chương **Custom authentication filter** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Toàn mô-đun hướng dẫn xác thực HTTP request bằng **HMAC với shared secret**, canonical request chứa method/URI/header và/hoặc body theo hợp đồng ký, kiểm tra chữ ký, timestamp/nonce chống replay, key rotation, kiểm thử proxy/gateway và ranh giới **authentication**–**authorization**.

> **Quy tắc lựa chọn:** Chỉ thêm custom filter khi có yêu cầu xử lý **ngay tại HTTP security boundary** mà các cơ chế sẵn có không đáp ứng sạch sẽ. Với HMAC trên **toàn request**, đặc biệt khi cần đọc raw body bytes, kiểm duplicate headers, chọn credential theo signed key ID và quyết định replay trước controller, filter ở vị trí xác thực thường là phù hợp. Nhưng **HMAC primitive, key registry, canonicalizer, replay store và policy không nên bị nhồi tất cả vào method `doFilterInternal`**. Ưu tiên tách thành các service có thể kiểm thử độc lập.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích filter trong **Servlet FilterChain** và **Spring Security FilterChainProxy**; biết vị trí của authentication so với controller/interceptor.
2. Nêu **những tình huống không cần custom filter**, kể cả khi hệ thống có logic bảo mật riêng.
3. Phân biệt `AuthenticationFilter` + `AuthenticationConverter` + `AuthenticationManager`/`AuthenticationProvider` với `OncePerRequestFilter` tự viết.
4. Xác định khi nào HMAC request authentication cần truy cập method, original URI, signed headers và raw body bytes **trước khi handler xử lý**.
5. Đề xuất trách nhiệm hợp lý cho filter, canonicalizer, verifier, credential registry, nonce store và authorization policy.
6. Đọc một HTTP request HMAC và mô tả đầy đủ authentication pipeline, từ parsing tới authenticated principal.
7. Nhận biết rủi ro **body consumption**, duplicate headers, proxy rewrites, filter ordering, request wrapping, async/error dispatch.
8. Viết skeleton Java 17/Spring Security Servlet cho filter ủy quyền xác minh HMAC cho service.
9. Thiết kế exception/failure handling, security context và stateless session policy.
10. Kiểm thử điều kiện bắt buộc/không bắt buộc HMAC theo endpoint, cross-client/multi-tenant và các failure modes thực tế.

## 2. Filter giải quyết bài toán nào?

Một HTTP request đi qua nhiều lớp:

~~~mermaid
flowchart TD
    A[Client HTTP request] --> B[Proxy / gateway / servlet container]
    B --> C[Servlet FilterChain]
    C --> D[Spring Security FilterChainProxy]
    D --> E[SecurityContextHolderFilter và những security filters]
    E --> F[Authentication mechanism: built-in hoặc custom]
    F --> G[AuthorizationFilter và request policy]
    G --> H[DispatcherServlet / Spring MVC]
    H --> I[Controller / method security]
    I --> J[Business service và persistence]
~~~

Một **Servlet Filter** nhìn được request/response ở tầng web trước controller. Spring Security tổ chức một tập filters theo thứ tự, được áp dụng qua `FilterChainProxy`. Authentication filter thường:

- Kiểm request có thuộc cơ chế mình phụ trách không.
- Trích credential và metadata theo **protocol grammar**.
- Giao việc xác minh cho `AuthenticationManager`/`AuthenticationProvider` hoặc một verifier service có trách nhiệm rõ.
- Khi thành công, đặt `Authentication` đáng tin vào `SecurityContext` theo cơ chế lifecycle của Spring Security.
- Khi thất bại, dừng request và trả response thích hợp, không chuyển tiếp sang business handler.
- Khi request không thuộc cơ chế mình xử lý, **bỏ qua có chủ đích** để filter chain khác hoặc chain hiện tại xử lý.

**Filter không phải nơi tự cấp quyền mọi tài nguyên.** Sau authentication, `AuthorizationFilter`, method security, resource-level policy và domain services vẫn kiểm tra principal được thực hiện action hay không.

### 2.1. Authentication và authorization khác nhau

Ví dụ HMAC được tạo bằng secret của client A:

~~~text
keyId      = client-a-k3
HMAC tag   = valid for request
principal  = client-a-service
tenant     = tenant-A
target URI = /v1/tenants/tenant-B/orders
~~~

Có thể **authentication PASS** cho client A, nhưng **authorization DENY** do A không có quyền trên tenant B. Một custom filter không được coi chữ ký đúng là quyền bypass mọi endpoint hoặc cấp role theo `X-Role: admin` caller tự khai.

### 2.2. Filter là phần của security chain, không phải tiện ích “chạy trước”

Nếu viết một `@Component` kế thừa `OncePerRequestFilter`, nó có thể được Spring Boot đăng ký như **Servlet Filter toàn cục**, khác với việc thêm nó vào **Spring Security chain** qua `http.addFilterBefore/After/At`. Đăng ký kép có thể khiến filter chạy hai lần hoặc ở vị trí ngoài dự kiến. Cần một chiến lược đăng ký nhất quán và test thật chuỗi filters.

## 3. Các trường hợp KHÔNG nên tự viết authentication filter

Trước khi tạo một filter mới, hãy hỏi: “Spring Security đã có cơ chế đáp ứng đúng contract chưa?”

| Nhu cầu | Hướng ưu tiên | Vì sao không nên tự viết filter? |
| --- | --- | --- |
| Bearer JWT chuẩn | OAuth2 Resource Server / JWT support | Đã có token parsing, validation, principal integration |
| Opaque OAuth2 access token | Resource Server opaque token introspection | Cơ chế hiện có phù hợp hơn tự gọi introspection trong filter |
| HTTP Basic | HTTP Basic support | Không cần parser/callback thủ công |
| Form login | Form Login / framework authentication flow | Xử lý session/login theo cơ chế chuẩn |
| OAuth2/OIDC login | OAuth2 Client/Login support | Tránh tự triển khai protocol phức tạp |
| mTLS client certificate | TLS termination + Spring Security X.509/mTLS integration theo topology | Không nên đọc một certificate header caller tự khai |
| Chỉ cần policy tenant/resource | `AuthorizationManager`, method security, domain checks | Đây là **authorization**, không phải authentication scheme mới |
| Chỉ thêm audit/request correlation | Observability/interceptor/filter phù hợp, không nhất thiết authentication filter | Không có credential phải verify |
| Chỉ validate JSON business field | Bean Validation/controller/service | Đây là input validation, không phải request authentication |
| Chỉ có một bước chuyển đổi Authentication | `AuthenticationConverter` + `AuthenticationProvider` | Có thể tái dùng `AuthenticationFilter` |
| Chỉ muốn dùng credential registry khác | Custom `AuthenticationProvider`/service | Logic xác minh credential không nhất thiết đổi HTTP filter |

Khi mechanism chuẩn đáp ứng contract, tự viết một filter thường làm tăng nguy cơ bỏ qua những bước đã có trong framework: context lifecycle, auth exceptions, header parsing, request matching, session policy và security events.

### 3.1. HMAC không đồng nghĩa OAuth2

HMAC request signing có thể hợp lý cho service-to-service hoặc partner API theo protocol riêng. Nếu yêu cầu chỉ là xác thực API bằng **OAuth2 Bearer JWT**, không nên ép HMAC để rồi tự phát minh key distribution và rotation.

Ngược lại, nếu hợp đồng đối tác quy định **signature trên method, URI, headers và body mỗi request**, một OAuth2 Bearer token đơn thuần **không thay thế đầy đủ integrity binding per-request**. Cần chọn cơ chế theo threat model/hợp đồng tích hợp.

### 3.2. “Muốn custom response 401” không đủ lý do

Đổi format lỗi có thể được giải quyết bằng `AuthenticationEntryPoint` hoặc `AuthenticationFailureHandler`. Muốn bổ sung claim từ một nguồn nội bộ có thể thực hiện trong converter/provider/user service. Chỉ vì muốn trả JSON `{"error":"UNAUTHORIZED"}` không có nghĩa phải viết filter xử lý toàn bộ xác thực.

## 4. Cây quyết định: có thực sự cần custom filter?

~~~mermaid
flowchart TD
    A[API cần authentication đặc biệt?] --> B{Có cơ chế Spring Security chuẩn phù hợp?}
    B -- Có --> C[Dùng cơ chế chuẩn + cấu hình policy]
    B -- Không --> D{Chỉ cần parser credential + provider?}
    D -- Có --> E[AuthenticationFilter + AuthenticationConverter + Provider]
    D -- Không --> F{Cần thao tác HTTP boundary đặc biệt?}
    F -- Không --> G[Đặt logic trong AuthenticationProvider/service]
    F -- Có --> H[Custom OncePerRequestFilter hoặc filter chuyên biệt]
    H --> I[Delegate HMAC, replay, registry cho testable services]
    I --> J[Kiểm body replay, ordering, context, errors, gateway]
~~~

Hãy đi từ **cơ chế chuẩn → framework extension points → custom filter tối thiểu**, không bắt đầu bằng việc viết `doFilterInternal` quá lớn.

### 4.1. Khi nào `AuthenticationFilter` đủ?

Trong mô hình Servlet của Spring Security, `AuthenticationFilter` có thể kết hợp:

- `RequestMatcher` quyết định request nào cần mechanism.
- `AuthenticationConverter` chuyển HTTP request thành một **unauthenticated Authentication request** chứa credentials/metadata.
- `AuthenticationManager` / `AuthenticationProvider` thực hiện xác minh.
- Authentication success/failure handlers theo contract.
- `SecurityContextRepository`/context handling theo framework configuration.

Nếu HMAC request của bạn có thể được biểu diễn an toàn bằng dữ liệu converter đọc được **mà không phá body streaming**, đây thường là lựa chọn dễ bảo trì hơn tự viết filter toàn bộ.

### 4.2. Khi nào `OncePerRequestFilter` đáng cân nhắc?

Khi protocol đòi hỏi một hoặc nhiều yêu cầu sau **mà extension points sẵn có không giải quyết đầy đủ trong topology thực tế**:

- Cần capture raw body bytes **trước MVC deserialization** và chuyển tiếp một request wrapper có body đọc lại được.
- Cần kiểm tra nhiều nguồn signed metadata và reject header ambiguity **ở HTTP boundary**.
- Cần tự chuẩn hóa/truyền trusted original URI semantics qua một gateway rewrite có hợp đồng ký phức tạp.
- Cần quyết định signed-request authentication một lần trước mọi handler tương ứng, cả khi có streaming/large body policy.
- Cần một integration point chặt giữa signature verifier, replay gate và một authentication mechanism riêng nhưng không thể biểu diễn sạch bằng converter/provider.
- Có yêu cầu audit/admission/chặn request trước khi một downstream consumer đọc/có side effect.

**Điều kiện “cần raw body” không tự động bắt buộc viết custom filter:** một converter kết hợp request wrapper ở bước trước, hoặc body-signing tại gateway, có thể vẫn phù hợp hơn. Quyết định dựa trên lifecycle của request và trách nhiệm được phân tách.

## 5. HMAC per-request là ví dụ thực tế cần cân nhắc filter

Một request có thể có:

~~~http
POST /signed-api/orders?dryRun=false HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1800000030
X-Nonce: 0123456789abcdef0123456789abcdef
X-Signature: <base64url-hmac-sha256-tag>

{"orderId":"O42","amount":250000}
~~~

Canonical request **minh họa**, không phải chuẩn chung:

~~~text
HMAC-REQUEST-V1
POST
/signed-api/orders
dryRun=false
audience:orders-api
content-type:application/json
key-id:partner-a-k3
timestamp:1800000030
nonce:0123456789abcdef0123456789abcdef
body-sha256:<sha256-hex-of-actual-raw-body-bytes>
~~~

Giả định version V1:

1. Các dòng ghép bằng LF và encode UTF-8, không thêm LF cuối.
2. Method, raw path, canonical query và các mandatory signed headers theo một contract rõ.
3. Key ID, timestamp và nonce nằm trong signed bytes.
4. Body hash do verifier **tính từ body bytes thực nhận**, không tin client-supplied hash.
5. Server lấy secret từ **trusted registry** theo exact key ID.
6. Tag là **full HMAC-SHA256 32-byte output**, encode Base64URL không padding.
7. HMAC không chứa chính tag `X-Signature` trong input.
8. Audience, algorithm, key status/expiry và principal đều theo policy server-side.
9. Timestamp freshness và nonce atomic replay claim độc lập với việc HMAC khớp.
10. Principal được xác thực vẫn cần authorization trên action/tenant/resource.

Nếu controller đọc `@RequestBody` trước khi custom auth logic chạy, hệ thống có thể:

- Để business deserialize/chạy trước xác thực.
- Hash JSON đã parse/serialize lại thay vì raw bytes signer gửi.
- Bỏ qua canonical path/query/header hoặc ký khác proxy.
- Cho client tạo signed header/body inconsistency mà verifier không nhận ra.
- Nhận duplicate/nội dung nhập nhằng do container đã normalize.

Vì vậy **per-request HMAC** thường cần xác minh ở lớp security/web filter trước controller. Nhưng **cách tổ chức** filter vẫn nên ưu tiên framework extension points phù hợp.

## 6. Filter làm gì và không nên làm gì?

| Trách nhiệm | Nơi hợp lý | Ghi chú |
| --- | --- | --- |
| Chọn endpoint/protocol | Security chain matcher + filter matcher | Không chạy bất ngờ trên form-login hoặc actuator |
| Trích header & strict parse | Converter / HTTP adapter | Reject missing/duplicate/malformed |
| Truy cập body bytes | Boundary adapter/request wrapper | Đảm bảo downstream đọc lại bytes chính xác |
| Canonical request | Pure canonicalizer | Có version và golden fixtures |
| Chọn secret theo key ID | Credential registry/verifier | No fallback, no key enumeration |
| HMAC expected tag | Crypto verifier | Full tag, constant-time-ish comparison primitive |
| Timestamp/nonce policy | Replay/freshness service | Shared atomic store, fail closed |
| Key rotation/disabled/revoked | Trusted key policy | Không tin status từ client |
| Principal và authorities | AuthenticationProvider / trusted result | Không lấy roles từ untrusted header |
| Đưa Authentication vào context | Security authentication integration | Đúng lifecycle của chain |
| Authorization tenant/object | AuthorizationManager, method/domain layer | Không bỏ qua khi MAC đúng |
| Business idempotency | Domain persistence/transaction | Không dùng nonce thay idempotency |
| Lỗi xác thực và response | AuthenticationEntryPoint/FailureHandler | Generic public errors, rich internal telemetry |
| Audit metrics | Structured logging/observability | Không log raw secret/expected tag |

**Filter nên là một adapter mỏng**, không phải một dịch vụ crypto, store replay, JSON parser, policy engine và business service gộp vào một class.

### 6.1. Nếu chỉ cần kiểm HMAC ở đúng một webhook endpoint?

Có thể dùng một security chain hẹp hoặc một filter/converter chỉ khớp webhook route. Không gắn custom HMAC filter lên toàn bộ application nếu nó sẽ chặn UI, health endpoints, session login hoặc OAuth callbacks. Một webhook receiver có signature provider-specific còn cần policy về timestamp/replay/body bytes và transport; dùng framework adapter vừa đủ.

### 6.2. Nếu chỉ muốn kiểm tenant trong request?

Đó là authorization. Sau khi principal được xác thực bằng Bearer/mTLS/HMAC, dùng `AuthorizationManager` hoặc domain-level policy để kiểm principal được phép truy cập tenant. Viết authentication filter thứ hai chỉ để kiểm tenant có thể khiến trách nhiệm và error handling lẫn lộn.

## 7. Các bất biến trước khi chấp nhận custom filter

Một thiết kế HMAC filter đạt yêu cầu nếu giữ những invariant sau:

1. **Request không thuộc mechanism** không bị filter thay đổi context hoặc body.
2. **Request bắt buộc dùng HMAC** không được bypass filter bằng việc thiếu headers hoặc gửi cơ chế khác nếu endpoint chỉ cho HMAC.
3. **Exactly one canonical credential selector** được parse từ request; duplicate `Authorization`/`X-Key-Id` phải reject tại trust boundary.
4. **Key ID do client khai không phải principal**; chỉ trusted key record sau MAC mới được dùng tạo Authentication.
5. Không có default secret hoặc thử toàn bộ keys cho tới khi một tag khớp.
6. Signed method, target URI, header/body semantics trùng với request được handler thực thi.
7. Full HMAC tag được strict decode và so; không accept prefix/truncated tag.
8. Timestamp và nonce được ký, freshness policy nhất quán theo clock.
9. Atomic nonce admission chỉ sau MAC hợp lệ, trên shared store với TTL đủ.
10. Key REVOKED, expired, wrong audience hoặc tenant denied không được chạy business dù tag khớp.
11. Không tạo/giữ `SecurityContext` khi authentication thất bại.
12. Successful Authentication có principal/authorities từ nguồn đáng tin, không từ caller-provided `X-Role`.
13. Filter không vô tình chạy hai lần do registration ngoài và trong Spring Security.
14. Async/error dispatch, gateway retries và request body replay có policy rõ.
15. Monitoring/lỗi công khai không rò shared secret, expected HMAC, full signed request còn có thể replay hoặc trạng thái key/tenant ngoài phạm vi.

## 8. Đặt filter vào đúng Spring Security filter chain

### 8.1. Servlet filter chain khác Spring Security chain

Một ứng dụng Spring Boot có thể có:

~~~text
Servlet container
  -> ordinary servlet filters
  -> DelegatingFilterProxy
      -> FilterChainProxy
          -> selected SecurityFilterChain (first matching chain)
              -> security context lifecycle filter
              -> configured authentication filters
              -> exception translation / authorization filters
  -> DispatcherServlet
  -> Controller
~~~

Thứ tự và các thành phần cụ thể phụ thuộc cấu hình/phiên bản Spring Security; không nên xem sơ đồ là danh sách thứ tự tuyệt đối của mọi filter.

`SecurityFilterChain` được chọn bằng `RequestMatcher`. Nếu có nhiều chains, **chain đầu tiên phù hợp** được dùng. Endpoint `/signed-api/**` cần HMAC nên có chain rõ ràng, tránh catch-all chain ưu tiên cao hơn vô tình bỏ qua HMAC.

### 8.2. Cấu hình Spring Security theo endpoint

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

public class SignedApiSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain signedApiChain(
            HttpSecurity http,
            HmacAuthenticationFilter hmacFilter) throws Exception {

        http.securityMatcher("/signed-api/**");

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated());

        // Chỉ disable CSRF khi thật sự là stateless, non-browser API
        // không dùng cookie/session credential.
        http.csrf(csrf -> csrf.disable());

        http.addFilterBefore(
                hmacFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

Đây là **cấu hình minh họa Spring Security Servlet 6-style**, chưa bao gồm toàn bộ bean của ứng dụng. `HmacAuthenticationFilter` sẽ được định nghĩa ở mục sau.

### 8.3. Đúng vị trí không chỉ là một dòng addFilterBefore

- Chạy sau cơ chế quản lý security context và trước request authorization.
- Nếu filter ném `AuthenticationException` trước `ExceptionTranslationFilter`, **không** giả định filter nằm sau bắt được exception này; cần xử lý thất bại tại filter hoặc dùng `AuthenticationFilter`.
- Không đụng body/context của request nằm ngoài HMAC endpoint.
- Không tạo lỗ hổng bằng catch-all chain ưu tiên cao hơn chain HMAC.
- Kiểm chứng thứ tự trên filter chain **thực tế** và tất cả endpoint variants.

### 8.4. Tránh đăng ký filter hai lần

Một Spring bean kế thừa `OncePerRequestFilter` đôi khi được Spring Boot **auto-register** ở Servlet container, trong khi bạn cũng đưa nó vào Spring Security qua `http.addFilterBefore`. Như vậy có thể gây double execution hoặc chạy ngoài đúng context.

Nếu filter là Spring bean và **chỉ** nên sống trong security chain, có thể disable ordinary servlet registration:

~~~java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;

@Bean
FilterRegistrationBean<HmacAuthenticationFilter> hmacRegistration(
        HmacAuthenticationFilter filter) {
    var registration = new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
~~~

Phải kiểm tra bean/servlet registration topology thực tế. Không vô hiệu hóa một filter rồi quên gắn nó vào chain cần xác thực.

### 8.5. Multiple mechanisms

Một API có thể tổ chức:

~~~text
/signed-api/** -> HMAC required
/oauth-api/**  -> OAuth2 Resource Server Bearer
/login/**      -> Session/form login
/actuator/**   -> Health/admin policy
~~~

Không âm thầm “thử HMAC sai rồi fallback sang Bearer” ở endpoint bắt buộc có per-request HMAC integrity. Nếu chủ đích hỗ trợ nhiều schemes, phải có routing/selection policy và test **cross-scheme confusion**.

## 9. Mức tùy biến tối thiểu: AuthenticationFilter + Converter + Provider

Nếu vấn đề chỉ là trích HMAC metadata và xác minh một kiểu credential riêng, hãy xem xét tận dụng `AuthenticationFilter` thay vì tự viết toàn bộ lifecycle.

~~~mermaid
flowchart TD
    A[HTTP request] --> B[AuthenticationFilter]
    B --> C[AuthenticationConverter]
    C --> D[Unauthenticated HMAC Authentication]
    D --> E[AuthenticationManager]
    E --> F[AuthenticationProvider]
    F --> G[Key registry + HMAC and replay services]
    G --> H{Verified?}
    H -- Yes --> I[Trusted Authentication principal and authorities]
    H -- No --> J[Failure handler]
    I --> K[SecurityContext integration]
    K --> L[Authorization]
~~~

- `AuthenticationConverter` trích credential/metadata, tạo một **unauthenticated Authentication token**.
- `AuthenticationManager` tìm provider phù hợp.
- `AuthenticationProvider` dùng trusted registry/secret để xác minh và trả principal sau thành công.
- `AuthenticationFilter` cung cấp request matching, success/failure handlers và integration vào security context.

### 9.1. Một data carrier chưa được xác thực

~~~java
public record PresentedHmacV1(
        String keyId,
        String timestampText,
        String nonceText,
        String signatureText,
        byte[] canonicalBytes) {

    public PresentedHmacV1 {
        canonicalBytes = canonicalBytes.clone();
    }

    @Override
    public byte[] canonicalBytes() {
        return canonicalBytes.clone();
    }
}
~~~

`canonicalBytes` bắt buộc đến từ **trusted HTTP canonicalizer**, không phải field `X-Canonical-Request` do client tự gửi. Không đưa principal/roles từ caller vào authenticated token trước khi kiểm MAC.

### 9.2. Converter đọc body vẫn phải bảo toàn body

Nếu HMAC ký raw body, converter có thể phải đọc ServletInputStream. Framework **không tự hoàn nguyên body stream**. Bạn phải có wrapper/filter được kiểm thử để downstream đọc đúng body bytes, hoặc thiết kế lại signing boundary.

Nếu chỉ có một `AuthenticationProvider` tùy biến trong cơ chế HTTP sẵn có, không cần custom Servlet Filter chỉ để thay cách tra key/permission.

### 9.3. Khi nào cần OncePerRequestFilter?

Khi cần kiểm soát HTTP boundary mà converter/provider không giải quyết sạch, chẳng hạn:

- Đọc raw body trước MVC và **pass body-replay wrapper** tới downstream.
- Kiểm strict header duplicates/HTTP sources và signing metadata tại ingress.
- Ràng buộc original URI được gateway rewrite qua một trust contract.
- Thiết lập admission policy cho signed request trước bất kỳ business consumer.
- Tích hợp một cơ chế HMAC đặc biệt có request lifecycle ngoài hợp đồng của AuthenticationFilter.

Nhưng **có raw body không tự động buộc custom filter**: một dedicated body wrapper + `AuthenticationFilter` có thể phù hợp hơn. Hãy chọn cách ít code bảo mật tùy biến nhất đáp ứng requirements.

## 10. Trường hợp cần đọc raw body bytes trước controller

HMAC per-request thường ký SHA-256 digest của **raw HTTP body**. Hai JSON payloads có thể mang cùng dữ liệu logic nhưng khác bytes:

~~~json
{"amount":100,"currency":"VND"}
~~~

~~~json
{ "currency": "VND", "amount": 100 }
~~~

Nếu hợp đồng ký định nghĩa raw bytes, chúng có **SHA-256 digests khác nhau**. Verifier không được deserialize JSON rồi serialize lại để tính expected tag theo cách tình cờ trùng với một client SDK.

### 10.1. ServletInputStream có lifecycle

Đọc `request.getInputStream()` có thể tiêu thụ stream. Nếu filter đọc body xong rồi gọi `filterChain.doFilter(request, response)` với request gốc, controller dùng `@RequestBody` có thể nhận body rỗng.

Một boundary adapter đúng cần:

1. Giới hạn request body size **trước và trong khi đọc**, không cấp phát vô hạn.
2. Hash/chọn canonical bytes đúng raw representation nhận được.
3. Nếu buffer, **wrap request** để downstream đọc **lại chính những bytes đã xác minh**.
4. Bảo đảm `getInputStream()`, `getReader()` và async/non-blocking API semantics phù hợp Servlet stack.
5. Có policy về `Content-Encoding`, charset, chunked transfer, multipart và streaming.
6. Không log raw body có dữ liệu nhạy cảm khi debug chữ ký.
7. Tránh `getParameterMap()` hoặc middleware khác tiêu thụ form body **trước** verification.
8. Không tin một body-hash header do client gửi nếu verifier không tính lại trên raw body.

### 10.2. ContentCachingRequestWrapper không tự rewind body

`ContentCachingRequestWrapper` của Spring cache body **khi** stream/reader được tiêu thụ. Nó không chủ động đọc toàn bộ body và không tự cho phép downstream đọc lại stream từ đầu sau khi một filter đã tiêu thụ.

Ví dụ sai về giả định:

~~~java
var wrapper = new ContentCachingRequestWrapper(request);
byte[] body = wrapper.getContentAsByteArray(); // Có thể vẫn rỗng.
filterChain.doFilter(wrapper, response);
~~~

Nếu chưa ai đọc thì content cache vẫn có thể rỗng. Nếu filter đã tiêu thụ body, downstream có thể không đọc lại được bằng wrapper đó. Muốn cả HMAC và controller cùng đọc được body, hãy dùng một **body-replay wrapper** được thiết kế và test đúng hoặc verify tại gateway/trust boundary khác.

### 10.3. Không đọc vô hạn bằng readAllBytes()

Một HMAC filter đọc hết body với `readAllBytes()` không giới hạn có thể biến endpoint thành mục tiêu memory exhaustion. Ví dụ policy:

~~~text
maxSignedBodyBytes = 1 MiB
when too large = reject before business
buffered-body = bounded bytes with replay support
streaming-upload = separate signing contract
~~~

Hạn mức 1 MiB chỉ minh họa, phải phù hợp API. Không chỉ dựa vào `Content-Length` do client khai; kiểm số bytes thực đọc. Có thể đặt limit ở gateway, container và application, lưu ý body compression/expansion.

### 10.4. Streaming và large uploads

Nếu endpoint nhận payload hàng GB, filter buffer toàn body vào heap có thể không chấp nhận được. Cần thiết kế streaming MAC/tee hoặc gateway verification, signed chunk protocol, upload session/metadata authorization tương ứng.

Không đánh đồng “custom filter có thể đọc request” với “custom filter phù hợp cho mọi payload”. Xử lý async callbacks và non-blocking input sai có thể gây deadlock hoặc mất bytes.

## 11. Canonical path/header qua reverse proxy

Ví dụ:

~~~text
Client:  POST /public/v1/orders?x=1&y=2
Gateway: removes /public prefix
Backend: POST /v1/orders?x=1&y=2
~~~

Nếu client ký public path nhưng backend chỉ thấy internal path, HMAC có thể mismatch. Nguy hiểm hơn: nếu gateway, verifier và router hiểu các resource semantics khác nhau, một tag đúng có thể được dùng để xác nhận một thao tác ngoài ý định của signer.

### 11.1. Xác định signing boundary

Các lựa chọn có chủ ý:

- Verify **trước gateway rewrite**, rồi gửi authenticated principal/request context qua kênh có integrity đến backend.
- Định nghĩa một canonical representation chung cho client và backend, có version rõ.
- Gateway truyền trusted original request metadata nhưng backend chỉ tin proxy đã được xác thực và loại bỏ các headers caller tự khai.

**Không** thử public path/internal path/decoded path liên tiếp tới khi một tag khớp. “Compatibility fallback” kiểu đó có thể tạo ambiguity và giảm tính ràng buộc của chữ ký.

### 11.2. Những chi tiết phải test

| Thành phần | Bất đồng tiềm ẩn |
| --- | --- |
| HTTP method | GET/POST, method override |
| Path | Encoded slash, dot segments, trailing slash, prefix rewrite |
| Query | Order, duplicate key, blank vs absent, percent encoding |
| Host/authority | HTTP/1.1 Host vs HTTP/2 :authority, trusted forwarding |
| Header names | HTTP case-insensitive names; canonical lowercasing |
| Header values | Whitespace, repeated fields, parsing khác nhau |
| Body | Raw bytes, content encoding, JSON reserialization |
| Message framing | Content-Length, Transfer-Encoding, HTTP/2 conversion |
| Retry | Gateway retry cùng nonce đến verifier khác |
| Tenant target | Signed route tenant khác actual business resource |

### 11.3. Duplicate authentication fields

~~~http
X-Key-Id: client-a-k3
x-key-id: client-b-k1
~~~

HTTP field names **không phân biệt hoa thường**. Đây là hai occurrences của cùng field. Reject ambiguity tại trusted ingress. Nếu proxy đã merge/drop occurrences, `HttpServletRequest.getHeaders()` ở backend **không phục hồi được raw request gốc**. Do đó unit test parser trong Java không thay raw HTTP tests tại gateway.

### 11.4. Không dùng X-Forwarded-* do caller tự khai

`X-Original-URI`, `X-Forwarded-Host` và `X-Authenticated-Principal` có thể được client giả. Chỉ dùng chúng nếu gateway **strip/overwrite** nguồn client và truyền qua một trust boundary bảo vệ (mTLS, signed trusted context hoặc tương đương), với kiểm soát direct backend access.

## 12. Filter phải độc lập với cryptographic verification service

Một thiết kế tách trách nhiệm:

~~~mermaid
flowchart TD
    A[HmacAuthenticationFilter] --> B[HmacHttpRequestAdapter]
    B --> C[Strict HTTP metadata and body replay]
    C --> D[HmacRequestVerificationService]
    D --> E[Canonicalizer V1]
    D --> F[Exact credential registry]
    D --> G[HmacSHA256 verifier]
    D --> H[Timestamp freshness checker]
    D --> I[Shared atomic nonce replay store]
    D --> J[Trusted principal / authorities]
    J --> K[Spring SecurityContext]
    K --> L[AuthorizationFilter and resource policy]
~~~

**Filter** biết HTTP request/response, filter chain và Spring Security context. **Verifier service** biết HMAC contract, key status và replay. **Canonicalizer** thuần/không phụ thuộc Servlet nếu có thể. **Authorization** vẫn là một bước riêng.

### 12.1. Một interface service tốt

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.AuthenticationException;

public interface HmacHttpVerificationService {
    VerifiedSignedHttpRequest verify(HttpServletRequest request)
            throws AuthenticationException;
}
~~~

Kết quả:

~~~java
import java.util.Collection;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.GrantedAuthority;

public record VerifiedSignedHttpRequest(
        HttpServletRequest downstreamRequest,
        HmacPrincipal principal,
        Collection<? extends GrantedAuthority> authorities) {}
~~~

Và principal:

~~~java
public record HmacPrincipal(
        String principalId,
        String clientId,
        String credentialKeyId,
        String tenantId,
        String audience) {}
~~~

**Điều kiện:** `downstreamRequest` là request **đã wrap đúng** để handler đọc lại body bytes đã được verifier xác minh. Nếu không đọc body, nó có thể là request gốc. `authorities` phải từ trusted credential/policy, không lấy trực tiếp từ `X-Role`.

Không cho bên ngoài tự gọi một phương thức tạo `VerifiedSignedHttpRequest` để bypass authentication; đây là một interface/record minh họa cho **trusted internal code path**. Trong production nên hạn chế quyền tạo authenticated result bằng package boundaries, encapsulation hoặc type system phù hợp.

### 12.2. Không gắn trực tiếp domain service vào filter

Sai về dependency:

~~~text
HmacAuthenticationFilter
  -> parse request JSON
  -> write order to database
  -> calculate HMAC
  -> create role from X-Role header
  -> update nonce map local
  -> call controller
~~~

Đúng về phân lớp:

~~~text
Filter: endpoint/matcher, security context, authentication failure
HTTP adapter: strict signed metadata/body semantics
Verifier: key lookup, canonical request, MAC, freshness, nonce
Authorization: principal, tenant, action, resource
Business: order/payment, idempotency, transaction
~~~

Việc tách lớp cho phép unit test HMAC verifier mà không phải khởi tạo Servlet container, và test filter ordering/body replay qua MockMvc/integration riêng.

## 13. Java 17: skeleton OncePerRequestFilter mỏng cho HMAC

Đây là ví dụ **Spring Security Servlet** dùng `jakarta.servlet` (Spring Boot 3 / Spring Security 6 style). Nó minh họa **lúc nào** một custom filter hợp lý và phải ủy quyền phần nào. Các services và beans cần được cung cấp bởi ứng dụng; đây không phải một ứng dụng chạy độc lập.

### 13.1. Filter phụ trách HTTP/security context, không tự tính HMAC

~~~java
import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.web.filter.OncePerRequestFilter;

public final class HmacAuthenticationFilter
        extends OncePerRequestFilter {

    private final HmacHttpVerificationService verifier;
    private final AuthenticationEntryPoint entryPoint;

    public HmacAuthenticationFilter(
            HmacHttpVerificationService verifier,
            AuthenticationEntryPoint entryPoint) {
        this.verifier = verifier;
        this.entryPoint = entryPoint;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        final VerifiedSignedHttpRequest verified;

        // Chỉ bắt lỗi từ verification step ở đây.
        // Lỗi từ downstream do các filters phía sau xử lý.
        try {
            verified = verifier.verify(request);
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();

            // Không trả chi tiết key ID, secret, expected MAC.
            entryPoint.commence(
                    request, response,
                    new BadCredentialsException("Invalid HMAC request"));
            return;
        }

        if (verified == null
                || verified.downstreamRequest() == null
                || verified.principal() == null
                || verified.authorities() == null) {
            SecurityContextHolder.clearContext();
            entryPoint.commence(
                    request, response,
                    new BadCredentialsException("Invalid HMAC request"));
            return;
        }

        // Sau MAC/key policy/freshness/replay success.
        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        verified.principal(),
                        null,
                        verified.authorities());

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        try {
            // Cực kỳ quan trọng nếu verifier đã đọc raw body:
            // dùng request wrapper cho phép downstream đọc lại
            // CHÍNH bytes đã được HMAC xác minh.
            chain.doFilter(verified.downstreamRequest(), response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Các thuộc tính đáng chú ý:

- Trên chain `/signed-api/**`, **request thiếu HMAC cũng phải fail**, không bỏ qua để thành anonymous rồi bất ngờ được authorize bởi rule lỏng.
- `verifier.verify` phải thực sự kiểm credential, canonical bytes, MAC, freshness, nonce **trước khi trả VerifiedSignedHttpRequest**.
- `Authentication` được tạo từ **trusted result**. Không dùng token do caller tự tạo.
- `finally` tránh context còn lại trong thread sau request; Spring Security cũng quản lý context lifecycle. Trong async flow cần integration riêng, không coi clear của một thread là toàn bộ giải pháp.
- `AuthenticationEntryPoint` trả lỗi công khai chung. Với lỗi registry/KMS/nonce store, service có thể phân biệt internal cause nhưng vẫn **không được cho request qua**.
- Code **không catch AuthenticationException quanh toàn `chain.doFilter`**, tránh nuốt lỗi auth từ downstream và đè failure handling của các filters phía sau.

### 13.2. Không tùy tiện swallow mọi exception

Nếu verifier gặp lỗi unexpected (ví dụ DB partition, illegal state, crypto provider issue), request phải **không đi tiếp**. Ví dụ catch riêng `AuthenticationException` và trả generic authentication failure; lỗi runtime khác propagate thành server error hoặc được mapped bởi security error handler đúng policy, nhưng không bao giờ **fail open**.

Sai:

~~~java
try {
    verifyHmac(request);
} catch (Exception ignored) {
    // continue request to preserve availability
}
chain.doFilter(request, response); // Can admit unauthenticated requests!
~~~

Một hệ thống nghiêm ngặt nên định nghĩa các internal outcomes `MALFORMED`, `UNKNOWN_KEY`, `BAD_MAC`, `STALE`, `REPLAY`, `LOOKUP_UNAVAILABLE`, `NONCE_STORE_UNAVAILABLE`. Public errors có thể generic để hạn chế key enumeration.

### 13.3. EntryPoint và filter bean

Một `AuthenticationEntryPoint` đơn giản cho API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;

@Bean
AuthenticationEntryPoint signedApiEntryPoint() {
    return new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);
}
~~~

Một HMAC filter instance có thể được tạo với verifier/entry point qua constructor injection. Nếu nó là Spring bean, cân nhắc disable auto servlet registration như mục 8.4 để tránh hai chains. Test integration phải xác nhận số lần verifier được gọi cho một request.

### 13.4. Khi nào nên dùng Spring AuthenticationFilter thay skeleton này?

Nếu không cần pass body wrapper, converter có thể tạo token một cách an toàn và provider kiểm HMAC/replay, `AuthenticationFilter` thường ít boilerplate hơn, hỗ trợ success/failure hooks và context lifecycle. Skeleton này giúp thấy trách nhiệm nhưng **không phải khuyến nghị mặc định thay framework**.

## 14. Dịch vụ xác minh phía sau filter: một contract nghiêm ngặt

Một `HmacHttpVerificationService` production có thể được triển khai theo các bước:

~~~text
1. Check request is HMAC-required endpoint and size limits.
2. Reject ambiguous HTTP fields at trusted ingress.
3. Parse exactly one key ID, timestamp, nonce and signature.
4. Validate strict grammar/encoding and mandatory signed fields.
5. Read bounded raw body bytes; create replayable downstream request.
6. Build canonical bytes from received method/URI/headers/body.
7. Exact key ID lookup from trusted registry; no fallback.
8. Check key ACTIVE/RETIRING window, audience, algorithm and key status.
9. Compute expected HMAC using selected secret.
10. Strictly decode presented full-length tag; compare securely.
11. Validate signed timestamp against server clock.
12. Atomic claim nonce on shared replay authority, fail closed.
13. Create trusted principal and authorities from key record.
14. Return verified result and correctly wrapped request.
~~~

Tùy threat model, bước key lookup/policy có thể được thực hiện trước body buffering để giảm DoS trên unknown keys, với điều kiện không tạo side effects hay dựa trên untrusted data sai cách. Không dùng “keyId FOUND” làm authentication success trước MAC.

### 14.1. Strict parser không tự trim/normalize key ID

Ví dụ key ID grammar:

~~~text
[A-Za-z0-9_-]{1,64}
~~~

Sai:
- Dùng `trim()`/`toLowerCase()` rồi lookup mà protocol không quy định.
- Percent-decode `client%2Da` thành alias ngoài contract.
- Lấy header đầu tiên nếu có hai `X-Key-Id`.
- Dùng `LIKE` prefix query thay exact unique lookup.
- Khi unknown key ID thì thử default secret hoặc secret của client khác.

### 14.2. Exact header occurrences trong Servlet adapter

Một helper minh họa:

~~~java
import java.util.Collections;
import java.util.List;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.authentication.BadCredentialsException;

public final class SignedHeaderV1 {
    private SignedHeaderV1() {}

    public static String requireSingle(
            HttpServletRequest request, String headerName) {

        List<String> values = Collections.list(
                request.getHeaders(headerName));

        if (values.size() != 1 || values.get(0) == null
                || values.get(0).isEmpty()) {
            throw new BadCredentialsException(
                    "Invalid signed request");
        }

        return values.get(0);
    }
}
~~~

**Giới hạn:** Helper chỉ nhìn occurrences mà Servlet container **còn giữ**. Nếu gateway trước đó đã merge/drop duplicate, chỉ có ingress raw-HTTP policy mới xử lý được. Cũng phải validate syntax/length/CRLF và trường hợp một value chứa dấu phẩy nếu protocol không cho field kết hợp, không coi `size==1` là đủ bảo mật.

### 14.3. HMAC primitive trong Java 17

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSha256V1 {
    private HmacSha256V1() {}

    public static byte[] expected(
            byte[] trustedSecret, byte[] canonicalBytes)
            throws GeneralSecurityException {

        if (trustedSecret == null || trustedSecret.length == 0
                || canonicalBytes == null) {
            throw new IllegalArgumentException("Invalid HMAC input");
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(trustedSecret, "HmacSHA256"));
        return mac.doFinal(canonicalBytes);
    }

    public static boolean fullTagEquals(
            byte[] expected32, byte[] presented32) {
        return expected32 != null && expected32.length == 32
                && presented32 != null && presented32.length == 32
                && MessageDigest.isEqual(expected32, presented32);
    }
}
~~~

`MessageDigest.isEqual` phù hợp để so full tag bytes thay vì `String.equals` hay so prefix. Nhưng nó **không biến toàn key lookup/parser/cache thành constant-time**. Phải đánh giá timing/enumeration theo threat model.

### 14.4. Base64URL tag phải strict

HMAC-SHA256 output là 32 bytes; Base64URL **không padding** có độ dài 43 ký tự. Một decoder nên reject length sai, padding, ký tự ngoài alphabet, non-canonical encoding và tags không đủ 32 bytes.

~~~java
import java.util.Base64;
import java.util.regex.Pattern;
import org.springframework.security.authentication.BadCredentialsException;

public final class HmacTagCodecV1 {
    private static final Pattern TAG =
            Pattern.compile("[A-Za-z0-9_-]{43}");

    private HmacTagCodecV1() {}

    public static byte[] decode(String presented) {
        if (presented == null || !TAG.matcher(presented).matches()) {
            throw new BadCredentialsException("Invalid signature");
        }

        final byte[] tag;
        try {
            tag = Base64.getUrlDecoder().decode(presented);
        } catch (IllegalArgumentException invalid) {
            throw new BadCredentialsException("Invalid signature");
        }

        if (tag.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(tag).equals(presented)) {
            throw new BadCredentialsException("Invalid signature");
        }
        return tag;
    }
}
~~~

### 14.5. Chữ ký không thay credential lifecycle

Khi secret đã lộ, attacker có thể ký timestamp/nonce mới. Vì vậy key `REVOKED` phải reject **dù tag cryptographically correct**. `notBefore` thường inclusive, `notAfter` exclusive; key RETIRING chỉ được verify trong overlap được policy cho phép, không fallback từ key ID mới sang secret cũ.

### 14.6. Replay gate

Một key format minh họa:

~~~text
hmac-replay:v1:orders-api:partner-a-k3:0123456789abcdef0123456789abcdef
~~~

Claim bằng shared atomic insert-if-absent, ví dụ Redis `SET key value NX EX ttl` trên primary. Không dùng `GET` rồi `SET` riêng. Nếu replay store unavailable/unknown outcome, không xử lý business. Redis primary atomicity **không tự bảo đảm durability qua async replica failover**; cần test và authority đúng reliability requirement.

Timestamp/nonce là signed fields. Nếu max past age 300 giây, future skew 30 giây và margin 30 giây thì nonce retention bound bảo thủ là **360 giây** tính từ claim. Nonce unique giúp chống replay, nhưng không thay idempotency của business operation và không chặn attacker có stolen secret tạo request mới.

### 14.7. Ưu tiên một testable verifier service

Verifier service không nên phụ thuộc vào Servlet Filter để test HMAC known-answer vectors (RFC 4231), canonical request fixtures, key rotation matrix, timestamp edges và atomic nonce semantics. Filter integration tests chỉ cần chứng minh adapter gọi đúng service, xử lý context/failure và forward body đúng.

## 15. JUnit 5: kiểm thử hành vi custom filter

Filter tests khác HMAC primitive tests: cần chứng minh **đã gọi verifier, dừng request sai trước business, thiết lập SecurityContext trong chain và xóa context sau request**.

Các ví dụ dùng JUnit Jupiter, Spring Mock Servlet và Mockito. Cần bổ sung dependencies/packages trong project thật; code phục vụ thực hành STEP 4, chưa chạy build.

### 15.1. Thành công: principal xuất hiện bên trong chain

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;

public final class HmacAuthenticationFilterTest {

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void verifiedPrincipalAvailableOnlyInsideChain()
            throws Exception {
        var verifier = mock(HmacHttpVerificationService.class);
        var filter = new HmacAuthenticationFilter(
                verifier,
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED));

        var request = new MockHttpServletRequest(
                "POST", "/signed-api/orders");
        var response = new MockHttpServletResponse();

        var principal = new HmacPrincipal(
                "partner-a-service", "partner-A",
                "partner-a-k3", "tenant-A", "orders-api");

        when(verifier.verify(any(HttpServletRequest.class)))
                .thenReturn(new VerifiedSignedHttpRequest(
                        request, principal,
                        List.of(new SimpleGrantedAuthority(
                                "SCOPE_orders:create"))));

        var calls = new AtomicInteger();
        filter.doFilter(request, response, (req, res) -> {
            calls.incrementAndGet();

            var authentication = SecurityContextHolder
                    .getContext().getAuthentication();

            assertNotNull(authentication);
            assertTrue(authentication.isAuthenticated());
            assertEquals(principal, authentication.getPrincipal());
        });

        assertEquals(1, calls.get());
        verify(verifier, times(1)).verify(
                any(HttpServletRequest.class));

        assertNull(SecurityContextHolder.getContext()
                .getAuthentication());
    }
}
~~~

**Giới hạn:** Unit test chỉ chứng minh behavior của filter trong một invocation. Nó không chứng minh body wrapper đúng, security chain chọn đúng endpoint hoặc gateway không rewrite URI.

### 15.2. HMAC thất bại: không được gọi business

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.util.concurrent.atomic.AtomicInteger;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;

public final class HmacAuthenticationFailureTest {

    @Test
    void badSignatureDoesNotReachHandler() throws Exception {
        var verifier = mock(HmacHttpVerificationService.class);

        when(verifier.verify(any(HttpServletRequest.class)))
                .thenThrow(new BadCredentialsException("Internal bad MAC"));

        var filter = new HmacAuthenticationFilter(
                verifier,
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED));

        var request = new MockHttpServletRequest(
                "POST", "/signed-api/orders");
        var response = new MockHttpServletResponse();
        var handlerCalls = new AtomicInteger();

        filter.doFilter(request, response,
                (req, res) -> handlerCalls.incrementAndGet());

        assertEquals(0, handlerCalls.get());
        assertEquals(401, response.getStatus());
    }
}
~~~

Service fake ở đây không tính MAC, vì vậy còn cần unit tests **thật** cho verifier, canonicalizer, registry và replay store. Filter unit test chỉ kiểm nếu verifier báo lỗi thì chain bị dừng.

### 15.3. Những tình huống filter unit tests khác

- `/signed-api/**` thiếu signed headers → fail, không đi vào controller.
- Duplicate ID, invalid Base64URL, timestamp quá dài → generic authentication failure.
- Registry unavailable hoặc replay store UNKNOWN → fail closed.
- Request success A rồi failure B cùng thread → B không thừa hưởng context A.
- Downstream controller ném exception → context được xóa; filter không nhầm lỗi controller thành bad MAC.
- Filter được gọi đúng một lần cho request khi configured inside Spring Security.
- Filter không đọc body của endpoint ngoài HMAC chain.
- `VerifiedSignedHttpRequest` trả null/sai contract → fail, không gọi handler.
- Trusted authorities từ registry, không từ `X-Role`.

## 16. Integration tests cho SecurityFilterChain thực tế

Ngoài unit tests, dùng Spring Security Test, `MockMvc` hoặc Servlet container để chứng minh **security chain thực sự** đã được cấu hình. Không chỉ dùng `@WithMockUser`, vì cách đó có thể bypass HMAC filter.

| Request | Kỳ vọng |
| --- | --- |
| POST `/signed-api/orders` không HMAC | 401, không business |
| POST key ID malformed | Reject trước lookup |
| POST signature sai | Generic authentication failure |
| POST valid HMAC, fresh timestamp, new nonce | Authenticated, authorization vẫn bắt buộc |
| POST valid HMAC, sai tenant | Authorization deny |
| POST valid HMAC, replay nonce | Replay reject |
| POST Bearer-only trên HMAC-required route | Không bypass |
| GET `/oauth-api/me` Bearer đúng | OAuth2 chain; HMAC không được gọi |
| GET health endpoint | Theo health policy riêng |
| POST empty body, max size và max+1 | Digest/limits đúng |
| Success client A rồi failure B cùng thread | Không leak context A |

### 16.1. Thứ tự filter và duplicate registration

Test các tình huống:

1. Catch-all chain match `/signed-api/**` trước HMAC chain.
2. Filter được auto-register ở Servlet container **và** Spring Security chain.
3. Filter chạy trước security context lifecycle hoặc sau authorization.
4. Exception từ early filter không được failure handler xử lý đúng.
5. Controller vẫn chạy khi HMAC mismatch.
6. Một auth mechanism khác được dùng để bypass HMAC-required endpoint.

Assert `verifierInvocationCount`, response status và authenticated principal **trong controller**, không chỉ mock toàn security layer.

### 16.2. Body replay integration test

~~~text
Client sends exact raw body bytes B.
Verifier computes SHA256(B) and matches HMAC.
Controller receives exact B.
Business handler executes once.
~~~

Test Unicode/whitespace JSON, empty body, max size/max+1, multipart/content encoding theo contract, chunked transfer và một pre-filter tiêu thụ stream. Nếu chỉ so JSON object logic, test không chứng minh raw bytes được giữ nguyên.

### 16.3. Gateway e2e khác MockMvc

`MockMvc` không tái tạo đầy đủ raw HTTP framing, duplicate fields đã bị proxy merge hoặc HTTP/2 pseudo-headers. Gửi requests qua ingress thật:

- Duplicate `Authorization`/`X-Key-Id` khác case bị reject.
- Host/authority và path prefix mapping đúng signing boundary.
- Body không bị rewrite trước verify ngoài contract.
- Gateway retry cùng nonce N không admit hai lần trên hai pods.
- Backend không bị bypass bằng giả `X-Authenticated-Principal`.

## 17. Async/error dispatch và retries

`OncePerRequestFilter` dùng already-filtered marker và dispatcher policy để tránh filter lặp ngoài ý muốn; nó **không** bảo đảm business operation exactly-once qua gateway retries.

### 17.1. Async Servlet

Khi initial request thread và async dispatch khác nhau:

- Đánh giá `shouldNotFilterAsyncDispatch` và security context propagation của framework.
- Nếu chạy verify lại, nonce có thể đã claim và bị coi là replay.
- Nếu không chạy lại, phải chuyển trusted principal đến async task an toàn.
- Long-running stream có thể cần reauthorize khi tenant/key revoke.
- Không giữ mutable static/thread-local identity sau request.

Skeleton filter synchronous ở mục 13 không tự chứng minh async support. **WebFlux** cần `SecurityWebFilterChain`/reactive `WebFilter`, không gắn Servlet `OncePerRequestFilter`.

### 17.2. Error dispatch

Error handler hoặc `/error` có thể trigger dispatcher khác. HMAC verify lại bằng cùng nonce có thể che lỗi gốc bằng replay error. Test `DispatcherType.ERROR`, chain selection và cách trả generic errors.

### 17.3. Gateway retry là request mới

Gateway retry sau timeout có thể tới verifier pod khác. Nếu lần đầu đã claim nonce N, retry nguyên request phải bị replay reject theo contract. Client có thể ký **request mới với nonce mới**, giữ operation ID và tra business status/idempotency store.

Không tắt replay protection để làm retry tự động “pass”.

### 17.4. Exactly-once business là nhiệm vụ riêng

Hai signed requests khác nonce nhưng cùng orderId đều có thể qua HMAC/replay. Domain/database cần enforce idempotency hoặc unique operation constraint; queued workers xử lý sau tenant revoke có thể phải revalidate policy trước commit.

## 18. Multi-client, multi-tenant và key rotation

Một HMAC endpoint có thể phục vụ:

~~~text
Client A -> key A3 -> secret KA3 -> principal A -> tenant A
Client B -> key B1 -> secret KB1 -> principal B -> tenant B
~~~

Nếu request khai key A3 nhưng tag được tạo bằng secret KB1, exact lookup A3 phải dùng KA3 và **reject**. Không thử tất cả secrets của tenant/clients đến khi tag match.

### 18.1. Revocation độc lập

~~~text
Credential A3: REVOKED
Credential B1: ACTIVE

A3 tag mathematically correct -> REJECT under key policy.
B1 tag valid + fresh nonce -> MAY AUTHENTICATE.
~~~

Key IDs riêng nhưng secret bytes dùng chung không đem lại cryptographic isolation. Mỗi client/credential trust boundary cần secret độc lập và permissions tương ứng.

### 18.2. Tenant revocation dù HMAC đúng

~~~text
Credential A3: ACTIVE
HMAC(A3, request) = MATCH
Target tenant A: REVOKED
-> Authorization / tenant policy DENY.
~~~

Filter HMAC authentication có thể thành công, nhưng request không được thực thi business. Với queued workers, tenant policy có thể phải được kiểm lại trước commit nếu requirement đòi hỏi.

### 18.3. Rotation overlap không phải fallback

~~~text
A2 RETIRING until time T
A3 ACTIVE
~~~

Khi request khai A2 chỉ dùng secret A2 trong overlap hợp lệ. Khi khai A3 chỉ dùng secret A3. Một mismatch không kích hoạt “thử A2” hoặc “thử newest key”. Với compromised secret, emergency revoke có thể cần chặn ngay thay vì giữ overlap thông thường.

### 18.4. Request-scoped identity

Không dùng:

~~~java
static String currentClientId;
static String currentTenantId;
~~~

cho ứng dụng nhận requests đồng thời. Dùng trusted per-request `SecurityContext`, cleanup và context propagation theo framework. Reactive/async tasks cần quản lý riêng để client B không đọc principal A.

## 19. Failure modes và fail-closed

| Lỗi | Hành vi an toàn |
| --- | --- |
| Missing HMAC trên required route | Deny |
| Header grammar/control bytes invalid | Deny sớm |
| Duplicate Authorization/Key-ID | Deny ambiguity |
| Unknown key ID | Deny, no fallback |
| Registry timeout/partition | Fail closed |
| Secret manager unavailable | Fail closed |
| Credential revoked/expired/wrong audience | Deny dù MAC đúng |
| HMAC mismatch | Deny; không thử secret khác |
| Bad Base64URL hoặc truncated tag | Deny |
| Timestamp stale/too future | Deny |
| Replay nonce | Deny |
| Replay store UNKNOWN | Fail closed |
| Body quá lớn | Reject trước business |
| Body không replay tới controller | Không xử lý như một verified payload |
| Tenant permission unavailable | Deny sensitive action |
| Downstream controller exception | Không che thành bad MAC |
| Security context leaked | Sửa lifecycle |
| Gateway signing path mismatch | Reject và sửa signing boundary |
| Cache key ACTIVE stale sau revoke | Đúng revocation guarantee |

### 19.1. Không rò expected tag hoặc secret

Sai:

~~~json
{
  "error": "MAC_MISMATCH",
  "keyId": "partner-a-k3",
  "expectedSignature": "...",
  "secretRef": "kms/internal/path"
}
~~~

Public error nên generic theo API contract, còn internal metrics/logs tách các nguyên nhân `AUTH_KEY_UNKNOWN`, `AUTH_MAC_MISMATCH`, `AUTH_REPLAY`, `AUTH_STORE_UNAVAILABLE` và redacted fields.

### 19.2. Bad signature khác dependency outage

Tag sai là authentication failure; secret manager timeout là lỗi hạ tầng. Cả hai không được gọi business, nhưng HTTP status/retry behavior có thể khác theo contract. Đừng cho gateway retry vô hạn một outage rồi làm tăng tải hoặc tạo replay confusion.

### 19.3. Timing và key enumeration

Unknown key ID thường reject nhanh hơn known key, có thể tạo key-existence timing oracle. `MessageDigest.isEqual` chỉ giúp so tag, không làm toàn key lookup/parser/cache constant-time. Áp dụng error hygiene, pre-auth rate limits, key ID entropy và monitoring theo threat model.

### 19.4. DoS trước authentication

Attacker có thể gửi body cực lớn để ép buffering, random IDs gây registry misses, malformed headers gây CPU parsing hoặc floods tới KMS/nonce store. Cần ingress/body/header limits, bounded timeouts, bounded negative cache, coarse pre-auth rate limiting và backpressure. Không dùng raw unknown key ID làm metric label vô hạn.

## 20. Observability, audit và incident response

### 20.1. Internal reason codes

~~~text
HMAC_HEADER_INVALID
HMAC_KEY_ID_UNKNOWN
HMAC_CREDENTIAL_REVOKED
HMAC_ALGORITHM_NOT_ALLOWED
HMAC_CANONICALIZATION_REJECT
HMAC_BODY_TOO_LARGE
HMAC_TAG_MISMATCH
HMAC_TIMESTAMP_STALE
HMAC_NONCE_REPLAY
HMAC_NONCE_STORE_UNAVAILABLE
HMAC_REGISTRY_UNAVAILABLE
HMAC_AUTHENTICATION_ACCEPTED
AUTHZ_TENANT_DENIED
~~~

Không log **shared secret, expected HMAC, raw Authorization, sensitive body hoặc full replayable signed request**. Internal metadata có thể gồm correlation ID, trusted principal/tenant sau authentication, route/action, outcome và latency, theo retention/privacy policy.

### 20.2. Metrics cardinality

Raw key IDs từ caller chưa authenticated có thể thay đổi vô hạn. Metrics nên aggregate theo failure reason và dùng **trusted principal** sau thành công; identifiers chi tiết chỉ ở logs điều tra được kiểm soát, nếu policy cho phép.

### 20.3. Khi secret bị compromise

Nếu secret bị lộ, attacker có thể tạo HMAC tag mới với timestamp và nonce fresh. Filter không phân biệt legitimate client với attacker chỉ bằng tag. Quy trình:

1. Revoke affected key IDs và xác nhận mọi verifier/gateway từ chối theo deadline.
2. Rotate bằng secret độc lập, key ID mới và secure delivery.
3. Kiểm cache/regions/direct backend routes không còn stale ACTIVE.
4. Điều tra accepted requests/business side effects trong exposure window.
5. Sửa đường rò CI/log/secret manager; không lặp lại ở key mới.
6. Không re-enable compromised secret để sửa downtime.
7. Giữ tenant/resource authorization và business idempotency.

### 20.4. Điều tra HMAC bypass

Khi unsigned request tới được handler, xem:

~~~text
Matched SecurityFilterChain and request matcher
Filter ordering and registration count
Header parser and gateway transform
Custom filter matcher and shouldNotFilter
Entry point/exception behavior
SecurityContext principal provenance
Authorization rule that allowed the action
Original path/body signing boundary
Direct backend / alternate ingress
~~~

Một log “filter ran” từ Servlet container không chứng minh request đã đi qua **đúng HMAC security chain**. Nó có thể chạy trước chain và không chặn hoặc một chain khác đã match route.

## 21. Khi nào custom filter làm mọi thứ tệ hơn?

Một custom authentication filter thường là lựa chọn kém nếu:

- Viết chỉ để đổi HTTP 401 thành JSON.
- Tự triển khai OAuth2/JWT flow đã có implementation Spring Security phù hợp.
- Đọc request body nhưng không wrap lại cho controller.
- Dùng authentication filter để giải quyết tenant grants thay vì authorization.
- Chứa secret hardcoded và không hỗ trợ key ID/rotation.
- Thử nhiều keys hoặc canonicalizations cho tới khi tag khớp.
- Tạo authenticated principal từ `X-Client-Id` hoặc `X-Role` chưa verify.
- Dùng local nonce map khi hệ thống có nhiều pods.
- Xử lý retries bằng cách bỏ qua nonce replay gate.
- Bắt mọi exceptions rồi tiếp tục business để “giữ availability”.
- Được đăng ký hai lần trong container và Spring Security.
- Chỉ test MockMvc, chưa bao giờ test qua gateway/proxy thực.
- Dùng Servlet API trong ứng dụng WebFlux/reactive.
- Không có owner bảo trì code khi framework/protocol đổi phiên bản.

### 21.1. Tối ưu theo yêu cầu, không theo số dòng code

| Nhu cầu thực sự | Extension point ưu tiên |
| --- | --- |
| Credential parsing mới | `AuthenticationConverter` |
| Key/secret verification riêng | `AuthenticationProvider` hoặc verifier service |
| Request matching cho một mechanism | Security chain matcher, `AuthenticationFilter` |
| Authorization tenant/resource | `AuthorizationManager`, method/domain security |
| Custom 401/403 body | Entry point/failure handler/access denied handler |
| Request audit | Observability/filter/interceptor phù hợp |
| Stateless HTTP HMAC per-request body signing | Wrapper + framework mechanism hoặc custom filter mỏng |
| Large streaming payload | Streaming contract/gateway design, không in-memory filter mặc định |
| Reactive WebFlux | Reactive `SecurityWebFilterChain`/`WebFilter`, không Servlet filter |

### 21.2. Có thể dùng custom filter mà vẫn giữ converter/provider

Không cần lựa chọn “hoặc hoàn toàn built-in, hoặc tự viết tất cả”. Có thể để một specialized Servlet Filter **chỉ wrap raw body/normalize trusted edge metadata**, sau đó `AuthenticationFilter` và provider kiểm signed request. Hoặc custom HMAC filter gọi `AuthenticationManager` và để provider thực hiện crypto.

Quan trọng là xác định rõ **ai sở hữu credential parsing, crypto verification, nonce admission, SecurityContext và authorization** để không chạy trùng, bỏ sót hoặc thay đổi trust assumptions.

## 22. Ba tình huống quyết định kiến trúc

### Tình huống A — REST API đã có OAuth2 Bearer JWT

Yêu cầu: Bên thứ ba truy cập `GET /api/reports` bằng JWT issuer đáng tin. Token có scope/tenant claims được xác minh theo issuer, signature, expiry và audience.

**Lựa chọn:** Dùng Spring Security OAuth2 Resource Server, kiểm scopes/audience và tenant authorization. Không tự viết một filter mới để parse `Authorization: Bearer ...` nếu cơ chế chuẩn đáp ứng yêu cầu.

**Lý do:** Tránh tự triển khai key discovery/rotation, token validation, error handling và SecurityContext lifecycle; giảm code security tùy biến.

### Tình huống B — Partner webhook ký raw body bằng HMAC

Yêu cầu: Partner gửi `POST /webhooks/partner-a`, ký method, path, timestamp, nonce và raw payload. Server phải chặn replay, giữ body không đổi cho webhook controller và có key rotation.

**Lựa chọn:** Một HMAC verification component tại security boundary là hợp lý. Bắt đầu với `AuthenticationFilter` + converter/provider **nếu** body handling có thể được giải quyết an toàn. Nếu cần bounded body capture + downstream replay wrapper ngay tại Servlet edge, dùng **custom OncePerRequestFilter mỏng** và một verifier service riêng.

**Điều kiện kiểm thử:** Full tag, raw bytes, header duplicates, key rotation, timestamp/nonce, fail closed, proxy signing boundary, body replay và downstream authorization.

### Tình huống C — Client HMAC hợp lệ nhưng không có quyền tenant B

Yêu cầu: Request ký đúng dưới client A nhưng path trỏ `/v1/tenants/tenant-B/orders`.

**Lựa chọn:** Authentication vẫn do HMAC mechanism hiện có. Tenant access thuộc **authorization/domain policy**, không cần một authentication filter thứ hai. Deny nếu principal A không có grant/object rights trên tenant B.

**Lý do:** HMAC đúng chỉ chứng minh khả năng dùng key A. Nó không chứng minh tenant B đã cấp quyền.

### Tình huống D — mTLS do gateway terminate

Yêu cầu: Gateway xác minh client certificate, backend cần trusted client identity.

**Lựa chọn:** Dùng integration mTLS/X.509 hoặc trusted gateway assertion đã được bảo vệ, có thể bằng Spring Security pre-auth mechanism tương ứng. Không viết filter tin mọi giá trị `X-Client-Cert` do Internet tự khai.

**Điều kiện:** Gateway strip caller-supplied headers, xác thực internal connection, bảo vệ direct backend access và hỗ trợ certificate lifecycle/rotation.

### Tình huống E — Chỉ cần quota theo client

Yêu cầu: Mỗi client có giới hạn RPS khác nhau.

**Lựa chọn:** Authentication xác định trusted principal trước, sau đó rate limit/quota layer dùng principal hoặc tenant policy. Không tạo một HMAC authentication filter mới chỉ để đếm requests.

### Tình huống F — Dữ liệu ký lớn, endpoint streaming

Yêu cầu: Upload file lớn với HMAC integrity.

**Lựa chọn:** Thiết kế streaming/gateway signing protocol và verify theo data-flow thực tế. Một custom filter đọc hết body vào heap trước controller **không** là giải pháp mặc định.

## 23. Ma trận kiểm thử quyết định có cần custom filter

| Quyết định/điều kiện | Test hoặc bằng chứng cần có |
| --- | --- |
| Chọn JWT Bearer thay custom | OAuth2 Resource Server xác minh issuer/audience/expiry/scope |
| Chọn converter/provider thay filter | Trích credential, verify, error và context lifecycle đúng |
| Chọn OncePerRequestFilter | Có yêu cầu HTTP boundary thực sự không giải quyết sạch bằng extension points |
| Chọn body wrapper | Verifier và controller đọc cùng raw bytes; giới hạn kích thước |
| Chọn security chain riêng | HMAC required routes không bypass bằng catch-all/Bearer |
| Filter ordering | Authentication xảy ra trước authorization |
| Filter registration | Một request không làm verify hai lần |
| Unknown key | No fallback, generic reject |
| Key revoked | Correct MAC vẫn reject |
| Cross-client secret | Key A và secret B không mạo danh A |
| Cross-tenant access | HMAC A đúng, tenant B unauthorized phải deny |
| Signed metadata | Key ID/timestamp/nonce là signed fields |
| Canonical method/path/query | Signed semantics bằng handler semantics |
| Header duplicates | Reject tại ingress ngay cả HTTP header names khác case |
| Body bytes | Không reserialize JSON rồi dùng digest khác |
| Body > limit | Reject trước cấp phát/handler lớn |
| Full HMAC tag | Strict Base64URL decode, 32-byte compare |
| Timestamp boundaries | Past age/future skew đúng, server clock |
| Nonce store | Atomic admission giữa pods, TTL đủ, fail closed |
| Gateway retries | Same nonce không double-admit |
| Async/error dispatch | Không vô tình verify lại bằng cùng nonce hoặc mất principal |
| Secret manager outage | Không dùng default/cached invalid secret |
| Cache stale after revoke | Không chấp nhận key cũ ngoài revocation guarantee |
| Response errors | Không leak secret/expected tag/key state ngoài policy |
| Audit | Failure reason rõ nhưng không chứa replayable request |
| SecurityContext | Không leak principal giữa requests/threads |
| Authorization | Filter success không bypass resource policy |
| WebFlux vs Servlet | Dùng đúng stack security integration |
| Streaming uploads | Có architecture/acceptance criteria riêng |

## 24. Bài tập thực hành

### Bài tập 1 — Chọn extension point

Bạn có ba APIs: (a) JWT Bearer chuẩn, (b) HMAC ký body theo contract riêng, (c) Bearer token đúng nhưng cần kiểm quyền tenant. Với mỗi API, chọn cơ chế Spring Security phù hợp và giải thích tại sao có/không cần custom Servlet Filter.

### Bài tập 2 — Chỉ sử dụng AuthenticationConverter/Provider

Viết một converter parse `keyId`, `timestamp`, `nonce` và signature thành unauthenticated token. Provider gọi trusted HMAC verifier và trả Authentication từ registry. Mô tả cách xử lý raw body để controller vẫn đọc được body sau khi converter hoàn thành.

### Bài tập 3 — OncePerRequestFilter mỏng

Sử dụng skeleton `HmacAuthenticationFilter`. Viết fake `HmacHttpVerificationService`. Assert filter thiết lập principal bên trong chain, ngừng chain khi verifier ném `BadCredentialsException`, và xóa SecurityContext sau request.

### Bài tập 4 — Bảo vệ body

Tạo POST với raw bytes `B`. Verifier tính digest chính xác `SHA256(B)`; controller phải nhận đúng `B`. Test empty body, Unicode, whitespace JSON, max size/max+1, body đã bị pre-filter tiêu thụ.

### Bài tập 5 — Header ambiguity

Gửi hai fields `X-Key-Id` khác case qua gateway thật. Assert ingress reject trước khi backend chọn key. Kiểm `Authorization` duplicates và `Content-Length`/`Transfer-Encoding` ambiguity nếu môi trường hỗ trợ raw requests.

### Bài tập 6 — Cross-client secret

Đăng ký key A3/secret KA3, B1/secret KB1. Gửi request khai A3 nhưng HMAC bằng KB1; hệ thống phải reject mà không thử KB1. Đổi A3 thành REVOKED và gửi tag đúng dưới KA3; vẫn reject.

### Bài tập 7 — Timestamp/nonce

Dùng `Clock.fixed` để test timestamp quá cũ/quá tương lai và nonce trùng. Tạo 50 concurrent requests cùng nonce qua ít nhất hai verifier pods và một shared replay store. Kiểm at most one admission theo guarantee.

### Bài tập 8 — Lỗi registry/replay

Registry timeout hoặc replay store UNKNOWN. Kiểm không tạo authenticated principal, không gọi controller, không ghi side effect. Log reason code đã redacted, response không chứa secret/expected tag.

### Bài tập 9 — Filter ordering

Tạo hai `SecurityFilterChain`: một HMAC ở `/signed-api/**` và một Bearer route khác. Viết tests chứng minh HMAC endpoint không bị match bởi catch-all chain, filter không chạy hai lần và Bearer-only request không bypass HMAC.

### Bài tập 10 — Proxy rewrite

Client ký `/public/v1/orders` còn backend nhận `/v1/orders`. Chọn một signing boundary và test request end-to-end qua gateway. Không thử nhiều path variants cho tới khi một tag khớp.

### Bài tập 11 — Authorization sau authentication

Client A ký request đúng nhưng truy cập resource tenant B. HMAC filter có thể tạo principal A; authorization phải deny B. Thử lại với một trusted delegated grant B để minh họa cơ chế policy riêng.

### Bài tập 12 — Async/error dispatch

Dùng Servlet async hoặc streaming response. Kiểm filter không claim nonce lần hai khi error/async dispatch, context được truyền an toàn và authorization có được re-check theo tenant revocation policy.

### Bài tập 13 — Code review

Review một filter có các lỗi: `readAllBytes()` vô hạn, parser dùng `getHeader` bỏ duplicate, secret mặc định, `String.equals` cho tag, local `HashSet` nonce, catch `Exception` rồi `chain.doFilter`. Liệt kê từng threat và đề xuất extension point/service thích hợp.

### Bài tập 14 — Thiết kế test suite theo rủi ro

Phân loại tests thành: pure crypto/canonical fixtures, verifier + fake stores, filter unit, MVC/security chain integration, gateway HTTP integration, multi-node failover, incident rotation/revocation. Xác định ít nhất một invariant cho từng tầng.

## 25. Checklist trước khi chọn custom authentication filter

### 25.1. Quyết định kiến trúc

- [ ] Đã phân biệt rõ **authentication** với authorization, input validation và audit.
- [ ] Đã xem xét các cơ chế Spring Security sẵn có (OAuth2/JWT, Basic, form login, X.509/mTLS).
- [ ] Đã xem xét `AuthenticationFilter` + `AuthenticationConverter` + `AuthenticationProvider`.
- [ ] Có lý do cụ thể cần xử lý **HTTP boundary** (body/canonical URI/header parser/gateway) mà extension points đơn giản không đáp ứng sạch.
- [ ] Nếu chỉ cần custom 401 response, chọn EntryPoint/FailureHandler thay vì viết full filter.
- [ ] Nếu chỉ cần tenant/resource permission, dùng authorization policy/domain service.
- [ ] Nếu dùng WebFlux, chọn reactive filter chain thay vì Servlet `OncePerRequestFilter`.
- [ ] Đã mô tả signing boundary, trust boundaries và các assumption về proxy/gateway.
- [ ] Đã chỉ định owner cho key registry, HMAC verifier, replay store và incident response.
- [ ] Có test plan và người chịu trách nhiệm bảo trì khi nâng version Spring Security.

### 25.2. Spring Security integration

- [ ] HMAC-required endpoints khớp đúng `SecurityFilterChain`.
- [ ] Catch-all chain không bypass required HMAC chain.
- [ ] Authentication xảy ra trước authorization.
- [ ] Filter không auto-register kép ở container và security chain.
- [ ] Filter chạy đúng một lần theo intended Servlet dispatch policy.
- [ ] Failure ngừng filter chain, không chuyển tiếp sang controller.
- [ ] Authentication result đáng tin mới tạo `SecurityContext`.
- [ ] SecurityContext được cleanup và không leak giữa requests/threads.
- [ ] Exception ở early filter được xử lý bằng EntryPoint/FailureHandler phù hợp.
- [ ] Downstream exceptions không bị custom auth filter che thành “bad MAC”.
- [ ] Stateless/session persistence policy phù hợp; không vô tình lưu HMAC identity vào session trái thiết kế.
- [ ] CSRF policy được đánh giá theo browser/cookie threat model, không disable chỉ theo thói quen.
- [ ] Async/error dispatch và reactive/Servlet stack đúng contract.

### 25.3. HTTP/HMAC protocol

- [ ] Exact key ID từ request được strict parse, không trim/lowercase/alias ngoài contract.
- [ ] Duplicate `Authorization`/`X-Key-Id`/mandatory signed headers được reject tại trusted ingress.
- [ ] Canonical request version, LF/UTF-8, method/path/query/header/body rules rõ.
- [ ] Key ID, timestamp, nonce và relevant audience/headers được signed.
- [ ] Body digest server tính từ raw body bytes và verifier/body handler thấy cùng bytes.
- [ ] Body buffering có giới hạn, replay wrapper hoạt động đúng; large streams có design riêng.
- [ ] Proxy/gateway không làm đổi signed semantics ngoài contract.
- [ ] Key registry exact-match, một ID → một record/secret/version; no fallback.
- [ ] Algorithm và audience là server-side policy, không chọn tùy ý từ header caller.
- [ ] Credential ACTIVE/RETIRING/REVOKED/expired được kiểm đúng.
- [ ] Full HMAC-SHA256 32-byte tag được strict decode và so bằng primitive phù hợp.
- [ ] Timestamp freshness dùng server clock, có past age/future skew rõ.
- [ ] Nonce replay claim atomic trên shared authority, TTL bao phủ window.
- [ ] Replay store uncertainty, secret manager timeout và registry outage đều fail closed.
- [ ] HMAC hợp lệ không bỏ qua tenant/resource authorization hoặc business idempotency.

### 25.4. Testing, observability và vận hành

- [ ] Có HMAC known-answer test vectors (ví dụ RFC 4231) độc lập với code production.
- [ ] Có golden canonical request bytes fixtures, bao gồm Unicode/URI/header/body cases.
- [ ] Có unit tests cho converter, provider/verifier và filter failure/success paths.
- [ ] Có Spring Security chain integration tests, không chỉ `@WithMockUser`.
- [ ] Có raw HTTP gateway tests cho duplicate fields, rewrite và request smuggling ambiguity.
- [ ] Có body replay test bằng raw bytes, empty/max/max+1 và streaming policy.
- [ ] Có cross-client, tenant denial, key rotation/revocation, clock/nonce tests.
- [ ] Có concurrency/failover tests cho shared replay authority và credential state cache.
- [ ] Có tests cho async/error dispatch, multiple filter registration và unexpected errors.
- [ ] Public errors không lộ secret, expected HMAC, key status hay full replayable request.
- [ ] Logs/metrics không nhận unbounded raw key IDs thành labels.
- [ ] Incident runbook có emergency revoke, secret rotation và kiểm mọi verifier paths.

## 26. Câu hỏi tự kiểm tra

1. **Custom filter là gì?** Một filter do ứng dụng triển khai để xử lý logic HTTP ở chuỗi Servlet/Spring Security, thường cho cơ chế xác thực khác mặc định.
2. **Mọi API có business policy riêng đều cần custom authentication filter không?** Không; nhiều policy thuộc authorization hoặc domain service.
3. **Nếu dùng Bearer JWT chuẩn thì ưu tiên gì?** Spring Security OAuth2 Resource Server thay vì tự parse JWT bằng filter mới.
4. **Nếu chỉ cần lấy credential ở header lạ?** Xem xét `AuthenticationConverter` và provider với `AuthenticationFilter`.
5. **Nếu chỉ đổi response 401?** `AuthenticationEntryPoint` hoặc failure handler.
6. **Khi nào OncePerRequestFilter phù hợp?** Khi có HTTP boundary concern thật sự như body replay/strict signed request handling không giải quyết gọn bằng extension points.
7. **Vì sao HMAC cần xử lý trước controller?** Phải xác minh method/URI/headers/body trước khi business dựa trên chúng hoặc tạo side effects.
8. **Controller có thể đọc lại body sau khi filter tiêu thụ stream không?** Không tự động; cần body-replay wrapper hoặc architecture khác.
9. **ContentCachingRequestWrapper tự rewind body không?** Không mặc định; nó cache khi body được đọc, không chủ động replay.
10. **Có nên đọc all body bytes không giới hạn?** Không; cần memory/size limits và streaming design cho uploads lớn.
11. **Key ID là principal chưa?** Không; chỉ là untrusted selector cho registry lookup.
12. **HMAC đúng có nghĩa đã được phép trên mọi tenant không?** Không; authorization kiểm tenant/resource/action riêng.
13. **Tại sao key ID phải được ký?** Ràng buộc credential selector vào canonical request, giảm identity confusion.
14. **Khi signature mismatch có nên thử secret khác không?** Không; exact ID chỉ chọn một secret/version.
15. **Nonce mới có thay HMAC verification không?** Không, nonce chỉ là replay gate sau MAC.
16. **Secret bị lộ có bị nonce/timestamp chặn khi attacker ký request mới không?** Không; phải revoke/rotate credential và điều tra.
17. **HMAC comparison nên dùng gì?** Strict full tag decode và primitive như `MessageDigest.isEqual`.
18. **MessageDigest.isEqual có làm toàn verifier constant-time không?** Không; lookup/parser/error timing vẫn có thể khác.
19. **Vì sao không tin X-Forwarded-Host từ Internet?** Nó có thể do caller giả; chỉ trusted gateway context qua boundary có integrity mới đủ.
20. **Servlet header names case-insensitive ảnh hưởng gì?** `X-Key-Id` và `x-key-id` là duplicate field name, cần reject ambiguity.
21. **Tại sao filter có thể chạy hai lần?** Container registration và Spring Security chain registration cùng tồn tại, hoặc dispatch policy không rõ.
22. **OncePerRequestFilter có bảo đảm exactly-once business không?** Không, retry/async và operations mới khác nonce vẫn tồn tại.
23. **Nếu HMAC filter ném AuthenticationException ở trước ExceptionTranslationFilter thì sao?** Phải có failure handling đúng vị trí, không giả định filter phía sau bắt nó.
24. **Có nên bắt Exception rồi tiếp tục chain cho availability?** Không; đó là fail-open.
25. **WebFlux có dùng Servlet OncePerRequestFilter không?** Không; dùng reactive security/WebFilter.
26. **Vì sao test @WithMockUser chưa đủ?** Nó có thể bypass actual HMAC parsing/verification.
27. **MockMvc đã chứng minh gateway rewrite/HTTP2 semantics chưa?** Chưa; cần e2e qua ingress thật.
28. **Nonce store local per pod có đủ không?** Không nếu request có thể tới nhiều pods.
29. **HMAC filter có nên quyết định business idempotency không?** Không; business layer xử lý operation IDs và durable transactions.
30. **Một filter đáng tin có đặc điểm gì?** HTTP adapter mỏng, hợp đồng ký rõ, verifier/service testable, context lifecycle đúng, fail closed, authorization riêng và integration tests đủ ranh giới.

## 27. Tài liệu tham khảo và hướng đọc tiếp

- **Spring Security Reference — Servlet Architecture và SecurityFilterChain.** Cách security filters được tổ chức và match requests.
- **Spring Security Reference — Authentication Architecture.** `Authentication`, `AuthenticationManager`, `AuthenticationProvider` và `SecurityContextHolder`.
- **Spring Security API — AuthenticationFilter, AuthenticationConverter, AuthenticationEntryPoint.** Framework extension points cần cân nhắc trước custom filter.
- **Spring Framework API — OncePerRequestFilter và ContentCachingRequestWrapper.** Servlet dispatch semantics và giới hạn caching request body.
- **Spring Security Reference — OAuth2 Resource Server và Servlet Authorization.** Các lựa chọn sẵn có thay custom authentication filter.
- **Spring Security Test / MockMvc Integration.** Kiểm thử security chains và authentication/authorization flow.
- **Java SE 17 — javax.crypto.Mac, SecretKeySpec, MessageDigest.isEqual, Clock, SecureRandom.** Java crypto/time primitives cho HMAC.
- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Cơ chế MAC đối xứng.
- **RFC 4231 — HMAC-SHA-224/256/384/512 Test Vectors.** Known-answer tests độc lập với implementation.
- **RFC 9110 — HTTP Semantics; RFC 9112 — HTTP/1.1; RFC 9113 — HTTP/2.** HTTP fields, framing và gateway semantics.
- **RFC 3986 — URI Generic Syntax.** Path/query encoding và canonicalization design.
- **OWASP API Security, Authentication và Secrets Management guidance.** Endpoint protection, credential lifecycle, least privilege và logging.

## 28. Tổng kết quyết định

Bạn nên chọn custom filter **chỉ khi** ứng dụng có yêu cầu thực sự ở HTTP security boundary mà mechanisms/extension points sẵn có không đủ rõ ràng. Đối với HMAC request authentication, việc cần xác minh **canonical method/URI/headers/raw body** trước controller và bảo vệ **replay/key lifecycle** là lý do chính đáng để đặt cơ chế xác thực trong security filter chain. Tuy nhiên, điểm mở rộng phù hợp vẫn có thể là **AuthenticationFilter + converter/provider**, kết hợp body wrapper; không phải lúc nào cũng cần tự triển khai `OncePerRequestFilter`.

Nếu cuối cùng cần custom filter, hãy giữ nó **mỏng**: xác định endpoint, tích hợp trusted verifier, đặt SecurityContext sau authentication và dừng chain khi failure. Các lớp độc lập xử lý canonicalization, HMAC, registry, freshness, nonce và key rotation; authorization/tenant/business idempotency ở lớp policy và domain. Khi kiểm thử được raw body, gateway rewrite, filter order, context cleanup, cross-client/tenant isolation và failure cases, filter mới thực sự nâng mức bảo vệ thay vì trở thành điểm yếu mới của HTTP request signing.



