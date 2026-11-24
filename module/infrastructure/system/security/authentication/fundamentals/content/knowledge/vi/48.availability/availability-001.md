# Độ sẵn sàng của hệ thống xác thực

> **Chương:** Availability  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích cách thiết kế và vận hành hệ thống xác thực có khả năng phục vụ liên tục, phục hồi sau lỗi và chịu được tải bất thường mà vẫn giữ nguyên các ranh giới tin cậy, chính sách xác minh và kiểm soát truy cập.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Định nghĩa availability cho authentication theo kết quả người dùng và security control.
2. Xây dựng SLI, SLO, error budget và phân biệt availability với correctness.
3. Lập bản đồ dependency của login, MFA, federation, token, session và recovery.
4. Thiết kế high availability, redundancy, failover, backup và disaster recovery.
5. Chọn fail-open, fail-closed hoặc degraded mode theo loại quyết định bảo mật.
6. Áp dụng timeout, retry, circuit breaker, bulkhead, rate limit và load shedding.
7. Giữ session, token, signing key, certificate và revocation state nhất quán khi có nhiều node.
8. Xử lý outage của IdP, MFA provider, KMS, database, DNS, network và time service.
9. Triển khai health checks, metrics, alerting và runbook trong Java/Spring.
10. Kiểm thử failure mode bằng integration test, fault injection và game day.

## 2. Availability của hệ thống xác thực là gì?

**Availability** là khả năng hệ thống cung cấp chức năng cần thiết khi được gọi, trong khoảng thời gian và điều kiện đã cam kết. Với authentication, điều đó có nghĩa người dùng hợp lệ có thể xác minh danh tính và nhận session/token đúng policy; request không hợp lệ vẫn phải bị từ chối.

Không nên đo availability chỉ bằng việc web server trả HTTP 200. Một login endpoint có thể luôn trả 200 nhưng tất cả người dùng đều không đăng nhập được, hoặc hệ thống có thể trả token sai audience trong lúc failover. Cả hai đều không phải availability thành công.

Một authentication transaction có thể gồm:

1. Client kết nối tới gateway hoặc application.
2. Identity provider xác minh credential.
3. MFA/passkey/certificate challenge được xử lý nếu policy yêu cầu.
4. Account, risk và authentication context được kiểm tra.
5. Session hoặc token được tạo.
6. Signing key, session store và policy service được truy cập.
7. Client nhận kết quả và có thể sử dụng session/token.

Availability cần đo kết quả end-to-end của luồng này, đồng thời theo dõi từng dependency để xác định nguyên nhân khi transaction thất bại.

## 3. Availability không được đánh đổi correctness và security

Hệ thống xác thực phải sẵn sàng nhưng không được biến lỗi dependency thành quyền truy cập trái phép.

Ví dụ:

- Nếu MFA provider ngừng hoạt động, không tự động bỏ MFA cho tài khoản admin.
- Nếu không kiểm tra được chữ ký token, không chấp nhận token chỉ vì gateway đang quá tải.
- Nếu session đã bị revoke nhưng node chưa nhận event, cần policy nhất quán về thời gian chấp nhận tối đa.
- Nếu KMS không thể ký token, không dùng một khóa không được quản lý hoặc khóa cũ đã bị thu hồi.
- Nếu risk engine lỗi, chỉ dùng fallback đã được đánh giá cho đúng loại action.

Ba thuộc tính cần xem cùng nhau:

| Thuộc tính | Câu hỏi |
|---|---|
| Availability | Người dùng hợp lệ có hoàn tất luồng cần thiết được không? |
| Correctness | Kết quả xác thực/session/token có đúng protocol và trạng thái không? |
| Security | Hệ thống có giữ được policy, trust boundary và authorization khi có lỗi không? |

Một degraded mode tốt duy trì những chức năng an toàn còn lại. Nó không hạ thấp điều kiện xác minh mà không có quyết định rủi ro được phê duyệt.

## 4. Xác định critical user journeys

Không phải mọi endpoint trong identity platform đều có cùng mức quan trọng. Hãy xác định các journey mà người dùng và workload cần:

| Journey | Thành phần chính | Tác động khi gián đoạn |
|---|---|---|
| Đăng nhập bằng password | Login API, verifier store, abuse control, session service | Người dùng không tạo được phiên |
| Đăng nhập bằng passkey | WebAuthn RP, challenge store, browser/authenticator, account store | Không xác minh được assertion |
| MFA | TOTP/push/SMS provider hoặc authenticator app | Không hoàn tất step-up |
| OIDC/SAML federation | Authorization server, metadata/JWKS, callback, state/nonce store | SSO thất bại |
| Token issuance/refresh | Authorization server, signing key, client registry, token store | API client không lấy được token |
| Session validation | Cookie, session store, revocation/version state | Request hợp lệ bị từ chối hoặc phiên cũ bị chấp nhận |
| Logout/revocation | Session service, event bus, cache invalidation | Phiên bị thu hồi chưa mất hiệu lực toàn hệ thống |
| Account recovery | Recovery service, email/SMS, risk/approval | Người dùng mất khả năng khôi phục tài khoản |
| Workload authentication | Service identity, CA, certificate, DNS, mesh | Service-to-service call thất bại |

Đặt SLO riêng cho từng journey. Một hệ thống có thể duy trì session hiện tại dù login mới đang lỗi; ngược lại, token refresh có thể bị lỗi dù web login vẫn hoạt động.

## 5. Dependency map và failure domain

Một authentication platform thường phụ thuộc:

- DNS và service discovery.
- Load balancer, ingress và network.
- Identity provider hoặc federation provider.
- User/account database.
- Password verifier hoặc credential store.
- MFA provider và notification gateway.
- WebAuthn challenge/state store.
- Session store/cache.
- Token signing KMS/HSM và key distribution.
- Certificate authority và trust bundle.
- Policy/risk engine.
- Queue/event bus cho revocation và provisioning.
- Time synchronization.
- Observability pipeline.

~~~mermaid
flowchart TD
    U["User / Workload"] --> G["Gateway / Load balancer"]
    G --> A["Authentication service"]
    A --> DB["Account and credential store"]
    A --> M["MFA / Passkey provider"]
    A --> I["Federation / IdP"]
    A --> P["Policy and risk service"]
    A --> K["KMS / HSM signing keys"]
    A --> S["Session / token store"]
    S --> Q["Revocation event bus"]
    A --> T["Time / DNS / service discovery"]
    A --> O["Metrics, logs and audit"]
~~~

Với mỗi dependency, ghi rõ:

- Criticality đối với từng journey.
- Failure mode: timeout, unavailable, stale data, partial response hoặc corrupted state.
- Timeout/retry budget.
- Fallback được phép.
- Owner và escalation path.
- Recovery objective.
- Có single point of failure hay không.

Không phải dependency nào cũng cần fail toàn bộ platform. Ví dụ, metrics backend lỗi không nhất thiết phải ngăn login nếu audit/security event vẫn được ghi vào durable buffer theo policy. Ngược lại, không xác minh được credential hoặc signing key có thể buộc transaction phải dừng.

## 6. SLI, SLO và error budget

**SLI (Service Level Indicator)** là phép đo chất lượng dịch vụ. **SLO (Service Level Objective)** là mục tiêu cho SLI trong một cửa sổ thời gian. **Error budget** là phần lỗi hoặc downtime được phép theo SLO.

Ví dụ SLI cho login:

\[
\text{Login availability} =
\frac{\text{eligible valid login attempts completed correctly}}
{\text{eligible valid login attempts}}
\]

Denominator cần được định nghĩa cẩn thận:

- Loại request malformed hoặc không thuộc contract nếu phù hợp.
- Không loại lỗi hệ thống chỉ để làm đẹp tỷ lệ.
- Phân biệt credential sai do người dùng với dependency failure.
- Không tính login thất bại do policy deny là lỗi availability nếu hệ thống đã thực thi đúng policy.
- Theo dõi riêng security rejection và infrastructure error.

Ví dụ SLO minh họa:

| Journey | SLI | SLO ví dụ |
|---|---|---|
| Password/passkey login | Tỷ lệ eligible transaction hoàn tất đúng | 99.9% mỗi 30 ngày |
| Token issuance | Tỷ lệ request hợp lệ được cấp token đúng | 99.95% mỗi 30 ngày |
| Session validation | Tỷ lệ lookup hoàn tất trong latency budget | 99.9% mỗi 30 ngày |
| Revocation | Thời gian các node ngừng chấp nhận session đã revoke | 99% trong 30 giây |
| MFA step-up | Tỷ lệ challenge hợp lệ hoàn tất khi provider khỏe | 99.9% mỗi 30 ngày |

Các con số chỉ là ví dụ. Chọn SLO dựa trên risk appetite, kiến trúc, hợp đồng với provider và hậu quả của outage. Với revocation, cần đặt mục tiêu latency chứ không chỉ availability.

Error budget giúp quyết định khi nào nên giảm tốc độ release, ưu tiên reliability work hoặc thay đổi kiến trúc. Không dùng error budget để hợp thức hóa lỗi bảo mật.

## 7. Đo availability end-to-end

Đo ở nhiều lớp:

1. **Synthetic journey:** tài khoản test và flow được kiểm soát chạy qua login, MFA, token hoặc session.
2. **Real-user monitoring:** đo latency và kết quả thực tế đã được aggregate.
3. **Service metrics:** request rate, error rate, latency, saturation.
4. **Dependency metrics:** database, Redis, KMS, IdP, DNS và provider health.
5. **Security outcome:** số lần token/session bị từ chối đúng policy, revoke propagation và challenge failures.

Synthetic check phải dùng identity và credential test riêng, scope tối thiểu, không truy cập dữ liệu người dùng thật. Không tạo hàng nghìn login test làm nhiễu abuse detection hoặc làm tăng tải MFA provider.

Một synthetic login thành công cũng không chứng minh mọi user segment đều hoạt động. Theo dõi các client, region và authentication method có ý nghĩa nhưng giới hạn label/cardinality.

## 8. High availability và redundancy

High availability thường kết hợp:

- Nhiều application instance không chia sẻ local-only state quan trọng.
- Load balancer health-aware.
- Database replication và failover.
- Session store có replication/failover.
- Nhiều zone hoặc failure domain.
- KMS/HSM có khả năng phục vụ dự phòng.
- IdP/provider redundancy theo trust policy.
- DNS và network path dự phòng.
- Queue/event bus có replication.
- Monitoring và alert không phụ thuộc duy nhất vào hệ thống đang được giám sát.

Redundancy chỉ có ích nếu failure mode độc lập. Hai instance trên cùng một node hoặc cùng một zone không chống được lỗi node/zone. Hai region dùng chung một KMS key service duy nhất vẫn có single point of failure.

### Active-active và active-passive

| Mô hình | Ưu điểm | Rủi ro/cân nhắc |
|---|---|---|
| Active-active | Phân tải, chịu lỗi instance/zone, giảm failover time | Đồng bộ session, consistency, split-brain và duplicate processing |
| Active-passive | Mô hình state đơn giản hơn trong một số hệ thống | Failover time, standby drift và capacity chưa được kiểm chứng |
| Multi-region | Chịu lỗi vùng, hỗ trợ disaster recovery | Replication lag, data residency, key distribution và conflict resolution |

Không chọn active-active chỉ vì nghe có vẻ sẵn sàng hơn. Hãy xác định dữ liệu nào cần strongly consistent, dữ liệu nào chấp nhận eventual consistency và hành vi an toàn khi hai region mất kết nối.

## 9. Session availability và consistency

Session state có thể được lưu:

- Trong memory của từng instance.
- Trong shared store như Redis/database.
- Trong distributed cache.
- Trong signed self-contained token.
- Kết hợp opaque session handle và token.

Local in-memory session đơn giản nhưng khi instance chết hoặc load balancer chuyển request sang node khác, session có thể mất. Sticky session giảm một số lần chuyển node nhưng không loại bỏ lỗi node.

Shared store giúp các node đọc cùng trạng thái nhưng tạo dependency cần HA. Cần xem:

- Replication mode và consistency.
- Failover behavior.
- TTL/expiry semantics.
- Eviction policy.
- Connection pool và timeout.
- Session version/revocation marker.
- Khả năng invalidate cache trên mọi node.

### Failover không được hồi sinh session đã revoke

Một tình huống nguy hiểm là replica chậm chưa nhận revocation, sau đó được promote và trả lại trạng thái cũ. Thiết kế cần:

- Replication guarantees phù hợp với security state.
- Durable revocation/version marker.
- Monotonic security version hoặc epoch theo account/session.
- Reconciliation sau failover.
- Không chấp nhận replica stale vượt giới hạn an toàn.

Nếu không thể chứng minh trạng thái revoke mới nhất, hành động nhạy cảm cần fail closed hoặc yêu cầu xác minh lại theo policy.

## 10. Token availability và signing key

Token issuance phụ thuộc:

- Authorization server.
- Client registration/configuration.
- Signing key và KMS/HSM.
- Key metadata/JWKS distribution.
- Clock và expiry validation.
- Refresh token store hoặc rotation state.

Một số kiểm soát:

- Cache public verification keys có TTL và refresh strategy.
- Phân phối JWKS có version và overlap khi rotate.
- Duy trì nhiều signing key theo rotation policy, không dùng key đã compromise.
- Có KMS/HSM redundancy và kiểm tra capacity.
- Giám sát sign/decrypt latency và error.
- Không tạo token bằng khóa dự phòng không được phê duyệt.

### KMS/HSM outage

Nếu signing operation không thể thực hiện, authorization server có thể không cấp token mới. Các resource server vẫn có thể xác minh token cũ bằng public key đã cache nếu key còn được trust và token chưa hết hạn.

Không dùng private key local fallback chỉ để giữ availability nếu key đó chưa được provision, kiểm soát và audit đúng. Nếu cần offline signing capability, phải thiết kế trước: key custody, validity, usage scope, revocation và disaster procedure.

## 11. JWKS và key distribution khi dependency lỗi

Resource server thường lấy public key từ JWKS endpoint. Khi endpoint tạm lỗi:

- Có thể tiếp tục dùng key đã cache nếu cache còn trong policy freshness.
- Token dùng key ID chưa biết cần refresh key set theo giới hạn.
- Không chấp nhận chữ ký không xác minh được.
- Không bỏ qua issuer/audience/expiry chỉ vì JWKS unavailable.
- Cảnh báo khi key refresh kéo dài hoặc cache quá hạn.

Cache quá ngắn làm tăng phụ thuộc runtime vào IdP; cache vô hạn làm chậm thu hồi key bị compromise. Cần định nghĩa maximum stale age và emergency key distrust propagation.

## 12. MFA provider availability và fallback

MFA có thể phụ thuộc SMS gateway, email service, push provider hoặc external identity provider. Mỗi phương thức có failure mode khác nhau.

Nguyên tắc:

- Không tự động downgrade từ phishing-resistant factor sang SMS/email vì provider timeout.
- Cho phép user chọn authenticator dự phòng đã enroll và đáp ứng assurance policy.
- TOTP/passkey có thể ít phụ thuộc network provider hơn, nhưng vẫn phụ thuộc device, clock và verifier service.
- Backup code phải được tạo, lưu và dùng theo recovery policy.
- Push retry phải có giới hạn, tránh notification storm.
- SMS/email fallback phải được coi là lựa chọn có risk riêng, không phải tương đương passkey.

Nếu MFA provider outage, có thể cho phép những action ít rủi ro đã được policy định nghĩa, nhưng không được mở rộng quyền cho admin hoặc transaction nhạy cảm.

### Recovery không phải bypass khẩn cấp

Recovery flow phải có identity proofing và assurance phù hợp. Không bỏ MFA chỉ vì người dùng không nhận được SMS. Có thể dùng phương thức đã đăng ký khác, quy trình support xác minh độc lập hoặc recovery code có giới hạn.

## 13. Identity provider và federation outage

Nếu upstream IdP unavailable:

- Login mới qua IdP đó có thể thất bại.
- Existing RP session có thể tiếp tục trong giới hạn lifetime và risk policy.
- Token đã cấp có thể tiếp tục được resource server xác minh nếu signature/key/expiry hợp lệ.
- Token refresh hoặc step-up có thể không thực hiện được.
- Metadata/JWKS cache có thể hỗ trợ hoạt động trong khoảng stale window đã phê duyệt.

Không kéo dài session hoặc token vô hạn để che outage. Không chấp nhận token từ issuer khác như fallback nếu trust relationship chưa được cấu hình và kiểm thử.

Với ứng dụng có nhiều IdP, fallback provider phải được ràng buộc với identity mapping rõ. Không tự động liên kết account theo email giống nhau khi chuyển IdP trong tình huống khẩn cấp.

## 14. DNS, service discovery, network và certificate

Authentication phụ thuộc kết nối tới database, IdP, KMS, MFA provider và service nội bộ. DNS/network/certificate outage có thể làm luồng xác thực thất bại dù application khỏe.

Kiểm soát:

- DNS resolver dự phòng và zone được quản lý.
- Timeout phù hợp với request budget.
- Connection pool có giới hạn.
- TLS certificate rotation có overlap và monitoring.
- Trust bundle được phân phối an toàn.
- Service discovery cache có stale window rõ.
- Egress allowlist và network route dự phòng.
- Không tắt TLS validation khi certificate hoặc DNS lỗi.

Certificate hết hạn có thể làm mTLS fail trên diện rộng. Theo dõi certificate expiry, renewal success, CA health và propagation trước ngày hết hạn.

## 15. Time synchronization

Thời gian ảnh hưởng tới:

- JWT exp/nbf/iat validation.
- TOTP time step.
- Certificate validity.
- Challenge expiry.
- Session idle/absolute timeout.
- Replay window và signed request timestamp.
- Audit event ordering.

Clock drift giữa node có thể khiến token bị coi là chưa có hiệu lực hoặc đã hết hạn, TOTP liên tục sai và certificate validation thất bại.

Kiểm soát:

- Đồng bộ time source đáng tin.
- Theo dõi clock offset/drift.
- Giới hạn clock skew trong policy.
- Không tăng leeway vô hạn để che NTP outage.
- Dùng monotonic clock cho đo duration trong process.
- Dùng wall clock đã đồng bộ cho timestamp/protocol cần thời gian tuyệt đối.

Không dùng client clock làm nguồn quyết định session expiry hoặc token validity.

## 16. Database, cache và credential store

Account database và credential store thường nằm trên đường critical path:

- Account status/lock state.
- Password verifier.
- Passkey public key và credential metadata.
- TOTP verifier/seed encryption metadata.
- Recovery grant state.
- Client registration.
- Refresh token family.
- Session version/revocation state.

Thiết kế availability:

- Replication và backup có kiểm tra restore.
- Connection pool, query timeout và index phù hợp.
- Circuit breaker cho dependency chậm.
- Read replica chỉ dùng cho dữ liệu chấp nhận stale.
- Credential/revocation state cần consistency phù hợp với risk.
- Không fallback sang bản backup cũ làm account bị disable hoặc credential đã revoke trở thành active.

Không phải dữ liệu nào cũng có thể đọc stale. Profile display có thể chấp nhận eventual consistency; account disabled, credential revoked hoặc recovery grant consumed thường cần kiểm tra trạng thái mới nhất theo policy.

## 17. Fail-open, fail-closed và degraded mode

Đây là quyết định theo loại kiểm soát, không phải một cấu hình toàn hệ thống.

| Thành phần lỗi | Hành vi an toàn thường gặp | Lý do |
|---|---|---|
| Password verifier store | Fail closed cho login | Không thể xác minh credential |
| Token signature validation | Fail closed | Không chứng minh được tính hợp lệ |
| Authorization policy cho admin action | Fail closed | Không biết quyền có được phép |
| Revocation state không đồng bộ | Giới hạn theo freshness; fail closed cho action nhạy cảm | Tránh chấp nhận session đã revoke |
| MFA provider | Dùng factor dự phòng đã enroll; không downgrade ngầm | Giữ assurance |
| Risk engine | Fallback theo risk tier được phê duyệt | Tránh bỏ toàn bộ risk control |
| Metrics backend | Có thể buffer/drop noncritical metrics theo policy | Metrics không phải bằng chứng authorization |
| Audit sink | Durable buffer hoặc fail closed cho thao tác nhạy cảm | Không mất bằng chứng |
| Avatar/profile service | Degraded response | Không ảnh hưởng authentication |
| DNS/JWKS | Cache trong stale window cho key đã trust; unknown key vẫn reject | Cân bằng availability và key trust |

### Ví dụ degraded mode

- Cho phép session hiện tại tiếp tục với lifetime không vượt policy, trong khi login mới qua IdP đang lỗi.
- Cho phép user dùng passkey đã enroll thay SMS provider đang outage.
- Tạm ngừng thao tác admin nhạy cảm nhưng giữ chức năng đọc thông tin không nhạy cảm.
- Dùng public key đã cache để xác minh token hiện có trong thời gian stale window được phê duyệt.
- Queue notification để gửi sau, nhưng không coi notification failure là bằng chứng MFA đã hoàn tất.

Degraded mode phải được thiết kế và diễn tập trước. Không tạo bypass thủ công trong lúc outage nếu chưa có approval, scope và audit.

## 18. Timeout, retry và deadline propagation

Timeout ngăn một dependency chậm chiếm hết thread/connection. Mỗi request cần một overall deadline và ngân sách con cho dependency.

Ví dụ:

~~~text
Overall login deadline: 3 seconds
  account lookup: 300 ms
  password verification: bounded CPU budget
  risk check: 400 ms
  MFA provider: 1.2 seconds
  session creation: 300 ms
  response reserve: 300 ms
~~~

Đây chỉ là ví dụ. Password hashing cần đủ chi phí chống offline cracking nhưng cũng phải có concurrency limit để tránh CPU exhaustion. Không áp dụng timeout quá thấp khiến user hợp lệ thường xuyên thất bại.

Retry:

- Chỉ retry lỗi transient có thể phục hồi.
- Có exponential backoff và jitter.
- Giới hạn retry count và total deadline.
- Không retry credential rejection.
- Không retry POST side effect nếu không có idempotency contract.
- Propagate deadline xuống dependency thay vì để mỗi layer tự chờ lâu.

Retry storm có thể làm outage nặng hơn. Khi dependency quá tải, giảm retry và trả lỗi có thể phục hồi theo contract.

## 19. Circuit breaker và bulkhead

**Circuit breaker** tạm ngừng gọi dependency đang lỗi liên tục để tránh làm cạn tài nguyên và cho dependency thời gian hồi phục.

Trạng thái thường gồm:

- Closed: request được phép đi qua.
- Open: request bị chặn nhanh.
- Half-open: cho một số probe giới hạn để kiểm tra phục hồi.

**Bulkhead** tách tài nguyên để lỗi một dependency không chiếm hết thread/connection của các luồng khác.

Ví dụ:

- Pool riêng cho MFA provider.
- Pool riêng cho KMS.
- Giới hạn concurrency password verification.
- Queue riêng cho email/recovery notification.
- Thread/connection budget riêng cho session store.

Circuit breaker không được biến thành allow. Khi breaker mở, request phụ thuộc vào service đó phải nhận degraded result hoặc fail theo policy.

## 20. Rate limiting, load shedding và DDoS

Authentication endpoints là mục tiêu phổ biến của abuse:

- Password spraying/brute force.
- Credential stuffing.
- MFA push bombing.
- OTP request flooding.
- Account enumeration.
- Recovery abuse.
- Token endpoint flooding.
- Session validation amplification.

Kiểm soát:

- Rate limit theo account, client, IP/network aggregate và device/risk context phù hợp.
- Giới hạn concurrency và queue depth.
- Adaptive challenge hoặc progressive delay.
- CAPTCHA/challenge chỉ như một lớp hỗ trợ, không thay authentication.
- Bảo vệ KDF CPU budget và tránh password verification không giới hạn song song.
- Giới hạn gửi OTP/push theo recipient/account/time window.
- Load shedding có ưu tiên cho health/critical control plane.
- Dùng edge protection/WAF/DDoS mitigation.

Không chỉ rate limit theo IP vì NAT, proxy và mobile carrier có thể chia sẻ địa chỉ. Không khóa account vĩnh viễn chỉ vì attacker cố tình gửi sai password để gây denial of service.

## 21. Queue và asynchronous side effects

Một số hoạt động không cần hoàn tất trong login request:

- Gửi notification đăng nhập mới.
- Gửi email cảnh báo.
- Analytics và noncritical telemetry.
- Provisioning downstream.
- Reconciliation và cleanup.

Đưa side effect phù hợp vào queue giúp giảm latency và cô lập lỗi provider. Nhưng không được đưa bước quyết định security cần thiết ra background rồi trả thành công trước khi hoàn tất.

Ví dụ:

- Có thể queue email thông báo sau khi session đã được tạo đúng policy.
- Không thể trả login success trước khi MFA bắt buộc được xác minh.
- Có thể queue cleanup expired session.
- Không thể coi revoke hoàn tất nếu resource server vẫn chấp nhận session cũ vượt SLA.

Queue cần durable delivery, retry có giới hạn, dead-letter handling, idempotent consumer và monitoring backlog.

## 22. Health check và readiness

Health endpoint cần phân biệt:

- Liveness: process có thể tiếp tục chạy không?
- Readiness: instance có đủ dependency để nhận traffic của journey cụ thể không?
- Startup: initialization/key/configuration đã hoàn tất chưa?
- Dependency health: các dependency quan trọng có đang đáp ứng không?

Không nên đưa mọi dependency optional vào liveness. Nếu metrics backend tạm lỗi và liveness fail, orchestrator có thể restart hàng loạt instance, làm outage nặng hơn.

Readiness cần phản ánh khả năng phục vụ request theo policy. Một instance không có signing key hợp lệ có thể không ready cho token issuance; nhưng có thể vẫn phục vụ endpoint health hoặc chức năng không phụ thuộc signing.

Không trả chi tiết secret/configuration trong health response.

## 23. Disaster recovery, backup, RTO và RPO

**RTO (Recovery Time Objective)** là thời gian mục tiêu để khôi phục dịch vụ. **RPO (Recovery Point Objective)** là lượng dữ liệu có thể chấp nhận mất tính theo thời gian.

Các dữ liệu cần kế hoạch DR:

- Account và credential metadata.
- Password verifier và encrypted TOTP secret.
- Passkey public key/credential records.
- Session/revocation state.
- Refresh token family và client registration.
- Signing key/KMS/HSM key metadata.
- Certificate authority và trust bundle.
- Recovery configuration và policy.
- Audit evidence.

Backup phải được mã hóa, access-controlled và kiểm tra restore. Backup cũ không được làm sống lại account đã disable, credential đã revoke hoặc token family đã invalidated. Có thể cần lưu security epoch/revocation journal độc lập để reconcile sau restore.

Ví dụ DR plan:

1. Phát hiện primary region outage.
2. Đánh giá trust state và tính toàn vẹn của replica.
3. Promote database/session store theo runbook.
4. Khôi phục KMS/HSM access và trust bundle.
5. Kiểm tra DNS, certificate, IdP connectivity và clock.
6. Reconcile revocation/security version.
7. Chạy synthetic login/MFA/token/session journey.
8. Mở traffic dần và theo dõi error budget.

Không failover traffic chỉ dựa trên process health. Cần xác minh state, signing capability và security policy tại site dự phòng.

## 24. Certificate và key rotation không làm gián đoạn dịch vụ

Rotation là thao tác security cần thực hiện định kỳ và khi compromise. Nếu không có overlap plan, rotation có thể làm toàn bộ login/token/service call thất bại.

Một quy trình:

1. Tạo key/certificate mới trong KMS/CA.
2. Phân phối public key/trust bundle hoặc certificate chain mới.
3. Cho verifier chấp nhận cả key cũ và mới trong khoảng overlap được kiểm soát.
4. Chuyển issuer sang ký bằng key mới.
5. Xác nhận mọi consumer đã nhận metadata mới.
6. Ngừng chấp nhận key cũ theo policy.
7. Thu hồi/xóa key cũ an toàn.
8. Theo dõi lỗi signature/certificate và rollback plan.

Nếu key cũ bị compromise, không dùng overlap thông thường để tiếp tục trust key đó. Emergency rotation cần revoke nhanh và chấp nhận ảnh hưởng availability theo risk decision.

## 25. Clock, entropy và cryptographic dependencies

Authentication cần entropy cho:

- Session ID.
- OAuth state/nonce.
- WebAuthn challenge.
- Recovery token.
- API key.
- CSRF token.

Nếu CSPRNG hoặc entropy source không sẵn sàng, không thay bằng timestamp, counter hoặc PRNG yếu để duy trì availability. Tạo credential yếu còn nguy hiểm hơn trả lỗi tạm thời.

Cryptographic provider, HSM và KMS cần capacity, health monitoring, failover và key custody plan. Không tự tạo một khóa local không được quản lý khi HSM lỗi.

## 26. Java/Spring: timeout và resilience cho dependency

Ví dụ WebClient đặt timeout cho lời gọi dependency:

~~~java
@Bean
WebClient identityProviderClient(WebClient.Builder builder) {
    HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(2))
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500);

    return builder
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("https://idp.internal")
        .build();
}
~~~

Ví dụ chỉ minh họa timeout kết nối và response. Cần cấu hình thêm overall deadline, pool limits, TLS trust, mTLS nếu cần, retry policy và telemetry theo dependency. Không retry lỗi authentication hoặc certificate validation.

### Bulkhead và circuit breaker

~~~java
@Service
class MfaGateway {
    private final WebClient client;

    MfaGateway(WebClient client) {
        this.client = client;
    }

    Mono<MfaResult> verify(MfaRequest request) {
        return client.post()
            .uri("/v1/challenges/verify")
            .bodyValue(request)
            .retrieve()
            .bodyToMono(MfaResult.class)
            .timeout(Duration.ofSeconds(2));
    }
}
~~~

Trong production, áp dụng resilience operator/library như Resilience4j theo policy đã đánh giá: concurrency limit, circuit breaker và retry cho lỗi transient phù hợp. Khi breaker open, trả trạng thái MFA provider unavailable; không tự coi challenge là thành công.

## 27. Java/Spring: readiness theo capability

Một ứng dụng có thể có nhiều capability. Readiness cho token issuance cần kiểm tra signing dependency, trong khi endpoint health tổng quát có thể chỉ kiểm tra process.

~~~java
@Component
class SigningCapabilityHealthIndicator implements HealthIndicator {
    private final SigningKeyProvider keys;

    SigningCapabilityHealthIndicator(SigningKeyProvider keys) {
        this.keys = keys;
    }

    @Override
    public Health health() {
        if (keys.canSignWithActiveKey()) {
            return Health.up().build();
        }
        return Health.down()
            .withDetail("capability", "token-signing")
            .build();
    }
}
~~~

Đây là ví dụ khung. Không expose endpoint health chi tiết cho public network. Orchestrator/readiness policy cần xác định capability nào bắt buộc trước khi nhận traffic cho từng route.

## 28. Metrics và alert cho authentication availability

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| auth_login_attempts_total | Login attempts theo kết quả đã chuẩn hóa |
| auth_login_duration_seconds | Login transaction latency |
| auth_dependency_requests_total | Request tới dependency theo outcome |
| auth_dependency_duration_seconds | Dependency latency |
| auth_session_store_errors_total | Lỗi session store |
| auth_token_sign_errors_total | Lỗi token signing |
| auth_mfa_provider_errors_total | Lỗi MFA provider |
| auth_revocation_propagation_seconds | Thời gian revoke tới khi áp dụng |
| auth_queue_backlog | Công việc async đang chờ |
| auth_circuit_breaker_state | Trạng thái breaker theo dependency |

Không đưa username, session ID, token, email hoặc raw URL vào metric labels. Dùng enum bounded như dependency, method, result, environment và region.

### Prometheus query ví dụ

~~~promql
sum(rate(auth_login_attempts_total{result="success"}[5m]))
/
clamp_min(sum(rate(auth_login_attempts_total{result=~"success|system_error"}[5m])), 1)
~~~

Denominator ở ví dụ chỉ gồm success và system_error để minh họa availability theo eligible transaction; cần điều chỉnh theo instrumentation thật và không trộn credential rejection.

### Alert ví dụ

- Login system_error ratio vượt SLO trong 5 phút.
- p99 login latency vượt deadline.
- KMS signing error tăng.
- MFA provider timeout tăng.
- Session store error hoặc saturation tăng.
- Revocation propagation vượt giới hạn.
- Certificate còn ít ngày tới expiry nhưng renewal chưa thành công.
- Audit/revocation queue backlog tăng.
- Clock offset vượt ngưỡng.

Mỗi alert cần owner, severity, runbook và điều kiện đóng.

## 29. Chaos engineering và failure testing

Availability không thể được chứng minh chỉ bằng unit test hoặc dashboard xanh. Cần diễn tập lỗi dependency có kiểm soát:

- Kill một application instance.
- Tắt một zone hoặc network path.
- Tăng latency Redis/database.
- Làm KMS timeout.
- Làm MFA provider trả 5xx.
- Làm DNS resolver lỗi hoặc trả stale record.
- Tạo clock skew trong môi trường test.
- Chặn event bus để kiểm tra revocation propagation.
- Làm audit sink unavailable.
- Rotate certificate/key trong khi traffic đang chạy.
- Tăng login traffic để kiểm tra rate limit và password hashing concurrency.

Chaos test phải có blast radius giới hạn, rollback, monitoring và owner. Không chạy thử trên production nếu chưa có approval và safety guardrail.

## 30. Ma trận kiểm thử availability

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Một authentication instance chết | Load balancer chuyển traffic sang instance khỏe |
| Một zone mất kết nối | Journey tiếp tục trong capacity và policy đã thiết kế |
| Account database timeout | Login không xác minh được thì fail closed |
| Session store failover | Không hồi sinh session đã revoked |
| Redis stale replica được promote | Security version/revocation được reconcile trước khi nhận traffic nhạy cảm |
| KMS signing unavailable | Không phát token bằng khóa không được phê duyệt |
| Public JWKS key đã cache, endpoint tạm lỗi | Xác minh key đã trust trong stale window |
| Token có key ID chưa biết khi JWKS lỗi | Từ chối, không bỏ signature validation |
| MFA provider timeout | Không tự downgrade factor; dùng phương thức dự phòng đã enroll nếu policy cho phép |
| Passkey challenge store unavailable | Không chấp nhận assertion chưa được xác minh challenge |
| IdP outage | Existing session tiếp tục trong policy; login/refresh mới xử lý theo contract |
| DNS resolver lỗi | Dùng resolver dự phòng/cache hợp lệ; không bỏ TLS identity check |
| Certificate hết hạn | Kết nối bị từ chối và alert được tạo |
| Clock drift | Alert; token/TOTP policy không nới vô hạn |
| Audit sink unavailable | Durable buffer hoặc fail closed theo sensitivity |
| Metrics backend unavailable | Authentication tiếp tục nếu audit/security evidence được bảo đảm theo policy |
| Retry storm | Backoff, jitter, circuit breaker và load shedding giới hạn amplification |
| MFA push flood | Rate limit và notification quota hoạt động |
| Password spraying | Abuse controls giới hạn tải mà không khóa hàng loạt nạn nhân vô lý |
| Session revoke event bị trễ | Propagation SLO cảnh báo; action nhạy cảm kiểm tra freshness |
| Queue backlog tăng | Alert, backpressure và dead-letter handling hoạt động |
| Failover sang region dự phòng | Key, policy, revocation và account state được kiểm tra trước khi mở traffic |
| Restore backup cũ | Account/credential đã revoked không trở lại active |
| Certificate rotation trong traffic | Overlap không gây outage; key cũ bị retire đúng policy |
| Local profile trên production | Deployment guard chặn |
| Synthetic login | Hoàn tất đúng policy bằng test identity, không gây abuse alert |

Kiểm thử cả availability và security outcome. Một test pass nếu login tiếp tục hoạt động nhưng chấp nhận token sai chữ ký là test thất bại.

## 31. Tình huống phân tích

### Tình huống A: MFA provider outage

Người dùng password login thành công nhưng không nhận được push approval do provider lỗi.

**Phân tích:** Không bỏ MFA cho mọi tài khoản. Cho phép user dùng passkey hoặc TOTP đã enroll nếu policy chấp nhận; admin/high-risk action vẫn yêu cầu factor đủ assurance. Theo dõi provider health và thông báo trạng thái rõ ràng.

### Tình huống B: KMS outage khi cấp token

Authorization server không thể gọi KMS để ký access token mới.

**Phân tích:** Dừng issuance mới hoặc chuyển sang signer dự phòng đã provision và được phê duyệt. Resource server có thể tiếp tục xác minh token cũ bằng public key đã trust. Không dùng private key local tự sinh.

### Tình huống C: session store failover làm sống lại phiên cũ

Primary store đã nhận revoke nhưng replica được promote chưa có revocation marker.

**Phân tích:** Thiết kế consistency cho security state, account/session epoch và reconciliation. Không phục vụ action nhạy cảm từ replica stale khi chưa xác minh revoke state.

### Tình huống D: DNS outage

Authentication service không tìm được IdP hoặc KMS endpoint.

**Phân tích:** Resolver dự phòng, cache có stale window và service discovery được cấu hình trước. Vẫn xác minh TLS peer identity; không chuyển tới endpoint tùy ý hoặc tắt certificate validation.

### Tình huống E: retry storm làm hệ thống sụp thêm

MFA provider chậm. Mọi application node retry liên tục, làm connection pool và provider quá tải.

**Phân tích:** Deadline propagation, exponential backoff, jitter, bounded concurrency, circuit breaker và queue limit. Khi breaker mở, trả degraded result theo policy thay vì retry vô hạn.

### Tình huống F: audit backend unavailable

Secret store vẫn hoạt động nhưng audit collector không nhận event.

**Phân tích:** Dùng durable buffer hoặc từ chối thao tác nhạy cảm theo policy. Không âm thầm tiếp tục đọc secret mà không có bằng chứng; theo dõi backlog và replay event sau khi phục hồi.

## 32. Quy trình thiết kế và vận hành

Trước khi đưa authentication platform vào production, hãy xác định:

1. Critical journey nào cần SLO riêng?
2. Denominator của từng availability SLI gồm những request nào?
3. Dependency map và failure domain đã đầy đủ chưa?
4. Thành phần nào là single point of failure?
5. Session, revocation, account và credential state cần consistency mức nào?
6. KMS/HSM, CA và JWKS có redundancy/rotation plan không?
7. MFA/IdP outage có phương thức dự phòng đã enroll và policy rõ không?
8. Fail-open/fail-closed được quyết định theo từng control chưa?
9. Timeout, deadline, retry budget và concurrency limit có được cấu hình?
10. Circuit breaker/bulkhead có giữ nguyên security decision không?
11. Rate limit và load shedding có bảo vệ password KDF/MFA/recovery không?
12. DNS, certificate và clock có monitoring/fallback không?
13. Backup/restore có RTO/RPO và test định kỳ không?
14. Failover có thể làm sống lại credential/session đã revoke không?
15. Health/readiness có phản ánh đúng capability của instance không?
16. Metrics, audit và alert có hoạt động khi chính dependency lỗi không?
17. Có chaos test cho database, Redis, KMS, IdP, MFA, DNS, queue và region không?
18. Runbook có owner, escalation, rollback và communication plan không?

## 33. Ghi nhớ trọng tâm

- **Availability là hoàn tất transaction đúng policy.** HTTP 200 hoặc process UP không đủ.
- **Không đánh đổi security để giữ uptime.** Không bỏ MFA, signature validation hoặc authorization khi dependency lỗi.
- **Đo từng critical journey và dependency.** Login, token issuance, session validation, revoke và recovery có failure mode khác nhau.
- **Session và revocation cần consistency có chủ đích.** Failover không được làm sống lại session đã bị thu hồi.
- **KMS/JWKS/MFA/IdP cần fallback được thiết kế trước.** Cache và backup chỉ dùng trong freshness/assurance policy đã phê duyệt.
- **Fail-open hay fail-closed phụ thuộc control và risk.** Metrics có thể degraded; credential verification và authorization nhạy cảm thường phải fail closed.
- **Timeout, retry, circuit breaker và bulkhead ngăn lỗi lan rộng.** Retry không có budget có thể tạo outage lớn hơn.
- **Rate limiting và load shedding bảo vệ authentication khỏi abuse.** Cần giới hạn concurrency của password hashing và MFA.
- **DR phải bảo toàn security state.** Restore không được hồi sinh account, credential hoặc session đã revoke.
- **Chaos test phải xác minh cả availability lẫn correctness.** Một hệ thống vẫn nhận login nhưng chấp nhận proof sai là không đạt.

Hệ thống xác thực sẵn sàng là hệ thống có thể tiếp tục phục vụ các journey hợp lệ trong phạm vi đã cam kết, phục hồi có kiểm soát khi dependency lỗi và giữ nguyên các quyết định bảo mật. Thiết kế availability tốt bắt đầu từ failure domain và SLO rõ ràng, sau đó kết hợp redundancy, consistency, fallback có giới hạn, overload protection và diễn tập phục hồi.
