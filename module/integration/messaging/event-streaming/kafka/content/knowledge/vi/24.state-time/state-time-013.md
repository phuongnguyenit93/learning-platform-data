# Kiểm soát kích thước state store và xử lý key lệch

Kafka Streams lưu trạng thái cục bộ để thực hiện các phép aggregate, count, join, window và deduplicate. Khi số lượng key tăng hoặc một vài key nhận phần lớn lưu lượng, state store có thể chiếm nhiều RAM/đĩa, task xử lý chậm và thời gian khôi phục sau rebalance kéo dài.

Để vận hành ổn định, cần phân biệt hai vấn đề:

- **State store quá lớn**: có quá nhiều key, cửa sổ lưu quá lâu, value quá nặng hoặc dữ liệu cũ không được dọn.
- **Key skew (lệch key)**: một vài key nhận lượng record vượt trội, khiến một partition/task trở thành điểm nóng dù tổng state store chưa lớn.

Hai vấn đề có thể xuất hiện cùng lúc nhưng cách xử lý khác nhau. Giảm retention giúp giới hạn state theo thời gian; salting và aggregate nhiều tầng giúp phân tán tải của hot key. Tăng số partition hoặc worker chỉ hữu ích khi cách phân phối key và topology cho phép tận dụng tài nguyên mới.

## 1. State store trong Kafka Streams

State store là nơi Kafka Streams lưu dữ liệu cần giữ qua nhiều record. Ví dụ:

- count() lưu số lượng record theo key.
- aggregate() lưu kết quả tổng hợp theo key.
- reduce() lưu kết quả gộp.
- Windowed aggregation lưu kết quả theo key và time window.
- Join có state store để giữ dữ liệu hai phía trong khoảng thời gian cần thiết.
- Deduplication lưu dấu event đã xử lý để nhận diện bản tin lặp.

Với topology stateless như filter/map/mapValues, ứng dụng không cần store để nhớ trạng thái giữa các record. Khi chuyển sang aggregate, join hoặc window, Kafka Streams phải duy trì state để tính kết quả tiếp theo.

~~~mermaid
flowchart LR
    IN["Input topic"] --> P["Kafka Streams task"]
    P --> A["Aggregate / Join / Window"]
    A <--> S["Local state store"]
    S --> C["Changelog topic"]
    A --> OUT["Output topic"]
    C --> R["Restore / standby task"]
~~~

State store thường được chia theo task và partition. Một instance Kafka Streams có thể chạy nhiều stream thread; mỗi thread chạy một hoặc nhiều task. Task sở hữu partition input và state store tương ứng. Khi partition được chuyển sang instance khác, state của task có thể được khôi phục từ changelog topic.

### Các loại state store thường gặp

| Loại store | Dữ liệu lưu | Ví dụ sử dụng |
|---|---|---|
| Key-value store | Một giá trị hiện tại cho mỗi key | Count theo customer, trạng thái đơn hàng |
| Window store | Giá trị theo key và time window | Tổng doanh thu mỗi 5 phút |
| Session store | Phiên hoạt động theo key và khoảng inactivity | Session người dùng |
| In-memory store | State nằm trong bộ nhớ tiến trình | State nhỏ, cần độ trễ thấp và có thể tái tạo |
| Persistent store | State trên local disk, thường dùng RocksDB | State lớn hơn RAM, cần phục hồi qua changelog |

Persistent store không có nghĩa dữ liệu chỉ tồn tại trên ổ đĩa local. Kafka Streams thường ghi changelog topic để có thể phục hồi state khi task chuyển máy hoặc local state bị mất. Hãy coi local store là bản làm việc của task và changelog là nguồn phục hồi theo cấu hình.

## 2. State store lớn lên như thế nào?

Dung lượng state phụ thuộc vào số key đang hoạt động, kích thước key/value, số window còn hiệu lực, metadata của store và overhead của RocksDB.

Một ước lượng ban đầu:

\[
S \approx N_k \times (K + V + M) \times W \times F
\]

Trong đó:

- \(N_k\): số key duy nhất đang được giữ.
- \(K\): kích thước trung bình của serialized key.
- \(V\): kích thước trung bình của serialized value.
- \(M\): overhead trung bình cho index, metadata và cấu trúc store.
- \(W\): số phiên bản/window còn được giữ cho mỗi key; với key-value store không có version/window thì gần 1.
- \(F\): hệ số dự phòng cho index, compaction, write amplification và dữ liệu tạm.

Công thức chỉ dùng để lập kế hoạch sơ bộ. RocksDB có thể giữ thêm dữ liệu trong memtable, block cache, SST file và compaction; dung lượng trên đĩa và RAM không bằng nhau.

Ví dụ, 5 triệu customer key, mỗi key/value cùng metadata chiếm trung bình 300 byte:

\[
5{,}000{,}000 \times 300 \approx 1.5\ GB
\]

Đây mới là payload ước lượng. Cần cộng overhead của RocksDB, changelog, cache, compaction và phần dự phòng. Nếu cùng key có 12 window còn hiệu lực, state có thể lớn hơn nhiều lần so với một key-value store thông thường.

Khi lập capacity plan, tách riêng ba ngân sách: local state trên từng Kafka Streams instance, changelog topic trên Kafka broker (có nhân theo replication factor), và dung lượng tạm cho restore/compaction. Không cộng chúng thành một con số RAM duy nhất vì chúng nằm ở các tầng lưu trữ khác nhau.

### Những nguyên nhân làm state tăng

- Dữ liệu có cardinality cao: mỗi event tạo một key mới.
- Window retention quá dài so với yêu cầu nghiệp vụ.
- Grace period lớn khiến window cũ phải chờ thêm thời gian nhận late event.
- Value chứa payload lớn hoặc lưu field không cần thiết.
- Deduplication store giữ event ID quá lâu.
- Session store có quá nhiều session chưa hết hạn.
- Topic đầu vào có key không ổn định, làm cùng một entity bị phân thành nhiều key.
- Nhiều state store cùng lưu lại dữ liệu gần giống nhau.

Không phải state store lớn nào cũng là lỗi. Nếu nghiệp vụ cần lịch sử trong một khoảng thời gian xác định, state cần đủ dung lượng để đáp ứng. Mục tiêu là state có giới hạn và tăng trưởng có thể dự đoán.

## 3. Phân biệt high cardinality và hot key

Hai kiểu tải lệch thường bị nhầm lẫn:

| Đặc điểm | High cardinality | Hot key / key skew |
|---|---|---|
| Dấu hiệu | Rất nhiều key duy nhất | Một vài key nhận phần lớn record |
| Tác động chính | State store lớn, nhiều entry, nhiều disk I/O | Một task/partition quá tải |
| Số partition | Có thể phân phối tương đối đều nếu key tốt | Tăng partition không tách một key đơn lẻ |
| Hướng xử lý | Giảm key cardinality, retention, payload, window | Phân mảnh key, pre-aggregate, xử lý nhiều tầng |
| Ví dụ | Mỗi request ID tạo một entry dedup | Một customer hoặc merchant phát sinh phần lớn event |

Ví dụ:

- Một triệu user, mỗi user gửi 10 event/ngày: cardinality cao nhưng tải có thể phân bố đều.
- Một merchant nhận 40% toàn bộ event: hot key, dù tổng số merchant chỉ vài nghìn.

High cardinality chủ yếu làm store lớn. Hot key chủ yếu làm một task xử lý nhiều record hơn các task khác; store của hot key có thể chỉ có một entry nhưng entry đó được cập nhật liên tục.

## 4. Đo dung lượng và phát hiện store tăng bất thường

Không nên đợi worker hết disk hoặc bị OOM mới xử lý. Hãy theo dõi theo từng instance, thread, task và store:

- Kích thước thư mục state.dir và từng task directory.
- Dung lượng RocksDB/SST file và block cache.
- Số entry/key ước lượng trong store.
- Tốc độ put, get, delete, flush và compaction.
- Tỷ lệ state restore và thời gian restore.
- Changelog topic throughput, lag và dung lượng.
- Số lượng window/session còn hiệu lực.
- Số partition/task và phân bố record giữa các partition.

Kafka Streams xuất metrics qua JMX và metrics recording API. Tên metric cụ thể thay đổi theo phiên bản và loại store; hãy lọc theo scope state-store, stream-thread, task và rocksdb nếu phiên bản cung cấp. Không dựa vào một metric tổng duy nhất để kết luận store đã đầy.

### Phân biệt disk, cache và state logic

| Số đo | Cho biết điều gì | Không thể kết luận trực tiếp |
|---|---|---|
| Disk usage của state directory | Dung lượng local store và file liên quan | Số key logic chính xác |
| RocksDB block cache | Block đang được cache trong RAM | Tổng dung lượng store |
| Changelog topic size | Dữ liệu phục hồi được lưu trên Kafka | Local store size tại một thời điểm |
| Restore lag/time | Chi phí phục hồi state | Mức độ skew của key hiện tại |
| Input records per partition | Lưu lượng phân bố theo partition | Số key duy nhất của partition |

Để phát hiện hot key, cần histogram theo key hoặc theo nhóm key. Có thể lấy mẫu ở producer, dùng metrics nghiệp vụ theo customer/merchant hoặc chạy một topology phân tích riêng. Tránh log mọi key trong production vì có thể tạo thêm tải và làm lộ dữ liệu nhạy cảm.

## 5. Giới hạn state bằng window size, grace và retention

Windowed aggregation thường là nguồn state tăng nhanh nhất. Ba khái niệm cần phân biệt:

- **Window size**: khoảng thời gian dữ liệu được gom vào cùng một window.
- **Grace period**: thời gian cho phép record đến trễ sau khi window kết thúc.
- **Retention**: thời gian state store giữ window để truy vấn/khôi phục trước khi có thể dọn.

Với time window, retention phải đủ lớn để bao phủ window và grace theo yêu cầu của Kafka Streams. Không đặt retention ngắn hơn khoảng thời gian cần nhận late event hoặc truy vấn kết quả.

Ví dụ đếm số đơn hàng theo customer trong các cửa sổ 5 phút, cho phép event đến trễ 1 phút:

~~~java
KTable<Windowed<String>, Long> orderCounts =
    orders
        .groupByKey(Grouped.with(Serdes.String(), orderSerde))
        .windowedBy(
            TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)
            )
        )
        .count(
            Materialized
                .<String, Long, WindowStore<Bytes, byte[]>>as(
                    "orders-count-by-customer"
                )
                .withKeySerde(Serdes.String())
                .withValueSerde(Serdes.Long())
                .withRetention(Duration.ofMinutes(30))
        );
~~~

Retention 30 phút trong ví dụ là lựa chọn minh họa, lớn hơn window 5 phút cộng grace 1 phút. Giá trị thực tế phải dựa vào thời gian truy vấn kết quả, yêu cầu late event, khả năng phục hồi và chính sách lưu trữ.

Đoạn code minh họa cần các import tương ứng từ java.time, org.apache.kafka.common.utils.Bytes, org.apache.kafka.streams.kstream và org.apache.kafka.streams.state, cùng orderSerde được định nghĩa trong ứng dụng. Nếu store được query bằng Interactive Queries, retention cũng phải bao phủ thời gian mà API cần trả lời truy vấn.

Nếu chỉ cần tổng hợp trong 5 phút gần nhất, giữ window hàng ngày hoặc hàng tuần có thể lãng phí disk. Ngược lại, nếu báo cáo cần truy vấn lại window trong nhiều giờ, retention quá ngắn sẽ làm mất state cần thiết.

### Grace không phải retention

Grace quyết định khi nào window được coi là đã đóng đối với event-time processing. Retention quyết định state của window được giữ bao lâu trong store. Tăng grace thường làm tăng thời gian một window còn cần được duy trì, nhưng không nên coi hai cấu hình là một.

Record đến muộn hơn grace có thể bị loại khỏi phép aggregate theo window. Hãy theo dõi dropped late records và xác nhận timestamp extractor đang đọc đúng event time.

## 6. Giới hạn state cho key-value store và deduplication

Key-value store không tự hết hạn chỉ vì key đã lâu không được cập nhật. Nếu nghiệp vụ cần TTL, phải thiết kế cơ chế xóa/expire:

- Dùng window store nếu dữ liệu có vòng đời theo thời gian.
- Dùng punctuator hoặc processor API để quét và xóa entry hết hạn.
- Lưu timestamp hết hạn trong value để xác định entry cần xóa.
- Dùng tombstone/update phù hợp khi state được phát ra changelog.

Ví dụ logic TTL:

~~~java
record DedupEntry(long expiresAtMs) {}

// Ý tưởng: khi xử lý event, lưu eventId -> expiresAtMs.
// Một punctuator định kỳ quét các entry đã hết hạn và xóa khỏi store.
if (entry.expiresAtMs() <= context.currentSystemTimeMs()) {
    store.delete(eventId);
}
~~~

Đây là đoạn logic minh họa, không phải processor hoàn chỉnh. Với store lớn, không quét toàn bộ key mỗi giây vì chi phí scan sẽ tăng theo cardinality. Có thể dùng window store, index theo expiry bucket hoặc chia nhỏ lịch quét theo partition/range.

Nếu dùng persistent key-value store cho deduplication, hãy xác định rõ thời gian một event ID cần được nhớ. TTL 7 ngày và TTL 90 ngày có thể tạo khác biệt rất lớn về số entry, disk và changelog traffic.

## 7. Giảm kích thước value và số store

Một state entry nên chỉ lưu dữ liệu cần thiết cho phép tính hoặc truy vấn.

Ví dụ không nên lưu toàn bộ Order JSON 20 KB nếu aggregate chỉ cần customer ID và tổng tiền. Có thể lưu một cấu trúc nhỏ:

~~~java
record CustomerTotals(long orderCount, long amountCents) {}
~~~

Các hướng giảm footprint:

- Chỉ giữ field cần cho aggregation/join.
- Chuẩn hóa key và tránh key có chuỗi dài không cần thiết.
- Dùng kiểu số phù hợp thay cho decimal/string nếu domain cho phép.
- Tránh lặp lại metadata lớn trong mọi state value.
- Hợp nhất các store có cùng lifecycle nếu topology và semantics cho phép.
- Xóa store/branch không còn được sử dụng khi refactor topology.
- Chọn Avro/Protobuf hoặc serializer gọn nếu phù hợp schema.

Không hy sinh tính đúng đắn chỉ để giảm byte. Ví dụ, bỏ currency code khi tổng hợp nhiều loại tiền có thể làm sai kết quả nghiệp vụ.

## 8. Cache state store

Kafka Streams có cache cho state store. Cache có thể gom nhiều lần cập nhật cùng key trước khi flush xuống store/changelog, giảm write amplification và số record changelog. Cache không làm giảm số key logic mà store cần giữ.

Cấu hình dung lượng cache cần kiểm tra theo phiên bản Kafka Streams đang dùng. Các phiên bản có thể sử dụng tên cấu hình mới statestore.cache.max.bytes; các phiên bản cũ có cấu hình cache.max.bytes.buffering. Không copy tên property giữa các major version mà chưa kiểm tra tài liệu client tương ứng.

Ví dụ cấu hình theo Kafka Streams phiên bản hỗ trợ statestore.cache.max.bytes:

~~~java
Properties props = new Properties();
props.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "orders-state-app"
);
props.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
props.put("statestore.cache.max.bytes", 64L * 1024 * 1024);
~~~

Đoạn code cần import java.util.Properties và org.apache.kafka.streams.StreamsConfig.

Cache được chia sẻ theo phạm vi instance theo cơ chế của Kafka Streams; đây không phải ngân sách RAM riêng cho từng store. Khi tăng cache, hãy tính cả heap, RocksDB block cache, thread stack, producer/consumer buffers và ứng dụng chạy cùng JVM.

Cache quá nhỏ có thể làm tăng flush/changelog write. Cache quá lớn có thể tạo áp lực heap và GC. Đo throughput, latency, heap usage và store write rate trước/sau khi thay đổi.

## 9. RocksDB và local disk

Persistent state store mặc định của Kafka Streams thường dùng RocksDB. RocksDB lưu dữ liệu theo log-structured merge tree (LSM): ghi vào memtable, flush thành SST file, sau đó compaction hợp nhất các file.

Đặc điểm cần lưu ý:

- Ghi tuần tự và compaction giúp xử lý state lớn hơn RAM.
- Đọc có thể cần truy cập nhiều level nếu cache không hiệu quả.
- Compaction tạo I/O và dung lượng tạm trong lúc hợp nhất file.
- Disk latency, IOPS và dung lượng trống ảnh hưởng trực tiếp đến task.
- Nhiều store/task trên một instance cùng cạnh tranh CPU, RAM và disk.

Đặt state.dir trên volume có dung lượng và IOPS phù hợp:

~~~properties
state.dir=/var/lib/kafka-streams
num.stream.threads=4
num.standby.replicas=1
replication.factor=3
~~~

Các giá trị trên chỉ là ví dụ. state.dir phải có quyền ghi, đủ dung lượng cho local state, changelog restore và compaction tạm thời. Không đặt state store trên filesystem tạm nếu workload không chấp nhận thời gian restore sau restart.

### Tùy chỉnh RocksDB

Kafka Streams cho phép dùng RocksDBConfigSetter qua cấu hình rocksdb.config.setter để điều chỉnh options như write buffer, block cache và table format. Đây là tối ưu cấp thấp; cấu hình sai có thể làm tăng RAM, disk I/O hoặc giảm hiệu năng.

~~~java
public final class AppRocksDbConfig implements RocksDBConfigSetter {

    @Override
    public void setConfig(
            String storeName,
            Options options,
            Map<String, Object> configs) {

        options.setWriteBufferSize(16L * 1024 * 1024);
        options.setMaxWriteBufferNumber(3);
    }

    @Override
    public void close(String storeName, Options options) {
        // Giải phóng resource do setter tự tạo nếu có.
    }
}
~~~

Đây là ví dụ tối giản; cần import org.rocksdb.Options, org.apache.kafka.streams.state.RocksDBConfigSetter và java.util.Map cùng cấu hình class đầy đủ. Nếu tạo RocksDB Cache hoặc Filter native, phải quản lý vòng đời và giải phóng đúng cách; không tạo một native cache mới cho mỗi store mà không có ngân sách RAM.

Khai báo class:

~~~properties
rocksdb.config.setter=com.example.streams.AppRocksDbConfig
~~~

Trước khi tùy chỉnh, hãy đo baseline. Không tăng write buffer hoặc block cache theo cảm tính; mỗi task/store có thể tạo nhiều native resource và làm tổng RAM vượt dự kiến.

## 10. Changelog topic, restore và standby replica

State store có thể được khôi phục từ changelog topic. Khi task chuyển sang instance khác, Kafka Streams đọc changelog để tái tạo state local. Store lớn hoặc changelog có nhiều dữ liệu sẽ kéo dài thời gian restore.

Các cấu hình cần quan tâm:

| Cấu hình | Tác dụng |
|---|---|
| application.id | Định danh ứng dụng, consumer group và namespace state/internal topics |
| state.dir | Thư mục local lưu state store |
| replication.factor | Replication factor cho internal topics do Kafka Streams tạo |
| num.standby.replicas | Số standby task giữ bản state cập nhật từ changelog |
| commit.interval.ms | Chu kỳ commit/flush theo semantics và cấu hình ứng dụng |

Trong production, internal changelog/repartition topic cần replication factor phù hợp với độ bền mong muốn và số broker. Đừng để replication factor thấp chỉ vì môi trường dev dùng một broker.

num.standby.replicas có thể giảm thời gian failover vì standby task đã duy trì state gần nhất. Đổi lại, standby tiêu tốn CPU, disk và network trên instance khác. Standby replica là bản state của task; nó khác Kafka partition replica và không thay thế replication factor của changelog topic.

Giữ application.id ổn định qua restart của cùng một ứng dụng để Kafka Streams nhận diện đúng group và state. Đổi application ID có thể tạo một ứng dụng mới với internal topics và state namespace khác, dẫn đến đọc lại dữ liệu hoặc tạo thêm state.

## 11. Nhận diện key skew trong topology

Kafka partitioner thường định tuyến record có key dựa trên hash của key. Vì vậy, mọi record có cùng key sẽ đi về cùng partition của topic theo partitioning scheme hiện tại.

Ví dụ một topic 12 partition:

~~~text
partition 0:  8% records
partition 1:  7% records
partition 2:  9% records
partition 3:  8% records
partition 4:  7% records
partition 5:  8% records
partition 6:  8% records
partition 7:  7% records
partition 8:  8% records
partition 9:  8% records
partition 10: 8% records
partition 11: 14% records
~~~

Phân bố 14% so với khoảng 8% có thể là chênh lệch nhỏ hoặc đáng điều tra tùy throughput. Nếu một partition nhận 50% record, đây là dấu hiệu skew mạnh.

Để chẩn đoán:

1. So sánh records/bytes in per partition.
2. So sánh process latency, task busy time và consumer lag theo task.
3. Lấy mẫu key có tần suất cao từ producer hoặc pipeline quan sát.
4. Kiểm tra các key mặc định như UNKNOWN, GLOBAL hoặc ALL vì chúng có thể gom nhiều record vào một partition. Kiểm tra riêng key null: tùy operator, record không có key có thể bị bỏ qua trong phép grouping thay vì trở thành một hot key.
5. Kiểm tra một customer/merchant có phát sinh lưu lượng bất thường không.
6. Kiểm tra sau selectKey, map hoặc groupBy key có bị gom về một giá trị chung không.

Đừng chỉ nhìn tổng throughput của toàn ứng dụng. Một instance có thể còn CPU rảnh trong khi task chứa hot partition đã bão hòa.

## 12. Vì sao tăng partition hoặc stream thread không luôn giải quyết được hot key?

Tăng số partition giúp phân phối nhiều key khác nhau trên nhiều partition hơn. Nhưng nếu một key duy nhất chiếm 40% traffic, tất cả record mang key đó vẫn được định tuyến đến cùng partition theo cùng partitioner.

Tương tự, tăng num.stream.threads chỉ tăng khả năng chạy nhiều task song song. Một task xử lý một partition input cụ thể vẫn bị giới hạn bởi một luồng xử lý của task; thêm thread không chia một key nóng thành nhiều task độc lập.

Tăng partition có thể còn làm thay đổi mapping key-to-partition đối với record mới, gây thay đổi thứ tự quan sát khi cùng entity chuyển sang partition khác. Cần đánh giá ordering và state migration trước khi tăng partition của topic đang hoạt động.

Tăng số worker có ích khi có nhiều task chưa được phân phối đủ tài nguyên. Nó không tự chia nhỏ stateful operation của một key duy nhất.

## 13. Salting key để phân tán tải

Một cách phổ biến để xử lý hot key là thêm salt/bucket vào key. Thay vì gom mọi event của customer customer-7 vào một key, chia thành nhiều key:

~~~text
customer-7#0
customer-7#1
customer-7#2
...
customer-7#15
~~~

Bucket có thể được tính bằng hash của event ID/order ID:

~~~java
private static int bucketFor(String stableId, int bucketCount) {
    return Math.floorMod(stableId.hashCode(), bucketCount);
}

KStream<String, Payment> bucketed =
    payments.selectKey((key, payment) ->
        payment.customerId()
            + "#" + bucketFor(payment.paymentId(), 16)
    );
~~~

Các event của cùng customer được phân tán trên tối đa 16 bucket, giúp stage đầu aggregate song song. Dùng ID ổn định để cùng một event replay vẫn đi vào cùng bucket; không dùng random salt nếu cần idempotency.

### Salting thay đổi semantics

Sau khi salt key, state store không còn một entry cho mỗi customer mà có thể có 16 entry cho mỗi customer. Nếu cần kết quả tổng theo customer, phải có bước tổng hợp tiếp theo.

~~~mermaid
flowchart LR
    IN["Payment events<br/>customer-7"] --> SALT["Add bucket to key"]
    SALT --> P["Repartition"]
    P --> A["Partial aggregate<br/>customer-7#0..15"]
    A --> M["Merge partial results"]
    M --> OUT["Total by customer"]
~~~

Số bucket phải được chọn theo partition count, throughput và chi phí state. Nếu topic/repartition chỉ có 4 partition thì 16 bucket key không tạo được 16 task song song. Có thể cấu hình số partition cho repartition topic nếu API/phiên bản hỗ trợ.

Salting làm mất thứ tự toàn cục giữa các event của cùng customer vì chúng có thể đi vào các bucket/partition khác nhau. Chỉ áp dụng khi phép tính có thể kết hợp và không cần một chuỗi xử lý tuần tự duy nhất cho customer đó.

## 14. Aggregate hai tầng đúng cách

Ví dụ dưới đây minh họa ý tưởng:

1. Tạo key customerId#bucket.
2. Repartition theo key đã salt.
3. Đếm payment theo từng bucket.
4. Gom các partial count về customer.

~~~java
KStream<String, Payment> bucketed = payments
    .selectKey((key, payment) ->
        payment.customerId()
            + "#" + bucketFor(payment.paymentId(), BUCKET_COUNT)
    )
    .repartition(
        Repartitioned
            .with(Serdes.String(), paymentSerde)
            .withNumberOfPartitions(BUCKET_COUNT)
    );

KTable<String, Long> partialCounts = bucketed
    .groupByKey(Grouped.with(Serdes.String(), paymentSerde))
    .count(
        Materialized
            .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                "payment-count-by-customer-bucket"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
    );

KTable<String, Long> totalByCustomer = partialCounts
    .groupBy(
        (bucketKey, partialCount) -> KeyValue.pair(
            customerIdFromBucketKey(bucketKey),
            partialCount
        ),
        Grouped.with(Serdes.String(), Serdes.Long())
    )
    .aggregate(
        () -> 0L,
        (customerId, newPartial, total) -> total + newPartial,
        (customerId, oldPartial, total) -> total - oldPartial,
        Materialized
            .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                "payment-count-by-customer"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
    );
~~~

Đây là mẫu minh họa cho KTable aggregation: khi partial count của một bucket thay đổi, phép aggregate nhóm cần cộng giá trị mới và trừ giá trị cũ. Không chuyển partialCounts.toStream() rồi cộng dồn mọi giá trị như event delta; KTable phát changelog của giá trị hiện tại, không phải chỉ phần chênh lệch.

customerIdFromBucketKey() phải parse format key có quy tắc rõ ràng, không dùng delimiter có thể xuất hiện trong customer ID nếu không escape. Trong code production nên dùng composite key có SerDe riêng thay cho ghép chuỗi.

Đoạn code giả định BUCKET_COUNT, Payment, paymentSerde, customerIdFromBucketKey() và các import Kafka Streams/SerDes đã được định nghĩa. Nếu paymentId có thể lặp do retry/replay, cần deduplicate hoặc dùng event ID idempotent trước khi count để tránh đếm trùng.

Các store Materialized trong ví dụ dùng KeyValueStore; cần import org.apache.kafka.common.utils.Bytes và org.apache.kafka.streams.state.KeyValueStore. Nếu muốn kiểm soát cấu hình changelog, có thể dùng Materialized.withLoggingEnabled(...) với các topic config phù hợp; không tắt logging cho state cần khôi phục sau lỗi nếu chưa có cơ chế rebuild thay thế.

### Giới hạn của hai tầng

Stage đầu phân tán việc tính toán và lưu partial state. Stage cuối vẫn gom partial state theo customer, nên customer đó vẫn có một key ở stage cuối. Bản thân KTable count có thể phát một cập nhật partial cho mỗi payment; do đó hai tầng không tự động giảm số update ở stage cuối. Cache có thể gộp nhiều cập nhật cùng key trong một chu kỳ flush, hoặc ứng dụng có thể batch/emit partial theo chu kỳ. Nếu không giảm được tần suất update, stage cuối vẫn có thể nóng; khi đó cân nhắc giữ state theo bucket và tổng hợp khi truy vấn.

Salting không phù hợp nếu nghiệp vụ bắt buộc xử lý tuần tự từng event theo một customer trên một state machine. Trong trường hợp đó, hot key là ràng buộc của mô hình dữ liệu; cần cân nhắc partition theo entity khác, tách workload hoặc chấp nhận một điểm tuần tự hóa.

## 15. Các chiến lược khác để giảm key skew

| Chiến lược | Cách hoạt động | Khi phù hợp | Đánh đổi |
|---|---|---|---|
| Salting/bucketing | Chia một key nóng thành nhiều key con | Aggregate có thể gộp kết quả | Cần merge stage và state lớn hơn |
| Pre-aggregation ở producer | Gom nhiều event thành batch/tổng phụ trước khi gửi | Producer có thể gom theo thời gian | Tăng độ trễ và phức tạp retry |
| Two-stage aggregation | Aggregate song song rồi merge | Count/sum/min/max có tính kết hợp | Stage cuối vẫn có thể nóng |
| Tách hot key | Đưa nhóm key đặc biệt sang topic/topology riêng | Chỉ vài key bất thường | Tăng số luồng vận hành |
| Fan-out đọc | Lưu shard state và tổng hợp khi truy vấn | Chấp nhận kết quả tổng hợp ở read path | Query phức tạp hơn |
| Thay key nghiệp vụ | Phân vùng theo entity độc lập hơn | Có thể đổi semantics | Có thể ảnh hưởng ordering và join |

Chỉ chọn chiến lược sau khi xác định phép aggregate có thể chia nhỏ hay không. Sum/count/min/max thường dễ kết hợp; phép tính phụ thuộc thứ tự, state machine hoặc side effect có thể không kết hợp an toàn.

## 16. Kiểm soát cache, suppression và output

suppress() có thể giữ kết quả cho đến khi window đóng hoặc điều kiện suppression đạt. Nó giúp tránh phát quá nhiều kết quả trung gian, nhưng buffer suppression cũng tiêu thụ tài nguyên và cần cấu hình giới hạn phù hợp.

Ví dụ khái niệm:

~~~java
windowedCounts
    .suppress(
        Suppressed.untilWindowCloses(
            Suppressed.BufferConfig.maxBytes(64L * 1024 * 1024)
        )
    )
    .toStream()
    .to("orders.final-window-counts");
~~~

Đoạn code giả định windowedCounts là KTable có window và chỉ phát kết quả cuối khi window đóng. Buffer giới hạn 64 MiB là giá trị minh họa; nếu buffer đầy, hành vi phụ thuộc loại BufferConfig. Strict buffer có thể làm task fail thay vì âm thầm vượt giới hạn; eager buffer có thể phát sớm và thay đổi semantics. Chọn theo yêu cầu nghiệp vụ.

Không dùng suppression để che một state store không được giới hạn. Window retention, grace, key cardinality và buffer size vẫn cần được tính riêng.

## 17. Runbook khi state store đầy hoặc task bị hot

Khi disk tăng nhanh hoặc task lag bất thường, thực hiện theo thứ tự:

1. Xác định instance, thread, task và store đang chiếm tài nguyên.
2. So sánh disk usage, state-store metrics, RocksDB metrics và changelog size.
3. So sánh input records/bytes theo partition để phát hiện skew.
4. Xác định high cardinality hay hot key; kiểm tra key sample và số key duy nhất.
5. Kiểm tra window size, grace, retention, TTL và payload size.
6. Kiểm tra cache, RocksDB compaction, disk IOPS và dung lượng trống.
7. Kiểm tra restore time, standby replica và changelog replication.
8. Chọn biện pháp: giảm retention/payload, TTL, salting, pre-aggregation hoặc tách workload.
9. Đo lại store size, task latency, lag và restore time sau thay đổi.

Không xóa trực tiếp RocksDB directory khi ứng dụng đang chạy để giải phóng dung lượng. Thao tác đó có thể làm state store không nhất quán; nếu cần xóa local state, dừng ứng dụng và làm theo quy trình reset/restore có kiểm soát, hiểu rõ tác động đến offset và changelog.

## 18. Bài tập tự kiểm tra

1. State store khác cache ở điểm nào?
2. Vì sao high cardinality làm state store lớn dù tải mỗi key thấp?
3. Vì sao một hot key không được chia ra nhiều partition chỉ bằng cách tăng partition count?
4. Phân biệt window size, grace period và retention.
5. Vì sao key-value store cần cơ chế TTL riêng nếu key không còn được cập nhật?
6. Changelog topic giúp khôi phục local state như thế nào?
7. num.standby.replicas giảm thời gian failover bằng cách nào và tốn tài nguyên gì?
8. Salting key thay đổi semantics và ordering ra sao?
9. Vì sao stage merge của KTable phải trừ partial value cũ trước khi cộng value mới?
10. Vì sao suppress() cũng cần giới hạn buffer?

## Kết luận

Kiểm soát state store bắt đầu từ việc hiểu dữ liệu nào cần lưu, có bao nhiêu key, value lớn bao nhiêu và state phải tồn tại trong bao lâu. Window size, grace, retention, TTL, cache, RocksDB, changelog và standby replica tác động đến các phần khác nhau của vòng đời state; không có một cấu hình đơn lẻ giải quyết tất cả.

Key skew cần được đo theo partition/task và key distribution. Tăng partition hoặc stream thread giúp khi có nhiều key độc lập, nhưng không tách một hot key đơn lẻ. Salting, pre-aggregation và aggregate nhiều tầng có thể phân tán tải nếu phép tính có thể kết hợp; đổi lại, state và logic merge phức tạp hơn. Hãy đo trước/sau thay đổi và bảo toàn semantics nghiệp vụ, ordering cùng khả năng phục hồi.
