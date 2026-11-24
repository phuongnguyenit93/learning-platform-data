# Đăng ký binder qua META-INF/spring.binders

Spring Cloud Stream giúp ứng dụng Java xử lý sự kiện qua mô hình hàm `Supplier`, `Function` và `Consumer`. Lớp business logic thường không cần biết message đến từ Kafka, RabbitMQ hay Pulsar: một **binder** chịu trách nhiệm gắn input/output binding với middleware tương ứng. Ngoài những binder có sẵn, framework còn mở rộng bằng Binder SPI để một thư viện có thể cung cấp binder riêng.

Để Spring Cloud Stream **phát hiện một loại binder** trên classpath, thư viện binder phải đóng gói tài nguyên `META-INF/spring.binders`. Tệp này dùng định dạng Java properties, ánh xạ tên binder type tới một hoặc nhiều lớp cấu hình Spring. Các lớp cấu hình khởi tạo bean thực thi giao diện `org.springframework.cloud.stream.binder.Binder` cùng những đối tượng kết nối cần thiết. Khi ứng dụng chọn binder cho một binding, framework dùng thông tin đăng ký đó để tạo và sử dụng binder tương ứng.

Chủ đề thuộc chương **Mở rộng**: đăng ký binder là cách mở rộng Spring Cloud Stream sang một middleware mới hoặc đóng gói reusable adapter. Nó **không tự tăng throughput**, không tự tạo consumer group, không tự bảo đảm retry/DLQ và không thay thế cấu hình destination/partition. Những khả năng đó phải được implementation của binder và broker cung cấp; việc mở rộng số replica còn phụ thuộc mô hình consumer group/subscription thực tế.

> Phiên bản tham chiếu: tài liệu chính thức Spring Cloud Stream 5.1.0. Ví dụ sử dụng Java và tên lớp minh họa trong package `com.example.stream.binder.audit`. Đối với Spring Cloud Stream 4.x/5.x, hãy dùng BOM tương thích với Spring Boot/Cloud hiện tại; không sao chép class/API của release khác nếu chưa kiểm tra.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa `Binder`, binder type, binder configuration, binding name và destination.
- Đặt đúng tệp `src/main/resources/META-INF/spring.binders` trong một module binder.
- Viết entry Java properties ánh xạ tên loại binder tới lớp `@Configuration`.
- Phân biệt discovery qua `spring.binders` với Spring Boot auto-configuration và component scanning.
- Tạo một skeleton custom binder theo `ProvisioningProvider`, `MessageProducer` và `MessageHandler`.
- Cấu hình ứng dụng chọn binder theo type hoặc configuration name.
- Chạy nhiều binder cùng lúc và nhiều kết nối của cùng một binder type.
- Kiểm tra JAR, classpath, metadata và thứ tự khởi động khi không phát hiện binder.
- Hiểu các lỗi trùng binder key, xung đột bean và version không tương thích.
- Thiết kế kiểm thử và vận hành khi đóng gói binder cho nhiều instance/cluster.

## 1. Vì sao cần đăng ký binder?

Giả sử bạn xây dựng ứng dụng:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(order.orderId(), "ACCEPTED");
}
~~~

Hàm chỉ biểu diễn nghiệp vụ. Khi runtime bắt đầu, Spring Cloud Stream phải:

1. Biết input binding của hàm là `acceptOrder-in-0`, output là `acceptOrder-out-0`.
2. Xác định binding nào dùng binder nào.
3. Tạo kết nối producer/consumer và, khi được cấu hình, provision destination ở broker.
4. Chuyển dữ liệu từ broker vào function và gửi kết quả ra broker.
5. Theo dõi lifecycle start/stop, error handling và tài nguyên.

Binder là adapter thực hiện phần kết nối đó. Nếu dependency của binder Kafka hoặc RabbitMQ có mặt, framework có thể phát hiện binder được cung cấp sẵn. Nếu muốn hỗ trợ một middleware nội bộ, một hệ thống event bus đặc thù hoặc một transport tự xây dựng, thư viện custom binder phải giới thiệu chính nó cho Spring Cloud Stream. `META-INF/spring.binders` chính là cơ chế đăng ký loại binder đó.

### 1.1. Hai hướng mở rộng khác nhau

| Nhu cầu | Cách tiếp cận |
|---|---|
| Chỉ cần Kafka, RabbitMQ hoặc Pulsar có binder phù hợp | Thêm dependency binder được hỗ trợ và cấu hình binding |
| Cùng loại broker nhưng hai cluster khác nhau | Tạo nhiều **binder configuration** cùng một type |
| Middleware mới, không có Binder SPI implementation thích hợp | Viết custom Binder và đóng gói `spring.binders` |
| Chỉ muốn transform/routing nghiệp vụ | Viết Function/Consumer, thường **không cần** custom Binder |
| Cần thêm concurrency, partition hoặc instance | Cấu hình broker/binder, không sửa `spring.binders` |

Không tạo custom Binder chỉ để đổi tên topic, thay serializer hay thêm một handler nghiệp vụ. Những việc đó thường đã có extension point ở cấp function hoặc binding.

## 2. Phân biệt năm khái niệm dễ nhầm

| Khái niệm | Ví dụ | Được khai báo ở đâu? |
|---|---|---|
| **Binder type** | `kafka`, `rabbit`, `audit` | Key trong `META-INF/spring.binders` |
| **Binder configuration name** | `auditEast`, `kafkaPrimary` | Key dưới `spring.cloud.stream.binders` |
| **Binding name** | `acceptOrder-in-0` | Chữ ký function hoặc cấu hình `bindings` |
| **Destination** | `orders.created`, `audit.events` | `spring.cloud.stream.bindings.<name>.destination` |
| **Consumer group/subscription** | `order-processing` | Cấu hình consumer binding, semantics theo broker |

Một binder type có thể có nhiều binder configuration. Mỗi binder configuration có thể phục vụ nhiều binding, và mỗi binding có thể trỏ tới destination khác nhau.

Ví dụ:

~~~text
META-INF/spring.binders
   audit --> com.example...AuditBinderConfiguration
                 |
                 v
spring.cloud.stream.binders
   auditEast (type=audit)
   auditWest (type=audit)
                 |
                 v
spring.cloud.stream.bindings
   acceptOrder-out-0 (binder=auditEast, destination=orders.audit)
   retryOrder-out-0  (binder=auditWest, destination=orders.retry)
~~~

`audit` là **binder type** được đăng ký trong JAR. `auditEast` và `auditWest` là tên các instance cấu hình trong ứng dụng. `orders.audit` không phải tên binder mà là destination. Sự tách biệt này là chìa khóa để đọc cấu hình multi-binder.

## 3. Tệp META-INF/spring.binders chứa gì?

`spring.binders` là **Java properties resource**, không phải YAML hay Java class. Nó phải nằm đúng đường dẫn:

~~~text
custom-audit-binder/
  pom.xml
  src/
    main/
      java/
        com/example/stream/binder/audit/
          AuditBinderConfiguration.java
          AuditBinder.java
          AuditProvisioningProvider.java
          ...
      resources/
        META-INF/
          spring.binders
~~~

Nội dung tối thiểu của `src/main/resources/META-INF/spring.binders`:

~~~properties
audit=com.example.stream.binder.audit.AuditBinderConfiguration
~~~

Trong định dạng properties, dấu bằng liên kết key và value. Key `audit` là tên loại binder do bạn đăng ký; value là **tên lớp đầy đủ** (fully qualified class name) của cấu hình Spring tạo bean Binder.

Tài liệu Spring Cloud Stream cũng sử dụng cú pháp xuống dòng:

~~~properties
audit:\
com.example.stream.binder.audit.AuditBinderConfiguration
~~~

Dấu hai chấm là dấu phân cách properties, còn dấu gạch chéo ngược cuối dòng có nghĩa **tiếp tục value ở dòng kế tiếp**. Vì vậy hai cách trên tương đương; không phải đưa ký tự gạch chéo ngược vào tên class.

### 3.1. Đăng ký nhiều binder type

Nếu một thư viện thực sự cung cấp hai Binder implementation khác nhau:

~~~properties
audit=com.example.stream.binder.audit.AuditBinderConfiguration
archive=com.example.stream.binder.archive.ArchiveBinderConfiguration
~~~

Mỗi key đại diện một type riêng. Không dùng cùng key `audit` cho hai implementation không tương thích.

### 3.2. Nhiều configuration class cho một type

Value có thể là danh sách tên configuration class, phân cách bằng dấu phẩy:

~~~properties
audit=com.example.stream.binder.audit.AuditBinderConfiguration,com.example.stream.binder.audit.AuditMetricsConfiguration
~~~

Chỉ thêm lớp phụ khi hiểu bean lifecycle và dependency của nó. Dù dùng một hay nhiều lớp, bộ cấu hình cho một binder type phải tạo **một Binder bean thực tế, rõ ràng**, chứ không tạo nhiều Binder bean cạnh tranh. Nếu `AuditMetricsConfiguration` cũng định nghĩa bean `Binder` thứ hai, việc khởi tạo có thể mơ hồ hoặc thất bại.

### 3.3. Những điều spring.binders không làm

Nội dung file này không:

- Khai báo topic, queue hoặc subscription.
- Chọn broker URL hay credentials.
- Tạo consumer group cho toàn bộ ứng dụng.
- Khởi chạy mọi function trong FunctionCatalog.
- Đăng ký Spring Bean bằng component scan thông thường.
- Định nghĩa schema, retry, DLQ hay transaction.
- Bảo đảm một Binder hoạt động đúng chỉ vì class được tìm thấy.

File chỉ giúp framework **biết cách tải cấu hình của một binder type**. Phần kết nối và xử lý message là trách nhiệm của các bean do cấu hình đó tạo ra.

## 4. Cách Spring Cloud Stream tìm binder trên classpath

Khi khởi động:

~~~mermaid
flowchart TD
    A[Application với binder dependencies] --> B[ClassLoader tìm META-INF/spring.binders]
    B --> C[Đọc key binder type và cấu hình]
    C --> D[Binder type registry]
    D --> E{Ứng dụng chọn binder nào?}
    E -->|Một type phù hợp| F[BinderFactory lấy hoặc tạo Binder]
    E -->|Nhiều type| G[Theo defaultBinder hoặc binding.binder]
    G --> F
    F --> H[Khởi tạo Binder trong context phù hợp]
    H --> I[Bind input/output tới destination]
~~~

Đây là sơ đồ khái niệm của quá trình discovery và tạo Binder. Tên một số lớp nội bộ như `BinderTypeRegistry` hoặc `DefaultBinderFactory` giúp đọc stack trace, nhưng ứng dụng bình thường không phải tự instantiate chúng. API nội bộ có thể thay đổi giữa các phiên bản.

### 4.1. Chỉ có một binder type

Nếu chỉ có một Binder implementation trên classpath và không có cấu hình chọn binder mâu thuẫn, Spring Cloud Stream thường tự chọn Binder đó làm mặc định.

Ví dụ ứng dụng chỉ có dependency Kafka binder. Các binding có thể không cần khai báo `binder: kafka` riêng.

### 4.2. Có nhiều binder type

Nếu có Kafka binder và RabbitMQ binder cùng trên classpath, ứng dụng phải chỉ định binder cho từng binding hoặc một `defaultBinder` phù hợp. Không trông chờ classpath order sẽ chọn đúng middleware theo ý mình.

~~~yaml
spring:
  cloud:
    stream:
      defaultBinder: kafka
      bindings:
        acceptOrder-in-0:
          binder: kafka
          destination: orders.created
          group: order-processors
        acceptOrder-out-0:
          binder: rabbit
          destination: orders.accepted
~~~

`defaultBinder` hữu ích nếu đa số binding dùng cùng middleware, nhưng với bridge xuyên broker nên khai báo `binder` tường minh ở các binding quan trọng để dễ review.

### 4.3. Context riêng cho binder configuration

Khi có cấu hình `spring.cloud.stream.binders.<name>`, Spring Cloud Stream có thể tạo context/environment phù hợp cho binder. Các thuộc tính `type`, `environment`, `inheritEnvironment` và `defaultCandidate` điều khiển cách lựa chọn và khởi tạo.

Không tự cho rằng bean từ binder configuration luôn nằm trong application context chính hoặc mọi property của application đều được kế thừa khi `environment` tách biệt. Nên kiểm tra đúng dependency injection, profiles và cấu hình broker ở context binder.

## 5. Quan hệ với Binder SPI

Giao diện chủ đạo là:

~~~java
public interface Binder<T, C extends ConsumerProperties, P extends ProducerProperties> {
    Binding<T> bindConsumer(
            String destinationName,
            String group,
            T inboundBindTarget,
            C consumerProperties);

    Binding<T> bindProducer(
            String destinationName,
            T outboundBindTarget,
            P producerProperties);
}
~~~

Đây là chữ ký rút gọn để giải thích hợp đồng Binder SPI. Binder chịu trách nhiệm:

- Kết nối target nhận vào với broker hoặc transport (`bindConsumer`).
- Kết nối target phát ra với broker (`bindProducer`).
- Áp dụng consumer group và producer/consumer properties.
- Tạo/đọc destination khi được phép.
- Quản lý lifecycle và giải phóng tài nguyên qua `Binding`.

Các implementation thường mở rộng `AbstractMessageChannelBinder` thay vì viết toàn bộ từ đầu. Binder sẽ kết nối với Spring Messaging/Integration bằng:

| Thành phần | Trách nhiệm |
|---|---|
| `ProvisioningProvider` | Resolve/provision logical destination sang tài nguyên transport |
| `ProducerDestination` | Mô tả đích của producer; có thể hỗ trợ partition |
| `ConsumerDestination` | Mô tả đích của consumer |
| `MessageHandler` | Gửi record ra middleware ở phía producer |
| `MessageProducer` | Nhận record từ middleware rồi đẩy vào message channel |
| `AbstractMessageChannelBinder` | Khung triển khai Binder cho message channels |
| `@Configuration` | Tạo bean Binder cùng các dependency của nó |
| `spring.binders` | Đăng ký tên type và configuration class trên classpath |

### 5.1. Phân chia trách nhiệm

~~~text
Spring Cloud Function
  Supplier / Function / Consumer
                |
                v
Spring Cloud Stream binding
                |
                v
Binder SPI implementation
  +-----------------------------+
  | ProvisioningProvider        |
  | MessageProducer / Handler   |
  | retry/ack/partition support |
  +-----------------------------+
                |
                v
Middleware cụ thể (Kafka, RabbitMQ, Pulsar, custom)
~~~

Không phải mọi Binder hỗ trợ cùng một tập feature. Kafka consumer group và offset commit khác RabbitMQ queue/ack và Pulsar subscription. Một custom Binder phải nêu rõ những semantics mà nó triển khai, không dùng chữ “Binder” như bảo đảm exactly-once chung cho mọi middleware.

## 6. Ví dụ xây dựng skeleton custom binder

Ví dụ sau giả định middleware nội bộ tên **Acme Audit Transport**. Mục tiêu là thấy rõ quan hệ giữa Java class, Spring `@Configuration` và `spring.binders`. Phần transport được để thành extension point bởi một binder thật phải tích hợp client, callback, acknowledgment và lifecycle riêng.

### 6.1. Phụ thuộc của module binder

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream</artifactId>
    </dependency>
</dependencies>
~~~

Quản lý version bằng Spring Cloud release train BOM tương thích ứng dụng. Không tự gán các version Spring Boot, Spring Cloud Stream và Spring Integration khác nhau chỉ vì Maven resolve được.

### 6.2. ProvisioningProvider

Đầu tiên mô tả cách tên destination logic tương ứng đích transport:

~~~java
package com.example.stream.binder.audit;

import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.cloud.stream.provisioning.ProvisioningProvider;

public final class AuditProvisioningProvider
        implements ProvisioningProvider<ConsumerProperties, ProducerProperties> {

    @Override
    public ProducerDestination provisionProducerDestination(
            String name, ProducerProperties properties) {
        return new AuditDestination(validate(name));
    }

    @Override
    public ConsumerDestination provisionConsumerDestination(
            String name, String group, ConsumerProperties properties) {
        return new AuditDestination(validate(name));
    }

    private String validate(String name) {
        if (name == null || !name.matches("[a-zA-Z0-9._-]{1,80}")) {
            throw new IllegalArgumentException("Invalid audit destination");
        }
        return name;
    }
}

final class AuditDestination
        implements ProducerDestination, ConsumerDestination {

    private final String name;

    AuditDestination(String name) {
        this.name = name;
    }

    @Override
    public String getName() {
        return name;
    }

    @Override
    public String getNameForPartition(int partition) {
        return name + "-" + partition;
    }
}
~~~

Ví dụ cho thấy binder có thể validate logical destination. Trong production, provisioner còn phải resolve topic/queue, kiểm tra quyền, tránh tạo tài nguyên ngoài allowlist và map group/partition theo transport thực tế. Phương thức `getNameForPartition` ở đây chỉ minh họa phép đặt tên; nó chưa làm transport hỗ trợ partition.

### 6.3. Khung Binder implementation

Một Binder cho message channel có thể kế thừa `AbstractMessageChannelBinder` và hiện thực hai factory method:

~~~java
package com.example.stream.binder.audit;

import org.springframework.cloud.stream.binder.AbstractMessageChannelBinder;
import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.integration.core.MessageProducer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

public final class AuditBinder extends AbstractMessageChannelBinder<
        ConsumerProperties, ProducerProperties, AuditProvisioningProvider> {

    public AuditBinder(AuditProvisioningProvider provisioner) {
        super(null, provisioner);
    }

    @Override
    protected MessageHandler createProducerMessageHandler(
            ProducerDestination destination,
            ProducerProperties properties,
            MessageChannel errorChannel) {

        // PHẢI thay bằng producer của Acme Audit Transport:
        // serialize message, gửi tới destination và xử lý confirm/error.
        return message -> {
            throw new UnsupportedOperationException(
                    "Implement Audit Transport producer before running");
        };
    }

    @Override
    protected MessageProducer createConsumerEndpoint(
            ConsumerDestination destination,
            String group,
            ConsumerProperties properties) {

        // PHẢI thay bằng MessageProducer kết nối Acme Audit Transport:
        // subscribe theo group, nhận message, xử lý ack và lifecycle.
        throw new UnsupportedOperationException(
                "Implement Audit Transport consumer before running");
    }
}
~~~

**Quan trọng:** đây là skeleton **không có transport**. Code minh họa contract SPI và có thể dùng làm điểm bắt đầu cho module, nhưng **không thể gửi/nhận message** và không được triển khai production trước khi thay các placeholder bằng producer/consumer thực sự.

Để tạo binder vận hành được, tối thiểu phải triển khai:

1. Producer client và xác nhận publish/failure.
2. Consumer receiver và bridge vào Spring Messaging channel.
3. Subscribe/ack/redelivery hoặc checkpoint đúng semantics.
4. Start, stop, cleanup, reconnect và shutdown.
5. Provisioning với ACL, partition, group, retry và resource cleanup.
6. Error handling, metrics/tracing, schema và integration tests.

### 6.4. Cấu hình tạo Binder bean

~~~java
package com.example.stream.binder.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditBinderConfiguration {

    @Bean
    AuditProvisioningProvider auditProvisioningProvider() {
        return new AuditProvisioningProvider();
    }

    @Bean
    AuditBinder auditBinder(AuditProvisioningProvider provisioner) {
        return new AuditBinder(provisioner);
    }
}
~~~

Lớp cấu hình là entrypoint mà `spring.binders` chỉ đến. Framework phải có khả năng tải class và tạo các bean của nó. Nếu client kết nối middleware cần settings hoặc credentials, cấu hình này cũng cần đăng ký client bean/connection factory phù hợp.

Đối với một binder type, hãy có chính xác **một bean Binder** được tạo từ bộ cấu hình đó. Nếu nhiều bean Binder cạnh tranh trong cùng binder context, quá trình chọn implementation có thể mơ hồ. Cũng tránh import trực tiếp cấu hình Binder custom bằng component scan vào application chính khi framework còn tạo binder-specific context, nếu chưa hiểu bean lifecycle; có thể dẫn tới double initialization.

### 6.5. Đăng ký vào META-INF/spring.binders

Đặt tài nguyên:

~~~text
src/main/resources/META-INF/spring.binders
~~~

Nội dung:

~~~properties
audit=com.example.stream.binder.audit.AuditBinderConfiguration
~~~

Đây mới là bước đăng ký **binder type `audit`**. Tên `audit` cần thống nhất với property `type` hoặc `defaultBinder` khi ứng dụng sử dụng nó. Lớp `AuditBinderConfiguration` phải được đóng gói vào cùng JAR hoặc dependency runtime có thể load.

## 7. Phân biệt spring.binders, spring.factories và AutoConfiguration.imports

Spring Boot và các dự án Spring dùng nhiều cơ chế discovery khác nhau:

| Tài nguyên | Vai trò điển hình | Thay thế spring.binders? |
|---|---|---|
| `META-INF/spring.binders` | Khai báo tên binder type và configuration class cho Spring Cloud Stream | Chính là cơ chế đăng ký Binder SPI |
| `META-INF/spring.factories` | Cơ chế SpringFactoriesLoader/extension metadata, từng dùng cho nhiều auto-configuration cũ | **Không** |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Đăng ký Spring Boot auto-configuration ở các dòng Boot hiện đại | **Không** |
| `META-INF/services/...` | Java ServiceLoader cho một interface cụ thể | **Không mặc định** |
| `application.yml` | Khai báo binding, broker properties, binder config name | **Không** |

Một Binder JAR có thể đồng thời chứa `spring.binders` và metadata auto-configuration khác. Nhưng một `@AutoConfiguration` được Spring Boot tải lên không có nghĩa key `audit` đã được Spring Cloud Stream đăng ký trong Binder SPI. Tương tự, một file `spring.binders` đúng có thể chỉ tạo context Binder riêng, không mặc nhiên đưa mọi bean của nó vào main application context.

### 7.1. Không dựa vào @ComponentScan để thay đăng ký type

Một class `@Configuration` có thể được component scan trong application, nhưng binder type registry không vì thế có key `audit`. Hãy dùng resource đúng chuẩn. Nếu mục tiêu chỉ cần một custom client dùng trực tiếp trong business service, không nhất thiết phải viết Binder SPI.

### 7.2. Không coi spring.binders là cấu hình broker

Đừng viết:

~~~properties
# SAI VAI TRÒ:
orders.created=kafka:9092
audit.events=my-queue
~~~

Key trong `spring.binders` là **loại Binder**, value là **tên class cấu hình**. Destination và endpoint broker phải nằm trong application configuration hoặc properties của binder implementation.

## 8. Dùng custom binder trong ứng dụng Spring Cloud Stream

Ứng dụng cần dependency runtime tới JAR binder:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example.stream</groupId>
        <artifactId>acme-audit-binder</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

Coordinates trên chỉ là ví dụ cho artifact do đội phát triển tự phát hành, **không phải một artifact có sẵn trên Maven Central**. Ứng dụng còn cần các dependency Spring Cloud Stream và BOM thích hợp.

Khi chỉ có binder type `audit` trên classpath và mọi binding đều dùng nó:

~~~yaml
spring:
  cloud:
    function:
      definition: auditEvent
    stream:
      defaultBinder: audit
      bindings:
        auditEvent-in-0:
          destination: audit.input
          group: audit-workers
        auditEvent-out-0:
          destination: audit.output
~~~

Function minh họa:

~~~java
@Bean
Function<AuditEvent, AuditEvent> auditEvent() {
    return event -> event;
}
~~~

Lưu ý: skeleton `AuditBinder` ở mục 6 cố ý chưa kết nối transport. Cấu hình trên chỉ chạy thành công sau khi Binder đã hoàn thiện producer/consumer implementations và properties kết nối.

### 8.1. Binder type khác binder configuration name

Khi có nhiều kết nối của cùng một type:

~~~yaml
spring:
  cloud:
    function:
      definition: auditEvent
    stream:
      bindings:
        auditEvent-in-0:
          binder: auditEast
          destination: audit.input
          group: audit-workers
        auditEvent-out-0:
          binder: auditWest
          destination: audit.output
      binders:
        auditEast:
          type: audit
          environment:
            audit:
              transport:
                endpoint: https://audit-east.internal
        auditWest:
          type: audit
          environment:
            audit:
              transport:
                endpoint: https://audit-west.internal
~~~

Ở đây:

- `audit` là type do JAR `spring.binders` công bố.
- `auditEast` và `auditWest` là configuration names do ứng dụng định nghĩa.
- `auditEvent-in-0.binder` phải tham chiếu **configuration name** `auditEast`, không nhầm với tên destination.
- Hai ví dụ `audit.transport.endpoint` chỉ có tác dụng nếu Binder custom thực sự khai báo và đọc property đó.

**Cảnh báo:** khi bật explicit binder configuration, quá trình cấu hình binder mặc định bị thay thế; phải khai báo đầy đủ tất cả binder được ứng dụng dùng. Đừng chỉ khai báo `auditEast` rồi trông chờ Kafka/Rabbit binder khác tự xuất hiện nếu configuration đã chuyển sang explicit mode.

### 8.2. Bốn property quan trọng

| Property | Ý nghĩa | Giá trị/ghi chú |
|---|---|---|
| `spring.cloud.stream.binders.<name>.type` | Loại Binder | Key của `spring.binders`; mặc định bằng config name |
| `spring.cloud.stream.binders.<name>.environment` | Properties của môi trường binder | Dùng để cấu hình endpoint, credentials, profiles... |
| `spring.cloud.stream.binders.<name>.inheritEnvironment` | Kế thừa môi trường application hay không | Mặc định `true` |
| `spring.cloud.stream.binders.<name>.defaultCandidate` | Có được xem là binder mặc định hay không | Mặc định `true` |

Nếu một framework/plugin thêm binder phục vụ mục đích đặc biệt nhưng không muốn ảnh hưởng chọn default binder:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        auditIsolated:
          type: audit
          defaultCandidate: false
~~~

Binder này chỉ được dùng khi được tham chiếu phù hợp. Với nhiều binder, đặt `binder` rõ ở từng input/output binding để tránh ambiguity.

## 9. Ví dụ Kafka và Rabbit binder cùng classpath

Trường hợp thông dụng hơn custom binder là kết hợp các binder được phát hành sẵn:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream-binder-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream-binder-rabbit</artifactId>
    </dependency>
</dependencies>
~~~

Để BOM quản lý version, không tự thêm version khác dòng. Mỗi artifact binder mang `spring.binders` của nó trong JAR.

~~~yaml
spring:
  cloud:
    function:
      definition: orderBridge
    stream:
      bindings:
        orderBridge-in-0:
          binder: kafka
          destination: orders.created
          group: order-bridge
        orderBridge-out-0:
          binder: rabbit
          destination: orders.forwarded
~~~

`spring.binders` giúp framework phát hiện **hai binder type**. `bindings.*.binder` chọn loại/một configuration cụ thể cho mỗi binding. Điều đó không làm hai broker chung transaction: từ Kafka sang RabbitMQ vẫn cần thiết kế xác nhận nguồn, publish đích, idempotency hoặc outbox/inbox để quản lý lỗi và duplicate.

### 9.1. Khi nào không cần thêm spring.binders vào ứng dụng?

Nếu dùng binder Kafka/Rabbit/Pulsar có sẵn, application thông thường **không cần tự tạo** `src/main/resources/META-INF/spring.binders`. Resource đúng đã nằm trong binder dependency.

Tạo file này trong application với key `kafka` chỉ để chỉ lại class có sẵn có thể gây trùng định nghĩa hoặc thay đổi resolution. Hãy chỉ viết file mới khi bạn phát hành một **binder implementation** riêng, hoặc có yêu cầu extension đã được thiết kế và thử nghiệm kỹ.

## 10. Đóng gói JAR để resource có thể được phát hiện

Khi build một Maven/Gradle module tiêu chuẩn, `src/main/resources` được copy vào classpath output và JAR.

JAR của binder phải chứa ít nhất:

~~~text
META-INF/spring.binders
com/example/stream/binder/audit/AuditBinderConfiguration.class
com/example/stream/binder/audit/AuditBinder.class
com/example/stream/binder/audit/AuditProvisioningProvider.class
...
~~~

Kiểm tra bằng JDK `jar`:

~~~bash
jar tf target/acme-audit-binder-1.0.0.jar
~~~

Tìm `META-INF/spring.binders` trong danh sách. Với PowerShell:

~~~powershell
jar tf target/acme-audit-binder-1.0.0.jar |
  Select-String 'META-INF/spring.binders|AuditBinderConfiguration.class'
~~~

Với Spring Boot executable JAR sử dụng nested dependencies, binder JAR thường nằm dưới `BOOT-INF/lib/`. Việc không thấy `META-INF/spring.binders` ở **root** của application fat JAR không đồng nghĩa file mất; phải kiểm tra JAR bên trong hoặc truy vấn resource bằng runtime classloader.

### 10.1. Maven Shade và resource merge

Nếu đóng gói uber-JAR bằng Maven Shade hoặc cơ chế tương tự, nhiều dependency có thể cùng chứa file tên `META-INF/spring.binders`. Không được để quá trình shading vô tình **ghi đè một file bằng file khác**. Phải cấu hình cơ chế merge resource thích hợp và kiểm tra file kết quả chứa đủ các key không trùng.

Với ứng dụng Spring Boot thông thường, nên giữ binder như dependency JAR bình thường và để Boot repackaging xử lý classpath, thay vì gộp thủ công các resource. Tùy bản build plugin, việc gộp resource có thể cần cấu hình khác; xác minh artifact sau build là bước bắt buộc.

### 10.2. Xung đột key giữa các JAR

Nếu hai JAR đều có:

~~~properties
audit=com.vendor.a.AuditBinderConfiguration
~~~

và:

~~~properties
audit=com.vendor.b.AnotherAuditBinderConfiguration
~~~

thì type `audit` bị xung đột. Kết quả discovery có thể lỗi hoặc phụ thuộc cách registry xử lý duplicate. Không thiết kế dựa vào thứ tự classpath để “thắng” một key. Hãy đặt key đủ đặc thù, loại dependency thừa hoặc đổi binder type trước khi đóng gói.

### 10.3. Resource phải nằm ở runtime classpath

Các lỗi thường gặp:

- File nằm tại `src/test/resources`, nên chỉ xuất hiện khi chạy test.
- Dependency binder có scope `test` hoặc `provided`, không có trong runtime image.
- Resource bị exclude bởi build plugin.
- Tên file sai chữ hoa/thường, ví dụ `spring.binder` thay vì `spring.binders`.
- File nằm ở root `spring.binders`, thiếu `META-INF/`.
- Jar có metadata nhưng thiếu class `AuditBinderConfiguration` do shading/exclusion.

Filesystem trên Linux phân biệt chữ hoa/thường; tên resource phải chính xác.

## 11. Kiểm tra resource qua ClassLoader

Nếu nghi ngờ JAR được đóng gói sai, có thể liệt kê tất cả resource `META-INF/spring.binders` mà runtime classloader nhìn thấy:

~~~java
import java.net.URL;
import java.util.Collections;
import java.util.Enumeration;

public final class BinderResourceInspector {

    public static void printResources() throws Exception {
        ClassLoader loader =
                Thread.currentThread().getContextClassLoader();

        Enumeration<URL> urls =
                loader.getResources("META-INF/spring.binders");

        for (URL url : Collections.list(urls)) {
            System.out.println("Found binder metadata: " + url);
        }
    }
}
~~~

Phương thức này **chỉ chẩn đoán resource**, không đăng ký Binder mới. Đừng biến output trên thành log mặc định trong production nếu URL chứa đường dẫn nhạy cảm; dùng ở local/test hoặc debug được kiểm soát.

### 11.1. Test kiểm tra entry cụ thể

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.net.URL;
import java.util.Collections;
import java.util.Properties;

import org.junit.jupiter.api.Test;

class BinderMetadataTest {

    @Test
    void auditBinderTypeIsVisible() throws Exception {
        var loader = getClass().getClassLoader();
        var urls = Collections.list(
                loader.getResources("META-INF/spring.binders"));

        boolean found = false;
        for (URL url : urls) {
            Properties properties = new Properties();
            try (InputStream input = url.openStream()) {
                properties.load(input);
            }
            if ("com.example.stream.binder.audit.AuditBinderConfiguration"
                    .equals(properties.getProperty("audit"))) {
                found = true;
                break;
            }
        }

        assertTrue(found, "audit binder metadata must be on classpath");
    }
}
~~~

Test này chỉ chứng minh resource và property key tồn tại. Nó **không chứng minh** Binder bean được tạo thành công hoặc transport hoạt động. Cần thêm context startup test và integration test.

## 12. Test khởi tạo binder và integration test

Một test tốt đi qua nhiều mức:

| Mức | Nội dung | Kết luận có thể rút ra |
|---|---|---|
| Metadata test | File `META-INF/spring.binders` tồn tại, key/value đúng | Binder type có thể được discovery |
| ApplicationContext test | Class cấu hình tải được và tạo đúng một Binder bean | Wiring Spring cơ bản đúng |
| BinderFactory test | Yêu cầu binder theo tên/type lấy được implementation mong muốn | Registry và selection hoạt động |
| Producer test | Output binding gửi message tới transport | Producer path hoạt động |
| Consumer test | Input binding nhận message qua group/subscription | Consumer path hoạt động |
| Failure test | Broker ngắt, nack, redelivery, retry, shutdown | Reliability semantics được kiểm chứng |
| Multi-binder test | Kafka/Rabbit/custom binder cùng classpath | Không collision và chọn đúng binder |
| Packaged-app test | Chạy executable JAR/container image | Resource còn nguyên trong artifact cuối |

### 12.1. Kiểm thử BinderFactory

Trong application context có Spring Cloud Stream:

~~~java
@Autowired
BinderFactory binderFactory;

@Test
void customBinderCanBeResolved() {
    Binder<?, ?, ?> binder =
            binderFactory.getBinder("audit", MessageChannel.class);

    assertNotNull(binder);
}
~~~

Đoạn code minh họa việc lấy Binder theo tên cấu hình/type trong trường hợp một binder type `audit` đơn lẻ. Với `auditEast` hoặc `auditWest`, phải truyền tên **binder configuration** tương ứng. Kiểm tra generic method/API theo version Spring Cloud Stream của project; test thực tế cần khởi tạo context với Binder đã hoàn thiện, vì skeleton cố ý ném lỗi khi bắt đầu binding.

### 12.2. Kiểm thử cả producer và consumer

Để tránh test xanh giả, với custom transport hãy kiểm tra:

1. Producer gửi event có `eventId` và schema hợp lệ tới đúng destination.
2. Consumer dùng group/subscription và nhận message đúng một lần theo semantics đã công bố, hoặc xử lý duplicate an toàn.
3. Consumer stop/start không làm mất message chưa được xác nhận.
4. Retry và DLQ được triển khai nếu Binder tuyên bố hỗ trợ.
5. Partition key/ordering hoạt động nếu Binder hỗ trợ partition.
6. Authentication, ACL và TLS bị từ chối đúng khi credentials không hợp lệ.
7. Nhiều replica cùng chạy không tạo race hoặc duplicate side effect ngoài thiết kế.

Spring Cloud Stream Test Binder giúp test function/binding logic, nhưng **không thay thế** integration test của một Binder implementation mới vì nó không dùng transport thật.

## 13. Troubleshooting: lỗi không nhận diện binder

Khi application khởi động lỗi, hãy kiểm tra theo thứ tự.

### 13.1. Binder type không được tìm thấy

Triệu chứng: log đề cập không có binder phù hợp, unknown binder type, hoặc `BinderFactory` không thể tạo tên được yêu cầu.

Kiểm tra:

1. Dependency binder có thực sự trong **runtimeClasspath**?
2. JAR có `META-INF/spring.binders` đúng chữ hoa/thường?
3. Key trong file có đúng `audit` không?
4. `spring.cloud.stream.binders.<name>.type` có trỏ tới key đó?
5. File resource có bị shading làm mất hoặc bị trùng key không?

Không sửa bằng cách cho tất cả binding tự động dùng một binder khác mà chưa hiểu routing; điều đó có thể gửi message sang middleware sai.

### 13.2. Configuration class không load được

Triệu chứng: `ClassNotFoundException` hoặc `NoClassDefFoundError` khi framework tải configuration.

Nguyên nhân:

- Giá trị trong `spring.binders` sai package/class name.
- JAR chứa file properties nhưng thiếu class.
- Một dependency bắt buộc của configuration/transport client bị exclude.
- Binder được compile với API Spring Cloud Stream khác phiên bản runtime.

Giải pháp: so class name với package khai báo, kiểm tra JAR, dependency tree và release train. Không che lỗi bằng catch-all khiến Binder hoạt động nửa vời.

### 13.3. Có nhiều Binder bean

Triệu chứng: wiring mơ hồ hoặc không chọn được Binder implementation.

Nguyên nhân: configuration import thêm Binder khác hoặc các cấu hình chung tạo nhiều bean `Binder` trong binder-specific context. Tách configuration và chỉ để một bean Binder cho mỗi binder type. Xem `@ConditionalOnMissingBean` và `@ComponentScan` có vô tình mở rộng phạm vi quá mức không.

### 13.4. Mặc định chọn sai binder

Triệu chứng: binding gửi tới RabbitMQ thay vì Kafka hoặc startup báo nhiều binder candidates.

Giải pháp:

- Đặt `spring.cloud.stream.defaultBinder` nếu thực sự có một default rõ ràng.
- Ưu tiên cấu hình `bindings.<bindingName>.binder` cho input/output quan trọng.
- Với explicit binder configurations, tham chiếu configuration name (ví dụ `kafkaEast`), không chỉ type key.
- Dùng `defaultCandidate: false` với binder không muốn tham gia default selection.

### 13.5. Binder được phát hiện nhưng kết nối broker thất bại

Đây là lỗi **sau discovery**, không phải lỗi `spring.binders`. Kiểm tra broker URL, DNS, TLS, credentials, topic/queue existence, ACL, timeout và khả năng network. Binder custom phải report lỗi health/reconnect có ý nghĩa thay vì tự khởi động “thành công” rồi bỏ message.

### 13.6. Chạy IDE được, chạy fat JAR lỗi

Đây thường là khác biệt classpath/packaging. Kiểm tra dependency scope và resource merge; sử dụng executable JAR/image thật trong integration test. Đừng xác minh chỉ bằng IDE run configuration.

## 14. Bảng lỗi thường gặp

| Sai sót | Hậu quả | Cách khắc phục |
|---|---|---|
| Đặt file ở `resources/spring.binders` | Không được discovery | Chuyển đúng `META-INF/spring.binders` |
| Dùng YAML trong spring.binders | Key/value bị parse sai | Dùng Java properties |
| Value là tên Binder class thay vì configuration | Không có bean Binder được tạo | Trỏ tới `@Configuration` |
| Đặt key là tên topic | Binder type không nhất quán | Key phải là type như `audit` |
| JAR không chứa file resource | Runtime không thấy binder | Kiểm tra package/artifact |
| Trùng type key với thư viện khác | Collision/mơ hồ | Dùng tên type riêng |
| Hai Binder bean trong cùng type | Bean resolution lỗi | Chỉ tạo một Binder bean |
| Thiếu dependency client/runtime | Class loading hoặc connection lỗi | Quản lý dependency theo BOM |
| Quên `binding.binder` khi có nhiều types | Chọn nhầm hoặc ambiguous | Chọn rõ từng binding |
| Nhầm type và config name | Lookup binder sai | Kiểm tra `binders.<name>.type` |
| Dùng custom binder skeleton chưa triển khai transport | Startup/binding/send lỗi | Hoàn thiện producer/consumer |
| Chỉ test metadata | Không phát hiện bug vận chuyển message | Thêm integration/failure tests |
| Tự gộp JAR làm mất spring.binders | Binder biến mất trên production image | Kiểm tra merge và JAR cuối |
| Cho rằng binder đã đăng ký là tự scale được | Nhiều instance có thể xử lý trùng hoặc mất message | Thiết kế group, ack, partition, idempotency |

## 15. Liên hệ với khả năng mở rộng và triển khai

`spring.binders` được đọc từ classpath của **mỗi instance ứng dụng**, không phải registry lưu ở Kafka/RabbitMQ/Pulsar broker. Khi scale từ 2 lên 5 Pod, cả 5 image phải chứa cùng binder artifact và metadata tương thích.

~~~text
Image v1 + acme-audit-binder-1.0.jar
    |        |        |
  Pod A    Pod B    Pod C
    \        |        /
         Acme Audit Transport
~~~

Nếu Pod A dùng binder 1.0 còn Pod B dùng binder 2.0, chúng có thể hiểu schema, destination hoặc ack khác nhau. Rolling update cần kiểm thử khả năng cùng tồn tại giữa hai phiên bản, không chỉ kiểm tra file `spring.binders`.

### 15.1. Registration không thay thế consumer group

| Nền tảng | Yêu cầu scale vẫn phải xử lý |
|---|---|
| Kafka binder | Consumer group, partition assignment, offset commit, rebalance |
| RabbitMQ binder | Queue semantics, prefetch, consumer ack, redelivery |
| Pulsar binder | Subscription type, backlog, ack/redelivery, partition/key ordering |
| Custom binder | Tự định nghĩa group/sharing, checkpoint, retry, partition, shutdown |

Một Binder đăng ký thành công nhưng mọi replica cùng subscribe ở chế độ broadcast có thể làm một event được xử lý nhiều lần. Ngược lại, một Binder đặt một khóa lock toàn cục có thể làm mọi replica khác idle. Khả năng scale thực sự phụ thuộc middleware và cách Binder sử dụng nó.

### 15.2. Bảo mật và quyền vận hành

Binder là plugin Java chạy trong JVM của ứng dụng. Một JAR binder không đáng tin có thể chạy mã với quyền của service account. Vì vậy:

- Chỉ dùng binder từ nguồn và version đã review.
- Scan dependency và lock artifact versions.
- Không cho người dùng cuối tải JAR mới vào runtime.
- Cấp broker ACL theo principle of least privilege.
- Không cấp quyền tạo mọi topic/queue chỉ để “provision cho dễ”.
- Giữ secret khỏi source code, log và `spring.binders`.
- Theo dõi số connection, destination, retry, DLQ và lỗi client của binder.

### 15.3. Dấu hiệu vận hành cần quan sát

- Binder startup/initialization errors.
- Thời gian bind consumer/producer.
- Consumer lag hoặc queue depth theo broker.
- Tỷ lệ publish success/failure và acknowledgment.
- Số lần reconnect, rebalance, retry và dead-letter.
- Thời gian graceful shutdown và message còn dang dở.
- Sự khác biệt binder version giữa các Pod.

Để sửa lỗi “binder không được tìm thấy”, không cần tăng replica hay concurrency: đây là vấn đề artifact/registry. Để sửa lag hoặc backlog, phải điều tra throughput, broker và consumer semantics, không sửa `spring.binders`.

## 16. Checklist đăng ký một binder mới

Trước khi phát hành:

1. Chọn một binder type key duy nhất, có ý nghĩa và ổn định.
2. Triển khai Binder SPI hoặc kế thừa `AbstractMessageChannelBinder`.
3. Cung cấp `ProvisioningProvider` và producer/consumer endpoints.
4. Xác định transaction, acknowledgment, ordering, partition và retry semantics.
5. Tạo `@Configuration` sinh đúng một bean `Binder`.
6. Đặt file đúng `src/main/resources/META-INF/spring.binders`.
7. Ánh xạ key tới FQCN của configuration, không phải Binder class.
8. Kiểm tra Java properties parse được, không có key collision.
9. Căn version với Spring Cloud Stream/BOM đang sử dụng.
10. Đóng gói Binder JAR và kiểm tra resource/class nằm trong artifact.
11. Thêm dependency JAR vào runtime classpath của consumer application.
12. Khai báo `spring.cloud.stream.binders.<name>.type` khi dùng explicit configurations.
13. Chọn `bindings.<bindingName>.binder` cho từng binding quan trọng.
14. Chạy metadata, context, BinderFactory và transport integration tests.
15. Chạy test packaged application, multi-binder, failover và multi-replica.
16. Triển khai bằng artifact version đã pin, theo dõi health và backlog.

## Kết luận

`META-INF/spring.binders` là điểm đăng ký loại binder trong Spring Cloud Stream: mỗi key khai báo một binder type, còn value liệt kê lớp cấu hình Spring có nhiệm vụ tạo Binder bean và hạ tầng kết nối. Tệp phải nằm trên runtime classpath của thư viện binder, được đóng gói nguyên vẹn trong JAR và dùng đúng định dạng Java properties.

Đừng nhầm key trong `spring.binders` với tên binder configuration, binding name hay broker destination. Dùng `spring.cloud.stream.binders.<name>.type` để trỏ tới binder type và `spring.cloud.stream.bindings.<bindingName>.binder` để chọn configuration cho một binding. Khi có nhiều binder, cấu hình chúng tường minh và kiểm tra dependency, classpath, bean wiring, broker access cùng tích hợp thực tế. Việc đăng ký thành công chỉ là bước đầu của Binder SPI; khả năng scale, retry/DLQ, partition và bảo đảm giao nhận phải được thực hiện và kiểm thử riêng.

## Tài liệu tham khảo

- [Spring Cloud Stream — Binder SPI](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-binder-api.html)
- [Spring Cloud Stream — Implementing Custom Binders](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-custom-binder-impl.html)
- [Spring Cloud Stream — Binder Detection](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-detection.html)
- [Spring Cloud Stream — Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html)
- [Spring Cloud Stream — Connecting to Multiple Systems](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-systems.html)
- [Spring Cloud Stream — Binder Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-configuration-properties.html)
