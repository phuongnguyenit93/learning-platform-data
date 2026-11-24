# Audit exchange: Kiểm toán quá trình trao đổi token

## 1. Audit exchange là gì và vì sao cần thiết?

Trong hệ thống dùng OAuth 2.0/OIDC, một token có thể được phát hành cho ứng dụng ban đầu nhưng không phù hợp để gọi một dịch vụ khác. **Token exchange** cho phép một thành phần được ủy quyền đưa token hiện có tới Authorization Server/Security Token Service (STS), yêu cầu một token mới với đối tượng nhận, phạm vi quyền và ngữ cảnh sử dụng phù hợp. Cơ chế chuẩn hóa phổ biến là OAuth 2.0 Token Exchange theo RFC 8693.

**Audit exchange** là việc ghi lại bằng chứng có cấu trúc về từng quyết định trao đổi token: ai gửi yêu cầu, dựa trên danh tính/quyền nào, muốn truy cập dịch vụ nào, STS đánh giá chính sách ra sao, token có được cấp hay không, và cấp với những giới hạn nào. Audit phục vụ truy vết, điều tra sự cố, kiểm soát đặc quyền và chứng minh việc thực thi chính sách.

Ví dụ: người dùng đăng nhập vào ứng dụng bán hàng; dịch vụ Đơn hàng cần gọi dịch vụ Kho. Dịch vụ Đơn hàng yêu cầu STS đổi token đại diện cho người dùng thành token có audience là dịch vụ Kho và scope chỉ là đọc tồn kho. Nếu sau đó xuất hiện truy cập tồn kho bất thường, audit exchange giúp trả lời: token nào là nguồn của việc cấp quyền, client và actor nào tham gia, STS áp dụng policy gì, token mới hướng tới audience nào và có hiệu lực bao lâu.

Trong phạm vi module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, audit exchange liên kết trực tiếp với mô hình tin cậy và vòng đời token: xác thực client, thẩm định JWT/opaque token, kiểm tra claims/scope/audience, phát hành token mới, giới hạn quyền, thu hồi và phát hiện hành vi sử dụng lại bất thường. Audit giúp phát hiện và giải thích quyết định bảo mật; **bản ghi audit tự nó không xác thực token, không thu hồi token và không ngăn replay**.

Sau bài học, người học cần:

- Phân biệt audit bảo mật với application log, distributed trace và metric.
- Xác định dữ liệu tối thiểu cần ghi cho một lần token exchange thành công hoặc thất bại.
- Thiết kế sự kiện audit có thể liên kết qua nhiều service mà không làm lộ bearer token.
- Biết kiểm tra tính toàn vẹn, truy vấn bất thường và xử lý tình huống hệ thống audit gặp lỗi.

## 2. Ngữ cảnh của một lần token exchange

Theo RFC 8693, client gửi yêu cầu đến token endpoint, thường gồm:

| Thành phần | Vai trò | Ý nghĩa đối với audit |
| --- | --- | --- |
| <code>grant_type</code> | Xác định giao thức token exchange | Phân biệt với client credentials, authorization code hoặc refresh token |
| <code>subject_token</code> và <code>subject_token_type</code> | Token nguồn và loại của nó | Chỉ ghi **loại** và định danh tương quan đã được bảo vệ; tuyệt đối không ghi token gốc |
| <code>actor_token</code> và <code>actor_token_type</code> (tùy chọn) | Thông tin token của actor thực hiện hành động thay mặt subject | Ghi danh tính actor **sau khi đã xác minh**, nếu cơ chế này được sử dụng |
| <code>audience</code> hoặc <code>resource</code> (tùy chọn theo request/policy) | Bên nhận hoặc tài nguyên mong muốn | Đối chiếu nơi yêu cầu với nơi được phép cấp token |
| <code>scope</code> | Quyền được yêu cầu | So sánh requested scopes với granted scopes |
| <code>requested_token_type</code> (tùy chọn) | Loại token mong muốn nhận | Giải thích token mới là access token, JWT hoặc loại được STS hỗ trợ |

Request minh họa sau sử dụng placeholder, không chứa credential thật:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.internal
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&
subject_token=REDACTED&
subject_token_type=urn:ietf:params:oauth:token-type:access_token&
audience=inventory-api&
scope=inventory.read
~~~

Nếu STS chấp nhận, nó có thể trả một access token mới cùng metadata như <code>issued_token_type</code>, <code>token_type</code>, <code>expires_in</code> và <code>scope</code>. STS phải áp dụng chính sách xác thực, ràng buộc đối tượng nhận và cấp quyền trước khi phát hành. **Không thể suy ra rằng client có quyền exchange chỉ vì token nguồn còn hiệu lực.**

Phân biệt những danh tính thường bị trộn lẫn:

1. **Client**: ứng dụng đã được xác thực khi gọi token endpoint, ví dụ <code>orders-api</code>.
2. **Subject**: chủ thể mà quyền/token nguồn thể hiện, ví dụ người dùng <code>user-184</code>.
3. **Actor**: thực thể thực hiện hành động thay mặt subject trong mô hình ủy quyền; có thể được cung cấp qua <code>actor_token</code> hoặc suy ra theo cơ chế có kiểm chứng của STS.
4. **Issuer**: tổ chức/thành phần phát hành và chịu trách nhiệm về token.
5. **Audience/resource**: hệ thống được dự định sử dụng token mới, ví dụ <code>inventory-api</code>.

Client và actor **không tự động đồng nhất**. Khi không có actor token hoặc cơ chế delegation đáng tin cậy, audit phải biểu diễn actor là <code>null</code>/<code>unknown</code> theo schema thay vì tự bịa danh tính. JWT có thể mang claim <code>act</code> để biểu diễn actor trong ngữ cảnh delegation theo RFC 8693; opaque token có thể cần introspection hoặc dữ liệu server-side. Chỉ ghi claim đã được STS xác minh.

### 2.1 Luồng thực thi và vị trí ghi audit

~~~mermaid
sequenceDiagram
    participant C as Orders API (client)
    participant S as STS / Authorization Server
    participant A as Audit pipeline
    participant R as Inventory API
    C->>S: Token exchange request
    S->>S: Xác thực client và kiểm tra token nguồn
    S->>S: Đánh giá actor, audience, scope, policy
    alt Được cho phép
        S->>S: Phát hành token có phạm vi giới hạn
        S-->>A: TOKEN_EXCHANGE_ISSUED (metadata)
        S-->>C: Token mới + metadata
        C->>R: Gọi API bằng token mới
        R-->>A: TOKEN_USE_ACCEPTED / REJECTED (nếu được triển khai)
    else Bị từ chối
        S-->>A: TOKEN_EXCHANGE_DENIED (mã nguyên nhân)
        S-->>C: OAuth error
    end
~~~

Sơ đồ mô tả **trình tự logic**, không bắt buộc STS phải gửi log qua mạng đồng bộ. Trong thực tế, một hàng đợi bền vững, transactional outbox hoặc audit agent có thể vận chuyển sự kiện đến kho audit/SIEM. Bằng chứng <code>TOKEN_EXCHANGE_ISSUED</code> chỉ nói STS đã phát hành token; muốn xác minh token đã được dịch vụ đích chấp nhận thì cần thêm audit xác thực/ủy quyền ở dịch vụ đích.

## 3. Những câu hỏi mà audit phải trả lời

Một bản ghi tốt cho phép tái dựng các quyết định quan trọng mà không phải lưu lại token bí mật:

| Câu hỏi điều tra | Bằng chứng cần có |
| --- | --- |
| Ai thực hiện yêu cầu? | Client đã xác thực, phương thức xác thực client, tenant/zone nếu áp dụng |
| Yêu cầu thay mặt ai? | Subject đã xác minh, actor đã xác minh, kiểu delegation/impersonation nếu hệ thống hỗ trợ |
| Token nguồn đến từ đâu? | Issuer, token type, fingerprint hoặc <code>jti</code> đã xác minh, thời điểm hết hạn nếu cần |
| Muốn dùng token để làm gì? | Requested audience/resource, requested scope, loại token được yêu cầu |
| STS thực sự cho phép gì? | Granted audience, granted scopes, loại token được cấp, TTL |
| Vì sao cho phép/từ chối? | Decision, reason code chuẩn hóa, policy ID/version, kết quả kiểm tra chính |
| Sự kiện xảy ra lúc nào, ở đâu? | Thời gian UTC, service/instance, môi trường, trace/request ID |
| Có thể nối các bước liên quan không? | Exchange ID, correlation ID, token fingerprint, parent exchange ID khi có exchange dây chuyền |
| Audit có đáng tin không? | Event ID duy nhất, nguồn phát, kiểm soát quyền ghi, bảo vệ chống sửa/xóa, bằng chứng vận chuyển |

**Không ghi dữ liệu chưa xác minh như thể đó là danh tính đã xác thực.** Ví dụ, nếu chữ ký của JWT nguồn sai, giá trị <code>sub</code> do kẻ tấn công tự đặt trong payload chỉ là input không đáng tin. Audit nên ghi <code>subject_verified=false</code>, phân loại lỗi <code>INVALID_SUBJECT_TOKEN</code> và fingerprint an toàn nếu policy cho phép, thay vì ghi <code>subject_id</code> như một danh tính hợp lệ.

## 4. Thiết kế schema sự kiện audit

Một schema có phiên bản giúp dịch vụ ghi log và SIEM hiểu cùng ý nghĩa. Đặt tên nhất quán và tách rõ **requested** (được yêu cầu) khỏi **granted** (được cấp). Bảng sau là gợi ý thiết kế, **không phải schema bắt buộc của RFC 8693**.

| Nhóm | Field đề xuất | Ghi chú |
| --- | --- | --- |
| Định danh | <code>schema_version</code>, <code>event_id</code> | Phiên bản hợp đồng; event ID duy nhất để loại bản ghi gửi lặp |
| Loại và kết quả | <code>event_type</code>, <code>decision</code> | Ví dụ <code>TOKEN_EXCHANGE_ISSUED</code>/<code>DENIED</code>/<code>ERROR</code> |
| Thời gian | <code>occurred_at</code>, <code>duration_ms</code> | UTC ISO 8601; đo thời gian xử lý khi có thể |
| Nguồn | <code>service</code>, <code>environment</code>, <code>tenant_id</code> | Giới hạn trường tenant theo chính sách dữ liệu |
| Correlation | <code>exchange_id</code>, <code>request_id</code>, <code>trace_id</code> | Trace ID thuận tiện; không dùng nó làm bằng chứng danh tính |
| Client | <code>client_id</code>, <code>client_auth_method</code> | Chỉ tin <code>client_id</code> khi đã xác thực; nếu thất bại cần trạng thái riêng |
| Chủ thể | <code>subject_id</code>, <code>actor_id</code>, <code>delegation_mode</code> | Giá trị đã xác minh và tối thiểu cần thiết |
| Token nguồn | <code>subject_token_type</code>, <code>source_issuer</code>, <code>source_token_fp</code> | Fingerprint bảo vệ bằng keyed HMAC; không lưu token |
| Token được cấp | <code>issued_token_type</code>, <code>issued_token_fp</code>, <code>expires_in_seconds</code> | Chỉ xuất hiện khi issuance thực sự thành công |
| Đối tượng nhận | <code>requested_audiences</code>, <code>granted_audiences</code> | Mảng được chuẩn hóa, giữ rõ yêu cầu/đáp ứng |
| Quyền | <code>requested_scopes</code>, <code>granted_scopes</code> | Mảng được chuẩn hóa; không suy ra granted = requested |
| Quyết định policy | <code>policy_id</code>, <code>policy_version</code>, <code>reason_code</code> | Reason code hữu hạn, ổn định; tránh thông điệp lỗi tùy ý |
| Vận hành | <code>http_status</code>, <code>failure_stage</code> | Tách lỗi xác thực, validate, policy, issue, hạ tầng |
| Kiểm soát fingerprint | <code>fingerprint_key_version</code> | Hỗ trợ xoay khóa và biết lúc nào liên kết được các dấu vết |

Tùy quy định riêng, chỉ thêm IP/thiết bị/vị trí ở mức tối thiểu thật sự cần để điều tra; chúng có thể là dữ liệu cá nhân. Không nên dùng user-agent, IP hoặc thông tin từ header do client tự gửi làm danh tính bảo mật đã xác minh.

### 4.1 Sự kiện exchange thành công

Đây là ví dụ metadata **giả lập** sau khi STS xác thực và phát hành token. Các fingerprint chỉ mang tính minh họa:

~~~json
{
  "schema_version": "1.0",
  "event_id": "evt-7ef21",
  "event_type": "TOKEN_EXCHANGE_ISSUED",
  "occurred_at": "2026-11-23T09:20:18.421Z",
  "service": "central-sts",
  "environment": "production",
  "exchange_id": "exc-81a4",
  "request_id": "req-53c1",
  "trace_id": "e4e8a2fba06944f99000a1ceaa8a0e73",
  "client_id": "orders-api",
  "client_auth_method": "private_key_jwt",
  "subject_id": "user-184",
  "actor_id": "orders-api",
  "delegation_mode": "delegation",
  "subject_token_type": "access_token",
  "source_issuer": "https://auth.example.internal",
  "source_token_fp": "f8e94a5e8b8eaa708226fb09c2771964",
  "requested_audiences": ["inventory-api"],
  "granted_audiences": ["inventory-api"],
  "requested_scopes": ["inventory.read", "inventory.write"],
  "granted_scopes": ["inventory.read"],
  "issued_token_type": "access_token",
  "issued_token_fp": "f11947a2f1053bd22ad9e1326a51f4c8",
  "expires_in_seconds": 300,
  "policy_id": "orders-to-inventory",
  "policy_version": "v12",
  "decision": "ALLOW",
  "reason_code": "SCOPE_REDUCED_BY_POLICY",
  "http_status": 200,
  "duration_ms": 37,
  "fingerprint_key_version": "audit-k3"
}
~~~

Ví dụ thể hiện **STS chỉ cấp scope đọc dù client yêu cầu cả ghi**. Việc giảm quyền là một quyết định policy nên được ghi tường minh, nếu chính sách cho phép trả scope hẹp hơn. <code>actor_id</code> trong ví dụ giả định đã được xác minh bằng cơ chế delegation của hệ thống; không phải mọi token exchange đều có actor.

### 4.2 Sự kiện exchange bị từ chối

~~~json
{
  "schema_version": "1.0",
  "event_id": "evt-7ef22",
  "event_type": "TOKEN_EXCHANGE_DENIED",
  "occurred_at": "2026-11-23T09:21:02.103Z",
  "service": "central-sts",
  "exchange_id": "exc-81a5",
  "client_id": "orders-api",
  "subject_id": "user-184",
  "subject_token_type": "access_token",
  "requested_audiences": ["payment-admin-api"],
  "requested_scopes": ["payments.admin"],
  "decision": "DENY",
  "reason_code": "AUDIENCE_NOT_ALLOWED",
  "failure_stage": "POLICY_EVALUATION",
  "policy_id": "orders-token-exchange",
  "policy_version": "v12",
  "http_status": 400,
  "duration_ms": 9
}
~~~

Đối với lỗi không xác thực được client, phải bỏ trống <code>client_id</code> tin cậy hoặc biểu diễn rõ <code>client_authenticated=false</code>; không lấy trực tiếp trường client ID tự khai báo trong request làm chứng cứ. Khi từ chối trước bước cấp token, không có <code>issued_token_fp</code> hoặc <code>granted_scopes</code>.

### 4.3 Phân loại event, decision và reason code

| Event | Khi ghi | Ví dụ reason code |
| --- | --- | --- |
| <code>TOKEN_EXCHANGE_ISSUED</code> | STS đã hoàn tất phát hành token mới | <code>POLICY_APPROVED</code>, <code>SCOPE_REDUCED_BY_POLICY</code> |
| <code>TOKEN_EXCHANGE_DENIED</code> | Yêu cầu bị từ chối vì xác thực, token, quyền hoặc chính sách | <code>CLIENT_AUTH_FAILED</code>, <code>INVALID_SUBJECT_TOKEN</code>, <code>AUDIENCE_NOT_ALLOWED</code>, <code>SCOPE_NOT_ALLOWED</code>, <code>ACTOR_NOT_TRUSTED</code> |
| <code>TOKEN_EXCHANGE_ERROR</code> | Lỗi xử lý/hạ tầng chưa thể phân loại là quyết định từ chối có chủ ý | <code>KEY_SERVICE_UNAVAILABLE</code>, <code>ISSUANCE_FAILED</code> |
| <code>TOKEN_EXCHANGE_STARTED</code> (tùy chọn) | Đội bảo mật cần theo dõi request chưa có kết quả cuối cùng | Không thay thế sự kiện kết thúc; cần timeout/dedup phù hợp |

Với phần lớn hệ thống, **ít nhất một sự kiện kết thúc** (issued/denied/error) cho mỗi yêu cầu được xử lý là điểm khởi đầu tốt. Nếu triển khai thêm started event, dùng <code>exchange_id</code> liên kết thay vì đếm started và issued thành hai lần exchange. <code>reason_code</code> là mã nội bộ có chủ đích; không tuyên bố nó là OAuth error code chuẩn. OAuth error trả client (ví dụ <code>invalid_grant</code>, <code>invalid_scope</code>, <code>invalid_target</code> khi thích hợp) có thể được ánh xạ riêng để không làm lộ chi tiết chính sách.

## 5. Quy tắc bảo mật dữ liệu trong audit

### 5.1 Không bao giờ ghi secret hoặc raw token

**Không ghi** <code>subject_token</code>, <code>actor_token</code>, access token mới, refresh token, ID token, cookie, header <code>Authorization</code>, client secret, private key, chữ ký chưa che, full request body hay full response body. Bearer token bị lộ từ log vẫn có thể bị dùng cho tới khi hết hạn/thu hồi; ngay cả token hết hạn cũng tiết lộ cấu trúc và thông tin danh tính.

Không log nguyên object request/response, payload JWT đã decode hoặc thông báo exception không kiểm soát. Một payload JWT chưa xác thực có thể chứa nội dung do kẻ tấn công tự tạo; trường tùy ý có thể mang PII hoặc chuỗi cố ý gây nhiễu log. Dùng **allowlist field** của schema audit và mã hóa JSON đúng chuẩn.

### 5.2 Correlation bằng fingerprint an toàn

Để liên kết các lần exchange mà không lưu token, STS có thể tạo:

<code>source_token_fp = truncate_128bit(HMAC-SHA256(K_audit, token_bytes))</code>

Giá trị này hỗ trợ tìm các request dùng chung token nguồn hoặc nối token được cấp ở exchange A với token nguồn ở exchange B, **khi cùng phạm vi khóa HMAC và chính sách bảo mật cho phép**. Ưu tiên keyed HMAC thay cho SHA-256 trần; HMAC giảm nguy cơ thử đoán giá trị đối với token có entropy thấp hoặc token có cấu trúc có thể dự đoán. Fingerprint vẫn là dữ liệu liên kết cần hạn chế truy cập và thời gian lưu.

Ví dụ Java 17+ cho việc tính fingerprint; khóa phải được nạp từ secret manager/keystore, tuyệt đối không hardcode:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class AuditTokenFingerprint {
    private final SecretKeySpec key;

    public AuditTokenFingerprint(byte[] auditKey) {
        if (auditKey == null || auditKey.length < 32) {
            throw new IllegalArgumentException("Audit HMAC key must be at least 256 bits");
        }
        this.key = new SecretKeySpec(auditKey.clone(), "HmacSHA256");
    }

    public String fromToken(String rawToken) {
        if (rawToken == null || rawToken.isEmpty()) {
            throw new IllegalArgumentException("Missing token");
        }
        try {
            // Mac được khởi tạo riêng cho mỗi lần gọi vì không thread-safe.
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            byte[] digest = mac.doFinal(rawToken.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest, 0, 16); // 128 bit
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("Cannot compute audit fingerprint", e);
        }
    }
}
~~~

Tại service exchange, chỉ truyền chuỗi token vào hàm HMAC trong bộ nhớ, đưa **fingerprint** vào audit event, sau đó loại chuỗi token khỏi cấu trúc log. Các hệ thống cần thống nhất canonical input (chính xác byte/chuỗi của token, không tự sửa dấu cách hoặc chuẩn hóa tùy ý), phạm vi khóa, phiên bản khóa và thời gian xoay khóa. Khi xoay khóa, fingerprint cũ/mới có thể khác nhau; đưa <code>fingerprint_key_version</code> vào event để tránh suy luận sai.

Với JWT đã được kiểm tra hợp lệ, <code>jti</code> có thể là một khóa tra cứu bổ sung nếu được issuer cung cấp và policy cho phép. <code>jti</code> không phải lúc nào cũng có, không được bảo đảm duy nhất xuyên mọi issuer, và **không phải bằng chứng token chưa từng bị replay**. Với opaque token, sử dụng metadata đáng tin cậy từ STS/introspection và fingerprint để tương quan.

### 5.3 Quyền truy cập, thời gian lưu và chống sửa audit

- Gửi audit tới luồng riêng có quyền ghi hạn chế; ứng dụng thường không được tự sửa/xóa bản ghi cũ.
- Áp dụng TLS khi vận chuyển; mã hóa khi lưu; phân quyền đọc dựa trên nhiệm vụ; audit cả các lượt truy cập dữ liệu audit nhạy cảm.
- Dùng append-only/WORM hoặc cơ chế chống sửa/xóa thích hợp, xác thực nguồn gửi và theo dõi độ trễ/mất dữ liệu. Có thể ký hoặc băm theo lô để tăng khả năng chứng minh tính toàn vẹn; chỉ gọi là **tamper-evident** khi hệ thống thực sự có đối chứng và quy trình kiểm tra.
- Quy định retention, xóa đúng hạn và hạn chế PII theo yêu cầu pháp lý/chính sách tổ chức; không mặc định giữ vĩnh viễn.
- Tránh dùng dữ liệu audit làm kho token dự phòng, kho profile người dùng hoặc nơi lưu claims chưa được thẩm định.

## 6. Thời điểm phát sự kiện và tính đúng đắn khi gặp lỗi

Một lần exchange thường đi qua các cổng:

1. Nhận request và gắn <code>exchange_id</code>/<code>request_id</code>; không đưa body vào log.
2. Xác thực client và xác định identity đáng tin cậy (nếu thất bại ghi lỗi ở giai đoạn này).
3. Kiểm tra token nguồn: issuer/signature hoặc introspection, expiry, token type, audience/binding và quy tắc tin cậy.
4. Kiểm tra actor và chính sách delegation/impersonation nếu có; so khớp requested audience/resource và requested scopes với policy.
5. Hoàn thành hoặc từ chối issuance; xây dựng **sự kiện cuối cùng** từ kết quả có thật, sau đó đưa đến audit pipeline được thiết kế bền vững.

Với lỗi ở bước 2–4, không được đánh dấu subject/actor là đã xác minh nếu thực tế chưa qua kiểm tra. Nếu issuance thất bại sau khi policy cho phép, event phải là <code>ERROR</code>, không phải <code>ISSUED</code>. Nếu đã phát hành nhưng lỗi phản hồi client, phải có cơ chế phân biệt "đã tạo token" với "client đã nhận token"; không giả định hai sự kiện đồng nhất.

**Tính bền vững:** logger in ra stdout rồi mất do container restart không đủ mạnh cho yêu cầu audit quan trọng. Có thể dùng hàng đợi bền vững, transactional outbox khi dữ liệu issuance và event cùng nằm trong một transaction thích hợp, hoặc một audit transport có cơ chế retry, acknowledgement, dead-letter queue. Bảo đảm idempotency bằng <code>event_id</code> khi gửi lại. Khi audit backend lỗi, quyết định chặn thao tác nhạy cảm hay cho tiếp tục phải được policy xác định từ trước; cần có cảnh báo và khả năng đối soát, không lặng lẽ bỏ qua.

**Phân tán:** dùng thời gian UTC đồng bộ NTP, <code>trace_id</code> để nối các hop và <code>exchange_id</code> cho lần trao đổi cụ thể. Nếu token A được đổi tiếp thành token B, ghi <code>parent_exchange_id</code> hoặc fingerprint của token nguồn theo quyền truy cập để truy chuỗi. Không dựa hoàn toàn vào timestamp để suy luận thứ tự khi các node có lệch đồng hồ.

## 7. Đối chiếu với các cơ chế phòng thủ khác

Audit là thành phần quan sát và điều tra của hệ thống bảo mật token. Nó không thay thế các cơ chế bảo vệ trực tiếp:

| Rủi ro | Kiểm soát trực tiếp | Audit giúp ích gì? |
| --- | --- | --- |
| Đổi token cho audience không được phép | Policy audience/resource, xác thực client, validate token nguồn | Ghi requested/granted audience và lý do từ chối |
| Leo thang scope | Policy scope tối thiểu, chỉ cấp quyền cho phép | Đối chiếu requested/granted scopes và cảnh báo mẫu tăng quyền |
| Delegation trái phép | Xác thực actor, chính sách trust/delegation, ràng buộc subject | Truy ra actor đã xác minh, đường ủy quyền, policy/version |
| Token bị đánh cắp | TTL ngắn, ràng buộc người sở hữu (mTLS/DPoP khi hỗ trợ), bảo vệ kho token | Tìm token fingerprint xuất hiện ở client/ngữ cảnh lạ |
| Replay request/token | Kiểm tra audience, expiry, sender constraint, rate limit, replay control phù hợp use case | Phát hiện chuỗi lặp bất thường; không kết luận mọi lần tái dùng đều gian lận |
| Token đã thu hồi vẫn được dùng | Revocation/introspection và chính sách cache của resource server | Liên kết exchange với audit revoke/introspection và token use |
| Thay đổi chính sách âm thầm | Quản lý cấu hình/approval/versioning | Xác định policy version cho mỗi lần quyết định |

Đặc biệt, access token dạng bearer thường **được phép sử dụng nhiều lần trong thời hạn hiệu lực**. Vì vậy, thấy cùng fingerprint xuất hiện nhiều lần không đủ để kết luận có replay độc hại. Cần kết hợp client identity, audience, thời gian, tốc độ và hành vi thực tế; kiểm soát một lần dùng chỉ áp dụng khi hợp đồng token/token exchange quy định.

## 8. Truy vấn, phát hiện bất thường và điều tra

Các tín hiệu audit hữu ích trong SIEM:

- Tỷ lệ <code>CLIENT_AUTH_FAILED</code>, <code>INVALID_SUBJECT_TOKEN</code>, <code>AUDIENCE_NOT_ALLOWED</code> hoặc <code>SCOPE_NOT_ALLOWED</code> tăng đột ngột so với baseline.
- Một client yêu cầu liên tiếp nhiều audience mới, đặc biệt các audience đặc quyền.
- Cùng source token fingerprint được đưa tới STS từ nhiều client hoặc vùng triển khai không phù hợp với chính sách.
- Actor/delegation chain dài hoặc khác thường; scope được yêu cầu liên tục cao hơn scope được cấp.
- Token được cấp có TTL hoặc audience vượt giới hạn đã định; policy version thay đổi gần thời điểm bất thường.
- Event <code>ISSUED</code> không có dấu vết sử dụng tương ứng khi nghiệp vụ kỳ vọng, hoặc token use ở resource server không tìm được issuance tương ứng (cần xét độ trễ thu thập và các nguồn token khác).

Ví dụ truy vấn SQL minh họa trên kho audit đã chuẩn hóa:

~~~sql
SELECT client_id,
       reason_code,
       COUNT(*) AS denied_count
FROM security_audit
WHERE event_type = 'TOKEN_EXCHANGE_DENIED'
  AND occurred_at >= CURRENT_TIMESTAMP - INTERVAL '15 minutes'
GROUP BY client_id, reason_code
HAVING COUNT(*) >= 20
ORDER BY denied_count DESC;
~~~

Ngưỡng 20/15 phút chỉ là **ví dụ**, phải hiệu chỉnh theo lưu lượng, baseline và sai số vận chuyển. Cần phân biệt lỗi do triển khai client mới, sai cấu hình, rate limit và tấn công thực sự.

Kịch bản điều tra: hệ thống nhận cảnh báo nhiều request từ <code>orders-api</code> tới <code>payment-admin-api</code>. Nhân viên vận hành tra chuỗi <code>exchange_id</code>, thấy tất cả bị <code>AUDIENCE_NOT_ALLOWED</code> theo <code>policy_version=v12</code>; không có event <code>ISSUED</code> tương ứng. Kết luận kiểm chứng được là **STS đã từ chối các request quan sát được**. Chưa thể kết luận toàn hệ thống không có token hợp lệ khác hoặc không có lỗ hổng ở resource server nếu chưa đối soát audit của issuer và resource server.

Khi xử lý sự cố, thứ tự thực tế thường là xác định event/correlation, đối chiếu dấu thời gian và policy version, liên kết source/issued fingerprint, kiểm tra audit của resource server, phân loại lỗi cấu hình hay abuse, rồi thực hiện biện pháp phù hợp như vô hiệu hóa client, thu hồi token hoặc siết policy. Quyết định khắc phục không nên dựa duy nhất vào một log riêng lẻ.

## 9. Kiểm thử audit exchange

Kiểm thử phải đánh giá **cả quyết định bảo mật lẫn bằng chứng audit**. Có thể dùng bảng test case sau làm tiêu chí chấp nhận:

| Tình huống | Kết quả exchange kỳ vọng | Audit kỳ vọng |
| --- | --- | --- |
| Client hợp lệ; subject token còn hiệu lực; audience và scope được phép | Phát token mới | <code>ISSUED</code>, client/subject đã xác minh, requested/granted audience/scope và TTL đúng |
| Client yêu cầu <code>inventory.write</code> nhưng policy chỉ cho đọc và hỗ trợ downscope | Chỉ phát quyền đọc | <code>ISSUED</code> với requested khác granted, reason phản ánh downscope |
| Client authentication thất bại | Từ chối | <code>DENIED</code>; không xem client ID tự khai là danh tính đã xác thực |
| JWT nguồn sai chữ ký hoặc opaque token introspection không hợp lệ | Từ chối | <code>DENIED</code>, <code>INVALID_SUBJECT_TOKEN</code>; không tin claims từ token lỗi |
| Audience không được cấp hoặc actor không đáng tin | Từ chối | <code>DENIED</code>, reason code đúng; không có issued token fingerprint |
| Issuance service lỗi sau bước policy | Lỗi exchange | <code>ERROR</code> với stage <code>ISSUANCE</code>, không báo đã phát hành |
| Audit sink bị gián đoạn, sau đó hồi phục | Theo policy và thiết kế durability | Không mất/lặp logic event khi retry; kiểm soát dedup bằng event ID |
| Token exchange lặp với cùng source token | Theo policy, có thể được phép | Có thể truy cùng fingerprint; không tự gắn nhãn tấn công nếu hợp lệ |
| Raw token hoặc secret xuất hiện trong exception/request | Không cho xuất hiện trong audit | Test bảo đảm không có token, Authorization header, password hay full body |
| Người đọc audit không có quyền | Không được truy cập dữ liệu audit | RBAC, nhật ký truy cập, retention và bảo vệ chống sửa/xóa hoạt động |

Lưu ý kiểm tra các sự kiện ở đường lỗi thường ít được chạy qua hơn đường thành công. Nếu không thu được audit cho request bị từ chối, hệ thống mất phần dữ liệu quan trọng nhất để điều tra hành vi dò quyền.

## 10. Bài tập ứng dụng

**Bối cảnh:** Một hệ thống có <code>web-frontend</code>, <code>orders-api</code>, <code>inventory-api</code> và STS. <code>orders-api</code> đổi access token có subject là người dùng để gọi <code>inventory-api</code>. Client được phép yêu cầu <code>inventory.read</code>, không được phép <code>inventory.write</code> hoặc audience <code>payment-admin-api</code>.

1. Thiết kế event schema tối thiểu cho hai case: exchange thành công (scope đọc) và exchange bị từ chối (audience payment admin).
2. Xác định trường nào chỉ được ghi sau khi xác thực client hoặc kiểm tra subject token thành công.
3. Cho biết vì sao log nguyên <code>subject_token</code> là rủi ro, và cách dùng HMAC fingerprint để nối hai lần exchange.
4. Đề xuất truy vấn phát hiện một client cố thử nhiều audience trái phép trong 15 phút.
5. Giải thích cần thêm bằng chứng nào từ <code>inventory-api</code> để chứng minh token vừa cấp đã thực sự được sử dụng.

**Gợi ý tự đánh giá:** Lời giải tốt ghi rõ requested/granted scopes, thời gian UTC, quyết định và policy version; không nhầm client với actor; dùng subject đáng tin cậy; không lộ token; phân biệt sự kiện cấp token với sự kiện resource server chấp nhận token; và xử lý khả năng audit pipeline bị trễ hoặc gửi trùng.

## 11. Checklist khi triển khai

- [ ] Đã liệt kê rõ các outcome <code>ISSUED</code>, <code>DENIED</code>, <code>ERROR</code> và giai đoạn lỗi.
- [ ] Client, subject, actor được ghi đúng mức độ đã xác minh; thiếu actor thì giữ trống.
- [ ] Có requested và granted audience/scope tách biệt.
- [ ] Có policy ID/version, event ID, UTC timestamp và correlation/exchange ID.
- [ ] Chỉ ghi metadata an toàn; chặn raw token, client secret, headers/cookies, request/response body.
- [ ] Token fingerprint dùng HMAC với khóa bảo vệ và có phiên bản khóa.
- [ ] Có cơ chế vận chuyển bền vững, retry/dedup, giám sát mất hoặc trễ audit.
- [ ] Audit store có quyền truy cập tối thiểu, chính sách giữ/xóa dữ liệu và chống sửa phù hợp.
- [ ] Cảnh báo được hiệu chỉnh bằng baseline; cùng fingerprint lặp lại không mặc định là tấn công.
- [ ] Đã kiểm thử đường thành công, đường từ chối, lỗi hạ tầng và lỗi audit pipeline.

## Tài liệu tham khảo

- **RFC 8693 — OAuth 2.0 Token Exchange:** cơ chế exchange, subject/actor token, audience/resource và những trường phản hồi.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** token endpoint, client authentication, scope và xử lý lỗi OAuth.
- **RFC 7519 — JSON Web Token (JWT):** các registered claims như <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, <code>jti</code>.
- **RFC 8705 / RFC 9449:** các cơ chế sender-constrained access tokens dựa trên mutual TLS và DPoP để giảm rủi ro dùng token bị đánh cắp khi hệ thống hỗ trợ.

Audit exchange hiệu quả là một **dòng bằng chứng bảo mật có cấu trúc, tối thiểu hóa dữ liệu nhạy cảm, liên kết được quyết định STS với hành vi ở resource server và có thể kiểm tra tính toàn vẹn**. Thiết kế này giúp tổ chức phát hiện việc yêu cầu quá quyền, điều tra delegation và đánh giá vòng đời token mà không biến hệ thống log thành nơi phát tán credential.
