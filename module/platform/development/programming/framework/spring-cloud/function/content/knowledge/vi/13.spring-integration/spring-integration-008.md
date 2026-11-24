# Tích hợp sự kiện CloudEvents và đối chiếu hỗ trợ phiên bản

## 1. Mục tiêu và bối cảnh

**Spring Cloud Function (SCF)** khuyến khích xây dựng nghiệp vụ bằng `Supplier<T>`, `Function<T,R>` và `Consumer<T>`. Nhờ `FunctionCatalog`, một hàm có thể được tra cứu, ghép (*composition*) và gọi qua HTTP, sự kiện, serverless hay một `IntegrationFlow` mà không phụ thuộc trực tiếp giao thức.

**Spring Integration** cung cấp Enterprise Integration Patterns (EIP) như *Message Channel*, *Transformer*, *Router*, *Filter*, *Gateway*, *Poller* và *Error Channel*. **CloudEvents** giải quyết vấn đề ở lớp khác: một **định dạng mô tả sự kiện thống nhất**, giúp các bên phát/nhận sự kiện trao đổi các thuộc tính cơ bản như mã sự kiện, nguồn và loại sự kiện mà không phụ thuộc vào giao thức vận chuyển.

Khi kết hợp cả ba, ứng dụng cần biết:

- CloudEvents 1.0 yêu cầu những thuộc tính nào, và `data` khác gì phần metadata?
- **Binary content mode** và **structured content mode** ảnh hưởng thế nào tới HTTP header/body, `Message<?>` và converter?
- Cách đưa sự kiện vào Spring Integration, gọi lại function nghiệp vụ trong `FunctionCatalog`, rồi phát CloudEvent mới.
- Mốc phiên bản nào cung cấp tiện ích CloudEvents trong **Spring Cloud Function**, và mốc nào có module **`spring-integration-cloudevents`**?
- Những kiểm tra cần có để tránh lỗi version skew, content type, mất metadata, xử lý trùng hoặc phát sự kiện không hợp lệ.

Bài học này thuộc chương **Spring Integration** của module **SPRING_CLOUD_FUNCTION**. Các phần giải thích mô hình và phiên bản được tách rõ để bạn áp dụng vào cả dự án đang dùng Spring Boot 3.x lẫn dòng mới hơn mà không mặc định mọi API xuất hiện ở mọi release.

## 2. CloudEvents là gì và không phải là gì?

CloudEvents là đặc tả do cộng đồng CNCF phát triển để mô tả **một sự kiện đã xảy ra** theo cấu trúc thống nhất. Nó định nghĩa thuộc tính ngữ cảnh (*context attributes*), dữ liệu sự kiện và các định dạng/protocol binding để truyền qua HTTP, Kafka, AMQP cùng những phương tiện khác.

Một ví dụ đơn giản: dịch vụ đơn hàng phát sự kiện “đơn hàng đã được tạo”:

~~~json
{
  "specversion": "1.0",
  "id": "evt-DH-101-v1",
  "source": "/sales/order-service",
  "type": "com.example.order.created",
  "subject": "orders/DH-101",
  "time": "2026-11-24T09:00:00Z",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "DH-101",
    "totalVnd": 1500000
  }
}
~~~

**CloudEvents không phải message broker, queue, workflow engine hay Spring Integration flow.** Nó không tự đem lại retry, transaction, ordering, exactly-once hoặc DLQ. `FunctionCatalog` cũng không tự tạo adapter gửi sự kiện; phần kết nối vẫn cần HTTP adapter, Spring Cloud Stream binder, Spring Integration adapter hoặc serverless event adapter tương ứng.

~~~mermaid
flowchart LR
    P["Service phát sự kiện"] --> A["CloudEvents<br/>context + data"]
    A --> B["HTTP / Kafka / AMQP / serverless"]
    B --> C["Adapter / header mapper"]
    C --> D["Spring Integration<br/>Message + EIP"]
    E["FunctionCatalog"] -. "lookup / composition" .-> F["Function nghiệp vụ"]
    D --> F
    F --> G["Transformer / outbound adapter"]
    G --> H["CloudEvent kết quả nếu cần"]
~~~

## 3. Hợp đồng CloudEvents 1.0

### 3.1. Các thuộc tính bắt buộc

Trong CloudEvents **specversion 1.0**, mỗi sự kiện hợp lệ phải có đủ bốn context attributes:

| Thuộc tính | Kiểu | Ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| `specversion` | String | Phiên bản của đặc tả mà sự kiện tuân theo. | `"1.0"` |
| `id` | String | Định danh sự kiện trong phạm vi nguồn phát. | `"evt-DH-101-v1"` |
| `source` | URI-reference | Xác định ngữ cảnh hoặc nguồn phát sự kiện. | `"/sales/order-service"` |
| `type` | String | Phân loại ý nghĩa sự kiện, do producer và consumer thỏa thuận. | `"com.example.order.created"` |

Producer phải đảm bảo **cặp `source + id` là duy nhất cho mỗi sự kiện khác nhau**. Khi cùng một sự kiện được gửi lại, consumer có thể xem cặp đó là dấu hiệu sự kiện trùng; đây là nền tảng tốt để xây idempotency. `source` phải là URI-reference không rỗng; URI tuyệt đối được khuyến nghị nhưng không bắt buộc.

### 3.2. Thuộc tính tùy chọn và dữ liệu

| Thuộc tính | Vai trò |
| --- | --- |
| `subject` | Xác định tài nguyên cụ thể bên trong ngữ cảnh `source`, ví dụ `orders/DH-101`. |
| `time` | Thời điểm xảy ra sự kiện (định dạng timestamp hợp lệ); khác với thời gian broker giao message. |
| `datacontenttype` | Media type của `data`, ví dụ `application/json` hoặc `text/plain`. |
| `dataschema` | URI trỏ tới schema mô tả `data`; tự nó không buộc consumer tải hoặc tự động xác thực schema. |
| `data` | Phần dữ liệu sự kiện, không phải một trong bốn thuộc tính bắt buộc của context. |
| Extension attributes | Metadata tùy biến theo contract, ví dụ `traceid`, `tenantid`; tên extension phải hợp lệ theo đặc tả. |

Đừng nhầm:

- `specversion` là **phiên bản đặc tả CloudEvents**, ví dụ `1.0`.
- `dataschema` hoặc field `schemaVersion` trong `data` liên quan đến **phiên bản hợp đồng dữ liệu nghiệp vụ**.
- `spring-cloud-function` `4.x/5.x`, Spring Integration `6.x/7.x` là **phiên bản thư viện**.
- `type` mô tả **loại sự kiện**, không tự là tên bean trong `FunctionCatalog`.

Một hệ thống có thể đồng thời dùng CloudEvents 1.0, schema nghiệp vụ v3 và Spring Cloud Function 5.1; ba con số đó mang các ý nghĩa khác nhau.

### 3.3. Tính tương thích của sự kiện

Một consumer không nên chỉ kiểm tra `specversion == "1.0"` rồi tin mọi dữ liệu còn lại. Cần kiểm tra thêm `source`, tập `type` cho phép, phiên bản schema nghiệp vụ, định dạng của `data`, kích thước payload và thông tin định danh của nguồn phát. Nếu là sự kiện đến từ bên ngoài, metadata được gửi qua header vẫn là **dữ liệu đầu vào**, chưa phải bằng chứng xác thực.

## 4. Binary và structured content mode

Đây là hai cách truyền **cùng một CloudEvent** được CloudEvents HTTP protocol binding quy định.

### 4.1. Structured mode

Context attributes cùng `data` nằm trong **một object JSON**; HTTP header `Content-Type` là `application/cloudevents+json`:

~~~http
POST /events HTTP/1.1
Host: localhost:8080
Content-Type: application/cloudevents+json

{
  "specversion": "1.0",
  "id": "evt-101",
  "source": "/sales/order-service",
  "type": "com.example.order.created",
  "datacontenttype": "application/json",
  "data": {"orderId":"DH-101","totalVnd":1500000}
}
~~~

Muốn đọc structured CloudEvent, bên nhận cần parser cho **event format** thích hợp; không thể chỉ lấy body và coi đó trực tiếp là một `OrderCreated` bởi body còn chứa cả context.

### 4.2. Binary mode

Các thuộc tính CloudEvents được đặt trong **header của HTTP binding**, còn body chính là event `data`:

~~~http
POST /events HTTP/1.1
Host: localhost:8080
Content-Type: application/json
ce-specversion: 1.0
ce-id: evt-101
ce-source: /sales/order-service
ce-type: com.example.order.created

{"orderId":"DH-101","totalVnd":1500000}
~~~

Chữ “binary” ở đây mô tả **cách tách metadata khỏi body**; `data` vẫn có thể là JSON hoặc text thuần. Trên HTTP, `ce-` là tiền tố của các CloudEvent context attributes ở binary mode. Với Kafka/AMQP, cần kiểm tra protocol binding và header mapper cụ thể; **không mặc định mọi transport dùng đúng tiền tố `ce-`**.

### 4.3. Bảng đối chiếu

| Vấn đề | Structured | Binary |
| --- | --- | --- |
| Nơi mang context | Cùng object/event format với `data` trong body. | Transport headers hoặc metadata tương ứng. |
| HTTP Content-Type | `application/cloudevents+json` cho JSON structured. | `datacontenttype` của `data`, ví dụ `application/json`. |
| Cách đọc | Deserialize toàn bộ CloudEvent rồi lấy `data`. | Đọc headers CloudEvents và body dữ liệu. |
| Khi đi qua broker | Cần format/binding phù hợp; broker có thể mang cả sự kiện trong payload. | Cần header mapping phù hợp với broker. |
| Failure phổ biến | Thiếu JSON EventFormat hoặc sai content type. | Mất context headers khi qua adapter, hoặc sai header prefix. |

CloudEvents còn có **batch mode** trong HTTP binding, nhưng không nên suy ra rằng mọi Spring Integration transformer hay adapter hỗ trợ tự động việc gửi/nhận nhiều CloudEvent trong một lần gọi. Hãy kiểm tra riêng khả năng xử lý batch trong phiên bản cụ thể.

## 5. Đối chiếu khả năng theo phiên bản

Phần này phân biệt **ba lớp khác nhau**: Spring Cloud Function, Spring Integration và Java SDK cho CloudEvents. Đây là những thông tin được đối chiếu theo tài liệu chính thức tại **24/11/2026**.

### 5.1. Ma trận hỗ trợ tính năng

| Thành phần / dòng phiên bản | CloudEvents và API liên quan | Ghi chú áp dụng |
| --- | --- | --- |
| **Spring Cloud Function từ 3.1** | Có `CloudEventMessageBuilder`, `CloudEventMessageUtils` và cơ chế hỗ trợ biểu diễn CloudEvents trong Spring Message. | Đây là tiện ích của **SCF context**; không đồng nghĩa có module CloudEvents riêng của Spring Integration. |
| **Spring Cloud Function từ 4.0.3** | Có module `spring-cloud-function-integration` và `FunctionFlowBuilder` để `fromSupplier`, `apply`, `accept` theo tên trong catalog. | Dùng cho kết nối mô hình hàm với Integration DSL; nó không tự là CloudEvents serializer. |
| **Spring Integration 6.x và 7.0.x** | Vẫn có Message, Transformer, Header Enricher và adapter để tự xây luồng CloudEvents bằng SDK/header mapper. | **Chưa có** module chuyên dụng `spring-integration-cloudevents`. |
| **Spring Integration từ 7.1.0 (GA tháng 6/2026)** | Bổ sung **`spring-integration-cloudevents`**, `ToCloudEventTransformer`, `FromCloudEventTransformer` và DSL CloudEvents. | Module chuyên dụng được tài liệu công bố hỗ trợ **CloudEvents spec 1.0**. |
| **Spring Integration 7.2.0 (GA 19/11/2026)** | Tiếp tục có module và transformer CloudEvents. | Có thể tham khảo tài liệu dòng 7.2, nhưng phải khớp BOM/Boot đang dùng. |
| **CloudEvents Java SDK** | `CloudEvent`, `CloudEventBuilder.v1()`, `EventFormatProvider`, HTTP/Kafka binding và nhiều event format. | Version **SDK Java** độc lập với `specversion: "1.0"`; module JSON cần dependency thích hợp. |

**Bốn mốc dễ nhầm:**

1. SCF hỗ trợ mô hình **CloudEvents headers** từ trước khi có module CloudEvents chuyên dụng của Spring Integration.
2. `spring-cloud-function-integration` xuất hiện ở **SCF 4.0.3**, phục vụ gọi hàm từ Spring Integration; tên module này khác với `spring-integration-cloudevents`.
3. `spring-integration-cloudevents` xuất hiện trong **Spring Integration 7.1**; **không thể chỉ copy import `ToCloudEventTransformer` vào dự án SI 6.5** rồi kỳ vọng class tồn tại.
4. `ToCloudEventTransformer` và `FromCloudEventTransformer` hiện nhắm **CloudEvents v1.0**. Đừng coi một `specversion` mới chưa được tài liệu xác nhận là tương thích mặc định.

### 5.2. Đối chiếu theo release train

| Dòng dự án tham khảo | Spring Boot / Spring Cloud | Cách tiếp cận CloudEvents hợp lý |
| --- | --- | --- |
| Dự án Spring Boot 3.5.x | Spring Cloud 2025.0.x, SCF 4.3.x theo release train. | Tận dụng SCF `CloudEventMessageBuilder`, CloudEvents Java SDK và Spring Integration DSL hiện có; không giả định đã có SI CloudEvents module 7.1. |
| Dự án Spring Boot 4.0.x/4.1.x | Spring Cloud 2025.1.x phù hợp, SCF 5.0.x. | Kiểm **Spring Integration được quản lý ở patch/BOM thực tế**; nếu là 7.0 thì chưa có module CloudEvents chuyên dụng, nếu có 7.1+ thì dùng sau khi xác minh tương thích. |
| Dự án Spring Boot 4.2.x | Spring Cloud 2026.0.x và SCF 5.1.x theo train. | Có thể hướng đến Spring Integration 7.2.x và module CloudEvents; kiểm release notes, BOM và starter trước khi chạy. |

Đây là bảng **định hướng chọn API**, không phải giấy phép nâng riêng SI hoặc SCF lên một major version khác. Version của **Spring Boot**, **Spring Cloud release train**, **Spring Integration**, **CloudEvents SDK** và **CloudEvents specversion** phải được kiểm tra ở đúng lớp. Cách chắc chắn là chọn một BOM của Spring Cloud tương thích Boot, sau đó kiểm tra dependency tree và tài liệu của phiên bản đã khóa.

### 5.3. Cách kiểm tra dependency thực tế

Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud,org.springframework.integration,io.cloudevents
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trong kết quả, kiểm tra artifact `spring-cloud-function-context`, `spring-cloud-function-integration`, `spring-integration-core`, `spring-integration-cloudevents` và các module `io.cloudevents`. Bảng hỗ trợ chỉ có ý nghĩa khi các artifact thực sự có mặt trong build.

## 6. Chọn cách tích hợp phù hợp

### 6.1. Cách A — Dùng Spring Cloud Function và metadata của Spring Message

Nếu dự án chưa có `spring-integration-cloudevents`, bạn vẫn có thể dùng tiện ích của SCF:

~~~java
import org.springframework.cloud.function.cloudevent.CloudEventMessageBuilder;
import org.springframework.messaging.Message;

Message<String> eventMessage = CloudEventMessageBuilder
        .withData("DH-101")
        .setSource("/sales/order-service")
        .setType("com.example.order.created")
        .setId("evt-101")
        .build();
~~~

`CloudEventMessageBuilder` hỗ trợ tạo `Message<T>` với context attributes. Tiền tố header và nội dung được adapter xử lý tùy giao thức; không tự biến nó thành **structured CloudEvents JSON** chỉ bằng việc gọi `build()`.

Khi nhận đầu vào `Message<OrderCreated>`, business function có thể đọc cả payload và metadata nếu cần:

~~~java
@Bean
Function<Message<String>, Message<String>> normalizeEvent() {
    return message -> MessageBuilder.fromMessage(message)
            .setPayload(message.getPayload().strip().toUpperCase())
            .build();
}
~~~

Đây là phương án dùng **SCF context** và Spring Messaging. Nếu function không cần metadata, ưu tiên `Function<String,String>` để tái sử dụng đơn giản hơn. Conversion ở adapter phải được kiểm chứng riêng.

### 6.2. Cách B — Dùng Java SDK để dựng CloudEvent

Ví dụ sử dụng CloudEvents Java SDK:

~~~java
import io.cloudevents.CloudEvent;
import io.cloudevents.core.builder.CloudEventBuilder;

import java.net.URI;
import java.nio.charset.StandardCharsets;

CloudEvent event = CloudEventBuilder.v1()
        .withId("evt-101")
        .withSource(URI.create("/sales/order-service"))
        .withType("com.example.order.created")
        .withSubject("orders/DH-101")
        .withData("text/plain",
                " dh-101 ".getBytes(StandardCharsets.UTF_8))
        .build();
~~~

SDK kiểm soát rõ các context attributes và cho phép serialize bằng một `EventFormat` tương ứng. Nếu muốn truyền structured JSON, cần module event format như `cloudevents-json-jackson` (hoặc biến thể Jackson 3 theo SDK đang dùng).

### 6.3. Cách C — Dùng module `spring-integration-cloudevents`

Với Spring Integration **7.1+**, có hai transformer:

- **`FromCloudEventTransformer`:** từ payload `CloudEvent` hoặc các byte biểu diễn structured CloudEvent, tạo Spring Integration message với `data` là payload và metadata CloudEvents trở thành các header như `ce-id`, `ce-type`, `ce-source`.
- **`ToCloudEventTransformer`:** từ Spring Integration message thành CloudEvents. Không chỉ định `EventFormat` thì đi theo **binary mode**, giữ payload và thêm header CloudEvents. Có format thì serialize CloudEvent vào payload theo **structured mode**.

Module này là công cụ **chuẩn hóa ranh giới message**; nghiệp vụ sau đó vẫn dùng `Supplier`, `Function`, `Consumer` hoặc catalog như bình thường.

## 7. Dependency cho ví dụ Spring Integration 7.1+

Phần ví dụ dưới đây sử dụng Spring Integration 7.1+ với Spring Cloud Function release tương thích, Java 17+ và Spring Boot có dependency management đã cấu hình.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-cloudevents</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-integration-cloudevents` dựa trên CloudEvents Java SDK; kiểm tra dependency tree và thêm `cloudevents-core` hoặc module EventFormat nếu ứng dụng trực tiếp sử dụng SDK hoặc cần structured JSON. Ví dụ sau dùng `CloudEventBuilder.v1()` và payload text nên không cần JSON EventFormat để tạo object CloudEvent.

**Không khai báo một version Spring Integration 7.1/7.2 ngẫu nhiên vào dự án đang khóa Spring Integration 6.x.** Nếu BOM của dự án chưa quản lý artifact mới, cần chọn phiên bản/release train tương thích trước khi bổ sung.

## 8. Ví dụ inbound: CloudEvent → IntegrationFlow → FunctionCatalog

### 8.1. Bài toán

Đầu vào là CloudEvent loại `com.example.order.created`, có `data` là mã đơn dạng UTF-8 text. Flow:

1. Nhận một `Message<CloudEvent>` ở channel `events.input`.
2. `FromCloudEventTransformer` chuyển `data` thành payload `byte[]`, đưa `ce-id`, `ce-source`, `ce-type` vào header.
3. Chuyển payload bytes thành `String`.
4. Tra cứu và gọi hàm `normalizeOrderId` từ `FunctionCatalog`.
5. Gửi chuỗi chuẩn hóa tới một `QueueChannel` để test.

~~~mermaid
flowchart LR
    A["CloudEvent object"] --> B["events.input"]
    B --> C["FromCloudEventTransformer"]
    C --> D["Message<byte[]> + ce-* headers"]
    D --> E["UTF-8 byte[] → String"]
    E --> F["FunctionCatalog.lookup(normalizeOrderId)"]
    F --> G["events.output QueueChannel"]
~~~

### 8.2. Hàm nghiệp vụ độc lập với CloudEvents

Tạo `src/main/java/example/events/OrderFunctions.java`:

~~~java
package example.events;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<String, String> normalizeOrderId() {
        return orderId ->
                orderId.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

Function này có thể được gọi từ HTTP, CloudEvents, Kafka message hoặc serverless adapter nếu có bước chuyển payload thích hợp. Nó không có phụ thuộc vào `CloudEvent`, `Message<?>` hay tên channel.

### 8.3. IntegrationFlow sử dụng transformer chính thức

Tạo `src/main/java/example/events/EventFlows.java`:

~~~java
package example.events;

import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

// CloudEvents là DSL factory của module spring-integration-cloudevents.
// IDE cần import class theo phiên bản Spring Integration 7.1+ đang dùng.

@Configuration
class EventFlows {

    @Bean("events.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean("events.output")
    PollableChannel output() {
        return new QueueChannel(16);
    }

    @Bean
    IntegrationFlow incomingEvents(FunctionCatalog catalog) {
        Function<String, String> normalize = Objects.requireNonNull(
                catalog.lookup("normalizeOrderId"),
                "Không tìm thấy normalizeOrderId");

        return IntegrationFlow.from("events.input")
                .transform(CloudEvents.fromCloudEventTransformer())
                .transform(byte[].class, data ->
                        new String(data, StandardCharsets.UTF_8))
                .filter(String.class, orderId -> !orderId.isBlank())
                .transform(String.class, normalize::apply)
                .channel("events.output")
                .get();
    }
}
~~~

Mẫu `.transform(CloudEvents.fromCloudEventTransformer())` là API Java DSL chính thức của module CloudEvents. `FromCloudEventTransformer` xử lý phần envelope, còn `normalizeOrderId` xử lý nghiệp vụ. `QueueChannel` giúp nhận kết quả trong test, không cần cấu hình poller nếu test tự gọi `receive(...)`.

**Chính sách đáng bổ sung khi triển khai thật:** kiểm tra `specversion`, `source` và `type` trước khi xử lý dữ liệu, đối chiếu `datacontenttype` với định dạng byte mà bạn định đọc, giới hạn kích thước và schema. Ở ví dụ tối thiểu này ta giả định producer đã dùng đúng `text/plain` và đúng event type.

### 8.4. Gửi sự kiện vào flow

Tạo một CloudEvent bằng SDK và đưa vào input channel:

~~~java
CloudEvent event = CloudEventBuilder.v1()
        .withId("evt-101")
        .withSource(URI.create("/sales/order-service"))
        .withType("com.example.order.created")
        .withData("text/plain",
                " dh-101 ".getBytes(StandardCharsets.UTF_8))
        .build();

MessageChannel input =
        context.getBean("events.input", MessageChannel.class);

input.send(MessageBuilder.withPayload(event).build());

PollableChannel output =
        context.getBean("events.output", PollableChannel.class);

Message<?> result = output.receive(1000);

assertNotNull(result);
assertEquals("DH-101", result.getPayload());
assertEquals("evt-101", result.getHeaders().get("ce-id"));
assertEquals("com.example.order.created",
        result.getHeaders().get("ce-type"));
~~~

Đây là phần của một test hoặc đoạn mã có `ApplicationContext context` và các import SDK/JUnit/Spring Messaging phù hợp. Với `DirectChannel`, các transformer chạy đồng bộ trước khi `send(...)` trả về; `receive(1000)` lấy message mà `QueueChannel` đã lưu.

`ce-id` là ID sự kiện của CloudEvents, **khác** với header `id` do Spring Messaging sinh ra. Trong hệ thống có redelivery, nên dùng `source + id` làm cơ sở chống xử lý trùng thay vì Spring Message ID.

## 9. Ví dụ structured JSON đầu vào

Bây giờ producer không gửi object `CloudEvent` mà gửi bytes của structured CloudEvent JSON:

~~~json
{
  "specversion": "1.0",
  "id": "evt-102",
  "source": "/sales/order-service",
  "type": "com.example.order.created",
  "datacontenttype": "text/plain",
  "data": "  dh-102  "
}
~~~

Ở ingress Spring Integration, message có thể được tạo như sau:

~~~java
byte[] jsonBytes = eventJson.getBytes(StandardCharsets.UTF_8);

Message<byte[]> incoming = MessageBuilder
        .withPayload(jsonBytes)
        .setHeader(MessageHeaders.CONTENT_TYPE,
                "application/cloudevents+json")
        .build();
~~~

`eventJson` ở đây là chuỗi JSON đã minh họa. Khi module `cloudevents-json-jackson` hoặc `cloudevents-json-jackson3` phù hợp có trên classpath, `FromCloudEventTransformer` có thể tra cứu `EventFormat` bằng `EventFormatProvider` và deserialize sự kiện. Sau đó, payload trở thành `data` bytes, các thuộc tính trở thành header `ce-*` và flow trong phần 8 có thể tiếp tục.

Đừng bỏ qua việc lựa chọn module JSON:

- **Jackson 2:** `io.cloudevents:cloudevents-json-jackson`.
- **Jackson 3:** `io.cloudevents:cloudevents-json-jackson3`, được cung cấp ở các dòng SDK hỗ trợ Jackson 3.
- Cần **khóa phiên bản SDK** và các module format cùng dòng; không ghép tùy tiện hai module hay coi việc dùng Spring Boot 4 tự động đảm bảo mọi format đều tồn tại.

Nếu thiếu format phù hợp hoặc `contentType` không trùng với format được đăng ký, transformer có thể ném `MessageTransformationException`. Hãy test structured và binary riêng vì chúng có đường decode khác nhau.

## 10. Outbound: Function tạo dữ liệu, transformer tạo CloudEvent

Ở chiều phát, business function nên trả **domain result** hoặc payload bytes đã có serializer hợp lệ. Tầng IntegrationFlow thêm context của CloudEvents.

~~~text
Function nghiệp vụ
    ↓
OrderDecision
    ↓ serialize thành byte[] theo datacontenttype
Message<byte[]> + eventId/source/type
    ↓
ToCloudEventTransformer
    ├─ không có EventFormat → binary mode (ce-* headers)
    └─ có EventFormat → structured mode (serialized CloudEvent)
    ↓
Outbound adapter (HTTP / broker / serverless)
~~~

### 10.1. Binary mode bằng ToCloudEventTransformer

Ví dụ cấu trúc DSL cho một message có payload `byte[]` và `contentType = "text/plain"`:

~~~java
return IntegrationFlow.from("events.outboundInput")
        .enrichHeaders(CloudEvents.headers()
                .idExpression("headers['businessEventId']")
                .sourceFunction(message ->
                        URI.create("/sales/order-service"))
                .type("com.example.order.normalized"))
        .transform(CloudEvents.toCloudEventTransformer())
        .channel("events.binaryOutput")
        .get();
~~~

Đây là fragment: các channel nguồn/đích và header `businessEventId` phải được khai báo, import `java.net.URI` cùng DSL factory `CloudEvents`. Theo tài liệu Spring Integration 7.1+, **`ToCloudEventTransformer` yêu cầu payload là `byte[]`**. Nếu mới có `OrderDecision` hoặc `String`, phải serialize rõ ràng trước khi gọi transformer.

Không cấu hình `EventFormat` thì transformer sử dụng binary mode: payload data giữ nguyên, các context attributes thêm vào headers với prefix `ce-` theo cách ánh xạ của module. `contentType` của message phản ánh `datacontenttype`.

### 10.2. Structured mode bằng EventFormat

Nếu được cấu hình một `EventFormat` phù hợp (hoặc expression cho content type để `EventFormatProvider` tra cứu), `ToCloudEventTransformer` có thể serialize toàn bộ CloudEvent vào payload. Với JSON, media type thường là `application/cloudevents+json` và phải có module JSON EventFormat tương ứng.

Đừng tự đổi `Content-Type` của binary message thành `application/cloudevents+json` mà không thật sự serialize event. Đây là lỗi dễ gây việc consumer hiểu body chỉ chứa `data` như một structured CloudEvent và báo parse error.

### 10.3. Định nghĩa id, source và type có chủ đích

Transformer có những default như ID message, source nội bộ và type chung theo tài liệu. Khi phát **business event**, nên thiết lập:

- `id`: event ID ổn định, giữ nguyên nếu phải retry cùng sự kiện.
- `source`: định danh producer đã công bố.
- `type`: tên event đã thỏa thuận, ví dụ `com.example.order.normalized`.
- `datacontenttype`: trùng serializer thực tế của data.
- `subject` và extension: chỉ thêm khi contract cần, tránh lộ thông tin nhạy cảm.

Khi một function xử lý input event và **phát một event mới**, đừng tự động copy cả bốn thuộc tính bắt buộc của event gốc sang event mới: một sự kiện mới thường cần `id`/`type` mới; có thể giữ `correlationId` để truy vết nguyên nhân.

## 11. Header mapping và sự khác nhau giữa Spring Message và CloudEvent

Sau `FromCloudEventTransformer`, một Spring Integration message thường có:

~~~text
payload = byte[] (" dh-101 ")
headers:
  ce-id              = evt-101
  ce-source          = /sales/order-service
  ce-type            = com.example.order.created
  ce-datacontenttype = text/plain
  contentType        = text/plain
  id                 = ... (Spring Message ID)
  timestamp          = ...
~~~

Đây là cách biểu diễn **nội bộ** sau khi transformer ánh xạ event attributes. `ce-id` là CloudEvent context, `id` là định danh của Spring Message. Không nên ghi đè một trong hai mà không chủ đích.

Một số điều phải kiểm tra:

1. **Transport binding:** `ce-` trong HTTP binary khác các quy tắc của binding Kafka/AMQP; dùng adapter hoặc SDK binding đúng giao thức.
2. **Adapter header mapper:** có adapter chỉ truyền allowlist headers; cần test `ce-id`, `ce-source`, `ce-type` sau khi đi qua hạ tầng thật.
3. **Content type:** `application/cloudevents+json` mô tả **structured envelope**; `application/json`/`text/plain` mô tả **data** trong binary mode.
4. **Function signatures:** `Function<byte[],R>` nhận raw data; `Function<OrderCreated,R>` yêu cầu decoder/mapper; `Function<Message<T>,Message<R>>` có thể đọc headers khi cần.
5. **Routing:** dùng `ce-type` để chọn kênh EIP là quyết định ở tầng Integration; một function gọi trực tiếp từ catalog vẫn không tự gửi message qua router.

Nếu một nguồn ngoài được phép tự chọn tên function qua header hoặc expression, cần allowlist function được phép chạy và tránh thực thi biểu thức tùy ý theo dữ liệu không tin cậy.

## 12. Lỗi thường gặp khi hỗ trợ CloudEvents

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Sự kiện thiếu `specversion`, `id`, `source` hoặc `type` | Producer tạo event không hợp lệ hoặc header mapping làm rơi thuộc tính. | Validate CloudEvents trước business function; kiểm tra transport binding. |
| Event có `specversion` không được hỗ trợ | Consumer/transformer chỉ công bố hỗ trợ spec v1.0. | Từ chối có kiểm soát, nâng component khi có hỗ trợ chính thức. |
| Structured JSON bị đọc như domain JSON | Sai `contentType` hoặc bỏ bước deserialize envelope. | Chọn `application/cloudevents+json` và EventFormat tương ứng. |
| `FromCloudEventTransformer` không deserialize được | Payload không phải `CloudEvent`/serialized bytes phù hợp, hoặc thiếu format. | Kiểm kiểu, content type và EventFormatProvider. |
| `ToCloudEventTransformer` báo sai payload | Đầu vào không phải `byte[]` theo hợp đồng transformer. | Serialize domain object trước khi transform. |
| Consumer không thấy `ce-type` sau Kafka | Header mapper hoặc protocol binding khác HTTP. | Kiểm tra Kafka binding và nội dung header thực tế. |
| `ClassNotFoundException` với transformer | Đang dùng Spring Integration dưới 7.1 hoặc thiếu artifact. | Đối chiếu BOM và `spring-integration-cloudevents`. |
| `FunctionFlowBuilder` không inject được | Thiếu `spring-cloud-function-integration` hoặc bản SCF quá cũ. | Kiểm tra SCF từ 4.0.3 và auto-configuration. |
| Event bị xử lý hai lần | Retry/redelivery theo broker hoặc caller gửi lại. | Idempotency theo `source + id` và transaction phù hợp. |
| Mất metadata khi function trả kết quả | Function chỉ trả payload hoặc adapter làm rơi header. | Dùng message-aware contract nơi cần; test header propagation. |

Một validation error không nhất thiết cần retry; lỗi hạ tầng có thể retry/backoff; lỗi mapping format/schema có thể cần quarantine hoặc dead-letter để phân tích. `FunctionCatalog`, CloudEvents và Spring Integration không tự cung cấp exactly-once khi chưa có thiết kế giao nhận.

## 13. Kiểm thử theo contract và theo phiên bản

### 13.1. Unit test function thuần

~~~java
OrderFunctions functions = new OrderFunctions();

assertEquals("DH-101",
        functions.normalizeOrderId().apply(" dh-101 "));
~~~

Đây là test business logic. Nó không chứng minh một serialized CloudEvent có thể đi qua HTTP/broker.

### 13.2. Test transformer với object CloudEvent

~~~java
CloudEvent event = CloudEventBuilder.v1()
        .withId("evt-201")
        .withSource(URI.create("/sales/order-service"))
        .withType("com.example.order.created")
        .withData("text/plain",
                "dh-201".getBytes(StandardCharsets.UTF_8))
        .build();

Message<?> parsed = new FromCloudEventTransformer().transform(
        MessageBuilder.withPayload(event).build());

assertEquals("evt-201", parsed.getHeaders().get("ce-id"));
assertEquals("com.example.order.created",
        parsed.getHeaders().get("ce-type"));
assertEquals("dh-201",
        new String((byte[]) parsed.getPayload(),
                StandardCharsets.UTF_8));
~~~

Đây là test module **Spring Integration 7.1+**; các class chính là `io.cloudevents.CloudEvent`, `io.cloudevents.core.builder.CloudEventBuilder` và `FromCloudEventTransformer` của artifact `spring-integration-cloudevents`.

### 13.3. Integration test flow

Ở ví dụ phần 8, gửi `Message<CloudEvent>` tới `events.input` và gọi `events.output.receive(timeout)`. Kiểm cả:

- Payload từ dữ liệu text `" dh-101 "` đã được normalize thành `"DH-101"`.
- Header `ce-id`, `ce-source` và `ce-type` vẫn dùng để correlation.
- Một message rỗng bị EIP Filter loại theo chính sách của flow.
- Thông điệp sai `type`, sai `specversion` hoặc có format không hỗ trợ được từ chối ở tầng xác thực thích hợp.

### 13.4. Contract test tại biên thật

| Trường hợp | Cần xác nhận |
| --- | --- |
| HTTP structured JSON | `Content-Type: application/cloudevents+json` và parser đọc đủ context + data. |
| HTTP binary | `ce-*` headers được map, body vẫn là domain data đúng `datacontenttype`. |
| Kafka/AMQP | Header mapping theo đúng protocol binding, không giả định dùng HTTP prefix. |
| Schema v1/v2 của domain | Consumer chấp nhận/không chấp nhận đúng theo contract, độc lập với `specversion`. |
| Redelivery | `source + id` ổn định; consumer idempotent. |
| Không có EventFormat | Structured parsing báo lỗi có kiểm soát, không nuốt lỗi. |
| Đổi release train | Build/import/API và wire format được kiểm chứng với BOM đã khóa. |

## 14. Lộ trình nâng cấp từ dự án cũ

Nếu dự án đang ở SCF 4.x + Spring Integration 6.x:

1. **Giữ business function thuần:** `Function<OrderCreated,OrderDecision>` chỉ xử lý domain payload.
2. **Bọc CloudEvents ở biên:** dùng `CloudEventMessageBuilder` hoặc CloudEvents Java SDK; ánh xạ context headers thủ công có kiểm soát nếu cần.
3. **Kiểm thử structured/binary, header mapping:** đặc biệt nếu đi qua Kafka hoặc AMQP.
4. **Chọn release train tương thích trước khi nâng:** nâng Spring Boot/Spring Cloud theo BOM được công bố; sau đó mới xác minh SI 7.1+ và artifact `spring-integration-cloudevents`.
5. **Dùng transformer chính thức khi đã sẵn sàng:** đặt `FromCloudEventTransformer` trước business function, `ToCloudEventTransformer` sau serialization của output.
6. **Giữ contract event ID/schema:** tránh thay `source`, `id`, `type` khi chỉ đổi implementation hoặc thư viện; nếu đổi schema nghiệp vụ, có kế hoạch tương thích.

Một ứng dụng không bắt buộc chuyển sang Spring Integration 7.1 chỉ để xử lý CloudEvents. SCF và CloudEvents SDK đã cho phép xây giải pháp theo contract từ trước. Ưu điểm của module mới là tích hợp transform/metadata theo DSL và giảm mã chuyển đổi thủ công ở ranh giới.

## 15. Checklist thiết kế

- [ ] Consumer kiểm đủ `specversion`, `id`, `source`, `type` trước khi thực thi nghiệp vụ.
- [ ] Producer đảm bảo `source + id` là duy nhất với các sự kiện khác nhau và ổn định khi retry cùng một sự kiện.
- [ ] `datacontenttype` đúng với bytes trong `data` và có mapper/schema validation phù hợp.
- [ ] Biết rõ incoming message là **CloudEvent object**, **structured bytes** hay **binary data + metadata**.
- [ ] Đã đối chiếu version SCF, SI, SDK và Spring Boot/Cloud BOM.
- [ ] Không dùng `spring-integration-cloudevents` nếu project đang ở SI dưới 7.1.
- [ ] Không nhầm SCF `spring-cloud-function-integration` với SI `spring-integration-cloudevents`.
- [ ] Function nghiệp vụ giữ độc lập với HTTP/Kafka/serverless khi không cần metadata.
- [ ] Kiểm thử `ce-*` headers tại đúng ranh giới adapter và không giả định transport khác nhau có cùng prefix.
- [ ] Retry, DLQ, idempotency và tracing có chính sách rõ, không phụ thuộc vào format CloudEvents đơn thuần.

### Câu hỏi tự đánh giá

1. Vì sao `specversion: "1.0"` không cho biết phiên bản của Spring Cloud Function?
2. Trong HTTP binary mode, `Content-Type: application/json` mô tả gì?
3. Tại sao một consumer nhận structured CloudEvent không thể lấy body JSON làm thẳng `OrderCreated`?
4. `CloudEventMessageBuilder` trong SCF khác `ToCloudEventTransformer` của Spring Integration ra sao?
5. Vì sao SI 6.x không thể chỉ thêm import `FromCloudEventTransformer` mà không nâng dependency phù hợp?
6. Tại sao idempotency dựa trên `source + id` đáng tin cậy hơn Spring Message header `id`?
7. Nếu nhận một event kiểu `com.example.order.created` nhưng `data` không đúng schema, lớp nào cần báo lỗi?

## 16. Tài liệu tham khảo chính thức

- [CloudEvents 1.0 — Core Specification](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md): các thuộc tính bắt buộc/tùy chọn, ý nghĩa `source + id` và extension.
- [CloudEvents — HTTP Protocol Binding](https://github.com/cloudevents/spec/blob/main/cloudevents/bindings/http-protocol-binding.md): structured, binary và batch content modes.
- [CloudEvents — JSON Event Format](https://github.com/cloudevents/spec/blob/main/cloudevents/formats/json-format.md): serialization của CloudEvent trong structured JSON.
- [Spring Integration — CloudEvents Support](https://docs.spring.io/spring-integration/reference/cloudevents.html): module, `ToCloudEventTransformer`, `FromCloudEventTransformer` và DSL.
- [Spring Integration — Changes between 7.0 and 7.1](https://docs.spring.io/spring-integration/reference/changes-7.0-7.1.html): mốc đưa module `spring-integration-cloudevents` vào framework.
- [Spring Integration 7.1.0 Released](https://spring.io/blog/2026/06/10/spring-integration-7-1-0-released/): xác nhận phát hành module mới.
- [Spring Integration 7.2.0 Released](https://spring.io/blog/2026/11/19/spring-integration-7-2-0-available/): thông báo bản 7.2.0.
- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): `FunctionFlowBuilder` và các mốc từ SCF 4.0.3.
- [Spring Cloud Function — CloudEventMessageBuilder Javadoc](https://javadoc.io/static/org.springframework.cloud/spring-cloud-function-context/4.0.1/org/springframework/cloud/function/cloudevent/CloudEventMessageBuilder.html): tiện ích SCF từ phiên bản 3.1.
- [CloudEvents Java SDK — Core](https://cloudevents.github.io/sdk-java/core.html) và [JSON Event Format](https://cloudevents.github.io/sdk-java/json-jackson.html): build/deserialize và quản lý event format.
- [Spring Cloud — Release Train Compatibility](https://spring.io/projects/spring-cloud/): Spring Boot tương ứng Spring Cloud release train.

**Kết luận:** CloudEvents xác định **hợp đồng sự kiện**; `FunctionCatalog` giữ **logic nghiệp vụ dùng lại được**; Spring Integration và adapter đảm nhiệm **đường đi, chuyển đổi message và xử lý lỗi**. Với Spring Integration 7.1+, `spring-integration-cloudevents` bổ sung transformer CloudEvents 1.0; ở các dự án cũ vẫn có thể dùng tiện ích CloudEvents của Spring Cloud Function hoặc Java SDK. Hãy đối chiếu **specversion, schema, library version và release train** riêng biệt, rồi kiểm thử wire format, content type, header mapping và idempotency trước khi đưa vào production.
