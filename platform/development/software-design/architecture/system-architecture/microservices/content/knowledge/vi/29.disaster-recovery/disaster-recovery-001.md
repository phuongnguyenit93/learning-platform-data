# Phân biệt tính sẵn sàng cao với khả năng khôi phục thảm họa trong microservices

## 1. Bối cảnh và mục tiêu

Một hệ thống microservices có thể chạy 30 replica trên nhiều máy chủ, tự restart khi một pod lỗi, nhưng vẫn ngừng hoạt động hoàn toàn nếu vùng triển khai bị mất, database bị xóa hoặc một tài khoản quản trị bị xâm nhập. Ngược lại, hệ thống có backup ở vùng khác có thể khôi phục được sau một ngày nhưng không đáp ứng yêu cầu phục vụ liên tục của người dùng.

Hai mục tiêu thường bị nhầm lẫn:

- **High Availability (HA, tính sẵn sàng cao):** giảm gián đoạn trong các sự cố dự kiến, thường bằng dự phòng, phát hiện lỗi và chuyển tải hoặc tự động phục hồi trong ranh giới thiết kế.
- **Disaster Recovery (DR, khôi phục thảm họa):** chuẩn bị phương án khôi phục dịch vụ, dữ liệu và khả năng vận hành khi một sự cố lớn làm vô hiệu hoặc không còn đáng tin cậy những thành phần, vùng hoặc hệ thống vốn dùng để duy trì dịch vụ.

HA tập trung **tiếp tục phục vụ khi thành phần hỏng**. DR tập trung **khôi phục năng lực phục vụ sau sự kiện vượt qua phạm vi chịu lỗi thông thường**, đồng thời đáp ứng giới hạn thời gian gián đoạn và mất dữ liệu được chấp nhận.

Hai chiến lược liên quan nhưng không thay thế nhau. Nhiều replica bảo vệ ứng dụng trước một số lỗi node, nhưng không bảo vệ dữ liệu trước xóa nhầm được replication sang mọi bản sao. Backup được kiểm chứng cho phép phục hồi dữ liệu bị xóa, nhưng nếu phục hồi mất sáu giờ thì chưa đáp ứng các hệ thống cần failover trong vài phút.

Bài học hướng tới khả năng:
1. Giải thích chính xác HA, DR, fault tolerance, resilience, backup và business continuity.
2. Phân biệt availability SLO, RTO, RPO và phạm vi lỗi (failure domain).
3. Nhận diện sự cố mà HA xử lý được và sự cố buộc kích hoạt DR.
4. Thiết kế hạ tầng, dữ liệu và quy trình failover/failback cho microservices.
5. Phân tích trade-off giữa active-active, active-passive, warm standby, pilot light và backup/restore.
6. Thiết lập runbook, kiểm thử khôi phục và bằng chứng đạt mục tiêu vận hành.

## 2. HA và DR khác nhau ở điểm nào?

| Góc nhìn | High Availability | Disaster Recovery |
| --- | --- | --- |
| Mục đích | Giảm tần suất/thời gian gián đoạn của dịch vụ đang vận hành | Khôi phục sau sự kiện nghiêm trọng hoặc mất miền vận hành |
| Loại lỗi điển hình | Process/pod chết, node hỏng, một instance DB mất, một AZ lỗi nếu có thiết kế | Region không khả dụng, mất dữ liệu diện rộng, mã độc phá hủy, cấu hình toàn vùng bị hỏng |
| Biện pháp chủ yếu | Health check, load balancing, replication, quorum, failover, redundancy | Backup/restore, sao chép ngoài vùng, môi trường dự phòng, quy trình tuyên bố thảm họa và chuyển vùng |
| Thời gian phản ứng | Thường tự động, tính bằng giây hoặc phút tùy thiết kế | Từ phút đến nhiều giờ/ngày theo chiến lược và RTO |
| Trọng tâm dữ liệu | Khả năng đọc/ghi tiếp tục với tính nhất quán phù hợp | Khả năng có dữ liệu đúng, an toàn và phục hồi được tới mốc chấp nhận |
| Quy trình | Tự phục hồi thường nhật, giám sát và on-call | Kế hoạch/điều phối khủng hoảng, quyết định kích hoạt, khôi phục và failback |
| Bằng chứng | SLI/SLO availability, failover duration, lỗi khi thành phần bị loại | RTO/RPO thực đo, tính toàn vẹn backup, drill kết thúc thành công |
| Giới hạn | Không đủ trước mất toàn bộ miền hoặc lỗi logic lan truyền | Không tự duy trì dịch vụ liên tục trước mọi lỗi nhỏ |

**Ví dụ 1 — HA:** pod `catalog-service` bị OOMKilled; Kubernetes tạo pod khác, service mesh/load balancer bỏ endpoint unhealthy và các replica khác xử lý traffic. Nếu người dùng gần như không gián đoạn, đó là hiệu quả của HA.

**Ví dụ 2 — HA có điều kiện:** database primary hỏng; hệ thống bầu replica mới. Có thể có vài giây lỗi ghi và nguy cơ mất một số giao dịch chưa sao chép, tùy cơ chế commit và replication. HA không đồng nghĩa RPO bằng 0.

**Ví dụ 3 — DR:** cả region chứa database và cluster không thể truy cập. Nhóm kích hoạt môi trường ở region dự phòng, quyết định vị trí dữ liệu phục hồi và chuyển DNS/traffic. Đây là khôi phục thảm họa, dù kỹ thuật cũng có thể sử dụng load balancer và replication.

**Ví dụ 4 — DR về mặt logic:** một migration hoặc tài khoản bị chiếm đã xóa dữ liệu và lệnh xóa lan tới các replica. Tất cả node vẫn còn sống, dashboard CPU bình thường, nhưng dữ liệu không thể tin cậy. HA không giải quyết vấn đề này; cần phục hồi từ bản sao không bị ảnh hưởng và xác minh dữ liệu.

## 3. Các khái niệm liên quan

**Availability:** tỷ lệ thời gian hoặc tỷ lệ request đáp ứng điều kiện thành công theo định nghĩa dịch vụ. Availability cần nhìn từ người dùng và luồng nghiệp vụ, không chỉ trạng thái process.

**Reliability:** khả năng thực hiện chức năng đúng trong một khoảng thời gian và điều kiện; một HTTP 200 trả kết quả nghiệp vụ sai không thể được xem là thành công chỉ vì server còn hoạt động.

**Fault tolerance:** khả năng hệ thống tiếp tục vận hành khi một số thành phần lỗi, với mức suy giảm được định nghĩa.

**Resilience:** khả năng chịu đựng, thích ứng, phục hồi và cải thiện sau lỗi; bao gồm phòng ngừa, phát hiện, cô lập, phục hồi và học hỏi.

**Business continuity:** bảo đảm hoạt động kinh doanh quan trọng tiếp tục trong khủng hoảng, có thể bao gồm quy trình thủ công, con người, hỗ trợ khách hàng, pháp lý và đối tác ngoài kỹ thuật. DR là một phần của bức tranh này.

**Backup:** bản sao dữ liệu/metadata để phục hồi; có thể là snapshot, logical dump, archive hoặc continuous backup kèm log giao dịch. Replication không phải backup nếu cùng lan truyền thao tác xóa hoặc corruption.

**Failover:** chuyển xử lý sang thành phần, instance hoặc môi trường dự phòng khi thành phần chính không đáp ứng.

**Failback:** chuyển hệ thống trở lại môi trường chính hoặc trạng thái mục tiêu mới sau khi đã khôi phục và xác nhận. Failback thường phức tạp hơn suy nghĩ ban đầu vì dữ liệu có thể tiếp tục thay đổi tại môi trường dự phòng.

**Failure domain:** tập thành phần có thể cùng bị ảnh hưởng bởi một sự cố như một process, host, rack, availability zone, region, cloud provider, hệ thống IAM hoặc đội vận hành.

Điểm mấu chốt là đo độ bền của hệ thống **so với những failure domain đã chọn**, không tuyên bố “đã có HA” một cách tuyệt đối.

## 4. Từ pod đến region: những lớp lỗi khác nhau

~~~text
Service request
  ├── Process / thread / container
  ├── Pod / VM / node
  ├── Rack / network segment
  ├── Availability zone (AZ)
  ├── Region / data center
  ├── Identity / DNS / cloud control plane
  ├── Data integrity / encryption keys
  └── Tác động rộng: sai cấu hình, xâm nhập, vận hành, nhà cung cấp
~~~

Thiết kế nhiều replica trong cùng node bảo vệ rất ít. Đặt replica trên nhiều node trong cùng AZ giúp giảm lỗi node, nhưng chưa đảm bảo chịu lỗi AZ. Dùng nhiều AZ vẫn không đủ chống mất cả region, lỗi IAM chung hoặc thay đổi cấu hình phá hủy được áp dụng toàn hệ thống.

Khi xác định chiến lược, lập **bản đồ phụ thuộc**:
- API gateway, DNS, certificate, WAF, CDN.
- Service discovery, cluster control plane và worker nodes.
- Datastore chính, read replicas, cache, search index, broker.
- Secret manager, IAM, key management, container registry.
- External payment, email, nhà cung cấp nhận diện, logistics.
- Observability, CI/CD, artifact store, source repository.
- Nhà vận hành, network để truy cập, tài liệu runbook.

Một standby region có cluster sẵn nhưng không thể lấy certificate hoặc container image có thể vẫn không phục vụ được. Mục tiêu DR chỉ đáng tin khi **đường thực thi end-to-end** được kiểm chứng.

## 5. Availability SLO khác RTO và RPO

### 5.1. Availability SLO

SLO availability nói về mức độ dịch vụ đáp ứng người dùng trong một khoảng thời gian.

Ví dụ: mục tiêu availability 99,9% trong 30 ngày. Nếu giả định một tháng 30 ngày liên tục, ngân sách thời gian không khả dụng lý thuyết xấp xỉ:

`30 ngày × 24 giờ × 60 phút × (1 − 0,999) = 43,2 phút`.

Phép tính này chỉ minh họa **time-based availability**. Nếu SLI của tổ chức tính theo tỷ lệ request thành công, ngân sách được tính theo request chứ không thể đồng nhất hoàn toàn với số phút downtime.

Một service đạt SLO tháng không có nghĩa mọi sự cố có thể được giải quyết trong 43,2 phút: thời điểm sự cố, error budget đã tiêu dùng và phân phối request còn quan trọng.

### 5.2. RTO — Recovery Time Objective

**RTO** là mục tiêu thời gian tối đa để khôi phục chức năng hoặc quy trình sau mốc sự cố/kích hoạt được tổ chức định nghĩa. RTO thường bao gồm phát hiện, tuyên bố thảm họa, quyết định failover, khởi tạo, phục hồi, chuyển traffic và kiểm chứng nghiệp vụ.

Ví dụ: checkout RTO 30 phút nghĩa là cần phương án và diễn tập chứng minh checkout có thể được khôi phục theo định nghĩa service đạt yêu cầu trong 30 phút từ mốc bắt đầu tính RTO đã chốt. Không nên coi chỉ “pod đã Running” là hoàn tất RTO nếu luồng đặt hàng vẫn lỗi.

### 5.3. RPO — Recovery Point Objective

**RPO** là giới hạn lượng dữ liệu có thể mất, thường biểu diễn bằng khoảng thời gian tính từ trạng thái khôi phục đến mốc sự cố. RPO 5 phút cho biết thiết kế cho phép mất các cập nhật được commit trong khoảng tối đa 5 phút trước thảm họa theo cách đo và phạm vi đã định.

RPO không khẳng định “backup được tạo đúng mỗi 5 phút”. Nếu backup 5 phút/lần nhưng truyền, kiểm chứng, giải mã hoặc cataloging chậm, bản phục hồi thực tế có thể cũ hơn mục tiêu. RPO cũng không tự chứng minh dữ liệu giao dịch giữa nhiều database nhất quán.

### 5.4. RTO và RPO là hai trục độc lập

| Kịch bản | RTO | RPO | Ý nghĩa |
| --- | --- | --- | --- |
| Cluster phụ lỗi, tự chuyển sang node khác | Vài giây/phút | Có thể bằng 0 hoặc khác 0 | Phụ thuộc replication và commit semantics |
| Restore snapshot hôm qua | Có thể nhiều giờ | Có thể gần 24 giờ | Phục hồi được nhưng mất nhiều dữ liệu |
| Warm standby đa vùng | Phút đến giờ | Theo replication lag/cách phục hồi | Cần duy trì sẵn hạ tầng và dữ liệu |
| Active-active đa vùng | Có thể ngắn | Không tự động bằng 0 | Cần giải quyết consistency và conflict |
| Backup immutable/cách ly để chống xóa độc hại | Phụ thuộc phục hồi | Theo điểm khôi phục sạch cuối cùng | Quan trọng khi bản replica đã bị nhiễm lỗi |

Các con số trong bảng chỉ là xu hướng; RTO/RPO phải được định nghĩa và chứng minh bằng thực nghiệm, theo từng nghiệp vụ.

## 6. Phân tầng quan trọng của dịch vụ

Không nên yêu cầu mọi microservice có cùng RTO/RPO. Ví dụ hệ thống bán hàng:

| Năng lực | Tác động khi gián đoạn | RTO minh họa | RPO minh họa |
| --- | --- | --- | --- |
| Checkout và thanh toán | Không chốt đơn hoặc có rủi ro giao dịch | 15 phút | Gần 0, tùy cam kết và thiết kế |
| Quản lý đơn hàng | Khách không xem/đổi trạng thái | 30 phút | 1 phút |
| Catalog hiển thị | Người dùng khó xem sản phẩm | 60 phút | 15 phút nếu có thể tái tạo |
| Recommendation | Trải nghiệm gợi ý suy giảm | 4 giờ | 1 giờ hoặc tái tạo |
| Batch analytics | Báo cáo chậm cập nhật | 24 giờ | Theo batch lịch sử và SLA |
| Notification | Chậm email/SMS | 2 giờ | Phụ thuộc khả năng replay event |

Đây là **mục tiêu giả định cho bài học**, không phải tiêu chuẩn bắt buộc. Người phụ trách nghiệp vụ phải xác nhận tác động tài chính, an toàn, danh tiếng, pháp lý và phụ thuộc lẫn nhau.

Cần đánh giá **quy trình nghiệp vụ** thay vì chỉ từng service. Checkout có RTO 15 phút nhưng phụ thuộc identity-service có RTO 4 giờ thì mục tiêu checkout khó đạt. Tương tự, hệ thống có thể mở lại gateway nhưng chưa thể tạo đơn nếu inventory database chưa phục hồi.

## 7. HA trong thực tế: các cơ chế chủ đạo

### 7.1. Dự phòng instance và phân tán lỗi

Với stateless API, thường chạy nhiều replica trên nhiều node/AZ, load balancer chỉ gửi traffic tới instance đủ điều kiện, và scheduler tái tạo instance hỏng.

Cần:
- Readiness probe đo khả năng nhận traffic, không chỉ process tồn tại.
- Liveness probe đủ thận trọng, tránh tự restart service khi dependency đang tạm chậm.
- Pod anti-affinity/topology spread hoặc placement policy phù hợp failure domain.
- Đủ headroom để các instance còn lại chịu tải khi một phần bị mất.
- Graceful shutdown, connection draining và retry/budget hợp lý.
- Autoscaling để theo kịp nhu cầu, nhưng không xem autoscaler là thay thế cho capacity dự phòng ngay thời điểm failover.

### 7.2. Dependency HA

Ứng dụng khỏe chưa đủ nếu mọi replica cùng gọi một database primary đơn lẻ, một broker đơn lẻ hoặc một DNS không đáng tin.

Database HA có thể có primary/standby và failover; cache cluster có replication và sharding; broker có quorum/replica. Cần hiểu **quorum, consistency, replication lag, failover policy và client reconnect** của từng công nghệ.

Các thuật ngữ “managed database”, “cluster” hoặc “multi-node” không đảm bảo mọi dạng lỗi được xử lý. Ví dụ ba replica database dùng cùng volume vật lý hoặc cùng khóa mã hóa có điểm chung dễ hỏng.

### 7.3. Graceful degradation

Khi recommendation-service lỗi, checkout có thể vẫn phục vụ bằng cách ẩn phần gợi ý. Khi notification-service tạm dừng, event có thể được queue rồi xử lý lại. Đây là HA ở góc nhìn **khả năng nghiệp vụ**, vì hệ thống tiếp tục đáp ứng luồng cốt lõi dù chức năng phụ suy giảm.

Cần phân loại dependency bắt buộc và không bắt buộc, đồng thời định nghĩa rõ hành vi dự phòng. Không nên “degrade” bằng cách bỏ xác thực thanh toán hoặc dùng dữ liệu quyền truy cập cũ thiếu kiểm chứng.

### 7.4. Backpressure, timeout và bulkhead

Trong sự cố, retry thiếu kiểm soát có thể khuếch đại tải lên dependency đang yếu. Dùng:
- Timeout và deadline xuyên suốt call chain.
- Retry có backoff và jitter cho operation có thể retry an toàn.
- Circuit breaker hạn chế gọi dependency đang lỗi.
- Bulkhead/queue limit cách ly luồng nghiệp vụ.
- Rate limit/admission control khi capacity còn lại không đủ.

Các cơ chế này tăng khả năng chịu lỗi nhưng không thay thế phương án phục hồi dữ liệu hoặc vùng triển khai.

## 8. Khi nào HA không đủ?

Một số tình huống vượt qua thiết kế HA thông thường:

1. **Mất cả region:** mọi node trong vùng không thể truy cập, multi-AZ cùng region không cứu được.
2. **Dữ liệu bị xóa/corrupt và replication lan lỗi:** tất cả bản sao hoạt động nhưng đều có dữ liệu sai.
3. **Credential hoặc khóa mã hóa bị mất/thu hồi:** replica và backup có thể không đọc được dữ liệu.
4. **Cấu hình hoặc migration phá hủy triển khai đồng loạt:** deployment tự động đẩy cùng lỗi tới mọi AZ.
5. **Xâm nhập/ransomware:** attacker xóa snapshot, khóa hệ thống hoặc đầu độc artifact.
6. **Provider/control plane outage:** service vẫn chạy nhưng không thể scale, rotate secret hoặc sửa định tuyến.
7. **Lỗi logic ở cấp nghiệp vụ:** hệ thống xử lý nhanh nhưng giao dịch bị nhân đôi hoặc không thể đối soát.
8. **Phụ thuộc quan trọng ngoài vùng:** region dự phòng vẫn phụ thuộc một API/identity/DNS bị lỗi diện rộng.

Có thể ứng phó một số tình huống trên bằng HA thiết kế rất rộng, ví dụ active-active multi-region. Điểm phân biệt không phải cứ “mất vùng” là DR hay “mất node” là HA tuyệt đối: **HA là cơ chế phục vụ liên tục, DR là năng lực và quy trình phục hồi từ tình huống nghiêm trọng với mục tiêu RTO/RPO rõ ràng**. Một kiến trúc đa vùng có thể đồng thời hỗ trợ cả hai.

## 9. Các chiến lược DR điển hình

### 9.1. Backup and restore

Giữ backup và cấu hình hạ tầng để dựng lại môi trường khi cần. Phù hợp dịch vụ không yêu cầu khôi phục tức thời và ngân sách hạn chế.

Ưu điểm: ít chi phí compute standby. Nhược điểm: RTO thường dài; việc phục hồi phụ thuộc băng thông, kích thước dữ liệu, key, image, automation và chất lượng runbook.

### 9.2. Pilot light

Giữ các thành phần tối thiểu luôn sẵn ở nơi dự phòng, thường là dữ liệu hoặc một lõi hạ tầng, còn phần ứng dụng sẽ scale/dựng lên khi kích hoạt.

Ưu điểm: RTO tốt hơn dựng từ số 0 nếu những thành phần chậm nhất đã chuẩn bị. Nhược điểm: phụ thuộc khả năng mở rộng nhanh và việc dữ liệu còn usable.

### 9.3. Warm standby

Chạy một môi trường dự phòng đã có phần lớn thành phần cốt lõi nhưng công suất thấp hơn production. Khi sự cố, mở rộng capacity rồi chuyển traffic.

Ưu điểm: giảm thời gian khởi động. Nhược điểm: tốn chi phí duy trì và phải kiểm thử capacity thực sự khi failover.

### 9.4. Active-passive với standby gần đầy đủ

Vùng chính xử lý hầu hết traffic; vùng dự phòng luôn sẵn và có dữ liệu đồng bộ theo thiết kế. Failover có thể tự động hoặc được phê duyệt.

Ưu điểm: luồng ghi chủ đạo rõ ràng, vận hành đơn giản hơn active-active nhiều writer. Nhược điểm: vẫn có cutover downtime, replication lag và bài toán tránh hai vùng cùng nhận write.

### 9.5. Active-active đa vùng

Nhiều vùng đồng thời phục vụ traffic; có thể có phân vùng dữ liệu theo vùng, single-writer toàn cục hoặc multi-writer với conflict resolution. Chiến lược phức tạp nhất ở consistency, routing, rate limit, session, idempotency và observability.

Ưu điểm: có thể giảm gián đoạn khi một vùng mất nếu thiết kế và capacity đủ. Nhược điểm: chi phí và độ phức tạp lớn, dễ gặp split-brain hoặc xung đột ghi.

### 9.6. Bảng đánh đổi

| Chiến lược | Hạ tầng thường trực dự phòng | RTO tiềm năng | RPO tiềm năng | Độ phức tạp |
| --- | --- | --- | --- | --- |
| Backup/restore | Thấp | Dài | Theo backup/log | Trung bình, đòi hỏi diễn tập restore |
| Pilot light | Thấp–vừa | Trung bình | Theo đồng bộ dữ liệu | Trung bình |
| Warm standby | Vừa | Ngắn hơn | Theo replication lag | Trung bình–cao |
| Active-passive gần đầy đủ | Cao | Ngắn | Theo replication/commit | Cao |
| Active-active | Cao | Có thể rất ngắn | Phụ thuộc mô hình ghi | Rất cao |

Không suy luận RTO/RPO số phút cụ thể chỉ từ tên chiến lược. Nhiều hệ thống “active-active” vẫn có RTO lớn vì traffic routing hoặc dữ liệu không thể failover tự động. Ngược lại, backup/restore được tự động hóa và kiểm chứng có thể đáp ứng tốt mục tiêu của một dịch vụ ít quan trọng.

## 10. Sơ đồ hai cấp: HA trong vùng, DR giữa vùng

~~~mermaid
flowchart TD
    U[Người dùng] --> G[Global routing / DNS]
    G --> A[Region A - chính]
    A --> A1[AZ 1: API replicas]
    A --> A2[AZ 2: API replicas]
    A1 --> DA[Primary data tier]
    A2 --> DA
    DA --> R[Replication / backups / recovery log]
    R --> DB[Region B: dữ liệu dự phòng]
    G -. Cutover khi thảm họa .-> B[Region B - standby]
    B --> B1[API replicas dự phòng]
    B1 --> DB
~~~

Trong Region A, HA giải quyết lỗi một pod, node, AZ hoặc database instance trong phạm vi kiến trúc. Khi Region A không thể sử dụng hoặc không còn tin cậy, kế hoạch DR dùng tài nguyên và dữ liệu Region B.

Sơ đồ lược bỏ nhiều yếu tố: secret manager, IAM, container registry, chứng chỉ, message broker, outbound provider và observability. Đối với hệ thống thật, tất cả phải nằm trong bản đồ recovery dependency để không rơi vào tình huống ứng dụng khởi động nhưng không xử lý được nghiệp vụ.

## 11. RPO phụ thuộc tính đúng đắn của dữ liệu, không chỉ tốc độ sao chép

### 11.1. Synchronous và asynchronous replication

**Synchronous replication:** một số thiết kế chỉ xác nhận commit khi đã đạt điều kiện ghi tới replica/quorum, giảm nguy cơ mất dữ liệu đã xác nhận; đổi lại latency write và availability có thể chịu tác động khi đường mạng hoặc quorum không đáp ứng.

**Asynchronous replication:** primary xác nhận commit trước rồi đẩy thay đổi tới secondary. Khi primary mất, những commit chưa tới standby có thể bị mất. RPO thực tế phụ thuộc replication lag và thời điểm lỗi.

Từ “synchronous” không tự chứng minh toàn hệ thống có RPO 0. Cần đọc đúng **write acknowledgment semantics**, thành phần nào nằm trong quorum, mức durability và khả năng phân vùng mạng.

### 11.2. Replication không phải backup

Nếu một lệnh sai xóa bảng sản phẩm và replica đồng bộ ngay lập tức, cả hai bên đều có trạng thái đã xóa. Một database cluster vẫn HA nhưng không còn dữ liệu cần thiết.

Backup tốt cho DR thường cần:
- Bản sao có lịch sử theo thời điểm hoặc point-in-time recovery.
- Kho lưu ở miền lỗi khác; quyền truy cập và khóa mã hóa có kế hoạch khôi phục.
- Bảo vệ khỏi xóa/sửa trái phép, chẳng hạn immutable retention hoặc tài khoản độc lập khi phù hợp.
- Xác minh checksum, tính toàn vẹn và khả năng phục hồi thực tế.
- Chính sách retention, kích thước, chi phí và nhu cầu phục hồi từ điểm sạch trước corruption.

Một backup “successful” trên dashboard không chứng minh restoration thành công. Cần thử khôi phục và kiểm tra dữ liệu nghiệp vụ.

### 11.3. Consistency giữa nhiều service

Trong microservices, mỗi service thường sở hữu dữ liệu riêng. Khi phục hồi order-service tại 10:00 nhưng payment-service tại 10:03, hệ thống có thể có payment đã thu mà order chưa được ghi. Một RPO từng database thấp vẫn không đảm bảo **business consistency**.

Cần xác định:
- Aggregate nghiệp vụ cần được đối soát.
- Transaction ID và idempotency key.
- Outbox/event log và khả năng replay theo mốc.
- Quan hệ saga và các bước compensation.
- Phương án reconcile với hệ thống ngoài, đặc biệt payment.
- Thứ tự phục hồi giữa các datastore, queue và consumer.

Không tùy tiện restore tất cả database về các snapshot khác thời điểm rồi mở traffic ngay. Phải có **consistency check và reconciliation** phù hợp.

## 12. HA cho dữ liệu không đồng nghĩa failover ghi an toàn

Cơ chế tự bầu primary có nguy cơ **split-brain**: hai node hoặc vùng cùng tin rằng mình được phép ghi. Nếu giao thông mạng bị chia cắt và mỗi phía vẫn nhận write, khi kết nối trở lại có thể phát sinh xung đột khó giải quyết.

Biện pháp:
- Quorum và lease/fencing để chỉ một writer hợp lệ trong mô hình single-writer.
- Epoch/term/token tăng khi primary thay đổi, từ chối writer cũ.
- Chính sách routing client tới writer đang được chấp thuận.
- Hiểu hành vi khi quorum mất: có thể phải từ chối write để giữ safety.
- Kiểm tra cả database, cache, broker và các external side effects.

Khi kích hoạt DR, không chỉ thay DNS rồi cho standby ghi nếu primary vẫn có thể ghi được trong một phần mạng. Quy trình failover cần **fence môi trường cũ** hoặc chứng minh nó không thể tiếp tục phát hành write theo những đường còn tồn tại.

Trong active-active multi-writer, cần mô hình giải quyết xung đột cụ thể (partitioning, CRDT, application-level merge, optimistic concurrency hoặc một authority cho từng aggregate). Không dùng last-write-wins theo timestamp một cách mặc định cho tiền hoặc tồn kho.

## 13. Dịch vụ stateless và stateful trong chiến lược recovery

### 13.1. Stateless API

Với service không giữ trạng thái nghiệp vụ bền vững trong bộ nhớ:
- Image/artifact cần tồn tại ở registry có thể truy cập từ vùng dự phòng.
- Manifest, config, policy và secret references phải version hóa và có thể áp dụng.
- Load balancer, DNS, certificates và service discovery cần sẵn sàng.
- Warm-up cache và connection pools cần tính vào thời gian recovery.
- Phiên làm việc nếu lưu ở local memory có thể mất; cần chính sách re-login hoặc session store đáng tin.

Stateless giúp HA và DR dễ hơn nhưng **không làm mất phụ thuộc vào dữ liệu, IAM và network**.

### 13.2. Stateful services

Database, broker, object store và search index có cơ chế sao chép/khôi phục khác nhau. Ví dụ:
- **Database:** snapshot, WAL/transaction log, replication, point-in-time restore.
- **Kafka/broker:** topic replication, offsets, producer idempotency, replay, ordering, retention.
- **Object storage:** versioning, replication, backup, lifecycle, quyền xóa và encryption keys.
- **Search index:** có thể tái dựng từ source hoặc phải giữ snapshot nếu rebuild quá lâu.
- **Cache:** có thể coi là disposable nếu không chứa state duy nhất; cần ước tính tải cold-start sau failover.
- **Session:** xác định điều gì được khôi phục, điều gì buộc người dùng đăng nhập lại.

Nếu cache được khởi tạo lại và hàng triệu request đồng thời miss database ngay sau DR, hệ thống có thể không đạt RTO dù tất cả service đều đã Running. Cần capacity cho warm-up, throttling và khởi động tăng dần.

## 14. Phụ thuộc ẩn có thể phá hủy mục tiêu DR

Một site dự phòng hoạt động trên sơ đồ chưa chắc hoạt động khi xảy ra sự cố. Những điểm thiếu thường gặp:
- Registry chứa container image chỉ có tại region chính.
- Certificate/key được lưu trong key management service không còn truy cập được.
- Secret manager hoặc IAM role không được thiết lập cho region dự phòng.
- DNS phụ thuộc provider bị lỗi; TTL không đồng nghĩa client đổi endpoint tức thì.
- CDN/WAF rules hoặc gateway config chưa được đồng bộ.
- Database restore cần version engine/plugin không có tại vùng dự phòng.
- Job scheduler đang chạy ở hai nơi và tạo thanh toán trùng.
- External payment callback chỉ trỏ về region cũ.
- Nhóm SRE không có quyền break-glass hoặc phương tiện truy cập khi provider IAM lỗi.
- Dashboard và log chỉ tồn tại tại hạ tầng bị mất, làm DR khó quan sát.
- Broker topic và consumer offsets không thể chuyển đúng.
- Data residency/compliance không cho phép đưa dữ liệu sang region mới.

Mỗi phụ thuộc phải có một trong ba phương án: **phục hồi**, **thay thế**, hoặc **tạm loại bỏ bằng degraded mode có chấp nhận nghiệp vụ**. Không yêu cầu một service phụ chưa khôi phục làm blocker cho mọi nghiệp vụ nếu thiết kế có thể cô lập.

## 15. Luồng xử lý sự cố: HA trước, DR khi vượt ngưỡng

Một quyết định kích hoạt DR cần căn cứ vào severity, failure domain, dự báo thời gian khôi phục và hậu quả dữ liệu. Không phải mọi lỗi 500 đều cần failover region; failover nóng vội có thể gây mất dữ liệu hoặc tạo split-brain.

~~~mermaid
flowchart TD
    A[Phát hiện gián đoạn] --> B{Lỗi nằm trong phạm vi HA?}
    B -- Có --> C[Thử self-healing/failover thông thường]
    C --> D{Đã phục hồi service SLO?}
    D -- Có --> E[Theo dõi, ghi incident, khắc phục nguyên nhân]
    D -- Không --> F[Đánh giá severity, RTO, RPO, tính toàn vẹn]
    B -- Không --> F
    F --> G{DR được kích hoạt?}
    G -- Chưa --> H[Giảm tải/degrade, khắc phục có thời hạn]
    H --> F
    G -- Có --> I[Fence nguồn ghi cũ, chọn recovery point]
    I --> J[Khôi phục dữ liệu và dependencies]
    J --> K[Chuyển traffic, smoke test, đối soát]
    K --> L{Nghiệp vụ đạt tiêu chí?}
    L -- Không --> M[Xử lý/điều chỉnh trong incident]
    M --> K
    L -- Có --> N[Thông báo khôi phục, giám sát, lên kế hoạch failback]
~~~

Sơ đồ là luồng quyết định khái niệm. Tổ chức phải có tiêu chí kích hoạt và người có thẩm quyền. Với tình huống data corruption hoặc tấn công, cần giữ bằng chứng, cô lập tác nhân và chọn bản khôi phục sạch, thay vì chỉ chuyển traffic sang replica đang chứa cùng dữ liệu lỗi.

## 16. Thiết kế một runbook DR có thể thực thi

Một runbook không nên chỉ ghi “chuyển sang region B”. Cần thông tin để người không trực tiếp xây hệ thống vẫn có thể thực hiện các bước được cấp quyền.

**Mẫu runbook:**

| Phần | Nội dung cần chuẩn bị |
| --- | --- |
| Phạm vi | Quy trình nghiệp vụ và service cần phục hồi; điều kiện loại trừ |
| Mục tiêu | RTO, RPO, acceptable degraded mode |
| Kích hoạt | Định nghĩa sự cố; người ra quyết định; đường escalation |
| Liên hệ | Incident commander, service owners, security, DBA, đối tác |
| Kiểm soát ghi | Fencing/quy trình ngắt writer cũ, chống split-brain |
| Recovery point | Backup/replica đã được chọn, timestamp/version và bằng chứng tính toàn vẹn |
| Phụ thuộc | Thứ tự phục hồi IAM, network, key, data, broker, API |
| Thao tác | Lệnh/sơ đồ automation, preconditions, nơi lấy artifact/config |
| Validation | Smoke test, reconciliation, business probes, dashboard |
| Rollback quyết định | Khi nào dừng cutover, khi nào quay lại, rủi ro dữ liệu |
| Truyền thông | Cập nhật nội bộ/khách hàng, thời gian và trạng thái |
| Evidence | Mốc thời gian, quyết định, dữ liệu mất thực tế, thay đổi |
| Failback | Đồng bộ ngược, kiểm tra dữ liệu, cutover về vị trí mong muốn |

Tài liệu phải giữ ở nơi truy cập được **khi region hoặc SSO chính bị lỗi**. Đường break-glass, contact tree và quyền thực thi cần được kiểm tra định kỳ, đồng thời lưu an toàn để không lộ credential.

### 16.1. Mốc thời gian cần ghi

`T_detect`: phát hiện bất thường.

`T_declare`: quyết định kích hoạt DR.

`T_fence`: nguồn ghi cũ được vô hiệu theo policy.

`T_restore_start`: bắt đầu khôi phục.

`T_traffic`: chuyển traffic vào môi trường dự phòng.

`T_business_ok`: quy trình nghiệp vụ chính đã hoạt động đủ tiêu chí.

`T_last_durable`: điểm dữ liệu cuối có thể chứng minh bền vững/nhất quán.

Để tính RTO thực tế, phải thống nhất mốc bắt đầu (thường từ thời điểm gián đoạn ảnh hưởng nghiệp vụ hoặc sự kiện theo BIA) và mốc kết thúc `T_business_ok`, không chỉ đo thời gian một script restore chạy. RPO thực tế dựa trên chênh lệch giữa mốc sự cố và `T_last_durable` có thể dùng, có điều chỉnh theo trường hợp restore logic/corruption.

## 17. Failover và failback không đối xứng

**Failover** thường được tối ưu theo tốc độ: cô lập primary, chọn replica/backup hợp lệ, mở service dự phòng, điều hướng traffic.

**Failback** có thể kéo dài hơn vì trong thời gian standby phục vụ, dữ liệu mới đã được ghi ở đó. Không thể chỉ “bật lại primary” nếu trạng thái cũ kém mới hơn.

Một quy trình failback an toàn:
1. Xác nhận môi trường chính ổn định và nguyên nhân thảm họa đã được khắc phục.
2. Đánh giá nơi đang là authority cho dữ liệu và writer.
3. Đồng bộ dữ liệu theo hướng đúng, kiểm tra conflict và consistency.
4. Khôi phục replication/backup/monitoring ở trạng thái mong muốn.
5. Thử nghiệm read-only hoặc traffic nhỏ có kiểm soát.
6. Thực hiện fencing/cutover để không tạo hai writer đồng thời.
7. Chạy smoke test, business reconciliation và theo dõi sau chuyển.
8. Cập nhật tài liệu, chủ sở hữu và trạng thái on-call.

Có những trường hợp không cần failback về vùng cũ ngay: vùng dự phòng trở thành primary mới. Quyết định dựa trên rủi ro, chi phí, data location và vận hành dài hạn, không phải thói quen kỹ thuật.

## 18. DR cho event-driven microservices

Event-driven architecture có thể hỗ trợ phục hồi qua event log, nhưng chỉ khi có retention, durability, offset và idempotency phù hợp.

Những câu hỏi cốt lõi:
- Broker có sao chép sang miền độc lập không; những message nào có thể mất theo RPO?
- Consumer offsets được restore ra sao; liệu event được xử lý trùng sau failover?
- Event ordering được bảo đảm trong phạm vi partition/key nào?
- Hệ thống đối tác đã nhận side effect gì trước thảm họa?
- Outbox còn đồng bộ với database đã restore không?
- DLQ có chứa message cần xử lý lại không?
- Có cơ chế kiểm tra schema/version khi consumer mới khởi động?

Ví dụ một event `OrderPaid` đã gửi email nhưng database order khôi phục về mốc trước event. Replay event nếu không có idempotency có thể gửi email hai lần hoặc tạo nghiệp vụ lặp. Dùng business ID, deduplication store, idempotency key và reconciliation với nguồn thanh toán; không dựa vào giả định “exactly once” trên toàn bộ ranh giới dịch vụ.

Khi phục hồi broker, cần xác định liệu consumer nên replay từ snapshot offset hay từ một timestamp, và hậu quả khi event tồn tại nhưng state database chưa đồng nhất. Runbook phải chỉ ra cách chuyển sang trạng thái phục vụ an toàn trước khi mở traffic và xử lý backlog.

## 19. DR cho cơ sở dữ liệu: restore không chỉ là khởi động lại

Ví dụ hệ thống lưu đơn hàng trong PostgreSQL:
- Có snapshot định kỳ và WAL archiving để hỗ trợ point-in-time recovery (PITR).
- Bản sao dữ liệu và WAL ở vùng dự phòng phù hợp yêu cầu bảo vệ.
- Khóa giải mã và quyền restore được kiểm soát.
- Script phục hồi tạo database ở trạng thái cô lập, không cho app ghi trước khi xác minh.
- DBA/application owner chọn recovery target trước hoặc sau thao tác lỗi tùy mục đích.
- Service kiểm tra schema, extension, migrations, dữ liệu và khả năng kết nối.
- Sau xác nhận, gateway mới mở traffic.

PITR không tự đảm bảo business consistency giữa các database riêng. Ví dụ payment record ở service A và order state ở service B có thể khác thời điểm. Cần reconciliation theo transaction IDs, event sequence và audit log.

**Không thử restore production backup trực tiếp vào môi trường mà người dùng thật đang ghi**, trừ khi đó là quy trình phục hồi đã được kiểm soát và được ủy quyền. Bài diễn tập nên dùng môi trường cô lập và dữ liệu được bảo vệ.

## 20. Backup bảo vệ khỏi mã độc và lỗi vận hành

DR không chỉ đối phó thiên tai hoặc cloud outage. Nhiều thảm họa đến từ xóa nhầm, deployment sai và tấn công có chủ đích.

Một backup strategy đáng tin nên có:
1. **Đa bản sao và đa miền lỗi:** tránh tất cả backup cùng account/region/quyền xóa.
2. **Tính bất biến hoặc bảo vệ xóa:** chính sách retention phù hợp và quyền ghi/xóa tách biệt.
3. **Versioning/PITR:** nhiều mốc khôi phục để tránh bản sao chỉ chứa trạng thái đã hỏng.
4. **Mã hóa và khóa khôi phục:** lưu key theo quy trình an toàn, kiểm tra có thể giải mã sau sự cố.
5. **Cô lập mạng và IAM:** hạn chế đường để tài khoản production bị chiếm xóa cả backup.
6. **Kiểm tra tính toàn vẹn:** checksum/restore verification, business data checks.
7. **Diễn tập restore định kỳ:** tính thời gian thực và ghi evidence.
8. **Chính sách retention/khôi phục theo pháp lý:** không sao chép dữ liệu tùy tiện sang nơi không được phép.

Nếu attacker có quyền sửa hoặc xóa cả backup, “có backup” chưa phải phương án phục hồi. Bản sao chống sửa, tài khoản độc lập và quy trình thử phục hồi giúp giảm rủi ro nhưng cần thiết kế cho cả khóa mã hóa và quyền truy cập.

## 21. Kubernetes: HA và DR ở những mức khác nhau

Kubernetes hỗ trợ self-healing cho workload và một số cơ chế phân tán, nhưng không mặc định cung cấp DR hoàn chỉnh cho mọi tài nguyên.

**HA tại cluster:**
- Deployment có nhiều replica.
- Readiness/liveness/startup probes phù hợp.
- Topology spread qua node/AZ.
- PodDisruptionBudget cho maintenance tự nguyện, không phải bảo đảm chống mọi sự cố.
- Autoscaling và resource headroom.
- HA control plane và storage controller phù hợp nền tảng.
- Database/broker stateful có cơ chế HA riêng.

**DR:**
- Hạ tầng cluster tại vùng dự phòng bằng IaC.
- Artifact image, Helm charts/manifests, policy, CRDs và cấu hình được lưu ở nguồn truy cập được.
- Backup/restore của persistent data và Kubernetes resources cần thiết.
- IAM, secret và encryption key có phương án recovery.
- Ingress/DNS/traffic cutover và monitoring xuyên vùng.
- Quy trình data consistency, tránh double-writer và test runbook.

Kubernetes Deployment có replica=3 không bảo đảm 3 replica nằm ở ba AZ. StatefulSet có nhiều pod không tự bảo đảm dữ liệu nhất quán hay restore point. PersistentVolume replication cũng có thể lan truyền xóa nhầm.

### 21.1. Manifest HA minh họa

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: catalog-service
      containers:
        - name: catalog
          image: registry.example/catalog-service@sha256:<approved-digest>
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
~~~

Đoạn YAML là ví dụ ý tưởng, không phải cấu hình production hoàn chỉnh. Digest là placeholder cần thay bằng giá trị thật; còn thiếu requests/limits, security policy, termination handling, service account, deployment strategy và nhiều kiểm soát khác. Nếu cluster không có đủ AZ/node tương ứng, `DoNotSchedule` có thể làm pod Pending. Cần cân nhắc trade-off giữa topology spread và khả năng schedule.

## 22. Java/Spring Boot: readiness, state và shutdown

Với dịch vụ Java, liveness không nên gắn chặt vào dependency dùng chung đến mức khi database chậm, toàn bộ pod cùng restart gây retry storm. Readiness nên phản ánh khả năng nhận traffic an toàn theo hợp đồng service. Một service đọc catalog từ cache có thể vẫn ready khi recommendation-service lỗi, nhưng checkout có thể không ready nếu payment authorization không hoạt động và không có degraded mode hợp lệ.

Ví dụ cấu hình khái niệm trong Spring Boot:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Tên property và hành vi cần phù hợp phiên bản framework. Cấu hình shutdown không thay thế cho grace period, connection draining và xử lý request dài trong Kubernetes. Không expose chi tiết health nhạy cảm ra internet.

Khi failover, Java runtime có thể mất thời gian JIT warm-up, tạo connection pool và tải cache. Các bước này cần tính vào RTO và readiness, đặc biệt với warm standby có ít tài nguyên. Nếu ứng dụng giữ session hoặc state nghiệp vụ trong process memory, khôi phục pod không đồng nghĩa khôi phục phiên/giao dịch.

## 23. DNS, traffic routing và giới hạn failover tự động

Thay bản ghi DNS là một phần của cutover nhưng không bảo đảm mọi client chuyển ngay vì:
- Resolver có cache và thực tế thời gian sống có thể không đúng lý tưởng.
- Kết nối keep-alive và connection pool giữ endpoint cũ.
- Mobile/desktop client có retry/backoff riêng.
- CDN, edge routing, session pinning và proxy có chính sách riêng.
- Định tuyến toàn cầu có thể không nhận biết data consistency.

Một global load balancer hoặc traffic manager có thể kiểm tra health vùng và chuyển traffic nhanh hơn theo thiết kế, nhưng phải kết nối với **điều kiện dữ liệu đã sẵn sàng và quyền ghi an toàn**. Nếu tự chuyển traffic sang standby trong khi database replica chưa đủ mới hoặc writer cũ chưa được fence, có thể vi phạm RPO hoặc gây split-brain.

Nên đo **thời gian hội tụ traffic** và thực hiện synthetic requests từ nhiều vị trí, thay vì chỉ xác nhận một bản ghi DNS đã được sửa.

## 24. Kinh nghiệm phân biệt qua bốn kịch bản

### Kịch bản A: Một pod hỏng

- **Hiện tượng:** một replica order-service ngừng trả response, các replica khác còn hoạt động.
- **Phương án:** readiness loại endpoint; Deployment tạo pod mới.
- **Phân loại:** HA.
- **Phép đo:** error rate, p95 latency, recovery time, capacity còn lại.
- **DR:** không nên kích hoạt nếu HA đang đáp ứng SLO.

### Kịch bản B: Mất một AZ

- **Hiện tượng:** node và volume thuộc một AZ không sẵn sàng.
- **Phương án:** replica trải nhiều AZ, storage/database HA, load balancer bỏ AZ lỗi.
- **Phân loại:** HA nếu kiến trúc được thiết kế chịu lỗi AZ; có thể cần recovery escalation nếu dữ liệu phụ thuộc AZ đó.
- **Phép đo:** tỉ lệ request lỗi trong failover, khả năng chịu traffic của AZ còn lại, quorum status.

### Kịch bản C: Mất cả region

- **Hiện tượng:** gateway và database cùng region không truy cập được.
- **Phương án:** kích hoạt runbook DR, xác nhận state và data point của region B, fence writer cũ, chuyển traffic, đối soát.
- **Phân loại:** DR; kiến trúc multi-region có thể giảm cutover downtime bằng cơ chế HA xuyên vùng.
- **Phép đo:** RTO/RPO thực tế, business success, data consistency, time-to-traffic.

### Kịch bản D: Xóa nhầm dữ liệu và lan qua replica

- **Hiện tượng:** tất cả replica khỏe nhưng bảng order bị xóa.
- **Phương án:** cô lập write, xác định điểm sạch, PITR/restore, kiểm tra event/outbox và đối soát nghiệp vụ.
- **Phân loại:** DR dữ liệu.
- **Phép đo:** recovery point usable, đơn hàng cần xử lý bù, data loss thực tế, thời gian trở lại phục vụ.
- **HA:** replication không thể tự cứu nếu chính thao tác xóa cũng được replicate.

## 25. Ma trận quyết định theo mục tiêu và failure domain

| Sự cố cần chịu | Tổ hợp giải pháp | Câu hỏi xác minh |
| --- | --- | --- |
| Process crash | Nhiều replica + probes | Tỷ lệ lỗi khi kill một pod là bao nhiêu? |
| Node outage | Replica trên nhiều node + capacity dự phòng | Mất node có kéo dài queue hoặc timeout? |
| AZ outage | Multi-AZ compute, DB và network | Mất AZ vẫn đảm bảo quorum và lưu lượng? |
| Region outage | Cross-region standby/multi-region + cutover | Có đạt RTO/RPO khi vùng chính không truy cập? |
| Corrupt data | Point-in-time backup, immutable recovery points | Có xác định và phục hồi bản sạch không? |
| Ransomware/compromise | Backup cách ly, least privilege, forensic | Tài khoản bị chiếm có thể xóa cả backup/key? |
| Sai deployment diện rộng | Canary/rollback + isolated copies/config | Rollback code có đủ nếu schema bị xóa? |
| External dependency outage | Bulkhead, graceful degradation, fallback | Luồng nào vẫn phục vụ đúng nghiệp vụ? |
| Data center/region failback | Reverse replication, fencing, reconciliation | Không tạo hai writer và không mất update mới? |

Ma trận không có nghĩa chỉ cần chọn một ô là hệ thống “đã sẵn sàng”. Cần đo end-to-end và xem failure domain của những thành phần chung như IAM, DNS và management plane.

## 26. Kiểm chứng HA bằng fault injection có kiểm soát

Đo HA không chỉ bằng việc nhìn pod replica count. Một chương trình thử nghiệm có thể:
1. Đặt baseline thông lượng, p95/p99, error rate, capacity còn lại.
2. Xóa một pod, dừng một node test hoặc mô phỏng network latency có kiểm soát.
3. Quan sát load balancer, readiness, retries, circuit breaker và sự chuyển tải.
4. Kiểm tra request đang xử lý có thất bại hoặc bị thực hiện hai lần không.
5. Ghi thời gian từ lỗi tới khi SLI trở lại bình thường.
6. Đánh giá tài nguyên còn lại dưới giờ cao điểm giả lập.
7. Đảm bảo hệ thống tự trở về trạng thái vận hành cân bằng.

Với database failover, đo không chỉ thời điểm election kết thúc mà còn **thời điểm ứng dụng kết nối lại và ghi nghiệp vụ thành công**. Một client có DNS/connection pool cũ có thể tiếp tục lỗi dù database primary mới đã lên.

Test fault injection nên diễn ra ở môi trường phù hợp, có quyền và biện pháp giới hạn tác động; tránh phá production nếu không có kế hoạch được phê duyệt.

## 27. Kiểm chứng DR bằng game day và recovery drill

Khác với test HA, diễn tập DR phải xác nhận rằng **quy trình điều phối và con người** thực hiện được phương án khi điều kiện bình thường không còn.

Một drill đầy đủ:
1. Chọn kịch bản (mất region, corrupt database, mất backup key, mất broker...).
2. Chốt RTO/RPO, điều kiện thành công, người quyết định và giới hạn test.
3. Dựng tình huống trong môi trường an toàn hoặc vùng phục hồi cô lập.
4. Bắt đầu đồng hồ theo mốc đã thống nhất.
5. Đánh giá và tuyên bố DR; thực hiện fencing nếu có writer.
6. Khôi phục IAM/key, network, database, broker và application theo dependency order.
7. Chuyển traffic tổng hợp/test traffic, chạy smoke và business reconciliation.
8. Ghi `T_business_ok`, điểm dữ liệu cuối phục hồi và mọi sai lệch.
9. Thử failback hoặc giữ trạng thái dự phòng như primary tùy phạm vi drill.
10. Retrospective và cập nhật runbook, automation, owner, danh sách phụ thuộc.

**Không đánh dấu hoàn tất chỉ vì script restore thoát code 0.** Cần thực hiện được giao dịch nghiệp vụ mẫu, đọc/ghi dữ liệu đúng, xác minh event, secret, auth và hệ thống quan sát.

### 27.1. Những biến số drill nên thay đổi theo kỳ

- Người vận hành khác nhau chạy runbook; không chỉ tác giả script.
- Không có quyền truy cập máy chủ chính hoặc SSO chính.
- Backup gần nhất bị hỏng; phải chọn recovery point trước.
- Replication lag cao hơn thông thường.
- Standby thiếu capacity, phải scale.
- Một dependency ngoài vùng không khả dụng.
- Event replay tạo duplicate; phải xử lý idempotency.
- DNS chuyển chậm và client còn kết nối cũ.
- Đã failover, sau đó cần failback với dữ liệu mới.

Một DR plan chưa từng diễn tập là giả định kiến trúc, không phải năng lực đã chứng minh.

## 28. Đo lường và theo dõi HA/DR

### 28.1. HA metrics

- Successful request ratio, error rate, latency p95/p99.
- Số replica ready/desired, số node available, số AZ đang phục vụ.
- Thời gian failover của database, số lần primary switch, replication lag.
- Queue depth/consumer lag sau một failover.
- Requests retry, timeout, circuit breaker events.
- Capacity headroom và saturation sau khi mất một phần hạ tầng.
- Tỷ lệ giao dịch nghiệp vụ hoàn tất, không chỉ HTTP status.

### 28.2. DR metrics

- Thời gian detect, declare, restore, traffic cutover và business recovery.
- RTO thực đo theo quy trình nghiệp vụ.
- RPO thực đo theo recovery point usable và tính nhất quán dữ liệu.
- Tuổi của backup gần nhất, backup success và restore test success.
- Replication lag theo vùng và tình trạng snapshot/WAL.
- Số service/dependency đã recovery so với danh sách bắt buộc.
- Dữ liệu/công việc phải replay, reconcile hoặc xử lý thủ công.
- Thời gian failback và sự cố phát sinh trong failback.
- Tuổi runbook, thời điểm drill cuối và các blocker chưa giải quyết.

**Đo availability liên tục không thay cho DR drill.** Một hệ thống không có downtime sáu tháng có thể vẫn thiếu khả năng restore khi bị xóa dữ liệu. Ngược lại, một restore test thành công không chứng minh khả năng chịu lỗi thường nhật dưới tải cao.

## 29. Quan hệ giữa HA, DR và chi phí

Thiết kế tốt là lựa chọn **mức bảo vệ theo mức độ quan trọng của nghiệp vụ**:

- Tăng replica từ 1 lên 3 giúp giảm nhiều lỗi đơn lẻ, nhưng làm tăng chi phí compute và chưa khắc phục lỗi dữ liệu chung.
- Multi-AZ tăng độ bền trước mất AZ, có thể tăng phí mạng/storage và yêu cầu quorum.
- Cross-region replication thêm chi phí truyền dữ liệu, storage và operational complexity.
- Warm standby giữ capacity sẵn, đổi lại chi phí duy trì hàng ngày.
- Active-active có thể giảm gián đoạn nhưng làm khó consistency, data locality và conflict resolution.
- Backup sâu và immutable tăng storage cost, nhưng là lớp thiết yếu để phục hồi khỏi corruption/tấn công.

Mục tiêu không phải “luôn chọn chiến lược đắt nhất”. Có thể service notification chỉ cần queue bền và replay trong vài giờ, còn payment cần kiểm soát dữ liệu nghiêm ngặt với RPO thấp và reconciliation tốt. Đầu tư nên dựa trên Business Impact Analysis (BIA), rủi ro và evidence từ drill.

## 30. Case study: hệ thống đặt hàng đa dịch vụ

Giả sử một hệ thống có:
- `catalog-service`: thông tin sản phẩm, cache được.
- `inventory-service`: reserve tồn kho, dữ liệu giao dịch.
- `order-service`: tạo, cập nhật đơn hàng.
- `payment-service`: gọi đối tác thanh toán.
- `notification-service`: gửi email/SMS qua event.
- PostgreSQL từng service, Kafka cho event, Redis làm cache.

### 30.1. HA khi một pod order-service lỗi

Các replica order-service còn lại tiếp tục nhận request. Readiness và load balancer loại instance hỏng, HPA/scheduler khôi phục capacity. Các request đang dang dở phải dùng idempotency key ở create-order để retry không tạo đơn trùng.

Những câu hỏi đo: bao nhiêu request bị lỗi? Thời gian trở lại p95 bình thường? Database pool có bị bão hòa do retry không? Notification có bị lặp?

### 30.2. HA khi primary database lỗi

Database tự failover sang standby theo chính sách. Order-service reconnect và xử lý retry idempotent. Nhóm kiểm tra acknowledged writes có bị mất không và transaction có còn nhất quán sau bầu primary. Nếu RPO thực tế của database không đáp ứng cam kết, phải điều chỉnh replication/commit semantics chứ không chỉ tăng replica ứng dụng.

### 30.3. DR khi cả region chính mất

Region dự phòng có compute, network, IAM, image, secret, database recovery và Kafka strategy. Incident commander kích hoạt runbook:
1. Cô lập writer cũ hoặc xác nhận điều kiện fencing.
2. Chọn recovery point dùng được cho các database.
3. Phục hồi order/inventory/payment cùng metadata cần thiết.
4. Kiểm tra outbox/Kafka offset, event trùng và giao dịch với đối tác.
5. Khởi động các service theo phụ thuộc.
6. Kiểm tra đặt hàng/đặt chỗ/thanh toán qua synthetic scenario và đối soát.
7. Chuyển traffic thật theo policy, theo dõi SLI.
8. Ghi RTO, RPO và các giao dịch phải bù hoặc xử lý thủ công.

Catalog có thể mở lại từ bản cache/read model tương đối cũ với giới hạn rõ, nhưng checkout không được chấp nhận thanh toán chỉ dựa trên dữ liệu giá hoặc tồn kho đã quá hạn.

### 30.4. DR khi dữ liệu bị xóa sai

Một migration xóa nhầm bảng `orders`, sau đó replica cũng nhận lệnh. Nhóm cô lập ghi, xác định mốc trước migration, dùng PITR để phục hồi order DB vào môi trường an toàn, rồi reconciliation với payment/inventory và event logs. Có thể phải xử lý các giao dịch xuất hiện sau mốc phục hồi.

Không giải quyết bằng cách chỉ “chuyển sang replica”, vì replica có thể chứa cùng trạng thái đã xóa. Đây là ví dụ rõ về **replication giúp HA nhưng không thay thế backup/DR**.

## 31. Những ngộ nhận phổ biến

### “Có ba replica nên không cần DR”

Ba replica trong một cluster có thể cùng mất vì region outage, sai cấu hình, credential bị thu hồi hoặc DB corruption. Cần nhìn failure domain và dữ liệu.

### “Có backup nên hệ thống HA”

Backup cho khả năng phục hồi ở tương lai, không tự chuyển traffic khi pod/node lỗi. Thời gian restore có thể vượt availability SLO.

### “Multi-AZ nghĩa là multi-region”

AZ và region là các miền lỗi khác nhau. Multi-AZ giảm một lớp rủi ro nhưng không tự chống mất region.

### “Sao chép đồng bộ thì luôn RPO = 0”

Phải hiểu chính xác nơi commit được xác nhận, durability và quorum. Backup/restore của nhiều database và tác động ngoài vẫn có thể mất consistency.

### “Có replication nên không cần backup”

Thao tác xóa, corruption hoặc encryption độc hại có thể được replicate. Cần bản khôi phục tại thời điểm sạch với quyền/retention an toàn.

### “Active-active tự động có cả HA và DR hoàn chỉnh”

Active-active cần conflict resolution, định tuyến, capacity, consistency, bảo mật và recovery khỏi logic corruption. Nếu cả hai vùng dùng chung hạ tầng kiểm soát hoặc cùng lỗi code, cả hai vẫn có thể mất.

### “RTO là thời gian pod khởi động”

RTO phải được đo tới lúc quy trình nghiệp vụ đáp ứng tiêu chí đã định, gồm dữ liệu, mạng, identity, routing, warm-up và kiểm chứng.

### “Restore backup thành công nghĩa là dữ liệu đúng”

Cần business validation, referential consistency, reconcile event/payment và kiểm tra recovery point.

### “Chuyển DNS một lần là xong”

Client caches, connection pools, replication và writer fencing có thể kéo dài hoặc làm sai cutover.

### “Khi chính quay lại chỉ cần chuyển traffic về”

Failback cần đồng bộ trạng thái mới, tránh hai writer và kiểm tra nghiệp vụ. Có thể phức tạp hơn failover.

## 32. Checklist thiết kế cho một microservice

Trước khi tuyên bố service đủ HA hoặc DR, nhóm nên trả lời:

1. Service xử lý nghiệp vụ nào, owner là ai và người dùng bị ảnh hưởng thế nào?
2. Availability SLO/SLI được định nghĩa và đo từ đâu?
3. RTO/RPO của quy trình nghiệp vụ là bao nhiêu; ai phê duyệt?
4. Những failure domain nào được HA bảo vệ: process, node, AZ, database instance?
5. Replica có thực sự nằm ở các failure domain khác nhau không?
6. Tài nguyên còn lại có capacity chịu tải khi một AZ hoặc instance biến mất?
7. Data tier có quorum, failover và cơ chế fencing đúng không?
8. Backup có được lưu cách ly, bảo vệ xóa và thử restore định kỳ?
9. RPO thực tế có được đo từ recovery point usable thay vì chỉ lịch backup?
10. DR region có registry, IAM, secret, key, DNS và network đầy đủ?
11. Phụ thuộc bên thứ ba có kế hoạch khi không sẵn sàng?
12. Có bản đồ thứ tự khôi phục giữa database, broker, services và gateway?
13. Event replay có idempotency và khả năng reconciliation?
14. Ai kích hoạt DR, ai dừng writer cũ, ai phê duyệt mở traffic?
15. Có bản runbook dùng được khi SSO hoặc vùng chính hỏng?
16. DR drill gần nhất có đạt RTO/RPO và business smoke test?
17. Có phương án failback an toàn, tránh split-brain và mất dữ liệu mới?
18. Những phát hiện sau drill được theo dõi đến khi khắc phục chưa?

Checklist là điểm khởi đầu cho trao đổi giữa service team, platform, SRE, DBA, security và nghiệp vụ, không phải sự chứng nhận đạt tiêu chuẩn.

## 33. Bài tập thực hành

### Bài 1 — Phân loại sự cố

Với từng tình huống, hãy chọn HA, DR hoặc phối hợp cả hai, giải thích phạm vi lỗi và phép đo cần quan sát:

1. Một pod Java hết memory và tự restart.
2. Mất một AZ nhưng cluster và database trải trên ba AZ.
3. Primary database hỏng, standby có lag vài giây.
4. Region chính mất kết nối toàn bộ.
5. Admin chạy script xóa dữ liệu và lệnh được replicate.
6. Ứng dụng deploy bug xuống cả hai vùng active-active.
7. Nhà cung cấp thanh toán không nhận request trong hai giờ.
8. Khóa giải mã dữ liệu production và backup không truy cập được.

Không chỉ viết nhãn; phải chỉ ra **khi nào cơ chế HA thất bại**, **tài nguyên nào cần phục hồi** và **hậu quả dữ liệu**.

### Bài 2 — Thiết kế RTO/RPO

Một hệ thống checkout có SLO availability 99,95% theo request trong 30 ngày. Nghiệp vụ yêu cầu có thể mở lại nhận đơn trong 30 phút sau mất region, và mất tối đa 60 giây dữ liệu đã xác nhận.

Hãy:
1. Xác định availability SLO, RTO và RPO là những đại lượng khác nhau.
2. Thiết kế region dự phòng theo ít nhất hai chiến lược và nêu trade-off.
3. Giải thích có thể đáp ứng RPO 60 giây thế nào bằng replication/backup và cách kiểm chứng.
4. Định nghĩa điều kiện `business_ok` để kết thúc đồng hồ RTO.
5. Chọn phương án bảo vệ acknowledged payment khỏi nhân đôi hoặc mất đối soát.
6. Mô tả thứ tự phục hồi IAM, database, broker, services, gateway.
7. Xác định điều kiện fencing cần thiết trước khi writer standby hoạt động.

### Bài 3 — Phân tích số liệu drill

Một diễn tập giả định có timeline:
- 09:00: traffic sản xuất bắt đầu lỗi do vùng chính không khả dụng.
- 09:04: hệ thống phát hiện đủ bằng chứng.
- 09:10: incident commander kích hoạt DR.
- 09:14: nguồn ghi cũ được fence theo cơ chế đã xác nhận.
- 09:18: bắt đầu restore.
- 09:34: database, broker và service đã khởi động.
- 09:40: chuyển traffic vào vùng dự phòng.
- 09:46: giao dịch nghiệp vụ mẫu và SLI quan trọng đạt tiêu chí.
- Dữ liệu cuối cùng có thể phục hồi nhất quán là 08:58:45.

Theo mốc sự cố 09:00, **thời gian từ gián đoạn đến `business_ok` là 46 phút**. Điểm khôi phục lùi **75 giây** so với 09:00. Nếu RTO mục tiêu 30 phút và RPO mục tiêu 60 giây thì drill này chưa đạt cả hai mục tiêu. Nên phân tích từng giai đoạn và nguyên nhân chậm, không che phần thời gian detect/declare bằng việc chỉ báo “restore mất 16 phút”.

Các số liệu là giả định phục vụ bài tập; trong hệ thống thực, cần xác định thời điểm data loss cuối từ log/transaction thực và kiểm tra dữ liệu được phục hồi chính xác.

### Bài 4 — Khác biệt giữa HA và DR cho PostgreSQL

Giả sử primary ở AZ A, standby ở AZ B, snapshot sao lưu hàng ngày trên cùng tài khoản cloud, không có region dự phòng.

Hãy:
- Liệt kê lỗi được bảo vệ và lỗi chưa được bảo vệ.
- Đề xuất thay đổi backup nhằm giảm rủi ro xóa/corruption lan rộng.
- Ước lượng những yếu tố quyết định RTO khi phục hồi sang region mới.
- Giải thích trường hợp replication lag làm RPO khác 0.
- Đề xuất cách đo data consistency sau restore.
- Thiết kế một drill không ảnh hưởng dữ liệu thật.

### Bài 5 — Phương án multi-region cho order-service

Thiết kế sơ đồ order-service kết hợp inventory, payment và message broker:
- HA trên mỗi region/cluster.
- Vùng chính/vùng dự phòng hoặc active-active có mô hình writer rõ.
- Backup immutable tách khỏi replication.
- Event outbox và idempotency.
- Định tuyến failover, cách fence, kiểm chứng business.
- Quy trình failback và reconciliation.
- Dashboard HA và kết quả DR drill.

Kết quả phải mô tả được trường hợp **mất vùng**, **xóa dữ liệu**, và **khôi phục khi có giao dịch dang dở**, không chỉ vẽ số lượng replica.

## 34. Câu hỏi tự kiểm tra

1. Vì sao một hệ thống HA tốt vẫn cần kế hoạch DR?
2. Backup phục vụ mục tiêu nào khác replication?
3. RTO đo đến lúc nào: process chạy, API 200 hay nghiệp vụ thực sự dùng được?
4. RPO 5 phút có đồng nghĩa đặt cron backup 5 phút/lần không?
5. Một môi trường active-active có thể mất dữ liệu hoặc gây double-writer trong điều kiện nào?
6. AZ, region, IAM và data integrity là những failure domain khác nhau ra sao?
7. Vì sao graceful degradation có thể tăng availability nhưng không giải quyết DR?
8. Sự khác biệt giữa failover và failback quan trọng nhất ở đâu?
9. Trong microservices, database restore độc lập có thể gây bất nhất business như thế nào?
10. Event replay sau disaster có nguy cơ nhân đôi side effects ra sao?
11. Khi nào nên ưu tiên warm standby thay vì active-active?
12. Tại sao phải kiểm tra artifact registry, KMS và DNS trong DR drill?
13. Nếu khách hàng thấy lỗi nhưng pod Ready, availability SLI nên đo ra sao?
14. Tại sao không nên kích hoạt DR ngay cho mọi lỗi 500?
15. Bằng chứng nào chứng minh một runbook thực sự đạt RTO/RPO?

## 35. Tổng kết

**HA và DR phục vụ hai lớp mục tiêu khác nhau.** HA giúp duy trì hoạt động khi những thành phần được dự phòng hỏng và giảm tác động của sự cố thường ngày. DR chuẩn bị cho tình huống một phần lớn hệ thống hoặc dữ liệu không còn khả dụng/đáng tin, và tập trung khôi phục **đúng chức năng, đúng dữ liệu, đúng thời hạn**.

Trong microservices, HA bắt đầu từ phân tán replica, health check, capacity headroom, database quorum và thiết kế giảm phụ thuộc dây chuyền. DR cần phân tích ảnh hưởng nghiệp vụ, RTO/RPO, backup có thể restore, miền lỗi độc lập, data consistency, kế hoạch chuyển vùng, kiểm soát writer, event replay, runbook và diễn tập.

Không thể thay RTO/RPO bằng con số uptime và cũng không thể thay HA bằng backup. Kiến trúc đáng tin cậy kết hợp cả hai, xác định rõ lỗi nào được chịu đựng tự động, lỗi nào cần phối hợp khôi phục và cách **kiểm chứng end-to-end bằng giao dịch nghiệp vụ thật trong môi trường diễn tập an toàn**.
