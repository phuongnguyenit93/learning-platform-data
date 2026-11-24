# Phát sự kiện từ REST, lịch chạy và service nghiệp vụ

Không phải sự kiện nào cũng được tạo ra bên trong một hàm Supplier. Trong ứng dụng thực tế, sự kiện có thể phát sinh khi REST API nhận yêu cầu, khi một tác vụ chạy theo lịch đến hạn hoặc khi service nghiệp vụ hoàn tất một thao tác. Spring Cloud Stream cung cấp **StreamBridge** để những thành phần imperative này gửi message vào luồng đã cấu hình mà không cần tự gọi API riêng của Kafka, RabbitMQ hoặc Pulsar.

**StreamBridge** đóng vai trò cầu nối giữa mã Java thông thường và hệ thống messaging. Thành phần gọi tạo payload hoặc **Message<?>**, chọn binding đầu ra, rồi gửi message. Binder đảm nhiệm việc chuyển message đến destination tương ứng. Cách tổ chức này giúp controller, scheduler và service tập trung vào nghiệp vụ, trong khi cấu hình binding chịu trách nhiệm kết nối với broker.

## 1. StreamBridge giải quyết vấn đề gì?

Supplier phù hợp khi ứng dụng chủ động tạo message theo cơ chế poll hoặc nguồn phát liên tục. Nhưng một REST controller không phải Supplier; nó được gọi khi có HTTP request. Một scheduler chạy theo thời gian cũng không cần biến thành một hàm Supplier. Service nghiệp vụ thường chỉ muốn phát sự kiện tại một điểm cụ thể trong quy trình xử lý.

**StreamBridge** cho phép gửi message từ các thành phần đó:

~~~text
REST request -----------+
                        |
Scheduled task ---------+--> StreamBridge --> Output binding
                        |                         |
Business service ------+                         v
                                             Binder
                                                |
                                                v
                                           Kafka / RabbitMQ / Pulsar
~~~

Ví dụ, khi khách hàng xác nhận đơn hàng, ứng dụng có thể phát **OrderConfirmed**. Khi đến giờ tổng hợp tồn kho, scheduler phát **InventorySnapshotRequested**. Khi service hoàn tất thanh toán, nó phát **PaymentCompleted**.

**StreamBridge** là API của Spring Cloud Stream. Nó không phải KafkaTemplate, RabbitTemplate hay Pulsar client; ứng dụng không cần trực tiếp tạo producer của từng broker nếu chỉ dùng các khả năng mà binder cung cấp.

## 2. Khai báo output binding

Với những destination đã biết trước, nên khai báo output binding trong **application.yml**. Ví dụ dùng Kafka binder:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderConfirmed-out-0:
          destination: orders.confirmed
          content-type: application/json
        inventorySnapshot-out-0:
          destination: inventory.snapshot.requested
          content-type: application/json
        paymentCompleted-out-0:
          destination: payments.completed
          content-type: application/json
      kafka:
        binder:
          brokers: localhost:9092
~~~

Trong cấu hình:

- **orderConfirmed-out-0**, **inventorySnapshot-out-0** và **paymentCompleted-out-0** là tên binding mà mã Java truyền cho **StreamBridge**.
- **destination** là tên luồng logic trên broker.
- **content-type** cho biết định dạng payload để message converter xử lý.
- **brokers** là cấu hình riêng của Kafka binder trong ví dụ này.

Tên binding đầu ra được khai báo tường minh nên không phụ thuộc vào tên phương thức Java đang gọi **StreamBridge**. Một binding có thể được dùng từ nhiều nơi trong ứng dụng nếu các nơi đó cùng phát một loại message theo cùng hợp đồng.

Nếu dùng RabbitMQ hoặc Pulsar, phần binding và destination logic vẫn có thể giữ cách tổ chức tương tự. Thay starter và cấu hình kết nối bằng binder tương ứng, sau đó kiểm tra cách destination được ánh xạ thành exchange/queue hoặc topic/subscription. Không sao chép cấu hình broker Kafka sang binder khác.

## 3. Phát sự kiện từ REST controller

REST API thường nhận một lệnh từ client, thực hiện kiểm tra đầu vào rồi phát sự kiện để các dịch vụ khác xử lý bất đồng bộ. Ví dụ dưới đây minh họa endpoint phát sự kiện xác nhận đơn hàng:

~~~java
import java.time.Instant;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

record OrderConfirmed(String orderId, Instant confirmedAt) {}

@RestController
class OrderEventController {

    private final StreamBridge streamBridge;

    OrderEventController(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @PostMapping("/api/orders/{orderId}/confirm")
    ResponseEntity<Void> confirm(@PathVariable String orderId) {
        if (orderId == null || orderId.isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        OrderConfirmed event =
                new OrderConfirmed(orderId, Instant.now());

        boolean sent = streamBridge.send("orderConfirmed-out-0", event);
        if (!sent) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .build();
        }

        return ResponseEntity.accepted().build();
    }
}
~~~

Khi endpoint được gọi, controller tạo payload **OrderConfirmed** và gửi qua binding **orderConfirmed-out-0**. Binder ánh xạ binding đó đến destination **orders.confirmed**. Client nhận HTTP 202 khi thao tác gửi được chấp nhận ở phía ứng dụng.

Giá trị **true** từ **StreamBridge.send** cho biết thao tác gửi vào output channel thành công theo cơ chế của binding. Nó không chứng minh consumer đã nhận, xử lý hoặc commit nghiệp vụ. Tương tự, HTTP 202 chỉ nên được hiểu là ứng dụng đã chấp nhận yêu cầu xử lý bất đồng bộ theo hợp đồng API; không mô tả nó như xác nhận hoàn tất nghiệp vụ phía sau.

Trong ứng dụng thật, controller thường gọi service nghiệp vụ để kiểm tra quyền, trạng thái đơn hàng và quy tắc chuyển trạng thái. Ví dụ trên tập trung vào vị trí phát sự kiện. Nếu thao tác đồng thời ghi cơ sở dữ liệu và phát message, cần xử lý tính nhất quán giữa hai việc; phần transactional outbox bên dưới trình bày cách làm bền vững hơn.

## 4. Gửi Message có header

**StreamBridge** có thể gửi object trực tiếp hoặc gửi **Message<?>**. Khi cần gắn metadata như event ID, event type hoặc correlation ID, tạo message bằng **MessageBuilder**:

~~~java
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderConfirmed> message = MessageBuilder
        .withPayload(new OrderConfirmed("ORD-1001", Instant.now()))
        .setHeader("eventId", UUID.randomUUID().toString())
        .setHeader("eventType", "OrderConfirmed")
        .setHeader("correlationId", "corr-8a21")
        .build();

boolean sent = streamBridge.send("orderConfirmed-out-0", message);
~~~

Header hỗ trợ truy vết và diễn giải sự kiện ở consumer. Nên dùng tên header nhất quán giữa các producer và chỉ truyền metadata cần thiết. Không đưa token, thông tin xác thực hoặc payload nghiệp vụ lớn vào header.

Nếu **content-type** đã được khai báo ở binding, Spring Cloud Stream có thể dùng message converter tương ứng để tuần tự hóa payload. Khi gửi **Message<?>**, kiểm tra header và cấu hình binding để bảo đảm converter nhận đúng kiểu dữ liệu. Với Avro hoặc Protobuf dùng native serializer, cần cấu hình serializer/deserializer của binder theo định dạng đã chọn; **StreamBridge** không tự biến object thành mọi định dạng nhị phân chỉ bằng cách đổi content type.

## 5. Phát sự kiện từ lịch chạy

Một tác vụ định kỳ có thể phát message mà không cần có HTTP request. Bật scheduling và dùng **StreamBridge** trong thành phần chạy theo lịch:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

record InventorySnapshotRequested(String requestId, Instant requestedAt) {}

@Configuration
@EnableScheduling
class SchedulingConfiguration {}

@Component
class InventorySnapshotScheduler {

    private final StreamBridge streamBridge;

    InventorySnapshotScheduler(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @Scheduled(fixedDelay = 60000)
    void requestSnapshot() {
        InventorySnapshotRequested event =
                new InventorySnapshotRequested(
                        UUID.randomUUID().toString(),
                        Instant.now());

        boolean sent = streamBridge.send("inventorySnapshot-out-0", event);
        if (!sent) {
            // Ghi log hoặc tăng metric để vận hành phát hiện lần gửi lỗi.
        }
    }
}
~~~

Thuộc tính **fixedDelay** quy định khoảng thời gian chờ sau khi lần gọi trước hoàn tất. Ví dụ dùng chu kỳ 60.000 ms. Có thể dùng cron expression khi lịch cần gắn với giờ cụ thể:

~~~java
@Scheduled(cron = "0 0 2 * * *")
void requestNightlySnapshot() {
    // Tạo sự kiện và gửi qua StreamBridge.
}
~~~

Khi triển khai nhiều instance của ứng dụng, mỗi instance có thể chạy cùng lịch và phát trùng sự kiện. Nếu chỉ một lần phát cho mỗi kỳ là yêu cầu bắt buộc, cần cơ chế điều phối như distributed lock, leader election hoặc lưu lịch chạy trong cơ sở dữ liệu. Consumer vẫn nên idempotent vì message có thể được giao lại.

Với tác vụ quan trọng, đừng chỉ ghi log khi gửi thất bại rồi bỏ qua. Hãy lưu trạng thái công việc cần phát, đặt chính sách thử lại và có cảnh báo nếu một kỳ chạy không được gửi thành công.

## 6. Phát sự kiện từ service nghiệp vụ

Service nghiệp vụ là nơi thường biết một sự kiện đã thực sự xảy ra. Ví dụ, sau khi xác nhận thanh toán thành công, service phát **PaymentCompleted** để dịch vụ hóa đơn hoặc phân tích tiếp tục xử lý:

~~~java
import java.time.Instant;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

record PaymentCompleted(
        String paymentId,
        String orderId,
        long amountMinorUnits,
        Instant completedAt) {}

@Service
class PaymentApplicationService {

    private final StreamBridge streamBridge;
    private final PaymentGateway paymentGateway;

    PaymentApplicationService(
            StreamBridge streamBridge,
            PaymentGateway paymentGateway) {
        this.streamBridge = streamBridge;
        this.paymentGateway = paymentGateway;
    }

    void completePayment(String paymentId, String orderId) {
        PaymentResult result = paymentGateway.capture(paymentId);
        if (!result.success()) {
            throw new IllegalStateException("Payment was not completed");
        }

        PaymentCompleted event = new PaymentCompleted(
                paymentId,
                orderId,
                result.amountMinorUnits(),
                Instant.now());

        boolean sent = streamBridge.send("paymentCompleted-out-0", event);
        if (!sent) {
            throw new IllegalStateException(
                    "Could not publish PaymentCompleted");
        }
    }
}
~~~

Các kiểu **PaymentGateway**, **PaymentResult** đại diện cho thành phần nghiệp vụ của ứng dụng. Điểm quan trọng là sự kiện chỉ được tạo sau khi thao tác thanh toán thành công. Consumer có thể dùng paymentId hoặc eventId để nhận diện message và tránh ghi nhận thanh toán hai lần.

Ví dụ trên thể hiện luồng gọi trực tiếp để dễ hiểu, nhưng cần cân nhắc kỹ khi service đồng thời cập nhật cơ sở dữ liệu. Nếu thanh toán đã thành công hoặc bản ghi nghiệp vụ đã commit mà thao tác gửi message thất bại, hệ thống có thể ở trạng thái nghiệp vụ hoàn tất nhưng sự kiện chưa được phát. Nếu gửi message thành công rồi transaction cơ sở dữ liệu rollback, consumer có thể nhận một sự kiện cho thay đổi chưa tồn tại.

Không nên mặc định lời gọi **StreamBridge.send** và transaction cơ sở dữ liệu tạo thành một giao dịch nguyên tử. Với sự kiện quan trọng gắn với thay đổi dữ liệu, nên dùng transactional outbox.

## 7. Transactional outbox khi cần bảo đảm phát sự kiện

Transactional outbox giải quyết tình huống một thao tác nghiệp vụ cần vừa cập nhật dữ liệu vừa phát sự kiện. Trong cùng transaction cơ sở dữ liệu, service ghi thay đổi nghiệp vụ và một bản ghi outbox. Một publisher riêng đọc các bản ghi chưa phát, gửi bằng **StreamBridge**, rồi đánh dấu đã phát sau khi gửi thành công.

~~~text
Business service
      |
      v
Database transaction
  - cập nhật dữ liệu nghiệp vụ
  - thêm bản ghi Outbox
      |
      v
Commit
      |
      v
Outbox publisher / scheduled poller
      |
      v
StreamBridge.send(...)
      |
      v
Broker destination
      |
      v
Đánh dấu bản ghi Outbox đã gửi
~~~

Vì dữ liệu nghiệp vụ và outbox được ghi trong cùng transaction, nếu transaction rollback thì cả hai đều không xuất hiện. Nếu ứng dụng dừng sau commit nhưng trước khi publish, publisher có thể gửi lại khi khởi động. Điều này giúp tránh mất sự kiện do khoảng trống giữa commit và gửi message.

Pseudocode của publisher:

~~~java
void publishPendingEvents() {
    List<OutboxEvent> events = outboxRepository.findPendingBatch(100);

    for (OutboxEvent event : events) {
        boolean sent = streamBridge.send(
                "paymentCompleted-out-0",
                event.toPaymentCompleted());

        if (sent) {
            outboxRepository.markPublished(event.id());
        } else {
            outboxRepository.recordAttempt(event.id());
        }
    }
}
~~~

Đây là pseudocode tập trung vào trình tự. Khi triển khai thật, cần thiết kế khóa hoặc cơ chế claim bản ghi để nhiều publisher không xử lý cùng một batch ngoài ý muốn, đặt giới hạn retry và lưu thông tin lỗi. Nếu publisher gửi thành công nhưng dừng trước khi đánh dấu outbox, message có thể được gửi lại. Vì vậy, outbox thường cung cấp khả năng phát ít nhất một lần; consumer phải idempotent dựa trên eventId hoặc khóa nghiệp vụ.

## 8. Binding khai báo và destination động

Có hai cách dùng **StreamBridge**:

**Binding khai báo trước** phù hợp khi destination đã biết và ổn định. Ví dụ **orderConfirmed-out-0** được cấu hình rõ ràng với destination **orders.confirmed**. Cách này giúp review cấu hình, cấp quyền và giám sát dễ hơn.

**Destination động** phù hợp khi đích gửi được quyết định lúc chạy. Nếu không có binding cùng tên, **StreamBridge** có thể tạo output binding động cho destination được truyền vào:

~~~java
boolean sent = streamBridge.send("tenant-a.audit-events", auditEvent);
~~~

Trong ví dụ này, tên truyền vào được dùng làm destination động khi chưa có binding tương ứng. Việc tạo binding động phụ thuộc khả năng của binder và cấu hình ứng dụng. Nên giới hạn destination được phép theo quy tắc của hệ thống, tránh nhận một tên tùy ý từ HTTP request rồi dùng trực tiếp làm destination. Nếu người gọi có thể chọn destination, hãy ánh xạ lựa chọn đó qua danh sách cho phép do ứng dụng kiểm soát.

Khi destination đã biết trước, ưu tiên binding khai báo. Destination động tạo thêm tài nguyên và trạng thái binding trong ứng dụng; cần quản lý số lượng destination, cache binding, quyền broker và vòng đời tài nguyên. Không dùng destination động để thay thế một mô hình định tuyến nghiệp vụ đã có quy tắc rõ ràng.

## 9. Xử lý kết quả gửi và lỗi

**StreamBridge.send** trả về boolean để cho biết thao tác gửi message qua binding có thành công ở thời điểm gọi hay không. Hãy kiểm tra kết quả khi ứng dụng cần phản ứng với lỗi:

- Với REST API đồng bộ, trả lỗi phù hợp nếu message không được chấp nhận gửi và hợp đồng endpoint yêu cầu xác nhận việc gửi.
- Với scheduler, ghi log có eventId, tăng metric và đưa công việc vào hàng đợi thử lại hoặc bảng trạng thái.
- Với service nghiệp vụ quan trọng, dùng outbox để không phụ thuộc vào một lần gửi trực tiếp.
- Với mọi consumer, thiết kế xử lý lặp an toàn và theo dõi retry/DLQ ở binder.

Kết quả **true** không chứng minh broker đã lưu bền vững theo mọi cấu hình, consumer đã nhận message hay nghiệp vụ phía sau đã hoàn tất. Muốn biết message đã được xử lý, cần cơ chế xác nhận ở cấp ứng dụng, trạng thái nghiệp vụ hoặc phản hồi sự kiện riêng.

Không retry vô hạn ngay trong luồng HTTP hoặc thread xử lý nghiệp vụ; điều đó có thể làm cạn thread và tăng tải khi broker gặp sự cố. Retry cần có giới hạn, backoff và nơi lưu trạng thái nếu công việc phải được phục hồi sau khi tiến trình dừng.

## 10. Kiểm thử thành phần dùng StreamBridge

Có thể dùng Spring Cloud Stream test binder để kiểm tra message được gửi ra output binding mà không cần chạy broker thật. Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.cloud.stream.binder.test.OutputDestination;

@SpringBootTest(properties = {
        "spring.cloud.stream.output-bindings=orderConfirmed-out-0",
        "spring.cloud.stream.bindings.orderConfirmed-out-0.destination=orders.confirmed",
        "spring.cloud.stream.bindings.orderConfirmed-out-0.content-type=application/json"
})
class OrderEventPublishingTest {

    @Autowired
    StreamBridge streamBridge;

    @Autowired
    OutputDestination output;

    @Test
    void publishesAnOrderConfirmedEvent() {
        OrderConfirmed event =
                new OrderConfirmed("ORD-TEST-1", Instant.parse("2026-01-01T00:00:00Z"));

        assertTrue(streamBridge.send("orderConfirmed-out-0", event));
        assertNotNull(output.receive(1000, "orderConfirmed-out-0"));
    }
}
~~~

Test binder xác nhận đường gửi ở cấp ứng dụng và output binding. Nó không thay thế kiểm thử tích hợp với Kafka, RabbitMQ hoặc Pulsar. Với broker thật, cần kiểm tra quyền ghi destination, serialization, header mapping, lỗi kết nối, retry và hành vi khi broker tạm dừng.

Với transactional outbox, bổ sung kiểm thử rằng thay đổi nghiệp vụ và bản ghi outbox cùng commit hoặc cùng rollback; publisher gửi lại bản ghi pending sau khi restart; và consumer không tạo side effect trùng khi nhận lại cùng eventId.

## 11. Chọn điểm phát sự kiện trong kiến trúc

| Nguồn phát | Khi nên dùng | Điều cần chú ý |
|---|---|---|
| REST controller | HTTP request trực tiếp yêu cầu phát một message | Xác thực, validation, timeout và ngữ nghĩa HTTP response |
| Scheduled task | Sự kiện hoặc công việc phát theo lịch | Nhiều instance có thể chạy trùng; cần điều phối và lưu trạng thái |
| Business service | Sự kiện phát sinh từ kết quả nghiệp vụ | Đồng bộ transaction và message; cân nhắc outbox |
| Outbox publisher | Sự kiện phải được phát bền vững sau khi dữ liệu commit | Idempotency, claim batch, retry và trạng thái publish |

Nên phát sự kiện tại nơi có đủ thông tin để xác định sự kiện thực sự đã xảy ra. Controller có thể nhận yêu cầu nhưng không nên tự kết luận một nghiệp vụ thành công nếu service chưa hoàn tất kiểm tra. Scheduler có thể tạo yêu cầu xử lý định kỳ nhưng cần mã lần chạy để phát hiện trùng. Service nghiệp vụ hiểu trạng thái domain, còn outbox bảo đảm sự kiện được lưu cùng thay đổi dữ liệu.

## 12. Checklist trước khi triển khai

- Binding đầu ra có tên rõ ràng và destination được cấu hình đúng.
- Payload có hợp đồng ổn định, eventId và metadata cần thiết.
- Content type và serializer phù hợp với định dạng dữ liệu.
- REST endpoint phân biệt yêu cầu được chấp nhận với nghiệp vụ đã hoàn tất.
- Scheduler có cơ chế tránh phát trùng khi chạy nhiều instance nếu yêu cầu nghiệp vụ cần điều đó.
- Service nghiệp vụ không giả định DB transaction và broker send là nguyên tử.
- Sự kiện quan trọng dùng outbox hoặc cơ chế giao nhận đã được thiết kế tương đương.
- Publisher có retry hữu hạn, quan sát lỗi và khả năng tiếp tục sau restart.
- Consumer idempotent và có theo dõi retry/DLQ.
- Kiểm thử bằng test binder và kiểm thử tích hợp với binder/broker thực tế.

**StreamBridge** giúp REST controller, scheduler và service nghiệp vụ gửi message qua cùng mô hình binding của Spring Cloud Stream. Binding khai báo trước phù hợp với destination ổn định; destination động hữu ích khi đích gửi thực sự được quyết định lúc chạy và được kiểm soát. Với sự kiện gắn với thay đổi dữ liệu quan trọng, transactional outbox, retry có giới hạn và consumer idempotent giúp luồng phát sự kiện có thể phục hồi và vận hành tin cậy hơn.
