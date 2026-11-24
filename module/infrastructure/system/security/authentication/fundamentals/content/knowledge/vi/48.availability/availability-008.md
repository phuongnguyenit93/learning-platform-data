# Availability test — Kiểm thử tính sẵn sàng của hệ thống xác thực

## 1. Availability test là gì?

**Availability test** (kiểm thử tính sẵn sàng) là hoạt động kiểm tra xem hệ thống có thể tiếp tục cung cấp các chức năng xác thực và quản lý phiên ở mức dịch vụ đã cam kết hay không, trong điều kiện bình thường, tải cao, lỗi phụ thuộc và phục hồi sau sự cố. Với hệ thống authentication, “dịch vụ hoạt động” không chỉ là server trả HTTP 200; người dùng cần thực sự đăng nhập, hoàn tất MFA, tạo hoặc gia hạn session và truy cập tài nguyên theo quyền được cấp.

Ví dụ: trang đăng nhập vẫn mở được nhưng identity database đang lỗi nên không thể xác minh password. Nếu health check chỉ gọi endpoint health của web server, hệ thống có thể báo healthy dù chức năng cốt lõi đã ngừng hoạt động. Availability test cần thực hiện một hành trình đăng nhập tổng hợp bằng tài khoản kiểm thử, xác minh token/session được cấp và sau đó kết thúc phiên an toàn.

Trong chương **Availability** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, availability test kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần biết kiểm thử cả khả năng phục vụ lẫn các bất biến bảo mật: hệ thống phải phục hồi được mà không chấp nhận credential đã revoke, bỏ qua MFA, làm sống lại session cũ hoặc mở quyền truy cập khi không thể xác minh danh tính.

**Availability không có nghĩa là luôn cho phép truy cập bằng mọi giá.** Khi không thể xác minh credential hoặc trạng thái thu hồi, hệ thống có thể phải từ chối một hành động nhạy cảm để giữ an toàn. Kiểm thử cần xác nhận degraded mode đó được giới hạn đúng phạm vi, có thông báo phù hợp và có đường phục hồi.

## 2. Vì sao hệ thống xác thực cần kiểm thử availability riêng?

Authentication thường là dependency dùng chung của nhiều sản phẩm. Một lỗi nhỏ ở IdP, database, cache, KMS hoặc MFA provider có thể ảnh hưởng đồng thời tới nhiều ứng dụng và tenant.

Các nguyên nhân gián đoạn thường gặp:

- Identity database hoặc session store hết connection, quá tải hoặc mất quorum.
- KMS/HSM không sẵn sàng khiến server không thể ký, giải mã hoặc xác minh một số credential.
- MFA provider, SMS gateway, email provider hoặc push service bị chậm.
- DNS, certificate chain, OCSP/CRL hoặc clock synchronization gặp sự cố.
- Cache/revocation service lỗi làm tăng tải lên nguồn authoritative.
- Token signing key rotation hoặc cấu hình issuer sai.
- Một đợt password spraying/credential stuffing làm cạn CPU và connection.
- Deployment hoặc schema migration khiến login, refresh hay recovery thất bại.
- Failover sang region có dữ liệu session/credential chưa đồng bộ.

Kiểm thử availability giúp phát hiện điểm lỗi đơn, xác định hành vi khi dependency suy giảm và đo thời gian khôi phục. Nó cũng kiểm tra xem biện pháp bảo mật như rate limiting, revocation và MFA có hoạt động đúng khi hệ thống chịu tải hay không.

## 3. Availability khác với reliability và resilience

| Khái niệm | Trọng tâm | Câu hỏi kiểm thử |
| --- | --- | --- |
| **Availability** | Dịch vụ có sẵn để người dùng thực hiện chức năng cần thiết. | Người dùng có thể đăng nhập hoặc refresh session trong SLO không? |
| **Reliability** | Dịch vụ thực hiện đúng chức năng ổn định theo thời gian. | Login có kết quả đúng, không cấp session sai hoặc mất dữ liệu không? |
| **Resilience** | Khả năng chịu lỗi, suy giảm có kiểm soát và phục hồi. | Khi MFA provider hoặc một region lỗi, hệ thống có tiếp tục theo policy an toàn không? |
| **Recoverability** | Khả năng đưa hệ thống về trạng thái vận hành tin cậy sau sự cố. | Có thể khôi phục credential/session state mà không làm sống lại dữ liệu đã revoke không? |

Một dịch vụ có uptime cao nhưng thỉnh thoảng chấp nhận session đã revoke thì không đáng tin cậy. Một dịch vụ từ chối tất cả login khi một provider phụ bị lỗi có thể an toàn nhưng availability kém nếu có phương thức thay thế đã được phê duyệt. Cần đo đồng thời kết quả nghiệp vụ, tính đúng đắn và thời gian phục hồi.

## 4. Ranh giới hệ thống và dependency map

Trước khi kiểm thử, xác định toàn bộ hành trình xác thực và các dependency:

~~~mermaid
flowchart TD
    U["Browser / Mobile / Workload"]
    EDGE["DNS / CDN / WAF / Load balancer"]
    GW["API gateway"]
    AUTH["Authentication service"]
    IDDB[("Identity database")]
    CACHE[("Session / revocation cache")]
    KMS["KMS / HSM"]
    MFA["MFA / Passkey / Certificate services"]
    TOKEN["Token / Session service"]
    RP["Relying party / Resource APIs"]
    AUDIT["Audit / SIEM / Notification"]
    U --> EDGE --> GW --> AUTH
    AUTH <--> IDDB
    AUTH <--> CACHE
    AUTH <--> KMS
    AUTH <--> MFA
    AUTH --> TOKEN --> RP
    AUTH --> AUDIT
~~~

Dependency map cần chỉ ra:

- Thành phần nào nằm trên critical path của login, refresh, logout và recovery.
- Dependency nào có thể timeout hoặc trả lỗi từng phần.
- Thành phần nào có cache/fallback và giới hạn stale.
- Thành phần nào có trạng thái bảo mật authoritative.
- Failure domain: process, node, zone, region, provider hoặc network.
- Owner, on-call, dashboard và runbook tương ứng.

Không chỉ kiểm thử từng service riêng. Một service có thể healthy nhưng luồng end-to-end vẫn thất bại do DNS, TLS, network policy, token audience hoặc quyền truy cập giữa các service.

## 5. Xác định user journey cần kiểm thử

Availability test nên đại diện cho những hành trình người dùng thực sự cần:

| Journey | Các bước chính | Điều cần xác minh |
| --- | --- | --- |
| Password login | Gửi identifier/password, xác minh, tạo session | Credential hợp lệ được chấp nhận đúng; lỗi không làm lộ account. |
| MFA login | Password/passkey, challenge, verify factor, tạo session | Challenge có thể hoàn tất; không bypass khi provider lỗi. |
| Passkey login | Challenge WebAuthn, assertion, verify, session | Challenge/RP ID/origin đúng; verifier và credential registry sẵn sàng. |
| Certificate authentication | Client certificate, chain/status check, authorization | Trust chain và revocation status được kiểm tra theo policy. |
| Token refresh | Kiểm tra refresh token, rotation, cấp access token | Token family nhất quán; xử lý concurrency/reuse đúng. |
| Logout/revoke | Thu hồi session/token, lan truyền trạng thái | Mọi verifier từ chối trong propagation SLA. |
| Account recovery | Request, evidence, approval, replace credential | Recovery có thể hoàn tất mà không hạ assurance trái policy. |
| Federation/SSO | Redirect, callback, validate assertion/token | Issuer, audience, state, nonce và signing keys được xử lý đúng. |
| Workload authentication | Client credential, certificate hoặc signed request | Service identity có thể xác thực và scope đúng. |

Ưu tiên journey theo mức độ quan trọng và số người dùng bị ảnh hưởng. Một ứng dụng có thể cần passwordless login là critical; ứng dụng khác có thể coi recovery là luồng quan trọng nhưng không cần thực hiện liên tục trong synthetic monitoring.

## 6. SLI, SLO và error budget cho authentication

Không thể đánh giá availability chỉ bằng uptime của process. Cần Service Level Indicator (SLI) gắn với hành động người dùng:

- **Successful authentication availability:** tỷ lệ transaction hợp lệ hoàn tất thành công.
- **Authentication latency:** thời gian từ lúc bắt đầu tới kết quả xác thực.
- **MFA completion latency:** thời gian hoàn tất challenge, tách thời gian chờ người dùng khỏi thời gian xử lý provider.
- **Token refresh success:** tỷ lệ refresh hợp lệ được xử lý đúng.
- **Logout/revocation propagation:** thời gian từ commit revoke tới khi verifier từ chối.
- **Recovery availability:** tỷ lệ recovery transaction hợp lệ hoàn tất theo policy.
- **False rejection:** tỷ lệ người dùng hợp lệ bị từ chối do lỗi hệ thống.
- **Security failure rate:** tỷ lệ request không hợp lệ bị chặn đúng; không tính đây là lỗi availability.

Ví dụ SLO minh họa:

| SLI | Mục tiêu giả định |
| --- | --- |
| Login transaction hợp lệ hoàn tất | 99,9% trong cửa sổ đo đã định |
| P95 xử lý password/passkey verify | Dưới ngưỡng latency theo tải thiết kế |
| Token refresh hợp lệ | 99,9% khi dependency khỏe |
| Revoke propagation | P99 dưới giới hạn security SLA |
| Critical dependency detection | Cảnh báo trong vài phút theo runbook |

Các con số chỉ là ví dụ. Mục tiêu thực tế phải dựa trên nhu cầu sản phẩm, threat model, kiến trúc và khả năng vận hành. Không gộp login thất bại do người dùng nhập sai vào lỗi hệ thống; cần phân loại outcome.

## 7. Thiết kế health check và synthetic monitoring

Health check nên có nhiều mức:

- **Liveness:** process còn chạy và không bị deadlock.
- **Readiness:** instance có thể nhận traffic; các dependency bắt buộc ở trạng thái phù hợp.
- **Dependency health:** database, cache, KMS, IdP hoặc provider có phản hồi.
- **Synthetic journey:** một tài khoản kiểm thử thực hiện hành trình login/refresh/logout qua đường đi gần giống người dùng.

Không cho liveness endpoint gọi mọi dependency; điều đó có thể tạo cascade khi dependency chậm. Readiness cần phân biệt dependency bắt buộc với dependency tùy chọn. Synthetic monitoring nên chạy bằng account riêng, scope tối thiểu và dữ liệu không nhạy cảm.

### Synthetic account an toàn

- Tạo account riêng cho monitoring, không dùng tài khoản nhân viên.
- Chỉ cấp quyền vào tài nguyên thử nghiệm.
- Secret lưu trong secret manager, rotate theo policy.
- Không dùng recovery code hoặc credential production của người thật.
- Tách tenant/test environment khi có thể.
- Ghi nhận synthetic traffic để không làm nhiễu fraud detection.
- Đảm bảo test không kích hoạt khóa tài khoản hoặc thông báo người dùng thật.

Synthetic test phải thực hiện login thật ở mức cần thiết nhưng không tạo side effect nguy hiểm. Logout và cleanup session sau mỗi lần chạy.

## 8. Kiểm thử tải cho password authentication

Password verification thường tốn CPU/memory do dùng password hashing chậm có chủ đích. Đây là đặc tính bảo mật, nhưng có thể bị lợi dụng để gây cạn tài nguyên.

Kiểm thử cần đánh giá:

- Throughput và latency ở tải bình thường, peak và burst.
- CPU/memory khi xác minh hash với tham số production.
- Connection pool và queue depth.
- Tác động của account lookup, rate limit store và dummy hash path.
- Hành vi khi database chậm hoặc cache miss tăng.
- Password reset/change đồng thời với login.
- Throttling theo account/source/global có hoạt động đúng khi scale nhiều node.

Không giảm cost password hash chỉ để vượt load test nếu điều đó làm yếu bảo mật. Hãy scale worker, giới hạn concurrency, điều tiết request và đặt capacity phù hợp. Với identifier không tồn tại, dummy verification có thể giúp giảm timing enumeration, nhưng cần kiểm soát chi phí và rate limit để tránh DoS.

## 9. Kiểm thử MFA và các dịch vụ bên ngoài

MFA có thể phụ thuộc push provider, SMS, email, TOTP verifier, passkey authenticator hoặc dịch vụ attestation. Mỗi loại có failure mode khác nhau:

| Dependency | Failure mode | Kết quả cần kiểm thử |
| --- | --- | --- |
| Push provider | Timeout, delivery chậm, duplicate | Challenge hết hạn đúng; không tự approve; retry có giới hạn. |
| SMS gateway | Provider lỗi, throttling, SIM delivery delay | Không gửi mã vô hạn; có phương thức recovery phù hợp. |
| Email provider | Bounce, queue backlog, domain issue | Recovery không bị coi hoàn tất khi chưa xác minh. |
| TOTP verifier | Clock skew, replay store unavailable | Không chấp nhận mã cũ; xử lý thời gian có giới hạn. |
| Passkey verifier | Challenge store hoặc credential registry lỗi | Không bỏ qua signature/RP ID/origin checks. |
| Attestation service | API unavailable hoặc metadata stale | Áp dụng policy rõ; không tự nâng assurance. |

Không fallback tự động từ passkey sang SMS/email yếu khi provider lỗi. Nếu phương thức thay thế được policy cho phép, cần step-up/recovery có kiểm soát; nếu không, từ chối tạm thời và hướng dẫn người dùng.

## 10. Kiểm thử KMS/HSM và signing key

KMS/HSM có thể nằm trên critical path của token signing, decryption hoặc certificate authentication. Availability test cần kiểm tra:

- Latency và throughput của sign/verify/encrypt/decrypt.
- Quota, throttling và connection/session limit.
- Key version rotation và key state transitions.
- Failover giữa HSM partition/replica theo kiến trúc.
- Cache public key/JWKS và hành vi khi key service lỗi.
- Khả năng xác minh token cũ trong thời gian rotation.
- Quy trình backup/restore key theo custody policy.

Không cache private key ra ngoài HSM để “tăng availability” nếu threat model không cho phép. Với public verification key, có thể cache theo TTL và key rotation policy. Nếu không thể ký token mới, không phát hành token giả hoặc dùng key không được phê duyệt; có thể tạm dừng login/refresh trong phạm vi bị ảnh hưởng.

## 11. Kiểm thử session store, cache và revocation

Session store thường quyết định trạng thái active/revoked, idle timeout, refresh token family và security epoch. Kiểm thử:

- Read/write latency và connection exhaustion.
- Cache hit/miss, eviction và stale data.
- Failover, replication lag và consistency.
- Logout/revoke propagation giữa mọi region.
- Concurrent refresh và duplicate request.
- Session expiry khi clock lệch.
- Store unavailable trong lúc login, refresh hoặc logout.
- Khôi phục sau restart và disaster recovery.

Một yêu cầu quan trọng: nếu không kiểm tra được trạng thái session/credential mới nhất, hệ thống không được âm thầm coi mọi session là active. Hãy định nghĩa hành vi theo mức nhạy cảm của request.

## 12. Kiểm thử token issuer, JWKS và federation

Token issuance/validation phụ thuộc signing key, issuer metadata, JWKS, clock và cấu hình client/resource server:

- JWKS endpoint timeout hoặc trả key set không hợp lệ.
- Key rotation trong khi token cũ còn hạn.
- Cache JWKS quá hạn hoặc không refresh được.
- Issuer/audience mismatch.
- Token expiry và clock skew.
- Introspection endpoint unavailable.
- OIDC discovery hoặc federation metadata thay đổi.
- SAML signing certificate rollover.

Verifier có thể cache public key đã xác minh để giảm phụ thuộc tức thời, nhưng phải có giới hạn freshness và xử lý unknown key ID an toàn. Không chấp nhận token chỉ vì JWKS fetch thất bại; chỉ dùng key cache đã tin cậy theo policy và không bỏ kiểm tra signature, issuer, audience hoặc expiry.

## 13. Kiểm thử rate limiting và chống DoS

Availability của authentication thường bị ảnh hưởng bởi tấn công có chủ đích:

- Password spraying trên nhiều account.
- Credential stuffing từ nhiều IP.
- MFA push bombing.
- Login endpoint bị flood để tiêu tốn password hash CPU.
- Recovery/resend endpoint gửi SMS/email hàng loạt.
- Token introspection bị gọi quá mức.
- Session store hoặc KMS bị tạo tải giả.

Kiểm thử phải xác nhận rate limit hoạt động phân tán và không tạo DoS cho người dùng hợp lệ:

- Giới hạn theo account, source, subnet/ASN, device/client và toàn hệ thống.
- Progressive delay có trần, không giữ worker bằng sleep.
- Account lockout không thể bị attacker kích hoạt dễ dàng để khóa nạn nhân.
- Challenge/MFA request có cooldown và giới hạn.
- Recovery và resend có quota cùng response chống enumeration.
- WAF/gateway bảo vệ capacity nhưng không chặn nhầm toàn bộ NAT/enterprise network.

Không thử tải hoặc flood production nếu chưa có phê duyệt và giới hạn tác động. Load/DoS simulation nên chạy trong môi trường kiểm thử hoặc cửa sổ diễn tập có kiểm soát.

## 14. Fail-open và fail-closed trong authentication

Khi dependency lỗi, quyết định tiếp tục hay từ chối phải theo security boundary:

| Tình huống | Hướng xử lý tham khảo |
| --- | --- |
| Password verifier không truy cập được | Không chấp nhận password mà không xác minh; trả lỗi tạm thời. |
| Revocation store lỗi | Không tự coi credential/session là active cho hành động nhạy cảm. |
| MFA provider lỗi | Không âm thầm bỏ MFA; dùng phương thức thay thế đã được policy phê duyệt hoặc từ chối. |
| KMS không ký được token | Không phát hành token bằng key không được phê duyệt. |
| Public key cache còn fresh | Có thể tiếp tục verify chữ ký theo cache policy đã định. |
| Risk engine lỗi | Dùng fallback policy được đánh giá trước; không mặc định bỏ mọi kiểm soát. |
| Audit sink tạm lỗi | Durable outbox/spool hoặc từ chối hành động cần audit bắt buộc theo policy. |
| Notification provider lỗi | Có thể hoàn tất thao tác nếu notification không phải bước xác minh; ghi nhận và retry cảnh báo. |

Fail-closed không phải câu trả lời cho mọi dependency. Ví dụ notification delivery lỗi không nhất thiết phải chặn login nếu thông báo không phải yếu tố xác thực. Ngược lại, MFA verifier lỗi không thể được xem như MFA thành công.

## 15. Timeout, retry, circuit breaker và bulkhead

Một dependency chậm có thể giữ connection và thread, làm lỗi lan sang các chức năng khác. Kiểm thử cần xác nhận:

- Timeout riêng theo dependency và hành động.
- Retry chỉ với lỗi tạm thời và request an toàn để retry.
- Exponential backoff có jitter và giới hạn số lần.
- Không retry vô hạn hoặc tạo retry storm.
- Circuit breaker mở khi dependency liên tục lỗi, rồi half-open để kiểm tra phục hồi.
- Bulkhead tách pool/queue cho login, refresh, recovery và notification.
- Deadline tổng cho một authentication transaction.
- Idempotency cho thao tác có side effect như consume challenge hoặc rotate refresh token.

Không retry một request ký hoặc consume challenge nếu semantics không hỗ trợ idempotency. Retry mù có thể tạo token family phân nhánh, gửi nhiều OTP hoặc thực hiện hành động nhiều lần.

## 16. Degraded mode và graceful degradation

Degraded mode là trạng thái hệ thống vẫn cung cấp một số chức năng an toàn khi một dependency suy giảm:

- Cho phép verify token bằng public key cache còn hiệu lực nếu policy cho phép.
- Tạm dừng enrollment credential mới nếu attestation provider không khả dụng.
- Cho phép session hiện tại đọc tài nguyên ít nhạy cảm theo cache TTL, nhưng yêu cầu authoritative check cho hành động nhạy cảm.
- Tạm dừng password reset nếu recovery channel không thể xác minh.
- Giữ notification event trong durable queue khi provider email/push lỗi.
- Giới hạn login mới nếu identity database không sẵn sàng.

Degraded mode phải được định nghĩa trước, có thời hạn và telemetry. Không để hệ thống tự chuyển sang chế độ yếu hơn mà không có policy hoặc cảnh báo. Khi dependency phục hồi, cần reconcile các transaction pending, token family và revocation event.

## 17. Multi-zone và multi-region failover

Availability test cần kiểm tra failure domain:

| Sự cố | Điều cần xác minh |
| --- | --- |
| Một process/node chết | Load balancer loại node; session không mất hoặc bị tạo lại sai. |
| Một availability zone lỗi | Traffic chuyển sang zone còn khỏe; dependency có quorum. |
| Một region mất kết nối | Failover theo policy; không đọc trạng thái revoke stale để chấp nhận session. |
| Primary database failover | Transaction đã commit không bị mất; token/session state không rollback. |
| Event bus gián đoạn | Outbox giữ sự kiện; consumer bắt kịp sau phục hồi. |
| KMS/HSM partition lỗi | Key operation failover theo thiết kế; không export key trái policy. |
| DNS/provider outage | Phát hiện và xử lý đúng; không fallback sang endpoint không tin cậy. |

Failover cần có RTO/RPO và consistency contract. Một replica khỏe về process nhưng chậm dữ liệu có thể không an toàn để phục vụ revoke/session validation. Kiểm thử phải bao gồm cả khả năng phục hồi dữ liệu lẫn trạng thái bảo mật.

## 18. Kiểm thử recovery và disaster recovery

Recovery test xác minh hệ thống có thể phục hồi sau mất dữ liệu hoặc dịch vụ mà không làm sống lại credential đã thu hồi:

- Restore identity database và credential registry.
- Restore session store theo policy; cân nhắc buộc đăng nhập lại thay vì khôi phục session cũ.
- Khôi phục KMS/HSM key theo quorum và custody.
- Khôi phục issuer signing key/JWKS và certificate trust.
- Replay outbox/event log sau snapshot.
- Hợp nhất tombstone, security epoch, revocation và deprovisioning.
- Kiểm tra account/tenant/credential mapping.
- Xác minh refresh token family và recovery code consumed state.
- Chạy synthetic login, MFA, passkey, logout và revoke sau restore.

Backup có thể chứa trạng thái trước sự cố. Không restore thẳng vào production mà không đối chiếu sự kiện mới hơn snapshot. Nếu không thể xác minh trạng thái session/credential, revoke hoặc re-enroll theo policy an toàn hơn việc chấp nhận dữ liệu cũ.

## 19. Availability test cho account recovery

Recovery thường phụ thuộc email/SMS, helpdesk, identity proofing, risk engine và credential service. Kiểm thử:

- Recovery request có thể được tiếp nhận và theo dõi khi một provider chậm.
- OTP/recovery token có TTL, purpose binding và one-time consumption.
- Challenge đã dùng không thể dùng lại sau retry hoặc failover.
- Helpdesk workflow có approval và audit.
- Recovery channel mới không tự được tin cậy chỉ vì vừa được thêm.
- Người dùng có phương thức dự phòng khi một kênh không khả dụng.
- Recovery không hạ assurance hoặc bỏ qua account suspension.
- Thông báo và event được gửi lại idempotently sau provider outage.

Không làm recovery “luôn thành công” bằng cách bỏ xác minh khi email/SMS provider lỗi. Có thể giữ transaction pending, hướng dẫn kênh thay thế đã xác minh hoặc yêu cầu hỗ trợ theo quy trình.

## 20. Kiểm thử load, soak và stress

Ba loại kiểm thử tải trả lời các câu hỏi khác nhau:

- **Load test:** hệ thống đáp ứng tải dự kiến và peak đã xác định không?
- **Stress test:** điều gì xảy ra khi vượt capacity; hệ thống suy giảm có kiểm soát hay sụp đổ dây chuyền?
- **Soak test:** chạy tải kéo dài có gây memory leak, queue buildup, connection leak hoặc token/session state drift không?

Kịch bản cần mô phỏng phân bố thực tế: login mới, refresh token, MFA challenge, passkey verification, introspection, logout, recovery và API request. Không chỉ tạo hàng triệu request cùng một endpoint.

Đo:

- Throughput theo transaction type.
- P50/P95/P99 latency và timeout.
- Error rate phân loại theo nguyên nhân.
- CPU, memory, connection pool, queue depth.
- Database/KMS/MFA provider utilization.
- Cache hit ratio và stale/revocation propagation.
- Retry rate, circuit breaker state và thread saturation.
- False rejection/lockout của người dùng hợp lệ.

## 21. Chaos testing có kiểm soát

Chaos testing đưa lỗi có chủ đích để kiểm tra giả định resilience. Chỉ chạy trong môi trường và phạm vi đã phê duyệt:

- Kill một application node.
- Inject latency hoặc packet loss tới session store.
- Tạm dừng consumer revocation event.
- Làm KMS sandbox timeout.
- Mô phỏng MFA provider trả lỗi hoặc duplicate callback.
- Tạo replica lag.
- Restart worker trong lúc refresh rotation hoặc recovery transaction đang diễn ra.
- Mất một zone rồi phục hồi.

Mỗi thử nghiệm cần hypothesis, blast radius, stop condition, rollback và người chịu trách nhiệm. Không thực hiện chaos/DoS trên production chỉ để “xem chuyện gì xảy ra”. Với production game day, giới hạn tenant, account thử nghiệm, tải và cửa sổ thời gian; có khả năng dừng ngay.

## 22. Bảo đảm security invariant trong khi kiểm thử availability

Availability test không được đánh đổi các bất biến xác thực:

- Credential không active không được chấp nhận.
- Challenge/nonce đã consume không được dùng lại.
- MFA bắt buộc không được bypass khi provider lỗi.
- Token sai issuer, audience, signature hoặc hết hạn không được chấp nhận.
- Session đã revoke không được sống lại sau cache refresh/failover/restore.
- Authorization và tenant boundary vẫn được kiểm tra.
- Account suspended/deprovisioned không được mở lại do replica stale.
- Rate limit không được vô hiệu hóa toàn cục khi một store lỗi.
- Secret không xuất hiện trong log hoặc test report.
- Synthetic account không có quyền vượt ngoài môi trường thử nghiệm.

Một test chỉ PASS nếu cả availability target và security invariant đều đạt. Nếu hệ thống vẫn trả 200 nhưng chấp nhận token đã revoke, đó là failure nghiêm trọng chứ không phải availability success.

## 23. Mã giả: synthetic authentication journey

Mã giả minh họa một synthetic check dùng account riêng và cleanup rõ ràng:

~~~text
runSyntheticAuthCheck():
    account = loadDedicatedSyntheticAccountFromSecretManager()
    require account.environment == monitoringEnvironment
    require account.scope == minimalTestScope

    startedAt = trustedClockNow()
    transaction = beginLogin(account.identifier)

    passwordResult = submitTestCredential(
        transaction,
        account.testCredential
    )
    require passwordResult.accepted

    if transaction.requiresMfa:
        mfaResult = completeSyntheticMfaThroughApprovedTestAdapter(
            transaction
        )
        require mfaResult.verified

    session = requireSessionCreated(transaction)
    require session.principal == account.principalReference
    require session.assurance >= configuredTestAssurance

    response = callTestResourceWithSession(session)
    require response.status == expectedStatus

    revokeSession(session.id)
    require verifierRejects(session.id)

    emitSyntheticMetric(
        duration = trustedClockNow() - startedAt,
        outcome = "success"
    )
~~~

Trong triển khai thật:

- Synthetic adapter chỉ hoạt động trong test environment hoặc account được cấp riêng.
- Không ghi credential/token/session cookie vào metric hoặc log.
- MFA test phải mô phỏng theo phương thức được nhà cung cấp hỗ trợ, không bypass verifier production.
- Có timeout và cleanup nếu test thất bại giữa chừng.
- Tách synthetic traffic khỏi fraud/risk analytics bằng marker được xác thực ở server.
- Nếu revoke/cleanup thất bại, phát cảnh báo và dọn session theo runbook.

## 24. Tình huống thực tế: MFA provider bị gián đoạn

Một ứng dụng doanh nghiệp yêu cầu MFA cho mọi lần đăng nhập. Push provider gặp outage trong 20 phút. Trang login và password verifier vẫn khỏe, nhưng người dùng không nhận được push để hoàn tất đăng nhập.

### Cách xử lý không an toàn

- Tự động bỏ MFA để người dùng đăng nhập bằng password.
- Chấp nhận mọi challenge timeout như đã xác minh.
- Gửi push/SMS lặp vô hạn.
- Chuyển sang email OTP yếu hơn mà không có policy.
- Đánh dấu health check thành công chỉ vì password endpoint trả 200.

### Cách xử lý có kiểm soát

1. Synthetic journey phát hiện MFA completion thất bại và alert đúng owner.
2. Circuit breaker giới hạn request tới provider đang lỗi.
3. Login transaction giữ trạng thái pending hoặc kết thúc với lỗi tạm thời theo TTL.
4. Người dùng có thể chọn passkey/security key dự phòng nếu đã đăng ký và policy cho phép.
5. Không tạo authenticated session khi factor bắt buộc chưa hoàn tất.
6. Notification/helpdesk được dùng để hướng dẫn, không thay thế bằng chứng MFA.
7. Khi provider phục hồi, kiểm tra callback/challenge cũ đã hết hạn và không thể replay.
8. Đo recovery time, số login bị ảnh hưởng và false rejection.

## 25. Báo cáo kết quả và tiêu chí pass/fail

Mỗi availability test nên có:

- Mục tiêu, phạm vi, môi trường và thời gian chạy.
- Version ứng dụng, cấu hình và dependency versions.
- Workload profile, concurrency và dữ liệu test.
- SLI/SLO mục tiêu và ngưỡng pass/fail.
- Failure injection/hypothesis nếu có.
- Kết quả latency, throughput, error rate và resource utilization.
- Security invariant đã kiểm tra.
- Các lỗi, ảnh hưởng, false positive và giới hạn của phép thử.
- Evidence reference, dashboard và trace ID đã redact.
- Owner, remediation và thời hạn thực hiện.

Không báo “100% availability” chỉ vì synthetic check chạy một lần thành công. Báo cáo cần nêu cửa sổ đo, sample size, coverage và các dependency chưa được kiểm thử.

## 26. Checklist thiết kế availability test

- [ ] Vẽ dependency map và xác định critical path của login, MFA, passkey, refresh, logout và recovery.
- [ ] Định nghĩa SLI/SLO theo transaction hợp lệ, latency và revocation propagation.
- [ ] Phân biệt lỗi người dùng, lỗi credential, lỗi policy và lỗi hệ thống.
- [ ] Có liveness, readiness, dependency health và synthetic journey riêng.
- [ ] Dùng synthetic account/tenant riêng, scope tối thiểu và secret manager.
- [ ] Kiểm thử password hash capacity, MFA provider, KMS/HSM, session store, JWKS và federation.
- [ ] Kiểm thử rate limit, spraying/stuffing, MFA fatigue và resource exhaustion trong môi trường kiểm soát.
- [ ] Định nghĩa fail-open/fail-closed theo dependency và hành động.
- [ ] Có timeout, retry, jitter, circuit breaker, bulkhead và idempotency.
- [ ] Degraded mode không bypass MFA, signature, revocation hoặc authorization.
- [ ] Kiểm thử cache TTL, event lag, multi-zone/region và failover.
- [ ] Kiểm thử recovery/restore, RPO/RTO, tombstone và security epoch.
- [ ] Có load, stress, soak và chaos test với blast radius/stop condition.
- [ ] Giữ security invariant trong mọi failure injection.
- [ ] Không log password, OTP, token, cookie hoặc private key.
- [ ] Đo false rejection, lockout, duplicate transaction và session drift.
- [ ] Có runbook, on-call, dashboard, alert và owner rõ ràng.
- [ ] Báo cáo sample size, test window, limitations và remediation.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao health check trả HTTP 200 chưa chứng minh hệ thống xác thực sẵn sàng?

**Gợi ý:** Process có thể sống nhưng identity database, KMS hoặc MFA provider trên critical path vẫn lỗi; cần synthetic journey.

**Câu 2.** Nếu MFA provider timeout, hệ thống có nên tự bỏ qua MFA không?

**Gợi ý:** Không. Chỉ dùng phương thức thay thế đã được policy phê duyệt; nếu không thì giữ pending hoặc từ chối tạm thời.

**Câu 3.** Vì sao cần kiểm thử revocation propagation khi đo availability?

**Gợi ý:** Failover/cache có thể làm session đã revoke tiếp tục được chấp nhận; availability phải giữ security invariant.

**Câu 4.** Load test password verifier cần chú ý điều gì?

**Gợi ý:** Hash có cost chủ đích; đo CPU/memory, queue, rate limit và capacity mà không hạ tham số bảo mật.

**Câu 5.** Khi nào notification provider lỗi không nên chặn login?

**Gợi ý:** Khi notification chỉ là cảnh báo hậu sự kiện, không phải yếu tố xác thực hoặc bước phê duyệt bắt buộc. Event cần được giữ/retry.

**Câu 6.** Chaos testing production cần những giới hạn nào?

**Gợi ý:** Phạm vi phê duyệt, blast radius, account/tenant thử nghiệm, stop condition, rollback và người chịu trách nhiệm.

**Câu 7.** Vì sao restore test phải kiểm tra credential/session đã revoke?

**Gợi ý:** Snapshot cũ có thể làm sống lại trạng thái active; cần hợp nhất revocation log, tombstone và security epoch.

## 28. Ghi nhớ

**Availability test cho hệ thống xác thực phải đo được người dùng hợp lệ có hoàn tất hành trình login, MFA, passkey, refresh, logout và recovery trong SLO hay không, đồng thời giữ nguyên các bất biến bảo mật khi dependency lỗi.** Kiểm thử cần bao phủ identity database, session store, cache, KMS/HSM, MFA provider, token issuer, federation, DNS/TLS và các failure domain; kết hợp synthetic journey, load/stress/soak, fault injection và restore drill. Timeout, retry, circuit breaker, degraded mode và failover phải được thiết kế theo từng hành động. Hệ thống không được bypass MFA, chấp nhận credential đã revoke hoặc làm sống lại session cũ để đạt uptime. Một bài test chỉ thành công khi dịch vụ phục hồi có kiểm soát, trạng thái bảo mật vẫn đúng và kết quả được đo bằng SLI/SLO cùng evidence có thể kiểm tra.
