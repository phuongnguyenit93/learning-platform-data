# Kiểm thử khởi động lại, lỗi mạng và phục hồi sau sự cố

Một ứng dụng Spring Cloud Stream phải tiếp tục xử lý đúng khi tiến trình khởi động lại, broker tạm ngừng, kết nối mạng bị đứt hoặc một dependency bên ngoài không phản hồi. Kiểm thử các tình huống này giúp xác nhận ứng dụng có kết nối lại, tiếp tục từ vị trí phù hợp, xử lý bản tin được giao lại và không tạo tác động phụ trùng lặp ngoài ý muốn.

Với mô hình Supplier, Function và Consumer, cần kiểm tra cả đường phát lẫn đường nhận. Với Kafka, RabbitMQ hoặc Pulsar, mỗi binder có cơ chế lưu vị trí đọc, acknowledgement, retry và redelivery riêng. Vì vậy, một bài kiểm thử chỉ chạy hàm trong JVM không đủ để chứng minh khả năng phục hồi của hệ thống đang chạy với broker thật.

## 1. Mục tiêu của kiểm thử phục hồi

Một bài kiểm thử phục hồi nên trả lời được các câu hỏi cụ thể:

- Ứng dụng có khởi động được khi broker đang tạm thời không sẵn sàng không?
- Producer có tiếp tục gửi được sau khi kết nối được khôi phục không?
- Consumer có kết nối lại và tiếp tục nhận bản tin không?
- Bản tin đang xử lý khi tiến trình dừng có được giao lại không?
- Vị trí đọc hoặc acknowledgement có được lưu đúng không?
- Một bản tin có thể được xử lý lại không, và tác động phụ có bị nhân đôi không?
- Lỗi nghiệp vụ có đi qua retry rồi đến DLQ theo cấu hình không?
- Sau khi broker hoặc ứng dụng hoạt động lại, backlog có được tiêu thụ hết không?
- Consumer group, queue hoặc subscription có giữ đúng danh tính qua lần khởi động lại không?

Không nên chỉ kiểm tra rằng log có dòng “connected” hoặc trạng thái health chuyển sang UP. Cần xác nhận kết quả nghiệp vụ ở nơi lưu bền vững và trạng thái của broker.

## 2. Ba lớp kiểm thử bổ sung cho nhau

| Lớp | Thành phần được kiểm tra | Có thể xác nhận | Không thể tự chứng minh |
|---|---|---|---|
| Unit test | Logic xử lý, idempotency, mapping, retry policy của ứng dụng | Kết quả hàm với dữ liệu đã cho | Kết nối broker, offset, acknowledgement, reconnect |
| Test Binder | Function/Consumer, binding và chuyển message trong JVM | Wiring cơ bản và kết quả xử lý nhanh | Lỗi mạng, broker restart, partition rebalance, persistence |
| Integration/resilience test | Ứng dụng cùng broker thật và hạ tầng thử nghiệm | Reconnect, redelivery, offset, DLQ, phục hồi sau sự cố | Mọi tình huống production nếu topology thử nghiệm quá đơn giản |

Spring Cloud Stream cung cấp Spring Integration Test Binder để kiểm thử ứng dụng mà không cần broker. Binder này chạy trong JVM và dùng các channel nội bộ. Nó hữu ích để kiểm tra logic function và tên binding, nhưng không mô phỏng socket, broker election, consumer group hoặc message persistence.

Một bộ kiểm thử cân bằng thường dùng Test Binder cho logic nhanh, rồi dùng broker container hoặc môi trường tích hợp cho những kịch bản liên quan đến vận hành.

## 3. Test Binder kiểm tra logic trước khi tạo lỗi hạ tầng

Dependency test của Spring Cloud Stream:

~~~kotlin
testImplementation("org.springframework.cloud:spring-cloud-stream-test-binder")
~~~

Ví dụ Function nhận sự kiện đơn hàng và chuẩn hóa trạng thái:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String status) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderEvent, OrderEvent> normalizeOrder() {
        return event -> new OrderEvent(
                event.orderId(),
                event.status().trim().toUpperCase());
    }
}
~~~

Test Binder có thể xác nhận binding và kết quả Function:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.support.GenericMessage;

@SpringBootTest(classes = OrderFunctionTest.TestApplication.class)
class OrderFunctionTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void normalizesOrderStatus() {
        input.send(new GenericMessage<>(
                "{\"orderId\":\"O-100\",\"status\":\" paid \"}".getBytes()),
                "normalizeOrder-in-0");

        var result = output.receive(2_000, "normalizeOrder-out-0");

        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload()))
                .contains("\"status\":\"PAID\"");
    }

    @SpringBootApplication
    @EnableTestBinder
    @Import(OrderFunctions.class)
    static class TestApplication {}
}
~~~

Ví dụ cần được điều chỉnh theo cách ứng dụng cấu hình component scan, serializer và test configuration. Mục tiêu của test này là xác nhận function hoạt động với binding; nó không phải bài kiểm thử restart.

## 4. Tạo môi trường broker thật cho integration test

Testcontainers có module cho Kafka, RabbitMQ và Apache Pulsar. Mỗi test có thể khởi động broker dùng một lần, cấp địa chỉ động cho Spring Boot rồi dọn container sau khi hoàn tất.

Ví dụ dependency trong Gradle khi dự án đã quản lý phiên bản Testcontainers bằng BOM:

~~~kotlin
testImplementation("org.testcontainers:testcontainers")
testImplementation("org.testcontainers:testcontainers-kafka")
testImplementation("org.testcontainers:testcontainers-rabbitmq")
testImplementation("org.testcontainers:testcontainers-pulsar")
testImplementation("org.testcontainers:testcontainers-toxiproxy")
~~~

Chỉ thêm module cho broker mà test suite thực sự sử dụng. Không cần khởi động cả ba broker cho mọi test.

Với Kafka, Spring Kafka cung cấp Embedded Kafka và các tiện ích test. Embedded broker phù hợp cho nhiều integration test nhẹ, nhưng test restart, network interruption hoặc nhiều broker cần một môi trường có thể điều khiển vòng đời broker rõ ràng. Testcontainers giúp chạy broker trong container và phối hợp với Toxiproxy để tạo lỗi mạng.

Nếu ứng dụng dùng Kafka binder và muốn dùng embedded broker, hãy bảo đảm test binder không thay thế Kafka binder trong test đó. Spring Kafka lưu ý rằng dependency test support của Spring Cloud Stream có thể tự chọn Test Binder; test dùng broker thật cần loại trừ cấu hình Test Binder tương ứng.

Ví dụ khung integration test dùng Kafka container:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;

@Testcontainers
@SpringBootTest(properties = {
        "spring.autoconfigure.exclude="
                + "org.springframework.cloud.stream.test.binder.TestSupportBinderAutoConfiguration"
})
class KafkaBinderRecoveryIT {

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @DynamicPropertySource
    static void brokerProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.stream.kafka.binder.brokers",
                kafka::getBootstrapServers);
    }

    @Test
    void brokerIsAvailableForTheApplication() {
        // Gửi và nhận message qua binding thật; các bài test khác
        // điều khiển restart hoặc network fault.
    }
}
~~~

Đây là khung kiểm thử; phiên bản image Kafka, API Testcontainers và thuộc tính binder phải khớp dependency của dự án. Test này dùng Kafka binder thật, không dùng Test Binder trong cùng context.

## 5. Đặt consumer group hoặc subscription ổn định

Khả năng tiếp tục sau restart phụ thuộc vào danh tính consumer:

| Broker | Danh tính cần giữ ổn định | Điều cần kiểm tra |
|---|---|---|
| Kafka | Consumer group | Offset đã commit được tiếp tục dùng sau khi instance mới tham gia |
| RabbitMQ | Queue và binding của group | Queue durable còn tồn tại và message chưa ack được giao lại |
| Pulsar | Subscription name | Subscription cursor và kiểu subscription được giữ qua lần reconnect |

Với Kafka, khai báo group rõ ràng:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
~~~

Khi ứng dụng khởi động lại với cùng group, consumer tiếp tục từ offset đã commit theo cấu hình. Thuộc tính start-offset như earliest thường chỉ quyết định vị trí bắt đầu cho group mới chưa có offset; nó không có nghĩa là mỗi lần restart đều đọc lại từ đầu. Không thay group ID giữa các lần triển khai nếu mục tiêu là tiếp tục tiến độ đã lưu.

Với RabbitMQ, queue dùng cho consumer group phải có vòng đời phù hợp. Queue tạm hoặc auto-delete có thể biến mất khi consumer ngắt kết nối, làm thay đổi cách message được giữ lại. Với Pulsar, subscription name cần ổn định để cursor được tiếp tục thay vì tạo subscription mới không liên quan.

## 6. Kiểm thử ứng dụng khởi động lại

Kịch bản restart ứng dụng nên kiểm tra cả message đã hoàn tất và message đang xử lý:

1. Khởi động producer và consumer với group/subscription cố định.
2. Gửi một tập message có ID duy nhất, ví dụ EVT-001 đến EVT-020.
3. Chờ một phần message được xử lý và xác nhận kết quả đã ghi bền vững.
4. Dừng consumer có chủ đích; với kịch bản crash, kết thúc tiến trình đột ngột thay vì đóng context theo cách graceful.
5. Trong thời gian consumer dừng, tiếp tục gửi thêm message.
6. Khởi động consumer với cùng cấu hình và cùng group/subscription.
7. Chờ backlog được xử lý.
8. Xác nhận tất cả message cần xử lý đã có kết quả và không có tác động phụ trùng lặp ngoài ý muốn.

Graceful shutdown và crash là hai tình huống khác nhau. Khi graceful shutdown, listener container có thể dừng nhận message, hoàn tất công việc đang chạy và commit offset/ack theo cấu hình. Khi tiến trình bị kill, bản tin đang xử lý có thể chưa được xác nhận và được giao lại.

Nên có ít nhất hai test riêng:

- **Graceful restart:** xác nhận ứng dụng dừng có kiểm soát và tiếp tục từ vị trí đã lưu.
- **Abrupt termination:** xác nhận message chưa được xác nhận được giao lại và ứng dụng xử lý an toàn khi có duplicate.

## 7. Kiểm thử broker restart và reconnect

Broker restart khác application restart. Trong bài test này, giữ ứng dụng đang chạy, dừng broker hoặc làm broker mất khả năng nhận kết nối, sau đó khởi động broker lại.

Các bước cơ bản:

1. Khởi động broker và ứng dụng.
2. Xác nhận producer và consumer đã kết nối.
3. Gửi một message nền để xác nhận đường đi bình thường.
4. Dừng broker hoặc tạm ngắt đường mạng giữa ứng dụng và broker.
5. Trong thời gian gián đoạn, thử gửi và quan sát lỗi theo semantics của producer.
6. Khôi phục broker hoặc kết nối.
7. Chờ client reconnect và consumer group/queue/subscription hoạt động lại.
8. Gửi message kiểm tra mới.
9. Xác nhận message được nhận, xử lý và lưu kết quả.
10. Đối chiếu message đã gửi trong thời gian broker gián đoạn để xác định message nào được retry, message nào cần ứng dụng gửi lại.

Không mặc định producer sẽ giữ mọi message trong bộ nhớ vô thời hạn khi broker ngừng hoạt động. Kết quả phụ thuộc timeout, retry, buffer, binder và API gửi. Ứng dụng phải xử lý lỗi send và quyết định có lưu outbox hoặc retry ở tầng nghiệp vụ hay không.

Với Kafka nhiều broker, một broker đơn lẻ trong Testcontainers không mô phỏng đầy đủ leader election, replica ISR hoặc mất quorum. Nếu yêu cầu phục hồi liên quan đến replication, hãy chạy cluster thử nghiệm nhiều broker và dừng broker đang giữ partition leader để xác nhận client chuyển sang leader mới.

## 8. Mô phỏng lỗi mạng bằng Toxiproxy

Testcontainers Toxiproxy tạo TCP proxy ở giữa ứng dụng và broker. Test có thể thêm độ trễ, giới hạn băng thông hoặc cắt kết nối để kiểm tra reconnect và timeout.

Một topology thử nghiệm có thể gồm:

~~~text
Spring Cloud Stream application
             |
             v
         Toxiproxy
             |
             v
       Kafka / RabbitMQ / Pulsar
~~~

Testcontainers cho phép tạo proxy đến broker trong cùng Docker network. Ví dụ API điều khiển proxy có thể tạo một proxy tên kafka, lắng nghe tại cổng thử nghiệm và forward đến địa chỉ broker nội bộ. Sau đó cấu hình ứng dụng kết nối qua địa chỉ proxy thay vì kết nối thẳng đến broker.

Các kiểu lỗi hữu ích:

| Lỗi mạng | Mục đích |
|---|---|
| Cắt cả hai chiều TCP | Mô phỏng mất kết nối đột ngột |
| Chỉ cắt chiều upstream | Kiểm tra producer/client không gửi được dữ liệu |
| Chỉ cắt chiều downstream | Kiểm tra client không nhận được phản hồi hoặc acknowledgement |
| Thêm latency và jitter | Kiểm tra timeout và backoff |
| Giới hạn bandwidth | Kiểm tra backlog, throughput và thời gian phục hồi |
| Đóng socket chậm | Kiểm tra xử lý kết nối bị treo hoặc đóng muộn |

Ví dụ ý tưởng điều khiển Toxiproxy:

~~~java
// Proxy đã được tạo và đang chuyển tiếp đến broker.
proxy.toxics().bandwidth(
        "cut-upstream",
        ToxicDirection.UPSTREAM,
        0);

proxy.toxics().bandwidth(
        "cut-downstream",
        ToxicDirection.DOWNSTREAM,
        0);

// Sau khi xác nhận ứng dụng nhận biết sự cố, gỡ hai toxic.
proxy.toxics().get("cut-upstream").remove();
proxy.toxics().get("cut-downstream").remove();
~~~

Đoạn mã minh họa API Toxiproxy; cần tạo container, network, proxy và địa chỉ broker trước khi dùng. Khi cắt kết nối, kiểm thử phải chờ đến khi ứng dụng quan sát được lỗi; sau khi gỡ toxic, kiểm tra client có kết nối lại và xử lý message mới.

Toxiproxy kiểm tra lỗi TCP. Nó không mô phỏng mọi lỗi DNS, TLS certificate, xác thực broker, lỗi logic của broker hoặc lỗi phân vùng mạng ở tầng ứng dụng. Những trường hợp đó cần test riêng nếu có trong threat model.

## 9. Phân biệt lỗi nghiệp vụ với lỗi kết nối

Lỗi nghiệp vụ xảy ra khi message đã đến ứng dụng nhưng Function/Consumer không xử lý được, ví dụ dữ liệu sai schema hoặc không thỏa quy tắc. Lỗi kết nối xảy ra khi client không thể giao tiếp với broker hoặc không nhận được phản hồi đúng hạn.

| Loại lỗi | Ví dụ | Hành vi cần xác minh |
|---|---|---|
| Lỗi nghiệp vụ tạm thời | Database timeout, API phụ trợ tạm ngừng | Retry theo backoff và giới hạn |
| Lỗi nghiệp vụ không thể phục hồi | Payload sai định dạng, thiếu trường bắt buộc | Đưa vào DLQ hoặc luồng lỗi, tránh retry vô hạn |
| Lỗi broker | Broker restart, leader chuyển đổi | Client reconnect, producer/consumer tiếp tục theo cấu hình |
| Lỗi mạng | TCP reset, timeout, mất route | Timeout hữu hạn, reconnect và phục hồi |
| Lỗi xác thực | Credential hết hạn hoặc sai | Báo lỗi rõ ràng; không retry vô hạn như lỗi tạm thời |
| Lỗi schema | Producer và consumer không tương thích | Không lặp vô hạn cùng một payload không thể giải mã |

Một lỗi mạng có thể xảy ra sau khi broker đã nhận message nhưng trước khi producer nhận acknowledgement. Trong tình huống đó, producer không biết chắc broker đã lưu message hay chưa. Retry ở tầng ứng dụng có thể tạo duplicate. Đây là lý do cần event ID ổn định và consumer idempotent.

## 10. Xác nhận offset và acknowledgement đúng thời điểm

Kiểm thử phục hồi phải xác minh thời điểm message được xác nhận:

- Kafka: offset chỉ được commit theo acknowledgement mode, transaction hoặc cấu hình container. Nếu xử lý xong side effect nhưng tiến trình dừng trước khi commit offset, message có thể được giao lại.
- RabbitMQ: message chưa được ack có thể được requeue/redeliver khi consumer hoặc connection mất. Cần kiểm tra queue durable, acknowledgement mode và cấu hình reject/requeue/DLQ.
- Pulsar: acknowledgement mode có thể là BATCH, RECORD hoặc MANUAL trong Spring for Apache Pulsar. Redelivery phụ thuộc ack timeout, nack và subscription type.

Không nên kiểm tra chỉ bằng số lần Function được gọi. Hãy đối chiếu message ID, số bản ghi nghiệp vụ đã tạo, offset/ack state và trạng thái DLQ.

Với Kafka, có thể đọc offset group bằng công cụ quản trị hoặc Admin API trong integration test. Với RabbitMQ, kiểm tra queue depth, unacked và dead-letter queue. Với Pulsar, kiểm tra subscription backlog và redelivery/DLQ.

## 11. Kiểm thử cửa sổ duplicate khi ứng dụng crash

Một cửa sổ lỗi quan trọng xuất hiện khi side effect đã hoàn tất nhưng acknowledgement chưa được lưu:

~~~text
Consumer nhận EVT-100
        |
        v
Ghi kết quả nghiệp vụ vào database
        |
        v
Tiến trình bị dừng trước khi ack/commit
        |
        v
Broker giao lại EVT-100
        |
        v
Consumer chạy lại cùng nghiệp vụ
~~~

Nếu consumer không idempotent, database có thể ghi hai lần, thanh toán có thể bị trừ hai lần hoặc một email có thể được gửi lặp.

Một cách bảo vệ phổ biến là lưu event ID trong bảng deduplication cùng transaction với thay đổi nghiệp vụ:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Ví dụ xử lý theo PostgreSQL:

~~~java
record OrderCreated(String eventId, String orderId) {}

// Phương thức nằm trong service đã inject jdbcTemplate và orderRepository.
@Transactional
public void handle(OrderCreated event) {
    int inserted = jdbcTemplate.update("""
            INSERT INTO processed_events(event_id, processed_at)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT (event_id) DO NOTHING
            """, event.eventId());

    if (inserted == 0) {
        return;
    }

    orderRepository.apply(event);
}
~~~

Nếu event ID đã tồn tại, handler bỏ qua side effect đã hoàn tất. Vì insert dedup và cập nhật nghiệp vụ nằm trong cùng transaction database, tiến trình crash giữa hai thao tác sẽ rollback cả hai; lần giao lại có thể xử lý lại an toàn.

Ví dụ trên giả định database hỗ trợ cú pháp PostgreSQL và các thao tác dùng chung transaction manager. Nếu side effect nằm ở hệ thống ngoài, cần idempotency key hoặc quy trình outbox/inbox tương ứng; một transaction database không tự bao phủ HTTP API hoặc hệ thống thanh toán.

## 12. Kiểm thử retry và DLQ sau sự cố

Sau khi broker hoặc dependency trở lại, một message lỗi nghiệp vụ có thể vẫn cần retry hoặc chuyển DLQ. Kiểm thử phải phân biệt lỗi tạm thời được phục hồi và poison message không thể xử lý.

Ví dụ cấu hình consumer Kafka có group, retry và DLQ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 5000
            back-off-multiplier: 2
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.events.order-processor.dlq
~~~

Với Kafka binder, DLQ cần consumer group rõ ràng. Khi retry hết mà handler vẫn lỗi, record được gửi vào DLQ theo cấu hình. Lỗi broker/network và lỗi do Function ném exception không nhất thiết đi qua cùng một retry mechanism; cần kiểm tra hành vi client reconnect riêng với binder retry của message handler.

Với RabbitMQ binder, có thể dùng autoBindDlq, maxAttempts, republishToDlq hoặc dead-letter exchange/queue theo nhu cầu. Cần tránh cấu hình requeue vô hạn cho poison message vì nó có thể tạo vòng lặp redelivery liên tục.

Với Pulsar, acknowledgement timeout hoặc negative acknowledgement có thể kích hoạt redelivery. Dead-letter topic native của Pulsar có giới hạn theo subscription type; tài liệu Spring for Apache Pulsar mô tả DLQ native cho Shared subscription. Hãy kiểm tra đúng semantics của binder/client đang dùng trước khi khẳng định mọi subscription có cùng hành vi.

Một test DLQ tốt cần xác nhận:

1. Message lỗi được giao đúng số lần thử.
2. Message được chuyển đến đúng DLQ sau khi hết retry.
3. Metadata nguồn và thông tin lỗi được giữ đủ để điều tra.
4. Consumer chính vẫn tiếp tục xử lý message kế tiếp nếu chính sách cho phép.
5. Redrive từ DLQ không tạo side effect trùng lặp.

## 13. Kiểm thử RabbitMQ reconnect và redelivery

Spring AMQP listener container có khả năng khởi động lại consumer khi connection bị mất. Nếu broker không sẵn sàng khi container khởi động, container có thể tiếp tục thử kết nối theo recovery backoff.

Kịch bản RabbitMQ:

- Gửi message vào queue durable trước khi dừng consumer.
- Dừng RabbitMQ hoặc cắt TCP proxy.
- Xác nhận producer/consumer nhận lỗi kết nối theo cấu hình.
- Khởi động lại broker hoặc gỡ network fault.
- Xác nhận listener container tạo lại consumer.
- Xác nhận message chưa ack được giao lại.
- Kiểm tra header redelivered hoặc metadata delivery để phân biệt lần giao lại.
- Xác nhận queue và DLQ còn tồn tại sau broker restart.

Nếu queue là auto-delete hoặc exclusive, hành vi sau khi connection mất có thể khác queue durable. Kiểm thử cần dùng đúng loại queue mà production triển khai.

## 14. Kiểm thử Pulsar acknowledgement và redelivery

Với Spring for Apache Pulsar, chế độ ack ảnh hưởng trực tiếp đến cách message được xác nhận:

Các semantics dưới đây là của Spring for Apache Pulsar. Nếu ứng dụng dùng một Pulsar binder riêng cho Spring Cloud Stream, hãy kiểm tra binder đó ánh xạ acknowledgement và redelivery sang Pulsar client như thế nào ở đúng phiên bản đang triển khai.

| Ack mode | Hành vi cần kiểm tra |
|---|---|
| BATCH | Các message trong batch được ack khi batch xử lý thành công; lỗi có thể khiến message lỗi bị nack |
| RECORD | Ack hoặc nack theo từng record trong chế độ single-record |
| MANUAL | Ứng dụng tự gọi acknowledge hoặc nack; phải kiểm thử mọi nhánh exception |

Một consumer crash trước khi ack có thể khiến message được giao lại. Ack timeout lớn hơn 0 cũng có thể làm message chưa ack được redeliver. Khi dùng negative acknowledgement, delay/backoff quyết định thời điểm giao lại.

Với batch listener, cần đặc biệt kiểm tra cách xử lý một record lỗi trong batch. Không giả định RECORD ack mode có thể dùng cho mọi batch listener; API và giới hạn phụ thuộc Spring Pulsar version.

## 15. Kiểm thử backlog và tốc độ phục hồi

Sau một sự cố kéo dài, consumer có thể phải xử lý backlog lớn. Chỉ xác nhận một message mới được nhận là chưa đủ.

Hãy tạo backlog có kích thước xác định, ví dụ 5.000 event với ID duy nhất:

1. Tạm dừng consumer hoặc cắt kết nối.
2. Gửi backlog vào broker.
3. Khôi phục consumer.
4. Đo thời gian từ lúc reconnect đến khi nhận message đầu tiên.
5. Đo tốc độ tiêu thụ và thời gian backlog về 0.
6. Theo dõi consumer lag, queue depth hoặc subscription backlog.
7. Xác nhận số event nghiệp vụ duy nhất bằng số event kỳ vọng.

Đặt ngưỡng phục hồi dựa trên SLO thực tế. Không đặt timeout test quá ngắn khiến test flake khi CI chậm, nhưng cũng không dùng timeout vô hạn che giấu consumer không reconnect.

## 16. Ma trận kịch bản nên có

| Kịch bản | Cách tạo lỗi | Kết quả cần xác nhận |
|---|---|---|
| Consumer graceful restart | Dừng context/tiến trình có kiểm soát | Consumer trở lại cùng group/subscription và tiếp tục tiến độ |
| Consumer crash giữa xử lý | Kill tiến trình sau side effect, trước ack/commit | Message được giao lại; idempotency ngăn duplicate side effect |
| Broker restart | Dừng rồi khởi động broker | Client reconnect; queue/topic/subscription và dữ liệu bền vững còn đúng |
| TCP connection reset | Cắt proxy hai chiều | Client phát hiện lỗi và kết nối lại |
| Network blackhole | Giữ kết nối không truyền dữ liệu | Timeout xảy ra theo giới hạn; sau đó phục hồi |
| Latency cao | Thêm độ trễ/jitter | Timeout/backoff không tạo retry storm |
| Dependency tạm ngừng | Làm API/database phụ trợ trả lỗi | Retry có giới hạn; xử lý lại thành công khi dependency trở lại |
| Poison message | Gửi payload không hợp lệ | Retry hữu hạn rồi DLQ/luồng lỗi |
| Consumer scale up/down | Thay số instance | Rebalance/assignment không làm mất message |
| Backlog lớn | Tạo nhiều message khi consumer dừng | Backlog được xử lý hết trong SLO |
| DLQ redrive | Phát lại một message đã sửa | Event được xử lý đúng và không lặp side effect |

Không cần chạy mọi kịch bản trên mọi pull request. Có thể chạy unit/Test Binder thường xuyên, integration broker trên CI, còn chaos test dài hoặc cluster nhiều broker theo lịch hoặc trước release quan trọng.

## 17. Dùng Awaitility để chờ điều kiện thay vì sleep cố định

Trong integration test, thời gian reconnect phụ thuộc broker, container runtime và CI. Thay vì ngủ cố định rồi giả định ứng dụng đã phục hồi, hãy chờ một điều kiện quan sát được với timeout:

~~~java
import static org.awaitility.Awaitility.await;
import static java.util.concurrent.TimeUnit.SECONDS;

await()
        .atMost(30, SECONDS)
        .pollInterval(200, java.util.concurrent.TimeUnit.MILLISECONDS)
        .untilAsserted(() -> {
            assertThat(orderRepository.countByEventId("EVT-200"))
                    .isEqualTo(1);
        });
~~~

Điều kiện chờ nên là kết quả nghiệp vụ hoặc trạng thái broker có ý nghĩa, không chỉ là một log text. Nếu test hết timeout, in thêm thông tin consumer group/offset, queue depth, DLQ depth và trạng thái container để điều tra.

## 18. Những lỗi làm test phục hồi không đáng tin cậy

- Dùng Test Binder rồi kết luận ứng dụng reconnect được với Kafka hoặc RabbitMQ.
- Dùng consumer group ngẫu nhiên ở mỗi lần khởi động nên test vô tình đọc lại toàn bộ topic.
- Dùng topic/queue dùng chung giữa test, khiến message cũ làm sai kết quả.
- Chỉ đếm số lần handler chạy mà không kiểm tra side effect và duplicate.
- Dùng một Kafka broker đơn lẻ để kết luận cluster replication/leader election hoạt động đúng.
- Cắt mạng nhưng không chờ client phát hiện lỗi trước khi khôi phục.
- Dùng Thread.sleep cố định thay cho chờ điều kiện.
- Retry vô hạn khiến test treo hoặc poison message chiếm consumer.
- Không kiểm tra DLQ hoặc backlog sau khi test kết thúc.
- Không cô lập dữ liệu và không dọn queue/topic/subscription, khiến test sau nhận message cũ.
- Chỉ kiểm tra graceful shutdown, bỏ qua crash đột ngột khi message đang xử lý.

## 19. Quan sát sau khi phục hồi

Để biết ứng dụng đã phục hồi thực sự, cần theo dõi:

- Trạng thái kết nối producer và consumer.
- Số lần reconnect và thời gian từ lỗi đến khi kết nối lại.
- Consumer lag, queue depth hoặc subscription backlog.
- Offset commit hoặc acknowledgement rate.
- Số lần redelivery và retry.
- Số message đi vào DLQ.
- Tỷ lệ event ID trùng lặp bị idempotency bỏ qua.
- Tốc độ xử lý backlog sau sự cố.
- Lỗi xác thực, TLS, serialization và provisioning.

Log nên có event ID, destination/topic, group/subscription, attempt number và correlation ID. Không ghi payload nhạy cảm. Metric cần phân biệt lỗi broker với lỗi nghiệp vụ để người vận hành không nhầm một đợt network outage với một đợt poison message.

## 20. Checklist trước khi phát hành

- Test Binder đã xác nhận logic Supplier/Function/Consumer và binding.
- Integration test dùng broker thật cho đường gửi/nhận quan trọng.
- Consumer group, queue hoặc subscription có danh tính ổn định.
- Có test graceful restart và abrupt termination.
- Có test broker restart hoặc kết nối bị cắt.
- Có test latency/timeout và reconnect.
- Đã kiểm tra offset/ack chỉ được lưu đúng theo semantics mong muốn.
- Side effect quan trọng có idempotency hoặc inbox/deduplication.
- Retry có giới hạn và poison message có đường DLQ/luồng lỗi.
- Đã kiểm tra redrive và tránh lặp side effect.
- Backlog được xử lý lại trong thời gian SLO.
- Test cô lập topic/queue/subscription và dọn dữ liệu sau khi chạy.
- Log, metric và alert cho reconnect, lag, redelivery và DLQ đã có.

Kiểm thử khởi động lại, lỗi mạng và phục hồi sau sự cố phải xác nhận cả khả năng kết nối lại lẫn kết quả nghiệp vụ sau khi message được giao lại. Test Binder giúp kiểm tra logic trong JVM; broker container và Toxiproxy giúp kiểm tra broker, offset/ack, reconnect và network fault. Vì các binder Kafka, RabbitMQ và Pulsar có semantics khác nhau, cần kiểm thử đúng group, queue hoặc subscription, xác nhận retry/DLQ và thiết kế consumer idempotent cho cửa sổ crash sau side effect nhưng trước acknowledgement.

## Tài liệu tham khảo

- [Spring Cloud Stream — Testing with the Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka — Listener Container and Offset Commits](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring AMQP — Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/4.0/amqp/resilience-recovering-from-errors-and-broker-failures.html)
- [Spring Cloud Stream — Kafka Retry and DLQ](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/retry-dlq.html)
- [Spring Cloud Stream — RabbitMQ Binder DLQ and Retry](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/overview.html)
- [Spring for Apache Pulsar — Message Acknowledgment and Redelivery](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Testcontainers — Toxiproxy Module](https://java.testcontainers.org/modules/toxiproxy/)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)
- [Testcontainers — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/)
- [Testcontainers — Apache Pulsar Module](https://java.testcontainers.org/modules/pulsar/)
