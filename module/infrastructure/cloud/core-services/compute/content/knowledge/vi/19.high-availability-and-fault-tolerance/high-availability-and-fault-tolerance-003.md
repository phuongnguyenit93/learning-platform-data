# Nhân bản workload qua nhiều zone và tránh điểm lỗi duy nhất

Một ứng dụng có thể chạy tốt trên nhiều máy ảo nhưng vẫn ngừng hoạt động nếu tất cả máy nằm trong cùng một vùng sẵn sàng (Availability Zone), cùng phụ thuộc vào một load balancer hoặc dùng chung một database đơn lẻ. Nhân bản workload chỉ tạo ra tính sẵn sàng cao khi các bản sao được đặt trong những failure domain độc lập và các thành phần dùng chung cũng có phương án dự phòng.

**Nhân bản workload qua nhiều zone** là cách triển khai nhiều bản sao của ứng dụng hoặc dịch vụ trên các vùng sẵn sàng khác nhau trong cùng một region. Khi một zone gặp sự cố, các bản sao ở zone còn lại tiếp tục phục vụ. Thiết kế cần phối hợp placement, load balancing, health check, replication dữ liệu, capacity dự phòng và quy trình failover.

Bài học thuộc module **CLOUD_CORE_SERVICES_COMPUTE**, chương **Sẵn sàng cao và khả năng chịu lỗi**. Nội dung tập trung vào việc phân tán workload qua nhiều zone, nhận diện điểm lỗi duy nhất (Single Point of Failure - SPOF), lựa chọn mô hình active-active hoặc active-passive, bảo vệ dữ liệu stateful và kiểm thử khả năng phục hồi.

## 1. Failure domain và Availability Zone

Failure domain là phạm vi mà một sự cố có thể ảnh hưởng đồng thời đến một hoặc nhiều thành phần. Ví dụ:

- Một tiến trình hoặc container.
- Một máy ảo hoặc máy vật lý.
- Một rack hoặc cụm host.
- Một Availability Zone.
- Một region.
- Một nhà cung cấp cloud hoặc dịch vụ bên ngoài.

Availability Zone (AZ) là một vùng hạ tầng riêng biệt trong một cloud region. Các zone được thiết kế để giảm tương quan sự cố bằng cách tách biệt một số thành phần như nguồn điện, làm mát và mạng. Tuy nhiên, zone vẫn có thể dùng chung một số dịch vụ khu vực hoặc control plane. Vì vậy, không nên hiểu rằng hai zone hoàn toàn không có bất kỳ phụ thuộc chung nào.

Một region thường có nhiều AZ. Đặt các bản sao workload ở nhiều AZ giúp ứng dụng chịu được một số sự cố ở cấp zone mà không cần chuyển toàn bộ hệ thống sang region khác.

### 1.1. Phân biệt multi-instance, multi-zone và multi-region

| Mô hình | Phạm vi dự phòng | Có thể chịu được | Chi phí và độ phức tạp |
|---|---|---|---|
| Multi-process | Nhiều tiến trình trên một host | Một tiến trình lỗi | Thấp, nhưng host vẫn là SPOF |
| Multi-instance, same zone | Nhiều VM trong một zone | Một VM hoặc một phần host lỗi | Vừa; chưa chịu được sự cố zone |
| Multi-zone, same region | Nhiều bản sao qua các AZ | Một zone bị gián đoạn trong giới hạn thiết kế | Cao hơn; cần phân phối traffic và dữ liệu |
| Multi-region | Nhiều region | Một region bị gián đoạn | Phức tạp, chi phí và độ trễ replication cao hơn |

Nhiều VM trong cùng một AZ không tạo ra khả năng chịu lỗi zone. Nếu toàn bộ VM, database và load balancer phụ thuộc vào cùng một zone, sự cố zone vẫn có thể làm dịch vụ ngừng hoạt động.

### 1.2. Xác định ranh giới lỗi trước khi thiết kế

Hãy lập danh sách các thành phần và hỏi: nếu thành phần hoặc failure domain này ngừng hoạt động, dịch vụ có còn hoạt động không?

- Nếu một VM hỏng, replica khác có nhận tải được không?
- Nếu một AZ mất kết nối, traffic có chuyển sang AZ còn lại không?
- Nếu một subnet hoặc NAT gateway lỗi, ứng dụng có còn truy cập dependency cần thiết không?
- Nếu database primary lỗi, có replica đủ mới để promote không?
- Nếu dịch vụ DNS, identity hoặc secret manager gặp sự cố, workload có thể tiếp tục xử lý không?

Thiết kế HA bắt đầu bằng việc xác định những gì phải tiếp tục hoạt động và mức suy giảm nào có thể chấp nhận.

## 2. Availability, redundancy và fault tolerance

Ba khái niệm liên quan nhưng không giống nhau:

- **Availability:** xác suất hoặc tỷ lệ thời gian dịch vụ sẵn sàng đáp ứng yêu cầu.
- **Redundancy:** có thành phần dự phòng để thay thế khi thành phần chính lỗi.
- **Fault tolerance:** khả năng tiếp tục hoạt động khi một hoặc nhiều lỗi đã xác định xảy ra, có thể không gián đoạn hoặc chỉ suy giảm trong giới hạn.

Có hai VM không tự động đồng nghĩa với fault tolerance. Nếu cả hai cùng đọc một storage duy nhất, cùng dùng một database đơn lẻ hoặc cùng phụ thuộc một network path, điểm lỗi chung vẫn tồn tại.

### 2.1. Active-active

Trong mô hình active-active, nhiều bản sao cùng xử lý traffic hoặc công việc. Load balancer phân phối request tới các bản sao khỏe mạnh.

Ưu điểm:

- Năng lực của nhiều bản sao được sử dụng trong điều kiện bình thường.
- Khi một bản sao hoặc zone lỗi, phần còn lại có thể tiếp nhận thêm tải.
- Phù hợp với API stateless, web service và worker có thể xử lý song song.

Điều kiện:

- Trạng thái phiên hoặc dữ liệu dùng chung phải được quản lý phù hợp.
- Các bản sao cần tương thích về phiên bản và cấu hình.
- Capacity còn lại phải đủ sau khi mất một zone hoặc một nhóm instance.
- Các thao tác ghi đồng thời cần có quy tắc nhất quán và chống trùng lặp.

### 2.2. Active-passive

Trong mô hình active-passive, một bản sao xử lý traffic chính; bản sao dự phòng chờ sẵn hoặc chạy ở chế độ standby. Khi primary lỗi, hệ thống promote hoặc chuyển traffic sang standby.

Ưu điểm:

- Có thể phù hợp với workload stateful chỉ cho phép một node ghi tại một thời điểm.
- Giảm nhu cầu xử lý xung đột ghi đồng thời.
- Có thể giảm chi phí nếu standby dùng capacity nhỏ hơn và có thể mở rộng khi failover.

Đổi lại, quá trình phát hiện lỗi, promote, đồng bộ trạng thái và cập nhật route có thể làm tăng thời gian phục hồi. Standby phải được kiểm tra định kỳ để bảo đảm nó thực sự sẵn sàng.

### 2.3. So sánh mô hình

| Tiêu chí | Active-active | Active-passive |
|---|---|---|
| Phục vụ traffic bình thường | Nhiều bản sao | Chủ yếu một bản sao |
| Chuyển đổi khi lỗi | Loại bản sao lỗi khỏi phân phối | Promote hoặc kích hoạt standby |
| Sử dụng capacity | Cao hơn trong điều kiện bình thường | Standby có thể chưa dùng hết |
| Xử lý trạng thái | Cần thiết kế đồng thời và idempotency | Cần đồng bộ và quy trình chuyển primary |
| Trường hợp phù hợp | API stateless, web, worker phân tán | Database primary/standby, hệ thống chỉ có một writer |

Có thể kết hợp hai mô hình: API chạy active-active qua nhiều AZ, trong khi database chạy primary/standby với replication và failover có kiểm soát.

## 3. Phân tán workload qua nhiều zone

Một kiến trúc multi-zone cơ bản đặt các replica ứng dụng trong các subnet thuộc các AZ khác nhau. Load balancer hoặc lớp điều phối gửi traffic tới replica khỏe mạnh.

~~~mermaid
flowchart TB
    U["Người dùng / Client"] --> DNS["DNS / Global entry"]
    DNS --> LB["Regional Load Balancer"]
    LB --> A1
    LB --> A2
    LB --> A3
    subgraph Z1["Availability Zone A"]
      A1["App replica A1"]
      W1["Worker A"]
    end
    subgraph Z2["Availability Zone B"]
      A2["App replica B1"]
      W2["Worker B"]
    end
    subgraph Z3["Availability Zone C"]
      A3["App replica C1"]
      W3["Worker C"]
    end
    A1 --> DB["Database multi-zone"]
    A2 --> DB
    A3 --> DB
    W1 --> Q["Durable Queue"]
    W2 --> Q
    W3 --> Q
~~~

Sơ đồ minh họa một region có ba zone. Số lượng zone thực tế phụ thuộc region và dịch vụ. Một số dịch vụ được quản lý tự động phân tán dữ liệu hoặc endpoint; các dịch vụ khác yêu cầu khách hàng tự cấu hình subnet, replica và routing.

### 3.1. Đặt replica ở các AZ khác nhau

Khi tạo VM hoặc node pool:

- Chọn subnet ở nhiều AZ.
- Phân phối instance group hoặc autoscaling group qua các subnet đó.
- Tránh để mọi replica cùng bị giới hạn trong một AZ.
- Dùng anti-affinity hoặc topology spread cho workload trên Kubernetes.
- Xác minh scheduler còn đủ capacity ở các zone còn lại.
- Kiểm tra quota và giới hạn instance family theo từng AZ.

Không nên chỉ nhìn số lượng instance. Hãy xác minh vị trí AZ thực tế của từng replica bằng metadata hoặc cloud inventory.

### 3.2. Phân phối traffic

Load balancer cần:

- Kiểm tra health của backend bằng endpoint phản ánh khả năng phục vụ thực tế.
- Ngừng gửi request tới replica không khỏe.
- Có backend ở nhiều AZ.
- Duy trì kết nối và timeout hợp lý.
- Hỗ trợ drain khi deploy hoặc scale-in.
- Có phương án khi một zone mất toàn bộ backend.

Health check chỉ kiểm tra tiến trình đang sống có thể chưa đủ. Một API có thể trả HTTP 200 ở endpoint health nhưng không truy cập được database hoặc dependency thiết yếu. Nên phân biệt liveness với readiness và chọn mức kiểm tra phù hợp để tránh loại toàn bộ replica chỉ vì một dependency phụ đang suy giảm.

### 3.3. Cross-zone load balancing

Một số load balancer phân phối traffic chỉ tới backend trong cùng AZ; một số hỗ trợ phân phối xuyên AZ. Hành vi này ảnh hưởng đến khả năng sử dụng capacity và chi phí data transfer.

Nếu cross-zone bị tắt, một AZ còn ít backend có thể bị quá tải dù các AZ khác còn capacity. Nếu bật, traffic có thể đi qua AZ và phát sinh chi phí hoặc độ trễ mạng. Cần hiểu chính sách của load balancer và kiểm thử khi một AZ bị loại khỏi dịch vụ.

## 4. Tính capacity khi mất một zone

Một hệ thống multi-zone phải còn đủ năng lực sau khi mất failure domain lớn nhất mà nó cam kết chịu được. Nếu ba zone mỗi zone chạy đúng 33% tải và không có capacity dự phòng, khi một zone mất, hai zone còn lại phải tăng tải lên 50% so với trước.

Ví dụ: hệ thống cần 900 request/giây. Nếu phân phối đều trên ba AZ, mỗi zone phục vụ 300 request/giây. Khi mất một zone, hai zone còn lại phải phục vụ 450 request/giây mỗi zone. Nếu mỗi zone chỉ có capacity tối đa 350 request/giây, hệ thống sẽ quá tải trong sự cố.

### 4.1. Công thức capacity cơ bản

Gọi N là số AZ có workload, F là số AZ có thể mất trong kịch bản thiết kế, C là capacity tối đa của mỗi AZ và D là nhu cầu tải đỉnh. Điều kiện tối thiểu:

~~~text
(N - F) * C >= D
~~~

Với ba AZ và mục tiêu chịu lỗi một AZ, mỗi AZ cần có capacity ít nhất bằng một nửa nhu cầu toàn hệ thống nếu tải được phân phối đều. Trên thực tế cần thêm headroom cho tải không đều, failover, deploy và biến động hiệu năng.

### 4.2. Autoscaling không thay thế capacity dự phòng

Autoscaling có thể tạo thêm instance sau khi tải tăng, nhưng việc tạo máy cần thời gian và có thể thất bại nếu AZ còn lại thiếu quota hoặc hết capacity. Một thiết kế cần xác định:

- Minimum capacity luôn được duy trì.
- Maximum capacity và quota theo từng AZ.
- Thời gian khởi động ứng dụng và warm-up.
- Capacity còn lại ngay sau khi một AZ mất.
- Tốc độ autoscaling và giới hạn tăng instance.
- Khả năng kéo image, lấy secret và kết nối dependency khi scale.

Nếu SLO yêu cầu không chờ autoscaling sau sự cố, cần giữ sẵn capacity N+1 hoặc mức dự phòng tương ứng.

### 4.3. Workload có thể suy giảm có kiểm soát

Khi capacity còn lại không đủ cho mọi chức năng, hệ thống có thể ưu tiên:

- Giữ các endpoint quan trọng và giao dịch cốt lõi.
- Giảm tác vụ nền hoặc tác vụ phân tích không khẩn cấp.
- Giới hạn request theo tenant hoặc rate limit.
- Tạm dừng tính năng không thiết yếu.
- Dùng queue để tiếp nhận công việc có thể xử lý chậm.

Suy giảm có kiểm soát tốt hơn để mọi thành phần tiếp tục nhận tải rồi cùng sụp đổ.

## 5. Nhân bản workload stateless

Workload stateless không giữ trạng thái phiên hoặc dữ liệu nghiệp vụ duy nhất trong bộ nhớ cục bộ của một replica. Mỗi request có thể được xử lý bởi bất kỳ replica khỏe mạnh nào.

Để chạy stateless qua nhiều zone:

- Đưa session vào kho dùng chung hoặc dùng token có thể xác minh độc lập.
- Lưu file upload và kết quả vào object storage hoặc shared storage phù hợp.
- Lưu cấu hình và secret ở dịch vụ quản lý tập trung có tính sẵn sàng phù hợp.
- Dùng queue bền vững cho công việc bất đồng bộ.
- Bảo đảm request có thể retry an toàn khi client không biết replica trước đã hoàn tất hay chưa.
- Không dựa vào local disk của instance làm nơi lưu dữ liệu duy nhất.

### 5.1. Session và sticky session

Sticky session giữ một client ở cùng backend trong một khoảng thời gian. Nó có thể hữu ích cho một số ứng dụng legacy, nhưng làm giảm khả năng chuyển request tự do khi một backend hoặc AZ lỗi.

Nếu có thể, hãy externalize session vào kho dùng chung hoặc dùng token stateless. Nếu phải dùng sticky session, cần xác định hành vi khi backend mất và thời gian người dùng phải đăng nhập lại.

### 5.2. Local cache

Cache cục bộ giúp giảm latency và tải lên database, nhưng cache không nên là nguồn dữ liệu chuẩn duy nhất. Khi một replica mới được tạo ở AZ khác, cache của nó có thể rỗng; cần kiểm soát cache warm-up, TTL, invalidation và tải dồn lên database khi cache miss.

Nếu tất cả replica cùng khởi động lại và đồng thời nạp cache, có thể tạo thundering herd. Dùng jitter, request coalescing, rate limit hoặc warm-up theo từng nhóm.

## 6. Nhân bản workload stateful và bảo vệ dữ liệu

Workload stateful cần lưu trạng thái giữa các lần gọi. Ví dụ gồm database, message broker, distributed cache, file service và hệ thống lưu trữ.

Có thể nhân bản stateful bằng:

- Replication ở cấp ứng dụng hoặc database.
- Storage có replication đa AZ do cloud provider quản lý.
- Cluster có quorum và leader election.
- Durable queue với broker hoặc storage phân tán.
- Snapshot/backup được lưu ở failure domain khác.

Không phải mọi loại dữ liệu đều cần đồng bộ từng mili giây. Lựa chọn phụ thuộc RPO, RTO, độ trễ, consistency model và chi phí.

### 6.1. Synchronous replication

Synchronous replication thường chỉ xác nhận ghi sau khi dữ liệu được ghi tới các bản sao theo điều kiện commit của hệ thống. Nó có thể giảm mất dữ liệu khi primary lỗi, nhưng làm tăng latency ghi và phụ thuộc vào kết nối giữa các zone.

Khi mạng giữa các zone chậm hoặc bị chia cắt, hệ thống có thể từ chối ghi hoặc giảm availability để giữ consistency. Đây là trade-off cần được xác định theo database và yêu cầu nghiệp vụ.

### 6.2. Asynchronous replication

Asynchronous replication cho phép primary xác nhận ghi trước khi replica nhận đủ dữ liệu. Latency thường thấp hơn, nhưng nếu primary lỗi đột ngột, các giao dịch chưa kịp replicate có thể bị mất khi failover.

Độ trễ replication cần được đo và cảnh báo. Một replica có thể đang online nhưng quá tụt hậu để promote an toàn.

### 6.3. Quorum và split-brain

Một số hệ thống phân tán cần quorum để xác định node nào có quyền commit hoặc giữ vai trò leader. Với ba voter độc lập, quorum thường cần đa số, tức hai voter. Khi một node mất, hai node còn lại vẫn có thể đạt quorum.

Split-brain xảy ra khi hai phía của một mạng phân vùng đều tin rằng mình là primary và cùng nhận ghi. Hậu quả có thể là dữ liệu xung đột hoặc không thể hợp nhất.

Để tránh split-brain:

- Dùng cơ chế consensus/quorum được hệ thống hỗ trợ.
- Có leader election với lease hoặc term/epoch rõ ràng.
- Fencing node cũ trước khi promote node mới.
- Không tự promote replica chỉ dựa vào timeout mà không xác minh trạng thái primary cũ.
- Kiểm thử network partition và phục hồi.

Không tự thiết kế thuật toán quorum hoặc fencing bằng script đơn giản cho database production. Hãy dùng cơ chế HA chính thức của database hoặc dịch vụ được quản lý.

## 7. Database multi-zone

Database thường là dependency quan trọng nhất của ứng dụng. Nếu API được nhân bản qua ba AZ nhưng database chỉ có một instance ở AZ A, database vẫn là SPOF.

Các mô hình thường gặp:

- Database managed multi-AZ với standby hoặc replication được provider quản lý.
- Database cluster có primary và replica ở nhiều AZ.
- Database phân tán với quorum.
- Primary/secondary do khách hàng tự vận hành.

Khi chọn mô hình, cần kiểm tra:

- Replica có nằm ở AZ khác không?
- Replication đồng bộ hay bất đồng bộ?
- Cơ chế phát hiện lỗi và promote là tự động hay thủ công?
- Endpoint có tự chuyển sang primary mới không?
- DNS cache và connection pool có cập nhật sau failover không?
- Ứng dụng xử lý transaction đang mở và retry ra sao?
- Có thể phục hồi nếu cả primary lẫn replica lỗi không?

### 7.1. Failover database

Quy trình failover thường gồm phát hiện primary không còn phục vụ, xác minh replica đủ điều kiện, fencing primary cũ, promote replica, cập nhật endpoint và cho ứng dụng kết nối lại.

Trong thời gian chuyển đổi:

- Connection hiện tại có thể bị đóng.
- Transaction chưa commit có thể rollback.
- Một số request có thể timeout dù transaction đã commit ở database.
- Client có thể retry và gây ghi trùng nếu không có idempotency.

Ứng dụng cần connection retry có backoff, transaction boundary rõ ràng và idempotency key cho các thao tác nghiệp vụ có thể được gửi lại.

### 7.2. Backup không thay thế replication

Replication giúp duy trì bản sao gần thời gian thực và hỗ trợ failover. Backup giúp phục hồi dữ liệu sau xóa nhầm, mã độc, lỗi logic hoặc hỏng dữ liệu được replicate sang bản sao.

Nếu một bản ghi bị xóa nhầm rồi thao tác xóa được replicate, replica cũng có thể mất bản ghi đó. Vì vậy, cần backup độc lập, retention phù hợp, bản sao bất biến hoặc được bảo vệ và kiểm thử restore định kỳ.

## 8. Tránh SPOF ở các thành phần phụ thuộc

Một hệ thống có nhiều app replica vẫn có thể ngừng hoạt động vì một thành phần dùng chung. Hãy lập dependency map từ client tới backend và kiểm tra từng điểm.

| Thành phần | SPOF có thể gặp | Cách giảm rủi ro |
|---|---|---|
| Load balancer | Một thiết bị hoặc endpoint duy nhất do khách hàng tự quản lý | Dùng dịch vụ load balancing có HA hoặc nhiều lớp entry point |
| DNS | Một resolver hoặc zone cấu hình sai | Dùng DNS managed có HA, nhiều authoritative endpoint và kiểm tra record |
| Database | Một primary không có replica phù hợp | Multi-AZ replication, failover và backup độc lập |
| Storage | Một volume hoặc file server duy nhất | Storage đa AZ, replication hoặc mount target theo zone |
| Queue/broker | Một broker hoặc node đơn lẻ | Cluster/broker managed có durability và replication |
| NAT/egress | Một NAT gateway hoặc router trong một AZ | Egress path dự phòng, NAT theo zone hoặc phương án failover |
| Identity/secret | Một endpoint hoặc secret service không có cache/HA phù hợp | Dùng dịch vụ managed, thiết kế refresh và cache an toàn |
| KMS/encryption | Key policy hoặc endpoint lỗi làm không thể đọc dữ liệu | Dự phòng endpoint, quyền truy cập và quy trình khôi phục key |
| Monitoring | Một collector duy nhất | Nhiều collector hoặc telemetry pipeline có buffer |
| Deployment pipeline | Một runner hoặc artifact server đơn lẻ | Runner và artifact được phân tán, lưu trữ bền vững |

Không phải mọi dependency cần được nhân bản do khách hàng tự triển khai. Một số dịch vụ managed đã có HA nội bộ, nhưng cần xác nhận scope, SLA, behavior khi zone lỗi và các quota liên quan.

### 8.1. Network path và egress

Một ứng dụng ở AZ B có thể vẫn phụ thuộc NAT gateway nằm ở AZ A để gọi API bên ngoài. Nếu AZ A mất, ứng dụng ở AZ B còn chạy nhưng mất đường egress.

Với workload cần hoạt động độc lập theo AZ, cân nhắc:

- NAT gateway hoặc egress path theo từng AZ.
- Route table không trỏ tất cả subnet vào một thiết bị duy nhất.
- Private endpoint hoặc service endpoint khi phù hợp.
- DNS resolver và network firewall có tính sẵn sàng phù hợp.
- Kiểm thử truy cập dependency từ từng AZ.

### 8.2. DNS và service discovery

DNS có thể trở thành điểm lỗi hoặc gây failover chậm nếu TTL quá dài, resolver không sẵn sàng hoặc health check không cập nhật record đúng cách. Cần xác định:

- DNS record có trỏ tới regional load balancer hay một IP instance?
- TTL và cache của client có ảnh hưởng tới chuyển đổi không?
- Resolver được cung cấp theo region/AZ hay do khách hàng tự vận hành?
- Service discovery có xóa endpoint không khỏe kịp thời không?
- Client có retry khi địa chỉ cũ còn trong cache không?

Không nên dùng DNS round-robin đơn giản như cơ chế HA duy nhất cho ứng dụng cần failover có kiểm soát.

## 9. Kubernetes: phân tán Pod qua nhiều zone

Kubernetes có thể đặt nhiều replica của Deployment lên các node khác nhau, nhưng nếu scheduler đặt tất cả Pod vào cùng một zone thì workload vẫn có SPOF ở cấp AZ.

### 9.1. Topology spread constraints

Topology spread constraints giúp phân tán Pod theo topology key, ví dụ zone hoặc hostname.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 6
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: catalog-api
      containers:
        - name: api
          image: registry.example/catalog-api:v3
          ports:
            - containerPort: 8080
~~~

Với sáu replica và ba zone có capacity, scheduler có thể phân phối cân bằng, thường là hai Pod mỗi zone. Cấu hình thực tế còn phụ thuộc node labels, node affinity, taint/toleration và capacity từng zone. DoNotSchedule có thể khiến Pod Pending nếu không thể đạt điều kiện spread; hãy cân nhắc behavior khi một zone đã mất.

### 9.2. Pod anti-affinity

Pod anti-affinity có thể ngăn các replica cùng ứng dụng đặt trên cùng node hoặc zone theo topology key. Hard anti-affinity giúp tăng tách biệt nhưng có thể khiến Pod không được schedule khi thiếu node phù hợp. Soft preference linh hoạt hơn nhưng không bảo đảm phân tán tuyệt đối.

Hãy chọn mức ràng buộc theo mục tiêu availability và capacity thực tế. Topology spread constraints thường hữu ích khi muốn cân bằng số Pod giữa các zone.

### 9.3. PodDisruptionBudget

PodDisruptionBudget (PDB) giới hạn số Pod có thể bị gián đoạn trong một số voluntary disruption như drain node. PDB hỗ trợ bảo vệ số replica sẵn sàng trong bảo trì, nhưng không ngăn được lỗi node hoặc zone đột ngột và không tự tạo thêm capacity.

PDB cần được thiết kế cùng số replica, topology spread, autoscaling và quy trình bảo trì. Không dùng PDB như bằng chứng duy nhất rằng ứng dụng chịu được mất một zone.

### 9.4. Node pool và cluster

Node pool nên có node ở nhiều AZ. Cần xác minh:

- Node labels phản ánh zone chính xác.
- Autoscaler có thể tạo node ở zone còn capacity.
- Persistent volume có topology phù hợp.
- Pod có thể được reschedule khi zone mất.
- Ingress/load balancer có backend ở các zone còn lại.
- Cluster control plane và API endpoint có mô hình HA được provider hỗ trợ.

Persistent volume gắn với một zone có thể không di chuyển tức thời sang zone khác. Stateful workload cần storage và database architecture hỗ trợ failover, không chỉ dựa vào việc Pod có thể reschedule.

## 10. StatefulSet, volume và dữ liệu theo zone

Kubernetes StatefulSet cung cấp danh tính mạng và thứ tự ổn định cho Pod, nhưng bản thân StatefulSet không tự nhân bản dữ liệu. Nếu mỗi Pod dùng một persistent volume ở một zone, việc Pod chuyển zone có thể bị giới hạn bởi topology của volume.

Đối với database hoặc broker:

- Dùng operator hoặc cơ chế cluster được nhà cung cấp hỗ trợ.
- Đặt replica ở nhiều zone và kiểm tra quorum.
- Xác định volume có thể attach ở zone khác hay cần bản sao riêng.
- Theo dõi replication lag và trạng thái leader.
- Kiểm thử node/zone failure và restore.

Không tạo nhiều bản sao Pod database dùng chung một volume ghi nếu database engine không hỗ trợ chế độ đó. Storage replication và database replication là hai lớp khác nhau, cần tuân theo kiến trúc của sản phẩm.

## 11. RTO, RPO và mục tiêu phục hồi

Thiết kế HA cần có mục tiêu đo được:

- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận để khôi phục dịch vụ sau sự cố.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận mất, thường diễn đạt bằng khoảng thời gian dữ liệu.

Ví dụ:

- API stateless có thể có RTO vài phút nếu replica còn lại nhận traffic nhanh.
- Database đồng bộ đa AZ có thể có RPO rất thấp trong điều kiện được hỗ trợ, nhưng vẫn cần xác nhận semantics và failure mode của dịch vụ.
- Backup hàng ngày có thể tạo RPO gần một ngày nếu không có log shipping hoặc replication khác.

RTO/RPO phải xuất phát từ yêu cầu nghiệp vụ, không chọn theo khả năng của một dịch vụ riêng lẻ.

### 11.1. Các giai đoạn tạo nên RTO

RTO có thể được phân tích thành các khoảng:

~~~text
RTO = T_detect + T_decide + T_promote + T_route + T_verify
~~~

Trong đó:

- T_detect: thời gian phát hiện lỗi.
- T_decide: thời gian quyết định hoặc kích hoạt failover.
- T_promote: thời gian khởi động hoặc promote replica.
- T_route: thời gian chuyển traffic hoặc kết nối.
- T_verify: thời gian xác minh dịch vụ phục hồi.

Đo từng phần giúp tìm bước làm failover chậm. Nếu DNS cache chiếm phần lớn thời gian, tăng số replica ứng dụng sẽ không cải thiện RTO.

### 11.2. RPO và replication lag

Với replication bất đồng bộ, RPO thực tế phụ thuộc dữ liệu đã được truyền và xác nhận tại thời điểm primary lỗi. Theo dõi replication lag, WAL/binlog/stream offset hoặc chỉ số tương ứng. Không chỉ nhìn replica ở trạng thái healthy; cần xác nhận độ mới của dữ liệu trước khi promote.

### 11.3. Kiểm thử restore

Backup chỉ có giá trị khi có thể phục hồi. Cần diễn tập:

- Khôi phục database từ backup.
- Áp dụng transaction log hoặc point-in-time recovery nếu có.
- Khôi phục file/object và quyền truy cập.
- Khởi chạy workload từ image dự phòng.
- Xác minh dữ liệu và chức năng nghiệp vụ.

Ghi lại thời gian restore thực tế và so sánh với RTO/RPO đã cam kết.

## 12. Failover và failback

Failover là chuyển workload sang thành phần hoặc zone dự phòng khi thành phần chính lỗi. Failback là đưa hệ thống trở về trạng thái vận hành bình thường hoặc vị trí ưu tiên sau khi sự cố được xử lý.

### 12.1. Failover tự động và thủ công

Failover tự động giảm thời gian phản ứng nhưng có nguy cơ false positive nếu health check quá nhạy hoặc network partition làm primary vẫn chạy nhưng không thể được quan sát. Failover thủ công giảm rủi ro quyết định sai nhưng tăng RTO do cần người vận hành.

Có thể tự động failover cho các lỗi có tín hiệu đáng tin cậy và quy trình đã kiểm thử; yêu cầu phê duyệt thủ công cho các thao tác có nguy cơ mất dữ liệu hoặc split-brain.

### 12.2. Quy trình failover ứng dụng

1. Health check xác định replica hoặc zone không còn phục vụ.
2. Load balancer ngừng gửi traffic tới backend lỗi.
3. Replica còn lại nhận thêm request trong giới hạn capacity.
4. Autoscaler bổ sung capacity nếu cần và nếu còn quota.
5. Monitoring xác nhận latency, error rate và saturation.

### 12.3. Quy trình failover database

1. Phát hiện primary lỗi bằng health check và cơ chế consensus.
2. Xác minh replica đủ mới và có quyền trở thành primary.
3. Fencing primary cũ hoặc bảo đảm nó không thể tiếp tục ghi.
4. Promote replica theo quy trình của database.
5. Cập nhật endpoint và cho connection pool kết nối lại.
6. Xác minh transaction, replication và tính nhất quán.
7. Theo dõi hệ thống trước khi khôi phục topology dự phòng.

### 12.4. Failback cần có kế hoạch

Không nên đưa traffic trở lại zone vừa phục hồi ngay khi máy có thể ping. Cần:

- Xác nhận nguyên nhân sự cố đã được xử lý.
- Đồng bộ dữ liệu về node/zone được phục hồi.
- Kiểm tra replication lag và role primary/standby.
- Xác nhận capacity và network.
- Thực hiện chuyển traffic từng bước.
- Theo dõi metric và chuẩn bị rollback nếu lỗi tái diễn.

## 13. Các điểm lỗi chung thường bị bỏ sót

Một kiến trúc nhìn có vẻ multi-zone vẫn có thể có SPOF ở những thành phần sau:

### 13.1. Một cấu hình hoặc secret dùng chung bị lỗi

Nếu mọi replica cùng tải một cấu hình sai hoặc secret đã hết hạn, toàn bộ zone có thể lỗi cùng lúc. Cần versioning cấu hình, rollout có kiểm soát, kiểm tra secret rotation và khả năng rollback.

### 13.2. Một image lỗi được triển khai đồng loạt

Multi-zone không giúp ích nếu cùng một image lỗi được deploy tới tất cả AZ. Dùng canary, rolling deployment, kiểm tra health và khả năng dừng rollout.

### 13.3. Một dịch vụ bên ngoài duy nhất

Ứng dụng có thể phụ thuộc một API thanh toán, email hoặc identity provider bên ngoài. Cần xác định behavior khi dependency đó lỗi: timeout, retry, queue, fallback hoặc degraded mode.

### 13.4. Một đường egress duy nhất

Các subnet ở nhiều AZ có thể cùng route ra một NAT gateway. Nếu gateway hoặc AZ chứa gateway lỗi, toàn bộ workload mất kết nối ra ngoài. Cần đánh giá route table và thiết kế egress theo zone.

### 13.5. Một người hoặc một quy trình vận hành duy nhất

Runbook chỉ một người hiểu, credential break-glass không kiểm thử hoặc pipeline deploy chỉ chạy ở một runner cũng có thể làm chậm phục hồi. Cần tài liệu hóa, phân quyền phù hợp và diễn tập cho nhóm trực.

## 14. Kiểm thử khả năng chịu lỗi

Không thể kết luận hệ thống HA chỉ từ sơ đồ kiến trúc. Phải tạo tình huống lỗi có kiểm soát và đo hành vi thực tế.

Các bài kiểm thử:

1. Dừng một VM hoặc Pod.
2. Drain một node Kubernetes.
3. Tạm ngừng backend ở một AZ trong môi trường thử nghiệm.
4. Mô phỏng database primary failover.
5. Kiểm tra replication lag trước và sau failover.
6. Ngắt một network path hoặc egress dependency trong môi trường kiểm thử.
7. Làm chậm DNS hoặc dependency để kiểm tra timeout và retry.
8. Scale workload lên mức tải cao khi một AZ đã bị loại.
9. Kiểm tra backup restore trong một failure domain khác.
10. Kiểm tra failback sau khi zone phục hồi.

### 14.1. Tiêu chí đạt

- Workload còn lại nhận traffic theo đúng health policy.
- Capacity còn lại không vượt ngưỡng saturation.
- Error rate và latency nằm trong mục tiêu hoặc phục hồi trong RTO.
- Dữ liệu mất nằm trong RPO.
- Không xảy ra split-brain hoặc ghi trùng ngoài kiểm soát.
- Alert phát hiện sự cố và runbook hướng dẫn đúng bước.
- Failback không gây gián đoạn hoặc mất dữ liệu ngoài dự kiến.

### 14.2. Chaos engineering

Chaos engineering chủ động đưa lỗi vào hệ thống để kiểm tra giả thuyết về khả năng chịu lỗi. Bắt đầu từ phạm vi nhỏ, môi trường thử nghiệm hoặc canary, có giới hạn blast radius, điều kiện dừng và người chịu trách nhiệm.

Không nên tắt cả một AZ production lần đầu tiên chỉ để xem hệ thống có hoạt động không. Hãy xây dựng diễn tập tăng dần, dùng game day và chỉ mở rộng khi các kiểm soát đã chứng minh hiệu quả.

## 15. Quan sát hệ thống multi-zone

Dashboard HA nên cho thấy trạng thái theo từng zone và toàn dịch vụ:

- Số replica khỏe mạnh theo AZ.
- Request rate và traffic share theo AZ.
- CPU, memory, network và queue depth theo AZ.
- Backend unhealthy và thời gian health check.
- Database primary/replica role và replication lag.
- Failover event và thời gian từng giai đoạn.
- Error rate, p95/p99 latency và SLO.
- Capacity còn lại khi loại một zone.
- Trạng thái NAT, DNS, storage endpoint và dependency quan trọng.

Tránh chỉ hiển thị metric tổng hợp toàn region. Nếu AZ A quá tải còn AZ B nhàn rỗi, số trung bình toàn hệ thống có thể che mất vấn đề.

### 15.1. Cảnh báo theo zone

Nên cảnh báo khi:

- Một AZ không còn replica khỏe.
- Traffic phân phối lệch bất thường.
- Replica count giảm dưới mức chịu lỗi.
- Capacity còn lại không đủ chịu mất một zone.
- Replication lag vượt ngưỡng nghiệp vụ.
- Database failover hoặc leader election kéo dài.
- Một đường network/egress quan trọng không còn dự phòng.

### 15.2. SLO và error budget

Đo availability theo request thành công và mục tiêu SLO của dịch vụ. Một VM vẫn healthy nhưng mọi request đều timeout tới database không có nghĩa ứng dụng đang available. SLO nên phản ánh hành vi người dùng và các giao dịch quan trọng.

## 16. Ví dụ kiến trúc: API thương mại điện tử qua ba AZ

Một hệ thống bán hàng cần phục vụ API catalog và order liên tục. Kiến trúc tham khảo:

| Thành phần | Thiết kế | Mục tiêu |
|---|---|---|
| Entry point | Regional load balancer | Tiếp nhận traffic và kiểm tra backend |
| API | Sáu replica, phân bố hai replica mỗi AZ | Chịu mất một AZ và tiếp tục phục vụ |
| Worker | Nhiều worker đọc durable queue | Xử lý bất đồng bộ và phân tán tải |
| Database | Managed database multi-AZ hoặc cluster có failover | Duy trì dữ liệu và endpoint ghi |
| Session | Token hoặc kho session dùng chung | Không phụ thuộc local memory |
| File | Object storage có durability/replication theo dịch vụ | Không lưu file duy nhất trên VM |
| Egress | NAT/route dự phòng theo AZ hoặc private endpoint | Tránh một đường ra ngoài duy nhất |
| Observability | Metric, log và alert theo zone | Phát hiện lệch tải và failover |

Trong kịch bản AZ B mất:

1. Load balancer ngừng gửi traffic tới backend ở AZ B.
2. Bốn replica ở AZ A và C tiếp nhận request.
3. Hệ thống kiểm tra capacity; nếu cần, autoscaler bổ sung instance ở hai AZ còn lại.
4. Worker tiếp tục lấy message từ durable queue.
5. Database multi-AZ thực hiện failover nếu primary nằm ở AZ B.
6. API xử lý connection reset và retry an toàn.
7. Monitoring xác nhận latency, error rate, database role và queue depth.

Kiến trúc chỉ đạt mục tiêu nếu bốn replica còn lại có đủ capacity, database có thể failover, egress không phụ thuộc AZ B và các secret/configuration vẫn truy cập được.

## 17. Ví dụ cấu hình phân bố VM qua nhiều AZ

Ví dụ Terraform rút gọn cho một nhóm EC2 Auto Scaling sử dụng subnet ở nhiều AZ:

~~~hcl
resource "aws_launch_template" "api" {
  name_prefix   = "catalog-api-"
  image_id      = var.approved_ami_id
  instance_type = "m6i.large"

  user_data = base64encode(var.bootstrap_script)
}

resource "aws_autoscaling_group" "api" {
  name                = "catalog-api-multi-az"
  min_size            = 6
  desired_capacity    = 6
  max_size            = 12
  vpc_zone_identifier = var.private_subnet_ids

  launch_template {
    id      = aws_launch_template.api.id
    version = "$Latest"
  }

  health_check_type         = "ELB"
  health_check_grace_period = 180

  target_group_arns = [var.api_target_group_arn]
}
~~~

Trong ví dụ, private subnet được truyền từ nhiều AZ và nhóm có tối thiểu sáu instance. Cần xác minh danh sách subnet thực sự thuộc các AZ khác nhau; chỉ truyền nhiều subnet trong cùng một AZ không tạo ra multi-zone.

Để dùng trong production, cần bổ sung security group, IAM instance profile, metadata options, rolling instance refresh, scaling policy, health check phù hợp và cấu hình load balancer. Cũng cần xác minh quota và capacity của instance family tại từng AZ.

### 17.1. Những gì ví dụ chưa tự bảo đảm

Auto Scaling Group có thể phân phối instance qua subnet nhưng không tự giải quyết mọi SPOF:

- Database phải có HA riêng.
- Storage và file upload phải tồn tại ngoài local disk.
- Egress path cần được phân tán.
- Bootstrap phải lấy cấu hình và secret từ dịch vụ có tính sẵn sàng.
- Ứng dụng phải stateless hoặc có session/data replication.
- Health check cần phản ánh khả năng nhận traffic.

## 18. Chi phí và trade-off của multi-zone

Multi-zone tăng khả năng chịu lỗi nhưng cũng tăng chi phí và độ phức tạp:

- Chạy nhiều VM/Pod hơn để có capacity dự phòng.
- Replication và cross-zone data transfer.
- Load balancer, NAT hoặc endpoint theo zone.
- Storage replica, database standby hoặc license.
- Monitoring, backup và diễn tập.
- Chi phí vận hành cho quy trình failover/failback.

Không nên giảm số replica xuống mức không còn chịu được mất một zone chỉ để tiết kiệm chi phí nếu mục tiêu availability vẫn yêu cầu multi-zone. Có thể tối ưu bằng autoscaling, instance family phù hợp và capacity policy, nhưng phải giữ năng lực dự phòng đã cam kết.

### 18.1. Tối ưu theo mức quan trọng

Không phải mọi workload đều cần cùng mức HA:

- Dịch vụ giao dịch cốt lõi có thể cần multi-zone và database failover.
- Batch có thể chạy lại từ checkpoint và chấp nhận RTO dài hơn.
- Môi trường development có thể dùng ít replica hơn.
- Tác vụ phân tích có thể được ưu tiên chạy khi còn capacity.

Phân loại theo business criticality giúp cân bằng chi phí với tác động sự cố.

## 19. Những sai lầm thường gặp

- **Chạy nhiều VM trong một AZ rồi gọi là multi-zone:** toàn bộ workload vẫn có thể mất khi zone lỗi.
- **Chỉ nhân bản tầng ứng dụng:** database, storage, NAT hoặc DNS vẫn là SPOF.
- **Không tính capacity sau khi mất một zone:** replica còn lại quá tải ngay khi failover.
- **Dùng health check chỉ kiểm tra process:** backend có thể healthy nhưng không phục vụ được nghiệp vụ.
- **Giữ session trong RAM của một replica:** request sau failover mất session hoặc phải đăng nhập lại.
- **Giả định autoscaling diễn ra tức thời:** capacity mới có thể mất nhiều phút hoặc không tạo được do quota.
- **Không theo dõi replication lag:** promote replica cũ có thể mất dữ liệu vượt RPO.
- **Không fencing primary cũ:** có thể tạo split-brain.
- **Coi PDB là bảo vệ zone failure:** PDB chủ yếu điều phối voluntary disruption, không ngăn lỗi zone đột ngột.
- **Cho rằng StatefulSet tự nhân bản dữ liệu:** Pod replica không đồng nghĩa dữ liệu đã được replicate.
- **Không kiểm thử failback:** chuyển traffic trở lại có thể gây lỗi lần hai.
- **Chỉ xem metric toàn region:** không nhận ra một zone đang quá tải hoặc mất replica.

## 20. Checklist thiết kế và kiểm thử multi-zone

Trước khi đưa workload vào production, hãy xác nhận:

- [ ] Các replica thực sự nằm ở ít nhất hai AZ độc lập.
- [ ] Load balancer có backend khỏe mạnh ở nhiều AZ.
- [ ] Health check và readiness phản ánh khả năng phục vụ.
- [ ] Capacity còn lại đủ khi mất một AZ theo kịch bản đã chọn.
- [ ] Autoscaling có quota và subnet ở các AZ còn lại.
- [ ] Session, file và trạng thái ứng dụng không phụ thuộc local disk/memory của một VM.
- [ ] Database có replication và failover phù hợp với RPO/RTO.
- [ ] Có quorum/fencing hoặc cơ chế chống split-brain cho hệ thống cần leader.
- [ ] Backup độc lập và restore đã được kiểm thử.
- [ ] DNS, NAT/egress, secret, identity, queue và storage không tạo SPOF ẩn.
- [ ] Kubernetes có topology spread/anti-affinity phù hợp và node ở nhiều zone.
- [ ] Alert và dashboard thể hiện tình trạng theo từng AZ.
- [ ] Đã diễn tập mất VM, node, AZ và failback trong phạm vi an toàn.
- [ ] Runbook, owner và quy trình escalation đã được xác định.

## 21. Quy trình triển khai và duy trì

Có thể áp dụng quy trình sau:

1. **Xác định SLO:** thống nhất availability, RTO và RPO với chủ sở hữu nghiệp vụ.
2. **Lập dependency map:** liệt kê app, database, storage, network, DNS, identity và dịch vụ ngoài.
3. **Xác định failure domain:** chọn các AZ và loại sự cố cần chịu được.
4. **Thiết kế placement:** phân tán VM, Pod, worker và database replica.
5. **Tính capacity:** xác nhận phần còn lại đủ tải sau khi mất zone.
6. **Thiết kế dữ liệu:** chọn replication, quorum, backup và consistency phù hợp.
7. **Thiết kế traffic:** cấu hình health check, routing, drain và retry.
8. **Kiểm thử:** mô phỏng lỗi theo từng lớp và đo RTO/RPO.
9. **Vận hành:** theo dõi metric theo zone, replication lag và capacity headroom.
10. **Rà soát định kỳ:** kiểm tra SPOF mới phát sinh do thay đổi kiến trúc, route hoặc dependency.

## 22. Ghi nhớ

Nhân bản workload qua nhiều zone giúp giảm nguy cơ một sự cố hạ tầng làm ngừng toàn bộ dịch vụ. Tuy nhiên, HA chỉ thực sự hiệu quả khi placement, load balancing, capacity, dữ liệu và các dependency quan trọng cùng được thiết kế để chịu lỗi.

Workload stateless thường phù hợp với active-active; workload stateful cần replication, quorum, fencing và quy trình failover rõ ràng. Hãy tính capacity sau khi mất một zone, bảo vệ database bằng replication và backup độc lập, kiểm tra cả DNS/NAT/identity/secret/queue, rồi diễn tập failover và failback. Đo RTO, RPO, latency và error rate thực tế để chứng minh hệ thống đáp ứng mục tiêu sẵn sàng đã đặt ra.
