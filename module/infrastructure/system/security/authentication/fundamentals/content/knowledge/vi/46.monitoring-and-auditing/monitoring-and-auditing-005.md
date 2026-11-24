# Session metric

## 1. Session metric là gì?

**Session metric** là các chỉ số đo lường trạng thái, vòng đời, hiệu năng và mức độ an toàn của các phiên xác thực. Chúng giúp đội vận hành trả lời những câu hỏi như: có bao nhiêu phiên đang hoạt động, hệ thống tạo và làm mới phiên có ổn định không, phiên bị thu hồi có mất hiệu lực kịp thời không, thời gian sống của phiên có đúng policy không và có dấu hiệu chiếm quyền phiên hay không.

Session là trạng thái duy trì việc xác thực giữa nhiều request. Với web app, session thường được tham chiếu bằng cookie ngẫu nhiên và được lưu phía server. Với mobile hoặc API, ứng dụng có thể dùng access token, refresh token hoặc một session handle. Một số hệ thống dùng JWT tự chứa; một số dùng opaque token và tra trạng thái tại authorization server. Các mô hình này có đặc điểm quan sát khác nhau, vì vậy metric phải phản ánh đúng loại session đang được đo.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, session metric kết nối authentication, cookie, token, sign-in/sign-out, step-up, revocation, credential lifecycle và trust boundary. Mục tiêu không chỉ là đếm phiên, mà còn kiểm chứng các kiểm soát như idle timeout, absolute lifetime, rotation, concurrent-session policy và revoke có hoạt động như thiết kế hay không.

Sau bài học, người học có thể:

- Phân biệt session metric, application metric, security event và audit record.
- Mô hình hóa vòng đời session và các trạng thái có thể quan sát.
- Định nghĩa active session, session creation, refresh, expiry và revocation.
- Đo idle timeout, absolute timeout, session age và concurrent sessions.
- Theo dõi lỗi, latency và availability của session store.
- Phát hiện session anomaly, token replay và dấu hiệu account takeover.
- Thiết kế metric label có cardinality giới hạn và bảo vệ privacy.
- Phân biệt session server-side với JWT/self-contained token.
- Xây dashboard, alert và SLO cho session service.
- Kiểm thử metric, lifecycle event, revoke propagation và clock behavior.

## 2. Session và vòng đời cần được đo

Một session đại diện cho trạng thái xác thực hoặc tham chiếu tới trạng thái đó. Tùy kiến trúc, session có thể được lưu ở server, trong token hoặc kết hợp cả hai.

Một vòng đời điển hình:

1. Người dùng hoặc workload hoàn tất authentication.
2. Server tạo session hoặc cấp token.
3. Client gửi cookie/token trong các request tiếp theo.
4. Session được sử dụng và có thể được gia hạn theo policy.
5. Session hết hạn do idle timeout hoặc absolute lifetime.
6. Session có thể bị thu hồi khi logout, đổi credential, phát hiện compromise hoặc admin action.
7. Session cuối cùng bị xóa khỏi store hoặc không còn được chấp nhận.

~~~mermaid
stateDiagram-v2
    [*] --> Created: Authentication success
    Created --> Active: Session issued
    Active --> Active: Valid request / refresh
    Active --> Expired: Idle or absolute timeout
    Active --> Revoked: Logout / admin / incident
    Active --> Invalidated: Credential or policy change
    Expired --> [*]
    Revoked --> [*]
    Invalidated --> [*]
~~~

Metric nên phản ánh các chuyển trạng thái quan trọng. Nếu chỉ đếm số session record trong Redis, có thể đếm cả session hết hạn chưa được dọn, session revoked chưa xóa hoặc record orphan. Định nghĩa active phải dựa trên điều kiện hệ thống thực sự chấp nhận session.

### 2.1. Session không đồng nghĩa access token

Một access token thường có thời hạn ngắn và dùng gọi resource server. Refresh token dùng xin access token mới. Session có thể đại diện cho trạng thái đăng nhập lâu hơn cả một access token cụ thể.

Không cộng số access token, refresh token và session cookie thành một chỉ số “số phiên” duy nhất nếu chúng không cùng semantics. Ví dụ, một user session có thể tạo nhiều access token trong quá trình refresh; đếm token sẽ phóng đại số phiên người dùng.

### 2.2. Session state theo kiến trúc

| Mô hình | Nơi giữ trạng thái | Metric cần chú ý |
| --- | --- | --- |
| Server-side session | Session store hoặc database | Active records, lookup latency, TTL, eviction, revoke |
| Opaque access token | Authorization server/introspection store | Token active/revoked, introspection latency, cache freshness |
| JWT access token | Claims và chữ ký; có thể thêm denylist/session registry | Issuance, expiry, validation failure, revoke propagation |
| Refresh token family | Token family state tại authorization server | Rotation, reuse detection, revoke family |
| Mobile device session | Backend session cùng device/key reference | Device enrollment, refresh, revoke, concurrent device |
| Federated SSO session | IdP và relying party có thể có session riêng | IdP session, RP session, logout propagation |

Đặt tên metric phải nêu rõ đang đo session, access token hay refresh token. Nếu kiến trúc có nhiều lớp, dashboard nên hiển thị riêng.

## 3. Metric, log, trace và audit khác nhau

Các loại telemetry phục vụ câu hỏi khác nhau:

| Loại | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Metric** | Hệ thống đang hoạt động thế nào theo thời gian? | Session creation rate, active session gauge, refresh failure ratio |
| **Log/event** | Một sự kiện cụ thể đã xảy ra điều gì? | Session created, expired, revoked, refresh token reuse |
| **Trace** | Request đi qua những thành phần nào và chậm ở đâu? | Login → session service → Redis → API gateway |
| **Audit record** | Ai thực hiện hành động bảo mật nào, khi nào và kết quả ra sao? | Admin revoked session của principal X theo incident ticket |

Một metric như số lần revoke tăng cao có thể báo hiệu sự cố, nhưng không cho biết session nào bị revoke hoặc ai khởi tạo. Audit record có thể trả lời câu hỏi đó. Ngược lại, audit log chi tiết không thay thế metric để phát hiện xu hướng tăng bất thường.

Không dùng log raw session ID làm cách duy nhất để liên kết sự kiện. Cần reference đã bảo vệ và correlation ID.

## 4. Nhóm session metric cốt lõi

### 4.1. Session creation

Đo số session mới được tạo theo thời gian:
- Tổng session creation.
- Creation rate theo phút/giây.
- Tỷ lệ tạo session thành công trên login attempt thành công.
- Latency từ lúc authentication thành công đến lúc session sẵn sàng.
- Lỗi tạo session theo nguyên nhân.

Creation tăng đột biến có thể do traffic tăng, client retry, session fixation bug, bot login hoặc lỗi refresh tạo session mới ngoài ý muốn. Cần phân biệt login session mới với refresh token rotation hoặc session renewal.

### 4.2. Active sessions

Active session là session hiện được hệ thống coi là hợp lệ và có thể được sử dụng theo policy tại thời điểm đo. Có thể theo dõi:
- Tổng active sessions.
- Active sessions theo application/tenant/environment.
- Số active sessions trên mỗi principal dưới dạng phân phối.
- Active sessions theo device category nếu cần.
- Active sessions theo session type.

Đây thường là gauge, tức giá trị tại thời điểm quan sát. Không tính active session bằng cách cộng tất cả session-created rồi trừ session-expired nếu event có thể bị mất, trùng hoặc đến sai thứ tự. Nếu dùng event stream, cần reconciliation với source of truth.

### 4.3. Session refresh

Theo dõi:
- Refresh attempts.
- Refresh successes.
- Refresh failures.
- Refresh success ratio.
- Refresh latency.
- Refresh token reuse detections.
- Token family revocations.
- Số refresh token rotation thành công.
- Lỗi do token hết hạn, revoked, invalid signature hoặc client mismatch.

Refresh failure tăng có thể do authorization server outage, clock skew, key rotation lỗi, refresh token reuse, session revoked hoặc client gửi token cũ sau khi rotation. Cần reason code nội bộ có cấu trúc.

### 4.4. Session expiry

Theo dõi:
- Session expired do idle timeout.
- Session expired do absolute lifetime.
- Session bị từ chối vì quá hạn.
- Session record tồn tại quá TTL dự kiến.
- Cleanup lag.
- Phân phối session age tại thời điểm kết thúc.
- Tỷ lệ session kết thúc theo expiry so với logout/revoke.

Idle expiry và absolute expiry có semantics khác nhau. Không gộp thành một event “expired” nếu cần xác minh từng policy.

### 4.5. Session revocation

Theo dõi:
- Revoke requests.
- Revoke success/failure.
- Revoke latency.
- Thời gian từ khi revoke được yêu cầu tới khi mọi resource server ngừng chấp nhận session/token.
- Số session bị revoke theo logout, password reset, MFA reset, admin action hoặc incident.
- Số lần request dùng session đã revoked.
- Revoke propagation delay giữa region.

Đây là nhóm metric quan trọng với account takeover. Revoke API trả HTTP 200 chưa chứng minh token đã bị vô hiệu ở mọi nơi. Cần đo hiệu lực thực tế ở resource server hoặc introspection/cache layer.

### 4.6. Concurrent sessions

Concurrent sessions là số phiên hoạt động đồng thời của một principal hoặc một nhóm principal. Theo dõi:
- Phân phối số phiên trên mỗi principal.
- Tỷ lệ principal vượt giới hạn.
- Số lần hệ thống từ chối phiên mới vì policy.
- Số lần phiên cũ bị thay thế.
- Số thiết bị mới được đăng ký.
- Concurrent session theo user, service account hoặc device class.

Không mặc định nhiều phiên là xấu: người dùng có thể đăng nhập trên mobile, laptop và tablet. Ngưỡng phải dựa trên policy và use case. Với service account, một workload có thể có nhiều instance hợp lệ; giới hạn cần tính tới autoscaling.

## 5. Định nghĩa metric và công thức

Metric cần có tên, unit, semantics, source, aggregation, label và owner. Định nghĩa rõ giúp dashboard và alert không diễn giải sai.

| Metric | Kiểu thường dùng | Định nghĩa |
| --- | --- | --- |
| session_created_total | Counter | Tổng session được tạo thành công |
| session_creation_failed_total | Counter | Tổng lần tạo session thất bại |
| session_active | Gauge | Số session đang active theo source of truth hoặc snapshot |
| session_refresh_total | Counter | Tổng refresh attempts, phân loại result |
| session_refresh_duration_seconds | Histogram | Thời gian xử lý refresh |
| session_expired_total | Counter | Tổng session hết hạn, phân loại idle/absolute |
| session_revoked_total | Counter | Tổng session revoke thành công, phân loại reason |
| session_revoke_propagation_seconds | Histogram | Thời gian tới khi revoke có hiệu lực toàn bộ |
| session_store_request_duration_seconds | Histogram | Latency thao tác với session store |
| session_store_errors_total | Counter | Lỗi truy cập session store |
| session_validation_failed_total | Counter | Lần xác minh session thất bại theo reason |
| session_concurrent_per_principal | Histogram | Phân phối số phiên đồng thời trên principal |
| session_age_seconds | Histogram | Tuổi session tại một sự kiện kết thúc/quan sát |

### 5.1. Tỷ lệ refresh thành công

~~~text
refresh_success_ratio =
    successful_refreshes / total_refresh_attempts
~~~

Chỉ tính trong cùng cửa sổ thời gian và cùng phạm vi client/issuer. Nếu mẫu số bằng 0, hiển thị không có dữ liệu thay vì 0% thành công. Tách lỗi do client gửi token cũ với lỗi hệ thống để không tạo alert sai.

### 5.2. Tỷ lệ revoke thành công

~~~text
revoke_success_ratio =
    successful_revoke_operations / revoke_attempts
~~~

Metric này đo thao tác revoke được chấp nhận ở service. Nó chưa đo thời gian mọi verifier ngừng chấp nhận token. Bổ sung propagation latency và synthetic validation sau revoke để đánh giá end-to-end.

### 5.3. Session churn

~~~text
session_churn_rate =
    (sessions_created + sessions_ended) / average_active_sessions
~~~

Churn cao có thể biểu thị session bị tạo/hủy liên tục, token refresh gây tạo session mới, client không giữ cookie hoặc bot login/logout. Cần xác định “ended” gồm những trạng thái nào và tránh đếm một session vừa revoked vừa expired hai lần.

### 5.4. Session age

~~~text
session_age_seconds = ended_at - created_at
~~~

Phân phối tuổi session giúp đánh giá timeout policy và phát hiện session sống quá lâu. Với session còn active, có thể đo current age theo snapshot nhưng cần tránh tính từ clock không đáng tin. Không chỉ dùng average; histogram/percentile cho thấy tail dài.

### 5.5. Concurrent session distribution

Có thể đo số session active theo principal rồi xuất histogram hoặc quantile. Tránh tạo một time series riêng cho từng user ID vì cardinality và privacy. Nếu cần điều tra một principal cụ thể, dùng audit/query có quyền kiểm soát thay vì metric label.

## 6. Idle timeout, absolute timeout và session age

Session policy thường có ít nhất hai giới hạn:

- **Idle timeout:** session hết hạn nếu không có hoạt động hợp lệ trong khoảng thời gian quy định.
- **Absolute timeout:** session hết hạn sau tổng thời gian tối đa kể từ lúc tạo, bất kể có hoạt động hay refresh.

Ví dụ, ứng dụng có idle timeout 30 phút và absolute lifetime 12 giờ. Người dùng hoạt động đều có thể tránh idle timeout, nhưng vẫn phải đăng nhập lại sau 12 giờ.

Metric nên theo dõi:
- Session hết hạn do idle timeout.
- Session hết hạn do absolute timeout.
- Session bị từ chối vì quá tuổi.
- Session được gia hạn sau hoạt động hợp lệ.
- Session được giữ sống bởi request không có ý nghĩa nghiệp vụ.
- Phân phối session age tại logout/expiry.
- Số session vượt giới hạn do cleanup hoặc clock issue.

Không để polling nền hoặc health check tự động reset idle timer nếu policy định nghĩa idle là hoạt động của người dùng. Xác định rõ request nào được coi là activity.

### 6.1. Sliding expiration

Sliding expiration gia hạn thời hạn idle khi có hoạt động phù hợp. Theo dõi số lần gia hạn, tần suất ghi session store và session sống lâu bất thường.

Nếu mọi request đều cập nhật TTL, traffic nền có thể giữ session sống mãi. Cân nhắc throttle cập nhật hoặc chỉ gia hạn theo ngưỡng, nhưng phải bảo đảm semantics timeout không bị vượt policy.

### 6.2. Clock skew và expiry

Các node có clock lệch có thể đánh giá session expiry khác nhau. Dùng thời gian hệ thống được đồng bộ, kiểm soát clock drift và thống nhất đơn vị/timezone. Với timeout nội bộ, monotonic clock phù hợp để đo elapsed time; timestamp giữa node thường cần wall clock UTC.

Metric clock offset và expiry rejection có thể giúp phát hiện lỗi đồng bộ. Không tăng timeout toàn hệ thống để che một node sai clock.

## 7. Session validation và lỗi

Theo dõi các lần session validation thất bại:
- Cookie/session ID thiếu.
- Session không tồn tại.
- Session hết hạn.
- Session revoked.
- Signature/token invalid.
- Issuer/audience không đúng.
- Session binding hoặc device key mismatch.
- CSRF validation failure ở request dùng cookie.
- Session store unavailable.
- Malformed token hoặc cookie.

Phân loại reason code nội bộ giúp tìm nguyên nhân. Không phản hồi chi tiết cho caller nếu có thể tiết lộ account/session state.

Tỷ lệ validation failure tăng có thể là:
- Người dùng quay lại với cookie cũ.
- Deployment làm đổi session format.
- Clock skew.
- Cache/session store outage.
- Token signing key rotation lỗi.
- Credential stuffing hoặc replay.
- Client app gửi token cũ sau refresh rotation.

### 7.1. Đừng coi mọi invalid session là attack

Session hết hạn hoặc cookie bị xóa là hành vi bình thường. Cần baseline theo client, browser, release version và thời gian. Alert dựa trên spike, phân bố và kết hợp tín hiệu khác, không phải mỗi lần invalid session.

### 7.2. Validation latency

Đo latency theo stage:
- Cookie/token parsing.
- Signature verification.
- Session store lookup.
- Introspection.
- Revocation check.
- Policy evaluation.

Nếu p95/p99 tăng, người dùng có thể gặp login loop hoặc API timeout. Trace giúp xác định dependency gây chậm; metric tổng thể giúp theo dõi xu hướng.

## 8. Session store và hạ tầng

Với server-side session, session store là dependency bảo mật và availability quan trọng. Theo dõi:
- Read/write latency.
- Error rate.
- Connection pool saturation.
- Timeout/retry.
- Memory usage.
- Eviction.
- Expired key cleanup.
- Replication lag.
- Persistence/backup status nếu cần.
- Failover và recovery time.

Nếu session store bị eviction ngoài dự kiến, session hợp lệ có thể mất sớm. Nếu stale replica vẫn giữ session đã revoked, request có thể tiếp tục được chấp nhận. Nếu store outage khiến verifier fail-open, attacker có thể bypass session validation.

### 8.1. Cache và source of truth

Nếu có cache local/distributed, xác định đâu là source of truth. Revoke cần invalidate cache hoặc có cơ chế kiểm tra version/status đủ mới. Đo propagation lag và stale acceptance.

Không chỉ đo Redis availability; cần synthetic check tạo session, xác minh, revoke rồi xác nhận session bị từ chối trên các verifier.

### 8.2. Fail-open và fail-closed

Với session authentication, store không sẵn sàng thường nên dẫn tới từ chối tạm thời hoặc retry theo policy, đặc biệt cho thao tác nhạy cảm. Fail-open có thể cho request đi qua khi không xác minh được session.

Nếu hệ thống có degraded mode, định nghĩa endpoint nào có thể hoạt động, dữ liệu nào được phép và thời gian tối đa. Đo số request đi vào degraded mode và alert ngay khi vượt ngưỡng.

## 9. JWT và session metric

JWT access token tự chứa claims và có thể được xác minh cục bộ. Nếu không có session registry hoặc denylist, server không nhất thiết biết chính xác có bao nhiêu token đang còn hiệu lực hoặc thu hồi token đã phát hành ra sao.

Metric JWT có thể gồm:
- Access token issued.
- Token validation success/failure.
- Expired/not-before rejection.
- Issuer/audience mismatch.
- Signature verification failure.
- Key ID unknown hoặc signing key rotation issue.
- Refresh token rotation/reuse detection.
- Denylist lookup latency.
- Revocation event propagation.
- Token lifetime distribution.

Không coi số JWT được phát hành là số session active. Một session có thể có nhiều access token; một token có thể được dùng bởi nhiều request.

### 9.1. Token expiry và revocation

JWT đã ký có thể vẫn hợp lệ tới exp nếu verifier không kiểm tra revocation state. Để revoke sớm, hệ thống có thể dùng:
- Access token lifetime ngắn.
- Opaque token và introspection.
- Session/version claim tra trạng thái.
- Denylist hoặc revocation registry.
- Sender-constrained token theo profile.
- Event propagation tới verifier/cache.

Mỗi lựa chọn có trade-off giữa latency, availability, privacy và revoke speed. Metric cần đo thời gian từ revoke event tới lần xác minh đầu tiên bị từ chối.

### 9.2. Refresh token rotation

Theo dõi token family:
- Rotation success.
- Reuse detection.
- Family revoke.
- Refresh after revoke.
- Concurrent refresh race.
- Client retry sau timeout.

Reuse có thể báo hiệu token bị sao chép, nhưng cũng có thể do race/retry hợp lệ nếu client không xử lý rotation đúng. Cần correlation theo token family reference được bảo vệ, không log refresh token.

## 10. Event schema cho session lifecycle

Metric tổng hợp cần dựa trên event có semantics rõ. Một event lifecycle có thể chứa:
- Event type.
- Timestamp UTC.
- Event ID duy nhất.
- Session reference đã pseudonymize.
- Principal reference.
- Client/application reference.
- Session type.
- Authentication method/context category.
- Device category hoặc workload reference nếu cần.
- Expiry mode.
- Reason code.
- Region/instance.
- Correlation/trace ID.
- Policy version.

Ví dụ event minh họa:

~~~json
{
  "event_type": "session.revoked",
  "event_id": "evt-8f2c",
  "occurred_at": "2026-11-22T08:30:00Z",
  "session_ref": "hmac:v3:7c91...",
  "principal_ref": "usr-ref:31a...",
  "client_id": "web-portal",
  "session_type": "server_side",
  "reason": "credential_reset",
  "region": "ap-southeast",
  "correlation_id": "req-19ac"
}
~~~

Đây là schema minh họa. Không đưa raw session ID, cookie, token hoặc secret vào event. Nếu cần liên kết nhiều event, dùng keyed reference có quản lý key version và quyền truy cập.

### 10.1. Event time và processing time

Event time là thời điểm sự kiện thực sự xảy ra; processing time là thời điểm pipeline nhận/xử lý event. Chênh lệch lớn có thể chỉ ra queue lag, network delay hoặc clock skew.

Dashboard cần phân biệt hai loại. Khi tính session lifetime, dùng timestamp nguồn đáng tin cậy và xử lý event đến muộn/đảo thứ tự.

### 10.2. Event deduplication và ordering

Một event có thể được gửi lại do retry hoặc message broker delivery semantics. Dùng event ID và idempotent consumer để tránh đếm session revoke hai lần. Không giả định event stream luôn exactly-once.

Nếu session.created đến sau session.revoked do reorder, consumer cần xử lý theo event timestamp/version và source-of-truth state, không hồi sinh session chỉ vì event cũ đến muộn.

## 11. Metric naming, labels và cardinality

Metric tốt có tên ổn định, unit rõ và label có tập giá trị giới hạn.

Ví dụ:
- session_events_total với label event_type.
- session_validation_total với label result và reason_class.
- session_store_duration_seconds với label operation.
- session_active với label application và environment.
- session_refresh_total với label outcome và client_type.

Tránh label có giá trị không giới hạn:
- session_id.
- user_id/email.
- IP address.
- Full URL hoặc resource ID.
- Raw user-agent.
- Token ID hoặc credential ID.
- Error message tự do.

High cardinality làm tăng chi phí lưu trữ, giảm hiệu năng query và có thể tạo dữ liệu cá nhân trong monitoring system.

### 11.1. Phân loại thay vì ghi raw value

Thay vì label raw user-agent, dùng nhóm browser hoặc platform đã chuẩn hóa nếu thật sự cần. Thay vì IP, dùng network class/region theo policy. Thay vì email, dùng client/tenant tier hoặc aggregate.

Nếu cần điều tra principal cụ thể, truy vấn audit store bằng quyền được cấp và reference bảo vệ. Metrics system không phải nơi lưu mọi chi tiết nhận diện.

### 11.2. Histogram và percentile

Dùng histogram cho latency, session age và revoke propagation. Percentile như p50, p95, p99 cho biết tail behavior; average có thể che các request rất chậm.

Không cộng percentile giữa các instance theo cách tùy tiện. Dùng histogram bucket hoặc native histogram theo backend để tính percentile trên tổng population.

## 12. Instrumentation và telemetry pipeline

Một pipeline phổ biến:

~~~mermaid
flowchart LR
    A[Auth / Session Service] --> B[Metrics + Structured Events]
    A --> C[Trace Context]
    B --> D[Collector / Agent]
    C --> D
    D --> E[Metrics Backend]
    D --> F[Log / Event Store]
    D --> G[Trace Backend]
    F --> H[SIEM / Detection]
    E --> I[Dashboard / Alert]
    H --> I
~~~

### 12.1. Instrument tại nơi trạng thái được quyết định

Session service là nơi phù hợp để ghi nhận:
- Session create.
- Session rotate.
- Refresh.
- Expire.
- Revoke.
- Validation result.
- Store dependency result.

Không chỉ instrument ở API gateway vì gateway có thể không biết session được gia hạn, revoke hoặc xóa trong backend.

### 12.2. OpenTelemetry và metrics backend

Có thể dùng OpenTelemetry để chuẩn hóa metrics, logs và traces, rồi export tới hệ thống quan sát. Đặt tên instrument, unit và attributes nhất quán. Không đưa secret hoặc high-cardinality identifier vào span attributes.

Metrics backend như Prometheus phù hợp với counter, gauge và histogram; log/event store hoặc SIEM phù hợp với truy vấn sự kiện chi tiết. Chọn backend theo retention, access control và khả năng audit.

### 12.3. Sampling

Trace sampling giảm chi phí nhưng có thể bỏ sót request hiếm hoặc failure. Có thể dùng tail sampling ưu tiên error/high latency hoặc tạo security event riêng cho các sự kiện quan trọng như token reuse/revoke failure.

Không dựa vào sampled trace để chứng minh mọi session revoke đều đã được ghi audit. Audit quan trọng cần cơ chế delivery và retention riêng.

## 13. Dashboard session

Dashboard nên trả lời được câu hỏi vận hành, không chỉ hiển thị nhiều biểu đồ.

Một bố cục có thể gồm:

**Tổng quan**
- Active sessions hiện tại.
- Session creation rate.
- Refresh success ratio.
- Session validation failure ratio.
- Revoke success ratio.
- Session service availability.

**Vòng đời**
- Created, refreshed, expired, revoked theo thời gian.
- Idle vs absolute expiry.
- Session age p50/p95/p99.
- Concurrent sessions distribution.

**Hiệu năng**
- Create/refresh/validate latency p50/p95/p99.
- Session store latency/error/eviction.
- Introspection/cache latency.
- Revoke propagation delay.

**Security**
- Refresh token reuse.
- Spike invalid session.
- Concurrent session anomaly.
- Login/session creation burst.
- Revoked session vẫn được sử dụng.
- Session policy/config drift.

**Privacy và data quality**
- Event ingestion lag.
- Duplicate/out-of-order events.
- High-cardinality label count.
- Redaction test status.
- Retention/deletion job status.

### 13.1. Baseline theo hành vi

Không có một con số active session hoặc refresh failure phù hợp mọi sản phẩm. Baseline cần phân theo:
- Application/client.
- Environment.
- Region.
- User-facing hay service-to-service.
- Giờ cao điểm và chu kỳ batch.
- Phiên bản client.
- Loại session/token.

Không chia quá nhỏ tới mức tạo cardinality cao hoặc suy ra hoạt động cá nhân. Dùng aggregate và quyền truy cập phù hợp.

## 14. Alerting và detection

Alert cần gắn với tác động, baseline và khả năng hành động. Không alert cho mọi session expiry vì expiry là hoạt động bình thường.

Một số tín hiệu:
- Session creation tăng đột biến không tương ứng traffic.
- Refresh failure ratio vượt ngưỡng.
- Session store latency/error tăng.
- Revoke propagation chậm hơn SLA.
- Session đã revoked vẫn được chấp nhận.
- Refresh token reuse tăng.
- Concurrent sessions bất thường.
- Session age vượt absolute lifetime.
- Cleanup lag khiến record expired tồn tại lâu.
- Event ingestion bị trễ hoặc mất.
- Số invalid session tăng cùng credential stuffing signal.

### 14.1. Ví dụ alert logic

~~~text
alert RefreshFailureHigh:
    refresh_attempts >= minimum_sample
    AND refresh_failure_ratio > configured_threshold
    FOR sustained_window

alert RevokePropagationSlow:
    p95(revoke_propagation_seconds) > revoke_slo
    FOR sustained_window

alert RevokedSessionAccepted:
    accepted_request_with_revoked_session > 0
~~~

Các điều kiện và ngưỡng chỉ là mẫu. Cần hiệu chỉnh theo traffic, SLO, false positive và mức độ rủi ro. Với revoked session được chấp nhận, một lần có thể đã đủ để mở incident tùy loại API.

### 14.2. Detection không đồng nghĩa khóa account tự động

Một spike concurrent session có thể là người dùng đổi thiết bị hoặc client retry. Detection nên kết hợp nhiều tín hiệu và risk policy:
- Tạo alert hoặc step-up.
- Thu hồi một session cụ thể.
- Revoke toàn bộ session khi có bằng chứng compromise.
- Yêu cầu reauthentication.
- Tạm hạn chế action nhạy cảm.
- Gửi thông báo bảo mật.

Không khóa account vĩnh viễn chỉ từ một IP hoặc một thiết bị mới.

## 15. SLO cho session service

Service có thể định nghĩa SLI/SLO:
- Availability của session create/validate/refresh.
- p95/p99 latency cho validation.
- Refresh success ratio trong điều kiện dependency bình thường.
- Revoke propagation time.
- Tỷ lệ request bị từ chối sai do lỗi session store.
- Event delivery completeness/lag.
- Session expiry enforcement correctness.

Ví dụ mục tiêu nội bộ có thể yêu cầu p95 validation dưới một ngưỡng và p99 revoke propagation dưới một thời gian nhất định. Giá trị cụ thể phải dựa trên kiến trúc và risk acceptance, không lấy một con số chung cho mọi hệ thống.

### 15.1. Security SLI khác availability SLI

Một session service có thể có availability cao nhưng vẫn không an toàn nếu revoke chậm hoặc session sống quá policy. Vì vậy, đo cả:
- **Availability:** có thể tạo/xác minh session không?
- **Correctness:** có chấp nhận đúng session và từ chối session hết hạn/revoked không?
- **Security effectiveness:** revoke, rotation và timeout có hiệu lực trong thời gian yêu cầu không?
- **Privacy:** telemetry có tránh lộ credential và identifier không?

## 16. Privacy và audit trong session telemetry

Session metrics và audit có thể tiết lộ người dùng đăng nhập lúc nào, dùng thiết bị nào, ở đâu và sử dụng dịch vụ ra sao. Cần:
- Không log raw session ID hoặc token.
- Dùng pseudonymous reference có keyed HMAC nếu cần correlation.
- Không dùng user ID/email/IP làm metric label.
- Giảm độ chính xác vị trí khi không cần.
- Hạn chế retention và quyền đọc.
- Tách aggregate metrics khỏi audit detail.
- Redact cookie và Authorization header tại nguồn.
- Không ghi biometric template hoặc OTP.
- Có deletion/retention workflow cho log, trace và event store.
- Audit truy cập vào audit data.

### 16.1. Audit event tối thiểu

Một audit record cho revoke có thể gồm:
- Actor: user, admin hoặc security automation.
- Subject/session reference bị tác động.
- Action: revoke session.
- Reason category.
- Timestamp.
- Result.
- Correlation/incident reference.
- Policy version hoặc approval reference nếu cần.

Không cần lưu session cookie để chứng minh đã revoke. Dùng reference đã bảo vệ và lưu riêng mapping nếu có nhu cầu điều tra hợp lệ.

### 16.2. Integrity và access control

Audit record quan trọng nên được bảo vệ khỏi sửa/xóa trái phép bằng quyền ghi một chiều, storage policy, retention lock hoặc integrity mechanism phù hợp. Không để service account của ứng dụng vừa tạo audit vừa có quyền xóa lịch sử của chính nó.

## 17. Distributed session và multi-region

Trong hệ thống nhiều instance hoặc region, session state và revoke phải nhất quán đủ với yêu cầu bảo mật.

Các vấn đề:
- Session tạo ở region A nhưng request tới region B.
- Cache B chưa nhận revoke event.
- Event đến trễ hoặc đảo thứ tự.
- Clock lệch khiến expiry khác nhau.
- Replication lag làm active gauge sai.
- Session store failover làm mất hoặc hồi sinh state.
- Retry tạo duplicate event.

### 17.1. Revoke propagation

Đo thời gian từ khi revoke được commit ở source of truth tới khi:
- Cache invalidated.
- Introspection trả inactive.
- Resource server từ chối token/session.
- Tất cả region đã nhận event.

Có thể dùng synthetic session: tạo, revoke, rồi gửi request kiểm tra từ nhiều region. Đây là cách xác minh hiệu lực thay vì chỉ đo thời gian API revoke trả response.

### 17.2. Eventual consistency

Nếu dùng eventual consistency, xác định maximum stale window. Với API nhạy cảm, có thể yêu cầu online status check hoặc version check. Với nội dung ít rủi ro, policy có thể chấp nhận một khoảng propagation ngắn.

Không mô tả hệ thống là “revoke tức thời” nếu cache hoặc replica vẫn chấp nhận token trong vài phút.

### 17.3. Session cleanup và orphan records

Cleanup job có thể xóa expired records định kỳ. Theo dõi:
- Cleanup duration.
- Records scanned/deleted.
- Cleanup failures.
- Oldest expired record age.
- Orphan record count.
- Job last-success timestamp.

Record tồn tại sau expiry không nhất thiết là session còn hợp lệ, nhưng có thể làm sai active count hoặc tăng storage. Validation phải dựa trên expiry/state, không dựa vào record existence.

## 18. Incident response dựa trên session metric

Khi session metric báo bất thường:

1. Xác định metric, scope, thời điểm bắt đầu và mức độ ảnh hưởng.
2. Kiểm tra deployment, traffic spike, client version và dependency.
3. Đối chiếu lifecycle events và audit records.
4. Xác định principal/client/region bị ảnh hưởng bằng reference có kiểm soát.
5. Kiểm tra refresh token reuse, session replay và revoked-session acceptance.
6. Revoke session/token/device key khi có dấu hiệu compromise.
7. Kiểm tra revoke propagation trên tất cả verifier.
8. Đánh giá side effect và dữ liệu bị truy cập.
9. Khôi phục session service hoặc store theo runbook.
10. Thêm regression test, điều chỉnh alert và ghi incident review.

Không đưa raw session ID hoặc token vào ticket/chat. Chia sẻ correlation reference và giới hạn người có quyền tra cứu.

## 19. Ví dụ: phát hiện session bị chiếm quyền

Một ứng dụng SaaS thấy số concurrent sessions trên một nhóm account tăng nhanh, refresh token reuse cũng tăng và một số request vẫn thành công sau khi session bị revoke.

Điều tra:
1. Dashboard cho thấy session creation tăng nhưng login success không tăng tương ứng.
2. Refresh service ghi nhận token family reuse từ client/device context khác.
3. Audit cho thấy một số session bị revoke sau password reset.
4. Synthetic validation cho thấy một region vẫn chấp nhận session do cache chưa invalidated.
5. Team cô lập region/cache lỗi và revoke token family bị ảnh hưởng.
6. Backend xác minh lại session status trước action nhạy cảm.
7. Notification được gửi tới người dùng bị ảnh hưởng.
8. Regression test kiểm tra concurrent refresh, replay và multi-region revoke.

~~~mermaid
flowchart TD
    A[Concurrent sessions tăng] --> B[Refresh token reuse tăng]
    B --> C[Đối chiếu lifecycle event và audit]
    C --> D{Verifier còn chấp nhận session revoked?}
    D -- Có --> E[Cô lập cache/region và revoke]
    D -- Không --> F[Điều tra client retry hoặc hành vi hợp lệ]
    E --> G[Kiểm tra mọi region bằng synthetic request]
    F --> H[Điều chỉnh baseline/risk rule]
    G --> I[Đánh giá side effect và thông báo]
    H --> J[Regression test và incident review]
    I --> J
~~~

Metric là tín hiệu phát hiện, không tự kết luận account nào bị compromise. Cần kết hợp audit, trace, threat intelligence và xác minh business impact.

## 20. Kiểm thử session metric

| Test case | Kết quả mong đợi |
| --- | --- |
| Login tạo session thành công | Counter tăng đúng một lần |
| Login thất bại | Không tạo active session |
| Session refresh thành công | Refresh success tăng; không đếm thành session mới nếu không tạo session mới |
| Refresh token reuse | Event/metric reuse tăng và family policy được áp dụng |
| Idle timeout | Session kết thúc theo idle policy |
| Absolute timeout | Session hết hạn dù có hoạt động liên tục |
| Logout | Session revoke/end event được ghi |
| Password reset | Session liên quan bị revoke theo policy |
| Admin revoke | Actor, reason và kết quả được audit |
| Revoke propagation | Verifier từ chối trong SLA |
| Revoked session request | Bị từ chối và có metric phù hợp |
| Session store timeout | Error/latency tăng, không fail-open ngoài policy |
| Cache eviction | Không hồi sinh hoặc chấp nhận session không hợp lệ |
| Duplicate lifecycle event | Consumer không đếm hai lần |
| Event out of order | Session không bị hồi sinh bởi event cũ |
| Clock skew | Expiry được xử lý nhất quán và có telemetry |
| Concurrent sessions vượt ngưỡng | Policy và alert hoạt động đúng |
| Multi-region revoke | Tất cả region từ chối session sau propagation |
| JWT access token refresh | Không đếm mỗi access token thành một session |
| Session cleanup | Expired record được dọn và cleanup lag được đo |
| Metric label audit | Không có user ID, session ID, email, IP raw |
| Log/trace inspection | Không có cookie hoặc token thô |
| Dashboard empty traffic | Không hiển thị success ratio sai khi mẫu số bằng 0 |
| Alert low sample | Không báo động do vài request đơn lẻ nếu chưa đủ điều kiện |
| Synthetic session check | Create → validate → revoke → reject được xác nhận |

### 20.1. Kiểm thử độ chính xác metric

So sánh metric với source of truth trong môi trường test:
- Tạo N session đã biết.
- Refresh một số session.
- Revoke một phần.
- Để một phần hết idle timeout.
- Để một phần chạm absolute lifetime.
- Gửi duplicate/out-of-order events.
- Đối chiếu active count và lifecycle counters.

Không dùng production account hoặc session thật làm test fixture. Test cần kiểm tra cả trường hợp event bị mất và store unavailable.

## 21. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Định nghĩa session rõ? | Tách session, access token và refresh token |
| Active session có semantics? | Chỉ tính trạng thái thực sự được chấp nhận |
| Lifecycle có event? | Create, refresh, expire, revoke, invalidate |
| Idle/absolute timeout tách riêng? | Metric phân biệt từng policy |
| Refresh có theo dõi reuse? | Token family và client retry được phân tích |
| Revoke có đo hiệu lực? | Propagation tới mọi verifier/region |
| Concurrent sessions có baseline? | Theo principal class/use case, không giả định một ngưỡng |
| Session store được giám sát? | Latency, error, eviction, replication và cleanup |
| JWT được đếm đúng? | Không coi token issuance là session creation |
| Event schema có chuẩn? | Timestamp, event ID, reason và correlation |
| Event duplicate/order được xử lý? | Idempotency và state version |
| Metric label có bounded cardinality? | Không dùng session/user ID hoặc IP raw |
| Privacy được bảo vệ? | Pseudonymous reference, retention và access control |
| Dashboard trả lời câu hỏi vận hành? | Lifecycle, latency, security và data quality |
| Alert có actionable? | Baseline, sample threshold, owner và runbook |
| SLO có security correctness? | Revoke, expiry và validation correctness |
| Audit có integrity? | Quyền ghi/xóa tách biệt và có traceability |
| Multi-region được kiểm thử? | Revoke propagation và clock consistency |
| Incident response có quy trình? | Triage, revoke, verify, notify và review |
| Có regression test? | Replay, timeout, outage, duplicate event và privacy |

### Tình huống tự kiểm tra

**Tình huống 1:** Một user có một session đăng nhập nhưng đã nhận 10 access token trong quá trình refresh. Dashboard có nên hiển thị 10 active sessions không?

**Trả lời:** Không. Access token và session có vòng đời khác nhau. Dashboard cần đếm session theo semantics của hệ thống, không đếm mỗi access token như một phiên người dùng.

**Tình huống 2:** API revoke trả thành công. Có thể kết luận mọi region đã từ chối session ngay lập tức không?

**Trả lời:** Không. Cần đo revoke propagation và kiểm tra verifier/cache ở từng region bằng synthetic request hoặc telemetry tương đương.

**Tình huống 3:** Session record vẫn tồn tại trong Redis sau khi idle timeout. Session có còn active không?

**Trả lời:** Không nhất thiết. Active phải dựa trên expiry/state và quyết định validation, không chỉ dựa vào việc record còn tồn tại.

**Tình huống 4:** Metric dùng user_id làm label để đếm session theo từng người. Vấn đề là gì?

**Trả lời:** Cardinality tăng mạnh và metric system chứa identifier cá nhân. Dùng histogram/aggregate; điều tra một principal qua audit store với reference và quyền kiểm soát.

**Tình huống 5:** Refresh failure tăng sau khi client release phiên bản mới. Nên revoke toàn bộ user session ngay không?

**Trả lời:** Không tự động. Đối chiếu client version, reason code, token rotation và dependency trước. Có thể là bug retry hoặc gửi token cũ; revoke diện rộng chỉ khi có bằng chứng compromise hoặc policy yêu cầu.

**Tình huống 6:** JWT có exp trong tương lai nhưng account vừa bị khóa. Metric nào giúp xác minh việc khóa có hiệu lực?

**Trả lời:** Theo dõi revocation/status propagation và synthetic request tới resource server. Nếu verifier chỉ kiểm tra chữ ký/exp, JWT có thể còn được chấp nhận tới khi hết hạn.

**Tình huống 7:** Một service account có hàng trăm session do autoscaling. Có thể dùng cùng ngưỡng concurrent session như user account không?

**Trả lời:** Không. Baseline và policy phải phân biệt user principal với workload identity và tính đến số instance hợp lệ.

## 22. Ghi nhớ

**Session metric đo vòng đời, trạng thái, hiệu năng và hiệu lực bảo mật của phiên xác thực.** Cần phân biệt session với access token/refresh token; định nghĩa active session theo trạng thái thực sự được verifier chấp nhận; đo create, refresh, idle/absolute expiry, revoke, concurrent sessions, validation và session-store health.

Metric cho biết xu hướng; lifecycle event giải thích sự kiện; trace chỉ ra đường đi và latency; audit ghi actor, action, result và reason có thể điều tra. Đặc biệt, revoke API thành công chưa đủ: phải đo propagation tới mọi verifier. Dùng label có cardinality giới hạn, không log raw session ID/token, bảo vệ audit integrity và đặt retention phù hợp. Dashboard, alert, SLO và synthetic tests cần kiểm chứng cả availability lẫn correctness của timeout, rotation và revocation trong môi trường phân tán.
