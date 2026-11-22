# Xử lý ít nhất một lần và thiết kế consumer lũy đẳng

**Redis Streams** là cấu trúc dữ liệu Redis lưu các bản ghi có ID theo thứ tự. Khác với Redis Pub/Sub truyền thông điệp tức thời cho subscriber đang kết nối, Stream có thể giữ message để consumer đọc sau. Với **consumer group**, Redis còn theo dõi những bản ghi đã giao cho consumer nhưng chưa được xác nhận bằng `XACK`.

Nhờ đó, ứng dụng sử dụng **Spring Data Redis** có thể xây dựng quy trình xử lý theo hướng *at-least-once* (ít nhất một lần): nếu consumer nhận message nhưng chết trước khi xác nhận, một consumer có thể nhận lại message đang pending và thử xử lý tiếp. Tuy nhiên, **giao lại đồng nghĩa một message có thể được xử lý nhiều lần**. Để không trừ tiền hai lần, gửi hai email hay cộng số liệu hai lần, handler phải được thiết kế **lũy đẳng (idempotent)**.

Mục tiêu của bài học là hiểu đường đi `XADD → XREADGROUP → xử lý nghiệp vụ → XACK`, cách khôi phục pending message và cách kết hợp khóa chống trùng với transaction dữ liệu nghiệp vụ. Ví dụ dùng Spring Data Redis, Java 21 và PostgreSQL cho một thao tác cần tính nhất quán.

## 1. At-least-once là cam kết gì?

Các thuật ngữ delivery thường gặp:

| Ngữ nghĩa | Ý nghĩa | Hệ quả với consumer |
| --- | --- | --- |
| **At-most-once** | Một lần giao hoặc không giao; message có thể mất khi lỗi | Ít nguy cơ trùng do broker, nhưng có nguy cơ bỏ sót |
| **At-least-once** | Message chưa hoàn tất có thể được giao lại cho đến khi được xác nhận, khi hệ thống còn giữ message và có recovery | Handler phải chấp nhận xử lý lặp |
| **Exactly-once effect** | Tác động nghiệp vụ được áp dụng một lần cho cùng một sự kiện logic | Cần idempotency, transaction hoặc giao thức phối hợp thích hợp |

Ở Redis Streams, consumer group dùng **Pending Entries List (PEL)** để theo dõi việc giao message. Điều này hỗ trợ xây dựng at-least-once, nhưng kết quả thực tế còn phụ thuộc việc ứng dụng **khôi phục pending**, cấu hình retention và độ bền dữ liệu của Redis. Chỉ tạo một group rồi gọi `XREADGROUP` không tự tạo bảo đảm tuyệt đối rằng mọi sự kiện sẽ được xử lý thành công.

Lũy đẳng là tính chất:

\[
f(f(s,e),e)=f(s,e)
\]

Trong đó `s` là trạng thái nghiệp vụ và `e` là một sự kiện. Xử lý cùng sự kiện `e` thêm lần nữa không làm thay đổi kết quả cuối so với xử lý một lần.

Ví dụ:

- `SET order:101:status PAID` với cùng trạng thái có thể có hiệu ứng cuối lũy đẳng, nếu không có side effect phụ.
- `INCR total_paid` hoặc `UPDATE balance = balance + 100` **không lũy đẳng**; chạy hai lần làm tăng hai lần.
- Gửi email, gọi cổng thanh toán hoặc ghi thông báo ra ngoài **không trở thành lũy đẳng** chỉ vì thao tác Redis được thực hiện bằng cùng một message.

Do đó, thiết kế đúng cần xét **tác động nghiệp vụ**, không chỉ đếm số lần callback được gọi.

## 2. Vòng đời message trong consumer group

Giả sử hệ thống có stream `billing:payments` và group `billing-workers`. Publisher đưa sự kiện thanh toán vào stream:

~~~redis
XADD billing:payments * eventId evt-101 invoiceId inv-42 amountCents 125000
~~~

Redis tạo một **Stream ID**, ví dụ `1731500000000-0`. ID này khác với `eventId` nghiệp vụ do publisher tạo:

- **Stream ID** định danh entry cụ thể trong Redis Stream, dùng cho `XACK`, `XPENDING`, `XCLAIM` hoặc `XAUTOCLAIM`.
- **eventId** định danh sự kiện nghiệp vụ theo hợp đồng giữa các hệ thống; cùng sự kiện được publish lại có thể nhận một Stream ID mới nhưng cần giữ nguyên `eventId`.

Tạo group trước khi worker bắt đầu:

~~~redis
XGROUP CREATE billing:payments billing-workers 0 MKSTREAM
~~~

ID `0` yêu cầu group có thể đọc từ đầu những entry hiện đang lưu trong stream. Nếu tạo group bằng `$`, group bắt đầu từ những message **mới kể từ thời điểm tạo group**, bỏ qua các entry cũ trong cách đọc thông thường.

Worker đọc message mới:

~~~redis
XREADGROUP GROUP billing-workers worker-a COUNT 10 BLOCK 2000 STREAMS billing:payments >
~~~

Ký hiệu `>` có nghĩa consumer group nhận những entry **chưa được giao cho consumer nào trong group**. Redis thêm các message vừa giao vào PEL của group, gắn với consumer đang sở hữu chúng.

Sau khi nghiệp vụ hoàn tất:

~~~redis
XACK billing:payments billing-workers 1731500000000-0
~~~

`XACK` gỡ entry khỏi PEL của group. Nó **không phải lệnh xóa message khỏi chính stream**. Entry vẫn có thể tồn tại cho đến khi bị trim hoặc xóa theo chính sách lưu trữ.

~~~text
Publisher                   Redis Streams                 Consumer
    |                            |                            |
    +-- XADD ------------------->| entry lưu trong stream      |
    |                            |                            |
    |                            |<----- XREADGROUP (>) -------+
    |                            |------ message ------------>|
    |                            |     thêm entry vào PEL      |
    |                            |                            |
    |                            |                     Xử lý nghiệp vụ
    |                            |                            |
    |                            |<--------- XACK -------------+
    |                            |     gỡ entry khỏi PEL       |
~~~

**Điểm mấu chốt:** ACK xác nhận tiến độ xử lý của group, còn dữ liệu stream và tác động nghiệp vụ có vòng đời riêng.

## 3. Pending Entries List và lý do message được giao lại

PEL lưu dấu những entry đã giao nhưng chưa ACK. Với một entry đang pending, Redis có thể theo dõi consumer sở hữu, thời gian idle và số lần giao.

Các lệnh quan sát:

~~~redis
XPENDING billing:payments billing-workers
XPENDING billing:payments billing-workers - + 10
~~~

Lệnh đầu cung cấp tổng quan số pending, dải ID và phân bố theo consumer. Dạng mở rộng có thể hiển thị ID, consumer, idle time và số lần giao. **Pending không tự đồng nghĩa với lỗi**: một message đang được xử lý bình thường cũng là pending cho đến khi ACK.

### Bốn tình huống quan trọng

| Thời điểm có sự cố | Trạng thái có thể xảy ra | Hành vi khi recovery |
| --- | --- | --- |
| Trước khi `XREADGROUP` giao message | Entry chưa giao, chưa vào PEL | Worker trong group có thể đọc như message mới |
| Sau khi nhận, trước khi ghi nghiệp vụ | Entry pending, chưa có side effect | Consumer nhận lại và xử lý |
| Sau khi ghi nghiệp vụ thành công, trước `XACK` | Side effect đã xảy ra; entry vẫn pending | **Có nguy cơ xử lý trùng** |
| Sau khi `XACK` thành công | Entry không còn pending | Group không tự giao lại vì thiếu ACK |

Trường hợp thứ ba là lý do cần idempotency. Ví dụ:

~~~text
1. Worker A nhận event evt-101.
2. Worker A cộng 125.000 vào tổng tiền đã thanh toán.
3. Database commit thành công.
4. Worker A mất điện trước XACK.
5. Redis vẫn giữ entry trong PEL.
6. Worker B claim entry và xử lý lại.
7. Nếu code cộng tiền lần nữa → sai nghiệp vụ.
~~~

Không thể giải quyết bằng cách chuyển `XACK` lên trước bước commit:

~~~text
XACK thành công
    |
    v
Worker crash trước khi cập nhật database
    |
    v
Message không còn pending, tác động nghiệp vụ chưa xảy ra
~~~

Quy tắc mặc định cho consumer có xử lý bền vững là **ACK sau khi tác động nghiệp vụ đã hoàn tất và được commit**. Khi đó cần chấp nhận khả năng xử lý lặp và làm handler lũy đẳng.

## 4. Hai lớp định danh để chống trùng

Không nên dùng tên consumer, ID Redis connection hoặc thời gian nhận làm khóa idempotency. Chúng thay đổi khi worker restart và không đại diện cho sự kiện.

Có hai mức chống trùng:

| Khóa | Phát hiện được | Giới hạn |
| --- | --- | --- |
| **Stream ID** | Cùng một entry Redis được giao lại sau crash/claim | Không nhận ra cùng sự kiện được publisher ghi lại thành entry mới |
| **eventId nghiệp vụ** | Cùng sự kiện logic được giao lại hoặc publish lại với Stream ID khác | Cần producer giữ eventId ổn định khi retry và bảo đảm không tái dùng eventId cho sự kiện khác |

Ví dụ một publisher không biết lệnh `XADD` đã thành công hay chưa và thử lại:

~~~text
Stream ID 1731500000000-0   eventId=evt-101
Stream ID 1731500000005-0   eventId=evt-101
~~~

Hai entry là hai bản ghi Redis riêng, nhưng cùng đại diện cho một sự kiện logic. Dedupe theo Stream ID sẽ xem chúng là hai sự kiện; dedupe theo `eventId` có thể nhận ra trùng lặp.

**eventId phải ổn định qua retry**. Nếu producer tạo UUID mới mỗi lần gửi lại cùng một thao tác, consumer không có cách tổng quát để biết hai payload là một sự kiện logic. Đồng thời, một `eventId` lặp lại với payload khác nhau là vi phạm hợp đồng cần được phát hiện, không nên im lặng coi là hợp lệ.

## 5. Một cách tưởng đúng nhưng có thể làm mất nghiệp vụ

Giả sử consumer đánh dấu đã xử lý bằng Redis:

~~~redis
SET processed:evt-101 1 NX EX 86400
~~~

Nếu lệnh thành công, consumer tiếp tục ghi database. Nếu key đã tồn tại, consumer bỏ qua.

Cách này hữu ích trong một số bài toán đơn giản, nhưng **không đủ** cho thao tác nghiệp vụ quan trọng khi dấu chống trùng và side effect nằm ở hai tài nguyên khác nhau.

~~~text
SET processed:evt-101 1 NX EX 86400  → thành công
                     |
                 Worker crash
                     |
             Chưa cập nhật database
                     |
        Retry thấy processed key đã tồn tại
                     |
                 Bỏ qua xử lý
                     |
          Nghiệp vụ bị mất vĩnh viễn
~~~

Đảo thứ tự cũng không hoàn toàn giải quyết:

~~~text
Cập nhật database thành công
         |
      Worker crash
         |
Chưa ghi processed key
         |
Retry cập nhật database lần nữa
~~~

Muốn chắc chắn **dấu đã xử lý và thay đổi dữ liệu nghiệp vụ cùng thành công hoặc cùng rollback**, hãy đặt chúng trong **cùng một transaction của nơi lưu dữ liệu nghiệp vụ**, khi nơi đó hỗ trợ giao dịch phù hợp.

Redis có thể hỗ trợ Lua script hoặc transaction cho dữ liệu hoàn toàn nằm trong Redis, nhưng chúng không tự bao trùm một giao dịch PostgreSQL và một cuộc gọi HTTP tới hệ thống ngoài.

## 6. Thiết kế lũy đẳng bằng ràng buộc duy nhất trong database

Ví dụ nghiệp vụ: mỗi sự kiện `PaymentReceived` cộng số tiền vào tổng thanh toán của hóa đơn. Nếu cộng hai lần, số tiền sẽ sai. Ta dùng PostgreSQL và lưu một dấu chống trùng với khóa duy nhất theo **handler + eventId**.

### 6.1. Schema minh họa

~~~sql
CREATE TABLE invoice_totals (
    invoice_id VARCHAR(100) PRIMARY KEY,
    total_paid_cents BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE processed_events (
    handler_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (handler_name, event_id)
);
~~~

`handler_name` cho phép nhiều loại consumer/handler cùng dùng một `eventId` mà vẫn độc lập về kết quả xử lý. Nếu một sự kiện phải tạo nhiều projection khác nhau, mỗi handler cần ghi dấu thành công của chính mình.

Trong dự án dùng SQL database khác, cú pháp chèn bỏ qua xung đột sẽ khác. Ví dụ bên dưới sử dụng `ON CONFLICT DO NOTHING` của PostgreSQL.

### 6.2. Service áp dụng side effect cùng dấu chống trùng

~~~java
package com.example.redis.streams;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentProjectionService {

    private static final String HANDLER = "invoice-payment-projection";

    private final JdbcTemplate jdbc;

    public PaymentProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(String eventId, String invoiceId, long amountCents) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }
        if (invoiceId == null || invoiceId.isBlank() || amountCents <= 0) {
            throw new IllegalArgumentException(
                "Invalid payment event"
            );
        }

        int inserted = jdbc.update(
            """
            INSERT INTO processed_events (handler_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            HANDLER, eventId
        );

        if (inserted == 0) {
            // Handler này đã commit thành công cùng eventId trước đó.
            return;
        }

        int updated = jdbc.update(
            """
            UPDATE invoice_totals
            SET total_paid_cents = total_paid_cents + ?
            WHERE invoice_id = ?
            """,
            amountCents, invoiceId
        );

        if (updated != 1) {
            // Exception khiến marker vừa INSERT cũng rollback.
            throw new IllegalStateException(
                "Invoice not found: " + invoiceId
            );
        }
    }
}
~~~

Ví dụ yêu cầu ứng dụng có `JdbcTemplate`, `PlatformTransactionManager` cho PostgreSQL và phương thức `apply` được gọi qua Spring proxy để `@Transactional` thực sự có hiệu lực. Spring Boot với JDBC starter và DataSource cấu hình đúng thường cung cấp những thành phần này. Nếu method bị gọi nội bộ trong cùng bean (self-invocation), giao dịch qua proxy có thể không được áp dụng.

### Vì sao cách này chống trùng khi có hai worker?

Giả sử worker A và worker B xử lý cùng `eventId` gần như đồng thời:

1. Cả hai thử `INSERT` khóa `(handler_name, event_id)`.
2. Ràng buộc `PRIMARY KEY` trong PostgreSQL bảo đảm chỉ một transaction có thể commit dấu đó.
3. Transaction thắng tiếp tục cập nhật hóa đơn và commit cả hai thay đổi.
4. Transaction còn lại khi thấy conflict sẽ không cộng tiền nữa.
5. Nếu transaction thắng bị rollback vì lỗi cập nhật hóa đơn, dấu cũng rollback; lần retry sau có cơ hội thực hiện nghiệp vụ.

Đặc tính quan trọng không phải là câu lệnh kiểm tra trước `SELECT EXISTS`, vì kiểm tra rồi ghi có thể race. **Ràng buộc duy nhất của database cùng transaction** mới là biên giới nhất quán ở đây.

Lưu ý: ở ví dụ này, tăng `total_paid_cents` một lần vẫn đòi hỏi mỗi hóa đơn đã có bản ghi `invoice_totals`. Nếu hóa đơn không tồn tại, transaction thất bại và entry Redis vẫn cần được retry hoặc chuyển xử lý sự cố. Trong hệ thống thực, nên kiểm tra thêm currency, version, event type và bất biến nghiệp vụ.

## 7. Xử lý message bằng Spring Data Redis và ACK sau commit

Giả sử Redis đã có consumer group:

~~~redis
XGROUP CREATE billing:payments billing-workers 0 MKSTREAM
~~~

Lệnh tạo group chỉ chạy khi khởi tạo hạ tầng, không lặp lại một cách vô điều kiện ở mỗi lần xử lý. Nếu group đã tồn tại, Redis sẽ trả lỗi tương ứng; mã bootstrap cần xử lý trường hợp đó mà không che những lỗi kết nối hay cấu hình khác.

Một ví dụ poll theo batch sử dụng `StringRedisTemplate` và `StreamOperations`:

~~~java
package com.example.redis.streams;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class PaymentStreamConsumer {

    private static final Logger log =
        LoggerFactory.getLogger(PaymentStreamConsumer.class);

    private static final String STREAM = "billing:payments";
    private static final String GROUP = "billing-workers";

    private final StreamOperations<String, String, String> streams;
    private final PaymentProjectionService projection;

    public PaymentStreamConsumer(
            StringRedisTemplate redis,
            PaymentProjectionService projection) {
        this.streams = redis.opsForStream();
        this.projection = projection;
    }

    // Gọi từ một worker được quản lý vòng đời, không chạy trong HTTP request.
    public int pollOnce(String consumerName) {
        List<MapRecord<String, String, String>> records = streams.read(
            Consumer.from(GROUP, consumerName),
            StreamReadOptions.empty()
                .count(10)
                .block(Duration.ofSeconds(2)),
            StreamOffset.create(STREAM, ReadOffset.lastConsumed())
        );

        if (records == null || records.isEmpty()) {
            return 0;
        }

        for (MapRecord<String, String, String> record : records) {
            try {
                Map<String, String> data = record.getValue();
                String eventId = data.get("eventId");
                String invoiceId = data.get("invoiceId");
                long amountCents = Long.parseLong(
                    data.get("amountCents")
                );

                // Phương thức @Transactional: marker + side effect
                // cùng commit hoặc cùng rollback trong PostgreSQL.
                projection.apply(eventId, invoiceId, amountCents);

                // Chỉ ACK SAU khi apply() trả về thành công.
                streams.acknowledge(STREAM, GROUP, record.getId());
            } catch (Exception error) {
                // Không ACK khi xử lý lỗi.
                // Entry vẫn pending để recovery quyết định retry/DLQ.
                log.warn(
                    "Failed stream entry id={} in group={}",
                    record.getId(), GROUP, error
                );
            }
        }

        return records.size();
    }
}
~~~

Các import và API minh họa mô hình Spring Data Redis 3.x. `StringRedisTemplate` sử dụng string serializer cho key/value/hash; bên phát và bên đọc phải thống nhất encoding và định dạng field. Nếu stream dùng binary payload hoặc một serializer tùy biến, kiểu `MapRecord` và cách deserialize phải thay đổi tương ứng.

**Không để `@Transactional` của PostgreSQL bao trùm việc chờ `XREADGROUP` và toàn bộ vòng poll.** Transaction nên chỉ giữ trong phần cập nhật database; ACK thực hiện sau khi method transactional hoàn tất. Điều này tránh giữ transaction/connection DB trong suốt thời gian Redis đang chờ message.

### Một vòng poll chưa phải một hệ thống consumer hoàn chỉnh

`pollOnce` là lõi xử lý, cần được gọi từ worker có lifecycle riêng. Ứng dụng production phải:

- Bắt đầu worker khi consumer group và connection sẵn sàng.
- Sử dụng `consumerName` ổn định hoặc quản lý danh tính phù hợp theo instance; nhiều worker cùng group nên có tên phân biệt.
- Dừng vòng poll khi ứng dụng shutdown; giới hạn thời gian block để có thể dừng hợp lý.
- Giới hạn số message đang xử lý và lượng tài nguyên DB/Redis.
- Có cơ chế riêng để xử lý **pending cũ**, vì `ReadOffset.lastConsumed()` trong consumer group thường lấy message mới, không tự quét tất cả pending.

Spring Data Redis còn có `StreamMessageListenerContainer` và `StreamReceiver` cho mô hình lắng nghe liên tục. Khi dùng listener container, phải **tắt auto-ack** nếu nghiệp vụ yêu cầu chỉ ACK sau khi commit; tự động ACK sai thời điểm có thể làm mất cơ hội retry.

## 8. Vì sao `ReadOffset.lastConsumed()` không đủ cho khôi phục?

Trong Redis CLI, consumer group dùng:

~~~redis
XREADGROUP GROUP billing-workers worker-a STREAMS billing:payments >
~~~

Dấu `>` hướng tới những entry **chưa được giao**. Một entry từng được giao cho `worker-a` nhưng chưa ACK sẽ nằm trong PEL; chỉ gọi `>` tiếp tục có thể không đọc lại entry đang pending đó.

Có hai hướng khôi phục:

1. **Đọc pending của chính consumer** bằng cách dùng ID khác `>` trong `XREADGROUP`, ví dụ ID `0`, để xử lý các entry đang pending cho consumer đó.
2. **Claim pending từ consumer cũ** bằng `XCLAIM` hoặc `XAUTOCLAIM`, phù hợp khi worker cũ đã chết hoặc không còn khả năng hoàn tất.

Ví dụ đọc lại pending của chính `worker-a`:

~~~redis
XREADGROUP GROUP billing-workers worker-a COUNT 10 STREAMS billing:payments 0
~~~

Với ID `0`, Redis trả về các entry pending cho consumer tương ứng theo phạm vi ID, không phải những entry chưa từng được giao. Cần phân biệt rõ với `>`.

### Recovery bằng `XAUTOCLAIM`

`XAUTOCLAIM` (Redis 6.2 trở lên) giúp tìm và chuyển quyền sở hữu những entry pending đã idle đủ lâu:

~~~redis
XAUTOCLAIM billing:payments billing-workers worker-b 60000 0-0 COUNT 100
~~~

Ý nghĩa:

| Tham số | Vai trò |
| --- | --- |
| `billing:payments` | Tên stream |
| `billing-workers` | Consumer group |
| `worker-b` | Consumer nhận quyền xử lý entry |
| `60000` | Idle tối thiểu 60.000 ms trước khi được claim |
| `0-0` | ID bắt đầu quét PEL |
| `COUNT 100` | Số entry mục tiêu cho mỗi lượt claim |

Kết quả `XAUTOCLAIM` gồm cursor ID để tiếp tục quét và các entry được claim. Worker cần tiếp tục theo cursor đến khi hoàn thành lượt quét, rồi có thể lên lịch quét lại trong tương lai. Với các phiên bản Redis mới hơn, kết quả có thể còn kèm ID của entry đã bị xóa khỏi stream nhưng vẫn được tham chiếu trong PEL.

**Không đặt min-idle quá ngắn.** Nếu một worker đang xử lý hợp lệ mất 90 giây nhưng `XAUTOCLAIM` lấy entry ngay sau 5 giây, hai worker có thể cùng xử lý nó. Idempotency vẫn phải chịu được tình huống đó, nhưng claim quá sớm gây tải và lỗi vận hành không cần thiết.

Trong hệ thống có thời gian xử lý biến thiên, nên đo p95/p99 processing duration rồi chọn min-idle, timeout và recovery interval tương ứng. Với công việc rất dài, có thể cần mô hình heartbeat/tiếp tục claim hợp lý để phân biệt worker chậm với worker đã chết.

## 9. Retry, poison message và Dead Letter Queue

Không phải mọi lỗi đều nên retry mãi mãi:

- **Lỗi tạm thời**: database timeout, Redis network, dịch vụ phụ thuộc đang quá tải; retry có backoff thường hữu ích.
- **Lỗi dữ liệu cố định**: thiếu `eventId`, sai định dạng số tiền, schema event không còn tương thích; retry vô hạn không tự sửa payload.
- **Lỗi nghiệp vụ có điều kiện**: hóa đơn chưa được tạo hoặc trạng thái chưa sẵn sàng; phải phân biệt thứ tự sự kiện với lỗi không thể khôi phục.

Thông tin PEL có thể cho biết **số lần entry được giao**. Nhưng “delivery count” không đồng nghĩa số lần cập nhật database thành công: một lần giao có thể chưa vào handler, còn một handler có thể xử lý lỗi trước khi ghi DB.

Một chính sách vận hành khả thi:

~~~text
Entry pending quá lâu
         |
         v
XAUTOCLAIM vào worker recovery
         |
         v
Kiểm tra số lần giao / lỗi gần nhất
         |
      +-- có thể retry --> xử lý lại --> commit --> XACK
      |
      +-- không thể xử lý tiếp
                    |
                    v
           Ghi bền vững vào DLQ
                    |
                    v
           Xác nhận ghi DLQ thành công
                    |
                    v
           XACK entry ở group gốc
~~~

Ví dụ DLQ cũng có thể là một Redis Stream riêng, chẳng hạn `billing:payments:dlq`, hoặc bảng database lưu payload và nguyên nhân lỗi để con người điều tra.

**Quan trọng:** nếu ghi DLQ thành công nhưng worker chết trước khi ACK entry gốc, recovery có thể ghi DLQ lần nữa. Nếu cần DLQ không trùng, phải có khóa idempotency riêng hoặc một giao thức kiểm soát chuyển trạng thái; đơn thuần gọi `XADD DLQ` rồi `XACK` ở hai lệnh khác nhau không đảm bảo cả hai cùng xảy ra.

Không ACK message lỗi chỉ để “dọn” PEL nếu chưa có quyết định rằng sự kiện đó được phép bỏ qua hoặc đã được lưu ở nơi xử lý tiếp.

## 10. Idempotency với side effect bên ngoài database

Giải pháp `processed_events` + transaction PostgreSQL trong phần trước bảo đảm một lần cập nhật **cho những thay đổi nằm trong cùng database transaction đó**. Nó không tự bao trùm email, HTTP, object storage hoặc một Redis key khác.

Giả sử handler làm:

~~~text
1. INSERT processed_events
2. UPDATE invoice_totals
3. Gửi email xác nhận
4. COMMIT PostgreSQL
5. XACK Redis
~~~

Nếu email đã gửi nhưng PostgreSQL rollback, lần retry có thể gửi email thứ hai. Nếu database commit nhưng ứng dụng chết trước khi gửi email, có thể mất email dù event đã được xem là xử lý xong.

Một giải pháp phổ biến là **transactional outbox**:

~~~text
          Redis Stream event
                 |
                 v
       Transaction PostgreSQL
        /        |          \
       v         v           v
  Dấu đã xử lý  Cập nhật DB  Outbox row
        \        |          /
         +-------+---------+
                 |
             COMMIT DB
                 |
                 v
               XACK

         Outbox publisher riêng
                 |
                 v
       Gửi email / API / event mới
                 |
                 v
       Ghi trạng thái gửi + retry
~~~

Outbox giúp không mất **ý định thực hiện side effect**, nhưng publisher ra hệ thống ngoài vẫn có thể gửi trùng nếu phản hồi bị mất sau khi phía nhận đã xử lý. Khi có thể, truyền một **idempotency key** tới API đích hoặc dùng khóa nghiệp vụ duy nhất phía đích. Với email, cần xác định chấp nhận gửi trùng hay xây dựng cơ chế ghi nhận/tránh trùng theo yêu cầu thực tế.

Tương tự, nếu mọi trạng thái nghiệp vụ nằm trong Redis, có thể cân nhắc một Lua script hoặc thao tác dữ liệu Redis nguyên tử để vừa kiểm tra eventId vừa áp dụng hiệu ứng trong phạm vi phù hợp. Nhưng giao dịch Redis không tự bảo đảm atomicity với PostgreSQL hay hệ thống bên ngoài.

## 11. Dữ liệu trùng, thứ tự và cạnh tranh giữa các consumer

At-least-once không có nghĩa mọi event sẽ được xử lý đúng thứ tự nghiệp vụ:

- Redis Stream có thứ tự entry theo ID, nhưng nhiều consumer trong một group xử lý song song và hoàn tất ở những thời điểm khác nhau.
- Một event cũ đang pending có thể được claim sau khi những event mới hơn đã hoàn tất.
- Một producer có thể phát cùng sự kiện logic nhiều lần với các Stream ID khác nhau.

Ví dụ:

~~~text
evt-10: Đặt trạng thái đơn hàng = PAID
evt-11: Đặt trạng thái đơn hàng = REFUNDED
~~~

Nếu `evt-11` hoàn tất trước `evt-10`, một handler chỉ dùng `SET status = ...` có thể ghi ngược trạng thái về `PAID`. Cả hai event đều được xử lý **một lần**, nhưng trạng thái cuối vẫn sai.

Do đó, bên cạnh idempotency key, một số nghiệp vụ cần:

- **Version/sequence** theo aggregate, ví dụ `orderVersion = 12`.
- **Conditional update** chỉ khi version kế tiếp hợp lệ, hoặc nếu event mới hơn.
- **Partitioning theo entity** để những event của cùng aggregate đi qua một luồng xử lý có thứ tự nhất định.
- **Reconciliation** để khôi phục khi một event bị thiếu hoặc đến quá muộn.

Ví dụ cập nhật có kiểm soát version ở PostgreSQL:

~~~sql
UPDATE order_projection
SET status = :new_status, version = :event_version
WHERE order_id = :order_id
  AND version < :event_version;
~~~

Điều kiện `version < event_version` chỉ là ví dụ cho mô hình “event mới nhất thắng”. Với event cần áp dụng tuần tự từng bước và không được bỏ qua version trung gian, cần điều kiện mạnh hơn, chẳng hạn `version = event_version - 1` và xử lý khoảng trống.

**Lũy đẳng** giải quyết trùng cùng một sự kiện; **ordering/versioning** giải quyết quan hệ giữa các sự kiện khác nhau.

## 12. Retention của Stream và tuổi thọ dấu chống trùng

At-least-once chỉ còn ý nghĩa khi Redis vẫn giữ dữ liệu cần retry. Có thể giới hạn kích thước stream bằng `MAXLEN` hoặc giới hạn theo ID/thời gian bằng chính sách trim, nhưng phải cân nhắc message chưa được ACK.

Ví dụ:

~~~redis
XADD billing:payments MAXLEN ~ 100000 * eventId evt-202 invoiceId inv-50 amountCents 75000
~~~

Ký hiệu `~` là cơ chế cắt gần đúng. Việc trim có thể loại bỏ một entry khỏi stream **kể cả khi entry đó chưa được xử lý xong**; tùy lệnh và phiên bản, PEL có thể còn tham chiếu tới ID mà payload đã không còn. Recovery không thể tái xử lý một payload đã bị xóa trừ khi có bản sao bền vững ở nơi khác.

Vì vậy:

1. Chọn retention đủ dài so với downtime, min-idle claim, thời gian retry và giới hạn vận hành.
2. Giám sát pending lâu ngày và độ trễ xử lý trước khi áp dụng trim mạnh.
3. Có chính sách backup/persistence/replication Redis phù hợp với độ bền dữ liệu yêu cầu.
4. Với sự kiện tuyệt đối không được mất, cân nhắc source-of-truth và log bền vững ngoài cache memory.

Redis Streams lưu entry, nhưng mức bền vững của dữ liệu còn phụ thuộc AOF/RDB, replication và phương án khôi phục khi Redis/server hỏng. **At-least-once không phải lời hứa không bao giờ mất dữ liệu dưới mọi cấu hình hạ tầng**.

### Dấu idempotency được giữ bao lâu?

Nếu dùng bảng `processed_events`, việc xóa dấu quá sớm có thể khiến message bị retry rất muộn và tác động lại lần nữa. Giả sử marker chỉ giữ 24 giờ nhưng một entry còn pending hoặc một producer replay sau 72 giờ; handler có thể xem event cũ là mới.

Thời hạn giữ dấu phải ít nhất phản ánh:

- Khoảng thời gian mà cùng eventId còn có thể được gửi lại.
- Retention của stream và thời gian retry/DLQ/replay.
- Độ quan trọng của nghiệp vụ, ví dụ sự kiện thanh toán có thể cần giữ dấu lâu dài.

Nếu marker quá nhiều, có thể phân vùng bảng theo thời gian và dọn theo policy kiểm soát, nhưng không được xóa chỉ để tiết kiệm dung lượng mà vô tình mở cửa cho double charge.

## 13. Vận hành với nhiều consumer instance

Một consumer group có thể có nhiều consumer:

~~~text
                  Redis Stream
                billing:payments
                       |
               Group billing-workers
                /       |       \
               v        v        v
           worker-a  worker-b  worker-c
               |        |        |
               +--------+--------+
                        |
                    PostgreSQL
             UNIQUE(handler,eventId)
~~~

Redis phân phối các message mới trong group theo cơ chế consumer group; mỗi entry mới thông thường được giao tới một consumer. Khi worker chết, entry đang pending không tự biến mất: recovery có thể claim lại sang worker khác. Do đó, dù một entry thường có **một consumer sở hữu ở mỗi thời điểm**, hai tiến trình vẫn có thể cùng thực hiện tác động nghiệp vụ nếu claim quá sớm hoặc kết nối trễ.

Ràng buộc duy nhất trong PostgreSQL bảo vệ trạng thái ngay cả khi ứng dụng có nhiều instance. Semaphore hoặc map `seenEventIds` trong một JVM không đủ vì mỗi instance có bộ nhớ riêng và bộ nhớ sẽ mất khi restart.

Các vấn đề vận hành nên được quan sát:

| Chỉ số | Điều muốn phát hiện |
| --- | --- |
| Số pending trong group | Tồn đọng chưa ACK |
| Pending idle p95/p99 hoặc oldest idle | Worker treo hoặc bị bỏ quên |
| Delivery attempts/claims | Retry bất thường, lỗi kéo dài |
| Thời gian xử lý message | Có cần tăng min-idle hay giảm concurrency |
| Số eventId trùng được bỏ qua | Tần suất duplicate delivery hoặc duplicate publish |
| Lỗi commit và lỗi ACK | Phân biệt lỗi nghiệp vụ với lỗi broker |
| DLQ size và tuổi bản ghi lớn nhất | Poison messages cần can thiệp |
| Stream length/retention | Nguy cơ trim trước khi recovery |
| Consumer lag và throughput | Khả năng theo kịp producer |

Tại Redis, có thể quan sát bằng:

~~~redis
XINFO STREAM billing:payments
XINFO GROUPS billing:payments
XINFO CONSUMERS billing:payments billing-workers
XPENDING billing:payments billing-workers
~~~

Chỉ số `lag` hoặc các trường thông tin trả về có thể khác theo phiên bản Redis và tình trạng group; không nên suy luận duy nhất từ một con số để kết luận toàn bộ pipeline xử lý ổn định.

## 14. Kiểm thử để chứng minh lũy đẳng và recovery

Một hệ thống cần kiểm tra cả **bảo đảm nghiệp vụ** lẫn **hành vi message pending**. Các ca kiểm thử sau phù hợp với bài học:

| Trường hợp | Tác động mong đợi |
| --- | --- |
| Xử lý cùng `eventId` hai lần trong một worker | `total_paid_cents` chỉ tăng một lần |
| Hai worker cùng xử lý một `eventId` | Unique constraint bảo đảm một transaction áp dụng |
| Lỗi database sau khi tạo dấu nhưng trước commit | Transaction rollback cả dấu và side effect; retry có thể chạy lại |
| DB commit thành công nhưng ACK không gửi được | Retry được phát lại; marker chống tăng hai lần; sau đó ACK |
| Sự kiện thiếu field hoặc sai kiểu | Không ACK như thành công; có retry/DLQ policy |
| Message mới được đọc nhưng chưa ACK | Entry xuất hiện trong PEL |
| Worker cũ chết, entry idle vượt ngưỡng | Recovery claim lại; handler vẫn lũy đẳng |
| Cùng eventId được publish thành hai Stream ID | Chỉ một hiệu ứng nghiệp vụ nếu eventId ổn định |
| Redis trim payload khi entry còn pending | Phát hiện tình huống thiếu payload, xử lý theo retention/recovery policy |

### 14.1. Test ở mức PostgreSQL transaction

Giả sử bảng `invoice_totals` đã có hóa đơn `inv-test-1` với tổng tiền 0:

~~~java
@Test
void duplicateEventDoesNotDoubleApplyPayment() {
    projection.apply("evt-test-1", "inv-test-1", 125000);
    projection.apply("evt-test-1", "inv-test-1", 125000);

    Long paid = jdbc.queryForObject(
        """
        SELECT total_paid_cents
        FROM invoice_totals
        WHERE invoice_id = ?
        """,
        Long.class,
        "inv-test-1"
    );

    assertThat(paid).isEqualTo(125000L);
}
~~~

Đoạn test cần chạy cùng PostgreSQL test thật, schema và `PaymentProjectionService` đã cấu hình transaction. Không dùng mock `JdbcTemplate` nếu mục tiêu là chứng minh ràng buộc duy nhất và rollback.

Một test khác có thể cố ý tạo event cho hóa đơn không tồn tại, bắt exception, sau đó tạo hóa đơn và gọi lại **cùng eventId**. Nếu dấu đã rollback đúng, lần sau vẫn cập nhật được hóa đơn. Test này chứng minh không rơi vào lỗi “đánh dấu đã xử lý trước khi thực hiện nghiệp vụ”.

### 14.2. Test PEL trên Redis thật

Với một stream dành riêng cho test:

~~~redis
XADD test:payments * eventId evt-test-2 invoiceId inv-test-2 amountCents 20000
XGROUP CREATE test:payments test-group 0
XREADGROUP GROUP test-group test-worker COUNT 1 STREAMS test:payments >
XPENDING test:payments test-group
~~~

Sau `XREADGROUP`, số pending phải tăng nếu có entry vừa được giao và chưa ACK. Lấy **Stream ID thực tế** từ phản hồi `XREADGROUP` và thử:

~~~redis
XACK test:payments test-group <stream-id>
XPENDING test:payments test-group
~~~

Sau ACK thành công, entry tương ứng không còn trong PEL. Đây là bài test **hành vi Redis**, khác với bài test bảo đảm dữ liệu nghiệp vụ không bị cộng lặp.

Với JUnit/Spring Boot, có thể khởi động Redis bằng Testcontainers, tạo stream/group độc lập bằng UUID và thực hiện các bước tương tự thông qua `StringRedisTemplate.opsForStream()`. Không nên cố định một `Thread.sleep(...)` để chờ pending đổi trạng thái; đọc trạng thái thực tế và dùng timeout/polling khi cần chờ một hành vi bất đồng bộ.

### 14.3. Test lỗi đúng chỗ

Các tình huống crash trong sản xuất khó tái hiện bằng một unit test đơn giản. Trong integration test có kiểm soát, có thể dùng một điểm chặn giữa **DB commit** và **XACK**, cố ý không ACK, rồi cho recovery xử lý lại cùng eventId. Kết luận quan trọng là:

~~~text
Số lần handler nhận event      >= 2
Số lần tác động DB được commit  = 1
Pending sau recovery + ACK      = 0
~~~

Đây mới là bằng chứng rõ của **at-least-once delivery cùng idempotent effect**. Chỉ khẳng định callback được gọi đúng một lần sẽ bỏ qua chính trường hợp lỗi mà hệ thống cần chịu được.

## 15. Những lỗi triển khai phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Cộng tiền/trừ tồn kho hai lần | Message được redeliver sau khi side effect đã commit | Dedupe theo eventId với transaction/ràng buộc duy nhất |
| Message mất khỏi pending nhưng DB chưa đổi | `XACK` trước commit hoặc auto-ack | ACK sau khi commit; tắt auto-ack nếu dùng container |
| Chỉ xử lý message mới, pending cũ không bao giờ hết | Worker chỉ đọc `>`/`lastConsumed` | Xây dựng recovery cho PEL bằng pending read/`XAUTOCLAIM` |
| `SET NX processed` thành công rồi worker crash | Dấu chống trùng được ghi trước side effect ở kho khác | Đặt dấu và cập nhật nghiệp vụ trong cùng transaction |
| Retry cùng sự kiện vẫn bị xử lý hai lần | Producer cấp `eventId` mới khi publish lại | Định nghĩa eventId ổn định và hợp đồng retry |
| Hai instance đều cập nhật cùng event | Dedupe chỉ dùng `ConcurrentHashMap` trong JVM | Ràng buộc duy nhất/atomicity ở nơi lưu chung |
| Pending bị claim khi worker gốc còn chạy | Min-idle nhỏ hơn thời gian xử lý thực tế | Chỉnh ngưỡng theo processing latency; giữ handler lũy đẳng |
| Poison message retry mãi mãi | Không có giới hạn retry/DLQ | Phân loại lỗi và lưu DLQ trước khi ACK theo policy |
| ACK thành công nhưng entry vẫn còn khi `XRANGE` | `XACK` không xóa entry khỏi stream | Quản lý retention/trim riêng |
| Pending có ID nhưng không lấy được payload | Stream đã trim/xóa entry | Bảo vệ retention; giám sát pending và recovery |
| Event cũ ghi đè trạng thái của event mới | Xử lý song song không giữ thứ tự nghiệp vụ | Version/conditional update hoặc partitioning theo entity |
| Email được gửi hai lần dù DB marker đúng | Side effect nằm ngoài transaction DB | Transactional outbox và idempotency phía nhận |
| Consumer group mới không thấy lịch sử cũ | Group được tạo bằng `$` | Chọn start offset theo yêu cầu; `0` để đọc dữ liệu cũ |
| Worker dừng nhưng message không tự chuyển sang worker khác | Redis giữ ownership trong PEL | Recovery claim với idle threshold và policy rõ ràng |

## 16. Mẫu thiết kế vận hành

Một luồng xử lý đáng tin cậy có thể tổ chức thành hai worker:

~~~text
                          Producer
                             |
                             v
                      XADD eventId ổn định
                             |
                             v
                     Redis Stream + Group
                        /            \
                       /              \
             Worker đọc mới       Worker recovery
                 XREADGROUP >          XPENDING
                      |                XAUTOCLAIM
                      +-------+--------+
                              |
                              v
                        Validate payload
                              |
                              v
               PostgreSQL transaction:
                 - INSERT dedupe marker
                 - UPDATE business state
                 - INSERT outbox nếu cần
                              |
                     +--------+--------+
                     |                 |
                  COMMIT             ROLLBACK
                     |                 |
                     v                 v
                    XACK         Giữ pending/retry
                     |              hoặc DLQ
                     v
               Hoàn tất cho group
~~~

Với kiến trúc này cần thống nhất các quy tắc:

1. **Producer** tạo `eventId` một lần cho sự kiện logic và giữ nguyên khi retry.
2. **Consumer** coi mọi lần giao message là có thể trùng, kể cả lần giao đầu tiên mà nó nhìn thấy.
3. **Database transaction** bảo vệ marker chống trùng và thay đổi nghiệp vụ.
4. **XACK** chỉ xảy ra khi handler đã hoàn tất thành công hoặc xác nhận event thực sự đã xử lý trước đó.
5. **Recovery worker** xử lý pending quá hạn, có backoff và giới hạn số lượt retry.
6. **Poison message** được lưu vào DLQ hoặc nguồn điều tra trước khi bỏ khỏi luồng retry.
7. **Retention và idempotency window** phải đủ dài cho downtime, replay và nghĩa vụ nghiệp vụ.
8. **Ordering/versioning** được thiết kế riêng nếu nhiều sự kiện cùng ảnh hưởng một entity.
9. **Side effect ngoài DB** dùng outbox/idempotency phía đích theo yêu cầu bảo đảm.
10. **Metrics** cho pending, duplicate, ACK failure, DLQ và processing time được theo dõi thường xuyên.

Redis Streams cung cấp nền tảng để **giao lại message chưa ACK**, còn tính đúng đắn khi message xuất hiện nhiều lần là trách nhiệm thiết kế của ứng dụng. Khi kết hợp consumer group, PEL recovery, ACK sau commit và ràng buộc idempotency trong transaction nghiệp vụ, hệ thống có thể xử lý lặp một cách an toàn hơn mà không giả định rằng callback chỉ chạy đúng một lần.
