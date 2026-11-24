# Debug mode: chẩn đoán an toàn trong hệ thống xác thực

> **Chương:** Error và privacy  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích cách cung cấp thông tin chẩn đoán đủ để phát hiện và sửa lỗi authentication mà không làm lộ credential, dữ liệu cá nhân, cấu hình nội bộ hoặc chi tiết giúp attacker vượt qua hệ thống.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt debug mode, diagnostic logging, audit logging và production observability.
2. Mô hình hóa rủi ro khi bật debug mode trong authentication service.
3. Nhận diện dữ liệu nhạy cảm có thể xuất hiện trong error, log, trace, dump và diagnostic bundle.
4. Thiết kế error response an toàn cho password, MFA, passkey, token, session và recovery.
5. Quản lý debug feature bằng environment, feature flag, authorization, approval và thời hạn.
6. Thu thập correlation ID và structured telemetry mà không ghi secret.
7. Giới hạn debug endpoint, actuator, heap dump, thread dump và support tooling.
8. Xử lý production incident bằng quy trình break-glass có audit và cleanup.
9. Triển khai cấu hình Java/Spring an toàn và xây dựng ma trận kiểm thử debug mode.

## 2. Debug mode là gì?

**Debug mode** là chế độ hoặc tập cấu hình làm tăng mức thông tin chẩn đoán để giúp developer/operator hiểu trạng thái và nguyên nhân lỗi. Nó có thể bật stack trace, request detail, diagnostic endpoint, protocol trace, verbose log, profiling hoặc công cụ quan sát nội bộ.

Trong hệ thống xác thực, debug có thể giúp tìm nguyên nhân:

- Password verifier không khớp.
- WebAuthn challenge hết hạn hoặc origin/RP ID không khớp.
- TOTP code nằm ngoài time window.
- JWT sai issuer, audience, signature hoặc expiry.
- Certificate chain không được trust.
- Session bị invalidate hoặc cookie không được gửi.
- OAuth callback sai state/nonce.
- Recovery grant đã hết hạn hoặc đã được tiêu thụ.

Nhưng thông tin giúp developer chẩn đoán cũng có thể giúp attacker hiểu cách hệ thống hoạt động, tìm account hợp lệ, lấy credential hoặc vượt qua trust boundary.

Vì vậy, debug mode phải có phạm vi, người được phép bật, dữ liệu được phép thu thập, nơi lưu trữ, thời hạn và quy trình tắt rõ ràng. Debug không phải lý do để ghi toàn bộ request/response hoặc hiển thị exception nội bộ cho người dùng.

## 3. Debug mode, logging, audit và observability

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| Debug mode | Tăng thông tin chẩn đoán có kiểm soát | Trace bước xác minh OIDC callback |
| Application logging | Ghi trạng thái xử lý ứng dụng | Authentication handler trả reason code |
| Security audit | Ghi bằng chứng hành động và quyết định | User đăng ký passkey mới |
| Metrics | Đo số lượng và xu hướng | Tỷ lệ MFA failure theo method |
| Distributed tracing | Theo dõi request qua nhiều service | Gateway → IdP → token service |
| Profiling/diagnostic dump | Tìm vấn đề hiệu năng hoặc trạng thái process | Thread dump khi authentication bị treo |

Các loại telemetry bổ sung cho nhau. Không nên bật debug toàn cục chỉ vì cần một audit event hoặc metric. Hãy chọn công cụ ít dữ liệu nhạy cảm nhất có thể trả lời câu hỏi điều tra.

## 4. Threat model khi bật debug

Debug mode làm tăng bề mặt dữ liệu và bề mặt điều khiển:

- Error response có thể tiết lộ stack trace, class name, SQL, file path hoặc dependency version.
- Log có thể ghi password, OTP, Authorization header, cookie hoặc token.
- Protocol trace có thể lưu assertion, authorization code, SAML response hoặc client secret.
- Diagnostic endpoint có thể tiết lộ environment variable, configuration và heap state.
- Heap/thread dump có thể chứa plaintext secret đang ở memory.
- Debug console có thể cho phép thay đổi state hoặc thực thi lệnh.
- Debug flag có thể bị bật qua query parameter, header hoặc client-controlled configuration.
- Support bundle có thể được tải lên ticket hoặc chia sẻ ngoài trust boundary.

~~~mermaid
flowchart TD
    A["Authentication failure"] --> B["Operator requests diagnostics"]
    B --> C["Debug scope and approval"]
    C --> D["Collect allowlisted telemetry"]
    D --> E["Redact secrets and minimize PII"]
    E --> F["Restricted diagnostic store"]
    F --> G["Investigate with correlation IDs"]
    G --> H["Expire data and disable debug"]
    X["Attacker / unauthorized insider"] -.-> C
    X -.-> F
    X -.-> D
~~~

Threat model cần xét cả attacker bên ngoài lẫn insider, vendor support, CI/CD pipeline, log processor và người có quyền đọc observability platform.

## 5. Nguyên tắc: debug phải fail safe

Một thiết kế an toàn nên tuân theo:

1. Debug mặc định tắt ở production.
2. Không cho request client tự bật debug bằng header, query parameter hoặc body field.
3. Debug flag phải được điều khiển từ trusted control plane hoặc deployment configuration.
4. Chỉ principal có quyền chẩn đoán mới bật hoặc đọc diagnostic data.
5. Scope debug giới hạn theo service, environment, account hoặc request.
6. Debug có expiry tự động và người chịu trách nhiệm.
7. Thu thập theo allowlist; không dump toàn bộ object/request.
8. Redact secret trước khi ghi hoặc export.
9. Diagnostic store tách quyền với application runtime.
10. Mọi lần bật, đọc, export và tắt debug đều có audit.

Nếu debug control plane không truy cập được, production không được tự chuyển sang verbose mode. Giữ trạng thái an toàn hiện tại và tạo cảnh báo.

## 6. Không tiết lộ chi tiết lỗi xác thực cho người dùng

Thông báo công khai nên đủ hữu ích để người dùng biết bước tiếp theo nhưng không tiết lộ account existence, credential state hoặc nội bộ hệ thống.

Ví dụ:

| Tình huống nội bộ | Response công khai an toàn hơn |
|---|---|
| Username không tồn tại | Thông tin đăng nhập không hợp lệ |
| Password sai | Thông tin đăng nhập không hợp lệ |
| Account bị khóa | Không thể hoàn tất đăng nhập; dùng kênh hỗ trợ chính thức nếu cần |
| Email recovery không tồn tại | Nếu tài khoản đủ điều kiện, hướng dẫn sẽ được gửi |
| MFA code sai/hết hạn | Không thể xác minh mã; thử lại hoặc dùng phương thức được hỗ trợ |
| Token sai chữ ký | Yêu cầu không hợp lệ hoặc không được phép |
| Certificate chain không trust | Kết nối không được chấp nhận |

Không nên trả khác biệt dễ dò giữa username tồn tại và không tồn tại ở endpoint login/recovery. Với một số workflow đã xác thực, có thể cung cấp hướng dẫn chi tiết hơn vì principal đã được xác minh.

### Public error và internal reason

Tách hai lớp:

- **Public code/message:** ổn định, ít thông tin, không chứa chi tiết nhạy cảm.
- **Internal reason code:** giúp operator phân biệt nguyên nhân như INVALID_CREDENTIAL, CHALLENGE_EXPIRED, ISSUER_MISMATCH hoặc SESSION_REVOKED.

Internal reason chỉ nằm trong log/trace có kiểm soát. Không đưa raw exception hoặc stack trace vào response.

## 7. Những dữ liệu tuyệt đối không ghi vào debug log

Không ghi trực tiếp:

- Password, password reset token hoặc bootstrap password.
- OTP, TOTP seed, recovery code hoặc provisioning URI.
- Passkey private key, authenticator private material hoặc raw attestation data nếu không cần thiết.
- Access token, refresh token, ID token, authorization code hoặc SAML assertion.
- Session cookie, CSRF token hoặc Authorization header.
- API key, client secret, database password và cloud credential.
- Private key, key export material hoặc decrypted secret.
- Toàn bộ request/response body khi schema có thể chứa dữ liệu xác thực.

Các dữ liệu này có thể xuất hiện trong:

- Application log và exception message.
- HTTP access log và reverse proxy.
- Distributed trace/span attributes.
- APM agent và profiler.
- Heap dump, core dump và crash report.
- Browser console và client telemetry.
- CI test output, screenshots và support bundle.

Không cho rằng dữ liệu an toàn chỉ vì log ở private network. Log thường có nhiều người và hệ thống có quyền đọc hơn secret manager.

## 8. Redaction và data minimization

**Redaction** loại bỏ hoặc thay thế dữ liệu nhạy cảm trước khi ghi. **Data minimization** chỉ thu thập những trường cần thiết cho mục tiêu chẩn đoán.

Ví dụ:

~~~text
Unsafe:
  Authorization: Bearer eyJ...
  cookie: SESSION=abc123
  username: user@example.test
  otp: 381204

Safer:
  auth_scheme = bearer
  session_ref = sess-ref-7f2a
  subject_ref = user-ref-104
  factor_type = TOTP
  result = DENIED
  reason_code = OTP_WINDOW_INVALID
  request_id = req-91ac
~~~

Các nguyên tắc:

- Dùng allowlist field thay vì ghi object rồi cố redact mọi trường.
- Dùng opaque reference thay cho raw credential.
- Mask PII theo policy, ví dụ chỉ giữ phần tối thiểu cần thiết.
- Không dùng token hash làm nhãn metric hoặc label có cardinality cao.
- Không đưa email, username, session ID hoặc IP vào metric label nếu không cần.
- Kiểm tra nested object, exception cause và serialization output.
- Redact tại source trước khi dữ liệu rời process.
- Kiểm thử redaction bằng secret canary giả lập.

Masking một phần không phải lúc nào cũng an toàn. Một email bị che một phần vẫn có thể nhận diện người dùng trong tập dữ liệu nhỏ; chọn pseudonymous ID nếu mục tiêu là correlation.

## 9. Correlation ID thay cho raw credential

Khi request đi qua gateway, authentication service, token service và application API, operator cần ghép các sự kiện lại với nhau.

Dùng:

- Request ID do gateway/server tạo.
- Trace ID/span ID từ tracing system.
- Authentication transaction ID.
- Session reference nội bộ không dùng để xác thực.
- Credential ID hoặc key ID không bí mật.
- Policy decision ID.
- Provider request ID.

Không dùng raw session cookie, bearer token, OTP hoặc authorization code làm correlation key. Không nhận correlation ID từ client như bằng chứng duy nhất; gateway có thể tạo hoặc chuẩn hóa ID và bảo vệ tính duy nhất trong phạm vi cần thiết.

Correlation ID không nên mang PII hoặc dữ liệu có thể đoán. Với public response, có thể trả request ID để người dùng cung cấp cho support.

## 10. Debug password authentication

Khi password login thất bại, operator thường cần biết bước nào lỗi:

- Request validation.
- Account lookup.
- Rate limit hoặc abuse control.
- Password hash verification.
- Account status.
- MFA requirement.
- Session creation.

Thông tin an toàn có thể ghi:

- Authentication transaction ID.
- Kết quả từng stage dưới dạng success/denied.
- Algorithm/profile của password verifier nếu cần điều tra migration.
- Reason code nội bộ.
- Rate-limit bucket reference.
- Account pseudonymous reference.

Không ghi:

- Password nhập vào.
- Password hash đầy đủ nếu log không cần và có thể bị dùng để offline cracking.
- Password reset token.
- Secret pepper hoặc KMS key.

Password hash là dữ liệu nhạy cảm. Dù không phải plaintext, việc đưa hash vào log làm tăng bề mặt tấn công và không cần thiết cho hầu hết chẩn đoán.

## 11. Debug MFA, passkey và recovery

### TOTP và push

Có thể ghi factor type, transaction ID, result, time window identifier và reason code. Không ghi OTP hoặc TOTP seed. Với push, không log nội dung bí mật của challenge hoặc mã number-matching nếu mã đó có thể được dùng để hoàn tất approval.

### Passkey/WebAuthn

Có thể ghi:

- RP ID theo cấu hình.
- Origin đã chuẩn hóa nếu policy cho phép.
- Challenge reference, không ghi raw challenge nếu không cần.
- Credential ID dạng reference/pseudonymous.
- Result của kiểm tra origin, RP ID hash, signature và user verification.
- Attestation format/policy result ở mức cần thiết.

Không ghi private key, raw assertion, toàn bộ clientDataJSON/authenticatorData hoặc attestation object nếu không có nhu cầu pháp lý/kỹ thuật được phê duyệt. Những payload này có thể chứa identifier và dữ liệu thiết bị.

### Recovery

Ghi recovery purpose, grant reference, trạng thái pending/consumed/expired và decision. Không ghi recovery link, token hoặc code. Không bật debug để in nội dung email/SMS.

## 12. Debug token, OAuth/OIDC và SAML

Các luồng federation thường chứa artifact có giá trị cao:

- OAuth authorization code.
- PKCE verifier.
- OIDC ID token và access/refresh token.
- State và nonce.
- SAML Response/Assertion.
- Client secret và private signing key.

Không log raw artifact hoặc bật wire logging ở production để chẩn đoán callback.

Thay vào đó, ghi kết quả validation:

- Configured issuer matched/mismatched.
- Audience matched/mismatched.
- Signature validation result và key ID.
- Token expired/not-yet-valid.
- State/nonce transaction reference matched/mismatched.
- Redirect URI profile matched/mismatched.
- Scope/consent decision.
- Correlation ID từ IdP/provider nếu được cung cấp.

Nếu cần xem payload trong môi trường test, dùng token và identity giả lập. Không copy production token vào issue tracker hoặc chat.

## 13. Debug certificate và mTLS

Khi TLS handshake thất bại, log an toàn có thể ghi:

- Peer identity reference.
- Certificate issuer/subject/SAN đã được chuẩn hóa theo policy.
- Serial number hoặc certificate fingerprint nếu cần correlation.
- Validity result.
- Chain validation result.
- EKU/key usage result.
- Trust anchor/profile ID.
- TLS alert category và handshake phase.

Không export private key để debug. Không ghi nội dung keystore hoặc secret password. Certificate metadata cũng có thể tiết lộ topology và danh tính workload, nên giới hạn quyền đọc và retention.

## 14. Debug endpoint và management interface

Các endpoint như health, metrics, info, env, config, heapdump, threaddump và mappings có thể tiết lộ thông tin nhạy cảm.

Quy tắc:

- Chỉ expose endpoint thực sự cần.
- Tách management port/network khỏi public application traffic.
- Yêu cầu authentication và authorization mạnh.
- Không public endpoint env/config/heapdump.
- Không trả environment variables hoặc secret references có thể bị khai thác.
- Giới hạn source network và workload identity.
- Ghi audit cho mọi lần truy cập.
- Không dùng endpoint debug có khả năng thay đổi runtime config nếu không có approval.

Health endpoint nên trả trạng thái tối thiểu, ví dụ UP/DOWN hoặc readiness status, không trả connection string, dependency host, version chi tiết hoặc stack trace.

### Spring Boot Actuator

Spring Boot Actuator cung cấp nhiều management endpoint. Chỉ expose những endpoint cần thiết qua cấu hình rõ ràng; không mở rộng tất cả endpoint vì tiện debugging.

Ví dụ cấu hình giới hạn:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: never
  server:
    port: 9091
~~~

Đây là ví dụ minh họa. Management port riêng không tự làm endpoint an toàn; cần network policy, authentication/authorization, TLS phù hợp và kiểm tra rằng port không được publish ra internet. Không expose env, configprops, heapdump hoặc threaddump công khai.

## 15. Debug feature flag và cấu hình theo môi trường

Không nên dùng một boolean global có thể được thay đổi bởi mọi developer hoặc request client.

Thiết kế feature flag:

- Mặc định false ở production.
- Được quản lý bởi control plane có authentication và authorization.
- Có scope theo service, instance, environment hoặc transaction.
- Có owner, reason, ticket/incident ID và expiry.
- Có audit cho enable/disable và người phê duyệt.
- Không thay đổi log level toàn hệ thống nếu chỉ cần trace một request.
- Có kill switch để tắt ngay khi phát hiện dữ liệu nhạy cảm.

Tách cấu hình:

| Môi trường | Debug policy |
|---|---|
| Local development | Có thể bật verbose, dùng dữ liệu giả |
| Automated test | Có thể bật trace có kiểm soát và fixture giả |
| Staging | Giới hạn theo quyền, dữ liệu đã mask |
| Production | Tắt mặc định; bật tạm thời theo incident và scope hẹp |

Không để profile local/dev được kích hoạt nhầm trong production. Kiểm tra profile, environment variable và deployment manifest trong pipeline.

## 16. Debug một request cụ thể

Thay vì bật debug toàn service, có thể bật diagnostic sampling cho một transaction:

1. Operator tạo incident/change reference.
2. Chọn service, environment và khoảng thời gian.
3. Chọn request ID hoặc transaction ID đã biết.
4. Hệ thống xác minh quyền operator và approval.
5. Chỉ thu allowlisted fields cho request đó.
6. Diagnostic context tự hết hạn.
7. Event bật/tắt và người đọc bundle được audit.
8. Bundle được lưu ở nơi có quyền truy cập giới hạn.

Không cho client tự gửi header như X-Debug: true rồi server ghi request body. Nếu cần propagation, gateway phải xác minh debug grant và tạo context nội bộ có chữ ký hoặc metadata được bảo vệ.

## 17. Stack trace và exception handling

Stack trace hữu ích cho developer nhưng thường không phù hợp với public response.

Public response nên chứa:

- Error code ổn định.
- Thông điệp hướng dẫn ngắn.
- Request/correlation ID.
- HTTP status phù hợp.

Internal log có thể chứa:

- Exception class.
- Stack trace nếu policy cho phép.
- Component/stage.
- Sanitized input metadata.
- Correlation ID.
- Reason code.

Trước khi ghi exception, cần kiểm tra message và cause chain không chứa URL có token, SQL bind values, credential hoặc request body. Một thư viện có thể đưa secret vào exception message dù application không chủ ý.

Không trả stack trace, SQL statement, file path, hostname nội bộ hoặc dependency version cho client.

## 18. Diagnostic dump và support bundle

Heap dump, core dump, thread dump và support bundle có thể chứa:

- Plaintext secret trong memory.
- Request body và response cache.
- Token, cookie hoặc authorization header.
- PII và dữ liệu nghiệp vụ.
- Environment variable và connection string.
- Internal hostname, topology và file path.

Trước khi thu thập:

1. Xác định câu hỏi chẩn đoán và artifact tối thiểu.
2. Đánh giá có thể dùng thread dump/metric thay heap dump không.
3. Xác minh approval và quyền operator.
4. Ghi vị trí lưu, encryption, owner và expiry.
5. Hạn chế tải xuống và chia sẻ.
6. Scan/redact theo công cụ đã được kiểm chứng.
7. Xóa artifact khi hết mục đích/retention.

Không gửi heap dump production qua email hoặc issue tracker công khai. Không upload bundle lên dịch vụ bên ngoài chưa được phê duyệt.

## 19. Debug mode và privacy

Diagnostic data có thể tạo hồ sơ hành vi người dùng nếu thu thập quá mức:

- Login time và location.
- IP/device fingerprint.
- Email, phone và username.
- Factor enrollment và recovery history.
- Session activity.
- Failed authentication patterns.
- Organization membership.

Nguyên tắc privacy:

- Xác định mục đích cụ thể trước khi thu thập.
- Thu thập ít nhất có thể.
- Pseudonymize subject khi không cần danh tính thật.
- Giới hạn quyền truy cập theo vai trò.
- Đặt retention và xóa theo lịch.
- Ghi audit khi export/read diagnostic data.
- Không dùng debug telemetry cho mục đích khác nếu chưa có căn cứ và thông báo phù hợp.
- Tránh metric label có giá trị nhận dạng cá nhân.

Debug data vẫn là dữ liệu cần bảo vệ. Việc không chứa password không có nghĩa nó vô hại.

## 20. Audit việc bật và sử dụng debug

Các event cần ghi:

- Debug flag enabled/disabled.
- Actor và approver.
- Service/environment/scope.
- Reason/incident reference.
- Start time và expiry.
- Log level hoặc diagnostic category đã bật.
- Bundle created/downloaded/exported/deleted.
- Access denied hoặc approval failure.
- Emergency override và post-review.

Không ghi secret hoặc nội dung raw diagnostic bundle vào audit. Audit phải nằm ngoài quyền kiểm soát trực tiếp của operator đang bật debug khi có thể.

## 21. Incident response khi debug bị bật sai

Nếu phát hiện debug mode đang bật ngoài policy:

1. Xác định service, instance, thời điểm và người bật.
2. Tắt debug hoặc thu hẹp scope ngay khi có thể.
3. Xác định loại dữ liệu đã được ghi hoặc expose.
4. Kiểm tra log, trace, dump, endpoint và support bundle.
5. Nếu credential có thể đã lộ, revoke/rotate credential liên quan.
6. Thu hồi diagnostic link hoặc quyền truy cập bundle.
7. Kiểm tra access log để xác định ai đã đọc/export dữ liệu.
8. Bảo toàn evidence cần thiết trong kho điều tra an toàn.
9. Xóa bản sao không cần thiết theo incident/retention policy.
10. Sửa cấu hình, test guardrail và ghi post-incident review.

Không chỉ tắt flag rồi kết thúc. Nếu debug đã ghi token hoặc secret, cần xử lý như một credential exposure incident.

## 22. Java/Spring: cấu hình logging không lộ credential

Ví dụ dùng profile để kiểm soát log level:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.security: INFO

---
spring:
  config:
    activate:
      on-profile: local
logging:
  level:
    root: DEBUG
    org.springframework.security: DEBUG
~~~

Đây là minh họa cho local development. Production deployment phải bảo đảm profile local không được kích hoạt. Với Spring Security, debug log có thể tiết lộ chi tiết filter chain và request context; cần kiểm tra output thực tế của phiên bản framework và app.

Không bật DEBUG cho toàn bộ HTTP client/server wire logging trong production vì header/body có thể chứa token và cookie.

### Sanitized diagnostic event

~~~java
record AuthenticationDiagnostic(
    String requestId,
    String subjectRef,
    String authenticationMethod,
    String stage,
    String result,
    String reasonCode
) {}

AuthenticationDiagnostic diagnostic(
        String requestId,
        String subjectRef,
        String method,
        String stage,
        boolean success,
        String reasonCode) {
    return new AuthenticationDiagnostic(
        requestId,
        subjectRef,
        method,
        stage,
        success ? "SUCCESS" : "DENIED",
        reasonCode
    );
}
~~~

DTO chỉ chứa metadata allowlisted. Không thêm password, OTP, token, cookie hoặc raw request vào event. Subject reference cần pseudonymous hoặc opaque nếu log không cần nhận diện trực tiếp user.

### Public error response

~~~java
record ApiError(
    String code,
    String message,
    String requestId
) {}

ApiError authenticationFailure(String requestId) {
    return new ApiError(
        "AUTHENTICATION_FAILED",
        "Không thể xác minh thông tin đăng nhập.",
        requestId
    );
}
~~~

Internal logs có thể giữ reason code cụ thể theo quyền truy cập; response công khai không phân biệt account tồn tại, password sai hay account bị khóa nếu điều đó tạo account enumeration risk.

## 23. Ma trận kiểm thử debug mode

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Production khởi động mặc định | Debug tắt |
| Client gửi header yêu cầu debug | Không thay đổi debug configuration |
| Client thêm query parameter debug | Không thay đổi log level hoặc response detail |
| Operator không có quyền bật debug | Từ chối và audit |
| Debug grant hết hạn | Tự động tắt |
| Debug chỉ cho một request | Không lan sang request khác |
| Password login thất bại | Không log password hoặc password hash |
| TOTP thất bại | Không log OTP hoặc seed |
| WebAuthn thất bại | Không log private material hoặc raw assertion không cần thiết |
| OAuth callback lỗi | Không log code, state, nonce, token hoặc PKCE verifier |
| JWT validation thất bại | Chỉ log reason code/metadata allowlisted |
| TLS/mTLS handshake lỗi | Không export private key hoặc keystore password |
| HTTP wire logging bật | Secret scanner phát hiện token/cookie; production guard chặn |
| Exception chứa token trong message | Redaction ngăn token vào log/response |
| Actuator env/config/heapdump được gọi từ public network | Không expose hoặc bị authorization/network policy chặn |
| Health endpoint | Chỉ trả trạng thái tối thiểu |
| Heap dump được yêu cầu | Cần approval, restricted storage, expiry và audit |
| Diagnostic bundle export | Người tải được xác thực, quyền và mục đích được ghi |
| Debug flag bị bật ngoài change window | Alert/incident được tạo |
| Log sink unavailable | Không tự bật verbose mode hoặc âm thầm bỏ audit |
| Diagnostic data quá hạn | Bị xóa/archive theo retention policy |
| Debug mode được tắt | Không còn diagnostic scope tồn tại ngoài expiry |
| Secret canary trong request fixture | Không xuất hiện trong log, trace, metric hoặc bundle |
| Subject ID đưa vào metric label | Test phát hiện high-cardinality/PII label |
| Local profile trên production | Deployment guard từ chối |

Kiểm thử cả cấu hình khởi động, runtime feature flag, endpoint management và nội dung telemetry thực tế. Đừng chỉ kiểm tra rằng application trả status 200/401; cần scan log, trace và bundle bằng secret canary giả.

## 24. Tình huống phân tích

### Tình huống A: bật Spring Security DEBUG trong production

Một operator tăng log level để điều tra login failure. Log bắt đầu chứa request detail và thông tin filter chain rộng hơn dự kiến.

**Phân tích:** DEBUG có thể tiết lộ context nhạy cảm. Thu hẹp theo component/request, kiểm tra output, redact trước sink, đặt expiry và audit người bật. Không bật HTTP wire logging toàn cục.

### Tình huống B: stack trace tiết lộ account tồn tại

Endpoint recovery trả lỗi khác nhau khi email không tồn tại và khi account bị khóa.

**Phân tích:** Public response tạo account enumeration oracle. Dùng response chung; internal reason code được giữ trong log có kiểm soát.

### Tình huống C: support bundle chứa refresh token

Nhân viên support thu diagnostic bundle và tải lên ticket để đội khác phân tích. Bundle chứa header Authorization.

**Phân tích:** Xử lý như credential exposure. Thu hồi token/session liên quan, hạn chế quyền ticket, xóa bản sao không cần thiết và sửa allowlist/redaction tại source.

### Tình huống D: actuator env endpoint public

Ứng dụng expose endpoint env để tiện kiểm tra deployment. Endpoint trả một số biến cấu hình và secret reference.

**Phân tích:** Management endpoint đã vượt trust boundary. Tắt exposure, giới hạn management network, yêu cầu authorization, audit access và kiểm tra dữ liệu đã bị đọc.

### Tình huống E: debug flag được client tự bật

Ứng dụng đọc header X-Debug và bật verbose logging cho request đó.

**Phân tích:** Client không phải authority để thay đổi diagnostic policy. Chỉ trusted control plane cấp debug grant có scope, approval và expiry; gateway xóa header do client gửi.

## 25. Quy trình thiết kế và vận hành

Trước khi triển khai debug mode, hãy xác định:

1. Câu hỏi chẩn đoán cụ thể là gì và telemetry tối thiểu nào trả lời được?
2. Debug mặc định có tắt ở production không?
3. Ai có quyền bật, đọc và export diagnostic data?
4. Feature flag có scope, owner, reason, approval và expiry không?
5. Client có thể tác động debug qua header/query/body không?
6. Error response có chống account enumeration và không lộ stack trace không?
7. Log/trace có allowlist và redaction ở source không?
8. Password, OTP, token, cookie, private key và recovery code có bị chặn khỏi telemetry không?
9. Actuator/management endpoint có được giới hạn network và authorization không?
10. Heap/thread dump và support bundle được bảo vệ, mã hóa, audit và xóa thế nào?
11. Correlation ID có đủ cho điều tra mà không dùng raw credential không?
12. Audit bật/tắt/export debug có nằm ngoài quyền operator không?
13. Audit/log sink failure có semantics rõ và cảnh báo không?
14. Có quy trình revoke/rotate credential nếu debug làm lộ secret không?
15. Có kiểm thử secret canary trên log, trace, metric, dump và bundle không?

## 26. Ghi nhớ trọng tâm

- **Debug mode là một quyền nhạy cảm.** Mặc định tắt ở production và chỉ bật theo scope, approval, owner và expiry.
- **Debug không phải quyền ghi mọi dữ liệu.** Thu thập theo allowlist và data minimization.
- **Không ghi credential vào log.** Password, OTP, token, cookie, recovery code và private key phải được loại khỏi telemetry.
- **Public error và internal reason phải tách biệt.** Không để error response trở thành công cụ dò account hoặc cấu hình nội bộ.
- **Correlation ID thay raw token.** Điều tra qua request/trace/transaction reference an toàn.
- **Actuator, heap dump và support bundle là bề mặt nhạy cảm.** Giới hạn network, authorization, export và retention.
- **Debug flag không do client điều khiển.** Dùng trusted control plane và audit mọi thay đổi.
- **Audit debug cũng cần bảo vệ integrity.** Người bật debug không nên tự xóa bằng chứng.
- **Nếu secret có thể đã lộ, xử lý như credential incident.** Revoke/rotate và điều tra bản sao dữ liệu.
- **Kiểm thử nội dung telemetry thực tế.** Secret canary giúp phát hiện dữ liệu nhạy cảm bị ghi ngoài dự kiến.

Debug mode an toàn cho phép đội vận hành hiểu lỗi xác thực mà không biến log, trace, endpoint quản trị hoặc support bundle thành đường rò credential. Giới hạn quyền bật, thu thập tối thiểu, redaction tại nguồn, audit độc lập và tự động tắt giúp cân bằng khả năng chẩn đoán với bảo vệ danh tính và quyền riêng tư.
