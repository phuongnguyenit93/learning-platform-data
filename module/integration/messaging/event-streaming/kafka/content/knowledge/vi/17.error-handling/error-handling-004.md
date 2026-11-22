# Retry topic và tác động đến thứ tự theo key

Retry giúp consumer thử lại những record chưa xử lý được do lỗi tạm thời như database timeout, dịch vụ phụ thuộc mất kết nối hoặc giới hạn tài nguyên. Khi lỗi kéo dài, ứng dụng có thể đưa record sang retry topic để xử lý lại sau một khoảng delay thay vì giữ consumer chờ tại chỗ.

Cách làm này tăng khả năng phục hồi và cho phép main topic tiếp tục được tiêu thụ. Tuy nhiên, retry topic tạo ra một luồng xử lý riêng. Trong khi event cũ đang chờ retry, các event mới hơn của cùng key vẫn có thể được xử lý từ main topic. Vì vậy, **non-blocking retry có thể phá vỡ thứ tự theo key**, dù producer đã gửi mọi event của key đó vào cùng một partition ban đầu.

Kafka chỉ bảo đảm thứ tự trong từng partition log. Khi record được chuyển sang retry topic, nó thuộc một log khác với offset và tiến độ consumer riêng. Muốn giữ đúng thứ tự nghiệp vụ, hệ thống phải lựa chọn rõ giữa việc chặn partition để retry tại chỗ, chấp nhận event đến trễ và kiểm tra version, hoặc xây dựng cơ chế holdback theo từng entity.

## 1. Retry giải quyết vấn đề gì?

Consumer có thể gặp lỗi khi xử lý record:

- Database tạm thời không kết nối được.
- HTTP service trả lỗi 503 hoặc timeout.
- Connection pool hết kết nối trong một khoảng ngắn.
- Rate limit của dịch vụ downstream bị vượt.
- Một dependency đang khởi động lại hoặc failover.
- Lỗi tài nguyên tạm thời khiến thao tác chưa thể hoàn tất.

Nếu bỏ qua record ngay sau lỗi, ứng dụng có thể làm mất tác động nghiệp vụ của event. Nếu retry vô hạn ngay trong poll thread, consumer có thể bị kẹt, vượt poll interval và làm group rebalance.

Retry tạo cơ hội xử lý lại record sau khi nguyên nhân tạm thời được khắc phục. Một chiến lược retry tốt cần trả lời:

1. Lỗi nào có thể retry?
2. Retry bao nhiêu lần?
3. Khoảng chờ giữa các lần retry là bao lâu?
4. Trong khi chờ, các record khác có được xử lý không?
5. Nếu retry hết số lần, record được đưa đi đâu?
6. Retry có làm thay đổi thứ tự theo key hoặc partition không?
7. Làm sao tránh duplicate side effect khi record được giao lại?

## 2. Phân biệt blocking retry, retry topic và DLT

Có ba khái niệm thường được dùng cùng nhau nhưng vai trò khác nhau.

| Cơ chế | Cách hoạt động | Ảnh hưởng chính |
|---|---|---|
| Blocking retry | Consumer thử lại record tại luồng xử lý hiện tại trước khi đi tiếp | Giữ thứ tự partition tốt hơn nhưng có thể chặn các record phía sau |
| Retry topic | Record lỗi được publish sang topic khác để thử lại sau | Main topic tiếp tục; record sau có thể vượt record đang retry |
| Dead Letter Topic (DLT) | Record hết retry hoặc gặp lỗi không thể xử lý được chuyển sang topic cách ly | Tách lỗi khỏi luồng chính để điều tra và replay có kiểm soát |

Retry topic không phải là DLT. Retry topic là nơi lưu record đang chờ một lần thử khác. DLT thường là nơi nhận record đã hết chính sách retry hoặc được phân loại là không thể xử lý tự động.

Một record có thể đi qua nhiều retry topic với các khoảng delay khác nhau, rồi cuối cùng được chuyển vào DLT.

~~~text
Main topic
    |
    v
Consumer xử lý
    |
    +---- Thành công ----------------------> Hoàn tất
    |
    +---- Lỗi tạm thời
    |        |
    |        v
    |    Retry topic (delay ngắn)
    |        |
    |        v
    |    Consumer retry
    |        |
    |        +---- Thành công ------------> Hoàn tất
    |        |
    |        +---- Lỗi tiếp
    |                 |
    |                 v
    |             Retry topic tiếp theo
    |                 |
    |                 v
    |                DLT
    |
    +---- Lỗi không retry ----------------> DLT hoặc cách ly
~~~

Blocking retry giữ record trong tiến trình xử lý của partition. Retry topic tách record sang một log khác. DLT lưu record cần điều tra hoặc xử lý thủ công.

## 3. Kafka bảo đảm thứ tự ở đâu?

Kafka duy trì thứ tự record trong một partition. Một consumer group tại một thời điểm chỉ gán một partition cho tối đa một member. Khi consumer đọc tuần tự partition, nó nhận các record theo thứ tự offset.

Ví dụ topic orders có partition 2:

~~~text
partition 2
offset 100: OrderCreated(order-42)
offset 101: PaymentAuthorized(order-42)
offset 102: InventoryReserved(order-42)
offset 103: ShipmentCreated(order-42)
~~~

Nếu tất cả record dùng key order-42 và cùng partitioning rule, chúng có thể được lưu trong cùng partition theo thứ tự producer append.

Nhưng khi offset 100 bị lỗi và được chuyển sang retry topic:

~~~text
orders partition 2:
offset 100: OrderCreated(order-42)       -> chuyển retry
offset 101: PaymentAuthorized(order-42)  -> xử lý tiếp
offset 102: InventoryReserved(order-42)  -> xử lý tiếp

orders-retry partition 2:
retry record: OrderCreated(order-42)    -> chờ delay
~~~

Main topic và retry topic là hai log độc lập. Consumer main topic có thể xử lý PaymentAuthorized và InventoryReserved trước khi OrderCreated được thử lại thành công.

**Cùng key không có nghĩa cùng một thứ tự xuyên qua nhiều topic.** Key có thể giúp record cùng entity vào cùng partition index nếu partitioner và partition count tương thích, nhưng hai topic vẫn có offset, consumer progress và lịch xử lý độc lập.

## 4. Vì sao retry topic có thể phá vỡ thứ tự theo key?

Giả sử một đơn hàng có ba event liên tiếp:

| Offset ở main topic | Key | Event | Version |
|---:|---|---|---:|
| 100 | order-42 | OrderCreated | 1 |
| 101 | order-42 | PaymentAuthorized | 2 |
| 102 | order-42 | InventoryReserved | 3 |

Consumer nhận version 1 nhưng database đang lỗi. Framework publish record này sang retry topic để thử lại sau 30 giây. Main consumer tiếp tục nhận version 2 và version 3.

Kết quả có thể xảy ra:

~~~text
10:00:00  version 1 nhận lỗi database
10:00:01  version 1 được chuyển sang retry topic
10:00:02  version 2 được xử lý thành công
10:00:03  version 3 được xử lý thành công
10:00:30  version 1 được retry và xử lý thành công
~~~

Trạng thái cuối cùng có thể bị lùi từ version 3 về version 1 nếu consumer ghi đè không kiểm tra version.

Vấn đề không nằm ở việc Kafka sắp xếp sai partition. Kafka đã giữ đúng thứ tự trong main topic. Ứng dụng đã tách version 1 sang một luồng có lịch xử lý khác, khiến thứ tự hoàn thành nghiệp vụ thay đổi.

### 4.1. Giữ cùng key trên retry topic vẫn chưa đủ

Khi chuyển record sang retry topic, producer thường giữ key của record gốc. Nếu retry topic có partition count và partitioner tương thích, record có thể được ghi vào partition tương ứng với key ban đầu.

Điều đó giúp các retry của cùng key có thể được gom lại, nhưng không tạo thứ tự tổng thể giữa main topic và retry topic:

- Main consumer tiếp tục đọc main partition.
- Retry consumer đọc retry partition theo tiến độ riêng.
- Hai consumer có thể chạy đồng thời.
- Record mới ở main topic có thể hoàn tất trước record cũ ở retry topic.
- Delay khác nhau có thể khiến retry attempt đến theo thứ tự khác nhau.

Muốn bảo vệ thứ tự, phải có cơ chế phối hợp giữa luồng chính và luồng retry.

### 4.2. Nhiều tầng retry có thể làm thứ tự khó dự đoán hơn

Ví dụ một event được chuyển qua các topic delay 1 giây, 10 giây và 1 phút. Event version 2 có thể lỗi ít hơn và được xử lý ngay, trong khi version 1 đang ở tầng delay dài nhất.

Nếu không kiểm tra version hoặc trạng thái entity, các event có thể hoàn thành theo thứ tự:

~~~text
version 2 -> hoàn tất
version 3 -> hoàn tất
version 1 -> retry thành công
~~~

Không nên giả định retry topic sẽ tự sắp xếp lại theo offset ban đầu. Delay queue là cơ chế điều phối thời điểm thử lại, không phải cơ chế phục hồi thứ tự nghiệp vụ.

## 5. Chọn chiến lược theo yêu cầu ordering

Trước khi chọn retry, cần xác định phạm vi thứ tự mà nghiệp vụ yêu cầu:

- **Thứ tự toàn partition:** mọi record trong partition phải hoàn tất lần lượt.
- **Thứ tự theo key/entity:** các event cùng orderId phải theo thứ tự, nhưng entity khác vẫn có thể tiến triển.
- **Không cần thứ tự nghiêm ngặt:** event đến trễ có thể được xử lý nếu consumer kiểm tra version và trạng thái.
- **Thứ tự giữa nhiều topic:** cần một workflow coordinator hoặc version logic; Kafka không tự tạo total order giữa topic.

Bảng quyết định:

| Yêu cầu | Chiến lược thường phù hợp | Đánh đổi |
|---|---|---|
| Giữ thứ tự nghiêm ngặt trong partition | Blocking retry tại chỗ | Một record có thể chặn các record phía sau |
| Giữ thứ tự theo entity, cho entity khác tiếp tục | Per-key holdback hoặc durable state machine | Phức tạp hơn, cần lưu trạng thái chờ |
| Cho phép event đến trễ | Retry topic + aggregate version | Consumer phải phát hiện gap và stale event |
| Event lỗi không thể tự phục hồi | DLT + quy trình replay có kiểm soát | Cần vận hành và theo dõi DLT |
| Workflow có nhiều topic | Correlation ID, sequence/version và coordinator | Cần điều phối ở tầng ứng dụng |

Không có một chiến lược tối ưu cho mọi topic. Chọn theo hậu quả khi event bước sau được xử lý trước event bước trước.

## 6. Blocking retry: giữ thứ tự bằng cách chờ tại chỗ

Blocking retry thử lại record lỗi trước khi consumer tiếp tục các record sau trong cùng luồng xử lý. Với một partition, record phía sau không được xử lý vượt qua record đang retry theo mô hình xử lý tuần tự.

Ví dụ:

~~~text
partition 2:
offset 100: OrderCreated       -> lỗi, retry
offset 101: PaymentAuthorized  -> chờ
offset 102: InventoryReserved  -> chờ

Sau khi offset 100 thành công:
offset 101 được xử lý
offset 102 được xử lý
~~~

Ưu điểm:

- Giữ thứ tự xử lý của partition.
- Không cần phối hợp thứ tự giữa main topic và retry topic.
- Dễ suy luận khi các event cùng entity nằm trong cùng partition.
- Phù hợp với quy trình không cho phép bước sau vượt bước trước.

Nhược điểm:

- Một record lỗi có thể chặn mọi entity khác cùng partition.
- Downstream lỗi kéo dài làm consumer lag tăng.
- Retry delay dài có thể làm poll loop không tiến triển.
- Consumer có thể vượt max.poll.interval.ms nếu retry block không được quản lý đúng.
- Một partition nóng hoặc có poison message có thể ảnh hưởng nhiều key khác.

### 6.1. Ví dụ Spring Kafka với DefaultErrorHandler

Có thể cấu hình retry hữu hạn bằng DefaultErrorHandler và FixedBackOff:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            template,
            (record, exception) ->
                new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
        );

    FixedBackOff backOff = new FixedBackOff(
        1_000L, // delay giữa các lần retry
        2L      // số lần retry sau lần giao đầu tiên
    );

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class,
        InvalidOrderEventException.class
    );

    return handler;
}
~~~

Ví dụ minh họa cấu hình Spring Kafka; cần khai báo bean vào listener container factory theo phiên bản đang dùng và bảo đảm DLT có đủ partition để nhận record từ partition nguồn. Nếu không dùng DLT, có thể cấu hình recoverer khác theo chính sách ứng dụng.

Với FixedBackOff trong ví dụ, consumer thử lại hữu hạn. Khi hết retry, recoverer publish record sang DLT. Không nên cấu hình retry vô hạn nếu một record có thể bị lỗi cố định.

Lưu ý: khi record được recover thành công bằng cách publish sang DLT, luồng main có thể tiếp tục với offset sau. Vì vậy blocking retry giữ thứ tự trong thời gian record còn đang được retry; việc chuyển record sang DLT không tự bảo đảm event đó sẽ được xử lý trước các event sau. Nếu thứ tự theo entity vẫn bắt buộc sau khi đưa vào DLT, cần giữ entity ở trạng thái blocked hoặc dùng version gate cho đến khi record được phục hồi.

### 6.2. Backoff có giới hạn

Backoff giúp giảm áp lực lên dịch vụ đang lỗi. Có thể dùng exponential backoff:

~~~text
Lần 1: chờ 1 giây
Lần 2: chờ 2 giây
Lần 3: chờ 4 giây
Lần 4: chờ 8 giây
~~~

Nên có giới hạn tối đa và cân nhắc jitter để nhiều consumer không retry đồng thời. Retry quá dày có thể tạo retry storm, làm dependency đang phục hồi tiếp tục quá tải.

### 6.3. Khi nào blocking retry không phù hợp?

Không nên dùng blocking retry dài cho mọi lỗi nếu:

- Một partition chứa nhiều entity không liên quan.
- Downstream có sự cố kéo dài nhiều phút.
- Consumer cần tiếp tục xử lý entity khác.
- Thời gian retry vượt giới hạn poll hoặc SLA.
- Poison message có thể chặn partition vô thời hạn.

Có thể chuyển record sang DLT sau số lần retry hữu hạn, hoặc thiết kế holdback theo key để chỉ chặn entity lỗi.

## 7. Non-blocking retry: đưa record sang retry topic

Non-blocking retry chuyển record lỗi sang một topic khác để thử lại sau. Main consumer có thể tiếp tục xử lý các record phía sau.

Spring Kafka hỗ trợ retry topic thông qua @RetryableTopic. Framework có thể tạo các retry topic theo cấu hình delay và chuyển record giữa các tầng retry trước khi đưa vào DLT.

Ví dụ:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 30_000
    ),
    dltTopicSuffix = ".DLT"
)
@KafkaListener(
    topics = "orders",
    groupId = "order-projection"
)
public void listen(
        ConsumerRecord<String, OrderEvent> record) {

    orderProjection.apply(record.key(), record.value());
}
~~~

Ví dụ dùng annotation của Spring Kafka. Cần kiểm tra import, phiên bản framework, cấu hình topic auto-creation, serializer và DLT handler của ứng dụng. Thuộc tính attempts biểu thị tổng số lần giao theo semantics của phiên bản Spring Kafka; xác nhận lại tài liệu phiên bản đang dùng trước khi đặt số lần retry cho production.

### 7.1. DLT handler

Có thể khai báo handler cho record đã hết retry:

~~~java
@DltHandler
public void handleDlt(
        ConsumerRecord<String, OrderEvent> record) {

    // Ghi eventId, key, topic gốc và lỗi.
    // Đưa vào quy trình điều tra hoặc replay có kiểm soát.
}
~~~

DLT handler nên ghi nhận tối thiểu:

- Topic, partition và offset gốc nếu có metadata.
- Entity key và event ID.
- Aggregate version.
- Exception class và thông điệp lỗi.
- Số lần retry và thời điểm lỗi.
- Correlation ID hoặc trace ID.

Không log toàn bộ payload nếu có dữ liệu nhạy cảm hoặc dung lượng lớn.

### 7.2. Ưu điểm và giới hạn

Ưu điểm:

- Main topic không bị chặn lâu bởi một record lỗi.
- Có thể đặt delay dài mà không giữ listener thread chờ.
- Retry được tách thành luồng riêng, dễ theo dõi.
- Hữu ích khi downstream lỗi tạm thời nhưng các entity khác vẫn cần tiếp tục.

Giới hạn:

- Event mới hơn của cùng key có thể được xử lý trước event đang retry.
- Retry consumer có thể có tốc độ và concurrency khác main consumer.
- Delay và nhiều retry tier làm tăng độ phức tạp vận hành.
- Record có thể được giao nhiều lần, nên consumer phải idempotent.
- Replay từ DLT có thể làm thứ tự khác với lịch sử ban đầu.

### 7.3. Retry topic không phải một delay queue toàn cục

Mỗi retry topic là một Kafka topic có partition log riêng và tiến độ đọc riêng theo consumer group. Group ID và cách các listener container tham gia group được framework quản lý theo cấu hình; không nên giả định retry topic có một group ID độc lập nếu chưa kiểm tra cấu hình thực tế. Delay được thực hiện theo cơ chế framework quản lý, chẳng hạn các topic có khoảng delay khác nhau hoặc cơ chế scheduler tương ứng phiên bản.

Không nên giả định mọi record được phát lại chính xác tại một thời điểm tuyệt đối. Consumer lag, broker load, scheduling và số lượng record chờ đều có thể làm thời điểm retry thực tế trễ hơn cấu hình.

## 8. Giữ thứ tự bằng aggregate version

Một cách thực tế để chấp nhận non-blocking retry mà vẫn bảo vệ state là gắn version tăng dần cho từng aggregate.

Ví dụ:

~~~text
orderId=order-42
version=1  OrderCreated
version=2  PaymentAuthorized
version=3  InventoryReserved
version=4  ShipmentCreated
~~~

Consumer lưu version đã áp dụng. Khi nhận event:

- Version bằng currentVersion + 1: có thể áp dụng.
- Version nhỏ hơn hoặc bằng currentVersion: có thể là duplicate hoặc stale event.
- Version lớn hơn currentVersion + 1: có gap, cần chờ hoặc khôi phục event bị thiếu.

Ví dụ currentVersion đang là 0 nhưng consumer nhận version 2:

~~~text
Current version: 0
Received version: 2

Expected version: 1
Result: GAP
Action: Hold, retry, replay hoặc điều tra
~~~

Không nên áp dụng version 2 chỉ vì record deserialize thành công. Nếu event version 1 vẫn đang ở retry topic, áp dụng version 2 có thể làm trạng thái entity nhảy qua một bước.

### 8.1. Conditional update trong database

Version check phải được bảo vệ bằng transaction hoặc optimistic locking. Tránh thực hiện đọc version rồi ghi state bằng hai thao tác tách rời.

Ví dụ SQL:

~~~sql
UPDATE orders
SET status = :new_status,
    version = :next_version
WHERE order_id = :order_id
  AND version = :expected_version;
~~~

Nếu số dòng được cập nhật bằng 0, version hiện tại không khớp. Ứng dụng cần xác định đó là duplicate, stale event hay gap.

Cách này ngăn event cũ ghi đè state mới nếu nhiều consumer hoặc retry worker cùng tác động lên một entity.

### 8.2. Phân biệt duplicate và stale event

Giả sử currentVersion = 4:

| Version nhận được | Diễn giải có thể | Hướng xử lý |
|---:|---|---|
| 5 | Bước tiếp theo | Áp dụng nếu state transition hợp lệ |
| 4 | Có thể duplicate cùng version | Kiểm tra event ID hoặc event đã xử lý |
| 3 | Event cũ/stale | Không ghi đè state mới |
| 7 | Gap version 5 và 6 | Hold hoặc khôi phục các event còn thiếu |

Version không thay thế event ID. Hai event khác nhau có thể cùng version nếu mô hình nghiệp vụ cho phép nhiều event trong một transaction; khi đó cần sequence chi tiết hơn hoặc một quy ước version rõ ràng.

## 9. Per-key holdback: chặn entity lỗi nhưng cho entity khác tiếp tục

Nếu nghiệp vụ cần giữ thứ tự theo entity nhưng không muốn chặn cả partition, có thể xây dựng một cơ chế holdback.

Khi version 1 của order-42 lỗi:

1. Ghi trạng thái order-42 đang bị blocked tại version 1.
2. Khi nhận version 2 của order-42, không áp dụng ngay.
3. Lưu version 2 vào một vùng chờ bền vững.
4. Event của order-57 vẫn có thể tiếp tục xử lý.
5. Khi version 1 được retry thành công, xử lý tiếp version 2.
6. Xóa trạng thái blocked khi entity đã bắt kịp.

~~~text
order-42:
  version 1 -> retry, blocked
  version 2 -> hold
  version 3 -> hold

order-57:
  version 1 -> process
  version 2 -> process

Sau khi order-42 version 1 thành công:
  order-42 version 2 -> process
  order-42 version 3 -> process
~~~

Cách này cô lập lỗi theo entity thay vì theo partition. Tuy nhiên, cần lưu holdback bền vững để consumer restart không làm mất event chờ.

### 9.1. Holdback cần những thành phần nào?

Một thiết kế thường cần:

- Entity ID và version đang chờ.
- Event ID và payload hoặc vị trí tham chiếu đến payload.
- Trạng thái retry và số lần thử.
- Thời điểm tiếp theo được phép retry.
- Trạng thái blocked/unblocked.
- Cơ chế lock hoặc lease để chỉ một worker xử lý entity tại một thời điểm.
- Cơ chế xóa/hoàn tất event sau khi side effect đã commit.

Không nên giữ mọi event chờ trong RAM. Nếu process chết, các event đó sẽ mất khỏi bộ nhớ dù offset Kafka có thể đã được commit.

### 9.2. Tránh deadlock logic

Nếu entity bị blocked vì version 1, không được yêu cầu version 2 hoàn tất để version 1 được retry. Trạng thái holdback phải cho phép version thiếu được xử lý độc lập.

Cần đặt giới hạn số event chờ và thời gian chờ. Nếu một entity bị blocked quá lâu, cảnh báo và đưa vào quy trình vận hành thay vì tích lũy vô hạn.

## 10. Retry theo partition hay theo key?

Hai phạm vi này có đánh đổi khác nhau.

| Tiêu chí | Blocking retry theo partition | Holdback theo key |
|---|---|---|
| Phạm vi bị chặn | Mọi key trong partition | Chỉ entity đang lỗi |
| Độ phức tạp | Thấp hơn | Cao hơn |
| Thứ tự partition | Dễ giữ | Cần version và completion tracking |
| Throughput khi có poison event | Có thể giảm mạnh | Entity khác vẫn tiến triển |
| Lưu trạng thái chờ | Không cần kho holdback riêng | Cần lưu bền vững |
| Vận hành | Dễ suy luận hơn | Cần monitor blocked entity và backlog |
| Phù hợp | Workflow ít lỗi, thứ tự nghiêm ngặt toàn partition | Nhiều entity độc lập, cần cô lập lỗi |

Nếu một partition có nhiều entity độc lập, blocking retry có thể làm một order lỗi chặn hàng nghìn order khác. Holdback giảm phạm vi ảnh hưởng nhưng cần thiết kế dữ liệu và concurrency cẩn thận.

Không có lựa chọn đúng tuyệt đối. Đo tỷ lệ lỗi, thời gian phục hồi và mức ảnh hưởng nghiệp vụ trước khi quyết định.

## 11. Phân loại lỗi trước khi retry

Không phải mọi exception đều nên retry.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Timeout, connection reset, HTTP 503 | Retry hữu hạn với backoff |
| Rate limit | HTTP 429 | Retry theo Retry-After hoặc backoff có jitter |
| Lỗi dữ liệu | JSON sai, thiếu field bắt buộc | Không retry vô hạn; chuyển DLT |
| Lỗi nghiệp vụ vĩnh viễn | Đơn hàng đã hủy, trạng thái không hợp lệ | Cách ly hoặc xử lý theo quy tắc nghiệp vụ |
| Lỗi cấu hình | Credential sai, ACL thiếu | Sửa cấu hình; retry không tự giải quyết |
| Lỗi schema | Schema không tương thích | Kiểm tra version, có thể DLT hoặc chờ rollout |
| Lỗi phụ thuộc kéo dài | Database outage | Retry có giới hạn, circuit breaker và backpressure |

Một lỗi được xem là retryable hay không nên dựa trên nguyên nhân, không chỉ dựa vào superclass exception.

### 11.1. Exponential backoff và jitter

Nếu nhiều consumer cùng retry sau đúng một khoảng thời gian cố định, chúng có thể tạo ra đợt request dồn dập khi downstream phục hồi.

Exponential backoff tăng dần khoảng chờ:

\[
delay_n = \min(delay_{max}, delay_{base} \times multiplier^{n-1})
\]

Có thể thêm jitter để phân tán thời điểm retry:

\[
actualDelay = random(0, delay_n)
\]

Đây là công thức minh họa. Cần chọn kiểu jitter và giới hạn phù hợp với SLA. Không nên để retry kéo dài hơn thời gian lưu giữ dữ liệu hoặc cửa sổ nghiệp vụ cho phép.

## 12. Idempotency: record có thể được xử lý nhiều lần

Retry topic, DLT replay và consumer restart đều có thể khiến cùng một event được xử lý nhiều lần. Vì vậy, side effect phải được thiết kế idempotent.

Một cách là lưu event ID vào inbox với unique constraint:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một transaction database:

1. Insert event ID vào inbox.
2. Nếu event ID đã tồn tại, không thực hiện lại side effect.
3. Kiểm tra aggregate version.
4. Cập nhật state.
5. Commit transaction.

Nếu consumer crash sau khi database commit nhưng trước khi Kafka offset được commit, record có thể được giao lại. Inbox giúp lần giao lại không tạo side effect trùng.

Idempotency không tự bảo đảm ordering. Một event version cũ có event ID mới vẫn cần bị từ chối bằng version/state transition.

## 13. DLT và replay có kiểm soát

DLT là nơi lưu record không thể xử lý sau chính sách retry. DLT cần có quy trình vận hành rõ ràng:

- Cảnh báo khi DLT tăng.
- Lưu exception và metadata gốc.
- Phân loại lỗi dữ liệu, lỗi nghiệp vụ và lỗi hạ tầng.
- Xác định nguyên nhân trước khi replay.
- Replay vào topic gốc hoặc luồng recovery có kiểm soát.
- Kiểm tra key, partition, event ID và aggregate version.
- Ghi nhận ai thực hiện replay, lúc nào và vì sao.

### 13.1. Replay DLT có thể làm đảo thứ tự

Giả sử version 1 và version 2 cùng vào DLT, nhưng operator replay version 2 trước. Nếu consumer không kiểm tra version, state có thể chuyển sai.

Khi replay:

1. Nhóm record theo entity key.
2. Sắp xếp theo aggregate version hoặc sequence nghiệp vụ.
3. Kiểm tra event trước đó đã được áp dụng chưa.
4. Replay version thiếu trước.
5. Xác minh state sau mỗi batch.
6. Theo dõi duplicate và side effect.

Không nên replay toàn bộ DLT một cách mù quáng vào production. Cần dry-run, giới hạn tốc độ và kế hoạch rollback hoặc bù trừ nghiệp vụ.

### 13.2. Giữ metadata gốc

Khi chuyển record sang retry topic hoặc DLT, nên giữ:

- Original topic, partition, offset.
- Entity key.
- Event ID và aggregate version.
- Timestamp gốc.
- Retry attempt và exception.
- Trace/correlation ID.

Framework có thể lưu một số thông tin gốc trong headers. Tên header cụ thể phụ thuộc phiên bản Spring Kafka và cấu hình; ứng dụng nên dùng API của framework thay vì tự giả định tên header nội bộ.

## 14. Spring Kafka: chọn blocking hay retry topic

Spring Kafka hỗ trợ cả blocking retry qua error handler và non-blocking retry qua retry topic.

### 14.1. Blocking retry với DefaultErrorHandler

Mẫu cấu hình:

~~~java
@Bean
public DefaultErrorHandler errorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            template,
            (record, exception) ->
                new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
        );

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L)
        );

    handler.addNotRetryableExceptions(
        InvalidOrderEventException.class
    );

    return handler;
}
~~~

Cấu hình này minh họa retry tại chỗ với backoff hữu hạn và chuyển record đã recover sang DLT. Cần kết nối handler vào listener container factory và cấu hình DLT phù hợp.

### 14.2. Non-blocking retry với @RetryableTopic

~~~java
@RetryableTopic(
    attempts = "5",
    backoff = @Backoff(
        delay = 2_000,
        multiplier = 2.0,
        maxDelay = 60_000
    )
)
@KafkaListener(
    topics = "order-events",
    groupId = "order-projection"
)
public void consume(
        ConsumerRecord<String, OrderEvent> record) {

    projection.apply(record.key(), record.value());
}
~~~

Spring Kafka tự tổ chức các retry topic và chuyển record theo chính sách backoff. Cần xem xét giới hạn theo phiên bản:

- Retry topic naming và topic creation.
- Số partition và replication factor của retry/DLT.
- Exception được retry hoặc loại trừ.
- DLT handler và cách publish record lỗi.
- Serializer/deserializer cho cả record thành công và raw payload lỗi.
- Concurrency và consumer group của retry listener.
- Tác động tới ordering theo key.
- Khả năng retry topic bị lag khi downstream vẫn lỗi.

Non-blocking retry không phù hợp nếu yêu cầu nghiêm ngặt là không để event sau của cùng partition/entity được xử lý trước event lỗi, trừ khi có cơ chế version gate hoặc holdback.

### 14.3. Không trộn hai chiến lược mà không rõ ranh giới

Một ứng dụng có thể có lỗi được retry blocking và lỗi khác chuyển retry topic, nhưng phải phân loại exception rõ ràng. Nếu cùng một exception lúc thì blocking, lúc thì non-blocking, hành vi thứ tự sẽ khó dự đoán và khó vận hành.

Tạo một bảng phân loại lỗi và thống nhất chính sách:

| Exception | Retry policy | Có cho event sau tiếp tục? |
|---|---|---|
| DatabaseTimeoutException | Retry topic hoặc blocking tùy ordering | Theo yêu cầu entity |
| InvalidPayloadException | DLT ngay | Thường có, sau khi cách ly |
| RateLimitException | Retry topic với delay | Có thể, nếu version gate bảo vệ |
| OutOfOrderEventException | Holdback hoặc retry có điều kiện | Không áp dụng event vượt version |
| AuthenticationException | Dừng/cảnh báo và sửa cấu hình | Không retry dồn dập |

## 15. Retry topic và nhiều topic: không có total order

Nếu workflow phát event vào nhiều topic, thứ tự càng cần được quản lý ở tầng ứng dụng.

~~~text
orders:
  OrderCreated(order-42)

payments:
  PaymentAuthorized(order-42)

inventory:
  InventoryReserved(order-42)
~~~

Mỗi topic có partition log riêng. Dù cùng key order-42, Kafka không cung cấp một offset chung hoặc thứ tự tổng thể giữa orders, payments và inventory.

Nếu một event trong orders bị retry, event trong payments vẫn có thể được xử lý. Muốn bảo vệ workflow, có thể:

- Dùng một topic aggregate-events chứa nhiều event type.
- Gắn aggregateVersion xuyên suốt các bước.
- Dùng saga/state machine điều phối chuyển trạng thái.
- Kiểm tra prerequisite trước khi áp dụng side effect.
- Hold event nếu bước trước chưa hoàn tất.

Kafka transaction có thể ghi nhiều record nguyên tử trong phạm vi Kafka transaction, nhưng không tạo thứ tự nghiệp vụ giữa các topic và không bao trùm database/API ngoài Kafka.

## 16. Quan sát retry và tác động đến ordering

Không chỉ theo dõi tổng số record retry. Cần quan sát theo topic, key và version để phát hiện entity bị đảo thứ tự.

| Metric hoặc dấu hiệu | Ý nghĩa |
|---|---|
| Retry topic lag | Record đang chờ retry tích tụ |
| DLT record count | Lỗi không được phục hồi tự động |
| Retry attempts per event | Số lần thử và nhóm lỗi phổ biến |
| Retry age | Tuổi của record từ lần lỗi đầu tiên |
| Main topic consumer lag | Main consumer có đang tiến triển không |
| Version gap count | Event bước sau đến khi version trước chưa hoàn tất |
| Stale event count | Event cũ đến sau state mới |
| Duplicate event ID | Record được giao hoặc publish lặp |
| Per-key blocked duration | Entity bị hold quá lâu |
| Retry publish failure | Framework không thể chuyển record sang retry topic |

Log nên có:

~~~text
entityKey=order-42
eventId=evt-1001
aggregateVersion=1
originalTopic=order-events
originalPartition=2
originalOffset=100
retryAttempt=2
exception=DatabaseTimeoutException
nextRetryAt=2026-11-20T10:30:00Z
~~~

Không cần log payload đầy đủ nếu có dữ liệu nhạy cảm. Event ID, key đã được kiểm soát và metadata gốc thường đủ để điều tra.

## 17. Runbook khi retry làm sai thứ tự

Khi phát hiện event version 2 đã được áp dụng trong khi version 1 đang ở retry topic:

1. Xác định entity key và aggregate version hiện tại.
2. Tạm ngăn các event mới của entity đó tạo thêm side effect nếu cần.
3. Kiểm tra retry topic và DLT để tìm version còn thiếu.
4. Kiểm tra event ID để phân biệt duplicate với event chưa xử lý.
5. Khôi phục version thiếu theo thứ tự.
6. Dùng conditional update hoặc state machine để không ghi đè state mới.
7. Nếu đã phát sinh side effect không thể đảo ngược, thực hiện nghiệp vụ bù trừ.
8. Xác minh trạng thái cuối và giải phóng entity khỏi holdback.
9. Điều chỉnh retry policy nếu lỗi tương tự có thể lặp lại.

Không reset offset của main topic một cách tùy tiện để cố khôi phục thứ tự. Reset offset có thể làm phát lại nhiều record và tạo duplicate side effect.

## 18. Chọn retry strategy cho từng loại workload

| Workload | Đặc tính | Chiến lược thường phù hợp |
|---|---|---|
| Ledger hoặc giao dịch tài chính | Thứ tự và tính đúng đắn rất nghiêm ngặt | Blocking retry có giới hạn, version gate, inbox/outbox |
| Order workflow | Các bước của cùng order phải tuần tự | Key=orderId, version, blocking hoặc per-key holdback |
| Notification | Có thể chấp nhận đến trễ hoặc đổi thứ tự trong giới hạn | Retry topic, idempotent delivery |
| Telemetry | Nhiều record, có thể bỏ qua một số lỗi dữ liệu | Retry hữu hạn, DLT và xử lý theo lô |
| Projection/read model | Có thể rebuild hoặc replay | Retry topic + version check + rebuild strategy |
| Inventory reservation | Không được trừ/giữ tồn kho hai lần | Idempotency, conditional update và version gate |

Đây là gợi ý thiết kế ban đầu. Cần xác nhận RPO, RTO, thứ tự nghiệp vụ và hậu quả của duplicate trước khi triển khai.

## 19. Những lỗi thường gặp

- **Cho rằng cùng key bảo đảm thứ tự xuyên qua retry topic:** mỗi topic là một log riêng.
- **Dùng non-blocking retry cho workflow nghiêm ngặt mà không version gate:** event bước sau có thể vượt event lỗi.
- **Retry vô hạn:** poison message có thể gây retry storm và tích tụ backlog.
- **Không phân loại exception:** lỗi dữ liệu cố định bị retry như lỗi mạng tạm thời.
- **Chỉ có DLT nhưng không có replay runbook:** record bị cách ly nhưng không có đường phục hồi.
- **Replay DLT không sắp xếp theo entity version:** state có thể tiếp tục sai.
- **Commit offset ngay sau khi enqueue worker:** crash có thể làm mất tác vụ chưa hoàn tất.
- **Không idempotent consumer:** retry hoặc replay tạo side effect trùng.
- **Tăng retry delay mà không theo dõi tuổi record:** event có thể trễ quá SLA nghiệp vụ.
- **Không giữ original metadata:** khó truy vết record từ retry/DLT về partition gốc.
- **Cho rằng retry topic là delay queue chính xác:** thời điểm retry còn phụ thuộc lag và scheduling.
- **Cho rằng Kafka transaction tự bảo vệ database:** transaction Kafka không tự bao trùm side effect ngoài Kafka.

## 20. Checklist thiết kế retry topic

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Error classification | Lỗi nào retry, lỗi nào DLT ngay? |
| Retry count | Số lần thử có giới hạn không? |
| Backoff | Có exponential backoff, max delay và jitter phù hợp không? |
| Ordering scope | Cần giữ thứ tự toàn partition hay theo entity key? |
| Key preservation | Key gốc có được giữ khi publish retry không? |
| Partitioning | Retry topic có partition strategy phù hợp không? |
| Version gate | Consumer có phát hiện duplicate, stale event và gap không? |
| Holdback | Có cần lưu bền vững event sau của entity đang lỗi không? |
| Idempotency | Side effect có chống duplicate không? |
| DLT | Có cảnh báo, điều tra và replay có kiểm soát không? |
| Observability | Có theo dõi retry age, lag, DLT và version gap không? |
| Retention | Retry/DLT có giữ dữ liệu đủ lâu cho vận hành không? |
| Capacity | Retry consumer và downstream có đủ capacity khi backlog phục hồi không? |
| Spring Kafka | Annotation/error handler có tương thích phiên bản và listener type không? |

## 21. Kết luận

Retry topic giúp tách record lỗi khỏi luồng chính và thử lại sau một khoảng delay, nhờ đó main consumer có thể tiếp tục xử lý. Đổi lại, record đang retry có thể bị event mới hơn của cùng key vượt qua. Cùng key chỉ giúp định tuyến theo partition trong từng topic; nó không tạo thứ tự tổng thể giữa main topic, retry topic và DLT.

Nếu thứ tự nghiêm ngặt quan trọng, blocking retry tại chỗ giữ partition ordering tốt hơn nhưng có thể chặn các entity khác cùng partition. Nếu cần non-blocking retry, hãy dùng aggregate version, idempotent consumer và state transition có điều kiện; khi cần cô lập lỗi theo entity, xây dựng per-key holdback bền vững. DLT và replay phải có runbook, giữ metadata gốc và phục hồi theo version.

Một chiến lược retry đáng tin cậy luôn kết hợp phân loại lỗi, retry hữu hạn, backoff, idempotency, quan sát backlog và quy trình phục hồi. Chọn chiến lược dựa trên hậu quả nghiệp vụ khi event đến trễ hoặc sai thứ tự, không chỉ dựa trên mong muốn làm consumer tiếp tục chạy.
