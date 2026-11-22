# Grace period và xử lý sự kiện đến trễ

Trong hệ thống event streaming, thứ tự record được xử lý không phải lúc nào cũng trùng với thứ tự sự kiện xảy ra trong nghiệp vụ. Network delay, retry, consumer lag, nhiều partition và các nguồn dữ liệu khác nhau có thể khiến event cũ đến sau event mới. Kafka Streams xử lý tình huống này bằng event-time, stream-time và **grace period** của window/join.

Grace period xác định khoảng thời gian bổ sung sau khi window kết thúc mà Kafka Streams vẫn chấp nhận record đến không đúng thứ tự để cập nhật kết quả. Grace không làm consumer chờ một khoảng thời gian cố định trước khi xử lý record; nó kéo dài thời điểm window được xem là đóng. Muốn dùng đúng, cần phân biệt event-time với processing-time, out-of-order với late, grace với retention, và biết cách xử lý record đã đến sau grace.

## 1. Vì sao event có thể đến trễ?

Giả sử một đơn hàng phát ra hai event:

- `OrderCreated` xảy ra lúc 10:00.
- `PaymentAuthorized` xảy ra lúc 10:02.

Do network hoặc retry, consumer có thể nhận `PaymentAuthorized` lúc 10:03 nhưng chỉ nhận `OrderCreated` lúc 10:07. Nếu chỉ dựa vào thời điểm nhận record, hệ thống có thể kết luận sai rằng payment xảy ra trước khi order được tạo.

Các nguyên nhân phổ biến:

- Producer retry sau timeout hoặc mất kết nối.
- Một partition có tốc độ ghi/đọc chậm hơn partition khác.
- Consumer bị pause, rebalance hoặc xử lý một record lâu.
- Connector CDC đọc transaction log trễ so với database commit.
- Event đi qua nhiều service, queue hoặc retry topic.
- Đồng hồ máy chủ lệch nhau hoặc timestamp nghiệp vụ được tạo sai.
- Batch/buffer khiến record cũ được publish sau record mới.

Đối với phép tổng hợp theo thời gian, nếu một event đến sau khi kết quả window đã được xem là hoàn tất, Kafka Streams cần một quy tắc để quyết định có còn cập nhật kết quả hay không. Grace period chính là một phần của quy tắc đó.

## 2. Event-time, processing-time và stream-time

Ba khái niệm thời gian này không giống nhau:

| Loại thời gian | Ý nghĩa | Ví dụ |
|---|---|---|
| Event-time | Thời điểm sự kiện thực sự xảy ra theo dữ liệu nghiệp vụ | `occurredAt=10:02` trong payload |
| Processing-time | Thời điểm ứng dụng thực tế xử lý record | Consumer xử lý record lúc 10:07 |
| Stream-time | Mốc thời gian tiến triển theo timestamp của record mà Kafka Streams đã quan sát trong task | Task đã thấy record có timestamp lớn nhất là 10:08 |

Kafka Streams dùng timestamp của record để điều khiển window và join. Timestamp này được cung cấp qua `TimestampExtractor`; mặc định thường lấy Kafka record timestamp. Nếu producer dùng `CreateTime`, timestamp thường do producer gắn; nếu topic dùng `LogAppendTime`, broker gắn thời điểm append. Cả hai đều có thể khác event-time nghiệp vụ.

Stream-time là khái niệm logic của xử lý stream, không phải đồng hồ wall-clock. Nó tiến lên khi task xử lý record có timestamp lớn hơn mốc trước đó. Nếu không có record mới, stream-time có thể đứng yên dù thời gian thực vẫn trôi qua.

Với task xử lý nhiều input partition, timestamp từ các partition có thể ảnh hưởng tới stream-time chung của task. Một partition có event timestamp tiến nhanh có thể làm window của task tiến tới thời điểm đóng, trong khi partition khác còn event cũ chưa được đọc.

## 3. Out-of-order và late event khác nhau thế nào?

**Out-of-order event** là event có event-time nhỏ hơn một event khác đã được xử lý trước đó. Nó chưa chắc bị loại bỏ. Nếu window liên quan vẫn còn trong grace period, Kafka Streams vẫn có thể chấp nhận event đó.

**Late event** trong ngữ cảnh windowed operation là event đến khi stream-time đã vượt qua thời điểm window kết thúc cộng grace period. Khi window đã đóng theo stream-time, record không còn được dùng để cập nhật window đó và có thể bị drop khỏi nhánh windowed operation.

Ví dụ window 5 phút từ 10:00 đến 10:05, grace 1 phút:

- Event timestamp 10:04 đến khi stream-time là 10:05:30: có thể vẫn được chấp nhận.
- Event timestamp 10:03 đến khi stream-time đã tiến qua 10:06: window tương ứng đã hết grace, event quá trễ cho window đó.

Điểm quyết định là stream-time, không chỉ thời gian hiện tại trên máy. Một record có timestamp nhỏ hơn stream-time có thể là out-of-order nhưng vẫn nằm trong grace; một record đến sau wall-clock lâu chưa chắc đã late nếu stream-time chưa tiến đủ.

## 4. Grace period hoạt động như thế nào?

Với một window có thời điểm kết thúc là `windowEnd`, grace period cho phép record đến muộn trong khoảng sau `windowEnd`. Window chỉ được xem là đóng khi stream-time tiến qua ranh giới `windowEnd + grace` theo semantics của windowed operator.

```text
Window:       10:00 ---------------- 10:05
                                      |
                                      +---- Grace 1 phút ----+
                                                            10:06

Stream-time: 10:04       10:05:30       10:06:30
               |             |              |
               |             |              +-- Window đã đóng
               |             +-- Event trong grace có thể được nhận
               +-- Window vẫn đang mở
```

Grace không phải thời gian sleep của consumer. Kafka Streams vẫn xử lý record ngay khi fetch được; grace chỉ quyết định window state còn nhận update hay đã đóng.

Grace period được cấu hình theo từng window/join operation. Hai phép toán trong cùng topology có thể có grace khác nhau vì độ trễ và yêu cầu nghiệp vụ khác nhau.

## 5. Ví dụ tính kết quả với window và grace

Giả sử ứng dụng đếm số đơn hàng theo key trong các tumbling window 5 phút, grace 1 phút. Window đầu tiên là `[10:00, 10:05)`.

| Thứ tự xử lý | Event-time của record | Stream-time sau khi xử lý | Kết quả |
|---:|---|---|---|
| 1 | 10:01 | 10:01 | Cập nhật window 10:00–10:05 |
| 2 | 10:04 | 10:04 | Cập nhật cùng window |
| 3 | 10:05:30 | 10:05:30 | Window trước vẫn còn grace |
| 4 | 10:03 | 10:05:30 | Out-of-order nhưng vẫn được chấp nhận trong grace |
| 5 | 10:06:30 | 10:06:30 | Stream-time tiến qua mốc đóng window 10:06 |
| 6 | 10:02 | 10:06:30 | Quá trễ cho window 10:00–10:05; không cập nhật window đó |

Record ở bước 4 đến sau record có timestamp 10:05:30 nhưng vẫn được chấp nhận vì window chưa đóng. Record ở bước 6 có timestamp thuộc window cũ nhưng được xử lý sau khi stream-time đã vượt grace, nên không còn được tính vào kết quả window đó.

Đây là ví dụ minh họa cho tumbling window. Với hopping, session và join window, ranh giới window và cách record thuộc một hay nhiều window sẽ khác.

## 6. Cấu hình grace cho TimeWindows

Với Kafka Streams DSL hiện đại, có thể khai báo size và grace trực tiếp bằng `TimeWindows.ofSizeAndGrace()`:

```java
KTable<Windowed<String>, Long> orderCounts = orders
        .groupByKey(Grouped.with(Serdes.String(), orderSerde))
        .windowedBy(TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)))
        .count(Materialized.as("orders-count-by-window"));
```

Trong ví dụ:

- Window size là 5 phút.
- Grace là 1 phút sau khi window kết thúc.
- Record đến trong grace có thể cập nhật aggregate.
- Record đến sau khi window đóng bị loại khỏi aggregate đó.
- Kết quả là `KTable` có key dạng `Windowed<String>` vì mỗi key có nhiều window.

Các API window thay đổi qua phiên bản Kafka Streams. Với version cũ, có thể gặp API builder khác hoặc API no-grace riêng. Hãy dùng Javadoc đúng dependency; không trộn ví dụ `TimeWindows` của version cũ với API mới.

### Tumbling window

Tumbling window có các khoảng liên tiếp, không chồng lấn. Mỗi event timestamp thuộc một window theo ranh giới kích thước.

```text
10:00       10:05       10:10       10:15
  |-----------|-----------|-----------|
   Window 1    Window 2    Window 3
```

Grace được tính sau khi từng window kết thúc. Event có timestamp 10:04 có thể thuộc Window 1, nhưng nếu đến sau khi stream-time đã đóng Window 1 thì nó không cập nhật aggregate của Window 1.

### Hopping window

Hopping window có kích thước và bước trượt (advance) riêng, nên một event có thể thuộc nhiều window. Grace được áp dụng cho từng window mà event thuộc về. Một event có thể còn hợp lệ cho window mới hơn nhưng đã quá trễ cho window cũ hơn.

Ví dụ window size 10 phút, advance 5 phút:

```text
10:00             10:10
  |-----------------|
       10:05             10:15
         |-----------------|
              10:10             10:20
                |-----------------|
```

Khi xử lý late event, không nên nghĩ một record chỉ có một window nếu đang dùng hopping window.

## 7. Grace cho KStream-KStream join

KStream-KStream join ghép hai record có cùng key khi timestamp của chúng thỏa điều kiện join window. Grace cho phép các record đến không đúng thứ tự trong một khoảng sau khi join window kết thúc.

Ví dụ:

```java
KStream<String, OrderPlaced> orders = builder.stream(
        "orders",
        Consumed.with(Serdes.String(), orderSerde));

KStream<String, PaymentAuthorized> payments = builder.stream(
        "payments",
        Consumed.with(Serdes.String(), paymentSerde));

KStream<String, OrderPayment> joined = orders.join(
        payments,
        (order, payment) -> new OrderPayment(
                order.orderId(), payment.paymentId()),
        JoinWindows.ofTimeDifferenceAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)),
        StreamJoined.with(Serdes.String(), orderSerde, paymentSerde));
```

Ở đây:

- Join window cho phép hai event cùng key có timestamp chênh lệch tối đa theo cấu hình 5 phút.
- Grace 1 phút cho phép xử lý record đến trễ trong khoảng window còn mở.
- Hai input vẫn phải co-partition để record cùng key được xử lý trong cùng task.
- Record ngoài time difference hoặc đến sau grace không tạo cặp join cho window tương ứng.

Grace không mở rộng khoảng cách nghiệp vụ giữa hai event. Nếu order lúc 10:00 và payment lúc 10:20, grace 1 phút không biến chúng thành cặp hợp lệ trong join window 5 phút. Grace xử lý thứ tự đến; join window xử lý khoảng cách event-time.

### Left/outer join và thời điểm phát kết quả không khớp

Với left/outer KStream join, kết quả unmatched cần chờ đủ thời gian để phía còn lại có cơ hội đến. Grace ảnh hưởng thời điểm window được đóng và khi nào kết quả unmatched có thể được phát ra. Nếu tăng grace, kết quả cuối có thể được phát muộn hơn, đổi lại có thêm cơ hội ghép record đến trễ.

Không dùng grace quá dài nếu downstream cần kết quả nhanh. Cần cân bằng giữa độ trễ event thực tế và thời gian chờ kết luận một event không có đối tác.

## 8. Grace cho SessionWindows

Session window nhóm các event của cùng key thành một phiên dựa trên inactivity gap. Nếu giữa hai event không có khoảng im lặng vượt quá gap, chúng có thể thuộc cùng session. Khi một event đến trễ, nó có thể nối hoặc mở rộng một session đã tồn tại; thậm chí có thể hợp nhất hai session trước đó.

Với API Kafka Streams mới có hỗ trợ, có thể cấu hình session inactivity gap và grace bằng API tương ứng, ví dụ `SessionWindows.ofInactivityGapAndGrace(...)`. Tên API và khả năng có mặt phụ thuộc Kafka Streams version.

Ví dụ logic:

```text
Inactivity gap = 10 phút
Grace          = 6 phút

Event A: 10:00
Event B: 10:08  -> cùng session với A
Event X: 10:12  -> record khác làm stream-time tiến lên
Event D: 10:11  -> đến out-of-order; session A-B vẫn trong grace
Event C: 10:20  -> cách D 9 phút, có thể nối vào cùng session
```

Session window có ranh giới động vì event mới có thể mở rộng hoặc hợp nhất phiên. Do đó, không áp dụng máy móc phép tính `windowEnd` cố định như tumbling window; hãy kiểm tra session close/grace semantics của API đang dùng.

## 9. Grace period và retention của state store

Grace quyết định tới khi nào windowed operation chấp nhận late event. Retention quyết định dữ liệu window state được giữ trong store bao lâu để phục vụ xử lý và truy vấn.

Hai khái niệm liên quan nhưng không giống nhau:

| Thuộc tính | Mục đích | Nếu đặt quá thấp |
|---|---|---|
| Grace period | Xác định thời gian cho phép event đến trễ sau window end | Event đến sau ranh giới bị loại khỏi window |
| Window store retention | Giữ state/window data trong store | State cần thiết có thể hết hạn hoặc cấu hình không hợp lệ |
| Changelog retention | Giữ dữ liệu phục hồi state store trong Kafka | Có thể ảnh hưởng khả năng restore state nếu retention không phù hợp |

Với window store, retention cần đủ lớn để bao phủ window size cộng grace theo yêu cầu của Kafka Streams. Có thể cấu hình retention rõ ràng qua `Materialized.withRetention(...)`:

```java
KTable<Windowed<String>, Long> counts = orders
        .groupByKey(Grouped.with(Serdes.String(), orderSerde))
        .windowedBy(TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)))
        .count(Materialized.<String, Long, WindowStore<Bytes, byte[]>>as(
                        "orders-count-store")
                .withRetention(Duration.ofHours(1)));
```

Retention một giờ trong ví dụ chỉ để minh họa. Không nên tăng retention vô hạn để “bù” cho grace nhỏ; state lớn làm tăng disk, changelog traffic và thời gian restore. Chọn retention theo yêu cầu truy vấn, thời gian phục hồi và semantics của store.

## 10. TimestampExtractor quyết định event-time

Grace chỉ có ý nghĩa nếu timestamp đầu vào đúng. Nếu producer gửi timestamp là thời gian publish thay vì thời gian nghiệp vụ, Kafka Streams sẽ tính window theo publish time và có thể không nhận ra event thực sự đến trễ.

Ví dụ event có trường `occurredAt`:

```java
public final class OrderTimestampExtractor implements TimestampExtractor {

    @Override
    public long extract(ConsumerRecord<Object, Object> record,
                        long partitionTime) {
        if (record.value() instanceof OrderEvent event
                && event.occurredAt() != null) {
            return event.occurredAt().toEpochMilli();
        }

        // Chính sách fallback phải được chọn rõ ràng theo data contract.
        return record.timestamp();
    }
}
```

Cấu hình:

```java
props.put(
        StreamsConfig.DEFAULT_TIMESTAMP_EXTRACTOR_CLASS_CONFIG,
        OrderTimestampExtractor.class.getName());
```

Fallback về Kafka record timestamp chỉ là lựa chọn minh họa. Nếu timestamp nghiệp vụ bắt buộc phải có, có thể từ chối/quarantine record thiếu hoặc sai timestamp thay vì fallback âm thầm. Không dùng `Instant.now()` cho event lỗi vì mỗi lần retry có thể tạo timestamp mới và làm record cũ trông như event mới.

Các quy tắc nên thống nhất:

- Ghi timestamp ở UTC hoặc có timezone rõ ràng.
- Quy định độ chính xác (milliseconds, microseconds) và cách chuyển đổi.
- Kiểm tra timestamp âm, null, quá xa trong tương lai hoặc quá cũ.
- Không dùng timestamp từ client không tin cậy nếu có thể giả mạo window.
- Giữ riêng `occurredAt`, `publishedAt` và thời điểm broker append nếu nghiệp vụ cần phân tích latency.

## 11. Stream-time có thể tiến nhanh hơn một partition

Trong task có nhiều input partition, record timestamp mới từ một partition có thể làm stream-time tiến lên. Nếu một partition khác đang bị lag hoặc tạm thời không có dữ liệu, event cũ đến từ partition đó có thể bị xem là late khi cuối cùng được xử lý.

Ví dụ:

- Partition 0 đã phát event timestamp 11:00.
- Partition 1 còn record timestamp 10:45 nhưng bị trễ do consumer/network.
- Task xử lý record 11:00 trước, stream-time tiến lên.
- Khi record 10:45 được đọc, một số window của nó có thể đã qua grace.

Đây là lý do cần thiết kế partitioning, producer timestamp và consumer throughput hợp lý. Nếu event cùng entity cần thứ tự, nên dùng key ổn định để các event của entity đi cùng partition; tuy nhiên, nhiều input topic của join vẫn cần co-partitioning và có thể chịu ảnh hưởng từ partition khác trong cùng task.

### `max.task.idle.ms` và chờ input partition

Kafka Streams có cấu hình `max.task.idle.ms` trong các version hỗ trợ để task có thể chờ một khoảng khi một input partition tạm thời không có record, nhằm giảm nguy cơ xử lý dữ liệu từ input khác quá sớm. Cấu hình này có thể cải thiện tính đồng bộ của nhiều input nhưng tăng latency.

`max.task.idle.ms` không thay thế grace period:

- Grace quyết định window/join còn chấp nhận late record hay không.
- `max.task.idle.ms` ảnh hưởng cách task chờ dữ liệu input khi phối hợp nhiều partition.
- Cả hai cần được chọn theo latency, skew và độ trễ thực tế.

Không tăng `max.task.idle.ms` vô hạn để che giấu partition bị lag. Cần xử lý nguyên nhân gốc như broker/network, partition skew hoặc consumer throughput.

## 12. Chọn grace period bao nhiêu là hợp lý?

Grace nên dựa trên phân bố event lateness thực tế, không chọn theo cảm tính. Có thể đo:

```text
lateness = processing_time - event_time
```

Đây là chỉ số quan sát đơn giản; nó không hoàn toàn bằng độ trễ stream-time so với event-time nhưng giúp hiểu phân bố trễ end-to-end. Nên đo theo từng source, partition, event type và thời điểm tải cao.

Một cách chọn:

1. Thu thập lateness trong điều kiện bình thường và lúc có sự cố.
2. Tính p50, p95, p99 và maximum có ý nghĩa vận hành.
3. Xác định mức late mà nghiệp vụ còn muốn chấp nhận.
4. Chọn grace bao phủ mục tiêu lateness, có thêm biên cho biến động.
5. Ước lượng chi phí state store, retention, changelog và thời gian phát kết quả.
6. Chạy thử với event replay/out-of-order và xác nhận tỷ lệ late drop.
7. Theo dõi sau triển khai và điều chỉnh nếu phân bố thay đổi.

Ví dụ:

| Phân bố lateness | Grace tham khảo | Đánh đổi |
|---|---|---|
| Hầu hết dưới 2 giây, p99 dưới 10 giây | Vài chục giây | Kết quả nhanh, ít state hơn |
| p99 khoảng 2 phút | 2–3 phút tùy SLA | Chấp nhận phần lớn event chậm, kết quả window muộn hơn |
| Có batch/retry trễ 30 phút | Có thể cần hàng chục phút hoặc chiến lược backfill | State và độ trễ tăng đáng kể; nên cân nhắc pipeline sửa sai riêng |

Các con số chỉ minh họa. Grace lớn không giải quyết được event bị mất nhiều giờ/ngày hoặc timestamp sai; những trường hợp đó cần replay/backfill hoặc quy trình correction.

## 13. Độ trễ kết quả và chi phí của grace lớn

Grace càng lớn, Kafka Streams giữ window có khả năng nhận late event lâu hơn. Điều này ảnh hưởng:

- State store giữ nhiều window hơn.
- Changelog topic phát sinh thêm dữ liệu và retention cần phù hợp.
- Kết quả cuối của window có thể được xác nhận muộn hơn.
- Outer/left join có thể chờ lâu hơn trước khi phát unmatched result.
- Suppression tới khi window đóng sẽ giữ kết quả lâu hơn.
- Restore/rebalance có thể mất nhiều thời gian hơn khi state lớn.

Không nên đặt grace rất lớn chỉ để tránh mất event. Nếu event có thể trễ nhiều giờ nhưng phần lớn kết quả cần có trong vài giây, hãy tách luồng:

- Luồng realtime dùng grace ngắn để đáp ứng SLA.
- Luồng reconciliation/backfill xử lý dữ liệu quá trễ và phát correction/upsert.

Thiết kế này giúp kết quả realtime nhanh, đồng thời vẫn có cơ chế sửa sai cho dữ liệu đến muộn vượt SLA.

## 14. Suppression và kết quả cuối window

Với aggregation, `KTable` có thể phát update mỗi khi state thay đổi. Nếu downstream chỉ cần kết quả cuối khi window đóng, có thể dùng `Suppressed.untilWindowCloses(...)` trong topology phù hợp:

```java
KTable<Windowed<String>, Long> finalCounts = counts.suppress(
        Suppressed.untilWindowCloses(
                Suppressed.BufferConfig.unbounded()));
```

Suppression giữ kết quả cho tới khi window đóng theo stream-time/grace semantics. Nếu grace dài, kết quả cuối cũng bị trì hoãn tương ứng.

`BufferConfig.unbounded()` trong ví dụ không giới hạn bộ nhớ buffer và có rủi ro tăng memory. Trong production, cân nhắc buffer có giới hạn, spill-to-disk nếu API/version hỗ trợ, và policy khi buffer đầy. Suppression là cơ chế phát kết quả cuối, không phải cách phát hiện mọi event late hoặc chuyển chúng sang DLT.

## 15. Làm gì với event đến sau grace?

Khi record quá trễ cho một windowed operation, Kafka Streams không tự động tạo một DLT record nghiệp vụ cho mọi late event. Record có thể bị bỏ qua ở phép toán window/join tương ứng; nhánh topology khác trước phép toán vẫn có thể xử lý record tùy cách khai báo.

Có một số chiến lược:

### Chấp nhận drop có quan sát

Nếu nghiệp vụ cho phép bỏ qua event quá trễ, hãy đo số lượng và tỷ lệ late record, log metadata cần thiết và cảnh báo khi vượt ngưỡng. Không log toàn bộ payload nhạy cảm.

### Lưu raw event trước window operation

Có thể ghi một bản raw/audit stream sang topic lưu trữ trước khi thực hiện windowed aggregation. Topic này tạo nguồn cho backfill và điều tra. Cần retention, ACL và chi phí storage phù hợp.

### Tách nhánh kiểm tra lateness

Nếu cần chuyển late event sang topic riêng, phải xây dựng logic phân loại theo cùng timestamp/window semantics trước khi window operation, chẳng hạn Processor API có state/stream-time awareness. Cần bảo đảm logic phân loại khớp với window thực tế; chỉ so sánh với `Instant.now()` sẽ không tương đương stream-time.

### Correction hoặc backfill

Với event đến muộn nhưng quan trọng về nghiệp vụ, chạy một luồng sửa sai riêng: đọc raw event, tính lại kết quả hoặc phát correction event/upsert. Downstream cần idempotency/version để correction không ghi đè kết quả mới hơn.

### Rebuild state

Nếu cần tính lại lịch sử lớn, có thể tạo một Kafka Streams application với `application.id` riêng để rebuild state/output từ nguồn lưu trữ. Cần ghi output sang topic mới hoặc có cơ chế cutover; tránh chạy đồng thời hai application cùng ghi vào một topic nghiệp vụ mà không có quy tắc hợp nhất.

## 16. Replay không tự làm event hết late

Replay một event cũ vào cùng topology không đảm bảo nó được chấp nhận. Nếu stream-time đã tiến xa hơn window end + grace, event replay vẫn có thể quá trễ.

Khi cần replay/backfill:

- Xác định replay dùng cùng `application.id` hay một application ID riêng.
- Xác định state store/changelog cũ có được dùng lại hay cần rebuild.
- Xác định output topic có bị ghi duplicate hay không.
- Giữ event ID và source position ổn định để downstream deduplicate.
- Nếu cần tính lại theo lịch sử, dùng topic/output riêng rồi đối soát và cutover.
- Không reset offset production chỉ để thử replay mà chưa có kế hoạch khôi phục state và output.

Một cách phổ biến là chạy backfill với `application.id` mới và output topic mới, sau đó đối soát/cutover. Cách này tách state của lần tính lại khỏi ứng dụng realtime hiện tại.

## 17. Phân biệt grace, window size, retention và retry

| Khái niệm | Câu hỏi trả lời | Không có nghĩa là |
|---|---|---|
| Window size | Hai event có thể được gom/join trong khoảng event-time nào? | Thời gian consumer chờ trước khi xử lý |
| Grace period | Sau khi window kết thúc, còn chấp nhận event đến trễ bao lâu theo stream-time? | Kéo dài khoảng cách event-time giữa hai record |
| State store retention | Giữ state/window data trong bao lâu? | Cho phép event đến muộn vô hạn |
| Retry/backoff | Khi xử lý lỗi, thử lại sau bao lâu và bao nhiêu lần? | Làm timestamp event cũ trở thành mới |
| `max.task.idle.ms` | Task có thể chờ input partition khác bao lâu để đồng bộ xử lý? | Thay thế grace hoặc sửa partition skew |

Ví dụ: window size 5 phút, grace 1 phút, retry 10 lần. Nếu record có event-time thuộc window đã đóng, retry consumer 10 lần không làm window mở lại. Muốn xử lý event đó, cần backfill/correction hoặc tăng grace trong một lần triển khai được kiểm soát.

## 18. Theo dõi late event và stream-time

Các metric nên quan sát:

| Metric/đại lượng | Mục đích |
|---|---|
| Event-time lateness p50/p95/p99 | Hiểu độ trễ event so với thời điểm xử lý |
| Dropped/late records | Đo record bị loại do quá grace hoặc lỗi liên quan |
| Stream-time theo task | Xác định task đang tiến tới mốc event-time nào |
| Input partition lag | Tìm partition chậm làm tăng out-of-order |
| Processing rate và process latency | Phát hiện processor chậm hoặc downstream nghẽn |
| Window store size/changelog traffic | Đánh giá chi phí state khi tăng grace |
| Join unmatched/late result | Phát hiện event hai phía đến lệch thời gian |
| Suppression buffer size | Theo dõi lượng kết quả chờ window đóng |

Tên metric Kafka Streams thay đổi theo version và scope sensor. Hãy kiểm tra metric catalog của đúng Kafka Streams release và exporter. Không gắn dashboard vào một tên metric tự đoán; có thể bổ sung application metric để ghi nhận `eventTime`, `processingTime`, `taskId`, topic/partition và quyết định chấp nhận/loại.

Log nên có event ID, event timestamp, record timestamp, topic, partition, offset, task/application ID và loại xử lý. Tránh dùng event ID/customer ID làm metric label có cardinality cao.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Event cũ không cập nhật aggregate | Stream-time đã vượt window end + grace | Kiểm tra stream-time và grace; dùng correction/backfill nếu event quan trọng |
| Grace tăng nhưng vẫn có event bị drop | Timestamp sai, event trễ vượt grace mới hoặc task stream-time tiến nhanh | Kiểm tra TimestampExtractor, lateness distribution và partition skew |
| Consumer lag thấp nhưng kết quả window vẫn muộn | Grace dài hoặc suppression chờ window đóng | Xem window/grace/suppression và SLA kết quả |
| Window không bao giờ đóng | Không có record mới làm stream-time tiến lên | Hiểu stream-time không phải wall-clock; nếu cần phát theo thời gian thực, cân nhắc wall-clock punctuation hoặc logic riêng |
| Event từ partition chậm bị late | Partition khác trong task tiến stream-time trước | Kiểm tra partition lag/skew, keying và `max.task.idle.ms` |
| Tăng grace làm disk/memory tăng | Nhiều window được giữ lâu hơn | Sizing store/retention, giới hạn grace theo p99 và tách backfill |
| Join không có cặp dù cùng key | Event-time chênh quá join window | Kiểm tra timestamp, join window và grace riêng biệt |
| Outer join phát unmatched quá muộn | Grace dài hoặc stream-time chưa tiến tới mốc đóng | Đánh giá latency và stream-time progression |
| Replay event vẫn bị drop | Replay dùng state/stream-time đã tiến | Dùng application ID/state mới hoặc quy trình backfill |
| Dữ liệu sai do fallback timestamp hiện tại | Event cũ bị biến thành event mới | Dùng timestamp nghiệp vụ hợp lệ hoặc quarantine timestamp lỗi |

## 20. Checklist chọn grace và xử lý late event

**Timestamp và partition:**

- Xác định timestamp nào là event-time và ai tạo nó.
- Dùng UTC/timezone rõ ràng và chuẩn hóa độ chính xác.
- Kiểm tra timestamp null, âm, quá cũ hoặc tương lai bất thường.
- Giữ key ổn định để event cùng entity đi cùng partition.
- Theo dõi partition lag và skew giữa các input.

**Window và grace:**

- Chọn window size theo khoảng thời gian nghiệp vụ.
- Đo lateness p95/p99 trước khi chọn grace.
- Cấu hình grace rõ ràng cho từng window/join.
- Nhớ grace xử lý thứ tự đến, không mở rộng join time difference.
- Đặt state store retention đủ bao phủ window và grace.
- Đánh giá suppression và độ trễ phát kết quả cuối.

**Late-event policy:**

- Quyết định event quá grace được drop, audit, DLT/quarantine hay correction.
- Giữ raw event nếu cần khả năng backfill.
- Không giả định retry sẽ làm event cũ hợp lệ trở lại.
- Dùng application ID/state/output riêng cho lịch sử rebuild khi phù hợp.
- Bảo đảm downstream idempotent và xử lý correction theo version.

**Vận hành:**

- Theo dõi lateness, late/drop count, stream-time và partition lag.
- Theo dõi state store, changelog, suppression buffer và restore time.
- Kiểm thử out-of-order, late trong grace, late ngoài grace và idle partition.
- Kiểm thử replay/rebuild và đối soát kết quả với nguồn.
- Xác minh API/metric theo đúng Kafka Streams version.

## 21. Ghi nhớ

Event-time mô tả lúc nghiệp vụ xảy ra; processing-time là lúc ứng dụng xử lý; stream-time tiến theo timestamp record mà task quan sát. Out-of-order event chưa chắc bị drop: nếu window còn trong grace, event vẫn có thể cập nhật kết quả. Event chỉ quá trễ cho window khi stream-time đã vượt ranh giới window end cộng grace.

Grace period không phải thời gian chờ trước khi xử lý và cũng không mở rộng khoảng cách timestamp của join. Window size xác định event nào có thể thuộc cùng window/join; grace cho phép event đến trễ; retention giữ state; retry xử lý lỗi thực thi. Chọn grace dựa trên phân bố lateness và SLA, đồng thời sizing state store/changelog. Với event vượt grace, cần policy rõ ràng như drop có quan sát, lưu raw, correction hoặc backfill; replay trên state đã tiến không tự làm event cũ được chấp nhận. Thiết kế timestamp, partitioning, window, grace và late-event policy cùng nhau giúp kết quả Kafka Streams đúng hơn khi dữ liệu đến không theo thứ tự.
