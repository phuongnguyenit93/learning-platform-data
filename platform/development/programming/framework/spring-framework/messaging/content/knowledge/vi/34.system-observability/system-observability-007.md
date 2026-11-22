# Micrometer Observation cho JMS theo khả năng phiên bản và cấu hình

## Mục tiêu

Sau bài này, bạn có thể bật quan sát cho luồng JMS trong Spring, biết chính xác phiên bản và dependency nào cần có, phân biệt thời gian gửi message với thời gian xử lý message, xác minh observation được tạo ở cả producer và consumer, và đưa metrics/traces tới backend theo cách an toàn về cardinality.

## 1. Observation là gì?

Micrometer Observation là lớp trừu tượng để ghi nhận một hoạt động đang diễn ra trong ứng dụng. Một observation có thể được xử lý bởi nhiều `ObservationHandler`:

- Handler cho metrics tạo timer, counter hoặc các meter tương ứng.
- Handler cho tracing tạo span và liên kết hoạt động với trace hiện tại.
- Handler tùy chỉnh có thể ghi log hoặc đẩy dữ liệu tới hệ thống quan sát riêng.

`ObservationRegistry` là nơi đăng ký và điều phối các observation. Nếu không có handler phù hợp, observation có thể không tạo ra metrics hoặc trace nào. Vì vậy, việc thấy một API `setObservationRegistry(...)` trong code chưa đủ để kết luận dữ liệu đã được xuất tới backend.

Cần phân biệt ba lớp:

1. **Observation instrumentation:** Spring/Micrometer xác định thời điểm bắt đầu, kết thúc và metadata của thao tác JMS.
2. **Observation handlers và registry:** chuyển observation thành metrics, traces hoặc dữ liệu khác.
3. **Exporter/backend:** nhận metrics hoặc traces, ví dụ Prometheus, OTLP collector, Zipkin hoặc hệ thống APM.

Micrometer Observation không thay thế log và cũng không tự cung cấp toàn bộ trạng thái nội bộ của broker.

## 2. Khả năng theo phiên bản và dependency

JMS Observation phụ thuộc đồng thời vào phiên bản Spring, API JMS và Micrometer instrumentation.

| Thành phần | Điều kiện |
|---|---|
| Spring Framework | API cấu hình Observation cho `JmsTemplate` và listener container có từ Spring Framework 6.1 |
| JMS API | `micrometer-jakarta9` instrument Jakarta Messaging (`jakarta.jms`) |
| Micrometer | Cần dependency `io.micrometer:micrometer-jakarta9` trên classpath để có JMS instrumentation |
| Spring Boot | Tài liệu Spring Boot 3.2.x mô tả auto-instrumentation cho các `JmsTemplate` và phương thức `@JmsListener` khả dụng |
| Backend metrics | Cần một `MeterRegistry`/registry exporter phù hợp nếu muốn xuất metrics ra ngoài |
| Backend tracing | Cần Micrometer Tracing bridge và exporter/tracer phù hợp nếu muốn xuất spans |

Hai API quan trọng được bổ sung từ Spring Framework 6.1:

- `JmsTemplate.setObservationRegistry(ObservationRegistry)` để ghi nhận hoạt động publish.
- `AbstractJmsListenerContainerFactory.setObservationRegistry(ObservationRegistry)` để ghi nhận hoạt động xử lý của listener container.

Với Spring Framework 6.0 hoặc cũ hơn, không giả định hai setter này tồn tại. Với ứng dụng Spring Boot 2 / Spring Framework 5 dùng `javax.jms`, dependency `micrometer-jakarta9` không phải instrumentation tương thích với API cũ. Hãy kiểm tra dependency tree và Javadoc của đúng phiên bản trước khi áp dụng ví dụ.

### Dependency Maven

Trong dự án Spring Boot, để Spring Boot BOM quản lý phiên bản Micrometer thay vì tự chọn một phiên bản rời rạc:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-jakarta9</artifactId>
    </dependency>

    <!-- Chọn registry theo backend, ví dụ Prometheus. -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-actuator` cung cấp nền tảng quản lý và auto-configuration observability của Spring Boot. `micrometer-jakarta9` bổ sung instrumentation cho Jakarta JMS. Registry Prometheus chỉ là ví dụ; có thể chọn OTLP, Datadog, New Relic hoặc registry khác theo hệ thống đang dùng.

Không cần khai báo version riêng cho các dependency Micrometer nếu dự án đã dùng Spring Boot dependency management/BOM tương ứng. Khi không dùng Boot BOM, hãy dùng Micrometer BOM và kiểm tra compatibility matrix giữa Micrometer, Spring Framework và JMS provider.

## 3. Hai observation chính cho JMS

Spring Framework cùng Micrometer Jakarta JMS instrumentation tạo hai loại observation:

| Observation | Thời điểm | Ý nghĩa |
|---|---|---|
| `jms.message.publish` | Producer gửi message tới destination | Đo thời gian thao tác gửi qua JMS producer, thường thông qua `JmsTemplate` |
| `jms.message.process` | Consumer xử lý message đã nhận | Đo thời gian listener xử lý message, thường qua `MessageListener` hoặc `@JmsListener` |

Hiện tại instrumentation này không tạo observation riêng tên `jms.message.receive` cho thời gian chờ nhận message. Việc đo thời gian chờ trong `MessageConsumer.receive()` không đồng nghĩa với thời gian xử lý và không tự cung cấp ngữ cảnh trace để theo dõi handler sau khi nhận.

Điều này dẫn tới một giới hạn quan trọng: `jms.message.process` cho biết listener xử lý nhanh hay chậm, nhưng không trực tiếp cho biết message đã nằm trong queue bao lâu trước khi được giao. Muốn đo queue age/consumer lag, hãy dùng metric của broker hoặc ghi timestamp nghiệp vụ/created-at khi publish và tính độ trễ ở consumer.

## 4. Bật Observation cho producer bằng JmsTemplate

Với Spring Framework 6.1+, cấu hình `ObservationRegistry` trên `JmsTemplate`:

~~~java
import io.micrometer.observation.ObservationRegistry;
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
class JmsProducerConfiguration {

    @Bean
    JmsTemplate observedJmsTemplate(
            ConnectionFactory connectionFactory,
            ObservationRegistry observationRegistry) {

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setObservationRegistry(observationRegistry);
        return template;
    }
}
~~~

Khi gọi:

~~~java
jmsTemplate.convertAndSend("orders.created", orderEvent);
~~~

Spring/Micrometer tạo observation `jms.message.publish` quanh thao tác gửi. Observation đo thời gian gửi message tới broker và instrumentation có thể truyền tracing context qua các JMS message headers.

Nếu sử dụng `JmsMessagingTemplate`, hãy tạo nó từ `JmsTemplate` đã cấu hình ObservationRegistry:

~~~java
import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.jms.core.JmsTemplate;

JmsMessagingTemplate messagingTemplate =
    new JmsMessagingTemplate(observedJmsTemplate);
~~~

Không tạo một `JmsTemplate` khác chưa được cấu hình rồi kỳ vọng observation tự xuất hiện.

## 5. Bật Observation cho @JmsListener

Observation cho consumer phải được cấu hình trên đúng `JmsListenerContainerFactory` mà listener sử dụng.

~~~java
import io.micrometer.observation.ObservationRegistry;
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class JmsListenerObservationConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            ObservationRegistry observationRegistry) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setObservationRegistry(observationRegistry);
        return factory;
    }
}
~~~

Listener có thể được khai báo như sau:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @JmsListener(
        destination = "orders.created",
        containerFactory = "jmsListenerContainerFactory"
    )
    public void handle(OrderCreated event) {
        // Xử lý nghiệp vụ.
    }
}
~~~

Khi listener container xử lý message, observation `jms.message.process` đo thời gian thực thi listener. Nếu listener ném exception, observation có thể ghi nhận trạng thái lỗi và exception theo convention. Hành vi acknowledgement/rollback vẫn phụ thuộc cấu hình transaction và JMS provider; Observation không tự rollback message.

### Khi dùng Spring Boot

Spring Boot 3.2.x reference mô tả auto-instrumentation cho các bean `JmsTemplate` và các method `@JmsListener`. Boot cũng cung cấp ObservationRegistry và các handler phù hợp khi Actuator/observability được cấu hình.

Tuy nhiên, một `@JmsListener` có thể tham chiếu factory riêng qua thuộc tính `containerFactory`. Nếu tự khai báo factory tùy chỉnh, hãy bảo đảm factory đó được cấu hình ObservationRegistry. Khi dùng `DefaultJmsListenerContainerFactoryConfigurer`, có thể giữ lại các default mà Boot đã thiết lập rồi thêm registry:

~~~java
import io.micrometer.observation.ObservationRegistry;
import jakarta.jms.ConnectionFactory;

import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
class CustomJmsFactoryConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory observedFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ObservationRegistry observationRegistry) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory, connectionFactory);
        factory.setObservationRegistry(observationRegistry);
        return factory;
    }
}
~~~

Trong dự án Boot, hãy dùng đúng factory bean trong annotation:

~~~java
@JmsListener(
    destination = "orders.created",
    containerFactory = "observedFactory"
)
public void handle(OrderCreated event) {
    // Xử lý nghiệp vụ.
}
~~~

Nếu chỉ dùng factory mặc định do Boot tạo và auto-configuration đã hoạt động, không cần khai báo một factory mới chỉ để lặp lại cấu hình mặc định.

## 6. Truyền trace context qua JMS

Observation cho producer và consumer có thể tạo hai span liên quan trong cùng một distributed trace:

1. Producer đang xử lý một request hoặc business operation.
2. `JmsTemplate` bắt đầu observation `jms.message.publish`.
3. Instrumentation ghi trace context vào JMS message headers theo cơ chế propagation.
4. Consumer nhận message.
5. `jms.message.process` khôi phục trace context từ headers và tạo span xử lý liên quan.

Nhờ đó, trace có thể nối luồng xử lý HTTP/API với việc publish message và consumer xử lý message, kể cả khi hai thao tác chạy ở các thread/process khác nhau.

Để có trace thật, ứng dụng cần Micrometer Tracing bridge và tracer/exporter được cấu hình. Chỉ có `ObservationRegistry` hoặc chỉ có metrics registry không đồng nghĩa với việc đã có distributed tracing.

Trace propagation cũng phụ thuộc vào việc message headers được giữ nguyên qua broker và middleware. Nếu một bridge, custom converter hoặc integration layer xóa các property/header liên quan, trace có thể bị đứt. Không nhét trace context vào payload nghiệp vụ nếu instrumentation đã hỗ trợ propagation qua headers.

## 7. Hiểu các key values và cardinality

Observation JMS mặc định có một số key values chung.

| Nhóm | Key | Ý nghĩa |
|---|---|---|
| Low cardinality | `error` | Tên class exception hoặc `none` |
| Low cardinality | `messaging.destination.temporary` | Destination có phải temporary queue/topic không |
| Low cardinality | `messaging.operation` | `publish` hoặc `process` |
| High cardinality | `messaging.message.conversation_id` | Correlation ID của message |
| High cardinality | `messaging.destination.name` | Tên destination |
| High cardinality | `messaging.message.id` | Message ID do provider cấp |

Low-cardinality values có số lượng giá trị hữu hạn, phù hợp làm metric tags. High-cardinality values có thể có số lượng rất lớn, vì vậy mặc định chỉ nên đưa vào trace/span và không nên dùng làm metric label.

Ví dụ:
- `messaging.operation=publish` chỉ có một số giá trị cố định.
- `error=JmsException` thường có số lượng class lỗi hữu hạn.
- `messaging.message.id=ID:...` có thể khác nhau cho từng message; đưa key này vào metric label sẽ tạo hàng triệu time series.
- `messaging.message.conversation_id` cũng có thể là duy nhất theo request; phù hợp hơn trong trace.

Không thêm customer ID, order ID, email hoặc payload vào low-cardinality tags. Nếu cần tra cứu một message cụ thể, dùng log có correlation ID hoặc trace search, đồng thời tuân thủ chính sách bảo vệ dữ liệu.

Có thể dùng custom ObservationConvention/ObservationFilter để điều chỉnh metadata. Trước khi đưa một key vào metrics, hãy ước lượng số giá trị tối đa của nó và kiểm tra tác động lên cardinality, memory, storage và chi phí backend.

## 8. Xem metrics bằng Spring Boot Actuator

Nếu ứng dụng có registry phù hợp, có thể kiểm tra metric name qua Actuator:

~~~properties
management.endpoints.web.exposure.include=health,metrics,prometheus
~~~

Endpoint `/actuator/metrics` hữu ích để chẩn đoán meter trong một instance. Ví dụ:

~~~text
GET /actuator/metrics/jms.message.publish
GET /actuator/metrics/jms.message.process
~~~

Tên metric ở Actuator là tên trong code/convention. Khi xuất sang Prometheus, naming convention có thể đổi dấu chấm thành dấu gạch dưới và thêm hậu tố đơn vị, ví dụ timer được biểu diễn thành các series tương ứng.

Nếu dùng Prometheus, thêm registry dependency và cấu hình Prometheus scrape `/actuator/prometheus`. Endpoint cần được expose và bảo vệ theo chính sách bảo mật của ứng dụng. Không dùng endpoint metrics làm backend lưu trữ production; hãy dùng Prometheus hoặc monitoring backend thực sự.

### Nên theo dõi gì?

- Thời gian publish message và tỷ lệ publish lỗi.
- Thời gian process message và tỷ lệ xử lý lỗi.
- Phân bố latency theo operation/destination nếu destination có cardinality thấp trong hệ thống.
- Trace cho những message có thời gian xử lý bất thường.
- Queue depth, enqueue age, consumer count, DLQ depth và broker health từ hệ thống monitoring của broker.

Spring JMS observations không thay thế broker metrics. Queue depth và backlog thường phải lấy từ Artemis management/JMX, IBM MQ monitoring hoặc API tương ứng của provider.

## 9. Kiểm thử Observation

Một test tốt cần kiểm tra rằng thao tác thật đi qua instrumentation và tạo meter, không chỉ kiểm tra bean `ObservationRegistry` tồn tại.

### Tạo registry dùng trong test

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();

ObservationRegistry observationRegistry = ObservationRegistry.create();
observationRegistry.observationConfig().observationHandler(
    new DefaultMeterObservationHandler(meterRegistry)
);
~~~

Đây là setup cho test; trong ứng dụng Boot, registry và handler thường được auto-configure. Test cần dependency `micrometer-core` và `micrometer-jakarta9`.

### Kiểm tra publish observation

1. Tạo `JmsTemplate` dùng broker thật và cấu hình `setObservationRegistry(observationRegistry)`.
2. Gửi một message tới destination test riêng.
3. Xác nhận consumer test nhận đúng message.
4. Tìm timer `jms.message.publish` trong `SimpleMeterRegistry`.
5. Xác nhận timer có ít nhất một lần ghi nhận và tag operation có giá trị publish.

Ví dụ assertion với AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

var publishTimer = meterRegistry.find("jms.message.publish").timer();

assertThat(publishTimer).isNotNull();
assertThat(publishTimer.count()).isGreaterThanOrEqualTo(1);
~~~

### Kiểm tra process observation

1. Cấu hình `ObservationRegistry` trên listener container factory.
2. Gửi message tới destination của `@JmsListener`.
3. Dùng `CountDownLatch` hoặc `BlockingQueue` để đợi listener hoàn tất.
4. Tìm timer `jms.message.process`.
5. Xác nhận timer được ghi nhận sau khi listener chạy.

Nếu muốn test error observation, tạo listener ném exception có chủ đích và kiểm tra error metadata. Với listener transacted, broker có thể redeliver; vì vậy test cần cấu hình số lần giao lại, delay và DLQ để kết quả ổn định. Không giả định một exception chỉ tạo đúng một process observation nếu broker giao lại message nhiều lần.

### Test context propagation

Dùng một producer span hiện tại, gửi message, sau đó để consumer xử lý. Kiểm tra trace backend/test tracer có span publish và process liên kết theo trace context. Chỉ assert rằng message có correlation ID không đủ để chứng minh distributed tracing đã được propagate.

### Test khi Observation chưa được bật

Chạy một test đối chứng với registry no-op hoặc không cấu hình registry. Điều này giúp phát hiện trường hợp test vô tình đo meter từ một instrumentation khác. So sánh trước/sau bằng meter name, count và tags; không chỉ kiểm tra endpoint HTTP trả 200.

## 10. Khi không dùng Spring JmsTemplate

Nếu ứng dụng gọi Jakarta JMS API trực tiếp, Micrometer cung cấp `JmsInstrumentation.instrumentSession(...)` để instrument session:

~~~java
import io.micrometer.jakarta9.instrument.jms.JmsInstrumentation;
import io.micrometer.observation.ObservationRegistry;

import jakarta.jms.Session;

Session instrumentedSession =
    JmsInstrumentation.instrumentSession(originalSession, observationRegistry);
~~~

Sau đó tạo producer/consumer từ session đã instrument. Cần bảo đảm không instrument cùng một session nhiều lần hoặc tạo thêm observation trùng lặp. Với code dùng `JmsTemplate` và `@JmsListener`, ưu tiên cấu hình registry trên Spring abstraction để tránh tự instrument lặp.

## 11. Giới hạn và lỗi thường gặp

- **Có Actuator nhưng thiếu `micrometer-jakarta9`:** registry có thể hoạt động cho HTTP/JVM nhưng không có JMS instrumentation.
- **Dùng Spring Framework dưới 6.1:** các setter `setObservationRegistry` có thể chưa tồn tại.
- **Dùng `javax.jms` với `micrometer-jakarta9`:** package API không tương thích; không trộn javax và jakarta.
- **Chỉ cấu hình JmsTemplate:** publish có thể được quan sát nhưng listener process chưa được instrument.
- **Chỉ cấu hình factory mặc định:** listener dùng custom `containerFactory` riêng có thể không có registry.
- **Có Observation nhưng không có handler:** observation được tạo nhưng không xuất thành metrics hoặc traces.
- **Có metrics nhưng mong đợi trace:** cần cấu hình Micrometer Tracing bridge và exporter.
- **Tìm metric `jms.message.receive`:** instrumentation JMS hiện tại tập trung vào publish và process, không tạo receive observation riêng.
- **Dùng message ID làm metric tag:** cardinality tăng không kiểm soát.
- **Mong đợi queue depth từ JMS Observation:** cần broker metrics/management API.
- **Đo process time rồi gọi đó là queue latency:** process time bắt đầu khi ứng dụng xử lý, không bao gồm toàn bộ thời gian message chờ trong broker.
- **Tạo JmsMessagingTemplate từ template chưa instrument:** registry trên template nguồn mới là nơi cần cấu hình.
- **Tạo factory mới và bỏ mất Boot defaults:** khi tùy chỉnh factory trong Boot, dùng configurer để giữ converter và các default cần thiết.

## 12. Checklist triển khai

- [ ] Xác nhận Spring Framework 6.1+ nếu dùng các ObservationRegistry setter.
- [ ] Xác nhận JMS API là Jakarta (`jakarta.jms`) khi dùng `micrometer-jakarta9`.
- [ ] Kiểm tra dependency tree có Micrometer Jakarta JMS instrumentation.
- [ ] Xác nhận Spring Boot Actuator/ObservationRegistry đã được cấu hình.
- [ ] Cấu hình registry trên mọi `JmsTemplate` dùng để publish.
- [ ] Cấu hình registry trên đúng `JmsListenerContainerFactory` của mỗi listener.
- [ ] Xác nhận có `jms.message.publish` và `jms.message.process` sau test message thật.
- [ ] Nếu cần tracing, thêm bridge/tracer/exporter và kiểm tra trace context qua JMS headers.
- [ ] Không đưa ID hoặc dữ liệu nhạy cảm vào metric tags.
- [ ] Dùng broker metrics cho queue depth, backlog, DLQ và consumer health.
- [ ] Expose Actuator endpoints có chọn lọc và bảo vệ chúng.
- [ ] Có integration test cho publish, process, error và trace propagation.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Observability Support](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html): tên JMS observations, dependency và cách cấu hình registry.
- [Spring Framework 6.1 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `setObservationRegistry`, có từ 6.1.
- [Spring Framework 6.1 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.1.9/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html): registry cho JMS message processing observations, có từ 6.1.
- [Spring Boot 3.2 — JMS Metrics](https://docs.spring.io/spring-boot/docs/3.2.10/reference/html/actuator.html): auto-instrumentation cho `JmsTemplate` và `@JmsListener`.
- [Micrometer — JMS Instrumentation](https://docs.micrometer.io/micrometer/reference/reference/jms.html): dependency `micrometer-jakarta9`, observations và key values.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ObservationRegistry, handlers, metrics và tracing.
