# Tổ chức package cho producer và consumer

Khi khởi tạo một ứng dụng Spring Kafka, hãy tổ chức package sao cho người đọc nhanh chóng tìm được nơi phát event, nơi nhận event, nơi định nghĩa hợp đồng dữ liệu và nơi cấu hình Kafka. Cấu trúc tốt cũng giúp phần nghiệp vụ không phụ thuộc trực tiếp vào `KafkaTemplate`, `@KafkaListener` hoặc các kiểu của Kafka client.

Trong module `SPRING_KAFKA_MESSAGING`, producer gửi sự kiện bằng Spring Kafka và `KafkaTemplate`; consumer nhận sự kiện bằng `@KafkaListener`. Một ứng dụng có thể đảm nhiệm cả hai vai trò, hoặc mỗi service chỉ đảm nhiệm một vai trò. Cấu trúc package cần thể hiện rõ ranh giới đó mà vẫn phù hợp với quy mô dự án.

## 1. Xác định trách nhiệm trước khi tạo package

Producer và consumer là hai đầu của luồng messaging, mỗi đầu có trách nhiệm riêng:

| Thành phần | Trách nhiệm chính | Không nên đảm nhiệm |
|---|---|---|
| Producer adapter | Chọn topic, key, headers; chuyển event thành record; gửi bằng `KafkaTemplate`; quan sát kết quả gửi | Chứa toàn bộ quy tắc nghiệp vụ tạo đơn hàng hoặc tính toán trạng thái domain |
| Consumer adapter | Khai báo `@KafkaListener`; nhận payload; chuyển thông tin cần thiết cho application use case; phối hợp xử lý lỗi ở biên messaging | Chứa toàn bộ nghiệp vụ phức tạp hoặc truy cập trực tiếp mọi repository trong listener |
| Event contract | Định nghĩa cấu trúc dữ liệu trao đổi qua Kafka, tên và ý nghĩa các trường | Tái sử dụng trực tiếp entity JPA hoặc object nội bộ của domain làm schema tích hợp |
| Kafka configuration | Cấu hình bootstrap servers, serializer/deserializer, consumer group, listener factory và topic khi cần | Trộn cấu hình hạ tầng vào domain model |
| Application/domain | Thực hiện quy tắc nghiệp vụ, điều phối use case và quản lý trạng thái | Phụ thuộc vào `KafkaTemplate`, `ConsumerRecord` hoặc API broker |

Một nguyên tắc hữu ích là **listener nhận dữ liệu rồi giao cho use case xử lý; publisher chuyển yêu cầu phát sự kiện thành Kafka record**. Hai adapter này là ranh giới giữa ứng dụng và Kafka.

## 2. Chọn cách tổ chức package phù hợp

Có hai cách tổ chức thường gặp.

### 2.1. Tổ chức theo vai trò kỹ thuật

Với một ứng dụng nhỏ, chỉ có một vài producer và consumer, có thể bắt đầu bằng cấu trúc đơn giản:

```text
com.example.messaging
├── MessagingApplication.java
├── config/
│   ├── KafkaProducerConfiguration.java
│   ├── KafkaConsumerConfiguration.java
│   └── KafkaTopicConfiguration.java
├── contract/
│   ├── OrderCreatedEvent.java
│   └── PaymentReceivedEvent.java
├── producer/
│   ├── OrderEventPublisher.java
│   └── PaymentEventPublisher.java
└── consumer/
    ├── OrderEventListener.java
    └── PaymentEventListener.java
```

Ưu điểm của cách này là dễ hiểu, ít thư mục và thuận tiện khi học các API Spring Kafka. Tuy nhiên, khi số lượng nghiệp vụ tăng lên, package `producer` hoặc `consumer` có thể chứa rất nhiều class thuộc các tính năng không liên quan. Người đọc phải đi qua nhiều thư mục để hiểu trọn vẹn một luồng nghiệp vụ.

### 2.2. Tổ chức theo tính năng, tách adapter bên trong tính năng

Với ứng dụng có nhiều nghiệp vụ, nên nhóm code theo feature hoặc bounded context trước, rồi chia producer và consumer bên trong feature đó:

```text
com.acme.orders
├── OrdersApplication.java
├── order/
│   ├── domain/
│   │   ├── Order.java
│   │   └── OrderRepository.java
│   ├── application/
│   │   ├── port/
│   │   │   └── out/
│   │   │       └── OrderEventPublisher.java
│   │   └── usecase/
│   │       ├── CreateOrderUseCase.java
│   │       └── HandleOrderCreatedUseCase.java
│   ├── messaging/
│   │   └── contract/
│   │       └── OrderCreatedEvent.java
│   └── adapter/
│       └── kafka/
│           ├── producer/
│           │   └── KafkaOrderEventPublisher.java
│           └── consumer/
│               └── OrderCreatedListener.java
├── infrastructure/
│   └── kafka/
│       ├── KafkaProducerConfiguration.java
│       ├── KafkaConsumerConfiguration.java
│       └── KafkaTopicConfiguration.java
└── support/
```

Trong cấu trúc này:

- `domain` chứa entity, value object và quy tắc domain.
- `application` chứa use case và các port mà use case cần sử dụng.
- `adapter.kafka.producer` triển khai port gửi event bằng Kafka.
- `adapter.kafka.consumer` nhận record và gọi use case tương ứng.
- `messaging.contract` chứa DTO đại diện cho schema trao đổi qua Kafka, độc lập với adapter cụ thể.
- `infrastructure.kafka` chứa cấu hình hạ tầng dùng chung cho ứng dụng.

Đây là một cách tổ chức tham khảo theo hướng ports and adapters. Dự án không bắt buộc phải dùng đầy đủ các tầng này. Với ứng dụng nhỏ, có thể bỏ `port` hoặc `support` nếu chúng chưa đem lại giá trị. Điều quan trọng là giữ được ranh giới giữa nghiệp vụ và công nghệ messaging.

## 3. Luồng phụ thuộc giữa producer, consumer và nghiệp vụ

Producer thường được gọi từ application use case sau khi nghiệp vụ quyết định cần phát một sự kiện. Consumer nhận record từ Kafka rồi gọi use case xử lý dữ liệu đến. Cả hai đi qua adapter ở biên hệ thống:

```mermaid
flowchart LR
    A[Application use case] --> B[OrderEventPublisher port]
    B --> C[KafkaOrderEventPublisher]
    C --> D[KafkaTemplate]
    D --> E[(Kafka topic)]
    E --> F[@KafkaListener]
    F --> G[HandleOrderCreatedUseCase]
    G --> H[Domain / Repository]
```

Chiều gửi và chiều nhận có thể nằm trong cùng một service, nhưng không có nghĩa chúng phải phụ thuộc trực tiếp vào nhau. Producer chỉ cần biết hợp đồng event và topic đích; consumer chỉ cần biết hợp đồng event mà nó xử lý. Hai đầu giao tiếp thông qua Kafka.

Không nên để domain entity gọi `KafkaTemplate.send(...)`. Domain model không cần biết broker, topic hoặc serializer. Nếu cần phát event sau khi lưu dữ liệu, hãy điều phối việc đó tại application layer. Với yêu cầu nhất quán giữa database và Kafka, có thể cần transactional outbox; không nên giả định rằng gọi `send()` ngay sau `repository.save()` tự động tạo ra một giao dịch nguyên tử xuyên hai hệ thống.

## 4. Đặt event contract ở đâu?

Event contract là schema mà producer và consumer cùng hiểu. Ví dụ:

```java
package com.acme.orders.order.messaging.contract;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total,
        Instant occurredAt
) {}
```

Contract nên mô tả dữ liệu công khai cần trao đổi, có tên trường rõ ràng và có chiến lược tương thích khi schema thay đổi. Không nên đưa các chi tiết nội bộ như entity có lazy relationship, trạng thái ORM hoặc service bean vào payload.

Nếu producer và consumer thuộc cùng một ứng dụng, contract có thể nằm trong package messaging của feature. Nếu chúng thuộc các service độc lập, cân nhắc một module thư viện contract có version riêng hoặc một schema registry/schema repository. Khi đó:

- Không chia sẻ entity JPA hoặc domain model nội bộ giữa các service.
- Chỉ chia sẻ kiểu dữ liệu hợp đồng được chủ động công bố.
- Thay đổi field cần xem xét khả năng tương thích với producer/consumer đang triển khai ở phiên bản khác.
- Không để consumer phụ thuộc vào package implementation của producer.

Ví dụ, service `orders` có thể phát `OrderCreatedEvent`; service `billing` chỉ cần contract của event để xử lý hóa đơn. `billing` không cần import `Order` entity hoặc `OrderRepository` của service `orders`.

## 5. Ví dụ tổ chức producer

Application layer định nghĩa port mà use case cần:

```java
package com.acme.orders.order.application.port.out;

import com.acme.orders.order.messaging.contract.OrderCreatedEvent;

public interface OrderEventPublisher {
    void publish(OrderCreatedEvent event);
}
```

Adapter triển khai port bằng `KafkaTemplate`:

```java
package com.acme.orders.order.adapter.kafka.producer;

import com.acme.orders.order.messaging.contract.OrderCreatedEvent;
import com.acme.orders.order.application.port.out.OrderEventPublisher;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class KafkaOrderEventPublisher implements OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;
    private final String topic;

    public KafkaOrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate,
            @Value("${app.kafka.topics.order-created}") String topic) {
        this.kafkaTemplate = kafkaTemplate;
        this.topic = topic;
    }

    @Override
    public void publish(OrderCreatedEvent event) {
        kafkaTemplate.send(topic, event.orderId(), event);
    }
}
```

Trong ví dụ, `orderId` là key để các event của cùng đơn hàng có thể được định tuyến vào cùng partition theo partitioner mặc định khi cấu hình partition ổn định. Publisher không tự quyết định quy tắc tạo đơn hàng; nó chỉ chuyển event thành thông điệp Kafka.

Đoạn code giữ ví dụ ngắn nên chưa xử lý kết quả bất đồng bộ từ `KafkaTemplate.send(...)`. Trong ứng dụng thật, cần quan sát send result/failure và xác định cách báo lỗi phù hợp với use case. Nếu port cần biểu diễn kết quả gửi, hãy dùng một kiểu trả về thuộc application layer như `CompletionStage` hoặc kiểu kết quả riêng, tránh để tầng application phụ thuộc trực tiếp vào `SendResult` của Spring Kafka.

## 6. Ví dụ tổ chức consumer

Consumer adapter chỉ nhận event và chuyển cho use case:

```java
package com.acme.orders.order.adapter.kafka.consumer;

import com.acme.orders.order.messaging.contract.OrderCreatedEvent;
import com.acme.orders.order.application.usecase.HandleOrderCreatedUseCase;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final HandleOrderCreatedUseCase useCase;

    public OrderCreatedListener(HandleOrderCreatedUseCase useCase) {
        this.useCase = useCase;
    }

    @KafkaListener(topics = "${app.kafka.topics.order-created}")
    public void onMessage(OrderCreatedEvent event) {
        useCase.handle(event);
    }
}
```

Use case xử lý nghiệp vụ được đặt ở application layer:

```java
package com.acme.orders.order.application.usecase;

import com.acme.orders.order.messaging.contract.OrderCreatedEvent;

public interface HandleOrderCreatedUseCase {
    void handle(OrderCreatedEvent event);
}
```

Trong dự án thực tế, implementation của use case sẽ kiểm tra dữ liệu, áp dụng quy tắc nghiệp vụ và gọi repository hoặc domain service. Listener không nên trở thành nơi chứa toàn bộ logic xử lý đơn hàng.

Nếu consumer cần metadata như key, partition, offset hoặc timestamp, có thể nhận `ConsumerRecord<String, OrderCreatedEvent>` hoặc tham số header phù hợp. Chỉ đưa metadata mà nghiệp vụ thực sự cần vào application layer; tránh làm domain phụ thuộc vào kiểu `ConsumerRecord` của Kafka client.

## 7. Đặt cấu hình Kafka ở đâu?

Với Spring Boot, nhiều cấu hình cơ bản có thể khai báo trong `application.yml`; Spring Boot tự tạo các bean cần thiết như `KafkaTemplate` và listener container factory theo cấu hình. Không cần tạo một class `@Configuration` chỉ để bọc lại mọi giá trị mặc định.

Ví dụ cấu hình cho producer và consumer dùng JSON:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: orders-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.acme.orders.order.messaging.contract.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.acme.orders.order.messaging.contract
        "[spring.json.use.type.headers]": false

app:
  kafka:
    topics:
      order-created: orders.created
```

Đây là cấu hình minh họa cho consumer biết trước kiểu payload. Khi tắt việc đọc type header, consumer dùng kiểu mặc định đã khai báo; điều này hữu ích khi producer và consumer không dùng cùng package Java. Trong môi trường thật, hãy cấu hình serializer/deserializer và schema theo hợp đồng được quản lý, không mở rộng trusted packages quá mức cần thiết. Cũng cần thống nhất cách xử lý dữ liệu không hợp lệ và lỗi deserialize.

Khi cần tùy biến sâu, đặt class cấu hình trong `infrastructure.kafka` hoặc package cấu hình chuyên biệt:

| Class hoặc file | Nội dung nên đặt ở đây |
|---|---|
| `application.yml` | Bootstrap servers, serializer/deserializer, consumer group, timeout và các thuộc tính theo môi trường |
| `KafkaProducerConfiguration` | ProducerFactory hoặc KafkaTemplate riêng khi cần nhiều cấu hình producer |
| `KafkaConsumerConfiguration` | ConsumerFactory/listener container factory riêng, concurrency hoặc error handler tùy chỉnh |
| `KafkaTopicConfiguration` | Khai báo `NewTopic` bean nếu ứng dụng có trách nhiệm tạo topic |

Nếu một service có nhiều producer/consumer dùng cấu hình khác nhau, đặt tên bean và factory theo mục đích, ví dụ `orderKafkaTemplate` hoặc `billingListenerContainerFactory`. Không gom mọi trường hợp vào một factory chung rồi thêm nhiều nhánh điều kiện khó theo dõi.

## 8. Tổ chức package cho kiểm thử

Package test nên phản ánh các ranh giới chính của source code:

```text
src/test/java/com/acme/orders
├── order/
│   ├── application/
│   │   └── HandleOrderCreatedUseCaseTest.java
│   └── adapter/kafka/
│       ├── producer/
│       │   └── KafkaOrderEventPublisherTest.java
│       └── consumer/
│           └── OrderCreatedListenerTest.java
└── infrastructure/kafka/
    └── KafkaConfigurationTest.java

src/test/resources
└── application-test.yml
```

- Unit test cho use case kiểm tra quy tắc nghiệp vụ mà không cần Kafka broker.
- Test producer kiểm tra topic, key, payload và cách adapter xử lý send result.
- Test consumer kiểm tra listener chuyển đúng event đến use case và xử lý metadata cần thiết.
- Integration test dùng Embedded Kafka hoặc Testcontainers để xác minh serialization, deserialization, topic, consumer group và luồng gửi nhận thực tế.

Không cần đưa toàn bộ test vào một class kiểm thử lớn cho cả producer lẫn consumer. Tách test theo trách nhiệm giúp xác định nhanh lỗi nằm ở nghiệp vụ, adapter hay cấu hình hạ tầng.

## 9. Những cách tổ chức nên tránh

- **Một package `kafka` chứa tất cả:** khi dự án lớn, publisher, listener, event, config và handler của nhiều feature bị trộn lẫn.
- **Đặt nghiệp vụ trong listener:** listener khó kiểm thử độc lập, khó tái sử dụng và dễ làm chậm luồng poll nếu xử lý quá nhiều việc.
- **Để domain phụ thuộc Kafka:** domain không nên import `KafkaTemplate`, `@KafkaListener`, `ConsumerRecord` hoặc serializer.
- **Dùng entity làm event contract:** thay đổi database mapping có thể vô tình phá vỡ schema mà service khác đang tiêu thụ.
- **Dùng chung implementation giữa các service:** các service chỉ nên chia sẻ contract được quản lý, không chia sẻ repository, entity hoặc logic nội bộ.
- **Tạo quá nhiều package khi chưa có nhu cầu:** một ứng dụng nhỏ không cần nhiều tầng rỗng hoặc interface chỉ để chuyển tiếp một lời gọi.
- **Gộp cấu hình mọi listener vào một class khổng lồ:** khi cần concurrency, retry hoặc deserialization khác nhau, cấu hình riêng theo mục đích sẽ dễ hiểu hơn.

## 10. Checklist trước khi bắt đầu phát triển

- [ ] Xác định service đóng vai trò producer, consumer hay cả hai.
- [ ] Chọn cách tổ chức theo vai trò kỹ thuật hoặc theo feature phù hợp quy mô.
- [ ] Xác định event contract độc lập với entity và schema database.
- [ ] Đặt producer adapter ở biên gửi và consumer adapter ở biên nhận.
- [ ] Để consumer delegate sang application use case.
- [ ] Để application layer gọi port phát event, adapter hiện thực port bằng `KafkaTemplate`.
- [ ] Đặt cấu hình serializer, deserializer, group ID và topic ở vị trí có thể quản lý theo môi trường.
- [ ] Tách unit test, adapter test và integration test.
- [ ] Có quy ước versioning và tương thích schema khi nhiều service cùng dùng event.
- [ ] Xác định cách quan sát lỗi gửi, lỗi deserialize và lỗi xử lý ở consumer.

Một cấu trúc package rõ ràng giúp producer và consumer phát triển độc lập, event contract có thể được quản lý lâu dài và nghiệp vụ ít bị ràng buộc vào Kafka. Khi dự án lớn dần, có thể tách các feature hoặc đưa contract sang module riêng mà không phải viết lại toàn bộ luồng messaging.
