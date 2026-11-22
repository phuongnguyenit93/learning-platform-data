# Exactly-once processing và idempotent side effect

Trong một hệ thống Spring Kafka, một message có thể được xử lý lại dù ứng dụng chỉ nhận được một lần gửi từ phía producer. Consumer có thể hoàn thành công việc rồi dừng trước khi offset được commit; khi khởi động lại hoặc sau rebalance, Kafka giao lại message đó. Producer cũng có thể gửi lại sau timeout vì không biết broker đã ghi nhận request trước đó hay chưa.

Vì vậy, cần phân biệt hai mục tiêu:

- **Exactly-once processing trong Kafka** bảo đảm kết quả ghi vào Kafka và offset đầu vào được commit như một đơn vị nguyên tử trong luồng consume-transform-produce.
- **Idempotent side effect** bảo đảm một tác động nghiệp vụ bên ngoài Kafka chỉ xảy ra một lần về mặt kết quả, dù cùng một event được giao hoặc xử lý nhiều lần.

Hai cơ chế bổ trợ cho nhau. Kafka transaction giải quyết ranh giới dữ liệu nằm trong Kafka; idempotency giải quyết các ranh giới như database, HTTP API, thanh toán, email hoặc hệ thống bên ngoài.

## 1. Vì sao một message có thể được xử lý nhiều lần?

Kafka consumer thường hoạt động theo cơ chế at-least-once khi ứng dụng commit offset sau khi xử lý. Cơ chế này ưu tiên không làm mất message, nhưng có thể tạo ra lần xử lý lặp lại.

Ví dụ, listener đọc message ở offset 42, cập nhật database thành công, rồi tiến trình bị dừng trước khi offset 43 được commit. Khi partition được giao lại, consumer đọc lại offset 42. Database đã được cập nhật, nhưng Kafka không biết điều đó vì offset chưa được commit.

| Thời điểm xảy ra lỗi | Điều consumer có thể quan sát | Rủi ro |
|---|---|---|
| Trước khi bắt đầu xử lý | Message chưa có tác động | Message được đọc lại; thường an toàn |
| Trong lúc gọi database hoặc HTTP API | Không rõ tác động đã hoàn tất hay chưa | Retry có thể lặp side effect |
| Sau khi database commit, trước khi offset commit | Database đã thay đổi, Kafka vẫn xem message chưa xử lý | Side effect có thể chạy lần hai |
| Sau khi publish output nhưng trước khi commit offset | Output có thể đã tồn tại, input vẫn được đọc lại | Có thể tạo output trùng |
| Producer timeout sau khi broker đã ghi message | Producer không chắc request trước đã thành công | Retry có thể tạo bản ghi trùng nếu producer không idempotent |

Không thể suy ra rằng listener chỉ chạy một lần từ việc ứng dụng sử dụng Kafka. Một thiết kế tin cậy phải xác định rõ ranh giới transaction và cách xử lý khi kết quả của một lời gọi trở nên không chắc chắn.

## 2. Exactly-once semantics của Kafka bảo vệ điều gì?

Kafka cung cấp hai cơ chế liên quan:

1. **Idempotent producer** dùng sequence number theo producer và partition để broker nhận biết bản ghi được gửi lại do retry. Nó ngăn bản sao phát sinh từ retry của cùng producer session trong phạm vi Kafka quản lý.
2. **Kafka transaction** gom nhiều lần ghi vào Kafka và offset consumer thành một transaction. Với luồng consume-transform-produce, output và offset input có thể cùng commit hoặc cùng abort.

Khi transaction commit, consumer dùng cấu hình **isolation.level=read_committed** chỉ đọc các bản ghi thuộc transaction đã commit. Bản ghi thuộc transaction bị abort sẽ không được trả về cho consumer ở chế độ này.

Điều đó không có nghĩa callback listener chỉ được gọi đúng một lần. Listener có thể chạy lại sau khi transaction abort hoặc khi ứng dụng phục hồi. Cam kết exactly-once nằm ở kết quả đã commit trong Kafka: một output của transaction không trở thành dữ liệu đã commit hai lần chỉ vì lần thực thi trước bị retry.

### 2.1 Cấu hình producer và consumer

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      transaction-id-prefix: ${INSTANCE_ID:local}-orders-
      properties:
        enable.idempotence: true
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

**transaction-id-prefix** yêu cầu Spring Kafka tạo producer có hỗ trợ transaction. Giá trị prefix phải khác nhau giữa các instance đang chạy đồng thời; nếu nhiều instance dùng cùng transactional ID, broker có thể fence producer cũ. Trong môi trường triển khai, hãy đặt INSTANCE_ID bằng định danh ổn định và duy nhất cho từng instance.

**enable.idempotence** bảo vệ retry ở producer. **acks: all** yêu cầu xác nhận theo cấu hình replication của Kafka. **isolation.level: read_committed** có ý nghĩa với consumer cần chỉ nhìn thấy dữ liệu transaction đã commit. Khi bật transaction cho listener, Spring Kafka quản lý việc commit offset theo transaction; không tự commit offset trước khi xử lý hoàn tất.

Chỉ đặt transaction-id-prefix chưa đủ để chứng minh listener container đang chạy trong transaction. Cần cấu hình **KafkaTransactionManager** cho listener container factory (hoặc xác nhận auto-configuration của phiên bản Spring Boot đang dùng đã nối manager vào đúng container). **KafkaTemplate** phải dùng producer factory tương ứng để các lệnh gửi trong listener tham gia transaction của container.

### 2.2 Consume-transform-produce trong một transaction

Giả sử service đọc OrderCreated từ topic orders, sau đó phát InvoiceRequested sang topic billing-events:

~~~java
@Component
public class BillingListener {
    private final KafkaTemplate<String, InvoiceRequested> kafkaTemplate;

    public BillingListener(
            KafkaTemplate<String, InvoiceRequested> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(topics = "orders", groupId = "billing")
    public void onOrder(OrderCreated event) {
        InvoiceRequested output = new InvoiceRequested(
                event.eventId(),
                event.orderId()
        );

        kafkaTemplate.send(
                "billing-events",
                event.orderId(),
                output
        );
    }
}
~~~

Đoạn listener trên chỉ có semantics consume-transform-produce exactly-once khi listener container được cấu hình với KafkaTransactionManager và KafkaTemplate tham gia cùng transaction. Khi listener trả về thành công, container đưa offset đã xử lý vào transaction rồi commit. Nếu xử lý thất bại, transaction abort; output không được công bố như dữ liệu đã commit và offset không tiến lên, nên message có thể được đọc lại.

Nếu listener gửi output bằng một producer không tham gia transaction của container, hoặc commit offset theo một đường riêng, hai thao tác không còn nguyên tử. Khi đó vẫn có cửa sổ tạo output trùng hoặc mất liên kết giữa input và output.

### 2.3 Transaction cho nhiều lần gửi Kafka độc lập

Khi cần ghi nhiều record Kafka như một nhóm nguyên tử bên ngoài listener container, có thể dùng **KafkaTemplate.executeInTransaction**:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("order-events", orderId, orderEvent);
    operations.send("audit-events", orderId, auditEvent);
    return null;
});
~~~

Hai lần gửi trên cùng commit hoặc abort. Transaction này gom các lần gửi của callback; nó không tự đưa offset của một consumer vào transaction. Với listener consume-transform-produce, hãy dùng transaction do listener container quản lý và gửi qua template tham gia transaction đó.

## 3. Kafka transaction không bao phủ side effect bên ngoài

Kafka transaction không tự tạo một transaction phân tán bao trùm Kafka, relational database và HTTP service. Ví dụ sau vẫn có lỗi:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) {
    paymentClient.charge(event.orderId(), event.amount());
    kafkaTemplate.send("payment-events", event.orderId(),
            new PaymentCompleted(event.orderId()));
}
~~~

Nếu lời gọi thanh toán thành công nhưng Kafka transaction abort, message sẽ được đọc lại và lệnh charge có thể chạy lần nữa. Nếu Kafka commit nhưng HTTP service chưa thực hiện side effect, hai hệ thống lại lệch trạng thái. Kafka không thể tự quyết định kết quả của một giao dịch HTTP.

Hãy xác định ranh giới bảo đảm theo loại side effect:

| Đích ghi | Cơ chế phù hợp | Phạm vi bảo đảm |
|---|---|---|
| Một hoặc nhiều topic Kafka | Producer idempotence và Kafka transaction | Record và offset Kafka có thể commit nguyên tử |
| Database quan hệ | Inbox/deduplication trong cùng DB transaction với thay đổi nghiệp vụ | Một event chỉ tạo hiệu ứng DB một lần trong phạm vi khóa duy nhất |
| HTTP API hỗ trợ idempotency key | Gửi khóa ổn định cho mỗi thao tác nghiệp vụ | Phụ thuộc hợp đồng idempotency của API đích |
| HTTP API không hỗ trợ idempotency | Outbox, state machine, retry có kiểm soát và đối soát | Giảm rủi ro; không thể bảo đảm exactly-once chỉ bằng Kafka |
| Gửi email hoặc webhook | Nhà cung cấp hỗ trợ idempotency, hoặc lưu trạng thái gửi và đối soát | Phụ thuộc khả năng chống trùng của hệ thống nhận |

## 4. Thiết kế idempotent side effect

Một thao tác là idempotent nếu thực hiện lại cùng một yêu cầu không làm thay đổi kết quả cuối cùng:

~~~text
apply(apply(state, event), event) = apply(state, event)
~~~

Ví dụ, đặt trạng thái đơn hàng thành PAID có thể idempotent nếu cập nhật theo orderId và trạng thái đích. Tăng số dư thêm 100 mỗi lần nhận event thì không idempotent: nhận lại event sẽ cộng tiền lần nữa.

### 4.1 Dùng event ID ổn định

Producer nên gán eventId duy nhất cho một sự kiện nghiệp vụ và giữ nguyên ID đó qua mọi lần retry hoặc replay. Không tạo UUID mới mỗi lần listener xử lý lại, vì consumer sẽ xem mỗi lần là một event khác nhau.

Idempotency key cần nhận diện đúng thao tác. Có thể dùng eventId, hoặc một khóa nghiệp vụ như orderId + operation nếu nhiều event khác nhau cùng biểu diễn một thao tác. Nếu cùng một key xuất hiện với payload khác nhau, nên phát hiện và ghi nhận đó là dữ liệu bất thường thay vì âm thầm bỏ qua.

### 4.2 Inbox table và database transaction

Với side effect trong database, lưu dấu event đã xử lý bằng một unique key. Việc ghi dấu và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng một database transaction.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name text NOT NULL,
    event_id uuid NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Listener có thể gọi service sau. Lệnh INSERT ... ON CONFLICT DO NOTHING trả về số dòng được thêm; nếu bằng 0 thì event đã được consumer này ghi nhận trước đó:

~~~java
@Service
public class OrderProjectionService {
    private final JdbcTemplate jdbc;
    private final InvoiceRepository invoices;

    public OrderProjectionService(
            JdbcTemplate jdbc,
            InvoiceRepository invoices) {
        this.jdbc = jdbc;
        this.invoices = invoices;
    }

    @Transactional
    public void handle(OrderCreated event) {
        int inserted = jdbc.update("""
            INSERT INTO consumer_inbox (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "billing",
            event.eventId()
        );

        if (inserted == 0) {
            return; // Event đã được xử lý thành công trước đó.
        }

        invoices.insertIfAbsent(
                event.orderId(),
                event.eventId()
        );
    }
}
~~~

insertIfAbsent đại diện cho thao tác ghi hóa đơn có unique constraint phù hợp, chẳng hạn unique theo order_id nếu mỗi đơn chỉ có một hóa đơn. Unique constraint ở database là lớp bảo vệ cuối cùng trước xử lý đồng thời; kiểm tra bằng một câu SELECT rồi mới INSERT không đủ an toàn khi hai consumer cùng chạy.

Trình tự này có các tính chất quan trọng:

1. Lần đầu, inbox row được thêm và thay đổi nghiệp vụ được ghi trong cùng transaction.
2. Nếu cập nhật nghiệp vụ thất bại, transaction rollback cả inbox row. Khi Kafka giao lại event, consumer vẫn có thể thử lại.
3. Nếu database commit thành công nhưng ứng dụng dừng trước khi Kafka commit offset, event được giao lại. Lần sau inbox insert xung đột, service bỏ qua side effect đã hoàn thành.
4. Nếu hai lần xử lý chạy đồng thời, unique constraint phân xử; chỉ transaction thêm được inbox row mới tiếp tục thao tác nghiệp vụ.

@Transactional trong ví dụ là transaction của database. Khi listener gọi service và service commit xong, listener mới trả về để container commit offset. Vẫn có cửa sổ database commit xong nhưng offset chưa commit; inbox chính là cơ chế làm cửa sổ đó an toàn khi retry.

Không đánh dấu event đã xử lý trước khi side effect thành công. Nếu lưu inbox row ở một transaction riêng rồi gọi database hoặc HTTP ở ngoài transaction đó, lỗi giữa hai bước có thể khiến lần retry bị bỏ qua dù side effect chưa từng xảy ra.

### 4.3 Idempotency key cho HTTP API

Nếu API đích hỗ trợ idempotency key, gửi cùng một key cho mọi lần thử của cùng thao tác:

~~~http
POST /payments
Idempotency-Key: order-payment:evt-8d7f...
Content-Type: application/json

{
  "orderId": "ORD-1042",
  "amount": 125000
}
~~~

Nhà cung cấp phải lưu kết quả gắn với key và trả lại kết quả tương ứng khi nhận request lặp. Chỉ thêm header Idempotency-Key không tự tạo bảo đảm nếu API đích không thực thi hợp đồng này. Cần xác minh thời gian lưu key, phạm vi duy nhất, cách xử lý cùng key nhưng payload khác, và phản hồi khi request đầu tiên đang chạy.

Nếu API không hỗ trợ idempotency, timeout tạo ra trạng thái không chắc chắn: request có thể đã được thực hiện dù client không nhận được response. Không thể giải quyết an toàn bằng cách gửi lại vô hạn. Hãy lưu trạng thái thao tác, dùng mã tham chiếu nghiệp vụ, truy vấn trạng thái từ hệ thống đích khi có thể, và đưa trường hợp không xác định vào quy trình đối soát.

## 5. Outbox và inbox trong luồng liên hệ database với Kafka

### 5.1 Transactional outbox khi ứng dụng ghi database rồi phát event

Một lỗi phổ biến là cập nhật database rồi gọi kafkaTemplate.send() trong cùng một method và kỳ vọng @Transactional làm cả hai nguyên tử. Nếu transaction manager đang quản lý database, lời gọi Kafka không tự trở thành một phần của transaction database.

Transactional outbox giải quyết việc này bằng cách ghi thay đổi nghiệp vụ và một bản ghi outbox trong cùng database transaction:

~~~text
Database transaction:
  UPDATE orders ...
  INSERT INTO outbox(event_id, topic, message_key, payload, status)
  COMMIT

Outbox relay:
  đọc các outbox row chưa gửi
  publish event lên Kafka
  đánh dấu đã gửi sau khi broker xác nhận
~~~

Nếu ứng dụng dừng trước commit, cả thay đổi nghiệp vụ và outbox row đều rollback. Nếu commit thành công nhưng relay chưa publish, row vẫn còn để relay tiếp tục sau khi khởi động lại. Relay có thể publish lặp nếu dừng sau khi broker nhận event nhưng trước khi đánh dấu row đã gửi; consumer vẫn cần inbox hoặc idempotency key.

Outbox biến việc phát event thành một công việc có thể retry và đối soát. Nó không làm lần publish qua mạng trở thành exactly-once; nó bảo đảm event không bị tách khỏi transaction ghi nghiệp vụ và chấp nhận relay at-least-once.

### 5.2 Inbox khi consumer ghi database

Inbox là phía nhận: nó ghi nhận event ID đã được áp dụng cùng transaction với thay đổi nghiệp vụ. Kết hợp outbox và inbox tạo luồng tin cậy:

~~~text
Service A                         Kafka                         Service B
---------                         -----                         ---------
DB: business row + outbox
          |
          v
      Outbox relay  ---------->  event  ---------------------> Inbox insert
                                                               + DB update
                                                               one DB commit
~~~

Thiết kế này vẫn cho phép retry ở relay và consumer, nhưng mỗi lần retry có một khóa ổn định để phát hiện thao tác đã hoàn tất.

## 6. Retry, dead-letter topic và replay

Retry là một phần bình thường của xử lý tin cậy. Idempotency key phải được giữ nguyên khi retry trong listener, retry sau rebalance, chuyển qua dead-letter topic (DLT), hoặc replay thủ công.

Một số quy tắc thực tế:

- Chỉ ghi nhận event hoàn tất trong cùng transaction với side effect cần bảo vệ.
- Để exception đi ra khỏi listener khi xử lý chưa thành công, nhằm cho container áp dụng retry hoặc error handler. Không bắt exception rồi trả về thành công nếu side effect chưa hoàn tất.
- Phân biệt lỗi tạm thời (timeout, lỗi mạng, database unavailable) với lỗi dữ liệu không thể tự phục hồi (schema sai, thiếu trường bắt buộc). Đặt giới hạn retry và chuyển lỗi cần can thiệp sang DLT.
- Khi replay từ DLT, giữ event ID gốc. Nếu nghiệp vụ cần chạy lại một thao tác đã hoàn tất, tạo một command/event mới với danh tính nghiệp vụ mới và quy tắc rõ ràng.
- Đặt retention của inbox lâu hơn khoảng thời gian tối đa có thể replay event. Nếu xóa dấu inbox quá sớm, một bản replay cũ có thể tạo side effect lần nữa.
- Theo dõi event ID và business key trong log/trace để tra cứu xuyên suốt producer, Kafka, consumer và hệ thống đích.

Với HTTP timeout, đừng đánh dấu inbox hoàn tất chỉ vì request đã được gửi. Chỉ đánh dấu sau khi có kết quả xác nhận hoặc sau khi quy trình đối soát đã xác định trạng thái cuối cùng. Nếu không thể xác định, lưu trạng thái UNKNOWN/PENDING_RECONCILIATION để xử lý có kiểm soát.

## 7. Kiểm thử các cửa sổ lỗi

Một bài kiểm thử chỉ gửi message thành công không chứng minh được exactly-once hoặc idempotency. Hãy chủ động mô phỏng các điểm dừng có thể xảy ra:

| Kịch bản | Điều cần kiểm chứng |
|---|---|
| Producer gửi lại sau timeout | Idempotent producer không tạo bản sao do retry trong cùng producer session |
| Listener gửi output rồi ném exception trước commit | Transaction abort; consumer read_committed không nhìn thấy output đã abort |
| Listener hoàn tất transaction | Output và offset input cùng commit |
| Database commit xong, tiến trình dừng trước offset commit | Kafka giao lại event nhưng inbox ngăn side effect DB lặp |
| Hai consumer xử lý cùng event đồng thời | Unique constraint chỉ cho một transaction nhận quyền xử lý |
| HTTP API thực hiện thành công nhưng client timeout | Retry với cùng idempotency key trả về cùng kết quả hoặc quy trình đối soát phát hiện trạng thái |
| Replay event từ DLT | Event ID cũ được nhận diện; side effect đã hoàn tất không chạy lần nữa |
| Relay publish xong rồi dừng trước khi cập nhật outbox | Event có thể được gửi lại nhưng consumer xử lý idempotent |

Ngoài kết quả cuối cùng, theo dõi số event bị bỏ qua do trùng, số lần retry, DLT count, transaction abort, consumer lag, tuổi của outbox row và số thao tác đang chờ đối soát. Các chỉ số này giúp phân biệt retry bình thường với lỗi kéo dài hoặc dữ liệu bị kẹt.

## 8. Cách chọn cơ chế theo luồng dữ liệu

| Luồng | Thiết kế nên dùng |
|---|---|
| Kafka → Kafka | Listener container transaction + KafkaTransactionManager + KafkaTemplate cùng producer factory; consumer downstream dùng read_committed |
| Kafka → database | Inbox với unique key và cập nhật nghiệp vụ trong một DB transaction; chỉ commit offset sau khi service thành công |
| Kafka → HTTP/payment | Idempotency key được API đích hỗ trợ; nếu không có, lưu trạng thái và dùng retry có kiểm soát cùng đối soát |
| Database → Kafka | Transactional outbox; relay có thể retry, consumer nhận dùng inbox/idempotency |
| Kafka → email/webhook | Ưu tiên API đích có idempotency; lưu trạng thái gửi và xử lý kết quả không xác định |

Khi thiết kế một listener Spring Kafka, hãy trả lời ba câu hỏi trước khi triển khai: transaction nào đang quản lý offset, transaction nào đang quản lý side effect, và khóa nào nhận diện cùng một thao tác qua mọi lần retry? Nếu hai thao tác nằm ở hai hệ thống không chia sẻ transaction, hãy thiết kế idempotency hoặc outbox/inbox cho ranh giới đó. Đây là cách biến at-least-once delivery thành kết quả nghiệp vụ an toàn trước retry, crash và replay.
