# Giới hạn exactly-once khi gọi dịch vụ hoặc tạo tác dụng phụ ngoài Kafka

Kafka transactions và exactly-once semantics (EOS) giúp một ứng dụng đọc record từ Kafka, xử lý và ghi record kết quả trở lại Kafka theo một giao dịch nhất quán. Tuy nhiên, bảo đảm này có ranh giới rõ ràng: Kafka có thể commit output records cùng consumer offsets trong một Kafka transaction, nhưng không thể tự rollback một lần gọi HTTP, một giao dịch database độc lập, một email đã gửi hoặc một file đã ghi.

Đây là giới hạn quan trọng khi xây dựng ứng dụng Spring Cloud Stream. Một function có thể chạy trong Kafka transaction rồi gọi dịch vụ thanh toán hoặc cập nhật cơ sở dữ liệu. Nếu transaction Kafka bị rollback sau khi tác dụng phụ bên ngoài đã hoàn tất, message đầu vào có thể được giao lại và code gọi dịch vụ sẽ chạy lần nữa. Muốn tránh tác dụng phụ trùng lặp, ứng dụng phải phối hợp với hệ thống bên ngoài bằng idempotency, inbox/outbox, saga hoặc cơ chế đối soát phù hợp.

## 1. Exactly-once của Kafka bảo đảm điều gì?

Với mô hình consume-process-produce, Kafka transaction có thể kết hợp hai việc:

1. Ghi các output records vào một hoặc nhiều Kafka topic.
2. Ghi offsets của các input records đã xử lý vào cùng transaction.

Hai việc được commit hoặc abort cùng nhau. Nếu transaction commit, downstream consumer dùng isolation level read_committed có thể đọc các output records đã commit và input offsets cũng được cập nhật. Nếu transaction abort, output records chưa commit không được consumer read_committed nhìn thấy và offsets đầu vào không được tiến lên như một giao dịch thành công.

Ví dụ một processor nhận OrderCreated và phát OrderAccepted:

~~~text
Kafka input topic
      |
      v
Consumer đọc record
      |
      v
Xử lý trong listener transaction
      |
      +----> Ghi output record vào Kafka transaction
      |
      +----> Ghi input offset vào cùng transaction
      |
      v
Commit transaction
      |
      +----> Output record được công bố
      +----> Input offset được cập nhật
~~~

Điểm cần hiểu đúng là EOS bảo vệ kết quả Kafka có thể quan sát được của chuỗi read-process-write. Nó không có nghĩa hàm xử lý chỉ được gọi đúng một lần trong mọi tình huống. Khi transaction rollback, record đầu vào có thể được đọc và xử lý lại. Vì vậy phần code xử lý vẫn có thể chạy nhiều lần; các output Kafka của những transaction bị abort không được công bố cho consumer read_committed.

Kafka transaction không bao gồm các hệ thống không tham gia transaction đó. HTTP API, database riêng, SMTP, object storage, filesystem hoặc một message broker khác không tự động trở thành một phần của Kafka transaction.

## 2. Bật transactional binder trong Spring Cloud Stream

Kafka Binder có thể bật transaction bằng cách đặt transaction-id-prefix khác rỗng:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: orders-processor-instance-1-
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
        processOrder-out-0:
          destination: orders.accepted
~~~

Giá trị orders-processor-instance-1- chỉ là ví dụ. Mỗi instance đang chạy của ứng dụng phải có transaction ID prefix duy nhất; trong môi trường container, hãy lấy một giá trị ổn định và khác nhau theo từng instance/pod. Nếu hai instance dùng cùng prefix, producer có thể fence lẫn nhau và làm transaction thất bại.

Trong processor application, consumer bắt đầu transaction. Các record được gửi từ consumer thread qua producer thuộc cùng transactional producer factory có thể tham gia transaction đó. Khi listener kết thúc bình thường, container gửi offset vào transaction rồi commit. Nếu listener ném exception, transaction rollback.

Ví dụ function xử lý và phát output:

~~~java
@Bean
Consumer<OrderCreated> processOrder(StreamBridge streamBridge) {
    return event -> {
        OrderAccepted accepted =
            new OrderAccepted(event.eventId(), event.orderId());

        boolean sent = streamBridge.send("processOrder-out-0", accepted);
        if (!sent) {
            throw new IllegalStateException("Output binding rejected the event");
        }
    };
}
~~~

Khi binder transaction được kích hoạt đúng và lời gọi StreamBridge diễn ra trên consumer thread, việc gửi output có thể tham gia Kafka transaction do consumer khởi tạo. Nếu có nhiều binder hoặc producer factory khác nhau, cần xác nhận các binding dùng đúng binder và transaction manager.

Producer properties riêng của từng binding bị bỏ qua khi transactional binder dùng producer factory chung; cấu hình producer cho transactional binder nằm dưới spring.cloud.stream.kafka.binder.transaction.producer. Hãy kiểm tra tài liệu phiên bản Spring Cloud Stream đang dùng trước khi sao chép cấu hình producer thông thường sang transactional binder.

## 3. Consumer downstream cần đọc committed records

Consumer downstream cần isolation.level=read_committed nếu chỉ muốn nhìn thấy các record thuộc transaction đã commit:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                isolation.level: read_committed
~~~

Tên binding trong ví dụ là processOrder-in-0; cấu hình thực tế phải đặt trên consumer binding cần đọc transactional output. Với read_uncommitted, consumer có thể nhìn thấy record từ transaction chưa commit hoặc đã abort. Khi xây dựng chuỗi processor dựa trên EOS, hãy cấu hình isolation phù hợp trên các consumer downstream.

read_committed không biến database hoặc HTTP API thành transactional resource của Kafka. Nó chỉ kiểm soát những record Kafka nào được phép nhìn thấy.

## 4. Vì sao gọi dịch vụ ngoài Kafka có thể bị lặp?

Giả sử một consumer đọc PaymentRequested, gọi payment API và sau đó commit Kafka transaction. Có một cửa sổ lỗi:

~~~text
1. Kafka giao PaymentRequested
2. Listener bắt đầu Kafka transaction
3. Ứng dụng gọi payment API
4. Payment service đã trừ tiền thành công
5. Ứng dụng gặp lỗi trước khi Kafka transaction commit
6. Kafka transaction rollback
7. Input offset chưa được commit
8. Kafka giao lại PaymentRequested
9. Listener gọi payment API lần nữa
~~~

Kafka không thể hoàn tác bước trừ tiền ở bước 4. Nếu payment API không hỗ trợ idempotency, lần gọi thứ hai có thể trừ tiền lần nữa dù output Kafka của lần xử lý đầu tiên đã bị abort.

Một tình huống khác cũng phổ biến: ứng dụng gửi HTTP request, dịch vụ bên ngoài thực hiện thành công nhưng response bị mất hoặc timeout. Ứng dụng không biết chắc thao tác đã thành công hay chưa. Nếu retry bằng một request mới, tác dụng phụ có thể lặp. Nếu không retry, thao tác có thể bị bỏ sót khi request thực sự chưa đến nơi.

Đây là bài toán kết quả không xác định (ambiguous outcome) giữa hai hệ thống độc lập. Kafka transaction không giải quyết được vì dịch vụ HTTP không tham gia cùng transaction.

## 5. Các cửa sổ lỗi khi ghi database

Giả sử consumer đọc một event Kafka rồi cập nhật database:

| Thời điểm lỗi | Kết quả có thể xảy ra |
|---|---|
| Trước khi DB commit | DB rollback; Kafka có thể giao lại event |
| Sau khi DB commit nhưng trước khi Kafka offset commit | DB đã thay đổi; Kafka giao lại event và có nguy cơ áp dụng thay đổi lần nữa |
| Offset Kafka được commit trước DB commit | Ứng dụng có thể mất tác dụng phụ DB nếu tiến trình chết trước khi DB commit |
| DB commit thành công nhưng response commit Kafka bị mất | Ứng dụng có thể không biết Kafka đã commit hay chưa; cần thiết kế xử lý lặp an toàn |

Thứ tự commit có thể giảm một số rủi ro nhưng không tạo ra một transaction nguyên tử giữa hai hệ thống. Nếu DB commit trước, crash trước Kafka offset commit dẫn đến redelivery. Nếu Kafka offset commit trước, crash trước DB commit có thể làm mất cập nhật DB. Chỉ một cơ chế transaction phân tán được cả hai hệ thống hỗ trợ mới có thể phối hợp commit nguyên tử; nhiều hệ thống thực tế không hỗ trợ hoặc không muốn vận hành 2PC.

Spring transaction synchronization hoặc việc phối hợp nhiều transaction manager có thể điều khiển thứ tự commit, nhưng không biến hai transaction manager độc lập thành một transaction phân tán có khả năng rollback nguyên tử khi process hoặc mạng bị lỗi giữa hai lần commit.

## 6. Idempotency: cùng một yêu cầu lặp lại không tạo thêm tác dụng phụ

Idempotency là thuộc tính mà việc thực hiện cùng một thao tác nhiều lần với cùng một định danh không làm thay đổi kết quả cuối cùng sau lần đầu. Ví dụ, xử lý eventId evt-1001 lần thứ hai không tạo thêm một khoản thanh toán hoặc một lần cộng điểm.

Với dịch vụ bên ngoài, dùng một idempotency key ổn định lấy từ event ID hoặc business operation ID:

~~~java
paymentClient.charge(
    new ChargeRequest(orderId, amount),
    event.eventId()
);
~~~

HTTP client có thể gửi eventId trong header Idempotency-Key:

~~~http
POST /payments
Idempotency-Key: evt-1001
Content-Type: application/json
~~~

Payment service cần lưu key và kết quả xử lý một cách nguyên tử với thao tác thanh toán. Khi nhận lại cùng key, nó trả về kết quả đã lưu thay vì tạo khoản thanh toán mới. Nếu cùng key nhưng payload khác, service nên từ chối để phát hiện lỗi tái sử dụng key.

Các nguyên tắc:

- Dùng eventId hoặc operationId ổn định qua mọi lần retry.
- Không sinh UUID mới mỗi lần gọi lại dịch vụ.
- Cùng một key phải đại diện cho cùng một thao tác và cùng payload có ý nghĩa.
- Dịch vụ nhận request phải lưu key, trạng thái và kết quả đủ lâu để bao phủ khoảng thời gian retry/replay.
- Nếu dịch vụ ngoài không hỗ trợ idempotency, cần cơ chế đối soát hoặc saga thay vì giả định retry là an toàn.

Idempotency không ngăn request được gửi nhiều lần; nó làm cho các lần gửi lặp có cùng kết quả nghiệp vụ.

## 7. Inbox pattern cho consumer ghi database

Inbox pattern ghi nhận event đã được xử lý trong cùng transaction database với thay đổi nghiệp vụ. Bảng inbox có unique constraint trên event ID:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Consumer mở một DB transaction, thử ghi event ID trước, rồi chỉ thực hiện tác dụng phụ nếu lần ghi đó thành công:

~~~java
@Transactional
public void apply(OrderPaid event) {
    boolean firstDelivery =
        inboxRepository.insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return; // Event đã được áp dụng trong một lần giao trước
    }

    orderRepository.markPaid(event.orderId(), event.amount());
}
~~~

insertIfAbsent phải được bảo vệ bởi unique constraint ở database; không chỉ kiểm tra SELECT rồi INSERT trong hai câu lệnh rời rạc vì hai consumer đồng thời có thể cùng vượt qua bước kiểm tra. Có thể dùng INSERT ... ON CONFLICT DO NOTHING hoặc câu lệnh tương đương của database.

Nếu cập nhật đơn hàng thất bại, transaction DB rollback cả dòng inbox lẫn thay đổi nghiệp vụ. Khi Kafka giao lại event, consumer có thể thử lại. Nếu DB commit thành công nhưng Kafka offset chưa commit, event được giao lại; lần sau insertIfAbsent trả về false và consumer bỏ qua tác dụng phụ đã hoàn thành. Khi listener kết thúc bình thường, offset có thể tiến lên.

Mẫu này tạo xử lý idempotent ở database dù Kafka offset và DB không cùng một transaction. Nó không làm callback chỉ chạy một lần; nó bảo đảm lần chạy lặp không áp dụng tác dụng phụ DB lần nữa.

## 8. Outbox pattern cho database và sự kiện phát ra

Một vấn đề khác là ứng dụng vừa cập nhật DB vừa phát event Kafka. Nếu DB commit thành công nhưng publish Kafka thất bại, trạng thái DB và event bị lệch. Nếu publish Kafka trước rồi DB rollback, downstream có thể nhận event cho thay đổi chưa tồn tại.

Outbox pattern giải quyết dual-write bằng cách lưu thay đổi nghiệp vụ và bản ghi cần phát vào cùng một DB transaction:

~~~text
DB transaction
   |
   +--> UPDATE orders
   |
   +--> INSERT outbox_event
   |
   +--> COMMIT

Outbox relay
   |
   +--> Đọc bản ghi chưa gửi
   |
   +--> Publish Kafka
   |
   +--> Đánh dấu đã gửi
~~~

Ví dụ schema:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Service ghi đơn hàng và outbox trong cùng transaction:

~~~java
@Transactional
public void confirmOrder(Order order) {
    orderRepository.save(order);
    outboxRepository.insert(
        OutboxEvent.from(order.eventId(), order.id(), "OrderConfirmed", order)
    );
}
~~~

Một relay hoặc CDC connector đọc outbox và publish lên Kafka. Nếu relay publish thành công nhưng chết trước khi đánh dấu published_at, nó có thể publish lại cùng event. Vì vậy, outbox đảm bảo không mất ý định phát event khi DB commit, nhưng relay vẫn thường có semantics at-least-once. Consumer cần idempotency/inbox theo eventId.

Outbox không tự tạo exactly-once giữa DB và Kafka; nó biến thao tác dual-write thành một DB transaction cộng với một luồng publish có thể retry và deduplicate.

## 9. Gọi HTTP API: idempotency, timeout và đối soát

Khi consumer gọi một dịch vụ ngoài, hãy thiết kế theo operation ID:

1. Xác định eventId hoặc tạo operationId một lần và lưu bền vững.
2. Gửi operationId làm idempotency key trong mọi lần retry.
3. Dịch vụ ngoài ghi nhận key và kết quả cùng transaction với tác dụng phụ.
4. Nếu timeout, retry cùng key hoặc truy vấn trạng thái theo key.
5. Nếu kết quả vẫn không rõ, chuyển sang trạng thái pending/reconciliation thay vì phát request mới với key khác.

Ví dụ pseudo-code:

~~~java
public PaymentResult charge(OrderCreated event) {
    String operationId = event.eventId();

    try {
        return paymentClient.charge(
            event.orderId(),
            event.total(),
            operationId
        );
    }
    catch (SocketTimeoutException timeout) {
        return paymentClient.findByIdempotencyKey(operationId)
            .orElseThrow(() -> new PaymentOutcomeUnknownException(operationId));
    }
}
~~~

Không phải dịch vụ nào cũng hỗ trợ idempotency key hoặc tra cứu kết quả. Nếu provider không có khả năng này, ứng dụng có thể cần lưu trạng thái operation, giới hạn retry, yêu cầu đối soát thủ công hoặc dùng quy trình bù trừ. Không thể tự bảo đảm exactly-once cho một API chỉ bằng cách đặt Kafka transaction quanh lời gọi HTTP.

## 10. Saga và hành động bù trừ

Khi một nghiệp vụ gồm nhiều dịch vụ độc lập, có thể dùng saga: mỗi bước commit cục bộ ở dịch vụ của nó; nếu bước sau thất bại, hệ thống phát một hành động bù trừ để đưa nghiệp vụ về trạng thái chấp nhận được.

Ví dụ đặt hàng:

| Bước | Tác dụng phụ | Hành động bù trừ có thể có |
|---|---|---|
| Giữ tồn kho | Giảm lượng hàng khả dụng | Giải phóng tồn kho |
| Thu tiền | Tạo khoản charge | Hoàn tiền |
| Tạo vận đơn | Đặt yêu cầu giao hàng | Hủy vận đơn nếu còn cho phép |

Saga không rollback lịch sử của dịch vụ bên ngoài như một DB transaction chung. Nó tạo một quy trình nghiệp vụ mới để bù trừ những tác dụng phụ đã xảy ra. Các bước saga cũng cần idempotency vì command/event có thể được giao lại.

Với thanh toán, hoàn tiền là một giao dịch mới có operation ID riêng, liên kết với khoản charge gốc. Không xóa hoặc giả vờ khoản charge chưa từng xảy ra.

## 11. Tác dụng phụ không phải database

Các tác dụng phụ khác cũng cần chiến lược idempotency hoặc reconciliation:

| Tác dụng phụ | Rủi ro khi retry | Cách giảm trùng lặp |
|---|---|---|
| Gửi email/SMS | Người nhận nhận nhiều bản giống nhau | Provider hỗ trợ idempotency; lưu notification ID và trạng thái gửi; đối soát trạng thái |
| Ghi file/object storage | Tạo nhiều object hoặc ghi đè dữ liệu | Dùng object key ổn định theo eventId, conditional write và checksum |
| Tạo tài khoản/tài nguyên cloud | Tạo nhiều tài nguyên cùng mục đích | Dùng client token/idempotency token và tra cứu theo operation ID |
| Cấp quyền hoặc gửi lệnh thiết bị | Áp dụng lệnh nhiều lần hoặc đảo trạng thái | Dùng command ID, version và thao tác idempotent; ghi nhận kết quả |
| Gửi webhook | Bên nhận xử lý cùng event nhiều lần | Gửi event ID, yêu cầu bên nhận deduplicate và retry có backoff |

Nếu một thao tác không thể làm idempotent và không có API tra cứu kết quả, hãy cân nhắc quy trình xác nhận thủ công hoặc đối soát. Một số tác dụng phụ, như gửi email đã được SMTP chấp nhận, không thể thu hồi bằng Kafka rollback.

## 12. Vì sao transaction synchronization không phải distributed atomic commit?

Spring for Apache Kafka hỗ trợ đồng bộ Kafka transaction với transaction manager khác. Ví dụ một DB transaction có thể commit trước, sau đó Kafka transaction commit; hoặc ứng dụng có thể sắp xếp thứ tự theo cách khác.

Đồng bộ thứ tự có ích nhưng vẫn có khoảng trống:

- DB commit thành công, process chết trước Kafka commit: DB đã thay đổi nhưng Kafka có thể giao lại event.
- Kafka commit thành công trước DB commit: DB commit thất bại thì output Kafka đã được công bố.
- Transaction manager thứ hai commit lỗi sau khi transaction manager thứ nhất đã commit: không thể rollback transaction đã commit trước đó chỉ bằng exception.

Vì vậy, không mô tả việc dùng hai transaction manager hoặc @Transactional lồng nhau như một bảo đảm exactly-once xuyên DB và Kafka. Nếu cả hai hệ thống thực sự hỗ trợ cùng một giao thức transaction phân tán và tổ chức chấp nhận chi phí vận hành, có thể đánh giá 2PC/XA cho trường hợp cụ thể. Với nhiều ứng dụng event-driven, inbox/outbox và idempotency dễ vận hành và phục hồi hơn.

## 13. Retry trong transactional binder

Retry vẫn có thể khiến code listener chạy lại. Với transactional Kafka Binder, exception trong listener làm transaction rollback; input record có thể được giao lại. Retry cần được cấu hình theo cơ chế after-rollback của container.

Tài liệu Kafka Binder lưu ý rằng cơ chế retry và dead-lettering thông thường của binder không hoạt động giống khi không dùng transaction. Khi transactional binder được bật, retry được điều phối sau rollback bằng DefaultAfterRollbackProcessor; dead-letter publication cũng được thực hiện ở giai đoạn xử lý sau rollback. Hãy kiểm tra cấu hình retryable exception, số lần thử, backoff và DLQ theo phiên bản Spring Cloud Stream.

Không retry vô hạn một lỗi nghiệp vụ không thể tự phục hồi. Với lỗi dữ liệu cố định, hãy chuyển sang luồng lỗi/DLQ sau số lần thử đã định và giữ event ID để điều tra. Dù dùng retry container hay retry ở tầng ứng dụng, tác dụng phụ ngoài Kafka vẫn phải idempotent.

## 14. Mẫu kiến trúc tham khảo

### Kafka-to-Kafka processor

- Dùng transactional binder.
- Consumer và output bindings dùng cùng transactional producer factory/binder.
- Các producer send diễn ra trên consumer thread để tham gia transaction.
- Downstream consumers dùng read_committed.
- Không gọi tác dụng phụ bên ngoài nếu chưa có idempotency/recovery.

### Kafka-to-database consumer

- Dùng DB transaction cho inbox row và thay đổi nghiệp vụ.
- Unique eventId bảo vệ trước redelivery.
- Chỉ để listener hoàn tất/offset commit sau khi DB transaction đã commit.
- Kiểm thử crash sau DB commit nhưng trước Kafka offset commit.

### Database-to-Kafka publisher

- Ghi thay đổi nghiệp vụ và outbox row trong cùng DB transaction.
- Relay/CDC publish outbox lên Kafka.
- Đánh dấu trạng thái gửi và xử lý khả năng publish lặp.
- Consumer downstream dùng inbox/idempotency.

### Kafka-to-external-service workflow

- Dùng eventId/operationId làm idempotency key.
- Lưu trạng thái operation để retry và reconciliation.
- Nếu workflow nhiều bước, dùng saga và hành động bù trừ.
- Không coi Kafka transaction là rollback của dịch vụ ngoài.

## 15. Kiểm thử các cửa sổ lỗi

Unit test thông thường không đủ để chứng minh xử lý an toàn khi process chết giữa hai hệ thống. Hãy kiểm thử các điểm lỗi có thể xảy ra:

- Gọi dịch vụ ngoài thành công, sau đó cố ý làm Kafka transaction rollback; xác nhận lần giao lại không tạo tác dụng phụ thứ hai.
- Dịch vụ ngoài hoàn tất nhưng client timeout; xác nhận retry cùng idempotency key trả về kết quả cũ.
- DB commit thành công, process chết trước khi Kafka offset commit; xác nhận inbox ngăn cập nhật trùng khi redelivery.
- DB transaction rollback; xác nhận inbox row và thay đổi nghiệp vụ cùng rollback.
- Outbox relay publish thành công rồi chết trước khi đánh dấu published; xác nhận consumer downstream deduplicate event.
- Kafka output được gửi nhưng transaction abort; xác nhận consumer read_committed không nhìn thấy output bị abort.
- Consumer read_uncommitted trong môi trường thử nghiệm để thấy sự khác biệt khi đọc transactional output.
- Hai instance chạy đồng thời; xác nhận transactionIdPrefix khác nhau và không fencing lẫn nhau.
- Retry cạn số lần; xác nhận record đi đến error/DLQ flow đã cấu hình và có thể điều tra.
- Saga thất bại giữa các bước; xác nhận hành động bù trừ có operation ID riêng và xử lý lặp an toàn.

Integration test nên dùng Kafka broker thật hoặc môi trường test tương đương có hỗ trợ transaction. Với DB/API ngoài, dùng fault injection hoặc mock có thể mô phỏng timeout sau khi phía server đã commit để kiểm tra trường hợp kết quả không xác định.

## 16. Checklist thiết kế exactly-once

- [ ] Đã xác định phạm vi exactly-once là Kafka-to-Kafka hay có hệ thống ngoài.
- [ ] Kafka transaction commit output records cùng input offsets.
- [ ] Mỗi application instance có transactionIdPrefix duy nhất.
- [ ] Consumer downstream dùng read_committed khi cần chỉ đọc output đã commit.
- [ ] Không giả định callback chỉ chạy một lần; đã thiết kế xử lý lặp an toàn.
- [ ] Mọi lời gọi HTTP có idempotency key ổn định hoặc quy trình đối soát.
- [ ] DB consumer dùng inbox/unique event ID trong cùng transaction với thay đổi nghiệp vụ.
- [ ] DB-to-Kafka publisher dùng outbox hoặc cơ chế dual-write có phục hồi.
- [ ] Tác dụng phụ không thể rollback có saga/compensation khi phù hợp.
- [ ] Đã hiểu thứ tự commit khi phối hợp nhiều transaction manager.
- [ ] Retry và DLQ phù hợp với transactional binder.
- [ ] Đã kiểm thử crash window, timeout, redelivery và replay.

Kafka EOS là bảo đảm mạnh cho việc đọc, xử lý và ghi giữa các Kafka topic khi offset và output cùng tham gia transaction. Nó không làm cho một lần gọi dịch vụ HTTP, một cập nhật database độc lập hay một email trở thành một phần của Kafka transaction. Hãy xem phần xử lý có thể chạy lại, dùng idempotency key và inbox để bảo vệ tác dụng phụ, dùng outbox cho dual-write từ database sang Kafka, và dùng saga khi cần bù trừ một quy trình nhiều dịch vụ.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.1 — Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/5.1/kafka/kafka-binder/transactional.html)
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Blog — Apache Kafka's Exactly-Once Semantics in Spring Cloud Stream Kafka Applications](https://spring.io/blog/2023/10/16/apache-kafkas-exactly-once-semantics-in-spring-cloud-stream-kafka/)
