# Đánh đổi giữa độ trễ, độ bền, chi phí và độ phức tạp

Một kiến trúc AWS tốt không phải kiến trúc nhanh nhất, có nhiều bản sao nhất hay dùng ít dịch vụ nhất. Kiến trúc cần đáp ứng đúng mục tiêu kinh doanh với mức rủi ro, chi phí và công sức vận hành mà tổ chức chấp nhận được. Khi giảm độ trễ, nhóm có thể phải dùng cache, replica hoặc triển khai gần người dùng hơn. Những lựa chọn đó có thể tăng chi phí, tạo dữ liệu cũ trong một khoảng thời gian hoặc làm quy trình vận hành phức tạp hơn.

Bốn chiều cần cân nhắc trong bài học là:

- **Độ trễ (latency):** thời gian một request hoặc một công việc cần để hoàn tất.
- **Độ bền dữ liệu (durability):** khả năng giữ dữ liệu tồn tại và có thể khôi phục sau lỗi hoặc sự cố.
- **Chi phí (cost):** tổng chi phí để cung cấp, bảo vệ, vận hành và thay đổi workload.
- **Độ phức tạp (complexity):** số thành phần, trạng thái, dependency, quy trình và kiến thức cần thiết để phát triển, vận hành và xử lý lỗi.

Các chiều này tương tác với nhau. Replication đồng bộ có thể bảo vệ dữ liệu tốt hơn nhưng thêm thời gian chờ mạng. Cache giảm thời gian đọc nhưng cần chính sách freshness và invalidation. Multi-Region có thể tăng khả năng phục hồi địa lý nhưng đòi hỏi giải quyết replication, conflict, identity, routing và vận hành ở nhiều nơi. Một quyết định đúng phải dựa trên yêu cầu đo được, thử nghiệm và bằng chứng từ workload.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt latency, durability, availability, consistency, RPO và RTO.
- Xác định thành phần tạo ra latency trên critical path.
- Giải thích ảnh hưởng của cache, replication, read replica, partitioning, compression và buffering.
- So sánh ghi đồng bộ với xử lý bất đồng bộ và nhận diện rủi ro mất dữ liệu.
- Chọn chiến lược backup, versioning, replication và storage class theo giá trị dữ liệu.
- Phân tích chi phí hạ tầng, truyền dữ liệu, lưu trữ, vận hành và phục hồi.
- Nhận diện complexity do distributed systems, multi-Region, event-driven processing và cache invalidation.
- Dùng decision matrix, load test, failure test và ADR để ghi lại quyết định kiến trúc.
- Thiết kế phương án phù hợp cho các luồng dữ liệu khác nhau trong cùng một ứng dụng AWS.

## 1. Bốn chiều của một quyết định kiến trúc

### 1.1. Độ trễ – latency

Latency là thời gian từ khi một hoạt động bắt đầu đến khi có kết quả mà bên gọi có thể sử dụng. Trong ứng dụng web, người dùng thường cảm nhận thời gian phản hồi từ lúc gửi request đến lúc nhận response. Với hệ thống xử lý nền, latency có thể là thời gian từ lúc event được tạo đến khi công việc hoàn tất.

Không nên chỉ nhìn vào giá trị trung bình. Một số request chậm có thể ảnh hưởng lớn đến trải nghiệm, đặc biệt khi một request gọi nhiều service nối tiếp.

Các chỉ số thường dùng:

| Chỉ số | Ý nghĩa |
|---|---|
| p50 | 50% request hoàn tất trong khoảng thời gian này hoặc nhanh hơn. |
| p95 | 95% request hoàn tất trong khoảng thời gian này hoặc nhanh hơn. |
| p99 | 99% request hoàn tất trong khoảng thời gian này hoặc nhanh hơn; giúp thấy tail latency. |
| Throughput | Số request, transaction hoặc công việc xử lý trong một đơn vị thời gian. |
| Queue age | Tuổi của message/công việc lâu nhất còn chờ xử lý. |
| Time to complete | Tổng thời gian từ lúc bắt đầu đến khi công việc nền hoàn tất. |

Ví dụ: API có p50 là 80 ms nhưng p99 là 2 giây. Người dùng có thể gặp trải nghiệm không ổn định dù giá trị trung bình trông tốt. Cần phân tích request chậm, dependency, retry, connection pool và tải đồng thời.

### 1.2. Độ bền dữ liệu – durability

Durability là khả năng dữ liệu đã được xác nhận ghi thành công vẫn tồn tại khi thiết bị, host, rack, Availability Zone hoặc một thành phần hạ tầng gặp lỗi theo mô hình bảo vệ của dịch vụ.

Durability không đồng nghĩa với availability:

- **Durability:** dữ liệu có còn tồn tại sau lỗi hay không?
- **Availability:** dữ liệu/dịch vụ có thể truy cập được khi người dùng cần hay không?

Một bản sao lưu có thể rất bền nhưng cần thời gian restore nên không giúp ứng dụng hoạt động ngay. Ngược lại, một dịch vụ có thể đang sẵn sàng phục vụ nhưng dữ liệu mới nhất chưa được nhân bản tới nơi dự phòng.

Durability cũng không tự bảo vệ khỏi mọi nguyên nhân mất dữ liệu. Nếu người dùng hoặc ứng dụng được cấp quyền xóa dữ liệu, thao tác xóa hợp lệ có thể được áp dụng trên các bản sao. Malware, lỗi logic hoặc một deployment sai có thể ghi đè dữ liệu đúng bằng dữ liệu sai. Vì vậy, dữ liệu quan trọng cần thêm versioning, backup, retention, immutable copy và kiểm thử restore.

### 1.3. Chi phí – cost

Chi phí workload không chỉ là giá giờ chạy của EC2 hoặc số GB lưu trữ. Tổng chi phí có thể gồm:

- Compute, database, cache, queue và load balancer.
- Storage capacity, IOPS, request, retrieval và lifecycle transition.
- Data transfer giữa AZ, Region, Internet, edge và on-premises.
- Replication, backup, snapshot và bản sao lưu cross-account/cross-Region.
- Logging, metrics, traces, security scanning và data ingestion.
- License, support plan và dịch vụ bên thứ ba.
- Nhân lực phát triển, vận hành, xử lý incident và duy trì automation.
- Chi phí downtime, dữ liệu mất, giao dịch lỗi và cơ hội kinh doanh bị ảnh hưởng.

Một lựa chọn có giá đơn vị cao hơn vẫn có thể giảm tổng chi phí nếu xử lý công việc nhanh hơn, cần ít instance-hours hơn hoặc giảm incident. Nên so sánh cost per request, cost per transaction, cost per GB được xử lý hoặc cost per business outcome.

### 1.4. Độ phức tạp – complexity

Complexity là lượng kiến thức và công việc cần để hiểu, thay đổi, quan sát, triển khai và phục hồi hệ thống. Nó đến từ:

- Số thành phần và số dependency.
- Số Region, account, AZ và network boundary.
- Số kiểu dữ liệu, schema, protocol và consistency model.
- Cache, replica, queue, retry, DLQ và state machine.
- Nhiều pipeline, deployment order và quy trình migration.
- Cơ chế failover, reconciliation, backup và restore.
- Nhiều team hoặc nhà cung cấp cùng sở hữu một luồng xử lý.

Complexity có chi phí trực tiếp: cần thêm dashboard, runbook, test, quyền IAM, trực vận hành và kỹ năng chuyên môn. Nó cũng làm tăng xác suất cấu hình sai và kéo dài thời gian điều tra khi có sự cố.

Một managed service có thể giảm complexity vận hành vì AWS quản lý phần hạ tầng, nhưng vẫn có service limits, IAM, quota, network dependency và cách tích hợp cần hiểu. Không nên đánh giá độ phức tạp chỉ bằng số dịch vụ trong sơ đồ.

## 2. Xác định điều gì là bắt buộc và điều gì có thể đánh đổi

Trước khi chọn giải pháp, phân loại yêu cầu thành ba nhóm:

1. **Ràng buộc bắt buộc:** yêu cầu compliance, data residency, giới hạn mất dữ liệu, security boundary, hợp đồng hoặc SLA.
2. **Mục tiêu cần tối ưu:** p95 latency, throughput, cost per transaction, thời gian phục hồi hoặc mức sử dụng tài nguyên.
3. **Điều có thể chấp nhận:** dữ liệu cũ tối đa bao lâu, công việc nền được trễ bao lâu, mức redundancy nào phù hợp, số bước vận hành nhóm có thể quản lý.

Ví dụ:

| Loại dữ liệu/luồng | Yêu cầu thường gặp | Đánh đổi có thể chấp nhận |
|---|---|---|
| Số dư tài khoản và trạng thái thanh toán | Không được xác nhận giao dịch nếu dữ liệu quan trọng chưa được ghi bền vững; kiểm soát consistency chặt. | Chấp nhận thêm latency trên đường ghi quan trọng. |
| Catalog và nội dung sản phẩm | Đọc nhanh, chịu tải lớn, dữ liệu có thể cập nhật theo đợt. | Chấp nhận cache cũ trong một TTL ngắn đã xác định. |
| Telemetry và clickstream | Throughput cao, có thể xử lý theo batch hoặc stream. | Chấp nhận xử lý trễ và một mức eventual consistency. |
| Log phục vụ audit | Cần retention, quyền truy cập và bảo vệ khỏi sửa/xóa trái phép. | Có thể lưu trên tầng truy xuất chậm hơn nếu quy trình điều tra chấp nhận thời gian lấy lại. |
| Báo cáo phân tích | Có thể cập nhật định kỳ, ưu tiên chi phí xử lý hợp lý. | Chấp nhận dữ liệu trễ vài phút hoặc vài giờ tùy nghiệp vụ. |

Không áp dụng một consistency model hoặc một SLA cho toàn bộ ứng dụng. Một workload có thể cần ghi đồng bộ cho thanh toán, cache cho catalog và xử lý bất đồng bộ cho email hoặc báo cáo.

## 3. Latency đến từ đâu?

Một request thường đi qua nhiều thành phần. Latency tổng có thể gồm:

- DNS resolution và kết nối TLS.
- Network round-trip giữa client, edge, load balancer và backend.
- Queueing time khi thành phần phía sau quá tải.
- Thời gian CPU, serialization, compression và xử lý ứng dụng.
- Database query, lock, commit, replication và connection pool.
- Gọi service bên ngoài hoặc chờ message.
- Retry, timeout và backoff.

Nếu các bước chạy nối tiếp, latency thường gần bằng tổng thời gian từng bước. Nếu một số bước chạy song song, thời gian phụ thuộc nhánh chậm nhất cùng chi phí điều phối.

~~~mermaid
flowchart LR
    C["Client"] --> E["CloudFront / DNS / TLS"]
    E --> L["ALB / API Gateway"]
    L --> A["Application"]
    A --> D["Database"]
    A --> Q["Queue / Event"]
    Q --> W["Background worker"]
    D --> A
    A --> L
    L --> E
    E --> C
~~~

Để giảm latency, trước hết xác định bước nào nằm trên critical path và đo thời gian từng dependency. Tăng CPU hoặc thêm cache không giải quyết được latency do DNS, network, lock contention hoặc service bên ngoài.

### 3.1. Tail latency và fan-out

Nếu một request gọi nhiều service song song, người dùng thường phải đợi nhánh chậm nhất. Khi một trang cần 20 dependency, xác suất có ít nhất một dependency chậm tăng lên. Nếu gọi tuần tự, tổng thời gian còn cộng dồn.

Cách giảm:

- Giảm số dependency trên critical path.
- Gộp request hoặc tạo read model phù hợp.
- Đặt timeout theo ngân sách latency.
- Dùng retry có giới hạn, exponential backoff và jitter.
- Tránh retry đồng loạt gây retry storm.
- Tách công việc không cần phản hồi tức thì sang queue.
- Theo dõi p95/p99 của từng dependency thay vì chỉ xem latency API tổng.

### 3.2. Đưa dữ liệu gần người dùng

Amazon CloudFront có thể cache nội dung ở edge để giảm round-trip tới origin. Với nội dung tĩnh hoặc dữ liệu ít thay đổi, TTL dài thường tăng cache hit và giảm tải origin. TTL ngắn hoặc invalidation giúp nội dung mới xuất hiện sớm hơn nhưng tăng số lần gọi origin và có thể phát sinh chi phí.

Với API cá nhân hóa, cần thiết kế cache key cẩn thận. Nếu bỏ sót header, cookie hoặc query parameter xác định người dùng, cache có thể trả nội dung sai người hoặc làm lộ dữ liệu. Không cache response nhạy cảm chỉ vì nó giúp giảm latency.

Các hướng triển khai:

- CloudFront cho static assets và response có thể cache.
- ElastiCache cho dữ liệu đọc nhiều và có thể chấp nhận freshness window.
- Browser cache cho nội dung công khai.
- API response caching khi cache key và quyền truy cập được xác định chính xác.

## 4. Đánh đổi giữa latency và durability

Một trong những quyết định quan trọng là thời điểm hệ thống xác nhận một thao tác ghi thành công.

### 4.1. Ghi đồng bộ – synchronous write

Trong ghi đồng bộ, caller chờ dịch vụ lưu trữ xác nhận thao tác trước khi trả kết quả thành công. Tùy dịch vụ, xác nhận có thể bao gồm ghi vào storage bền vững hoặc replication theo cơ chế của dịch vụ.

Ưu điểm:

- Caller biết thao tác đã đạt điều kiện commit được thiết kế.
- Phù hợp với giao dịch mà không thể báo thành công khi dữ liệu chưa được lưu.
- Dễ giữ invariant nghiệp vụ khi một bước ghi là điều kiện của bước tiếp theo.

Đánh đổi:

- Có thể thêm network round-trip hoặc thời gian chờ replication.
- Latency có thể tăng khi dependency xa hoặc có sự cố.
- Khi thành phần ghi không sẵn sàng, caller có thể phải chờ hoặc nhận lỗi.
- Cần thiết kế timeout và retry an toàn.

Ví dụ: dịch vụ thanh toán cần ghi trạng thái order và payment reference vào database trước khi xác nhận đơn hàng đã được tiếp nhận. Nhóm có thể chấp nhận thêm latency trên đường ghi để giữ tính nhất quán nghiệp vụ.

### 4.2. Ghi bất đồng bộ – asynchronous write

Trong xử lý bất đồng bộ, request ghi vào một buffer hoặc queue bền vững rồi trả lời caller trước khi tất cả công việc phía sau hoàn tất.

Ưu điểm:

- Caller không phải chờ xử lý dài.
- Có thể hấp thụ burst traffic và điều chỉnh tốc độ consumer.
- Dễ scale worker độc lập.
- Tách producer khỏi consumer và giảm coupling thời gian chạy.

Đánh đổi:

- Kết quả nghiệp vụ chưa hoàn tất tại thời điểm caller nhận phản hồi.
- Dữ liệu có thể chưa xuất hiện ở read model hoặc hệ thống phụ.
- Cần retry, DLQ, idempotency, ordering và reconciliation.
- Queue hoặc event pipeline trở thành thành phần cần theo dõi.

Chỉ trả thành công sau khi thông điệp đã được chấp nhận bởi một cơ chế lưu trữ bền vững đáp ứng yêu cầu. Nếu chỉ giữ event trong memory rồi trả HTTP 200, process crash có thể làm mất event.

### 4.3. So sánh hai mô hình

| Tiêu chí | Ghi đồng bộ | Ghi bất đồng bộ |
|---|---|---|
| Phản hồi caller | Chờ commit hoặc điều kiện ghi hoàn tất. | Có thể phản hồi sau khi queue/buffer nhận dữ liệu. |
| Latency phía người dùng | Thường cao hơn trên đường ghi. | Thường thấp hơn nếu chấp nhận công việc hoàn tất sau. |
| Durability | Phụ thuộc xác nhận ghi của datastore và cấu hình replication. | Phụ thuộc durability của queue/buffer và quy trình consumer. |
| Consistency | Dễ trả kết quả sau khi transaction commit. | Thường cần eventual consistency giữa các thành phần. |
| Failure handling | Caller xử lý timeout, rollback hoặc retry. | Consumer retry, DLQ, replay và idempotency. |
| Complexity | Có thể đơn giản hơn cho một transaction nhỏ; coupling tăng khi gọi nhiều dịch vụ đồng bộ. | Thêm queue, consumer, trạng thái pending và reconciliation. |
| Phù hợp | Thanh toán, cập nhật số dư, quyền truy cập, giao dịch quan trọng. | Email, notification, analytics, thumbnail, export và tác vụ nền. |

Không phải mọi thao tác bất đồng bộ đều kém bền. Amazon SQS lưu message theo thiết kế của dịch vụ; nhưng ứng dụng phải xử lý delivery semantics và xóa message đúng thời điểm. Với SQS Standard, message có thể được gửi nhiều lần; consumer nên idempotent. SQS FIFO hỗ trợ deduplication trong cửa sổ 5 phút cho producer retry, nhưng không loại bỏ mọi khả năng duplicate ở toàn bộ business workflow.

### 4.4. Transactional outbox

Một lỗi phổ biến xảy ra khi ứng dụng ghi database thành công nhưng gửi event thất bại, hoặc gửi event thành công rồi transaction database rollback. Hai thao tác độc lập không tự tạo thành một transaction phân tán.

Transactional outbox giảm khoảng trống này:

1. Trong cùng một database transaction, ghi dữ liệu nghiệp vụ và một bản ghi outbox.
2. Một publisher đọc outbox và gửi event tới SQS/EventBridge.
3. Publisher đánh dấu event đã publish sau khi nhận acknowledgement.
4. Consumer xử lý event idempotently và ghi nhận kết quả.
5. Job reconciliation tìm event bị kẹt hoặc lỗi lặp lại.

~~~mermaid
flowchart TD
    R["API request"] --> T["Database transaction"]
    T --> O["Order row + Outbox row"]
    O --> P["Outbox publisher"]
    P --> Q["SQS / EventBridge"]
    Q --> C["Idempotent consumer"]
    C --> D["Update downstream state"]
~~~

Outbox tăng thêm bảng, publisher và cơ chế dọn dẹp, nhưng giúp tránh mất event giữa commit database và publish. Với nghiệp vụ quan trọng, đây thường là trade-off tốt hơn việc gọi nhiều service đồng bộ trong request.

## 5. Consistency, replication và read latency

Consistency mô tả mức độ mà các lần đọc nhìn thấy các cập nhật đã ghi. Strong consistency và eventual consistency là hai mô hình thường gặp.

- **Strongly consistent read:** đọc phản ánh các cập nhật đã hoàn tất trước đó theo guarantee của dịch vụ và phạm vi hỗ trợ.
- **Eventually consistent read:** sau một cập nhật, một số lần đọc có thể tạm thời trả dữ liệu cũ; các replica sẽ hội tụ sau đó.

Eventual consistency không có nghĩa dữ liệu mất hoặc ngẫu nhiên. Nó có nghĩa ứng dụng phải chấp nhận một khoảng trễ hội tụ và thiết kế UX/logic phù hợp.

### 5.1. DynamoDB

Amazon DynamoDB hỗ trợ strongly consistent reads trên table và local secondary index (LSI). Global secondary index (GSI) và DynamoDB Streams chỉ hỗ trợ eventual consistency. Eventually consistent reads là mặc định và có chi phí đọc thấp hơn strong reads theo pricing model của DynamoDB.

Global tables có các consistency mode. Multi-Region eventual consistency (MREC) nhân bản thay đổi bất đồng bộ giữa Regions; Multi-Region strong consistency (MRSC) đồng bộ thay đổi giữa các Regions được hỗ trợ trước khi write trả về. Strong consistency đa Region có yêu cầu triển khai và giới hạn riêng, vì vậy cần xác minh Region/feature support trước khi chọn.

Lựa chọn:

| Use case | Hướng đọc | Lý do |
|---|---|---|
| Trang catalog | Eventual consistency thường đủ. | Một cập nhật chậm vài giây thường ít ảnh hưởng hơn chi phí/độ trễ của strong read. |
| Số dư và trạng thái giao dịch | Chọn consistency theo invariant nghiệp vụ; strong read khi cần xác nhận trạng thái mới nhất trong phạm vi được hỗ trợ. | Tránh quyết định dựa trên dữ liệu cũ. |
| Dashboard analytics | Eventual hoặc read model cập nhật theo batch. | Tối ưu throughput và cost khi không cần đọc tức thời. |
| GSI lookup | Phải chấp nhận eventual consistency của GSI. | GSI không hỗ trợ strongly consistent read. |

Không chuyển mọi read sang strong consistency. Hãy xác định chỗ nào stale data có thể gây sai nghiệp vụ và chỗ nào có thể chấp nhận.

### 5.2. Read replica

Read replica giúp phân tán truy vấn đọc khỏi writer. Nó có thể tăng read throughput và giảm tải primary database. Đổi lại:

- Có thêm chi phí compute và storage.
- Replica có thể có replication lag.
- Ứng dụng phải định tuyến read/write hợp lý.
- Read-after-write có thể trả dữ liệu cũ nếu request đọc sang replica chưa bắt kịp.
- Failover và endpoint management cần được kiểm thử.

Với RDS/Aurora, phân biệt Multi-AZ deployment phục vụ availability/failover với read replica/reader endpoint phục vụ read scaling. Các loại deployment cụ thể có hành vi khác nhau; không mặc định mọi standby đều có thể nhận truy vấn đọc.

### 5.3. Partitioning và sharding

Partitioning chia dữ liệu thành phần nhỏ hơn theo key hoặc phạm vi. Sharding phân tán partition trên nhiều node hoặc datastore.

Lợi ích:

- Giảm lượng dữ liệu một node phải xử lý.
- Tăng khả năng scale ngang.
- Hạn chế hotspot nếu key được phân phối tốt.

Chi phí:

- Cần chọn partition key.
- Query cross-partition phức tạp hơn.
- Giao dịch nhiều shard có thể khó hơn.
- Rebalancing và migration cần công cụ/quy trình.
- Một partition key nóng có thể tạo bottleneck.
- Monitoring và troubleshooting cần biết dữ liệu nằm ở đâu.

Không shard chỉ vì database đang lớn. Trước tiên đo query plan, index, connection pool, storage, IOPS, cache hit ratio và khả năng scale của dịch vụ managed hiện tại.

## 6. Cache: đổi memory và freshness lấy tốc độ

Cache lưu bản sao dữ liệu gần thành phần đọc để giảm thời gian truy xuất nguồn chính. Cache có thể nằm ở browser, CloudFront, API layer hoặc ElastiCache.

### 6.1. Lợi ích và chi phí

Lợi ích:

- Giảm latency đọc.
- Giảm tải database/origin.
- Hấp thụ burst traffic.
- Có thể tiếp tục phục vụ một số dữ liệu stale khi origin tạm thời lỗi, nếu chính sách cho phép.

Chi phí:

- Thêm memory/storage và request cost.
- Cần thiết kế TTL, invalidation và cache key.
- Cache miss hoặc cache stampede có thể gây tải đột biến.
- Dữ liệu stale có thể làm sai quyết định nghiệp vụ.
- Cache trở thành dependency cần monitor và capacity planning.

### 6.2. Cache-aside

Một mô hình phổ biến:

1. Ứng dụng đọc cache.
2. Nếu hit, trả dữ liệu.
3. Nếu miss, đọc datastore.
4. Ghi kết quả vào cache với TTL.
5. Khi dữ liệu thay đổi, invalidation hoặc cập nhật cache theo chính sách.

~~~text
read(key):
  value = cache.get(key)
  if value exists:
      return value

  value = database.get(key)
  cache.set(key, value, ttl)
  return value
~~~

Ví dụ: catalog sản phẩm có thể chấp nhận dữ liệu cũ trong 30 giây. Cache giảm tải database khi một sản phẩm được xem nhiều lần. Số dư tài khoản hoặc trạng thái thanh toán không nên dùng cùng chính sách cache nếu dữ liệu cũ có thể gây sai quyết định.

### 6.3. TTL, invalidation và cache stampede

TTL dài giúp tăng cache hit nhưng tăng thời gian dữ liệu có thể cũ. TTL ngắn giúp dữ liệu mới xuất hiện nhanh hơn nhưng tăng origin request. Invalidation chủ động cập nhật nhanh hơn nhưng cần quản lý dependency giữa dữ liệu và cache key.

Cache stampede xảy ra khi nhiều request cùng gặp cache miss hoặc cache entry hết hạn và cùng gọi origin. Biện pháp:

- Request coalescing hoặc single-flight.
- Jitter TTL để tránh nhiều key hết hạn cùng lúc.
- Stale-while-revalidate khi nghiệp vụ cho phép.
- Pre-warm cache cho nội dung dự đoán được.
- Giới hạn concurrency và bảo vệ origin.
- Dùng negative caching cho kết quả không tồn tại nếu phù hợp.

Không cache dữ liệu nhạy cảm giữa các user nếu cache key không bao gồm security context cần thiết.

## 7. Buffering, batching và compression

### 7.1. Buffering và queue

Buffering giữ công việc tạm thời để producer và consumer hoạt động ở tốc độ khác nhau. Amazon SQS, Kinesis Data Streams và Amazon MSK có thể hỗ trợ các mô hình messaging/streaming khác nhau.

Lợi ích:

- Hấp thụ traffic burst.
- Tách tốc độ producer khỏi consumer.
- Cho phép retry và xử lý nền.
- Giảm số lần gọi downstream khi batch nhiều message.

Đánh đổi:

- Thêm queue age và thời gian chờ.
- Cần quản lý visibility timeout, retry, DLQ, ordering và retention.
- Message có thể được xử lý nhiều lần tùy delivery model.
- Backlog có thể tăng nhanh nếu consumer capacity không đủ.

Theo dõi ApproximateAgeOfOldestMessage, số message visible/in-flight, số lần retry, DLQ depth và tốc độ xử lý. Không chỉ theo dõi queue length: backlog nhỏ nhưng message cũ vẫn có thể vi phạm SLA.

### 7.2. Batching

Batching gộp nhiều thao tác thành một request hoặc một lần xử lý. Nó có thể giảm overhead network/API và tăng throughput.

Đổi lại:

- Công việc đầu tiên phải chờ batch đầy hoặc timeout.
- Một lỗi có thể ảnh hưởng nhiều record.
- Payload lớn hơn và có thể chạm quota.
- Cần xử lý partial failure và retry từng phần.

Batching phù hợp với ingestion, log processing và analytics. Với giao dịch cần phản hồi ngay, không nên chờ gom batch nếu latency budget không cho phép.

### 7.3. Compression

Compression giảm số byte truyền hoặc lưu trữ, có thể giảm network time và storage cost. Đổi lại, CPU dùng để nén/giải nén tăng và có thể làm latency cao hơn nếu payload nhỏ hoặc CPU đang bận.

Cần đo:

- Kích thước trước/sau nén.
- CPU time.
- Network throughput.
- End-to-end p95/p99 latency.
- Chi phí lưu trữ và truyền dữ liệu.

Không nén dữ liệu đã được nén tốt hoặc payload nhỏ nếu overhead lớn hơn lợi ích.

## 8. Durability: replication không thay thế backup

### 8.1. Replication

Replication tạo bản sao dữ liệu ở một hoặc nhiều vị trí. Nó giúp tăng resilience và có thể giảm thời gian phục hồi, nhưng replica thường phản ánh thay đổi từ nguồn.

Nếu một ứng dụng xóa nhầm object hoặc mã hóa sai dữ liệu, thao tác đó có thể lan sang replica. Replication không phải bản lịch sử độc lập.

Ví dụ:

- S3 Standard lưu object dư thừa trên nhiều thiết bị ở tối thiểu ba Availability Zones trong một Region theo thiết kế dịch vụ.
- S3 One Zone-IA lưu dữ liệu trong một AZ; có thể phù hợp dữ liệu tái tạo được hoặc bản sao phụ, nhưng có rủi ro khi mất toàn bộ AZ.
- S3 Replication có thể sao chép object giữa bucket/Region để đáp ứng yêu cầu địa lý hoặc phân tách dữ liệu.
- RDS Multi-AZ hỗ trợ availability/failover của database theo deployment model; không thay thế backup và point-in-time recovery.

Các mức durability/availability là thuộc tính thiết kế của từng storage class/dịch vụ, không phải cam kết rằng người dùng không thể xóa nhầm hoặc ghi đè dữ liệu.

### 8.2. Backup và versioning

Backup tạo điểm khôi phục độc lập với trạng thái hiện tại của workload. Các lớp bảo vệ có thể gồm:

- S3 Versioning để giữ phiên bản object.
- S3 Object Lock để bảo vệ object theo retention/legal hold khi cấu hình phù hợp.
- AWS Backup để quản lý backup plan, vault và lifecycle cho resource được hỗ trợ.
- Snapshot và point-in-time recovery cho database/storage.
- Copy backup sang account hoặc Region khác.
- Backup vault protection và quyền IAM tách biệt với workload owner.

Backup có chi phí lưu trữ, copy, retrieval và quản trị. Retention dài giúp phục hồi sâu hơn nhưng tăng chi phí. Retention quá ngắn có thể không đủ để phát hiện ransomware hoặc corruption xảy ra âm thầm.

### 8.3. RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa tổ chức chấp nhận mất, thường đo bằng thời gian.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ sau gián đoạn.

| Chiến lược | RPO/RTO tương đối | Chi phí/độ phức tạp |
|---|---|---|
| Backup định kỳ, restore khi cần | Có thể có RPO dài hơn và RTO phụ thuộc thời gian restore. | Chi phí vận hành thấp hơn, nhưng phải kiểm thử restore. |
| Backup thường xuyên + PITR | RPO có thể ngắn hơn; RTO phụ thuộc dịch vụ và kích thước dữ liệu. | Tăng chi phí backup và quản lý retention. |
| Warm standby | RPO/RTO thường thấp hơn backup-only nếu replication và capacity được duy trì. | Có chi phí chạy môi trường dự phòng và kiểm thử failover. |
| Active-active đa Region | Có thể giảm thời gian gián đoạn cho một số workload. | Chi phí và complexity cao; cần giải quyết consistency, conflict và routing. |

Không chọn DR strategy chỉ theo tên gọi. Đo RPO/RTO trong diễn tập restore/failover. Một backup chưa từng restore thành công chưa chứng minh rằng hệ thống có thể phục hồi đúng hạn.

## 9. Multi-AZ và Multi-Region: tăng resilience, tăng chi phí

### 9.1. Multi-AZ

Triển khai nhiều AZ trong một Region giúp workload chịu được một số lỗi hạ tầng hoặc AZ. Các thành phần như load balancer, Auto Scaling, RDS Multi-AZ và dịch vụ lưu trữ regional có thể hỗ trợ mô hình này.

Lợi ích:

- Giảm phụ thuộc vào một địa điểm vật lý.
- Có thể failover hoặc tiếp tục phục vụ từ AZ còn hoạt động.
- Phù hợp nhiều hệ thống production cần high availability.

Đánh đổi:

- Tăng số tài nguyên hoặc capacity dự phòng.
- Có thể có chi phí truyền dữ liệu liên AZ.
- Cần kiểm tra application session, connection retry, DNS và failover behavior.
- Không bảo vệ khỏi lỗi logic, credential compromise hoặc xóa nhầm.

### 9.2. Multi-Region

Multi-Region đặt workload hoặc dữ liệu tại nhiều AWS Regions. Mô hình này có thể đáp ứng disaster recovery, data residency hoặc giảm latency cho người dùng phân tán toàn cầu.

Lợi ích:

- Tách biệt khỏi sự cố ảnh hưởng một Region.
- Có thể phục vụ người dùng gần hơn.
- Tạo lựa chọn failover địa lý và data residency.

Đánh đổi:

- Tăng compute, storage, replication và data transfer cost.
- Cần quản lý DNS/routing, certificates, secrets, IAM, quotas và deployment ở nhiều Region.
- Replication có thể bất đồng bộ và có lag.
- Multi-writer cần xử lý conflict và concurrent updates.
- Runbook, game day và monitoring phức tạp hơn.
- Một số dịch vụ hoặc tính năng không có ở mọi Region.

Không mặc định Multi-Region là kiến trúc tốt hơn Multi-AZ. Nếu RTO/RPO của business được đáp ứng bằng Multi-AZ và backup cross-Region, active-active có thể không đáng với chi phí và complexity.

## 10. Chọn storage theo access pattern và giá trị dữ liệu

Một workload thường có nhiều loại dữ liệu với yêu cầu khác nhau. Không nên lưu mọi dữ liệu vào cùng một storage tier.

| Dữ liệu | Đặc tính truy cập | Hướng lựa chọn |
|---|---|---|
| Object công khai, đọc thường xuyên | Cần truy cập nhanh, phân phối rộng. | S3 Standard + CloudFront. |
| Object truy cập không đều | Có thể cần truy xuất nhanh nhưng tần suất khó dự đoán. | S3 Intelligent-Tiering nếu economics phù hợp. |
| Dữ liệu ít truy cập nhưng cần lấy nhanh | Chấp nhận storage cost thấp hơn và retrieval charge. | S3 Standard-IA hoặc One Zone-IA theo yêu cầu resilience. |
| Archive cần giữ lâu | Hiếm khi truy cập, chấp nhận thời gian restore. | S3 Glacier storage classes theo thời gian truy xuất. |
| Database transaction | Random read/write, transaction và query. | RDS/Aurora/DynamoDB theo data model và access pattern. |
| Cache | Dữ liệu có thể tái tạo hoặc có nguồn chính. | ElastiCache hoặc edge cache. |
| File chia sẻ đồng thời | Nhiều compute cần filesystem semantics. | Amazon EFS hoặc Amazon FSx theo protocol và workload. |

Khi chọn storage class, cần xem minimum storage duration, retrieval charges, transition requests, lifecycle, replication và thời gian restore. Một class có giá lưu trữ thấp có thể đắt hơn nếu object được truy xuất thường xuyên.

## 11. Chi phí của latency, durability và complexity

### 11.1. Tính tổng chi phí sở hữu

Một mô hình ước lượng đơn giản:

\[
TCO = C_{compute} + C_{storage} + C_{requests} + C_{network}
+ C_{replication} + C_{backup} + C_{observability}
+ C_{operations}
\]

Trong đó C_operations gồm nhân lực, công cụ và chi phí vận hành. Mô hình thực tế có thể bổ sung license, support, security, compliance và chi phí downtime.

Khi so sánh phương án, dùng cùng một workload profile:

- Số request/transaction theo ngày và giờ cao điểm.
- Tỷ lệ read/write.
- Payload size và retention.
- Số AZ/Region.
- Cache hit ratio và replication volume.
- RPO/RTO, backup retention và restore frequency.
- Số deployment, incident và giờ vận hành.

### 11.2. Ví dụ cache và database cost

Giả sử API catalog nhận 1.000.000 lượt đọc mỗi ngày. Nếu không có cache, toàn bộ request đi tới database. Nếu cache hit ratio đạt 90%, khoảng 900.000 lượt đọc được phục vụ từ cache và khoảng 100.000 lượt cần đọc từ database (bỏ qua refresh, invalidation và request phụ).

Cache giảm 90% số lần đọc database trong mô hình đơn giản, nhưng phát sinh chi phí cache và cần chính sách freshness. Quyết định chỉ có lợi khi tổng chi phí cache + database sau thay đổi thấp hơn hoặc business value của latency cải thiện lớn hơn chi phí tăng thêm.

Không lấy hit ratio mục tiêu làm bảo đảm. Hãy đo theo key distribution, TTL, cache eviction và traffic thực.

### 11.3. Ví dụ chi phí redundancy

Giả sử một workload có hai phương án:

- Phương án A: một Region, Multi-AZ, backup cross-Region.
- Phương án B: hai Region active-active, replication liên tục.

Phương án B thường có nhiều compute/database capacity hơn, network/replication traffic, deployment pipeline và monitoring ở cả hai Region. Nó có thể đáng giá nếu downtime của một Region gây tổn thất rất lớn hoặc yêu cầu latency toàn cầu. Nếu workload chỉ cần khôi phục trong vài giờ, phương án A có thể đáp ứng với chi phí thấp hơn.

Hãy dùng AWS Pricing Calculator và bảng giá dịch vụ theo Region để tính con số thực tế. Không dùng một mức giá minh họa cho mọi account, Region, usage pattern hoặc hợp đồng.

## 12. Độ phức tạp và chi phí vận hành

Một giải pháp có thể giảm latency nhưng thêm nhiều trạng thái cần đồng bộ. Ví dụ, dùng cache, read replica, queue và search index đồng thời sẽ tạo ra nhiều bản sao của cùng dữ liệu.

Nhóm cần trả lời:

- Nguồn dữ liệu chính là gì?
- Khi dữ liệu thay đổi, bản sao nào được cập nhật trước?
- Có thể chấp nhận dữ liệu cũ bao lâu?
- Nếu event bị gửi hai lần, consumer xử lý thế nào?
- Nếu event bị mất hoặc consumer chết, ai phát hiện?
- Làm sao rebuild cache/index/read model?
- Khi failover, hệ thống chọn writer nào?
- Có cách reconcile dữ liệu sau khi hai Region cùng ghi không?
- Runbook nào cần trực vận hành và ai là owner?

Một thành phần chỉ nên được thêm khi có lợi ích đo được. Nếu cache chỉ tăng vài mili giây nhưng thêm nhiều lỗi stale data, invalidation và incident, có thể không đáng.

### 12.1. Reversible và irreversible decisions

Một số quyết định có thể đảo ngược nhanh:

- TTL cache.
- Autoscaling threshold.
- Instance size.
- Batch size.
- Timeout.

Một số quyết định khó đảo ngược:

- Database engine hoặc data model.
- Partition key/sharding strategy.
- Giao thức event/schema.
- Multi-Region write ownership.
- Data residency và retention model.

Với quyết định khó đảo ngược, cần PoC, migration plan, rollback, compatibility strategy và ADR trước khi triển khai rộng.

## 13. Decision matrix: chọn phương án dựa trên bằng chứng

Có thể dùng ma trận điểm để so sánh phương án, nhưng điểm số không thay thế các ràng buộc bắt buộc. Trước tiên loại phương án vi phạm compliance, RPO/RTO hoặc security boundary.

Ví dụ so sánh ba phương án cho catalog đọc nhiều:

| Tiêu chí | Trọng số | A: DB trực tiếp | B: DB + cache | C: DB + read replica + cache |
|---|---:|---:|---:|---:|
| Latency | 30% | 2 | 5 | 5 |
| Durability/consistency | 20% | 5 | 4 | 4 |
| Cost | 20% | 5 | 4 | 2 |
| Complexity | 20% | 5 | 3 | 2 |
| Scalability | 10% | 2 | 4 | 5 |

Điểm minh họa theo thang 1–5, không phải benchmark AWS. Nhóm cần thay trọng số và điểm theo yêu cầu thật. Phương án B có thể là lựa chọn cân bằng nếu cache đáp ứng latency và độ cũ được phép. Phương án C có thể phù hợp khi read load lớn đến mức cache đơn lẻ chưa đủ.

### 13.1. Quy trình ra quyết định

1. Ghi yêu cầu business và non-functional requirements.
2. Xác định ràng buộc bắt buộc: compliance, security, RPO/RTO, data residency.
3. Đo baseline latency, throughput, cost và failure behavior.
4. Liệt kê tối đa vài phương án khả thi.
5. Đánh giá tác động lên cả bốn chiều và các trụ cột liên quan.
6. Tạo PoC hoặc load test cho giả định quan trọng.
7. Chạy failure test: mất AZ, network partition, queue backlog, cache flush, replica lag hoặc restore.
8. Chọn phương án và ghi rõ điều gì được ưu tiên, điều gì được chấp nhận đánh đổi.
9. Triển khai theo giai đoạn và theo dõi metrics.
10. Review lại khi traffic, dữ liệu, giá dịch vụ hoặc business requirements thay đổi.

## 14. Tình huống thiết kế: cửa hàng trực tuyến

Một cửa hàng trực tuyến có ba luồng chính:

- Catalog và hình ảnh sản phẩm: đọc rất nhiều, cập nhật không liên tục.
- Checkout và thanh toán: cần đúng trạng thái đơn hàng, tránh ghi trùng và không xác nhận sai giao dịch.
- Notification và analytics: có thể xử lý nền sau khi đơn hàng được tạo.

### 14.1. Catalog

Thiết kế:

- CloudFront cache ảnh và nội dung công khai.
- ElastiCache cache thông tin sản phẩm thường đọc.
- Database là nguồn dữ liệu chính.
- TTL theo mức độ thường xuyên cập nhật; invalidation khi có thay đổi quan trọng.

Đánh đổi: tăng cache cost và complexity để giảm latency và tải database. Nếu một sản phẩm vừa thay giá, cache cần được cập nhật theo SLA freshness đã thống nhất.

### 14.2. Checkout và payment

Thiết kế:

- Ghi order và outbox event trong một transaction database.
- Dùng idempotency key để xử lý retry từ client/payment provider.
- Chỉ xác nhận order đã được ghi nhận khi transaction commit thành công.
- Publisher gửi event tới queue; worker xử lý inventory/notification.
- Dùng Multi-AZ database nếu yêu cầu availability của workload cần.
- Backup/PITR và restore test để đáp ứng RPO/RTO.

Đánh đổi: đường ghi có thể chậm hơn do commit và kiểm soát idempotency, nhưng giảm rủi ro mất hoặc tạo trùng giao dịch. Notification được xử lý bất đồng bộ để không kéo dài thời gian phản hồi checkout.

### 14.3. Notification và analytics

Thiết kế:

- SQS hoặc EventBridge nhận event sau khi order commit.
- Consumer xử lý idempotent, có retry và DLQ.
- Analytics pipeline gom batch và ghi vào data lake.
- Dashboard chấp nhận dữ liệu trễ theo SLA analytics.

Đánh đổi: dữ liệu analytics không cập nhật tức thời, nhưng chi phí và complexity thấp hơn việc đồng bộ tất cả hệ thống trong request checkout.

### 14.4. Bảng quyết định theo luồng

| Luồng | Latency | Durability | Cost | Complexity |
|---|---|---|---|---|
| Catalog | Ưu tiên thấp | Dữ liệu gốc phải bền; cache có thể stale. | Cache tăng cost nhưng giảm DB load. | TTL/invalidation và cache key. |
| Checkout | Latency quan trọng nhưng correctness là ràng buộc. | Transaction commit, backup và idempotency. | Chấp nhận chi phí database/HA phù hợp. | Outbox, retry, reconciliation. |
| Notification | Không cần tức thời. | Queue và retry bảo vệ công việc. | Worker scale theo backlog. | DLQ và xử lý duplicate. |
| Analytics | Có thể trễ theo batch. | Retention và replay theo yêu cầu. | Tối ưu storage/compute theo chu kỳ. | Pipeline, schema và data quality. |

## 15. Các anti-pattern cần tránh

1. **Tối ưu p50 nhưng bỏ qua p99.** Người dùng vẫn gặp request rất chậm.
2. **Thêm cache trước khi đo bottleneck.** Cache không giải quyết mọi vấn đề và có thể làm sai dữ liệu.
3. **Dùng replica như backup.** Replica có thể sao chép thao tác xóa hoặc corruption.
4. **Trả thành công trước khi dữ liệu được lưu bền vững.** Process crash có thể làm mất thao tác.
5. **Giữ mọi bước trong request đồng bộ.** Một dependency chậm có thể kéo dài toàn bộ latency.
6. **Đưa mọi event vào queue mà không có idempotency.** Retry có thể tạo giao dịch trùng.
7. **Chọn Multi-Region chỉ vì muốn high availability.** Complexity và cost có thể vượt nhu cầu business.
8. **Sharding quá sớm.** Tăng độ phức tạp trước khi chứng minh database hiện tại không đáp ứng.
9. **Chọn storage class chỉ theo giá GB/tháng.** Bỏ qua retrieval, minimum duration, transition và restore time.
10. **Đo chi phí chỉ ở compute.** Bỏ qua data transfer, logs, backup, replication và vận hành.
11. **Không kiểm thử restore.** Backup tồn tại nhưng có thể không đáp ứng RTO.
12. **Không đặt timeout hoặc giới hạn retry.** Có thể gây retry storm và làm sự cố lan rộng.
13. **Không đo replication lag.** Read replica hoặc Region dự phòng có thể chưa có dữ liệu cần thiết.
14. **Không ghi lại trade-off.** Nhóm sau không biết lý do lựa chọn và khó quyết định khi điều kiện thay đổi.

## 16. Câu hỏi tự kiểm tra

**1. Durability khác availability như thế nào?**

Durability nói về khả năng dữ liệu tồn tại sau lỗi; availability nói về khả năng truy cập dịch vụ/dữ liệu khi cần.

**2. Vì sao replication không thay thế backup?**

Replication có thể sao chép cả thao tác xóa nhầm, ghi đè hoặc corruption. Backup/versioning giữ điểm khôi phục độc lập theo retention.

**3. Khi nào ghi đồng bộ phù hợp?**

Khi caller cần biết transaction quan trọng đã commit trước khi xác nhận thành công, chẳng hạn cập nhật số dư hoặc tạo đơn hàng.

**4. Khi nào xử lý bất đồng bộ phù hợp?**

Khi công việc có thể hoàn tất sau phản hồi, như notification, thumbnail, analytics hoặc tác vụ nền.

**5. Eventual consistency có nghĩa dữ liệu bị mất không?**

Không. Nó có nghĩa replica có thể tạm thời trả dữ liệu cũ trước khi hội tụ.

**6. Vì sao cache có thể làm sai nghiệp vụ?**

Cache có thể phục vụ dữ liệu stale hoặc dữ liệu của sai user nếu TTL, invalidation hoặc cache key được thiết kế sai.

**7. Read replica tạo ra trade-off nào?**

Tăng read throughput và giảm tải primary, nhưng thêm chi phí, replication lag và routing complexity.

**8. Queue giúp ích gì khi traffic tăng đột biến?**

Queue hấp thụ burst và tách tốc độ producer khỏi consumer; đổi lại có queue age, retry, DLQ và consistency trễ.

**9. RPO và RTO khác nhau ra sao?**

RPO là lượng dữ liệu tối đa có thể mất; RTO là thời gian tối đa để khôi phục dịch vụ theo mục tiêu.

**10. Khi nào Multi-Region đáng chi phí?**

Khi yêu cầu business về disaster recovery, data residency hoặc latency địa lý không thể đáp ứng bằng một Region cùng Multi-AZ/backup.

**11. Vì sao p99 latency quan trọng?**

Nó thể hiện trải nghiệm của nhóm request chậm nhất và giúp phát hiện tail latency bị che bởi trung bình.

**12. Tại sao phải ghi ADR?**

ADR lưu bối cảnh, phương án, lý do, tác động và điều kiện review lại để quyết định có thể được hiểu và đánh giá sau này.

## 17. Checklist trước khi chốt kiến trúc

- [ ] Đã xác định latency target theo p50/p95/p99 và business outcome.
- [ ] Đã phân loại dữ liệu và xác định nguồn dữ liệu chính.
- [ ] Đã xác định consistency model cho từng luồng đọc/ghi.
- [ ] Đã định nghĩa RPO, RTO và kiểm thử restore/failover.
- [ ] Đã phân biệt replication, high availability và backup.
- [ ] Đã đo cache hit ratio, freshness, invalidation và stale data risk.
- [ ] Queue có retry, DLQ, idempotency và theo dõi backlog/age.
- [ ] Read replica/partitioning có lý do dựa trên workload measurement.
- [ ] Multi-AZ/Region đáp ứng business requirement và được tính cost.
- [ ] Storage class được chọn theo access pattern, retrieval và retention.
- [ ] Đã tính data transfer, request, replication, backup, logs và operational cost.
- [ ] Đã đánh giá số thành phần, dependency, failure mode và kỹ năng vận hành.
- [ ] Có load test, failure test và PoC cho giả định quan trọng.
- [ ] Quyết định quan trọng có ADR, owner và ngày review.
- [ ] Có metrics/cảnh báo để phát hiện trade-off không còn phù hợp.

## Tài liệu tham khảo

- [Evaluate trade-offs between performance and other non-functional requirements](https://docs.aws.amazon.com/wellarchitected/latest/framework/perf01-bp02.html)
- [Understanding trade-offs in the AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/perf-understanding-tradeoffs.html)
- [Evaluate how trade-offs impact customers and architecture efficiency](https://docs.aws.amazon.com/wellarchitected/2024-06-27/framework/perf_architecture_evaluate_trade_offs.html)
- [Data management best practices](https://docs.aws.amazon.com/wellarchitected/latest/framework/perf03.html)
- [Data protection and durability in Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DataDurability.html)
- [Amazon S3 FAQs – durability and data protection](https://aws.amazon.com/s3/faqs/)
- [S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html)
- [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [S3 Replication](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html)
- [Amazon DynamoDB read consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html)
- [Amazon DynamoDB global tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html)
- [Amazon RDS Multi-AZ deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.html)
- [Amazon CloudFront cache expiration](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Expiration.html)
- [Understanding CloudFront cache policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cache-key-understand-cache-policy.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Exactly-once processing in Amazon SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Amazon SQS outage recovery scenarios](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/designing-for-outage-recovery-scenarios.html)
- [AWS Backup feature availability](https://docs.aws.amazon.com/aws-backup/latest/devguide/backup-feature-availability.html)
- [AWS Pricing Calculator](https://calculator.aws/)
- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/framework.html)

