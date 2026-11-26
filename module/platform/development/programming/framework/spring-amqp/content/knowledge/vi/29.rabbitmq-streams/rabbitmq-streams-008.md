# Offset bắt đầu, theo dõi offset và đọc lại dữ liệu

**RabbitMQ Streams** lưu message theo mô hình **log nối tiếp có thể đọc lại**. Thay vì coi một message được ACK là đã biến mất khỏi queue như luồng xử lý thông thường của classic queue, stream lưu các bản ghi cho tới khi **chính sách retention** loại bỏ những phần dữ liệu cũ. Nhiều consumer có thể đọc cùng stream ở các vị trí khác nhau mà không giành quyền sở hữu từng message.

Khi xây ứng dụng **SPRING_AMQP**, hiểu **offset bắt đầu**, **theo dõi offset** (*offset tracking*) và **replay** là điều kiện để khôi phục consumer sau sự cố, xây lại projection, chạy consumer mới hoặc kiểm tra sự kiện lịch sử. Các khái niệm này bổ sung cho những kiến thức về `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, xác nhận giao nhận, retry, dead-letter và quan sát hệ thống; cách dùng chính xác phụ thuộc việc ứng dụng đang sử dụng **AMQP 0-9-1** hay **giao thức RabbitMQ Stream gốc**.

## 1. Vì sao RabbitMQ Stream cần offset?

Một stream có thể hình dung như chuỗi bản ghi được append theo thời gian:

```text
        RabbitMQ stream: orders.stream
        +------+------+------+------+------+------+------+
        | 101  | 102  | 103  | 104  | 105  | 106  | 107  |
        +------+------+------+------+------+------+------+
           ^             ^                    ^
           |             |                    |
    Consumer A       Consumer B           Consumer C
    xử lý đến 101    xử lý đến 103        đọc từ 106

Consumer A: muốn tiếp tục từ vị trí đã hoàn thành
Consumer B: muốn phát lại một vùng dữ liệu để sửa projection
Consumer C: chỉ quan tâm các sự kiện mới gần cuối stream
```

Mỗi bản ghi có một **offset** được RabbitMQ gắn khi append vào stream. Offset là một **vị trí** trong **stream cụ thể**, cho biết dữ liệu ở đâu trong thứ tự log:

- Offset **không phải** `messageId` nghiệp vụ, `correlationId` hay offset của consumer khác.
- Một message được đọc nhiều lần vẫn là **cùng bản ghi và offset** trong stream.
- Hai stream khác nhau có offset độc lập: offset 100 của stream A không có quan hệ thứ tự với offset 100 của stream B.
- Offset tăng theo thứ tự vị trí append, nhưng không nên coi offset là bộ đếm business event liên tiếp hay khóa chính toàn hệ thống. Việc lọc, retention và chi tiết lưu trữ có thể làm dữ liệu quan sát không đầy đủ ở mọi số.
- Consumer có thể nhận message rồi dừng trước khi ghi nhận tiến độ; **offset đã đọc** chưa chắc là **offset đã xử lý thành công**.

**Phân biệt với classic queue:** Với classic queue, `basic.ack` thông báo delivery đã xử lý và message thông thường được loại khỏi queue. Với RabbitMQ Stream, **việc đọc/ghi tiến độ không xóa message khỏi log**; retention quyết định dữ liệu còn lại. Offset tracking là checkpoint cho consumer, khác với việc ACK từng message của AMQP queue thông thường.

## 2. Ba khái niệm cần tách biệt

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Start offset / offset specification** | Khi *attach* consumer, muốn bắt đầu đọc từ đâu? | Đọc từ đầu dữ liệu còn giữ, từ cuối, từ offset 205 hay theo timestamp |
| **Offset tracking / checkpoint** | Consumer đã xử lý thành công đến vị trí nào? | Dịch vụ billing lưu `lastProcessedOffset=214` |
| **Replay / reprocessing** | Có chủ đích đọc lại vùng dữ liệu đã đọc trước đó như thế nào? | Đọc lại từ offset 180 để dựng lại bảng tổng hợp |

Ba thao tác không tự thay thế nhau. Chỉ gọi `OffsetSpecification.first()` không tự kích hoạt checkpoint. Chỉ lưu checkpoint ở broker không ngăn consumer xử lý trùng khi crash. Và đặt offset bắt đầu bằng `last()` không phải là cách bảo đảm chỉ nhận “đúng một message cuối”.

Một quy trình hoạt động hợp lý:

```text
[Consumer khởi tạo]
      |
      +-- Tra checkpoint đã lưu (nếu có)
      |
      +-- Chọn offset bắt đầu
      |
      v
[Attach vào stream / đọc message]
      |
      v
[Đọc offset + eventId]
      |
      v
[Xử lý nghiệp vụ + commit DB]
      |
      v
[Lưu checkpoint / xác nhận tiến độ]
      |
      v
[Tiếp tục đọc]
```

Để thiết kế chính xác, **xác định trước nguồn sự thật của checkpoint**: RabbitMQ broker, database riêng của ứng dụng hay một kết hợp có quy tắc rõ ràng.

## 3. Các lựa chọn offset bắt đầu trong RabbitMQ Streams

RabbitMQ Stream protocol hỗ trợ các điểm bắt đầu thường dùng; Java Stream client biểu diễn bằng `OffsetSpecification`.

| Lựa chọn | Ý nghĩa thực tế | Dùng khi nào? |
|---|---|---|
| `OffsetSpecification.first()` | Đọc từ bản ghi **sớm nhất còn được retention giữ lại** | Khởi tạo projection, điều tra toàn bộ dữ liệu còn lại |
| `OffsetSpecification.last()` | Bắt đầu ở **chunk cuối** của stream; có thể nhận **nhiều message**, không chỉ đúng một message cuối | Muốn đọc vùng dữ liệu gần cuối và tiếp tục nhận mới |
| `OffsetSpecification.next()` | Bắt đầu **sau phần dữ liệu hiện có tại thời điểm attach**; chỉ theo dõi message mới về sau | Consumer chỉ cần sự kiện phát sinh từ lúc bắt đầu theo dõi |
| `OffsetSpecification.offset(n)` | Yêu cầu đọc từ vị trí offset cụ thể `n` trở đi nếu dữ liệu còn tồn tại | Resume theo checkpoint; replay một khoảng đã biết |
| `OffsetSpecification.timestamp(t)` | Bắt đầu từ vị trí tương ứng mốc timestamp trong stream, theo cách broker ánh xạ timestamp sang chunk/offset | Điều tra dữ liệu xung quanh một thời điểm |

### 3.1. first không phải “message đầu tiên từng được publish”

Nếu stream từng có offset 1..500, nhưng retention đã xóa dữ liệu cũ và chỉ còn khoảng 300..500, `first()` đưa consumer tới vùng dữ liệu **còn giữ lại**, không khôi phục được 1..299. Không có start offset nào đọc lại dữ liệu đã bị retention xóa.

### 3.2. last không tương đương next

Một lỗi hiểu phổ biến là `last()` chỉ phát đúng message có offset lớn nhất. Stream lưu dữ liệu thành **chunks**; `last()` định vị theo chunk cuối, có thể chuyển về **nhiều message**. Trong khi đó `next()` chủ yếu để nhận **các message mới sau khi attach**, không dùng để dựng lại lịch sử.

Ví dụ giả định chunk cuối chứa offsets 490..500:

```text
Retained: [ 1 ... 489 ][ 490 491 492 ... 500 ] | tiếp tục append 501 ...
                     ^                  ^        ^
                     |                  |        |
                   last()         các message      next()
                                 trong chunk cuối
```

Trước khi chọn `next()` cho nghiệp vụ quan trọng, phải xác nhận rằng **không còn dữ liệu cũ cần xử lý** hoặc đã có cơ chế checkpoint/reconciliation khác. Nếu một consumer mới chỉ dùng `next()`, nó có thể bỏ qua backlog đã tồn tại.

### 3.3. Offset cụ thể và timestamp

`OffsetSpecification.offset(200L)` yêu cầu bắt đầu từ vùng vị trí 200. Nếu retention đã xóa vị trí 200, không thể mặc định rằng broker sẽ tái tạo được các message cũ; cần xác minh vị trí retained earliest và có kế hoạch snapshot/đối soát.

`OffsetSpecification.timestamp(...)` dùng timestamp **liên quan tới bản ghi do broker quản lý trong stream**, không phải tùy ý lấy field `occurredAt` trong JSON nghiệp vụ rồi suy ra kết quả chính xác tuyệt đối. Mốc thời gian được broker ánh xạ ở mức lưu trữ; có thể bắt đầu từ một chunk có một số bản ghi nằm trước mốc yêu cầu. Khi cần replay theo ranh giới thời gian nghiêm ngặt, ứng dụng nên **lọc lại theo thời gian nghiệp vụ** sau khi nhận và hiểu khác biệt giữa broker timestamp với event timestamp.

## 4. Giao thức Stream gốc và Spring AMQP khác nhau thế nào?

RabbitMQ có thể cho phép làm việc với kiểu queue `stream` qua hai đường truy cập:

1. **Native RabbitMQ Stream protocol** (mặc định cổng **5552**): dùng RabbitMQ Java Stream client hoặc tích hợp stream tương ứng trong Spring AMQP. Client có API offset, tên consumer, offset tracking và replay chuyên dụng.
2. **AMQP 0-9-1** (thường cổng **5672**): các client như `RabbitTemplate` và listener queue truyền thống dùng phương thức AMQP; RabbitMQ cũng hỗ trợ các khả năng tiêu thụ stream qua AMQP với quy tắc/consumer arguments riêng.

Hai con đường không dùng cùng API và không phải mọi tính năng được diễn giải y hệt. Với bài học về `OffsetSpecification` và broker-side tracking, ví dụ chính sử dụng **native Stream Java client**. Khi tích hợp Spring, sử dụng module **`spring-rabbit-stream`**, các thành phần như `StreamListenerContainer` và `RabbitStreamTemplate` tùy phiên bản Spring AMQP.

Không nên lấy code `@RabbitListener` dùng `SimpleRabbitListenerContainerFactory` của **classic queue** rồi mặc định có thể truyền `OffsetSpecification.first()` vào container đó. Đồng thời, `RabbitTemplate.convertAndSend(...)` dùng AMQP 0-9-1 không phải phương thức publish qua native Stream Java client.

### 4.1. Phần hạ tầng tối thiểu

Để chạy thử Native Stream protocol:

- RabbitMQ phải hỗ trợ Streams và bật plugin `rabbitmq_stream`; nếu dùng Management UI, plugin management tương ứng cần cấu hình.
- Broker mở Stream listener (thường **5552**) và client có quyền truy cập stream trong đúng virtual host.
- Stream `orders.stream` phải tồn tại; tạo bằng stream client/API hoặc công cụ quản trị phù hợp.
- Java ứng dụng có dependency `com.rabbitmq:stream-client` với phiên bản tương thích RabbitMQ server. Với Spring AMQP, chọn phiên bản `spring-rabbit-stream` tương thích với Spring Boot/Spring AMQP đang dùng.
- Dùng tài khoản/vhost/TLS và network policy tương ứng; **không nhầm cổng 5552 với 5672**.

Ví dụ minh họa tối thiểu tạo môi trường native client:

```java
import com.rabbitmq.stream.Environment;

Environment environment = Environment.builder()
        .host("localhost")
        .port(5552)
        .build();

// Giả sử orders.stream đã được tạo và tài khoản có quyền phù hợp.
// Khi ứng dụng kết thúc, cần đóng consumer trước rồi đóng environment.
```

Ví dụ không chứa mật khẩu; cấu hình credential/TLS tùy môi trường. Không tạo stream mới mỗi lần khởi động nếu đã có chính sách provision topology riêng.

## 5. Code chọn offset khi tạo consumer

Native Java client có `ConsumerBuilder`, `OffsetSpecification` và callback xử lý message; context của callback cung cấp offset của bản ghi được giao.

```java
import com.rabbitmq.stream.Consumer;
import com.rabbitmq.stream.Environment;
import com.rabbitmq.stream.OffsetSpecification;
import java.nio.charset.StandardCharsets;

public class ReadFromBeginning {
    public static Consumer start(Environment environment) {
        return environment.consumerBuilder()
                .stream("orders.stream")
                .offset(OffsetSpecification.first())
                .messageHandler((context, message) -> {
                    long offset = context.offset();
                    String payload = new String(
                            message.getBodyAsBinary(),
                            StandardCharsets.UTF_8);

                    System.out.printf(
                            "offset=%d payload=%s%n", offset, payload);
                })
                .build();
    }
}
```

Đây là consumer **đọc và in message**, chưa ghi tiến độ đáng tin cậy. Nó hữu ích để khám phá và so sánh `first()` với các start specification khác; nếu restart bằng `first()`, dữ liệu vẫn còn trong retention sẽ được gửi lại.

### 5.1. Đọc từ cuối và chỉ theo dõi message mới

```java
// Bắt đầu trong chunk cuối, có thể đọc nhiều message hiện có.
OffsetSpecification nearEnd = OffsetSpecification.last();

// Chỉ theo dõi message mới kể từ lúc consumer attach.
OffsetSpecification newOnly = OffsetSpecification.next();

// Đọc từ một vị trí cụ thể, phù hợp checkpoint/replay.
OffsetSpecification fromPosition = OffsetSpecification.offset(250L);

// Mốc millisecond từ epoch; broker ánh xạ vào vùng stream.
long epochMillis = java.time.Instant
        .parse("2026-11-01T00:00:00Z")
        .toEpochMilli();
OffsetSpecification fromTime =
        OffsetSpecification.timestamp(epochMillis);
```

Các lệnh trên là ví dụ **lựa chọn**: một consumer builder chỉ nhận một offset specification ở lần attach. Không cộng thêm 1 vào timestamp; đơn vị và semantics của timestamp khác offset số nguyên.

**Lưu ý phiên bản:** API và tên phương thức có thể tiến hóa theo version RabbitMQ Java Stream client. Kiểm tra Java client đang dùng khi chuyển ví dụ thành code production.

## 6. Offset tracking: lưu tiến độ ở broker

Với native stream client, consumer **có tên** có thể dùng cơ chế broker lưu offset đã xử lý. Tên tiêu thụ là định danh logic của ứng dụng đọc stream, ví dụ `billing-projection-v1`.

### 6.1. Vì sao cần tên consumer?

Nếu mỗi lần restart bạn tạo một tên mới như `billing-2026-11-26-1230`, broker sẽ coi đó là consumer khác và không thể tự liên hệ checkpoint với tên cũ. Cách đặt tên cần ổn định theo **ứng dụng và luồng xử lý**, không ngẫu nhiên theo process ID.

Ví dụ:

| Đường xử lý | Tên consumer gợi ý | Stream |
|---|---|---|
| Billing projection | `billing-projection-v1` | `orders.stream` |
| Search indexing | `search-indexer-v2` | `orders.stream` |
| Replay sandbox | `billing-replay-test-001` | `orders.stream` |

Một stream có thể được hai consumer logic đọc độc lập, checkpoint của `billing-projection-v1` không phải checkpoint của `search-indexer-v2`. Khi dùng **super stream** có nhiều partitions, offset theo từng partition/stream thành phần; cùng một số offset ở partition khác không có ý nghĩa chung.

### 6.2. Manual offset tracking

Ví dụ dùng `manualTrackingStrategy()` và `context.storeOffset()`. Chỉ ghi nhận tiến độ **sau khi công việc nghiệp vụ đã hoàn tất thành công**:

```java
import com.rabbitmq.stream.Consumer;
import com.rabbitmq.stream.Environment;
import com.rabbitmq.stream.OffsetSpecification;

public class TrackedConsumer {
    private final OrderProjectionService projection;

    public TrackedConsumer(OrderProjectionService projection) {
        this.projection = projection;
    }

    public Consumer start(Environment environment) {
        return environment.consumerBuilder()
                .stream("orders.stream")
                .name("billing-projection-v1")
                .offset(OffsetSpecification.first())
                .manualTrackingStrategy()
                .messageHandler((context, message) -> {
                    long offset = context.offset();
                    // Service này là thành phần ứng dụng:
                    // phải commit DB / effect bền vững rồi mới return.
                    projection.apply(message.getBodyAsBinary(), offset);

                    // Ghi checkpoint tại broker sau khi apply thành công.
                    context.storeOffset();
                })
                .build();
    }
}
```

`OrderProjectionService` là service giả định. Bài học tập trung vào vị trí lời gọi `storeOffset()` so với commit nghiệp vụ; đây là **khoảng tách biệt giữa broker và database**, không phải một transaction duy nhất.

Khi khởi động lại consumer có tên, phải hiểu **cách Java client/phiên bản cụ thể sử dụng offset đã lưu so với cấu hình `offset(...)`**. Có client tự xử lý khôi phục offset đã tracking trong điều kiện phù hợp; với ứng dụng tự kiểm soát checkpoint, hãy truy xuất checkpoint, chọn start position rõ ràng và kiểm chứng bằng test restart. Không giả định rằng thêm `name(...)` sẽ đảm bảo không bao giờ có duplicate.

### 6.3. Automatic offset tracking

Stream client cũng hỗ trợ **automatic tracking** theo chiến lược gom nhóm/tần suất, thay vì mỗi callback đều gọi `storeOffset()`. Điều này giúp giảm số lần ghi offset lên broker, nhưng lưu tiến độ theo khoảng thời gian hoặc số message có thể dẫn đến **replay một số message cuối** khi consumer crash.

Cần phân biệt:

- **Message đã nhận:** handler được gọi.
- **Message xử lý thành công:** dữ liệu nghiệp vụ đã commit.
- **Offset lưu ở broker:** lần checkpoint được broker ghi nhận.
- **Offset dùng khi restart:** có thể phụ thuộc checkpoint hiện có, bản dữ liệu được retention giữ lại và chính sách khởi tạo.

Nếu callback chỉ **đẩy việc xử lý vào executor rồi trả về ngay**, automatic tracking có thể lưu offset dù task chưa hoàn tất. Hãy thiết kế callback, backpressure và cơ chế checkpoint theo **thứ tự hoàn tất thực sự**. Không cập nhật checkpoint tới offset mới nhất nếu vẫn còn message offset nhỏ hơn chưa xử lý thành công.

### 6.4. Checkpoint lệch do crash

```text
Message offset 300 nhận được
          |
          v
       Ghi DB
          |
     DB COMMIT OK
          |
     [CRASH HERE]
          |
     chưa storeOffset(300)
          |
       restart
          |
   có thể đọc lại offset 300
```

Đây là **at-least-once processing**. Nếu nghiệp vụ tăng tiền, tạo hóa đơn hoặc gửi HTTP mỗi lần nhận, việc đọc lại có thể tạo tác dụng phụ trùng. Cách xử lý là **idempotency** dựa trên `eventId` hoặc một khóa nghiệp vụ được commit cùng tác dụng phụ.

Trường hợp ngược lại còn nguy hiểm hơn: nếu lưu checkpoint **trước** khi commit DB rồi process chết, sau restart có nguy cơ **bỏ qua event chưa xử lý**. Vì vậy không checkpoint trước commit chỉ để tránh đọc lại.

## 7. Lưu checkpoint trong database của ứng dụng

Broker-side offset tracking thuận tiện, nhưng có tình huống cần đảm bảo **checkpoint và projection database cùng commit**. Khi đó hãy dùng **application-owned checkpoint table** trong cùng DB transaction với thay đổi nghiệp vụ.

### 7.1. Cấu trúc bảng PostgreSQL

```sql
CREATE TABLE billing_projection (
    order_id       uuid PRIMARY KEY,
    amount_cents   bigint NOT NULL,
    state          varchar(30) NOT NULL
);

CREATE TABLE processed_stream_events (
    consumer_name  varchar(100) NOT NULL,
    event_id       uuid NOT NULL,
    processed_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE stream_checkpoints (
    consumer_name       varchar(100) NOT NULL,
    stream_name         varchar(150) NOT NULL,
    last_applied_offset bigint NOT NULL,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, stream_name)
);
```

Bảng checkpoint khóa theo **consumerName + streamName**. Với super stream, cần checkpoint riêng theo **partition stream** hoặc định danh phân vùng; không thể dùng một số offset toàn cục cho nhiều partitions.

`processed_stream_events` chống sự kiện nghiệp vụ bị publish trùng dưới **offset mới**. Chỉ dựa vào `stream offset` có thể không phát hiện duplicate do producer gửi lại cùng event vào vị trí khác.

### 7.2. Code cập nhật projection, dedup và checkpoint nguyên tử

Ví dụ nhận event JSON có các trường `eventId`, `orderId`, `amountCents` và `state`. `OrderSnapshot` có dạng:

```java
public record OrderSnapshot(
        UUID eventId,
        UUID orderId,
        long amountCents,
        String state) {
}
```

Service dùng Spring JDBC và một transaction database. Ví dụ giả định mỗi stream/partition chỉ có **một worker xử lý tuần tự** cho consumer logic này; nếu xử lý song song, cần một cơ chế đánh dấu các offset hoàn tất liên tiếp thay vì lấy giá trị lớn nhất.

```java
@Service
public class BillingProjectionService {
    private static final String CONSUMER = "billing-projection-v1";
    private static final String STREAM = "orders.stream";

    private final JdbcTemplate jdbc;

    public BillingProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderSnapshot event, long offset) {
        // Một worker tuần tự/stream: chỉ apply offset mới hơn checkpoint.
        List<Long> rows = jdbc.query("""
                SELECT last_applied_offset
                FROM stream_checkpoints
                WHERE consumer_name = ? AND stream_name = ?
                FOR UPDATE
                """,
                (rs, n) -> rs.getLong(1),
                CONSUMER, STREAM);

        if (!rows.isEmpty() && offset <= rows.get(0)) {
            return; // Replay một vị trí đã commit.
        }

        int firstProcessing = jdbc.update("""
                INSERT INTO processed_stream_events (consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """,
                CONSUMER, event.eventId());

        if (firstProcessing == 1) {
            jdbc.update("""
                    INSERT INTO billing_projection (
                        order_id, amount_cents, state
                    ) VALUES (?, ?, ?)
                    ON CONFLICT (order_id)
                    DO UPDATE SET
                        amount_cents = EXCLUDED.amount_cents,
                        state = EXCLUDED.state
                    """,
                    event.orderId(), event.amountCents(), event.state());
        }

        jdbc.update("""
                INSERT INTO stream_checkpoints (
                    consumer_name, stream_name, last_applied_offset
                ) VALUES (?, ?, ?)
                ON CONFLICT (consumer_name, stream_name)
                DO UPDATE SET
                    last_applied_offset = EXCLUDED.last_applied_offset,
                    updated_at = now()
                """,
                CONSUMER, STREAM, offset);
    }
}
```

Các import: `java.util.UUID`, `java.util.List`, `org.springframework.jdbc.core.JdbcTemplate`, `org.springframework.stereotype.Service` và `org.springframework.transaction.annotation.Transactional`.

**Giới hạn quan trọng của ví dụ:**

- Code minh họa **chỉ đúng khi offsets được xử lý tuần tự cho mỗi consumer/stream**. Nếu hai worker cùng gọi `apply` song song, hàng checkpoint chưa tồn tại lúc ban đầu và phép upsert có thể cho kết quả không mong muốn; production cần khóa/ownership và cập nhật có kiểm tra tiến độ.
- Nếu đồng thời có offsets 301 hoàn tất trước 300, không được lưu checkpoint=301 rồi coi 300 đã xử lý. Cần xử lý tuần tự, hoặc duy trì ledger các offset hoàn tất và chỉ tăng **highest contiguous completed offset**.
- Dữ liệu `billing_projection` ví dụ là snapshot cập nhật trực tiếp; event delta/state-machine phải có version/order check để tránh áp dụng trạng thái mới rồi bị snapshot cũ ghi đè.
- Nếu `processed_stream_events` bị xóa theo retention, hãy xác định phạm vi còn đảm bảo dedup. Nếu same business event có thể xuất hiện lại sau thời gian dài, cần chiến lược retention của ledger phù hợp.

**Lợi ích:** Nếu DB commit, cả projection, processed marker và checkpoint đều commit. Nếu DB rollback, cả ba cùng rollback. Broker checkpoint có thể vẫn được dùng để tối ưu, nhưng **DB checkpoint mới là nguồn sự thật** khi thiết kế chọn mô hình này.

### 7.3. Chọn offset resume từ database

Khi service khởi động:

```java
Long lastApplied = checkpointRepository.findLastApplied(
        "billing-projection-v1", "orders.stream");

OffsetSpecification start = lastApplied == null
        ? OffsetSpecification.first()
        : OffsetSpecification.offset(lastApplied + 1);
```

`checkpointRepository` là abstraction ứng dụng cần viết để đọc bảng `stream_checkpoints`. Cần kiểm tra overflow/giá trị không hợp lệ và retention boundary. Nếu Java client/native consumer có hành vi tự resume theo broker stored offset, phải cấu hình sao cho **DB checkpoint được ưu tiên**, tránh việc một checkpoint broker mới hơn lấn át DB checkpoint cũ.

### 7.4. Trường hợp offset có thể nhảy

Không nên kiểm tra `offset == last + 1` một cách máy móc ở mọi hệ thống: offset là vị trí stream và việc broker tổ chức message/filter/retention có thể làm những số nhìn thấy không liên tiếp như counter ứng dụng. Điều **cần** bảo đảm là consumer xử lý **theo thứ tự stream được giao** và không đánh dấu vượt quá message chưa hoàn tất. Để phát hiện mất sự kiện nghiệp vụ, dùng thêm `eventId`, `aggregateId`, `aggregateVersion`, sự kiện đối soát và trạng thái retention.

## 8. Replay dữ liệu: chủ đích, điểm bắt đầu và kết quả mong muốn

Replay là **đọc lại message lịch sử vẫn còn trên stream**, không nhất thiết gửi lại chúng từ producer. Một dịch vụ có thể tạo consumer mới với start position cụ thể rồi đọc lại chính log đó.

### 8.1. Các tình huống replay

| Mục đích | Cách chọn điểm bắt đầu | Chú ý |
|---|---|---|
| Tạo projection mới từ dữ liệu đã lưu | `first()` hoặc snapshot checkpoint | Dữ liệu cũ có thể đã bị retention xóa |
| Sửa projection khi logic trước đó bị lỗi | Offset cũ hơn checkpoint hoặc reset ứng dụng | Không làm thay đổi production checkpoint nếu chạy thử |
| Điều tra sự kiện khoảng thời gian | `timestamp(t)` kết hợp filter chính xác | Broker timestamp có thể khác event timestamp |
| Reprocess một đơn hàng từ event store | Offset đầu vùng quan tâm + lọc `aggregateId` | Cần tránh gây tác dụng phụ phụ trùng |
| Consumer mới chỉ nhận dữ liệu mới | `next()` | Không hồi phục backlog |
| Kiểm tra vài bản ghi cuối | `last()` | Có thể đọc cả chunk cuối, không chính xác một record |

### 8.2. Quy trình replay an toàn

Ví dụ service billing đã checkpoint đến offset 900 nhưng muốn sửa lỗi xử lý một nhóm đơn từ offset 700:

1. **Xác định mục tiêu:** dựng lại một bảng projection hay chạy lại tác dụng phụ? Nếu chỉ sửa projection, không gửi email/thanh toán lần nữa.
2. **Xác minh retention:** vị trí offset 700 còn được broker giữ lại không? Nếu không, phải dùng snapshot/backup hoặc nguồn sự thật khác.
3. **Tách consumer/checkpoint replay:** chọn tên `billing-rebuild-2026-11` và database/schema/tables rebuild riêng. Không ghi đè checkpoint `billing-projection-v1` đang chạy sản xuất.
4. **Bắt đầu từ `OffsetSpecification.offset(700L)`**, đọc tới một mốc cuối được chốt (ví dụ offset 900) hoặc tới điểm “bắt kịp” được kiểm soát.
5. **Xử lý theo logic idempotent:** mỗi event có `eventId`; dựng lại projection dựa trên state machine/version đúng.
6. **So sánh kết quả:** kiểm tra tổng số bản ghi, checksum, aggregate totals và chênh lệch với dữ liệu nguồn.
7. **Chuyển đổi phiên bản projection:** chỉ khi đã kiểm tra mới quyết định chuyển consumer/nguồn đọc sang projection đã rebuild, xử lý event phát sinh trong lúc replay.
8. **Ghi lại audit:** offset đầu/cuối, số event đã apply, số duplicate, poison record, mất dữ liệu do retention và thời điểm hoàn thành.

Chỉ đổi start offset của **consumer production** từ 900 xuống 700 mà không kiểm soát side effect có thể gửi lại email, thanh toán, thông báo hoặc áp dụng delta hai lần.

### 8.3. Ví dụ consumer replay từ offset cụ thể

```java
Consumer replay = environment.consumerBuilder()
        .stream("orders.stream")
        .offset(OffsetSpecification.offset(700L))
        .messageHandler((context, message) -> {
            long offset = context.offset();

            // RebuildService ghi projection sandbox; không gửi tác dụng phụ.
            rebuildService.accept(offset, message.getBodyAsBinary());
        })
        .build();
```

`rebuildService` là service giả định. Bản code này không tự dừng ở offset 900 và không tự lưu checkpoint: hai cơ chế đó cần được bổ sung theo phạm vi replay. Nếu muốn đóng consumer sau một mốc, nên điều khiển lifecycle an toàn ở ngoài callback, tránh giả định gọi close ngay trong callback luôn hợp lệ.

## 9. Retention quyết định bạn có thể đọc lại đến đâu

RabbitMQ Streams được thiết kế lưu trữ log với chính sách retention, thường dựa trên **kích thước tối đa** và/hoặc **thời gian lưu**. Chính sách có thể xóa các **segments** cũ chứ không xóa chính xác từng message tại giây chạm ngưỡng.

```text
Stream trên broker:
  [segment 1][segment 2][segment 3][segment 4][segment 5]
           ^                                          ^
       dữ liệu cũ                                  tail hiện tại

Sau retention:
              [segment 3][segment 4][segment 5]
                    ^
              earliest retained
              (đầu dữ liệu có thể replay)
```

Các tình huống phải chuẩn bị:

- Consumer checkpoint sau cùng là offset 120 nhưng broker chỉ còn dữ liệu từ khoảng 350: replay từ 121 **không thể tái tạo 121..349** chỉ từ stream.
- Một consumer chạy chậm hơn tốc độ retention: dữ liệu có thể hết hạn trước khi nó xử lý tới, dù consumer vẫn còn sống.
- Replay làm lại projection mất nhiều giờ: nếu retention tiếp tục xóa segments cũ trước khi replay đọc xong, kết quả có thể không đầy đủ.
- Dùng `first()` không đảm bảo toàn bộ lịch sử doanh nghiệp: cần snapshot, backup hoặc archive dài hạn nếu đây là yêu cầu nghiệp vụ.

**Đừng thiết kế retention bằng thời gian chờ trung bình duy nhất.** Cần xét thời gian gián đoạn tối đa chấp nhận, backlog lớn nhất, thời gian replay một lần, throughput consumer và chi phí lưu trữ.

Nếu checkpoint nằm **sau tail** do lưu sai, hoặc chỉ tới vùng đã bị retention xóa, không tự động “reset về first” trong production rồi coi đã khôi phục đúng. Phải phát cảnh báo, đối soát nguồn sự thật, chọn snapshot hoặc quyết định nghiệp vụ rõ ràng.

## 10. Stream, super stream và nhiều consumer

### 10.1. Một stream với nhiều consumer logic

Hai consumer ứng dụng khác nhau có thể đọc cùng một stream:

```text
orders.stream: [e1][e2][e3][e4][e5][e6][e7]
                   |          |              |
                   v          v              v
              Billing      Search         Audit
           checkpoint=2  checkpoint=4   checkpoint=7
```

Mỗi consumer logic có tiến độ riêng. Đọc lại Billing không buộc Search hay Audit đọc lại, và một consumer đóng cũng không tự xóa dữ liệu khỏi stream.

### 10.2. Super streams: offset theo partition

**Super stream** là tập nhiều stream partitions cho khả năng scale và routing theo khóa. Với cấu trúc này:

```text
super stream: orders.super
           |
           +-- orders.super-0: offsets 0,1,2,...
           +-- orders.super-1: offsets 0,1,2,...
           +-- orders.super-2: offsets 0,1,2,...
```

Offset 50 của partition 0 **không** tương đương offset 50 của partition 1. Một checkpoint có ý nghĩa phải gắn với **stream partition**, consumer identity và phạm vi dữ liệu. Không lấy `max(offset)` toàn super stream rồi coi đó là checkpoint hợp lệ.

Khi consumer group có nhiều instance, phải xác định **ownership của partition**, bảo đảm hai instance không cùng áp dụng một partition không kiểm soát. Nếu chuyển ownership lúc failover, instance mới resume từ checkpoint của partition đó và chấp nhận redelivery. Ordering theo một aggregate chỉ được đảm bảo trong giới hạn routing key/partition và cách xử lý song song của ứng dụng.

### 10.3. Không dùng offset để thay aggregateVersion

Offset trả lời: **message nằm ở đâu trong một stream partition**. `aggregateVersion` trả lời: **đối tượng nghiệp vụ đã thay đổi đến phiên bản nào**. Hai event cùng aggregate có thể ở hai offset khác nhau; nếu publish lại một event cũ, nó nhận offset mới nhưng có thể vẫn mang cùng `eventId` và `aggregateVersion`.

Khi dựng projection, dùng offset để resume/replay và dùng event ID/version để quyết định duplicate, thứ tự nghiệp vụ và transition hợp lệ.

## 11. Lỗi điển hình khi tracking và replay

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Luôn dùng `next()` khi restart | Có thể bỏ qua backlog | Resume từ checkpoint hoặc chính sách start rõ ràng |
| Coi `last()` là đúng một message cuối | Có thể xử lý nhiều message trong chunk cuối | Hiểu semantics chunk; idempotency |
| Ghi `storeOffset()` trước DB commit | Có thể bỏ qua dữ liệu chưa xử lý khi crash | Commit nghiệp vụ trước rồi checkpoint |
| Không lưu offset hoặc lưu không ổn định | Mỗi restart replay rất nhiều dữ liệu | Dùng named consumer tracking hoặc DB checkpoint |
| Đẩy task async rồi checkpoint ngay | Mark processed trước khi task hoàn thành | Theo dõi completion liên tiếp, backpressure |
| Khởi động replay bằng tên consumer production | Ghi đè/làm thay đổi checkpoint production | Tên replay riêng, lưu checkpoint riêng |
| Replay event và chạy side effect không idempotent | Thanh toán/email bị lặp | Sandbox projection, event ID dedup, chế độ replay |
| Cho nhiều worker ghi checkpoint bằng `MAX(offset)` | Có thể vượt qua offset chưa hoàn tất | Chỉ advance theo thứ tự đã commit |
| Không giám sát retention | Checkpoint rơi sau vùng đã bị xóa | Alert lag vs retention, snapshot/backup |
| Nhầm offset global với partition offset | Resume sai trong super stream | Checkpoint per partition |
| Nhầm `RabbitTemplate` với native stream client | Cấu hình offset không áp dụng như dự kiến | Chọn đúng protocol/API/container |
| Dựa vào broker checkpoint để bảo đảm exactly-once | Xử lý trùng khi crash/retry | Dedup idempotent cùng transaction nghiệp vụ |

**Một nguyên tắc vận hành:** Khi startup, hệ thống nên log nguồn checkpoint, stream/partition, offset bắt đầu được chọn và earliest retained offset (nếu có khả năng truy vấn), đồng thời cảnh báo nếu không thể đảm bảo khôi phục đầy đủ.

## 12. Quan sát offset, lag và khả năng replay

Các metrics và thông tin nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| `last_received_offset` | Offset cao nhất đã đi vào handler; chưa chắc xử lý thành công |
| `last_applied_offset` | Offset cao nhất đã commit nghiệp vụ theo thứ tự |
| `last_stored_offset` | Checkpoint broker hoặc DB hiện đang biết |
| `stream_tail_offset` | Vị trí gần cuối stream theo broker |
| `consumer_offset_lag` | Chênh lệch giữa tail và checkpoint, có thể không phản ánh chính xác số message còn lại |
| `oldest_retained_offset` | Vị trí dữ liệu sớm nhất broker còn giữ |
| `retention_safety_margin` | Khoảng cách/thời gian dự kiến trước khi dữ liệu cần đọc bị retention xóa |
| `offset_store_failures_total` | Lỗi ghi checkpoint |
| `stream_replay_events_total` | Số bản ghi đã xử lý trong một phiên replay |
| `consumer_duplicate_total` | Số event ID được nhận lại |
| `stream_handler_latency` | Thời gian từ callback đến lúc commit nghiệp vụ |

**Không nhầm “lag offset” với “lag thời gian”:** Offset tăng theo số vị trí, còn doanh nghiệp thường quan tâm độ trễ từ `occurredAt` đến khi side effect commit. Kết hợp cả hai, cùng tốc độ append/consume và retention window để dự báo rủi ro consumer tụt hậu.

Log có thể mang `streamName`, `consumerName`, `offset`, `eventId`, `aggregateId`, `correlationId` và hành động `APPLIED`/`DUPLICATE`/`REPLAYED`. Với metrics, tránh gắn từng event ID làm label do cardinality quá cao.

## 13. Thực hành từng bước với RabbitMQ Streams

Dùng một RabbitMQ có Stream plugin hoạt động, một stream `orders.stream` và native Java Stream client. Có thể publish một dãy 10 message với event IDs cố định; trong bài thực hành, tạo vài message bằng producer native client hoặc công cụ của RabbitMQ có hỗ trợ Streams.

### Thí nghiệm 1 — first, last và next

1. Publish 10 message vào `orders.stream`.
2. Tạo consumer với `first()`; ghi lại offsets và số message đọc được.
3. Tạo consumer mới với `last()`; quan sát có thể nhận **nhiều message** ở chunk cuối.
4. Tạo consumer với `next()` rồi publish thêm 2 message; xác minh nó chủ yếu nhận **message mới** sau attach.
5. Ghi rõ offset đầu và cuối mà mỗi consumer quan sát, không chỉ số lượng.

### Thí nghiệm 2 — Bắt đầu từ offset cụ thể

1. Từ kết quả thí nghiệm 1, chọn offset đã ghi nhận của message thứ tư.
2. Tạo consumer mới với `OffsetSpecification.offset(chosenOffset)`.
3. Đối chiếu event ID nhận được; xác minh replay không tự xóa message trước đó.
4. Ghi lại số lượng đọc lại, kiểm tra mọi dữ liệu nằm trong retention.

### Thí nghiệm 3 — Checkpoint manual

1. Dùng consumer tên `billing-projection-test` và `manualTrackingStrategy()`.
2. Xử lý/commit các message; chỉ gọi `context.storeOffset()` **sau xử lý thành công**.
3. Dừng consumer ở offset đã lưu, khởi động lại với chính sách resume được kiểm chứng.
4. Đối chiếu offset đầu của lần khởi động mới và số duplicate (nếu có). Không coi kết quả “không trùng” ở một lần chạy là bảo đảm exactly-once.

### Thí nghiệm 4 — Crash giữa DB commit và storeOffset

1. Giả lập DB projection ghi thành công, rồi dừng ứng dụng trước khi checkpoint broker được lưu.
2. Restart; message cuối có thể được đọc lại.
3. Dùng `processed_stream_events` có unique `eventId` để kiểm tra side effect không lặp.
4. Quan sát checkpoint cuối cùng hội tụ với tiến độ đã commit.

### Thí nghiệm 5 — Replay vào projection sandbox

1. Giữ consumer production và checkpoint của nó nguyên vẹn.
2. Tạo consumer tên riêng, bắt đầu từ offset cũ.
3. Đọc sự kiện vào bảng projection khác.
4. So sánh kết quả checksum/tổng hợp và quyết định cutover theo quy trình, không để replay gọi API thanh toán/thông báo.

### Thí nghiệm 6 — Timestamp

1. Ghi timestamp ở nhiều message cùng khoảng thời gian khác nhau.
2. Chọn `OffsetSpecification.timestamp(epochMillis)` với mốc giữa chuỗi.
3. Quan sát offset thực tế được giao đầu tiên.
4. Lọc lại message theo `occurredAt` nếu yêu cầu giới hạn theo **thời gian nghiệp vụ**.

### Thí nghiệm 7 — Retention

1. Trong môi trường test, thiết lập retention ngắn hoặc kích thước nhỏ để các segments cũ có thể hết hạn.
2. Publish đủ dữ liệu và chờ retention có hiệu lực theo cơ chế broker.
3. Tạo `first()` và offset cũ đã bị loại.
4. Ghi rõ dữ liệu nào **không thể replay**; thử quy trình khôi phục từ snapshot/backup nguồn.

### Thí nghiệm 8 — Super stream và per-partition offset

1. Tạo super stream nhiều partitions, publish cùng partition key cho một aggregate.
2. Quan sát offset của từng partition.
3. Mô phỏng chuyển owner một partition sang consumer instance khác.
4. Xác nhận offset resume theo partition và business event ID vẫn chống duplicate.

**Tiêu chí đạt:** Học viên phân biệt được offset bắt đầu và checkpoint, không checkpoint trước DB commit, hiểu `last()`/`next()`, replay không ảnh hưởng consumer production, biết giới hạn retention và dùng idempotency để chịu được redelivery.

## 14. Câu hỏi tự kiểm tra

1. Tại sao `first()` không phải luôn là message đầu tiên từng được publish vào stream?
2. `last()` có luôn trả đúng một message cuối không?
3. Khác biệt giữa `next()` và `offset(n)` khi consumer restart?
4. Nếu xử lý DB thành công nhưng crash trước `storeOffset()`, điều gì có thể xảy ra và khắc phục ra sao?
5. Nếu `storeOffset()` chạy trước DB commit, vì sao có nguy cơ mất xử lý?
6. `eventId` khác stream offset thế nào khi producer publish lại cùng một event?
7. Tại sao consumer chỉ xử lý đúng một stream partition mới có thể đơn giản cập nhật `last_applied_offset` sau mỗi message?
8. Khi phải rebuild projection từ đầu nhưng retention đã xóa dữ liệu lịch sử, hướng khôi phục nào phù hợp?
9. Vì sao timestamp broker không nhất thiết khớp timestamp event trong JSON?
10. Có thể dùng một checkpoint offset chung cho mọi partition trong super stream không?

**Đáp án gợi ý:** (1) retention có thể xóa message cũ; (2) không, `last` thường bắt đầu từ chunk cuối; (3) `next` bỏ backlog còn `offset(n)` chủ đích đọc từ vị trí n; (4) có thể replay trùng, cần idempotency; (5) checkpoint có thể vượt tác dụng phụ chưa commit; (6) cùng event ID có thể nằm ở nhiều offset khác nhau; (7) tránh đánh dấu vượt message chưa hoàn tất; (8) dùng snapshot/backup/reconciliation; (9) timestamp broker và thời gian nghiệp vụ có nguồn/semantics khác; (10) không.

## 15. Tổng kết

RabbitMQ Streams cho phép consumer **định vị nơi bắt đầu đọc**, **lưu tiến độ đã xử lý** và **đọc lại dữ liệu lịch sử còn trong retention**. `first()`, `last()`, `next()`, `offset(n)` và `timestamp(t)` giải quyết những nhu cầu khởi tạo khác nhau. Chúng không tự tạo cam kết exactly-once: tiến độ thực sự cần dựa trên **xử lý nghiệp vụ đã commit**, còn broker checkpoint có thể trễ hơn và dẫn tới replay.

Khi dùng Stream với Spring AMQP, cần phân biệt native stream client với `RabbitTemplate`/`@RabbitListener` classic queue, chọn đúng container/API theo protocol. Kết hợp **stable event ID, idempotent consumer, checkpoint có ranh giới transaction rõ ràng, retention đủ dài, quan sát lag và replay có kiểm soát** để đáp ứng yêu cầu độ tin cậy đầu cuối.

### Tài liệu tham khảo

- [RabbitMQ — Streams](https://www.rabbitmq.com/docs/streams): đặc điểm lưu trữ, retention và cơ chế sử dụng stream.
- [RabbitMQ — Stream Protocol](https://www.rabbitmq.com/docs/stream): native protocol, offset và các lựa chọn khi consume.
- [RabbitMQ Stream Java Client — Consumer Offset Tracking](https://rabbitmq.github.io/rabbitmq-stream-java-client/stable/htmlsingle/#consumer-offset-tracking): consumer có tên, chiến lược tracking và lưu offset.
- [RabbitMQ Stream Java Client — Consuming](https://rabbitmq.github.io/rabbitmq-stream-java-client/stable/htmlsingle/#consuming): `OffsetSpecification`, consumer builder và callback.
- [Spring AMQP — Using the RabbitMQ Stream Plugin](https://docs.spring.io/spring-amqp/reference/stream.html): tích hợp Spring AMQP với native RabbitMQ Streams.

