# Chẩn đoán lỗi thời gian, múi giờ và độ lệch đồng hồ trong Spring Security Federation

## 1. Bài toán thực tế và kết quả cần đạt

Một hệ thống Spring Security đăng nhập liên kết có thể thỉnh thoảng từ chối **SAML 2.0 Assertion**, **OIDC ID Token**, **OAuth 2.0 Access Token**, **CAS ticket** hoặc session ngay cả khi chữ ký, issuer và cấu hình URL có vẻ đúng. Lỗi thường chỉ xuất hiện ở một số pod, vào lúc chuyển giờ, ngay sau phát hành token hoặc sát thời điểm hết hạn. Các thông báo có thể là `Assertion is not yet valid`, `Assertion has expired`, `Jwt expired`, `nbf is in the future`, `invalid_grant`, session state/authorization request expired hoặc certificate not yet valid.

Có ít nhất **bốn nguyên nhân độc lập** phải phân biệt:

1. **Đồng hồ vật lý của một node sai**: IdP nghĩ thời điểm hiện tại là 10:00:50, trong khi Spring SP đang thấy 10:00:00; mọi điều kiện thời gian bị dịch.
2. **Múi giờ hiển thị hoặc parse sai**: cùng một `Instant` được hiển thị thành UTC và giờ Việt Nam khác nhau; hoặc code bỏ mất offset khi parse dẫn đến so sánh lệch đúng nhiều giờ.
3. **Độ trễ hợp lệ đã hết**: assertion, token, ticket thực sự quá hạn, một phiên login/browser mất thời gian quá lâu; đồng hồ hoàn toàn đúng cũng phải từ chối.
4. **Chính sách clock skew sai hoặc không đồng nhất**: một service cho phép lệch 30 giây, service khác 0 giây; đôi khi mã hết hạn được chấp nhận quá lâu do nới skew.

Bài thuộc nhóm **Quan sát và gỡ lỗi** của module **Spring Security - federation**. Mục tiêu là xác định đúng tầng lỗi, đo sai lệch thực, phân tích mốc `NotBefore`/`NotOnOrAfter` và `nbf`/`exp`, đọc logs an toàn, cấu hình validator trong Spring, test có thời gian cố định với **Java 17**, và khắc phục **nguyên nhân đồng bộ thời gian** thay vì vô hiệu hóa validation.

**Quy tắc an toàn:** Clock skew (*leeway*) là một dung sai nhỏ cho các đồng hồ phân tán, **không** phải cách cho phép Assertion/token hết hạn nhiều giờ. Không dùng `permitAll()`, tắt chữ ký, bỏ kiểm audience/recipient hoặc đặt skew vô hạn để “chữa” lỗi thời gian.

## 2. Ba khái niệm thường bị đánh đồng

| Khái niệm | Định nghĩa | Ví dụ | Khi nào thực sự gây lỗi? |
| --- | --- | --- | --- |
| **Instant / thời điểm tuyệt đối** | Một điểm duy nhất trên timeline, thường chuẩn UTC | `2026-11-07T03:00:00Z` | Đồng hồ nguồn/đích đo sai thời điểm hiện tại |
| **Time zone / múi giờ** | Quy tắc đổi Instant thành ngày giờ dân sự, bao gồm DST nếu có | `Asia/Ho_Chi_Minh` hoặc `Europe/Berlin` | Code parse/so sánh local time như thời điểm tuyệt đối |
| **UTC offset** | Độ lệch giờ tại một thời điểm, có dạng `+07:00` | `2026-11-07T10:00:00+07:00` | Code bỏ offset hoặc gắn offset sai |
| **Clock skew** | Chênh lệch giữa đồng hồ nguồn và validator tại cùng thời điểm thực | SP nhanh hơn IdP 45 giây | Artifact bị coi “chưa hợp lệ” hoặc “đã hết hạn” |
| **Latency** | Thời gian qua network, browser redirect, IdP xử lý và queue | SAML POST mất 5 giây | Timestamp có thời hạn ngắn đã hết trước khi kiểm |
| **Validity window** | Khoảng thời gian một assertion/token được chấp nhận | `[NotBefore, NotOnOrAfter)` | Request đến ngoài khoảng được phép |
| **TTL** | Thời gian sống do issuer/service xác định | Token 5 phút | Token thật sự hết hạn hoặc replay |
| **Clock skew allowance** | Dung sai validator cho khác biệt nhỏ | `Duration.ofSeconds(60)` | Cấu hình quá rộng làm tăng replay window |

Một điểm khác quan trọng: **đổi timezone JVM không làm đồng hồ chạy nhanh/chậm hơn**. Nếu `Instant.now()` trên node vẫn đúng, `Europe/Berlin` và `Asia/Ho_Chi_Minh` chỉ làm khác **cách hiển thị**. Nếu code tự biến `LocalDateTime` thành `Instant` bằng timezone mặc định thì đổi timezone có thể làm **logic ứng dụng sai**; đó là lỗi parse/mapping, không phải bằng chứng NTP sai.

### Minh họa cùng một thời điểm

~~~text
UTC:
  2026-11-07T03:00:00Z

Vietnam time (UTC+07):
  2026-11-07T10:00:00+07:00

Both represent exactly the SAME Instant.

Wrong interpretation:
  parse 2026-11-07T10:00:00 as UTC
  => shifts the actual instant forward by 7 hours
~~~

Với định dạng có `Z` hay `+07:00`, hãy parse thành `Instant` hoặc `OffsetDateTime` rồi so sánh trên timeline; không so chuỗi giờ địa phương với ISO UTC hoặc với giờ trong dashboard.

## 3. Những đồng hồ nào tham gia luồng federation?

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant I as IdP clock
    participant P as Proxy/load balancer
    participant S as Spring SP clock
    participant R as Resource Server clock
    B->>I: SSO login
    I->>I: IssueInstant, NotBefore, NotOnOrAfter
    I-->>B: SAMLResponse hoặc OIDC authorization code
    B->>P: Redirect/POST callback
    P->>S: Forward request
    S->>S: Check signature/issuer, then validity at current time
    S-->>B: Session or failure
    opt API Access Token later
        B->>R: Authorization: Bearer token
        R->>R: Check exp/nbf and local clock
        R-->>B: 200 or 401
    end
~~~

Đồng hồ đáng quan tâm:

- **IdP/Authorization Server** phát timestamp trong Assertion, ID Token, Access Token và tạo session/ticket.
- **Spring Service Provider/Relying Party** đọc thời điểm hiện tại để kiểm các điều kiện từ IdP.
- **API Resource Server** có thể là hệ thống khác, đồng hồ riêng, xử lý JWT `exp`/`nbf`.
- **CAS Server** thường quản lý tuổi thọ ticket ở server; `CAS Service Ticket` không nhất thiết mang `NotOnOrAfter` kiểu SAML.
- **Reverse proxy/WAF** ghi thời gian request và có thể thêm queue/caching/latency; bản thân proxy không nhất thiết làm việc validate Assertion.
- **Browser** có đồng hồ địa phương phục vụ JS/cookie/UX, nhưng **SAML SP server-side** và **JWT Resource Server** không nên tin browser clock để quyết định quyền; cookie/session behavior có thể bị ảnh hưởng theo client.
- **Container/node VM**: `TZ`/`-Duser.timezone` chi phối hiển thị, còn nguồn system clock do kernel/hạ tầng cung cấp; không giả định mỗi container có một hardware clock riêng biệt.

**Không chỉ kiểm giờ máy developer.** Trong Kubernetes, các worker nodes/pods của IdP và SP có thể trải trên nhiều hosts; một node lệch 90 giây tạo lỗi ngẫu nhiên “pod A PASS, pod B FAIL” trong khi cả hai có cùng code/config.

## 4. SAML 2.0: NotBefore và NotOnOrAfter

Trong SAML Core, `<saml:Conditions>` có thể có:

~~~xml
<saml:Conditions
    NotBefore="2026-11-07T03:00:00Z"
    NotOnOrAfter="2026-11-07T03:05:00Z">
  <saml:AudienceRestriction>
    <saml:Audience>https://sp.example/metadata</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

**Không phải Assertion hoàn chỉnh**: ví dụ lược bỏ XML Signature, issuer, subject, subject confirmation và các trường khác.

Ngữ nghĩa thời gian của Conditions:

- **`NotBefore`:** không chấp nhận Assertion **trước** mốc này; tại đúng mốc bắt đầu là hợp lệ nếu các điều kiện khác đều đúng.
- **`NotOnOrAfter`:** không chấp nhận Assertion **kể từ** mốc này; tại đúng mốc kết thúc đã hết hạn.
- Khoảng hợp lệ theo mô hình không skew là **`[NotBefore, NotOnOrAfter)`**, tức bắt đầu **bao gồm**, kết thúc **không bao gồm**.
- Các thuộc tính thời gian có thể vắng mặt theo profile và validator; đừng tự suy “missing expiration = unlimited acceptance”. Hợp đồng ứng dụng/IdP cần giới hạn freshness, subject confirmation và replay.
- Đừng sửa XML timestamps do IdP đã ký rồi mong chữ ký còn đúng.

### Bảng ranh giới SAML không skew

| SP current UTC time | NotBefore | NotOnOrAfter | Kết luận chỉ xét Conditions |
| --- | --- | --- | --- |
| 02:59:59 | 03:00:00 | 03:05:00 | **Chưa hợp lệ** |
| 03:00:00 | 03:00:00 | 03:05:00 | Hợp lệ tại đầu khoảng |
| 03:04:59 | 03:00:00 | 03:05:00 | Hợp lệ trong khoảng |
| 03:05:00 | 03:00:00 | 03:05:00 | **Hết hạn** |
| 03:05:01 | 03:00:00 | 03:05:00 | **Hết hạn** |

Tất cả thời gian ở bảng cùng ngày và UTC, chỉ để làm rõ boundary; một real SAML response vẫn phải qua chữ ký, issuer, audience, recipient, subject confirmation và correlation/replay checks.

### SubjectConfirmationData còn một khoảng riêng

Trong Web Browser SSO, `<saml:SubjectConfirmationData>` kiểu bearer có thể mang `Recipient`, `InResponseTo` và `NotOnOrAfter`:

~~~xml
<saml:SubjectConfirmation Method=
    "urn:oasis:names:tc:SAML:2.0:cm:bearer">
  <saml:SubjectConfirmationData
      InResponseTo="_authn-request-test-01"
      Recipient="https://sp.example/login/saml2/sso/corp"
      NotOnOrAfter="2026-11-07T03:02:00Z"/>
</saml:SubjectConfirmation>
~~~

**Điều kiện bị giới hạn chặt hơn**: ngay cả khi Conditions còn tới 03:05, bearer SubjectConfirmationData hết hạn lúc 03:02 thì Response lúc 03:03 phải bị từ chối bởi subject confirmation validator. Không chỉ kiểm mỗi Conditions rồi coi SAML login hợp lệ.

Ngoài ra phải kiểm `Recipient`, `InResponseTo` theo SP-initiated flow, đúng subject confirmation method, issuer, audience và request correlation. Nếu IdP cho IdP-initiated SSO, policy `InResponseTo`/response correlation khác với SP-initiated; không nới tự do nếu chưa có trust model.

## 5. IssueInstant không phải NotOnOrAfter

SAML Response và Assertion có thể có `IssueInstant`. Đây là **thời điểm được phát hành**, không tự là thời điểm bắt đầu/kết thúc hiệu lực của bearer confirmation. Một số validator/profile có giới hạn freshness của `IssueInstant` hoặc response age; không được nhầm với `NotBefore` hay `NotOnOrAfter`.

Ví dụ:

~~~text
Response IssueInstant:             03:00:00Z
Assertion Conditions NotBefore:    02:59:30Z
Assertion Conditions NotOnOrAfter: 03:05:00Z
SubjectConfirmationData expiry:   03:02:00Z
SP receives at:                   03:02:30Z

Conclusion:
  Conditions may still be within window.
  Bearer subject confirmation has already expired.
  Authentication must fail unless a narrowly approved leeway
  and the actual profile validator allow it.
~~~

Một lỗi thường gặp là lấy **Response IssueInstant** rồi tự cộng 5 phút làm “valid-until” và bỏ qua SubjectConfirmationData. Đây là cách tự chế SAML validator không an toàn. Spring Security/OpenSAML thực hiện các validations theo cấu hình; business code **không** nên parse raw XML để thay provider.

### Có được áp dụng skew vào mọi trường cùng lúc?

Không mặc định. **Clock skew allowance** thuộc về **validator của một loại điều kiện**. Spring/OpenSAML có default validators cho Conditions/SubjectConfirmationData, có thể có response-specific checks và policies riêng. Cần kiểm docs và integration tests cho phiên bản thực, thay vì giả định một property thay đổi mọi timestamp ở mọi path.

## 6. Clock skew: hướng lệch và khoảng chấp nhận

Giả sử:
- IdP issue Assertion có `NotBefore = 03:00:00Z`.
- SP tại cùng thời điểm thực chỉ thấy `02:59:40Z`, **chậm 20 giây**.
- Không skew: SP nhận Assertion **chưa hợp lệ**.
- Nếu SP validator cho leeway **30 giây**, Assertion có thể được chấp nhận về mặt thời gian (các kiểm tra khác vẫn bắt buộc).

Trường hợp ngược:
- IdP đặt `NotOnOrAfter = 03:05:00Z`.
- SP đồng hồ **nhanh 20 giây**, đọc `03:05:10Z` khi thời gian thực là 03:04:50.
- Không skew: SP thấy **đã hết hạn**.
- Leeway 30 giây có thể cho phép SP chấp nhận sát biên.

Tư duy công thức cho một cửa sổ kiểu `[start, end)`, với `now` và tolerance `s ≥ 0`:

~~~text
Start check:
  now + s >= start

End check:
  now - s < end

Combined:
  (now + s >= start) AND (now - s < end)
~~~

Đây là **mô hình giáo dục** để giải thích leeway; các thư viện có thể có comparison details/precision riêng theo SAML/JWT/profile, nên **không dùng công thức này để thay Spring/OpenSAML security validator**.

**Tác động bảo mật:** cho phép skew 10 phút có thể chấp nhận một Assertion/token quá hạn **tới 10 phút theo clock của validator** hoặc sớm hơn thời điểm bắt đầu 10 phút. Vì thế đây là nới vùng nhận credentials, tăng khả năng replay trong những hệ thống thiếu chống replay. Skew phải nhỏ, có căn cứ đo, nhất quán và đi kèm giám sát.

### Tại sao “tăng skew tới 24 giờ” là anti-pattern?

- Che giấu NTP sai hoặc parse thiếu timezone.
- Kéo dài khả năng sử dụng lại bearer assertions/tokens.
- Làm timestamp freshness không còn nhiều giá trị.
- Gây khác biệt chính sách giữa SP, API và IdP.
- Có thể phá quy tắc hết hạn ngắn của CAS ticket/anti-replay caches.
- Khi xóa nới skew sau này sẽ làm login hỏng hàng loạt.

Cách sửa gốc: **đồng bộ thời gian IdP/SP/API nodes**, phát timestamps đúng chuẩn timezone, sửa clock source và chỉ cho skew nhỏ phục vụ jitter/latency thật.

## 7. Spring Security SAML2: đặt clock skew đúng API và version

Tài liệu **Spring Security hiện hành** mô tả `OpenSaml5AuthenticationProvider.AssertionValidator` với builder `clockSkew(...)`. Đoạn sau là **Spring Security Servlet JavaConfig fragment**, cần dependencies SAML2, metadata IdP và `RelyingPartyRegistration` thật:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.authentication
        .OpenSaml5AuthenticationProvider;
import org.springframework.security.saml2.provider.service.authentication
        .OpenSaml5AuthenticationProvider.AssertionValidator;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlClockSkewSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        OpenSaml5AuthenticationProvider provider =
                new OpenSaml5AuthenticationProvider();

        AssertionValidator assertionValidator =
                AssertionValidator.builder()
                        .clockSkew(Duration.ofSeconds(60))
                        .build();
        provider.setAssertionValidator(assertionValidator);

        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .saml2Login(saml2 -> saml2
                        .authenticationManager(
                                new ProviderManager(provider)))
                .build();
    }
}
~~~

Lệnh import dài có thể được Java cho phép tách dòng quanh dấu chấm như ví dụ, nhưng **đây là fragment phụ thuộc Spring Security/OpenSAML version, không phải file tự chạy bằng javac thuần**. Cần thực thi integration tests trên resolved dependencies.

**60 giây chỉ là ví dụ chính sách**, không khẳng định là default cho mọi phiên bản SAML2. Tài liệu Spring cho minh họa một mức khác (10 phút); điều đó **không có nghĩa 10 phút là khuyến nghị production hoặc mặc định của provider**. Mức production nên lấy từ số liệu clock drift thật cộng một dư lượng nhỏ được security phê duyệt.

### Spring Security 6 so với 7

- Spring Security 5/6 có nhiều hướng dẫn dùng `OpenSaml4AuthenticationProvider`; API custom `assertionValidator`/clock skew có thể khác.
- Spring Security 7 dùng `OpenSaml5AuthenticationProvider` và builder `AssertionValidator` trong reference hiện tại.
- `RelyingPartyRegistration`, decryption/signing credentials, issuer/ACS/EntityID, IdP metadata vẫn phải đúng.
- Không copy API của version khác rồi giảm checks vì compile error.
- Khi thay custom assertion validator, phải **giữ validations mặc định cần thiết**; đừng implement một converter luôn trả success.
- Sau thay đổi, kiểm cả `NotBefore` và `NotOnOrAfter` của Conditions và SubjectConfirmationData bằng **signed fixtures** có boundary gần skew.
- Đừng coi lỗi `Destination`/`Audience`/`Signature` là “clock skew”; các lỗi đó cần sửa trust/metadata.

Nguồn: [Spring Security — Authenticating SAML2 Responses, Setting a Clock Skew](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html).

## 8. OAuth/OIDC/JWT: exp, nbf và iat không giống nhau

Một JWT claim set minh họa:

~~~json
{
  "iss": "https://login.example/realms/staff",
  "sub": "user-041",
  "aud": "reports-api",
  "iat": 1794020400,
  "nbf": 1794020400,
  "exp": 1794020700
}
~~~

**Đây là JSON claim subset không có chữ ký**, chỉ để mô tả cấu trúc. Các số NumericDate là số giây từ Unix epoch UTC, **không phải milliseconds**. Trong thực tế phải đọc claims từ JWT đã được Spring/JWT decoder verify, không dùng `Base64.getDecoder()` rồi tự cấp Authentication.

Theo **RFC 7519**:

- **`exp`:** thời điểm **bắt đầu không được chấp nhận**; validator cần thấy `now < exp` nếu không có leeway.
- **`nbf`:** token **chưa được chấp nhận** nếu `now < nbf`; tại đúng `nbf` có thể được chấp nhận.
- **`iat`:** token **được phát hành lúc nào**, dùng xác định tuổi token; **không tự là ngày hết hạn**. Việc reject `iat` tương lai/limit max age phải có validator/policy tương ứng, không giả định mọi Spring JWT decoder đều xử lý như `nbf`.
- **`auth_time`:** trong OIDC, là thời điểm **end-user authentication** tại IdP, khác `iat` của ID Token; liên quan `max_age`/fresh login/step-up.
- **`jti`:** ID có thể được dùng cho replay tracking khi có store/chính sách, không phải thời gian.
- **`aud`/`iss`/signature:** bắt buộc theo token/profile và resource server trust, **không bị thay thế bằng kiểm exp**.

RFC 7519 cho phép **một leeway nhỏ (thường không quá vài phút)** để bù clock skew cho `exp`/`nbf`. Không nên chọn skew rộng hơn TTL token. Đặc biệt: **expires at exp** là mốc **exclusive**, không phải đến hết một ngày nếu `exp` ghi đầu ngày.

### Rất dễ nhầm epoch seconds với milliseconds

~~~text
JWT NumericDate / unix seconds:
  1794020400

Java Instant.ofEpochSecond(...):
  đúng đơn vị nếu giá trị là seconds

Java Instant.ofEpochMilli(...):
  sẽ chỉ về một thời điểm rất khác nếu truyền 1794020400
~~~

Nếu timestamp bị lệch hàng chục năm, trước tiên kiểm **unit seconds/milliseconds**, không vội tăng clock skew.

## 9. Spring Security Resource Server: JwtTimestampValidator

Tài liệu Spring Security Resource Server cho biết:

- Decoder mặc định kiểm `iss` khi cấu hình `issuer-uri`.
- `JwtTimestampValidator` kiểm `exp` và `nbf`.
- Tài liệu hiện hành nêu **Resource Server mặc định dùng clock skew 60 giây**.
- Có thể tùy chỉnh bằng `new JwtTimestampValidator(Duration.ofSeconds(...))`.
- Việc thay validator cần **bảo toàn kiểm issuer** và những validators khác được policy yêu cầu, ví dụ audience/application token type.

Ví dụ **Spring project fragment** cho Resource Server Servlet (không chạy độc lập):

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public class JwtTimeValidationConfig {

    @Bean
    NimbusJwtDecoder jwtDecoder() {
        String issuer = "https://login.example/realms/staff";

        NimbusJwtDecoder decoder = (NimbusJwtDecoder)
                JwtDecoders.fromIssuerLocation(issuer);

        OAuth2TokenValidator<Jwt> timeAndIssuer =
                new DelegatingOAuth2TokenValidator<>(
                        new JwtTimestampValidator(
                                Duration.ofSeconds(60)),
                        new JwtIssuerValidator(issuer));

        decoder.setJwtValidator(timeAndIssuer);
        // Production: add required audience/token-purpose validators.
        return decoder;
    }
}
~~~

**Lưu ý:** code trên minh họa explicit timestamp + issuer validation đúng mẫu tài liệu, **chưa thêm audience/client-scope validator** và có thể không giữ đầy đủ các defaults nếu application đã có custom validators. Khi cấu hình production, bổ sung audience/token-type/scope checks theo resource server contract; không vô tình thay toàn bộ validation pipeline bằng chỉ một clock check.

Nguồn: [Spring Security — OAuth2 Resource Server JWT, Customizing Timestamp Validation](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).

### OIDC browser login khác JWT Resource Server

`oauth2Login()` xử lý client-side Authorization Code/OIDC authentication; `oauth2ResourceServer().jwt()` xử lý bearer Access Token của API. **Đừng sửa JwtTimestampValidator của API rồi kết luận OIDC ID Token login tại browser client đã có cùng skew**. Nimbus/ID Token validators và OAuth2 Client logic có thể khác; phải kiểm đúng luồng đang lỗi.

Trong OIDC Authorization Code flow còn có:
- `state` và authorization request **timeout** trong session/repository.
- `nonce` ràng buộc ID Token.
- Code expiry, redirect URI/PKCE verifier và một lần sử dụng ở token endpoint.
- IdP login session và user authentication freshness (`auth_time`/`max_age`).

Một request với `invalid_grant` có thể do **authorization code đã hết hạn hoặc dùng rồi**, redirect_uri sai, PKCE mismatch hoặc client auth fail — không được quy hết cho NTP.

## 10. CAS: ticket TTL và đồng hồ phía CAS Server

CAS classic SSO có `Service Ticket` dạng `ticket=ST-...` trên service callback rồi được `CasAuthenticationProvider`/ticket validator xác minh qua CAS server. Ticket thường có TTL ngắn và one-time-use, nhưng **không có cùng bộ thuộc tính NotBefore/NotOnOrAfter trong browser URL như SAML**.

Nếu CAS server từ chối service ticket:

1. Kiểm **service URL binding** có đúng không.
2. Kiểm ticket đã bị dùng một lần trước đó chưa.
3. Kiểm TTL và ticket registry/policy **đúng phiên bản CAS server**.
4. Kiểm clock sync giữa CAS nodes nếu registry/session distributed.
5. Kiểm proxy/browser redirect loops hoặc queue tạo thời gian trễ.
6. Kiểm network/TLS và nơi lưu logs.

**Không tự đặt “CAS ST luôn hết hạn sau N giây”** nếu chưa biết bản CAS và policy; timeout có thể cấu hình. Cũng không áp `JwtTimestampValidator` cho CAS ST, hoặc phát lại một ST đã validate nhằm “tránh expired”.

## 11. Session, cookie và TLS cũng có lỗi liên quan thời gian

Một login có thể fail dù SAML Assertion hợp lệ do một cơ chế khác:

| Tình huống | Tầng | Kiểm gì? |
| --- | --- | --- |
| SAML Assertion `NotOnOrAfter` vừa quá hạn | SAML provider | Conditions/SubjectConfirmationData, actual skew |
| JWT `exp` hết hạn | Resource Server | exp NumericDate, node clock, skew |
| ID Token login fail vì `iat`/`nonce`/`auth_time` | OIDC Client | Auth request correlation, issuer/session policy |
| CAS ST hết hạn | CAS server/registry | Ticket TTL, one-time use, queue delays |
| TLS certificate `NotBefore` tương lai | PKIX/TLS | Server/client cert validity, current node clock |
| Session timeout | Spring/IdP sessions | Last accessed/absolute TTL, session store, logout |
| Cookie `Expires`/`Max-Age` sai | Browser/client | Cookie attributes, browser clock/refresh behavior |
| CSRF token expired | Web session/form | Form lifetime và session/cookie policy |
| LoginState/RelayState không còn | Session/cache persistence | TTL của correlation store, wrong node, SameSite cookie |
| Secret/metadata rollover time | Key management | Cert rotation window/keys, không phải SAML Conditions |

**Ví dụ TLS:** JVM báo certificate `NotYetValidException` vì một node thực sự chậm 2 ngày. Nới SAML skew **không sửa TLS trust**. Ngược lại certificate hết hạn thật không được “giải quyết” bằng đặt hệ thống lùi giờ, vì điều đó tạo thêm lỗi federation và audit.

### Cookie Expires vs Max-Age

Browser có thể dùng thông tin thời gian server trong xử lý cookie expiry và có những điều chỉnh theo browser implementation. Không quy mọi `SameSite`/`Secure`/`HttpOnly` behavior cho NTP. Cookie bị chặn do cross-site SAML POST là vấn đề cookie policy, **không phải clock skew**.

## 12. NTP, chrony và đồng bộ thời gian trên Linux/Kubernetes

Trong production, **đồng hồ hệ thống phải được đồng bộ với nguồn thời gian đáng tin**, qua NTP hoặc dịch vụ quản lý thời gian của hạ tầng. Với Linux dùng `chrony`, kiểm:

~~~bash
# Chỉ đọc: trạng thái đồng bộ/timezone
date -u +"%Y-%m-%dT%H:%M:%SZ"
date +"%Y-%m-%d %H:%M:%S %Z %z"
timedatectl status

# Nếu cài chrony
chronyc tracking
chronyc sources -v
chronyc sourcestats -v

# Xem service đang chạy (tùy distro)
systemctl status chronyd
systemctl status chrony
~~~

**Các lệnh đọc trạng thái**; tên service có thể là `chronyd` hoặc `chrony` tùy distro, và `timedatectl` có thể không hoạt động trong container không chạy systemd. Nếu dùng cloud provider managed time service, xem dashboard/metrics tương ứng.

Chú ý các fields trong `chronyc tracking` như reference time, last offset, system time, RMS offset, root delay/root dispersion, leap status và update interval theo bản chrony. **Không lấy “local timezone GMT+7” làm bằng chứng server bị lệch 7 tiếng**.

### Kubernetes

~~~text
IdP pod A on node-01: current instant +0s
IdP pod B on node-02: current instant +95s
Spring pod C on node-03: current instant +2s

Consequence:
  tokens/assertions from pod B appear "issued in future"
  only for some login attempts
~~~

Container thường nhìn thấy system clock của host/kernel; `TZ` chỉ ảnh hưởng giờ hiển thị và API thời gian local. Trong một số runtime ảo hóa/time namespaces cấu hình đặc biệt hành vi có thể khác, nhưng mặc định **sửa NTP ở node/VM**, không phải chỉ đổi `TZ` trong pod.

Kiểm:
- Node đang chạy pod phát token/idp/session.
- Node đang chạy SP/API resource server từ chối.
- Clock sync status của **mọi nodes**, không chỉ một replica.
- Hypervisor/VM resume/suspend, snapshot, host drift, virtual time service, chrony/NTP conflict.
- NTP reachability, ACL/firewall, DNS, approved time sources.
- Nhiều daemon đồng bộ thời gian xung đột hoặc leap second handling.
- Clock jumps khi startup/VM migration, monotonic vs wall clock.

**Không sửa production clock bằng `date -s` tùy tiện**. Nên giao cho đội infra/time-sync xử lý, vì step thay đổi thời gian có thể ảnh hưởng database transactions, logs, cert validity, distributed locks và security sessions.

## 13. Chuẩn hóa timestamps trong logs để chẩn đoán được

Audit event tối thiểu nên gồm:

~~~text
timestamp_utc=2026-11-07T03:00:45.123Z
service=spring-sp
instance=sp-node-03
environment=prod
protocol=SAML2
registration_id=corp-idp
event=SAML_AUTHN_FAILURE
reason_code=ASSERTION_NOT_YET_VALID
correlation_id=nonsecret-opaque-id
observed_clock_offset_ms=+1800
validation_stage=ASSERTION_CONDITIONS
~~~

Đây là dữ liệu minh họa. Mỗi trường cần nguồn đo đáng tin:

- **`timestamp_utc`:** ghi ISO 8601 UTC với offset `Z` để các log từ hệ thống khác nhau so sánh được.
- **`instance`/`node`:** xác định pod/VM gây lỗi ngẫu nhiên.
- **`observed_clock_offset_ms`:** chỉ có khi có số đo từ NTP/monitoring; **không tự điền từ độ chênh giữa hai log timestamps** vì log delays khác nhau.
- **`validation_stage`:** phân biệt Conditions vs SubjectConfirmationData vs JWT Timestamp vs SSO session.
- **`reason_code`:** enum/error code do app mapping từ exception, không in raw credentials.
- **`correlation_id`:** ID riêng, không dùng `SAMLResponse`, CAS ticket, access token hay raw NameID.

Tránh log:
- Full `SAMLResponse`/Assertion XML, ID Token/JWT hoặc CAS ticket.
- Session cookie, Authorization header, SAML attributes/PII.
- Private keys và signed assertions.
- Raw query string chứa `code`, `state`, `ticket`.
- Detailed exception variables nếu chúng chứa XML/token.

Một SP ở UTC+07 vẫn có thể có log hiển thị `10:00+07:00`; nếu ingest sang SIEM parse đúng offset, đó chính là `03:00Z`. Chỉ khi SIEM **bỏ offset** rồi gắn timezone sai, dashboard mới có độ lệch 7 giờ.

## 14. Quan sát dấu vết khi một request thất bại

Không bắt đầu bằng “cho skew thêm 10 phút”. Lấy một **correlation ID** của sự kiện, rồi hỏi:

1. Ứng dụng nào từ chối? **IdP, Spring SP, Resource Server, CAS Server, gateway hay browser?**
2. Đó có phải lỗi **thời gian** hay lỗi issuer/signature/audience/recipient/session?
3. Timestamp trong log là **UTC Instant** hay local time? Offset được giữ hay đã mất?
4. IdP phát artifact lúc nào, SP/API kiểm lúc nào? Có **queue/redirect latency** bất thường không?
5. `NotBefore`/`NotOnOrAfter` thuộc Conditions hay SubjectConfirmationData? Bound nào hết hạn trước?
6. Có leeway chính thức bao nhiêu ở validator đang chạy? Default của **phiên bản thực tế** là gì?
7. Node IdP/SP/API nào phát và nhận request? NTP offset/root dispersion từng node?
8. Lỗi có trùng một node/pod hoặc ngay sau deploy/VM resume/clock step không?
9. Lỗi chỉ xảy ra sau browser idle, login page để lâu hoặc redirect loop?
10. Token/cookie/session có thực sự hết hạn theo TTL không?
11. Có ai sửa clock/timezone/JVM flags gần đây hoặc đổi time-zone rules không?
12. Có ai override default Spring security validator bằng custom implementation bỏ mất kiểm timestamp?

### Phân biệt latency với skew

Một Assertion có thời hạn 60 giây có thể hết hạn dù IdP/SP đồng hồ hoàn toàn khớp, nếu user bị giữ ở một intermediate consent page hoặc browser treo rồi mới POST. Mặt khác, lệch đồng hồ 90 giây gây failure ngay lập tức dù network latency chỉ 100 ms.

Không suy clock drift từ `(SP receive timestamp − IdP issue timestamp)` mà chưa trừ **network/processing latency** và hiểu timestamp semantics. Dùng NTP offset telemetry và tracing span timestamps để đối chiếu.

## 15. Các lỗi parse timezone trong Java/Spring

**Đúng:** dùng `Instant` cho mốc trên timeline, `OffsetDateTime` khi input có `Z`/`+07:00` và cần giữ original offset, `ZonedDateTime` cho hiển thị theo region, `Duration` cho khoảng cách.

**Sai thường gặp:**

~~~java
// Không làm để kiểm SAML/JWT absolute timestamps:
LocalDateTime source = LocalDateTime.parse("2026-11-07T10:00:00");
Instant guessed = source.atZone(ZoneId.systemDefault())
        .toInstant();
// Kết quả phụ thuộc cấu hình timezone của máy chạy.
~~~

Đây là ví dụ anti-pattern: chuỗi không có offset **không thể tự cung cấp absolute instant**. Nếu IdP gửi thời gian có offset chuẩn, giữ/parse offset; nếu một integration legacy gửi không offset, phải có **contract timezone rõ ràng** trước khi convert và xử lý DST ambiguity.

Ví dụ tốt:

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant utc = Instant.parse("2026-11-07T03:00:00Z");
Instant vn = OffsetDateTime
        .parse("2026-11-07T10:00:00+07:00")
        .toInstant();

boolean sameMoment = utc.equals(vn);
ZonedDateTime display =
        utc.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

`sameMoment == true`. `display` là thời gian địa phương của cùng `Instant`, không làm token có thêm thời gian sống.

### DST gây lỗi gì?

Ở các vùng như `Europe/Berlin`, một giờ trong ngày đổi sang giờ mùa hè có thể **không tồn tại** hoặc **xuất hiện hai lần**. `LocalDateTime.of(...)` không tự đủ để gắn đúng Instant cho những giờ này. Dùng `ZonedDateTime`, `ZoneId` và chính sách xác định khi ambiguous local time nếu thực sự cần calendar scheduling. **Federation token timestamps nên là UTC instants**, không dùng giờ địa phương không offset.

### JWT NumericDate là giây, không phải milliseconds

~~~java
Instant correct = Instant.ofEpochSecond(1794020400L);
// Sai nếu input NumericDate là giây:
Instant incorrect = Instant.ofEpochMilli(1794020400L);
~~~

Sai đơn vị có thể khiến token trông như hết hạn hàng chục năm hoặc chưa có hiệu lực. Các Spring JWT decoders thường chuyển `exp` thành `Instant`; không nên tự parse lại từ raw JSON khi có `Jwt.getExpiresAt()`.

## 16. Java 17 tự chạy: chẩn đoán UTC, clock skew và ranh giới

Mã dưới đây mô phỏng **cửa sổ [NotBefore, NotOnOrAfter)** ở tầng giáo dục. Nó dùng `Clock.fixed` để tests không phụ thuộc giờ hiện tại và `Clock.offset` để mô phỏng node chạy nhanh 45 giây. Mọi dữ liệu là synthetic, không tạo/verify SAMLResponse hoặc JWT thật. Trong production vẫn dùng **Spring Security/OpenSAML/Nimbus validator**.

Tạo file **`FederationClockDiagnosticsDemo.java`**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class FederationClockDiagnosticsDemo {

    // Model a half-open interval [NotBefore, NotOnOrAfter).
    // Only use this in education; real SAML/JWT validation does more.
    static boolean withinWindow(
            Clock clock,
            Instant notBefore,
            Instant notOnOrAfter,
            Duration skew) {

        if (skew.isNegative()
                || !notBefore.isBefore(notOnOrAfter)) {
            throw new IllegalArgumentException("Invalid time policy");
        }

        Instant now = clock.instant();
        return !now.plus(skew).isBefore(notBefore)
                && now.minus(skew).isBefore(notOnOrAfter);
    }

    public static void main(String[] args) {
        Instant base =
                Instant.parse("2026-11-07T03:00:00Z");

        Clock reference = Clock.fixed(base, ZoneOffset.UTC);
        Clock fastNode =
                Clock.offset(reference, Duration.ofSeconds(45));

        Instant fromVietnamOffset = OffsetDateTime.parse(
                "2026-11-07T10:00:00+07:00").toInstant();

        System.out.println("Same UTC instant: "
                + base.equals(fromVietnamOffset));

        System.out.println("Vietnam local: "
                + base.atZone(ZoneId.of("Asia/Ho_Chi_Minh")));

        Instant start = base.minusSeconds(60);
        Instant end = base.plusSeconds(30);

        System.out.println("Reference valid: "
                + withinWindow(reference, start, end,
                        Duration.ZERO));

        System.out.println("Fast node valid without skew: "
                + withinWindow(fastNode, start, end,
                        Duration.ZERO));

        System.out.println("Fast node valid with 30s skew: "
                + withinWindow(fastNode, start, end,
                        Duration.ofSeconds(30)));

        System.out.println("Exact expiry valid without skew: "
                + withinWindow(reference,
                        base.minusSeconds(60),
                        base, Duration.ZERO));

        System.out.println("Future NBF +25s allowed with 30s: "
                + withinWindow(reference, base.plusSeconds(25),
                        base.plusSeconds(90),
                        Duration.ofSeconds(30)));

        System.out.println("Future NBF +31s allowed with 30s: "
                + withinWindow(reference, base.plusSeconds(31),
                        base.plusSeconds(90),
                        Duration.ofSeconds(30)));

        System.out.println("Expired 20s allowed with 30s: "
                + withinWindow(reference, base.minusSeconds(90),
                        base.minusSeconds(20),
                        Duration.ofSeconds(30)));

        System.out.println("Expired 31s allowed with 30s: "
                + withinWindow(reference, base.minusSeconds(90),
                        base.minusSeconds(31),
                        Duration.ofSeconds(30)));

        System.out.println("Fast-node offset seconds: "
                + Duration.between(
                        reference.instant(),
                        fastNode.instant()).getSeconds());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac FederationClockDiagnosticsDemo.java
java FederationClockDiagnosticsDemo
~~~

**Stdout chính xác:**

~~~text
Same UTC instant: true
Vietnam local: 2026-11-07T10:00+07:00[Asia/Ho_Chi_Minh]
Reference valid: true
Fast node valid without skew: false
Fast node valid with 30s skew: true
Exact expiry valid without skew: false
Future NBF +25s allowed with 30s: true
Future NBF +31s allowed with 30s: false
Expired 20s allowed with 30s: true
Expired 31s allowed with 30s: false
Fast-node offset seconds: 45
~~~

### Giải thích từng kết quả

- **Same UTC instant: true:** `03:00Z` và `10:00+07:00` là cùng mốc thời gian.
- **Vietnam local:** Java `ZonedDateTime` dùng ID timezone `Asia/Ho_Chi_Minh` để hiển thị, không thay `Instant`.
- **Reference valid:** mốc hiện tại ở giữa khoảng `[now−60s, now+30s)`.
- **Fast node without skew: false:** node nhanh 45 giây vượt mốc end chỉ 30 giây trong tương lai.
- **Fast node with 30s skew: true:** validator dung sai 30 giây giúp hợp lệ trong mô hình; production vẫn cần sửa node clock.
- **Exact expiry without skew: false:** tại `NotOnOrAfter` hoặc JWT `exp` đã hết hạn.
- **Future NBF +25s:** có thể chấp nhận nếu policy cho skew30; **+31s** vượt tolerance.
- **Expired20s:** có thể chấp nhận với skew30; **31s** quá giới hạn.
- **Fast-node offset seconds: 45:** sai lệch mô phỏng giữa clocks, không phải đo NTP thực.

Code này **không** kiểm chữ ký, issuer, audience, recipient, InResponseTo, subject confirmation, replay, CAS ST hoặc PKIX certificate. **Không copy `withinWindow` vào production để thay JWT/SAML validator**. Hãy dùng nó làm bài tập suy luận giới hạn thời gian và tạo unit tests cho business policy *sau* khi protocol validation đã đúng.

## 17. Test deterministically với Clock.fixed và Clock.offset

**Đừng viết test kiểu sau**:

~~~java
// Anti-pattern: test chạy gần midnight hoặc dưới load sẽ flaky.
Instant now = Instant.now();
assertTrue(tokenExpiration.isAfter(now));
Thread.sleep(2000);
// Assertion may or may not expire due to environment/GC delays.
~~~

Thay bằng **Clock injection** cho code tự quản lý thời gian:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

// Fragment của test helper, không tự kiểm SAML:
Clock atStart = Clock.fixed(
        Instant.parse("2026-11-07T03:00:00Z"), ZoneOffset.UTC);

Clock thirtySecondsLater =
        Clock.offset(atStart, Duration.ofSeconds(30));
Clock oneMinuteEarlier =
        Clock.offset(atStart, Duration.ofMinutes(-1));
~~~

JUnit/MockMvc/provider integration cần thiết kế test fixtures cho signature, audience, correlation và timestamps. **Chỉ injection Clock vào business code không tự làm OpenSAML provider dùng clock đó**. Muốn kiểm provider skew thật, dùng API kiểm thử/version phù hợp, signed SAML test IdP có thời gian cố định hoặc test environment clock được kiểm soát an toàn; không thay `System.currentTimeMillis()` toàn hệ thống.

### Ma trận boundary có giá trị nhất

| Test | Input/time scenario | Expected |
| --- | --- | --- |
| T01 | SAML now 1ms trước NotBefore | Reject nếu skew 0 |
| T02 | SAML now đúng NotBefore | Conditions start acceptable |
| T03 | SAML now 1ms trước NotOnOrAfter | Conditions end acceptable |
| T04 | SAML now đúng NotOnOrAfter | Reject nếu skew 0 |
| T05 | SAML Conditions chưa hết, SubjectConfirmationData hết | Reject |
| T06 | IdP clock nhanh 30s, SP clock đúng | Kiểm leeway policy |
| T07 | SP clock nhanh 45s, leeway30s, window short | Kết quả theo binding/validator; không blanket accept |
| T08 | Signed Assertion bị chỉnh timestamp sau ký | Signature fail, test không chứng minh time validation |
| T09 | NotBefore sau NotOnOrAfter | Invalid conditions, reject |
| T10 | Missing times nhưng bearer confirmation invalid | Reject theo profile/policy |
| T11 | SAML IssueInstant tương lai xa | Response freshness/policy reject khi được enforce |
| T12 | Invalid Recipient/Audience với correct time | Reject |
| T13 | Duplicate/replayed Assertion ID với correct time | Replay policy reject |
| T14 | OIDC/JWT now == exp | Reject theo RFC semantics nếu no skew |
| T15 | JWT now == nbf | Valid theo time-boundary nếu còn hạn |
| T16 | JWT nbf future +25s và skew30 | Đánh giá trong tolerance |
| T17 | JWT exp past 31s và skew30 | Reject |
| T18 | JWT iat in future nhưng nbf/exp hợp lệ | Chỉ reject nếu có **iat policy** cụ thể |
| T19 | NumericDate seconds bị parse thành millis | Test phát hiện date rất sai |
| T20 | UTC Z vs +07 equivalent | Cùng Instant, kết quả giống nhau |
| T21 | IdP/SP pods khác node clock | Phát hiện intermittent failures |
| T22 | Clock synchronized, network delay quá TTL | Reject genuine expiry |
| T23 | Browser giữ login form quá lâu | State/correlation expiration riêng |
| T24 | Cookie blocked by SameSite on cross-site POST | Không chẩn đoán nhầm là clock skew |
| T25 | TLS cert not yet valid vì clock sai | Fail PKIX; sửa host clock/CA, không SAML skew |
| T26 | Leap second/DST transition/log local time | Logs canonicalize UTC, không double-count |
| T27 | CAS ticket already used | CAS deny replay; skew không hợp thức hóa |
| T28 | CAS ticket expired by policy | Deny, check actual CAS registry TTL |
| T29 | Multi-node time sync ổn nhưng khác validator config | Fix config drift, không chỉnh timezone |
| T30 | Negative skew configured | Reject invalid policy/config |

### Quan trọng về fixture timestamp và chữ ký

Nếu sửa `NotOnOrAfter` hoặc `IssueInstant` bên trong raw SAMLResponse đã ký, chữ ký không còn hợp lệ; test có thể fail signature trước time validation. Để test time boundary, **sinh lại Assertion bằng test IdP/OpenSAML signer** rồi ký lại bằng **lab private key**, hoặc dùng provider fixture builder được kiểm soát. Không lấy bất kỳ SAMLResponse production thật rồi chỉnh/log nó.

Với JWT, không được sửa `exp` trong payload sau khi ký rồi bảo đó là “expired token test” nếu muốn đi tới timestamp validator. Phải **phát lại JWT có signature hợp lệ** bằng test key và valid issuer/audience.

## 18. Quan sát đồng hồ trên nhiều node: so sánh đúng

Mẫu checklist node inventory:

~~~text
node-id   role            utc_now               ntp_offset    sync
idp-01    IdP             03:00:00.100Z         +1ms          yes
idp-02    IdP             03:01:30.000Z         +90s          no
sp-01     Spring SP       03:00:00.150Z         +2ms          yes
sp-02     Spring SP       03:00:00.170Z         +4ms          yes
api-01    Resource Server 03:00:00.160Z         +3ms          yes
~~~

Đây là **dữ liệu giả minh họa**; đồng hồ từng host được chụp ở những thời điểm khác nhau nên không thể suy offset từ cột utc_now nếu không có phép đo. Cột **ntp_offset** phải đến từ monitoring service được hiệu chuẩn; đơn vị cần thống nhất.

Nếu chỉ idp-02 lệch +90s, tokens issue từ node đó có thể có `nbf` hoặc `iat` tương lai so với SP và gây lỗi intermittent; tăng 120s skew có thể che lỗi, nhưng **sửa NTP idp-02** mới là hướng xử lý đúng.

### Monitoring đề xuất

- Node time sync status / stratum/reachability/chrony last offset/root dispersion.
- Absolute offset threshold và alert khi quá mức phù hợp risk.
- Time validation failures theo **provider / registration / SP instance / issuer / reason**.
- Histogram `NotBefore−SP now` và `SP now−NotOnOrAfter` từ **synthetic fixtures/anonymized metrics** khi có design phù hợp, không log raw Assertions.
- Request latency, queue duration, token exchange duration.
- Authentication failures sau NTP daemon restart, VM migration, clock step hoặc deployment.
- Configuration drift: tất cả SP nodes dùng cùng skew policy và version.
- Session/token age và revocation alerts.

**Không tự đẩy NameID/email, raw JWT/SAMLResponse hoặc CAS tickets vào metrics labels**, vì metrics cardinality/PII leak và tokens vẫn phải được bảo vệ.

## 19. Quy trình khắc phục theo lớp, không giảm kiểm tra bảo mật

### Bước 1 — Khoanh lỗi

Phân biệt **SAML assertion Conditions**, **bearer SubjectConfirmationData**, **OAuth/JWT timestamp**, **OIDC nonce/auth_time**, **CAS ticket TTL**, **TLS PKIX certificate validity** và **session timeout** qua error stage cụ thể.

### Bước 2 — Thu thập tối thiểu

Record correlation ID, trusted registrationId, node/pod ID, UTC event time, validation reason enum, config skew version và node NTP offset; không thu raw credentials.

### Bước 3 — Kiểm absolute time

Kiểm `date -u`/chrony trên IdP/SP/API nodes; so bằng `Instant`. Nếu timezone khác nhau nhưng cùng UTC Instant thì đó chỉ là hiển thị.

### Bước 4 — Đọc các time bounds thực

Dùng test fixture/hạ tầng kín để quan sát `NotBefore`/`NotOnOrAfter` trên Conditions, bearer SubjectConfirmationData, `IssueInstant`, `exp`/`nbf`/`iat`. Không trích nội dung thật ra logs công khai.

### Bước 5 — Kiểm latency và replay

Nếu clock đồng bộ nhưng quá hạn, kiểm TTL quá ngắn, redirect loops, browser idle, queue và duplicate reuse; không vội nới skew.

### Bước 6 — Đồng bộ hạ tầng

Sửa NTP/chrony/cloud time service và node drift qua infrastructure change control; không tự step system clock ở production khi chưa đánh giá phụ thuộc.

### Bước 7 — Điều chỉnh policy nhỏ nhất

Nếu clock drift thật chỉ vài giây, chọn allowance nhỏ, document owner, test both start/end boundaries, issuer/correlation/replay và theo dõi metrics. Không cho skew hàng giờ.

### Bước 8 — Khôi phục và hậu kiểm

Đảm bảo signing, audience, recipient, session/cookie và tenant policies vẫn hoạt động; test expired/replay tokens bị từ chối đúng. Bảo toàn incident data theo quy định và loại sensitive logs.

## 20. Runbook lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân có khả năng | Việc cần làm |
| --- | --- | --- |
| `NotBefore condition is not yet valid` | SP clock chậm, IdP clock nhanh, lệch parse UTC, leeway quá nhỏ | So UTC/NTP offsets, xem Conditions |
| `SubjectConfirmationData expired` | Browser delay, bound chặt hơn Conditions, SP clock nhanh | So subject end và latency, không chỉ Conditions |
| `Assertion expired` | Real TTL expired, SP clock nhanh, skew/config mismatch | Đo NTP và effective end bound |
| SAML signature invalid | Wrong IdP signing cert/XML tampering | Sửa trust/signature, **không tăng skew** |
| SAML audience mismatch | EntityID/registration sai | Sửa metadata/audience |
| SAML response valid trên pod A nhưng fail pod B | Time sync drift hoặc key/validation configs khác nhau | Kiểm node clocks và deployment drift |
| JWT `exp` expired | Token TTL, system clock, validator skew | So exp NumericDate và now |
| JWT `nbf` in future | AS fast/resource server slow, wrong epoch units | So Instant UTC |
| JWT `iat` unexpectedly future | Node time drift hoặc policy strict | Kiểm iat validator riêng, không suy từ exp |
| OIDC `invalid_grant` | Code expired/redeemed, PKCE mismatch, redirect URI | Phân loại token endpoint error trước khi đổ lỗi clock |
| OIDC login loop | Session/cookie/state issue, clock/timebound | Kiểm SameSite/correlation storage và token timing |
| CAS ST invalid | Ticket replay/expired/service mismatch | Kiểm CAS ticket validation + registry |
| TLS `NotYetValidException` | Cert date hoặc host clock sai | Kiểm PKIX/certificate/NTP |
| TLS `CertificateExpiredException` | Cert thật sự hết hạn hoặc host fast | Renew cert hoặc sửa time source |
| Log IdP 10:00, SP 03:00 cùng sự kiện | +07 offset vs UTC | Convert timestamps, không sửa clocks nếu Instant trùng |
| JWT exp như năm 1970 | Epoch seconds bị hiểu milliseconds | Đổi `ofEpochSecond` |
| Lỗi chỉ ngày DST | Parse LocalDateTime/ZoneId sai | Dùng ISO Instant/OffsetDateTime |
| Session expired nhanh ở một node | Session store/TTL/clock drift | Kiểm store semantics và node clock |
| Skew nới nhưng login vẫn fail | Signature/audience/recipient/replay/auth state | Quay lại xác định stage lỗi |

**Không log decoded token XML hoặc raw URLs để “nhìn rõ hơn”**. Use sanitized structured logs, test identities, approved secure tools và short-lived diagnostics.

## 21. Những anti-pattern nguy hiểm

### A — “Máy chạy UTC, người dùng ở Việt Nam nên lệch 7 giờ”

Sai. UTC 03:00 và Việt Nam 10:00 cùng `Instant`; lỗi chỉ xuất hiện khi parser bỏ offset/zone hoặc gắn nhầm. **Không nới skew 7 giờ**.

### B — “Tắt NotBefore/NotOnOrAfter cho login bớt lỗi”

Sai. Đây là các giới hạn replay/freshness quan trọng. Bỏ kiểm có thể chấp nhận bearer assertion quá hạn. Sửa clock/issuer/latency, không bỏ SAML conditions.

### C — “IssueInstant cộng 5 phút thay cho mọi time check”

Sai. Conditions và SubjectConfirmationData có mốc riêng; `InResponseTo`, recipient và audience cũng bắt buộc theo profile. Không tự chế validator đơn giản hóa.

### D — “JWT iat cũng là exp”

Sai. `iat` là thời điểm phát hành; `exp` là mốc hết hạn; `nbf` là mốc chưa có hiệu lực. Mỗi claim có semantics rõ trong RFC 7519.

### E — “Timezone JVM khác nghĩa đồng hồ node lệch”

Sai. `-Duser.timezone=UTC` có thể giúp log thống nhất nhưng **không sửa NTP offset thực**. Mức skew đo bằng đồng hồ nguồn đáng tin và UTC instants, không so strings local.

### F — “Skew 10 phút nên không cần đồng bộ NTP”

Sai. Skew làm rộng acceptance window và có thể che node time drift. Monitoring/NTP là cơ chế chính; leeway là dự phòng nhỏ.

### G — “Sửa XML/JWT đã ký để tạo test expired”

Sai. Chữ ký fail trước time validation. Phải sinh **fixture có chữ ký hợp lệ bằng test keys** rồi test boundary.

### H — “Truy cập CAS ticket lần hai để thử clock”

Sai. CAS ST thông thường one-time-use; lần hai bị từ chối do replay, không chứng minh clock lệch.

### I — “Token exp sau 5 phút nghĩa login session cũng hết hạn sau 5 phút”

Không nhất thiết. Access Token, ID Token, IdP SSO session, Spring session, CAS ticket và certificate lifetime là nhiều cơ chế độc lập. Cần lập bảng TTL thực.

### J — “Cho ID Token vẫn hợp lệ là được API access”

Sai. ID Token dành cho OIDC client; API Resource Server cần **Access Token đúng audience/scope**, không được bỏ qua phân biệt để chữa expiry.

## 22. Checklist QA khi bàn giao

- [ ] Phân biệt Instant UTC, offset, ZoneId, DST và clock drift.
- [ ] Logs canonicalize UTC ISO 8601 có `Z`/offset, không bỏ timezone khi ingest.
- [ ] SAML Conditions `NotBefore` inclusive/`NotOnOrAfter` exclusive đã test.
- [ ] Bearer SubjectConfirmationData có expiration/Recipient/InResponseTo riêng.
- [ ] `IssueInstant` không bị dùng thay condition expiry.
- [ ] Signature, issuer, audience, destination, recipient, correlation và replay vẫn được validate.
- [ ] IdP và SP resource server NTP/chrony telemetry được đo theo node.
- [ ] Không chỉ sửa timezone `TZ` để chữa NTP drift.
- [ ] Spring SAML OpenSAML version và `AssertionValidator.clockSkew` được kiểm đúng.
- [ ] Không chọn skew rộng dựa trên ví dụ tài liệu mà thiếu risk assessment.
- [ ] JWT Resource Server có `JwtTimestampValidator` kiểm `nbf`/`exp`.
- [ ] Jwt issuer và audience/scope validations vẫn giữ khi custom timestamp validator.
- [ ] OIDC browser login `state`/`nonce`/code timeout không bị nhầm với API JWT.
- [ ] CAS ticket TTL, replay và service binding được phân biệt SAML time conditions.
- [ ] TLS certificate validity, cookie/session TTL và IdP session time được phân biệt.
- [ ] Không lấy `LocalDateTime` thiếu offset làm absolute auth timestamp.
- [ ] JWT NumericDate parse bằng epoch seconds, không milliseconds.
- [ ] Java tests dùng `Clock.fixed`/`Clock.offset` khi kiểm business logic.
- [ ] Có signed/encrypted SAML fixtures và signed JWT fixtures cho time boundary tests.
- [ ] Có test at-start, at-end, +/−skew, invalid issuer/signature và replay.
- [ ] Kiểm pod A/B, IdP/SP/API nodes có configs/skew policy đồng nhất.
- [ ] Không log raw SAMLResponse, JWT, CAS ticket, cookie, secrets hoặc PII.
- [ ] Root cause là clock/latency/token TTL/formatter/validation được ghi rõ.
- [ ] Có monitoring, alert và incident/runbook cho time synchronization drift.
- [ ] Sau thay đổi vẫn từ chối assertions/tokens quá hạn thật, sai issuer và đã replay.

## 23. Tài liệu chính thức tham khảo

1. [Spring Security — Authenticating SAML2 Responses / Setting a Clock Skew](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `OpenSaml5AuthenticationProvider.AssertionValidator.builder().clockSkew(...)` và validator.
2. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SAML response processing, signature, decryption, assertion conditions và subject validation.
3. [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtTimestampValidator`, mặc định 60s và custom clock skew.
4. [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `exp`, `nbf`, `iat`, NumericDate và clock leeway.
5. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `auth_time`/`max_age`, ID Token, nonce, expiration/issuer.
6. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `Conditions`, `NotBefore`, `NotOnOrAfter`, `IssueInstant`, subject confirmation.
7. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO bearer SubjectConfirmationData và SP obligations.
8. [Oracle Java 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): `Clock.fixed`, `Clock.offset` và testable current time.
9. [Oracle Java 17 — java.time package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): `Instant`, `OffsetDateTime`, `LocalDateTime`/`ZonedDateTime`.
10. [Oracle Java 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): ISO instant/offset parsing.
11. [chrony Project — Documentation](https://chrony-project.org/documentation.html): `chronyc tracking`/`sources` và đồng bộ host time.
12. [Spring Security — CAS Authentication Filter Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): CAS service ticket callback/token validation.
13. [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signing, subject, validity, replay, SP validation.
14. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): tránh log credentials và PII khi debug.
15. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): authorization code binding, replay/expiry và modern OAuth security.

**Kết luận:** Phần lớn lỗi “SAML/JWT thời gian” chỉ giải được khi phân biệt **Instant thực**, **múi giờ hiển thị**, **TTL hết hạn thật**, **latency** và **clock skew giữa nodes**. SAML có nhiều giới hạn thời gian độc lập (Conditions, SubjectConfirmationData, IssueInstant), JWT có `nbf`/`exp`/`iat`, còn CAS ticket có registry TTL riêng. Spring Security hỗ trợ tùy chỉnh validator, nhưng **không có cấu hình nào thay thế NTP/chrony và validation đầy đủ**. Hãy đo offset trên từng IdP/SP/API node, chuẩn hóa UTC, dùng fixtures có chữ ký thật trong integration tests, chọn leeway nhỏ và bảo toàn những kiểm tra signature/audience/recipient/replay trước khi đánh dấu sự cố đã xử lý.