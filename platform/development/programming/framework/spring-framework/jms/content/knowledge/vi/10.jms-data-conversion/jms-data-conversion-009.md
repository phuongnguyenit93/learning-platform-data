# Phân biệt lỗi chuyển đổi với lỗi xử lý nghiệp vụ trong Spring JMS

## 1. Mục tiêu và tình huống thực tế

Trong ứng dụng **Spring Framework – JMS**, một message có thể bị từ chối trước khi đi vào hàm xử lý, hoặc đã chuyển đổi thành Java object thành công nhưng thất bại vì quy tắc nghiệp vụ. Cả hai trường hợp đều có thể xuất hiện trong log như “listener failed”, nhưng **nguyên nhân, người chịu trách nhiệm sửa và chính sách retry không giống nhau**.

Xét hệ thống nhận lệnh đặt hàng:
- Message có JSON `{"orderId":"O-101","quantity":2}`, schema hợp lệ và còn hàng: **xử lý thành công**.
- Message là `{invalid-json` hoặc có type id không được nhận diện: **lỗi chuyển đổi dữ liệu**.
- Message hợp lệ về cú pháp và cấu trúc nhưng `quantity=0`, sản phẩm hết hàng hoặc đơn đã bị hủy: **lỗi nghiệp vụ**, tùy contract và chính sách hệ thống.
- Message hợp lệ nhưng database đang mất kết nối: **lỗi hạ tầng tạm thời**, phát sinh trong lúc xử lý nghiệp vụ, không phải lỗi JSON.

Nếu cấu hình retry vô hạn cho message JSON hỏng, consumer sẽ mắc kẹt trên một **poison message**. Nếu ngược lại, chuyển mọi lỗi nghiệp vụ vào DLQ ngay, bạn có thể bỏ qua những lỗi tạm thời đáng lẽ hồi phục sau vài giây.

Sau bài này, bạn sẽ biết:
1. Phân chia đường đi của message thành các giai đoạn và xác định **exception xảy ra trước hay sau business handler**.
2. Phân biệt `MessageConversionException` của JMS, `MessageConversionException` ở tầng Spring Messaging, lỗi validation và ngoại lệ nghiệp vụ.
3. Cấu hình `MessageConverter`, `JmsTemplate` và `@JmsListener` theo cùng hợp đồng dữ liệu.
4. Lựa chọn retry, rollback, dead-letter queue (DLQ), cảnh báo và cơ chế xử lý dữ liệu lỗi phù hợp.
5. Chạy demo **Java 17 + Spring Boot + Artemis** có ba kết quả xác định: thành công, lỗi giải mã và lỗi quy tắc kinh doanh.

Bài tập trung vào **chuyển đổi dữ liệu** tại biên JMS. Việc triển khai outbox, retry queue, schema registry hoặc transaction phân tán ở mức production được đề cập đúng phần liên quan, không biến chúng thành giải pháp mặc định cho mọi lỗi.

## 2. Bản đồ xử lý: lỗi có thể xuất hiện ở đâu?

~~~text
PRODUCER (ứng dụng nguồn)
  Java object
      |
      |  ① MessageConverter.toMessage(...)
      v
  JMS Message / Headers
      |
      |  ② MessageProducer.send(...) / broker
      v
──────────────────── JMS broker / Queue ─────────────────────
      |
      |  ③ Session / consumer nhận JMS Message
      v
  JMS Message
      |
      |  ④ MessageConverter.fromMessage(...)
      v
  Payload Java / Spring Message
      |
      |  ⑤ Adapter: type resolution / @Payload / @Valid / headers
      v
  @JmsListener(OrderCreated command)
      |
      |  ⑥ Business rules, database, external service
      v
  Xử lý thành công / thất bại
      |
      |  ⑦ Transaction, ACK, rollback, redelivery/DLQ
      v
  Hoàn tất vòng đời message
~~~

| Giai đoạn | Lỗi điển hình | Nhận định ban đầu |
|---|---|---|
| ① Producer → JMS | Object không serialize được, mapping không hỗ trợ, converter không tạo được `TextMessage`/`BytesMessage`. | **Outbound conversion error**; broker có thể chưa nhận message. |
| ② Gửi qua JMS | Sai credentials, Queue không tồn tại, network interruption, broker bị từ chối tài nguyên. | **JMS transport/provider error**; không đồng nhất với lỗi converter. |
| ③ Nhận từ broker | Timeout, kết nối đứt, ACK/transaction lỗi. | **Receive/transport error**, thường liên quan broker hoặc hạ tầng. |
| ④ JMS → Java | JSON sai cú pháp, không khớp schema, thiếu type id, kiểu dữ liệu không hỗ trợ. | **Inbound conversion error**, chưa gọi nghiệp vụ. |
| ⑤ Adapter/validation | Thiếu `@Header` bắt buộc, không đổi được tham số method, `@Valid` thất bại. | **Argument binding/validation error**; có thể xảy ra trước method nhưng không luôn thuộc JMS converter. |
| ⑥ Business handler | Số lượng không hợp lệ, đơn không tồn tại, tồn kho thiếu, vi phạm trạng thái, DB timeout. | **Business/infrastructure error**; phải phân loại tiếp thành vĩnh viễn hay tạm thời. |
| ⑦ Commit/ACK | Transaction rollback, broker không xác nhận ACK, lỗi gửi reply. | **Completion/infrastructure error**, thậm chí xảy ra sau side effect nghiệp vụ. |

**Đừng phân loại chỉ theo câu “listener failed”.** Hãy lấy root cause, stack trace, giai đoạn thực hiện, loại payload và message ID. Một exception bọc ngoài như `ListenerExecutionFailedException` có thể che nguyên nhân ở tầng converter hoặc ở code nghiệp vụ.

## 3. Hai chữ “MessageConversionException” khác nhau

Spring có **hai** class cùng simple name:

~~~java
org.springframework.jms.support.converter.MessageConversionException
org.springframework.messaging.converter.MessageConversionException
~~~

| Class | Thuộc thành phần | Ngữ cảnh điển hình |
|---|---|---|
| `org.springframework.jms.support.converter.MessageConversionException` | Spring **JMS**; kế thừa `org.springframework.jms.JmsException` (unchecked). | `MessageConverter.toMessage` hoặc `fromMessage` không chuyển được Java ↔ JMS Message. |
| `org.springframework.messaging.converter.MessageConversionException` | Spring **Messaging**; kế thừa `MessagingException`. | Converter/adapter dùng Spring `Message<?>` trong quá trình chuyển kiểu payload cho annotated handler. |

Cả hai đều biểu đạt thất bại **chuyển đổi**, nhưng class và package khác nhau. Khi viết `catch`, import đúng class; trong chẩn đoán, đọc **fully-qualified class name** nếu log chỉ có `MessageConversionException`.

Các ngoại lệ khác có thể liên quan:

- `jakarta.jms.MessageFormatException`: lỗi ở API provider khi đọc nội dung/kiểu JMS không tương thích.
- `jakarta.jms.JMSException`: checked exception của JMS; Spring có thể chuyển thành một subclass `JmsException` khi dùng `JmsTemplate`.
- `org.springframework.jms.listener.adapter.ListenerExecutionFailedException`: lớp ngoại lệ liên quan việc thực thi listener/adapter, có thể bọc lỗi khác; **đọc `getCause()`**.
- `org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException` hoặc lỗi tham số/validation: phản ánh input không đạt ràng buộc method, chưa chắc business handler đã chạy.
- `IllegalArgumentException`/ngoại lệ do ứng dụng tự tạo: **không đủ thông tin để suy ra nguồn**. Một converter tùy chỉnh cũng có thể ném `IllegalArgumentException`; một service nghiệp vụ cũng có thể parse JSON sai.

Không giả định mọi lỗi conversion đều cùng một class. Với converter tự viết, runtime wrapper và adapter, exception cụ thể phụ thuộc API, phiên bản Spring và cách triển khai. Khi cần xử lý đồng nhất, thiết kế taxonomy ứng dụng ở biên.

## 4. Lỗi chuyển đổi: nhận diện đúng và biết điểm dừng

### 4.1. Outbound conversion: trước khi message được gửi

Với `JmsTemplate.convertAndSend(destination, object)`:

~~~java
// Đoạn mã trong service đã inject JmsTemplate.
jmsTemplate.convertAndSend("sales.orders", orderCreated);
~~~

Spring dùng `MessageConverter.toMessage(orderCreated, session)`. Nếu converter không hỗ trợ class của `orderCreated`, Jackson không serialize được, hoặc không tạo được JMS Message, lỗi xảy ra **trong producer path**. Không mặc định kết luận “broker đã nhận, cần xử lý DLQ” vì có thể chưa có bản tin nào được phát hành.

Phân biệt:
- Converter thất bại **trước** `send`: sửa producer data/schema/converter rồi gửi lại theo business event ID.
- Gửi đã được gọi nhưng kết quả **không xác định** do timeout: broker có thể đã nhận dù client không thấy ACK. Khi retry, dùng idempotency/deduplication; không khẳng định send thất bại hoàn toàn chỉ từ timeout.
- Serializer thành công nhưng payload sai ý nghĩa: đó không phải lỗi chuyển đổi kỹ thuật; kiểm tra contract/schema validation trước khi publish.

### 4.2. Inbound conversion: message đã có trên Queue

Với consumer, `MessageConverter.fromMessage(jmsMessage)` chuyển `TextMessage`/`BytesMessage` thành object Java hoặc kiểu đơn giản. Những ví dụ thường gặp:
- Body chứa JSON thiếu dấu ngoặc hoặc dữ liệu byte không khớp encoding.
- Producer gửi `ObjectMessage` còn consumer mong JSON `TextMessage`.
- Header type id bị thiếu, sai hoặc trỏ đến kiểu không được cho phép.
- Java class đã đổi cấu trúc khiến Jackson không thể tạo object.
- Consumer dùng converter JSON nhưng producer vẫn dùng `SimpleMessageConverter` theo một hợp đồng khác.

Trường hợp JSON sai cú pháp khó tự “khỏi” bằng cách retry cùng byte payload. Trước khi gọi handler, adapter có thể ném conversion exception, và nghiệp vụ **chưa chạy**. Đừng sửa bằng cách `catch (Exception)` ở đầu method `@JmsListener` rồi bỏ qua: method có thể chưa được invoke, nên `catch` trong method **không bắt được** lỗi xảy ra ở converter/adapter bên ngoài nó.

### 4.3. Hợp đồng schema quan trọng hơn chỉ riêng cú pháp JSON

Một payload như:

~~~json
{"orderId":"O-202","quantity":0}
~~~

là JSON hợp lệ. Nếu class Java có `String orderId` và `int quantity`, Jackson có thể tạo object thành công. Nhưng `quantity=0` có thể vi phạm quy tắc “quantity phải dương” và bị **business handler** từ chối.

Ngược lại, một payload:

~~~json
{"orderId":"O-202","quantity":"two"}
~~~

có thể dẫn đến **conversion failure** nếu kiểu Java là `int` và parser không thể chuyển `"two"` sang số (hành vi coercion chính xác tùy cấu hình Jackson). Để chắc chắn, định nghĩa và test chính sách coercion/unknown fields thay vì suy luận từ JSON trông “có vẻ hợp lý”.

**Một JSON trông hợp lệ chưa đủ để là business event hợp lệ.** Cần ít nhất ba tầng hợp đồng:
1. **Syntax/transport:** bytes/TextMessage có decode đúng.
2. **Structure/schema:** field bắt buộc, kiểu, version, type id, ràng buộc dữ liệu đầu vào.
3. **Domain invariant:** trạng thái đơn hàng, tồn kho, quyền nghiệp vụ, giới hạn giao dịch.

Nên xác định ranh giới rõ: lỗi schema/message contract có thể được phát hiện ở converter hoặc validation layer; lỗi domain chỉ nên được quyết định sau khi đã có dữ liệu đủ tin cậy.

## 5. Lỗi validation có phải lỗi chuyển đổi không?

**Không nhất thiết.** Một `@JmsListener` có tham số `@Valid @Payload OrderCreated order` có thể:
- Giải mã JSON thành object thành công ở converter.
- Sau đó bean validation kiểm tra `@NotBlank`, `@Positive` hoặc constraint khác.
- Nếu constraint sai, adapter/argument validation báo lỗi **trước khi method nghiệp vụ chạy**.

Điều này khác cả lỗi JSON syntax và lỗi tồn kho bên trong service. Ở góc độ **xử lý message**, validation đầu vào thường được coi là **permanent contract/input error**, nhưng về mặt class exception nó không bắt buộc là JMS `MessageConversionException`.

Ví dụ phân biệt ba trạng thái:

| Input | Chuyển JSON → Java | Validation đầu vào | Nghiệp vụ |
|---|---|---|---|
| `{broken-json` | **Thất bại** | Không chạy | Không chạy |
| `{"orderId":"","quantity":0}` | Có thể thành công | **Thất bại** nếu áp dụng `@NotBlank`/`@Positive` | Chưa chạy |
| `{"orderId":"O-7","quantity":2}`, nhưng đơn đã đóng | Thành công | Thành công | **Từ chối theo trạng thái domain** |

Nếu dùng `@Valid` trên method, phải bảo đảm bean validator và `DefaultMessageHandlerMethodFactory`/adapter được cấu hình thích hợp; không mặc định Spring JMS tự thực thi mọi annotation validation chỉ vì class có `@NotBlank`.

## 6. Lỗi nghiệp vụ: phân loại thêm permanent và transient

Sau khi converter/adapter tạo payload, business code chạy. Hai lỗi business cùng tạo exception nhưng không nên có cùng chính sách:

| Nhóm | Ví dụ | Khuyến nghị xử lý |
|---|---|---|
| **Business rejection vĩnh viễn** | `quantity <= 0`, trạng thái đơn đã `CANCELLED`, tham chiếu đến object không hợp lệ theo contract. | Ghi kết quả từ chối có mã lý do; ACK/commit **chỉ khi đã xử lý chủ đích** và có audit. Có thể chuyển parking queue/DLQ nếu contract yêu cầu điều tra. |
| **Business conflict có thể tự hết** | Chờ thông tin phụ thuộc đến sau, tài nguyên đang khóa, phiên bản dữ liệu chưa đồng bộ. | Retry có giới hạn + backoff hoặc chờ event phụ thuộc, không lặp vô hạn. |
| **Lỗi hạ tầng tạm thời** | DB timeout, HTTP 503, broker phụ mất kết nối. | Rollback/retry giới hạn, circuit breaker, alert và DLQ khi hết lần thử. |
| **Lỗi lập trình** | `NullPointerException`, bug xử lý mapping nội bộ, giả định domain sai. | Sửa code, không biến mọi bug thành lỗi input; tạm park message để khôi phục sau deploy. |
| **Nghiệp vụ idempotent đã xử lý** | Nhận lại `eventId` từng xử lý thành công. | Có thể ACK như thành công sau khi xác thực kết quả, không lặp side effect. |

Ví dụ lỗi thuộc domain:

~~~java
public final class InvalidOrderQuantityException
        extends RuntimeException {
    public InvalidOrderQuantityException(String id) {
        super("quantity must be positive for " + id);
    }
}
~~~

Đây là **kiểu ngoại lệ ứng dụng tự định nghĩa**, không phải Spring JMS API. Tên exception có ý nghĩa giúp quyết định retry/ACK/DLQ tốt hơn một `IllegalStateException` chung.

Không đồng nhất việc “thất bại bên trong handler” với “business reject”. Một `DataAccessResourceFailureException` từ DB là lỗi hạ tầng phát sinh khi handler đang chạy; tình huống đó thường nên được retry, khác một `InvalidOrderQuantityException`.

## 7. Thiết kế MessageConverter đúng hợp đồng

Trong Spring Framework 6, các giao diện thuộc package `jakarta.jms` (không phải `javax.jms`). Converter JMS chính:

~~~java
org.springframework.jms.support.converter.MessageConverter
~~~

Hai hướng:

~~~java
Message toMessage(Object object, jakarta.jms.Session session)
Object fromMessage(jakarta.jms.Message message)
~~~

Cả hai có thể ném `jakarta.jms.JMSException` hoặc `org.springframework.jms.support.converter.MessageConversionException`, tùy lỗi. `JmsTemplate` gọi converter được cấu hình khi dùng `convertAndSend`/`receiveAndConvert`. Với annotated listener, converter cũng cần được cung cấp đúng cho listener adapter/container factory; đừng mặc định hai phía sẽ luôn có cấu hình giống nhau nếu tự khai báo nhiều factory.

### SimpleMessageConverter

`SimpleMessageConverter` là lựa chọn mặc định trong nhiều cấu hình Spring JMS, xử lý các dạng payload phổ biến như `String` ↔ `TextMessage`, byte[] ↔ `BytesMessage`, `Map` ↔ `MapMessage` và một số object `Serializable`. Nó **không tự đoán rằng JSON String phải deserialize thành record domain của bạn**.

Nếu producer gửi `TextMessage` chứa `{"orderId":"O-1"}`, listener nhận tham số `String` có thể lấy ra nguyên JSON String và phải parse riêng; việc parse JSON **bên trong method** sẽ là một exception xảy ra trong handler, dù bản chất nguyên nhân là dữ liệu đầu vào. Vì vậy phải phân loại theo **nguyên nhân gốc và công đoạn thực sự parse**, chứ không chỉ vị trí stack trace.

### MappingJackson2MessageConverter

Dùng converter Jackson 2 của Spring Framework 6 để chuyển POJO/record ↔ JSON TextMessage:

~~~java
import java.util.Map;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();
converter.setTargetType(MessageType.TEXT);
converter.setTypeIdPropertyName("_type");
converter.setTypeIdMappings(
        Map.of("order.created.v1", OrderCreated.class));
converter.setTrustedPackages("example.jms"); // Spring Framework 6.2.19+
~~~

Đây là **mảnh cấu hình**, giả định đã có type `OrderCreated`. `setTypeIdPropertyName("_type")` rất quan trọng: khi nhận, converter cần biết kiểu Java mục tiêu. `setTypeIdMappings` cho phép dùng **ID ổn định** như `order.created.v1` thay vì bắt producer gửi tên Java class nội bộ. `setTargetType(TEXT)` giúp kiểm tra body JSON thuận tiện trong công cụ broker.

**Bảo mật:** với broker hoặc producer không hoàn toàn tin cậy, không cho phép type id tùy ý kích hoạt deserialize class không được phép. Spring Framework **6.2.19+** bổ sung `setTrustedPackages(...)` và vá vấn đề deserialization ở Jackson JMS converters (CVE-2026-41855); hãy dùng phiên bản được vá, allowlist ID/type/package và giới hạn quyền publish. Type ID mapping nên là hợp đồng rõ ràng, không phải cổng cho việc chọn class arbitrary.

## 8. Demo chạy được: ba trường hợp khác nhau trên cùng Queue

Mục tiêu demo:
- Dùng **Spring Boot 3.5.16**, BOM quản lý **Spring Framework 6.2.19**, Java 17 và Artemis embedded.
- Dùng `MappingJackson2MessageConverter` tạo `TextMessage` chứa JSON và JMS property `_type`.
- Gửi ba message lần lượt, sau mỗi lần **nhận raw JMS Message**, gọi converter rõ ràng và chạy quy tắc nghiệp vụ.
- In ba kết quả cố định để người học **thấy lỗi xuất hiện ở tầng nào**.

**Lưu ý giới hạn cố ý:** ví dụ dùng `JmsTemplate.receive(...)` và xử lý converter **sau khi nhận** để quan sát trực tiếp hai đường lỗi, nên không thể suy ra cơ chế rollback/redelivery của `@JmsListener` production. Ở chế độ AUTO_ACKNOWLEDGE, một message đã được `receive()` rồi mới conversion-fail có thể đã được ACK. Bài sẽ chỉ ra cách bố trí listener transaction cho hệ thống thật ở phần sau.

### 8.1. Cấu trúc

~~~text
jms-error-boundary/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/application.yml
    └── java/example/jms/ErrorBoundaryApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-error-boundary'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    implementation 'org.springframework.boot:spring-boot-starter-json'

    // Phần server nhúng chỉ phục vụ lab, không cần với broker từ xa.
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

Nếu dự án production đang dùng Spring Boot khác, hãy dùng dependency BOM và nhánh hỗ trợ phù hợp; không ghép ngẫu nhiên phiên bản Spring Framework/Jackson/Artemis. Spring Boot 3.5.16 được chọn để demo tái lập, **không phải mặc định cập nhật bảo mật cho mọi dự án tương lai**.

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.orders
      persistent: false
~~~

### 8.2. Java 17: đầy đủ một file

`src/main/java/example/jms/ErrorBoundaryApplication.java`:

~~~java
package example.jms;

import java.util.Map;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConversionException;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@SpringBootApplication
public class ErrorBoundaryApplication {
    private static final String QUEUE = "demo.orders";
    private static final String TYPE_ID = "order.created.v1";

    // Record của Java 17; Jackson nhận biết component orderId/quantity.
    public record OrderCreated(String orderId, int quantity) {}

    static final class InvalidQuantity extends RuntimeException {
        InvalidQuantity() {
            super("quantity must be positive");
        }
    }

    public static void main(String[] args) {
        SpringApplication.run(ErrorBoundaryApplication.class, args);
    }

    @Bean
    MessageConverter jmsMessageConverter() {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(Map.of(TYPE_ID, OrderCreated.class));
        converter.setTrustedPackages("example.jms");
        return converter;
    }

    @Bean
    JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            MessageConverter jmsMessageConverter) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(jmsMessageConverter);
        template.setReceiveTimeout(3_000L);
        return template;
    }

    @Bean
    ApplicationRunner runCases(
            JmsTemplate template, MessageConverter converter) {
        return args -> {
            // 1. JSON được converter tạo đúng + nghiệp vụ hợp lệ.
            template.convertAndSend(QUEUE,
                    new OrderCreated("O-100", 2),
                    message -> {
                        message.setJMSCorrelationID("case-1");
                        return message;
                    });
            classifyOnce(template, converter);

            // 2. Gửi TextMessage JSON sai cú pháp bằng MessageCreator.
            // send(...) không gọi converter.toMessage(...) cho body này.
            template.send(QUEUE, session -> {
                TextMessage raw =
                        session.createTextMessage("{invalid-json");
                raw.setStringProperty("_type", TYPE_ID);
                raw.setJMSCorrelationID("case-2");
                return raw;
            });
            classifyOnce(template, converter);

            // 3. JSON hợp lệ (quantity=0), nhưng vi phạm business rule.
            template.convertAndSend(QUEUE,
                    new OrderCreated("O-102", 0),
                    message -> {
                        message.setJMSCorrelationID("case-3");
                        return message;
                    });
            classifyOnce(template, converter);
        };
    }

    private static void classifyOnce(
            JmsTemplate template, MessageConverter converter)
            throws JMSException {
        Message raw = template.receive(QUEUE);
        if (raw == null) {
            throw new IllegalStateException("receive timed out");
        }

        String correlationId = raw.getJMSCorrelationID();

        try {
            Object payload = converter.fromMessage(raw);
            if (!(payload instanceof OrderCreated order)) {
                throw new IllegalStateException(
                        "unexpected payload type");
            }

            applyBusinessRule(order);
            System.out.println(
                    "ACCEPTED|" + correlationId + "|" + order.orderId());

        } catch (MessageConversionException ex) {
            System.out.println("CONVERSION_ERROR|" + correlationId);

        } catch (InvalidQuantity ex) {
            System.out.println(
                    "BUSINESS_ERROR|" + correlationId
                    + "|" + ex.getMessage());
        }
    }

    private static void applyBusinessRule(OrderCreated event) {
        if (event.quantity() <= 0) {
            throw new InvalidQuantity();
        }
    }
}
~~~

**Tại sao kết quả khác nhau?**
- `case-1`: `convertAndSend` dùng Jackson tạo JSON và type id đúng. `fromMessage` tạo `OrderCreated`; method `applyBusinessRule` chấp nhận quantity=2.
- `case-2`: raw `TextMessage` được gửi trực tiếp, có `_type=order.created.v1` nhưng body `{invalid-json`. Jackson đọc type id hợp lệ, sau đó không parse được JSON và ném JMS `MessageConversionException`. **`applyBusinessRule` không chạy.**
- `case-3`: body JSON valid và type id đúng; chuyển đổi thành record thành công. `applyBusinessRule` kiểm tra quantity=0, ném `InvalidQuantity`. **Đây là business error, không phải conversion error.**

### 8.3. Chạy

Từ thư mục dự án, dùng JDK 17+ và Gradle tương thích. Nếu đã có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Nếu chưa có Wrapper, có thể dùng Gradle đã cài:

~~~bash
gradle bootRun
~~~

Trên Windows PowerShell, với Wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

Sau log của Spring Boot và Artemis, mã demo in đúng ba dòng (theo thứ tự gọi send/receive trong Runner):

~~~text
ACCEPTED|case-1|O-100
CONVERSION_ERROR|case-2
BUSINESS_ERROR|case-3|quantity must be positive
~~~

Các dòng log khởi động, tên thread và timestamp của Spring/Artemis phụ thuộc môi trường, không thuộc phần output cố định. Demo chủ ý **không** tái sử dụng message bị lỗi và không khai báo `@JmsListener` cạnh tranh, vì vậy phép đo chỉ quan sát bước decode và business rule, không đánh giá redelivery/retry. `persistent: false` chỉ dùng trong lab, không chứng minh durability.

### 8.4. Điểm cần nhớ khi chuyển từ demo sang hệ thống thật

Trong demo, `JmsTemplate.receive` lấy message raw rồi tự gọi `converter.fromMessage`. Với `receiveAndConvert`, template sẽ thực hiện việc chuyển đổi bên trong method. Cả hai không thay cho listener container có chính sách transaction/ACK và DLQ.

Không copy cách `catch (MessageConversionException)` rồi chỉ in log trong demo làm chính sách consumer production. Trong hệ thống thật, nếu message đã được ACK mà không có record/quarantine, bạn có thể mất chứng cứ lỗi và không thể chạy lại sau khi sửa producer.

## 9. @JmsListener: converter có thể lỗi trước khi gọi method

Ví dụ listener nhận record:

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {
    private final OrderService service;

    public OrderListener(OrderService service) {
        this.service = service;
    }

    @JmsListener(destination = "orders.incoming")
    public void onOrder(OrderCreated event) {
        service.handle(event);
    }
}
~~~

Đoạn này là **mảnh minh họa**: `OrderCreated` và `OrderService` là các type do ứng dụng cung cấp, và cần listener factory/converter phù hợp. Với message JSON sai hoặc không resolve được type id, converter/adapter có thể ném lỗi **trước `onOrder(...)`**; logging đặt ở đầu method sẽ không ghi được trường hợp đó.

Ngược lại, nếu `onOrder(...)` đã chạy rồi `service.handle(event)` ném `OrderRejectedException`, lỗi nằm trong đường nghiệp vụ. Một method handler trả kết quả rồi bước **reply conversion** thất bại cũng có thể tạo lỗi conversion **sau** khi business logic đã thực thi — khi đó side effect có thể đã xảy ra, cần đặc biệt chú ý transaction/idempotency.

### Cấu hình listener container minh họa

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory,
        MessageConverter jmsMessageConverter) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(jmsMessageConverter);

    // Một invocation và phần nhận message cùng transaction JMS local.
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-3");
    return factory;
}
~~~

Mảnh bean này cần import `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Bean`, `org.springframework.jms.config.DefaultJmsListenerContainerFactory` và `org.springframework.jms.support.converter.MessageConverter` trong lớp `@Configuration` có `@EnableJms` khi dùng Spring Framework thuần. Với Boot, kiểm tra auto-configuration và lựa chọn factory trước khi khai báo lại. Đặt tên bean đúng `jmsListenerContainerFactory` nếu `@JmsListener` không chỉ định factory.

**Quan trọng:** `setSessionTransacted(true)` giúp message receipt được rollback nếu việc xử lý listener thất bại trong phạm vi local JMS transaction (khi dùng container phù hợp). Nhưng retry count, redelivery delay, DLQ và thời điểm chấm dứt retry là **policy broker/container** cần kiểm tra. Không có đoạn cấu hình nào ở trên tự giới hạn “tối đa ba lần rồi DLQ”.

### ErrorHandler không phải nút “ACK message”

Bạn có thể cấu hình `ErrorHandler` cho listener container để logging/metrics các exception thoát ra; tuy nhiên không nên suy ra rằng chỉ cần thêm `ErrorHandler` sẽ tự phân loại poison message, ACK, rollback hoặc route DLQ. Phạm vi transaction, nơi exception bị bắt/ném lại và chính sách broker quyết định kết quả. Cần integration test với JMS provider cụ thể.

## 10. Những cách bắt exception thường làm sai

### Sai 1: Catch quá rộng và nuốt lỗi

~~~java
@JmsListener(destination = "orders.incoming")
public void onOrder(OrderCreated event) {
    try {
        service.handle(event);
    } catch (Exception ex) {
        log.error("failed to process order", ex);
        // Không ném lại: container có thể xem invocation thành công.
    }
}
~~~

Trong đoạn trên, `service` và `log` là thành phần ứng dụng; đây chỉ là mảnh minh họa. Với session transacted, nếu handler **nuốt exception** và trả về bình thường, container có thể commit/ACK message, khiến một lỗi transient không được retry. Đồng thời đoạn `catch` không xử lý được những lỗi xảy ra ở converter **trước khi method chạy**.

**Sửa:** xử lý rõ exception nào là kết quả nghiệp vụ cuối cùng (có audit/outcome) và exception nào phải tiếp tục fail để container rollback. Không coi mọi exception là thành công, cũng không retry vô hạn lỗi input vĩnh viễn.

### Sai 2: Bắt mọi conversion error rồi gửi DLQ mới bằng tay

Nếu chưa thiết lập transaction/outbox, cách “catch rồi publish đến queue mới rồi ACK queue cũ” có thể mất dữ liệu ở khoảng giữa hai thao tác. Ngoài ra chính policy broker đã có DLQ/redelivery; gửi thêm bằng tay có thể tạo bản sao trùng hoặc loop.

**Sửa:** dùng cơ chế dead-letter/parking phù hợp broker, hoặc bảo đảm thao tác chuyển có transaction phù hợp, kèm event ID, số lần thử, reason code và replay có kiểm soát.

### Sai 3: Catch JsonProcessingException ở business rồi gắn nhãn business

~~~java
public void onOrder(String json) throws Exception {
    OrderCreated event = objectMapper.readValue(
            json, OrderCreated.class);
    service.handle(event);
}
~~~

Ví dụ này parse JSON **trong handler**, vì đã chọn tham số `String`. Root cause của `readValue` thất bại là **data conversion/input**, dù stack trace phát sinh trong method. Có thể refactor bằng một converter JMS rõ ràng, hoặc phân tách hàm `parse` trước hàm `handleDomain`. Mảnh code này giả định có `objectMapper`, `OrderCreated` và `service` trong ứng dụng.

### Sai 4: Gọi @Valid là lỗi Jackson

JSON có thể deserialize thành object bình thường rồi validation mới thất bại. Phân biệt loại lỗi và thời điểm thất bại; dùng mã lỗi `SCHEMA_INVALID` hoặc `ARGUMENT_VALIDATION_FAILED` khi phù hợp thay vì luôn ghi `JSON_PARSE_ERROR`.

### Sai 5: Coi IOException, JMSException hoặc timeout là business rejection

Lỗi kết nối/broker/DB timeout có thể tạm thời và retry có ích. Đừng gán nguyên nhân từ bối cảnh gọi là “OrderService” mà chưa xem exception chain, trạng thái transaction và telemetry.

## 11. Chính sách retry / rollback / DLQ theo loại lỗi

Không có chính sách mặc định đúng cho mọi hệ thống, nhưng bảng sau là điểm bắt đầu thực dụng:

| Loại kết quả | Retry? | ACK / rollback / parking gợi ý |
|---|---|---|
| JSON sai cú pháp, thiếu type id không thể xử lý | **Không retry vô hạn cùng message**. | Park/DLQ với mã `CONVERSION_ERROR` và metadata đủ chẩn đoán; kiểm tra quyền truy cập, tránh log payload nhạy cảm. |
| Schema không tương thích sau deployment | Có thể **khôi phục bằng code/schema migration**. | Park/dead-letter có quản lý rồi replay khi converter đã sửa; giữ message ID/business ID. |
| Input validation vĩnh viễn | Thường không retry cùng dữ liệu. | Ghi kết quả từ chối/audit; ACK hoặc parking theo contract. |
| Business rule cuối cùng | Không retry nếu không thể thay đổi; có thể gửi rejection event. | Ghi kết quả một lần, ACK sau khi đã hoàn tất hành vi từ chối. |
| Business dependency chưa sẵn sàng | Retry có điều kiện nếu kỳ vọng tự phục hồi. | Backoff/jitter, max attempts, DLQ khi vượt ngưỡng. |
| DB/HTTP/broker timeout | Thường retry có giới hạn. | Rollback trong transaction phù hợp; idempotency trước tác dụng phụ. |
| Lỗi code sau triển khai | Retry liên tục ít khi có ích cho đến khi sửa bản chạy. | Alert, giới hạn attempt, park message, replay sau deploy. |

### Tại sao không nên để mọi exception tự rollback mãi?

Với một message hỏng vĩnh viễn, nếu container rollback rồi broker redeliver vô hạn, consumer có thể làm CPU tăng, spam log và bỏ đói message hợp lệ. Với một lỗi business không thể thay đổi, việc retry liên tục cũng không tạo ra thành công.

Chính sách poison message thực tế cần:
- Có **max delivery attempts** và redelivery delay/backoff.
- Có DLQ/parking riêng, quyền truy cập phù hợp và thao tác replay có kiểm soát.
- Ghi reason taxonomy và version schema/converter.
- Đo tỷ lệ conversion failures và số message bị kẹt theo Queue/producer.
- Không dùng “ACK rồi bỏ qua” trừ khi contract ghi rõ đây là một kết quả cuối cùng và có audit cần thiết.

### Lưu ý về ACK/transaction

- Với listener sử dụng JMS transaction local, exception thoát khỏi invocation thường khiến transaction rollback, cho phép broker áp dụng redelivery policy.
- Với AUTO_ACKNOWLEDGE không có transaction, message có thể đã được ACK **trước hoặc trong** quá trình callback tùy container/kiểu nhận; không mặc định rằng ném exception sẽ luôn redeliver.
- Với `JmsTemplate.receive` rồi tự xử lý, ACK có thể đã xảy ra trước converter, như demo.
- Database transaction và JMS transaction không tự động là một; commit DB thành công rồi rollback JMS có thể dẫn đến duplicate side effect. Dùng idempotency, outbox/inbox hoặc XA/JTA khi thật sự có yêu cầu và hạ tầng hỗ trợ.

**Không có gì ở đây hứa hẹn exactly-once end-to-end.** Bảo đảm xử lý một lần ở nghiệp vụ thường phải dựa trên key duy nhất, transaction persistence và deduplication.

## 12. Quan sát: ghi đúng nguyên nhân nhưng không lộ dữ liệu

Một hệ thống có hàng chục Queue nên thống nhất thông tin trong log/metric cho mọi lỗi:

| Trường | Mục đích |
|---|---|
| `JMSMessageID` / event ID | Đối chiếu broker, producer và consumer; không giả định JMSMessageID là khóa idempotency nghiệp vụ. |
| `JMSCorrelationID` | Ghép các request/reply, trace giao dịch hoặc quy trình. |
| Destination / subscriber / consumer group | Biết Queue/Topic và component chịu trách nhiệm. |
| Schema name/version và type id | Xác định hợp đồng dữ liệu nào thất bại. |
| `errorStage` | `PRODUCER_CONVERSION`, `CONSUMER_CONVERSION`, `ARGUMENT_VALIDATION`, `BUSINESS_RULE`, `INFRASTRUCTURE` hoặc `ACK_COMMIT`. |
| `errorCode` / exception cause | Mã ổn định để alert và định tuyến, ví dụ `INVALID_JSON`, `UNKNOWN_TYPE_ID`, `ORDER_REJECTED`, `DB_TIMEOUT`. |
| Delivery count | Đọc `JMSXDeliveryCount` nếu provider cung cấp và thuộc tính tồn tại; xác minh semantics theo broker. |
| Outcome và retry policy | `REJECTED`, `RETRYING`, `PARKED`, `COMPLETED`; backoff/max attempts. |

Không log toàn bộ JSON chứa dữ liệu cá nhân, token, thông tin thanh toán hoặc stack trace nhạy cảm vào hệ thống không có quyền. Để debug converter có thể lưu **payload đã được kiểm soát/redact/encrypt** ở vùng quarantine ngắn hạn, kèm retention và audit. Không in raw body không giới hạn từ producer không tin cậy.

### Phân biệt theo stack trace

Ví dụ hai chuỗi nguyên nhân (minh họa cấu trúc, không phải output nguyên văn của một vendor):

~~~text
ListenerExecutionFailedException
  caused by MessageConversionException (Spring JMS)
    caused by JsonParseException
→ CONSUMER_CONVERSION: handler chưa chạy
~~~

~~~text
ListenerExecutionFailedException
  caused by InvalidOrderQuantityException
→ BUSINESS_RULE: handler đã được invoke
~~~

Đọc `getCause()` nhiều tầng, kết hợp marker “đã vào handler hay chưa”; không gắn taxonomy bằng việc tìm một substring trong message lỗi. Cẩn thận exception khác có thể bọc `MessageConversionException`, hoặc parse JSON do business handler tự làm.

## 13. Kiểm thử cả producer lẫn consumer

Một bộ test tối thiểu nên có:

| Test | Input/tác động | Mong đợi |
|---|---|---|
| **Valid happy path** | JSON hợp lệ và domain chấp nhận. | Convert thành công, service thực thi một lần theo test, ACK/commit. |
| **Outbound conversion** | Producer serialize object không được hỗ trợ. | Không coi là business rejection; kiểm tra có/bỏ broker publish theo ranh giới lỗi. |
| **Malformed JSON** | TextMessage sai cú pháp với type id hợp lệ. | Báo conversion stage; business handler không chạy. |
| **Missing type id** | JSON đúng nhưng không có `_type`. | Converter báo không resolve được target type (với converter cấu hình như ví dụ). |
| **Wrong type / schema** | Type ID không được hỗ trợ hoặc field sai kiểu. | Phân loại contract/schema, không tự động gọi domain. |
| **Input validation** | JSON hợp lệ nhưng vi phạm `@Valid`. | Xác nhận có object, nhưng method chưa chạy; reason riêng. |
| **Business permanent** | Quantity=0 hoặc order status không cho phép. | Service đã chạy; reject theo contract, không infinite retry. |
| **Business transient** | DB timeout có thể phục hồi. | Rollback/redelivery có giới hạn; side effect không nhân đôi. |
| **Listener transaction** | Có `sessionTransacted=true` và throw từ handler. | Test rollback, redelivery, DLQ thực của broker. |
| **Reply conversion** | Handler chạy xong nhưng response object không serialize được. | Đánh dấu lỗi sau business, bảo vệ idempotency/reply semantics. |
| **Recovery/migration** | Deploy converter mới nhận schema cũ. | Replay có kiểm soát, message lỗi không bị mất trước khi sửa. |

**Điểm quan trọng:** không chỉ unit test hàm Java. Cần integration test với **chính JMS provider/driver, acknowledgement mode và listener factory** mà production sử dụng. Một log “conversion failed” trong lab không cho biết message có được redeliver trong production hay không.

### Unit test không cần broker

Có thể test `MessageConverter` trực tiếp bằng message mock/stub (hoặc một embedded provider được cô lập); cũng có thể tách hàm domain ra một pure Java service để test quantity/state transition mà không cần JMS. Tuy nhiên khi xác minh ACK, transaction, DLQ hoặc retry, chỉ unit test converter là **không đủ**.

## 14. Checklist thiết kế trước khi merge code

- [ ] Đã chỉ rõ ranh giới outbound conversion, broker transport, inbound conversion, validation, business và commit/ACK.
- [ ] Đã chọn một hợp đồng payload (TextMessage JSON, BytesMessage hoặc kiểu khác) với schema/version/type id minh bạch.
- [ ] `JmsTemplate` và listener factory dùng converter tương thích; kiểm tra dữ liệu thực từ producer khác.
- [ ] Không deserialize arbitrary class từ untrusted type id; đã nâng bản Spring có bản vá và allowlist type/package.
- [ ] Business handler không parse lại JSON tùy tiện mà không phân loại nguyên nhân dữ liệu.
- [ ] Có ngoại lệ nghiệp vụ có ý nghĩa, phân biệt rejection permanent với lỗi transient.
- [ ] Có luật retry/backoff/max attempts, DLQ/parking và chiến lược replay.
- [ ] Consumer có transaction/ACK semantics đã được test; không nuốt exception ngoài chủ đích.
- [ ] Có idempotent business operation khi redelivery sau timeout/rollback.
- [ ] Có observability theo errorStage, message ID, schema version, delivery attempts; không log secrets.
- [ ] Đã test malformed payload, thiếu type id, validation failure, business rejection và lỗi DB/network.
- [ ] Không coi `STATUS=sent`/HTTP 202 hay logger thành công là bằng chứng business handler hoàn thành.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Consumer nhận `TextMessage` có body `{bad-json`, converter Jackson ném `MessageConversionException` trước khi `@JmsListener` được gọi. Lỗi thuộc nhóm nào?

**Đáp án:** Inbound conversion error. Domain method chưa chạy; retry vô hạn cùng byte payload thường vô ích. Điều tra producer/schema, park/DLQ và replay sau sửa lỗi.

**Câu 2.** JSON `{"orderId":"O-30","quantity":0}` được deserialize thành `OrderCreated`, sau đó `OrderService` ném `InvalidOrderQuantityException`. Có phải lỗi converter không?

**Đáp án:** Không. Converter đã hoàn tất; business rule từ chối dữ liệu. Nếu quantity tối thiểu phải dương theo contract, có thể chuyển ràng buộc sang validation trước handler nhưng phải ghi rõ tầng phát hiện.

**Câu 3.** Handler `@JmsListener(String rawJson)` tự gọi Jackson và nhận `JsonParseException`. Có nên ghi `BUSINESS_RULE_ERROR` chỉ vì lỗi xuất hiện trong handler?

**Đáp án:** Không. Nguyên nhân thực chất là data conversion/input. Phân loại theo bước parse, có thể refactor dùng `MessageConverter` trước domain service.

**Câu 4.** Một service có thể bắt `org.springframework.messaging.converter.MessageConversionException` và `org.springframework.jms.support.converter.MessageConversionException` như một class không?

**Đáp án:** Không. Hai kiểu có package và hierarchy khác nhau; cần phân loại chính xác bằng fully qualified name hoặc cause chain và không nhập nhằng ở import.

**Câu 5.** Vì sao `sessionTransacted=true` không tự bảo đảm message hỏng được đưa vào DLQ sau đúng ba lần?

**Đáp án:** Nó quyết định transaction/rollback trong listener. Số lần redelivery, delay và DLQ phụ thuộc cấu hình broker/provider và policy bổ sung.

**Câu 6.** Lỗi DB timeout xảy ra sau khi converter thành công và trước khi business xử lý xong. Có nên coi là “business rejection vĩnh viễn” không?

**Đáp án:** Không. Đây là lỗi hạ tầng tạm thời xảy ra trên đường xử lý nghiệp vụ; cân nhắc retry giới hạn, backoff, idempotency và alert.

**Câu 7.** Đã catch conversion exception khi dùng `JmsTemplate.receive()` trong AUTO_ACKNOWLEDGE và in log. Liệu message có tự quay lại Queue không?

**Đáp án:** Không thể giả định. Receive có thể đã ACK trước bước converter; phải test semantics thực, dùng listener transaction phù hợp và chính sách quarantine thay vì kỳ vọng catch sẽ rollback.

## 16. Tài liệu chính thức

- [Spring Framework 6.2 — Using JMS và MessageConverter](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html).
- [Spring Framework 6.2 — Receiving a Message, listener transaction và ACK](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html).
- [Spring Framework 6.2 — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html).
- [Spring Framework 6.2.19 — JMS MessageConverter interface](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html).
- [Spring Framework 6.2.19 — JMS MessageConversionException](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MessageConversionException.html).
- [Spring Framework 6.2.19 — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html).
- [Spring Framework 6.2.19 — Spring Messaging MessageConversionException](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/converter/MessageConversionException.html).
- [Spring Boot — Messaging with JMS: Artemis, JSON converter và listener](https://spring.io/guides/gs/messaging-jms/).
- [Spring Boot 3.5.16 — Managed dependency coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html).
- [Spring Security Advisory CVE-2026-41855 — Jackson JMS deserialization](https://spring.io/security/cve-2026-41855/).
- [Jakarta Messaging 3.1 specification — JMS Message and semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
