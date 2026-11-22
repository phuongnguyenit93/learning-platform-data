# Consumer group, consumer và vị trí đọc của nhóm trong Redis Streams với Spring Data Redis

## 1. Vì sao Redis Streams cần consumer group?

Redis Streams lưu các bản ghi (*entry*) theo ID có thứ tự trong một stream. Publisher ghi bằng `XADD`, consumer có thể đọc bằng `XREAD`. Khi có nhiều instance cùng xử lý một loại công việc, mỗi instance đọc độc lập toàn bộ stream có thể khiến một sự kiện được thực hiện nhiều lần. **Consumer group** giải quyết bài toán phân phối bản ghi mới giữa nhiều consumer cùng nhóm, đồng thời theo dõi các bản ghi đã giao nhưng chưa được xác nhận hoàn tất.

Ví dụ:

```text
Stream: orders:events
    ID 100-0    OrderCreated(42)
    ID 101-0    OrderCreated(43)
    ID 102-0    OrderCreated(44)

Group: order-workers
    consumer worker-A    nhận ID 100-0, 102-0
    consumer worker-B    nhận ID 101-0

Group khác: audit-workers
    consumer audit-A     cũng có thể nhận cả ba ID
```

Các consumer **trong cùng group** phối hợp để mỗi bản ghi mới thường được giao cho một consumer của group. **Hai group khác nhau** có vị trí đọc riêng nên đều có thể nhận cùng một bản ghi. Consumer group là cơ chế phân phối và ghi nhận pending, không tự bảo đảm nghiệp vụ được xử lý chính xác một lần (*exactly once*).

Trong Spring Data Redis, các API liên quan gồm `StreamOperations`, `Consumer.from(...)`, `StreamOffset`, `ReadOffset` và `StreamMessageListenerContainer`.

## 2. Stream, consumer group và consumer khác nhau thế nào?

| Thành phần | Phạm vi | Trách nhiệm |
| --- | --- | --- |
| **Stream** | Một Redis key, ví dụ `orders:events` | Lưu các record và field/value của từng record. |
| **Consumer group** | Một tên group gắn với stream | Theo dõi vị trí giao các message mới và danh sách pending của group. |
| **Consumer** | Một danh tính thuộc group, ví dụ `worker-A` | Nhận message được phân phối và sở hữu các pending record cho đến khi ACK/claim. |
| **Pending Entries List (PEL)** | Cấu trúc quản lý của group, gồm thông tin theo consumer | Ghi nhận record đã giao nhưng chưa được xác nhận bằng `XACK`. |

Một stream có thể có nhiều group. Một group có nhiều consumer. Tên consumer không phải tên thread hoặc kết nối TCP bắt buộc, mà là **danh tính logic** được Redis ghi trong metadata.

Cần phân biệt ba câu hỏi:

1. **Record có còn trong stream không?** Dùng `XRANGE` hoặc `XREVRANGE`.
2. **Group đã giao record mới tới đâu?** Dùng `XINFO GROUPS` xem `last-delivered-id`.
3. **Record đã được xử lý và ACK chưa?** Dùng `XPENDING` và trạng thái nghiệp vụ bên ngoài Redis.

Có thể group đã giao record mới nhất trong stream nhưng vẫn còn hàng nghìn bản ghi cũ đang pending. **Vị trí giao mới khác vị trí xử lý thành công.**

## 3. ID của stream và các ký hiệu đặc biệt

Record ID phổ biến có dạng:

```text
<millisecondsTime>-<sequenceNumber>
1700000000000-0
1700000000000-1
1700000000001-0
```

Khi gọi `XADD orders:events * ...`, Redis tự chọn ID. Dấu `*` khi ghi không mang ý nghĩa đọc mới trong consumer group.

| Ký hiệu | Ngữ cảnh | Ý nghĩa |
| --- | --- | --- |
| `0-0` | `XGROUP CREATE` / `XGROUP SETID` | Mốc thấp nhất: group mới có thể nhận cả record đã có trong stream. |
| `$` | `XGROUP CREATE` | Mốc ID cuối stream tại lúc tạo group: bỏ qua backlog trước khi group được tạo. |
| `>` | `XREADGROUP` | Xin record **chưa được giao cho consumer nào của group**. |
| `0` hoặc `0-0` | `XREADGROUP` | Duyệt pending của **chính consumer đang gọi**, không phải toàn bộ stream. |
| ID cụ thể | `XREADGROUP` | Duyệt các pending ID lớn hơn mốc đó của chính consumer. |

Hai ký hiệu hay bị nhầm nhất là `$` và `>`: `$` là mốc cuối stream khi chọn vị trí khởi tạo group; `>` là yêu cầu Redis giao các bản ghi mới theo vị trí hiện tại của group.

## 4. Tạo group bắt đầu từ lịch sử hay từ hiện tại

Giả sử đã có một số record:

```redis
XADD orders:events * type created orderId 42
XADD orders:events * type created orderId 43
XADD orders:events * type created orderId 44
```

### 4.1. Tạo group từ `0-0`

```redis
XGROUP CREATE orders:events order-workers 0-0
```

Group mới bắt đầu ở ID thấp nhất. Consumer đọc bằng `>` có thể nhận các record cũ còn lưu trong stream, rồi nhận record tiếp tục được ghi sau đó. Đây là lựa chọn khi nhóm cần xử lý toàn bộ backlog còn được giữ lại.

“Lịch sử” không có nghĩa dữ liệu đã bị `XDEL` hoặc `XTRIM` cũng được phát lại; Redis không khôi phục record đã xóa chỉ nhờ việc tạo group ở `0-0`.

### 4.2. Tạo group từ `$`

```redis
XGROUP CREATE orders:events order-workers $
```

Vị trí bắt đầu bằng ID cuối của stream tại thời điểm tạo group. Các record đã có trước đó không được phân phối qua đường đọc message mới bằng `>`. Cách này phù hợp khi chỉ cần nhận những sự kiện phát sinh **sau khi bật group**.

Chọn `$` nhầm khi cần xử lý backlog sẽ khiến nhiều record cũ bị bỏ qua theo vị trí đọc nhóm. Chúng có thể vẫn còn trong stream, nhưng không tự xuất hiện ở lần `XREADGROUP ... >` tiếp theo.

### 4.3. Khi stream chưa tồn tại

```redis
XGROUP CREATE orders:events order-workers 0-0 MKSTREAM
```

`MKSTREAM` tạo stream rỗng trước khi tạo group. Lệnh này hữu ích trong bootstrap. Nếu group đã tồn tại, `XGROUP CREATE` báo `BUSYGROUP`. Nên xử lý tình huống group đã được tạo một cách có chủ đích thay vì luôn reset vị trí của group mỗi lần deploy.

## 5. Consumer đọc record mới bằng `XREADGROUP ... >`

Ví dụ consumer A:

```redis
XREADGROUP GROUP order-workers worker-A COUNT 2 BLOCK 2000 STREAMS orders:events >
```

| Thành phần | Ý nghĩa |
| --- | --- |
| `GROUP order-workers worker-A` | Tên group và tên consumer; Redis có thể tạo consumer này khi nó đọc lần đầu. |
| `COUNT 2` | Đề nghị tối đa hai record trong một lần đọc. |
| `BLOCK 2000` | Chờ tối đa 2.000 ms nếu hiện chưa có record mới. |
| `STREAMS orders:events >` | Đọc record chưa từng được giao trong group. |

Consumer B:

```redis
XREADGROUP GROUP order-workers worker-B COUNT 2 BLOCK 2000 STREAMS orders:events >
```

Mỗi record được Redis giao cho một consumer đang gọi `XREADGROUP` của group và thường được đưa vào PEL. **Redis không áp dụng round-robin cân bằng tuyệt đối**: consumer nào poll nhiều hơn, nhanh hơn hoặc dùng batch lớn hơn có thể nhận nhiều record hơn.

Nếu worker-A đã nhận record nhưng chưa `XACK` rồi đột ngột ngừng chạy, worker-B chỉ đọc `>` **không tự nhận lại** record pending của A. Muốn phục hồi record ấy, phải đọc pending đúng consumer hoặc dùng cơ chế claim.

### Nhiều group vẫn nhận được cùng record

Ngoài `order-workers`, một `audit-workers` có thể có:

```redis
XGROUP CREATE orders:events audit-workers 0-0
XREADGROUP GROUP audit-workers audit-A STREAMS orders:events >
```

Audit group có tiến độ và PEL độc lập với order-workers. Xử lý và ACK trong audit-workers không xác nhận thay cho order-workers.

## 6. Vị trí đọc của group: `last-delivered-id`

Redis theo dõi ID cuối được group đánh dấu đã giao ở đường đọc mới thông qua metadata `last-delivered-id`. Có thể xem:

```redis
XINFO GROUPS orders:events
```

Ví dụ kết quả rút gọn:

```text
name              order-workers
consumers         2
pending           3
last-delivered-id 1700000000002-0
entries-read      ...
lag               ...
```

Điều này cho biết group đã giao record mới đến ID `1700000000002-0`, **nhưng vẫn có ba record pending**. Vì vậy `last-delivered-id` không tương đương “ID cuối đã xử lý thành công” hoặc “ID cuối đã ACK”.

Một số phiên bản Redis có các trường `entries-read` và `lag` để hỗ trợ theo dõi backlog. `lag` có thể không xác định trong một số trường hợp như thay đổi vị trí đặc biệt hoặc thiếu thông tin chuỗi ID; đừng tự coi giá trị không xác định là 0.

### Group cursor và consumer cursor có giống nhau?

Không. Các consumer trong cùng group phối hợp quanh **vị trí giao message mới của group**. Mỗi consumer có một tập pending thuộc quyền sở hữu của nó, nhưng không có một luồng message mới độc lập giống hai client `XREAD` trên cùng stream.

Khi group giao ID mới hơn, pending cũ vẫn có thể tồn tại. Group cursor tiến lên **không tự ACK**, cũng không xóa các pending đã giao.

## 7. Pending Entries List (PEL) lưu gì?

Khi `XREADGROUP` giao một record, Redis thường thêm metadata vào PEL:

```text
ID 1700000000000-0
    owner: worker-A
    idle time: thời gian từ lần giao/claim liên quan
    delivery count: số lần được giao theo metadata Redis
```

PEL thể hiện “record đã giao nhưng chưa ACK”, không kết luận rằng ứng dụng đang thực hiện, đã thành công hay thất bại.

Sử dụng:

```redis
XPENDING orders:events order-workers
XPENDING orders:events order-workers - + 10
```

Lệnh thứ nhất trả thông tin tổng quan như số pending, ID nhỏ nhất/lớn nhất và phân bố theo consumer. Lệnh thứ hai trả chi tiết một số ID, consumer đang sở hữu, thời gian idle và số lần delivery.

Một pending lâu có thể do tiến trình bị chết, lỗi logic, phụ thuộc bên ngoài chậm hoặc record đặc biệt khó xử lý. Cần kết hợp metric ứng dụng trước khi can thiệp.

## 8. `XACK` xác nhận xử lý, nhưng không xóa stream entry

Sau khi xử lý thành công một record:

```redis
XACK orders:events order-workers 1700000000000-0
```

Redis loại record đó khỏi PEL của group. **Dữ liệu record vẫn tồn tại trong stream** cho tới khi bị xóa/trim theo chính sách lưu giữ.

| Lệnh | Vị trí giao mới của group | PEL | Dữ liệu stream |
| --- | --- | --- | --- |
| `XREADGROUP ... >` | Có thể tiến | Thêm pending mới | Vẫn còn |
| `XACK` | Không phải lệnh dịch cursor | Xóa pending đã xác nhận | Vẫn còn |
| `XDEL` | Không trực tiếp xác nhận tiến độ xử lý | Có thể khiến pending không còn payload để xử lý lại | Xóa entry |
| `XTRIM` | Không tự quyết định mọi group đã ACK | Có thể ảnh hưởng pending nếu trim trước khi xử lý | Cắt bỏ entry |

Ví dụ:

```redis
XLEN orders:events
XACK orders:events order-workers 1700000000000-0
XLEN orders:events
```

`XLEN` không giảm chỉ vì `XACK`. ACK thuộc phạm vi group; retention thuộc phạm vi stream.

Nếu ACK **trước** khi ghi dữ liệu nghiệp vụ xong, rồi worker chết, công việc có thể bị mất ở cấp ứng dụng vì record không còn pending. Nếu ghi dữ liệu thành công **trước** ACK rồi worker chết, record có thể được xử lý lại. Vì vậy cần ACK sau khi xử lý thành công và thiết kế **idempotency** cho side effect.

## 9. Khác biệt quyết định: `XREADGROUP ... >` và `XREADGROUP ... 0`

### Đọc message mới của group: `>`

```redis
XREADGROUP GROUP order-workers worker-A COUNT 10 STREAMS orders:events >
```

Lệnh tìm các record chưa từng được giao trong group. Nó **không trả lại pending của worker-A hoặc worker-B** chỉ vì chúng chưa ACK.

### Đọc lại pending của chính consumer: `0`

```redis
XREADGROUP GROUP order-workers worker-A COUNT 10 STREAMS orders:events 0
```

Lệnh đọc pending do **worker-A** đang sở hữu, bắt đầu từ mốc thấp. Nó không đọc lại toàn stream và cũng không lấy pending của worker-B.

Với ID cụ thể:

```redis
XREADGROUP GROUP order-workers worker-A COUNT 10 STREAMS orders:events 1700000000000-0
```

Redis duyệt các pending ID lớn hơn mốc đưa vào. Có thể dùng để phân trang pending theo record ID.

| Lệnh | Dữ liệu được trả |
| --- | --- |
| `XREADGROUP GROUP g A STREAMS s >` | Record mới chưa được giao trong group g |
| `XREADGROUP GROUP g A STREAMS s 0` | Pending đang thuộc A |
| `XREADGROUP GROUP g B STREAMS s 0` | Pending đang thuộc B |
| `XAUTOCLAIM s g B ...` | Pending đủ idle được chuyển quyền sở hữu sang B |

Để tạo group mới đọc từ đầu stream, chọn `0-0` tại **`XGROUP CREATE`**, sau đó vẫn đọc message mới bằng `>`. Đổi mã polling sang ID `0-0` trong một group đang hoạt động không có tác dụng reset group để đọc toàn bộ stream.

## 10. Consumer bị lỗi: `XCLAIM` và `XAUTOCLAIM`

Nếu worker-A chết sau khi nhận message, pending của A vẫn tồn tại. Redis không tự đẩy pending sang worker-B qua `>`. Có thể dùng thao tác claim.

### Tiếp quản một ID bằng `XCLAIM`

```redis
XCLAIM orders:events order-workers worker-B 60000 1700000000000-0
```

Trong đó `60000` là thời gian idle tối thiểu tính bằng mili giây. Khi claim thành công, record được gán lại cho worker-B để xử lý và ACK trong cùng group.

### Duyệt và claim bằng `XAUTOCLAIM`

Redis 6.2 trở lên hỗ trợ:

```redis
XAUTOCLAIM orders:events order-workers worker-B 60000 0-0 COUNT 20
```

Lệnh quét PEL từ cursor `0-0`, tìm record idle đủ lâu, claim cho worker-B và trả những record được claim cùng cursor dùng cho lượt quét tiếp. Khi có nhiều pending, tiếp tục dùng cursor trả về cho đến khi hoàn thành vòng duyệt; các pending mới có thể xuất hiện sau đó.

Một số phiên bản Redis còn trả danh sách ID đã được dọn khỏi PEL vì record tương ứng đã bị xóa khỏi stream. Do đó cần chấp nhận trường hợp pending metadata tồn tại nhưng không còn payload để xử lý.

**Claim không chứng minh worker cũ đã chết.** Worker-A có thể đang xử lý một nhiệm vụ dài. Claim quá sớm khiến A và B cùng thực hiện side effect. Ngưỡng idle cần dựa trên latency thực tế và ứng dụng vẫn cần idempotency hoặc cơ chế fencing phù hợp.

### Đừng xóa consumer để “khởi động lại” pending

`XGROUP DELCONSUMER` loại metadata của consumer và pending gắn với consumer ấy theo semantics lệnh. Nên kiểm tra/chuyển pending trước khi xóa consumer. Nếu worker chỉ đổi tên sau restart, việc đọc `>` trên tên mới không tự giải cứu pending của tên cũ.

## 11. Spring Data Redis: `Consumer`, `ReadOffset` và `StreamOffset`

Mapping giữa Redis và Java:

| Redis | Spring Data Redis |
| --- | --- |
| Stream key `orders:events` | `StreamOffset.create("orders:events", ...)` |
| Group `order-workers` | `Consumer.from("order-workers", "worker-A")` |
| Đọc mới bằng `>` | `ReadOffset.lastConsumed()` khi đọc consumer group |
| Đọc qua `XREADGROUP` | `StreamOperations.read(Consumer, options, offsets)` |
| ACK một ID | `opsForStream().acknowledge(stream, group, recordId)` |
| Polling và callback | `StreamMessageListenerContainer` |

Điểm cần hiểu là `ReadOffset.lastConsumed()` **trong chế độ consumer group** được sử dụng cho yêu cầu message mới theo tiến độ của group, tương ứng `>`. Nó không có nghĩa “ID cuối consumer A đã ACK”.

### 11.1. Polling một batch qua `StringRedisTemplate`

```java
import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderStreamPoller {

    private final StringRedisTemplate redis;

    public OrderStreamPoller(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void pollOnce() {
        List<MapRecord<String, Object, Object>> messages =
                redis.opsForStream().read(
                        Consumer.from("order-workers", "worker-A"),
                        StreamReadOptions.empty()
                                .count(10)
                                .block(Duration.ofSeconds(2)),
                        StreamOffset.create(
                                "orders:events",
                                ReadOffset.lastConsumed()));

        if (messages == null) {
            return;
        }

        for (MapRecord<String, Object, Object> message : messages) {
            try {
                String orderId = String.valueOf(
                        message.getValue().get("orderId"));

                // Xử lý nghiệp vụ có idempotency.
                processOrder(orderId);

                redis.opsForStream().acknowledge(
                        "orders:events",
                        "order-workers",
                        message.getId());
            } catch (Exception ex) {
                // Ghi log/metric; không ACK để còn pending.
                // Phải có cơ chế xử lý lại pending riêng.
            }
        }
    }

    private void processOrder(String orderId) {
        // Triển khai logic nghiệp vụ của ứng dụng.
    }
}
```

Ví dụ này giả định stream chứa field `orderId` ở định dạng mà `StringRedisTemplate` đọc được. Khi dùng custom serializer hoặc object mapping, các kiểu generic và cách giải mã cần điều chỉnh tương ứng.

Lưu ý mã trên là ví dụ về **đọc message mới**, chưa có worker đọc lại pending, policy retry hoặc dead-letter; cần bổ sung chúng khi ứng dụng phải bảo đảm việc xử lý.

### 11.2. Dùng `StreamMessageListenerContainer`

Listener dạng callback:

```java
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamListener
        implements StreamListener<String,
                MapRecord<String, String, String>> {

    private final StringRedisTemplate redis;

    public OrderStreamListener(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public void onMessage(MapRecord<String, String, String> message) {
        try {
            String orderId = message.getValue().get("orderId");
            String recordId = message.getId().getValue();

            processIdempotently(orderId, recordId);

            redis.opsForStream().acknowledge(
                    "orders:events",
                    "order-workers",
                    message.getId());
        } catch (Exception ex) {
            // Ghi thông tin lỗi và record ID.
            // Không ACK khi chưa hoàn tất xử lý.
        }
    }

    private void processIdempotently(String orderId, String recordId) {
        // Ví dụ: ghi kết quả kèm unique business/event ID.
    }
}
```

Cấu hình container:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;

@Configuration
public class StreamConsumerConfiguration {

    @Bean
    public StreamMessageListenerContainer<String,
            MapRecord<String, String, String>> streamContainer(
            RedisConnectionFactory connectionFactory,
            OrderStreamListener listener) {

        var options = StreamMessageListenerContainer
                .StreamMessageListenerContainerOptions
                .<String, MapRecord<String, String, String>>builder()
                .pollTimeout(Duration.ofSeconds(2))
                .batchSize(10)
                .keySerializer(RedisSerializer.string())
                .hashKeySerializer(RedisSerializer.string())
                .hashValueSerializer(RedisSerializer.string())
                .build();

        var container = StreamMessageListenerContainer
                .create(connectionFactory, options);

        container.receive(
                Consumer.from("order-workers", "worker-A"),
                StreamOffset.create(
                        "orders:events",
                        ReadOffset.lastConsumed()),
                listener);

        return container;
    }
}
```

Container là Spring bean có lifecycle để bắt đầu/dừng các subscription. Tên `worker-A` là minh họa; trong triển khai nhiều instance, nên cấu hình **một tên consumer phân biệt cho mỗi instance đang hoạt động**. Nếu hai tiến trình cùng dùng một tên consumer, việc quan sát owner/recovery trở nên khó kiểm soát. Ngược lại, khi consumer đổi tên sau restart, pending gắn với tên cũ vẫn cần được claim hoặc phục hồi theo thiết kế.

Trong ứng dụng dùng cấu hình serialization khác, cần khai báo key/hash-key/hash-value serializer tương ứng. Container xử lý polling/callback; **không tự tạo group, tự ACK mọi nghiệp vụ hoặc tự claim tất cả pending cũ**.

## 12. Chọn `ReadOffset` cần căn cứ vào chế độ đọc

Spring Data Redis có các cách tạo read offset, nhưng **cùng một offset có thể có ý nghĩa khác trong XREAD và XREADGROUP**.

| Cách chọn | Khi đọc stream trực tiếp (không group) | Khi đọc với consumer group |
| --- | --- | --- |
| `ReadOffset.from("0-0")` | Bắt đầu từ sau ID cho trước trong dữ liệu stream | Có thể duyệt pending của chính consumer; không tạo group lại từ đầu |
| `ReadOffset.latest()` | Chọn mốc cuối hiện tại, tương tự `$` | Không phải lựa chọn tiêu chuẩn để poll message mới của group |
| `ReadOffset.lastConsumed()` | Dựa vào vị trí đã dùng theo abstraction | Trong consumer group, dùng để xin record mới (`>`) |

**Muốn xử lý backlog từ đầu:** tạo group ở `0-0` rồi poll với `lastConsumed()`.

**Muốn chỉ xử lý message phát sinh sau thời điểm khởi tạo:** tạo group ở `$` rồi poll với `lastConsumed()`.

Hãy tách hai quyết định: *group bắt đầu ở đâu* (do `XGROUP CREATE`/`SETID`) và *consumer muốn lấy message mới hay pending* (do `>`/ID trong `XREADGROUP`).

Nếu dùng `ReadOffset.latest()` để polling stream **không group**, message xuất hiện giữa hai lượt có thể bị bỏ qua khi lần poll sau lại chọn mốc cuối hiện tại. Trong consumer group, `lastConsumed()` tránh cách dùng offset “latest” gây nhầm lẫn đó cho đường nhận message mới.

## 13. Xử lý pending khi ứng dụng restart

Tình huống:

```text
worker-A nhận record 100-0 qua XREADGROUP ... >
worker-A ghi thành công vào database
worker-A mất kết nối trước XACK

Redis:
  record 100-0 vẫn pending và owner = worker-A

worker-B đọc bằng >:
  chỉ nhận các record mới, KHÔNG tự nhận 100-0

Recovery:
  worker-A đọc pending của mình từ ID 0, hoặc
  worker-B claim 100-0 khi đủ thời gian idle
```

Nếu worker-B xử lý lại 100-0, tác dụng phụ đã ghi ở database có thể xảy ra lần hai. Vì vậy cần dùng record ID/event ID/ID nghiệp vụ làm khóa idempotency, ví dụ unique constraint ở database trong cùng transaction với thao tác thay đổi nghiệp vụ.

Một chính sách thực tế:

1. Poll record mới qua `lastConsumed()`.
2. ACK **sau khi** hoàn tất tác dụng phụ bền vững.
3. Khi handler thất bại, giữ pending; ghi lỗi có giới hạn.
4. Theo dõi tuổi pending và số lần delivery.
5. Có tiến trình duyệt pending của consumer hoặc `XAUTOCLAIM` theo ngưỡng idle hợp lý.
6. Giới hạn retry, có dead-letter stream/record lỗi cho message không xử lý được; chỉ ACK message nguồn khi đã xác nhận chuyển thông điệp sang nơi xử lý tiếp theo thành công theo chính sách.
7. Cân chỉnh concurrency và batch size để pending không tăng không kiểm soát.

Không có đường phục hồi pending thì consumer group dù lưu PEL vẫn có thể để công việc “kẹt” vô thời hạn.

## 14. Thay đổi vị trí group bằng `XGROUP SETID`

Redis hỗ trợ chỉnh vị trí đọc group:

```redis
XGROUP SETID orders:events order-workers 0-0
```

Lệnh này chỉnh **last-delivered-id**. Nó không phải lệnh rollback mọi thay đổi do consumer đã gây ra, không tự xóa PEL và không reset trạng thái nghiệp vụ. Nếu đặt vị trí lùi, một số message cũ có thể được xem xét lại ở đường đọc mới, tạo nguy cơ trùng. Nếu đặt vị trí tiến tới cuối, một số backlog có thể bị bỏ qua.

Cần chú ý:

- Những record đã bị xóa khỏi stream không thể phục hồi nhờ `SETID`.
- Pending hiện có cần được kiểm soát riêng.
- Đặt cursor trong lúc nhiều worker đang chạy có thể gây kết quả khó dự đoán.
- Khởi tạo group idempotent không nên tự động chạy `SETID` ở mỗi lần deploy.

Nếu cần replay một tập dữ liệu độc lập, đôi khi tạo **consumer group mới** với mốc phù hợp là phương án dễ kiểm soát hơn reset group sản xuất.

## 15. Retention của stream khác trạng thái ACK của group

Các lệnh quan sát:

```redis
XLEN orders:events
XRANGE orders:events - + COUNT 10
XINFO STREAM orders:events
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events order-workers
XPENDING orders:events order-workers
```

- `XLEN` đo số record còn lưu.
- `XRANGE` xem các record hiện còn.
- `XINFO STREAM` xem metadata stream.
- `XINFO GROUPS` xem các group và tiến độ giao mới.
- `XINFO CONSUMERS` xem consumer và pending của từng consumer.
- `XPENDING` xem việc chưa ACK.

Ví dụ giới hạn độ dài stream:

```redis
XTRIM orders:events MAXLEN ~ 100000
```

Dấu `~` yêu cầu trim xấp xỉ vì tối ưu thực thi. **Lệnh không xác nhận tất cả group đã hoàn tất trước khi xóa record.** Nếu retention quá ngắn, record pending hoặc backlog chưa giao có thể mất payload. Việc thiết kế retention phải xét tốc độ vào, tốc độ xử lý, thời gian gián đoạn dài nhất và nhu cầu replay.

Ở phiên bản Redis mới có thêm các tùy chọn xóa có xét trạng thái consumer group, nhưng phải xác nhận semantics và hỗ trợ phiên bản cụ thể trước khi dùng.

## 16. Redis Streams consumer group có bảo đảm exactly-once không?

**Không tự động.** Consumer group cung cấp phân phối và metadata pending để ứng dụng xây cơ chế xử lý/retry, nhưng kết quả nghiệp vụ vẫn có thể lặp:

| Lỗi xảy ra khi | Trạng thái Redis | Rủi ro |
| --- | --- | --- |
| Worker chết trước khi xử lý và chưa ACK | Record pending | Cần recovery/claim để xử lý tiếp |
| Worker xử lý thành công nhưng chết trước ACK | Record vẫn pending | Retry có thể lặp tác dụng phụ |
| Worker ACK trước khi commit kết quả | Pending đã biến mất | Xử lý lỗi sau ACK có thể mất công việc |
| Worker nhận với `NOACK` | Không tạo pending thông thường | Không có đường khôi phục qua PEL khi xử lý lỗi |

Chỉ khi kết hợp idempotency, xác nhận đúng thời điểm, kiểm soát retry và phục hồi pending mới có thể đạt hiệu quả *at least once* cho dữ liệu còn lưu và còn truy xuất được. Ngay cả như vậy, tích hợp với SQL, HTTP hay hệ thống ngoài cần cơ chế chống lặp và xử lý lỗi riêng.

## 17. Giám sát group và consumer trong vận hành

Sử dụng:

```redis
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events order-workers
XPENDING orders:events order-workers
```

| Tín hiệu | Điều cần hiểu |
| --- | --- |
| `last-delivered-id` | Mốc giao record mới, không phải mốc hoàn tất |
| `pending` | Số record đã giao chưa ACK |
| `lag` | Ước lượng record chưa giao khi Redis có đủ dữ liệu metadata; đôi khi không xác định |
| Idle/inactive của consumer | Mức độ hoạt động, ý nghĩa cụ thể phụ thuộc phiên bản Redis |
| Delivery count | Gợi ý record bị phát lại/claim nhiều lần |
| ACK rate | Tốc độ xác nhận xử lý |
| Processing latency | Thời gian xử lý cần dùng để chọn ngưỡng claim |
| Dead-letter count | Số record không xử lý được theo retry policy |

Các lệnh cần thận trọng:

- `XGROUP DESTROY` xóa group và trạng thái pending của group.
- `XGROUP SETID ... $` có thể bỏ qua các record còn chưa được giao.
- `XGROUP DELCONSUMER` ảnh hưởng các pending do consumer sở hữu.
- `XTRIM` quá mạnh có thể xóa record cần retry.
- `XACK` hàng loạt chưa kiểm chứng có thể làm sạch pending mà không hoàn thành tác vụ.

## 18. Thực hành với hai consumer

Bài thực hành dùng stream test độc lập.

### Bước 1: tạo group

```redis
XGROUP CREATE demo:orders:events demo-workers 0-0 MKSTREAM
```

### Bước 2: thêm ba record

```redis
XADD demo:orders:events * type created orderId 101
XADD demo:orders:events * type created orderId 102
XADD demo:orders:events * type created orderId 103
```

Ghi lại ID mà Redis trả về.

### Bước 3: consumer A đọc hai record

```redis
XREADGROUP GROUP demo-workers worker-A COUNT 2 STREAMS demo:orders:events >
XPENDING demo:orders:events demo-workers
```

### Bước 4: consumer B đọc record còn lại

```redis
XREADGROUP GROUP demo-workers worker-B COUNT 2 STREAMS demo:orders:events >
```

Consumer B thường nhận bản ghi thứ ba chưa giao. Nếu B đọc tiếp bằng `>` mà không có bản ghi mới, nó không tự nhận pending thuộc A.

### Bước 5: ACK một record của A

```redis
XACK demo:orders:events demo-workers <id-thuc-te-cua-record-A>
XLEN demo:orders:events
XPENDING demo:orders:events demo-workers
```

`XPENDING` giảm nếu ACK thành công, nhưng `XLEN` không giảm chỉ do ACK.

### Bước 6: A đọc lại pending

```redis
XREADGROUP GROUP demo-workers worker-A COUNT 10 STREAMS demo:orders:events 0
```

Lệnh đọc lại pending của A, không đọc lại toàn bộ record đã lưu.

### Bước 7: B tiếp quản pending của A

Trong Redis 6.2+ trên môi trường test:

```redis
XAUTOCLAIM demo:orders:events demo-workers worker-B 1000 0-0 COUNT 10
```

Ngưỡng 1 giây chỉ minh họa. Trong production, chọn giá trị đủ cao dựa vào thời gian xử lý nghiệp vụ để tránh claim một record mà A vẫn xử lý bình thường.

### Bước 8: xem metadata

```redis
XINFO GROUPS demo:orders:events
XINFO CONSUMERS demo:orders:events demo-workers
XPENDING demo:orders:events demo-workers
XLEN demo:orders:events
```

Có thể pending về 0 trong khi ba record vẫn nằm trong stream. Đây là khác biệt giữa trạng thái xử lý và retention.

## 19. Những hiểu lầm thường gặp

**“Mỗi consumer trong group có cursor độc lập cho toàn stream.”**  
Không. Group phối hợp vị trí giao record mới; mỗi consumer chủ yếu có phần pending và metadata riêng.

**“`last-delivered-id` là ID cuối đã ACK.”**  
Không. Group có thể giao record tới cuối stream trong khi còn nhiều pending chưa xử lý.

**“`XREADGROUP ... >` sẽ tự retry bản ghi lỗi.”**  
Không. Bản ghi lỗi đã giao nằm pending; cần đọc pending hoặc claim.

**“`XREADGROUP ... 0` là cách đọc toàn stream từ đầu.”**  
Không. Trong consumer group, nó duyệt pending của consumer đang gọi.

**“Tạo group ở `$` giúp đọc backlog.”**  
Không. Nó khởi tạo group tại mốc cuối của stream ở thời điểm tạo.

**“`XACK` xóa dữ liệu khỏi stream.”**  
Không. `XACK` chỉ loại pending của group, không thực hiện retention.

**“Nhiều consumer và ACK đem lại exactly-once tự động.”**  
Không. Xử lý lặp vẫn có thể xảy ra sau lỗi kết nối và retry; cần idempotency.

**“`lag = 0` nghĩa là mọi việc đã xử lý xong.”**  
Không. Group vẫn có thể còn pending chưa ACK.

## 20. Câu hỏi tự kiểm tra

1. Vì sao hai consumer của một group phối hợp phân phối message, trong khi hai group khác nhau có thể cùng nhận một message?
2. `XGROUP CREATE stream group 0-0` khác `XGROUP CREATE stream group $` ở đâu?
3. `last-delivered-id` phản ánh điều gì và khác trạng thái ACK thế nào?
4. Vì sao một pending của A không được B nhận bằng `XREADGROUP ... >`?
5. Khi đọc với `XREADGROUP ... 0`, Redis lấy pending của consumer nào?
6. `XACK` có làm `XLEN` giảm không?
7. Tại sao `XAUTOCLAIM` cần `min-idle-time` hợp lý và idempotency?
8. Spring Data Redis dùng `ReadOffset.lastConsumed()` trong consumer group để yêu cầu loại message nào?
9. Nếu SQL đã commit rồi worker chết trước ACK, rủi ro lúc recovery là gì?
10. Khi `pending > 0` nhưng `lag = 0`, group đã hoàn tất công việc chưa?

**Ghi nhớ:** Trong Redis Streams, **group giữ vị trí giao message mới**, **consumer nhận phần việc của group**, còn **PEL theo dõi message đã giao nhưng chưa ACK**. Chọn vị trí khởi tạo group bằng `0-0` hoặc `$`, đọc mới bằng `>` (qua `ReadOffset.lastConsumed()` trong Spring Data Redis), rồi thiết kế riêng ACK, recovery và retention.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): `StreamOperations`, consumer group, offset và listener container.
- [Redis — XGROUP CREATE](https://redis.io/docs/latest/commands/xgroup-create/): tạo group và lựa chọn `0-0` hoặc `$`.
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/): đọc message mới bằng `>` và pending bằng ID.
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/): kiểm tra Pending Entries List.
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/): xác nhận xử lý trong group.
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/): tiếp quản pending theo idle time.
- [Redis — XINFO GROUPS](https://redis.io/docs/latest/commands/xinfo-groups/): `last-delivered-id`, pending và lag.
