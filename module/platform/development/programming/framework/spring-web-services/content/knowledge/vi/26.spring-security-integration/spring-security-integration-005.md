# Kiểm chứng Authentication, SecurityContext và đường truyền danh tính

> **Chương:** Tích hợp Spring Security  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP theo hướng **contract-first** với Spring Web Services (Spring-WS): thiết kế XSD/WSDL, ánh xạ JAXB/OXM, xây dựng endpoint và SOAP client, xử lý SOAP Fault, interceptor, XML security, WS-Security và chứng chỉ, đồng thời kiểm thử tương thích hệ thống doanh nghiệp.

## 1. Bài toán: xác thực xong, danh tính có thật sự đến đúng nghiệp vụ?

Một hệ thống tích hợp SOAP có thể xác minh thành công chứng chỉ mTLS, UsernameToken hoặc chữ ký WS-Security, nhưng vẫn mắc lỗi bảo mật nếu **danh tính đã xác minh không được đưa đến đúng nơi kiểm tra quyền**. Chẳng hạn, SOAP endpoint gọi service hủy đơn hàng nhưng `SecurityContextHolder` không có `Authentication`, chứa danh tính từ request trước do thread reuse, hoặc mang danh tính do client tự ghi trong SOAP Header.

Chủ đề bài học không chỉ là “làm sao đăng nhập bằng Spring Security”, mà là **kiểm chứng toàn bộ đường truyền danh tính**:

~~~text
Nguồn danh tính được chứng thực
    → Validation / authentication thực tế
    → Authentication object đáng tin
    → SecurityContext đúng request/thời điểm
    → Method security và business authorization
    → Cleanup / propagation đúng qua các thread boundaries
~~~

Nếu một mũi tên bị đứt, có thể xuất hiện hai nhóm lỗi: request hợp lệ bị từ chối vì mất ngữ cảnh; hoặc nguy hiểm hơn, request không hợp lệ được thực thi dưới danh tính **sai hoặc còn sót**.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt `Authentication`, `principal`, `credentials`, `authorities` và `SecurityContext` trong Spring Security.
2. Xác định khi nào HTTP/mTLS authentication **tự đi vào** `SecurityContextHolder` thông qua security filter chain, và khi nào WS-Security/WSS4J **không tự làm điều đó**.
3. Giải thích cách ràng buộc danh tính từ certificate/UsernameToken đã được xác minh với đối tác, tenant, operation và tài nguyên.
4. Thiết kế cơ chế tạo `Authentication` chỉ từ **trusted verification evidence**, không từ SOAP Body/Header tùy ý.
5. Giữ `SecurityContext` đúng phạm vi và dọn sạch khi request hoàn tất, kể cả lỗi hoặc thread pool reuse.
6. Xử lý việc chuyển danh tính sang `@Async`, executor, messaging/outbox mà không rò quyền.
7. Phân biệt **authentication** với **authorization**, và cấu hình `@EnableMethodSecurity`/`@PreAuthorize` để kiểm tra quyền ở service layer.
8. Kiểm thử từ SOAP/HTTP ingress đến business side effects bằng positive/negative tests, không chỉ kiểm tra field `isAuthenticated()`.
9. Nhận biết giới hạn của `@WithMockUser` và `MockWebServiceClient` khi cần chứng minh chữ ký SOAP/mTLS thật.
10. Phân tích sự cố “SecurityContext bị null”, “anonymous dù đã ký SOAP” và “danh tính request A lẫn vào request B”.

**Thông điệp chính:** `SecurityContextHolder` là **nơi lưu ngữ cảnh**, không phải engine xác thực WS-Security. Nó chỉ đáng tin khi quá trình tạo, thiết lập, sử dụng, truyền và dọn `Authentication` đã được kiểm chứng ở mọi đường vào.

## 2. Bản đồ các lớp bảo mật trong SOAP ứng dụng Spring

Một SOAP request có thể có nhiều “danh tính” ở các lớp khác nhau:

~~~mermaid
flowchart TB
    C["SOAP client"]
    T["HTTPS / mTLS peer"]
    F["Spring Security servlet filter chain"]
    M["Spring-WS MessageDispatcherServlet"]
    W["WSS4J inbound token/signature verification"]
    B["Trusted identity bridge / policy"]
    SC["SecurityContextHolder"]
    E["@Endpoint"]
    S["@PreAuthorize Service"]
    C --> T --> F --> M --> W --> B --> SC
    SC --> E --> S
    S --> D["Database / event / business outcome"]
~~~

Đây là **mô hình trách nhiệm**, không phải cam kết thứ tự cố định cho mọi Spring-WS version. Trong servlet stack, Spring Security filter chain thường bao quanh Spring-WS servlet. Tuy nhiên, WSS4J ở tầng SOAP có thể diễn ra sau HTTP filters; nếu yêu cầu danh tính WS-Security cho quyền ở tầng business, phải có cơ chế bridge được thiết kế rõ.

### 2.1. Bốn hệ thống kiểm soát có mục đích riêng

| Lớp | Xác minh điều gì? | Không tự đảm bảo |
|---|---|---|
| HTTPS/mTLS | Kênh mã hóa, certificate server; tùy cấu hình, danh tính certificate client | SOAP Body đã được ký và caller có quyền trên đơn hàng |
| Spring Security HTTP | HTTP authentication/filter chain, URL-based authorization, `SecurityContext` | WSS4J xác minh Body signature nếu không cấu hình |
| Spring-WS/WSS4J | WS-Security tokens, Signature/Encryption/Timestamp, required actions | `SecurityContextHolder` đã chứa principal đúng trong mọi cấu hình |
| Business/method authorization | Principal có quyền thực hiện operation trên tenant/resource | Chữ ký/certificate/HTTP transport hợp lệ từ đầu |

**Không đồng nhất mTLS với WS-Security X.509 signature.** Một certificate được dùng trong TLS handshake không nhất thiết trùng signer certificate ở SOAP Header. Nếu hai danh tính khác nhau, cần policy ràng buộc và xác định trường hợp được phép (gateway ký thay, delegated identity) thay vì dùng danh tính nào có sẵn một cách ngẫu nhiên.

### 2.2. Hai đường hình thành Authentication

**Đường A — HTTP authentication:** Spring Security filter xác thực HTTP Basic, mTLS/X.509 hoặc cơ chế HTTP đã cấu hình rồi thiết lập `Authentication` trong `SecurityContextHolder`. Khi Spring-WS endpoint chạy **trong cùng servlet request thread**, nó thường có thể nhìn thấy context này.

**Đường B — SOAP message authentication:** WSS4J xử lý UsernameToken/chữ ký/Timestamp; kết quả xác minh ở tầng SOAP **không mặc nhiên tương đương một Spring Security Authentication trong SecurityContextHolder**. Cần sử dụng integration được phiên bản hỗ trợ hoặc adapter tin cậy chuyển kết quả đã xác minh thành Spring Security principal.

Không thể giải quyết đường B bằng cách chỉ thêm `@EnableWebSecurity` hoặc `@EnableMethodSecurity` rồi giả định WSS4J sẽ tự xuất hiện trong context. Ngược lại, chỉ thêm WSS4J interceptor cũng không làm `@PreAuthorize` tự biết authorities của signer.

## 3. Authentication là gì: phân biệt danh tính, bằng chứng và quyền

Spring Security sử dụng `org.springframework.security.core.Authentication` làm abstraction cho một yêu cầu xác thực hoặc một danh tính đã xác thực.

### 3.1. Các thuộc tính cần hiểu

| API | Ý nghĩa | Điều cần cảnh giác |
|---|---|---|
| `getPrincipal()` | Đại diện cho subject/principal; có thể là String, `UserDetails` hoặc object tùy ứng dụng | Không mặc định là partner ID hay tenant đáng tin |
| `getCredentials()` | Bằng chứng như password/token; có thể đã bị xóa sau authentication | Không log, không dùng cho business |
| `getAuthorities()` | Authorities do authentication/trust mapping cấp | Không lấy trực tiếp từ input SOAP |
| `isAuthenticated()` | Cờ trạng thái của implementation | **Không tự chứng minh** signature/credential đã được kiểm tra |
| `getDetails()` | Metadata tùy ý của authentication mechanism | Không tự có quyền hạn hay bảo đảm toàn vẹn |
| `getName()` | Tên subject theo implementation | Không tự thay kiểm tra tenant/resource |

`Authentication` có thể chứa **unauthenticated authentication request** khi trước validation. Một số implementations có constructor/factory tạo object được đánh dấu authenticated khi caller truyền authorities. Vì vậy lớp tạo `Authentication` phải nằm **sau trusted verifier**, không cho code xử lý raw SOAP input tự tạo authenticated token.

### 3.2. AnonymousAuthenticationToken là bẫy phổ biến

Trong một số Spring Security configurations, khi chưa có authenticated user, framework có thể tạo `AnonymousAuthenticationToken`. Lưu ý:

- `AnonymousAuthenticationToken#isAuthenticated()` có thể trả `true` theo semantics của class.
- Điều đó **không chứng minh caller đã đăng nhập** hoặc đạt bảo mật WS-Security.
- `AuthenticationTrustResolver`, biểu thức `isAuthenticated()` trong Spring Security authorization và policy hiện đại có thể phân biệt anonymous; không viết check bảo mật bằng cách chỉ gọi `auth != null && auth.isAuthenticated()`.

**Phản ví dụ:**

~~~java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

if (auth != null && auth.isAuthenticated()) {
    // SAI nếu đây là gate duy nhất; anonymous token có thể
    // được đánh dấu authenticated ở mức Authentication.
    orderService.cancelOrder();
}
~~~

Đúng hướng: cấu hình authorization ở Spring Security theo profile, kết hợp trust resolver/authorities, principal-to-tenant mapping và required WS-Security verification. Với operation có side effects, method-level authorization nên kiểm tra quyền cụ thể, không chỉ “authentication tồn tại”.

### 3.3. Authentication không thay business authorization

Giả sử signer đã được xác thực là đối tác `PARTNER_A`. Điều đó chưa đủ để:

- Tải đơn hàng của `PARTNER_B`.
- Hủy đơn đã thuộc tenant khác.
- Đặt `ReplyTo` đến callback URL của đối tác khác.
- Ký thay hoặc đọc tài liệu của người dùng khác.

Một authorization decision cần thông tin:

~~~text
Verified identity
+ Partner / tenant mapping từ registry tin cậy
+ Required SOAP security policy pass
+ Operation authority
+ Ownership/resource policy
+ Request context và business state
= Authorized operation
~~~

Không đọc `tenantId` trong SOAP Body rồi đặt nó thành principal/role mà không kiểm tra với tenant assignments của signer. Một caller hợp lệ vẫn có thể gửi `orderId` không thuộc quyền.

## 4. SecurityContextHolder: nơi lưu và giới hạn vòng đời

`org.springframework.security.core.context.SecurityContextHolder` cung cấp cách truy cập `SecurityContext` hiện hành. Trong ứng dụng servlet thread-based, mặc định thường dùng `ThreadLocal` theo `SecurityContextHolderStrategy`.

### 4.1. Đọc context trong service

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public final class SecurityInspector {

    public static Authentication current() {
        return SecurityContextHolder.getContext()
                .getAuthentication();
    }
}
~~~

Code trên chỉ **đọc** context, không tự thực hiện authentication. `Authentication` có thể null, anonymous hoặc không đủ quyền. Trong production, nên dùng method security và typed principal khi cần, thay vì rải các câu lệnh `SecurityContextHolder.getContext()` khắp nghiệp vụ.

### 4.2. Không gán Authentication vào một shared context

Khi tạo context mới:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

SecurityContext next =
        SecurityContextHolder.createEmptyContext();
next.setAuthentication(authenticatedFromTrustedSource);
SecurityContextHolder.setContext(next);
~~~

`authenticatedFromTrustedSource` là biến **giả định đã được tạo sau trusted verification**, không phải một object xây từ XML đầu vào. Cách tạo `SecurityContext` mới tránh sửa trực tiếp context đang được chia sẻ bởi một cơ chế persistence/session khác.

**Không** làm:

~~~java
// Rủi ro khi context có thể được chia sẻ/truyền từ nơi khác.
SecurityContextHolder.getContext()
        .setAuthentication(untrustedAuthentication);
~~~

đặc biệt khi object được tạo từ `Username`/`Role` do caller tự cung cấp hoặc có context từ HTTP authentication trước đó.

### 4.3. ThreadLocal không tự đi qua mọi thread

~~~mermaid
sequenceDiagram
    participant F as Spring Security Filter
    participant T as HTTP request thread
    participant X as Async executor thread
    F->>T: Establish request SecurityContext
    T->>T: Invoke SOAP endpoint
    T->>X: Submit task
    Note over X: ThreadLocal mặc định không tự theo task
    X-->>T: Result or completion
    T->>F: Request completes
    F->>F: Context cleanup theo filter lifecycle
~~~

Nếu code gọi `CompletableFuture.supplyAsync(...)` hay `@Async` mà không thiết kế context propagation, worker thread có thể **không có danh tính**. Nếu tự dùng global static field hoặc `MODE_INHERITABLETHREADLOCAL` với thread pool, có thể dẫn tới **danh tính cũ bị giữ lại** hoặc lan ngoài phạm vi cần thiết.

### 4.4. Gắn context mới phải có cleanup

Một đoạn code set context nhưng không restore/clear trong `finally` có thể khiến worker thread tái sử dụng mang danh tính của request trước:

~~~java
// PHẢN VÍ DỤ:
SecurityContextHolder.setContext(contextForPartnerA);
performBusiness();
 // Thiếu finally restore / clearContext.
~~~

Phương án cho **một phạm vi đồng bộ, giới hạn rõ**:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import java.util.function.Supplier;

public final class ScopedSecurityContext {

    private ScopedSecurityContext() {}

    public static <T> T callAs(
            Authentication trustedAuthentication,
            Supplier<T> action) {

        if (trustedAuthentication == null) {
            throw new SecurityException(
                    "Trusted authentication is required");
        }

        SecurityContext previous =
                SecurityContextHolder.getContext();

        SecurityContext replacement =
                SecurityContextHolder.createEmptyContext();
        replacement.setAuthentication(trustedAuthentication);

        try {
            SecurityContextHolder.setContext(replacement);
            return action.get();
        } finally {
            SecurityContextHolder.setContext(previous);
        }
    }
}
~~~

Đây là **helper giới hạn vòng đời context**, không phải verifier. Chỉ code trusted adapter sau authentication mới được gọi nó với một `Authentication` đáng tin. Restore context trước đó thay vì luôn `clearContext()` vì có thể tồn tại HTTP authentication đã hợp lệ của request đang bao quanh. Nếu scope bắt đầu từ background worker không có context, việc restore một empty context cũng cần được kiểm soát và executor phải có cleanup theo lifecycle.

**Cảnh báo:** nếu `action` kích hoạt công việc bất đồng bộ rồi trả về ngay, context trong task đó **không được bảo đảm** bởi helper này. Hãy dùng explicit propagation hoặc công việc tách biệt có danh tính/authorization của nó.

## 5. Nguồn danh tính: HTTP, mTLS, WS-Security và gateway

### 5.1. Đường danh tính từ HTTP filters

Trong một ứng dụng Spring Boot servlet, chuỗi lọc do Spring Security quản lý thường chạy **trước** `MessageDispatcherServlet`. Nếu HTTP authentication đã được cấu hình:

~~~text
POST /ws/orders
    → SecurityFilterChain
    → AuthenticationManager / provider
    → SecurityContext for servlet request
    → MessageDispatcherServlet
    → Spring-WS EndpointMapping / Endpoint
    → Method security / business
~~~

Đây là hình ảnh khái quát; Spring Security version mới có cơ chế `SecurityContextHolderFilter`, repository và authentication filters cụ thể. Không giả định context được tự lưu bền vững trong session nếu ứng dụng đã chọn stateless. **Dữ liệu nhận từ mTLS client cert** có thể được xác thực ở HTTP layer và ánh xạ thành principal nếu filter/config có thực, nhưng chỉ cấu hình TLS yêu cầu certificate tại web server chưa có nghĩa Spring Security đã xây được `Authentication`.

### 5.2. Đường danh tính từ WSS4J

~~~text
SOAP Envelope
    → Spring-WS message factory
    → WSS4J validates token/signature/timestamp
    → Verified signer / token identity from trusted result
    → Application-approved partner/tenant/authorities mapping
    → Spring Security Authentication (trusted bridge)
    → SecurityContext for bounded business invocation
    → Method security + business
~~~

Một `wsse:Security` tồn tại không tự tạo `Authentication`. Phải kiểm tra những hành động bắt buộc như Signature, UsernameToken, Timestamp có được xác minh thật, signer certificate có được trust, signed parts bao phủ đúng Body, và token/replay policy có đạt hay không. Một library có thể xác nhận chữ ký mật mã hợp lệ nhưng signer **không được cấp quyền** gọi operation.

### 5.3. Khi HTTP và SOAP cùng có danh tính

Giả sử TLS kết thúc tại gateway được xác thực là `GATEWAY_1`, còn `wsse:Signature` đại diện cho `PARTNER_A`. Không thể tự coi hai danh tính “không khớp” là tấn công, vì đây có thể là mô hình delegation được thiết kế trước. Nhưng cũng không được để gateway hoặc client tự đổi principal mà không policy.

Cần chính sách binding:

| Vấn đề | Quyết định phải có |
|---|---|
| HTTP identity | Gateway/service principal hoặc direct client certificate? |
| SOAP identity | Signer của Body/required Headers, UsernameToken subject? |
| Identity authority | Ai được chứng thực business principal? |
| Delegation | Gateway nào được phép chuyển lời cho partner/tenant nào? |
| Mismatch | Khi nào reject, khi nào delegation hợp lệ? |
| Audit | Ghi cả transport principal và business principal **sau verification**, không ghi secret |
| Authorization | Dùng principal nào kiểm tra ownership/resource? |
| Revocation | Certificate/partner entitlement thay đổi ảnh hưởng session/callback ra sao? |

Bản thân HTTP Header `X-Partner-Id` hoặc SOAP Header `<PartnerId>` **không phải chứng cứ authentication**, trừ khi nó nằm trong cơ chế đã được bảo vệ, verified và mapped theo chính sách.

### 5.4. Không giả định HTTPS bảo vệ toàn bộ thông điệp qua trung gian

TLS bảo vệ từng kết nối, có thể terminate tại proxy. WS-Security có thể cung cấp integrity/confidentiality ở mức message qua trung gian theo policy, nên một hệ thống nhiều hop phải xác định rõ **ai là trusted transport peer** và **ai là signed message author**. Spring Security `Authentication` nên đại diện cho identity được chọn một cách **có chủ đích**, không phải trường XML dễ truy cập nhất.

## 6. Cấu hình SecurityFilterChain cho HTTP SOAP ingress

Trong ứng dụng servlet, Spring Security filter chain thường xử lý HTTP authentication **trước** `MessageDispatcherServlet`. Ví dụ khi contract yêu cầu cả mTLS và WS-Security:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SoapHttpSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain soapHttpChain(HttpSecurity http)
            throws Exception {

        http.securityMatcher("/ws/**")
            .authorizeHttpRequests(auth ->
                    auth.anyRequest().authenticated())
            .x509(Customizer.withDefaults())
            .sessionManagement(session ->
                    session.sessionCreationPolicy(
                            SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable());

        return http.build();
    }
}
~~~

Đây là **khung cấu hình HTTP**, chưa đủ để chạy mTLS trong production. Còn phải cấu hình:

- HTTPS và yêu cầu client certificate tại container/TLS termination point.
- Trust chain, certificate revocation policy (nếu bắt buộc), TLS SAN/hostname.
- X.509 authentication provider/`UserDetailsService` ánh xạ certificate subject hoặc danh tính đã xác minh thành principal/authorities **do server quản lý**.
- `securityMatcher("/ws/**")` bao phủ **mọi SOAP URL thực**; có chain an toàn cho các routes khác.
- Chỉ loại trừ CSRF trên **SOAP stateless/machine-to-machine** paths khi đã phân tích client/authentication model; không tắt CSRF toàn web UI dùng session/cookies.
- WSS4J interceptor riêng nếu SOAP message còn bắt buộc chữ ký/Timestamp/UsernameToken.

`@EnableMethodSecurity` bật method authorization, không tự verify SOAP signature hoặc cấp authorities. `SessionCreationPolicy.STATELESS` không đồng nghĩa request tự có Authentication và không thay cleanup ThreadLocal.

### 6.1. Nếu chỉ dùng WS-Security, không có HTTP authentication

Với SOAP service mà **chỉ** WSS4J xác thực incoming message, cấu hình `anyRequest().authenticated()` ở HTTP filter chain có thể chặn request **trước khi WSS4J xử lý**. Khi ấy, đường vào HTTP cần được thiết kế để đưa request tới SOAP verifier, nhưng **mọi business operation được bảo vệ vẫn phải fail closed** khi thiếu/không đạt security policy.

Một cấu hình HTTP `permitAll` riêng cho SOAP ingress **không tự bảo vệ service**. Chỉ nên áp dụng khi đội phát triển chứng minh bằng tests rằng:

1. Mọi protected operation đều đi qua WSS4J gate bắt buộc.
2. Request thiếu `wsse:Security`, signature sai, token hết hạn và wrong signer bị từ chối.
3. Không có EndpointMapping, URL alias hoặc alternate transport bypass.
4. Business services vẫn kiểm tra authorization và ownership.
5. HTTP/TLS/gateway có limits, chống XXE và quy tắc egress phù hợp.

Một design thường xuyên thay đổi giữa mTLS-only, WS-Security-only và kết hợp cần lập policy matrix rõ. Không “fix HTTP 401” bằng cách bỏ toàn bộ security filters hoặc vô hiệu hóa WSS4J.

### 6.2. HTTP route không phải SOAP operation

Hai requests cùng POST tới `/ws/orders` có thể chứa `GetOrder` và `CancelOrder`. HTTP `SecurityFilterChain` chọn theo URL/HTTP context, còn `EndpointMapping` chọn SOAP handler dựa trên PayloadRoot, SOAPAction hoặc WS-Addressing (tùy cấu hình). Vì vậy bảo vệ còn cần:

- WS-Security required actions và signed coverage theo SOAP operation.
- Business authorities riêng như `ORDER_READ`/`ORDER_WRITE`.
- Authorization resource-level: cùng có `ORDER_WRITE` cũng không được hủy đơn tenant khác.

Không lấy SOAPAction hoặc tên element do caller khai báo làm quyền cho phép bỏ authentication.

## 7. Bridge kết quả WS-Security đã xác minh thành Authentication

### 7.1. Dữ liệu đầu vào cho bridge phải có provenance tin cậy

Giả sử WSS4J đã verify đủ: Signature/Timestamp hoặc UsernameToken, signed references bảo vệ **đúng SOAP Body**, signer/key trust hợp lệ, thời gian/replay đúng policy. Tầng tích hợp **sau verify** mới có thể tạo identity object.

~~~java
package com.example.orders.security;

// Đối tượng nội bộ đại diện kết quả xác minh, KHÔNG phải DTO JAXB.
public record VerifiedSoapIdentity(
        String verifiedSignerId,
        String partnerId,
        String tenantId) {
}
~~~

Một `record` public không tự chống giả mạo: code khác vẫn tạo được object. Production cần giới hạn API/constructor/factory hoặc module boundary để chỉ **trusted WSS4J integration** có thể cấp identity; không bao giờ deserialize `VerifiedSoapIdentity` trực tiếp từ SOAP Body/Header. Verification kết quả phải ràng buộc signer identity với partner/tenant authoritative registry.

### 7.2. AuthenticationManager và PreAuthenticatedAuthenticationToken

Sau khi có trusted identity, Spring Security có `PreAuthenticatedAuthenticationToken` để biểu diễn credential đã được hệ thống khác verify, rồi map sang principal/authorities bằng provider tin cậy:

~~~java
package com.example.orders.security;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;

public final class VerifiedSoapAuthenticationAdapter {
    private final AuthenticationManager authenticationManager;

    public VerifiedSoapAuthenticationAdapter(
            AuthenticationManager authenticationManager) {
        this.authenticationManager = authenticationManager;
    }

    public Authentication authenticateVerified(
            VerifiedSoapIdentity trustedIdentity) {
        if (trustedIdentity == null) {
            throw new SecurityException(
                    "Verified SOAP identity required");
        }

        // Token hai tham số chưa được đánh dấu authenticated.
        var request = new PreAuthenticatedAuthenticationToken(
                trustedIdentity, null);

        Authentication authenticated =
                authenticationManager.authenticate(request);

        if (authenticated == null
                || !authenticated.isAuthenticated()) {
            throw new SecurityException(
                    "SOAP authentication failed");
        }

        return authenticated;
    }
}
~~~

Đây là **mẫu bridge**, không phải cryptographic verifier. `AuthenticationManager` phải dùng provider xử lý `PreAuthenticatedAuthenticationToken`, xác thực ràng buộc signer/partner/tenant và cấp authorities từ registry của server. Một attacker **không được** có cách đưa input bất kỳ thành `VerifiedSoapIdentity` của adapter này.

### 7.3. Ví dụ pre-auth provider mapping

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;

@Configuration
class SoapPreAuthConfig {

    @Bean
    AuthenticationManager soapAuthenticationManager(
            PartnerUserDirectory partnerUserDirectory) {
        var provider = new PreAuthenticatedAuthenticationProvider();

        provider.setPreAuthenticatedUserDetailsService(token -> {
            if (!(token.getPrincipal()
                    instanceof VerifiedSoapIdentity identity)) {
                throw new IllegalArgumentException(
                        "Trusted SOAP identity required");
            }

            return partnerUserDirectory.loadUserForVerifiedSigner(
                    identity.verifiedSignerId(),
                    identity.partnerId(),
                    identity.tenantId());
        });

        return new ProviderManager(List.of(provider));
    }
}
~~~

`PartnerUserDirectory` là **interface ứng dụng tự triển khai**, trả `UserDetails` sau khi kiểm tra trusted signer, partner active, tenant assignment, certificate/key revocation/entitlements. Đoạn code không tự lấy WSS4J result; integration đó phụ thuộc **Spring-WS/WSS4J version, token type và security profile thực**.

Nếu có nhiều `AuthenticationManager`, dùng qualifier để không nhầm HTTP manager với SOAP pre-auth manager. Không để provider nhận `Username`/`Role`/`tenantId` trực tiếp từ Body mà không mapping.

### 7.4. Tạo context cho bounded business invocation

Sau khi WSS4J verification đã hoàn thành:

~~~java
Authentication authenticated =
        soapAuthenticationAdapter.authenticateVerified(
                trustedIdentityFromWss4jResult);

SubmitOrderResponse response =
        ScopedSecurityContext.callAs(
                authenticated,
                () -> orderService.submitOrder(request));
~~~

`trustedIdentityFromWss4jResult` phải là evidence do trusted adapter tạo. `orderService` là Spring bean riêng có method-security proxy. Helper `ScopedSecurityContext` ở mục 4 chỉ bảo vệ **phạm vi đồng bộ**, restore context cũ trong `finally`; nó không tự chuyển sang `@Async` task hoặc hàng đợi.

### 7.5. Khi đã có Spring-WS/Spring Security integration sẵn

Một số Spring-WS/WSS4J configurations có integration callback handlers hỗ trợ Spring Security. Không tự tạo bridge trùng khi integration đã làm việc đó. Thay vào đó, cần xác minh:

- Authentication được tạo **sau credential/signature verification**.
- Authorities đến từ registry, không phải SOAP claims tự khai.
- Thread/request cleanup đúng, không rò sang HTTP request kế tiếp.
- Missing Security Header và failed signature làm business service bị chặn.
- Context dùng bởi endpoint và service là context **của cùng verified sender**.

Đừng suy từ tên class “Security” mà coi context đã đúng; phải test behavior end-to-end.

## 8. Method security và business authorization

### 8.1. Bật Spring Security method authorization

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

`@EnableMethodSecurity` hoạt động qua Spring AOP/proxy. Khi method được gọi qua Spring-managed bean, `@PreAuthorize` có thể kiểm tra `Authentication` hiện hành. **Self-invocation** (`this.securedMethod(...)`) và đường gọi không đi qua proxy có thể bypass advice; vì vậy cần test chính cấu trúc dependency thực.

### 8.2. Quyền trên operation và tài nguyên

~~~java
package com.example.orders.service;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "hasAuthority('ORDER_WRITE') " +
        "and @orderAccess.canWrite(authentication, #orderId)")
    public SubmitOrderResponse submitOrder(
            @P("orderId") String orderId,
            SubmitOrderRequest request) {

        // Re-check ownership/trạng thái dưới transaction nếu
        // business operation có side effect và dễ bị race.
        return orders.submit(orderId, request);
    }
}
~~~

`OrderRepository`, `SubmitOrderRequest`, `SubmitOrderResponse` là classes **giả định** của ứng dụng. `@P("orderId")` giúp biểu thức SpEL lấy tham số ổn định ngay cả khi không có metadata compiler parameter names.

Bean authorization:

~~~java
package com.example.orders.service;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("orderAccess")
public class OrderAccess {

    private final PartnerOrderPolicyRegistry policy;

    public OrderAccess(PartnerOrderPolicyRegistry policy) {
        this.policy = policy;
    }

    public boolean canWrite(
            Authentication authentication, String orderId) {
        if (authentication == null || orderId == null) {
            return false;
        }

        return policy.isOrderWritableBy(
                authentication.getName(), orderId);
    }
}
~~~

`PartnerOrderPolicyRegistry` là component giả định; phải dùng **authoritative principal/tenant-resource binding** từ server, không chỉ tìm `orderId` trong SOAP request rồi tin thuộc tính `tenantId` caller khai báo.

Lời gọi sau authentication:

~~~java
SubmitOrderResponse result =
    ScopedSecurityContext.callAs(authenticated, () ->
        orderService.submitOrder(request.getOrderId(), request));
~~~

**Chú ý:** `Authentication#getName()` phải ánh xạ đến principal ID tin cậy. Với principal đa tenant, nên có `PartnerPrincipal` typed và policy dựa trên partner+tenant, không suy tenant từ một String ngẫu nhiên. Method security không thay việc kiểm tra business state trong transaction (TOCTOU).

### 8.3. Check quyền nào ở đâu?

| Kiểm soát | Tầng phù hợp |
|---|---|
| HTTPS/mTLS, HTTP auth | Security filter chain/transport |
| WS-Security Signature, Timestamp | WSS4J/WS-Security |
| Mapping signer → partner/tenant/authorities | Trusted authentication adapter/provider |
| `ORDER_WRITE` authority | Spring method authorization |
| Đơn hàng thuộc tenant/principal? | Authorization service/database |
| Đơn đã được hủy hoặc xử lý? | Business state/transaction |
| Retry/idempotency | Domain service/outbox policy |

**Đừng dùng `auth.isAuthenticated()` làm điều kiện duy nhất** cho thao tác có side effects, vì anonymous authentication implementations có thể báo authenticated ở mức object. Dùng authoritative principal mapping, roles/authorities và resource policy.

## 9. Vòng đời SecurityContext: request, exception và thread reuse

### 9.1. Phạm vi context phải được xác định rõ

Trong servlet stack, Spring Security tạo/lấy context quanh HTTP request và dọn theo lifecycle của filter. Spring Security 6 có `SecurityContextHolderFilter` và `SecurityContextRepository` với semantics lưu context riêng; không suy rằng một lần `setContext` tự lưu vào HTTP session.

Khi SOAP identity được gắn bên trong endpoint, scope của nó có thể ngắn hơn HTTP request:

~~~mermaid
sequenceDiagram
    participant F as HTTP Security Filter
    participant E as Spring-WS Endpoint
    participant B as Trusted SOAP bridge
    participant S as Secured Service
    F->>E: Transport context
    E->>B: WSS4J verified signer evidence
    B->>B: AuthenticationManager maps identity
    B->>B: Save previous context, set SOAP context
    B->>S: Call @PreAuthorize method
    S-->>B: Response / exception
    B->>B: finally: restore previous context
    B-->>E: End scoped business invocation
    E-->>F: SOAP response/Fault
    F->>F: Request context cleanup
~~~

Sơ đồ thể hiện thiết kế, **không phải luồng tự động** của mọi WSS4J integration. Tầng bridge phải chạy sau xác minh và trước method security.

### 9.2. try/finally cho cả lỗi nghiệp vụ

~~~java
SecurityContext previous =
        SecurityContextHolder.getContext();

try {
    SecurityContext next =
            SecurityContextHolder.createEmptyContext();
    next.setAuthentication(trustedAuthentication);
    SecurityContextHolder.setContext(next);

    return securedBusinessCall.get();
} finally {
    SecurityContextHolder.setContext(previous);
}
~~~

Nếu service ném `AccessDeniedException`, `DataAccessException` hoặc lỗi nghiệp vụ, context vẫn được restore. Với nested HTTP principal + SOAP principal, **restore previous** giữ lại transport context; clear vô điều kiện có thể làm mất context hợp lệ của outer layer.

### 9.3. afterCompletion không đủ cho mọi lỗi

`EndpointInterceptor#afterCompletion` có thể không được gọi trong mọi lỗi **trước dispatch**. Cần kiểm tra:

- Malformed XML bị từ chối ở SOAP message factory.
- WSS4J validation thất bại.
- Endpoint mapping không tìm thấy operation.
- Interceptor chain dừng sớm hoặc ném exception.
- Business method trả SOAP Fault.
- Servlet async dispatch/timeout và executor thread reuse.

Không chỉ đặt cleanup trong `afterCompletion` rồi cho là an toàn. Dùng scope `finally` nơi tự set context, và dựa vào Spring Security filter lifecycle cho HTTP context.

### 9.4. Không thay ThreadLocal bằng global state

~~~java
// PHẢN VÍ DỤ: shared identity giữa concurrent requests.
public final class UnsafeIdentity {
    public static String currentPartner;
}
~~~

`SecurityContextHolder.MODE_GLOBAL` có thể trộn user giữa threads. `MODE_INHERITABLETHREADLOCAL` không phù hợp để tự động xử lý thread pool reuse: thread tạo trước task có thể mang context cũ. Không dùng static mutable field hoặc thay strategy toàn JVM chỉ để chữa một lỗi `Authentication == null`.

## 10. @Async, executor và outbox: danh tính qua thread boundary

### 10.1. @Async không tự chuyển ThreadLocal

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class OrderNotificationService {

    @Async("soapIdentityTaskExecutor")
    public CompletableFuture<String> notifyPartner() {
        Authentication auth =
                SecurityContextHolder.getContext()
                        .getAuthentication();

        return CompletableFuture.completedFuture(
                auth == null ? "NO_CONTEXT" : auth.getName());
    }
}
~~~

Đây là snippet minh họa; class phải là Spring-managed bean và `@EnableAsync` được bật. Không suy rằng `auth` sẽ là SOAP signer của request gốc chỉ vì method được gọi trong endpoint.

### 10.2. Executor wrapper cho task ngắn

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class SoapAsyncConfiguration {

    @Bean
    public AsyncTaskExecutor soapIdentityTaskExecutor() {
        ThreadPoolTaskExecutor delegate =
                new ThreadPoolTaskExecutor();
        delegate.setCorePoolSize(4);
        delegate.setMaxPoolSize(8);
        delegate.setQueueCapacity(100);
        delegate.setThreadNamePrefix("soap-identity-");
        delegate.initialize();

        return new DelegatingSecurityContextAsyncTaskExecutor(
                delegate);
    }
}
~~~

`DelegatingSecurityContextAsyncTaskExecutor` có thể capture/apply context lúc submit task và dọn sau khi chạy. Nếu task được submit **trước WSS4J verification/bridge**, nó có thể nhận gateway identity hoặc anonymous thay SOAP signer. Nếu quyền bị revoke giữa submit và execute, còn cần kiểm tra policy lúc thực thi.

**Wrapper truyền context không xác thực identity**, không tự bảo vệ SOAP Signature/MTOM/TLS và không cấp quyền. Nếu task chạy rất lâu, đừng xem context snapshot là authorization vĩnh viễn.

### 10.3. Bài test thread leak

Một regression test nên:

1. Submit task trong context `PARTNER_A`; assert thấy đúng principal.
2. Sau task, verify worker không còn context A khi idle/nhận task độc lập.
3. Submit task B của `PARTNER_B` vào cùng pool; assert không thấy A.
4. Submit task không có context; assert không tự mang A/B.
5. Buộc task A ném exception; assert cleanup.
6. Thử concurrent tasks để phát hiện race.

Dùng futures/barriers và timeouts test, không lấy `Thread.sleep` làm bảo đảm duy nhất.

### 10.4. Durable outbox không lưu Authentication object

~~~text
SOAP request verified
  → persist verifiedPartnerId, tenantId, operationId
  → durable outbox / message queue
  → worker authenticates its own service identity
  → reloads partner entitlement and ownership
  → reauthorizes action / callback destination
  → executes job with idempotency controls
~~~

Không serialize `SecurityContext`, `Authentication`, UsernameToken, SOAP SignatureValue hoặc private key vào queue để phục hồi sau nhiều giờ. Lưu **IDs đã xác minh**, policy version, job/correlation ID và expiry trong message được bảo vệ integrity. Worker phải kiểm tra lại suspension/revocation/tenant ownership và dùng credentials riêng theo policy.

### 10.5. WebFlux/reactive là mô hình khác

Trong reactive pipelines, security context thường đi theo Reactor Context qua `ReactiveSecurityContextHolder`, không dựa hoàn toàn vào servlet ThreadLocal. Không sao chép `SecurityContextHolder.setContext` vào WebFlux rồi dùng global principal; phải có reactive-context propagation riêng và test qua asynchronous boundaries.

## 11. Kiểm chứng provenance của Authentication và danh tính qua các hop

### 11.1. Một authenticated token sai nguồn là một security bypass

~~~java
// PHẢN VÍ DỤ: caller tự chọn identity qua SOAP Header.
String username = extractSoapHeader("Username");

Authentication auth =
        UsernamePasswordAuthenticationToken.authenticated(
                username, null,
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));

SecurityContextHolder.getContext().setAuthentication(auth);
~~~

Đoạn code trên **cố ý không an toàn**. Nó đánh dấu caller đã authenticated và được quyền admin mà **không** xác minh chữ ký, UsernameToken, mTLS hoặc registry. `Authentication` là một data structure, không tự kiểm mật mã khi khởi tạo.

Cũng không được tạo trusted principal từ:

- `<PartnerId>`, `<tenantId>` hay `<Role>` trong SOAP Body/Headers chưa verified.
- Chỉ một `wsse:UsernameToken` có username mà validator chưa kiểm password/digest/replay.
- `ds:KeyInfo` do client đưa lên nhưng chưa có cryptographic/reference validation.
- HTTP `X-Partner-Id`, `X-Forwarded-User` hoặc `X-Client-Cert` không được proxy xác thực và bảo vệ khỏi spoofing.
- `wsa:ReplyTo`, `MessageID` hoặc SOAPAction (routing metadata).
- Một JSON/XML flag `authenticated=true` của caller.

### 11.2. Bằng chứng phải thu được từ đúng nguồn

| Nguồn | Bằng chứng trước khi tạo principal |
|---|---|
| HTTP Basic | `AuthenticationProvider` kiểm credential, TLS bảo vệ password transport |
| Direct mTLS | TLS client certificate chain verified, client-auth enforced, certificate identity mapped to user |
| Gateway mTLS | Gateway thực sự authenticate peer; backend xác thực gateway và tin headers qua kênh chống giả mạo |
| WS-Security UsernameToken | WSS4J/token validator kiểm password/digest, nonce/timestamp theo policy |
| SOAP X.509 Signature | Signature, references, signer certificate trust, signed Body/Headers, algorithms và freshness pass |
| SAML/Kerberos/token khác | Issuer/audience/subject/time/signature verification theo profile |
| Delegation | Actor được phép ủy quyền, subject+tenant scope và audit trail rõ |
| Outbox worker | Worker identity riêng và dữ liệu identity reference có integrity, reauthorization theo policy |

**Authentication thành công và authorization thành công là hai bước riêng.** Khi `VerifiedSoapIdentity` cho thấy signer `PARTNER_A`, chưa thể kết luận partner A được truy cập `ORDER_123` của tenant B.

### 11.3. Một request có thể chứa ba danh tính khác nhau

Ví dụ:

~~~text
TLS peer / gateway = GATEWAY_1
WS-Security signer = PARTNER_A
SOAP Body.partnerId = PARTNER_B
~~~

Hành vi đúng:

1. Xác minh gateway certificate hoặc HTTP transport principal.
2. Xác minh SOAP signer và required signed references.
3. Kiểm tra gateway `GATEWAY_1` có được **ủy quyền chuyển lời** cho `PARTNER_A` không.
4. Kiểm tra signer `PARTNER_A` có quyền thao tác tài nguyên của `PARTNER_B` không; mặc định không khi thiếu delegation contract.
5. Tạo business principal từ trusted mapping, không từ Body.partnerId.
6. Từ chối hoặc audit identity mismatch theo policy, **không tự fallback** sang danh tính “ít lỗi hơn”.
7. Giữ evidence của transport signer và business signer **tách biệt** trong audit metadata đã chuẩn hóa.

### 11.4. Trust boundary ở gateway/load balancer

Khi TLS terminate tại reverse proxy, application backend có thể không thấy trực tiếp client certificate. Nếu proxy chuyển identity bằng HTTP Header, phải bảo đảm:

- Không có direct bypass tới backend từ Internet/untrusted networks.
- Proxy xóa mọi client-supplied identity headers trước khi chèn headers đã xác thực.
- Proxy ↔ backend dùng kênh được bảo vệ, auth gateway/ACL.
- Các certificate attributes / principal IDs được validate và giới hạn format.
- Backend vẫn thực hiện SOAP message signature validation nếu đó là contract.
- Policy ràng buộc gateway identity ↔ SOAP signer ↔ tenant/operation.

Không xem một `X-Forwarded-User` có mặt là đủ để tạo `PreAuthenticatedAuthenticationToken`. Nó phải được tạo **bởi hệ thống đã được xác thực**, với trust boundary được review.

### 11.5. Khi WSS4J không cấp principal tự động

Một Spring-WS `Wss4jSecurityInterceptor` có thể báo token/signature pass, nhưng `SecurityContextHolder` vẫn không chứa expected principal nếu không có bridge tích hợp. Đây là **mất ngữ cảnh**, không phải lý do bỏ qua method security.

Quy trình xử lý:

1. Xác minh `wsse:Security` hợp lệ và WSS4J validation thật chạy trên endpoint.
2. Xác định API/result carrier mà version/framework hỗ trợ để đọc **validated principal** sau verification.
3. Tạo adapter nội bộ chỉ cho phép kết quả đã verified đi vào `AuthenticationManager`.
4. Mapping signer/UsernameToken subject tới partner/tenant/authorities qua authoritative registry.
5. Scope `SecurityContext` trước lời gọi Spring-managed method-security service.
6. Test với request valid, no-header, invalid signature, partner revoked và cross-tenant.
7. Không tự đọc raw SOAP XML để dựng principal trong thời gian chờ tích hợp.

## 12. SOAP response, Fault và việc giữ đúng danh tính

### 12.1. Context trong response signing có thể khác context nghiệp vụ

Sau khi business method return, Spring-WS có thể thực hiện WS-Security securement trên **response**. Nếu scoped identity bridge đã restore context cũ, response interceptor không thể tự kỳ vọng `SecurityContextHolder` còn mang SOAP signer.

Giải pháp là thiết kế **message-scoped trusted metadata**:

- Verified signer ID / business principal từ kết quả security stack.
- Correlation ID và policy version được server quản lý.
- Key/certificate lựa chọn để server ký response theo **server security identity**, không dùng private key của client.
- Storage theo message context/bounded request object được kiểm soát.
- Cleanup ở cuối response/Fault path; không giữ static mutable fields.

**Phân biệt:** danh tính của người gửi request và danh tính ký response là hai vai trò khác nhau. Không ghi đè principal chỉ để response interceptor nhìn thấy một String tiện lợi.

### 12.2. Lỗi xảy ra trước authentication

Một XML request không well-formed hoặc SOAP Signature sai có thể chưa có business principal được xác minh. Error handler không nên:

- Dùng `<Username>` từ raw SOAP Header làm audit principal đã xác thực.
- Sinh `Authentication` với authorities mặc định để tạo Fault.
- Gửi SOAP Fault tới `wsa:FaultTo` chưa được authorize (rủi ro SSRF/lộ dữ liệu).
- Ký response bằng certificate/key tham chiếu từ untrusted `KeyInfo`.
- Tiếp tục xử lý nghiệp vụ dưới guest account khi protected operation fail.

Fault nên phân biệt security denial, transport/parser errors và modeled business faults mà không log raw credentials/Body. Một số lỗi xảy ra trước `EndpointExceptionResolver`; không giả định mọi lỗi đều có SOAP Fault hoàn chỉnh.

### 12.3. Outbound WebServiceTemplate và identity delegation

Một business service dùng `WebServiceTemplate` gọi SOAP đối tác:

~~~text
Inbound verified SOAP signer: PARTNER_A
    → business authorization
    → outbound SOAP client with service/delegated identity
    → partner HTTPS/mTLS and WS-Security
    → response validation
~~~

Không tự copy inbound `wsse:UsernameToken`, PasswordDigest, private key hoặc SOAP Signature vào outbound message. Outbound client phải dùng **credentials và signing keys được cấp riêng**, hoặc delegation token hợp lệ theo contract.

`WebServiceMessageCallback` giúp chỉnh SOAPAction/custom Header, không thay WSS4J signing. Client interceptor và HTTP message sender cần cấu hình riêng cho WS-Security, mTLS/TLS và response validation. Nếu outbound call chạy qua `@Async`, còn phải xác minh context/metadata propagation như mục 10.

### 12.4. Cẩn trọng với SOAP Fault đã ký và chưa ký

Nếu contract yêu cầu signed normal response và modeled business Fault, client phải verify trước khi dùng details. Nhưng một security Fault sinh ra **trước** khi server có authenticated recipient hoặc signing context có thể theo profile khác. Không tự chấp nhận mọi unsigned Fault chứa dữ liệu nghiệp vụ; xác định policy riêng cho fault types và test tương thích.

### 12.5. Observability không nên thành một identity source

Một hệ thống tracing có thể lưu `correlationId`, `MessageID`, remote IP, HTTP peer DN và signer fingerprint hash đã verify. Chúng có thể giúp điều tra, nhưng không dùng `traceId` hay `X-Request-Id` thay authentication.

Chỉ ghi **metadata đã được chuẩn hóa**, không nguyên SOAP Header/Body hoặc token. Khi một security check fail, ghi outcome `DENIED` thay vì gán principal theo tên tự khai của caller.

## 13. Chiến lược kiểm thử: từ SecurityContext unit test đến SOAP thật

Một bài kiểm thử tốt phải trả lời **ba câu hỏi độc lập**:

1. **Authentication có được tạo đúng từ nguồn đáng tin không?** Không có cách giả lập dữ liệu SOAP chưa xác minh để lấy authorities.
2. **SecurityContext có đúng trong phạm vi gọi business không?** Không bị mất khi thread chuyển hoặc rò vào request khác.
3. **Business method có kiểm quyền cụ thể không?** Không chỉ đọc `isAuthenticated` rồi cho phép mọi resource.

Không thể chứng minh cả ba bằng một `@WithMockUser` hay một Mockito mock của `Authentication`.

### 13.1. Ma trận theo tầng

| Loại test | Kiểm được | Không tự chứng minh |
|---|---|---|
| Unit test `ScopedSecurityContext` | Scope, restore trong `finally`, nested context | WS-Security signature, mTLS |
| Unit test `AuthenticationManager`/provider | Mapping trusted identity tới user/authorities, deny revoked partner | Certificate đã verify trong WSS4J |
| `@WithMockUser` method-security test | `@PreAuthorize`, authority/tenant policy khi đã có principal | XML Signature, UsernameToken, TLS, provenance |
| `MockWebServiceClient` | Spring-WS endpoint dispatch, SOAP payload, một phần interceptor chain/context | Servlet HTTP filters và TLS/mTLS handshake thật |
| MockMvc + Spring Security test support | HTTP filter-chain routing, CSRF/authentication rules và request matchers | Real TLS certificate validation nếu dùng request post-processor giả lập |
| Spring Boot server thật + HTTPS SOAP client | Transport + servlet filters + Spring-WS + WSS4J + business | Mọi production topology nếu gateway/certs/regions khác |
| End-to-end async/outbox test | Identity propagation, reauthorization và idempotency | Cryptographic trust nếu không đưa real signed SOAP vào đầu pipeline |

### 13.2. Scope unit test: exception vẫn restore context cũ

~~~java
package com.example.orders.security;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

class ScopedSecurityContextTest {

    @Test
    void restoresPreviousContextEvenWhenBusinessThrows() {

        SecurityContext outer =
                SecurityContextHolder.createEmptyContext();
        outer.setAuthentication(
                new TestingAuthenticationToken(
                    "http-gateway", "test-only", "TRANSPORT"));

        SecurityContextHolder.setContext(outer);

        var soapSigner = new TestingAuthenticationToken(
                "partner-a", "test-only", "ORDER_WRITE");

        try {
            assertThrows(IllegalStateException.class,
                () -> ScopedSecurityContext.callAs(
                    soapSigner, () -> {
                        assertEquals(
                            "partner-a",
                            SecurityContextHolder.getContext()
                                .getAuthentication().getName());
                        throw new IllegalStateException("synthetic");
                    }));

            assertSame(
                outer, SecurityContextHolder.getContext());
            assertEquals(
                "http-gateway",
                SecurityContextHolder.getContext()
                    .getAuthentication().getName());
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void rejectsMissingTrustedAuthentication() {
        try {
            assertThrows(SecurityException.class,
                () -> ScopedSecurityContext.callAs(
                    null, () -> "must-not-run"));
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

`TestingAuthenticationToken` chỉ dành cho **test**; unit test này không giả vờ kiểm chứng certificate hay WSS4J. Nó xác minh đúng một invariant: khi đổi context trong một phạm vi đồng bộ, exception không làm mất context trước đó.

### 13.3. Unit test authentication provider

Dùng một `PartnerUserDirectory` giả do test kiểm soát, chuẩn bị các ca:

- Signer verified và active → principal đúng, authorities do registry cấp.
- Signer unknown/revoked/suspended → AuthenticationManager từ chối.
- Signer hợp lệ nhưng tenant không được phép → từ chối hoặc không cấp quyền tenant.
- Principal type không phải `VerifiedSoapIdentity` → từ chối.
- Authorities do SOAP Body gửi lên nhưng registry không cấp → không xuất hiện trong Authentication.
- Identity bị thiếu hoặc không đủ trường → fail closed.
- Không có provider phù hợp → không chuyển sang anonymous fallback.

**Caveat:** unit test tự tạo `VerifiedSoapIdentity` không chứng minh một attacker SOAP client có thể hay không thể giả mạo object ở production. Điều đó phải được kiểm qua **integration boundary** nơi WSS4J result được chuyển cho adapter.

### 13.4. Test method security với @WithMockUser

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.test.context.support.WithMockUser;

class OrderAuthorizationTest {

    @Test
    @WithMockUser(
        username = "partner-a",
        authorities = {"ORDER_WRITE"})
    void callerNeedsResourceOwnership() {
        // Gọi OrderService thực qua Spring proxy.
        // Kiểm tra cả case order thuộc partner-a
        // và order thuộc partner-b bị AccessDeniedException.
        // @WithMockUser KHÔNG xác minh SOAP Signature.
    }
}
~~~

Test trên cần Spring Test context và `OrderService` bean thật (hoặc một test slice cấu hình method security). Không test self-invocation bằng cách gọi trực tiếp method trên object tạo bằng `new OrderService(...)`; như vậy proxy advice có thể không chạy.

### 13.5. Test context rò giữa các requests

Nếu thread pool xử lý request A và B liên tiếp:

1. Request A có verified signer `PARTNER_A`, được phép đọc đơn A.
2. Request A kết thúc bằng cả success và exception trong hai kịch bản.
3. Request B hoàn toàn thiếu security token/header.
4. Request B phải bị từ chối và **không được thấy** Authentication `PARTNER_A`.
5. Request C có verified signer `PARTNER_B`, chỉ có authorities của B.
6. Chạy đồng thời A/C để phát hiện shared mutable fields hoặc race khi mapping tenant.
7. Quan sát `SecurityContextHolder` trong service layer, không chỉ ở endpoint.

**Expected invariant:** protected service không bao giờ thực thi dưới identity không thuộc request hiện tại.

## 14. End-to-end tests: thực sự xác minh HTTP → WSS4J → business

### 14.1. Vì sao MockWebServiceClient chưa đủ?

`MockWebServiceClient` tiện cho Spring-WS endpoint tests nhưng có thể bỏ qua **servlet filter chain và TLS handshake**. Một test mock có `Authentication` gán sẵn sẽ không chứng minh:

- HTTP mTLS certificate có được verify không.
- Spring Security X.509 filter có thực sự chọn `SecurityFilterChain` phù hợp không.
- Incoming WS-Security Signature/required actions được WSS4J verify trước endpoint không.
- Verified signer identity có tới `AuthenticationManager` và method-security service không.
- Một URL alias/gateway path có vô tình bypass security không.

Cần ít nhất một integration test chạy **HTTP(S) server thật**, đúng servlet/filter/MessageDispatcherServlet và WSS4J configuration.

### 14.2. Test pipeline bằng SOAP payload hợp lệ

Một XSD contract-first có thể định nghĩa root:

~~~xml
<ord:CancelOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1001</ord:orderId>
</ord:CancelOrderRequest>
~~~

Để test missing authentication, hãy giữ **Body hợp lệ theo XSD** và chỉ bỏ WS-Security Header hoặc client certificate yêu cầu. Nếu Body cũng sai schema, request có thể bị chặn bởi XSD/parser trước authentication gate và test **không chứng minh** security đã bảo vệ đúng.

Kỳ vọng:

~~~text
Valid SOAP + valid signer + authorized order
    → authenticated principal đúng
    → required authorities present
    → business call allowed exactly once

Valid SOAP + no Security Header (policy requires WSS4J)
    → security denied
    → business call count = 0

Valid SOAP + signature invalid / signer revoked
    → security denied
    → business call count = 0

Valid SOAP + valid signer A + order owned by B
    → authentication succeeds
    → authorization denied
    → business call count = 0

Request A valid, then B invalid on reused thread
    → B denied
    → no stale principal A
~~~

### 14.3. Test mTLS và WS-Security là hai nhóm khác nhau

Với HTTPS client-auth:

- Dùng server certificate test với SAN đúng và truststore CA phù hợp.
- Thử **không có client certificate** khi container yêu cầu mTLS → TLS/HTTP denial trước SOAP (tùy handshake policy).
- Thử client certificate trusted chain và signer mapping hợp lệ.
- Thử client certificate sai CA hoặc không được authorization mapping → từ chối.
- Thử WS-Security missing/invalid dù mTLS hợp lệ → từ chối nếu policy yêu cầu cả hai.
- Thử WS-Security valid nhưng mTLS thiếu → vẫn từ chối nếu yêu cầu HTTP mTLS.

Một Mockito fake `X509Certificate`, HTTP header `X-Client-Cert` hoặc MockMvc `x509()` request post-processor chỉ chứng minh filter behavior giả lập; **không** thay thế test TLS handshake thật.

### 14.4. Test chữ ký SOAP thật

Dùng WSS4J/WS-Security tooling với **test keys/certificates**, chuẩn bị:

1. Signed SOAP Body + Timestamp hợp lệ.
2. Header thiếu hoàn toàn.
3. Header rỗng hoặc chỉ có Timestamp.
4. Signature sai digest.
5. Signature hợp lệ nhưng ký một optional Header, không phủ Body bắt buộc.
6. Signer certificate không thuộc trust policy hoặc bị revoke.
7. Timestamp hết hạn hoặc quá xa tương lai.
8. Duplicate Id/signed-node confusion.
9. SOAP 1.1/1.2 với actor/role đúng hoặc sai.
10. WS-Addressing Headers bắt buộc ký nhưng bị thay sau signing.

Kiểm tra **Authentication không được tạo** khi policy không đạt; hoặc ít nhất không đi tới protected method. Dùng partner/tenant mapping thật trong test environment, không chỉ assert WSS4J không ném exception.

### 14.5. Ma trận principal và authorization

| Transport identity | SOAP signer | Resource | Expected outcome |
|---|---|---|---|
| Gateway đã được trust | PARTNER_A đã verify | Order A được phép | Thành công theo delegation policy |
| Gateway đã được trust | PARTNER_A đã verify | Order B không thuộc quyền | Denied bởi service authorization |
| Gateway đã được trust | Không có signer (bắt buộc) | Order A | Denied trước business |
| Gateway chưa được trust | PARTNER_A signed SOAP | Order A | Denied nếu HTTP gateway/mTLS bắt buộc |
| Partner A mTLS trực tiếp | PARTNER_A signed SOAP | Order A | Thành công nếu hai policies pass |
| Partner A mTLS | PARTNER_B signed SOAP | Order A | Reject trừ khi delegation explicit |
| Partner A hợp lệ | PARTNER_A signer revoked | Order A | Denied |
| Partner A hợp lệ | Signature pass nhưng Body unsigned | Order A | Denied required signed coverage |

Không hardcode các partner IDs hoặc vai trò trên trong test production; chúng là fixtures. Với hệ thống có signed SOAP proxy hợp pháp, policy có thể cho phép delegated identity mismatch, nhưng phải được mô tả và kiểm thử thay vì dùng điều kiện “lấy tên nào cũng được”.

### 14.6. Điều kiện nghiệm thu của pipeline

Một integration test hoàn chỉnh cần assert:

- `Authentication#getName()` hoặc typed principal trỏ đến **đúng verified partner/tenant**.
- Authorities đến từ server registry.
- `SecurityContextHolder` thấy đúng identity ở **method-security service**.
- `@PreAuthorize` và resource ownership chặn cross-tenant access.
- Business call count bằng 0 nếu verification hoặc authorization fail.
- Context được restore/clear khi request hoàn tất, kể cả SOAP Fault.
- Dữ liệu SOAP response/Fault không lộ authentication secrets.
- Không có đường legacy/gateway/async bypass được kiểm thử.
- Không cần disable WS-Security validation hoặc hostname verification để test pass.

## 15. Bảng chẩn đoán Authentication và SecurityContext

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra an toàn |
|---|---|---|
| `Authentication == null` trong endpoint | HTTP filter không authenticate hoặc WS-Security result chưa được bridge | Xác định nguồn auth dự kiến, filter chain và WSS4J validated result |
| Authentication là anonymous | HTTP policy cho anonymous hoặc bridge không thiết lập context | Kiểm tra trust resolver, token type và required SOAP policy |
| `isAuthenticated() == true` nhưng không có danh tính thật | `AnonymousAuthenticationToken` hoặc token được đánh dấu authenticated sai | Dùng provider/provenance + authorities/resource policy |
| WSS4J signature pass nhưng `@PreAuthorize` deny | Chưa map signer sang Spring authorities hoặc context không nằm trong service thread | AuthenticationManager/bridge/method proxy |
| mTLS pass nhưng UsernameToken bị từ chối | Hai lớp auth khác nhau | Kiểm tra required WS-Security actions; không bỏ validate |
| `SecurityContext` chứa gateway identity, không phải signer | Chưa bridge SOAP principal hoặc scope restore sớm | Policy transport vs SOAP identity |
| `@PreAuthorize` không chạy | `@EnableMethodSecurity` thiếu, bean không proxied, self-invocation | Kiểm tra Spring-managed bean, invocation qua proxy và test access denied |
| Request B thấy partner A | Static mutable state, ThreadLocal leak hoặc sai executor propagation | Cleanup/restore, không MODE_GLOBAL, test thread reuse |
| `@Async` không có principal | ThreadLocal không chuyển theo executor | DelegatingSecurityContext executor hoặc explicit identity metadata |
| `@Async` thấy principal request trước | InheritableThreadLocal/thread pool reuse hoặc không clear | Scoped context, executor wrapper và concurrent tests |
| SOAP Body chứa tenant B nhưng Authentication là A | Body input chưa được authorize | So trusted partner/tenant/resource trong registry |
| Một URL legacy cho phép unsigned SOAP | Security filter/WSS4J interceptor không bao phủ mapping | Inventory mọi entrypoint và no-header tests |
| Test `@WithMockUser` pass, production deny | Test chỉ set context, không test SOAP/mTLS authentication | Real HTTP/SOAP integration test |
| Response signing không có SOAP principal | Scoped bridge restore trước response interceptor | Message-scoped trusted metadata, response policy |
| Sau TLS proxy, client certificate không đến backend | TLS termination và trusted proxy identity propagation chưa thiết kế | Mối tin cậy gateway→backend, chặn client-supplied spoofed headers |
| Revoke partner nhưng worker vẫn gửi callback | Job giữ stale Authentication/authority snapshot | Reauthorize tại worker, policy version/TTL |
| Spring Security filter gây HTTP 401 trước WSS4J | HTTP chain yêu cầu authenticated nhưng chỉ SOAP token được hỗ trợ | Thiết kế HTTP ingress cho SOAP verification, giữ fail-closed business |
| SOAP Fault trả stack trace/UsernameToken | Error handler log/echo raw exception/message | Metadata-only logs, Fault mapping tối thiểu |
| JWT/token identity sai issuer/audience | Provider chỉ parse claims, chưa verify | Dùng validator đúng profile và trust policy |
| Multiple SecurityFilterChain chọn sai | Matcher/order không khớp URL thực | Inspect chain matchers/ordered routes, test từng URL |

### 15.1. Quy trình định vị lỗi theo tầng

~~~mermaid
flowchart TD
    A["SOAP request bị từ chối hoặc sai principal"] --> B{"HTTP layer có auth như policy?"}
    B -->|Không| C["Filter chain, mTLS, token provider, proxy"]
    B -->|Có| D{"WSS4J actions / signed coverage pass?"}
    D -->|Không| E["Signature, Timestamp, UsernameToken, trust"]
    D -->|Có| F{"Trusted signer identity mapped?"}
    F -->|Không| G["Identity bridge, AuthenticationManager, registry"]
    F -->|Có| H{"SecurityContext đúng trong service thread?"}
    H -->|Không| I["Scope, filter lifecycle, async/executor"]
    H -->|Có| J{"Authorities và ownership hợp lệ?"}
    J -->|Không| K["@PreAuthorize, tenant/resource policy"]
    J -->|Có| L["Business operation theo transaction/idempotency"]
~~~

Không log toàn bộ SOAP hoặc password để “tìm principal”. Ghi operation code, route ID, security phase, principal ID **chỉ sau verification**, authorization reason và correlation ID có kiểm soát.

### 15.2. Quy tắc quan sát context trong logs

Một log có thể dùng:

~~~text
transport_auth=MTLS_VERIFIED
message_auth=WS_SIGNATURE_VERIFIED
principal_mapping=PARTNER_A_ACTIVE
context_scope=BUSINESS_INVOCATION
operation=CANCEL_ORDER
authorization=DENIED_RESOURCE_OWNERSHIP
business_invoked=false
~~~

Đây là metadata **do server thiết lập sau verified checks**. Không dùng raw values của `UsernameToken`, SOAP Body, certificate private key, `SignatureValue`, `KeyInfo` hoặc raw exception text làm labels; chúng có thể lộ dữ liệu hoặc tăng cardinality.

## 16. Case study: mất danh tính khi chuyển SOAP request sang async worker

### 16.1. Bối cảnh

Một hệ thống tích hợp xác minh `wsse:Signature` cho lệnh `SubmitOrderRequest`. WSS4J kiểm tra chữ ký của đối tác `PARTNER_A`, bridge tạo `Authentication` có `ORDER_WRITE`, `@PreAuthorize` chấp nhận ghi một outbox job. Sau đó chương trình gọi `@Async` để gửi xác nhận sang đối tác.

Tại môi trường test đơn luồng, mọi thứ hoạt động. Khi production tải cao:

- Một số async callbacks fail vì `SecurityContextHolder.getContext().getAuthentication() == null`.
- Một developer đổi chiến lược context sang `MODE_INHERITABLETHREADLOCAL` và vài test bắt đầu pass.
- Nhưng dưới thread pool reuse, có lúc worker thấy danh tính từ một task khác, dẫn đến lỗi cross-tenant hoặc audit sai.
- Nếu quyền đối tác bị revoke sau khi job vào queue, task vẫn có thể dựa vào authorities cũ mà không re-check.

Đây là ví dụ điển hình của **sai lầm coi request-local SecurityContext là kho danh tính dùng được vô thời hạn**.

### 16.2. Phân tích theo từng ranh giới

| Ranh giới | Điều cần bảo đảm |
|---|---|
| Inbound SOAP | WSS4J verify đúng Body/headers, trust signer và required actions |
| Trusted bridge | Partner/tenant mapping từ registry, authorities không lấy từ SOAP input |
| Business invocation | Spring Security context đúng scope, method security chạy |
| Outbox commit | Job/identity references được ghi an toàn và idempotent |
| Async task submit | Biết context được capture khi nào, hoặc không truyền context |
| Worker execution | Reauthorize theo trạng thái partner/tenant/resource hiện tại |
| Outbound SOAP | Service identity/delegated credentials riêng, TLS/WS-Security đúng |
| Retry/Fault | Không reuse stale identity hoặc gửi dữ liệu sai tenant |

### 16.3. Cách sửa theo hướng ổn định

1. **Không dùng** `MODE_GLOBAL` hay `MODE_INHERITABLETHREADLOCAL` như cơ chế propagation cho thread pool.
2. Với task ngắn trong cùng request, dùng `DelegatingSecurityContextAsyncTaskExecutor` hoặc wrapper tương đương đã kiểm thử.
3. Chỉ submit task sau khi trusted bridge/method security đã thực hiện phần chính sách phù hợp.
4. Với job kéo dài, chỉ lưu **verified identity references**, không serialize Authentication/credentials.
5. Worker dùng service principal riêng cho downstream, đồng thời reauthorize delegated business operation theo registry hiện tại.
6. Đặt TTL/idempotency/revocation controls, đặc biệt với callback chứa tài liệu nhạy cảm.
7. Test request A/B liên tiếp trên reused worker threads, exception cleanup và revoked partner.
8. Ghi audit rõ **source identity**, **effective business identity** và **worker service identity**.

### 16.4. Một thiết kế sửa lỗi có thể kiểm thử

~~~mermaid
flowchart TB
    A["WSS4J verified SOAP request"] --> B["Trusted partner/tenant mapping"]
    B --> C["Scoped Authentication"]
    C --> D["@PreAuthorize business"]
    D --> E["Outbox: partner ID + tenant ID + job ID"]
    E --> F["Worker authenticates as service"]
    F --> G["Reauthorize current partner/resource"]
    G -->|Allowed| H["Send callback with approved credentials"]
    G -->|Denied/revoked| I["Stop / dead-letter / audit"]
~~~

Nghiệm thu yêu cầu:

- Valid request chỉ gọi business một lần; invalid signature hoặc cross-tenant resource **không tạo job**.
- Job xử lý sau khi partner bị suspend không thực hiện external callback trái policy.
- Worker context không giữ request A sau khi task hoàn tất, kể cả exception.
- Outbound callback đúng partner/tenant, TLS/WS-Security profile và `RelatesTo`/correlation.
- Test dùng chính runtime/executor configuration thực, không chỉ gọi `@Async` method trực tiếp như hàm đồng bộ.

### 16.5. Nếu còn một legacy route không đi qua WSS4J

Đây là một rủi ro **khác** nhưng có thể cộng hưởng với stale context. Nếu legacy SOAP URL bỏ qua WSS4J, một caller chưa xác thực có thể vào business khi code kiểm `Authentication` cũ/có sẵn. Cần khóa route và kiểm thử toàn bộ ingress paths, không chỉ sửa async executor.

## 17. Bài tập tự luyện kèm đáp án

### Bài 1 — Authentication có khác SecurityContext không?

Một developer nói “đã dùng `@EnableMethodSecurity` nên Spring tự xác thực mọi SOAP request”. Đúng không?

**Đáp án:** Không. Method security chỉ áp dụng authorization theo context; HTTP/mTLS hoặc WSS4J phải authenticate trước, và identity bridge phải tạo `Authentication` đáng tin ở đúng scope.

### Bài 2 — WSS4J verify thành công, Authentication lại null

SOAP request có chữ ký hợp lệ, nhưng service đọc `SecurityContextHolder.getContext().getAuthentication()` bằng null. Có được bỏ `@PreAuthorize` không?

**Đáp án:** Không. Xác định WS-Security integration đã chuyển verified signer sang Spring Authentication chưa; thiết kế trusted bridge rồi test đến method security. Không lấy username từ raw SOAP Header để chữa tạm.

### Bài 3 — isAuthenticated bằng true với anonymous

Một `AnonymousAuthenticationToken` trả `isAuthenticated() == true`. Có thể cho `CancelOrder` chạy không?

**Đáp án:** Không. Không coi cờ đó là business authentication proof. Cần authorization policy phân biệt anonymous, authorities và resource ownership, cùng required SOAP security actions.

### Bài 4 — TLS gateway khác SOAP signer

TLS peer là gateway G, SOAP signer là partner A. Có bắt buộc hai tên phải giống nhau không?

**Đáp án:** Không nếu có delegation/trust model hợp lệ. Nhưng phải xác minh gateway, SOAP signer, quyền đại diện và tenant binding; không mặc định dùng danh tính bất kỳ hoặc bỏ kiểm soát.

### Bài 5 — Tạo PreAuthenticatedAuthenticationToken

Có thể tạo token 3 tham số với role Admin ngay từ SOAP field `<Role>ADMIN</Role>` rồi set vào context không?

**Đáp án:** Không. Đó là identity spoofing. Pre-authentication chỉ hợp lệ khi caller đã được tầng tin cậy xác minh, và authorities phải đến từ registry/chính sách do server kiểm soát.

### Bài 6 — @PreAuthorize không chạy

Method `submitOrder` có `@PreAuthorize` nhưng test gọi `new OrderService(...).submitOrder(...)` vẫn chạy. Vì sao?

**Đáp án:** Test gọi object tạo trực tiếp, không qua Spring-managed proxy. Cần test đúng bean/proxy, `@EnableMethodSecurity` và tránh self-invocation bypass.

### Bài 7 — Thread pool sau khi request kết thúc

Một worker thread còn mang `Authentication` từ request A; request B chạy trên cùng thread. Rủi ro?

**Đáp án:** Cross-request identity leak, nhầm authorization/audit và có thể cross-tenant side effect. Dùng scoped cleanup/restore, executor wrappers hoặc explicit identity context với tests concurrent.

### Bài 8 — Dùng InheritableThreadLocal

Developer bật `MODE_INHERITABLETHREADLOCAL` vì `@Async` không thấy context. Có phải giải pháp tổng quát?

**Đáp án:** Không. Thread pool reuse có thể giữ danh tính cũ hoặc không capture identity đúng task. Ưu tiên `DelegatingSecurityContextAsyncTaskExecutor` cho task ngắn hoặc identity references/re-auth ở durable jobs.

### Bài 9 — Response signer không còn trong SecurityContext

Sau khi endpoint return, bridge restore HTTP context và response interceptor không thấy SOAP signer. Có nên bỏ cleanup để giữ signer đến khi response gửi xong không?

**Đáp án:** Không mặc định. Dùng trusted message-scoped metadata cho response signing/correlation theo policy, tránh thread-local identity leak. Phân biệt signer request với server key dùng ký response.

### Bài 10 — @WithMockUser pass

Test với `@WithMockUser(username="partner-a", authorities="ORDER_WRITE")` thành công. Có chứng minh SOAP signature đã verify đúng không?

**Đáp án:** Không. Test chỉ gán mock Authentication để thử authorization. Cần real HTTP/SOAP integration test với signed request và WSS4J, signer trust, Body coverage, gateway/mTLS nếu yêu cầu.

### Bài 11 — SOAP payload chứa tenant khác

Principal verified là A nhưng Body gửi `tenantId=B` và `orderId` thuộc B. Server nên làm gì?

**Đáp án:** Từ chối trừ khi có delegation/authorization rõ. Không tạo `Authentication` cho B từ field Body; so owner tại authoritative data store và business method security.

### Bài 12 — Token bị revoke sau khi job vào queue

Một worker dùng serialized Authentication được lưu hai giờ trước để gửi tài liệu cho đối tác vừa bị suspend. Có an toàn không?

**Đáp án:** Không. Outbox chỉ nên lưu verified identity references, expiry/policy version; worker xác thực service principal riêng và reauthorize partner/resource/destination tại lúc thực thi.

### Bài 13 — mTLS pass nhưng thiếu WS-Security Header

HTTP security đã authenticated client, nhưng operation yêu cầu Signed Body và Timestamp. Server có thể xử lý Body không ký không?

**Đáp án:** Không. HTTP mTLS và WS-Security bảo vệ các khía cạnh khác nhau; required message-level security vẫn bắt buộc theo contract.

### Bài 14 — Authentication trong SOAP Fault

Request signature không hợp lệ nhưng Fault handler gán principal theo UsernameToken để ghi audit. Có vấn đề gì?

**Đáp án:** Có. UsernameToken chưa verified không phải trusted principal. Ghi denied reason/correlation ID server-managed; không dùng untrusted identity cho authorization hoặc log như đã xác thực.

## 18. Checklist kiểm chứng Authentication, SecurityContext và đường truyền danh tính

### 18.1. Hợp đồng bảo mật và định nghĩa danh tính

- [ ] Mỗi SOAP operation xác định rõ cơ chế authentication: HTTP Basic, direct mTLS, gateway mTLS, WS-Security UsernameToken, SOAP X.509 Signature hoặc kết hợp.
- [ ] XSD/WSDL/WS-SecurityPolicy mô tả rõ required actions, signed parts, encrypted parts, timestamp/replay.
- [ ] Có bản đồ **transport principal → message signer → effective business principal**.
- [ ] Nếu gateway ký/chuyển tiếp thay client, delegation policy được phê duyệt và có audit.
- [ ] Partner/tenant/resource mapping được tra từ registry/DB do server quản lý.
- [ ] Không dùng `SOAPAction`, `MessageID`, `ReplyTo` hay `tenantId` tự khai làm bằng chứng authentication.
- [ ] Quyền riêng cho đọc, ghi, hủy, tải tài liệu và callback đã được quy định.
- [ ] Trạng thái revoked/suspended/expired của partner và keys được kiểm tra theo policy.
- [ ] Không tự cấp role/authority từ SOAP Header hoặc unsigned JWT claims.
- [ ] Một authenticated principal không tự được phép truy cập resource của tenant khác.

### 18.2. HTTP/TLS và Spring Security filter chain

- [ ] Biết rõ `MessageDispatcherServlet` được map tới những HTTP paths nào.
- [ ] `SecurityFilterChain` match đúng tất cả protected paths và aliases.
- [ ] Nếu mTLS bắt buộc, container/gateway **thực sự yêu cầu client certificate**.
- [ ] Certificate chain và trust/hostname policies được kiểm chứng, không dùng trust-all.
- [ ] X.509/HTTP AuthenticationProvider map certificate/token tới chính xác principal.
- [ ] Nếu proxy terminate mTLS, backend chặn direct bypass và chỉ nhận protected identity metadata.
- [ ] HTTP `SecurityContext` tồn tại trong request thread khi phương thức HTTP authentication thành công.
- [ ] Không để mặc định `permitAll` vô tình mở SOAP endpoints thiếu WSS4J enforcement.
- [ ] Nếu WS-Security-only, HTTP policy cho phép đưa SOAP đến verifier nhưng không cho unverified business execution.
- [ ] CSRF/session/`STATELESS` chính sách được thiết kế riêng cho SOAP M2M thay vì tắt bảo mật toàn hệ thống.
- [ ] Hệ thống nhiều `SecurityFilterChain` có integration tests cho matcher order/coverage.

### 18.3. WS-Security và trusted identity bridge

- [ ] WSS4J interceptor thực chạy trên **mọi protected SOAP operation**.
- [ ] Request không có `wsse:Security` hoặc thiếu required actions bị từ chối.
- [ ] Signature phải bao phủ **đúng SOAP Body và required Headers** mà business sử dụng.
- [ ] Signature/reference IDs, signer certificate trust, Timestamp/nonce/replay được xác minh theo policy.
- [ ] Không bị bypass do malformed XML, actor/role khác, SOAP 1.1/1.2 hay alternate endpoint mapping.
- [ ] Verified identity được lấy từ **security stack result**, không từ raw XML.
- [ ] Bridge chỉ nhận trusted evidence có provenance và không công khai factory tạo “verified” cho untrusted caller.
- [ ] `AuthenticationManager`/pre-auth provider xác nhận signer/partner/tenant và trạng thái còn hiệu lực.
- [ ] Authorities được cấp từ authoritative registry, không từ SOAP payload.
- [ ] Thiếu verifier/Crypto/registry không chuyển sang guest/fallback; **fail closed**.
- [ ] Nếu dùng Spring-WS/Spring Security integration sẵn, đã kiểm chứng nó tạo context sau successful verification, không chỉ header presence.
- [ ] Không có hai bridge vô tình ghi đè một principal mạnh bằng principal yếu hơn.

### 18.4. SecurityContext và method authorization

- [ ] `Authentication#getPrincipal()` / `getName()` đại diện đúng effective business principal.
- [ ] Không dùng `auth != null && auth.isAuthenticated()` làm gate duy nhất; nhận diện anonymous authentication.
- [ ] `SecurityContextHolder` được đặt trong đúng request/thread sau verification.
- [ ] Dùng `SecurityContextHolder.createEmptyContext()` thay vì sửa shared context tùy tiện.
- [ ] Mọi custom scope setContext có `finally` restore/cleanup kể cả khi exception.
- [ ] Không giữ principal trong singleton mutable field hoặc global static.
- [ ] Có `@EnableMethodSecurity` và service được gọi qua Spring-managed proxy.
- [ ] Không có self-invocation làm bỏ qua `@PreAuthorize`.
- [ ] Authorities như `ORDER_WRITE` không thay resource ownership/tenant checks.
- [ ] Authorization được kiểm sát transaction/business state đối với operations có side effects.
- [ ] Không có request A lưu lại context cho request B sau khi response/Fault hoàn tất.
- [ ] Không dùng `MODE_GLOBAL` hay `MODE_INHERITABLETHREADLOCAL` làm giải pháp propagation cho thread pool.

### 18.5. Async, outbox và response

- [ ] `@Async` tasks được submit đúng sau bridge/authorization khi cần danh tính hiện hành.
- [ ] Executor propagation được cấu hình có kiểm thử cleanup và context isolation.
- [ ] Task không có security context bị từ chối hoặc dùng identity riêng đúng policy; không lấy stale context.
- [ ] Durable jobs lưu identity references/policy version/expiry, không serialize whole `SecurityContext`/credentials.
- [ ] Worker reauthorize partner, tenant, resource và callback destination tại thời điểm chạy.
- [ ] Có idempotency/retry/TTL/dead-letter rules cho asynchronous side effects.
- [ ] Outbound SOAP client dùng service/delegated identity hợp lệ; không copy raw UsernameToken hoặc signature từ inbound.
- [ ] Response signing và Fault handling dùng trusted message-scoped metadata đúng vòng đời.
- [ ] Normal response/Modeled Fault được verify theo WS-SecurityPolicy khi client nhận.
- [ ] Fault của request chưa xác thực không dùng `FaultTo` chưa được authorize làm outbound URL.
- [ ] Không lấy raw SOAP Headers từ request thất bại để tạo principal/audit identity.

### 18.6. Regression tests tối thiểu trước phát hành

- [ ] Valid SOAP signature/mTLS theo policy → Authentication đúng, business authorized.
- [ ] Body hợp lệ nhưng `wsse:Security` thiếu → deny, **business calls = 0**.
- [ ] Signature sai, signer untrusted/revoked, Timestamp hết hạn → deny.
- [ ] Signature hợp lệ nhưng Body chưa ký → deny required signed coverage.
- [ ] Principal A yêu cầu tài nguyên tenant B → method security deny.
- [ ] HTTP filter chooses đúng chain cho mọi SOAP URLs/gateway aliases.
- [ ] Test `@WithMockUser` chỉ được ghi nhận là method authorization test, không giả làm WSS4J test.
- [ ] `MockWebServiceClient` tests không được dùng để khẳng định mTLS handshake success.
- [ ] Có real HTTPS/SOAP integration tests với certificate/key fixtures test.
- [ ] Test A/B context isolation khi request concurrent/reused threads và khi exception xảy ra.
- [ ] Test async executor context propagation và cleanup sau normal/exceptional completion.
- [ ] Test partner bị revoke khi job đang chờ queue → không phát sinh callback trái policy.
- [ ] Test signed SOAP response/Fault được client verify trước sử dụng dữ liệu.
- [ ] Test logs, metrics và SOAP Fault không chứa raw token, private key, signature, PII.
- [ ] Test lại khi nâng Spring Security, Spring-WS, WSS4J, servlet container, JDK hoặc thay gateway topology.

### 18.7. Bảng quyết định nhanh

| Nhu cầu | Thành phần hoặc hướng xử lý |
|---|---|
| Xác thực HTTP request | `SecurityFilterChain`, authentication filter/provider |
| Xác minh TLS client certificate | Servlet container/gateway TLS policy + Spring Security X.509 mapping |
| Xác minh UsernameToken/SOAP Signature | WSS4J/WS-Security policy |
| Đưa verified SOAP signer vào Spring Security | Trusted identity bridge + `AuthenticationManager`/provider |
| Lấy principal trong bounded service invocation | `SecurityContextHolder` với scoped set/restore |
| Kiểm tra role/operation | `@EnableMethodSecurity` và `@PreAuthorize` |
| Kiểm tra order thuộc tenant | Authorization service/DB, không chỉ granted authority |
| Truyền context sang task ngắn | `DelegatingSecurityContextAsyncTaskExecutor` hoặc tương đương |
| Xử lý background job nhiều giờ | Identity reference + worker authentication + reauthorization |
| Tránh lẫn identity giữa requests | Thread-local scope, `finally` cleanup, tests concurrent |
| Xác minh bảo mật SOAP đã thực thi | Signed message integration tests + business side-effect assertions |
| Điều tra sai context | Quan sát auth source, verified principal, context scope, thread boundary |

**Ghi nhớ:** Một `Authentication` có ý nghĩa bảo mật khi được tạo từ **bằng chứng đã xác thực**, ánh xạ vào **đúng business principal và authorities**, đặt trong **đúng SecurityContext của lời gọi** và được sử dụng để kiểm tra **quyền trên tài nguyên cụ thể**. Spring Security HTTP filters, Spring-WS/WSS4J và business authorization là các lớp bổ sung, không tự thay thế nhau. Đường truyền danh tính phải được kiểm chứng cả lúc nhận SOAP, chuyển thread, ghi outbox, gửi callback và xử lý SOAP Fault; kết quả cần được chứng minh bằng negative tests rằng **không request nào thiếu xác minh được dùng quyền hoặc dữ liệu của request khác**.
