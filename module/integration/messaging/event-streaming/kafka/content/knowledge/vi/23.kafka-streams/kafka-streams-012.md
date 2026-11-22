# Processor API và trường hợp DSL chưa đáp ứng

## Mục tiêu

Kafka Streams DSL cung cấp các phép biến đổi cấp cao như **map**, **filter**, **groupBy**, **aggregate**, **join**, **windowedBy** và **toTable**. Với phần lớn pipeline event streaming, DSL giúp code ngắn, dễ đọc và để framework quản lý topology, state store, repartition và task.

Tuy nhiên, một số xử lý cần điều khiển luồng record ở mức thấp: truy cập metadata của record, đọc/ghi state store theo logic riêng, phát record tới nhiều nhánh, lập lịch punctuation, hoặc triển khai state machine mà các phép DSL tiêu chuẩn không mô tả rõ. Khi đó Processor API cho phép viết logic tùy chỉnh và kết nối trực tiếp vào topology.

Bài học này trình bày ranh giới giữa DSL và Processor API, cách xây dựng processor với API hiện đại, quản lý state store, forward record, lập lịch xử lý theo thời gian và kiểm thử topology.

Sau bài học, bạn có thể:

- Chọn DSL hay Processor API theo độ phức tạp của xử lý.
- Phân biệt Processor API hiện đại với API cũ.
- Xây dựng topology gồm source, processor, state store và sink.
- Truy cập record key/value/timestamp/headers và forward record.
- Dùng state store và punctuation cho xử lý stateful tùy chỉnh.
- Kiểm thử processor bằng TopologyTestDriver.
- Hiểu tác động của task, partition, changelog, rebalance và exactly-once.

## 1. DSL và Processor API giải quyết hai mức trừu tượng

Kafka Streams DSL là API khai báo. Bạn mô tả phép biến đổi mong muốn; framework xây dựng processor topology bên dưới và quản lý phần lớn chi tiết thực thi.

Processor API là API cấp thấp hơn. Bạn định nghĩa processor node, đầu vào/đầu ra, state store và cách record được forward giữa các node. Nó cho phép kiểm soát chi tiết hơn nhưng cũng khiến ứng dụng chịu trách nhiệm nhiều hơn về luồng dữ liệu, state, ordering và lifecycle.

| Tiêu chí | Streams DSL | Processor API |
|---|---|---|
| Mức trừu tượng | Phép biến đổi cấp cao | Node xử lý record cấp thấp |
| Code | Thường ngắn và khai báo | Nhiều code lifecycle và wiring hơn |
| Join/aggregate/window | Có operator chuyên biệt | Tự xây dựng state và logic nếu cần |
| State | Framework quản lý qua table/aggregate API | Truy cập trực tiếp state store |
| Forward/routing | Theo cấu trúc DSL như branch/merge | Chủ động forward từ processor tới node downstream |
| Timestamp/punctuation | Dùng semantics của DSL/window | Có thể schedule callback theo stream time hoặc wall-clock |
| Metadata record | Có thể cần API bổ sung hoặc custom processor | Truy cập trực tiếp Record và ProcessorContext |
| Bảo trì | Dễ đọc với pipeline chuẩn | Linh hoạt nhưng dễ tạo logic khó hiểu nếu lạm dụng |

Nguyên tắc thực tế: bắt đầu bằng DSL cho filter, map, join, aggregation và windowing phổ biến. Chỉ đưa Processor API vào nơi cần khả năng điều khiển cấp thấp; một topology có thể kết hợp DSL và processor tùy chỉnh.

## 2. Khi nào DSL chưa đáp ứng?

Một số trường hợp Processor API có thể phù hợp hơn:

| Nhu cầu | Vì sao Processor API hữu ích |
|---|---|
| State machine nhiều trạng thái | Tự định nghĩa state transition, timeout và hành động khi nhận event |
| Logic state store đặc thù | Truy cập trực tiếp key-value/window/session store và quản lý nhiều thao tác trong một lần xử lý |
| Punctuation | Chạy logic định kỳ theo stream time hoặc wall-clock time |
| Routing tùy chỉnh | Forward record theo điều kiện runtime tới các node downstream |
| Record metadata | Đọc timestamp, headers và metadata nguồn trong cùng một processor |
| Custom aggregation phức tạp | Cần cập nhật nhiều store hoặc nhiều loại state theo một event |
| Protocol/envelope riêng | Kiểm tra header, version, event type và tự tạo output record |
| Tích hợp processor hiện có | Đóng gói logic tùy chỉnh thành processor node để tái sử dụng |

Không nên chuyển sang Processor API chỉ vì DSL có vẻ ít mạnh. DSL đã có nhiều operator tối ưu và biểu đạt tốt các tác vụ chuẩn. Nếu viết lại join/window/aggregation bằng state store thủ công, bạn phải tự xử lý semantics mà DSL đã giải quyết.

### 2.1. Ví dụ chọn API

Với pipeline:

1. Đọc topic orders.
2. Bỏ record không hợp lệ.
3. Chuẩn hóa currency.
4. Tổng hợp doanh thu theo cửa sổ 5 phút.
5. Ghi kết quả vào topic revenue-5m.

DSL thường là lựa chọn tốt vì filter, map, groupBy, window và aggregate đều có operator rõ ràng.

Nếu yêu cầu thêm:

- Giữ state machine theo từng order.
- Khi order không có event cập nhật trong 30 phút, phát timeout event.
- Kiểm tra header eventType và schemaVersion.
- Đọc state từ nhiều store và forward cùng record tới nhiều downstream node.

Processor API có thể giúp diễn đạt logic rõ hơn, nhất là khi callback theo thời gian và state transition là trung tâm của nghiệp vụ.

## 3. Processor API hiện đại

Kafka Streams cung cấp Processor API hiện đại trong package **org.apache.kafka.streams.processor.api**. API này làm việc với **Record<K,V>** và các kiểu generic thể hiện key/value đầu vào, đầu ra.

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| Processor<KIn,VIn,KOut,VOut> | Interface triển khai logic xử lý record |
| ProcessorSupplier<KIn,VIn,KOut,VOut> | Factory tạo processor instance cho task |
| ProcessorContext<KOut,VOut> | Context để truy cập state store, forward record, schedule punctuation và metadata runtime |
| Record<K,V> | Record gồm key, value, timestamp và headers |
| StateStore | Nơi lưu state gắn với task/partition |
| Topology | Đồ thị source, processor, state store và sink |

Với code mới, ưu tiên package **processor.api** và chữ ký API tương ứng với phiên bản Kafka Streams đang dùng. Các ví dụ cũ có thể dùng **org.apache.kafka.streams.processor.Processor**, **ProcessorContext** hoặc **transform()** với chữ ký khác; không trộn hai thế hệ API trong cùng một processor.

### 3.1. Vòng đời processor

Một processor thường có ba điểm chính:

- **init(context):** nhận context, lấy state store và đăng ký punctuation.
- **process(record):** xử lý từng record được task chuyển tới.
- **close():** giải phóng resource riêng do processor tạo ra.

Kafka Streams tạo processor instance theo task. **ProcessorSupplier** phải trả về instance mới; không dùng một processor object duy nhất cho nhiều task hoặc nhiều thread.

Processor không nên giữ mutable state dùng chung static hoặc singleton. State cần phục hồi phải đặt trong state store do Kafka Streams quản lý.

## 4. Record và ProcessorContext

**Record<K,V>** mang các thành phần:

- **key:** định danh dùng cho partitioning hoặc xử lý theo entity.
- **value:** payload của event.
- **timestamp:** timestamp được Kafka Streams dùng trong stream-time processing.
- **headers:** metadata gắn với Kafka record.

Record trong API hiện đại là đối tượng bất biến: các phương thức như **withKey**, **withValue**, **withTimestamp** tạo record mới. Cách này giúp tránh thay đổi âm thầm record đầu vào.

Ví dụ tạo record output mới:

~~~java
Record<String, Long> output = input.withValue(input.value() * 2);
context.forward(output);
~~~

**ProcessorContext** cung cấp các khả năng:

- **forward(record):** gửi record tới các child node downstream.
- **getStateStore(name):** lấy state store đã gắn vào processor.
- **schedule(...):** đăng ký punctuation theo stream time hoặc wall-clock time.
- **taskId()** và **applicationId():** nhận diện task/application đang xử lý.
- **currentStreamTimeMs()** và **currentSystemTimeMs():** đọc thời gian runtime tương ứng.
- **recordMetadata():** đọc metadata của record hiện tại khi có sẵn.

Không giả định **recordMetadata()** luôn có giá trị trong mọi callback. Ví dụ, punctuation không gắn với một record đầu vào cụ thể nên metadata record hiện tại có thể không tồn tại.

## 5. Ví dụ: processor tính running total theo key

Giả sử topic orders chứa key là orderId, value là số tiền của một giao dịch. Processor cộng dồn giá trị theo key và phát tổng hiện tại sang topic order-totals.

### 5.1. Tạo processor

~~~java
import org.apache.kafka.streams.processor.api.Processor;
import org.apache.kafka.streams.processor.api.ProcessorContext;
import org.apache.kafka.streams.processor.api.Record;
import org.apache.kafka.streams.state.KeyValueStore;

public class RunningTotalProcessor
        implements Processor<String, Long, String, Long> {

    private ProcessorContext<String, Long> context;
    private KeyValueStore<String, Long> totals;

    @Override
    public void init(ProcessorContext<String, Long> context) {
        this.context = context;
        this.totals = context.getStateStore("running-total-store");
    }

    @Override
    public void process(Record<String, Long> record) {
        if (record.key() == null || record.value() == null) {
            return;
        }

        Long current = totals.get(record.key());
        long next = (current == null ? 0L : current) + record.value();

        totals.put(record.key(), next);
        context.forward(record.withValue(next));
    }

    @Override
    public void close() {
        // Kafka Streams quản lý lifecycle của state store.
        // Đóng tại đây chỉ những resource riêng do processor tạo ra.
    }
}
~~~

Processor lấy tổng cũ từ store, cộng giá trị mới, cập nhật store và forward record có value mới. Key, timestamp và headers được giữ từ record đầu vào nhờ **withValue**.

Ví dụ:

| Input key | Input value | Stored total trước đó | Output |
|---|---:|---:|---:|
| order-1 | 100 | 0 | 100 |
| order-2 | 50 | 0 | 50 |
| order-1 | 25 | 100 | 125 |

Đây chỉ là ví dụ minh họa state theo key. Nếu nghiệp vụ cần tổng doanh thu theo customer, key đầu vào phải là customer ID hoặc topology phải repartition theo customer trước khi xử lý. State store local của một task không tự tổng hợp cùng một key nếu các record của key đó nằm ở partition khác nhau.

### 5.2. Khai báo topology

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.state.KeyValueStore;
import org.apache.kafka.streams.state.StoreBuilder;
import org.apache.kafka.streams.state.Stores;

StoreBuilder<KeyValueStore<String, Long>> totalsStore =
        Stores.keyValueStoreBuilder(
                Stores.persistentKeyValueStore("running-total-store"),
                Serdes.String(),
                Serdes.Long());

Topology topology = new Topology();

topology.addSource(
        "orders-source",
        Serdes.String().deserializer(),
        Serdes.Long().deserializer(),
        "orders");

topology.addProcessor(
        "running-total",
        RunningTotalProcessor::new,
        "orders-source");

topology.addStateStore(totalsStore, "running-total");

topology.addSink(
        "totals-sink",
        "order-totals",
        Serdes.String().serializer(),
        Serdes.Long().serializer(),
        "running-total");
~~~

Topology gồm:

1. **orders-source** đọc key/value từ topic orders.
2. **running-total** xử lý record và truy cập state store.
3. **running-total-store** giữ tổng theo key.
4. **totals-sink** ghi output vào topic order-totals.

State store được gắn vào processor bằng **addStateStore**. Tên store phải khớp với tên được lấy trong **context.getStateStore**.

### 5.3. Khởi chạy KafkaStreams

~~~java
import java.util.Properties;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsConfig;

Properties props = new Properties();
props.put(StreamsConfig.APPLICATION_ID_CONFIG, "running-total-app");
props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(
        StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
        Serdes.String().getClass().getName());
props.put(
        StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
        Serdes.Long().getClass().getName());

KafkaStreams streams = new KafkaStreams(topology, props);
streams.start();

Runtime.getRuntime().addShutdownHook(
        new Thread(streams::close));
~~~

Ví dụ dùng explicit serializers/deserializers trên source và sink nên default Serdes không quyết định các node đó; cấu hình vẫn hữu ích cho những operator hoặc store cần default Serdes trong topology mở rộng.

Trong ứng dụng thực tế, cần đăng ký **setUncaughtExceptionHandler**, **setStateListener** và **setGlobalStateRestoreListener** nếu muốn quan sát lỗi runtime, trạng thái lifecycle và quá trình restore state. Chọn exception response phù hợp thay vì tự động bỏ qua mọi lỗi.

## 6. State store trong Processor API

State store cho phép processor giữ trạng thái giữa các record. Các loại thường dùng:

| Store | Công dụng |
|---|---|
| Key-value store | Lưu giá trị hiện tại theo key |
| Window store | Lưu dữ liệu theo key và time window |
| Session store | Lưu session theo key và khoảng thời gian hoạt động |
| Versioned key-value store | Lưu nhiều phiên bản theo timestamp để hỗ trợ truy vấn theo thời gian, tùy phiên bản và cấu hình |

Persistent store thường dùng RocksDB và được hỗ trợ bởi changelog topic để phục hồi sau khi task chuyển sang instance khác. In-memory store có thể nhanh hơn nhưng nếu không có cơ chế logging phù hợp thì state có thể mất khi process dừng.

### 6.1. Store gắn với task và partition

Kafka Streams chia topology thành tasks dựa trên input partitions. Mỗi task xử lý một tập partition và có state store tương ứng. Vì vậy:

- State của một key được quản lý trong task nhận partition chứa key đó.
- Cùng key phải được partitioner route nhất quán để state lookup đúng.
- Tăng số partition có thể làm thay đổi mapping key-to-task.
- Không chia sẻ một store instance thủ công giữa các processor/task.

Nếu processor cần tổng hợp theo một key khác với key của topic nguồn, cần repartition trước. Ví dụ nguồn partition theo orderId nhưng muốn tổng hợp theo customerId, phải đổi key/repartition theo customer ID trước khi cập nhật store để mọi event của cùng customer đi tới cùng task.

### 6.2. Changelog và phục hồi state

Với state store có logging, Kafka Streams ghi các thay đổi store vào changelog topic. Khi task được chuyển sang worker khác hoặc local state bị mất, framework có thể restore store từ changelog.

Các cấu hình liên quan:

- **num.standby.replicas:** số standby task replicas để giảm thời gian khôi phục state khi task được chuyển.
- **state.dir:** thư mục local lưu state store.
- **replication.factor:** replication factor cho internal topics như changelog/repartition, theo cấu hình ứng dụng và broker.
- Cấu hình cache/state store tương ứng với phiên bản Streams đang dùng.

Không xóa changelog topic hoặc state directory khi ứng dụng đang chạy nếu chưa có kế hoạch reset/rebuild state. Mất changelog có thể khiến state không thể restore chính xác từ lịch sử đã lưu.

### 6.3. Logging và caching

State store builder có thể bật/tắt changelog logging và caching. Tắt logging làm giảm write traffic trong một số trường hợp nhưng loại bỏ cơ chế khôi phục state từ changelog; chỉ làm khi state có thể tái tạo an toàn từ nguồn và đã hiểu rõ hậu quả.

Caching có thể gom các cập nhật state/output trước khi flush, giảm write amplification và số record changelog. Đổi lại, thời điểm output xuất hiện có thể trễ hơn và không phải từng lần cập nhật store đều tạo record downstream ngay lập tức.

## 7. Forward record và routing

Trong Processor API, **context.forward(record)** chuyển record tới các child node được nối downstream trong topology. Nếu processor có nhiều child, record có thể được forward tới các nhánh đó theo cấu trúc topology.

Ví dụ, một processor phân loại sự kiện:

~~~java
// OrderResult là kiểu output chung có thể biểu diễn cả event hợp lệ
// và diagnostic record; ProcessorContext được khai báo với output type này.
@Override
public void process(Record<String, OrderEvent> record) {
    OrderEvent event = record.value();

    if (event == null) {
        return;
    }

    if (event.isValid()) {
        context.forward(new Record<String, OrderResult>(
                record.key(),
                OrderResult.valid(event),
                record.timestamp(),
                record.headers()));
    } else {
        Record<String, OrderResult> invalid =
                new Record<>(
                        record.key(),
                        OrderResult.invalid(InvalidOrder.from(event)),
                        record.timestamp(),
                        record.headers());
        context.forward(invalid, "invalid-sink");
    }
}
~~~

Đây là đoạn minh họa; class processor cần implement output generic tương ứng, ví dụ Processor<String, OrderEvent, String, OrderResult>, và ProcessorContext<String, OrderResult>. Topology phải khai báo child có tên invalid-sink. Cả nhánh hợp lệ và không hợp lệ dùng chung output type OrderResult; mỗi sink có thể serialize envelope theo contract riêng.

Một topology có thể tạo hai sink node downstream với tên khác nhau, ví dụ valid-sink và invalid-sink, rồi processor định tuyến theo điều kiện. Cần đảm bảo mọi đường đi có thể forward đều được nối đúng; nếu không, record có thể không tới output mong muốn.

### 7.1. Giữ metadata khi tạo output

Khi thay payload, dùng **record.withValue(...)** để giữ key, timestamp và headers. Nếu cần thay key hoặc timestamp, dùng phương thức tạo record tương ứng thay vì tự tạo record mới rồi vô tình bỏ metadata.

Headers có thể mang correlation ID, trace context, content type hoặc schema metadata. Không xóa header gốc nếu consumer downstream cần nó. Cũng không đưa payload nhạy cảm hoặc stack trace lớn vào header.

## 8. Punctuation: xử lý theo stream time và wall-clock time

Punctuation cho phép processor chạy callback theo thời gian mà không cần đợi một record cụ thể tới. Ví dụ:

- Phát timeout event cho order đã chờ quá lâu.
- Dọn state cũ theo retention nghiệp vụ.
- Tạo snapshot hoặc heartbeat định kỳ.
- Đóng cửa sổ xử lý tùy chỉnh khi thời gian tiến lên.

Có hai loại thời gian:

| Loại | Ý nghĩa | Đặc điểm |
|---|---|---|
| STREAM_TIME | Thời gian tiến theo timestamp record mà task quan sát | Chỉ tiến khi có record mới; phù hợp event-time logic |
| WALL_CLOCK_TIME | Đồng hồ hệ thống của máy chạy task | Có thể chạy khi không có record; phụ thuộc scheduling và runtime |

### 8.1. Schedule punctuation

~~~java
import java.time.Duration;
import org.apache.kafka.streams.processor.PunctuationType;

@Override
public void init(ProcessorContext<String, Long> context) {
    this.context = context;
    this.totals = context.getStateStore("running-total-store");

    context.schedule(
            Duration.ofMinutes(1),
            PunctuationType.STREAM_TIME,
            timestamp -> emitPeriodicSnapshot(timestamp));
}

private void emitPeriodicSnapshot(long timestamp) {
    try (var iterator = totals.all()) {
        while (iterator.hasNext()) {
            var entry = iterator.next();
            context.forward(new Record<>(
                    entry.key,
                    entry.value,
                    timestamp));
        }
    }
}
~~~

Ví dụ này minh họa cách đọc toàn bộ key-value store và forward snapshot record. Trong production, không nên scan một store lớn mỗi phút nếu chi phí vượt khả năng task; dùng index/state phù hợp, phân trang nếu có, hoặc phát snapshot theo batch có giới hạn.

### 8.2. Chọn stream time hay wall-clock

**STREAM_TIME** phù hợp khi quyết định phụ thuộc event timestamp. Nếu partition không có record mới, stream time có thể không tiến và punctuation không chạy đúng lịch đồng hồ.

**WALL_CLOCK_TIME** phù hợp với công việc định kỳ không phụ thuộc event-time, nhưng thời gian hệ thống có thể bị ảnh hưởng bởi pause, scheduling, clock skew hoặc restart. Không dùng wall-clock punctuation để suy ra event đã trễ nghiệp vụ nếu timestamp event và timezone chưa được chuẩn hóa.

Punctuation không phải cron job chính xác theo từng giây. Kafka Streams gọi callback khi task có cơ hội xử lý theo lịch; thời điểm thực tế có thể trễ so với interval được yêu cầu.

## 9. Xử lý event-time và state machine

Processor API hữu ích khi mỗi aggregate có state transition riêng. Ví dụ order có trạng thái:

~~~text
CREATED -> PAID -> FULFILLED
    |         |
    +-------> CANCELLED
~~~

Processor có thể đọc trạng thái hiện tại từ store, xác thực transition, cập nhật version và forward event kết quả.

Ví dụ logic:

~~~java
OrderState current = stateStore.get(event.orderId());

if (current == null && event.type() == CREATED) {
    stateStore.put(event.orderId(), OrderState.created(event.version()));
    context.forward(record);
    return;
}

if (current != null && event.version() == current.version() + 1) {
    OrderState next = current.apply(event);
    stateStore.put(event.orderId(), next);
    context.forward(record.withValue(toOutput(next)));
    return;
}

// Version bị lặp, bị thiếu hoặc transition không hợp lệ:
// route sang nhánh xử lý lỗi/quarantine theo topology.
~~~

Đây là pseudocode: enum, state transition và output type phải được định nghĩa theo domain. Trong production cần phân biệt duplicate event ID, event version cũ, version gap và transition nghiệp vụ không hợp lệ; không gom tất cả thành một lỗi chung.

### 9.1. Event đến trễ

Event-time processing phải xác định cách xử lý record có timestamp nhỏ hơn stream time hiện tại:

- Chấp nhận và cập nhật state nếu nghiệp vụ cho phép.
- Bỏ qua hoặc route sang late-event topic nếu đã quá giới hạn.
- Lưu vào state để reconciliation nếu có thể tới muộn.
- Dùng grace period nếu logic windowed cần chờ event trễ.

Processor API cho phép tự triển khai chính sách nhưng bạn phải chịu trách nhiệm về retention, state cleanup, ordering và replay. Nếu chỉ cần window aggregation có grace period chuẩn, DSL thường ít lỗi hơn.

## 10. Tích hợp Processor API với DSL

Không cần viết toàn bộ topology bằng Processor API nếu chỉ một bước cần logic đặc thù. Có thể xây dựng phần lớn pipeline bằng DSL rồi chèn custom processor ở ranh giới phù hợp.

Ví dụ kiến trúc:

~~~mermaid
flowchart LR
    A[builder.stream orders] --> B[DSL filter]
    B --> C[DSL selectKey / repartition]
    C --> D[Custom Processor]
    D --> E[State store]
    D --> F[DSL downstream / sink]
~~~

Các phiên bản Kafka Streams hiện đại cung cấp operator tích hợp Processor API vào DSL, chẳng hạn **process** và **processValues**. Processor API supplier dùng với process có thể định nghĩa kiểu key/value output; processValues dùng fixed-key processor để giữ nguyên key và xử lý value. Chữ ký generic, overload và cách operator kết nối output phụ thuộc Kafka Streams version, vì vậy hãy đối chiếu API reference đúng dependency trước khi triển khai.

Nếu cần wiring nhiều child node, source/sink tường minh hoặc kiểm soát topology hoàn toàn, dùng **Topology** trực tiếp như ví dụ ở phần trước. Không tạo hai topology độc lập cùng đọc một topic chỉ để kết hợp kết quả; hãy thiết kế ranh giới DSL/processor trong cùng application topology.

## 11. Topology, task và parallelism

Processor node không chạy như một thread toàn cục. Kafka Streams tạo tasks dựa trên partition của source topics và thực thi các node của topology trong từng task.

Ví dụ:

- Topic input có 12 partitions.
- Topology có một source và một processor stateful.
- Application có 3 stream threads.
- Tối đa 12 tasks có thể được tạo theo source partitions; các task được phân phối lên các thread/instance.

Tăng **num.stream.threads** không tạo thêm input partition. Nếu số partition ít, số task song song bị giới hạn. Nếu có nhiều task hơn thread, một thread có thể chạy nhiều task.

### 11.1. Không chia sẻ processor instance

Đăng ký supplier:

~~~java
topology.addProcessor(
        "running-total",
        RunningTotalProcessor::new,
        "orders-source");
~~~

Không viết:

~~~java
RunningTotalProcessor singleton = new RunningTotalProcessor();
topology.addProcessor(
        "running-total",
        () -> singleton,
        "orders-source");
~~~

Singleton processor có thể bị nhiều task sử dụng, gây race condition, trộn context và state không đúng partition.

### 11.2. Rebalance và state restoration

Khi instance rời application group hoặc partitions thay đổi assignment, task có thể được chuyển sang instance khác. Kafka Streams sẽ phục hồi state store từ local state/changelog theo cơ chế của framework.

Processor phải đặt state bền vững trong store, không giữ state nghiệp vụ chỉ trong field Java. Field processor có thể dùng để cache reference tới context/store, nhưng không phải nơi duy nhất giữ trạng thái cần sống qua rebalance.

## 12. Exactly-once và side effect bên ngoài

Kafka Streams có thể cấu hình processing guarantee:

~~~java
props.put(
        StreamsConfig.PROCESSING_GUARANTEE_CONFIG,
        StreamsConfig.EXACTLY_ONCE_V2);
~~~

Với exactly-once v2, Kafka Streams phối hợp output Kafka records, state-store changelog và input offsets trong transaction theo semantics của framework. Điều này giúp tránh output trùng hoặc state/offset lệch trong các trường hợp retry được hỗ trợ.

Guarantee này áp dụng cho phạm vi xử lý Kafka Streams được quản lý. Nếu processor gọi trực tiếp database, REST API, gửi email hoặc tạo side effect ngoài Kafka, các thao tác đó không tự nằm trong Kafka transaction. Cần outbox/inbox, idempotency key hoặc một cơ chế transaction riêng ở hệ thống đích.

Không gọi API ngoài đồng bộ trong process() nếu có thể tránh. Network call chậm sẽ chặn task thread, làm tăng processing latency và có thể gây rebalance khi timeout/processing interval liên quan bị vượt. Nếu bắt buộc tích hợp ngoài, thiết kế retry, timeout, concurrency, ordering và idempotency riêng.

## 13. Kiểm thử Processor API bằng TopologyTestDriver

**TopologyTestDriver** cho phép chạy topology trong test mà không cần broker thật. Nó phù hợp để kiểm tra logic processor, state store, routing và output record một cách xác định.

Ví dụ JUnit:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.TestInputTopic;
import org.apache.kafka.streams.TestOutputTopic;
import org.apache.kafka.streams.TopologyTestDriver;
import org.junit.jupiter.api.Test;

class RunningTotalProcessorTest {

    @Test
    void shouldAccumulateValuesPerKey() {
        Properties props = new Properties();
        props.put(StreamsConfig.APPLICATION_ID_CONFIG, "running-total-test");
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "dummy:9092");

        try (TopologyTestDriver driver =
                     new TopologyTestDriver(buildTopology(), props)) {

            TestInputTopic<String, Long> input =
                    driver.createInputTopic(
                            "orders",
                            Serdes.String().serializer(),
                            Serdes.Long().serializer());

            TestOutputTopic<String, Long> output =
                    driver.createOutputTopic(
                            "order-totals",
                            Serdes.String().deserializer(),
                            Serdes.Long().deserializer());

            Instant t1 = Instant.parse("2026-11-20T10:00:00Z");
            input.pipeInput("order-1", 100L, t1);
            input.pipeInput("order-2", 50L, t1.plusSeconds(1));
            input.pipeInput("order-1", 25L, t1.plusSeconds(2));

            List<Long> values = output.readValuesToList();
            assertThat(values).containsExactly(100L, 50L, 125L);
        }
    }
}
~~~

Trong ví dụ, **buildTopology()** trả topology đã khai báo source, processor, store và sink như phần 5. Test dùng serializer/deserializer rõ ràng để tránh phụ thuộc default Serdes.

### 13.1. Test những tình huống nào?

- Record hợp lệ cập nhật state và tạo output đúng.
- Record null key/value được xử lý theo policy.
- Nhiều key không làm lẫn state.
- Event duplicate/version cũ không tạo side effect sai.
- Header/timestamp được giữ hoặc thay đổi đúng.
- Punctuation chạy đúng với stream time hoặc wall-clock test driver.
- State store restore/reopen theo kịch bản test phù hợp.
- Record đi đúng sink/branch.

TopologyTestDriver không mô phỏng đầy đủ broker replication, network failure, group rebalance, transaction coordinator hoặc database CDC. Cần integration test với Kafka thật/Testcontainers cho những hành vi đó.

## 14. Quan sát và debug topology

Có thể in mô tả topology:

~~~java
System.out.println(topology.describe());
~~~

Kiểm tra:

- Source topic và deserializer.
- Thứ tự processor nodes.
- State store được gắn với processor nào.
- Repartition topics có được tạo đúng không.
- Sink topic và serializer.
- Các nhánh có node downstream đúng không.

Monitoring nên bao gồm:

| Nhóm | Chỉ số cần quan sát |
|---|---|
| Stream threads | Thread state, uncaught exception, thread replacement |
| Tasks | Active/standby tasks, task migration, restoration duration |
| Processing | Records consumed/produced, process latency, skipped records |
| State stores | Restore rate, changelog lag, store size, cache hit/write behavior |
| Punctuation | Callback duration, callback failures, thời gian trễ so với lịch |
| Kafka | Consumer lag, producer errors, repartition/changelog topic health |
| Application | Business validation failures, late events, version gaps, duplicate count |

Không chỉ nhìn consumer lag. Một processor có thể đọc record nhanh nhưng thực hiện CPU work lâu, giữ state tăng liên tục hoặc phát output chậm. Đo cả throughput, process latency và state restoration.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| getStateStore trả null hoặc lỗi | Store chưa được add hoặc tên không khớp | Gắn store bằng addStateStore và kiểm tra đúng tên |
| State của key bị phân tán | Input chưa repartition theo key cần aggregate | selectKey/repartition trước processor hoặc thiết kế topic key phù hợp |
| State mất sau restart | State chỉ lưu trong field Java hoặc changelog bị vô hiệu hóa/mất | Dùng state store có logging và bảo vệ changelog |
| Task lỗi khi rebalance | Supplier trả singleton hoặc processor giữ mutable global state | Trả instance mới từ supplier; state nghiệp vụ đặt trong store |
| Không thấy output | Chưa gọi forward, thiếu sink/child hoặc nhánh không được nối | Kiểm tra topology và routing |
| Punctuation không chạy khi topic idle | Dùng STREAM_TIME nhưng stream time không tiến | Chọn wall-clock nếu nghiệp vụ thực sự dựa vào đồng hồ |
| Punctuation trễ | Callback tốn thời gian hoặc task bận | Giảm batch, tối ưu store scan và callback |
| Record output mất header/timestamp | Tạo Record mới mà không copy metadata | Dùng withValue hoặc truyền key/timestamp/headers có chủ đích |
| Throughput không tăng khi thêm thread | Số input partitions/task không đủ hoặc connector/source bottleneck | Kiểm tra partition count, task count và bottleneck |
| Test pass nhưng production lỗi | Chưa test broker/rebalance/transaction/network | Bổ sung integration và failure tests |

## 16. Checklist chọn DSL hay Processor API

Trước khi chọn Processor API, trả lời:

1. DSL có operator tiêu chuẩn diễn đạt được logic không?
2. Có cần truy cập record metadata/headers hoặc forward tùy chỉnh không?
3. Có state store đặc thù hoặc nhiều state transition không?
4. Có cần punctuation theo stream time/wall-clock không?
5. Có thể giữ ordering theo key và partition như thế nào?
6. State có thể restore từ changelog sau rebalance không?
7. Processor có side effect bên ngoài không; nếu có, idempotency ra sao?
8. Có thể test logic bằng TopologyTestDriver và test failure bằng broker thật không?

Chọn DSL nếu pipeline chủ yếu là phép biến đổi/aggregation/join chuẩn. Chọn Processor API nếu cần điều khiển record/state ở mức thấp. Kết hợp hai API nếu chỉ một vài bước đặc biệt cần custom processor.

## 17. Bài thực hành và tự kiểm tra

### Thực hành A — Xây dựng processor stateful

1. Tạo topic orders có key customerId và value là số tiền.
2. Xây dựng RunningTotalProcessor dùng KeyValueStore.
3. Repartition theo customerId nếu input chưa có key này.
4. Forward tổng hiện tại sang customer-totals.
5. Gửi nhiều record của cùng customer và kiểm tra state được cộng dồn.
6. Gửi record của customer khác và xác nhận state độc lập.

### Thực hành B — Punctuation và timeout

1. Xây dựng store lưu thời điểm event cuối cùng theo order.
2. Schedule punctuation bằng STREAM_TIME.
3. Tạo order không có event tiếp theo và quan sát timeout behavior.
4. Thử topic idle để xác nhận stream time không tiến.
5. Chuyển sang WALL_CLOCK_TIME trong lab và so sánh.
6. Định nghĩa chính sách late event và duplicate trước khi phát timeout event.

### Thực hành C — Kiểm thử topology

1. Dùng TopologyTestDriver tạo input/output topics.
2. Kiểm tra state update, output key/value và timestamp.
3. Kiểm tra routing record hợp lệ và không hợp lệ.
4. Kiểm tra punctuation và event-time edge cases.
5. Chạy integration test với Kafka để xác minh state restoration, changelog và rebalance.

### Câu hỏi tự kiểm tra

1. DSL và Processor API khác nhau ở mức trừu tượng nào?
2. Khi nào nên dùng DSL thay vì viết processor tùy chỉnh?
3. ProcessorSupplier có vai trò gì?
4. Vì sao không được dùng một processor singleton cho nhiều task?
5. Record.withValue() giữ lại những metadata nào?
6. ProcessorContext.forward() làm gì?
7. State store gắn với task và partition như thế nào?
8. Changelog topic giúp phục hồi state ra sao?
9. STREAM_TIME khác WALL_CLOCK_TIME ở đâu?
10. Vì sao stream-time punctuation có thể không chạy khi input partition idle?
11. Vì sao đổi key hoặc tăng partition có thể ảnh hưởng ordering/state locality?
12. Exactly-once v2 của Kafka Streams có bao gồm REST API hoặc database side effect không?
13. TopologyTestDriver kiểm thử được gì và không thay thế loại test nào?

## Kết luận

Kafka Streams DSL nên là lựa chọn đầu tiên cho các phép filter, map, join, window và aggregation chuẩn. Processor API phù hợp khi cần điều khiển record, metadata, state store, routing hoặc punctuation ở mức thấp. Khi triển khai, dùng Processor API hiện đại, tạo processor instance riêng cho mỗi task, đặt state nghiệp vụ trong store có changelog, kiểm soát key/partition để giữ ordering và kiểm thử topology bằng TopologyTestDriver. Với side effect bên ngoài Kafka, vẫn cần transaction hoặc idempotency riêng; exactly-once của Kafka Streams không tự mở rộng sang database hay API ngoài.

## Tài liệu tham khảo

- [Apache Kafka 4.1 — Processor API](https://kafka.apache.org/41/streams/developer-guide/processor-api/)
- [Apache Kafka 4.1 — DSL API](https://kafka.apache.org/41/streams/developer-guide/dsl-api/)
- [Apache Kafka 4.1 — State Stores](https://kafka.apache.org/41/streams/developer-guide/processor-api/#state-stores)
- [Apache Kafka 4.1 — Testing Kafka Streams](https://kafka.apache.org/41/streams/developer-guide/testing/)
- [Apache Kafka 4.1 — Streams Configuration](https://kafka.apache.org/41/streams/developer-guide/config-streams/)
