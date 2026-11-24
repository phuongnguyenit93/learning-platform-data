# Subscription pattern và wildcard topic

## 1. Bài toán và mục tiêu học tập

Trong một hệ thống IoT, một Spring Integration application có thể cần nhận dữ liệu từ hàng nghìn thiết bị:

~~~text
tenants/tenant-a/devices/device-17/telemetry
tenants/tenant-a/devices/device-21/telemetry
tenants/tenant-a/devices/device-35/telemetry
...
~~~

Nếu tạo một MQTT subscription riêng cho **mỗi thiết bị**, số lượng topic filter và cấu hình vận hành có thể tăng rất nhanh. MQTT giải quyết trường hợp này bằng **subscription topic filters**: subscriber đăng ký một mẫu như `tenants/tenant-a/devices/+/telemetry`, broker tự so khớp các **topic names** thực tế của những PUBLISH đến.

Tuy nhiên, wildcard topic rất dễ bị hiểu sai. `+` không phải regex bất kỳ; `#` chỉ có thể nằm ở cấp cuối; một PUBLISH không được dùng wildcard như subscription. Quan trọng hơn, filter rộng **không phải cơ chế xác thực hoặc phân quyền**: nếu subscription vượt ranh giới tenant, ứng dụng có thể nhận cả dữ liệu không được phép.

Bài **“Subscription pattern và wildcard topic”** thuộc chương **Adapter MQTT** trong module **SPRING_INTEGRATION_ADAPTERS**. Module hướng đến kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`, thực hành file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời xử lý hợp đồng message, lỗi và vòng đời kết nối.

Sau bài học, người học có thể:

1. Phân biệt **MQTT topic name**, **topic filter**, **broker URL**, **Spring MessageChannel** và message header.
2. Nắm chính xác cú pháp wildcard `+` (một cấp) và `#` (nhiều cấp).
3. Giải thích edge cases như cấp topic rỗng, topic bắt đầu bằng `$`, chữ hoa/chữ thường và filter chồng lấp.
4. Cấu hình `MqttPahoMessageDrivenChannelAdapter` để subscribe một hoặc nhiều topic filters.
5. Dùng `MqttHeaders.RECEIVED_TOPIC` xác định **topic thực nhận**, không nhầm với filter đã subscribe.
6. Kết hợp `IntegrationFlow` với validate topic, tenant, device ID, schema, error handling và idempotency.
7. Hiểu QoS subscription, Client ID, `cleanSession`, reconnect và tác động của thay đổi topic lúc runtime.
8. Kiểm thử matching bằng bảng trường hợp, unit test không broker, sau đó thực nghiệm với MQTT broker.
9. Chọn khi nào dùng topic wildcard, Spring router, shared subscription hoặc nhiều inbound endpoints.

**Thông điệp chính:** topic filter chọn **những publication nào broker chuyển tới MQTT client**. Sau khi nhận, ứng dụng vẫn cần kiểm tra **topic cụ thể, identity, quyền truy cập, payload schema và trạng thái nghiệp vụ** trước khi xử lý.

## 2. Kiến trúc: broker lọc topic trước, Spring xử lý sau

~~~mermaid
flowchart LR
    D1["Publisher device-17"]
    D2["Publisher device-21"]
    D3["Publisher device-35"]
    B[("MQTT broker<br/>topic matching")]
    SUB["Paho subscriber<br/>filter: tenants/tenant-a/devices/+/telemetry"]
    AD["MqttPahoMessageDrivenChannelAdapter"]
    CH["mqtt.telemetry.in<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>validate topic + parse JSON"]
    DB[("Database / downstream")]
    D1 -->|"PUBLISH topic cụ thể"| B
    D2 -->|"PUBLISH topic cụ thể"| B
    D3 -->|"PUBLISH topic cụ thể"| B
    B -->|"DELIVER theo filter và QoS"| SUB
    SUB --> AD --> CH --> FLOW --> DB
~~~

Các lớp có vai trò riêng:

| Thành phần | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| Broker URI | `tcp://localhost:1883` | Nơi Paho kết nối MQTT broker. |
| Publish topic name | `tenants/tenant-a/devices/device-17/telemetry` | Địa chỉ giao thức của **một PUBLISH cụ thể**. |
| Subscription topic filter | `tenants/tenant-a/devices/+/telemetry` | Mẫu broker dùng để quyết định có giao PUBLISH tới subscriber hay không. |
| Spring MessageChannel | `mqtt.telemetry.in` | Đường nội bộ để adapter bàn giao Spring message vào flow. |
| Received topic header | `MqttHeaders.RECEIVED_TOPIC` | Topic **thực tế** của PUBLISH đã được broker giao, ví dụ `.../device-17/telemetry`. |
| Business identity | `tenantId`, `deviceId`, `eventId` | Dữ liệu cần xác thực/validate và dùng để chống xử lý trùng. |

Một Spring channel có thể nhận message từ rất nhiều MQTT topics, không cần tạo một channel riêng cho từng thiết bị. Ngược lại, một MQTT client có thể subscribe nhiều filters, và những filters đó vẫn có thể được đưa chung vào một Spring channel.

### 2.1. MQTT inbound là message-driven

`MqttPahoMessageDrivenChannelAdapter` đăng ký MQTT subscription và nhận message qua cơ chế client callback. Nó **không** cần `@Poller` để hỏi broker định kỳ có message hay không. Poller chỉ cần nếu **bước nội bộ sau đó** lấy message từ `PollableChannel` như `QueueChannel`.

### 2.2. Topic filter không quyết định payload kiểu Java

Broker so khớp topic, không biết payload JSON, protobuf hay text. `DefaultPahoMessageConverter` chuyển payload byte thành `String` hoặc `byte[]` theo cấu hình, rồi handler/transformer của Spring Integration mới decode schema.

Không suy luận rằng filter `.../telemetry` bắt buộc mọi publisher gửi `TemperatureReading` hợp lệ. Hợp đồng định dạng dữ liệu và quyền thiết bị phải được thực hiện ở ứng dụng.

## 3. Topic name và topic filter: phân biệt từ đầu

**Topic name** là chuỗi gắn với PUBLISH. Nó có cấu trúc các cấp ngăn bằng dấu `/`:

~~~text
tenants / tenant-a / devices / device-17 / telemetry
   1        2         3         4          5
~~~

**Topic filter** là chuỗi subscriber dùng trong SUBSCRIBE. Nó có thể chứa wildcard:

~~~text
tenants/tenant-a/devices/+/telemetry
tenants/tenant-a/devices/#
tenants/tenant-a/#
~~~

| Thao tác | Hợp lệ | Không hợp lệ |
| --- | --- | --- |
| PUBLISH | `tenants/tenant-a/devices/device-17/telemetry` | `tenants/tenant-a/devices/+/telemetry` |
| PUBLISH | `devices/device-17/state` | `devices/#` |
| SUBSCRIBE | `tenants/tenant-a/devices/+/telemetry` | `devices/room#` |
| SUBSCRIBE | `devices/#` | `devices/#/state` |

**Quy tắc:** wildcard `+` và `#` dùng trong **topic filter**; một **topic name** của PUBLISH không được chứa các wildcard này.

### 3.1. Topic filters không phải regex

MQTT filters không hiểu `*`, `?`, nhóm regex, biểu thức `[0-9]+` hay backslash escape theo cách regex Java vận hành.

~~~text
MQTT:
  devices/+/state         ✓ single-level
  devices/#               ✓ multi-level

Không phải MQTT filters hợp lệ với ý nghĩa mong muốn:
  devices/*/state
  devices/(device-17|device-21)/state
  devices/[0-9]+/state
~~~

Nếu cần chọn tập thiết bị theo database policy phức tạp, có thể subscribe filter hợp lệ đủ hẹp rồi **filter lại trong Spring Integration**; tuy nhiên broker ACL cũng phải đảm bảo client chỉ có thể nhận topic trong phạm vi được ủy quyền.

### 3.2. Topic names phân biệt chữ hoa/thường

~~~text
devices/device-17/state
Devices/device-17/state
devices/Device-17/state
~~~

Ba chuỗi có thể là **ba MQTT topic names khác nhau**. Nếu hợp đồng quyết định dùng lowercase, chuẩn hóa nhất quán khi cấp identity và tạo topic, không chỉ chuyển lowercase ở subscriber sau khi đã authorize theo giá trị khác.

## 4. Wildcard cộng (+): đúng một cấp topic

`+` là **single-level wildcard**. Nó phải đứng độc lập ở **toàn bộ một cấp** topic filter, tức là được bao bởi `/` hoặc mép chuỗi.

Ví dụ:

~~~text
Filter: devices/+/state

✓ devices/device-17/state
✓ devices/device-21/state
✓ devices//state
✗ devices/device-17/metrics/state
✗ devices/state
✗ devices/device-17/state/extra
~~~

Trường hợp `devices//state` có cấp topic rỗng giữa hai dấu `/`. MQTT cho phép cấu trúc có cấp rỗng và single-level wildcard có thể match cấp đó. Tuy nhiên, trong hệ thống nghiệp vụ, **device ID rỗng thường không hợp lệ**; Spring handler phải validate và reject.

### 4.1. Nhiều dấu + trong một filter

~~~text
Filter: tenants/+/devices/+/telemetry

✓ tenants/tenant-a/devices/device-17/telemetry
✓ tenants/tenant-b/devices/device-21/telemetry
✗ tenants/tenant-a/devices/device-17/state
✗ tenants/tenant-a/devices/device-17/extra/telemetry
~~~

Filter này có thể nhận dữ liệu **nhiều tenant**, nên không được dùng cho một service chỉ có quyền tenant-a nếu broker principal không được phép đọc tenant-b. Mỗi `+` chỉ đại diện **một cấp**, không phải chuỗi nhiều cấp chứa `/`.

### 4.2. Những filter chứa + sai vị trí

~~~text
devices/device+/state        ← sai: + không chiếm toàn cấp
devices/+suffix/state        ← sai
devices/pre+fix/state        ← sai
devices/+/state             ← đúng
+/devices/+/telemetry       ← đúng về cú pháp; xét ngoại lệ $ ở mục 6
~~~

Muốn tìm các topic có device ID bắt đầu bằng `device-`, không thể viết `device-+` như wildcard suffix. Có thể subscribe `devices/+/state` rồi lọc ID bằng regex Java ở business layer, hoặc thiết kế hierarchy để tiền tố là một cấp riêng.

## 5. Wildcard thăng (#): không hoặc nhiều cấp từ vị trí cuối

`#` là **multi-level wildcard**. Nó phải là **cấp cuối cùng**, chiếm trọn cấp. Filter `#` một mình hợp lệ; filter `a/#` có thể match cả topic `a`, `a/` và các cấp sâu hơn.

~~~text
Filter: devices/#

✓ devices
✓ devices/
✓ devices/device-17
✓ devices/device-17/state
✓ devices/device-17/sensors/temperature
✗ other/devices/device-17/state
~~~

Khác với `+`, `#` có thể match **zero level còn lại**, do đó `devices/#` match topic `devices` dù không có dấu slash ở cuối.

### 5.1. Quy tắc vị trí của #

| Filter | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `#` | Có | Match các topic thông thường ở mọi độ sâu (ngoại lệ topic bắt đầu `$`). |
| `devices/#` | Có | Match `devices` và mọi topic bên dưới. |
| `tenants/tenant-a/#` | Có | Match cây topic của tenant-a. |
| `devices/#/state` | **Không** | `#` không ở cấp cuối. |
| `devices/room#` | **Không** | `#` không đứng độc lập thành cấp. |
| `devices/#extra` | **Không** | Có ký tự khác chung cấp với `#`. |
| `#/#` | **Không** | `#` đầu tiên không phải cấp cuối. |

Filter `devices/#` có thể nhận cả dữ liệu state, telemetry, command và những nhánh khác. Nếu service chỉ cần telemetry, dùng filter hẹp hơn `devices/+/telemetry` hoặc một hierarchy có tenant/loại dữ liệu rõ ràng.

### 5.2. Một dấu + và một dấu # kết hợp

~~~text
Filter: tenants/tenant-a/devices/+/sensors/#

✓ tenants/tenant-a/devices/device-17/sensors
✓ tenants/tenant-a/devices/device-17/sensors/
✓ tenants/tenant-a/devices/device-17/sensors/temperature
✓ tenants/tenant-a/devices/device-17/sensors/environment/humidity
✗ tenants/tenant-b/devices/device-17/sensors/temperature
✗ tenants/tenant-a/devices/device-17/commands
~~~

Đây là cách lọc mọi loại sensor dưới một tenant trong khi vẫn chỉ giữ một cấp device ID, thay vì sử dụng wildcard quá rộng từ gốc broker.

## 6. Topic bắt đầu bằng dấu $: ngoại lệ quan trọng

Trong MQTT, topic name bắt đầu bằng ký tự `$` thường dành cho **broker/system topics** hoặc convention đặc biệt. Quy tắc matching MQTT 3.1.1: filter bắt đầu bằng `#` hoặc `+` **không match** topic name có ký tự đầu tiên là `$`.

Ví dụ:

| Subscription filter | Topic được publish | Match? |
| --- | --- | --- |
| `#` | `devices/device-17/state` | Có |
| `#` | `$SYS/broker/uptime` | **Không** |
| `+/broker/uptime` | `$SYS/broker/uptime` | **Không** |
| `$SYS/#` | `$SYS/broker/uptime` | Có về cú pháp; broker ACL có thể từ chối. |
| `$SYS/+/uptime` | `$SYS/broker/uptime` | Có về cú pháp; broker có thể dùng topic khác. |

**Không hiểu `#` là “mọi topic tuyệt đối”**. Nếu muốn quan sát `$SYS` của broker test, cần subscribe filter bắt đầu `$SYS` tường minh và có quyền; tên, khả năng hỗ trợ và nội dung `$SYS` không phải một bộ API thống nhất giữa mọi broker.

### 6.1. Topic có dấu slash ở đầu

Topic name `/devices/device-17` hợp lệ về cấu trúc MQTT và có **cấp đầu rỗng**. Nó khác `devices/device-17`. Các filter `/devices/#` và `devices/#` không tương đương.

Để giảm sai sót, hệ thống nghiệp vụ nên chuẩn hóa topic không bắt đầu/không kết thúc bằng slash nếu không có lý do rõ ràng; nhưng không được tuyên bố MQTT protocol cấm các trường hợp này.

### 6.2. Empty levels và business IDs

Các topics như `devices//state` có thể hợp lệ về matching, nhưng device ID là chuỗi rỗng. Spring handler cần reject theo business policy. Đừng coi khả năng broker match wildcard là bằng chứng giá trị ID đã được validate.

### 6.3. Ký tự Unicode và độ dài

Topic name/filter là chuỗi UTF-8 theo giới hạn của giao thức, không chỉ ASCII. Ứng dụng cần quy định canonical naming, hạn chế ID ngoài allowlist nếu tương tác giữa nhiều ngôn ngữ/thiết bị và xác minh độ dài **tính theo bytes UTF-8** khi cần.

Không dùng “url encode” hoặc tự thay dấu `/` trong một topic mà không có hợp đồng thống nhất: nó có thể khiến publisher và subscriber thực hiện matching khác nhau hoặc tạo collision giữa các ID.

## 7. Ma trận ví dụ so khớp topic filter

Bảng sau dùng quy tắc matching của MQTT, **không** tính thêm broker ACL hay giới hạn của một broker cụ thể.

| Filter | Topic name | Match? | Vì sao? |
| --- | --- | --- | --- |
| `sensors/+/temperature` | `sensors/device-17/temperature` | Có | `+` match một cấp `device-17`. |
| `sensors/+/temperature` | `sensors/device-17/room/temperature` | Không | Có thêm cấp `room`. |
| `sensors/+/temperature` | `sensors//temperature` | Có | Cấp giữa rỗng, vẫn là một cấp. |
| `sensors/#` | `sensors` | Có | `#` match zero cấp còn lại. |
| `sensors/#` | `sensors/device-17/temperature` | Có | `#` match nhiều cấp. |
| `sensors/+/+#` | `sensors/device-17/temperature` | **Filter không hợp lệ** | `#` phải đứng riêng thành cấp. |
| `devices/+/state` | `devices/device-17/state/last` | Không | Thừa một cấp cuối. |
| `tenants/tenant-a/#` | `tenants/tenant-b/devices/17/state` | Không | Prefix khác tenant. |
| `#` | `$SYS/broker/uptime` | Không | Ngoại lệ `$` ở ký tự đầu. |
| `$SYS/#` | `$SYS/broker/uptime` | Có | Prefix bắt đầu bằng `$SYS` tường minh. |
| `devices/#` | `devices/` | Có | `#` match phần còn lại. |
| `devices/+` | `devices` | Không | Thiếu một cấp `/…` cần cho `+`. |

Những ma trận như vậy nên được chuyển thành **contract tests** dùng broker thật cho các tính năng đặc thù/ranh giới. Một regex Java tự viết để mô phỏng MQTT không phải bằng chứng cuối cùng broker xử lý y hệt, đặc biệt khi có shared subscriptions hoặc extension của vendor.

## 8. Subscription filters chồng lấp: có thể nhận trùng

Giả sử cùng một MQTT client đăng ký hai filters:

~~~text
sensors/+/temperature
sensors/#
~~~

Một publication tới `sensors/device-17/temperature` match **cả hai**. Theo MQTT 3.1.1, server phải thực hiện delivery tuân theo các subscription phù hợp và mức QoS đã được chấp nhận; trong những điều kiện được phép nó **có thể giao thêm các bản sao** cho các subscription chồng lấp. Vì vậy **đừng thiết kế business handler dựa trên giả định “một PUBLISH luôn chỉ có một callback”** khi có overlapping subscriptions.

### 8.1. QoS khi chồng lấp filter

Giả sử:

~~~text
SUBSCRIBE sensors/+/temperature, QoS 1
SUBSCRIBE sensors/#,             QoS 0

PUBLISH sensors/device-17/temperature, QoS 1
~~~

Một publication có nhiều subscription phù hợp. QoS delivery của message phải theo quy định của giao thức/broker đối với các subscriptions đó; thường mức QoS cao nhất được chấp nhận trong các matching subscriptions là điều cần xét, nhưng không suy luận rằng ứng dụng chắc chắn nhận đúng một bản duy nhất ở một QoS duy nhất cho mọi broker/extension.

Muốn xử lý an toàn:

1. Tránh tạo filters trùng nghĩa khi không cần.
2. Dùng `eventId` trong payload cho idempotency.
3. Test broker thật với overlapping filters và QoS khác nhau.
4. Quan sát duplicate delivery và không thực thi side effect lặp.
5. Nếu cần tách nhánh business, dùng một subscription hẹp rồi **Spring router**, thay vì cố tổ chức business routing bằng chồng filters khó đoán.

### 8.2. Nhiều MQTT clients khác nhau

Hai clients với Client ID khác nhau cùng subscribe một filter thông thường thường **đều có thể nhận** một publication phù hợp. Đây là **fan-out theo từng subscriber**, không phải competing consumers như một queue.

Muốn chia tải giữa các workers sao cho chỉ một member của nhóm nhận một message, cần **shared subscriptions** theo hỗ trợ broker/MQTT version hoặc một hạ tầng queue tương ứng. Không dùng **Client ID trùng** để tạo competing consumer: client mới có thể ngắt client cũ, gây reconnect loop.

## 9. QoS của subscription và QoS của PUBLISH

MQTT có QoS ở **hai chặng**:

~~~mermaid
flowchart LR
    PUB["Publisher QoS=1"]
    B[("MQTT broker")]
    SUB["Subscriber SUBSCRIBE QoS=0"]
    APP["Spring Integration handler"]
    PUB -->|"PUBLISH QoS 1 + PUBACK"| B
    B -->|"Delivery QoS tối đa theo subscription"| SUB --> APP
~~~

Publisher có thể PUBLISH ở QoS 1, nhưng nếu subscriber đăng ký filter ở QoS 0 thì chặng broker → subscriber **không tự nâng lên QoS 1**. Khi hai subscription chồng lấp, xem mục 8 thay vì chỉ dùng một công thức giản lược.

| Publisher QoS | Subscriber QoS (một filter) | QoS delivery thường gặp |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 0 | 1 | 0 |
| 1 | 0 | 0 |
| 1 | 1 | 1 |
| 1 | 2 | 1 |
| 2 | 1 | 1 |
| 2 | 2 | 2 |

Spring Integration inbound adapter có thể cấu hình:

~~~java
adapter.setQos(1);
~~~

Đó là **subscription QoS** cho các filters được adapter quản lý theo API sử dụng, không phải QoS mặc định của outbound publications. MQTT outbound `MqttPahoMessageHandler` có `setDefaultQos(1)` hoặc header `MqttHeaders.QOS`, là chiều khác.

### 9.1. QoS không thay thế xử lý trùng trong database

- QoS 0: at most once ở tầng giao thức, có thể mất message.
- QoS 1: at least once ở tầng giao thức, có thể giao lại.
- QoS 2: exactly once **trong phạm vi MQTT protocol delivery**, không bao phủ một transaction DB hoặc command thiết bị.
- Subscription filters chồng lấp hoặc ứng dụng publish lại event mới cùng `eventId` cũng có thể gây duplicate nghiệp vụ.

Do đó cần `eventId`/`commandId` ổn định và idempotent handler khi dữ liệu quan trọng.

## 10. Session, subscribe lại và reconnect

Topic filter không chỉ là một chuỗi cấu hình khi khởi động; nó có quan hệ với **MQTT Client ID** và **session**.

### 10.1. cleanSession=true

Với MQTT 3.1.1, client `cleanSession=true` yêu cầu session sạch. Khi reconnect, application/inbound adapter phải bảo đảm các subscription cần thiết được đăng ký lại. Không suy ra vì bean tồn tại trong Spring context mà broker vẫn còn subscription của connection trước.

### 10.2. cleanSession=false

`cleanSession=false` cho phép broker duy trì session/subscriptions và một số message QoS 1/2 theo quy tắc MQTT và chính sách lưu trữ. Để tận dụng:

1. Subscriber phải thực sự subscribe topic filter thành công.
2. Client ID phải **ổn định** qua reconnect/restart.
3. Hai clients active không được dùng trùng Client ID.
4. Broker có khả năng duy trì session/offline messages trong giới hạn cấu hình.
5. Khi failover sang broker khác, broker cluster phải có session state phù hợp.

**Persistent session không phải retained message**: session có thể giữ message của các subscription lúc subscriber offline; retained là snapshot mới nhất theo topic dành cho việc subscribe phù hợp. Hai cơ chế bổ trợ nhưng không thay thế nhau.

### 10.3. Last Will không phải subscription filter

Last Will là publication do broker phát theo Will Topic cụ thể khi MQTT client mất kết nối bất thường. Một observer Spring có thể subscribe `devices/+/availability` để nhận Will của nhiều thiết bị; nhưng **client thiết bị** phải khai báo Will khi CONNECT. Filter của Spring không tự tạo Will cho thiết bị.

## 11. Ví dụ Spring Boot: subscription pattern cho telemetry theo tenant

Xây một ứng dụng nhận JSON nhiệt độ từ:

~~~text
tenants/tenant-a/devices/{deviceId}/telemetry
~~~

Thay vì subscribe từng thiết bị, một `MqttPahoMessageDrivenChannelAdapter` dùng topic filter:

~~~text
tenants/tenant-a/devices/+/telemetry
~~~

Spring flow sẽ:

1. Nhận MQTT message như `String` JSON.
2. Lấy **topic thực tế** từ `MqttHeaders.RECEIVED_TOPIC`.
3. Trích `deviceId` từ một topic có shape đúng và thuộc tenant-a.
4. Dùng Jackson parse payload thành DTO `TemperatureReading`.
5. Đối chiếu `deviceId` của payload với topic.
6. Ghi sự kiện vào sink giả, hoặc thay bằng DB/HTTP/JMS/AMQP/Kafka handler.
7. Reject dữ liệu sai; production nên có error flow/quarantine.

Ví dụ yêu cầu Java 17+ và Spring Boot/Spring Integration MQTT dùng Eclipse Paho MQTT v3 API tương thích.

### 11.1. Dependency Maven

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

Spring Boot BOM nên quản lý dependency versions đồng bộ. Không trộn class `org.eclipse.paho.client.mqttv3.MqttConnectOptions` với MQTT v5 API rồi kỳ vọng nguyên ví dụ chạy không thay đổi.

### 11.2. Cấu trúc source

~~~text
src/main/java/demo/mqttfilters/
    MqttFiltersApplication.java
    TemperatureReading.java
    TopicFilterValidator.java
    AcceptedTelemetry.java
    TelemetrySink.java
    TopicFilterFlowConfiguration.java
    MqttFilterTransportConfiguration.java

src/main/resources/
    application.properties

src/test/java/demo/mqttfilters/
    TopicFilterFlowTest.java
~~~

Mọi class thuộc package `demo.mqttfilters`. Class Java có modifier `public` phải đặt trong file trùng tên. Các class khác có thể để package-private để test trực tiếp.

### 11.3. Application và properties

~~~java
package demo.mqttfilters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttFiltersApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttFiltersApplication.class, args);
    }
}
~~~

`application.properties`:

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}
app.mqtt.client-id=${MQTT_CLIENT_ID:tenant-a-telemetry-subscriber-1}
app.mqtt.tenant-id=tenant-a
~~~

Demo giả định broker local ở `localhost:1883` và có quyền subscribe topic phù hợp. Spring Boot **không tự chạy MQTT broker**. Với production cần TLS, credentials/secret management, broker topic ACL và Client ID duy nhất cho mỗi subscriber đang hoạt động.

### 11.4. DTO và business validation

~~~java
package demo.mqttfilters;

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
                || celsius < -80 || celsius > 150) {
            throw new IllegalArgumentException("Giá trị nhiệt độ không hợp lệ");
        }
    }
}
~~~

Dải nhiệt độ chỉ minh họa cho ví dụ. Một ứng dụng thật cần schema versioning, device-specific limits và kiểm tra quyền publish/tenant ở broker lẫn business layer. Một MQTT topic filter chỉ quyết định delivery, không phải validation.

### 11.5. Validator dùng **exact received topic**, không dùng wildcard để parse

~~~java
package demo.mqttfilters;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class TopicFilterValidator {

    private final String tenantId;
    private final Pattern telemetryTopic;

    TopicFilterValidator(String tenantId) {
        if (tenantId == null
                || !tenantId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("tenantId không hợp lệ");
        }
        this.tenantId = tenantId;
        this.telemetryTopic = Pattern.compile(
                "^tenants/" + Pattern.quote(tenantId)
                + "/devices/([A-Za-z0-9_-]{1,40})/telemetry$");
    }

    String subscriptionFilter() {
        return "tenants/" + tenantId + "/devices/+/telemetry";
    }

    String requireDeviceId(Object receivedTopic) {
        if (!(receivedTopic instanceof String topic)) {
            throw new IllegalArgumentException("Thiếu received MQTT topic");
        }

        Matcher matcher = telemetryTopic.matcher(topic);
        if (!matcher.matches()) {
            throw new IllegalArgumentException(
                    "Topic không thuộc phạm vi telemetry tenant: " + topic);
        }

        return matcher.group(1);
    }
}
~~~

Ở đây **regex Java** được dùng **sau khi broker đã so khớp MQTT subscription filter**, để validate **topic name cụ thể** theo business contract. Regex này **không phải MQTT topic filter**.

Điểm bảo mật: `subscriptionFilter()` được xây từ `tenantId` đã validate, không lấy nguyên MQTT filter từ HTTP caller. Vì topic cụ thể phải match pattern có tenant cố định, những topic như `tenants/tenant-b/...` hoặc `.../devices//telemetry` sẽ bị từ chối nếu đi vào flow bất thường.

### 11.6. Sink giả có thể kiểm thử

~~~java
package demo.mqttfilters;

record AcceptedTelemetry(
        String topic,
        TemperatureReading reading) {
}
~~~

~~~java
package demo.mqttfilters;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class TelemetrySink {

    private final List<AcceptedTelemetry> accepted =
            new CopyOnWriteArrayList<>();

    void accept(AcceptedTelemetry event) {
        accepted.add(event);
    }

    List<AcceptedTelemetry> snapshot() {
        return List.copyOf(accepted);
    }

    void clear() {
        accepted.clear();
    }
}
~~~

`TelemetrySink` chỉ giữ dữ liệu trong bộ nhớ để phục vụ bài học, không bảo đảm lưu bền vững qua restart. Khi kết nối thực, thay bằng business handler có idempotency, transaction, retry/error policy theo hệ thống DB hoặc outbound adapter khác.

### 11.7. Spring MessageChannel và IntegrationFlow

~~~java
package demo.mqttfilters;

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
class TopicFilterFlowConfiguration {

    @Bean(name = "mqtt.telemetry.in")
    MessageChannel telemetryInput() {
        return new DirectChannel();
    }

    @Bean
    TopicFilterValidator topicFilterValidator(
            @Value("${app.mqtt.tenant-id}") String tenantId) {
        return new TopicFilterValidator(tenantId);
    }

    @Bean
    ObjectMapper telemetryMapper() {
        return new ObjectMapper();
    }

    @Bean
    TelemetrySink telemetrySink() {
        return new TelemetrySink();
    }

    @Bean
    IntegrationFlow telemetryFlow(
            TopicFilterValidator validator,
            ObjectMapper mapper,
            TelemetrySink sink) {

        return IntegrationFlow.from("mqtt.telemetry.in")
                .handle(String.class, (json, headers) -> {

                    String deviceId = validator.requireDeviceId(
                            headers.get(MqttHeaders.RECEIVED_TOPIC));

                    final TemperatureReading reading;
                    try {
                        reading = mapper.readValue(
                                json, TemperatureReading.class);
                    } catch (JsonProcessingException ex) {
                        throw new IllegalArgumentException(
                                "Không parse được telemetry JSON", ex);
                    }

                    if (!deviceId.equals(reading.deviceId())) {
                        throw new IllegalArgumentException(
                                "deviceId trong payload khác MQTT topic");
                    }

                    String actualTopic = (String)
                            headers.get(MqttHeaders.RECEIVED_TOPIC);

                    sink.accept(new AcceptedTelemetry(
                            actualTopic, reading));

                    return null; // inbound một chiều
                })
                .get();
    }
}
~~~

**Flow không dùng `@Poller`** để nhận MQTT messages; callback từ inbound adapter sẽ phát `Message<String>` vào `mqtt.telemetry.in`. Với `DirectChannel`, handler làm việc đồng bộ theo thread gửi message vào channel trong bài học. Khi parser/DB nặng, có thể thêm queue/executor có giới hạn để tránh chặn callback MQTT không kiểm soát.

Nếu dùng `DefaultPahoMessageConverter.setPayloadAsBytes(true)`, payload inbound có thể là `byte[]` thay vì `String`; khi đó phải thay contract handler/decoder tương ứng. Không giả định broker tự parse JSON thành DTO.

### 11.8. MQTT client factory và adapter subscribe wildcard

~~~java
package demo.mqttfilters;

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
class MqttFilterTransportConfiguration {

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
    MqttPahoMessageDrivenChannelAdapter telemetryAdapter(
            MqttPahoClientFactory mqttClientFactory,
            @Qualifier("mqtt.telemetry.in") MessageChannel output,
            TopicFilterValidator topicFilterValidator,
            @Value("${app.mqtt.client-id}") String clientId) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId,
                mqttClientFactory,
                topicFilterValidator.subscriptionFilter());

        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(output);
        return adapter;
    }
}
~~~

Hành vi theo từng bước:

1. `mqttClientFactory` cung cấp Paho connection options; `setCleanSession(false)` minh họa session bền hơn cho subscriber cần offline delivery.
2. `telemetryAdapter` subscribe filter `tenants/tenant-a/devices/+/telemetry`.
3. Broker giao những PUBLISH có topic phù hợp cho MQTT client của adapter, theo QoS/session/ACL.
4. `DefaultPahoMessageConverter` chuyển MQTT bytes sang payload Spring text trong demo.
5. Inbound adapter đặt received topic metadata, rồi gửi message vào channel.
6. Spring flow kiểm tra **topic thực nhận**, parse JSON và đối chiếu device ID trước khi xử lý.

**Đặc biệt:** filter `+` chỉ xuất hiện trong **SUBSCRIBE**. Publisher ngoài Spring vẫn phải PUBLISH topic như `tenants/tenant-a/devices/device-17/telemetry`, không publish vào chính filter `tenants/tenant-a/devices/+/telemetry`.

Client ID trong properties chỉ thích hợp cho một local instance; chạy hai replica cùng ID có thể khiến broker ngắt connection cũ. Với `cleanSession=false`, Client ID ổn định là cần thiết để phục hồi session logic nhưng phải bảo đảm chỉ một active client sở hữu ID đó.

### 11.9. Dữ liệu MQTT đầu vào minh họa

PUBLISH từ device-17:

~~~text
Topic: tenants/tenant-a/devices/device-17/telemetry
QoS:   1
Payload:
{"eventId":"evt-1001","deviceId":"device-17","celsius":26.5}
~~~

`TopicFilterValidator` trích `device-17` từ topic thực. Jackson parse payload thành `TemperatureReading`. Nếu `deviceId` của JSON là `device-21` thì flow reject dù topic đã match wildcard subscription tại broker.

Một publisher cố gắng gửi sang `tenants/tenant-b/devices/device-17/telemetry` sẽ không match subscription filter tenant-a. Tuy nhiên, **đó không thay thế ACL broker**: principal của subscriber phải được cấp quyền đọc đúng namespace của mình; filter hẹp là defense-in-depth, không phải authorization.

## 12. Subscribe nhiều filters trong một adapter

Một client có thể cần nhận cả telemetry và availability:

~~~text
tenants/tenant-a/devices/+/telemetry
tenants/tenant-a/devices/+/availability
~~~

`MqttPahoMessageDrivenChannelAdapter` hỗ trợ cấu hình nhiều topic filters ở constructor trong các phiên bản API Paho MQTT tương ứng:

~~~java
var adapter = new MqttPahoMessageDrivenChannelAdapter(
        "tenant-a-mqtt-in",
        mqttClientFactory,
        "tenants/tenant-a/devices/+/telemetry",
        "tenants/tenant-a/devices/+/availability");

adapter.setQos(1);
adapter.setOutputChannel(mqttInboundChannel);
~~~

Snippet này là **phương án thay thế** cho adapter demo mục 11; không thêm đồng thời vào cùng channel rồi mặc nhiên mong đợi business handler telemetry xử lý được payload `ONLINE/OFFLINE`.

### 12.1. Router ở Spring theo received topic

Khi hai loại topic mang payload schema khác nhau, hãy route theo `MqttHeaders.RECEIVED_TOPIC` sang hai flows riêng:

~~~mermaid
flowchart TD
    BROKER[("MQTT broker")]
    AD["Inbound adapter<br/>2 subscription filters"]
    CH["mqtt.all.in"]
    R{"Router theo received topic"}
    TELE["mqtt.telemetry<br/>JSON decoder → DB"]
    AVAIL["mqtt.availability<br/>ONLINE/OFFLINE handler"]
    ERR["unknown-topic / quarantine"]
    BROKER --> AD --> CH --> R
    R -->|"*/telemetry"| TELE
    R -->|"*/availability"| AVAIL
    R -->|"khác"| ERR
~~~

Đây là sơ đồ kiến trúc. Khi triển khai Java DSL `.route(...)`, nên dùng rule parse/validate topic cụ thể hoặc một mapping đã kiểm soát, không định tuyến dựa trên một phép `String.contains("state")` dễ match sai. Cả hai nhánh phải kiểm tra tenant, device ID và schema.

Một channel khác với MQTT filter: **topic filter** được broker dùng để quyết định giao PUBLISH đến client; **Spring router** quyết định consumer/processing flow nội bộ sau khi message đã vào ứng dụng.

### 12.2. Khi nào tách thành hai MQTT inbound adapters?

Tách adapter nếu:

- Một nhánh cần converter `String`, nhánh kia cần `byte[]`.
- Hai nhóm topic có credentials/ACL hoặc broker URLs khác nhau.
- Cần Client ID/session/QoS/recovery policies khác nhau.
- Khả năng nghẽn của một nhóm dữ liệu không được ảnh hưởng nhóm còn lại.
- Cần lifecycle start/stop hoặc scaling độc lập.

Hai adapters chạy đồng thời cần **Client ID riêng**; có thể dùng cùng `MqttPahoClientFactory` nếu phù hợp cấu hình connection, nhưng đừng suy ra chúng chia sẻ một physical MQTT connection.

## 13. Subscription thay đổi tại runtime

Có những hệ thống muốn thêm/bớt topic filter mà không restart ứng dụng, ví dụ subscriber chuyển từ một khu vực thiết bị sang khu vực khác.

Trong các phiên bản Spring Integration hỗ trợ, `MqttPahoMessageDrivenChannelAdapter` có API để quản lý topic subscriptions tại runtime, chẳng hạn các phương thức thuộc nhóm `addTopic(...)` và `removeTopic(...)`. Chữ ký và hành vi trên lifecycle đang chạy cần đối chiếu phiên bản thực tế.

Ví dụ ý tưởng:

~~~java
// Minh họa API ở những phiên bản adapter hỗ trợ:
adapter.addTopic(
        "tenants/tenant-a/devices/+/availability", 1);

adapter.removeTopic(
        "tenants/tenant-a/devices/+/availability");
~~~

**Đây không phải mã phải thêm vào ví dụ hoàn chỉnh ở mục 11.** Khi thay filter runtime, cần kiểm soát:

1. **Authorization:** ai có quyền thêm filter mới và thuộc tenant nào?
2. **Idempotency:** không thêm trùng hoặc xóa một filter vẫn được flow khác sử dụng.
3. **Session state:** nếu `cleanSession=false`, subscription đã được broker lưu có thể tồn tại qua reconnect; cần xác định app/adapter đồng bộ state thế nào.
4. **Concurrency:** thay filter khi đang nhận message có thể có in-flight publications.
5. **Replay:** subscribe một filter mới có thể làm broker gửi retained snapshots theo matching.
6. **Observability:** log audit thời gian và identity người thay đổi, số active filters và kết quả SUBACK/UNSUBACK khi có thể.
7. **Rollback:** khi add/remove thất bại giữa chừng, trạng thái app và broker không được âm thầm bất nhất.

### 13.1. SUBSCRIBE và UNSUBSCRIBE không phải transaction nghiệp vụ

Khi một client thay đổi subscription, broker xử lý theo protocol. Điều này không tạo transaction cùng database, không xóa business events đã nhận, và không tự bù trừ message đã xử lý khi filter được remove.

Nếu nghiệp vụ yêu cầu quản lý subscriptions theo khách hàng, nên có bảng trạng thái desired/actual subscriptions, validation và logic reconcile sau reconnect/restart thay vì chỉ gọi method rồi bỏ qua kết quả.

### 13.2. Cần lưu ý retained snapshots khi thêm filter

Khi SUBSCRIBE một filter mới, broker có thể gửi ngay retained messages phù hợp. Consumer không nên mặc định xem chúng là **event mới vừa được publisher phát**. Trạng thái retained là snapshot theo topic, khác với event history.

Với command một lần, publisher thường không nên đặt retained=true. Một subscriber mới có thể nhận command retained cũ và vô tình kích hoạt lại hành động vật lý.

## 14. Security: wildcard rộng có thể vượt ranh giới tenant

MQTT wildcard là **công cụ chọn topic**, không phải cơ chế cấp quyền. Ví dụ filter:

~~~text
tenants/+/devices/+/telemetry
~~~

có thể nhận dữ liệu của nhiều tenant nếu broker cho phép. Một service chỉ xử lý `tenant-a` không nên đăng ký wildcard ở cấp tenant mà trông chờ downstream validator để “bảo vệ dữ liệu” duy nhất.

Các lớp kiểm soát nên phối hợp:

| Lớp | Cần làm gì? |
| --- | --- |
| MQTT broker auth | Xác thực principal/client ID/certificate theo hạ tầng hỗ trợ. |
| Broker subscription ACL | Chỉ cho phép principal subscribe filters/topics thuộc tenant và role được cấp. |
| Broker publish ACL | Device chỉ publish vào namespace tương ứng, không ghi vào topic của thiết bị khác. |
| Topic filter trong adapter | Hẹp nhất theo use case, ví dụ `tenants/tenant-a/devices/+/telemetry`. |
| Received topic validation | Parse topic thực nhận, reject cấp rỗng, sai shape hoặc tenant mismatch. |
| Payload validation | Đối chiếu `deviceId`, `tenantId`, schemaVersion và event ID với topic. |
| Data isolation | Không ghi dữ liệu tenant-b sang DB tenant-a; không phát tán vào topic/HTTP khác. |
| Logging/audit | Ghi action và ID cần thiết; không log credentials hoặc raw payload nhạy cảm. |

### 14.1. Vì sao nhận toàn broker với # có thể nguy hiểm?

`#` rất tiện khi debug một broker thử nghiệm; trong production nó có thể làm ứng dụng nhận các loại payload không hỗ trợ, tiêu thụ CPU/memory, lộ dữ liệu nếu ACL lỏng, và phát sinh rủi ro log chứa thông tin nhạy cảm. Nó cũng không match `$SYS` vì ngoại lệ special topic.

**Ưu tiên subscribe filter hẹp** theo domain, tenant, device type và kind. Nếu thật sự phải subscribe nhiều namespace, hãy tách role/client credentials, route và validation.

### 14.2. Topic injection qua định danh

Nếu client HTTP cung cấp `deviceId = "a/../../tenant-b"` hoặc chứa `+`/`#`, một ứng dụng ghép topic trực tiếp có thể tạo topic sai shape hoặc cố điều hướng sang dữ liệu khác. Cần kiểm tra ID theo allowlist và **authorization độc lập**, không tự “sửa” bằng cách thay thế ký tự một cách gây collision.

### 14.3. Broker ACL khác ứng dụng filter

Nếu broker được cấu hình cho phép user subscribe toàn bộ `tenants/#`, việc client tự chọn `tenants/tenant-a/#` không ngăn user sửa config để đọc tenant-b. Broker ACL là ranh giới kiểm soát quyền; filter và validator là lớp tăng cường an toàn, không thay thế ACL.

## 15. Lỗi subscription và xử lý message

~~~mermaid
flowchart TD
    APP["Spring Integration app"]
    CONNECT{"Connect broker được?"}
    SUB{"SUBSCRIBE filter được chấp nhận?"}
    MATCH["Broker matching PUBLISH"]
    CONVERT["Paho converter → Spring Message"]
    VALID{"Validate topic/payload?"}
    DB["Business DB / outbound"]
    ERR["Error flow / quarantine / alert"]
    APP --> CONNECT
    CONNECT -->|"Có"| SUB
    CONNECT -->|"Không"| ERR
    SUB -->|"Có"| MATCH --> CONVERT --> VALID
    SUB -->|"Không: ACL/filter invalid"| ERR
    VALID -->|"Đúng"| DB
    VALID -->|"Sai"| ERR
    DB -. "Downstream failure" .-> ERR
~~~

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Client kết nối thành công nhưng không nhận message | Topic filter sai case/shape, publisher sai topic, ACL, subscription chưa được chấp nhận. | Kiểm tra filter, MQTT topic thực, broker logs/SUBACK và Spring endpoint lifecycle. |
| Broker từ chối SUBSCRIBE | ACL hoặc topic filter không hợp lệ. | Sửa quyền/cấu hình; không retry vô hạn lỗi permission. |
| Nhận telemetry từ tenant khác | Filter quá rộng, ACL sai hoặc bridge không kiểm tra tenant. | Hẹp filter, fix broker ACL, validation và audit. |
| Một publish tạo nhiều lần xử lý | Overlapping subscriptions, QoS redelivery, publisher retry hoặc nhiều clients. | `eventId`/unique constraint, phân tích topology. |
| Message đã tới nhưng JSON parser lỗi | Converter/schema mismatch, dữ liệu độc hại hoặc version cũ. | Quarantine, schema mapping, không retry vô hạn lỗi cố định. |
| Inbound nhận đúng topic nhưng DB ghi nhầm thiết bị | Không đối chiếu payload `deviceId` và received topic. | Parse/validate topic cụ thể và identity. |
| Sau reconnect không nhận topic trước đây | Session bị xóa, Client ID đổi, adapter không re-subscribe hoặc broker failover. | Test recovery, session/subscription state và active filters. |
| Subscribe filter mới nhưng nhận dữ liệu “cũ” | Retained snapshot và/hoặc session backlog. | Xử lý event-time, retained metadata, policy snapshot vs event. |
| Client ID trùng gây reconnect liên tục | Hai active subscribers cùng MQTT Client ID. | Quản lý Client ID theo instance/consumer ownership. |

**Không suy luận** rằng exception từ một Spring handler sau inbound sẽ làm broker tự động phát lại MQTT PUBLISH đến khi DB commit. MQTT ACK và transaction DB là hai cơ chế riêng; cách ack/manual ack và error channel phụ thuộc adapter/version/config.

### 15.1. Retry và DLQ/quarantine

- **Không retry vô hạn** một JSON sai schema, topic không thuộc tenant hoặc filter bị ACL từ chối.
- **Có thể retry có giới hạn** lỗi mạng, DB hoặc downstream không sẵn sàng; dùng backoff và metric.
- **Lưu bền vững** message quan trọng vào inbox/queue/outbox hoặc persistent store theo SLA.
- **Giữ eventId** để consumer idempotent khi cùng event được nhận lại hoặc replay.
- **Dùng error channel** của Spring Integration theo endpoint/flow phù hợp, không mặc định mọi lỗi client callback đều được đưa tới một channel chung.

### 15.2. Backpressure khi wildcard quá rộng

Một filter rộng như `devices/#` có thể đột ngột khiến inbound adapter nhận nhiều loại message và gấp nhiều lần lưu lượng dự kiến. Với `DirectChannel`, handler downstream blocking có thể kéo dài thời gian xử lý callback; với `ExecutorChannel`/`QueueChannel` phải giới hạn queue, thread pool, memory và policy khi full.

`QueueChannel` mặc định trong RAM không trở thành persistence khi subscriber dùng `cleanSession=false`. Session bền ở broker và queue bền trong Spring là hai cấp dữ liệu khác nhau.

## 16. Test flow không cần MQTT broker

Ví dụ mục 11 tách `TopicFilterFlowConfiguration` khỏi `MqttFilterTransportConfiguration`. Do đó test có thể nạp **chỉ flow/channel/validator/JSON parser** và tự đưa Spring message có `MqttHeaders.RECEIVED_TOPIC` vào channel.

Test này không đụng network, không mở MQTT client và không cần broker đang chạy.

Tạo `TopicFilterFlowTest.java` trong package `demo.mqttfilters`:

~~~java
package demo.mqttfilters;

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
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = TopicFilterFlowConfiguration.class)
@TestPropertySource(properties = "app.mqtt.tenant-id=tenant-a")
class TopicFilterFlowTest {

    @Autowired
    @Qualifier("mqtt.telemetry.in")
    MessageChannel input;

    @Autowired
    TelemetrySink sink;

    @Autowired
    TopicFilterValidator validator;

    @BeforeEach
    void clear() {
        sink.clear();
    }

    @Test
    void createsTenantScopedSubscriptionFilter() {
        assertEquals(
                "tenants/tenant-a/devices/+/telemetry",
                validator.subscriptionFilter());
    }

    @Test
    void acceptsMatchingTopicAndMatchingJsonDevice() {
        String json = "{\"eventId\":\"evt-test-1\","
                + "\"deviceId\":\"device-17\","
                + "\"celsius\":26.5}";

        boolean accepted = input.send(
                MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "tenants/tenant-a/devices/device-17/telemetry")
                        .build());

        assertTrue(accepted);
        assertEquals(
                List.of(new AcceptedTelemetry(
                        "tenants/tenant-a/devices/device-17/telemetry",
                        new TemperatureReading(
                                "evt-test-1", "device-17", 26.5))),
                sink.snapshot());
    }

    @Test
    void rejectsWrongTenantTopic() {
        String json = "{\"eventId\":\"evt-test-2\","
                + "\"deviceId\":\"device-17\","
                + "\"celsius\":25.0}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "tenants/tenant-b/devices/device-17/telemetry")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void rejectsEmptyDeviceLevel() {
        String json = "{\"eventId\":\"evt-test-3\","
                + "\"deviceId\":\"device-17\","
                + "\"celsius\":25.0}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "tenants/tenant-a/devices//telemetry")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void rejectsJsonDeviceDifferentFromTopic() {
        String json = "{\"eventId\":\"evt-test-4\","
                + "\"deviceId\":\"device-21\","
                + "\"celsius\":27.0}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "tenants/tenant-a/devices/device-17/telemetry")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void rejectsMalformedJson() {
        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(
                        "{\"eventId\":")
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "tenants/tenant-a/devices/device-17/telemetry")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }
}
~~~

Test chứng minh:

1. Subscription filter được xây có tenant scope đúng.
2. Flow nhận Spring message có topic thực và parse JSON.
3. Topic ngoài tenant, topic có device ID rỗng và payload không khớp bị chặn.
4. Sink chỉ ghi khi message đã validate.
5. Không cần mở kết nối broker.

**Giới hạn:** test **không chứng minh** MQTT broker đã match `+`/`#` đúng, đã trả SUBACK, delivery QoS, retained/session hay reconnect hoạt động. Những điều đó cần broker integration test.

### 16.1. Test một hàm so khớp MQTT filter tự viết có đủ không?

Nếu cần thực hành, có thể viết `matches(String filter, String topic)` theo MQTT 3.1.1 và test bảng ở mục 7. Nhưng **không dùng regex đơn giản kiểu `filter.replace("+", ".*")`**: phép thay này sai với cấp topic, `#` match zero cấp, dấu `$` và empty levels.

Một implementation local chỉ dùng để kiểm tra logic cấu hình hoặc visualization; integration test broker vẫn là phép thử cuối cùng cho behavior publish/subscribe thực tế.

## 17. Test end-to-end với MQTT broker và CLI

Giả định broker thử nghiệm ở `localhost:1883` và Mosquitto CLI đã cài. Không chạy các lệnh ngắt broker hoặc thay ACL trên production. Với broker TLS/auth, phải cấu hình chứng chỉ và credential đúng cho ứng dụng/CLI.

### 17.1. Subscribe filter tại CLI

Mở terminal A:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-topic-filter-observer-1 \
  -t 'tenants/tenant-a/devices/+/telemetry' \
  -q 1 -v
~~~

Đối số `-t` là **subscription filter**, không phải publish topic. Option `-v` hiển thị topic thực và payload để dễ kiểm tra.

### 17.2. Publish vào hai topics có match

Terminal B:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'tenants/tenant-a/devices/device-17/telemetry' \
  -q 1 \
  -m '{"eventId":"evt-cli-17","deviceId":"device-17","celsius":26.5}'
~~~

Sau đó:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'tenants/tenant-a/devices/device-21/telemetry' \
  -q 1 \
  -m '{"eventId":"evt-cli-21","deviceId":"device-21","celsius":27.0}'
~~~

Subscriber CLI có thể hiển thị hai dòng, đều nằm trong một MQTT filter:

~~~text
tenants/tenant-a/devices/device-17/telemetry {"eventId":"evt-cli-17","deviceId":"device-17","celsius":26.5}
tenants/tenant-a/devices/device-21/telemetry {"eventId":"evt-cli-21","deviceId":"device-21","celsius":27.0}
~~~

Spring application ví dụ cũng có thể nhận hai message đó qua inbound adapter và cập nhật `TelemetrySink` nếu chạy cùng broker và được cấp quyền.

### 17.3. Publish topic không match

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'tenants/tenant-b/devices/device-17/telemetry' \
  -q 1 \
  -m '{"eventId":"evt-other-tenant","deviceId":"device-17","celsius":26.0}'
~~~

Filter tenant-a **không match** topic tenant-b. Kết quả “không thấy message ở subscriber” có thể do topic không match, nhưng cũng có thể do ACL, subscriber không online hoặc broker khác; khi test, cần giữ điều kiện kết nối và quyền phù hợp để tránh kết luận sai.

### 17.4. Test single-level và multi-level filter

Mở hai CLI subscribers khác nhau:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-plus-1 -t 'devices/+/state' -v
~~~

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-hash-1 -t 'devices/#' -v
~~~

Publish lần lượt:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' -m 'ONLINE'
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/sensors/temp' -m '26.5'
~~~

Filter `devices/+/state` chỉ match publication đầu; `devices/#` match cả hai. Nếu các clients được cấp quyền tương ứng, đây là minh họa trực tiếp khác biệt `+` và `#`.

### 17.5. Test ngoại lệ $SYS

Dùng broker test hỗ trợ `$SYS`, subscribe tường minh `$SYS/#`. Không thể kỳ vọng filter `#` nhận những topic system đó. Tuy nhiên, không phải broker nào cũng public cùng tên topics hoặc cho phép tài khoản thử nghiệm subscribe `$SYS`; một test không thấy message có thể do broker support/ACL, không chứng minh quy tắc wildcard sai.

### 17.6. Ma trận integration tests

| Kịch bản | Cách thử | Cần quan sát |
| --- | --- | --- |
| Một cấp wildcard | `devices/+/state` với topic có đúng một cấp giữa. | Match. |
| Thêm một cấp | `devices/device-17/sensors/state`. | Không match filter trên. |
| Multi-level | `devices/#` với topic sâu nhiều cấp. | Match. |
| Zero level của `#` | `devices/#` và topic `devices`. | Match theo MQTT semantics. |
| Empty level của `+` | `devices//state`. | Broker có thể giao theo filter, business validator phải reject ID rỗng. |
| Topic `$SYS` | Filter `#` và `$SYS/#` trong broker test có hỗ trợ. | Quan sát ngoại lệ `$`. |
| Filter chồng lấp | Subscribe `sensors/#` và `sensors/+/temperature` trên cùng client. | Kiểm tra QoS/duplicate behavior và dedup. |
| SUBSCRIBE unauthorized | Principal chỉ được tenant-a, thử filter tenant-b. | Broker từ chối theo ACL. |
| clean session/restart | Tắt subscriber rồi reconnect cùng Client ID. | Subscription/backlog theo broker/session policy. |
| Retained publication | Publish retained state rồi subscribe filter mới. | Có thể nhận snapshot ngay; không nhầm với event live. |
| Nhiều instance | Hai subscriber khác Client ID; rồi thử ID trùng trong test. | Fan-out bình thường vs connection conflict. |
| Payload sai JSON | Topic match nhưng payload malformed. | Spring validator/quarantine, không xem là lỗi matching. |

## 18. Shared subscriptions và chia tải consumer

Một filter thường như:

~~~text
sensors/+/temperature
~~~

được nhiều MQTT clients đăng ký sẽ cho mỗi client nhận những publication phù hợp theo subscription riêng. Điều này **không** tương đương với queue competing consumers mà mỗi message chỉ có một worker xử lý.

Một số MQTT broker hỗ trợ **shared subscriptions** — trong MQTT 5 có cơ chế được chuẩn hóa và nhiều broker cũng cung cấp extension khi dùng MQTT 3.x — với một dạng thường thấy:

~~~text
$share/telemetry-workers/sensors/+/temperature
~~~

Ở đây `telemetry-workers` là nhóm shared subscription và `sensors/+/temperature` là filter được chia sẻ. **Không giả định** mọi broker, phiên bản protocol và ACL đều chấp nhận cú pháp `$share` hoặc có cùng chính sách cân tải/retained.

Lưu ý quan trọng:

1. Shared subscription là tính năng của broker/giao thức, không phải cơ chế tạo ra từ `DirectChannel` hay Client ID trùng.
2. Nó không bảo đảm processing exactly-once trong DB; vẫn cần `eventId`, idempotency và retry.
3. Ordering theo một thiết bị có thể cần partition/sequence policy; chia tải có thể làm message của cùng device đến các workers khác nhau.
4. Client IDs của các thành viên đang online vẫn phải khác nhau.
5. Cần test retained behavior, ACL, QoS, session, failover và compatibility của chính broker đã chọn.

Trong hệ thống cần xử lý sự kiện theo partition và replay bền vững lâu dài, có thể cân nhắc Kafka/JMS/AMQP hoặc một broker/queue phù hợp thay vì ép MQTT filter thuần đóng vai trò stream processor.

## 19. Vận hành: topic cardinality, performance và observability

Wildcard hẹp hay rộng ảnh hưởng trực tiếp lượng message mà subscriber nhận:

~~~text
telemetry/device-17             → Chỉ một topic cụ thể
telemetry/+/temperature         → Một lớp thiết bị, một loại dữ liệu
telemetry/#                     → Mọi cấp bên dưới telemetry
#                               → Rất rộng cho topic thường
~~~

Với một fleet lớn, `#` có thể nhận quá nhiều dữ liệu, làm tăng network bandwidth, converter allocations, JSON parse time và tải DB. Điều này có thể gây backpressure ngay cả khi MQTT connection vẫn hoạt động.

### 19.1. Metrics cần quan sát

| Metric/nhãn gợi ý | Giá trị vận hành |
| --- | --- |
| `mqtt_active_filters` | Số subscription filters đang được client quản lý. |
| `mqtt_received_messages_total{kind}` | Lưu lượng theo nhóm business, tránh label từng device nếu cardinality quá cao. |
| `mqtt_subscription_rejected_total` | Phát hiện ACL/filter cấu hình sai. |
| `mqtt_connection_recovery_total` | Theo dõi reconnect/re-subscribe. |
| `mqtt_received_topic_validation_errors_total` | Phát hiện topic sai shape/tenant. |
| `mqtt_payload_schema_errors_total` | Tách lỗi JSON/schema khỏi lỗi topic. |
| `mqtt_duplicate_event_total` | Kiểm tra idempotency và overlapping subscriptions. |
| `mqtt_consumer_backlog` | Đo queue/outbox lag. |
| `mqtt_business_processing_latency_ms` | Biết thời gian xử lý sau adapter, không chỉ MQTT connection health. |

Tên metric là **đề xuất thiết kế**, không phải bộ metric mặc định Spring Integration/Paho luôn tự phát đúng tên đó. Không dùng raw topic chứa device ID làm metric label vô hạn; cardinality có thể phá hỏng hệ thống monitoring.

### 19.2. Quy trình thay topic filter trong production

1. Xác định business use case và quyền truy cập.
2. Viết bảng match/non-match bao gồm empty levels và `$`.
3. Kiểm tra broker ACL và cảnh báo có thể nhận payload khác schema.
4. Deploy thử trên một client với Client ID riêng.
5. Theo dõi rate, queue depth, duplicate, parse errors và subscription state.
6. Thực nghiệm restart/reconnect/failover.
7. Thay/thu hẹp filter cũ theo kế hoạch, tránh overlap ngoài ý muốn.
8. Ghi audit desired/actual subscription filters và rollback plan.

Không chỉ sửa một chuỗi topic trong config rồi cho rằng broker luôn cập nhật filter ngay ở connection đang hoạt động. Cần hiểu lifecycle của adapter và cách áp dụng subscription changes.

## 20. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách điều tra/khắc phục |
| --- | --- | --- |
| Subscribe `devices/*/state` không nhận gì. | `*` không phải MQTT wildcard. | Dùng `devices/+/state`. |
| Subscribe `devices/#/state` bị từ chối. | `#` chỉ hợp lệ ở cấp cuối. | Dùng `devices/#` rồi route/validate, hoặc thiết kế hierarchy khác. |
| `devices/+/state` không match topic có hai cấp device. | `+` đúng một cấp. | Kiểm tra topic shape, dùng `#` khi thật sự cần nhiều cấp. |
| `devices/#` nhận cả topic `devices`. | `#` có thể match zero cấp. | Validate exact received topic trong Spring. |
| `devices/+/state` nhận topic `devices//state`. | Cấp rỗng vẫn có thể match `+`. | Reject device ID rỗng ở business validator. |
| `#` không nhận `$SYS`. | Ngoại lệ ký tự đầu `$`. | Dùng `$SYS/#` khi broker hỗ trợ và cấp quyền. |
| Subscription đúng nhưng handler parse sai. | Payload schema/encoding khác, adapter converter không phù hợp. | Kiểm tra converter, received topic và schema routing. |
| Một event ghi DB nhiều lần. | Overlap, QoS redelivery, nhiều subscribers hoặc retry app. | Dùng event ID/idempotency; bỏ filters chồng lấp không cần thiết. |
| Hai replicas tự đá connection. | Client ID trùng. | Unique Client ID per active connection. |
| Sau restart không nhận event offline. | clean session, Client ID, QoS/broker storage không phù hợp. | Test subscription persistence và broker backlog. |
| Service tenant-a đọc được data tenant-b. | Filter quá rộng/broker ACL sai. | Fix ACL và filter theo tenant, validate identity. |
| Chạy CLI subscribe nhưng không thấy publication. | Broker khác host/port, ACL, QoS/session, filter sai hoặc publisher không gửi. | Kiểm tra các điều kiện theo từng tầng. |
| Dynamic add/remove không tồn tại ở version project. | API Spring Integration phiên bản khác. | Kiểm tra API đúng version và thiết kế deploy/restart phù hợp. |
| Queue tăng nhanh sau đổi filter. | Filter quá rộng làm lưu lượng bùng nổ. | Hẹp filter, rate limit, backpressure/persistent queue. |
| Broker đã gửi PUBLISH nhưng DB không ghi. | Conversion/validation/business handler lỗi. | Error flow/quarantine/transaction, không chỉ sửa subscription. |

## 21. Bài tập thực hành: tách telemetry theo tenant và thiết bị

**Bối cảnh:** một nền tảng quản lý tòa nhà có hàng nghìn sensor thuộc các tenants khác nhau. Mỗi device publish nhiệt độ, độ ẩm, trạng thái ONLINE/OFFLINE và các cảnh báo. Một Spring Integration backend xử lý tenant-a, đồng thời một worker khác chỉ chịu trách nhiệm kiểm tra availability.

Yêu cầu:

1. Thiết kế namespace topic thống nhất: `tenants/{tenantId}/devices/{deviceId}/{kind}`.
2. Chọn subscription filters cho temperature, humidity, availability và nhóm tất cả sensor của tenant-a.
3. Viết bảng match/non-match ít nhất 12 trường hợp, có `+`, `#`, empty levels và ngoại lệ `$`.
4. Giải thích vì sao publisher không được gửi tới topic chứa wildcard.
5. Cấu hình `MqttPahoClientFactory` và `MqttPahoMessageDrivenChannelAdapter` subscribe `tenants/tenant-a/devices/+/telemetry` QoS 1.
6. Dùng `MqttHeaders.RECEIVED_TOPIC` để xác định device ID từ topic cụ thể; validate cùng payload JSON.
7. Kiểm tra tenant/device authorization bằng broker ACL và business validation, không dùng filter làm ranh giới bảo mật duy nhất.
8. Viết error flow/quarantine cho schema mismatch và topic invalid; không retry vô hạn message sai cố định.
9. Thử hai overlapping subscriptions trong một client với broker test và quan sát duplicate/QoS.
10. Thử hai subscriber clients khác Client ID cùng topic filter để thấy fan-out.
11. Thử Client ID trùng rồi giải thích vì sao không dùng cách này để chia tải.
12. Tạo pipeline availability khác schema với telemetry; route theo received topic hoặc tách adapter/client khi policy khác.
13. Test subscriber offline/reconnect với `cleanSession=false` và Client ID ổn định; đối chiếu QoS/session/broker persistence.
14. Đo lưu lượng, conversion time, queue backlog khi đổi filter từ `.../+/telemetry` sang `.../#`.
15. Xây unit test không broker cho topic validation và JSON, sau đó test subscription matching thực với Mosquitto CLI.
16. Nếu broker hỗ trợ, thử shared subscriptions theo tài liệu/version cụ thể và đánh giá điều kiện dedup/ordering.

**Tiêu chí đạt:** chỉ nhận và xử lý dữ liệu được quyền, không nhầm wildcard SUBSCRIBE với PUBLISH topic, validate topic thực, xử lý duplicate, hiểu reconnect/session, và không để filter quá rộng làm nghẽn Spring Integration flow.

## 22. Câu hỏi tự kiểm tra

1. Topic name và topic filter khác nhau ở đâu?
2. MQTT broker URL khác một Spring `MessageChannel` như thế nào?
3. `+` match bao nhiêu cấp topic? Nó có match một cấp rỗng không?
4. `#` được đặt ở đâu? `a/#` có match topic `a` không?
5. Vì sao `devices/#/state` và `devices/device+#` không phải filter hợp lệ?
6. Filter `devices/+/state` có match `devices/device-17/room/state` không?
7. Filter `#` có match `$SYS/broker/uptime` không? Vì sao?
8. Muốn subscribe system topic, nên dùng filter nào và cần thêm quyền gì?
9. MQTT topic names có phân biệt `Devices` và `devices` không?
10. Vì sao MQTT wildcard filter không phải Java regex?
11. Vì sao một subscription filter match topic không có nghĩa payload JSON hợp lệ?
12. Khi nào cần dùng `MqttHeaders.RECEIVED_TOPIC` thay vì `MqttHeaders.TOPIC`?
13. Overlapping subscriptions có tạo nguy cơ duplicate như thế nào?
14. Hai MQTT clients khác Client ID subscribe cùng một filter sẽ nhận message theo cơ chế nào?
15. QoS của publisher và QoS của subscriber filter khác nhau thế nào?
16. Vì sao QoS 2 không thay thế unique constraint của database?
17. `cleanSession=false` cần Client ID như thế nào để phục hồi session?
18. Một adapter dùng `DefaultPahoMessageConverter` có tự parse JSON thành DTO không?
19. Cách phân biệt topic filter chọn message và Spring router chọn business flow?
20. Khi thêm filter runtime, cần xử lý retained snapshots và subscription state ra sao?
21. Vì sao broker ACL cần thiết ngay cả khi filter được cố định theo tenant?
22. Shared subscription khác “hai clients cùng dùng Client ID” ở đâu?
23. Nếu mở rộng filter từ `devices/+/telemetry` sang `devices/#`, rủi ro hiệu năng nào xuất hiện?
24. Test flow dùng fake Spring message có chứng minh broker matching wildcard không?
25. Vì sao trạng thái online/reconnect tốt chưa chứng minh dữ liệu đã được commit ở DB?

**Gợi ý:** wildcard `+` match một cấp, `#` match phần còn lại và phải ở cuối; ngoại lệ `$` cần xử lý riêng; inbound adapter phát **topic thực** cho Spring flow, còn ACL, schema và idempotency vẫn thuộc trách nhiệm ứng dụng.

## 23. Kết luận

**Subscription pattern và wildcard topic** giúp một MQTT subscriber nhận message từ nhiều topic theo quy tắc chung mà không cần tạo một subscription cho mỗi thiết bị:

- `+` match **đúng một cấp** topic, có thể là cấp rỗng; `#` match **không hoặc nhiều cấp** và phải đứng cuối filter.
- Một PUBLISH phải dùng **topic name cụ thể**, không dùng `+`/`#` như subscription.
- Topic bắt đầu `$` có ngoại lệ khi filter bắt đầu bằng wildcard `#`/`+`; muốn nhận system topics phải dùng prefix phù hợp và được broker cấp quyền.
- Filter chồng lấp, QoS và session/reconnect có thể tác động đến số lần delivery; consumer phải được thiết kế idempotent.
- `MqttPahoMessageDrivenChannelAdapter` subscribe topic filters ở broker rồi chuyển Spring message vào `MessageChannel`; `MqttHeaders.RECEIVED_TOPIC` cho biết **topic name đã nhận**, cần được validate trước khi xử lý business.
- Broker ACL, tenant/topic validation, schema contract, error handling, backpressure và test broker thật là điều kiện để wildcard subscription vận hành an toàn.

Trong module **SPRING_INTEGRATION_ADAPTERS**, MQTT subscription filters là ranh giới chọn dữ liệu từ broker, còn Spring Integration channels/routers/handlers chịu trách nhiệm chuyển đổi và xử lý với file, SFTP, HTTP, JMS, AMQP, Kafka hoặc database. Thiết kế đúng phân biệt rõ **broker matching → inbound conversion → topic/identity validation → business processing**, để hệ thống vừa linh hoạt mở rộng số thiết bị vừa duy trì tính đúng đắn và khả năng quan sát.

