# Failover, failback và chuyển lưu lượng giữa các region

Một kiến trúc đa region không tự động trở thành hệ thống phục hồi thảm họa. Hai region có thể đều có máy chủ và dịch vụ chạy tốt nhưng ứng dụng vẫn ngừng phục vụ khi database chỉ cho phép ghi tại region bị sự cố, DNS trỏ tới địa chỉ cũ hoặc hệ thống xác thực không hoạt động ở nơi dự phòng. Để duy trì dịch vụ khi một vùng triển khai gặp vấn đề, nhóm vận hành phải phối hợp **chuyển lưu lượng**, **chuyển vai trò dữ liệu**, **đảm bảo tính nhất quán** và **khôi phục trạng thái bình thường**.

Trong Google Cloud, giải pháp có thể kết hợp Cloud Load Balancing, Cloud DNS, Cloud Run, GKE, Compute Engine, Cloud SQL, Spanner, Cloud Storage và các dịch vụ tích hợp dữ liệu. Bài học này tập trung vào quyết định kiến trúc và runbook có thể kiểm chứng: khi nào cần failover, làm sao đưa traffic sang region dự phòng, khi nào được mở ghi dữ liệu, cách failback an toàn và cách diễn tập để đáp ứng RTO/RPO. Không có một lệnh gcloud chung nào thực hiện đầy đủ quá trình này cho mọi dịch vụ.

## 1. Phân biệt failover, failback và traffic shifting

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Failover | Chuyển dịch vụ sang thành phần hoặc region dự phòng khi region chính không thể phục vụ theo mục tiêu | Dừng ghi tại region A, kích hoạt writer ở B và chuyển request sang B |
| Failback | Chuyển dịch vụ về region ban đầu sau khi sửa sự cố, đồng bộ dữ liệu và xác minh năng lực | Sao chép các thay đổi hợp lệ từ B về A rồi chuyển quyền ghi và traffic theo kế hoạch |
| Traffic shifting | Thay đổi tỷ lệ hoặc đích nhận request mà không nhất thiết có sự cố | Chuyển 5%, 25%, 100% traffic sang region B để kiểm chứng |
| Disaster recovery (DR) | Tập hợp phương án phục hồi ứng dụng, dữ liệu và phụ thuộc khi xảy ra gián đoạn nghiêm trọng | Runbook vận hành, cơ chế sao lưu, khôi phục và kiểm chứng |
| High availability (HA) | Giảm gián đoạn từ lỗi thành phần hoặc miền lỗi trong điều kiện thiết kế | Nhiều instance/zone, health checks và tự động thay thế |

Failover không đồng nghĩa dữ liệu đã được phục hồi chính xác. Traffic shifting thành công không có nghĩa tất cả giao dịch ghi đã an toàn. Failback cũng không chỉ là đặt lại tỷ lệ traffic: sau một thời gian chạy tại B, B có thể chứa những ghi mới mà A chưa có.

Phân biệt **failover của tầng ứng dụng** với **failover của tầng dữ liệu**. Có thể hướng request đọc sang B khi B đã sẵn sàng, nhưng không được mở ghi ở B trước khi xử lý rõ writer cũ, trạng thái replication và quyền sở hữu dữ liệu.

## 2. Đặt mục tiêu RTO, RPO và SLO

Hai chỉ tiêu nền tảng:

- **Recovery Time Objective (RTO):** thời gian gián đoạn tối đa mà doanh nghiệp đặt mục tiêu chấp nhận để khôi phục dịch vụ sau sự cố.
- **Recovery Point Objective (RPO):** mức mất dữ liệu tối đa chấp nhận được, biểu diễn bằng độ lệch thời điểm giữa dữ liệu được phục hồi và trạng thái trước sự cố.

Ví dụ, hệ thống đơn hàng có RTO 15 phút và RPO 5 phút. Nhóm cần thiết kế sao cho có thể khôi phục chức năng quan trọng trong khoảng thời gian mục tiêu và không mất quá lượng dữ liệu tương ứng 5 phút trong kịch bản đã chọn. Đây là yêu cầu thiết kế, không phải cam kết rằng mọi loại sự cố đều tự đáp ứng mục tiêu.

Một cách phân tích RTO:

\[
\text{Tổng thời gian phục hồi} \approx
\text{Phát hiện} +
\text{Ra quyết định} +
\text{Khôi phục dữ liệu} +
\text{Chuyển lưu lượng} +
\text{Xác minh}
\]

Nếu phát hiện mất 8 phút và quy trình phê duyệt mất 10 phút, không thể đạt RTO 15 phút dù thao tác chuyển traffic chỉ mất 30 giây. Hãy đo từng giai đoạn bằng diễn tập thực tế và báo cáo p50/p95 nếu có đủ mẫu.

RPO phụ thuộc chiến lược sao chép và ngữ nghĩa ghi. Asynchronous replication có thể có độ trễ; phiên ghi vừa được xác nhận ở A có thể chưa tới B khi A ngừng hoạt động. Với một số dịch vụ đa region có strong consistency và failover do nhà cung cấp quản lý, cách xác định RPO sẽ khác. Phải áp dụng mục tiêu theo **mỗi hệ thống dữ liệu**, không suy ra từ việc cả hai region đều có tài nguyên.

SLO của hành trình người dùng vẫn quan trọng: API có thể trả HTTP 200 sau failover nhưng đọc dữ liệu sai hoặc gây trùng giao dịch. SLI nên bao gồm tính đúng đắn, khả dụng, latency và trạng thái backlog tùy nghiệp vụ.

## 3. Chọn mô hình active-passive hoặc active-active

| Mô hình | Cách hoạt động | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Cold standby | Region B có định nghĩa hạ tầng, cần tạo phần lớn resource khi có sự cố | Chi phí duy trì thấp | RTO dài, khôi phục phụ thuộc provisioning |
| Warm standby | Region B có hạ tầng/dịch vụ cơ bản, dữ liệu được sao chép, nhận rất ít hoặc không nhận traffic | Cân bằng chi phí và RTO | Cần scale B trước khi nhận tải đầy đủ |
| Hot standby / active-passive | Region B đã sẵn sàng phục vụ, A nhận phần lớn traffic; B được giữ đồng bộ | Chuyển tương đối nhanh nếu dữ liệu sẵn sàng | Chi phí duy trì cao, cần chống split-brain |
| Active-active | Hai region cùng phục vụ một phần traffic | Tận dụng công suất, giảm phụ thuộc vào một region | Khó nhất ở dữ liệu ghi, phiên người dùng và xung đột |

Không nên gọi một hệ thống active-active chỉ vì frontend đặt ở hai region. Nếu mọi request cuối cùng đều ghi vào một database writer tại A, A vẫn có thể là điểm lỗi ảnh hưởng toàn bộ chức năng ghi. Có thể thiết kế frontend active-active, nhưng database vẫn active-passive; runbook phải thể hiện chính xác điều đó.

Lựa chọn cần dựa trên tính sẵn sàng của dependency, khả năng chịu lỗi và chi phí. Một ứng dụng đọc dữ liệu công khai có thể chuyển traffic rất linh hoạt; ứng dụng thanh toán yêu cầu giao dịch chính xác có thể cần failover có phê duyệt và kiểm chứng dữ liệu trước khi cho phép ghi.

## 4. Vẽ dependency map trước khi chọn đường chuyển

Hãy lập bản đồ từ request người dùng đến mọi thành phần cần thiết:

~~~mermaid
flowchart LR
  U["Người dùng"] --> E["DNS / Global edge"]
  E --> A["Region A: Cloud Run hoặc GKE"]
  E --> B["Region B: Cloud Run hoặc GKE"]
  A --> DA["Database writer A"]
  B --> DB["Replica hoặc writer dự phòng B"]
  DA -. "Sao chép theo khả năng dịch vụ" .-> DB
  A --> Q["Pub/Sub / xử lý sự kiện"]
  B --> Q
  A --> S["Secrets, IAM, APIs phụ trợ"]
  B --> S
  S --> X["Dịch vụ bên ngoài / on-prem"]
~~~

Cần xác định từng dependency có khả dụng tại B không:

| Phụ thuộc | Câu hỏi cần trả lời trước failover |
| --- | --- |
| Artifact và runtime | Image/digest, quyền pull, cấu hình Cloud Run/GKE ở B có sẵn không? |
| Database | B có bản sao hợp lệ không, replication lag bao nhiêu, ai là writer? |
| Object storage | Bucket/dữ liệu có thể đọc được từ B không, cơ chế sao chép và RPO cụ thể là gì? |
| Secret/KMS | Workload identity ở B có quyền dùng secret/key và chúng có khả dụng đúng vùng không? |
| Hàng đợi/sự kiện | Consumer B có thể tiếp tục mà không xử lý trùng hoặc bỏ sót không? |
| DNS/ingress | Route, chứng chỉ TLS, firewall, WAF, authentication và health signal ở B có hoạt động không? |
| Kết nối riêng | VPN/Interconnect/PSC hoặc endpoint on-prem có sẵn route đi và về từ B không? |
| Dịch vụ ngoài | Callback URL, allowlist IP, quota và khóa API có chấp nhận region B không? |

Nếu B không có dữ liệu quan trọng hoặc không truy cập được hệ thống thanh toán bên thứ ba, chuyển 100% HTTP traffic sang B có thể chỉ biến lỗi hạ tầng thành lỗi nghiệp vụ.

## 5. Kiến trúc tham chiếu hai region trên Google Cloud

Giả sử dịch vụ chạy ở hai region giả định A và B, dùng cùng phiên bản container và chính sách bảo mật; tầng dữ liệu có cơ chế dự phòng tương ứng. Một cơ chế điều khiển traffic chung ở trước hai endpoint quyết định request mới đi đâu.

~~~mermaid
flowchart TD
  C["Client / API caller"] --> LB["Global Load Balancing hoặc DNS steering"]
  LB -->|"Bình thường"| RA["Region A - ứng dụng"]
  LB -->|"Dự phòng / chia tải"| RB["Region B - ứng dụng"]
  RA --> WA["Nguồn dữ liệu ghi chủ động"]
  RB --> WB["Nguồn dữ liệu ở B"]
  WA -. "Replication có giới hạn RPO" .-> WB
  CT["DR coordinator + runbook"] --> G["Gate: health, capacity, data readiness"]
  G --> LB
  G --> WA
  G --> WB
  OBS["Monitoring, Logging, Audit"] --> CT
  RA --> OBS
  RB --> OBS
~~~

Sơ đồ chỉ biểu diễn quyết định kiến trúc, không phải một cấu hình API cụ thể. Đường replication, quyền write và cách tải được chuyển khác nhau theo loại database. Không kết nối hai database để cả hai cùng nhận ghi nếu sản phẩm hoặc tầng ứng dụng không hỗ trợ multi-writer với cơ chế giải quyết xung đột.

Một thiết kế thực tế phải chỉ rõ tình huống nào load balancer tự động chuyển theo health, tình huống nào cần người phê duyệt và tình huống nào bị chặn do dữ liệu chưa sẵn sàng.

## 6. Traffic shifting với global load balancing

Global external Application Load Balancer có thể đưa một địa chỉ/điểm vào toàn cầu trước các backend tại nhiều region, với lựa chọn backend và chính sách định tuyến tùy cấu hình. Với backend hỗ trợ health check, tín hiệu sức khỏe và capacity có thể tham gia quyết định chọn backend. Một số tính năng như weighted routing, route rules hoặc failover behavior phụ thuộc loại load balancer và backend.

Đối với Compute Engine và một số loại GKE backend, health checks của load balancer có thể cung cấp tín hiệu để chuyển traffic khỏi endpoint lỗi. Nhưng cần hiểu rõ ranh giới:

- Health check chỉ xác nhận điều kiện đã cấu hình, không tự bảo đảm dữ liệu/đơn hàng được xử lý chính xác.
- Session đang xử lý có thể bị gián đoạn; không phải mọi kết nối hiện tại được chuyển liền mạch.
- Chuyển traffic vẫn chịu giới hạn propagation, draining, caching và năng lực backend.
- Nếu health check chỉ đọc endpoint đơn giản, service vẫn có thể trả khỏe dù database writer đã chết.

**Lưu ý riêng cho Cloud Run:** khi kết nối qua serverless network endpoint group (serverless NEG), không được giả định cơ chế health check và failover chuẩn của VM/instance group áp dụng giống hệt. Khả năng traffic management và đánh giá lỗi của serverless backend phụ thuộc loại load balancer và tính năng được hỗ trợ. Phải kiểm tra hành vi thực tế khi B hỏng ứng dụng, không chỉ khi B trả lời HTTP 200 cho một endpoint.

Để canary hoặc chuyển có kế hoạch, có thể đặt chính sách định tuyến chọn vùng hoặc chia tỷ trọng khi cấu hình backend hỗ trợ. Không đồng nhất **Cloud Run revision traffic splitting** với **chuyển region**: revision splitting trong một dịch vụ chỉ xử lý các revision của dịch vụ đó; điều phối giữa các region cần tầng trước hoặc quy trình phù hợp.

## 7. Chuyển lưu lượng bằng DNS: lợi ích và giới hạn

Một lựa chọn khác là dùng DNS để thay đổi IP hoặc endpoint mà client nhận được. Cloud DNS hỗ trợ các loại record và routing policy theo phạm vi sản phẩm, nhưng thiết kế failover phải xét loại record, TTL, cơ chế health và hành vi resolver thực tế.

| Điểm cần xét | Hệ quả |
| --- | --- |
| TTL và caching | Client/resolver có thể tiếp tục dùng câu trả lời cũ sau khi thay đổi |
| Keep-alive và connection pool | Kết nối hiện có không bị di chuyển chỉ vì DNS trả IP mới |
| DNS propagation | Không có bảo đảm mọi client thấy cập nhật cùng một thời điểm |
| Health-aware policy | Chỉ dùng khi loại policy/record và phương án health được hỗ trợ |
| Private DNS | Phải xét resolver, forwarding, inbound/peering và các VPC được ủy quyền |
| DNSSEC/TLS/cert | Chuyển đích không được làm hỏng validation hoặc endpoint identity |

Giảm TTL trước một cuộc chuyển đổi có kế hoạch có thể giúp giảm độ trễ do cache, nhưng không bảo đảm mọi client tuân thủ TTL. Không thể giảm TTL vào đúng lúc sự cố rồi kỳ vọng toàn bộ cache cũ hết hạn tức thì.

Đối với API giao dịch cần RTO ngắn, thường nên xem xét một entrypoint ổn định ở tầng load balancer và chỉ dùng DNS làm phần định danh/khám phá tên. DNS steering có thể phù hợp với từng kịch bản nhưng phải diễn tập và chấp nhận độ trễ đổi đích. Cần đo **thời gian client thực sự chuyển thành công**, không chỉ thời điểm Cloud DNS API nhận bản ghi mới.

## 8. Chuyển traffic ở GKE, Cloud Run và Compute Engine

### GKE

Trong GKE, có thể dùng backend được hỗ trợ bởi Cloud Load Balancing, Gateway hoặc kiến trúc multi-cluster được hỗ trợ để định tuyến qua các cluster/region. Để chuyển thành công, B phải có node capacity, Pod Ready, ingress policy, chứng chỉ và kết nối data layer phù hợp.

Khi tăng traffic về B, quan sát:

- Desired/available replicas, readiness, pod startup và HPA.
- Scheduling/node autoscaler, CPU/memory và connection pools.
- Ingress upstream errors, TLS, timeout và 5xx.
- Khả năng B vẫn chạy nếu control plane hoặc hạ tầng của A không truy cập được.

Không coi Pod Ready là đủ để mở write nếu database chưa sẵn sàng. Một endpoint kiểm tra sẵn sàng phục vụ request nên phân biệt readiness của frontend với readiness của dependency ghi và trạng thái vận hành DR.

### Cloud Run

Mỗi service triển khai trong một region có endpoint và cấu hình riêng. B phải có image, environment variables, IAM, secret access, CPU/memory, concurrency và max instances phù hợp. Có thể dùng cơ chế định tuyến phía trước để phân phối request đến các service ở các region khác nhau.

Một service ở B đang chạy nhưng max instances quá thấp, giới hạn kết nối dữ liệu thiếu hoặc chưa có quyền đọc secret sẽ không thay thế được A ở tải production. Sau khi chuyển, cần xem latency, tỷ lệ lỗi và tốc độ autoscaling, thay vì chỉ kiểm tra một lần gọi thành công.

### Compute Engine

Với VM hoặc managed instance groups ở nhiều region, cần xác định image/template, health checks, autoscaling, state không lưu cục bộ, startup script và cách backend của load balancer phân phối traffic. Phải kiểm tra các loại backend hỗ trợ chính sách failover dự kiến; không sao chép nguyên mẫu cấu hình regional load balancer sang global load balancer mà chưa xét semantics.

## 9. Tín hiệu nào được phép kích hoạt failover?

Không nên kích hoạt chuyển vùng chỉ vì một metric vượt ngưỡng trong vài giây. Một trigger tốt kết hợp tín hiệu khách hàng, trạng thái nền tảng và tình trạng dữ liệu:

| Loại tín hiệu | Ví dụ | Dùng để quyết định gì? |
| --- | --- | --- |
| SLI người dùng | Tỷ lệ request lỗi, p95/p99, giao dịch không hoàn tất | Có thực sự ảnh hưởng khả năng phục vụ không? |
| Infrastructure | Backend unhealthy, instance không ready, mất kết nối region | Phạm vi sự cố và nơi còn khỏe |
| Data state | Replication lag, khả năng promote, consistency checkpoint | B có thể nhận ghi an toàn không? |
| Dependency | IAM, Secret Manager, payment gateway, DNS, private connectivity | B có đáp ứng đầy đủ hành trình không? |
| Capacity | CPU, queue, số instance/pod, database throughput | B có chịu được tải sau chuyển không? |
| Con người/quy trình | Incident commander, người sở hữu dữ liệu, change approval | Ai có quyền quyết định chuyển hoặc dừng? |

Nên có ít nhất hai bước: **phát hiện và đánh giá** rồi **xác nhận điều kiện để chuyển**. Một lỗi health check tạm thời có thể do đợt deploy đang diễn ra; chuyển vùng đột ngột rồi đảo lại liên tục có thể khuếch đại sự cố.

Định nghĩa ngưỡng hysteresis, thời gian quan sát tối thiểu, cooldown và quy định ai được override. Với dữ liệu ghi có nguy cơ mất/corruption, ưu tiên failover có kiểm soát hoặc tự động hóa có những safety gates chặt, thay vì chuyển writer chỉ dựa trên HTTP health.

## 10. Chống split-brain và xác lập quyền ghi duy nhất

**Split-brain** xảy ra khi hai phía cùng tin mình là writer hợp lệ trong mô hình yêu cầu một nguồn ghi. Ví dụ mạng giữa A và B bị phân vùng, cả hai tiếp tục nhận đơn hàng và sinh các trạng thái khác nhau. Khi kết nối phục hồi, không thể hợp nhất dữ liệu một cách an toàn nếu không có quy tắc rõ.

Các biện pháp thiết kế:

1. Xác định **nguồn sự thật** và writer hợp lệ tại từng thời điểm.
2. Dùng cơ chế fencing hoặc điều khiển quyền ghi được hỗ trợ để bảo đảm writer cũ không thể tiếp tục ghi khi B được mở.
3. Chỉ promote dữ liệu tại B sau khi xác minh điều kiện an toàn theo cơ chế sản phẩm.
4. Ghi nhận generation/epoch, leader identity hoặc trạng thái chuyển vai trò nếu hệ thống dùng cơ chế tương ứng.
5. Bảo đảm API và jobs có idempotency key, đặc biệt với retry và message redelivery.
6. Có kế hoạch đối soát các giao dịch gần điểm gián đoạn.

Không dựa duy nhất vào việc cập nhật DNS để chặn ghi ở A. Client vẫn có thể giữ địa chỉ cũ hoặc kết nối đang mở. Fencing phải được thực hiện ở tầng có khả năng ngăn write một cách đáng tin cậy: database role/quyền, network policy được kiểm chứng, ứng dụng hoặc cơ chế leader election phù hợp.

Với active-active multi-writer thực sự, cần thiết kế conflict resolution và consistency theo dữ liệu nghiệp vụ. Đó là bài toán khác với việc bật hai replica cùng nhận request HTTP.

## 11. Đặc điểm failover của từng dịch vụ dữ liệu GCP

Các dịch vụ Google Cloud không có cùng cách chuyển vai trò:

| Dịch vụ / mô hình | Đặc điểm DR cần đánh giá | Rủi ro cần kiểm tra |
| --- | --- | --- |
| Cloud SQL với cross-region read replica | Replica liên vùng có thể dùng cho phục hồi bằng quy trình promote thích hợp | Sao chép bất đồng bộ có thể lag; promote và chuyển connection string không tự tạo đường replication ngược |
| Cloud SQL HA nội vùng | Xử lý một số sự cố trong vùng/zone theo cơ chế HA của dịch vụ | Không thay thế kế hoạch DR khi cả region bị ảnh hưởng |
| Spanner multi-region | Dịch vụ quản lý replication/leader theo cấu hình instance và mô hình consistency của Spanner | Không áp runbook promote SQL replica máy móc cho Spanner |
| Cloud Storage dual/multi-region | Dữ liệu được phân phối theo loại bucket và chính sách replication được hỗ trợ | Không đồng nhất khả dụng object với RPO bằng 0; cần kiểm tra độ trễ replicate |
| Firestore | Khả năng phục hồi phụ thuộc vị trí database, cấu hình và tính năng được hỗ trợ | Không giả định có manual cross-region replica promotion như Cloud SQL |
| Pub/Sub | Cần xác định message retention, backlog, subscription và luồng producer/consumer | Giao lại, xử lý trùng, ordering và data location |
| BigQuery | Dataset location, sao chép/copy và tính năng DR riêng theo cấu hình | Query ở B có thể chưa có dataset/bảng mới hoặc quyền truy cập tương ứng |

**Cloud SQL:** trong mô hình cross-region replica, cần xác định replication lag, checkpoint và tình trạng replica trước khi promote. Promotion có thể làm đứt quan hệ replication cũ; không được giả định A sẽ tự trở thành replica của B khi A trở lại. Failback thường đòi tái thiết lập replica, đồng bộ dữ liệu và chuyển vai trò có kế hoạch.

**Spanner:** dùng khả năng multi-region và consistency của chính sản phẩm; không thao tác như thể đang điều khiển hai primary MySQL. Cần thiết kế vị trí đọc/ghi, latency, failover behavior và kiểm thử điều kiện đặc thù mà Spanner hỗ trợ.

**Storage và analytics:** phục hồi database không tự phục hồi object, dataset phân tích hoặc metadata liên quan. Nếu giao dịch đơn hàng ghi database rồi lưu file lên Cloud Storage, cần xác định cách đối soát hai nguồn dữ liệu sau sự cố.

Sao lưu là lớp bảo vệ độc lập với replication: lỗi ứng dụng hoặc xóa nhầm có thể được sao chép sang region B. Cần retention, backup, kiểm tra restore và biện pháp bảo vệ khỏi lỗi logic hoặc xóa dữ liệu.

## 12. Trình tự failover chuẩn: không chuyển traffic quá sớm

Một runbook khả thi nên có các giai đoạn với **entry criteria**, người chịu trách nhiệm và **exit criteria**.

| Giai đoạn | Thao tác | Điều kiện để đi tiếp |
| --- | --- | --- |
| F0. Declare | Xác nhận incident, mức ảnh hưởng, chọn incident commander | Có quyền quyết định và kênh liên lạc |
| F1. Freeze | Tạm dừng deploy/jobs thay đổi schema; kiểm soát write tại A khi cần | Không có thay đổi làm lệch trạng thái |
| F2. Assess data | Kiểm tra replication lag, checkpoint, backup, khả năng promote | Biết rõ RPO ước lượng và lựa chọn phục hồi |
| F3. Fence old writer | Ngăn A tiếp tục ghi nếu yêu cầu single-writer | Có bằng chứng writer cũ không còn nhận ghi |
| F4. Promote/activate B | Kích hoạt data writer hoặc trạng thái dữ liệu tại B theo runbook dịch vụ | B xử lý được write/read thử nghiệm |
| F5. Enable workloads | Xác minh secrets, IAM, capacity, service endpoints ở B | Critical user journeys trên B thành công |
| F6. Shift traffic | Chuyển request mới theo policy hỗ trợ | Tỷ lệ lỗi và latency tại B trong ngưỡng |
| F7. Observe | Theo dõi backlog, retry, traffic còn lại tại A, giao dịch bất thường | SLO đang phục hồi; không có split-brain |
| F8. Stabilize | Ghi lại điểm phục hồi, tài nguyên đã thay đổi và tình trạng dự phòng | Runbook cập nhật, có kế hoạch failback |

Không cần mọi bước luôn có cùng thứ tự tuyệt đối: với ứng dụng chỉ đọc có thể chuyển một phần traffic trước khi chuyển writer; với một số dịch vụ được quản lý, nền tảng tự xử lý data failover. Nhưng mỗi bước bỏ qua phải có lý do rõ ràng, tránh biến runbook thành loạt lệnh thủ công không có kiểm soát.

Trong trường hợp mất kết nối liên region và không biết A còn sống hay không, cần ưu tiên an toàn dữ liệu hơn tốc độ. Nếu không thể chứng minh quyền ghi duy nhất, dùng chế độ read-only hoặc từ chối tạm thời một số thao tác nguy hiểm cho đến khi có phương án fencing an toàn.

## 13. Ví dụ kiểm tra sẵn sàng và trạng thái trước khi chuyển

Các lệnh dưới đây chỉ nhằm **quan sát**, không thực hiện failover hoặc thay đổi lưu lượng. Thay project, region và resource bằng môi trường thử nghiệm hợp lệ.

Kiểm tra hai Cloud Run services:

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --format="value(status.url,status.conditions)"

gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-east1 \
  --format="value(status.url,status.conditions)"
~~~

Kiểm tra backend services global (nếu kiến trúc sử dụng loại này):

~~~bash
gcloud compute backend-services list \
  --project=PROJECT_ID \
  --global

gcloud compute backend-services get-health BACKEND_SERVICE_NAME \
  --project=PROJECT_ID \
  --global
~~~

Lệnh get-health áp dụng cho backend/health-check model được hỗ trợ, không phải bảo đảm quan sát được health giống nhau với serverless NEG. Nếu đang dùng Cloud Run qua serverless NEG, hãy kết hợp logs, request probes và telemetry của ứng dụng thay vì suy diễn từ một câu lệnh.

Kiểm tra Cloud SQL instance liên quan:

~~~bash
gcloud sql instances describe DB_INSTANCE_NAME \
  --project=PROJECT_ID \
  --format="yaml(name,region,state,replicaConfiguration,masterInstanceName)"
~~~

Các trường hiển thị có thể khác nhau theo phiên bản CLI và loại instance; dữ liệu từ lệnh describe **không thay thế** kiểm tra replication lag và trạng thái transaction bằng metric/query được dịch vụ hỗ trợ. Không promote database chỉ vì instance báo RUNNABLE.

Kiểm tra DNS zone nếu DNS nằm trong đường chuyển:

~~~bash
gcloud dns record-sets list \
  --project=PROJECT_ID \
  --zone=APP_DNS_ZONE
~~~

Trong diễn tập, cần lưu snapshot policy/record/route theo cách kiểm toán được và xác minh request thật đến đúng region B. Không đưa token hoặc secret vào log phục hồi.

## 14. Chuyển traffic từng bước khi dữ liệu cho phép

Nếu B đã sẵn sàng phục vụ và mô hình dữ liệu cho phép hai region nhận một phần lưu lượng, có thể chuyển có kiểm soát để phát hiện lỗi sớm:

| Giai đoạn | Phân phối minh họa | Gate cần kiểm tra |
| --- | --- | --- |
| Baseline | A: 100%, B: 0% | B đã warm, data/identity/endpoint hợp lệ |
| Canary | A: 95%, B: 5% | SLI, error rate, latency, phiên và phụ thuộc |
| Mở rộng | A: 75%, B: 25% | Capacity B, database connections, retry/backlog |
| Chuyển phần lớn | A: 25%, B: 75% | Không có lỗi theo nhóm người dùng |
| Hoàn tất | A: 0%, B: 100% | SLO ổn định, không còn request quan trọng ở A |

Đây là **kịch bản chuyển có kế hoạch**, không phải quy trình bắt buộc khi A đã hỏng hoàn toàn. Khi A lỗi nghiêm trọng, có thể chuyển thẳng sang B nếu các safety gates cho phép. Ngược lại, nếu chỉ B được phép ghi, không gửi một phần request ghi tới A trong các bước canary khi A đã bị fence.

Thay tỷ lệ traffic phải phù hợp ngữ nghĩa transaction, session affinity và vùng dữ liệu. Với đơn hàng, tách rõ **read canary**, **write canary**, callback từ đối tác và các tác vụ chạy nền. Nếu client có session state trong bộ nhớ tại A, cần thiết kế session store chia sẻ hoặc cơ chế cấp token stateless phù hợp để B phục vụ request tiếp nối.

Khi tăng traffic, quan sát RPS thực tế theo region thay vì chỉ tỷ lệ cấu hình. DNS cache, session đang mở hoặc cơ chế chọn backend có thể khiến phần trăm thực tế khác mong đợi.

## 15. Xử lý Cloud DNS, phiên và kết nối lâu dài

Ngay cả khi entrypoint chuyển traffic nhanh, các kết nối cũ có thể tiếp tục đi tới A:

- HTTP keep-alive và gRPC streaming tồn tại qua nhiều request.
- Connection pool của Java/Spring có thể giữ IP hoặc socket cũ.
- DNS resolver caching không tuân thủ cùng một TTL.
- Mobile client có thể mất mạng và retry sau khoảng thời gian dài.
- Webhooks từ hệ thống ngoài có allowlist endpoint hoặc IP cũ.

Thiết kế chuyển vùng cần xử lý **draining**, đóng hoặc retry kết nối an toàn, timeout và idempotency. Không trả về lỗi tùy tiện để ép client chuyển nơi nếu client sẽ retry một thao tác thanh toán không có idempotency key.

Với DNS, xác định authoritative zone, TTL hiện tại, routing policy, private/public zone và cách rollback. Với global load balancer, kiểm tra certificate, backend mapping, edge security, URL map và route rules. Trong cả hai trường hợp, mục tiêu là có một địa chỉ dịch vụ ổn định cho người dùng càng nhiều càng tốt.

## 16. Hàng đợi, job và tác vụ nền khi failover

Chuyển request HTTP chỉ là một phần của hệ thống. Pub/Sub consumer, Cloud Run Jobs, scheduled jobs và worker trên GKE/VM có thể tiếp tục chạy tại A ngay cả khi frontend đã chuyển sang B.

Trước khi cho B xử lý các công việc có side effect, cần xác định:

1. Ai là owner của scheduled job hoặc leader xử lý tác vụ định kỳ?
2. Consumer tại A có đang xử lý message chưa ack không?
3. Message có thể được giao lại sau khi A chết không, và handler có idempotent không?
4. Khi B dùng database mới, nó có đọc đúng dữ liệu tham chiếu để xử lý message cũ không?
5. DLQ, retry policy và retention có còn đáp ứng recovery window không?

Một hệ thống có thể phải tạm ngừng consumer vài phút để bảo đảm writer và schema ở B sẵn sàng. Hãy đánh giá backlog, oldest unacked message age, tốc độ drain và tình trạng downstream sau khi mở lại. Không coi việc backlog giảm là bằng chứng nghiệp vụ thành công nếu worker chỉ ack message mà bỏ qua lỗi ghi.

## 17. Failback không phải đảo ngược failover

Sau khi A phục hồi, có thể B đã trở thành nguồn ghi hợp lệ và chứa nhiều thay đổi mới. Chuyển traffic ngay về A khi A chưa nhận các thay đổi này có thể làm mất đơn hàng, tạo dữ liệu cũ hoặc gây hai writer.

Failback là một thay đổi có kế hoạch với những điều kiện:

- A đã hoạt động ổn định và nguyên nhân sự cố được khắc phục, không chỉ khởi động lại.
- Dữ liệu ở A được tái đồng bộ từ nguồn sự thật hiện tại là B; xác minh lag và consistency checkpoint.
- Hạ tầng, IAM, secrets, cấu hình schema và artifact ở A tương đương phiên bản chạy tại B.
- Có cơ chế chuyển quyền ghi an toàn và fencing writer cũ sau khi đổi vai trò.
- Có cách rollback về B nếu A có lỗi và nếu trạng thái dữ liệu cho phép.
- Người dùng và hệ thống ngoài có thông báo nếu dịch vụ cần cửa sổ read-only hoặc maintenance.

Không giả định cơ chế replication tự đảo chiều sau khi promote B. Với Cloud SQL hoặc hệ thống database khác, quy trình rebuild replica hoặc thiết lập reverse replication cần tuân thủ khả năng hỗ trợ của dịch vụ; có thể yêu cầu bước tạo bản sao, backup/restore hoặc thời gian đồng bộ đáng kể.

Một số tổ chức chọn **không failback ngay**: để B là primary lâu hơn nhằm giảm thêm một lần chuyển đổi rủi ro. Đây có thể là quyết định đúng nếu B đủ năng lực, đáp ứng residency/latency và đã có kế hoạch tái lập DR cho lần sự cố tiếp theo.

## 18. Runbook failback có kiểm soát

| Giai đoạn | Thao tác | Bằng chứng hoàn tất |
| --- | --- | --- |
| B0. Assess A | Kiểm tra nguyên nhân cũ, hệ thống phụ trợ và khả năng sẵn sàng A | SLI và health đã phục hồi trong khoảng theo dõi |
| B1. Establish source | Xác nhận B là nguồn dữ liệu hợp lệ sau failover | Có checkpoint và bảng đối soát giao dịch |
| B2. Re-seed/re-replicate | Tái tạo hoặc đồng bộ dữ liệu về A theo cơ chế dịch vụ | A bắt kịp và có thể đọc/kiểm chứng |
| B3. Dry run | Kiểm tra A ở chế độ không gây side effect hoặc read-only | Critical read journeys và capacity PASS |
| B4. Plan write cutover | Tạm dừng/điều tiết ghi, drain jobs, xử lý transaction in-flight | Không còn write đang mở không kiểm soát |
| B5. Fence B; activate A | Chuyển writer theo quy trình hỗ trợ, khóa B khi cần single-writer | A là writer duy nhất, kiểm tra consistency |
| B6. Shift traffic | Chuyển HTTP/gRPC và worker về A có kiểm soát | Error rate, p95, backlog và data checks PASS |
| B7. Rebuild standby | Cấu hình B trở lại vai trò dự phòng với replication đúng hướng | DR topology trở lại trạng thái bảo vệ |
| B8. Close incident | Đánh giá RTO/RPO, chênh lệch dữ liệu và bài học | Runbook, dashboards và quyết định được lưu |

Ở giai đoạn B5, thứ tự thực thi cụ thể phụ thuộc loại database và thủ tục được sản phẩm hỗ trợ. Không thực hiện thao tác thay leader thủ công ngoài kiến trúc của dịch vụ được quản lý. Với dịch vụ có failover nền tảng tự động, hãy dùng semantics chính thức thay vì ép một bản sao trở thành primary bằng lệnh không được hỗ trợ.

## 19. Đối soát dữ liệu và giao dịch sau chuyển vùng

Một phép ping hoặc health check không phát hiện mất giao dịch. Để xác nhận phục hồi, nên có các kiểm tra:

- **Transaction IDs:** giao dịch nào được tạo trước/sau thời điểm chuyển writer, có thiếu hoặc trùng không?
- **Watermark/checkpoint:** bộ xử lý sự kiện đã hoàn tất đến offset hoặc thời điểm nào?
- **Read-after-write:** giao dịch mới tạo ở B có thể đọc lại từ đúng nguồn không?
- **Object-to-record:** bản ghi tham chiếu object trên Cloud Storage có object tương ứng không?
- **External side effects:** email, thanh toán, callback đã gửi có lặp lại do retry không?
- **Schema/version:** vùng B có migration/schema tương thích với ứng dụng hiện tại không?

Nếu RPO khác 0, cần công khai phạm vi dữ liệu có thể mất và quy trình phục hồi từ event log, đối tác hoặc sao lưu nếu khả thi. Không thể khẳng định RPO đạt chỉ vì replication lag lúc kiểm tra là 0: phải xét thời điểm mất liên lạc và bằng chứng ứng với lần sự cố thật.

Trong nghiệp vụ không chấp nhận giao dịch trùng, dùng idempotency key và trạng thái xử lý bền vững. Retry nên có exponential backoff và giới hạn số lần; retry vô hạn trong lúc dữ liệu chưa sẵn sàng sẽ tăng tải tại region B.

## 20. Quan sát failover: điều gì cần đo?

Dashboard và alert phục vụ DR nên có ba nhóm tín hiệu:

| Nhóm | Metric hoặc bằng chứng |
| --- | --- |
| Trải nghiệm người dùng | Availability, p95/p99 latency, HTTP/gRPC errors, kết quả giao dịch thật |
| Routing và capacity | Backend health theo loại hỗ trợ, RPS từng region, instance/pod count, CPU/RAM, connection pool, queue |
| Dữ liệu và tính đúng đắn | Replication lag, writer identity, checkpoint, transaction conflicts, backlog, oldest unacked age |

Một timeline sự cố cần ghi:

~~~text
T0  Sự cố bắt đầu ảnh hưởng người dùng
T1  Alert được phát hiện và incident được mở
T2  Quyết định chuyển vùng được phê duyệt
T3  Writer cũ được fence hoặc trạng thái ghi an toàn
T4  Dữ liệu tại B sẵn sàng phục vụ
T5  Traffic chuyển đến B
T6  Hành trình nghiệp vụ và SLO ổn định
T7  Phục hồi khả năng dự phòng; lập kế hoạch failback
~~~

RTO quan sát được cần dựa trên lúc mất chức năng đến lúc chức năng được khôi phục, không chỉ lấy thời gian chạy script chuyển traffic. Cần ghi lại số request lỗi, số giao dịch bị ảnh hưởng và dữ liệu có thể mất để đánh giá tác động thực.

Audit trail nên chứa người ra quyết định, bản cấu hình trước/sau, source revision, thời điểm thay đổi, quyền sử dụng và kết quả health checks. Không ghi thông tin xác thực hoặc dữ liệu nhạy cảm vào ticket/log công khai.

## 21. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ triển khai frontend ở hai region | Database writer vẫn là điểm lỗi duy nhất | Thiết kế DR cho mọi dependency quan trọng |
| Xem backend healthy như dữ liệu đã sẵn sàng | Request thành công giả hoặc ghi dữ liệu sai | Dùng health và data-readiness gates riêng |
| Mở writer B trước khi fence A | Nguy cơ split-brain và dữ liệu phân kỳ | Xác lập writer duy nhất bằng cơ chế được hỗ trợ |
| Tin rằng DNS đổi là mọi client chuyển ngay | Cache và kết nối cũ vẫn đi về A | Đo client thực tế, dùng draining và idempotency |
| Coi Cloud SQL HA nội vùng là DR liên region | Sự cố region vẫn làm ngừng dữ liệu | Xây dựng kế hoạch cross-region riêng |
| Coi backup giống replication | Backup có thể cũ; replication có thể sao chép lỗi logic | Duy trì cả DR replication và backup/restore |
| Chuyển traffic 100% khi B chưa đủ capacity | Overload, timeout, lỗi dây chuyền | Kiểm thử mức tải và autoscaling B trước |
| Chuyển HTTP mà quên workers | Jobs A và B cùng xử lý gây side effect trùng | Chuyển leader/consumer cùng dữ liệu |
| Failback về A khi dữ liệu A cũ | Mất transaction được ghi trong thời gian chạy ở B | Reverse replication, fencing, reconcile rồi mới cutover |
| Diễn tập chỉ một lần không đo RTO/RPO | Không phát hiện thay đổi cấu hình và lỗi phụ thuộc | Diễn tập định kỳ, ghi số liệu và remediation |
| Không kiểm tra IAM/secret ở B | Region dự phòng khởi động nhưng không hoạt động | Kiểm thử identity và critical journeys ở B |

## 22. Diễn tập failover và failback an toàn

Trước lần diễn tập đầu tiên, dùng project/ứng dụng thử nghiệm có dữ liệu giả và giới hạn chi phí. Không chủ động cắt traffic hay promote database production nếu chưa có phê duyệt, người trực và kế hoạch hoàn nguyên cụ thể.

Một lộ trình diễn tập tăng dần:

1. **Tabletop exercise:** các nhóm đi qua từng bước runbook và xác nhận vai trò, đường liên lạc, phê duyệt.
2. **Read-only dry run:** kiểm tra kết nối, cấu hình B, IAM, route/DNS, SLO và replication status mà không đổi writer.
3. **Canary traffic:** chuyển một phần request đọc ở môi trường thử nghiệm có dữ liệu phù hợp.
4. **Controlled failure:** mô phỏng endpoint A lỗi và xác minh cơ chế traffic failover theo chính sách hỗ trợ.
5. **Data promotion rehearsal:** thực hành chuyển writer và kiểm tra tính nhất quán trên database thử nghiệm.
6. **Failback rehearsal:** đồng bộ ngược, chuyển quyền ghi lại và tái lập B làm standby.
7. **Peak-load check:** bảo đảm B chịu được mức traffic mục tiêu và dependency không bị quá tải.
8. **Postmortem:** ghi RTO/RPO quan sát được, lỗi, manual steps và kế hoạch tự động hóa an toàn.

Không nhất thiết phá hủy tài nguyên để kiểm thử mất region. Có thể dùng traffic controls hoặc fault injection ở phạm vi thử nghiệm, nhưng phải chứng minh kịch bản thực sự kiểm tra các failure modes liên quan: network partition, mất data writer, lỗi DNS và hỏng dependency.

Trong mọi diễn tập, cần có **abort criteria**: khi dữ liệu sai, chi phí tăng ngoài giới hạn hoặc hệ thống ngoài phạm vi chịu ảnh hưởng, dừng và phục hồi ngay theo runbook. Tiêu chí dừng phải độc lập với điều kiện thành công của phép thử.

## 23. Bài thực hành: ứng dụng đơn hàng hai region

**Bối cảnh:** API Spring Boot chạy ở Cloud Run region A (asia-southeast1) và B (asia-east1). Backend dữ liệu dùng một database chính ở A và cơ chế replica B mà nhóm đã xác nhận hỗ trợ phục hồi theo mục tiêu của tổ chức. Một global entrypoint đứng trước hai API.

Yêu cầu giả định: RTO 30 phút, RPO tối đa 10 phút, tỷ lệ thành công của các thao tác quan trọng sau chuyển vùng đạt ít nhất 99,5% trong giai đoạn ổn định. Các giá trị này chỉ phục vụ bài tập và không là tính năng mặc định của các dịch vụ GCP.

Nhiệm vụ:

1. Lập dependency map gồm Cloud Run, database, Secret Manager, IAM, Artifact Registry, Pub/Sub và các dịch vụ đối tác.
2. Xác định model warm standby hay hot standby và ước lượng chi phí duy trì B.
3. Thiết kế tín hiệu phát hiện lỗi và ngưỡng ra quyết định failover.
4. Viết phương án fence writer A trước khi B nhận ghi, theo khả năng sản phẩm database.
5. Chuẩn bị các phép kiểm read/write, transaction ID và replication lag.
6. Mô tả cách global entrypoint hướng request mới sang B, đồng thời xử lý session/gRPC connections cũ.
7. Xây dựng timeline T0–T6 để đo RTO và báo cáo RPO thực tế.
8. Giả lập B là primary trong một thời gian, sinh dữ liệu mới và thiết kế reverse replication.
9. Viết các bước failback về A không làm mất ghi mới ở B.
10. Tạo checklist xác minh sau chuyển vùng gồm latency, lỗi, backlog và audit trail.

**Kết quả cần nộp:** sơ đồ, ma trận dependency readiness, bảng rủi ro mất dữ liệu, policy chuyển traffic, runbook failover/failback có người chịu trách nhiệm, bằng chứng thử nghiệm và báo cáo đối chiếu RTO/RPO. Không điền số liệu latency hoặc replication lag giả như thể được đo từ hệ thống thực.

## 24. Checklist production cho chuyển vùng an toàn

- Có RTO/RPO, SLI/SLO và phạm vi sự cố được phê duyệt cho từng chức năng quan trọng.
- Có inventory ứng dụng, data stores, jobs, secrets, IAM, DNS, network và dịch vụ ngoài ở cả hai region.
- B có artifact, capacity, cấu hình, quyền và dependency cần thiết để phục vụ traffic.
- Đã phân biệt failover của frontend với failover quyền ghi dữ liệu.
- Có bằng chứng về replication lag, data checkpoint, backup và giới hạn mất dữ liệu.
- Có cơ chế chống split-brain và ngăn writer cũ tiếp tục ghi khi chuyển vai trò.
- Phương án load balancing hoặc DNS steering được hỗ trợ cho backend cụ thể và đã kiểm thử.
- Đã thử session, long-lived connections, queue consumers, retry và idempotency.
- Chuyển traffic theo điều kiện sức khỏe và dữ liệu, không chỉ một health endpoint.
- Runbook xác định incident commander, người phê duyệt data promotion và điều kiện abort.
- Đã xác minh B xử lý được tải kỳ vọng, kể cả database connections và autoscaling.
- Có dashboard ghi RPS theo region, lỗi, latency, writer state, lag và backlog.
- Failback bao gồm đồng bộ ngược, đối soát, write cutover và tái lập standby.
- Có kế hoạch kiểm thử định kỳ và quản lý thay đổi khi kiến trúc phát triển.
- Không có secret trong mã triển khai hoặc tài liệu sự cố, quyền DR theo nguyên tắc tối thiểu.
- Sau diễn tập/sự cố, số liệu thực được ghi cùng thay đổi cần khắc phục và người sở hữu.

Failover thành công không phải là lúc một bản ghi DNS đổi hoặc một load balancer chọn backend khác, mà là lúc người dùng có thể tiếp tục giao dịch đúng đắn trên vùng phục hồi trong giới hạn RTO/RPO đã thống nhất. Failback chỉ hoàn tất khi dữ liệu, quyền ghi, traffic và năng lực dự phòng được khôi phục có kiểm chứng. Với Google Cloud, kết hợp cơ chế chuyển traffic phù hợp, mô hình dữ liệu chính xác, giám sát theo SLO và diễn tập thường xuyên sẽ giúp kiến trúc đa region trở thành một kế hoạch DR đáng tin cậy thay vì chỉ là hai bản triển khai song song.
