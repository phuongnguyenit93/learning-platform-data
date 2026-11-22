# Thiết kế tiêu chí hoàn tất gồm khả năng triển khai và quan sát

Một tính năng có thể chạy đúng trên máy của lập trình viên và vượt qua unit test, nhưng vẫn chưa sẵn sàng để phát hành. Khi đưa lên môi trường thật, nó có thể thiếu cấu hình, quyền truy cập, health check, log đủ ngữ cảnh, metric để nhận biết lỗi hoặc quy trình quay lui khi có sự cố.

Vì vậy, tiêu chí hoàn tất (Definition of Done – DoD) cần bao gồm cả khả năng triển khai và khả năng quan sát. Nhóm phải xác định trước thay đổi sẽ được đóng gói, cấu hình, phát hành, xác minh và vận hành như thế nào; đồng thời phải có tín hiệu để biết hệ thống đang hoạt động đúng hoặc đang suy giảm.

DoD không phải một danh sách thủ tục để ký cho xong. Nó là thỏa thuận chất lượng chung giữa phát triển, kiểm thử, vận hành, bảo mật và người sở hữu sản phẩm. Mỗi tiêu chí cần có cách kiểm tra, người chịu trách nhiệm và bằng chứng có thể xem lại.

## 1. Hoàn tất tính năng chưa đồng nghĩa sẵn sàng triển khai

Một thay đổi thường đi qua nhiều mức hoàn tất:

- **Code complete:** phần mã theo phạm vi đã được viết.
- **Test complete:** các kiểm tra được yêu cầu đã chạy và đạt.
- **Deployable:** artifact, cấu hình, quyền và điều kiện triển khai đã sẵn sàng.
- **Operationally ready:** có thể theo dõi, chẩn đoán, xử lý và phục hồi khi chạy.
- **Release complete:** đã triển khai tới target, xác minh sau triển khai và lưu bằng chứng.

Các mức này có liên hệ nhưng không thay thế nhau. Build xanh không chứng minh ứng dụng có quyền truy cập database production. Deployment controller báo rollout hoàn tất cũng không chứng minh luồng nghiệp vụ quan trọng đang hoạt động.

Một nhóm cần mô tả rõ trạng thái nào được gọi là Done trong từng loại công việc. Với thay đổi chỉ sửa tài liệu, yêu cầu triển khai có thể không áp dụng. Với thay đổi service production, deployability và observability thường là điều kiện bắt buộc trước khi đóng công việc.

## 2. Phân biệt Acceptance Criteria, Definition of Done và Release Readiness

Ba khái niệm này thường bị trộn lẫn.

| Khái niệm | Trả lời câu hỏi | Phạm vi |
|---|---|---|
| Acceptance Criteria | Tính năng phải hành xử như thế nào để được chấp nhận? | Một story hoặc yêu cầu |
| Definition of Done | Mọi thay đổi phải đáp ứng chuẩn chất lượng nào? | Nhóm hoặc sản phẩm |
| Release Readiness | Phiên bản cụ thể đã đủ điều kiện phát hành chưa? | Một release/deployment |

Ví dụ với tính năng tạo đơn hàng:

- Acceptance Criteria: người dùng hợp lệ có thể tạo đơn; đơn có mã duy nhất; tổng tiền được tính theo quy tắc đã thống nhất; request không hợp lệ nhận lỗi phù hợp.
- DoD: có unit/integration test; API được mô tả; log và metric cần thiết được bổ sung; cấu hình và secret được quản lý; migration tương thích; có dashboard và runbook.
- Release Readiness: artifact đã được kiểm tra; target đúng; migration hoàn tất; smoke test đạt; error rate và latency nằm trong ngưỡng; rollback hoặc forward-fix đã được xác định.

Acceptance Criteria mô tả kết quả của tính năng. DoD mô tả chuẩn chất lượng áp dụng xuyên suốt. Release Readiness đánh giá phiên bản và môi trường cụ thể tại thời điểm phát hành.

## 3. Đưa deployability vào DoD từ lúc lập kế hoạch

Khả năng triển khai không nên chỉ được hỏi ở cuối sprint. Khi refinement, nhóm cần nhận diện thay đổi có tác động gì tới runtime, database, cấu hình, quyền, hạ tầng và cách rollout.

Các câu hỏi nên được đặt sớm:

- Có thêm dependency hoặc system package nào không?
- Có thay đổi biến môi trường, config key hoặc secret reference không?
- Có cần thay đổi IAM/RBAC hoặc network rule không?
- Có migration schema hoặc backfill dữ liệu không?
- Phiên bản cũ và mới có thể cùng chạy trong rolling deployment không?
- Có cần feature flag, canary hoặc giới hạn traffic ban đầu không?
- Có ảnh hưởng startup, readiness, graceful shutdown hoặc capacity không?
- Nếu deploy lỗi, có thể rollback ứng dụng không? Schema và dữ liệu có tương thích không?
- Có bước thủ công hoặc approval nào cần chuẩn bị trước?

Nếu câu trả lời chỉ xuất hiện trong ngày phát hành, nhóm có thể phát hiện quá muộn rằng artifact thiếu cấu hình, migration không tương thích hoặc quyền của workload chưa được cấp.

## 4. Các lớp của khả năng triển khai

Một thay đổi deployable cần đủ thông tin và thành phần để được đưa lên môi trường theo quy trình đã định.

| Lớp | Điều kiện cần xem xét | Bằng chứng gợi ý |
|---|---|---|
| Artifact | Build thành công, định danh bất biến, đúng target | Build result, digest, provenance |
| Configuration | Config key có schema, giá trị mặc định và validation | Config reference, validation test |
| Secrets | Secret được tham chiếu từ secret manager, có owner và rotation | Secret reference, permission check |
| Identity/access | Workload có đúng quyền tối thiểu | IAM/RBAC review, authorization test |
| Dependencies | Database, queue, API hoặc service phụ thuộc sẵn sàng | Contract/integration test |
| Data/schema | Migration tương thích với các version cùng tồn tại | Migration result, compatibility test |
| Runtime | Resource request/limit, port, probe và shutdown hợp lệ | Deployment manifest validation |
| Rollout | Có strategy, timeout, pause và điều kiện promote | Deployment policy |
| Recovery | Có rollback hoặc forward-fix plan phù hợp | Recovery procedure |
| Verification | Có smoke check và tiêu chí sau deploy | Test report, evidence record |

Không phải mọi thay đổi đều cần tất cả mục. DoD có thể dùng quy tắc "áp dụng nếu có" nhưng phải nêu rõ ai xác định phạm vi và cách ghi nhận mục không áp dụng.

## 5. Artifact phải sẵn sàng cho phát hành

Artifact là đầu vào của deployment. DoD nên yêu cầu artifact được tạo bằng pipeline đã kiểm soát và có thể truy vết tới source revision.

Các điều kiện thường cần:

- Build và test bắt buộc đã đạt.
- Artifact có version hoặc digest bất biến.
- Metadata liên kết artifact với commit, build run và pipeline definition.
- Dependency được khóa theo cơ chế của dự án.
- Package hoặc container image đúng target OS/architecture.
- Artifact được lưu trong registry/repository có quyền truy cập phù hợp.
- Không đóng gói secret hoặc file cấu hình môi trường nhạy cảm.
- Có SBOM/provenance nếu policy của sản phẩm yêu cầu.

Không nên dùng một tag có thể bị ghi đè làm định danh duy nhất cho bản phát hành. Deployment nên tham chiếu tới digest hoặc artifact ID không thay đổi. Nhờ vậy, nhóm có thể xác định chính xác nội dung đã được test và nội dung đang chạy.

Nếu build một lần rồi promote qua staging và production, cần giữ cùng artifact digest. Việc build lại riêng cho production có thể tạo ra nội dung khác với artifact đã xác minh ở staging.

## 6. Cấu hình phải có hợp đồng và validation

Cấu hình môi trường thường là nguồn lỗi sau deploy. Một key mới có thể chưa được khai báo ở production; một giá trị có thể sai kiểu; hoặc một giá trị mặc định phù hợp local nhưng không phù hợp môi trường thật.

Với mỗi config key quan trọng, cần xác định:

- Tên và kiểu dữ liệu.
- Có bắt buộc hay không.
- Giá trị mặc định và phạm vi hợp lệ.
- Môi trường hoặc service sử dụng.
- Nguồn quản lý giá trị.
- Hành vi khi thiếu hoặc không hợp lệ.
- Cách thay đổi mà không cần rebuild artifact.

Ứng dụng nên validate cấu hình lúc khởi động hoặc trước khi nhận traffic. Nếu config bắt buộc bị thiếu, service cần fail rõ ràng và cung cấp thông báo không chứa secret.

Ví dụ hợp đồng cấu hình:

```yaml
server:
  port: 8080

orders:
  max-items-per-request: 50
  request-timeout: 3s

database:
  url: required
  username: required
  password-ref: secret-manager://prod/orders/db-password
```

Đây là cấu trúc minh họa; cú pháp thực tế phụ thuộc framework. Giá trị nhạy cảm cần được lấy từ secret manager hoặc workload identity. Không commit password thật vào file cấu hình hoặc ghi nó vào log khi validation thất bại.

## 7. Identity và quyền truy cập phải được chuẩn bị

Một service có thể khởi động nhưng không thể thực hiện công việc vì workload thiếu quyền tới database, queue, object storage hoặc API nội bộ.

DoD nên kiểm tra:

- Workload chạy bằng identity dự kiến.
- Quyền được cấp theo least privilege.
- Mỗi môi trường dùng scope quyền riêng.
- Không dùng credential cá nhân của developer trong runtime.
- Token có thời hạn và audience phù hợp nếu dùng workload identity.
- Quyền đọc secret chỉ cấp cho thành phần cần thiết.
- Quy trình thu hồi hoặc rotation đã được xác định.
- Các thao tác nhạy cảm có audit trail.

Không kiểm tra quyền chỉ bằng cách xác nhận credential tồn tại. Cần xác minh service có thể thực hiện đúng thao tác cần thiết và bị từ chối đối với thao tác ngoài phạm vi. Ví dụ, service xử lý đơn có thể ghi vào bảng orders nhưng không được phép đọc secret của service thanh toán.

## 8. Migration và tương thích giữa các phiên bản

Thay đổi database thường làm tăng rủi ro khi rolling hoặc blue-green deployment vì app cũ và mới có thể cùng truy cập schema trong một khoảng thời gian.

DoD cho thay đổi dữ liệu cần xác định:

- Migration có version và được review.
- Expand được triển khai trước khi code mới phụ thuộc cấu trúc mới.
- App cũ và app mới tương thích trong giai đoạn rollout.
- Backfill có batch, checkpoint và cách chạy lại an toàn nếu cần.
- Có reconciliation hoặc invariant để xác minh dữ liệu.
- Contract migration chỉ chạy khi không còn consumer cũ và rollback window đã đóng.
- Quy trình phục hồi dữ liệu được xem xét theo mức độ rủi ro.

Không tự động downgrade schema khi deploy ứng dụng thất bại. Rollback ứng dụng và rollback dữ liệu là hai quyết định riêng. Nếu schema đã thay đổi theo cách không thể đảo ngược an toàn, nhóm cần forward-fix hoặc migration bù.

## 9. Health check phải phản ánh trạng thái có ý nghĩa

Health endpoint là một phần của khả năng triển khai, nhưng mỗi loại probe có mục đích riêng.

- **Liveness:** process còn hoạt động và không bị kẹt theo tiêu chí của ứng dụng.
- **Readiness:** instance đã sẵn sàng nhận traffic.
- **Startup probe:** cho ứng dụng đủ thời gian khởi động trước khi áp dụng các probe khác.
- **Synthetic/business check:** xác minh một luồng nghiệp vụ qua giao diện hoặc API.

Không nên để liveness phụ thuộc vào mọi dependency bên ngoài. Nếu database tạm thời chậm, liveness thất bại trên tất cả instance có thể khiến orchestrator restart liên tục và làm sự cố nặng hơn. Readiness có thể phản ánh dependency mà service cần để nhận traffic; liveness nên phát hiện tình trạng process không thể tự phục hồi.

DoD cần nêu rõ probe endpoint, timeout, initial delay, failure threshold và hành vi khi probe thất bại. Giá trị phải dựa trên thời gian startup và đặc tính hệ thống, không sao chép máy móc giữa các service.

## 10. Graceful shutdown và xử lý request đang chạy

Khi rollout hoặc scale-in, orchestrator có thể gửi tín hiệu dừng tới instance. Nếu ứng dụng thoát ngay lập tức, request đang xử lý có thể bị ngắt hoặc message đang tiêu thụ bị mất.

DoD nên kiểm tra:

- Ứng dụng ngừng nhận request mới khi bắt đầu shutdown.
- Readiness chuyển sang trạng thái không nhận traffic.
- Request đang chạy được phép hoàn tất trong thời hạn hợp lý.
- Consumer dừng nhận message mới và xử lý/ack theo quy tắc.
- Connection pool, thread và resource được đóng đúng thứ tự.
- Process thoát trước termination grace period.
- Có timeout cho shutdown và hành vi khi quá hạn.

Với worker xử lý message, cần xác định hành vi khi bị terminate giữa một công việc. Nếu có thể xử lý lại, handler cần idempotent hoặc dùng cơ chế deduplication. Nếu không, rollout có thể tạo tác dụng phụ trùng lặp.

## 11. Observability là một phần của sản phẩm

Observability (khả năng quan sát) giúp nhóm suy luận trạng thái bên trong hệ thống từ các tín hiệu mà hệ thống phát ra. Ba nhóm dữ liệu thường gặp là logs, metrics và traces.

- **Logs:** sự kiện chi tiết theo thời gian, có ngữ cảnh để điều tra.
- **Metrics:** chuỗi số liệu tổng hợp để nhận biết xu hướng và mức độ ảnh hưởng.
- **Traces:** đường đi của một request qua nhiều service/dependency.

Dashboard, alert và runbook là lớp sử dụng các tín hiệu đó để hỗ trợ quyết định. Chỉ thêm log không đồng nghĩa đã có observability. Nhóm cần biết log/metric/trace nào trả lời câu hỏi vận hành cụ thể.

Một thay đổi hoàn tất khi các tín hiệu cần thiết được tạo, thu thập, truy vấn và có người sở hữu chúng.

## 12. Thiết kế log có cấu trúc và an toàn

Log nên có cấu trúc nhất quán để có thể lọc theo service, version, environment và request.

Các field thường hữu ích:

- timestamp theo UTC.
- severity/level.
- service name và service version.
- environment.
- event name.
- request ID hoặc correlation ID.
- trace ID/span ID nếu có.
- operation hoặc route.
- kết quả và error category.
- duration nếu là thao tác có thời gian.

Ví dụ:

```json
{
  "timestamp": "2026-11-18T08:30:12Z",
  "level": "ERROR",
  "service": "orders-api",
  "version": "3.8.1",
  "environment": "production",
  "event": "order.persistence.failed",
  "request_id": "req-7f31",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "error_type": "database_timeout",
  "duration_ms": 1200
}
```

Ví dụ không chứa payload đơn hàng hoặc credential. Không log access token, password, private key, session cookie hay dữ liệu cá nhân nếu không có nhu cầu và cơ chế bảo vệ phù hợp. Nếu cần log identifier người dùng, hãy chọn dạng đã được giảm định danh hoặc masking theo policy.

DoD cũng cần yêu cầu kiểm tra log khi lỗi xảy ra: thông điệp có đủ ngữ cảnh để điều tra không, có stack trace phù hợp không, có vô tình làm lộ dữ liệu không và log level có gây nhiễu không.

## 13. Metrics cần trả lời câu hỏi vận hành

Metrics nên được chọn theo hành vi và rủi ro của service, không chỉ theo những gì thư viện instrumentation cung cấp mặc định.

Một bộ cơ bản cho API thường gồm:

- Request rate: số request theo thời gian.
- Error rate: tỷ lệ request lỗi theo loại hoặc status class.
- Latency: p50, p95, p99.
- Saturation: CPU, memory, connection pool, queue hoặc worker capacity.
- Dependency health: timeout, retry, connection failure.
- Business metric: số đơn được tạo, số thanh toán thành công hoặc tỷ lệ tác vụ hoàn tất.

Tránh label có cardinality quá cao như raw user ID, request ID hoặc email. Những giá trị đó phù hợp với log/trace có kiểm soát hơn là metric label. Cardinality lớn làm tăng chi phí và có thể gây quá tải metrics backend.

DoD nên xác định metric quan trọng, đơn vị, label, cách tính và nơi hiển thị. Metric cần có tên và semantics nhất quán giữa các version để dashboard không bị gãy khi deploy.

## 14. Traces và liên kết giữa các service

Khi một request đi qua API gateway, orders service, inventory service và database, log riêng của từng service có thể không đủ để tái dựng thứ tự và thời gian.

Distributed tracing giúp liên kết các span theo trace context. DoD cho thay đổi có nhiều dependency nên xác định:

- Trace context được truyền qua HTTP/message khi phù hợp.
- Span thể hiện operation quan trọng.
- Error và timeout được đánh dấu.
- Dependency call có duration và outcome.
- Sampling policy đủ quan sát nhưng không tạo chi phí không cần thiết.
- Trace không ghi payload nhạy cảm ngoài policy.
- Service name/version được gắn vào resource attributes.

Không nhất thiết tạo span cho mọi hàm nội bộ. Tập trung vào ranh giới request, dependency và công việc bất đồng bộ có giá trị chẩn đoán.

## 15. Từ metrics tới SLI và SLO

SLI (Service Level Indicator) là phép đo chất lượng dịch vụ. SLO (Service Level Objective) là mục tiêu cho SLI trong một khoảng thời gian.

Ví dụ minh họa cho API tạo đơn:

- Availability SLI: tỷ lệ request hợp lệ được xử lý thành công.
- Latency SLI: tỷ lệ request hoàn tất dưới ngưỡng đã định.
- SLO: 99,9% request hợp lệ thành công trong cửa sổ 30 ngày.
- Latency objective: 95% request hoàn tất trong 300 ms, theo điều kiện traffic đã thống nhất.

Các con số này chỉ là ví dụ; nhóm cần chọn ngưỡng từ yêu cầu sản phẩm và dữ liệu thực tế. Không áp dụng một SLO giống nhau cho mọi endpoint.

DoD của thay đổi ảnh hưởng tới reliability nên xác định SLI/SLO nào có liên quan, metric đã có chưa và release có làm thay đổi error budget hay không. Nếu chưa có SLO cho service, tối thiểu cần có tín hiệu về lỗi, latency và saturation để phát hiện suy giảm.

## 16. Alert phải có hành động và người nhận

Alert không chỉ là ngưỡng metric vượt mức. Một alert hữu ích cần trả lời:

- Điều gì đang sai?
- Người dùng hoặc service nào bị ảnh hưởng?
- Mức độ nghiêm trọng ra sao?
- Ai chịu trách nhiệm phản hồi?
- Cần mở dashboard hoặc runbook nào?
- Điều kiện nào để đóng alert?

Alert nên tập trung vào triệu chứng ảnh hưởng người dùng hoặc nguy cơ sắp ảnh hưởng. Ví dụ, tỷ lệ request lỗi tăng trong một cửa sổ đủ dài có thể cần page on-call; một lần CPU tăng ngắn có thể chỉ cần ghi nhận hoặc cảnh báo mức thấp.

Tránh tạo alert cho mọi log ERROR. Điều đó tạo nhiễu và khiến người trực bỏ qua tín hiệu quan trọng. Alert cần có owner, routing, severity, threshold, evaluation window và runbook link.

DoD cho thay đổi làm tăng một loại lỗi mới nên xem xét alert tương ứng. Nếu lỗi có thể gây mất dữ liệu hoặc gián đoạn nghiêm trọng, cần xác định tín hiệu phát hiện và hành động phản ứng trước khi phát hành.

## 17. Dashboard cần phục vụ một câu hỏi cụ thể

Dashboard không phải nơi tập hợp mọi metric. Mỗi dashboard nên giúp một nhóm người trả lời một câu hỏi.

Ví dụ:

- Service overview: service có khỏe không?
- Release dashboard: version nào đang chạy và rollout tiến tới đâu?
- Dependency dashboard: database hoặc queue có gây nghẽn không?
- Business dashboard: luồng tạo đơn có thành công không?
- SLO dashboard: service đang tiêu thụ error budget với tốc độ nào?

Dashboard cần có:

- Service/environment/version filter.
- Metric quan trọng và ngưỡng tham chiếu.
- Link tới log query và trace nếu có.
- Annotation cho deployment hoặc migration.
- Hướng dẫn đọc và owner.
- Time range mặc định phù hợp với mục tiêu.

Khi deploy version mới, dashboard cần cho phép so sánh trước/sau và lọc theo version hoặc revision. Nếu metric không có label version, việc tách ảnh hưởng của bản phát hành mới sẽ khó hơn.

## 18. Runbook là một phần của tiêu chí hoàn tất

Runbook mô tả cách người vận hành chẩn đoán và xử lý một tình huống. Nó nên tập trung vào hành động cụ thể, không chỉ giải thích kiến trúc.

Một runbook hữu ích có:

1. Triệu chứng và phạm vi ảnh hưởng.
2. Alert hoặc dashboard liên quan.
3. Các bước xác minh đầu tiên.
4. Lệnh hoặc query chỉ đọc để chẩn đoán.
5. Ngưỡng cần escalation.
6. Hành động giảm thiểu an toàn.
7. Điều kiện rollback hoặc forward-fix.
8. Owner và kênh escalation.
9. Cách xác minh hệ thống đã phục hồi.

Ví dụ, runbook cho database timeout có thể hướng dẫn kiểm tra connection pool, query latency, lock wait và database availability trước khi đề xuất restart. Hành động phá hủy hoặc thay đổi dữ liệu cần có điều kiện và quyền rõ ràng.

Không coi một file runbook tồn tại là đủ. Cần có người khác ngoài tác giả thử theo các bước để xác nhận hướng dẫn có thể sử dụng.

## 19. Deployability và observability phải liên kết với nhau

Khả năng triển khai và khả năng quan sát không phải hai checklist tách rời. Một quyết định deploy cần tín hiệu để xác nhận kết quả; một tín hiệu chỉ hữu ích nếu gắn với phiên bản và target đang được triển khai.

Ví dụ:

- Artifact digest cho biết chính xác nội dung nào đang chạy.
- Service version trong metric/log giúp lọc tín hiệu theo release.
- Deployment annotation giúp đặt mốc thời gian trên dashboard.
- Smoke test có trace ID giúp tìm đường đi request.
- Migration run ID liên kết lỗi dữ liệu với thay đổi schema.
- Rollout revision cho biết instance nào đã nhận version mới.

DoD nên yêu cầu các ID cần thiết được truyền xuyên suốt build, deploy và verification. Không dùng một tên version chung chung nếu có thể deploy nhiều digest khác nhau dưới cùng một tag.

## 20. Xác minh sau triển khai

Sau khi deployment controller báo hoàn tất, pipeline cần thực hiện kiểm tra trên target thực tế.

Một luồng cơ bản:

1. Xác nhận đúng environment, cluster, namespace và workload.
2. Xác nhận digest/revision thực tế khớp artifact đã duyệt.
3. Chờ rollout và readiness đạt.
4. Chạy smoke test cho endpoint và luồng quan trọng.
5. Quan sát error rate, latency, saturation và dependency.
6. Kiểm tra migration/data invariant nếu có.
7. Giữ cửa sổ quan sát phù hợp với đặc tính traffic.
8. Lưu kết quả và quyết định promote, pause, rollback hoặc inconclusive.

Một health endpoint trả 200 không chứng minh toàn bộ tính năng đúng. Smoke test nên kiểm tra hành vi có ý nghĩa và không gây tác dụng phụ ngoài dự kiến. Nếu test tạo dữ liệu, cần có cơ chế cleanup hoặc test tenant riêng.

Nếu telemetry backend không khả dụng, không nên tự động đánh dấu observability gate là pass. Policy cần quy định khi nào được retry, chờ hoặc yêu cầu người có thẩm quyền đánh giá.

## 21. Rollout strategy và khả năng quay lui

DoD cần xác định cách phát hành phù hợp với mức rủi ro:

- **Rolling deployment:** thay instance theo từng nhóm; cần tương thích version và graceful shutdown.
- **Blue-green:** chạy hai nhóm môi trường và chuyển traffic; cần kiểm tra schema, session và state dùng chung.
- **Canary:** mở traffic theo tỷ lệ; cần metric và ngưỡng promote/rollback.
- **Feature flag:** tách việc deploy code khỏi việc bật hành vi; cần owner và kế hoạch tắt flag.

Rollback plan phải xem xét cả ứng dụng, schema và dữ liệu. Nếu migration đã xóa cột mà version cũ cần, rollback binary có thể không hoạt động. Khi đó cần forward-fix hoặc migration bù.

Với mỗi release có rủi ro, ghi rõ:

- Điều kiện dừng rollout.
- Metric hoặc check kích hoạt rollback.
- Ai hoặc policy nào có quyền quyết định.
- Phiên bản/artifact quay về.
- Tác động tới schema và dữ liệu.
- Cách xác minh sau rollback.
- Hành động nếu rollback không khả thi.

Không nên viết "có thể rollback" nếu nhóm chưa xác định rollback tới artifact nào và schema hiện tại có tương thích hay không.

## 22. Bảo mật và quyền riêng tư trong vận hành

Observability có thể vô tình tạo thêm đường rò rỉ dữ liệu. Log, trace, dashboard và report đều cần được phân loại.

DoD cần kiểm tra:

- Secret không xuất hiện trong log, artifact hoặc test report.
- PII được masking hoặc loại bỏ theo policy.
- Dashboard và log store có quyền truy cập phù hợp.
- Service account chỉ có quyền cần thiết.
- Debug endpoint không mở công khai ngoài dự kiến.
- Metric label không chứa dữ liệu nhạy cảm hoặc định danh cá nhân.
- Runbook không chứa credential hoặc thông tin truy cập lâu dài.
- Retention phù hợp với mục đích và yêu cầu dữ liệu.

Bật debug logging trong production có thể hữu ích khi điều tra nhưng cần kiểm soát thời gian, phạm vi và dữ liệu được ghi. Nếu có chế độ debug tạm thời, DoD nên yêu cầu owner, thời hạn tắt và audit.

## 23. Chia sẻ trách nhiệm giữa các vai trò

DoD là thỏa thuận của cả nhóm. Một người có thể thực hiện nhiều vai trò, nhưng trách nhiệm cần rõ.

| Vai trò | Đóng góp chính | Bằng chứng hoặc quyết định |
|---|---|---|
| Product owner | Xác định giá trị, acceptance criteria và rủi ro người dùng | Yêu cầu được chấp nhận, phạm vi release |
| Developer | Code, test, config, instrumentation và deploy manifest | PR, test report, metric/log/tracing changes |
| QA | Thiết kế test, negative case và xác minh hành vi | Test result, defect record |
| Platform/DevOps | Pipeline, identity, environment, rollout và recovery | Pipeline result, deployment evidence |
| SRE/Operations | SLI/SLO, alert, dashboard, runbook và response | Operational readiness review |
| Security | Quyền, secret, dependency và threat/risk review | Security check, approval khi cần |
| On-call/service owner | Tiếp nhận vận hành và xác nhận khả năng hỗ trợ | Ownership, escalation và runbook acceptance |

Không nên đẩy toàn bộ observability cho Operations ở cuối dự án. Developer hiểu code path và ngữ cảnh lỗi nhất; họ cần bổ sung instrumentation ngay khi xây dựng tính năng. Operations/SRE giúp xác định tín hiệu và cách phản ứng phù hợp.

## 24. Tổ chức review liên chức năng

Một thay đổi có thể cần review từ nhiều vai trò nhưng không phải mọi PR đều cần một cuộc họp lớn.

Có thể dùng các điểm phối hợp:

- **Refinement:** nhận diện deploy, data, security và observability impact.
- **Design review:** thống nhất SLI, instrumentation, rollout và recovery với thay đổi rủi ro cao.
- **Pull request review:** kiểm tra code, test, config, log/metric và tài liệu.
- **Pre-release review:** xác nhận release evidence, target, migration, approval và rollback.
- **Post-deploy review:** đánh giá tín hiệu sau triển khai và ghi nhận vấn đề.

Dùng template để thu thập câu trả lời không đồng nghĩa bắt buộc họp. Cuộc họp nên dành cho quyết định có trade-off hoặc rủi ro mà tài liệu không giải quyết được.

## 25. Ví dụ: DoD cho tính năng tạo đơn hàng

Giả sử team bổ sung API POST /orders. Tính năng tạo đơn cần kiểm tra chức năng, triển khai và vận hành.

**Acceptance Criteria:**

- Người dùng có quyền có thể tạo đơn với payload hợp lệ.
- Payload không hợp lệ trả lỗi có cấu trúc.
- Mỗi request được xử lý theo quy tắc idempotency đã thống nhất.
- Tổng tiền và trạng thái đơn tuân theo quy tắc nghiệp vụ.
- Request không được phép không tạo đơn hoặc tác dụng phụ.

**Deployability:**

- Artifact được build và truy vết tới commit.
- Config key cho giới hạn item và timeout được validate.
- Workload identity có quyền cần thiết tới database và message broker.
- Migration tương thích với app version cũ trong rolling deployment.
- Readiness và graceful shutdown hoạt động.
- Có rollout timeout và recovery plan.

**Observability:**

- Log ghi event tạo đơn, outcome, request ID và trace ID, không ghi payload nhạy cảm.
- Metric đếm request, success/error, latency và lỗi dependency.
- Trace liên kết API với database/message broker.
- Dashboard hiển thị traffic, error rate và latency theo service version.
- Alert cho tỷ lệ lỗi tăng kéo dài hoặc dependency timeout.
- Runbook hướng dẫn điều tra lỗi tạo đơn và queue backlog.

**Release verification:**

- Đúng artifact digest đang chạy.
- Rollout đủ replica ready.
- Smoke test tạo đơn test trong tenant chuyên dụng và xác minh kết quả.
- Metric trong cửa sổ quan sát nằm trong ngưỡng.
- Không có migration/data reconciliation failure.
- Evidence được lưu cùng release ID.

Nhờ tách tiêu chí như vậy, team biết việc nào phải hoàn tất trong story và việc nào là gate của release.

## 26. Ví dụ DoD trong ticket

Một ticket có thể ghi tiêu chí theo dạng ngắn, dễ review:

```markdown
### Acceptance criteria
- [ ] Request hợp lệ tạo được đơn và trả về mã đơn.
- [ ] Request không hợp lệ trả lỗi có cấu trúc.
- [ ] Retry cùng idempotency key không tạo đơn trùng.

### Definition of Done
- [ ] Unit và integration tests đạt.
- [ ] API contract và config schema được cập nhật.
- [ ] Migration tương thích với phiên bản đang chạy.
- [ ] Log có request/trace ID và không ghi dữ liệu nhạy cảm.
- [ ] Metrics về request, error và latency có thể truy vấn.
- [ ] Dashboard và alert liên quan được cập nhật.
- [ ] Runbook có bước chẩn đoán lỗi mới.
- [ ] Artifact và deployment config được review.
- [ ] Recovery/rollback plan được xác định.

### Release verification
- [ ] Đúng artifact digest được triển khai.
- [ ] Rollout và smoke test đạt.
- [ ] Metric sau deploy nằm trong ngưỡng đã định.
- [ ] Evidence được lưu vào release record.
```

Template cần điều chỉnh theo loại công việc. Một thay đổi không ảnh hưởng schema có thể đánh dấu migration là not applicable với lý do. Không nên yêu cầu mọi ticket phải tạo dashboard mới nếu dashboard hiện có đã trả lời được câu hỏi vận hành.

## 27. Ví dụ pipeline thực thi DoD

Pipeline có thể ánh xạ các điều kiện vào những job rõ ràng:

```yaml
jobs:
  validate:
    steps:
      - validate source and configuration
      - run unit and integration tests
      - build immutable artifact
      - validate deployment manifests

  security:
    steps:
      - scan dependencies and artifact
      - verify secret references and permissions

  deploy:
    needs: [validate, security]
    steps:
      - verify target and approval
      - apply compatible migration
      - deploy artifact by digest
      - wait for rollout readiness

  verify:
    needs: [deploy]
    steps:
      - run smoke and business checks
      - collect metrics, logs and traces
      - evaluate post-deploy thresholds
      - store deployment evidence

  release-decision:
    needs: [verify]
    steps:
      - promote, pause, rollback or mark inconclusive
```

Đây là cấu trúc khái niệm, cần chuyển thành cú pháp của nền tảng CI đang dùng. Các bước bảo mật, approval và migration có thể được tổ chức khác tùy mức rủi ro. Điều quan trọng là mỗi điều kiện DoD có một bước kiểm tra hoặc bằng chứng tương ứng.

Pipeline không thể tự xác nhận những yếu tố chưa được tự động hóa, chẳng hạn runbook đã dễ dùng hay alert có routing đúng. Những mục đó cần review hoặc diễn tập có người tham gia, rồi lưu kết quả.

## 28. Xử lý mục không áp dụng và ngoại lệ

Không phải mọi tiêu chí đều áp dụng cho mọi thay đổi. Tuy nhiên, "N/A" không nên là cách bỏ qua một điều kiện khó đáp ứng.

Một mục có thể được đánh dấu không áp dụng khi:

- Thay đổi không tạo runtime artifact.
- Không có schema/data change.
- Không thêm dependency hoặc permission mới.
- Dashboard/runbook hiện tại đã bao phủ hành vi và không cần sửa.
- Release không làm thay đổi hành vi production.

Khi đánh dấu N/A, ghi lý do và người xác nhận. Với ngoại lệ có rủi ro, cần ghi:

- Tiêu chí nào được miễn.
- Lý do và tác động.
- Biện pháp giảm thiểu tạm thời.
- Người có thẩm quyền chấp thuận.
- Owner xử lý phần còn thiếu.
- Thời hạn hết hiệu lực hoặc release phải hoàn tất.

Ngoại lệ không nên trở thành trạng thái vĩnh viễn. Nếu một tiêu chí thường xuyên bị miễn, DoD hoặc cách triển khai có thể chưa phù hợp; nhóm cần xem lại thiết kế.

## 29. Đo chất lượng của DoD

Một DoD hữu ích giúp phát hiện vấn đề sớm và giảm công việc phát sinh sau release. Có thể theo dõi:

- Tỷ lệ deployment cần rollback hoặc hotfix.
- Tỷ lệ incident có thể liên hệ với thiếu instrumentation hoặc runbook.
- Thời gian từ lúc deploy tới khi phát hiện lỗi.
- Thời gian từ alert tới khi xác định nguyên nhân.
- Tỷ lệ release có đầy đủ post-deploy evidence.
- Tỷ lệ config/permission failure sau deploy.
- Số migration gây incompatibility.
- Số ngoại lệ DoD còn quá hạn.
- Tỷ lệ alert actionable và tỷ lệ alert nhiễu.
- Tỷ lệ service có owner, SLI/SLO và runbook rõ.

Không nên dùng số lượng log, dashboard hay test làm thước đo duy nhất. Mục tiêu là khả năng phát hiện, hiểu và xử lý vấn đề; nhiều telemetry hơn nhưng không có owner hoặc hành động có thể chỉ tăng chi phí.

Nhóm nên xem lại DoD sau incident và release lớn. Nếu một sự cố xảy ra vì thiếu health check hoặc không biết version nào đang chạy, bổ sung tiêu chí cụ thể để ngăn lặp lại.

## 30. Những anti-pattern thường gặp

| Cách làm chưa tốt | Hệ quả | Cách cải thiện |
|---|---|---|
| DoD chỉ yêu cầu code review và unit test | Thiếu điều kiện triển khai và vận hành | Bổ sung deployability/observability theo rủi ro |
| Đợi đến cuối sprint mới hỏi về deploy | Phát hiện muộn config, migration hoặc quyền thiếu | Xem xét từ refinement |
| Coi log là toàn bộ observability | Khó đo xu hướng và liên kết request | Kết hợp logs, metrics và traces |
| Có dashboard nhưng không có owner | Không ai duy trì hoặc phản ứng | Gán service owner và người nhận |
| Alert cho mọi lỗi | Nhiễu và alert fatigue | Alert theo triệu chứng, mức độ và hành động |
| Chỉ kiểm tra health endpoint | Bỏ sót lỗi nghiệp vụ | Thêm smoke/synthetic/business check |
| Nói rollback nhưng không kiểm tra schema | Rollback app có thể không chạy | Kiểm tra tương thích app/schema/data |
| Log toàn bộ request/response | Rò rỉ PII hoặc secret | Chọn field cần thiết và masking |
| Đánh dấu N/A không lý do | Che giấu tiêu chí chưa hoàn tất | Ghi lý do, owner và người xác nhận |
| Runbook chỉ tồn tại trên giấy | On-call không thể xử lý khi sự cố | Diễn tập và review runbook |
| Observability do một nhóm làm sau cùng | Thiếu ngữ cảnh từ code | Developer bổ sung instrumentation cùng tính năng |
| Release gate không lưu evidence | Khó truy vết quyết định | Lưu artifact, target, checks và decision |

## 31. Lộ trình áp dụng trong nhóm

Có thể bắt đầu từ một service có tần suất deploy cao:

1. **Chọn service và owner:** xác định người chịu trách nhiệm cuối cùng về runtime và release.
2. **Đọc lại support/acceptance contract:** xác định hành vi người dùng và mức chất lượng cần giữ.
3. **Lập DoD hiện tại:** tìm những mục đang có và những lỗi sau deploy thường gặp.
4. **Thêm deployability criteria:** artifact, config, identity, migration, rollout và recovery.
5. **Thêm observability criteria:** log, metric, trace, SLI/SLO, dashboard, alert và runbook.
6. **Ánh xạ vào pipeline:** tự động hóa các gate có thể kiểm tra bằng máy.
7. **Định nghĩa review thủ công:** phân công owner cho runbook, alert routing và ngoại lệ.
8. **Diễn tập:** triển khai vào môi trường thử, tạo một lỗi có kiểm soát và kiểm tra khả năng phát hiện/chẩn đoán.
9. **Thu thập feedback:** hỏi developer, QA và on-call tiêu chí nào hữu ích hoặc gây lãng phí.
10. **Cập nhật DoD:** điều chỉnh theo incident, release và thay đổi kiến trúc.

Không cần đưa toàn bộ tiêu chí vào mọi loại công việc ngay từ ngày đầu. Bắt đầu bằng những điều kiện có tác động lớn tới người dùng và khả năng phục hồi, sau đó mở rộng theo dữ liệu.

## 32. Checklist tiêu chí hoàn tất

### Chức năng và chất lượng

- [ ] Acceptance criteria đã được kiểm tra.
- [ ] Code review hoàn tất.
- [ ] Unit/integration/contract tests phù hợp đã đạt.
- [ ] Lỗi và giới hạn đã biết được ghi nhận.
- [ ] Tài liệu API hoặc hành vi được cập nhật.

### Khả năng triển khai

- [ ] Artifact có định danh bất biến và truy vết được.
- [ ] Config được khai báo, validate và có nguồn giá trị rõ.
- [ ] Secret được tham chiếu an toàn.
- [ ] Workload identity có quyền tối thiểu cần thiết.
- [ ] Dependency và target đã được kiểm tra.
- [ ] Migration tương thích với version cùng tồn tại.
- [ ] Health probe và graceful shutdown hoạt động.
- [ ] Rollout strategy và timeout được xác định.
- [ ] Rollback/forward-fix plan phù hợp với schema và dữ liệu.

### Khả năng quan sát và vận hành

- [ ] Log có cấu trúc, correlation ID và không lộ dữ liệu nhạy cảm.
- [ ] Metrics về traffic, errors, latency và saturation có thể truy vấn.
- [ ] Trace liên kết dependency quan trọng nếu cần.
- [ ] SLI/SLO hoặc ngưỡng vận hành được xác định.
- [ ] Dashboard có owner và hiển thị version/deployment.
- [ ] Alert có routing, severity và hành động.
- [ ] Runbook có thể thực hiện và đã được review.
- [ ] Post-deploy smoke/business checks có kết quả.
- [ ] Evidence gắn release, artifact, target và decision.

### Phối hợp và bàn giao

- [ ] Service owner và on-call được xác định.
- [ ] QA, developer và operations đã thống nhất điều kiện chấp nhận.
- [ ] Mục N/A có lý do và người xác nhận.
- [ ] Ngoại lệ có owner, biện pháp giảm thiểu và thời hạn.
- [ ] Kết quả triển khai được chia sẻ cho nhóm chịu trách nhiệm.

## Kết luận

Thiết kế DoD gồm khả năng triển khai và quan sát giúp nhóm định nghĩa chất lượng theo toàn bộ vòng đời thay đổi. Một tính năng chỉ thực sự sẵn sàng khi artifact, cấu hình, quyền, migration, rollout và recovery đã được xem xét; đồng thời hệ thống phát ra log, metric, trace và có dashboard, alert, runbook để người chịu trách nhiệm hiểu điều đang xảy ra.

Đưa các tiêu chí này vào refinement, review và release gate giúp developer, QA, platform, security và operations chia sẻ cùng một kỳ vọng. Mỗi mục cần có cách xác minh và evidence; các ngoại lệ phải có lý do, owner và thời hạn. Nhờ đó, "Done" có nghĩa là nhóm có thể phát hành, nhận biết kết quả và xử lý khi hệ thống không đạt kỳ vọng.

