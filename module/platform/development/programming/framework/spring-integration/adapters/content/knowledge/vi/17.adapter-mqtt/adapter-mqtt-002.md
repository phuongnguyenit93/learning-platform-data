# MQTT outbound channel adapter

## 1. Bài toán và mục tiêu học tập

Một ứng dụng Spring có thể nhận đơn hàng, cập nhật thiết bị hoặc thu thập dữ liệu từ cơ sở dữ liệu, rồi cần **publish** một sự kiện hoặc lệnh tới MQTT broker. Các thiết bị và dịch vụ khác subscribe topic tương ứng để nhận bản tin. Trong Spring Integration, **MQTT outbound channel adapter** đóng vai trò consumer của `MessageChannel`: nó nhận Spring `Message<?>`, chuyển payload và các header cần thiết sang MQTT publication, rồi gửi thông qua MQTT client tới broker.

Bài này thuộc chương **Adapter MQTT** của module **SPRING_INTEGRATION_ADAPTERS**. Phạm vi của module là kết nối hệ thống bên ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành trao đổi qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời quản lý hợp đồng message, lỗi và vòng đời kết nối. MQTT outbound là một ví dụ rõ ràng của nguyên tắc: **endpoint trong flow nhận message nội bộ, client giao thức đảm nhiệm gửi ra hệ thống ngoài**.

Một tình huống cụ thể: hệ thống quản lý nhà thông minh nhận lệnh điều khiển trong Java, tạo JSON rồi publish tới topic `devices/device-17/commands`. Thiết bị subscribe topic này để nhận lệnh và có thể publish một message trạng thái hoặc ACK nghiệp vụ lên topic khác.

Sau bài học, người học có thể:

- Giải thích chiều đi **IntegrationFlow → outbound handler → MQTT broker → subscriber**.
- Dùng `MqttPahoMessageHandler`, `MqttPahoClientFactory` và `DefaultPahoMessageConverter` để cấu hình MQTT outbound.
- Gắn handler vào một channel bằng Java DSL hoặc `@ServiceActivator` mà không đăng ký trùng endpoint.
- Thiết lập topic, QoS, retained theo mặc định hoặc theo **headers từng message**.
- Phân biệt publish đồng bộ/bất đồng bộ, completion timeout, broker acknowledgement và xác nhận nghiệp vụ của thiết bị.
- Phân tích lỗi kết nối, reconnect, queue/backpressure, retry, idempotency, bảo mật TLS và shutdown.
- Kiểm thử flow bằng một handler giả không cần broker, sau đó kiểm thử outbound thực với broker thử nghiệm.

**Điểm cần nhớ:** việc publish thành công ở MQTT QoS 1 hoặc 2 chỉ thể hiện một mức bảo đảm ở **giao thức MQTT**. Nó không chứng minh subscriber đã thực thi lệnh và lưu trạng thái nghiệp vụ thành công.

## 2. Kiến trúc của MQTT outbound adapter

~~~mermaid
flowchart LR
    APP["Java service / inbound adapter<br/>file, SFTP, HTTP, JMS, Kafka, DB"]
    CH["mqtt.publish.requests<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>validate / transform / route"]
    HANDLER["MqttPahoMessageHandler<br/>outbound adapter"]
    CLIENT["Paho MQTT client"]
    BROKER[("MQTT broker")]
    SUB["MQTT subscriber / thiết bị"]
    APP --> CH --> FLOW --> HANDLER --> CLIENT
    CLIENT -->|"PUBLISH topic / QoS / retained"| BROKER
    BROKER -->|"DELIVER theo subscription"| SUB
~~~

| Thành phần | Trách nhiệm | Giới hạn cần hiểu |
| --- | --- | --- |
| Producer nội bộ | Tạo lệnh/sự kiện đã được chuẩn hóa thành Spring message. | Không tự quyết định trạng thái kết nối MQTT. |
| `MessageChannel` | Bàn giao message tới endpoint xử lý. | `send() == true` không phải ACK nghiệp vụ từ subscriber. |
| `IntegrationFlow` | Validate, transform, route và lựa chọn điểm publish. | Không tự gửi MQTT nếu chưa có outbound handler. |
| `MqttPahoMessageHandler` | Chuyển `Message<?>` thành MQTT publication. | Là **outbound one-way handler**, không phải MQTT request–reply gateway. |
| `MqttPahoClientFactory` | Cung cấp cấu hình và tạo MQTT client cho handler. | Không thay thế quản lý ACL, TLS, secrets, phiên bản broker. |
| MQTT broker | Nhận và phân phối publication theo QoS, session/topic policy. | Không tự bảo đảm thiết bị xử lý nghiệp vụ. |
| Subscriber | Nhận bản tin ở topic đã subscribe. | Có thể offline, xử lý lỗi hoặc bỏ lỡ message tùy session/QoS. |

Sơ đồ minh họa một chiều gửi. Khi cần trạng thái sau khi thiết bị thi hành lệnh, phải có **luồng nhận phản hồi riêng**, chẳng hạn MQTT inbound message-driven adapter subscribe `devices/+/ack` rồi tương quan ACK với command ID. Không giả định rằng handler outbound sẽ trả về một `DeviceAck` cho caller.

### 2.1. Outbound adapter không phải inbound adapter

- **Inbound message-driven adapter** subscribe MQTT topic và phát message từ broker vào Spring channel; nó được kích hoạt bằng callback nhận.
- **Outbound channel adapter** subscribe một **Spring input channel** và publish message ra MQTT broker; nó không cần `@Poller` nếu channel đầu vào là `DirectChannel`.
- **Poller** chỉ cần thiết ở nhánh nội bộ khi consumer lấy message từ một `PollableChannel` như `QueueChannel`, không phải để outbound handler chủ động hỏi MQTT broker có dữ liệu hay chưa.

### 2.2. Outbound adapter cũng không phải gateway request–reply

Một MQTT publication không tương đương lời gọi HTTP nhận response trực tiếp. `MqttPahoMessageHandler` chủ yếu làm **side effect gửi bản tin**. Nếu method Java gọi một `@MessagingGateway` mong chờ kết quả, không nên chỉ gắn handler outbound một chiều rồi cho rằng gateway sẽ tự nhận ACK nghiệp vụ.

Có thể thiết kế API `void publishCommand(...)`; hoặc trả về tracking ID khi lệnh đã được ứng dụng chấp nhận. Với ACK nghiệp vụ, một flow khác phải subscribe topic phản hồi, kiểm tra correlation ID và cập nhật trạng thái theo timeout riêng.

## 3. Các khái niệm MQTT ảnh hưởng tới outbound

### 3.1. Topic và cấu trúc tên

Publisher gửi đến **một topic cụ thể**, ví dụ:

~~~text
devices/device-17/commands
devices/device-17/config
devices/device-21/commands
events/inventory/changed
~~~

Topic của publication **không chứa wildcard subscribe** như `+` hoặc `#`. Wildcard dùng để định nghĩa *topic filter* cho subscriber, ví dụ `devices/+/commands`. Nếu ứng dụng lấy device ID từ request, cần kiểm tra hợp lệ trước khi ghép vào topic để tránh gửi sang thiết bị hoặc tenant khác.

### 3.2. QoS là mức delivery của giao thức

| QoS | Ý nghĩa tại MQTT | Cần chú ý khi publish |
| --- | --- | --- |
| **0 — at most once** | Không thực hiện quy trình xác nhận QoS 1/2; có nguy cơ mất message. | Phù hợp telemetry mất một mẫu vẫn chấp nhận được, nếu nghiệp vụ cho phép. |
| **1 — at least once** | MQTT dùng xác nhận để tăng khả năng delivery và có thể gửi lại. | Subscriber cần xử lý lặp theo `commandId`/`eventId`. |
| **2 — exactly once ở tầng MQTT** | Giao thức dùng handshake để giảm trùng lặp một lần delivery hợp lệ. | Không đồng nghĩa side effect DB/thiết bị đúng một lần hoặc publisher không phát trùng command mới. |

QoS tối đa của đường delivery phụ thuộc QoS publisher và subscription, cùng hành vi broker/client. Trong outbound handler, `setDefaultQos(1)` là mức mặc định cho publication không có header QoS override; nó **không** buộc các subscriber phải nhận ở QoS 1.

### 3.3. Retained message

Publisher có thể đặt **retained = true** để broker lưu bản tin retained mới nhất cho topic (theo giới hạn/chính sách broker). Subscriber đến sau có thể nhận retained message khi subscribe.

| Bài toán | Retained có phù hợp? | Lý do |
| --- | --- | --- |
| Trạng thái hiện tại của thiết bị | Thường hữu ích. | Subscriber mới cần snapshot gần nhất. |
| Cấu hình mong muốn của thiết bị | Có thể phù hợp sau khi xét bảo mật và semantics ghi đè. | Thiết bị offline có thể nhận trạng thái mong muốn khi quay lại. |
| Lệnh kích hoạt hành động một lần | **Thường không**. | Subscriber mới hoặc subscribe lại có nguy cơ thực hiện lại lệnh cũ. |
| Sự kiện tài chính/đơn hàng | Thường dùng sự kiện có ID và kho/broker phù hợp, không coi retained là event log. | Retained không lưu toàn bộ lịch sử sự kiện. |

Retained message không phải một hàng đợi offline đầy đủ. Không dùng retained như thay thế transaction log hoặc event store.

### 3.4. Client ID, session và nhiều instance

`clientId` xác định MQTT client kết nối broker. Khi có nhiều instance Spring đang publish đồng thời, **mỗi client đang hoạt động cần Client ID riêng** để tránh cạnh tranh kết nối. Với MQTT 3.1.1, `cleanSession` liên quan state/session ở broker; với một publisher chỉ gửi, session persistence không tự biến một request API thành giao dịch có khôi phục.

Nếu nhiều instance cùng xử lý một outbox để publish MQTT, phải có cơ chế **claim/outbox/partition** ở phía ứng dụng. Việc mỗi instance dùng Client ID riêng chỉ giải quyết xung đột kết nối, không tránh publish cùng một business event nhiều lần.

## 4. Dependencies và cách chọn client

Bài sử dụng **Spring Integration MQTT + Eclipse Paho MQTT v3 API**, phù hợp với Java 17+ và Spring Boot/Spring Integration tương thích. Với Maven đã quản lý phiên bản qua Spring Boot BOM:

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

Module MQTT cung cấp `MqttPahoMessageHandler` cho outbound, `MqttPahoMessageDrivenChannelAdapter` cho inbound và các thành phần chuyển đổi MQTT. Đừng trộn lẫn cấu hình Paho v3 ở bài này với Paho MQTT v5 hoặc các thư viện client khác mà chưa điều chỉnh API và semantics tương ứng.

Các class chính:

~~~java
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
~~~

Một broker thử nghiệm có thể chạy tại `tcp://localhost:1883`. Đây chỉ là ví dụ môi trường local. Với mạng thật, cần TLS, xác thực và ACL topic phù hợp; không đưa mật khẩu trực tiếp vào source code hoặc log.

## 5. Ví dụ hoàn chỉnh: Spring Integration publish lệnh điều khiển thiết bị

Mục tiêu: một Java service gửi JSON command vào Spring `MessageChannel` `mqtt.publish.requests`. Flow nhận message, đưa vào `MqttPahoMessageHandler`, và adapter publish nó lên MQTT broker.

Cấu trúc minh họa:

~~~text
src/main/java/demo/mqttout/
    MqttOutboundApplication.java
    MqttPublishFlowConfiguration.java
    MqttPublisherConfiguration.java
    DemoCommandPublisher.java

src/main/resources/
    application.properties
~~~

Các class dưới đây nằm trong package `demo.mqttout`; đặt mỗi class có top-level `public` vào file đúng tên theo Java.

### 5.1. Application khởi động

~~~java
package demo.mqttout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttOutboundApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttOutboundApplication.class, args);
    }
}
~~~

### 5.2. Khai báo channel và integration flow

~~~java
package demo.mqttout;

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
public class MqttPublishFlowConfiguration {

    @Bean(name = "mqtt.publish.requests")
    MessageChannel publishRequests() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow mqttOutboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {

        return IntegrationFlow.from("mqtt.publish.requests")
                .handle(publisher)
                .get();
    }
}
~~~

Đây là luồng tối giản **channel → outbound handler**. `.handle(publisher)` tạo endpoint nhận message từ channel đầu vào và gọi `MessageHandler.handleMessage(...)`. Nó không tự poll broker và không tạo reply nghiệp vụ.

### 5.3. Bean MQTT client factory và outbound handler

~~~java
package demo.mqttout;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;

@Configuration
public class MqttPublisherConfiguration {

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
            MqttPahoClientFactory clientFactory,
            @Value("${app.mqtt.publisher-client-id}") String clientId,
            @Value("${app.mqtt.default-topic}") String defaultTopic) {

        var handler = new MqttPahoMessageHandler(
                clientId, clientFactory);

        handler.setDefaultTopic(defaultTopic);
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setAsync(false);
        handler.setCompletionTimeout(5000);
        handler.setConverter(new DefaultPahoMessageConverter());

        return handler;
    }
}
~~~

Giải thích:

1. `MqttConnectOptions` mô tả broker, thời gian kết nối, keepalive và session. Trong production cần cấu hình xác thực/TLS qua cơ chế quản lý secret.
2. `DefaultMqttPahoClientFactory` tạo client cho handler; dùng bean factory giúp quản lý cấu hình kết nối tập trung.
3. `MqttPahoMessageHandler` là **outbound message handler**; nó publish một message khi consumer endpoint trong flow gọi handler.
4. `setDefaultTopic(...)` định nghĩa topic fallback nếu message không mang header topic.
5. `setDefaultQos(1)` và `setDefaultRetained(false)` đặt chính sách mặc định; từng message có thể cung cấp header tương ứng.
6. `setAsync(false)` chọn chế độ publish đồng bộ theo handler. Nó có thể chờ bước hoàn thành của Paho/broker theo QoS, **không chờ thiết bị thực thi lệnh**.
7. `setCompletionTimeout(5000)` giới hạn thời gian đợi hoàn thành theo logic adapter/client; nó không thay thế timeout nghiệp vụ hoặc timeout của một flow chờ ACK ở topic khác.
8. `DefaultPahoMessageConverter` chuyển payload Spring thành MQTT payload. Ví dụ này dùng `String` JSON; nếu đầu vào là DTO riêng, hãy serialize/validate trước khi publish.

`MqttPahoMessageHandler` là bean độc lập, nhưng **chỉ khi được nối bằng `.handle(publisher)` thì nó mới có consumer endpoint** cho `mqtt.publish.requests`. Không tạo thêm `@ServiceActivator` cho cùng handler/channel khi chưa muốn có consumer thứ hai.

### 5.4. Properties cho môi trường local

Tệp `application.properties`:

~~~properties
app.mqtt.broker-url=tcp://localhost:1883
app.mqtt.publisher-client-id=spring-commands-publisher-local-1
app.mqtt.default-topic=devices/default/commands
~~~

Ví dụ giả định broker test ở `localhost:1883`. Muốn chạy thành công phải có broker sẵn sàng và cho phép publisher kết nối/publish. Không dùng Client ID này cho nhiều instance chạy song song.

### 5.5. Producer gửi command qua channel

~~~java
package demo.mqttout;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.stereotype.Component;

@Component
class DemoCommandPublisher implements ApplicationRunner {

    private final MessageChannel publishRequests;

    DemoCommandPublisher(
            @Qualifier("mqtt.publish.requests")
            MessageChannel publishRequests) {
        this.publishRequests = publishRequests;
    }

    @Override
    public void run(org.springframework.boot.ApplicationArguments args) {
        String command = "{\"commandId\":\"cmd-1001\","
                + "\"deviceId\":\"device-17\","
                + "\"action\":\"TURN_ON\"}";

        boolean sent = publishRequests.send(
                MessageBuilder.withPayload(command)
                        .setHeader(MqttHeaders.TOPIC,
                                "devices/device-17/commands")
                        .setHeader(MqttHeaders.QOS, 1)
                        .setHeader(MqttHeaders.RETAINED, false)
                        .build());

        System.out.println("Channel handoff: " + sent);
    }
}
~~~

Ví dụ có chủ đích chạy **một lần** khi Spring Boot khởi động. Nếu broker không sẵn sàng hoặc publish lỗi, handler có thể ném exception trên đường gửi message; với ứng dụng production cần quyết định startup có nên phụ thuộc broker và cách khôi phục command chưa gửi.

Khi broker nhận publication, thiết bị đang subscribe topic `devices/device-17/commands` có thể nhận payload:

~~~json
{
  "commandId": "cmd-1001",
  "deviceId": "device-17",
  "action": "TURN_ON"
}
~~~

Điều này chưa chứng minh thiết bị đã bật thành công. Khi cần xác nhận, thiết bị nên publish một **ACK nghiệp vụ** có cùng `commandId` lên một topic phản hồi phù hợp, và ứng dụng cần inbound adapter khác nhận, kiểm tra ACK và cập nhật trạng thái command.

## 6. Hợp đồng message: payload và các header MQTT outbound

`MqttPahoMessageHandler` dùng message payload và MQTT headers để tạo publication. Ví dụ:

~~~text
Spring Message<String>
  payload:
    {"commandId":"cmd-1001","action":"TURN_ON"}
  headers:
    mqtt_topic: "devices/device-17/commands"
    mqtt_qos: 1
    mqtt_retained: false
    correlationId: "trace-cmd-1001"
~~~

Tên string cụ thể của header nên được thao tác thông qua hằng `MqttHeaders` để tránh lệ thuộc vào cách đặt tên và khác biệt phiên bản.

| Hằng Java | Vai trò | Giá trị ví dụ |
| --- | --- | --- |
| `MqttHeaders.TOPIC` | Chỉ định topic publish, có thể override default topic. | `"devices/device-17/commands"`. |
| `MqttHeaders.QOS` | Chỉ định QoS cho publication. | `0`, `1` hoặc `2`. |
| `MqttHeaders.RETAINED` | Xác định bản tin có retained hay không. | `false` cho command một lần. |
| `correlationId` do ứng dụng tự đặt | Truy vết giữa request và tiến trình xử lý. | `"trace-cmd-1001"`. |
| `commandId` trong payload | Nhận diện command nghiệp vụ để chống trùng và đối soát ACK. | `"cmd-1001"`. |

Các header tùy biến như `correlationId` **không mặc nhiên được publish nguyên vẹn** như MQTT user properties ở MQTT v3. MQTT v3 publication mang chủ yếu topic, QoS, retained flag và payload binary. Nếu subscriber cần correlation ID, hãy đưa vào payload theo schema được hai bên thống nhất. Không tự động serialize toàn bộ `MessageHeaders`, nhất là header nội bộ `replyChannel` hoặc `errorChannel`.

### 6.1. Default topic so với topic theo message

Nếu message không chứa `MqttHeaders.TOPIC`, handler có thể dùng `defaultTopic`:

~~~java
handler.setDefaultTopic("events/default");
~~~

Nhưng nếu message mang:

~~~java
.setHeader(MqttHeaders.TOPIC, "events/stock/changed")
~~~

thì outbound converter/handler dùng topic tương ứng với message theo cơ chế được cấu hình. **Không để message từ nguồn không đáng tin cậy tự chọn tên topic tùy ý.** Hãy validate tenant/device ID và mapping sang topic được phép trong một bước transform/router trước outbound handler.

### 6.2. Vì sao không nên publish DTO tùy ý bằng toString()?

Publisher nội bộ có thể giữ `OrderCreatedEvent` hoặc `DeviceCommand` dạng Java record. Nếu truyền thẳng object không có converter/schema rõ ràng, payload nhận ở MQTT subscriber có thể không phải JSON mà bên nhận mong đợi.

Cách tốt hơn là serialize DTO thành `String` JSON hoặc `byte[]` bằng Jackson/codec phù hợp, quy định:

- Version schema, charset, thời gian và đơn vị dữ liệu.
- Các trường bắt buộc (`commandId`, `deviceId`, `eventTime`).
- Giới hạn kích thước payload, định dạng và encoding.
- Cách nhận diện duplicate và xử lý backward compatibility.

MQTT broker không kiểm tra payload có đúng schema nghiệp vụ hay không; nhiệm vụ đó thuộc producer/consumer.

## 7. Publish đồng bộ và bất đồng bộ

`MqttPahoMessageHandler` hỗ trợ publish theo hai chiến lược.

### 7.1. Đồng bộ: setAsync(false)

~~~java
handler.setAsync(false);
handler.setCompletionTimeout(5000);
~~~

Ở chế độ này, handler có thể chặn thread gọi `handleMessage(...)` để chờ thao tác publish hoàn thành theo cơ chế Paho. Nếu channel đầu vào là `DirectChannel`, caller gửi message có thể chịu thời gian đợi đó. Khi có lỗi kết nối, không có subscriber hay broker phản hồi chậm, cần phân biệt:

- MQTT publication hoàn thành tại Paho/broker theo QoS.
- Spring `MessageChannel.send(...)` bàn giao message nội bộ.
- Subscriber đã nhận hoặc đã thi hành command nghiệp vụ.

Đó là **ba mốc khác nhau**; thời gian chờ 5 giây của handler không phải SLA 5 giây để thiết bị bật đèn.

### 7.2. Bất đồng bộ: setAsync(true)

~~~java
handler.setAsync(true);
handler.setAsyncEvents(true);
~~~

Khi dùng chế độ bất đồng bộ, handler có thể quay về trước khi publish được xác nhận hoàn tất. Spring Integration có cơ chế application events trong những phiên bản phù hợp để theo dõi publish sent/delivered/not-delivered; tên lớp event và tính khả dụng cần đối chiếu với phiên bản đang dùng. **Không xem việc `send()` trả về sớm là publish thành công**.

Với async publish, cần ghi nhận `commandId`/`eventId`, theo dõi kết quả callback/event khi cần, xử lý lỗi sau khi caller đã trả về và thiết kế restart recovery. Nếu chỉ gửi rồi quên, lỗi phát sinh sau đó có thể không đến được caller gốc.

### 7.3. Khi nào chọn cách nào?

| Tiêu chí | Đồng bộ | Bất đồng bộ |
| --- | --- | --- |
| Đường gọi | Handler có thể chờ publish token hoàn tất. | Handler thường bàn giao công việc và trả sớm. |
| Độ trễ caller | Cao hơn nếu broker/network chậm. | Thấp hơn ở đường gọi, nhưng vẫn cần kiểm soát hàng đợi. |
| Xử lý lỗi | Nhiều lỗi có thể ném ngay theo call stack. | Lỗi có thể đến sau qua callback/event/monitoring. |
| Xác nhận subscriber xử lý | Không có chỉ nhờ sync. | Không có chỉ nhờ async. |
| Tính bền vững | Không tự bảo đảm sau crash. | Không tự bảo đảm sau crash; đặc biệt cần lưu trạng thái publish. |

Nếu cần chắc chắn lệnh không bị thất lạc khi broker offline hoặc ứng dụng restart, đừng chỉ đổi `setAsync(false)` thành `true`. Cần thiết kế **outbox bền vững**, trạng thái lệnh, retry và xử lý trùng.

## 8. Cách đăng ký outbound handler bằng @ServiceActivator

Thay vì gắn handler qua Java DSL `.handle(publisher)`, Spring Integration cho phép đặt `@ServiceActivator` trên method `@Bean` tạo `MessageHandler`:

~~~java
@Bean
@ServiceActivator(inputChannel = "mqtt.publish.requests")
MessageHandler mqttOutboundHandler(
        MqttPahoClientFactory factory) {

    var handler = new MqttPahoMessageHandler(
            "mqtt-publisher-unique", factory);
    handler.setDefaultTopic("events/commands");
    handler.setDefaultQos(1);
    handler.setAsync(false);
    return handler;
}
~~~

Snippet này là **cấu hình thay thế** cho `mqttPublishFlow` + handler ở mục 5, không phải code được thêm đồng thời vào ví dụ hoàn chỉnh. Nếu cùng channel có hai consumer trên `DirectChannel`, một message có thể được phân phối cho một trong số chúng thay vì gửi hai lần như mong đợi. Nếu muốn broadcast ra nhiều broker, phải dùng kiến trúc publish–subscribe/multicast với chính sách lỗi riêng cho từng nhánh.

Đặt bean và endpoint độc lập giúp kiểm thử thay `MqttPahoMessageHandler` bằng fake `MessageHandler` mà không cần broker.

### 8.1. MQTT outbound và QueueChannel

Nếu ứng dụng đưa lệnh vào `QueueChannel` để tách thread nhận request khỏi xử lý publish, endpoint cần **poller** lấy message khỏi queue. Java DSL có thể khai báo:

~~~java
@Bean(name = "mqtt.publish.buffered")
QueueChannel bufferedPublishRequests() {
    return new QueueChannel(200);
}

@Bean
IntegrationFlow bufferedMqttOutboundFlow(
        @Qualifier("mqttPublisher") MessageHandler publisher) {

    return IntegrationFlow.from("mqtt.publish.buffered")
            .handle(publisher, endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofMillis(500))
                            .maxMessagesPerPoll(20)))
            .get();
}
~~~

Snippet này là **phương án khác** cho flow mục 5; cần import `QueueChannel`, `Pollers`, `Duration`, `@Bean` và `@Qualifier`. `QueueChannel` trong bộ nhớ không bảo đảm sống qua restart, và poller không tự retry đúng một message nếu đã bị lấy khỏi queue rồi xử lý lỗi. Với lệnh quan trọng, ưu tiên persistent queue/outbox và policy phục hồi được kiểm thử thực tế.

## 9. Lỗi xuất bản, retry và idempotency

Một luồng gửi MQTT có thể thất bại tại nhiều điểm:

~~~mermaid
flowchart TD
    P["Ứng dụng tạo command / event"]
    V{"Validate payload và topic?"}
    CH["MessageChannel"]
    H["MqttPahoMessageHandler"]
    B{"Broker nhận publish?"}
    S["Subscriber xử lý"]
    OK["Ghi nhận kết quả nghiệp vụ"]
    ERR["Error flow / outbox / retry"]
    P --> V
    V -->|"Có"| CH --> H --> B
    V -->|"Không"| ERR
    B -->|"Thành công ở MQTT"| S --> OK
    B -->|"Lỗi / chưa rõ"| ERR
    H -. "connection / timeout" .-> ERR
~~~

| Lỗi | Phát hiện ở đâu? | Cách xử lý phù hợp |
| --- | --- | --- |
| Topic sai hoặc không được phép | Validation, broker ACL. | Reject/quarantine; sửa cấu hình hoặc quyền, không retry vô hạn. |
| Broker mất kết nối | Client/handler và metric. | Reconnect có backoff, đánh dấu message chưa publish chắc chắn. |
| Timeout chờ completion | Handler sync hoặc publish callback. | Kết quả không chắc chắn; có thể broker đã nhận, phải retry idempotent. |
| Payload không serialize được | Transformer/converter. | Sửa dữ liệu/codec; lưu quarantine với context. |
| Queue nội bộ đầy | Channel/producer. | Giới hạn tải, backpressure, chính sách reject/retry rõ ràng. |
| Subscriber chưa xử lý | ACK nghiệp vụ không tới hoặc timeout. | Theo dõi command ID, retry/đối soát ở tầng nghiệp vụ. |
| Kết quả ACK bị mất | Luồng phản hồi hoặc mạng. | Truy vấn trạng thái thiết bị/đích, không phát lệnh lặp mù. |

### 9.1. Ví dụ nguy cơ publish trùng

Ứng dụng gửi command `cmd-1001` QoS 1. Broker có thể đã nhận publication nhưng ứng dụng bị ngắt kết nối trước khi nhận xác nhận. Nếu ứng dụng retry bằng một publication mới, subscriber có thể nhận **hai message cùng command ID**.

Do đó payload phải mang ID ổn định, ví dụ:

~~~json
{
  "commandId": "cmd-1001",
  "deviceId": "device-17",
  "action": "TURN_ON",
  "issuedAt": "2026-11-23T02:00:00Z"
}
~~~

Consumer cần cơ chế dedup hoặc lệnh phải idempotent theo nghiệp vụ. Đối với thao tác nguy hiểm như mở khóa, thanh toán hoặc thay đổi cấu hình quan trọng, lệnh nên có expiry, authorization, version/state precondition và cơ chế xác nhận riêng; MQTT QoS không đủ làm kiểm soát an toàn.

### 9.2. Transactional outbox cho dữ liệu quan trọng

Nếu một transaction ghi vào database đồng thời cần publish MQTT, không thể cho rằng transaction database bao phủ broker. Một kiến trúc phổ biến:

~~~mermaid
flowchart LR
    API["Business service"]
    DB[("Database<br/>business + outbox")]
    WORKER["Outbox publisher"]
    MQTT["MQTT outbound adapter"]
    BROKER[("Broker")]
    ACK["ACK/state tracking"]
    API -->|"Một DB transaction"| DB
    DB -->|"Đọc pending event"| WORKER
    WORKER --> MQTT --> BROKER
    BROKER -. "phản hồi tùy hợp đồng" .-> ACK
~~~

Ghi sự kiện vào outbox **cùng transaction DB với business record**. Worker publish từ outbox, theo dõi kết quả gửi, cập nhật trạng thái, retry với backoff và idempotency. Nếu worker crash giữa publish và cập nhật outbox, nó có thể gửi lại, nên subscriber vẫn phải chống duplicate theo event ID.

**Đừng đánh dấu event “đã xử lý ở subscriber” chỉ vì MQTT publish token thành công.** Điều đó chỉ chứng minh mức hoàn thành tương ứng của thao tác gửi, không phải kết quả nghiệp vụ bên nhận.

## 10. Backpressure, hiệu năng và kiểu channel

MQTT outbound dễ trở thành điểm nghẽn khi upstream tạo message nhanh hơn khả năng broker chấp nhận hoặc đường mạng cho phép.

| Channel trước handler | Hành vi | Rủi ro và kiểm soát |
| --- | --- | --- |
| `DirectChannel` | Handler publish ngay trong thread sender. | Broker chậm làm caller chậm; kiểm soát timeout và latency. |
| `ExecutorChannel` | Publish được chuyển sang thread pool. | Executor queue đầy, lỗi async, shutdown; phải giới hạn tài nguyên. |
| `QueueChannel` | Message chờ consumer polling. | Capacity, retry, persistent store, đo backlog và lịch poll. |
| `PublishSubscribeChannel` | Phát cùng message đến nhiều consumer. | Chỉ dùng nếu thật sự cần gửi nhiều đích; quản lý kết quả từng nhánh. |

Không nhầm **MQTT broker buffer** với **Spring QueueChannel**. Một queue nội bộ không đẩy dữ liệu lên broker cho đến khi một consumer lấy message và handler publish. Khi ứng dụng restart, queue RAM có thể mất message; khi broker offline, backlog có thể vượt dung lượng và gây lỗi upstream.

Các metric nên theo dõi: số publication theo topic/QoS, thời gian publish completion, timeout/reconnect, pending outbox, queue depth, số lần retry, message không rõ kết quả, late ACK và duplicate theo command ID.

### 10.1. Giữ thứ tự theo thiết bị

Nếu cùng một thiết bị nhận lệnh `TURN_ON` rồi `TURN_OFF`, việc publish song song nhiều thread có thể làm thay đổi thứ tự quan sát khi network/retry xảy ra. Với lệnh phụ thuộc thứ tự, cần định nghĩa sequence/version, partition hoặc một producer path có kiểm soát theo device ID. Không suy ra rằng vì gọi `MessageChannel.send(...)` theo thứ tự thì mọi subscriber chắc chắn xử lý cùng thứ tự trong mọi tình huống.

## 11. Vòng đời: startup, reconnect và shutdown

Một outbound adapter cần được quản lý như tài nguyên kết nối thực, không chỉ là một method Java:

1. **Startup:** tạo bean factory/handler và mở kết nối khi endpoint/client cần publish; quyết định ứng dụng có được chạy khi broker chưa sẵn sàng không.
2. **Broker không sẵn sàng:** cách ghi nhận command chưa gửi, retry, backoff và cảnh báo; không nuốt lỗi rồi coi như đã publish.
3. **Reconnect:** client ID, session, TLS và quyền publish vẫn hợp lệ; cần giám sát số lần kết nối lại.
4. **Credential rotation:** mật khẩu/chứng chỉ được thay đổi qua cơ chế an toàn, tránh downtime dài hoặc lộ secret.
5. **Shutdown:** ngừng nhận request mới, xử lý in-flight/pending publish theo giới hạn thời gian, đóng tài nguyên và giữ outbox chưa hoàn tất.
6. **Scale nhiều instance:** Client ID không trùng; outbox được claim/partition phù hợp; subscriber xử lý được duplicate.

Một handler được Spring quản lý không tự bảo đảm mọi message đang nằm trong bộ nhớ Paho sẽ được publish sau crash. Nếu yêu cầu recovery chắc chắn, hãy lập **hợp đồng trạng thái bền vững** ở application hoặc hạ tầng hỗ trợ.

## 12. Bảo mật outbound MQTT

| Nguy cơ | Biện pháp |
| --- | --- |
| Nghe lén lệnh trên mạng | Dùng TLS và xác minh chứng chỉ broker; cấu hình Paho SSL đúng môi trường. |
| Mật khẩu bị lộ | Secrets từ env/secret manager, hạn chế log, xoay vòng credentials. |
| Publisher gửi sai topic | ACL tại broker và kiểm tra topic/tenant/device ID trong ứng dụng. |
| Client ID trùng | Mỗi client hoạt động có ID riêng; tránh ngắt kết nối lẫn nhau. |
| Payload kích hoạt hành động trái phép | Chữ ký/ủy quyền theo nghiệp vụ nếu cần; validate command/schema. |
| Lệnh hết hạn được gửi lại | Expiry ở nghiệp vụ, timestamp, version và dedup tại thiết bị. |
| Retained command nguy hiểm | Mặc định `retained=false` cho hành động một lần, không phát tán command cũ. |
| Payload và metadata nhạy cảm trong log | Log commandId, topic đã kiểm tra và mã lỗi; tránh in secrets/full payload. |

Với MQTT v3, TLS thường dùng kết nối kiểu `ssl://broker-host:8883` và cấu hình SSL socket/certificates phù hợp trong `MqttConnectOptions`. Chỉ thay URL thành `ssl://` mà không thiết lập trust store cần thiết chưa chắc đủ để kết nối an toàn. Cũng không vô hiệu hóa hostname/certificate verification trong môi trường production.

## 13. Kiểm thử flow outbound không cần broker

Muốn kiểm tra **channel → IntegrationFlow → outbound handler**, có thể dùng cùng `MqttPublishFlowConfiguration` ở mục 5 nhưng **thay bean `mqttPublisher` bằng fake `MessageHandler`**. Test này không nạp `MqttPublisherConfiguration` nên không tạo Paho client, không truy cập mạng.

Thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo tệp `MqttPublishFlowTest.java` trong package `demo.mqttout`:

~~~java
package demo.mqttout;

import static org.junit.jupiter.api.Assertions.assertEquals;
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
        MqttPublishFlowConfiguration.class,
        FakePublisherConfiguration.class
})
class MqttPublishFlowTest {

    @Autowired
    @Qualifier("mqtt.publish.requests")
    MessageChannel requests;

    @Autowired
    RecordingPublisher publisher;

    @BeforeEach
    void reset() {
        publisher.clear();
    }

    @Test
    void forwardsPayloadAndOutboundHeadersToHandler() {
        String payload = "{\"commandId\":\"cmd-test-1\","
                + "\"action\":\"TURN_ON\"}";

        boolean accepted = requests.send(
                MessageBuilder.withPayload(payload)
                        .setHeader(MqttHeaders.TOPIC,
                                "devices/test-1/commands")
                        .setHeader(MqttHeaders.QOS, 1)
                        .setHeader(MqttHeaders.RETAINED, false)
                        .build());

        assertTrue(accepted);
        assertEquals(
                List.of(new PublishedCommand(
                        payload, "devices/test-1/commands",
                        1, false)),
                publisher.snapshot());
    }
}

record PublishedCommand(
        String payload, String topic, int qos, boolean retained) {}

class RecordingPublisher implements MessageHandler {

    private final List<PublishedCommand> recorded =
            new CopyOnWriteArrayList<>();

    @Override
    public void handleMessage(Message<?> message) {
        recorded.add(new PublishedCommand(
                (String) message.getPayload(),
                (String) message.getHeaders().get(MqttHeaders.TOPIC),
                (Integer) message.getHeaders().get(MqttHeaders.QOS),
                (Boolean) message.getHeaders().get(MqttHeaders.RETAINED)));
    }

    List<PublishedCommand> snapshot() {
        return List.copyOf(recorded);
    }

    void clear() {
        recorded.clear();
    }
}

@Configuration
class FakePublisherConfiguration {

    @Bean(name = "mqttPublisher")
    RecordingPublisher mqttPublisher() {
        return new RecordingPublisher();
    }
}
~~~

Test chứng minh:

- Bean `mqtt.publish.requests` có endpoint consumer đúng.
- `IntegrationFlow` chuyển message đến bean `mqttPublisher` qua `.handle(...)`.
- Payload `String` và ba header MQTT outbound đến handler nguyên vẹn.
- Với `DirectChannel`, có thể assert ngay sau `send(...)`.

**Giới hạn:** test chưa kiểm tra converter thực của Paho, topic publish ở broker, QoS ACK, reconnect hoặc retained. Đó là lý do cần thêm test end-to-end với broker. Đừng kết luận MQTT đã publish thành công chỉ vì fake handler nhận message.

## 14. Kiểm thử end-to-end với MQTT broker

Khi có broker local và CLI MQTT, có thể chuẩn bị subscriber trước:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -t 'devices/+/commands' -v
~~~

Sau đó chạy `MqttOutboundApplication`. `DemoCommandPublisher` publish JSON lệnh tới `devices/device-17/commands`. Subscriber dự kiến in topic và payload tương ứng:

~~~text
devices/device-17/commands {"commandId":"cmd-1001","deviceId":"device-17","action":"TURN_ON"}
~~~

Điều kiện tiên quyết: broker đang chạy, application đúng URL/topic và broker cho phép hai client test kết nối; CLI `mosquitto_sub` đã cài. Với broker yêu cầu xác thực hoặc TLS, cần cấu hình cả ứng dụng và CLI đúng quyền; không tắt bảo mật broker production chỉ để kiểm thử.

### 14.1. Các kịch bản cần xác minh

| Kịch bản | Cách kiểm tra | Điều phải kết luận đúng |
| --- | --- | --- |
| Default topic | Không đặt `MqttHeaders.TOPIC`. | Publication dùng topic mặc định cấu hình. |
| Override topic | Set topic header khác default. | Message đến topic được chỉ định nếu ACL cho phép. |
| QoS 0/1/2 | Thay QoS trong môi trường test. | Kiểm tra delivery/ack theo protocol, không suy ra xử lý nghiệp vụ. |
| Retained | Publish retained vào topic test. | Subscriber mới nhận bản tin retained khi subscribe. |
| Broker offline | Ngắt broker trước hoặc trong lúc publish. | Ghi nhận lỗi/timeout và trạng thái cần retry; không mất command âm thầm. |
| Broker trở lại | Bật broker, publish/retry theo policy. | Message phục hồi mà không side effect trùng. |
| Subscriber offline | Dừng subscriber, publish rồi khởi động lại. | Kết quả phụ thuộc QoS/session/broker và retained; không giả định sẽ có replay đầy đủ. |
| Không được quyền publish | Topic trái ACL. | Lỗi được báo rõ và command không đánh dấu thành công. |
| Publish trùng command ID | Gửi lại cùng JSON/event. | Subscriber hoặc DB không thực hiện lặp nghiệp vụ. |
| High throughput | Publish nhiều message nhanh hơn broker. | Queue/pool có giới hạn, không cạn tài nguyên, có metric backlog. |

Nếu cần ACK sau khi thiết bị thực thi, triển khai inbound subscription `devices/+/ack` và đối soát `commandId`; test phải xác nhận **trạng thái thiết bị** thay vì chỉ nhìn output của `mosquitto_sub`.

## 15. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Gửi message vào channel nhưng không thấy broker nhận. | Flow chưa đăng ký consumer/bean handler, sai channel, broker offline. | Kiểm tra `mqtt.publish.requests`, `.handle(publisher)` và client logs. |
| Handler báo topic không hợp lệ. | Header topic trống/sai, default topic thiếu, wildcard được dùng ở publish. | Kiểm tra `MqttHeaders.TOPIC` và mapping topic. |
| Không kết nối broker. | Sai URL, DNS, port, TLS, credential. | Kiểm tra Paho options, network, certificate và broker ACL. |
| Hai instance disconnect lẫn nhau. | Client ID trùng. | Tạo Client ID duy nhất trên mỗi client đang hoạt động. |
| Gửi bằng QoS 1 nhưng thiết bị không phản hồi. | QoS chỉ bảo đảm MQTT delivery, thiết bị không xử lý/không publish ACK. | Thiết kế ACK nghiệp vụ riêng với timeout. |
| Subscriber mới thực hiện lệnh cũ. | Publication command bị đánh dấu retained. | Dùng retained=false cho command một lần. |
| `send()` trả true nhưng publish thất bại sau đó. | `setAsync(true)`, xử lý ở thread khác hoặc lỗi đến muộn. | Monitor publish completion/callback và outbox state. |
| Lệnh bị gửi trùng sau retry. | Broker đã nhận nhưng client mất ACK; app phát publication mới. | Dùng `commandId`, dedup và đối soát. |
| Queue có nhiều message nhưng không publish. | QueueChannel thiếu poller consumer. | Bổ sung poller phù hợp, giám sát queue depth. |
| Restart mất lệnh chưa gửi. | Chỉ giữ queue hoặc state trong RAM. | Outbox/persistent store và recovery policy. |
| JSON của bên nhận sai. | Converter không serialize DTO theo schema thỏa thuận. | Serialize tường minh String/byte[], contract test. |
| Gateway Java timeout dù broker nhận lệnh. | MQTT outbound one-way không tạo reply nghiệp vụ. | Tách ACK flow, trả tracking ID và đối soát. |

## 16. Bài tập thực hành: hệ thống gửi lệnh tới thiết bị

**Bối cảnh:** ứng dụng quản lý điều hòa nhận yêu cầu đặt nhiệt độ từ HTTP và lưu command vào database. Sau đó gửi MQTT command tới thiết bị đã đăng ký topic `devices/<deviceId>/commands`; thiết bị publish ACK vào `devices/<deviceId>/ack`.

Yêu cầu:

1. Thiết kế DTO `TemperatureCommand(commandId, deviceId, targetCelsius, issuedAt)` và schema JSON gửi ra.
2. Cấu hình `MqttPahoClientFactory` theo environment, có TLS và credentials khi broker yêu cầu.
3. Đăng ký `MqttPahoMessageHandler` là bean độc lập, topic mặc định cho test, QoS 1, retained=false.
4. Tạo `mqtt.publish.requests` và `IntegrationFlow` dùng handler bean để publish.
5. Validate device ID, topic ACL/tenant và giới hạn nhiệt độ trước khi đặt `MqttHeaders.TOPIC`.
6. Ghi business command cùng outbox trong một DB transaction; worker đọc outbox và phát MQTT.
7. Xử lý broker mất kết nối, completion timeout, restart và retry có giới hạn; không đánh dấu command hoàn tất chỉ sau publish.
8. Tạo MQTT inbound adapter riêng subscribe ACK, đối chiếu `commandId`, xử lý ACK muộn, trùng hoặc không khớp.
9. Viết test flow không broker cho payload/topic/QoS/retained và test có broker cho publish, ACL, retained, disconnect/reconnect.
10. Giải thích khi nào dùng publisher sync hay async, và backpressure theo số thiết bị/tốc độ request.

**Tiêu chí đạt:** không publish sai topic, không retained lệnh một lần, broker failure không làm mất command bền vững, retry không kích hoạt lệnh trùng ngoài hợp đồng, và có trạng thái tách biệt **ACCEPTED → PUBLISHED → DEVICE_ACKNOWLEDGED**.

## 17. Câu hỏi tự kiểm tra

1. `MqttPahoMessageHandler` nhận message từ đâu và gửi message đến đâu?
2. Outbound adapter có cần `@Poller` khi input là `DirectChannel` không?
3. Khác biệt giữa `MqttHeaders.TOPIC` và topic filter chứa `+`/`#`?
4. Khi nào `defaultTopic` được dùng?
5. `setDefaultQos(1)` có bảo đảm subscriber thực thi lệnh đúng một lần không?
6. Vì sao `retained=true` có thể nguy hiểm với command một lần?
7. Client ID của hai publisher chạy đồng thời nên cấu hình thế nào?
8. Publish `async=true` khác `async=false` ở thời điểm lỗi và độ trễ ra sao?
9. Vì sao `MessageChannel.send(...)` trả true chưa chứng minh MQTT publish thành công?
10. Vì sao MQTT publish token thành công không phải business ACK?
11. Khi retry sau timeout, làm thế nào tránh gửi trùng `commandId`?
12. QueueChannel có tự lưu message bền qua restart không?
13. Khi handler publish JSON, vì sao cần serialize DTO rõ ràng?
14. Test dùng fake `MessageHandler` chứng minh điều gì và chưa chứng minh điều gì?
15. Khi đổi broker từ TCP sang TLS, phải kiểm tra thêm điều gì?
16. Khi cùng event cần gửi MQTT và Kafka, nên thiết kế trạng thái và retry cho từng đích thế nào?

**Gợi ý:** MQTT outbound là endpoint gửi một chiều, không trực tiếp cung cấp reply nghiệp vụ. Header topic/QoS/retained điều khiển publication, còn khả năng xử lý sau khi broker nhận phụ thuộc subscriber, ACK riêng và idempotency. Reliability end-to-end phải kiểm thử khi mạng, broker, app hoặc subscriber gặp lỗi.

## 18. Kết luận

**MQTT outbound channel adapter** giúp đưa dữ liệu từ Spring Integration ra MQTT broker bằng `MqttPahoMessageHandler`. Một `MessageChannel` nhận command/event nội bộ, `IntegrationFlow` validate và chuyển đến handler, còn `MqttPahoClientFactory` cung cấp kết nối giao thức. Topic, QoS và retained có thể lấy từ cấu hình mặc định hoặc header từng message.

Trong module **SPRING_INTEGRATION_ADAPTERS**, MQTT outbound là một trong các cách kết nối tới hệ thống ngoài bên cạnh file, SFTP, HTTP, JMS, AMQP, Kafka và database. Thiết kế đúng phải tách rõ **bàn giao message trong Spring**, **publish hoàn thành ở broker** và **subscriber hoàn tất nghiệp vụ**; đồng thời quản lý TLS/ACL, client ID, retry/backpressure, idempotency, outbox và kiểm thử cả flow lẫn kết nối thật.

