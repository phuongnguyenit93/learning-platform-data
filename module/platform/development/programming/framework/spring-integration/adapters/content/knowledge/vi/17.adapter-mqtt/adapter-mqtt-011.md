# Xử lý duplicate message theo QoS

## 1. Vì sao MQTT message có thể được xử lý nhiều lần?

Một cảm biến nhiệt độ publish bản tin `{"eventId":"evt-1001","celsius":26.5}` lên MQTT với QoS 1. Broker đã nhận dữ liệu, nhưng packet `PUBACK` bị mất trên đường về. MQTT client không biết broker đã nhận hay chưa, nên cơ chế giao thức có thể dẫn tới gửi lại PUBLISH. Spring Integration backend vì thế có thể nhìn thấy **hai lần nhận** cho cùng một sự kiện nghiệp vụ. Nếu mỗi lần nhận đều tăng bộ đếm, tính tiền, gửi email hoặc điều khiển thiết bị, kết quả sẽ sai.

Bài **“Xử lý duplicate message theo QoS”** nằm trong chương **Adapter MQTT** thuộc module **SPRING_INTEGRATION_ADAPTERS**. Module hướng tới kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; xử lý hợp đồng message, lỗi và vòng đời kết nối. Trong MQTT, chuyện **nhận trùng** là điểm mà hợp đồng giao thức gặp ràng buộc nhất quán dữ liệu và business side effects.

Sau bài này, người học có thể:

1. Nêu chính xác ý nghĩa **QoS 0, 1, 2** và phạm vi xác nhận của từng QoS.
2. Phân biệt **gói MQTT được giao lại**, **retained snapshot được nhận lại**, **ứng dụng publish lại** và **hai events hợp lệ nhưng có nội dung giống nhau**.
3. Hiểu giới hạn của **DUP flag**, MQTT packet identifier, client session và Paho delivery token.
4. Thiết kế **business event ID** ổn định qua reconnect/retry và định danh scope theo tenant/device.
5. Áp dụng **deduplication/idempotency** bằng unique constraint và một database transaction chung với side effect.
6. Xây MQTT inbound adapter, `MessageChannel` và `IntegrationFlow` parse/validate event rồi gọi một processor chống trùng.
7. Phân biệt MQTT acknowledgement với transaction commit, xử lý lỗi, optional manual ACK và poison messages.
8. Kiểm thử flow không broker, DB concurrency và MQTT broker với lỗi mạng giả lập.
9. Điều phối duplicate khi bridge MQTT sang HTTP, JMS/AMQP, Kafka, database hoặc file/SFTP.

**Quy tắc nền tảng:** MQTT QoS mô tả việc giao **MQTT publication** trong phạm vi protocol. Nó không mặc định bảo đảm **một business event chỉ gây một side effect** trong Spring Integration hoặc hệ thống đích.

## 2. Ba tầng “một lần” thường bị đánh đồng

~~~mermaid
flowchart LR
    PUB["Publisher / thiết bị<br/>business event evt-1001"]
    BROKER[("MQTT broker")]
    IN["Spring MQTT inbound adapter"]
    CH["MessageChannel"]
    GUARD["Idempotency guard<br/>tenantId + eventId"]
    DB[("Database + business effect")]
    OUT["HTTP / JMS / Kafka / SFTP"]
    PUB -->|"MQTT PUBLISH QoS 1"| BROKER
    BROKER -->|"Có thể giao lại"| IN
    IN --> CH --> GUARD --> DB
    DB -->|"Nếu cần, qua outbox"| OUT
~~~

Phân biệt ba câu hỏi:

| Câu hỏi | Cơ chế liên quan | Cần kiểm chứng ở đâu? |
| --- | --- | --- |
| MQTT client/broker đã hoàn tất giao nhận một packet? | MQTT QoS, packet identifier, ACK/handshake. | Protocol/client/broker metrics và logs. |
| Spring Integration đã nhận callback và chuyển message vào flow? | MQTT inbound adapter, converter, `MessageChannel`, error channel. | App logs, metrics, integration tests. |
| Một business event đã tạo side effect **chính xác một lần**? | Event ID, database uniqueness, transaction, idempotent consumer/outbox. | Database và hệ thống đích, kể cả crash/retry scenarios. |

Ví dụ, QoS 2 giảm duplicate của **một publication trong phạm vi giao thức**, nhưng nếu business service gọi publish hai lần với cùng command ID thì broker thấy **hai publications độc lập**. Bên nhận vẫn phải nhận diện lệnh trùng theo business ID.

### 2.1. “Duplicate message” có nhiều định nghĩa

- **Transport duplicate:** một PUBLISH thuộc cùng giao dịch protocol được truyền lại vì ACK/lifecycle của QoS.
- **Application duplicate:** producer/outbox/worker phát lại cùng event với cùng business intent.
- **Replay:** một message đã lưu trong queue/session/retained hoặc kho lưu trữ được giao lại sau subscribe/restart.
- **Duplicate side effect:** dữ liệu hoặc hành động kinh doanh bị ghi/thực hiện lặp; đây là điều cần ngăn chặn.
- **Trùng nội dung hợp lệ:** hai sensor readings cùng nhiệt độ `26.5` nhưng có event ID khác, hoàn toàn có thể là **hai readings đúng**.

Không dùng một phép `payload.equals(...)` để kết luận hai sự kiện giống nhau: một thiết bị có thể phát giá trị nhiệt độ không đổi mỗi phút mà mỗi mẫu đều hợp lệ.

## 3. QoS 0: at most once của một MQTT PUBLISH

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    participant S as Subscriber
    P->>B: PUBLISH QoS 0
    B->>S: PUBLISH QoS 0 (nếu subscription phù hợp)
    Note over P,B: Không có PUBACK cho QoS 0
~~~

Ở QoS 0, sender không thực hiện handshake xác nhận PUBLISH; broker/client có thể bỏ lỡ message nếu mạng lỗi. Cơ chế giao thức **không cung cấp retransmission bảo đảm delivery** như QoS 1/2.

**QoS 0 không có nghĩa business event không thể trùng.** Ví dụ:

1. Thiết bị lấy reading `evt-1001`.
2. Publish QoS 0.
3. Ứng dụng thiết bị không biết broker có nhận không, nên tự gọi publish lại một PUBLISH **mới**.
4. Backend nhận hai PUBLISH độc lập với cùng `eventId`.

Cả hai publications có thể có QoS 0, vẫn gây duplicate nghiệp vụ. Vì vậy idempotent processor hữu ích ngay cả với nguồn QoS 0 nếu ứng dụng có retry/replay ngoài giao thức.

### 3.1. Trường hợp dùng QoS 0

QoS 0 hợp cho telemetry dày đặc, dữ liệu có thể đo lại hoặc mất một vài mẫu được chấp nhận. Không hợp với yêu cầu “không được mất bất kỳ lệnh thanh toán nào” chỉ bằng cấu hình QoS 0. Với dữ liệu quan trọng, cần storage và retry policy ở application/broker.

## 4. QoS 1: at least once và DUP có thể xuất hiện

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    participant S as Spring subscriber
    P->>B: PUBLISH QoS 1, packetId=57, DUP=0
    B->>S: PUBLISH eventId=evt-1001
    B--xP: PUBACK bị mất
    Note over P: Kết quả chưa chắc chắn
    P->>B: PUBLISH retry, packetId=57, DUP=1
    B->>S: PUBLISH có thể khiến app thấy evt-1001 lần nữa
    B-->>P: PUBACK packetId=57
~~~

Sơ đồ mô tả một tình huống minh họa. Việc broker chuyển phát lại tới subscriber, cách giữ session/packet state và thời điểm retry phụ thuộc protocol/client/broker và trạng thái connection; **đừng suy diễn rằng mọi QoS 1 retry đều tạo đúng hai callback**. Nhưng hệ thống dùng QoS 1 phải chịu được khả năng nhận lại.

QoS 1 sử dụng `PUBLISH → PUBACK`. Khi publisher chưa nhận PUBACK, nó có thể không biết broker đã xử lý hay chưa. Tương tự, broker → subscriber còn một chặng QoS/ACK riêng, vì vậy duplicate có thể xuất hiện ở bên nhận ngay cả khi publisher không nhìn thấy lỗi.

### 4.1. At least once không đồng nghĩa “luôn có duplicate”

Một PUBLISH QoS 1 bình thường có thể được nhận đúng một lần. **Duplicate là khả năng**, không phải hệ thống bắt buộc giao lại tất cả messages. Dữ liệu business quan trọng nên thiết kế chống trùng trước khi sự cố thực sự xảy ra, không đợi log có DUP flag mới làm.

### 4.2. QoS publisher và subscriber khác nhau

Publisher gửi QoS 1 nhưng subscriber subscribe filter ở QoS 0 thì chặng broker → subscriber có thể được giao với QoS 0. Không thể nhìn QoS publisher rồi khẳng định QoS delivery của subscriber. Hơn nữa, các subscriptions chồng lấp và chính sách broker có thể tạo thêm delivery; phải test đúng topology.

## 5. QoS 2: exactly once **ở tầng giao thức**, không ở database

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    P->>B: PUBLISH QoS 2, packetId=57
    B-->>P: PUBREC
    P->>B: PUBREL
    B-->>P: PUBCOMP
    Note over P,B: Một MQTT QoS 2 publication hoàn tất handshake
~~~

QoS 2 cung cấp cơ chế giao nhận đúng một lần của **một publication** theo MQTT session/handshake. Thế nhưng không có transaction chung với Spring handler, PostgreSQL, file/SFTP hay REST API.

Ví dụ:

~~~text
Publisher gọi PUBLISH(commandId=cmd-1001, QoS 2)
→ handshake hoàn tất.

Process publisher crash trước khi ghi trạng thái gửi vào DB.
→ Outbox worker chạy lại, gọi một PUBLISH mới
  với commandId=cmd-1001, QoS 2.
→ Broker nhìn thấy hai PUBLISH operations khác nhau.
→ Device vẫn cần kiểm tra commandId trước khi bật thiết bị.
~~~

Như vậy QoS 2 **không thay thế** idempotency. Nó cũng làm tăng số control packets và protocol state so với QoS 1, nên chọn dựa trên SLA, broker/client support và benchmark thực tế.

### 5.1. Ma trận so sánh

| QoS | Ý nghĩa ở tầng MQTT | Có thể mất? | Có thể xuất hiện trùng nghiệp vụ? |
| ---: | --- | --- | --- |
| 0 | At most once, không có broker PUBACK. | Có. | Có, nếu producer/application tạo lại PUBLISH. |
| 1 | At least once, có `PUBACK`. | Protocol hướng tới giao nhận có ACK; vẫn phụ thuộc storage, session, kết nối và application. | **Có**, do retransmission, retry và nhiều nguồn. |
| 2 | Exactly once cho một MQTT publication/handshake. | Bị chi phối session/broker persistence và lifecycle; không có cam kết business transaction tuyệt đối. | **Có**, nếu tạo nhiều PUBLISHes cho cùng event hoặc replay bên ngoài protocol. |

**Không phát biểu “QoS 2 = exactly-once processing ở tất cả hệ thống đích”.** Điều được bảo đảm chỉ thuộc protocol scope trong các điều kiện giao thức, không bao trùm side effects của Spring.

## 6. Nguồn gây duplicate: không chỉ MQTT retransmission

| Nguồn | Tình huống ví dụ | Cơ chế bảo vệ |
| --- | --- | --- |
| QoS 1 retransmission | PUBACK bị mất, packet có thể được gửi lại. | Event ID + idempotent handler. |
| Session recovery/offline backlog | Subscriber reconnect và nhận lại PUBLISH đang xử lý dở. | Dedup bền qua restart. |
| Application publisher retry | HTTP/outbox worker timeout rồi tạo PUBLISH mới. | Stable event ID qua retries. |
| Bridge đa broker | Cùng event đi qua hai đường bridge. | ID nguồn + namespace/tenant, loại loop. |
| Two subscriptions overlap | `sensors/#` và `sensors/+/temperature` cùng match. | Tránh overlap không cần thiết, dedup. |
| Retained snapshot | Subscribe mới nhận lại retained state. | Tách snapshot và event, version/freshness. |
| Processing retry | DB hoặc handler ném lỗi, message/inbox được replay. | Transaction + unique key. |
| Multiple app instances | Hai consumers nhận cùng event từ các subscriptions riêng. | Unique constraint chung trong DB. |
| HTTP retry trước MQTT | Client gửi hai HTTP requests tạo cùng nghiệp vụ. | Idempotency key ngay ở API. |
| Device reconnect/reboot | Device gửi lại batch telemetry chưa chắc được ghi. | Event ID được persist ở device/buffer. |

### 6.1. Một bản tin có cùng payload không nhất thiết là duplicate

~~~json
{"eventId":"evt-1001","deviceId":"device-17","celsius":26.5}
~~~

~~~json
{"eventId":"evt-1002","deviceId":"device-17","celsius":26.5}
~~~

Hai records có nhiệt độ giống nhau nhưng event IDs khác nhau có thể là hai readings thật tại hai thời điểm khác nhau. Dùng payload hash làm khóa dedup duy nhất sẽ xóa nhầm dữ liệu hợp lệ.

### 6.2. Một event ID mà nội dung khác nhau cũng là lỗi

~~~text
evt-1001 → celsius=26.5
evt-1001 → celsius=99.9
~~~

Đây là **idempotency key collision hoặc vi phạm producer contract**, không phải duplicate bình thường nên lặng lẽ bỏ qua. Khi giữ event ID cố định qua retry, producer phải giữ **ý nghĩa business và payload theo contract**; consumer có thể lưu hash/version để phát hiện trường hợp ID được tái sử dụng cho nội dung khác.

## 7. DUP flag: tín hiệu giao thức, không phải khóa dedup

MQTT PUBLISH có cờ **DUP** ở fixed header. Nó được dùng trong các trường hợp retransmission theo MQTT protocol. Tuy nhiên:

- `DUP=1` không phải một business ID; nó chỉ nói về một MQTT PUBLISH được gửi lại theo semantics giao thức, không khẳng định consumer đã xử lý payload trước đó.
- `DUP=0` không có nghĩa event nghiệp vụ là mới: hai PUBLISHes độc lập cùng `eventId` đều có thể bắt đầu với DUP=0.
- Broker nhận packet từ một publisher rồi gửi tới subscriber là **hai chặng khác nhau**; không giả định DUP flag phía publisher được chuyển nguyên vẹn thành một header downstream.
- Các Spring Integration MQTT converters/versions có thể bộc lộ metadata DUP/retained/QoS qua headers khác nhau; kiểm tra API đang dùng thay vì quyết định dedup dựa duy nhất một header không chắc chắn.

### 7.1. Vì sao dùng DUP flag để bỏ message là sai?

~~~text
if (mqttDupFlag) {
    return; // SAI nếu dựa vào đó để bỏ message
}
~~~

Một PUBLISH mang DUP=1 có thể là lần **đầu tiên** mà ứng dụng của bạn thực sự thấy, vì lần gửi ban đầu có thể chưa tới subscriber. Bỏ tất cả DUP=1 sẽ làm mất dữ liệu.

Ngược lại, `DUP=0` vẫn có thể trùng business ID với một publication trước đó. **Cần kiểm tra business identity đã persist**, không phải chỉ flag ở packet.

## 8. Packet identifier và delivery token cũng không phải business ID

MQTT packet identifier có phạm vi trong một client connection/session và được tái sử dụng sau khi protocol exchange tương ứng hoàn tất. Paho `IMqttDeliveryToken` theo dõi publish operation của client runtime; token không được serialize thành khóa bền qua restart.

| Giá trị | Dùng đúng | Sai khi dùng để... |
| --- | --- | --- |
| MQTT packet ID | Chẩn đoán handshake/ACK trong protocol context. | Primary key toàn cục của telemetry/business event. |
| Paho delivery token | Quan sát publish operation/timeout. | Định danh business message ở mọi consumer. |
| Spring `MessageHeaders.ID` | Trace Spring message instance. | Dedup mọi MQTT replay nếu ID được tạo mới khi convert. |
| `MqttHeaders.RECEIVED_TOPIC` | Xác thực topic thực nhận và parse tenant/device. | Thay thế event ID của từng PUBLISH. |
| Producer `eventId` | Định danh sự kiện nghiệp vụ xuyên retry. | Tin tuyệt đối khi chưa validate nguồn/tenant và tính nhất quán payload. |

### 8.1. Thiết kế eventId bền vững

Một telemetry event nên mang ID do producer cấp **khi event được tạo** và giữ không đổi trên mọi attempt:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-device17-000001",
  "tenantId": "tenant-a",
  "deviceId": "device-17",
  "sequence": 1001,
  "celsius": 26.5
}
~~~

Nếu thiết bị reboot, không reset bộ đếm để tái sử dụng cùng ID cho event mới. Có thể dùng UUID/ULID hoặc `deviceId + bootEpoch + sequence`; cần bảo đảm tính duy nhất trong namespace, quản lý clock và persistence. Một timestamp đơn lẻ không đủ nếu đồng hồ bị lệch hoặc hai events sinh cùng mili giây.

## 9. Retained, session, resubscribe: vì sao đọc lại chưa chắc là lỗi?

MQTT 3.1.1 hỗ trợ **retained message** và **persistent session**. Hai cơ chế khác nhau:

| Cơ chế | Broker lưu gì? | Tác động đến consumer |
| --- | --- | --- |
| Retained | Snapshot PUBLISH cuối cùng trên mỗi topic theo policy. | Subscriber mới có thể nhận lại snapshot ngay khi subscribe. |
| `cleanSession=false` | Subscription/session và message liên quan QoS 1/2 theo protocol/broker policy. | Subscriber có thể nhận pending/offline messages sau reconnect. |
| QoS 1 in-flight | Giao thức theo dõi PUBLISH/PUBACK chưa hoàn tất. | Redelivery có thể xảy ra. |
| Outbox/inbox ứng dụng | Business records mà chính app persist. | Application có khả năng reconcile/retry/skip duplicate qua restart. |

Không xem retained `ONLINE` gửi lại sau subscribe là một event “thiết bị vừa online lúc này”. Nó là **snapshot broker**. Nếu muốn event log không trùng, phải định nghĩa schema riêng, độ mới của dữ liệu và cách xử lý retained.

### 9.1. QoS và subscription filters chồng lấp

Một subscriber có thể đăng ký:

~~~text
sensors/#
sensors/+/temperature
~~~

Cùng một PUBLISH vào `sensors/device-17/temperature` match cả hai. Theo MQTT 3.1.1, broker có thể giao các bản sao tương ứng trong trường hợp matching subscriptions overlap. Do đó, ngay cả khi publisher chỉ gửi một lần, consumer vẫn cần sẵn sàng cho tình huống duplicate.

### 9.2. Multi-instance và Client ID

Hai app instances có **Client ID khác nhau** subscribe filter thông thường có thể **cùng nhận** một event: fan-out theo subscriber, không phải competing queue. Chúng có thể ghi trùng vào cùng DB nếu không có unique constraint.

Hai active clients **dùng cùng Client ID** có thể đá connection của nhau; đó **không** phải kỹ thuật chia tải. Nếu broker hỗ trợ shared subscriptions, dùng cơ chế đó theo version/broker ACL, nhưng vẫn cần idempotency vì side effects có thể retry hoặc application publish lại.

## 10. Bắt đầu từ hợp đồng business: chọn khóa idempotency

Một khóa tốt phải trả lời: “Đây có phải cùng một **business event** trước đó không?”, không phải “bytes có giống nhau không?”. Trong môi trường nhiều tenant, ví dụ:

~~~text
Idempotency key = (tenantId, eventId)
Topic namespace  = tenants/{tenantId}/devices/{deviceId}/temperature
Business contract = eventId ổn định qua mọi retry của cùng reading
~~~

Nếu thiết bị chỉ bảo đảm `eventId` unique trong từng device, khóa phải mở rộng thành `(tenantId, deviceId, eventId)`. Chọn scope chính xác theo guarantee thực của producer, không tự ý coi một ID ngắn là unique toàn bộ công ty.

### 10.1. Không dùng hash payload làm ID chính

Hai readings có cùng bytes có thể là hai measurements hợp lệ. Hash payload hữu ích để **kiểm tra collision** khi cùng `eventId` được gửi với nội dung khác, không nên thay thế ID nguồn. Nếu application không có event ID, cần bổ sung vào schema/publisher; mọi heuristic như topic + timestamp + hash đều có nguy cơ bỏ sai event hoặc không bắt được retry.

### 10.2. Vì sao cần verify topic và identity trước dedup?

Một publisher không được phép có thể cố phát message với `eventId` trùng một device khác và làm processor bỏ nhầm dữ liệu của device thật. Phải xác thực broker principal/topic ACL và đối chiếu `tenantId`, `deviceId` từ topic với payload/owner, rồi mới quyết định idempotency key.

### 10.3. Dedup window là một quyết định nghiệp vụ

Nếu lưu mọi event IDs mãi, DB sẽ tăng không giới hạn. Nếu TTL chỉ 24 giờ nhưng outbox có thể replay event cũ sau 7 ngày, duplicate vẫn có thể tạo side effect trở lại. Quyết định retention cần dựa trên:

- Thời gian replay tối đa ở publisher/outbox.
- Broker session/backlog/retained behavior.
- Chính sách backfill/reprocessing, incident recovery.
- SLA và rủi ro của side effects (thanh toán, điều khiển thiết bị).
- Khả năng lưu compacted event IDs và snapshots.

**Không xóa idempotency records sớm hơn khả năng cùng business event quay lại** nếu nghiệp vụ đòi kết quả “một lần” lâu dài. Đối với dữ liệu lịch sử, có thể dùng partition/archival và chính sách reconcile riêng.


## 11. Cơ chế dedup bền vững: unique constraint và một transaction

Mẫu đơn giản nhưng hiệu quả khi ghi vào PostgreSQL:

~~~mermaid
sequenceDiagram
    participant IN as Spring inbound flow
    participant DB as PostgreSQL
    IN->>DB: BEGIN
    IN->>DB: INSERT (tenantId,eventId) ON CONFLICT DO NOTHING
    alt ID mới
        DB-->>IN: inserted=1
        IN->>DB: INSERT business reading
        IN->>DB: COMMIT
    else ID đã tồn tại
        DB-->>IN: inserted=0
        IN->>DB: Đối chiếu payload hash / owner
        IN->>DB: COMMIT không tạo side effect mới
    end
~~~

### 11.1. Schema PostgreSQL minh họa

~~~sql
CREATE TABLE IF NOT EXISTS processed_mqtt_events (
    tenant_id       VARCHAR(64) NOT NULL,
    event_id        VARCHAR(128) NOT NULL,
    device_id       VARCHAR(64) NOT NULL,
    payload_sha256  CHAR(64) NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id)
);

CREATE TABLE IF NOT EXISTS telemetry_readings (
    tenant_id       VARCHAR(64) NOT NULL,
    event_id        VARCHAR(128) NOT NULL,
    device_id       VARCHAR(64) NOT NULL,
    sequence_no     BIGINT NOT NULL,
    celsius         NUMERIC(8, 2) NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_telemetry_device
    ON telemetry_readings(tenant_id, device_id, sequence_no);
~~~

`processed_mqtt_events` đóng vai trò **idempotency ledger**. `telemetry_readings` là side effect nghiệp vụ lưu các measurements. Khóa chính `(tenant_id,event_id)` bảo đảm hai threads/instances không thể đồng thời commit hai entries với cùng key.

Trong transaction, ứng dụng làm:

~~~sql
INSERT INTO processed_mqtt_events
    (tenant_id, event_id, device_id, payload_sha256)
VALUES
    ('tenant-a', 'evt-1001', 'device-17', 'example-hash')
ON CONFLICT (tenant_id, event_id) DO NOTHING;
~~~

Nếu không có conflict, insert trả **1 row affected**; side effect được thực hiện trong **cùng transaction**. Nếu đã tồn tại, insert trả **0**, không tạo side effect mới và có thể kiểm tra hash của event cũ.

**Quan trọng:** `example-hash` chỉ là placeholder cho SQL minh họa; Java processor phía dưới sẽ tạo hash SHA-256 hex thật. Không dùng một giá trị hash cố định trong production.

### 11.2. Vì sao “SELECT rồi INSERT” không đủ?

Sai lầm phổ biến:

~~~text
Thread A: SELECT eventId=evt-1001 → chưa có
Thread B: SELECT eventId=evt-1001 → chưa có
Thread A: UPDATE business counter +1
Thread B: UPDATE business counter +1
Thread A/B: INSERT event ID
~~~

Hai threads cùng thấy “chưa có” trước khi một thread insert. Nếu không có unique constraint và transaction, counter có thể tăng hai lần.

Mẫu `INSERT ... ON CONFLICT DO NOTHING` để database giải quyết race. Đừng thay bằng `ConcurrentHashMap` nếu có nhiều JVM instances hoặc cần tồn tại qua restart.

### 11.3. Điều kiện atomicity và giới hạn

Nếu insert idempotency key đã commit **trước** khi ghi business reading trong một transaction khác, sau đó business write thất bại, các lần replay sẽ bị chặn dù side effect chưa xảy ra. Vì thế **idempotency record và DB business write phải commit hoặc rollback cùng nhau**.

Nếu side effect đi ra **ngoài** cùng database (HTTP, Kafka, gửi email, điều khiển thiết bị), transaction PostgreSQL không thể commit atomic với hệ thống đó. Cần transactional outbox cho bước phát ra ngoài và **idempotent consumer** tại đích, hoặc giao thức reconciliation/fencing phù hợp.

### 11.4. Hash có ý nghĩa gì?

Hash của raw bytes giúp phát hiện producer tái dùng một `eventId` cho nội dung khác. Trong một contract nghiêm ngặt, cùng key nhưng payload SHA-256 khác cần đưa vào quarantine/audit.

Tuy nhiên, nếu producer có thể thay đổi serialization của cùng sự kiện (khoảng trắng JSON khác), raw hash có thể khác dù field nghiệp vụ không đổi. Khi đó phải định nghĩa **canonical representation** hoặc lưu/so sánh một business fingerprint đã chuẩn hóa, không vội coi đó là tấn công. Bài này chọn policy **retry phải giữ raw payload ổn định** để đơn giản hóa.

## 12. Kiến trúc Spring Integration cho inbound idempotency

~~~mermaid
flowchart LR
    DEV["Thiết bị / publisher"]
    B[("MQTT broker")]
    AD["MqttPahoMessageDrivenChannelAdapter<br/>QoS=1"]
    RAW["DefaultPahoMessageConverter<br/>payloadAsBytes=true"]
    CH["mqtt.telemetry.raw"]
    FLOW["IntegrationFlow<br/>validate topic + JSON"]
    SVC["TelemetryProcessor<br/>@Transactional"]
    LEDGER[("processed_mqtt_events")]
    READ[("telemetry_readings")]
    ERR["Error/quarantine"]
    DEV --> B --> AD --> RAW --> CH --> FLOW --> SVC
    SVC --> LEDGER
    SVC --> READ
    FLOW -. "invalid bytes/schema/topic" .-> ERR
    SVC -. "DB unavailable" .-> ERR
~~~

**Phân tách trách nhiệm:**

1. MQTT broker và Paho quản lý subscription/delivery/QoS.
2. `MqttPahoMessageDrivenChannelAdapter` chuyển PUBLISH thành Spring `Message<byte[]>`.
3. Spring `MessageChannel` đưa message vào `IntegrationFlow`.
4. Flow kiểm tra **received topic**, parse JSON và đối chiếu tenant/device ID.
5. `TelemetryProcessor` gắn với database transaction, dedup key và business write.
6. Lỗi cố định vào quarantine; lỗi DB tạm thời cần policy retry/replay bền vững theo SLA.
7. Nếu downstream khác database cần event, dùng outbox ghi chung DB transaction.

Không yêu cầu viết một `@Poller` để hỏi MQTT broker: inbound adapter là **message-driven**. Chỉ khi tự đặt `QueueChannel` trong nội bộ Spring thì downstream cần poller/consumer lấy message từ queue.

### 12.1. Vì sao giữ raw bytes?

Một MQTT payload có thể là JSON UTF-8, protobuf hoặc binary format khác. Trong bài này, cấu hình converter `setPayloadAsBytes(true)` giúp:

- Biết kích thước bytes trước khi parse.
- Tính payload hash trên dữ liệu **thực nhận**.
- Tránh một vòng text decode/re-encode làm thay bytes.
- Có thể lưu raw bytes theo chính sách quarantine khi schema invalid.

Jackson đọc JSON trực tiếp từ `byte[]`. MQTT topic name và QoS/retained vẫn thuộc headers/transport metadata, không phải JSON tự sinh từ broker.

## 13. Ví dụ Spring Boot đầy đủ: nhận MQTT và chống trùng bằng PostgreSQL

**Bối cảnh:** tenant-a có nhiều cảm biến. Chúng publish theo topic:

~~~text
tenants/tenant-a/devices/device-17/temperature
tenants/tenant-a/devices/device-21/temperature
~~~

Subscription filter của backend:

~~~text
tenants/tenant-a/devices/+/temperature
~~~

Payload JSON được thống nhất:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-device17-000001",
  "tenantId": "tenant-a",
  "deviceId": "device-17",
  "sequence": 1001,
  "celsius": 26.5
}
~~~

Hai lần nhận cùng `eventId` và cùng payload phải **tạo tối đa một row** trong `telemetry_readings`. Nếu cùng ID nhưng nội dung khác, processor ném lỗi **collision** theo contract. Nếu một publisher gửi hai events khác ID nhưng cùng `celsius`, cả hai readings được ghi.

Ví dụ dùng Java 17+, Spring Boot, Spring Integration MQTT/Paho MQTT v3, Jackson, Spring JDBC và PostgreSQL. H2/in-memory DB có cú pháp upsert/locking khác, nên **không** giả định SQL PostgreSQL này chạy nguyên dạng trên mọi database.

### 13.1. Maven dependencies

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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
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

Dùng Spring Boot BOM tương thích để quản lý versions. MQTT broker và PostgreSQL cần được **khởi động riêng** và có credentials/quyền tương ứng; Spring Boot không tự tạo broker. Không chạy demo SQL trên production database khi chưa phê duyệt schema và migration.

### 13.2. Cấu trúc mã

~~~text
src/main/java/demo/mqttdedup/
    MqttDedupApplication.java
    TelemetryEvent.java
    DedupOutcome.java
    TelemetryProcessor.java
    JdbcTelemetryProcessor.java
    MqttDedupTransportConfiguration.java
    MqttDedupFlowConfiguration.java

src/main/resources/
    application.properties
    schema.sql

src/test/java/demo/mqttdedup/
    MqttDedupFlowTest.java
~~~

Mọi class trong ví dụ thuộc package `demo.mqttdedup`. Class public phải nằm trong file trùng tên; các helper class có thể package-private để test trực tiếp.

### 13.3. Spring Boot application

~~~java
package demo.mqttdedup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttDedupApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttDedupApplication.class, args);
    }
}
~~~

### 13.4. application.properties

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}
app.mqtt.client-id=${MQTT_CLIENT_ID:tenant-a-telemetry-local-1}
app.mqtt.tenant-id=tenant-a

spring.datasource.url=${DB_URL:jdbc:postgresql://localhost:5432/mqtt_lab}
spring.datasource.username=${DB_USER:mqtt_demo}
spring.datasource.password=${DB_PASSWORD}

# Chỉ cho môi trường lab với schema.sql đã được review.
spring.sql.init.mode=always
~~~

Trong production, dùng migration tool/quản trị schema thay vì để nhiều replicas cùng tự chạy schema initialization, và lấy secrets từ hạ tầng cấu hình bảo mật. Broker external nên dùng TLS, broker cert verification và ACL, không dùng TCP plaintext như local lab.

Tệp `schema.sql` chứa DDL PostgreSQL ở mục 11. Với `spring.sql.init.mode=always`, Spring Boot thực thi script khi khởi động theo chính sách initialization; cần DB user có quyền DDL trong lab. Trong production nên tách migration permissions khỏi runtime user.

### 13.5. Business DTO

~~~java
package demo.mqttdedup;

import java.math.BigDecimal;

record TelemetryEvent(
        int schemaVersion,
        String eventId,
        String tenantId,
        String deviceId,
        long sequence,
        BigDecimal celsius) {

    TelemetryEvent {
        if (schemaVersion != 1) {
            throw new IllegalArgumentException(
                    "Schema version chưa hỗ trợ");
        }
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,128}")) {
            throw new IllegalArgumentException("eventId không hợp lệ");
        }
        if (tenantId == null
                || !tenantId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("tenantId không hợp lệ");
        }
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("deviceId không hợp lệ");
        }
        if (sequence < 0) {
            throw new IllegalArgumentException("sequence âm");
        }
        if (celsius == null
                || celsius.compareTo(new BigDecimal("-80")) < 0
                || celsius.compareTo(new BigDecimal("150")) > 0) {
            throw new IllegalArgumentException(
                    "Nhiệt độ không hợp lệ");
        }
    }
}
~~~

Nhiệt độ -80..150 và cấu trúc ID là **business constraints minh họa**, không phải quy tắc MQTT. Nếu firmware gửi schema khác, cần versioned decoder/contract, không chỉ tăng wildcard subscription.

### 13.6. Processor interface và kết quả

~~~java
package demo.mqttdedup;

enum DedupOutcome {
    NEW_EVENT,
    DUPLICATE_IGNORED
}

interface TelemetryProcessor {
    DedupOutcome accept(TelemetryEvent event, byte[] rawPayload);
}
~~~

Tách interface giúp test flow không phải mở PostgreSQL, trong khi implementation production có thể dùng JDBC transaction với unique constraint.

### 13.7. JDBC processor: dedup và side effect trong cùng transaction

~~~java
package demo.mqttdedup;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
class JdbcTelemetryProcessor implements TelemetryProcessor {

    private final JdbcTemplate jdbc;

    JdbcTelemetryProcessor(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional
    public DedupOutcome accept(
            TelemetryEvent event, byte[] rawPayload) {

        String hash = sha256(rawPayload);

        int inserted = jdbc.update("""
                INSERT INTO processed_mqtt_events
                    (tenant_id, event_id, device_id, payload_sha256)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (tenant_id, event_id) DO NOTHING
                """,
                event.tenantId(), event.eventId(),
                event.deviceId(), hash);

        if (inserted == 0) {
            String previousHash = jdbc.queryForObject("""
                    SELECT payload_sha256
                    FROM processed_mqtt_events
                    WHERE tenant_id = ? AND event_id = ?
                    """,
                    String.class,
                    event.tenantId(), event.eventId());

            if (!hash.equals(previousHash)) {
                throw new IllegalStateException(
                        "Event ID đã tồn tại nhưng nội dung khác");
            }
            return DedupOutcome.DUPLICATE_IGNORED;
        }

        jdbc.update("""
                INSERT INTO telemetry_readings
                    (tenant_id, event_id, device_id,
                     sequence_no, celsius)
                VALUES (?, ?, ?, ?, ?)
                """,
                event.tenantId(), event.eventId(),
                event.deviceId(), event.sequence(),
                event.celsius());

        return DedupOutcome.NEW_EVENT;
    }

    private static String sha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest
                    .getInstance("SHA-256")
                    .digest(bytes);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "JVM thiếu SHA-256", ex);
        }
    }
}
~~~

**Độ tin cậy của cơ chế này nằm ở database unique constraint và transaction**, không nằm ở `if (eventIdAlreadySeen)` trên Java heap. Hai threads có thể chạy đồng thời; PostgreSQL giải quyết unique key conflict và transaction sẽ commit hoặc rollback cả key lẫn reading.

Giả định triển khai:

- PostgreSQL dùng isolation phù hợp, phổ biến `READ COMMITTED`; test concurrency dưới load/reconnect thực.
- DB connection pool và transaction management của Spring được cấu hình đúng.
- `@Transactional` áp dụng khi gọi public method qua Spring bean/proxy, không tự gọi nội bộ khiến advice bị bỏ qua.
- Raw bytes retry của cùng event giữ ổn định theo data contract; nếu khác representation hợp lệ, thay hash policy bằng canonical business fingerprint.
- Side effect hiện tại chỉ ghi **cùng PostgreSQL database**. Nếu gửi HTTP/Kafka/JMS ngay bên trong transaction thì không có atomic guarantee xuyên hệ thống.
- DB errors phải được phân loại là transient/nontransient; việc ném exception từ service không tự tạo MQTT durable redelivery.

### 13.8. Tại sao insert key trước reading và cùng transaction?

Nếu insert reading thành công rồi application crash trước khi ghi idempotency key trong transaction **khác**, replay có thể tạo duplicate side effect. Nếu insert key trước trong transaction khác rồi reading lỗi, replay bị chặn sai. Một `@Transactional` bao trùm **hai INSERTs** là yếu tố trọng tâm.

Khi `ON CONFLICT DO NOTHING` trả 0, việc query hash giúp phân biệt retry cùng payload với một event ID bị dùng lại cho payload khác. Khi hash khác, ném exception để hệ thống quarantine/điều tra, không tự ghi đè row cũ.

### 13.9. QoS và DB idempotency là hai lớp bổ trợ

Dù MQTT input QoS 1 hay 2, Spring flow nên xử lý theo business event ID. QoS 1 có thể redeliver; QoS 2 cũng không bảo vệ khỏi outbox producer phát hai publications độc lập hoặc consumer nhận retained/replay từ nguồn khác. Unique constraint đóng vai trò bảo vệ kết quả ở database.


### 13.10. TopicScope: nhận diện tenant/device từ topic thực

~~~java
package demo.mqttdedup;

record TopicScope(String tenantId) {

    TopicScope {
        if (tenantId == null
                || !tenantId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("tenantId không hợp lệ");
        }
    }

    String subscriptionFilter() {
        return "tenants/" + tenantId
                + "/devices/+/temperature";
    }

    String requireDeviceId(Object receivedTopic) {
        if (!(receivedTopic instanceof String topic)) {
            throw new IllegalArgumentException("Thiếu received topic");
        }

        String[] parts = topic.split("/", -1);
        if (parts.length != 5
                || !"tenants".equals(parts[0])
                || !tenantId.equals(parts[1])
                || !"devices".equals(parts[2])
                || !parts[3].matches("[A-Za-z0-9_-]{1,64}")
                || !"temperature".equals(parts[4])) {
            throw new IllegalArgumentException(
                    "Topic không thuộc tenant/device hợp lệ: " + topic);
        }
        return parts[3];
    }
}
~~~

`TopicScope` kiểm tra **topic name thực nhận**, không phải subscription filter. MQTT `+` có thể match một cấp topic rỗng như `devices//temperature`; business validator ở đây từ chối device ID rỗng.

### 13.11. Inbound MessageChannel và IntegrationFlow

~~~java
package demo.mqttdedup;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class MqttDedupFlowConfiguration {

    @Bean(name = "mqtt.telemetry.raw")
    MessageChannel rawTelemetryInput() {
        return new DirectChannel();
    }

    @Bean
    TopicScope topicScope(
            @Value("${app.mqtt.tenant-id}") String tenantId) {
        return new TopicScope(tenantId);
    }

    @Bean
    ObjectMapper mqttPayloadMapper() {
        return new ObjectMapper();
    }

    @Bean
    IntegrationFlow rawTelemetryFlow(
            TopicScope topicScope,
            ObjectMapper mqttPayloadMapper,
            TelemetryProcessor processor) {

        return IntegrationFlow.from("mqtt.telemetry.raw")
                .handle(byte[].class, (raw, headers) -> {
                    if (raw.length == 0 || raw.length > 16_384) {
                        throw new IllegalArgumentException(
                                "Payload size không hợp lệ");
                    }

                    String deviceId = topicScope.requireDeviceId(
                            headers.get(MqttHeaders.RECEIVED_TOPIC));

                    final TelemetryEvent event;
                    try {
                        event = mqttPayloadMapper.readValue(
                                raw, TelemetryEvent.class);
                    } catch (JsonProcessingException ex) {
                        throw new IllegalArgumentException(
                                "Không parse được telemetry JSON", ex);
                    }

                    if (!topicScope.tenantId().equals(event.tenantId())
                            || !deviceId.equals(event.deviceId())) {
                        throw new IllegalArgumentException(
                                "Topic và payload khác tenant/device");
                    }

                    // Transaction nằm trong processor bean.
                    processor.accept(event, raw);
                    return null; // Inbound one-way
                })
                .get();
    }
}
~~~

Các ranh giới:

1. Converter inbound chọn `byte[]`, do đó handler sử dụng `.handle(byte[].class, ...)`.
2. Kiểm byte length **trước** khi parse; JSON parser không tự giới hạn topic/device.
3. `MqttHeaders.RECEIVED_TOPIC` cho biết topic **thực nhận**; không dùng `MqttHeaders.TOPIC` outbound để thay thế.
4. So sánh `tenantId`, `deviceId` ở topic với JSON trước khi ghi idempotency record.
5. `TelemetryProcessor.accept(...)` được gọi qua bean Spring, để `@Transactional` có hiệu lực theo proxy configuration.
6. `return null` biểu thị endpoint một chiều.
7. Code demo chưa có durable quarantine/error policy production; cần triển khai như mục 18.

### 13.12. Cấu hình MQTT inbound adapter

~~~java
package demo.mqttdedup;

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
class MqttDedupTransportConfiguration {

    @Bean
    MqttPahoClientFactory mqttClientFactory(
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
    MqttPahoMessageDrivenChannelAdapter mqttTelemetryAdapter(
            MqttPahoClientFactory mqttClientFactory,
            TopicScope topicScope,
            @Qualifier("mqtt.telemetry.raw") MessageChannel output,
            @Value("${app.mqtt.client-id}") String clientId) {

        var converter = new DefaultPahoMessageConverter();
        converter.setPayloadAsBytes(true);

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, mqttClientFactory,
                topicScope.subscriptionFilter());

        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(converter);
        adapter.setOutputChannel(output);
        return adapter;
    }
}
~~~

`setQos(1)` là QoS của **subscription** đối với chặng broker → subscriber; QoS publish của thiết bị là một giá trị độc lập. `cleanSession=false` minh họa persistent session MQTT 3.1.1. Để phục hồi session, Client ID phải ổn định qua restart, nhưng **không được dùng cùng ID cho hai active replicas**.

Trong ví dụ tắt Paho auto reconnect và dùng recovery interval của inbound adapter nhằm minh họa một chiến lược phục hồi. Hành vi thực tế phải test trên Spring Integration/Paho version của dự án trước khi phối hợp nhiều cơ chế reconnect.

### 13.13. Giới hạn bảo đảm của demo

Nếu broker giao lại đúng raw message với `eventId=evt-device17-000001`, PostgreSQL unique constraint bảo đảm tối đa một ledger row và một telemetry reading được commit theo processor.

Nhưng một database dedup processor **không tự bảo đảm MQTT message không bị mất** khi Paho/client/broker đã ACK trước DB commit hoặc không còn replay source sau crash. Idempotency giải quyết duplicate side effects; durability và delivery guarantee đòi hỏi thiết kế acknowledgement/inbox/broker storage riêng.

## 14. Khi nào cần manual acknowledgement?

~~~mermaid
sequenceDiagram
    participant B as MQTT broker
    participant C as Paho / inbound adapter
    participant F as Spring flow
    participant DB as PostgreSQL
    B->>C: PUBLISH QoS 1
    C->>F: Message<byte[]>
    F->>DB: Dedup + business write
    DB-->>F: COMMIT
    Note over B,DB: MQTT ACK timing phụ thuộc Paho/Spring configuration
    C-->>B: ACK theo client/adapter mode
~~~

**Sơ đồ diễn giải ranh giới**, không khẳng định default adapter luôn trì hoãn PUBACK đến sau DB commit. Với QoS, callback, converter và Spring version khác nhau, ACK timing có thể khác. Không suy ra exception ném từ handler sẽ tự rollback một PUBACK đã gửi.

### 14.1. Manual ACK tùy phiên bản adapter

Một số Spring Integration MQTT inbound adapter versions hỗ trợ manual acknowledgments:

~~~java
// Chỉ dùng khi version hỗ trợ và đã kiểm chứng callback contract.
adapter.setManualAcks(true);
~~~

Khi đó ứng dụng có thể nhận acknowledgment callback qua message header/API tương ứng. Quy trình mong muốn:

~~~text
PUBLISH nhận được + acknowledgment callback
    → validate topic/bytes/schema
    → processor @Transactional ghi ledger + business side effect
    → transaction commit thành công
    → acknowledge bằng callback theo đúng API version
~~~

**Đây là pseudocode về thứ tự, không phải code callback có thể copy nguyên.** Tên callback/header, cách nhận callback, tác dụng của `acknowledge()` và lúc broker coi packet complete phải kiểm tra theo đúng dependency version. Không tự đoán header name hoặc ACK message bằng API không tồn tại.

### 14.2. Khoảng hở crash không thể xóa hết

Nếu DB đã commit nhưng process chết trước MQTT ACK, message có thể được giao lại sau recovery. Unique constraint xử lý lại an toàn. Nếu MQTT ACK đã hoàn tất trước khi DB commit và DB lỗi, message có thể bị mất trong business store. Vì vậy cần phối hợp **durable write, idempotency, ACK policy và replay** thay vì chỉ bật manual ACK rồi tuyên bố end-to-end exactly-once.

### 14.3. Poison message và manual ACK

JSON sai schema sẽ không trở nên đúng chỉ vì broker redeliver. Policy production cần quarantine/inbox đủ bền (topic, metadata, raw payload có bảo mật, reason) rồi quyết định ACK hoặc chuyển điều tra; tránh kẹt session hoặc tạo retry loop vô hạn.

## 15. Multi-instance: database là điểm đồng bộ thực

~~~mermaid
flowchart TD
    B[("MQTT broker")]
    A["Subscriber A<br/>Client ID A"]
    C["Subscriber B<br/>Client ID B"]
    DB[("PostgreSQL<br/>PRIMARY KEY tenant_id,event_id")]
    B --> A
    B --> C
    A -->|"INSERT evt-1001"| DB
    C -->|"INSERT evt-1001"| DB
~~~

Hai MQTT clients khác ID cùng subscribe một topic filter thông thường có thể đều nhận PUBLISH. Nếu chúng cùng ghi DB, `ConcurrentHashMap` riêng mỗi JVM không ngăn trùng. PostgreSQL unique constraint và transaction chung sẽ phân xử ngay cả khi hai process xử lý đồng thời.

### 15.1. Shared subscriptions không đồng nghĩa exactly once ở business

Một số broker hỗ trợ shared subscription để giao một message đến một thành viên nhóm theo chính sách broker/protocol, nhưng worker vẫn có thể crash, duplicate sau reconnect hoặc producer gửi lại cùng event. Shared subscription giảm fan-out không mong muốn; nó **không thay** business ID và idempotency.

### 15.2. Không dùng Client ID trùng để chia tải

Hai active clients dùng cùng MQTT Client ID có thể cắt kết nối của nhau, tạo reconnect loop và session khó đoán. Dùng các Client IDs riêng hoặc cơ chế shared subscription có hỗ trợ; không biến Client ID conflict thành chiến lược load balancing.

### 15.3. Cache chỉ để tối ưu

Cache memory/Redis có thể giảm một số DB queries nhưng có TTL/eviction/race, không nhất thiết cùng transaction với business writes. Với nghiệp vụ quan trọng, database uniqueness vẫn là nguồn sự thật. Nếu cache miss, correctness vẫn phải giữ nguyên.

## 16. Duplicate khác out-of-order

Dedup loại cùng business event; nó **không bảo đảm** events khác nhau đến đúng thứ tự.

~~~text
Publisher tạo:
  evt-101 sequence=101 celsius=25
  evt-102 sequence=102 celsius=26

Backend nhận:
  evt-102 trước
  evt-101 sau
~~~

Cả hai events khác ID nên được chấp nhận vào event history. Nhưng nếu cập nhật `latest_temperature` theo thứ tự callback, có thể ghi ngược 25 sau 26.

### 16.1. Event log và latest state

- **Event history:** giữ mọi unique event, không xóa một reading hợp lệ chỉ vì nó đến muộn.
- **Latest snapshot:** update có điều kiện dựa trên `sequence + bootEpoch` hoặc một ordering policy đáng tin cậy.
- **Alert stream:** có thể cần watermark, debounce và event-time validation để tránh cảnh báo lặp/out-of-order.

Ví dụ SQL về latest snapshot (cần tạo table và contract sequence riêng trước khi dùng):

~~~sql
INSERT INTO device_latest_temperature
    (tenant_id, device_id, sequence_no, celsius)
VALUES (:tenant_id, :device_id, :sequence_no, :celsius)
ON CONFLICT (tenant_id, device_id)
DO UPDATE SET
    sequence_no = EXCLUDED.sequence_no,
    celsius = EXCLUDED.celsius
WHERE device_latest_temperature.sequence_no < EXCLUDED.sequence_no;
~~~

Không dùng `sequence` thuần nếu device reset về 0 khi reboot và có thể gây overwrite sai; đưa `bootEpoch`/generation và quy tắc so sánh vào hợp đồng.

### 16.2. Duplicate command có thể cần gửi lại ACK

Nếu device thấy `commandId` đã thực thi trước đó, nó nên **không chạy lại side effect**, nhưng có thể publish lại business ACK cũ để giúp publisher reconcile. “Idempotent” không nhất thiết nghĩa là không phát bất kỳ phản hồi nào khi duplicate; đó là bảo toàn kết quả nghiệp vụ.


## 17. Bridge MQTT sang Kafka, JMS, HTTP, file hoặc SFTP

Nếu MQTT inbound flow cần chuyển message sang một hệ thống khác, idempotency ở PostgreSQL **chưa đủ** để bảo đảm publication ở đích.

~~~text
MQTT evt-1001 nhận được
→ DB đánh dấu processed và COMMIT
→ Java process crash trước khi publish Kafka
→ MQTT retry evt-1001, nhưng DB dedup bỏ qua
→ Kafka có thể chưa bao giờ nhận event
~~~

Ngược lại, nếu gửi Kafka/HTTP thành công rồi mới ghi dedup record, crash ở giữa có thể làm side effect bị lặp khi retry.

| Hệ thống đích | Phương án khuyến nghị |
| --- | --- |
| PostgreSQL cùng database | Ledger và business rows trong cùng transaction. |
| Kafka | Ghi **outbox event** trong DB transaction; relay publish, Kafka consumer cũng idempotent. |
| JMS/AMQP | Inbox/outbox, message ID ổn định, ACK và retry policy riêng. |
| HTTP | Idempotency key trong request contract, retry có giới hạn, timeout là outcome chưa chắc chắn. |
| File/SFTP | Tên file theo event ID, temp-file rồi rename khi phù hợp, đối soát trạng thái đích. |
| MQTT outbound command | Command ID ổn định, retained policy, ACK nghiệp vụ riêng. |
| Notification/email | Notification ID, send log/outbox và chống gửi lặp. |

### 17.1. Inbox + outbox trong một transaction

~~~mermaid
flowchart LR
    MQTT["MQTT inbound"]
    DB[("DB transaction<br/>inbox + business + outbox")]
    RELAY["Outbox relay"]
    DEST["Kafka / JMS / HTTP / SFTP"]
    MQTT --> DB --> RELAY --> DEST
    DEST -. "ACK/reconciliation" .-> RELAY
~~~

Một transaction ghi inbox event key, business effect trong DB và outbox row. Sau commit, relay gửi tới đích. Nếu relay gửi thành công rồi crash trước khi mark sent, nó có thể gửi lại; **downstream vẫn phải idempotent**.

### 17.2. Chống bridge loop

Nếu một MQTT event được bridge sang Kafka rồi Kafka consumer lại publish cùng event về source MQTT topic, có thể tạo vòng lặp. Ngoài idempotency key, cần source/origin metadata, route rõ ràng, hop limit hoặc cấu hình loại loop. Dedup trong DB không tự cắt luồng network looping.

## 18. Xử lý duplicate, collision và lỗi khác nhau

| Outcome | Ví dụ | Chính sách |
| --- | --- | --- |
| `NEW_EVENT` | Key mới, transaction commit. | Ghi side effect và đo metric new. |
| `DUPLICATE_IGNORED` | Key cũ, payload hash hợp lệ. | Không ghi side effect lần hai; có thể gửi lại ACK nghiệp vụ. |
| `INVALID_TOPIC_SCHEMA` | Sai tenant/topic, JSON malformed, thiếu event ID. | Quarantine; không retry vô hạn lỗi cố định. |
| `EVENT_ID_COLLISION` | Cùng key nhưng payload khác theo contract. | Quarantine và điều tra publisher/ACL. |
| `TRANSIENT_DB_FAILURE` | Database unavailable/deadlock. | Retry có budget/backoff từ durable source. |
| `BROKER_CONNECTION_FAILURE` | Reconnect, session state không đồng nhất. | Broker monitoring, kiểm tra subscription/replay. |

### 18.1. Duplicate hợp lệ là một kết quả xử lý thành công

Một QoS 1 redelivery cùng `eventId`/payload đã commit không nhất thiết là exception. Trả `DUPLICATE_IGNORED` và kết thúc an toàn, thay vì ném lỗi cho mọi duplicate rồi tạo log storm và retry loop.

### 18.2. Collision phải được đánh giá riêng

Một ID từng đại diện 26.5°C nhưng bây giờ gắn 99.9°C có thể là firmware reset ID, producer retry thay payload hoặc giả mạo. Trong contract byte-stable, hash khác cần quarantine/audit thay vì ghi đè record cũ.

Nếu business cho phép cùng event nhưng JSON serialization thay đổi whitespace/field order, hãy dùng fingerprint canonical thay raw SHA-256. Phải chọn rõ một chính sách và test để tránh false collision.

### 18.3. Ném exception không đồng nghĩa MQTT broker sẽ retry

Spring `IntegrationFlow` có thể gửi `ErrorMessage`/exception tới error path theo endpoint, nhưng MQTT ACK có thể đã được client gửi trước khi DB xử lý. Đừng mặc định rằng một exception Java rollback `PUBACK`. Khi cần delivery guarantee mạnh, phải kiểm tra manual ACK timing, session, durable inbox hoặc một nguồn có khả năng replay theo deployment thực tế.

### 18.4. Quarantine và an toàn dữ liệu

Record lưu trữ lỗi nên có `receivedTopic`, business ID nếu parse được, `reasonCode`, byte length, receive time và secure raw payload reference. Hạn chế retention, mã hóa dữ liệu, ACL và không log toàn bộ PII/secret. Không publish lại poison message về chính source topic vô hạn.

## 19. Test flow không cần MQTT broker

Test không broker có thể xác minh topic/JSON/dedup contract bằng `@SpringJUnitConfig` chỉ nạp `MqttDedupFlowConfiguration` và fake `TelemetryProcessor`. Nó **không** chứng minh broker retransmission hay DB transaction.

### 19.1. Fake processor có thể đọc trong test

~~~java
package demo.mqttdedup;

import java.util.Arrays;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

class InMemoryTestTelemetryProcessor
        implements TelemetryProcessor {

    private final Map<String, byte[]> seen =
            new ConcurrentHashMap<>();

    @Override
    public DedupOutcome accept(TelemetryEvent event, byte[] raw) {
        String key = event.tenantId() + ":" + event.eventId();
        byte[] previous = seen.putIfAbsent(key, raw.clone());

        if (previous == null) {
            return DedupOutcome.NEW_EVENT;
        }
        if (!Arrays.equals(previous, raw)) {
            throw new IllegalStateException("Collision trong test");
        }
        return DedupOutcome.DUPLICATE_IGNORED;
    }

    int uniqueEvents() {
        return seen.size();
    }

    void clear() {
        seen.clear();
    }
}
~~~

Fake này có thể chịu được concurrent map operations trong một JVM nhưng **không có durability**; không dùng thay unique constraint PostgreSQL trong hệ thống thật.

### 19.2. JUnit flow test

~~~java
package demo.mqttdedup;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        MqttDedupFlowConfiguration.class,
        DedupTestBeans.class
})
@TestPropertySource(properties = "app.mqtt.tenant-id=tenant-a")
class MqttDedupFlowTest {

    @Autowired
    @Qualifier("mqtt.telemetry.raw")
    MessageChannel input;

    @Autowired
    InMemoryTestTelemetryProcessor processor;

    @BeforeEach
    void reset() {
        processor.clear();
    }

    private static byte[] event(String id, String celsius) {
        String json = "{\"schemaVersion\":1,"
                + "\"eventId\":\"" + id + "\","
                + "\"tenantId\":\"tenant-a\","
                + "\"deviceId\":\"device-17\","
                + "\"sequence\":1001,"
                + "\"celsius\":" + celsius + "}";
        return json.getBytes(StandardCharsets.UTF_8);
    }

    private boolean send(byte[] bytes, String topic) {
        return input.send(MessageBuilder.withPayload(bytes)
                .setHeader(MqttHeaders.RECEIVED_TOPIC, topic)
                .build());
    }

    @Test
    void sameEventTwiceHasOnlyOneBusinessEffect() {
        String topic =
                "tenants/tenant-a/devices/device-17/temperature";
        byte[] payload = event("evt-1001", "26.5");

        assertTrue(send(payload, topic));
        assertTrue(send(payload, topic));
        assertEquals(1, processor.uniqueEvents());
    }

    @Test
    void sameTemperatureButDifferentIdsAreBothValid() {
        String topic =
                "tenants/tenant-a/devices/device-17/temperature";

        send(event("evt-1001", "26.5"), topic);
        send(event("evt-1002", "26.5"), topic);
        assertEquals(2, processor.uniqueEvents());
    }

    @Test
    void sameIdWithDifferentPayloadIsCollision() {
        String topic =
                "tenants/tenant-a/devices/device-17/temperature";

        send(event("evt-1001", "26.5"), topic);

        assertThrows(RuntimeException.class, () ->
                send(event("evt-1001", "99.9"), topic));
        assertEquals(1, processor.uniqueEvents());
    }

    @Test
    void wrongTenantIsRejectedBeforeSideEffect() {
        assertThrows(RuntimeException.class, () ->
                send(event("evt-1001", "26.5"),
                        "tenants/tenant-b/devices/device-17/temperature"));
        assertEquals(0, processor.uniqueEvents());
    }

    @Test
    void malformedJsonIsRejected() {
        String topic =
                "tenants/tenant-a/devices/device-17/temperature";
        assertThrows(RuntimeException.class, () ->
                send("{\"eventId\":".getBytes(StandardCharsets.UTF_8),
                        topic));
        assertEquals(0, processor.uniqueEvents());
    }
}

@Configuration
class DedupTestBeans {

    @Bean
    InMemoryTestTelemetryProcessor telemetryProcessor() {
        return new InMemoryTestTelemetryProcessor();
    }
}
~~~

Với `DirectChannel`, handler thực hiện đồng bộ trong các test này. `assertThrows(RuntimeException.class)` không khóa cứng lớp wrapper messaging exception của một Spring Integration version; khi QA chuyên sâu cần assert cause/errorChannel.

### 19.3. Giới hạn của no-broker test

| Cấp kiểm thử | Có thể chứng minh | Chưa chứng minh |
| --- | --- | --- |
| No-broker Spring flow | JSON/received topic/ID/branching. | MQTT ACK, Paho callback, broker QoS. |
| PostgreSQL integration | Unique key, rollback, transaction, concurrency. | MQTT protocol retransmission. |
| Broker end-to-end | Subscription, reconnect, QoS behavior trong lab. | Tất cả network failures và exactly-once ở external systems. |

**Test duplicate bằng hai lệnh gửi fake Spring Message không phải test MQTT DUP flag.** Để kiểm tra retransmission giao thức cần broker/network fault injection thực tế.


## 20. Kiểm thử PostgreSQL và MQTT broker thực tế

### 20.1. Concurrency test với PostgreSQL

Chạy một PostgreSQL test instance cô lập với DDL `processed_mqtt_events` và `telemetry_readings`. Từ **hai transactions hoặc hai service instances**, đồng thời gọi `JdbcTelemetryProcessor.accept(...)` với cùng `(tenant-a, evt-1001)` và cùng payload.

Sau khi cả hai attempts kết thúc:

~~~sql
SELECT count(*) AS ledger_count
FROM processed_mqtt_events
WHERE tenant_id = 'tenant-a' AND event_id = 'evt-1001';

SELECT count(*) AS reading_count
FROM telemetry_readings
WHERE tenant_id = 'tenant-a' AND event_id = 'evt-1001';
~~~

Kỳ vọng: `ledger_count = 1` và `reading_count = 1`. Một attempt tạo `NEW_EVENT`, attempt còn lại trả `DUPLICATE_IGNORED` nếu đều hoàn tất và cùng payload.

Kiểm thử rollback: gây exception **sau khi insert ledger nhưng trước khi insert reading** trong một transaction, xác minh không còn ledger record đã commit và retry có thể ghi cả hai. Đây là điểm thường bị bỏ sót khi chỉ test happy path.

**Chú ý:** các SQL dùng `ON CONFLICT` là PostgreSQL-specific. Nếu dùng H2/Testcontainers hay database khác, phải đảm bảo version/cú pháp tương thích; tốt nhất test concurrency bằng cùng loại database production.

### 20.2. Gửi hai MQTT publications cùng business ID

Dùng broker test do bạn kiểm soát; ví dụ Mosquitto chạy tại `localhost:1883`. Spring app đã subscribe `tenants/tenant-a/devices/+/temperature`. Mở subscriber CLI:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i dedup-observer-local-1 \
  -t 'tenants/tenant-a/devices/+/temperature' \
  -q 1 -v
~~~

Publish telemetry:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'tenants/tenant-a/devices/device-17/temperature' \
  -q 1 \
  -m '{"schemaVersion":1,"eventId":"evt-cli-1","tenantId":"tenant-a","deviceId":"device-17","sequence":1001,"celsius":26.5}'
~~~

Chạy **lại chính lệnh** đó. Có thể thấy hai MQTT publications nhưng PostgreSQL chỉ có **một** event `evt-cli-1`. Nếu DB có hai side effects, idempotency guard hoặc transaction/unique key không đúng.

**Giới hạn phép thử:** gọi CLI hai lần tạo **hai PUBLISH operations độc lập** với cùng business ID. Nó test application duplicate handling, **không** chứng minh đó là retransmission QoS 1 có DUP=1.

### 20.3. Hai events cùng nhiệt độ nhưng ID khác

Publish tương tự với `eventId=evt-cli-2` nhưng giữ nguyên `celsius=26.5`. Kỳ vọng PostgreSQL có cả `evt-cli-1` và `evt-cli-2`. Nếu bản thứ hai bị loại chỉ vì trị số nhiệt độ bằng nhau, dedup key đã sai.

### 20.4. So sánh QoS 0/1/2

Thử `mosquitto_pub -q 0`, `-q 1`, `-q 2` tương ứng, với broker/subscription QoS phù hợp. Quan sát publisher logs, client session và database:

- QoS 0 không có `PUBACK`.
- QoS 1 có `PUBACK` và có thể redelivery trong các fault scenarios.
- QoS 2 dùng `PUBREC/PUBREL/PUBCOMP`; application publisher vẫn có thể tạo PUBLISH mới cùng business ID.
- Không xem thời gian CLI kết thúc là bằng chứng business DB commit.

### 20.5. Fault injection để thấy retransmission thật

Muốn thử protocol duplicate, cần một proxy/test harness làm **PUBLISH tới broker thành công nhưng ACK về publisher bị mất/trễ**, hoặc chủ động tạo network partition ở đúng giai đoạn in-flight/session.

~~~mermaid
sequenceDiagram
    participant P as MQTT Publisher
    participant B as Broker test
    participant A as Spring inbound
    participant DB as PostgreSQL
    P->>B: PUBLISH QoS1 evt-1001
    B->>A: Delivery evt-1001
    A->>DB: BEGIN + dedup + COMMIT
    B--xP: PUBACK mất
    P->>B: Retransmit / retry
    B->>A: Event có thể được giao lại
    A->>DB: ON CONFLICT, không tạo side effect mới
~~~

**Đây là một kịch bản có thể xảy ra, không cam kết broker sẽ tạo đúng hai deliveries.** Network fault quá mạnh có thể khiến client báo `connection lost` thay vì completion timeout. Cần ghi đúng error, packet capture khi có quyền và version của broker/client.

Không ngắt MQTT broker production, không làm gián đoạn thiết bị thật. Kiểm thử lỗi nên sử dụng isolated broker/containers.

### 20.6. Ba điểm crash cần test

| Thời điểm crash | Kết quả mong muốn |
| --- | --- |
| Trước DB transaction | Chưa có business commit; nếu source có replay, event có thể được xử lý lại. |
| Sau ledger INSERT nhưng trước COMMIT | Rollback cả ledger và business write; replay không bị chặn sai. |
| Sau DB COMMIT nhưng trước MQTT ACK | Event có thể redeliver; unique constraint khiến replay không tạo effect lần hai. |

Với side effect ngoài DB như HTTP/Kafka, bổ sung test crash **sau khi publish đích nhưng trước khi mark outbox sent**, vì chính bước đó có thể tạo downstream duplicate.

### 20.7. Test matrix hoàn chỉnh

| Case | Kỳ vọng |
| --- | --- |
| New event, JSON hợp lệ | Ghi một ledger và business row. |
| Cùng ID + cùng bytes nhận 2/10 lần | Side effect chỉ một lần. |
| Cùng ID nhưng payload khác | Collision được phát hiện, không overwrite. |
| Khác ID nhưng giá trị nhiệt độ giống | Cả hai events hợp lệ được lưu. |
| Tenant/topic khác JSON | Reject trước dedup insert. |
| Payload malformed/oversize | Reject, không hết RAM hoặc retry vô hạn. |
| Hai instances ghi cùng ID | Database unique key ngăn trùng. |
| Session replay sau reconnect | Không tăng business side effect. |
| Retained message nhận lại | Phân biệt snapshot với live event. |
| Overlapping subscriptions | Loại duplicate, giảm overlap khi có thể. |
| QoS 1 lost ACK | Có thể retry, không tạo effect lặp. |
| QoS 2 + app publish hai lần | Dedup dựa business ID. |
| Database unavailable | Không commit marker sai, có retry/recovery policy. |
| Outbox relay crash sau gửi | Downstream idempotent và đối soát được. |

## 21. Security: duplicate handling không thay authorization

Một publisher không được tin cậy có thể gửi event ID đã có để khiến consumer bỏ qua dữ liệu mới, hoặc giả `deviceId` để ghi vào tenant khác. Kiểm tra idempotency chỉ có ý nghĩa sau **identity + permission validation**.

| Nguy cơ | Kiểm soát |
| --- | --- |
| Publisher giả event ID của thiết bị khác | Broker auth/TLS, topic publish ACL theo identity; business validator đối chiếu topic/tenant. |
| Subscriber nhận topic tenant khác qua `#` | Subscription ACL, filter tenant-scoped và validate `RECEIVED_TOPIC`. |
| Tái dùng ID cho payload khác | Fingerprint/version check, quarantine/audit. |
| Payload rất lớn gây tải memory | Giới hạn broker/client, kiểm `raw.length` trước parse. |
| Schema nguy hiểm/deserialization không tin cậy | Jackson mapping DTO allowlisted, không Java serialization tùy ý. |
| Raw payload chứa PII/secret | Redacted logs, mã hóa quarantine, TTL và quyền truy cập. |
| Retained command cũ gây thực thi lại | Không dùng retained cho lệnh một lần; command ID và TTL. |
| Dedup cache bị poisoning | Không chấp nhận ID trước khi authorize, DB unique key và transaction. |

**Không dùng MQTT Client ID hoặc topic name như bằng chứng xác thực duy nhất.** Nó có thể là định danh khai báo trong protocol, nhưng quyền tin cậy phải đến từ broker identity/ACL và business mapping.

## 22. Observability: biết duplicate thuộc lớp nào

Một dashboard chỉ hiển thị “10% MQTT duplicate” là không đủ nếu không phân biệt protocol redelivery với application retry.

| Metric/field gợi ý | Công dụng |
| --- | --- |
| `mqtt_inbound_messages_total` | Số MQTT messages adapter nhận. |
| `mqtt_transport_duplicate_flag_total` | Thống kê DUP metadata khi converter/version cung cấp. |
| `business_new_events_total` | Số event IDs mới đã commit. |
| `business_duplicates_ignored_total` | Số retries/replays không tạo side effect. |
| `business_id_collisions_total` | Số event ID bị tái sử dụng sai. |
| `mqtt_inbound_processing_errors_total{kind}` | Lỗi topic/schema/DB/recovery. |
| `mqtt_reconnect_attempts_total` | Reconnect loop và incident correlation. |
| `idempotency_db_conflicts_total` | Số unique-key conflicts, có thể đo trong processor. |
| `mqtt_inbox_backlog` | Lượng inbound durable work chưa xử lý. |
| `mqtt_outbox_oldest_age_seconds` | Mức trễ relay downstream. |
| `business_effect_commit_latency_ms` | Độ trễ transaction nghiệp vụ. |
| `business_event_replay_lag_seconds` | Tuổi event khi được replay/đối soát. |

Các tên trên chỉ là **gợi ý thiết kế**, không phải bộ metric Spring Integration/Paho tự phát theo đúng tên. Tránh đặt từng `eventId` hoặc `deviceId` làm metric label do cardinality rất cao; lưu IDs trong log/trace được hạn chế truy cập.

### 22.1. Trace một event bị giao lại

~~~text
evt-1001 RECEIVED attempt=1
evt-1001 VALIDATED
evt-1001 DEDUP_NEW
evt-1001 DB_COMMITTED

evt-1001 RECEIVED attempt=2
evt-1001 VALIDATED
evt-1001 DEDUP_ALREADY_PROCESSED
evt-1001 SIDE_EFFECT_SKIPPED
~~~

Không nên gọi lần thứ hai là “MQTT retransmission” nếu chỉ biết nó có cùng business ID; có thể là producer gửi PUBLISH mới. Log cần ghi **điều đã quan sát**, ví dụ receivedTopic, eventId, source client role, timestamp, connection/session epoch nếu có.

### 22.2. Khi duplicate rate tăng đột ngột

Điều tra theo thứ tự:

1. Publisher có đang retry vì timeout không?
2. Broker/client có reconnect loop, client ID trùng hoặc session state bất ổn không?
3. Subscriber có chồng lấp MQTT filters hoặc nhiều instances cùng subscribe không?
4. Bridge có loop hoặc outbox relay liên tục replay không?
5. Consumer có DB timeout khiến upstream retry không?
6. Idempotency key có vô tình reset khi thiết bị reboot hoặc thay firmware không?
7. Retained messages có bị nhầm thành live events khi resubscribe không?

Chỉ tăng QoS từ 1 lên 2 hiếm khi tự sửa tất cả các trường hợp trên, vì nhiều duplicate sinh ra **ngoài** protocol retransmission.

## 23. Anti-patterns và cách thay thế

| Anti-pattern | Vì sao sai | Thay thế |
| --- | --- | --- |
| “QoS 2 thì khỏi cần dedup.” | QoS 2 không bao phủ hai application publishes và DB effects. | Stable event ID + atomic idempotent processing. |
| `if (DUP) return;` | DUP=1 có thể là lần đầu app thực sự thấy. | Tra durable event key. |
| `if (!cache.contains(id)) {write(); cache.put(id);}` | Race, RAM cache mất khi restart. | DB unique constraint và transaction. |
| Dedup theo payload hash duy nhất | Hai readings hợp lệ có cùng giá trị/bytes. | Business event ID, hash chỉ để kiểm collision. |
| Đánh dấu processed trước business write ở transaction khác | Crash có thể làm event mất. | Ledger + write chung transaction. |
| Publish HTTP/Kafka rồi assume DB commit atomic | Không có distributed atomicity mặc định. | Transactional outbox/inbox và idempotent downstream. |
| Mỗi retry tạo eventId mới | Consumer không biết retries thuộc cùng event. | Giữ eventId ổn định. |
| Dùng MQTT packet ID làm database key | Reuse/khác scope client session. | Business ID. |
| Ném exception cho mọi duplicate | Tạo retry/log storm. | Duplicate hợp lệ là idempotent success. |
| Để dedup TTL 1 ngày trong khi replay 7 ngày | Replay sau TTL tạo effect lặp. | Retention theo max replay horizon. |
| Gán cùng Client ID cho hai replicas | Broker có thể đá kết nối. | Unique active Client ID hoặc shared subscriptions hỗ trợ. |
| Coi exception Java là rollback MQTT ACK | ACK timing độc lập transaction. | Kiểm tra adapter/manual ACK/version và durable inbox. |

## 24. Bài tập thực hành: telemetry và lệnh điều khiển

**Bối cảnh:** một hệ thống IoT có 20.000 cảm biến publish telemetry QoS 1, một backend Spring Integration lưu PostgreSQL, và một downstream Kafka consumer phát thông báo cảnh báo. Mạng thiết bị không ổn định, có thể phát lại messages sau reconnect hoặc outbox retry.

### Yêu cầu

1. Thiết kế MQTT topic `tenants/{tenantId}/devices/{deviceId}/temperature` và JSON schema chứa `schemaVersion`, `eventId`, `tenantId`, `deviceId`, `sequence`, `celsius`.
2. Chọn event ID tồn tại qua restart/replay; mô tả cách tránh collision khi firmware reboot.
3. Cấu hình `MqttPahoMessageDrivenChannelAdapter` subscribe filter hẹp theo tenant, QoS 1, dùng converter `payloadAsBytes=true`.
4. Dùng `MqttHeaders.RECEIVED_TOPIC` kiểm tra tenant/device và Jackson parse payload.
5. Thiết kế bảng dedup ledger với composite unique key, data retention theo replay horizon và hash để phát hiện ID collision.
6. Viết `@Transactional` processor insert ledger rồi reading trong **cùng transaction**.
7. Gửi cùng event hai lần; kiểm tra chỉ một reading được commit.
8. Gửi hai events có giá trị đo như nhau nhưng IDs khác; kiểm tra không bị bỏ sai.
9. Chạy hai consumer instances cùng ghi database; test concurrent duplicate và unique key conflict.
10. Thử database rollback giữa ledger và business write; retry phải không bị chặn sai.
11. Test malformed payload, wrong tenant, oversize và ID collision bằng error/quarantine policy.
12. Thêm outbox row trong transaction để relay event sang Kafka; thử crash sau Kafka send nhưng trước mark sent.
13. Làm Kafka consumer idempotent theo same event ID; không dựa vào duplicate filtering ở MQTT như bảo đảm cuối.
14. Test broker reconnect/session recovery, QoS 0/1/2 và overlapping subscription filters.
15. Phân biệt hai lệnh CLI cùng eventId với packet-level QoS retransmission; dùng fault injection để test latter.
16. Thiết kế latest state update có sequence/epoch để xử lý out-of-order.
17. Xem xét manual ACK theo API version; đo thứ tự DB commit và MQTT ACK trong fault test.
18. Thiết kế metrics new/duplicate/collision/error/replay lag và bảo mật broker ACL/TLS.
19. Thử business command `TURN_ON` xuất hiện hai lần: thiết bị không chạy side effect hai lần nhưng có thể phản hồi ACK cũ.
20. Viết tài liệu nêu rõ delivery guarantee ở từng ranh giới MQTT → Spring → PostgreSQL → Kafka.

**Tiêu chí đạt:** duplicate không tạo side effect lặp; events khác ID vẫn được giữ; transaction rollback và concurrency đúng; ACK timing không bị giả định; có durable outbox và test broker thật; hệ thống truy vết được vì sao event bị redeliver.

## 25. Câu hỏi tự kiểm tra

1. QoS 0 có bao giờ tạo business duplicate không? Vì sao?
2. QoS 1 dùng handshake nào? Khi `PUBACK` bị mất, điều gì có thể xảy ra?
3. QoS 2 exactly once áp dụng cho phạm vi nào?
4. Vì sao hai QoS 2 PUBLISHes với cùng `commandId` vẫn có thể tạo side effect lặp?
5. `DUP=1` có luôn chứng minh consumer đã nhận event trước đó không?
6. `DUP=0` có luôn chứng minh event mới không?
7. MQTT packet ID và Paho token khác event ID ra sao?
8. Hai readings cùng 26.5°C có thể là hai business events hợp lệ không?
9. Vì sao raw payload hash không nên là idempotency key duy nhất?
10. Khi cùng event ID đi cùng bytes khác nhau, nên làm gì?
11. Dùng `SELECT` rồi `INSERT` có tránh race giữa hai threads không?
12. Vì sao cần database unique constraint ngay cả khi dùng cache?
13. Tại sao ledger INSERT và business INSERT phải cùng transaction?
14. Nếu DB commit nhưng MQTT ACK chưa gửi và app crash, replay nên được xử lý thế nào?
15. Nếu MQTT đã ACK nhưng DB chưa commit và app crash, có thể mất business event không?
16. Manual ACK có biến PostgreSQL và broker thành một distributed transaction không?
17. MQTT retained và persistent session khác nhau như thế nào?
18. Khi subscribe lại và nhận retained ONLINE, có nên coi là live online event không?
19. Overlapping subscriptions có thể gây duplicate ra sao?
20. Hai MQTT clients khác ID subscribe cùng topic khác shared subscription như thế nào?
21. Vì sao Client ID trùng giữa hai active instances không phải load balancing?
22. Dedup và out-of-order là hai vấn đề khác nhau ra sao?
23. Khi sequence reset sau reboot, latest-state update cần thêm gì?
24. Vì sao phải validate tenant/device topic trước khi ghi dedup key?
25. Khi MQTT event được chuyển tiếp Kafka/HTTP, vì sao cần outbox?
26. Test fake `MessageChannel` có chứng minh broker DUP flag không?
27. Test hai `mosquitto_pub` cùng ID có phải test QoS retransmission không?
28. Poison message có nên retry vô hạn không?
29. Idempotency retention cần so với thời gian replay tối đa như thế nào?
30. Metric nào nên đo để phân biệt business duplicate với Paho reconnect problem?

**Gợi ý:** QoS là cơ chế protocol; dedup là **hợp đồng business + durable idempotency**. Một event ID ổn định, unique constraint, transaction và replay policy được kiểm thử là các thành phần không thể bỏ qua.

## 26. Kết luận

**Xử lý duplicate message theo QoS** trong Spring Integration MQTT đòi hỏi phân biệt rõ giao thức và nghiệp vụ:

- **QoS 0:** không có broker ACK cho PUBLISH, nhưng business duplicate vẫn có thể đến từ nhiều application publishes.
- **QoS 1:** at-least-once có khả năng redelivery; consumer phải sẵn sàng nhận cùng event ID nhiều lần.
- **QoS 2:** exactly-once trong phạm vi một MQTT publication/handshake, **không** tự bảo đảm business side effect exactly once.
- **DUP flag, packet ID, delivery token, Spring message UUID:** metadata kỹ thuật hữu ích cho chẩn đoán, **không** thay durable business event ID.
- **Event ID + database unique constraint + transaction:** chặn side effect bị ghi lặp giữa nhiều threads, instances, reconnects và restarts.
- **Session, retained, topic overlap, bridge và outbox:** là những nguồn duplicate/replay cần thiết kế riêng.
- **Manual ACK, error channel và retry:** phải kiểm chứng theo Paho/Spring Integration version; không giả định exception Java tự rollback MQTT ACK.
- **Kiểm thử theo ba lớp:** Spring flow không broker, database concurrency và broker end-to-end có fault injection.

Trong module **SPRING_INTEGRATION_ADAPTERS**, kết hợp **MQTT transport → MessageChannel → validate payload/topic → idempotent transaction → outbox/downstream** giúp luồng tích hợp giữ được tính đúng đắn khi kết nối mất ổn định. Mục tiêu không phải ngăn mọi PUBLISH xuất hiện lặp, mà là **bảo đảm mỗi business event hợp lệ gây đúng hiệu ứng được phép và có thể truy vết/đối soát khi xảy ra retry**.





