# Suppress, cache và thời điểm phát kết quả tổng hợp

Kafka Streams thường phát ra một bản cập nhật mỗi khi KTable thay đổi. Với một phép aggregation, một key có thể được cập nhật hàng trăm lần trong một cửa sổ thời gian. Downstream nhận toàn bộ các thay đổi đó có thể tốn network, I/O và chi phí xử lý, trong khi một số use case chỉ cần kết quả cuối cùng của cửa sổ hoặc muốn giới hạn tần suất phát cập nhật.

Kafka Streams có hai cơ chế liên quan nhưng giải quyết hai mục đích khác nhau:

- **KTable cache** gom và hợp nhất các cập nhật trong bộ đệm để giảm số lần ghi/forward. Đây chủ yếu là tối ưu hiệu năng.
- **Suppression** là một toán tử DSL có semantics rõ ràng về thời điểm phát record. Nó có thể giữ các cập nhật cho đến khi cửa sổ đóng hoặc giới hạn tần suất phát theo key.

Muốn chọn đúng cơ chế, cần hiểu stream-time, window end, grace period, late event và giới hạn buffer. Suppression không phải bộ hẹn giờ theo đồng hồ máy; thời điểm phát của nó gắn với tiến triển thời gian trong stream.

## 1. KTable phát cập nhật như thế nào?

KTable biểu diễn trạng thái mới nhất theo key. Khi aggregation nhận record mới, state store được cập nhật và KTable có thể phát ra một changelog record chứa giá trị mới.

Ví dụ đếm số đơn hàng theo customer:

~~~text
Input events:
customer-7 order-1
customer-7 order-2
customer-7 order-3
customer-7 order-4

KTable updates:
customer-7 -> 1
customer-7 -> 2
customer-7 -> 3
customer-7 -> 4
~~~

Mỗi dòng là một trạng thái mới của cùng key. Nếu downstream chỉ cần số lượng cuối cùng sau 5 phút, phát cả bốn update có thể không cần thiết.

KTable update stream có semantics upsert:

- Record có key và value khác null: tạo hoặc cập nhật trạng thái của key.
- Record có key và value null: tombstone, biểu thị xóa trạng thái của key.
- KTable downstream giữ giá trị mới nhất mà nó nhận được cho từng key.

### 1.1. KTable không phải một snapshot bất biến

KTable là một luồng thay đổi trạng thái. Một phép aggregation như count() có thể cập nhật liên tục:

~~~java
KTable<String, Long> counts =
    events
        .groupByKey()
        .count();
~~~

Nếu bốn event của customer-7 lần lượt đến, KTable có thể tạo bốn update như ví dụ. Consumer của topic đầu ra có thể nhận nhiều giá trị cho cùng key và phải hiểu đây là các bản cập nhật trạng thái.

Nếu downstream ghi database bằng upsert, nhận nhiều update có thể vẫn đúng nhưng làm tăng write load. Nếu downstream gửi thông báo cho người dùng, phát mọi intermediate value có thể gây spam.

## 2. KTable cache: gom cập nhật để giảm I/O

Kafka Streams có cache cho state store. Khi cache bật, các cập nhật cho cùng key có thể được coalesce trước khi flush xuống state store hoặc forward tới downstream processor.

Ví dụ trong một khoảng cache flush:

~~~text
Updates từ aggregation:
customer-7 -> 1
customer-7 -> 2
customer-7 -> 3
customer-7 -> 4

Giá trị được giữ trong cache:
customer-7 -> 4

Sau flush:
customer-7 -> 4
~~~

Cache có thể giảm số lần ghi RocksDB và số lượng update được truyền qua topology. Đây là tối ưu hiệu năng, không phải cam kết chỉ phát một kết quả cuối cùng.

### 2.1. Cache được flush khi nào?

Cache có thể được flush khi:

- Bộ đệm đạt ngưỡng dung lượng.
- Kafka Streams thực hiện commit theo chu kỳ.
- Các điều kiện nội bộ của state store yêu cầu flush.
- Application đóng hoặc chuyển trạng thái theo lifecycle.

commit.interval.ms có ảnh hưởng đến nhịp commit và flush. Tuy nhiên, không nên hiểu nó là một lịch phát kết quả chính xác theo đồng hồ tường. Cache cũng có thể flush sớm khi đầy.

Nếu cache flush sau mỗi nhóm update, downstream vẫn có thể nhận nhiều bản cập nhật trước khi window đóng.

### 2.2. Cấu hình cache của state store

Với các phiên bản Kafka Streams hiện đại, cấu hình cache state store dùng property statestore.cache.max.bytes. Ví dụ:

~~~java
Properties props = new Properties();

props.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "customer-analytics"
);
props.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
props.put(
    StreamsConfig.STATESTORE_CACHE_MAX_BYTES_CONFIG,
    64L * 1024 * 1024
);
props.put(
    StreamsConfig.COMMIT_INTERVAL_MS_CONFIG,
    1_000
);
~~~

Property cache giới hạn dung lượng bộ đệm state store theo cấu hình của Kafka Streams. Cần đọc tài liệu đúng phiên bản vì các bản cũ có thể dùng tên cấu hình cache.max.bytes.buffering, hiện đã được thay thế/deprecate trong các phiên bản mới.

Ngân sách cache được cấu hình ở cấp Kafka Streams client và được chia sẻ giữa các stream thread của instance đó; không hiểu con số 64 MB trong ví dụ là 64 MB cho từng state store riêng lẻ. Khi chạy nhiều instance, mỗi instance có ngân sách cache riêng.

Đặt cache bằng 0 sẽ tắt caching. Tắt cache có thể làm các update được forward thường xuyên hơn, tăng write amplification và downstream traffic. Chỉ nên tắt khi cần semantics quan sát từng update hoặc sau khi đo tác động.

### 2.3. Cache không biết khi nào window đã kết thúc

Cache chỉ gom cập nhật trong thời gian chúng nằm trong bộ đệm. Nó không biết nghiệp vụ yêu cầu đợi đến cuối cửa sổ 5 phút.

Ví dụ:

~~~text
10:00:10  customer-7 -> 1
10:00:20  customer-7 -> 2
10:00:30  cache flush -> customer-7 -> 2
10:01:00  customer-7 -> 3
10:01:30  cache flush -> customer-7 -> 3
10:05:00  window end
~~~

Downstream vẫn có thể nhận update tại 10:00:30 và 10:01:30, trước khi window kết thúc. Cache không thay thế được final-result semantics.

## 3. Suppression là gì?

Suppression là một toán tử trên KTable, được cấu hình qua suppress() và Suppressed. Nó giữ các update trong buffer và chỉ phát theo chính sách thời gian đã chọn.

Hai chính sách thường gặp:

- untilWindowCloses(...): giữ kết quả windowed aggregation cho đến khi window đóng, bao gồm grace period.
- untilTimeLimit(...): giới hạn tần suất phát update theo key trong một khoảng stream-time.

Suppression thay đổi thời điểm downstream nhìn thấy update. Vì vậy, đây là một phần semantics của topology, không chỉ là tối ưu cache.

### 3.1. So sánh cache và suppression

| Tiêu chí | KTable cache | Suppression |
|---|---|---|
| Mục đích | Giảm state-store write và update traffic | Điều khiển thời điểm phát kết quả |
| Biết window end | Không | Có với untilWindowCloses |
| Giới hạn tần suất theo key | Không có bảo đảm rõ ràng | Có với untilTimeLimit |
| Bảo đảm final result | Không | Có với untilWindowCloses nếu buffer strict |
| Có thể flush sớm | Có khi cache đầy/commit | Tùy BufferConfig |
| Cấu hình | State store cache và commit | Suppressed.BufferConfig |
| Tác động | Tối ưu hiệu năng | Thay đổi output timing/semantics |

Hai cơ chế có thể cùng tồn tại. Cache giảm lượng update mà suppression phải nhận; suppression tiếp tục giữ kết quả cho đến thời điểm được chỉ định.

## 4. Stream-time, event-time và wall-clock time

Để hiểu suppression, cần phân biệt ba khái niệm thời gian.

- **Event timestamp:** timestamp gắn với record, thường được trích xuất từ event hoặc metadata Kafka.
- **Stream-time:** khái niệm thời gian tiến triển trong task dựa trên timestamp của các record đã xử lý.
- **Wall-clock time:** thời gian thực của máy đang chạy application.

Kafka Streams dùng timestamp extractor để lấy timestamp cho record. Stream-time tiến triển khi task xử lý record có timestamp mới. Nó không đơn giản là thời gian hiện tại của máy.

Ví dụ:

~~~text
Máy hiện tại: 10:10:00

Record đã xử lý:
10:00:00
10:00:05
10:00:12

Stream-time xấp xỉ timestamp lớn nhất đã quan sát:
10:00:12
~~~

Nếu không có record mới, stream-time có thể không tiến thêm dù wall-clock tiếp tục chạy.

### 4.1. Suppression không phải timer theo wall-clock

Giả sử một window kết thúc lúc 10:05 và grace period là 1 phút. Nếu không có record nào mới được xử lý để đẩy stream-time qua ngưỡng đóng window, kết quả final có thể chưa được phát dù đồng hồ máy đã chỉ 10:10.

Khi record mới có timestamp đủ lớn được xử lý, stream-time tiến lên và các window đủ điều kiện đóng mới được phát.

Điều này quan trọng với topic ít traffic hoặc partition bị idle. Không được thiết kế SLA theo kiểu “đúng 5 phút sau record đầu tiên chắc chắn có output” nếu dùng suppression dựa trên stream-time.

### 4.2. Timestamp extractor quyết định thời gian của stream

Kafka Streams có thể lấy timestamp từ:
- Timestamp do producer ghi vào Kafka record.
- Field timestamp trong payload thông qua custom TimestampExtractor.
- WallclockTimestampExtractor, nếu ứng dụng chủ động chọn semantics này.

Dùng timestamp nghiệp vụ giúp window theo event-time. Dùng wall-clock extractor có thể làm timestamp record phản ánh thời gian xử lý, nhưng stream-time vẫn tiến triển thông qua record được xử lý; suppression không biến thành một scheduler độc lập chạy khi không có input.

Nếu timestamp bị sai, nằm quá xa trong tương lai hoặc không đơn điệu theo dữ liệu thực tế, window closure và suppression timing có thể bất thường.

## 5. Window end và grace period

Windowed aggregation chia record thành các cửa sổ thời gian. Ví dụ tumbling window 5 phút:

~~~text
Window A: [10:00, 10:05)
Window B: [10:05, 10:10)
Window C: [10:10, 10:15)
~~~

Window thường được biểu diễn theo khoảng nửa mở: bắt đầu được tính, kết thúc không được tính. Record có timestamp đúng 10:05 thuộc window kế tiếp.

Grace period là khoảng thời gian cho phép record đến muộn sau window end mà vẫn được chấp nhận vào window cũ.

Ví dụ:

- Window: 10:00 đến trước 10:05.
- Grace: 1 phút.
- Record timestamp 10:04:50 vẫn thuộc window.
- Record timestamp 10:05:30 có thể được chấp nhận vào window cũ nếu đến khi stream-time chưa vượt ngưỡng grace.
- Khi stream-time đã đi qua window end cộng grace, window đủ điều kiện đóng và suppression có thể phát kết quả cuối.

Grace period không phải thời gian chờ tính từ lúc record đầu tiên tới. Nó gắn với thời điểm kết thúc của window.

### 5.1. Cấu hình window có grace

Ví dụ 5 phút tumbling window với grace 1 phút:

~~~java
TimeWindows windows =
    TimeWindows.ofSizeAndGrace(
        Duration.ofMinutes(5),
        Duration.ofMinutes(1)
    );
~~~

Windowed aggregation:

~~~java
KTable<Windowed<String>, Long> counts =
    events
        .selectKey(
            (orderId, event) -> event.customerId()
        )
        .groupByKey(
            Grouped.with(
                Serdes.String(),
                orderEventSerde
            )
        )
        .windowedBy(windows)
        .count(
            Materialized.as("customer-order-window-counts")
        );
~~~

selectKey() thay key từ orderId sang customerId. groupByKey() kích hoạt repartition cần thiết để các event cùng customer được xử lý trên cùng partition trước khi aggregation.

### 5.2. Grace càng dài, final output càng muộn

Grace dài cho phép chấp nhận event đến muộn lâu hơn, nhưng cũng kéo dài thời gian giữ state và suppression buffer.

| Grace period | Lợi ích | Chi phí |
|---|---|---|
| 0 | Final result có thể phát sớm hơn | Event đến muộn dễ bị loại |
| 30 giây | Chấp nhận trễ ngắn | Giữ state/buffer lâu hơn 30 giây |
| 5 phút | Phù hợp nguồn có độ trễ lớn hơn | Output final muộn, buffer lớn hơn |
| 1 giờ | Chấp nhận dữ liệu rất trễ | Tăng state, storage và thời gian phục hồi |

Chọn grace dựa trên phân phối độ trễ thực tế của nguồn, không chọn chỉ vì muốn output xuất hiện sớm.

## 6. untilWindowCloses: chỉ phát kết quả cuối cùng của window

Với windowed KTable, untilWindowCloses() giữ các update cho đến khi stream-time đi qua window end cộng grace. Khi đó, nó phát giá trị cuối cùng cho từng key-window.

Ví dụ:

~~~java
KTable<Windowed<String>, Long> finalCounts =
    counts.suppress(
        Suppressed.untilWindowCloses(
            Suppressed.BufferConfig
                .maxBytes(64L * 1024 * 1024)
                .shutDownWhenFull()
        )
    );
~~~

Đây là strict buffer: nếu buffer đầy, application dừng thay vì phát sớm một giá trị trung gian. Nhờ vậy, semantics “chỉ phát sau khi window đóng” được giữ.

Đầu ra:

~~~java
finalCounts
    .toStream()
    .to(
        "customer-order-final-counts",
        Produced.with(
            WindowedSerdes.timeWindowedSerdeFrom(String.class),
            Serdes.Long()
        )
    );
~~~

Output key là Windowed<String>, chứa customerId và thông tin window. Downstream có thể dùng key này để phân biệt kết quả của customer-7 trong từng window.

### 6.1. Ví dụ diễn tiến

Window 10:00–10:05, grace 1 phút:

~~~text
Event timestamp 10:00:10 -> count 1
Event timestamp 10:01:00 -> count 2
Event timestamp 10:03:20 -> count 3
Event timestamp 10:04:50 -> count 4

KTable trung gian:
customer-7@[10:00,10:05) -> 1
customer-7@[10:00,10:05) -> 2
customer-7@[10:00,10:05) -> 3
customer-7@[10:00,10:05) -> 4

Khi stream-time đi qua 10:06:
customer-7@[10:00,10:05) -> 4
~~~

Downstream chỉ nhận một kết quả final cho key-window. Các update trung gian không được phát qua suppression operator.

### 6.2. untilWindowCloses chỉ áp dụng cho windowed table

Không thể dùng untilWindowCloses() cho KTable không có window key. Nếu cần giới hạn tần suất phát của KTable thông thường, xem untilTimeLimit().

Cũng cần phân biệt final của một window với final của một entity trong toàn bộ vòng đời. Một customer có thể có kết quả final ở nhiều window khác nhau.

### 6.3. Final là final theo grace policy

Sau khi window đóng, event đến muộn hơn ngưỡng grace không được bổ sung vào kết quả final của window đó theo semantics windowed aggregation. Nếu nghiệp vụ cần sửa lại kết quả sau thời điểm này, phải có một quy trình correction/reconciliation riêng, hoặc chọn grace đủ dài ngay từ đầu.

Không dùng suppression để che giấu dữ liệu trễ. Cần đo late-record drop và xác định có cần backfill hay không.

## 7. untilTimeLimit: giới hạn tần suất update theo key

untilTimeLimit() phù hợp với KTable không windowed hoặc use case cần giới hạn số lần phát update trong một khoảng stream-time.

Ví dụ:

~~~java
KTable<String, Long> throttledCounts =
    counts.suppress(
        Suppressed.untilTimeLimit(
            Duration.ofSeconds(30),
            Suppressed.BufferConfig
                .maxBytes(16L * 1024 * 1024)
                .emitEarlyWhenFull()
        )
    );
~~~

Với mỗi key, suppression giữ update trong khoảng thời gian giới hạn rồi phát giá trị mới nhất. Các update tiếp theo đến trong khoảng chờ thay thế giá trị đang buffer; chúng không nhất thiết khởi động lại bộ đếm thời gian của chu kỳ hiện tại.

Sau khi một update được phát, các update mới có thể bắt đầu chu kỳ suppression tiếp theo.

### 7.1. untilTimeLimit không phải final window result

Giả sử customer-7 được cập nhật liên tục:

~~~text
Stream-time 10:00:00 -> customer-7 = 10
Stream-time 10:00:05 -> customer-7 = 11
Stream-time 10:00:10 -> customer-7 = 12
Stream-time 10:00:30 -> phát customer-7 = 12
Stream-time 10:00:35 -> customer-7 = 13
Stream-time 10:01:00 -> phát customer-7 = 13
~~~

Đây là rate limiting/debounce theo key. Giá trị được phát là snapshot mới nhất ở thời điểm suppression cho phép phát, không phải kết quả cuối cùng của một window nghiệp vụ.

Nếu cần một kết quả duy nhất khi window kết thúc, hãy dùng untilWindowCloses().

### 7.2. Thời gian của untilTimeLimit cũng dựa trên stream-time

Nếu stream-time không tiến triển vì không có record mới, update đang được giữ có thể chưa được phát dù wall-clock đã vượt 30 giây.

Nếu nghiệp vụ cần gửi thông báo đúng giờ wall-clock ngay cả khi topic idle, cần một cơ chế scheduler/punctuation hoặc hệ thống điều phối riêng. Không giả định untilTimeLimit() là cron timer.

## 8. BufferConfig và hành vi khi buffer đầy

Suppression cần buffer để giữ update chưa được phát. Buffer có thể tăng khi:
- Có nhiều key/window đang mở.
- Grace period dài.
- Input throughput cao.
- Stream-time không tiến triển.
- Downstream hoặc task không xử lý kịp.
- Có nhiều cửa sổ chồng lấp như hopping windows.

Cần chọn giới hạn buffer theo dung lượng, cardinality và thời gian giữ.

### 8.1. Unbounded buffer

Ví dụ:

~~~java
Suppressed.untilWindowCloses(
    Suppressed.BufferConfig.unbounded()
);
~~~

Unbounded không đặt giới hạn buffer. Nó tránh việc buffer đầy làm thay đổi semantics, nhưng có thể khiến tài nguyên tăng không kiểm soát khi số key/window lớn hoặc stream-time bị kẹt.

Không dùng unbounded trong production mà không có capacity estimate, monitoring và giới hạn hạ tầng phù hợp.

### 8.2. Strict buffer: dừng khi đầy

Ví dụ:

~~~java
Suppressed.BufferConfig strictBuffer =
    Suppressed.BufferConfig
        .maxBytes(64L * 1024 * 1024)
        .shutDownWhenFull();
~~~

Khi đạt giới hạn, strict buffer phát sinh lỗi và Kafka Streams dừng xử lý theo chính sách shutdown của stream thread/application thay vì phát sớm record. Điều này bảo toàn yêu cầu final-only nhưng làm topology ngừng tiến triển cho đến khi nguyên nhân được xử lý hoặc capacity được điều chỉnh.

Có thể giới hạn theo số record:

~~~java
Suppressed.BufferConfig strictByCount =
    Suppressed.BufferConfig
        .maxRecords(500_000L)
        .shutDownWhenFull();
~~~

Chọn maxBytes thường phản ánh dung lượng tốt hơn khi kích thước record biến động mạnh. maxRecords dễ hiểu nhưng 500.000 record nhỏ và 500.000 record lớn có chi phí rất khác nhau.

### 8.3. Eager buffer: phát sớm khi đầy

Với use case chấp nhận update sớm, có thể cấu hình:

~~~java
Suppressed.BufferConfig eagerBuffer =
    Suppressed.BufferConfig
        .maxBytes(16L * 1024 * 1024)
        .emitEarlyWhenFull();
~~~

Khi buffer đầy, suppression có thể phát một số record sớm để giải phóng chỗ. Điều này có thể phá vỡ kỳ vọng “chỉ phát kết quả final” nếu dùng cho window-close suppression.

untilWindowCloses() yêu cầu strict buffer config để không làm suy yếu finality. Không dùng eager policy cho bài toán cần final-only output.

### 8.4. Tính capacity theo số key và window đang mở

Ước lượng sơ bộ:

\[
BufferBytes \approx ActiveKeyWindows \times AverageBufferedRecordBytes
\]

Ví dụ:
- 200.000 key-window đang mở.
- Mỗi buffered record trung bình 300 byte.
- Buffer payload xấp xỉ 60 MB, chưa tính overhead store/index/serialization.

Đây chỉ là ước lượng ban đầu. Đo trên dữ liệu thực tế và để headroom cho peak traffic, skew và late event.

## 9. Suppression buffer và phục hồi

Suppression là stateful operation. Buffer giữ các update chưa đủ điều kiện phát, nên cần tính tới:
- Dung lượng buffer.
- Changelog/restore behavior theo cấu hình store và phiên bản.
- Thời gian phục hồi sau restart.
- Disk và network khi restore.
- Standby replica nếu application sử dụng.
- Trạng thái window/grace tại thời điểm restart.

Không giả định buffer là một hàng đợi vô hình không tốn tài nguyên. Hãy kiểm tra state store và internal topic liên quan trong topology thực tế, đặc biệt khi dùng nhiều key-window hoặc grace dài.

Sau restart, application phải phục hồi state và tiếp tục xử lý sao cho kết quả final không bị mất hoặc phát lặp ngoài semantics đã thiết kế. Kiểm thử crash/restart khi buffer đang chứa nhiều update trước khi đưa vào production.

## 10. Kết hợp cache và suppression

Cache và suppression có thể cùng được dùng:

~~~text
Input events
    |
    v
Windowed aggregation
    |
    v
State store cache
    |  coalesce các update gần nhau
    v
Suppression buffer
    |  giữ tới khi window đóng + grace
    v
Final result
    |
    v
Kafka output topic
~~~

Cache giảm số update trung gian được forward tới suppression. Suppression bảo đảm downstream chỉ nhận kết quả theo policy đã chọn.

Không nên tắt cache chỉ vì đã dùng suppression. Cũng không nên cho rằng cache đã bật thì không cần suppression. Chọn theo throughput, write amplification, latency và semantics output.

### 10.1. Cấu hình tổng hợp

~~~java
Properties props = new Properties();

props.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "customer-window-analytics"
);
props.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
props.put(
    StreamsConfig.STATESTORE_CACHE_MAX_BYTES_CONFIG,
    64L * 1024 * 1024
);
props.put(
    StreamsConfig.COMMIT_INTERVAL_MS_CONFIG,
    1_000
);

StreamsBuilder builder = new StreamsBuilder();

KStream<String, OrderEvent> orders =
    builder.stream(
        "orders",
        Consumed.with(Serdes.String(), orderEventSerde)
    );

KTable<Windowed<String>, Long> counts =
    orders
        .selectKey(
            (orderId, event) -> event.customerId()
        )
        .groupByKey(
            Grouped.with(
                Serdes.String(),
                orderEventSerde
            )
        )
        .windowedBy(
            TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)
            )
        )
        .count(
            Materialized.as("customer-order-counts")
        );

KTable<Windowed<String>, Long> finalCounts =
    counts.suppress(
        Suppressed.untilWindowCloses(
            Suppressed.BufferConfig
                .maxBytes(64L * 1024 * 1024)
                .shutDownWhenFull()
        )
    );

finalCounts
    .toStream()
    .to(
        "customer-order-final-counts",
        Produced.with(
            WindowedSerdes.timeWindowedSerdeFrom(String.class),
            Serdes.Long()
        )
    );

KafkaStreams streams =
    new KafkaStreams(builder.build(), props);
~~~

Ví dụ minh họa một topology hoàn chỉnh. Cần bổ sung model OrderEvent, Serde, imports, lifecycle start/close và cấu hình broker phù hợp với project. selectKey() đổi key sang customerId; groupByKey() dẫn tới repartition trước windowed aggregation; suppress() chỉ phát kết quả khi window đã đóng theo stream-time và grace.

## 11. Tác động đến latency và downstream

Suppression đổi latency để giảm số lượng update downstream.

| Cơ chế | Output latency | Số update | Phù hợp |
|---|---|---|---|
| Không cache, không suppression | Thấp | Nhiều | Phản ứng từng update |
| Cache | Phụ thuộc flush | Có thể giảm | Giảm write amplification |
| untilTimeLimit | Theo stream-time limit | Giới hạn theo key | Dashboard, notification có rate limit |
| untilWindowCloses | Sau window end + grace | Một kết quả/key-window | Báo cáo cuối kỳ, settlement |
| Cache + untilWindowCloses | Sau window end + grace | Một kết quả/key-window | Throughput cao và cần final result |

Nếu downstream cần cập nhật gần real-time, untilWindowCloses() có thể quá trễ. Có thể phát hai luồng:
- Một luồng cập nhật sớm để hiển thị trạng thái tạm thời.
- Một luồng final-only để đối soát hoặc settlement.

Không dùng cùng một output contract cho cả provisional và final result nếu downstream cần phân biệt rõ.

## 12. Late events và correction strategy

Late event là record có event timestamp thuộc một window cũ nhưng đến sau khi stream đã tiến triển.

Ví dụ:
- Window kết thúc 10:05.
- Grace đến 10:06.
- Stream-time đã qua 10:06 và final result được phát.
- Một event có timestamp 10:04 đến sau đó.

Event này quá muộn so với grace. Windowed aggregation không cập nhật final result đã đóng theo policy đó.

Các chiến lược:
1. Chọn grace đủ lớn dựa trên phân phối event lateness.
2. Ghi nhận late-record drop metric.
3. Lưu raw event để backfill.
4. Tạo correction event hoặc adjustment topic.
5. Recompute window bị ảnh hưởng trong quy trình riêng.
6. Dùng version/correction marker để downstream phân biệt kết quả hiệu chỉnh.

Không kéo dài suppression buffer vô hạn chỉ để chờ mọi event có thể đến. Nếu nguồn không có giới hạn lateness, cần mô hình correction thay vì chờ mãi.

## 13. Window type và output final

Các loại window có cách đóng khác nhau:

- **Tumbling window:** các khoảng cố định, không chồng lấp.
- **Hopping window:** các khoảng có thể chồng lấp; một event có thể thuộc nhiều window.
- **Sliding window:** cửa sổ trượt theo chênh lệch timestamp của record.
- **Session window:** được gom theo hoạt động và gap; session có thể mở rộng khi event mới đến.

untilWindowCloses() phát final result cho từng window key theo semantics window tương ứng. Với hopping window, một event có thể cập nhật nhiều key-window và suppression sẽ giữ từng kết quả riêng.

Với session window, window end có thể thay đổi khi session được mở rộng. Cần kiểm tra đúng API window và grace behavior của phiên bản Kafka Streams đang dùng.

## 14. Kiểm thử suppression bằng TopologyTestDriver

TopologyTestDriver cho phép gửi record với timestamp xác định và kiểm tra output trước/sau khi stream-time vượt ngưỡng window close.

Ví dụ kiểm thử ý tưởng:

~~~java
@Test
void shouldEmitOnlyFinalWindowCount() {
    StreamsBuilder builder = new StreamsBuilder();

    KStream<String, OrderEvent> orders =
        builder.stream(
            "orders",
            Consumed.with(Serdes.String(), orderEventSerde)
        );

    KTable<Windowed<String>, Long> counts =
        orders
            .selectKey(
                (orderId, event) -> event.customerId()
            )
            .groupByKey(
                Grouped.with(
                    Serdes.String(),
                    orderEventSerde
                )
            )
            .windowedBy(
                TimeWindows.ofSizeAndGrace(
                    Duration.ofMinutes(5),
                    Duration.ofMinutes(1)
                )
            )
            .count();

    counts
        .suppress(
            Suppressed.untilWindowCloses(
                Suppressed.BufferConfig
                    .maxBytes(10L * 1024 * 1024)
                    .shutDownWhenFull()
            )
        )
        .toStream()
        .to(
            "final-counts",
            Produced.with(
                WindowedSerdes.timeWindowedSerdeFrom(String.class),
                Serdes.Long()
            )
        );

    Properties props = new Properties();
    props.put(
        StreamsConfig.APPLICATION_ID_CONFIG,
        "suppression-test"
    );
    props.put(
        StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
        "dummy:9092"
    );

    try (TopologyTestDriver driver =
             new TopologyTestDriver(builder.build(), props)) {

        TestInputTopic<String, OrderEvent> input =
            driver.createInputTopic(
                "orders",
                new StringSerializer(),
                orderEventSerde.serializer()
            );

        TestOutputTopic<Windowed<String>, Long> output =
            driver.createOutputTopic(
                "final-counts",
                WindowedSerdes.timeWindowedSerdeFrom(String.class).deserializer(),
                new LongDeserializer()
            );

        Instant start = Instant.parse("2026-01-01T10:00:00Z");

        input.pipeInput(
            "order-1",
            new OrderEvent("order-1", "customer-7", 100L),
            start.plusSeconds(10)
        );
        input.pipeInput(
            "order-2",
            new OrderEvent("order-2", "customer-7", 200L),
            start.plusSeconds(30)
        );

        assertThat(output.isEmpty()).isTrue();

        // Đẩy stream-time vượt window end 10:05 + grace 1 phút.
        input.pipeInput(
            "order-3",
            new OrderEvent("order-3", "customer-8", 50L),
            start.plusSeconds(7 * 60L)
        );

        List<KeyValue<Windowed<String>, Long>> results =
            output.readKeyValuesToList();

        assertThat(results)
            .anySatisfy(result -> {
                assertThat(result.key.key()).isEqualTo("customer-7");
                assertThat(result.value).isEqualTo(2L);
            });
    }
}
~~~

Đây là ví dụ minh họa; cần có model, Serde, JUnit và AssertJ tương ứng. Test dùng một record timestamp 7 phút để đẩy stream-time qua ngưỡng đóng window. Tùy task/input partitions và Kafka Streams version, cần thiết kế dữ liệu test sao cho timestamp thực sự tiến triển trên task đang giữ suppression buffer.

### 14.1. Những điều TopologyTestDriver không chứng minh

TopologyTestDriver hữu ích cho logic và output semantics nhưng không mô phỏng đầy đủ:
- Broker replication và ISR.
- Network delay và consumer lag.
- ACL trên internal topics.
- Failover giữa các instance.
- State restoration sau process crash.
- Capacity behavior dưới peak traffic thực tế.

Cần integration test với broker thật cho các tình huống restart, restore, buffer pressure và deployment.

## 15. Monitoring suppression và cache

Theo dõi cả state store, stream-time và output:

- Số lượng key/window đang được giữ.
- Buffer size/bytes và buffer full event.
- Suppression rate và số record được phát.
- Late-record drop count.
- Window closure delay.
- State store size và changelog size.
- Restore duration sau restart.
- Commit/flush latency.
- Cache hit/coalescing behavior nếu metric được cung cấp.
- Downstream output rate và consumer lag.

Tên metric phụ thuộc Kafka Streams version và metrics reporter. Không hard-code metric name nếu chưa kiểm tra JMX/Micrometer metrics của client đang chạy.

### 15.1. Cảnh báo quan trọng

- Suppression buffer tiến gần ngưỡng.
- Application dừng do strict buffer full.
- Stream-time không tiến triển trong khi input backlog tăng.
- Window final output trễ hơn SLA.
- Late-record drop tăng bất thường.
- State restore kéo dài sau restart.
- Cache flush liên tục do dung lượng nhỏ.
- Output rate giảm về 0 bất thường.

Một output topic im lặng có thể là hành vi bình thường nếu window chưa đóng. Cần đối chiếu stream-time, grace và input progress trước khi kết luận topology bị treo.

## 16. Runbook khi final output không xuất hiện

1. Kiểm tra input topic có record mới không.
2. Kiểm tra consumer lag và task assignment.
3. Kiểm tra timestamp extractor và timestamp thực tế của record.
4. Xác định stream-time của task có tiến triển không.
5. Tính window end và grace threshold.
6. Kiểm tra record có bị loại vì quá muộn không.
7. Kiểm tra suppression buffer và state store.
8. Kiểm tra task error, buffer-full exception và application logs.
9. Kiểm tra changelog/internal topic và quyền ACL.
10. Kiểm tra output topic và downstream consumer.
11. Nếu restart, theo dõi state restoration và final output sau restore.

Không tăng commit.interval.ms hoặc tắt suppression để “làm output xuất hiện” trước khi xác định nguyên nhân. Những thay đổi đó có thể làm thay đổi latency hoặc semantics.

## 17. Anti-patterns thường gặp

- **Dùng cache thay suppression:** cache có thể flush trước window end.
- **Dùng untilTimeLimit để tạo final window result:** time limit không phải window closure.
- **Nhầm stream-time với wall-clock:** topic idle có thể không phát final đúng theo thời gian đồng hồ.
- **Dùng eager buffer cho final-only:** buffer đầy có thể làm update trung gian được phát sớm.
- **Dùng unbounded buffer không tính capacity:** số key/window lớn có thể làm state và storage tăng mạnh.
- **Chọn grace quá dài:** output final chậm và giữ state/buffer lâu.
- **Chọn grace quá ngắn:** late event bị loại và kết quả final thiếu dữ liệu.
- **Bỏ qua null key:** record không có key có thể không tham gia aggregation theo cách mong muốn.
- **Cho rằng suppression sort record:** suppression giữ update, không sắp xếp theo timestamp nghiệp vụ.
- **Không kiểm thử restart:** buffer/state restore có thể ảnh hưởng thời điểm phát output.
- **Dùng một output cho cả provisional và final:** downstream không phân biệt trạng thái tạm thời với kết quả đã đóng.

## 18. Quy trình lựa chọn cơ chế

| Yêu cầu | Cơ chế nên xem xét |
|---|---|
| Giảm state-store write và update traffic | KTable cache |
| Chỉ phát một kết quả sau khi window đóng | untilWindowCloses với strict buffer |
| Giới hạn tần suất update của key không windowed | untilTimeLimit |
| Cần mọi update gần real-time | Không suppression; cân nhắc cache |
| Cần provisional và final output | Hai nhánh output với contract riêng |
| Nguồn có late event đáng kể | Window grace phù hợp + untilWindowCloses |
| Topic idle nhưng cần deadline wall-clock | Scheduler/punctuation hoặc hệ thống điều phối riêng |
| Buffer không được phép phát sớm | Strict buffer và capacity đủ lớn |

Một trình tự thiết kế tốt:

1. Xác định downstream cần mọi update, latest update hay final window result.
2. Chọn event timestamp và TimestampExtractor.
3. Xác định window size và grace period.
4. Ước lượng active key-window cardinality.
5. Chọn cache size và commit interval.
6. Nếu cần suppression, chọn untilWindowCloses hoặc untilTimeLimit.
7. Chọn buffer maxBytes/maxRecords và strict/eager policy.
8. Kiểm thử late event, stream-time idle, buffer full và restart.
9. Đo output latency, state size, lag và restore time.
10. Viết runbook cho final output trễ hoặc suppression buffer đầy.

## 19. Checklist production

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Output semantics | Downstream cần intermediate, latest hay final result? |
| Cache | Cache đang bật bao nhiêu byte và flush theo điều kiện nào? |
| Commit | commit.interval.ms có phù hợp latency/durability không? |
| Timestamp | TimestampExtractor có đúng event-time không? |
| Stream-time | Có hiểu task stream-time và hành vi khi input idle không? |
| Window | Window size/type có đúng nghiệp vụ không? |
| Grace | Grace phản ánh độ trễ thực tế của event chưa? |
| Suppression | Dùng untilWindowCloses hay untilTimeLimit? |
| Buffer | Có maxBytes/maxRecords và capacity estimate không? |
| Full policy | Buffer full thì shutdown hay emit early? |
| State | Store/changelog/restore đã được kiểm thử chưa? |
| Late events | Có metric và correction/backfill strategy không? |
| Ordering | Downstream có hiểu event-time và sequence không? |
| Monitoring | Có buffer, stream-time, late drop, output delay và lag alert không? |
| Testing | Có test final output, idle stream, late event, restart và buffer pressure không? |

## 20. Kết luận

KTable cache và Suppression đều có thể làm giảm số update mà downstream nhận, nhưng chúng có semantics khác nhau. Cache là tối ưu state store và coalesce các cập nhật trong bộ đệm; nó không bảo đảm chỉ phát kết quả cuối của window. Suppression là toán tử điều khiển thời điểm phát: untilWindowCloses() giữ kết quả đến khi stream-time vượt window end cộng grace, còn untilTimeLimit() giới hạn tần suất update theo key.

Thời gian của suppression dựa trên stream-time, không đơn giản là wall-clock. Vì vậy, topic idle có thể khiến final output chưa xuất hiện dù thời gian thực đã trôi qua. Grace period quyết định mức event lateness được chấp nhận; buffer policy quyết định điều gì xảy ra khi dữ liệu đang chờ vượt capacity.

Trong production, hãy xác định output contract trước, chọn timestamp/window/grace phù hợp, dùng strict buffer nếu cần final-only semantics, ước lượng capacity và kiểm thử late event, stream-time không tiến triển, buffer full cùng state restoration. Theo dõi output delay và late-record drop để biết kết quả final có thực sự phản ánh dữ liệu mà nghiệp vụ mong đợi hay không.

## Tài liệu tham khảo

- Apache Kafka Streams DSL: https://kafka.apache.org/44/streams/developer-guide/dsl-api/
- Apache Kafka Streams configuration: https://kafka.apache.org/44/streams/developer-guide/config-streams/
- Apache Kafka Streams Suppressed API: https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/kstream/Suppressed.html
- Apache Kafka Streams KTable API: https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/kstream/KTable.html
- Apache Kafka Streams TimeWindows API: https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/kstream/TimeWindows.html
