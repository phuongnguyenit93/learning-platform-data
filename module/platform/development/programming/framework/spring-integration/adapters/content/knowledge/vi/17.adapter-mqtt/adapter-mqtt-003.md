# MQTT client factory và broker URL

## 1. Mục tiêu bài học

Trong Spring Integration, việc kết nối MQTT broker không bắt đầu từ một `MessageChannel` mà từ **MQTT client**. Client phải biết broker ở đâu, dùng giao thức vận chuyển nào, có cần xác thực hay TLS không, kết nối bao lâu thì timeout, giữ session ra sao và nhận diện client bằng ID nào. Spring Integration đóng gói phần cấu hình chung này trong **`MqttPahoClientFactory`**, giúp inbound và outbound MQTT adapter dùng kết nối được quản lý nhất quán.

Bài **MQTT client factory và broker URL** thuộc chương **Adapter MQTT** trong module **SPRING_INTEGRATION_ADAPTERS**. Mục tiêu của module là kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, thực hành với file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời xử lý hợp đồng message, lỗi và vòng đời kết nối. MQTT là một giao thức publish–subscribe nên cách quản lý broker, client và subscription khác với các nguồn polling như file/SFTP/JDBC.

Sau bài học, người học có thể:

- Hiểu quan hệ giữa **`DefaultMqttPahoClientFactory`**, **`MqttConnectOptions`**, MQTT client và MQTT adapter.
- Chọn broker URL đúng giao thức (`tcp://`, `ssl://`), phân biệt URL kết nối với MQTT topic.
- Cấu hình nhiều broker URI theo cơ chế **kết nối dự phòng**, không nhầm thành cân bằng tải message.
- Tạo Spring bean factory và dùng cho `MqttPahoMessageDrivenChannelAdapter` cũng như `MqttPahoMessageHandler`.
- Quản lý Client ID, session, keepalive, connection timeout, recovery/reconnect và ứng dụng nhiều instance.
- Áp dụng TLS, credential/ACL, biến môi trường và nguyên tắc không đưa secret vào mã nguồn.
- Kiểm thử cấu hình factory **không cần broker**, rồi xác minh kết nối thật trong bài thử end-to-end.
- Phân tích giới hạn của factory: có kết nối không đồng nghĩa MQTT message đã được xử lý thành công ở downstream.

**Thông điệp chính:** Factory chịu trách nhiệm **tạo và cấu hình client giao thức**. Inbound adapter quyết định subscribe rồi phát Spring message vào channel; outbound adapter nhận Spring message từ channel rồi publish. Các khả năng như retry nghiệp vụ, transaction, idempotency hay ACK từ thiết bị **không xuất hiện tự động chỉ vì factory kết nối broker thành công**.

## 2. Factory nằm ở đâu trong kiến trúc?

~~~mermaid
flowchart LR
    CFG["Spring Configuration<br/>broker URL, TLS, credentials, session"]
    OPT["MqttConnectOptions"]
    FACTORY["DefaultMqttPahoClientFactory"]
    INBOUND["MqttPahoMessageDrivenChannelAdapter<br/>subscriber client ID"]
    OUTBOUND["MqttPahoMessageHandler<br/>publisher client ID"]
    BROKER[("MQTT Broker")]
    INCH["mqtt.inbound<br/>MessageChannel"]
    OUTCH["mqtt.outbound<br/>MessageChannel"]
    FLOW["IntegrationFlow"]
    CFG --> OPT --> FACTORY
    FACTORY --> INBOUND
    FACTORY --> OUTBOUND
    BROKER -->|"deliver"| INBOUND --> INCH --> FLOW
    FLOW --> OUTCH --> OUTBOUND -->|"publish"| BROKER
~~~

Các thành phần đảm nhận các trách nhiệm khác nhau:

| Thành phần | Vai trò | Cần phân biệt |
| --- | --- | --- |
| `MqttConnectOptions` | Mô tả URI broker, timeout, keepalive, credential, TLS/session theo API Eclipse Paho v3. | Đây là **cấu hình kết nối**, không phải MQTT message. |
| `MqttPahoClientFactory` | Giao diện factory mà MQTT adapter dùng để có MQTT client cấu hình sẵn. | Không phải một MQTT broker. |
| `DefaultMqttPahoClientFactory` | Implementation thường dùng, nhận `MqttConnectOptions`. | Không phải một channel và không tự tạo integration flow. |
| `MqttPahoMessageDrivenChannelAdapter` | Client subscriber nhận message theo callback, phát vào Spring channel. | Không yêu cầu poller đọc MQTT broker. |
| `MqttPahoMessageHandler` | Handler outbound publish payload/topic từ Spring message ra broker. | Không phải gateway đồng bộ chờ kết quả nghiệp vụ từ subscriber. |
| `MessageChannel` | Bàn giao message giữa endpoint của Spring Integration. | Không tự chứa thông tin broker URL. |
| MQTT broker | Server nhận publication và phân phối theo topic/subscription. | Không quản lý transaction của ứng dụng downstream. |

Thông thường factory được đăng ký thành **Spring bean singleton** chứa cấu hình kết nối. Hai adapter có thể inject cùng bean factory, nhưng **không nên kết luận** rằng inbound/outbound chia sẻ cùng một kết nối vật lý hoặc cùng Client ID. Mỗi adapter xác định danh tính client của mình và quản lý hoạt động subscribe/publish tương ứng.

### 2.1. Chia sẻ factory hay chia sẻ client?

Giả sử một ứng dụng vừa subscribe `sensors/+/temperature` vừa publish `devices/+/commands`. Hai adapter có thể cùng sử dụng một `MqttPahoClientFactory` để tái sử dụng URI, TLS trust configuration và credential. Tuy nhiên:

1. Inbound adapter cần **subscriber Client ID** phù hợp để quản lý session/subscription.
2. Outbound handler cần **publisher Client ID** riêng để không tranh chấp kết nối.
3. Nếu chính sách session/credential của hai chiều khác nhau, hãy tạo **hai factory bean** hoặc tách cấu hình thay vì ép mọi adapter dùng chung options.
4. Factory không phải message bus cho phép mọi adapter tự chia sẻ subscription hay ACK nghiệp vụ.

**Không dùng cùng Client ID cho hai MQTT clients đồng thời.** Broker thường coi Client ID là danh tính duy nhất của phiên đang kết nối; một client mới đăng nhập với cùng ID có thể khiến client cũ bị ngắt.

## 3. Broker URL là gì?

**Broker URL** (URI kết nối) là địa chỉ mà Eclipse Paho sử dụng để **mở kết nối MQTT đến server**. Nó không phải topic và không phải địa chỉ của Spring `MessageChannel`.

Ví dụ phổ biến với Paho MQTT v3:

| Broker URI | Vận chuyển | Ngữ cảnh sử dụng |
| --- | --- | --- |
| `tcp://localhost:1883` | MQTT trên TCP không mã hóa. | Broker thử nghiệm trên cùng máy. |
| `tcp://mqtt-broker.internal:1883` | MQTT trên TCP trong mạng nội bộ. | Chỉ khi mạng và chính sách an ninh cho phép. |
| `ssl://mqtt.example.com:8883` | MQTT qua TLS theo Paho v3 URI scheme. | Kết nối yêu cầu mã hóa/xác minh server. |

**Không đồng nhất URL của broker với URL web** như `https://...` hoặc tự thay `tcp://` bằng `mqtt://` khi chưa biết thư viện MQTT có hỗ trợ URI scheme đó. Paho còn có các cách kết nối WebSocket ở những phiên bản/cấu hình nhất định; bài này giới hạn ở `tcp://` và `ssl://` để minh họa API Paho v3.

Một URI chứa: **scheme → host → port**. Khi đổi port, phải bảo đảm broker thật sự lắng nghe trên port đó và firewall/security group cho phép. Port 1883/8883 là các giá trị thông dụng, không phải cam kết mọi broker đều dùng mặc định.

~~~text
tcp://mqtt-broker.internal:1883
│     │                    │
│     │                    └─ Port broker MQTT
│     └────────────────────── Hostname / IP broker
└──────────────────────────── Scheme vận chuyển
~~~

### 3.1. Broker URI khác MQTT topic thế nào?

~~~text
Broker URI: tcp://localhost:1883
Client ID:  telemetry-subscriber-1
Subscribe:  sensors/+/temperature

Publish topic: devices/device-17/commands
Payload:       {"commandId":"cmd-1001","action":"TURN_ON"}
~~~

- Broker URI được dùng khi **thiết lập kết nối**.
- Client ID nhận diện MQTT client session với broker.
- Subscribe filter như `sensors/+/temperature` được adapter inbound đăng ký **sau khi kết nối**.
- Publish topic như `devices/device-17/commands` chỉ định nơi **gửi bản tin** trong namespace topic của broker.

Không đưa topic vào chuỗi broker URI kiểu `tcp://localhost:1883/devices/...`. Với MQTT TCP thuần, topic là trường của MQTT protocol, không phải đường dẫn HTTP. Nếu cần chuyển nhiều loại event, giữ broker URI ổn định và cấu hình topic/subscription ở adapter/message.

### 3.2. Broker URI và cấu hình theo môi trường

| Môi trường | Ví dụ | Khuyến nghị |
| --- | --- | --- |
| Local development | `tcp://localhost:1883` | Broker test riêng, không dùng dữ liệu thật. |
| Integration test | URI của broker test/container. | Chờ broker sẵn sàng, cách ly Client ID/topic cho test. |
| Staging | `ssl://mqtt-staging.example.internal:8883` | Dùng TLS và quyền topic gần giống production. |
| Production | `ssl://mqtt-prod.example.internal:8883` hoặc DNS/VIP do hạ tầng cung cấp. | Cấu hình secret, TLS trust, monitoring và kế hoạch failover. |

Khi ứng dụng chạy trong container, `localhost` là **chính container đó**, không tự trỏ đến MQTT broker trên máy host hoặc container khác. Hãy dùng DNS/service name có thể truy cập từ network namespace của ứng dụng.

## 4. Dependency và lựa chọn phiên bản MQTT client

Với Spring Boot đã quản lý phiên bản dependency, Maven tối thiểu:

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

`spring-integration-mqtt` cung cấp các adapter MQTT và thành phần factory dựa trên Eclipse Paho. Ví dụ bài này dùng **Paho MQTT v3**, cụ thể là `org.eclipse.paho.client.mqttv3.MqttConnectOptions`, phù hợp với client MQTT 3.1.1.

Đừng trộn API v3 ở ví dụ này với API MQTT v5 chỉ vì broker hỗ trợ cả hai. MQTT v5 dùng các khái niệm mới như session expiry và user properties; cách biểu diễn chúng trong client/options khác với `cleanSession` của MQTT v3.

Các import cốt lõi:

~~~java
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
~~~

Ưu tiên để **Spring Boot BOM quản lý phiên bản** của Spring Integration/Paho và kiểm tra API theo phiên bản hiện sử dụng. Việc dùng một file YAML có `mqtt:...` hoặc một URL MQTT bất kỳ không thay thế việc có module MQTT tương thích trên classpath.

## 5. Tạo MqttPahoClientFactory bằng Spring @Bean

Với một broker test, cấu hình Java ngắn nhất:

~~~java
@Configuration
class SimpleMqttFactoryConfiguration {

    @Bean
    MqttPahoClientFactory mqttClientFactory() {
        MqttConnectOptions options = new MqttConnectOptions();
        options.setServerURIs(new String[] {
                "tcp://localhost:1883"
        });
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(true);

        DefaultMqttPahoClientFactory factory =
                new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }
}
~~~

Snippet cần các import `@Configuration`, `@Bean` và các class Paho/Spring Integration đã nêu. Chỉ dùng URL hardcoded trong một ví dụ local; ứng dụng triển khai phải lấy broker URL và credentials từ cấu hình theo môi trường.

Ý nghĩa:

- `setServerURIs(String[])` cung cấp **một hoặc nhiều endpoint broker** để Paho thử kết nối.
- `setConnectionTimeout(10)` đặt timeout kết nối theo **giây**.
- `setKeepAliveInterval(30)` đặt keepalive theo **giây**, giúp broker/client phát hiện mất kết nối ở mức protocol.
- `setCleanSession(true)` dùng session mới khi kết nối theo MQTT 3.1.1. Nếu subscriber cần session bền vững khi offline thì phải thiết kế lại Client ID, QoS và session policy.
- `setConnectionOptions(options)` đưa options vào factory để adapter tạo client theo cấu hình chung.

**Quan trọng:** việc tạo bean factory không có nghĩa kết nối MQTT đã được mở. Kết nối phát sinh trong vòng đời adapter/client khi adapter khởi động hoặc publish/subscribe theo cách hoạt động của endpoint.

## 6. Ví dụ hoàn chỉnh: cấu hình broker URL bằng application.properties

Ta xây một ứng dụng nhỏ có hai flow: inbound subscribe telemetry và outbound publish command. Cả hai sử dụng **một factory bean** nhưng có **Client ID riêng**. Mục tiêu là làm rõ đối tượng kết nối được cấu hình ở đâu, adapter kết nối thế nào và message đi qua channel nào.

Cấu trúc tệp:

~~~text
src/main/java/demo/mqttfactory/
    MqttFactoryApplication.java
    MqttConnectionConfiguration.java
    MqttAdapterConfiguration.java

src/main/resources/
    application.properties
~~~

Yêu cầu Java 17+ và Spring Boot/Spring Integration có module MQTT tương thích. Cần broker MQTT chạy sẵn để thử publish/subscribe end-to-end; việc chạy Spring Boot không tự tạo broker.

### 6.1. Property placeholders và biến môi trường

~~~properties
# Broker URI: một hoặc nhiều URI, phân tách bằng dấu phẩy.
app.mqtt.broker-urls=${MQTT_BROKER_URLS:tcp://localhost:1883}

# Hai client ID phải khác nhau trong cùng thời điểm.
app.mqtt.inbound-client-id=${MQTT_INBOUND_CLIENT_ID:demo-telemetry-in-1}
app.mqtt.outbound-client-id=${MQTT_OUTBOUND_CLIENT_ID:demo-command-out-1}

app.mqtt.subscribe-topic=sensors/+/temperature
app.mqtt.publish-topic=devices/demo-1/commands

# Tham số Paho MQTT v3.
app.mqtt.connection-timeout-seconds=10
app.mqtt.keep-alive-seconds=30
app.mqtt.clean-session=true

# Lấy secret từ biến môi trường, không commit giá trị thật.
app.mqtt.username=${MQTT_USERNAME:}
app.mqtt.password=${MQTT_PASSWORD:}
~~~

Trong môi trường production, nên cấu hình broker URL, ID, username/password và chứng chỉ qua deployment secrets hoặc hệ thống quản lý cấu hình. Không ghi mật khẩu thật vào `application.properties` trong repository, không in raw secret vào log khi cấu hình bean.

### 6.2. Khởi động Spring Boot

~~~java
package demo.mqttfactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttFactoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttFactoryApplication.class, args);
    }
}
~~~

`@SpringBootApplication` quét các class `@Configuration` trong cùng package hoặc subpackage. Spring Boot starter integration cung cấp hạ tầng để Spring Integration đăng ký endpoint theo bean definitions.

### 6.3. Cấu hình options và factory độc lập

~~~java
package demo.mqttfactory;

import java.util.Arrays;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;

@Configuration
class MqttConnectionConfiguration {

    @Bean
    MqttConnectOptions mqttConnectOptions(
            @Value("${app.mqtt.broker-urls}") String brokerUrls,
            @Value("${app.mqtt.connection-timeout-seconds:10}")
            int connectionTimeoutSeconds,
            @Value("${app.mqtt.keep-alive-seconds:30}")
            int keepAliveSeconds,
            @Value("${app.mqtt.clean-session:true}") boolean cleanSession,
            @Value("${app.mqtt.username:}") String username,
            @Value("${app.mqtt.password:}") String password) {

        String[] uris = Arrays.stream(brokerUrls.split(","))
                .map(String::trim)
                .filter(uri -> !uri.isBlank())
                .toArray(String[]::new);

        if (uris.length == 0) {
            throw new IllegalArgumentException(
                    "app.mqtt.broker-urls phải có ít nhất một URI");
        }

        for (String uri : uris) {
            if (!uri.startsWith("tcp://")
                    && !uri.startsWith("ssl://")) {
                throw new IllegalArgumentException(
                        "Chỉ dùng tcp:// hoặc ssl:// trong demo: " + uri);
            }
        }

        var options = new MqttConnectOptions();
        options.setServerURIs(uris);
        options.setConnectionTimeout(connectionTimeoutSeconds);
        options.setKeepAliveInterval(keepAliveSeconds);
        options.setCleanSession(cleanSession);

        if (!username.isBlank()) {
            options.setUserName(username);
        }
        if (!password.isBlank()) {
            options.setPassword(password.toCharArray());
        }

        return options;
    }

    @Bean
    MqttPahoClientFactory mqttClientFactory(
            MqttConnectOptions mqttConnectOptions) {

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(mqttConnectOptions);
        return factory;
    }
}
~~~

Thiết kế dùng **hai bean riêng**:

1. `mqttConnectOptions` nắm toàn bộ tham số kết nối, dễ unit test và quan sát bằng các thuộc tính an toàn, không log secret.
2. `mqttClientFactory` giữ options và cung cấp cho adapter khi Spring khởi động flow.

Ví dụ chỉ cho phép URI `tcp://` hoặc `ssl://`. Nó **không** kiểm tra DNS, broker có đang mở hay chứng chỉ TLS hợp lệ — các điều kiện đó chỉ được xác minh khi kết nối thực tế. Nếu broker dùng WebSocket, cần bổ sung scheme và cấu hình client phù hợp **sau khi xác nhận phiên bản Paho hỗ trợ**.

Khi username/password không được cung cấp, client thử kết nối theo chính sách broker; không phải broker nào cũng cho phép anonymous connection. Nếu production cần xác thực, nên validation fail-fast với trường bắt buộc và tránh startup khi thiếu secret.

### 6.4. Inbound và outbound adapter dùng chung factory

~~~java
package demo.mqttfactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
class MqttAdapterConfiguration {

    @Bean(name = "mqtt.inbound")
    MessageChannel mqttInboundChannel() {
        return new DirectChannel();
    }

    @Bean(name = "mqtt.outbound")
    MessageChannel mqttOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter mqttInboundAdapter(
            MqttPahoClientFactory factory,
            @Qualifier("mqtt.inbound") MessageChannel input,
            @Value("${app.mqtt.inbound-client-id}") String clientId,
            @Value("${app.mqtt.subscribe-topic}") String topicFilter) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, factory, topicFilter);
        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(input);
        return adapter;
    }

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler mqttPublisher(
            MqttPahoClientFactory factory,
            @Value("${app.mqtt.outbound-client-id}") String clientId,
            @Value("${app.mqtt.publish-topic}") String topic) {

        var handler = new MqttPahoMessageHandler(
                clientId, factory);
        handler.setDefaultTopic(topic);
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setAsync(false);
        handler.setCompletionTimeout(5000);
        handler.setConverter(new DefaultPahoMessageConverter());
        return handler;
    }

    @Bean
    IntegrationFlow telemetryFlow() {
        return IntegrationFlow.from("mqtt.inbound")
                .handle(String.class, (payload, headers) -> {
                    System.out.println(
                            "MQTT received topic="
                            + headers.get(MqttHeaders.RECEIVED_TOPIC)
                            + ", bytes=" + payload.length());
                    return null; // inbound một chiều
                })
                .get();
    }

    @Bean
    IntegrationFlow outboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {

        return IntegrationFlow.from("mqtt.outbound")
                .handle(publisher)
                .get();
    }
}
~~~

Hai adapter dùng **cùng factory bean** nhưng được cấu hình với hai client ID khác nhau. `mqttInboundAdapter` nhận bản tin do broker gửi, thông qua `setOutputChannel(...)` để phát Spring message vào `mqtt.inbound`; `outboundFlow` lắng nghe `mqtt.outbound` và dùng `mqttPublisher` để publish message.

Khi ứng dụng bắt đầu, inbound adapter có thể khởi động subscription và kết nối tới broker theo lifecycle. Outbound handler tạo/dùng client kết nối khi cần publish. **Không đặt thêm `@ServiceActivator(inputChannel="mqtt.outbound")` lên cùng handler nếu DSL đã đăng ký consumer**; tránh tạo các endpoint cạnh tranh ngoài ý định.

Ví dụ một service gửi command tới outbound channel:

~~~java
@Service
class DeviceCommandPublisher {

    private final MessageChannel output;

    DeviceCommandPublisher(
            @Qualifier("mqtt.outbound") MessageChannel output) {
        this.output = output;
    }

    void publish(String commandJson, String deviceId) {
        // Phải kiểm tra deviceId, tenant và quyền trước khi ghép topic.
        String topic = "devices/" + deviceId + "/commands";
        output.send(MessageBuilder.withPayload(commandJson)
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, 1)
                .setHeader(MqttHeaders.RETAINED, false)
                .build());
    }
}
~~~

Snippet này cần import `@Service`, `@Qualifier`, `MessageChannel`, `MessageBuilder` và `MqttHeaders`. Nó giả định caller đã validate `deviceId` và JSON theo hợp đồng; **không dùng trực tiếp giá trị device ID không tin cậy** để định tuyến publish. Với quyền dữ liệu đa tenant, cần xác thực cả client/broker ACL và permission nghiệp vụ.

### 6.5. Kết quả mong đợi và giới hạn

~~~mermaid
sequenceDiagram
    participant APP as Java / Spring Integration
    participant OUT as MQTT outbound handler
    participant F as MqttPahoClientFactory
    participant BROKER as MQTT broker
    participant IN as MQTT inbound adapter
    participant FLOW as mqtt.inbound flow
    APP->>OUT: Message<String> + mqtt_topic
    OUT->>F: Sử dụng cấu hình Paho client
    OUT->>BROKER: PUBLISH topic + QoS
    BROKER-->>OUT: MQTT protocol acknowledgement theo QoS
    BROKER->>IN: DELIVER khi topic filter khớp
    IN->>FLOW: Spring Message<String>
~~~

Lời gọi publish thành công không có nghĩa subscriber đã cập nhật trạng thái thiết bị. Nếu cần ACK nghiệp vụ, phải thiết kế topic ACK, message correlation, timeout, idempotency và consumer inbound riêng. Factory chỉ quản lý connection, **không biến MQTT thành transaction request–reply**.

## 7. Nhiều broker URL: fallback khác load balancing

`MqttConnectOptions#setServerURIs(...)` có thể nhận nhiều URI:

~~~java
options.setServerURIs(new String[] {
        "ssl://mqtt-a.example.internal:8883",
        "ssl://mqtt-b.example.internal:8883"
});
~~~

Mục tiêu thường là có **danh sách broker endpoint mà Paho có thể thử kết nối**. Tuy nhiên, cần phân biệt các kiến trúc:

| Kiểu hạ tầng | Ý nghĩa của nhiều URI | Rủi ro |
| --- | --- | --- |
| Các node thuộc cùng một cluster MQTT có state/session phù hợp | Client có thể thử endpoint khác khi một node không khả dụng theo cơ chế client/broker. | Session/subscription/retained vẫn phụ thuộc broker cluster thực tế. |
| Hai broker độc lập, không chia sẻ dữ liệu | Client có thể kết nối sang broker khác. | Topic/history/session của hai broker không tự đồng bộ. |
| DNS/VIP/load balancer phía trước cluster | Client có thể chỉ cần một DNS/VIP. | Cần health check, sticky session hoặc broker behavior phù hợp. |

**Nhiều URI không có nghĩa một publish sẽ được gửi tới tất cả broker.** Paho kết nối tới một endpoint trong danh sách tại một thời điểm theo cơ chế client, không phải message replicator hay multicast. Nếu muốn phát cùng event đến hai hệ thống MQTT độc lập, phải có hai outbound endpoints/factories hoặc một cơ chế replication được thiết kế rõ, cùng chính sách retry/dedup từng đích.

### 7.1. Cảnh báo về session khi failover

Với MQTT v3, một subscriber dùng `cleanSession=false` và Client ID ổn định có thể được broker lưu trạng thái session/offline delivery theo cấu hình. Nếu client chuyển giữa **hai broker độc lập không chia sẻ session**, không thể giả định message lúc offline vẫn được giao đủ.

Khi thiết kế HA, cần kiểm tra broker cluster có đồng bộ session/subscription/retained/in-flight đúng yêu cầu không, và thực nghiệm các kịch bản: broker mất, network partition, reconnect, publish đang chờ ACK và subscription sau failover.

### 7.2. Một URI cho TCP và một URI cho TLS có nên đặt chung?

Ví dụ:

~~~text
tcp://mqtt-a:1883,ssl://mqtt-b:8883
~~~

Paho có thể gặp các endpoint có yêu cầu bảo mật khác nhau. Việc dùng danh sách như vậy **không nên là cách tự động downgrade từ TLS sang plaintext**. Trong production, các endpoint dự phòng cần đáp ứng cùng chính sách bảo mật; nếu yêu cầu TLS, chỉ cấu hình broker URI TLS hợp lệ và trust configuration tương ứng.

## 8. Client ID: danh tính kết nối không phải correlation ID

Một số tên gần giống nhau nhưng vai trò hoàn toàn khác:

| Định danh | Phạm vi | Ví dụ |
| --- | --- | --- |
| **MQTT Client ID** | Nhận diện client session kết nối broker. | `telemetry-inbound-prod-1`. |
| **MQTT topic** | Namespace publish/subscribe của broker. | `sensors/room-17/temperature`. |
| **Message ID / eventId nghiệp vụ** | Nhận diện một event hoặc command để chống trùng và đối soát. | `evt-2026-1001`. |
| **Correlation ID** | Liên kết request, publish, ACK và log. | `trace-ord-1001`. |
| **Spring bean name** | Định danh component trong application context. | `mqttClientFactory`, `mqttPublisher`. |

Đặt cùng một Client ID trên hai MQTT client active có thể gây hiện tượng **đăng nhập mới đá kết nối cũ**, dẫn đến reconnect liên tục và message không ổn định. Nếu cùng process có inbound và outbound adapter, nên dùng ID riêng cho từng client.

Trong môi trường nhiều replica, có thể đặt `MQTT_INBOUND_CLIENT_ID` và `MQTT_OUTBOUND_CLIENT_ID` từ deployment identity hoặc instance ordinal. Tuy nhiên, Client ID **thay đổi sau restart** có thể ảnh hưởng việc tiếp tục một MQTT persistent session. Cần chọn chiến lược nhất quán:

- Muốn **duy trì subscription/session offline của một client logic**: dùng Client ID ổn định qua restart, tránh chạy trùng client cùng ID.
- Muốn **nhiều subscriber độc lập nhận cùng message**: dùng ID khác nhau và hiểu mỗi subscription/session có chính sách riêng.
- Muốn **chia tải trong nhóm consumer**: dùng broker feature shared subscriptions khi phù hợp phiên bản/giao thức, hoặc một kiến trúc hàng đợi khác; không dùng chung Client ID để giả lập competing consumers.

Không nhầm việc Client ID không trùng với **tính duy nhất của event**. Nếu hai instance đọc cùng outbox và publish cùng `eventId`, subscriber vẫn có thể nhận hai publication khác nhau dù mỗi publisher có Client ID riêng.

## 9. Session, QoS và cleanSession ở factory

Với MQTT 3.1.1/Paho v3, `MqttConnectOptions.setCleanSession(...)` điều khiển cách client/broker khởi tạo hoặc duy trì session.

| Tùy chọn | Ý nghĩa điển hình | Hợp với trường hợp |
| --- | --- | --- |
| `cleanSession=true` | Bắt đầu session sạch khi kết nối; trạng thái subscription/session cũ không được khôi phục theo cách session bền. | Consumer không yêu cầu giữ message lúc offline, publisher demo. |
| `cleanSession=false` | Cho phép session bền hơn với broker hỗ trợ; cần Client ID ổn định. | Subscriber cần khả năng nhận một số message QoS 1/2 khi reconnect theo broker policy. |
| QoS 0 | Delivery at-most-once ở tầng MQTT. | Telemetry có thể mất mẫu theo yêu cầu. |
| QoS 1 | Delivery at-least-once ở tầng MQTT, có thể trùng. | Event cần độ tin cậy cao hơn nhưng consumer phải idempotent. |
| QoS 2 | Handshake exactly-once ở **tầng MQTT protocol**. | Không thay thế transaction nghiệp vụ bên nhận. |

Factory đặt `cleanSession` cho các client sử dụng options đó. Trong ứng dụng ví dụ, **cả inbound và outbound** dùng chung option cleanSession. Nếu inbound cần `cleanSession=false` còn outbound muốn `true`, nên tạo **hai factory bean** với options riêng, inject qua `@Qualifier` để thể hiện chính sách rõ ràng.

`cleanSession=false` **không bảo đảm message vô hạn lúc offline**: broker có thể áp dụng giới hạn dung lượng, TTL, session policy, và message delivery còn phụ thuộc QoS, sự tồn tại của subscription và khả năng lưu trữ của broker.

### 9.1. QoS được đặt ở đâu?

`MqttConnectOptions` tập trung vào **connection/session**, không chọn QoS cho mọi publication hoặc subscription theo nghiệp vụ. QoS thường được cấu hình ở **adapter**:

~~~java
// Inbound subscription QoS
inboundAdapter.setQos(1);

// Outbound publish QoS mặc định
outboundHandler.setDefaultQos(1);
~~~

Đối với outbound, từng message có thể override bằng `MqttHeaders.QOS`. Đối với inbound, publisher QoS và subscription QoS cùng tác động đến QoS delivery hiệu lực. Không dùng `setCleanSession(false)` để thay thế việc chọn QoS và xử lý idempotency.

## 10. TLS, xác thực và broker URL bảo mật

Trong môi trường thật, đường kết nối giữa ứng dụng và broker thường cần mã hóa và xác minh máy chủ.

### 10.1. Chuyển từ TCP sang TLS

Cấu hình địa chỉ:

~~~properties
app.mqtt.broker-urls=ssl://mqtt.example.internal:8883
~~~

Với Paho v3, `ssl://` biểu thị MQTT over TLS. Còn cấu hình chứng chỉ tin cậy, hostname verification, client certificate nếu broker dùng mTLS và chính sách TLS phụ thuộc JVM, Paho, broker và hạ tầng.

Ví dụ JVM được cung cấp một trust store do đơn vị vận hành quản lý:

~~~text
-Djavax.net.ssl.trustStore=/path/to/truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Mật khẩu trust store (nếu có) phải được cấp qua secret management hoặc cơ chế bảo mật tương ứng, **không** ghi trực tiếp vào repo hay command history. Đường dẫn trên là minh họa; không phải file có sẵn.

**Cần xác minh thực tế:** có thể kết nối TLS thành công mà vẫn cần kiểm tra chain certificate, hostname, rotation và quyền publish/subscribe. Không vô hiệu hóa kiểm tra chứng chỉ hoặc cho phép tất cả trust managers để “sửa nhanh” lỗi TLS.

### 10.2. Username/password không thay thế TLS

~~~java
options.setUserName(username);
options.setPassword(password.toCharArray());
~~~

Đây là credential cấp MQTT CONNECT theo cách Paho v3 hỗ trợ. Khi dùng `tcp://` trên mạng không tin cậy, credentials và payload có thể bị lộ. Khi broker yêu cầu xác thực, hãy dùng **TLS** cùng credential/ACL.

Không log `MqttConnectOptions` bằng cách có thể làm lộ secret. Với hệ thống cần thay đổi password hoặc certificate khi đang chạy, phải thiết kế restart/reconnect/bean refresh theo lifecycle thay vì giả định thay một biến môi trường là kết nối hiện tại được cập nhật ngay.

### 10.3. ACL topic và least privilege

Ví dụ:

| Client | Quyền nên có | Không nên có |
| --- | --- | --- |
| Inbound telemetry | Subscribe `sensors/+/temperature`. | Subscribe mọi topic quản trị không liên quan. |
| Outbound command | Publish `devices/+/commands` theo vùng thiết bị được cấp phép. | Publish tùy ý tới topic tenant khác. |
| Audit subscriber | Subscribe topic audit được phép. | Publish lệnh điều khiển nếu không được ủy quyền. |

Broker ACL quyết định principal/client có quyền publish/subscribe topic nào. Ứng dụng còn phải kiểm tra tenant/device ID từ request trước khi tạo MQTT topic. Có URL và credential đúng **chưa đủ** chứng minh một command được phép gửi tới thiết bị cụ thể.

## 11. Timeout, keepalive và reconnect: ba mục tiêu khác nhau

Một số thuộc tính nghe giống nhau nhưng hoạt động ở các giai đoạn khác:

| Thuộc tính | Đơn vị thường dùng | Tác dụng |
| --- | --- | --- |
| `MqttConnectOptions.setConnectionTimeout(10)` | **Giây** | Giới hạn thời gian cho một lần thiết lập connection theo Paho. |
| `MqttConnectOptions.setKeepAliveInterval(30)` | **Giây** | Điều khiển MQTT keepalive để phát hiện kết nối không hoạt động theo protocol. |
| `MqttPahoMessageHandler.setCompletionTimeout(5000)` | **Mili giây** | Thời hạn chờ hoàn tất thao tác publish theo handler/client. |
| `MqttPahoMessageDrivenChannelAdapter.setRecoveryInterval(10000)` | **Mili giây** | Khoảng phục hồi/retry connection của inbound adapter theo API. |
| Timeout của business ACK | Do ứng dụng tự quy định | Đợi thiết bị/subscriber xác nhận thực hiện command, nếu có. |

**Không đồng nhất connection timeout và completion timeout.** Ví dụ kết nối có thể được mở thành công sau 2 giây, nhưng publish QoS 1 vẫn có thể chậm do broker hoặc mạng. Completion timeout 5 giây cũng không chứng minh thiết bị đã thực hiện lệnh trong 5 giây.

### 11.1. Ai quản lý reconnect?

Paho có khả năng automatic reconnect, và Spring Integration inbound adapter cũng có logic recovery/lifecycle theo phiên bản. Khi cấu hình, cần xác định **một chiến lược kết nối/phục hồi rõ ràng**; không mặc định bật mọi cơ chế reconnect cùng lúc mà không kiểm thử tương tác.

Nên kiểm tra:

1. Broker chưa chạy khi application startup.
2. Broker disconnect khi subscriber đang xử lý message.
3. Network chỉ bị gián đoạn ngắn, không mất DNS.
4. Credential bị thu hồi, reconnect không bao giờ thành công cho đến khi sửa config.
5. Client ID trùng do deploy hai instance cùng lúc.
6. Broker failover giữa hai URI và session có/không được đồng bộ.

Chính sách phải có backoff, metric, alert và giới hạn tải reconnect. Nếu một ứng dụng có hàng nghìn client, các lần reconnect cùng lúc có thể tạo “thundering herd”; cần điều phối rollout và backoff.

### 11.2. Keepalive không phải heartbeat nghiệp vụ

MQTT keepalive cho biết kết nối protocol còn hoạt động, không cho biết **cảm biến đã gửi dữ liệu hợp lệ** hoặc thiết bị đã nhận lệnh gần nhất. Nếu cần phát hiện thiết bị offline, thiết kế heartbeat/state event/Last Will và timestamp, cùng quy tắc đánh giá từ dữ liệu thực tế.

## 12. Dùng nhiều factory bean khi chính sách khác nhau

Trong hệ thống nhiều chức năng, việc dùng chung một factory có thể làm cấu hình ràng buộc không mong muốn:

~~~mermaid
flowchart TB
    OPT1["Inbound options<br/>cleanSession=false<br/>Client ID ổn định"]
    OPT2["Outbound options<br/>cleanSession=true<br/>Client ID riêng"]
    F1["telemetryClientFactory"]
    F2["commandsClientFactory"]
    IN["MQTT inbound adapter"]
    OUT["MQTT outbound handler"]
    OPT1 --> F1 --> IN
    OPT2 --> F2 --> OUT
~~~

Ví dụ chỉ mô tả ý tưởng:

~~~java
@Bean("telemetryClientFactory")
MqttPahoClientFactory telemetryClientFactory() {
    var options = new MqttConnectOptions();
    options.setServerURIs(new String[] {
            "ssl://mqtt.example.internal:8883"
    });
    options.setCleanSession(false);
    var factory = new DefaultMqttPahoClientFactory();
    factory.setConnectionOptions(options);
    return factory;
}

@Bean("commandsClientFactory")
MqttPahoClientFactory commandsClientFactory() {
    var options = new MqttConnectOptions();
    options.setServerURIs(new String[] {
            "ssl://mqtt.example.internal:8883"
    });
    options.setCleanSession(true);
    var factory = new DefaultMqttPahoClientFactory();
    factory.setConnectionOptions(options);
    return factory;
}
~~~

Đây là **snippet minh họa**, không thay thế cấu hình TLS/credentials đầy đủ và không được thêm cùng bean name với ví dụ ở mục 6 mà không chủ động tổ chức lại context.

Khi có hai factory cùng kiểu `MqttPahoClientFactory`, Spring injection có thể mơ hồ. Dùng `@Qualifier("telemetryClientFactory")` hoặc `@Qualifier("commandsClientFactory")` tại các method tạo adapter. Đồng thời tránh duplicate Client ID giữa các adapter dù chúng dùng factory khác nhau.

Nên tái sử dụng một helper tạo `MqttConnectOptions` an toàn để không copy cùng secret/TLS settings sai lệch ở nhiều class; vẫn giữ chính sách session/reconnect riêng cho từng adapter theo yêu cầu.

## 13. Xử lý lỗi kết nối và trạng thái message

Một client factory cấu hình sai có thể khiến adapter không kết nối được, nhưng ngay cả khi broker hoạt động cũng vẫn có những lỗi về message delivery.

~~~mermaid
flowchart TD
    CFG["Broker URI / auth / TLS"]
    CLIENT{"Paho connect thành công?"}
    ADAPTER["Inbound subscribe / outbound publish"]
    CH["MessageChannel"]
    BUSINESS["Validate / DB / HTTP / Kafka"]
    ERROR["Error flow / retry / quarantine / outbox"]
    CFG --> CLIENT
    CLIENT -->|"Có"| ADAPTER --> CH --> BUSINESS
    CLIENT -->|"Không"| ERROR
    ADAPTER -. "publish/subscription lỗi" .-> ERROR
    BUSINESS -. "nghiệp vụ lỗi" .-> ERROR
~~~

| Loại lỗi | Vị trí phát sinh | Biện pháp phù hợp |
| --- | --- | --- |
| URI không hợp lệ | Parse options hoặc lúc connect. | Validate URI/scheme và test cấu hình trước deploy. |
| DNS/firewall/port sai | Kết nối TCP/TLS. | Kiểm tra network route, DNS và health của broker. |
| TLS trust/hostname không hợp lệ | TLS handshake. | Sửa certificate/trust configuration, không vô hiệu hóa xác minh. |
| Username/password hoặc ACL sai | CONNECT/SUBSCRIBE/PUBLISH. | Sửa secret/quyền và fail rõ ràng; tránh retry vô hạn cấu hình sai. |
| Client ID trùng | Trong quá trình kết nối. | Tạo ID riêng hoặc đảm bảo chỉ một client active cho session đó. |
| Publish completion timeout | Outbound handler/client. | Xem kết quả chưa chắc chắn; retry theo idempotency và outbox. |
| Inbound nhận payload sai schema | Converter/validator downstream. | Quarantine và báo lỗi dữ liệu, không sửa broker URL. |
| Downstream DB/HTTP không sẵn sàng | Sau `MessageChannel`. | Retry/transaction ở tầng nghiệp vụ, không chỉ reconnect MQTT. |

**Lỗi message không thể giải quyết chỉ bằng đổi broker URL.** Khi ứng dụng đã nhận message từ broker nhưng DB ghi thất bại, cơ chế reconnect có thể hoàn toàn không liên quan. Cần thiết kế error channel, retry, DLQ/quarantine, idempotency và policy xác nhận tại endpoint thích hợp.

### 13.1. MQTT QoS không phải transaction nghiệp vụ

- Với MQTT QoS 1, broker/client có thể phát lại message làm **duplicate delivery**.
- Với QoS 2, exactly-once được định nghĩa ở mức **MQTT protocol delivery**, không bao gồm transaction database hay việc điều khiển thiết bị.
- Với message retained, subscriber mới có thể nhận một **state snapshot cũ**, không nhất thiết là sự kiện mới.
- Với outbound publish hoàn tất nhưng application crash trước khi cập nhật outbox, lần chạy sau có thể publish lại cùng event ID.

Do đó payload nên mang `eventId`/`commandId` ổn định; downstream dùng unique constraint/idempotency và có trạng thái đã xử lý. Khi broker không trả ACK kịp, đừng phát lại lệnh quan trọng mà không kiểm tra kết quả trước đó.

## 14. Vòng đời của factory và adapter trong Spring

`MqttPahoClientFactory` là bean chứa quy tắc tạo MQTT client; bản thân factory **không có subscription được cấu hình** cho đến khi adapter inbound sử dụng nó. Outbound adapter cũng không publish chỉ vì factory tồn tại.

Khi ứng dụng vận hành, cần hiểu các giai đoạn:

1. **Tạo bean:** Spring khởi tạo options, factory và adapter. Chỗ này phát hiện sớm config thiếu hoặc không hợp lệ nếu có validation.
2. **Khởi động endpoint:** inbound adapter có thể kết nối và subscribe theo `SmartLifecycle`/framework. Outbound client có thể cần kết nối khi handler bắt đầu hoạt động.
3. **Xử lý message:** broker delivery → adapter → channel → flow hoặc flow → handler → broker; lỗi có thể phát sinh ở bất kỳ chặng nào.
4. **Phục hồi kết nối:** áp dụng recovery/reconnect policy, có thể cần đăng ký lại subscription theo session.
5. **Shutdown:** ngừng nhận yêu cầu mới, cho xử lý in-flight cơ hội hoàn tất và giải phóng tài nguyên client.

Nếu đổi broker URI hoặc credential trong deployment config, các **bean đã tạo trước đó không tự cập nhật** chỉ vì file property bị chỉnh. Thường cần refresh/restart có kiểm soát hoặc một cơ chế thay cấu hình chủ động; phải xác minh session/reconnect và không làm mất dữ liệu.

### 14.1. Monitoring cần có

Các tín hiệu vận hành quan trọng:

- Connected/disconnected state, số lần reconnect, thời gian downtime.
- URI broker đang sử dụng, nhưng **không log password, token hoặc khóa cá nhân**.
- Số publish attempts, publish success/timeout, subscribe failures và ACL rejection.
- Số message inbound/outbound, latency xử lý và lượng message queue.
- Số duplicate/retry theo `eventId`, trạng thái outbox/quarantine.
- Cảnh báo khi Client ID trùng hoặc khi client liên tục chuyển broker.

Quan sát kết nối có ích, nhưng không phải thước đo cuối cho xử lý nghiệp vụ. Ví dụ biểu đồ “MQTT connected = true” không bảo đảm DB tiêu thụ event đang hoạt động.

## 15. Kiểm thử bean factory không cần broker

Vì `MqttConnectOptions` và `MqttPahoClientFactory` là các Spring bean độc lập, có thể kiểm thử cấu hình **không mở kết nối MQTT**. Tránh khởi động toàn bộ `MqttFactoryApplication` trong unit test nếu điều đó làm inbound adapter tự động connect tới broker.

Thêm dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo `MqttConnectionConfigurationTest.java` trong package `demo.mqttfactory`:

~~~java
package demo.mqttfactory;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = MqttConnectionConfiguration.class)
@TestPropertySource(properties = {
        "app.mqtt.broker-urls=tcp://mqtt-a:1883,tcp://mqtt-b:1883",
        "app.mqtt.connection-timeout-seconds=8",
        "app.mqtt.keep-alive-seconds=45",
        "app.mqtt.clean-session=false",
        "app.mqtt.username=test-client",
        "app.mqtt.password=test-secret"
})
class MqttConnectionConfigurationTest {

    @Autowired
    MqttConnectOptions options;

    @Autowired
    MqttPahoClientFactory factory;

    @Test
    void createsOptionsAndClientFactoryWithoutNetwork() {
        assertNotNull(factory);
        assertArrayEquals(
                new String[] {
                        "tcp://mqtt-a:1883",
                        "tcp://mqtt-b:1883"
                },
                options.getServerURIs());
        assertEquals(8, options.getConnectionTimeout());
        assertEquals(45, options.getKeepAliveInterval());
        assertEquals("test-client", options.getUserName());
        assertTrue(!options.isCleanSession());
    }
}
~~~

Test này chứng minh:

- Spring có thể bind các giá trị `app.mqtt.*` vào method tạo options.
- Hai broker URI được parse/trim và đưa vào Paho.
- Timeout/keepalive/clean session đã vào options đúng đơn vị.
- Factory bean được tạo nhưng không cần broker đang mở.

**Test này chưa chứng minh MQTT connection thành công.** Nó không xác minh DNS, TLS, secret production, ACL, subscription, failover, publish hay reconnect. Những thứ đó cần integration test với broker thật.

### 15.1. Kiểm thử trường hợp cấu hình lỗi

Bổ sung các test fail-fast cho:

1. `app.mqtt.broker-urls` rỗng hoặc chỉ có dấu phẩy/khoảng trắng.
2. URI có scheme không được demo hỗ trợ như `http://...`.
3. Connection timeout âm hoặc keepalive không hợp lệ — nên validate thêm theo chính sách trước khi tạo options.
4. Production profile thiếu secret hoặc thiếu TLS.
5. Inbound và outbound Client ID bị trùng; có thể dùng một validation bean hoặc integration test tại startup để phát hiện.
6. Config có hai factory cùng kiểu nhưng quên `@Qualifier` ở adapter.

Không đưa password production vào source/test logs. Mật khẩu trong example test chỉ là chuỗi giả được dùng để minh họa property binding.

## 16. Kiểm thử kết nối end-to-end với broker

Khi broker thử nghiệm đã được khởi động và MQTT CLI được cài, một kiểm thử thủ công đơn giản:

**Terminal A — subscribe topic:**

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-cli-subscriber-1 \
  -t 'devices/+/commands' -v
~~~

**Terminal B — publish một command:**

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -i demo-cli-publisher-1 \
  -t 'devices/demo-1/commands' \
  -q 1 \
  -m '{"commandId":"cmd-1001","action":"TURN_ON"}'
~~~

Chạy Spring Boot ứng dụng với broker URI cùng môi trường. Có thể publish từ `DeviceCommandPublisher` để kiểm tra **Spring outbound handler → broker**. Muốn kiểm tra **Spring inbound adapter**, publish một bản tin vào topic filter `sensors/+/temperature`.

Ví dụ:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -i demo-cli-telemetry-1 \
  -t 'sensors/room-17/temperature' \
  -q 1 \
  -m '{"eventId":"evt-1001","celsius":26.5}'
~~~

CLI chỉ hoạt động nếu broker cho phép các kết nối như ví dụ và công cụ Mosquitto đã cài. Nếu broker yêu cầu TLS/credentials, phải dùng lệnh và chứng chỉ phù hợp thay vì tắt bảo mật.

### 16.1. Bộ kịch bản quan trọng

| Thử nghiệm | Cách làm | Kết quả cần quan sát |
| --- | --- | --- |
| Một broker URI đúng | Connect tới broker test đang chạy. | Adapter khởi động và xử lý đúng subscription/publication. |
| URI không reachable | Trỏ tới host/port sai. | Lỗi kết nối được ghi nhận; không coi app xử lý message thành công. |
| Hai broker URI dự phòng | Dùng cluster test hỗ trợ failover. | Client thử endpoint phù hợp và subscription/side effect được kiểm chứng lại. |
| TLS certificate sai | Dùng broker cert không được trust. | Handshake thất bại đúng cách, không “bypass TLS”. |
| ACL publish/subscribe sai | Dùng principal thiếu quyền topic. | Có thông tin lỗi, không âm thầm mất message. |
| Client ID trùng | Cho hai client dùng cùng ID. | Quan sát kết nối cạnh tranh, áp dụng chiến lược định danh đúng. |
| `cleanSession=false` | Disconnect/reconnect subscriber với ID ổn định. | Kiểm tra offline delivery theo QoS/session của broker, không suy luận tự động. |
| Broker restart | Khởi động lại broker trong lúc truyền message. | Recovery, reconnect, redelivery/duplicate theo hợp đồng. |
| Downstream lỗi | Handler nhận MQTT nhưng DB fail. | Error flow/retry hoặc quarantine được kiểm chứng, không chỉ nhìn broker health. |
| Nhiều message nhanh | Publish vượt tốc độ handler. | Queue/backpressure được đo, không cạn bộ nhớ/thread. |

Để xác nhận hệ thống hoàn chỉnh, cần đối chiếu số message tại broker, tại Spring channel và tại trạng thái cuối của database/thiết bị. Test chỉ nhìn MQTT client “connected” chưa đủ.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không kết nối được dù broker chạy. | Host/port sai, `localhost` trỏ về container khác, firewall. | Kiểm tra DNS, network namespace và broker listener. |
| Broker URI báo không hợp lệ. | Nhầm `https://`/`mqtt://` với Paho TCP/TLS URI. | Dùng scheme được client hỗ trợ; phân biệt URI và topic. |
| TLS handshake failure. | CA/truststore thiếu, hostname hoặc certificate chain sai. | Sửa trust configuration, không tắt certificate verification. |
| Unauthorized khi connect. | Username/password sai hoặc broker policy thay đổi. | Cập nhật secrets/quyền an toàn và restart/reconnect có kiểm soát. |
| Connect được nhưng không subscribe. | ACL topic sai, filter sai, inbound adapter không start. | Kiểm tra subscription, broker logs và adapter lifecycle. |
| Publish không đến thiết bị. | Topic sai, publisher ACL, subscriber offline, QoS/session policy. | Kiểm tra topic thực, broker delivery và ACK nghiệp vụ riêng. |
| Hai instance ngắt kết nối liên tục. | Trùng Client ID. | Tạo định danh duy nhất hoặc quản lý active session ổn định. |
| Không nhận offline message sau failover. | Hai broker không chia sẻ MQTT session. | Xem topology cluster/session và kiểm thử broker thực. |
| Đặt nhiều URL nhưng message không nhân bản. | `setServerURIs` không phải fan-out publisher. | Dùng replication hoặc hai outbound flow riêng nếu cần nhiều đích. |
| Timeout publish nhưng broker có thể đã nhận. | ACK MQTT bị mất hoặc chậm. | Không retry mù; outbox và idempotency theo event ID. |
| Đổi biến môi trường mà kết nối không đổi. | Bean/options đã được tạo từ trước. | Dùng restart/reload có kiểm soát và xác minh trạng thái. |
| MQTT kết nối tốt nhưng dữ liệu không có trong DB. | Lỗi validation/downstream, error channel không được xử lý. | Quan sát đầy đủ IntegrationFlow, transaction và retry. |

## 18. Bài thực hành: thiết kế MQTT connection factory cho hai môi trường

**Tình huống:** một hệ thống nhận telemetry MQTT từ thiết bị và publish command điều khiển. Development dùng broker local; production dùng cụm broker TLS có hai endpoint.

Yêu cầu:

1. Tạo `MqttConnectOptions` bean từ `app.mqtt.broker-urls`, timeout, keepalive, clean session và credential.
2. Khai báo `DefaultMqttPahoClientFactory` dùng options đó, inject vào một inbound adapter và một outbound handler.
3. Quy định Client ID riêng cho inbound/outbound, phát hiện trùng ID ngay lúc startup nếu cả hai adapter cùng dùng một ID.
4. Development dùng `tcp://localhost:1883`; production chỉ dùng `ssl://mqtt-a:8883,ssl://mqtt-b:8883` với truststore đúng.
5. Đặt TLS/username/password qua secrets; không commit password vào `application.properties`.
6. Inbound subscribe `sensors/+/temperature` ở QoS 1, phát vào `mqtt.inbound` và validate JSON.
7. Outbound publish tới `devices/<deviceId>/commands` với QoS 1, retained=false, payload mang `commandId`.
8. Mô phỏng broker URI đầu tiên không reachable, quan sát fallback và xác minh session/subscription với broker cluster.
9. Test hai replica cùng Client ID rồi sửa chiến lược nhận diện, giải thích ảnh hưởng đến persistent session.
10. Thực hiện test xử lý duplicate, broker ACK đến muộn, DB failure và restart để chứng minh cách khôi phục ứng dụng.

**Tiêu chí đạt:** cấu hình kết nối được tách khỏi flow, URI và scheme hợp lệ, client IDs/session rõ ràng, TLS/ACL đúng, observable reconnect và test chứng minh không nhầm broker delivery với nghiệp vụ hoàn tất.

## 19. Câu hỏi tự kiểm tra

1. `MqttPahoClientFactory` khác `MqttConnectOptions` như thế nào?
2. Chỉ tạo factory bean đã làm MQTT client subscribe/publish chưa?
3. Broker URI khác MQTT topic ở chỗ nào?
4. Vì sao `tcp://localhost:1883` có thể sai khi chạy trong Docker/Kubernetes?
5. `ssl://` chỉ định điều gì, và còn cần kiểm tra gì để kết nối bảo mật?
6. `setServerURIs` có tự publish cùng message lên mọi broker không?
7. Khi chuyển sang broker dự phòng không chia sẻ session, rủi ro dữ liệu nào xuất hiện?
8. Vì sao inbound và outbound cùng factory vẫn cần hai Client ID?
9. Dùng `cleanSession=false` nhưng Client ID thay đổi mỗi restart có vấn đề gì?
10. Connection timeout và completion timeout khác nhau thế nào?
11. Keepalive có chứng minh cảm biến hoạt động bình thường không?
12. Khi credential thay đổi, factory bean đã chạy có tự reload options không?
13. Một MQTT QoS 2 publication có bảo đảm database ghi đúng một lần không?
14. Có nên dùng retained=true cho lệnh bật thiết bị một lần không?
15. Unit test factory không broker kiểm chứng được gì và không kiểm chứng được gì?
16. Nếu ứng dụng nhận MQTT message rồi DB lỗi, reconnect broker có giải quyết được không?
17. Khi nào nên dùng hai factory riêng thay vì một factory chung?
18. Làm thế nào giới hạn việc publisher tự tạo topic theo một header không đáng tin cậy?

**Gợi ý:** Factory tạo client từ connection options; broker URI dùng cho kết nối, topic dùng cho publish/subscribe; client ID/session liên quan hoạt động tại broker; lỗi downstream và side effect trùng cần xử lý ngoài tầng kết nối.

## 20. Kết luận

**MQTT client factory và broker URL** là nền tảng kết nối MQTT của Spring Integration. `MqttConnectOptions` xác định broker URI, timeout, keepalive, session và credential; `DefaultMqttPahoClientFactory` chuyển cấu hình đó cho `MqttPahoMessageDrivenChannelAdapter` hoặc `MqttPahoMessageHandler`. Các adapter tiếp tục làm nhiệm vụ subscribe/publish và gắn kết với `MessageChannel`/`IntegrationFlow`.

Khi triển khai **SPRING_INTEGRATION_ADAPTERS** với MQTT, hãy tách rõ **cấu hình connection**, **định danh client/session**, **hợp đồng topic/payload/headers** và **thành công nghiệp vụ**. Nhiều broker URL là cơ chế lựa chọn endpoint kết nối, không phải multicast hay transaction; TLS/ACL phải được xác thực; retry, outbox, idempotency và kiểm thử end-to-end quyết định hệ thống có thể phục hồi an toàn khi broker, ứng dụng hoặc downstream gặp lỗi.

