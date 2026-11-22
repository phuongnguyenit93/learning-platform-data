# Tác động của `ReadOffset` đến mất hoặc lặp bản ghi trong Spring Data Redis Streams

Redis Streams cho phép ứng dụng lưu các bản ghi có **ID theo thứ tự** và đọc lại những bản ghi đã ghi vào stream. Trong Spring Data Redis, `ReadOffset` xác định **vị trí bắt đầu cho lần đọc tiếp theo**. Lựa chọn tưởng như nhỏ này quyết định một reader có đọc được backlog hay không, có bỏ qua bản ghi đến trong khoảng ngắt giữa hai lần poll hay không, và có đọc lại dữ liệu khi khởi động lại hay không.

Ba lựa chọn rất dễ nhầm:

- `ReadOffset.latest()`: bắt đầu từ phần cuối stream hiện tại; thích hợp với kiểu **chỉ quan tâm bản ghi mới** nhưng có thể bỏ qua dữ liệu đã có hoặc dữ liệu xuất hiện giữa các lần đọc nếu liên tục lấy lại vị trí cuối.
- `ReadOffset.from(id)`: đọc các bản ghi có ID **lớn hơn** một ID cụ thể; phù hợp với reader tự quản lý checkpoint, nhưng lưu checkpoint sai thời điểm có thể gây **mất** hoặc **lặp** xử lý.
- `ReadOffset.lastConsumed()`: dùng trong bối cảnh **consumer group** để nhận các bản ghi mới chưa được group giao thông qua `XREADGROUP` (tương ứng với ký hiệu `>` trong ngữ nghĩa Redis). Nó không tự thu hồi mọi bản ghi còn *pending* khi consumer bị lỗi.

Điểm quan trọng nhất: **`ReadOffset` quyết định vị trí đọc, không quyết định một bản ghi đã được xử lý nghiệp vụ thành công hay chưa.** Để xây dựng luồng đáng tin cậy, cần kết hợp offset với chính sách checkpoint, ACK, reclaim pending, retention và idempotency.

## 1. Redis Stream lưu bản ghi như thế nào?

Một Redis Stream chứa những entry gồm ID và tập field/value. Ví dụ dùng Redis CLI:

```redis
XADD orders:events * eventId evt-101 type ORDER_CREATED orderId order-101
XADD orders:events * eventId evt-102 type ORDER_PAID orderId order-101
XADD orders:events * eventId evt-103 type ORDER_SHIPPED orderId order-101
```

Redis có thể tạo các ID ví dụ như:

```text
1731000000000-0   ORDER_CREATED
1731000000100-0   ORDER_PAID
1731000000200-0   ORDER_SHIPPED
```

Con số chỉ để minh họa, không phải ID cố định phải có trên máy của bạn. Dạng ID thường có hai thành phần phân cách bởi dấu `-`; Redis sắp xếp stream theo ID. Không nên coi ID như dấu thời gian nghiệp vụ có thể tự suy ra hoàn toàn từ đồng hồ của mọi producer.

Luồng dữ liệu:

```text
          Redis Stream: orders:events

ID A            ID B              ID C
 |               |                 |
 v               v                 v
ORDER_CREATED -> ORDER_PAID -> ORDER_SHIPPED
                      ^
                      |
                Vị trí reader đã đọc
```

Một reader cần quyết định sẽ đọc từ **đầu stream**, **sau ID đã biết**, hay **chỉ từ những bản ghi phát sinh sau thời điểm hiện tại**. Spring Data Redis diễn đạt quyết định này bằng `ReadOffset`.

### 1.1. Redis Streams khác Redis Pub/Sub

Redis Pub/Sub phát message đến subscriber đang kết nối, không lưu lịch sử cho subscriber đến muộn. Redis Streams lưu bản ghi trong cấu trúc dữ liệu để reader có thể đọc theo ID, miễn là bản ghi còn được giữ lại.

Tuy nhiên, **lưu trữ được không đồng nghĩa tự động không mất dữ liệu**. Nếu reader cố ý đọc từ cuối, checkpoint vượt quá bản ghi chưa xử lý hoặc stream bị trim trước khi xử lý, dữ liệu vẫn có thể bị bỏ sót.

## 2. `ReadOffset` được ánh xạ tới hành vi đọc nào?

Ở Redis CLI, lệnh `XREAD` sử dụng stream ID để biểu diễn vị trí đọc:

```redis
XREAD COUNT 10 STREAMS orders:events 0-0
```

Lệnh này đọc các entry có ID lớn hơn `0-0`. Vì đa số bản ghi do Redis tạo có ID lớn hơn `0-0`, đây là cách thường dùng để đọc backlog còn tồn tại.

Muốn chỉ chờ những entry được thêm **sau khi lệnh bắt đầu đọc**, Redis cho phép ký hiệu `$`:

```redis
XREAD BLOCK 2000 STREAMS orders:events $
```

Trong consumer group, `XREADGROUP` có ký hiệu `>` để yêu cầu các entry **mới, chưa được giao cho consumer nào trong group**:

```redis
XREADGROUP GROUP order-workers worker-1 COUNT 10 STREAMS orders:events >
```

Các lựa chọn Java thường được diễn giải theo hướng:

| Spring Data Redis | Ý nghĩa chính | Tình huống sử dụng |
|---|---|---|
| `ReadOffset.latest()` | Bắt đầu tại cuối stream vào thời điểm đọc, tương tự `$` với `XREAD` | Chỉ cần message mới, chấp nhận bỏ qua lịch sử |
| `ReadOffset.from("0-0")` | Đọc sau ID `0-0` | Đọc backlog từ đầu phần dữ liệu còn lưu |
| `ReadOffset.from(lastId)` | Đọc những entry có ID lớn hơn checkpoint `lastId` | Reader tự quản lý offset |
| `ReadOffset.lastConsumed()` | Đọc theo vị trí group đã giao, thường tương ứng `>` trong `XREADGROUP` | Consumer group nhận entry mới |
| ID cụ thể trong `XREADGROUP`, ví dụ `0` | Xem lại entry pending của consumer tương ứng theo ngữ nghĩa Redis | Khôi phục pending, không phải đọc toàn bộ entry chưa giao |

**Chú ý phạm vi:** `ReadOffset.lastConsumed()` được dùng với consumer group; không nên hiểu nó là một checkpoint bền vững tự động cho mọi reader độc lập. Tương tự, cung cấp ID số trong `XREADGROUP` có ngữ nghĩa khác so với dùng ID ấy trong `XREAD`. Phải xét **cả lệnh đọc và giá trị offset**.

### 2.1. ID truyền vào là vị trí *đã đi qua*, không phải entry đầu tiên cần đọc

Ví dụ có ba entry ID A, B, C với `A < B < C`.

```text
XREAD ... A  -> thường trả B, C
XREAD ... B  -> thường trả C
XREAD ... C  -> chỉ chờ/nhận entry mới hơn C
```

Redis dùng điều kiện **ID lớn hơn ID đã cung cấp** cho `XREAD`. Nếu checkpoint đang lưu ID cuối cùng **đã xử lý thành công**, lần đọc tiếp theo dùng đúng checkpoint này.

Một lỗi phổ biến là lưu ID **cần xử lý đầu tiên** rồi truyền nó vào `ReadOffset.from(id)`, dẫn đến việc bỏ qua chính entry đó.

## 3. `ReadOffset.latest()`: chỉ đọc tương lai và nguy cơ bỏ qua bản ghi

Giả sử stream đã có:

```text
A: ORDER_CREATED
B: ORDER_PAID
C: ORDER_SHIPPED
```

Reader bắt đầu bằng:

```java
StreamOffset.create(
    "orders:events",
    ReadOffset.latest()
)
```

Khi ánh xạ thành lệnh `XREAD` từ `$`, Redis lấy **phần cuối stream ở thời điểm lệnh đọc được xử lý** làm mốc. A, B, C đã tồn tại trước thời điểm đó nên không được trả về.

```text
A ---- B ---- C        | reader bắt đầu ở cuối
                       |
                       +---- D mới đến -> có thể đọc D
```

Đây là hành vi **đúng nếu yêu cầu là quan sát sự kiện realtime kể từ khi subscribe**. Nhưng nó sai nếu nghiệp vụ bắt buộc xử lý cả A, B, C.

### 3.1. Khoảng trống giữa hai lần poll

Nguy cơ lớn hơn xuất hiện khi reader **liên tục đọc lại từ `latest()`**, đặc biệt khi mỗi lần đọc không giữ ID cuối cùng đã nhận.

```text
t0   Reader gọi XREAD BLOCK ... $ và chờ
t1   Bản ghi D đến; reader nhận D
t2   Lệnh đọc kết thúc, Java đang xử lý D
t3   Bản ghi E được XADD vào stream
t4   Java xử lý D xong
t5   Reader gọi XREAD BLOCK ... $ một lần nữa
```

Ở `t5`, `$` tham chiếu tới cuối stream **đang chứa E**, nên lần đọc ấy có thể bỏ qua E để chỉ đợi những entry đến sau `t5`.

```text
                     D đã nhận
                         |
                         v
... C ---- D ---- E ---- | XREAD từ "$" tại t5
                 ^
                 |
       E có thể không được reader này trả về
```

Đây là lý do chiến lược `latest()` không phù hợp với worker phải xử lý tất cả entry. Tài liệu Spring Data Redis cũng phân biệt việc đọc từ latest với việc đọc từ ID cụ thể: đọc từ ID đã biết tránh khoảng trống này khi entry vẫn còn trong stream.

**Điều kiện:** mô tả trên áp dụng khi một lần `XREAD` thực sự sử dụng `$`/vị trí cuối hiện tại. Một container/driver có thể giữ hoặc cập nhật offset riêng theo cách triển khai; khi thiết kế độ tin cậy phải dựa vào chiến lược `ReadOffset` và hành vi thực tế của API, không giả định container biến `latest()` thành một checkpoint bền vững.

### 3.2. Khi nào `latest()` là lựa chọn hợp lý?

- Màn hình realtime chỉ quan tâm thông tin mới kể từ lúc mở.
- Telemetry hoặc notification có thể mất một số sự kiện vì còn nguồn khác để tải trạng thái hiện tại.
- Listener không có nghĩa vụ xử lý backlog.
- Ứng dụng chủ động chấp nhận bỏ qua message trong những giai đoạn không subscribe/không polling.

Không nên dùng `latest()` cho:

- Ghi sổ nghiệp vụ bắt buộc đủ sự kiện.
- Tác vụ cần xử lý lại sau downtime.
- Đồng bộ dữ liệu qua nhiều bước mà thiếu một event gây sai trạng thái.
- Luồng thu phí, đặt hàng, trừ tồn kho không cho phép bỏ sót.

Nếu chỉ cần trạng thái mới nhất thay vì xử lý mọi sự kiện, đôi khi tốt hơn là **đọc trạng thái hiện tại từ nguồn dữ liệu** thay vì dựa vào một stream consumer được thiết kế chỉ nhận tương lai.

## 4. `ReadOffset.from(id)`: tiếp tục sau một vị trí rõ ràng

`ReadOffset.from(id)` dùng một ID cụ thể làm mốc. Ví dụ:

```java
StreamOffset<String> offset = StreamOffset.create(
    "orders:events",
    ReadOffset.from("1731000000100-0")
);
```

Với giả định ID đó là của event B và stream còn C, lần đọc theo `XREAD` có thể trả C và các entry mới hơn.

Mô hình:

```text
A ---- B ---- C ---- D ---- E
       ^
       |
    checkpoint=B
                 |
                 +--> đọc C, D, E
```

Ưu điểm là **không nhảy lại về cuối stream sau mỗi lần poll**. Nếu E xuất hiện trong lúc ứng dụng đang xử lý D, lần đọc tiếp theo từ D vẫn lấy E nếu E còn được lưu.

Tuy nhiên, `ReadOffset.from(id)` **không tự biết bản ghi nào đã được xử lý thành công**. Ứng dụng phải quyết định checkpoint là gì và lưu ở đâu.

### 4.1. Không có checkpoint bền vững: đọc lại từ đầu khi restart

Nếu ứng dụng luôn khởi động với:

```java
ReadOffset.from("0-0")
```

nó đọc từ đầu phần lịch sử còn tồn tại trong stream. Điều này hữu ích khi chạy một tác vụ quét lại dữ liệu, nhưng khi service restart, nó có thể xử lý lại hàng nghìn entry cũ.

```text
Lần chạy 1: A, B, C đã xử lý
App restart
Lần chạy 2: lại đọc A, B, C từ 0-0
```

Nếu handler chỉ `cache.evict(productId)` thì lặp có thể chấp nhận được. Nếu handler ghi thanh toán hoặc tăng bộ đếm nghiệp vụ, lặp có thể gây sai dữ liệu.

Vì thế cần checkpoint **bền vững** nếu muốn reader độc lập tiếp tục qua restart mà không phải quét lại tất cả.

### 4.2. Checkpoint chỉ nên đại diện cho tiến độ đã xử lý

Giả sử reader xử lý tuần tự A, B, C.

```text
Đọc A -> xử lý A thành công -> checkpoint A
Đọc B -> xử lý B thành công -> checkpoint B
Đọc C -> xử lý C thành công -> checkpoint C
```

Sau restart, `ReadOffset.from(C)` sẽ đọc những entry mới hơn C.

Nếu checkpoint được lưu **ngay khi nhận message** trước khi xử lý, một crash có thể làm mất công việc:

```text
Nhận B
Lưu checkpoint = B
Ứng dụng crash trước khi xử lý B
Restart từ B -> Redis chỉ trả entry > B
B không được xử lý
```

Ngược lại, nếu xử lý xong rồi mới checkpoint:

```text
Nhận B
Xử lý B thành công
Ứng dụng crash trước khi lưu checkpoint = B
Restart từ A -> B được đọc lại
```

Trường hợp thứ hai có **lặp xử lý**, nhưng có thể kiểm soát bằng idempotency. Đây là đánh đổi thường gặp để đạt mục tiêu *at-least-once processing* với checkpoint riêng, miễn là dữ liệu còn trong stream và cơ chế lưu checkpoint thực sự bền vững.

## 5. Hai cửa sổ lỗi: checkpoint trước hay sau xử lý?

Đây là phần quan trọng nhất khi thiết kế reader tự quản lý offset.

| Thứ tự thao tác | Nếu crash ở khoảng giữa | Rủi ro |
|---|---|---|
| **Checkpoint → xử lý** | Đã lưu vị trí mới nhưng side effect chưa xong | **Mất xử lý** |
| **Xử lý → checkpoint** | Side effect xong nhưng vị trí chưa lưu | **Lặp xử lý** |
| Xử lý và checkpoint trong **một transaction nguyên tử ở cùng nguồn dữ liệu** | Có thể tránh trạng thái nửa chừng trong phạm vi transaction đó | Cần giao dịch thực sự và cùng ranh giới nguồn dữ liệu |
| Xử lý ở DB, checkpoint ở Redis độc lập | Không có commit phân tán tự động | Vẫn có cửa sổ lỗi, cần idempotency/recovery |

Minh họa với side effect ở PostgreSQL và checkpoint ở Redis:

```text
Transaction DB commit:
    UPDATE payments ...       -> thành công

Redis checkpoint:
    SET stream:checkpoint ... -> chưa được gọi

JVM crash
```

Sau restart, entry có thể xuất hiện lại vì checkpoint vẫn cũ. Nếu thay đổi DB không idempotent, có nguy cơ thực hiện nghiệp vụ hai lần.

**Không chọn thời điểm checkpoint chỉ để loại bỏ duplicate trên dashboard.** Nếu bản ghi rất quan trọng, ưu tiên không bỏ qua công việc rồi thiết kế idempotency và trạng thái xử lý có thể khôi phục.

## 6. Ví dụ đọc không dùng consumer group với `ReadOffset.from(...)`

Spring Data Redis cung cấp `StreamOperations` và `StreamReadOptions` cho thao tác `XREAD`.

Ví dụ minh họa một reader tuần tự; `CheckpointStore` là abstraction do ứng dụng cung cấp để **lưu bền vững** ID cuối cùng xử lý thành công:

```java
package com.example.orders;

import java.util.List;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderStreamReader {

    private static final String STREAM = "orders:events";

    private final StringRedisTemplate redis;
    private final CheckpointStore checkpoints;
    private final OrderEventHandler handler;

    public OrderStreamReader(
            StringRedisTemplate redis,
            CheckpointStore checkpoints,
            OrderEventHandler handler
    ) {
        this.redis = redis;
        this.checkpoints = checkpoints;
        this.handler = handler;
    }

    public void pollOnce() {
        String lastProcessedId = checkpoints.load(STREAM)
                .orElse("0-0");

        List<MapRecord<String, Object, Object>> records =
                redis.opsForStream().read(
                    StreamReadOptions.empty().count(20),
                    StreamOffset.create(
                        STREAM,
                        ReadOffset.from(lastProcessedId)
                    )
                );

        if (records == null || records.isEmpty()) {
            return;
        }

        for (MapRecord<String, Object, Object> record : records) {
            // Nếu xử lý thất bại, dừng mà không vượt checkpoint.
            handler.handle(record);

            checkpoints.save(
                STREAM,
                record.getId().getValue()
            );
        }
    }
}
```

Các interface ứng dụng:

```java
package com.example.orders;

import java.util.Optional;
import org.springframework.data.redis.connection.stream.MapRecord;

public interface CheckpointStore {
    Optional<String> load(String streamKey);
    void save(String streamKey, String lastProcessedId);
}

public interface OrderEventHandler {
    void handle(MapRecord<String, Object, Object> record);
}
```

Hợp đồng quan trọng:

1. `load` trả về checkpoint **đã lưu bền vững**; không chỉ là một biến tĩnh trong JVM.
2. `save` chỉ được gọi **sau khi handler xác nhận xử lý thành công**.
3. Reader xử lý tuần tự theo ID; nếu handler ném exception tại B, không tự tiến checkpoint đến C.
4. Nếu `save` thất bại sau khi handler đã thực hiện side effect, lần poll sau có thể đọc lại entry vừa xử lý.
5. Handler cần idempotency nếu side effect không được phép lặp.
6. Với nhiều instance cùng đọc độc lập từ một checkpoint chung, phải có cơ chế điều phối/ownership; nếu không, chúng có thể cùng xử lý một entry và ghi checkpoint đè nhau.

Đây là mẫu **một reader tuần tự**. Nó không tự thay thế consumer group khi muốn chia công việc cho nhiều worker.

### 6.1. Không cập nhật checkpoint đến bản ghi cuối của batch trước khi xử lý

Một lỗi nguy hiểm:

```java
List<MapRecord<String, Object, Object>> batch = readBatch();

String lastId = batch.get(batch.size() - 1).getId().getValue();

// SAI nếu batch còn entry chưa xử lý:
checkpointStore.save(STREAM, lastId);

for (var record : batch) {
    handler.handle(record);
}
```

Nếu app crash ở giữa vòng lặp, những entry chưa xử lý trước `lastId` bị bỏ qua ở lần restart.

Cách đơn giản nhất là checkpoint sau từng entry thành công. Nếu vì hiệu năng cần checkpoint theo batch, hãy xác nhận **toàn bộ batch đã xử lý thành công** và hiểu rằng crash trước khi lưu batch checkpoint có thể khiến một số entry bị xử lý lại.

### 6.2. Xử lý song song khiến checkpoint phức tạp hơn

Nếu reader giao A, B, C cho ba thread:

```text
A: xử lý 500 ms
B: xử lý  50 ms -> xong trước
C: xử lý  80 ms -> xong trước A
```

Không được lưu checkpoint C chỉ vì C đã hoàn thành: A còn dang dở, lần restart từ C sẽ bỏ qua A.

Khi xử lý song song, checkpoint an toàn phải biểu diễn **ranh giới các entry liên tiếp đã hoàn thành** hoặc lưu trạng thái hoàn thành theo từng ID. Nếu không cần độ phức tạp này, có thể dùng reader tuần tự hoặc thiết kế phân vùng theo key với progress riêng.

## 7. Consumer group khác gì reader tự lưu checkpoint?

Redis Streams consumer group được tạo bởi `XGROUP`, và dùng `XREADGROUP` để phân phối entry cho những consumer cùng group.

Khởi tạo group đọc cả backlog còn có:

```redis
XGROUP CREATE orders:events order-workers 0-0 MKSTREAM
```

Các thành phần:

- `orders:events`: tên stream.
- `order-workers`: tên consumer group.
- `0-0`: group bắt đầu từ trước những entry thông thường, cho phép đọc backlog.
- `MKSTREAM`: tạo stream nếu chưa tồn tại.

Sau đó:

```redis
XREADGROUP GROUP order-workers worker-a COUNT 10 STREAMS orders:events >
```

Ký hiệu `>` yêu cầu những entry **chưa từng được giao** trong group. Redis lưu thông tin tiến độ delivery của group và tạo trạng thái *pending* cho những entry đã giao nhưng chưa được ACK.

**Consumer group tách hai trạng thái quan trọng:**

1. **Đã giao cho consumer** (*delivered*).
2. **Đã xác nhận xử lý** (*acknowledged*) bằng `XACK`.

Sự khác biệt này không có trong một `XREAD` độc lập chỉ mang offset ID.

### 7.1. `ReadOffset.lastConsumed()` trong Spring Data Redis

Khi đăng ký group consumer bằng API của Spring Data Redis, mẫu thông dụng:

```java
Consumer.from("order-workers", "worker-a"),

StreamOffset.create(
    "orders:events",
    ReadOffset.lastConsumed()
)
```

Hướng đọc này tương đương yêu cầu **entry mới** của group, thường được Redis thực hiện bằng `XREADGROUP ... >`.

Cần hiểu rằng tên `lastConsumed()` không có nghĩa:

- "Entry cuối đã hoàn thành side effect ở application".
- "Entry cuối đã được `XACK`".
- "Tự lấy lại mọi entry pending từ lần trước".
- "Tự tái phát các entry đã bị trim".
- "Tự bảo đảm exactly-once".

Với group, muốn biết entry nào đã được giao nhưng chưa ACK phải xem **Pending Entries List (PEL)** và có quy trình xử lý lại thích hợp.

## 8. `XGROUP CREATE ... $` có thể bỏ qua backlog dù dùng `lastConsumed()`

Một tình huống rất dễ hiểu nhầm:

Stream đã có A, B, C:

```text
orders:events:
    A -> B -> C
```

Group được tạo ở vị trí cuối:

```redis
XGROUP CREATE orders:events order-workers $ MKSTREAM
```

Khi đó group đặt vị trí bắt đầu **sau dữ liệu hiện có**. Consumer:

```redis
XREADGROUP GROUP order-workers worker-a STREAMS orders:events >
```

chỉ nhận các entry mới được thêm sau mốc của group, không tự nhận lại A, B, C.

```text
A ---- B ---- C | group tạo ở "$" ---- D ---- E
                ^
                |
       Group khởi đầu sau C
                                   |
                                   +-- nhận D, E
```

**Đây là quyết định tại lúc tạo group**, không chỉ quyết định của reader Java.

So sánh:

| Cách tạo group | Hệ quả thường gặp |
|---|---|
| `XGROUP CREATE stream group 0-0` | Có thể nhận backlog còn lưu từ đầu bằng `>` |
| `XGROUP CREATE stream group $` | Bỏ qua backlog hiện có, nhận entry mới |
| Group đã tồn tại | Tham số tạo ban đầu không được áp dụng lại khi service restart; group giữ trạng thái trong Redis |
| `XGROUP SETID` thay đổi vị trí group | Có thể thay đổi tập entry mới được giao; phải dùng rất thận trọng và hiểu PEL |

Nếu yêu cầu là xử lý mọi entry từ trước khi service triển khai, tạo group từ `0-0` (hoặc mốc nghiệp vụ rõ ràng) là lựa chọn thông thường. Nếu chỉ muốn theo dõi các event tương lai, `$` có thể là chủ đích.

Không được nghĩ rằng `ReadOffset.lastConsumed()` sẽ khắc phục việc group vốn được tạo từ `$`.

## 9. Pending Entries List: bản ghi được giao nhưng chưa ACK

Giả sử consumer A đọc một entry:

```redis
XREADGROUP GROUP order-workers worker-a COUNT 1 STREAMS orders:events >
```

Redis đánh dấu entry đó là **pending** cho group/consumer tương ứng, cho đến khi được xác nhận:

```redis
XACK orders:events order-workers <entry-id>
```

Nếu consumer crash **sau khi nhận nhưng trước `XACK`**, entry không tự biến thành một entry chưa từng được giao. Nó nằm trong PEL.

```text
              Redis Stream             Consumer Group
                 entry B
                    |
                    v
                 Delivered -------------> PEL: B (worker-a)
                    |
                    v
               Worker crash
                    |
                    X (không có XACK)
                    |
                    v
              B vẫn pending
```

Consumer B khác gọi:

```redis
XREADGROUP GROUP order-workers worker-b STREAMS orders:events >
```

sẽ chủ yếu nhận **entry mới chưa được giao**, không tự lấy entry B đang pending của A.

### 9.1. Kiểm tra pending

Redis CLI:

```redis
XPENDING orders:events order-workers
```

Lệnh này cho thông tin tổng quan số pending, khoảng ID và consumer liên quan.

Kiểm tra chi tiết hơn:

```redis
XPENDING orders:events order-workers - + 10
```

Kết quả có thể gồm:

- ID entry pending.
- Tên consumer đang sở hữu.
- Thời gian idle kể từ lần giao gần nhất.
- Số lần delivery theo cơ chế Redis.

Các thông số này giúp phát hiện consumer bị dừng hoặc message xử lý quá lâu. Nhưng “pending lâu” không luôn đồng nghĩa consumer đã chết: có thể một công việc đang chạy hợp lệ. Cần điều chỉnh timeout theo nghiệp vụ.

### 9.2. Đọc lại pending của chính consumer

Với `XREADGROUP`, dùng một ID cụ thể khác `>` (ví dụ `0`) có thể truy cập lịch sử pending **của chính consumer được chỉ định**, không phải danh sách mọi entry của cả group chưa bao giờ đọc.

Ví dụ:

```redis
XREADGROUP GROUP order-workers worker-a COUNT 10 STREAMS orders:events 0
```

Cách này giúp consumer A xem lại những entry pending gắn với chính tên consumer đó.

Điểm dễ nhầm: `0` trong `XREADGROUP` với consumer group **không có nghĩa y hệt** `0-0` trong `XREAD` thông thường. Với `XREADGROUP`, nó truy cập pending history của consumer phù hợp.

### 9.3. Chuyển pending từ consumer cũ sang consumer mới

Nếu worker A mất kết nối và không quay lại, worker B có thể dùng `XCLAIM` hoặc `XAUTOCLAIM` để nhận ownership của những pending entry đáp ứng ngưỡng idle.

Ví dụ minh họa:

```redis
XAUTOCLAIM orders:events order-workers worker-b 60000 0-0 COUNT 20
```

Ý nghĩa:

- `order-workers`: group.
- `worker-b`: consumer muốn claim.
- `60000`: yêu cầu idle ít nhất 60.000 ms.
- `0-0`: điểm bắt đầu quét pending.
- `COUNT 20`: giới hạn số item quét/nhận theo semantics của command.

`XAUTOCLAIM` trả cursor để tiếp tục quét; một lần gọi không nhất thiết xử lý hết toàn bộ PEL. Cần đọc và xử lý kết quả, chạy tiếp nếu còn pending, cùng với giới hạn batch và giám sát.

Sau khi xử lý nghiệp vụ thành công, worker mới `XACK`.

**Cần idempotency:** consumer A có thể vẫn đang chạy hoặc đã làm side effect thành công nhưng chết trước ACK; worker B claim và xử lý lại. Không thể suy luận rằng “được claim” nghĩa là side effect chưa từng xảy ra.

## 10. Crash trước và sau `XACK` quyết định mất hay lặp

Đối với consumer group, ranh giới tương tự checkpoint nhưng liên quan đến ACK và PEL.

| Trình tự | Nếu crash ở khoảng giữa | Hệ quả |
|---|---|---|
| **ACK → xử lý** | Đã xóa trạng thái pending trước khi side effect hoàn tất | Có thể **mất xử lý** |
| **Xử lý → ACK** | Side effect xong nhưng pending chưa được ACK | Có thể **lặp xử lý** khi reclaim |
| Xử lý → ACK, không có cơ chế reclaim | Pending bị kẹt vô thời hạn | Không lặp nhưng cũng không hoàn thành recovery |
| Xử lý idempotent → ACK + reclaim hợp lý | Có thể xử lý lại nhưng không lặp side effect nghiệp vụ | Hướng *at-least-once* thực tế |
| Xử lý ở DB và ACK ở Redis | Hai thao tác trên hai resource khác nhau | Không có exactly-once phân tán tự động |

Ví dụ:

```text
Worker A:
    XREADGROUP -> nhận event B
    UPDATE database -> commit
    JVM crash trước XACK

Worker B:
    XAUTOCLAIM -> nhận lại event B
    UPDATE database lần nữa?
```

Nếu `UPDATE` là “tăng số dư thêm 100”, xử lý hai lần sẽ sai. Nếu transaction DB kiểm tra `eventId` chưa xử lý rồi ghi side effect và dấu đã xử lý **trong cùng transaction**, worker B có thể nhận diện event B là duplicate và ACK an toàn.

Đây là ví dụ cho nguyên tắc: **hệ thống có thể giao/đọc lặp, nhưng side effect nghiệp vụ cần idempotent**.

## 11. Đừng ACK trước khi xử lý xong

Với Spring Data Redis, một listener group thường nhận message rồi handler thực hiện công việc và ACK sau khi thành công:

```text
receive message
    |
    v
validate and deserialize
    |
    v
businessHandler.handle(message)
    |
    +-- lỗi ----------> không ACK -> pending/retry/reclaim theo chính sách
    |
    +-- thành công ---> XACK
```

Một số API/container có chế độ **auto-ack**. Cần hiểu đúng thời điểm ACK của chế độ đó: nếu hệ thống yêu cầu khả năng khôi phục sau handler failure, đừng chọn auto-ack mà không xác minh nó bảo đảm điều gì.

Nếu ACK ngay khi nhận message hoặc trước khi commit nghiệp vụ, một exception sau đó có thể khiến message không còn pending để retry. Với tác vụ bắt buộc hoàn tất, thường nên **manual ACK sau khi handler thành công**.

Không được cho rằng `XACK` là lời gọi rollback hay xóa bản ghi trong stream. `XACK` chỉ đánh dấu entry không còn pending trong group; entry vẫn có thể nằm trong stream cho đến khi bị `XDEL`, trim hoặc chính sách lưu trữ khác loại bỏ.

## 12. Ví dụ group listener với `ReadOffset.lastConsumed()`

Spring Data Redis có `StreamMessageListenerContainer` để poll stream và dispatch message tới `StreamListener`.

Ví dụ minh họa một consumer group xử lý message rồi ACK thủ công:

```java
package com.example.orders;

import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.data.redis.stream.StreamMessageListenerContainer
        .StreamMessageListenerContainerOptions;

@Configuration(proxyBeanMethods = false)
public class OrderStreamListenerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(
                OrderStreamListenerConfiguration.class
            );

    @Bean
    public StreamMessageListenerContainer<
        String, MapRecord<String, String, String>
    > orderStreamContainer(
        RedisConnectionFactory connectionFactory,
        StringRedisTemplate redis,
        OrderRecordHandler handler
    ) {
        StreamMessageListenerContainerOptions<
            String, MapRecord<String, String, String>
        > options = StreamMessageListenerContainerOptions
                .<String, MapRecord<String, String, String>>builder()
                .pollTimeout(Duration.ofSeconds(2))
                .build();

        var container = StreamMessageListenerContainer.create(
            connectionFactory, options
        );

        container.receive(
            Consumer.from("order-workers", "worker-a"),
            StreamOffset.create(
                "orders:events",
                ReadOffset.lastConsumed()
            ),
            message -> {
                try {
                    handler.handle(message);

                    redis.opsForStream().acknowledge(
                        "orders:events",
                        "order-workers",
                        message.getId()
                    );
                } catch (Exception ex) {
                    log.error(
                        "Stream processing failed; record remains pending: {}",
                        message.getId(),
                        ex
                    );
                    // Không ACK: xử lý lại qua pending/reclaim policy.
                }
            }
        );

        return container;
    }
}
```

Interface ứng dụng:

```java
package com.example.orders;

import org.springframework.data.redis.connection.stream.MapRecord;

public interface OrderRecordHandler {
    void handle(MapRecord<String, String, String> message);
}
```

Một số điểm cần lưu ý:

- Đây là ví dụ cấu hình minh họa; cách khai báo generic/serializer của `StreamMessageListenerContainerOptions` cần được điều chỉnh cho version Spring Data Redis và định dạng record của dự án.
- Consumer group `order-workers` phải **đã được tạo** trước khi listener bắt đầu đọc. Lệnh `XGROUP CREATE` có thể được triển khai trong bước khởi tạo có kiểm soát; phải xử lý trường hợp group đã tồn tại thay vì coi là lỗi hệ thống.
- Tên consumer `worker-a` cần được quản lý theo topology triển khai; dùng cùng tên cho nhiều instance có thể làm recovery/ownership khó theo dõi.
- Nếu handler ném exception và code bắt lỗi, message **vẫn pending**; lỗi không tự tạo retry. Cần worker/quy trình reclaim.
- Nếu `acknowledge(...)` lỗi sau khi handler thành công, entry có thể được xử lý lại. Handler vẫn phải idempotent.
- Container của Spring có lifecycle; nên để Spring quản lý start/stop, thay vì tạo container ngoài context và quên start.
- Nếu dùng consumer tự động ACK hoặc một API khác, cần xem chính xác semantics của callback và ACK; ví dụ này cố ý ACK sau handler.

### 12.1. Vì sao không dùng `ReadOffset.latest()` trong đoạn group?

Consumer group dùng trạng thái delivery của group và `>` để nhận entry mới. `ReadOffset.lastConsumed()` diễn đạt mục tiêu đó rõ hơn. Dùng `latest()` như thể đang `XREAD` độc lập có thể dẫn tới ngữ nghĩa không mong muốn, không hợp lệ hoặc không phù hợp khi truyền cho `XREADGROUP`, tùy cách API ánh xạ.

Khi dùng consumer group, hãy phân biệt rõ:

```text
ReadOffset.lastConsumed() -> nhận entry mới trong group
pending recovery           -> dùng lịch sử pending / claim
group creation ID          -> quyết định backlog ban đầu
```

Đây là **ba cơ chế khác nhau**, không thể được thay thế bởi một offset duy nhất.

## 13. Tại sao `lastConsumed()` không đồng nghĩa “đã xử lý thành công”?

Tên `lastConsumed` có thể gây cảm giác Redis biết vị trí mà ứng dụng đã xử lý hoàn tất. Trong consumer group, Redis chủ yếu biết:

- Group đã giao entry nào.
- Consumer nào đang sở hữu các pending entry.
- Entry nào đã được `XACK`.
- Last-delivered ID dùng để chọn entry mới.

Redis **không thể tự biết** một giao dịch PostgreSQL, một lần gọi HTTP, một email hoặc một thay đổi ở dịch vụ bên ngoài đã hoàn thành đúng nghiệp vụ hay chưa.

Ví dụ:

```text
XREADGROUP -> giao B cho worker-a
worker-a bắt đầu xử lý B
DB đã commit
worker-a crash trước XACK
```

Group biết B vẫn pending. Nó không biết DB đã commit. Khi khôi phục, B có thể được chạy lại. Đây là lý do phải đặt idempotency ở nơi side effect được lưu.

Mặt khác, nếu ứng dụng ACK B trước khi DB commit mà transaction DB rollback, Redis đã đánh dấu B không pending dù nghiệp vụ thất bại.

**ACK là xác nhận của consumer đối với stream group**, không phải lời chứng tự động về thành công của mọi hệ thống liên quan.

## 14. Group có nhiều worker: thứ tự và lặp xử lý

Giả sử các entry A, B, C được group giao cho hai worker:

```text
Stream: A -> B -> C

worker-a nhận A
worker-b nhận B
worker-a nhận C
```

Có thể xảy ra:

```text
worker-a xử lý A trong 500 ms
worker-b xử lý B trong  50 ms
worker-a xử lý C trong  70 ms

B hoàn thành trước A
```

Redis Stream có thứ tự ID, nhưng **thứ tự hoàn thành side effect qua nhiều consumer không được bảo đảm chỉ bằng ReadOffset**.

Nếu nghiệp vụ yêu cầu cập nhật cho cùng `orderId` theo thứ tự:

- Gắn version/sequence vào event và kiểm tra trước khi áp dụng.
- Phân vùng xử lý để event cùng aggregate có ownership rõ.
- Dùng cập nhật có điều kiện/optimistic locking tại database.
- Hoặc chọn mô hình một consumer tuần tự khi lưu lượng và SLA cho phép.

Không nên dựa vào `ReadOffset.from(...)` hay `lastConsumed()` để thay thế một cơ chế ordering cho nhiều worker.

Với consumer group, tính chia việc còn phụ thuộc group membership, trạng thái pending và việc claim; restart/timeout có thể khiến entry được xử lý lại bởi consumer khác.

## 15. Retention, `XTRIM` và `XDEL`: offset đúng vẫn có thể không đọc được dữ liệu

`ReadOffset.from(lastId)` chỉ cho Redis biết mốc muốn đọc. Nó **không bảo đảm entry sau mốc vẫn được lưu**.

Ví dụ stream có A, B, C, D, E:

```text
A ---- B ---- C ---- D ---- E
       ^
       |
    checkpoint=B
```

Nếu stream bị trim để chỉ giữ D và E:

```text
D ---- E
```

Reader từ B chỉ có thể đọc những entry còn tồn tại, ví dụ D và E. C đã bị loại khỏi stream, nên không thể khôi phục chỉ bằng việc đặt lại `ReadOffset`.

Các cơ chế liên quan:

- `XTRIM`: cắt bớt entry theo giới hạn ID hoặc số lượng.
- `XADD ... MAXLEN` / `MINID`: kết hợp thêm entry và giới hạn retention.
- `XDEL`: xóa entry cụ thể.
- Chính sách persistence, sự cố Redis hoặc thao tác quản trị cũng ảnh hưởng khả năng khôi phục.
- Một entry pending trong PEL có thể không còn payload nếu entry đã bị xóa/trim; PEL và dữ liệu stream không đồng nghĩa luôn tồn tại song song mãi mãi.

Vì vậy cần định nghĩa **thời gian lưu trữ tối thiểu** lớn hơn downtime/retry lag dự kiến, và theo dõi consumer lag/pending.

### 15.1. “At-least-once” phụ thuộc điều kiện nào?

Một pipeline dùng checkpoint sau xử lý hoặc consumer group + ACK/reclaim có thể hướng tới *at-least-once processing*, nhưng chỉ khi:

1. Entry được ghi và còn tồn tại đủ lâu trong stream.
2. Reader không tự nhảy checkpoint vượt entry chưa hoàn thành.
3. Pending entry được phát hiện và xử lý lại.
4. Không có lỗi không thể phục hồi làm mất dữ liệu nguồn.
5. Handler có cơ chế chịu duplicate.
6. Các yêu cầu về durability/failover của Redis được đáp ứng theo cấu hình thực tế.

Không thể hứa at-least-once tuyệt đối chỉ bằng một dòng `ReadOffset.lastConsumed()`.

## 16. Thêm `BLOCK`, `COUNT` không thay đổi ý nghĩa offset

Khi đọc stream, Spring Data Redis có thể dùng `StreamReadOptions`:

```java
StreamReadOptions.empty()
    .count(20)
    .block(Duration.ofSeconds(2))
```

- `COUNT 20`: gợi ý/giới hạn số entry đọc trong một đợt theo lệnh Redis.
- `BLOCK 2000`: chờ entry xuất hiện tối đa khoảng 2 giây nếu hiện chưa có entry phù hợp.
- `ReadOffset`: mốc chọn entry nào là đủ điều kiện trả về.

Thay `COUNT` hoặc `BLOCK` không sửa được việc dùng `$` sai mục đích:

```text
XREAD BLOCK 2000 STREAMS orders:events $
```

vẫn bắt đầu tại cuối stream ở lần đọc đó. Nếu một record xuất hiện ngay trước lệnh và reader lại dùng `$`, nó có thể bị bỏ qua dù tăng thời gian `BLOCK` lên rất dài.

Tương tự, dùng `COUNT 100` không biến handler tự động ACK 100 entry sau khi nghiệp vụ thành công. Offset, batching, ACK và concurrency là các quyết định độc lập.

### 16.1. Khi poll timeout, làm thế nào để không bỏ qua entry?

Với reader không dùng group, giữ `lastProcessedId`:

```text
Poll từ ID=B
Không có dữ liệu -> timeout
Poll lại từ ID=B
Có C -> xử lý C -> checkpoint C
Poll từ ID=C
```

Đừng dùng lại `latest()` ở mỗi lượt nếu mục tiêu là bắt đủ các entry.

Với consumer group, mỗi lần đọc entry mới dùng `lastConsumed()`/`>` theo ngữ nghĩa group. Đồng thời chạy một quy trình khác để phát hiện **pending** cần khôi phục.

## 17. Kịch bản minh họa trong Redis CLI

Phần này giúp quan sát trực tiếp sự khác biệt giữa đọc stream thông thường và consumer group. Dùng một Redis thử nghiệm, không chạy trên stream production.

### 17.1. Tạo stream mẫu

```redis
XADD lab:orders * type CREATED orderId 101
XADD lab:orders * type PAID orderId 101
XADD lab:orders * type SHIPPED orderId 101
XRANGE lab:orders - +
```

Ghi lại ID Redis trả về cho từng lệnh `XADD`. Trong các ví dụ tiếp theo, thay `<id-a>`, `<id-b>` bằng ID thực tế.

### 17.2. `XREAD` từ đầu

```redis
XREAD COUNT 10 STREAMS lab:orders 0-0
```

Các entry đã có sẽ được trả về theo ID tăng dần.

### 17.3. `XREAD` sau ID đã xử lý

```redis
XREAD COUNT 10 STREAMS lab:orders <id-b>
```

Nếu `<id-b>` là ID của entry `PAID`, kết quả sẽ là các entry có ID lớn hơn, chẳng hạn `SHIPPED`.

### 17.4. `XREAD` từ cuối

Ở terminal A:

```redis
XREAD BLOCK 10000 STREAMS lab:orders $
```

Ở terminal B, thêm event trong thời gian terminal A đang chờ:

```redis
XADD lab:orders * type CANCELLED orderId 101
```

Terminal A có thể nhận `CANCELLED`. Nhưng nếu `CANCELLED` đã được thêm **trước khi** terminal A gọi `XREAD ... $`, nó sẽ bị coi là lịch sử và không được trả ở lần đọc đó.

### 17.5. Tạo group từ đầu và đọc entry mới của group

Dùng một stream/group mới để tránh trạng thái cũ trong thử nghiệm:

```redis
XGROUP CREATE lab:orders lab-workers 0-0
XREADGROUP GROUP lab-workers worker-1 COUNT 2 STREAMS lab:orders >
XPENDING lab:orders lab-workers
```

Hai entry đầu sẽ trở thành pending nếu chưa ACK.

ACK một entry:

```redis
XACK lab:orders lab-workers <id-a>
```

Kiểm tra lại:

```redis
XPENDING lab:orders lab-workers
```

Entry đã ACK không còn trong PEL, nhưng thường vẫn xuất hiện trong `XRANGE` vì `XACK` không tự xóa nó khỏi stream.

### 17.6. Đọc pending của chính consumer và claim

```redis
XREADGROUP GROUP lab-workers worker-1 COUNT 10 STREAMS lab:orders 0
```

Lệnh này dùng offset dạng số để đọc lịch sử pending của consumer `worker-1`.

Khi cần một consumer khác claim entry đủ lâu chưa được ACK:

```redis
XAUTOCLAIM lab:orders lab-workers worker-2 60000 0-0 COUNT 10
```

Chỉ các entry đáp ứng điều kiện idle mới có thể được claim theo lệnh đó. Thao tác claim nên gắn với logic xử lý lại và ACK sau thành công; không phải “xóa hết pending”.

### 17.7. So sánh group tạo từ `$`

Tạo stream khác:

```redis
XADD lab:new-orders * event first
XADD lab:new-orders * event second
XGROUP CREATE lab:new-orders newest-only $ 
XREADGROUP GROUP newest-only worker-1 STREAMS lab:new-orders >
```

Lần đọc đầu có thể không trả hai entry cũ. Thêm:

```redis
XADD lab:new-orders * event third
XREADGROUP GROUP newest-only worker-1 STREAMS lab:new-orders >
```

Group nhận entry `third` mới, minh họa ảnh hưởng của offset **khi tạo group**.

## 18. Bảng quyết định khi chọn `ReadOffset`

| Nhu cầu | Lựa chọn khởi đầu | Cần bổ sung |
|---|---|---|
| Chỉ nhận thông báo mới từ thời điểm bắt đầu nghe | `ReadOffset.latest()` với `XREAD` | Chấp nhận mất backlog/khoảng trống giữa poll |
| Đọc toàn bộ entry còn lưu cho một job quét một lần | `ReadOffset.from("0-0")` | Xác định việc replay có an toàn không |
| Reader riêng, tiếp tục sau restart | `ReadOffset.from(checkpoint)` | Checkpoint bền vững sau xử lý, idempotency |
| Nhiều worker chia việc theo group | `ReadOffset.lastConsumed()` | Group tạo ở mốc đúng, manual ACK, pending recovery |
| Consumer bị crash, cần lấy entry chưa ACK | Pending history hoặc `XAUTOCLAIM`/`XCLAIM` | Xử lý lại idempotent, ACK, ngưỡng idle |
| Cần xử lý lại mọi event từ một mốc lịch sử | Reader riêng hoặc group mới tạo ở ID phù hợp | Stream retention còn đủ; không tùy tiện đổi group production |
| Không được bỏ bất kỳ event quan trọng nào | Chỉ offset là chưa đủ | Durable source, retry/reclaim, retention, monitoring, idempotency |
| Cần exactly-once side effect trên DB | Không có ReadOffset nào tự đáp ứng | DB transaction/idempotency key hoặc phối hợp giao dịch phù hợp |

Một quy tắc thiết kế dễ nhớ:

> **Offset quyết định bản ghi nào có thể được giao; checkpoint/ACK quyết định việc đánh dấu tiến độ; idempotency quyết định việc xử lý lặp có an toàn hay không.**

## 19. Những hiểu lầm thường gặp

**“`latest()` bảo đảm luôn nhận mọi bản ghi mới, kể cả trong khoảng ngắt giữa các poll.”** Sai khi mỗi lượt đọc lại lấy `$` mới. Entry đến trước lần đọc tiếp theo có thể bị bỏ qua.

**“`from(id)` sẽ đọc lại chính entry có ID đó.”** Với `XREAD`, các entry trả về có ID lớn hơn mốc đã cung cấp; cần đặt checkpoint là ID cuối **đã xử lý**, không phải ID đầu **cần xử lý**.

**“Đọc từ `0-0` luôn an toàn cho service chạy nhiều năm.”** Không tự động. Restart có thể đọc lại hàng loạt event cũ; nếu stream đã trim thì những event bị loại cũng không thể đọc lại.

**“`lastConsumed()` nghĩa là last ACKed.”** Không nên đánh đồng. Group theo dõi delivery và ACK riêng; các entry đã giao nhưng chưa ACK nằm ở PEL.

**“Consumer mới dùng `lastConsumed()` sẽ tự xử lý pending của consumer chết.”** Sai. `>` thường nhận entry mới; pending của consumer khác cần reclaim.

**“Tạo group với `$` rồi dùng `lastConsumed()` sẽ đọc backlog.”** Sai. Group đã khởi đầu ở cuối stream hiện có.

**“ACK ngay khi nhận message giúp tránh xử lý trùng.”** Có thể làm mất xử lý nếu side effect chưa hoàn thành. Tránh duplicate bằng idempotency, không bằng bỏ qua khả năng phục hồi.

**“ACK sau xử lý bảo đảm exactly-once.”** Không. Crash giữa side effect và ACK khiến record được xử lý lại khi reclaim.

**“Một consumer group luôn giữ thứ tự hoàn thành side effect.”** Không. Nhiều worker, nhiều thread và retry có thể làm các event hoàn thành không theo thứ tự ID.

**“Redis giữ pending nên payload không thể mất.”** Không. Trimming hoặc xóa entry có thể loại payload; pending metadata không thay thế stream retention.

**“`COUNT` lớn hoặc `BLOCK` lâu sẽ sửa được lỗi offset.”** Không. Hai tùy chọn này điều khiển batch/wait, không thay đổi ý nghĩa `$`, ID cụ thể hay `>`.

**“Chỉ cần lưu checkpoint trong biến static.”** Không bền vững qua restart và không phối hợp an toàn giữa nhiều instance.

**“Xử lý song song xong record C thì checkpoint C là an toàn.”** Không, nếu A/B chưa hoàn thành. Checkpoint đơn phải biểu diễn ranh giới liên tiếp đã xử lý.

## 20. Thiết kế vận hành để phát hiện mất hoặc lặp bản ghi

Một ứng dụng có thể chạy nhiều tuần mà không báo exception, nhưng vẫn bỏ sót event hoặc xử lý lặp khi restart. Do đó cần theo dõi nhiều lớp.

### 20.1. Với reader không dùng group

- Checkpoint ID cuối cùng đã xử lý và thời điểm cập nhật.
- ID đầu/cuối còn tồn tại trong stream (`XINFO STREAM` hoặc `XRANGE` phạm vi thích hợp).
- Độ chênh giữa thời gian event và thời gian xử lý.
- Số entry xử lý thành công/lỗi theo loại.
- Số lần gặp duplicate theo `eventId`.
- Số lần resume sau restart.
- Các khoảng trống đáng ngờ do checkpoint nhảy hoặc stream retention.

Nếu checkpoint quá cũ nhưng stream đã trim quá xa, cần ghi nhận **không thể replay trọn vẹn**, không âm thầm nhảy đến entry còn mới rồi báo hệ thống đã xử lý đủ.

### 20.2. Với consumer group

Redis CLI hữu ích:

```redis
XINFO STREAM orders:events
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events order-workers
XPENDING orders:events order-workers
```

Các chỉ số cần quan sát:

| Chỉ số | Ý nghĩa |
|---|---|
| Stream length | Số entry còn được giữ lại; không phải tổng event mọi thời điểm |
| Group last-delivered ID | Vị trí entry mới đã được giao theo group |
| Group lag (nếu Redis cung cấp và giá trị có ý nghĩa) | Số entry phía sau mốc giao, không phải số pending đã xử lý thất bại |
| Pending count | Entry đã giao nhưng chưa ACK |
| Pending idle | Nhận diện entry có nguy cơ bị worker bỏ quên |
| Delivery count | Dấu hiệu entry được giao lại, cần hiểu theo cơ chế Redis |
| Handler success/error | Phân biệt nhận message và xử lý thành công |
| Claim/retry count | Phát hiện consumer lỗi và tình trạng duplicate |
| Oldest retained ID | Đánh giá nguy cơ trim vượt tiến độ xử lý |

**Group lag = 0 không có nghĩa mọi event đã xử lý thành công.** Nhóm có thể đã giao hết entry mới, nhưng còn rất nhiều pending chưa ACK.

Tương tự, pending count nhỏ không bảo đảm không mất dữ liệu nếu ACK quá sớm hoặc group được tạo từ `$` khi stream đã có backlog.

### 20.3. Không suy luận mất record chỉ từ ID không liên tục

Stream ID có thể không liên tục về mặt số học. Hai ID liên tiếp không bắt buộc có giá trị tăng đúng `1`, vì ID được gắn theo thời gian và sequence.

Muốn phát hiện mất nghiệp vụ, sử dụng event ID/sequence do **nguồn nghiệp vụ** quản lý hoặc đối chiếu với outbox/event log đáng tin cậy. Một khoảng nhảy lớn giữa Redis Stream IDs không tự chứng minh có event bị thiếu.

## 21. Kiến trúc đề xuất cho luồng cần xử lý đáng tin cậy

Giả sử hệ thống đơn hàng yêu cầu mọi event được xử lý, có thể retry sau crash và không cập nhật trùng side effect:

```text
Producer
   |
   v
XADD orders:events
   |
   v
Consumer group "order-workers"
   |
   +-- XREADGROUP ... > / ReadOffset.lastConsumed()
   |         |
   |         v
   |    handler có idempotency theo eventId
   |         |
   |         v
   |    commit side effect
   |         |
   |         v
   |        XACK
   |
   +-- Recovery job
          |
          +-- XPENDING / XAUTOCLAIM
          |
          +-- xử lý lại idempotent
          |
          +-- XACK sau thành công
```

Ngoài các thành phần trên, cần:

1. Tạo group ở mốc đúng (`0-0` nếu cần backlog; `$` nếu chủ động chỉ lấy dữ liệu về sau).
2. Giữ retention đủ lâu để vượt downtime/retry lag.
3. Dùng consumer identity có chủ đích và giám sát ownership pending.
4. Không dùng auto-ack trước khi side effect hoàn thành khi yêu cầu khôi phục.
5. Định nghĩa poison-message policy: retry có giới hạn, lưu lỗi và dead-letter theo thiết kế.
6. Đặt idempotency ở cùng transaction với side effect quan trọng khi có thể.
7. Khi có nhiều worker, quản lý thứ tự/phiên bản của event theo aggregate.
8. Chỉ báo “đã xử lý” khi đã đạt tiêu chí nghiệp vụ, không chỉ vì `XREADGROUP` đã trả message.

Trong hệ thống quan trọng, còn cần đánh giá persistence/replication của Redis và khoảng hở ghi giữa DB nguồn và Redis Stream. Nếu DB cập nhật thành công nhưng XADD không xảy ra, `ReadOffset` của consumer không thể tạo lại event chưa từng được ghi; có thể cân nhắc transactional outbox tại producer.

## 22. Checklist chẩn đoán khi thấy thiếu hoặc lặp event

**Nếu thiếu event:**

1. Reader có dùng `ReadOffset.latest()`/`$` trong mỗi poll không?
2. Group có được tạo từ `$` khi stream đã có backlog không?
3. Checkpoint có bị lưu trước khi handler thành công không?
4. Có ACK trước khi commit nghiệp vụ không?
5. Stream có bị trim/`XDEL` trước khi đọc hoặc reclaim không?
6. Có pending chưa ACK bị bỏ quên vì consumer mới chỉ đọc `>` không?
7. Có lỗi deserialize/handler nhưng hệ thống vẫn báo thành công không?
8. Có khoảng hở giữa nguồn phát event và `XADD` không?

**Nếu lặp event:**

1. Reader có khởi động lại từ `0-0` mỗi lần không?
2. Checkpoint có được lưu bền vững sau xử lý không?
3. Có crash giữa xử lý và checkpoint/ACK không?
4. Consumer có bị `XAUTOCLAIM` khi worker gốc còn chạy chậm không?
5. Producer có retry `XADD` cùng event nghiệp vụ với ID stream mới không?
6. Có nhiều reader độc lập cùng đọc toàn bộ stream không?
7. Handler đã có idempotency theo `eventId` chưa?
8. Có xử lý song song làm checkpoint nhảy quá một số entry chưa xong không?

Không có một cấu hình offset duy nhất sửa được tất cả các lỗi trên. Cần xác định **điểm dữ liệu được coi là giao, điểm công việc được coi là hoàn tất, và cơ chế phục hồi khi process bị dừng giữa hai điểm**.

## 23. Kết luận

`ReadOffset` là một yếu tố quyết định độ tin cậy của Redis Streams trong Spring Data Redis:

- **`ReadOffset.latest()`** hữu ích cho reader chỉ quan tâm bản ghi mới, nhưng có thể bỏ qua backlog và bản ghi đến giữa các lượt poll nếu mỗi lần lại đọc từ cuối.
- **`ReadOffset.from(id)`** giúp tiếp tục đọc từ một ID rõ ràng; với reader riêng, nên dùng checkpoint bền vững và chỉ cập nhật sau khi xử lý thành công, chấp nhận khả năng đọc lại để tránh mất xử lý.
- **`ReadOffset.lastConsumed()`** dùng cho consumer group nhận entry mới. Nó phải đi cùng **group creation ID**, `XACK`, giám sát PEL và cơ chế claim/retry pending; bản thân nó không tự khôi phục entry đã giao nhưng chưa ACK.

Trong mọi mô hình, **offset không thay thế idempotency, retention hay transaction nghiệp vụ**. Để giảm mất dữ liệu, không nhảy tiến độ trước khi xử lý thành công và bảo đảm có thể replay. Để xử lý lặp an toàn, dùng event ID cùng cơ chế cập nhật idempotent. Để giữ thứ tự, cần kiểm soát concurrency và version thay vì chỉ dựa vào thứ tự ID của stream.

Khi hiểu rõ ranh giới giữa **đã đọc**, **đã giao**, **đã xử lý**, **đã ACK** và **còn lưu trong stream**, ứng dụng có thể lựa chọn `ReadOffset` đúng với yêu cầu và thiết kế luồng tiêu thụ có thể phục hồi sau lỗi mà không tạo những cam kết delivery sai lệch.
