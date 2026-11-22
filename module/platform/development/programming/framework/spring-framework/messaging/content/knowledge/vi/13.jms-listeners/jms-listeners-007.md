# @Payload, @Header, @Headers và kiểm tra hợp lệ đầu vào trong JMS Listener

Khi dùng **@JmsListener**, Spring JMS nhận message từ destination, chuyển body và metadata sang mô hình Spring Messaging, sau đó phân giải các tham số của method listener. Ba annotation **@Payload**, **@Header** và **@Headers** giúp method nhận đúng phần dữ liệu cần xử lý mà không phải tự đọc từng trường từ một jakarta.jms.Message.

Để xử lý đầu vào an toàn, cần phân biệt ba việc:

1. **Chuyển đổi:** biến body JMS thành kiểu Java mà listener yêu cầu.
2. **Binding:** đưa payload và từng header vào đúng tham số method.
3. **Validation:** kiểm tra dữ liệu đã chuyển đổi có đáp ứng các ràng buộc của ứng dụng hay không.

Nếu một bước thất bại, method listener có thể chưa được gọi. Vì vậy, cấu hình converter, header mapping và validator là một phần của hợp đồng nhận message.

## 1. Luồng xử lý trước khi gọi listener

Với listener dùng annotation, Spring tạo message listener container và adapter để nhận message. Một luồng phổ biến:

~~~text
JMS Provider / Broker
       |
       | jakarta.jms.Message
       v
JMS MessageConverter
       |
       | body -> Java payload
       | JMS headers / properties -> Spring headers
       v
Spring Message<?>
       |
       | Method argument resolution
       | @Payload / @Header / @Headers
       v
Validation (@Valid / @Validated)
       |
       v
@JmsListener method
~~~

Mỗi bước có trách nhiệm riêng:

- **JMS MessageConverter** chuyển body từ TextMessage, BytesMessage, MapMessage hoặc ObjectMessage sang object Java.
- **JmsHeaderMapper** ánh xạ các JMS headers và properties thành Spring message headers.
- **@Payload** lấy payload từ Spring Message.
- **@Header** lấy một header cụ thể theo tên.
- **@Headers** lấy toàn bộ headers sau khi mapper xử lý.
- **Validator** kiểm tra các constraint trên payload trước khi method xử lý nghiệp vụ.

Cần nhớ rằng **@Payload không tự parse JSON**. JSON phải được chuyển thành kiểu Java bởi converter được cấu hình trên listener container factory. Tương tự, **@Header** không tự đọc một property bất kỳ từ raw JMS message; property đó phải được mapper đưa vào Spring headers.

## 2. @Payload: lấy dữ liệu chính của message

**org.springframework.messaging.handler.annotation.Payload** đánh dấu tham số nhận payload. Đây là phần body đã được converter chuyển đổi.

Ví dụ listener nhận một chuỗi:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(@Payload String body) {
    System.out.println("body=" + body);
}
~~~

Nếu converter đã chuyển JSON thành DTO, listener có thể nhận trực tiếp DTO:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(@Payload OrderCreated order) {
    orderService.process(order);
}
~~~

Trong method listener, một tham số không được đánh dấu là loại đặc biệt như Spring Message hoặc JMS Session thường được xem là payload ngay cả khi không có @Payload. Viết annotation tường minh giúp người đọc nhận ra tham số nào là body.

### Thuộc tính required

Payload mặc định là bắt buộc. Nếu luồng cho phép message không có payload, có thể dùng:

~~~java
public void receive(@Payload(required = false) String body) {
    if (body == null) {
        return;
    }
    // xử lý body
}
~~~

Với message nghiệp vụ như lệnh tạo đơn hàng, payload thường nên là bắt buộc. Nếu body rỗng hoặc không thể chuyển đổi, nên xử lý như một đầu vào không hợp lệ theo chính sách của consumer.

### Payload DTO và converter

Nếu listener khai báo OrderCreated nhưng converter trả về String, Spring không tự biến chuỗi JSON thành DTO chỉ vì kiểu tham số là OrderCreated. Cần cấu hình một converter JSON tương thích.

Với Spring JMS và Jackson 2, converter thường dùng là **org.springframework.jms.support.converter.MappingJackson2MessageConverter**. Đây là converter của Spring JMS, khác với converter cùng tên trong package Spring Messaging.

## 3. @Header: lấy một metadata cụ thể

**org.springframework.messaging.handler.annotation.Header** dùng để bind một message header vào tham số method.

Ví dụ:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        @Payload String body,
        @Header("eventType") String eventType
) {
    System.out.println("eventType=" + eventType);
    System.out.println("body=" + body);
}
~~~

Ở đây, eventType là một custom JMS property được header mapper chuyển thành Spring header cùng tên. Nếu producer không gửi property đó, tham số mặc định là bắt buộc nên việc phân giải tham số sẽ thất bại trước khi method chạy.

### Header bắt buộc, tùy chọn và giá trị mặc định

Header mặc định là bắt buộc. Có thể thay đổi hành vi:

~~~java
public void receive(
        @Header(name = "eventType") String eventType,
        @Header(name = "tenantId", required = false) String tenantId,
        @Header(name = "source", defaultValue = "unknown") String source
) {
    // tenantId có thể null; source dùng giá trị mặc định nếu thiếu.
}
~~~

- **required = true** là mặc định. Header thiếu khiến Spring không thể phân giải tham số.
- **required = false** cho phép header không có; nên dùng kiểu tham chiếu như String hoặc Long nếu giá trị có thể null.
- **defaultValue** cung cấp giá trị thay thế khi header không có. Đây là lựa chọn phù hợp khi ứng dụng có một giá trị mặc định rõ ràng.

Spring có thể chuyển đổi kiểu header thông qua ConversionService. Ví dụ, một giá trị dạng số được ánh xạ sang tham số Integer hoặc Long nếu có converter phù hợp. Nếu giá trị không thể chuyển đổi, việc bind tham số sẽ thất bại.

### Header JMS tiêu chuẩn qua JmsHeaders

Spring JMS ánh xạ các JMS headers tiêu chuẩn vào Spring message headers theo các tên được định nghĩa trong **org.springframework.jms.support.JmsHeaders**.

| Hằng số | Ý nghĩa |
|---|---|
| **JmsHeaders.MESSAGE_ID** | ID do JMS provider gán cho message. |
| **JmsHeaders.CORRELATION_ID** | JMSCorrelationID, dùng liên kết request/reply hoặc các message liên quan. |
| **JmsHeaders.REPLY_TO** | Destination phản hồi của message. |
| **JmsHeaders.DESTINATION** | Queue hoặc Topic nhận message. |
| **JmsHeaders.TIMESTAMP** | Thời điểm gửi do provider ghi nhận. |
| **JmsHeaders.DELIVERY_MODE** | Persistent hoặc non-persistent. |
| **JmsHeaders.PRIORITY** | Mức ưu tiên JMS. |
| **JmsHeaders.EXPIRATION** | Thời điểm message hết hạn. |
| **JmsHeaders.REDELIVERED** | Cho biết message đã được giao lại. |
| **JmsHeaders.TYPE** | Nhãn kiểu message JMS. |

Nên dùng hằng số thay vì tự viết chuỗi tên header:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        @Header(JmsHeaders.CORRELATION_ID) String correlationId,
        @Header(name = JmsHeaders.MESSAGE_ID, required = false) String messageId
) {
    // correlationId và messageId được lấy từ metadata JMS đã ánh xạ.
}
~~~

Một số JMS headers là giá trị chỉ đọc do provider quản lý. Việc đọc chúng qua Spring header không có nghĩa producer có thể tùy ý ghi đè chúng.

## 4. @Headers: nhận toàn bộ message headers

**org.springframework.messaging.handler.annotation.Headers** bind toàn bộ Spring message headers vào một tham số có kiểu tương thích với Map.

Ví dụ:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        @Payload String body,
        @Headers Map<String, Object> headers
) {
    Object eventType = headers.get("eventType");
    Object correlationId = headers.get(JmsHeaders.CORRELATION_ID);

    System.out.println("eventType=" + eventType);
    System.out.println("correlationId=" + correlationId);
}
~~~

Map chứa các header mà Spring Message đang mang sau khi JMS header mapper thực hiện ánh xạ. Nó có thể gồm:

- JMS metadata tiêu chuẩn như message ID, correlation ID, destination và timestamp.
- Custom JMS properties do producer đặt.
- Metadata nội bộ hoặc metadata được adapter bổ sung trong quá trình xử lý.

Có thể nhận trực tiếp **MessageHeaders** hoặc Spring **Message<?>** nếu muốn truy cập payload và headers cùng lúc:

~~~java
public void receive(Message<OrderCreated> message) {
    OrderCreated order = message.getPayload();
    Object correlationId = message.getHeaders().get(JmsHeaders.CORRELATION_ID);
}
~~~

Dùng @Header khi method chỉ cần một vài trường rõ ràng. Dùng @Headers khi cần kiểm tra nhiều metadata hoặc viết logic tổng quát. Không nên log toàn bộ Map một cách mặc định vì headers có thể chứa thông tin định danh, tenant hoặc dữ liệu nhạy cảm.

## 5. Phân biệt payload, JMS headers và JMS properties

Một JMS message có body, headers và properties. Spring ánh xạ chúng vào Spring Message theo các quy tắc khác nhau:

| Phần trong JMS | Ví dụ | Cách truy cập trong listener |
|---|---|---|
| Body | JSON trong TextMessage | @Payload DTO hoặc String sau conversion |
| JMS header tiêu chuẩn | JMSCorrelationID | @Header(JmsHeaders.CORRELATION_ID) |
| Custom JMS property | eventType, tenantId, schemaVersion | @Header("eventType"), @Headers Map |
| Toàn bộ metadata đã ánh xạ | JMS headers + properties | @Headers Map hoặc MessageHeaders |

Ví dụ producer tạo message có:

~~~text
Body:
  {"orderId":"ORD-1001","total":125.50,"currency":"USD"}

JMS headers:
  JMSCorrelationID = checkout-001

JMS properties:
  eventType = OrderCreated
  tenantId = tenant-42
  schemaVersion = 1
  _type = order-created
~~~

Listener có thể nhận body thành OrderCreated, lấy correlation ID bằng JmsHeaders.CORRELATION_ID và lấy eventType hoặc tenantId bằng tên property.

Không nhầm custom JMS property với field trong JSON. Nếu eventType chỉ nằm trong body JSON, @Header("eventType") sẽ không tìm thấy nó. Nếu muốn dùng @Header, producer phải đặt property hoặc một adapter phải tạo Spring header tương ứng.

## 6. Kiểm tra hợp lệ đầu vào với @Valid

**@Valid** từ Jakarta Bean Validation yêu cầu Spring kiểm tra các constraint trên object payload trước khi gọi method listener.

Ví dụ DTO:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record OrderCreated(
        @NotBlank String orderId,
        @NotNull @DecimalMin("0.01") BigDecimal total,
        @NotBlank @Pattern(regexp = "[A-Z]{3}") String currency
) {
}
~~~

Listener:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(@Payload @Valid OrderCreated order) {
    orderService.process(order);
}
~~~

Các constraint được kiểm tra trước khi method chạy:

- orderId không được null, rỗng hoặc chỉ có khoảng trắng.
- total phải có giá trị và lớn hơn hoặc bằng 0.01.
- currency phải gồm ba chữ cái viết hoa theo quy ước trong ví dụ.

Nếu DTO có object lồng nhau, đặt @Valid trên thuộc tính lồng nhau để validation đi sâu vào object đó:

~~~java
public record OrderCreated(
        @NotBlank String orderId,
        @NotNull @Valid Customer customer
) {
}

public record Customer(
        @NotBlank String customerId,
        @NotBlank String email
) {
}
~~~

### Cấu hình Validator cho JMS listener

Spring dùng **DefaultMessageHandlerMethodFactory** để phân giải tham số của các method @JmsListener. Có thể cấu hình Validator cho factory bằng **JmsListenerConfigurer**.

Ví dụ:

~~~java
@Configuration
@EnableJms
public class ValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean jmsValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean
    public DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory(
            org.springframework.validation.Validator validator
    ) {
        DefaultMessageHandlerMethodFactory factory =
                new DefaultMessageHandlerMethodFactory();
        factory.setValidator(validator);
        return factory;
    }

    @Bean
    public JmsListenerConfigurer jmsListenerConfigurer(
            DefaultMessageHandlerMethodFactory methodFactory
    ) {
        return new JmsListenerConfigurer() {
            @Override
            public void configureJmsListeners(
                    JmsListenerEndpointRegistrar registrar
            ) {
                registrar.setMessageHandlerMethodFactory(methodFactory);
            }
        };
    }
}
~~~

Cần có một implementation Jakarta Bean Validation trên classpath, chẳng hạn Hibernate Validator. **LocalValidatorFactoryBean** kết nối provider Bean Validation với Spring Validator; **DefaultMessageHandlerMethodFactory** dùng validator đó để kiểm tra tham số payload được đánh dấu @Valid hoặc @Validated.

Nếu dự án dùng Spring Framework 6.x, import validation là **jakarta.validation.Valid** và các constraint thuộc **jakarta.validation.constraints**. Dự án Spring Framework 5.3 dùng namespace **javax.validation**; không trộn hai namespace trong cùng một cấu hình.

### @Valid và @Validated

- **@Valid** kích hoạt validation theo Jakarta Bean Validation trên payload.
- **@Validated** của Spring hỗ trợ chỉ định validation groups, ví dụ nhóm Create hoặc Update, khi ứng dụng đã khai báo các group tương ứng.

Validation của payload trong message handler method cần được cấu hình qua message handler method factory như ví dụ trên. Không nên giả định chỉ thêm dependency validation là mọi JMS listener đều tự động dùng validator tùy chỉnh của ứng dụng.

## 7. Header validation và business validation

@Valid thường kiểm tra object payload. Việc bind header có quy tắc riêng:

- Header bắt buộc được kiểm tra bởi required mặc định của @Header.
- Header tùy chọn cần dùng required = false hoặc defaultValue.
- Header có kiểu dữ liệu không chuyển đổi được sẽ gây lỗi khi Spring phân giải tham số.
- Quy tắc nghiệp vụ của header như eventType phải thuộc danh sách được phép cần được kiểm tra rõ ràng trong listener hoặc một validator/service chuyên biệt.

Ví dụ:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        @Payload @Valid OrderCreated order,
        @Header("eventType") String eventType,
        @Header(name = "tenantId", defaultValue = "public") String tenantId
) {
    if (!"OrderCreated".equals(eventType)) {
        throw new IllegalArgumentException("Unsupported eventType");
    }

    if (tenantId.isBlank()) {
        throw new IllegalArgumentException("tenantId must not be blank");
    }

    orderService.process(order, tenantId);
}
~~~

Nếu cần Bean Validation cho tham số method như header, có thể cấu hình method validation riêng bằng Spring method validation và các constraint tương ứng. Không nên cho rằng @Valid trên payload tự động áp dụng cùng quy tắc lên mọi tham số @Header.

## 8. Cấu hình JSON converter và validation trong một JMS listener

Ví dụ dưới đây dùng Java 17, Spring Framework 6.2.19, Jackson 2 và Hibernate Validator. Jackson converter biến JSON TextMessage thành DTO; validator kiểm tra DTO; listener nhận payload và metadata qua ba annotation.

### Maven dependencies

Tạo pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-listener-validation</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.3</version>
        </dependency>

        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>

        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
    </dependencies>
</project>
~~~

Ứng dụng thực tế còn cần JMS provider client và cấu hình ConnectionFactory phù hợp với broker đang dùng. Spring Framework 6.x dùng Jakarta namespace jakarta.jms.

### DTO: OrderCreated.java

~~~java
package com.example.messaging;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record OrderCreated(
        @NotBlank String orderId,
        @NotNull @DecimalMin("0.01") BigDecimal total,
        @NotBlank @Pattern(regexp = "[A-Z]{3}") String currency
) {
}
~~~

### Cấu hình: JmsConfiguration.java

~~~java
package com.example.messaging;

import java.util.Map;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;
import org.springframework.messaging.handler.annotation.support.DefaultMessageHandlerMethodFactory;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public MappingJackson2MessageConverter orderMessageConverter() {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();

        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(
                Map.of("order-created", OrderCreated.class)
        );

        return converter;
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            MappingJackson2MessageConverter converter
    ) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(converter);
        factory.setSessionTransacted(true);

        return factory;
    }

    @Bean
    public JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            MappingJackson2MessageConverter converter
    ) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(converter);
        return template;
    }

    @Bean
    public LocalValidatorFactoryBean jmsValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean
    public DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory(
            Validator validator
    ) {
        DefaultMessageHandlerMethodFactory factory =
                new DefaultMessageHandlerMethodFactory();

        factory.setValidator(validator);
        return factory;
    }

    @Bean
    public JmsListenerConfigurer jmsListenerConfigurer(
            DefaultMessageHandlerMethodFactory methodFactory
    ) {
        return new JmsListenerConfigurer() {
            @Override
            public void configureJmsListeners(
                    JmsListenerEndpointRegistrar registrar
            ) {
                registrar.setMessageHandlerMethodFactory(methodFactory);
            }
        };
    }
}
~~~

Converter dùng **TextMessage** cho JSON và property **_type** để nhận diện loại DTO. Mapping dùng type ID tổng hợp order-created thay vì truyền tên class Java qua broker. Khi nhận message, converter dùng mapping đó để khôi phục OrderCreated.

### Listener: OrderListener.java

~~~java
package com.example.messaging;

import java.util.Map;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

import jakarta.validation.Valid;

@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void receive(
            @Payload @Valid OrderCreated order,
            @Header("eventType") String eventType,
            @Header(name = JmsHeaders.CORRELATION_ID, required = false)
            String correlationId,
            @Header(name = "tenantId", defaultValue = "public")
            String tenantId,
            @Headers Map<String, Object> headers
    ) {
        if (!"OrderCreated".equals(eventType)) {
            throw new IllegalArgumentException("Unsupported eventType");
        }

        if (!Integer.valueOf(1).equals(headers.get("schemaVersion"))) {
            throw new IllegalArgumentException("Unsupported schemaVersion");
        }

        System.out.printf(
                "accepted order=%s total=%s currency=%s eventType=%s correlation=%s tenant=%s%n",
                order.orderId(),
                order.total(),
                order.currency(),
                eventType,
                correlationId,
                tenantId
        );
    }
}
~~~

### Producer gửi message: OrderPublisher.java

~~~java
package com.example.messaging;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish() {
        OrderCreated event = new OrderCreated(
                "ORD-1001",
                new java.math.BigDecimal("125.50"),
                "USD"
        );

        jmsTemplate.convertAndSend(
                "orders.queue",
                event,
                message -> {
                    message.setStringProperty("eventType", "OrderCreated");
                    message.setStringProperty("tenantId", "tenant-42");
                    message.setIntProperty("schemaVersion", 1);
                    message.setJMSCorrelationID("checkout-001");
                    return message;
                }
        );
    }
}
~~~

Producer gửi body JSON cùng các JMS properties:

- **_type = order-created** do MappingJackson2MessageConverter tạo.
- **eventType = OrderCreated** để listener phân loại event.
- **tenantId = tenant-42** để xác định tenant.
- **schemaVersion = 1** để kiểm tra phiên bản hợp đồng.
- **JMSCorrelationID = checkout-001** để truy vết luồng nghiệp vụ.

Khi listener nhận message, Spring chuyển JSON thành OrderCreated, ánh xạ các properties thành headers, kiểm tra constraint của DTO rồi mới gọi receive. Nếu tất cả kiểm tra thành công, output minh họa là:

~~~text
accepted order=ORD-1001 total=125.50 currency=USD eventType=OrderCreated correlation=checkout-001 tenant=tenant-42
~~~

Đây là ví dụ tích hợp cần broker JMS đang chạy, ConnectionFactory và queue orders.queue đã được cấu hình. Output chỉ xuất hiện khi message thực sự được gửi và listener nhận thành công; không thể chạy độc lập chỉ bằng javac/java mà thiếu provider.

## 9. Điều gì xảy ra khi đầu vào không hợp lệ?

Cần phân loại lỗi theo giai đoạn để chọn cách xử lý:

| Giai đoạn | Ví dụ | Kết quả |
|---|---|---|
| JMS conversion | JSON sai cú pháp, thiếu type ID, body không đúng kiểu | Converter ném lỗi; listener method chưa được gọi. |
| Payload binding | Payload không thể chuyển thành kiểu tham số | Spring không phân giải được tham số; method chưa được gọi. |
| Header binding | Thiếu eventType bắt buộc hoặc header không chuyển đổi được | Việc phân giải tham số thất bại; method chưa được gọi. |
| Bean Validation | orderId rỗng hoặc total không hợp lệ | @Valid phát hiện constraint violation trước khi method chạy. |
| Business validation | eventType không được hỗ trợ hoặc schemaVersion sai | Method đã chạy và logic kiểm tra nghiệp vụ chủ động từ chối. |

Trong cấu hình ví dụ, listener container dùng transacted session. Khi lỗi được ném ra trong quá trình xử lý, transaction có thể rollback theo cấu hình container. Provider quyết định redelivery theo chính sách đã cấu hình. Cần có giới hạn redelivery và dead-letter queue/quarantine cho message độc hại hoặc không thể sửa; không retry vô hạn một payload sai schema.

Validation không thay thế xử lý exception. Hãy ghi log có kiểm soát, giữ correlation ID, phân loại lỗi tạm thời và lỗi dữ liệu, đồng thời tránh ghi toàn bộ payload hoặc headers nhạy cảm.

## 10. Những nhầm lẫn thường gặp

1. **“@Payload tự parse JSON.”** Không đúng. JMS MessageConverter phải chuyển body sang DTO trước khi listener nhận payload.
2. **“@Header đọc trực tiếp mọi trường trong JSON body.”** Không đúng. @Header đọc Spring message header đã được mapper tạo từ JMS header/property hoặc metadata khác.
3. **“@Headers nhận body cùng headers.”** Không đúng. Nó nhận Map chứa metadata; body thuộc @Payload hoặc Message.getPayload().
4. **“@Headers có thể dùng với bất kỳ kiểu tham số nào.”** Không đúng. Tham số phải tương thích với Map; MessageHeaders hoặc Message<?> là các cách khác để truy cập metadata.
5. **“@Header thiếu luôn trả null.”** Không đúng. required mặc định là true. Dùng required=false hoặc defaultValue khi header thực sự tùy chọn.
6. **“@Valid tự chạy chỉ vì có Hibernate Validator.”** Cần cấu hình validator cho DefaultMessageHandlerMethodFactory hoặc dùng cấu hình listener phù hợp.
7. **“@Valid trên payload cũng validate tất cả headers.”** Không đúng. Payload validation và header binding là hai việc riêng; quy tắc header cần required/defaultValue, kiểm tra nghiệp vụ hoặc method validation riêng.
8. **“Conversion lỗi và validation lỗi là một.”** Không đúng. Conversion tạo object; validation kiểm tra constraint trên object đã tạo.
9. **“@Headers Map luôn an toàn để log.”** Không đúng. Map có thể chứa correlation, tenant và metadata nhạy cảm.
10. **“Chỉ cần đặt property trong JSON là @Header đọc được.”** Không đúng. Property phải được producer gửi ở JMS properties hoặc adapter ánh xạ thành Spring header.
11. **“Validation thất bại tự động đưa message vào dead-letter queue.”** Không đúng. Redelivery và DLQ là chính sách của listener container/provider/broker, cần cấu hình riêng.
12. **“Spring 6 vẫn dùng javax.validation.”** Không đúng. Spring Framework 6 dùng Jakarta namespace jakarta.validation; Spring 5.3 dùng javax.validation.

## 11. Ghi nhớ

- **@Payload** lấy body đã được JMS MessageConverter chuyển thành kiểu Java.
- **@Header** lấy một metadata theo tên; mặc định header là bắt buộc.
- **@Headers** lấy toàn bộ Spring message headers vào Map.
- **JmsHeaders** cung cấp tên chuẩn cho correlation ID, message ID, destination, reply-to, timestamp và các thuộc tính JMS khác.
- **JmsHeaderMapper** chuyển JMS headers/properties sang Spring headers; custom property có thể được truy cập bằng tên của nó.
- **@Valid** kiểm tra constraint trên payload; cần Validator được cấu hình cho DefaultMessageHandlerMethodFactory.
- Conversion, header binding, Bean Validation và business validation là các lớp kiểm tra khác nhau.
- Với Spring 6.x, dùng jakarta.jms và jakarta.validation; converter JSON của JMS thuộc package org.springframework.jms.support.converter.
- Khi validation hoặc conversion thất bại, xử lý transaction, redelivery và DLQ theo chính sách broker/container.

Khi xây dựng JMS listener, hãy xác định rõ body được chuyển thành kiểu nào, metadata nào bắt buộc, metadata nào tùy chọn và constraint nào phải được kiểm tra trước nghiệp vụ. Một listener có hợp đồng đầu vào rõ ràng giúp phát hiện lỗi sớm và giữ cho consumer an toàn khi nhận message từ nhiều producer.

## Tài liệu tham khảo

- [Spring Framework 6.2.19 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [Spring Framework 6.2 — JmsHeaders API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/JmsHeaders.html)
- [Spring Framework — MappingJackson2MessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html)
- [Spring Framework — DefaultMessageHandlerMethodFactory API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html)
