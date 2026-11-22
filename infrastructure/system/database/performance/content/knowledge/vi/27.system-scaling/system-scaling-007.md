# Tác động hiệu năng của giao dịch hoặc phép nối phân tán

Khi dữ liệu được chia trên nhiều node, shard hoặc vùng địa lý, một thao tác nghiệp vụ có thể cần nhiều database participant cùng tham gia. Giao dịch phân tán phải phối hợp để các thay đổi được commit hoặc abort nhất quán; phép nối phân tán phải đưa dữ liệu từ nhiều node về cùng một nơi xử lý hoặc phân phối lại dữ liệu theo khóa join. Cả hai đều phát sinh chi phí mạng, đồng bộ, serialization, hàng đợi và xử lý lỗi. Nếu thiết kế không chú ý vị trí dữ liệu, một truy vấn ngắn hoặc một giao dịch nhỏ cũng có thể chậm hơn nhiều so với thao tác chỉ diễn ra trên một node.

Bài học thuộc chương **Mở rộng hệ thống** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Trong hệ thống phân tán, việc tối ưu cần xem cả số participant, số round trip, lượng dữ liệu trao đổi, độ lệch tải, thời gian giữ khóa và yêu cầu nhất quán; không thể chỉ nhìn thời gian thực thi SQL tại một node.

## 1. Hai loại công việc phân tán cần phân biệt

**Giao dịch phân tán (distributed transaction)** là một transaction có thay đổi hoặc phụ thuộc dữ liệu ở nhiều participant và cần một cơ chế phối hợp để bảo đảm kết quả theo semantics đã chọn. Participant có thể là nhiều shard của cùng một distributed database, nhiều database resource được điều phối qua XA, hoặc các hệ thống dịch vụ có quy trình nghiệp vụ riêng.

**Phép nối phân tán (distributed join)** là phép join mà dữ liệu của hai hoặc nhiều đầu vào nằm trên các node khác nhau. Query engine phải thực hiện join tại các node có dữ liệu, gửi một tập dữ liệu đến node khác hoặc repartition/shuffle các đầu vào theo join key.

| Khía cạnh | Giao dịch phân tán | Phép nối phân tán |
|---|---|---|
| Mục tiêu | Đồng bộ thay đổi và kết quả commit/abort giữa participant | Kết hợp hàng từ các nguồn dữ liệu phân tán |
| Chi phí chính | Round trip điều phối, ghi log bền vững, lock/wait, recovery | Truyền dữ liệu, shuffle, serialization, skew, spill và phối hợp stage |
| Tài nguyên bị giữ | Transaction state, lock, connection và log resource | Buffer, network bandwidth, worker, memory và temporary storage |
| Rủi ro hiệu năng | Transaction kéo dài, participant chậm, trạng thái in-doubt | Network amplification, data movement lớn, một node bị lệch tải |
| Cách giảm chi phí | Giảm số participant, rút ngắn transaction, đặt dữ liệu gần nhau | Colocation, pushdown, projection/filter sớm, broadcast có kiểm soát |

Hai khái niệm có thể xuất hiện cùng lúc. Ví dụ, một transaction đọc dữ liệu qua distributed join rồi cập nhật nhiều shard; khi đó cả chi phí query phân tán và chi phí commit phân tán đều có thể ảnh hưởng latency.

## 2. Vì sao thao tác qua nhiều node thường chậm hơn?

Một thao tác cục bộ thường có thể dùng bộ nhớ, CPU và storage của một node. Khi cần node khác, hệ thống phải gửi thông điệp qua mạng và chờ phản hồi. Thời gian bổ sung có thể đến từ:

- **Round-trip time (RTT):** thời gian gửi yêu cầu và nhận phản hồi qua mạng.
- **Serialization/deserialization:** chuyển object hoặc row thành dạng truyền và giải mã ở đầu nhận.
- **Network transfer:** thời gian truyền số byte dữ liệu thực tế.
- **Queueing:** chờ worker, connection, network buffer hoặc slot thực thi ở node đích.
- **Coordination:** điều phối thứ tự công việc, đồng bộ trạng thái và tổng hợp kết quả.
- **Durability:** ghi log hoặc chờ xác nhận bền vững từ storage/replica.
- **Failure handling:** timeout, retry, leader change, node unavailable hoặc phục hồi transaction.

Một mô hình ước lượng đơn giản cho một giai đoạn mạng là:

```text
T_stage ≈ số_RTT_nối_tiếp × RTT
        + bytes_truyền / bandwidth_hữu_dụng
        + serialization
        + queueing
        + xử_lý_tại_node
```

Đây chỉ là mô hình để phân tích. Các node có thể xử lý song song, nhiều gói tin có thể truyền đồng thời và một số công việc có thể chồng lấp. Trong một stage song song, thời gian thường bị chi phối bởi participant chậm nhất cộng thời gian điều phối; không thể luôn cộng thời gian của mọi node như thể chúng chạy tuần tự.

### 2.1. RTT có thể quan trọng hơn số câu SQL

Một câu SQL đơn giản cần một lượt trao đổi đến shard khác có thể tốn nhiều thời gian hơn một câu SQL phức tạp nhưng chạy tại chỗ. Nếu một transaction thực hiện nhiều lần đọc/ghi tuần tự giữa các service hoặc shard, từng RTT nối tiếp sẽ cộng dồn.

Ví dụ, nếu RTT giữa hai vùng là 40 ms và một luồng xử lý cần 5 lượt trao đổi tuần tự, riêng thời gian chờ mạng có thể vào khoảng 200 ms trước khi tính xử lý và ghi log. Nếu các lời gọi độc lập có thể chạy song song, tổng thời gian có thể thấp hơn, nhưng vẫn bị giới hạn bởi participant chậm nhất và tài nguyên dùng chung.

### 2.2. Số node tham gia ảnh hưởng tail latency

Khi một request phải chờ nhiều participant, khả năng có ít nhất một participant phản hồi chậm tăng lên. Nếu một truy vấn fan-out đến hàng chục shard và phải đợi tất cả, latency p95/p99 của request có thể bị chi phối bởi shard chậm nhất. Đây là lý do cần theo dõi latency theo từng shard/participant, không chỉ latency tổng.

## 3. Giao dịch phân tán và atomic commit

Khi một transaction thay đổi nhiều participant, hệ thống cần một cách quyết định các thay đổi được commit đồng bộ hay abort. Một giao thức phổ biến là **Two-Phase Commit (2PC)**. Một số hệ thống dùng biến thể, giao thức atomic commit khác hoặc tích hợp consensus; không nên giả định mọi distributed database đều triển khai cùng một cơ chế.

### 3.1. Vai trò coordinator và participant

- **Coordinator:** điều phối transaction, yêu cầu participant chuẩn bị và quyết định commit/abort theo kết quả.
- **Participant:** node/resource thực hiện phần công việc của transaction, chuẩn bị khả năng commit và phản hồi coordinator.
- **Transaction identifier:** định danh chung giúp các node liên kết trạng thái của cùng transaction.
- **Transaction log:** lưu trạng thái cần thiết để phục hồi quyết định sau sự cố.

### 3.2. Hai pha của Two-Phase Commit

**Pha 1 — Prepare:**

1. Coordinator gửi yêu cầu `PREPARE` đến các participant.
2. Mỗi participant kiểm tra transaction có thể commit hay không.
3. Participant thực hiện các bước cần thiết, ghi prepare record bền vững theo giao thức và giữ các resource/lock cần thiết để có thể commit sau đó.
4. Participant trả lời `YES` hoặc `NO`.

**Pha 2 — Commit hoặc Abort:**

1. Nếu tất cả participant trả lời `YES`, coordinator ghi quyết định commit bền vững rồi gửi `COMMIT`.
2. Nếu có participant trả lời `NO` hoặc transaction phải hủy theo chính sách, coordinator quyết định abort và gửi `ABORT`.
3. Participant thực hiện quyết định, ghi log trạng thái cần thiết, giải phóng resource và phản hồi hoàn tất.

```text
Coordinator                  Participant A        Participant B
     |                              |                    |
     |--------- PREPARE ----------->|                    |
     |--------- PREPARE ------------------------------->|
     |                              |                    |
     |<-------- YES ----------------|                    |
     |<------------------------------- YES -------------|
     |                              |                    |
     |   ghi quyết định COMMIT      |                    |
     |--------- COMMIT ----------->|                    |
     |--------- COMMIT ------------------------------->|
     |                              |                    |
     |<-------- ACK ----------------|                    |
     |<------------------------------- ACK -------------|
     |                              |                    |
```

Trong triển khai thực tế, coordinator có thể gửi yêu cầu song song, có thêm thông điệp recovery/status và chi tiết ghi log khác nhau. Sơ đồ chỉ minh họa hai pha logic.

### 3.3. Vì sao 2PC làm tăng latency?

So với transaction chỉ chạy trên một participant, 2PC bổ sung các lượt trao đổi prepare và commit/abort. Mỗi participant còn có thể phải ghi log bền vững trước khi trả lời. Coordinator phải đợi các participant cần thiết, nên một participant chậm có thể kéo dài transaction tổng thể.

Chi phí tăng theo:

- Số participant và topology mạng.
- RTT giữa coordinator với participant.
- Thời gian flush log và độ trễ storage ở từng participant.
- Thời gian thực thi phần nghiệp vụ tại mỗi node.
- Số lượng transaction phân tán đồng thời.
- Mức tranh chấp lock và queue ở participant.

Không thể suy ra latency 2PC chỉ bằng `2 × RTT`: còn có ghi log, xử lý participant, thời gian chờ node chậm và các round trip phụ thuộc triển khai. Tuy nhiên, số pha và RTT nối tiếp là một thành phần quan trọng khi phân tích.

## 4. Lock duration và trạng thái in-doubt

Một participant có thể phải giữ lock hoặc resource cho đến khi nhận quyết định cuối cùng. Nếu coordinator hoặc mạng chậm sau prepare, transaction đã prepared có thể tiếp tục giữ lock trong khi chờ.

Hệ quả:

- Transaction khác phải chờ cùng hàng hoặc tài nguyên.
- Blocking chain và lock wait tăng.
- Deadlock hoặc timeout có thể tăng nếu nhiều transaction giao nhau trên các shard.
- Connection và transaction slot bị giữ lâu hơn.
- Throughput giảm dù CPU tại một số node chưa bão hòa.

Nếu coordinator gặp sự cố sau khi participant đã prepare nhưng trước khi nhận quyết định cuối cùng, participant có thể rơi vào trạng thái **in-doubt**. Participant không thể tự đoán commit hay abort nếu giao thức yêu cầu quyết định từ coordinator hoặc log recovery. Nó có thể phải giữ resource cho đến khi truy vấn được trạng thái quyết định hoặc quá trình recovery hoàn tất.

Đây là một trong những trade-off quan trọng của atomic commit: bảo đảm tính nguyên tử giữa nhiều resource có thể làm transaction phụ thuộc vào khả năng điều phối và phục hồi.

### 4.1. Timeout không tự chứng minh transaction đã abort

Nếu client timeout khi chờ kết quả commit, transaction có thể:

- Đã commit nhưng phản hồi bị mất.
- Đã abort.
- Đang được coordinator xử lý.
- Đang ở trạng thái in-doubt và chờ recovery.

Client không nên tự động gửi lại một thao tác không idempotent chỉ vì không nhận được response. Cần dùng transaction status/recovery API của nền tảng, idempotency key hoặc business operation identifier để xác định kết quả an toàn.

### 4.2. Deadlock giữa nhiều participant

Nếu các transaction khóa shard hoặc hàng theo thứ tự khác nhau, chúng có thể tạo chu trình chờ. Ví dụ transaction A khóa hàng trên shard 1 rồi chờ shard 2; transaction B khóa shard 2 rồi chờ shard 1. Deadlock detection có thể chọn một transaction làm victim để rollback.

Giảm nguy cơ bằng cách:

- Truy cập các resource theo thứ tự nhất quán nếu ứng dụng kiểm soát được.
- Giữ transaction ngắn và tránh chờ network/API bên ngoài khi đang giữ lock.
- Giảm số participant cần khóa đồng thời.
- Dùng retry có giới hạn và backoff/jitter cho lỗi retryable.
- Theo dõi deadlock graph hoặc wait-for graph theo từng node.

## 5. XA và transaction qua nhiều resource manager

XA là một chuẩn giao diện để transaction manager phối hợp transaction giữa các resource manager, ví dụ nhiều database hoặc database và message broker có hỗ trợ XA. Với mô hình phổ biến, transaction manager đóng vai trò coordinator và các resource manager tham gia prepare/commit theo giao thức tương ứng.

XA có thể giúp ứng dụng đạt atomic commit qua nhiều resource, nhưng cần cân nhắc:

- Nhiều round trip và log write.
- Connection/resource phải được giữ trong suốt transaction.
- Khả năng hỗ trợ và cấu hình của từng driver/resource manager.
- Recovery log và quy trình xử lý transaction in-doubt.
- Timeout, failover và sự khác biệt giữa các hệ thống.
- Giới hạn scalability khi số participant và transaction đồng thời tăng.

Không phải mọi database hoặc broker đều hỗ trợ XA đầy đủ. Cần kiểm tra compatibility, recovery procedure và giới hạn phiên bản trước khi triển khai.

### 5.1. Distributed database transaction và saga không giống nhau

**Saga** chia một quy trình nghiệp vụ thành nhiều local transaction, mỗi bước commit độc lập. Nếu bước sau thất bại, hệ thống có thể chạy compensating action để đưa trạng thái nghiệp vụ về một trạng thái chấp nhận được.

Saga không cung cấp atomic rollback vật lý như 2PC. Compensation là một thao tác nghiệp vụ mới, có thể thất bại hoặc cần retry. Đổi lại, saga tránh giữ một transaction database xuyên suốt nhiều service và thường phù hợp hơn với quy trình dài hoặc hệ thống độc lập.

Chọn 2PC/XA khi cần atomic commit thực sự giữa các resource hỗ trợ và chấp nhận chi phí điều phối. Chọn saga khi nghiệp vụ chấp nhận trạng thái trung gian và có thể định nghĩa compensation/idempotency. Không thay 2PC bằng saga mà không đánh giá lại yêu cầu consistency và hành vi khi lỗi.

## 6. Giảm chi phí giao dịch phân tán

### 6.1. Giảm số participant

Một transaction chỉ cập nhật một shard thường tránh được coordination xuyên shard. Thiết kế dữ liệu theo aggregate hoặc partition key của luồng nghiệp vụ có thể giúp các hàng thường được cập nhật cùng nhau nằm trên cùng participant.

Ví dụ, nếu thao tác tạo đơn hàng luôn cập nhật `orders` và `order_items`, có thể cân nhắc partition cùng theo `order_id` để các thao tác liên quan được colocate. Cần xem truy vấn theo customer, reporting và phân bố dữ liệu để tránh tạo hotspot hoặc làm truy vấn khác quá đắt.

### 6.2. Rút ngắn transaction

- Đọc/kiểm tra dữ liệu cần thiết trước khi bắt đầu transaction nếu semantics cho phép.
- Không gọi HTTP, gửi email hoặc chờ người dùng trong lúc giữ transaction DB.
- Giảm số câu SQL và round trip tuần tự giữa các participant.
- Chỉ cập nhật các hàng cần thiết.
- Dùng batch phù hợp thay cho hàng loạt thao tác nhỏ tuần tự khi driver/DB hỗ trợ.
- Commit ngay khi công việc atomic đã hoàn tất.

Không di chuyển thao tác ra ngoài transaction nếu điều đó tạo race condition hoặc phá vỡ invariant nghiệp vụ. Cần xác định dữ liệu nào phải được khóa/kiểm tra nguyên tử.

### 6.3. Giảm fan-out và round trip

Thay vì gọi từng shard một cách tuần tự, có thể gom yêu cầu hoặc thực hiện song song khi chúng độc lập. Tuy nhiên, parallel fan-out tăng đồng thời tải trên các node và vẫn phải đợi participant chậm nhất nếu kết quả cần đầy đủ.

Ưu tiên API/query cho phép gửi một lệnh theo batch, multi-row operation hoặc set-based SQL thay vì vòng lặp từng hàng qua mạng. Giảm round trip thường đem lại lợi ích lớn hơn tối ưu một biểu thức SQL nhỏ.

### 6.4. Đặt coordinator và participant gần nhau

Đặt ứng dụng/coordinator cùng region với database hoặc dùng topology mạng có RTT thấp có thể giảm thời gian trao đổi. Nhưng yêu cầu residency, disaster recovery, security zone và availability có thể giới hạn vị trí. Không đánh đổi yêu cầu pháp lý hoặc khả năng phục hồi chỉ để giảm vài mili giây.

### 6.5. Bảo đảm recovery và quan sát transaction

Theo dõi coordinator log, prepared transaction count, transaction age, participant status và thời gian recovery. Có quy trình xử lý in-doubt transaction theo hướng dẫn nền tảng; không tự xóa trạng thái prepared hoặc kill session tùy tiện vì có thể phá vỡ quyết định atomic commit.

## 7. Phép nối phân tán: dữ liệu cần gặp nhau ở đâu?

Một join phân tán cần đưa các hàng có cùng join key đến cùng một nơi xử lý. Nếu dữ liệu hai bảng đã được phân vùng tương thích theo join key, engine có thể join cục bộ trên từng node. Nếu không, nó có thể phải broadcast một phía hoặc shuffle/repartition dữ liệu.

Các chiến lược thường gặp:

1. **Colocated/local join:** hai phía được partition tương thích, cùng key nằm trên cùng node.
2. **Broadcast join:** gửi toàn bộ hoặc phần đã lọc của một phía nhỏ đến các node đang giữ phía lớn.
3. **Shuffle/repartition join:** phân phối lại cả hai phía theo hash join key để các hàng có cùng key đến cùng worker.
4. **Gather-to-coordinator:** chuyển dữ liệu về một node điều phối để join; đơn giản nhưng có thể tạo bottleneck.
5. **Semi-join/runtime filtering:** gửi tập key hoặc filter nhỏ sang phía dữ liệu lớn để giảm số hàng cần truyền/đọc.

### 7.1. Colocated join

Giả sử hai bảng `orders` và `order_items` cùng được phân vùng theo `order_id` bằng cùng hash function và cùng số bucket. Khi join:

```sql
SELECT o.order_id, i.product_id, i.quantity
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.order_id >= :from_id
  AND o.order_id < :to_id;
```

Các hàng cùng `order_id` có thể nằm trên cùng shard. Mỗi shard thực hiện phần join cục bộ, sau đó coordinator chỉ cần tổng hợp/trả kết quả. Cách này tránh shuffle lớn.

Colocation chỉ có hiệu quả khi partitioning thực sự tương thích và optimizer nhận ra. Khác hash function, số partition, key type hoặc partition map có thể khiến dữ liệu không colocated dù tên cột giống nhau.

### 7.2. Broadcast join

Nếu một bảng nhỏ sau khi lọc, query engine có thể broadcast bảng đó đến các worker chứa bảng lớn. Mỗi worker join phần dữ liệu lớn cục bộ với bản sao bảng nhỏ.

Ví dụ dimension `regions` chỉ có vài trăm hàng, còn `sales_fact` có hàng tỷ hàng. Broadcast `regions` có thể rẻ hơn shuffle toàn bộ fact table.

Broadcast không miễn phí. Nếu dimension sau filter vẫn lớn, số worker cao hoặc có nhiều query đồng thời, việc gửi và giữ nhiều bản sao có thể tiêu tốn network và memory. Hãy xem kích thước thực tế sau filter, không chỉ kích thước bảng gốc.

### 7.3. Shuffle/repartition join

Nếu hai bảng partition theo các khóa khác nhau, engine có thể hash-partition cả hai theo join key và chuyển các bucket đến worker tương ứng. Mọi hàng cùng join key sẽ đến cùng nơi để join.

```text
orders partitions                 order_items partitions
  shard A  shard B                   shard C  shard D
      \      /                          \      /
       hash repartition                  hash repartition
             \                            /
              \                          /
                 workers by order_id
                         |
                      local join
                         |
                    merge results
```

Shuffle có thể truyền một phần rất lớn dữ liệu qua mạng. Nếu đầu vào rộng hoặc predicate chưa được áp dụng trước shuffle, bytes truyền sẽ tăng mạnh. Nếu memory không đủ, engine có thể spill partition trung gian ra disk.

### 7.4. Gather về coordinator

Một số kế hoạch gửi một hoặc cả hai đầu vào về coordinator để thực hiện join. Với dữ liệu nhỏ, cách này có thể hợp lý. Với dữ liệu lớn, coordinator trở thành điểm nóng về network, CPU và memory, đồng thời giới hạn khả năng song song.

Không kết luận gather luôn xấu. Cần xem số hàng và byte thực tế, số worker, chi phí shuffle thay thế và khả năng xử lý của coordinator.

## 8. Giảm dữ liệu trước khi join phân tán

Các kỹ thuật projection pruning và predicate pushdown có tác động đặc biệt lớn trước network exchange.

### 8.1. Lọc trước khi shuffle

Ví dụ chỉ cần doanh thu của một tháng và một nhóm khu vực:

```sql
SELECT s.region_id, r.region_name, SUM(s.net_amount) AS revenue
FROM sales_fact AS s
JOIN regions AS r
  ON r.region_id = s.region_id
WHERE s.sale_date >= DATE '2026-10-01'
  AND s.sale_date <  DATE '2026-11-01'
  AND s.region_id IN (7, 8, 9)
GROUP BY s.region_id, r.region_name;
```

Nếu engine có thể partition prune theo `sale_date`, lọc `region_id` và chỉ đọc `region_id`, `net_amount` cùng các cột cần thiết, lượng dữ liệu gửi qua exchange sẽ giảm.

### 8.2. Chỉ truyền cột cần cho join và kết quả

Tránh `SELECT *` trong truy vấn phân tán. Mỗi cột dư có thể được serialize, truyền qua mạng, giữ trong shuffle buffer và giải mã ở worker khác. Projection pruning trước exchange giảm cả network bytes lẫn memory.

### 8.3. Semi-join reduction và Bloom filter

Nếu phía dimension tạo ra tập key nhỏ, engine có thể truyền key set hoặc Bloom filter sang scan phía fact. Fact worker loại bỏ hàng không có khả năng match trước khi gửi dữ liệu qua network. Bloom filter có thể có false positive nên vẫn cần phép join chính xác ở bước sau; nó không được dùng để tự tạo kết quả cuối.

Hiệu quả phụ thuộc cardinality, selectivity, kích thước filter và thời điểm filter sẵn sàng. Nếu tập key quá lớn hoặc ít chọn lọc, overhead tạo/truyền filter có thể không đáng.

## 9. Data skew và một shard trở thành nút thắt

Data skew xảy ra khi phân bố khóa không đều. Trong hash shuffle, một số key phổ biến có thể khiến một worker nhận nhiều hàng hơn hẳn các worker khác. Những worker khác hoàn thành sớm nhưng toàn stage phải đợi worker nặng nhất.

Ví dụ 30% đơn hàng có `tenant_id = 1`, trong khi hàng nghìn tenant còn lại chia đều phần còn lại. Hash partition theo `tenant_id` có thể tạo một partition lớn hơn nhiều so với các partition khác.

Dấu hiệu:

- Một worker có input rows/bytes cao hơn hẳn.
- Một partition shuffle lớn, thời gian xử lý dài hoặc spill nhiều.
- CPU/network ở một node cao trong khi các node khác rảnh.
- Query stage gần hoàn tất nhưng một task kéo dài.
- p95/p99 tăng mạnh dù average worker time thấp.

Biện pháp tùy workload:

- Dùng skew handling hoặc adaptive query execution nếu engine hỗ trợ.
- Tách hot key và xử lý riêng rồi hợp nhất kết quả đúng semantics.
- Salting key cho một số phép aggregate/join nếu có thể bảo đảm kết quả chính xác.
- Chọn partition key phản ánh phân bố dữ liệu tốt hơn.
- Broadcast phía nhỏ nếu đủ nhỏ sau filter.
- Dùng statistics và histogram phản ánh data skew.

Không salting khóa tùy tiện cho join nhiều-nhiều vì có thể tạo bản ghi trùng hoặc nhân bản kết quả. Phải thiết kế cách replicate/salt cả hai phía và kiểm chứng multiplicity.

## 10. Colocation và thiết kế khóa phân vùng

Để giảm distributed join và transaction, chọn partition key theo các truy vấn và thao tác nghiệp vụ thường xuyên cùng nhau.

Các câu hỏi thiết kế:

- Những bảng nào thường join với nhau?
- Những hàng nào thường được cập nhật trong cùng transaction?
- Khóa nào có cardinality và phân bố phù hợp?
- Có tenant hoặc key nóng gây skew không?
- Truy vấn cross-tenant/reporting cần fan-out ở mức nào?
- Có thể dùng cùng partition map/hash function cho các bảng liên quan không?
- Việc colocate có làm một node chứa quá nhiều dữ liệu hoặc trở thành hotspot không?

### 10.1. Colocation theo aggregate hoặc tenant

Trong hệ thống multi-tenant, partition theo `tenant_id` có thể đặt dữ liệu của một tenant trên cùng shard, giúp truy vấn và transaction trong tenant thường cục bộ. Nhưng nếu một tenant lớn vượt xa các tenant khác, shard đó có thể nóng. Ngoài ra, truy vấn báo cáo toàn tenant vẫn cần fan-out hoặc hệ thống phân tích riêng.

### 10.2. Colocation theo khóa nghiệp vụ

Với đơn hàng, `order_id` có thể là khóa tốt để đặt `orders` và `order_items` cùng shard. Nhưng truy vấn theo `customer_id` có thể phải phân tán nếu các đơn hàng của một customer không cùng partition. Không có partition key tối ưu cho mọi access pattern; cần ưu tiên workload chính và chấp nhận/thiết kế đường truy cập cho workload phụ.

### 10.3. Denormalization và materialized data

Lưu thêm một số thuộc tính dimension vào fact hoặc aggregate table có thể giảm join phân tán trong đường đọc. Đổi lại, hệ thống phải cập nhật bản sao, xử lý dữ liệu đến muộn và bảo đảm freshness. Denormalization là trade-off về write amplification và consistency, không phải cách xóa bỏ chi phí miễn phí.

## 11. Giao dịch phân tán kết hợp với phép nối phân tán

Một transaction có thể chạy distributed query để tìm các hàng cần cập nhật rồi commit trên nhiều shard. Ví dụ, nghiệp vụ chuyển tiền giữa hai tài khoản ở hai shard:

1. Tìm tài khoản nguồn và đích.
2. Kiểm tra số dư và trạng thái.
3. Trừ tiền ở shard nguồn.
4. Cộng tiền ở shard đích.
5. Commit atomic giữa hai participant.

Nếu truy vấn tìm tài khoản phải fan-out qua nhiều shard, phần đọc đã tốn network. Nếu transaction sau đó cập nhật hai shard, commit coordination tiếp tục tạo chi phí. Tối ưu cần xem cả access path để tìm hàng và transaction protocol để commit.

Một số hướng giảm chi phí:

- Đặt dữ liệu thường được cập nhật cùng nhau gần nhau khi semantics cho phép.
- Dùng account ID hoặc tenant ID để định tuyến trực tiếp thay vì scatter-gather.
- Giảm số lần đọc tuần tự trong transaction.
- Giữ transaction ngắn, không gọi dịch vụ ngoài khi đang giữ lock.
- Dùng idempotency key cho request có thể retry sau timeout.
- Tách read model/reporting khỏi đường ghi nếu có thể chấp nhận độ trễ đồng bộ.

Không được bỏ bước atomicity hoặc kiểm tra invariant chỉ để giảm số participant. Ví dụ chuyển tiền không thể chỉ cập nhật một phía rồi hy vọng tác vụ nền sẽ luôn cập nhật phía còn lại nếu nghiệp vụ yêu cầu không tạo hoặc mất tiền.

## 12. Isolation, consistency và hiệu năng

Giao dịch phân tán phải giữ semantics nhất quán mà ứng dụng yêu cầu. Một số hệ thống cung cấp serializable transaction xuyên shard; một số dùng snapshot isolation hoặc consistency model khác; một số quy trình service-level dùng eventual consistency.

Các yếu tố cần hiểu:

- **Isolation level:** xác định transaction nhìn thấy thay đổi của transaction khác như thế nào.
- **Read consistency:** các phần dữ liệu được đọc có thuộc một snapshot nhất quán không.
- **Atomicity:** các thay đổi của transaction được commit cùng nhau hay không.
- **Durability:** commit được bảo đảm tồn tại sau sự cố theo cấu hình nào.
- **Replication consistency:** commit có chờ replica hoặc quorum hay không.
- **Retry semantics:** lỗi serialization/deadlock/timeout có thể retry an toàn không.

Giảm isolation hoặc chuyển sang eventual consistency có thể giảm chờ trong một số kiến trúc, nhưng có thể làm thay đổi kết quả nghiệp vụ. Chỉ thực hiện khi nghiệp vụ chấp nhận rõ các anomaly hoặc trạng thái trung gian.

### 12.1. Retry và idempotency

Distributed transaction có thể trả timeout trong khi kết quả commit chưa rõ. Client retry một thao tác tạo đơn hàng hoặc chuyển tiền mà không có idempotency có thể tạo bản ghi trùng hoặc thực hiện hai lần.

Một mẫu xử lý an toàn có thể gồm:

- Mỗi business request có idempotency key duy nhất.
- Server lưu trạng thái xử lý và kết quả gắn với key.
- Retry chỉ áp dụng cho lỗi được xác định retryable.
- Dùng exponential backoff và jitter.
- Truy vấn trạng thái transaction/operation trước khi thực hiện lại khi kết quả lần trước chưa rõ.

Idempotency ở tầng ứng dụng không tự thay thế atomic commit; nó giúp kiểm soát việc lặp lại request.

## 13. Đo chi phí giao dịch phân tán

Đo tổng latency là chưa đủ. Cần tách các giai đoạn và participant.

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Transaction | Transaction duration, commit latency, abort rate | Transaction phân tán kéo dài bao lâu và thường thất bại thế nào? |
| Coordination | Participant count, prepare duration, decision/commit duration | Chi phí điều phối nằm ở pha nào? |
| Network | RTT, bytes sent/received, retransmission, connection wait | Mạng có phải bottleneck không? |
| Participant | Per-node latency, queue, CPU, I/O, log flush | Node nào làm transaction chậm? |
| Locking | Lock wait, blocking chain, deadlock, prepared transaction age | Resource bị giữ lâu đến đâu? |
| Recovery | In-doubt count/age, recovery duration, coordinator availability | Có transaction chờ quyết định hoặc recovery không? |
| Application | End-to-end p95/p99, timeout, retry, duplicate request | Người gọi quan sát điều gì? |

Theo dõi phân vị và phân bố theo participant. Average commit latency có thể che giấu một shard thường xuyên chậm hoặc một nhóm transaction có nhiều participant.

## 14. Đo chi phí phép nối phân tán

Với distributed join, cần theo dõi:

- Số hàng và bytes ở mỗi đầu vào trước join.
- Số partition/shard được truy cập.
- Số hàng/bytes sau filter và projection.
- Exchange type: local, broadcast, repartition, gather.
- Network bytes và shuffle read/write.
- Task/worker duration và mức skew.
- Memory peak, spill bytes và temporary I/O.
- Join output rows, duplicate/multiplicity và thời gian tổng hợp.
- Remote scan latency và connector pushdown effectiveness.

Một truy vấn có thể có thời gian scan thấp nhưng shuffle lớn; hoặc bytes shuffle thấp nhưng một hot partition kéo dài. Cần xem từng stage trong distributed execution plan.

### 14.1. Đọc execution plan

Hãy tìm các dấu hiệu:

- Local/colocated join hay repartition exchange.
- Broadcast build side và kích thước build side thực tế.
- Filter/projection có xảy ra trước exchange không.
- Partition pruning và số shard được đọc.
- Estimated rows so với actual rows.
- Skew giữa task/worker.
- Spill ra disk và memory pressure.
- Gather về coordinator và lượng dữ liệu được gom.

Tên operator khác nhau giữa distributed SQL engine, MPP warehouse và database shard middleware. Hãy đọc plan theo tài liệu đúng sản phẩm, đồng thời dùng runtime metrics để xác nhận.

## 15. Ví dụ: join hai bảng phân vùng khác nhau

Giả sử:

- `orders` có 500 triệu hàng, partition theo `customer_id`.
- `order_items` có 2 tỷ hàng, partition theo `order_id`.
- Truy vấn join theo `order_id` để tính doanh thu theo sản phẩm.

Do hai bảng partition theo key khác nhau, các hàng cùng `order_id` có thể nằm trên node khác nhau. Engine có thể phải repartition/shuffle một hoặc cả hai phía theo `order_id`.

Truy vấn:

```sql
SELECT i.product_id, SUM(i.quantity * i.unit_price) AS revenue
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-11-01 00:00:00'
GROUP BY i.product_id;
```

Các bước phân tích:

1. Xem predicate ngày có prune partition/file của `orders` không.
2. Xem `orders` có chỉ đọc `order_id` và các cột thực sự cần không.
3. Xem filter ngày có được áp dụng trước khi repartition không.
4. Xem `order_items` có index/partition/file layout hỗ trợ tập order ID đã lọc không.
5. Đọc plan để biết engine broadcast, shuffle hay gather.
6. Đo bytes shuffle, worker skew, spill và output rows.
7. Đánh giá phương án colocate hai bảng theo `order_id` hoặc duy trì read model phù hợp nếu workload join này rất phổ biến.

Nếu chỉ một tháng trong nhiều năm được chọn, lọc sớm có thể giảm lượng `orders` phải shuffle. Tuy nhiên, nếu `order_items` không thể lọc tương ứng và vẫn phải shuffle hàng tỷ bản ghi, cần xem semi-join reduction hoặc thay đổi partitioning. Chọn lại partition key có thể cải thiện join này nhưng làm truy vấn theo customer đắt hơn; phải đánh giá workload tổng thể.

## 16. Ví dụ: giao dịch chuyển tiền qua hai shard

Giả sử tài khoản A và B nằm ở hai shard khác nhau. Nghiệp vụ yêu cầu trừ số dư A và cộng số dư B trong cùng một giao dịch atomic.

Một mô hình 2PC có thể thực hiện:

1. Định tuyến tài khoản đến đúng shard.
2. Bắt đầu transaction tại hai participant.
3. Kiểm tra số dư và cập nhật cả hai phía.
4. Coordinator yêu cầu hai participant prepare.
5. Sau khi nhận đủ YES, coordinator ghi quyết định commit và gửi commit.
6. Hai participant hoàn tất và giải phóng lock.

Tối ưu đường xử lý:

- Định tuyến bằng account ID thay vì broadcast tìm tài khoản.
- Đọc và xác thực thông tin cần thiết với số round trip ít nhất có thể.
- Dùng cập nhật có điều kiện để bảo vệ invariant số dư, nhưng bảo đảm semantics transaction đúng.
- Giữ transaction không chứa gọi API bên ngoài hoặc thao tác chờ lâu.
- Dùng idempotency key để xử lý client timeout và retry.
- Theo dõi thời gian prepare/commit, lock wait và trạng thái in-doubt.

Nếu nghiệp vụ có thể chấp nhận trạng thái chuyển tiền đang xử lý và compensation, saga có thể là một phương án kiến trúc khác. Nhưng saga không tạo atomicity tức thời giống 2PC và cần thiết kế sổ cái, trạng thái trung gian cùng compensation chính xác.

## 17. Các chiến lược kiến trúc để giảm chi phí phân tán

### 17.1. Data locality trước khi tăng phần cứng

Đặt dữ liệu thường được truy cập cùng nhau trên cùng shard có thể loại bỏ nhiều round trip và shuffle. Trước khi tăng network bandwidth hoặc số node, hãy xem có thể cải thiện locality bằng partition key, colocation hoặc routing hay không.

### 17.2. Tách OLTP và workload phân tích

Truy vấn báo cáo toàn hệ thống có thể fan-out qua nhiều shard và cạnh tranh tài nguyên với transaction ngắn. Có thể dùng read replica, CDC pipeline, warehouse hoặc materialized read model để chuyển tải phân tích sang hệ thống phù hợp. Đổi lại, dữ liệu có thể trễ so với nguồn và pipeline cần giám sát lag, completeness và recovery.

### 17.3. Denormalize có chủ đích

Lưu các thuộc tính dimension hoặc aggregate thường dùng cạnh dữ liệu fact có thể giảm distributed join. Cần xác định nguồn sự thật, cơ chế cập nhật, xử lý late events và cách sửa dữ liệu sai. Denormalization làm tăng write amplification và consistency work.

### 17.4. Giảm số lần gọi dịch vụ trong transaction

Đưa network calls, email, file upload hoặc thao tác người dùng ra ngoài transaction DB nếu có thể. Mẫu transactional outbox có thể ghi sự kiện cùng transaction local rồi publish bất đồng bộ; consumer cần idempotency và theo dõi delivery. Outbox không làm một transaction xuyên nhiều database trở thành atomic, nhưng giúp đồng bộ thay đổi local với việc phát sự kiện theo mô hình đáng tin cậy hơn.

### 17.5. Giới hạn fan-out

Một request fan-out đến tất cả shard có chi phí tăng theo số node và tail latency. Có thể dùng routing key, partition pruning, pre-aggregation, caching phù hợp hoặc read model. Nếu kết quả bắt buộc bao phủ mọi shard, cần đặt timeout, concurrency limit và backpressure để không tạo tải dây chuyền.

## 18. Những sai lầm thường gặp

- **Coi distributed transaction chỉ là nhiều câu SQL:** bỏ qua prepare/commit, log, coordination và recovery.
- **Cho rằng timeout nghĩa là transaction đã abort:** kết quả commit có thể chưa rõ hoặc phản hồi đã mất.
- **Retry thao tác không idempotent:** có thể tạo giao dịch hoặc bản ghi trùng.
- **Giữ transaction trong lúc gọi API ngoài:** làm lock và participant resource bị giữ lâu.
- **Tăng số participant không kiểm soát:** làm tăng coordination và khả năng gặp node chậm.
- **Nhầm saga với 2PC:** saga có trạng thái trung gian và compensation, không có atomic rollback vật lý xuyên service.
- **Cho rằng hai bảng cùng tên khóa là colocated:** cần partitioning function/map tương thích.
- **Broadcast bảng lớn:** có thể gây network amplification và memory pressure trên mọi worker.
- **Shuffle toàn bộ dữ liệu trước khi lọc:** làm tăng bytes truyền và spill.
- **Bỏ qua data skew:** một worker nóng có thể quyết định latency toàn stage.
- **Gather mọi dữ liệu về coordinator:** có thể tạo bottleneck và mất khả năng song song.
- **Đổi partition key chỉ tối ưu một join:** có thể làm các truy vấn và transaction khác tốn kém hơn.
- **Giảm isolation để tăng tốc mà không kiểm tra nghiệp vụ:** có thể làm sai invariant và tính nhất quán.
- **Chỉ xem average latency:** bỏ qua p95/p99 và participant chậm nhất.
- **Chỉ xem SQL plan cục bộ:** không thấy exchange, network bytes, participant wait hoặc recovery.

## 19. Bài tập tự kiểm tra

### Bài tập 1: Tính chi phí RTT

Một distributed transaction cần ba lượt trao đổi tuần tự giữa coordinator và participant. RTT trung bình là 25 ms. Chưa tính xử lý và ghi log.

**Câu hỏi:** phần thời gian mạng tối thiểu theo mô hình đơn giản là bao nhiêu? Nếu ba participant được gọi song song trong cùng một pha, có thể cộng RTT của cả ba không?

**Gợi ý trả lời:** ba lượt nối tiếp tương ứng khoảng 75 ms thời gian chờ mạng. Nếu ba participant được gọi song song, không cộng RTT của từng participant như chạy tuần tự; thời gian pha thường chịu ảnh hưởng bởi phản hồi chậm nhất, cộng xử lý/queue. Cần xem giao thức và topology thực tế.

### Bài tập 2: Transaction in-doubt

Hai participant đã trả lời YES cho prepare. Coordinator bị mất kết nối trước khi gửi quyết định cuối cùng.

**Câu hỏi:** client có thể kết luận transaction đã abort và gửi lại ngay không?

**Gợi ý trả lời:** không. Transaction có thể in-doubt; participant có thể giữ resource chờ recovery. Cần truy vấn trạng thái theo giao thức/nền tảng và dùng idempotency key để tránh thực hiện lặp.

### Bài tập 3: Chọn chiến lược join

Một fact table rất lớn join với dimension table chỉ còn 2 MB sau khi filter. Engine có thể broadcast dimension đến 40 worker.

**Câu hỏi:** vì sao broadcast có thể hợp lý và cần kiểm tra gì?

**Gợi ý trả lời:** truyền một tập nhỏ đến worker có thể rẻ hơn shuffle fact lớn. Cần xem kích thước sau serialization, số worker, memory mỗi worker, số query đồng thời và plan thực tế. Nếu dimension lớn hơn dự kiến hoặc broadcast lặp nhiều, chi phí có thể cao.

### Bài tập 4: Colocation

`orders` partition theo `customer_id`, còn `order_items` partition theo `order_id`. Truy vấn thường xuyên join hai bảng theo `order_id`.

**Câu hỏi:** vì sao có thể cần shuffle và phương án nào cần đánh giá?

**Gợi ý trả lời:** cùng order ID không bảo đảm hai hàng nằm cùng shard vì partition key khác nhau. Có thể repartition theo order_id, thay đổi colocation cho bảng liên quan hoặc tạo read model. Phải đánh giá thêm truy vấn theo customer và phân bố dữ liệu.

### Bài tập 5: Data skew

Một distributed join có 64 worker. 63 worker hoàn tất trong 10 giây, một worker mất 90 giây và spill dữ liệu lớn.

**Câu hỏi:** cần điều tra gì?

**Gợi ý trả lời:** kiểm tra key distribution, hot keys, input rows/bytes theo task, partition size, hash distribution và statistics. Thử skew handling, salting có kiểm soát, broadcast hoặc tách hot key. Kiểm chứng multiplicity để không nhân đôi kết quả.

### Bài tập 6: Pooling và transaction dài

Một ứng dụng dùng 200 connection pool slots nhưng nhiều transaction giữ connection trong khi gọi HTTP service 2 giây. Pool acquisition p99 tăng cao.

**Câu hỏi:** tăng pool lên 500 có giải quyết gốc rễ không?

**Gợi ý trả lời:** chưa chắc; nguyên nhân là connection và transaction bị giữ lâu ngoài thời gian DB cần thiết. Cần rút ngắn transaction, đưa lời gọi HTTP ra ngoài vùng giữ lock, kiểm tra outbox/saga nếu phù hợp và đo lại pool hold time cùng DB contention.

### Checklist tối ưu giao dịch và phép nối phân tán

- [ ] Đã phân biệt distributed transaction với distributed join và xác định có cả hai hay không.
- [ ] Đã xác định coordinator, participant, shard/region và transaction protocol.
- [ ] Đã đo RTT, số round trip nối tiếp, bytes truyền và thời gian ghi log.
- [ ] Đã đo participant count, prepare/commit duration và latency từng node.
- [ ] Đã theo dõi lock duration, blocking, deadlock và in-doubt transaction.
- [ ] Đã xác định retry semantics, idempotency và quy trình recovery.
- [ ] Đã xem join plan: colocated, broadcast, shuffle/repartition hay gather.
- [ ] Đã lọc sớm và chỉ truyền cột cần thiết trước network exchange.
- [ ] Đã đo shuffle bytes, worker skew, memory peak và spill.
- [ ] Đã đánh giá partition key, colocation, tenant skew và hotspot.
- [ ] Đã xem consistency/isolation và tính đúng đắn trước khi giảm coordination.
- [ ] Đã đánh giá read model, denormalization, outbox hoặc saga theo yêu cầu nghiệp vụ.
- [ ] Đã so sánh p50/p95/p99, throughput, lỗi và tài nguyên trước/sau.
- [ ] Đã kiểm thử failover, timeout, retry và phục hồi trong môi trường phù hợp.

Giao dịch phân tán trả chi phí cho coordination, round trip, ghi log và thời gian giữ resource; phép nối phân tán trả chi phí cho data movement, shuffle, network và xử lý skew. Giảm chi phí bằng cách đưa dữ liệu liên quan về cùng nơi, giảm participant, lọc và chiếu cột trước exchange, giữ transaction ngắn và kiểm soát retry. Mọi thay đổi phải giữ đúng semantics về atomicity, isolation, NULL, duplicate và nghiệp vụ; hãy xác nhận bằng distributed execution plan, participant metrics, network bytes, lock waits, p95/p99 và thử nghiệm lỗi trước khi triển khai.
