# MessagePostProcessor cho dữ liệu trước khi gửi

> **Chủ đề:** `JmsTemplate` trong Spring Framework JMS. `MessagePostProcessor` là điểm can thiệp **sau khi `MessageConverter` chuyển đổi dữ liệu Java thành JMS `Message`, nhưng trước khi `MessageProducer` gửi message tới broker**. Cơ chế này đặc biệt hữu ích để bổ sung correlation ID, loại sự kiện, phiên bản schema và các JMS properties theo từng lần gửi.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Mô tả chính xác thứ tự `convertAndSend → MessageConverter → MessagePostProcessor → send` và thời điểm có thể chỉnh sửa JMS message.
2. Sử dụng overload `JmsTemplate.convertAndSend(destination, payload, postProcessor)` để thêm header/property, đồng thời giữ nguyên payload do converter tạo.
3. Phân biệt **JMS headers**, **message properties** và **body**, đặc biệt những header do JMS provider quản lý khi gửi.
4. Viết một chương trình Java 17 / Spring Boot 3.3 / ActiveMQ Artemis chạy được, gửi một `TextMessage`, nhận lại đúng message theo selector, kiểm tra header và properties.
5. Thiết kế post-processor có thể tái sử dụng mà không làm mất thông tin theo từng request, không tạo side effect trùng khi retry và không vô tình thay đổi cấu hình QoS của template dùng chung.
6. Chẩn đoán khi callback không chạy, body không đúng kiểu, header bị provider ghi đè hoặc message không được consumer chọn.

Đây là một **cơ chế chỉnh sửa message ngay trước send**. Nó không phải một consumer, một filter chạy sau khi broker tiếp nhận hay một thành phần xử lý message khi đã được gửi thành công.

## 2. MessagePostProcessor nằm ở đâu trong luồng gửi?

Với Spring Framework 6.x, `JmsTemplate` có thể gửi dữ liệu theo hai cách phổ biến:

- `send(destination, MessageCreator)`: mã ứng dụng tự tạo `jakarta.jms.Message` với `Session`.
- `convertAndSend(destination, object)`: một `MessageConverter` chuyển Java object thành JMS `Message`; template gửi nó đi.

Để **can thiệp sau khi chuyển đổi**, dùng overload nhận thêm `org.springframework.jms.core.MessagePostProcessor`.

~~~text
Ứng dụng gọi:
    jmsTemplate.convertAndSend("orders.events", payload, processor)
                           |
                           v
            MessageConverter.toMessage(...)
                           |
                           v
              jakarta.jms.Message
                           |
                           v
       MessagePostProcessor.postProcessMessage(...)
       - setJMSCorrelationID(...)
       - setStringProperty(...)
       - setIntProperty(...)
       - trả về Message (không được null)
                           |
                           v
           JMS MessageProducer.send(...)
                           |
                           v
                      JMS broker
                           |
                           v
                     JMS consumer
~~~

**Chốt thứ tự:** callback nhận **JMS message đã được tạo bởi converter**. Ở đây bạn có thể thêm metadata phụ thuộc request, nhưng không cần tự tạo body `TextMessage`/`BytesMessage` nếu converter đã làm đúng việc đó.

Ví dụ một ứng dụng gửi chuỗi `"order-created"`. Mặc định, `SimpleMessageConverter` của Spring chuyển `String` thành JMS `TextMessage`. `MessagePostProcessor` có thể bổ sung:

~~~text
Body: TextMessage("order-created")
Header: JMSCorrelationID = "trace-abc-001"
Properties:
    eventType     = "order.created" (String)
    schemaVersion = 1               (int)
    sourceService = "order-service" (String)
~~~

Body vẫn giữ nguyên. Consumer có thể đọc metadata để định tuyến, ghi log có liên kết hoặc kiểm tra schema version trước khi xử lý.

## 3. API cốt lõi: một functional interface

Trong Spring Framework 6.x:

~~~java
package org.springframework.jms.core;

import jakarta.jms.JMSException;
import jakarta.jms.Message;

@FunctionalInterface
public interface MessagePostProcessor {
    Message postProcessMessage(Message message) throws JMSException;
}
~~~

Đây là cách viết lại chữ ký API để học, **không phải file cần tạo trong project** (interface thực tế đã có trong dependency Spring JMS).

- **Đầu vào:** một `jakarta.jms.Message`, thường do `MessageConverter` vừa tạo.
- **Đầu ra:** chính message đã chỉnh sửa, hoặc một message thay thế hợp lệ; **không trả `null`**.
- **Exception:** phương thức cho phép `JMSException` khi thao tác JMS API thất bại. `JmsTemplate` chuyển các JMS checked exceptions phù hợp thành Spring `JmsException` runtime.
- **Cách triển khai:** dùng lambda hoặc class triển khai interface vì chỉ có một abstract method.

Cách ngắn gọn:

~~~java
// Snippet: jmsTemplate là bean Spring đã cấu hình.
jmsTemplate.convertAndSend("orders.events", "order-created", message -> {
    message.setJMSCorrelationID("trace-abc-001");
    message.setStringProperty("eventType", "order.created");
    message.setIntProperty("schemaVersion", 1);
    return message;
});
~~~

Không cần khởi tạo `MessagePostProcessor` trước nếu logic chỉ dùng một lần. Với logic dùng chung, có thể tạo một đối tượng processor có tham số hoặc một phương thức trả về lambda.

Lưu ý: ví dụ trên dùng **`org.springframework.jms.core.MessagePostProcessor`**, hoạt động trên `jakarta.jms.Message`. Spring còn có interface **`org.springframework.messaging.core.MessagePostProcessor`** hoạt động trên `org.springframework.messaging.Message<?>` trong các API messaging khác. Hai interface khác package và kiểu message; không chọn nhầm import khi biên dịch.

## 4. Header, property và body: chỉnh ở lớp nào?

| Thành phần | Ví dụ | Cách đặt hợp lý | Điểm cần nhớ |
| --- | --- | --- | --- |
| Body (payload) | JSON/chuỗi `"order-created"` | `MessageConverter` | Converter chịu trách nhiệm biểu diễn dữ liệu, encoding và content type |
| JMS header do ứng dụng có thể đặt | `JMSCorrelationID`, `JMSType`, `JMSReplyTo` | `MessagePostProcessor` khi đã có `Message` hợp lệ | Dùng đúng API setter/getter của `jakarta.jms.Message` |
| Custom application property | `eventType`, `schemaVersion`, `sourceService`, `runId` | `setStringProperty`/`setIntProperty`/... trong processor | Type của property có ý nghĩa khi consumer đọc hoặc dùng selector |
| Provider-managed header | `JMSMessageID`, `JMSTimestamp`, `JMSDestination` | JMS provider đặt trong quá trình gửi | Đừng tự tạo/ghi đè rồi kỳ vọng giữ nguyên |
| QoS khi gửi | delivery mode, priority, time-to-live | `MessageProducer` hoặc cấu hình `JmsTemplate` với explicit QoS | Không đặt bằng cách sửa các header đã hoặc sẽ do provider ghi |

Ví dụ phân biệt header với property:

~~~java
message.setJMSCorrelationID("req-001");             // JMS header
message.setStringProperty("eventType", "created");   // Custom String property
message.setIntProperty("schemaVersion", 2);         // Custom int property
~~~

Consumer đọc tương ứng:

~~~java
String correlationId = message.getJMSCorrelationID();
String eventType = message.getStringProperty("eventType");
int schemaVersion = message.getIntProperty("schemaVersion");
~~~

**Không** dùng `setStringProperty("JMSCorrelationID", "...")` thay cho `setJMSCorrelationID(...)`; cái đầu chỉ là property có tên giống header và không bảo đảm thay đổi trường JMS thật.

### 4.1. Correlation ID và trace ID

`JMSCorrelationID` được ứng dụng thường dùng để liên kết request–reply hoặc các bước trong cùng một luồng nghiệp vụ. Giá trị thường do service phát message chọn, chẳng hạn command ID hoặc correlation ID đã được tạo ở API ingress.

Nếu có trace phân tán (OpenTelemetry), đừng mặc định coi `JMSCorrelationID` đồng nghĩa với `traceparent`; mỗi hệ thống có thể dùng convention khác nhau. Có thể giữ correlation ID làm header, còn `traceparent`/`tracestate` dưới các properties riêng theo chuẩn instrumentation đang sử dụng. **Không sinh ID mới tùy tiện trong mỗi lần retry** nếu cần nhận diện cùng một thao tác logic.

### 4.2. Properties và selector

JMS có property kiểu primitive và String: `setStringProperty`, `setIntProperty`, `setBooleanProperty`, ... Khi gửi property:

~~~java
message.setStringProperty("eventType", "order.created");
message.setIntProperty("schemaVersion", 1);
~~~

Consumer có thể tạo JMS selector tương ứng:

~~~text
eventType = 'order.created' AND schemaVersion = 1
~~~

Selector chỉ kiểm tra **header/property**, không phân tích body JSON. Tên property phải tuân theo quy tắc định danh của JMS selector; tránh namespace dành riêng do chuẩn/broker quy định. Những chuỗi metadata do client gửi cần được validate; không ghép tùy ý input chưa kiểm soát vào selector.

### 4.3. Có thể thay body trong processor không?

JMS `TextMessage` là mutable trong giai đoạn tạo; về mặt API bạn có thể cast đúng kiểu và gọi `setText(...)` trước send. Tuy nhiên, nếu mục tiêu là chuyển DTO thành JSON, thay tên trường, kiểm tra encoding hoặc quản lý schema, nên đặt việc đó trong **`MessageConverter`/serializer**, nơi trách nhiệm rõ ràng và dễ unit test. Processor phù hợp hơn với metadata phát sinh **sau khi payload đã được chuyển đổi**. Đừng cast mọi `Message` thành `TextMessage` vì converter có thể tạo `BytesMessage`, `MapMessage` hoặc `ObjectMessage`.

## 5. Các overload dùng MessagePostProcessor

Những cách gọi điển hình của `JmsTemplate`:

~~~java
// Snippet: jmsTemplate đã được inject; processor là MessagePostProcessor.
jmsTemplate.convertAndSend("orders.events", payload, processor);

// Có defaultDestination đã cấu hình:
jmsTemplate.convertAndSend(payload, processor);

// Có jakarta.jms.Destination đã được cung cấp:
jmsTemplate.convertAndSend(destination, payload, processor);
~~~

`convertAndSend` sẽ chuyển đổi object sang JMS `Message`, gọi post-processor, rồi gửi. Việc gọi `jmsTemplate.send(destination, session -> ...)` là API của **`MessageCreator`**: lambda tại đó nhận `Session` để tạo message, nên không nhầm với callback `MessagePostProcessor` nhận `Message` đã chuyển đổi.

| Tình huống | API nên dùng | Vì sao |
| --- | --- | --- |
| Gửi một `String`/`byte[]`/`Map` với converter hiện tại | `convertAndSend` | Không phải tự tạo JMS message |
| Thêm correlation ID/property riêng cho mỗi request | `convertAndSend(..., MessagePostProcessor)` | Can thiệp đúng sau chuyển đổi và trước send |
| Tự tạo `BytesMessage` hoặc message đặc biệt từ `Session` | `send(..., MessageCreator)` | Có toàn quyền truy cập `Session` tạo message |
| Chuyển DTO thành JSON/Text/Bytes theo schema | `MessageConverter` | Tách serialization khỏi metadata |
| Điều chỉnh delivery mode/priority/TTL chung cho template | `JmsTemplate` + `explicitQosEnabled` | QoS do producer/provider áp dụng khi send |
| Biến đổi kết quả ở consumer | Listener/converter phía nhận | Post-processor của producer không được gọi khi nhận |

Đừng mong callback của `convertAndSend` tự chạy cho mọi đường gửi qua template. **Nó chỉ được áp dụng cho các lời gọi chuyển vào đúng overload nhận processor**, không phải một interceptor toàn cục được gắn tự động vào mọi lần `send`.

## 6. Ví dụ đầy đủ: Spring Boot 3.3 + ActiveMQ Artemis + Java 17

Ta sẽ gửi một `TextMessage` bằng `JmsTemplate.convertAndSend`, đặt metadata trong lambda, rồi dùng `JmsTemplate.receiveSelected` để **đọc đúng message do lần chạy này gửi**. Thí nghiệm giúp quan sát nội dung trước khi gửi và kiểm tra broker giữ metadata khi nhận.

### 6.1. Chuẩn bị broker

Cần một **ActiveMQ Artemis broker** chạy ở `tcp://localhost:61616`, tài khoản `artemis/artemis` cho **môi trường demo cục bộ cách ly**, và queue `demo.postprocess`. Hãy tạo queue kiểu anycast/point-to-point trước khi chạy; nếu broker demo cho phép tự động tạo queue thì có thể dùng cơ chế đó, nhưng với broker thật phải tuân theo quyền tạo destination.

Ví dụ nếu đã có Docker và muốn thử ở máy riêng, image chính thức có thể được chạy như sau:

~~~bash
docker run --detach --rm --name artemis-postprocess-demo -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

Kiểm tra log trước khi chạy Java:

~~~bash
docker logs artemis-postprocess-demo
~~~

Nếu broker đã tồn tại ở cùng port, **không** khởi chạy thêm container dùng chung port. Khi kết thúc, dùng `docker stop artemis-postprocess-demo` để dọn môi trường thử. Lệnh demo không cấu hình persistence qua volume; không coi đó là cách triển khai production.

### 6.2. Cấu trúc project

~~~text
jms-message-postprocessor/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/PostProcessorApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-message-postprocessor'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "artemis"
    password: "artemis"
~~~

`spring.artemis.mode: native` bảo đảm dự án nhắm đến Artemis bên ngoài tiến trình. Các thông tin `artemis/artemis` chỉ là mặc định của môi trường **demo local**; trong môi trường thật, sử dụng secret được quản lý và ghi đè bằng `SPRING_ARTEMIS_USER`/`SPRING_ARTEMIS_PASSWORD` hoặc cấu hình tập trung, tuyệt đối không commit mật khẩu thật.

### 6.3. Java runnable: kiểm tra payload và metadata

`src/main/java/demo/PostProcessorApplication.java`:

~~~java
package demo;

import java.util.UUID;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class PostProcessorApplication {

    private static final String QUEUE = "demo.postprocess";
    private static final String PAYLOAD = "order-created";

    public static void main(String[] args) {
        SpringApplication.run(PostProcessorApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JmsTemplate template) {
        return args -> {
            // Phân biệt đúng message thử của lượt chạy này.
            String runId = UUID.randomUUID().toString();

            // Demo chỉ chạy một luồng; đặt timeout để không chờ vô hạn.
            template.setReceiveTimeout(5_000L);

            template.convertAndSend(QUEUE, PAYLOAD, message -> {
                // Converter đã tạo JMS Message trước khi lambda chạy.
                if (!(message instanceof TextMessage)) {
                    throw new IllegalStateException(
                            "Expected TextMessage for String payload");
                }

                // JMS header để liên kết các bước của một yêu cầu.
                message.setJMSCorrelationID(runId);

                // Application properties phục vụ selector/xử lý metadata.
                message.setStringProperty("runId", runId);
                message.setStringProperty("eventType", "order.created");
                message.setIntProperty("schemaVersion", 1);

                System.out.println("POSTPROCESSOR_OK");
                return message; // Bắt buộc trả một Message khác null.
            });

            // Dòng này chỉ xuất hiện khi lời gọi gửi đã trả về bình thường.
            System.out.println("SEND_OK");

            String selector = "runId = '" + runId + "'";
            Message received = template.receiveSelected(QUEUE, selector);

            if (!(received instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "No matching TextMessage within 5000 ms");
            }
            if (!PAYLOAD.equals(text.getText())) {
                throw new IllegalStateException("Payload mismatch");
            }

            System.out.println("RECEIVE_OK body=" + text.getText());

            boolean metadataMatches =
                    runId.equals(text.getJMSCorrelationID())
                    && runId.equals(text.getStringProperty("runId"))
                    && "order.created".equals(
                            text.getStringProperty("eventType"))
                    && text.getIntProperty("schemaVersion") == 1;

            if (!metadataMatches) {
                throw new IllegalStateException("Metadata mismatch");
            }

            System.out.println("METADATA_OK");
        };
    }
}
~~~

**Ý nghĩa các bước:**

1. Spring Boot cấu hình `ConnectionFactory` và `JmsTemplate` từ starter Artemis. Không cần tự tạo `Session` hay `MessageProducer`.
2. `String PAYLOAD` được `SimpleMessageConverter` mặc định chuyển thành `TextMessage`.
3. Lambda `MessagePostProcessor` nhận message này, kiểm tra kiểu, đặt correlation ID và ba application properties. Trong ví dụ, dữ liệu đã chuyển đổi là nội dung body; callback chỉ bổ sung metadata.
4. `POSTPROCESSOR_OK` được in **bên trong callback**, vì vậy xuất hiện **trước** `SEND_OK`. Điều này chứng minh callback chạy, **chưa chứng minh broker đã nhận** khi dòng đầu tiên xuất hiện.
5. Sau khi `convertAndSend` trả về không lỗi, chương trình in `SEND_OK`. Về mặt nghiệp vụ, vẫn cần tách “producer gửi” khỏi “consumer đã xử lý”.
6. `receiveSelected` tạo consumer với selector chỉ chấp nhận `runId` của lần này. `setReceiveTimeout(5000)` giới hạn thời gian nhận.
7. `RECEIVE_OK` chỉ được in khi body đúng. `METADATA_OK` chỉ được in sau khi xác nhận correlation ID, eventType, schemaVersion và runId.
8. `ApplicationRunner` thực hiện thí nghiệm một lần rồi kết thúc; ứng dụng demo không mở HTTP server. Đây là ví dụ kiểm tra đồng bộ, không phải mô hình listener lâu dài trong production.

Tên file `PostProcessorApplication.java` khớp public class; source dùng Java 17 pattern matching `instanceof`. Vì code phụ thuộc Spring/JMS, hãy chạy qua Gradle (có classpath thích hợp), không dùng `javac PostProcessorApplication.java` đơn lẻ.

### 6.4. Chạy và đối chiếu stdout

Tại thư mục dự án đã tạo file trên, với JDK 17+ và Gradle cài sẵn:

~~~bash
gradle bootRun
~~~

Khi broker, queue và credentials hoạt động đúng, các **dòng do ứng dụng tự in** là:

~~~text
POSTPROCESSOR_OK
SEND_OK
RECEIVE_OK body=order-created
METADATA_OK
~~~

Log khởi động/đóng Spring và Artemis có thể xuất hiện xen kẽ. Giá trị `runId` là UUID ngẫu nhiên nhưng **không in ra** trong output mẫu. Selector theo runId giúp nhận đúng message mới, kể cả khi queue còn message cũ từ lần thử khác.

Nếu broker chưa kết nối, queue chưa tạo và broker không cho auto-create, quyền gửi/nhận không đủ hoặc quá thời gian chờ, chương trình ném exception; output mẫu trên chỉ áp dụng khi các điều kiện thử nghiệm được đáp ứng. Nếu `POSTPROCESSOR_OK` xuất hiện nhưng `SEND_OK` không xuất hiện, lỗi có thể nằm ở bước producer/broker **sau callback**.

Để tránh tiêu thụ message của ứng dụng khác, chỉ thực hiện trên **queue dành riêng cho demo**. Trong production không nên dùng `JmsTemplate.receiveSelected` trên queue nghiệp vụ chỉ để “xem metadata”; có thể làm thay đổi kết quả giao message và acknowledgement.

## 7. Mẫu code ứng dụng thực: metadata theo từng request

Trong ứng dụng gửi đơn hàng, correlation ID và tenant/context thường khác nhau ở từng request. Tạo một processor riêng cho mỗi lời gọi giúp giữ tính thread-safe:

~~~java
// Snippet trong Spring service; JmsTemplate được inject sẵn.
public void publishOrderEvent(
        String orderId,
        String correlationId,
        String sourceService) {

    String payload = "order-created:" + orderId;

    jmsTemplate.convertAndSend(
            "orders.events",
            payload,
            message -> {
                message.setJMSCorrelationID(correlationId);
                message.setStringProperty("eventType", "order.created");
                message.setStringProperty("sourceService", sourceService);
                message.setIntProperty("schemaVersion", 1);
                return message;
            });
}
~~~

Đây là **snippet**, không phải một class runnable độc lập. Một service thực tế phải xác thực/validate `orderId`, `correlationId`, `sourceService` trước khi phát message. Tên property và ý nghĩa của chúng là **hợp đồng giữa producer và consumer**; đổi tùy tiện có thể làm listener/selector không đọc được.

### 7.1. Tách logic post-processing dùng chung

Nếu nhiều lần gửi áp dụng cùng logic, tạo một factory trả về processor:

~~~java
// Snippet Java 17; import org.springframework.jms.core.MessagePostProcessor.
static MessagePostProcessor eventMetadata(
        String correlationId, String eventType, int version) {

    return message -> {
        message.setJMSCorrelationID(correlationId);
        message.setStringProperty("eventType", eventType);
        message.setIntProperty("schemaVersion", version);
        return message;
    };
}

// Lời gọi sử dụng:
jmsTemplate.convertAndSend(
        "orders.events",
        "order-created",
        eventMetadata("request-001", "order.created", 1));
~~~

Dùng biến local/parameter **không bị mutate** để processor ổn định trong một lượt gửi. `JmsTemplate` thường là singleton dùng được bởi nhiều request; không đặt “correlationId hiện tại” vào một field mutable của singleton rồi thay đổi giữa các thread.

### 7.2. Khi có nhiều thao tác metadata

Có thể gộp nhiều quy tắc vào **một callback** thay vì gửi hai message:

~~~java
jmsTemplate.convertAndSend("orders.events", "order-created", message -> {
    message.setJMSCorrelationID("request-001");
    message.setStringProperty("eventType", "order.created");
    message.setStringProperty("sourceService", "order-api");
    message.setIntProperty("schemaVersion", 1);
    return message;
});
~~~

Hai lần gọi `convertAndSend` là **hai lần gửi**, không phải hai giai đoạn bổ sung metadata vào cùng message. Nếu muốn chia thành các hàm xử lý nhỏ, gọi chúng tuần tự trên cùng `Message` trong lambda và chỉ return một lần.

## 8. Những header không nên đặt bằng post-processor

Một điểm dễ nhầm: do callback nhận được JMS `Message`, có vẻ ta có thể gọi mọi setter trên message. Nhưng **quyền kiểm soát cuối cùng của một số header thuộc về JMS producer/provider**.

| Header hoặc tùy chọn | Có thể đọc/chỉnh trong processor? | Cách triển khai đáng tin |
| --- | --- | --- |
| `JMSCorrelationID` | Có thể đặt trong processor | `message.setJMSCorrelationID(id)` |
| `JMSType` | Có thể đặt nếu ứng dụng dùng trường này | `message.setJMSType(type)` |
| Custom property `eventType` | Có thể đặt | `message.setStringProperty("eventType", type)` |
| `JMSReplyTo` | Có thể đặt khi đã có destination hợp lệ | `message.setJMSReplyTo(replyDestination)` |
| `JMSMessageID` | Do provider cấp khi gửi | Đọc message sau gửi/ở consumer; không tự gán để thay ID |
| `JMSTimestamp` | Do provider xác lập theo cấu hình send | Không tự chỉnh để giả thời điểm gửi |
| `JMSDestination` | Do producer/provider đặt | Chọn destination trong `convertAndSend` |
| `JMSDeliveryMode` | Producer/provider quyết định tại send | Đặt delivery mode của producer/template |
| `JMSPriority` | Producer/provider quyết định tại send | Cấu hình priority trên producer/template |
| `JMSExpiration` | Provider tính từ TTL | Đặt time-to-live thay vì tự ghi timestamp |

**Ví dụ cần tránh:**

~~~java
jmsTemplate.convertAndSend("orders.events", "order-created", message -> {
    message.setJMSPriority(9); // Không phải cách đặt QoS đáng tin.
    message.setJMSExpiration(System.currentTimeMillis() + 30_000L);
    return message;
});
~~~

Các giá trị này có thể bị provider ghi đè khi send. Nếu toàn bộ message gửi qua một template cần TTL/priority/mode cụ thể, cấu hình template khi tạo bean:

~~~java
// Snippet Spring @Configuration; không copy vào demo nếu chưa điều chỉnh bean.
@Bean
JmsTemplate shortLivedTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setExplicitQosEnabled(true);
    template.setPriority(7);
    template.setTimeToLive(30_000L);
    template.setDeliveryMode(DeliveryMode.PERSISTENT);
    return template;
}
~~~

Đoạn này cần import `jakarta.jms.ConnectionFactory`, `jakarta.jms.DeliveryMode`, `org.springframework.jms.core.JmsTemplate` và `org.springframework.context.annotation.Bean`. Các setter QoS trên template chỉ được chủ động áp dụng vào send nếu **`setExplicitQosEnabled(true)`** được bật. Cấu hình nên thực hiện **một lần khi tạo bean**; đừng gọi `template.setPriority(9)` trước mỗi request trong singleton dùng chung vì các thread có thể ghi đè cấu hình của nhau.

Nếu mỗi message cần QoS khác nhau, cân nhắc một template riêng theo nhóm policy, hoặc thao tác producer ở cấp JMS API/`JmsTemplate.execute` với tham số send cụ thể. Giữ `MessagePostProcessor` cho metadata, và phân biệt TTL với deadline nghiệp vụ trong body.

## 9. Vai trò của converter, processor và consumer trong một hệ thống thật

~~~text
Order Service
  |
  | orderId, business event
  v
MessageConverter                  -> serialize Java object thành JMS message
  |
  v
MessagePostProcessor             -> bổ sung correlationId, eventType, version
  |
  v
JmsTemplate / MessageProducer    -> chọn destination, delivery mode, priority, TTL
  |
  v
JMS Broker                       -> tiếp nhận, lưu, phân phối theo cấu hình
  |
  v
@JmsListener / Consumer          -> nhận, deserialize, validate metadata, xử lý
  |
  v
Database / External Service      -> side effect riêng, có transaction/idempotency
~~~

### 9.1. MessageConverter là gì?

Spring `org.springframework.jms.support.converter.MessageConverter` chuyển đổi giữa Java object và JMS `Message`. Mặc định `SimpleMessageConverter` hỗ trợ `String ↔ TextMessage`, `byte[] ↔ BytesMessage` và `Map ↔ MapMessage`. Với DTO JSON, thường cần cấu hình converter/serializer riêng; **việc gọi `convertAndSend` với một DTO bất kỳ không tự bảo đảm nó trở thành JSON TextMessage**.

Ví dụ DTO:

~~~java
public record OrderCreated(String orderId, int amount) {}
~~~

Đây chỉ là định nghĩa dữ liệu (đặt trong file `OrderCreated.java` nếu public), không phải ví dụ gửi chạy độc lập. Nếu muốn publish record này như JSON, chọn `MessageConverter` phù hợp và thiết lập mapping content/type một cách minh bạch. Sau đó `MessagePostProcessor` vẫn có thể thêm metadata mà không cần biết chi tiết serialize bên trong.

### 9.2. Consumer dựa vào metadata thế nào?

Một listener có thể lọc theo property `eventType`:

~~~java
// Snippet: chạy trong một Spring bean khác, có hạ tầng JMS listener.
@JmsListener(
    destination = "orders.events",
    selector = "eventType = 'order.created'")
public void handleOrderCreated(String body) {
    System.out.println("Received: " + body);
}
~~~

Cần import `org.springframework.jms.annotation.JmsListener`, cấu hình JMS listener của ứng dụng và quy tắc idempotency phù hợp. **Không thêm listener này vào cùng demo `receiveSelected` ở mục 6**, vì một listener khác trên cùng queue có thể cạnh tranh và tiêu thụ message trước phép thử đồng bộ.

Với xử lý metadata phức tạp, có thể nhận raw `jakarta.jms.Message` thông qua API tương ứng hoặc dùng Spring Messaging headers sau khi mapping. Cần kiểm tra converter và header mapper vì không phải mọi property/kiểu dữ liệu đều tự động ánh xạ như nhau.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `MessagePostProcessor` không chạy | Đã gọi overload `convertAndSend` không có processor hoặc dùng `send(MessageCreator)` | Kiểm tra đúng chữ ký `convertAndSend(..., processor)` |
| Callback ném lỗi trước `SEND_OK` | Sai kiểu JMS message, setter property không hợp lệ hoặc converter gặp lỗi | Kiểm tra converter, tên/type property, exception stack |
| `POSTPROCESSOR_OK` in rồi gửi thất bại | Post-processing xong nhưng broker/network/quyền send lỗi | Tách hai giai đoạn; xem exception khi producer send và broker log |
| Consumer không nhận message | Sai destination, selector không khớp, TTL hết, consumer khác đã nhận | Kiểm tra queue depth, selector, TTL, correlation ID, competing consumers |
| Metadata từ receiver khác mong đợi | Broker policy ghi đè hoặc converter/mapper khác đã xử lý | Đọc actual JMS headers/properties và config hai phía |
| `ClassCastException` khi cast `TextMessage` | Converter tạo `BytesMessage`, `MapMessage` hoặc provider message khác | Dùng `instanceof` và xác định converter đang hoạt động |
| `JMSPriority` không đúng số tự đặt | Header do provider/producer đặt khi send | Đặt QoS trên template/producer, bật explicit QoS nếu cần |
| Listener không tìm thấy `schemaVersion` | Property sai tên/chữ hoa-thường, hoặc chưa được post-process | Thống nhất contract, kiểm tra producer và raw received message |
| Request nhanh chậm bất thường | Callback gọi database/network hoặc tạo dữ liệu nặng | Giữ callback gọn, tránh blocking I/O |
| Một event bị tạo nhiều lần | Retry gửi hoặc transaction không rõ; processor được gọi lại | Dùng eventId/idempotency key ổn định; thiết kế outbox khi cần |
| Dữ liệu riêng tư xuất hiện trong broker/log | Đưa thông tin nhạy cảm vào property để tiện debug | Hạn chế metadata, kiểm soát log, retention, ACL, encryption |

**Thứ tự debug đề xuất:** xác nhận overload được gọi → theo dõi callback được kích hoạt → kiểm tra message vừa tạo → xác nhận send hoàn thành → đọc raw message ở consumer trên queue thử → so selector và provider policy. Không mặc định một lỗi selector là lỗi `MessagePostProcessor`.

### 10.1. Exception và retry

Nếu trong callback `postProcessMessage` có `JMSException`, quá trình `convertAndSend` có thể thất bại **trước khi producer gửi**. Nếu lỗi mạng xảy ra sau callback, vẫn có tình huống **không biết chắc broker đã tiếp nhận hay chưa**. Retry có thể phát message trùng dù metadata callback đều hợp lệ.

Do đó:
- Producer nên có **eventId/commandId** ổn định theo thao tác logic, nhất là khi retry.
- Consumer phải idempotent nếu side effect không được thực hiện lặp.
- Khi phát message song song với commit database, cân nhắc **transactional outbox**.
- Không thực hiện side effect không thể rollback (ví dụ trừ tiền, gửi email thật) **ngay trong post-processor**; callback có thể chạy rồi send vẫn lỗi.

### 10.2. Thread-safety

`JmsTemplate` thường được dùng như singleton trên nhiều thread. Lambda capture biến bất biến/local của từng request là cách tốt:

~~~java
String correlationId = requestCorrelationId;
jmsTemplate.convertAndSend("orders.events", payload, message -> {
    message.setJMSCorrelationID(correlationId);
    return message;
});
~~~

Đây là snippet minh họa; `requestCorrelationId` và `payload` phải có trong ngữ cảnh ứng dụng. Đừng lưu `correlationId` vào field singleton mutable kiểu “currentCorrelationId” rồi cập nhật trước mỗi send; nhiều request cùng lúc có thể lẫn metadata. Tránh thay đổi `JmsTemplate` shared configuration trong request path.

## 11. Khi nào không nên dùng MessagePostProcessor?

- Cần **serialize domain object** sang JSON/XML/Bytes: xây dựng `MessageConverter`.
- Cần **tạo message đặc biệt** bằng `Session` hoặc làm việc trực tiếp với JMS producer: dùng `MessageCreator`/`JmsTemplate.execute`.
- Cần **đọc và xử lý message**: dùng `@JmsListener`, listener container hoặc consumer.
- Cần **đảm bảo broker nhận/consumer xử lý**: thiết kế giao dịch, acknowledgement, retry và quan sát; post-processor một mình không bảo đảm độ tin cậy.
- Cần **thay đổi QoS cho từng lần gửi**: dùng policy producer/send phù hợp; không tự chỉnh provider-managed headers.
- Cần **tác vụ I/O chậm hoặc gọi database**: thực hiện ở tầng nghiệp vụ trước send hoặc trong luồng xử lý riêng có transaction, tránh đặt vào callback đồng bộ trước send.

## 12. Checklist áp dụng và câu hỏi tự kiểm tra

Checklist trước khi đưa một `MessagePostProcessor` vào ứng dụng:
- [ ] Chọn đúng interface `org.springframework.jms.core.MessagePostProcessor` của Spring JMS.
- [ ] Dùng đúng overload `convertAndSend` nhận processor.
- [ ] Converter tạo đúng loại JMS `Message` trước callback; không cast mù.
- [ ] Processor return một `jakarta.jms.Message` hợp lệ, không `null`.
- [ ] Chỉ đặt headers/properties thích hợp; giữ nguyên body trừ khi có hợp đồng rõ.
- [ ] Không đặt `JMSPriority`/`JMSExpiration` như cách cấu hình QoS.
- [ ] Correlation ID và eventId có chiến lược ổn định qua retry.
- [ ] Property names/types phù hợp selector và consumer contract.
- [ ] Không đưa secrets hoặc PII không cần thiết vào message/log.
- [ ] Đã test nhận lại raw message với queue riêng và selector/ID riêng.
- [ ] Đã xem xét transaction/outbox/idempotency nếu message liên quan dữ liệu quan trọng.

**Tự kiểm tra:**

1. `MessagePostProcessor` chạy trước hay sau `MessageConverter`? Tại sao điều này có lợi cho việc đặt JMS properties?
2. Khác biệt giữa `message.setJMSCorrelationID("x")` và `message.setStringProperty("JMSCorrelationID", "x")` là gì?
3. Vì sao `message.setJMSPriority(9)` trong processor không bảo đảm message được gửi ở priority `9`?
4. Nếu `POSTPROCESSOR_OK` xuất hiện nhưng `SEND_OK` không xuất hiện, có thể kết luận broker đã nhận message không?
5. Với DTO Java không có converter JSON được đăng ký, có thể mặc định `convertAndSend` sẽ gửi JSON `TextMessage` không?
6. Tại sao singleton `JmsTemplate` không nên có field mutable “currentCorrelationId” chia sẻ giữa các request?
7. Nếu consumer cần lọc `eventType = 'order.created'`, bạn phải đặt metadata ở đâu?
8. Sau khi callback chạy xong, message được gửi lặp lại do retry; trách nhiệm chống side effect trùng thuộc về đâu?

**Ghi nhớ:** `MessageConverter` xây dựng **JMS message từ Java object**; `MessagePostProcessor` bổ sung **header/property vào JMS message đó trước khi gửi**; `JmsTemplate` thực hiện **send**; và broker/consumer quyết định chuyện tiếp nhận, phân phối, xử lý sau đó. Từng thành phần có hợp đồng riêng, tránh trộn chức năng để dễ thử nghiệm, bảo trì và vận hành.

## Tài liệu tham khảo

- Spring Framework 6.1 – `MessagePostProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/jms/core/MessagePostProcessor.html
- Spring Framework – Sending a Message / JMS converters and post-processing: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework 6.1 – `JmsTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Boot 3.3 – JMS and Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Jakarta Messaging 3.1 Specification, JMS Headers and Message Properties: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
