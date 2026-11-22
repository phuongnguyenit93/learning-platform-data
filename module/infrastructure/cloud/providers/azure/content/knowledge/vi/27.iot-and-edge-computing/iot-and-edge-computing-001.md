# Kiến trúc tiếp nhận telemetry IoT trên Azure

Hãy tưởng tượng một nhà máy có 15.000 cảm biến đo nhiệt độ, độ rung và điện năng. Thiết bị gửi dữ liệu qua mạng di động, Wi-Fi hoặc gateway tại biên. Một số thiết bị chỉ có kết nối vài phút mỗi giờ; một số phát nhiều mẫu mỗi giây. Trung tâm vận hành muốn phát hiện quá nhiệt nhanh chóng, trong khi bộ phận phân tích muốn lưu dữ liệu nhiều tháng để dự báo bảo trì.

Bài toán không chỉ là mở một HTTP endpoint nhận JSON. Một nền tảng IoT đáng tin cậy phải **xác thực danh tính từng thiết bị, tiếp nhận dữ liệu theo quy mô, xử lý trùng/lỗi/mất kết nối, định tuyến theo nhu cầu, lưu trữ an toàn, quan sát được hệ thống và kiểm soát chi phí**.

Trên Microsoft Azure, một phương án phổ biến sử dụng **Azure IoT Hub** để kết nối và quản lý thiết bị, **Azure IoT Hub Device Provisioning Service (DPS)** để cấp phát ban đầu, **Azure IoT Edge hoặc các giải pháp xử lý tại biên phù hợp** để đệm và xử lý gần thiết bị, kết hợp **Azure Functions, Azure Stream Analytics, Azure Event Hubs, Azure Data Explorer, Azure Blob Storage/ADLS Gen2 và Databricks** cho những đường xử lý khác nhau.

Bài học thuộc chương **IoT và xử lý tại biên** trong mô-đun **CLOUD_PROVIDERS_AZURE**. Nó nối kiến thức Azure subscription, resource group, Microsoft Entra ID, mạng ảo, lưu trữ, giám sát, bảo mật và chi phí thành một kiến trúc ứng dụng IoT có thể triển khai và vận hành.

**Phạm vi:** kiến trúc và thực hành với Azure IoT Hub cho device-to-cloud (D2C) telemetry. Những gói dịch vụ, giới hạn và tính năng IoT có thể thay đổi theo thời gian; kiểm tra SKU, API/SDK, khu vực và quota thực tế trước khi triển khai. Ví dụ chỉ minh họa trên môi trường lab được cho phép, không thực thi trực tiếp lên subscription thật.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt telemetry, device state, command, device twin, event và business alert.
2. Vẽ kiến trúc đầu cuối từ sensor, gateway, IoT Hub tới hot path và cold path.
3. Chọn đúng vai trò của IoT Hub, Event Hubs, DPS, IoT Central và edge processing.
4. Giải thích quá trình provisioning, device identity, SAS/X.509 và vòng đời credential.
5. So sánh MQTT, AMQP, HTTPS và các phương án vượt mạng hạn chế.
6. Thiết kế telemetry envelope có device ID, event ID, sequence, timestamp, schema version, đơn vị đo và quality flags.
7. Hiểu IoT Hub built-in Event Hubs-compatible endpoint, message routes, custom endpoints, enrichments và fallback.
8. Thiết kế xử lý thời gian gần thực bằng Azure Functions/Stream Analytics và lưu trữ dài hạn bằng ADLS Gen2/Blob.
9. Nhận biết at-least-once delivery, partition-scoped ordering, idempotency, retry, backpressure và poison messages.
10. Thiết kế edge buffering/store-and-forward khi thiết bị mất kết nối.
11. Tính toán sơ bộ dung lượng thông điệp, lưu lượng, đơn vị IoT Hub, quota và chi phí.
12. Thiết lập bảo mật bằng device-level credentials, least privilege, private access, encryption và data lifecycle.
13. Thực hành Azure CLI/Python SDK gửi bản tin mô phỏng và kiểm tra đường nhận.
14. Thiết kế monitoring, incident runbooks, kiểm thử tải, rollback và recovery.
15. Áp dụng checklist production cho một hệ thống IoT đa thiết bị/đa cơ sở.

## 2. Telemetry là gì và không phải là gì?

### 2.1. Dữ liệu đo liên tục

**Telemetry** là dữ liệu quan sát được thiết bị gửi về, thường bao gồm:

- Nhiệt độ, độ ẩm, áp suất, điện áp, dòng điện.
- GPS/speed/location khi có quyền và mục đích hợp pháp.
- Heartbeat, firmware version, battery percentage.
- Tình trạng động cơ, thông số rung, uptime.
- Số đo môi trường hoặc năng lượng theo thời gian.

Ví dụ tài liệu:

~~~json
{
  "schemaVersion": "1.0",
  "eventId": "evt-3f9a",
  "deviceId": "motor-042",
  "bootId": "boot-19",
  "sequence": 1835,
  "eventTimeUtc": "2026-11-20T08:30:00.000Z",
  "measurements": {
    "temperatureC": 78.4,
    "vibrationMmS": 4.8,
    "currentA": 3.2
  },
  "quality": "ok"
}
~~~

Đây là payload mẫu. Trong một pipeline đúng, deviceId trong **message body không nên được coi là bằng chứng xác thực thiết bị**; ứng dụng phải đối chiếu với identity do IoT Hub xác nhận thông qua metadata hệ thống và chính sách registry. Một thiết bị bị chiếm quyền có thể gửi bất cứ nội dung JSON nào.

### 2.2. Phân biệt bốn luồng

| Loại | Chiều đi | Mục đích | Ví dụ |
|---|---|---|---|
| Device-to-cloud telemetry | Thiết bị → cloud | Gửi số đo/sự kiện | Nhiệt độ mỗi phút |
| Device state/reported properties | Thiết bị → cloud registry/twin | Trạng thái cấu hình/khả năng | Firmware version, connectivity state |
| Cloud-to-device command | Cloud → thiết bị | Yêu cầu thao tác | Khởi động đo ngay, reboot có kiểm soát |
| Desired configuration | Cloud → device twin | Khai báo trạng thái mong muốn | Chu kỳ đo = 60 giây |

Không nên đưa mọi trạng thái dài hạn vào luồng telemetry nếu cần truy vấn cấu hình hiện tại qua device twin. Ngược lại, **device twin không phải kho thời gian chuỗi chứa hàng tỷ mẫu**. Command và telemetry còn khác nhau về xác nhận, timeout, retry và tác động vật lý.

### 2.3. Telemetry event khác business alert

Một sự kiện nhiệt độ 78,4°C là **quan sát**. Cảnh báo “Động cơ 42 quá nhiệt 5 phút liên tục” là **kết luận xử lý** dựa trên quy tắc/time window.

Nếu cảm biến gửi lặp một mẫu ba lần, pipeline phải tránh phát ba alert hoặc tính ba lần vào trung bình. Nếu thiết bị gửi dữ liệu trễ, nghiệp vụ cần quyết định dùng thời gian đo hay thời gian cloud nhận.

## 3. Kiến trúc tham chiếu end-to-end

~~~mermaid
flowchart LR
    S["Sensors / devices"] --> G["Edge gateway / IoT Edge khi cần"]
    S --> I["Azure IoT Hub"]
    G --> I
    DPS["IoT Hub DPS"] -. "Provision identity/assignment" .-> S
    DPS -. "Assign hub" .-> I
    I --> R["Message routing / built-in endpoint"]
    R --> H["Hot path: Stream Analytics / Functions"]
    R --> C["Cold path: Blob / ADLS Gen2"]
    H --> A["Alerts / operational store / dashboards"]
    C --> T["Databricks / Data Explorer / analytics"]
    H --> M["Azure Monitor / runbook"]
    T --> M
~~~

Các tầng có trách nhiệm riêng:

1. **Device/gateway:** lấy số đo, đảm bảo định dạng, timestamp, bộ đệm, retry.
2. **Provisioning và identity:** đăng ký danh tính, cấp credential, gán thiết bị tới hub.
3. **IoT ingestion:** xác thực thiết bị, chấp nhận D2C messages theo quota, định tuyến.
4. **Hot path:** phát hiện bất thường, enrich/aggregate, tạo alerts/operational views.
5. **Cold path:** lưu dữ liệu thô/được chuẩn hóa để đối soát và phân tích dài hạn.
6. **Governance:** quyền truy cập, mã hóa, retention, kiểm toán.
7. **Operations:** metrics, logs, alerting, incident handling và cost management.

**Thông điệp đã được IoT Hub chấp nhận không có nghĩa mọi hệ thống phía sau đã xử lý thành công.** Từng chặng cần có cơ chế ghi nhận tiến độ, xử lý retry, quan sát consumer lag và kiểm thử phục hồi.

### 3.1. Data flow ở mức sự kiện

~~~mermaid
sequenceDiagram
    participant D as Device
    participant H as IoT Hub
    participant R as Route / Event endpoint
    participant P as Processor
    participant L as ADLS / Data store
    participant O as Operator

    D->>H: Authenticate + send telemetry
    H-->>D: Protocol-level acknowledgement
    H->>R: Route accepted message
    R->>P: Consume event
    P->>P: Validate, deduplicate, process
    P->>L: Persist raw/processed records
    P->>O: Alert only when business rule matches
~~~

ACK từ thiết bị tới IoT Hub chỉ xác nhận ở phạm vi tương tác giao thức/service được hỗ trợ, **không phải cam kết lưu hồ sơ cuối cùng, không phải xác nhận alert đã đến người trực ca**. Để cung cấp end-to-end guarantees, phải thiết kế downstream checkpoints, idempotency và nghiệp vụ xác nhận riêng.

## 4. Chọn dịch vụ đúng vai trò

### 4.1. Azure IoT Hub

**Azure IoT Hub** được thiết kế cho giao tiếp giữa thiết bị IoT và cloud:

- Device registry và danh tính riêng cho từng thiết bị.
- Device-to-cloud telemetry ingestion.
- Cloud-to-device communication theo SKU/tính năng được hỗ trợ.
- Device twins, jobs hoặc direct methods theo tier và capability.
- Message routing tới các endpoints được hỗ trợ.
- Device authentication bằng những cơ chế như SAS hoặc X.509.
- Giám sát device connectivity, ingress, routing và quota.

Sử dụng IoT Hub khi yêu cầu **danh tính thiết bị, vòng đời kết nối và quản lý thiết bị**, không chỉ nhận một dòng sự kiện vô danh.

### 4.2. Azure Event Hubs

**Azure Event Hubs** là dịch vụ streaming event ingestion tổng quát với partitions, consumer groups và các công cụ stream processing.

| Câu hỏi | IoT Hub | Event Hubs |
|---|---|---|
| Có device registry riêng? | Có | Không tương đương |
| Có Device Provisioning Service gán thiết bị? | Có thể tích hợp DPS | Không phải cơ chế chuẩn của Event Hubs |
| Có device twins/methods? | Theo tier/tính năng | Không phải chức năng cốt lõi |
| Phân phối stream sự kiện partitioned? | Có qua event endpoints | Có |
| Phù hợp generic logs/events/telemetry từ backend? | Có thể, nhưng thường dư abstraction | Rất phù hợp |
| Device-level identity/management là trọng tâm? | Có | Không |

Nếu 100.000 cảm biến thật cần enrollment, certificate rotation và quản lý online/offline, IoT Hub thường là ứng viên chính. Nếu backend ứng dụng đã xác thực gửi một lượng lớn application events thuần túy, Event Hubs có thể đủ.

### 4.3. IoT Hub built-in endpoint không phải Event Hubs namespace độc lập

IoT Hub có **built-in Event Hubs-compatible endpoint** để các stream consumers tương thích Event Hubs đọc device-to-cloud messages. Tuy nhiên:

- Endpoint này thuộc IoT Hub, không phải một Event Hubs namespace do bạn tạo.
- Nó có cấu hình/partition/retention/authorization riêng theo IoT Hub.
- Không phải tất cả Event Hubs management features và pricing options áp dụng nguyên trạng.
- Nếu muốn một stream độc lập cho nhiều nhóm consumer, có thể **route IoT Hub tới một Event Hubs custom endpoint** rồi dùng namespace đó theo nhu cầu.

Đừng nhầm **Event Hubs-compatible endpoint** của IoT Hub với một Event Hub vừa tự provision.

### 4.4. Azure IoT Hub Device Provisioning Service (DPS)

**DPS** giúp thực hiện zero-touch provisioning: một thiết bị mới dùng thông tin enrollment/attestation để được gán tới IoT Hub phù hợp, thay vì hard-code tất cả hub hostnames và credentials trong firmware.

DPS có thể dùng những phương thức attestation được hỗ trợ như X.509 và symmetric keys, cùng tùy chọn bảo mật dựa trên phần cứng như TPM theo device/platform và dịch vụ.

DPS không biến một thiết bị không đáng tin thành thiết bị an toàn: khóa/certificate nguồn vẫn phải được tạo, lưu, cấp phát và thu hồi theo quy trình bảo mật.

### 4.5. Azure IoT Central

**IoT Central** hướng tới phát triển giải pháp IoT ứng dụng/điều hành theo mô hình được quản lý cao hơn, với device templates, dashboards và workflows theo khả năng cung cấp hiện hành.

- Dùng khi muốn có nhanh một ứng dụng IoT hướng nghiệp vụ và phù hợp chức năng được cung cấp.
- Dùng kiến trúc IoT Hub + data services tự xây khi cần điều khiển chi tiết ingestion, routing, data contracts hoặc nhiều pipelines riêng.

Không quyết định chỉ qua tên sản phẩm; hãy xác minh roadmap, pricing, region, feature availability và quyền sở hữu dữ liệu ở thời điểm chọn.

### 4.6. Azure IoT Edge và xử lý ở biên

IoT Edge và các giải pháp edge Azure phù hợp có thể giúp chạy workloads gần thiết bị, giảm lưu lượng, xử lý cục bộ và đệm dữ liệu khi mạng gián đoạn. Những mô hình mới như Azure IoT Operations có deployment prerequisites và cách quản lý khác IoT Edge truyền thống; **không áp một bộ lệnh/tính năng edge cho mọi sản phẩm**.

Chọn edge khi có:
- Latency cần phản hồi tại chỗ.
- Mạng gián đoạn hoặc chi phí truyền tải lớn.
- Nhu cầu lọc/deduplicate/aggregate trước khi gửi cloud.
- Dữ liệu nhạy cảm cần xử lý trước khi rời nhà máy.
- Các protocol thiết bị công nghiệp chưa thể kết nối IoT Hub trực tiếp.

## 5. Thiết bị, identity và provisioning

### 5.1. Vòng đời thiết bị

~~~mermaid
flowchart LR
    M["Manufacture / enroll"] --> P["Provision via DPS"]
    P --> R["Register identity in IoT Hub"]
    R --> C["Connect and authenticate"]
    C --> O["Send telemetry / receive config"]
    O --> K["Rotate key / update certificate"]
    K --> O
    O --> D["Disable / retire / delete identity"]
~~~

Từng giai đoạn cần chủ sở hữu và log kiểm toán. Không dùng chung một symmetric key toàn hệ thống nếu có thể cấp danh tính riêng; khi một thiết bị bị lộ khóa, không nên gây sự cố cho toàn bộ fleet.

### 5.2. Symmetric key và SAS token

Trong một kịch bản lab, device identity có thể dùng symmetric key và SDK tạo **Shared Access Signature (SAS) token** để xác thực với IoT Hub.

Rủi ro:
- Thiết bị bị đánh cắp có thể lộ khóa.
- Shared keys lưu trong firmware plaintext dễ bị copy.
- Token/credential hết hạn khiến thiết bị mất kết nối.
- Credential bị lộ ở log hoặc source repo.
- Sử dụng hub-level connection string trên device trao quyền quá rộng.

Trong production ưu tiên lưu bí mật trong secure element/TPM khi phù hợp, rotation/revocation và không đưa khóa dịch vụ lên thiết bị.

### 5.3. X.509 certificates

X.509 có thể giúp mỗi thiết bị có private key riêng và chứng minh danh tính với chứng chỉ/chain được thiết kế đúng. Cần:

1. Trust chain/CA và loại enrollment được hỗ trợ.
2. Bảo vệ private key trong phần cứng/secure store.
3. Quản lý thời hạn chứng chỉ và rotation.
4. Thu hồi/disable thiết bị bị xâm nhập.
5. Điều phối certificate change không gây downtime toàn fleet.
6. Kiểm thử hệ thống khi certificate hết hạn hoặc clock sai.

**X.509 không bảo đảm an toàn nếu private key vẫn được copy tự do hoặc provisioning server tin một certificate không được xác minh.**

### 5.4. DPS enrollment và assignment

Một luồng điển hình:

~~~mermaid
sequenceDiagram
    participant D as New device
    participant P as DPS
    participant H as Assigned IoT Hub
    D->>P: Enrollment/attestation request
    P->>P: Verify enrollment and choose hub
    P-->>D: Assignment / hub info
    D->>H: Authenticate with provisioned identity
    H-->>D: Connection established
    D->>H: Device-to-cloud telemetry
~~~

Có thể dùng **individual enrollments** hoặc **enrollment groups** tùy thiết bị và phương thức attestation. Assignment policy có thể hướng tới cân bằng fleet/region/hub theo điều kiện được hỗ trợ.

DPS thực hiện provisioning, **không thay đường xử lý telemetry liên tục**. Sau provisioning, thiết bị gửi số đo tới IoT Hub đã được gán.

### 5.5. Device twin và reported/desired properties

Một device twin biểu diễn metadata/cấu hình của device theo mô hình JSON:

~~~json
{
  "properties": {
    "desired": {
      "samplingIntervalSeconds": 60
    },
    "reported": {
      "firmwareVersion": "2.3.1",
      "samplingIntervalSeconds": 60,
      "sensorHealth": "ok"
    }
  }
}
~~~

JSON trên là phần minh họa, không phải toàn bộ response twin. Cần phân biệt:

- **Desired:** trạng thái cloud muốn thiết bị áp dụng.
- **Reported:** trạng thái thiết bị cho biết đang áp dụng.
- **Tags:** metadata cloud-side theo quyền được cấp.

Đừng tạo một reported property mới cho mỗi điểm đo nhiệt độ. Twins thích hợp cho trạng thái và cấu hình, không phải bảng time-series hàng tỷ mẫu.

## 6. Giao thức thiết bị → Azure

### 6.1. So sánh MQTT, AMQP và HTTPS

| Giao thức | Khi phù hợp | Điểm lưu ý |
|---|---|---|
| MQTT trên TLS | Thiết bị hạn chế tài nguyên, kết nối lâu dài | Session/reconnect/QoS theo IoT Hub support; không phải generic MQTT broker |
| MQTT over WebSockets | Mạng chỉ cho HTTPS/WebSockets | TLS/443, overhead và proxy compatibility |
| AMQP trên TLS | SDK/gateway mạnh, multiplex/messaging | Cần hiểu connection/session và network policy |
| AMQP over WebSockets | Proxy hạn chế port | TLS/443, kết nối dài |
| HTTPS | Trường hợp đơn giản, gửi không liên tục | Overhead request/response, tính năng receive/feedback không giống persistent protocols |

Các cổng thường gặp ở kết nối TLS trực tiếp gồm MQTT 8883 và AMQP 5671; WebSockets/HTTPS thường dùng 443. **Kiểm tra cổng/giao thức chính xác theo Azure IoT SDK/version và chính sách mạng đang dùng**, không mở mọi cổng chỉ vì ví dụ.

### 6.2. MQTT của IoT Hub không phải broker MQTT tổng quát

IoT Hub hỗ trợ các cách kết nối MQTT và topic conventions dành cho IoT Hub. Không mặc định thiết bị có thể tự do publish/subscribe mọi topic tùy ý như một MQTT broker phổ thông, hoặc dùng mọi tính năng của tất cả phiên bản MQTT.

Với thiết bị mới, ưu tiên **Azure IoT Device SDK** phù hợp ngôn ngữ/thiết bị để SDK quản lý giao thức, authentication, TLS và reconnect. Nếu phải dùng raw MQTT client, đọc protocol-level documentation và kiểm thử đầy đủ.

### 6.3. Mạng không ổn định

Một cảm biến dùng LTE có thể mất kết nối giữa lúc gửi:

- Device cần có buffer và chính sách giới hạn dung lượng cục bộ.
- Retry với exponential backoff và jitter.
- Không tạo lại eventId mỗi lần retry cùng một mẫu.
- Có sequence/boot ID để nhận biết thiếu/lặp.
- Phân biệt send accepted với end-to-end processed.
- Theo dõi thời gian backlog và tỷ lệ drops.
- Có chính sách lấy mẫu/sampling khi quá tải.

Không retry vô hạn ở tốc độ tối đa: điều đó có thể gây battery drain, bão hòa hub và tăng chi phí.

## 7. Thiết kế telemetry contract

### 7.1. Envelope khuyến nghị

~~~json
{
  "schemaVersion": "1.0",
  "eventId": "evt-20261120-00183",
  "deviceId": "motor-042",
  "siteId": "factory-hcm",
  "bootId": "boot-19",
  "sequence": 1835,
  "eventTimeUtc": "2026-11-20T08:30:00.000Z",
  "firmwareVersion": "2.3.1",
  "measurements": {
    "temperatureC": 78.4,
    "vibrationMmS": 4.8,
    "currentA": 3.2
  },
  "quality": {
    "sensorStatus": "ok",
    "batteryPct": 92
  }
}
~~~

Không phải mọi trường đều phải được gửi lặp trong payload nếu đã có nguồn metadata tin cậy; ưu tiên cân bằng **kích thước message, khả năng truy xuất và data governance**.

### 7.2. Phân tích từng trường

| Field | Mục đích | Nguyên tắc |
|---|---|---|
| schemaVersion | Kiểm soát thay đổi contract | Version có tài liệu, backward compatibility |
| eventId | Idempotency/dedup | Giữ ổn định qua retry |
| deviceId | Mối liên hệ nghiệp vụ với thiết bị | Đối chiếu identity hệ thống từ IoT Hub |
| siteId | Phân vùng cơ sở/vị trí | Không tin tùy ý vào client khi dùng để phân quyền |
| bootId | Phân biệt các chu kỳ khởi động | Kết hợp sequence để phát hiện duplicate |
| sequence | Số thứ tự do device tạo | Có thể reset khi boot, cần hợp nhất cùng bootId |
| eventTimeUtc | Thời điểm cảm biến đo | Chấp nhận clock skew và clock quality |
| firmwareVersion | Phục vụ phân tích lỗi theo version | Không coi là bằng chứng đã được attestation |
| measurements | Các số đo kỹ thuật | Có unit, range, calibration |
| quality | Chất lượng/health/flags | Phân biệt unknown, invalid và 0 |

### 7.3. Units, timezone và độ chính xác

Một giá trị 78.4 không có đơn vị là không đủ. Nên dùng tên trường có đơn vị hoặc một schema rõ đơn vị.

- Temperature: °C hay °F?
- Vibration: mm/s RMS hay acceleration g?
- Energy: Wh hay kWh?
- Time: UTC ISO 8601 và offset?
- Location: hệ tọa độ nào và độ chính xác bao nhiêu?
- Precision: kiểu decimal/double và rounding policy?

Trong analytics, không nhân đôi doanh thu/điện năng chỉ vì hai đơn vị đo được hiểu khác nhau; cần schema evolution và contract tests.

### 7.4. Metadata hệ thống và nguồn danh tính

IoT Hub có metadata do service xử lý/đính kèm, chẳng hạn device identity và thời gian nhận tùy endpoint/protocol. Consumer nên:

1. Đọc device identity từ system properties khi API cung cấp.
2. So sánh với deviceId trong payload nếu cần, không tin payload một mình.
3. Ghi thời gian cloud nhận/enqueue riêng với eventTimeUtc.
4. Ghi message ID/correlation ID của ứng dụng để dedup/tracing.
5. Không đưa account keys hoặc raw SAS token vào payload.
6. Cẩn thận khi sử dụng metadata của hub/protocol trong route queries.

### 7.5. Schema evolution

Nếu firmware v2 thêm field vibrationMmS nhưng firmware v1 không có:

- Giữ version field rõ.
- Quy định default/missing values.
- Phân biệt trường không có với giá trị 0.
- Downstream parser phải xử lý nhiều version trong giai đoạn rollout.
- Đưa schema lạ vào quarantine thay vì loại bỏ âm thầm.
- Có owner phê duyệt breaking changes.
- Có plan backfill/replay dữ liệu nếu transformation thay đổi.

**Telemetry contract là giao ước giữa firmware, ingestion và analytics**. Nó cần test cùng quá trình phát hành ứng dụng, không chỉ kiểm thử riêng cloud.


## 8. Azure IoT Hub: lớp ingestion và điều tiết tải

### 8.1. Luồng thiết bị gửi D2C

~~~mermaid
flowchart LR
    D["Device SDK"] --> A["TLS + device auth"]
    A --> H["IoT Hub ingress"]
    H --> V["Validate protocol / quota"]
    V --> R["Message routing"]
    R --> E["Built-in Event Hubs-compatible endpoint"]
    R --> C["Custom endpoint(s)"]
    E --> P["Stream consumer"]
    C --> S["Storage / downstream services"]
~~~

Một thông điệp qua IoT Hub thường trải qua kết nối, authentication, service acceptance, routing và downstream consumer. Việc thiết bị gửi thành công không đồng nghĩa message đã xuất hiện trong báo cáo.

### 8.2. IoT Hub units, tier và quotas

Azure IoT Hub có các mức dịch vụ và capacity units với các quota/throttling khác nhau. Khi thiết kế cần kiểm tra:

- Số thiết bị có thể đăng ký và số kết nối.
- Khối lượng device-to-cloud messages mỗi ngày theo tier/unit.
- Giới hạn throughput/burst cho D2C operations.
- Message size limit, metering granularity và billing rules.
- Routing throughput/custom endpoint availability.
- Consumer partitions và retention của built-in endpoint.
- Giới hạn service operations khác telemetry.
- Region, availability và quota request process.

Không dùng con số quota từ một SKU khác làm giả định cho tất cả. SKU dành cho lab có thể thiếu những chức năng như production deployment cần.

### 8.3. Khi gặp throttling

Nếu thiết bị đồng loạt gửi một burst lớn:

1. IoT Hub có thể trả mã lỗi/thông báo throttling theo SDK/protocol.
2. Device cần retry với exponential backoff và jitter.
3. Edge buffer cần giữ dữ liệu theo storage policy.
4. Fleet có thể cần phân tán chu kỳ gửi tránh cùng phút.
5. Nhóm vận hành xem lại IoT Hub units/quota và downstream capacity.
6. Nếu vượt giới hạn của một hub hoặc region, phải tính chiến lược multi-hub có quản lý provisioning.

**Scale-out ở stream processor không nâng quota ingress của IoT Hub.** Ngược lại, tăng IoT Hub units cũng không tự giải quyết consumer đọc chậm.

### 8.4. Tách ingress khỏi processing

Không nên để firmware gọi trực tiếp vào database hoặc business APIs phức tạp cho mỗi mẫu, vì:

- Thiết bị phải giữ nhiều credentials và dependencies.
- Upstream bị coupling với schema/latency của downstream.
- Mất database khiến toàn bộ kết nối thiết bị bị ảnh hưởng.
- Khó thay đổi pipeline mà không cập nhật firmware.
- Khó kiểm soát backpressure và retries.

IoT Hub làm lớp ingestion, sau đó định tuyến sang các luồng xử lý với những trách nhiệm riêng.

## 9. Message routing: đưa telemetry tới đúng đích

### 9.1. Vì sao cần routing?

Ví dụ nhà máy muốn:

- Gửi **tất cả telemetry** tới ADLS Gen2/Blob để lưu trữ.
- Gửi sự kiện nhiệt độ cao tới stream processor.
- Gửi thông điệp chất lượng kém vào kênh giám sát.
- Tách dữ liệu theo loại event hoặc nhà máy khi chính sách cho phép.

Message routing của IoT Hub giúp gửi các thông điệp thỏa điều kiện tới các endpoints được hỗ trợ, thay vì firmware phải gửi nhiều bản sao tới nhiều hệ thống.

### 9.2. Những endpoint và hướng đi điển hình

| Đích | Mục đích | Điểm cần chú ý |
|---|---|---|
| Built-in Event Hubs-compatible endpoint | Consumer đọc telemetry stream từ hub | Retention/partitions/consumer groups theo cấu hình IoT Hub |
| Custom Azure Event Hubs endpoint | Tách stream để nhiều consumers xử lý | Có namespace, quota, RBAC, retention và phí riêng |
| Azure Blob Storage endpoint | Lưu D2C data cho cold path | File format/batching, naming, latency và retention |
| Service Bus queue | Hàng đợi công việc downstream được hỗ trợ | Không tối ưu thay thế kho time-series vô hạn |
| Service Bus topic | Fan-out workload events theo subscription filters | Xử lý duplicate/TTL/dead-letter theo thiết kế downstream |

Hỗ trợ endpoint, authentication và route source có giới hạn khác nhau tùy IoT Hub tier. **ADLS Gen2 thường dựa trên Azure Blob Storage capabilities**, nhưng các yêu cầu filesystem/hierarchical namespace, path, file format và pipeline phải được kiểm tra khi nối với route storage.

### 9.3. Route source, condition và priority

Một route có các yếu tố:

- **Source:** loại event như device telemetry theo khả năng cấu hình.
- **Condition/query:** biểu thức dùng system properties, application properties hoặc payload body khi routing dựa body được hỗ trợ.
- **Endpoint:** nơi gửi dữ liệu sau khi điều kiện khớp.
- **Enabled status:** route có hoạt động hay không.

Ví dụ ý tưởng:

~~~text
Route raw-all:
  Source: Device Telemetry Messages
  Condition: true
  Endpoint: Storage archive

Route operational-hot:
  Source: Device Telemetry Messages
  Condition: messageType = "telemetry"
  Endpoint: Event Hubs analytics

Route urgent:
  Source: Device Telemetry Messages
  Condition: priority = "high"
  Endpoint: Event Hubs alerting
~~~

Đây là mô tả kiến trúc, **không phải cú pháp hoàn chỉnh của Azure CLI hoặc route query DSL**. Condition thực phải dùng syntax supported và property naming chính xác. Không tự xem chuỗi JSON payload bất kỳ là route property.

### 9.4. Route query trên body cần metadata phù hợp

Khi IoT Hub cần phân tích **JSON body** cho route condition, message thường phải khai báo content type và encoding như:

~~~text
contentType: application/json
contentEncoding: utf-8
~~~

Khi dùng SDK, đây là message properties/metadata theo SDK, không nhất thiết là hai trường trong JSON body.

Nếu firmware quên thiết lập content type/encoding, route dựa trên body có thể không hoạt động như dự kiến dù message được hub nhận. Nếu mục tiêu chỉ là phân loại loại thông điệp, có thể dùng application property được kiểm soát như messageType hoặc priority để tránh parse body phức tạp ở routing layer.

### 9.5. Routing fallback và built-in endpoint

Một sai lầm dễ gặp: “IoT Hub luôn gửi một bản sao tới built-in endpoint kể cả khi đã bật custom routes”.

Thực tế cần **kiểm tra cấu hình routing tới built-in endpoint và fallback**. Khi có message routes, luồng đi mặc định có thể thay đổi; những messages không khớp route có thể được xử lý theo fallback settings. Thiết kế phải xác định rõ:

- Route nào cần gửi mọi telemetry tới cold path?
- Built-in endpoint có còn nhận messages không?
- Route nào là route tới built-in events endpoint khi cần?
- Fallback có bật theo đúng ý định không?
- Có message nào không khớp route bị bỏ khỏi downstream không?

Kiểm thử từng kịch bản bằng device test và endpoint consumer; không suy luận việc route được cấu hình thành công nghĩa là dữ liệu chắc chắn xuất hiện ở đích.

### 9.6. Message enrichment

Message enrichments có thể thêm metadata của IoT Hub vào messages được định tuyến theo khả năng dịch vụ, ví dụ thông tin tenant/site có nguồn từ device twin tags hoặc hub information.

Lợi ích:
- Downstream không cần tin hoàn toàn vào tenantId trong payload.
- Có thể giảm số truy vấn registry/twin ở consumer.
- Dễ gắn ownership/schema/route metadata.

Rủi ro:
- Metadata nguồn không cập nhật.
- Route hay consumer phụ thuộc property name bị đổi.
- Gửi tenant tag/PII tới đích không được phép.
- Message lớn hơn, tăng đơn vị metering và storage.

Chỉ enrich những property cần thiết, có data classification và tests.

## 10. Hot path: xử lý gần thời gian thực

### 10.1. Kiến trúc

~~~mermaid
flowchart LR
    H["IoT Hub"] --> E["Built-in endpoint / Event Hubs"]
    E --> F["Azure Functions / Stream Analytics"]
    F --> C["Operational DB / Azure Data Explorer"]
    F --> A["Alerts / Logic Apps / Incident workflow"]
    F --> M["Monitor / metric / logs"]
~~~

**Hot path** là nhánh xử lý dữ liệu nhanh để phục vụ cảnh báo, trạng thái gần hiện tại, dashboards hoặc điều khiển nghiệp vụ. Độ trễ cuối cùng phụ thuộc ingestion, endpoint, consumer scheduling, query windows và downstream.

### 10.2. Azure Stream Analytics

**Azure Stream Analytics** phù hợp với nhiều bài toán streaming SQL-like:

- Filter những messages vượt ngưỡng.
- Group theo window.
- Đếm số lần sự kiện xuất hiện trong một khoảng.
- Tính trung bình/trung vị theo functions được hỗ trợ.
- Join với reference data theo capability.
- Ghi kết quả tới những sinks phù hợp.

Ví dụ logic:

~~~text
Input: IoT Hub / Event Hubs-compatible endpoint
Filter: messageType = telemetry
Group: deviceId + 5-minute event-time window
Metric: average temperatureC
Rule: average > 80 and >= minimum sample count
Output: operational alerts
~~~

Stream Analytics có query language và window semantics riêng; không copy pseudo-SQL thành query chạy thật mà chưa kiểm tra event time mapping, TIMESTAMP BY, late arrival/out-of-order policies và output schema.

### 10.3. Azure Functions event processing

Azure Functions có thể dùng **Event Hubs trigger** để xử lý messages từ IoT Hub built-in Event Hubs-compatible endpoint hoặc custom Event Hubs endpoint theo cấu hình supported.

Phù hợp khi:
- Cần code Python/C#/JavaScript/Java theo plan.
- Cần validation/enrichment phức tạp.
- Cần gọi API hoặc ghi operational store.
- Muốn dùng bindings/integration theo hệ sinh thái Azure.

Phải xem xét:
- Batch size, concurrency, scale-out và checkpoint.
- Timeouts, retries và poison messages.
- End-to-end idempotency.
- Mạng tới databases/Key Vault/Storage.
- Service identity và least privilege.
- Chi phí khi event volume tăng đột biến.

### 10.4. Một mẫu xử lý alert có trạng thái

Ngưỡng đơn giản:

~~~text
if temperatureC > 90:
    send_alert()
~~~

có thể tạo 60 alerts/phút nếu thiết bị gửi mỗi giây. Một thiết kế tốt hơn:

~~~text
Per device:
  Aggregate over 5-minute event-time window
  Alert if average temperature > 90 AND 20 valid samples
  Suppress repeated alerts for agreed cooldown
  Include severity, device, site, window, source events
  Persist alert state with idempotency key
  Track acknowledgement and incident closure
~~~

**Alerts là business actions có side effects**. Khi stream processor retry, phải tránh gửi lại cảnh báo không cần thiết; các retry có kiểm soát, alert IDs và deduplication ở sink là quan trọng.

### 10.5. Azure Data Explorer và time-series analysis

**Azure Data Explorer (ADX)** phù hợp khi cần truy vấn nhiều telemetry events, time ranges, aggregations, anomalies và dashboards tương tác theo capability hỗ trợ.

Một kiến trúc có thể ingest từ IoT Hub hoặc Event Hubs qua data connection/ingestion pipeline được hỗ trợ, sau đó dùng KQL cho truy vấn thời gian.

Đây là **operational analytics/time-series store**, không thay thế backup lạnh mặc định và không nhất thiết là database OLTP cho mọi yêu cầu giao dịch.

## 11. Cold path: lưu dữ liệu lịch sử và phân tích

### 11.1. Raw archive trên Blob Storage / ADLS Gen2

**Cold path** lưu telemetry thô hoặc gần thô phục vụ:

- Đối soát và replay khi transformation thay đổi.
- Dữ liệu lịch sử cho machine learning.
- Kiểm toán vận hành, phân tích sự cố.
- Tổng hợp theo tuần/tháng/năm.
- Truy xuất theo site/device/date.
- Data science, dự báo bảo trì.

~~~mermaid
flowchart LR
    H["IoT Hub storage route"] --> B["Blob / ADLS Gen2 raw"]
    B --> L["Bronze"]
    L --> S["Silver clean & dedup"]
    S --> G["Gold features / aggregates"]
    G --> D["Databricks / BI / ML"]
~~~

Khi route IoT Hub tới Blob Storage, phải xem format output, batching, file naming, authentication, retention và cách downstream đọc. **Không mặc định mỗi message trở thành một file JSON có tên eventId**, vì service có thể gộp messages vào files theo quy tắc routing/capture.

### 11.2. Phân vùng dữ liệu theo thời gian và nguồn

Một layout ví dụ do pipeline quản lý:

~~~text
raw/
  source=iothub/
    site=factory-hcm/
      year=2026/
        month=11/
          day=20/
            hour=08/
              batch-0001.json
~~~

Nếu IoT Hub routing xuất file theo layout/format riêng, một ETL job có thể chuyển sang layout analytics mong muốn. Không giả định route storage hỗ trợ đặt mọi path template tùy ý như cấu trúc minh họa.

Khi thiết kế layout, cân nhắc:
- Số lượng file/objects.
- Data residency và PII.
- Retention/lifecycle management.
- Compression và Parquet/Delta conversion.
- Late data/backfill và overwrite policy.
- Quyền giữa tenants/sites.
- Cost storage transactions.

### 11.3. Medallion for IoT

| Lớp | Dữ liệu | Chức năng |
|---|---|---|
| Bronze | Raw telemetry, metadata xác thực và ingestion time | Giữ nguồn, hỗ trợ replay |
| Silver | Typed, chuẩn hóa units, deduplicate, quality flags | Dữ liệu sạch, linh hoạt |
| Gold | 5-minute averages, energy KPI, failure indicators | Báo cáo/ML/business actions |

Ví dụ Silver phát hiện nhiệt độ 1000°C vượt giới hạn kỹ thuật và đánh dấu invalid thay vì tính vào average; Gold dựa trên Silver chính xác sẽ ít nhiễu hơn.

### 11.4. Không để archive dựa duy nhất vào hot consumer

Nếu chỉ lưu vào ADLS sau khi Azure Function xử lý và function lỗi, bạn có thể mất nguồn raw telemetry theo retention của endpoint.

Thiết kế thường tốt hơn:

- Route raw trực tiếp tới storage/cold path, hoặc có durable capture pipeline độc lập.
- Hot consumer xử lý alerts.
- Có reconciliation: số messages accepted/routed vs output ingested.
- Giám sát endpoint health và consumer lag.
- Có khả năng replay từ raw archive.

Tuy vậy, nếu route archive lỗi và thiết bị vẫn gửi thành công, cần cảnh báo/giải pháp recovery. Không coi “đã có route” là bằng chứng dữ liệu chắc chắn được lưu.

### 11.5. Retention theo phân loại dữ liệu

- Dữ liệu môi trường/thiết bị: theo nhu cầu phân tích và chi phí.
- Dữ liệu vị trí người lao động: có rủi ro riêng tư, cần hạn chế quyền và retention.
- Dữ liệu phục vụ kiểm toán: có thể có yêu cầu lưu trữ bắt buộc.
- Logs/alerts: đôi khi cần lưu khác khoảng thời gian telemetry.
- Dữ liệu thô: nên có lifecycle chuyển storage tiers hoặc xóa khi hết chính sách.

Storage lifecycle và data governance không được định nghĩa chỉ bằng cấu hình IoT Hub endpoint retention.

## 12. Xử lý tại biên khi mất kết nối

### 12.1. Vì sao edge quan trọng?

Một công trường ở vùng xa chỉ có kết nối trong 20 phút mỗi giờ. Nếu firmware chỉ gửi rồi bỏ khi kết nối thất bại, mất 2/3 telemetry có thể làm sai báo cáo và bỏ lỡ sự cố.

Giải pháp edge/store-and-forward:

~~~mermaid
flowchart LR
    S["Sensors"] --> G["Edge gateway"]
    G --> F["Local durable buffer"]
    G --> A["Local rule / alert if required"]
    F --> R["Retry with backoff"]
    R --> H["Azure IoT Hub"]
    H --> P["Cloud processing"]
~~~

Thiết kế phải biết nếu gateway mất điện thì buffer nằm ở RAM hay storage bền vững, có checksum, flush/fsync và giới hạn dung lượng hay không.

### 12.2. Edge gateway là gì?

Một gateway có thể:
- Chuyển đổi OPC UA/Modbus/serial hoặc protocol công nghiệp khác sang message contract phù hợp.
- Gom nhiều cảm biến thành batches.
- Lọc noise, tính trung bình cục bộ, giảm bandwidth.
- Cache dữ liệu trước khi upload.
- Phân phối cấu hình, theo dõi tình trạng sensors.
- Đồng bộ thời gian hoặc ghi clock-quality.
- Chạy một số AI inference/rules tại chỗ.

Một gateway có thể đại diện nhiều downstream devices. Nếu quy định truy xuất danh tính từng cảm biến quan trọng, đừng bỏ deviceId/sourceId trong quá trình gom; cần thiết kế **device identity/child-device mapping** an toàn.

### 12.3. Store-and-forward và thứ tự

Một buffer bản ghi có thể lưu:

~~~json
{
  "eventId": "evt-3f9a",
  "deviceId": "motor-042",
  "bootId": "boot-19",
  "sequence": 1835,
  "eventTimeUtc": "2026-11-20T08:30:00Z",
  "localStoredAtUtc": "2026-11-20T08:30:02Z",
  "retryCount": 0,
  "payload": {
    "temperatureC": 78.4
  }
}
~~~

Khi có mạng trở lại, gateway upload backlog nhưng cần:
- Giữ eventId, timestamp gốc và sequence.
- Phân biệt thời điểm đo với thời điểm cloud nhận.
- Backoff/jitter; không đẩy toàn bộ backlog gây throttling.
- Có checksum và data integrity.
- Chỉ xóa local item sau trạng thái ACK theo policy; ACK không phải end-to-end processing.
- Giữ quota storage và oldest-first/priority-based eviction policy.

### 12.4. Edge filtering và mất thông tin

Lọc dữ liệu ở edge giúp giảm chi phí và latency, nhưng có thể mất chi tiết phục vụ điều tra.

Ví dụ:
- Gửi average nhiệt độ mỗi phút: giảm messages.
- Nhưng một đỉnh 120°C kéo dài 2 giây có thể bị average làm mờ.

Một chiến lược tốt:
- Gửi periodic aggregates.
- Gửi exception/anomaly events khi có ngưỡng.
- Lưu raw cục bộ trong khoảng ngắn nếu cần.
- Có cách tải raw đặc biệt sau incident.
- Kiểm tra false positives/false negatives.

## 13. Delivery semantics, duplicate và idempotency

### 13.1. Đừng mặc định exactly-once end-to-end

Một thiết bị có thể gửi event, IoT Hub chấp nhận, nhưng device không nhận ACK do mạng mất ngay lúc đó. Thiết bị retry cùng event. Consumer có thể thấy **hai copies**.

Điều này tạo tình huống:

~~~text
Device sends event-123
  → Hub accepts
  → ACK lost
Device retries event-123
  → Hub accepts again
Consumer receives two records
~~~

Một pipeline phù hợp phải dự kiến **at-least-once delivery hoặc replay** ở các chặng, tùy protocol/endpoint/SDK. Cần thiết kế idempotency ở consumer và sink.

### 13.2. Tạo idempotency key

Ví dụ:

~~~text
idempotencyKey =
  deviceId + bootId + sequence
~~~

Hoặc eventId được firmware tạo ổn định, bảo đảm uniqueness theo phạm vi được định nghĩa. Không đủ nếu sequence reset về 0 sau khi reboot mà không có bootId; cũng cần xử lý device ID được cấp sai hoặc eventId tái sử dụng do firmware bug.

### 13.3. Dedup trong stream processor

Một consumer có thể:

1. Parse message và xác minh schema.
2. Lấy identity hệ thống, không tin body một mình.
3. Tính idempotencyKey.
4. Kiểm tra/ghi key theo **atomic uniqueness hoặc conditional operation** ở store phù hợp.
5. Chỉ phát business effect một lần theo key.
6. Ghi checkpoint sau khi xử lý theo transaction semantics được hỗ trợ.
7. Retry an toàn nếu timeout.
8. Đưa poison events vào quarantine và báo owner.

“Đã SELECT thấy key chưa?” rồi mới INSERT **không an toàn khi hai consumers xử lý đồng thời** nếu store không có constraint/compare-and-set.

### 13.4. Ordering theo partition và device

Event streams thường có ordering guarantees theo **phạm vi một partition/sequence của nguồn**, không phải một thứ tự toàn cầu cho hàng nghìn devices. Khi dùng IoT Hub Event Hubs-compatible endpoint hoặc custom Event Hubs:

- Xác định device messages được phân phối tới partition nào.
- Không giả định hai device ở hai partitions có global order.
- Dùng sequence/eventTime để xử lý late/out-of-order events.
- Không tạo một consumer group duy nhất cho mọi hệ thống cần tiến độ độc lập.

Nếu nghiệp vụ cần per-device ordering chặt, hãy kiểm tra đặc tính partition mapping, key và concurrency của source/consumer. Có thể phải dùng stateful processing theo deviceId.

### 13.5. Poison message và dead-letter workflow

Một message sai JSON có thể khiến consumer fail liên tục. Đừng để toàn bộ partition mắc kẹt vô hạn vì một bản ghi:

- Validate schema/type/content size.
- Lưu bản ghi lỗi vào **quarantine** an toàn nếu policy cho phép.
- Ghi source metadata, reason, offset/time, correlation ID.
- Thực hiện checkpoint theo chiến lược rõ ràng.
- Có người/worker xử lý lại dữ liệu sau khi sửa.
- Không đưa raw PII/secrets vào exception logs.

**IoT Hub built-in endpoint không tự cung cấp mọi dead-letter semantics giống Service Bus queue**. Nếu cần DLQ, thiết kế ở processor/sink hoặc dùng một service hỗ trợ phù hợp.

### 13.6. Data loss và reconciliation

Một phương pháp kiểm tra:

~~~text
Device-generated events
    ↓
IoT Hub accepted/routed telemetry metrics
    ↓
Endpoint consumer received/processed count
    ↓
Raw storage persisted count
    ↓
Silver validated count + quarantined count
    ↓
Gold aggregation count
~~~

Các số này không luôn bằng nhau từng phút vì retention, delay, duplicate, batching và filtering. Hãy đối soát theo **eventId, window, route, schema và latency budget**, không chỉ so tổng số thô.

## 14. Event time, arrival time và dữ liệu đến trễ

### 14.1. Ba mốc thời gian

| Mốc | Ý nghĩa | Ai cung cấp |
|---|---|---|
| eventTimeUtc | Thời điểm cảm biến thực sự đo | Device hoặc gateway |
| ingestion/arrival time | Thời điểm IoT Hub/endpoint nhận | Cloud service metadata |
| processingTimeUtc | Thời điểm consumer xử lý | Hot/cold processor |

Một event đo lúc 08:00 có thể được gửi lúc 09:00 nếu gateway offline. Nếu chỉ dùng cloud arrival time để phân tích, bạn có thể thấy tình trạng quá nhiệt xảy ra vào lúc 09:00 dù sự cố thực diễn ra lúc 08:00.

### 14.2. Clock skew

Nhiều thiết bị IoT:
- Không đồng bộ NTP ổn định.
- Khởi động với ngày giờ mặc định.
- Không có RTC đáng tin cậy.
- Bị lệch thời gian sau mất điện.
- Sử dụng timezone địa phương mà không gửi offset.

Giải pháp:
- Đồng bộ thời gian có xác thực khi khả thi.
- Gửi UTC ISO 8601 và deviceClockStatus.
- Ghi cloud arrival time độc lập.
- Kiểm tra eventTime nằm trong range hợp lệ.
- Xử lý clock drift bằng quality flags/quarantine.
- Không tin một eventTime trong tương lai rất xa để bỏ qua monitoring.

### 14.3. Late-arrival policy

Với hot processing:

~~~text
Window size: 5 phút
Allowed lateness: 15 phút
Operational alert: mục tiêu vài phút
Late events > 15 phút: có thể vào replay/reconciliation
~~~

Đây là ví dụ. Không dùng một watermark 15 phút nếu edge buffer có thể giữ dữ liệu 8 giờ và business muốn báo cáo lịch sử đầy đủ.

Một phương án:
- Hot alerts dùng dữ liệu kịp thời, có xử lý late events rõ.
- Cold path giữ nguyên eventTime và phân tích lại khi backlog đến.
- Báo cáo Gold có chính sách reprocessing/backfill.
- Có metric tỷ lệ late data và phân phối delay.

### 14.4. Alerts và dữ liệu quá hạn

Nếu một sự kiện quá nhiệt lúc 08:00 chỉ đến lúc 11:00, có thể không hợp lý phát cảnh báo khẩn “đang quá nhiệt” lúc 11:00. Nhưng sự kiện vẫn quan trọng cho báo cáo sự cố.

Nên phân biệt:
- **Current safety alert:** dựa trên dữ liệu mới, TTL freshness.
- **Historical incident event:** vẫn lưu để điều tra.
- **Maintenance alert:** có thể tổng hợp dữ liệu đến trễ.
- **Business notification:** có cooldown, idempotency và suppression rules.

Không để một backlog dài tự động kích hoạt hàng nghìn alerts trễ gây nhiễu đội vận hành.


## 15. Bảo mật đầu cuối cho kiến trúc IoT

### 15.1. Mô hình mối đe dọa

IoT thường phải đối mặt với những rủi ro khác ứng dụng web thông thường:

- Thiết bị bị đánh cắp và lộ credentials.
- Firmware bị thay đổi hoặc có lỗ hổng.
- Gateway bị chiếm quyền và gửi dữ liệu giả.
- Kẻ tấn công phát lại cùng bản tin nhiều lần.
- Dữ liệu đo bị sửa hoặc mất khi truyền.
- IoT Hub policy key bị lộ do lưu trong repository.
- Network route quá rộng, mở inbound không cần thiết.
- Người có quyền truy cập archive xem được dữ liệu vị trí/PII.
- Cloud operator cấu hình route sai làm lộ hoặc mất dữ liệu.
- Flood/burst khiến hub hoặc consumer bị throttling.

Bảo mật phải áp dụng theo lớp: **identity, thiết bị, kết nối, routing, processing, storage, monitoring và quyền truy cập con người**.

### 15.2. Device identity khác cloud service identity

| Vai trò | Cơ chế điển hình | Phạm vi |
|---|---|---|
| Thiết bị vật lý | Per-device SAS hoặc X.509 theo IoT Hub support | Kết nối D2C/device-scoped |
| DPS enrollment | X.509, symmetric key hoặc hardware attestation được hỗ trợ | Provisioning và hub assignment |
| Backend/cloud operator | Microsoft Entra ID, Azure RBAC và IoT Hub data-plane roles | Quản lý registry/service operations |
| Stream processor | Managed identity hoặc secret được kiểm soát theo endpoint | Đọc event, ghi downstream |
| Storage archive writer | Managed identity/RBAC phù hợp nếu tích hợp hỗ trợ | Ghi Blob/ADLS |
| BI/analyst | Entra identity và data store permissions | Truy vấn dữ liệu đã phân quyền |

**Không đưa IoT Hub owner/service policy connection string lên thiết bị**. Device credentials nên giới hạn ở đúng device. Management plane Azure RBAC, IoT Hub data-plane permissions và storage RBAC có scope khác nhau; phải kiểm thử từng danh tính.

### 15.3. TLS và certificate validation

Các kết nối cần:
- TLS được SDK/protocol hỗ trợ.
- Kiểm tra server hostname/certificate chain.
- Không tắt certificate validation để chữa lỗi clock/DNS.
- Firmware có trust store và cơ chế cập nhật CA khi cần.
- Clock đủ chính xác cho token/certificate validity.
- Chính sách loại bỏ cipher/protocol cũ không đáp ứng yêu cầu.
- Kiểm thử rotation của thiết bị, hub và chứng chỉ CA.

Thiết bị có đồng hồ sai năm có thể từ chối kết nối TLS hoặc SAS token dù Hub đang hoạt động bình thường. Hãy kiểm tra thời gian và CA bundle trước khi xoá device identity.

### 15.4. Mạng public, private và hybrid

Một phương án có thể cần Azure Private Link/Private Endpoint cho IoT Hub hoặc dịch vụ dữ liệu được hỗ trợ. Nhưng điều đó có điều kiện:

- Thiết bị ở ngoài VNet có thể **không kết nối được** nếu chặn public access mà không có private route.
- Nhà máy có thể cần VPN/ExpressRoute, gateway hoặc mạng kết nối tới Private Endpoint.
- Device Provisioning Service và những dịch vụ chứng thực/identity có connectivity requirements riêng.
- Private DNS và firewall phải được kiểm tra từ đúng nơi thiết bị/gateway chạy.
- Stream processor/Function có thể có mô hình VNet integration khác tùy hosting plan.
- IoT Hub, Event Hubs, Storage và ADX/Databricks có cấu hình networking khác nhau.

Không copy cấu hình Private Endpoint của Azure SQL Database sang IoT Hub rồi cho rằng mọi hostname/port/security sẽ hoạt động giống nhau.

### 15.5. Least privilege và key rotation

Quy trình:
1. Cấp một danh tính riêng cho mỗi thiết bị hoặc nhóm thiết bị được thiết kế.
2. Không cấp hub-level owner keys cho firmware.
3. Lưu private keys trong secure hardware/store khi có thể.
4. Thiết kế rotation trước khi credentials hết hạn.
5. Có khả năng disable/revoke một device bị lộ.
6. Giới hạn quyền backend/service theo chức năng.
7. Audit các thay đổi registry, policy, routing và network.
8. Quản lý secrets tại Key Vault khi không thể dùng identity federation.
9. Kiểm thử quy trình phục hồi thiết bị khi rotation thất bại.

Thay device key có thể làm mất kết nối ngay nếu firmware chưa nhận key mới. Cần staged rotation và kiểm thử reconnect.

### 15.6. Data privacy và data residency

Một GPS coordinate có thể là telemetry kỹ thuật nhưng khi gắn với một cá nhân, nó có thể thành dữ liệu cá nhân nhạy cảm về vị trí. Cần:

- Thu thập đúng mục đích và có legal basis/consent theo pháp luật áp dụng.
- Giảm granularity khi không cần vị trí chính xác.
- Chỉ đưa PII vào hot path khi cần.
- Tách tenant/site access.
- Quy định retention ở IoT Hub endpoints, Storage, ADX, logs và backups.
- Phân quyền Blob/ADLS/ADX/BI và audit queries.
- Kiểm tra cross-region replication và vùng lưu trữ.
- Thiết kế deletion workflow khi có yêu cầu xóa dữ liệu.

**Xóa event ở một bảng phân tích không tự động xóa mọi bản sao ở raw archive, checkpoints, backup và logs.**

## 16. Capacity planning và ước tính dữ liệu

### 16.1. Bắt đầu từ bốn số

Để sizing IoT ingestion, thu thập:

1. **N:** số thiết bị dự kiến ở từng giai đoạn.
2. **F:** số messages mỗi thiết bị mỗi giây/phút/giờ.
3. **S:** kích thước payload trung bình và p95/p99.
4. **B:** burst factor và backlog upload khi edge reconnect.

Sau đó thêm retention, replication, số consumer, routes, compute, HA/DR và tăng trưởng.

### 16.2. Công thức khối lượng cơ bản

~~~text
Messages per day =
    numberOfDevices × messagesPerDevicePerDay

Approx raw data per day =
    messagesPerDay × payloadBytes

Average messages per second =
    messagesPerDay ÷ 86,400

Peak messages per second =
    averagePerSecond × burstFactor
~~~

Đây là sizing ban đầu, **không phải công thức bill Azure IoT Hub chính thức**. IoT Hub message metering có granularity/operation-dependent counting theo tier; ngoài payload có protocol overhead, routes, storage, retry và metadata.

### 16.3. Ví dụ 15.000 sensors gửi mỗi phút

~~~text
Devices: 15,000
Sampling: 1 message per minute per device
Payload: 1.2 KB (decimal approximation)
Burst factor: 5×

Daily messages:
    15,000 × 60 × 24 = 21,600,000 messages/day

Average:
    21,600,000 ÷ 86,400 = 250 messages/second

Peak design estimate:
    250 × 5 = 1,250 messages/second

Approx raw payload:
    21,600,000 × 1,200 bytes
    = 25,920,000,000 bytes ≈ 25.92 GB/day

30-day raw payload:
    ≈ 777.6 GB (before storage/file/replica overhead)
~~~

**Lưu ý:** nếu IoT Hub tính theo message-metering increments thay vì từng payload đúng byte, billable messages có thể khác 21,6 triệu. Con số này cũng không bao gồm dữ liệu gửi lại, message headers, retention, file metadata, indexes, checkpoint hay geo-replication.

### 16.4. Peak traffic từ reconnect

Giả sử 3.000 thiết bị offline trong 2 giờ rồi cùng upload backlog:

~~~text
Backlog per device:
  120 samples (1/minute × 120 minutes)

Total backlog:
  3,000 × 120 = 360,000 messages

Nếu toàn bộ gửi trong 60 giây:
  6,000 extra messages/second
~~~

Dù average bình thường chỉ 250 messages/second, một reconnect storm có thể vượt capacity. Vì vậy cần:
- Jitter khi reconnect.
- Rate limit tại edge.
- Backpressure.
- Buffer có TTL/storage limit.
- Cảnh báo backlog time.
- Thiết kế hub units/scale và nhiều hubs nếu cần.

### 16.5. Một hub hay nhiều hubs?

Một IoT Hub có thể đủ nếu số thiết bị, throughput, quotas, region và tính năng đáp ứng. Nhiều hubs có thể cần khi:

- Fleet vượt giới hạn/quota hoặc cần scale ngang.
- Đòi phân tách regions/data residency.
- Tách môi trường dev/test/prod.
- Các nhà máy có bảo mật/tenant isolation riêng.
- Cần các chính sách vận hành khác nhau.

Khi dùng multi-hub cần:
- DPS assignment policy rõ.
- Device-to-hub mapping.
- Monitoring tổng hợp.
- Routing/consumer discovery.
- Khả năng chuyển hub/region khi incident.
- Tránh gửi dữ liệu cùng device vào hai hub gây duplicates.

Nhiều hubs **không tự đảm bảo active-active geo-failover**; failover plan phải xác định identity re-provisioning, duplicate handling và data reconciliation.

## 17. Chi phí: IoT Hub chỉ là một phần

### 17.1. Các cấu phần TCO

~~~text
IoT system monthly cost =
    IoT Hub tier/units and billable operations
  + DPS operations/enrollments when applicable
  + Event Hubs throughput/retention if separate namespace
  + Functions/Stream Analytics/ADX compute and ingestion
  + Blob/ADLS storage, requests and data retention
  + Databricks/Synapse/Fabric analytics workloads
  + Network/Private Link/VPN/ExpressRoute/egress
  + Azure Monitor/Log Analytics ingestion and retention
  + Key Vault/security/audit services
  + Edge hardware, LTE, power, maintenance and operations
~~~

Các dịch vụ có mô hình tính tiền khác nhau. Không dùng một mức giá/million messages để dự toán cả pipeline.

### 17.2. Các đòn bẩy tối ưu

- Gửi chỉ telemetry có ích, không chứa payload trống/lặp vô nghĩa.
- Gom nhóm readings hợp lý nhưng không vi phạm message size và alert latency.
- Edge filtering/sampling có chủ đích.
- Thiết kế event contract gọn và binary compression khi thật sự cần, với khả năng hỗ trợ parser.
- Dùng cold storage lifecycle cho dữ liệu lịch sử.
- Không giữ mọi event ở operational DB đắt tiền nếu không truy vấn.
- Dừng compute phân tích không cần chạy liên tục.
- Dùng stream window/aggregate thay vì lưu mọi intermediate output vào Cosmos DB.
- Hạn chế duplicate routes và viết lại dữ liệu nhiều lần.
- Đặt budget/cost tags và đo cost per million valid events.
- Quản lý log retention/sampling, vẫn giữ audit bắt buộc.

Giảm sampling quá mạnh có thể làm bỏ lỡ đỉnh nhiệt ngắn gây hỏng máy. Tối ưu phải dựa vào **độ chính xác phát hiện và yêu cầu an toàn**, không chỉ tiền.

### 17.3. Metríc chi phí nên theo dõi

- Cost per active device/month.
- Cost per million accepted messages.
- Cost per million **valid** messages sau quarantine.
- Storage bytes per device/day.
- Egress per site.
- Hot path cost per generated alert.
- Retry/duplicate rate và phí tương ứng.
- Growth forecast theo sản lượng sensor.
- Cost của backup, disaster recovery và logs.

**Đừng lấy accepted messages làm mẫu số duy nhất** nếu 30% messages hỏng schema hoặc duplicate; chi phí/valid event có thể tăng dù giá IoT Hub không đổi.

## 18. Thực hành lab: IoT Hub và thiết bị mô phỏng

### 18.1. Mục tiêu và giới hạn

Lab này minh họa:
- Đọc subscription/IoT Hub context.
- Tạo device identity cho thiết bị mô phỏng.
- Gửi một bản tin D2C với event ID/timestamp/schema.
- Kiểm tra việc nhận ở IoT Hub/event consumer.
- Phân biệt service acceptance và downstream success.

Không cần thiết bị vật lý, không chạy trong production. Những lệnh tạo resources **có thể tính phí**; chỉ sử dụng subscription/resource group được phê duyệt.

Thông số ví dụ:

~~~text
Subscription: <SUBSCRIPTION_ID>
Resource group: rg-iot-lab
IoT Hub: iothub-factory-lab-<unique-suffix>
Device identity: motor-042
Event payload: telemetry JSON nhỏ
~~~

Azure IoT Hub name phải đáp ứng quy tắc và uniqueness của dịch vụ. Thay placeholder bằng tên thực, không chạy nguyên văn.

### 18.2. Kiểm tra Azure CLI và subscription

Trong Azure Cloud Shell hoặc terminal Bash có Azure CLI:

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az group show \
  --name rg-iot-lab \
  --query "{name:name,location:location}" \
  --output json
~~~

Nếu resource group chưa tồn tại, chỉ tạo khi có approval và đúng region/policy. Không tự tạo resource group khác vì thiếu quyền vào nhóm đã được cấp.

### 18.3. Tạo IoT Hub lab khi đã được cấp phép

Ví dụ:

~~~bash
az iot hub create \
  --resource-group rg-iot-lab \
  --name "<IOT_HUB_UNIQUE_NAME>" \
  --sku S1
~~~

Mẫu dùng SKU S1 để minh họa; giá/quota/SKU compatibility và khả năng tạo resource phải được kiểm tra theo region/subscription trước khi chạy.

Xem cấu hình:

~~~bash
az iot hub show \
  --resource-group rg-iot-lab \
  --name "<IOT_HUB_UNIQUE_NAME>" \
  --query "{name:name,location:location,sku:sku}" \
  --output json
~~~

Không tạo lại hub nếu nó đã có routes, device registry, dữ liệu hoặc consumer đang sử dụng.

### 18.4. Extension dành cho IoT device operations

Một số lệnh thao tác device identity/telemetry cần **Azure IoT extension** phù hợp với phiên bản Azure CLI:

~~~bash
az extension add --name azure-iot
az iot hub device-identity create --help
~~~

Nếu extension đã cài, kiểm tra phiên bản/update theo policy thay vì cài bừa trên build agent production. Lệnh extension chỉ minh họa, không được chạy trong assignment này.

### 18.5. Tạo device identity

~~~bash
az iot hub device-identity create \
  --hub-name "<IOT_HUB_UNIQUE_NAME>" \
  --device-id "motor-042"
~~~

Kiểm tra:

~~~bash
az iot hub device-identity show \
  --hub-name "<IOT_HUB_UNIQUE_NAME>" \
  --device-id "motor-042"
~~~

Device identity là bản ghi registry, **không phải chứng minh một thiết bị vật lý thật đã kết nối**. Trong lab có thể dùng device symmetric key/connection string do dịch vụ cấp, nhưng không in hoặc commit secrets.

### 18.6. Tạo credential lab không phơi bày bí mật

Với lab cần symmetric-key connection string, lấy nó qua cơ chế bảo mật được phê duyệt, lưu vào biến môi trường hoặc secret store của phiên chạy, không đưa nguyên văn vào chat/source control:

~~~text
IOTHUB_DEVICE_CONNECTION_STRING =
    HostName=<hub-hostname>;
    DeviceId=motor-042;
    SharedAccessKey=<DEVICE_KEY>
~~~

Đây chỉ là cấu trúc minh họa, không phải secret thật. Nếu dùng PowerShell/Bash, tránh lệnh để credential xuất hiện trong terminal history, logs hoặc job artifact.

**Production:** dùng DPS và X.509/khóa thiết bị được quản lý tốt hơn khi điều kiện cho phép. Không dùng hub-level service connection string làm device connection string.

### 18.7. Python SDK: gửi telemetry mô phỏng

Ví dụ ứng dụng Python 3 với SDK **azure-iot-device** tương thích. Cần cài package qua môi trường dev được phê duyệt và cung cấp biến môi trường IOTHUB_DEVICE_CONNECTION_STRING an toàn:

~~~python
import json
import os
import uuid
from datetime import datetime, timezone

from azure.iot.device import IoTHubDeviceClient, Message

device_connection_string = os.environ[
    "IOTHUB_DEVICE_CONNECTION_STRING"
]

client = IoTHubDeviceClient.create_from_connection_string(
    device_connection_string
)

telemetry = {
    "schemaVersion": "1.0",
    "eventId": str(uuid.uuid4()),
    "deviceId": "motor-042",
    "bootId": "boot-lab-01",
    "sequence": 1,
    "eventTimeUtc": datetime.now(timezone.utc).isoformat(),
    "measurements": {
        "temperatureC": 78.4,
        "vibrationMmS": 4.8,
        "currentA": 3.2
    },
    "quality": {
        "sensorStatus": "ok"
    }
}

message = Message(json.dumps(telemetry))
message.content_type = "application/json"
message.content_encoding = "utf-8"
message.message_id = telemetry["eventId"]
message.custom_properties["messageType"] = "telemetry"

try:
    client.connect()
    client.send_message(message)
    print("Telemetry gửi tới IoT Hub thành công ở mức SDK.")
finally:
    client.shutdown()
~~~

Kết quả trên chỉ minh họa device client được service chấp nhận khi kết nối thành công. Nó **không tự chứng minh endpoint route, Function, ADLS archive hoặc dashboard đã cập nhật**.

### 18.8. Một lựa chọn Azure CLI gửi D2C trong lab

Khi IoT extension hỗ trợ lệnh và device identity đã tồn tại, có thể dùng:

~~~bash
az iot device send-d2c-message \
  --hub-name "<IOT_HUB_UNIQUE_NAME>" \
  --device-id "motor-042" \
  --data '{"schemaVersion":"1.0","eventId":"evt-lab-01","temperatureC":78.4}'
~~~

Đây là ví dụ một lần gửi để smoke test. Kiểm tra help và format quoting theo shell, không sử dụng thiết bị sản xuất hoặc gửi PII trong test message. Với routing dựa trên JSON body, đảm bảo content type/encoding đúng theo SDK/CLI flags được hỗ trợ.

### 18.9. Xác minh bên nhận

Một bài kiểm thử có thể dùng:
- Công cụ monitor events của Azure IoT extension trong môi trường lab khi được hỗ trợ.
- Event Hubs-compatible consumer phù hợp với IoT Hub built-in endpoint.
- Azure Function hoặc Stream Analytics được cấu hình đúng endpoint/consumer group.
- Một custom route tới storage đã có permissions.
- Azure Monitor metrics và logs.

Ví dụ thao tác giám sát lab:

~~~bash
az iot hub monitor-events \
  --hub-name "<IOT_HUB_UNIQUE_NAME>" \
  --device-id "motor-042"
~~~

Lệnh monitor thường là long-running; thoát bằng cơ chế của terminal khi quan sát đủ. Nếu đã cấu hình custom routes, phải biết **built-in endpoint có thực sự nhận messages không**. Không vội kết luận thiết bị không gửi chỉ vì built-in monitor trống khi route đang đưa dữ liệu tới endpoint khác.

### 18.10. Cleanup có kiểm soát

- Dừng sensor simulator/monitor.
- Xem resource và billing thực tế.
- Xác minh IoT Hub/device identity chỉ phục vụ lab.
- Giữ các logs/test evidence được yêu cầu.
- Chỉ xóa lab resources khi có owner approval.
- Không chạy lệnh xóa cả IoT Hub dùng chung với nhiều thiết bị thật.

**Lab hoàn thành khi có evidence:** device identity tồn tại, message được gửi, consumer/endpoint đọc được event, xác nhận schema/deviceId/time và ghi log kết quả. Không coi một terminal in “sent” là đủ.

## 19. Thiết kế hot path processor

### 19.1. Pseudocode xử lý một telemetry event

~~~python
def process_telemetry(event, authenticated_device_id):
    payload = parse_json(event.body)

    validate_schema_version(payload["schemaVersion"])
    validate_measurement_units(payload["measurements"])

    if payload["deviceId"] != authenticated_device_id:
        quarantine(event, reason="device identity mismatch")
        return

    key = build_event_key(
        authenticated_device_id,
        payload["bootId"],
        payload["sequence"]
    )

    if not atomic_claim_event(key):
        return  # Duplicated/replayed event

    try:
        persist_telemetry_idempotently(payload, key)
        evaluate_business_window(payload, key)
    except Exception:
        mark_event_for_safe_retry(key)
        raise
~~~

Đây là **pseudocode kiến trúc**, không phải chương trình chạy trực tiếp: parse_json, atomic_claim_event, persistence và retry semantics phải được hiện thực. Trong thực tế, nếu claim event key thành công nhưng downstream ghi thất bại, một retry đơn giản có thể bị coi là duplicate và **bỏ qua vĩnh viễn**. Hãy dùng state machine pending/committed, transactional outbox, cùng-store atomic transaction hoặc reconciliation để tránh bẫy này.

### 19.2. Idempotency end-to-end

Một pipeline có ba bước:
1. Ghi dữ liệu operational.
2. Cập nhật trạng thái thiết bị.
3. Phát alert.

Không có transaction nguyên tử qua ba dịch vụ độc lập trừ khi có cơ chế thiết kế đặc biệt. Có thể:
- Ghi event và trạng thái xử lý vào một durable store trước.
- Dùng outbox để phát downstream messages.
- Deduplicate alert dựa trên stable alertId.
- Retry từng bước có kiểm soát.
- Theo dõi timeout và partial success.
- Có reconciliation job xử lý records pending.

**Idempotency không chỉ là câu lệnh if duplicate then return**; nó phải xét cả trường hợp thất bại sau khi đã claim key.

### 19.3. Xử lý payload độc hại hoặc lỗi

Thiết bị có thể gửi:
- JSON không parse được.
- Trường quá lớn.
- Định dạng timestamp không hợp lệ.
- Chỉ số nhiệt độ âm phi lý.
- Chuỗi payload có dữ liệu cá nhân không được phép.
- Mã script/SQL injection trong string field.

Cần giới hạn:
- Message size theo IoT Hub tier và parser.
- Schema types và numeric ranges.
- Depth của JSON, max string length.
- Resource/time limits khi parsing.
- Quarantine retention.
- Không log toàn bộ payload.
- Không nội suy dữ liệu không tin cậy vào SQL hoặc query DSL.

### 19.4. Một consumer hay nhiều consumer groups?

Nếu hot alerts và historical enrichment cùng đọc một event stream, có thể dùng consumer groups tách biệt ở endpoint hỗ trợ để mỗi nhóm giữ tiến độ riêng.

Tuy nhiên:
- Quá nhiều consumers/partitions có giới hạn.
- Consumer groups không tăng vô hạn khả năng đọc.
- Một consumer group chia tải giữa instances có checkpoint ownership semantics riêng.
- Việc đổi group/checkpoint có thể gây replay.
- Các consumer khác nhau có thể khác nhau về processing latency.

Đừng dùng chung checkpoint storage/prefix của hai ứng dụng khác mục tiêu mà chưa kiểm tra SDK/runtime requirements.



## 20. Monitoring, observability và SLO

### 20.1. Cần quan sát nhiều hơn “Hub có hoạt động không?”

Một hệ thống IoT có thể có IoT Hub khỏe mạnh nhưng consumer lỗi; hoặc Function thành công nhưng đang bỏ 40% events do schema không hợp lệ. Vì vậy cần các lớp metrics:

| Lớp | Tín hiệu | Ý nghĩa |
|---|---|---|
| Device | Online/offline, reconnect, battery, boot count | Chất lượng kết nối và sức khỏe thiết bị |
| Device buffer | Queued events, oldest age, drops, disk usage | Nguy cơ mất dữ liệu trước khi lên cloud |
| IoT Hub | Ingress accepted/rejected, throttling, active connections | Năng lực lớp tiếp nhận |
| Routes/endpoints | Routed messages, route failures, endpoint health | Có đưa sự kiện tới đích không |
| Stream consumers | Partition lag, offsets/checkpoints, retries | Hot path có theo kịp tốc độ gửi không |
| Processing | Parse errors, invalid schema, duplicate rates | Chất lượng dữ liệu đầu vào |
| Operational sink | Write latency, 429/5xx, failure rate | Có lưu trạng thái/alert được không |
| Cold storage | Raw files persisted, age of last batch, storage failures | Archive có đầy đủ/kịp thời không |
| Analytics | Silver quality, freshness, Gold lag | Báo cáo có đáng tin không |
| Security | Failed authentication, key changes, suspicious traffic | Có khả năng bị tấn công không |
| Cost | IoT Hub usage, endpoint/compute/storage/log cost | Có vượt ngân sách không |

Tên metrics và diagnostic categories cụ thể có thể thay đổi theo IoT Hub tier và dịch vụ. Đọc danh mục Azure Monitor metrics của tài nguyên thật thay vì giả định một metric tên “TTL” hoặc “Consumer Lag” luôn tồn tại trên IoT Hub.

### 20.2. SLI và SLO ví dụ

Một hệ thống có thể định nghĩa:

~~~text
Telemetry freshness SLI:
  Fraction of valid events processed within 2 minutes
  after arrival at IoT Hub.

Target SLO:
  >= 99.5% over a rolling 30-day window.

Archive completeness SLI:
  Fraction of accepted events recoverable in cold archive
  after allowing batching and agreed delay.

Critical device connectivity SLI:
  Fraction of priority devices connected or storing
  data safely in a verified edge buffer.
~~~

Số 99,5% chỉ là **mục tiêu minh họa**, không phải SLA tự động của Azure IoT Hub. Phải nêu rõ mẫu số: accepted, valid, device-generated hay archived messages. Nếu 10% thiết bị không gửi vì chết pin, đo chỉ trên accepted messages sẽ không phản ánh độ tin cậy toàn hệ thống.

### 20.3. Correlation ID và tracing

Một sự kiện nên có:
- eventId hoặc deviceId + bootId + sequence.
- Hub/device identity được xác thực từ metadata.
- Event time và arrival/processing timestamps.
- Route/consumer group/partition context khi API cung cấp.
- Ingestion batch ID.
- Processing status và error reason.
- Cold storage object/table reference.
- AlertId nếu event góp phần tạo cảnh báo.

Không bắt buộc mọi hệ thống có distributed trace tự động xuyên MQTT, IoT Hub, Event Hubs và Storage. Có thể cần **application correlation fields** và log aggregation riêng.

### 20.4. Cảnh báo cần có owner

| Alert | Ví dụ ý nghĩa | Hành động |
|---|---|---|
| Device offline tỷ lệ cao | Mất mạng hoặc lỗi firmware theo site | Phân tích theo site/firmware/provider |
| Gateway buffer gần đầy | Sắp mất dữ liệu | Giảm sampling, hỗ trợ mạng, tăng storage |
| IoT Hub throttling | Ingress quota/burst | Backoff, sizing, scale units khi phù hợp |
| Routing errors tăng | Endpoint credential/network/route lỗi | Kiểm tra target và route config |
| Consumer lag cao | Processor chậm hoặc bị dừng | Scale/tối ưu theo partitions/quota |
| Schema rejects tăng | Firmware rollout không tương thích | Quarantine và rollback firmware |
| Archive freshness trễ | Storage route/batch/permissions lỗi | Kiểm tra raw path và endpoint health |
| Duplicate rate tăng | Reconnect storm hoặc retry bug | Xem device SDK và network |
| Alert delivery thất bại | Downstream API/Logic Apps lỗi | Retry/outbox, escalation |
| Chi phí tăng bất thường | Sampling tăng hoặc duplicate routes | Kiểm tra per-device usage và cost |
| Auth failures bất thường | Token hết hạn hoặc credential lộ | Revoke/rotate và security review |

Mỗi cảnh báo cần có mức ưu tiên, owner, runbook và đường escalation, không chỉ gửi email chung rồi bỏ mặc.

### 20.5. KQL minh họa từ telemetry log của ứng dụng

Nếu một Azure Function gửi custom logs vào Application Insights/Log Analytics với bảng và fields phù hợp, có thể tổng hợp lỗi theo thời gian:

~~~kusto
AppTraces
| where TimeGenerated > ago(1h)
| where Message has "telemetry-validation"
| summarize Events=count() by bin(TimeGenerated, 5m), SeverityLevel
| order by TimeGenerated asc
~~~

KQL là minh họa; các bảng/cột và log message thực tế phụ thuộc workspace-based Application Insights, SDK và logging pipeline. Query trống không chứng minh hệ thống không có lỗi nếu logs không được thu thập.

### 20.6. Data quality SLO

Đề xuất theo dõi:
- Tỷ lệ payload hợp lệ theo schema.
- Tỷ lệ thiếu deviceId/eventTime/sequence.
- Tỷ lệ clock skew quá ngưỡng.
- Tỷ lệ out-of-range measurements.
- Tỷ lệ duplicate.
- Tỷ lệ events đến muộn.
- Tỷ lệ expected sample count bị thiếu theo device/site.
- Tỷ lệ bản ghi quarantine được xử lý lại.
- Tỷ lệ output archive và analytics có thể reconcile.

Không báo toàn hệ thống “healthy” chỉ vì HTTP/MQTT connections thành công trong khi chất lượng dữ liệu đang sai.

## 21. High availability và disaster recovery

### 21.1. Phân biệt HA, buffer và DR

| Cơ chế | Giải quyết | Không tự giải quyết |
|---|---|---|
| IoT Hub service availability | Sự cố nền tảng trong phạm vi SLA/tier | Mất kết nối thiết bị do LTE hoặc toàn khu vực |
| Device/edge durable buffer | Mất mạng tạm thời | Vô hạn dữ liệu khi ổ đĩa đầy/hỏng |
| Retry/backoff | Lỗi transient | Chính sách dữ liệu/credentials sai dài hạn |
| Multi-hub/region design | Một số sự cố theo hub/region | Tự động global failover nếu không xây |
| Raw cold archive | Replay/transformation lại | Cam kết ingest tức thời |
| Consumer checkpoints | Resume việc xử lý stream | Chống toàn bộ data loss ngoài retention |
| Data backup/replication | Phục hồi dữ liệu theo policy | Đồng bộ 0-lag mọi dịch vụ |

### 21.2. Mục tiêu RPO và RTO

- **RPO (Recovery Point Objective):** mức dữ liệu tối đa cho phép mất trong sự cố.
- **RTO (Recovery Time Objective):** thời gian mục tiêu khôi phục luồng dịch vụ.

Ví dụ:

~~~text
Critical alarms:
  Processing RTO target: < 15 minutes
  Acceptable data loss target: as low as feasible,
  with durable buffering and reconciliation.

Historical telemetry:
  RTO target: < 24 hours
  Restore/backfill from device/edge/archive logs.
~~~

Đây là mục tiêu do dự án đặt, không phải cam kết dịch vụ. Với dây chuyền có yêu cầu an toàn vật lý tức thời, **control loop an toàn tại chỗ phải hoạt động độc lập với cloud** khi mất kết nối.

### 21.3. Chiến lược khi mất một region

Một kế hoạch nghiêm túc cần xác định:

1. Những devices nào có thể giữ buffer khi cloud unavailable?
2. DPS có enrollment/assignment sang hub thay thế theo khả năng đã thiết kế không?
3. Mỗi thiết bị biết kết nối lại khi hub bị lỗi thế nào?
4. Device identity/credentials và twin state có sẵn ở nơi khôi phục không?
5. Hot/cold routes có được triển khai tại secondary không?
6. Storage/ADX/consumer checkpoints có khả năng recovery thế nào?
7. Alerting có fallback tại edge không?
8. Làm sao tránh duplicate events khi source gửi backlog cả trước và sau failover?
9. Ai phê duyệt failover và rollback?
10. Khi nào có thể failback mà không mất dữ liệu?

Một IoT Hub thứ hai **không tự đồng bộ toàn bộ device registry, trạng thái và các routes của hub thứ nhất** trong mọi thiết kế. Việc nhân bản hoặc tái tạo cấu hình cần IaC, provisioning strategy và bài kiểm thử thật.

### 21.4. Bảo vệ dữ liệu trước khi hết retention của endpoint

Event Hubs-compatible endpoints và các stream subscriptions có giới hạn thời gian giữ dữ liệu. Nếu consumer dừng lâu hơn retention được hỗ trợ, không thể replay từ endpoint đã hết thời hạn. Vì vậy:
- Có raw archive độc lập hoặc edge buffer khi yêu cầu.
- Theo dõi consumer lag và tuổi event cũ nhất.
- Đặt alert trước khi lag tiến gần retention.
- Tính thời gian khôi phục consumer.
- Có kế hoạch backfill từ storage nếu stream data đã biến mất.
- Kiểm soát duplicate và ordering khi backfill chồng dữ liệu real-time.

Không chọn “retention mặc định” chỉ vì lab nhỏ; production phải gắn retention với RTO, RPO và replay strategy.

### 21.5. Chaos/recovery tests

Trước production nên diễn tập:

- Ngắt internet của 10 thiết bị mô phỏng.
- Tắt gateway trong khi đang buffer.
- Đổi credential rồi thử reconnect.
- Chặn network tới custom Event Hubs/Storage endpoint.
- Dừng consumer lâu hơn chu kỳ sampling.
- Tạo poison message.
- Tạo backlog/reconnect storm.
- Thay schema version trong khi pipeline còn chạy.
- Thử failover hub/region nếu thiết kế hỗ trợ.
- Kiểm tra số event bị thiếu/trùng và alert state sau hồi phục.

Kết quả phải ghi evidence, thời gian UTC, số messages và root cause, không chỉ ghi “thử xong”.

## 22. Case study: hệ thống giám sát động cơ tại nhà máy

### 22.1. Yêu cầu

Một doanh nghiệp có:
- 12 cơ sở, mỗi cơ sở từ vài trăm đến vài nghìn cảm biến.
- Tổng 15.000 thiết bị dự kiến sau một năm.
- Telemetry nhiệt độ/độ rung mỗi phút; thiết bị quan trọng có thể gửi nhanh hơn.
- Mạng nhà máy bất ổn.
- Cần phát hiện quá nhiệt trong vài phút.
- Phân tích bảo trì dự đoán theo dữ liệu 12 tháng.
- Phân quyền vận hành theo site và tổ chức.
- Quy định không phát raw telemetry chứa PII ngoài phạm vi cho phép.
- Budget/cloud costs cần theo dõi từng nhà máy.

### 22.2. Thiết kế đề xuất ở mức logic

~~~mermaid
flowchart TD
    D["15k sensors"] --> E["Site edge gateways + durable buffers"]
    E --> H["Azure IoT Hub / hubs"]
    DPS["DPS + device identities"] --> H
    H --> R["Routes"]
    R --> EV["Hot Event Hubs-compatible / custom stream"]
    R --> BL["Raw archive Blob / ADLS Gen2"]
    EV --> SA["Stream Analytics / Azure Functions"]
    SA --> OP["Operational metrics / Azure Data Explorer"]
    SA --> AL["Alert service + incident workflow"]
    BL --> DA["Databricks Silver/Gold analytics"]
    DA --> BI["Maintenance dashboards / ML"]
    H --> MO["Azure Monitor / security logs"]
    SA --> MO
    DA --> MO
~~~

**Lưu ý:** một hub hoặc nhiều hubs là quyết định dựa trên S1/S2/S3 units, region, compliance, network và quotas thực tế; sơ đồ không khẳng định 15.000 thiết bị luôn cần multi-hub.

### 22.3. Device identity và fleet lifecycle

1. Manufacturing/onsite onboarding xác thực thiết bị.
2. DPS enrollment theo nhóm/individual theo attestation.
3. Gán vào hub phù hợp site/region.
4. Lưu deviceId, siteId, assetId và certificate status.
5. Kích hoạt TLS MQTT/AMQP theo SDK và firewall.
6. Gửi schemaVersion/bootId/sequence/eventId.
7. Device twins quản lý sampling interval/firmware state.
8. Giám sát kết nối và certificate expiry.
9. Rotate/revoke identity khi thay thiết bị hoặc phát hiện lộ key.
10. Decommission đúng quy trình cả cloud và edge.

### 22.4. Ingestion và processing

- **IoT Hub** chấp nhận device-to-cloud telemetry.
- **Hot route/stream** phục vụ alert windows, anomaly detection và operational metrics.
- **Cold archive** giữ raw dữ liệu có đủ metadata để replay.
- **Silver** chuẩn hóa units và loại duplicate/clock-error.
- **Gold** cung cấp thống kê theo thiết bị/site/ngày.
- **Data Explorer/BI** cho phép xem trend gần thời gian thực hoặc phân tích lịch sử.
- **Workflows/Functions** tạo ticket cảnh báo có idempotency và human acknowledgement.

Các operational alerts quan trọng phải có **cooldown, minimum sample count, freshness limit**. Không coi một mẫu tăng bất thường là chắc chắn dây chuyền cần dừng; quy trình dừng máy cần thiết kế an toàn riêng với chuyên gia vận hành.

### 22.5. Kế hoạch triển khai theo giai đoạn

| Giai đoạn | Phạm vi | Điều kiện để mở rộng |
|---|---|---|
| POC | 20 thiết bị mô phỏng hoặc thật trong lab | Schema/SDK/DPS/routing hoạt động |
| Pilot | Một dây chuyền, 100–300 thiết bị | Đo network reliability, alert latency |
| Site rollout | Một nhà máy, hàng nghìn thiết bị | Backpressure, consumer recovery, RBAC |
| Multi-site | Nhiều nhà máy và hubs khi cần | Governance, fleet assignment, cost |
| Enterprise | Toàn bộ fleet, DR và ML | SLO, audit, incident runbooks, scaling tests |

Không bỏ qua pilot với mạng và phần cứng thật chỉ vì cloud simulator gửi 100% events.

### 22.6. Tiêu chí chấp nhận

- Mỗi thiết bị có identity riêng, credential không hard-code vào repo.
- Khi mất mạng, dữ liệu được buffer theo giới hạn xác định.
- Retry cùng event không tạo alert trùng.
- Cloud nhận được authenticated metadata và timestamp riêng.
- Route hot và cold đều được kiểm chứng.
- 409/429/5xx hoặc protocol errors có retry/backoff thích hợp.
- Telemetry sai schema được quarantine và có alert.
- Dữ liệu quá trễ không gây cảnh báo khẩn sai thời điểm.
- Storage archive có retention/permissions theo site.
- Consumer restart có checkpoint/reconciliation.
- Có cost attribution theo site.
- Có runbook và rehearsal cho mất mạng/region.


## 23. Troubleshooting theo lớp

### 23.1. Bảng triệu chứng, nguyên nhân và hành động

| Triệu chứng | Khả năng lỗi | Cách kiểm tra |
|---|---|---|
| Thiết bị không kết nối được | DNS, TLS, port, clock, SAS/X.509 | Log SDK, thời gian hệ thống, certificate chain |
| Lỗi authentication | Device identity disabled, token/key hết hạn | IoT registry, credential và audit |
| DPS không assign hub | Enrollment/attestation/assignment policy | DPS registration status và device logs |
| Device gửi thành công, monitor trống | Built-in route/fallback/consumer group | Xem routing config và endpoint thực |
| Custom route không khớp | Query property/JSON content type sai | Message metadata và route test |
| D2C bị throttling | IoT Hub tier/unit limits hoặc burst | Ingress metrics, 429/quota feedback |
| Có kết nối nhưng không thấy telemetry | Firmware không gửi hoặc gửi sai message type | Device logs, packet send callbacks |
| Route tới Storage lỗi | Credential/RBAC, path, target firewall | Endpoint health và diagnostic logs |
| Consumer bị lag | CPU, downstream slow, partitions, retries | Processing latency và checkpoint ages |
| Alert lặp | Duplicate/replay, retry side effect | eventId/alertId, idempotency store |
| Alert không đến | Output side-effect fail, suppression policy | Outbox, downstream logs và SLA |
| Sai mốc thời gian | Device clock lệch hoặc timezone | So eventTime với cloud arrival |
| Báo cáo thiếu dữ liệu cũ | Late events, retention, pipeline filtering | Raw archive và backfill policies |
| Nhiệt độ 0 bất thường | Sensor invalid, default null-to-zero | Schema/quality flags/quarantine |
| Dữ liệu vượt message size | Payload quá lớn, batch không hợp lý | SDK errors, service limit |
| Hub khỏe nhưng Gold trễ | Analytics job lỗi hoặc cold backlog | Databricks/ADX pipeline monitoring |
| Gateway ổ đĩa đầy | Offline quá lâu, retry quá chậm | Local queue oldest age, disk alarms |
| Chi phí cao bất thường | Sampling quá nhiều, duplicates, extra routes | Per-device usage và cost breakdown |
| Chặn public access rồi devices offline | Chưa có private route/DNS tới hub | Test từ site mạng thật |
| Quá nhiều log chứa PII | Logging payload không kiểm soát | Redaction, retention, role review |
| Đổi region mất thiết bị | Identity/provisioning mapping chưa chuẩn bị | DPS re-provision và failover runbook |

### 23.2. Runbook: thiết bị không kết nối IoT Hub

1. Kiểm tra nguồn điện và network vật lý của device/gateway.
2. Đọc log SDK có timestamp UTC, hạn chế log secrets.
3. Kiểm tra DNS lookup endpoint và route tới đúng hub.
4. Kiểm tra outbound TLS port/proxy/firewall.
5. Kiểm tra device clock, SAS validity hoặc X.509 certificate chain.
6. Kiểm tra device identity enabled, hub name/deviceId.
7. Nếu dùng DPS, xác minh enrollment và assigned hub.
8. Kiểm tra public/private network restrictions của IoT Hub.
9. Thử kết nối từ thiết bị lab khác dùng cùng network để khoanh vùng.
10. Không rotate/xóa hàng loạt identities trước khi xác định root cause.

### 23.3. Runbook: device gửi thành công nhưng Storage không có dữ liệu

1. Xác định thời điểm send và device ID.
2. Kiểm tra IoT Hub accepted/ingress metrics.
3. Xem active routes, source, query, custom endpoints và fallback.
4. Kiểm tra route dựa JSON có content type/encoding đúng.
5. Xem endpoint diagnostics/health và authorization.
6. Đọc đúng path/object layout và batching interval ở Blob/ADLS.
7. Đối chiếu raw object creation time với eventTime.
8. Kiểm tra SDK/consumer đang kết nối tới built-in hay custom stream.
9. Nếu messages mất qua retention, xem edge buffer/replay source.
10. Tạo một event smoke test mới có eventId duy nhất và xác minh end-to-end.

### 23.4. Runbook: alert bùng nổ sau khi mạng phục hồi

1. Xem device backlog, oldest eventTime và connection recovery time.
2. Đánh giá eventTime vs processingTime.
3. Kiểm tra cooldown/freshness filters.
4. Tách historical incidents khỏi current safety alerts.
5. Dùng idempotency key để ngăn phát lại.
6. Điều tiết tốc độ replay, tránh quá tải processor.
7. Điều tra các alerts đã phát nhầm và ghi evidence.
8. Không xóa raw events để làm cảnh báo tắt; chỉnh rules có kiểm soát.

### 23.5. Runbook: tăng 429/throttling

1. Xác định source lỗi: IoT Hub, Event Hubs, Function, operational DB hay Storage.
2. Phân tích average/peak và reconnect/backlog burst.
3. Kiểm tra tier, units, quotas, per-operation limits.
4. Kiểm tra thiết bị retry có backoff/jitter không.
5. Điều tiết fleet sends hoặc edge upload rate.
6. Scale đúng lớp hạ tầng nếu SKU hỗ trợ và được phê duyệt.
7. Theo dõi impact tới dropped messages, queue age và alerts.
8. Kiểm chứng công suất sau điều chỉnh bằng load test.

## 24. Quy trình triển khai có kiểm soát

### 24.1. Giai đoạn A: xác định yêu cầu

Ghi rõ:
- Số devices hiện tại và sau 1–3 năm.
- Sampling rate trung bình và burst.
- Payload size, retention, schema versions.
- Device network/protocol/hardware/OS.
- Online/offline ratio, buffer capacity.
- Mục tiêu alert latency, RPO/RTO.
- Data ownership, PII, jurisdiction.
- Hot/cold consumers và business analytics.
- Budget, monitoring và on-call requirements.

Không sizing bằng chỉ số “bao nhiêu thiết bị” mà thiếu messages/device/second, payload size và backlog.

### 24.2. Giai đoạn B: provision resources

Theo IaC/approval:
1. Resource group, region, tagging, budgets.
2. IoT Hub tier/units với quota được xác minh.
3. DPS và enrollment model nếu fleet cần.
4. Device registry/identity policy.
5. Storage/Event Hubs/Stream Analytics/Functions/ADX khi cần.
6. Message routes và fallback có tests.
7. Managed identities/RBAC/Key Vault.
8. Private networking và site connectivity nếu có.
9. Diagnostic settings và log retention.
10. Backup, DR và replay policies.

Không tạo tất cả resources mà không có mục đích. Một bài toán nhỏ có thể chỉ cần IoT Hub + Storage + một consumer.

### 24.3. Giai đoạn C: ứng dụng/device testing

- Firmware gửi schemaVersion, UTC eventTime, stable eventId.
- Device ID được đối chiếu với hệ thống.
- Raw archive có thể đọc/replay.
- Hot processing đạt latency SLO.
- Retry trùng không phát alert trùng.
- Dữ liệu lỗi nằm trong quarantine, không mất im lặng.
- Network fail/recovery có buffer logic.
- Device credentials và rotation được thử.
- Dashboards phân biệt current/historical dữ liệu.
- Alert delivery có owner và acknowledgement.

### 24.4. Giai đoạn D: triển khai dần

~~~text
Lab simulator → 20 devices
              → 100 devices một site
              → 1.000 devices nhiều gateways
              → Multi-site production
              → Full fleet
~~~

Tại mỗi bước:
- Đo p95/p99 latency.
- Kiểm tra peak load và quotas.
- Xem costs per valid event.
- Kiểm tra security posture.
- Thực hiện rollback plan.
- Ghi lessons learned và cập nhật firmware/SDK support.

### 24.5. Infrastructure và configuration drift

Quản lý trong source control:
- IaC definitions cho IoT Hub, DPS, routes và endpoints.
- Configuration theo region/environment.
- Access/RBAC policies và identity lifecycle.
- Alert rules và diagnostic settings.
- Schema contracts và SDK versions.
- Runbooks, testing evidence và cost model.

Không để operator chỉnh production route thủ công rồi không ghi lại trong IaC: lần deploy tiếp theo có thể ghi đè một cấu hình quan trọng và làm mất telemetry.

## 25. Checklist production

### Thiết bị và identity

- [ ] Mỗi thiết bị có identity/trust model rõ ràng.
- [ ] Không nhúng hub-level owner key trong firmware.
- [ ] Device symmetric key/X.509 được bảo vệ và có kế hoạch rotation.
- [ ] DPS enrollment/assignment và fallback đã được thử nếu sử dụng.
- [ ] Device clocks được đồng bộ hoặc có clock-quality flags.
- [ ] Firmware SDK/protocol được cập nhật và có version policy.
- [ ] Device disable/decommission và key revocation có runbook.
- [ ] Edge buffer có giới hạn, dữ liệu bền vững và eviction policy.

### Ingestion và routing

- [ ] IoT Hub tier/units được sizing theo message volume và burst.
- [ ] Quotas, throttling, message size limits đã được kiểm tra.
- [ ] MQTT/AMQP/HTTPS lựa chọn theo thiết bị và network.
- [ ] TLS/certificate verification hoạt động trong môi trường thật.
- [ ] Built-in endpoint, custom routes và fallback được xác minh.
- [ ] Routes dựa JSON có content type/encoding và query tests.
- [ ] Raw storage route/capture đã có health monitoring.
- [ ] Mọi endpoint có least privilege và không mở public quá mức.

### Message contract và processing

- [ ] Payload có eventId, schemaVersion, time, units và quality status.
- [ ] deviceId payload được đối chiếu identity tin cậy.
- [ ] Sequence và boot ID đủ để phát hiện duplicate.
- [ ] Consumer có idempotency/retry/backoff đúng.
- [ ] Không tin exactly-once end-to-end nếu chưa chứng minh.
- [ ] Poison messages được quarantine theo retention policy.
- [ ] Late/out-of-order events được xử lý theo business rules.
- [ ] Hot alerts có cooldown, freshness và suppression.
- [ ] Consumer groups/checkpoints được phân tách đúng.
- [ ] Có raw replay và reconciliation cho storage/analytics.

### Security và governance

- [ ] Azure RBAC/data-plane roles/service identities tách rõ.
- [ ] Managed identity dùng khi integration hỗ trợ.
- [ ] Secrets ở Key Vault/secure store, không nằm trong logs.
- [ ] Private DNS/Private Endpoint/VPN/hybrid network đã kiểm thử nếu cần.
- [ ] PII/location data có phân loại, permission và retention rõ.
- [ ] Logs, backups và regional storage đáp ứng compliance.
- [ ] Threat detection/auditing và device key revocation có owner.
- [ ] Data deletion workflow bao gồm raw archive và downstream copies.

### Vận hành và chi phí

- [ ] Có alert cho device offline, gateway buffer, hub throttling.
- [ ] Có route health, archive freshness và consumer lag metrics.
- [ ] Data quality, duplicate/late ratios và schema drift được giám sát.
- [ ] Có cost budget, tags và cost per valid event.
- [ ] Có capacity/load test với reconnect storm.
- [ ] Có failover/DR design và kiểm thử theo RPO/RTO.
- [ ] Có incident runbooks cho connection/auth/route/consumer.
- [ ] Có owner, on-call và escalation paths.
- [ ] Có CI/CD/IaC và rollout staged.
- [ ] Có evidence trước khi mở rộng toàn fleet.

## 26. Câu hỏi tự kiểm tra

1. **Telemetry là gì?** Dữ liệu quan sát thiết bị gửi về cloud hoặc gateway.
2. **D2C nghĩa là gì?** Device-to-cloud communication.
3. **Device twin có thay được time-series storage không?** Không, chủ yếu dành cho trạng thái/configuration.
4. **IoT Hub khác Event Hubs ở đâu?** IoT Hub có device identity/management, Event Hubs dành cho generic event streams.
5. **IoT Hub built-in Event Hubs endpoint có phải namespace Event Hubs độc lập không?** Không.
6. **DPS giúp gì?** Provision/assign thiết bị tới IoT Hub theo attestation/enrollment.
7. **DPS có xử lý telemetry liên tục thay IoT Hub không?** Không.
8. **SAS và X.509 dùng làm gì?** Xác thực thiết bị theo cơ chế được hỗ trợ.
9. **Vì sao không để IoT Hub owner key trên firmware?** Trao quyền quá rộng và rủi ro lộ secrets.
10. **MQTT phù hợp khi nào?** Thiết bị kết nối lâu dài, ít tài nguyên, theo SDK/protocol hỗ trợ.
11. **IoT Hub có phải MQTT broker topic tùy ý không?** Không.
12. **Khi mạng chỉ cho TCP/443 nên đánh giá gì?** HTTPS hoặc MQTT/AMQP over WebSockets theo khả năng SDK.
13. **Content type/encoding cần chú ý khi routing JSON?** application/json và utf-8.
14. **DeviceId trong JSON có chứng minh danh tính thiết bị không?** Không, cần system identity.
15. **eventId cần thay đổi khi retry cùng một mẫu không?** Không, giữ ổn định để dedup.
16. **sequence có thể reset khi nào?** Khi firmware/device reboot hoặc bug; dùng bootId.
17. **Telemetry temperature cần thêm gì ngoài con số?** Unit, timestamp, device/source và quality.
18. **Hot path phục vụ gì?** Alerts/operational processing gần thời gian thực.
19. **Cold path phục vụ gì?** Archive, replay, analytics và ML dài hạn.
20. **Message routing giải quyết gì?** Đưa messages tới endpoints theo conditions.
21. **Bật routes có bảo đảm built-in endpoint luôn nhận tất cả messages không?** Không; kiểm tra route/fallback.
22. **Azure Stream Analytics thường dùng cho gì?** Streaming SQL-like transformations/windows.
23. **Azure Functions Event Hubs trigger cần chú ý gì?** Checkpoint, retries, concurrency và idempotency.
24. **Data Explorer có thay Blob raw archive không?** Không mặc định; dùng theo query/retention requirement.
25. **Tại sao edge buffer quan trọng?** Tránh mất data khi mạng gián đoạn.
26. **Retry không backoff gây gì?** Throttling, pin hao và burst chi phí.
27. **ACK của IoT Hub có chứng minh dashboard cập nhật không?** Không.
28. **Tại sao phải thiết kế at-least-once/replay?** Để xử lý messages bị gửi lặp hoặc đọc lại.
29. **Một cách tạo idempotency key là gì?** deviceId + bootId + sequence.
30. **Consumer có thể chỉ query duplicate rồi insert không?** Không an toàn nếu concurrency không có atomic constraint.
31. **Ordering có phải global theo mọi devices không?** Không.
32. **Poison messages xử lý ra sao?** Validate, quarantine, checkpoint/retry theo policy.
33. **Event time khác arrival time thế nào?** Lúc đo và lúc cloud nhận.
34. **Watermark/late policy quan trọng vì sao?** Để xử lý dữ liệu đến trễ và bounded state.
35. **15.000 devices gửi 1 phút một lần tạo bao nhiêu messages/ngày?** 21,6 triệu.
36. **Vì sao average 250 msg/s không đủ sizing?** Burst và reconnect backlog.
37. **IoT Hub scale units có tự tăng consumer capacity không?** Không.
38. **Private Endpoint có tự giải quyết kết nối thiết bị internet không?** Không, cần private network reachability.
39. **Xóa telemetry khỏi một Gold table có xóa toàn bộ raw archive không?** Không.
40. **Một SLO hợp lý cần xác định gì?** Mẫu số, latency window, phạm vi, đo lường và owner.
41. **Làm sao kiểm tra archive completeness?** So accepted/routed vs persisted event IDs theo window, tính delay/duplicate.
42. **Vì sao alert trễ không nên phát như sự cố hiện tại?** Dữ liệu backlog có thể đã hết tính khẩn cấp.
43. **IoT system RPO/RTO có phải giống nhau cho hot/cold path không?** Không, tùy business requirements.
44. **Multi-hub có tự đồng bộ identities/DR không?** Không mặc định; phải thiết kế/provision/reconcile.
45. **Khi nào có thể dùng IoT Central?** Khi chức năng platform-managed application phù hợp nghiệp vụ.
46. **Khi nào cần edge processing?** Mất mạng, latency cục bộ, giảm băng thông hoặc protocol conversion.
47. **Vì sao phải theo dõi schema rejects?** Thiết bị có thể kết nối tốt nhưng payload không dùng được.
48. **Vì sao cost per valid event đáng tin hơn cost per accepted event?** Phản ánh duplicate/invalid và hiệu quả xử lý.
49. **Khi gặp 429 trước hết nên xác định điều gì?** Service/layer nào bị throttling và traffic burst.
50. **Điều kiện của một rollout IoT an toàn?** Identity, routing, hot/cold, quality, monitoring, load/DR tests, budgets và runbooks đều đạt.

## 27. Tài liệu tham khảo

Các trang chính thức để kiểm tra service feature matrix, SDK, hạn mức và cấu hình hiện hành:

- [Azure IoT Hub documentation](https://learn.microsoft.com/azure/iot-hub/) — danh tính thiết bị, IoT Hub, D2C và service management.
- [What is Azure IoT Hub?](https://learn.microsoft.com/azure/iot-hub/iot-concepts-and-iot-hub) — kiến trúc và các khái niệm chính.
- [Device-to-cloud communication](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-d2c-guidance) — gửi telemetry, routing và semantics.
- [IoT Hub message routing](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-messages-d2c) — built-in endpoints, routing và application properties.
- [Azure IoT Hub routing tutorial](https://learn.microsoft.com/azure/iot-hub/tutorial-routing) — cấu hình tuyến thông điệp và Storage.
- [Azure IoT Hub Device Provisioning Service](https://learn.microsoft.com/azure/iot-dps/) — enrollment, attestation và hub assignment.
- [IoT Hub supported protocols](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-protocols) — MQTT, AMQP và HTTPS behavior.
- [Azure IoT device SDKs](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-sdks) — lựa chọn SDK thiết bị.
- [Azure IoT Hub quotas and throttling](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-quotas-throttling) — các giới hạn theo tier.
- [Azure IoT Hub pricing](https://azure.microsoft.com/pricing/details/iot-hub/) — metering/units/pricing.
- [Azure IoT Edge](https://learn.microsoft.com/azure/iot-edge/) — edge modules và thiết kế giải pháp tại biên.
- [Azure IoT Operations](https://learn.microsoft.com/azure/iot-operations/) — giải pháp IoT/edge hiện đại theo prerequisites.
- [Azure Event Hubs](https://learn.microsoft.com/azure/event-hubs/) — partitions, consumer groups, event ingestion.
- [Azure Stream Analytics](https://learn.microsoft.com/azure/stream-analytics/) — xử lý sự kiện theo thời gian.
- [Azure Functions Event Hubs trigger](https://learn.microsoft.com/azure/azure-functions/functions-bindings-event-hubs-trigger) — trigger, checkpoint và scale.
- [Azure Data Explorer](https://learn.microsoft.com/azure/data-explorer/) — KQL và analytics trên telemetry.
- [Azure Blob Storage / ADLS Gen2](https://learn.microsoft.com/azure/storage/blobs/data-lake-storage-introduction) — cold storage và data lake.
- [Azure Databricks](https://learn.microsoft.com/azure/databricks/) — xử lý Bronze/Silver/Gold và phân tích dữ liệu.
- [Azure IoT Hub monitoring](https://learn.microsoft.com/azure/iot-hub/monitor-iot-hub) — Azure Monitor metrics và diagnostic logs.
- [Azure IoT Hub security](https://learn.microsoft.com/azure/iot-hub/iot-hub-security-ground-up) — bảo mật thiết bị và dịch vụ.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — theo dõi cost, budgets và tags.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — dự toán theo tier, region và workload.

**Kết luận:** kiến trúc tiếp nhận telemetry IoT trên Azure không phải chỉ là “thiết bị gửi JSON vào cloud”. **Azure IoT Hub** giúp xác thực và tiếp nhận dữ liệu từ thiết bị; **DPS** hỗ trợ provisioning; **edge buffering** giữ dữ liệu khi mất mạng; **routing và Event Hubs-compatible/custom endpoints** phân phối tới hot/cold paths; **Functions/Stream Analytics, ADLS Gen2, Data Explorer và Databricks** xử lý, lưu và phân tích theo yêu cầu. Một giải pháp production phải có telemetry contract, idempotency, late-event policy, kiểm soát danh tính và mạng, monitoring từng chặng, recovery/DR và mô hình chi phí dựa trên tải thực. Chỉ chốt kiến trúc sau khi đã thử thiết bị, mạng, burst, consumer replay, dữ liệu trễ, bảo mật và khôi phục.

