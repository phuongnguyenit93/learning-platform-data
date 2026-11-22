# Định tuyến template bằng qualifier

Một ứng dụng Spring Kafka có thể cần gửi sự kiện đến nhiều topic, dùng nhiều kiểu serializer hoặc kết nối nhiều Kafka cluster. Khi đó, việc khai báo nhiều bean `KafkaTemplate` giúp tách cấu hình gửi theo từng mục đích. Spring sử dụng `@Qualifier` để chọn đúng bean khi inject vào service.

`@Qualifier` giải quyết việc **chọn dependency trong Spring ApplicationContext**. Nó không tự phân phối record theo key, không chọn partition và cũng không tự quyết định cluster dựa trên nội dung message. Luồng nghiệp vụ gọi template đã được inject; template đó sử dụng `ProducerFactory` tương ứng để gửi record.

## 1. Vì sao cần nhiều KafkaTemplate?

`KafkaTemplate` là abstraction của Spring Kafka để gửi record. Một template được xây dựng từ một `ProducerFactory`, do đó nó sử dụng cấu hình producer mà factory cung cấp: bootstrap servers, serializer, security, retry và các thuộc tính Kafka client khác.

Trong ứng dụng nhỏ, một template có thể gửi đến nhiều topic:

```java
kafkaTemplate.send("orders", orderId, orderCreated);
kafkaTemplate.send("billing-events", orderId, billingEvent);
```

Cách này phù hợp khi các luồng dùng chung cluster, serializer và chính sách producer. Tuy nhiên, khi ứng dụng lớn hơn, có thể cần tách template theo vai trò:

| Template | Mục đích | Cấu hình có thể khác |
|---|---|---|
| `ordersKafkaTemplate` | Gửi sự kiện đơn hàng | Topic mặc định, kiểu payload |
| `billingKafkaTemplate` | Gửi sự kiện thanh toán | Topic mặc định, serializer |
| `auditKafkaTemplate` | Gửi audit event | Cluster hoặc security riêng |
| `notificationKafkaTemplate` | Gửi thông báo | Retry, timeout hoặc cluster riêng |

Tách template giúp code thể hiện rõ ý định. Một service gửi hóa đơn không cần biết chi tiết tên bean hoặc cách tạo producer; nó chỉ nhận dependency đúng vai trò.

Không cần tạo nhiều template chỉ vì có nhiều topic. Nếu các topic dùng cùng producer config và code đã truyền topic rõ ràng, một template có thể đơn giản hơn. Chỉ tách khi ranh giới cấu hình hoặc trách nhiệm gửi có ý nghĩa.

## 2. Khai báo nhiều KafkaTemplate bean

Giả sử hai luồng gửi dùng chung Kafka cluster, cùng serializer và cùng producer factory, nhưng muốn có template riêng với topic mặc định khác nhau. Có thể tạo hai bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
class KafkaTemplateConfiguration {

    @Bean("ordersKafkaTemplate")
    KafkaTemplate<Object, Object> ordersKafkaTemplate(
            ProducerFactory<Object, Object> producerFactory) {

        KafkaTemplate<Object, Object> template =
                new KafkaTemplate<>(producerFactory);
        template.setDefaultTopic("orders");
        return template;
    }

    @Bean("billingKafkaTemplate")
    KafkaTemplate<Object, Object> billingKafkaTemplate(
            ProducerFactory<Object, Object> producerFactory) {

        KafkaTemplate<Object, Object> template =
                new KafkaTemplate<>(producerFactory);
        template.setDefaultTopic("billing-events");
        return template;
    }
}
```

Cả hai template dùng cùng một `ProducerFactory` nên chia sẻ cấu hình producer và cơ chế tạo client. Điểm khác nhau trong ví dụ là topic mặc định. Nếu gọi `sendDefault()`, mỗi template gửi đến topic mặc định mà nó đã được cấu hình.

Ví dụ này cũng minh họa một điểm quan trọng: tên bean giúp Spring phân biệt các dependency cùng kiểu. Cả hai bean đều là `KafkaTemplate<Object, Object>`, nên inject chỉ theo kiểu sẽ tạo ra nhiều ứng viên.

Hai template dùng chung factory cũng dùng chung cấu hình `client.id` và cơ chế quản lý producer của factory. Vì vậy, việc tách template theo topic mặc định không tự tạo ranh giới metric hoặc quota theo từng template. Nếu cần nhận diện và giới hạn lưu lượng độc lập, hãy tạo producer factory riêng với client ID và cấu hình tương ứng.

## 3. Dùng @Qualifier khi inject vào service

`@Qualifier` chỉ rõ bean mà constructor parameter cần nhận. Nên dùng constructor injection để dependency hiển thị ngay trong cấu trúc service:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class EventPublisher {

    private final KafkaTemplate<Object, Object> ordersTemplate;
    private final KafkaTemplate<Object, Object> billingTemplate;

    EventPublisher(
            @Qualifier("ordersKafkaTemplate")
            KafkaTemplate<Object, Object> ordersTemplate,
            @Qualifier("billingKafkaTemplate")
            KafkaTemplate<Object, Object> billingTemplate) {

        this.ordersTemplate = ordersTemplate;
        this.billingTemplate = billingTemplate;
    }

    void publishOrder(OrderCreated event) {
        ordersTemplate.sendDefault(event.orderId(), event);
    }

    void publishBilling(BillingCreated event) {
        billingTemplate.sendDefault(event.orderId(), event);
    }
}
```

Khi Spring tạo `EventPublisher`, nó tìm bean có qualifier tương ứng và inject vào đúng constructor parameter. Vì vậy, `ordersTemplate` luôn đại diện cho template gửi đơn hàng và `billingTemplate` đại diện cho template gửi sự kiện billing.

Trong ví dụ, `sendDefault(key, value)` dùng topic mặc định đã đặt trong từng template. Nếu muốn chọn topic theo từng lời gọi, có thể dùng `send(topic, key, value)`; qualifier vẫn có tác dụng chọn template, còn tham số topic chọn đích gửi trong cluster mà template đang sử dụng.

Nếu tên bean được khai báo bằng `@Bean("ordersKafkaTemplate")`, Spring có thể dùng bean name làm qualifier khi inject. Việc ghi rõ `@Qualifier("ordersKafkaTemplate")` vẫn giúp người đọc hiểu ý định và tránh phụ thuộc vào suy luận tên parameter.

## 4. Tách ProducerFactory khi cấu hình producer khác nhau

Hai template dùng chung factory chỉ khác cách gọi hoặc topic mặc định. Nếu cần kết nối hai Kafka cluster khác nhau, phải tạo hai `ProducerFactory` với cấu hình riêng và gắn từng template vào đúng factory.

Ví dụ cấu hình một producer factory cho audit cluster:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Configuration
class MultiClusterProducerConfiguration {

    @Bean("auditProducerFactory")
    ProducerFactory<Object, Object> auditProducerFactory(
            @Value("${app.kafka.audit.bootstrap-servers}")
            String bootstrapServers) {

        Map<String, Object> properties = new HashMap<>();
        properties.put(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers
        );
        properties.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class
        );
        properties.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                JsonSerializer.class
        );

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean("auditKafkaTemplate")
    KafkaTemplate<Object, Object> auditKafkaTemplate(
            @Qualifier("auditProducerFactory")
            ProducerFactory<Object, Object> producerFactory) {

        KafkaTemplate<Object, Object> template =
                new KafkaTemplate<>(producerFactory);
        template.setDefaultTopic("audit-events");
        return template;
    }
}
```

Thuộc tính môi trường tương ứng:

```yaml
app:
  kafka:
    audit:
      bootstrap-servers: audit-kafka-1:9092,audit-kafka-2:9092
```

Trong ví dụ, `auditKafkaTemplate` chỉ sử dụng `auditProducerFactory`. Producer factory mặc định của Spring Boot có thể tiếp tục phục vụ template nghiệp vụ khác. Cấu hình thực tế cho cluster riêng còn phải bổ sung security, timeout, acknowledgments, compression và serializer/deserializer phù hợp với yêu cầu của cluster đó.

Nếu tạo nhiều producer factory, hãy đặt qualifier ở cả nơi khai báo dependency lẫn nơi inject. Nếu bỏ qualifier ở tham số `ProducerFactory`, Spring có thể không biết factory nào cần dùng hoặc inject nhầm factory khi có nhiều bean cùng kiểu.

## 5. Phân biệt qualifier, bean name và @Primary

Ba cơ chế này có liên quan nhưng không thay thế nhau:

| Cơ chế | Vai trò | Khi nên dùng |
|---|---|---|
| Bean name | Tên định danh bean trong ApplicationContext | Đặt tên rõ cho từng template hoặc factory |
| `@Qualifier` | Thu hẹp ứng viên khi inject dependency | Service cần chọn chính xác một template |
| `@Primary` | Ưu tiên một bean khi inject theo kiểu mà không có qualifier cụ thể | Có một template mặc định cho phần lớn code cũ |

Ví dụ đánh dấu template mặc định:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@Bean("defaultKafkaTemplate")
@Primary
KafkaTemplate<Object, Object> defaultKafkaTemplate(
        ProducerFactory<Object, Object> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

Khi một constructor chỉ inject `KafkaTemplate<Object, Object>` mà không có qualifier, Spring ưu tiên bean `@Primary`. Khi constructor có `@Qualifier("auditKafkaTemplate")`, Spring chọn bean audit theo qualifier.

Không dùng `@Primary` để biểu diễn định tuyến nghiệp vụ. Nó chỉ giải quyết lựa chọn mặc định khi inject; nó không phân tích loại event hoặc nội dung record.

## 6. Generic type và nhiều template

Spring có thể sử dụng generic type để phân biệt bean. Ví dụ:

```java
@Bean("orderTemplate")
KafkaTemplate<String, OrderCreated> orderTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}

@Bean("invoiceTemplate")
KafkaTemplate<String, InvoiceCreated> invoiceTemplate(
        ProducerFactory<String, InvoiceCreated> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

Khi inject `KafkaTemplate<String, OrderCreated>`, generic type có thể giúp Spring chọn đúng bean. Tuy nhiên, nếu các template có cùng generic type, cần qualifier để phân biệt. Ngay cả khi generic type khác nhau, qualifier tường minh vẫn hữu ích khi ý nghĩa nghiệp vụ quan trọng hơn kiểu Java.

Tránh inject raw type `KafkaTemplate` hoặc dùng nhiều wildcard quá rộng nếu ứng dụng có nhiều template. Kiểu cụ thể giúp trình biên dịch kiểm tra key và payload, còn qualifier giúp Spring chọn đúng instance.

## 7. Định tuyến theo điều kiện runtime

`@Qualifier` phù hợp khi service biết trước template cần dùng trong constructor hoặc method. Nó không tự chọn template dựa trên trường trong event.

Nếu quyết định gửi phụ thuộc vào loại sự kiện hoặc tenant tại runtime, hãy viết một lớp định tuyến nghiệp vụ rõ ràng. Ví dụ:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
class EventRouter {

    private final KafkaTemplate<Object, Object> ordersTemplate;
    private final KafkaTemplate<Object, Object> billingTemplate;

    EventRouter(
            @Qualifier("ordersKafkaTemplate")
            KafkaTemplate<Object, Object> ordersTemplate,
            @Qualifier("billingKafkaTemplate")
            KafkaTemplate<Object, Object> billingTemplate) {
        this.ordersTemplate = ordersTemplate;
        this.billingTemplate = billingTemplate;
    }

    void publish(Object event) {
        if (event instanceof OrderCreated order) {
            ordersTemplate.sendDefault(order.orderId(), order);
            return;
        }

        if (event instanceof BillingCreated billing) {
            billingTemplate.sendDefault(billing.orderId(), billing);
            return;
        }

        throw new IllegalArgumentException(
                "Unsupported event type: " + event.getClass().getName()
        );
    }
}
```

Lớp router vẫn dùng qualifier để nhận đúng dependency. Logic runtime nằm ở phương thức `publish()`, nơi quyết định template theo kiểu event. Với nhiều loại event, có thể thay chuỗi `if` bằng strategy map, registry hoặc một interface publisher riêng cho từng loại sự kiện.

Không nên dùng tên bean được tạo từ dữ liệu không tin cậy hoặc để payload tự quyết định một bean tùy ý trong ApplicationContext. Hãy ánh xạ giá trị nghiệp vụ đã được kiểm soát sang một strategy rõ ràng.

## 8. Xử lý kết quả gửi và lỗi producer

Việc chọn đúng template không đồng nghĩa record đã được broker xác nhận. Các phương thức gửi của `KafkaTemplate` trả về future để ứng dụng quan sát kết quả bất đồng bộ. Với Spring Kafka 3.x, API gửi sử dụng `CompletableFuture`:

```java
ordersTemplate.sendDefault(event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Could not publish order event", exception);
                return;
            }

            var metadata = result.getRecordMetadata();
            log.info(
                    "Published order event to topic={}, partition={}, offset={}",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
        });
```

Nếu dùng phiên bản Spring Kafka cũ hơn, kiểu future có thể là `ListenableFuture`. Hãy dùng API tương ứng với phiên bản thư viện của ứng dụng.

Không bỏ qua kết quả future nếu nghiệp vụ cần biết gửi thành công hay thất bại. Với luồng quan trọng, cần xác định retry, timeout, xử lý lỗi và khả năng gửi trùng. Log nên ghi topic, partition, offset khi gửi thành công và nguyên nhân khi gửi thất bại; không log payload nhạy cảm.

## 9. Kiểm thử wiring của các template

Khi có nhiều template, lỗi thường gặp là qualifier sai, bean name không tồn tại hoặc template được gắn nhầm producer factory. Có thể kiểm tra ApplicationContext để bảo đảm các bean được đăng ký:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.kafka.core.KafkaTemplate;

@SpringBootTest
class KafkaTemplateWiringTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersNamedTemplates() {
        assertThat(context.getBean("ordersKafkaTemplate"))
                .isInstanceOf(KafkaTemplate.class);

        assertThat(context.getBean("billingKafkaTemplate"))
                .isInstanceOf(KafkaTemplate.class);
    }
}
```

Bài kiểm tra này xác nhận bean name có mặt và đúng kiểu. Việc Spring tạo được service có constructor qualifier cũng là một kiểm tra wiring: nếu qualifier không khớp, context sẽ không khởi động thành công.

Nếu muốn kiểm tra template gửi đến đúng cluster hoặc topic, cần kiểm thử ở mức producer integration với broker thử nghiệm hoặc mock producer factory phù hợp. Chỉ kiểm tra bean tồn tại không chứng minh cấu hình bootstrap servers, serializer hay topic mặc định là chính xác.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `NoUniqueBeanDefinitionException` khi inject template | Có nhiều bean cùng kiểu nhưng injection point không chỉ rõ qualifier hoặc primary | Thêm `@Qualifier` cho từng constructor parameter |
| `NoSuchBeanDefinitionException` | Tên qualifier không trùng bean đã đăng ký hoặc cấu hình bean chưa được scan | Kiểm tra tên `@Bean`, package scan và profile |
| Template gửi nhầm cluster | Template được inject bằng factory không đúng | Gắn qualifier rõ ở tham số `ProducerFactory` khi tạo template |
| Payload serialization thất bại | Template dùng factory với serializer không phù hợp payload | Kiểm tra producer factory, serializer và kiểu dữ liệu |
| Gửi nhầm topic mặc định | Template được cấu hình `setDefaultTopic()` sai hoặc dùng nhầm qualifier | Kiểm tra bean name và default topic; cân nhắc truyền topic tường minh |
| Tạo quá nhiều producer client | Mỗi template lại tạo một producer factory độc lập không cần thiết | Chia sẻ factory khi cấu hình producer giống nhau |
| Thêm template riêng làm mất template mặc định mong đợi | Auto-configuration có thể lùi khi ứng dụng đã khai báo bean theo điều kiện của Boot | Kiểm tra condition report và khai báo template mặc định có chủ đích |
| `@Primary` làm service gửi sai luồng | Service inject theo kiểu mà không có qualifier nên nhận template mặc định | Dùng qualifier ở nơi cần ranh giới nghiệp vụ rõ ràng |

## 11. Checklist thiết kế nhiều KafkaTemplate

1. Chỉ tạo nhiều template khi có khác biệt rõ về topic mặc định, producer config, serializer, cluster hoặc trách nhiệm nghiệp vụ.
2. Dùng chung `ProducerFactory` nếu các template thực sự dùng cùng cấu hình producer.
3. Tạo `ProducerFactory` riêng khi cần cluster, security hoặc serializer khác nhau.
4. Đặt bean name mô tả mục đích như `ordersKafkaTemplate` và `auditKafkaTemplate`.
5. Dùng `@Qualifier` tại constructor parameter và tại dependency factory nếu có nhiều bean cùng kiểu.
6. Chỉ dùng `@Primary` cho template mặc định; không dùng nó để định tuyến theo event.
7. Dùng generic type cụ thể để phát hiện sai kiểu key và payload.
8. Tách logic định tuyến runtime thành service hoặc strategy có kiểm thử.
9. Quan sát future trả về từ send và thiết kế retry/idempotency theo yêu cầu nghiệp vụ.
10. Kiểm tra bean wiring và xác minh cấu hình cluster/topic trước khi triển khai.

Khi ứng dụng có nhiều luồng gửi, mỗi `KafkaTemplate` nên đại diện cho một mục đích rõ ràng. Kết hợp bean name, `@Qualifier` và `ProducerFactory` đúng cấu hình giúp service gửi sự kiện đến đúng đích, đồng thời giữ cho dependency và trách nhiệm vận hành dễ kiểm tra.
