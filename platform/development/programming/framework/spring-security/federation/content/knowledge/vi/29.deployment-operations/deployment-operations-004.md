# Đồng bộ đồng hồ và giám sát độ lệch thời gian trong Spring Security Federation

## 1. Vì sao đồng hồ là một phần của an ninh SSO?

Một hệ thống Spring Boot xác thực bằng SAML 2.0, OIDC/OAuth2, Kerberos hoặc CAS cần nhiều máy thống nhất về **thời điểm hiện tại**. Chữ ký số hợp lệ và thông tin tài khoản đúng vẫn chưa đủ: một assertion/token có thể bị từ chối vì chưa đến thời điểm có hiệu lực hoặc đã hết hạn.

Ví dụ, Identity Provider (IdP) phát SAML Assertion lúc 12:00:00 UTC, hiệu lực đến 12:05:00. Một Service Provider (SP) chạy trên VM bị lệch **nhanh 7 phút** sẽ đọc 12:07:00 và xem assertion đã hết hạn. Trên cùng một cluster, một pod đúng giờ chấp nhận JWT còn pod nằm ở node sai giờ từ chối JWT đó, gây chuỗi 200/401 có vẻ ngẫu nhiên.

Điều này ảnh hưởng các hệ:
- SAML IdP và Spring Security SAML SP;
- OpenID Provider/Authorization Server và OIDC client;
- OAuth2 Resource Server kiểm Access Token có chữ ký JWT;
- Kerberos Key Distribution Center (KDC), domain controller, workstation, SPNEGO service;
- CAS Server, service-ticket registries và browser sessions;
- Reverse proxy/ingress, Java hosts, Kubernetes nodes, VMs, session stores và certificate validation.

**Bài Knowledge:** Spring Security - federation → Triển khai và vận hành → **“Đồng bộ đồng hồ và giám sát độ lệch thời gian”**.

### Mục tiêu học tập

Sau bài, người học có thể:

1. Phân biệt wall clock, UTC, timezone, monotonic time, offset, drift, NTP error/uncertainty và protocol clock-skew allowance.
2. Phân tích SAML `IssueInstant`, `NotBefore`, `NotOnOrAfter`, `SubjectConfirmationData` và OIDC/JWT `iat`, `nbf`, `exp`, `auth_time`.
3. Biết Kerberos clock skew không giống dung sai JWT; CAS ticket TTL có quy tắc riêng.
4. Cấu hình/kiểm tra nguồn thời gian trên Linux (`chronyd`, `systemd-timesyncd`) và Windows (`w32tm`).
5. Nhận diện VM/container/Kubernetes node có đồng hồ sai thay vì sửa timezone hoặc tăng JWT lifetime.
6. Đọc `chronyc tracking`, `sources -v`, `sourcestats -v` và các metrics `node_timex_*`.
7. Thiết kế dashboard, ngưỡng cảnh báo và runbook NTP outage, VM restore, clock step/slew.
8. Cấu hình `JwtTimestampValidator` hoặc SAML assertion `clockSkew` theo đúng Spring Security version mà không bỏ validators quan trọng.
9. Viết bài test time boundary với `Clock.fixed` và fixtures được ký hợp lệ.
10. Chạy chương trình Java 17 độc lập minh họa sai lệch đồng hồ và ảnh hưởng của dung sai.
11. Giải thích nguy cơ bảo mật khi nới clock-skew quá lớn và cách kiểm soát replay.
12. Phân biệt lỗi thời gian với lỗi issuer/audience, signature, certificate, ACS hoặc request correlation.

**Phạm vi:** Java 17+, Spring Security Servlet 6.x/7.x, Linux, Windows Server và Kubernetes. Các hostname `example.org`, giá trị offset và ngưỡng alert là ví dụ minh họa. Cần đối chiếu API, phương thức NTP và bảo mật với phiên bản/hạ tầng đang sử dụng.

---

## 2. Bốn khái niệm thời gian không được đánh đồng

### 2.1 Wall-clock time

*Wall clock* là thời điểm tuyệt đối trên lịch, dùng để hỏi “Bây giờ là khi nào?”. Trong Java:

~~~java
import java.time.Instant;

Instant now = Instant.now();
~~~

Trên JVM phổ biến, lời gọi này dựa vào đồng hồ hệ thống. Đồng hồ đó có thể bị chỉnh bởi NTP daemon, hypervisor hoặc người vận hành. Các validator SAML/JWT dựa vào thời gian loại này khi so sánh thời điểm có hiệu lực và hết hạn.

### 2.2 Monotonic time

Dùng `System.nanoTime()` khi cần đo **khoảng thời gian trôi qua** trong cùng JVM:

~~~java
long started = System.nanoTime();
// Thực hiện operation...
long elapsedNanos = System.nanoTime() - started;
~~~

Giá trị `nanoTime()` không là Unix epoch và không thể đem so trực tiếp với JWT `exp` hoặc SAML `NotBefore`. Monotonic clock được thiết kế cho elapsed time, tránh nhiều hệ quả của việc wall clock nhảy. Tính chất cụ thể khi suspend/slew phụ thuộc OS/JVM.

### 2.3 Timezone khác clock offset

- `2026-11-07T12:00:00Z` là một **UTC instant**.
- `Asia/Ho_Chi_Minh` dùng hiển thị instant đó thành thời gian địa phương.
- Chuyển timezone từ GMT+7 sang UTC **không làm một host sai 90 giây trở nên chính xác**.
- JWT `NumericDate` là số giây từ Unix epoch, không cộng/trừ 7 giờ thủ công.
- SAML timestamp cần parse đúng offset/timezone trong XML; không coi chuỗi UTC là `LocalDateTime` không có timezone.

### 2.4 Offset, drift và allowance

| Thuật ngữ | Nghĩa | Đơn vị thường gặp |
| --- | --- | --- |
| Clock offset | Sai khác giữa host clock và nguồn tham chiếu | ms, s |
| Drift | Sai khác tăng dần do oscillator/hệ thống | ms/phút, ppm |
| Frequency correction | Điều chỉnh tốc độ đồng hồ | ppm |
| Root dispersion | Bất định tích lũy từ hệ time source | s |
| Network delay/RTT | Trễ truyền NTP messages | ms |
| Protocol clock skew/leeway | Độ lệch timestamp mà validator chấp nhận | `Duration` |
| Time step | Chỉnh đồng hồ một bước ngay lập tức | s |
| Time slew | Thay đổi tốc độ để đồng hồ hội tụ dần | ppm, thời gian |
| Synchronization status | Có theo time source hợp lệ không | trạng thái/cờ |

**Cực kỳ quan trọng:** trường `Skew` tính bằng ppm từ `chronyc tracking` là *uncertainty về frequency*, **không phải** `clockSkew` trong Spring Security, vốn là một khoảng `Duration`.

## 3. Kiến trúc các bên phải đồng bộ

~~~mermaid
flowchart LR
  T[Approved NTP/NTS time sources]
  T --> I[IdP/Authorization Server nodes]
  T --> S[Spring SP/OIDC Client/API nodes]
  T --> K[Kerberos KDC/DC nodes]
  T --> D[DB/Redis/Queue/Schedulers]
  I -->|SAML/JWT timestamps| S
  K -->|Kerberos tickets| S
  D -->|TTL, replay state, sessions| S
~~~

| Thành phần | Dựa vào thời gian để | Hệ quả nếu lệch |
| --- | --- | --- |
| SAML IdP | Ký Assertion, `IssueInstant`, Conditions | Response phát với mốc mà SP đánh giá sai |
| SAML SP | Conditions, bearer confirmation, request state | Valid signature nhưng authentication fail |
| OIDC Provider | `iat`, `exp`, `auth_time`, optional `nbf` | ID Token bị đánh giá quá sớm/quá hạn |
| OAuth2 Resource Server | JWT `exp`, `nbf`, custom policy | 401 chỉ ở một số pods |
| KDC / Kerberos service | Ticket/authenticator timestamps | Clock skew/replay errors |
| CAS server/registry | Ticket/TGT lifetimes, TTL | ST được xem đã hết hạn hoặc chưa hợp lệ |
| TLS peer | X.509 notBefore/notAfter | Certificate not yet valid/expired |
| Redis, DB, scheduler | Expiry, TTL, retention, event ordering | Session expiry bất thường, audit khó kiểm |
| VM / Kubernetes node | Cung cấp wall clock cho workloads | Nhiều pods cùng sai giờ |

IdP A và SP B có thể **cùng lệch** +5 phút so với UTC nhưng tạm thời login vẫn thành công; điều đó không chứng minh time service đáng tin. Các bên thứ ba, certificates, KDC hoặc token consumer ở node khác vẫn có thể lỗi. Mục tiêu là đồng bộ đến mốc chuẩn được quản lý, không chỉ để hai hệ tình cờ thấy nhau “đúng”.

## 4. SAML: những điểm kiểm tra thời gian

Một ví dụ cấu trúc XML:

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion-1"
    Version="2.0"
    IssueInstant="2026-11-07T12:00:00Z">
  <saml:Issuer>https://idp.example.org</saml:Issuer>
  <saml:Subject>
    <saml:NameID>opaque-user</saml:NameID>
    <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData
          Recipient="https://sp.example.org/login/saml2/sso/idp"
          InResponseTo="_request-1"
          NotOnOrAfter="2026-11-07T12:04:00Z"/>
    </saml:SubjectConfirmation>
  </saml:Subject>
  <saml:Conditions
      NotBefore="2026-11-07T11:59:30Z"
      NotOnOrAfter="2026-11-07T12:05:00Z">
    <saml:AudienceRestriction>
      <saml:Audience>https://sp.example.org/metadata</saml:Audience>
    </saml:AudienceRestriction>
  </saml:Conditions>
</saml:Assertion>
~~~

**Lưu ý:** XML này chỉ minh họa fields, **chưa có XML Signature**, chưa phải SAML Response hợp lệ và không được dùng để tạo phiên đăng nhập.

### Ý nghĩa từng trường

- `Assertion@IssueInstant`: lúc IdP tạo assertion.
- `Response@IssueInstant`: lúc IdP tạo response.
- `Conditions@NotBefore`: assertion không được dùng trước mốc đó theo validation policy.
- `Conditions@NotOnOrAfter`: assertion không được dùng tại/từ thời điểm này trở đi (exclusive).
- `SubjectConfirmationData@NotOnOrAfter`: hạn cuối cho bearer confirmation; có thể ngắn hơn Conditions.
- `SubjectConfirmationData@InResponseTo`: correlation với AuthnRequest theo SP-initiated flow.
- `AuthnStatement@AuthnInstant`: lúc IdP đã xác thực user, khác assertion issue time.
- `AuthnStatement@SessionNotOnOrAfter`: thông tin về session của SAML IdP theo profile; không có nghĩa mọi `HttpSession` SP tự hủy ngay.
- `AuthnRequest@IssueInstant`: thời điểm SP tạo request; có thể liên quan policy request freshness.

### Conditions và SubjectConfirmation cần kiểm độc lập

Nếu:
- `Conditions@NotOnOrAfter = 12:05:00`
- `SubjectConfirmationData@NotOnOrAfter = 12:04:00`
- SP hiện đọc `12:04:30`

thì bearer SubjectConfirmation có thể không hợp lệ dù Conditions chưa hết hạn. Không thể chỉ test Conditions rồi bỏ quy tắc bearer.

### Khác nhau giữa thời gian và trust

Một SAML Assertion có timestamp hợp lệ nhưng thiếu chữ ký đúng/issuer sai/audience sai vẫn phải bị từ chối. Ngược lại, XML Signature đúng **không bỏ qua** việc kiểm Conditions, Recipient và correlation.

## 5. Spring SAML2: cấu hình dung sai theo phiên bản

Tài liệu Spring Security hiện hành minh họa `OpenSaml5AuthenticationProvider.AssertionValidator` và builder `.clockSkew(Duration)`. Một skeleton cho dự án Spring Security 7.x **đã xác minh API phù hợp**:

~~~java
package com.example.saml;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlTimeConfiguration {

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        var provider = new OpenSaml5AuthenticationProvider();
        var validator =
                OpenSaml5AuthenticationProvider.AssertionValidator
                        .builder()
                        .clockSkew(Duration.ofSeconds(45))
                        .build();
        provider.setAssertionValidator(validator);

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());
        http.saml2Login(saml -> saml
                .authenticationManager(new ProviderManager(provider)));
        return http.build();
    }
}
~~~

**Đây là Spring integration snippet**, không phải Java 17 standalone: cần Spring Security SAML2/OpenSAML dependencies, registration repository, SP/IdP metadata và verification credentials. Spring Security 6.x có `OpenSaml4AuthenticationProvider`/version-dependent APIs; **không copy nguyên code 7.x vào 6.x** khi chưa đối chiếu.

`Duration.ofSeconds(45)` là **ví dụ lựa chọn**, không phải một giá trị mặc định trong SAML. Docs có thể dùng 10 phút để minh họa API, **không phải khuyến nghị mở 10 phút trong production**.

### Khi tùy chỉnh phải bảo toàn bộ kiểm chứng

- Default signature/trusted verification credential checks vẫn phải hoạt động.
- Issuer, Destination, AudienceRestriction, bearer Recipient và InResponseTo phải giữ.
- Validation `NotBefore`/`NotOnOrAfter` vẫn hoạt động.
- OneTimeUse/replay policy nếu yêu cầu vẫn phải bảo toàn, không mặc định OpenSAML có global distributed replay cache trong mọi version.
- Không thay custom validator bằng một hàm luôn trả success.
- Kiểm bằng các **signed negative fixtures**; không dùng `@WithMockUser` để chứng minh SAML verifier.

### Nới tolerance không sửa đồng hồ

Nếu SP thực tế nhanh 3 phút, tăng assertion validator clock skew từ 30 giây lên 5 phút có thể làm login “đỡ lỗi” nhưng:
- TTL/replay window hiệu dụng rộng hơn ở những checks áp dụng skew.
- Các hệ khác (TLS, KDC, Resource Server) vẫn lệch.
- Root cause NTP bị che và dần xấu đi.
- Security approval và SLO thực tế không còn rõ.

Sửa time source **trước**, nới skew khi thật sự cần tương thích với một IdP theo profile đã thỏa thuận và review rủi ro.

## 6. OIDC: phân biệt iat, nbf, exp và auth_time

ID Token có thể chứa:

~~~json
{
  "iss": "https://idp.example.org",
  "sub": "user-123",
  "aud": "portal-client",
  "iat": 1794052800,
  "exp": 1794053100,
  "auth_time": 1794052770
}
~~~

Đây chỉ là claim JSON minh họa, **không phải JWT có chữ ký hợp lệ**. Các số `NumericDate` là mốc Unix, không phải giờ địa phương.

| Claim | Ý nghĩa | Cách hiểu |
| --- | --- | --- |
| `exp` | Thời điểm hết hạn, exclusive theo JWT | Khi current time đã tới `exp`, token không còn hợp lệ nếu không có leeway |
| `nbf` | Không có hiệu lực trước thời điểm này | Có thể là optional tùy token/profile |
| `iat` | Thời điểm token được phát | Không tự đồng nghĩa với `nbf` hay `auth_time` |
| `auth_time` | Thời điểm người dùng thực được xác thực | Quan trọng cho `max_age`/step-up/fresh login |
| `nonce` | Ràng buộc response với request login | Không là phép đo đồng hồ |
| `iss` | Issuer tin cậy | Clock đúng không thay verify issuer |
| `aud` | Client nhận ID Token | Không thay bằng skew |
| `state` | Correlation/CSRF OAuth2 authorization flow | Có state TTL riêng, khác JWT expiration |

**Không dùng ID Token làm API access token.** Resource Server nhận OAuth2 Access Token theo contract; OIDC client nhận ID Token theo OIDC validation. API của Spring `JwtTimestampValidator` trong Resource Server không nhất thiết là API cụ thể mà OIDC login ID Token dùng.

### auth_time và max_age

Một ID Token mới phát có thể dựa trên session cũ tại IdP. Vì vậy `iat` có thể vừa mới nhưng `auth_time` đã lâu. Nếu app yêu cầu xác thực lại bằng `max_age`/step-up, cần kiểm tính mới của `auth_time` theo OIDC profile, không cho qua chỉ vì token `exp` còn hạn.

Host lệch giờ có thể gây:
- ID Token bị xem đã hết hạn;
- ID Token bị đánh giá phát trong tương lai theo custom policy;
- `max_age`/freshness bị đánh giá sai;
- Logout/refresh scheduling bất thường.

Không bỏ `nonce`, `state`, signature hoặc `iss` vì chỉnh timestamp.

## 7. OAuth2 Resource Server JWT trong Spring Security

Với Spring Boot Resource Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org
~~~

Mẫu này chưa có audience policy cho API, chưa cấu hình token type, scopes hoặc custom rules. Tài liệu Spring Security Servlet hiện hành mô tả Resource Server mặc định kiểm chữ ký cùng `iss`, `exp` và `nbf` phù hợp configuration, với **default clock skew 60 giây**. Hãy kiểm version và custom decoder đang dùng; không suy 60 giây là default cho SAML, Kerberos hay CAS.

### Custom timestamp validator

~~~java
package com.example.jwt;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtTimeConfiguration {

    private static final String ISSUER = "https://idp.example.org";

    @Bean
    JwtDecoder decoder() {
        NimbusJwtDecoder decoder = (NimbusJwtDecoder)
                JwtDecoders.fromIssuerLocation(ISSUER);

        OAuth2TokenValidator<Jwt> validator =
                new DelegatingOAuth2TokenValidator<>(
                        new JwtTimestampValidator(Duration.ofSeconds(45)),
                        new JwtIssuerValidator(ISSUER));
        decoder.setJwtValidator(validator);
        return decoder;
    }
}
~~~

**Giới hạn bảo mật của snippet:**
- Nó minh họa `JwtTimestampValidator` và `JwtIssuerValidator`, **chưa phải một Resource Server cấu hình hoàn chỉnh**.
- `setJwtValidator(...)` thay validator composition của decoder. **Đừng vô tình bỏ** audience validator, token type validation, custom required-claims checks hoặc các defaults phù hợp phiên bản. Nếu vừa dùng `JwtValidators.createDefaultWithIssuer(...)` vừa thêm timestamp validator khác, validator mặc định có thể vẫn veto và skew mới không hoạt động như tưởng tượng.
- `45 giây` là số giả định, phải được approved và test.
- Signature/JWKS validation vẫn phải đúng; không tin issuer URL từ user input.
- Dùng `NimbusReactiveJwtDecoder` và API reactive riêng khi ứng dụng dùng WebFlux.
- Nếu dùng opaque token introspection, hiệu lực có thể được quyết định ở Authorization Server/introspection service, không phải validator này.
- **Không nhập một JWT đã expired thật rồi tăng skew hàng giờ** để bypass expiration.

### Mô hình time-window đơn giản

Với `notBefore`, `expiresAt`, dung sai `s` và thời gian `now`, một mô hình đơn giản cho validator có leeway:

~~~text
now + s >= notBefore
now - s <  expiresAt
~~~

Đây là công thức **minh họa hành vi chung**, không thay tài liệu API hoặc exact boundary/claim-presence policy của Spring. Các claim `exp/nbf` có thể optional hay required tùy token profile và validator. Nếu có yêu cầu token expiry bắt buộc, kiểm validator/version cụ thể thay vì suy.

### Nơi thường xảy ra lỗi giữa nhiều pods

~~~text
Token expires at:   12:00:30Z
Pod A clock:        12:00:10Z -> ACCEPT
Pod B clock:        12:02:00Z -> EXPIRED
Load balancer:      200, 401, 200, 401...
~~~

Một validation tolerance có thể thay đổi kết quả tùy độ lớn lệch, nhưng root cause là thời gian trên host node. Đừng tăng token lifetime hay bật retry login vô hạn trước khi kiểm NTP.

## 8. Kerberos và Windows Domain

Kerberos sử dụng timestamps trong authenticators và tickets để chống replay và giới hạn tuổi. Client, KDC/domain controller và service server cần lệch nhau trong mức chính sách cho phép. Microsoft mô tả default Kerberos `SkewTime` thường khoảng **5 phút** trong Windows/AD; con số chính xác phụ thuộc chính sách domain và implementation.

### Triệu chứng

- Kerberos/SPNEGO login thất bại với lỗi như `KRB_AP_ERR_SKEW`.
- Một client login được khi kết nối DC A nhưng fail khi dùng DC B.
- Snapshot/restore VM hoặc resume máy tạo sai lệch lớn.
- Service ticket được phát nhưng application server từ chối vì authenticator timestamp.
- Spring Security Kerberos extension dùng GSS/Kerberos của OS/JVM bị ảnh hưởng dù OAuth2/SAML app khác không lỗi.

**Không chỉnh policy Kerberos toàn domain từ 5 phút thành 30 phút chỉ để một máy bị lệch đăng nhập được.** Thay vào đó đo time source ở client, target server, KDCs; kiểm SPN, keytab, realm/DNS nếu lỗi thực chất không phải clock.

### Khác biệt với SAML/JWT

`JwtTimestampValidator` không điều chỉnh clock skew của KDC. `OpenSaml5AuthenticationProvider` cũng không quyết định clock tolerance của Kerberos. Mỗi protocol có cryptographic freshness model riêng và không dùng chung một property “clock-skew” toàn cầu.

## 9. CAS và ticket expiration

CAS Service Ticket (ST) thường có hạn ngắn và one-time use. CAS Ticket Granting Ticket (TGT) cũng có lifetime/idle policy tùy CAS server/version. Sai đồng hồ ở CAS cluster hoặc ticket registry có thể làm tickets bị xem là hết hạn sớm/muộn.

- Không suy ST là JWT và có claim `nbf`/`exp`.
- Xem CAS server ticket registry, TTL và expiration policy cụ thể.
- Test CAS Server nodes có clocks đồng bộ, nhất là khi load balancer chuyển node.
- Validate Service Ticket tại **đúng CAS server và đúng service ID**; lỗi service URL/ticket reuse không sửa bằng NTP.
- Kết nối logout/session token behavior theo CAS SLO implementation, không mặc định mọi Spring HttpSession hết hạn theo TGT.

## 10. TLS và X.509 là một lý do khác phải có đúng giờ

Nếu host nhanh 10 ngày, nó có thể nghĩ certificate “expired”; nếu host chậm nhiều ngày, nó có thể thấy certificate mới “not yet valid”. Lỗi TLS/JWKS/metadata fetch lúc đó xảy ra **trước** SAML/JWT validation.

Các bước cần phân biệt:
- Certificate thật đã hết hạn: **rotate/reissue** certificate, không chỉnh clock lùi.
- Host giờ sai: sửa NTP/Windows Time.
- Trust chain/hostname sai: sửa PKI/trust config.
- SAML signing certificate rotation: xử lý trust và metadata theo hợp đồng IdP/SP.
- OAuth2 JWKS cache cũ: xử lý key rotation và cache, không kết luận là time skew.

**Clock-skew allowance trong SAML/JWT không thay được X.509 certificate validity, TLS trust hoặc các hệ khác.**

## 11. NTP: estimated offset và độ trễ mạng

NTP dùng bốn timestamp theo mô hình:
- `t1`: client gửi request;
- `t2`: server nhận request;
- `t3`: server gửi phản hồi;
- `t4`: client nhận phản hồi.

Hai công thức nền tảng:

~~~text
Estimated offset (server minus client):
  theta ≈ ((t2 - t1) + (t3 - t4)) / 2

Round-trip delay:
  delta ≈ (t4 - t1) - (t3 - t2)
~~~

Ví dụ đơn vị mili-giây:

~~~text
t1=0, t2=525, t3=527, t4=52
theta = ((525-0)+(527-52))/2 = +500ms
delta = (52-0)-(527-525)    =   50ms
~~~

Trong ví dụ mô hình này server nhanh hơn client 500ms. Nhưng đường mạng không luôn đối xứng, còn jitter và thiết bị nguồn có error. NTP/chrony thu thập nhiều samples, nhiều sources để chọn reference và ước lượng bất định. **Một round-trip hoặc HTTP Date header không đủ chứng minh accurate UTC.**

### Stratum không phải thước đo trực tiếp của accuracy

Một source stratum 2 nhưng network jitter lớn có thể kém hữu ích hơn một nguồn stratum 3 ổn định. Ngoài stratum cần xem:
- Root delay và root dispersion;
- Reachability và last received;
- Source selection/falseticker;
- Offset estimates và RMS variation;
- Mức độ tin cậy của nguồn, NTS hoặc trusted infrastructure;
- Uptime/boot drift, VM hypervisor;
- Cross-source consistency.

## 12. Các mô hình đồng bộ thời gian

| Mô hình | Phù hợp | Cần chú ý |
| --- | --- | --- |
| NTP client tới approved servers | Hầu hết Linux/Windows/Cloud | Nguồn, network path, backup |
| NTS-protected NTP | Nguồn hỗ trợ NTS và client có support | NTS-KE/TLS trust và kết nối |
| Corporate NTP hierarchy | Mạng doanh nghiệp/domain | Tránh chọn random public pool |
| Managed cloud time service | VM/nodes trên cloud | Provider docs, network/DNS, guest agent |
| PTP | Workloads cực nhạy thời gian, hạ tầng hỗ trợ | NIC/switch/grandmaster, không mặc định cần cho SSO |
| RTC hardware clock | Boot/offline retention | Không thay ongoing NTP |
| Hypervisor guest-time integration | VM lifecycle | Phối hợp để tránh xung đột chỉnh đồng hồ |

Thời gian chính xác là **security dependency**. Nguồn time server bị spoof/compromised có thể ảnh hưởng token validity và log audit. Dùng trusted sources và xem hỗ trợ NTS khi thích hợp; **không phải mọi NTP server đều hỗ trợ `nts`**.

## 13. Linux với chrony: các lệnh quan sát an toàn

Trên host dùng `chronyd`:

~~~bash
date -u
timedatectl status
chronyc tracking
chronyc sources -v
chronyc sourcestats -v
~~~

Các lệnh này phục vụ quan sát. Nếu daemon chưa cài hoặc service không được dùng, `chronyc` có thể lỗi; điều đó không tự chứng minh host chưa đồng bộ, vì nó có thể dùng `systemd-timesyncd` hoặc time service khác.

### Đọc kết quả chronyc tracking

Ví dụ output **giả lập**:

~~~text
Reference ID    : C0A8010A (ntp-a.example.org)
Stratum         : 3
Ref time (UTC)  : Sat Nov 07 12:00:00 2026
System time     : 0.000850000 seconds fast of NTP time
Last offset     : +0.000230000 seconds
RMS offset      : 0.000400000 seconds
Frequency       : 3.150 ppm fast
Residual freq   : +0.020 ppm
Skew            : 0.160 ppm
Root delay      : 0.016000000 seconds
Root dispersion : 0.002000000 seconds
Update interval : 64.0 seconds
Leap status     : Normal
~~~

Giải thích:
- `Reference ID`: nguồn time đang dùng.
- `Stratum`: cấp NTP logic.
- `Ref time (UTC)`: mốc tham chiếu gần nhất.
- `System time`: ước tính sai khác của system clock với thời gian NTP.
- `Last offset`: sai khác đo lần update gần nhất.
- `RMS offset`: độ dao động offset.
- `Frequency`: oscillator correction.
- `Residual freq`: sai số frequency còn lại.
- `Skew`: uncertainty của frequency **đơn vị ppm**.
- `Root delay`: độ trễ tới nguồn gốc ước tính.
- `Root dispersion`: mức bất định thời gian tích lũy.
- `Update interval`: khoảng giữa updates.
- `Leap status`: trạng thái đồng bộ/leap.

Một process chronyd đang chạy nhưng `Leap status` cho biết chưa synchronized hoặc `Ref time` quá cũ vẫn đáng điều tra. `System time` nhỏ **không bảo đảm** nguồn thời gian đó đúng UTC nếu upstream sai.

### Đọc chronyc sources -v

Các biểu tượng thông dụng:
- `^*`: nguồn NTP hiện được chọn;
- `^+`: nguồn hợp lệ góp phần vào kết hợp;
- `^-`: nguồn hợp lệ nhưng không chọn để kết hợp;
- `^?`: không có đủ dữ liệu hoặc không reachable;
- `^x`: bị phân loại falseticker;
- `^~`: quá biến động.

Kiểm thêm `Reach`, `LastRx`, offset/uncertainty và nguồn có thuộc allow-list hay không. Không chỉ grep thấy `^*` rồi coi mọi SSO security timers an toàn.

### Đọc chronyc sourcestats -v

Chỉ số thống kê theo từng source giúp phát hiện:
- Một upstream lệch dần;
- Jitter/packet loss;
- Nhiều sources bất đồng;
- VM oscillator drift;
- Falseticker xuất hiện sau network changes.

Monitoring tốt theo dõi **cả độ lệch hiện tại và xu hướng**, không chỉ trạng thái service.

## 14. Chrony configuration có kiểm soát

Ví dụ `chrony.conf` cho Linux host:

~~~conf
# Ví dụ hostname trong mạng nội bộ; không phải nguồn time có thật.
server ntp-a.corp.example.org iburst
server ntp-b.corp.example.org iburst
server ntp-c.corp.example.org iburst

driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
~~~

Giải thích:
- `iburst` giúp lấy mẫu nhanh khi startup;
- `driftfile` lưu correction frequency;
- `makestep 1.0 3` cho phép step với offset đủ lớn trong **những updates ban đầu** theo chrony semantics;
- `rtcsync` ảnh hưởng tới cập nhật RTC/kernel sync state trên platform phù hợp;
- file path có thể khác theo distro: `/etc/chrony.conf` hoặc `/etc/chrony/chrony.conf`;
- không thay corporate sources bằng public pool một cách tự ý;
- không để `chronyd` và một daemon khác cùng cạnh tranh chỉnh một clock trừ kiến trúc được thiết kế rõ.

Khi tổ chức cung cấp pool nhiều sources:

~~~conf
pool ntp.corp.example.org iburst maxsources 4
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
~~~

`maxsources` là số nguồn mà chrony cố lấy từ pool, không bảo đảm tất cả nguồn đều tốt. Nếu có NTS server được hỗ trợ và chứng chỉ phù hợp:

~~~conf
server nts-time.corp.example.org iburst nts
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
~~~

Cấu hình NTS phụ thuộc chronyd build, NTS-KE/TLS trust, network ports và server capability. Không thêm `nts` vào server chưa hỗ trợ rồi kết luận NTP “đang an toàn” dù client mất sync.

### Điều không nên làm

- Không chạy `date -s`, `timedatectl set-time` hay `chronyc makestep` trên host đang phục vụ production khi chưa phân tích tác động.
- Không thay đổi sources để trỏ về máy không quản lý.
- Không khởi động hai time daemons cạnh tranh.
- Không đánh giá thành công chỉ vì `systemctl is-active chronyd` trả `active`.
- Không nâng skew SAML/JWT để bỏ qua failure từ NTP.

## 15. systemd-timesyncd hoặc ntpd

Trên một số Linux distro, `systemd-timesyncd` thay chrony:

~~~bash
timedatectl status
timedatectl timesync-status
timedatectl show -p NTPSynchronized
~~~

Lệnh `timesync-status`/property support phụ thuộc systemd version. Một file `/etc/systemd/timesyncd.conf` minh họa:

~~~ini
[Time]
NTP=ntp-a.corp.example.org ntp-b.corp.example.org
FallbackNTP=ntp-c.corp.example.org
~~~

Đây không phải lời khuyên bật cả chrony và timesyncd cùng lúc. Với `ntpd`/`ntpsec`, dùng công cụ tương ứng như `ntpq -p` nếu có. Vận hành phải xác định daemon/time hierarchy thực tế.

`timedatectl` có thể nói NTP service active nhưng việc **đã synchronized chính xác** cần nhìn source, offset, last successful update và daemon logs. Một daemon sống không bằng một đồng hồ đúng.

## 16. Windows Time: w32tm, domain controllers và PDC

Trong Windows/Active Directory, W32Time tham gia time hierarchy. Domain controller/KDC, domain member và dịch vụ Windows khác cần được kiểm phù hợp cấu hình domain.

Các lệnh chẩn đoán:

~~~powershell
w32tm /query /status
w32tm /query /source
w32tm /query /peers
w32tm /query /configuration
~~~

Trên một số hệ thống/quyền truy cập, cần mở command prompt elevated; truy vấn remote host có chính sách riêng.

### Tình huống phổ biến

- PDC emulator có external source sai/hỏng, các DCs nhận giờ sai.
- DC ở chi nhánh mất time sync nhưng vẫn trả Kerberos.
- Hypervisor/VM guest integration tranh quyền điều chỉnh clock.
- VM restore snapshot với thời gian cũ.
- NTP source không reachable qua network/firewall.
- Source thay do Group Policy nhưng một node chưa nhận.
- Windows Time service báo status nhưng offset đo độc lập vẫn lớn.

**Không cấu hình mỗi domain member tự lấy time tùy ý** nếu hệ cần tuân thủ corporate AD hierarchy.

`w32tm /resync` là thao tác can thiệp, không phải lệnh đọc. Chỉ thực hiện theo runbook/change approval, đặc biệt trên KDC, domain controllers hoặc service hosts có state nhạy cảm thời gian. Sau resync phải kiểm time source, offset, Kerberos và SSO flows.

## 17. Kubernetes, container và VM: tìm đồng hồ thực ở node

Linux containers thông thường dùng realtime clock của host kernel. Một container không phải đồng hồ vật lý độc lập; biến môi trường `TZ` hoặc timezone package trong image chỉ chủ yếu ảnh hưởng hiển thị.

### Khi một node lệch giờ

~~~text
IdP clock     12:00:00Z
k8s node A    12:00:00Z   -> pod A login OK
k8s node B    12:00:00Z   -> pod B login OK
k8s node C    12:07:00Z   -> pod C SAML expired
Load balancer             -> success/failure xen kẽ
~~~

Chẩn đoán:
1. Lấy `traceId`, ánh xạ request lỗi về pod và Kubernetes node.
2. Quan sát `date -u` trong pod nếu cần **nhưng kiểm NTP ở node/VM host**.
3. So sánh `chronyc tracking` hoặc time service trên node A/B/C.
4. Kiểm autoscaling, VM migration, suspend/resume, snapshot restore.
5. Kiểm time source/network reachability và node exporter metrics.
6. Nếu ảnh hưởng lớn, SRE có thể cordon/drain unhealthy node theo runbook; không là thao tác tự động cho mọi cảnh báo.
7. Sửa host time sync và recheck tất cả pods trước khi đưa node trở lại traffic.

### Hypervisor cũng có thể ảnh hưởng

- Guest VM time và host time cần chính sách tương thích;
- VM resume/suspend có thể tạo delta lớn;
- Một guest agent và chronyd chạy cạnh tranh có thể tạo step/slew không mong muốn;
- Cloud managed time service có cấu hình networking và region cụ thể;
- Không tắt host/guest time integration theo mẹo chung mà chưa đọc hướng dẫn cloud/hypervisor chính thức.

Nếu Spring app chạy Kubernetes, **readiness** có thể phụ thuộc node time health theo thiết kế platform, nhưng không nên cho mỗi HTTP login gọi NTP bên ngoài đồng bộ trong request path.

## 18. Step và slew: lựa chọn vận hành có rủi ro

**Slew**: chỉnh tốc độ đồng hồ để offset hội tụ dần. Ưu điểm là tránh nhảy UTC lớn, nhưng có thể cần thời gian sửa lỗi lớn.

**Step**: chỉnh tức thời. Một step lớn có thể gây:
- Job scheduler chạy lặp hoặc bỏ lịch;
- Session expiration thay đổi bất ngờ;
- JWT/SAML/certificate đột ngột “expired/not yet valid”;
- Logs có timestamp đảo thứ tự;
- TTL cache/replay window đánh giá không nhất quán;
- Database/queues/audit event order bị khó phân tích;
- Code đo duration bằng wall clock có kết quả âm hoặc quá lớn.

Do đó, thay vì tự chạy `chronyc makestep` ở production:
1. Xác minh source đúng;
2. Đo actual offset và uncertainty;
3. Phân biệt startup host chưa nhận traffic với live production node;
4. Xem platform owner và scheduled maintenance;
5. Nếu cần, isolate/drain node trước bước nhảy lớn;
6. Chọn step/slew theo change plan;
7. Kiểm NTP/SSO/session/scheduler sau remediation;
8. Ghi lại time correction trong audit/incident timeline.

## 19. Giám sát offset chưa đủ: nhiều tín hiệu phải hội tụ

| Metric/tín hiệu | Vai trò | Cảnh báo |
| --- | --- | --- |
| Estimated current offset | Host nhanh/chậm so reference | Vượt mục tiêu, tăng dần |
| Selected NTP source | Đang theo nguồn nào | Source lạ/mất source |
| Last sync/reference age | Đã bao lâu không cập nhật | Nguồn stale |
| Root dispersion/maxerror | Độ không chắc chắn | Cao dù offset nhỏ |
| RMS offset/jitter | Độ ổn định | Dao động tăng |
| Frequency/skew ppm | Oscillator drift | Bất thường sau VM event |
| Kernel time-sync flag | Tình trạng kernel reported | Cần đối chiếu daemon |
| Step/time-adjust events | Có nhảy đồng hồ | Đột ngột |
| SAML expired/not-before failures | App symptom | Correlate node/IdP |
| JWT exp/nbf errors | API symptom | Correlate node/token age |
| Kerberos skew errors | KDC/client/service | Correlate site/DC |
| TLS certificate date errors | Clock hoặc cert issue | Phân biệt với rotation |
| Clock source network errors | NTP unreachable | UDP 123/NTS/TLS/DNS |

Một host có offset nhỏ nhưng nguồn NTP không còn được cập nhật, uncertainty tăng nhanh, vẫn có thể gây sự cố sau vài giờ. Ngược lại metric báo sync lost có thể bị hiểu sai nếu daemon/kernel flag integration chưa đúng.

## 20. Prometheus node_exporter: timex metrics

Trên Linux, `node_exporter` có `timex` collector. Những metric thường gặp gồm:
- `node_timex_offset_seconds`
- `node_timex_sync_status`
- `node_timex_maxerror_seconds`

Theo tài liệu node_exporter, `timex` phản ánh trạng thái kernel. **Một số versions/daemons không duy trì kernel sync flag theo cùng cách**; với chrony, `rtcsync` có liên quan. Do đó không lấy `node_timex_sync_status=0` một mình làm bằng chứng NTP bị hỏng mà không xem `chronyc tracking` và nguồn thật.

### Prometheus alert rule mẫu

~~~yaml
groups:
  - name: time-synchronization
    rules:
      - alert: NodeClockOffsetWarning
        expr: abs(node_timex_offset_seconds) > 0.10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Clock offset above 100ms"
          description: "Inspect approved NTP source and chrony tracking"

      - alert: NodeClockOffsetCritical
        expr: abs(node_timex_offset_seconds) > 1
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Clock offset above 1 second"
          description: "Assess SSO/JWT/Kerberos traffic"

      - alert: NodeTimeSyncFlagLost
        expr: node_timex_sync_status == 0
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Kernel sync flag not set"
          description: "Cross-check chrony configuration and sources"
~~~

**100ms và 1s ở đây chỉ là ví dụ**; từng tổ chức phải xây ngưỡng theo SLO, clock accuracy thực tế, traffic, token lifetime và protocol skew. Một deployment có hạ tầng chính xác cao có thể cần ngưỡng thấp hơn nhiều.

### Khi dùng rule cần kiểm thêm

- Metrics có thực sự xuất hiện từ `timex` collector không?
- Kernel/exporter có hỗ trợ field đó không?
- Label `instance` có ánh xạ đúng tới Kubernetes node/VM?
- Missing metric/scrape failure có cảnh báo riêng, không bị coi là offset zero?
- `node_timex_sync_status` có phản ánh chrony thực tế không?
- Root dispersion, selected source, last successful NTP poll được lấy từ daemon/exporter nào?
- Alert có phù hợp startup grace period và auto-scaling?
- Có tránh duplicate alarms từ node đang drain không?

**Mục tiêu là phát hiện trước khi SSO fail**, không đợi offset lên mức vài phút mới phát alert.

## 21. Thiết kế dashboard phục vụ điều tra federation

Một dashboard hiệu quả có các nhóm:

**Time infrastructure**
- Offset theo region/cluster/node;
- Positive/negative signed offset;
- Selected source/reachability;
- Root dispersion, last sync age;
- Frequency change, clock step count;
- Windows time status/peer source;
- Approved-source compliance.

**Application symptoms**
- SAML conditions/subject-confirmation failure count theo IdP alias và node;
- JWT expired/nbf invalid rate theo API node;
- OIDC token time/freshness rejection theo client;
- Kerberos clock skew errors theo realm/DC;
- Certificate date errors;
- Authentication success/denied rates;
- Session/token expiry anomalies.

**Deployment context**
- Node restart/VM restore;
- IdP/AS rollout;
- NTP source configuration changes;
- Certificate rotation;
- Load-balancer distribution;
- JVM/Spring Security version differences;
- Region/zone.

Không dùng email, NameID, `sub`, raw JWT, cookies, service ticket hoặc session ID làm metric labels. Nếu lỗi đến từ provider exception, chỉ log **structured error category** khi có bằng chứng đáng tin; không đoán từ raw exception message/HTTP 302.

## 22. Đánh giá alarm: nguồn NTP chính xác hay tự báo sai?

Một daemon có thể đã đồng bộ với một upstream server đang **sai UTC**. Vì vậy:
- Kiểm nguồn có thuộc danh sách được tin cậy không.
- Dùng nhiều nguồn (theo network policy) để phát hiện disagreement.
- Xem source stratum nhưng **đừng coi stratum nhỏ là bảo đảm độ chính xác**.
- Quan sát root dispersion, RTT và measurement uncertainty.
- Nếu chính sách yêu cầu, đo so với một reference độc lập hoặc nguồn NTS/PTP.
- Kiểm thời gian ở cả IdP/AS và SP/Resource Server; đừng chỉ kiểm một phía.
- Không lấy HTTP `Date` header như oracle thời gian UTC nếu không biết trust/latency/cache.

### Không nhầm latency với clock skew

Nếu IdP tạo SAML Response lúc 12:00:00 và browser submit nó lúc 12:04:30, hết hạn tại 12:04:00:
- Có thể người dùng dừng ở MFA/browser tab;
- Browser/queue/proxy có chậm;
- IdP đặt bearer lifetime quá ngắn;
- SP clock nhanh;
- Response là static test fixture cũ.

Đo network/browsing latency và clock offset độc lập. **Đừng tăng skew khi user đã thực sự đưa assertion quá muộn** nếu security policy không cho phép.

## 23. Sự cố: SAML `NotBefore` ở tương lai

Giả sử SAML Response đã ký đúng nhưng provider báo Conditions chưa có hiệu lực.

Runbook:
1. Xác định IdP registration, node xử lý ACS và thời điểm UTC.
2. Kiểm signature/issuer/audience/recipient trước để không nhầm lỗi.
3. Đọc `chronyc tracking`/time service ở SP node đó.
4. Nếu có quyền, kiểm IdP host time/time source.
5. Xác định field thực tế bị từ chối: Conditions `NotBefore`, SubjectConfirmation expiry, `IssueInstant` policy hoặc request correlation.
6. Phân biệt browser delay với clock offset.
7. Sửa NTP/VM problem nếu phát hiện.
8. Test lại bằng **signed fixture hợp lệ**, không sửa XML sau khi ký.
9. Chỉ cân nhắc thay SAML skew theo approved contract nếu nguồn thời gian khỏe nhưng vẫn có độ sai số hợp lý.

**Không xóa Conditions khỏi assertion hoặc bỏ signature validation để login pass.**

## 24. Sự cố: JWT 401 ngẫu nhiên giữa các pods

Dấu hiệu:
- Cùng token đến cùng API nhưng response xen kẽ 200 và 401.
- Error có cấu trúc cho biết `exp` hoặc `nbf` invalid ở một số pods.
- Signatures/issuer/audience hợp lệ.

Các bước:
1. Map request trace → pod → host node.
2. So sánh token issue/expiry với trusted reference time, **không log raw token**.
3. Kiểm custom `JwtTimestampValidator`/decoder/skew config có đồng nhất giữa pods?
4. Kiểm node offset, selected source, root dispersion và VM resume events.
5. Kiểm downstream network/time daemon connectivity.
6. Nếu node lệch lớn, containment/drain theo change plan.
7. Sửa NTP và xác nhận positive + negative JWT tests.
8. Điều tra còn lỗi 401 vì token **thật sự hết hạn** hay không, đừng áp “tất cả 401 là clock skew”.

Không nên tự kéo dài JWT lifetime hoặc refresh token policy chỉ để che lỗi một node.

## 25. Sự cố: Kerberos/SPNEGO fail sau restore VM

Một VM snapshot cũ được restore có thể có guest clock quá khứ:
1. Kiểm UTC của guest, hypervisor và KDC/domain controllers.
2. Xem `w32tm` hoặc chrony status/offset.
3. Kiểm source có bị đổi sau restore không.
4. Xác định Kerberos error thật (`KRB_AP_ERR_SKEW` hay SPN/keytab).
5. Nếu cần clock step, đánh giá tác động/tách node trước.
6. Resync theo runbook.
7. Dùng ticket/login mới để kiểm; cached tickets có thể gây hiểu nhầm.
8. Kiểm cả các services dùng cùng VM: TLS, JWT, DB audit.

Thay đổi Kerberos domain policy để nới vài chục phút không phải một cách sửa chuyên nghiệp.

## 26. Phân biệt clock failure và những lỗi SSO khác

| Lỗi | Có thể do đồng hồ? | Cần xác minh |
| --- | --- | --- |
| SAML NotBefore / NotOnOrAfter | Có | Signed SAML, IdP/SP clocks, browser delay |
| SAML Signature invalid | Không sửa bằng clockSkew | Signing key/trust/XML references |
| SAML wrong Audience | Không | Entity ID/SP registration |
| SAML Recipient/Destination wrong | Không | Public ACS/proxy forwarded host |
| SAML InResponseTo mismatch | Không trực tiếp | Saved AuthnRequest/session/RelayState |
| JWT exp/nbf | Có | Token timestamps và Resource Server clock |
| JWT wrong issuer/audience | Không | Trusted issuer/client/API config |
| OAuth2 state/nonce invalid | Không trực tiếp | Browser session/correlation |
| Kerberos skew error | Thường | Client/service/KDC clocks |
| Kerberos principal unknown | Không | SPN/realm/keytab |
| CAS ticket expired | Có thể | CAS ticket TTL và network/browser delay |
| TLS cert not-yet-valid | Có thể | Host clock và cert validity |
| 302 login loop | Có thể nhưng chưa chắc | Cookies/CSRF/metadata/redirect/session |
| Redis/session TTL sai | Có thể | Store clock/expiry semantics |

Không đổi một global “skew” property chỉ vì thấy `authentication_failed`. Phân loại lỗi ở **đúng lớp validation**.

## 27. Kiểm thử timestamp deterministic với `Clock.fixed`

Khi tự viết service kiểm deadline/token issued age, inject `Clock` thay vì hardcode `Instant.now()`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock testClock = Clock.fixed(
        Instant.parse("2026-11-07T12:00:00Z"),
        ZoneOffset.UTC);
Instant current = testClock.instant();
~~~

Sử dụng test clock giúp kiểm ranh giới không phải `Thread.sleep` nhiều giây hoặc đổi đồng hồ OS. `JwtTimestampValidator` trong API Spring Security hiện tại có `setClock(Clock)`; chỉ dùng khi đã kiểm method/version cụ thể và toàn bộ decoder composition sử dụng đúng instance.

### Ma trận boundary tests

| Test | Kỳ vọng |
| --- | --- |
| `now` trước `nbf` quá skew | Từ chối |
| `now` vừa tới `nbf` | Theo exact validator boundary |
| `now` vừa trong cửa sổ | Cho qua time check |
| `now == exp` không skew | Từ chối theo exclusive expiry semantics |
| `now` sau exp quá skew | Từ chối |
| `now` chênh một chút trong approved skew | Có thể chấp nhận theo policy |
| `iat` tương lai | Theo OIDC/JWT custom policy, không tự suy |
| `auth_time` quá cũ với `max_age` | Buộc fresh authentication |
| SAML bearer expiry trước Conditions expiry | Phải tôn trọng bearer deadline |
| SAML signed fixture sai time | Từ chối **do time**, không vì signature hỏng |
| Replay trước expiry | Phụ thuộc OneTimeUse/correlation/replay policy |
| Multi-node JVM có time skew | Phát hiện decision khác nhau và sửa node |

**Đừng chỉnh time field trong XML/JWT sau khi ký rồi dùng sự từ chối đó làm bằng chứng time validator**: chữ ký sẽ sai. Hãy tạo fixture thời gian sai **trước khi ký hợp lệ bằng test key**; giữ các điều kiện khác phù hợp.

## 28. Chương trình Java 17 độc lập: mô phỏng leeway

Chương trình bên dưới dùng **Java Standard Library**, không yêu cầu Spring, không xác minh SAML/JWT signature. Nó làm rõ phép so sánh timestamp và ảnh hưởng của host chạy nhanh.

Tạo file `ClockSkewDemo.java`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public final class ClockSkewDemo {

    private static String validateWindow(
            Instant now,
            Instant notBefore,
            Instant expiresAt,
            Duration leeway) {

        if (leeway.isNegative()) {
            throw new IllegalArgumentException("negative leeway");
        }
        if (now.plus(leeway).isBefore(notBefore)) {
            return "TOO_EARLY";
        }
        if (!now.minus(leeway).isBefore(expiresAt)) {
            return "EXPIRED";
        }
        return "ACCEPT_TIME_ONLY";
    }

    private static long offsetMillis(
            Instant local, Instant reference) {
        return Duration.between(reference, local).toMillis();
    }

    public static void main(String[] args) {
        Instant reference =
                Instant.parse("2026-11-07T12:00:00Z");
        Clock fixed = Clock.fixed(reference, ZoneOffset.UTC);
        Instant correctNow = fixed.instant();
        Instant fastHostNow = reference.plusSeconds(90);

        Instant notBefore = reference.minusSeconds(10);
        Instant expiresAt = reference.plusSeconds(45);

        System.out.println("Reference UTC: " + correctNow);
        System.out.println("Fast host offset ms: "
                + offsetMillis(fastHostNow, reference));

        System.out.println("Correct, skew=0: "
                + validateWindow(correctNow, notBefore, expiresAt,
                        Duration.ZERO));
        System.out.println("Fast, skew=0: "
                + validateWindow(fastHostNow, notBefore, expiresAt,
                        Duration.ZERO));
        System.out.println("Fast, skew=60s: "
                + validateWindow(fastHostNow, notBefore, expiresAt,
                        Duration.ofSeconds(60)));

        System.out.println("Very old, skew=60s: "
                + validateWindow(reference, notBefore,
                        reference.minusSeconds(180),
                        Duration.ofSeconds(60)));

        System.out.println("Future nbf, skew=60s: "
                + validateWindow(reference,
                        reference.plusSeconds(120),
                        reference.plusSeconds(300),
                        Duration.ofSeconds(60)));

        System.out.println("At exp boundary, skew=0: "
                + validateWindow(reference.plusSeconds(45),
                        notBefore, expiresAt, Duration.ZERO));

        System.out.println("In UTC: "
                + correctNow.atOffset(ZoneOffset.UTC));
    }
}
~~~

Chạy:

~~~bash
javac ClockSkewDemo.java
java ClockSkewDemo
~~~

Stdout **chính xác**:

~~~text
Reference UTC: 2026-11-07T12:00:00Z
Fast host offset ms: 90000
Correct, skew=0: ACCEPT_TIME_ONLY
Fast, skew=0: EXPIRED
Fast, skew=60s: ACCEPT_TIME_ONLY
Very old, skew=60s: EXPIRED
Future nbf, skew=60s: TOO_EARLY
At exp boundary, skew=0: EXPIRED
In UTC: 2026-11-07T12:00Z
~~~

**Giải thích:** Host nhanh 90s. Token có `exp=12:00:45Z`. Host đọc 12:01:30Z, tức nhìn token đã hết hạn 45s. Nếu nới tolerance 60s, time-only check vẫn chấp nhận. Điều này **không sửa clock offset**, chỉ làm rộng cửa sổ kiểm. Với host đúng giờ, token được chấp nhận cho tới hạn nominal.

**Giới hạn:**
- Chỉ mô phỏng một cửa sổ `nbf`/`exp` có leeway đối xứng; exact boundary/claim requirement của từng thư viện có thể khác.
- Không verify signature, issuer, audience, recipient, SAML Conditions đầy đủ, OAuth2 state hay OIDC nonce.
- Không đo NTP trên máy thật.
- Không chứng minh replay cache, token revocation hay global policy.
- Kết quả `ACCEPT_TIME_ONLY` **không có nghĩa là Authentication hợp lệ**.
- Đây là chương trình standalone; các Spring Security snippets phía trên cần project/dependencies riêng.

## 29. Integration test và thí nghiệm skew ở môi trường an toàn

### Unit/service tests
- Inject `Clock.fixed` vào business expiration logic;
- Tạo cases exact expiry và not-before boundary;
- Kiểm timezone serialization và UTC Instant;
- Dùng fake time trong phạm vi test, không chỉnh OS production.

### SAML verifier tests
- Dùng test IdP signing key/certificate;
- Tạo Response/Assertion có conditions hợp lệ và không hợp lệ;
- Ký **sau khi** đặt timestamps;
- Giữ đúng issuer/audience/recipient/InResponseTo;
- Kiểm actual OpenSAML provider phản hồi;
- Không dùng `@WithMockUser` làm bằng chứng SAML signature/time validation.

### OIDC/JWT verifier tests
- Dùng test Authorization Server/JWKs và signed tokens;
- Cho tokens với `nbf`, `exp`, `iat`, `auth_time` ở ranh giới;
- Kiểm issuer/audience/nonce vẫn hợp lệ để isolate time validator;
- Kiểm expiration và refresh behavior ở đúng token type;
- Với opaque token, kiểm introspection/AS semantics thay vì giả JWT.

### Staging infra tests
- Mô phỏng một node thời gian sai trong **môi trường isolated/được phê duyệt**;
- Kiểm SSO traffic qua từng node;
- Kiểm clock step/slew, VM suspend/resume, NTP outage/source changes;
- Test HPA/node autoscale và restart recovery;
- Kiểm monitoring đánh dấu host không đủ readiness khi offset vượt policy;
- Không thay đồng hồ KDC/IdP production hoặc các shared CI hosts.

## 30. Alert và SLO: phát hiện trước khi người dùng không đăng nhập được

Một cách thiết kế mục tiêu:
- `measured steady-state offset` phải **nhỏ hơn nhiều** so với `allowed protocol skew`;
- Alarm warning xuất hiện trước khi offset ăn gần hết allowance;
- Có một alert khác cho **nguồn NTP không được cập nhật** dù current offset tạm nhỏ;
- Root dispersion/uncertainty phải ở mức chấp nhận;
- Security-critical service không được nhận traffic nếu clock untrusted theo readiness policy;
- Incident response phải cân nhắc availability **và** rủi ro replay/token được chấp nhận quá hạn.

**Các ngưỡng 100ms, 1s hay 10m for trong ví dụ không phải chuẩn của mọi công ty**. KDC Windows có tolerance mặc định vài phút; một SAML bearer SubjectConfirmation có thể sống chỉ vài phút; một API token TTL cũng có thể ngắn. Dùng đo đạc thực tế, threat model và network topology để chọn.

### Cần alert những sự kiện nào?

1. `abs(offset)` tăng nhanh.
2. Offset vượt warning/critical threshold.
3. Một node chọn source không nằm trong approved set.
4. Root dispersion/maxerror tăng lâu dài.
5. Không có selected sync source.
6. Kernel sync flag lost, sau khi xác nhận daemon semantics.
7. Node exporter missing timex metrics.
8. VM resume/clock step xảy ra.
9. IdP/SP SAML time failures tăng theo node.
10. JWT expired/nbf errors tăng bất thường.
11. Kerberos skew error tăng tại một DC/site.
12. TLS “not yet valid” đồng thời với time alarms.

### Log/metrics tránh lộ thông tin

Ghi trace ID, node, region, IdP alias, validator error category có căn cứ và timestamp UTC. **Không** log raw JWT, SAML Assertion, CAS ticket, password, private key, email hoặc session ID vào public telemetry. Không dùng `sub`/NameID/email làm metric label có cardinality lớn.

## 31. Runbook xử lý time synchronization incident

**Bước 1 — Xác định phạm vi.** App nào? IdP/AS/SP/KDC/DB? Một node hay nhiều nodes? Bắt đầu từ lúc nào? Có trùng deploy/VM resume không?

**Bước 2 — Xác định lỗi.** Signature/issuer/audience fail khác NotBefore/NotOnOrAfter. Kerberos skew khác SPN failure. TLS not-yet-valid khác certificate chain unknown.

**Bước 3 — Đọc thời gian host.** Linux: `date -u`, `chronyc tracking`, `chronyc sources -v`; Windows: `w32tm /query /status`, `/source`. So giữa nodes và approved time sources.

**Bước 4 — Kiểm nguồn.** NTP servers, DNS, UDP 123/network, NTS certificate/connectivity, domain time hierarchy, hypervisor/guest agent.

**Bước 5 — Containment.** Nếu node có nguy cơ chấp nhận token quá hạn hoặc fail login diện rộng, cân nhắc route/drain node theo change policy. Không tăng skew bừa bãi.

**Bước 6 — Remediation.** Sửa nguồn NTP, daemon config hoặc VM time issue. Đánh giá bước clock step/slew và tác động lên jobs/sessions/DB.

**Bước 7 — Verify.** Kiểm selected source, offset, uncertainty, last sync, health qua nhiều chu kỳ; chạy SAML/OIDC/JWT/Kerberos positive + negative tests.

**Bước 8 — Khôi phục.** Đưa node healthy trở lại traffic; rollback bất kỳ temporary skew exception nào đã được incident approval.

**Bước 9 — Postmortem.** Ghi root cause, thời gian gián đoạn, security impact, alert blind spots, config drift và hành động phòng ngừa.

## 32. Các lỗi vận hành thường gặp

| Sai lầm | Vì sao nguy hiểm | Giải pháp |
| --- | --- | --- |
| Tăng SAML/JWT skew lên 30 phút | Token/assertion validity mở rộng, che NTP lỗi | Sửa clocks, giới hạn allowance |
| Sửa timezone để “sửa giờ” | Chỉ thay cách hiển thị | Kiểm offset thực theo UTC |
| `chronyd` chạy tức là synchronized | Có thể mất nguồn, root dispersion tăng | Đọc tracking/sources/status |
| Tin stratum nhỏ chắc chính xác | Stratum không phản ánh toàn bộ network/source quality | Kiểm uncertainty/trust |
| Chỉ monitor container clock | Bỏ qua node/VM time source | Monitor Kubernetes nodes |
| Chỉ alert ở ngưỡng Kerberos 5 phút | User đã gặp nhiều lỗi trước alarm | Warning thấp hơn tolerance |
| Dùng HTTP Date làm đồng hồ chuẩn | Network/cache/proxy delay và trust yếu | Approved NTP/NTS reference |
| Bỏ SAML `NotBefore` validator | Hạ bảo mật để che lỗi | Sửa IdP/SP clock |
| Sửa signed XML timestamp sau ký | Signature hỏng, test sai nguyên nhân | Sinh fixture mới rồi ký |
| Bỏ `exp` để JWT cũ pass | Token hết hạn được chấp nhận | Enforce expiry, sửa clock |
| `setJwtValidator` chỉ thêm timestamp | Có thể xóa audience/issuer/custom checks | Compose đầy đủ validators |
| Chạy `chronyc makestep` tùy tiện | Clock jump ảnh hưởng sessions/jobs | Change plan/maintenance |
| Chạy hai time daemons cạnh tranh | Giờ bị điều chỉnh bất thường | Một time hierarchy có chủ |
| Bỏ qua Windows KDC clocks | Kerberos fail dù Spring đúng | Kiểm DC/PDC W32Time |
| Bỏ qua startup node chưa sync | Pod mới nhận traffic quá sớm | Readiness/time source policy |
| Cache/TTL đo bằng wall clock sai | Session expiry/retention bất thường | Monotonic duration và correct UTC deadlines |
| Clock alert chỉ nhìn sync flag | Daemon có thể không cập nhật kernel flag | Đối chiếu chrony/root dispersion |
| Coi mọi 401 là NTP | Có thể là issuer/audience/token invalid | Phân loại theo validator layer |
| Bỏ qua leap/smear policy | Sources khác chính sách làm UTC lệch tại event đặc biệt | Đảm bảo source compatibility |
| Tắt certificate checks do TLS lỗi | Mở lỗ hổng PKI | Phân biệt time offset và cert validity |

## 33. Bài tập ôn tập có đáp án

**Câu 1.** Đổi timezone từ GMT+7 sang UTC có làm UTC clock chính xác hơn không?

**Đáp án:** không; timezone chỉ đổi biểu diễn thời gian, NTP/time synchronization mới sửa offset.

**Câu 2.** `System.nanoTime()` có phải thời gian Unix epoch không?

**Đáp án:** không. Dùng đo elapsed duration, không dùng cho JWT/SAML deadline.

**Câu 3.** SAML Conditions còn hạn nhưng bearer SubjectConfirmation đã quá hạn. Có được login không?

**Đáp án:** không nếu bearer confirmation không đạt validator policy; các điều kiện được xét độc lập.

**Câu 4.** Token JWT có signature đúng nhưng `nbf` trong tương lai quá tolerance, có cho qua không?

**Đáp án:** không; cryptographic validity không thay time-window validation.

**Câu 5.** Spring Resource Server hiện hành nêu default clock skew bao nhiêu?

**Đáp án:** tài liệu hiện tại nêu 60 giây. Cần xem version/custom decoder, không mặc định cho SAML/Kerberos.

**Câu 6.** `JwtTimestampValidator(Duration.ofSeconds(45))` có sửa đồng hồ OS không?

**Đáp án:** không. Nó chỉ nới phép so sánh timestamp.

**Câu 7.** `JwtDecoder#setJwtValidator(...)` có thể bỏ validators nào nếu dùng sai?

**Đáp án:** issuer, audience, token-type/custom required-claim checks hoặc defaults khác; cần composition đầy đủ.

**Câu 8.** Kerberos Windows/AD thường có tolerance mặc định cỡ bao nhiêu?

**Đáp án:** Microsoft nêu khoảng 5 phút theo policy phổ biến; đồng hồ healthy nên lệch nhỏ hơn nhiều.

**Câu 9.** `chronyc tracking` field `Skew` là Spring SAML `clockSkew` không?

**Đáp án:** không, chrony là frequency uncertainty tính ppm; Spring là time Duration.

**Câu 10.** `node_timex_sync_status=1` có chứng nhận offset < 1 ms không?

**Đáp án:** không. Cần offset/uncertainty, approved sources và daemon metrics.

**Câu 11.** Tại sao container `date -u` sai? Nên sửa ở đâu?

**Đáp án:** Linux container thường dùng host node realtime clock; kiểm NTP/VM host thay vì đổi timezone hoặc tự chạy privileged NTP trong từng pod.

**Câu 12.** `chronyd active` nhưng nguồn time không reachable có thể login SAML fail không?

**Đáp án:** có, service liveness không đồng nghĩa synchronized.

**Câu 13.** NTP step và slew khác gì?

**Đáp án:** step nhảy clock tức thì, slew đổi tốc độ để hội tụ; step có thể ảnh hưởng logs, token windows, sessions và schedulers.

**Câu 14.** Một signed SAML fixture bị sửa `NotBefore` sau khi ký rồi từ chối chứng minh time validator đúng chưa?

**Đáp án:** chưa. Signature hỏng có thể là nguyên nhân. Cần sinh wrong-time fixture và ký hợp lệ.

**Câu 15.** `auth_time` và `iat` trong OIDC có giống nhau không?

**Đáp án:** không. `auth_time` là lúc end user thực được xác thực; `iat` là lúc token được phát.

**Câu 16.** Host chạy chậm 2 phút có nguy cơ gì?

**Đáp án:** tùy validator, có thể tiếp tục chấp nhận token đã hết hạn so với UTC hoặc đánh giá bước xác thực sai.

**Câu 17.** Root dispersion lớn nhưng current offset nhỏ có cần điều tra?

**Đáp án:** có; uncertainty lớn có thể báo nguồn mất sync và clock không còn đáng tin.

**Câu 18.** Một node chạy nhanh 7 phút, pod khác đúng giờ. Có thể xuất hiện 200/401 luân phiên không?

**Đáp án:** có. Load balancer chuyển request giữa nodes có quyết định timestamp khác nhau.

**Câu 19.** Certificate “not yet valid” chắc chắn do timezone sai không?

**Đáp án:** không. Cần xem UTC clock và certificate validity/deployment/trust thực tế.

**Câu 20.** Có nên bật NTS với bất kỳ NTP server nào không?

**Đáp án:** không; client build, server NTS, TLS trust và network phải hỗ trợ.

**Câu 21.** CAS ticket expiry có phải `JwtTimestampValidator` kiểm không?

**Đáp án:** không; CAS ticket lifetime do CAS server/registry implementation quyết định.

**Câu 22.** Alert ở đúng ngưỡng Kerberos 5 phút có tốt không?

**Đáp án:** không nên là alert đầu tiên; phải có early warning thấp hơn nhiều so với ngưỡng ảnh hưởng.

**Câu 23.** Một node có `^*` trong chronyc sources đã đủ chứng minh đồng hồ đúng tuyệt đối chưa?

**Đáp án:** chưa; kiểm root dispersion, trust/accuracy của source và offset thực.

**Câu 24.** Lỗi SAML Signature invalid có sửa được bằng tăng `clockSkew` không?

**Đáp án:** không. Đây là lỗi trust/signature hoặc dữ liệu/XML.

**Câu 25.** Vì sao không gọi NTP server trực tiếp trong mỗi login request?

**Đáp án:** thêm latency/failure dependency, nguồn có thể unavailable; nên đồng bộ OS qua daemon và kiểm readiness/telemetry.

## 34. Checklist production

- [ ] IdP/AS/SP/KDC/Resource Server nodes dùng time sources được phê duyệt.
- [ ] Đồng hồ được xem theo UTC Instant; timezone chỉ cho hiển thị.
- [ ] Host/container/VM responsibility được xác định rõ.
- [ ] Không có hai daemon/time agents cạnh tranh điều chỉnh clock.
- [ ] Có nhiều time sources tin cậy hoặc failover phù hợp.
- [ ] NTS dùng khi client/server hỗ trợ và trust/network được xác minh.
- [ ] `chronyc tracking/sources` hoặc `w32tm` health được giám sát.
- [ ] Có offset, root dispersion/uncertainty và source age metrics.
- [ ] Prometheus timex metrics được kiểm có thật và diễn giải đúng daemon.
- [ ] Missing metric/scrape failure có alert, không bị coi là offset 0.
- [ ] Warning thresholds nhỏ hơn protocol tolerance, có critical threshold.
- [ ] Kubernetes node/VM time health được monitor, không chỉ app pods.
- [ ] Có chiến lược startup readiness khi host chưa synchronized.
- [ ] Có runbook VM resume/snapshot/clock jump và time source outage.
- [ ] Step vs slew được phê duyệt trên production hosts.
- [ ] Spring SAML `clockSkew` gắn với profile/version và security approval.
- [ ] SAML signature/issuer/audience/recipient/Conditions validators còn nguyên.
- [ ] JWT `exp`/`nbf` được kiểm với skew được đo, không tăng tùy ý.
- [ ] Custom `setJwtValidator` giữ issuer/audience/token-policy checks đầy đủ.
- [ ] OIDC `auth_time`, `max_age`, `nonce` không bị đánh đồng với `iat`.
- [ ] Kerberos KDC/DC clock được kiểm theo domain policy.
- [ ] CAS Ticket TTL và store clocks được kiểm theo implementation.
- [ ] TLS certificate validity được phân biệt với time drift và key rotation.
- [ ] Time-boundary tests dùng `Clock.fixed`/signed fixtures.
- [ ] Không chỉnh timestamps trong signed payload sau khi ký.
- [ ] Session/replay/OneTimeUse/revocation policy vẫn kiểm đủ sau thay skew.
- [ ] Logs dùng UTC + trace IDs, tránh raw tokens/assertions/PII.
- [ ] Alerts liên kết host metrics với SAML/JWT/Kerberos failure categories.
- [ ] Sau remediation kiểm positive và negative SSO flows trên nhiều nodes.
- [ ] Nếu nới skew tạm trong incident, có owner/expiry/rollback plan.
- [ ] Đã rà soát source/time config drift theo cluster/region và KDC site.

## 35. Tổng kết

**Đồng bộ đồng hồ là điều kiện vận hành của xác thực liên kết, không chỉ là sở thích định dạng logs.** Một IdP phát SAML/JWT đúng chữ ký nhưng SP chạy sai giờ vẫn có thể từ chối; một SP chạy chậm quá mức cũng có thể làm cửa sổ chấp nhận tokens rộng hơn dự định.

Năm nguyên tắc thực dụng:

1. **Sửa clock infrastructure trước:** approved NTP/NTS/chrony/W32Time, kiểm đúng host/VM/Kubernetes node.
2. **Clock-skew chỉ là allowance cho validator:** nới skew không phải phương pháp sửa clock; có đánh đổi bảo mật.
3. **Đọc nhiều tín hiệu:** offset + uncertainty + selected source + last sync + app time failures.
4. **Test đúng nguyên nhân:** signed SAML/JWT fixtures có timestamps cố ý sai nhưng chữ ký/trust và các conditions khác đúng.
5. **Bảo đảm incident readiness:** runbook step/slew, NTP outage, VM resume, multi-node inconsistency và security impact.

Mục tiêu là **một thời gian UTC đáng tin, được giám sát và có sai số nhỏ**, để Spring Security có thể giữ nguyên các validation quan trọng, chứ không phải mở cửa thời gian đến khi mọi token đều được chấp nhận.

### Tài liệu chính thức tham khảo

1. Spring Security — Resource Server JWT, Customizing Timestamp Validation và default clock skew: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
2. Spring Security — SAML2 Authentication, AssertionValidator clock skew: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
3. Spring Security — JwtTimestampValidator API, `setClock`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html
4. OASIS SAML 2.0 Core, assertion Conditions và SubjectConfirmation: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
5. OpenID Connect Core 1.0, ID Token claims và `max_age`: https://openid.net/specs/openid-connect-core-1_0.html
6. RFC 7519 — JSON Web Token, NumericDate, exp/nbf/iat: https://www.rfc-editor.org/rfc/rfc7519.html
7. Chrony — chronyc tracking/sources/sourcestats: https://chrony-project.org/doc/4.4/chronyc.html
8. Chrony — chrony.conf configuration: https://chrony-project.org/doc/latest/chrony.conf.html
9. Chrony — Configuration examples and accuracy: https://chrony-project.org/examples.html
10. Prometheus node_exporter — Monitoring time sync with timex: https://github.com/prometheus/node_exporter/blob/master/docs/TIME.md
11. Prometheus node_exporter — NodeClockSkewDetected/NodeClockNotSynchronising alert examples: https://github.com/prometheus/node_exporter/blob/master/docs/node-mixin/alerts/alerts.libsonnet
12. Microsoft Learn — Windows Time Service Tools and Settings (`w32tm`): https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/windows-time-service-tools-and-settings
13. Microsoft Learn — Kerberos protocol KDC configuration, typical SkewTime default: https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-protocol-registry-kdc-configuration-keys
14. Microsoft Learn — Authoritative time source for PDC: https://learn.microsoft.com/en-us/services-hub/microsoft-engage-center/health/remediation-steps-ad/configure-the-root-pdc-with-an-authoritative-time-source-and-avoid-widespread-time-skew
15. IETF RFC 8915 — Network Time Security for NTP: https://www.rfc-editor.org/rfc/rfc8915.html