# DefaultMessageHandlerMethodFactory và giải quyết tham số trong Spring JMS

> **Chủ đề cha:** Dữ liệu listener — Spring Framework JMS.  
> **Nhiệm vụ:** Hiểu cách một phương thức `@JmsListener` nhận đúng **payload, headers, Spring Messaging Message, raw JMS Message và Session**; vai trò của `DefaultMessageHandlerMethodFactory`, thứ tự chọn `HandlerMethodArgumentResolver`, cơ chế chuyển kiểu, validation và mở rộng custom argument resolver. Bài có ví dụ Java 17+ cho Spring Boot 3.5 với ActiveMQ Artemis.

**Phiên bản:** Spring Framework 6.2.x, Spring Boot 3.5.x, Jakarta Messaging (`jakarta.jms`), Java 17+. Không trộn `javax.jms` của Spring 5/JMS cũ với `jakarta.jms`. Tất cả ví dụ cấu hình custom phải được đánh giá cùng bean `JmsListenerContainerFactory` và cơ chế message conversion thực tế của ứng dụng.

## 1. Vì sao phương thức @JmsListener có thể nhận nhiều kiểu tham số?

Một JMS consumer cấp thấp thường nhận một đối tượng `jakarta.jms.Message`. Trong Spring, ta có thể viết:

~~~java
@JmsListener(destination = "jobs.in")
public void onJob(String jobId) {
    process(jobId);
}
~~~

hoặc:

~~~java
@JmsListener(destination = "jobs.in")
public void onJob(
        @Payload String jobId,
        @Header("tenantId") String tenantId,
        @Header("retryCount") int retryCount) {
    process(jobId, tenantId, retryCount);
}
~~~

Cùng một transport message nhưng Spring biết được tham số nào là body và tham số nào là metadata, vì nó có **hệ thống giải quyết tham số (argument resolution)**. `DefaultMessageHandlerMethodFactory` tạo `InvocableHandlerMethod` với các `HandlerMethodArgumentResolver` phù hợp cho các method-based endpoints. Đây là điểm khác biệt giữa một `@JmsListener` kiểu POJO và callback thô `jakarta.jms.MessageListener`.

**Tách ba trách nhiệm:**

1. **Listener container:** mở connection/session/consumer, nhận message, quản lý concurrency, transaction, recovery và shutdown.
2. **JMS → Spring Messaging adapter/converter:** bọc raw JMS message, trích body và ánh xạ JMS headers/properties sang Spring `Message<?>`.
3. **Handler method factory:** nhận Spring message đã chuyển, áp dụng argument resolvers, type conversion/validation rồi gọi method Java đúng chữ ký.

`DefaultMessageHandlerMethodFactory` nằm ở **bước 3**. Nó không phải JMS provider, không phải broker, không nhận message từ queue, không tạo transaction và không quyết định số listener threads.

## 2. Sơ đồ đường đi của một message

~~~text
Producer
   |
   |  JMS TextMessage body="job-101"
   |  property tenantId="shop-a", retryCount=2
   v
JMS Queue: jobs.in
   |
   v
DefaultMessageListenerContainer
   |  nhận, quản lý Session + ACK/transaction
   v
MessagingMessageListenerAdapter
   |  giữ raw jakarta.jms.Message, jakarta.jms.Session
   |  chuyển body + headers sang Spring Message<?>
   v
InvocableHandlerMethod
   |  được tạo bởi DefaultMessageHandlerMethodFactory
   |
   +-- @Payload String jobId           -> "job-101"
   +-- @Header("tenantId") String      -> "shop-a"
   +-- @Header("retryCount") int       -> 2
   +-- @Headers Map<String,Object>     -> nhiều headers
   +-- jakarta.jms.Message             -> raw message
   +-- jakarta.jms.Session             -> Session đang xử lý
   |
   v
Java handler / validation / business service
   |
   v
Return hoặc exception
   |
   v
JMS commit / rollback theo listener container
~~~

**Hai nhận định quan trọng:**
- Raw JMS `Message` và `Session` có thể được **listener adapter đưa thêm vào invocation** như special/provided arguments. Không phải mọi tham số đều do `PayloadMethodArgumentResolver` tạo ra.
- Việc một tham số chuyển đổi thành công **không đồng nghĩa** business work thành công; JMS acknowledgement/transaction cần được cấu hình độc lập.

## 3. Bảng các kiểu tham số được hỗ trợ

| Chữ ký tham số | Nguồn dữ liệu | Ý nghĩa và lưu ý |
| --- | --- | --- |
| `String payload`, `OrderEvent payload` | Spring message payload | Với tham số thông thường không mang annotation đặc biệt, Spring coi là payload |
| `@Payload String payload` | Spring message payload | Khai báo tường minh; có thể đi kèm `@Valid` hoặc `@Validated` |
| `@Header("tenantId") String tenantId` | Spring headers | Đọc đúng một header/property; hỗ trợ chuyển đổi kiểu khi cấu hình phù hợp |
| `@Header(value="priority", required=false) Integer priority` | Spring headers | Header có thể thiếu; cần kiểu nullable phù hợp |
| `@Headers Map<String,Object> all` | Spring headers | Truy cập nhiều headers cùng lúc |
| `org.springframework.messaging.Message<OrderEvent> msg` | Spring Messaging abstraction | Payload và map headers; khác với raw JMS Message |
| `org.springframework.messaging.MessageHeaders headers` | Spring Messaging headers | Đọc map đã ánh xạ, tránh phụ thuộc raw provider |
| `org.springframework.jms.support.JmsMessageHeaderAccessor accessor` | Accessor của Spring cho JMS headers | Tiện hơn khi cần các JMS metadata chuẩn |
| `jakarta.jms.Message raw`, `TextMessage raw` | Raw transport message | Đọc JMS headers/properties/body trực tiếp theo JMS API |
| `jakarta.jms.Session session` | JMS Session của lần listener invocation | Dùng khi thực sự cần JMS-specific APIs, không tự đóng session |

Các loại trên được mô tả trong tài liệu `@JmsListener` của Spring Framework 6.2. Không nhầm `org.springframework.messaging.Message` với `jakarta.jms.Message`: hai interface khác nhau dù cùng tên ngắn `Message`.

**Phạm vi một payload:** một handler thông thường đại diện cho **một message** và một payload. Việc khai báo hai tham số trần không annotate rồi kỳ vọng Spring tách một JSON body thành hai Java variables **không phải** behavior mặc định. Muốn nhiều field, dùng một DTO hoặc trích field có chủ đích sau conversion.

## 4. @Payload và các quy tắc nhận dạng payload

Một method:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(String jobId) {
    // jobId là payload do Spring xác định.
}
~~~

tương đương về ý định binding với:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(@Payload String jobId) {
    // Khai báo tường minh để người đọc hiểu nguồn tham số.
}
~~~

`@Payload` trong ngữ cảnh này là `org.springframework.messaging.handler.annotation.Payload`, **không phải** annotation của Jakarta JMS.

### 4.1. Nếu body type không tương thích?

Giả sử producer gửi `TextMessage` có nội dung `"job-101"`, converter JMS mặc định thường tạo payload String. Method nhận `String` hợp lý.

Nếu method lại khai báo:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(OrderEvent event) {
    // ...
}
~~~

thì Spring phải có **đường chuyển đổi thực sự** từ dữ liệu nhận thành `OrderEvent`. Chỉ đổi chữ ký từ String sang DTO không tạo ra bộ parser JSON. Nếu dùng `SimpleMessageConverter`, TextMessage JSON thường vẫn là `String`. Để có DTO, cần converter/schema tương ứng (ví dụ Jackson JSON trên JMS layer) hoặc một Spring Messaging `MessageConverter` có logic rõ ràng.

### 4.2. Tham số payload không phải lúc nào cũng mặc định hợp lệ

- Body trống/nullable có thể khiến `PayloadMethodArgumentResolver` báo lỗi khi tham số bắt buộc.
- `@Payload(required=false)` cho phép mô tả optional semantics ở resolver, nhưng behavior còn phụ thuộc converter/target type.
- `Optional<T>` chỉ có ý nghĩa khi resolver và conversion stack thực tế hỗ trợ tình huống đó; đừng mặc định payload thiếu luôn trở thành `Optional.empty()` trong mọi phiên bản.
- Một message có schema sai có thể thất bại **trước khi handler được gọi**.
- Không dùng `@Payload` trên một raw `jakarta.jms.Message` rồi mong nó đại diện transport message nữa; hãy để raw message được hỗ trợ bởi adapter qua tham số raw rõ ràng.

### 4.3. Vì sao Payload resolver đứng cuối?

`PayloadMethodArgumentResolver` là resolver có phạm vi rộng: nó có thể xem nhiều tham số không annotate là payload. Vì vậy Spring đặt nó **sau** các resolver chuyên dụng như `@Header`, `@Headers` và Spring `Message<?>`. Nếu đứng trước, tham số metadata có nguy cơ bị nhận nhầm là body.

## 5. @Header: lấy một header hoặc JMS property

Một JMS producer có thể gửi:

~~~java
jmsTemplate.send("jobs.in", session -> {
    TextMessage text = session.createTextMessage("job-101");
    text.setStringProperty("tenantId", "shop-a");
    text.setIntProperty("retryCount", 2);
    text.setJMSCorrelationID("corr-101");
    return text;
});
~~~

Với method:

~~~java
@JmsListener(destination = "jobs.in")
public void onJob(
        @Payload String job,
        @Header("tenantId") String tenantId,
        @Header("retryCount") int retryCount) {
    // job="job-101", tenantId="shop-a", retryCount=2
}
~~~

`@Header` lấy dữ liệu từ Spring `MessageHeaders` mà JMS adapter đã xây dựng. Các application JMS properties thường được ánh xạ sang Spring headers. Spring có `org.springframework.jms.support.JmsHeaders` định nghĩa tên cho một số standard JMS headers; dùng constants thay vì tự đoán spelling khi đọc correlation ID/message ID/priority.

### 5.1. Header thiếu và required

`@Header` thường coi header là bắt buộc. Nếu thiếu, listener có thể báo lỗi **trước khi vào business method**. Ví dụ cho phép thiếu:

~~~java
public void handle(
        @Payload String body,
        @Header(value = "region", required = false)
        String region) {
    // region có thể null; cần policy nghiệp vụ riêng.
}
~~~

Khi cần giá trị mặc định, có thể khai báo `defaultValue` qua annotation:

~~~java
@Header(name = "region", defaultValue = "GLOBAL")
String region
~~~

Đây là mảnh **tham số method**, không phải file Java độc lập. Header mặc định chỉ là behavior của handler argument binding, **không sửa** JMS message property đã được broker lưu, không thay JMS selector trên consumer.

### 5.2. Header conversion dùng ConversionService

Giả sử producer đặt property String `"2"`:

~~~java
text.setStringProperty("retryCount", "2");
~~~

Header resolver có thể dùng Spring `ConversionService` để chuyển `"2"` sang `int` trong method, nếu conversion service được cấu hình cho phép. Đây là **conversion lúc binding header**, **khác** việc JMS selector tự ép String thành số.

Hãy phân biệt:
- **JMS selector** `retryCount >= 2` sẽ không mặc định so sánh đúng nếu property là String.
- **Spring `@Header("retryCount") int`** có thể chuyển String thành số khi xử lý method parameter.
- **Schema contract** vẫn nên đặt numeric JMS property bằng numeric setter khi về mặt nghiệp vụ nó là số.

Không dùng header conversion để che lỗi type contract từ producer.

### 5.3. Required, default và dữ liệu nhạy cảm

Khi header `tenantId` được dùng để phân quyền, không đặt default tenant một cách tùy tiện. Nếu user gửi một JMS property giả mạo, `@Header("tenantId")` chỉ trích giá trị đó, **không chứng minh nguồn gửi đã được ủy quyền**. Broker ACL/TLS, identity và business authorization phải xác minh tenant đúng phạm vi.

## 6. @Headers, MessageHeaders và JmsMessageHeaderAccessor

Dùng `@Headers` khi cần map:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(
        @Payload String job,
        @Headers Map<String, Object> headers) {
    Object tenant = headers.get("tenantId");
    // Có thể đọc các mapped JMS headers/properties khác.
}
~~~

Dùng `MessageHeaders` nếu muốn abstraction rõ:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(
        @Payload String job,
        MessageHeaders headers) {
    String tenant = headers.get("tenantId", String.class);
}
~~~

Các ví dụ là **mảnh method Java**, cần imports `Map`, `@Headers`, `MessageHeaders` và các Spring JMS annotations.

Dùng Spring `Message<?>` để gom cả body và metadata:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(org.springframework.messaging.Message<String> message) {
    String job = message.getPayload();
    Object tenant = message.getHeaders().get("tenantId");
}
~~~

**Chú ý:** map headers phản ánh phép ánh xạ qua `JmsHeaderMapper` hoặc adapter tương ứng. Nó không nhất thiết chứa mọi JMS/provider property ở cùng tên/kiểu với raw message. Khi cần một raw JMS header ít thông dụng, bạn có thể thêm tham số `jakarta.jms.Message` và đọc trực tiếp thay vì đoán tên Spring header.

### 6.1. JmsMessageHeaderAccessor

Spring cung cấp `org.springframework.jms.support.JmsMessageHeaderAccessor`, giúp truy cập JMS headers dưới dạng accessor typed. Khi cần tính di động ở mức Spring Messaging, có thể dùng accessor thay vì tự ép `headers.get("jms_...")`:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(
        @Payload String job,
        JmsMessageHeaderAccessor headers) {
    String correlation = headers.getCorrelationId();
    // Kiểm tra giá trị null và hợp đồng correlation ID.
}
~~~

Đây là mảnh minh họa; cần import accessor Spring. Tên getter/semantics thuộc phiên bản Spring cụ thể, nên đối chiếu Javadoc khi nâng major.

## 7. Raw jakarta.jms.Message và Session: ngoại lệ trong invocation

`@JmsListener` có thể nhận **raw JMS Message** và **JMS Session**:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(
        @Payload String job,
        jakarta.jms.Message raw,
        jakarta.jms.Session session) throws jakarta.jms.JMSException {

    String jmsMessageId = raw.getJMSMessageID();
    boolean transacted = session.getTransacted();
    // Không tự đóng session: listener container sở hữu vòng đời.
}
~~~

JMS listener adapter có khả năng cung cấp các đối tượng raw này làm **additional arguments** cho invoker. Đó không phải cùng một resolver với `@Header` hoặc `@Payload`.

**Vì sao cần raw message?** Có thể cần:
- `getJMSCorrelationID()`, `getJMSRedelivered()` hoặc `getJMSReplyTo()` theo JMS API.
- Provider-specific property hoặc header không được Spring mapper chuyển đúng.
- Đọc một `TextMessage`/`BytesMessage` cụ thể khi contract không dùng Java DTO converter.

**Vì sao cần Session?** Một số trường hợp reply/interop cần tạo JMS message với session đang xử lý; nhưng phần lớn business handlers không nên phụ thuộc Session. Không gọi `session.close()`, `session.commit()`, `session.rollback()` hoặc `message.acknowledge()` trong code chung mà không thiết kế ownership/transaction chính xác. Với Spring listener container, nó thường chịu trách nhiệm ACK/commit/rollback.

### 7.1. Raw JMS Message khác Spring Message

| Khía cạnh | `jakarta.jms.Message` | `org.springframework.messaging.Message<T>` |
| --- | --- | --- |
| Thư viện | Jakarta Messaging/JMS | Spring Messaging |
| Body | Đọc theo subtype hoặc JMS body API | `getPayload()` đã nằm trong object generic |
| Headers | `getJMS...()` / `get...Property()` | `getHeaders()` trả `MessageHeaders` |
| Session | Thuộc JMS container/protocol | Không mang JMS Session |
| Dùng khi | Cần API transport cụ thể | Muốn handler ít phụ thuộc JMS |
| Conversion | Tùy body type & Spring adapter | Spring Messaging method argument resolution |

**Không import nhầm:** Nếu cùng file cần cả hai, viết fully-qualified name cho một type; Java không thể có hai `import ...Message;` trùng tên ngắn rồi mong compiler tự phân biệt.

## 8. DefaultMessageHandlerMethodFactory thực sự tạo những gì?

Trong Spring Framework 6.2, class:

~~~text
org.springframework.messaging.handler.annotation.support
    .DefaultMessageHandlerMethodFactory
~~~

triển khai `MessageHandlerMethodFactory`, `BeanFactoryAware` và `InitializingBean`. Nó tạo `InvocableHandlerMethod` gắn với các `HandlerMethodArgumentResolver`.

Những setter thường dùng:

~~~java
factory.setConversionService(conversionService);
factory.setMessageConverter(springMessagingConverter);
factory.setValidator(validator);
factory.setCustomArgumentResolvers(customResolvers);
~~~

**Quan trọng:** `setMessageConverter` ở class này nhận **`org.springframework.messaging.converter.MessageConverter`**. Nó **khác interface** `org.springframework.jms.support.converter.MessageConverter` dùng cho `JmsTemplate` và listener JMS adapter. Không thể hoán đổi chúng chỉ vì cùng có tên `MessageConverter`.

### 8.1. Resolver order

Thứ tự khởi tạo các resolver mặc định trong Spring Messaging 6.2 thường là:

~~~text
1. HeaderMethodArgumentResolver      -> @Header
2. HeadersMethodArgumentResolver     -> @Headers
3. MessageMethodArgumentResolver     -> Spring Message<?>
4. Custom resolvers (nếu có)
5. PayloadMethodArgumentResolver     -> @Payload và fallback payload
~~~

**Vì sao custom đứng trước payload?** Payload resolver quá rộng; nếu ở trước custom, nó sẽ nhận hầu hết custom argument types. Custom resolver được đặt sau built-in header/message resolvers nhưng trước payload; muốn thay hoàn toàn behavior của built-in resolver cần xây một method factory tùy biến với policy rõ ràng, không chỉ thêm một resolver trùng loại.

### 8.2. Vai trò ConversionService và MessageConverter

- `ConversionService`: chuyển giá trị tham số/header theo cặp Java types, ví dụ String → int, enum, domain value object nếu đã đăng ký converter.
- **Spring Messaging MessageConverter**: chuyển payload trong Spring `Message<?>` sang target method parameter type theo interface Messaging converter; mặc định sử dụng `GenericMessageConverter` dựa trên ConversionService.
- **JMS MessageConverter**: chuyển `TextMessage`, `BytesMessage`, `MapMessage`, JSON JMS message... thành payload mà adapter đưa vào Spring Messaging; thuộc tầng khác.

Không đưa `MappingJackson2MessageConverter` của `org.springframework.jms.support.converter` vào `DefaultMessageHandlerMethodFactory.setMessageConverter(...)`; chữ ký không tương thích. Nếu muốn JSON DTO, đặt JMS Jackson converter vào `DefaultJmsListenerContainerFactory`/adapter phù hợp **hoặc** thiết kế Spring Messaging converter tương ứng, rồi test end-to-end.

### 8.3. Validator

`setValidator(org.springframework.validation.Validator)` bật validation cho những `@Payload` arguments được đánh dấu `@Validated` hoặc `@jakarta.validation.Valid`. Mặc định của method factory không tự đảm bảo chạy mọi Bean Validation constraint; hãy cung cấp validator thực sự và các dependencies phù hợp.

Khi validator báo lỗi, `PayloadMethodArgumentResolver` có thể ném `MethodArgumentNotValidException` **trước khi body của listener chạy**. Lỗi này cần được xử lý bởi error/transaction policy của container. Không trông cậy business method `try/catch` bắt lỗi xảy ra **trước method invocation**.

### 8.4. Khởi tạo method factory đúng vòng đời

`DefaultMessageHandlerMethodFactory` triển khai `InitializingBean`; khi định nghĩa là một `@Bean`, Spring gọi `afterPropertiesSet()` sau khi inject properties/BeanFactory. Nếu tự `new` một factory và truyền thẳng tới registrar bên ngoài vòng đời bean, các argument resolvers có thể **chưa được khởi tạo**. Cách đơn giản, an toàn: khai báo nó thành **Spring bean** rồi inject vào `JmsListenerConfigurer`.

## 9. Cấu hình đúng qua JmsListenerConfigurer

Một Spring configurer:

~~~java
@Configuration
@EnableJms
public class JmsMethodConfigurer implements JmsListenerConfigurer {

    private final DefaultMessageHandlerMethodFactory methodFactory;

    public JmsMethodConfigurer(
            DefaultMessageHandlerMethodFactory methodFactory) {
        this.methodFactory = methodFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        registrar.setMessageHandlerMethodFactory(methodFactory);
    }
}
~~~

Đây là **mảnh cấu hình class**; cần bean `DefaultMessageHandlerMethodFactory` đã khai báo trong cấu hình khác, cùng các imports Spring phù hợp. `JmsListenerConfigurer` thuộc `org.springframework.jms.annotation`, còn `JmsListenerEndpointRegistrar` thuộc `org.springframework.jms.config`.

**Không nhầm hai factory:**
- `registrar.setMessageHandlerMethodFactory(...)` cung cấp cách **giải tham số và gọi method**.
- `registrar.setContainerFactory(...)` cung cấp **listener container** để nhận message từ broker.

Một endpoint có thể dùng container factory cấu hình transacted/concurrency đúng nhưng vẫn không parse được DTO nếu method converter thiếu; ngược lại, một method factory có validator tốt cũng không bảo đảm JMS retry nếu container ACK trước khi handler thất bại.

### 9.1. Spring Boot có tự bật @JmsListener không?

Spring Boot tự cấu hình listener infrastructure ở nhiều cấu hình JMS chuẩn. Trong project Spring Framework thuần có thể dùng `@EnableJms`. Lab bên dưới đặt `@EnableJms` tường minh, không tự tạo hai bộ infrastructure. Khi làm việc với một ứng dụng có nhiều modules, nên kiểm tra bean factory/annotation support hiện hữu trước khi bổ sung cấu hình để tránh xung đột.

### 9.2. Chọn container factory độc lập

~~~java
@Bean("jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory listenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1");
    return factory;
}
~~~

Đây là **mảnh bean method** có imports Jakarta JMS ConnectionFactory và Spring factory. Nó ảnh hưởng JMS Session, transaction và concurrency, không thay `DefaultMessageHandlerMethodFactory`.

## 10. Validation với @Payload và @Validated

Ví dụ business payload `String` chỉ được chấp nhận nếu bắt đầu bằng prefix `job-`. Với Spring `Validator`:

~~~java
public final class JobIdValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return String.class.equals(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        String value = (String) target;
        if (!value.startsWith("job-")) {
            errors.reject("jobId.invalid", "Job ID must start with job-");
        }
    }
}
~~~

Đây là **mảnh class**, cần imports `org.springframework.validation.Validator` và `Errors`, và không cần Jackson/Bean Validation để kiểm tra một chuỗi.

Gắn vào method factory:

~~~java
@Bean
DefaultMessageHandlerMethodFactory handlerMethodFactory() {
    var factory = new DefaultMessageHandlerMethodFactory();
    factory.setValidator(new JobIdValidator());
    return factory;
}
~~~

Listener sử dụng:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(@Payload @Validated String jobId) {
    // Chỉ tới đây khi argument resolution + validator thành công.
}
~~~

`@Validated` là `org.springframework.validation.annotation.Validated`; nó đánh dấu đối số cần validation tại `PayloadMethodArgumentResolver`. Đối với DTO có Jakarta Bean Validation constraints (`@NotBlank`, `@Min`...), cần `jakarta.validation.Valid`, Bean Validation provider (ví dụ Hibernate Validator qua `spring-boot-starter-validation`) và Spring Validator phù hợp.

### Khác biệt với method-level validation

`@Validated` đặt trên **payload parameter** kích hoạt validation trong argument resolver; một số mô hình cũng dùng AOP method validation trên class/service. Hai đường này **khác nhau** về thời điểm throw exception và cách cấu hình. Không viết tài liệu như thể mọi `@NotBlank` trên method param đều tự chạy chỉ vì service có `@Validated` ở class.

### Một case cần nhớ: lỗi xảy ra trước handler

Nếu `jobId="bad"`, validator có thể ném `MethodArgumentNotValidException` trước khi code bên trong `handle(...)` được chạy. Với transacted listener container, lỗi có thể rollback JMS Session; với không-transacted/AUTO_ACK, redelivery không được bảo đảm theo cùng cách. Phải có DLQ/max redelivery và cảnh báo để tránh poison message.

## 11. Custom HandlerMethodArgumentResolver

Khi method handler cần một object domain được tạo từ headers, ví dụ `TenantContext`, có thể thêm resolver tùy chỉnh.

**File domain type (mảnh Java 17+):**

~~~java
public record TenantContext(String tenantId) {}
~~~

**Mảnh resolver Spring Messaging:**

~~~java
public final class TenantContextArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return TenantContext.class.equals(parameter.getParameterType());
    }

    @Override
    public Object resolveArgument(
            MethodParameter parameter,
            org.springframework.messaging.Message<?> message) {

        Object value = message.getHeaders().get("tenantId");
        if (!(value instanceof String tenant) || tenant.isBlank()) {
            throw new IllegalArgumentException("Missing tenantId");
        }
        return new TenantContext(tenant);
    }
}
~~~

Các mảnh này cần imports `org.springframework.core.MethodParameter`, `org.springframework.messaging.handler.invocation.HandlerMethodArgumentResolver` và được đặt thành các file/class đúng tên. **Đừng lấy nhầm** `org.springframework.web.method.support.HandlerMethodArgumentResolver` của Spring MVC: messaging handler resolver là interface **khác package và khác signature**.

Đăng ký:

~~~java
@Bean
DefaultMessageHandlerMethodFactory handlerMethodFactory() {
    var factory = new DefaultMessageHandlerMethodFactory();
    factory.setCustomArgumentResolvers(
            List.of(new TenantContextArgumentResolver()));
    return factory;
}
~~~

Cần import `java.util.List`. Từ đó một method-based listener có thể nhận:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(@Payload String jobId, TenantContext context) {
    // Đọc context.tenantId() do custom resolver tạo.
}
~~~

**Điều cần test:** resolver chỉ được gọi cho đúng target type, không chiếm tham số `@Header` hoặc Spring `Message<?>`, và ném exception hợp lý khi header thiếu. Vì custom resolvers được đặt **trước payload fallback**, không annotate `TenantContext` bằng `@Payload` rồi kỳ vọng nó luôn được convert từ body; hãy quyết định rõ loại tham số đó lấy từ nguồn nào.

### Khi nào không cần custom resolver?

Nếu chỉ cần một header đơn giản, `@Header("tenantId")` đã đủ. Custom resolver đáng dùng khi nhiều handlers cùng cần một **context object có quy tắc xác thực/chuẩn hóa riêng**, và bạn muốn centralize việc dựng context. Resolver không phải security boundary độc lập: thông tin tenant từ JMS property phải được đối chiếu với identity/broker ACL và quyền nghiệp vụ.

## 12. Lab hoàn chỉnh: Java 17, Spring Boot 3.5 và Artemis embedded

Lab tập trung vào **method factory + argument resolution + validation**, không cần Jackson JSON converter. Một `TextMessage` chứa `job-101` được gửi cùng tenant/attempt metadata. Listener khai báo đủ các dạng:
- `@Payload @Validated String`;
- `@Header("tenantId") String`;
- `@Header("retryCount") int`;
- `@Headers Map<String,Object>`;
- raw `jakarta.jms.Message`;
- `jakarta.jms.Session`.

Một `CountDownLatch` giữ `ApplicationRunner` chờ callback, giúp in một dòng kết quả theo thứ tự xác định, không phụ thuộc scheduling giữa các thread.

### 12.1. Khởi tạo Maven project

Tạo project tại https://start.spring.io/:
- Maven, Java 17+, Spring Boot 3.5.x.
- Group `com.example`, artifact `jms-arguments-lab`.
- Package `com.example.jmsargumentslab`.
- Dependency **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).

Thêm vào `pom.xml` có Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Đây là **dependency bổ sung**, không phải toàn bộ `pom.xml`. Chọn phiên bản Artemis do Boot BOM quản lý. Vì lab dùng custom Spring `Validator`, **không bắt buộc** thêm Jakarta Bean Validation starter; muốn chuyển sang `@Valid` Bean Validation DTO thì thêm `spring-boot-starter-validation`.

### 12.2. Cấu hình local broker

Tạo `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-arguments-lab
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=handler.method.demo
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Broker embedded này chỉ phục vụ demo argument resolution; `persistent=false` có nghĩa lab **không kiểm chứng durability sau restart**. Với môi trường production cần broker có persistence, auth/TLS, quota và DLQ phù hợp.

### 12.3. File 1 — Application entry point, JMS factory và producer

Lưu `src/main/java/com/example/jmsargumentslab/JmsArgumentsLabApplication.java`:

~~~java
package com.example.jmsargumentslab;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.messaging.handler.annotation.support.DefaultMessageHandlerMethodFactory;

@SpringBootApplication
@EnableJms
public class JmsArgumentsLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsArgumentsLabApplication.class, args);
    }

    @Bean("jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory factory) {

        var containerFactory = new DefaultJmsListenerContainerFactory();
        containerFactory.setConnectionFactory(factory);
        containerFactory.setSessionTransacted(true);
        containerFactory.setConcurrency("1");
        return containerFactory;
    }

    @Bean
    DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory(
            JobIdValidator validator) {

        var methodFactory = new DefaultMessageHandlerMethodFactory();
        methodFactory.setValidator(validator);
        return methodFactory;
    }

    @Bean
    ApplicationRunner publish(
            JmsTemplate template,
            ListenerResult result) {

        return args -> {
            template.send("handler.method.demo", session -> {
                TextMessage text =
                        session.createTextMessage("job-101");
                text.setStringProperty("tenantId", "shop-a");
                text.setIntProperty("retryCount", 2);
                text.setJMSCorrelationID("corr-101");
                return text;
            });

            if (!result.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not handle the message in time");
            }

            System.out.println("RESULT=" + result.value());
        };
    }
}
~~~

**Tại sao `jmsHandlerMethodFactory` là bean?** Spring tự gọi lifecycle initialization (`afterPropertiesSet`) trên `DefaultMessageHandlerMethodFactory` trước khi configurer gắn nó vào registrar. Đồng thời `JmsListenerContainerFactory` là bean riêng để nhận message với `sessionTransacted=true`. Đó là **hai factory khác chức năng**.

### 12.4. File 2 — JmsListenerConfigurer gắn method factory

Lưu `src/main/java/com/example/jmsargumentslab/ArgumentConfigurer.java`:

~~~java
package com.example.jmsargumentslab;

import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.messaging.handler.annotation.support.DefaultMessageHandlerMethodFactory;

@Configuration(proxyBeanMethods = false)
public class ArgumentConfigurer implements JmsListenerConfigurer {

    private final DefaultMessageHandlerMethodFactory methodFactory;

    public ArgumentConfigurer(
            DefaultMessageHandlerMethodFactory methodFactory) {
        this.methodFactory = methodFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        registrar.setMessageHandlerMethodFactory(methodFactory);
    }
}
~~~

`ArgumentConfigurer` **không** thay factory JMS container đã khai báo trong application. Nó chỉ thay cách Spring tạo invoker và bind arguments cho các `@JmsListener` method-based endpoints.

### 12.5. File 3 — Validator cho payload String

Lưu `src/main/java/com/example/jmsargumentslab/JobIdValidator.java`:

~~~java
package com.example.jmsargumentslab;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class JobIdValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return String.class.equals(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        String jobId = (String) target;
        if (!jobId.startsWith("job-")) {
            errors.reject(
                    "jobId.invalid",
                    "Job ID must start with job-");
        }
    }
}
~~~

`JobIdValidator` minh họa Spring Validator thuần, không cần Hibernate Validator/Bean Validation provider. Với dự án thật, thường xác thực DTO bằng Jakarta Bean Validation constraints và có schema contract/versioning rõ.

### 12.6. File 4 — Listener gồm đủ loại arguments

Lưu `src/main/java/com/example/jmsargumentslab/JobListener.java`:

~~~java
package com.example.jmsargumentslab;

import java.util.Map;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Session;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@Component
public class JobListener {

    private final ListenerResult result;

    public JobListener(ListenerResult result) {
        this.result = result;
    }

    @JmsListener(
            id = "methodArgsListener",
            destination = "handler.method.demo")
    public void onJob(
            @Payload @Validated String jobId,
            @Header("tenantId") String tenantId,
            @Header("retryCount") int retryCount,
            @Headers Map<String, Object> headers,
            Message raw,
            Session session) throws JMSException {

        if (!tenantId.equals(headers.get("tenantId"))) {
            throw new IllegalStateException(
                    "Header mapping mismatch");
        }

        String correlation = raw.getJMSCorrelationID();
        boolean transacted = session.getTransacted();

        result.record(
                jobId + "|" + tenantId + "|" + retryCount
                + "|" + correlation + "|" + transacted);
    }
}
~~~

Điểm cần quan sát:
- `@Payload @Validated` kích hoạt `JobIdValidator` qua `DefaultMessageHandlerMethodFactory`.
- `@Header` giải được tenant string và retryCount int.
- `@Headers` chứa bản đồ Spring headers đã ánh xạ từ JMS properties.
- `Message raw` ở đây là **`jakarta.jms.Message`**; nếu import `org.springframework.messaging.Message` thì behavior và API khác.
- `Session` do container cung cấp; `session.getTransacted()` trả `true` theo cấu hình `setSessionTransacted(true)` trong lab.
- Method khai báo `throws JMSException` vì các getter raw JMS có checked exception; Spring method invocation có thể propagate exception để container quản lý.

**Không tự gọi `session.commit()`/`session.close()` trong listener**. Để container quyết định transaction sau khi method hoàn tất.

### 12.7. File 5 — Đồng bộ đầu ra để không race với listener thread

Lưu `src/main/java/com/example/jmsargumentslab/ListenerResult.java`:

~~~java
package com.example.jmsargumentslab;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

@Component
public class ListenerResult {

    private final CountDownLatch latch = new CountDownLatch(1);
    private volatile String value;

    public void record(String newValue) {
        this.value = newValue;
        latch.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    public String value() {
        return this.value;
    }
}
~~~

Chỉ dùng `CountDownLatch` để chứng minh callback được gọi. Trong production **không dùng** một latch cố định để điều khiển pipeline JMS chạy dài hạn; dùng metric, transaction và status store thích hợp.

### 12.8. Cách chạy và stdout

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Với Artemis embedded hoạt động, queue ban đầu trống, không có consumer cạnh tranh, mọi Spring bean tải thành công và callback hoàn tất trong 10 giây, dòng ứng dụng in ra là:

~~~text
RESULT=job-101|shop-a|2|corr-101|true
~~~

Các log Boot/Artemis khác có thể xuất hiện trước/sau. Sau khi runner in dòng kết quả, process có thể vẫn chạy vì JMS listener containers dùng threads; dừng bằng Ctrl+C và quan sát graceful shutdown.

**Điều dòng RESULT chứng minh:** payload được giải, các headers/đối tượng JMS được cung cấp, validator cho phép `job-101`, Session đang transacted. **Nó không chứng minh** exactly-once business effects hoặc đã JMS commit ở thời điểm `ListenerResult.record` được gọi; commit của container xảy ra theo lifecycle sau callback.

### 12.9. Bài thử lỗi validation có kiểm soát

Thay `"job-101"` thành `"invalid-101"`. Validator báo lỗi trước khi body method được chạy. Vì factory dùng JMS transaction, message có thể bị rollback và broker redeliver theo policy. **Không thử điều này trên broker production hoặc queue không có giới hạn retry**: poison message có thể lặp mãi và runner sẽ timeout. Với test integration cần cấu hình max deliveries và DLQ rồi kiểm tra số lần delivery/rollback.

### 12.10. Bài thử lỗi header

Bỏ `setStringProperty("tenantId","shop-a")` khi tạo message. `@Header("tenantId")` mặc định bắt buộc; resolution có thể fail **trước method invocation**, chứ không đến câu `if` trong handler. Đây là ranh giới quan trọng giữa lỗi argument binding và lỗi business logic. Kịch bản này cũng cần broker test riêng có retry budget/DLQ.

## 13. JSON DTO: đừng nhầm hai hệ converter cùng tên

Khi payload là JSON từ `TextMessage` và muốn method:

~~~java
@JmsListener(destination = "orders.json")
public void onOrder(@Valid @Payload OrderEvent event) {
    // DTO đã được convert và validate.
}
~~~

cần các điều kiện sau:
1. Producer phát **JSON body theo schema**, không chỉ một Java `toString()`.
2. Container/adapter dùng converter JSON phù hợp, chẳng hạn **`org.springframework.jms.support.converter.MappingJackson2MessageConverter`** trong Spring Framework 6.x, với target text/bytes và type ID mapping (hoặc phương án parse typed tường minh).
3. `DefaultMessageHandlerMethodFactory` có Spring `Validator` biết cách validate DTO, thường thông qua `LocalValidatorFactoryBean` và `spring-boot-starter-validation`.
4. `@Valid` là `jakarta.validation.Valid`; constraints của `OrderEvent` được định nghĩa với required fields/ranges.
5. JMS transaction/ACK, DLQ và idempotency đáp ứng hợp đồng nghiệp vụ.

**Hai interface không hoán đổi được:**

~~~text
org.springframework.jms.support.converter.MessageConverter
   - toMessage(Object, jakarta.jms.Session)
   - fromMessage(jakarta.jms.Message)

org.springframework.messaging.converter.MessageConverter
   - toMessage(Object, MessageHeaders)
   - fromMessage(org.springframework.messaging.Message<?>, Class<?>)
~~~

Tùy version, Spring Messaging interface có overload hỗ trợ conversion hint. Dòng minh họa là các chữ ký chủ chốt, **không phải định nghĩa interface đầy đủ để copy biên dịch**.

### Lưu ý bảo mật JSON

Nếu converter nhận type ID từ JMS properties:
- Đặt alias cố định và whitelist rõ, không cho arbitrary Java FQCN từ nguồn không tin cậy.
- Cập nhật Spring Framework theo bản sửa bảo mật hiện hành; không coi map type ID là lớp chống deserialization duy nhất.
- Tránh Jackson polymorphic default typing rộng, cấu hình parser limits, validate schema.
- Không gửi Java `ObjectMessage` qua biên service không tin cậy chỉ để nhận typed DTO.

## 14. Tối ưu ConversionService cho header/domain type

Để method nhận `@Header("region") RegionCode region` thay vì String, có thể đăng ký converter với `ConversionService`:

~~~java
// Mảnh code: enum RegionCode { APAC, EU, US } do app định nghĩa.
var conversion = new DefaultFormattingConversionService();
conversion.addConverter(
        String.class,
        RegionCode.class,
        RegionCode::valueOf);

var methodFactory = new DefaultMessageHandlerMethodFactory();
methodFactory.setConversionService(conversion);
~~~

Đây là **mảnh cấu hình**, cần imports `DefaultFormattingConversionService`, DTO/enum và đăng ký factory là Spring bean để lifecycle khởi tạo resolver. Trong lab đã có bean method factory riêng; không copy đoạn này tạo **một factory mới** rồi bỏ qua cấu hình validator.

Chọn converter chủ động:
- Giá trị header từ JMS có kiểu gì?
- Conversion có phân biệt hoa/thường?
- Giá trị không hợp lệ ném exception loại nào?
- Nếu header optional thì xử lý null ra sao?
- Mã này có cần tự thêm telemetry/audit khi mapping fail không?

Một `ConversionService` không tự parse JSON DTO nếu thiếu thích hợp `MessageConverter`; nó chủ yếu quản lý conversion giữa Java value types.

## 15. Custom resolver hay @Header? Tiêu chí lựa chọn

| Yêu cầu | Giải pháp | Ghi chú |
| --- | --- | --- |
| Một property String/number | `@Header` | Thường đủ; dễ đọc |
| Toàn bộ Spring headers | `@Headers` hoặc `MessageHeaders` | Giữ abstraction |
| Header JMS đặc thù không map | raw `jakarta.jms.Message` | Chấp nhận dependency transport |
| Payload một kiểu đơn giản | `@Payload` + converter mặc định | TextMessage → String |
| Payload JSON DTO | JSON converter + validator | Kiểm tra schema/type security |
| Context domain được tạo từ nhiều headers | Custom `HandlerMethodArgumentResolver` | Đặt trước payload fallback |
| Nhận `Session` để tạo JMS reply | raw `jakarta.jms.Session` | Không tự điều khiển transaction tùy tiện |
| Ngăn handler chạy khi DTO invalid | `setValidator` + `@Valid`/`@Validated` | Phải có validator thực |
| Điều chỉnh số threads/recovery/transaction | `DefaultJmsListenerContainerFactory` | Không thuộc method factory |

**Đừng tạo resolver custom chỉ để đổi tên `tenantId`:** thông thường có thể xử lý qua `@Header` hoặc một domain service. Resolver mới làm tăng khả năng ảnh hưởng đến thứ tự resolution và error handling.

## 16. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| `@Header` không tìm thấy tenantId | Producer không đặt JMS property, mapper khác, sai hoa/thường | Đọc raw JMS properties và Spring headers trong broker test |
| `@Header int` bị lỗi chuyển kiểu | Property là String không hợp lệ hoặc ConversionService thiếu converter | Kiểm tra setter và value thực tế |
| `@Headers Map` thiếu một field | JMS header mapper chỉ copy một subset hoặc field nằm trong body | Không đoán; kiểm tra raw message và mapper config |
| Method nhận String thay DTO | `SimpleMessageConverter` không parse JSON | Gắn JMS JSON converter/schema |
| `@Valid` không phát huy hiệu lực | Chưa có Spring Validator trong factory hoặc Bean Validation provider | Cấu hình `setValidator`, starter validation nếu dùng constraints |
| Custom resolver không chạy | Sai interface package hoặc `supportsParameter` trả false | Dùng messaging resolver, test order |
| Spring dùng payload thay TenantContext | Resolver không được đăng ký vào factory của annotated methods | Kiểm tra registrar/bean method factory |
| Method factory lỗi sau khi tự `new` | Chưa chạy `afterPropertiesSet` khởi tạo argument resolvers | Khai báo method factory là Spring bean |
| Thấy `Message` nhưng không có `getPayload()` | Import `jakarta.jms.Message` thay vì Spring Messaging `Message<?>` | Dùng fully-qualified class khi cần cả hai |
| `Session` không có/được quản lý sai | Handler chạy ngoài JMS listener adapter hoặc tự đóng session | Chỉ dùng injection qua `@JmsListener` với infrastructure hợp lệ |
| Error trong converter nhưng handler catch không thấy | Lỗi xảy ra trước invocation | Container error handler, transaction và DLQ |
| Số lần delivery không khớp | Rollback, broker redelivery, concurrency hoặc ack mode | Bật message ID/correlation ID/retry metrics, idempotency |
| `@Header(required=false) int` fail khi thiếu | Primitive `int` không biểu diễn null | Dùng `Integer` hoặc `String` nullable |
| Duplicate method invocation | Hai listener endpoints cùng queue hoặc redelivery | Kiểm tra registry ID, subscriptions và idempotency |
| Không có listener nào chạy | `@EnableJms`/Boot autoconfig/factory/connection sai | Kiểm tra Spring context, broker URL, destination name |
| Custom factory mất một số Boot defaults | Tự `new DefaultJmsListenerContainerFactory` mà không áp configurer | Sử dụng `DefaultJmsListenerContainerFactoryConfigurer` khi cần giữ Boot settings |
| ACK xảy ra trước business success | Container/session không transacted hoặc exception bị nuốt | Xem ACK policy; xử lý fail bằng transaction, DLQ |
| Validation lỗi liên tục gây backlog | Poison message thiếu giới hạn redelivery | Bounded retry, quarantine/DLQ, cảnh báo |

### Về logger/debug

Nên log **destination, endpoint ID, JMSMessageID, correlation ID, error category, số lần redelivery** khi provider hỗ trợ, nhưng không log toàn bộ payload chứa PII/secret chỉ để chẩn đoán. Payload validation lỗi có thể xảy ra trước method body; quan sát container-level error handlers thay vì chỉ log trong handler.

## 17. Transaction, retry, DLQ và ranh giới công việc

Trong lab `sessionTransacted=true` để phân biệt các pha:

~~~text
Broker giao message
  -> JMS listener container nhận trong Session
  -> message converter / argument resolvers
  -> payload validator
  -> business handler
  -> handler return bình thường => local JMS commit
  -> handler/conversion error => local JMS rollback (policy broker)
~~~

Nếu message invalid liên tục, nó có thể bị redeliver đến giới hạn broker rồi chuyển DLQ; chính sách broker phải được cấu hình. Nếu handler bắt exception, log rồi **trả về bình thường**, container có thể commit như thành công. Điều này có thể gây mất công việc.

**Không có exactly-once business tự động**:
- Handler ghi DB, process chết trước JMS commit → broker có thể redeliver và DB operation lặp.
- Dùng idempotency key theo event/business ID, inbox/dedup table với unique constraint.
- Nếu producer cần gửi message theo DB transaction, cân nhắc transactional outbox.
- JMS local transaction không tự bao gồm DB transaction; hạ tầng XA/JTA nếu thật sự dùng phải được thiết kế, test và có chi phí rõ.

`DefaultMessageHandlerMethodFactory` chỉ giúp các arguments được binding/validated đúng; nó **không giải quyết** các vấn đề giao nhận, persistence, DLQ, ordering hay network partitions.

## 18. Kiểm thử: unit, integration, negative cases

### 18.1. Unit test method-level

Với custom resolver/validator:
- `JobIdValidator.supports(String.class)` phải true, `supports(Integer.class)` phải false.
- `validate("job-101")` không sinh errors; `validate("bad")` sinh error code.
- `TenantContextArgumentResolver.supportsParameter(...)` đúng với `TenantContext` và sai với kiểu khác.
- `resolveArgument` lấy `tenantId` từ `MessageHeaders` đúng và báo lỗi khi thiếu.
- Custom ConversionService mapping enum, number, malformed values phải có test rõ.

### 18.2. Integration test broker thật

| Tình huống | Kỳ vọng |
| --- | --- |
| TextMessage `job-101` với tenantId và retryCount | Handler nhận String, int, Map và raw JMS Message/Session |
| JMS correlation ID được gửi | Raw JMS getter đọc lại đúng |
| Payload bắt đầu `job-` | Validator pass, method chạy |
| Payload `bad-1` | Validator fail trước invocation; broker xử lý theo transaction |
| Header tenantId bị thiếu | `@Header` báo lỗi trước invocation |
| Header numeric đặt String `"2"` | Có conversion nếu ConversionService cho phép; selector JMS vẫn yêu cầu type contract riêng |
| Target method đòi DTO nhưng JMS converter là Simple | Conversion fail hoặc sai type; không âm thầm tạo DTO |
| Đăng ký custom resolver TenantContext | Context được tạo trước payload fallback |
| Registry có đúng endpoint ID | Không bị tạo hai consumers ngoài ý muốn |
| Listener ném exception sau business write | Transaction/rollback và idempotency được đối chiếu |
| JSON invalid hoặc type ID không biết | Conversion/error handler/DLQ hoạt động |
| Broker reconnect/rolling deployment | Container recovery và compatibility với backlog |
| App bị SIGTERM trong lúc handler chạy | Container dừng đúng pha, xử lý message in-flight theo policy |

**Không đánh giá retry chỉ qua log business method.** Một lỗi conversion/validation có thể xảy ra trước khi method chạy, nên cần quan sát JMS delivery count, broker DLQ, transaction và Spring listener exception logs.

### 18.3. Vì sao unit test không đủ?

Mock `Message<?>` có thể chứng minh custom resolver hoạt động. Nhưng nó không xác minh JMS Session injection, header mapper, broker selectors, ACK/commit, redelivery hoặc thread lifecycle. Dùng Artemis local/container staging cho integration tests; tránh test poison messages vào hàng đợi production.

## 19. Checklist khi thiết kế listener thực tế

- Method có phân biệt rõ payload, header, raw JMS message và Session không?
- Package import của hai `Message` types có chính xác không?
- JMS producer có đặt các properties với tên và Java types đúng contract?
- `@Header` có xử lý optional/missing đúng, tránh primitive khi null?
- Spring `MessageHeaders`/`JmsHeaderMapper` có giữ đúng metadata cần thiết?
- `DefaultMessageHandlerMethodFactory` được đăng ký qua `JmsListenerConfigurer`/`JmsListenerEndpointRegistrar` chưa?
- Method factory là Spring bean đã chạy initialization?
- Validator được cấu hình và `@Payload @Valid`/`@Validated` được dùng đúng chưa?
- Có nhầm Spring Messaging `MessageConverter` với Spring JMS `MessageConverter` không?
- Custom resolver dùng đúng messaging package và đứng trước payload fallback?
- JMS container factory có đúng `ConnectionFactory`, `pubSubDomain`, concurrency, transaction, converter?
- Khi đổi Spring Boot auto-configuration, có giữ những defaults phù hợp không?
- DTO JSON có schema/version/type-ID allowlist, parser constraints và validation?
- Listener throwing exception có rollback theo broker policy? Có chặn poison message bằng retry budget/DLQ?
- Có idempotency khi broker redeliver sau crash?
- Có giám sát registry IDs, error handler, JMS message ID, DLQ và shutdown?
- Đã có integration tests cho header missing, conversion fail, validation fail và normal path?
- Không tự gọi `Session.close()`/`commit()` bừa bãi trong handler?
- Không dùng headers từ producer chưa xác thực như dữ liệu cấp quyền duy nhất?

## 20. Bài tập củng cố

1. Phân biệt ba tầng listener container, JMS-to-Spring converter và handler method factory trên một sơ đồ.
2. Một method `onJob(String job, @Header("tenantId") String tenant)` nhận JMS `TextMessage` và property tenantId. Resolver nào xử lý từng tham số?
3. Đổi `@Header("retryCount") int` thành `Integer` và thiếu property, chuyện gì khác khi có `required=false`?
4. Tại sao method factory `setMessageConverter(...)` không chấp nhận `org.springframework.jms.support.converter.MappingJackson2MessageConverter`?
5. Giải thích vì sao `PayloadMethodArgumentResolver` phải ở sau custom resolver.
6. Một listener muốn nhận raw `jakarta.jms.Message` và `org.springframework.messaging.Message<String>` cùng lúc. Cách tránh import collision?
7. Nếu `@Validated @Payload String` bị validator reject, code trong method có chạy không? Container xử lý message theo transaction thế nào?
8. Thêm custom resolver `TenantContext` và chứng minh nó lấy ID từ headers, không phải JSON body.
9. Dùng `@Headers Map` để quan sát message metadata và so sánh với `raw.getJMSCorrelationID()`; có thể khác nhau vì mapper không?
10. Giải thích vì sao `@Header("tenantId")` không tự xác thực tenant.
11. Một ứng dụng có `DefaultMessageHandlerMethodFactory` bean nhưng không kết nối tới registrar; liệu các `@JmsListener` có dùng bean đó tự động không?
12. Thay tên queue của lab để broker không tồn tại và tắt auto-create; phân biệt lỗi connection/destination với lỗi argument resolution.
13. Thử một message malformed `job=bad-1` trong staging, kiểm chứng rollback, redelivery count và DLQ mà không gây infinite retry.
14. Đặt converter/validator typed DTO v2 nhưng backlog có JSON v1; đề xuất migration với schema version, alias và tests.
15. Trong lab, sửa method dùng một Spring `Message<String>` thay vì `@Payload String`/`@Headers Map`; thông tin nào vẫn xem được, thông tin nào phải đọc raw?
16. Vì sao một dòng `RESULT=...` in từ callback không chứng minh JMS commit hoặc DB exactly-once?

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — **Annotation-driven JMS Listener Endpoints**, supported arguments và validator configuration: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — **DefaultMessageHandlerMethodFactory** Javadoc, ConversionService, MessageConverter, Validator, custom resolvers: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html
- Spring Framework 6.2 — **PayloadMethodArgumentResolver** Javadoc, validation and fallback payload: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html
- Spring Framework 6.2 — **JmsListenerConfigurer** Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListenerConfigurer.html
- Spring Framework 6.2 — **MessagingMessageListenerAdapter** Javadoc, raw JMS Message/Session as additional arguments: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/adapter/MessagingMessageListenerAdapter.html
- Spring Framework 6.2 — **JmsListener** API, supported method signatures: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Boot 3.5 — **Messaging with JMS**, Artemis autoconfiguration: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Boot 3.5 — **System Requirements**, Java 17: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Jakarta Messaging 3.1 — **JMS Message and Session APIs**: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
