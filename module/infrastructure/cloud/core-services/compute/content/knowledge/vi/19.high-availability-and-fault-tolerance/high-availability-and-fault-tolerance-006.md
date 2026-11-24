# Chọn active-active hoặc active-passive theo yêu cầu dịch vụ

Khi một máy chủ, availability zone (AZ) hoặc region gặp sự cố, dịch vụ cần tiếp tục xử lý yêu cầu trong giới hạn gián đoạn và mất dữ liệu đã chấp nhận. Hai mô hình thường được dùng là **active-active** và **active-passive**. Trong active-active, nhiều site hoặc nhóm tài nguyên cùng phục vụ traffic. Trong active-passive, một site phục vụ chính còn site khác giữ vai trò dự phòng và chỉ tiếp quản khi cần.

Không có mô hình nào luôn tốt hơn. Active-active có thể giảm thời gian chuyển traffic và tận dụng tài nguyên dự phòng, nhưng đòi hỏi thiết kế dữ liệu, đồng bộ trạng thái và xử lý xung đột phức tạp hơn. Active-passive thường dễ duy trì một nguồn ghi chính và đơn giản hóa nhất quán dữ liệu, nhưng cần quy trình failover tin cậy và có thể để tài nguyên standby nhàn rỗi.

Việc lựa chọn phải bắt đầu từ yêu cầu **RTO**, **RPO**, phạm vi lỗi cần chịu đựng, kiểu workload, khả năng đồng bộ dữ liệu, chi phí và năng lực vận hành. Bài học này trình bày cách đánh giá hai mô hình cho ứng dụng trên VM, container và dịch vụ cloud, đồng thời chỉ ra những thành phần cần kiểm thử trước khi đưa vào production.

## 1. High availability và fault tolerance

**High availability (HA)** là khả năng duy trì dịch vụ hoạt động với mức gián đoạn thấp khi một hoặc nhiều thành phần gặp lỗi. HA thường đạt được bằng dự phòng, health check, failover, phân tán failure domain và tự động khôi phục.

**Fault tolerance** là khả năng tiếp tục hoạt động khi một thành phần lỗi, thường với mức gián đoạn rất thấp hoặc không gián đoạn ở phạm vi lỗi đã xác định. Mức fault tolerance cao thường cần thiết kế sâu hơn ở cả compute, network, storage, data và ứng dụng.

Các thuật ngữ này không nên được dùng như cam kết tuyệt đối. Một hệ thống HA vẫn có thể gián đoạn khi lỗi vượt quá giả định thiết kế, khi dependency chung bị lỗi hoặc khi quá trình failover không thành công.

### Dự phòng không đồng nghĩa với sẵn sàng

Có thêm một VM hoặc một region chưa đủ để chứng minh dịch vụ có HA. Cần xác minh:

- Tài nguyên dự phòng có nằm trong failure domain độc lập không.
- Standby có đủ CPU, RAM, network và storage để tiếp nhận tải không.
- Dữ liệu cần thiết có sẵn và đủ mới không.
- Traffic có thể được chuyển sang nơi còn khỏe mạnh không.
- Danh tính, secret, certificate và quyền truy cập có hoạt động ở site dự phòng không.
- Ứng dụng có khởi động và phục vụ đúng sau khi failover không.
- Đội vận hành có phát hiện, quyết định và khôi phục được trong thời gian mục tiêu không.

Một standby cùng nằm trên host, rack hoặc AZ với primary có thể bị mất cùng sự cố. Thiết kế HA phải xác định rõ failure domain mà hệ thống cần sống sót.

## 2. RTO và RPO: yêu cầu kinh doanh trước khi chọn mô hình

Hai chỉ số quan trọng nhất khi thiết kế HA và disaster recovery (DR) là RTO và RPO.

- **Recovery Time Objective (RTO):** khoảng thời gian gián đoạn tối đa mà tổ chức chấp nhận trước khi dịch vụ phải được khôi phục.
- **Recovery Point Objective (RPO):** lượng dữ liệu tối đa có thể mất, thường được biểu diễn bằng khoảng thời gian dữ liệu trước sự cố.

Ví dụ, một dịch vụ đặt RTO 10 phút và RPO 1 phút. Khi sự cố xảy ra, tổ chức muốn khôi phục dịch vụ trong tối đa 10 phút và chấp nhận mất không quá khoảng một phút dữ liệu theo định nghĩa và cách đo đã thống nhất.

### RTO không chỉ là thời gian boot máy

RTO thực tế có thể bao gồm:

1. Phát hiện lỗi.
2. Xác minh lỗi có phải sự cố thật hay không.
3. Ra quyết định failover.
4. Fencing hoặc cô lập primary cũ nếu cần.
5. Promote database hoặc storage replica.
6. Khởi động/scale ứng dụng.
7. Cập nhật route, load balancer hoặc DNS.
8. Kiểm tra readiness và smoke test.
9. Cho phép traffic trở lại.
10. Xác nhận nghiệp vụ hoạt động bình thường.

Một VM có thể boot trong hai phút nhưng dịch vụ vẫn chưa phục hồi vì database chưa promote, secret chưa có, route chưa cập nhật hoặc ứng dụng chưa warm-up.

### RPO phụ thuộc cách sao chép dữ liệu

- **Synchronous replication:** thao tác ghi thường chỉ được xác nhận sau khi dữ liệu được lưu ở các replica theo điều kiện đồng bộ. Có thể đạt RPO gần 0 hoặc bằng 0 trong phạm vi cam kết của hệ thống, nhưng tăng latency và phụ thuộc kết nối giữa các site.
- **Asynchronous replication:** primary xác nhận ghi trước khi replica nhận đủ dữ liệu. Hiệu năng và khoảng cách địa lý linh hoạt hơn, nhưng có thể mất các giao dịch chưa được sao chép khi primary hỏng.
- **Periodic backup/snapshot:** dữ liệu được lưu theo chu kỳ. RPO có thể bằng khoảng thời gian giữa các lần backup, cộng thêm các yếu tố vận hành.

Không suy ra RPO chỉ từ tên active-active hay active-passive. Một hệ thống active-active dùng replication bất đồng bộ vẫn có thể mất dữ liệu đã xác nhận ở site khác trong một số tình huống. Một hệ thống active-passive dùng replication đồng bộ có thể có RPO rất thấp nhưng failover vẫn mất thời gian.

### RTO/RPO cần được đo bằng diễn tập

RTO và RPO là mục tiêu cho đến khi được kiểm chứng. Hãy đo thời gian từ lúc tạo lỗi đến lúc giao dịch thành công trở lại, đồng thời đối chiếu dữ liệu trước/sau để xác định lượng mất hoặc trùng lặp.

## 3. Mô hình active-active

Active-active có ít nhất hai site, zone hoặc nhóm tài nguyên đang phục vụ traffic cùng lúc. Traffic có thể được phân phối theo tỷ trọng, vị trí địa lý, latency, hash hoặc thuật toán cân bằng tải.

### Kiến trúc tổng quát

~~~mermaid
flowchart TB
    C["Clients"] --> G["Global traffic manager"]
    G --> A["Site A - active"]
    G --> B["Site B - active"]
    A --> ALB["Local load balancer A"]
    B --> BLB["Local load balancer B"]
    ALB --> A1["App replicas A"]
    BLB --> B1["App replicas B"]
    A1 --> D["Data layer / replication"]
    B1 --> D
~~~

Cả Site A và Site B nhận request. Tầng data có thể là database phân tán, multi-primary, partitioned data hoặc một mô hình ghi có điều phối. Không mặc định hai site cùng ghi mọi dữ liệu vào hai database độc lập rồi tự động hợp nhất.

### Ưu điểm

- Cả hai site đều đóng góp capacity khi bình thường.
- Có thể chuyển traffic nhanh sang site còn lại khi một site lỗi.
- Tài nguyên dự phòng được sử dụng thường xuyên, giảm tình trạng standby hoàn toàn nhàn rỗi.
- Có thể đặt traffic gần người dùng để giảm latency.
- Có thể bảo trì một site trong khi site còn lại tiếp tục phục vụ, nếu đủ capacity.

### Chi phí và độ phức tạp

- Cần đồng bộ hoặc phân vùng dữ liệu.
- Cần xử lý xung đột ghi và consistency.
- Cần tránh hai site cùng nhận traffic nhưng một dependency chỉ chịu được tải của một site.
- Cần thiết kế identity, session, cache và queue dùng chung hoặc đồng bộ.
- Cần kiểm soát split-brain khi network partition.
- Cần kiểm thử traffic shift, failover và failback.
- Cần giám sát replication lag và trạng thái từng site.

### Active-active ở một tầng không có nghĩa toàn hệ thống active-active

Ứng dụng có thể chạy active-active ở hai AZ trong khi database dùng một primary duy nhất với standby. Đây là mô hình phổ biến và có thể hợp lý. Tương tự, load balancer có thể gửi traffic tới nhiều web server nhưng file storage hoặc queue phía sau vẫn có một vùng ghi chính.

Khi mô tả kiến trúc, hãy ghi rõ active-active áp dụng ở tầng nào: frontend, application, database, storage, message broker hay toàn bộ stack.

## 4. Mô hình active-passive

Active-passive có một site hoặc nhóm tài nguyên chính đang phục vụ traffic. Site còn lại ở trạng thái standby, được giữ sẵn để tiếp quản khi primary không còn đáp ứng.

### Kiến trúc tổng quát

~~~mermaid
flowchart TB
    C["Clients"] --> G["Traffic manager"]
    G --> P["Primary site - active"]
    G -. "Failover khi primary lỗi" .-> S["Secondary site - passive"]
    P --> PA["Application + primary data"]
    S --> SA["Standby application + replicated data"]
    PA -->|Replication| SA
~~~

Ở trạng thái bình thường, traffic chủ yếu tới primary. Secondary nhận bản sao dữ liệu và có thể chạy một phần thành phần cần thiết, nhưng không nhận traffic production thông thường cho workload chính.

Khi primary lỗi, quy trình sẽ cô lập hoặc fencing primary nếu cần, promote dữ liệu ở secondary, khởi động hoặc mở rộng ứng dụng và chuyển traffic.

### Các mức standby

| Kiểu standby | Trạng thái tài nguyên | Thời gian khôi phục tương đối | Chi phí tương đối |
|---|---|---|---|
| Cold standby | Chỉ giữ backup/image/config; cần cấp máy khi có sự cố | Dài hơn | Thấp hơn |
| Warm standby | Một phần tài nguyên đã chạy, dữ liệu được replicate; cần scale hoặc hoàn tất khởi tạo | Trung bình | Trung bình |
| Hot standby | Tài nguyên và ứng dụng gần như sẵn sàng, dữ liệu được cập nhật liên tục | Ngắn hơn | Cao hơn |

Tên gọi cold/warm/hot không phải lúc nào cũng có định nghĩa giống nhau giữa nhà cung cấp. Cần mô tả trạng thái cụ thể: VM đã boot chưa, ứng dụng đã chạy chưa, database replica đã sẵn sàng promote chưa, route đã chuẩn bị chưa và secret có truy cập được không.

### Ưu điểm

- Có thể giữ một nguồn ghi chính, giảm độ phức tạp của multi-writer.
- Dễ xác định nơi nhận traffic bình thường.
- Có thể giảm chi phí compute nếu standby không cần chạy đầy đủ.
- Quy trình data consistency thường đơn giản hơn active-active.
- Phù hợp với workload có RTO vài phút hoặc lâu hơn và RPO được replication hỗ trợ.

### Hạn chế

- Standby có thể không đủ capacity nếu chưa được kiểm thử.
- Failover có thể mất thời gian vì cần promote data, scale app và đổi route.
- Standby ít được dùng thường xuyên nên lỗi cấu hình có thể không bị phát hiện.
- Khi failover, toàn bộ tải chuyển sang một site nên cần capacity dự phòng.
- Failback về primary cũ có thể phức tạp nếu dữ liệu đã thay đổi ở secondary.

## 5. So sánh active-active và active-passive

| Tiêu chí | Active-active | Active-passive |
|---|---|---|
| Traffic bình thường | Nhiều site cùng phục vụ | Chủ yếu một site phục vụ |
| Sử dụng tài nguyên | Cả hai site đóng góp capacity | Standby có thể nhàn rỗi hoặc chạy một phần |
| Failover traffic | Chuyển tỷ trọng sang site còn lại | Chuyển vai trò và traffic sang standby |
| Data architecture | Cần phân vùng, multi-writer hoặc cơ chế ghi có điều phối | Thường dễ duy trì single-writer |
| Xung đột ghi | Có thể xuất hiện ở multi-primary | Thấp hơn nếu fencing và promotion đúng |
| RTO | Có thể thấp nếu data và routing đã sẵn sàng | Phụ thuộc thời gian promote, scale và chuyển traffic |
| RPO | Phụ thuộc replication/consistency | Phụ thuộc replication/backup |
| Chi phí compute | Cao hơn baseline nhưng tài nguyên được dùng | Từ thấp đến cao tùy cold/warm/hot |
| Vận hành | Phức tạp về consistency và traffic | Phức tạp về failover/failback và standby drift |
| Phù hợp | Global service, tải lớn, cần phục vụ liên tục và có khả năng xử lý dữ liệu phân tán | Hệ thống cần DR, workload single-writer, RTO/RPO cho phép chuyển vai trò |

Không nên chọn active-active chỉ vì muốn có RTO thấp. Nếu database không thể xử lý multi-writer và không có thiết kế phân vùng dữ liệu, active-active ở toàn bộ tầng có thể tạo rủi ro lớn hơn lợi ích.

## 6. Chọn theo RTO, RPO và mức độ quan trọng của dịch vụ

Bắt đầu bằng cách phân loại dịch vụ theo tác động kinh doanh.

| Yêu cầu | Thiết kế có thể cân nhắc | Điểm phải xác minh |
|---|---|---|
| RTO rất thấp, RPO gần 0 | Active-active hoặc hot standby với replication đồng bộ phù hợp | Latency replication, fencing, capacity khi mất site |
| RTO vài phút, RPO vài giây/phút | Warm/hot active-passive hoặc active-active theo tầng | Replication lag, promote time, routing |
| RTO hàng chục phút, RPO theo chu kỳ backup | Cold/warm standby và backup/restore | Thời gian cấp máy, restore, DNS và kiểm tra dữ liệu |
| Dịch vụ đọc nhiều, dữ liệu phân vùng theo vùng | Active-active có thể phù hợp | Read/write routing, consistency và failover |
| Workload single-writer, giao dịch quan trọng | Active-passive thường đơn giản hơn | Synchronous/asynchronous replication, fencing và recovery |
| Batch có thể chạy lại | Active-passive hoặc queue-based worker group | Idempotency, checkpoint và duplicate handling |

### Ví dụ phân loại

- API tra cứu catalog có thể phục vụ đọc từ nhiều vùng, trong khi cập nhật dữ liệu được điều phối về một writer.
- Dịch vụ thanh toán có thể ưu tiên single-writer database và hot standby để tránh xung đột giao dịch.
- Worker xử lý ảnh có thể chạy active-active trên nhiều node vì job nằm trong durable queue và được thiết kế idempotent.
- Hệ thống báo cáo nội bộ có thể dùng warm standby nếu downtime vài phút được chấp nhận.

Mỗi dịch vụ cần SLO và mục tiêu khôi phục riêng. Không áp một mẫu HA duy nhất cho mọi thành phần.

## 7. Thiết kế traffic routing và health check

### Global traffic manager

Traffic manager có thể là DNS-based routing, global load balancer, anycast hoặc dịch vụ điều phối traffic của nền tảng cloud.

Các chiến lược thường gặp:
- Active-active chia traffic theo tỷ trọng.
- Geo routing đưa người dùng tới vùng gần.
- Latency-based routing chọn endpoint có độ trễ phù hợp.
- Weighted routing cho phép canary hoặc điều chỉnh tải.
- Failover routing chuyển traffic khi endpoint không khỏe.
- Anycast đưa kết nối tới điểm gần trong mạng hỗ trợ.

### Health check cần phản ánh khả năng phục vụ

Một health check chỉ kiểm tra process còn sống có thể không phát hiện database hoặc dependency đã lỗi. Ngược lại, kiểm tra quá sâu trên mọi request có thể tạo tải lớn hoặc đánh dấu toàn bộ site unhealthy do một dependency chậm tạm thời.

Có thể tách:
- **Liveness:** process có còn hoạt động và cần restart không?
- **Readiness:** instance có thể nhận traffic mới không?
- **Dependency health:** database, queue hoặc service phụ thuộc có đáp ứng không?
- **Site health:** site có đủ năng lực và data state để tiếp tục phục vụ không?

Health check cần timeout, threshold, interval và hysteresis phù hợp. Tránh flapping khi trạng thái thay đổi liên tục quanh ngưỡng.

### DNS và thời gian chuyển traffic

DNS failover phụ thuộc TTL, cache resolver và client. TTL thấp không bảo đảm mọi client đổi endpoint ngay lập tức; một số resolver có thể cache lâu hơn hoặc ứng dụng giữ connection cũ.

Global load balancer có thể chuyển traffic nhanh hơn ở một số kiến trúc, nhưng vẫn cần xử lý connection đang mở, session, health detection và control plane availability.

### Connection draining

Khi rút một site hoặc instance khỏi traffic:
1. Ngừng nhận connection/request mới.
2. Cho request đang xử lý hoàn tất trong giới hạn.
3. Đóng hoặc chuyển connection dài hạn theo protocol.
4. Dừng worker hoặc consumer.
5. Chỉ terminate sau khi drain hoặc hết deadline.

WebSocket, gRPC stream và TCP connection dài có thể tồn tại lâu. Cần chính sách reconnect và retry phía client.

## 8. Trạng thái ứng dụng: session, cache, file và queue

Active-active hoặc active-passive chỉ hoạt động đúng nếu ứng dụng biết trạng thái nào nằm ở đâu.

### Stateless application

Ứng dụng stateless không phụ thuộc vào dữ liệu session chỉ tồn tại trong RAM của một instance. Session có thể được lưu ở shared store, token có chữ ký hoặc cơ chế khác để request tiếp theo có thể đến instance khác.

Stateless giúp scale và failover dễ hơn, nhưng shared session store vẫn là dependency cần HA.

### Cache

Cache cục bộ tại mỗi site có thể không đồng nhất. Khi traffic chuyển site, cache lạnh làm latency tăng và có thể tạo load spike lên database.

Cần xem:
- Cache có thể tái tạo từ source of truth không.
- Cache invalidation và TTL.
- Warm-up trước khi nhận traffic.
- Stampede protection.
- Giới hạn tải lên database khi cache miss tăng.

Không nhất thiết replicate toàn bộ cache nếu có thể tái tạo an toàn.

### File và object storage

File lưu trên local disk của một VM có thể không có ở site khác. Cần dùng shared file storage, object storage hoặc cơ chế replication/backup phù hợp.

Đối với object storage, kiểm tra versioning, replication lag, retention và quyền truy cập ở region dự phòng. Không giả định object đã replicate ngay khi upload nếu dịch vụ sử dụng replication bất đồng bộ.

### Queue và background jobs

Queue bền vững giúp worker ở nhiều site có thể lấy task. Tuy nhiên, cần kiểm soát:
- Consumer group và partition ownership.
- Visibility timeout hoặc acknowledgment.
- Redelivery khi worker chết.
- Duplicate delivery.
- Ordering requirement.
- Checkpoint và retry policy.

Thiết kế job idempotent để một task được giao lại không tạo tác động nghiệp vụ lặp.

## 9. Data replication và consistency

Data layer thường quyết định độ khó thực sự của active-active.

### Single-writer replication

Một database primary nhận ghi, replica nhận bản sao. Trong active-passive, replica có thể được promote khi primary lỗi. Trong kiến trúc app active-active, cả hai site có thể đọc từ replica hoặc route write về writer duy nhất.

Ưu điểm là tránh nhiều primary ghi đồng thời. Hạn chế là write routing và failover database cần hoạt động chính xác; replica có thể có replication lag nếu bất đồng bộ.

### Multi-primary replication

Nhiều site có thể nhận ghi. Điều này cần giải quyết trường hợp cùng một bản ghi bị sửa ở nhiều nơi hoặc network partition khiến các site không thể trao đổi.

Các cách xử lý có thể gồm:
- Phân vùng dữ liệu theo tenant, user hoặc vùng địa lý để mỗi key có writer rõ ràng.
- Conflict resolution theo rule nghiệp vụ.
- Version vector hoặc metadata versioning.
- Last-write-wins trong trường hợp dữ liệu phù hợp, hiểu rõ rủi ro.
- CRDT cho cấu trúc dữ liệu và phép toán có thể hợp nhất theo mô hình hỗ trợ.
- Giao dịch phân tán hoặc consensus khi yêu cầu consistency cao và chấp nhận chi phí/latency.

Last-write-wins không phù hợp cho mọi giao dịch. Nếu hai cập nhật tài chính cùng ghi một số dư, việc chọn timestamp mới hơn có thể làm mất một giao dịch hợp lệ. Quy tắc merge phải dựa trên semantics nghiệp vụ.

### Synchronous và asynchronous replication

| Thuộc tính | Synchronous | Asynchronous |
|---|---|---|
| Xác nhận ghi | Chờ điều kiện đồng bộ theo cơ chế triển khai | Primary có thể xác nhận trước khi replica nhận |
| RPO | Có thể gần 0 trong phạm vi được bảo đảm | Có thể mất phần dữ liệu chưa replicate |
| Latency | Tăng do chờ mạng/replica | Thường thấp hơn cho primary |
| Khả năng chịu partition | Có thể block hoặc từ chối ghi tùy consistency policy | Có thể tiếp tục ghi nhưng tăng nguy cơ divergence |
| Phù hợp | Giao dịch cần độ bền và consistency cao | Workload chấp nhận replication lag và RPO khác 0 |

Synchronous replication qua khoảng cách địa lý lớn có thể làm tăng latency đáng kể. Một số hệ thống dùng quorum hoặc synchronous trong cùng region và asynchronous tới region DR. Cần hiểu chính xác commit acknowledgment và durability guarantee.

### Replication lag

Theo dõi:
- Thời gian trễ giữa primary và replica.
- Số transaction/log chưa áp dụng.
- Vị trí log replication.
- Tốc độ phát sinh và áp dụng log.
- Trạng thái kết nối replication.
- Dung lượng hàng đợi replication.

Nếu failover khi replica chưa bắt kịp, RPO có thể vượt mục tiêu. Có thể chặn promotion hoặc yêu cầu xác nhận rủi ro nếu lag quá lớn.

## 10. Split-brain, quorum và fencing

**Split-brain** xảy ra khi hai node hoặc hai site cùng tin rằng mình là primary và cùng chấp nhận ghi. Điều này có thể tạo hai lịch sử dữ liệu khác nhau.

### Vì sao split-brain xảy ra?

- Network partition làm primary và standby mất liên lạc.
- Health check nhầm primary đã chết.
- Control plane hoặc failover controller không thống nhất trạng thái.
- Standby được promote nhưng primary cũ vẫn chạy.
- Operator thực hiện failover thủ công khi automation cũng đang chạy.

### Quorum

Một số hệ thống dùng quorum để yêu cầu đa số thành viên đồng ý trước khi thực hiện thay đổi trạng thái hoặc bầu leader. Với 3 voting members, quorum thường yêu cầu 2 thành viên.

Quorum giúp tránh hai phía của network partition cùng đạt đa số trong cùng cấu hình membership, nhưng cần triển khai đúng failure domain. Nếu tất cả voting member nằm trong một AZ, mất AZ đó có thể làm cluster mất quorum.

Witness có thể được đặt ở failure domain thứ ba để hỗ trợ quyết định, nhưng witness không thay thế dữ liệu và không tự cung cấp capacity phục vụ.

### Fencing

Fencing là cách ngăn node cũ tiếp tục ghi sau khi quyền primary đã chuyển sang node mới.

Các cơ chế có thể gồm:
- Tắt hoặc cô lập VM cũ qua control plane.
- Thu hồi quyền truy cập storage.
- Lease có epoch/generation tăng dần.
- Fencing token được storage hoặc database kiểm tra.
- STONITH trong một số cluster quản trị máy vật lý/VM.

Chỉ đổi DNS hoặc load balancer không đủ fencing database writer. Client cũ hoặc kết nối trực tiếp vẫn có thể ghi nếu primary cũ còn quyền.

### Failover an toàn

Một trình tự thường gặp:
1. Phát hiện primary không đáp ứng.
2. Xác minh quorum và trạng thái failure domain.
3. Fencing primary cũ hoặc chứng minh nó không thể ghi.
4. Xác định replica đủ điều kiện promotion.
5. Promote một writer mới.
6. Cập nhật service discovery/connection endpoint.
7. Mở traffic theo từng bước.
8. Kiểm tra consistency và giao dịch.
9. Giữ primary cũ ở trạng thái cách ly cho đến khi có kế hoạch resync.

Tự động failover cần được thiết kế với cùng sự cẩn trọng như data replication. Failover quá nhanh dựa trên health check yếu có thể gây split-brain.

## 11. HA theo AZ và multi-region

### Multi-AZ

Multi-AZ phân tán compute và dependency qua nhiều vùng sẵn sàng trong cùng region. Mục tiêu thường là chịu lỗi datacenter hoặc AZ.

Ưu điểm:
- Latency giữa các AZ thường thấp hơn liên vùng.
- Có thể dùng replication đồng bộ trong một số dịch vụ.
- Traffic nội vùng và control plane thường thuận tiện hơn.

Cần kiểm tra:
- VM/instance có được phân phối thực sự qua AZ không.
- Load balancer có gửi traffic tới AZ khỏe mạnh không.
- Database có replica ở AZ khác không.
- Storage có zone scope hay regional scope.
- Subnet, IP, quota và capacity ở từng AZ.

### Multi-region

Multi-region phân tán dịch vụ qua các region địa lý khác nhau, giúp giảm rủi ro sự cố diện rộng và phục vụ người dùng gần vùng của họ.

Đổi lại:
- Network latency cao hơn.
- Replication bất đồng bộ có thể tạo RPO lớn hơn.
- Data residency và compliance phức tạp hơn.
- DNS/global routing và failover cần được kiểm thử.
- Secret, certificate, key management và IAM cần sẵn sàng ở region dự phòng.
- Chi phí egress, replication và tài nguyên tăng.

### AZ failover không thay thế region DR

Một sự cố region có thể ảnh hưởng nhiều AZ cùng lúc. Nếu yêu cầu chịu được mất region, cần có thiết kế multi-region hoặc quy trình restore sang region khác. Multi-AZ thường giải quyết failure domain nhỏ hơn và không tự đảm bảo DR.

## 12. Capacity khi failover

Mô hình HA cần đủ capacity ở trạng thái lỗi, không chỉ trạng thái bình thường.

### Active-active

Nếu hai site mỗi nơi phục vụ 50% traffic, khi một site mất, site còn lại phải có khả năng nhận phần traffic chuyển sang. Nếu mỗi site chỉ được sizing vừa đủ cho 50%, failover sẽ gây overload.

Có thể chọn:
- Mỗi site đủ phục vụ 100% tải cần thiết.
- Mỗi site đủ phục vụ tải quan trọng/critical tier, còn chức năng phụ bị giảm.
- Có autoscaling nhanh cùng warm capacity.
- Có load shedding để ưu tiên request thiết yếu.

### Active-passive

Standby cần đủ capacity để tiếp nhận tải theo RTO. Nếu standby chỉ có 20% compute của primary, nó có thể không đạt throughput sau failover.

Có thể dùng warm standby với ít instance và scale nhanh, nhưng phải đo thời gian scale và giới hạn quota. Không giả định capacity sẽ luôn có sẵn đúng lúc region đang gặp sự cố.

### Capacity failover theo N-1

Nếu cần chịu lỗi một site trong số N site, tính capacity còn lại sau khi mất site lớn nhất. Ví dụ hai site có capacity bằng nhau và mỗi site phải chịu toàn bộ tải khi site kia lỗi, tổng capacity bình thường phải có đủ hai site, mỗi site đủ 100% tải mục tiêu. Nếu dùng ba site, có thể tính theo mức tải phân bố và failure scenario cụ thể.

Cần tính cả:
- CPU/RAM và instance quota.
- Database connection và query capacity.
- Storage IOPS/throughput.
- Network egress và NAT.
- Load balancer capacity.
- API rate limit và license.
- Cache warm-up và replication apply rate.

## 13. Bảo vệ dependency và loại bỏ single point of failure

HA của ứng dụng không có ý nghĩa nếu dependency chung vẫn là single point of failure.

Các thành phần cần rà soát:
- DNS và service discovery.
- Global/local load balancer.
- Database và connection proxy.
- Message broker.
- Cache/session store.
- Object/file storage.
- Secret manager và key service.
- Identity provider.
- NAT gateway, firewall và network route.
- CI/CD, image registry và bootstrap repository.
- Monitoring, alerting và control plane.

Không phải mọi dependency đều cần active-active. Có thể dùng managed multi-AZ service, replicated endpoint, backup/restore hoặc quy trình thủ công theo RTO. Quan trọng là dependency phải đáp ứng mục tiêu của service.

### Control plane và data plane

Control plane điều khiển cấu hình, provisioning và routing; data plane xử lý traffic thực tế. Một hệ thống có thể tiếp tục phục vụ traffic khi control plane tạm lỗi, nhưng không thể scale hoặc cập nhật route. Ngược lại, control plane khỏe không đảm bảo data plane hoạt động.

Thiết kế cần hiểu:
- Failover có phụ thuộc API control plane đang hoạt động không.
- Route đã được cấu hình trước hay cần tạo mới.
- Secret và image đã có ở standby chưa.
- DNS/global routing có dependency chung nào không.
- Có thể thực hiện thao tác phục hồi khi một dịch vụ quản lý bị gián đoạn không.

## 14. Session, giao dịch và tính idempotent khi failover

Khi traffic chuyển giữa site, request có thể được gửi lại do client timeout hoặc connection bị reset. Một giao dịch có thể đã commit ở primary nhưng response chưa đến client. Client retry có thể tạo giao dịch trùng nếu ứng dụng không hỗ trợ idempotency.

### Idempotency key

Với thao tác tạo đơn hàng, thanh toán hoặc ghi dữ liệu, client có thể gửi một idempotency key duy nhất. Server lưu kết quả xử lý theo key và trả lại kết quả cũ nếu request được gửi lại.

Cần lưu idempotency record trong data store có consistency phù hợp và giữ đủ lâu cho retry window. Nếu mỗi site lưu idempotency key cục bộ mà không replicate, active-active có thể xử lý trùng khi request retry tới site khác.

### Exactly-once là mục tiêu khó

Queue và distributed system thường cung cấp at-least-once hoặc at-most-once semantics tùy cấu hình. Exactly-once ở cấp nghiệp vụ thường cần idempotency, transaction boundary và deduplication. Không nên tuyên bố hệ thống xử lý exactly-once chỉ vì broker có tính năng tương ứng.

### Session và long-lived connection

Session trong memory của một instance có thể mất khi failover. Hãy dùng shared session store, token stateless hoặc cơ chế phục hồi session.

WebSocket, gRPC stream và TCP connection dài thường bị reset khi site hoặc route thay đổi. Client cần reconnect có backoff và tránh tạo connection storm.

## 15. Failback: quay về site chính

Failover là chuyển dịch vụ sang site dự phòng. Failback là đưa dịch vụ trở lại site hoặc topology ban đầu sau khi sự cố được xử lý.

Failback không nên chỉ là đổi route về primary cũ. Trong thời gian secondary phục vụ, dữ liệu đã thay đổi. Primary cũ có thể đã stale và không được phép trở lại làm writer ngay.

### Quy trình failback an toàn

1. Xác định nguyên nhân sự cố ở primary đã được xử lý.
2. Giữ primary cũ ở trạng thái không nhận ghi.
3. Đồng bộ dữ liệu từ site đang active về primary cũ.
4. Kiểm tra replication lag và consistency.
5. Xác minh capacity, version và cấu hình.
6. Thực hiện chuyển writer theo quy trình có fencing.
7. Chuyển traffic dần hoặc theo kế hoạch.
8. Theo dõi error, latency, replication và giao dịch.
9. Giữ khả năng quay lại site hiện tại nếu phát sinh lỗi.
10. Kết thúc failback sau khi xác nhận dữ liệu và SLO ổn định.

Với active-active, failback có thể là khôi phục một site và đưa nó trở lại tỷ trọng traffic ban đầu. Cần warm cache, kiểm tra replication và tăng traffic dần.

## 16. Backup, HA và disaster recovery không thay thế nhau

- **HA:** duy trì dịch vụ khi thành phần hoặc failure domain gặp lỗi.
- **DR:** khôi phục dịch vụ sau sự cố lớn như mất region hoặc hỏng diện rộng.
- **Backup:** bản sao dữ liệu có thể dùng để phục hồi trạng thái trước đó.

Replication có thể sao chép cả dữ liệu bị xóa nhầm, mã hóa bởi ransomware hoặc lỗi logic. Backup độc lập, immutable hoặc có retention phù hợp giúp khôi phục về thời điểm trước sự cố.

Một kiến trúc tốt thường kết hợp:
- Multi-AZ HA cho lỗi hạ tầng thường gặp.
- Multi-region DR cho sự cố region nếu yêu cầu.
- Backup và restore test cho lỗi dữ liệu hoặc thao tác.
- Runbook và diễn tập để chứng minh RTO/RPO.

## 17. Ví dụ: chọn mô hình cho hai dịch vụ

### Dịch vụ catalog đọc nhiều

Yêu cầu:
- Người dùng ở nhiều khu vực.
- Đọc catalog chiếm phần lớn traffic.
- Cập nhật dữ liệu ít hơn và có thể điều phối.
- Chấp nhận replication lag nhỏ cho một số bản cập nhật không quan trọng.

Thiết kế có thể chọn:
- Ứng dụng active-active ở nhiều region.
- Traffic manager phân phối theo latency và health.
- Read replica hoặc data copy ở từng region.
- Write route về writer chính hoặc phân vùng theo tenant.
- Cache có TTL và invalidation.
- Failover khi một region lỗi.

Rủi ro cần kiểm tra là dữ liệu đọc stale, cache cold và write routing khi region primary lỗi.

### Dịch vụ giao dịch thanh toán

Yêu cầu:
- Mỗi giao dịch cần một kết quả nhất quán.
- Không chấp nhận ghi trùng.
- RPO rất thấp.
- Audit và đối soát là bắt buộc.

Thiết kế có thể chọn:
- Application tier active-active hoặc multi-AZ.
- Database single-writer với synchronous HA trong region nếu dịch vụ hỗ trợ.
- Standby region được replicate và có quy trình promote rõ ràng.
- Fencing trước khi promote writer mới.
- Idempotency key cho mọi thao tác thanh toán.
- Outbox/event pattern để phát sự kiện sau commit.
- DR test và đối soát sau failover.

Mô hình này có thể đơn giản hóa data consistency hơn multi-primary, nhưng cần đo latency và thời gian failover của database.

## 18. Kiểm thử HA và fault tolerance

Không thể xác nhận HA chỉ bằng cách nhìn trạng thái hai site đang xanh. Cần tạo lỗi có kiểm soát và đo kết quả.

### Các tình huống cần thử

- Một VM hoặc pod bị terminate.
- Một AZ mất kết nối.
- Load balancer không truy cập được backend.
- Database primary bị dừng.
- Replication lag tăng hoặc replication link bị ngắt.
- Network partition giữa primary và standby.
- DNS hoặc service discovery lỗi.
- Secret manager hoặc key service không truy cập được.
- Một site bị quá tải khi nhận toàn bộ traffic.
- Client retry và reconnect đồng loạt.
- Rollout ứng dụng trong khi một site đang degraded.
- Failback sau khi primary phục hồi.

### Đo kết quả

Mỗi lần diễn tập nên ghi:
- Thời điểm bắt đầu fault.
- Thời điểm phát hiện.
- Thời điểm bắt đầu failover.
- Thời điểm traffic chuyển.
- Thời điểm request thành công trở lại.
- RTO thực tế.
- Replication lag và RPO thực tế.
- Số request lỗi, timeout hoặc duplicate.
- Capacity và latency sau failover.
- Thao tác thủ công cần thiết.
- Những bước runbook chưa rõ.

### Game day và chaos testing

Game day là buổi diễn tập có kế hoạch để kiểm tra quy trình và phối hợp. Chaos testing có thể tự động tạo lỗi có kiểm soát trên một phạm vi nhỏ.

Bắt đầu ở staging hoặc một phần traffic, có rollback và điều kiện dừng rõ ràng. Không tạo lỗi diện rộng trên production nếu chưa có guardrail và phê duyệt vận hành phù hợp.

## 19. Bảo mật và vận hành trong mô hình nhiều site

Mỗi site phải có cấu hình bảo mật tương đương với phạm vi phục vụ của nó.

Kiểm tra:
- IAM role/service account và quyền tối thiểu.
- Secret, certificate và encryption key có sẵn ở site dự phòng.
- Key policy và quyền decrypt.
- Network segmentation và firewall rule.
- TLS giữa client, load balancer, app và database.
- Audit log tập trung và đồng bộ thời gian.
- Image và configuration version nhất quán.
- Patch level và security baseline của standby.
- Backup, snapshot và quyền truy cập restore.

Không để standby lâu ngày không cập nhật. Một site dự phòng có image hoặc certificate hết hạn có thể thất bại đúng lúc cần failover.

## 20. Ma trận quyết định active-active hay active-passive

Dùng các câu hỏi sau để chọn mô hình:

| Câu hỏi | Nếu câu trả lời là “có” | Hướng cân nhắc |
|---|---|---|
| Dịch vụ cần phục vụ đồng thời người dùng ở nhiều vùng? | Traffic có lợi khi xử lý gần người dùng | Active-active ở application tier |
| Dữ liệu có thể phân vùng theo tenant/region? | Có thể xác định writer cho từng phần dữ liệu | Active-active có partitioning |
| Nhiều site phải ghi cùng dữ liệu? | Cần conflict resolution và consistency rõ | Multi-primary chỉ khi có mô hình dữ liệu phù hợp |
| Workload cần single-writer và giao dịch nhất quán? | Tránh nhiều primary ghi đồng thời | Active-passive ở data tier |
| RTO vài phút có chấp nhận được? | Có thể scale/promote khi sự cố | Warm standby |
| RTO rất thấp và standby phải sẵn sàng ngay? | Cần capacity và data sẵn sàng | Hot standby hoặc active-active |
| Ngân sách hạn chế? | Có thể chấp nhận standby ít tài nguyên | Cold/warm standby, nhưng phải đo RTO |
| Đội ngũ có thể vận hành multi-region data? | Có thể xử lý replication, partition và conflict | Cân nhắc active-active |
| Dependency chưa có HA? | App HA không đủ để bảo vệ dịch vụ | Thiết kế lại dependency trước |

### Nguyên tắc chọn

- Chọn active-active khi lợi ích phục vụ đồng thời ở nhiều site đáng với độ phức tạp về data, routing và consistency.
- Chọn active-passive khi một writer chính giúp giảm rủi ro và mục tiêu RTO/RPO có thể đạt bằng standby cùng replication.
- Có thể kết hợp: active-active cho frontend/app, active-passive cho database; multi-AZ active-active trong region và warm standby ở region DR.
- Chọn mô hình nhỏ nhất có thể đáp ứng SLO, RTO và RPO đã được kiểm chứng.

## 21. Checklist trước khi đưa kiến trúc HA vào production

- [ ] Đã xác định failure domain cần chịu đựng: instance, AZ hay region.
- [ ] Đã xác định SLO, RTO và RPO theo từng dịch vụ.
- [ ] Đã xác định active-active hay active-passive ở từng tầng.
- [ ] Đã kiểm tra capacity khi mất một site hoặc một AZ.
- [ ] Đã xác định trạng thái standby: cold, warm hay hot.
- [ ] Đã thiết kế traffic routing, health check và connection draining.
- [ ] Đã xác định nguồn ghi chính và consistency model.
- [ ] Đã đo replication lag và quy tắc promotion.
- [ ] Có quorum/fencing phù hợp để ngăn split-brain.
- [ ] Session, cache, file và queue có chiến lược phục hồi.
- [ ] Request retry có idempotency hoặc deduplication.
- [ ] Dependency quan trọng có HA hoặc quy trình phục hồi.
- [ ] Secret, key, certificate và IAM sẵn sàng ở site dự phòng.
- [ ] Có backup độc lập và đã thử restore.
- [ ] Có runbook failover và failback.
- [ ] Đã diễn tập mất instance, AZ, region và network partition.
- [ ] Đã đo RTO/RPO thực tế và ghi nhận sai lệch.
- [ ] Có dashboard, alert và audit cho replication, health và traffic.
- [ ] Đã xác định điều kiện dừng và rollback trong game day.
- [ ] Có người chịu trách nhiệm và lịch diễn tập định kỳ.

## Kết luận

Active-active cho phép nhiều site cùng phục vụ traffic và có thể rút ngắn thời gian chuyển tải, nhưng yêu cầu thiết kế data consistency, replication, routing và split-brain control cẩn thận. Active-passive giữ một site chính và một site standby, thường phù hợp với workload single-writer hoặc yêu cầu giảm độ phức tạp dữ liệu, đổi lại cần bảo đảm standby đủ capacity và failover/failback được kiểm thử. Quyết định nên dựa trên RTO, RPO, failure domain, khả năng phục hồi dữ liệu, giới hạn dependency, ngân sách và năng lực vận hành. Một kiến trúc chỉ được xem là đáp ứng HA khi quá trình failover thực tế đã được diễn tập, đo lường và chứng minh bằng kết quả dịch vụ cùng dữ liệu.
