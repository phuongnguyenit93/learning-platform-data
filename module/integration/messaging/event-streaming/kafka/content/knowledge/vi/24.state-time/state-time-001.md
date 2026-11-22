# State store trong bộ nhớ hoặc trên đĩa

## Mục tiêu bài học

Kafka Streams hỗ trợ xử lý có trạng thái (stateful processing), ví dụ đếm số event theo key, tính tổng doanh thu, giữ trạng thái tài khoản, join hai luồng dữ liệu hoặc gom event theo cửa sổ thời gian. Để thực hiện các phép toán này, ứng dụng cần lưu trạng thái trung gian. Kafka Streams cung cấp State Store để lưu và truy vấn trạng thái đó, thường ở bộ nhớ hoặc trên đĩa cục bộ, đồng thời có thể sao lưu thay đổi lên Kafka changelog topic để phục hồi.

Sau bài học, bạn có thể:

- Giải thích State Store và mối liên hệ giữa task, partition và local state.
- Phân biệt in-memory store, persistent store và changelog-backed fault tolerance.
- Chọn KeyValueStore, WindowStore hoặc SessionStore theo bài toán.
- Khai báo store qua Kafka Streams DSL với `Materialized`.
- Tạo và gắn store thủ công bằng Processor API.
- Hiểu RocksDB, `state.dir`, changelog topic, restore và standby replica.
- Cấu hình retention, caching, logging và replication phù hợp.
- Truy vấn local state và hiểu giới hạn của Interactive Queries.
- Theo dõi dung lượng, restore time, disk, memory và lỗi state store.
- Kiểm thử restart, rebalance, restore và thay đổi schema của state.

## 1. State Store là gì?

Một phép biến đổi stateless xử lý từng record độc lập. Ví dụ đổi chữ thường thành chữ hoa không cần nhớ record trước. Ngược lại, phép xử lý stateful cần giữ thông tin từ các record đã đến:

- Đếm số đơn hàng theo `customerId`.
- Tính tổng tiền theo tài khoản.
- Giữ trạng thái mới nhất của một entity.
- Join stream đơn hàng với bảng khách hàng.
- Tính tổng doanh thu trong 5 phút gần nhất.
- Gom các event thuộc cùng một session người dùng.

State Store là abstraction để Kafka Streams lưu và truy cập dữ liệu trạng thái trong quá trình xử lý. Store được gắn với topology và các task thực thi topology. Mỗi task thường sở hữu một phần state tương ứng với các input partition mà task xử lý.

```text
Input topic: orders (6 partitions)
                 |
                 v
          Kafka Streams topology
                 |
        +--------+--------+
        |        |        |
        v        v        v
      Task 0   Task 1   Task 2
        |        |        |
        v        v        v
   Local store Local store Local store
   partition 0 partition 1 partition 2
        |        |        |
        +--------+--------+
                 |
                 v
       Changelog topic in Kafka
```

Sơ đồ đơn giản hóa việc phân phối task. Một task có thể xử lý nhiều partition và sở hữu nhiều state store; số task thực tế phụ thuộc topology, source topic và repartition topic.

### 1.1. Vì sao không chỉ dùng biến Java hoặc `HashMap`?

Một biến hoặc `HashMap` trong service chỉ tồn tại trong process đó. Nó không tự biết partition nào được chuyển sang instance khác khi rebalance, không có cơ chế restore từ Kafka và không quản lý vòng đời state theo task.

State Store tích hợp với Kafka Streams để:

- Gắn state với task và input partition.
- Lưu dữ liệu cục bộ bằng store implementation phù hợp.
- Ghi changelog để phục hồi state sau lỗi khi logging được bật.
- Chuyển giao task/state khi application instance thay đổi.
- Hỗ trợ các phép toán stateful trong DSL và Processor API.
- Cung cấp API truy vấn state theo store name/type.

### 1.2. State Store không phải Kafka topic

State Store thường được đọc/ghi trực tiếp trong local process khi task xử lý. Changelog topic là bản ghi Kafka dùng để phục hồi và đồng bộ state. Topic nghiệp vụ chứa event đầu vào/đầu ra, còn changelog topic lưu các thay đổi state theo định dạng nội bộ của Kafka Streams.

Không dùng changelog topic như API dữ liệu nghiệp vụ và không chỉnh sửa record trong changelog bằng producer ứng dụng.

## 2. Phân biệt in-memory store và persistent store

Kafka Streams có thể dùng store nằm trong bộ nhớ hoặc store persistent trên đĩa cục bộ.

### 2.1. In-memory State Store

In-memory store giữ key/value trong RAM của process. Ví dụ `Stores.inMemoryKeyValueStore("recent-orders")` tạo một key-value store dựa trên bộ nhớ.

Ưu điểm:

- Truy cập nhanh, tránh chi phí I/O đĩa cho thao tác store cơ bản.
- Cấu trúc đơn giản, phù hợp state nhỏ.
- Không cần quản lý dung lượng file database cục bộ.

Đánh đổi:

- Dung lượng bị giới hạn bởi heap/RAM.
- State mất khi process hoặc máy bị dừng.
- State lớn có thể gây garbage collection, memory pressure hoặc `OutOfMemoryError`.
- Nếu bật changelog, khởi động lại vẫn có thể restore state từ Kafka nhưng cần thời gian và tài nguyên mạng/CPU.

In-memory không có nghĩa state không thể phục hồi. Tính phục hồi phụ thuộc changelog logging và nguồn có thể rebuild state, không chỉ phụ thuộc nơi lưu local.

### 2.2. Persistent State Store

Persistent store lưu state trên đĩa cục bộ. Với Kafka Streams, persistent key-value/window/session store mặc định thường dùng RocksDB làm storage engine (native library). Store giữ dữ liệu qua restart process nếu thư mục local còn tồn tại.

Ưu điểm:

- Có thể lưu state lớn hơn giới hạn heap Java.
- Giảm áp lực giữ toàn bộ state trong Java heap.
- Phù hợp aggregation, join và lookup có state đáng kể.
- Restart cùng máy có thể tái sử dụng local state và giảm lượng dữ liệu cần restore.

Đánh đổi:

- Cần dung lượng đĩa, IOPS và quản lý file.
- Có chi phí serialization, RocksDB compaction và native memory.
- Disk đầy hoặc filesystem chậm có thể làm task dừng hoặc tăng latency.
- Local disk hỏng vẫn cần changelog để phục hồi.

Persistent store không đồng nghĩa state được nhân bản trên nhiều máy. Nó chỉ nói dữ liệu được lưu local trên storage engine persistent.

### 2.3. So sánh

| Tiêu chí | In-memory | Persistent (thường là RocksDB) |
|---|---|---|
| Nơi lưu local | RAM | Disk cục bộ, có cache RAM |
| Dung lượng | Hạn chế bởi bộ nhớ | Hạn chế bởi disk và tài nguyên hệ thống |
| Latency | Thường thấp cho state nhỏ | Có thêm chi phí storage/compaction, cache có thể giảm đọc đĩa |
| Java heap | Có thể tăng theo state | Có thể giữ heap thấp hơn, nhưng vẫn dùng native memory/cache |
| Restart process | Local state mất, thường restore từ changelog nếu bật | Có thể mở lại local state còn tồn tại; restore phần thiếu nếu cần |
| Mất máy/local disk | Cần restore từ changelog hoặc nguồn rebuild | Cần restore từ changelog hoặc nguồn rebuild |
| Phù hợp | State nhỏ, tạm thời, lab | State lớn, ứng dụng production phổ biến |

Không nên chọn store chỉ theo benchmark thao tác `get/put`. Cần đo cả restore, compaction, write amplification, disk throughput, heap/native memory và latency dưới tải thật.

## 3. Persistence và fault tolerance là hai khái niệm khác nhau

Đây là điểm quan trọng nhất khi thiết kế State Store.

- **Local persistence:** state còn trên đĩa sau khi process restart trên cùng máy.
- **Changelog fault tolerance:** thay đổi state được ghi vào Kafka để có thể khôi phục khi local state mất hoặc task chuyển sang instance khác.
- **Rebuild từ source:** ứng dụng có thể tái tạo state bằng cách replay input topic nếu topic còn đủ dữ liệu và topology xác định.

Ba cơ chế này có thể cùng tồn tại nhưng không thay thế nhau.

### 3.1. In-memory store có thể fault-tolerant

Nếu in-memory store bật changelog logging, mỗi thay đổi state được ghi vào changelog topic theo cơ chế Kafka Streams. Khi instance mất, task mới có thể dựng lại store bằng cách đọc changelog. In-memory local copy mất nhưng state logic vẫn có đường phục hồi.

Nếu logging bị tắt và không có nguồn input đủ để rebuild, state có thể mất vĩnh viễn khi process/máy bị mất.

### 3.2. Persistent store vẫn cần changelog

RocksDB giữ state trên local disk, nhưng disk có thể hỏng, pod bị thay thế, volume bị xóa hoặc instance không còn được dùng cho task đó. Changelog cung cấp bản sao có thể replay từ Kafka cluster.

Không nên xem persistent local directory là bản backup duy nhất của state production.

### 3.3. Khi nào tắt changelog?

Có thể tắt logging cho store khi ứng dụng chấp nhận rằng store sẽ được tạo lại từ nguồn khác hoặc store chỉ là cache có thể mất. Ví dụ cache lookup có thể được nạp lại từ database/source topic.

Trước khi tắt logging, trả lời:

1. Nếu mất toàn bộ local state, có nguồn nào dựng lại chính xác không?
2. Input topic còn retention đủ dài để replay không?
3. Rebuild có tạo side effect hoặc output duplicate không?
4. Thời gian rebuild có đáp ứng RTO không?
5. State có chứa thông tin đã bị xóa khỏi source hiện tại không?

Nếu không có câu trả lời rõ ràng, giữ changelog logging.

## 4. Các loại State Store

Kafka Streams cung cấp các abstraction chính cho stateful processing.

### 4.1. KeyValueStore

Lưu một value hiện tại cho mỗi key. Thích hợp:

- Số lượng event theo customer.
- Số dư hiện tại theo account.
- Trạng thái mới nhất theo order ID.
- Aggregation không giới hạn theo thời gian (cho đến khi có tombstone/cleanup riêng).

API khái quát gồm `get(key)`, `put(key, value)`, `delete(key)` và range/all iterator tùy implementation.

### 4.2. WindowStore

Lưu nhiều giá trị theo key và timestamp/window. Thích hợp:

- Đếm event trong 5 phút gần nhất.
- Tính tổng doanh thu theo cửa sổ 1 phút.
- Lưu dữ liệu phục vụ windowed aggregation hoặc query theo thời gian.

Window store có retention để loại bỏ dữ liệu cũ ngoài phạm vi cần giữ. Cần tính cả window size, grace period và yêu cầu truy vấn/replay.

### 4.3. SessionStore

Lưu session theo key, thường được xác định bằng thời gian bắt đầu và kết thúc. Thích hợp gom hoạt động của một user thành session dựa trên khoảng inactivity.

Session window có thể được mở rộng khi event mới đến trong khoảng grace/merge rule. Vì vậy state store cần quản lý nhiều session cho cùng key và khả năng merge session.

### 4.4. Timestamped và versioned stores

Một số API/phiên bản Kafka Streams có store giữ timestamp cùng value hoặc giữ nhiều version theo thời gian, ví dụ `TimestampedKeyValueStore` và `VersionedKeyValueStore`. Chúng phục vụ semantics như truy vấn theo thời điểm hoặc xử lý out-of-order trong một số phép join/table.

Khả năng, retention và API cụ thể phụ thuộc Kafka Streams version. Khi dùng versioned store, hãy kiểm tra yêu cầu version tối thiểu và semantics của DSL operator thay vì giả định nó giống KeyValueStore thông thường.

### 4.5. Chọn loại store

| Bài toán | Store thường phù hợp |
|---|---|
| Một giá trị hiện tại theo key | KeyValueStore |
| Aggregation theo time window | WindowStore |
| Gom hoạt động theo phiên | SessionStore |
| Cần timestamp metadata hoặc version theo thời gian | Timestamped/Versioned store nếu version hỗ trợ |
| Cache nhỏ có thể rebuild | In-memory KeyValueStore, cân nhắc logging disabled |
| State production lớn | Persistent store với changelog |

## 5. Khai báo store trong Kafka Streams DSL

DSL thường tạo state store tự động cho aggregation, join và window operation. Có thể đặt tên và cấu hình store qua `Materialized`.

### 5.1. Đếm event và materialize vào store

```java
StreamsBuilder builder = new StreamsBuilder();

KStream<String, String> events = builder.stream(
    "orders",
    Consumed.with(Serdes.String(), Serdes.String())
);

KTable<String, Long> orderCounts = events
    .groupByKey()
    .count(
        Materialized.<String, Long, KeyValueStore<Bytes, byte[]>>as("order-counts")
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
    );

orderCounts.toStream().to(
    "order-counts-output",
    Produced.with(Serdes.String(), Serdes.Long())
);
```

`Materialized.as("order-counts")` đặt tên cho store. `withKeySerde` và `withValueSerde` chỉ rõ cách serialize key/value của state và changelog. Tên store cần ổn định vì nó có thể tham gia vào tên changelog topic và truy vấn store.

### 5.2. Vì sao `count()` tạo state?

Khi nhận event có key `ORD-101`, Kafka Streams phải đọc count hiện tại, tăng lên rồi lưu lại. State store giữ count mới nhất theo key. Nếu không có store, ứng dụng không thể tính tổng tích lũy qua nhiều record và restart.

`KTable` biểu diễn kết quả cập nhật theo key; output stream từ `toStream()` phát các thay đổi của bảng, không nhất thiết là một bản snapshot đầy đủ ở mỗi event.

### 5.3. Chọn persistent hoặc in-memory store

Với store tự định nghĩa, có thể chọn store supplier. Một số DSL operator tự chọn implementation mặc định; kiểm tra API `Materialized` của version đang dùng khi muốn chỉ định supplier cụ thể.

Ví dụ khai báo store thủ công ở phần Processor API bên dưới cho thấy cách chọn `Stores.inMemoryKeyValueStore()` hoặc `Stores.persistentKeyValueStore()` rõ ràng.

### 5.4. Store name là một phần của contract vận hành

Đổi store name có thể làm Kafka Streams xem đây là store khác, tạo changelog topic mới hoặc cần restore/rebuild state. Không đổi tên store trong một lần refactor đơn giản nếu đang có state production lớn mà chưa lập kế hoạch migration.

Tương tự, đổi `application.id` tạo namespace ứng dụng khác cho consumer group và internal topics. Điều này có thể khiến application mới xử lý lại input và tạo state mới thay vì tiếp tục state cũ.

## 6. Tạo State Store thủ công với Processor API

Khi DSL không đủ linh hoạt, Processor API cho phép định nghĩa processor và truy cập state store trực tiếp.

### 6.1. Tạo persistent store

```java
StoreBuilder<KeyValueStore<String, Long>> countsStore =
    Stores.keyValueStoreBuilder(
        Stores.persistentKeyValueStore("custom-counts"),
        Serdes.String(),
        Serdes.Long()
    );

builder.addStateStore(countsStore);
```

`persistentKeyValueStore` yêu cầu store persistent; Kafka Streams thường dùng RocksDB implementation mặc định. `addStateStore` đăng ký store vào topology.

### 6.2. Chọn in-memory store

Thay supplier bằng:

```java
Stores.inMemoryKeyValueStore("custom-counts")
```

Các phần còn lại như key/value Serde và `addStateStore` giữ nguyên. Nếu bật changelog mặc định cho store builder, in-memory store vẫn có thể được restore từ Kafka.

### 6.3. Processor dùng store

Ví dụ minh họa theo Processor API mới:

```java
public class CountProcessor
        implements Processor<String, String, String, Long> {

    private ProcessorContext<String, Long> context;
    private KeyValueStore<String, Long> store;

    @Override
    public void init(ProcessorContext<String, Long> context) {
        this.context = context;
        this.store = context.getStateStore("custom-counts");
    }

    @Override
    public void process(Record<String, String> record) {
        String key = record.key();
        if (key == null) {
            return;
        }

        Long current = store.get(key);
        long next = current == null ? 1L : current + 1L;
        store.put(key, next);

        context.forward(new Record<>(key, next, record.timestamp()));
    }
}
```

Gắn processor với store:

```java
builder.stream("order-events", Consumed.with(Serdes.String(), Serdes.String()))
    .process(
        CountProcessor::new,
        Named.as("count-orders"),
        "custom-counts"
    )
    .to("order-counts", Produced.with(Serdes.String(), Serdes.Long()));
```

Đây là API Processor mới dùng generic key/value đầu vào và đầu ra. Các version cũ có Processor API khác; không trộn `Processor` cũ với `Processor<KIn,VIn,KOut,VOut>` mới trong cùng ví dụ. Cần dùng API khớp Kafka Streams dependency.

### 6.4. Store được gắn với processor như thế nào?

Tên store truyền vào `process(..., "custom-counts")` phải khớp store đã đăng ký bằng `builder.addStateStore()`. Kafka Streams cấp store cho task/processor theo topology. Không tạo một `HashMap` global để thay thế state store khi cần chia partition và phục hồi.

### 6.5. Vòng đời store

Framework quản lý việc mở, restore, flush và close store theo task lifecycle. Trong Processor API, lấy store trong `init()` sau khi context được cấp. Không giữ tham chiếu store qua task migration hoặc tự close store từ processor nếu framework sở hữu vòng đời đó.

## 7. Changelog topic và khôi phục state

### 7.1. Changelog là gì?

Khi logging được bật, Kafka Streams ghi thay đổi state vào changelog topic. Với KeyValueStore, changelog thường lưu bản cập nhật theo key; compaction giữ giá trị mới nhất của key và tombstone biểu diễn xóa.

Changelog giúp tái tạo state local bằng cách replay các thay đổi đã ghi. Nó là nguồn phục hồi khi local state mất, task chuyển sang instance khác hoặc application khởi động trên máy mới.

```text
Task xử lý input
      |
      +----> Local State Store
      |
      +----> Changelog topic (Kafka)
                    |
                    v
              Replicated log
                    |
          local state mất / task move
                    |
                    v
              Restore consumer
                    |
                    v
             Rebuild local store
```

### 7.2. Changelog topic được quản lý tự động

Kafka Streams thường tạo internal changelog topic theo `application.id` và tên store. Tên chính xác là chi tiết framework; không hard-code tên internal topic trong business code.

Changelog topic cần replication và cấu hình phù hợp. Kafka Streams có cấu hình `replication.factor` cho internal topics; đặt giá trị production theo số broker và yêu cầu availability, thường không để mặc định thấp của môi trường lab.

Không xóa changelog topic khi application đang cần state đó. Nếu changelog mất, local store còn có thể tiếp tục tạm thời nhưng khả năng restore sau khi local state mất sẽ bị ảnh hưởng.

### 7.3. Logging enabled/disabled

Với store builder, có thể điều khiển changelog:

```java
StoreBuilder<KeyValueStore<String, Long>> recoverableStore =
    Stores.keyValueStoreBuilder(
        Stores.persistentKeyValueStore("recoverable-counts"),
        Serdes.String(),
        Serdes.Long()
    ).withLoggingEnabled(Map.of());
```

Hoặc tắt logging:

```java
StoreBuilder<KeyValueStore<String, String>> cacheStore =
    Stores.keyValueStoreBuilder(
        Stores.inMemoryKeyValueStore("rebuildable-cache"),
        Serdes.String(),
        Serdes.String()
    ).withLoggingDisabled();
```

`withLoggingEnabled()` thường là mặc định cho store builder, nhưng khai báo tường minh giúp người đọc thấy yêu cầu recovery. Chỉ dùng `withLoggingDisabled()` khi state có thể được tái tạo an toàn hoặc mất state được chấp nhận.

### 7.4. Changelog retention và cleanup policy

Changelog của key-value store thường dùng compaction để giữ trạng thái mới nhất theo key. Window/session store có semantics retention theo thời gian nên internal topic có thể cần cấu hình cleanup kết hợp compaction và delete tùy store/version.

Không tự áp `cleanup.policy=delete` cho mọi changelog topic. Xóa record changelog còn cần thiết có thể khiến restore không đầy đủ. Hãy để Kafka Streams quản lý cấu hình internal topic hoặc chỉ override theo tài liệu và yêu cầu rõ ràng.

### 7.5. Serde phải ổn định

Changelog chứa bytes đã serialize. Khi ứng dụng nâng version, state store mới phải đọc được bytes cũ. Nếu đổi Serde, đổi schema hoặc đổi ý nghĩa field, cần migration state:

- Giữ khả năng đọc format cũ trong giai đoạn chuyển tiếp.
- Dùng version marker hoặc schema registry phù hợp.
- Có thể tạo store mới và rebuild từ input topic.
- Kiểm tra changelog restore trước khi rollout rộng.

Đổi class Java hoặc package của object không tự bảo đảm tương thích wire format.

## 8. Restore và standby replica

### 8.1. Khi nào cần restore?

Kafka Streams restore local state khi:

- Task được gán cho instance mới chưa có local store.
- Local state directory bị xóa hoặc không còn dùng được.
- Một số changelog partition cần replay để bắt kịp state.
- Application triển khai trên máy/container mới.

Nếu local persistent store còn nguyên và khớp task, framework có thể tái sử dụng state rồi khôi phục phần thiếu. Restore time phụ thuộc kích thước state, changelog volume, network, disk và tốc độ xử lý.

### 8.2. Standby task

Kafka Streams có thể duy trì standby replica của state store trên instance khác. Standby task không xử lý input như active task; nó theo dõi changelog để giữ local state gần với active task.

Khi active task bị mất, standby có thể được promote, giảm lượng restore cần làm trước khi tiếp tục xử lý.

Thiết lập bằng cấu hình như:

```properties
num.standby.replicas=1
```

Số standby tăng mức dự phòng nhưng tiêu tốn thêm CPU, disk, network và tài nguyên broker. Cần đủ instance để đặt active và standby ở các process/host khác nhau.

### 8.3. Standby không thay thế changelog

Standby replica cũng cần changelog để cập nhật state. Nếu toàn bộ local copy mất, changelog vẫn là nguồn restore. Standby là cách giảm RTO, không phải bản backup độc lập.

### 8.4. Chọn số standby

| Cấu hình | Tác động |
|---|---|
| `num.standby.replicas=0` | Ít tài nguyên hơn; failover có thể cần restore toàn bộ state |
| `num.standby.replicas=1` | Có một bản standby cho task khi đủ instance và assignment phù hợp |
| Nhiều standby | Tăng khả năng sẵn sàng, tăng đáng kể chi phí lưu trữ và traffic changelog |

Standby assignment phụ thuộc số application instance, task và assignor. Đặt giá trị 1 không bảo đảm mọi task luôn có standby nếu cluster không đủ instance.

## 9. Thư mục local state và cấu hình `state.dir`

### 9.1. `state.dir`

Kafka Streams dùng `state.dir` làm thư mục gốc lưu local state, metadata và dữ liệu store. Có thể cấu hình:

```properties
state.dir=/var/lib/order-streams/state
```

Mỗi application instance cần thư mục local phù hợp và quyền đọc/ghi. Không để nhiều process độc lập dùng chung một thư mục state theo cách gây xung đột file lock hoặc ghi đè dữ liệu.

### 9.2. Local disk và container

Với container/Kubernetes:

- Dùng volume local hoặc storage phù hợp với latency của RocksDB.
- Dành dung lượng cho store data, RocksDB compaction, changelog restore và file tạm.
- Đảm bảo user chạy process có quyền đọc/ghi.
- Theo dõi disk usage và inode.
- Hiểu rõ pod restart giữ hay xóa volume.
- Nếu pod chuyển node và local volume không đi theo, chuẩn bị restore từ changelog.

Network filesystem có latency/locking behavior khác local disk. Chỉ dùng khi đã kiểm tra yêu cầu và được Kafka Streams/RocksDB deployment hỗ trợ; mặc định ưu tiên storage local hiệu năng ổn định.

### 9.3. Không gọi `cleanUp()` tùy tiện

`KafkaStreams.cleanUp()` xóa local state directory của ứng dụng. Nó hữu ích trong test hoặc khi cố ý muốn rebuild state, nhưng không phải thao tác restart thông thường.

Nếu gọi trong production, ứng dụng có thể phải restore toàn bộ state từ changelog, làm startup chậm và tăng tải Kafka. Nếu changelog bị tắt hoặc không còn đầy đủ, state có thể mất.

### 9.4. Backup local directory có cần thiết không?

Changelog là cơ chế phục hồi chính của Kafka Streams khi state logging được bật. Backup local directory có thể giúp rút ngắn thời gian khôi phục trong một số quy trình, nhưng phải nhất quán với task/partition và version ứng dụng. Không copy một RocksDB directory đang được ghi mà không có snapshot/backup procedure được hỗ trợ.

## 10. Caching và write amplification

### 10.1. State store cache

Kafka Streams có caching cho state store. Khi nhiều record cập nhật cùng key trong một khoảng thời gian, cache có thể gộp các thay đổi trước khi flush xuống store/changelog. Điều này giảm số lần ghi và lượng changelog record trong một số workload.

Ví dụ một key được cập nhật 100 lần trong batch/cache window; downstream có thể chỉ quan sát một số update đã được coalesced tùy semantics KTable/cache, thay vì mọi intermediate update.

### 10.2. Cấu hình cache

Ví dụ cấu hình theo API/config của nhiều phiên bản Kafka Streams:

```properties
cache.max.bytes.buffering=104857600
commit.interval.ms=1000
```

Tên config và cách áp dụng có thể thay đổi theo Kafka Streams version; một số bản mới có cấu hình cache chuyên biệt cho state store. Đối chiếu `StreamsConfig` và documentation của version đang dùng.

Cache dùng bộ nhớ chung theo ứng dụng và được phân bổ giữa các thread/task/store theo implementation. Đặt quá cao có thể tăng memory pressure; đặt quá thấp có thể tăng write/changelog traffic.

### 10.3. Cache khác RocksDB block cache

Kafka Streams record cache giúp coalesce update và giảm flush/write vào store/changelog. RocksDB block cache giữ block/index/filter trong memory để tăng tốc đọc disk. Đây là hai lớp cache khác nhau.

Một process có thể tiêu thụ RAM cho:

- Java heap và Kafka Streams record cache.
- RocksDB block cache và memtable (native memory).
- Network buffers, producer/consumer buffers.
- JVM metadata, thread stack và direct buffers.

Chỉ nhìn heap usage không đủ để biết tổng memory của container.

### 10.4. Cân bằng cache và độ trễ

Cache lớn có thể giảm write amplification nhưng thay đổi thời điểm flush và visibility của state/output. Với workload cần latency thấp, đo thời gian từ input record đến output/store query và chọn commit/cache interval theo SLA.

Không dùng cache để thay thế durability. Khi cần đảm bảo atomic output/state/offset, cấu hình processing guarantee phù hợp; cache chỉ là tối ưu hiệu năng.

## 11. Window store và retention

### 11.1. Windowed aggregation

Ví dụ đếm số đơn hàng theo cửa sổ 5 phút:

```java
KTable<Windowed<String>, Long> counts = events
    .groupByKey()
    .windowedBy(TimeWindows.ofSizeAndGrace(
        Duration.ofMinutes(5),
        Duration.ofMinutes(1)
    ))
    .count(
        Materialized.<String, Long, WindowStore<Bytes, byte[]>>as("orders-5m")
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
            .withRetention(Duration.ofHours(2))
    );
```

Ví dụ dùng API window DSL hiện đại. Cần bảo đảm retention đủ lớn cho window size cộng grace period và yêu cầu truy vấn. Nếu retention quá ngắn, state cần thiết có thể bị xóa trước khi event late được xử lý hoặc trước khi ứng dụng cần query.

### 11.2. Window size, grace và retention

- **Window size:** độ dài cửa sổ gom event.
- **Grace period:** khoảng thời gian cho phép event đến trễ vẫn được cập nhật window.
- **Retention:** thời gian giữ state/window sau khi không còn cần cho xử lý theo semantics của store.

Retention không nên nhỏ hơn giới hạn tối thiểu do window/grace yêu cầu. API có thể từ chối cấu hình quá nhỏ hoặc áp dụng giới hạn theo version. Chọn retention lớn hơn nếu cần query lịch sử hoặc audit window.

### 11.3. Session store

Session window gom event theo key cho đến khi có khoảng inactivity đủ dài để kết thúc session. Session store cần giữ session start/end, aggregate và merge state khi event mới nối hai session.

Retention session cần đủ để hỗ trợ session inactivity gap, grace period và yêu cầu truy vấn. Không áp retention giống key-value store nếu dữ liệu có vòng đời theo thời gian.

### 11.4. Tombstone và xóa state

Với key-value changelog, tombstone biểu diễn xóa key và giúp restore loại bỏ state cũ. Với window/session store, cleanup dựa trên retention và timestamp. Cần phân biệt xóa một key nghiệp vụ với hết hạn state theo thời gian.

## 12. Truy vấn state bằng Interactive Queries

### 12.1. Local query

State Store được phân phối theo task/partition trên các instance. Một query đến một instance chỉ có thể đọc local state mà instance đó đang sở hữu hoặc có bản standby/readable tương ứng theo API/version.

Ví dụ lấy read-only key-value store:

```java
ReadOnlyKeyValueStore<String, Long> store = kafkaStreams.store(
    StoreQueryParameters.fromNameAndType(
        "order-counts",
        QueryableStoreTypes.keyValueStore()
    )
);

Long count = store.get("ORD-101");
```

Store name phải khớp `Materialized.as("order-counts")`. Kiểu queryable store phải đúng với loại store đã materialize.

### 12.2. Query key thuộc instance khác

Nếu key được partition đến task trên instance khác, local query tại instance hiện tại có thể không tìm thấy state hoặc báo store/partition không khả dụng. Interactive Queries cần cơ chế định tuyến:

1. Xác định partition của key theo partitioner/metadata phù hợp.
2. Hỏi Kafka Streams instance nào đang active cho partition đó.
3. Gọi endpoint nội bộ của instance sở hữu partition.
4. Instance đó đọc local store và trả kết quả.

Có thể cấu hình `application.server` để công bố endpoint của instance và dùng metadata API như `queryMetadataForKey()` tùy version.

### 12.3. Interactive Queries không phải database cluster tự động

Kafka Streams không tự tạo một REST API phân tán cho mọi state store. Ứng dụng phải xây endpoint, xác thực, routing, timeout, retry và xử lý trường hợp rebalance khiến metadata thay đổi.

Nếu cần query toàn bộ state, có thể phải fan-out đến các instance hoặc materialize dữ liệu sang database/search system phù hợp. Không scan tất cả store partition qua một endpoint như thể chúng nằm trên một node.

### 12.4. Đọc và ghi state

Business query bên ngoài thường dùng read-only store interface. Không tự sửa state store từ REST controller hoặc thread tùy ý trong khi Kafka Streams đang xử lý task. Việc mutate ngoài task có thể phá ordering, changelog consistency và thread-safety.

Nếu cần thay đổi state, phát command/event vào input topic hoặc dùng cơ chế tương tác được thiết kế rõ ràng để thay đổi state trong context của topology.

## 13. Cấu hình và ví dụ ứng dụng

### 13.1. Cấu hình Kafka Streams

Ví dụ properties:

```properties
application.id=order-analytics
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
state.dir=/var/lib/order-analytics/state
replication.factor=3
num.stream.threads=3
num.standby.replicas=1
processing.guarantee=exactly_once_v2
```

Ý nghĩa:

- `application.id`: định danh ứng dụng, đồng thời dùng cho consumer group và namespace internal topics.
- `state.dir`: thư mục local state.
- `replication.factor`: replication factor cho internal topics do Kafka Streams tạo, tùy version/config.
- `num.stream.threads`: số stream thread trong mỗi application instance.
- `num.standby.replicas`: số standby task mong muốn.
- `processing.guarantee`: semantics xử lý; `exactly_once_v2` yêu cầu broker/client version tương thích.

Không đặt `application.id` khác nhau giữa các instance của cùng một logical application. Nếu khác, chúng hoạt động như các ứng dụng/consumer group khác nhau.

### 13.2. Tạo KafkaStreams

```java
Properties props = new Properties();
props.put(StreamsConfig.APPLICATION_ID_CONFIG, "order-analytics");
props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(StreamsConfig.STATE_DIR_CONFIG, "/var/lib/order-analytics/state");
props.put(StreamsConfig.REPLICATION_FACTOR_CONFIG, 3);
props.put(StreamsConfig.NUM_STANDBY_REPLICAS_CONFIG, 1);
props.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG,
    StreamsConfig.EXACTLY_ONCE_V2);

KafkaStreams streams = new KafkaStreams(builder.build(), props);
streams.start();
```

Trong ứng dụng thật, cần thêm uncaught exception handler, state listener, shutdown hook và đóng `KafkaStreams` có timeout. Không gọi `start()` nhiều lần trên cùng object.

### 13.3. Graceful shutdown

```java
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    streams.close(Duration.ofSeconds(30));
}));
```

Graceful close cho Streams cơ hội dừng thread và flush/commit theo lifecycle. Nếu process bị kill -9 hoặc máy mất điện, Kafka Streams sẽ dựa vào changelog/offset transaction để phục hồi theo processing guarantee.

Không gọi `cleanUp()` trong shutdown hook thông thường; close và cleanup là hai thao tác khác nhau.

## 14. RocksDB và tối ưu storage

### 14.1. RocksDB là gì trong Kafka Streams?

RocksDB là embedded key-value storage engine chạy trong cùng process, sử dụng native code và lưu dữ liệu trên local disk. Kafka Streams dùng RocksDB cho nhiều persistent state store mặc định.

RocksDB sử dụng memtable, SST files, block cache và compaction. Vì vậy, hiệu năng phụ thuộc cả memory lẫn disk, không chỉ Java heap.

### 14.2. Dung lượng disk

Ước lượng ban đầu:

```text
local_state_disk
  >= active_store_data
     + standby_store_data
     + compaction_headroom
     + restore_and_temporary_space
     + operational_margin
```

State size cần tính theo số partition/task được gán trên một instance. Khi rebalance, instance có thể tạm thời giữ thêm state/restore data. Đặt disk quota chỉ bằng kích thước logical state hiện tại dễ gây đầy disk trong compaction hoặc restore.

### 14.3. Tuning RocksDB

Kafka Streams hỗ trợ cấu hình RocksDB thông qua `RocksDBConfigSetter` trong các version có API tương ứng. Có thể điều chỉnh block cache, write buffer, compression và một số option khác.

Không tăng cache hoặc write buffer một cách tùy tiện. Tổng native memory có thể vượt giới hạn container dù JVM heap còn thấp. Benchmark bằng workload thật và theo dõi RSS/container memory.

### 14.4. Disk I/O và compaction

Theo dõi:

- Disk read/write latency và throughput.
- IOPS, queue depth và filesystem utilization.
- RocksDB compaction duration/backlog nếu có metric.
- State store put/get latency.
- Restore throughput và thời gian task chuyển sang RUNNING.
- Disk free space và inode.

Nếu disk chậm, tăng số stream thread có thể làm tình trạng nặng hơn vì nhiều task tranh chấp I/O.

## 15. Monitoring State Store và restore

Theo dõi state store ở nhiều lớp.

| Lớp | Tín hiệu cần theo dõi | Ý nghĩa |
|---|---|---|
| Kafka Streams app | State, rebalance, thread count, task assignment | Ứng dụng có ổn định không |
| State store | Store size, put/get latency, open/close error | State có hoạt động bình thường không |
| Restore | Restore rate, total restore records/latency, restore duration | Task mất bao lâu để sẵn sàng |
| Changelog topic | Partition count, replication, ISR, end offset | Nguồn phục hồi có khỏe không |
| Local storage | Disk usage, I/O latency, native memory | Store có bị giới hạn tài nguyên không |
| Standby | Standby lag và assignment | Failover có thể phục hồi nhanh không |

Tên metric JMX thay đổi theo Kafka version. Kiểm tra MBean thực tế thay vì hard-code metric name từ một bản hướng dẫn cũ.

### 15.1. Alert gợi ý

- Disk free thấp hơn ngưỡng an toàn.
- Restore duration tăng đột biến sau deploy/rebalance.
- Changelog topic under-replicated hoặc thiếu ISR.
- State store open/restore failure.
- Standby lag lớn hơn failover objective.
- Rebalance lặp lại làm task liên tục migrate.
- Native memory/RSS tăng trong khi heap không tăng tương ứng.
- Input lag tăng đồng thời với RocksDB latency.

## 16. Các lỗi và anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Dùng `HashMap` global thay State Store | State không gắn task/partition và mất khi restart | Dùng store do Kafka Streams quản lý |
| Nghĩ persistent store không cần changelog | Mất local disk là mất state | Bật changelog hoặc có rebuild plan đã kiểm chứng |
| Tắt logging cho state quan trọng | Không restore được khi local state mất | Giữ changelog fault tolerance |
| Chọn in-memory cho state rất lớn | Heap pressure và GC pause | Dùng persistent store hoặc thiết kế state nhỏ hơn |
| Chọn RocksDB nhưng không giám sát disk | Disk đầy, compaction chậm, task fail | Dự phòng disk và theo dõi I/O |
| Đổi store name tùy tiện | Tạo state/changelog mới hoặc restore lại | Xem store name là identity vận hành |
| Đổi Serde nhưng không migration | Restore bytes cũ thất bại hoặc sai dữ liệu | Giữ reader tương thích hoặc rebuild store mới |
| Xóa changelog topic để reset | Mất nguồn phục hồi | Dùng migration/rebuild có kế hoạch |
| Gọi `cleanUp()` khi restart bình thường | Buộc restore toàn bộ state, startup chậm | Chỉ cleanup khi chủ động rebuild/test |
| Dùng chung `state.dir` giữa nhiều process | File lock/xung đột local state | Thư mục riêng theo instance |
| Tăng standby replicas mà không tính tài nguyên | Tăng disk, network và broker load | Chọn theo RTO và khả năng cluster |
| Query local store từ bất kỳ instance | Không tìm thấy partition thuộc node khác | Dùng Interactive Query metadata và routing |
| Ghi state từ REST thread tùy ý | Race condition và changelog inconsistency | Đưa command vào topology hoặc API được hỗ trợ |
| Giả định cache là durability | State/output có thể chưa được commit như kỳ vọng | Cấu hình processing guarantee và changelog đúng |

## 17. Kiểm thử State Store

### 17.1. Unit test topology

`TopologyTestDriver` hỗ trợ kiểm thử topology và state store mà không cần Kafka broker thật trong nhiều trường hợp. Có thể:

- Đưa record vào input topic test.
- Đọc output topic.
- Lấy store theo tên và kiểm tra state.
- Kiểm tra window/session aggregation với timestamp cụ thể.
- Kiểm tra null key, tombstone và late event.

Ví dụ khái quát:

```java
try (TopologyTestDriver driver = new TopologyTestDriver(
        builder.build(), testProperties)) {

    TestInputTopic<String, String> input = driver.createInputTopic(
        "orders", new StringSerializer(), new StringSerializer());

    input.pipeInput("ORD-101", "created");
    input.pipeInput("ORD-101", "paid");

    KeyValueStore<String, Long> store = driver.getKeyValueStore("order-counts");
    assertEquals(2L, store.get("ORD-101"));
}
```

API test driver và cách lấy store cần khớp Kafka Streams version. Đây là test topology/state logic, không chứng minh restore thực tế từ broker changelog.

### 17.2. Integration test

Với broker thật hoặc môi trường Kafka test tương đương, kiểm tra:

- Changelog topic được tạo và có replication phù hợp.
- Application restart vẫn phục hồi state.
- Xóa local state directory trong môi trường test khiến state restore từ changelog.
- Worker/task rebalance không làm mất state.
- Standby được cập nhật và có thể được promote.
- `exactly_once_v2` giữ output/changelog/offset theo transaction semantics.
- Schema/Serde version mới đọc được changelog cũ.

Không xóa local state hoặc changelog trong production chỉ để thử restore. Thực hiện fault injection trong môi trường staging có dữ liệu kiểm soát.

## 18. Runbook khi State Store lỗi

Khi topology không khởi động hoặc state không đúng, xử lý theo thứ tự:

1. Ghi lại `application.id`, store name, task/partition và thời điểm lỗi.
2. Kiểm tra Kafka Streams state listener, thread exception và log restore.
3. Kiểm tra `state.dir`, quyền filesystem, disk free và native memory.
4. Kiểm tra changelog topic tồn tại, partition/replication/ISR khỏe.
5. Xác nhận `Serde` và schema tương thích với bytes changelog cũ.
6. Kiểm tra application ID/store name có bị đổi ngoài kế hoạch không.
7. Kiểm tra rebalance, standby assignment và restore lag.
8. Nếu local state hỏng, dừng instance theo runbook và để framework restore từ changelog.
9. Chỉ cleanup local state khi đã xác nhận changelog/source rebuild đầy đủ.
10. Sau recovery, kiểm tra output, state value, input lag và business invariant.

Nếu changelog cũng mất hoặc không đầy đủ, cần đánh giá khả năng rebuild từ input topics. Nếu input retention không đủ, state có thể không thể tái tạo chính xác; cần backup/audit source hoặc khôi phục từ nguồn khác.

## 19. Checklist thiết kế và vận hành

- Store type phù hợp với semantics: key-value, window, session hoặc versioned.
- Đã chọn in-memory/persistent theo kích thước state, latency và tài nguyên.
- State quan trọng có changelog logging hoặc rebuild plan được kiểm thử.
- Store name và `application.id` được quản lý như identity vận hành.
- Key/value Serde ổn định và có kế hoạch schema evolution.
- Changelog internal topics có replication factor và ACL phù hợp.
- Window/session retention đủ cho window size, grace và query window.
- `state.dir` riêng cho mỗi instance, có disk và permission phù hợp.
- Không xóa local state hoặc changelog tùy tiện.
- Cache, RocksDB native memory và Java heap được tính chung vào memory budget.
- Standby replicas được chọn theo RTO và số instance thực tế.
- Interactive Queries có routing đến instance sở hữu partition.
- Không mutate store từ thread bên ngoài task lifecycle.
- Có metric restore, changelog health, disk, state size và standby lag.
- Có unit test topology và integration test restore/rebalance.
- Có runbook recovery và quy trình migration store/schema.

## 20. Câu hỏi tự kiểm tra

1. State Store giải quyết vấn đề gì trong Kafka Streams?
2. Vì sao stateful aggregation cần state store còn stateless map thì không?
3. In-memory store và persistent store khác nhau ở nơi lưu local như thế nào?
4. Vì sao persistent local state vẫn cần changelog?
5. In-memory store có thể fault-tolerant không? Điều kiện là gì?
6. Khi nào có thể tắt changelog logging?
7. KeyValueStore, WindowStore và SessionStore khác nhau ra sao?
8. `Materialized.as()` có vai trò gì?
9. Vì sao Serde cần tương thích với changelog cũ?
10. Changelog topic giúp restore task như thế nào?
11. Standby task khác active task ra sao?
12. `state.dir` được dùng để làm gì và vì sao không nên dùng chung giữa process?
13. Vì sao `cleanUp()` không phải thao tác restart thông thường?
14. Kafka Streams record cache khác RocksDB block cache như thế nào?
15. Window size, grace period và retention liên hệ với nhau ra sao?
16. Interactive Queries định tuyến request đến instance sở hữu partition bằng cách nào?
17. Vì sao heap metric không phản ánh toàn bộ memory của RocksDB?
18. Cần kiểm thử những tình huống nào để xác minh state restore?

## Kết luận

State Store giúp Kafka Streams thực hiện aggregation, join và các phép xử lý cần ghi nhớ dữ liệu. In-memory store phù hợp state nhỏ và truy cập nhanh; persistent store thường dùng RocksDB để lưu state lớn trên local disk. Local persistence và fault tolerance là hai lớp khác nhau: changelog topic mới là nguồn phục hồi khi local state mất, còn standby replica giúp giảm thời gian failover. Lựa chọn store cần đi cùng Serde ổn định, retention, caching, `state.dir`, replication, monitoring và quy trình restore. Khi triển khai đúng, stateful topology có thể phục hồi sau restart/rebalance mà vẫn giữ được trạng thái nghiệp vụ nhất quán.
