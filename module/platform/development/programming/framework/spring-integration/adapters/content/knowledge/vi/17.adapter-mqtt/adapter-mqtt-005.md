# QoS retain và clean session

## 1. Bối cảnh và mục tiêu

Khi kết nối Spring Integration với MQTT broker, ba lựa chọn có ảnh hưởng lớn tới hành vi nhận/gửi message là **Quality of Service (QoS)**, **retained message** (thường gọi ngắn là *retain*) và **clean session**. Chúng phục vụ **ba vấn đề khác nhau**:

- **QoS:** mức bảo đảm chuyển giao một MQTT PUBLISH giữa các bên tham gia giao thức.
- **Retain:** broker có giữ lại bản tin cuối cùng trên một topic để gửi cho subscriber mới không?
- **Clean session:** MQTT 3.1.1 client/broker có duy trì session/subscription và dữ liệu liên quan sau khi client ngắt kết nối không?

Ba khái niệm không thay thế nhau. Một retained message không phải hàng đợi lưu mọi event; clean session không xác định QoS; QoS 2 không bảo đảm database hoặc thiết bị chỉ thực hiện một nghiệp vụ đúng một lần.

Bài này nằm trong chương **Adapter MQTT** của module **SPRING_INTEGRATION_ADAPTERS**, nơi người học kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành trao đổi qua file, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu và quản lý lỗi, hợp đồng message, vòng đời kết nối. Với MQTT, Spring Integration kết nối broker bằng các adapter Paho, rồi truyền message qua channel đến business flow hoặc publish trở lại broker.

Sau bài học, người học có thể:

1. Phân biệt chính xác QoS 0, 1, 2 và phạm vi bảo đảm của từng cấp.
2. Giải thích retained flag trên publication và việc xóa retained message.
3. Thiết kế clean session theo **MQTT 3.1.1**, Client ID, subscription và trường hợp offline/reconnect.
4. Chọn cấu hình khác nhau cho **telemetry**, **state snapshot**, **command một lần** và **sự kiện quan trọng**.
5. Đặt QoS/retained từ `MqttHeaders` hoặc default của `MqttPahoMessageHandler`.
6. Cấu hình inbound QoS và clean session qua `MqttPahoMessageDrivenChannelAdapter` và `MqttConnectOptions`.
7. Viết Java DSL flow, unit test không broker và test end-to-end có broker.
8. Thiết kế retry, idempotency, replay, bảo mật và giám sát đúng tầng.

> **Phạm vi phiên bản:** ví dụ dùng Spring Integration MQTT dựa trên Eclipse Paho MQTT v3 và MQTT **3.1.1**. MQTT 5 dùng *Clean Start* và *Session Expiry Interval* thay cho mô hình một cờ `cleanSession`; không áp dụng nguyên xi API v3 của bài này cho MQTT 5.

## 2. Ba khái niệm trên ba trục độc lập

~~~mermaid
flowchart LR
    PUB["Publisher<br/>PUBLISH(payload, topic, QoS, RETAIN)"]
    B[("MQTT broker<br/>session + retained state")]
    SUB["Subscriber<br/>Client ID + cleanSession + subscription QoS"]
    FLOW["Spring Integration<br/>MessageChannel → Handler"]
    PUB -->|"QoS đường publish"| B
    B -->|"QoS delivery theo subscription"| SUB
    B -.->|"Retained snapshot khi subscribe"| SUB
    SUB -->|"Inbound message-driven adapter"| FLOW
~~~

| Thuộc tính | Đặt ở đâu? | Tác động chính | **Không** bảo đảm |
| --- | --- | --- | --- |
| **QoS publish** | Publisher/`MqttPahoMessageHandler` hoặc `MqttHeaders.QOS`. | Cơ chế giao nhận publication tới broker theo QoS đã chọn. | Subscriber thực hiện side effect đúng một lần. |
| **QoS subscription** | Subscriber/`MqttPahoMessageDrivenChannelAdapter.setQos(...)`. | Cấp QoS tối đa broker có thể dùng khi gửi message phù hợp đến client. | Thay đổi QoS của publication gốc hoặc bảo đảm database đã commit. |
| **RETAIN** | Publisher/`MqttHeaders.RETAINED` hoặc default handler. | Yêu cầu broker duy trì bản tin retained mới nhất của topic. | Lưu lịch sử sự kiện hoặc mọi message khi subscriber offline. |
| **Clean session** | Client `MqttConnectOptions.setCleanSession(...)` khi CONNECT. | Quy định việc bắt đầu mới hay duy trì session MQTT 3.1.1. | Tự tạo durable queue/transaction của Spring Integration. |
| **Client ID** | Khi tạo MQTT client/adapter. | Broker nhận diện client session cụ thể. | Định danh event/command cho idempotency nghiệp vụ. |

Một ví dụ quan trọng: thiết bị publish giá trị nhiệt độ tại `sensors/device-17/temperature` với QoS 1 và RETAIN=true. Một subscriber mới cleanSession=true có thể nhận snapshot retained gần nhất ngay khi subscribe, nhưng **không nhận toàn bộ nhiệt độ trong quá khứ**. Một subscriber offline dùng persistent session, Client ID ổn định và subscription QoS 1 có thể nhận các message QoS 1/2 broker lưu khi offline theo chính sách broker, ngay cả khi các publication đó **không retained**.

## 3. QoS 0: at most once

MQTT QoS 0 dùng một lần gửi `PUBLISH` mà không có handshake acknowledgement dành cho QoS 1/2. Nó ưu tiên chi phí thấp, độ trễ và lưu lượng protocol.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as MQTT broker
    participant S as Subscriber
    P->>B: PUBLISH(QoS=0)
    B->>S: PUBLISH nếu subscriber đủ điều kiện
    Note over P,S: Không có handshake PUBACK/PUBREC/PUBREL/PUBCOMP
~~~

Điểm cần nhớ:

- Publication có thể mất khi connection đứt, broker không hoạt động hoặc client không nhận kịp.
- Không nên kỳ vọng redelivery có bảo đảm từ MQTT QoS 0.
- Nếu Spring source chỉ giữ telemetry trong RAM, lỗi kết nối có thể dẫn đến mất bản ghi không phục hồi.
- Dùng QoS 0 cho dữ liệu có thể lấy mẫu lại, chẳng hạn nhiệt độ gửi rất thường xuyên, **nếu nghiệp vụ cho phép mất vài mẫu**.

Ví dụ:

~~~text
topic   = sensors/device-17/temperature
payload = {"deviceId":"device-17","celsius":26.5}
qos     = 0
retain  = false
~~~

**Bẫy thường gặp:** send trong Spring Integration trả về thành công không có nghĩa subscriber đã nhận QoS 0 message. Khi ứng dụng gọi outbound handler, kết quả phụ thuộc đường xử lý và chế độ sync/async, nhưng không tồn tại ACK tầng MQTT QoS 1/2 cho publication QoS 0.

## 4. QoS 1: at least once

QoS 1 dùng một handshake hai bước `PUBLISH → PUBACK`. Khi client chưa thấy xác nhận trong điều kiện protocol tương ứng, bản tin có thể được giao lại. Điều này cải thiện khả năng delivery nhưng cho phép **duplicate**.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as MQTT broker
    P->>B: PUBLISH(QoS=1, packetId=42)
    B-->>P: PUBACK(packetId=42)
    Note over P,B: Nếu PUBACK bị mất, PUBLISH có thể được gửi lại
~~~

Đối với publisher → broker, QoS 1 chỉ xác nhận delivery theo giao thức cho **chặng này**. Broker → subscriber là một chặng khác, với subscription QoS và session riêng. Một lần PUBACK ở publisher **không chứng minh**:

1. Subscriber đang online.
2. Subscriber thực sự đọc được payload.
3. Thiết bị đã thực hiện lệnh.
4. Service handler trong Spring đã commit database.

**Ví dụ duplicate nghiệp vụ:** publisher tạo command `cmd-1001`, broker nhận và gửi PUBACK nhưng gói ACK thất lạc. Ứng dụng retry bằng một PUBLISH mới, subscriber có thể nhận command lần nữa. Dù chỉ một packet bị gửi lại với DUP flag hay hai publication riêng có cùng payload, application vẫn cần **commandId** và chính sách idempotency.

| Loại dữ liệu | Khi QoS 1 phù hợp | Điều kiện bổ sung |
| --- | --- | --- |
| Sự kiện cập nhật tồn kho | Cần ưu tiên không mất event. | Dùng `eventId`, idempotency và checkpoint. |
| Command thay trạng thái | Thiết bị cần có cơ hội nhận lệnh khi mạng chập chờn. | Tránh thực hiện tác dụng phụ hai lần, có ACK nghiệp vụ. |
| Telemetry quan trọng | Cần khả năng delivery tốt hơn QoS 0. | Dedup theo device ID + sequence/event ID. |

Không đồng nhất “at least once” ở tầng MQTT với “cứ xử lý database thất bại thì broker chắc chắn phát lại”. Thời điểm MQTT acknowledgement, manual ack option và error path phải được xác minh riêng theo adapter/client phiên bản thực tế.

## 5. QoS 2: exactly once ở tầng MQTT

QoS 2 dùng handshake bốn bước để xử lý một publication trong phạm vi MQTT protocol:

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as MQTT broker
    P->>B: PUBLISH(QoS=2, packetId=42)
    B-->>P: PUBREC(packetId=42)
    P->>B: PUBREL(packetId=42)
    B-->>P: PUBCOMP(packetId=42)
~~~

Với một phiên MQTT hợp lệ, handshake giúp ngăn duplicate delivery **của cùng một publication ở tầng giao thức**. Tuy nhiên:

- Publisher vẫn có thể tạo **hai publication khác nhau** cùng biểu diễn một event nghiệp vụ.
- Sau khi message được Spring Integration chuyển tới handler, một transaction DB có thể fail hoặc được retry riêng.
- Thiết bị có thể thực thi lệnh rồi crash trước khi phát ACK nghiệp vụ; caller retry tạo một command khác cùng tác dụng.
- Việc tăng QoS có thêm chi phí protocol, trạng thái in-flight và độ trễ so với QoS thấp hơn.

**Không gọi QoS 2 là “exactly once end-to-end”.** Nếu yêu cầu không ghi trùng hóa đơn, cần database unique constraint/idempotency key; nếu yêu cầu thiết bị không mở khóa hai lần, cần command ID, trạng thái và kiểm soát nghiệp vụ riêng. Chọn QoS 2 khi giao thức và SLA thực sự cần, sau khi đo chi phí broker/client.

## 6. QoS hiệu lực khi publisher và subscriber khác mức

Publisher chọn QoS cho mỗi PUBLISH; subscriber chọn mức QoS khi SUBSCRIBE. Trong MQTT 3.1.1, broker phân phối message ở mức QoS tối đa không vượt mức subscription đã được chấp nhận; thường diễn đạt bằng:

~~~text
QoS_delivery = min(QoS_publish, QoS_subscription)
~~~

| QoS PUBLISH | QoS SUBSCRIBE | QoS broker thường giao cho subscriber |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 0 | 1 | 0 |
| 0 | 2 | 0 |
| 1 | 0 | 0 |
| 1 | 1 | 1 |
| 1 | 2 | 1 |
| 2 | 0 | 0 |
| 2 | 1 | 1 |
| 2 | 2 | 2 |

Ví dụ outbound handler đặt `MqttHeaders.QOS = 1`, nhưng subscriber subscribe filter ở QoS 0: chặng delivery đến subscriber có thể là **QoS 0**. Vì thế việc thay đổi publisher QoS chỉ giải quyết một phần vấn đề; phải kiểm tra cả subscriber QoS và broker policy.

Nếu topic filter trùng nhau hoặc có nhiều subscription overlapping, broker có quy định cách giao hiệu lực; khi đó không nên suy luận đơn giản “mọi subscription đều nhận một bản sao”. Thử nghiệm với broker thật để xác định hành vi cần cho ứng dụng.

## 7. Retained message: snapshot mới nhất của một topic

Khi publisher gửi một `PUBLISH` với flag **RETAIN=true**, broker được yêu cầu lưu message retained mới nhất cho **topic đó**. Một subscriber tạo subscription phù hợp sau đó có thể nhận retained message theo hành vi protocol/broker.

~~~mermaid
sequenceDiagram
    participant P as Temperature publisher
    participant B as MQTT broker
    participant S as Subscriber mới
    P->>B: PUBLISH(topic=devices/17/state, RETAIN=true, state=ON)
    Note over B: Lưu retained snapshot gần nhất cho topic
    S->>B: SUBSCRIBE(devices/+/state)
    B-->>S: Retained state=ON
~~~

Một topic thường chỉ có **snapshot retained gần nhất**, không phải lịch sử mọi publication:

~~~text
PUBLISH retained=true, topic=devices/17/state, payload=OFF
PUBLISH retained=true, topic=devices/17/state, payload=ON

Subscriber mới subscribe devices/+/state
  → Nhận snapshot retained ON, không nhận cả OFF và ON như event log.
~~~

Retained đặc biệt phù hợp với dữ liệu kiểu **current state**:

- Thiết bị đang online/offline và trạng thái mới nhất.
- Giá trị cấu hình mong muốn tại thời điểm hiện tại.
- Snapshot nhiệt độ gần nhất nếu subscriber mới cần nhìn thấy ngay.

**Không dùng retained bừa bãi cho command một lần** như mở khóa, thanh toán, kích hoạt bơm hoặc gửi SMS. Subscriber mới hoặc subscriber đăng ký lại có thể nhận một command cũ và thực hiện lại side effect.

### 7.1. RETAIN=false không xóa snapshot retained trước đó

Nếu broker đã giữ retained message trên topic, sau đó publisher gửi một message mới với `RETAIN=false`, publication không tự thay thế/xóa snapshot retained đang lưu. Khi cần cập nhật retained state, phải publish retained mới.

Ví dụ:

~~~text
t1: PUBLISH topic=devices/17/state, payload=ON,  RETAIN=true
t2: PUBLISH topic=devices/17/state, payload=OFF, RETAIN=false
t3: subscriber mới SUBSCRIBE devices/+/state
    → Có thể nhận snapshot retained ON được lưu từ t1.
~~~

Điều này dễ gây lỗi “subscriber mới thấy trạng thái cũ” dù log ứng dụng cho thấy một publication gần đây hơn. Cần quy ước nhất quán: **state snapshot luôn publish retained=true** nếu broker được dùng như bộ nhớ state đó.

### 7.2. Xóa retained message

Trong MQTT 3.1.1, cách yêu cầu broker xóa retained state của một topic là publish tới **đúng topic đó** với RETAIN=true và **payload dài 0 byte**.

Ví dụ CLI (broker thử nghiệm):

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' \
  -q 1 -r -n
~~~

Ở đây `-r` bật retained flag, `-n` chỉ định payload rỗng. Đây là **lệnh thay đổi retained state** trên broker. Không chạy trên topic production nếu chưa xác minh chủ sở hữu dữ liệu, quyền và hệ quả với subscriber.

Nếu muốn biểu thị giá trị null theo nghiệp vụ, **không** đồng nhất ngay với xóa retained. Một payload JSON `{"value":null}` có chiều dài khác 0 và sẽ được broker giữ nếu RETAIN=true.

### 7.3. Cờ RETAIN trên bản tin nhận được

Với MQTT 3.1.1, khi broker gửi **retained snapshot do subscription mới**, subscriber có thể thấy retained flag. Một publication live mà broker chuyển cho subscriber hiện đang đăng ký có thể được gửi với flag theo quy tắc protocol khác; không chỉ nhìn payload giống nhau rồi đoán message là mới.

Spring Integration MQTT inbound converter có thể đưa thông tin này vào received metadata headers. Hằng header và hành vi mapping cần được kiểm tra đúng phiên bản thư viện đang dùng (ví dụ các hằng nhóm `MqttHeaders.RECEIVED_*`). Khi ứng dụng phải phân biệt snapshot và event mới, test với broker thật và lưu timestamp/event ID trong payload.

## 8. Clean session trong MQTT 3.1.1

Khi một MQTT 3.1.1 client CONNECT, cờ **Clean Session** cho biết broker/client có bắt đầu bằng session mới hay có thể duy trì session đã tồn tại.

### 8.1. cleanSession=true

- Client yêu cầu bắt đầu session sạch, không phục hồi trạng thái session cũ theo cách persistent session.
- Broker không duy trì trạng thái subscription/session đó sau khi client ngắt kết nối theo quy định của clean session.
- Khi client kết nối lại, ứng dụng thường **phải subscribe lại** topic cần nhận.
- Nếu subscriber offline, những publication phát trong thời gian đó **không được tích lũy chỉ nhờ subscription cũ** của một clean session.
- Sau khi subscribe lại, broker có thể gửi retained snapshot mới nhất nếu có, nhưng không phải toàn bộ lịch sử message offline.

Phù hợp với ứng dụng chỉ cần dữ liệu live, có khả năng mất mẫu và có logic khởi tạo subscribe/reconnect rõ ràng.

### 8.2. cleanSession=false

- Client yêu cầu dùng một **persistent session** gắn với Client ID.
- Broker có thể duy trì subscription và các message/in-flight state theo quy định MQTT và giới hạn tài nguyên.
- Nếu subscriber đã subscribe QoS 1/2 rồi offline, broker có thể lưu các message thuộc subscription đó để giao khi client **kết nối lại cùng Client ID**.
- Persistent session cần kết hợp chính sách QoS, broker storage/quota, session lifecycle và Client ID ổn định.
- Nó **không** tự bền vững hóa `QueueChannel` trong Spring, transaction của database, hoặc biến một telemetry QoS 0 thành message được lưu đầy đủ lúc offline.

**Quan trọng:** chỉ đặt `cleanSession=false` trong options mà chưa từng subscribe thành công không tạo ra subscription cần thiết. Session state phụ thuộc quá trình CONNECT/SUBSCRIBE thực tế.

### 8.3. So sánh trực tiếp

| Tiêu chí | `cleanSession=true` | `cleanSession=false` |
| --- | --- | --- |
| Trạng thái cũ khi CONNECT | Bắt đầu session sạch. | Có thể khôi phục session đã lưu cho cùng Client ID. |
| Subscription sau offline | Không được giữ cho client theo clean session. | Có thể được broker duy trì. |
| Offline message QoS 1/2 | Không có bảo đảm tích lũy từ session cũ. | Có thể được lưu/giao theo MQTT và chính sách broker nếu subscription hợp lệ. |
| Client ID khi restart | Có thể đổi nếu không yêu cầu session cũ. | Thường phải **ổn định** để phục hồi session. |
| Retained snapshot khi subscribe mới | Có thể nhận. | Cũng có thể nhận khi subscription mới được tạo; không tự suy luận mọi reconnect đều replay retained. |
| Cần thiết kế idempotency? | **Có** khi nguồn/retry có thể phát trùng. | **Có**, đặc biệt với QoS 1/2 và redelivery. |
| Đảm bảo exactly-once database? | Không. | Không. |

### 8.4. Clean session không phải “clean history”

Cờ clean session không xóa retained message của toàn broker. Retained message là trạng thái theo **topic tại broker**, không phải chỉ là dữ liệu private của client session. Một subscriber mới cleanSession=true vẫn có thể nhận retained snapshot có từ trước.

Ngược lại, `cleanSession=false` không phải cấu hình “giữ mọi message trên mọi topic”. Broker chỉ lưu những gì thuộc subscription/session và policy được thiết kế, trong khả năng lưu trữ tương ứng.

## 9. Bốn tình huống kết hợp QoS, retained và clean session

### Tình huống A: telemetry live, chấp nhận mất mẫu

~~~text
Publisher: qos=0, retain=false
Subscriber: subscribe qos=0, cleanSession=true
Mục tiêu: dữ liệu hiện tại, mất một số mẫu vẫn chấp nhận được.
~~~

Đơn giản và nhẹ; nếu subscriber offline, không kỳ vọng replay các mẫu đã bỏ lỡ.

### Tình huống B: snapshot trạng thái mới nhất

~~~text
Publisher: qos=1, retain=true
Subscriber: subscribe qos=1, cleanSession=true
Mục tiêu: subscriber mới nhận snapshot trạng thái gần nhất.
~~~

Khi subscriber kết nối lại và đăng ký mới, nó có thể nhận retained snapshot ngay. Nhưng nếu trạng thái `ON` rồi `OFF` trong lúc offline, subscriber **không nhận đầy đủ cả hai sự kiện**, chỉ có state snapshot cuối nếu publisher duy trì retained đúng cách.

### Tình huống C: cần nhận event offline

~~~text
Publisher: qos=1, retain=false
Subscriber: subscribe qos=1, cleanSession=false
Client ID: cố định qua restart
Mục tiêu: broker lưu một số event khi client tạm offline.
~~~

Yêu cầu subscription được tạo thành công trước khi offline, broker hỗ trợ session storage và không vượt quota/retention. Khi reconnect, client có thể nhận backlog đã lưu. Consumer phải xử lý duplicate, lag và order.

### Tình huống D: command một lần có ACK nghiệp vụ

~~~text
Publisher: qos=1, retain=false
Subscriber: subscribe qos=1, cleanSession=false hoặc theo SLA thiết bị
Payload: {"commandId":"cmd-1001","action":"TURN_ON"}
Mục tiêu: delivery tốt hơn và xác nhận thiết bị đã thực thi.
~~~

Không dùng retained command trừ khi **thực sự là desired-state command** được thiết kế idempotent và có version/expiry. Cần luồng ACK riêng theo `commandId`, timeout và idempotency ở thiết bị; MQTT QoS chỉ là một phần.

## 10. Quan hệ retained và persistent session khi reconnect

Đây là một điểm dễ nhầm cần tách riêng:

~~~mermaid
flowchart TD
    START["Subscriber kết nối lại"]
    SESSION{"Có persistent session cũ?"}
    EXIST["Khôi phục subscription / in-flight state<br/>theo broker"]
    NEW["Tạo subscription mới"]
    RET{"Broker có retained snapshot<br/>cho topic filter?"}
    BACKLOG["Giao các message offline thuộc session<br/>nếu còn và hợp lệ"]
    SNAP["Giao retained snapshot theo quy tắc subscribe"]
    LIVE["Nhận publication live"]
    START --> SESSION
    SESSION -->|"Có"| EXIST --> BACKLOG --> LIVE
    SESSION -->|"Không hoặc clean session"| NEW --> RET
    RET -->|"Có"| SNAP --> LIVE
    RET -->|"Không"| LIVE
~~~

Sơ đồ thể hiện **ý tưởng chính**, không phải cam kết cố định về thứ tự callback của mọi client/broker. Khi adapter tự subscribe lại trong lúc đã có persistent session, broker có thể xử lý như một SUBSCRIBE mới và retained behavior tùy quy tắc giao thức/broker. Phải kiểm tra thực tế.

| Nếu cần... | Cơ chế chính | Không nên làm |
| --- | --- | --- |
| Chỉ giá trị hiện tại | Retained snapshot mới nhất. | Dùng retained thay event log lịch sử. |
| Nhận các event bỏ lỡ khi client offline | Persistent session + subscription QoS 1/2 + broker storage. | Chỉ bật RETAIN=true rồi cho rằng nhận đủ mọi event. |
| Replay đầy đủ sau mất DB nhiều giờ/ngày | Kho sự kiện/outbox/broker phù hợp yêu cầu, checkpoint. | Chỉ dựa vào clean session hay RAM queue. |
| Tránh xử lý command trùng | Event/command ID, unique constraint, idempotent handler. | Chỉ tăng QoS lên 2. |
| Đảm bảo thiết bị hoàn tất lệnh | ACK nghiệp vụ/correlation và timeout. | Chỉ dựa vào PUBACK MQTT. |

## 11. Cấu hình Spring Integration và Eclipse Paho

Với Spring Boot (Java 17+) và Spring Integration MQTT dựa trên Paho v3, dependency Maven cơ bản:

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

Không tự đặt version xung đột nếu đã dùng dependency management/BOM tương thích của Spring Boot. Các class thường dùng:

~~~java
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
~~~

Trong ứng dụng thực, URL broker, credentials, TLS/ACL và Client ID phải lấy từ cấu hình môi trường, không hardcode secret.

### 11.1. Client factory chọn clean session

~~~java
@Bean
MqttPahoClientFactory subscriberFactory() {
    var options = new MqttConnectOptions();
    options.setServerURIs(new String[] {"tcp://localhost:1883"});
    options.setConnectionTimeout(10);
    options.setKeepAliveInterval(30);
    options.setCleanSession(false); // Subscriber cần persistent session

    var factory = new DefaultMqttPahoClientFactory();
    factory.setConnectionOptions(options);
    return factory;
}
~~~

`setCleanSession(false)` là cấu hình **MQTT 3.1.1 connection/session**. Nó không phải `setRetained(false)` của outbound message và không chọn subscription QoS. Nếu một publisher khác dùng cleanSession=true, có thể tạo **factory bean thứ hai** với options riêng thay vì chia sẻ một chính sách không phù hợp cho cả hai chiều.

### 11.2. Inbound adapter chọn QoS subscription

~~~java
@Bean
MqttPahoMessageDrivenChannelAdapter mqttInboundAdapter(
        @Qualifier("subscriberFactory") MqttPahoClientFactory factory,
        @Qualifier("mqtt.telemetry.in") MessageChannel output,
        @Value("${app.mqtt.subscriber-id}") String clientId) {

    var adapter = new MqttPahoMessageDrivenChannelAdapter(
            clientId, factory, "sensors/+/temperature");
    adapter.setQos(1);
    adapter.setRecoveryInterval(10000);
    adapter.setConverter(new DefaultPahoMessageConverter());
    adapter.setOutputChannel(output);
    return adapter;
}
~~~

Đây là inbound **message-driven**: broker giao MQTT PUBLISH qua callback của client, adapter chuyển thành Spring message rồi gửi vào `mqtt.telemetry.in`. **Không có `@Poller`** đọc broker. Nếu phía sau là `QueueChannel` thì consumer của queue mới cần poller ở chặng nội bộ.

### 11.3. Outbound handler chọn default QoS và retained

~~~java
@Bean(name = "mqttPublisher")
MqttPahoMessageHandler mqttPublisher(
        @Qualifier("publisherFactory") MqttPahoClientFactory factory,
        @Value("${app.mqtt.publisher-id}") String clientId) {

    var handler = new MqttPahoMessageHandler(clientId, factory);
    handler.setDefaultTopic("devices/default/state");
    handler.setDefaultQos(1);
    handler.setDefaultRetained(false);
    handler.setConverter(new DefaultPahoMessageConverter());
    handler.setAsync(false);
    handler.setCompletionTimeout(5000);
    return handler;
}
~~~

`setDefaultQos(1)` và `setDefaultRetained(false)` là **giá trị mặc định của publication** khi message không có override theo hợp đồng converter. Một publication cụ thể có thể chỉ định `MqttHeaders.QOS` và `MqttHeaders.RETAINED`. Đừng dùng default retained=true cho mọi message nếu cùng handler gửi cả state snapshot và command một lần.

Cả hai đoạn trên chỉ minh họa **cấu hình endpoint**; ví dụ hoàn chỉnh với factory, channel, flow và publisher nằm ở mục 12.

## 12. Ví dụ end-to-end trong Spring Boot: STATE, COMMAND, TELEMETRY

Mục tiêu: xây một ứng dụng có outbound flow gửi ba loại message và inbound adapter subscribe telemetry. Cấu hình:

- **STATE:** QoS 1, retained=true.
- **COMMAND:** QoS 1, retained=false.
- **TELEMETRY:** QoS 0, retained=false.
- **Subscriber telemetry:** subscribe QoS 1, cleanSession=false với Client ID ổn định.
- **Publisher:** cleanSession=true với Client ID khác subscriber.

Ứng dụng có thể chạy với broker test `tcp://localhost:1883`; nó **không khởi tạo broker**. Đây là demo về semantics, chưa có transactional outbox hay persistent store cho dữ liệu production.

### 12.1. Cấu trúc dự án

~~~text
src/main/java/demo/mqttsemantics/
    MqttSemanticsApplication.java
    MqttConnectionConfiguration.java
    MqttEndpointConfiguration.java
    MqttEvent.java
    MqttPublishPolicy.java
    MqttEventPublisher.java

src/main/resources/
    application.properties
~~~

Mã sử dụng Java 17+, các class thuộc package `demo.mqttsemantics`. Với các snippet, import đủ được thể hiện ở từng file; class không `public` có thể đổi sang package-private tùy bố trí tệp.

### 12.2. application.properties

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}

# Subscriber persistent session cần Client ID ổn định qua restart,
# đồng thời phải duy nhất giữa các instance đang online.
app.mqtt.subscriber-id=${MQTT_SUBSCRIBER_ID:telemetry-subscriber-local-1}
app.mqtt.publisher-id=${MQTT_PUBLISHER_ID:events-publisher-local-1}
~~~

Local demo không cấu hình TLS/credential. Nếu kết nối broker production, thay URL bằng kết nối TLS, cấu hình chứng chỉ tin cậy/credentials từ secrets và giới hạn publish/subscribe bằng broker ACL. Client ID mặc định ở đây **không an toàn khi chạy nhiều replica cùng lúc**.

### 12.3. Spring Boot application

~~~java
package demo.mqttsemantics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttSemanticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttSemanticsApplication.class, args);
    }
}
~~~

### 12.4. Hai factory: session policy riêng cho subscriber và publisher

~~~java
package demo.mqttsemantics;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;

@Configuration
class MqttConnectionConfiguration {

    @Bean(name = "subscriberFactory")
    MqttPahoClientFactory subscriberFactory(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {
        return newFactory(brokerUrl, false);
    }

    @Bean(name = "publisherFactory")
    MqttPahoClientFactory publisherFactory(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {
        return newFactory(brokerUrl, true);
    }

    private MqttPahoClientFactory newFactory(
            String brokerUrl, boolean cleanSession) {
        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(cleanSession);

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }
}
~~~

Hai factory không tự tạo publisher/subscriber cho đến khi adapter dùng chúng. Hai factory cùng kiểu `MqttPahoClientFactory` nên lúc inject dùng `@Qualifier` để tránh mơ hồ.

### 12.5. DTO và policy QoS/retained tại ranh giới nghiệp vụ

~~~java
package demo.mqttsemantics;

record MqttEvent(
        String eventId,
        String deviceId,
        String kind,
        String json) {
}
~~~

~~~java
package demo.mqttsemantics;

import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class MqttPublishPolicy {

    private MqttPublishPolicy() {}

    static Message<String> toMessage(MqttEvent event) {
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Thiếu eventId");
        }
        if (event.deviceId() == null
                || !event.deviceId().matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("deviceId không hợp lệ");
        }
        if (event.kind() == null
                || event.json() == null
                || event.json().isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu loại event hoặc JSON payload");
        }

        String topic;
        int qos;
        boolean retained;

        switch (event.kind()) {
            case "STATE" -> {
                topic = "devices/" + event.deviceId() + "/state";
                qos = 1;
                retained = true;
            }
            case "COMMAND" -> {
                topic = "devices/" + event.deviceId() + "/commands";
                qos = 1;
                retained = false;
            }
            case "TELEMETRY" -> {
                topic = "sensors/" + event.deviceId() + "/temperature";
                qos = 0;
                retained = false;
            }
            default -> throw new IllegalArgumentException(
                    "Loại event không hỗ trợ: " + event.kind());
        }

        return MessageBuilder.withPayload(event.json())
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, qos)
                .setHeader(MqttHeaders.RETAINED, retained)
                .setHeader("eventId", event.eventId())
                .build();
    }
}
~~~

**Giải thích contract:**

1. Message nội bộ chứa JSON text; demo giả định JSON đã được tạo từ DTO đáng tin cậy. Trong production cần serialize/validate JSON thực tế, và `eventId` phải tồn tại **trong payload** nếu MQTT subscriber cần đọc.
2. `deviceId` được giới hạn ký tự, không cho phép `/`, `+` hay `#` làm thay đổi cấu trúc topic.
3. Policy chọn QoS/retained **theo loại dữ liệu**, tránh một default cho tất cả event.
4. `MqttHeaders.TOPIC` là topic MQTT dùng cho outbound, không phải tên `MessageChannel`.
5. `eventId` chỉ là header Spring nội bộ trong snippet; với MQTT v3, header ứng dụng không mặc nhiên trở thành metadata MQTT ở broker.

Retained state có thể giúp subscriber mới lấy snapshot, nhưng cũng tạo rủi ro state cũ nếu luồng publish state không nhất quán. Với command, `retained=false` tránh subscriber mới nhận lại lệnh một lần.

### 12.6. Cấu hình channel, inbound adapter và outbound handler

~~~java
package demo.mqttsemantics;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
class MqttEndpointConfiguration {

    @Bean(name = "mqtt.publish.requests")
    MessageChannel publishRequests() {
        return new DirectChannel();
    }

    @Bean(name = "mqtt.telemetry.in")
    MessageChannel telemetryInput() {
        return new DirectChannel();
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter telemetryAdapter(
            @Qualifier("subscriberFactory") MqttPahoClientFactory factory,
            @Qualifier("mqtt.telemetry.in") MessageChannel channel,
            @Value("${app.mqtt.subscriber-id}") String clientId) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, factory, "sensors/+/temperature");
        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(channel);
        return adapter;
    }

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler publisher(
            @Qualifier("publisherFactory") MqttPahoClientFactory factory,
            @Value("${app.mqtt.publisher-id}") String clientId) {

        var handler = new MqttPahoMessageHandler(clientId, factory);
        handler.setDefaultTopic("demo/unrouted");
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setConverter(new DefaultPahoMessageConverter());
        handler.setAsync(false);
        handler.setCompletionTimeout(5000);
        return handler;
    }

    @Bean
    IntegrationFlow outboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {
        return IntegrationFlow.from("mqtt.publish.requests")
                .handle(publisher)
                .get();
    }

    @Bean
    IntegrationFlow inboundTelemetryFlow() {
        return IntegrationFlow.from("mqtt.telemetry.in")
                .handle(String.class, (payload, headers) -> {
                    System.out.println(
                            "MQTT topic="
                            + headers.get(MqttHeaders.RECEIVED_TOPIC)
                            + " payload length=" + payload.length());
                    return null;
                })
                .get();
    }
}
~~~

Ở đây:

- `subscriberFactory` dùng `cleanSession=false`, trong khi `publisherFactory` dùng `cleanSession=true`.
- Inbound adapter subscribe QoS 1, nhưng khi publisher gửi telemetry ở QoS 0 thì chặng broker → subscriber vẫn có thể dùng QoS 0.
- Outbound handler nhận QoS/retained **theo từng message** qua `MqttHeaders.QOS` và `MqttHeaders.RETAINED`; mặc định chỉ là fallback.
- `inboundTelemetryFlow` xử lý theo callback từ MQTT, **không có `@Poller`**.
- `outboundFlow` dùng `DirectChannel`; với publish sync, thread gửi có thể bị chặn chờ completion.
- Topic mặc định `demo/unrouted` chỉ để thấy hành vi fallback trong demo; với command production, thiếu `MqttHeaders.TOPIC` nên bị từ chối trước handler thay vì gửi đến topic fallback.

### 12.7. Service phát message

~~~java
package demo.mqttsemantics;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.stereotype.Service;

@Service
class MqttEventPublisher {

    private final MessageChannel channel;

    MqttEventPublisher(
            @Qualifier("mqtt.publish.requests") MessageChannel channel) {
        this.channel = channel;
    }

    boolean publish(MqttEvent event) {
        return channel.send(MqttPublishPolicy.toMessage(event));
    }
}
~~~

Caller có thể gửi snapshot:

~~~java
publisher.publish(new MqttEvent(
        "evt-state-1001",
        "device-17",
        "STATE",
        "{\"eventId\":\"evt-state-1001\",\"state\":\"ON\"}"));
~~~

hoặc command:

~~~java
publisher.publish(new MqttEvent(
        "cmd-1001",
        "device-17",
        "COMMAND",
        "{\"commandId\":\"cmd-1001\",\"action\":\"TURN_OFF\"}"));
~~~

Bản tin STATE sẽ publish tới `devices/device-17/state` với QoS 1 và retained=true; COMMAND sẽ publish tới `devices/device-17/commands` với QoS 1 và retained=false. Cần broker đã chạy và cấu hình publish/subscribe permission phù hợp.

**Không coi boolean trả về từ `publish(...)` là business ACK.** Nó là kết quả gửi message tới Spring channel, không phải xác nhận thiết bị đã thực thi command.

## 13. Kiểm thử chính sách QoS/retained không cần MQTT broker

Tách MQTT transport khỏi flow giúp unit/integration test nhanh và ổn định. Với `MqttPublishPolicy` độc lập, có thể kiểm thử topic, QoS và retained trực tiếp. Để xác nhận Spring wiring, tạo **fake `MessageHandler`** thay cho Paho publisher.

Thêm test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Để test không cần broker, dùng một Spring context chỉ gồm channel + outbound flow cùng fake publisher; **không nạp `MqttConnectionConfiguration` hay inbound adapter** của demo.

~~~java
package demo.mqttsemantics;

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
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        MqttOutboundTestConfiguration.class,
        RecordingMqttPublisherConfiguration.class
})
class MqttPublishPolicyTest {

    @Autowired
    @Qualifier("mqtt.publish.requests")
    MessageChannel input;

    @Autowired
    RecordingMqttPublisher recorded;

    @BeforeEach
    void reset() {
        recorded.clear();
    }

    @Test
    void stateIsRetainedWithQosOne() {
        MqttEvent event = new MqttEvent(
                "evt-test-state", "device-17", "STATE",
                "{\"eventId\":\"evt-test-state\",\"state\":\"ON\"}");

        assertTrue(input.send(MqttPublishPolicy.toMessage(event)));
        assertEquals(List.of(new SentMqtt(
                "devices/device-17/state", 1, true, event.json())),
                recorded.snapshot());
    }

    @Test
    void commandIsNotRetained() {
        MqttEvent event = new MqttEvent(
                "cmd-test-1", "device-17", "COMMAND",
                "{\"commandId\":\"cmd-test-1\",\"action\":\"TURN_OFF\"}");

        assertTrue(input.send(MqttPublishPolicy.toMessage(event)));
        assertEquals(List.of(new SentMqtt(
                "devices/device-17/commands", 1, false, event.json())),
                recorded.snapshot());
    }

    @Test
    void telemetryUsesQosZeroWithoutRetained() {
        MqttEvent event = new MqttEvent(
                "evt-temp-1", "device-17", "TELEMETRY",
                "{\"eventId\":\"evt-temp-1\",\"celsius\":26.5}");

        assertTrue(input.send(MqttPublishPolicy.toMessage(event)));
        assertEquals(List.of(new SentMqtt(
                "sensors/device-17/temperature", 0, false,
                event.json())),
                recorded.snapshot());
    }
}

record SentMqtt(String topic, int qos, boolean retained,
                String payload) {}

class RecordingMqttPublisher implements MessageHandler {

    private final List<SentMqtt> messages =
            new CopyOnWriteArrayList<>();

    @Override
    public void handleMessage(Message<?> message) {
        messages.add(new SentMqtt(
                (String) message.getHeaders().get(MqttHeaders.TOPIC),
                (Integer) message.getHeaders().get(MqttHeaders.QOS),
                (Boolean) message.getHeaders().get(MqttHeaders.RETAINED),
                (String) message.getPayload()));
    }

    List<SentMqtt> snapshot() {
        return List.copyOf(messages);
    }

    void clear() {
        messages.clear();
    }
}

@Configuration
@EnableIntegration
class MqttOutboundTestConfiguration {

    @Bean(name = "mqtt.publish.requests")
    MessageChannel publishRequests() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow outboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {
        return IntegrationFlow.from("mqtt.publish.requests")
                .handle(publisher)
                .get();
    }
}

@Configuration
class RecordingMqttPublisherConfiguration {

    @Bean(name = "mqttPublisher")
    RecordingMqttPublisher recordingPublisher() {
        return new RecordingMqttPublisher();
    }
}
~~~

Test kiểm tra:

1. Topic tạo theo loại event và device ID.
2. State dùng QoS 1, retained=true.
3. Command dùng QoS 1, retained=false.
4. Telemetry dùng QoS 0, retained=false.
5. Message thực sự đi qua Spring channel và flow vào handler bean.

**Giới hạn:** fake handler không sử dụng Paho, không kết nối broker và không kiểm tra session/offline delivery, PUBACK hay retained storage. Phần đó cần test có broker.

### 13.1. Các unit test bổ sung nên viết

- Thiếu `eventId`, `deviceId`, `kind` hoặc JSON: policy phải reject trước khi publish.
- `deviceId` chứa `/`, `+` hoặc `#`: không tạo topic.
- Một command có JSON không chứa commandId phù hợp: validation schema cần reject ở tầng ứng dụng khi đã parse JSON.
- Một callback MQ có RETAIN=true nhưng handler giả xử lý như event mới: kiểm tra quy tắc snapshot vs event.
- Một event retry sau khi routing policy đổi: kiểm tra `eventId` và route decision cố định theo hợp đồng.

## 14. Kiểm thử QoS, retained và session với broker MQTT thật

Để kiểm chứng đặc tính giao thức, cần broker test. Ví dụ sau dùng `mosquitto_pub`/`mosquitto_sub` và broker local tại `localhost:1883`. Đây là bài thử độc lập, không phải lệnh cần chạy trên broker production.

### 14.1. Retained snapshot tới subscriber mới

**Terminal A – publish retained state:**

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' \
  -q 1 -r \
  -m '{"eventId":"evt-state-1","state":"ON"}'
~~~

**Terminal B – subscribe sau khi publish:**

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -t 'devices/+/state' -q 1 -v
~~~

Subscriber mới có thể thấy bản retained state `ON` dù publication được gửi **trước khi** nó subscribe.

**Thử thay thế retained:**

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' \
  -q 1 -r \
  -m '{"eventId":"evt-state-2","state":"OFF"}'
~~~

Khi subscriber mới subscribe, snapshot có thể là `OFF`. Việc này minh họa retained là giá trị mới nhất, không phải lịch sử `ON` và `OFF`.

**Xóa retained khi đã được phép:**

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' \
  -q 1 -r -n
~~~

Sau khi xóa, subscriber mới không nên được cấp snapshot retained cũ cho topic đó. Chỉ dùng trên broker/topic thử nghiệm do bạn kiểm soát.

### 14.2. Test persistent session khi subscriber offline

Để test cần broker cho phép session persistence theo cấu hình. **Bước 1:** mở subscriber với Client ID cố định, clean session disabled (theo Mosquitto CLI):

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i durable-temperature-1 -c \
  -q 1 -t 'sensors/+/temperature' -v
~~~

**Bước 2:** dừng subscriber bằng Ctrl+C sau khi subscription đã được tạo thành công.

**Bước 3:** trong lúc subscriber offline, publish một message QoS 1 không retained:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'sensors/device-17/temperature' \
  -q 1 \
  -m '{"eventId":"evt-offline-1","celsius":27.5}'
~~~

**Bước 4:** chạy lại **cùng** lệnh subscriber với Client ID `durable-temperature-1`, `-c` và cùng topic/QoS. Nếu broker đã giữ session/subscription và bản tin theo policy, subscriber có thể nhận message offline.

Để so sánh, chạy lại kịch bản với một Client ID mới hoặc clean session mặc định; subscriber mới sẽ không có session backlog trước đó, ngoại trừ retained snapshot nếu đã được tạo trong bài thử khác.

**Kết luận đúng:** việc nhận offline message phụ thuộc session thực tế, subscription QoS, publish QoS, broker policy/storage và reconnect cùng Client ID. Không chỉ dựa vào lệnh `-c` để suy ra mọi message sẽ luôn được lưu vô hạn.

### 14.3. Test duplicate, qos downgrade và restart

| Kịch bản | Cách thực hiện | Kết luận mong muốn |
| --- | --- | --- |
| Publisher QoS 1, subscriber QoS 0 | Publish `-q 1`, subscribe `-q 0`. | Chặng tới subscriber có thể là QoS 0; publisher QoS không ép subscription QoS. |
| QoS 1 gặp mất mạng | Mô phỏng disconnect/ACK thất lạc, reconnect. | Có thể redelivery; business handler cần chống duplicate. |
| QoS 2 | Publish/subscribe QoS 2. | Đo overhead và chỉ suy luận exactly-once ở tầng MQTT protocol. |
| Retained STATE | Publish `-r` rồi subscribe mới. | Subscriber mới nhận snapshot đã lưu. |
| Non-retained COMMAND | Publish command không `-r`, subscribe sau. | Subscriber mới không tự nhận command đã qua như retained snapshot. |
| Clean session true | Subscriber offline khi publish. | Không có backlog do persistent session cũ. |
| Clean session false | Subscriber cùng ID restart, QoS 1/2. | Có thể khôi phục subscription/backlog nếu broker hỗ trợ. |
| Client ID trùng | Hai subscriber active cùng ID. | Có nguy cơ ngắt kết nối lẫn nhau; không dùng như competing consumers. |
| Broker restart | Khởi động lại broker trong bài test. | Kiểm tra session/retained storage thật, không giả định luôn bền. |

**Lưu ý môi trường:** những kịch bản có restart/reconnect/ACL cần broker do người thử nghiệm kiểm soát. Khi broker yêu cầu TLS/authentication, sử dụng chứng chỉ và credentials dành riêng cho test; không hạ bảo mật broker production để chạy demo.

## 15. Xử lý lỗi, retry và idempotency

Ba thiết lập MQTT không đủ để bảo đảm toàn bộ một luồng Spring Integration hoàn tất. Một flow có thể thất bại ở nhiều tầng:

~~~mermaid
flowchart TD
    SRC["Publisher / Adapter source"]
    MQTT["MQTT transport<br/>QoS, retained, session"]
    B[("MQTT broker")]
    SUB["Spring MQTT inbound adapter"]
    CH["MessageChannel"]
    H["Business handler / DB / HTTP"]
    OK["Ghi nhận thành công theo nghiệp vụ"]
    ERR["Retry / error channel / DLQ / quarantine"]
    SRC --> MQTT --> B --> SUB --> CH --> H --> OK
    MQTT -. "disconnect / timeout" .-> ERR
    SUB -. "converter / dispatch" .-> ERR
    H -. "DB/HTTP lỗi" .-> ERR
~~~

| Lỗi | QoS/retained/clean session có giải quyết? | Cần thêm gì? |
| --- | --- | --- |
| TCP disconnect khi publish QoS 0 | Không có ACK/redelivery QoS 1/2. | Quyết định có chấp nhận mất dữ liệu hay cần outbox/retry. |
| MQTT PUBACK chậm/mất | QoS 1/2 có cơ chế protocol, vẫn có duplicate/uncertain outcome. | Event ID/idempotency, backoff và đối soát. |
| Subscriber offline | Persistent session có thể lưu QoS 1/2; retained cung cấp snapshot cuối. | Chính sách broker/session TTL, backlog và monitoring. |
| JSON sai schema | Không. | Parse/validate, reject/quarantine, không retry vô hạn lỗi dữ liệu. |
| DB ghi thất bại sau MQTT delivery | Không tự rollback MQTT ACK hay broker state. | Transaction riêng, error flow, replay nguồn và idempotency. |
| Publisher phát lặp cùng business command | Không; hai publish khác nhau có thể cùng ID nghiệp vụ. | Command ID và chống trùng ở subscriber. |
| Retained command cũ kích hoạt thiết bị mới | RETAIN tạo nguy cơ này. | retained=false, expiry/nonce/version và ACK nghiệp vụ. |
| Queue trong Spring mất sau restart | Clean session không bảo vệ queue RAM. | Persistent message store/broker/outbox. |

### 15.1. Vì sao phải phân biệt delivery và business acknowledgement?

~~~mermaid
sequenceDiagram
    participant APP as Publisher app
    participant B as MQTT broker
    participant DEVICE as Thiết bị / Subscriber
    participant DB as Business state
    APP->>B: PUBLISH(cmd-1001, QoS=1)
    B-->>APP: PUBACK (MQTT delivery)
    B->>DEVICE: PUBLISH(cmd-1001)
    DEVICE->>DB: Thực hiện / lưu trạng thái
    DEVICE-->>APP: ACK nghiệp vụ riêng (topic ACK)
~~~

PUBACK chỉ phản ánh một chặng giao thức, không phải chứng minh đoạn `DEVICE → DB` thành công. Nếu business ACK chưa đến, caller không thể đơn giản kết luận command chưa chạy; nó cũng có thể đã chạy nhưng ACK thất lạc. Thiết kế nên lưu `commandId`, trạng thái, timeout, retry có kiểm soát và khả năng tra cứu trạng thái tại đích.

### 15.2. Transactional outbox và replay

Một mẫu đáng cân nhắc khi command/event rất quan trọng:

1. Ghi business record và outbox record cùng một transaction database.
2. Outbox chứa `eventId`/`commandId`, payload, topic, QoS, retained và trạng thái gửi.
3. Worker đọc outbox rồi publish MQTT theo retry/backoff.
4. Đánh dấu publication theo mức xác nhận MQTT thích hợp, nhưng **không đánh dấu thiết bị đã xử lý** trước ACK nghiệp vụ.
5. Subscriber dùng idempotency key/unique constraint để không lặp side effect khi broker/app gửi trùng.
6. Khi replay, giữ nguyên `eventId` và chính sách topic/retained đã chọn, hoặc lưu version rule nếu routing có thể đổi.

Nếu worker crash sau publish nhưng trước khi cập nhật outbox, event có thể được gửi lại. Đó là lý do idempotency vẫn cần thiết ngay cả khi dùng QoS 2.

## 16. Bảo mật, vòng đời và scale nhiều instance

### 16.1. Client ID và session qua replica

Với `cleanSession=false`, Client ID là chìa khóa để phục hồi session. Nếu mỗi restart tạo random Client ID mới, subscriber sẽ không tái sử dụng session cũ, đồng thời tạo thêm session tồn tại tại broker theo chính sách dọn dẹp. Nhưng nếu nhiều replica đồng thời dùng cùng một Client ID, broker có thể đẩy kết nối cũ ra.

Cần lựa chọn:

- **Một consumer logic cố định:** Client ID ổn định, chỉ một instance hoạt động cùng ID tại một thời điểm.
- **Nhiều subscriber độc lập:** Client ID khác nhau, mỗi subscriber có session và subscription riêng.
- **Chia tải một stream:** dùng shared subscription khi broker/giao thức hỗ trợ hoặc kiến trúc queue, không chia tải bằng cách cho nhiều process cùng Client ID.
- **Cấu hình HA:** kiểm tra cluster có duy trì session/retained khi failover hay không; nhiều broker URI không đồng nghĩa broker độc lập chia sẻ state.

### 16.2. Retained data và quyền truy cập

Một retained snapshot có thể được giao cho subscriber mới vào **thời điểm sau publication ban đầu**. Do đó:

- Không retained secrets/token, command có quyền lực cao hoặc dữ liệu nhạy cảm không phù hợp.
- Giới hạn topic ACL để người không có quyền không subscribe được state.
- Xác thực device/tenant ID trong topic/payload.
- Quy định retention/clear retained khi thiết bị bị xóa, chuyển tenant hoặc đổi quyền.
- Theo dõi retained topic cardinality và quota của broker.

### 16.3. TLS, connection và callback thread

`MqttConnectOptions` nên dùng TLS và credential/ACL thích hợp trong production. Khi inbound adapter phát message vào `DirectChannel`, downstream blocking có thể kéo dài thời gian xử lý callback; nếu dùng `QueueChannel` hoặc `ExecutorChannel` để cách ly, phải thiết kế capacity, error path, persistence và shutdown.

Không coi clean session=false là lời giải backpressure. Broker backlog và Spring queue backlog thuộc hai lớp khác nhau. Monitor message lag, in-flight count, reconnect, CPU/thread pool, broker quota và database latency.

## 17. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Subscriber mới nhận message cũ dù mới subscribe. | Broker có retained snapshot. | Kiểm tra received retained metadata, event timestamp và retained policy. |
| Retained state hiển thị ON nhưng thiết bị vừa gửi OFF. | Publication OFF dùng RETAIN=false, không thay thế snapshot. | Publish state mới với retained=true hoặc xóa snapshot đúng cách. |
| Subscriber offline không nhận dữ liệu khi quay lại. | cleanSession=true, QoS 0, Client ID thay đổi, chưa từng subscribe hoặc broker không giữ session. | Kiểm tra cả Client ID, clean session, QoS ở hai chặng, storage và subscription. |
| Hai replica reconnect liên tục. | Cùng MQTT Client ID. | Cấp ID duy nhất hoặc một active subscriber logic. |
| QoS 1 làm database có bản ghi trùng. | Redelivery/retry, thiếu idempotency. | Unique constraint theo event ID và kiểm tra duplicate. |
| QoS 2 vẫn tạo hai đơn hàng. | Publisher gửi hai publication khác nhau cùng ý nghĩa nghiệp vụ. | Dedup theo order/command ID, không chỉ QoS. |
| Thiết bị chạy lại lệnh cũ sau khi subscribe. | Command dùng RETAIN=true. | retained=false, cleanup retained sai, kiểm soát replay/expiry. |
| `setQos(1)` inbound nhưng nhận QoS 0. | Publisher đã publish QoS 0. | Kiểm tra QoS cả publisher và subscriber. |
| Clean session false nhưng mất event sau broker restart. | Broker không lưu session/message bền theo policy hoặc vượt quota. | Kiểm tra broker persistence/quota/test failover, bổ sung outbox. |
| Application restart mất queue message. | `QueueChannel` mặc định trong RAM. | Dùng persistent store/outbox; clean session không bảo vệ Spring queue. |
| MQTT ACK nhận rồi nhưng business handler chưa chạy. | MQTT delivery và business processing là hai chặng. | Thiết kế ACK nghiệp vụ, retry và quan sát downstream. |
| Topic retained bị xóa nhầm. | Publish zero-length retained tới topic production. | Áp dụng quyền riêng, audit và kiểm soát lệnh cleanup. |

## 18. Bài tập thực hành

**Tình huống:** một hệ thống IoT nhận nhiệt độ qua MQTT và gửi lệnh bật/tắt điều hòa. Yêu cầu dữ liệu nhiệt độ có thể mất ít mẫu, subscriber mới cần biết trạng thái gần nhất, còn lệnh điều hòa cần xử lý không lặp.

Thực hiện:

1. Thiết kế topic `sensors/{deviceId}/temperature`, `devices/{deviceId}/state`, `devices/{deviceId}/commands` và `devices/{deviceId}/ack`.
2. Chọn QoS, retained cho từng topic và giải thích vì sao command một lần không retained.
3. Tạo `MqttPahoClientFactory` subscriber cleanSession=false và publisher cleanSession=true.
4. Chọn Client ID ổn định cho subscriber nhưng không dùng trùng giữa các replica.
5. Đăng ký inbound adapter QoS 1 và output channel `mqtt.telemetry.in`; viết flow parse/validate JSON.
6. Đăng ký outbound handler nhận từ `mqtt.publish.requests`, tạo header `MqttHeaders.QOS`, `RETAINED`, `TOPIC` theo loại event.
7. Viết test không broker kiểm tra QoS/retained policy với STATE, COMMAND, TELEMETRY và input sai.
8. Publish retained state, subscribe mới, xác nhận nhận snapshot; publish non-retained state và giải thích vì sao snapshot trước vẫn còn.
9. Xóa retained snapshot đúng topic trong broker test, kiểm tra subscriber mới không nhận state cũ.
10. Test persistent session: subscribe Client ID cố định clean=false, offline, publish QoS 1, reconnect và kiểm tra backlog theo broker policy.
11. Test QoS publisher=1/subscriber=0 rồi nêu nhận xét về QoS chặng delivery.
12. Mô phỏng command được thiết bị thực thi nhưng ACK nghiệp vụ thất lạc; thiết kế retry với command ID không tạo tác dụng phụ thứ hai.
13. Dùng một outbox hoặc kho replay riêng cho dữ liệu bắt buộc khôi phục sau app crash.

**Tiêu chí đạt:** phân biệt được snapshot retained với offline queued messages, giải thích rõ Client ID/session, chứng minh QoS không thay transaction DB, và test phản ánh đúng ba loại trạng thái **MQTT_DELIVERED**, **BUSINESS_PROCESSED**, **BUSINESS_ACKNOWLEDGED**.

## 19. Câu hỏi tự kiểm tra

1. MQTT QoS 0, 1, 2 khác nhau về handshake và nguy cơ duplicate như thế nào?
2. QoS 2 có khiến một giao dịch database chắc chắn chỉ commit một lần không?
3. Publisher QoS 1, subscriber QoS 0: broker thường giao ở QoS mấy?
4. Retained message giữ lịch sử hay chỉ snapshot mới nhất của topic?
5. Publisher gửi RETAIN=false vào topic đã có retained: snapshot cũ có bị xóa không?
6. Xóa retained state bằng cách nào trong MQTT 3.1.1?
7. Vì sao retained command một lần có thể nguy hiểm?
8. `cleanSession=true` có làm broker quên retained message của mọi topic không?
9. Để subscriber nhận event QoS 1/2 khi offline, cần những điều kiện nào ngoài `cleanSession=false`?
10. Vì sao Client ID thay đổi sau restart làm persistent session không còn tác dụng mong đợi?
11. Hai replica cùng Client ID có tương đương với nhóm competing consumers không?
12. Cấu hình inbound `setQos(1)` khác outbound `setDefaultQos(1)` ra sao?
13. Khi Spring Integration nhận MQTT message rồi handler DB lỗi, MQTT PUBACK có tự rollback theo DB không?
14. Làm sao phân biệt retained snapshot với event mới và event gửi trùng?
15. Khi dùng `QueueChannel` trong Spring, clean session có bảo vệ các message đang nằm trong RAM không?
16. Tại sao cần business ACK qua topic riêng cho command?
17. Một publication QoS 1 có thể đến broker mà publisher vẫn thấy timeout không?
18. Khi broker failover sang node độc lập, persistent session có chắc còn nguyên không?
19. Vì sao cần lưu `eventId` vào payload MQTT v3 thay vì chỉ header Spring?
20. Trong hệ thống nhiều tenant, retained state cần những kiểm soát quyền và dọn dẹp nào?

**Gợi ý:** QoS quyết định handshake ở các chặng MQTT, retained cung cấp snapshot theo topic, clean session quyết định vòng đời session MQTT 3.1.1. Các bảo đảm này không thay thế idempotency, outbox hay ACK nghiệp vụ.

## 20. Kết luận

**QoS, retain và clean session là ba cơ chế khác nhau của MQTT**:

- **QoS 0/1/2** điều chỉnh cách publication được giao ở tầng MQTT, với các mức at-most-once, at-least-once và exactly-once protocol.
- **RETAIN** quyết định broker có giữ snapshot mới nhất trên topic để subscriber mới nhận không; retained không lưu toàn bộ event history.
- **Clean session** trong MQTT 3.1.1 quyết định session/subscription có được duy trì qua disconnect với Client ID ổn định hay không; nó không phải lựa chọn lưu dữ liệu bền vững của Spring Integration.

Trong module **SPRING_INTEGRATION_ADAPTERS**, việc dùng các cơ chế này phải gắn với inbound/outbound MQTT adapter, `MessageChannel`, flow xử lý và hợp đồng message. Cấu hình chuẩn cần lựa chọn **QoS ở cả publisher/subscriber**, **retained theo loại dữ liệu**, **Client ID/session theo lifecycle**, cùng **error handling, backpressure, idempotency và kiểm thử broker thực tế**. Chỉ khi kết hợp những phần đó và xác nhận side effect ở đích mới có thể đánh giá một hệ thống MQTT đủ tin cậy cho nghiệp vụ.

