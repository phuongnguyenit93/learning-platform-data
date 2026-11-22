# Quan sát listener, truyền ngữ cảnh và kiểm thử tích hợp Spring

## Mục tiêu bài học

Một ứng dụng Spring Kafka có thể nhận record thành công nhưng vẫn khó vận hành nếu không biết listener nào đang chạy, đang xử lý topic/partition nào, mất bao lâu để xử lý, lỗi xảy ra ở đâu hoặc một request nghiệp vụ đã đi qua những dịch vụ nào. Observability giúp nối log, metrics và distributed tracing để giải thích hành vi của listener trong môi trường thật.

Khi xử lý bất đồng bộ, context của request như trace ID, correlation ID và thông tin tenant cũng cần được truyền qua Kafka headers hoặc qua executor. Nếu chỉ dựa vào ThreadLocal/MDC, context có thể mất khi chuyển thread. Integration test cần chạy producer, broker và listener cùng nhau để xác minh serialization, headers, acknowledgment, retry và luồng xử lý thực tế.

Bài học hướng dẫn cấu hình quan sát listener bằng Micrometer Observation, theo dõi container và consumer metrics, truyền trace/correlation context, viết integration test với Embedded Kafka và kiểm tra các tình huống lỗi. Các ví dụ dùng Spring Kafka hiện đại; một số API phụ thuộc phiên bản Spring Kafka, Spring Boot và Micrometer của dự án.

Sau bài học, người học có thể:

- Theo dõi vòng đời listener container và trạng thái partition assignment.
- Bật Micrometer Observation cho listener container và KafkaTemplate.
- Phân biệt metrics, logs, traces và business correlation ID.
- Truyền trace context qua Kafka headers và context qua executor.
- Ghi log có cấu trúc mà không làm lộ payload hoặc dữ liệu nhạy cảm.
- Viết integration test cho producer và @KafkaListener bằng Embedded Kafka.
- Kiểm tra retry, dead-letter topic, headers, commit và rebalance trong test.
- Chọn khi nào cần Embedded Kafka và khi nào cần Testcontainers.

## 1. Observability trong Spring Kafka

Observability là khả năng suy luận trạng thái bên trong hệ thống từ tín hiệu mà ứng dụng phát ra. Với Kafka listener, cần quan sát cả hoạt động của client, container, broker và xử lý nghiệp vụ.

Ba tín hiệu chính:

| Tín hiệu | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Metrics | Hệ thống đang hoạt động nhanh/chậm và có xu hướng gì? | Listener duration, consumer lag, rebalance count |
| Logs | Một lần xử lý cụ thể đã xảy ra điều gì? | Event ID, topic, partition, offset, exception |
| Traces | Một request đi qua các dịch vụ và Kafka như thế nào? | HTTP request → publish Kafka → consume → database |

Không tín hiệu nào thay thế hoàn toàn hai tín hiệu còn lại. Metrics cho thấy xu hướng, logs giải thích chi tiết một sự kiện và traces cho thấy quan hệ nhân quả qua nhiều thành phần.

~~~mermaid
flowchart LR
    A[HTTP request] --> B[Spring service]
    B --> C[KafkaTemplate]
    C --> D[Kafka topic]
    D --> E[@KafkaListener]
    E --> F[Database / downstream]
    B -.-> G[Metrics, logs, trace]
    C -.-> G
    E -.-> G
    F -.-> G
~~~

Mục tiêu là có thể tìm một event theo ID, xác định producer đã gửi đến topic/partition nào, consumer nào nhận, listener xử lý mất bao lâu và lỗi phát sinh ở bước nào.

## 2. Theo dõi listener container

Spring Kafka quản lý listener thông qua listener container. Với @KafkaListener, Spring đăng ký endpoint và tạo container để quản lý KafkaConsumer, vòng poll, listener invocation, acknowledgment, error handler và lifecycle.

Các trạng thái cần quan sát:

- Container đã start hay chưa.
- Consumer đã join group và được gán partition nào.
- Container đang chạy, pause hay stop.
- Listener có liên tục bị lỗi hoặc retry không.
- Rebalance có xảy ra thường xuyên không.
- Consumer lag có tăng liên tục không.

### 2.1. Đặt ID cho listener

Đặt ID ổn định cho từng listener giúp tra cứu container và log dễ hơn:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "order-projection"
)
public void consume(String payload) {
    orderService.process(payload);
}
~~~

ID listener là định danh endpoint trong Spring application. Nó không thay thế group ID, client ID hoặc Kafka transactional ID.

### 2.2. Quan sát qua KafkaListenerEndpointRegistry

Spring cung cấp KafkaListenerEndpointRegistry để truy cập các listener container được đăng ký bởi @KafkaListener:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class ListenerStatusReporter {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerStatusReporter(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void report(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        if (container == null) {
            System.out.println("Listener not registered: " + listenerId);
            return;
        }

        System.out.printf(
            "listener=%s running=%s assigned=%s%n",
            listenerId,
            container.isRunning(),
            container.getAssignedPartitions()
        );
    }
}
~~~

getAssignedPartitions() có thể trả về null khi container chưa được gán partition hoặc chưa khởi động. Đây là thông tin trạng thái runtime; không nên coi null là lỗi ứng dụng nếu listener chưa join group.

Container registry cũng hỗ trợ start/stop/pause/resume trong các tình huống vận hành. Các thao tác này cần được kiểm soát bằng quyền quản trị và audit log; không nên phơi bày endpoint công khai cho phép người dùng tùy ý dừng consumer.

### 2.3. Phân biệt container và consumer

Một ConcurrentMessageListenerContainer có thể quản lý nhiều child KafkaMessageListenerContainer theo concurrency. Mỗi child thường có một KafkaConsumer riêng. Vì vậy:

- Container chính biểu diễn listener endpoint.
- Child container đại diện các consumer thread.
- Một partition tại một thời điểm chỉ được gán cho một consumer trong cùng group.
- Concurrency cao hơn số partition có thể tạo thread consumer không được gán partition.

Khi quan sát assignment, cần xem cả listener ID, group ID, client ID và partition để tránh nhầm container với một KafkaConsumer đơn lẻ.

## 3. Bật Micrometer Observation

Spring Kafka hỗ trợ Micrometer Observation cho producer và listener container. Observation có thể tạo timer/metrics và span tracing khi ứng dụng có ObservationRegistry cùng tracing bridge phù hợp.

Observation API cho Kafka listener và KafkaTemplate có trong các phiên bản Spring Kafka hiện đại (3.x). Với Spring Kafka 2.x, cơ chế Micrometer metrics cũ và API cấu hình có thể khác; không sao chép nguyên các setter Observation vào dự án 2.x. Hãy kiểm tra phiên bản dependency được Spring Boot quản lý.

Các dependency thường dùng trong Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>context-propagation</artifactId>
</dependency>
~~~

Có thể chọn tracing bridge khác nếu nền tảng sử dụng Brave. Không cần thêm đồng thời nhiều tracing bridge cho cùng một ứng dụng.

### 3.1. Bật observation trên listener container

Với factory tự cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import io.micrometer.observation.ObservationRegistry;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String> ordersListenerFactory(
            ConsumerFactory<String, String> consumerFactory,
            ObservationRegistry observationRegistry) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);

        var containerProperties = factory.getContainerProperties();
        containerProperties.setObservationEnabled(true);
        containerProperties.setObservationRegistry(observationRegistry);

        return factory;
    }
}
~~~

Gắn factory vào listener:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    containerFactory = "ordersListenerFactory"
)
public void consume(String payload) {
    orderService.process(payload);
}
~~~

Nếu dùng Spring Boot auto-configuration, có thể tùy biến factory được Boot tạo thay vì khai báo factory mới. Tránh vô tình bỏ các cấu hình mặc định như error handler, converter, transaction manager hoặc common properties khi tự tạo factory.

### 3.2. Bật observation cho KafkaTemplate

Producer observation giúp theo dõi lần gửi từ ứng dụng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import io.micrometer.observation.ObservationRegistry;

@Configuration
public class KafkaProducerObservationConfiguration {

    public KafkaProducerObservationConfiguration(
            KafkaTemplate<String, String> kafkaTemplate,
            ObservationRegistry observationRegistry) {

        kafkaTemplate.setObservationEnabled(true);
        kafkaTemplate.setObservationRegistry(observationRegistry);
    }
}
~~~

Khi observation được bật và tracing bridge được cấu hình, producer/consumer instrumentation có thể tạo span và truyền trace context qua Kafka headers. Tên observation, convention và tags có thể khác theo phiên bản Spring Kafka; hãy xác nhận trên dependency đang dùng.

### 3.3. Không bật observation nhưng thiếu registry/exporter

Observation tạo tín hiệu trong ứng dụng, nhưng để xem dashboard hoặc trace ở hệ thống tập trung còn cần:

- ObservationRegistry được cấu hình.
- MeterRegistry/exporter cho metrics.
- Tracing bridge và exporter cho spans nếu cần distributed tracing.
- Collector/backend như Prometheus, OTLP collector hoặc tracing backend.
- Sampling policy phù hợp để kiểm soát chi phí.

Nếu chỉ bật observation mà chưa cấu hình exporter, dữ liệu có thể không xuất hiện ở dashboard hoặc tracing backend.

Với Spring Boot có hỗ trợ các thuộc tính này, có thể bật observation bằng YAML thay vì gọi setter thủ công:

~~~yaml
spring:
  kafka:
    listener:
      observation-enabled: true
    template:
      observation-enabled: true
~~~

Chọn một nơi cấu hình làm nguồn chính để tránh khó xác định giá trị cuối cùng khi vừa dùng YAML vừa tùy biến bean. Khi observation được bật, Spring Kafka dùng observation để quản lý timer và không duy trì các Micrometer timer listener riêng như chế độ metrics cũ. Nếu cần metric listener, hãy xem timer được tạo từ observation và convention đang áp dụng.

## 4. Metrics cần theo dõi

### 4.1. Listener metrics

Theo dõi các chỉ số tổng quát:

| Metric/nhóm metric | Ý nghĩa | Khi nào cần chú ý |
|---|---|---|
| Listener duration | Thời gian xử lý listener | p95/p99 tăng bất thường |
| Listener success/error count | Số lần xử lý thành công/thất bại | Error rate tăng |
| Retry/recovery count | Số lần retry và recover | Retry tăng liên tục hoặc DLT tăng |
| Container running/paused | Trạng thái container | Container dừng ngoài kế hoạch |
| Assigned partitions | Số partition đang được gán | Assignment bằng 0 ngoài dự kiến |
| Rebalance count/latency | Số lần và thời gian rebalance | Rebalance xảy ra liên tục |

Tên metric cụ thể phụ thuộc Spring Kafka, Micrometer và cấu hình observation. Không hard-code tên metric trước khi kiểm tra endpoint /actuator/metrics hoặc registry đang export.

Với observation mặc định của Spring Kafka 3.x, các timer thường có tên spring.kafka.listener cho listener container và spring.kafka.template cho KafkaTemplate. Tag mặc định gồm thông tin định danh listener hoặc bean template; custom convention có thể bổ sung tag. Hãy kiểm tra tên và tag thực tế ở phiên bản dự án.

### 4.2. Kafka consumer metrics

Kafka client cung cấp các metric về fetch, heartbeat, commit, records và lag. Các metric đáng quan sát:

- records-consumed-rate và records-consumed-total.
- records-lag-max hoặc metric lag do exporter/monitoring stack tổng hợp.
- heartbeat-rate và heartbeat-response-time-max.
- commit-latency-avg và commit-latency-max.
- fetch-latency-avg, fetch-rate và bytes-consumed-rate.
- request-latency-avg và network request errors.

Tên chính xác và cách export có thể khác giữa Kafka client version và JMX exporter. Hãy xác minh MBean/metric thực tế thay vì giả định mọi metric đều được export tự động.

### 4.3. Alert có ý nghĩa vận hành

Một số alert hữu ích:

- Listener error rate vượt ngưỡng trong một khoảng thời gian.
- Consumer lag tăng liên tục hoặc vượt SLA.
- Listener container dừng ngoài kế hoạch.
- Rebalance rate tăng đột biến.
- Heartbeat response chậm hoặc session timeout.
- Retry/DLT rate tăng.
- p95/p99 listener duration vượt ngân sách xử lý.
- Consumer không có partition assignment dù group cần xử lý dữ liệu.

Không tạo alert chỉ dựa trên một lần lỗi đơn lẻ. Dùng cửa sổ thời gian, rate và ngưỡng phù hợp workload để giảm cảnh báo giả.

### 4.4. Tránh metric cardinality cao

Không đưa orderId, customerId, email, requestId hoặc eventId vào metric tag. Mỗi giá trị riêng có thể tạo một time series mới, làm tăng bộ nhớ và chi phí của metrics backend.

Hãy dùng:

- Metric tags có cardinality thấp như topic, listener ID, result hoặc exception type đã chuẩn hóa.
- Trace/span để tìm một request cụ thể.
- Log có cấu trúc để ghi event ID và correlation ID.

Không gắn payload hoặc thông tin định danh cá nhân vào metric, log hay trace baggage nếu không có lý do và chính sách bảo mật rõ ràng.

## 5. Log có cấu trúc cho listener

Log nên chứa đủ thông tin để định vị record mà không phải ghi toàn bộ payload:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventListener.class);

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "order-projection"
    )
    public void consume(ConsumerRecord<String, String> record) {
        log.info(
            "Kafka record received topic={} partition={} offset={} key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key()
        );

        orderService.process(record.value());
    }
}
~~~

Ở production, cân nhắc che hoặc hash key nếu key chứa thông tin nhạy cảm. Log offset cùng topic và partition để định vị record; chỉ offset riêng lẻ không đủ.

### 5.1. Phân biệt log nhận record và log xử lý thành công

Một log trước khi gọi service chỉ chứng minh listener đã nhận record. Nó không chứng minh nghiệp vụ đã commit thành công. Nên ghi event xử lý hoàn tất sau khi service trả về thành công:

~~~java
orderService.process(record.value());

log.info(
    "Order event processed topic={} partition={} offset={}",
    record.topic(),
    record.partition(),
    record.offset()
);
~~~

Nếu service ném exception, log thành công không được phát ra. Error handler có thể retry listener invocation; vì vậy log nhận record có thể xuất hiện nhiều lần cho cùng offset.

## 6. Truyền correlation ID qua Kafka headers

Correlation ID giúp nối log của producer và consumer cho cùng một luồng nghiệp vụ. Đây thường là ID do ứng dụng tạo hoặc nhận từ HTTP request; nó khác trace ID do tracing system quản lý.

### 6.1. Gắn correlation ID khi publish

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String payload, String correlationId) {
        ProducerRecord<String, String> record =
            new ProducerRecord<>("orders", orderId, payload);

        record.headers().add(
            "correlation-id",
            correlationId.getBytes(StandardCharsets.UTF_8)
        );

        kafkaTemplate.send(record);
    }
}
~~~

Nếu correlation ID đến từ HTTP request, nên tạo một ID mới khi không có giá trị hợp lệ. Không tin cậy header từ client bên ngoài nếu nó có thể chứa dữ liệu quá dài hoặc ký tự điều khiển.

### 6.2. Đọc correlation ID trong listener

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.slf4j.MDC;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class CorrelatedOrderListener {

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void consume(ConsumerRecord<String, String> record) {
        Header header = record.headers().lastHeader("correlation-id");
        String correlationId = header == null
            ? "missing"
            : new String(header.value(), StandardCharsets.UTF_8);

        try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("correlationId", correlationId)) {
            process(record.value());
        }
    }
}
~~~

MDC là ThreadLocal gắn với thread hiện tại. Dùng putCloseable hoặc finally để xóa giá trị sau xử lý; nếu không, thread consumer được tái sử dụng có thể mang correlation ID của record trước sang record tiếp theo.

Correlation ID phục vụ tìm kiếm log. Không nên dùng nó làm metric tag vì mỗi request thường có giá trị khác nhau.

## 7. Truyền distributed tracing context

Trace context mô tả quan hệ giữa các span qua nhiều dịch vụ. Với Micrometer Tracing và Spring Kafka observation được bật, producer observation có thể inject trace context vào Kafka headers; listener observation có thể extract context khi consumer nhận record.

Luồng ví dụ:

~~~mermaid
flowchart LR
    A[HTTP server span] --> B[Service span]
    B --> C[Kafka producer span]
    C -->|trace headers| D[Kafka topic]
    D --> E[Kafka listener span]
    E --> F[Database span]
~~~

Trace context thường dùng W3C Trace Context như traceparent và tracestate. Cấu hình cụ thể phụ thuộc tracing bridge và instrumentation đang dùng.

### 7.1. Không tự tạo trace ID thay cho tracing system

Nếu ứng dụng đã dùng Micrometer Tracing, không tự tạo header traceparent theo format riêng và không ghi đè header tracing do instrumentation quản lý. Hãy để producer/consumer observation thực hiện inject/extract context.

Correlation ID có thể được truyền song song như business header riêng. Trace ID và correlation ID có mục đích khác nhau:

| ID | Mục đích |
|---|---|
| Trace ID | Nối span trong distributed trace |
| Span ID | Định danh một thao tác cụ thể trong trace |
| Correlation ID | Nối log/sự kiện theo nghiệp vụ hoặc request |
| Event ID | Định danh một event cụ thể, ổn định qua retry |

Không gộp các ID này thành một trường nếu hệ thống cần phân biệt request, event và trace.

### 7.2. Context qua executor bất đồng bộ

ThreadLocal/MDC không tự động truyền sang thread khác. Nếu listener chuyển công việc sang executor, trace context hoặc MDC có thể biến mất nếu executor không propagate context.

Với Spring Framework 6.1 trở lên, có thể dùng ContextPropagatingTaskDecorator cùng Micrometer Context Propagation:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncConfiguration {

    @Bean
    ThreadPoolTaskExecutor orderExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("order-worker-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

ContextPropagatingTaskDecorator truyền các context accessor đã đăng ký trong Micrometer Context Propagation. Nó không tự động biến mọi custom ThreadLocal thành context có thể propagate; cần đăng ký accessor phù hợp nếu ứng dụng có context riêng.

Nếu chỉ cần truyền MDC thuần túy, có thể viết TaskDecorator sao chép MDC map khi submit và khôi phục/xóa map trong finally. Không dùng MDC copy như giải pháp thay thế distributed tracing context.

### 7.3. Xử lý bất đồng bộ cần quản lý offset

Không gửi record sang executor rồi để listener trả về thành công ngay nếu công việc nghiệp vụ chưa hoàn tất mà container có thể commit offset. Khi chuyển xử lý bất đồng bộ, cần thiết kế acknowledgment, retry, ordering và shutdown để offset chỉ tiến sau khi xử lý được xác nhận.

Các lựa chọn gồm:

- Xử lý đồng bộ trong listener nếu thời gian xử lý nằm trong poll interval.
- Dùng pause/resume container để điều tiết khi worker queue đầy.
- Dùng manual acknowledgment sau khi công việc hoàn tất, với giới hạn concurrency và thứ tự rõ ràng.
- Dùng mô hình worker riêng với checkpoint bền vững và idempotency.

Context propagation không giải quyết vấn đề commit offset. Đây là hai trách nhiệm riêng.

## 8. Truyền headers khi chuyển tiếp hoặc retry record

Khi ứng dụng consume rồi publish record mới, hãy quyết định header nào cần được giữ:

- Correlation ID để tiếp tục liên kết nghiệp vụ.
- Event ID nếu đây là cùng event được chuyển tiếp theo semantics của hệ thống.
- Trace context nên được instrumentation tạo span mới và inject theo quan hệ trace.
- Header version/schema metadata nếu serializer hoặc integration cần.
- Retry/DLT metadata như original topic, partition, offset và exception headers do framework quản lý.

Không sao chép mù quáng toàn bộ headers giữa các topic. Có header chỉ hợp lệ cho một lần publish hoặc một lần retry cụ thể; duplicate tracing headers hoặc exception headers cũ có thể gây khó hiểu khi debug.

## 9. Cấu hình error handler để quan sát retry và DLT

Observability cần ghi nhận cả lần xử lý lỗi, retry và recovery. Spring Kafka cung cấp DefaultErrorHandler và DeadLetterPublishingRecoverer để cấu hình retry có giới hạn và gửi record không xử lý được sang dead-letter topic.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

        return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1000L, 2L)
        );
    }
}
~~~

Trong ví dụ, FixedBackOff có khoảng chờ một giây và hai lần retry sau lần xử lý đầu tiên. Hãy xác nhận retry semantics theo loại exception và phiên bản Spring Kafka. Một số lỗi có thể được phân loại là fatal/non-retryable hoặc cần cấu hình addNotRetryableExceptions.

Gắn error handler vào factory:

~~~java
factory.setCommonErrorHandler(kafkaErrorHandler);
~~~

Khi dùng Spring Boot auto-configured factory, có thể cấu hình qua factory customizer hoặc khai báo factory riêng. Đừng tạo một factory khác mà vô tình bỏ cấu hình observation hoặc transaction hiện có.

### 9.1. Quan sát DLT

Theo dõi:

- Số record được retry.
- Số record được recover.
- Số record publish sang DLT.
- Topic gốc, partition, offset và exception class.
- Tuổi của record trong DLT.
- Tỷ lệ xử lý thành công sau retry.

Không ghi stack trace đầy đủ hoặc payload nhạy cảm vào metric tags. Log exception có kiểm soát và bảo đảm DLT có retention, ACL, owner và quy trình replay.

## 10. Integration test với Embedded Kafka

Unit test có thể mock KafkaTemplate hoặc service, nhưng không kiểm tra được serialization, broker protocol, listener container, consumer group và header thực tế. Integration test dùng broker thật trong môi trường test giúp xác minh các thành phần phối hợp.

Spring Kafka cung cấp spring-kafka-test với @EmbeddedKafka để chạy broker embedded cho test.

Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Phiên bản spring-kafka-test nên khớp với Spring Kafka mà ứng dụng đang dùng. Spring Boot dependency management thường giúp đồng bộ version.

### 10.1. Tạo listener probe cho test

Probe dùng queue để test thread có thể chờ kết quả listener:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventProbe {

    private final BlockingQueue<String> received =
        new LinkedBlockingQueue<>();

    @KafkaListener(
        id = "ordersIntegrationTestListener",
        topics = "orders-it",
        groupId = "orders-it-group"
    )
    public void listen(String payload) {
        received.offer(payload);
    }

    public String poll(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.poll(timeout, unit);
    }
}
~~~

Trong ứng dụng thực tế, listener gọi service nghiệp vụ. Probe chỉ là test fixture để quan sát listener đã nhận message.

### 10.2. Integration test gửi và nhận record

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;

@SpringBootTest(properties = {
    "spring.kafka.consumer.auto-offset-reset=earliest"
})
@EmbeddedKafka(
    partitions = 1,
    topics = "orders-it",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderKafkaIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    OrderEventProbe probe;

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @BeforeEach
    void waitForListenerAssignment() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersIntegrationTestListener");
        ContainerTestUtils.waitForAssignment(container, 1);
    }

    @Test
    void publishesAndConsumesOrderEvent() throws Exception {
        kafkaTemplate.send(
            "orders-it",
            "order-42",
            "{\"orderId\":\"order-42\",\"status\":\"CREATED\"}"
        ).get(10, TimeUnit.SECONDS);

        String received = probe.poll(10, TimeUnit.SECONDS);

        assertThat(received)
            .isNotNull()
            .contains("\"orderId\":\"order-42\"")
            .contains("\"status\":\"CREATED\"");
    }
}
~~~

spring.kafka.bootstrap-servers được trỏ tới broker embedded qua thuộc tính annotation. Tên thuộc tính và hỗ trợ annotation có thể khác theo Spring Kafka version; kiểm tra API của spring-kafka-test nếu dự án dùng phiên bản cũ.

Test dùng timeout hữu hạn thay cho Thread.sleep cố định. Nếu listener chưa nhận record, test thất bại với timeout rõ ràng thay vì phụ thuộc timing của máy.

### 10.3. Kiểm thử correlation header

Gửi ProducerRecord có header:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, String> record =
    new ProducerRecord<>("orders-it", "order-42", payload);

record.headers().add(
    "correlation-id",
    "corr-it-001".getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record).get(10, TimeUnit.SECONDS);
~~~

Probe có thể đưa cả payload và correlation ID vào queue hoặc một test result object. Test xác nhận consumer đọc đúng header và ứng dụng đưa ID vào log context.

## 11. Kiểm thử retry, lỗi và dead-letter topic

Một integration test cho error handler nên xác minh:

1. Listener nhận record.
2. Lần xử lý đầu ném exception có thể retry.
3. Error handler thực hiện số lần retry đã cấu hình.
4. Sau khi hết retry, recoverer publish record sang DLT.
5. DLT record có thông tin nguồn gốc và exception header phù hợp.
6. Consumer group tiếp tục tiến offset theo acknowledgment/recovery semantics.

Không chỉ kiểm tra số lần gọi mock. Cần xác minh record thực tế xuất hiện trên DLT topic bằng consumer test riêng hoặc test probe.

### 11.1. Tránh test phụ thuộc thứ tự chạy

Mỗi test nên có:

- Topic riêng hoặc topic được reset rõ ràng.
- Group ID riêng nếu test song song.
- Consumer auto offset reset phù hợp.
- Timeout hữu hạn cho send và receive.
- Queue/latch được làm sạch giữa các test.
- Lifecycle broker và Spring context được quản lý nhất quán.

Không để hai test cùng dùng group ID và topic rồi cùng chờ một record; consumer group sẽ chia partition và chỉ một test có thể nhận record đó.

## 12. Embedded Kafka hay Testcontainers?

| Tiêu chí | Embedded Kafka | Testcontainers Kafka |
|---|---|---|
| Khởi tạo | Nhanh, tích hợp trực tiếp với Spring Kafka test | Khởi chạy container Docker |
| Môi trường | Broker embedded trong JVM test | Broker chạy trong container |
| Phù hợp | Kiểm tra listener, producer, serialization, group và retry | Kiểm tra gần môi trường triển khai hơn, networking và cấu hình broker |
| Yêu cầu | Dependency spring-kafka-test | Docker và Testcontainers |
| Giới hạn | Không mô phỏng đầy đủ topology production hoặc nhiều broker | Chậm hơn và phụ thuộc môi trường Docker |

Chọn Embedded Kafka cho phần lớn integration test nhanh ở cấp ứng dụng. Dùng Testcontainers hoặc môi trường Kafka test riêng khi cần kiểm tra nhiều broker, KRaft, TLS/SASL, rack placement hoặc cấu hình gần production.

Embedded Kafka không chứng minh ứng dụng hoạt động đúng với mọi cluster production. Cần có thêm smoke test hoặc staging validation cho cấu hình hạ tầng thực tế.

## 13. Kiểm thử observability

Ngoài kiểm tra payload, integration test có thể xác minh:

- Listener observation được tạo khi message được xử lý.
- Producer và consumer trace có chung trace ID theo cấu hình tracing.
- Correlation ID được giữ trong header.
- Listener error được ghi nhận và retry counter tăng.
- DLT record chứa metadata nguồn gốc.
- Metric tags không chứa event ID hoặc customer ID.

Không nên assert tên metric nội bộ quá chặt nếu tên có thể đổi theo Micrometer/Spring Kafka version. Có thể kiểm tra observation được ghi nhận qua test ObservationRegistry hoặc kiểm tra metric theo convention mà dự án đã chuẩn hóa.

Một kiểm thử trace propagation cần cấu hình tracing bridge và test exporter/in-memory span reporter phù hợp. Chỉ bật observation không đồng nghĩa đã có backend nhận trace.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Listener chạy nhưng không thấy metric | Observation chưa bật hoặc registry/exporter chưa cấu hình | Kiểm tra ContainerProperties, ObservationRegistry và Actuator |
| Producer trace không nối với consumer trace | Tracing bridge thiếu hoặc header propagation bị thay đổi | Kiểm tra producer/consumer observation và Kafka headers |
| MDC có correlation ID sai | ThreadLocal không được dọn sau xử lý | Dùng putCloseable/finally và kiểm tra thread reuse |
| Context mất khi chạy executor | ThreadLocal không được propagate | Dùng ContextPropagatingTaskDecorator hoặc context accessor |
| Integration test timeout | Listener chưa start, sai bootstrap server/topic/group hoặc deserialize lỗi | Kiểm tra broker embedded, listener log và test properties |
| Test nhận record cũ | Topic/group được dùng lại giữa test | Dùng topic/group riêng hoặc dọn fixture |
| Hai test cạnh tranh record | Dùng cùng group ID trên cùng topic | Cô lập group hoặc chạy test tuần tự |
| DLT không có record | Error handler chưa gắn vào container factory hoặc exception không retry/recover như dự kiến | Kiểm tra factory, exception classification và recoverer |
| Metric cardinality tăng liên tục | Gắn event ID hoặc business key vào tag | Chuyển giá trị đó sang log/trace |
| Listener container dừng sau exception | Fatal error, deserialization failure hoặc lifecycle config | Kiểm tra error handler, container state và logs |

## 15. Checklist triển khai

Trước khi đưa listener vào production, kiểm tra:

- Listener có ID và group ID rõ ràng.
- Observation được bật và registry/exporter đã hoạt động.
- Metrics có listener latency, error, retry, lag và rebalance.
- Logs có topic, partition, offset và event/correlation ID phù hợp.
- Trace context được truyền qua Kafka headers.
- Context được propagate đúng nếu listener chuyển sang executor.
- MDC được dọn sau mỗi lần xử lý.
- Không đưa dữ liệu nhạy cảm hoặc high-cardinality ID vào metric tags.
- Error handler có retry/backoff/recovery policy rõ ràng.
- DLT có ACL, retention, monitoring và quy trình replay.
- Integration test xác minh send, consume, headers và lỗi.
- Test cô lập topic/group và không phụ thuộc Thread.sleep.
- Staging/smoke test xác minh cấu hình cluster production-like.

## 16. Bài tập thực hành

### Bài tập 1: Quan sát listener container

1. Tạo một @KafkaListener có ID ordersListener.
2. Dùng KafkaListenerEndpointRegistry lấy container.
3. In running state và assigned partitions.
4. Dừng/restart listener trong môi trường lab.
5. Quan sát thay đổi assignment và consumer group.

### Bài tập 2: Bật Micrometer Observation

1. Thêm Actuator và tracing bridge.
2. Bật observation cho listener container và KafkaTemplate.
3. Gửi một record và kiểm tra metrics.
4. Kiểm tra trace producer và consumer.
5. Tắt observation rồi so sánh tín hiệu quan sát.

### Bài tập 3: Truyền correlation ID

1. Gửi ProducerRecord có header correlation-id.
2. Đọc header trong listener.
3. Đưa ID vào MDC trong phạm vi xử lý.
4. Ghi log nhận và xử lý thành công.
5. Gửi hai record liên tiếp và xác nhận MDC không bị giữ nhầm giữa các record.

### Bài tập 4: Context qua executor

1. Tạo ThreadPoolTaskExecutor có ContextPropagatingTaskDecorator.
2. Gửi công việc từ listener sang executor.
3. Kiểm tra trace/log context ở worker thread.
4. So sánh khi bỏ task decorator.
5. Bảo đảm acknowledgment chỉ hoàn tất sau khi nghiệp vụ được xác nhận.

### Bài tập 5: Integration test

1. Thêm spring-kafka-test.
2. Tạo topic bằng @EmbeddedKafka.
3. Viết listener probe dùng BlockingQueue.
4. Gửi record bằng KafkaTemplate.
5. Chờ listener nhận bằng timeout hữu hạn.
6. Kiểm tra payload, key và correlation header.
7. Tạo test lỗi để xác minh retry và DLT.

## 17. Câu hỏi tự kiểm tra

1. Metrics, logs và traces khác nhau ở điểm nào?
2. KafkaListenerEndpointRegistry dùng để làm gì?
3. Vì sao listener ID không giống group ID?
4. ObservationRegistry và tracing exporter có vai trò gì?
5. Producer/consumer observation truyền trace context qua Kafka bằng cách nào?
6. Vì sao không đưa event ID vào metric tag?
7. Correlation ID khác trace ID và event ID thế nào?
8. Vì sao MDC phải được dọn sau mỗi listener invocation?
9. ContextPropagatingTaskDecorator giải quyết vấn đề gì và cần điều kiện nào?
10. Vì sao chuyển xử lý sang executor có thể gây lỗi commit offset?
11. Embedded Kafka kiểm thử được những thành phần nào?
12. Vì sao Testcontainers phù hợp hơn khi cần mô phỏng môi trường nhiều broker?
13. Làm sao kiểm thử retry và dead-letter topic mà không phụ thuộc Thread.sleep?
14. Vì sao hai integration test không nên chia sẻ cùng group ID và topic khi chạy song song?

Quan sát listener, truyền context và integration test cần được thiết kế cùng nhau. Khi metrics cho thấy xu hướng, trace nối producer với consumer, log định vị record và test xác minh hành vi thực tế, nhóm phát triển có thể phát hiện lỗi sớm và vận hành Spring Kafka đáng tin cậy hơn.
