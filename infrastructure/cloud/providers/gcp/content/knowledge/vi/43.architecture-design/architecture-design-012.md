# Đánh giá trade-offs về bảo mật, độ tin cậy và chi phí

Một kiến trúc Google Cloud tốt không đơn giản là kiến trúc **an toàn nhất**, **không bao giờ gián đoạn** hoặc **có hóa đơn thấp nhất**. Mỗi mục tiêu đều có giới hạn, chi phí và rủi ro. Thêm nhiều bản sao có thể tăng khả năng chịu lỗi nhưng cũng làm tăng chi phí và độ phức tạp. Siết chặt quyền truy cập và chặn toàn bộ đường ra có thể giảm bề mặt tấn công nhưng khiến quy trình triển khai, tích hợp và xử lý sự cố khó hơn. Tối ưu hóa chi phí quá mức có thể giảm số instance dự phòng đến mức hệ thống không đáp ứng lưu lượng đột biến.

Nhiệm vụ của người thiết kế kiến trúc là **xác định ràng buộc không thể đánh đổi**, so sánh các phương án theo dữ liệu, rồi chọn tổ hợp kiểm soát bảo mật, khả năng phục hồi và chi phí phù hợp nhất với mục tiêu nghiệp vụ. Việc đánh giá cần minh bạch về giả định, phần chưa biết và điều kiện khiến quyết định phải được xem xét lại.

Bài học thuộc chương **Thiết kế kiến trúc GCP** của module **CLOUD_PROVIDERS_GCP**. Module hướng dẫn khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, các dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành, theo dõi độ tin cậy và quản lý chi phí. Trong bài này, chúng ta kết nối ba góc nhìn đó để đánh giá các quyết định kiến trúc của ứng dụng Java/Spring trên Google Cloud.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt yêu cầu bắt buộc với tiêu chí có thể tối ưu hoặc đánh đổi.
- Mô tả tác động hai chiều giữa bảo mật, độ tin cậy, hiệu năng, tốc độ triển khai và chi phí.
- Áp dụng shared responsibility, threat modeling và defense in depth vào thiết kế GCP.
- Sử dụng SLI, SLO, error budget, RTO, RPO và phân tích failure mode để ra quyết định.
- Ước tính tổng chi phí sở hữu (TCO), bao gồm resource, network, quan sát và nhân lực vận hành.
- So sánh phương án theo ma trận có trọng số, kiểm tra sensitivity và tránh tính điểm thay cho ràng buộc bắt buộc.
- Phân tích ví dụ Cloud Run, GKE, Compute Engine, Cloud SQL, storage và mạng riêng.
- Viết Architecture Decision Record (ADR) có bằng chứng, biện pháp giảm rủi ro và điều kiện đánh giá lại.

## 1. Trade-off trong kiến trúc là gì?

Trade-off là sự lựa chọn mà khi cải thiện một đặc tính, ta thường phải trả giá bằng một đặc tính khác. Ví dụ:

- Tăng số bản sao và mở rộng đa vùng có thể cải thiện availability nhưng phát sinh chi phí compute, network và vận hành.
- Bật private networking và hạn chế egress giảm một phần rủi ro truy cập trái phép nhưng thêm yêu cầu DNS, routing và monitoring.
- Giảm minimum instances cho Cloud Run có thể tiết kiệm chi phí khi ít tải nhưng làm tăng xác suất cold start.
- Chia nhỏ microservices có thể hỗ trợ phát triển độc lập nhưng tăng số kết nối mạng, danh tính service, dependency và failure mode.
- Tăng thời gian lưu log giúp điều tra sự cố và đáp ứng chính sách nhưng tăng chi phí lưu giữ và rủi ro dữ liệu nhạy cảm bị truy cập.

Không phải mọi thứ đều được phép đánh đổi. Mã hóa bắt buộc, dữ liệu không được rời một phạm vi pháp lý nhất định, yêu cầu audit hoặc quyền tối thiểu theo chính sách có thể là **ràng buộc cứng**. Một phương án vi phạm ràng buộc cứng phải bị loại, dù điểm tổng hợp hoặc hóa đơn thấp hơn.

### Ba lớp quyết định

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Ràng buộc bắt buộc | Điều gì không được vi phạm? | Data residency, regulatory controls, quyền đọc secret |
| Mục tiêu định lượng | Hệ thống cần tốt đến mức nào? | Availability SLO 99,95%; P95 latency 300 ms; ngân sách tháng |
| Ưu tiên và trade-off | Trong những phương án hợp lệ, điều gì quan trọng hơn? | Tốc độ phát hành, vận hành đơn giản, chi phí biến đổi |

Ví dụ, nếu dữ liệu bắt buộc ở một region cụ thể, phương án replica sang region khác có thể không hợp lệ. Không thể chỉ cho nó điểm bảo mật thấp rồi bù bằng điểm availability cao.

## 2. Khung đánh giá: yêu cầu → phương án → bằng chứng → quyết định

Đề xuất một quy trình gồm sáu bước:

1. **Hiểu tác động nghiệp vụ:** ai dùng hệ thống, khi nào, một giờ gián đoạn gây hậu quả gì?
2. **Xác định các guardrail:** dữ liệu nhạy cảm, IAM, residency, audit, quota, ngân sách trần và thời hạn phục hồi.
3. **Thiết kế ít nhất hai phương án khả thi:** ví dụ Cloud Run đơn region + Cloud SQL HA và Cloud Run đa region + database có replication phù hợp.
4. **Đánh giá rủi ro và failure mode:** điều gì có thể thất bại, xác suất/mức tác động, cách phát hiện và xử lý?
5. **Ước tính, thử nghiệm và so sánh:** đo latency, thông lượng, failover, khối lượng dữ liệu và chi phí dưới tải đại diện.
6. **Ghi ADR và theo dõi:** quyết định, lý do, rủi ro còn lại, owner, chỉ số kiểm chứng và mốc đánh giá lại.

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ và SLO"] --> B["Guardrails: bảo mật, compliance, ngân sách"]
    B --> C["Thiết kế phương án hợp lệ"]
    C --> D["Threat model + failure modes"]
    D --> E["Load test + recovery drill + cost estimate"]
    E --> F{"Đạt các ngưỡng bắt buộc?"}
    F -->|"Không"| C
    F -->|"Có"| G["So sánh trade-offs, ghi ADR"]
    G --> H["Triển khai có kiểm soát, đo thực tế"]
    H --> I["Đánh giá lại định kỳ hoặc khi điều kiện đổi"]
~~~

Khung này tránh hai sai lầm: chọn dịch vụ theo cảm tính và tạo một bảng điểm trông chính xác nhưng được xây từ các giả định chưa kiểm chứng.

## 3. Bảo mật: xác định tài sản, tác nhân và đường tấn công

Bảo mật không chỉ là bật một vài sản phẩm. Kiến trúc cần biết **đang bảo vệ thứ gì**, **ai có thể truy cập**, **đường dữ liệu đi đâu** và **điều gì xảy ra khi một thành phần bị xâm nhập**.

### Các tài sản cần bảo vệ

- Dữ liệu khách hàng, giao dịch và thông tin cá nhân.
- Credential: database password, API token, OAuth secret, key.
- Artifact phần mềm và quy trình build/release.
- Quyền thay đổi hạ tầng và cấu hình production.
- Tính toàn vẹn của dữ liệu, thông điệp và bản ghi audit.
- Tính sẵn sàng của endpoint, queue và database.

### Threat modeling ngắn gọn

Với ứng dụng Orders API:

1. Vẽ thành phần và data flow: Internet hoặc client nội bộ → load balancer/Cloud Run → Cloud SQL → Pub/Sub → worker.
2. Đánh dấu trust boundary: public internet, VPC, service identity, project, môi trường staging/production.
3. Liệt kê tác nhân và threat: user chưa xác thực, tài khoản bị chiếm quyền, dependency bị xâm nhập, image độc hại, secret bị lộ.
4. Xác định biện pháp phòng ngừa, phát hiện và phục hồi cho từng threat.
5. Ghi rủi ro còn lại; ưu tiên theo tác động và khả năng xảy ra.

| Nguy cơ | Đường tác động | Kiểm soát gợi ý | Chi phí/độ phức tạp |
|---|---|---|---|
| Token bị rò rỉ trong Git | Truy cập API hoặc DB trái phép | Secret Manager, rotation, code scanning | Phải quản lý IAM và vòng đời secret |
| Runtime identity có quyền rộng | Một service bị xâm nhập ảnh hưởng nhiều tài nguyên | Least privilege, phân tách service accounts | Nhiều IAM bindings và quy trình review |
| API bị lạm dụng | Request bất thường làm tăng tải/hóa đơn | Authentication, rate limiting, Cloud Armor phù hợp | Thêm policy và theo dõi false positive |
| Build pipeline bị chỉnh sửa | Artifact production chứa mã độc | Protected branches, trusted builder, attestations | Tăng công việc supply-chain |
| Dữ liệu truy cập sai region | Vi phạm yêu cầu residency | Resource location policy, thiết kế replication | Giảm lựa chọn DR/cross-region |
| Log chứa PII | Lộ dữ liệu qua hệ thống quan sát | Redaction, access controls, retention | Phức tạp instrumentation và audit |

Không đánh giá mức độ bảo mật chỉ bằng số lượng công cụ. Một hệ thống có nhiều sản phẩm nhưng runtime service account vẫn có quyền Editor toàn project có thể rủi ro hơn hệ thống đơn giản có ranh giới quyền rõ.

## 4. Shared responsibility và bảo mật theo lớp

Google quản lý một phần bảo mật hạ tầng, nhưng khách hàng vẫn phải quản lý cấu hình, dữ liệu, ứng dụng, danh tính và nhiều kiểm soát bổ sung. Phạm vi trách nhiệm thay đổi theo dịch vụ.

| Tầng | Compute Engine | GKE | Cloud Run/App Engine |
|---|---|---|---|
| Host/guest OS | Tự quản guest OS và patch | GKE quản lý nhiều lớp node; mức tự quản tùy mode | Google quản lý môi trường chạy |
| Container/app dependencies | Nếu dùng container, nhóm quản lý | Nhóm quản lý | Nhóm quản lý image/runtime code |
| IAM và runtime identity | Nhóm cấu hình | Nhóm cấu hình IAM/RBAC/Workload Identity | Nhóm cấu hình service account, invoker và policy |
| Network exposure | Firewall, LB, routes | VPC, Service/Gateway, NetworkPolicy | Ingress/egress, VPC connectivity |
| Secret và dữ liệu | Nhóm phân quyền, rotation và bảo vệ | Nhóm phân quyền, rotation và bảo vệ | Nhóm phân quyền, rotation và bảo vệ |
| Logs/audit/IR | Nhóm thiết kế và vận hành | Nhóm thiết kế và vận hành | Nhóm thiết kế và vận hành |

### Defense in depth

Một API xử lý thanh toán không nên chỉ dựa vào một lớp xác thực duy nhất:

- IAM và application authentication ở cửa vào.
- Authorization theo hành động và đối tượng nghiệp vụ trong ứng dụng.
- Runtime service account riêng với quyền tối thiểu.
- Secret Manager, không nhúng credential vào image.
- Private connectivity và policy mạng phù hợp.
- Database user có quyền hạn chế theo schema/table.
- Input validation, rate limiting và bảo vệ chống abuse.
- Audit logs, alert và quy trình ứng phó khi phát hiện bất thường.

Các lớp này không thay thế nhau. Đặt Cloud SQL trên private IP không bảo đảm rằng một API có quyền DB rộng sẽ không thể xóa nhầm dữ liệu; IAM chặt chẽ cũng không thay thế kiểm tra authorization ở tầng ứng dụng.

### Quyền tối thiểu và tính sẵn sàng

Quyền quá rộng tăng blast radius, nhưng thiết kế IAM cũng phải được vận hành an toàn: một thay đổi policy nhầm có thể làm service mất quyền và gây outage. Biện pháp cân bằng gồm:

1. Tách build, deploy và runtime identities.
2. Dùng role đủ nhỏ ở cấp resource có thể áp dụng.
3. Test IAM/config trong môi trường staging hoặc policy-as-code trước khi áp dụng.
4. Giữ phương án break-glass có kiểm soát, thời hạn và audit cho tình huống khẩn cấp.
5. Theo dõi denied requests và quyền được sử dụng thực tế để tinh chỉnh dần.

Không xử lý lỗi PERMISSION_DENIED trong production bằng cách cấp Owner/Editor một cách vội vàng. Cần biết thao tác nào bị từ chối và xác định bản thay đổi quyền tối thiểu.

## 5. Network isolation: bảo mật hơn có phải lúc nào cũng tốt hơn?

Mạng riêng, policy egress chặt và tránh public IP có thể giảm bề mặt tấn công. Tuy nhiên, chúng cũng tạo thêm thành phần vận hành: VPC, DNS, routing, NAT, firewall, gateway, peering hoặc Private Service Connect tùy dịch vụ.

### Ví dụ ba mức triển khai Orders API

| Phương án | Cấu hình | Lợi ích | Đánh đổi |
|---|---|---|---|
| A | Cloud Run có endpoint công khai, xác thực ứng dụng/IAM phù hợp | Dễ tích hợp client bên ngoài | Cần giám sát abuse, ingress và WAF/rate-limit khi cần |
| B | Cloud Run sau load balancer/Cloud Armor, chính sách ingress phù hợp | Quản lý edge, rate-limit, bảo vệ L7 | Tăng chi phí và thao tác cấu hình |
| C | Service chỉ nhận traffic nội bộ, VPC/connectivity phù hợp | Giảm nguồn truy cập trực tiếp | Yêu cầu gateway hoặc đường kết nối cho external clients |

**Không kết luận A là không an toàn hoặc C là luôn đủ an toàn.** Một API public có authentication, authorization, rate limit và quan sát tốt có thể đáp ứng yêu cầu; một API chỉ internal nhưng không kiểm soát quyền từng tenant vẫn có thể lộ dữ liệu. Chọn mô hình theo loại khách hàng, threat model và ranh giới trust.

### Chi phí và độ tin cậy của network

- Private egress có thể phát sinh thành phần tính phí như NAT, load balancer hoặc kết nối mạng khác.
- Routing phức tạp tăng khả năng cấu hình sai DNS/firewall khiến deployment hoặc health check thất bại.
- Tách VPC/project giảm một phần blast radius nhưng tạo thêm cross-project permissions và đường kết nối.
- Khi cần nhiều region, network egress và data replication có thể là thành phần chi phí đáng kể.

Trước production, kiểm tra cả đường đi của request **và** đường đi của quản trị: pull image, truy cập Secret Manager, metrics/logging, DNS resolution, access tới database và thao tác rollback.

## 6. Bảo vệ dữ liệu: mã hóa, khóa và vị trí dữ liệu

Các dịch vụ Google Cloud cung cấp encryption at rest và in transit ở các phạm vi nhất định, nhưng kiến trúc phải chọn cách quản lý khóa, nơi lưu bản sao và quyền truy cập dữ liệu phù hợp với yêu cầu.

| Quyết định | Lợi ích | Chi phí/rủi ro vận hành |
|---|---|---|
| Mã hóa mặc định do dịch vụ quản lý | Ít công sức quản lý key | Ít quyền điều khiển key lifecycle theo chính sách đặc thù |
| CMEK bằng Cloud KMS trên dịch vụ hỗ trợ | Tăng kiểm soát key và đáp ứng một số yêu cầu compliance | Phải quản lý IAM key, vòng đời, audit, availability của key và phí liên quan |
| Thêm lớp mã hóa ở ứng dụng | Bảo vệ dữ liệu theo ranh giới nghiệp vụ riêng | Quản lý key phức tạp, ảnh hưởng search/index và khôi phục |
| Replication đa region | Tăng lựa chọn phục hồi và độ bền | Tăng phạm vi lưu trữ, network/cost và yêu cầu residency |
| Retention dài | Hỗ trợ audit và điều tra | Tăng dữ liệu lưu, tác động riêng tư và chi phí |
| Retention tối thiểu | Giảm lưu dữ liệu không cần thiết | Có thể thiếu dữ liệu cho điều tra/khôi phục nếu cấu hình sai |

### CMEK không miễn phí về mặt độ tin cậy

Khi dùng customer-managed encryption keys, khả năng truy cập key trở thành phụ thuộc vận hành của dịch vụ. Nếu key bị vô hiệu hóa, thu hồi quyền hoặc cấu hình key sai, dữ liệu có thể không đọc/ghi được theo hành vi của từng dịch vụ. Vì vậy, cần:

- Xác nhận dịch vụ và resource hỗ trợ CMEK trong region phù hợp.
- Dùng key location/phân quyền theo yêu cầu.
- Quản lý rotation, key version và quyền sử dụng key qua quy trình review.
- Theo dõi lỗi truy cập KMS và audit.
- Diễn tập phục hồi khi key không khả dụng, không chỉ diễn tập restore dữ liệu.

Không xóa hoặc vô hiệu hóa key đang bảo vệ dữ liệu nếu chưa đánh giá tác động. Quyền quản lý key nên được tách khỏi quyền quản lý dữ liệu khi yêu cầu tổ chức cần phân tách nhiệm vụ.

## 7. Độ tin cậy: xác định điều người dùng thực sự quan tâm

Độ tin cậy không thể đo chỉ bằng CPU uptime hoặc số Pod Running. Một hệ thống có thể trả HTTP 200 nhưng đơn hàng không được lưu; hoặc API healthy nhưng worker không xử lý message trong thời hạn cam kết.

### SLI, SLO và error budget

- **SLI (Service Level Indicator):** phép đo chất lượng dịch vụ, ví dụ tỷ lệ request thành công hoặc tỷ lệ đơn hàng hoàn tất trong 30 giây.
- **SLO (Service Level Objective):** ngưỡng mục tiêu cho SLI trong một cửa sổ thời gian.
- **Error budget:** lượng lỗi tối đa được chấp nhận theo SLO đó.

Ví dụ: API có mục tiêu **99,9% request hợp lệ thành công trong 30 ngày**. Nếu trong kỳ có 1.000.000 request hợp lệ, tối đa 1.000 request thất bại nằm trong error budget về mặt toán học. Việc tính SLI cần xác định chính xác request nào được tính, lỗi nào do client, lỗi nào do server và cách loại trừ trường hợp không hợp lệ.

~~~text
Good request ratio = good_events / valid_events
Error budget (events) = valid_events * (1 - target_ratio)
~~~

Không dùng công thức thời gian downtime để thay thế request-based SLO một cách máy móc. Nếu SLO được định nghĩa theo thời gian, có thể quy đổi mức không sẵn sàng thành thời lượng; nếu SLO theo request, phải đếm sự kiện theo đúng định nghĩa.

### Latency SLO

Đừng chỉ đo latency trung bình. Ví dụ:

~~~text
99% request hợp lệ có thời gian phản hồi < 400 ms
trong cửa sổ 28 ngày
~~~

P95/P99 latency và histogram giúp hiểu tail latency. Việc đặt SLO cần gắn với trải nghiệm người dùng và baseline; không chọn một con số rất thấp chỉ để có vẻ chuyên nghiệp.

### RTO và RPO

- **RTO (Recovery Time Objective):** khoảng thời gian tối đa chấp nhận được để khôi phục dịch vụ sau gián đoạn.
- **RPO (Recovery Point Objective):** lượng dữ liệu mất tối đa có thể chấp nhận, thường biểu diễn qua thời gian tính đến điểm khôi phục.

Ví dụ: RTO 30 phút, RPO 5 phút là hai ràng buộc khác nhau. Thêm replica của API có thể giúp khôi phục compute nhanh hơn nhưng không tự bảo đảm database chỉ mất tối đa 5 phút dữ liệu.

### Reliability không đồng nghĩa đa region

Đa region có thể tăng khả năng chịu lỗi region nhưng cũng tạo lỗi mới: replication lag, split-brain, routing, inconsistent writes, khóa và điều phối failover. Nếu nghiệp vụ chấp nhận RTO dài hơn, single-region multi-zone kết hợp backup/restore đã diễn tập có thể là lựa chọn tốt hơn về cả chi phí và độ phức tạp.

## 8. Phân tích failure modes trước khi mua thêm khả năng chịu lỗi

Một hệ thống thường không thất bại chỉ vì server bị tắt. Cần phân tích toàn bộ chuỗi phụ thuộc:

~~~mermaid
flowchart LR
    A["Client"] --> B["Ingress / Load Balancer"]
    B --> C["Orders API"]
    C --> D["Cloud SQL"]
    C --> E["Payment API"]
    C --> F["Pub/Sub"]
    F --> G["Order Worker"]
    G --> H["Cloud Storage"]
    C --> S["Secret Manager / Identity"]
    G --> S
~~~

Nếu thêm hai region cho Orders API nhưng vẫn dùng một database chỉ có một điểm lỗi không được kiểm soát, toàn hệ thống chưa chắc đáp ứng RTO mới. Tương tự, nhiều bản sao API không giúp ích nếu mọi replica dùng cùng credential đã bị thu hồi hoặc cùng một dependency bên ngoài đang gián đoạn.

### Mẫu bảng failure mode

| Failure mode | Tác động | Tín hiệu phát hiện | Cách giới hạn/khôi phục | Rủi ro còn lại |
|---|---|---|---|---|
| Một container/Pod crash | Một phần request lỗi | Restart, error rate, readiness | Multiple replicas, restart, health checks | Tải tăng lên replica còn lại |
| Một zone không khả dụng | Mất một phần capacity | Region/zone metrics, failed nodes | Multi-zone placement, regional resources | Phụ thuộc chung ở region |
| Database failover | Giao dịch có thể timeout | Connection errors, DB metrics | HA, retry có giới hạn, idempotency | Kết nối đang mở có thể bị cắt |
| Dependency thanh toán timeout | Đơn hàng không hoàn tất | Dependency latency, business SLI | Timeout, circuit breaker, queue/fallback nếu nghiệp vụ cho phép | Tồn đọng hoặc tác động nghiệp vụ |
| IAM hoặc secret bị cấu hình sai | App không truy cập data/API | PermissionDenied, startup failures | Change review, canary, rollback, audit | Khôi phục phụ thuộc quyền quản trị |
| Release tạo lỗi logic | Lỗi diện rộng | Error budget burn, traces, synthetic tests | Progressive rollout, kill switch, rollback | Schema/data có thể không rollback được |
| Region outage | Nhiều thành phần không sẵn sàng | Monitoring từ region khác | Multi-region DR hoặc khôi phục ở region dự phòng | Replication lag và failover complexity |
| Build artifact bị xâm nhập | Ảnh hưởng bảo mật/tính toàn vẹn | Provenance/scan/audit | Signed provenance, approval, rollback và revocation | Phát hiện có thể đến muộn |

Đừng chỉ chấm severity và probability theo trực giác. Ghi nguồn bằng chứng: tần suất đã quan sát, incident trước đó, đặc tính dependency, kiểm thử failover và giả định trong thiết kế.

### Single point of failure có nhiều hình thức

- **Compute:** một VM/Pod/instance.
- **State:** database hoặc storage không có kế hoạch phục hồi.
- **Control plane:** pipeline, quyền IAM hoặc hệ thống DNS.
- **Con người/quy trình:** chỉ một người biết cách rollback, không có runbook.
- **Thay đổi:** tất cả replica được deploy đồng thời với cùng một lỗi.
- **Tổ chức:** không rõ owner, alert không được định tuyến đến người trực.

Thiết kế HA cần xét cả các điểm lỗi chung, không chỉ đếm instance.

## 9. Các cơ chế reliability và trade-off của chúng

### Redundancy và đa vùng

Nhiều replica ở nhiều zone có thể giảm tác động của lỗi instance/zone. Nhưng replica tiêu tốn tài nguyên và có thể khiến trạng thái phân tán phức tạp hơn. Với hệ thống stateless, replica thường đơn giản; với database hoặc xử lý ghi, phải hiểu tính nhất quán, replication và failover.

### Timeout, retry, backoff và idempotency

Retry giúp vượt qua lỗi tạm thời nhưng **có thể gây retry storm** khi dependency đang quá tải. Ví dụ 100 request gốc, mỗi request thử lại ba lần có thể nhân đáng kể lưu lượng đến backend lỗi. Hãy dùng:

- Timeout có giới hạn theo ngân sách thời gian request.
- Retry chỉ với lỗi phù hợp; không retry vô tội vạ lỗi dữ liệu hoặc authorization.
- Exponential backoff, jitter và giới hạn số lần/chi phí retry.
- Circuit breaker, bulkhead hoặc queue để cô lập lỗi.
- Idempotency key cho thao tác ghi, thanh toán hoặc tạo đơn hàng để tránh xử lý trùng.

Ví dụ pseudocode cho lời gọi đến đối tác thanh toán:

~~~text
idempotencyKey = orderId + ":payment"
attempt = 0

while attempt < maxAttempts:
    result = callPartner(
        idempotencyKey=idempotencyKey,
        timeout=perAttemptTimeout)

    if result.success:
        return result
    if result.permanentFailure:
        stopAndReport(result)

    sleep(backoffWithJitter(attempt))
    attempt += 1

return pendingForReconciliation
~~~

Mã giả nhấn mạnh idempotency và phân biệt lỗi tạm thời/vĩnh viễn. Trong hệ thống thanh toán thật, cần hợp đồng idempotency với đối tác, tracking trạng thái không rõ kết quả (unknown outcome) và reconciliation; không được hiểu timeout nghĩa là giao dịch chắc chắn chưa thực hiện.

### Queue buffering và xử lý bất đồng bộ

Pub/Sub giúp tách API khỏi worker, giảm phụ thuộc thời gian giữa các thành phần và cho phép scale độc lập. Nhưng queue tạo thêm chi phí, latency end-to-end, yêu cầu xử lý duplicate, retry và dead-letter. Nếu mọi tác vụ bắt buộc đồng bộ trong vài trăm mili giây, chuyển tất cả vào queue có thể vi phạm kỳ vọng người dùng.

### Backup và restore

Backup hỗ trợ phục hồi dữ liệu trước lỗi logic hoặc xóa nhầm; replica đồng bộ **không thay thế backup**, vì một lệnh xóa sai có thể lan sang replica. Ngược lại, backup không bảo đảm availability khi một zone lỗi nếu khôi phục mất nhiều giờ. Cần cả HA và DR theo RTO/RPO.

### Progressive delivery

Canary 5–10% traffic có thể giảm blast radius của release lỗi; nhưng còn phải bảo đảm metric đủ volume để phát hiện lỗi và client không dùng chung state không tương thích. Các nền tảng như Cloud Run có revision traffic split, GKE dùng Deployment kết hợp progressive delivery tools nếu cần kiểm soát traffic tinh hơn. Kiến trúc càng nhiều giai đoạn phát hành thì pipeline và monitoring càng phức tạp.

### Sự đánh đổi khi tăng resilience

| Cơ chế | Lợi ích | Đánh đổi |
|---|---|---|
| Minimum instances | Giảm cold start, capacity sẵn sàng | Chi phí khi idle |
| Đa zone | Chịu lỗi zone tốt hơn | Replica và network, giới hạn placement |
| Đa region | Thêm phương án khi region outage | Replication, routing, chi phí, consistency |
| Retry/backoff | Phục hồi lỗi tạm thời | Thêm latency và tải nếu thiết kế sai |
| Circuit breaker | Bảo vệ downstream khỏi cascading failures | Có thể từ chối request khi dependency chưa hồi phục hoàn toàn |
| Queue | Tách nhịp xử lý, tăng khả năng hấp thụ đột biến | Eventual consistency, duplicate, backlog, DLQ |
| Backup/PITR | Phục hồi khi dữ liệu bị xóa/sai | Phí storage/logging và thời gian restore |
| Canary/rollback | Giới hạn tác động release lỗi | Đòi hỏi metric, automation và tương thích schema |

## 10. Chi phí cloud: tổng chi phí sở hữu thay vì hóa đơn VM

Chi phí kiến trúc phải được nhìn theo vòng đời: development, staging, production, backup, sự cố, phục hồi và nâng cấp. Các khoản không xuất hiện trong chi phí compute có thể trở thành phần đáng kể.

~~~text
Total Cost of Ownership (TCO)
  = runtime resources
  + data storage, backups and replication
  + network egress, load balancing, NAT/connectivity
  + managed databases, cache, messaging
  + observability, logging, security and key management
  + build/release and artifact storage
  + operational effort, incidents and maintenance
~~~

### Những yếu tố dễ bỏ sót

| Nhóm | Ví dụ |
|---|---|
| Compute | CPU/memory, disk, GPU, minimum instances, reservations |
| Network | Internet egress, cross-zone/region transfer khi được tính phí, LB, Cloud NAT |
| Data | Database instance, storage, read/write operations, backup, PITR, replicas |
| Telemetry | Log ingestion/storage, metrics, trace samples |
| Security | KMS operations, security tooling, secrets, kiểm tra supply-chain |
| Operations | Trực ca, nâng cấp GKE, vá OS, diễn tập failover, incident recovery |
| Non-production | Staging, CI test project, temporary environments và tài nguyên bị bỏ quên |

Không thể kết luận Cloud Run rẻ hơn GKE hay VM trong mọi trường hợp. Cloud Run có thể phù hợp với workload gián đoạn và scale-to-zero; GKE có thể tận dụng capacity dùng chung cho nhiều service; Compute Engine có thể tối ưu khi tải đều và tổ chức vận hành hiệu quả. Để quyết định, cần dựa trên tài nguyên thực đo và báo giá hiện hành.

### Cost allocation và trách nhiệm

Một kiến trúc không có owner cho chi phí rất khó tối ưu. Nên:

- Dùng project/folder để phân định môi trường hoặc nhóm.
- Áp dụng labels/tags phù hợp cho cost allocation, nơi dịch vụ hỗ trợ.
- Bật Cloud Billing export sang BigQuery để phân tích chi phí theo kỳ.
- Đặt budget alerts; **cảnh báo ngân sách không mặc định tự ngắt tiêu dùng hoặc bảo đảm giới hạn chi phí**.
- Theo dõi service owner, cost center và ngày hết hạn tài nguyên thử nghiệm.
- So sánh dự toán với hóa đơn thực tế sau vài tuần hoặc một chu kỳ tải đầy đủ.

## 11. Tính toán chi phí theo mô hình workload

Trước khi dùng Pricing Calculator, cần đo hoặc ước lượng profile tải.

### Mô hình request-driven

Giả sử Orders API có:

- Trung bình 20 request/giây trong giờ làm việc.
- Peak 300 request/giây trong 15 phút.
- Mỗi request chiếm CPU time và memory khác nhau.
- Ban đêm có khoảng thời gian rất ít request.

Các biến cần đo:

- CPU time per request và request concurrency.
- Memory per instance, startup time và số connection DB.
- Số minimum/maximum instances cần cho latency SLO.
- Request size, response size và network egress.
- Tần suất request đến dịch vụ phụ trợ và lượng log/trace.

Cloud Run có thể tiết kiệm thời gian idle nếu cấu hình phù hợp, nhưng minimum instances hoặc instance-based billing thay đổi profile chi phí. Với GKE, cần tính Pod requests, overhead, node capacity, autoscaler, cluster charges và phần capacity đang idle. Với VM, cần tính thời gian VM chạy, disk và các LB/HA components.

### Mô hình CPU-utilization không đủ

CPU 30% không nhất thiết chứng tỏ một workload có thể giảm 70% chi phí. Có thể workload bị giới hạn bởi memory, I/O, kết nối hoặc latency tail. Tương tự, request/second cao không có nghĩa CPU cao nếu request chỉ đọc cache.

Nên đo bằng load test với biểu đồ:

1. Throughput và error ratio.
2. P50/P95/P99 latency.
3. CPU và memory theo replica/instance.
4. Connection pool, queue depth và dependency latency.
5. Chi phí theo môi trường thử nghiệm trong kỳ đo.

Với chi phí production, cần tính đủ traffic theo ngày/tuần/tháng, không lấy peak 15 phút nhân cho cả tháng.

### Mô hình dữ liệu bền vững

Ví dụ database 100 GiB và tăng 10 GiB mỗi tháng:

- Primary storage tăng theo thời gian.
- HA hoặc replica có thể làm tăng tài nguyên compute/storage.
- Backups, transaction logs và PITR phát sinh lưu trữ khác.
- Cross-region replica hoặc export có thể phát sinh network/data transfer.
- Các query hoặc giao dịch cũng tạo tải CPU, IOPS và latency.

Không chỉ dùng giá một GiB storage để ước tính tổng chi phí database. Nếu sử dụng Cloud SQL, cần xem cấu hình instance, HA, backups, storage, network và license/tier phù hợp.

### Phân tích theo đơn vị nghiệp vụ

Công thức đơn giản:

~~~text
Unit cost per successful order
  = attributable monthly service cost
    / successful orders completed in that month
~~~

Chỉ số này hữu ích khi tính theo cùng phạm vi chi phí và định nghĩa “thành công” ổn định. Nếu tăng reliability làm giảm tỷ lệ đơn hàng thất bại, chi phí runtime có thể tăng nhưng **cost per successful order** lại giảm. Do đó, “hóa đơn thấp nhất” không phải luôn là mục tiêu tối ưu cho doanh nghiệp.

## 12. Các biện pháp tối ưu chi phí và tác động đến security/reliability

| Biện pháp | Khả năng tiết kiệm | Rủi ro nếu làm quá mức | Kiểm soát |
|---|---|---|---|
| Right-size CPU/memory | Giảm tài nguyên dư | OOM, throttling, latency | Load test và quan sát percentile |
| Giảm min instances | Ít compute khi nhàn rỗi | Cold start, startup thắt nút | Đo user-facing latency SLO |
| Chuyển sang preemptible/Spot capacity nơi phù hợp | Giảm đơn giá một số workload | Bị thu hồi, gián đoạn tác vụ | Checkpoint, retry, noncritical workloads |
| Giảm retention log | Giảm lưu dữ liệu | Thiếu bằng chứng cho incident/audit | Retention theo phân loại log |
| Sampling traces | Giảm telemetry | Bỏ sót một số lỗi hiếm | Error-biased sampling hoặc sampling có mục tiêu |
| Giảm replica/region dự phòng | Giảm compute/network | Giảm availability/failover capacity | Đo RTO/SLO, thử nghiệm fault |
| Batch request/message | Giảm overhead | Tăng latency và blast radius mỗi batch | Giới hạn batch size và deadline |
| Reserved/committed capacity nơi phù hợp | Giảm giá với tải ổn định | Cam kết chi phí và thiếu linh hoạt | Forecast và phân tích sử dụng dài hạn |
| Tắt test environment theo lịch | Giảm chi phí non-production | Hỏng integration/backup nếu job chạy ngoài lịch | Scheduling, owner và quy trình bật lại |

Không nên hy sinh các bảo vệ nền tảng như mã hóa, backup bắt buộc, khả năng audit hoặc least privilege chỉ để giảm chi phí. Nếu đề xuất tiết kiệm vi phạm guardrail, phải loại hoặc xin thay đổi ràng buộc qua quy trình quản trị được phê duyệt.

### FinOps là một vòng lặp

1. **Inform:** thấy chi phí theo project/service/team và đơn vị nghiệp vụ.
2. **Optimize:** right-size, loại bỏ tài nguyên mồ côi, thay đổi billing phù hợp.
3. **Operate:** phân công owner, đặt cảnh báo và xem xét tối ưu theo chu kỳ.

Mọi thay đổi giảm chi phí quan trọng nên có một phép đo trước/sau với guardrail SLO. Nếu chi phí giảm 15% nhưng error budget bị tiêu thụ nhanh hơn rõ rệt, cần đánh giá lại.

## 13. So sánh nền tảng GCP dưới góc nhìn ba mục tiêu

Chọn Compute Engine, GKE, Cloud Run hay App Engine là quyết định tác động đến cả ba chiều. Bảng dưới đây nêu các đặc điểm thiết kế, **không phải xếp hạng an toàn tuyệt đối**.

| Platform | Bảo mật | Độ tin cậy | Chi phí/vận hành |
|---|---|---|---|
| Compute Engine | Tự quản guest OS, firewall, image patch; kiểm soát OS cao | Có thể dùng MIG, nhiều zone, LB; tự thiết kế HA/DR | VM/disk/network, nhiều công việc OS/patch |
| GKE Standard | RBAC, NetworkPolicy, Workload Identity; nhóm quản node nhiều hơn | Kubernetes orchestration, HPA/node autoscaling, rollout | Cluster/node capacity, storage, network và platform team |
| GKE Autopilot | Nhiều chính sách node/security được quản lý; vẫn cần quyền workload | GKE quản capacity theo workload; vẫn thiết kế Pod topology/SLO | Chi phí theo workload mode, giảm việc quản node |
| Cloud Run | Runtime service account, ingress/egress, container/image controls | Revision, traffic splitting, autoscaling; dependency vẫn phải có HA | Chi phí theo resource/billing model, min instances, network |
| App Engine | Managed runtime/service identity, giới hạn và tính năng theo môi trường | Version/traffic splitting, autoscaling tùy Standard/Flexible | Instance pricing, legacy integration, chi phí migration nếu đổi |

### Ví dụ so sánh hai phương án API Spring Boot

**Phương án A — Cloud Run + Cloud SQL trong một region**

- Không quản cluster, ít công việc node patching.
- Dùng Cloud Run IAM, Secret Manager, controlled ingress, audit.
- Dùng Cloud SQL HA nếu RTO/availability yêu cầu và chi phí phù hợp.
- Có thể cần min instances để kiểm soát cold-start.
- Khi cả region bị gián đoạn, cần một kế hoạch DR riêng.

**Phương án B — GKE regional + Cloud SQL HA trong một region**

- Kiểm soát sâu hơn Kubernetes networking, scheduling và policy.
- Node/Pod có thể đặt đa zone, có HPA và rolling updates.
- Cần hiểu cluster admission, node pool, RBAC, probes và resource requests.
- Chi phí có thể tốt nếu đã có cluster dùng chung; có thể không hợp lý cho một API nhỏ.
- Nếu vẫn phụ thuộc một Cloud SQL region, khả năng chịu lỗi region chưa được giải quyết.

**Kết luận:** Nếu SLO của API và yêu cầu compliance đều đáp ứng, phương án ít vận hành hơn thường đáng cân nhắc. Nhưng nếu bắt buộc Kubernetes policy/sidecar hoặc sử dụng cluster chung rất hiệu quả, GKE có thể hợp lý hơn.

## 14. Phương pháp so sánh định lượng và rủi ro bị đánh lừa bởi điểm số

Một ma trận trọng số giúp trao đổi quyết định có cấu trúc, nhưng chỉ dùng sau khi đã loại phương án không đáp ứng guardrail.

Giả sử có ba lựa chọn:

- A: Cloud Run đơn region + Cloud SQL HA.
- B: Cloud Run đa region + chiến lược dữ liệu DR được thiết kế riêng.
- C: GKE regional + Cloud SQL HA.

Đặt thang điểm 1–5 cho từng tiêu chí, 5 là tốt nhất trong bối cảnh được mô tả. Đây là **điểm ví dụ do nhóm kiến trúc gán**, không phải đo kiểm hay xếp hạng chính thức của Google Cloud.

| Tiêu chí | Trọng số | A | B | C |
|---|---:|---:|---:|---:|
| Đáp ứng SLO và khả năng phục hồi | 35% | 3 | 5 | 4 |
| Giảm rủi ro bảo mật/tuân thủ | 30% | 4 | 4 | 4 |
| Tổng chi phí sở hữu thấp | 25% | 5 | 2 | 3 |
| Đơn giản vận hành và triển khai | 10% | 5 | 2 | 2 |

Tổng điểm minh họa:

~~~text
Score(A) = 0.35*3 + 0.30*4 + 0.25*5 + 0.10*5 = 4.00
Score(B) = 0.35*5 + 0.30*4 + 0.25*2 + 0.10*2 = 3.65
Score(C) = 0.35*4 + 0.30*4 + 0.25*3 + 0.10*2 = 3.55
~~~

Theo những điểm giả định trên, A dẫn đầu. Nhưng nếu tổ chức có yêu cầu bắt buộc **khôi phục sau region outage trong 10 phút**, mà A không đáp ứng thì A bị loại trước khi chấm điểm. B có thể là lựa chọn dù hóa đơn cao hơn.

### Không dùng điểm số để hợp thức hóa giả định

- “Bảo mật 4/5” không có ý nghĩa nếu chưa xác định threat và control cần có.
- “Reliability 5/5” không thể suy ra chỉ vì có hai region; phải kiểm thử failover và dữ liệu.
- “Chi phí 2/5” phải xuất phát từ cost model hoặc hóa đơn, không dựa trên cảm giác “đa region chắc đắt”.
- Mỗi điểm cần owner, nguồn chứng cứ và độ tin cậy. Có thể dùng khoảng điểm khi chưa chắc.

### Sensitivity analysis

Thay trọng số và xem quyết định có đổi không. Nếu tăng trọng số reliability từ 35% lên 55%, giảm cost xuống 10% và giữ tổng bằng 100%, B có thể vượt A tùy điểm các tiêu chí khác. Nếu chỉ cần thay đổi trọng số nhỏ mà người thắng thay đổi liên tục, quyết định **nhạy với giả định**, cần thu thập thêm dữ liệu hoặc làm rõ ưu tiên của stakeholder.

Đặt các câu hỏi:

1. Phương án nào vẫn tốt khi lưu lượng tăng gấp ba?
2. Nếu database chiếm 70% hóa đơn, tối ưu runtime có còn đáng kể?
3. Nếu yêu cầu RTO giảm một nửa, cần thay đổi cấu trúc nào?
4. Nếu nhân sự trực ca ít đi, chi phí vận hành GKE/VM thay đổi thế nào?
5. Nếu quy định dữ liệu thay đổi, phương án nào bị loại?

### Pareto frontier

Một phương án bị **dominated** nếu có phương án khác tốt hơn hoặc bằng trên mọi tiêu chí quan trọng, và tốt hơn ít nhất một tiêu chí, trong cùng các ràng buộc. Khi đó có thể loại phương án dominated khỏi shortlist.

Thực tế thường có nhiều phương án không ai thắng tuyệt đối: một phương án rẻ hơn nhưng RTO chậm hơn; phương án khác nhanh phục hồi hơn nhưng đắt và phức tạp hơn. Chúng nằm trên mặt trận đánh đổi (Pareto frontier) và cần quyết định dựa trên mục tiêu nghiệp vụ.

## 15. Ví dụ xuyên suốt: Orders API và hai mức yêu cầu

Giả sử ứng dụng **orders-api** viết bằng Spring Boot, dùng Cloud SQL PostgreSQL, Pub/Sub và Cloud Storage. Service có dữ liệu thanh toán nhưng không lưu trực tiếp thông tin thẻ. Đây là một **kịch bản giả định**, không phải hệ thống hoặc con số thực tế của tổ chức nào.

### Bối cảnh

- API phục vụ khách hàng tại một thị trường, lưu lượng theo giờ cao điểm.
- Dữ liệu đơn hàng phải bền vững và có audit trail.
- Deploy vài lần mỗi tuần.
- Đội vận hành nhỏ, ưu tiên hệ thống đơn giản.
- Database có giao dịch quan trọng; duplicate payment không được phép.

### Mức 1: ứng dụng chưa phải hệ thống trọng yếu

Giả sử:

- Availability SLO 99,9% theo request hợp lệ.
- RTO mục tiêu 2 giờ cho tình huống mất region.
- RPO mục tiêu 15 phút với dữ liệu có thể khôi phục theo quy trình được kiểm chứng.
- Ngân sách có giới hạn, chịu được một phần downtime.

Một ứng viên:

~~~mermaid
flowchart TD
    U["Clients"] --> CR["Cloud Run Orders API<br/>một region"]
    CR --> DB["Cloud SQL<br/>HA khi phù hợp"]
    CR --> PS["Pub/Sub"]
    PS --> W["Cloud Run worker/Job"]
    CR --> SM["Secret Manager"]
    DB --> BK["Backups + PITR<br/>theo cấu hình"]
    CR --> MON["Cloud Monitoring / Logging"]
    W --> MON
~~~

Các hạng mục thiết kế:

- Cloud Run service có min/max instances, concurrency và timeout dựa trên load test.
- Cloud SQL HA trong region nếu yêu cầu chịu lỗi zone, backup/PITR phù hợp.
- Lưu secret ngoài source; runtime service account chỉ có quyền cần thiết.
- Định nghĩa idempotency key cho đơn hàng/thanh toán.
- Cảnh báo theo error budget burn và độ trễ nghiệp vụ.
- Diễn tập restore database và quy trình tạo service ở region dự phòng để kiểm chứng RTO/RPO.

**Trade-off:** ít chi phí vận hành nền tảng hơn GKE, nhưng cần kế hoạch phục hồi khi region gặp sự cố; một single-region deployment không tự đáp ứng RTO region chỉ vì Cloud Run quản lý instance.

### Mức 2: hệ thống giao dịch trọng yếu

Giả sử yêu cầu thay đổi:

- SLO 99,99% cho luồng tạo đơn hàng.
- RTO 10 phút đối với outage của region chính.
- RPO gần 0 cho giao dịch quan trọng, có tiêu chí nghiệp vụ cụ thể.
- Dữ liệu có thể được lưu/replicate trong các region đã phê duyệt.

Một ứng viên:

- Hai deployment API ở các region khác nhau, routing/failover được thiết kế và thử.
- Data architecture đáp ứng yêu cầu RPO: đánh giá database có multi-region capability, replication mode, consistency và failover thực tế.
- Idempotency, reconciliation và conflict resolution cho write path.
- Independent monitoring và quy trình điều phối failover.
- Security và key/secret availability ở cả hai region.

Không thể đạt RPO gần 0 một cách đáng tin cậy chỉ bằng việc thêm asynchronous cross-region replica mà không hiểu replication lag. Nếu workload yêu cầu giao dịch ghi đa vùng với consistency chặt, cần đánh giá dịch vụ database và mô hình dữ liệu được thiết kế cho yêu cầu đó, ví dụ Spanner khi phù hợp; điều này có thể thay đổi đáng kể code, schema và chi phí.

**Trade-off:** có khả năng đạt phục hồi nhanh hơn nhưng tăng chi phí, network, trạng thái phân tán, thử nghiệm và đội vận hành. Phương án này chỉ đáng làm khi tác động nghiệp vụ của downtime và mất dữ liệu biện minh cho đầu tư.

### Bảng so sánh hai mức

| Tiêu chí | Mức 1 | Mức 2 |
|---|---|---|
| Compute routing | Một region | Nhiều region, failover được kiểm chứng |
| Database | HA/backup trong giới hạn RTO/RPO | Thiết kế đa region hoặc chiến lược consistency phù hợp |
| Chi phí | Thường thấp hơn nếu mọi yếu tố khác tương tự | Thường tăng do redundancy và replication |
| Vận hành | Ít thành phần hơn | Runbook/automation và diễn tập phức tạp hơn |
| Bảo mật | IAM, network, secrets, audit bắt buộc | Các kiểm soát tương tự áp dụng trên nhiều region |
| Điểm yếu còn lại | Region outage và thời gian restore | Data consistency/failover orchestration, common-mode failure |

Điều quan trọng là **không đánh đồng security, reliability và cost thành ba thanh trượt độc lập**. Một quyết định đổi database để cải thiện RPO sẽ tác động đến quyền truy cập dữ liệu, schema, network transfer, bill và kỹ năng vận hành.

## 16. Rủi ro, khả năng xảy ra và chi phí mất dịch vụ

Không phải quyết định nào cũng cần một hệ thống điểm phức tạp, nhưng nhiều quyết định có thể được mô tả bằng **expected loss** để stakeholder hiểu tác động.

~~~text
Expected annual incident loss (illustrative)
  = probability of scenario per year
    * business impact if scenario occurs
~~~

Ví dụ giả định:

- Một sự cố region kéo dài có xác suất ước tính 2%/năm.
- Nếu xảy ra, tổng tác động nghiệp vụ ước tính 500.000 đơn vị tiền tệ.
- Expected annual loss tương ứng là 10.000 đơn vị tiền tệ/năm.

Đây chỉ là ví dụ về phương pháp tính, **không phải xác suất thực hoặc báo giá của Google Cloud**. Nếu phương án multi-region cần chi phí thêm lớn hơn expected loss, vẫn có thể đáng chọn vì compliance, thiệt hại uy tín, tail risk hoặc yêu cầu RTO bắt buộc. Ngược lại, expected loss thấp không biện minh cho bỏ qua các kiểm soát bảo mật nền tảng.

### Khi không biết xác suất

Đừng tự đặt một con số rồi coi là chính xác. Có thể dùng ba kịch bản:

- **Optimistic:** ít sự cố, giá tài nguyên thấp, traffic đúng dự đoán.
- **Base case:** dựa trên số liệu hiện có và forecast trung vị.
- **Stress case:** peak traffic, một dependency lỗi và chi phí failover tăng.

Ghi nguồn giả định và làm sensitivity analysis. Với rủi ro hiếm nhưng tác động rất lớn, cần xem xét business impact analysis thay vì chỉ lấy trung bình.

### Risk register

| ID | Rủi ro | Khả năng | Tác động | Kiểm soát hiện tại | Hành động/owner |
|---|---|---|---|---|---|
| R1 | Deploy cấu hình IAM sai | Chưa rõ | API mất quyền DB | Peer review | Thêm policy validation, platform team |
| R2 | DB failover vượt RTO | Chưa đo | Lỗi giao dịch | HA, monitoring | Diễn tập failover, SRE |
| R3 | Đột biến traffic tăng hóa đơn | Phụ thuộc campaign | Budget vượt | Max instances | Cost forecast + alert, FinOps |
| R4 | Secret lộ trong log | Chưa đo | Vi phạm bảo mật | Log redaction | Test không lộ secret, security |
| R5 | Replica liên vùng không theo kịp | Chưa đo | RPO không đạt | Replication monitoring | Đo lag và thử failover, DB owner |

Không ghi “Đã giảm thiểu” chỉ vì đã tạo ticket. Hành động chỉ hoàn tất sau khi có bằng chứng: test, metrics, policy được áp dụng hoặc diễn tập phục hồi.

## 17. Kiểm chứng trade-off bằng thử nghiệm thay vì giả định

Một quyết định kiến trúc quan trọng nên có **test plan** tương ứng với mục tiêu.

### Kiểm thử bảo mật

- Review IAM và service accounts theo least privilege.
- Thử truy cập secret ngoài phạm vi được cấp, xác nhận bị từ chối.
- Kiểm tra endpoint chưa xác thực không thể gọi API nội bộ.
- Kiểm tra image và dependency scan trong CI.
- Thử đánh giá egress bằng workload test không chứa dữ liệu nhạy cảm.
- Xác nhận audit logs có sự kiện cần thiết và retention đúng chính sách.

### Kiểm thử độ tin cậy

- Load test với traffic base, peak và đột biến.
- Diễn tập restart/rollout để đo tác động đến request.
- Mô phỏng dependency timeout và xác minh retry/circuit breaker.
- Diễn tập failover của database trong môi trường được phê duyệt.
- Khôi phục từ backup thử và xác minh dữ liệu nghiệp vụ.
- Kiểm tra retry không tạo đơn hàng hoặc thanh toán trùng.
- Xác nhận alert đến đúng người và runbook đủ để khôi phục.

### Kiểm thử chi phí

- Gắn owner và resource labels vào hạ tầng test.
- Bật budget alert, giám sát số resource khi load test.
- Chạy test trong khoảng ngắn, có deadline và cleanup.
- Đo lượng CPU/memory, egress, storage, log và DB requests.
- Đối chiếu dashboard chi phí với dữ liệu từ Billing export và thời gian đo.
- Mở rộng kết quả theo profile traffic có cơ sở, lưu giả định.

**An toàn khi thực hành:** không tự chạy chaos engineering trên production khi chưa có phạm vi, bảo vệ và phê duyệt vận hành. Với environment thử, đặt quota/max instances/deadline và kế hoạch dừng để tránh tăng chi phí ngoài dự kiến.

### Chứng minh bằng tiêu chí trước/sau

| Mục tiêu | Dữ liệu trước | Thay đổi | Tiêu chí sau |
|---|---|---|---|
| Giảm cold start | P95 latency khi idle rồi có request | Tăng min instances có kiểm soát | P95 đạt SLO, chi phí trong ngân sách |
| Giảm quyền runtime | Service account có quyền project rộng | Tách IAM theo secret/database | Test chức năng pass, denied request ngoài scope |
| Chịu lỗi zone | Một điểm lỗi tại node/zone | Bố trí replicas/HA phù hợp | Diễn tập zone failure đạt RTO |
| Giảm log cost | Log ingestion cao | Sampling/loại log không cần | Không mất audit/security events bắt buộc |
| Giảm failed orders | Timeout và duplicate | Idempotency + bounded retry | Duplicate rate giảm, latency đạt SLO |

## 18. Vận hành quyết định: dashboard, alert và quy trình thay đổi

Sau khi chọn kiến trúc, nhóm cần một dashboard theo dõi **cả ba mục tiêu**:

| Góc nhìn | Chỉ số nên theo dõi | Cách dùng |
|---|---|---|
| Security | Denied access, auth failure, secret access bất thường, image scan findings | Phát hiện dấu hiệu vượt quyền hoặc thay đổi trái phép |
| Reliability | Good request ratio, P95/P99 latency, error budget burn, queue age, DB failover | Phát hiện tác động người dùng và dependency |
| Cost | Chi phí theo project/service, runtime utilization, network egress, unit cost/order | So với budget và tìm tối ưu an toàn |
| Delivery | Deploy frequency, rollback, change failure rate, time to restore | Kiểm tra rủi ro phát hành và khả năng hồi phục |

Đừng tạo alert cho mọi metric. Alert nên chỉ ra tình trạng cần hành động, có severity và owner. Ví dụ:

- Error budget burn nhanh và liên tục → xem xét giảm traffic hoặc rollback.
- Quyền Secret Manager bị thay đổi bất thường → điều tra theo runbook bảo mật.
- Cost vượt forecast do số instance tăng nhanh → kiểm tra traffic bất thường, abuse hoặc retry storm.
- Database replication lag vượt ngưỡng RPO → dừng các thao tác DR phụ thuộc dữ liệu chưa đồng bộ.

Một alert chi phí không nên tự động dừng production theo cách có thể gây outage lớn hơn mức tiết kiệm. Nếu tổ chức muốn tự động hạn chế tài nguyên, cần thiết kế policy rõ phạm vi, exception và phê duyệt vì budget alerts vốn không phải cơ chế cắt chi phí cứng.

## 19. Một số kiểm soát nâng cao và tác động chéo

### VPC Service Controls không thay thế IAM

VPC Service Controls có thể giúp xây dựng service perimeter để giảm một số đường rò rỉ dữ liệu khi truy cập các dịch vụ được hỗ trợ. Đây là lớp bảo vệ bổ sung cho IAM, không phải thay thế xác thực, authorization trong ứng dụng hoặc bảo vệ dữ liệu ở các dịch vụ không được bao phủ.

Khi đề xuất service perimeter:

1. Xác định dữ liệu, API và project thuộc phạm vi bảo vệ.
2. Kiểm tra các dịch vụ và đường truy cập có được hỗ trợ không.
3. Lập danh sách CI/CD, nhà phát triển, service account, backup/export và hệ thống giám sát cần quyền truy cập.
4. Dùng chế độ dry-run và xem audit logs/violation logs trước khi enforcement.
5. Áp dụng policy theo giai đoạn và có rollback plan.

**Trade-off:** perimeter phù hợp giúp giảm một số rủi ro exfiltration, nhưng một policy sai có thể chặn pipeline, export hoặc ứng dụng production. Cần theo dõi tác động đến độ tin cậy và khả năng vận hành trước khi bật chính sách chặn.

### Observability: giảm lưu lượng log mà không mất khả năng điều tra

Giảm log verbosity có thể tiết kiệm chi phí, nhưng một sự cố bảo mật hoặc production không thể được phân tích nếu thiếu dấu vết. Nên:

- Giữ các loại audit log bắt buộc và security events theo yêu cầu.
- Không log secret, token, raw credentials, dữ liệu cá nhân không cần thiết.
- Dùng structured logs chứa correlation ID, service, version, severity và mã lỗi.
- Cân nhắc sampling cho request logs có volume lớn; giữ dữ liệu lỗi và sự kiện quan trọng ở mức đủ điều tra.
- Đặt retention theo phân loại dữ liệu; xác định nguồn cần archive dài hạn.
- Đo lại log ingestion sau khi thay đổi, đồng thời kiểm tra runbook điều tra vẫn hoạt động.

Không dùng cách “tắt toàn bộ logs” như một chiến lược cost optimization. Chi phí của việc không thể phát hiện hoặc chứng minh một sự cố có thể lớn hơn chi phí lưu log cần thiết.

### Quota và giới hạn chi tiêu

Quota và giới hạn số instance có thể giảm tác động của lỗi retry storm hoặc abuse và giúp dự đoán chi phí. Nhưng chúng có thể khiến request bị từ chối khi lưu lượng hợp lệ tăng. Cần cân bằng:

- Quota để ngăn workload tạo tài nguyên vượt kế hoạch.
- Max instances hoặc concurrency để giới hạn kết nối downstream.
- Autoscaling đủ nhanh và có headroom cho peak hợp lệ.
- Cost forecast, cảnh báo ngân sách và action plan khi chi phí bất thường.
- Thỏa thuận trước tình huống nào ưu tiên giữ availability, tình huống nào chấp nhận throttling.

Một hệ thống thanh toán với SLO khắt khe có thể ưu tiên tránh outage hơn việc tự động tắt service khi có cảnh báo ngân sách. Mặt khác, một môi trường thử nghiệm có thể áp dụng mức giới hạn thấp và TTL nghiêm ngặt. **Chính sách chi phí phải phụ thuộc criticality của workload.**

## 20. Ghi quyết định bằng Architecture Decision Record

ADR làm rõ vì sao nhóm chọn một phương án, ai chấp nhận rủi ro còn lại và điều kiện nào khiến quyết định phải đánh giá lại. ADR không chỉ là biên bản họp: nó cần dữ liệu và đường dẫn đến bằng chứng.

### Mẫu ADR

~~~markdown
# ADR-012: Chọn kiến trúc cho Orders API

## Bối cảnh
- Owner nghiệp vụ:
- Owner kỹ thuật:
- Mức độ quan trọng:
- Workload và dependency:
- Data classification:
- Traffic base/peak:
- SLO và định nghĩa SLI:
- RTO/RPO:
- Chi phí trần và kỳ đánh giá:

## Ràng buộc bắt buộc
- Data residency:
- Authentication / authorization:
- Encryption / key ownership:
- Audit, retention, backup:
- Thời hạn khôi phục:

## Phương án
- A: Cloud Run single-region + Cloud SQL HA
- B: Cloud Run multi-region + data DR phù hợp
- C: GKE regional + Cloud SQL HA

## Bằng chứng so sánh
| Tiêu chí | A | B | C | Nguồn dữ liệu |
|---|---|---|---|---|
| Security guardrails | | | | |
| Load test / P95 | | | | |
| RTO drill | | | | |
| RPO observation | | | | |
| Monthly TCO range | | | | |
| Operational effort | | | | |

## Quyết định
- Phương án chọn:
- Lý do:
- Phương án bị loại:
- Các giả định chưa được xác minh:

## Rủi ro và biện pháp
| Risk | Mitigation | Owner | Verification | Due date |
|---|---|---|---|---|
| | | | | |

## Rollout và rollback
- Thử nghiệm staging:
- Canary:
- Smoke test:
- Điều kiện rollback:
- Database migration compatibility:

## Đánh giá lại
- Mốc thời gian:
- Điều kiện kích hoạt: SLO burn, traffic x3, budget breach,
  yêu cầu compliance đổi hoặc incident quan trọng
~~~

Không đưa credential, dữ liệu khách hàng hay quy tắc bảo mật nhạy cảm vào ADR chia sẻ rộng. Với tài liệu chứa chi tiết nhạy cảm, giữ liên kết tới nơi lưu có quyền truy cập phù hợp.

## 21. Bài tập thực hành: quyết định dưới ràng buộc và ngân sách

Giả sử nhóm vận hành một API Spring Boot dùng Cloud SQL và Pub/Sub. Hiện tại có một Cloud Run deployment trong một region. Doanh nghiệp muốn cải thiện availability, nhưng ngân sách tăng thêm có giới hạn.

### Phần A — Thu thập yêu cầu

1. Xác định ai sử dụng API, giờ cao điểm và tác động của một giờ outage.
2. Viết ít nhất hai SLI: request success và tỷ lệ đơn hàng hoàn thành đúng thời gian.
3. Đề xuất SLO, RTO, RPO có căn cứ nghiệp vụ.
4. Phân loại dữ liệu: public, internal, confidential và secret theo chính sách áp dụng.
5. Ghi các guardrail: nơi được lưu dữ liệu, quyền IAM, encryption, audit và retention.
6. Xác định budget ceiling, baseline chi phí hiện tại và owner chấp nhận chi phí.

### Phần B — Thiết kế phương án

So sánh ít nhất ba phương án:

- A: Cloud Run + Cloud SQL theo cấu hình hiện tại, tối ưu canary, backup, monitoring.
- B: Cloud Run + Cloud SQL HA trong region, thêm fault isolation và backup/PITR.
- C: Thêm phương án multi-region phù hợp với yêu cầu dữ liệu và khả năng vận hành.

Nếu cần, bổ sung GKE hoặc Compute Engine như ứng viên và giải thích yêu cầu nào biện minh cho phần vận hành tăng thêm.

Với mỗi phương án, ghi:

1. Sơ đồ component và trust boundary.
2. Danh sách failure mode và single points of failure.
3. IAM/service identities, ingress/egress và secret management.
4. Chiến lược HA, backup, restore, failover, schema migration.
5. Dự toán chi phí tối thiểu/base/peak; phần chưa có số liệu.
6. Kiểm thử cần thực hiện trước khi production.

### Phần C — Chấm điểm và đánh giá độ nhạy

1. Loại phương án không đạt guardrail.
2. Xác định những phương án bị dominated.
3. Chấm các tiêu chí còn lại với trọng số được stakeholder đồng thuận.
4. Thử thay đổi trọng số security, reliability và cost.
5. Xem phương án được chọn có đổi trong stress case không.
6. Ghi rủi ro còn lại và người chịu trách nhiệm.

### Phần D — Kiểm chứng thực nghiệm

Trong project và môi trường thử nghiệm được phê duyệt:

1. Chạy load test với base traffic và peak traffic giới hạn.
2. Đo P95 latency, error rate, database connections và số instance.
3. Thực hiện smoke test sau canary release.
4. Mô phỏng một dependency timeout, quan sát retry và error budget.
5. Diễn tập restore hoặc failover theo runbook được chuẩn bị.
6. Đối chiếu chi phí test với mô hình dự toán.
7. Hoàn thiện ADR cùng quyết định và điều kiện đánh giá lại.

**Không thực hiện thao tác phá hủy hoặc ép failover trên production ngoài quy trình vận hành đã được phê duyệt.** Các bước tạo tài nguyên test cần owner, quota/giới hạn và cleanup.

### Tiêu chí chấm bài

| Yêu cầu | Đạt khi |
|---|---|
| Guardrails rõ ràng | Có danh sách pass/fail và owner |
| Reliability định lượng | SLI/SLO/RTO/RPO có định nghĩa và bằng chứng |
| Bảo mật theo luồng dữ liệu | Xác định IAM, trust boundary, secret, audit |
| Chi phí đầy đủ | Có network, storage, backup, observability, operations |
| Chọn phương án | Có trade-offs và sensitivity analysis |
| Hành động tiếp theo | Có test plan, owner, deadline và ADR |

## 22. Checklist trước khi chấp thuận kiến trúc

- [ ] Đã ghi mục tiêu nghiệp vụ và mức độ quan trọng của workload.
- [ ] Đã xác định ràng buộc bắt buộc về compliance, residency, security và ngân sách.
- [ ] Đã phân biệt hard gates với tiêu chí có thể đánh đổi.
- [ ] Đã có threat model và trust boundary của dữ liệu.
- [ ] Đã thiết kế least privilege cho build, deploy và runtime identities.
- [ ] Đã xem xét network ingress/egress, firewall, VPC và dữ liệu trên đường truyền.
- [ ] Đã quyết định secret/key lifecycle và phục hồi khi key không sẵn sàng.
- [ ] Đã xác định SLI, SLO và cách tính error budget đúng.
- [ ] Đã xác định RTO, RPO và kịch bản lỗi tương ứng.
- [ ] Đã xét common-mode failures, không chỉ số lượng replica.
- [ ] Đã chọn HA, backup, PITR và DR đúng mục tiêu, có diễn tập.
- [ ] Đã đánh giá retry, idempotency, timeout, circuit breaker và queue.
- [ ] Đã tính database connection limits và downstream quotas khi autoscaling.
- [ ] Đã kiểm tra consistency/replication khi triển khai đa region.
- [ ] Đã ước tính TCO gồm compute, storage, network, backup, telemetry, operations.
- [ ] Đã có cost allocation, budget alerts và owner theo dõi chi phí.
- [ ] Đã chạy load/security/failover test phù hợp trong môi trường an toàn.
- [ ] Đã kiểm tra điều kiện rollout và rollback của ứng dụng/dữ liệu.
- [ ] Đã ghi lại giả định, độ chắc chắn, rủi ro còn lại và sensitivity.
- [ ] Đã có ADR, lịch đánh giá lại và người phê duyệt.

## Câu hỏi tự kiểm tra

**1. Vì sao không nên dùng một bảng điểm duy nhất để chọn kiến trúc?**

Vì một điểm cao có thể che lấp việc vi phạm ràng buộc bắt buộc. Trước tiên phải áp dụng hard gates, sau đó mới so sánh các phương án hợp lệ bằng điểm số và bằng chứng.

**2. SLI theo request 99,9% khác thế nào với uptime 99,9%?**

SLI theo request đếm tỷ lệ request hợp lệ thành công; uptime theo thời gian đo thời lượng hệ thống đáp ứng điều kiện available. Không chuyển đổi giữa hai cách đo khi chưa định nghĩa rõ.

**3. Vì sao thêm replica API không bảo đảm đạt RPO?**

RPO phụ thuộc dữ liệu, replication, backup và thời điểm khôi phục. Replica API xử lý compute, không tự sao lưu database.

**4. CMEK có tạo rủi ro reliability không?**

Có thể. Quyền truy cập key, trạng thái key hoặc key location sai có thể khiến dịch vụ không đọc/ghi dữ liệu được. Vì vậy cần cả quyền kiểm soát và runbook/monitoring cho key.

**5. Vì sao giảm minimum instances cần kiểm tra SLO?**

Vì có thể tăng cold start và latency cho request sau thời gian idle. Chỉ giảm khi độ trễ thực tế vẫn nằm trong mục tiêu.

**6. Khi nào đa region có thể không đáng đầu tư?**

Khi tác động của region outage chấp nhận được theo RTO/RPO, chi phí và độ phức tạp multi-region vượt lợi ích, hoặc giải pháp dữ liệu chưa bảo đảm consistency. Phải dựa trên yêu cầu và thử nghiệm, không phải quy tắc tuyệt đối.

**7. Dùng budget alert có tự chặn chi tiêu không?**

Thông thường không. Budget alert chủ yếu thông báo theo ngưỡng; các cơ chế spend control hoặc tự động hóa phải được thiết kế riêng và đánh giá tác động đến availability.

**8. Vì sao retry có thể làm outage nghiêm trọng hơn?**

Nếu nhiều client retry đồng thời hoặc retry vô hạn, dependency đã quá tải nhận thêm request, làm kéo dài sự cố. Cần backoff, jitter, timeout, giới hạn và idempotency.

**9. Điều gì phân biệt TCO và giá một instance?**

TCO còn tính database, network, storage, telemetry, bảo mật, non-production và công sức vận hành trong vòng đời hệ thống.

**10. Khi nào cần đánh giá lại ADR?**

Khi traffic, SLO, quy định, năng lực đội ngũ hoặc chi phí thay đổi đáng kể; sau một incident quan trọng; hoặc đến mốc review đã ghi trong quyết định.

## Tài liệu tham khảo

- [Google Cloud Well-Architected Framework](https://docs.cloud.google.com/architecture/framework)
- [Security, privacy, and compliance pillar](https://docs.cloud.google.com/architecture/framework/security)
- [Reliability pillar](https://docs.cloud.google.com/architecture/framework/reliability)
- [Cost optimization pillar](https://docs.cloud.google.com/architecture/framework/cost-optimization)
- [Google Cloud Disaster Recovery Planning Guide](https://docs.cloud.google.com/architecture/dr-scenarios-planning-guide)
- [Cloud SQL high availability for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres/high-availability)
- [Cloud SQL cross-region replicas](https://docs.cloud.google.com/sql/docs/postgres/replication/cross-region-replicas)
- [Cloud Run minimum instances](https://docs.cloud.google.com/run/docs/configuring/min-instances)
- [Cloud Run multi-region](https://docs.cloud.google.com/run/docs/multiple-regions)
- [Cloud KMS customer-managed encryption keys](https://docs.cloud.google.com/kms/docs/cmek)
- [VPC Service Controls overview](https://docs.cloud.google.com/vpc-service-controls/docs/overview)
- [Cloud Logging routing overview](https://docs.cloud.google.com/logging/docs/routing/overview)
- [Cloud Billing budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)
- [Google SRE Book: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)

## Kết luận

Đánh giá trade-offs về **bảo mật, độ tin cậy và chi phí** là một quy trình ra quyết định liên tục. Bảo mật xác định các ranh giới và kiểm soát không được bỏ qua; độ tin cậy được đo bằng SLI, SLO, error budget, RTO và RPO; chi phí phản ánh toàn bộ vòng đời hạ tầng, dữ liệu, network, observability và vận hành. Những mục tiêu này ảnh hưởng lẫn nhau: CMEK tạo thêm phụ thuộc key, đa region tạo thêm replication và routing, autoscaling tác động lên database, còn tối ưu log hoặc resource có thể làm thay đổi khả năng phát hiện và khôi phục sự cố.

Một quyết định tốt không phải phương án thắng mọi ô trong bảng, mà là phương án **đáp ứng các guardrail bắt buộc, có bằng chứng về trade-offs, có thể vận hành trong ngân sách và có kế hoạch kiểm chứng rủi ro còn lại**. Hãy đo trước và sau, ghi ADR, phân công owner và chủ động đánh giá lại khi yêu cầu nghiệp vụ thay đổi.
