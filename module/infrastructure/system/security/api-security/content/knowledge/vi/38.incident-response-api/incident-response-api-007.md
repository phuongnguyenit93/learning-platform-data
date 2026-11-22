# Post-incident review và cập nhật control

Sau khi một sự cố bảo mật API được khống chế và dịch vụ đã phục hồi, tổ chức cần xem lại toàn bộ diễn biến để hiểu điều gì đã xảy ra, vì sao các lớp bảo vệ không ngăn hoặc phát hiện sớm hơn, dữ liệu và khách hàng nào bị ảnh hưởng, và cần thay đổi control nào để giảm khả năng tái diễn. Hoạt động này thường được gọi là post-incident review hoặc postmortem.

Post-incident review không chỉ là viết báo cáo sự cố hay tìm người chịu trách nhiệm. Mục tiêu là chuyển bằng chứng và bài học từ một incident cụ thể thành thay đổi có thể kiểm chứng trong thiết kế API, cấu hình, quy trình vận hành, kiểm thử và giám sát. Một review có giá trị phải dẫn tới action item có owner, thời hạn, mức ưu tiên và tiêu chí xác nhận hoàn thành.

Trong API security, review cần xem xét cả endpoint, principal, object, tenant, business flow, gateway, dependency, message consumer và các đường truy cập nội bộ. Một request có thể vượt qua authentication nhưng vẫn khai thác lỗi object-level authorization; một webhook hợp lệ về chữ ký vẫn có thể bị replay; một service đã phục hồi nhưng secret cũ chưa bị revoke vẫn để lại nguy cơ.

## 1. Mục tiêu của post-incident review

Một review tốt cần trả lời được các câu hỏi:

- Điều gì đã xảy ra, trong khoảng thời gian nào và qua những thành phần nào?
- Kẻ tấn công hoặc nguyên nhân sự cố đã khai thác điều kiện nào?
- Endpoint, account, token, tenant, resource và business flow nào bị ảnh hưởng?
- Dữ liệu nào đã bị xem, sửa, xóa, xuất hoặc gửi tới bên thứ ba?
- Control nào đã hoạt động đúng, control nào thiếu, sai cấu hình hoặc không được giám sát?
- Vì sao detection, triage, containment và recovery mất khoảng thời gian như vậy?
- Những thay đổi nào giúp ngăn ngừa, phát hiện, giới hạn tác động hoặc phục hồi nhanh hơn?
- Làm thế nào chứng minh các thay đổi đã có hiệu lực và không tạo regression?

Review nên hướng tới cải thiện hệ thống và quy trình. Tránh quy kết một cá nhân chỉ vì họ là người cuối cùng thao tác; cần phân tích cả thiết kế, quyền hạn, hướng dẫn, tooling, tải công việc và điều kiện khiến hành động đó trở nên khả thi.

### 1.1. Phân biệt các hoạt động sau sự cố

| Hoạt động | Mục tiêu | Đầu ra |
|---|---|---|
| Incident response | Phát hiện, phân loại, containment và xử lý sự cố đang diễn ra | Incident được khống chế, evidence được bảo toàn |
| Recovery | Khôi phục dịch vụ và kiểm tra trạng thái an toàn | Service hoạt động lại với control cần thiết |
| Post-incident review | Phân tích diễn biến, nguyên nhân, tác động và bài học | Review report, control gap và action item |
| Remediation | Thực hiện thay đổi kỹ thuật/vận hành đã thống nhất | Code, policy, cấu hình, runbook hoặc training được cập nhật |
| Validation/assurance | Xác minh remediation có hiệu quả | Test evidence, metric, audit hoặc sign-off |

Không nên coi incident đã đóng là mọi action item đã hoàn tất. Incident có thể được đóng khi nguy cơ tức thời đã được kiểm soát; các remediation dài hạn vẫn cần owner và theo dõi riêng.

## 2. Khi nào tổ chức cần thực hiện review?

Nên có review chính thức cho các sự cố có ảnh hưởng đáng kể hoặc có bài học liên quan tới control, ví dụ:

- Truy cập trái phép dữ liệu hoặc hành động của tenant khác.
- Token, API key, signing key hoặc secret bị lộ, sử dụng sai hoặc không thể thu hồi đúng hạn.
- Authentication/authorization bypass, BOLA/IDOR hoặc privilege escalation.
- SSRF, injection, unsafe deserialization hoặc lạm dụng endpoint gây ảnh hưởng hệ thống.
- Abuse rate, credential stuffing, scraping hoặc chiếm dụng tài nguyên quy mô lớn.
- Webhook/event bị giả mạo, replay hoặc xử lý sai tenant context.
- API gateway, WAF, identity provider hoặc authorization service cấu hình sai gây exposure hoặc outage.
- Logging, alerting hoặc incident workflow không phát hiện/không phản ứng đúng như thiết kế.
- Sự cố lặp lại dù remediation trước đó đã được đánh dấu hoàn thành.

Có thể áp dụng review nhẹ cho sự cố nhỏ hoặc near miss. Near miss cũng có giá trị: một request độc hại bị chặn bởi rule tạm thời có thể cho thấy một control chính thức đang thiếu.

## 3. Bảo toàn bằng chứng trước khi phân tích

Review chỉ đáng tin khi dựa trên bằng chứng có nguồn gốc và thời gian rõ ràng. Khi thu thập evidence, cần tuân theo quy trình incident response, privacy policy và yêu cầu pháp lý của tổ chức.

Nguồn evidence liên quan API có thể gồm:

- Gateway, WAF, load balancer và reverse proxy access/security logs.
- Application logs, authentication events, authorization decisions và audit records.
- Identity provider logs, token issuance/revocation events và MFA events.
- Database audit/query logs, transaction history, change records và backup metadata.
- Cloud control-plane events, IAM changes, secret manager audit và key rotation history.
- Distributed traces, metrics, alert history và deployment/configuration timeline.
- Message broker logs, queue/DLQ records, webhook delivery history và consumer offsets.
- Client, partner hoặc provider reports; support tickets và incident communications.
- Git commit, CI/CD pipeline, release artifact và infrastructure-as-code history.

### 3.1. Ghi nhận nguồn gốc và tính toàn vẹn

Với mỗi evidence item, ghi tối thiểu:

- Evidence ID và mô tả ngắn.
- Nguồn hệ thống, account/project/region và người thu thập.
- Thời điểm thu thập, timezone và khoảng thời gian dữ liệu bao phủ.
- Cách export, query hoặc snapshot; phiên bản tool nếu có ý nghĩa.
- Hash/checksum hoặc cơ chế integrity phù hợp.
- Vị trí lưu trữ, quyền truy cập và retention.
- Những giới hạn đã biết như log sampling, clock drift hoặc thiếu dữ liệu.

Không chỉnh sửa bản evidence gốc để tiện phân tích. Tạo bản làm việc riêng, ghi lại transformation và giữ liên kết về nguồn. Nếu cần redact dữ liệu cá nhân hoặc secret, bảo vệ bản gốc theo quy trình được phép và chỉ chia sẻ bản đã xử lý cho người không cần xem dữ liệu đầy đủ.

### 3.2. Đồng bộ thời gian và correlation

Các hệ thống có thể ghi timestamp theo timezone hoặc clock khác nhau. Chuẩn hóa timeline về UTC nhưng giữ timestamp gốc và offset nếu cần. Ghi nhận clock skew, log ingestion delay và thời gian sự kiện được phát hiện so với thời gian thực tế.

Correlation ID và trace ID giúp nối request qua gateway, API và downstream, nhưng không phải bằng chứng độc lập về danh tính. Đối chiếu với authenticated principal, token/session reference, broker identity và audit event. Không tin request ID do client tự gửi nếu hệ thống không validate hoặc thay bằng ID nội bộ.

### 3.3. Bảo vệ evidence nhạy cảm

Evidence có thể chứa token, API key, cookie, PII, payload thanh toán hoặc dữ liệu tenant. Không dán secret thô vào báo cáo, chat hoặc ticket thông thường. Dùng reference, fingerprint hoặc bản đã redact. Chỉ nhóm được ủy quyền mới truy cập evidence đầy đủ; ghi audit khi export hoặc chia sẻ.

## 4. Xây dựng timeline có thể kiểm chứng

Timeline nên phân biệt thời điểm hoạt động tấn công, thời điểm control ghi nhận, thời điểm con người nhận alert và thời điểm hành động được thực hiện.

| Mốc | Ý nghĩa | Ví dụ |
|---|---|---|
| `T0` | Hoạt động đầu tiên được xác nhận | Token bị sử dụng từ client bất thường |
| `T1` | Control đầu tiên ghi nhận | Gateway log xuất hiện access pattern lạ |
| `T2` | Detection/alert | SIEM tạo alert hoặc khách hàng báo cáo |
| `T3` | Triage bắt đầu | On-call xác nhận mức độ và phạm vi |
| `T4` | Containment | API key bị revoke, route bị khóa hoặc traffic bị chặn |
| `T5` | Eradication | Xóa persistence, sửa policy hoặc triển khai bản vá |
| `T6` | Recovery | Dịch vụ hoạt động lại sau validation |
| `T7` | Review/remediation | Action item được thống nhất và giao owner |

Đừng ghi một mốc như sự thật nếu chỉ là suy đoán. Dùng nhãn `confirmed`, `estimated` hoặc `unknown`; trích dẫn evidence ID hỗ trợ mỗi kết luận. Nếu log chỉ cho thấy lần đầu phát hiện chứ không chứng minh lần đầu bị khai thác, phải ghi rõ giới hạn đó.

### 4.1. Đo thời gian phản ứng

Một số chỉ số có thể dùng:

- **Time to detect (TTD):** khoảng từ hoạt động đầu tiên được xác nhận hoặc ước tính tới lúc hệ thống/người vận hành phát hiện.
- **Time to acknowledge:** từ alert tới lúc có người chịu trách nhiệm xác nhận.
- **Time to contain (TTC):** từ detection tới lúc đường khai thác hoặc tác động tức thời bị chặn.
- **Time to recover:** từ containment tới lúc dịch vụ được khôi phục và xác minh an toàn.
- **Time to revoke:** thời gian từ quyết định tới lúc token/credential thực sự mất hiệu lực trên các hệ thống liên quan.

Định nghĩa cách đo nhất quán. Nếu không biết chính xác thời điểm bắt đầu, không đưa ra con số TTD giả chính xác; ghi khoảng ước tính và độ tin cậy.

## 5. Phân tích phạm vi ảnh hưởng của API

Phạm vi không chỉ là endpoint bị khai thác. Cần truy vết các danh tính, resource, tenant và dependency mà endpoint có thể tác động.

### 5.1. Phạm vi kỹ thuật

- Host, route template, method, API version và gateway/ingress path.
- Service, pod/instance, region và deployment version.
- Authentication mechanism, issuer, audience, client ID và token type.
- Scope, role, policy version và authorization decision.
- Database, cache, object storage, search index và message topic.
- Dependency/upstream, webhook target và network egress.
- Secret, certificate, signing key hoặc API key liên quan.
- Feature flag, configuration change và infrastructure policy.

### 5.2. Phạm vi dữ liệu và tenant

Xác định dữ liệu nào có thể đã bị đọc, sửa, xóa, export hoặc gửi ra ngoài. Với hệ thống đa tenant, cần xác định tenant nguồn, tenant bị ảnh hưởng và liệu có cross-tenant access hay không.

Không kết luận “không có exfiltration” chỉ vì không tìm thấy log tải dữ liệu. Có thể log bị thiếu, response body không được ghi hoặc attacker dùng endpoint khác. Phân biệt:

- Đã xác nhận có truy cập.
- Có khả năng truy cập dựa trên quyền/đường đi.
- Có bằng chứng dữ liệu đã được đọc hoặc truyền ra ngoài.
- Không tìm thấy bằng chứng trong telemetry hiện có.

Đây là các mức kết luận khác nhau. Ghi rõ dữ liệu còn thiếu và cách nó ảnh hưởng tới confidence của assessment.

### 5.3. Tác động nghiệp vụ

Đánh giá ảnh hưởng tới:

- Tính bảo mật, toàn vẹn và sẵn sàng của dữ liệu/API.
- Giao dịch tài chính, trạng thái đơn hàng hoặc workflow phê duyệt.
- Khả năng đăng nhập, cấp quyền hoặc tích hợp của khách hàng.
- SLA, hoạt động vận hành, đối tác và downstream service.
- Nghĩa vụ thông báo, điều tra hoặc báo cáo theo hợp đồng/pháp luật.

Không đưa kết luận pháp lý hoặc cam kết thông báo chỉ dựa trên suy đoán kỹ thuật. Chuyển thông tin cho bộ phận privacy/legal/compliance theo quy trình tổ chức.

## 6. Phân tích nguyên nhân gốc và yếu tố góp phần

Root cause không nên chỉ là nhãn như “developer forgot authorization” hoặc “user clicked phishing link”. Cần giải thích chuỗi điều kiện kỹ thuật và tổ chức khiến sự cố xảy ra và kéo dài.

Một phân tích đầy đủ có thể tách:

- **Trigger:** sự kiện trực tiếp khởi phát incident, ví dụ attacker gửi request với object ID của tenant khác.
- **Vulnerability/control gap:** điều kiện cho phép hành vi, ví dụ endpoint chỉ kiểm tra scope nhưng không kiểm tra owner/tenant.
- **Contributing factors:** yếu tố làm tăng khả năng hoặc tác động, ví dụ ID tuần tự, quyền service account quá rộng, thiếu rate limit.
- **Detection gap:** lý do hoạt động không được phát hiện sớm, ví dụ audit log không ghi resource tenant hoặc alert không theo dõi deny/allow pattern.
- **Response gap:** lý do containment chậm, ví dụ không có quy trình revoke token hàng loạt hoặc owner của gateway policy không rõ.
- **Recovery gap:** lý do khôi phục chưa an toàn, ví dụ secret cũ còn hiệu lực ở một consumer.

### 6.1. Dùng chuỗi “vì sao” có bằng chứng

Ví dụ incident BOLA:

1. Vì sao user đọc được đơn hàng tenant khác? Endpoint tải order theo `orderId` mà không lọc tenant và không gọi object authorization.
2. Vì sao endpoint thiếu object authorization? Controller mới chỉ kiểm tra scope `orders:read`; service dùng repository method toàn cục.
3. Vì sao code review không phát hiện? Checklist review chỉ yêu cầu authentication và function permission, không có test cross-tenant.
4. Vì sao test không có case cross-tenant? Test fixture chỉ tạo một tenant và mọi resource đều thuộc cùng actor.
5. Vì sao control không phát hiện sau release? Audit không ghi tenant context và monitoring không cảnh báo truy cập chéo.

Kết luận không dừng ở “thiếu kiểm tra quyền”. Các yếu tố hệ thống gồm policy checklist, repository API, test fixture, audit schema và detection đều góp phần. Mỗi yếu tố có thể cần remediation riêng.

### 6.2. Tránh kết luận vượt quá bằng chứng

Không suy ra động cơ attacker nếu telemetry không chứng minh. Không khẳng định một deployment gây incident chỉ vì thời gian gần nhau; cần đối chiếu commit, config diff, request trace và reproduction. Nếu có nhiều giả thuyết, ghi từng giả thuyết, evidence ủng hộ/phản bác và bước xác minh còn thiếu.

## 7. Đánh giá control theo vòng đời bảo mật

Phân loại control theo mục tiêu giúp tìm ra khoảng trống thay vì chỉ vá endpoint đã bị khai thác.

| Nhóm control | Câu hỏi review | Ví dụ API security |
|---|---|---|
| Prevent | Điều gì lẽ ra ngăn hành vi? | Authentication, object/function authorization, tenant isolation, schema validation, SSRF egress policy |
| Detect | Điều gì lẽ ra phát hiện? | Audit event, anomaly detection, rate-limit alert, secret-use monitoring |
| Contain | Làm sao giới hạn tác động nhanh? | Revoke token/key, disable route, isolate tenant, block egress |
| Eradicate | Làm sao loại bỏ nguyên nhân? | Patch code, sửa IAM/policy, xóa persistence, rotate secret |
| Recover | Làm sao trở lại trạng thái tin cậy? | Restore service, validate data, re-enable route theo canary |
| Learn | Làm sao giảm tái diễn? | Regression test, runbook, threat model và training |

Với mỗi control, đánh giá:

- Có tồn tại trong thiết kế và production không?
- Có bao phủ tất cả endpoint/version/tenant/service liên quan không?
- Có được cấu hình đúng và bật ở môi trường bị ảnh hưởng không?
- Có hoạt động như mong đợi dưới concurrency, failure và bypass path không?
- Có telemetry để chứng minh nó đã chạy không?
- Có owner, test và quy trình duy trì không?

Một control được khai báo trong tài liệu nhưng không được triển khai hoặc không được giám sát không thể coi là control hiệu quả.

## 8. Chuyển bài học thành control update cụ thể

Action item cần mô tả thay đổi có thể review và kiểm chứng. “Tăng cường bảo mật API” hoặc “cải thiện monitoring” quá mơ hồ để theo dõi.

Một action item nên có:

- Finding hoặc control gap liên quan.
- Thay đổi cụ thể và phạm vi áp dụng.
- Owner chịu trách nhiệm và reviewer/approver nếu cần.
- Priority/severity và lý do.
- Due date hoặc milestone.
- Dependency và rủi ro triển khai.
- Test/metric/evidence dùng để xác nhận.
- Cách rollback hoặc xử lý nếu remediation gây regression.
- Trạng thái và liên kết tới PR/change/ticket.

### 8.1. Ví dụ mapping từ finding sang control

| Finding | Control update | Cách xác minh |
|---|---|---|
| BOLA trên `GET /orders/{id}` | Scoped repository query và object authorization ở service | Integration test tenant A không đọc được order tenant B |
| Token bị lộ trong log | Redaction tại appender/APM/gateway và secret scanning | Secret fixture không xuất hiện trong mọi log sink |
| API key cũ còn hiệu lực sau rotation | Credential inventory, overlap window và revoke verification | Test key cũ bị từ chối ở mọi instance/consumer |
| SSRF qua URL callback | Destination allowlist, DNS/IP validation và egress restriction | Test loopback/private/link-local/redirect bị chặn |
| Webhook replay | Timestamp/nonce/event dedup và idempotent consumer | Replay cùng event không tạo side effect thứ hai |
| Abuse export endpoint | Tenant/client quota, concurrency cap và alert | Load/security test xác nhận limit và alert |
| Validation bypass | Schema/property test và fail-closed parsing | Fuzz regression corpus không vượt validator |
| Thiếu detection khi permission bị deny hàng loạt | Structured audit, metric và threshold alert | Synthetic event kích hoạt alert trong thời gian mục tiêu |
| Break-glass grant không tự hết hạn | TTL bắt buộc, revoke propagation và audit | Test expiry/revoke ở mọi API instance |

### 8.2. Ưu tiên remediation theo rủi ro

Có thể phân loại:

- **Immediate containment:** cần làm ngay để chặn khai thác hoặc thu hồi credential.
- **Short-term corrective:** sửa code/config/control gap có rủi ro cao trong thời gian ngắn.
- **Systemic improvement:** cải thiện platform, shared library, policy-as-code, testing hoặc monitoring.
- **Long-term resilience:** thay đổi kiến trúc, giảm blast radius, tăng khả năng phục hồi.

Ưu tiên dựa trên khả năng khai thác, dữ liệu/tài sản bị ảnh hưởng, mức độ truy cập, exposure, khả năng tái diễn và thời gian tồn tại của control gap. Không ưu tiên chỉ theo mức độ dễ làm hoặc người yêu cầu có quyền cao.

## 9. Cập nhật control theo từng lớp API

Sau incident, rà soát các lớp liên quan thay vì chỉ sửa dòng code nơi lỗi được phát hiện.

### 9.1. Authentication và credential lifecycle

- Rà soát issuer, audience, token type, expiry, signing algorithm và key rotation.
- Thu hồi session, refresh token, API key hoặc certificate có nguy cơ bị lộ.
- Kiểm tra token revocation/denylist propagation và cache.
- Giới hạn credential theo client, environment, tenant và scope.
- Thêm test cho replay, token confusion, expired token và key rotation.

### 9.2. Function, object và property authorization

- Kiểm tra quyền theo endpoint + method + action.
- Thêm object-level authorization và tenant-scoped repository access.
- Giới hạn field được đọc/ghi; tránh mass assignment và overexposure.
- Xác minh state transition trước side effect.
- Test cross-user, cross-tenant, role boundary và negative permission.

### 9.3. Input validation, output filtering và SSRF

- Chuẩn hóa parser, schema version và giới hạn body/depth/array.
- Từ chối input nhập nhằng hoặc sai encoding.
- Áp dụng output DTO allowlist và error response không lộ nội bộ.
- Kiểm tra URL scheme, hostname, resolved IP, redirect và egress policy.
- Bổ sung fuzzing/property-based regression test cho payload và parser differential.

### 9.4. Abuse, quota và dependency resilience

- Điều chỉnh rate limit theo principal, tenant, route và chi phí operation.
- Thêm concurrency/bulkhead limit, timeout budget và retry policy có giới hạn.
- Đánh giá circuit breaker và fallback không được fail-open authorization.
- Theo dõi outbound quota và dependency failure.
- Xác minh limit nhất quán giữa gateway, service và nhiều instance.

### 9.5. Webhook, async message và gateway

- Ràng buộc producer identity, signature, audience và tenant context.
- Chống replay bằng timestamp/nonce/deduplication và idempotency.
- Kiểm tra gateway/backend route, method, version và policy nhất quán.
- Không tin identity header do client gửi; xác thực service-to-service.
- Giữ tenant context qua retry, DLQ, redrive và event chain.

### 9.6. Logging, alert và incident readiness

- Ghi decision có cấu trúc với route, principal reference, tenant reference và policy version.
- Không log token, API key, secret hoặc payload nhạy cảm.
- Bổ sung alert cho hành vi bất thường và control failure.
- Xác định owner, severity, escalation path và on-call contact.
- Diễn tập revoke credential, disable endpoint, isolate tenant và restore service.

## 10. Quản lý action item và tránh remediation hình thức

Action item cần được theo dõi như công việc kỹ thuật có tiêu chí nghiệm thu, không chỉ là một dòng trong báo cáo.

### 10.1. Mẫu action item

```yaml
id: SEC-API-142
finding: BOLA on order detail endpoint
control: object_level_authorization
change: scope order lookup by authenticated tenant and enforce owner policy
owner: orders-platform-team
reviewer: api-security
priority: P1
due_date: 2026-12-05
verification:
  - integration test denies cross-tenant read and update
  - audit records policy decision without exposing foreign resource data
  - gateway and direct-service paths use the same authorization rule
rollback: revert behind a feature flag while keeping endpoint deny-by-default
status: OPEN
```

Đây là ví dụ cấu trúc. Không đưa secret hoặc dữ liệu khách hàng vào ticket/action item. Owner và due date phải là giá trị được nhóm chịu trách nhiệm xác nhận.

### 10.2. Definition of done

Không đánh dấu remediation hoàn thành chỉ vì PR đã merge hoặc cấu hình đã deploy. Tùy loại control, cần:

- Code/config được review và triển khai đúng môi trường.
- Test âm/dương chứng minh policy hoạt động.
- Test qua gateway và direct backend path nếu có.
- Metric/log/alert đã được cập nhật và kiểm tra.
- Rollback/operational runbook được cập nhật.
- Owner vận hành xác nhận control có thể duy trì.
- Không còn secret/credential cũ hoặc permission tạm thời chưa thu hồi.
- Risk acceptance được ghi rõ nếu một phần remediation chưa thực hiện.

Nếu chỉ hoàn thành một phần, giữ action ở trạng thái `PARTIAL` hoặc `BLOCKED` và ghi rủi ro còn lại. Không đóng finding bằng cách đổi tên hoặc chuyển sang backlog mà không có quyết định risk acceptance có thẩm quyền.

## 11. Xác minh remediation và kiểm tra regression

Mỗi control update cần có bằng chứng rằng nó thực sự giải quyết finding và không phá chức năng hợp lệ.

Các hình thức xác minh:

- Unit/integration test cho authorization, validation và business rule.
- Negative security test với token thiếu quyền, tenant khác và resource không hợp lệ.
- Fuzzing/property-based test và regression corpus.
- Contract test cho gateway, webhook và message schema.
- Configuration/IaC policy test và drift detection.
- Synthetic monitoring hoặc controlled exercise để xác nhận alert.
- Review log/audit để chứng minh decision được ghi nhận.
- Canary rollout, observation window và rollback criteria.
- Independent security review hoặc penetration test khi rủi ro yêu cầu.

### 11.1. Kiểm tra cả bypass path

Nếu sửa authorization ở gateway, kiểm tra backend có thể bị gọi trực tiếp hay qua ingress khác không. Nếu sửa một controller, kiểm tra các API version, nested endpoint, export, GraphQL resolver và worker có dùng cùng service/policy không.

Nếu rotate secret, kiểm tra tất cả consumer, background worker, deployment và region. Nếu thêm rate limit, kiểm tra nhiều instance, IPv6/proxy path và key spoofing. Nếu cập nhật webhook verification, kiểm tra retry và DLQ redrive.

### 11.2. Quan sát sau khi deploy

Theo dõi error rate, latency, deny rate, quota rejection, dependency failure, support tickets và hành vi khách hàng trong một khoảng thời gian phù hợp. Một control có thể đúng về bảo mật nhưng làm block nhầm traffic hợp lệ; cần có rollback/adjustment được kiểm soát và không vô hiệu hóa bảo vệ chỉ để giảm alert.

## 12. Cập nhật threat model và tài liệu vận hành

Incident có thể cho thấy threat model trước đó bỏ sót actor, trust boundary hoặc đường dữ liệu. Cập nhật:

- Data flow và trust boundary giữa client, gateway, service, database và dependency.
- Threat scenario, abuse case và attacker capability.
- Asset inventory, secret inventory và service ownership.
- Endpoint inventory, permission matrix và tenant boundary.
- Security requirement, API contract và schema.
- Runbook detection, containment, revoke, recovery và escalation.
- Dashboard, alert threshold và SLO/security indicator.
- Checklist code review, release và architecture review.

Không chỉ thêm một đoạn vào runbook. Hãy liên kết thay đổi với owner, phiên bản và quy trình review để tài liệu không nhanh chóng lỗi thời.

## 13. Đánh giá hiệu quả sau remediation

Sau một thời gian, đánh giá liệu control mới có giảm rủi ro thực tế:

- Số lần tái diễn cùng pattern hoặc cùng root cause.
- Tỷ lệ endpoint có authorization test và tenant isolation test.
- Thời gian revoke token/key và propagation tới consumer.
- Tỷ lệ alert đúng, false positive và thời gian acknowledge.
- Thời gian containment/recovery trong diễn tập hoặc incident tiếp theo.
- Số action item quá hạn và số risk acceptance còn hiệu lực.
- Số lần bypass control hoặc emergency exception được sử dụng.

Không dùng số lượng log hoặc số lượng test đơn thuần làm thước đo thành công. Metric cần phản ánh hiệu quả của control và được diễn giải cùng traffic, coverage và mức độ phơi nhiễm.

### 13.1. Kiểm tra control drift

Control có thể suy giảm theo thời gian do endpoint mới, API version mới, service mới, policy copy-paste hoặc cấu hình thủ công. Thiết lập kiểm tra định kỳ:

- Route inventory so với gateway và backend endpoint thực tế.
- Endpoint có authentication/function/object authorization.
- Secret inventory so với credential đang được workload sử dụng.
- Expiry/rotation policy và credential còn hiệu lực.
- Log/alert coverage của route nhạy cảm.
- Rate-limit, timeout và egress policy theo environment.
- Break-glass grant và quyền tạm thời còn active.

Control update chỉ bền vững khi có owner và cơ chế phát hiện drift.

## 14. Cấu trúc một post-incident review report

Một báo cáo có thể theo cấu trúc:

1. **Executive summary:** điều gì xảy ra, mức độ, ảnh hưởng và trạng thái hiện tại.
2. **Scope:** service, endpoint, tenant, dữ liệu và khách hàng liên quan.
3. **Timeline:** mốc confirmed/estimated, evidence reference và độ tin cậy.
4. **Attack/Failure narrative:** chuỗi request, identity, policy và dependency.
5. **Impact assessment:** confidentiality, integrity, availability và business impact.
6. **Root cause:** trigger, vulnerability/control gap và contributing factors.
7. **Detection/response analysis:** điều gì hoạt động, điều gì chậm hoặc thiếu.
8. **Control assessment:** prevent, detect, contain, eradicate, recover.
9. **Remediation plan:** action, owner, priority, due date và verification.
10. **Residual risk:** phần chưa xử lý, risk owner và thời hạn chấp nhận.
11. **Appendix:** evidence index, query/method, glossary và liên kết change.

### 14.1. Mẫu review rút gọn

```markdown
# Post-incident review: <incident-id>

## Summary
- Severity:
- Status:
- Incident commander:
- Review owner:

## Scope and impact
- Services/endpoints:
- Principals/tenants:
- Data and business flows:
- Confirmed impact:
- Unknowns and confidence:

## Timeline
| UTC time | Event | Evidence ID | Confidence |
|---|---|---|---|

## Root cause and contributing factors
- Trigger:
- Vulnerability/control gap:
- Contributing factors:
- Detection gap:
- Response/recovery gap:

## Control assessment
| Control | Expected behavior | Observed behavior | Gap |
|---|---|---|---|

## Actions
| ID | Change | Owner | Priority | Due date | Verification | Status |
|---|---|---|---|---|---|---|

## Residual risk and follow-up
- Risk owner:
- Acceptance/expiry:
- Next review date:
```

## 15. Ma trận ví dụ: từ incident API tới control update

| Incident pattern | Câu hỏi review | Control update tiêu biểu |
|---|---|---|
| BOLA/cross-tenant read | Endpoint nào thiếu object check? Query có tenant predicate không? | Shared authorization service, scoped repository, cross-tenant tests |
| Token theft/replay | Token phát sinh ở đâu, audience/scope/TTL ra sao? | Phishing-resistant MFA, short-lived token, revoke propagation, replay detection |
| API key exposure | Secret xuất hiện ở log, code, CI hay client? | Secret scanning, vault, rotation automation, log redaction |
| SSRF | URL nào được caller kiểm soát? Redirect/DNS/egress ra sao? | Destination allowlist, DNS/IP validation, egress firewall, safe HTTP client |
| Rate abuse | Quota theo principal/tenant có đúng không? | Distributed limiter, concurrency budget, abuse alert |
| Webhook replay | Signature bao phủ thành phần nào? Dedup key có tenant scope không? | Signed envelope, timestamp/nonce, idempotent consumer |
| Gateway policy drift | Gateway và backend có match cùng route/method/version không? | Route inventory, policy-as-code, drift tests |
| Error enumeration | 403/404, body/header/timing có phân biệt resource không? | Concealment policy, scoped lookup, response regression tests |
| Dependency outage | Timeout/retry/fallback có khuếch đại tải hoặc fail-open không? | Timeout budget, circuit breaker, bounded retry, safe fallback |
| Break-glass misuse | Ai yêu cầu/phê duyệt, scope và TTL ra sao? | Dual control, JIT grant, immutable audit, automatic revoke |

## 16. Checklist post-incident review và control update

- [ ] Có review owner và phạm vi rõ ràng.
- [ ] Evidence được bảo toàn, có nguồn gốc, timestamp và integrity phù hợp.
- [ ] Timeline phân biệt confirmed, estimated và unknown.
- [ ] Correlation được đối chiếu với identity/audit, không chỉ dựa vào trace ID.
- [ ] Scope bao gồm endpoint, method, version, principal, tenant, resource và dependency.
- [ ] Impact assessment phân biệt confirmed access, possible access và confirmed exfiltration.
- [ ] Root cause giải thích chuỗi điều kiện; không dừng ở lỗi cá nhân hoặc trigger.
- [ ] Control được đánh giá theo prevent, detect, contain, eradicate, recover và learn.
- [ ] Finding được chuyển thành action cụ thể có owner, priority và due date.
- [ ] Mỗi action có verification criteria và evidence cần thu thập.
- [ ] Regression test bao phủ endpoint, tenant, version và bypass path liên quan.
- [ ] Secret/token/permission tạm thời đã được revoke hoặc rotate khi cần.
- [ ] Runbook, threat model, API contract và monitoring được cập nhật.
- [ ] Residual risk có risk owner, approval và expiry/review date.
- [ ] Post-deploy observation xác nhận control hoạt động và không gây regression.
- [ ] Có cơ chế kiểm tra control drift và theo dõi action quá hạn.

## 17. Nguyên tắc thiết kế

Post-incident review biến một sự cố cụ thể thành cải thiện lâu dài cho API security. Bắt đầu từ evidence có nguồn gốc, dựng timeline có độ tin cậy, xác định phạm vi principal/tenant/resource/dependency và phân tích trigger, control gap cùng các yếu tố góp phần. Đánh giá riêng prevention, detection, containment, eradication và recovery để không bỏ sót những lớp đã thất bại hoặc cần cải thiện.

Chuyển mỗi finding thành control update cụ thể, có owner, priority, deadline và cách xác minh. Kiểm tra cả đường gateway lẫn backend, mọi API version, worker và dependency liên quan; cập nhật test, alert, runbook và threat model. Không đóng remediation chỉ vì code đã merge: cần bằng chứng control đã triển khai, có hiệu lực và được duy trì. **Một post-incident review hoàn tất khi bài học đã trở thành thay đổi có thể kiểm chứng và rủi ro còn lại có người chịu trách nhiệm.**
