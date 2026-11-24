# Payload conversion cho MQTT message

## 1. Bài toán: byte của MQTT khác object trong Spring

MQTT truyền **payload dưới dạng byte**. Một broker MQTT không tự hiểu rằng chuỗi byte đó là JSON, ảnh JPEG, protobuf hay một số đo nhiệt độ. Trong khi đó, Spring Integration sử dụng `Message<?>` với payload có kiểu Java như `String`, `byte[]`, `TemperatureReading`, kèm `MessageHeaders`. Để tích hợp ổn định, ứng dụng cần chuyển đổi dữ liệu tại đúng ranh giới giữa **MQTT transport** và **hợp đồng nghiệp vụ**.

Ví dụ, một cảm biến publish:

~~~text
MQTT topic: sensors/device-17/temperature
MQTT QoS:   1
MQTT bytes: 7B 22 65 76 65 6E 74 49 64 22 3A ... 7D
Diễn giải UTF-8:
{"eventId":"evt-1001","deviceId":"device-17","celsius":26.5}
~~~

Dòng byte chỉ trở thành `TemperatureReading` khi ứng dụng **chủ động quyết định encoding và parse schema JSON**. Nếu một thiết bị khác dùng protobuf, cũng topic đó nhưng payload nhị phân, việc ép mọi dữ liệu thành `String` sẽ phá hợp đồng và có thể làm hỏng byte.

Bài **“Payload conversion cho MQTT message”** thuộc chương **Adapter MQTT** của module **SPRING_INTEGRATION_ADAPTERS**. Module này kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời xử lý hợp đồng message, lỗi và vòng đời kết nối. Đối với MQTT, chuyển đổi payload là nơi nối ranh giới protocol vào các flow xử lý dữ liệu đó.

Sau bài học, người học có thể:

1. Phân biệt **MQTT payload bytes**, **Spring payload**, **message headers**, **DTO nghiệp vụ**.
2. Cấu hình `DefaultPahoMessageConverter` trong MQTT inbound/outbound adapter.
3. Chọn `String` hay `byte[]` theo hợp đồng dữ liệu; hiểu vì sao phải thống nhất charset.
4. Parse/serialize JSON qua Jackson ở **transformer/handler** thay vì trông chờ MQTT broker hiểu schema.
5. Phân biệt topic/QoS/retained của giao thức với dữ liệu ứng dụng truyền trong payload.
6. Tạo Spring Boot flow nhận message JSON, validate DTO và đưa vào business sink; publish DTO ra broker.
7. Giữ nguyên byte cho payload nhị phân, tránh chuyển đổi hai lần làm sai dữ liệu.
8. Thiết kế kiểm thử không có broker và kiểm thử end-to-end qua broker, gồm trường hợp lỗi encoding/schema.
9. Quy hoạch error flow, quarantine, giới hạn kích thước payload, idempotency và backward compatibility.

**Quy tắc cốt lõi:** `DefaultPahoMessageConverter` xử lý **MQTT message ↔ Spring Message**. Jackson/codec nghiệp vụ xử lý **JSON hoặc binary schema ↔ Java DTO**. Đây là hai lớp khác nhau, không nên gộp làm một phép biến đổi “magic”.

## 2. Vị trí của conversion trong hai chiều tích hợp

~~~mermaid
flowchart LR
    DEVICE["Thiết bị / Publisher"]
    BROKER[("MQTT broker")]
    PAHO["Eclipse Paho MQTT client"]
    CONVERTER["DefaultPahoMessageConverter"]
    CH["mqtt.telemetry.in<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>JSON parser + validation"]
    DTO["TemperatureReading"]
    DB[("Database")]
    DEVICE -->|"PUBLISH bytes/topic/QoS"| BROKER
    BROKER --> PAHO --> CONVERTER
    CONVERTER -->|"Message<String> hoặc Message<byte[]>"| CH
    CH --> FLOW --> DTO --> DB
~~~

Chiều outbound là quá trình đảo ngược ở ranh giới transport:

~~~mermaid
flowchart LR
    SRC["Java DTO / business event"]
    JSON["Jackson serializer / binary encoder"]
    CH["mqtt.publish.requests<br/>MessageChannel"]
    HANDLER["MqttPahoMessageHandler"]
    CONV["DefaultPahoMessageConverter"]
    BROKER[("MQTT broker")]
    SUB["Subscriber"]
    SRC --> JSON -->|"Message<String> hoặc Message<byte[]>"| CH
    CH --> HANDLER --> CONV
    CONV -->|"MQTT PUBLISH bytes"| BROKER --> SUB
~~~

### 2.1. Ranh giới nào chịu trách nhiệm điều gì?

| Lớp | Nhận dữ liệu | Xuất dữ liệu | Ai chịu trách nhiệm? |
| --- | --- | --- | --- |
| MQTT protocol | Topic, byte payload, QoS, retained flag. | Packet gửi qua broker. | Client MQTT/Paho và broker. |
| MQTT adapter converter | MQTT message từ Paho hoặc Spring message từ flow. | Spring `Message<?>` hoặc Paho MQTT message. | `DefaultPahoMessageConverter`/converter tùy biến. |
| Data format decoder/encoder | `String` JSON, `byte[]` protobuf, Avro, CBOR. | DTO Java hoặc bytes/text có schema. | Jackson/protobuf codec/transformer do ứng dụng chọn. |
| Business validation | DTO đã parse. | Event được chấp nhận hoặc lỗi. | Handler/service/validator nghiệp vụ. |
| Business effect | Event hợp lệ. | Ghi DB, gọi HTTP, gửi JMS/Kafka, tạo ACK. | Spring Integration flow và downstream service. |

Chuyển đổi thành công ở một lớp **không đồng nghĩa** lớp tiếp theo hợp lệ. JSON có cú pháp đúng nhưng `deviceId` rỗng vẫn là dữ liệu nghiệp vụ sai; MQTT packet đã được broker nhận nhưng DB ghi lỗi vẫn là tác vụ chưa hoàn tất.

## 3. MQTT message có những trường gì và không có gì?

Một MQTT PUBLISH theo MQTT 3.1.1 mang những phần như **topic name**, QoS, retained flag, packet identifier tùy QoS và **payload byte sequence**. MQTT v3 không tự mang một schema Java, không có Content-Type tổng quát như HTTP và không tự tuần tự hóa toàn bộ Spring `MessageHeaders`.

Ví dụ:

~~~text
PUBLISH:
  topic  = sensors/device-17/temperature
  qos    = 1
  retain = false
  body   = bytes UTF-8 của JSON

Sau inbound conversion:
  Spring Message<String>:
    payload = "{\"eventId\":\"evt-1001\",...}"
    headers[RECEIVED_TOPIC] = "sensors/device-17/temperature"
    headers[...]           = metadata MQTT tùy converter/phiên bản
~~~

Khi publish outbound, các header như `MqttHeaders.TOPIC`, `MqttHeaders.QOS` và `MqttHeaders.RETAINED` được converter/handler sử dụng để đặt thuộc tính MQTT publication. Một header ứng dụng như `correlationId` **không tự được gửi thành MQTT v3 metadata**; nếu subscriber cần giá trị đó, nó phải nằm trong **payload schema** hoặc một contract được implement rõ.

### 3.1. Topic nội bộ và topic giao thức

| Giá trị | Ví dụ | Vai trò |
| --- | --- | --- |
| Spring input channel | `mqtt.telemetry.in` | Nơi adapter chuyển Spring message vào flow. |
| MQTT received topic | `sensors/device-17/temperature` | Topic cụ thể broker đã giao PUBLISH tới inbound client. |
| MQTT outbound topic | `devices/device-17/commands` | Topic mà outbound handler publish. |
| Subscriber topic filter | `sensors/+/temperature` | Quy tắc broker dùng để phân phối tới subscriber. |
| Payload content type do ứng dụng quy ước | `application/json; charset=utf-8` | Schema/encoding của bytes, **không phải trường mặc định của MQTT v3**. |

Trong Spring Integration, hằng `MqttHeaders.RECEIVED_TOPIC` dùng để đọc topic nguồn của inbound message, còn `MqttHeaders.TOPIC` dùng để chỉ định topic publish outbound. Không tự động lấy inbound received topic làm outbound destination khi thực hiện bridge giữa các giao thức; cần xác định đích theo business policy.

## 4. DefaultPahoMessageConverter làm gì?

`DefaultPahoMessageConverter` là converter MQTT mặc định thường được dùng với các adapter Paho của Spring Integration. Nó kết nối dữ liệu giữa biểu diễn MQTT và biểu diễn Spring message.

### 4.1. Inbound: byte[] đến payload Spring

Trong cấu hình text phổ biến, converter có thể diễn giải byte payload nhận từ MQTT thành `String` theo charset được cấu hình/phiên bản mặc định. Điều này tiện với JSON text hoặc bản tin trạng thái `ONLINE`/`OFFLINE`.

~~~java
var adapter = new MqttPahoMessageDrivenChannelAdapter(
        "telemetry-subscriber-1",
        mqttClientFactory,
        "sensors/+/temperature");

adapter.setConverter(new DefaultPahoMessageConverter());
adapter.setOutputChannel(telemetryInputChannel);
~~~

Với converter mặc định ở cấu hình text, downstream thường nhận `Message<String>`. **Đây không phải parse JSON thành DTO**; payload vẫn là chuỗi JSON nguyên bản.

### 4.2. Inbound: giữ payload dưới dạng byte[]

Nếu nguồn publish payload nhị phân, hoặc ứng dụng muốn tự kiểm soát giải mã/charset, hãy chọn byte array:

~~~java
var converter = new DefaultPahoMessageConverter();
converter.setPayloadAsBytes(true);

adapter.setConverter(converter);
~~~

Bây giờ flow downstream có thể nhận `Message<byte[]>` và tự kiểm tra signature/magic bytes, decompress, decode protobuf hoặc đọc JSON UTF-8 bằng parser được cấu hình tường minh.

**Quan trọng:** không biến byte của ảnh, file ZIP, protobuf hoặc dữ liệu mã hóa thành text chỉ vì muốn log dễ đọc. Một phép decode text không hợp lệ có thể thay thế ký tự, làm sai hash/signature hoặc khiến round-trip thành bytes không còn giống bản gốc.

### 4.3. Outbound: từ Spring message sang MQTT bytes

Outbound adapter như `MqttPahoMessageHandler` gọi converter để tạo Paho MQTT message. Với payload `String`, converter chuyển text thành bytes theo encoding; với `byte[]`, nó có thể phát dữ liệu nhị phân mà không cần qua JSON/text.

~~~java
var handler = new MqttPahoMessageHandler(
        "events-publisher-1", mqttClientFactory);

handler.setDefaultTopic("events/default");
handler.setDefaultQos(1);
handler.setDefaultRetained(false);
handler.setConverter(new DefaultPahoMessageConverter());
handler.setAsync(false);
~~~

Không mặc định gửi DTO Java như `TemperatureReading` thẳng vào handler rồi chờ thiết bị nhận JSON. Hãy **serialize DTO** trước khi đặt message vào outbound channel; nếu muốn converter tùy biến nhận DTO trực tiếp, phải thiết kế rõ API, schema, metadata và test.

### 4.4. Converter có thể nhận biết nội dung theo topic không?

`DefaultPahoMessageConverter` không phải schema registry hay JSON parser thông minh dựa trên tên topic. Nó chuyển dữ liệu transport, không biết `sensors/+/temperature` phải là `TemperatureReading` còn `sensors/+/humidity` phải là `HumidityReading`. Phần đó thuộc transformer, router và validator do ứng dụng cấu hình.

## 5. String, byte[] hay Java DTO: chọn ở đâu?

| Kiểu Spring payload | Khi thích hợp | Chú ý |
| --- | --- | --- |
| `String` | Text UTF-8, JSON, trạng thái `ONLINE/OFFLINE`, CSV nhỏ. | Phải thống nhất charset, size limit, schema và validate nội dung. |
| `byte[]` | Protobuf, CBOR, nén, dữ liệu mã hóa, ảnh hoặc payload không chắc encoding. | Bảo toàn bytes; có decoder/checksum/signature riêng. |
| Java record/DTO | Tầng nghiệp vụ sau parse/validate; trước serialize outbound. | MQTT broker không hiểu Java object; cần serialization contract. |
| `Message<String>` | Vừa có JSON text vừa giữ được MQTT headers. | Header Spring nội bộ không tự đến subscriber bên kia broker. |
| `Message<byte[]>` | Giữ bytes và metadata MQTT để làm bước decode sau. | Tránh logging trực tiếp payload hoặc copy quá nhiều bytes. |

Không nên dùng Java serialization mặc định (`ObjectOutputStream`) làm giao thức liên thiết bị nếu không có hợp đồng được kiểm soát: nó kém tương thích đa ngôn ngữ, phức tạp về bảo mật, phiên bản và khó vận hành. Cũng không nên quyết định “byte[] hay String” theo kích thước duy nhất: bản chất dữ liệu, encoding và yêu cầu bảo toàn bytes mới là yếu tố chính.

### 5.1. Hai pipeline chuẩn

Text JSON:

~~~text
MQTT byte[] → DefaultPahoMessageConverter → String JSON
            → Jackson ObjectMapper → TemperatureReading
            → validate business fields → DB
~~~

Binary protobuf:

~~~text
MQTT byte[] → converter.payloadAsBytes=true → byte[]
            → Protobuf parser → TemperatureReading
            → validate business fields → DB
~~~

Outbound diễn ra theo chiều ngược lại: DTO → encoder đã chọn → `String` hoặc `byte[]` → MQTT converter → PUBLISH.

## 6. Charset và encoding: không được đoán từ tên topic

MQTT payload về cơ bản là một chuỗi byte. Với data format là JSON, cần công bố quy tắc encoding (thường chọn **UTF-8**) và tuân thủ cùng một cách ở producer/consumer.

Ví dụ cùng một ký tự Unicode có thể có biểu diễn byte khác nhau theo encoding; nếu một thiết bị gửi UTF-16 nhưng consumer giả định UTF-8, việc parse JSON có thể lỗi hoặc cho ra giá trị không mong đợi.

Một hợp đồng JSON phù hợp:

~~~text
Topic:          sensors/{deviceId}/temperature
Payload format: application/json
Encoding:       UTF-8
Schema:         temperature-reading/v1
Fields:         eventId, deviceId, celsius
Maximum bytes:  16 KiB theo policy ứng dụng
QoS:            1
Retained:       false
~~~

**Không tự suy ra charset từ MQTT Topic Name.** Tên topic và định dạng payload độc lập. MQTT 3.1.1 cũng không truyền HTTP `Content-Type` mặc định.

### 6.1. Decode rõ ràng khi đã giữ byte[]

Nếu ứng dụng chủ động chọn raw bytes, có thể dùng `StandardCharsets.UTF_8` trong decoder để tránh phụ thuộc charset mặc định của môi trường:

~~~java
String text = new String(rawBytes, StandardCharsets.UTF_8);
~~~

Tuy nhiên, constructor `String` có thể thay thế chuỗi byte UTF-8 không hợp lệ theo hành vi decoder. Khi yêu cầu **từ chối** byte lỗi thay vì thay ký tự, dùng decoder với `CodingErrorAction.REPORT`:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String text = decoder.decode(ByteBuffer.wrap(rawBytes)).toString();
~~~

Snippet cần import:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
~~~

Phương thức `decode(...)` có thể ném `CharacterCodingException`; hãy xử lý bằng flow lỗi/quarantine chứ không âm thầm bỏ message hoặc retry lỗi schema vô hạn.

### 6.2. Cần biết kích thước bytes trước khi parse

Giới hạn payload nên được kiểm ở cả broker, client và application, ví dụ không nhận JSON telemetry lớn hơn 16 KiB. `String.length()` đếm UTF-16 code units trong Java, **không tương đương số byte UTF-8**. Nếu cần enforce byte limit chuẩn, tốt nhất làm ở lúc dữ liệu còn là `byte[]` và kiểm tra `rawBytes.length` trước khi giải mã.

Nếu converter đã tạo `String` trước khi validate size, broker/client vẫn có thể đã cấp phát memory để đọc bytes; vì vậy giới hạn ở broker và decoder là lớp bảo vệ cần thiết.

## 7. JSON parsing là trách nhiệm của transformer/handler

Một publisher gửi JSON:

~~~json
{
  "eventId": "evt-1001",
  "deviceId": "device-17",
  "celsius": 26.5
}
~~~

`DefaultPahoMessageConverter` có thể chuyển bytes thành một `String` chứa JSON trên. Nhưng để có Java DTO cần một data format decoder như **Jackson**:

~~~java
TemperatureReading reading =
        objectMapper.readValue(json, TemperatureReading.class);
~~~

Parser biết cú pháp JSON và mapping sang fields của record; business validator biết giá trị có hợp lệ hay không. Hai nhiệm vụ phải tách biệt:

- **Parse error:** không phải JSON, sai kiểu dữ liệu, field bắt buộc không ánh xạ được.
- **Validation error:** JSON parse được nhưng `eventId` rỗng, `deviceId` ngoài allowlist, nhiệt độ ngoài dải được phép.
- **Authorization error:** topic hoặc device ID thuộc tenant không được phép.
- **Transport error:** MQTT connection, subscription, converter bytes/text hoặc broker policy.

Khi handler downstream ghi database lỗi, đừng coi đó là lỗi converter và gửi lại nguyên PUBLISH vô hạn mà không có idempotency.

### 7.1. Schema phải được version hóa

Một thiết bị đời cũ có thể gửi:

~~~json
{"deviceId":"device-17","value":26.5}
~~~

Trong khi hệ thống mới đòi:

~~~json
{
  "schemaVersion": 2,
  "eventId": "evt-1001",
  "deviceId": "device-17",
  "celsius": 26.5
}
~~~

Không nên chờ Jackson đoán ý nghĩa field `value`. Có thể dùng một bước transformer dựa trên `schemaVersion`, topic namespace hoặc mapping client đã được quản lý. Version là **hợp đồng ứng dụng**, không phải tính năng mặc định của `DefaultPahoMessageConverter`.

## 8. Ví dụ Spring Boot đầy đủ: MQTT JSON → DTO → xử lý

Ví dụ dùng Java 17+, Spring Boot, Spring Integration MQTT dựa trên Eclipse Paho MQTT v3 và Jackson. Chúng ta xây một application có:

- MQTT inbound message-driven adapter subscribe `sensors/+/temperature`.
- `DefaultPahoMessageConverter` chuyển MQTT text thành `Message<String>`.
- `IntegrationFlow` parse JSON qua Jackson thành `TemperatureReading`, kiểm tra topic khớp device ID và ghi sink.
- MQTT outbound handler dùng cùng factory nhưng **Client ID khác**, publish JSON từ DTO lên broker.
- Một unit/integration test chỉ nạp flow, **không** mở network.

Ví dụ có thể chạy với broker test `tcp://localhost:1883` nếu broker đã được khởi động và cho phép client kết nối. Spring Boot không tự tạo MQTT broker.

### 8.1. Maven dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-mqtt</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Để Spring Boot BOM quản lý version tương thích. Ví dụ cụ thể dùng `MqttConnectOptions` của Paho MQTT v3, không áp dụng trực tiếp cho MQTT v5 client. `jackson-databind` được khai báo tường minh vì bài dựa vào `ObjectMapper`.

### 8.2. Cấu trúc file

~~~text
src/main/java/demo/mqttconversion/
  MqttConversionApplication.java
  TemperatureReading.java
  AcceptedTelemetry.java
  TelemetrySink.java
  TelemetryInboundFlowConfiguration.java
  MqttTransportConfiguration.java
  MqttOutboundFlowConfiguration.java
  TemperaturePublisher.java

src/main/resources/
  application.properties

src/test/java/demo/mqttconversion/
  TelemetryInboundFlowTest.java
  TemperaturePublisherTest.java
~~~

Các class/record thuộc package `demo.mqttconversion`. Class có modifier `public` cần nằm trong file Java trùng tên. Mọi thành phần được đặt trong cùng package để Spring component scanning và Java package visibility nhất quán.

### 8.3. Application và cấu hình môi trường

~~~java
package demo.mqttconversion;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttConversionApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttConversionApplication.class, args);
    }
}
~~~

`src/main/resources/application.properties`:

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}
app.mqtt.subscriber-id=${MQTT_SUBSCRIBER_ID:telemetry-in-local-1}
app.mqtt.publisher-id=${MQTT_PUBLISHER_ID:telemetry-out-local-1}
~~~

Local demo chưa thiết lập TLS/password. Với broker production, yêu cầu TLS, authentication, broker topic ACL và cấu hình secrets bên ngoài source. Không dùng cùng Client ID cho inbound và outbound client hoặc giữa hai replica đồng thời.

### 8.4. DTO và validation

~~~java
package demo.mqttconversion;

record TemperatureReading(
        String eventId,
        String deviceId,
        Double celsius) {

    TemperatureReading {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("Thiếu eventId");
        }
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("deviceId không hợp lệ");
        }
        if (celsius == null
                || !Double.isFinite(celsius)
                || celsius < -80
                || celsius > 150) {
            throw new IllegalArgumentException(
                    "Giá trị nhiệt độ không hợp lệ");
        }
    }
}
~~~

Validation nằm ở constructor record để cả JSON decoder và producer nội bộ đều phải cung cấp fields hợp lệ. Dải `-80..150` là **quy ước minh họa**, không phải chuẩn đo lường cho mọi cảm biến. Production nên dùng Bean Validation/schema và giới hạn theo loại thiết bị.

Jackson hiện đại có thể map JSON fields vào các component của Java record. Nếu nguồn gửi schema cũ hoặc khác key, cần một mapping/version strategy, không dùng field name tùy ý mà không kiểm thử.

### 8.5. Sink minh họa

~~~java
package demo.mqttconversion;

record AcceptedTelemetry(
        String topic,
        TemperatureReading reading) {
}
~~~

~~~java
package demo.mqttconversion;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class TelemetrySink {

    private final List<AcceptedTelemetry> accepted =
            new CopyOnWriteArrayList<>();

    void accept(AcceptedTelemetry item) {
        accepted.add(item);
    }

    List<AcceptedTelemetry> snapshot() {
        return List.copyOf(accepted);
    }

    void clear() {
        accepted.clear();
    }
}
~~~

Sink chỉ lưu RAM để test; production có thể thay bằng service activator ghi DB, HTTP outbound gateway, JMS/AMQP/Kafka outbound adapter hoặc lưu file/SFTP. Thời điểm xử lý business hoàn tất cần xác định rõ, đặc biệt khi MQTT client đã ACK delivery nhưng downstream chưa commit.

### 8.6. MessageChannel và inbound IntegrationFlow

~~~java
package demo.mqttconversion;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class TelemetryInboundFlowConfiguration {

    @Bean(name = "mqtt.telemetry.in")
    MessageChannel telemetryInput() {
        return new DirectChannel();
    }

    @Bean
    ObjectMapper telemetryObjectMapper() {
        return new ObjectMapper();
    }

    @Bean
    TelemetrySink telemetrySink() {
        return new TelemetrySink();
    }

    @Bean
    IntegrationFlow telemetryInboundFlow(
            ObjectMapper telemetryObjectMapper,
            TelemetrySink sink) {

        return IntegrationFlow.from("mqtt.telemetry.in")
                .handle(String.class, (json, headers) -> {
                    Object rawTopic =
                            headers.get(MqttHeaders.RECEIVED_TOPIC);

                    if (!(rawTopic instanceof String topic)
                            || !topic.matches(
                                    "sensors/[A-Za-z0-9_-]{1,40}/temperature")) {
                        throw new IllegalArgumentException(
                                "Topic telemetry không hợp lệ");
                    }

                    final TemperatureReading reading;
                    try {
                        reading = telemetryObjectMapper.readValue(
                                json, TemperatureReading.class);
                    } catch (JsonProcessingException ex) {
                        throw new IllegalArgumentException(
                                "Không parse được JSON telemetry", ex);
                    }

                    String expectedTopic = "sensors/"
                            + reading.deviceId()
                            + "/temperature";
                    if (!topic.equals(expectedTopic)) {
                        throw new IllegalArgumentException(
                                "deviceId không khớp MQTT topic");
                    }

                    sink.accept(new AcceptedTelemetry(topic, reading));
                    return null; // inbound one-way, không có reply
                })
                .get();
    }
}
~~~

**Lý do dùng handler có `String.class`:** đây là flow text JSON, converter inbound sẽ đưa vào payload `String`. Nếu cấu hình `setPayloadAsBytes(true)` ở adapter, contract đầu vào đổi thành `byte[]` và handler này **không còn khớp kiểu**. Khi thay converter phải cập nhật toàn bộ downstream tương ứng.

Flow kiểm tra topic và `deviceId` để tránh một publisher gửi payload của device A dưới topic device B. Điều này **chưa thay thế broker ACL và authentication**; nó là một lớp kiểm soát business bổ sung.

**Lưu ý về lỗi:** exception parse/validation trong handler có thể bị Spring Integration bọc thành messaging exception. Ứng dụng thật cần error flow/quarantine và policy MQTT acknowledgement rõ ràng; không chỉ ném lỗi và giả định broker chắc chắn phát lại đúng message.

### 8.7. MQTT factory, inbound và outbound endpoints

~~~java
package demo.mqttconversion;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
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
        options.setCleanSession(true);

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter mqttInboundAdapter(
            MqttPahoClientFactory mqttClientFactory,
            @Qualifier("mqtt.telemetry.in") MessageChannel output,
            @Value("${app.mqtt.subscriber-id}") String clientId) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, mqttClientFactory, "sensors/+/temperature");

        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(output);
        return adapter;
    }

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler mqttPublisher(
            MqttPahoClientFactory mqttClientFactory,
            @Value("${app.mqtt.publisher-id}") String clientId) {

        var handler = new MqttPahoMessageHandler(
                clientId, mqttClientFactory);
        handler.setDefaultTopic("demo/unrouted");
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setConverter(new DefaultPahoMessageConverter());
        handler.setAsync(false);
        handler.setCompletionTimeout(5000);
        return handler;
    }
}
~~~

Trong ví dụ, inbound adapter là **message-driven** và không có poller; Paho client nhận PUBLISH rồi converter phát message vào channel. Outbound handler sử dụng cùng factory options nhưng **Client ID khác**, nhận Spring message và publish ra MQTT.

Topic mặc định `demo/unrouted` chỉ là đích phụ cho demo. Với dữ liệu thật, hãy validate topic ở producer và không để missing header âm thầm gửi sự kiện tới một đích không mong muốn. Giới hạn thời gian `completionTimeout(5000)` không phải “thời gian DB được phép xử lý”; nó giới hạn thao tác publish theo contract handler/Paho, và timeout có thể tạo kết quả publish **chưa chắc chắn**.

### 8.8. Outbound channel và Java DSL handler

~~~java
package demo.mqttconversion;

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
class MqttOutboundFlowConfiguration {

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

`MessageChannel` nối producer nội bộ với outbound endpoint; `.handle(publisher)` đăng ký consumer. Không thêm đồng thời `@ServiceActivator(inputChannel="mqtt.publish.requests")` cho **cùng handler** nếu không muốn có hai consumer cạnh tranh.

### 8.9. Serialize DTO trước khi publish

~~~java
package demo.mqttconversion;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class TemperaturePublisher {

    private final MessageChannel output;
    private final ObjectMapper mapper;

    TemperaturePublisher(
            @Qualifier("mqtt.publish.requests") MessageChannel output,
            ObjectMapper mapper) {
        this.output = output;
        this.mapper = mapper;
    }

    boolean publish(TemperatureReading reading)
            throws JsonProcessingException {

        if (reading == null) {
            throw new IllegalArgumentException("Thiếu telemetry");
        }

        String json = mapper.writeValueAsString(reading);
        String topic = "sensors/"
                + reading.deviceId()
                + "/temperature";

        return output.send(MessageBuilder.withPayload(json)
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, 1)
                .setHeader(MqttHeaders.RETAINED, false)
                .build());
    }
}
~~~

Caller có thể tạo DTO:

~~~java
TemperatureReading reading = new TemperatureReading(
        "evt-1001", "device-17", 26.5);

publisher.publish(reading);
~~~

Pipeline outbound thực hiện:

~~~text
TemperatureReading
  → ObjectMapper.writeValueAsString(...)
  → Spring Message<String> + MQTT headers
  → MqttPahoMessageHandler
  → DefaultPahoMessageConverter
  → MQTT PUBLISH byte payload
~~~

Khi subscriber của cùng ứng dụng nhận lại topic phù hợp, pipeline inbound parse JSON và ghi vào `TelemetrySink`. Đó là test round-trip tiện lợi trong local, nhưng không nên dùng vòng loop này để chứng minh hệ thống production có exactly-once delivery.

## 9. Payload nhị phân: không buộc mọi message thành JSON

MQTT thường dùng trong môi trường IoT nơi payload có thể là binary frame cố định, CBOR/protobuf hoặc dữ liệu đã được nén. Khi đó `String` có thể không phải representation phù hợp.

### 9.1. Cấu hình inbound byte[]

~~~java
var binaryConverter = new DefaultPahoMessageConverter();
binaryConverter.setPayloadAsBytes(true);

var binaryAdapter = new MqttPahoMessageDrivenChannelAdapter(
        "binary-subscriber-1",
        mqttClientFactory,
        "devices/+/binary");

binaryAdapter.setConverter(binaryConverter);
binaryAdapter.setQos(1);
binaryAdapter.setOutputChannel(binaryInputChannel);
~~~

Consumer của channel cần xử lý `byte[]`:

~~~java
@Bean
IntegrationFlow binaryFlow() {
    return IntegrationFlow.from("mqtt.binary.in")
            .handle(byte[].class, (bytes, headers) -> {
                if (bytes.length < 4) {
                    throw new IllegalArgumentException(
                            "Binary frame quá ngắn");
                }
                // Decode theo binary protocol đã được thống nhất.
                // Có thể kiểm checksum, frame version, signature...
                return null;
            })
            .get();
}
~~~

Snippet `binaryFlow` giả định bean channel tên `mqtt.binary.in` đã được tạo và `binaryInputChannel` trong đoạn trước tham chiếu đúng bean đó. Đây là **phương án thay thế** cho text inbound, không thêm một consumer nhận String trên cùng channel rồi kỳ vọng hai handler cùng nhìn thấy mọi message.

### 9.2. Outbound binary

~~~java
byte[] frame = new byte[] {
        0x01, 0x00, 0x7F, (byte) 0xA5
};

Message<byte[]> message = MessageBuilder.withPayload(frame)
        .setHeader(MqttHeaders.TOPIC, "devices/device-17/binary")
        .setHeader(MqttHeaders.QOS, 1)
        .setHeader(MqttHeaders.RETAINED, false)
        .build();

binaryOutboundChannel.send(message);
~~~

Đây là minh họa producer, cần import `Message`, `MessageBuilder`, `MqttHeaders`, và một `MessageChannel` tên `binaryOutboundChannel` đã được nối tới MQTT handler. Không gọi `new String(frame)` rồi gửi lại để “dễ xử lý”: việc chuyển text có thể không đảo ngược được theo từng byte.

### 9.3. Khi nào nên tách adapter theo payload type?

Nếu hai topic có định dạng rất khác nhau (text JSON vs raw protobuf), có thể tạo **hai MQTT inbound adapters** với converters cấu hình khác nhau và output channels riêng:

~~~text
MQTT JSON topic  → converter String → mqtt.json.in  → Jackson parser
MQTT binary topic → converter bytes  → mqtt.bytes.in → Protobuf decoder
~~~

Mỗi MQTT client cần Client ID riêng khi hoạt động đồng thời. Nếu dùng chung adapter và channel với `payloadAsBytes=true` cho tất cả topics, downstream cần router/decoder xác định data format từ received topic và schema chính thức.

## 10. Topic-based schema mapping và content type

Khi một client subscribe nhiều filters:

~~~text
sensors/+/temperature
sensors/+/humidity
devices/+/config
~~~

không nên áp một JSON DTO duy nhất cho mọi payload. Cần mapping theo **topic + schema version**:

| Topic pattern | Kiểu payload đã quy ước | Decoder |
| --- | --- | --- |
| `sensors/+/temperature` | JSON UTF-8, `temperature/v1`. | Jackson → `TemperatureReading`. |
| `sensors/+/humidity` | JSON UTF-8, `humidity/v1`. | Jackson → `HumidityReading`. |
| `devices/+/binary` | Protobuf bytes, `device-frame/v2`. | Protobuf parser. |
| `devices/+/availability` | UTF-8 text `ONLINE`/`OFFLINE`. | Enum/state parser. |

MQTT v3 không có header `Content-Type` chuẩn kiểu HTTP. Có thể đưa `schemaVersion` trong JSON/binary frame, dùng topic namespace (`v1/...`) hoặc registry bên ngoài. MQTT v5 hỗ trợ các metadata khác như Content Type và Payload Format Indicator; khi dùng v5 phải chọn client/converter v5 phù hợp, không giả định các field đó tự xuất hiện trong Paho v3.

### 10.1. Không dùng topic làm bằng chứng quyền

Topic từ broker có thể giúp chọn decoder nhưng không thay thế authorization. Nếu publisher được phép gửi tới nhiều topic, nó có thể cố gửi payload chứa `deviceId` của tenant khác. Vì vậy decoder phải kết hợp validation và đối chiếu identity với topic, còn broker phải giới hạn ACL.

### 10.2. Routing trước khi decode hay sau khi decode?

- **Trước decode:** khi topic quyết định schema, route theo `MqttHeaders.RECEIVED_TOPIC` rồi dùng decoder tương ứng.
- **Sau decode:** khi mọi message cùng envelope/schema tổng quát, parse envelope trước để route theo field `eventType`.
- **Kết hợp:** decode một envelope nhỏ trước, rồi chọn body decoder theo `type/version`.

Không có một quy tắc cố định cho mọi hệ thống. Quan trọng là **schema lựa chọn phải rõ, không đoán mò từ nội dung text**, và kiểm thử các trường hợp không nhận diện được schema.

## 11. Header mapping: đừng làm mất metadata khi transform

Khi chuyển MQTT message qua transformer, payload có thể đổi từ `String` sang DTO nhưng metadata như received topic, event timestamp và trace context vẫn có ích.

Ví dụ ban đầu:

~~~text
Message<String>:
  payload = JSON
  headers[MqttHeaders.RECEIVED_TOPIC] = sensors/device-17/temperature
~~~

Sau transformer:

~~~text
Message<TemperatureReading>:
  payload = TemperatureReading(...)
  headers[MqttHeaders.RECEIVED_TOPIC] = sensors/device-17/temperature
~~~

Cách tạo Spring message mới cần tuân theo policy **giữ hoặc loại bỏ headers có chủ đích**. Nếu tạo message thủ công bằng `MessageBuilder.withPayload(dto).build()` mà không copy headers, bạn có thể vô tình mất `RECEIVED_TOPIC` và correlation metadata. Khi dùng transformer của Spring Integration, kiểm tra behavior header propagation theo endpoint/version đang sử dụng.

Mặt khác, **không giữ tất cả headers một cách mù quáng** khi bridge sang một hệ thống khác. Các header nội bộ như `replyChannel`, `errorChannel` hoặc credentials không phải dữ liệu công khai cho subscriber MQTT.

### 11.1. Payload transformation không có nghĩa QoS thay đổi

QoS, retained, topic thuộc thông tin chuyển giao MQTT. Khi JSON payload được parse thành DTO trong Spring, message đã vào flow; việc thay đổi DTO không gửi một MQTT ACK mới hay thay đổi QoS publication đã nhận.

Nếu cần publish một event mới sau transform, đó là **outbound MQTT publication khác** với topic/QoS/retained được quyết định riêng. Không tự copy `MqttHeaders.RECEIVED_TOPIC` thành `MqttHeaders.TOPIC` như một bridge vô điều kiện.

### 11.2. Application correlation ID phải nằm đúng chỗ

Với MQTT v3, event ID cần được subscriber đọc phải có trong payload schema, ví dụ:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-1001",
  "deviceId": "device-17",
  "celsius": 26.5
}
~~~

Đặt `eventId` **chỉ ở Spring header nội bộ** sẽ không làm thiết bị/consumer ngoài Spring biết ID đó. Sự khác biệt này rất quan trọng cho idempotency và tracing xuyên hệ thống.

## 12. Lỗi converter và JSON validation cần đi về đâu?

~~~mermaid
flowchart TD
    BROKER[("MQTT broker")]
    CLIENT["Paho client"]
    CONV{"MQTT converter"}
    CH["Spring MessageChannel"]
    PARSE{"JSON / binary decoder"}
    VAL{"Business validation"}
    DB[("DB / outbound adapter")]
    ERR["Error flow / quarantine / audit"]
    BROKER --> CLIENT --> CONV
    CONV -->|"Spring Message"| CH --> PARSE
    CONV -->|"Lỗi decode text / mapping"| ERR
    PARSE -->|"DTO"| VAL
    PARSE -->|"Malformed payload/schema"| ERR
    VAL -->|"Hợp lệ"| DB
    VAL -->|"Sai business rule"| ERR
    DB -. "Timeout/transaction error" .-> ERR
~~~

Có ít nhất bốn nhóm lỗi khác nhau:

| Nhóm | Ví dụ | Chính sách khuyến nghị |
| --- | --- | --- |
| Transport converter | Byte không giải mã text được theo policy, converter không chấp nhận type. | Quarantine raw bytes khi có thể, kiểm tra client/converter config. |
| Schema parser | JSON thiếu dấu ngoặc, sai kiểu `celsius`, schema version không hỗ trợ. | Reject/quarantine, không retry vô hạn lỗi dữ liệu cố định. |
| Business validator | `deviceId` không khớp topic, temperature ngoài dải cho phép. | Ghi lý do, audit và đối chiếu publisher quyền. |
| Downstream | DB unavailable, HTTP timeout, Kafka producer error. | Retry có giới hạn và idempotency, hoặc kho xử lý lại bền vững. |

Spring Integration có error handling qua `ErrorMessage`/`errorChannel` khi endpoint/flow phù hợp được cấu hình. Nhưng **không giả định** mọi exception trong Paho callback tự động trở thành message trên một channel tùy ý hoặc khiến broker chắc chắn redeliver đến khi DB commit.

### 12.1. Vì sao lỗi JSON không nên retry mãi?

Nếu payload được broker giao là:

~~~text
{"eventId":"evt-1001","celsius":
~~~

thì gửi lại cùng bytes không làm JSON trở nên hợp lệ. Retry vô hạn gây nghẽn, log storm và có thể chiếm toàn bộ tài nguyên consumer. Cần đánh dấu **non-retryable** và lưu bản tin sai (nếu chính sách cho phép) cùng topic, correlation/event ID, byte length, code lỗi và thời điểm nhận.

### 12.2. Lỗi downstream có thể đã xảy ra sau MQTT ACK

Một PUBLISH QoS 1 có thể đã được MQTT client/broker acknowledge theo protocol trước khi database commit. Nếu DB lỗi, MQTT protocol **không tự rollback** transaction DB và không đồng nghĩa broker chắc chắn phát lại. Nếu cần bảo đảm end-to-end, phải thiết kế manual acknowledgment trong những adapter/version phù hợp, hoặc lưu vào kho bền vững và xử lý idempotent — tất cả cần test crash/restart thực tế.

## 13. Lưu raw payload để điều tra và replay

Khi message bị lỗi parse, nếu chỉ lưu string đã qua conversion có thể mất bytes gốc. Với hệ thống đòi điều tra hoặc replay, có thể chọn inbound `payloadAsBytes=true`, lưu tạm payload thô vào quarantine bền vững và decode ở một worker độc lập.

Một quarantine record nên chứa:

~~~json
{
  "messageId": "quarantine-001",
  "receivedTopic": "sensors/device-17/temperature",
  "receivedAt": "2026-11-23T03:00:00Z",
  "schemaHint": "temperature/v1",
  "payloadLength": 42,
  "payloadStorageRef": "secure-object-store/path",
  "reasonCode": "INVALID_JSON"
}
~~~

Đây là **schema minh họa**, không phải output tự động của Spring Integration MQTT. Với dữ liệu có PII/secrets, hạn chế thời gian lưu, mã hóa, ACL và audit truy cập. Không lưu nguyên binary payload vào log text lớn hoặc log toàn bộ thông tin cảm biến nếu không cần.

### 13.1. Không tạo vòng lặp reprocessing

Nếu decoder lỗi rồi publish lại cùng message vào chính source topic, subscriber có thể nhận lại vô hạn. Nên tách `invalid-events`/quarantine store, đánh dấu retry count, reason và quyết định dead-letter/replay theo quản trị. Replay phải giữ `eventId` ổn định và idempotency của business side effect.

### 13.2. Dữ liệu có chữ ký số

Nếu payload được thiết bị ký số, **phải xác minh chữ ký trên bytes đúng canonical contract** trước khi biến đổi làm thay đổi representation. Việc parse JSON rồi serialize lại có thể đổi khoảng trắng, thứ tự field hoặc kiểu biểu diễn số; chữ ký trên raw bytes có thể không còn khớp. Chọn điểm verify/decode theo protocol cụ thể.

## 14. Kiểm thử flow JSON không cần broker

Logic inbound ở mục 8 được tách khỏi MQTT transport: `TelemetryInboundFlowConfiguration` tạo channel, ObjectMapper, sink và IntegrationFlow, nhưng **không khởi tạo Paho client**. Có thể dùng `@SpringJUnitConfig` chỉ nạp class này.

Tạo `TelemetryInboundFlowTest.java` trong package `demo.mqttconversion`:

~~~java
package demo.mqttconversion;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
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

@SpringJUnitConfig(classes = TelemetryInboundFlowConfiguration.class)
class TelemetryInboundFlowTest {

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
    void validJsonBecomesValidatedDto() {
        String json = "{\"eventId\":\"evt-test-1\","
                + "\"deviceId\":\"device-17\","
                + "\"celsius\":26.5}";

        boolean accepted = input.send(
                MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "sensors/device-17/temperature")
                        .build());

        assertTrue(accepted);
        assertEquals(
                List.of(new AcceptedTelemetry(
                        "sensors/device-17/temperature",
                        new TemperatureReading(
                                "evt-test-1", "device-17", 26.5))),
                sink.snapshot());
    }

    @Test
    void topicDeviceMismatchIsRejected() {
        String json = "{\"eventId\":\"evt-test-2\","
                + "\"deviceId\":\"device-21\","
                + "\"celsius\":25.0}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "sensors/device-17/temperature")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void malformedJsonIsRejected() {
        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(
                        "{\"eventId\":")
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "sensors/device-17/temperature")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void invalidTemperatureIsRejected() {
        String json = "{\"eventId\":\"evt-test-4\","
                + "\"deviceId\":\"device-17\","
                + "\"celsius\":9999}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "sensors/device-17/temperature")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }
}
~~~

Test chứng minh:

- Spring channel và flow đã được đăng ký.
- Parser chuyển JSON text thành record Java đúng.
- Validation loại dữ liệu sai.
- So sánh device ID với received topic hoạt động.
- Với `DirectChannel`, handler được gọi đồng bộ trong demo.

**Không thể** từ test này kết luận Paho đã decode bytes với charset đúng, broker đã nhận QoS 1, retained flag đúng hoặc MQTT reconnect hoạt động. Đây là **test business conversion sau khi đã có Spring Message<String>**.

### 14.1. Test JSON serialization không cần broker

Có thể kiểm tra round-trip DTO/Jackson riêng:

~~~java
var mapper = new ObjectMapper();
var original = new TemperatureReading(
        "evt-test-5", "device-17", 26.5);

String json = mapper.writeValueAsString(original);
TemperatureReading decoded = mapper.readValue(
        json, TemperatureReading.class);

assertEquals(original, decoded);
~~~

Đây là đoạn nằm trong JUnit test method, cần import `ObjectMapper` và `assertEquals`. Nó xác minh schema Java/Jackson nhưng **không chứng minh** MQTT adapter đã chọn đúng topic hoặc converter đã phát đúng bytes. Với contract quan trọng, dùng thêm golden JSON fixtures từ publisher thực và test decode binary.

## 15. Kiểm thử outbound flow bằng fake MessageHandler

Để tách network, test outbound không dùng `MqttTransportConfiguration`. Tạo một Spring context tối giản chỉ chứa `MqttOutboundFlowConfiguration`, `ObjectMapper`, `TemperaturePublisher` và một fake bean tên `mqttPublisher`.

~~~java
package demo.mqttconversion;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.integration.mqtt.support.MqttHeaders;

record OutboundObservation(
        String topic, String payload, int qos, boolean retained) {
}

class RecordingPublisher implements MessageHandler {

    private final List<OutboundObservation> observations =
            new CopyOnWriteArrayList<>();

    @Override
    public void handleMessage(Message<?> message) {
        observations.add(new OutboundObservation(
                (String) message.getHeaders().get(MqttHeaders.TOPIC),
                (String) message.getPayload(),
                (Integer) message.getHeaders().get(MqttHeaders.QOS),
                (Boolean) message.getHeaders().get(MqttHeaders.RETAINED)));
    }

    List<OutboundObservation> snapshot() {
        return List.copyOf(observations);
    }
}

@Configuration
class OutboundTestBeans {

    @Bean(name = "mqttPublisher")
    RecordingPublisher mqttPublisher() {
        return new RecordingPublisher();
    }

    @Bean
    TemperaturePublisher temperaturePublisher(
            @Qualifier("mqtt.publish.requests")
            org.springframework.messaging.MessageChannel input,
            com.fasterxml.jackson.databind.ObjectMapper mapper) {
        return new TemperaturePublisher(input, mapper);
    }

    @Bean
    com.fasterxml.jackson.databind.ObjectMapper objectMapper() {
        return new com.fasterxml.jackson.databind.ObjectMapper();
    }
}
~~~

Trong test, nạp `@SpringJUnitConfig(classes = {MqttOutboundFlowConfiguration.class, OutboundTestBeans.class})`, inject `TemperaturePublisher` và `RecordingPublisher` rồi assert:

~~~java
TemperatureReading event = new TemperatureReading(
        "evt-out-1", "device-17", 26.5);

boolean sent = publisher.publish(event);
assertTrue(sent);

var actual = recorder.snapshot();
assertEquals(1, actual.size());
assertEquals("sensors/device-17/temperature",
        actual.get(0).topic());
assertEquals(1, actual.get(0).qos());
assertEquals(false, actual.get(0).retained());

TemperatureReading decoded = objectMapper.readValue(
        actual.get(0).payload(),
        TemperatureReading.class);
assertEquals(event, decoded);
~~~

Các biến `publisher`, `recorder`, `objectMapper` là bean đã inject trong class test; đoạn trên nằm trong test method và cần imports JUnit tương ứng. Test xác minh:

1. DTO được serialize thành JSON.
2. Topic/QoS/retained headers được đặt đúng.
3. `IntegrationFlow` chuyển message đến outbound handler bean.
4. Có thể deserialize ngược payload thành DTO tương đương.

**Giới hạn:** fake handler không gọi `DefaultPahoMessageConverter` và không giao MQTT packet cho broker. Kiểm thử byte-level transport và QoS phải làm ở bước integration test.

## 16. Kiểm thử end-to-end bằng broker và CLI

Chỉ dùng broker thử nghiệm đã được người học thiết lập. Ví dụ `tcp://localhost:1883` giả định broker MQTT local cho phép các client test kết nối. Nếu broker yêu cầu TLS/credentials, cấu hình đúng cả ứng dụng và CLI; không tắt bảo mật broker production.

### 16.1. Gửi JSON inbound bằng Mosquitto CLI

Với backend Spring đang subscribe `sensors/+/temperature`, publish:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'sensors/device-17/temperature' \
  -q 1 \
  -m '{"eventId":"evt-cli-1","deviceId":"device-17","celsius":26.5}'
~~~

Nếu flow hoạt động, `TelemetrySink` có một `AcceptedTelemetry` mang đúng topic, eventId, deviceId và temperature. Kiểm tra bằng test hook/metric thay vì chỉ quan sát “broker nhận”.

### 16.2. Gửi dữ liệu lỗi để kiểm tra quarantine

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'sensors/device-17/temperature' \
  -q 1 \
  -m '{"eventId":"evt-cli-bad","deviceId":"device-17","celsius":'
~~~

Flow JSON handler có thể ném lỗi, nhưng demo chưa có quarantine store production. Cần quan sát log/error policy và bổ sung quarantine/persistent retry trước khi dùng trong hệ thống đáng tin cậy. Không tuyên bố broker tự redeliver vô hạn mỗi khi handler ném exception.

### 16.3. Quan sát outbound publication

Mở subscriber:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -t 'sensors/+/temperature' -v
~~~

Gọi `TemperaturePublisher.publish(...)` từ một API/test hook local. Subscriber thấy topic và JSON text khi broker cho phép và kết nối hoạt động. Nếu cả inbound/outbound cùng nằm trong một application subscribe cùng topic, message xuất bản có thể **đi ngược vào inbound flow**; đây là expected behavior nhưng phải tránh vòng loop khi flow tự publish lại mọi message nhận.

### 16.4. Test binary payload

Với topic `devices/device-17/binary`, dùng CLI có khả năng publish payload từ một file binary thử nghiệm:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/binary' \
  -q 1 \
  -f sample-frame.bin
~~~

`sample-frame.bin` là file **do bài test chuẩn bị trước**, không phải file sẵn có. Khi adapter dùng `setPayloadAsBytes(true)`, downstream phải nhận byte array tương ứng; so sánh length và hash để chứng minh dữ liệu không bị thay đổi bởi bước convert thành text.

### 16.5. Test matrix cần có

| Thử nghiệm | Dữ liệu gửi | Điều cần xác nhận |
| --- | --- | --- |
| JSON UTF-8 hợp lệ | Payload schema v1, topic đúng. | Converter text và Jackson decode đúng field. |
| JSON sai cú pháp | Thiếu dấu ngoặc/value. | Lỗi parse vào error policy, không side effect DB. |
| Field sai kiểu | `celsius="very hot"`. | Parser/validation reject có lý do. |
| Topic/payload không khớp | Topic device-17, JSON device-21. | Business validator chặn publish sai danh tính. |
| Unicode | Field text có ký tự tiếng Việt. | Round-trip UTF-8 đúng, không lỗi encoding. |
| Binary frame | Bytes chứa `0x00` hoặc `0xFF`. | Byte[] không bị biến dạng qua text decoder. |
| Payload quá lớn | Vượt byte limit. | Broker/client/app reject có kiểm soát, không hết RAM. |
| Empty bytes | MQTT payload length 0. | App phân biệt legitimate empty payload với lệnh xóa retained. |
| QoS 1 duplicate | Gửi lại cùng `eventId`. | DB/handler idempotent. |
| Broker disconnect | Ngắt kết nối trong môi trường test. | Recovery/replay theo policy; không biến lỗi MQTT thành lỗi schema. |
| Retained snapshot | Publish retained rồi subscribe mới. | Snapshot có thể xuất hiện lại; không tính là event mới nếu hợp đồng cấm. |
| Schema version mới | Payload `schemaVersion=2`. | Consumer reject hoặc chọn decoder version tương ứng. |

## 17. Empty payload và retained deletion: cẩn trọng với zero bytes

Trong MQTT 3.1.1, một PUBLISH có **RETAIN=true** và payload **zero-length** tới topic cụ thể thường được dùng để **xóa retained message** trên broker.

Điều này liên quan trực tiếp đến payload conversion:

- `byte[0]` là một payload có độ dài 0, không phải chuỗi `"null"` hay JSON `null`.
- `String` rỗng khi mã hóa thành UTF-8 có thể cho ra zero-length bytes, nhưng policy xóa retained phụ thuộc **cả RETAIN flag** và topic, không chỉ nội dung.
- Dữ liệu JSON `{"value":null}` là bytes không rỗng, không tương đương xóa retained.
- App không nên tự động biến “không có body” thành một retained publish ở topic production.

**Bảo mật:** thao tác xóa retained state phải có authorization và audit. Một converter mất dữ liệu rồi tạo `byte[0]` cùng retained=true có thể vô tình xóa snapshot quan trọng của thiết bị.

## 18. Hiệu năng, backpressure và dữ liệu lớn

Converter không chạy trong chân không: khi broker nhận message nhanh hơn consumer parse/validate/ghi DB, hệ thống có thể nghẽn.

| Rủi ro | Vì sao | Giải pháp |
| --- | --- | --- |
| JSON quá lớn | Cấp phát chuỗi/AST và áp lực GC. | Broker/application byte limit, streaming parser khi cần. |
| Byte[] bị copy nhiều lần | Tăng memory/GC, tốn CPU. | Giữ binary bytes qua tối thiểu số bước và đo allocations. |
| Parse trên MQTT callback thread | Handler blocking làm chậm nhận/ACK. | Cách ly qua executor/queue có capacity và error policy. |
| Queue trong RAM | Restart có thể mất dữ liệu đang đợi. | Persistent store/outbox theo SLA. |
| Gửi lại dữ liệu lỗi vô hạn | Poison message làm cạn pool, log storm. | Retry budget, non-retryable schema errors, quarantine. |
| Schema mapping theo topic lớn | Nhiều rules khó bảo trì/không nhất quán. | Schema registry/config versioning và contract tests. |
| Payload chứa secret/PII | Log/tracing làm lộ thông tin. | Redaction, access control, hạn chế retention. |

`DirectChannel` đơn giản và đồng bộ trong demo, nhưng production có thể cần `ExecutorChannel` hoặc `QueueChannel` để tách load. Nếu đổi sang `QueueChannel`, consumer phía sau **cần poller** lấy Spring messages khỏi queue; điều đó không biến MQTT inbound thành polling adapter.

### 18.1. Không nhận MQTT như file transfer mặc định

Dù MQTT có thể chở binary bytes, nó không tự cung cấp phân mảnh file, resume, kiểm checksum file, transaction nhiều chunk hoặc lưu lâu bền như dịch vụ file/object store. Với payload lớn, cân nhắc publish **metadata/link bảo mật** đến object store thay vì nhét toàn bộ file vào PUBLISH. Cần giới hạn URL/ACL và expiry, không coi MQTT payload là công cụ chuyển file dung lượng tùy ý.

## 19. Bảo mật khi chuyển đổi payload

MQTT payload có thể do thiết bị/caller không tin cậy tạo; parser và converter phải nằm trong mô hình đe dọa của ứng dụng:

1. **Xác thực kết nối**: broker TLS/credentials hoặc mTLS tùy môi trường.
2. **ACL topic**: publisher chỉ được publish topic thuộc thiết bị/tenant phù hợp; subscriber chỉ đọc phạm vi được phép.
3. **Validation**: bắt buộc fields/schema; đối chiếu topic-device ID.
4. **Giới hạn bytes**: từ broker/client đến parser, tránh payload quá lớn.
5. **Từ chối unsafe deserialization**: không dùng Java object deserialization hay polymorphic type resolution không kiểm soát từ dữ liệu người dùng.
6. **Encoding rõ ràng**: UTF-8 hoặc binary codec do contract chỉ định; không đoán từ payload.
7. **Quarantine có hạn**: mã hóa, TTL, giới hạn truy cập và audit nếu cần lưu raw bytes.
8. **Không log full payload**: nhất là token, dữ liệu cá nhân, payload binary/PII.
9. **Idempotency**: eventId/commandId trong payload để chống redelivery và replay.
10. **Replay an toàn**: payload sai không được đưa lại source topic vô hạn hoặc điều khiển thiết bị ngoài ý muốn.

### 19.1. Malformed Unicode và JSON injection

Nếu người dùng gửi các chuỗi có ký tự đặc biệt, **đừng tự ghép JSON bằng string interpolation** như:

~~~java
String json = "{\"deviceId\":\"" + userDeviceId + "\"}";
~~~

Giá trị chứa dấu nháy hoặc escape có thể tạo JSON lỗi hoặc nội dung khác dự kiến. Hãy validate identity và sử dụng Jackson serializer từ DTO; nó xử lý escaping theo JSON grammar. Điều đó vẫn không thay thế authorization và validation nội dung.

## 20. Các lỗi phổ biến và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Handler chỉ nhận `String` nhưng payload là `byte[]`. | Converter đã bật `payloadAsBytes=true`. | Kiểm tra converter và generic type của downstream handler. |
| JSON parser báo lỗi dù publisher nói gửi JSON. | Sai charset, bytes không phải JSON, payload bị cắt hoặc schema sai. | Quan sát byte length, decode policy, thử raw bytes trong test bảo mật. |
| Emoji/ký tự tiếng Việt bị lỗi. | Producer/consumer dùng charset khác hoặc decoder thay ký tự. | Thống nhất UTF-8, test multilingual round-trip và strict decoder. |
| Java DTO có field null. | JSON thiếu key, sai tên, schema version lệch. | Log code lỗi/mapping, thêm required field validation. |
| Subscriber không thấy eventId. | Chỉ đặt eventId trong Spring header nội bộ. | Đưa ID vào JSON/binary payload schema. |
| Inbound flow ghi sai thiết bị. | Không đối chiếu received topic với payload deviceId. | Validate topic shape, device authorization và ID consistency. |
| Payload binary bị hỏng. | Ép bytes qua `String` và encode lại. | Dùng `setPayloadAsBytes(true)`, so sánh byte-for-byte. |
| Topic outbound sai. | Nhầm `MqttHeaders.RECEIVED_TOPIC` với `MqttHeaders.TOPIC`. | Set outbound topic sau route/authorization. |
| Một event tạo nhiều bản ghi DB. | QoS redelivery/retry hoặc publisher phát hai message cùng nghiệp vụ. | Dedup theo eventId và unique constraint. |
| Parse fail làm MQTT connection gián đoạn. | Handler ném exception trên callback, không có error policy. | Kiểm tra Paho/Spring logs, errorChannel và quarantine. |
| Message cũ xuất hiện sau restart. | Retained snapshot hoặc persistent session/redelivery. | Xem metadata, event time, QoS/retained và idempotency. |
| Payload zero bytes xóa retained state. | RETAIN=true cùng payload dài 0 theo MQTT. | Restrict publish policy, test empty bytes và ACL. |
| Thấy Spring channel.send(true) nhưng thiết bị không nhận. | Send chỉ thể hiện handoff nội bộ/handler theo topology, không phải business ACK. | Kiểm tra broker, QoS, subscriber/session và ACK riêng. |
| Parser chậm khiến broker reconnect. | Blocking quá lâu trên inbound callback/không backpressure. | Giới hạn parsing latency, executor/queue, monitoring. |
| Lỗi protobuf version cũ. | Decoder/schema mismatch. | Hợp đồng version, migration và golden fixtures. |

## 21. Bài tập thực hành: telemetry hỗn hợp JSON và binary

**Bối cảnh:** một hệ thống nhận dữ liệu cảm biến MQTT từ thiết bị đời cũ và đời mới.

- Thiết bị đời cũ publish JSON UTF-8 ở `sensors/{deviceId}/temperature`.
- Thiết bị đời mới publish binary frame ở `devices/{deviceId}/binary`.
- Backend chuẩn hóa thành `TemperatureReading` rồi lưu DB và phát một event kết quả tới Kafka.

Yêu cầu:

1. Xác định topic filter và schema của mỗi loại payload; quy định maximum bytes và QoS.
2. Tạo `MqttPahoClientFactory` và inbound adapter cho JSON với converter text.
3. Tạo inbound adapter thứ hai với `setPayloadAsBytes(true)` và Client ID riêng cho binary.
4. Xây hai Spring input channels, không trộn `String` và `byte[]` mà không có contract.
5. Viết JSON decoder bằng Jackson, binary decoder theo một frame spec do bạn tự định nghĩa (version, độ dài, checksum).
6. Dùng transformer đưa cả hai loại payload về DTO chung `TemperatureReading`.
7. Validate `deviceId` trùng với MQTT received topic; validate eventId, dải nhiệt độ và schemaVersion.
8. Dùng error flow/quarantine bền vững cho payload sai; không retry schema error vô hạn.
9. Thêm idempotency key theo eventId trước khi ghi DB; phản hồi nếu nhận QoS 1 duplicate.
10. Đặt headers phù hợp khi publish event kết quả, đưa correlation ID cần thiết vào payload đối tác.
11. Viết test no-broker cho JSON, binary, topic mismatch và byte payload có `0x00`/`0xFF`.
12. Kiểm thử MQTT broker thật, gửi JSON qua `mosquitto_pub -m` và binary qua `-f`.
13. Giới hạn queue, memory, max payload size; quan sát thời gian parse và backlog.
14. Test retained empty payload không thể vô tình xóa state của một topic production.
15. Ghi tài liệu data contract bao gồm encoding, schema version, cách tăng version tương thích ngược và chính sách dead-letter.

**Tiêu chí đạt:** message JSON và binary được chuẩn hóa chính xác không mất byte; converter đảm nhiệm transport, decoder đảm nhiệm schema; lỗi có thể truy vết, không ghi sai device/tenant, có cơ chế chống duplicate và kiểm thử được từ raw bytes đến trạng thái đích.

## 22. Câu hỏi tự kiểm tra

1. Vì sao MQTT broker không thể tự tạo Java `TemperatureReading` từ payload?
2. `DefaultPahoMessageConverter` khác Jackson `ObjectMapper` như thế nào?
3. Khi nào inbound nên dùng `String`, khi nào nên dùng `byte[]`?
4. `setPayloadAsBytes(true)` ảnh hưởng kiểu payload mà handler nhận thế nào?
5. MQTT v3 có mặc định gửi `Content-Type: application/json` giống HTTP không?
6. Vì sao cần một encoding contract dù JSON text thường dùng UTF-8?
7. `String.length()` có đồng nghĩa với số byte UTF-8 không?
8. Khi byte không phải UTF-8 hợp lệ, muốn reject thay vì thay ký tự phải dùng gì?
9. Topic filter `sensors/+/temperature` có chứng minh publisher được quyền gửi `deviceId` bất kỳ không?
10. Vì sao `MqttHeaders.RECEIVED_TOPIC` cần được kiểm tra với `deviceId` bên trong payload?
11. Vì sao eventId chỉ nằm trong Spring header không đủ cho subscriber MQTT v3?
12. Khi gửi DTO outbound, tại sao nên serialize bằng Jackson trước converter?
13. Một biến đổi từ JSON sang DTO có bảo đảm QoS đúng một lần ở DB không?
14. Vì sao giữ raw bytes khi quarantine có thể quan trọng hơn lưu string đã decode?
15. Nếu payload có chữ ký, cần verify trước hay sau một phép parse/serialize có thể đổi bytes?
16. Payload zero-length cùng RETAIN=true có ý nghĩa gì?
17. Fake handler test xác minh được gì và không xác minh được gì?
18. Khi chuyển flow JSON sang binary, những thành phần downstream nào cần thay đổi?
19. Nếu cùng một adapter subscribe nhiều topic có schema khác nhau, nên route ở đâu?
20. Cách phân biệt parse error, validation error và DB timeout?
21. Vì sao không nên dùng Java object deserialization không kiểm soát với MQTT payload?
22. Một application vừa subscribe vừa publish cùng topic có thể tạo loop trong trường hợp nào?
23. Schema versioning đóng vai trò gì với thiết bị cũ và mới?
24. Nếu message inbound có retained snapshot cũ, có nên tính đó là event mới không?

**Gợi ý:** MQTT là byte transport. Converter tạo Spring message; parser/decoder xử lý format; validator bảo vệ business contract; broker QoS và transaction nghiệp vụ là các tầng khác nhau.

## 23. Kết luận

**Payload conversion cho MQTT message** là việc nối dữ liệu giao thức **MQTT topic + bytes + QoS/retained** với **Spring Message và kiểu Java** một cách có chủ đích.

- `DefaultPahoMessageConverter` chuyển đổi ở ranh giới MQTT/Spring; inbound có thể chọn `String` cho text hoặc `byte[]` cho binary.
- JSON, protobuf và các data formats khác cần **decoder/encoder nghiệp vụ riêng**, có schema/version rõ ràng.
- `MqttHeaders.RECEIVED_TOPIC` và `MqttHeaders.TOPIC` có mục đích khác nhau; metadata Spring không tự truyền xuyên MQTT v3.
- Chất lượng tích hợp phụ thuộc vào **encoding, byte limit, validation, topic authorization, error/quarantine, idempotency** và kiểm thử với broker thực tế.
- Hoàn tất MQTT delivery không đồng nghĩa DB, HTTP, JMS, Kafka hoặc thiết bị đã xử lý nghiệp vụ thành công.

Trong module **SPRING_INTEGRATION_ADAPTERS**, tách bạch **transport converter → data format transformer → business handler** giúp flow dễ kiểm thử, mở rộng từ JSON sang binary và thay đổi giao thức mà không phá vỡ hợp đồng message. Bảo toàn dữ liệu đúng ở mỗi ranh giới là nền tảng để vận hành Spring Integration MQTT đáng tin cậy.

