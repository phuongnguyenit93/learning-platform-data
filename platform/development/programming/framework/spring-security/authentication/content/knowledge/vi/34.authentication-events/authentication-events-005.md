# Thiết kế nhật ký đăng nhập và theo dõi thiết bị, phiên liên quan trong Spring Security

> **Phạm vi:** Xây dựng audit trail cho xác thực người dùng, quản lý thiết bị và các phiên liên quan trên Spring Boot 3 / Spring Security 6.x (Servlet, Java 17+). Trọng tâm là **ghi đúng sự kiện, liên kết các lần đăng nhập và phiên mà không làm lộ credential**, phân biệt tín hiệu thiết bị với bằng chứng danh tính, quản lý vòng đời session và kiểm thử khả năng theo dõi sự cố. Một nhật ký an toàn phải hữu ích cho điều tra và người dùng, nhưng không được trở thành kho chứa password, JWT, cookie phiên hay dữ liệu định danh không cần thiết.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ biết:

1. Phân biệt **thử xác thực**, **xác thực thành công ở provider**, **hoàn tất MFA**, **tạo/luân chuyển phiên**, **đăng xuất**, **hết hạn** và **thu hồi phiên**.
2. Thiết kế schema audit có event ID, timestamp UTC, loại sự kiện, outcome, actor/subject, correlation ID, method/factor, nguồn mạng, device reference và session reference với mức dữ liệu tối thiểu.
3. Nắm rõ sự khác biệt giữa **identity người dùng**, **thiết bị quan sát được**, **thiết bị đã được liên kết** và **HTTP session / access token**.
4. Tận dụng `AuthenticationSuccessEvent`, `AbstractAuthenticationFailureEvent`, success/failure handler, `HttpSessionEventPublisher`, `SessionRegistry` và session events của Spring Security đúng mục đích.
5. Tạo bản ghi tương quan an toàn từ session ID bằng HMAC có secret tách biệt; **không ghi raw `JSESSIONID`**, access token hoặc cookie vào log.
6. Phân biệt tính năng **xem lịch sử đăng nhập**, **danh sách phiên đang hoạt động**, **đăng xuất thiết bị khác** và **cảnh báo đăng nhập bất thường**.
7. Kiểm thử hành vi trong hệ thống nhiều node, sự kiện đến trễ/lặp, logout hoặc revoke không đồng bộ, dữ liệu nhạy cảm và luồng đăng nhập nhiều yếu tố.

**Bài toán cốt lõi:** Không phải mọi authentication success đều tạo session mới, không phải mọi HTTP session đều chứng minh login đầy đủ, và không phải mọi User-Agent/IP mới đều có nghĩa là thiết bị mới. Log muốn đáng tin phải diễn đạt **sự kiện gì đã thực sự xảy ra**, tại boundary nào, với mức độ chắc chắn nào.

## 2. Threat model: ghi log để bảo vệ chứ không để lộ thêm

Audit đăng nhập giúp phát hiện credential stuffing, brute-force, account takeover, session hijacking, login từ nguồn bất thường và sự kiện khôi phục MFA trái phép. Tuy nhiên chính hệ thống logging có thể bị khai thác:

| Rủi ro | Ví dụ | Cơ chế chống |
| --- | --- | --- |
| **Credential leak qua log** | Ghi header `Cookie`, `Authorization`, password, OTP hoặc raw session ID | Redaction theo allowlist, không log toàn request |
| **Log injection** | User-Agent có CRLF hoặc control characters để giả tạo dòng audit | Encode/sanitize input trước khi serialize |
| **Account enumeration** | Log và response công khai làm lộ username tồn tại hay bị khóa | Dùng outcome nội bộ đã phân quyền, response công khai chung |
| **Tracking quá mức** | Gắn fingerprint cố định xuyên nhiều website hoặc giữ IP thô vô hạn | Data minimization, retention, mục đích và quyền xem rõ ràng |
| **Session correlation sai** | Đổi session ID sau login nhưng log xem là hai người dùng | Ghi liên kết rotated old/new refs theo một sự kiện đã xác minh |
| **Sự kiện bị nhân đôi** | Ghi success tại AuthenticationProvider và handler thành hai login | Event ID, phân biệt event type, dedupe |
| **Mất audit khi queue đầy** | Ứng dụng báo thành công nhưng không thể truy lịch sử bảo mật quan trọng | Durable queue/outbox, error budget, backpressure |
| **Sửa/xóa audit trái phép** | Attacker chiếm admin rồi xóa log login của mình | Kho append-only/immutability, least privilege, phân tách quyền |
| **DoS vào audit pipeline** | Bot spam username, sinh vô hạn log hoặc notification | Quota, sampling chỉ cho telemetry ít quan trọng, giữ audit cần thiết |
| **Session revoke chưa hiệu lực** | UI nói “đã đăng xuất thiết bị” nhưng store khác vẫn chấp nhận session | Revoke authoritative store, kiểm chứng nhiều instance |

**Không dùng logging để thay thế authorization.** Một cảnh báo “thiết bị lạ” không đủ để chặn kẻ tấn công nếu session/token vẫn hợp lệ; phải có quy trình step-up, revoke hoặc risk decision được thực thi tại boundary bảo mật.

## 3. Mỗi từ “đăng nhập” có thể chỉ một sự kiện khác

Các mốc nên đặt tên riêng:

| Event type gợi ý | Sự kiện thực | Không được suy diễn |
| --- | --- | --- |
| `AUTH_ATTEMPT_OBSERVED` | Server/gateway thấy một yêu cầu thử xác thực | Chưa biết username có tồn tại |
| `AUTH_PROVIDER_SUCCEEDED` | `AuthenticationManager`/provider xác minh một cơ chế thành công | Chưa chắc MFA hoàn tất hay session được phát |
| `AUTH_PROVIDER_FAILED` | Một authentication attempt bị từ chối | Chưa chắc sai password; có thể account locked/outage |
| `MFA_CHALLENGE_STARTED` | Một thử thách yếu tố 2 được tạo | Chưa có chứng cứ yếu tố 2 |
| `MFA_VERIFIED` | Factor 2 được xác minh và state chống replay commit | Chưa chắc session được lưu thành công |
| `LOGIN_COMPLETED` | Chính sách xác thực đủ factor và ứng dụng sẵn sàng cấp quyền | Chưa đủ để khẳng định client nhận được cookie |
| `SESSION_CREATED` | Session được tạo trong servlet/session store | Có thể là anonymous session trước login |
| `SESSION_ID_ROTATED` | ID thay khi chống session fixation | Không phải một thiết bị mới |
| `SESSION_AUTHENTICATED` | Session chứa security context hợp lệ theo policy | Khác với sự kiện tạo session thuần túy |
| `SESSION_ACTIVITY_OBSERVED` | Request hợp lệ gắn với một session đã có | Không phải lần login mới |
| `LOGOUT_REQUESTED` | Nhận yêu cầu logout hợp lệ | Chưa chắc mọi state bên ngoài đã thu hồi |
| `SESSION_REVOKE_REQUESTED` | User/admin yêu cầu ngừng một phiên | Chưa chứng minh toàn cụm đã từ chối session |
| `SESSION_REVOKED` | Backend authoritative store đã vô hiệu phiên | Request in-flight có thể đã bắt đầu trước đó |
| `SESSION_DESTROYED` / `SESSION_EXPIRED` | Container/store báo session không còn hoạt động | Lý do kết thúc có thể cần xác định từ nguồn khác |
| `DEVICE_REMEMBERED` / `DEVICE_FORGOTTEN` | Ứng dụng đăng ký/xóa một thiết bị nhớ với sự chấp thuận | Không đồng nghĩa đã xác thực sinh trắc/khóa phần cứng |
| `RISK_ALERT_RAISED` | Bộ phân tích phát tín hiệu nghi ngờ | Là chỉ báo, không phải bằng chứng compromise |

**Phân biệt “authentication success” và “login completed”:** Spring `AuthenticationSuccessEvent` được phát ở tầng cơ chế xác thực khi cấu hình publisher. Nó có thể xảy ra khi còn bước TOTP, khi xử lý HTTP Basic cho từng request hoặc khi một custom flow trả authentication mà chưa lưu session. Muốn audit “login thành công và phiên sẵn sàng”, cần thêm event ở **chính điểm ứng dụng biết toàn bộ flow đã hoàn tất**, không lấy riêng provider success để suy đoán.

Với OAuth2/OIDC, IdP còn có login/SSO session riêng và ứng dụng có session local riêng. Đăng xuất local **không chắc** đã đăng xuất IdP hoặc thu hồi mọi refresh token; log phải phân biệt kết quả thực tế của từng hệ.

## 4. Mô hình ba đối tượng: account, device, session

~~~text
                     ACCOUNT (user_id)
                         |
               +---------+-----------+
               |                     |
         DEVICE RECORD A        DEVICE RECORD B
         (nếu ứng dụng          (nếu ứng dụng
          thực sự quản lý)        thực sự quản lý)
               |                     |
       +-------+-------+             +-------+
       |               |                     |
   SESSION S1       SESSION S2            SESSION S3
   browser A        browser A            mobile B
   các tab chung    profile khác         hoặc client token
       |
       +-- AUTH ATTEMPTS / MFA EVENTS / RISK SIGNALS / ACTIVITY
~~~

Một account có thể có nhiều device và nhiều session. Một browser profile có thể có nhiều session do logout/login hoặc cookie bị xóa. Nhiều tab cùng browser profile thường **dùng chung cookie phiên**, vì thế “3 tab mở” **không** đồng nghĩa 3 thiết bị hay 3 concurrent sessions. Một phiên có thể thay ID sau login/reauth mà vẫn là cùng hành trình xác thực.

### Account/user identity

- Trước xác thực, username/email là **claim do client đưa** và có thể sai hoặc không tồn tại; lưu fingerprint có phân quyền, không gắn như một `user_id` đã xác minh.
- Sau xác thực, dùng subject ID bất biến của ứng dụng (hoặc issuer + subject đối với OIDC) làm identity tham chiếu. Không dựa vào email làm khóa toàn cục nếu email có thể đổi hay trùng giữa tenant.
- Trong hệ multi-tenant, identity ổn định nên gồm tenant/issuer; không cho phép client tự gửi tenant ID để nối lịch sử người khác.

### Device

- `User-Agent`, IP, ASN, phiên bản OS/browser hoặc vị trí suy đoán là **tín hiệu quan sát được**, dễ sai, đổi thường xuyên và có thể bị giả.
- Device ID do ứng dụng phát trong cookie có thể cho UX “thiết bị quen thuộc”, nhưng một cookie bị sao chép cũng có thể bị giả mạo. Không xem nó là bằng chứng sở hữu thiết bị hoặc thay password/MFA.
- WebAuthn/FIDO2 credential hoặc khóa thiết bị có proof of possession mới có thể hỗ trợ **liên kết mật mã** nếu được enrollment và verify đúng; vẫn cần policy, revocation và risk assessment.
- “Thiết bị đã nhớ” khác “thiết bị được tin cậy đủ bỏ MFA”; quyết định giảm step-up đòi cơ chế riêng, TTL, user consent và security review.

### Session

- `HttpSession` trong Servlet thường được tham chiếu bởi cookie `JSESSIONID` do container quản lý. Cookie là **bearer secret**, không phải ID hiển thị trong log/UI.
- Trong Spring Security, `SecurityContext` có `Authentication` (principal, authorities, trạng thái). Một session có thể tồn tại trước login, chưa có authentication hoặc chỉ có một phần flow MFA.
- API stateless dùng access token/JWT không có cùng lifecycle với HTTP session; token có `jti`/issuer/subject và expiry riêng, revocation của JWT tự chứa phải được thiết kế riêng. Không đưa JWT raw vào audit.

## 5. Thiết kế schema audit tối thiểu, nhất quán và có ngữ nghĩa

Một bản ghi audit nên có các nhóm trường sau (tất cả dữ liệu được kiểm tra trước khi ghi):

| Trường | Dữ liệu gợi ý | Quy tắc |
| --- | --- | --- |
| `event_id` | UUID/ULID unique do server cấp | Dedupe và đối chiếu bất biến |
| `event_type` | Enum như `AUTH_PROVIDER_FAILED` | Taxonomy versioned, không nhận tự do từ client |
| `schema_version` | 1, 2... | Cho phép nâng cấp consumer |
| `occurred_at` | Thời gian xảy ra theo UTC `Instant` | Không tin client clock |
| `recorded_at` | Khi hệ thống audit thực sự nhận | Đo queue lag và event đến muộn |
| `service`/`environment`/`region` | Định danh bounded do server cấp | Correlation đa dịch vụ, cardinality thấp |
| `actor_ref` | Định danh đã xác thực/pseudonym | Null khi chưa biết user |
| `submitted_identifier_ref` | HMAC fingerprint input login nếu cần | Không phải user ID đã xác minh |
| `tenant_ref` | Tenant có nguồn tin cậy | Không lấy raw tenant param để xác lập quyền |
| `outcome`/`reason_category` | SUCCESS, DENIED, INFRA_ERROR... | Reason nội bộ, tránh raw exception |
| `auth_method`/`factor` | PASSWORD, OIDC, WEBAUTHN, TOTP... | Đánh dấu mức xác minh thực sự |
| `attempt_ref` | ID cho một login attempt / MFA journey | Liên kết bước prelogin -> postlogin |
| `session_ref` | HMAC/surrogate không phải raw cookie | Không dùng làm bearer credential |
| `previous_session_ref` | Chỉ khi session ID rotation được kiểm chứng | Liên kết trước–sau |
| `device_ref` | Device record/app-issued reference nếu có | Bằng chứng thiết bị cần phân loại |
| `source_network` | IP đã rút gọn/HMAC, ASN nếu cần | Tuân thủ quy định privacy/retention |
| `user_agent_family` | Browser/OS loại đã giảm chi tiết | Không cần log toàn User-Agent |
| `request_id`/`trace_id` | Trace do gateway/backend phát | Không chứa query secret hoặc PII |
| `action`/`confidence` | Allow, step-up, alert; low/medium/high | Không coi tín hiệu suy luận là sự thật |
| `causation_event_id` | Event dẫn tới event mới | Dò chuỗi hành động và chống vòng lặp |

**Schema có thể lưu dưới JSON lines, bảng audit có index hoặc sự kiện gửi qua message broker.** Không nhất thiết mỗi sản phẩm cần mọi cột. Chỉ giữ dữ liệu thật sự phục vụ phòng vệ, điều tra, hỗ trợ user, compliance và vận hành. Nên chuẩn hóa `event_type`, `reason_category` bằng enum hữu hạn để tránh log injection và bùng nổ metric.

### Một sự kiện audit đã giảm nhạy cảm

~~~json
{
  "schema_version": 1,
  "event_id": "3c9b2e18-248b-4a40-927b-9009a8acbc67",
  "event_type": "SESSION_AUTHENTICATED",
  "occurred_at": "2026-11-06T09:10:00Z",
  "service": "customer-portal",
  "environment": "prod",
  "actor_ref": "usr_ea24c9",
  "attempt_ref": "att_f712",
  "session_ref": "sr_47a11ad7c29a9b7234e98fc70225d3aa",
  "device_ref": "dev_a5c1",
  "auth_method": "PASSWORD_TOTP",
  "outcome": "SUCCESS",
  "source_network": "203.0.113.0/24",
  "user_agent_family": "Chrome",
  "request_id": "req_2b18"
}
~~~

Các ID, địa chỉ mạng và thời gian trên là **giá trị tài liệu minh họa**, không phải log thật. Dữ liệu IP thuộc dải tài liệu TEST-NET-3. Một request log thực tế có thể không biết device_ref/actor_ref: phải để null, **không tự dựng** ra danh tính hoặc “thiết bị” từ một header không đáng tin.

### Không ghi trực tiếp những dữ liệu nào?

- Password, mã TOTP/HOTP, recovery code, passkey private key, PIN, security answer.
- Cookie `JSESSIONID`, `Authorization` header, access/refresh token, JWT đầy đủ, API key, CSRF token hoặc raw session ID.
- Toàn bộ `Authentication.toString()`, `SecurityContext`, request body login, exception chứa credentials, stack trace vào kênh người dùng.
- URL query có token/reset link; raw User-Agent có newline/control characters; địa chỉ IP hoặc địa lý chi tiết khi không cần.
- Trường PII nhạy cảm chỉ để tăng cardinality metric hoặc làm “thống kê thiết bị” không có mục đích rõ.

OWASP khuyến nghị có cơ chế correlation cho session **không chứa raw session ID**; có thể dùng salted hash hoặc HMAC thay thế. HMAC với audit key bí mật giúp tránh lộ raw session identifier và chống việc đoán ID từ log tốt hơn một phép hash không có key; vẫn phải giới hạn quyền truy cập audit ref và thời hạn lưu.

## 6. Nhiều loại ID, không được trộn lẫn

| ID | Sinh tại đâu | Dùng để làm gì | Có được log nguyên văn? |
| --- | --- | --- | --- |
| `user_id`/`subject` | User store hoặc IdP đáng tin | Danh tính đã xác minh | Tùy quy định; thường pseudonym hóa |
| `attempt_id` | Server lúc bắt đầu flow | Liên kết authentication và MFA | Có thể nếu random, không có quyền truy cập |
| `request_id` | Trusted ingress/server | Một HTTP request | Thường có thể nếu kiểm soát format |
| `trace_id` | Tracing framework/gateway | Nhiều span/service | Có thể nếu loại bỏ trace baggage nhạy cảm |
| Raw `HttpSession.getId()` | Servlet container/session store | Xác thực và định tuyến session | **Không** trong audit/log |
| `session_ref` | HMAC/audit mapping | Tương quan nhiều event của một session | Có, nhưng là dữ liệu audit hạn chế |
| `device_id` | Server/credential enrollment | Nhóm phiên có cùng device record | Có điều kiện, không thay xác thực |
| `jti`/token family ref | Issuer/token service | Nhận diện token phát hành | Tùy policy, không log raw bearer token |

**Session fixation protection:** Sau login, Spring Security có thể đổi session ID. `session_ref` tính từ ID cũ sẽ khác ID mới; muốn nối log cần một sự kiện `SESSION_ID_ROTATED` có `previous_session_ref` và `session_ref` mới. Chỉ tạo liên kết này từ dữ liệu server/container và bảo đảm cả hai refs thuộc cùng session transition, không theo claim do browser cung cấp.

**Lưu ý bảo vệ HMAC key:** Audit HMAC key lưu qua KMS/secret manager, không cùng credential signing key của JWT hoặc token khác; có version, quyền truy cập tối thiểu và kế hoạch rotate. Dùng đủ độ dài digest (ví dụ 128 bit trở lên cho correlation trong giới hạn dữ liệu) để giảm trùng nhau, và tính theo **raw session ID chỉ trong bộ nhớ server**, không xuất raw ra event. Khi rotate audit key, ref cũ/mới có thể khác; cần thiết kế phiên bản hoặc giai đoạn chuyển đổi phù hợp với retention. HMAC session ref không dùng thay session cookie để đăng nhập.

## 7. Java 17 chạy độc lập: tham chiếu phiên an toàn và log injection

Đây là ví dụ JDK 17 thuần, minh họa cách tạo **HMAC-SHA256 correlation reference** cho phiên mà không in raw ID, liên kết các sự kiện trước/sau khi ID đổi, và chặn newline/control characters đơn giản. Khóa HMAC và session IDs trong chương trình là **dữ liệu giả để kiểm thử**, không phải cấu hình production.

Tạo tệp `AuthAuditDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class AuthAuditDemo {
    record AuditEvent(String type, String userRef,
                      String sessionRef, Instant occurredAt) {}

    static String sessionReference(String rawSessionId, byte[] auditKey)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(auditKey, "HmacSHA256"));
        byte[] digest = mac.doFinal(
                rawSessionId.getBytes(StandardCharsets.UTF_8));
        // 16 byte (128 bit) đầu đủ cho demo correlation.
        return "sr_" + HexFormat.of().formatHex(digest).substring(0, 32);
    }

    static String sanitize(String untrusted) {
        if (untrusted == null) {
            return "";
        }
        return untrusted.replace('\r', '_')
                .replace('\n', '_')
                .replace('\t', '_');
    }

    public static void main(String[] args) throws Exception {
        byte[] auditKey = "demo-only-audit-key-not-for-production"
                .getBytes(StandardCharsets.UTF_8);
        String originalSessionId = "session-secret-old";
        String rotatedSessionId = "session-secret-new";

        String oldRef = sessionReference(originalSessionId, auditKey);
        String newRef = sessionReference(rotatedSessionId, auditKey);

        List<AuditEvent> events = List.of(
                new AuditEvent("AUTH_PROVIDER_SUCCEEDED", "u_17",
                        oldRef, Instant.parse("2026-11-06T00:00:00Z")),
                new AuditEvent("SESSION_ID_ROTATED", "u_17",
                        newRef, Instant.parse("2026-11-06T00:00:01Z")),
                new AuditEvent("LOGOUT_COMPLETED", "u_17",
                        newRef, Instant.parse("2026-11-06T00:05:00Z"))
        );

        System.out.println("events: " + events.size());
        System.out.println("rotation changed reference: "
                + !oldRef.equals(newRef));
        System.out.println("logout same reference: "
                + events.get(1).sessionRef().equals(
                        events.get(2).sessionRef()));
        System.out.println("raw session absent: "
                + events.stream().noneMatch(e ->
                        e.sessionRef().contains("session-secret")));
        System.out.println("injection sanitized: "
                + sanitize("Chrome\r\nrole=admin")
                        .equals("Chrome__role=admin"));
        System.out.println("timestamps ordered: "
                + events.get(0).occurredAt().isBefore(
                        events.get(1).occurredAt()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AuthAuditDemo.java
java AuthAuditDemo
~~~

Stdout chính xác:

~~~text
events: 3
rotation changed reference: true
logout same reference: true
raw session absent: true
injection sanitized: true
timestamps ordered: true
~~~

**Giải thích:**

1. Hai raw session IDs khác nhau tạo hai HMAC refs khác nhau. Trong audit thật, cần thêm một field `previous_session_ref` vào event thay ID để nối S1 -> S2; chương trình chỉ minh họa việc ID ref đổi.
2. Sự kiện logout và event rotated sau đó cùng dùng ref mới, nên có thể tương quan mà không cần log cookie.
3. Hàm `sanitize` tránh CR/LF/tab tạo dòng log giả trong ví dụ; production cần **structured logging với encoder đúng**, giới hạn chiều dài, Unicode/control-character policy và validation cho mọi trường input. Không dùng một phép replace nhỏ làm lớp bảo vệ duy nhất.
4. Code không tạo, cấp, validate hoặc revoke session thật; `sessionReference` chỉ dùng cho **audit correlation**. Audit HMAC key cố định trong demo phải được thay bằng KMS/secret manager, có version và rotation khi vận hành thật.
5. Thời gian sự kiện lấy từ `Instant.parse` để output deterministic; ứng dụng production phải lấy `Clock`/server time tin cậy và có cả `recorded_at` để đo ingestion delay.

## 8. Event flow: từ request login đến session thực sự hoạt động

Một luồng username/password + TOTP trong Servlet:

~~~text
POST /login
    |
    +-- REQUEST_OBSERVED (attempt_ref mới)
    |
    +-- AuthenticationManager
           |
           +-- BadCredentials -> AUTH_PROVIDER_FAILED, no login session
           |
           +-- password OK -> AUTH_PROVIDER_SUCCEEDED (factor=PASSWORD)
                                  |
                                  v
                           MFA_CHALLENGE_STARTED
                                  |
                            correct TOTP + atomic replay update
                                  |
                                  v
                           MFA_VERIFIED
                                  |
                         auth/authorities đủ policy
                                  |
                      session fixation protection
                      session ID có thể thay đổi
                                  |
                     SecurityContext persisted
                                  |
                                  v
                          SESSION_AUTHENTICATED
                                  |
                  +---------------+----------------+
                  |               |                |
                activity        logout       expiry/revoke
                  |               |                |
          SESSION_ACTIVITY   LOGOUT_*      SESSION_DESTROYED
~~~

Tất cả mốc là mô hình **event semantics cho ứng dụng**, không phải mỗi mũi tên sẽ tự động phát một Spring event có cùng tên. Spring chỉ có một số event sẵn; các event `MFA_VERIFIED`, `SESSION_AUTHENTICATED`, `DEVICE_REMEMBERED` là sự kiện nghiệp vụ bảo mật **ứng dụng phải tự phát** sau khi transaction tương ứng thành công.

Một provider thành công có thể xuất hiện **nhiều lần** trong một login (password, OTP, OAuth2 callback, remember-me hoặc token authentication khác), hoặc không tạo local HTTP session trong REST stateless. Đừng đếm số `AuthenticationSuccessEvent` bằng số “người đăng nhập thành công” mà không phân biệt flow và de-duplication.

### Hai loại thời gian thường bị bỏ quên

- `occurred_at`: thời điểm bước xác thực/session xảy ra trên node nguồn.
- `recorded_at`: thời điểm audit sink xác nhận đã lưu sự kiện.

Khi dùng queue, `recorded_at` có thể trễ nhiều giây/phút so với occurred. Các node có clock skew, vì vậy truy vết nên dùng `attempt_ref`, `causation_event_id` và thứ tự chuyển trạng thái, không chỉ sort UTC timestamp rồi khẳng định nguyên nhân.

## 9. Spring Security: bắt sự kiện provider thành công/thất bại

Spring Security 6.x hỗ trợ `AuthenticationEventPublisher`. `DefaultAuthenticationEventPublisher` có thể phát `AuthenticationSuccessEvent` và các subclass của `AbstractAuthenticationFailureEvent` dựa trên ngoại lệ. Khi xây `AuthenticationManager` riêng, phải chắc chắn publisher đã được gắn; không mặc định mọi custom authentication path sẽ phát event.

Bean publish nếu ứng dụng chưa có publisher phù hợp:

~~~java
package example.security;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;

@Configuration
public class AuthenticationEventConfiguration {

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationEvents) {
        return new DefaultAuthenticationEventPublisher(applicationEvents);
    }
}
~~~

Listener khái niệm: nhận **authentication object** từ Spring, chuyển thành các trường đã giảm nhạy cảm rồi đưa vào audit sink. Mảnh code này chạy trong dự án có các bean `AuditWriter`/`IdentityReferences` thực tế, **không phải chương trình `javac` chạy độc lập**:

~~~java
package example.security;

import java.time.Instant;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.stereotype.Component;

@Component
public final class AuthenticationAuditListener {
    private final AuditWriter writer;
    private final IdentityReferences identities;

    public AuthenticationAuditListener(
            AuditWriter writer, IdentityReferences identities) {
        this.writer = writer;
        this.identities = identities;
    }

    @EventListener
    public void success(AuthenticationSuccessEvent event) {
        String subject = identities.fromVerified(
                event.getAuthentication());
        writer.append(new AuditRecord("AUTH_PROVIDER_SUCCEEDED",
                subject, "SUCCESS", Instant.now()));
    }

    @EventListener
    public void failure(AbstractAuthenticationFailureEvent event) {
        String submitted = identities.fromSubmitted(
                event.getAuthentication());
        String reason = reasonCategory(event.getException());
        writer.append(new AuditRecord("AUTH_PROVIDER_FAILED",
                submitted, reason, Instant.now()));
    }

    private static String reasonCategory(AuthenticationException error) {
        if (error instanceof BadCredentialsException) {
            return "BAD_CREDENTIALS";
        }
        if (error instanceof LockedException) {
            return "LOCKED";
        }
        return "AUTH_ERROR";
    }

    public record AuditRecord(
            String type, String subjectRef, String result, Instant at) {}

    public interface AuditWriter {
        void append(AuditRecord record);
    }

    public interface IdentityReferences {
        String fromVerified(Authentication authentication);
        String fromSubmitted(Authentication authentication);
    }
}
~~~

**Điều kiện để dùng đúng:**

- `IdentityReferences.fromVerified` lấy stable user ID đã được xác minh hoặc pseudonym phù hợp. `fromSubmitted` phải biến username chưa xác minh thành một fingerprint/HMAC có key và TTL phù hợp; không khẳng định account tồn tại hoặc log raw user input.
- Không dùng `event.getAuthentication().toString()`: object có thể chứa credentials, request details, principal attributes hoặc dữ liệu cá nhân.
- `reasonCategory` chỉ ánh xạ các loại lỗi cần phân tích, không ghi `exception.getMessage()`; lỗi backend nên phân loại riêng nếu contract có thể phân biệt. Các exception custom có thể cần `DefaultAuthenticationEventPublisher.setAdditionalExceptionMappings(...)` vì mapping mặc định là **exact exception-class match**, không tự bao phủ mọi subclass.
- `AuthenticationSuccessEvent` không chứa đầy đủ request/session/device metadata trong mọi flow. Thu thập context có kiểm soát ở filter/gateway hoặc success handler, rồi gắn bằng `attempt_ref`/trusted request context; **không** đoán IP/device từ `Authentication.getName()`.
- Tránh cấu hình nhiều publisher hoặc listener cùng viết một event type gây double-count. Với custom `ProviderManager` và parent manager, phải xem đường publish để tránh event trùng.
- `@EventListener` mặc định có thể chạy đồng bộ với nơi phát event. `AuditWriter.append` không được chặn login lâu vì mạng SIEM; dùng kiến trúc durable outbox/queue có giới hạn và contract rõ cho sự kiện quan trọng.
- Trên REST stateless, một authentication event có thể sinh cho **mỗi request** chứ không phải mỗi lần user mở trình duyệt. Cần tách metrics success của HTTP request ra khỏi login session counts.

## 10. Spring Security: success/failure handler và HTTP context

`AuthenticationSuccessHandler`/`AuthenticationFailureHandler` ở form login biết request/response, có thể thấy remote address, headers đã được chọn lọc, CSRF/redirect/correlation metadata và flow outcome. Điều này bổ sung cho listener ở provider layer.

Đừng dùng success handler chỉ để ghi “session đã tạo” **trước khi** session fixation, lưu `SecurityContext` hoặc MFA step-up hoàn tất. Nếu một custom success handler thay handler mặc định, trách nhiệm quản lý `SecurityContext`/session và redirect có thể thay đổi; cần test theo phiên bản framework thực tế. Bản thân sự kiện “handler được gọi” chỉ chứng minh handler bắt đầu xử lý, không phải browser chắc chắn nhận cookie hay user đã dùng session.

Có thể đặt một `attempt_ref` ngẫu nhiên do server tạo trong pre-auth flow, rồi chuyển nó qua các bước MFA và vào session-level audit khi đăng nhập hoàn tất. Cần chống session fixation, CSRF, replay và bảo vệ scope của attempt reference; đừng tin một query parameter do client gửi để nối hai user khác nhau. Trong OIDC, dùng `state`/nonce đúng protocol, **không tái sử dụng chúng làm event label công khai** hoặc in ra log.

**Login failure handler** nên map lỗi ra thông báo công khai chung, trong khi audit giữ reason category có kiểm soát. `BadCredentialsException` khác `LockedException` và `AuthenticationServiceException`; ghi sai loại sự kiện có thể khiến hệ thống false-positive account takeover hoặc làm ẩn outage của IdP/LDAP.

### Điểm phát custom event SESSION_AUTHENTICATED

Ở cuối flow, chỉ emit khi:

1. Danh tính và toàn bộ factors bắt buộc đã được xác minh.
2. Session fixation protection (nếu dùng) được xử lý và session ID cuối cùng đã biết.
3. `SecurityContextRepository` lưu security context phù hợp và backend nhận commit; với Spring Security 6, custom auth có thể cần **explicit saveContext(...)** để tồn tại qua request.
4. Quyết định cấp quyền/TTL/remember-me theo policy đã áp dụng và event có actor_ref, session_ref mới được tính từ server-side ID.
5. Nếu event emit trước khi commit và commit thất bại, phải ghi outcome `FAILED` hoặc dùng transactional outbox để tránh phantom login audit.

**Không dùng cookie value trong log.** Nếu cần test correlation, tạo HMAC sessionRef tại trusted server side; không đưa raw ID ra message broker.

## 11. Quản lý vòng đời session và concurrency

Spring Security Servlet có `HttpSessionEventPublisher` để chuyển các lifecycle event của servlet session thành Spring application events, `SessionRegistry`/`SessionRegistryImpl` cho concurrent session control và `SessionInformation` mô tả phiên. Ví dụ cấu hình cho ứng dụng form login có session:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class SessionSecurityConfiguration {

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error", "/assets/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionFixation(fix -> fix.changeSessionId())
                        .maximumSessions(3)
                        .maxSessionsPreventsLogin(false))
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

**Ý nghĩa và giới hạn:**

- `sessionFixation(...changeSessionId())` thay ID theo cơ chế Servlet khi đăng nhập để chống session fixation; không có nghĩa thay ID là tạo một thiết bị mới. Server có thể nhận `SessionIdChangedEvent` nếu lifecycle publisher được cấu hình đúng.
- `maximumSessions(3)` đặt giới hạn minh họa 3 phiên concurrent theo user; mặc định khi vượt ngưỡng thường expire session cũ, tùy `maxSessionsPreventsLogin`. Con số phải theo policy và kiểm thử nhiều thiết bị. Với custom authentication filter, có thể phải gắn session authentication strategy thủ công.
- `HttpSessionEventPublisher` hỗ trợ thông báo session destroyed/ID changed; **không** đảm bảo mọi kết thúc phiên (browser đóng tab, network mất, JWT hết hạn) phát event ngay.
- `SessionRegistryImpl` mặc định dựa trên bộ nhớ của JVM. Trong cụm nhiều instance, muốn danh sách phiên/trạng thái revoke **toàn cụm**, phải thiết kế repository/registry chia sẻ hoặc tích hợp Spring Session phù hợp, không coi local registry là authoritative.
- Nếu dùng custom `UserDetails` làm principal, cần `equals()/hashCode()` nhất quán nếu registry dựa trên object principal, nếu không có thể tính sai số session theo user.
- `SessionInformation.expireNow()` đánh dấu session expired trong registry; hiệu lực thực tế thường được kiểm tra ở request sau bởi Spring filter. Đừng hứa “đã terminate mọi request đang chạy” nếu chưa có cơ chế đóng/revoke ở backend. Khi dùng distributed session store, xóa record authoritative và propagate invalidation theo thiết kế.
- Nếu dùng OAuth2 Resource Server/JWT stateless, `SessionRegistry` HTTP không quản lý access token client như session cookie; cần thiết kế token revocation/short TTL/introspection riêng.

### Những sự kiện session khác nhau

`SessionCreationEvent`, `SessionDestroyedEvent`, `SessionIdChangedEvent` và các kiểu HTTP tương ứng thể hiện lifecycle từ container, không trực tiếp cho biết một user đã hoàn thành MFA. Khi nhận session-destroyed, có thể chưa biết lý do là logout, timeout, concurrent expiry hay admin revoke nếu không giữ causal event riêng. Hãy ghi `LOGOUT_REQUESTED`/`SESSION_REVOKE_REQUESTED` và đối chiếu với destruction để có reason đáng tin.

Spring Security có sự kiện logout từ flow framework khi cấu hình phù hợp, nhưng logout success không phải bằng chứng IdP SSO session, remember-me token và mọi client token đã bị thu hồi. Ghi rõ scope **LOCAL_SESSION_LOGOUT** khi chỉ xóa phiên địa phương.

## 12. Danh sách “Thiết bị và phiên của tôi” cho người dùng

Một giao diện tài khoản hữu ích có thể hiển thị:

| Cột trong UI | Nguồn/ý nghĩa | Không nên làm |
| --- | --- | --- |
| Thiết bị/trình duyệt | Browser family, OS family suy luận từ User-Agent | Khẳng định chính xác model/owner chỉ từ UA |
| Thời điểm đăng nhập | `SESSION_AUTHENTICATED` của session đó | Hiển thị provider success như login hoàn chỉnh |
| Lần hoạt động gần nhất | `SESSION_ACTIVITY_OBSERVED` đã được làm mới theo interval | Ghi update DB trên mọi pixel/API call |
| Vùng địa lý gần đúng | IP geolocation khi được phép và có độ tin cậy | Hiển thị vị trí chính xác đến địa chỉ nhà |
| Phiên hiện tại | So với sessionRef phía server của request đang xác thực | Tin `current=true` do client gửi |
| Thiết bị đã nhớ | Device record có enrollment/consent | Gán quyền cao chỉ vì đã thấy UA giống |
| Trạng thái | Active, expired, revoked, logged out, unknown | Giả “online realtime” khi chỉ có last-seen |
| Hành động | Đăng xuất phiên này, đăng xuất tất cả phiên khác, quên thiết bị | Chỉ xóa dòng UI/audit mà không revoke thật |

**Hai dữ liệu khác nhau: lịch sử và active sessions.** Lịch sử đăng nhập là chuỗi sự kiện đã xảy ra, kể cả phiên đã chết. Danh sách session đang hoạt động là view của authoritative session store/registry, cần đối chiếu TTL, expired flag và revocation. Một sự kiện login trong audit **không có nghĩa** session vẫn sống sau nhiều ngày.

### API gợi ý (do ứng dụng xây dựng)

| Endpoint | Chức năng | Biên bảo mật |
| --- | --- | --- |
| `GET /account/security/logins` | Đọc lịch sử login đã lọc theo user hiện tại | Chỉ subject đã xác thực, phân trang/retention |
| `GET /account/security/sessions` | Liệt kê phiên đang active từ registry/repository | Không xuất raw session IDs/tokens |
| `DELETE /account/security/sessions/{publicRef}` | Revoke một session đã được lookup theo opaque UI ref | Kiểm tra owner server-side, chống IDOR |
| `POST /account/security/sessions/revoke-others` | Thu hồi các phiên khác | Reauthentication/MFA theo policy, chống CSRF |
| `GET /account/security/devices` | Danh sách device records đã đăng ký | Trường suy đoán tách khỏi verified |
| `DELETE /account/security/devices/{deviceRef}` | Quên/revoke một remembered-device credential | Không tự revoke mọi session trừ khi policy yêu cầu |

Các URL này chỉ là thiết kế API cho ứng dụng, **không phải endpoint Spring Security tự phát sinh**. `publicRef` nên là UUID/surrogate random **không thể dùng để xác thực** và không trùng raw session cookie; server ánh xạ đến session đang sở hữu sau khi kiểm tra `user_id`. Một cookie session hiện tại bị chiếm có thể dùng để bấm “đăng xuất phiên khác”; hành động rủi ro cao nên yêu cầu **fresh authentication/MFA** trước khi revoke toàn bộ hoặc xóa device trust.

Để tránh CSRF, các hành động POST/DELETE quản trị phiên dựa vào cookie phải có bảo vệ CSRF theo đúng mô hình session của ứng dụng. Không đưa `sessionId` vào URL hoặc raw token vào response. Sau khi user bấm revoke, backend phải thực sự cập nhật session store/registry, không chỉ xóa row audit hoặc `device record`.

## 13. Sự kiện đăng nhập từ thiết bị “lạ” và cảnh báo

Thiết bị lạ là **khái niệm xác suất**, không tự là tấn công. Một browser vừa update, người dùng bật chế độ riêng tư, xóa cookie, đổi mạng 4G/Wi-Fi hoặc dùng VPN có thể tạo cùng tín hiệu như thiết bị mới. Ngược lại, attacker có thể sao chép User-Agent và cookie của thiết bị cũ.

### Một số tín hiệu có giá trị

- Login thành công sau chuỗi thất bại lớn hoặc nhiều IP.
- Session mới xuất hiện sau khi user vừa reset password/MFA.
- Hai phiên đăng nhập từ hai vùng không tương thích trong khoảng ngắn (**impossible travel** chỉ là tín hiệu không chắc).
- Device remembered cookie chưa từng thấy, hoặc device credential/attestation đã enrollment nhưng chứng cứ không hợp lệ.
- User-Agent/OS family thay đổi đáng kể, IP/ASN rủi ro, thời gian truy cập bất thường.
- Token reuse hoặc refresh token family có dấu hiệu replay.
- Bắt đầu nhiều session trong thời gian rất ngắn, thay đổi quyền và xuất dữ liệu nhạy cảm.

**Không tự đưa ra kết luận “user chắc chắn bị hack” từ một IP mới.** Risk engine phải có confidence, khả năng giải thích, hạn chế false positive, chính sách escalation và đường hỗ trợ. Đối với thao tác nhạy cảm, có thể step-up bằng TOTP/WebAuthn/passkey đã đăng ký, tạm hạn chế hành động hoặc yêu cầu reauthentication; không khóa account vĩnh viễn vì IP geolocation thiếu chính xác.

### Thiết kế thông báo

- Gửi cảnh báo đăng nhập mới sau khi **login thực sự hoàn thành**, không gửi email cho mọi `AUTH_PROVIDER_SUCCEEDED` trong flow MFA.
- Dùng nội dung hữu ích nhưng giảm nhạy cảm: thời gian, browser family, vùng gần đúng nếu cần, link vào trang quản lý phiên.
- Email link nên trỏ đến **trang bảo mật chính thức**, không chứa magic token dài hạn hoặc raw session. Không cho attacker đưa URL redirect tùy ý.
- Rate limit/deduplicate notifications; tránh bot kích hoạt hàng nghìn email bằng cách gửi password sai, và phải cân nhắc user chưa có session.
- Nếu người dùng chọn “không phải tôi”, bước tiếp theo phải **revoke/reauth theo đúng giao thức** rồi báo trạng thái; không chỉ ghi ticket hoặc đánh dấu thông báo đã đọc.
- Không dùng channel gửi thông báo đã bị attacker đổi mà không có audit/quy trình bảo vệ thay đổi email/phone.

## 14. Privacy, retention và phân quyền dữ liệu đăng nhập

Địa chỉ IP, lịch sử thiết bị, geolocation ước lượng, thời gian login và session correlations có thể tiết lộ hoạt động cá nhân. Do đó việc ghi log phải tuân thủ **mục đích rõ, tối thiểu hóa, hạn lưu, kiểm soát truy cập và pháp luật áp dụng**. Pseudonymized ID vẫn có khả năng liên kết/khôi phục thông qua hệ thống, không tự động trở thành dữ liệu vô danh.

### Tách ba kho theo mục đích

| Kho | Chứa dữ liệu gì | Người được truy cập |
| --- | --- | --- |
| Operational metrics | Tổng số auth success/failure, latency, event lag, error categories | SRE/Monitoring; cardinality thấp, không raw PII |
| Security audit | Actor refs, event type, session refs, reason, correlation, risk signals cần điều tra | Security/compliance với RBAC và audit mọi lần đọc |
| User-visible history | Login time, browser/OS family, location gần đúng và trạng thái | Chính chủ tài khoản, phân trang, không lộ session secret |

**Retention:** Đặt chính sách khác nhau cho raw network data, device observations, audit security events và aggregate metrics. Ví dụ “giữ audit 90 ngày” chỉ là một quyết định sản phẩm cần được phê duyệt, không phải chuẩn mặc định áp dụng mọi quốc gia. Một investigation/legal hold có thể có quy trình riêng theo pháp luật, nhưng không nên trở thành lý do giữ mọi địa chỉ IP vô thời hạn.

**Access control:** Nhân viên hỗ trợ không cần mặc định thấy IP đầy đủ hoặc session correlation của mọi user. Truy cập log nhạy cảm phải có permission, lý do, audit và alert khi đọc hàng loạt. Kiểm soát export/download, mã hóa at rest/in transit, retention và xóa dữ liệu theo chính sách.

**Privacy-by-design:** Đừng bật thu thập canvas fingerprint/fonts/installed plugins chỉ để viết “thiết bị này là iPhone”. Ưu tiên nguồn dữ liệu sẵn có với độ chi tiết phù hợp và consent/minimization, nêu rõ uncertainty thay vì làm người dùng tưởng geolocation chính xác tuyệt đối.

## 15. Pipeline audit đáng tin: durability, ordering, idempotency

Hệ thống production thường tách transaction xử lý login/session và pipeline audit:

~~~text
Spring Security / Authentication service
    |
    +-- emit structured event with server-owned event_id, actor_ref
    |
    +-- durable outbox / bounded queue (tùy criticality)
                   |
                   v
          Audit consumer / sanitizer
                   |
           +-------+----------+
           |                  |
     Append-only log      Risk analytics
           |                  |
      Indexed queries     Alerts / step-up
           |
     User session history view (filtered)
~~~

**Không làm việc nặng trong EventListener đồng bộ.** Truy vấn geolocation, gửi email, gọi SIEM hoặc format stack trace trên HTTP login thread làm chậm xác thực và tạo DoS khi backend audit chậm. Dùng queue có độ bền, bounded size, backpressure và idempotency, hoặc transactional outbox khi login phải gắn chặt với bằng chứng sự kiện.

### Những bất biến vận hành

1. **Không làm giả success:** Chỉ ghi `SESSION_AUTHENTICATED` sau khi trạng thái xác thực/session đã được commit theo contract. Nếu emit trước rồi commit thất bại, cần trạng thái outcome chính xác hoặc outbox cùng transaction.
2. **At-least-once => dedupe:** Message broker có thể chuyển cùng event nhiều lần. Sink dùng `event_id` làm khóa idempotency; không biến hai bản sao thành hai lần đăng nhập.
3. **Out-of-order:** Sự kiện logout có thể tới trước session-created do queue shard. Consumer xử lý `causation_event_id`/sequence, không tự “hồi sinh” session chỉ vì event đến trễ.
4. **Không xóa event lịch sử khi revoke:** Audit là dòng sự kiện append-only; active sessions là view có thể cập nhật theo trạng thái. Xóa login record để “đăng xuất” là sai ngữ nghĩa.
5. **Backpressure/failure policy:** Khi sink unavailable, phải có chính sách đã đánh giá rủi ro cho sự kiện bảo mật bắt buộc, không âm thầm drop; với metric phụ có thể sampling theo policy. Không retry vô hạn trong HTTP request.
6. **Access integrity:** Nơi lưu audit nên có append-only/immutable retention và phân quyền tách biệt; có log truy cập/chỉnh sửa cấu hình logging.
7. **Clock/trace:** Giữ UTC timestamp, received_at, correlation/causation ID và schema version; khi multi-region có skew, không suy luận thứ tự tuyệt đối chỉ từ timestamp.
8. **Sensitive fields:** Sanitize tại nguồn, hạn chế payload sau khi chuyển vào queue và kiểm tra redaction trước khi xuất log ra bên thứ ba.

### Metrics nhưng không cardinality explosion

Nên có nhãn cố định như `event_type`, `outcome`, `method`, `environment`, `region` và `service`. Không làm Prometheus label bằng `user_id`, `session_ref`, full IP, `attempt_ref` hay device fingerprint. Các ID ấy có thể được tìm trong audit indexed store với quyền hạn, không nên là chiều của time-series metrics.

## 16. Multi-instance, Spring Session và giới hạn độ nhất quán

### SessionRegistryImpl chưa tự đồng bộ toàn cụm

Với 3 application pods, mỗi pod có `SessionRegistryImpl` riêng, việc nhìn `getAllSessions(...)` trên pod A không mặc định bao gồm phiên đăng ký ở B/C. Nếu UI hiển thị “tất cả phiên đang hoạt động” hoặc chính sách maximum sessions áp dụng toàn hệ thống, phải dùng **shared session repository/registry** và kiểm thử đồng bộ, ví dụ tích hợp Spring Session nếu phù hợp với loại session store. Không coi việc dùng Redis cho cache thông thường là bằng chứng registry đã phân tán đúng.

### Phiên “đã thu hồi” nhưng request vẫn chạy

Một thao tác revoke từ user/admin có thể gồm:

1. Xác thực người yêu cầu và kiểm tra owner/authority của session đích bằng dữ liệu server.
2. Ghi trạng thái revoked/expired vào authoritative session store hoặc xóa session theo API backend.
3. Phát event `SESSION_REVOKED` sau khi commit, kèm causation và actor_ref; phát invalidation tới cache nếu có.
4. Kiểm thử request **mới** dùng cookie cũ không còn hợp lệ tại mọi pod/region.
5. Đánh giá request **đang chạy** hoặc websocket/long-poll streaming có cần cơ chế đóng riêng không.
6. Cập nhật active session UI theo state thực, giữ audit lịch sử riêng.

`SessionInformation.expireNow()` trong Spring có thể chỉ khiến phiên bị chặn ở lần request tiếp theo khi filter kiểm tra trạng thái. Nếu yêu cầu “revoke tức thời ở mọi instance”, phải đảm bảo backend thực thi và đo được SLA, không chỉ gọi một method trên registry local rồi báo hoàn thành.

### Access token, JWT và refresh token

Ứng dụng có session cookie có thể đồng thời có JWT access token ở mobile. Đừng trộn token với server HttpSession:

- Access token tự chứa thường hợp lệ tới `exp` trừ khi resource server có cơ chế bổ sung (denylist, token version, introspection, ngắn hạn).
- Refresh token có vòng đời, rotation/reuse detection và revocation khác; không ghi raw token, chỉ family ID/jti theo policy.
- `LogoutSuccessEvent` của local web session không khẳng định refresh token ở IdP hoặc thiết bị khác đã bị thu hồi.
- Gắn `auth_method` và `credential_type` để UI biết phiên web, mobile app session và API service account thực sự được hỗ trợ tới mức nào.

### Offline/không có session destroyed event

Browser đóng tab không chắc gửi logout request; một người dùng mất mạng có thể không tạo request mới. `last_seen_at` không phải bằng chứng “online”, và timeout có thể được phát hiện khi session store dọn TTL hoặc lúc một request đến sau hạn. UI nên nói “hoạt động lần cuối lúc...” thay vì tuyên bố thiết bị online realtime nếu backend không có heartbeat/chứng cứ.

## 17. Kịch bản kiểm thử tự động và thực tế

### Unit test schema, privacy và correlation

- Event ID unique, schema version và event_type/outcome từ enum được chấp nhận; invalid type không tự trở thành arbitrary log field.
- Raw `JSESSIONID`/cookie, access token, password, OTP, recovery code **không xuất hiện** trong JSON audit, exception hoặc log collector.
- Một session ID tạo cùng `session_ref` khi audit key/version giống nhau; ID khác tạo ref khác; thời gian rotate có liên kết previous/new refs đúng.
- HMAC key bị rotate theo version có cách truy lịch sử được duyệt mà không lưu raw ID; metric labels không chứa per-user refs.
- User-Agent `"\r\nADMIN=true"`/Unicode control/giá trị cực dài được structured encode/sanitize và giới hạn length; không tạo dòng log giả.
- Unknown username trước login được lưu như unverified submitted ref; không gắn thành user_id có thật.
- IP dùng từ trusted reverse proxy, không nhận `X-Forwarded-For` do client tùy ý giả; geolocation mang độ tin cậy và precision phù hợp.
- Idempotent consumer xử lý event trùng `event_id` đúng một lần; timestamps đến muộn không thay đổi trạng thái đã revoke.

### Spring Security integration tests

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Sai username/password | `AUTH_PROVIDER_FAILED` với reason hạn chế, không có session authenticated |
| Password đúng và MFA còn pending | Provider success có thể có; **không** có full session event |
| Hoàn thành MFA và persist SecurityContext | `SESSION_AUTHENTICATED` đúng user, factor và sessionRef |
| Login form thay session ID | `SESSION_ID_ROTATED` có old/new refs, không raw cookie |
| Browser mở tab thứ hai | Không tự phát “new device/login” chỉ vì tab mới |
| Logout local | Dừng phiên local, audit yêu cầu + kết quả chính xác, không hứa IdP logout |
| Session timeout | Không hiển thị Active sau khi backend xác nhận expired |
| Đăng nhập lần thứ tư khi maximumSessions=3 | Xử lý phiên cũ/mới theo policy và registry |
| Admin/user revoke một phiên khác | Request mới bằng cookie cũ bị từ chối trên mọi node |
| Revocation event đến muộn | Không hồi sinh session cũ trong UI projection |
| OIDC login hoặc remember-me | Event taxonomy phân biệt mechanism, không giả MFA |
| JWT stateless | Không xếp nó thành `HttpSession`; theo dõi bằng token metadata an toàn |
| Audit sink lỗi | Behavior theo error policy và không lộ secrets |
| Attacker sửa device ID/UI publicRef | Bị kiểm tra ownership, không thành phiên trusted |
| Spring custom ProviderManager | Publisher đã được gắn, không mất hoặc nhân đôi event |

Với Servlet, dùng `MockMvc` và các request test có session/cookie khi cần; test `HttpSessionEventPublisher` với container/embedded server nếu MockMvc không mô phỏng đầy đủ lifecycle. Với WebFlux, chọn `WebTestClient`, `ReactiveSecurityContextHolder` và reactive session registry tương ứng; không mặc định dùng listener Servlet.

### Test vận hành và bảo mật

- Test login từ browser mới, xóa cookie, đổi User-Agent, NAT/VPN, geolocation thiếu chính xác: cảnh báo không gây chặn sai quá mức.
- Test hai pods và Redis/DB shared session store: active session list khớp, revoke được áp dụng trên mọi pod.
- Test logout rồi gửi request cookie cũ, đồng thời có request in-flight để xác định SLA/điểm kiểm tra.
- Test backend audit chậm, queue đầy, at-least-once duplicate và event out of order.
- Kiểm tra retention/purge, legal hold nếu được phê duyệt, RBAC truy vấn audit và audit việc đọc/export.
- Test load login failure từ nhiều nguồn: logging không làm cạn CPU, thread, memory hoặc gửi quá nhiều email.
- Test user tự xem lịch sử của mình nhưng không truy cập được lịch sử/phiên của user khác (chống IDOR).
- Khi gửi alert “đăng nhập lạ”, link không chứa session token, không redirect ngoài domain và có rate limit.

## 18. Những lỗi triển khai phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Ghi `AuthenticationSuccessEvent` thành “login đã hoàn tất” | Sai với MFA/Basic/custom authentication | Event taxonomy theo boundary, ghi session authenticated sau commit |
| Log `Authentication.toString()` hoặc toàn request headers | Có thể lộ password/token/user details | Field allowlist và redaction ngay tại nguồn |
| Log raw `HttpSession.getId()`/cookie | Audit leak trở thành session hijack | HMAC sessionRef/surrogate, bảo vệ audit key |
| User-Agent/IP = unique trusted device | Dễ spoof, false positives, theo dõi sai | Tách device observation và verified enrollment |
| Mỗi tab = một session/device | UI sai khi tabs chia sẻ browser cookie | Dựa vào session store, không đo tab |
| Logout xóa row audit nhưng không invalid session | Cookie vẫn dùng được | Revoke authoritative session và verify |
| `SessionRegistryImpl` local = toàn cụm | Không thấy session trên pod khác | Shared store/registry và end-to-end test |
| `expireNow()` = hủy mọi request tức thời | Có thể chỉ hiệu lực ở request kế tiếp | Xác định SLA, kill streams nếu cần |
| Dùng JWT như `HttpSession` | Báo revoke sai | Token lifecycle riêng, revocation theo thiết kế |
| Event sync gọi SIEM chậm | Login latency, DoS khi collector lỗi | Durable queue/outbox, bounded backpressure |
| Message broker at-least-once, không dedupe | Một login xuất hiện nhiều lần | Event ID idempotency, tách event types |
| Sắp event theo timestamp duy nhất | Clock skew/out-of-order làm sai state | Causation/sequence và authoritative state |
| Dùng raw email/IP trong metric labels | Cardinality explosion và lộ PII | Metrics aggregate, audit store phân quyền |
| Cho support xem/revoke session bất kỳ | Chiếm quyền và xâm phạm riêng tư | RBAC, owner check, reauth và audit hành động |
| Gửi email mỗi failed login | Attacker gây notification bombing | Rate limit/aggregate và chọn ngưỡng |
| UI nói “online” khi chỉ có last seen | Thông tin sai | Hiển thị thời gian hoạt động gần nhất |
| Định vị IP là địa chỉ chính xác | Gây hiểu lầm và thu thập quá mức | Vùng gần đúng và độ tin cậy |
| Bỏ qua các luồng OIDC/remember-me/MFA | Có đường không được audit | Kiểm kê tất cả authentication entry points |

## 19. Checklist sản xuất

**Thiết kế dữ liệu và privacy**

- [ ] Có định nghĩa event types riêng cho authentication attempt, factor, session, device, revoke và alert.
- [ ] Audit schema versioned, event_id unique, UTC occurred_at/recorded_at, actor_ref, outcome, correlation và causation.
- [ ] Không ghi plaintext password/OTP/token/cookie/CSRF/raw session ID; có test redaction và log injection.
- [ ] Session correlation dùng HMAC/surrogate đủ entropy, key bảo vệ riêng, không lẫn auth token.
- [ ] Device observation được ghi rõ là **risk signal**, không thay xác thực; có chính sách privacy, retention và quyền truy cập.

**Spring Security và lưu trữ**

- [ ] `AuthenticationEventPublisher` được cấu hình cho đúng ProviderManager, không duplicate/miss event.
- [ ] Provider success được tách khỏi login hoàn tất và MFA verified.
- [ ] `SecurityContext` được persist đúng khi custom authentication; session ID rotation được liên kết an toàn.
- [ ] `HttpSessionEventPublisher`, session registry và concurrent policy có test; multi-node dùng shared authoritative store.
- [ ] Logout/timeout/revoke phân biệt nguồn sự kiện, kiểm tra request mới sau revoke.
- [ ] Stateless JWT/refresh token/mobile sessions dùng mô hình theo dõi tương ứng, không lấy session registry web làm nguồn duy nhất.

**Vận hành và UI**

- [ ] UI lịch sử login, active sessions và remembered devices tách ba danh sách đúng nghĩa.
- [ ] Mọi thao tác xem/revoke xác minh owner server-side; admin actions có RBAC, MFA/fresh auth nếu rủi ro cao.
- [ ] Có detection bất thường với confidence, tránh lockout sai khi NAT/VPN/cookie thay đổi.
- [ ] Có durable queue/outbox hoặc failure policy rõ cho security audit, idempotency và event ordering.
- [ ] Metrics ít cardinality, access audit, retention/purge và cảnh báo khi pipeline mất dữ liệu.
- [ ] Test hai node, multi-tabs, session fixation, login MFA pending, logout, revoke, audit backlog và email bombing.

**Kết luận:** Nhật ký đăng nhập hữu ích khi trả lời đúng **ai (sau xác minh), cơ chế nào, lúc nào, từ đâu với độ tin cậy ra sao, phiên nào được cấp và khi nào bị chấm dứt**. Thiết bị là một khái niệm quản lý/quan sát có nhiều mức độ bằng chứng; session là credential có lifecycle riêng; authentication success là một bước kỹ thuật chứ không luôn là login hoàn chỉnh. Mô hình event rõ nghĩa, correlation HMAC không lộ secret, session registry bền vững, privacy và kiểm thử end-to-end là nền tảng để điều tra sự cố và trao quyền quản lý phiên an toàn cho người dùng.

## Nguồn tham khảo chính thức

- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SessionRegistry và Session Events API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/package-summary.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)
- [Java 17 — Mac API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html)
- [Java 17 — Instant API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
