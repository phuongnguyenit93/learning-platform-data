# Thiết kế chủ đề, partition và khóa phân vùng

## 1. Vì sao topic, partition và key là quyết định kiến trúc?

Trong kiến trúc hướng sự kiện, producer phát ra sự kiện để các consumer xử lý độc lập theo nhu cầu nghiệp vụ. Message broker hoặc event streaming platform tiếp nhận, lưu giữ và phân phối sự kiện. Khi lưu lượng tăng, một topic thường được chia thành nhiều **partition** để xử lý song song, phân tải và lưu trữ dữ liệu theo từng luồng. Nhưng partition không chỉ là thông số hiệu năng: nó ảnh hưởng tới thứ tự sự kiện, khả năng mở rộng, tính sẵn sàng, phân bố dữ liệu và cách consumer phục hồi sau lỗi.

**Partition key** quyết định sự kiện nào được đưa vào partition nào. Nếu chọn key không phù hợp, tất cả sự kiện có thể dồn vào một partition (*hot partition*), hoặc các sự kiện liên quan đến cùng một thực thể bị phân tán khiến việc bảo toàn thứ tự và xử lý trạng thái trở nên khó khăn. Nếu chọn số partition quá lớn hoặc thay đổi số partition mà không tính đến thuật toán ánh xạ key, nhóm có thể trả chi phí vận hành và đối mặt với thay đổi thứ tự khi replay.

Trong module **CLOUD_ARCHITECTURE**, thiết kế event topic, partition và key cần xuất phát từ yêu cầu nghiệp vụ, sau đó mới đánh đổi giữa throughput, ordering, độ tin cậy, bảo mật, chi phí và vận hành theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt event, topic, partition, offset, producer, consumer và consumer group.
- Thiết kế topic theo miền nghiệp vụ, vòng đời dữ liệu và ranh giới quyền sở hữu.
- Chọn partition key dựa trên quan hệ nghiệp vụ, thứ tự cần bảo toàn và phân bố tải.
- Ước lượng số partition, throughput và số consumer có ích.
- Nhận diện hot key, skew, rebalance, duplicate delivery và các thay đổi ảnh hưởng ordering.
- Xây dựng chính sách schema, retention, retry, monitoring và bảo mật cho event stream.

## 2. Những khái niệm cơ bản

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Event** | Sự kiện mô tả điều đã xảy ra, thường bất biến sau khi công bố | OrderPlaced, PaymentCaptured |
| **Topic** | Tên logic của luồng sự kiện cùng mục đích hoặc hợp đồng | orders.placed.v1 |
| **Partition** | Phân đoạn của topic, chứa một chuỗi record có thứ tự riêng | Partition 0, 1, 2 |
| **Record / message** | Đơn vị dữ liệu được ghi vào partition, thường gồm key, value, headers và timestamp | Key order-123, payload OrderPlaced |
| **Offset** | Vị trí của record trong một partition | Offset 1042 của partition 1 |
| **Producer** | Thành phần ghi event vào topic | Order service |
| **Consumer** | Thành phần đọc và xử lý event | Inventory projection |
| **Consumer group** | Nhóm consumer phối hợp phân chia partition để đọc song song | inventory-projection |
| **Partition key** | Giá trị dùng để định tuyến record tới partition | orderId, customerId, accountId |
| **Retention** | Chính sách giữ record theo thời gian hoặc dung lượng | Giữ event 7 ngày |

Topic là ranh giới tên và hợp đồng logic; partition là đơn vị song song và thứ tự bên trong topic. Trong Kafka, mỗi partition là một log được sắp xếp theo offset tăng dần. **Thứ tự được bảo đảm trong một partition**, chứ không có một thứ tự toàn cục giữa mọi partition của topic.

~~~mermaid
flowchart TB
    Producer["Producer: Order service"] --> Topic["Topic: orders.placed"]
    subgraph T["Topic gồm nhiều partition"]
        P0["Partition 0: offset 0,1,2,..."]
        P1["Partition 1: offset 0,1,2,..."]
        P2["Partition 2: offset 0,1,2,..."]
    end
    Topic --> P0
    Topic --> P1
    Topic --> P2
    subgraph G["Consumer group: inventory-projection"]
        C0["Consumer A"]
        C1["Consumer B"]
        C2["Consumer C"]
    end
    P0 --> C0
    P1 --> C1
    P2 --> C2
~~~

Sơ đồ minh họa consumer group có ba consumer và ba partition. Broker có thể phân phối partition khác đi khi số consumer thay đổi hoặc xảy ra rebalance. Hai consumer trong cùng group truyền thống không đồng thời sở hữu cùng một partition; các group khác nhau có thể đọc cùng topic độc lập.

## 3. Thiết kế topic theo hợp đồng nghiệp vụ

Topic nên phản ánh một luồng sự kiện có ý nghĩa và một hợp đồng mà producer/consumer cùng hiểu. Không nên tạo topic chỉ theo từng bảng database, endpoint hoặc tên đội nếu điều đó không biểu đạt ngữ nghĩa sự kiện.

### 3.1. Chọn ranh giới topic

- **Theo sự kiện nghiệp vụ:** orders.placed, payments.captured, inventory.reserved.
- **Theo miền sở hữu:** đội Order sở hữu event về vòng đời đơn; đội Payment sở hữu event về giao dịch thanh toán.
- **Theo nhu cầu tiêu thụ và retention:** event audit, event tích hợp, event cập nhật projection có thể có chính sách khác nhau.
- **Theo mức độ tin cậy hoặc dữ liệu:** event chứa dữ liệu nhạy cảm có thể cần topic và quyền truy cập riêng.

Tránh topic chung chung như events hoặc messages nếu chúng gom quá nhiều hợp đồng khác nhau. Consumer có thể phải đọc, lọc và bỏ phần lớn dữ liệu; quyền truy cập cũng khó cấp theo nguyên tắc tối thiểu.

### 3.2. Topic không đồng nghĩa với event type

Một topic có thể chứa một loại event hoặc nhiều loại có cùng hợp đồng và yêu cầu vận hành. Nếu gom nhiều event type, mỗi record cần có trường type/version rõ ràng và schema registry/validation tương ứng.

| Một topic cho mỗi event type | Nhiều event type trong một topic |
| --- | --- |
| Dễ quản lý schema, ACL, retention và routing riêng | Ít topic và metadata hơn, thuận lợi cho luồng cùng ownership |
| Tăng số topic, partition và cấu hình | Consumer phải phân biệt type; policy có thể khó tách |
| Phù hợp event có lifecycle/criticality khác nhau | Phù hợp event có contract và vận hành tương đồng |

Không có số topic tối ưu cho mọi hệ thống. Hãy định nghĩa owner, schema, retention, key, consumer, quyền truy cập và quy trình thay đổi cho từng topic.

### 3.3. Tên topic và versioning

Tên topic nên nhất quán, mô tả miền và hành động, tránh lẫn tên môi trường nếu nền tảng đã tách cluster/namespace bằng cấu hình. Ví dụ:

~~~text
orders.placed.v1
orders.cancelled.v1
payments.captured.v1
inventory.reserved.v1
~~~

Version trong tên topic chỉ là một chiến lược. Một số hệ thống quản lý version ở schema registry hoặc header. Khi hợp đồng thay đổi:

- Thêm field optional có default có thể tương thích ngược nếu consumer hỗ trợ.
- Thay đổi phá vỡ tương thích như đổi semantics, xóa field bắt buộc hoặc đổi encoding có thể cần topic/version mới và giai đoạn migration.
- Không thay ý nghĩa event cũ nhưng giữ nguyên tên/schema version; consumer cũ có thể diễn giải sai.
- Định nghĩa thời gian hỗ trợ đồng thời producer/consumer cũ, cutover, replay và ngày ngừng topic cũ.

## 4. Partition: song song hóa có giới hạn

Partition chia topic thành nhiều log độc lập. Trong Kafka, mỗi partition có leader phục vụ đọc/ghi và có thể có replica trên broker khác để tăng khả năng chịu lỗi theo cấu hình replication. Consumer group dùng partition làm đơn vị phân công, nên số partition giới hạn mức song song tối đa của group đối với topic đó.

### 4.1. Partition ảnh hưởng điều gì?

1. **Throughput:** nhiều partition cho phép producer/consumer phân tán hoạt động trên nhiều broker và worker nếu workload và broker capacity phù hợp.
2. **Ordering:** thứ tự chỉ được bảo đảm trong từng partition. Các event liên quan cần cùng key để được định tuyến nhất quán.
3. **Consumer parallelism:** consumer group truyền thống không thể có nhiều consumer độc lập cùng đọc một partition để tăng throughput; consumer dư có thể idle.
4. **Storage và replication:** mỗi partition tạo metadata, log segment, file handle, leader/replica và công việc recovery.
5. **Rebalance:** thay đổi membership hoặc assignment có thể làm partition chuyển owner và tạm dừng tiêu thụ.
6. **Retention và recovery:** số partition ảnh hưởng phân bố disk, thời gian phục hồi replica và hiệu quả quản trị.

Nhiều partition hơn không tự làm một partition đơn lẻ ghi nhanh hơn. Nếu mọi event cùng key bị dồn vào một partition thì partition đó vẫn là giới hạn.

### 4.2. Số consumer hiệu dụng

Với một topic có P partition và một consumer group truyền thống có C consumer, số consumer có thể trực tiếp xử lý partition song song tối đa là:

$$
C_active = min(P, C)
$$

Nếu có 3 partition và 8 consumer trong cùng group, tối đa 3 consumer được gán partition; 5 consumer còn lại không xử lý dữ liệu topic đó. Nếu có 12 partition và 3 consumer, mỗi consumer có thể nhận nhiều partition.

Hạn mức này chỉ mô tả phân công partition; throughput thực tế còn phụ thuộc tốc độ xử lý mỗi record, batch, network, disk, broker, số topic và dependency phía sau.

### 4.3. Partition và replication factor là hai quyết định khác nhau

- **Partition count** quyết định số log độc lập, khả năng phân tải và parallelism.
- **Replication factor** xác định số bản sao của mỗi partition trên các broker.
- **min.insync.replicas** và producer acknowledgment policy ảnh hưởng mức bảo đảm ghi khi broker lỗi.

Tăng partition không tự tăng khả năng chịu mất broker; tăng replication factor cũng không tự tăng consumer parallelism. Cần chọn riêng theo throughput, durability, availability và chi phí.

## 5. Chọn partition key theo ngữ nghĩa nghiệp vụ

Partition key thường là lựa chọn quan trọng nhất để giữ các event liên quan ở cùng partition. Với Kafka, producer dùng partitioner để ánh xạ key sang partition; mặc định phổ biến là hash key và modulo số partition, nhưng thuật toán cụ thể phụ thuộc client/partitioner và cấu hình.

### 5.1. Chọn key cho thứ tự cần bảo toàn

Hãy hỏi: **Những sự kiện nào cần được xử lý theo thứ tự tương đối?**

| Luồng nghiệp vụ | Thứ tự cần bảo toàn | Key ứng viên |
| --- | --- | --- |
| Trạng thái một đơn hàng | Đặt → thanh toán → hủy/hoàn tiền theo order | orderId |
| Số dư một tài khoản | Debit/credit của cùng account | accountId |
| Trạng thái một thiết bị IoT | Reading/command của thiết bị | deviceId |
| Trạng thái một khách hàng | Cập nhật profile cùng customer | customerId |
| Tồn kho theo SKU/kho | Điều chỉnh cùng đơn vị tồn kho | warehouseId + sku |

Nếu key là orderId, mọi event cho cùng đơn hàng thường vào cùng partition khi partition count và partitioner không đổi. Điều đó cho phép consumer xử lý tuần tự theo partition đối với event của order đó. Các order khác được phân tán.

### 5.2. Key không nhất thiết là primary key của database

Primary key xác định record trong database; partition key xác định **đơn vị cần giữ gần nhau và thứ tự xử lý** trong stream. Hai giá trị có thể giống nhau nhưng không bắt buộc.

Ví dụ orderId phù hợp để giữ vòng đời đơn hàng cùng nhau; consumer tổng hợp hạn mức theo customerId lại cần xử lý các order của một khách theo cùng partition nếu logic yêu cầu thứ tự theo khách. Có thể cần một stream/projection khác với key riêng, hoặc thiết kế consumer xử lý concurrency và versioning rõ ràng.

### 5.3. Key rỗng hoặc null

Nếu producer không gửi key, partitioner có thể phân phối record theo round-robin, sticky partitioning hoặc cơ chế khác tùy client/version. Cách này có thể cải thiện cân bằng tải nhưng không giữ thứ tự theo thực thể. Không nên để key null khi nghiệp vụ cần tuần tự hóa thay đổi cùng entity.

Key phải ổn định và có canonical representation. Tránh dùng object serialization không ổn định, timestamp riêng lẻ hoặc giá trị thay đổi qua các event của cùng entity. Nếu key chứa thông tin cá nhân, cân nhắc ID nội bộ hoặc token hóa để tránh lộ dữ liệu trong log/monitoring.

## 6. Phân bố key và hiện tượng hot partition

### 6.1. Cardinality và độ lệch tải

Partition key có **cardinality** là số lượng giá trị khác nhau có thể xuất hiện. Cardinality cao thường tạo khả năng phân tán tốt hơn, nhưng không bảo đảm phân bố đều. Nếu một key xuất hiện với tần suất vượt trội, partition nhận key đó sẽ chịu tải lớn hơn.

Ví dụ:

- eventType chỉ có 4 giá trị nhưng một type chiếm 90% event: dễ dồn tải vào một partition hoặc một nhóm partition nhỏ.
- countryCode có ít giá trị; nếu một quốc gia chiếm phần lớn traffic, partition tương ứng có thể nóng.
- customerId có nhiều giá trị nhưng một khách hàng lớn phát hàng triệu event: một key vẫn có thể thành hot key.
- orderId có cardinality cao và traffic thường phân tán; một order burst vẫn có thể tạo hot key ngắn hạn.

### 6.2. Ví dụ phân bố tải minh họa

Giả sử topic có 8 partition và 100.000 event/giây:

| Cách chọn key | Phân bố giả định | Hệ quả |
| --- | --- | --- |
| Không key, sticky/round-robin | Gần 12.500 event/s mỗi partition trong tình huống lý tưởng | Cân bằng hơn nhưng không giữ thứ tự theo entity |
| eventType với một type chiếm 80% | Một số ít partition nhận phần lớn dữ liệu | Hot partition, consumer không tăng parallelism cho key đó |
| orderId có nhiều giá trị | Lưu lượng trải trên nhiều partition nếu hash và tải đủ đều | Giữ thứ tự theo đơn hàng |
| customerId với một khách rất lớn | Partition của khách đó có thể nhận tỷ lệ áp đảo | Cần xử lý hot key nếu logic cho phép phân rã |

Các con số chỉ minh họa; hash partitioning không bảo đảm mỗi key ở một partition riêng, và phân bố thực tế phải đo trên dữ liệu key của hệ thống.

### 6.3. Phát hiện hot partition

- Theo dõi bytes in/out, record rate và request latency theo từng partition/broker.
- So sánh consumer lag theo partition; một partition tăng lag liên tục trong khi partition khác rảnh là tín hiệu skew.
- Phân tích tần suất key ở mức mẫu hoặc telemetry an toàn; tránh log toàn bộ key nhạy cảm.
- Đo phân vị tải của key, không chỉ cardinality trung bình.
- Liên hệ tải partition với broker leader, disk, network và consumer processing time.

### 6.4. Giảm hot key mà không phá thứ tự

1. **Chọn key đúng hơn:** thay eventType hoặc tenant chung bằng entity key có phân bố phù hợp, nếu thứ tự nghiệp vụ cho phép.
2. **Tách topic theo miền tải:** cô lập luồng có traffic khác biệt hoặc policy riêng.
3. **Phân mảnh logic (key salting):** thêm shard suffix để chia tải, nhưng chỉ khi không cần total ordering cho toàn key và có bước tổng hợp đúng.
4. **Tách luồng cập nhật:** event có thể gộp/batch hoặc chuyển sang compacted state stream nếu phù hợp.
5. **Tối ưu consumer:** batch, xử lý I/O hiệu quả, giảm thao tác đồng bộ và tăng capacity downstream.

Không nên đơn giản thêm partition rồi kỳ vọng key nóng tự phân tán. Một key duy nhất vẫn ánh xạ tới một partition trong một topic nếu semantics key không đổi.

## 7. Ordering: bảo toàn thứ tự ở phạm vi nào?

Kafka bảo đảm record trong cùng partition được đọc theo thứ tự offset. Broker append record vào log và consumer đọc theo thứ tự đó. Tuy nhiên, **không có thứ tự toàn cục giữa partition 0 và partition 1**. Consumer group khác nhau cũng có tốc độ và vị trí offset độc lập.

~~~mermaid
flowchart TB
    subgraph P0["Partition 0"]
        A1["Order A: placed"]
        A2["Order A: paid"]
        A3["Order A: shipped"]
        A1 --> A2 --> A3
    end
    subgraph P1["Partition 1"]
        B1["Order B: placed"]
        B2["Order B: cancelled"]
        B1 --> B2
    end
    P0 -. "Không có global ordering với P1" .- P1
~~~

Nếu event của order A và order B nằm ở các partition khác nhau, consumer có thể nhận event B trước khi xử lý xong event A. Đây không phải lỗi broker; đó là kết quả của xử lý song song.

### 7.1. Ordering không thay thế version và idempotency

Ngay cả khi cùng entity dùng một key, consumer vẫn cần xử lý:

- **Duplicate delivery:** event có thể được xử lý lại khi offset chưa commit hoặc sau lỗi.
- **Out-of-order từ producer:** upstream có thể phát event sai trình tự nghiệp vụ; broker không sửa lại.
- **Replay/backfill:** consumer mới có thể đọc lịch sử và tương tác với trạng thái hiện tại.
- **Concurrent producers:** hai producer ghi cùng key có thể không tạo thứ tự nghiệp vụ mong muốn nếu không có coordination.
- **Retry topic:** retry qua topic khác có thể khiến event sau được xử lý trước event đang chờ retry.

Nên dùng aggregateVersion, sequence number hoặc event time nghiệp vụ khi cần phát hiện stale/out-of-order update. Idempotency key/eventId giúp consumer loại tác dụng phụ trùng; offset commit phải phù hợp với việc ghi dữ liệu.

### 7.2. Producer idempotence và transactions

Kafka producer idempotence giúp hạn chế duplicate do retry ở tầng producer trong phạm vi semantics được hỗ trợ; nó không tự làm consumer xử lý exactly-once trên database bên ngoài. Kafka transactions có thể phối hợp đọc/ghi Kafka topic và commit offset trong một transaction Kafka theo mô hình phù hợp, nhưng không tự bao trùm transaction PostgreSQL hay payment API.

Nếu consumer ghi database rồi commit offset, crash giữa hai thao tác có thể khiến record được giao lại. Cần idempotent database write, inbox/dedup table hoặc cơ chế phối hợp phù hợp. Không quảng bá exactly-once nếu chỉ bật một cấu hình producer.

## 8. Thay đổi partition count và tác động tới key mapping

Trong partitioner dựa trên hash modulo số partition, partition thường được tính khái niệm như:

$$
partition = hash(key) mod P
$$

Khi P thay đổi, cùng key có thể được ánh xạ sang partition khác. Do đó event mới của một entity có thể được ghi vào partition mới trong khi event cũ còn ở partition cũ. Nếu consumer đọc song song, **thứ tự toàn entity có thể bị phá vỡ trong giai đoạn chuyển đổi**.

Không phải mọi client và partitioner đều dùng đúng công thức modulo; sticky partitioning, custom partitioner và consistent hashing có thể khác. Nhưng **partition topology là một phần của semantics định tuyến**, nên thay đổi partition count cần kế hoạch.

### 8.1. Khi nào tăng partition?

- Throughput cần cao hơn và broker có capacity.
- Consumer group cần thêm parallelism và logic có thể chia theo key.
- Dữ liệu tăng, partition hiện tại đã đạt giới hạn lưu trữ/throughput hợp lý.
- Có kế hoạch chuyển đổi để đảm bảo ordering và key mapping.

### 8.2. Phương án thay đổi an toàn

- **Tạo topic version mới:** chuyển producer sang topic mới với số partition mới; dùng cutover/drain/replay có kiểm soát.
- **Giữ partition count ổn định:** chọn dư địa capacity ban đầu hợp lý thay vì thay đổi thường xuyên.
- **Routing theo epoch/shard map:** với hệ thống đặc thù, quản lý mapping key→partition riêng và version hóa; cần kiểm thử tính đúng đắn.
- **Dual-publish và reconcile:** có thể ghi sang hai topic trong giai đoạn chuyển đổi, nhưng consumer phải chống duplicate và xác định thứ tự cắt.

Không xóa hoặc tạo lại topic chỉ để reset partition mà không có kế hoạch retention, replay, ACL, consumer offset và khôi phục dữ liệu.

## 9. Compaction, retention và key

Topic có cleanup policy **delete** giữ record theo thời gian/dung lượng rồi xóa log segment cũ khi đủ điều kiện. Topic **compacted** giữ lại record mới nhất theo key trong quá trình compaction, phù hợp một số luồng trạng thái. Nhiều cấu hình hỗ trợ kết hợp delete và compact với semantics riêng.

| Loại topic | Dùng cho | Vai trò của key |
| --- | --- | --- |
| Event history, retention theo thời gian | Lịch sử sự kiện, audit hoặc tích hợp | Giữ thứ tự theo entity và grouping |
| Compacted state topic | Bản trạng thái hiện tại theo entity | Xác định record nào được giữ lại sau compaction |
| Retry / DLQ topic | Event xử lý lỗi hoặc cần điều tra | Giữ tương quan; cần metadata retry |

Tombstone (record có key và value null trong compacted topic) thường biểu thị xóa key khi compaction; nó không phải thông điệp xóa ngay lập tức và không thay thế retention/backup. Consumer cần hiểu tombstone và thời hạn lưu tombstone theo cấu hình.

Retention cần xét yêu cầu replay, audit, privacy/deletion, chi phí disk, replication, tốc độ consumer catch-up và dung lượng broker. Event stream không tự trở thành hệ thống lưu trữ lịch sử vô hạn.

## 10. Thiết kế producer và partition key trong code

Ví dụ Java với Kafka producer: key là orderId, value là event đã serialize. Đoạn code tập trung vào routing và không đại diện cấu hình đầy đủ production.

~~~java
ProducerRecord<String, OrderPlaced> record =
    new ProducerRecord<>(
        "orders.placed.v1",
        event.orderId(),   // partition key
        event
    );

producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        // Ghi nhận lỗi gửi; xử lý retry theo chính sách,
        // không tự retry vô hạn trong callback.
        logger.error("Failed to publish OrderPlaced", exception);
        return;
    }
    logger.info(
        "Published order event to partition={}, offset={}",
        metadata.partition(),
        metadata.offset()
    );
});
~~~

Producer record gửi key string orderId; partitioner quyết định partition theo key và cấu hình. Trong production cần cấu hình bootstrap, serializer, TLS/SASL, idempotence, acks, retries, delivery timeout và error handling. Không log payload nhạy cảm.

### 10.1. Ví dụ cấu hình producer

~~~properties
bootstrap.servers=broker-1.example.internal:9093,broker-2.example.internal:9093
key.serializer=org.apache.kafka.common.serialization.StringSerializer
value.serializer=org.apache.kafka.common.serialization.ByteArraySerializer
acks=all
enable.idempotence=true
delivery.timeout.ms=120000
request.timeout.ms=30000
max.in.flight.requests.per.connection=5
~~~

Đây là cấu hình minh họa; version client và broker có defaults/compatibility khác nhau. Nếu dùng custom serializer hoặc Schema Registry, cần serializer tương ứng. acks=all và idempotence tăng độ tin cậy khi producer gửi nhưng không bảo đảm event đã được consumer ghi database.

## 11. Consumer group, assignment và rebalance

Consumer group phân chia partition giữa các member để xử lý song song. Khi member thêm, mất heartbeat, rời group hoặc partition thay đổi, broker/client có thể thực hiện rebalance.

### 11.1. Rebalance ảnh hưởng ra sao?

- Consumer có thể tạm ngừng fetch/processing trong lúc revoke và assign partition, tùy protocol/strategy.
- Nếu xử lý record quá lâu, poll/heartbeat không đúng có thể làm consumer bị xem là không hoạt động.
- Partition mới được giao có thể bắt đầu từ committed offset, nên record chưa commit được đọc lại.
- Nếu commit offset trước khi DB write thành công, record có thể bị mất khỏi góc nhìn consumer.
- Nếu commit sau DB write và crash giữa hai bước, record có thể được xử lý lặp.

### 11.2. Quản lý offset

Offset là vị trí đọc của consumer trong **từng partition**. Chỉ xác nhận tiến độ sau khi tác dụng phụ cần thiết hoàn tất hoặc có cơ chế idempotent cho lần xử lý lại.

Với xử lý batch song song trong một partition, cần commit offset cao nhất đã hoàn tất liên tục; không commit vượt qua record còn đang xử lý vì khi crash có thể bỏ qua record đó.

### 11.3. Consumer vượt số partition

Nếu topic có 6 partition nhưng group có 10 consumer, tối đa 6 consumer nhận partition; 4 consumer có thể idle. Nếu cần throughput cao hơn, tăng partition có thể là lựa chọn nhưng chỉ khi producer, broker, downstream và key distribution hỗ trợ. Đôi khi tối ưu batch, query, compression hoặc xử lý consumer hiệu quả hơn tăng partition.

## 12. Ước lượng số partition và throughput

Không có công thức sizing duy nhất phù hợp mọi broker. Có thể dùng mô hình sơ bộ:

- R: tổng tốc độ record cần xử lý (record/giây),
- r: throughput bền vững đo được của một partition trong điều kiện thử tải,
- P: số partition.

Ước lượng:

$$
P >= ceil(R / r)
$$

Ví dụ tải mục tiêu 24.000 record/giây và thử tải đo được một partition xử lý ổn định 3.000 record/giây:

$$
P >= ceil(24000 / 3000) = 8
$$

Con số 8 là **điểm bắt đầu lý thuyết**, chưa tính headroom, replication, skew, kích thước record, network, disk, consumer downstream, rebalance và yêu cầu phục hồi. Nếu một key nóng chiếm 40% tải, tăng từ 8 lên 16 partition có thể vẫn không giúp partition chứa key đó.

### 12.1. Sizing theo consumer throughput

Nếu một consumer xử lý bền vững q record/giây và cần tổng R, số consumer cần thiết xấp xỉ:

$$
C >= ceil(R / q)
$$

Vì mỗi consumer group cần partition riêng để song song, số partition phải đủ lớn để gán cho các consumer này. Nhưng quá nhiều partition làm tăng chi phí broker, memory, file handle, metadata, recovery và rebalance.

### 12.2. Kích thước message

Throughput record/giây không phản ánh đủ khi kích thước record khác nhau. Cần đo bytes/giây, compression ratio, batch size, maximum message size, request size và network bandwidth. Một topic 10.000 event/giây cỡ 1 KB khác xa topic 10.000 event/giây cỡ 1 MB.

## 13. Bảo mật và phân quyền theo topic

Topic là ranh giới ACL và quản trị hữu ích. Không nên để mọi producer/consumer có quyền đọc/ghi mọi topic.

- **Producer ACL:** chỉ service owner được ghi vào topic do họ sở hữu.
- **Consumer ACL:** chỉ nhóm cần dữ liệu được đọc; tránh cấp wildcard nếu không có lý do.
- **Consumer group ACL:** kiểm soát quyền sử dụng group ID khi broker hỗ trợ.
- **Schema governance:** giới hạn ai có thể đăng ký schema, tương thích và xóa version.
- **Encryption in transit:** TLS giữa producer, broker và consumer; certificate/credential rotation.
- **Encryption at rest:** mã hóa storage và backup theo policy cloud/broker.
- **Sensitive key:** tránh đặt email, số điện thoại hoặc dữ liệu cá nhân trực tiếp làm key nếu có thể xuất hiện trong log/metric.
- **Data minimization:** event chỉ chứa field cần thiết; cân nhắc retention, quyền xóa và masking.

Nếu key là customerId, có thể dùng ID nội bộ hoặc token ổn định thay vì email/phone. Nhưng nếu cần partition cùng một customer, token phải ổn định theo cùng thuật toán/secret version; rotation cần kế hoạch để không làm cùng entity chuyển partition bất ngờ.

## 14. Vận hành và giám sát topic/partition

Theo dõi broker, topic, partition, producer, consumer và downstream. Dashboard chỉ có tổng throughput có thể che giấu partition nóng hoặc consumer group bị lag.

| Lớp | Chỉ số / tín hiệu |
| --- | --- |
| Topic | Partition count, retention, replication factor, bytes/records in/out |
| Partition | Leader distribution, replica ISR, size, traffic skew, under-replicated partitions |
| Broker | Disk utilization, network throughput, request latency, CPU, memory, request queue |
| Producer | Send latency, retry, error rate, batch size, compression, record size |
| Consumer group | Lag theo partition, processing rate, rebalance count/time, commit failures |
| Downstream | DB saturation, API rate limit, processing latency, DLQ growth |

### 14.1. Consumer lag

Consumer lag là khoảng cách giữa vị trí ghi mới nhất của partition và offset consumer đã xử lý/commit theo định nghĩa metric của công cụ. Lag tăng kéo dài có thể do consumer chậm, thiếu consumer, partition skew, downstream quá tải hoặc consumer lỗi.

Không chỉ theo dõi tổng lag. Hãy theo dõi lag lớn nhất và độ tuổi record cũ nhất theo partition; một partition nóng có thể nghẽn dù tổng lag nhìn nhỏ.

### 14.2. Leader và replica

Theo dõi leader imbalance, under-replicated partitions, offline partitions, ISR shrink và thời gian recovery. Replication factor cao cần disk/network và replication throughput cao; nếu broker thiếu capacity, tăng replication có thể làm hệ thống chậm hơn.

### 14.3. Runbook khi lag tăng

1. Xác định group, topic và partition có lag lớn nhất.
2. So sánh record/bytes in với tốc độ xử lý/commit; kiểm tra key hoặc partition skew.
3. Xem consumer error, retry, rebalance và thời gian xử lý mỗi record.
4. Kiểm tra downstream như database, API rate limit, object storage và connection pool.
5. Chỉ tăng consumer nếu còn partition và downstream capacity; nếu không, xử lý bottleneck hoặc giảm producer rate.
6. Theo dõi backlog age, lag và SLO sau thay đổi; cập nhật runbook nếu nguyên nhân lặp lại.

## 15. Reliability: retry topic, dead-letter và replay

Consumer không nên chặn cả partition vô hạn vì một record lỗi. Nhưng đẩy mọi lỗi sang DLQ ngay cũng có thể làm mất ngữ nghĩa nghiệp vụ hoặc thứ tự. Cần phân loại:

| Lỗi | Cách xử lý thường gặp |
| --- | --- |
| Lỗi tạm thời downstream | Retry có backoff, giới hạn số lần và deadline |
| Schema/payload không hợp lệ | Dead-letter, cảnh báo, metadata để điều tra |
| Vi phạm nghiệp vụ | Ghi nhận từ chối hoặc event cần review; không retry mù |
| Lỗi credential/quyền | Dừng hoặc throttle consumer, cảnh báo; tránh DLQ hàng loạt |
| Downstream quá tải | Backpressure, giảm concurrency, tạm dừng có kiểm soát |

Retry topic tạo luồng mới và có thể thay đổi thứ tự. Ví dụ OrderPlaced bị retry trong khi PaymentCaptured của cùng order đã được xử lý, trạng thái có thể sai. Các phương án gồm:

- Retry trong cùng partition bằng pause/backoff, chấp nhận block key/partition trong thời gian giới hạn.
- Dùng retry topic có metadata attempts/next retry time và consumer kiểm soát thứ tự theo entity/version.
- Tách lỗi kỹ thuật khỏi event nghiệp vụ; dùng state machine hoặc workflow bền vững.
- Dead-letter cuối cùng khi quá ngưỡng, có quy trình replay sau sửa lỗi và theo dõi idempotency.

DLQ cần giữ original topic/partition/offset, key, headers, schema version, exception class và timestamp nhưng phải loại bỏ/che payload nhạy cảm khi không cần. Reprocess phải có owner, phê duyệt và cách chống tác dụng phụ trùng.

## 16. Well-Architected: các đánh đổi cần xem xét

| Góc nhìn | Quyết định topic/partition/key | Đánh đổi |
| --- | --- | --- |
| **Operational Excellence / Vận hành** | Topic ownership, schema registry, partition plan, IaC và runbook | Quy ước tốt giảm lỗi nhưng cần governance và automation |
| **Security / Bảo mật** | ACL theo topic/group, TLS, encryption at rest, key privacy | Quyền hẹp giảm lộ dữ liệu nhưng tăng quản trị identity và rotation |
| **Reliability / Độ tin cậy** | Replication, acks, ISR, idempotency, retention và replay | Durability cao hơn tốn disk/network và latency |
| **Performance Efficiency / Hiệu quả hiệu năng** | Partition count, key distribution, batch/compression | Nhiều partition tăng parallelism nhưng tăng overhead và rebalance |
| **Cost Optimization / Tối ưu chi phí** | Sizing theo throughput, retention, replication, consumer capacity | Giữ lâu và nhân bản tăng storage/egress; quá ít partition tăng backlog |
| **Sustainability / Bền vững** | Giảm record thừa, retention đúng hạn, compression và capacity right-size | Tiết kiệm tài nguyên phải giữ headroom cho peak và recovery |

Không tối ưu riêng throughput nếu nghiệp vụ cần ordering hoặc audit. Không tối ưu riêng ordering bằng cách gom mọi event vào một partition nếu hệ thống cần mở rộng. **Key và partition phải phản ánh ranh giới tuần tự hóa nhỏ nhất mà nghiệp vụ thực sự cần.**

## 17. Bài thực hành: thiết kế event stream cho thương mại điện tử

Một nền tảng bán hàng phát ra OrderPlaced, PaymentAuthorized, OrderCancelled, InventoryReserved và ShipmentCreated. Có ba consumer group: inventory projection, customer notification và analytics. Tải đỉnh dự kiến 30.000 event/giây, nhưng một khách hàng doanh nghiệp có thể tạo 25% tổng event trong campaign. Consumer inventory phải giữ đúng thứ tự các thay đổi của cùng đơn hàng; analytics có thể xử lý trễ hơn.

**Yêu cầu bài làm:**

1. Xác định topic boundary, owner và schema/version cho các event; giải thích event nào nên ở cùng hoặc khác topic.
2. Chọn partition key cho topic vòng đời đơn hàng và giải thích tại sao orderId, customerId hoặc eventType phù hợp/không phù hợp.
3. Đề xuất số partition ban đầu từ throughput đo được hoặc giả định thử tải; nêu headroom, replication factor và giới hạn consumer.
4. Phân tích hot key do khách hàng doanh nghiệp chiếm 25% traffic; đề xuất ít nhất hai hướng giảm skew và nêu ảnh hưởng ordering.
5. Giải thích consumer group assignment cho 12 partition với 3, 12 và 16 consumer; nêu consumer nào idle.
6. Thiết kế retry, DLQ và replay cho InventoryReserved lỗi do database timeout; bảo đảm không xử lý trùng tác dụng phụ.
7. Đưa ra kế hoạch tăng partition hoặc chuyển topic version mà không làm sai thứ tự event của cùng order.
8. Đề xuất dashboard/alert cho producer latency, partition skew, under-replicated partitions và consumer lag.
9. Ghi ADR về partition key và partition count, gồm điều kiện xem xét lại khi traffic hoặc quy tắc nghiệp vụ thay đổi.

### Gợi ý đánh giá

Một thiết kế tốt cần chỉ rõ **thứ tự cần bảo toàn theo thực thể nào**, key có phân bố ra sao và mức song song mong muốn. Nếu inventory cần xử lý theo order, orderId thường là ứng viên tự nhiên cho stream vòng đời đơn; nhưng nếu hot key customer là vấn đề, không thể đổi sang key ngẫu nhiên mà vẫn kỳ vọng ordering theo order tự động. Có thể dùng stream khác, partitioning hai tầng hoặc xử lý có version/dedup phù hợp.

Số partition phải dựa vào throughput trên môi trường tương đương, không suy từ số consumer mong muốn. Nếu số partition lớn hơn consumer, có consumer idle; nếu số consumer lớn hơn partition, thêm consumer không làm tăng parallelism cho group.

## 18. Checklist trước khi đưa topic vào production

- [ ] Topic có purpose, owner, event contract và consumer được xác định.
- [ ] Partition key phản ánh entity cần ordering và có phân bố tải được đo.
- [ ] Đã đánh giá cardinality, hot key, key privacy và skew theo campaign.
- [ ] Partition count dựa trên throughput/record size thử tải, consumer parallelism và headroom.
- [ ] Replication factor, acks, min ISR và durability được chọn riêng với partition count.
- [ ] Có chính sách schema compatibility, versioning, migration và replay.
- [ ] Có retention, compaction, tombstone và quy tắc privacy/deletion phù hợp.
- [ ] Consumer group, offset commit, rebalance và idempotency được kiểm thử.
- [ ] Retry, DLQ, backoff, ordering và replay có owner/runbook.
- [ ] ACL producer/consumer/group theo least privilege; TLS và encryption at rest được cấu hình.
- [ ] Metrics có lag theo partition, throughput, latency, ISR, skew và downstream saturation.
- [ ] Thay đổi partition count có kế hoạch key remapping và ordering.
- [ ] Có load test warm/peak/burst, broker failure, consumer rebalance và downstream outage.
- [ ] Tổng chi phí broker, storage, replication, network, retention và vận hành được duyệt.

**Ghi nhớ:** Topic xác định hợp đồng của luồng sự kiện; partition xác định các log độc lập để phân tải và xử lý song song; key quyết định những sự kiện nào đi cùng nhau và có thể giữ thứ tự theo thực thể. Thiết kế tốt chọn key theo **ngữ nghĩa nghiệp vụ**, chọn partition theo **throughput và parallelism có đo đạc**, đồng thời quản lý hot key, rebalance, retry, retention và thay đổi topology như những quyết định kiến trúc có tác động lâu dài.
