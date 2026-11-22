# Che dữ liệu nhạy cảm khi bật log Spring Security, OpenSAML hoặc Kerberos

**Module:** Spring Security – federation  
**Chủ đề cha:** Quan sát và gỡ lỗi  
**Stack tham chiếu:** Spring Boot 3.x, Spring Security 6.x, OpenSAML 4/5, Spring Security Kerberos/JAAS/JGSS, Java 17+, SLF4J/Logback.

## 1. Vì sao cần che dữ liệu khi bật log xác thực?

SAML2, OIDC và Kerberos liên quan trực tiếp đến danh tính và credential. Khi đăng nhập lỗi 401/403, SAML signature invalid hoặc Kerberos GSSException, DEBUG/TRACE giúp tìm filter/validator đang xử lý request. Tuy nhiên, dữ liệu mà người vận hành đang debug có thể chứa **bearer credentials, session tokens, PII và key material**.

Nếu ghi thô, một bản log có thể trở thành con đường dẫn tới:

- **Chiếm quyền phiên:** cookie JSESSIONID, gateway session cookie, bearer access/refresh token và một số vé xác thực còn hạn bị người xem log sử dụng lại.
- **Rò rỉ danh tính:** XML SAML Assertion có NameID, email, employee ID, department, groups, phone, tenant và attributes.
- **Lộ thông tin Kerberos:** AP-REQ/service ticket, TGT, GSS context, keytab content và session keys bị thu qua debug.
- **Lộ hạ tầng:** KDC/realm/service principal, IdP endpoints, key/certificate metadata, private file paths.
- **Log injection:** input chứa CR/LF hoặc multiline XML tạo dòng giả, làm sai audit hoặc tăng dung lượng logs.
- **Nhân bản dữ liệu ngoài kiểm soát:** console, stdout/stderr, APM, collector, SIEM, ticket attachments và backups đều có thể chứa các bản sao.

**Không coi Base64 là biện pháp bảo mật.** SAMLResponse HTTP-POST là XML được Base64-encode; JWT header/payload cũng có thể đọc. Một bearer token “trông như chuỗi random” vẫn là credential có thể bị tái sử dụng.

### Mục tiêu sau bài

1. Phân loại trường dữ liệu **không được xuất hiện trong log**.
2. Biết mức DEBUG/TRACE của **Spring Security** khác native debug của **JDK Kerberos/JAAS/JGSS**.
3. Thiết kế log **event/outcome/reasonCode/requestId** thay vì dump Request/Authentication/Assertion.
4. Áp dụng HMAC pseudonymization khi cần liên kết các events theo user mà không ghi NameID/UPN.
5. Kiểm tra cả **HTTP/proxy access log, APM, stdout/stderr và collector**, không chỉ Logback.
6. Bật debug theo scope/time window, kiểm thử synthetic canary, và xử lý khi đã có secret bị ghi.
7. Chạy được ví dụ Java 17 tự kiểm tra allowlist field, che tokens và chống CRLF log injection.

## 2. Bảng phân loại dữ liệu khi debug federation

| Nhóm | Ví dụ nguồn | Chính sách |
| --- | --- | --- |
| **Reusable secret** | Authorization Bearer/Basic/Negotiate, cookie, JSESSIONID, refresh token, client_secret, password | **Không log raw** kể cả DEBUG |
| **SAML identity assertion** | SAMLResponse, SAMLRequest, Assertion, NameID, Attributes, SessionIndex, RelayState | Không dump XML/Base64; log reason enum/IdP alias |
| **Kerberos credential** | AP-REQ/TGT/service ticket, keytab, ticket cache, session keys, GSS token | Không in bytes, hex dumps, keytab secret |
| **Khóa xác thực** | SP/IdP private key, signing secret, keystore password, JAAS password | Không log; dùng key alias/version |
| **Danh tính/PII** | Email, phone, UPN, principal, tenant/role, internal account ID | Minimize; HMAC-tag từ **verified** principal theo policy |
| **Session/correlation** | Cookie ID, InResponseTo, OAuth code, state, nonce, code_verifier | Không log raw; dùng interaction ID server-generated |
| **Metadata hạ tầng** | SPN/FQDN@REALM, KDC host, IdP entityID, X.509 fingerprint, secret mount path | Chỉ approved aliases; hạn chế topology |
| **HTTP raw input** | Header values, body, query string, user-agent, URL, exception message | Dữ liệu chưa tin, không pass thẳng vào logger |
| **Safe diagnostic** | AUTH_DENIED, SIG_INVALID, NO_CRED, HTTP 403, route template, duration bucket | Cho phép với schema allowlist |

Một số dữ liệu **có thể được công khai trong những bối cảnh khác** (ví dụ IdP metadata hoặc X.509 public cert), nhưng không có nghĩa phải lặp lại toàn bộ trong log. Chỉ log thông tin thực sự cần để điều tra.

**Masking một phần token là không đủ.** Đối với token/cookie/key, tốt hơn là **không ghi giá trị** hoặc chỉ ghi `[REDACTED]`/present=true. Với email/user ID ít biến thể, SHA-256 không khóa có thể bị suy đoán bằng dictionary; HMAC-SHA-256 có khóa riêng phù hợp hơn khi cần pseudonymization, nhưng vẫn phải quản lý privacy và key.

## 3. Mô hình bảo vệ theo từng lớp log

~~~text
HTTP/IdP/KDC request
       |
       v
Application / authentication libraries
  [A] No raw tokens / assertions / private keys in log calls
       |
       +--> SLF4J/Logback/Log4j2
       |
       +--> JVM Kerberos/JAAS/JGSS native stdout/stderr
       |
       v
Runtime / Ingress / Proxy / APM
  [B] No sensitive headers, bodies, full URLs or span attributes
       |
       v
Log agent / collector / queue
  [C] Secondary DLP/redaction, encrypted transport
       |
       v
SIEM / dashboards / alerts / archives / exports
  [D] RBAC, audit access, retention, backups, incident handling
~~~

**Tuyến phòng vệ chính là [A] — không tạo raw credential trong log.** Regex masking tại collector chỉ là defense-in-depth vì khi đó dữ liệu có thể đã đi qua console, file, stdout/stderr hoặc alert queue khác.

**Một Logback masking converter không tự bao phủ**:

- JDK Kerberos/JAAS debug dùng System.out/System.err ngoài SLF4J.
- Tomcat/Undertow/Nginx/Envoy access logs.
- OpenTelemetry/APM request header capture và exception attachments.
- HTTP client wire logs hoặc browser HAR/support bundles.
- File appenders hay JSON appenders không dùng chung converter.
- CI/test reports và crash diagnostics.

Không thể đánh giá an toàn chỉ bằng cách mở một log file rồi grep Authorization. Phải inventory **mọi sink và bản sao**.

## 4. Spring Security: bật DEBUG/TRACE có mục tiêu

Spring Security có DEBUG/TRACE cho FilterChainProxy, CSRF, authentication, authorization và xử lý 401/403. Đó là nguồn chẩn đoán hữu ích, nhưng trong ứng dụng có thể có custom filters/principals ghi thêm PII.

### 4.1. Mức log khuyến nghị ở môi trường thông thường

**src/main/resources/application.yml**

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.security: WARN
    org.springframework.security.saml2: WARN
    org.springframework.security.kerberos: WARN
    org.opensaml: WARN
    net.shibboleth: WARN
    com.example.security.audit: INFO
~~~

**Lưu ý:** org.opensaml và net.shibboleth chỉ là logger namespaces tham khảo theo major version/dependency; phải kiểm tra runtime thực tế. WARN không tự làm sạch những messages do thư viện khác/custom code sinh ra.

### 4.2. Điều tra 403 bằng một logger hẹp

Trên staging hoặc một diagnostic window được phê duyệt:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.security: WARN
    org.springframework.security.web.FilterChainProxy: DEBUG
    org.springframework.security.web.access.ExceptionTranslationFilter: DEBUG
    org.opensaml: WARN
    net.shibboleth: WARN
~~~

- **FilterChainProxy** có thể cho biết request có được security chain xử lý hay không.
- **ExceptionTranslationFilter** giúp nhận diện luồng authentication entry point/access denial tùy Spring Security version.
- Không bật toàn bộ **org.springframework.security=TRACE** nhiều giờ chỉ để xem vì sao một route trả 403.
- Khi filter debug ghi request path, đường dẫn có PII/path params vẫn cần đánh giá: không mặc định mọi URL đều an toàn.
- Dùng **reason code** do app kiểm soát để phân biệt CSRF_DENIED, NO_AUTHENTICATION, MISSING_AUTHORITY hoặc LOCAL_USER_DISABLED.

Tài liệu Spring Security mô tả DEBUG/TRACE như công cụ chẩn đoán filter invocations. **Nó không phải bảo đảm rằng nội dung DEBUG luôn không có secret trong mọi custom filter hoặc extension**.

### 4.3. Không log toàn bộ Authentication hoặc Principal

~~~java
// Anti-pattern: toString() của đối tượng tùy biến có thể
// in principal attributes, details hoặc credentials.
log.debug("authentication={}",
    SecurityContextHolder.getContext().getAuthentication());
log.debug("principal={}", authentication.getPrincipal());
log.debug("headers={}", request.getHeader("Authorization"));
~~~

Một số implementation cố che credentials, nhưng không thể giả định **mọi** custom Authentication/principal/toString đều đã redact. Các claim XML, email, role, request details hoặc sensitive attributes vẫn có thể xuất hiện.

**Thay thế:**

~~~java
// Fragment: correlationId do trusted edge/app tạo.
log.info("event={} outcome={} reason={} requestId={}",
    "AUTHORIZATION_DENIED", "DENY",
    "MISSING_REQUIRED_AUTHORITY", correlationId);
~~~

Ngay cả parameterized SLF4J cũng **không tự redaction**. Nếu argument là raw SAMLResponse, token hoặc exception chứa PII, vẫn rò như khi nối chuỗi.

## 5. OpenSAML: SAMLResponse và NameID là dữ liệu nhạy cảm

Spring Security SAML2 dùng OpenSAML để xử lý SAMLResponse/Assertion. Các đối tượng có thể giữ NameID, Attributes, SessionIndex, SignatureValue và XML đã parse.

### 5.1. Tránh ghi những đối tượng nào?

- Request parameter **SAMLResponse**; Base64 có thể decode ra Assertion XML.
- **SAMLRequest**, RelayState, raw SAML metadata XML.
- **Saml2Authentication.getSaml2Response()** hoặc object giữ XML/Response.
- **Saml2AuthenticatedPrincipal.getAttributes()** và toàn bộ NameID/Attributes.
- Assertion XML, SubjectConfirmationData, Conditions, SessionIndex, EncryptedAssertion.
- XMLDSig SignedInfo/SignatureValue, KeyInfo/X509Data nguyên văn.
- Raw exception.getMessage(), toString(), cause chain nếu có XML hoặc identity text.
- Dump toàn bộ HTTP request khi SAML assertion validation fail.

**Nguyên tắc về trust:** NameID/Issuer do một SAMLResponse chưa được verify có thể do attacker khai. Không ghi chúng là “verifiedUser” trong audit khi signature/issuer/audience còn chưa kiểm.

### 5.2. Log gì thay payload?

| Sự cố | Safe event / reasonCode | Metadata phù hợp |
| --- | --- | --- |
| ACS nhận POST | SAML_ACS_RECEIVED | requestId, approved registration alias |
| XML malformed | SAML_XML_REJECTED | parser error category, byte-size bucket |
| Signature invalid | SAML_SIGNATURE_INVALID | trusted IdP alias, signer key version alias |
| Signing key không trusted | SAML_UNTRUSTED_SIGNING_KEY | configured trustset alias |
| Issuer mismatch | SAML_ISSUER_MISMATCH | expected IdP alias, không raw untrusted issuer |
| Audience/Recipient sai | SAML_AUDIENCE_MISMATCH | SP registration alias |
| Destination/ACS sai | SAML_DESTINATION_INVALID | route template |
| Assertion expired | SAML_ASSERTION_EXPIRED | clock skew bucket |
| InResponseTo mismatch | SAML_REQUEST_CORRELATION_FAILED | server interaction ID |
| Replay detected | SAML_REPLAY_REJECTED | replay policy code |
| User thiếu local account | SAML_LOCAL_ACCOUNT_DENIED | verified userTag nếu có |
| Login success | SAML_AUTHENTICATED | verified userTag, IdP alias |

Ví dụ:

~~~json
{
  "timestamp": "2026-11-07T03:00:00Z",
  "service": "sso-sp",
  "event": "SAML_LOGIN_FAILED",
  "protocol": "SAML2",
  "outcome": "DENY",
  "reasonCode": "SIG_INVALID",
  "registrationAlias": "corp-idp",
  "requestId": "req-91ab",
  "userTag": null
}
~~~

**Không lấy raw Issuer từ XML thất bại rồi gán vào trusted issuer field.** Log expected registration alias và categorical failure, tránh đưa untrusted claims vào log như sự thật.

### 5.3. Logging categories và SAML Extension đời cũ

Có thể gặp loggers trong **org.opensaml** và **net.shibboleth** theo version. Khi cần debug, bật đúng class/package nhỏ trên staging và review sample output; không bật full org.opensaml=TRACE mặc định.

**Cảnh báo legacy:** Spring Security SAML Extension/OpenSAML đời cũ có cấu hình SAMLDefaultLogger và tùy chọn logAllMessages/logMessagesOnException. Không copy cấu hình đó vào Spring Security 6.x như thể API tương đương; trên hệ thống legacy, bật message dumping có thể in raw Assertion XML.

### 5.4. Failure handler không rò XML

~~~java
// Fragment trong HttpSecurity, cần logger bean/imports.
http.saml2Login(saml -> saml
    .failureHandler((request, response, exception) -> {
        // KHÔNG request.getParameter("SAMLResponse")
        // KHÔNG exception.getMessage() hoặc toString()
        auditLogger.warn(
            "event={} outcome={} reason={}",
            "SAML_LOGIN_FAILED", "DENY", "VALIDATION_FAILED");
        response.sendRedirect("/login?error");
    }));
~~~

Production nên map lỗi provider đã biết sang **enum allowlist** và không log raw throwable/cause nếu chưa kiểm tra. Failure handler không được dùng request parameter để xây Location có token/RelayState.

## 6. Kerberos/JAAS/JGSS: có native debug ngoài Logback

JDK Kerberos/Java GSS-API có các debug flags, với hành vi/version khác nhau:

~~~text
-Dsun.security.krb5.debug=true
-Dsun.security.jgss.debug=true
-Dsun.security.spnego.debug=true
-Djava.security.debug=all
-Djavax.net.debug=all
~~~

JAAS **Krb5LoginModule** cũng có option **debug=true**. Một số phiên bản Spring Security Kerberos có **SunJaasKerberosTicketValidator.setDebug(true)**. **Đây là những tùy chọn rủi ro cao, không phải cài đặt production thường trực.** Oracle cảnh báo security debug có thể chứa thông tin nhạy cảm. Kiểm tra sự hỗ trợ/đầu ra ở đúng phiên bản JDK dùng thực tế.

### 6.1. Vì sao chỉ cấu hình Logback không đủ?

JDK/JAAS/JGSS có thể in trực tiếp **System.out/System.err**. Vì thế:

- logging.level.org.springframework.security=OFF không bảo đảm tắt JDK Kerberos debug.
- Logback %replace converter/JSON encoder không chắc xử lý dòng JDK native này.
- Container runtime, kubectl logs và log agent vẫn có thể thu raw stdout/stderr.
- JVM startup flags, environment/process inspection và support bundles cũng có thể lộ địa chỉ KDC, principal hoặc secret paths.

**Chính sách:** Tắt native debug ngay tại nguồn. Nếu thực sự cần, dùng **test Kerberos realm, service account và keytab riêng**, process cô lập, không ship đến SIEM production.

### 6.2. Thứ gì không được in từ Kerberos?

| Nguồn | Dữ liệu cấm raw | Thay bằng |
| --- | --- | --- |
| Authorization: Negotiate | GSS/SPNEGO AP-REQ token | SPNEGO present=true |
| TGT, ticket cache | Ticket bytes/credential keys | cacheAvailable bool |
| Keytab | Secret key bytes, keytab dump | keytabReadable bool, rotation alias |
| JAAS Subject/GSSContext | Credentials, ticket objects | auth outcome enum |
| User principal/UPN | alice@REALM và danh tính nhân viên | HMAC userTag sau validation |
| Service principal | HTTP/FQDN@REALM nếu lộ topology | approved SPN alias |
| GSSException | Full message/stack nếu chứa danh tính | GSS major status enum |
| KDC/realm/path | Internal network và secret mount path | safe realm/service alias |
| Session key/enctype dump | Key material | enctype category khi được phép |

Đặc biệt: kiểm keytab metadata qua công cụ quản trị có thể dùng **klist -k -e** trong môi trường được phép, nhưng **không dùng -K** vì có thể in key material. Không upload keytab, ticket cache hoặc raw Kerberos trace lên issue/chat.

### 6.3. Ví dụ phân loại GSSException

~~~java
// Fragment: GSSException từ org.ietf.jgss.
// Code accept token do Kerberos library cung cấp.
try {
    // performKerberosAccept(...); // thao tác thực tế của thư viện
} catch (GSSException ex) {
    String reason = switch (ex.getMajor()) {
        case GSSException.NO_CRED -> "GSS_NO_CRED";
        case GSSException.DEFECTIVE_TOKEN -> "GSS_DEFECTIVE_TOKEN";
        case GSSException.BAD_MIC -> "GSS_BAD_MIC";
        default -> "GSS_FAILURE";
    };
    auditLogger.warn("event={} reason={}",
        "KERBEROS_TICKET_REJECTED", reason);
    // Fail closed, không cấp quyền khi validate lỗi.
}
~~~

Đây là **fragment**, không phải class biên dịch riêng: phần Kerberos accept và logger do ứng dụng cấu hình. Không log ex.toString(), ex.getMessage(), raw ticket byte[] hoặc JAAS Subject. Các nguyên nhân cụ thể như keytab không đọc được, KVNO sai, clock skew cần được map an toàn ở tầng phù hợp.

### 6.4. Chẩn đoán Kerberos an toàn

1. Xem HTTP 401 có WWW-Authenticate: Negotiate không (**không** log Authorization token).
2. Đối chiếu SPN alias, keytabReadable, KDC reachability, clock/NTP, DNS/realm config.
3. Ghi GSS error category thay vì raw token hoặc exception.
4. Nếu validator thành công nhưng request bị 403, kiểm local UserDetailsService/role thay vì tự kết luận GSS hỏng.
5. Debug sâu chỉ trong lab/test realm với test keytab và stdout/stderr cô lập.
6. Tắt JVM/JAAS flags sau test và xác nhận runtime thực tế.

## 7. Các đường rò ngoài Spring Security logger

Đừng chỉ tìm các lệnh log trong Java. Một môi trường SSO có thể leak ở:

- **CommonsRequestLoggingFilter** khi bật includePayload, includeHeaders hoặc includeQueryString.
- Custom Servlet filter/interceptor/response wrapper ghi request/response đầy đủ.
- Nginx/Envoy/Tomcat access logs ghi full URI chứa OAuth code, state, RelayState.
- HTTP client wire logs, Reactor Netty, Apache HttpClient/OkHttp interceptors.
- APM/OpenTelemetry traces có url.full, enduser.id, http.request.header.authorization, exception.message.
- Sentry/error reporter ghi request context/stacktrace chứa PII.
- MDC chứa email, principal, session ID, Cookie hoặc SAMLResponse.
- CI runner, HAR/browser trace, crash dump, support bundle, container stdout/stderr và alert attachments.

### RequestLoggingFilter phải hạn chế payload/headers

~~~java
// Fragment của Spring Boot web app.
CommonsRequestLoggingFilter filter =
    new CommonsRequestLoggingFilter();
filter.setIncludeHeaders(false);
filter.setIncludePayload(false);
filter.setIncludeQueryString(false);
filter.setIncludeClientInfo(false);
filter.setMaxPayloadLength(0);
~~~

Cấu hình này **không che được logs ở proxy/APM/JDK**. Không log raw request bodies hoặc query trên ACS, OIDC callback, login, logout và token endpoints; cũng cần áp chính sách tương tự với các business APIs có Bearer/Cookie.

URL path có thể chứa email/PII; ưu tiên **route template** (/api/orders/{id}) thay vì full URL.

### Regex masking và JSON encoder không phải giải pháp đầy đủ

Regex dễ bỏ sót token trong Base64, URL encoding, multiline XML, JSON nested fields, repeated headers, exception causes, các token bị split/truncate, hoặc những custom headers khác tên. Structured JSON encoder có thể escape CRLF nhưng **vẫn in raw secret** nếu event chứa nó.

**Ưu tiên source-level field allowlist**; collector DLP/regex chỉ bổ sung để giảm rủi ro từ third-party outputs, và phải test nhiều encoding.

## 8. Safe security audit event: chỉ fields có ý nghĩa

Một security event tối thiểu có thể chứa:

| Field | Nguồn | Chính sách |
| --- | --- | --- |
| timestamp | Server UTC | Được phép |
| service | Deployment alias | Không lấy từ Host header chưa tin |
| requestId | Server-generated/ingress đã chuẩn hóa | Dài giới hạn, không chứa credential |
| event | Enum | SAML_LOGIN_FAILED, ACCESS_DENIED |
| protocol | Enum | SAML2, OIDC, KERBEROS, SPRING_SECURITY |
| outcome | Enum | SUCCESS, DENY, ERROR |
| reasonCode | Enum | SIG_INVALID, NO_CRED, ISSUER_MISMATCH |
| registrationAlias | Config allowlist | Không raw untrusted Issuer |
| userTag | HMAC pseudonym | Chỉ sau xác thực thành công |
| httpStatus | 302, 401, 403... | Được phép |
| durationBucket | Nhóm thời gian | Không raw payload |
| routeTemplate | App configuration | Tránh raw URL/PII |

Không có field tự do tên details nhận XML/headers/exception message.

~~~json
{
  "timestamp": "2026-11-07T03:00:00Z",
  "service": "sso-sp",
  "requestId": "req-56a1",
  "event": "SAML_LOGIN_FAILED",
  "protocol": "SAML2",
  "outcome": "DENY",
  "reasonCode": "SIG_INVALID",
  "registrationAlias": "corp-idp",
  "userTag": null,
  "httpStatus": 401
}
~~~

### SLF4J application code

~~~java
// Fragment trong Spring Boot, logger đã khai báo:
auditLogger.warn(
    "event={} protocol={} outcome={} reason={} requestId={}",
    "SAML_LOGIN_FAILED", "SAML2", "DENY",
    "SIG_INVALID", safeServerGeneratedRequestId);
~~~

**Không log exception dưới dạng argument cuối cùng** khi chưa đánh giá: SLF4J có thể in Throwable/stacktrace, bao gồm message mang token, XML hoặc internal paths.

## 9. Java 17 runnable: HMAC pseudonymization và field allowlist

Bài thực hành sau dùng **JDK 17 thuần**, không cần Spring, OpenSAML, IdP hay KDC. Nó minh họa:

- Chỉ các field event, outcome, reason, requestId và userTag được phép vào log.
- Raw Authorization/Bearer, SAMLResponse và Cookie bị bỏ ngay lúc tạo event.
- User ID được pseudonymize bằng HMAC-SHA-256 (12 bytes digest → 24 hex).
- CRLF/tab/controls trong requestId được thay thành dấu gạch dưới, giới hạn chiều dài.
- Kết quả chỉ in các boolean assertions, không in userTag thật.

**Tệp: SafeSecurityLogDemo.java**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SafeSecurityLogDemo {

    private static final Set<String> ALLOWED =
        Set.of("event", "outcome", "reason", "requestId", "userTag");

    // Key DEMO, tuyệt đối không dùng ở production.
    private static final byte[] TEST_KEY =
        "demo-not-a-production-secret"
            .getBytes(StandardCharsets.UTF_8);

    static String tag(String user, byte[] key)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        byte[] digest =
            mac.doFinal(user.getBytes(StandardCharsets.UTF_8));
        return HexFormat.of().formatHex(digest, 0, 12);
    }

    static String safeValue(String value) {
        if (value == null) {
            return "-";
        }
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < value.length()
                && out.length() < 80; i++) {
            char c = value.charAt(i);
            if (Character.isISOControl(c)
                    || c == '\u2028' || c == '\u2029') {
                out.append('_');
            } else {
                out.append(c);
            }
        }
        return out.toString();
    }

    static String event(Map<String, String> input) {
        StringBuilder out = new StringBuilder();
        String[] keys =
            {"event", "outcome", "reason", "requestId", "userTag"};
        for (String key : keys) {
            if (!ALLOWED.contains(key)) {
                continue;
            }
            if (out.length() > 0) {
                out.append(' ');
            }
            out.append(key).append('=')
                .append(safeValue(input.get(key)));
        }
        return out.toString();
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        String user = "alice@example.test";
        String bearer = "fake-bearer-never-log";
        String saml = "fake-saml-never-log";
        String cookie = "fake-cookie-never-log";

        String a = tag(user, TEST_KEY);
        String same = tag(user, TEST_KEY);
        String b = tag("bob@example.test", TEST_KEY);

        Map<String, String> fields = Map.of(
            "event", "SAML_LOGIN_FAILED",
            "outcome", "DENY",
            "reason", "SIG_INVALID",
            "requestId", "req-001\nspoofed=admin",
            "userTag", a,
            "Authorization", bearer,
            "SAMLResponse", saml,
            "Cookie", cookie);

        String line = event(fields);

        System.out.println("stableTag=" + a.equals(same));
        System.out.println("differentUsers=" + !a.equals(b));
        System.out.println("hasRawUser=" + line.contains(user));
        System.out.println("hasBearer=" + line.contains(bearer));
        System.out.println("hasSaml=" + line.contains(saml));
        System.out.println("hasCookie=" + line.contains(cookie));
        System.out.println("hasNewline=" + line.contains("\n"));
        System.out.println("safeRequestId=" +
            line.contains("requestId=req-001_spoofed=admin"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SafeSecurityLogDemo.java
java SafeSecurityLogDemo
~~~

**Stdout chính xác theo logic Java 17:**

~~~text
stableTag=true
differentUsers=true
hasRawUser=false
hasBearer=false
hasSaml=false
hasCookie=false
hasNewline=false
safeRequestId=true
~~~

**Diễn giải:** HMAC tạo tag ổn định cho cùng user/khóa, tag khác cho hai users với xác suất rất cao; các field không trong allowlist bị loại; CR/LF thành `_` nên không tạo dòng log giả.

**Giới hạn:** Đây là event builder minh họa, không phải Logback plugin, không kiểm HTTP/native JVM logs. Production phải lấy HMAC key từ secret manager/KMS (không hardcode), có rotation/ACL và chia scope theo môi trường/tenant. UserTag vẫn có thể là pseudonymous personal data; không coi HMAC là vô danh tuyệt đối. Event/outcome/reason trong hệ thống thật nên là enum do server chọn, không cho client điền tùy ý. RequestId tốt nhất do server tạo; sanitization chỉ là lớp bổ sung.

## 10. MDC và distributed tracing

MDC giúp correlation các events trong một request. Nhưng đừng đưa session ID, raw principal, email hoặc Authorization vào MDC: field ấy có thể được mọi appender/trace exporter ghi.

~~~java
import org.slf4j.MDC;

// Fragment: serverRequestId do trusted edge/server tạo.
try (MDC.MDCCloseable scope =
        MDC.putCloseable("requestId", serverRequestId)) {
    filterChain.doFilter(request, response);
}
~~~

Phải clear MDC trong finally/try-with-resources để tránh dữ liệu của request trước lọt sang request khác trên thread pool. Async/reactive hoặc virtual threads cần cơ chế context propagation phù hợp; không mặc định MDC luôn di chuyển đúng.

**Anti-pattern:**

~~~java
MDC.put("Authorization", request.getHeader("Authorization"));
MDC.put("sessionId", request.getSession().getId());
MDC.put("username", authentication.getName());
MDC.put("saml", request.getParameter("SAMLResponse"));
~~~

APM tracing có nguyên tắc tương tự: tránh span attributes như raw full URL, sensitive headers, XML body hoặc exception.message nếu chứa PII. JSON encoder chỉ escape output, **không tự che nội dung**.

## 11. Debug có thời hạn và rollback

### Trước khi bật

1. Xác định câu hỏi: FilterChain match? SAML signature/Issuer? Kerberos keytab? Clock skew? UserDetailsService?
2. Có ticket/owner, approval, logger category, environment, số pod, thời gian kết thúc và rollback plan.
3. Ưu tiên staging và **test IdP/test Kerberos realm** với fake credentials/NameID.
4. Kiểm nơi lưu: console, stdout/stderr, appender file, proxy access log, APM, collector/SIEM/alerts.
5. Tạo synthetic canaries để xác nhận không có token/XML/UPN rò.
6. Bật đúng logger hẹp và mức DEBUG thấp nhất cần; không tự động mở all/TRACE.
7. Xác minh RBAC/retention/export và ai được xem log ở giai đoạn debug.

### Khi đang bật

- Giới hạn đúng workload/pod; quan sát log volume, CPU/disk và event categories.
- Dùng requestId để correlate, không in raw InResponseTo/session key.
- Nếu phát hiện credential ở stdout/stderr/collector, dừng thu thập và đánh giá sự cố.
- Không dán HAR/debug bundle có raw tokens vào issue/chat/email không được phép.

### Sau khi bật

1. Hạ logger levels; tắt JVM krb5/jgss/spnego flags và JAAS debug=true (có thể phải restart JVM).
2. Xác minh **runtime config** đã thực sự trở lại mức an toàn, không chỉ sửa YAML/Git.
3. Test logs mới không chứa canary; safe audit events vẫn tồn tại.
4. Xem lại các copies cũ ở agent, SIEM, alert, queue, backups và exports.
5. Nếu có leak, revoke/rotate theo phạm vi; audit ai đã truy cập.
6. Ghi safe incident summary và thêm regression tests/deployment guardrails.

**Tắt DEBUG không xóa credentials đã ghi trong log cũ.**

## 12. Chẩn đoán mà không cần raw token

### 12.1. SAML2 login thất bại

- Kiểm ACS endpoint và approved registration alias, không in SAMLResponse.
- Xem reason code: XML_MALFORMED, SIG_INVALID, UNTRUSTED_KEY, ISSUER_MISMATCH, AUDIENCE_MISMATCH, DESTINATION_INVALID, ASSERTION_EXPIRED, CORRELATION_FAILED, REPLAY_REJECTED.
- Kiểm SP EntityID/ACS URL, trusted IdP signing key alias, thời gian và local user mapping.
- Nếu signature fail, **không tin NameID trong XML như user đã xác thực**.
- Reproduce với signed synthetic fixture trong staging thay vì in Assertion của user thật.

### 12.2. Kerberos Negotiate 401

- Có WWW-Authenticate: Negotiate không, chỉ log presence chứ không log Authorization token.
- Kiểm service principal alias, keytabReadable, KVNO/enctype metadata qua kênh admin được phê duyệt.
- Kiểm DNS/KDC/clock/skew, policy browser trusted site và GSS major status.
- Phân biệt ticket validation fail với local account/role denial.
- Native JDK debug chỉ ở lab với test realm/keytab và cô lập stdout/stderr.

### 12.3. Spring Security 403

- Kiểm security chain, CSRF vs not-authenticated vs missing authority.
- Ghi route template, method, event, reason enum, status, requestId.
- Nếu principal đã verified, có thể ghi userTag HMAC theo policy.
- Không ghi raw SecurityContext/Authentication/session/CSRF tokens.
- Khi có tenant/resource deny, kiểm policy business nhưng không in dữ liệu object nhạy cảm.

## 13. Kiểm thử chống rò rỉ trên mọi sink

Dùng **chỉ fake secrets/canaries** ở staging/test, không đưa token/keytab thật vào bài test.

| # | Test | Kỳ vọng |
| --- | --- | --- |
| 1 | Authorization Bearer fake token | Không log raw |
| 2 | Authorization Negotiate fake GSS token | Không log raw |
| 3 | Basic auth fake base64 | Không log raw |
| 4 | Cookie JSESSIONID fake | Không log raw |
| 5 | Set-Cookie session response | Không log raw |
| 6 | SAMLResponse Base64 với fake NameID | Không raw XML/Base64 |
| 7 | SAMLRequest và RelayState fake | Không raw |
| 8 | EncryptedAssertion/SignatureValue | Không dump |
| 9 | OIDC access_token/id_token/refresh_token | Không log raw |
| 10 | OAuth state/code/code_verifier | Không log raw query |
| 11 | CSRF 403 | Có reason enum, không CSRF token |
| 12 | Authentication.toString custom | Không dump attributes/credentials |
| 13 | SAML signature invalid | SIG_INVALID, không raw assertion |
| 14 | Wrong Issuer từ untrusted XML | Không log raw received issuer như trusted |
| 15 | SAML fail trước validate | userTag null |
| 16 | Kerberos GSS_NO_CRED | Log code, không ticket |
| 17 | Keytab unreadable | Log boolean/alias, không secret |
| 18 | Native krb5 debug trong test realm | Kiểm stdout/stderr |
| 19 | Spring Security logger DEBUG hẹp | Không xuất hiện fake secrets |
| 20 | CommonsRequestLoggingFilter | Không include headers/body/query |
| 21 | Nginx/Tomcat/Envoy access logs | Không full URL query chứa code/token |
| 22 | HTTP client wire logging | Không dump auth headers |
| 23 | APM/OTel spans | Không chứa PII/token/session |
| 24 | MDC với fake token | Bị bỏ khỏi logging schema |
| 25 | CRLF trong requestId | Không log injection |
| 26 | JSON nested secret | Không lọt encoder/collector |
| 27 | Exception message có fake token | Không in raw message/stack |
| 28 | User input quá dài | Bị giới hạn; không log DoS |
| 29 | HMAC same user | Stable pseudonym |
| 30 | HMAC different users | Tags khác với xác suất rất cao |
| 31 | HMAC key rotation | Không lộ key, scope đúng |
| 32 | Async/multiple appenders | Chính sách áp tất cả sinks |
| 33 | SIEM alert/export/backup | Không có raw canary |
| 34 | Debug expiry | TRACE/JVM flags tắt thực tế |
| 35 | Log RBAC/retention | Đúng thời hạn và quyền |
| 36 | Audit event khi log giảm | Safe events vẫn có mặt |

**Test quy trình:**

1. Tạo canary tokens và XML có dữ liệu giả, thử raw/Base64/URL-encoded/JSON-escaped dạng.
2. Gửi qua success và failure của SAML2/OIDC/Kerberos test endpoints.
3. Thu stdout, stderr, Logback console/file, proxy access log, APM spans, collector queues, SIEM test index và alert payload.
4. Assert không có canary, cả dạng encoded/decoded, trong mọi sink.
5. Assert các safe audit events vẫn xuất hiện: event/outcome/reasonCode/requestId.
6. Kiểm RBAC, retention, alert export và backup theo chính sách.
7. Chạy lại sau upgrade JDK/OpenSAML/Spring Security/Logback hoặc thêm filter mới.

**Log hoàn toàn rỗng không phải QA PASS**, vì thiếu audit security events có thể làm mất khả năng phát hiện tấn công.

## 14. Incident response nếu đã log secret

Khi production đã ghi Authorization, session cookie, SAML XML hoặc Kerberos credential:

1. **Chặn rò mới tại nguồn**: tắt raw logging/native debug, rollback cấu hình.
2. **Cô lập sinks**: hạn viewer/export, định vị app log, stdout, collector, SIEM, alert attachments và backups.
3. Phân loại exposure: reusable token/session, SAML PII, Kerberos ticket, keytab/private key.
4. Revoke/expire sessions/tokens hoặc rotate service credentials/keytab/keys theo mức lộ và threat model.
5. Audit truy cập log, đánh giá privacy/legal notification obligations.
6. Không paste lại raw token/PII trong incident reports; dùng safe correlation IDs.
7. Sửa code/log policy, cập nhật CI canary tests, áp debug expiry/approval.
8. Theo dõi dấu hiệu sử dụng lại credential hoặc hành vi bất thường.

**Encryption at rest chỉ bảo vệ log storage, không thay source-level minimization.** Người có quyền query/export log vẫn thấy raw secret nếu app đã lưu nó.

## 15. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Hướng giải quyết |
| --- | --- | --- |
| TRACE Spring Security mặc định production | Quá nhiều dữ liệu/volume/PII | Logger hẹp và time window |
| Base64 SAMLResponse được coi vô hại | Decode được XML/NameID | Không ghi body/param |
| Một Logback regex đã che hết | JDK stderr/proxy/APM ngoài converter | Source-level allowlist + multi-sink tests |
| JSON log thì auto redact | JSON vẫn serialize token | Schema allowlist |
| Authentication.toString luôn an toàn | Custom principal/details có thể leak | Event/outcome/verified tag |
| Chỉ hash SHA-256 email | Dictionary attack | HMAC keyed hoặc không log |
| Full exception để debug nhanh | Raw message có XML/PII/file paths | Safe error enums |
| Kerberos debug là một SLF4J logger | JDK có stdout/stderr native | Tắt JVM/JAAS flags |
| Logs trong SIEM nội bộ nên khỏi che | Nhiều viewer/export/backups | RBAC, minimization, TTL |
| Tắt debug nghĩa là đã xóa leak | Copies cũ còn tồn tại | Incident response + revoke/rotate |
| Issuer trong failed SAML là identity đã verified | Chưa qua trust validation | Log configured alias/reason |
| MDC chứa session ID để dễ search | Credential có thể bị lộ | Server requestId hoặc HMAC theo policy |

## 16. Checklist production

- [ ] Có inventory mọi data-flow: Spring/SLF4J, JVM stdout/stderr, reverse proxy, APM, collector, SIEM.
- [ ] Không log raw Authorization Bearer/Basic/Negotiate, Cookies/JSESSIONID, access/refresh/ID tokens.
- [ ] Không log SAMLResponse/SAMLRequest, XML Assertion, NameID, Attributes, RelayState hoặc SessionIndex raw.
- [ ] Không log Kerberos AP-REQ/TGT/ticket cache, keytab/private key, GSSContext, JAAS Subject hoặc session keys.
- [ ] Không log raw Authentication/Principal/Saml2Authentication hoặc exception messages chưa review.
- [ ] Spring Security và OpenSAML logger levels đủ thấp; DEBUG chỉ ở class/package hẹp khi được phê duyệt.
- [ ] Không bật JDK krb5/jgss/spnego.debug hoặc Krb5LoginModule debug=true thường trực.
- [ ] Console/stdout/stderr native Kerberos được test riêng với Logback.
- [ ] HTTP access logs, CommonsRequestLoggingFilter, APM/OTel và HTTP clients không tự động dump auth headers/body/query.
- [ ] Chỉ log safe event enum, outcome, reasonCode, approved registration alias, route template và requestId.
- [ ] userTag chỉ từ verified principal, tạo bằng HMAC keyed theo privacy/key lifecycle.
- [ ] MDC/trace attributes không chứa token, email, session ID hoặc XML.
- [ ] CRLF/control chars và length của untrusted fields được giới hạn; log injection bị chặn.
- [ ] JSON/Logback regex che bổ sung, không thay source minimization.
- [ ] Log storage có encryption, RBAC, audit export, retention/delete và backup controls.
- [ ] Debug ticket có scope, owner, expiry, rollback và kiểm tra runtime đã tắt.
- [ ] Canary leak tests chạy trên console/file/stdout/stderr/proxy/APM/collector/SIEM.
- [ ] Safe security events vẫn có mặt dù không lưu raw payload.
- [ ] Có kế hoạch incident response revoke/rotate nếu log chứa secrets.
- [ ] Sau nâng framework/JDK/logger provider, chạy regression tests trước production.

**Kết luận:** Bật DEBUG/TRACE cho Spring Security, OpenSAML hoặc Kerberos là hành động **mở rộng bề mặt truy cập dữ liệu xác thực**, không chỉ tăng số dòng log. Giữ giá trị chẩn đoán bằng **typed security events, reason codes, requestId và verified HMAC userTag**, tránh tạo raw credentials/Assertion/Keytab trong log ngay từ đầu. Kiểm cả JVM native debug, proxy, APM và SIEM, bật có thời hạn và xử lý leak theo incident response. Một regex hay JSON encoder đơn lẻ không thể bảo đảm bí mật.

## 17. Tài liệu tham khảo

- [Spring Security – Servlet Architecture / Logging](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain DEBUG/TRACE và 401/403 diagnostics.
- [Spring Security – Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): OpenSAML/Saml2Authentication flow và SAMLResponse handling.
- [Spring Boot 3.5 – Logging](https://docs.spring.io/spring-boot/3.5/how-to/logging.html): logging.level, Logback/logback-spring.xml.
- [Oracle Java 17 – Troubleshooting Security](https://docs.oracle.com/en/java/javase/17/security/troubleshooting-security.html): Java security debug flags.
- [Oracle JGSS Debugging Guide](https://docs.oracle.com/en/java/javase/24/security/troubleshooting-security.html): Kerberos/JGSS/JAAS debug and cautions, verify runtime version.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): sensitive data to exclude, log injection và event schema.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): không log raw session IDs, correlation.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): authentication failures/privacy.
- [SLF4J Manual](https://www.slf4j.org/manual.html): SLF4J APIs, MDC.
- [Java 17 javax.crypto.Mac API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): HmacSHA256 pseudonymous tagging.