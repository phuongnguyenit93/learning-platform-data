# Đối chiếu kiểu dữ liệu, header và xác nhận khi kết nối khác giao thức

> **Chương:** Giao thức kết nối  
> **Công nghệ:** Apache ActiveMQ Artemis; so sánh Core/JMS, AMQP 1.0, STOMP và MQTT trong hệ sinh thái ActiveMQ Classic/Artemis.  
> **Trọng tâm:** Message vẫn đến đúng nơi **không có nghĩa** payload, header và cơ chế xác nhận còn nguyên ngữ nghĩa ban đầu.

## 1. Mục tiêu và bài toán thực tế

Một dịch vụ Java dùng **Artemis JMS client** phát `OrderCreated`. Bên nhận có thể là ứng dụng Java dùng **AMQP 1.0**, một worker dùng **STOMP 1.2** hoặc một thiết bị dùng **MQTT**. Chúng có thể kết nối cùng broker Artemis, nhưng không nhất thiết dùng chung quy ước mã hóa body, tên header hay cách xác nhận message.

Sau bài học, người học có thể:

1. Phân biệt **JMS/Jakarta Messaging là API** với **Core, AMQP, OpenWire, STOMP, MQTT là giao thức trao đổi trên kết nối**.
2. Chỉ ra dữ liệu nào có thể trao đổi ổn định giữa các client và dữ liệu nào cần một **hợp đồng payload/header** riêng.
3. So sánh acknowledgment/settlement ở JMS, AMQP, STOMP và MQTT mà không nhầm xác nhận vận chuyển với hoàn tất nghiệp vụ.
4. Cấu hình các acceptor Artemis và một **anycast queue tường minh** để kiểm tra cùng một message qua các client khác giao thức.
5. Thực hiện kịch bản **Java Core/JMS producer → AMQP/JMS consumer** và **Java Core/JMS producer → STOMP manual-ACK consumer**, kiểm tra kiểu dữ liệu, định danh và redelivery.

Giả sử đơn hàng `ORD-1042` cần được xử lý đúng một lần ở cấp nghiệp vụ. Producer tạo payload JSON và metadata để quan sát:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-1042",
  "eventType": "OrderCreated",
  "orderId": "ORD-1042",
  "amount": 1500,
  "currency": "VND"
}
~~~

Một consumer phải đọc được `eventId`, diễn giải đúng `amount`, xác nhận sau khi công việc hoàn thành, đồng thời xử lý được trường hợp broker giao lại message. Nếu một client coi `amount` là số nguyên còn client khác chỉ thấy chuỗi `"1500"`, selector hoặc phép so sánh có thể cho kết quả khác nhau.

## 2. Bốn lớp cần đối chiếu trước khi nối hai hệ thống

Một message đi qua Artemis có thể được diễn giải qua bốn lớp:

~~~mermaid
flowchart LR
    A[Application A] -->|JMS API| C[Artemis Core client]
    C -->|CORE protocol| B[(Artemis broker)]
    B -->|AMQP 1.0| D[AMQP provider]
    D -->|JMS API| E[Application B]
    B -->|STOMP 1.2| F[STOMP worker]
    B -->|MQTT| G[MQTT client]
~~~

- **API ứng dụng:** `jakarta.jms.Message`, `TextMessage`, `BytesMessage`, `JMSContext.commit()`… là hợp đồng mà chương trình Java gọi.
- **Wire protocol:** Core, AMQP 1.0, OpenWire, STOMP hoặc MQTT là dữ liệu mà client thực sự gửi qua kết nối TCP/TLS/WebSocket tùy hỗ trợ.
- **Broker representation và routing:** Artemis tiếp nhận, lưu, chuyển đổi nếu cần, định tuyến vào address/queue. Việc dùng cùng tên destination chưa bảo đảm mọi client chọn cùng kiểu routing.
- **Nghiệp vụ:** ứng dụng giải mã payload, kiểm tra schema, xử lý idempotent, rồi xác nhận theo cơ chế của client.

**Không được đồng nhất “dùng JMS” với “dùng cùng giao thức”.** Artemis JMS client kết nối bằng Core; Apache Qpid JMS client có thể cung cấp **cùng giao diện Jakarta JMS** nhưng thực sự kết nối bằng **AMQP 1.0**. Hai bên cùng gọi `JMSContext.createConsumer()` không có nghĩa các frame giao thức, mapping header hay transaction xử lý giống nhau ở dưới lớp API.

### Ma trận định hướng

| Bên kết nối | Cách gọi từ ứng dụng | Payload thường thấy trên wire | Xác nhận ở cấp giao thức/client |
|---|---|---|---|
| **Artemis Core client** | Artemis Core API hoặc Artemis JMS/Jakarta client | Artemis Core message | JMS ACK/commit hoặc Core consumer ACK |
| **OpenWire client** | ActiveMQ Classic JMS client | OpenWire command/message | JMS ACK/transaction được client mã hóa theo OpenWire |
| **AMQP 1.0 client** | AMQP native hoặc Qpid JMS | AMQP message với `header/properties/application-properties/body` | Delivery state/disposition và settlement; Qpid JMS ánh xạ thành ACK/commit |
| **STOMP client** | Frame `SEND/SUBSCRIBE/MESSAGE/ACK/NACK` | Header dạng văn bản và body dạng bytes | `ack:auto`, `client` hoặc `client-individual`; `ACK/NACK` nếu manual |
| **MQTT client** | MQTT publish/subscribe API | Topic + byte payload + metadata giao thức | QoS 0/1/2, các gói PUBACK/PUBREC/PUBREL/PUBCOMP theo mức QoS |

Artemis có thể hỗ trợ nhiều giao thức, nhưng **giao thức được bật trên acceptor, phiên bản broker, thư viện client và chế độ destination** quyết định kịch bản nào hoạt động. Không suy luận rằng mọi header hoặc hành vi ACK có thể chuyển nguyên trạng qua tất cả các hàng của bảng.

## 3. Payload: thứ dễ đọc nhất cũng dễ hiểu nhầm nhất

### 3.1. Text, bytes, map và object không tương đương nhau

| Kiểu ở một JMS producer | Mục đích | Khi qua client khác giao thức |
|---|---|---|
| `TextMessage` | Chuỗi ký tự, thường chứa JSON/XML/text | Có thể hiện thành AMQP value hoặc representation có thông tin kiểu; STOMP/MQTT thấy body bytes và phải biết encoding. **Không mặc định giữ nguyên Java message class.** |
| `BytesMessage` | Dữ liệu nhị phân | Phù hợp để chuyển payload bytes, nhưng bên nhận phải biết encoding, schema và kích thước. STOMP cần xử lý `content-length` nếu body có byte NUL. |
| `MapMessage` | Tập key/value với các kiểu JMS hỗ trợ | AMQP có map/value riêng nhưng cách chuyển đổi và kiểu số có thể phụ thuộc provider. STOMP/MQTT không có một kiểu MapMessage tương đương theo giao thức. |
| `ObjectMessage` | Đối tượng Java được serialize | **Không thích hợp làm hợp đồng xuyên giao thức**: phụ thuộc class, serializer, compatibility và rủi ro bảo mật deserialization. |
| `StreamMessage` | Chuỗi giá trị tuần tự có kiểu | Không có cách biểu diễn tương đương tự nhiên trên mọi giao thức; cần chuyển thành schema payload cụ thể. |

Trường hợp message JMS dạng `TextMessage` được chuyển qua AMQP không đồng nghĩa lúc dùng một AMQP client thuần bạn sẽ luôn nhận một `amqp-value<string>` giống nhau. Mapping cụ thể do provider và phiên bản quyết định. Với Qpid JMS, provider có thể ánh xạ dữ liệu vào đối tượng JMS; một AMQP client thuần lại nhìn thấy cấu trúc AMQP khác. Khi tính portability, **kiểm tra bytes và nội dung đã giải mã**, không đoán từ tên class của producer.

### 3.2. Hợp đồng khuyến nghị cho dữ liệu liên giao thức

Với sự kiện nghiệp vụ, ưu tiên **payload JSON UTF-8 có schema** và chỉ dùng một tập nhỏ metadata ổn định:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-1042",
  "eventType": "OrderCreated",
  "orderId": "ORD-1042",
  "amount": 1500,
  "currency": "VND",
  "occurredAt": "2026-11-17T07:00:00Z"
}
~~~

Điều kiện để payload thực sự portable:

- Bên phát và bên nhận thống nhất **UTF-8**, schema và ý nghĩa đơn vị (ví dụ `amount` là đồng tiền nguyên, không nhầm đơn vị nhỏ nhất với giá trị thập phân).
- `schemaVersion` giúp consumer từ chối hoặc xử lý phù hợp khi schema thay đổi; không dựa vào version của client JMS.
- `eventId` nằm **trong payload** để làm khóa idempotency cho mọi protocol; nếu cũng đưa vào message property thì hai nơi phải đồng nhất.
- Không chứa object Java serialize, class name hay thông tin đăng nhập trong body.
- `content-type: application/json` là thông tin hữu ích **nếu client và broker truyền tải được**; vẫn phải kiểm tra payload đúng là JSON UTF-8 ở bên nhận.
- Trường hợp payload lớn, cần kiểm thử giới hạn frame/message và chiến lược large-message/paging của từng giao thức. Một wire format có thể không giữ mọi metadata kiểu của wire format khác.

### 3.3. “Số 1500” là bẫy mapping thường gặp

Ở Java JMS:

~~~java
message.setIntProperty("amount", 1500);        // Integer
message.setStringProperty("currency", "VND"); // String
~~~

Ở STOMP, **header có giá trị dạng chuỗi**. Một sender STOMP có thể gửi:

~~~text
amount:1500
currency:VND
~~~

Khi broker chuyển thông tin đó thành message properties, không được **mặc định** `amount` sẽ thành JMS `int`. JMS selector:

~~~sql
amount >= 1000
~~~

đòi hỏi toán hạng có kiểu phù hợp; nếu `amount` thực sự là chuỗi `"1500"` thì so sánh số **không tự nhiên có cùng ngữ nghĩa**. Tránh dựa vào cơ chế auto-conversion đặc thù broker để bảo đảm tương thích lâu dài.

**Quy tắc:** Các trường dùng để lọc/routing cần quy định **kiểu property**, cách đưa vào protocol khác và test selector xuyên giao thức. Nếu có nhiều client không quản lý được kiểu header, hãy dựa trên **payload schema và consumer validation**, hoặc dùng thuộc tính chuỗi có ý nghĩa cố định, ví dụ `eventType = 'OrderCreated'`.

## 4. Header và identifier: những thứ trông giống nhau nhưng khác phạm vi

Message metadata chia thành:

- **Application metadata:** `eventId`, `traceId`, `eventType`, `schemaVersion` do ứng dụng định nghĩa. Nên giữ khóa chính ổn định trong payload, rồi bổ sung property nếu cần selector.
- **Provider/protocol metadata:** ID do broker sinh, priority, destination, TTL/expiration, delivery count, ACK token, packet identifier… có thể đổi dạng khi chuyển giao thức.

### 4.1. Ma trận đối chiếu header

| Ý nghĩa | JMS/Artemis Core (thông qua JMS API) | AMQP 1.0 | STOMP | MQTT |
|---|---|---|---|---|
| Định danh nghiệp vụ | `eventId` dưới dạng JMS property | `application-properties["eventId"]` nếu mapping phù hợp | Custom header `eventId` kiểu chuỗi | Trong payload; MQTT 5 có user properties nhưng không phải bản sao JMS property bảo đảm |
| ID message do provider tạo | `JMSMessageID` | `properties.message-id` có thể có nhiều kiểu AMQP | `message-id` của MESSAGE frame | Packet Identifier (nếu QoS cần) có phạm vi trao đổi MQTT, **không phải eventId** |
| Correlation | `JMSCorrelationID` | `properties.correlation-id`, có thể không phải chuỗi | Custom header, cách map phụ thuộc provider | MQTT 5 có `Correlation Data` dạng bytes; MQTT 3.1.1 không có trường tương đương |
| Điểm trả lời | `JMSReplyTo` là Destination | `properties.reply-to`, định dạng địa chỉ AMQP | Thường phải định nghĩa header ứng dụng hoặc convention riêng | MQTT 5 `Response Topic`, không mặc định giống JMSReplyTo |
| Độ ưu tiên | `JMSPriority` (0–9) | `header.priority` | Custom/provider-specific header nếu hỗ trợ | Không có header priority tương đương chuẩn |
| Hạn sử dụng | `JMSExpiration` / TTL | `ttl` hoặc `absolute-expiry-time` | Header thời hạn phụ thuộc broker, không chuẩn hóa thành JMS TTL mọi nơi | MQTT 5 có Message Expiry Interval; MQTT 3.1.1 không |
| Loại nội dung | JMS class + property ứng dụng nếu đặt | `content-type`, `body section` | `content-type` và `content-length` | Payload bytes; MQTT 5 có Content Type và Payload Format Indicator |
| Lần giao lại | `JMSRedelivered`, `JMSXDeliveryCount` nếu được hỗ trợ | Delivery state/count theo AMQP mapping và broker | Có thể có redelivery metadata theo broker; không phải header portable chung | `DUP` báo retransmission theo giao thức; **không phải số lần xử lý nghiệp vụ** |

Các cột **không phải quy tắc chuyển đổi 1:1**. Ví dụ AMQP `message-id` có thể là UUID hoặc unsigned long, còn `JMSMessageID` thường được JMS provider biểu diễn thành chuỗi riêng. Khi đổi qua client/protocol, việc so sánh trực tiếp hai ID có thể thất bại dù chúng đại diện cùng một message logic.

### 4.2. Không dùng provider message ID làm khóa chống trùng

Giả sử một message có:

~~~text
JMSMessageID = ID:brokerA-...   (do provider đặt)
eventId      = evt-1042         (do ứng dụng đặt)
traceId      = trace-801        (do ứng dụng đặt)
~~~

Sau khi bridge, replay hoặc chuyển giao thức, provider ID có thể khác hoặc không được thể hiện theo cùng cú pháp. Khóa idempotency nên dựa trên **`eventId` do domain cấp ổn định**, không phải `message-id`, `JMSMessageID` hay MQTT Packet Identifier.

Tương tự, **`traceId` để theo dõi** và **`correlationId` cho request/reply** có thể có chức năng khác nhau. Nếu cần truy vết xuyên Core/AMQP/STOMP/MQTT, đưa `traceId` vào payload hoặc application metadata do các bên đã thỏa thuận, thay vì chỉ trông chờ `JMSCorrelationID` được mọi protocol tự tái tạo đúng.

### 4.3. Header STOMP, MQTT phải kiểm tra theo phiên bản

- STOMP frame có cú pháp header dạng văn bản, giữa header và body là dòng trống, kết thúc frame bằng byte NUL; nếu có `content-length`, parser phải tuân theo độ dài để không nhầm byte NUL trong payload thành kết thúc.
- STOMP 1.2 dùng giá trị ở **`ack` header của MESSAGE frame** làm token cho header `id` trong frame ACK/NACK. Đừng thay bằng `message-id` theo thói quen từ các phiên bản cũ.
- MQTT 3.1.1 không có User Properties; MQTT 5 có thêm User Properties, Content Type, Correlation Data và Message Expiry, nhưng mức hỗ trợ cần kiểm tra ở **broker/client/phiên bản**. Không giả định broker Artemis tự ánh xạ mọi user property của MQTT 5 thành JMS property cùng tên.
- Khi dùng OpenWire từ ActiveMQ Classic client tới Artemis, những kiểu đặc thù như `ObjectMessage` và thuộc tính của ActiveMQ Classic cần kiểm thử riêng; khả năng đọc một JMS property không đồng nghĩa mọi extension của Classic tồn tại trên AMQP, STOMP hay MQTT.

## 5. ACK/settlement: khác nhau về thao tác, cùng một câu hỏi nghiệp vụ

**Acknowledgment của transport xác nhận việc giao/nhận message theo quy tắc của provider. Nó không có nghĩa đơn hàng đã giao, email đã gửi hoặc transaction DB đã commit.**

### 5.1. So sánh theo giao thức

| Cơ chế | Khi nào message có thể được xác nhận? | Cách biểu đạt | Điểm cần thận trọng |
|---|---|---|---|
| JMS `AUTO_ACKNOWLEDGE` | Provider xác nhận theo semantics nhận đồng bộ hoặc callback thành công | JMS provider phát ACK qua Core/OpenWire/AMQP | Nếu code nhận rồi thực hiện side effect sau đó, message có thể đã được ACK trước khi nghiệp vụ hoàn tất |
| JMS `CLIENT_ACKNOWLEDGE` | Ứng dụng gọi `message.acknowledge()` | ACK của JMS provider | Theo JMS, một lệnh acknowledge có thể xác nhận **mọi message đã nhận trong cùng session**; không mặc định ACK riêng một message |
| JMS transacted session | Ứng dụng gọi `session.commit()` hoặc `context.commit()` | Commit JMS transaction | `rollback()` cho phép redelivery; **không nguyên tử với DB/HTTP bên ngoài** nếu chưa có cơ chế phối hợp |
| AMQP 1.0 | Receiver đưa ra delivery outcome và settlement | `accepted`, `released`, `rejected`, `modified`… | `accepted` có ý nghĩa ở cấp delivery; mapping và settlement mode quyết định thời điểm broker ghi nhận |
| STOMP `ack:auto` | Server/client xử lý theo cơ chế tự xác nhận của subscription | Không cần ACK frame riêng | Không dùng khi nghiệp vụ cần quyết định ACK sau khi commit |
| STOMP `ack:client` | Client gửi ACK có thể xác nhận **tích lũy** các message đến vị trí đó trên subscription | `ACK` frame | Không nhầm với xác nhận riêng từng message |
| STOMP `ack:client-individual` | Client gửi ACK cho đúng delivery token | `ACK` frame, STOMP 1.2 dùng `id=<ack token>` | Phù hợp demo manual ACK; cần xử lý NACK, disconnect, redelivery |
| MQTT QoS 0 | Không có handshake bảo đảm nhận ở lớp MQTT | PUBLISH QoS 0 | Có thể mất trên đường truyền; không có PUBACK |
| MQTT QoS 1 | Bên gửi/nhận hoàn thành bước giao theo handshake MQTT | PUBLISH/PUBACK | Có thể có retransmission/duplicate; PUBACK **không nói consumer khác đã xử lý DB** |
| MQTT QoS 2 | Handshake bảo đảm exactly-once delivery theo phạm vi MQTT protocol exchange | PUBLISH/PUBREC/PUBREL/PUBCOMP | Không mở rộng thành exactly-once **đầu-cuối xuyên JMS/DB** |

AMQP 1.0 còn phân biệt **delivery outcome** và **settlement**. Receiver có thể xử lý delivery ở các trạng thái chưa settled trước khi broker quyết định cuối cùng. Nếu dùng **Qpid JMS**, ứng dụng gọi `JMSContext.commit()` nhưng thư viện thực hiện thao tác AMQP dưới lớp API; nếu dùng AMQP native, ứng dụng phải quản lý disposition/settlement trực tiếp. Không tự áp dụng cách ACK của JMS vào một client AMQP native.

### 5.2. Ba ranh giới gây duplicate

~~~mermaid
sequenceDiagram
    participant P as JMS Producer (Core)
    participant B as Artemis queue
    participant C as STOMP/AMQP Consumer
    participant D as Business DB
    P->>B: Gửi eventId=evt-1042
    B-->>P: Send/commit thành công
    B->>C: Giao message
    C->>D: Ghi nghiệp vụ với eventId
    D-->>C: DB commit thành công
    Note over C: Tiến trình chết trước ACK/disposition
    B->>C: Redelivery cho consumer phù hợp
    C->>D: Kiểm tra eventId đã xử lý
    D-->>C: Không làm lại side effect
    C->>B: ACK/accepted/commit
~~~

Có ba điểm có thể sai:

1. Producer gửi đi nhưng không biết chắc broker đã nhận vì kết nối đứt đúng lúc xác nhận: ứng dụng có thể **gửi lại cùng eventId**.
2. Broker đã giao message nhưng consumer mất kết nối trước ACK: broker có thể **giao lại** sau timeout/rollback.
3. DB hoặc HTTP side effect thành công nhưng consumer chưa kịp ACK: nếu không idempotent, tác động có thể **lặp** khi redelivery.

Điều kiện an toàn thường dùng là **at-least-once delivery + idempotent handler**:

~~~sql
BEGIN;

-- Cần unique constraint trên (consumer_name, event_id).
INSERT INTO processed_messages (consumer_name, event_id)
VALUES ('fulfillment', 'evt-1042');

-- Cập nhật dữ liệu nghiệp vụ trong cùng transaction DB.
UPDATE orders SET state = 'READY_FOR_SHIPPING'
WHERE order_id = 'ORD-1042' AND state = 'PAID';

COMMIT;
~~~

Trong code thật, phải xử lý lỗi vi phạm unique constraint như trường hợp “đã xử lý” và tránh phát lại side effect. Khi DB commit xong, consumer mới ACK. Đối với email/API bên ngoài, cần cơ chế idempotency của downstream hoặc outbox cho việc phát lệnh bên ngoài; ví dụ SQL trên **không biến HTTP thành một phần của DB transaction**.

## 6. Cấu hình broker Artemis cho kịch bản liên giao thức

Để kiểm chứng rõ ràng, dùng **một anycast queue** `interop.orders` được khai báo tường minh. Khi ấy cả producer JMS Core và consumer AMQP/STOMP sẽ truy cập cùng queue theo tên giống nhau. Tránh trộn queue/topic, auto-created subscriptions và routing multicast trong phép thử đầu tiên.

**Điều kiện:** một broker Artemis instance đã được tạo, có JDK phù hợp, user/password cho phép gửi và nhận ở `interop.orders`. Các đoạn XML dưới là **mảnh cấu hình đặt trong section có sẵn của `ARTEMIS_INSTANCE/etc/broker.xml`**; không thay toàn bộ file, không tạo thêm section trùng. Dừng broker và restart sau khi chỉnh trong lab.

### 6.1. Acceptor theo giao thức

Trong `<acceptors>` đã có, cấu hình hoặc điều chỉnh các acceptor:

~~~xml
<acceptor name="lab-core">
    tcp://127.0.0.1:61616?protocols=CORE
</acceptor>
<acceptor name="lab-amqp">
    tcp://127.0.0.1:5672?protocols=AMQP
</acceptor>
<acceptor name="lab-stomp">
    tcp://127.0.0.1:61613?protocols=STOMP
</acceptor>
<acceptor name="lab-mqtt">
    tcp://127.0.0.1:1883?protocols=MQTT
</acceptor>
~~~

- `61616`: Artemis Core/JMS client trong lab.
- `5672`: AMQP 1.0 client (ví dụ Qpid JMS).
- `61613`: STOMP client.
- `1883`: MQTT client nếu bạn thực hành phần tùy chọn.

Đây là **bốn cổng riêng** nhằm làm rõ protocol. Một số cấu hình Artemis sử dụng acceptor đa giao thức; không cần tạo bốn cổng nếu không có yêu cầu lab. Nếu instance đã dùng một cổng cho giao thức khác, sửa/thay cấu hình tương ứng để tránh `Address already in use`. Chỉ bind localhost để thử nghiệm; môi trường thật cần TLS, phân quyền và firewall. STOMP `login/passcode` qua TCP không mã hóa **không nên đưa qua mạng không tin cậy**.

### 6.2. Address/queue dùng chung

Bên trong `<addresses>` hiện hữu:

~~~xml
<address name="interop.orders">
    <anycast>
        <queue name="interop.orders">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
~~~

Queue này có **một backlog chung**. Mỗi message được consumer nhận/ACK thì không còn trong queue cho consumer khác. Muốn **mỗi loại dịch vụ đều nhận bản sao**, cần thiết kế multicast với queue/subscription độc lập; bài này dùng anycast chỉ để đo khác biệt kiểu dữ liệu, header và ACK trên cùng message.

Vì queue có tên trùng address và khai báo anycast rõ ràng, ví dụ Java và STOMP bên dưới đều dùng destination `interop.orders`. Tuy nhiên **prefix/mapping của STOMP hoặc AMQP có thể được cấu hình khác ở broker từng môi trường**; hãy đối chiếu console để chắc chắn cả hai đang trỏ tới **cùng queue vật lý**. Đừng kết luận chỉ từ việc tên destination giống nhau.

### 6.3. Quyền truy cập và retry

Cấu hình user/role theo cơ chế bảo mật của instance. Với mục đích minh họa, trong section `<security-settings>` có thể cấp cho role lab:

~~~xml
<security-setting match="interop.orders">
    <permission type="send" roles="interop-lab"/>
    <permission type="consume" roles="interop-lab"/>
</security-setting>
~~~

Role `interop-lab` phải tồn tại và được gán cho user của bạn. Nếu queue đã khai báo tường minh và không cần client tạo queue, thông thường không cấp quyền tạo/xóa queue chỉ để chạy lab. Khi cần test redelivery, cấu hình chính sách ở `<address-settings>` phù hợp, tránh vòng lặp retry nóng.

Không đặt message type/selector theo cấu hình broker để “đoán” kiểu JSON; broker **không tự biết schema ứng dụng**. Thử nghiệm dưới đây sẽ kiểm tra representation thực tế ở từng client.

## 7. Thực hành A: Java Core/JMS producer gửi payload và metadata có kiểu

### 7.1. Dependency

Ví dụ Java 17 dùng Jakarta Messaging (`jakarta.jms.*`) cùng Artemis Jakarta client tương thích broker. Trong `pom.xml` của project lab độc lập:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <!-- Định nghĩa phiên bản Artemis client đã kiểm thử trong dự án. -->
    <artemis.version>2.57.0</artemis.version>
</properties>
<dependencies>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>${artemis.version}</version>
    </dependency>
</dependencies>
~~~

Phiên bản trên là **ví dụ cấu hình dependency**, cần kiểm tra với broker/JDK thực tế. Dự án dùng API `javax.jms.*` phải chọn client tương ứng; không trộn hai namespace.

### 7.2. Mã nguồn

Lớp `CoreJmsPublisher` tạo message có **JSON body**, một property kiểu `int` và các property kiểu chuỗi. Nó cũng đặt `JMSCorrelationID` để so sánh xem client khác nhìn thấy gì.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.UUID;

public final class CoreJmsPublisher {
    public static void main(String[] args) throws Exception {
        String user = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");
        String eventId = "evt-" + UUID.randomUUID();
        String traceId = "trace-" + UUID.randomUUID();

        String json = """
            {"schemaVersion":1,
             "eventId":"%s",
             "eventType":"OrderCreated",
             "orderId":"ORD-1042",
             "amount":1500,
             "currency":"VND"}
            """.formatted(eventId);

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue("interop.orders");

            TextMessage message = context.createTextMessage(json);
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("eventType", "OrderCreated");
            message.setStringProperty("traceId", traceId);
            message.setStringProperty("payloadFormat", "application/json");
            message.setIntProperty("amount", 1500); // Integer, không phải String.
            message.setJMSCorrelationID(traceId);

            try {
                context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .send(queue, message);
                context.commit();

                System.out.println("eventId=" + eventId);
                System.out.println(
                    "JMSMessageID=" + message.getJMSMessageID());
                System.out.println("traceId=" + traceId);
            } catch (Exception error) {
                context.rollback();
                throw error;
            }
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + name);
        }
        return value;
    }
}
~~~

**Kết quả cần ghi:** `eventId` và `traceId` trong log producer; count queue tăng 1 khi chưa có consumer. Bởi vì producer dùng `SESSION_TRANSACTED`, message chỉ được coi là đã gửi hoàn tất sau `context.commit()` thành công. Nếu mạng đứt đúng lúc commit, kết quả có thể không xác định; khi retry phải **giữ cùng eventId cho cùng sự kiện**, không tự tạo eventId mới.

Trước mỗi lượt kiểm tra, hoặc dùng queue trống hoặc ghi lại `eventId` cụ thể để phân biệt message mới và cũ. **Không chạy nhiều consumer cùng lúc** khi đang so sánh một message: vì đây là anycast queue, consumer nào ACK trước thì message không còn cho consumer còn lại.

## 8. Thực hành B: nhận cùng message bằng AMQP 1.0 qua Qpid JMS

Đây là phép thử rất hữu ích: **API Java vẫn là Jakarta JMS**, nhưng giao thức kết nối đã đổi từ **Artemis Core** sang **AMQP 1.0**.

### 8.1. Dependency và URL

Dùng provider Qpid JMS dòng **Jakarta-compatible** (kiểm tra phiên bản được chọn). Khai báo một dependency trong dự án nhận:

~~~xml
<dependency>
    <groupId>org.apache.qpid</groupId>
    <artifactId>qpid-jms-client</artifactId>
    <version>${qpid.jms.version}</version>
</dependency>
~~~

Định nghĩa `qpid.jms.version` bằng **bản Qpid JMS đã xác nhận dùng `jakarta.jms.*`**; các bản client cũ có thể dùng `javax.jms.*`. URL AMQP sử dụng cổng `5672`, không phải cổng Core `61616` trong bài lab.

### 8.2. Mã nhận bằng AMQP/JMS

~~~java
import jakarta.jms.BytesMessage;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.qpid.jms.JmsConnectionFactory;

import java.nio.charset.StandardCharsets;

public final class AmqpJmsReceiver {
    public static void main(String[] args) throws Exception {
        String user = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");

        JmsConnectionFactory factory =
            new JmsConnectionFactory("amqp://127.0.0.1:5672");

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = context.createQueue("interop.orders");
            Message message = context.createConsumer(queue).receive(8000);
            if (message == null) {
                System.out.println("Không có message trong 8 giây.");
                return;
            }

            try {
                System.out.println(
                    "Class=" + message.getClass().getName());
                System.out.println(
                    "JMSMessageID=" + message.getJMSMessageID());
                System.out.println(
                    "JMSCorrelationID=" + message.getJMSCorrelationID());
                System.out.println(
                    "eventId=" + message.getStringProperty("eventId"));
                System.out.println(
                    "traceId=" + message.getStringProperty("traceId"));

                if (message.propertyExists("amount")) {
                    System.out.println(
                        "amount=" + message.getObjectProperty("amount")
                        + ", property object class="
                        + message.getObjectProperty("amount")
                                 .getClass().getName());
                }

                if (message instanceof TextMessage text) {
                    System.out.println("Text body=" + text.getText());
                } else if (message instanceof BytesMessage bytes) {
                    byte[] buffer = new byte[(int) bytes.getBodyLength()];
                    bytes.readBytes(buffer);
                    System.out.println(
                        "Byte body=" +
                        new String(buffer, StandardCharsets.UTF_8));
                } else {
                    System.out.println(
                        "Kiểu JMS message khác, cần mapping theo provider.");
                }

                // Trong ứng dụng thật: validate schema, xử lý idempotent.
                context.commit();
                System.out.println("AMQP/JMS transaction committed.");
            } catch (Exception error) {
                context.rollback();
                throw error;
            }
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + name);
        }
        return value;
    }
}
~~~

**Điểm quan sát quan trọng:** `eventId` trong JSON và property ứng dụng phải cùng giá trị. Kiểm tra kiểu của `amount` bằng `getObjectProperty()` thay vì chỉ in giá trị. Lưu lại `JMSMessageID` và `JMSCorrelationID` bên nhận để đối chiếu, **không giả định chuỗi ID giống hệt producer**: provider có thể map field AMQP khác so với JMS Core.

Code kiểm tra `TextMessage` và `BytesMessage` vì kiểu JMS nhận được phụ thuộc mapping của broker/provider. Đừng ngầm ép mọi message nhận qua AMQP thành `TextMessage`; ứng dụng production cần một hợp đồng content-type/body rõ ràng và xử lý mismatch có kiểm soát.

**Về transaction:** `context.commit()` ở ứng dụng Qpid JMS đi qua AMQP provider. Một client AMQP native không có JMS transaction API sẽ phải tự quản lý delivery outcome, settlement hoặc AMQP transactions nếu giao thức/provider hỗ trợ. Hai ứng dụng không “dùng chung một transaction” chỉ vì cùng tiêu thụ một queue.

## 9. Thực hành C: STOMP 1.2 manual ACK trên cùng queue

Bài này dùng Java standard library mở kết nối TCP thô để thấy chính xác frame STOMP. Đây là **client tối giản cho payload UTF-8 không chứa byte NUL**, không phải STOMP parser đủ chức năng. Nếu dùng trong production, nên chọn thư viện STOMP quản lý chuẩn escaping, `content-length`, heartbeat và reconnect.

### 9.1. Trao đổi frame trên wire

Client gửi:

~~~text
CONNECT
accept-version:1.2
host:localhost
login:<user>
passcode:<password>

\0
~~~

Sau khi nhận `CONNECTED`, client subscribe vào queue:

~~~text
SUBSCRIBE
id:orders-sub
destination:interop.orders
ack:client-individual

\0
~~~

Broker gửi một frame tương tự:

~~~text
MESSAGE
subscription:orders-sub
message-id:<broker-message-id>
ack:<opaque-ack-token>
destination:interop.orders
eventId:evt-1042

{"eventId":"evt-1042", "...":"..."}\0
~~~

**Chú ý hai ID:** `message-id` là định danh message do server đưa ra trong MESSAGE frame; với **STOMP 1.2**, client phải dùng giá trị **`ack:...`** của MESSAGE frame cho `ACK id:...`:

~~~text
ACK
id:<opaque-ack-token>
receipt:ack-1

\0
~~~

Broker có thể gửi `RECEIPT` ứng với `ack-1`; receipt xác nhận server đã xử lý frame ở cấp STOMP. Nó **không** chứng minh hiệu ứng nghiệp vụ bên ngoài broker đã commit.

Ký hiệu `\0` trong ví dụ là **một byte NUL thực tế (0x00)**, không phải hai ký tự backslash và số 0. Khi viết client, phải gửi byte này ở cuối frame.

### 9.2. Java STOMP client tối giản

Chạy sau khi publish một message mới, lúc queue chưa có consumer nào khác:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public final class StompManualAckReceiver {
    public static void main(String[] args) throws Exception {
        String user = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");
        boolean ack = args.length == 0 || !"no-ack".equals(args[0]);

        try (Socket socket = new Socket("127.0.0.1", 61613)) {
            socket.setSoTimeout(15000);
            InputStream input = socket.getInputStream();
            OutputStream output = socket.getOutputStream();

            // Demo chỉ dành cho credentials đơn giản không chứa CR/LF.
            send(output,
                "CONNECT\naccept-version:1.2\nhost:localhost"
                + "\nlogin:" + user
                + "\npasscode:" + password + "\n\n\0");

            String connected = readTextFrame(input);
            if (!connected.startsWith("CONNECTED\n")) {
                throw new IllegalStateException(
                    "STOMP CONNECT thất bại: " + connected);
            }

            send(output,
                "SUBSCRIBE\nid:orders-sub"
                + "\ndestination:interop.orders"
                + "\nack:client-individual\n\n\0");

            String frame = readTextFrame(input);
            if (!frame.startsWith("MESSAGE\n")) {
                throw new IllegalStateException(
                    "Kỳ vọng MESSAGE: " + frame);
            }

            String ackToken = header(frame, "ack");
            String eventId = header(frame, "eventId");
            int divider = frame.indexOf("\n\n");
            String body = divider < 0 ? "" : frame.substring(divider + 2);

            System.out.println("eventId header=" + eventId);
            System.out.println("JSON body=" + body);

            // Production: parse JSON, validate schema và đảm bảo
            // idempotency trước khi gửi ACK.
            if (ack) {
                if (ackToken == null) {
                    throw new IllegalStateException(
                        "STOMP 1.2 MESSAGE thiếu ack token.");
                }
                send(output,
                    "ACK\nid:" + ackToken +
                    "\nreceipt:ack-1\n\n\0");

                String receipt = readTextFrame(input);
                if (!receipt.startsWith("RECEIPT\n")
                        || !receipt.contains("receipt-id:ack-1")) {
                    throw new IllegalStateException(
                        "Không nhận ACK receipt: " + receipt);
                }
                System.out.println("ACK receipt confirmed.");
            } else {
                System.out.println(
                    "Đóng kết nối trước ACK để thử redelivery.");
            }
        }
    }

    private static void send(OutputStream out, String frame)
            throws Exception {
        out.write(frame.getBytes(StandardCharsets.UTF_8));
        out.flush();
    }

    private static String header(String frame, String key) {
        int divider = frame.indexOf("\n\n");
        String lines = divider >= 0
            ? frame.substring(0, divider) : frame;

        for (String line : lines.split("\n")) {
            int colon = line.indexOf(':');
            if (colon > 0 && line.substring(0, colon).equals(key)) {
                return line.substring(colon + 1);
            }
        }
        return null;
    }

    private static String readTextFrame(InputStream input)
            throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        int value;

        while ((value = input.read()) != -1) {
            if (value == 0) {
                return out.toString(StandardCharsets.UTF_8)
                    .replace("\r\n", "\n");
            }
            // Bỏ qua heartbeat LF/CR ở đầu frame.
            if (out.size() == 0 && (value == '\n' || value == '\r')) {
                continue;
            }
            out.write(value);
        }
        throw new EOFException("Kết nối đóng giữa chừng.");
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + name);
        }
        return value;
    }
}
~~~

**Giới hạn chủ ý của mã:** `readTextFrame()` đọc tới NUL nên **chỉ an toàn trong demo payload text không chứa NUL**. STOMP chuẩn cho phép body nhị phân và hỗ trợ `content-length`; client thật phải đọc đúng số bytes, xử lý escaping header của STOMP 1.2, `ERROR`/`RECEIPT`, heartbeat và reconnect. Mã trên cũng không xử lý hết tình huống `CONNECTED`/`ERROR` có nhiều header/line endings và không mã hóa nội dung credentials; chỉ dùng trên localhost lab.

### 9.3. Kiểm chứng redelivery với STOMP

1. Dọn queue lab và chạy `CoreJmsPublisher` một lần.
2. Chạy `StompManualAckReceiver no-ack`. Chương trình nhận MESSAGE rồi đóng TCP **trước khi ACK**.
3. Kiểm tra queue count/delivering và cấu hình redelivery; broker có thể giao lại message cho consumer mới sau khi phát hiện disconnect.
4. Chạy `StompManualAckReceiver` (không đối số); so sánh **cùng eventId** với lần trước. Lần này chương trình gửi `ACK` và đợi `RECEIPT`, queue giảm sau khi xử lý thành công.
5. Nếu message không được giao lại ngay, kiểm tra timeout, chính sách redelivery, số lần giao tối đa, DLQ và consumer khác; không đặt kỳ vọng cố định “đúng 1 giây” khi chưa cấu hình.

STOMP `NACK` có thể biểu đạt việc không chấp nhận delivery; Artemis xử lý theo cơ chế redelivery/poison message và cấu hình broker/client. Không suy rằng `NACK` luôn chuyển thẳng sang DLQ hoặc luôn có cùng ngữ nghĩa với `session.rollback()` của JMS.

## 10. MQTT: lý do không thể biến PUBACK thành JMS ACK

MQTT có mô hình **publish/subscribe theo topic** với payload là bytes và QoS cho từng trao đổi client-broker. Nó không có cùng mô hình queue transaction/acknowledgment API như JMS. Vì vậy trước khi nối MQTT với queue Artemis hoặc JMS consumer, cần tách hai vấn đề:

1. **Routing/interoperability:** topic name MQTT sẽ được map tới address và subscription/queue như thế nào, theo phiên bản Artemis và cấu hình? Nhiều trường hợp MQTT dùng multicast/pub-sub semantics, không giống một JMS anycast queue.
2. **Độ tin cậy:** mức QoS mà publisher chọn và mức QoS của subscriber **là hai chặng khác nhau**. QoS 2 ở chặng MQTT không bảo đảm một consumer JMS khác không xử lý side effect hai lần.

### 10.1. Ba mức QoS qua ví dụ sensor

| QoS | Bên phát biết gì ở cấp MQTT? | Điều vẫn chưa được bảo đảm |
|---|---|---|
| **0** | Gửi PUBLISH, không có handshake ACK bảo đảm nhận | Không biết broker đã nhận hay chưa; mất message có thể xảy ra |
| **1** | Nhận PUBACK khi exchange hoàn tất ở mức QoS 1 | Subscriber/worker downstream đã ghi DB hay chưa, duplicate ứng dụng |
| **2** | Hoàn tất handshake QoS 2 cho exchange | Exactly-once **toàn chuỗi MQTT → Artemis → JMS → DB** |

Ví dụ một thiết bị gửi:

~~~text
MQTT PUBLISH
topic: sensors/temp
payload bytes: {"deviceId":"s-7","celsius":28.4}
qos: 1
~~~

Broker có thể phản hồi PUBACK, trong khi consumer Java ở một queue khác chưa xử lý xong. Nếu consumer Java chết sau DB commit nhưng trước ACK của phía mình, message vẫn có thể bị giao lại trong chặng đó. Vì vậy phải dùng **eventId/readingId trong payload và idempotency ở nơi ghi DB**.

### 10.2. Những metadata thường bị nhầm

- **MQTT Packet Identifier** chỉ phục vụ các exchange QoS nhất định, bị tái sử dụng theo thời gian và không phải định danh domain.
- **MQTT DUP** chỉ là dấu hiệu retransmission theo giao thức, không phải cờ chắc chắn ứng dụng đã ghi DB trùng.
- **MQTT retained message** là cơ chế lưu bản gần nhất cho topic theo MQTT, **không phải** durable JMS topic subscription hay event log có đầy đủ lịch sử.
- **MQTT session persistence** và Artemis durable queue có quan hệ cần cấu hình/kiểm thử, nhưng không nên coi chúng là một thứ.
- **MQTT 5 User Properties** là các cặp chuỗi có thể giúp đưa metadata, nhưng client MQTT 3.1.1 không có trường này; body phải tự chứa các trường cốt lõi nếu muốn tương thích rộng.

Nếu cần thực hành MQTT qua `1883`, có thể dùng MQTT client bất kỳ được broker và cơ chế xác thực hỗ trợ để publish/subscribe vào một topic **riêng**, ví dụ `sensors/temp`, rồi quan sát QoS 0/1/2. Không dùng MQTT test đó để kết luận `interop.orders` anycast có mapping y hệt JMS; muốn làm việc ấy phải định nghĩa và kiểm chứng routing riêng.

## 11. Quy trình kiểm chứng có thể lặp lại

Mỗi kịch bản sau nên bắt đầu với queue `interop.orders` trống, không có consumer khác và broker đang chạy với bốn acceptor như phần 6.

| Ca | Producer → Consumer | Bước thực hiện | Kết quả cần ghi |
|---|---|---|---|
| **A** | Core/JMS → AMQP/Qpid JMS | Chạy publisher, rồi `AmqpJmsReceiver` | Body JSON đúng; `eventId` ổn định; ghi kiểu property `amount`, ID/header phía AMQP và queue về 0 sau commit |
| **B** | Core/JMS → STOMP 1.2 | Chạy publisher, rồi STOMP receiver mặc định | Frame MESSAGE có body JSON; ACK dùng token từ `ack` header; nhận RECEIPT; queue giảm |
| **C** | Core/JMS → STOMP 1.2 (mất ACK) | Chạy publisher, `no-ack`, sau đó receiver mặc định | Cùng `eventId` có thể được giao lại theo policy; queue giảm sau ACK hợp lệ |
| **D** | STOMP publisher → JMS/Core consumer | Dùng một client STOMP send payload JSON và header `amount:1500`, rồi JMS receive | Đối chiếu loại property thực tế; không mặc định selector số xử lý chuỗi |
| **E** | MQTT → MQTT, nếu có client hỗ trợ | So sánh QoS 0 và 1/2 trên topic thử riêng | Kiểm tra handshake, duplicate khi reconnect; không suy ra JMS transaction |
| **F** | AMQP/JMS producer → Core/JMS consumer | Đảo chiều ca A, giữ nguyên payload schema | Đối chiếu body, header, TTL/delivery mode nếu đặt; đánh dấu trường mapping khác |

### 11.1. Ca D: frame STOMP SEND để so kiểu dữ liệu

Client STOMP gửi một frame dạng:

~~~text
SEND
destination:interop.orders
content-type:application/json
eventId:evt-stomp-1
eventType:OrderCreated
amount:1500

{"schemaVersion":1,"eventId":"evt-stomp-1","amount":1500}\0
~~~

Đặt Java consumer nhận từ JMS queue `interop.orders`. Quan sát:

~~~java
Message message = context.createConsumer(queue).receive(5000);
if (message != null) {
    Object amount = message.getObjectProperty("amount");
    System.out.println("amount=" + amount);
    System.out.println(
        "Java type=" + (amount == null ? "null" : amount.getClass()));
}
~~~

Giá trị header trên STOMP wire là một **chuỗi văn bản**. Nếu broker/provider giữ kiểu String, selector `amount >= 1000` không được coi là hoạt động như với `setIntProperty("amount", 1500)`. Nếu môi trường của bạn có extension chuyển kiểu, phải ghi rõ phiên bản/cấu hình và test riêng. Khi cần lọc chính xác, thống nhất metadata ngay từ đầu.

### 11.2. Cách ghi log đủ để so sánh

Ở cả producer và consumer, ghi:

~~~text
eventId / traceId / schemaVersion
protocol + client library + version
destination address + queue name + routing type
payload byte length + charset + SHA-256 (nếu cần kiểm tra nguyên vẹn)
application properties: name, value, runtime type
provider message ID / correlation ID (chỉ để chẩn đoán)
delivery/ack timestamp, redelivery count nếu có
business result + idempotency outcome
~~~

Không ghi password, token hoặc toàn bộ payload chứa dữ liệu nhạy cảm vào log. **Đối chiếu payload hash và eventId** đáng tin cậy hơn việc chỉ so `JMSMessageID` với `message-id` của STOMP hay MQTT Packet Identifier.

### 11.3. Các bài test lỗi có ích hơn một lần happy path

- **Sai charset:** STOMP/MQTT payload là bytes không hợp lệ UTF-8 → consumer phải reject/quarantine theo hợp đồng, không tiếp tục parse bừa.
- **Sai kiểu metadata:** producer STOMP gửi `amount:1500` như chuỗi → JMS selector so số phải được test và có fallback rõ.
- **Mất kết nối trước ACK:** consumer đã log/DB commit nhưng chưa ACK → cùng `eventId` xuất hiện lại; phải phát hiện duplicate.
- **Mất kết nối sau ACK gửi nhưng trước receipt:** client có thể không biết chắc ACK đã được broker xử lý → không tự suy trạng thái từ timeout.
- **TTL/expiration:** publisher đặt TTL ngắn, consumer offline lâu → message có thể expire; không nhầm với việc broker “bỏ message vì khác giao thức”.
- **Unmatched routing:** AMQP/STOMP destination cùng tên nhưng queue không nhận → kiểm tra address, routing type, prefixes, auto-create và quyền.
- **Nhiều consumer cùng queue:** message được một consumer ACK rồi không còn cho consumer thứ hai → đây là hành vi anycast, không phải mất dữ liệu.

## 12. Chẩn đoán lỗi theo lớp

| Triệu chứng | Lớp cần kiểm tra | Câu hỏi cụ thể |
|---|---|---|
| Core/JMS kết nối được, AMQP không | **Acceptor/transport** | Cổng `5672` có listen? `protocols=AMQP`? TLS/credentials có khớp? |
| STOMP CONNECTED nhưng không thấy MESSAGE | **Destination/routing** | `destination:interop.orders` map tới queue nào? Queue có backlog? Role có quyền consume? |
| Cùng JSON nhưng JMS selector không khớp | **Metadata type** | Property `amount` là Integer hay String? Property có tồn tại hay chỉ nằm trong body? |
| AMQP nhận được body nhưng class JMS khác | **Provider mapping** | Provider dùng TextMessage hay BytesMessage? Content-type và body section trên wire là gì? |
| Provider message ID khác nhau | **Header mapping** | Đang so provider ID hay eventId? AMQP `message-id` có cùng kiểu dữ liệu không? |
| STOMP ACK không xóa message | **STOMP 1.2 ACK** | Có dùng đúng MESSAGE `ack` token cho ACK `id` không? Có receive receipt/error? |
| STOMP consumer nhận trùng | **Redelivery / business idempotency** | ACK đã gửi thành công chưa? Worker chết trước ACK? DLQ/retry policy ra sao? |
| MQTT PUBACK rồi DB vẫn chưa cập nhật | **ACK scope** | PUBACK xác nhận chặng nào? JMS/DB consumer có hoàn tất và ACK chưa? |
| Sau restart message không còn | **Durability/expiry** | Producer persistent? Broker persistence? TTL? Queue/subscription bền vững? |
| Cấu hình cùng tên queue nhưng kết quả khác | **Routing** | Anycast/multicast, FQQN, auto-create/prefix có khác giữa client? |

## 13. Quy tắc thiết kế để tránh lỗi liên giao thức

1. **Xác định contract ở cấp ứng dụng:** chọn JSON/Avro/Protobuf cùng schema, encoding, version và eventId; ghi rõ loại dữ liệu, đơn vị và timezone.
2. **Tối thiểu hóa phụ thuộc vào provider header:** dùng `eventId` và `traceId` trong payload hoặc application metadata được kiểm chứng; không dùng ID/packet identifier của protocol làm khóa nghiệp vụ.
3. **Test header thực sự đến đích:** đặc biệt là correlation ID, content-type, TTL, priority, delivery count và kiểu property dùng cho selector.
4. **Chọn chế độ ACK theo điểm hoàn tất nghiệp vụ:** với JMS dùng transaction/ACK chủ động; với STOMP dùng manual ACK khi cần; với AMQP native kiểm soát disposition/settlement. MQTT QoS không thay thế bước ACK của consumer JMS khác.
5. **Idempotency là bắt buộc khi có redelivery:** ghi nhận `(consumer, eventId)` với unique constraint và tạo side effect an toàn trước khi xác nhận message.
6. **Cấu hình broker theo từng giao thức:** kiểm tra acceptor, TLS, authentication, mapping destination và routing. Khác protocol không tự tạo fan-out độc lập.
7. **Quan sát bằng dữ liệu có thể đối chiếu:** payload hash, eventId, tên queue, loại header, ack/settlement timestamp, retry count và DLQ. Đừng chỉ xem số message đã dequeue.
8. **Ghi rõ phạm vi hỗ trợ của phiên bản:** Artemis và ActiveMQ Classic hỗ trợ các protocol/extension ở mức khác nhau; với MQTT 5, AMQP native transaction, STOMP ACK hay OpenWire extensions, dùng tài liệu và integration test của **đúng broker/client/version**.

### Câu hỏi tự kiểm tra

1. Tại sao Qpid JMS và Artemis JMS cùng nhập `jakarta.jms.*` nhưng vẫn có thể dùng hai wire protocol khác nhau?
2. Khi JMS producer gửi `TextMessage` chứa JSON, STOMP receiver có thể mặc định coi `content-type:application/json` và lớp Java TextMessage sẽ được giữ nguyên không?
3. Vì sao `amount >= 1000` có thể hoạt động với Core/JMS producer nhưng không hoạt động với STOMP sender gửi header `amount:1500`?
4. Trong STOMP 1.2, ACK phải tham chiếu `ack` token hay `message-id` của MESSAGE frame?
5. Khi MQTT publisher nhận PUBACK QoS 1, điều gì **đã được xác nhận** và điều gì **chưa được xác nhận** ở consumer Java/DB?
6. Nếu consumer STOMP đã cập nhật DB nhưng crash trước khi ACK, hãy mô tả cách idempotency giúp xử lý redelivery.
7. Một JMS queue `interop.orders` có một Core receiver và một AMQP receiver chạy đồng thời. Cả hai có đương nhiên nhận **cùng** mọi message không? Muốn fan-out nên dùng cấu trúc nào?
8. Những metadata nào bạn sẽ đặt vào payload/schema thay vì chỉ dựa vào header của một giao thức cụ thể?

### Hướng dẫn đối chiếu với tài liệu chính thức

Để xác minh khả năng hỗ trợ theo phiên bản và cấu hình đang chạy, xem tài liệu của Apache ActiveMQ Artemis tại [Artemis documentation](https://artemis.apache.org/components/artemis/documentation/latest/) về *Protocols Interoperability*, *AMQP*, *STOMP*, *MQTT*, *Address Model*, *Message Redelivery* và *JMS/Core Mapping*. Với client Qpid JMS, xem [Apache Qpid JMS](https://qpid.apache.org/components/jms/). Với STOMP frame/ACK, xem [STOMP Protocol Specification 1.2](https://stomp.github.io/stomp-specification-1.2.html); với MQTT QoS/metadata, đối chiếu đúng MQTT 3.1.1 hoặc MQTT 5 của client và broker.

**Kết luận:** Khi message đi qua nhiều giao thức, cần kiểm chứng **ba lớp độc lập**: *payload có giải mã cùng ý nghĩa không*, *header có giữ đúng tên và kiểu không*, *xác nhận có xảy ra sau khi nghiệp vụ hoàn tất không*. Artemis có thể giúp định tuyến message giữa Core, AMQP, STOMP và MQTT, nhưng không tự biến tất cả các API/message type/ACK thành một hợp đồng đồng nhất. Hãy dùng schema + eventId ổn định, cấu hình route rõ ràng, thử nghiệm provider mapping và idempotent consumer để hệ thống bất đồng bộ đáng tin cậy.
