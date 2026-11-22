# Cửa sổ lỗi giữa đọc, xử lý và commit offset

Khi một Kafka consumer đọc record, thực hiện nghiệp vụ rồi commit offset, ba thao tác này không mặc nhiên nằm trong cùng một transaction. Ứng dụng có thể dừng ở bất kỳ thời điểm nào giữa chúng. Vị trí xảy ra lỗi quyết định record sẽ được đọc lại, bị bỏ qua hay tạo tác dụng phụ trùng lặp.

Đây là **cửa sổ lỗi giữa đọc, xử lý và commit offset**. Muốn thiết kế consumer đáng tin cậy, cần hiểu rõ position khác committed offset, xác định thứ tự giữa side effect và commit, rồi chọn cơ chế phù hợp: at-most-once, at-least-once, idempotent processing hoặc Kafka transaction.

## 1. Ba bước trong vòng đời xử lý một record

Một consumer thường thực hiện ba bước logic:

1. **Đọc:** gọi poll để nhận record từ partition. Position của consumer tiến lên sau các record đã được poll.
2. **Xử lý:** thực hiện nghiệp vụ, ví dụ cập nhật database, gọi API hoặc tạo sự kiện đầu ra.
3. **Commit:** lưu offset tiếp theo cần đọc cho consumer group để khôi phục sau restart hoặc rebalance.

Committed offset là checkpoint bền vững của group. Nếu record có offset N đã xử lý xong và muốn lần sau bắt đầu từ record kế tiếp, consumer commit N+1.

~~~mermaid
flowchart LR
    A["poll() đọc record N"] --> B["Position tiến đến N+1"]
    B --> C["Xử lý nghiệp vụ"]
    C --> D["Commit offset N+1"]
    D --> E["Group checkpoint"]
~~~

Vấn đề là bước xử lý nghiệp vụ và bước commit offset thường thuộc hai hệ thống khác nhau. Kafka quản lý offset; database hoặc API bên ngoài quản lý side effect. Nếu ứng dụng crash giữa hai bước, Kafka không thể tự biết side effect bên ngoài đã hoàn tất hay chưa.

## 2. Position không phải committed offset

Sau khi poll trả record, position có thể đã tiến đến offset tiếp theo ngay cả khi ứng dụng chưa xử lý xong record. Committed offset chỉ thay đổi khi commit thành công.

Ví dụ partition có record offset 40, 41 và 42:

| Thời điểm | Position | Committed offset | Trạng thái |
|---|---:|---:|---|
| Trước poll | 40 | 40 | Sẵn sàng đọc record 40 |
| Poll trả record 40–42 | 43 | 40 | Đã lấy record nhưng chưa commit |
| Xử lý record 40–42 xong | 43 | 40 | Nghiệp vụ hoàn tất, checkpoint chưa cập nhật |
| Commit thành công | 43 | 43 | Lần chạy sau tiếp tục từ 43 |

Nếu consumer dừng ở dòng thứ ba, group vẫn khôi phục từ committed offset 40 và có thể đọc lại cả ba record. Đây là cơ chế giúp tránh bỏ qua dữ liệu khi chưa commit, nhưng cũng có thể khiến nghiệp vụ được thực hiện lại.

## 3. Các cửa sổ lỗi quan trọng

Giả sử consumer xử lý record offset 40 và cập nhật số dư trong database.

| Điểm crash | Offset đã commit? | Side effect đã xảy ra? | Kết quả khi chạy lại |
|---|---|---|---|
| Trước khi xử lý | Chưa | Chưa | Đọc lại record 40 và xử lý bình thường |
| Trong khi xử lý, transaction DB rollback | Chưa | Chưa được commit ở DB | Đọc lại và thử xử lý |
| Sau khi DB commit, trước khi commit Kafka offset | Chưa | Có | Đọc lại record 40; có nguy cơ áp dụng side effect lần hai |
| Sau khi Kafka offset commit, trước khi xử lý xong | Có | Chưa hoặc mới một phần | Consumer tiếp tục từ 41; phần nghiệp vụ còn thiếu có thể bị mất |
| Sau khi DB và Kafka offset đều commit | Có | Có | Tiếp tục từ 41 |

Hai tình huống cần đặc biệt chú ý:

- **Commit trước, xử lý sau:** nếu ứng dụng crash sau commit nhưng trước side effect, record bị bỏ qua khi khởi động lại. Đây là nguy cơ mất xử lý.
- **Xử lý trước, commit sau:** nếu side effect thành công nhưng ứng dụng crash trước commit, record được đọc lại. Đây là nguy cơ xử lý trùng.

Không có thứ tự đơn giản nào vừa bảo đảm không mất xử lý vừa tự loại bỏ duplicate khi side effect và offset thuộc hai hệ thống không có transaction chung.

## 4. At-most-once và at-least-once

Thời điểm commit quyết định ngữ nghĩa giao nhận ở phía consumer:

| Semantics | Thứ tự chính | Rủi ro khi crash |
|---|---|---|
| At-most-once | Commit offset trước khi xử lý | Có thể bỏ qua record nếu crash sau commit |
| At-least-once | Xử lý xong rồi commit offset | Có thể xử lý lại record nếu crash trước commit |

### At-most-once

Consumer lưu checkpoint trước khi thực hiện nghiệp vụ. Nếu tiến trình dừng sau commit, Kafka sẽ không giao lại record đó cho group dù nghiệp vụ có thể chưa chạy.

Cách này phù hợp khi bỏ sót một số cập nhật ít quan trọng được chấp nhận và việc xử lý trùng gây tác hại lớn hơn. Không dùng cho luồng thanh toán, đơn hàng hoặc dữ liệu cần bảo đảm xử lý.

### At-least-once

Consumer xử lý thành công rồi mới commit. Nếu crash sau khi side effect đã commit nhưng trước khi Kafka offset được lưu, record sẽ được đọc lại. Do đó, consumer phải chịu được việc nhận cùng event nhiều lần.

Đây là lựa chọn phổ biến khi cần tránh mất xử lý. Kết hợp với idempotent consumer, at-least-once có thể tạo hiệu quả nghiệp vụ một lần dù record được giao lại.

## 5. Idempotent consumer giảm tác hại của replay

Một thao tác idempotent có thể được thực hiện nhiều lần mà trạng thái cuối vẫn giống như thực hiện một lần. Ví dụ:

- Đặt trạng thái đơn hàng thành PAID theo order ID là thao tác có thể thiết kế idempotent.
- Cộng thêm 100.000 đồng vào số dư mỗi lần nhận event không idempotent nếu không có khóa chống trùng.
- Ghi một bản ghi có event ID duy nhất và bỏ qua event đã xử lý là cách tạo idempotency ở tầng ứng dụng.

Mỗi sự kiện nên có định danh ổn định, chẳng hạn eventId. Consumer lưu event ID đã xử lý cùng với thay đổi nghiệp vụ. Khi nhận lại event đó, ứng dụng nhận ra bản ghi trùng và không áp dụng side effect lần nữa.

### Inbox pattern với database

Inbox pattern lưu dấu sự kiện đã xử lý trong cùng database transaction với thay đổi nghiệp vụ:

1. Bắt đầu transaction database.
2. Ghi eventId vào bảng inbox có unique constraint.
3. Nếu event ID đã tồn tại, không thực hiện side effect lần nữa.
4. Nếu là event mới, áp dụng thay đổi nghiệp vụ.
5. Commit transaction database.
6. Sau khi transaction thành công, commit Kafka offset.

Ví dụ schema:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);

CREATE TABLE account_balance (
    account_id VARCHAR(100) PRIMARY KEY,
    balance DECIMAL(19, 2) NOT NULL
);
~~~

Với PostgreSQL, có thể dùng INSERT ... ON CONFLICT DO NOTHING để giành quyền xử lý event ID:

~~~sql
INSERT INTO processed_events (event_id, processed_at)
VALUES (:eventId, CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;
~~~

Nếu số dòng được thêm là 1, transaction này là lần đầu xử lý event và có thể cập nhật nghiệp vụ. Nếu số dòng là 0, event đã được xử lý trước đó và consumer có thể kết thúc transaction mà không lặp side effect.

Điều quan trọng là thao tác insert inbox và cập nhật nghiệp vụ phải nằm trong **cùng một transaction database**. Nếu ghi inbox trước rồi commit riêng, sau đó mới cập nhật số dư, crash giữa hai thao tác có thể khiến event bị đánh dấu đã xử lý nhưng nghiệp vụ chưa xảy ra.

### Ví dụ service Spring

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentEventHandler {

    private final ProcessedEventRepository processedEvents;
    private final AccountRepository accounts;

    public PaymentEventHandler(
        ProcessedEventRepository processedEvents,
        AccountRepository accounts
    ) {
        this.processedEvents = processedEvents;
        this.accounts = accounts;
    }

    @Transactional
    public void handle(PaymentReceived event) {
        boolean firstDelivery =
            processedEvents.insertIfAbsent(event.eventId());

        if (!firstDelivery) {
            return;
        }

        accounts.addPayment(
            event.accountId(),
            event.amount()
        );
    }
}
~~~

insertIfAbsent cần được triển khai bằng câu lệnh atomic có unique constraint, ví dụ PostgreSQL ON CONFLICT DO NOTHING, và trả về số dòng được thêm. Không triển khai bằng cặp existsById() rồi save() nếu có thể có nhiều consumer hoặc nhiều luồng đồng thời, vì hai lần kiểm tra có thể cùng thấy chưa tồn tại.

Nếu cập nhật nghiệp vụ thất bại, transaction phải rollback cả inbox marker lẫn thay đổi nghiệp vụ. Khi Kafka giao lại record, consumer có thể thử lại từ đầu.

Listener Spring Kafka nên gọi service transactional qua bean proxy và để exception xử lý nghiệp vụ truyền ra listener container:

~~~java
@KafkaListener(
    topics = "payments.received",
    groupId = "accounting-service"
)
public void onPayment(PaymentReceived event) {
    paymentEventHandler.handle(event);
}
~~~

Khi lời gọi service trả về, transaction database đã commit thành công. Container sau đó mới thực hiện commit offset theo AckMode. Nếu service ném exception, không nên bắt rồi bỏ qua như thể xử lý thành công; hãy để error handler/retry policy quyết định việc retry, recover hoặc đưa record vào DLT. Nếu listener nuốt exception rồi return bình thường, container có thể xem lần xử lý là thành công và commit offset dù database transaction đã rollback.

## 6. Commit Kafka offset sau transaction database

Khi database và Kafka không dùng chung transaction, trình tự phổ biến với inbox pattern là:

~~~mermaid
sequenceDiagram
    participant C as Kafka Consumer
    participant DB as Database
    participant K as Kafka Group Coordinator
    C->>DB: Begin transaction
    C->>DB: Insert eventId vào inbox
    C->>DB: Cập nhật nghiệp vụ nếu event mới
    C->>DB: Commit DB transaction
    DB-->>C: Thành công
    C->>K: Commit offset N+1
    K-->>C: Commit thành công
~~~

Nếu ứng dụng crash sau DB commit nhưng trước Kafka offset commit, Kafka giao lại event. Inbox nhận diện event ID đã tồn tại, bỏ qua side effect trùng, sau đó consumer commit offset.

Nếu DB transaction rollback, inbox marker cũng rollback. Kafka offset chưa commit nên record được giao lại để thử lại.

Nếu commit offset thất bại hoặc kết quả commit không rõ do mất response, ứng dụng phải chấp nhận khả năng record được giao lại. Inbox pattern bảo vệ side effect database trong trường hợp này.

## 7. Vì sao Kafka transaction không tự bao gồm database?

Kafka transaction có thể phối hợp việc ghi record đầu ra và commit offset đầu vào trong cùng Kafka transaction. Nhưng transaction đó chỉ quản lý tài nguyên Kafka. Nó không tự rollback một lệnh SQL đã commit hoặc một HTTP request đã gửi đến dịch vụ khác.

Ví dụ consumer đọc orders, cập nhật database và commit offset Kafka:

1. Database commit thành công.
2. Kafka transaction bị abort hoặc offset không được commit.
3. Consumer đọc lại event.
4. Database có thể nhận cùng side effect lần thứ hai nếu không có idempotency.

Để bảo đảm hiệu quả một lần ở database, vẫn cần inbox/deduplication hoặc cơ chế transaction phối hợp phù hợp với database. Không gọi hệ thống bên ngoài như thể chúng là một phần của Kafka transaction.

## 8. Exactly-once semantics trong luồng Kafka-to-Kafka

Kafka hỗ trợ transaction để xử lý một chuỗi consume-process-produce trong phạm vi Kafka:

1. Consumer đọc record từ topic đầu vào.
2. Producer transactional ghi các record đầu ra.
3. Producer gửi offset đã xử lý của consumer group vào cùng transaction bằng sendOffsetsToTransaction.
4. Nếu transaction commit, output record và input offsets cùng được commit.
5. Nếu transaction abort, output không được hiển thị cho consumer dùng read_committed, và input offset không tiến lên.

~~~mermaid
flowchart TD
    A["Consumer đọc input record"] --> B["Xử lý"]
    B --> C["Producer ghi output trong transaction"]
    C --> D["Gửi input offsets vào transaction"]
    D --> E{"Commit transaction?"}
    E -->|"Commit"| F["Output visible<br/>Input offset committed"]
    E -->|"Abort"| G["Output không visible với read_committed<br/>Input offset chưa tiến"]
~~~

Ví dụ khung Java:

~~~java
producer.initTransactions();

while (running) {
    ConsumerRecords<String, InputEvent> records =
        consumer.poll(Duration.ofMillis(500));

    if (records.isEmpty()) {
        continue;
    }

    producer.beginTransaction();
    try {
        for (ConsumerRecord<String, InputEvent> record : records) {
            OutputEvent output = transform(record.value());
            producer.send(
                new ProducerRecord<>(
                    "derived.events",
                    record.key(),
                    output
                )
            );
        }

        producer.sendOffsetsToTransaction(
            offsetsAfter(records),
            consumer.groupMetadata()
        );
        producer.commitTransaction();
    } catch (Exception exception) {
        producer.abortTransaction();
        throw exception;
    }
}
~~~

Đây là khung minh họa; offsetsAfter phải tính offset tiếp theo N+1 cho từng partition đã xử lý liên tục. Producer cần transactional.id ổn định và duy nhất giữa các producer đang chạy đồng thời; consumer tắt auto commit. Consumer đọc output cần đặt isolation.level=read_committed để không nhìn thấy record thuộc transaction đã abort.

Ví dụ cấu hình khái quát:

~~~properties
# Producer
transactional.id=orders-transformer-0
enable.idempotence=true
acks=all

# Consumer
enable.auto.commit=false
isolation.level=read_committed
~~~

Khi transaction commit, Kafka ghi output và offset input như một đơn vị nguyên tử trong Kafka. Khi abort, consumer sẽ đọc lại input sau khi offset cũ được khôi phục và có thể thử lại phép biến đổi.

## 9. Exactly-once có phạm vi rõ ràng

“Exactly-once” không phải lời hứa rằng mọi dòng code, API hoặc side effect trên toàn hệ thống chỉ chạy đúng một lần. Cần nêu rõ phạm vi bảo đảm:

| Phạm vi | Cơ chế | Điều được bảo đảm |
|---|---|---|
| Producer gửi lại batch do retry | Idempotent producer | Broker tránh append trùng batch trong producer session/protocol |
| Kafka input → xử lý → Kafka output | Kafka transaction + offset trong transaction + read_committed | Output và input offset được commit nguyên tử trong Kafka |
| Kafka input → database | Inbox/idempotent write và DB transaction | Side effect DB không lặp dù record có thể được giao lại |
| Kafka input → HTTP/API ngoài | Idempotency key hoặc hợp đồng idempotent của API | Dịch vụ đích nhận diện và loại yêu cầu lặp |
| Database update → Kafka output | Transactional Outbox + relay idempotent | Event được lưu bền vững cùng thay đổi DB và có thể phát lại an toàn |

Nếu một luồng đi qua Kafka, database, cache và HTTP service, cần thiết kế bảo đảm riêng cho từng ranh giới. Kafka transaction không biến các hệ thống đó thành một distributed transaction.

## 10. Auto commit có thể làm rộng cửa sổ lỗi

Với enable.auto.commit=true, consumer tự commit tiến độ poll theo chu kỳ. Cơ chế này không hiểu nghiệp vụ đã hoàn tất hay chưa.

Nếu ứng dụng xử lý đồng bộ từng batch và chỉ gọi poll tiếp sau khi xử lý xong, auto commit có thể phù hợp với trường hợp đơn giản. Nhưng nếu ứng dụng dispatch record sang worker bất đồng bộ, nuốt exception rồi tiếp tục poll, hoặc cho phép công việc chưa xong khi chu kỳ commit chạy, committed offset có thể vượt qua record chưa xử lý.

Với nghiệp vụ cần kiểm soát chặt, thường đặt:

~~~properties
enable.auto.commit=false
~~~

Sau đó commit offset sau khi công việc tương ứng đã hoàn tất. Nếu xử lý song song, chỉ commit offset hoàn tất liên tục theo từng partition; không commit offset cao nhất khi còn record có offset thấp hơn chưa xong.

## 11. Retry, poison message và cửa sổ lỗi

Nếu xử lý record thất bại, consumer có thể retry. Cần phân biệt:

- Lỗi tạm thời như database timeout: retry có giới hạn và backoff.
- Lỗi dữ liệu vĩnh viễn như schema không hợp lệ: cần cách ly hoặc dead-letter để không chặn partition mãi mãi.
- Lỗi sau side effect nhưng trước offset commit: retry có thể lặp side effect; inbox/idempotency phải bảo vệ.

Dead-letter topic giúp cách ly record không thể xử lý sau chính sách retry. Khi chuyển record sang DLT, ứng dụng cần xác định thời điểm commit offset gốc. Nếu publish DLT thành công nhưng commit offset gốc thất bại, record lỗi có thể được đọc lại và publish DLT lần nữa. Có thể dùng event ID và xử lý idempotent ở consumer DLT để chống bản ghi trùng.

Với Kafka-to-Kafka, có thể dùng Kafka transaction để ghi DLT record và commit offset gốc trong cùng transaction nếu thiết kế phù hợp. Với database hoặc API ngoài, cần cơ chế idempotency riêng.

## 12. Quan sát và kiểm thử các failure window

Không chỉ kiểm tra happy path. Hãy chủ động mô phỏng crash ở từng ranh giới:

1. Dừng consumer ngay sau poll nhưng trước khi xử lý.
2. Dừng consumer sau khi DB transaction rollback.
3. Dừng consumer ngay sau DB commit nhưng trước Kafka offset commit.
4. Làm mất kết nối trong lúc commit offset để quan sát kết quả không chắc chắn.
5. Dừng consumer sau khi offset commit nhưng trước khi side effect (để kiểm tra thiết kế có commit sớm hay không).
6. Abort Kafka transaction sau khi gửi output nhưng trước commit.
7. Gửi lại cùng event ID để xác nhận inbox/deduplication ngăn side effect lặp.

Các metric và log nên có:

- Topic, partition, offset và event ID.
- Thời gian từ poll đến bắt đầu xử lý và thời gian xử lý nghiệp vụ.
- Thời điểm DB transaction commit/rollback.
- Kết quả commit offset hoặc Kafka transaction.
- Số lần delivery/retry của cùng event ID.
- Số event bị deduplicate, số lỗi DLT và consumer lag.

Không ghi payload nhạy cảm vào log. Dùng event ID/correlation ID để liên kết log consumer, database và dịch vụ downstream.

## 13. Checklist thiết kế consumer an toàn

- Xác định side effect nằm ở Kafka, database hay API ngoài.
- Xác định thứ tự xử lý và commit tương ứng với semantics mong muốn.
- Dùng at-least-once khi cần tránh mất xử lý và làm side effect idempotent.
- Tạo event ID ổn định để nhận diện replay.
- Với database, lưu inbox marker và thay đổi nghiệp vụ trong cùng DB transaction.
- Commit Kafka offset sau khi DB transaction thành công.
- Với Kafka-to-Kafka, dùng Kafka transaction để ghi output và input offsets cùng nhau.
- Consumer đọc transactional output dùng isolation.level=read_committed.
- Không giả định Kafka transaction bao gồm database hoặc HTTP API.
- Nếu xử lý song song, chỉ commit offset hoàn tất liên tục theo partition.
- Có retry giới hạn, backoff và DLT cho lỗi không thể phục hồi.
- Kiểm thử crash tại các điểm giữa poll, side effect và commit.

## Kết luận

Cửa sổ lỗi xuất hiện vì đọc record, thực hiện side effect và commit offset là các bước riêng biệt. Commit trước xử lý có thể làm mất công việc; xử lý trước commit có thể khiến record được đọc lại và side effect lặp. Position tiến lên khi poll, còn committed offset là checkpoint dùng để khôi phục consumer group.

Với side effect ở database, inbox pattern kết hợp unique event ID và transaction database giúp xử lý replay an toàn; commit Kafka offset sau DB commit. Với luồng Kafka-to-Kafka, Kafka transaction có thể commit output và input offset như một đơn vị, với consumer output dùng read_committed. Hãy luôn xác định phạm vi exactly-once và bảo vệ từng ranh giới hệ thống thay vì giả định một transaction Kafka bao phủ toàn bộ ứng dụng.
