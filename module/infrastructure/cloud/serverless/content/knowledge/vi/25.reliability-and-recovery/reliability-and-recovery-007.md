# Phân tích khả năng chịu lỗi vùng sẵn sàng và vùng địa lý

Một ứng dụng serverless có thể tự động mở rộng và được vận hành trên hạ tầng do nhà cung cấp quản lý, nhưng điều đó không có nghĩa ứng dụng tự động chịu được mọi sự cố hạ tầng. Function có thể chạy lại ở execution environment khác, trong khi database, queue, cache, network route hoặc secret store mà nó phụ thuộc vẫn có thể nằm trong một failure domain duy nhất. Khi một vùng hạ tầng gặp sự cố, toàn bộ luồng nghiệp vụ có thể dừng dù code function không thay đổi.

Thiết kế chịu lỗi cần hiểu rõ hai cấp độ địa lý thường gặp: **Availability Zone (AZ)** và **Region**. Multi-AZ giúp hệ thống tiếp tục hoạt động khi một vùng sẵn sàng trong Region bị lỗi. Multi-Region giúp duy trì dịch vụ khi cả Region gặp sự cố, nhưng kéo theo bài toán định tuyến, sao chép dữ liệu, consistency, quyền ghi và phục hồi phức tạp hơn.

Trong module **CLOUD_SERVERLESS**, người học phát triển Java function kích hoạt bởi HTTP, message hoặc event, đồng thời xử lý trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí. Bài này phân tích cách xây dựng khả năng chịu lỗi ở cấp AZ và Region, xác định RTO/RPO, chọn mô hình active-passive hoặc active-active và kiểm thử quy trình failover/failback.

## 1. Failure domain là gì?

Failure domain là một phạm vi hạ tầng có thể bị ảnh hưởng bởi cùng một sự cố. Nếu nhiều thành phần cùng phụ thuộc vào một failure domain, một sự cố tại đó có thể làm chúng ngừng hoạt động đồng thời.

Các failure domain thường gặp:

- **Process/runtime:** một JVM, execution environment hoặc container bị crash.
- **Instance/host:** máy chủ vật lý hoặc máy ảo gặp lỗi.
- **Rack/network segment:** nguồn điện, switch hoặc tuyến mạng cục bộ gặp sự cố.
- **Availability Zone:** một vùng hạ tầng độc lập tương đối trong một Region.
- **Region:** một khu vực địa lý chứa nhiều AZ và dịch vụ cloud.
- **Global service/control plane:** DNS, identity provider, control plane, CDN hoặc dịch vụ quản lý dùng chung gặp sự cố.
- **External dependency:** payment provider, email gateway, SaaS hoặc mạng đối tác không sẵn sàng.

Một hệ thống có nhiều function instance nhưng tất cả đều ghi vào cùng một database single-AZ vẫn có một failure domain tập trung. Tăng số instance không loại bỏ điểm lỗi đó.

~~~mermaid
flowchart TD
    G[Global entry / DNS] --> R[Cloud Region]
    R --> A[Availability Zone A]
    R --> B[Availability Zone B]
    R --> C[Availability Zone C]
    A --> F1[Function execution]
    A --> D1[Database node]
    B --> F2[Function execution]
    B --> D2[Database standby]
    C --> F3[Function execution]
    C --> Q[Queue / storage]
    G --> X[External identity / payment]
~~~

Sơ đồ chỉ minh họa cách phân chia phạm vi. Một dịch vụ serverless managed có thể tự phân tán execution environment, nhưng phạm vi HA và replication của từng dịch vụ phụ thuộc cấu hình, loại dịch vụ và cam kết của provider.

## 2. Availability Zone và Region khác nhau thế nào?

**Availability Zone** là một vùng hạ tầng riêng biệt trong một Region. Các AZ thường được thiết kế để giảm tương quan lỗi về nguồn điện, mạng và cơ sở vật chất, đồng thời kết nối với nhau bằng mạng có độ trễ thấp. Mức độ độc lập cụ thể và cách provider đặt tên AZ khác nhau.

**Region** là một khu vực địa lý lớn, thường chứa nhiều AZ. Các Region thường cách nhau xa hơn, có failure domain và kết nối mạng riêng. Khoảng cách địa lý giúp giảm rủi ro một sự cố cục bộ ảnh hưởng đồng thời, nhưng tăng latency và độ phức tạp khi sao chép dữ liệu.

| Tiêu chí | Multi-AZ | Multi-Region |
|---|---|---|
| Phạm vi bảo vệ | Sự cố một AZ hoặc thành phần zonal | Sự cố diện rộng của một Region |
| Network latency | Thường thấp hơn giữa các AZ | Thường cao hơn giữa các Region |
| Data replication | Có thể đồng bộ hoặc managed trong Region | Thường cần replication liên vùng |
| RPO | Có thể gần 0 với một số cấu hình đồng bộ | Phụ thuộc replication lag và mô hình ghi |
| RTO | Thường ngắn hơn nếu failover tự động | Có thể dài hơn do promote, routing và kiểm tra |
| Chi phí | Thêm replica/capacity và traffic liên AZ | Thêm stack, replication, egress và vận hành |
| Độ phức tạp | Vừa phải | Cao hơn đáng kể |
| Trường hợp dùng | HA cho sự cố hạ tầng cục bộ | DR cho sự cố Region, yêu cầu địa lý hoặc residency |

Không nên giả định tên AZ giống nhau giữa các account hoặc tenant nếu provider có ánh xạ AZ khác nhau. Dùng cơ chế placement/zone ID được provider hỗ trợ thay vì hardcode tên suy đoán.

## 3. HA, fault tolerance và disaster recovery

Ba khái niệm liên quan nhưng có mục tiêu khác nhau:

- **High Availability (HA):** giảm thời gian dịch vụ không sẵn sàng bằng redundancy, health check và failover.
- **Fault tolerance:** tiếp tục cung cấp một phần hoặc toàn bộ chức năng khi một thành phần lỗi, thường nhờ replication và thiết kế loại bỏ single point of failure.
- **Disaster Recovery (DR):** khôi phục dịch vụ và dữ liệu sau sự cố lớn, ví dụ mất cả Region, lỗi dữ liệu diện rộng hoặc mất quyền truy cập vào môi trường chính.

Multi-AZ thường là nền tảng cho HA trong một Region. Multi-Region thường được dùng cho DR hoặc yêu cầu phục vụ người dùng ở nhiều địa lý. Một kiến trúc active-active nhiều Region cũng có thể phục vụ HA, nhưng chỉ khi dữ liệu và quyền ghi được thiết kế phù hợp.

Không đồng nhất HA với backup. Replica có thể sao chép cả thao tác xóa nhầm hoặc dữ liệu bị hỏng; backup cho phép khôi phục về một điểm trước sự cố. Hệ thống quan trọng thường cần cả replication lẫn backup độc lập.

## 4. Xác định RTO và RPO

Trước khi chọn kiến trúc, cần xác định hai mục tiêu phục hồi:

- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận để khôi phục dịch vụ sau sự cố.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận mất, thường biểu diễn bằng khoảng thời gian dữ liệu.

Ví dụ, nếu RTO là 15 phút, dịch vụ cần trở lại mức hoạt động chấp nhận được trong vòng 15 phút. Nếu RPO là 1 phút, hệ thống chấp nhận mất tối đa khoảng một phút dữ liệu mới nhất trong kịch bản được định nghĩa.

RTO/RPO phải được đặt theo nghiệp vụ, không chọn chỉ dựa trên tính năng cloud.

| Loại workload minh họa | RTO mục tiêu | RPO mục tiêu | Hướng kiến trúc có thể xem xét |
|---|---:|---:|---|
| Báo cáo nội bộ ít quan trọng | Vài giờ | Vài giờ | Backup và restore |
| API nghiệp vụ thông thường | 30–60 phút | 5–15 phút | Warm standby, replication bất đồng bộ |
| Thanh toán/đặt hàng trọng yếu | Vài phút | Gần 0 đến vài giây theo khả năng | Multi-AZ, DR liên vùng được diễn tập |
| Nội dung công khai có thể tái tạo | Vài phút đến vài giờ | Có thể tái tạo | CDN/cache và origin dự phòng |

Các giá trị trong bảng chỉ là ví dụ thảo luận, không phải khuyến nghị mặc định hay bảo đảm của provider. Một RPO bằng 0 có thể đòi hỏi đồng bộ ghi, quorum hoặc một hệ thống phân tán cụ thể; đổi lại latency và khả năng ghi khi network partition có thể bị ảnh hưởng.

### Xác định RTO/RPO theo từng capability

Một hệ thống có thể có RTO khác nhau cho API đọc, API ghi, xử lý thanh toán và báo cáo. Nếu database phục hồi trong 10 phút nhưng DNS failover mất 20 phút, RTO tổng thể vẫn bị chi phối bởi DNS. Hãy đo từ góc nhìn người dùng: thời điểm request đầu tiên thành công với dữ liệu hợp lệ và side effect đúng.

Khi lập kế hoạch, phân rã RTO thành các khoảng có thể đo: phát hiện sự cố, quyết định failover, fence writer cũ, promote/khôi phục dữ liệu, chuẩn bị capacity, chuyển routing và xác minh nghiệp vụ. Với hệ thống queue, cần tính cả thời gian backlog được xử lý trở lại mức SLA; API có thể đã nhận request nhưng đơn hàng vẫn đang chờ trong queue. RTO nên được đo cho từng capability và cả thời gian phục hồi hoàn chỉnh của business flow.

## 5. Multi-AZ cho serverless: function không phải toàn bộ kiến trúc

Function serverless thường được provider quản lý execution environment và khả năng scale trong một Region. Tuy nhiên, các dependency mà function sử dụng có thể có cấu hình zonal hoặc regional khác nhau.

Một thiết kế Multi-AZ cần xem xét:

- Function/API endpoint có phụ thuộc một subnet hoặc một network route duy nhất không?
- Khi function kết nối vào VPC, các subnet có trải trên nhiều AZ không?
- NAT gateway, firewall, route table và VPC endpoint có single-AZ dependency không?
- Database có standby/failover node ở AZ khác không?
- Cache, search cluster và message broker có replica ở nhiều AZ không?
- Object storage/queue là dịch vụ regional hay resource gắn với một AZ?
- Secret, KMS key, certificate và identity dependency có sẵn trong AZ dự phòng không?
- Log/metric/trace có tiếp tục được gửi khi một AZ mất kết nối không?

Không phải mọi dịch vụ cloud đều yêu cầu người dùng tự triển khai một instance trong từng AZ. Một số dịch vụ managed đã tự phân tán hoặc cung cấp cấu hình Multi-AZ. Cần đọc phạm vi availability và cấu hình thực tế của đúng service tier.

### Ví dụ function trong VPC

Nếu Java Lambda cần truy cập database private, function có thể được cấu hình với nhiều subnet thuộc các AZ khác nhau. Điều đó giúp network interface của function có lựa chọn đường đi ở nhiều AZ, nhưng không tự tạo HA cho database, NAT hoặc route.

Nếu function chỉ gọi dịch vụ regional qua endpoint managed, đường đi và failure domain có thể khác. Hãy xác định dependency nào thực sự zonal và dependency nào đã được provider quản lý ở cấp Region.

## 6. Bảo vệ network path qua nhiều AZ

Network có thể trở thành single point of failure ngay cả khi compute và database đã Multi-AZ.

Một số điểm cần kiểm tra:

- Subnet placement: workload có subnet ở nhiều AZ hay không?
- Route table: mỗi subnet có route cần thiết khi một AZ lỗi không?
- NAT: nếu outbound Internet cần thiết, NAT có dự phòng theo AZ hoặc cơ chế thay thế không?
- VPC endpoint/private link: endpoint có zone placement hoặc quota nào?
- Firewall/security appliance: có cluster/route dự phòng không?
- DNS resolver: ứng dụng có phụ thuộc một resolver riêng tự vận hành không?
- Connection pool: sau failover, connection cũ có được tạo lại đúng cách không?

Nếu nhiều subnet cùng route qua một NAT instance hoặc appliance đơn lẻ, kiến trúc có thể vẫn mất outbound connectivity khi thành phần đó lỗi. Đánh giá cả đường request vào và đường gọi dependency ra.

Không nên đặt tất cả traffic qua một điểm tập trung chỉ để đơn giản hóa network nếu điểm đó không có redundancy tương ứng.

## 7. Database Multi-AZ và vai trò của failover

Database thường là thành phần quyết định RPO/RTO. Có nhiều mô hình:

- **Synchronous standby:** primary chỉ xác nhận commit sau khi dữ liệu được ghi đến một replica theo cơ chế đồng bộ/quorum. Có thể giảm RPO nhưng tăng phụ thuộc network và latency.
- **Asynchronous replica:** primary xác nhận trước, replica cập nhật sau. Giảm latency write nhưng có replication lag và khả năng mất một phần dữ liệu mới nhất khi failover.
- **Managed Multi-AZ:** provider quản lý standby, health detection và một phần quá trình chuyển đổi.
- **Read replica:** chủ yếu phục vụ read scaling hoặc DR tùy sản phẩm; không mặc định có thể tự động nhận write.

Cần phân biệt failover của database với failover của ứng dụng. Sau khi database chuyển primary, Java function có thể vẫn giữ connection đến endpoint cũ. Connection pool phải xử lý stale connection, retry có giới hạn và reconnect.

### Khi database failover

1. Database phát hiện primary không còn khả dụng.
2. Hệ thống chọn/promote standby theo cơ chế của dịch vụ.
3. Endpoint hoặc DNS có thể cập nhật.
4. Client cần phát hiện connection cũ và kết nối lại.
5. Request đang chạy có thể nhận timeout hoặc lỗi transaction.
6. Ứng dụng cần retry an toàn bằng idempotency key.
7. Queue/workflow có thể replay công việc chưa xác nhận.

Không retry một thao tác ghi không idempotent chỉ vì client nhận timeout. Transaction có thể đã commit nhưng response bị mất. Trước khi retry, dùng idempotency key hoặc truy vấn trạng thái operation để xác định kết quả.

## 8. Queue, event bus và stream trong kiến trúc Multi-AZ

Queue và event service managed thường có availability model riêng. Một queue regional không nhất thiết yêu cầu người dùng tạo queue riêng cho từng AZ. Tuy nhiên, consumer, producer, encryption key, permission và các destination phụ trợ vẫn cần được kiểm tra.

Với queue/event:

- Producer cần xử lý timeout khi publish và tránh tạo event nghiệp vụ trùng.
- Consumer cần idempotent vì redelivery là hành vi bình thường.
- Visibility timeout/lease phải phù hợp thời gian xử lý.
- DLQ phải có retention, quyền đọc và cảnh báo.
- Event schema và event ID phải ổn định để replay.
- Workflow cần checkpoint hoặc trạng thái bền vững.
- Nếu một AZ lỗi, consumer ở AZ khác phải tiếp tục nhận việc khi service hỗ trợ.

Với stream có partition/shard ordering, không thay đổi consumer placement hoặc checkpoint một cách tùy tiện. Failover cần bảo toàn sequence semantics và tránh hai consumer cùng xử lý một partition nếu service không hỗ trợ.

## 9. Multi-Region: khi nào cần?

Multi-Region có chi phí và độ phức tạp cao hơn Multi-AZ. Cần xem xét khi có một hoặc nhiều yêu cầu:

- RTO của sự cố Region thấp hơn khả năng khôi phục trong cùng Region.
- RPO yêu cầu replication sang khu vực địa lý khác.
- Có yêu cầu data residency hoặc phục vụ người dùng ở nhiều khu vực.
- Một Region không đủ capacity hoặc không đáp ứng latency.
- Rủi ro gián đoạn diện rộng cần được giảm thiểu.
- Nghiệp vụ yêu cầu continuity khi Region chính bị mất hoàn toàn.

Không triển khai Multi-Region chỉ vì “cloud có thể lỗi”. Đầu tiên phải xác định impact, xác suất, RTO/RPO và chi phí của downtime. Một hệ thống có backup được kiểm thử có thể phù hợp hơn active-active nếu business chấp nhận RTO dài hơn.

## 10. Các mô hình DR phổ biến

### Backup and restore

Chỉ duy trì backup dữ liệu, artifact, cấu hình và hạ tầng cần thiết. Khi có sự cố, dựng lại stack ở Region khác rồi restore dữ liệu.

- Chi phí thường thấp hơn các mô hình giữ sẵn toàn bộ compute.
- RTO dài hơn vì phải provision và restore.
- RPO phụ thuộc lịch backup và khả năng log shipping.
- Cần kiểm thử restore, không chỉ kiểm tra job backup thành công.

### Pilot light

Giữ sẵn các thành phần tối thiểu ở Region dự phòng, ví dụ database replica hoặc hạ tầng nền tảng quan trọng. Khi sự cố, scale và deploy phần còn lại.

- RTO ngắn hơn backup/restore thuần túy.
- Chi phí trung bình.
- Cần tự động hóa bước scale/deploy và kiểm tra dependency.
- Capacity dự phòng có thể chưa đủ cho tải production ngay lập tức.

### Warm standby

Duy trì một bản triển khai đầy đủ hơn ở Region dự phòng nhưng chạy ở capacity thấp. Khi failover, tăng capacity và chuyển traffic.

- RTO thường ngắn hơn pilot light.
- Có chi phí duy trì compute và data replication.
- Cần kiểm tra capacity ramp-up và quota ở Region dự phòng.

### Hot standby / active-passive

Region chính phục vụ traffic; Region dự phòng giữ capacity sẵn sàng hoặc gần sẵn sàng. Khi failover, Region dự phòng tiếp nhận phần lớn hoặc toàn bộ traffic.

- RTO có thể ngắn nếu dữ liệu, routing và capacity đã sẵn sàng.
- Tốn chi phí duy trì capacity dự phòng.
- Cần cơ chế fencing để Region cũ không tiếp tục ghi khi Region mới đã được promote.

### Active-active

Nhiều Region cùng phục vụ traffic. Có thể route người dùng đến Region gần nhất hoặc theo policy.

- Có thể giảm latency và tiếp tục phục vụ khi một Region lỗi.
- Cần giải quyết write ownership, conflict và consistency.
- Chi phí replication, network và vận hành cao hơn.
- Failover traffic cần kiểm soát để không làm quá tải Region còn lại.

| Mô hình | Capacity dự phòng | RTO tương đối | RPO tương đối | Chi phí/độ phức tạp |
|---|---|---|---|---|
| Backup and restore | Không hoặc rất ít | Dài | Theo backup/replication | Thấp hơn |
| Pilot light | Thành phần cốt lõi | Trung bình đến dài | Theo replica/log shipping | Trung bình |
| Warm standby | Stack chạy capacity thấp | Trung bình đến ngắn | Theo replication | Cao hơn |
| Hot standby | Capacity gần production | Ngắn nếu chuyển đổi tốt | Theo replication/consistency | Cao |
| Active-active | Nhiều Region cùng phục vụ | Có thể rất ngắn ở tầng routing | Phụ thuộc mô hình ghi | Cao nhất trong nhiều trường hợp |

Các mức tương đối không phải cam kết. Một warm standby có DNS, database promotion hoặc quota chưa chuẩn bị có thể có RTO dài hơn một pilot light được tự động hóa tốt.

## 11. Chọn active-passive hay active-active

Active-passive phù hợp khi muốn một nơi sở hữu quyền ghi và một Region chờ nhận vai trò sau failover. Nó đơn giản hóa consistency và business ownership, nhưng cần kiểm thử promote/fencing.

Active-active phù hợp khi có nhu cầu phục vụ đồng thời nhiều địa lý hoặc yêu cầu continuity cao, và dữ liệu có thể được phân vùng theo ownership hoặc xử lý conflict rõ ràng.

Câu hỏi trước khi chọn:

- Có thể chia dữ liệu theo tenant/customer/aggregate để mỗi Region sở hữu một phần không?
- Hai Region có thể cùng cập nhật một record không?
- Nếu cùng ghi, conflict được giải quyết theo version, sequence hay business merge?
- Có thể chấp nhận eventual consistency không?
- Write có thể được route về home Region không?
- Nếu một Region mất kết nối với Region kia, hệ thống có tiếp tục nhận write hay chuyển read-only?
- Có cơ chế ngăn Region cũ tiếp tục ghi sau khi failover không?

Không dùng active-active chỉ bằng cách deploy cùng function ở hai Region rồi đặt DNS round-robin. Nếu cả hai function ghi cùng một database hoặc hai replica không có conflict strategy, dữ liệu có thể không nhất quán.

## 12. Replication và consistency giữa các Region

Replication có thể đồng bộ hoặc bất đồng bộ.

**Synchronous replication** yêu cầu xác nhận dữ liệu theo một cơ chế đồng thuận trước khi trả thành công. Nó có thể giảm RPO, nhưng tăng latency và có thể làm write không khả dụng khi network giữa các Region bị phân vùng.

**Asynchronous replication** cho phép primary trả thành công trước khi replica nhận đủ dữ liệu. Nó giảm latency cho write, nhưng có replication lag. Khi primary mất đột ngột, một số write gần nhất có thể chưa tới replica.

### Ví dụ replication lag

Giả sử Region A ghi event lúc 10:00:00.100Z. Region B chỉ nhận được event đó lúc 10:00:02.100Z. Nếu Region A mất lúc 10:00:01Z, replica B chưa có event vừa ghi. Khoảng trễ này ảnh hưởng RPO.

Không chỉ đo lag trung bình. Theo dõi p95/p99 replication lag, oldest unapplied log/event, replica health và khả năng catch-up sau khi link hồi phục.

### Read-after-write

Một người dùng vừa ghi dữ liệu ở Region A rồi được route sang Region B có thể đọc bản replica cũ. Các cách xử lý:

- Giữ session affinity về home Region trong một khoảng thời gian.
- Dùng version token để biết replica đã bắt kịp hay chưa.
- Đọc từ primary khi cần read-your-writes.
- Trả trạng thái pending nếu nghiệp vụ chấp nhận eventual consistency.
- Không chuyển write sang Region khác khi chưa có quyền ownership rõ ràng.

## 13. Split-brain và writer fencing

Split-brain xảy ra khi hai Region cùng tin rằng mình là primary và cùng nhận write. Điều này có thể xuất hiện khi network partition làm mất liên lạc giữa các Region nhưng cả hai vẫn nhận request từ client.

Hậu quả:

- Hai bản ghi cùng ID có nội dung khác nhau.
- Sequence/version bị phân nhánh.
- Inventory hoặc quota bị cấp phát vượt mức.
- Payment/order side effect bị thực hiện hai lần.
- Replication sau đó không thể tự merge đúng ý nghĩa nghiệp vụ.

Cần một cơ chế writer ownership rõ ràng:

- Một authority/quorum quyết định writer hiện tại.
- Lease có thời hạn và renewal.
- Monotonic fencing token/epoch tăng sau mỗi lần chuyển primary.
- Storage layer từ chối write mang epoch cũ.
- Runbook không cho phép promote Region mới trước khi fencing Region cũ.

### Fencing token

Giả sử Region A đang giữ epoch 41. Khi failover, hệ thống cấp epoch 42 cho Region B. Database hoặc service sở hữu dữ liệu chỉ chấp nhận write có epoch mới nhất. Nếu Region A hồi phục và tiếp tục gửi write epoch 41, thao tác phải bị từ chối.

Fencing phải được kiểm tra tại nơi thực hiện write, không chỉ trong memory của Java process. Nếu chỉ có một boolean trong process để chỉ ra Region đang active, một instance cũ có thể vẫn ghi sau khi process khác đã đổi vai trò.

## 14. Idempotency khi failover và replay

Trong DR, event có thể được replay từ queue, stream, outbox hoặc backup. Một request có thể được xử lý ở Region A rồi được gửi lại ở Region B vì response không đến client. Consumer cần stable idempotency key xuyên Region.

Một record idempotency nên có:

- event ID hoặc operation ID ổn định.
- trạng thái PROCESSING/COMPLETED/FAILED.
- kết quả hoặc reference đến side effect đã tạo.
- version/epoch nếu quyền ghi thay đổi theo Region.
- thời điểm tạo và thời gian retention.
- nguồn Region và trace/correlation reference nếu cần.

Nếu idempotency table chỉ tồn tại trong database Region A và không được replicate trước failover, Region B có thể không biết event đã hoàn tất. Với side effect quan trọng, cần xác định nơi lưu deduplication record và RPO của record đó.

Đối với external provider như payment, truyền cùng idempotency key đến provider nếu API hỗ trợ. Nếu provider không hỗ trợ, cần lưu provider reference và reconciliation trước khi retry một thao tác có thể đã thành công.

## 15. Event routing và queue giữa các Region

Một kiến trúc Multi-Region cần quyết định event được phát và tiêu thụ ở đâu.

Các mô hình thường gặp:

- **Regional queue riêng:** mỗi Region có queue/consumer riêng; producer route event đến Region sở hữu dữ liệu.
- **Replicated event stream:** event được chuyển sang Region khác để phục vụ DR hoặc analytics.
- **Global event routing:** một lớp routing phân phối event theo Region, tenant hoặc loại event.
- **Central queue:** nhiều Region consume một queue chung nếu dịch vụ hỗ trợ và latency/availability phù hợp.

Các câu hỏi quan trọng:

- Event có được publish đồng thời sang hai Region không?
- Nếu publish thành công ở A nhưng thất bại ở B, retry sẽ làm gì?
- Consumer có thể xử lý cùng event ở cả hai Region không?
- Event ordering được giữ theo aggregate/partition key không?
- Khi failover, backlog cũ ở Region A được replay hay bỏ qua?
- DLQ ở Region nào và ai có quyền redrive?
- Event schema và encryption key có sẵn ở Region dự phòng không?

Transactional outbox giúp ghi business change và event cần phát trong cùng transaction. Dispatcher có thể retry publish; consumer idempotent xử lý duplicate. Đây là pattern hữu ích để tránh mất event khi ứng dụng crash giữa database commit và publish.

## 16. Serverless workflow trong Multi-Region

Workflow engine thường có execution state lưu ở một Region hoặc trong một service scope cụ thể. Không giả định workflow execution tự động tiếp tục ở Region khác khi Region chính mất.

Cần xác định:

- Workflow definition có được deploy ở Region dự phòng không?
- Execution state có được replicate hoặc checkpoint ra store độc lập không?
- Timer, callback token và wait state có thể khôi phục không?
- Một task đang chạy có thể được thực hiện lại ở Region mới không?
- Có idempotency cho task và external side effect không?
- Compensation step có được lưu và replay an toàn không?
- Workflow run ID có ổn định khi restore/restart không?

Với workflow dài, lưu business state và operation checkpoint bền vững ngoài memory của function. Khi DR, có thể cần khởi tạo execution mới từ checkpoint thay vì cố di chuyển một execution đang chạy.

Không tạo một workflow mới từ đầu nếu các side effect trước đó chưa được đối chiếu. Trước khi resume, xác định task nào đã commit, task nào đang không rõ kết quả và task nào có thể chạy lại an toàn.

## 17. Routing và failover traffic

Traffic có thể được chuyển giữa Region bằng DNS failover, global load balancer, anycast routing, CDN hoặc API gateway. Mỗi cơ chế có thời gian hội tụ và semantics riêng.

### DNS failover

DNS có thể trả địa chỉ của Region khỏe mạnh. Nhưng resolver, client và connection pool có thể cache DNS lâu hơn TTL. Existing connection không tự chuyển sang Region mới. Vì vậy, DNS TTL thấp không bảo đảm toàn bộ client đổi route ngay lập tức.

### Global load balancer

Global load balancer có thể health-check endpoint và route request đến Region phù hợp. Cần bảo đảm health check phản ánh khả năng phục vụ nghiệp vụ, không chỉ việc process còn sống.

### Client-side routing

SDK hoặc client có thể chọn Region theo policy. Cách này cần quản lý endpoint list, certificate, auth và cache của client. Client cũ có thể giữ cấu hình route lâu hơn dự kiến.

### Health check

Phân biệt:

- **Liveness:** process/runtime còn sống không?
- **Readiness:** service có thể nhận request mới không?
- **Dependency health:** database, queue hoặc external API có đủ khả năng đáp ứng nghiệp vụ không?
- **Synthetic transaction:** một luồng kiểm tra đại diện có thực sự hoàn tất không?

Nếu health check quá sâu và gọi nhiều dependency, nó có thể tạo tải lớn hoặc đánh dấu toàn bộ Region unhealthy chỉ vì một dependency phụ bị chậm. Thiết kế readiness theo capability: có thể API đọc vẫn hoạt động trong khi API ghi tạm ngừng.

## 18. Quy trình failover có kiểm soát

Failover không nên chỉ là đổi DNS. Một quy trình điển hình:

1. **Detect:** xác nhận sự cố bằng nhiều tín hiệu, loại trừ lỗi monitoring đơn lẻ.
2. **Declare:** incident commander hoặc cơ chế tự động có thẩm quyền tuyên bố failover.
3. **Fence:** ngăn Region cũ tiếp tục nhận write nếu quyền ghi sẽ chuyển sang nơi khác.
4. **Assess data:** kiểm tra replication lag, RPO thực tế và trạng thái transaction chưa rõ.
5. **Promote:** promote database/replica hoặc khôi phục data store ở Region đích.
6. **Verify dependencies:** IAM, KMS, secrets, network, queue, event source và external allowlist.
7. **Scale capacity:** tăng instance/concurrency và kiểm tra quota.
8. **Enable consumers:** chỉ mở queue/stream consumer khi writer và idempotency store sẵn sàng.
9. **Route traffic:** chuyển DNS/global routing hoặc API endpoint.
10. **Observe:** theo dõi error rate, p95/p99, backlog, duplicate, replication lag và business completion.
11. **Communicate:** cập nhật trạng thái dịch vụ và tác động dữ liệu theo quy trình tổ chức.

Nếu không thể chứng minh Region cũ đã bị fence, không cho phép hai Region cùng ghi vào dữ liệu authoritative. Có thể tạm chuyển một phần API sang read-only hoặc trả lỗi có kiểm soát cho write thay vì tạo split-brain.

## 19. Failback sau khi Region chính phục hồi

Failback là chuyển workload từ Region dự phòng về Region chính. Nó không nên diễn ra ngay khi Region chính báo healthy.

Trước failback:

- Xác minh nguyên nhân sự cố đã được xử lý.
- Kiểm tra data store cũ có stale hoặc corrupted không.
- Đồng bộ dữ liệu phát sinh trong thời gian DR.
- Xác định writer authority và fencing epoch mới.
- Kiểm tra event backlog, DLQ và workflow đang chạy.
- Xác nhận capacity/quota và network.
- Thử routing ở phạm vi nhỏ hoặc canary.
- Theo dõi consistency và business metrics trước khi chuyển toàn bộ.

Trong nhiều hệ thống, tiếp tục chạy ở Region dự phòng lâu hơn sẽ an toàn hơn việc failback vội. Chọn thời điểm dựa trên rủi ro và chi phí, không chỉ vì Region cũ đã hoạt động trở lại.

## 20. Backup và restore liên vùng

Replication giúp có bản sao gần thời gian thực, còn backup giúp quay lại điểm trước khi dữ liệu bị xóa hoặc hỏng. Hai cơ chế cần độc lập đủ để một lỗi logic không phá hủy mọi bản sao.

Checklist backup:

- Backup có nằm ở failure domain khác không?
- Có bản copy cross-Region hoặc immutable/offline không?
- Encryption key có thể truy cập từ Region phục hồi không?
- Retention có đáp ứng RPO và yêu cầu compliance không?
- Có kiểm tra checksum và tính toàn vẹn không?
- Restore có được diễn tập với dữ liệu thực tế đại diện không?
- Có runbook khôi phục schema, secret, IAM và network không?

Backup job thành công không chứng minh có thể restore. Đo thời gian restore, khả năng phục hồi đến điểm mong muốn và tỷ lệ dữ liệu kiểm tra được.

## 21. Bảo mật trong kiến trúc Multi-Region

Một Region dự phòng phải có security posture tương đương Region chính. Những thành phần thường bị bỏ sót:

- IAM role/policy và trust relationship.
- KMS key, key policy và quyền decrypt.
- Secret manager và version của secret.
- TLS certificate, custom domain và DNS record.
- Network ACL, security group, firewall và private endpoint.
- Audit log, security event và alert destination.
- Backup access, replication role và break-glass account.

Không sao chép secret dài hạn sang Region dự phòng một cách tùy tiện. Dùng secret manager/KMS và quyền tối thiểu, kiểm tra khả năng truy cập key khi failover. Nếu key chỉ tồn tại ở Region chính, dữ liệu được replicate có thể không decrypt được ở Region đích.

Failover cũng là một sự kiện nhạy cảm về bảo mật. Audit ai đã promote database, thay đổi writer epoch, chuyển route và redrive message.

## 22. Chi phí và trade-off của Multi-AZ/Multi-Region

Chi phí không chỉ là số function invocation:

- Database standby/replica và storage.
- Function warm capacity hoặc provisioned concurrency.
- Queue, stream và event replication.
- Data transfer liên AZ/liên Region.
- NAT, private endpoint, load balancer và DNS.
- Log/metric/trace ở nhiều Region.
- Backup, snapshot và restore test.
- KMS key, secret replication và audit.
- Chi phí vận hành, diễn tập và trực sự cố.

Active-active có thể tăng capacity và giảm latency, nhưng có thể tăng chi phí replication và conflict resolution. Warm standby tốn ít compute hơn hot standby nhưng RTO có thể dài hơn. Backup/restore có chi phí thường thấp hơn nhưng thời gian phục hồi dài và đòi hỏi automation tốt.

Đánh giá chi phí theo một kịch bản DR hoàn chỉnh: bao nhiêu thời gian chạy dự phòng, bao nhiêu traffic failover, data egress, backlog replay và capacity cần thiết sau sự cố.

## 23. Observability cho AZ và Region

Dashboard cần phân đoạn theo Region, AZ (nếu provider cung cấp metadata), service, function, route và dependency.

Các metric quan trọng:

- Request rate, error rate, p95/p99 latency theo Region.
- Invocation concurrency, throttling và cold start.
- Queue depth, oldest message age, retry và DLQ.
- Database primary/replica health và replication lag.
- Connection errors, DNS resolution và network latency.
- Workflow started/running/failed/completed theo Region.
- Idempotency duplicate/conflict và fencing rejection.
- Failover/failback state và thời gian từng bước.
- Backup/restore job status và restore test duration.

Correlation ID, trace ID và workflow run ID giúp ghép log qua các Region. Tuy nhiên, telemetry pipeline cũng có thể bị ảnh hưởng bởi sự cố Region. Nên có cách xem trạng thái độc lập hoặc global monitoring bên ngoài Region đang được giám sát.

## 24. Kiểm thử khả năng chịu lỗi

Kiểm thử không chỉ xác nhận function vẫn trả 200. Cần xác nhận dữ liệu, side effect, thứ tự và RTO/RPO vẫn nằm trong giới hạn.

Các loại test:

1. **AZ isolation:** làm mất một subnet, route hoặc dependency zonal trong môi trường test.
2. **Instance/runtime failure:** terminate instance hoặc làm function timeout để xác nhận retry/idempotency.
3. **Database failover:** chuyển primary/standby và kiểm tra connection recovery.
4. **Network partition:** mô phỏng mất kết nối giữa các Region để kiểm tra writer fencing.
5. **Region failover:** ngắt route đến Region chính và chuyển traffic sang dự phòng.
6. **Queue replay:** redrive message và xác nhận không tạo side effect trùng.
7. **Workflow resume:** khôi phục từ checkpoint và xác nhận step đã commit không chạy lại sai.
8. **Backup restore:** restore dữ liệu vào môi trường cô lập và đo RTO/RPO.
9. **Failback:** chuyển lại Region cũ sau khi đồng bộ và fencing.
10. **Capacity test:** đảm bảo Region dự phòng chịu được tải sau failover.

### Game day và chaos testing

Game day là buổi diễn tập có kịch bản, người chịu trách nhiệm, tiêu chí thành công và quy trình rollback. Chaos testing có thể inject failure có kiểm soát như latency, packet loss, process termination hoặc dependency unavailability.

Bắt đầu ở môi trường non-production và phạm vi nhỏ. Chỉ thử trên production khi có phê duyệt, blast radius giới hạn, monitoring và abort condition rõ ràng.

## 25. Ví dụ Java: kiểm tra writer ownership và idempotency

Ví dụ sau minh họa một consumer chỉ được ghi khi Region hiện tại giữ writer epoch mới nhất. Repository cần thực hiện các thao tác bằng transaction/conditional write tại nơi lưu dữ liệu authoritative.

~~~java
public final class OrderEventConsumer {
    private final WriterLeaseRepository leaseRepository;
    private final InboxRepository inboxRepository;
    private final OrderRepository orderRepository;

    public void handle(
            OrderCreated event,
            String region,
            long writerEpoch) {

        transaction(() -> {
            if (!leaseRepository.isCurrentWriter(region, writerEpoch)) {
                throw new StaleWriterException();
            }

            InboxClaim claim = inboxRepository.claim(event.eventId());

            if (claim.isCompleted()) {
                return;
            }

            if (!claim.isOwnedByCurrentAttempt()) {
                throw new RetryableProcessingException();
            }

            orderRepository.applyCreatedEvent(event);
            inboxRepository.markCompleted(event.eventId());
        });
    }
}
~~~

Đây là pseudocode vì transaction và claim semantics phụ thuộc database. Các điều kiện quan trọng:

- Writer epoch phải được xác thực atomically ở storage boundary.
- Inbox event ID có unique constraint hoặc conditional write.
- Business update và trạng thái COMPLETED cùng commit trong transaction nếu cùng database.
- Nếu event đang PROCESSING ở transaction riêng, phải có lease/timeout và recovery.
- External side effect cần provider idempotency key hoặc outbox/reconciliation.
- Region cũ không thể ghi chỉ vì một Java process còn giữ cấu hình cũ.

Không chỉ dùng biến trong memory để quyết định quyền ghi. Sau network partition hoặc failover, process cũ có thể chưa nhận được config mới.

## 26. Ma trận lựa chọn kiến trúc

| Yêu cầu | Multi-AZ | Warm standby Region | Active-active Region |
|---|---|---|---|
| Chịu lỗi một AZ | Có thể đáp ứng nếu dependency được phân tán | Có thể nhưng không phải mục tiêu chính | Có thể |
| Chịu lỗi toàn Region | Không | Có, theo RTO/RPO thiết kế | Có, nếu data plane và routing sẵn sàng |
| Latency liên vùng | Không cần cho request bình thường | Chỉ khi replication/failover | Thường xuyên nếu đọc/ghi liên vùng |
| Write ownership | Một Region | Primary rồi promote | Phải phân vùng hoặc giải quyết conflict |
| Vận hành | Thấp đến vừa | Vừa đến cao | Cao |
| Chi phí | Vừa | Cao | Cao nhất trong nhiều trường hợp |
| Phù hợp | HA cho ứng dụng thông thường | DR với RTO tương đối ngắn | Workload đa địa lý và consistency được thiết kế |

Không có mô hình tốt nhất cho mọi hệ thống. Chọn mô hình dựa trên RTO/RPO, consistency, khả năng vận hành, data residency và budget.

## 27. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Chỉ deploy nhiều function instance | Database hoặc network vẫn là single point of failure | Vẽ failure domain toàn dependency chain |
| Cho rằng managed serverless tự động Multi-AZ mọi dependency | Queue, database hoặc NAT vẫn có thể tập trung | Xác minh availability scope từng dịch vụ |
| Nhầm Multi-AZ với Multi-Region DR | Không chịu được sự cố Region | Xác định failure scenario và RTO/RPO |
| Có replica nhưng không có backup độc lập | Xóa nhầm/corruption lan sang replica | Backup immutable/cross-Region và restore test |
| Promote replica mà không đo lag | Mất dữ liệu vượt RPO | Kiểm tra replication lag và quyết định có chấp nhận không |
| Hai Region cùng ghi | Split-brain và conflict | Writer ownership, quorum và fencing token |
| Chỉ đổi DNS khi failover | Client cache và connection cũ vẫn đi Region lỗi | Routing plan, TTL, connection retry và health check |
| Retry POST sau timeout mà không idempotency | Side effect trùng | Stable key và reconciliation |
| Replay toàn bộ queue mà không checkpoint | Xử lý lặp hoặc sai thứ tự | Event ID, inbox/outbox và ordering |
| Workflow mới chạy từ đầu | Lặp side effect đã commit | Durable checkpoint và resume có kiểm soát |
| Failback ngay khi Region cũ healthy | Mất dữ liệu hoặc writer conflict | Reconcile, fence và canary failback |
| Không chuẩn bị KMS/IAM/secrets ở Region đích | Dữ liệu không decrypt hoặc function không chạy | DR security readiness test |
| Chỉ đo health check của process | Endpoint sống nhưng nghiệp vụ không hoạt động | Readiness và synthetic transaction theo capability |
| Không diễn tập restore/failover | RTO thực tế vượt mục tiêu | Game day và restore test định kỳ |

## 28. Quy trình xây dựng kế hoạch HA/DR

1. **Lập inventory:** function, API, database, queue, stream, cache, workflow, network, identity, secret và external dependency.
2. **Vẽ failure domain:** xác định thành phần nào zonal, regional, global hoặc external.
3. **Phân loại nghiệp vụ:** read, write, payment, notification, reporting và background processing.
4. **Đặt RTO/RPO:** theo business impact và capability, không chỉ một con số chung.
5. **Chọn Multi-AZ:** loại bỏ single-AZ dependency cho dịch vụ cần HA.
6. **Chọn DR pattern:** backup/restore, pilot light, warm standby, hot standby hoặc active-active.
7. **Thiết kế data:** replication, consistency, writer ownership, fencing và backup.
8. **Thiết kế event:** idempotency, outbox, queue routing, DLQ và replay.
9. **Chuẩn bị Region dự phòng:** code, config, IAM, KMS, secret, quota, network và observability.
10. **Tự động hóa failover:** runbook, approval, promote, route và capacity.
11. **Thiết kế failback:** reconcile dữ liệu, chuyển writer và traffic theo giai đoạn.
12. **Kiểm thử:** AZ failure, Region loss, network partition, restore, replay và load sau failover.
13. **Đo kết quả:** RTO/RPO thực tế, data loss, error rate và business completion.
14. **Cập nhật:** điều chỉnh kiến trúc và runbook khi dependency hoặc quota thay đổi.

## 29. Checklist production

- **Failure domains:** đã phân loại process, AZ, Region, global service và external dependency.
- **Multi-AZ:** compute, database, cache, queue và network path có cấu hình phù hợp.
- **RTO/RPO:** có mục tiêu được business owner chấp thuận cho từng capability.
- **Database:** hiểu sync/async replication, failover endpoint, connection recovery và transaction outcome.
- **Multi-Region:** đã chọn DR pattern dựa trên RTO/RPO và budget.
- **Writer ownership:** có primary authority, fencing/epoch và cơ chế chống split-brain.
- **Consistency:** đã xác định read-after-write, conflict resolution và replication lag.
- **Idempotency:** event ID và operation key ổn định xuyên Region; external side effect có reconciliation.
- **Queue/workflow:** replay, DLQ, checkpoint và resume không tạo side effect trùng.
- **Routing:** DNS/global load balancer, TTL, health check và client connection behavior đã được kiểm thử.
- **Security:** IAM, KMS, secrets, certificate, network policy và audit có sẵn ở Region đích.
- **Backup:** có bản độc lập và restore test đã đo thời gian.
- **Capacity:** Region dự phòng có quota và đủ capacity sau failover.
- **Observability:** dashboard global, metric theo Region/AZ, log/trace correlation và alert.
- **Runbook:** có detect, declare, fence, promote, route, verify, communicate và failback.
- **Testing:** đã diễn tập AZ failure, Region failover, network partition, queue replay và restore.
- **Cost:** đã tính replica, warm capacity, data transfer, backup, telemetry và chi phí diễn tập.

## 30. Kết luận

Multi-AZ giúp giảm tác động của sự cố trong một Region; Multi-Region mở rộng khả năng phục hồi khi cả Region gặp sự cố hoặc khi hệ thống cần phục vụ nhiều địa lý. Hai chiến lược giải quyết failure domain khác nhau và không thể thay thế cho nhau. Function serverless chỉ là một phần của kiến trúc: database, queue, network, identity, secret, workflow và external provider đều cần được đưa vào phân tích.

Hãy bắt đầu từ business impact, RTO và RPO rồi chọn mô hình backup/restore, pilot light, warm standby, hot standby hoặc active-active. Multi-Region đòi hỏi thiết kế replication, consistency, writer ownership, fencing, idempotency và routing. Nếu không kiểm soát các yếu tố đó, failover có thể chuyển sự cố availability thành sự cố mất hoặc ghi sai dữ liệu.

Một kế hoạch HA/DR chỉ đáng tin khi được diễn tập: kiểm tra AZ failure, Region loss, database promotion, queue replay, workflow resume, backup restore và failback. Đo RTO/RPO thực tế, quan sát theo từng Region và cập nhật runbook để Java serverless có thể phục hồi đúng nghiệp vụ khi một failure domain không còn sẵn sàng.
