# Từ chối thông điệp SAML2 không hợp lệ mà không làm lộ assertion hoặc khóa

> **Chủ đề:** Spring Security – federation · **Nhóm:** Kiểm chứng SAML2. Bài học trình bày cách **từ chối an toàn** SAML Response/Assertion và các yêu cầu giao thức không hợp lệ trong ứng dụng Java/Spring Security đóng vai trò Service Provider (SP): xác minh đầy đủ, xử lý lỗi không tiết lộ dữ liệu, phân tách thông báo cho người dùng và nhật ký bảo mật, tránh ghi raw SAML vào log/APM/WAF, bảo vệ khóa ký/giải mã, và kiểm thử các đường lỗi ở nhiều lớp. Ví dụ tích hợp tập trung vào Spring Boot 3.x / Spring Security 6.x Servlet; mã Java thuần chạy với JDK 17+.

## 1. Mục tiêu và nguyên tắc chính

Sau bài này, bạn có thể:

1. Mô tả **điểm mà SP phải bác bỏ** một SAMLResponse không thỏa chữ ký, nguồn tin cậy, audience, recipient, điều kiện thời gian, state/correlation hoặc chống replay.
2. Phân biệt **xác thực SAML** với **hiển thị/thông báo lỗi**: một thông điệp bị từ chối không được sinh `Authentication` mới, trong khi phản hồi browser vẫn chỉ nên là thông báo chung.
3. Cấu hình `saml2Login(...).failureHandler(...)` để phản hồi lỗi xác thực mà **không đưa exception message, SAMLResponse, assertion hoặc khóa** vào response.
4. Thiết kế audit event an toàn: dùng **reason code theo allowlist**, correlation ID được sinh/kiểm soát, metadata đã xác minh; không ghi raw XML/Base64/cookie/RelayState hay principal PII.
5. Biết rằng failure handler **không bao phủ toàn bộ** lỗi trước filter, lỗi proxy/parser/size limit hoặc lỗi sau khi app khởi động; áp dụng phòng vệ nhiều lớp.
6. Viết test âm tính chứng minh cả hai tính chất: **request bị từ chối** và **không rò dữ liệu qua response, log, trace, metrics**.

### Câu trả lời ngắn cho bài toán

**Không phải:** “SAML invalid → throw exception với XML và certificate để dễ debug.”

**Mà là:** “SAML invalid → dừng authentication/fail closed → client nhận lỗi chung, không chứa dữ liệu nhạy cảm → audit nội bộ chỉ ghi code và correlation ID tối thiểu → bảo vệ raw payload/keys ở toàn bộ HTTP/exception/logging/telemetry pipeline.”

Bảo vệ dữ liệu không được làm mất khả năng vận hành: đội hỗ trợ vẫn cần phân biệt lỗi metadata, clock skew, correlation và chữ ký **ở kênh nội bộ được kiểm soát**. Nhưng không phải bằng cách đưa nguyên assertion, private key hoặc stack trace cho trình duyệt.

## 2. Mô hình tin cậy khi SP nhận SAMLResponse

### 2.1. Điểm nhận và ranh giới dữ liệu

Một ứng dụng Spring Security thực hiện SAML 2.0 Web Browser SSO theo luồng phổ biến:

```text
Browser                 SP / Spring Security                     IdP
   |                             |                                |
   | GET /saml2/authenticate/corp|                                |
   |---------------------------->|                                |
   |    tạo AuthnRequest, lưu ID/state                            |
   |<----------------------------| redirect/form tới IdP         |
   |                              \------------------------------>|
   |                              IdP xác thực user, ký Assertion |
   |<-------------------------------------------------------------|
   | POST /login/saml2/sso/corp (SAMLResponse)                    |
   |---------------------------->|                                |
   |   Saml2WebSsoAuthenticationFilter                             |
   |     -> AuthenticationConverter chọn registration/context     |
   |     -> OpenSAML provider parse/decrypt/verify                |
   |     -> issuer/signature/destination/audience/time/state      |
   |     -> quyết định Authentication success/failure             |
   |     -> nếu failure: generic response + safe audit only       |
   |<----------------------------|                                |
```

`SAMLResponse` do **browser vận chuyển**, vì vậy body POST đến ACS là **dữ liệu không đáng tin** cho tới khi provider xác minh. Một attacker có thể tự POST tùy ý tới ACS, thay `SAMLResponse`, `RelayState` hoặc path/headers. Chỉ vì trường `SAMLResponse` có nội dung Base64 hoặc XML parse được không có nghĩa nó đến từ IdP đáng tin.

Phân biệt dữ liệu ở ba tầng:

| Tầng | Có thể tin ngay? | Điều nên làm |
| --- | --- | --- |
| HTTP body/query, `SAMLResponse` Base64, `RelayState`, headers từ client | **Không** | Giới hạn kích thước, không log, kiểm tra định dạng ở component đúng |
| XML Response/Assertion sau decode/parse nhưng chưa validate | **Không** | Dùng provider/validator chuẩn; không lấy claims để tạo quyền hoặc ghi audit “user X” |
| `Saml2Authentication`/principal sau validation thành công | Có thể dùng theo phạm vi tin cậy đã cấu hình | Vẫn phải map tenant/roles và kiểm tra authorization nghiệp vụ |

**Base64 không phải mã hóa.** SAML Response có thể chứa `NameID`, email, nhóm, thuộc tính cá nhân, subject confirmation và dữ liệu có thể bị tái sử dụng trong thời gian ngắn. Nếu body được log, việc chỉ cất một chuỗi Base64 **không** bảo vệ quyền riêng tư hay loại bỏ nguy cơ replay.

### 2.2. Khóa nào nhạy cảm?

SAML có **nhiều vai trò khóa**:

- **IdP private signing key**: IdP dùng ký Response/Assertion; không bao giờ có trong cấu hình SP.
- **IdP public verification certificate**: SP giữ làm trust anchor để xác minh chữ ký IdP; certificate này có thể được **công bố trong metadata công khai của IdP**, vì bản thân nó không phải private key. Tuy vậy, không cần tiết lộ/echo certificate và trust path nội bộ trong lỗi login.
- **SP private signing key**: SP ký `AuthnRequest`, khi được cấu hình cần ký.
- **SP private decryption key**: SP giải mã `EncryptedAssertion`/`EncryptedAttribute`, khi giao thức sử dụng encryption.
- **SP public signing/decryption certificates**: có thể được công bố theo SP metadata/hợp đồng; không đồng nghĩa với việc được lộ private keys.

**Từ “không làm lộ khóa” chủ yếu là bảo vệ private keys, bí mật và cấu hình trust nhạy cảm.** Không nên gọi public certificate là secret; tuy nhiên failure response không phải nơi giải thích chi tiết certificate chain, key aliases, đường dẫn file secrets, fingerprint rollover hoặc tên HSM slot cho bất kỳ khách truy cập nào.

## 3. Điều kiện dẫn đến từ chối SAMLResponse hoặc Assertion

Một thông điệp cần bị từ chối nếu vi phạm **một điều kiện bảo mật bắt buộc**. Đừng dừng ở “XML signature valid” hoặc “IdP gửi về đúng hostname”.

| Lớp | Kiểm tra của SP | Ví dụ không hợp lệ | Phản ứng an toàn |
| --- | --- | --- | --- |
| Transport / input | Phương thức/path/binding đúng, Content-Type và kích thước hợp lý | POST sai endpoint, payload rỗng/quá lớn, form field thiếu | 4xx/generic failure theo lớp, không parse tùy tiện |
| Decode / XML parser | Base64 hợp lệ, XML well-formed, giới hạn entity/DTD/size/depth | Base64 lỗi, XML malformed, XML entity abuse | Reject, không log raw XML |
| Registration | Có `RelyingPartyRegistration` tin cậy đúng ngữ cảnh | Registration ID lạ/tenant khác | Reject hoặc lỗi chung, không tự tạo IdP từ payload |
| Signature/trust | Chữ ký bảo vệ **đúng dữ liệu dùng**, signing key thuộc IdP được trust | Không ký, ký sai, `KeyInfo` của attacker | Reject; không chuyển sang trust-on-first-use |
| `Issuer` | Response/assertion do IdP đã cấu hình phát | Issuer sai hoặc khớp chuỗi nhưng key không tin | Reject |
| `Destination` / `Recipient` | Response và bearer confirmation hướng đúng ACS | Gửi tới ACS khác hoặc HTTP host sai | Reject, rà public URL/proxy |
| `AudienceRestriction` | Assertion phát cho chính SP entityID | Assertion thuộc SP khác | Reject |
| Time conditions | `NotBefore`, `NotOnOrAfter`, SubjectConfirmationData, `IssueInstant` theo policy | Chưa hiệu lực, hết hạn, clock skew lớn | Reject; chỉ nới skew có kiểm soát |
| Request correlation | `InResponseTo` gắn AuthnRequest đã lưu, đúng registration/session | Request ID sai/đã mất/đã dùng | Reject theo SP-initiated policy |
| Anti-replay | IDs chưa được dùng, nếu policy yêu cầu dùng một lần | Gửi lại assertion/Response cũ | Reject atomic, kể cả nhiều pods |
| Assertion identity | Subject/NameID, confirmations và claims phù hợp | Assertion mơ hồ, subject khác phần đã ký | Reject/không dựng principal |
| SAML Status | Response báo không thành công | `Requester`, `Responder`, authentication canceled/failed | Không coi là authenticated |
| Application mapping | Claims map sang user/tenant/quyền đúng | Group bất hợp lệ, subject trùng tenant khác | Reject mapping hoặc không cấp quyền theo policy |

**Điều rất quan trọng:** invalid signature, wrong audience, expired assertion, replay, failure to decrypt và missing `InResponseTo` đều có thể là **nguyên nhân nội bộ khác nhau**, nhưng **client không cần nhận các chi tiết ấy**. Bên ngoài có thể cùng thông báo: “Không thể hoàn tất đăng nhập SSO. Vui lòng thử lại hoặc liên hệ hỗ trợ.”

### 3.1. Chữ ký hợp lệ với một khóa không đồng nghĩa nguồn đáng tin

Nếu SP tự lấy public key từ `ds:KeyInfo` do browser gửi rồi tin nó, attacker có thể ký XML bằng khóa của mình. SP phải xác minh chữ ký bằng certificate/key lấy từ **IdP registration đã được thẩm định**, kiểm tra issuer/tenant và chắc chắn object được dùng để tạo principal là object đã được chữ ký bảo vệ. Hành vi XML Signature Wrapping làm rõ vì sao chỉ nhìn một cờ “signature valid” chưa đủ.

Khi fail do signature, log an toàn có thể ghi `INVALID_SIGNATURE` nhưng không ghi XML signature value, `KeyInfo`, certificate PEM, private key, full XML canonicalization dump hoặc raw SAMLResponse.

### 3.2. Thời gian và replay

`NotOnOrAfter` có hiệu lực **loại trừ**: đến thời điểm đó là hết hạn. Clock skew (nếu cho phép) phải là policy được định nghĩa, không tùy ý cộng phút để “đăng nhập được”. Một assertion chưa hết hạn vẫn có thể bị **replay**, nên cần chống sử dụng lặp theo ID/state; đặc biệt trong multi-node, cache chống replay cần được chia sẻ và atomic theo thiết kế.

Một response hết hạn nên bị từ chối giống response sai chữ ký ở phía browser. Nội bộ chỉ cần mã `EXPIRED_ASSERTION` và một correlation ID; đừng trả cho browser timestamp chính xác, assertion ID hoặc toàn bộ Conditions XML.

### 3.3. Không nhầm lỗi xác thực với lỗi cấp quyền

- **Authentication failure:** chưa tạo danh tính được tin, vì SAMLResponse không hợp lệ; đi qua SAML authentication failure path.
- **Authorization denial:** user đã authenticated, nhưng thiếu permission cho endpoint/tenant/object; thông thường là 403/đường xử lý quyền của ứng dụng, **không phải** validation error SAML.
- **Infrastructure failure:** Redis/session store không truy cập được, HSM không hoạt động, IdP metadata chưa sẵn sàng; phải xử lý có kiểm soát và không tự nới validation để tạo login thành công.

Không biến `ROLE_USER` mặc định hay một claim `groups=admin` trong raw assertion thành quyền để “tránh lỗi đăng nhập”.

## 4. Nguyên tắc fail closed và hai kênh thông tin

Khi kiểm tra giao thức không đạt, hệ thống cần:

1. **Không tạo `Authentication` cho payload đó**, không lưu principal hoặc authorities từ claims chưa xác thực.
2. **Không bỏ qua validation** để tiếp tục luồng; không chọn signing certificate khác theo gợi ý từ raw XML.
3. **Không trả dữ liệu nhạy cảm** trong body/headers, redirect URL, HTML hidden fields, exception stack trace, flash attribute hay page-source comments.
4. **Ghi sự kiện có cấu trúc ở nội bộ** với code/định danh tối thiểu; để đội vận hành điều tra không cần sao chép SAML payload.
5. **Không cache** response lỗi chứa user data và không cho error endpoint thành open redirect.
6. **Cho user bước tiếp theo an toàn**: thử login lại qua link cố định hoặc liên hệ hỗ trợ với request reference ID được tạo nội bộ.

### 4.1. Dữ liệu hiển thị và dữ liệu nội bộ

| Thông tin | Trình duyệt/user | Audit nội bộ được kiểm soát |
| --- | --- | --- |
| Thông báo “Không thể hoàn tất đăng nhập SSO” | **Có** | Không bắt buộc |
| Support correlation ID ngẫu nhiên, không chứa danh tính | Có thể có | Có |
| Lỗi nhóm `INVALID_SIGNATURE`, `WRONG_AUDIENCE`, `SAML_EXPIRED` | **Không** | Có, theo allowlist |
| Issuer IdP sau khi đã xác minh hoặc registration ID tin cậy | Không | Có nếu thật sự cần |
| Raw `SAMLResponse`/assertion XML/Base64 | **Không** | **Không log** |
| `NameID`/email/groups/PII | Không hiển thị trong error | Chỉ khi có căn cứ nghiệp vụ và bảo vệ riêng, mặc định **không** |
| Signature values, `KeyInfo` XML, session cookie, RelayState bí mật | Không | Không log raw |
| SP/IdP private keys hoặc decryption secrets | **Tuyệt đối không** | **Tuyệt đối không** |
| Stack trace/`exception.getMessage()`/nested causes | Không | Tránh log trực tiếp trên path có input SAML; sử dụng code/metrics có kiểm soát |
| Node ID, thời gian, route template, validator stage | Không cần | Có thể có, sau normalization |

### 4.2. Vì sao `exception.getMessage()` không an toàn?

Không thể dựa vào một giả định rằng message của mọi thư viện luôn “sạch”. Tùy phiên bản validator, parser, servlet container hoặc exception wrapper, message/cause có thể chứa XML fragment, cấu trúc signing cert, path chứa secret, giá trị claim, URI hoặc dữ liệu attacker cung cấp.

Do đó các anti-pattern sau cần tránh:

```java
// KHÔNG dùng trong production SAML failure handling.
logger.error("SAML failed, response={}, error={}",
        request.getParameter("SAMLResponse"), exception);
response.getWriter().write(exception.getMessage());
```

Đoạn code thể hiện **hành vi sai** để nhận diện trong review; không phải giải pháp được khuyến nghị. Bất kỳ statement nào serialize exception với full stack trace cũng cần xem xét vì chain có thể chứa dữ liệu nhạy cảm. Nếu cần root-cause chi tiết để sửa bug, dùng môi trường test/fixture không có PII, protected debug channel và quy trình cấp quyền hạn chế; không bật raw payload logging trên production đại trà.

### 4.3. Same external response nhưng đủ khả năng hỗ trợ

Ví dụ user-facing:

```text
Không thể hoàn tất đăng nhập SSO.
Vui lòng thử lại. Nếu lỗi tiếp diễn, liên hệ bộ phận hỗ trợ
và cung cấp mã yêu cầu hiển thị trên trang.
```

Nếu đưa **mã yêu cầu** ra browser, hãy tạo UUID/opaque ID độc lập với SAML content. Audit nội bộ dùng cùng ID để liên kết. Đừng biến mã yêu cầu thành phiên đăng nhập, secret cho phép truy xuất XML hay một API công khai trả về chi tiết lỗi.

Để tránh tạo thêm login oracle, không trả thông báo đặc biệt “email X không tồn tại”, “IdP ký bằng certificate alias K” hoặc “assertion cho tenant Z” cho bên ngoài. HTTP status có thể khác nhau theo các lớp edge/proxy, nhưng ứng dụng nên giữ lỗi validation SAML đồng nhất về **body và độ chi tiết**.

## 5. Nơi Spring Security xác thực và xử lý thất bại

### 5.1. Những lớp cần phân biệt

| Thành phần | Trách nhiệm |
| --- | --- |
| `Saml2WebSsoAuthenticationRequestFilter` | Tạo/đưa `AuthnRequest` sang IdP; không kiểm tra SAMLResponse |
| `Saml2WebSsoAuthenticationFilter` | Nhận POST `SAMLResponse` tại ACS, chạy authentication flow |
| `Saml2AuthenticationTokenConverter` | Trích response, xác định registration/context từ request hoặc state |
| `RelyingPartyRegistrationRepository` | Cung cấp IdP trust, SP entityID/ACS/credentials hợp lệ |
| `OpenSaml4AuthenticationProvider` / `OpenSaml5AuthenticationProvider` | Dựa trên version OpenSAML/Spring Security để parse/decrypt/validate SAML |
| `AuthenticationManager` | Điều phối authentication, trả kết quả/exception |
| `AuthenticationFailureHandler` | Chọn cách trả lời cho **authentication failures mà authentication filter đã bắt và chuyển tới handler** |
| `AuthenticationEventPublisher` / observability | Có thể phát sự kiện failure; phải hạn chế thông tin payload khi ghi log/metrics |
| `ExceptionTranslationFilter` | Chuyển một số exception liên quan xác thực/ủy quyền trong filter chain sang entry point/access denied handling |
| Edge/proxy/servlet error handling | Xử lý lỗi trước hoặc ngoài SAML authentication filter, ví dụ quá lớn/sai HTTP method |

**Lưu ý phiên bản:** Spring Security 6.5 có thể dùng OpenSAML 4 hoặc 5 tùy dependency, và 7.x dùng OpenSAML 5 trong tài liệu hiện hành. Không hardcode một loại provider trong mọi phiên bản; giữ validation mặc định và kiểm tra release đang sử dụng.

### 5.2. AuthenticationFailureHandler không phải lớp bắt mọi lỗi

Một `AuthenticationFailureHandler` ở `saml2Login` xử lý các `AuthenticationException` đi qua SAML authentication processing filter. Nhưng nó **không chắc chắn** chạy đối với:

- HTTP body vượt giới hạn và bị ingress/Tomcat/WAF chặn trước app.
- Exception ở request size limiter, servlet filter đặt trước SAML filter, hoặc một route bị cấu hình sai.
- Sai cấu hình lúc ứng dụng start, private key file không đọc được, lỗi metadata dependency trước khi flow được dựng.
- SAML logout request/response nếu ứng dụng triển khai SLO; SLO có filters và failure handling riêng.
- Exception ngoài authentication processing, ví dụ lỗi ở custom filter/logger/trace collector sau đó.

Cần error handling nhiều lớp: edge 400/413/429/503 chung, servlet/container error mapping không stack trace, SAML failure handler cho authentication failures, và cơ chế alert nội bộ cho infrastructure incidents. Không để Spring Boot error page mặc định trong một môi trường cấu hình debug phơi exception/trace ra browser.

### 5.3. Không can thiệp validator chỉ để làm đẹp lỗi

Có thể tùy biến response/assertion validator bằng extension của OpenSAML provider, nhưng phải **kết hợp** với validation mặc định chứ không thay bằng code chỉ kiểm tra issuer hoặc có chữ ký. Khi cần thay thông báo lỗi, trước tiên hãy dùng failure handler, log policy và mapping error codes; đừng vô hiệu chữ ký, audience, replay hoặc `InResponseTo` để tránh một exception.

## 6. Cấu hình Spring Security 6.x: trả lỗi chung khi SAML login thất bại

### 6.1. SecurityFilterChain với failure handler rõ ràng

Ví dụ source-level cho Spring Boot 3.x / Spring Security 6.x Servlet; có thể sử dụng `saml2Login(saml -> saml.failureHandler(...))`. Để giảm nguy cơ lộ chi tiết, handler **không đọc `SAMLResponse` và không serialize exception**.

Tạo `SamlFailureSecurityConfig.java`:

```java
import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

@Configuration
public class SamlFailureSecurityConfig {

    private static final Logger LOG =
            LoggerFactory.getLogger(SamlFailureSecurityConfig.class);

    @Bean
    AuthenticationFailureHandler samlFailureHandler() {
        return (request, response, exception) -> {
            String eventId = UUID.randomUUID().toString();

            // Không ghi exception, SAMLResponse, RelayState hoặc cookies.
            LOG.warn("event=saml_auth_rejected event_id={} result=DENIED",
                    eventId);

            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding("UTF-8");
            response.setContentType(MediaType.TEXT_PLAIN_VALUE);
            response.setHeader("Cache-Control", "no-store");
            response.setHeader("Pragma", "no-cache");
            response.setHeader("Referrer-Policy", "no-referrer");
            response.getWriter().write(
                    "Không thể hoàn tất đăng nhập SSO. "
                  + "Vui lòng thử lại hoặc liên hệ hỗ trợ. "
                  + "Mã tham chiếu: " + eventId);
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationFailureHandler samlFailureHandler) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .failureHandler(samlFailureHandler));

        return http.build();
    }
}
```

**Giải thích giới hạn và hành vi:**

- Đây là **class cấu hình Spring**, không phải chương trình Java độc lập chạy `javac`. Ứng dụng còn cần `spring-security-saml2-service-provider`, một `RelyingPartyRegistrationRepository`/IdP được cấu hình và runtime Servlet.
- Mỗi failure được cấp một `eventId` ngẫu nhiên để hỗ trợ đối chiếu; mã đó **không dựa trên assertion ID hoặc `NameID`**. Chỉ trao event ID cho người dùng, không trao chi tiết verification nội bộ.
- LOG chỉ có event type, ID và kết quả. Không có `exception` trong tham số logger: SLF4J có thể log stack trace khi Throwable được truyền vào, nên cố ý **không** đưa vào.
- `response.setStatus(401)` là lựa chọn minh họa cho ứng dụng trả response plain text. Tùy UX/IdP/browser, ứng dụng có thể dùng redirect đến một trang lỗi tĩnh; không có một HTTP status bắt buộc duy nhất cho mọi SAML login failure.
- `Cache-Control: no-store` giảm khả năng cache response lỗi có mã tham chiếu. `Referrer-Policy: no-referrer` giảm truyền thông tin trong referer của trang lỗi, nhưng không thay chính sách log/body.
- Spring Security sẽ xử lý authentication failure theo cơ chế filter; handler này **không** tự xóa toàn bộ mọi HttpSession cũ hoặc revoke các phiên khác. Nếu có yêu cầu session revocation riêng, phải xác định policy rõ để tránh vô tình logout user từ một POST lỗi do attacker gửi.
- Với site thực, có thể trả trang lỗi tĩnh, i18n, hoặc redirect nội bộ bằng URL cố định. Không echo `exception.getMessage()` hoặc tham số `returnUrl` thành redirect target.
- Để tránh vòng lặp login, trang lỗi nếu là endpoint riêng như `GET /sso/error` phải được `permitAll()`, không kích hoạt SAML login một lần nữa.

**Điều kiện tiên quyết:** Filter chain phải match ACS `/login/saml2/sso/{registrationId}`. Nếu ứng dụng có nhiều `SecurityFilterChain`, hãy đảm bảo callback đi vào chain chứa `saml2Login`. Nếu IdP response bị proxy chặn trước filter, handler không chạy; phải có generic error mapping tại ingress.

### 6.2. Biến thể chuyển sang trang lỗi tĩnh

Nếu browser cần UI thay vì hiển thị text trên ACS POST, có thể dùng:

```java
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

// Fragment cho cấu hình saml2Login, khi /sso/error là GET public:
SimpleUrlAuthenticationFailureHandler handler =
        new SimpleUrlAuthenticationFailureHandler("/sso/error");

// http.saml2Login(saml -> saml.failureHandler(handler));
```

Đây là **fragment**, không phải class runnable độc lập. Trang `/sso/error` chỉ hiển thị thông báo chung, nút thử lại dẫn tới URL khởi tạo login đã cho phép, không chứa exception, assertion, certificate hay một `next` URL tùy ý. Kiểm tra handler/framework có lưu exception trong session hoặc request attribute cho UI theo cách bạn không mong muốn; trang lỗi không được truy xuất/hiển thị nội dung đó. Nếu chọn cách này thay vì failure handler ghi audit, cần instrument audit riêng không làm rò Throwable.

### 6.3. Nếu muốn phân loại reason code

Phân loại lỗi nội bộ tốt nhất tại **validator/integration boundary đã kiểm tra an toàn**, bằng enum cố định. Ví dụ:

```text
INVALID_FORMAT
UNTRUSTED_ISSUER
INVALID_SIGNATURE
WRONG_AUDIENCE
WRONG_RECIPIENT
EXPIRED_ASSERTION
REQUEST_CORRELATION_FAILED
REPLAY_DETECTED
DECRYPTION_FAILED
INTERNAL_AUTHENTICATION_ERROR
```

Không cố phân loại bằng:

```java
// Anti-pattern: đừng lấy exception message làm reason code.
String reason = exception.getMessage();
LOG.error("reason=" + reason);
```

Đoạn trên không an toàn vì exception message có thể chứa dữ liệu từ payload. Nếu chỉ có một generic authentication exception mà chưa biết lý do chính xác, ghi `AUTHENTICATION_REJECTED` là tốt hơn đoán từ văn bản exception. Để có reason code sâu hơn, dùng event từ các lớp validator đã có telemetry an toàn, rồi chuẩn hóa thành enum; không tự log raw SAML.

## 7. Quan sát vận hành an toàn: log ít nhưng hữu ích

### 7.1. Mẫu audit event

```json
{
  "event": "saml_auth_rejected",
  "event_id": "b8aee5d2-0d66-4749-98b5-81563f1b2008",
  "reason_code": "INVALID_SIGNATURE",
  "registration": "corp",
  "node": "pod-b",
  "result": "DENIED",
  "timestamp": "2026-11-07T03:00:00Z"
}
```

Đây là **mẫu JSON giả lập**, không phải log sinh ra từ code `SamlFailureSecurityConfig` (code ở trên chỉ log event/result/ID, chưa có validator reason_code). Chỉ điền `registration` khi đã kiểm soát hoặc đối chiếu allowlist: một raw `registrationId` trong path hay `Issuer` trong XML chưa xác minh là đầu vào của attacker. `timestamp` dùng giờ hệ thống, không lấy `IssueInstant` từ response chưa tin làm thời gian event.

Tùy tình huống, có thể bổ sung:

- `correlation_id` do ingress/service sinh, khác secret RelayState; đồng nhất xuyên node nhưng không chứa raw SAML.
- Code stage `DECODE`, `TRUST`, `CONDITIONS`, `CORRELATION` (danh mục cố định), latency và response HTTP class.
- Mã hóa danh IdP registration đã duyệt (không lưu chuỗi Issuer chưa tin nếu không có nhu cầu).
- Node/cluster/region đã biết, version của IdP integration, key rollover phase dưới dạng flag không nhạy cảm.
- Đếm số sự kiện theo reason code cho phát hiện incident, không gắn email/NameID làm nhãn metrics.

### 7.2. Nguồn có thể rò dữ liệu dù code handler không log

| Thành phần | Rủi ro | Biện pháp |
| --- | --- | --- |
| Servlet logging filter, ví dụ `CommonsRequestLoggingFilter` cấu hình capture body | Ghi `SAMLResponse`/cookies vào access/debug log | Không bật includePayload cho ACS; redact field nhạy cảm |
| Reverse proxy/ingress access logs | Ghi request body, URL Redirect có `SAMLRequest`/RelayState | Tắt body logging cho SSO, tránh raw query strings nếu chứa state |
| WAF/IDS request capture | Lưu nguyên payload bị nghi ngờ | Thiết lập redaction/exclusion có kiểm soát cho ACS |
| APM/OTel tracing | Tự động thu request body/form field/exception attributes | Loại bỏ `SAMLResponse`, `SAMLRequest`, Cookie, Authorization và raw exception |
| Error monitoring (Sentry/…) | Đính kèm HTTP body, headers, request params hoặc exception locals | Cấu hình scrubbing/before-send, test bằng canary dữ liệu giả |
| Framework debug log/OpenSAML | In XML, signature, input bytes khi log level quá chi tiết | Giới hạn logger levels ở production, dùng test fixture để debug |
| Application logger | `log.error("SAML", exception)` serialize message + cause | Chỉ ghi event/reason allowlist; bảo vệ debug riêng |
| Error page/JSON response | `exception.getMessage()`, stack trace, nguyên SAML code | Generic response, xử lý mapping toàn ứng dụng |
| Redirect URL/`Location` | Query chứa `RelayState`, key path, assertion ID, raw errors | URL cố định hoặc opaque event ID, allowlist return target |
| Metrics labels | `NameID`/Issuer string/Exception text làm label | Chỉ tag low-cardinality từ allowlist |
| Support ticket/screenshot | User/dev copy URL, SAML body, PEM | Hướng dẫn gửi event ID, che thông tin nhạy cảm |
| Redis/session dump | Pending request hoặc SAML state chưa được phân loại dữ liệu | ACL, encryption, TTL, không dump vào debug không kiểm soát |
| CI/CD, startup diagnostics | Private keys trong env vars/config print, debug mount | Secret manager, quyền file, redact, không commit |

**Quan trọng:** Một log an toàn tại `AuthenticationFailureHandler` không bù được ingress/WAF/APM đang capture body trước handler. Cần kiểm kê **từ browser tới SP và từ SP tới toàn bộ telemetry backend**.

### 7.3. Redaction: không tin regex đơn độc

Các dấu hiệu cần che:

```text
SAMLResponse
SAMLRequest
RelayState (nếu chứa opaque secret/state có thể dùng lại)
Cookie / Set-Cookie
Authorization
NameID, assertion XML, AttributeValue chứa PII
ds:SignatureValue / KeyInfo XML
private-key PEM blocks, credentials, decryption keys
```

Một regex tìm `SAMLResponse=...` có thể bỏ sót:

- Body dùng multipart/encoding khác, form URL-encoded, key viết hoa/thường khác.
- Giá trị Base64 bị xuống dòng, có nhiều tham số cùng tên hoặc được encode hai lần.
- XML được capture sau decode chứ không còn tên `SAMLResponse`.
- Exception message chứa từng đoạn assertion hoặc PEM không có tên field.
- Trace middleware log object Java, JSON serialization của exception, hoặc một span attribute bất ngờ.

**Tư duy an toàn hơn:** **không thu thập body/query credential từ đầu** (allowlist fields log), sau đó áp dụng masking/scrubbing thứ cấp và kiểm thử bằng canary. Redaction theo blacklist là lớp bổ sung, không phải cơ chế duy nhất.

### 7.4. Sanitize dữ liệu không đáng tin trước khi log

Attacker có thể cố đưa newline/control characters vào `Issuer`, `RelayState` hoặc field khác để gây **log injection**, giả mạo một dòng sự kiện “LOGIN_SUCCESS”. Nếu log chuỗi do người dùng nhập, cần giới hạn độ dài, escape control chars, JSON structured encoding và allowlist. Tốt nhất dùng registration ID lấy từ config sau validation chứ không dùng raw XML issuer.

Không dùng arbitrary exception message làm dynamic metric label vì vừa rò thông tin vừa gây **cardinality explosion** trong hệ thống metrics.

## 8. Bảo vệ khóa và certificate trong xử lý lỗi

### 8.1. Chữ ký và trust anchor

SAML Response/Assertion được IdP ký bằng private key. SP xác minh chữ ký bằng **IdP public signing key/certificate từ `RelyingPartyRegistration` đã tin cậy**, không phải bất kỳ certificate nào nằm trong XML `ds:KeyInfo`.

Một certificate công khai trong SP/IdP metadata không phải secret, nhưng cần quản trị trust và rotation nghiêm ngặt. Nếu IdP public cert thay mà SP chưa cập nhật, người dùng có thể gặp SAML signature failure. Phản ứng đúng là thông báo lỗi chung và mở sự kiện vận hành về rollover; **không** gửi certificate nội bộ/PEM tới user, cũng không bỏ signature verification để cho login tiếp tục.

### 8.2. Key material tuyệt đối không đi vào phản hồi

Các nội dung không bao giờ xuất hiện trong response/log:

- `-----BEGIN PRIVATE KEY-----`, PEM PKCS#8, JWK private parameters, HSM credentials, key store password.
- Password mở keystore, giá trị environment secret, cloud key management token.
- `Saml2X509Credential` hoặc object credential dump chứa private key.
- Debug stack trace có địa chỉ secret mount kèm thông tin nhạy cảm; file path có thể không phải secret nhưng vẫn không nên công khai qua login error.

Không đặt private keys vào YAML source control. Nên dùng secret store, key rotation và quyền đọc tối thiểu. Nếu một giá trị bí mật đã bị log, cần xử lý như **credential exposure incident**, không chỉ xóa một dòng log: kiểm tra backups/trace pipeline, thu hồi/đổi khóa, rà session và quyền.

### 8.3. Decryption errors

Nếu `EncryptedAssertion`/`EncryptedAttribute` không giải mã được bằng private decryption key đúng, **không** tiếp tục lấy plaintext từ nơi khác hoặc bỏ validation. Ghi một code `DECRYPTION_FAILED` ở audit nội bộ, client thấy thông báo chung. Tránh log cipher text, decrypted attributes, key handles, IV hoặc toàn bộ chain exception của thư viện crypto.

Một thay đổi thứ tự decryption và signature validation có thể phá XML signature hoặc ràng buộc bảo mật. Khi tùy biến OpenSAML provider, cần hiểu signature coverage và các extension của version, dùng tài liệu chính thức để đảm bảo không đọc unverified assertions.

### 8.4. Public certificate không đồng nghĩa “cho phép debug công khai”

Một số SP công bố SP public certificate trong SAML metadata vì IdP cần xác minh signed AuthnRequest. Điều đó **không** có nghĩa thông báo lỗi login nên liệt kê toàn bộ IdP signing certs, SHA fingerprints, alias keystore và key rollover schedule. Error page là mặt phẳng giao tiếp với client chưa tin; hạn chế tiết lộ chi tiết cấu hình có thể giúp attacker nhận diện môi trường.

## 9. Các đường lỗi không đi qua SAML authentication failure handler

### 9.1. Proxy, servlet container và request size

Một attacker có thể gửi `SAMLResponse` quá lớn để gây DoS hoặc kích hoạt logging của reverse proxy. Giới hạn HTTP request body, form parameters, XML parser depth/entity expansion và thời gian xử lý **trước** khi nội dung đến validator.

Ví dụ mức giới hạn phải tính theo kích thước assertion/attributes thật, có margin cho Base64/encoding; không chép một con số bất kỳ thành production standard. Khi vượt giới hạn, ingress/servlet trả lỗi chung (ví dụ 413) và không echo payload. Failure handler `saml2Login` có thể không chạy vì request đã bị chặn từ trước.

### 9.2. Base64 / XML parsing failures

Một `SAMLResponse` có field rỗng, ký tự không hợp lệ hoặc XML malformed phải được từ chối. Parser phải cấm/giới hạn external entities, DTD/XXE, entity expansion và schema fetching ngoài ý muốn theo cấu hình thư viện. Tránh tự parse raw SAML XML bằng regex/XPath riêng để lấy `NameID`, rồi chỉ nhờ provider kiểm tra chữ ký của một element khác.

DoS controls: giới hạn compressed/expanded sizes, số attributes/assertions, thời gian parse và concurrency. Cần test dữ liệu bất thường với fixture an toàn, không sử dụng payload production trong bug report.

### 9.3. Application/host error page

Spring Boot có cơ chế error handling riêng. Nếu môi trường staging bật stacktrace/exception details trong error payload, một lỗi trước/ngoài SAML filter có thể vô tình trả XML hoặc đường dẫn secret. Tại production, giữ error page generic, tắt hiển thị stack trace/exception messages, không đính kèm request body.

Ví dụ thuộc tính **hướng dẫn, cần đối chiếu phiên bản Spring Boot**:

```yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-exception: false
```

Các thuộc tính này hỗ trợ giảm phơi lỗi mặc định của Boot; **không** tự quản lý response do custom controller, proxy, servlet filter hoặc logger khác tạo. Kiểm tra output thực tế qua các lỗi âm tính.

### 9.4. Error processing khác SAML Logout

`Saml2LogoutRequestFilter` và `Saml2LogoutResponseFilter` phục vụ Single Logout (SLO) và có callback/signature/policy riêng. Một failure handler chỉ gắn ở `saml2Login` không bao quát hết SAML Logout. Nếu hệ thống bật SLO, phải áp dụng cùng nguyên tắc không lộ payload/keys ở các error paths tương ứng.

## 10. Thiết kế phản hồi lỗi: API và trình duyệt

### 10.1. Khi người dùng đăng nhập qua browser

Có thể dùng status 401 kèm text/page lỗi chung hoặc redirect cố định tới `/sso/error`. Một redirect an toàn phải có:

- URL nội bộ cố định/được allowlist, không lấy từ `RelayState`/`returnUrl` chưa kiểm tra.
- Trang lỗi được phép truy cập anonymous; nếu bảo vệ bằng SSO sẽ tạo loop.
- Không cho phép HTML response phản chiếu untrusted `Issuer`, `NameID`, `statusMessage`, exception text.
- Không lưu raw SAMLResponse trong flash/session chỉ để render thông báo.
- `Cache-Control: no-store` và security headers phù hợp.

Nếu error page có nút “Thử lại”, nó trỏ về URL khởi tạo SSO chuẩn, ví dụ `/saml2/authenticate/corp` cho một registration đã cho phép, không tự dùng raw SAMLResponse cũ.

### 10.2. Khi backend API dùng SAML session

API business dựa vào `HttpSession` sau SSO có thể trả 401 khi unauthenticated hoặc 403 khi insufficient authority. Nhưng **callback ACS vẫn là SAML browser protocol**, không biến raw `SAMLResponse` thành JSON error cho frontend. Phải bảo vệ CSRF state-changing endpoints, session fixation, cookie `Secure`/`HttpOnly`/`SameSite` theo flow; không disable CSRF toàn app để tránh POST ACS fail.

### 10.3. Không tiết lộ chi tiết phân loại qua timing tùy ý

Các lỗi validation có thể tốn thời gian khác nhau (signature verify, decrypt, XML parse). Không thể giả định mọi lỗi hoàn toàn constant-time ở cấp request. Tuy nhiên, không nên cố ý trả message/status/header riêng để kẻ tấn công phân biệt certificate, account existence hoặc tenant mapping. Dùng generic response cho lỗi xác thực và rate limit/monitoring cho lạm dụng.

Khi trả chi tiết hơn cho nhân viên vận hành, không dựa trên `?debug=true` do browser tự gửi. Kênh vận hành phải được xác thực/ủy quyền độc lập và không lưu raw credentials nếu không có quy trình riêng.

## 11. Java 17 thuần: phân tách mã lỗi nội bộ và thông báo công khai

Ví dụ sau chạy với **JDK 17+ không cần Spring Security**. Nó mô phỏng việc các điều kiện validation đã được cung cấp dưới dạng boolean. Đây **không phải** SAML parser/validator: boolean có thể do attacker tự tạo trong demo, không hề có cryptographic signature verification.

Tạo `SafeSamlFailureDemo.java`:

```java
public class SafeSamlFailureDemo {

    enum Reason {
        ACCEPTED,
        INVALID_SIGNATURE,
        WRONG_AUDIENCE,
        EXPIRED_ASSERTION,
        REQUEST_CORRELATION_FAILED
    }

    record Candidate(boolean signatureTrusted,
                     boolean audienceMatches,
                     boolean withinTimeWindow,
                     boolean requestCorrelated) {}

    static Reason evaluate(Candidate candidate) {
        if (!candidate.signatureTrusted()) {
            return Reason.INVALID_SIGNATURE;
        }
        if (!candidate.audienceMatches()) {
            return Reason.WRONG_AUDIENCE;
        }
        if (!candidate.withinTimeWindow()) {
            return Reason.EXPIRED_ASSERTION;
        }
        if (!candidate.requestCorrelated()) {
            return Reason.REQUEST_CORRELATION_FAILED;
        }
        return Reason.ACCEPTED;
    }

    static String publicMessage(Reason reason) {
        return reason == Reason.ACCEPTED
                ? "Sign-in complete"
                : "SSO sign-in failed";
    }

    public static void main(String[] args) {
        Candidate invalidSignature =
                new Candidate(false, true, true, true);
        Candidate wrongAudience =
                new Candidate(true, false, true, true);
        Candidate valid =
                new Candidate(true, true, true, true);

        Reason first = evaluate(invalidSignature);
        Reason second = evaluate(wrongAudience);
        Reason third = evaluate(valid);

        System.out.println("client 1: " + publicMessage(first));
        System.out.println("audit 1: " + first.name());
        System.out.println("client 2: " + publicMessage(second));
        System.out.println("audit 2: " + second.name());
        System.out.println("client 3: " + publicMessage(third));
        System.out.println("audit 3: " + third.name());
    }
}
```

Biên dịch và chạy:

```bash
javac SafeSamlFailureDemo.java
java SafeSamlFailureDemo
```

Stdout chính xác:

```text
client 1: SSO sign-in failed
audit 1: INVALID_SIGNATURE
client 2: SSO sign-in failed
audit 2: WRONG_AUDIENCE
client 3: Sign-in complete
audit 3: ACCEPTED
```

Điểm học tập:

- Hai lỗi khác nhau (`INVALID_SIGNATURE` và `WRONG_AUDIENCE`) tạo **cùng thông báo client**.
- Kênh `audit` có mã reason cố định, không chứa raw assertion hoặc khóa.
- `ACCEPTED` trong demo **không** chứng minh SAML đã được verify: các boolean chỉ do chương trình tự tạo. Production phải dùng Spring Security/OpenSAML để xác thực chữ ký/conditions/state trước khi tạo `Authentication`.
- Code demo dùng `System.out` để dễ quan sát; production audit dùng structured logger/metrics có access control, retention, log scrubbing và correlation IDs.
- Trong thực tế, một validation failure có thể thuộc nhiều nguyên nhân cùng lúc; code reason phân loại phải có policy nhất quán và không đoán từ untrusted exception message.

## 12. Kiểm thử QA: “reject” chưa đủ, phải “reject without leak”

### 12.1. Test hành vi bảo mật SAML

| Case âm tính | Kết quả authentication | Kết quả hiển thị/ghi log |
| --- | --- | --- |
| Thiếu `SAMLResponse` | Không tạo principal | Generic error; không dump form fields |
| Base64 sai | Reject | Không echo Base64 hoặc stack trace |
| XML malformed | Reject | Không trả XML fragment/DTD trong response |
| XML có entity/size abuse | Reject/413 tùy lớp | Không log body; giới hạn tài nguyên |
| Signature thiếu | Reject | Chỉ reason code nội bộ; không trả certificate info |
| Signature sai | Reject | Không log `SignatureValue`, XML hoặc full exception |
| `Issuer` chưa được tin | Reject | Không phản chiếu raw Issuer từ payload |
| Response cho SP entityID khác | Reject | Client không thấy expected Audience value |
| `Destination`/`Recipient` khác ACS | Reject | Không lộ URL nội bộ hoặc proxy headers |
| `NotBefore` trong tương lai | Reject | Không in timestamps/subject data cho browser |
| `NotOnOrAfter` đã qua | Reject | Không in assertion ID/Conditions |
| `InResponseTo` sai/đã consume | Reject | Generic error; audit code an toàn |
| Replay SAMLResponse trên hai pod | Reject lần lặp | Không chứa raw payload trong duplicate detection logs |
| Encrypted assertion không giải mã được | Reject | Không in decrypted/plaintext/ciphertext, private key path |
| Assertion có XML signature wrapping | Reject, chỉ dùng vùng XML được verify | Không in raw XML để “chứng minh” parser lỗi |
| IdP trả Status không thành công | Không authenticated | Client generic; internal code nếu cần |
| Claims có group lạ/tenant sai | Mapping/authorization reject theo policy | Không lộ claims hoặc account existence |
| Signing cert rollover bị lệch | Reject cho đến khi trust hợp lệ | Internal ops alert, không tắt signature |
| ACS path sai/không có filter | Không login | Generic 404/401; không stack trace |
| Client gửi RelayState tới host ngoài allowlist | Không open redirect | Không reflect/redirect theo giá trị raw |
| Một response thật bị ghi vào WAF/APM test canary | Bài test thất bại nếu secret xuất hiện | Sửa redaction/collection từ đầu |

### 12.2. Unit test cho failure handler

Không cần sinh assertion thật để kiểm thử **cách xuất thông báo lỗi**. Dùng `MockHttpServletRequest`, `MockHttpServletResponse` và một `AuthenticationException` test, gọi trực tiếp handler rồi assert:

- Status mong đợi (ví dụ 401), Content-Type text/plain UTF-8 hoặc redirect được allowlist.
- Body không chứa `SAMLResponse`, raw `NameID`, certificate PEM, exception message, stacktrace.
- Response headers không chứa `RelayState`, private key path, assertion ID.
- `Cache-Control: no-store` có mặt nếu cần.
- Event ID có định dạng opaque hợp lệ; dùng logger test appender đảm bảo không có raw request params/exception trong audit.
- Handler không dùng `exception.getMessage()` làm client output.

**Cẩn thận:** Nếu chỉ kiểm tra response mà không bắt logs/traces/proxy, vẫn có thể rò. Test riêng lớp logging và export telemetry bằng canary values.

### 12.3. Integration test end-to-end

Với IdP test và certificate test:

1. Tạo SP-initiated `AuthnRequest` từ Spring Security; lưu correlation state.
2. Gửi SAMLResponse hợp lệ ký bằng **IdP test private key**; xác nhận success.
3. Gửi các fixture sai chữ ký, sai audience, hết hạn, sai recipient, replay; xác nhận không tạo `Authentication`/session mới.
4. Thu response body, headers, redirect chain và browser error page; tìm secret canary/PII/certificate details.
5. Thu log ứng dụng, ingress/WAF/APM và metrics của môi trường test; tìm canary string trong raw XML, Base64, URL-encoded và debug exception.
6. Thử callback qua pod khác và session cookie bị chặn để kiểm tra không bỏ `InResponseTo`.
7. Thử 4xx/413 trước Spring filter, 5xx do lỗi config/Redis/keystore và lỗi SAML Logout nếu có; tất cả phải có generic external errors.
8. Khi một test fail, sửa **đúng lớp**: request-size guard, ACS matcher, IdP trust, cookie policy, failure handler, log scrubber, hoặc observability configuration.

### 12.4. Canary test kiểm tra lộ dữ liệu

Trong môi trường test **chỉ sử dụng dữ liệu giả**, gắn một token canary như:

```text
TEST_ONLY_SAML_CANARY_7F3A
```

vào một AttributeValue/NameID trong assertion do IdP test ký hoặc fixture được chuẩn bị hợp lệ theo test. Sau khi gửi fixture lỗi, quét các nguồn log/trace/error response xem canary có bị lộ không. Đừng dùng assertions thật của user và **không** chia sẻ PII trong ticket/screenshots.

Các lớp cần quét: request body capture trước SP, logger của OpenSAML/Spring Security, failure handler, custom exception mapping, API gateway/WAF/APM, crash reports và support systems. Nếu canary xuất hiện, test **FAIL** dù SP đã từ chối authentication đúng.

## 13. Chẩn đoán sự cố mà không bật raw payload logging

| Triệu chứng | Nguồn có thể | Dữ liệu kiểm tra an toàn |
| --- | --- | --- |
| Nhiều `INVALID_SIGNATURE` sau certificate rollover | SP metadata/IdP cert lệch | Thời điểm config deploy, IdP registration, certificate metadata công khai dưới kênh quản trị |
| `WRONG_AUDIENCE` sau đổi hostname | SP entityID không khớp | Public entityID đã cấu hình (không gửi trong browser error) |
| `WRONG_RECIPIENT`/`Destination` mismatch | ACS URL sai sau proxy | Public scheme/host/path/trusted forwarded headers |
| `EXPIRED_ASSERTION` tăng | Clock skew/IdP clock/latency | NTP metrics, allowed skew policy, histogram theo event code |
| `REQUEST_CORRELATION_FAILED` | Session state mất, SameSite cookie, request ID khác | Cookie có được gửi (không ghi giá trị), session store health, registration ID |
| `REPLAY_DETECTED` trên hai pod | Cache không atomic/chia sẻ | Replay store health, atomic transaction metrics |
| `DECRYPTION_FAILED` | Sai SP private decryption key, rollover | Version/rotation status ở kênh quản trị; không print private key |
| XML decode errors tăng | Client attack, proxy body rewrite, oversized payload | Body size/histogram/error count, không lưu body |
| Error page lộ stack trace | Spring Boot error config hoặc filter exception | Review global error mapping, integration test response |
| APM vẫn thấy SAMLResponse | Auto capture forms/exception locals | Cấu hình agent, denylisted fields, scrub policy |
| Response 401 nhưng user session vẫn còn | Failure path không đồng nghĩa revoke session | Session lifecycle/reauth/logout policy riêng |
| Nhiều 403 sau login success | Authorization/domain mapping | Role/object policy, không đổ mọi 403 cho SAML validation |

**Thứ tự debug hợp lý:** xác định error stage bằng event code; kiểm tra registration/metadata/clock/proxy/session bằng thông tin cấu hình; sử dụng signed **test fixtures** để tái tạo; chỉ dùng protected local debugger trên data giả; không bật logger “dump SAMLResponse” cho cả production.

## 14. Quan sát an toàn và ứng phó khi đã lỡ lộ dữ liệu

### 14.1. Nếu SAMLResponse/Assertion xuất hiện trong logs

1. **Ngừng thu thập** ở đúng nguồn: proxy, WAF, servlet request logger, APM agent hoặc custom exception formatter.
2. Hạn chế truy cập log/trace chứa credential và xác định khoảng thời gian, dữ liệu, người có thể xem.
3. Đánh giá khả năng assertion còn được dùng lại (lifetime, audience, subject confirmation, replay defense) và session nào được tạo; revoke session bị ảnh hưởng khi có dấu hiệu lạm dụng.
4. Làm việc với đội privacy/security về retention, pháp lý và quy trình xóa/giảm truy cập các bản sao trong archives/backups theo chính sách.
5. Bổ sung canary test và regression test để ngăn lặp.

**Không** copy raw assertion vào ticket mới hoặc chat nhóm để hỏi nguyên nhân; dùng event ID, reason code và một fixture giả thay thế.

### 14.2. Nếu private signing/decryption key bị lộ

1. Xem đây là **sự cố nghiêm trọng hơn lộ public certificate**: bảo vệ nơi lưu khóa, dừng phân phối trái phép, kiểm tra quyền và audit.
2. Tùy khóa bị lộ, phối hợp IdP/SP rotation, cập nhật metadata/cert trust và thu hồi khóa liên quan qua quy trình đã định.
3. Xác định các responses/requests/sessions có thể bị giả mạo hoặc giải mã, kiểm tra dấu hiệu truy cập trái phép.
4. Thu hồi secrets phụ (keystore passwords, cloud credentials) nếu cùng nguồn bị phơi; kiểm tra CI logs/backup.
5. Theo dõi các lỗi signature/decryption và login success bất thường trong giai đoạn chuyển khóa.
6. Không coi việc “đã xóa log” là khắc phục đủ nếu key vẫn có thể đã được sao chép.

### 14.3. Nếu hệ thống tăng lỗi nhưng không có bằng chứng tấn công

Lỗi SAML cũng thường đến từ misconfiguration: IdP cert rollover, lệch đồng hồ, ACS đổi URL, cookie SameSite, session store outage. Không tự mặc định mọi `INVALID_SIGNATURE` là attacker, nhưng cũng không tắt validation để giữ tỷ lệ login. Điều tra nguyên nhân có kiểm soát, dùng metrics nội bộ và test endpoint/metadata.

## 15. Checklist production

- [ ] ACS chỉ nhận đúng SAML response/binding theo cấu hình; giới hạn body size/parser complexity.
- [ ] Spring Security/OpenSAML vẫn xác minh chữ ký đúng object, issuer tin cậy, audience, recipient, destination, time conditions, correlation và replay policy.
- [ ] **Không** tạo `Authentication`/principal/role nếu SAML response invalid.
- [ ] `AuthenticationFailureHandler` cho SAML login chỉ trả thông báo chung và correlation ID độc lập; không serialize Throwable hay raw request body.
- [ ] Error mapping ngoài handler (proxy, servlet, global error page, startup/Redis/metadata failures, SAML Logout) cũng không lộ details.
- [ ] Không có `SAMLResponse`/`SAMLRequest`/Cookie/`RelayState` nhạy cảm trong access logs, trace, WAF hoặc APM.
- [ ] Structured audit dùng **reason code allowlist**, không dùng untrusted Issuer, NameID, exception message hay raw URL làm log fields.
- [ ] Private signing/decryption keys trong secret manager/keystore, không in vào startup/log/response và có rotation plan.
- [ ] Public certificates được quản trị trust đúng; không lấy `KeyInfo` của browser làm trust anchor.
- [ ] TLS, security headers, `Cache-Control: no-store` và request-size limits đã được kiểm thử.
- [ ] Trường hợp sai chữ ký, quá hạn, audience, recipient, InResponseTo, replay và XML malformed đều có test âm tính.
- [ ] Test **data-leak canary** quét response, log, trace và metrics đã chạy bằng dữ liệu giả.
- [ ] Không bật debug logging raw assertions trên production để “dễ sửa lỗi”.
- [ ] Error page không tạo login redirect loop, open redirect hay tiết lộ tồn tại account/tenant.
- [ ] Có dashboard/alert theo mã lỗi, node và thời gian; quyền đọc audit và retention được kiểm soát.
- [ ] Quy trình xử lý sự cố đã phân biệt lộ assertion với lộ private key và với lỗi cấu hình thông thường.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một SAMLResponse có chữ ký toán học hợp lệ bằng certificate đính kèm trong `KeyInfo`. SP có thể login ngay không?  
**Trả lời:** Không. SP chỉ tin public signing key gắn với **IdP registration đã được phê duyệt**, đồng thời phải kiểm tra issuer/audience/recipient/time/correlation và các điều kiện khác. Key do browser đưa không tự trở thành trust anchor.

**Câu 2.** Có nên ghi `log.error("SAML rejected", exception)` vào production logs để dễ debug?  
**Trả lời:** Không nên làm mặc định. Exception/cause có thể chứa dữ liệu từ SAML payload hoặc cấu hình nhạy cảm; ưu tiên event/reason code allowlist, event ID và protected diagnostics dùng fixture giả.

**Câu 3.** Từ chối login với `INVALID_SIGNATURE` và `EXPIRED_ASSERTION` có cần trả hai nội dung lỗi khác nhau cho browser?  
**Trả lời:** Thường không. Client chỉ cần thông báo chung; hệ thống vận hành phân biệt nguyên nhân trong audit có kiểm soát.

**Câu 4.** `SAMLResponse` là Base64, vậy log chuỗi đó có an toàn hơn log XML không?  
**Trả lời:** Không. Base64 không mã hóa bảo mật; có thể decode để lấy assertion và PII, thậm chí thử replay trong cửa sổ chấp nhận.

**Câu 5.** Tắt body logging của ứng dụng đã đủ để không rò assertion?  
**Trả lời:** Chưa đủ. Gateway, WAF, reverse proxy, APM, error monitoring và support systems có thể vẫn lưu body hoặc exception details.

**Câu 6.** Nếu IdP signing certificate bị thay mà SP chưa cập nhật, cách xử lý đúng là gì?  
**Trả lời:** Từ chối chữ ký không khớp, ghi sự kiện vận hành, xác minh và cập nhật trust theo quy trình rollover. Không bỏ signature validation để đăng nhập tạm.

**Câu 7.** SAML failure handler có bắt luôn request bị nginx chặn vì quá lớn không?  
**Trả lời:** Không. Lỗi 413 có thể xảy ra trước khi tới Spring Security; phải có generic error handling và redaction ở edge.

**Câu 8.** “Không lộ khóa” có nghĩa mọi public signing certificate đều bí mật?  
**Trả lời:** Không. Public certificate thường được công bố trong SAML metadata. **Private keys và secrets** phải giữ kín; failure page cũng không cần tiết lộ chi tiết trust/keystore nội bộ.

**Câu 9.** Tại sao test “response = 401” chưa đủ?  
**Trả lời:** Vì cùng request invalid có thể đã bị log nguyên `SAMLResponse` tại WAF/APM hoặc hiện trong exception. Phải kiểm thử **reject + no leak** xuyên hệ thống.

**Câu 10.** Có thể chuyển toàn bộ error details cho support qua query `?debug=true` không?  
**Trả lời:** Không. Debug phải có kênh riêng được xác thực/ủy quyền và dùng dữ liệu tối thiểu. Query do browser gửi không phải bằng chứng quyền xem secrets.

## 17. Tài liệu tham khảo chính thức và thực hành

- [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): luồng xác thực và điểm thất bại trước/sau OpenSAML authentication provider.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): cách provider xác minh SAMLResponse, issuer/destination, assertion conditions, tùy biến validation/decryption.
- [Spring Security – AuthenticationFailureHandler Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): handler cho authentication failure.
- [Spring Security – Servlet Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): phát sự kiện success/failure và exception mapping; đánh giá dữ liệu ghi log.
- [Spring Boot – Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): các `server.error.*` và giới hạn/config liên quan servlet.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): SAML Response, Assertion, signature/trust, Audience, SubjectConfirmation và Conditions.
- [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP Redirect/POST, `SAMLResponse`, `RelayState`.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): signature wrapping, trust keys, replay và SAML response validation.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet): dữ liệu không nên log, masking/sanitization, log injection, security events, quyền truy cập.
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): trả lỗi chung cho user, giữ chi tiết có kiểm soát và tránh rò secrets/stack traces.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet): session cookie, fixation, expiration và logout.

**Ghi nhớ:** **Từ chối SAML không hợp lệ** là một quyết định xác thực: không được tạo principal/quyền khi signature, trust, audience, recipient, thời gian hay correlation không đạt. **Không tiết lộ assertion hoặc khóa** là một quyết định xuyên hệ thống: browser chỉ thấy lỗi chung, audit chỉ ghi code/correlation ID có kiểm soát, còn proxy, servlet logs, OpenSAML diagnostics, APM, WAF và hỗ trợ kỹ thuật không được thu thập raw SAMLResponse, private keys hoặc secrets. Cả hai điều kiện phải đúng thì đường xử lý lỗi mới an toàn.