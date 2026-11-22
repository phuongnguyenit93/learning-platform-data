# Tumbling window, hopping window, sliding window và session window

Kafka Streams xử lý event liên tục, nhưng nhiều bài toán nghiệp vụ cần tổng hợp dữ liệu theo một khoảng thời gian: số đơn hàng trong mỗi 5 phút, doanh thu theo các khoảng 10 phút cập nhật mỗi phút, số thao tác trong 30 phút gần nhất hoặc một phiên hoạt động của người dùng kết thúc khi họ không phát sinh event trong một khoảng thời gian.

Windowing chia luồng event thành các cửa sổ thời gian để Kafka Streams có thể nhóm, đếm, cộng, join hoặc lưu trạng thái theo key và khoảng thời gian. Bốn loại cửa sổ thường gặp là tumbling, hopping, sliding và session. Chúng khác nhau ở cách xác định ranh giới, mức độ chồng lấn và cách xử lý khi event đến muộn.

## 1. Windowing giải quyết bài toán gì?

Giả sử topic orders.events chứa event tạo đơn hàng. Nếu chỉ gọi count() trên KGroupedStream, kết quả là tổng số event theo key trong toàn bộ vòng đời state store. Nếu cần số đơn hàng theo từng khoảng 5 phút, phải nhóm theo key và cửa sổ thời gian.

Ví dụ đầu ra:

| Cửa sổ | Số đơn hàng |
|---|---:|
| 10:00–10:05 | 42 |
| 10:05–10:10 | 57 |
| 10:10–10:15 | 39 |

Window không chỉ là bộ lọc theo thời gian. Nó là một phần của key trạng thái: kết quả aggregate được xác định bởi business key và ranh giới window. Một key có thể có nhiều kết quả tương ứng với nhiều window.

Các use case phổ biến:

- Đếm số đơn hàng, thanh toán hoặc request theo phút/giờ.
- Tính doanh thu, số lượng hoặc trung bình trong một khoảng thời gian.
- Phát hiện burst traffic và hành vi bất thường.
- Gom các thao tác gần nhau thành một session của user/device.
- Join hai luồng event có timestamp gần nhau.
- Tạo báo cáo cập nhật liên tục hoặc chỉ phát kết quả khi window đóng.

## 2. Event time, processing time và stream time

Trước khi chọn window, cần phân biệt ba khái niệm thời gian.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event time | Thời điểm nghiệp vụ thực sự xảy ra, thường nằm trong payload | Người dùng đặt hàng lúc 10:03 |
| Processing time | Thời điểm ứng dụng xử lý record | Kafka Streams xử lý record lúc 10:07 |
| Stream time | Mốc thời gian tiến triển theo timestamp của record mà task đã quan sát | Task đã xử lý event có timestamp lớn nhất là 10:07 |

Kafka Streams windowing thông thường dựa trên timestamp của record, tức event time nếu producer/extractor cung cấp đúng timestamp nghiệp vụ. Nó không tự dùng đồng hồ máy chủ tại thời điểm xử lý.

Ví dụ model được dùng trong các phần tiếp theo:

~~~java
public record OrderEvent(
    String eventId,
    String orderId,
    String customerId,
    long amount,
    Instant occurredAt
) {}
~~~

Một event xảy ra lúc 10:03 nhưng tới Kafka lúc 10:07 vẫn có timestamp event time là 10:03. Event có thể được tính vào window 10:00–10:05 nếu window chưa đóng theo stream time và grace period.

### Timestamp của Kafka record đến từ đâu?

Kafka record có timestamp. Tùy topic/broker configuration, timestamp có thể là:

- CreateTime: timestamp do producer gắn vào record; thường được dùng làm event time.
- LogAppendTime: timestamp broker gắn khi append record; gần với thời điểm broker nhận record hơn.

Kafka Streams sử dụng TimestampExtractor để lấy timestamp cho từng record. Mặc định, extractor dùng timestamp của Kafka record. Nếu muốn dùng field occurredAt trong payload, cần cấu hình custom TimestampExtractor.

~~~java
public class OrderEventTimestampExtractor implements TimestampExtractor {

    @Override
    public long extract(
            ConsumerRecord<Object, Object> record,
            long partitionTime) {

        OrderEvent event = (OrderEvent) record.value();
        if (event == null || event.occurredAt() == null) {
            return -1L;
        }

        return event.occurredAt().toEpochMilli();
    }
}
~~~

Ví dụ giả định OrderEvent có field occurredAt kiểu Instant. Timestamp âm hoặc timestamp không hợp lệ cần được xử lý theo invalid timestamp policy của Kafka Streams; không nên âm thầm thay bằng thời gian hiện tại vì điều đó làm sai event-time semantics.

Cấu hình extractor:

~~~properties
default.timestamp.extractor=com.example.streams.OrderEventTimestampExtractor
~~~

Nếu dùng WallclockTimestampExtractor, timestamp dựa trên thời gian xử lý thay vì timestamp nghiệp vụ. Cách này có thể phù hợp với một số bài toán processing-time, nhưng event đến trễ sẽ được xếp theo lúc xử lý và kết quả window có thể khác với báo cáo theo thời điểm thực tế.

### Stream time không phải wall clock

Stream time tiến triển khi task xử lý record có timestamp mới. Một task có thể không tăng stream time nếu không có record mới, dù đồng hồ hệ thống vẫn chạy. Ngược lại, một record có timestamp tương lai bất thường có thể đẩy stream time tiến nhanh và khiến các window cũ đóng sớm.

Vì vậy:

- Timestamp extractor phải nhất quán giữa các producer.
- Tránh timestamp tương lai hoặc sai timezone.
- Chuẩn hóa event time, thường dùng UTC.
- Theo dõi timestamp skew và out-of-order events.
- Không dùng grace period để che lỗi timestamp của producer.

## 3. Tổng quan bốn loại window

~~~mermaid
flowchart TD
    A[Event stream] --> B{Chọn window}
    B --> C[Tumbling]
    B --> D[Hopping]
    B --> E[Sliding]
    B --> F[Session]
    C --> G[Khoảng cố định, không chồng lấn]
    D --> H[Khoảng cố định, có thể chồng lấn]
    E --> I[Cửa sổ trượt theo timestamp của record]
    F --> J[Gom hoạt động theo inactivity gap]
~~~

| Loại | Cách xác định ranh giới | Chồng lấn? | Ví dụ phù hợp |
|---|---|---|---|
| Tumbling | Kích thước cố định, bước dịch bằng kích thước | Không | Doanh thu mỗi 5 phút |
| Hopping | Kích thước cố định, bước dịch nhỏ hơn hoặc bằng kích thước | Có thể | Tổng request 10 phút, cập nhật mỗi phút |
| Sliding | Dựa trên chênh lệch timestamp giữa các record | Có | Phát hiện hai hành động gần nhau trong 5 phút |
| Session | Kết thúc khi cùng key không có event trong inactivity gap | Không theo lưới cố định; có thể gộp session | Phiên hoạt động của user/device |

Tumbling và hopping là time windows có ranh giới cố định theo timeline. Sliding windows tạo các cửa sổ chồng lấn theo event timestamp. Session windows có ranh giới động, phụ thuộc hoạt động của từng key.

## 4. Tumbling window: khoảng cố định không chồng lấn

Tumbling window chia timeline thành các khoảng có cùng kích thước và không chồng lên nhau. Ví dụ window 5 phút:

Có thể hiểu mỗi time window là một khoảng đóng ở đầu và mở ở cuối: timestamp bằng start được tính vào window; timestamp bằng end thuộc window kế tiếp.

~~~text
10:00 ├──────── 10:05
10:05 ├──────── 10:10
10:10 ├──────── 10:15
10:15 ├──────── 10:20
~~~

Một event thuộc đúng một tumbling window dựa trên timestamp của nó. Với cửa sổ 5 phút:

- Event lúc 10:02 thuộc window 10:00–10:05.
- Event lúc 10:04:59 thuộc window 10:00–10:05.
- Event lúc 10:05:00 thuộc window tiếp theo 10:05–10:10.

Các time window được căn theo timeline epoch và kích thước/advance đã cấu hình, không bắt đầu lại theo thời điểm ứng dụng được deploy.

### Khi nào dùng tumbling?

- Tổng đơn hàng mỗi 5 phút.
- Tổng doanh thu mỗi giờ.
- Số lỗi theo từng phút.
- Báo cáo theo bucket thời gian không chồng lấn.

### Ví dụ Kafka Streams

~~~java
KGroupedStream<String, OrderEvent> ordersByCustomer =
    orders.groupBy(
        (orderId, event) -> event.customerId(),
        Grouped.with(Serdes.String(), orderEventSerde)
    );

KTable<Windowed<String>, Long> orderCountByFiveMinutes =
    ordersByCustomer
        .windowedBy(
            TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)
            )
        )
        .count(
            Materialized.as("orders-count-tumbling-5m")
        );
~~~

Ví dụ nhóm theo customerId và đếm số event trong mỗi window 5 phút. Grace period 1 phút cho phép event đến trễ trong giới hạn window chưa đóng. KTable kết quả được cập nhật khi aggregate thay đổi.

Nếu key của input đã là customerId, có thể dùng groupByKey() thay vì groupBy(). Nếu phải đổi key bằng groupBy(), Kafka Streams có thể cần repartition topic để đưa các record cùng key về cùng task.

## 5. Hopping window: khoảng cố định có bước dịch

Hopping window cũng có kích thước cố định nhưng dịch theo một bước advance. Khi advance nhỏ hơn window size, các cửa sổ chồng lấn.

Ví dụ window size 10 phút, advance 5 phút:

~~~text
10:00 ├────────────────── 10:10
             10:05 ├────────────────── 10:15
                          10:10 ├────────────────── 10:20
                                       10:15 ├────────────────── 10:25
~~~

Một event lúc 10:07 có thể thuộc cả window 10:00–10:10 và 10:05–10:15. Với size 10 phút và advance 5 phút, một event thông thường thuộc khoảng hai window. Nói chung, số window mà một event có thể tham gia phụ thuộc tỷ lệ window size/advance.

Nếu advance bằng window size, hopping không chồng lấn và hành vi tương đương tumbling. Nếu advance lớn hơn window size, có khoảng thời gian không nằm trong window nào; thường cần cân nhắc kỹ vì một số event có thể không được aggregate.

### Khi nào dùng hopping?

- Tổng request 10 phút gần nhất, cập nhật mỗi phút.
- Doanh thu trong 30 phút, cập nhật mỗi 5 phút.
- Theo dõi tải hệ thống với các bucket chồng lấn để dashboard cập nhật thường xuyên.
- Phát hiện xu hướng ngắn hạn mà không đợi hết bucket lớn.

### Ví dụ Kafka Streams

~~~java
KTable<Windowed<String>, Long> ordersPerTenMinutesEveryFive =
    ordersByCustomer
        .windowedBy(
            TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(10),
                Duration.ofMinutes(2)
            ).advanceBy(Duration.ofMinutes(5))
        )
        .count(
            Materialized.as("orders-count-hop-10m-5m")
        );
~~~

API advanceBy() định nghĩa bước dịch của hopping window. Tên API hiện đại dùng TimeWindows.ofSizeAndGrace(); hãy kiểm tra version Kafka Streams trong dự án vì các API window cũ có thể đã deprecated.

### Hopping có thể nhân số kết quả

Do một record thuộc nhiều window, aggregate có thể được cập nhật ở nhiều key window. Nếu ghi output ra topic, số record update có thể lớn hơn số input record. Cần tính chi phí state store, changelog và downstream throughput.

Không cộng các kết quả hopping như thể chúng là các bucket độc lập không chồng lấn; cùng một event có thể xuất hiện trong nhiều bucket.

## 6. Sliding window: cửa sổ trượt theo timestamp record

Sliding window được xác định bởi khoảng chênh lệch timestamp giữa các record, không phải lưới bucket cố định như tumbling/hopping. Khi record mới xuất hiện, Kafka Streams tạo hoặc mở rộng các cửa sổ có chứa record đó và các record gần nó trong khoảng thời gian cấu hình.

Ví dụ time difference 5 phút:

~~~text
Event A: 10:00
Event B: 10:03
Event C: 10:09

A và B có thể nằm trong cùng sliding window vì chênh lệch 3 phút.
C cách B 6 phút nên không thuộc cùng cửa sổ 5 phút với B.
~~~

Một record có thể tham gia nhiều sliding window khác nhau khi có các record lân cận. Cửa sổ không bắt đầu tại các mốc 10:00, 10:05, 10:10 cố định như hopping; ranh giới phát sinh từ timestamp của các record.

### Khi nào dùng sliding?

- Phát hiện hai lần đăng nhập/thao tác gần nhau.
- Đếm hoạt động của một key trong khoảng chênh lệch timestamp.
- Phân tích các sự kiện xảy ra gần nhau mà không cần bucket cố định.
- Windowed join khi cần ghép record có timestamp gần nhau.

### Ví dụ Kafka Streams

~~~java
KTable<Windowed<String>, Long> slidingOrderCounts =
    ordersByCustomer
        .windowedBy(
            SlidingWindows.ofTimeDifferenceAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)
            )
        )
        .count(
            Materialized.as("orders-count-sliding-5m")
        );
~~~

ofTimeDifferenceAndGrace() nhận time difference và grace period. Time difference là khoảng cách tối đa để các record được xét trong cùng sliding window; không phải advance interval như hopping.

### Sliding và hopping khác nhau

| Tiêu chí | Hopping | Sliding |
|---|---|---|
| Ranh giới | Các mốc cố định theo size/advance | Phát sinh theo timestamp record |
| Bước dịch | Advance interval được cấu hình | Không có advance interval cố định |
| Event thuộc nhiều window | Theo vị trí trong các bucket cố định | Theo quan hệ timestamp với các record khác |
| Kết quả | Các bucket có thể chồng lấn | Các window động có thể chồng lấn |
| Use case | Dashboard theo bucket cập nhật thường xuyên | Phân tích sự kiện gần nhau theo thời gian |

Không thay hopping bằng sliding chỉ vì cả hai đều có chồng lấn. Hãy chọn dựa trên định nghĩa nghiệp vụ của window.

## 7. Session window: gom hoạt động theo khoảng im lặng

Session window không chia timeline thành các bucket có độ dài cố định. Nó gom các record cùng key thành một session nếu khoảng cách giữa các hoạt động không vượt inactivity gap.

Ví dụ inactivity gap 30 phút:

~~~text
User A:
09:00 09:10 09:25                  10:20 10:35
|------ Session 1 ------|          |-- Session 2 --|
                         gap > 30m
~~~

Các event lúc 09:00, 09:10 và 09:25 thuộc cùng session vì các khoảng cách giữa hoạt động không vượt 30 phút. Nếu event tiếp theo đến lúc 10:20, session mới được tạo vì khoảng im lặng từ 09:25 đã vượt gap.

### Session có thể được mở rộng hoặc hợp nhất

Giả sử cùng một user có hai session tạm thời:

- Session A có event cuối lúc 10:00.
- Session B có event đầu lúc 10:50.
- Inactivity gap là 30 phút.

Một event mới lúc 10:25 có thể nối hai session vì nó cách event cuối của A 25 phút và cách event đầu của B 25 phút. Kafka Streams có thể hợp nhất các session thành một window dài hơn.

Đây là điểm khác biệt quan trọng: session boundary có thể thay đổi khi record mới đến. Aggregate cần có logic merger để kết hợp state của hai session khi chúng được nối.

### Khi nào dùng session?

- Session truy cập website/app của user.
- Phiên hoạt động của thiết bị IoT.
- Gom các thao tác của một account cho tới khi không có hoạt động trong N phút.
- Phát hiện burst event theo key với khoảng nghỉ linh hoạt.

### Ví dụ Kafka Streams

~~~java
KTable<Windowed<String>, Long> userSessions =
    userEvents
        .groupByKey(Grouped.with(Serdes.String(), userEventSerde))
        .windowedBy(
            SessionWindows.ofInactivityGapAndGrace(
                Duration.ofMinutes(30),
                Duration.ofMinutes(5)
            )
        )
        .count(
            Materialized.as("user-session-counts")
        );
~~~

Inactivity gap 30 phút xác định khoảng không hoạt động để kết thúc session; grace 5 phút cho phép event đến muộn theo stream-time policy. Một record muộn có thể mở rộng hoặc hợp nhất session nếu window vẫn còn trong thời gian được chấp nhận.

### Session aggregate cần merger

Với count(), Kafka Streams cung cấp phép cộng số lượng khi session được hợp nhất. Với aggregate tùy chỉnh, cần định nghĩa:

- Initializer: tạo state ban đầu.
- Aggregator: cập nhật state bằng record mới.
- Merger: hợp nhất state của hai session khi một record nối chúng.

~~~java
KTable<Windowed<String>, SessionSummary> summaries =
    userEvents
        .groupByKey(Grouped.with(Serdes.String(), userEventSerde))
        .windowedBy(
            SessionWindows.ofInactivityGapAndGrace(
                Duration.ofMinutes(30),
                Duration.ofMinutes(5)
            )
        )
        .aggregate(
            SessionSummary::empty,
            (key, event, summary) -> summary.add(event),
            (key, left, right) -> left.merge(right),
            Materialized.as("user-session-summary")
        );
~~~

SessionSummary là kiểu dữ liệu do ứng dụng định nghĩa. merge() phải kết hợp đúng số event, tổng amount, earliest/latest timestamp và các thuộc tính khác; không chỉ chọn tùy tiện một state.

## 8. So sánh bốn loại window bằng một bài toán

Giả sử cần phân tích hoạt động của từng customer:

| Yêu cầu | Window nên cân nhắc | Lý do |
|---|---|---|
| Đếm đơn hàng theo từng 5 phút, không trùng bucket | Tumbling | Mỗi event chỉ thuộc một khoảng cố định |
| Tính số đơn trong 15 phút gần nhất, cập nhật mỗi phút | Hopping | Bucket 15 phút trượt theo bước 1 phút |
| Xác định các thao tác cách nhau không quá 2 phút | Sliding | Ranh giới dựa trên chênh lệch timestamp record |
| Xác định phiên mua sắm kết thúc sau 30 phút không hoạt động | Session | Gap phụ thuộc chuỗi event của từng customer |

| Đặc điểm | Tumbling | Hopping | Sliding | Session |
|---|---|---|---|---|
| Độ dài | Cố định | Cố định | Time difference cố định | Động |
| Bước dịch | Bằng window size | Advance được cấu hình | Không có bước cố định | Theo event |
| Chồng lấn | Không | Có nếu advance nhỏ hơn size | Có | Session cùng key có thể hợp nhất |
| Phụ thuộc key | Aggregate có key | Aggregate có key | Aggregate có key | Rất quan trọng; gap tính theo key |
| Kết thúc window | Theo ranh giới và grace | Theo ranh giới và grace | Theo window end và grace | Theo inactivity gap và grace |
| Chi phí state | Thường thấp hơn với cùng size | Tăng theo số window chồng lấn | Có thể tăng theo số window động | Phụ thuộc số session và hoạt động key |

## 9. Grace period và late-arriving events

Trong hệ thống phân tán, event có thể đến không theo thứ tự timestamp. Ví dụ event xảy ra lúc 10:02 nhưng do mạng hoặc retry, chỉ tới Kafka Streams sau event lúc 10:07.

Grace period là khoảng thời gian cho phép record đến muộn được cập nhật window sau khi event-time window end đã qua theo stream-time. Khi stream time vượt quá window end cộng grace, window được xem là đóng; record quá muộn không còn được đưa vào aggregate của window đó.

Ví dụ tumbling window 10:00–10:05, grace 2 phút:

~~~text
Window end:       10:05
Grace period:     10:05 -> 10:07
Window closes:    sau khi stream-time vượt ngưỡng end + grace

Event timestamp 10:04, đến khi stream-time là 10:06:
  Có thể được chấp nhận trong grace.

Event timestamp 10:04, đến khi stream-time đã vượt 10:07:
  Quá muộn, không cập nhật window đã đóng.
~~~

Grace không phải thời gian chờ tính từ lúc record đầu tiên tới. Nó gắn với ranh giới window và stream-time. Nó cũng không có nghĩa Kafka Streams sẽ giữ window mở theo wall clock nếu không có record mới.

### Chọn grace period

Grace nên dựa trên độ trễ thực tế của nguồn:

- Độ trễ mạng và retry của producer.
- Thời gian queueing ở broker.
- Độ trễ xử lý và rebalance.
- Mức out-of-order của source partition.
- Yêu cầu độ chính xác của báo cáo.

Grace quá nhỏ làm rơi nhiều event đến trễ. Grace quá lớn giữ state lâu hơn, làm tăng storage và trì hoãn thời điểm có thể phát kết quả cuối cùng.

Không đặt grace vô hạn để tránh mất event. Nếu event đến trễ nhiều giờ/ngày, cân nhắc late-event topic, correction stream hoặc job backfill riêng.

## 10. Stream time và việc đóng window

Window đóng dựa trên stream time của task, không đơn giản dựa vào thời gian thực của máy. Khi task xử lý record có timestamp mới, stream time tiến triển; các window cũ có thể đi qua end + grace và được đóng.

Hệ quả:

- Nếu input ngừng hoàn toàn, stream time có thể không tiến và window chưa đóng dù wall clock đã qua lâu.
- Một record có timestamp rất xa trong tương lai có thể làm stream time nhảy nhanh và khiến window cũ đóng.
- Các partition của cùng task có thể ảnh hưởng tiến độ stream time và việc quan sát record muộn.
- Khi dùng nhiều input cho join, cần hiểu cách task đồng bộ partition/input và stream time.

Timestamp extractor cần kiểm tra timezone, clock skew và timestamp bất thường. Với event-time analytics, không thay timestamp thiếu bằng System.currentTimeMillis() một cách tùy tiện.

## 11. Window retention và state store

Kafka Streams lưu aggregate theo key và window trong state store. State store có thể dùng RocksDB hoặc store implementation khác, đồng thời có changelog topic để phục hồi state khi task chuyển instance hoặc ứng dụng restart.

Retention xác định thời gian state của window được giữ lại. Nó khác grace period:

| Cấu hình | Vai trò |
|---|---|
| Window size/time difference | Xác định phạm vi thời gian của cửa sổ |
| Inactivity gap | Xác định khoảng im lặng kết thúc session |
| Grace period | Xác định mức trễ được chấp nhận trước khi window đóng |
| Retention | Xác định state store giữ dữ liệu window trong bao lâu |

Với time window, retention phải đủ ít nhất để bao phủ window size cộng grace period. Với session window, retention cần bao phủ inactivity gap và grace theo yêu cầu của store/DSL. Có thể cần retention dài hơn nếu ứng dụng cần truy vấn lại state hoặc phục vụ interactive query.

Ví dụ materialize store:

~~~java
Materialized<String, Long, WindowStore<Bytes, byte[]>> store =
    Materialized.<String, Long, WindowStore<Bytes, byte[]>>as(
        "orders-count-store"
    )
    .withKeySerde(Serdes.String())
    .withValueSerde(Serdes.Long())
    .withRetention(Duration.ofDays(1));
~~~

Ví dụ trên minh họa cấu hình store cho windowed aggregation. Retention một ngày chỉ là giá trị ví dụ; phải lớn hơn mức tối thiểu do window/grace yêu cầu và phù hợp dung lượng disk. Không đặt retention nhỏ hơn window + grace.

### Changelog và phục hồi

Khi state store thay đổi, Kafka Streams có thể ghi changelog topic để tái tạo state. Nếu task chuyển sang instance khác, instance mới khôi phục store từ changelog và tiếp tục xử lý từ offset tương ứng.

Không xóa changelog/repartition topics khi application ID còn sử dụng. Các internal topics này là một phần của state recovery. Thay application ID có thể tạo bộ internal resources mới và làm ứng dụng bắt đầu một tiến trình state khác.

## 12. Aggregate và kết quả cập nhật liên tục

Windowed aggregation thường trả về KTable<Windowed<K>, V>. KTable phát các thay đổi của aggregate khi record mới đến; nó không nhất thiết chỉ phát một kết quả duy nhất khi window đóng.

Ví dụ count:

~~~java
KTable<Windowed<String>, Long> counts =
    ordersByCustomer
        .windowedBy(
            TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)
            )
        )
        .count();

counts.toStream().foreach((windowedKey, count) -> {
    System.out.printf(
        "customer=%s window=%s..%s count=%d%n",
        windowedKey.key(),
        Instant.ofEpochMilli(windowedKey.window().startTime()),
        Instant.ofEpochMilli(windowedKey.window().endTime()),
        count
    );
});
~~~

Mỗi lần aggregate thay đổi, KTable có thể phát update cho cùng windowed key. Consumer downstream cần hiểu đó là cập nhật trạng thái hiện tại của window, không phải một event delta để cộng thêm lần nữa.

Nếu ghi KTable changelog-style sang Kafka topic, hãy xác định key/window serde và semantics upsert. Nếu downstream cần lịch sử từng lần update, thiết kế event output riêng có event ID/version.

## 13. Chỉ phát kết quả cuối cùng khi window đóng

Một số use case muốn nhận kết quả sau khi grace period kết thúc thay vì nhận mọi update trung gian. Kafka Streams có Suppressed.untilWindowCloses() để buffer update và chỉ emit kết quả cuối khi window đóng.

~~~java
KTable<Windowed<String>, Long> finalCounts =
    ordersByCustomer
        .windowedBy(
            TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)
            )
        )
        .count()
        .suppress(
            Suppressed.untilWindowCloses(
                Suppressed.BufferConfig.unbounded()
            )
        );
~~~

BufferConfig.unbounded() minh họa semantics final-only, nhưng buffer không giới hạn có thể tiêu thụ nhiều bộ nhớ khi có nhiều key/window hoặc stream time không tiến triển. Production nên chọn giới hạn buffer, theo dõi buffer pressure và quyết định rõ hành vi khi đầy. Cấu hình emit-early khi buffer đầy sẽ thay đổi semantics từ chỉ phát kết quả cuối sang có thể phát update sớm.

Suppress không thay thế retention hoặc grace. Window vẫn cần state và thời gian chờ late record theo cấu hình. Nếu stream time không tiến, window có thể chưa đóng và kết quả final chưa được emit.

## 14. Ghi kết quả windowed ra topic

Windowed key gồm business key và metadata window. Khi ghi ra Kafka, cần Serde hiểu kiểu Windowed<K>.

Với time windows:

~~~java
finalCounts.toStream().to(
    "orders.counts.final",
    Produced.with(
        WindowedSerdes.timeWindowedSerdeFrom(String.class),
        Serdes.Long()
    )
);
~~~

Với session windows, dùng session window serde tương ứng:

~~~java
userSessions.toStream().to(
    "user.sessions.counts",
    Produced.with(
        WindowedSerdes.sessionWindowedSerdeFrom(String.class),
        Serdes.Long()
    )
);
~~~

Consumer cần giải mã windowed key để biết key gốc và ranh giới window. Một cách khác là map Windowed<K> thành business key và value envelope chứa windowStart/windowEnd/aggregate, nhưng khi đó phải thiết kế output schema rõ ràng và cân nhắc compaction key.

Không dùng Serdes.String() trực tiếp cho Windowed<String>; serialized key có thêm metadata window và cần serde đúng định dạng.

## 15. Spring Boot cấu hình Kafka Streams

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    streams:
      application-id: order-window-analytics
      properties:
        processing.guarantee: exactly_once_v2
        default.timestamp.extractor: com.example.streams.OrderEventTimestampExtractor
        state.dir: /var/lib/order-window-analytics
~~~

Application ID xác định logical Kafka Streams application và được dùng cho consumer group/internal resources. Các instance của cùng ứng dụng phải dùng cùng application ID; ứng dụng topology độc lập cần ID riêng.

Khi chạy nhiều instance, state.dir phải là thư mục local phù hợp cho mỗi process, có đủ disk và quyền ghi. Không dùng chung một thư mục RocksDB giữa nhiều instance.

### Tạo windowed topology bằng Spring Kafka Streams

~~~java
@Configuration
@EnableKafkaStreams
public class OrderWindowConfiguration {

    @Bean
    KStream<String, OrderEvent> orderWindowTopology(
            StreamsBuilder builder,
            Serde<OrderEvent> orderEventSerde) {

        KStream<String, OrderEvent> orders = builder.stream(
            "orders.events",
            Consumed.with(Serdes.String(), orderEventSerde)
        );

        KGroupedStream<String, OrderEvent> byCustomer =
            orders.groupBy(
                (orderId, event) -> event.customerId(),
                Grouped.with(Serdes.String(), orderEventSerde)
            );

        KTable<Windowed<String>, Long> counts =
            byCustomer
                .windowedBy(
                    TimeWindows.ofSizeAndGrace(
                        Duration.ofMinutes(5),
                        Duration.ofMinutes(1)
                    )
                )
                .count(
                    Materialized.as("orders-count-5m")
                );

        counts.toStream().to(
            "orders.counts.5m",
            Produced.with(
                WindowedSerdes.timeWindowedSerdeFrom(String.class),
                Serdes.Long()
            )
        );

        return orders;
    }
}
~~~

Ví dụ minh họa tumbling count theo customer. Cần khai báo bean Serde phù hợp với event schema và dependency kafka-streams tương thích với Spring Kafka version đang dùng.

## 16. Windowed join và yêu cầu thời gian

Windowing cũng được dùng cho stream-stream join. Khi join hai KStream, Kafka Streams cần biết hai record có timestamp đủ gần nhau để ghép hay không. SlidingWindows có thể định nghĩa time difference cho join; các loại join có semantics riêng về unmatched record và grace.

Không nhầm aggregate window với join window:

- Windowed aggregation nhóm record theo key và time window để tính count/sum/aggregate.
- KStream-KStream join ghép record từ hai stream theo key và thời gian.
- Session window có thể dùng trong join để ghép các event thuộc cùng phiên hoạt động.

Nếu hai input stream không cùng key partitioning, cần repartition để bảo đảm record cùng key đến cùng task. Window không tự sửa sai khác partitioning.

## 17. Late events và chiến lược correction

Grace period chỉ xử lý late record trong giới hạn đã chọn. Nếu event đến sau khi window đóng, có một số hướng:

1. Ghi nhận late event vào topic riêng để điều tra.
2. Tạo correction event cho báo cáo downstream.
3. Chạy batch backfill từ nguồn lưu trữ dài hạn.
4. Tạo topology rebuild state với application ID mới.
5. Điều chỉnh grace cho các window tương lai sau khi hiểu nguyên nhân trễ.

Không âm thầm bỏ qua late record quan trọng. Theo dõi số lượng record bị drop do late arrival và so sánh với SLO dữ liệu.

Nếu tăng grace, cần đánh giá state retention, thời gian phát final result và dung lượng store. Nếu giảm grace, cần chấp nhận tỷ lệ late event bị loại hoặc có correction path.

## 18. Key và partition ảnh hưởng window như thế nào?

Kafka Streams thực hiện windowed aggregation theo key. Tất cả record cần aggregate cùng key phải được xử lý trên cùng task/state partition.

Ví dụ:

- Đếm theo customerId: key phải là customerId trước aggregation.
- Đếm theo deviceId: key phải là deviceId.
- Session theo user: key phải là userId để inactivity gap áp dụng riêng từng user.

Nếu key nguồn là orderId nhưng aggregate theo customerId, dùng groupBy() để đổi key. Operation có thể tạo repartition topic. Repartition giúp phân phối record theo key mới nhưng tăng network, disk và serialization cost.

Không dùng timestamp làm key chỉ để tạo window. Timestamp thuộc window metadata; business key xác định entity được aggregate.

Partition count ảnh hưởng mức song song. Tăng partition có thể đổi key-to-partition mapping cho record mới; với stateful application, cần hiểu tác động đến ordering, task assignment và state restoration.

## 19. Monitoring windowed application

| Tín hiệu | Ý nghĩa |
|---|---|
| Input throughput theo partition | Nguồn có đều hay có partition nóng |
| Stream time và record timestamp lag | Task đang xử lý event time cách xa thời điểm thực tế bao nhiêu |
| Late record/drop count | Grace period có đủ cho độ trễ nguồn không |
| Window update/final emit rate | Aggregate có cập nhật và đóng window đúng kỳ vọng không |
| State store size/disk | Retention và số lượng key/window có vượt capacity không |
| Changelog/repartition throughput | Chi phí phục hồi và phân phối state |
| Suppression buffer size | Buffer final-only có tăng quá nhanh không |
| Task/stream thread state | Có task bị lỗi hoặc thread chết không |
| Consumer lag | Ứng dụng có theo kịp input topic không |
| Timestamp skew | Producer có phát timestamp tương lai/quá cũ không |

Các chỉ số late event và timestamp skew đặc biệt quan trọng. Consumer lag thấp không chứng minh window đúng nếu timestamp producer sai hoặc event bị drop do grace.

## 20. Kiểm thử window với TopologyTestDriver

TopologyTestDriver cho phép đưa record có timestamp xác định vào topology và đọc kết quả mà không cần broker thật. Điều này giúp kiểm tra ranh giới window, late record và grace period.

Ví dụ khung test:

~~~java
Properties props = new Properties();
props.put(StreamsConfig.APPLICATION_ID_CONFIG, "window-test");
props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "dummy:9092");

StreamsBuilder builder = new StreamsBuilder();
KStream<String, OrderEvent> source = builder.stream(
    "orders.events",
    Consumed.with(Serdes.String(), orderEventSerde)
);
KTable<Windowed<String>, Long> counts = source
    .groupBy(
        (orderId, event) -> event.customerId(),
        Grouped.with(Serdes.String(), orderEventSerde)
    )
    .windowedBy(
        TimeWindows.ofSizeAndGrace(
            Duration.ofMinutes(5),
            Duration.ofMinutes(1)
        )
    )
    .count();
counts.toStream().to(
    "orders.counts",
    Produced.with(
        WindowedSerdes.timeWindowedSerdeFrom(String.class),
        Serdes.Long()
    )
);

Topology topology = builder.build();

try (TopologyTestDriver driver =
         new TopologyTestDriver(topology, props)) {

    TestInputTopic<String, OrderEvent> input =
        driver.createInputTopic(
            "orders.events",
            Serdes.String().serializer(),
            orderEventSerde.serializer()
        );

    input.pipeInput(
        "order-1",
        orderEvent,
        Instant.parse("2026-11-20T10:02:00Z").toEpochMilli()
    );

    // Đọc output topic và kiểm tra Windowed key / aggregate.
}
~~~

Các test cần có:

- Record ngay trước, đúng tại và ngay sau window boundary.
- Tumbling không chồng lấn.
- Hopping một record xuất hiện trong đúng số window dự kiến.
- Sliding record gần nhau và record cách nhau quá time difference.
- Session mở rộng và hợp nhất khi có record nối hai session.
- Late record trong grace được chấp nhận.
- Late record sau grace bị drop theo policy.
- Timestamp bất thường và null/tombstone.
- Windowed key serde và output schema.
- State recovery sau restart bằng integration test với broker.

TopologyTestDriver kiểm tra logic trong process; vẫn cần integration test để kiểm tra broker, changelog topic, transaction, ACL, rebalance và disk state store.

## 21. Bài thực hành: so sánh bốn loại window

Tạo topic orders.events với key orderId và event chứa customerId, amount, occurredAt. Xây dựng topology aggregate theo customerId.

1. Tạo tumbling window 5 phút, đếm số order theo customer.
2. Gửi event tại 10:00:01, 10:04:59 và 10:05:00 để kiểm tra ranh giới.
3. Tạo hopping window size 10 phút, advance 5 phút; gửi event 10:07 và xác minh nó cập nhật các bucket chồng lấn.
4. Tạo sliding window time difference 5 phút; gửi event cách nhau 3 phút rồi 7 phút để so sánh nhóm.
5. Tạo session window gap 30 phút; gửi nhiều event cùng user và quan sát session được mở rộng.
6. Gửi event ở khoảng giữa hai session để kiểm tra merge session.
7. Thêm grace 1 phút và gửi late event trong/ngoài grace.
8. Cấu hình custom TimestampExtractor dùng occurredAt; so sánh với timestamp do broker gắn.
9. Materialize state store và quan sát changelog/retention.
10. Dùng Suppressed.untilWindowCloses() để so sánh update liên tục với final result.
11. Restart Streams application và xác minh state được phục hồi.
12. Theo dõi late record, stream time, state store size và consumer lag.

Chỉ thực hiện trên môi trường lab. Không thay timestamp extractor hoặc retention của topology production mà chưa đánh giá lại kết quả lịch sử.

## 22. Checklist chọn và triển khai window

- Xác định nghiệp vụ cần bucket cố định hay session động.
- Chọn tumbling nếu các bucket không được chồng lấn.
- Chọn hopping nếu cần bucket chồng lấn và bước cập nhật cố định.
- Chọn sliding nếu quan hệ được định nghĩa bằng timestamp difference giữa record.
- Chọn session nếu khoảng im lặng theo key quyết định ranh giới.
- Chọn timestamp extractor phản ánh đúng event time.
- Chuẩn hóa timezone và kiểm tra timestamp tương lai/quá cũ.
- Đặt grace theo độ trễ và mức out-of-order thực tế.
- Đặt retention ít nhất đủ cho window/gap cộng grace.
- Giữ key nhất quán trước aggregation và repartition khi đổi key.
- Hiểu KTable phát update liên tục; dùng suppression nếu chỉ cần final result.
- Giới hạn suppression buffer và theo dõi state store/disk.
- Dùng Windowed Serde đúng loại time/session window khi ghi output.
- Test ranh giới, late record, session merge và recovery.
- Theo dõi late event, stream time, lag, state size và final emit.

## 23. Những nhầm lẫn thường gặp

- **Tumbling và hopping giống nhau:** tumbling không chồng lấn; hopping có advance nhỏ hơn size nên một event có thể thuộc nhiều window.
- **Sliding chỉ là hopping với advance rất nhỏ:** sliding window được xác định theo timestamp difference giữa record, không theo lưới advance cố định.
- **Session có độ dài cố định:** session kết thúc theo inactivity gap và có thể được mở rộng/hợp nhất khi event mới tới.
- **Window đóng theo đồng hồ máy:** Kafka Streams dùng stream time cho event-time window lifecycle.
- **Grace là thời gian giữ state:** grace điều khiển late arrival; retention điều khiển thời gian state store giữ dữ liệu.
- **Event đến sau wall-clock end luôn bị loại:** event có thể được chấp nhận trong grace nếu stream time chưa vượt ngưỡng đóng.
- **Tăng grace không có chi phí:** grace lớn làm state và thời gian chờ final result tăng.
- **KTable chỉ phát một kết quả cuối:** aggregate thường phát update liên tục; suppression mới giới hạn output tới lúc window đóng.
- **Merge session chỉ cộng count:** custom aggregate cần merger kết hợp state đúng nghiệp vụ.
- **Window tự sửa key sai:** record cùng entity phải được group/repartition theo key phù hợp.
- **Exactly-once loại bỏ late event:** processing guarantee không thay thế timestamp, grace hoặc correction policy.
- **Consumer lag thấp nghĩa là window chính xác:** timestamp sai hoặc late event drop vẫn có thể làm kết quả sai.

Tumbling, hopping, sliding và session windows giải quyết bốn cách chia thời gian khác nhau. Tumbling phù hợp bucket cố định không chồng lấn; hopping phù hợp bucket cố định cập nhật theo bước; sliding phù hợp quan hệ gần nhau theo timestamp; session phù hợp chuỗi hoạt động có khoảng nghỉ. Để kết quả đúng, cần xác định event time, hiểu stream time và grace, giữ key/partition nhất quán, đặt retention phù hợp và kiểm thử cả event đúng hạn lẫn event đến muộn.
