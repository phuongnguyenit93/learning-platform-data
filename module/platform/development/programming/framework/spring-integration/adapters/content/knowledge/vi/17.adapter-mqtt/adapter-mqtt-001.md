# MQTT inbound message-driven adapter

## 1. Tổng quan: vì sao MQTT inbound là message-driven?

MQTT (Message Queuing Telemetry Transport) là giao thức publish–subscribe thường dùng khi thiết bị hoặc hệ thống ở biên mạng gửi dữ liệu telemetry, trạng thái cảm biến hay sự kiện đến **MQTT broker**. Một publisher gửi message vào **topic**; broker phân phối message cho các subscriber có subscription phù hợp.

Trong Spring Integration, **MQTT inbound message-driven adapter** tạo một MQTT subscriber, nhận các bản tin do broker đẩy đến qua callback và chuyển chúng thành `Message<?>` để đưa vào `MessageChannel`. Đây là một inbound adapter **theo sự kiện**, không phải một `MessageSource` có `@Poller` đi hỏi broker theo chu kỳ.

Bài này thuộc chương **Adapter MQTT** của module **SPRING_INTEGRATION_ADAPTERS**. Module hướng đến kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành với file, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu và MQTT, đồng thời làm rõ hợp đồng message, lỗi và vòng đời kết nối. Với MQTT, điểm cần hiểu là ranh giới **publisher → broker → MQTT client → Spring message channel → integration flow**.

Sau bài học, người học có thể:

- Phân biệt MQTT **message-driven inbound** với inbound polling adapter của file/JDBC/SFTP.
- Giải thích topic, subscription wildcard, client ID, QoS, retained message, session và reconnect.
- Tạo `MqttPahoMessageDrivenChannelAdapter` dùng `MqttPahoClientFactory` và đưa message vào channel.
- Chuyển tiếp payload/headers đến `IntegrationFlow`, định dạng JSON hoặc phân tuyến theo topic.
- Thiết kế xử lý lỗi, trùng lặp, backpressure, bảo mật, xác nhận xử lý và lifecycle.
- Kiểm thử flow mà không cần broker; sau đó kiểm thử thật với một MQTT broker thử nghiệm.

**Điểm cốt lõi:** MQTT broker có thể giao bản tin cho client, nhưng điều đó **không đồng nghĩa** dữ liệu đã được ghi thành công vào database hoặc hệ thống đích của ứng dụng. Cần phân biệt MQTT QoS với bảo đảm xử lý nghiệp vụ.

## 2. Luồng xử lý từ broker đến Spring Integration

~~~mermaid
flowchart LR
    DEV["Cảm biến / Publisher"]
    BROKER[("MQTT broker")]
    PAHO["MQTT Paho client<br/>subscribe topic filter"]
    ADAPTER["MqttPahoMessageDrivenChannelAdapter<br/>message-driven callback"]
    CH["mqtt.telemetry.in<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>validate / transform / route"]
    HANDLER["Service activator<br/>hoặc outbound adapter"]
    DB[("Database / hệ thống đích")]
    DEV -->|"PUBLISH topic + payload"| BROKER
    BROKER -->|"DELIVER theo subscription"| PAHO
    PAHO --> ADAPTER
    ADAPTER -->|"Message<?>"| CH
    CH --> FLOW --> HANDLER --> DB
~~~

Các vai trò được phân chia như sau:

| Thành phần | Trách nhiệm | Điều không đảm bảo |
| --- | --- | --- |
| Publisher | Tạo bản tin với topic, payload, QoS, retained flag. | Không biết handler Spring đã xử lý xong. |
| MQTT broker | Phân phối message tới subscription theo session/QoS. | Không quản lý transaction của database trong ứng dụng. |
| Paho MQTT client | Thiết lập kết nối, subscribe, nhận callback. | Không tự quyết định DTO nghiệp vụ. |
| `MqttPahoMessageDrivenChannelAdapter` | Chuyển MQTT delivery thành Spring message. | Không tự parse tất cả schema JSON hoặc xử lý side effect. |
| `MessageChannel` | Bàn giao message tới flow. | Không mặc nhiên lưu bền vững hoặc tạo consumer. |
| `IntegrationFlow` | Validate, transform, route, gọi handler. | Không tự đổi MQTT QoS thành exactly-once nghiệp vụ. |
| Handler/outbound adapter | Ghi DB, gửi HTTP/JMS/Kafka, lưu file. | Không tự tránh duplicate nếu thiếu thiết kế. |

Khi khởi động, inbound adapter tạo hoặc sử dụng client của factory, kết nối broker rồi đăng ký các topic filter. Khi broker giao message phù hợp, callback của client được adapter chuyển thành Spring `Message<?>` và gửi vào channel đã cấu hình. **Không cần `@Poller`** cho bước nhận MQTT message-driven.

## 3. Những khái niệm MQTT phải hiểu trước khi cấu hình adapter

### 3.1. Topic, topic filter và wildcard

Một MQTT publisher gửi dữ liệu đến **topic cụ thể**, ví dụ:

~~~text
sensors/room-17/temperature
sensors/room-17/humidity
sensors/room-21/temperature
~~~

Một subscriber có thể đăng ký **topic filter** với wildcard:

| Subscription filter | Ý nghĩa | Ví dụ phù hợp |
| --- | --- | --- |
| `sensors/room-17/temperature` | Chỉ nhận topic đúng tên. | `sensors/room-17/temperature`. |
| `sensors/+/temperature` | `+` khớp đúng **một cấp** topic. | `sensors/room-21/temperature`. |
| `sensors/#` | `#` khớp nhiều cấp còn lại; phải nằm cuối filter. | `sensors/room-17/temperature`, `sensors/room-17/humidity`. |
| `devices/+/state` | Nhận state của từng device ở một cấp. | `devices/device-42/state`. |

Wildcard là ký hiệu **đăng ký subscribe**, không phải cách đặt tên một topic để publisher gửi bản tin. Với dữ liệu thiết bị, hãy thiết kế tên topic có quy tắc, giới hạn subscription thật cần thiết và tránh subscribe quá rộng khiến ứng dụng bị ngập message không liên quan.

### 3.2. MQTT QoS không phải số lần xử lý nghiệp vụ

| QoS | Delivery giữa MQTT client và broker | Hệ quả với Spring Integration |
| --- | --- | --- |
| **0 — at most once** | Giao tối đa một lần ở tầng MQTT, không có cơ chế xác nhận delivery tương ứng QoS 1/2. | Có thể mất message khi mất mạng hoặc consumer không kịp nhận. |
| **1 — at least once** | Cơ chế xác nhận cho phép giao lại để tăng khả năng delivery. | Ứng dụng cần xử lý duplicate, ví dụ theo `eventId`. |
| **2 — exactly once (MQTT protocol)** | Giao thức dùng handshake để tránh xử lý lặp một MQTT publication theo cơ chế QoS 2. | **Không** đồng nghĩa transaction database/HTTP ở downstream chỉ xảy ra một lần. |

QoS hiệu lực của delivery phụ thuộc QoS bản tin publish và subscription, cùng quy định broker/client. Trong ví dụ `setQos(1)` thiết lập QoS subscription, **không ép publisher bắt buộc phát ở QoS 1**.

Nếu publisher gửi cùng một sự kiện nghiệp vụ hai lần với hai lần publish khác nhau, QoS 2 vẫn không thay thế idempotency ở service xử lý.

### 3.3. Client ID, clean session và retained message

- **Client ID** nhận diện một MQTT client session tại broker. Nhiều instance cùng dùng một Client ID có thể đẩy nhau ra khỏi kết nối hoặc gây hành vi reconnect không ổn định; đặt ID duy nhất cho từng client đang hoạt động.
- Trong MQTT 3.1.1/Paho v3, `cleanSession=false` cho phép sử dụng session bền hơn tại broker khi broker hỗ trợ, thường kết hợp Client ID ổn định và QoS 1/2. Nó **không** tự tạo checkpoint cho database của ứng dụng.
- **Retained message** là bản tin gần nhất được broker giữ trên một topic khi publisher đặt retained flag. Subscriber mới có thể nhận bản tin retained ngay khi subscribe, dù đó không phải telemetry mới được tạo.
- **Last Will and Testament (LWT)** là thông điệp được cấu hình để broker phát khi client mất kết nối bất thường theo điều kiện giao thức; đây là cơ chế MQTT, không phải exception handler của Spring.

**Thiết kế ID và session theo cách triển khai:** nếu hai instance cần nhận **cùng mọi sự kiện** như hai subscriber độc lập, mỗi instance cần Client ID riêng và subscription phù hợp. Nếu mục tiêu là chia tải một stream, đừng coi việc dùng chung Client ID như một nhóm competing consumers an toàn; cân nhắc shared subscription theo phiên bản broker/giao thức hoặc kiến trúc hàng đợi phù hợp.

## 4. Cấu hình Spring Boot và dependency MQTT

Với Java 17+, Spring Boot và Spring Integration theo dependency management của Boot, dùng:

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

`spring-integration-mqtt` cung cấp các endpoint MQTT dựa trên Eclipse Paho, trong đó có `MqttPahoMessageDrivenChannelAdapter`. Ví dụ bên dưới dùng **Paho MQTT v3 API** (`org.eclipse.paho.client.mqttv3.MqttConnectOptions`) và MQTT 3.1.1; đừng nhầm các lớp này với MQTT v5 API/adapter của phiên bản khác.

Các class cốt lõi:

~~~java
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
~~~

Khi triển khai thực, broker URL, username, password, client ID và topics phải đến từ cấu hình môi trường hoặc secret management, không hardcode credential vào source code.

### 4.1. Thuộc tính cấu hình ví dụ

Tạo `src/main/resources/application.properties`:

~~~properties
app.mqtt.broker-url=tcp://localhost:1883
app.mqtt.client-id=telemetry-inbound-local-1
app.mqtt.topic=sensors/+/temperature
~~~

Cấu hình trên giả định có một **broker thử nghiệm** lắng nghe ở máy local trên cổng 1883. Nó không tự khởi động broker. Với môi trường thật, phải cấu hình broker đã có, xác thực và TLS thay vì dùng kết nối TCP không mã hóa khi truyền dữ liệu qua mạng không tin cậy.

## 5. Ví dụ chạy được: MQTT inbound adapter → channel → processing flow

Ví dụ này nhận telemetry dạng JSON ở topic `sensors/+/temperature`. Để tập trung vào inbound adapter, handler **chưa parse JSON**, mà ghi lại payload dạng `String` và topic nhận được. Có thể bổ sung Jackson transformer và validator ở bước tiếp theo.

Tổ chức mã:

~~~text
src/main/java/demo/mqtt/
    MqttInboundApplication.java
    MqttTransportConfiguration.java
    TelemetryFlowConfiguration.java
    TelemetrySink.java

src/main/resources/
    application.properties
~~~

Các class trong snippets bên dưới thuộc package `demo.mqtt`.

### 5.1. Application bootstrap

~~~java
package demo.mqtt;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttInboundApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttInboundApplication.class, args);
    }
}
~~~

Spring Boot sẽ scan các `@Configuration` trong package ứng dụng. Spring Integration quản lý bean adapter cùng các endpoint sau khi application context khởi tạo.

### 5.2. MQTT client factory và inbound adapter

~~~java
package demo.mqtt;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.messaging.MessageChannel;

@Configuration
class MqttTransportConfiguration {

    @Bean
    MqttPahoClientFactory mqttClientFactory(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {

        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(false);

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter mqttInboundAdapter(
            MqttPahoClientFactory mqttClientFactory,
            @Qualifier("mqtt.telemetry.in") MessageChannel inputChannel,
            @Value("${app.mqtt.client-id}") String clientId,
            @Value("${app.mqtt.topic}") String topicFilter) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, mqttClientFactory, topicFilter);

        adapter.setQos(1);
        adapter.setCompletionTimeout(5000);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(inputChannel);
        return adapter;
    }
}
~~~

Phân tích từng thành phần:

1. `MqttConnectOptions` xác định broker, thời gian kết nối, keepalive và session. Với production cần bổ sung authentication/TLS; không dùng `cleanSession=false` như một phương án thay thế lưu sự kiện bền vững.
2. `DefaultMqttPahoClientFactory` tạo client theo options để adapter sử dụng. Tách factory thành bean giúp tái sử dụng cấu hình kết nối có kiểm soát.
3. `MqttPahoMessageDrivenChannelAdapter` là **inbound message-driven endpoint**, đăng ký subscribe theo topic filter. Nó không gọi `receive()` từ một `@Poller`.
4. `setQos(1)` là QoS subscription; `setCompletionTimeout(5000)` và `setRecoveryInterval(10000)` điều chỉnh một số giới hạn chờ/phục hồi của adapter theo API phiên bản đang dùng.
5. `DefaultPahoMessageConverter` chuyển MQTT message thành Spring `Message<?>`. Trong cấu hình mặc định thường nhận payload text dạng `String`; nếu cần binary, phải chọn converter phù hợp và đổi hợp đồng downstream.
6. `setOutputChannel(inputChannel)` chỉ ra nơi adapter **phát message** vào Spring Integration. Tên bean channel là `mqtt.telemetry.in`; inbound adapter không có input channel nội bộ theo nghĩa message từ flow.

**Bảo mật:** demo không khai báo username/password vì broker local có thể được cấu hình thử nghiệm riêng. Với broker yêu cầu xác thực, nạp secrets từ môi trường và cấu hình `MqttConnectOptions` (username, password/TLS socket factory). Đừng đưa mật khẩu vào log, source control hoặc ví dụ lệnh shell dùng trong production.

### 5.3. Channel, IntegrationFlow và handler

~~~java
package demo.mqtt;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class TelemetryFlowConfiguration {

    @Bean(name = "mqtt.telemetry.in")
    MessageChannel mqttTelemetryInput() {
        return new DirectChannel();
    }

    @Bean
    TelemetrySink telemetrySink() {
        return new TelemetrySink();
    }

    @Bean
    IntegrationFlow telemetryFlow(TelemetrySink sink) {
        return IntegrationFlow.from("mqtt.telemetry.in")
                .handle(String.class, (payload, headers) -> {
                    Object topic = headers.get(MqttHeaders.RECEIVED_TOPIC);
                    sink.accept(new ReceivedTelemetry(
                            topic == null ? "unknown" : topic.toString(),
                            payload));
                    return null; // flow inbound một chiều
                })
                .get();
    }
}
~~~

Thành phần ghi nhận dữ liệu cho demo:

~~~java
package demo.mqtt;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

record ReceivedTelemetry(String topic, String payload) {}

class TelemetrySink {

    private final List<ReceivedTelemetry> received =
            new CopyOnWriteArrayList<>();

    void accept(ReceivedTelemetry telemetry) {
        received.add(telemetry);
        System.out.println("MQTT received: " + telemetry.topic());
    }

    List<ReceivedTelemetry> snapshot() {
        return List.copyOf(received);
    }

    void clear() {
        received.clear();
    }
}
~~~

Spring Integration nhận MQTT message, chuyển payload sang `String` và gắn metadata vào headers. Handler lấy `MqttHeaders.RECEIVED_TOPIC` để biết topic gốc được broker giao tới, rồi ghi nhận dữ liệu. Tên/kiểu header của thư viện phụ thuộc API đang dùng; trong mã Java nên dùng hằng `MqttHeaders` thay cho tự đoán chuỗi header.

Với `DirectChannel`, handler được gọi theo cơ chế đồng bộ của channel ở phía Spring; vì callback MQTT cũng có những ràng buộc về thread/ack của client, đừng đặt một lời gọi HTTP hoặc truy vấn database không giới hạn thời gian trực tiếp trên đường callback.

### 5.4. Luồng dữ liệu mẫu

Publisher gửi:

~~~text
Topic: sensors/room-17/temperature
QoS:   1
Payload:
{"deviceId":"room-17","celsius":26.5,"eventId":"evt-1001"}
~~~

Ứng dụng nhận thành một Spring message có payload và metadata tương ứng:

~~~text
Message<String>
  payload = "{\"deviceId\":\"room-17\",\"celsius\":26.5,\"eventId\":\"evt-1001\"}"
  headers:
    mqtt_receivedTopic: "sensors/room-17/temperature"
    ... metadata MQTT khác tùy converter/phiên bản ...
~~~

Trong ví dụ, `TelemetrySink` ghi nhận `ReceivedTelemetry(topic, payload)`. Không nên tự tuyên bố JSON đã được validate chỉ vì payload text đi tới handler. Để kiểm tra nghiệp vụ, thêm transformer parse JSON, validate schema và đưa message lỗi vào kênh quarantine có chủ đích.

## 6. MQTT inbound khác inbound polling adapter

MQTT inbound thường được mô tả là **message-driven** vì broker phát bản tin cho subscriber theo kết nối đang hoạt động. Ngược lại, một inbound adapter đọc file hoặc database thường cần poller gọi `MessageSource.receive()`.

| Tiêu chí | MQTT message-driven inbound | File/JDBC polling inbound |
| --- | --- | --- |
| Nguồn kích hoạt | MQTT client nhận callback khi broker giao bản tin. | Poller chủ động gọi source theo lịch. |
| Bắt buộc có `@Poller`? | **Không**. | Thông thường **có** với `MessageSource`. |
| Cấu hình chính | Broker, Client ID, topic filter, QoS, session, reconnect. | Source, directory/query, filter/checkpoint, poll interval. |
| Đường message | Broker → Paho callback → adapter → output channel. | Scheduler → source.receive() → adapter → output channel. |
| Tốc độ đến | Phụ thuộc publisher/broker và tình trạng kết nối. | Phụ thuộc tần suất poll và giới hạn mỗi lượt. |
| Khôi phục sau mất mạng | MQTT session/QoS và broker policy. | Checkpoint/metadata của source và retry. |
| Lỗi xử lý nghiệp vụ | Cần error flow, replay, idempotency. | Cũng cần error flow, replay, idempotency. |

Nếu nghiệp vụ yêu cầu cập nhật mỗi 5 giây, không có nghĩa phải dùng poller đọc MQTT. Có thể publisher tự gửi theo lịch của thiết bị, còn MQTT inbound adapter vẫn tiếp nhận **theo callback**.

## 7. Metadata MQTT: topic, QoS, retained và duplicate

Khi MQTT message vào Spring Integration, **headers** có thể mang metadata giúp routing hoặc kiểm tra replay. Với Paho inbound, cần phân biệt header của **bản tin nhận được** với header dùng khi ứng dụng **publish** ra ngoài.

| Metadata | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| Received topic | Topic cụ thể đã nhận, dù subscription dùng wildcard. | Định tuyến theo thiết bị/loại telemetry. |
| Received QoS | QoS mà MQTT client nhận bản tin. | Quan sát delivery policy; không chứng minh DB đã ghi. |
| Retained | Broker đánh dấu bản tin retained. | Tránh nhầm snapshot trạng thái ban đầu với event mới. |
| Duplicate flag | MQTT protocol đánh dấu bản tin có khả năng giao lại. | Hỗ trợ quan sát, **không đủ** để deduplicate nghiệp vụ. |
| Correlation/business ID | Trường ứng dụng tự gắn trong payload/header sau parse. | Idempotency, tracing và đối soát. |

Một routing rule theo topic có thể chuyển:

~~~text
sensors/+/temperature  -> telemetry.temperature
sensors/+/humidity     -> telemetry.humidity
devices/+/state        -> telemetry.deviceState
~~~

Nếu muốn parse tên device từ topic, hãy xác thực số cấp topic và ký tự hợp lệ trước khi dùng làm tenant hoặc database key. Không tin một topic string do publisher kiểm soát như bằng chứng publisher được phép gửi dữ liệu cho tenant đó; quyền cần được áp dụng tại broker ACL và tầng nghiệp vụ.

### 7.1. Retained message không phải event mới

Giả sử broker giữ retained payload nhiệt độ gần nhất cho `sensors/room-17/temperature`. Khi adapter khởi động và subscribe, broker có thể chuyển retained message ngay cả khi sensor chưa gửi bản tin mới. Nếu downstream cộng dồn số sự kiện hoặc gửi cảnh báo mỗi lần nhận, cần xét retained flag và `eventId`/timestamp.

Với dữ liệu **state snapshot**, retained thường có ý nghĩa hữu ích; với dữ liệu **transaction/event phát sinh một lần**, cần quy định rõ có được retained hay không.

### 7.2. Duplicate flag không thay idempotency key

Một sự kiện nghiệp vụ có thể xuất hiện lặp do publisher retry, mạng mất phản hồi, broker redelivery hoặc ứng dụng chạy lại. Không thể chống trùng chỉ bằng kiểm tra cờ MQTT duplicate vì hai lần publish độc lập có thể mang cùng nội dung nhưng không bị đánh dấu duplicate theo protocol.

Tốt hơn, payload telemetry có trường `eventId` duy nhất do publisher sinh; phía đích lưu trạng thái đã xử lý theo `eventId` kết hợp thiết bị/tenant khi phù hợp.

## 8. Topic filter động và điều phối subscription

Một adapter có thể subscribe một hoặc nhiều topic filter. Với Paho adapter, danh sách topic được khai báo khi tạo endpoint, và một số phiên bản hỗ trợ thay đổi subscription khi adapter đang chạy.

Ví dụ cấu hình tĩnh:

~~~java
new MqttPahoMessageDrivenChannelAdapter(
        "telemetry-consumer-a",
        mqttClientFactory,
        "sensors/+/temperature",
        "sensors/+/humidity");
~~~

Hai subscription này đều chuyển vào **cùng output channel** nếu dùng cùng inbound adapter. Downstream có thể dùng received-topic để route đến flow khác nhau.

Nếu subscribe quá nhiều topic filter trùng nhau hoặc cho phép wildcard rộng, broker có thể giao khối lượng message lớn hơn dự kiến. Đừng xem topic filter là biện pháp xác thực: quyền publish/subscribe cần được giới hạn bằng ACL, principal và cấu hình broker.

### 8.1. Sử dụng channel chung và router

~~~mermaid
flowchart TD
    B["MQTT broker"]
    A["Paho inbound adapter<br/>topics: sensors/+/temperature, sensors/+/humidity"]
    CH["mqtt.telemetry.in"]
    R{"Router theo received topic"}
    T["telemetry.temperature"]
    H["telemetry.humidity"]
    ET["Temperature handler"]
    EH["Humidity handler"]
    B --> A --> CH --> R
    R -->|"*/temperature"| T --> ET
    R -->|"*/humidity"| H --> EH
~~~

Nếu nhiều topic mang **schema payload khác nhau**, nên route **trước hoặc ngay khi parse** dựa trên topic, sau đó chọn converter/validator phù hợp. Một transformer mặc định nhận `String` không biết tự phân biệt `TemperatureReading` với `HumidityReading` nếu chưa có rule.

## 9. Xử lý lỗi khi nhận MQTT message

Lỗi có thể xảy ra ở nhiều giai đoạn:

~~~mermaid
flowchart TD
    PUB["Publisher"]
    BROKER["Broker"]
    CLIENT["Paho / Inbound adapter"]
    FLOW["MessageChannel / IntegrationFlow"]
    DB["Database / outbound"]
    FAIL["Error flow / quarantine / retry"]
    PUB --> BROKER --> CLIENT --> FLOW --> DB
    CLIENT -. "mất kết nối / chuyển đổi lỗi" .-> FAIL
    FLOW -. "schema / dispatch lỗi" .-> FAIL
    DB -. "timeout / transaction thất bại" .-> FAIL
~~~

| Nhóm lỗi | Ví dụ | Chính sách xử lý |
| --- | --- | --- |
| Kết nối MQTT | Broker ngắt, DNS/TLS lỗi, client ID xung đột. | Recovery/reconnect, cảnh báo và giới hạn thời gian mất kết nối. |
| Subscribe | Không có quyền topic, topic filter sai, broker từ chối. | Sửa ACL/config; không retry vô hạn với cấu hình sai. |
| Converter/payload | Byte không hợp lệ, JSON sai schema, payload quá lớn. | Quarantine và báo lỗi có ID; không coi là sự cố broker. |
| Message channel | Không có consumer, downstream chậm hoặc queue đầy. | Kiểm tra topology, backpressure và error flow. |
| Handler nghiệp vụ | DB unavailable, HTTP timeout, lỗi validation. | Retry có giới hạn, idempotency, compensation khi cần. |
| Kết quả không chắc chắn | DB đã ghi nhưng client xử lý bị ngắt trước khi hoàn tất. | Đối soát transaction/ID để tránh duplicate. |

### 9.1. Spring error channel không phải MQTT dead-letter queue

Spring Integration có thể phát `ErrorMessage` sang error channel ở các vị trí được cấu hình hỗ trợ. MQTT v3 không có một **dead-letter queue chuẩn** giống cách một số broker queue triển khai. Nếu cần giữ message sai để xử lý lại, ứng dụng phải chủ động lưu vào database, file quarantine hoặc publish sang một **topic lỗi** theo thiết kế, với giới hạn retry và kiểm soát vòng lặp.

Không cho message lỗi quay lại cùng topic nguồn vô hạn; cần phân biệt số lần thử, lỗi có thể khôi phục và lỗi schema không thể khôi phục.

### 9.2. Error path và acknowledgements

Việc MQTT protocol xác nhận delivery không tương đương việc integration flow ghi database thành công. Tùy chế độ adapter, converter, channel và phiên bản, thời điểm xác nhận ở MQTT có thể khác thời điểm nghiệp vụ hoàn tất.

Nếu yêu cầu gắn acknowledgement với quá trình xử lý, cần nghiên cứu **manual acknowledgement** của adapter/Paho theo đúng phiên bản đang dùng và kiểm thử disconnect/crash thực tế. Đừng suy ra mặc định khi một handler ném exception thì broker chắc chắn phát lại đúng message cho tới khi DB ghi thành công.

## 10. Backpressure, thread và channel

MQTT có thể nhận message nhanh hơn tốc độ xử lý ở database hoặc HTTP client. Kiểu `MessageChannel` nối adapter với downstream ảnh hưởng lớn đến thread và rủi ro quá tải.

| Channel | Hành vi điển hình | Cần quan tâm |
| --- | --- | --- |
| `DirectChannel` | Handler chạy đồng bộ trên thread gửi từ adapter vào channel. | Handler blocking làm chậm callback/delivery; lỗi có thể lan theo call stack. |
| `ExecutorChannel` | Chuyển sang thread pool. | Giới hạn pool/queue, rejection, error channel và shutdown. |
| `QueueChannel` | Đưa message vào hàng đợi để endpoint sau poll. | Capacity, poller, persistence, retry và backlog. |
| `PublishSubscribeChannel` | Gửi tới nhiều consumer. | Lỗi một nhánh, duplicate side effect, ordering. |

Ví dụ demo dùng `DirectChannel` vì handler chỉ ghi một bản ghi nhỏ vào RAM. Không nên thay `TelemetrySink` bằng lời gọi database/HTTP không timeout mà vẫn nghĩ MQTT callback sẽ không chịu ảnh hưởng.

Một phương án tách xử lý có giới hạn:

~~~mermaid
flowchart LR
    A["MQTT inbound adapter"]
    Q["telemetry.buffered<br/>QueueChannel(capacity=1000)"]
    P["Polling consumer<br/>maxMessagesPerPoll"]
    V["Validate / Transform"]
    H["DB / outbound handler"]
    A --> Q --> P --> V --> H
~~~

Đây là một **quyết định kiến trúc**: nếu dùng `QueueChannel`, phải có polling consumer và cơ chế bảo vệ khi queue đầy. Queue bộ nhớ mặc định **không bền qua restart**. Nếu cần lưu dữ liệu đáng tin cậy trước khi ack/ghi đích, xem xét persistent message store, broker pipeline hoặc outbox và kiểm chứng end-to-end.

### 10.1. Thứ tự message

MQTT có những quy tắc thứ tự trong từng kết nối/QoS nhưng hệ thống ứng dụng có thể mất thứ tự quan sát khi xử lý song song qua executor, nhiều instance, retry hoặc nhiều topic. Nếu dữ liệu cảm biến phụ thuộc trình tự, thêm `sequenceNumber` hoặc `eventTime` trong payload, sau đó xác định cách xử lý bản ghi đến muộn/trùng và mức độ sắp xếp cần thiết.

## 11. Vòng đời: start, stop, reconnect và triển khai nhiều instance

`MqttPahoMessageDrivenChannelAdapter` là một endpoint do Spring quản lý. Khi context khởi tạo, adapter có thể tự start, mở kết nối MQTT và subscribe topic. Khi dừng, nó phải hủy/đóng tài nguyên phù hợp và ngừng nhận message mới theo lifecycle của framework/client.

Những trường hợp cần kiểm tra:

1. **Broker chưa sẵn sàng khi startup:** chính sách adapter khi không kết nối được và các lần phục hồi.
2. **Mạng ngắt trong lúc chạy:** client reconnect, subscription/session còn hiệu lực hay cần đăng ký lại.
3. **Client ID bị trùng:** hai instance đăng nhập với cùng ID gây mất kết nối lẫn nhau.
4. **Thay subscription:** topic filter thay đổi có tác động đến tải và dữ liệu bị bỏ sót hay không.
5. **Shutdown:** message đang trong xử lý, queue nội bộ, tài nguyên thread và kết nối được giải phóng thế nào.
6. **Nâng cấp phiên bản client/broker:** khả năng tương thích MQTT protocol, TLS, retained và session persistence.

### 11.1. Clean session và dữ liệu lúc offline

Với MQTT 3.1.1, nếu cần broker giữ subscription và một số message QoS 1/2 khi client tạm offline, thường phải dùng **Client ID ổn định** và `cleanSession=false` cùng sự hỗ trợ/cấu hình broker. Điều này không có nghĩa broker giữ message vô hạn hoặc dữ liệu sẽ không mất khi ổ đĩa broker đầy.

Trường hợp ứng dụng scale ngang với nhiều instance độc lập, mỗi instance phải có định danh và mô hình subscription thích hợp. Không dùng cùng Client ID như cơ chế load balancing tự động. Nếu broker hỗ trợ **shared subscriptions**, cần kiểm tra cú pháp và semantics đúng phiên bản/protocol/broker; đây không phải hành vi mặc định của topic subscription thông thường.

### 11.2. Giám sát adapter

Theo dõi ít nhất:

- Trạng thái kết nối và số lần reconnect.
- Số message được nhận theo topic/QoS, độ trễ từ eventTime đến lúc xử lý.
- Lỗi converter, validation, dispatch và handler theo nhóm.
- Queue depth, thời gian xử lý và số message retry/quarantine.
- Số message trùng theo `eventId`; retained messages và sự kiện đến muộn.
- Thời gian không nhận message của thiết bị khi dự kiến có heartbeat.

Không log nguyên payload có thông tin nhạy cảm hoặc secret từ headers. Dùng correlation ID, topic đã được kiểm tra và device ID để truy vết khi cần.

## 12. Bảo mật MQTT inbound

MQTT thường mang dữ liệu từ thiết bị ở môi trường không tin cậy. Thiết kế adapter cần tính đến:

| Rủi ro | Biện pháp |
| --- | --- |
| Kết nối MQTT không mã hóa | Dùng TLS (`ssl://...` hoặc cấu hình kết nối thích hợp), xác thực chứng chỉ broker. |
| Credentials lộ | Nạp qua secret manager/env; không hardcode hoặc log password. |
| Subscribe vượt quyền | ACL topic trên broker theo principal/client; chỉ subscribe tối thiểu. |
| Publisher giả mạo topic/device ID | Xác thực publisher tại broker, ràng buộc quyền topic và validate device ID trong payload. |
| Payload độc hại/quá lớn | Giới hạn kích thước, validate JSON/schema, giới hạn thời gian parse. |
| Bản tin trùng hoặc replay | `eventId`, timestamp, chống lặp tại đích, kiểm tra độ mới nếu nghiệp vụ yêu cầu. |
| Quá tải consumer | Capacity/backpressure, monitoring, giới hạn concurrency, có chiến lược bỏ/giữ dữ liệu rõ ràng. |

Đừng dựa vào `MqttHeaders.RECEIVED_TOPIC` như bằng chứng duy nhất rằng publisher được ủy quyền. Topic là metadata giao thức; xác thực và quyền truy cập phải được áp dụng ở broker và ứng dụng theo mô hình tin cậy.

## 13. Kiểm thử flow mà không cần MQTT broker

Phần lớn logic sau adapter nên được kiểm tra độc lập với broker. Vì `TelemetryFlowConfiguration` ở mục 5 chỉ khai báo channel và downstream handler, ta có thể khởi động **Spring Integration test context** riêng chứa class đó, không nạp `MqttTransportConfiguration`. Nhờ vậy test không thử kết nối network.

Thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo `TelemetryFlowTest.java` trong package `demo.mqtt`:

~~~java
package demo.mqtt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = TelemetryFlowConfiguration.class)
class TelemetryFlowTest {

    @Autowired
    @Qualifier("mqtt.telemetry.in")
    MessageChannel input;

    @Autowired
    TelemetrySink sink;

    @BeforeEach
    void reset() {
        sink.clear();
    }

    @Test
    void routesReceivedPayloadAndTopicToSink() {
        String json = "{\"deviceId\":\"room-17\",\"celsius\":26.5}";

        boolean sent = input.send(
                MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "sensors/room-17/temperature")
                        .build());

        assertTrue(sent);
        assertEquals(
                List.of(new ReceivedTelemetry(
                        "sensors/room-17/temperature", json)),
                sink.snapshot());
    }
}
~~~

Test này xác minh:

- Bean `mqtt.telemetry.in` tồn tại và có consumer.
- `IntegrationFlow` nhận message chứa payload `String`.
- Header topic được đưa vào `TelemetrySink`.
- Xử lý đồng bộ qua `DirectChannel` hoàn tất trước khi assert.

**Giới hạn:** test không kiểm tra Paho client kết nối, subscribe, QoS, retained flag, reconnect hoặc khả năng xử lý duplicate từ broker. Muốn kiểm chứng các đặc tính đó, phải có **integration test với broker thật** (local container/test environment) và một publisher độc lập.

## 14. Kiểm thử với broker MQTT thử nghiệm

Khi có broker local phù hợp đã cấu hình cho môi trường thử nghiệm, có thể dùng CLI `mosquitto_pub` để phát message:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'sensors/room-17/temperature' \
  -q 1 \
  -m '{"deviceId":"room-17","celsius":26.5,"eventId":"evt-1001"}'
~~~

Đoạn lệnh trên chỉ hoạt động nếu:

- Một broker MQTT đang chạy tại `localhost:1883` và cho phép client kiểm thử kết nối phù hợp.
- Ứng dụng dùng đúng broker URL, Client ID và topic filter.
- CLI `mosquitto_pub` đã được cài.
- Trường hợp broker yêu cầu username/password/TLS, lệnh và cấu hình ứng dụng được chỉnh đúng; đừng tắt bảo mật broker production để chạy demo.

Quan sát log `MQTT received: sensors/room-17/temperature`. Thay topic bằng `sensors/room-17/humidity`: nếu chỉ subscribe `sensors/+/temperature`, adapter sẽ không nhận message humidity.

### 14.1. Các test cần có khi kiểm tra end-to-end

| Thử nghiệm | Cách làm | Kết quả cần quan sát |
| --- | --- | --- |
| Topic phù hợp | Publish vào `sensors/room-17/temperature`. | Inbound nhận payload/topic đúng. |
| Topic không phù hợp | Publish vào `sensors/room-17/humidity`. | Subscription temperature không nhận nó. |
| QoS 1 / duplicate | Gửi hoặc mô phỏng redelivery cùng `eventId`. | Handler đích không tạo side effect lặp. |
| Retained | Publish retained, restart subscriber/subscribe lại. | Nhận diện đây là state snapshot, không đếm sai sự kiện mới. |
| Broker disconnect | Ngắt kết nối, chờ recovery, kết nối lại. | Kết nối/subscription phục hồi theo policy; không khẳng định không mất data. |
| Restart ứng dụng | Giữ/đổi Client ID và clean session theo kịch bản. | Kiểm tra session/QoS và dữ liệu offline theo broker policy. |
| Downstream lỗi | Cho handler throw exception hoặc DB không sẵn sàng. | Error flow/retry được quan sát, message không bị âm thầm mất. |
| High throughput | Publish nhanh hơn tốc độ handler. | Có backpressure/queue limit và metric; không cạn tài nguyên. |

Không chỉ kiểm tra log “received” rồi kết luận thành công: phải xác nhận trạng thái cuối ở database hoặc hệ thống đích nếu integration flow có side effect thật.

## 15. Những lỗi phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Không nhận MQTT message. | Broker URL sai, topic filter không khớp, ACL từ chối subscribe, client chưa start. | Kiểm tra connectivity, broker logs, subscription và lifecycle. |
| Hai instance liên tục disconnect. | Cùng Client ID đang được sử dụng. | Cấp Client ID duy nhất cho từng client active. |
| Nhận lại bản tin sau reconnect. | QoS/redelivery, session hoặc retained message. | Xem topic/QoS/retained, thêm idempotency theo eventId. |
| Không thấy message ở handler. | Adapter gửi sai channel hoặc channel không có consumer. | Kiểm tra `setOutputChannel(...)` và `IntegrationFlow.from(...)`. |
| JSON lỗi nhưng log vẫn thấy MQTT received. | Handler hiện chỉ nhận text, chưa parse/validate JSON. | Thêm JSON transformer và validation/quarantine. |
| Lỗi MQTT đã hết nhưng DB không có dữ liệu. | Xác nhận delivery protocol khác xác nhận xử lý nghiệp vụ. | Kiểm tra transaction/retry tại handler và trạng thái đích. |
| MQTT callback chậm, broker ngắt kết nối. | Downstream blocking, không giới hạn timeout, quá tải. | Giới hạn handler latency hoặc tách queue/executor có backpressure. |
| QoS 2 vẫn xuất hiện duplicate nghiệp vụ. | Publisher phát trùng sự kiện hoặc retry side effect. | Dùng stable eventId, unique constraint/idempotency. |
| Message mất sau restart. | Queue trong RAM, session không bền hoặc broker không giữ dữ liệu. | Kiểm tra clean session, Client ID, QoS và persistent storage. |
| Gặp retained payload cũ. | Broker gửi retained message khi subscribe. | Dùng retained flag/event timestamp và chính sách xử lý snapshot. |
| Spring có error channel nhưng không có DLQ MQTT. | MQTT v3 không cung cấp DLQ ứng dụng mặc định. | Thiết kế topic lỗi/quarantine hoặc kho bền vững và replay. |

## 16. Bài tập thực hành

**Tình huống:** hệ thống nhận telemetry nhiệt độ từ nhiều thiết bị MQTT. Thiết bị publish vào `sensors/<deviceId>/temperature` với payload JSON:

~~~json
{
  "eventId": "evt-1001",
  "deviceId": "room-17",
  "celsius": 26.5,
  "eventTime": "2026-11-23T01:00:00Z"
}
~~~

Yêu cầu:

1. Cấu hình `MqttPahoClientFactory` từ biến môi trường, dùng broker test có xác thực phù hợp và Client ID ổn định.
2. Tạo `MqttPahoMessageDrivenChannelAdapter` subscribe `sensors/+/temperature` ở QoS 1, output channel `mqtt.telemetry.in`.
3. Parse payload JSON thành DTO `TemperatureReading`, validate `eventId`, `deviceId`, đơn vị nhiệt độ và timestamp.
4. Đối chiếu device ID trong payload với received topic và quyền thiết bị theo thiết kế.
5. Chuyển message hợp lệ vào `telemetry.validated` rồi ghi vào database qua service activator.
6. Thiết kế idempotency theo `eventId` để retry hoặc duplicate không ghi lặp.
7. Phân biệt message retained, message mới và message đến muộn theo `eventTime`.
8. Message lỗi schema được lưu quarantine; lỗi kết nối DB được xử lý retry có giới hạn và có cơ chế đối soát.
9. Viết một test không cần broker cho channel/transformer/validator, một test end-to-end có broker cho subscribe/reconnect/QoS.
10. Giải thích vì sao `@Poller` không cần để nhận message-driven MQTT, nhưng có thể xuất hiện ở một chặng `QueueChannel` downstream.

**Tiêu chí đạt:** ứng dụng nhận đúng topic wildcard, bảo toàn metadata cần thiết, xử lý bản tin hợp lệ đến DB, ghi lỗi có thể truy vết, không tạo side effect trùng và nêu rõ thời điểm nào là MQTT delivery, thời điểm nào là xử lý nghiệp vụ hoàn tất.

## 17. Tự kiểm tra nhanh

1. MQTT message-driven adapter nhận dữ liệu nhờ broker callback hay nhờ `MessageSource.receive()` theo poller?
2. `MqttPahoMessageDrivenChannelAdapter` cần gì để kết nối broker và subscribe?
3. `sensors/+/temperature` khác `sensors/#` thế nào?
4. `setQos(1)` có buộc publisher gửi ở QoS 1 không?
5. Vì sao MQTT QoS 2 không đảm bảo database chỉ được ghi một lần?
6. Nếu hai instance cùng Client ID, rủi ro gì có thể xảy ra?
7. Vì sao `cleanSession=false` không thay thế checkpoint/outbox trong ứng dụng?
8. Retained message có nhất thiết là sự kiện mới không?
9. Header received topic dùng để làm gì trong flow?
10. Vì sao không nên gọi API HTTP blocking lâu ngay trên luồng callback dùng `DirectChannel`?
11. Khi chuyển sang `QueueChannel`, thành phần nào cần poller?
12. Tại sao chỉ test `MessageChannel.send(...)` không chứng minh subscribe/reconnect thực tế?
13. Có thể biến Spring `errorChannel` thành nơi replay an toàn bằng cách nào?
14. Nếu publisher gửi trùng event nhưng không có duplicate flag, xử lý sao?

**Gợi ý:** MQTT inbound nhận theo sự kiện của Paho/broker; QoS là cơ chế giao hàng giao thức, không phải transaction nghiệp vụ; client ID/session quyết định kết nối và message offline; payload/headers phải validate; idempotency, retry và giám sát được thiết kế ở mỗi ranh giới.

## 18. Kết luận

**MQTT inbound message-driven adapter** kết nối Spring Integration với hệ thống publish–subscribe mà không cần polling nguồn. `MqttPahoMessageDrivenChannelAdapter` subscribe topic filter qua `MqttPahoClientFactory`, nhận message do broker giao, chuyển qua converter và phát vào `MessageChannel`. Từ đó `IntegrationFlow` có thể validate, transform, route, ghi database hoặc đưa dữ liệu sang HTTP/JMS/Kafka.

Khi thiết kế MQTT trong module **SPRING_INTEGRATION_ADAPTERS**, cần phân biệt rõ **broker delivery với nghiệp vụ hoàn tất**, **topic wildcard với quyền truy cập**, **QoS/retained/session với chống trùng nghiệp vụ**, và **channel đồng bộ với queue/executor**. Một inbound adapter chỉ thực sự đáng tin cậy khi có cấu hình kết nối an toàn, retry/error path, idempotency và kiểm thử end-to-end theo đặc tính broker và hệ thống đích.

