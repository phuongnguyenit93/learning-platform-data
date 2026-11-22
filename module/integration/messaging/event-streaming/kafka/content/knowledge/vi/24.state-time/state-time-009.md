# Retention của cửa sổ, state store và changelog

Kafka Streams giữ state để thực hiện aggregation, join, windowing và truy vấn kết quả theo key hoặc theo khoảng thời gian. State có thể nằm trong local state store của ứng dụng, được sao lưu vào changelog topic trong Kafka và được khôi phục khi task chuyển worker hoặc process khởi động lại.

Retention quyết định dữ liệu nào còn được giữ và trong bao lâu. Với windowed processing, cần phân biệt ba khái niệm: kích thước cửa sổ (window size), khoảng chấp nhận dữ liệu đến muộn (grace period) và thời gian lưu state (retention). Với state store thông thường, không phải loại store nào cũng có TTL tự động. Changelog lại có chính sách compaction/retention riêng để hỗ trợ phục hồi.

Nếu đặt retention quá ngắn, ứng dụng có thể bỏ lỡ late event, không truy vấn được cửa sổ cũ hoặc không khôi phục được state như mong muốn. Nếu đặt quá dài, local disk, changelog và chi phí broker có thể tăng đáng kể.

## 1. Ba lớp dữ liệu cần phân biệt

Một ứng dụng Kafka Streams thường có ba nơi giữ dữ liệu:

1. **Input topic:** lưu record nguồn để consumer có thể đọc hoặc replay theo topic retention.
2. **Local state store:** lưu trạng thái mà task dùng khi xử lý, chẳng hạn tổng đơn hàng theo cửa sổ hoặc số dư mới nhất theo account.
3. **Changelog topic:** lưu thay đổi state store trong Kafka để khôi phục state khi task được tạo lại hoặc chuyển worker.

~~~mermaid
flowchart LR
    I["Input topic<br/>retention của log nguồn"] --> P["Kafka Streams task"]
    P --> L["Local state store<br/>window / key-value"]
    L --> C["Changelog topic<br/>compaction / retention"]
    P --> O["Output topic"]
    C --> R["Restore state khi restart"]
    R --> L
~~~

Ba lớp này có mục đích khác nhau. Giữ input topic lâu không tự động làm local state store giữ dữ liệu lâu hơn. Giữ changelog lâu cũng không đồng nghĩa consumer có thể replay toàn bộ input history nếu input topic đã hết retention.

## 2. Window size, grace period và retention

Với windowed aggregation, cần phân biệt:

- **Window size:** khoảng thời gian event được gom vào cùng một cửa sổ.
- **Grace period:** khoảng thời gian sau khi cửa sổ kết thúc mà Kafka Streams vẫn chấp nhận record đến muộn cho cửa sổ đó.
- **Retention:** thời gian state của cửa sổ được lưu trong window store để có thể truy vấn hoặc phục vụ xử lý.

Ví dụ cửa sổ 5 phút, grace 2 phút và retention 24 giờ:

~~~text
Window:      10:00 ---------------- 10:05
Grace:                               10:05 ---- 10:07
Retention:  state có thể được giữ đến khi hết thời gian lưu theo stream-time
~~~

Một event có timestamp 10:04:30 đến lúc stream-time đã là 10:06 có thể vẫn được chấp nhận vì còn trong grace. Event thuộc cửa sổ kết thúc 10:05 nhưng đến sau khi stream-time vượt 10:07 sẽ bị xem là quá muộn theo chính sách window đó.

Retention 24 giờ cho phép state của cửa sổ tồn tại lâu hơn thời hạn chấp nhận late event. Điều này hữu ích khi cần truy vấn kết quả cửa sổ đã đóng hoặc giữ state cho các nhu cầu downstream.

Với time window, retention phải ít nhất bằng window size cộng grace period. Đối với session window, cần đáp ứng mức tối thiểu theo inactivity gap và grace của session semantics. Kiểm tra ràng buộc của đúng loại window và phiên bản Kafka Streams khi cấu hình.

## 3. Grace không phải retention

Hai khái niệm này thường bị nhầm:

| Thuộc tính | Câu hỏi được trả lời | Tác động |
|---|---|---|
| Window size | Event thuộc khoảng thời gian nào? | Xác định biên cửa sổ |
| Grace period | Event đến muộn đến mức nào vẫn được nhận? | Quyết định late record có được cập nhật window hay không |
| Retention | State của window được giữ trong bao lâu? | Quyết định dữ liệu window còn khả dụng trong store |

Tăng retention không tự động cho phép nhận late event muộn hơn. Muốn chấp nhận late event lâu hơn, cần tăng grace period. Ngược lại, tăng grace không nhất thiết có nghĩa phải giữ window state vô hạn; retention vẫn cần đủ lớn để bao phủ window và grace.

Ví dụ:

- Window size: 5 phút.
- Grace: 2 phút.
- Retention: 24 giờ.

Record đến muộn 10 phút sau khi cửa sổ kết thúc vẫn bị từ chối theo grace, dù state có thể còn tồn tại trong store để truy vấn.

## 4. Stream-time và wall-clock time

Kafka Streams dùng timestamp của record để xác định tiến độ thời gian của stream. Stream-time của task tiến lên theo timestamp quan sát được trong quá trình xử lý; nó không đơn giản là đồng hồ hệ điều hành hiện tại.

Điều này quan trọng với window closure, late event và việc dọn dẹp state:

- Record có timestamp cũ có thể đến sau record timestamp mới.
- Grace period xác định giới hạn chấp nhận record out-of-order.
- Window retention dựa trên thời gian của dữ liệu/stream-time và cách store quản lý segment.
- Nếu input ngừng hoàn toàn, stream-time có thể không tiến lên; việc hết hạn state không nên được hiểu như một wall-clock TTL timer chạy độc lập.

Ví dụ, nếu task đã quan sát timestamp 12:00 nhưng sau đó không nhận thêm record, đồng hồ máy vẫn chạy tới 13:00 không có nghĩa stream-time tự động nhảy tới 13:00. Vì vậy, state/window cleanup có thể không diễn ra theo đúng số phút wall-clock mà người vận hành kỳ vọng.

Nếu nghiệp vụ yêu cầu xử lý theo thời gian thực của hệ thống thay vì timestamp event, cần thiết kế timestamp extractor, punctuator hoặc logic expiry riêng. Không thay grace/retention bằng một giả định rằng Kafka Streams tự động xóa state theo đồng hồ máy.

## 5. Retention cho tumbling, hopping và sliding windows

Các time window thường dùng:

- **Tumbling window:** các cửa sổ cố định, không chồng lấn.
- **Hopping window:** các cửa sổ có advance interval nhỏ hơn window size nên có thể chồng lấn.
- **Sliding window:** cửa sổ trượt theo chênh lệch timestamp của các record.
- **Session window:** nhóm record theo hoạt động, ngăn cách bởi inactivity gap.

Ví dụ tumbling window 5 phút:

~~~text
10:00 - 10:05 | 10:05 - 10:10 | 10:10 - 10:15
      W1      |       W2       |       W3
~~~

Ví dụ hopping window 5 phút, advance 1 phút:

~~~text
W1: 10:00 ---------------- 10:05
W2:        10:01 ---------------- 10:06
W3:               10:02 ---------------- 10:07
~~~

Một record có thể thuộc nhiều hopping/sliding windows. Vì vậy, state size có thể lớn hơn dự đoán nếu chỉ nhân số key với một cửa sổ duy nhất.

Khi chọn retention, cân nhắc:

- Window size và grace.
- Số lượng key khác nhau.
- Số window chồng lấn.
- Kích thước state value.
- Tần suất cập nhật mỗi key.
- Nhu cầu query window đã đóng.
- Số partition và số task.

Không chọn retention chỉ dựa trên thời gian nghiệp vụ; hãy ước lượng cả số lượng entry và kích thước lưu trữ.

## 6. Retention cho session windows

Session window nhóm các record của cùng key nếu khoảng cách giữa các hoạt động không vượt quá inactivity gap. Khi có record mới, hai session có thể được nối/merge nếu khoảng cách thỏa điều kiện.

Ví dụ inactivity gap 10 phút:

~~~text
order/customer A:
10:00, 10:04, 10:12       -> có thể thuộc cùng session
10:40                     -> session mới
~~~

Grace period cho phép record đến muộn làm thay đổi session trong giới hạn cho phép. Retention phải đủ để giữ state session theo quy tắc của loại window và yêu cầu truy vấn.

Với session store, không chỉ đếm số event. Một session có thể được mở rộng hoặc merge, làm thay đổi key/window boundaries và lượng state cần duy trì.

## 7. Cấu hình retention cho window store bằng Java DSL

Ví dụ đếm số đơn hàng theo customer trong tumbling window 5 phút, chấp nhận late event trong 2 phút và giữ window state 24 giờ:

~~~java
KTable<Windowed<String>, Long> orderCounts =
    builder.stream(
            "orders",
            Consumed.with(Serdes.String(), orderSerde)
        )
        .groupByKey()
        .windowedBy(
            TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(2)
            )
        )
        .count(
            Materialized.<String, Long, WindowStore<Bytes, byte[]>>as(
                "order-counts"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
            .withRetention(Duration.ofHours(24))
        );
~~~

Ví dụ này giả định orderSerde, builder và các import cần thiết đã được khai báo. Retention 24 giờ lớn hơn window size cộng grace là 7 phút.

Các điểm cần chú ý:

- Tên store order-counts phải ổn định nếu cần khôi phục state giữa các lần restart.
- withRetention() áp dụng cho store có window/session semantics hỗ trợ retention.
- Không đặt retention thấp hơn mức tối thiểu mà window và grace yêu cầu.
- Nếu muốn query window cũ lâu hơn, cần giữ state đủ lâu và cân nhắc chi phí disk/changelog.

### 7.1. Session store

Ví dụ session count theo customer:

~~~java
KTable<Windowed<String>, Long> sessionCounts =
    builder.stream(
            "customer-activity",
            Consumed.with(Serdes.String(), activitySerde)
        )
        .groupByKey()
        .windowedBy(
            SessionWindows.ofInactivityGapAndGrace(
                Duration.ofMinutes(10),
                Duration.ofMinutes(2)
            )
        )
        .count(
            Materialized.<String, Long, SessionStore<Bytes, byte[]>>as(
                "customer-sessions"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
            .withRetention(Duration.ofDays(2))
        );
~~~

Hãy kiểm tra retention minimum và API overload của session store theo phiên bản Kafka Streams đang dùng. Mức 2 ngày trong ví dụ là quyết định vận hành minh họa, không phải default bắt buộc.

## 8. KeyValueStore thông thường không có TTL tự động

Một KeyValueStore tiêu chuẩn giữ giá trị mới nhất theo key. Kafka Streams không tự động xóa mọi key sau một khoảng thời gian chỉ vì ứng dụng tạo store.

Ví dụ store lưu số dư mới nhất:

~~~java
KeyValueStore<String, BigDecimal> balances =
    (KeyValueStore<String, BigDecimal>) context.getStateStore("balances");
~~~

Nếu account không có event trong 90 ngày, entry không tự động biến mất chỉ vì đã 90 ngày. Muốn có expiry, ứng dụng cần chọn một cơ chế rõ ràng:

- Ghi timestamp cập nhật cùng value và xóa key khi đủ tuổi.
- Dùng punctuator để quét/xử lý expiry theo lịch phù hợp.
- Dùng store chuyên biệt có retention semantics.
- Để hệ thống nguồn quản lý lifecycle và phát tombstone/delete event.

Không nhầm Kafka topic retention với TTL của từng key trong local KeyValueStore. Topic có thể xóa segment theo thời gian, nhưng local state store không tự suy ra rằng key tương ứng phải hết hạn.

### 8.1. Xóa key và changelog tombstone

Khi ứng dụng gọi delete(key) trên một logged state store, Kafka Streams có thể ghi tombstone vào changelog để biểu thị key đã bị xóa. Khi restore, tombstone giúp state store không khôi phục lại giá trị cũ.

Nếu tự xây expiry, cần bảo đảm logic delete được thực thi và changelog được cập nhật. Chỉ ngừng đọc hoặc ngừng truy vấn key không có nghĩa key đã được xóa khỏi store.

## 9. VersionedKeyValueStore và history retention

Kafka Streams có versioned key-value store để lưu nhiều phiên bản value theo timestamp, hỗ trợ truy vấn as-of (lấy giá trị tại một thời điểm trong quá khứ) và xử lý record out-of-order theo semantics của store.

History retention xác định khoảng lịch sử mà store giữ để hỗ trợ truy vấn/ghi phiên bản cũ. Đây không phải TTL đơn giản cho toàn bộ key: giá trị mới nhất của key vẫn là trạng thái hiện tại; retention chủ yếu giới hạn lịch sử phiên bản cũ.

Versioned state stores được hỗ trợ từ các phiên bản Kafka Streams mới hơn (Kafka 3.5 trở lên). Ví dụ tạo supplier:

~~~java
VersionedBytesStoreSupplier supplier =
    Stores.persistentVersionedKeyValueStore(
        "account-history",
        Duration.ofDays(7)
    );

Materialized<String, AccountBalance, KeyValueStore<Bytes, byte[]>> materialized =
    Materialized.<String, AccountBalance>as(supplier)
        .withKeySerde(Serdes.String())
        .withValueSerde(accountBalanceSerde);
~~~

Đây là phần cấu hình store supplier; cách gắn vào aggregation hoặc processor phụ thuộc topology và generic type cụ thể. Kiểm tra API của Kafka Streams release đang sử dụng.

Nếu truy vấn lịch sử cũ hơn history retention, store có thể không còn dữ liệu để trả lời. Chọn retention dựa trên nhu cầu as-of lookup, độ trễ dữ liệu đến muộn và chi phí lưu nhiều version.

## 10. Changelog topic làm nhiệm vụ gì?

Với state store có bật logging (mặc định phổ biến), Kafka Streams ghi các thay đổi state vào internal changelog topic. Khi task cần khởi tạo lại state, framework đọc changelog để tái dựng store.

~~~mermaid
flowchart TD
    A["Input record"] --> B["Update local state store"]
    B --> C["Write changelog record"]
    C --> D["Commit transaction/checkpoint"]
    D --> E["Task moves or process restarts"]
    E --> F["Restore from changelog"]
    F --> G["Local state ready"]
~~~

Changelog không phải output business topic. Consumer nghiệp vụ thường không nên subscribe trực tiếp vào changelog nội bộ.

Một số mục đích của changelog:

- Phục hồi state sau process restart.
- Phục hồi task khi rebalance sang worker khác.
- Duy trì state cho standby replica.
- Khôi phục sau khi local state directory bị mất.
- Đồng bộ thay đổi state giữa local store và Kafka.

Tên changelog topic thường gắn với application ID và store name. Hãy xem metadata/topic list của đúng application thay vì tự suy đoán tên khi thao tác vận hành.

## 11. Compaction và delete retention của changelog

Changelog topic thường dùng log compaction để giữ thông tin cần thiết khôi phục state. Cấu hình cleanup policy phụ thuộc loại store:

- Key-value changelog thường dùng compact, giữ giá trị mới nhất theo key và tombstone cho key bị xóa.
- Window/session changelog có thể dùng compact,delete, vì dữ liệu window cũ cần hết hạn theo retention của store.

Compaction là quá trình nền. Nó không xóa record ngay lập tức khi một value mới xuất hiện. Nhiều phiên bản của key có thể còn tồn tại trong log cho tới khi cleaner xử lý segment.

### 11.1. retention.ms không giống delete.retention.ms

| Cấu hình | Ý nghĩa |
|---|---|
| retention.ms | Thời gian giữ segment khi topic dùng chính sách delete |
| retention.bytes | Giới hạn dung lượng giữ log khi topic dùng chính sách delete |
| cleanup.policy=compact | Giữ giá trị mới nhất theo key sau compaction |
| cleanup.policy=compact,delete | Kết hợp compaction và xóa segment cũ |
| delete.retention.ms | Thời gian tombstone được giữ để consumer có cơ hội quan sát delete trước khi tombstone bị dọn |

delete.retention.ms không phải TTL cho key trong state store. Không giảm nó tùy tiện vì consumer restore hoặc consumer đọc compacted topic cần có đủ thời gian quan sát tombstone.

Với internal changelog topics, Kafka Streams thường tự thiết lập các topic config phù hợp với loại store. Không tự sửa cleanup policy hoặc retention của changelog nếu chưa hiểu yêu cầu restore của ứng dụng.

## 12. Retention của window store liên hệ với changelog ra sao?

Window store giữ dữ liệu theo key và window timestamp. Changelog của store cần đủ thông tin để phục hồi phần state còn trong retention.

Khi cấu hình retention cho window store, Kafka Streams dùng cấu hình đó để quản lý vòng đời dữ liệu window và internal changelog tương ứng. Với windowed changelog, cleanup policy thường kết hợp compaction và delete để vừa giữ cập nhật cần thiết, vừa loại bỏ dữ liệu window quá cũ.

Điều này có nghĩa:

- Retention của store quyết định cửa sổ còn khả dụng trong local state.
- Changelog hỗ trợ restore các entry thuộc phạm vi cần giữ.
- Retention của changelog không nên bị rút ngắn độc lập khỏi store nếu việc đó làm thiếu dữ liệu restore.
- Compaction không phải thao tác xóa tức thời.
- Nếu cần query window lịch sử lâu hơn, hãy đặt store retention phù hợp ngay từ thiết kế.

Không coi changelog là bản backup vĩnh viễn. Changelog có thể compact và expire theo cấu hình. Nếu cần archive lịch sử lâu dài, hãy ghi output/event vào topic hoặc storage được thiết kế cho mục tiêu archive.

## 13. Input topic retention và khả năng replay

Input topic có retention riêng:

~~~properties
cleanup.policy=delete
retention.ms=604800000
~~~

Ví dụ trên giữ log nguồn trong 7 ngày theo thời gian, nếu không bị giới hạn sớm hơn bởi các điều kiện retention khác.

Nếu ứng dụng cần reset/replay từ đầu, input topic phải còn dữ liệu cần replay. Nếu topic đã xóa các segment cũ, Kafka Streams không thể dựng lại lịch sử đã mất chỉ bằng cách reset offset.

Phân biệt:

- **Input topic retention:** thời gian record nguồn còn có thể được đọc lại.
- **Window store retention:** thời gian window state còn khả dụng.
- **Changelog retention/compaction:** dữ liệu state cần cho khôi phục task.
- **Output topic retention:** thời gian kết quả đã phát còn có thể được consumer đọc/replay.

Có thể giữ input topic ngắn hơn changelog nếu mục tiêu là phục hồi state hiện tại nhanh chóng từ changelog. Nhưng khi cần rebuild state từ đầu, source history phải còn đủ lâu hoặc phải có snapshot/archive khác.

## 14. State restore và standby replicas

Khi task được chuyển sang worker khác, Kafka Streams cần khôi phục state store. Với logged store, framework đọc changelog từ offset đã lưu để tái dựng state.

Thời gian restore phụ thuộc:

- Kích thước changelog cần đọc.
- Số partition và tốc độ broker.
- Local state còn tồn tại hay phải restore toàn bộ.
- Compaction và số record cần replay.
- Network, disk throughput và RocksDB performance.

Có thể cấu hình standby replicas để duy trì bản state dự phòng trên worker khác:

~~~properties
num.standby.replicas=1
~~~

Standby task đọc changelog để cập nhật state gần với active task. Khi active task chuyển worker, standby có thể được promote, giảm thời gian restore. Đổi lại, standby dùng thêm CPU, network, disk và task capacity.

Standby replica không thay thế replication factor của changelog topic và không phải backup độc lập. Nó là một cơ chế giảm thời gian phục hồi trong cùng hệ thống Kafka Streams.

## 15. Logging của state store

State store thường bật changelog logging để hỗ trợ fault tolerance. Một số store có thể được cấu hình tắt logging:

~~~java
Materialized.<String, Long, KeyValueStore<Bytes, byte[]>>as("temporary-counts")
    .withKeySerde(Serdes.String())
    .withValueSerde(Serdes.Long())
    .withLoggingDisabled();
~~~

Chỉ tắt logging khi ứng dụng chấp nhận mất local state khi task được khởi tạo lại hoặc có thể tái tạo state bằng một cách khác đáng tin cậy. Nếu store là kết quả của việc đọc input history mà input retention không đủ, tắt changelog có thể làm state không thể phục hồi.

Một số store hoặc topology có thể có yêu cầu đặc thù; kiểm tra tài liệu Kafka Streams và semantics của operator trước khi thay đổi logging.

## 16. Ước lượng dung lượng state và changelog

Retention càng dài, dữ liệu cần giữ càng nhiều. Một ước lượng ban đầu cho window store:

\[
\text{State bytes} \approx
\text{active keys}
\times
\text{windows per key}
\times
\text{average value bytes}
\]

Sau đó cộng overhead của key, timestamp, index, RocksDB, segment và changelog.

Ví dụ:

- 500.000 customer key hoạt động.
- Trung bình 24 window còn giữ cho mỗi key.
- Value trung bình 80 byte.

Payload thô ước lượng:

\[
500{,}000 \times 24 \times 80
= 960{,}000{,}000 \text{ bytes}
\]

Khoảng 960 MB trước khi tính overhead. Đây không phải dung lượng disk cuối cùng; RocksDB index, block cache, compaction, serialization và replication làm con số thực tế khác đi.

Khi retention tăng từ 24 giờ lên 7 ngày, số window được giữ có thể tăng gần tuyến tính nếu lượng event/key phân bố đều. Với hopping windows chồng lấn hoặc hot key, mức tăng có thể khác đáng kể.

Theo dõi cả local state directory và broker storage. Chỉ nhìn kích thước changelog topic không phản ánh toàn bộ disk mà RocksDB sử dụng.

## 17. Thay đổi retention sau khi ứng dụng đã chạy

Thay đổi retention có thể ảnh hưởng state đang tồn tại và cách task restore. Trước khi triển khai:

1. Xác định loại store và retention hiện tại.
2. Xác định grace/window constraints.
3. Ước lượng dung lượng tăng/giảm.
4. Kiểm tra changelog topic config và replication.
5. Xem ứng dụng có cần query dữ liệu cũ hơn không.
6. Xác định có cần rebuild/replay hay không.
7. Triển khai cấu hình mới trong môi trường test.
8. Theo dõi task restart, restore time, local disk và broker storage.

Tăng retention không nhất thiết khôi phục được dữ liệu đã bị xóa trước đó. Giảm retention có thể làm các window cũ biến mất sớm hơn mong muốn. Với thay đổi lớn, có thể cần store name/application ID mới và migration có kiểm soát, nhưng đổi ID sẽ tạo vòng đời state khác; không dùng cách này như một thao tác cấu hình vô hại.

Không chỉnh sửa trực tiếp changelog internal topic để ép retention của store. Ưu tiên cấu hình qua Kafka Streams DSL/configuration và kiểm tra kết quả do framework tạo.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Late event bị bỏ dù state còn trong store | Grace period đã hết | Điều chỉnh grace và kiểm tra stream-time |
| Window cũ không query được | Window store retention đã hết | Tăng retention nếu cần query lịch sử |
| Local state lớn dần | Retention dài, cardinality cao hoặc key không được xóa | Đo số entry, expiry logic và RocksDB disk |
| Restart mất state | Store logging bị tắt hoặc changelog không đủ | Kiểm tra logging, changelog và input replay plan |
| Restore rất chậm | Changelog lớn hoặc local state mất | Kiểm tra restore rate, standby replicas và storage |
| Changelog topic đầy | Retention/compaction không phù hợp hoặc lượng update lớn | Kiểm tra cleanup policy, segment và broker storage |
| Key bị khôi phục lại sau delete | Tombstone không được xử lý đúng hoặc custom store logic sai | Kiểm tra changelog tombstone và restore |
| Input replay không đủ dữ liệu | Source topic retention đã xóa lịch sử | Tăng input retention hoặc dùng archive/snapshot |
| State không hết hạn khi không có event | Cleanup dựa vào stream-time chứ không phải wall clock | Thiết kế expiry theo clock/punctuator nếu nghiệp vụ yêu cầu |
| Tăng retention nhưng không có dữ liệu cũ | Dữ liệu đã expire trước khi đổi cấu hình | Cần nguồn archive hoặc replay nếu còn dữ liệu |

## 19. Checklist thiết kế retention

- [ ] Đã phân biệt input topic, local state store, changelog và output topic.
- [ ] Window size phản ánh đúng khoảng nghiệp vụ.
- [ ] Grace period phù hợp độ trễ/out-of-order của event.
- [ ] Retention của time window không thấp hơn window size cộng grace.
- [ ] Session store retention đáp ứng inactivity gap và grace.
- [ ] Đã xác định stream-time khác wall-clock time.
- [ ] Không giả định KeyValueStore có TTL mặc định.
- [ ] Nếu dùng versioned store, history retention đáp ứng nhu cầu as-of query.
- [ ] State store logging được bật nếu cần fault tolerance.
- [ ] Changelog cleanup policy phù hợp loại store.
- [ ] Không nhầm retention.ms với delete.retention.ms.
- [ ] Input topic retention đủ cho replay/reset plan.
- [ ] Changelog retention đủ cho restore theo store semantics.
- [ ] Replication factor và min ISR của internal topics phù hợp.
- [ ] Đã ước lượng local disk, changelog storage và compaction overhead.
- [ ] Standby replicas được cân nhắc theo RTO và tài nguyên.
- [ ] Thay đổi retention có kế hoạch test, rollout và rollback.
- [ ] Có metric cho local state size, restore latency, changelog lag và topic storage.

Retention của window, state store và changelog giải quyết các vấn đề khác nhau. Window size xác định khoảng gom event, grace xác định giới hạn chấp nhận late event, còn retention quyết định state được giữ để query và phục hồi trong bao lâu. KeyValueStore thông thường không tự có TTL; changelog dùng compaction và retention theo loại store để hỗ trợ restore. Hãy lập kế hoạch đồng thời cho input topic replay, local state, changelog và dung lượng broker để ứng dụng vừa xử lý đúng dữ liệu đến muộn vừa phục hồi được sau sự cố.
