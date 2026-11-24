# Last will và keep alive

## 1. Vì sao MQTT cần Last Will và Keep Alive?

Trong hệ thống IoT, một thiết bị có thể mất điện, đứt Wi-Fi, bị treo tiến trình hoặc rời mạng mà không gửi thông điệp “tôi đã offline”. Nếu backend chỉ chờ thiết bị chủ động thông báo trạng thái trước khi ngắt kết nối, trạng thái `ONLINE` có thể tồn tại mãi dù thiết bị đã biến mất.

MQTT có hai cơ chế liên quan để xử lý tình huống này:

- **Last Will and Testament (LWT), thường gọi ngắn là Last Will:** client khai báo trước một bản tin mà **broker** sẽ publish khi broker xác định kết nối của client đã kết thúc bất thường theo điều kiện MQTT.
- **Keep Alive:** client/broker duy trì việc phát hiện một connection không còn hoạt động nhờ giới hạn khoảng thời gian không có MQTT Control Packet và, khi cần, cặp `PINGREQ`/`PINGRESP`.

Chúng có quan hệ nhân quả: Keep Alive có thể giúp broker **phát hiện** client mất kết nối; LWT quy định broker cần **publish điều gì** sau khi phát hiện kiểu mất kết nối đó. Tuy nhiên, Last Will cũng có thể được phát khi TCP connection bị đóng bất thường mà không cần đợi hết keepalive.

Bài này nằm trong chương **Adapter MQTT** của module **SPRING_INTEGRATION_ADAPTERS**. Module tập trung kết nối hệ thống bên ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành file, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu, đồng thời kiểm soát hợp đồng message, lỗi và vòng đời kết nối. Ở đây, Spring Integration có thể subscribe thông điệp trạng thái qua MQTT inbound message-driven adapter, định tuyến chúng sang `IntegrationFlow` và cập nhật trạng thái thiết bị trong database.

### Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích trường Will Topic, Will Payload, Will QoS và Will Retain trong MQTT 3.1.1 CONNECT.
2. Phân biệt ngắt kết nối **có DISCONNECT hợp lệ** với **đứt kết nối bất thường**.
3. Hiểu Keep Alive tính bằng giây và vai trò của `PINGREQ`/`PINGRESP`, không xem keepalive là SLA phát hiện offline chính xác tuyệt đối.
4. Cấu hình `MqttConnectOptions.setWill(...)` và `setKeepAliveInterval(...)` bằng Eclipse Paho.
5. Thiết kế presence `ONLINE/OFFLINE` bằng retained message, Last Will và bản tin thông báo khi kết nối lại.
6. Nhận trạng thái thiết bị qua `MqttPahoMessageDrivenChannelAdapter` rồi đưa vào `MessageChannel` và `IntegrationFlow`.
7. Phân biệt LWT, heartbeat nghiệp vụ, session, QoS, retained và automatic reconnect.
8. Xử lý trạng thái cũ, kết nối chập chờn, duplicate, Client ID trùng, quyền topic, lỗi broker và multi-instance.
9. Viết kiểm thử flow không cần broker, sau đó thử nghiệm Last Will với broker test thực sự.

**Phạm vi kỹ thuật:** ví dụ dùng MQTT **3.1.1**, Spring Integration MQTT và Eclipse Paho MQTT v3. Với MQTT 5, một số tính năng như *Will Delay Interval* và *Message Expiry Interval* làm thay đổi chính sách phát Will; không dùng API v3 của bài này để suy diễn cho mọi MQTT 5 deployment.

## 2. Luồng Last Will từ client đến broker và Spring Integration

~~~mermaid
flowchart LR
    DEVICE["Thiết bị MQTT client<br/>cấu hình Will trước CONNECT"]
    BROKER[("MQTT broker")]
    OBS["Spring MQTT inbound adapter<br/>subscribe devices/+/availability"]
    CH["mqtt.presence.in<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>validate / classify"]
    DB[("Presence store / monitoring")]
    DEVICE -->|"CONNECT chứa Will"| BROKER
    DEVICE -->|"PUBLISH ONLINE sau CONNECT"| BROKER
    DEVICE -. "mất nguồn / mất mạng / không DISCONNECT" .-> BROKER
    BROKER -->|"PUBLISH Will OFFLINE"| OBS
    OBS --> CH --> FLOW --> DB
~~~

Broker chỉ biết connection của **MQTT client**, không biết tiến trình nghiệp vụ thực sự còn hoạt động tốt hay không. Backend nhận Last Will từ thiết bị qua **subscription bình thường**: Will là một MQTT PUBLISH được broker tạo ra theo nội dung client đã khai báo, không phải một exception Java được gửi thẳng vào service.

| Bước | Bên chịu trách nhiệm | Điều xảy ra |
| --- | --- | --- |
| 1 | Thiết bị / Paho client | Trước khi connect, khai báo Will Topic, payload, QoS và retained. |
| 2 | MQTT broker | Khi CONNECT hợp lệ, broker ghi nhận Will cho connection/session theo quy tắc MQTT. |
| 3 | Thiết bị | Sau khi connect thành công, publish trạng thái `ONLINE` bằng topic đã quy ước. |
| 4 | MQTT client và broker | Duy trì connection, xử lý MQTT packets và keepalive. |
| 5 | Broker | Nếu kết nối kết thúc bất thường theo điều kiện giao thức, broker publish Will `OFFLINE`. |
| 6 | Spring MQTT inbound adapter | Nhận PUBLISH qua subscribe callback, chuyển thành Spring `Message<?>`. |
| 7 | IntegrationFlow/handler | Validate topic/payload, đối soát trạng thái và ghi hệ thống đích. |

**Chú ý ranh giới:** nếu **thiết bị** muốn có LWT, chính **MQTT client trong thiết bị** phải khai báo Will khi CONNECT. Cấu hình LWT trên Paho client của **backend Spring** chỉ cho biết backend client có bị mất kết nối hay không; nó không thể thay thiết bị đăng ký Will của thiết bị.

## 3. MQTT Last Will gồm những trường nào?

Trong MQTT 3.1.1, CONNECT có thể mang thông tin Will nếu Will Flag bật. Với Paho MQTT v3, cấu hình thông qua:

~~~java
options.setWill(
        "devices/device-17/availability",
        "OFFLINE".getBytes(StandardCharsets.UTF_8),
        1,
        true);
~~~

Các tham số:

| Tham số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Will Topic** | `devices/device-17/availability` | MQTT topic cụ thể mà broker sẽ publish Will. |
| **Will Payload** | Byte UTF-8 của `OFFLINE` | Nội dung bản tin khi connection mất bất thường. |
| **Will QoS** | `1` | QoS của publication Will do broker phát. |
| **Will Retain** | `true` | Yêu cầu broker giữ lại Will dưới dạng retained snapshot mới nhất của topic. |

Topic Will là **topic PUBLISH**, không phải wildcard subscription filter; vì vậy không đặt `devices/+/availability` làm Will Topic của một thiết bị cụ thể.

Will Payload là **byte[]**, không bắt buộc là text. Nếu backend cần dữ liệu như `deviceId`, `timestamp`, `sessionEpoch` hoặc `schemaVersion`, hãy thống nhất format JSON/protobuf và giới hạn kích thước theo policy broker. Will payload được đăng ký **trước** khi có sự cố, nên không thể chứa timestamp chính xác do client sinh ngay tại thời điểm mạng đứt. Muốn biết thời điểm broker phát Will, consumer có thể bổ sung **receivedAt** dựa trên đồng hồ hệ thống đáng tin cậy.

### 3.1. Will có sẵn tự động cho mọi MQTT client không?

**Không.** Client không khai báo Will thì broker không có Will payload để publish khi connection biến mất. Các thành phần Spring Integration inbound/outbound được xây trên Paho cũng không tự sinh `OFFLINE` cho mọi thiết bị.

Nếu muốn backend Spring tự công bố trạng thái connection của chính mình, cấu hình Will trên **factory options của client backend đó** và publish một birth message `ONLINE` sau khi client thực sự kết nối thành công. Không dùng một Will Topic chung cho tất cả client ID: nhiều client có thể cùng ghi đè một retained status, làm việc truy vết trở nên sai lệch.

### 3.2. Will có phải một message được client gửi lúc chết?

**Không.** Khi client mất nguồn hoặc đứt mạng, nó không thể chủ động gửi nữa. Client chỉ cung cấp nội dung Will trong `CONNECT` từ trước; **broker** quyết định lúc nào cần tạo PUBLISH khi phát hiện connection kết thúc bất thường.

Đây cũng là lý do **broker phải còn hoạt động** để phát Will. Không thể coi LWT là cam kết rằng người quan sát luôn thấy OFFLINE tức thì khi cả broker hoặc mạng đến broker gặp sự cố.

## 4. Khi nào broker publish Last Will?

Trong MQTT 3.1.1, Will thường được publish khi kết nối bị đóng mà client **không gửi một DISCONNECT hợp lệ** trước đó, hoặc khi các điều kiện kết thúc kết nối bất thường khác theo giao thức được áp dụng.

| Tình huống | Có kỳ vọng broker phát Will không? | Ghi chú |
| --- | --- | --- |
| Thiết bị mất điện khi đang kết nối | **Có**, khi broker phát hiện connection bị mất. | Thời gian phát hiện không tức thì. |
| Mạng Wi-Fi bị cắt, client không còn liên lạc | **Có**, sau khi broker xác định mất kết nối, thường liên quan keepalive/TCP. | Có thể còn một khoảng thời gian trạng thái ONLINE bị cũ. |
| Tiến trình client chết đột ngột | **Có**, nếu connection kết thúc bất thường. | Tùy broker phát hiện socket/keepalive. |
| Client gọi MQTT `DISCONNECT` sạch | **Không**, Will thông thường được xóa thay vì publish. | Muốn hiện OFFLINE phải publish chủ động trước khi disconnect. |
| Client không hề CONNECT thành công | **Không thể kỳ vọng Will của connection chưa hình thành**. | Broker chưa ghi nhận Will hợp lệ. |
| Client đã reconnect thành công sau mất mạng | Will có thể đã được phát trước đó. | Client cần publish ONLINE mới để cập nhật presence. |
| Broker chết cùng thời điểm với client | **Không thể giả định Will đã được giao cho observer**. | Broker không hoạt động để phát; cần đối soát sau phục hồi. |
| Kết nối bị thay thế do Client ID trùng | Có thể bị coi là ngắt bất thường của client cũ. | Tránh dùng trùng Client ID; test hành vi broker cụ thể. |

Không diễn giải bảng này thành cam kết về thời điểm chính xác hoặc mọi tình huống lỗi. MQTT presence là **tín hiệu best-effort theo trạng thái connection**; dữ liệu quan trọng cần heartbeat, timestamp và chính sách xác nhận ở ứng dụng.

### 4.1. Graceful shutdown phải làm gì?

Khi phần mềm chủ động tắt bình thường, client có thể publish:

~~~text
topic   = devices/device-17/availability
payload = OFFLINE
qos     = 1
retain  = true
~~~

Sau khi publish hoàn tất ở tầng MQTT theo policy, nó gọi `disconnect()`. Broker sẽ **không phát Will** do disconnect sạch; nhưng retained `OFFLINE` đã được chủ động cập nhật nên subscriber mới vẫn thấy trạng thái phù hợp.

Nếu client gửi `DISCONNECT` mà quên publish OFFLINE, broker có thể giữ retained `ONLINE` cũ. Đó là lỗi thiết kế presence phổ biến. Ngược lại, khi kết nối chết đột ngột, client không có cơ hội publish OFFLINE nên Will cung cấp fallback.

### 4.2. Will không phải shutdown hook Java

Một JVM shutdown hook có thể không chạy khi mất điện, `SIGKILL`, crash hoặc kernel panic. LWT được broker thực thi sau khi phát hiện connection mất bất thường, nên không phụ thuộc việc JVM còn chạy để phát message. Nhưng LWT cũng **không thay thế** việc dọn tài nguyên, transaction/outbox hoặc thiết kế hệ thống đích.

## 5. Keep Alive hoạt động như thế nào?

Trong MQTT 3.1.1, Keep Alive là khoảng thời gian tối đa mà client cam kết không để trôi qua giữa các MQTT Control Packets gửi tới broker khi kết nối đang hoạt động, trong điều kiện protocol quy định.

Ví dụ Paho:

~~~java
MqttConnectOptions options = new MqttConnectOptions();
options.setKeepAliveInterval(20); // 20 GIÂY
~~~

Nếu không có packet nào khác cần gửi, client có thể phát `PINGREQ` để duy trì kết nối; broker phản hồi `PINGRESP`. Trong thời gian ứng dụng publish/subscribe dữ liệu, những MQTT packets khác có thể đã đủ làm mới hoạt động và không nhất thiết tạo PINGREQ đều đặn như đồng hồ.

~~~mermaid
sequenceDiagram
    participant C as MQTT client
    participant B as MQTT broker
    C->>B: CONNECT KeepAlive=20s + Will
    B-->>C: CONNACK
    Note over C,B: Không có MQTT packet khác cần gửi
    C->>B: PINGREQ
    B-->>C: PINGRESP
    Note over C,B: Connection vẫn hoạt động
    C--xB: Mất mạng / packet không tới
    Note over B: Không nhận control packet đủ lâu
    B->>B: Xác định connection bị mất
    B->>B: Publish Will theo cấu hình
~~~

### 5.1. Quy tắc khoảng 1,5 lần Keep Alive

Theo mô hình MQTT 3.1.1, khi broker không nhận được MQTT Control Packet từ client trong khoảng **1,5 lần Keep Alive**, broker phải xem connection là không còn hợp lệ và đóng kết nối theo quy tắc giao thức.

Ví dụ:

~~~text
Client Keep Alive = 20 giây
1,5 x Keep Alive = khoảng 30 giây
~~~

Đây là **ngưỡng hoạt động protocol**, không phải SLA “thiết bị chắc chắn OFFLINE sau đúng 30 giây”. Các yếu tố có thể làm thời điểm quan sát khác đi:

- Broker phát hiện TCP socket đóng sớm hơn do reset/FIN hoặc lỗi I/O.
- Scheduler, network partition và overload làm thời điểm xử lý bị trễ.
- Lúc bắt đầu mất mạng có thể không trùng thời điểm packet cuối cùng broker nhận.
- Broker/cluster đang lỗi hoặc restart nên không thể phát Will ngay.
- Spring observer có thể offline hoặc chậm tiêu thụ message.

**Không lấy `keepAlive=20` rồi đặt cảnh báo “mất kết nối đúng 20 giây” mà không đo thực tế.** Muốn cam kết phát hiện trạng thái cho nghiệp vụ, phải chọn SLA riêng và thực nghiệm khi network/broker hoạt động không ổn định.

### 5.2. Keepalive bằng 0 có nghĩa gì?

Trong MQTT 3.1.1, `Keep Alive = 0` vô hiệu hóa cơ chế timeout keepalive ở mức MQTT đối với client đó. Nó không có nghĩa TCP connection không bao giờ chết, cũng không ngăn broker đóng kết nối vì lý do khác.

Với thiết bị cần phát hiện offline, một Keep Alive hợp lý thường hữu ích hơn `0`, nhưng khoảng quá ngắn có thể tiêu tốn pin, băng thông và tăng false positive trên mạng yếu. Cần cân bằng SLA, mạng di động, thiết bị ngủ, năng lượng và broker capacity.

### 5.3. Keepalive khác Paho connection timeout

~~~java
options.setConnectionTimeout(10); // GIÂY: thời gian thiết lập connection
options.setKeepAliveInterval(20); // GIÂY: duy trì/phát hiện connection
~~~

`connectionTimeout` có ý nghĩa khi client đang **mở kết nối mới**; `keepAliveInterval` áp dụng cho connection hoạt động. Khi MQTT outbound publish, `MqttPahoMessageHandler.setCompletionTimeout(5000)` lại giới hạn **thời gian đợi thao tác publish** và tính bằng mili giây. Không tăng keepalive để sửa mọi lỗi publish timeout.

## 6. Kết hợp retained presence: ONLINE và OFFLINE

Mẫu phổ biến cho một thiết bị:

1. Device tạo Paho options với Will `OFFLINE`, Will QoS=1, Will Retain=true.
2. Client CONNECT và broker lưu thông tin Will.
3. Sau khi CONNECT thành công, device chủ động PUBLISH `ONLINE` với QoS=1, RETAIN=true lên **cùng topic availability**.
4. Khi mất kết nối bất thường, broker PUBLISH Will `OFFLINE`, RETAIN=true.
5. Khi device reconnect, nó phải PUBLISH `ONLINE` mới sau khi kết nối thành công.
6. Khi shutdown chủ động, device PUBLISH `OFFLINE` rồi MQTT `DISCONNECT` sạch.

~~~mermaid
sequenceDiagram
    participant D as Device client
    participant B as Broker
    participant S as Spring observer
    D->>B: CONNECT(Will=OFFLINE, retain=true, QoS=1)
    B-->>D: CONNACK
    D->>B: PUBLISH ONLINE (retain=true)
    B->>S: ONLINE
    Note over D,B: Mất nguồn/mất mạng
    B->>B: Phát hiện kết nối không còn hoạt động
    B->>S: Will OFFLINE
    Note over D,B: Thiết bị hoạt động trở lại
    D->>B: CONNECT(Will=OFFLINE)
    B-->>D: CONNACK
    D->>B: PUBLISH ONLINE (retain=true)
    B->>S: ONLINE
~~~

Retained presence giúp một subscriber mới không phải đợi thiết bị gửi lại status mới nhất. Nhưng đây là **snapshot tại broker**, không phải event history. Message retained `ONLINE` có thể bị cũ nếu broker chưa phát Will, nếu Will đã bị thiếu, hoặc nếu broker mất dữ liệu/không hoạt động.

### 6.1. Tại sao cả ONLINE và Will OFFLINE cần cùng topic?

Giả sử device `device-17` sử dụng:

~~~text
topic = devices/device-17/availability
ONLINE:  QoS=1, RETAIN=true
OFFLINE: QoS=1, RETAIN=true (Will)
~~~

Broker chỉ giữ retained snapshot cuối cùng trên topic đó; khi Will xuất hiện, retained OFFLINE **thay thế** retained ONLINE. Nếu device publish ONLINE sang topic khác, ví dụ `devices/device-17/online` nhưng Will OFFLINE nằm ở `devices/device-17/offline`, subscriber sẽ nhận hai trạng thái cạnh tranh và phải tự tổng hợp. Một topic availability với payload thể hiện state dễ đối soát hơn.

### 6.2. Retain=false không xóa trạng thái retained cũ

Nếu đã có retained ONLINE, sau đó device publish OFFLINE với `RETAIN=false`, broker không tự xóa/ghi đè retained ONLINE đang lưu. Người subscribe mới vẫn có thể thấy thông tin cũ. Vì vậy, với policy **presence retained**, tất cả các lần cập nhật snapshot nên nhất quán về topic và RETAIN=true.

Khi xóa thiết bị khỏi hệ thống, một người có quyền quản trị có thể yêu cầu broker xóa retained state bằng cách publish **payload 0 byte** với RETAIN=true lên đúng topic trong MQTT 3.1.1. Phải thực hiện theo quy trình bảo mật, tránh xóa nhầm retained state của tenant khác.

### 6.3. Last Will không chứa thời điểm chết chính xác

Will payload được thiết bị cung cấp khi CONNECT, nên JSON có `disconnectedAt` lấy trước kết nối là một timestamp gây hiểu nhầm. Nếu cần timestamp OFFLINE, observer nên gắn **receivedAt** của message broker hoặc giám sát broker có timestamp đáng tin cậy, kèm lưu ý độ trễ phát hiện.

Có thể chứa các trường ổn định như:

~~~json
{
  "deviceId": "device-17",
  "status": "OFFLINE",
  "connectionEpoch": "boot-20261123-001",
  "reason": "LAST_WILL"
}
~~~

`connectionEpoch` do ứng dụng thiết bị tạo trước CONNECT; nó giúp downstream nhận diện connection logic để giảm tình trạng xử lý trạng thái cũ, nhưng không tự bảo đảm ordering khi message từ nhiều broker/instance đi đến khác thời điểm.

## 7. Cấu hình LWT bằng Eclipse Paho MQTT v3

Một ví dụ Java cho thiết bị giả lập:

~~~java
import java.nio.charset.StandardCharsets;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;

String availabilityTopic = "devices/device-17/availability";
byte[] offline = "OFFLINE".getBytes(StandardCharsets.UTF_8);

MqttConnectOptions options = new MqttConnectOptions();
options.setServerURIs(new String[] {"tcp://localhost:1883"});
options.setConnectionTimeout(10);   // giây
options.setKeepAliveInterval(20);   // giây
options.setCleanSession(true);
options.setAutomaticReconnect(false); // demo để thấy mất kết nối

options.setWill(availabilityTopic, offline, 1, true);
~~~

Điểm quan trọng:

- `setWill(topic, byte[], qos, retained)` phải được gọi **trước CONNECT** để Will xuất hiện trong CONNECT packet.
- QoS phải nằm trong các cấp MQTT được hỗ trợ: 0, 1 hoặc 2.
- Topic phải là một tên topic publish cụ thể, không chứa wildcard subscribe.
- Will retained=true chỉ hợp lý khi backend cần snapshot ONLINE/OFFLINE cho observer mới.
- Client phải có **Client ID duy nhất** giữa các connection đồng thời; Will gắn với connection của client đó.
- `cleanSession=true/false` không tự bật hoặc vô hiệu hóa Will; đây là quyết định session/subscription riêng.
- Khi muốn giữ lịch sử sự kiện offline dài hạn, cần persistent event store; Will retained không thay thế event log.

Ví dụ này dùng transport TCP plaintext để chạy local. Với production, dùng TLS, xác thực broker và giới hạn quyền publish availability của từng thiết bị. Không đưa password hoặc private key vào mã nguồn.

### 7.1. Có thể cấu hình Will trong Spring Integration client factory không?

Có. Nếu backend Java được xây bằng `MqttPahoMessageHandler` hoặc `MqttPahoMessageDrivenChannelAdapter`, Paho client sử dụng `MqttPahoClientFactory`; factory nhận `MqttConnectOptions` có thể chứa Will.

~~~java
@Bean("bridgeClientFactory")
MqttPahoClientFactory bridgeClientFactory() {
    var options = new MqttConnectOptions();
    options.setServerURIs(new String[] {
            "tcp://localhost:1883"
    });
    options.setKeepAliveInterval(20);
    options.setConnectionTimeout(10);
    options.setWill(
            "services/integration-bridge/availability",
            "OFFLINE".getBytes(StandardCharsets.UTF_8),
            1,
            true);

    var factory = new DefaultMqttPahoClientFactory();
    factory.setConnectionOptions(options);
    return factory;
}
~~~

Snippet cần import `StandardCharsets`, `MqttConnectOptions`, `MqttPahoClientFactory`, `DefaultMqttPahoClientFactory` và `@Bean`.

**Giới hạn cần nhớ:** Will trên factory này thể hiện trạng thái của **MQTT client backend** được tạo từ options, không phải trạng thái của tất cả thiết bị. Nếu nhiều adapter dùng chung factory có cùng Will Topic, chúng có thể ghi đè retained presence của nhau. Nên cấp factory/Will Topic riêng theo role hoặc client logic, với Client ID rõ ràng.

### 7.2. Khi nào Will của backend bắt đầu có hiệu lực?

Bean factory được khởi tạo không đồng nghĩa client đã CONNECT. Will chỉ trở thành trạng thái được broker biết đến sau một CONNECT phù hợp. Nếu `MqttPahoMessageHandler` dùng kết nối lười khởi tạo khi có publish đầu tiên, không được coi bean tồn tại là backend đã “đăng ký Will”. Cần kiểm tra lifecycle thực tế, kết nối thành công và birth message theo adapter/client đang dùng.

## 8. Ví dụ giả lập thiết bị: gửi ONLINE và khai báo OFFLINE Will

Đoạn Java sau mô phỏng một MQTT device sử dụng Paho v3. Chạy trong một tiến trình riêng với Spring observer ở mục 9.

~~~java
package demo.mqttpresence;

import java.nio.charset.StandardCharsets;

import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;

public class DeviceWillSimulator {

    public static void main(String[] args) throws Exception {
        String brokerUrl = args.length > 0
                ? args[0] : "tcp://localhost:1883";
        String topic = "devices/device-17/availability";

        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(20);
        options.setCleanSession(true);
        options.setAutomaticReconnect(false);
        options.setWill(
                topic,
                "OFFLINE".getBytes(StandardCharsets.UTF_8),
                1,
                true);

        var client = new MqttClient(
                brokerUrl, "sim-device-17", new MemoryPersistence());

        client.connect(options);

        // Birth message: cập nhật retained ONLINE sau khi CONNECT.
        client.publish(
                topic,
                "ONLINE".getBytes(StandardCharsets.UTF_8),
                1,
                true);

        System.out.println(
                "Simulator ONLINE. Enter để DISCONNECT sạch.");
        System.in.read();

        // Graceful shutdown: publish OFFLINE trước DISCONNECT.
        client.publish(
                topic,
                "OFFLINE".getBytes(StandardCharsets.UTF_8),
                1,
                true);

        client.disconnect();
        client.close();
    }
}
~~~

**Cách đọc ví dụ:**

- Nếu nhấn Enter, simulator gửi retained OFFLINE rồi disconnect sạch; broker không cần phát Will.
- Nếu tiến trình bị **kết thúc cưỡng bức** khi broker vẫn hoạt động và client không kịp gửi DISCONNECT, broker có thể phát Will sau khi phát hiện connection kết thúc bất thường.
- Thời gian quan sát OFFLINE tùy phát hiện TCP/keepalive và điều kiện broker, không phải luôn đúng 20 giây.
- Nếu chỉ dừng chính broker, broker có thể không đủ khả năng phát Will cho observer đang kết nối vào broker đó; đó không phải phép thử đáng tin cậy cho tình huống “device chết nhưng broker còn sống”.
- Trong sản phẩm thật, nếu dùng `automaticReconnect=true`, phải bổ sung logic **publish ONLINE sau mỗi lần reconnect thành công**, không chỉ sau lần CONNECT đầu tiên.

### 8.1. Vì sao không bật automatic reconnect trong simulator ngắn này?

Mục tiêu demo là quan sát một connection mất bất thường và Will ở broker. Nếu bật auto reconnect nhưng không viết callback birth-message cho các lần reconnect, client có thể trở lại online trong khi retained OFFLINE vẫn còn, tạo kết quả sai. Trong production, có thể dùng cơ chế reconnect của client nhưng phải gắn nó với lifecycle publish ONLINE và kiểm tra thứ tự trạng thái.

### 8.2. Không đồng nhất process còn chạy với connection còn sống

Trong demo, tiến trình Java có thể chờ `System.in.read()` và không publish nghiệp vụ; Paho vẫn duy trì keepalive ở tầng MQTT. Nếu mã Java bị deadlock ở business worker nhưng mạng/client thread vẫn ping broker bình thường, MQTT Keep Alive vẫn cho thấy **connection còn hoạt động** dù tính năng nghiệp vụ đã bị treo. Vì vậy Last Will không phải health check toàn diện của ứng dụng.

## 9. Spring Integration: quan sát Will và trạng thái của thiết bị

Giờ xây **backend observer**: subscribe `devices/+/availability` qua MQTT inbound message-driven adapter, nhận `ONLINE/OFFLINE` từ thiết bị và ghi vào một sink minh họa. Đây là flow inbound, **không** tạo Will thay cho device.

### 9.1. Dependencies và cấu trúc

Ví dụ Java 17+, Spring Boot/Spring Integration tương thích với Paho MQTT v3. Maven dependencies:

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

Module MQTT cung cấp adapter và Paho client integration. `DeviceWillSimulator` sử dụng trực tiếp Paho v3; cần bảo đảm thư viện Paho tương thích có trên classpath (thường qua module MQTT), hoặc khai báo dependency có phiên bản được dự án quản lý khi tách simulator thành project độc lập.

Cấu trúc:

~~~text
src/main/java/demo/mqttpresence/
    PresenceApplication.java
    PresenceTransportConfiguration.java
    PresenceFlowConfiguration.java
    PresenceEvent.java
    PresenceSink.java
    DeviceWillSimulator.java

src/main/resources/
    application.properties

src/test/java/demo/mqttpresence/
    PresenceFlowTest.java
~~~

### 9.2. Spring Boot application

~~~java
package demo.mqttpresence;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PresenceApplication {

    public static void main(String[] args) {
        SpringApplication.run(PresenceApplication.class, args);
    }
}
~~~

Trong vận hành thực tế, simulator nên chạy ở **process riêng** hoặc module test, không tự khởi động cùng backend Spring. Đây là hai MQTT clients với vai trò khác nhau.

### 9.3. application.properties

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}
app.mqtt.observer-client-id=${MQTT_OBSERVER_CLIENT_ID:presence-observer-local-1}
app.mqtt.presence-topic-filter=devices/+/availability
~~~

Broker local `localhost:1883` chỉ là hạ tầng thử nghiệm; Spring Boot không tự khởi tạo broker. Trong container, `localhost` là chính container, không tự trỏ đến broker trên host. Với môi trường khác, dùng broker URL phù hợp, TLS, credentials và ACL.

### 9.4. MQTT factory và inbound adapter

~~~java
package demo.mqttpresence;

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
class PresenceTransportConfiguration {

    @Bean
    MqttPahoClientFactory presenceClientFactory(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {

        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(false);
        options.setAutomaticReconnect(false);

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter mqttPresenceAdapter(
            MqttPahoClientFactory presenceClientFactory,
            @Qualifier("mqtt.presence.in") MessageChannel output,
            @Value("${app.mqtt.observer-client-id}") String clientId,
            @Value("${app.mqtt.presence-topic-filter}") String topicFilter) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, presenceClientFactory, topicFilter);

        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(output);
        return adapter;
    }
}
~~~

Đặc điểm:

1. `presenceClientFactory` dùng Client ID mà adapter cung cấp khi tạo MQTT client; cấu hình broker, keepalive và session có thể áp dụng riêng cho observer.
2. `setCleanSession(false)` minh họa persistent session MQTT 3.1.1 cho observer. Client ID phải ổn định nếu muốn khôi phục session, và không được dùng đồng thời ở nhiều instance.
3. `setAutomaticReconnect(false)` nhằm để inbound adapter quản lý recovery theo cơ chế `setRecoveryInterval(...)` trong ví dụ này; phải kiểm tra thực tế theo phiên bản triển khai.
4. `setQos(1)` là subscription QoS của observer. Will từ device được broker phát với QoS 1; QoS effective của delivery còn phụ thuộc subscription.
5. `setOutputChannel(output)` phát message inbound vào Spring channel `mqtt.presence.in`.
6. MQTT inbound là **message-driven**, nên không cần `@Poller` để nhận broker callback.

**Phân biệt:** observer factory **không cần khai báo Will của device**. Will của device đã được đăng ký bởi `DeviceWillSimulator` khi chính device client CONNECT.

### 9.5. Presence flow và sink

~~~java
package demo.mqttpresence;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class PresenceFlowConfiguration {

    @Bean(name = "mqtt.presence.in")
    MessageChannel presenceInput() {
        return new DirectChannel();
    }

    @Bean
    PresenceSink presenceSink() {
        return new PresenceSink();
    }

    @Bean
    IntegrationFlow presenceFlow(PresenceSink sink) {
        return IntegrationFlow.from("mqtt.presence.in")
                .handle(String.class, (payload, headers) -> {
                    String topic = (String)
                            headers.get(MqttHeaders.RECEIVED_TOPIC);

                    if (topic == null
                            || !topic.matches(
                                    "devices/[A-Za-z0-9_-]{1,40}/availability")) {
                        throw new IllegalArgumentException(
                                "Topic presence không hợp lệ: " + topic);
                    }
                    if (!"ONLINE".equals(payload)
                            && !"OFFLINE".equals(payload)) {
                        throw new IllegalArgumentException(
                                "Presence status không hỗ trợ: " + payload);
                    }

                    sink.record(new PresenceEvent(topic, payload));
                    return null;
                })
                .get();
    }
}
~~~

~~~java
package demo.mqttpresence;

record PresenceEvent(String topic, String status) {
}
~~~

~~~java
package demo.mqttpresence;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class PresenceSink {

    private final List<PresenceEvent> events =
            new CopyOnWriteArrayList<>();

    void record(PresenceEvent event) {
        events.add(event);
        System.out.println(
                "MQTT presence: " + event.topic()
                + " = " + event.status());
    }

    List<PresenceEvent> snapshot() {
        return List.copyOf(events);
    }

    void clear() {
        events.clear();
    }
}
~~~

Mỗi khi thiết bị gửi retained ONLINE hoặc broker phát Will OFFLINE, adapter nhận một MQTT message có topic tương ứng; flow kiểm tra shape, payload và ghi sự kiện.

**Đây là ví dụ dạy wiring, chưa phải production presence store:** chỉ dùng `CopyOnWriteArrayList` trong RAM. Một hệ thống thật phải cập nhật DB theo device/session identity, kiểm tra timestamp và xử lý retained stale/duplicate/out-of-order; đồng thời tránh để validation exception làm nghẽn callback MQTT. Thay vì ném exception vô hạn với payload hỏng, cần một quarantine/error flow có chính sách riêng.

### 9.6. Vai trò của message headers

`MqttHeaders.RECEIVED_TOPIC` chỉ ra topic **thực tế đã nhận**. MQTT converter có thể đưa thêm QoS, retained, duplicate flag vào received headers theo phiên bản.

Không dùng `MqttHeaders.TOPIC` của outbound để suy đoán topic inbound. Với Will retained=true, subscriber mới có thể nhận retained OFFLINE khi subscribe; một status cũ cũng có thể xuất hiện do broker/session/replay, vì thế nên lưu `receivedAt`, epoch/session identifier và quyết định cách cập nhật trạng thái.

## 10. Khi nào LWT không đủ để đánh giá sức khỏe thiết bị?

Last Will chỉ cho biết **broker đã phát hiện bất thường ở MQTT connection**. Nó không chứng minh sensor, actuator hoặc business processing đang hoạt động.

| Tình huống | MQTT Keep Alive/LWT có thể quan sát? | Điều kiện bổ sung cần có |
| --- | --- | --- |
| Thiết bị mất Wi-Fi hoặc nguồn | Có thể phát hiện mất MQTT connection, rồi publish Will. | Broker và observer vẫn hoạt động. |
| Ứng dụng device bị treo nhưng MQTT networking thread còn ping | Connection vẫn có thể được coi là online. | Heartbeat nghiệp vụ và kiểm tra worker/sensor. |
| Cảm biến hỏng nhưng ứng dụng MQTT chạy | Có thể vẫn thấy ONLINE. | Kiểm tra dữ liệu cảm biến, lỗi đọc và freshness. |
| Server Spring subscriber dừng | Device connection có thể vẫn online; observer không nhận. | Monitoring riêng cho backend. |
| Broker chết | Will có thể không được gửi tại thời điểm broker offline. | Giám sát broker/cluster, reconciliation. |
| Thiết bị chủ động DISCONNECT không publish OFFLINE | Will không được phát. | Graceful shutdown contract. |
| Dữ liệu retained ONLINE quá cũ | Client có thể đã mất nhưng Will chưa được quan sát. | Timestamp/TTL ở presence store hoặc kiểm tra last-seen. |

### 10.1. Keep Alive khác heartbeat nghiệp vụ

- **Keep Alive:** protocol giữ và giám sát MQTT connection.
- **Heartbeat:** message nghiệp vụ định kỳ, chẳng hạn `{"deviceId":"device-17","seq":102,"health":"OK"}`, chứng minh một phần code ứng dụng đang chạy.
- **Health check:** có thể yêu cầu kiểm tra sensor, disk, CPU, quyền DB, khả năng thực thi lệnh.
- **Last Will:** broker phát message khi connection kết thúc bất thường.

Một thiết bị có thể duy trì MQTT connection tốt nhưng sensor không sinh dữ liệu trong nhiều giờ. Backend nên kết hợp `lastSeenAt`, `lastHealthyReadingAt`, heartbeat, LWT và tình trạng broker để đưa ra trạng thái như `ONLINE`, `OFFLINE`, `STALE`, `UNKNOWN` thay vì chỉ một boolean.

### 10.2. Thiết kế state machine cho presence

~~~mermaid
stateDiagram-v2
    [*] --> UNKNOWN
    UNKNOWN --> ONLINE: Birth ONLINE được xác nhận
    UNKNOWN --> OFFLINE: LWT OFFLINE
    ONLINE --> STALE: Không có heartbeat nghiệp vụ đủ lâu
    STALE --> ONLINE: Heartbeat / birth mới
    ONLINE --> OFFLINE: Last Will / Graceful OFFLINE
    STALE --> OFFLINE: Last Will / Graceful OFFLINE
    OFFLINE --> ONLINE: Birth ONLINE phiên mới
    ONLINE --> UNKNOWN: Broker/observer mất trạng thái tin cậy
    OFFLINE --> UNKNOWN: Không xác thực được trạng thái hiện tại
~~~

Các trạng thái và event ở đây là **policy ứng dụng**, không phải tính năng mặc định của Spring Integration. Nếu service cung cấp dashboard “thiết bị online”, cần công bố rõ nguồn bằng chứng và thời điểm cập nhật, nhất là khi retained snapshot bị cũ hoặc hệ thống vừa failover.

## 11. Retained presence, session và Client ID

### 11.1. Retained ≠ persistent session

Hai cơ chế giải quyết vấn đề khác nhau:

| Cơ chế | Gắn với | Dùng để làm gì? |
| --- | --- | --- |
| Retained message | MQTT topic tại broker. | Giữ snapshot mới nhất như `ONLINE/OFFLINE` cho subscriber mới. |
| Persistent session (`cleanSession=false`) | MQTT Client ID/session của subscriber. | Có thể giữ subscription và một số message QoS 1/2 khi subscriber offline. |
| Will | Connection của MQTT client đã CONNECT. | Broker publish message đã định nghĩa khi connection kết thúc bất thường. |
| Keep Alive | Connection đang hoạt động. | Phát hiện client không còn gửi MQTT packets theo thời gian. |

Một subscriber mới `cleanSession=true` vẫn có thể nhận retained OFFLINE nếu topic chứa snapshot đó. Một subscriber có persistent session không tự thay thế việc device phải cấu hình Will.

### 11.2. Client ID trùng có thể gây presence sai

Nếu hai device cùng dùng `device-17-client` làm Client ID, broker có thể ngắt connection trước khi cho connection mới hoạt động. Client cũ bị ngắt bất thường có thể khiến Will của nó phát OFFLINE sau khi device mới đã gửi ONLINE, tùy thứ tự và hành vi broker.

Hậu quả: retained state chập chờn `ONLINE → OFFLINE → ONLINE`, dashboard báo sai, reconnect loop và duplicate messages. **Client ID phải được quản lý như một danh tính kết nối có tính duy nhất**, không chỉ là chuỗi ngẫu nhiên dùng cho demo.

### 11.3. Reconnect sau Will phải cập nhật ONLINE

Nếu client bật `options.setAutomaticReconnect(true)`, Paho có thể tự nối lại MQTT connection sau mất mạng. Tuy nhiên, **đừng giả định** handler application tự publish ONLINE mới sau mọi lần reconnect. Cần lifecycle callback/hook phù hợp với Paho và phiên bản Spring Integration để:

1. Xác nhận kết nối mới thực sự đã thành công.
2. Phát lại retained ONLINE theo topic đúng.
3. Có thể tăng connection epoch/version.
4. Kiểm tra subscription cần thiết đã được khôi phục.
5. Theo dõi sự thay đổi trạng thái tránh tin vào OFFLINE cũ.

Một callback Paho v3 như `MqttCallbackExtended.connectComplete(...)` có thể hỗ trợ nhận biết reconnect; khi dùng callback cần tránh blocking không kiểm soát trên thread callback và theo dõi lỗi publish birth message.

## 12. Will của client backend: ai đang bị giám sát?

Một Spring Integration application cũng có thể khai báo LWT để hệ thống khác nhận diện **backend MQTT connector** mất kết nối:

~~~text
Client ID: inventory-bridge-01
Will topic: services/inventory-bridge-01/availability
Will payload: OFFLINE
Will QoS: 1
Will Retain: true
~~~

Sau khi MQTT client backend CONNECT, nó publish retained ONLINE. Khi connection đó mất bất thường, broker publish OFFLINE. Điều này giúp dashboard theo dõi **kết nối MQTT của backend bridge**, không phải chứng minh mọi inbound adapter file/SFTP/Kafka hay service DB của hệ thống đang khỏe.

### 12.1. Tránh dùng chung Will cho nhiều adapter

Nếu cùng factory bean có options chứa Will Topic `services/integration-bridge/availability` và factory được inject vào **hai adapter tạo hai MQTT clients**, cả hai có thể được broker gắn Will **cùng một topic**. Một adapter bị disconnect có thể làm dashboard báo toàn bộ service OFFLINE dù adapter kia còn hoạt động.

Giải pháp: tách factory/Will Topic theo client role, hoặc xây service-level health aggregator dựa trên nhiều tín hiệu. Không xem factory bean duy nhất là bằng chứng mọi adapter sử dụng chung một MQTT connection vật lý.

### 12.2. Lifecycle khi khởi động và dừng

- Bean `MqttPahoClientFactory` được tạo: **chưa có Will hoạt động** nếu client chưa CONNECT.
- MQTT client CONNECT thành công: Will được broker ghi nhận cho connection đó.
- Publisher/observer phát birth ONLINE: retained status được cập nhật.
- Shutdown graceful: phát OFFLINE theo policy, chờ publish completion thích hợp rồi `DISCONNECT`.
- Crash/network loss: broker phát Will nếu phát hiện và còn hoạt động.
- Reconnect: phát ONLINE mới và xác minh session/subscription.

Không phụ thuộc một `@PreDestroy` chạy không chặn để bảo đảm retained OFFLINE đã tới broker: shutdown có thời hạn và có thể bị cắt ngang, cần xử lý trạng thái chưa chắc chắn.

## 13. Điều kiện race: trạng thái OFFLINE/ONLINE đến sai thứ tự

Một hệ thống nhiều thiết bị, nhiều client hoặc broker cluster có thể quan sát các sự kiện không theo thứ tự mong muốn.

Ví dụ:

~~~text
T0: client epoch A CONNECT, PUBLISH ONLINE(A)
T1: mạng epoch A mất
T2: client epoch B CONNECT, PUBLISH ONLINE(B)
T3: broker/observer nhận Will OFFLINE(A) trễ
T4: database ghi OFFLINE(A) đè ONLINE(B) nếu không kiểm tra epoch
~~~

Không phải broker nào cũng có thứ tự chính xác này trong cùng một kết nối; đây là **kịch bản thiết kế để đánh giá race** khi có failover, nhiều client, retry, queue và consumer chạy bất đồng bộ.

Biện pháp:

1. Gắn **connection epoch/generation** do device/application tạo trước CONNECT và đưa vào birth/Will payload.
2. Lưu `receivedAt`/`lastSeenAt`, nhưng không chỉ dựa vào timestamp một nguồn không đáng tin cậy.
3. Khi xử lý state, áp dụng quy tắc **newer epoch wins** nếu có một cơ chế cấp generation đáng tin cậy.
4. Có thể lưu trạng thái thiết bị gắn với **Client ID/session owner** và đối soát lại với broker/heartbeat.
5. Sử dụng idempotency để không ghi lặp cùng event.
6. Không phát action nguy hiểm chỉ vì một OFFLINE/ONLINE đơn lẻ mà chưa có chính sách debounce.

### 13.1. Last Will không có timestamp mới nhất của client

Will được gửi dưới dạng payload **đã chuẩn bị từ trước**. Vì vậy, field `emittedAt` trong Will nếu tính tại lúc CONNECT là timestamp của thời điểm đăng ký, không phải thời điểm mất kết nối. Nếu cần timestamp “broker xác định OFFLINE”, sinh ở server/observer khi nhận Will và lưu source rõ ràng.

### 13.2. Presence OFFLINE có thể là trạng thái tạm thời

Thiết bị mất Wi-Fi 3 giây trên mạng di động nhưng broker phát Will sau phát hiện socket reset; thiết bị reconnect ngay sau đó. Nếu ứng dụng gửi liên tiếp email “thiết bị offline”/“thiết bị online” cho mỗi lần, người dùng có thể bị spam. Dùng debounce, hysteresis, alert threshold và phân loại sự kiện theo SLA.

## 14. Bảo mật Last Will và availability topic

Một topic presence có thể bị giả mạo nếu broker cho phép publisher không đáng tin gửi `ONLINE` hoặc `OFFLINE` thay cho thiết bị khác.

| Rủi ro | Kiểm soát |
| --- | --- |
| Publisher bất kỳ ghi `devices/device-17/availability` | Broker ACL ràng buộc identity với topic được phép, và validation ở application. |
| LWT payload chứa token hoặc PII | Chỉ lưu trạng thái/ID cần thiết, không để secret trong Will hoặc retained message. |
| Kết nối MQTT plaintext qua mạng bên ngoài | TLS, xác minh broker certificate, credentials/mTLS phù hợp. |
| Client ID trùng hoặc spoofing | Cấp Client ID duy nhất, ràng buộc identity ở broker khi hỗ trợ. |
| Subscriber đọc trạng thái tenant khác | Subscribe ACL theo tenant/device; không dùng wildcard toàn bộ topic nếu không cần. |
| Retained OFFLINE bị để lại sau xóa thiết bị | Quy trình cleanup retained với quyền và audit. |
| Dữ liệu trạng thái cũ kích hoạt hành động nguy hiểm | TTL nghiệp vụ, state freshness, idempotency và business authorization. |
| Broker/observer downtime | Theo dõi broker health; trạng thái `UNKNOWN` khi không có bằng chứng đủ mới. |

**Client ID hoặc topic name không phải bằng chứng xác thực thiết bị.** Chỉ vì message mang topic `devices/device-17/availability` chưa chứng minh thực sự do device-17 tạo ra. Broker authentication/ACL và hợp đồng nghiệp vụ phải ràng buộc nguồn dữ liệu.

## 15. Xử lý lỗi và khả năng phục hồi

Last Will là một tín hiệu connection, không phải cơ chế retry cho flow nghiệp vụ. Một pipeline có thể lỗi ở các tầng:

~~~mermaid
flowchart TD
    DEV["Device MQTT client"]
    BROKER[("Broker lưu Will và retained")]
    ADAPTER["Spring inbound MQTT adapter"]
    CH["mqtt.presence.in"]
    FLOW["Validate / Presence store"]
    ERROR["Error flow / quarantine / retry"]
    DEV -->|"CONNECT Will + PUBLISH ONLINE"| BROKER
    DEV -. "mất connection" .-> BROKER
    BROKER -->|"Will OFFLINE"| ADAPTER --> CH --> FLOW
    ADAPTER -. "subscribe / converter lỗi" .-> ERROR
    CH -. "consumer unavailable" .-> ERROR
    FLOW -. "DB lỗi" .-> ERROR
~~~

| Lỗi | LWT có tự giải quyết? | Chiến lược phù hợp |
| --- | --- | --- |
| Device mất connection bất thường | Broker có thể phát Will nếu đã đăng ký. | Consumer trạng thái, retained presence và monitoring. |
| Graceful device disconnect | **Không** phát Will. | Publish OFFLINE chủ động trước DISCONNECT. |
| Broker offline | Không phát/giao Will trong khi broker không hoạt động. | Broker monitoring/HA, reconcile sau phục hồi. |
| Observer Spring mất kết nối | Device vẫn có thể online. | Client recovery, subscription/session và kiểm tra trạng thái sau reconnect. |
| JSON/payload presence không hợp lệ | Không. | Validate, quarantine, audit topic/device ID. |
| Database cập nhật presence thất bại | Không. | Retry handler/idempotency/outbox/persistent queue. |
| Device business worker treo nhưng network thread ping | LWT không phát vì connection còn sống. | Heartbeat nghiệp vụ và health checks. |
| Command xử lý trùng | Không. | Command ID, unique constraint, ACK/đối soát. |

### 15.1. Spring Integration error channel

Với `DirectChannel`, exception từ handler có thể lan theo call stack của endpoint gửi. Ở inbound MQTT, đường đi từ Paho callback tới Spring flow và cách publish `ErrorMessage` phụ thuộc endpoint/error channel được cấu hình. Không giả định một exception ném trong `PresenceFlowConfiguration` luôn khiến broker phát lại cùng message hoặc rollback MQTT acknowledgement.

Nếu message presence sai schema, nên đưa vào quarantine có lý do và metadata. Nếu database đang không sẵn sàng, dùng retry có giới hạn và idempotent update. Nếu observer mất mạng, cần kiểm tra session/reconnect và retained status chứ không chỉ đọc error logs.

### 15.2. QoS 1/2 và duplicate trạng thái

Một Will publication dùng QoS 1 có thể được giao lại ở tầng MQTT; ứng dụng cũng có thể nhận lại retained OFFLINE khi subscribe mới. Xử lý duplicate `OFFLINE` phải **idempotent**. Với presence store, cập nhật cùng status nhiều lần không nên kích hoạt nhiều cảnh báo/side effect nếu không có thay đổi thực.

### 15.3. Không kích hoạt hành động bằng LWT thiếu kiểm soát

Ví dụ “thiết bị OFFLINE → tự reset ổ điện” có thể nguy hiểm nếu đó là kết quả mạng tạm mất, retained stale hoặc một publisher giả mạo. Khi LWT dẫn tới hành động vật lý, cần xác minh thêm trạng thái, quyền, debounce, giới hạn tần suất và cơ chế hồi phục an toàn.

## 16. Kiểm thử flow Spring không cần broker

Phần xử lý sau MQTT inbound adapter nên được unit/integration test tách khỏi network. `PresenceFlowConfiguration` ở mục 9 chỉ cần channel, sink và IntegrationFlow; ta có thể tạo Spring test context **không nạp `PresenceTransportConfiguration`**.

Maven test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo `PresenceFlowTest.java`:

~~~java
package demo.mqttpresence;

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

@SpringJUnitConfig(classes = PresenceFlowConfiguration.class)
class PresenceFlowTest {

    @Autowired
    @Qualifier("mqtt.presence.in")
    MessageChannel input;

    @Autowired
    PresenceSink sink;

    @BeforeEach
    void reset() {
        sink.clear();
    }

    @Test
    void recordsOnlineAndOffline() {
        input.send(MessageBuilder.withPayload("ONLINE")
                .setHeader(MqttHeaders.RECEIVED_TOPIC,
                        "devices/device-17/availability")
                .build());

        input.send(MessageBuilder.withPayload("OFFLINE")
                .setHeader(MqttHeaders.RECEIVED_TOPIC,
                        "devices/device-17/availability")
                .build());

        assertEquals(
                List.of(
                        new PresenceEvent(
                                "devices/device-17/availability",
                                "ONLINE"),
                        new PresenceEvent(
                                "devices/device-17/availability",
                                "OFFLINE")),
                sink.snapshot());
    }

    @Test
    void rejectsWrongTopicFormatBeforeRecording() {
        assertThrows(RuntimeException.class,
                () -> input.send(
                        MessageBuilder.withPayload("ONLINE")
                                .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                        "devices/other/tenant/availability")
                                .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void rejectsUnsupportedPresenceStatus() {
        assertThrows(RuntimeException.class,
                () -> input.send(
                        MessageBuilder.withPayload("NOT_SURE")
                                .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                        "devices/device-17/availability")
                                .build()));

        assertTrue(sink.snapshot().isEmpty());
    }
}
~~~

Hai test reject dùng `RuntimeException` ở tầng caller để tránh phụ thuộc wrapper exception cụ thể của phiên bản Spring Integration; trong ứng dụng thật cần kiểm tra nguyên nhân sâu hơn và assert error policy. Với `DirectChannel`, các lời gọi handler thông thường chạy đồng bộ, nên có thể đọc `sink.snapshot()` ngay sau `send(...)`.

Test chứng minh **channel wiring, payload validation và presence sink**, nhưng **không** chứng minh broker đã phát Last Will, Keep Alive vận hành, retained flag đúng hoặc adapter reconnect. Phải có broker integration tests cho những điều đó.

## 17. Thử Last Will với broker MQTT thực

Chỉ thử trên broker test mà bạn kiểm soát. Ví dụ broker chạy `tcp://localhost:1883` và đã cài CLI Mosquitto.

### 17.1. Bước 1: quan sát availability

Mở một terminal và subscribe:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-presence-observer-cli-1 \
  -q 1 -t 'devices/+/availability' -v
~~~

Khi chưa có retained status, subscriber có thể chờ message. Nếu broker đã giữ snapshot cũ, CLI có thể hiển thị status ngay sau subscribe; phải phân biệt retained snapshot với publication mới.

### 17.2. Bước 2: chạy simulator và nhìn ONLINE

Khởi động `DeviceWillSimulator` trong một process riêng. Khi CONNECT thành công, chương trình publish retained ONLINE:

~~~text
devices/device-17/availability ONLINE
~~~

Spring observer ở mục 9 cũng có thể nhận message qua `MqttPahoMessageDrivenChannelAdapter`.

### 17.3. Bước 3a: shutdown sạch

Nhấn Enter trong simulator để code publish retained OFFLINE rồi gọi `disconnect()`.

Kỳ vọng: observer nhận OFFLINE **do device publish chủ động**; không cần broker publish Will. Nếu device chỉ gọi DISCONNECT mà không publish OFFLINE, một retained ONLINE có thể vẫn còn.

### 17.4. Bước 3b: mất kết nối bất thường

Khởi chạy lại simulator, chờ ONLINE, sau đó **kết thúc cưỡng bức tiến trình client mà không cho nó gửi DISCONNECT**. Giữ broker và observer đang chạy.

Kỳ vọng: broker nhận biết kết nối client đã mất rồi publish Will `OFFLINE` vào topic availability. Thời gian quan sát phụ thuộc việc broker phát hiện socket mất hoặc keepalive; không mặc định đúng 20 giây.

Lưu ý: chỉ tắt simulator của bạn trong môi trường test; **không** làm gián đoạn thiết bị, broker hoặc ứng dụng production. Không dùng việc dừng broker làm phép thử duy nhất cho LWT, vì broker offline thì không thể giao Will tức thời.

### 17.5. Bước 4: kiểm tra retained OFFLINE

Sau khi Will đã được phát, mở subscriber mới:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-presence-observer-cli-2 \
  -q 1 -t 'devices/device-17/availability' -v
~~~

Nếu broker giữ retained Will, subscriber mới có thể nhận OFFLINE ngay khi subscribe. Điều đó minh họa RETAIN=true làm snapshot vẫn có ích cho consumer đến sau.

### 17.6. Bước 5: reconnect và online lại

Khởi động lại simulator. Nó CONNECT rồi publish ONLINE retained trên cùng topic, thay thế retained OFFLINE. Một subscriber mới sau thời điểm này có thể nhận ONLINE.

Nếu sản phẩm thật dùng Paho auto reconnect, phải có callback/hook publish ONLINE **sau mỗi lần reconnect**, không chỉ khi khởi động process. Cần kiểm tra status không bị retained OFFLINE cũ hoặc event từ connection epoch trước ghi đè.

### 17.7. Ma trận test cần có

| Kịch bản | Thao tác | Kết quả cần kiểm chứng |
| --- | --- | --- |
| CONNECT có Will | Device khai báo `setWill(...)` rồi kết nối. | Broker biết Will sau CONNECT thành công. |
| Clean DISCONNECT | Device gửi OFFLINE chủ động rồi DISCONNECT. | Không có Will ngoài ý muốn; retained state là OFFLINE. |
| Process crash | Kết thúc device client bất thường, broker vẫn sống. | Broker publish Will khi phát hiện mất connection. |
| Network blackhole | Chặn traffic của một device client trong test. | Phát hiện theo keepalive/TCP, không đòi SLA cứng. |
| Subscriber đến muộn | Subscribe mới sau retained OFFLINE. | Nhận snapshot retained phù hợp. |
| Device reconnect | CONNECT và publish ONLINE. | Trạng thái mới thay retained OFFLINE. |
| Duplicate Client ID | Tạo hai clients active trùng ID. | Quan sát khả năng connection bị thay thế; sửa cấp ID. |
| Broker downtime | Dừng broker test. | Không giả định Will được phát khi chính broker không chạy. |
| Backend observer offline | Dừng Spring subscriber, rồi khởi động lại. | Subscription/session/retained phù hợp policy. |
| Graceful shutdown thiếu OFFLINE | Chỉ DISCONNECT. | Có thể giữ retained ONLINE cũ; xác nhận bug policy. |
| Business worker bị treo | MQTT networking vẫn ping được. | LWT có thể **không** phát; cần heartbeat nghiệp vụ. |
| Will có QoS 1 | Mô phỏng delivery lại. | Presence store idempotent, không gửi trùng thông báo. |

## 18. Quan sát, vận hành và xử lý sự cố

### 18.1. Những metric nên có

| Metric/field gợi ý | Tác dụng |
| --- | --- |
| `mqtt_client_connected` | Theo dõi trạng thái MQTT connection, phân biệt client role. |
| `mqtt_last_packet_at` | Hỗ trợ phân tích keepalive và network. |
| `mqtt_keepalive_seconds` | Kiểm tra đúng cấu hình, tránh nhầm giây với mili giây. |
| `mqtt_reconnect_attempts_total` | Phát hiện reconnect loop. |
| `mqtt_last_will_received_total` | Đo số event Will observer nhận, sau khi xác định đúng nguồn dữ liệu. |
| `device_presence_last_seen_at` | Biết thời điểm backend quan sát status/heartbeat gần nhất. |
| `device_presence_epoch` | Đối soát status thuộc connection generation nào. |
| `device_heartbeat_lag_seconds` | Phát hiện business worker/sensor không hoạt động dù MQTT còn kết nối. |
| `mqtt_inbound_error_total` | Phát hiện payload lỗi, channel dispatch fail và adapter problems. |
| `broker_available` | Biết độ tin cậy của nguồn phát Last Will. |

Tên metric chỉ mang tính **gợi ý thiết kế**, không phải bộ metric Spring Integration/Paho tự sinh với đúng tên này. Không đưa credentials, token hoặc full payload nhạy cảm vào log.

### 18.2. Dấu hiệu lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| Không thấy OFFLINE khi device mất điện. | Client không khai báo Will, broker chưa phát hiện mất connection, broker offline hoặc observer không subscribe. | Kiểm tra CONNECT Will, topic filter, keepalive, broker log và subscriber. |
| Device DISCONNECT sạch nhưng dashboard vẫn ONLINE. | Không publish retained OFFLINE chủ động. | Bổ sung graceful shutdown presence policy. |
| Sau reconnect vẫn thấy retained OFFLINE. | Không publish ONLINE mới sau kết nối lại. | Birth message trong connect-complete lifecycle. |
| ONLINE/OFFLINE nhấp nháy. | Network chập chờn, trùng Client ID hoặc event cũ ghi đè. | Kiểm tra reconnect, epoch/order và debounce. |
| Cần offline trong 5 giây nhưng Keep Alive=60. | SLA phát hiện không khớp tham số và điều kiện mạng. | Đo từ packet cuối tới detection; phối hợp heartbeat/alert threshold. |
| Keep Alive ngắn khiến thiết bị hao pin. | Ping quá thường xuyên khi không có traffic. | Chọn khoảng phù hợp với power/network SLA. |
| Đổi connection timeout mà không đổi thời gian phát Will. | Connection timeout khác Keep Alive. | Kiểm tra `setKeepAliveInterval(...)` và broker behavior. |
| Retained OFFLINE mất sau broker restart. | Persistence/broker state không bền hoặc cluster khác. | Kiểm thử broker persistence, HA và reconciliation. |
| Subscriber không nhận Will sau restart. | Session/topic filter sai hoặc adapter chưa reconnect. | Kiểm tra observer Client ID, QoS, subscription và error flow. |
| LWT báo ONLINE nhưng sensor hỏng. | LWT chỉ phản ánh MQTT connection. | Heartbeat/business health checks. |
| Một Will OFFLINE làm toàn bộ backend bị báo OFFLINE. | Nhiều clients dùng cùng Will Topic. | Will namespace và factory/client identity riêng. |
| LWT gây xử lý lệnh lặp. | Presence event kích hoạt side effect thiếu dedup/policy. | Idempotency, hạn chế automation, business ACK và validation. |

## 19. Bài thực hành: xây hệ thống giám sát thiết bị an toàn

**Bối cảnh:** một hệ thống giám sát hàng trăm thiết bị đo nhiệt độ. Thiết bị có thể mất mạng ngắn hạn. Dashboard cần hiển thị trạng thái kết nối, nhưng không được coi ONLINE là bằng chứng cảm biến hoạt động đúng, cũng không được thực hiện hành động nguy hiểm khi nhận một event OFFLINE cũ.

### Yêu cầu

1. Định nghĩa topic `devices/{deviceId}/availability`, `devices/{deviceId}/heartbeat`, `sensors/{deviceId}/temperature`.
2. Client device đặt Will Topic availability, payload OFFLINE, QoS 1, retained=true, Keep Alive 20 giây trước CONNECT.
3. Sau CONNECT, device publish ONLINE retained; khi shutdown bình thường, publish OFFLINE retained rồi DISCONNECT.
4. Sau reconnect, device phải publish ONLINE mới và ghi nhận connection epoch.
5. Spring Integration MQTT inbound adapter subscribe `devices/+/availability` và chuyển message vào `mqtt.presence.in`.
6. Flow kiểm tra topic shape, payload schema, quyền device/tenant và trạng thái connection generation; trạng thái sai đi quarantine.
7. Lưu presence vào database theo update idempotent; thêm `receivedAt`, `lastHeartbeatAt` và policy `UNKNOWN/STALE`.
8. Viết test không broker cho flow, rồi test broker khi client crash, network blackhole và shutdown sạch.
9. Test retained status trước và sau khi thiết bị reconnect; kiểm tra không dùng retained snapshot cũ như bằng chứng mới nhất nếu thiếu thông tin.
10. Cho hai device instances dùng trùng Client ID trong môi trường test; giải thích reconnect loop và khắc phục.
11. Thử broker restart/failover; xác định trường hợp Will không thể được quan sát ngay.
12. Thiết kế alert debounce và business heartbeat để tránh nhầm MQTT network health với sensor health.
13. Hạn chế ACL để device chỉ publish availability/telemetry của chính nó; không để client khác giả trạng thái.
14. Đối soát dashboard khi observer Spring offline nhiều phút rồi subscribe lại.

**Tiêu chí đạt:** phân biệt clean DISCONNECT với crash, giải thích thời điểm broker phát Will không chính xác tuyệt đối, retained OFFLINE được thay bởi retained ONLINE sau reconnect, Spring flow không xử lý sai tenant/topic, presence store idempotent và dashboard có trạng thái UNKNOWN/STALE khi chưa đủ bằng chứng.

## 20. Câu hỏi tự kiểm tra

1. Last Will được MQTT client gửi lúc mất điện hay broker publish từ nội dung CONNECT đã đăng ký?
2. `setWill(...)` nhận những tham số nào và vì sao topic Will phải cụ thể?
3. Vì sao clean `DISCONNECT` thường không kích hoạt Will?
4. Nếu client shutdown bình thường nhưng không publish OFFLINE, retained ONLINE có thể vẫn còn không?
5. `setKeepAliveInterval(20)` là 20 giây hay 20 mili giây?
6. `PINGREQ` và `PINGRESP` xuất hiện khi nào?
7. Tại sao quy tắc khoảng 1,5 lần Keep Alive không phải SLA OFFLINE chính xác tuyệt đối?
8. Broker có thể phát Will trước ngưỡng keepalive không?
9. Nếu chính broker mất điện, có thể trông đợi subscriber nhận Will tức thì không?
10. Vì sao retained=true hữu ích cho availability topic nhưng không phải event log?
11. Sau reconnect tự động, client cần cập nhật trạng thái ONLINE ở đâu?
12. Keep Alive có phát hiện business worker bị deadlock trong khi MQTT ping thread vẫn chạy không?
13. Retained state và `cleanSession=false` liên quan nhau ra sao?
14. Client ID trùng có thể tạo vòng reconnect và trạng thái sai như thế nào?
15. Đặt Will trên factory Spring backend có tự động thay device firmware khai báo Will không?
16. Một factory tạo hai clients có cùng Will Topic có rủi ro gì?
17. Vì sao Will payload không thể mang chính xác timestamp tại thời điểm network vừa đứt do device tính?
18. Khi DB observer bị lỗi, LWT có rollback MQTT ACK hoặc tự retry business transaction không?
19. Cần những tín hiệu nào để phân biệt ONLINE, STALE và UNKNOWN?
20. Có nên dùng LWT OFFLINE đơn lẻ để tự kích hoạt lệnh nguy hiểm không?
21. Test fake `MessageChannel`/IntegrationFlow có thể chứng minh broker phát Will không?
22. Đâu là khác biệt giữa Last Will/Keep Alive và một application-level heartbeat?

**Gợi ý:** Keep Alive hỗ trợ broker phát hiện connection bất thường; Last Will là PUBLISH do broker phát khi cần; retained dùng snapshot, Client ID/session dùng quản lý connection/subscription; heartbeat/health và idempotency giúp business state đáng tin cậy hơn.

## 21. Kết luận

**Last Will và Keep Alive** phối hợp để MQTT hỗ trợ tín hiệu trạng thái kết nối:

- **Last Will** được client khai báo trước trong CONNECT. Khi connection kết thúc bất thường, broker có thể publish Will Topic/Payload với QoS và retained policy đã cấu hình; khi client DISCONNECT sạch, Will thông thường không được phát.
- **Keep Alive** quy định khoảng hoạt động MQTT và dùng `PINGREQ`/`PINGRESP` khi cần. Broker phát hiện connection không còn hoạt động theo quy tắc giao thức, nhưng thời gian quan sát OFFLINE không phải một cam kết chính xác tuyệt đối.
- **Retained ONLINE/OFFLINE** tạo snapshot presence cho subscriber mới. Device phải publish ONLINE sau connect/reconnect và OFFLINE chủ động khi shutdown bình thường.
- **Spring Integration MQTT inbound adapter** nhận các PUBLISH đó qua `MessageChannel` và `IntegrationFlow` để cập nhật presence store, xử lý lỗi và tích hợp DB/HTTP/Kafka hoặc hệ thống quan sát khác.

Trong module **SPRING_INTEGRATION_ADAPTERS**, thiết kế đáng tin cậy phải kết hợp Client ID, QoS, retained/session, reconnect, TLS/ACL, metadata và kiểm thử broker thực tế. **LWT chỉ cho biết trạng thái MQTT connection, không phải sức khỏe nghiệp vụ của thiết bị**; vì vậy cần thêm heartbeat, freshness, idempotency, error handling và quy tắc đối soát trước khi dùng presence để đưa ra quyết định quan trọng.

