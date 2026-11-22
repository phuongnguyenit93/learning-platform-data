# Lỗi chuyển đổi hoặc validation trước khi mã nghiệp vụ chạy trong Spring JMS

> **Module:** Spring Framework – JMS  
> **Nhóm:** Dữ liệu listener  
> **Trọng tâm:** Vì sao một message đã tới `@JmsListener` container nhưng method nghiệp vụ **chưa hề được gọi**, cách xác định lỗi nằm ở tầng nào và thiết kế rollback, retry, DLQ an toàn.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Trình bày chuỗi xử lý từ `jakarta.jms.Message` → chuyển đổi wire payload → Spring `Message<?>` → giải quyết tham số → Bean Validation → gọi method `@JmsListener`.
2. Phân biệt **conversion error**, **header/method-argument error** và **validation error** xảy ra **trước khi** dòng đầu tiên trong method nghiệp vụ chạy.
3. Nhận ra `MessageConversionException` của `spring-jms` khác với lỗi chuyển đổi của Spring Messaging; `MethodArgumentNotValidException` có thể được bọc thành `ListenerExecutionFailedException`.
4. Cấu hình converter và `@Payload @Valid` bằng `DefaultJmsListenerContainerFactory`, `JmsListenerConfigurer`, `DefaultMessageHandlerMethodFactory` và một `Validator` hoạt động thật.
5. Giải thích vì sao `try/catch` **bên trong body method listener** không thể bắt lỗi xảy ra trước khi method được gọi.
6. Hiểu chính xác ảnh hưởng của `sessionTransacted=true`, `AUTO_ACKNOWLEDGE`, redelivery, broker DLQ và `ErrorHandler`; không khẳng định mọi ngoại lệ đều tự đi DLQ.
7. Tách lỗi dữ liệu cố định (poison message) khỏi lỗi hạ tầng tạm thời để áp retry hữu hạn, quarantine và cơ chế sửa/replay có kiểm soát.
8. Kiểm thử hai tình huống tiêu biểu: JSON sai cú pháp và DTO hợp lệ về JSON nhưng vi phạm `@NotBlank`/`@Positive`, đồng thời chứng minh business method chưa chạy.
9. Quan sát lỗi ngay tại adapter/container, correlation ID, message type/schema, lỗi nguyên nhân gốc và delivery count mà không log payload nhạy cảm.

## 1. Bản chất vấn đề: có message nhưng handler không chạy

Một lỗi phổ biến khi vận hành Spring JMS:

> Broker hiển thị message đã được giao (hoặc tăng delivery count), listener container vẫn chạy, nhưng không thấy log dòng đầu tiên của `@JmsListener`. Ở phía broker, message có thể lặp lại, tăng redelivery count hoặc đi vào DLQ.

Không nhất thiết do network hoặc method nghiệp vụ “nuốt exception”. Một **method listener có tham số kiểu cụ thể** phải được Spring chuẩn bị trước khi invocation. Nếu chuẩn bị đối số thất bại, method **chưa được gọi một lần nào**.

```text
JMS Broker
   |
   | 1. Deliver jakarta.jms.Message
   v
DefaultMessageListenerContainer / Session
   |
   | 2. MessagingMessageListenerAdapter
   |    -> JMS MessageConverter (body + metadata)
   v
Spring Message<?> (payload + headers)
   |
   | 3. Resolve method arguments
   |    -> @Payload / @Header / MessageConverter / target type
   v
Typed Java arguments
   |
   | 4. @Valid / @Validated nếu có Validator
   |    -> Bean Validation constraints
   v
@JmsListener method body
   |
   | 5. Business validation, database, outbound calls...
   v
Ack / commit hoặc rollback theo container policy
```

**Ba điểm lỗi trước method:**

- **Bước 2:** Không thể chuyển JMS TextMessage/BytesMessage/MapMessage thành Java payload, JSON malformed, thiếu type-id, type-id không thuộc mapping, body không đúng kiểu.
- **Bước 3:** Không thể biến payload đã decode thành kiểu tham số `OrderCreated`, thiếu header bắt buộc, sai kiểu `@Header int`, không có converter phù hợp.
- **Bước 4:** Java DTO đã tạo được nhưng vi phạm ràng buộc `@Valid`, ví dụ `orderId` rỗng hoặc `quantity` không dương.

**Bước 5** mới là code ứng dụng tự viết trong method. Phải xác định đường lỗi trước khi chọn cách sửa. Một exception từ conversion/validation có thể bị adapter ném trở ra container **với method body chưa được thực thi**.

## 2. “Trước business” không phải “trước JMS receive”

Có ba sự kiện khác nhau:

1. Broker giao message cho JMS consumer/session.
2. Spring adapter chuyển đổi, resolve arguments và validate để chuẩn bị gọi handler.
3. Method ứng dụng được invoke, thực thi side effect.

Nếu lỗi ở (2), broker/provider và container **có thể đã tính đó là một delivery attempt**. Vì vậy:

- Message có thể đã chuyển từ ready sang in-flight trong broker.
- Transaction có thể rollback, dẫn tới redelivery message đó.
- `JMSRedelivered` hoặc `JMSXDeliveryCount` có thể thay đổi khi broker gửi lại, tùy support và policy.
- Không có log “handler started”, nhưng message vẫn có thể bị consume/ack nếu container đang dùng acknowledgment mode không phù hợp cho retry.
- Không nên suy từ `handlerCallCount=0` rằng broker chưa từng gửi message.

**Từ “trước” ở đây chỉ nghĩa là trước khi body method nghiệp vụ chạy**, không nghĩa là message chưa rời broker.

### 2.1. Hai cách viết listener cho hai mức kiểm soát

Listener nhận raw JMS Message:

```java
@JmsListener(destination = "orders.in")
public void raw(jakarta.jms.Message message) {
    // Ứng dụng tự kiểm tra JMS type và đọc body.
}
```

Listener nhận typed DTO:

```java
@JmsListener(destination = "orders.in")
public void typed(@Payload @Valid OrderCreated order) {
    // Spring phải chuẩn bị OrderCreated và validate trước lúc vào đây.
}
```

Đây là **hai chữ ký minh họa riêng biệt**. Nếu dùng cả hai trên cùng Queue, họ trở thành competing consumers; không phải cả hai cùng thấy mỗi message. Raw listener giảm chuyển đổi tự động trước handler, nhưng đẩy trách nhiệm decode/validation sang **code nghiệp vụ hoặc adapter riêng**. Không có một kiểu handler “an toàn tuyệt đối”.

### 2.2. @Valid có thể khiến method không được invoke

Khi `@Payload` argument đi qua `PayloadMethodArgumentResolver` với một `Validator` đã cấu hình, resolver kiểm tra các constraint trước khi gọi method. Vi phạm có thể gây `org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException`. Ở adapter phía JMS, exception có thể được bọc bởi `ListenerExecutionFailedException`, vì thế log ở container thường có **wrapper** bên ngoài và **root cause** bên trong.

Không nhìn duy nhất dòng exception đầu tiên rồi quyết định lỗi ở business handler. Hãy lần theo `cause` chain và frame conversion/argument resolver.

## 3. Phân loại các dạng lỗi theo giai đoạn

| Giai đoạn | Ví dụ lỗi | Method body có chạy chưa? | Điều cần kiểm tra |
| --- | --- | --- | --- |
| JMS consumer receive | Broker connection đứt, destination/permission lỗi | Chưa | Network, credentials, broker, container recovery |
| JMS wire conversion | TextMessage chứa JSON sai cú pháp | **Chưa** | JMS converter, payload, schema, encoding |
| JMS wire conversion | Missing/unknown `_type` của Jackson JMS converter | **Chưa** | Type-id property, allowlist mapping, version |
| JMS wire conversion | BytesMessage nhận ở converter chỉ chấp nhận TextMessage | **Chưa** | JMS message subtype, converter target type |
| Spring argument resolution | Payload là String nhưng handler đòi DTO, không có converter | **Chưa** | Spring Messaging converter, target type |
| Header binding | `@Header("attempt") int n` nhưng header thiếu/sai kiểu | **Chưa** | JMS/Spring header mapping, required flag |
| Bean Validation | DTO có `quantity=0` vi phạm `@Positive` | **Chưa** | `@Valid`, Bean Validation provider, validator |
| Method được gọi, app guard reject | `if (order.invalid()) throw ...` | **Đã bắt đầu** | Business rule, application exception |
| Method được gọi, DB timeout | Transaction/resource failure | **Đã bắt đầu** | DB metrics, transaction, retry |
| Return-value/reply conversion | Method trả DTO nhưng converter không serialize được reply | **Đã chạy method** | Return converter, `@SendTo`/`JMSReplyTo` |

**Phải tách rõ inbound và outbound.** Bài này tập trung lỗi **inbound trước invocation**. Lỗi khi conversion response chỉ xảy ra **sau** body method, nên không được chẩn đoán bằng cùng dấu hiệu “business chưa chạy”.

## 4. Tầng JMS wire conversion: dữ liệu từ broker chưa thành DTO

Đối tượng từ provider là `jakarta.jms.Message` và các subtype như `TextMessage`, `BytesMessage`, `MapMessage`.

Spring JMS converter có package:

```text
org.springframework.jms.support.converter.MessageConverter
```

Hai phương thức quan trọng:

```java
jakarta.jms.Message toMessage(Object object, jakarta.jms.Session session)
        throws jakarta.jms.JMSException;

Object fromMessage(jakarta.jms.Message message)
        throws jakarta.jms.JMSException;
```

Đây là **chữ ký rút gọn để học khái niệm**: API thật còn khai báo exception chuyển đổi riêng. Ở inbound, `fromMessage` phải giải mã JMS message thành payload Java. Nó có thể thất bại **trước khi** annotated handler được gọi.

### 4.1. SimpleMessageConverter không tự đọc JSON thành record

Converter mặc định của JMS thường là:

```text
org.springframework.jms.support.converter.SimpleMessageConverter
```

Nó biết chuyển đổi các dạng đơn giản: `TextMessage` → `String`, `BytesMessage` → `byte[]`, `MapMessage` → map, và ObjectMessage theo chính sách có hỗ trợ. Nếu broker có:

```json
{"orderId":"ORD-42","quantity":2}
```

dưới dạng **JMS TextMessage**, `SimpleMessageConverter` thường trả về một **String JSON**, không phải `OrderCreated`.

Nếu handler khai báo:

```java
public void onOrder(OrderCreated order)
```

thì cần một bước conversion khác có thể biến String thành DTO, hoặc đặt JSON converter ở **JMS wire layer**. Không mặc định chỉ thấy DTO type trong signature thì mọi framework tự dùng Jackson.

### 4.2. JMS MappingJackson2MessageConverter cần type-id hai chiều

Với **Spring Framework 6.2.x/Jackson 2**, có:

```text
org.springframework.jms.support.converter.MappingJackson2MessageConverter
```

Nó hỗ trợ JSON → Java DTO ở inbound; thường cần:

```java
converter.setTargetType(MessageType.TEXT);
converter.setTypeIdPropertyName("_type");
converter.setTypeIdMappings(Map.of(
        "order-created-v1", OrderCreated.class));
```

`setTypeIdPropertyName("_type")` có vai trò quan trọng **khi nhận**: converter cần biết type-id để chọn Java class. Nếu producer gửi TextMessage có JSON nhưng **quên `_type`**, hoặc id không có trong mapping, conversion có thể lỗi ngay ở adapter.

Sử dụng **logical type ID được allowlist** giúp giảm coupling với Java package/class name. Đừng để sender không tin cậy tự quyết định Java class bất kỳ bằng một raw class name.

### 4.3. JSON parse lỗi và validation lỗi hoàn toàn khác

Ví dụ 1 — JSON sai cú pháp:

```text
{ "orderId": "ORD-42", "quantity":
```

Jackson không thể tạo object. Đây là **conversion error**, Bean Validation chưa có DTO để kiểm tra.

Ví dụ 2 — JSON hợp lệ nhưng sai ràng buộc:

```json
{"orderId":"","quantity":0}
```

Jackson có thể tạo `OrderCreated("", 0)`; sau đó `@Valid` phát hiện `@NotBlank` và `@Positive`. Đây là **validation error**, không phải lỗi cú pháp JSON.

Ví dụ 3 — JSON hợp lệ nhưng sai kiểu:

```json
{"orderId":"ORD-42","quantity":"abc"}
```

Jackson có thể thất bại ở chuyển String thành số; tùy cấu hình coercion, lỗi xảy ra ở conversion. Tránh tự suy mọi trường hợp sai kiểu là `MethodArgumentNotValidException`.

### 4.4. Encoding và message subtype cũng là contract

Nếu producer chuyển sang `BytesMessage`, nhưng receiver cố đọc `TextMessage`, converter có thể không hỗ trợ. Nếu bytes không phải UTF-8 đúng schema hoặc bị nén mà receiver không biết giải nén, conversion cũng thất bại.

Một hợp đồng wire cần quy định:

- Queue/topic và message subtype.
- Content type/schema format.
- Encoding, compression, size limit.
- Type ID, schema version và backward compatibility.
- Những property bắt buộc, null/missing rules.
- Các lớp được phép deserialize.

Một consumer version mới không thể mặc nhiên đọc mọi message cũ nếu wire contract thay đổi không tương thích. Cần producer/consumer compatibility tests trước rollout.

## 5. Tầng Spring Messaging: giải quyết tham số trước handler

Annotated endpoint trong Spring sử dụng Spring Messaging abstraction để gọi Java method:

```text
org.springframework.messaging.Message<?>
org.springframework.messaging.handler.annotation.Payload
org.springframework.messaging.handler.annotation.Header
org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory
```

**Khác biệt package dễ nhầm:**

| Thành phần | Package chính | Vai trò |
| --- | --- | --- |
| JMS `MessageConverter` | `org.springframework.jms.support.converter` | Java payload ↔ `jakarta.jms.Message` |
| Messaging `MessageConverter` | `org.springframework.messaging.converter` | Spring `Message<?>` ↔ kiểu Java target |
| `MessagingMessageConverter` | `org.springframework.jms.support.converter` | Cầu nối JMS ↔ Spring Message/headers |
| `DefaultMessageHandlerMethodFactory` | `org.springframework.messaging.handler.annotation.support` | Tạo invoker/resolvers, converter, validator cho method |
| `@Payload` | `org.springframework.messaging.handler.annotation` | Đánh dấu payload argument |
| `@Header` | `org.springframework.messaging.handler.annotation` | Lấy header argument |
| `@Valid` | `jakarta.validation` | Đề nghị Bean Validation trên argument |

Ở đây có **hai interface cùng simple name `MessageConverter`** nhưng chữ ký khác nhau. Đổi converter ở phía `JmsTemplate` producer không tự động cấu hình converter cho listener, và đổi converter trong `DefaultMessageHandlerMethodFactory` không khiến JMS TextMessage bất hợp lệ biến thành message hợp lệ.

### 5.1. Vấn đề với @Header

Ví dụ:

```java
@JmsListener(destination = "orders.created")
public void handle(
        @Payload String orderId,
        @Header("tenantId") String tenantId,
        @Header("attempt") int attempt) {
    // Chỉ vào method khi Spring resolve được tất cả arguments.
}
```

Nếu thiếu `tenantId` (và header bị xem là bắt buộc), hoặc `attempt` là `"oops"` trong khi handler cần `int`, Spring có thể fail ngay ở argument resolver. Vì vậy kể cả **payload đúng** cũng không bảo đảm body method sẽ chạy.

Muốn header tùy chọn:

```java
@Header(name = "tenantId", required = false) String tenantId
```

Khi thiếu header, xử lý null/default rõ ràng. Không dùng kiểu primitive `int` cho một optional header không có default nếu khả năng absent cần được hỗ trợ; dùng `Integer` hoặc quy ước giá trị mặc định được test.

**Lưu ý:** JMS headers và Spring MessageHeaders không hoàn toàn giống nhau. `JmsHeaderMapper` quyết định mapping. Một custom JMS property có tên/kiểu không được hỗ trợ có thể không xuất hiện dưới đúng key mà handler mong đợi.

### 5.2. @Payload và targetClass

Một handler:

```java
public void handle(@Payload OrderCreated order)
```

cần một object `OrderCreated` ở method invocation. Nếu tầng JMS trả `String`, Spring Messaging argument resolver có thể thử converter theo **targetClass = OrderCreated.class**. Với converter mặc định không có String JSON → DTO, conversion thất bại.

Nếu tầng JMS đã trả `OrderCreated`, argument resolver thường có thể dùng trực tiếp mà không phải parse JSON lần hai. Chọn rõ chiến lược:

1. **JMS converter decode JSON → DTO**, sau đó `@Valid`.
2. **JMS converter decode TextMessage → String**, rồi Spring Messaging JSON converter decode String → DTO, sau đó `@Valid`.

Không trộn cả hai kiểu thành hai lần decode không cần thiết; điều quan trọng là producer/consumer dùng cùng wire/schema contract.

## 6. Tầng Bean Validation: object tạo xong nhưng không hợp lệ

Bean Validation là một bước **riêng** sau khi có object đúng kiểu, nếu được cấu hình và kích hoạt bằng `@Valid` hoặc `@Validated`.

### 6.1. DTO Java 17 với constraints

**File `OrderCreated.java`:**

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record OrderCreated(
        @NotBlank String orderId,
        @Positive int quantity) {
}
```

`@NotBlank` không cho null, chuỗi rỗng hoặc toàn whitespace. `@Positive` yêu cầu số **lớn hơn 0**. Với `quantity=0`, JSON deserialization vẫn có thể thành công; validation mới loại bỏ.

**Đừng nhầm ba lớp “valid”:**

- JSON syntax valid.
- JSON đủ type/schema để tạo Java object.
- Object thỏa business-facing Bean Validation constraints.

Một object có thể vượt qua lớp 1–2 nhưng fail lớp 3.

### 6.2. @Valid trên @JmsListener

**File `ValidatedOrderListener.java`:**

```java
import jakarta.validation.Valid;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class ValidatedOrderListener {

    private final OrderApplicationService applicationService;

    public ValidatedOrderListener(
            OrderApplicationService applicationService) {
        this.applicationService = applicationService;
    }

    @JmsListener(
            id = "orders.created.validated.v1",
            destination = "orders.created",
            containerFactory = "validatedOrderListenerFactory")
    public void receive(@Payload @Valid OrderCreated order) {
        // Dòng này CHỈ chạy nếu conversion + validation thành công.
        applicationService.process(order);
    }
}
```

`OrderApplicationService` là service nghiệp vụ do project cung cấp, phải có bean/implementation thực tế. Ví dụ là class tích hợp **trong Spring project**, không chạy bằng JDK riêng lẻ.

Khi constraint thất bại trước invocation, `applicationService.process` **không được gọi** bởi lần delivery đó. Đây là lợi ích của validation ở method boundary: tránh side effects cho message không hợp lệ, **nếu Validator đã được cấu hình đúng**.

### 6.3. @Valid một mình chưa đủ nếu chưa có provider và Validator

Các annotation `@NotBlank`/`@Positive` được cung cấp bởi **Jakarta Bean Validation API**; để thực thi còn cần một **provider** (ví dụ Hibernate Validator) và một `Validator` được Spring handler method infrastructure sử dụng.

Trong Spring Boot, starter validation có thể cung cấp cấu hình thích hợp. Trong Spring Framework thuần, cần cấu hình `LocalValidatorFactoryBean` và đưa validator vào `DefaultMessageHandlerMethodFactory`. Không giả định chỉ thêm dependency `jakarta.validation-api` là có runtime validation.

### 6.4. MethodArgumentNotValidException có ý nghĩa gì?

`PayloadMethodArgumentResolver` kiểm tra `@Valid`/`@Validated`; khi có binding/constraint errors, nó có thể ném:

```text
org.springframework.messaging.handler.annotation.support
    .MethodArgumentNotValidException
```

Đây **không phải** `org.springframework.web.bind.MethodArgumentNotValidException` của Spring MVC; cùng simple name khác package. Đường annotated JMS có thể bọc exception trong `org.springframework.jms.listener.adapter.ListenerExecutionFailedException` hoặc wrapper khác. Hãy kiểm tra cause chain khi log.

Đừng viết exception handler chỉ bắt **MVC exception class** rồi mong nó luôn hoạt động với JMS.

### 6.5. @Valid không kiểm tra toàn bộ nghiệp vụ

`@Valid` phù hợp các invariant ở input boundary:

- `orderId` không rỗng.
- `quantity` là số dương.
- Email/identifier có định dạng cơ bản.
- Nested bean nếu có cascade `@Valid` đúng.
- Giới hạn field lengths, cấu trúc payload.

Còn nghiệp vụ cần dữ liệu ngoài message (đơn hàng đã thanh toán chưa, tồn kho, chính sách pricing...) thường được kiểm tra **trong service**, sau khi method chạy. Đừng nhét database/network calls bất định vào validator đồng bộ nếu có thể khiến conversion boundary khó quan sát và retry sai nhóm.

## 7. Cấu hình Spring JMS đầy đủ: converter và validator ở đúng nơi

Ví dụ dùng **Spring Framework 6.2.x, Java 17+, Jakarta Messaging 3.x, Jackson 2 và Jakarta Bean Validation implementation**. Có broker/`ConnectionFactory` thật, queue `orders.created` đã được provision hoặc provider hỗ trợ tạo theo chính sách. Nếu dùng Spring 7/Jackson 3, cần kiểm tra các class/converter tương ứng ở phiên bản thực tế, không copy package và constructor bất chấp thay đổi.

### 7.1. Bean Validator

**File `OrderValidationConfig.java`:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class OrderValidationConfig {

    @Bean("orderBeanValidator")
    public LocalValidatorFactoryBean orderBeanValidator() {
        return new LocalValidatorFactoryBean();
    }
}
```

`LocalValidatorFactoryBean` kết nối Bean Validation provider với Spring `Validator`. Cần runtime provider (ví dụ Hibernate Validator). Với Spring Boot auto-configuration, tránh tạo hai bean validator cạnh tranh nếu ứng dụng đã có validator mặc định; chọn một cấu hình nhất quán.

### 7.2. JMS converter, listener factory, handler factory

**File `OrderJmsConfig.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;
import org.springframework.validation.Validator;

import java.util.Map;

@Configuration
@EnableJms
public class OrderJmsConfig implements JmsListenerConfigurer {

    private final Validator validator;

    public OrderJmsConfig(
            @Qualifier("orderBeanValidator") Validator validator) {
        this.validator = validator;
    }

    @Bean("orderJmsJsonConverter")
    public MappingJackson2MessageConverter orderJmsJsonConverter() {
        var converter = new MappingJackson2MessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(
                Map.of("order-created-v1", OrderCreated.class));
        return converter;
    }

    @Bean("validatedOrderListenerFactory")
    public DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory connectionFactory,
            @Qualifier("orderJmsJsonConverter")
            MappingJackson2MessageConverter converter) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(converter);
        factory.setSessionTransacted(true);
        factory.setPubSubDomain(false);
        factory.setConcurrency("1-3");

        // Quan sát lỗi ở ngoài handler; không tự thay đổi broker DLQ.
        factory.setErrorHandler(error -> {
            System.err.println(
                    "JMS listener pipeline failed: "
                    + error.getClass().getName());
        });
        return factory;
    }

    @Bean("orderJmsTemplate")
    public JmsTemplate orderJmsTemplate(
            ConnectionFactory connectionFactory,
            @Qualifier("orderJmsJsonConverter")
            MappingJackson2MessageConverter converter) {

        var template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(converter);
        template.setPubSubDomain(false);
        return template;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        var methodFactory = new DefaultMessageHandlerMethodFactory();
        methodFactory.setValidator(validator);
        registrar.setMessageHandlerMethodFactory(methodFactory);
    }
}
```

**Hai điểm cấu hình cố ý khác nhau:**

1. `factory.setMessageConverter(converter)` dùng **JMS-specific converter** để đọc TextMessage JSON và xác định `OrderCreated` từ property `_type`.
2. `methodFactory.setValidator(validator)` dùng Spring Messaging method argument validation **sau khi** đã có DTO để xét `@Valid`.

`setErrorHandler` nhận callback cấp container và có thể ghi nhận lỗi dù method chưa chạy. Đoạn callback ở đây chỉ in loại top-level exception; trong production cần cause chain, tracking ID và metric, với chính sách che dữ liệu nhạy cảm. Callback này **không tự sửa poison message, không tự republish DLQ, và không phải nơi quyết định transaction commit một cách tùy tiện**.

**Vì sao `setSessionTransacted(true)`?** Muốn lỗi trước invocation (cũng như lỗi trong method) có thể dẫn đến rollback/redelivery theo JMS transaction semantics, thay vì message có thể bị ACK không đáng tin ở `AUTO_ACKNOWLEDGE`. Tuy nhiên retry/DLQ cụ thể do container, broker và policy cấu hình; không thể bảo đảm chính xác số lần retry chỉ bằng annotation này.

### 7.3. Service nghiệp vụ và handler

**File `OrderApplicationService.java`:**

```java
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    public void process(OrderCreated event) {
        // Ví dụ tối giản: trong hệ thống thật là DB/outbox/idempotency.
        System.out.println("BUSINESS INVOKED: " + event.orderId());
    }
}
```

Sử dụng `ValidatedOrderListener` ở phần 6.2 cùng các config trên. Khi input được chuyển đổi và validate, service mới được gọi. Với malformed/invalid input, không được thấy `"BUSINESS INVOKED"` chỉ do message đó.

Mã Spring trên chỉ có ý nghĩa khi được đặt vào **cùng một ứng dụng** có component scanning, Spring container, JMS provider, broker queue, Jackson, Bean Validation provider và dependencies phù hợp. Không thể đưa các file vào một thư mục rồi chạy `javac *.java` chỉ với JDK.

### 7.4. Dependency cần thiết

Trong project Maven/Gradle, cần tương đương:

- `org.springframework:spring-jms`.
- `org.springframework:spring-messaging` theo Spring dependency management.
- Jakarta JMS API và implementation JMS provider/broker.
- Jackson phù hợp Spring version (Spring 6.x ví dụ đang dùng Jackson 2).
- `jakarta.validation:jakarta.validation-api`.
- Runtime Bean Validation provider (ví dụ Hibernate Validator).
- Spring Context và transaction infrastructure nếu ứng dụng cần.
- Test stack JUnit 5 và test broker/provider phù hợp.

Nếu dùng Spring Boot thì starter/version quản lý dependencies theo BOM; không ghép tùy ý Spring 6 class với Spring 7/Jackson 3 và cho rằng mọi API giống nhau.

## 8. Tạo ba message test: thành công, sai JSON, sai constraint

Giả sử đã có bean `orderJmsTemplate` dùng converter JSON ở trên. Producer gửi một DTO **hợp lệ**, một TextMessage **sai cú pháp**, và một DTO **vi phạm constraints**.

**File `OrderTestPublisher.java`:**

```java
import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderTestPublisher {

    private final JmsTemplate template;

    public OrderTestPublisher(
            @Qualifier("orderJmsTemplate") JmsTemplate template) {
        this.template = template;
    }

    public void sendValid() {
        template.convertAndSend(
                "orders.created",
                new OrderCreated("ORD-42", 2));
    }

    public void sendMalformedJson() {
        template.send("orders.created", session -> {
            TextMessage message = session.createTextMessage(
                    "{\"orderId\":\"ORD-43\",\"quantity\":");
            message.setStringProperty("_type", "order-created-v1");
            message.setStringProperty("testCase", "malformed");
            return message;
        });
    }

    public void sendInvalidConstraint() {
        template.convertAndSend(
                "orders.created",
                new OrderCreated("", 0));
    }
}
```

Ở đây:

- `sendValid()`: Jackson serialization → `TextMessage`; property `_type` được converter thiết lập theo mapping → DTO inbound hợp lệ → validation pass → method được gọi.
- `sendMalformedJson()`: dùng `send(..., MessageCreator)` để **bỏ qua converter của phía gửi**, tạo JSON hỏng nhưng có `_type`, buộc phía nhận thử parse và fail.
- `sendInvalidConstraint()`: JSON có thể được tạo/parse bình thường thành `OrderCreated("",0)`; lỗi chỉ nổ ở **method argument validation**.

**Không gọi ba method test này vào production.** Với `sessionTransacted=true`, hai message lỗi có thể gây redelivery nhiều lần và tăng retry/DLQ theo broker config. Test phải cách ly queue, giới hạn retry và kiểm tra cleanup.

### 8.1. Dự đoán kết quả, không bịa stdout runtime

Nếu queue, converter và validator đều cấu hình đúng:

| Lần gửi | JMS conversion | Bean Validation | Business body |
| --- | --- | --- | --- |
| `sendValid` | PASS | PASS | **Được invoke** |
| `sendMalformedJson` | FAIL | Không có DTO để validate | **Không invoke** |
| `sendInvalidConstraint` | PASS | FAIL | **Không invoke** |

Không thể khẳng định log, số lần redelivery hay thứ tự chính xác chỉ từ code. Provider, concurrency, transaction, listener timing và broker retry/DLQ policy quyết định runtime.

### 8.2. Nếu business vẫn được gọi với quantity=0?

Các khả năng cần kiểm tra:

1. `@Valid` import sai (ví dụ dùng Jakarta 3 nhưng lẫn `javax.validation` phiên bản cũ).
2. Không có runtime Bean Validation provider.
3. `DefaultMessageHandlerMethodFactory` không có validator hoặc bean factory không được registrar dùng.
4. Annotation method không trỏ tới `validatedOrderListenerFactory` như tưởng.
5. Handler đang thực sự nhận một route/binding khác, hoặc có thêm listener không validate.
6. Constraint áp vào object khác với object thực được deserialize.
7. Test đang đo output của một message khác hoặc một consumer khác cùng queue.

Không kết luận `@Valid` không hỗ trợ JMS chỉ vì một bản config chưa đúng.

## 9. Lỗi xảy ra trước method: không bắt bằng try/catch trong method được

Chống mẫu:

```java
@JmsListener(
        destination = "orders.created",
        containerFactory = "validatedOrderListenerFactory")
public void receive(@Payload @Valid OrderCreated event) {
    try {
        applicationService.process(event);
    } catch (Exception ex) {
        // Không bắt được lỗi deserialize/validate trước invocation!
    }
}
```

Nếu `@Valid` fail, Java execution **chưa vào dấu `{` của method**, do vậy `catch` không chạy. Tương tự, lỗi `@Header` bắt buộc hoặc conversion argument phát sinh trước invocation cũng không thể được method này catch.

**Đường phù hợp để quan sát** là container/adapter error-handling, logging/observability của converter, listener container và broker redelivery metrics. Khi cần phân loại và quarantine poison message, lựa chọn hệ thống/broker policy và code ở tầng có quyền đọc được **raw JMS message** trước conversion.

### 9.1. Lỗi thường bị bọc: tìm root cause

Một log có thể có cấu trúc khái niệm:

```text
ListenerExecutionFailedException
  caused by MethodArgumentNotValidException
    field error: quantity must be greater than 0
```

Hoặc:

```text
MessageConversionException
  caused by JsonProcessingException
    malformed JSON at ...
```

Đây là **mẫu hình log**, không phải stack trace cố định cho mọi Spring version. Wrapper có thể khác theo adapter, converter, provider và lỗi gốc. Đừng viết alert chỉ match một message string không có hợp đồng.

### 9.2. Không catch rồi coi message thành công nếu chưa xử lý

Nếu một raw listener bắt tất cả exception và return bình thường:

```java
try {
    decodeAndProcess(raw);
} catch (Exception ex) {
    logError(ex);
    // Nếu return normally: container có thể commit/ACK.
}
```

Với transacted session, nếu exception bị **nuốt** và method kết thúc bình thường, container có thể **commit** lần nhận đó. Message lỗi có thể biến mất khỏi queue dù chưa được lưu ở quarantine.

Chỉ xác nhận thành công khi thực sự đạt một **terminal outcome** đã định nghĩa (business commit hoặc quarantine bền vững và được quản trị). Nếu chưa đảm bảo, để lỗi được propagate để policy retry/rollback hoạt động, hoặc chuyển vào xử lý lỗi có giao dịch/phục hồi được.

## 10. Ack, transaction, retry và DLQ: hệ quả của pre-handler failure

Bước conversion/validation có thể fail **trước business method**, nhưng phản ứng của JMS vẫn phụ thuộc vào listener container và acknowledgment/transaction mode.

### 10.1. Với DefaultMessageListenerContainer có sessionTransacted=true

Thông thường:

```text
Broker deliver M
   |
   v
Spring container receives M inside JMS transaction
   |
   v
conversion or @Valid fails
   |
   v
Exception propagates out of listener adapter
   |
   v
JMS transaction rollback
   |
   v
Broker may redeliver M according to redelivery policy
   |
   +-- after retry limit, possibly DLQ/quarantine (provider-specific)
```

Thao tác rollback **không sửa JSON hoặc constraint**. Nếu input bất biến và lỗi deterministic, mỗi lần retry có thể fail cùng một chỗ. Một message hỏng có thể trở thành **poison message** chiếm thời gian, làm metrics noise và chặn backlog.

Một số broker hỗ trợ retry delays, max delivery attempts và dead-letter addresses; **JMS API không quy định tên DLQ hoặc số lần thử mặc định cho mọi provider**. Cần cấu hình trực tiếp theo broker mục tiêu.

### 10.2. Với AUTO_ACKNOWLEDGE

Theo tài liệu Spring JMS cho `DefaultMessageListenerContainer`, `AUTO_ACKNOWLEDGE` **không cung cấp bảo đảm reliability tương đương transacted receive**; container có thể acknowledge trước listener execution và exception không dẫn đến redelivery như mong muốn.

Vì thế không viết:

> “Bất cứ conversion error nào trong @JmsListener đều được broker retry rồi tự chuyển DLQ.”

Đó là sai nếu không kiểm tra cấu hình. Một lỗi xảy ra trước method vẫn có thể dẫn đến **message bị xem là đã xử lý** theo ack mode và container semantics.

### 10.3. CLIENT_ACKNOWLEDGE và session modes khác

`CLIENT_ACKNOWLEDGE` có semantics riêng; Spring container có thể acknowledge sau thành công và recover khi thất bại, nhưng tùy container/provider và configuration. Nó không tự giải quyết transaction với DB, và có khác biệt về thời điểm acknowledgment.

Với workload cần reliability, Spring reference khuyến nghị cân nhắc **local JMS transacted sessions** thay vì auto-ack mặc định. Khi có DB write cùng JMS, phải thiết kế idempotency/outbox/transaction isolation; local JMS transaction không tự biến DB thành cùng atomic commit.

### 10.4. ErrorHandler không phải broker retry controller

`DefaultJmsListenerContainerFactory.setErrorHandler(...)` (qua listener container) có thể nhận exception uncaught trong processing để log/metrics, ngay khi method body chưa bắt đầu. Nhưng:

- Không dùng `ErrorHandler` để giả định rằng `return` bình thường trong callback có nghĩa ACK/commit.
- Không mặc định callback có quyền thay đổi broker redelivery policy.
- Không ném lỗi tùy tiện từ error handler khiến container mất khả năng observability.
- Không dùng nó làm nơi thực hiện DB side effects không idempotent cho mỗi retry.
- Thay đổi ack behavior bằng **cấu hình transaction/ack thật** và test trên provider.

Callback xử lý lỗi nên quan sát và phân loại, còn **quarantine/ack** cần một chiến lược có giới hạn rõ (broker DLQ policy, raw listener gateway, hoặc consumer adapter được thiết kế để xử lý kết quả terminal).

### 10.5. Phân biệt lỗi cố định và lỗi tạm thời

| Loại lỗi | Retry giúp gì? | Hướng xử lý |
| --- | --- | --- |
| JSON malformed | Gần như không sửa được bản message cũ | Quarantine/DLQ, fix producer/schema |
| Thiếu type-id bắt buộc | Không tự xuất hiện sau retry | Điều chỉnh producer/mapping; replay có kiểm soát |
| Unknown schema version | Có thể sau khi deploy consumer mới, nhưng không chắc | Route tới compatible consumer/quarantine, versioning |
| DTO vi phạm `@NotBlank` | Không đổi sau retry | Terminal invalid, reject/quarantine theo policy |
| Header bắt buộc thiếu | Không tự xuất hiện | Fix contract, quarantine |
| JSON converter bug | Có thể cần deploy fix; retry vô hạn vẫn nguy hiểm | Fix/rollout, pause/redrive theo kế hoạch |
| Broker connection tạm ngắt | Retry/reconnect thường có ích | Bounded retry, backoff, metrics |
| Database timeout sau method start | Retry có thể có ích, nhưng side effects có thể đã xảy ra | Idempotency, transaction và controlled retries |
| Bean Validation phụ thuộc remote service chập chờn | Không nên đưa vào validator theo mặc định | Chuyển phần remote check vào business flow |

**Nguyên tắc:** lỗi deterministic về format/schema thường không thích hợp với retry vô hạn. Nhưng **đừng tự ACK bỏ message** chỉ vì đã nhận ra lỗi; phải có đường quarantine, audit hoặc reject nghiệp vụ có chủ đích.

## 11. Giới hạn của DLQ và chiến lược quarantine

### 11.1. DLQ không phải mặc định của @Valid

Spring không tạo một Queue tên `orders.created.DLQ` chỉ vì method có `@Valid`. JMS specification cũng không chuẩn hóa mọi broker đều dùng tên `DLQ`/`ActiveMQ.DLQ`. Một broker có thể hỗ trợ dead-letter address/queue sau redelivery limit, một broker khác có policy khác.

Nếu nhu cầu là “không làm mất message invalid”:

1. Cấu hình destination có retention và redelivery policy rõ.
2. Đặt max attempts/backoff phù hợp.
3. Định nghĩa dead-letter/quarantine destination theo provider.
4. Khi message đi quarantine, lưu metadata: original destination, message ID, correlation ID, type/schema version, rejection stage, timestamp, reason code.
5. Giữ payload thô nếu cần điều tra, **mã hóa/giới hạn truy cập và TTL** theo dữ liệu nhạy cảm.
6. Có quy trình triage, sửa producer/schema, kiểm tra tương thích và **manual redrive có idempotency**.
7. Test một message malformed thực sự đi vào đúng nơi sau số lần retry cấu hình.

### 11.2. Nếu không được phép dùng broker DLQ

Một ứng dụng có thể xây **ingress validation gateway** dùng raw JMS listener để giải mã và kiểm tra:

```text
incoming queue
   |
   v
Raw listener / validation gateway
   |
   +-- valid -> business queue/event flow
   |
   +-- invalid -> quarantine queue + reason
```

Nhưng phải giải quyết **atomicity** giữa nhận bản gốc và xuất bản quarantine/valid message. Với cùng JMS provider/session có thể dùng local JMS transaction khi phù hợp; nếu đẩy kết quả sang database/khác broker thì cần outbox/XA hoặc thiết kế bù trừ. Không return bình thường rồi mất message khi việc ghi quarantine thất bại.

Ở gateway kiểu này, conversion xảy ra **trong code được thiết kế để kiểm soát raw message**, không còn là `@Payload @Valid` trên cùng method khiến lỗi không bắt được. Đổi kiến trúc có đánh đổi: boilerplate, duplicate handling, throughput và security.

### 11.3. Idempotency khi redrive

Không dùng `JMSMessageID` làm business idempotency key duy nhất trong mọi hoàn cảnh: khi republish/redrive, provider có thể cấp message ID mới. Giữ một `eventId`/`orderId` độc lập trong body/JMS property để bảo vệ side effects. Redrive phải có dấu vết vì sao nó được thực hiện, bao nhiêu lần và kết quả.

## 12. Quan sát đúng nơi khi handler không được gọi

### 12.1. Những metric cần tách riêng

| Metric | Ý nghĩa | Tránh ngộ nhận |
| --- | --- | --- |
| `jms_receive_attempts` | Broker đã giao hoặc container nhận attempt | Không đồng nghĩa method được invoke |
| `jms_conversion_failures` | Lỗi body/serialization/type-id | Không phải lỗi business DB |
| `jms_argument_failures` | Lỗi binding `@Payload`/`@Header` | Không phải JSON syntax mọi trường hợp |
| `jms_validation_failures` | DTO vi phạm constraints trước invocation | Không đồng nghĩa database validation |
| `jms_handler_invocations` | Số lần body method được gọi | Có thể cao hơn unique business IDs khi redelivery |
| `jms_handler_success` | Business method hoàn tất | Chưa chắc DB/JMS cùng commit |
| `jms_redeliveries` | Retry từ broker/session | Không tự phân biệt permanent/transient |
| `jms_dlq_messages` | Message vào dead-letter destination | Broker-specific policy |
| `queue_oldest_age` | Tuổi message chưa xử lý | Có thể tăng khi poison/retry hoặc thiếu capacity |

Tên metric ở bảng là **gợi ý thiết kế**, không hứa Spring/JMS tự phát sẵn tất cả metric đó. Với Spring 6.1+ có cơ chế observation tùy cấu hình, nhưng cần xem version và observation registry thực tế.

### 12.2. Log nguyên nhân gốc, không log toàn body

Một record chẩn đoán hữu ích:

```text
endpointId=orders.created.validated.v1
destination=orders.created
messageId=ID:...                 (giá trị provider)
correlationId=req-42
eventId=evt-42
typeId=order-created-v1
schemaVersion=1
stage=VALIDATION
cause=MethodArgumentNotValidException
fields=[quantity]
attempt=3
outcome=ROLLED_BACK
```

Đây là **cấu trúc minh họa**, không phải log tự sinh cố định. Khi trường business ID không thể decode từ malformed JSON, dùng những header/JMS properties đã được broker đọc được, không đoán eventId.

Tránh ghi raw token, PII, payment/card data vào log. Nếu cần trích xuất payload để debug, dùng kênh quarantine được bảo vệ, có retention/audit.

### 12.3. Tìm chính xác ngăn xếp lỗi

Một checklist khi thấy `ListenerExecutionFailedException`:

1. Xem **root cause**: JMS `MessageConversionException`, JSON parse, `MethodArgumentNotValidException`, header binding hay lỗi app?
2. Xem stack nằm ở `MessagingMessageListenerAdapter.toMessagingMessage`, `PayloadMethodArgumentResolver` hay method service?
3. Xác định message type và property `_type` được gửi.
4. Xem bean `DefaultJmsListenerContainerFactory` mà annotation `containerFactory` tham chiếu có đúng converter?
5. Xem `JmsListenerConfigurer` đã đăng ký method factory có `Validator` chưa?
6. Xem transaction/ack mode và broker retry/DLQ policy.
7. Đọc broker redelivery count và message age trước khi quyết định replay.
8. Phân biệt **error lặp lại cùng raw message** với nhiều message khác nhau cùng schema issue.

### 12.4. Vì sao @JmsListener body log là tín hiệu không đủ?

`System.out.println("start")` nằm trong body sẽ không chạy với pre-invocation failure. Để phân tích những failure này cần **điểm quan sát trước body**, như container `ErrorHandler`, adapter instrumentation, broker metrics và tracing. Log trong method chỉ xác nhận đã qua tất cả bước trước đó.

## 13. Java 17 chạy độc lập: chứng minh lỗi ở hai cửa trước business

Đoạn sau là chương trình Java 17 thuần JDK. Nó **mô phỏng** ba bước decode → validate → business method và tách hai loại failure. Không yêu cầu Spring/JMS libraries hoặc broker. Dùng nó để quan sát tại sao không thể bắt lỗi tại một method chưa được invoke.

Tạo file **`PreHandlerFailureDemo.java`**:

```java
import java.util.List;

public final class PreHandlerFailureDemo {

    record Order(String id, int quantity) {}

    static final class DecodeFailure extends RuntimeException {
        DecodeFailure(String message) {
            super(message);
        }
    }

    private static int businessCalls = 0;

    static Order decode(String raw) {
        String[] fields = raw.split(",", -1);

        if (fields.length != 2) {
            throw new DecodeFailure("expected two fields");
        }

        try {
            return new Order(fields[0], Integer.parseInt(fields[1]));
        } catch (NumberFormatException ex) {
            throw new DecodeFailure("quantity is not an integer");
        }
    }

    static void validate(Order order) {
        if (order.id().isBlank() || order.quantity() <= 0) {
            throw new IllegalArgumentException("invalid order fields");
        }
    }

    static void business(Order order) {
        businessCalls++;
        System.out.println("BUSINESS: " + order.id());
    }

    static void deliver(String raw) {
        try {
            Order order = decode(raw);
            validate(order);
            business(order);
        } catch (DecodeFailure ex) {
            System.out.println("CONVERSION: " + ex.getMessage());
        } catch (IllegalArgumentException ex) {
            System.out.println("VALIDATION: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        for (String wire : List.of(
                "ORD-1,2",
                "not-a-record",
                "ORD-2,0",
                "ORD-3,1")) {
            deliver(wire);
        }

        System.out.println("Business calls: " + businessCalls);
    }
}
```

Biên dịch và chạy:

```bash
javac PreHandlerFailureDemo.java
java PreHandlerFailureDemo
```

**Stdout chính xác:**

```text
BUSINESS: ORD-1
CONVERSION: expected two fields
VALIDATION: invalid order fields
BUSINESS: ORD-3
Business calls: 2
```

Giải thích:

- `ORD-1,2` có hai field, quantity hợp lệ → decode/validate pass → business chạy.
- `not-a-record` thiếu dấu phẩy → `DecodeFailure` trước khi có `Order`.
- `ORD-2,0` decode được `Order` nhưng quantity không dương → validation fail, business không chạy.
- `ORD-3,1` hợp lệ → business chạy.
- Có bốn lần “delivery” mô phỏng nhưng chỉ **hai** lần business invocation.

**Giới hạn:** Demo không implement `@JmsListener`, không dùng Jackson/Jakarta Validation, không có JMS session, transaction, redelivery, DLQ hay Spring exception wrapper. Nó minh họa thứ tự **logical pipeline**; runtime thực phải được kiểm thử trên JMS provider.

## 14. Kiểm thử thực tế với broker: khẳng định “method chưa chạy”

### 14.1. Test conversion fail

1. Provision queue test `orders.created` và cấu hình consumer JMS Jackson converter với `_type` mapping.
2. Gửi raw `TextMessage` chứa JSON malformed, vẫn đặt `_type=order-created-v1`.
3. Chờ delivery attempt được broker ghi nhận.
4. Assert business service mock chưa có call cho event đó.
5. Xác minh log/root cause thuộc conversion/JSON, không phải Bean Validation.
6. Quan sát rollback và redelivery nếu listener session transacted.
7. Giới hạn attempts, xác minh message đi quarantine/DLQ nếu broker được cấu hình.

**Đừng dùng FIFO queue chung không cách ly với hệ thống test khác** vì một poison message có thể làm integration test treo/đọc nhầm message.

### 14.2. Test Bean Validation fail

1. Gửi DTO `new OrderCreated("",0)` qua converter Spring JSON.
2. Đảm bảo message được serialize thành TextMessage JSON hợp lệ với `_type`.
3. Consumer parse thành DTO thành công.
4. Argument resolver dùng Validator, phát hiện `@NotBlank`/`@Positive`.
5. Assert service method chưa có call.
6. Kiểm tra root cause `MethodArgumentNotValidException` hoặc wrapper thích hợp.
7. Kiểm tra rollback/retry/DLQ theo policy.

Nếu test không fail nhưng lại gọi service, kiểm tra provider validation và cấu hình `JmsListenerConfigurer` trước khi sửa code business.

### 14.3. Test missing header vs wrong header type

Dùng listener test:

```java
@JmsListener(destination = "header.test")
public void handle(
        @Payload String body,
        @Header("tenantId") String tenantId,
        @Header("attempt") int attempt) {
    // Code chạy sau khi cả hai headers được bind.
}
```

Gửi message thiếu `tenantId` và message có `attempt="n/a"`; xác minh exception thuộc **argument resolution** chứ không phải JSON converter. Tách các message và destination để kết quả test không lẫn nhau.

### 14.4. Test với sessionTransacted=false

Trong môi trường test riêng:

1. Gửi malformed message vào queue.
2. Dùng `DefaultMessageListenerContainer` với `AUTO_ACKNOWLEDGE`.
3. Kiểm tra có thể không có redelivery như mong muốn theo Spring semantics.
4. So với listener `sessionTransacted=true`.
5. Ghi lại behavior thực tế trên provider phiên bản đang dùng, tránh suy rộng từ một broker.

**Không dùng test này trên dữ liệu nghiệp vụ thật**, vì sai ack mode có thể khiến message bị mất.

### 14.5. Test poison-message policy hữu hạn

1. Cấu hình broker test max delivery attempts và dead-letter target.
2. Gửi message invalid cố định.
3. Kiểm tra cùng event ID được attempted theo giới hạn định trước.
4. Kiểm tra message cuối cùng ở DLQ và main queue không bị loop vô hạn.
5. Kiểm tra metric conversion/validation failure đúng loại, không đếm nhầm như business exception.
6. Khi redrive sau sửa producer/schema, đảm bảo idempotency.

### 14.6. Test compatibility khi deploy hai versions

1. Producer V1 phát schema version 1.
2. Consumer V2 chạy converter có type-id mapping version 1.
3. Chứng minh V2 vẫn parse/validate đúng dữ liệu cũ.
4. Đưa một payload V2 có field mới; xác minh consumer V1 reject/quarantine có chủ đích hoặc chấp nhận backward-compatible.
5. Test missing/unknown type-id mà không cho phép arbitrary Java class loading.
6. Không dùng “đọc được ở local” thay cho integration test với cùng provider settings.

## 15. Runbook xử lý production: không thấy log đầu @JmsListener

Khi alert “message tồn hoặc DLQ tăng, nhưng method handler không thấy log”:

### Bước 1 — Khoanh vùng chính xác endpoint

- `@JmsListener.id`, `destination`, `containerFactory` và selector.
- Queue vs Topic; subscription identity nếu durable.
- Broker namespace/vhost, ACL, consumer count và connection status.
- Có listener container khác cùng queue đang cạnh tranh nhận không?

Nếu selector không khớp, message có thể **chưa từng đến adapter**. Đây là nguyên nhân **trước receive**, khác lỗi conversion. Không nhầm với nội dung bài này.

### Bước 2 — Xác minh có delivery attempt

- JMS provider metrics: delivered/in-flight/redelivered count.
- Spring container adapter errors.
- Khi có thể, trace message ID/correlation ID.
- Kiểm tra `JMSRedelivered`/`JMSXDeliveryCount` theo provider support.

Nếu broker không có consumer match, không thể kết luận conversion fail chỉ vì không thấy business log.

### Bước 3 — Lấy root cause, không chỉ exception wrapper

Phân nhóm:

- `JMSException` kết nối/transport.
- `org.springframework.jms.support.converter.MessageConversionException` hoặc JSON cause: wire conversion.
- `org.springframework.messaging.converter.MessageConversionException`: Spring Messaging conversion.
- `MethodArgumentNotValidException`: Bean Validation/method argument.
- Missing `@Header`/wrong type: argument resolution.
- Exception stack từ `OrderApplicationService.process`: business method đã chạy.

### Bước 4 — Kiểm tra contract của một message mẫu

Dùng broker management/browse không tiêu thụ khi có thể, lấy:

- JMS Message subclass và body format.
- `_type`/`schemaVersion`/`contentType`.
- Header/property names và types.
- Giá trị vi phạm constraints (nếu có quyền/đã che nhạy cảm).
- Event ID và tính hợp lệ của business key.

Tránh tạo consumer không selector trên queue production chỉ để “đọc thử”, vì nó có thể ACK message của worker khác.

### Bước 5 — Xem transaction/retry/DLQ

- Container đang `sessionTransacted=true` hay auto-ack?
- Broker có retry hữu hạn hoặc redelivery delay?
- Có message lặp mãi mà không thể sửa trong body?
- DLQ có thực sự được provision/permission đúng không?
- Có scenario converter fail trên message cũ trong lúc rolling deploy?

### Bước 6 — Khắc phục đúng nơi

- Malformed JSON: sửa producer/serialization, quarantine/replay theo version.
- Wrong type-id: sửa mapping/metadata và compatibility.
- Method-arg type mismatch: cấu hình Spring Messaging converter hoặc đổi method contract.
- Missing header: xác định required/optional và đồng bộ producer.
- Validation fail: sửa dữ liệu/constraints nếu đúng nghiệp vụ, không tắt `@Valid` chỉ để im log.
- Broker tạm lỗi: backoff/recovery và quan sát lại.
- DLQ không hoạt động: cấu hình provider, không chờ Spring tự sinh DLQ.
- Poisons chiếm queue: có kế hoạch tạm ngừng/di dời message có kiểm soát và audit, không purge bừa bãi.

### Bước 7 — Xác nhận sau sửa

- Converter/validator errors giảm.
- Business invocation tăng cho message hợp lệ.
- Main queue backlog giảm và DLQ không tiếp tục bùng.
- Unique business IDs không bị xử lý trùng.
- Replayed events được ghi dấu cùng source version/reason.
- Không phát sinh PII leak trong error logs/quarantine.

## 16. Những sai lầm phổ biến

**Sai lầm 1 — “Có log broker delivered nghĩa là handler method đã chạy.”**  
Không. Delivery đến container rồi mới conversion/validation; body có thể chưa được invoke.

**Sai lầm 2 — “Thêm try/catch trong @JmsListener bắt mọi lỗi deserialize.”**  
Không. Lỗi có thể phát sinh trước invocation nên catch trong body không chạy.

**Sai lầm 3 — “Một DTO Java có @NotBlank là mặc nhiên được validate.”**  
Không. Cần `@Valid`/`@Validated` trên argument, validator/runtime provider và method infrastructure cấu hình đúng.

**Sai lầm 4 — “JSON sai cú pháp là lỗi Bean Validation.”**  
Không. Parse/deserialize fail trước khi Bean Validation có DTO để xét.

**Sai lầm 5 — “DTO tạo được thì chắc chắn handler chạy.”**  
Không. Method-argument validation có thể chặn, hoặc thiếu header bắt buộc.

**Sai lầm 6 — “Spring JMS và Spring Messaging MessageConverter cùng interface.”**  
Sai. Chúng khác package, chữ ký và mục đích. Phải đặt converter đúng tầng.

**Sai lầm 7 — “Set JSON converter cho sender là đủ để listener nhận DTO.”**  
Không. Consumer listener factory cũng phải có converter/handler conversion tương thích.

**Sai lầm 8 — “@Valid cùng import javax.validation.Valid từ code cũ vẫn luôn tương thích.”**  
Không. Spring Framework 6+/Jakarta dùng `jakarta.validation`; tránh trộn version không tương thích.

**Sai lầm 9 — “@Header thiếu luôn được truyền null.”**  
Không. `@Header` có required semantics; argument resolver có thể fail trước method.

**Sai lầm 10 — “Lỗi converter sẽ tự đi DLQ.”**  
Không. DLQ là policy broker/consumer retry; Spring `@Valid` không tự tạo nó.

**Sai lầm 11 — “AUTO_ACKNOWLEDGE bảo đảm redelivery khi handler fail.”**  
Không theo Spring `DefaultMessageListenerContainer`; cần cấu hình transacted/reliable mode và test.

**Sai lầm 12 — “Cứ retry JSON malformed đến khi nó hết lỗi.”**  
Không. Dữ liệu bất biến thường fail deterministic; áp retry hữu hạn/quarantine thay vì poison loop.

**Sai lầm 13 — “Chỉ cần ErrorHandler ghi log là message được quarantine.”**  
Không. ErrorHandler logging không tự publish DLQ hoặc xác nhận kết quả terminal.

**Sai lầm 14 — “Catch exception rồi return normally sẽ luôn an toàn.”**  
Không. Container có thể commit/ACK message đã chưa được xử lý hoặc chưa lưu ở quarantine.

**Sai lầm 15 — “Exception ở method receiver chắc chắn là lỗi business.”**  
Không. Wrapper có thể đến từ argument binding/validation trước invocation; kiểm tra root cause và stack.

**Sai lầm 16 — “Đổi JMSMessageID giúp deduplicate redrive.”**  
Không. Redrive thường tạo message ID mới; phải dùng business/event ID ổn định.

**Sai lầm 17 — “Lỗi validation chỉ xảy ra ở HTTP controller.”**  
Không. Spring Messaging `PayloadMethodArgumentResolver` hỗ trợ `@Valid` cho annotated message listeners, gồm JMS.

**Sai lầm 18 — “Message body hợp lệ về JSON là đủ để bảo mật.”**  
Không. Cần allowlist type-id, schema constraints, ACL và giới hạn size; tránh Java deserialization không tin cậy.

## 17. Checklist code review và vận hành

- [ ] Handler đang nhận raw `jakarta.jms.Message`, `String`, Spring `Message<?>` hay typed DTO?
- [ ] Đã xác định tất cả bước **trước method invocation** chưa?
- [ ] JMS wire converter có đúng package và được gắn cho **listener factory**, không chỉ producer?
- [ ] JMS TextMessage/BytesMessage subtype, encoding, schema và content type có thống nhất?
- [ ] Nếu JSON converter cần type-id, producer có đặt đúng property và receiver có allowlist mappings?
- [ ] Nếu dùng `@Payload OrderCreated`, handler đã có converter đúng target type?
- [ ] Nếu dùng `@Valid`, Jakarta Bean Validation implementation và Spring `Validator` có hoạt động thật?
- [ ] Đã phân biệt `MethodArgumentNotValidException` của Spring Messaging với MVC?
- [ ] Các `@Header` bắt buộc có thực sự được producer gửi/map đúng kiểu?
- [ ] Có log/counter ở container boundary cho pre-handler failures không?
- [ ] ErrorHandler có log cause chain và không làm mất thông tin message ID/type/schema?
- [ ] Có chính sách không ghi nguyên payload nhạy cảm vào logs/quarantine?
- [ ] Listener container dùng acknowledgment/transaction phù hợp reliability?
- [ ] Nếu rollback, broker có giới hạn redelivery và DLQ/quarantine thật không?
- [ ] Lỗi cố định được định tuyến tới xử lý terminal có audit, không retry vô hạn?
- [ ] Catch/return không khiến message chưa xử lý bị ACK vô tình?
- [ ] Có idempotency theo business ID khi retry/redrive?
- [ ] Có test JSON malformed **không gọi business service**?
- [ ] Có test DTO vi phạm `@Positive`/`@NotBlank` **không gọi business service**?
- [ ] Có test missing/invalid `@Header` và đúng exception stage?
- [ ] Đã test broker/container behavior thật cho ack, redelivery, DLQ và graceful shutdown?
- [ ] Đã kiểm thử compatibility giữa producer/consumer versions trong rolling deploy?
- [ ] Đã theo dõi backlog, oldest age, redelivery rate, validation failures và DLQ?
- [ ] Các phiên bản Spring/Jackson/Validation có tương thích với code ví dụ?

## 18. Tự kiểm tra kiến thức

**Câu 1.** Broker đã giao message, nhưng `@JmsListener` không in log đầu method. Có thể vì sao?

**Đáp án:** Conversion/argument resolution/Bean Validation có thể fail **trước invocation**. Cũng cần kiểm tra selector/consumer metrics để biết message có thực sự đến container không.

**Câu 2.** JMS TextMessage chứa JSON malformed. `@Valid` sẽ phát hiện trước hay Jackson converter?

**Đáp án:** Jackson/JMS wire conversion fail trước; chưa có DTO để `@Valid` kiểm tra.

**Câu 3.** DTO `OrderCreated("",0)` đã deserialize thành công. Vì sao method vẫn không chạy?

**Đáp án:** `@Payload @Valid` phát hiện `@NotBlank`/`@Positive` và ném validation exception trong argument resolver trước invocation.

**Câu 4.** `try/catch` nằm trong body `@JmsListener` bắt được `MethodArgumentNotValidException` của chính argument đó không?

**Đáp án:** Không. Exception xảy ra khi chuẩn bị tham số, trước khi vào body Java method.

**Câu 5.** Đặt `MappingJackson2MessageConverter` trên `JmsTemplate` sender, không cấu hình listener. Có chắc receiver có DTO không?

**Đáp án:** Không. Cần listener converter/argument conversion tương thích, phụ thuộc container factory thực được dùng.

**Câu 6.** `spring-jms MessageConverter` khác `spring-messaging MessageConverter` ở đâu?

**Đáp án:** JMS converter làm việc với `jakarta.jms.Message` và `Session`; Messaging converter làm việc với Spring `Message<?>` và target type. Hai interface không thay thế trực tiếp.

**Câu 7.** Vi phạm `@Valid` thường phát sinh exception nào trong Spring Messaging argument resolver?

**Đáp án:** `org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException`; ở adapter có thể thấy wrapper như `ListenerExecutionFailedException`.

**Câu 8.** `@Header("tenantId") String tenantId` có thể làm method chưa được gọi khi nào?

**Đáp án:** Khi header bắt buộc thiếu hoặc không thể resolve/convert; argument binding fail trước invocation.

**Câu 9.** Vì sao việc method chưa chạy không có nghĩa broker chưa tính delivery attempt?

**Đáp án:** Spring nhận JMS Message trước conversion; broker đã delivery tới consumer/session rồi.

**Câu 10.** `sessionTransacted=true` giúp gì khi conversion fail?

**Đáp án:** Có thể rollback lần nhận và broker redeliver theo policy. Nó không tự sửa payload hoặc tự định nghĩa DLQ.

**Câu 11.** Lỗi JSON malformed có nên retry vô hạn không?

**Đáp án:** Không. Đó là lỗi dữ liệu cố định; cần retry hữu hạn và quarantine/DLQ theo policy, sửa producer/schema rồi redrive có kiểm soát.

**Câu 12.** Spring `ErrorHandler` có tự tạo queue DLQ không?

**Đáp án:** Không. Nó hỗ trợ quan sát lỗi container; DLQ cần broker/application policy cụ thể.

**Câu 13.** Dùng `AUTO_ACKNOWLEDGE` có bảo đảm message được retry sau exception trong `DefaultMessageListenerContainer` không?

**Đáp án:** Không. Theo Spring reference, auto-ack không bảo đảm reliable redelivery; ưu tiên transacted sessions khi cần reliability.

**Câu 14.** Vì sao một raw listener catch exception rồi return bình thường có thể nguy hiểm?

**Đáp án:** Container có thể ACK/commit message dù decode/business chưa thành công, gây mất dữ liệu nếu chưa quarantine bền vững.

**Câu 15.** Tại sao cần `_type` với JMS Jackson converter?

**Đáp án:** Để xác định Java class khi deserializing incoming JSON theo cấu hình; logical type-id mappings giúp kiểm soát compatibility và an toàn.

**Câu 16.** Khi redrive message từ DLQ, dùng JMSMessageID làm idempotency key duy nhất đã đủ chưa?

**Đáp án:** Chưa. Provider có thể cấp ID mới; dùng business/event ID ổn định để dedupe.

**Câu 17.** Một message có `quantity="abc"` trong JSON. Đây luôn là validation error?

**Đáp án:** Không. Chuyển kiểu String→number có thể fail trước khi tạo DTO, nên thường là conversion error tùy converter/coercion settings.

**Câu 18.** Muốn biết business method có chạy chưa, nên đo gì?

**Đáp án:** Instrument method invocation/business side effect riêng, cùng với conversion/validation failure ở container và broker delivery/retry metrics.

**Câu 19.** Có `jakarta.validation-api` dependency nhưng không có implementation runtime thì `@Valid` chắc chắn chạy không?

**Đáp án:** Không. Cần Bean Validation provider và Spring Validator được cấu hình/đưa vào method factory.

**Câu 20.** Khi thấy `ListenerExecutionFailedException`, bước chẩn đoán đầu tiên là gì?

**Đáp án:** Tìm cause chain và stack frames để xác định lỗi wire conversion, argument binding, validation trước invocation hay exception thực sự trong method.

## Kết luận

Trong Spring JMS, đường vào một `@JmsListener` **không bắt đầu ở dòng code đầu tiên trong method**. Framework đã phải nhận `jakarta.jms.Message`, chuyển đổi dữ liệu, dựng Spring Message, resolve các tham số và có thể chạy Bean Validation **trước khi gọi Java method**. Bất kỳ lỗi nào ở các bước này đều có thể làm message đã được broker giao nhưng method nghiệp vụ **chưa chạy**.

Muốn xử lý đúng, phải:

- **Phân loại lỗi theo stage**, kiểm tra root cause thay vì chỉ wrapper.
- Đặt **JMS converter** và **Spring method validator** ở hai vị trí cấu hình tương ứng.
- Dùng `@Payload @Valid` với runtime Validator thực sự hoạt động.
- Ghi nhận pre-handler errors ở container/adapter, không chỉ `try/catch` trong body.
- Cấu hình transaction/ack, retry hữu hạn, broker DLQ/quarantine và redrive có audit.
- Không đánh đồng message delivered, handler invoked, business committed và JMS acknowledged.

### Tài liệu tham khảo chính thức

1. [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@JmsListener`, annotated method arguments, `@Payload @Valid`, `DefaultMessageHandlerMethodFactory` và `Validator`.
2. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — message listener containers, transaction, acknowledgment và failure propagation.
3. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — `DefaultMessageListenerContainer`/`SimpleMessageListenerContainer`, AUTO_ACKNOWLEDGE và transacted sessions.
4. [Spring Framework — PayloadMethodArgumentResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html) — conversion theo targetClass, `@Valid`/`@Validated` và `MethodArgumentNotValidException`.
5. [Spring Framework — DefaultMessageHandlerMethodFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html) — cấu hình method argument converter và validator.
6. [Spring Framework — JMS MappingJackson2MessageConverter (6.2)](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html) — `MessageType.TEXT`, `setTypeIdPropertyName` và type-id mappings.
7. [Spring Framework — MessagingMessageListenerAdapter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/adapter/MessagingMessageListenerAdapter.html) — JMS-to-Spring Message adapter và handler invocation.
8. [Spring Framework — AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html) — `setErrorHandler`, converter, acknowledgment và error handling.
9. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — provider delivery/ack/transaction, message headers và redelivery.
10. [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/3.0/) — `@Valid` và constraint semantics.
