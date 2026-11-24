# Topic expression và topic header

## 1. Bài toán: mỗi message phải được publish đúng MQTT topic

Trong một ứng dụng tích hợp, không phải mọi message gửi ra MQTT broker đều thuộc cùng một topic. Lệnh điều khiển thiết bị có thể gửi tới `devices/device-17/commands`, trạng thái hiện tại đến `devices/device-17/state` và sự kiện kho đến `inventory/warehouse-02/changed`. Nếu hardcode một topic chung, bên nhận khó phân biệt dữ liệu; nếu lấy nguyên chuỗi topic từ request bên ngoài, ứng dụng có nguy cơ publish sai thiết bị hoặc sai tenant.

**Topic expression và topic header** là hai cách giúp Spring Integration quyết định **topic publish cho từng message**. Topic có thể được tính từ payload/headers qua một biểu thức hoặc được một bước upstream xác định trước rồi đặt vào `MqttHeaders.TOPIC`. MQTT outbound handler đọc thông tin này để tạo MQTT PUBLISH gửi đến broker.

Bài này thuộc chương **Adapter MQTT** của module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối các hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời làm rõ hợp đồng message, lỗi và vòng đời kết nối. Với MQTT, lựa chọn topic là một phần **hợp đồng giữa producer, broker và subscriber**, không chỉ là cách đặt tên channel nội bộ.

Sau bài này, người học có thể:

- Phân biệt **broker URL**, **MQTT topic**, **topic filter**, **Spring MessageChannel** và **message header**.
- Hiểu cách dùng `setDefaultTopic(...)`, `MqttHeaders.TOPIC` và biểu thức SpEL để xác định topic của một publication.
- Phân biệt `MqttHeaders.TOPIC` dành cho outbound với `MqttHeaders.RECEIVED_TOPIC` mô tả bản tin inbound.
- Tạo một flow Java DSL kiểm tra payload, xây topic an toàn và đặt header trước `MqttPahoMessageHandler`.
- Áp dụng header `MqttHeaders.QOS` và `MqttHeaders.RETAINED` đúng theo loại sự kiện.
- Giải thích lựa chọn topic cố định, topic động, router theo topic và chính sách fallback.
- Kiểm thử việc xác định topic và header **không cần MQTT broker**, rồi kiểm tra publish thực với broker.
- Thiết kế bảo mật topic/tenant, chống trùng, xử lý lỗi và retry.

**Nguyên tắc:** Spring `MessageChannel` quyết định **endpoint nội bộ nào** nhận message; MQTT topic quyết định **subscriber trên broker nào** có thể nhận publication. Hai cơ chế này phục vụ hai cấp định tuyến khác nhau.

## 2. Vị trí của topic trong luồng MQTT outbound

~~~mermaid
flowchart LR
    SRC["Business service / file / SFTP / HTTP / JMS / Kafka"]
    C["device.events<br/>Spring MessageChannel"]
    V["Validate event và định danh"]
    T["Xác định topic<br/>expression hoặc header"]
    H["MqttPahoMessageHandler"]
    B[("MQTT broker")]
    S1["Subscriber device-17"]
    S2["Subscriber device-21"]
    SRC --> C --> V --> T --> H
    H -->|"PUBLISH devices/device-17/state"| B
    B -->|"subscription phù hợp"| S1
    B -->|"subscription phù hợp"| S2
~~~

Một MQTT outbound adapter nhận Spring `Message<?>` chứa **payload** và **headers**, ví dụ:

~~~text
Message<String>
  payload:
    {"eventId":"evt-2001","deviceId":"device-17","temperature":26.5}
  headers:
    mqtt_topic: "devices/device-17/state"
    mqtt_qos: 1
    mqtt_retained: true
    correlationId: "trace-evt-2001"
~~~

Các header này thể hiện ý định publish. Spring Integration hỗ trợ các hằng `MqttHeaders.TOPIC`, `MqttHeaders.QOS` và `MqttHeaders.RETAINED`; trong Java nên sử dụng hằng thay vì gõ chuỗi `mqtt_topic`, `mqtt_qos`, `mqtt_retained` bằng tay.

Khi handler chuyển message thành MQTT PUBLISH, MQTT v3 truyền topic, QoS, retained flag và payload theo giao thức. **Header tùy biến của Spring như `correlationId` không mặc nhiên trở thành MQTT user property**; nếu subscriber phải đọc ID đó thì đưa nó vào JSON/schema payload hoặc có một giao thức mapping cụ thể.

## 3. Năm khái niệm dễ nhầm

| Khái niệm | Ví dụ | Dùng ở đâu? |
| --- | --- | --- |
| **Broker URL** | `tcp://localhost:1883` hoặc `ssl://mqtt.example.net:8883`. | `MqttConnectOptions` và client factory để kết nối broker. |
| **MQTT publish topic** | `devices/device-17/commands`. | Một publication gửi ra broker. |
| **MQTT subscription filter** | `devices/+/commands`. | MQTT inbound/subscriber đăng ký nhận topic phù hợp. |
| **Spring MessageChannel** | `mqtt.publish.requests`. | Đường kết nối endpoint bên trong Spring context. |
| **Spring message header** | `MqttHeaders.TOPIC` → `devices/device-17/commands`. | Metadata để outbound handler tạo MQTT publication. |

Ví dụ một ứng dụng có đúng **một** Spring input channel `mqtt.publish.requests` nhưng publish sang hàng nghìn MQTT topics khác nhau. Nó không cần tạo một Spring channel cho mỗi thiết bị. Ngược lại, có thể có nhiều Spring channels dùng chung một MQTT topic nếu topology nghiệp vụ yêu cầu.

### 3.1. Topic là địa chỉ phân phối, không phải URL

~~~text
Broker URL:     ssl://mqtt.example.net:8883
Spring channel: mqtt.publish.requests
Publish topic:  devices/device-17/commands
Subscription:   devices/+/commands
~~~

Không thêm topic vào cuối TCP broker URI như một đường dẫn HTTP. Với MQTT TCP, topic là trường của MQTT PUBLISH/SUBSCRIBE, không phải một path của URL server.

### 3.2. PUBLISH topic không dùng ký tự wildcard

Trong MQTT, `+` và `#` là wildcard dành cho **subscription filters**. Một PUBLISH phải sử dụng **topic name cụ thể**; không publish tới `devices/+/state` hoặc `devices/#`.

Các cấp topic phân tách bằng dấu `/`; tên topic phân biệt chữ hoa/chữ thường. `devices/device-17/state` và `Devices/device-17/state` có thể là hai topic khác nhau. Một hệ thống nên chuẩn hóa quy tắc đặt tên và thực hiện contract tests giữa producer với subscriber.

Các topic bắt đầu bằng `$` có thể được broker dành cho mục đích quản trị hoặc quy ước đặc biệt như `$SYS`. Không để giá trị tùy ý từ client chọn topic thuộc vùng quản trị.

## 4. Ba chiến lược chọn topic cho MQTT outbound

### 4.1. Topic mặc định cố định

Khi mọi message của một flow đều mang cùng loại dữ liệu, có thể cấu hình topic cố định cho outbound handler:

~~~java
var handler = new MqttPahoMessageHandler(
        "events-publisher-1", mqttClientFactory);
handler.setDefaultTopic("events/orders/created");
handler.setDefaultQos(1);
handler.setDefaultRetained(false);
~~~

Cách này phù hợp nếu mọi message của handler đều thực sự thuộc `events/orders/created`. Khi không có topic override và converter/handler được cấu hình sử dụng default topic, giá trị đó được dùng làm đích.

**Nhược điểm:** nếu ứng dụng quên đặt topic cho một message đáng lẽ gửi đến một thiết bị cụ thể, default topic có thể khiến publication vẫn được gửi nhưng **sai địa chỉ nghiệp vụ**. Với command hoặc dữ liệu đa tenant, nên fail rõ ràng khi thiếu topic thay vì dùng fallback quá rộng.

### 4.2. Topic qua MqttHeaders.TOPIC

Một bước upstream xác định topic đúng rồi đặt vào Spring message:

~~~java
Message<String> message = MessageBuilder
        .withPayload("{\"eventId\":\"evt-2001\",\"state\":\"ON\"}")
        .setHeader(MqttHeaders.TOPIC, "devices/device-17/state")
        .setHeader(MqttHeaders.QOS, 1)
        .setHeader(MqttHeaders.RETAINED, true)
        .build();
~~~

Đây là lựa chọn rõ ràng khi **nhiều producer hoặc flow khác nhau** đều sử dụng một outbound MQTT handler. Producer chịu trách nhiệm xây/validate topic; adapter xử lý serialization và MQTT publish.

`MqttHeaders.TOPIC` thể hiện **topic muốn publish**, không phải tên MQTT subscription, không phải tên Spring bean và không tự đồng nghĩa với topic mà inbound adapter từng nhận.

### 4.3. Topic expression (SpEL)

Khi topic có quy tắc được suy ra từ dữ liệu, có thể diễn đạt phép tính đó bằng Spring Expression Language:

~~~text
'devices/' + payload.deviceId() + '/state'
~~~

Ví dụ biểu thức đọc `deviceId` từ payload một `DeviceEvent` và tạo tên topic `devices/device-17/state`. Biểu thức có thể đọc metadata từ headers:

~~~text
'tenants/' + headers['tenantId'] + '/events/' + payload.eventType()
~~~

Biểu thức ở đây là **quy tắc tính toán trong Spring**, không phải expression được MQTT broker thực thi. Cần validate mọi giá trị động trước khi tính topic. Nếu API adapter/DSL/XML của phiên bản dự án hỗ trợ cấu hình topic expression trực tiếp, có thể dùng tính năng đó; còn một cách dễ kiểm thử và ít phụ thuộc API hơn là tính biểu thức trong một bước upstream rồi đặt kết quả vào `MqttHeaders.TOPIC`.

**Lưu ý về thứ tự ưu tiên:** giữa topic expression cấu hình trực tiếp ở handler, topic header và default topic, hành vi cuối phụ thuộc adapter/converter và phiên bản. Tránh cấu hình đồng thời nhiều nguồn quyết định topic mà không có policy tường minh; hãy xác nhận bằng test với phiên bản Spring Integration đang dùng.

## 5. Đặt topic header và tính topic expression khác nhau ở đâu?

| Tiêu chí | Topic header | Topic expression |
| --- | --- | --- |
| Nơi ra quyết định | Producer, transformer hoặc header enricher upstream. | Biểu thức được đánh giá tại vị trí cấu hình. |
| Giá trị đầu ra | `MqttHeaders.TOPIC` chứa một topic đã được quyết định. | Kết quả tính toán là topic được dùng cho publication hoặc gắn vào header. |
| Khi nào hữu ích? | Nhiều nguồn đã biết topic, cần chuyển qua handler dùng chung. | Quy luật topic dựa trên payload/header tương đối ổn định. |
| Kiểm thử | Kiểm tra header tại ranh giới trước outbound handler. | Kiểm tra expression với nhiều payload/header và trường hợp dữ liệu sai. |
| Kiểm soát bảo mật | Kiểm tra giá trị header không do client chọn tùy tiện. | Kiểm tra từng biến đầu vào; không nhận biểu thức từ người dùng. |
| Khả năng thay đổi | Upstream có thể thay đổi đích mà handler không đổi. | Thay rule hoặc cấu hình biểu thức có thể ảnh hưởng nhiều message. |

Hai cách có thể phối hợp: **expression → topic string → `MqttHeaders.TOPIC` → outbound handler**. Đây là mô hình được dùng trong ví dụ chính của bài.

### 5.1. Topic header không phải một cơ chế authorization

Một header như `mqtt_topic = "tenants/vip/commands"` chỉ là dữ liệu do ứng dụng gửi kèm. Nếu inbound HTTP cho phép caller đặt header này tùy ý rồi forward thẳng đến MQTT, caller có thể cố tình điều hướng sang topic của tenant khác. Vì vậy **topic header phải được tạo hoặc xác thực ở ranh giới tin cậy**, với ACL/topic policy ở cả ứng dụng và broker.

### 5.2. Topic expression không phải router tới Spring channel

Ví dụ `.route(...)` trong Java DSL chọn **Spring MessageChannel** như `orders.standard` hoặc `orders.express`. Một expression tạo `"devices/device-17/state"` đang tính **MQTT topic**, không tạo subscriber mới trong Spring context. Cần phân biệt nơi lựa chọn dữ liệu được xử lý nội bộ với nơi MQTT broker phân phối publication.

## 6. Ví dụ hoàn chỉnh: đặt MQTT topic động từ DeviceEvent

Ta xây một ứng dụng nhận `DeviceEvent` qua Spring channel `device.events`. Dựa trên `kind` của event, flow chọn topic:

- `STATE` → `devices/{deviceId}/state`, retained `true` để subscriber mới thấy snapshot trạng thái.
- `COMMAND` → `devices/{deviceId}/commands`, retained `false` để tránh phát lại lệnh một lần.

Mỗi publication dùng QoS 1 và mang `eventId` trong JSON payload để subscriber có thể tự chống trùng. Demo đặt `eventId` vào header Spring để quan sát, nhưng **ID đó vẫn phải nằm trong JSON** nếu subscriber phải đọc nó khi dùng MQTT v3.

### 6.1. Dependency Maven

Với Spring Boot quản lý phiên bản dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mqtt</artifactId>
</dependency>
~~~

Ví dụ dùng Java 17+ và Spring Integration với Eclipse Paho MQTT v3. API class điển hình: `MqttPahoMessageHandler`, `MqttPahoClientFactory`, `DefaultPahoMessageConverter` và `MqttHeaders`. Nếu dự án dùng MQTT v5 adapter, cần đối chiếu API/client tương ứng thay vì trộn lẫn class của hai dòng.

### 6.2. Cấu trúc code

~~~text
src/main/java/demo/mqtttopics/
    MqttTopicApplication.java
    MqttTopicFlowConfiguration.java
    MqttTransportConfiguration.java
    DeviceEvent.java
    TopicMessageMapper.java
    DeviceEventPublisher.java

src/main/resources/
    application.properties
~~~

Các đoạn mã đều nằm trong package `demo.mqtttopics`. Class public phải được đặt vào file Java trùng tên; các class/record package-private có thể được tách thành file cùng tên để tiện đọc.

### 6.3. Spring Boot application

~~~java
package demo.mqtttopics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttTopicApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttTopicApplication.class, args);
    }
}
~~~

### 6.4. Data contract và chính sách tạo topic

~~~java
package demo.mqtttopics;

record DeviceEvent(
        String eventId,
        String deviceId,
        String kind,
        String json) {
}
~~~

Một service chuyên trách kiểm tra đầu vào và tạo Spring message:

~~~java
package demo.mqtttopics;

import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class TopicMessageMapper {

    private TopicMessageMapper() {
    }

    static Message<String> toMqttMessage(DeviceEvent event) {
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Thiếu eventId");
        }
        if (event.deviceId() == null
                || !event.deviceId().matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("deviceId không hợp lệ");
        }
        if (event.json() == null || event.json().isBlank()) {
            throw new IllegalArgumentException("Thiếu JSON payload");
        }

        String suffix;
        boolean retained;

        switch (event.kind()) {
            case "STATE" -> {
                suffix = "state";
                retained = true;
            }
            case "COMMAND" -> {
                suffix = "commands";
                retained = false;
            }
            default -> throw new IllegalArgumentException(
                    "Loại event không hỗ trợ: " + event.kind());
        }

        String topic = "devices/" + event.deviceId() + "/" + suffix;

        return MessageBuilder.withPayload(event.json())
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, 1)
                .setHeader(MqttHeaders.RETAINED, retained)
                .setHeader("eventId", event.eventId())
                .build();
    }
}
~~~

Trong ví dụ này:

1. `eventId` bắt buộc có để tạo định danh nghiệp vụ.
2. `deviceId` bị giới hạn bởi allowlist ký tự, độ dài; vì vậy không thể chèn dấu `/`, `+` hoặc `#` để thay đổi cấu trúc topic.
3. Chỉ hai giá trị `kind` được hỗ trợ, nên không có route tùy ý.
4. Topic, QoS và retained được đặt trong message headers **trước khi handler được gọi**.
5. Payload `json` được dùng nguyên dạng. Trong hệ thống thật, cần serialize từ DTO/validate JSON và bảo đảm `eventId` trong payload đúng với header.

**Lưu ý:** lựa chọn retained=true cho `STATE` chỉ đúng khi đó thực sự là trạng thái/snapshot cuối cùng được phép giữ ở broker; không áp dụng mặc định cho mọi event state. Nếu đó là sự kiện trạng thái có tính lịch sử và cần đủ mọi thay đổi, retained không thay thế event log.

### 6.5. Cấu hình inbound channel nội bộ và flow outbound

~~~java
package demo.mqtttopics;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
class MqttTopicFlowConfiguration {

    @Bean(name = "device.events")
    MessageChannel deviceEvents() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow deviceEventOutboundFlow(
            @Qualifier("mqttPublisher") MessageHandler mqttPublisher) {

        return IntegrationFlow.from("device.events")
                .transform(DeviceEvent.class,
                        TopicMessageMapper::toMqttMessage)
                .handle(mqttPublisher)
                .get();
    }
}
~~~

`.transform(...)` nhận payload `DeviceEvent`, chuyển thành Spring `Message<String>` chứa topic headers, rồi `.handle(...)` chuyển message đến MQTT outbound handler. Handler là điểm kết thúc một chiều, không tạo reply nghiệp vụ.

`DirectChannel` giúp ví dụ dễ hiểu, nhưng khi broker chậm thì thread gửi message có thể bị chặn theo chế độ publish đồng bộ. Không thêm một `@ServiceActivator(inputChannel="device.events")` thứ hai nếu không định thiết kế nhiều consumer, vì `DirectChannel` không mặc định broadcast.

### 6.6. Cấu hình client factory và outbound handler

~~~java
package demo.mqtttopics;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;

@Configuration
class MqttTransportConfiguration {

    @Bean
    MqttPahoClientFactory mqttClientFactory(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {

        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(true);

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler mqttPublisher(
            MqttPahoClientFactory factory,
            @Value("${app.mqtt.publisher-client-id}") String clientId) {

        var handler = new MqttPahoMessageHandler(clientId, factory);
        handler.setDefaultTopic("diagnostics/unrouted");
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setConverter(new DefaultPahoMessageConverter());
        handler.setAsync(false);
        handler.setCompletionTimeout(5000);
        return handler;
    }
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
app.mqtt.broker-url=tcp://localhost:1883
app.mqtt.publisher-client-id=topic-publisher-local-1
~~~

Ở đây handler có `defaultTopic` để minh họa fallback; tuy nhiên **mọi message hợp lệ từ `TopicMessageMapper` đều phải mang `MqttHeaders.TOPIC`**. Trong production, nên coi việc thiếu topic là lỗi ở validation stage nếu publication bắt buộc hướng tới thiết bị cụ thể; đừng để default topic che khuất bug routing.

Demo chưa cấu hình username, password hoặc TLS. Khi dùng broker ngoài mạng local, hãy nạp credentials từ secrets, dùng TLS và xác thực chứng chỉ, kiểm tra broker ACL trên từng topic. Việc tạo factory và handler không tự tạo MQTT broker.

### 6.7. Một service gọi flow

~~~java
package demo.mqtttopics;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class DeviceEventPublisher {

    private final MessageChannel input;

    DeviceEventPublisher(
            @Qualifier("device.events") MessageChannel input) {
        this.input = input;
    }

    boolean publish(DeviceEvent event) {
        return input.send(MessageBuilder.withPayload(event).build());
    }
}
~~~

Một caller đã xác thực có thể dùng:

~~~java
publisher.publish(new DeviceEvent(
        "evt-2001",
        "device-17",
        "STATE",
        "{\"eventId\":\"evt-2001\",\"deviceId\":\"device-17\","
                + "\"state\":\"ON\"}"));
~~~

Message chuyển từ `device.events` → mapper → outbound handler → MQTT broker với topic `devices/device-17/state`, QoS 1, retained=true.

**Không gọi đây là xác nhận thiết bị đã cập nhật:** `MessageChannel.send()` là thao tác bàn giao message trong Spring; tùy channel và cấu hình sync/async, kết quả publish/broker có thể cần quan sát riêng. Nếu ứng dụng cần biết thiết bị đã thực thi command, phải có inbound ACK flow tương quan bằng `eventId`/`commandId`.

## 7. Topic expression bằng Spring Expression Language (SpEL)

Ví dụ chính dùng Java thuần để kiểm soát validation và mapping. Khi quy tắc tính topic đơn giản, SpEL giúp mô tả cùng nguyên tắc bằng biểu thức ngắn.

Giả sử payload là `DeviceEvent`; tạo một Spring message:

~~~java
Message<DeviceEvent> source = MessageBuilder.withPayload(
        new DeviceEvent(
                "evt-2002",
                "device-21",
                "STATE",
                "{\"eventId\":\"evt-2002\",\"state\":\"OFF\"}"))
        .build();
~~~

Dùng `SpelExpressionParser` đánh giá topic:

~~~java
Expression expression = new SpelExpressionParser()
        .parseExpression(
                "'devices/' + payload.deviceId() + '/state'");

String topic = expression.getValue(source, String.class);
// topic = "devices/device-21/state"
~~~

Các import cần dùng:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
~~~

Ở đây root object của SpEL là `Message<DeviceEvent>`, nên `payload` trỏ đến record `DeviceEvent` và `payload.deviceId()` gọi accessor của record. Giá trị kết quả chỉ nên được đưa vào `MqttHeaders.TOPIC` **sau khi** `deviceId` đã được validate.

### 7.1. Biểu thức dựa trên header

Một flow có thể đặt thông tin routing đã được xác minh vào header `safeDeviceId`, rồi tính topic bằng:

~~~text
'devices/' + headers['safeDeviceId'] + '/commands'
~~~

Điều này phù hợp khi payload là `byte[]` hoặc `String` JSON và device ID đã được parse/validate ở bước trước. Không nên nhận `safeDeviceId` trực tiếp từ HTTP request header rồi tin nó chỉ vì tên có chữ `safe`.

Nếu dùng biểu thức cấu hình trực tiếp ở adapter hoặc một header enricher, cần bảo đảm expression thực sự được đánh giá **trên message mong đợi**, và loại kết quả cuối là `String` chứa MQTT topic hợp lệ. Hãy kiểm tra XSD/API của phiên bản Spring Integration đang sử dụng khi chuyển từ ví dụ Java sang XML hoặc Java DSL endpoint spec.

### 7.2. Không nhận SpEL từ dữ liệu người dùng

SpEL là một ngôn ngữ biểu thức của framework, có thể truy cập thuộc tính, gọi method và sử dụng nhiều tính năng khác. **Không** cho phép publisher/HTTP caller cung cấp nguyên văn biểu thức để Spring thực thi, vì sẽ tạo rủi ro an ninh và làm mất khả năng kiểm soát routing.

Biểu thức nên do developer hoặc cấu hình đã được tin cậy xác định; dữ liệu từ bên ngoài chỉ được dùng như các giá trị đã qua validation với danh sách ký tự/loại event được phép.

### 7.3. Tính toán trong transformer hay tại outbound adapter?

Hai lựa chọn có thể phù hợp:

- **Transformer/header enricher upstream:** tạo `MqttHeaders.TOPIC` trước handler. Ưu điểm là test topic policy không cần broker và có thể log routing decision trước khi gửi.
- **Biểu thức trực tiếp tại adapter:** gọn khi một handler có quy tắc cố định, nhưng cần hiểu độ ưu tiên với `MqttHeaders.TOPIC`/`defaultTopic` và bộ converter theo phiên bản.

Khi nhiều nguồn gửi cùng một outbound handler, giải pháp **upstream chuẩn hóa rồi đặt topic header** thường dễ kiểm soát authorization và hợp đồng hơn. Không cấu hình cùng lúc các nguồn topic cạnh tranh mà không có test về độ ưu tiên.

## 8. Inbound RECEIVED_TOPIC không đồng nhất với outbound TOPIC

Trong Spring Integration MQTT, một inbound adapter có thể gắn header `MqttHeaders.RECEIVED_TOPIC` cho biết **topic thực tế broker đã giao message tới**. Outbound handler sử dụng `MqttHeaders.TOPIC` để quyết định **đích publish**.

~~~text
Inbound nhận từ:
  mqtt_receivedTopic = "sensors/device-17/temperature"

Outbound cần publish đến:
  mqtt_topic = "telemetry/device-17/normalized"
~~~

Hai giá trị có thể khác nhau vì hệ thống thực hiện transform, bảo mật, phân tuyến hoặc chuyển đổi giao thức.

### 8.1. Ví dụ bridge dữ liệu từ MQTT inbound sang MQTT outbound

Không nên sao chép nguyên header của inbound message rồi mặc định đích outbound là topic gốc. Nếu yêu cầu chuyển telemetry đã chuẩn hóa sang một topic khác, nên thực hiện:

1. Đọc `MqttHeaders.RECEIVED_TOPIC` để biết nguồn.
2. Parse/validate device ID, topic shape và payload.
3. Xác định topic mới theo mapping được phép, ví dụ `telemetry/{deviceId}/normalized`.
4. Gắn `MqttHeaders.TOPIC` vào message outbound, cùng QoS/retained phù hợp.
5. Đưa tới outbound handler qua channel riêng, không tạo vòng publish–subscribe vô hạn.

Một publisher có thể vô tình subscribe chính topic nó publish và lặp lại message mãi nếu hai flow ghép vòng. Cần kiểm tra topology và đánh dấu/kiểm soát vòng lặp theo `eventId`, nguồn và quy tắc topic.

### 8.2. Header MQTT trong Spring khác MQTT user properties

Với MQTT v3, không có cơ chế user properties tổng quát như MQTT v5. Header Spring để điều khiển converter **không tự xuất hiện trong MQTT payload**. Nếu muốn subscriber biết trace ID, tenant, command ID, hãy quy định chúng trong JSON, binary frame hoặc định dạng application protocol đã thống nhất.

## 9. Khi nào dùng topic header, khi nào dùng router?

Một ứng dụng có thể cần cả hai tầng điều hướng:

~~~mermaid
flowchart LR
    E["Business event"]
    R{"Spring router theo eventType"}
    C1["events.telemetry<br/>Spring channel"]
    C2["events.commands<br/>Spring channel"]
    T1["Tạo topic + header<br/>telemetry/{id}/state"]
    T2["Tạo topic + header<br/>devices/{id}/commands"]
    O1["MQTT outbound handler"]
    O2["MQTT outbound handler"]
    B[("MQTT broker")]
    E --> R
    R -->|"STATE"| C1 --> T1 --> O1 --> B
    R -->|"COMMAND"| C2 --> T2 --> O2 --> B
~~~

Nếu hai loại event cần cùng client factory, cùng retry và QoS policy, có thể chỉ dùng **một** outbound handler với topic header động. Nếu chính sách bảo mật/credential, broker URL, retained, retry hoặc client lifecycle khác nhau đáng kể, nên cân nhắc **hai handler hoặc hai factory** để giữ ranh giới rõ ràng.

| Thiết kế | Lợi ích | Rủi ro cần quản lý |
| --- | --- | --- |
| Một outbound handler, nhiều topic header | Cấu hình tập trung, ít endpoint. | Mọi message phải xác định topic an toàn; chính sách broker chung. |
| Spring router → nhiều outbound handler | Cô lập chính sách theo loại message/đích. | Nhiều endpoint, client ID, monitoring và retry. |
| Topic expression trong một handler | Rule gọn nếu topic pattern ổn định. | Dễ bỏ sót validation/priority với header/default topic. |
| Mapping cấu hình giữa business key → topic | Kiểm soát tốt allowlist và thay đổi đích. | Cần quản lý version/config và test khi sửa mapping. |

**Không dùng topic wildcard MQTT như cách mô phỏng Spring router.** Wildcard filter dành cho subscriber; publisher phải chọn tên topic cụ thể.

## 10. Topic theo tenant/thiết bị: thiết kế hợp đồng và bảo mật

Tạo topic động từ dữ liệu đa tenant là một trong những nơi dễ xảy ra lỗi phân quyền.

Ví dụ cấu trúc:

~~~text
tenants/{tenantId}/devices/{deviceId}/commands
tenants/{tenantId}/devices/{deviceId}/state
~~~

Một thiết kế an toàn cần:

1. **Authentication:** caller phải được xác thực.
2. **Authorization:** caller được phép điều khiển `deviceId` thuộc `tenantId`.
3. **Validation:** ID chỉ chứa ký tự cho phép, không được chèn dấu `/`, wildcard, ký tự điều khiển hoặc chuỗi vượt độ dài.
4. **Canonical mapping:** topic được tạo bởi code từ ID đã xác minh; không nhận nguyên topic từ caller.
5. **Broker ACL:** MQTT publisher credential chỉ có quyền publish các topic được phép.
6. **Audit:** ghi actor, event/command ID, topic đã được kiểm tra và kết quả publish/ACK.
7. **Idempotency:** subscriber phân biệt command mới và command được giao lại.
8. **Retention policy:** không retained những command dùng một lần.

Đừng dùng `String.replace("/", "_")` tùy tiện để “chữa” topic injection vì hai ID khác nhau có thể bị biến thành cùng một topic. Tốt hơn là **từ chối ID không hợp lệ** theo hợp đồng hoặc encode bằng một quy tắc một-một đã được các bên thống nhất.

### 10.1. Topic case-sensitive và quy ước tên

Ví dụ `device-17`, `Device-17` và `DEVICE-17` có thể khác nhau. Nếu hệ thống chọn lowercase, chuẩn hóa ngay tại nơi cấp định danh hoặc trước khi lookup quyền, không chỉ lowercase topic sau khi authorization theo giá trị gốc.

Mỗi message cần có routing decision xác định được từ **business identity + loại message + version quy tắc** để có thể điều tra tình huống replay hoặc thay đổi contract.

## 11. QoS và retained cũng có thể đi theo header

Trong ví dụ Java, topic không phải header duy nhất ảnh hưởng đến publication:

~~~java
Message<String> stateMessage = MessageBuilder
        .withPayload("{\"eventId\":\"evt-2003\",\"state\":\"ON\"}")
        .setHeader(MqttHeaders.TOPIC, "devices/device-17/state")
        .setHeader(MqttHeaders.QOS, 1)
        .setHeader(MqttHeaders.RETAINED, true)
        .build();

Message<String> commandMessage = MessageBuilder
        .withPayload("{\"commandId\":\"cmd-3001\",\"action\":\"TURN_OFF\"}")
        .setHeader(MqttHeaders.TOPIC, "devices/device-17/commands")
        .setHeader(MqttHeaders.QOS, 1)
        .setHeader(MqttHeaders.RETAINED, false)
        .build();
~~~

| Loại dữ liệu | Topic | QoS minh họa | Retained minh họa |
| --- | --- | --- | --- |
| Snapshot thiết bị hiện tại | `devices/{id}/state` | 1 | `true` khi broker cần giữ trạng thái cuối. |
| Command một lần | `devices/{id}/commands` | 1 | `false` để không replay command cũ cho subscriber mới. |
| Telemetry liên tục | `sensors/{id}/temperature` | 0 hoặc 1 theo SLA. | Thường `false` nếu mỗi message là mẫu sự kiện. |
| Sự kiện nghiệp vụ quan trọng | `events/orders/created` | 1/2 theo giao thức. | Thường `false`; dùng kho sự kiện bền vững ngoài retained. |

QoS 1 có thể làm subscriber nhận trùng. QoS 2 giảm trùng ở tầng giao thức MQTT, **không bảo đảm side effect nghiệp vụ đúng một lần**. Retained chỉ lưu snapshot mới nhất theo topic (phụ thuộc broker), không phải một event store đầy đủ.

### 11.1. Những header nào không nên mang xuyên broker?

Không tự serialize Spring headers như `replyChannel`, `errorChannel`, object bảo mật, token nội bộ hoặc kết nối Java. Với MQTT v3, publisher thường cần chuyển thông tin nghiệp vụ vào payload schema; chỉ topic/QoS/retained là các tham số MQTT publication chính trong ví dụ.

Nếu cần request–reply qua MQTT, phải thiết kế **hai topic hoặc kênh logic request/ACK**, cùng command ID và cơ chế timeout/correlation. `MqttPahoMessageHandler` outbound là một handler gửi một chiều, không tự trở thành gateway trả DTO khi broker nhận publication.

## 12. Lỗi khi tạo hoặc truyền topic

~~~mermaid
flowchart TD
    IN["Message từ upstream"]
    VAL{"Validate type, device ID, quyền?"}
    MAP["Expression / mapper tạo topic"]
    HDR["Set MqttHeaders.TOPIC"]
    PUB["MqttPahoMessageHandler"]
    BROKER[("MQTT broker")]
    ERR["Error flow / quarantine / retry"]
    IN --> VAL
    VAL -->|"Hợp lệ"| MAP --> HDR --> PUB --> BROKER
    VAL -->|"Không hợp lệ"| ERR
    MAP -. "expression / mapping lỗi" .-> ERR
    PUB -. "topic invalid / broker lỗi" .-> ERR
~~~

| Loại lỗi | Ví dụ | Xử lý |
| --- | --- | --- |
| Thiếu ID/routing key | Payload không có deviceId. | Reject/quarantine trước khi build topic. |
| Topic có wildcard publish | `devices/+/commands`. | Không publish, sửa chính sách sinh topic. |
| Topic sai tenant | Caller muốn publish sang thiết bị không có quyền. | Authorization và broker ACL; ghi audit sự kiện bị từ chối. |
| Header topic sai kiểu | Header không phải `String` hoặc chứa giá trị không hợp lệ. | Contract validation trước handler. |
| Không có header và default topic | Message đi tới fallback ngoài ý muốn. | Fail fast với event quan trọng, test omission. |
| Expression không đánh giá được | Property thiếu/sai kiểu, SpEL parse/evaluation error. | Kiểm thử rule, kiểm tra schema, không retry vô hạn lỗi data. |
| Broker từ chối publish | ACL, kết nối, timeout, broker chưa sẵn sàng. | Retry/backoff có giới hạn, outbox và đối soát. |
| Đích đã nhận nhưng thiếu ACK | Broker/device phản hồi muộn hoặc mất. | Kết quả không chắc chắn; idempotency và business ACK riêng. |

**Phân biệt:** lỗi topic mapping thường là **lỗi dữ liệu/cấu hình**, không nên retry lại nguyên message vô hạn. Lỗi broker/network có thể tạm thời, nhưng retry publication sau timeout có nguy cơ trùng vì broker có thể đã nhận bản tin trước khi response mất.

### 12.1. Không để default topic che giấu lỗi

Với command/transaction, một cấu hình như `handler.setDefaultTopic("devices/default/commands")` có thể nguy hiểm: nếu mapper quên header, lệnh có thể tới thiết bị hoặc hệ thống không mong đợi.

Hãy dùng contract test xác nhận **mọi command mang topic cụ thể** trước handler. Nếu vẫn cần fallback, chọn topic chỉ để chẩn đoán/quarantine với quyền hạn riêng và không có subscriber thực hiện lệnh nghiệp vụ, hoặc đơn giản từ chối message thiếu topic.

### 12.2. Lỗi đồng bộ và bất đồng bộ

Với `DirectChannel` và handler `setAsync(false)`, một số lỗi outbound có thể lan về caller đang `send(...)`. Với `ExecutorChannel`, `QueueChannel` hoặc handler async, lỗi publish có thể xuất hiện trên thread/callback khác và cần monitoring/error handling riêng.

Đừng cho rằng một `MessageChannel.send()` thành công luôn đồng nghĩa MQTT broker đã ACK, hay broker ACK đồng nghĩa subscriber đã hoàn thành thao tác. Cần tách trạng thái **ACCEPTED → PUBLISH_ATTEMPTED → MQTT_PUBLISHED → BUSINESS_ACKNOWLEDGED** khi hệ thống yêu cầu theo dõi tin cậy.

## 13. Backpressure và số lượng topic lớn

Một publisher có thể gửi đến hàng nghìn topic mà chỉ sử dụng một MQTT handler, nhưng tốc độ và độ tin cậy còn phụ thuộc broker, network, QoS, session và subscriber.

- **Topic cardinality:** số lượng device ID/topic khác nhau; cần tránh tạo hàng triệu topic không kiểm soát bởi input rác.
- **Payload size:** không xuất JSON quá lớn hoặc nhúng secrets trong payload.
- **Publish throughput:** tốc độ message/giây, completion latency, số lỗi và retry.
- **Retained state:** retained=true trên mỗi topic có thể tạo nhiều state được broker lưu, tốn tài nguyên.
- **Queue backlog:** nếu dùng queue nội bộ, phải có capacity/poller và cơ chế tồn tại sau restart khi cần.
- **Partitioning:** nếu nhiều instance publish từ cùng outbox, phải claim/partition để hạn chế gửi trùng.

Một `QueueChannel` chỉ lưu message trong RAM mặc định, không biến Spring Integration thành một broker bền vững. Với event quan trọng, sử dụng outbox hoặc persistent message store và định danh sự kiện để replay an toàn.

### 13.1. Transactional outbox khi topic được quyết định động

Nếu DB transaction vừa ghi một sự kiện vừa cần publish MQTT, nên lưu **event ID, payload, schema version và route/topic decision** trong outbox theo một transaction. Worker sau đó đọc outbox và tạo Spring message có `MqttHeaders.TOPIC` được kiểm soát.

Nếu chỉ tính topic dựa trên cấu hình runtime mà không lưu version/routing decision, một event retry sau khi đổi cấu hình có thể đi sang topic khác. Tùy nghiệp vụ, cần lưu **topic cuối cùng đã chọn** hoặc quy tắc phiên bản để replay nhất quán. Khi MQTT publish hoàn tất nhưng worker crash trước khi cập nhật outbox, subscriber vẫn cần dedup event ID.

## 14. Kiểm thử topic mapping không cần MQTT broker

Để kiểm tra logic mà không kết nối broker, tách **flow định tuyến** khỏi **bean MQTT transport**. Trong ví dụ mục 6, `MqttTopicFlowConfiguration` chỉ cần một bean tên `mqttPublisher` kiểu `MessageHandler`. Test có thể cung cấp fake handler cùng tên và quan sát message gửi đến nó.

Thêm dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo `MqttTopicFlowTest.java` trong package `demo.mqtttopics`:

~~~java
package demo.mqtttopics;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        MqttTopicFlowConfiguration.class,
        RecordingPublisherConfiguration.class
})
class MqttTopicFlowTest {

    @Autowired
    @Qualifier("device.events")
    MessageChannel input;

    @Autowired
    RecordingPublisher publisher;

    @BeforeEach
    void reset() {
        publisher.clear();
    }

    @Test
    void stateEventUsesDeviceTopicAndRetainedTrue() {
        DeviceEvent event = new DeviceEvent(
                "evt-test-01", "device-17", "STATE",
                "{\"eventId\":\"evt-test-01\",\"state\":\"ON\"}");

        boolean accepted = input.send(
                MessageBuilder.withPayload(event).build());

        assertTrue(accepted);
        assertEquals(
                List.of(new Published(
                        "devices/device-17/state",
                        event.json(), 1, true)),
                publisher.snapshot());
    }

    @Test
    void commandEventUsesCommandTopicAndRetainedFalse() {
        DeviceEvent event = new DeviceEvent(
                "evt-test-02", "device-21", "COMMAND",
                "{\"eventId\":\"evt-test-02\",\"action\":\"TURN_OFF\"}");

        input.send(MessageBuilder.withPayload(event).build());

        assertEquals(
                List.of(new Published(
                        "devices/device-21/commands",
                        event.json(), 1, false)),
                publisher.snapshot());
    }

    @Test
    void invalidDeviceIdIsRejectedBeforePublish() {
        DeviceEvent event = new DeviceEvent(
                "evt-test-03", "other/tenant", "COMMAND",
                "{\"eventId\":\"evt-test-03\"}");

        assertThrows(IllegalArgumentException.class,
                () -> TopicMessageMapper.toMqttMessage(event));

        assertTrue(publisher.snapshot().isEmpty());
    }
}

record Published(String topic, String payload, int qos,
                 boolean retained) {}

class RecordingPublisher implements MessageHandler {

    private final List<Published> messages =
            new CopyOnWriteArrayList<>();

    @Override
    public void handleMessage(Message<?> message) {
        messages.add(new Published(
                (String) message.getHeaders().get(MqttHeaders.TOPIC),
                (String) message.getPayload(),
                (Integer) message.getHeaders().get(MqttHeaders.QOS),
                (Boolean) message.getHeaders().get(MqttHeaders.RETAINED)));
    }

    List<Published> snapshot() {
        return List.copyOf(messages);
    }

    void clear() {
        messages.clear();
    }
}

@Configuration
class RecordingPublisherConfiguration {

    @Bean(name = "mqttPublisher")
    RecordingPublisher mqttPublisher() {
        return new RecordingPublisher();
    }
}
~~~

Test này không nạp `MqttTransportConfiguration` và không tạo Paho client. Nó chứng minh:

1. Message được gửi vào đúng Spring input channel.
2. `IntegrationFlow` gọi mapper và outbound handler bean đã được inject.
3. `MqttHeaders.TOPIC` thay đổi theo `deviceId` và `kind`.
4. QoS/retained được đặt đúng theo loại publication.
5. Một device ID có dấu `/` bị từ chối trước khi tạo topic.

**Giới hạn:** fake `MessageHandler` chưa chứng minh MQTT broker nhận dữ liệu, converter Paho dùng header thế nào hoặc broker ACL có cho phép topic hay không. Những điểm này cần kiểm thử end-to-end.

### 14.1. Test trực tiếp topic expression

Bên cạnh flow test, nên có unit test cho expression với nhiều giá trị:

~~~java
var expression = new SpelExpressionParser()
        .parseExpression(
                "'devices/' + payload.deviceId() + '/state'");

var source = MessageBuilder.withPayload(
        new DeviceEvent("evt-1", "device-17", "STATE", "{}"))
        .build();

assertEquals("devices/device-17/state",
        expression.getValue(source, String.class));
~~~

Đây là snippet trong ngữ cảnh JUnit có `assertEquals`. Cần test input thiếu ID, ký tự không hợp lệ, key ở tenant khác, kết quả rỗng và rule sửa đổi. **Không dùng expression có dữ liệu chưa validate** làm căn cứ cấp quyền publish.

## 15. Kiểm thử thực với MQTT broker

Khi đã có broker local và Mosquitto CLI, mở subscriber:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -t 'devices/+/state' -v
~~~

Sau đó chạy ứng dụng và gọi `DeviceEventPublisher.publish(...)` với `kind="STATE"`. Subscriber sẽ nhận message trên topic tương ứng nếu broker hoạt động, subscription phù hợp và quyền cho phép.

Để kiểm tra riêng đường retained và topic, có thể publish trực tiếp bằng CLI:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' \
  -q 1 -r \
  -m '{"eventId":"evt-cli-01","state":"ON"}'
~~~

Chạy một subscriber mới trên topic `devices/device-17/state`: broker có thể gửi retained state mới nhất. Với command một lần, không dùng cờ `-r`:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/commands' \
  -q 1 \
  -m '{"commandId":"cmd-cli-01","action":"TURN_OFF"}'
~~~

CLI chỉ hoạt động nếu broker đang chạy tại địa chỉ test và Mosquitto client đã được cài. Với broker có TLS/username/password, cấu hình credentials/chứng chỉ và ACL phù hợp, không tắt bảo mật chỉ để chạy ví dụ.

### 15.1. Những kịch bản cần xác nhận

| Kịch bản | Thử nghiệm | Điều cần quan sát |
| --- | --- | --- |
| Đúng topic từ header | Gửi `STATE` của `device-17`. | Publication tới `devices/device-17/state`. |
| Topic mặc định | Gửi một message không có topic header trong môi trường kiểm soát. | Hiểu rõ nó có dùng default topic hay bị reject; production phải có policy. |
| Topic khác loại event | Gửi `COMMAND`. | Topic `.../commands`, retained=false. |
| Wildcard sai khi publish | Thử đưa `devices/+/state` làm topic. | Không chấp nhận một publish topic chứa wildcard. |
| Header topic không được quyền | Dùng topic vượt broker ACL. | Publish bị từ chối hoặc lỗi được ghi nhận, không đánh dấu thành công. |
| Retained | Publish trạng thái retained và subscribe lại. | Nhận snapshot giữ tại broker; không hiểu nhầm là event mới. |
| Broker offline | Ngắt broker trước khi gửi. | Lỗi/timeout và trạng thái retry, không mất message âm thầm. |
| Duplicate QoS 1 | Gửi lại cùng event ID. | Subscriber/DB không tạo side effect lặp. |
| Replay sau đổi rule | Thay topic mapping rồi retry event cũ. | Hợp đồng về route decision/version được giữ. |
| Nhiều instance publisher | Cùng gửi từ outbox. | Có claim/idempotency, không publish trùng không kiểm soát. |

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Tất cả publication tới một topic cố định. | Không đặt `MqttHeaders.TOPIC` hoặc default topic che mất mapping. | Kiểm tra mapper, header trước handler và default policy. |
| Subscriber không nhận dù Spring handler không báo lỗi. | Sai case/topic, subscription filter khác, broker ACL hoặc subscriber offline. | Kiểm tra topic PUBLISH thực tế, broker logs và subscribe filter. |
| Cố publish tới `devices/+/state` thất bại. | Dùng wildcard subscription trong publish topic. | Tạo topic cụ thể với device ID hợp lệ. |
| Dữ liệu sang nhầm tenant. | Lấy topic trực tiếp từ request/header không đáng tin. | Validate authorization, tạo topic bằng server-side mapping, broker ACL. |
| MQTT nhận đúng topic nguồn nhưng outbound gửi sai. | Nhầm `MqttHeaders.RECEIVED_TOPIC` với `MqttHeaders.TOPIC`. | Tạo topic outbound mới và set header phù hợp. |
| QoS/retained không như dự kiến. | Header vắng mặt/sai kiểu hoặc cấu hình default khác. | Kiểm thử hằng `MqttHeaders.QOS`/`RETAINED` và converter. |
| Expression báo không có thuộc tính. | Root message/payload khác schema; dùng sai accessor. | Unit test SpEL trên đúng DTO và header, validate trước mapping. |
| Gateway gọi publish nhưng chờ reply mãi. | MQTT outbound là adapter một chiều. | Thiết kế ACK inbound flow và correlation ID riêng. |
| Publish thành công nhưng DB/thiết bị có dữ liệu trùng. | Retry sau kết quả chưa chắc chắn, QoS redelivery hoặc publisher tạo hai event. | Idempotency theo event/command ID, unique constraint và đối soát. |
| Queue nội bộ tăng mãi. | Outbound chậm, thiếu poller hoặc chưa giới hạn capacity. | Backpressure, giới hạn tải, outbox/persistent queue và giám sát. |
| Sau restart event đi topic khác. | Rule/tenant mapping thay đổi giữa các lần publish. | Lưu route decision/version khi cần replay nhất quán. |
| Retained command được thực hiện lại. | Lệnh một lần bị publish với retained=true. | Retained=false cho command; dọn retained sai theo quy trình kiểm soát. |

## 17. Bài thực hành: định tuyến topic cho hệ thống nhiều thiết bị

**Bối cảnh:** một ứng dụng nhận sự kiện trạng thái từ SFTP CSV và lệnh từ HTTP API. Sau validation, cả hai loại được publish tới MQTT broker theo topic thiết bị. Thiết bị cập nhật trạng thái và gửi ACK riêng cho command.

Yêu cầu:

1. Định nghĩa `DeviceEvent(eventId, tenantId, deviceId, kind, json)` với `kind = STATE/COMMAND`.
2. Tạo một Spring input channel `mqtt.publish.requests`. Hai inbound flow SFTP và HTTP phải chuẩn hóa message trước khi gửi tới channel đó.
3. Dùng policy xác minh tenant, device ID và quyền người gửi, không lấy nguyên MQTT topic từ HTTP header.
4. Xây topic `tenants/{tenantId}/devices/{deviceId}/state` hoặc `.../commands` theo kind.
5. Đặt `MqttHeaders.TOPIC`, `MqttHeaders.QOS` và `MqttHeaders.RETAINED` đúng loại dữ liệu.
6. Viết một topic expression tương đương và unit test với hợp đồng DTO đã xác nhận.
7. Từ chối topic wildcard, ID có dấu `/`, topic ngoài tenant và các loại event không được hỗ trợ.
8. Cấu hình Paho outbound handler, broker URL/TLS/ACL và Client ID riêng cho mỗi publisher active.
9. Thiết kế outbox lưu routing decision/event ID để khôi phục an toàn khi broker timeout hoặc restart.
10. Subscriber trên broker phải kiểm tra event ID và ACK command qua topic riêng. Viết integration test gửi trùng một command và chứng minh không tạo side effect hai lần.

**Tiêu chí đạt:** topic được tạo từ dữ liệu đã authorize; không có publication sai tenant; state/command có QoS/retained policy rõ; test không broker kiểm tra được topic headers và test broker xác minh đúng topic publish; lưu được nguyên nhân lỗi và replay không thay đổi đích ngoài ý muốn.

## 18. Câu hỏi tự kiểm tra

1. Broker URI, MQTT topic và Spring MessageChannel khác nhau thế nào?
2. MQTT topic publish có dùng được wildcard `+` hoặc `#` không?
3. `MqttHeaders.TOPIC` dùng cho chiều nào của adapter?
4. Khi nhận MQTT inbound, vì sao nên đọc `MqttHeaders.RECEIVED_TOPIC` thay vì tự đoán topic?
5. `setDefaultTopic(...)` hữu ích khi nào, và có rủi ro gì với command?
6. Topic expression có được MQTT broker đánh giá không?
7. Vì sao không nên cho HTTP caller cung cấp một SpEL expression để server thực thi?
8. Khi dùng topic header, bước nào chịu trách nhiệm authorize thiết bị/tenant?
9. Nếu thay `MqttHeaders.TOPIC` bằng header string tự gõ, có rủi ro gì?
10. Topic header có tự truyền Spring `correlationId` qua MQTT v3 không?
11. `MqttHeaders.QOS` và `MqttHeaders.RETAINED` thay đổi gì ở publication?
12. Vì sao retained=true cho command một lần có thể nguy hiểm?
13. Một MQTT QoS 2 message có bảo đảm DB chỉ ghi đúng một lần không?
14. Khi broker timeout nhưng có thể đã nhận publish, retry cần điều kiện gì?
15. Test dùng fake `MessageHandler` kiểm chứng điều gì và còn thiếu điều gì?
16. Khi thay một rule expression, làm sao bảo đảm event đang retry không bị đổi topic?
17. Một outbound handler có thể publish ra nhiều MQTT topics mà không tạo một Spring channel cho mỗi topic không?
18. Khi nào nên dùng Spring router để tách nhiều MQTT outbound handlers?
19. Nếu MQTT subscriber không nhận dù outbound handler trả về không lỗi, phải kiểm tra những lớp nào?
20. Vì sao topic đúng vẫn chưa chứng minh command được thiết bị thực thi?

**Gợi ý:** biểu thức hoặc upstream transformer xác định topic; `MqttHeaders.TOPIC` chuyển quyết định đó cho outbound handler. Giao thức MQTT quyết định publish/delivery; logic bảo mật, ACK và idempotency thuộc hợp đồng của ứng dụng.

## 19. Kết luận

**Topic expression và topic header** giúp MQTT outbound adapter của Spring Integration publish từng message đến đúng topic thay vì gắn cứng một đích. `MqttHeaders.TOPIC` mang topic đã được quyết định; expression SpEL có thể tính topic từ payload/headers, nhưng chỉ nên dùng với dữ liệu đã validate. `setDefaultTopic(...)` phù hợp khi thực sự có topic fallback an toàn. Các header `MqttHeaders.QOS` và `MqttHeaders.RETAINED` bổ sung chính sách delivery và snapshot theo từng publication.

Trong module **SPRING_INTEGRATION_ADAPTERS**, việc định tuyến có thể bắt đầu từ file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu trước khi đến MQTT handler. Hệ thống đáng tin cậy cần phân biệt rõ **Spring channel routing** với **MQTT topic routing**, kiểm tra quyền theo tenant/thiết bị, giữ hợp đồng payload/headers, theo dõi retry/outbox và xác minh MQTT delivery lẫn ACK nghiệp vụ ở downstream.

