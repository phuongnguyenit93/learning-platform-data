# Device twin, direct method và cloud-to-device message

Trong module **CLOUD_PROVIDERS_AZURE**, chúng ta khám phá hệ sinh thái Microsoft Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, compute, lưu trữ và dữ liệu; mục tiêu là biết triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng trên Azure. Trong chương **IoT và xử lý tại biên**, bài học này tập trung vào **Azure IoT Hub** và ba cơ chế điều khiển, đồng bộ trạng thái từ cloud xuống thiết bị: **device twin**, **direct method** và **cloud-to-device (C2D) message**.

Hãy tưởng tượng một doanh nghiệp quản lý 50.000 thiết bị đo nhiệt độ và tủ lạnh thông minh. Cloud muốn đổi chu kỳ thu thập telemetry, yêu cầu một thiết bị đang online chụp ảnh chẩn đoán và gửi một thông báo vận hành cho thiết bị có thể đang offline. Cả ba hành động đều đi theo hướng cloud → device nhưng **không nên dùng chung một cơ chế**: cấu hình trạng thái dài hạn khác lời gọi cần phản hồi ngay, và cả hai khác một message cần nằm chờ thiết bị kết nối.

Sau bài học, bạn có thể:

- Phân biệt **desired properties, reported properties và tags** trong device twin; hiểu đồng bộ cuối cùng, version, ETag và optimistic concurrency.
- Chọn **direct method** khi cần yêu cầu–phản hồi đối với thiết bị trực tuyến; xử lý timeout và kết quả thực thi chưa rõ.
- Chọn **C2D message** cho thông điệp gửi một chiều có khả năng lưu tạm trong hàng đợi khi thiết bị offline, trong giới hạn TTL/quota.
- Hiểu khác biệt giữa **transport acknowledgement**, **business acknowledgement** và **trạng thái thiết bị đã thực sự áp dụng**.
- Thiết kế device handler bằng **Java IoT SDK**, phân biệt service-side với device-side, kết hợp IoT Hub với Azure Functions/Service Bus/Storage khi cần.
- Bảo vệ luồng IoT bằng **device identity, Microsoft Entra ID/RBAC phía dịch vụ, SAS/X.509, TLS**, phân quyền và idempotency.
- Xây telemetry/tracing, cảnh báo, runbook offline/failover và kiểm thử cho hàng nghìn thiết bị mà không gây bão lệnh.

## 1. Vai trò của Azure IoT Hub trong điều khiển thiết bị

**Azure IoT Hub** cung cấp một lớp giao tiếp được quản lý giữa ứng dụng cloud và thiết bị có danh tính. Thiết bị thường có kết nối outbound tới IoT Hub; cloud không nhất thiết biết IP hay mở một cổng inbound trên thiết bị.

```text
                      Cloud control plane
               Java service / Azure Functions
                          |
                 Azure IoT Hub APIs
                   /      |      \
                  /       |       \
           Device twin  Direct   Cloud-to-device
           properties   method       message
                  \       |       /
                   \      |      /
                 IoT Hub device identities
                          |
                MQTT / AMQP / HTTPS*
                          |
                     Edge devices
                  /        |        \
                sensor    gateway   controller

* Khả năng của từng cơ chế tùy transport/SDK; không
  giả định HTTPS polling có mọi tính năng như MQTT/AMQP.
```

Thiết bị có thể đồng thời gửi **device-to-cloud telemetry (D2C)** về số đo, trạng thái và kết quả thực thi dài hạn. Tuy nhiên, D2C telemetry là một luồng khác; việc IoT Hub chấp nhận message từ thiết bị **không** tự chứng minh cloud command đã được thực hiện hoặc dữ liệu đã được ghi bền vững vào database nghiệp vụ.

### 1.1. Điều khiển từ cloud không giống RPC trực tiếp qua Internet

Direct method có mô hình request–response nhưng đi **qua IoT Hub** và phụ thuộc thiết bị còn kết nối, có handler sẵn sàng, cùng thời hạn chờ. Device twin mang **trạng thái mong muốn và trạng thái báo cáo**, không phải RPC. C2D message là giao tiếp **bất đồng bộ một chiều**, có lưu tạm theo đặc tính hub/TTL, không bảo đảm thiết bị đã hoàn thành nghiệp vụ.

### 1.2. Ba câu hỏi để chọn cơ chế

Trước khi gửi một thao tác xuống thiết bị, hỏi:

1. Đây là **cấu hình/trạng thái cần hội tụ** hay một hành động xảy ra đúng một lần?
2. Cloud có cần biết kết quả **ngay trong request hiện tại** không?
3. Thiết bị có thể **offline nhiều giờ** và cần nhận thông điệp sau khi quay lại không?

Từ đó chọn cơ chế, yêu cầu acknowledgement và cách khôi phục.

## 2. Bảng quyết định: twin, direct method hay C2D?

| Tiêu chí | **Device twin** | **Direct method** | **C2D message** |
|---|---|---|---|
| Mục đích chính | Đồng bộ trạng thái/cấu hình mong muốn và trạng thái báo cáo | Gọi một hành động, lấy response trong thời gian giới hạn | Gửi thông điệp một chiều để xử lý bất đồng bộ |
| Thiết bị offline | Desired state vẫn lưu; thiết bị đồng bộ khi kết nối | Không gọi thành công nếu thiết bị không reachable/không có handler | Message có thể chờ trong hàng đợi thiết bị, **trong TTL/quota** |
| Cloud nhận kết quả đồng bộ | Không; xem reported properties/bằng chứng khác | Có response status/payload từ handler nếu kịp | Không có business response đồng bộ |
| Data semantics | **Trạng thái mới nhất** quan trọng, không lưu mọi lần đổi | Invocation có deadline, không có offline queue | Message được lưu và phân phối theo khả năng/TTL |
| Retry/duplicate | Desired cần áp dụng idempotent; versions để chống cũ | Timeout có thể gây **unknown outcome**, retry phải idempotent | Có thể bị deliver/reprocess nhiều lần; dùng message ID |
| Dung lượng | JSON twin có quota/kích thước; không chứa data stream lớn | Payload request/response bị giới hạn | Message payload/properties có giới hạn và TTL |
| Ví dụ | `telemetryIntervalSec=60` | `captureDiagnostics()` | Thông báo `maintenanceNotice` |
| Theo dõi hoàn tất | Reported + job/telemetry | Method response; long-running vẫn cần telemetry/twin | Application-level ACK D2C/twin, không chỉ transport feedback |

### 2.1. Chọn sai gây vấn đề gì?

- Dùng twin cho `reboot` như một boolean `true`: khi thiết bị reconnect, desired vẫn là `true` và có thể **reboot lặp**.
- Gọi direct method `installFirmware` chạy 30 phút: method timeout, cloud không biết thiết bị vẫn đang cập nhật.
- Gửi C2D message rồi xem “đã accepted by hub” là thiết bị đã hoàn tất: **sai tầng acknowledgement**.
- Dùng C2D queue cho cấu hình lâu dài và thiết bị offline quá TTL: thiết bị có thể **không bao giờ nhận được** cấu hình.

### 2.2. Một workflow có thể dùng nhiều cơ chế

Một rollout firmware v2 có thể:

1. Cloud ghi **desired** target version và rollout ID.
2. Thiết bị đồng bộ, validate và phản hồi **reported** `downloading` → `installed`.
3. Cloud có thể gọi **direct method** `startUpdate` cho thiết bị đang online khi cần kích hoạt ngay.
4. **C2D message** gửi thông báo ngắn cho thiết bị có thể đang offline, nhưng không là nguồn thật duy nhất.
5. Service ghi audit/rollout history vào database, dùng telemetry và reported trạng thái để xác nhận.

Một command quan trọng có thể cần **business command store** riêng ngoài IoT Hub để audit, dedup và orchestration.

## 3. Device twin là gì?

Mỗi identity thiết bị IoT Hub có một **device twin**, một tài liệu trạng thái JSON được IoT Hub quản lý. Nó thường gồm:

- **`tags`:** metadata phía dịch vụ, phục vụ phân nhóm/query; thiết bị không đọc trực tiếp tags qua device twin API.
- **`properties.desired`:** trạng thái cloud mong muốn, cloud/service cập nhật; thiết bị đọc và nhận thông báo khi thay đổi trong phạm vi hỗ trợ.
- **`properties.reported`:** trạng thái thiết bị tự báo, thiết bị cập nhật; cloud/service đọc để biết thiết bị thực tế.
- **Metadata/version:** IoT Hub quản lý `$version`, thời gian cập nhật và ETag/metadata ở các phần tương ứng.

### 3.1. Ví dụ device twin

```json
{
  "deviceId": "fridge-042",
  "tags": {
    "site": "hcm-warehouse-02",
    "model": "coldstore-v3",
    "environment": "production"
  },
  "properties": {
    "desired": {
      "telemetryIntervalSec": 60,
      "temperatureTargetC": 4.0,
      "firmware": {
        "targetVersion": "2.4.0",
        "rolloutId": "rollout-20261120-b"
      },
      "$version": 27
    },
    "reported": {
      "telemetryIntervalSec": 30,
      "temperatureTargetC": 4.0,
      "firmware": {
        "currentVersion": "2.3.1",
        "status": "downloading",
        "appliedRolloutId": "rollout-20261120-a"
      },
      "lastAppliedDesiredVersion": 26,
      "$version": 48
    }
  }
}
```

**Đây là JSON minh họa đã rút gọn**, không phải toàn bộ twin do API trả về. Các trường `deviceId`, `$version` và metadata hệ thống được IoT Hub quản lý; ứng dụng **không tự gửi $version trong desired patch**. Giá trị trong ví dụ cho thấy cloud muốn interval 60 giây nhưng device mới report 30 giây: **desired không đồng nghĩa đã áp dụng**.

### 3.2. Ai có thể đọc/ghi phần nào?

| Thành phần | Cloud service | Device client |
|---|---|---|
| `tags` | Đọc/ghi qua service-side APIs theo quyền | Không có quyền truy cập tags qua device twin interface |
| `desired` | Đọc/ghi | Đọc và nhận desired update, không tự ghi desired |
| `reported` | Đọc | Ghi reported properties |
| Identity / security | Service registry/data-plane permissions | Đăng nhập bằng identity riêng của thiết bị |

Thiết bị không được phép tự gắn tag `role=admin` rồi dùng tag đó thay đổi phân quyền backend. Tag dùng cho **management/query**, không thay IAM authorization.

### 3.3. Desired state và reported state không phải hai bản sao

Mẫu đúng:

```text
Cloud desired:
  telemetryIntervalSec = 60
       |
       v
IoT Hub lưu trạng thái mong muốn
       |
       v
Device nhận delta / GET twin sau reconnect
       |
       v
Validate -> lưu local config -> áp dụng an toàn
       |
       v
Device reported:
  telemetryIntervalSec = 60
  lastAppliedDesiredVersion = 27
  applyStatus = "succeeded"
```

Thiết bị chỉ nên report “succeeded” **sau khi áp dụng thực sự**, không ngay lúc nhận desired. Nếu áp dụng thất bại, report mã lỗi/trạng thái thay vì giả vờ đồng bộ.

## 4. Desired properties: cập nhật cấu hình theo trạng thái cuối

Ví dụ service muốn đổi interval và target temperature:

```json
{
  "properties": {
    "desired": {
      "telemetryIntervalSec": 60,
      "temperatureTargetC": 4.0
    }
  }
}
```

IoT Hub lưu patch desired. Khi thiết bị online và có subscription/handler phù hợp, device có thể nhận thông báo delta. Khi offline, desired state được lưu để thiết bị **GET full twin** hoặc đồng bộ sau reconnect. Không dựa vào việc nhận đủ *mọi delta theo thời gian* như event log.

### 4.1. Patch vs replace

**Patch** thay các trường được chỉ định mà không chủ ý ghi đè toàn bộ sibling fields. **Replace** toàn bộ twin/section nếu API cho phép có thể ghi mất cập nhật người khác nếu dùng stale copy. Với system nhiều controllers, ưu tiên cập nhật có điều kiện/versioning và giới hạn ownership theo từng namespace.

Ví dụ cloud team A quản lý `telemetryIntervalSec`, team B quản lý `firmware.targetVersion`. Một updater không nên gửi toàn bộ desired được lấy từ nhiều giờ trước để vô tình xóa đổi của team kia.

### 4.2. Xóa property bằng null

Trong patch semantics của IoT Hub twin, một property đặt `null` có thể dùng để **xóa** property đó; không nhầm với “đặt null là giá trị cấu hình phải áp dụng”. Ví dụ:

```json
{
  "properties": {
    "desired": {
      "deprecatedSamplingMode": null
    }
  }
}
```

Thiết bị phải có logic **default/fallback** rõ khi trường biến mất. Thay đổi và xóa config phải được thử trên firmware cũ để tránh crash sau khi reconnect.

### 4.3. Version và patch đến không theo giả định

Desired có `$version` giúp device biết mức cập nhật đã thấy. Trên mỗi handler:

1. Đọc version từ desired patch hoặc full twin.
2. So với `lastAppliedDesiredVersion` đã lưu bền vững nếu cần.
3. Không áp dụng một patch **cũ hơn** state đã hoàn tất.
4. Parse/validate toàn cấu hình phụ thuộc thay vì chỉ dùng delta thiếu context.
5. Report outcome cùng version/rollout ID.

Không giả định desired patch chỉ tới đúng một lần, hoặc không có gap trong các versions khi thiết bị offline. **Sau reconnect**, tốt nhất đồng bộ full twin theo chiến lược SDK/device.

## 5. Reported properties: xác nhận trạng thái thực tế

Device cập nhật reported sau khi thử áp dụng cấu hình:

```json
{
  "telemetryIntervalSec": 60,
  "temperatureTargetC": 4.0,
  "lastAppliedDesiredVersion": 27,
  "applyStatus": "succeeded",
  "firmware": {
    "currentVersion": "2.4.0",
    "status": "installed",
    "appliedRolloutId": "rollout-20261120-b"
  }
}
```

Đây là **phần reported-properties patch do device gửi** chứ không phải full twin response. Có thể thêm `lastApplyErrorCode` và `lastApplyTimeUtc` theo contract. Không gửi raw access tokens, secrets hoặc log nhạy cảm vào reported.

### 5.1. Trạng thái nên là state machine

Một firmware rollout có thể có:

```text
PENDING -> VALIDATING -> DOWNLOADING -> VERIFYING
     -> INSTALLING -> REBOOTING -> SUCCEEDED
                         |
                         +----------> FAILED
```

Từng transition nên có **rollout ID, desired version, timestamp, error code** được thống nhất. Dịch vụ cloud không đánh dấu toàn bộ rollout thành công chỉ vì IoT Hub đã nhận desired update.

### 5.2. Báo lỗi không thay “reported” bằng “desired”

Nếu thiết bị có sensor hỏng và không thể áp dụng `telemetryIntervalSec=60`, reported nên phản ánh **giá trị đang chạy** và trạng thái lỗi:

```json
{
  "telemetryIntervalSec": 30,
  "lastAppliedDesiredVersion": 26,
  "applyStatus": "failed",
  "lastFailedDesiredVersion": 27,
  "lastApplyErrorCode": "SENSOR_BUSY"
}
```

Giữ thông tin này giúp cloud phân biệt **không kết nối**, **chưa áp dụng** và **thất bại**.

### 5.3. Twin không phải telemetry store

Không cập nhật reported mỗi 100 ms cho nhiệt độ đo liên tục. Twin có quota/throttling và phù hợp **state tương đối ổn định**, không phải time-series storage. Số đo định kỳ nên dùng **device-to-cloud telemetry** và đích như Azure Data Explorer/Storage/stream processor theo kiến trúc. Dùng reported để tóm tắt trạng thái cần quản lý, ví dụ firmware version, mode hoặc health tổng hợp.

## 6. Tags, truy vấn đội thiết bị và job quy mô lớn

Tags có thể dùng để nhóm thiết bị:

```json
{
  "site": "hcm-warehouse-02",
  "region": "south",
  "model": "coldstore-v3",
  "maintenanceGroup": "wave-b"
}
```

Service-side có thể truy vấn identities/twins theo tags/reported trong khả năng **IoT Hub query language**; cú pháp thường theo dạng `SELECT * FROM devices WHERE ...`. Thông tin truy vấn/index có độ trễ cập nhật; không xem kết quả query là một snapshot tuyệt đối nhất quán với thời điểm vừa thay tag.

### 6.1. Ví dụ truy vấn fleet

```sql
SELECT *
FROM devices
WHERE tags.model = 'coldstore-v3'
  AND tags.maintenanceGroup = 'wave-b'
```

Đây là **IoT Hub twin query syntax**, không phải T-SQL của Azure SQL Database. Hỗ trợ projection, predicates và indexing có giới hạn riêng; xác minh với Hub tier/SDK và quyền hiện tại.

### 6.2. Thay cấu hình hàng nghìn thiết bị

Không nhất thiết chạy một vòng `for` và gửi 50.000 patches đồng thời. Với quy mô lớn, cân nhắc **IoT Hub jobs** cập nhật twin hoặc invoke direct method cho tập thiết bị khi tính năng/tier hỗ trợ. Thiết kế:

- Chia rollout thành waves/canary theo tags/model/site.
- Giới hạn tốc độ theo **IoT Hub quotas/throttling** và số thiết bị online.
- Theo dõi job state, timeout, số succeeded/failed.
- Xác nhận **reported business outcome** sau job, không chỉ job API status.
- Có pause/rollback/quarantine nhóm thiết bị gặp lỗi.

Tags có thể bị đổi trong quá trình chạy job; định nghĩa rõ **cohort snapshot/selection semantics**, không mặc định toàn bộ queries và jobs luôn trùng thiết bị.

## 7. Concurrency khi nhiều cloud services cập nhật twin

IoT Hub lưu **ETag** trên twin để hỗ trợ optimistic concurrency khi dùng các thao tác cập nhật tương thích. Với kiến trúc nhiều writers, vấn đề điển hình:

```text
Service A GET twin at ETag E1
Service B GET twin at ETag E1
Service B UPDATE desired.firmware -> ETag E2
Service A REPLACE twin dựa trên E1
    -> nguy cơ mất thay đổi mới hoặc bị 412 conflict
```

### 7.1. Optimistic concurrency

Khi API hỗ trợ điều kiện **If-Match/ETag**, chọn một chiến lược:

1. Đọc twin + ETag.
2. Tính patch/update theo ownership và contract.
3. Gửi update có điều kiện với ETag đã đọc.
4. Nếu nhận **precondition failed / conflict**, lấy bản mới và **merge logic đúng**, không ghi đè mù.
5. Dừng retry sau số lần giới hạn, ghi incident khi conflict liên tục.

Chi tiết API/SDK về ETag, patch/update và conflict có thể khác; **xác minh method signatures của phiên bản SDK**. Không truyền wildcard ETag vô điều kiện cho các thao tác có khả năng ghi đè dữ liệu của một controller khác.

### 7.2. Desired version không thay business revision

`$version` do IoT Hub quản lý giúp sắp thứ tự cập nhật twin; tuy nhiên service có thể cần **configurationRevision** hoặc `rolloutId` riêng để xác định một quyết định nghiệp vụ và đối chiếu đa dịch vụ.

```json
{
  "configurationRevision": "config-rev-0048",
  "telemetryIntervalSec": 60,
  "requestedBy": "fleet-config-service",
  "effectiveAfterUtc": "2026-11-21T00:00:00Z"
}
```

Một config revision vẫn cần validation trên device; không cho phép cloud thay đổi **safety-critical actuator parameters** chỉ bằng một JSON patch không có kiểm tra biên tại thiết bị.

### 7.3. Không gửi bí mật vào twin

Twin JSON thường có thể được đọc bởi nhiều principals có quyền quản lý thiết bị và có thể nằm trong logs/audits. Không lưu database passwords, SAS keys, device certificates, personal data hoặc API access tokens trong desired/reported/tags. Với cấu hình nhạy cảm, có thể gửi **opaque reference hoặc configuration version** và sử dụng cơ chế lấy secret bảo mật hơn theo threat model.

## 8. Direct method: lời gọi cần phản hồi đồng bộ

**Direct method** là lời gọi từ service/cloud tới handler trên thiết bị **đang reachable** thông qua IoT Hub. Cloud gửi **method name + JSON payload**, thiết bị chạy handler và trả **status + response payload** trước thời hạn chờ. Nó phù hợp với hành động ngắn khi cloud cần biết phản hồi trong cùng request.

Ví dụ:

```text
Java operations service
     |
     | invokeDeviceMethod(deviceId="fridge-042",
     |                    method="captureDiagnostics",
     |                    payload={"requestId":"cmd-117"})
     v
   Azure IoT Hub
     |
     | route to connected device
     v
Device direct method handler
     |
     | validate -> capture quick diagnostics -> return
     v
Response: {"status": 200, "payload": {"diagnosticId":"diag-719"}}
     |
     v
Cloud records result
```

Status `200` trong ví dụ là **mã response do handler thiết bị trả theo contract**, không phải bảo đảm kết quả đã được lưu tới Storage/SQL hoặc kiểm toán ở hệ thống khác.

### 8.1. Khi nào nên dùng?

- Yêu cầu thiết bị online đọc giá trị hiện tại rồi trả nhanh.
- Thử một hành động có thời gian ngắn và phản hồi xác định.
- Bật/tắt chế độ chẩn đoán **theo contract an toàn**, có device authorization.
- Gọi `ping` ứng dụng (để kiểm tra handler) thay vì chỉ biết trạng thái transport.
- Kích hoạt **một long-running job**, nhưng trả `accepted` với job ID và theo dõi kết quả qua reported/D2C.

### 8.2. Thiết bị offline: không có durable offline queue

Direct method **không phải** hàng đợi lệnh bền vững cho thiết bị offline. Nếu device chưa kết nối hoặc không subscribe/không có handler, invocation sẽ thất bại theo thời hạn và lỗi của API. Không kỳ vọng IoT Hub tự chạy phương thức đó sau khi thiết bị kết nối lại.

Nếu cần đảm bảo thiết bị offline **sau cùng áp dụng cấu hình**, ưu tiên **desired properties**. Nếu cần một thông điệp bất đồng bộ còn hạn, cân nhắc **C2D**. Nếu phải giữ command qua thời gian offline dài, cần **command store/workflow bền vững** ngoài direct method.

### 8.3. Hai loại thời hạn chờ

Các API gọi method thường có những tham số như:

- **Connection timeout:** thời gian IoT Hub chờ thiết bị reachable/đã đăng ký handler trong giới hạn được hỗ trợ.
- **Response timeout:** thời gian chờ handler trả kết quả sau khi invocation chuyển xuống thiết bị.

Cần phân biệt hai giai đoạn, chọn **total deadline** phù hợp API cloud. Mức timeout mặc định/giới hạn tối đa phụ thuộc service/SDK và có thể thay đổi; không hard-code giả định “chờ 60 giây” cho mọi implementation.

### 8.4. Device trả 202 Accepted có nghĩa gì?

Với firmware update cần 10 phút, handler có thể:

1. Validate request `requestId` và model/firmware version.
2. Lưu durable local job state.
3. Trả `status=202` cùng `jobId` sau vài giây.
4. Chạy download/verify/install ở background.
5. Cập nhật reported hoặc gửi D2C completion event khi hoàn tất.

`202` ở đây là **quy ước mã của ứng dụng**: chỉ xác nhận thiết bị đã nhận/lên lịch, không chứng minh firmware installed. Cloud phải kiểm tra job ID và trạng thái cuối.

## 9. Direct method và “unknown outcome” khi timeout

Đây là điểm dễ gây lỗi nhất khi thiết bị điều khiển phần cứng.

```text
Cloud                     IoT Hub                      Device
  |                         |                           |
  | invoke openValve(id=7)  |                           |
  |------------------------>|-------- invoke ---------->|
  |                         |              handler mở van|
  |                         |<------ status 200 ---------|
  |      X lost response / timeout                        |
  |                                                      |
  | cloud nhận timeout                                   |
  | Có nên gọi lại? **Không biết lệnh trước đã chạy chưa** |
```

**Timeout không chứng minh thiết bị không thực hiện thao tác.** Tương tự lỗi COMMIT ACK trong database, retry trực tiếp có thể tạo side effect hai lần.

### 9.1. Idempotency bằng commandId

Ví dụ cloud gửi:

```json
{
  "commandId": "cmd-20261120-117",
  "action": "setTargetTemperature",
  "targetC": 4.0,
  "expectedConfigRevision": "config-rev-0048"
}
```

Device nên:

1. Xác thực nguồn invocation qua kết nối IoT Hub đã ủy quyền và validate contract/payload.
2. Kiểm tra `commandId` có được xử lý trước đó chưa.
3. Nếu đã xử lý, trả **kết quả cũ** hoặc trạng thái hiện tại, không thực thi lại.
4. Nếu mới, ghi **in-progress record bền vững** (khi yêu cầu), kiểm tra điều kiện an toàn.
5. Thực thi hành động, lưu kết quả và trả response.
6. Report trạng thái hoàn tất qua twin/D2C khi cần audit.

**Dedup chỉ ở bộ nhớ RAM không đủ** nếu thiết bị reboot trong lúc chạy lệnh. Với side effect an toàn quan trọng, cần cơ chế local durable journal, operation reconciliation và giới hạn command validity.

### 9.2. Lệnh “set state” an toàn hơn “toggle”

So sánh:

```text
setFanSpeed(3)   -> nếu lặp lại cùng revision thường có thể idempotent
toggleFan()      -> gọi hai lần có thể trở về trạng thái ban đầu
incrementDose()  -> gọi hai lần có thể vượt liều
```

Với actuator có thể gây tác động vật lý, ưu tiên **desired target state + local safety bounds** thay vì command không idempotent. Không điều khiển safety-critical thiết bị qua cloud mà thiếu **local interlocks, watchdog, emergency stop và kiểm định** phù hợp.

### 9.3. Command expiration và chống replay

Một lệnh có thể có:

```json
{
  "commandId": "cmd-117",
  "issuedAtUtc": "2026-11-20T10:00:00Z",
  "expiresAtUtc": "2026-11-20T10:02:00Z",
  "requestedTargetC": 4.0
}
```

Device phải xử lý sai lệch thời gian và đồng hồ không tin cậy (offline), không chấp nhận commands quá cũ nếu hành động nguy hiểm. **Idempotency key + expiry + revision** có thể cần cùng nhau; chỉ có random ID không chống replay vô hạn nếu dedup state bị xóa.

### 9.4. Mã lỗi ứng dụng trong direct method

Ví dụ contract:

| Status ứng dụng | Diễn giải | Cloud action |
|---|---|---|
| `200` | Hoàn tất hành động nhanh | Ghi result, xác minh khi cần |
| `202` | Đã nhận và xử lý nền | Theo dõi job ID/telemetry |
| `400` | Payload sai | Sửa caller, không retry giống hệt |
| `403` | Device policy không cho phép | Kiểm tra quyền/safety, không bypass |
| `409` | State/revision conflict | Refresh state và ra quyết định mới |
| `429` | Device busy/throttled theo contract | Retry có backoff nếu idempotent |
| `500` | Handler lỗi nội bộ | Phân loại retry, điều tra device logs |

Các status là **quy ước ví dụ** chứ không phải tất cả các mã status được IoT Hub tự sinh. Phân biệt **lỗi invocation do hub/network** với **status do handler trả**.

## 10. Cloud-to-device message: thông điệp bất đồng bộ

**Cloud-to-device message (C2D)** cho phép ứng dụng cloud gửi thông điệp tới một device identity qua IoT Hub. Hub có thể **xếp hàng lưu tạm** cho thiết bị đang offline, theo TTL và service quotas. Device nhận message khi kết nối và xử lý theo API/protocol.

```text
Cloud service
     |
     | send C2D message(deviceId, payload, messageId, TTL)
     v
Azure IoT Hub per-device queue
     |
     +-- Device offline -> lưu tạm đến expiry/quota
     |
     +-- Device online -> deliver theo transport
     |
     v
Device message callback
     |
     +-- parse/validate/dedup
     +-- execute or persist local work
     +-- settle/ack theo transport/SDK nếu hỗ trợ
     |
     +--> optional business ACK qua device-to-cloud telemetry
```

### 10.1. Ví dụ payload C2D

```json
{
  "messageId": "notice-20261120-042",
  "type": "maintenanceNotice",
  "createdAtUtc": "2026-11-20T09:30:00Z",
  "expiresAtUtc": "2026-11-21T09:30:00Z",
  "notice": "Technician scheduled for inspection",
  "requiresAcknowledgement": true
}
```

Trong thực tế, `messageId`, TTL, correlation ID và delivery acknowledgment có thể nằm trong **IoT Hub message system/application properties**, không chỉ body JSON. Mẫu đưa cả `messageId` vào body để device handler dễ minh họa idempotency; đồng bộ body/header nếu dùng cả hai.

### 10.2. TTL không phải lưu trữ vô hạn

C2D message có **time-to-live (TTL)** theo IoT Hub message semantics và giới hạn dịch vụ; thiết bị offline lâu hơn TTL có thể không nhận được. Hàng đợi có giới hạn độ sâu/dung lượng và quotas. Tính năng “queue khi offline” **không** tương đương durable queue vô hạn như một command database.

Với cấu hình nên tồn tại sau nhiều tuần offline, dùng **twin desired state**, không chỉ C2D. Với nghiệp vụ audit mọi command quan trọng, lưu command trong **database/Service Bus** của ứng dụng rồi quản lý retry/expiry/device delivery có kiểm soát.

### 10.3. C2D là một chiều, không có response đồng bộ

Hub nhận message và đưa vào queue **không có nghĩa** device đã hiển thị thông báo, cập nhật cấu hình hoặc khởi động hành động. Nếu cloud cần biết đã xử lý, device phải gửi **application-level acknowledgment** (thường là D2C event/telemetry hoặc reported state) kèm `messageId`.

### 10.4. Phân biệt ba tầng acknowledgment

| Mức | Chứng minh | Không chứng minh |
|---|---|---|
| **Hub accepted** | IoT Hub đã chấp nhận message theo giao thức/quota | Device nhận hoặc xử lý |
| **Transport delivery/settlement** | Message đã được giao/settled theo semantics của protocol/client | Nghiệp vụ thực thi thành công |
| **Business ACK** | Device báo có bằng chứng xử lý theo contract | Mọi downstream side effect đã được lưu nếu không xác minh thêm |

Đặc biệt, các hành vi **complete/reject/abandon/feedback** phụ thuộc MQTT/AMQP/HTTPS và SDK. Không khẳng định một MQTT callback tự động bảo đảm transaction nghiệp vụ “exactly once”.

## 11. C2D delivery, feedback, order và duplicate

### 11.1. C2D feedback

IoT Hub có khả năng **delivery feedback** theo lựa chọn/system properties và đặc tính dịch vụ, để service biết tình trạng như delivery/expiry/rejection ở cấp được hỗ trợ. Nhưng **feedback không phải kết quả thực thi nghiệp vụ**; ví dụ thiết bị đã nhận message `scheduleMaintenance` nhưng không thể chạy do pin yếu.

Tùy SDK/API/transport, kiểu feedback và thời gian khả dụng khác nhau; xác minh khả năng đọc feedback queue/endpoint, retention và service quotas trước khi xây hệ thống phụ thuộc vào đó.

### 11.2. At-least-once, duplicate và ordering

Thiết kế handler theo hướng **chịu message trùng và arrival order không như kỳ vọng**; đừng giả định global ordering/exactly-once business execution. Có thể có retransmission sau reconnect, timeout hoặc failure giữa xử lý và settlement.

Ví dụ:

```text
messageId=msg-117, commandRevision=5
messageId=msg-118, commandRevision=6

Thiết bị nhận msg-118 trước,
không được áp msg-117 cũ sau đó để quay về config cũ.
```

Device cần version/revision precondition; với command không idempotent cần local journal và business reconciliation.

### 11.3. Không dùng C2D làm kho lệnh kinh doanh vĩnh viễn

Nếu backend phải bảo đảm “mọi firmware rollout được audit và hoàn tất trong 14 ngày”, cần lưu **business command record** ở database, có state machine, retry deadlines, device acknowledgment và dashboard. C2D là **kênh truyền trong một phần vòng đời**, không phải hệ thống workflow có lịch sử vô hạn.

### 11.4. Không trộn D2C và C2D

```text
Device-to-cloud:  sensor telemetry, state, business ACK
Cloud-to-device:  notification/work item xuống device
Direct method:    invoke handler online, immediate response
Device twin:      desired/reported state document
```

IoT Hub routing/consumer groups/Event Hubs-compatible endpoint thường phục vụ **D2C ingestion**, không phải cách duy nhất để nhận C2D messages trên thiết bị. Chọn API/client đúng hướng truyền.

## 12. So sánh hành vi khi thiết bị offline

| Trạng thái thiết bị | Twin desired | Direct method | C2D |
|---|---|---|---|
| Online, handler khỏe | Nhận patch/đọc twin rồi áp dụng | Nhận và trả response trong deadline | Nhận message theo protocol |
| Offline 5 phút | Desired mới nhất vẫn lưu | Thường invocation fail/timeout | Có thể chờ nếu TTL và quota cho phép |
| Offline vượt TTL C2D | Desired mới nhất vẫn lưu | Không có offline replay | Message có thể expired/không còn |
| Reconnect sau thay nhiều desired versions | GET full desired/latest state | Không tự phát lại method cũ | Nhận những messages còn hiệu lực |
| Reconnect sau firmware reset | Sync desired và báo state | Chỉ chạy method mới | Dedup bằng local message journal |
| Hub bị throttle hoặc queue đầy | Update có thể bị throttled/fail | Invoke có thể bị throttled/fail | Send có thể fail; cloud phải retry có kiểm soát |

### 12.1. “Online” không phải trạng thái tuyệt đối

Trong môi trường thực tế, connection state và telemetry có thể không cập nhật tức thì; thiết bị có thể giữ TCP socket nhưng handler bị treo, hoặc kết nối qua gateway gián đoạn. Đừng ra quyết định safety-critical chỉ dựa trên một flag online/offline. Hãy dùng **fresh heartbeat, timeout, ack state và thực thi local safety constraints**.

## 13. Chuẩn hóa command envelope cho IoT device

Để xử lý retry, audit và truy vết, service nên có một **command envelope** nhất quán khi gửi qua direct method hoặc C2D:

```json
{
  "schemaVersion": 2,
  "commandId": "cmd-20261120-117",
  "targetDeviceId": "fridge-042",
  "type": "captureDiagnostics",
  "requestedByService": "fleet-operations",
  "requestedAtUtc": "2026-11-20T10:00:00Z",
  "expiresAtUtc": "2026-11-20T10:05:00Z",
  "expectedConfigRevision": "config-rev-0048",
  "payload": {
    "includeSensors": true,
    "maxDurationSeconds": 10
  }
}
```

Đây là **application protocol mẫu**, không phải JSON bắt buộc của IoT Hub. Với direct method, `type` thường thể hiện ở method name còn envelope nằm trong method payload; với C2D, một số metadata nên dùng message properties.

### 13.1. Các trường quan trọng

| Trường | Vai trò | Kiểm tra |
|---|---|---|
| `schemaVersion` | Tương thích giữa firmware và service | Chỉ chấp nhận versions hỗ trợ |
| `commandId` | Dedup/correlation | Unique theo namespace/tenant/device |
| `targetDeviceId` | Ngăn nhầm đích logic | So với chính identity device và contract |
| `type` | Hành động được hỗ trợ | Allowlist; không thực thi code tùy ý |
| `requestedAtUtc` / `expiresAtUtc` | Chống lệnh quá cũ | Đồng hồ/TTL/clock-skew policy |
| `expectedConfigRevision` | Tránh thao tác trên state đã đổi | Compare version/revision |
| `payload` | Dữ liệu nghiệp vụ | Validate schema/range và quyền |

### 13.2. State machine của command

```text
CREATED
   |
   v
DISPATCHING ----(hub error)------> DISPATCH_RETRY
   |
   v
HUB_ACCEPTED / INVOKED
   |
   +------> DEVICE_ACCEPTED ---> RUNNING ---> SUCCEEDED
   |                                   |
   |                                   +----------> FAILED
   |
   +------> EXPIRED / NOT_DELIVERED
   |
   +------> UNKNOWN_OUTCOME ---> RECONCILE
```

Đây là state machine **business command store** của ứng dụng, không phải một tập trạng thái duy nhất do Azure IoT Hub cung cấp. Đối với twin desired, sẽ hợp lý hơn khi theo dõi **configuration revision applied** thay vì mỗi update là một công việc phải nhận đủ các trạng thái.

### 13.3. Tại sao cần audit store riêng?

Twin thể hiện state cuối; direct method response có deadline; C2D queue có TTL. Nếu doanh nghiệp cần lưu lịch sử lệnh, người yêu cầu, thời điểm, xác nhận và retry qua nhiều tuần, hãy dùng một database có giao dịch phù hợp (ví dụ Azure SQL/Cosmos DB theo nhu cầu), có **unique commandId**, retry state và retention policy. IoT Hub là **communication boundary**, không thay application workflow database.

## 14. Thực hành Azure CLI: chuẩn bị và đọc twin

Azure CLI cùng **Azure IoT extension** (nếu các nhóm lệnh chưa được tích hợp) có các commands quản lý IoT Hub. Các lệnh dưới đây là **mẫu dành cho môi trường lab**, yêu cầu quyền truy cập IoT Hub phù hợp; cú pháp/flags có thể thay đổi giữa các CLI/extension versions. Kiểm tra `az ... --help` tại máy triển khai trước khi dùng production.

### 14.1. Chuẩn bị biến môi trường

```bash
az login
az account set --subscription "<subscription-id>"

HUB_NAME="<your-iot-hub-name>"
DEVICE_ID="fridge-042"

# Nếu CLI báo thiếu nhóm lệnh IoT:
# az extension add --name azure-iot

az iot hub device-twin show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --output json
```

**Không tạo hoặc đổi device production ngoài quyền sở hữu.** Khi có nhiều subscriptions, kiểm tra `az account show` để tránh cập nhật nhầm hub.

### 14.2. Cập nhật desired property

Với CLI IoT extension hỗ trợ tham số `--set`:

```bash
az iot hub device-twin update \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --set properties.desired.telemetryIntervalSec=60 \
  --output json
```

Lệnh trên minh họa **cloud cập nhật desired**, không làm device report ngay 60 giây. Cần kiểm tra sau bằng `device-twin show` và đối chiếu `properties.reported.telemetryIntervalSec` hoặc `lastAppliedDesiredVersion`.

**Lưu ý concurrency:** các lệnh CLI update cụ thể có thể sử dụng ETag hoặc default merge semantics theo extension version. Với nhiều writers hoặc yêu cầu bảo vệ cao, dùng SDK/REST có điều kiện cập nhật rõ và kiểm thử conflict/412.

### 14.3. Query fleet theo tag

Khi CLI hỗ trợ IoT Hub twin query:

```bash
az iot hub query \
  --hub-name "$HUB_NAME" \
  --query-command \
    "SELECT * FROM devices WHERE tags.maintenanceGroup = 'wave-b'" \
  --output json
```

Quyền service-side query có thể khác quyền update twin. Không coi kết quả trả về là một transactionally consistent list với những tag changes đang diễn ra.

### 14.4. Dữ liệu trong outputs

Full twin có thể chứa tags, desired/reported và metadata nhạy cảm vận hành. Không đẩy nguyên JSON twin production lên public paste hoặc CI console log; ưu tiên extract những fields cần kiểm tra, dùng RBAC và log retention.

## 15. Azure CLI: gọi direct method

Trong lab, thiết bị cần đang online và device-side SDK đã đăng ký handler `captureDiagnostics`.

```bash
az iot hub invoke-device-method \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --method-name "captureDiagnostics" \
  --method-payload '{"commandId":"cmd-lab-117","includeSensors":true}' \
  --output json
```

Tham số thời gian chờ invocation, cách biểu diễn method payload và service error được CLI/extension hỗ trợ theo phiên bản. Kiểm tra `az iot hub invoke-device-method --help` khi cần cấu hình timeout. Lệnh trả JSON có thể gồm status/payload do handler trả.

### 15.1. Điều gì xảy ra nếu thiết bị offline?

Direct method không tự được queue. Cloud sẽ thấy lỗi/timeout khi thiết bị không reachable trong deadline; phải ghi event **method invocation unsuccessful**, không tự đánh dấu thiết bị “đã từ chối” vì handler chưa chắc nhận được gì.

### 15.2. Không gọi method “reboot” để thử kết nối trên production

Một số ví dụ IoT dùng `reboot` vì dễ quan sát. Nhưng reboot hàng loạt thiết bị hoặc actuator thật có thể ngắt dịch vụ vật lý. Ở lab, ưu tiên phương thức **`getStatus`** hay **`captureDiagnostics`** không gây tác động nguy hiểm, dùng thiết bị mô phỏng.

### 15.3. Phân biệt response status với CLI exit code

`az` có thể thoát thành công vì invocation API trả về một **method response** do thiết bị cung cấp, nhưng payload status ứng dụng là `400` hoặc `500`. Pipeline phải kiểm tra **cả command execution/transport outcome và status nghiệp vụ**; không chỉ nhìn process exit code.

## 16. Azure CLI: gửi cloud-to-device message

Với CLI IoT extension có nhóm lệnh `az iot device c2d-message`:

```bash
az iot device c2d-message send \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --data '{"messageId":"notice-lab-042","type":"maintenanceNotice"}'
```

**Cú pháp là mẫu minh họa, phải xác nhận với `az iot device c2d-message send --help` trong phiên bản đang cài.** Cách thiết lập TTL, acknowledgment và message properties cũng phải theo flags/SDK hiện hành.

### 16.1. Thử khi thiết bị đang offline

Trong **lab**:

1. Đảm bảo device identity và hub tier hỗ trợ C2D.
2. Ngắt kết nối device simulator theo cách an toàn.
3. Gửi message có TTL được hỗ trợ và đủ dài để đợi lần reconnect trong lab.
4. Kết nối lại device trước khi TTL hết.
5. Đọc device logs để xác nhận message được nhận/settled.
6. Nếu cần business confirmation, kiểm tra **D2C acknowledgment** cùng message ID.
7. Thử lại với offline dài hơn TTL để quan sát expiration/không nhận được.

Không chạy test này trên thiết bị vận hành thực tế mà không có phê duyệt; ngắt kết nối có thể ảnh hưởng cảnh báo và an toàn.

### 16.2. Lưu trạng thái message khi cloud cần tính tin cậy cao

Ví dụ một C2D notice cần được hiển thị trước ngày mai: IoT Hub queue TTL chỉ là một phần. Application workflow nên lưu `noticeId`, `deviceId`, `deadline`, `deliveryAttempt`, `businessAckAt` và lý do thất bại vào database. Nếu hết hạn, báo `expired` để operator xử lý, không loop gửi mãi.

## 17. Device-side Java: chọn SDK và quản lý lifecycle

Với Java, IoT Hub SDK thường được phân thành:

- **Device SDK:** chạy trên thiết bị/gateway, quản lý kết nối, device twin callbacks, direct method handlers và C2D message handlers.
- **Service SDK:** chạy ở backend/cloud, cập nhật twins, invoke direct methods, gửi C2D và quản lý registry/twin query.

Trong nhiều hệ thống còn dùng các Java packages/libraries thuộc **Azure IoT SDK for Java** như `com.microsoft.azure.sdk.iot: iot-device-client` và `iot-service-client` (tọa độ/cấu trúc chính xác tùy release). Tên API, dependency, quyền, support lifecycle và transport behaviors cần được **đối chiếu tài liệu/release notes của phiên bản được chọn**. Ví dụ tiếp theo ưu tiên minh họa **vòng đời ứng dụng và contract** thay vì giả vờ rằng mọi SDK version có cùng method signatures.

### 17.1. Vòng đời một device process

```text
Device boot
   |
   v
Load device identity, TLS trust, secure local config
   |
   v
Open IoT Hub connection (MQTT/AMQP theo SDK)
   |
   +--> Subscribe desired property updates
   +--> Register direct method handlers
   +--> Register C2D message handler
   |
   v
GET full device twin / reconcile desired
   |
   v
Run telemetry + command processing loop
   |
   +--> Persist local command journal
   +--> Apply safety checks
   +--> Update reported state / send D2C business ACK
   |
   v
On disconnect: backoff/reconnect; sync full twin
   |
   v
Graceful shutdown / persist checkpoints
```

### 17.2. Không tạo DeviceClient cho mỗi command

Device-side SDK quản lý TLS connection và subscriptions. Một ứng dụng nên có **connection lifecycle** ổn định theo SDK guidance, không mở một IoT Hub client mỗi lần đọc sensor/nhận method; điều đó gây auth/network overhead, quota pressure và làm mất callback state.

### 17.3. Handler không được block quá lâu

Method callback thường chạy trên luồng/callback executor của client. Nếu handler tải firmware 200 MB và block 20 phút, device có thể timeout direct method và ảnh hưởng các callbacks khác. Hãy **xác nhận nhanh**, lưu local job rồi worker riêng xử lý. Vẫn cần giới hạn queue size, CPU/memory, disk và watchdog.

### 17.4. Vòng đời khi restart

Sau device reboot:

1. Phục hồi identity và local command journal.
2. Kết nối lại hub an toàn.
3. Đăng ký handlers/subscriptions theo SDK.
4. **GET full twin** và xử lý desired version hiện tại.
5. Ghi reported state nếu state đã thay sau reboot.
6. Dedup messages và reconcile long-running commands từ local durable state.

Không giả định callbacks xảy ra theo đúng thứ tự từ trước khi reboot. Tránh áp lại command “một lần” chỉ vì nó còn là key desired.

## 18. Java: xây handler idempotent độc lập với IoT SDK

Ví dụ dưới đây là **business logic Java thuần**, dùng trong device-side callback của SDK. Mục tiêu là tách logic an toàn khỏi API cụ thể của SDK. Những interfaces minh họa phải được thay bằng implementation thật có persistence và hardware operations theo loại thiết bị.

```java
import java.time.Instant;
import java.util.Map;
import java.util.Objects;

record Command(
    String commandId,
    String action,
    int targetC,
    Instant expiresAtUtc,
    String configRevision
) {}

record Result(int status, String code, String commandId) {}

interface CommandJournal {
    Result findCompleted(String deviceId, String commandId);
    void markStarted(String deviceId, String commandId);
    void markCompleted(String deviceId, Result result);
}

interface TemperatureController {
    void setTargetTemperature(int targetC) throws Exception;
}

public final class DeviceCommandHandler {
    private final String localDeviceId;
    private final CommandJournal journal;
    private final TemperatureController controller;

    public DeviceCommandHandler(String localDeviceId,
                                CommandJournal journal,
                                TemperatureController controller) {
        this.localDeviceId = Objects.requireNonNull(localDeviceId);
        this.journal = Objects.requireNonNull(journal);
        this.controller = Objects.requireNonNull(controller);
    }

    public Result handle(Command command) {
        if (command == null || command.commandId() == null) {
            return new Result(400, "BAD_COMMAND", null);
        }
        if (command.expiresAtUtc() == null
                || Instant.now().isAfter(command.expiresAtUtc())) {
            return new Result(410, "EXPIRED", command.commandId());
        }
        Result prior = journal.findCompleted(
                localDeviceId, command.commandId());
        if (prior != null) return prior; // Dedup request đã hoàn tất.

        if (!"setTargetTemperature".equals(command.action())
                || command.targetC() < 2
                || command.targetC() > 8) {
            return new Result(400, "INVALID_OR_UNSAFE", command.commandId());
        }

        try {
            journal.markStarted(localDeviceId, command.commandId());
            controller.setTargetTemperature(command.targetC());
            Result result = new Result(200, "APPLIED", command.commandId());
            journal.markCompleted(localDeviceId, result);
            return result;
        } catch (Exception ex) {
            // Không mặc định hardware action chưa chạy nếu process bị lỗi.
            return new Result(500, "REQUIRES_RECONCILIATION",
                    command.commandId());
        }
    }
}
```

Đây là **mẫu minh họa**, **chưa production-ready**:

- `CommandJournal` cần có **atomic claim** để hai invocations cùng `commandId` không thực thi song song; `findCompleted` rồi `markStarted` riêng lẻ có race.
- State **STARTED nhưng chưa COMPLETED** sau crash phải được reconcile với phần cứng, không chạy lại mù.
- `TemperatureController` phải có hardware interlocks, permission và state revision checks.
- Clock `Instant.now()` có thể lệch nếu thiết bị offline lâu; cần time sync/expiry tolerance policy.
- Callback phải xác thực identity/authorization theo IoT Hub/device app và không chấp nhận command từ một local untrusted channel.
- Ví dụ dùng `int` degrees cho ngắn; thiết bị thật có calibration/limits/units khác.

### 18.1. Ánh xạ vào IoT SDK

Một device SDK adapter có thể chuyển:

```text
Direct method callback:
  methodName + JSON payload
    -> parse & validate Command
    -> DeviceCommandHandler.handle(...)
    -> serialize {status, code, commandId} as method response

C2D message callback:
  system properties + JSON body
    -> parse & validate Command/Notice
    -> local durable enqueue / dedup
    -> settle transport message theo SDK capabilities
    -> worker executes
    -> send D2C business ACK on completion
```

Chú ý: **transport settlement trước khi persist local work** có thể làm mất công việc nếu process crash; nhưng settlement sau side effect với retry có thể gây duplicate. Cần chọn ranh giới đúng và durable local journal cho workload quan trọng.

### 18.2. Vì sao không copy nguyên callback giữa direct method và C2D?

Direct method cần **return response ngay**, thường chỉ nên chạy tác vụ ngắn; C2D có thể nhận bất đồng bộ và ghi vào local queue. Cùng business handler có thể dùng lại, nhưng **wrapper transport, timeout, settlement, ack và retry khác nhau**.

## 19. Service-side Java: tách nghiệp vụ khỏi IoT Hub SDK

Backend cloud cũng nên tránh nhúng toàn bộ REST/SDK calls vào controller. Một interface nội bộ che sự khác biệt giữa phiên bản SDK, REST và authentication, đồng thời giữ được **business command store** và tests.

### 19.1. Thiết kế port cho ba cơ chế

```java
import java.time.Duration;
import java.util.Map;

record DesiredPatch(Map<String, Object> properties,
                    String configRevision) {}

record TwinView(String deviceId,
                String etag,
                long desiredVersion,
                Map<String, Object> desired,
                Map<String, Object> reported) {}

record InvocationResponse(int deviceStatus, String payloadJson) {}

record QueuedReceipt(String serviceMessageId, String trackingId) {}

interface IoTHubControlPort {
    TwinView readTwin(String deviceId) throws Exception;

    TwinView updateDesired(
            String deviceId, DesiredPatch patch, String expectedEtag)
            throws Exception;

    InvocationResponse invokeMethod(
            String deviceId, String methodName, String requestJson,
            Duration connectionTimeout, Duration responseTimeout)
            throws Exception;

    QueuedReceipt sendC2D(
            String deviceId, String messageId, String messageJson,
            Duration timeToLive)
            throws Exception;
}
```

**Đây là interface do ứng dụng tự định nghĩa**, không phải API có sẵn của Azure IoT Java SDK. Implementation thật phải dùng SDK/REST IoT Hub hỗ trợ của phiên bản đã chọn và xử lý trường hợp ETag conflict, quota, authentication, payload size/TTL.

### 19.2. Java service chọn đúng cơ chế

```java
import java.time.Duration;
import java.util.Map;

public final class FleetCommandService {
    private final IoTHubControlPort hub;

    public FleetCommandService(IoTHubControlPort hub) {
        this.hub = hub;
    }

    public TwinView setSamplingInterval(
            String deviceId, int intervalSeconds) throws Exception {
        if (intervalSeconds < 10 || intervalSeconds > 3600) {
            throw new IllegalArgumentException("Interval out of range");
        }
        TwinView current = hub.readTwin(deviceId);
        return hub.updateDesired(deviceId,
                new DesiredPatch(
                        Map.of("telemetryIntervalSec", intervalSeconds),
                        "config-rev-0049"),
                current.etag());
    }

    public InvocationResponse captureDiagnostics(
            String deviceId, String commandJson) throws Exception {
        return hub.invokeMethod(deviceId, "captureDiagnostics",
                commandJson, Duration.ofSeconds(5),
                Duration.ofSeconds(20));
    }

    public QueuedReceipt sendNotice(
            String deviceId, String messageId, String json) throws Exception {
        return hub.sendC2D(deviceId, messageId, json,
                Duration.ofHours(6));
    }
}
```

Các giá trị `5s`, `20s`, `6h` là **giả định lab**, không phải mặc định hoặc giới hạn bắt buộc IoT Hub. Kiểm tra capabilities/valid ranges của SDK và hub tier trước khi triển khai. Class chưa có authorization, persistent audit, rate limit và retry; không đặt trực tiếp trước Internet như production API.

### 19.3. Không trả HTTP 200 chỉ vì accepted by hub

Nếu backend REST API nhận `POST /devices/fridge-042/commands` rồi gửi C2D thành công, response ứng dụng có thể là:

```json
{
  "commandId": "cmd-117",
  "state": "QUEUED",
  "deviceExecutionComplete": false
}
```

HTTP status trả cho client có thể là `202 Accepted` **theo API design**, không biểu diễn device đã thực thi. Client dùng `GET /commands/cmd-117` hoặc subscription để theo dõi. Command store phải phân biệt **queued, dispatched, acknowledged, succeeded, failed, expired**.

### 19.4. Gửi command có tính bền vững

```text
Operator requests command
           |
           v
Authorize operator and device scope
           |
           v
Insert durable command record (unique commandId)
           |
           v
Dispatch via IoT Hub direct method / C2D / desired patch
           |
           v
Update dispatch attempt / IoT Hub result
           |
           v
Wait for device business ACK or reported convergence
           |
           v
Reconcile, timeout, escalate and audit
```

Việc ghi database và gọi IoT Hub **không tạo một transaction ACID duy nhất**. Nếu crash sau khi gửi nhưng trước khi ghi kết quả, lần dispatch sau có thể trùng: vì vậy cần stable command ID, dedup phía thiết bị và reconciliation. Có thể dùng **transactional outbox** để tách tạo command và dispatcher, nhưng outbox tự nó không tạo exactly-once trên device.

## 20. Device twin convergence: làm sao biết cấu hình đã áp dụng?

Đừng dùng so sánh đơn giản “desired value bằng reported value” khi update liên tục. Nên dùng **configuration revision + version + last applied status**.

### 20.1. Mô hình trạng thái

```text
Cloud config-rev-0049
  desired.version = 29
          |
          v
Device sees desired 29
          |
          v
Device validates and writes local config
          |
          v
Device applies config to actual sensor
          |
          v
Device reported:
  lastAppliedDesiredVersion = 29
  configRevision = "config-rev-0049"
  applyStatus = "succeeded"
          |
          v
Cloud checks actualReportedValue + revision + status
          |
          v
Mark configuration converged
```

**Sai lầm:** cloud update desired thành công rồi ghi `rollout_status=SUCCEEDED` ngay. Đúng hơn là `DESIRED_UPDATED`, sau đó **đợi reported đã xác minh**.

### 20.2. Không lấy reported cũ làm kết quả lần này

Một device có thể report `applyStatus=succeeded` từ revision cũ trong khi desired đã lên revision mới. Cần so **`lastAppliedDesiredVersion` hoặc `configRevision`** với revision hiện tại, đồng thời kiểm tra state mà device tự báo. Không chỉ xem chuỗi `"succeeded"`.

### 20.3. Firmware rollback

Nếu firmware `2.4.0` lỗi trên 5% thiết bị:

1. Dừng rollout waves tiếp theo.
2. Xác định devices đang `DOWNLOADING`/`INSTALLING`/`FAILED`/`SUCCEEDED`.
3. Cập nhật target version/revision mới hoặc rollback action phù hợp firmware capability.
4. Device tự xác minh package signature, hardware compatibility, power level và safe rollback.
5. Theo dõi reported version thực tế và device heartbeat.

Không coi việc sửa desired `targetVersion=2.3.1` là firmware ngay lập tức được rollback; thiết bị có thể offline hoặc không hỗ trợ downgrade an toàn.

## 21. Device identity, authentication và authorization

Luồng IoT có **hai trust boundaries** khác nhau:

- **Device → IoT Hub:** thiết bị xác thực bằng identity riêng, sử dụng cơ chế như **per-device symmetric keys/SAS tokens hoặc X.509 certificates** theo hỗ trợ; không dùng credential backend của toàn hub trên mọi thiết bị.
- **Cloud service → IoT Hub:** dịch vụ vận hành được cấp quyền data-plane bằng **Microsoft Entra ID/RBAC** hoặc phương án service credentials được cho phép, có least privilege.

### 21.1. Sơ đồ tin cậy

```text
Administrator / API client
       |
       | Entra ID + API authorization
       v
Fleet Operations Service (managed identity)
       |
       | IoT Hub data-plane permission
       v
Azure IoT Hub
       |
       | device identity authentication via TLS
       v
Device with individual key or certificate
       |
       | local policy + interlocks
       v
Physical actuator / sensor
```

Cloud service có quyền **update desired** không tự được quyền thay đổi firmware mọi thiết bị khi business policy chưa cho phép. Cần **authorization ở API nghiệp vụ** theo tenant/site/role/operation, không chỉ dựa vào IoT Hub RBAC.

### 21.2. Không nhúng hub-owner key trong firmware

Sử dụng một hub-level shared access policy có toàn quyền cho mọi device là anti-pattern nghiêm trọng: một thiết bị bị chiếm có thể ảnh hưởng toàn fleet. Mỗi device nên có identity/certificate/secret riêng, dễ rotate/revoke, được provisioning qua **Device Provisioning Service (DPS)** khi phù hợp.

### 21.3. RBAC phía cloud

Azure IoT Hub có các data-plane RBAC roles/permissions để đọc registry/twin, quản lý thiết bị và gọi các thao tác được cấp quyền theo tính năng. Một managed identity nên chỉ có **các quyền IoT Hub cần cho workload** tại scope phù hợp; không cấp Subscription Owner vì chỉ cần gửi method hoặc đọc twin.

**Control plane IAM** quản lý resource IoT Hub và **data-plane authorization** gửi command/đọc twins không tự đồng nghĩa. Kiểm tra chính xác role/action được hỗ trợ cho `update twin`, `invoke direct method`, `send C2D` theo SDK và tenant policy.

### 21.4. TLS, CA và credential rotation

- Device dùng TLS và kiểm tra hostname/server CA chain; đừng tắt certificate verification.
- SAS token có thời hạn và phải refresh; clock skew ảnh hưởng token expiry.
- X.509 certificate cần provisioning/revocation/rotation policy và private key protection.
- Khi device bị mất cắp, cần disable/revoke identity và chặn commands mới.
- Device firmware cập nhật trust store/CA theo cách an toàn, không khóa cứng certificate leaf cho cả vòng đời nhiều năm nếu không có kế hoạch rollover.

### 21.5. Commands phải có boundary ở thiết bị

Ngay cả khi một operator đã được cloud ủy quyền, device phải tự kiểm tra **local safety**:

- Nhiệt độ mục tiêu nằm trong ngưỡng được chứng nhận.
- Không mở van khi sensor báo nguy hiểm.
- Không reboot trong khi đang xử lý một chu kỳ quan trọng.
- Không chấp nhận lệnh firmware chưa verify chữ ký hoặc không đúng model.
- Command expiry/revision không cho lệnh cũ ghi đè state mới.

**IoT Hub là một kênh kết nối đáng tin cậy hơn về danh tính, không thay bộ điều khiển an toàn tại thiết bị.**

## 22. Network và hỗ trợ giao thức

Thiết bị IoT có thể dùng MQTT/AMQP và một số cơ chế HTTPS được IoT Hub hỗ trợ cho tình huống riêng. **Không phải cơ chế twin/direct method/C2D có cùng hỗ trợ trên mọi transport.**

### 22.1. MQTT vs AMQP/HTTPS

| Tiêu chí | MQTT | AMQP | HTTPS |
|---|---|---|---|
| IoT device kết nối | Thường phù hợp thiết bị constrained, giữ connection dài | Phù hợp nhiều SDK/gateway/transport | Request/polling, hạn chế tính năng realtime |
| Twin desired subscriptions | Hỗ trợ qua MQTT semantics/SDK | Hỗ trợ qua AMQP semantics/SDK | Không giả định có cùng push callback |
| Direct methods | Hỗ trợ theo client/tier/SDK | Hỗ trợ theo client/tier/SDK | Không giả định thiết bị HTTP-only có handler equivalent |
| C2D message | Có delivery/ack semantics riêng | Có settlement semantics riêng | Polling/ack behavior nếu API hỗ trợ |
| Network | Xem firewall, proxy, TLS, port | Xem firewall, proxy, TLS, port | Hợp mạng chỉ cho HTTPS nhưng khác capabilities |

**Đừng chuyển MQTT sang HTTPS chỉ vì proxy chặn cổng rồi mặc định direct methods vẫn chạy.** Kiểm tra protocol feature support của IoT Hub và device SDK, latency/connection behavior, message settlement và gateway topology.

### 22.2. Outbound connections và firewall

Thiết bị thường cần kết nối **outbound** tới IoT Hub và các endpoints phụ trợ (identity/DPS/time sync/update storage) tùy workflow. Tường lửa doanh nghiệp phải cho phép đúng endpoints/ports theo kiến trúc; không mở inbound Internet tới phần cứng để cloud gọi trực tiếp ngoài IoT Hub.

### 22.3. IoT Edge gateway

Khi thiết bị kết nối qua **Azure IoT Edge** hoặc gateway, cần phân biệt device twin và **module twin**, nested/gateway identities và store-and-forward. Offline behavior của edge hub, local routing, cache/twin synchronization phụ thuộc runtime/architecture, **không mặc định C2D/direct method sẽ được giữ vô hạn hoặc hoàn toàn giống thiết bị kết nối trực tiếp IoT Hub**.

### 22.4. Đồng hồ thiết bị

Device command expiry, SAS tokens, TLS certificates và event timestamps có thể phụ thuộc clock. Thiết bị offline lâu, pin RTC hỏng hoặc sync time sai có thể từ chối token hợp lệ hoặc chấp nhận lệnh hết hạn. Cần cơ chế time sync an toàn, monotonic timers cho deadline ngắn, clock-skew policy và cảnh báo drift.

## 23. IoT Hub quota, throttling và rollout fleet

IoT Hub áp dụng **quotas và rate limits** theo hub tier/units/operation types. Updates twin, invoking methods, gửi C2D, query registry và telemetry ingestion có thể có **hạn mức khác nhau**. Không suy rằng 50.000 thiết bị tương đương 50.000 phương thức gọi đồng thời mà hub phải xử lý không giới hạn.

### 23.1. Rollout theo waves

Ví dụ chia fleet:

```text
Wave A: 1% canary (500 devices)
  -> wait for reported convergence + failure thresholds
Wave B: 9% (4,500 devices)
  -> validate DQ/health/error rate
Wave C: 30% (15,000 devices)
  -> monitor hub throttles and device availability
Wave D: remaining 60% (30,000 devices)
  -> continue only if SLO and safety gate PASS
```

Các tỷ lệ chỉ để minh họa; kế hoạch thật cần phân tán theo site, time zone, model, network carrier, release channel và business risk.

### 23.2. Exponential backoff + jitter

Với lỗi throttling/429 hoặc lỗi mạng tạm thời, service retry có giới hạn:

```text
Attempt 1: send once
Attempt 2: delay ~200–400 ms
Attempt 3: delay ~500–1000 ms
Attempt 4: delay ~1–2 s
Then: park command / escalate, do not loop forever
```

Đây là **hình minh họa**, không phải retry policy bắt buộc của IoT Hub. Tôn trọng retry-after/backoff hints khi có, tránh nhân retry qua SDK + backend + scheduler khiến bão lệnh. **C2D/direct method retries không được tái thực thi command nguy hiểm nếu outcome không rõ.**

### 23.3. Không tăng hub units để sửa bug handler

Nếu 20.000 devices cùng cập nhật reported mỗi 100 ms do firmware bug, có thể gặp throttling và tăng chi phí. Giải pháp phải sửa tần suất/tính chất dữ liệu, chuyển telemetry qua D2C và chỉ report state change quan trọng; tăng tier không thay được một thiết kế dùng twin như streaming bus.

### 23.4. Cost-aware command cadence

Mỗi thao tác qua IoT Hub có thể chịu các giới hạn/định lượng message units theo payload, tier và loại operation. Số lệnh, retry, twin patch, telemetry và storage/processing downstream đều có thể đóng góp vào cost. **Không chốt một mức giá/limit cố định** nếu chưa kiểm tra pricing/quota hiện hành của hub SKU/region.

## 24. Monitoring: theo dõi một command xuyên cloud → device

Một dashboard chỉ hiển thị “IoT Hub request succeeded” sẽ bỏ sót thiết bị offline, lệnh đang chờ, ứng dụng lỗi handler và actuator không đạt trạng thái. Quan sát đủ nên gắn **correlation ID/command ID** xuyên:

```text
Operator / API request
   |
   +-- API authorization / request ID
   |
   v
Command store
   |
   +-- desired update / method invocation / C2D send
   |
   v
IoT Hub resource metrics + diagnostics
   |
   +-- throttling / failures / hub health
   |
   v
Device SDK callback
   |
   +-- receive latency / dedup / local queue
   |
   v
Physical/sensor workflow
   |
   +-- applied state / error / execution duration
   |
   v
Reported property or D2C business ACK
   |
   v
Cloud reconciliation / command status / alert
```

### 24.1. Metric theo tầng

| Tầng | Chỉ số quan trọng | Phát hiện |
|---|---|---|
| **Fleet API** | Command requests, unauthorized, dispatch failures | Cloud API errors/quyền |
| **IoT Hub** | Data-plane operation success/error, throttling, queue/telemetry metrics được hỗ trợ | Hub capacity/quota |
| **Connectivity** | Devices connected/disconnected theo telemetry/sự kiện, reconnect rate | Carrier, gateway hoặc certificate |
| **Twin** | Desired update rate, reported lag, convergence percent | Config rollout kẹt |
| **Direct method** | Invoke latency, device handler response, timeout rate | Offline/busy handler |
| **C2D** | Accepted, expired, delivery feedback, outstanding business ACK | Offline queue/TTL |
| **Device** | Local command queue depth, last applied revision, handler duration, failure code | Device CPU/storage/hardware |
| **Business** | % devices đạt cấu hình mục tiêu, SLA command completion | Tác động nghiệp vụ |

Không có nghĩa IoT Hub tự cung cấp **tất cả** các metrics trên. Những chỉ số như **convergence percent** và **business ACK latency** thường phải tự tính từ twin snapshots, device events và command store.

### 24.2. Phân biệt push event với status snapshot

Device twin `reported` là một snapshot trạng thái cuối; nếu device báo `RUNNING` rồi `FAILED` rồi `RUNNING` trong 2 giây, một query sau đó có thể chỉ thấy **state cuối**. Để audit transitions, device cần gửi **D2C events** có `commandId`, `transition`, `timestamp`; backend lưu theo quy tắc bảo mật/retention.

### 24.3. Một event D2C acknowledgement

```json
{
  "eventType": "commandResult",
  "deviceId": "fridge-042",
  "commandId": "cmd-20261120-117",
  "result": "SUCCEEDED",
  "configRevision": "config-rev-0049",
  "deviceEventTimeUtc": "2026-11-20T10:00:42Z",
  "actualTargetC": 4.0
}
```

Backend cần xác minh **device identity gắn với event nguồn đáng tin cậy** và so với command đang chờ. Trường `deviceId` trong payload **không tự là bằng chứng xác thực**; không tin một thiết bị A khai trong JSON mình là thiết bị B. D2C có thể trùng hoặc trễ, vì vậy ack processor phải idempotent và so revision/order.

### 24.4. Độ tươi của reported

Một device có reported `temperatureTargetC=4.0` từ hai tuần trước nhưng hiện offline không được coi là “đang vận hành bình thường”. Status service nên kết hợp:

- Last successful reported revision.
- Last business ACK/telemetry timestamp được xác minh.
- Connection health/freshness theo transport.
- Device heartbeat và các tín hiệu lỗi.
- Mức thời gian offline chấp nhận được cho loại thiết bị.

Tránh dùng một flag `isConnected` như quyền chứng thực rằng phần cứng đang an toàn.

## 25. Azure Monitor, Metrics và diagnostic settings

**Azure Monitor** có thể theo dõi tài nguyên IoT Hub qua platform metrics, alert rules và diagnostic settings gửi dữ liệu đến Log Analytics/Storage/Event Hubs tùy khả năng. **Tên metric, category, dimensions, retention và giá có thể thay đổi theo SKU/tính năng**, nên cần khám phá từ resource thay vì đoán tên.

### 25.1. Azure Portal

1. Mở **đúng IoT Hub** trong Azure Portal và xác minh subscription/resource group/tier.
2. Chọn **Monitoring → Metrics**, xem những metric definitions hiện có.
3. Chọn thời gian và aggregation phù hợp (Sum/Count/Max/Average theo metric).
4. Theo dõi lỗi/auth/throttling, D2C/C2D/twin/method operations theo những tín hiệu được cung cấp.
5. Bật **Diagnostic settings** cần thiết và xác minh logs thực sự vào workspace/Storage/Event Hubs.
6. Tạo alerts với owner/action group và runbook.
7. Ghép platform metrics với **device application telemetry** và command store.

**Không có IoT Hub platform metric cho business “đã mở van thành công” trừ khi ứng dụng tự gửi xác nhận đáng tin cậy.**

### 25.2. Azure CLI: khám phá metric definitions

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

IOTHUB_RESOURCE_ID="<full-IoT-Hub-Azure-resource-id>"

az monitor metrics list-definitions \
  --resource "$IOTHUB_RESOURCE_ID" \
  --output table
```

Sau khi chọn tên metric **thực sự xuất hiện**:

```bash
METRIC_NAME="<metric-name-from-definition>"

az monitor metrics list \
  --resource "$IOTHUB_RESOURCE_ID" \
  --metric "$METRIC_NAME" \
  --output json
```

Khi cần time grain hoặc metric namespace cụ thể, kiểm tra những values được resource/CLI cho phép; không mặc định mọi metric đều hỗ trợ một phút hoặc cùng dimensions.

### 25.3. Diagnostic settings

```bash
az monitor diagnostic-settings list \
  --resource "$IOTHUB_RESOURCE_ID" \
  --output json
```

Danh sách returned có thể rỗng nếu chưa cấu hình; điều đó không tự chứng minh hub không có platform metrics. Để tìm các diagnostic categories được hỗ trợ, dùng Azure Portal/CLI phù hợp resource. Khi cấu hình export:

- Lựa chọn Log Analytics workspace/Storage/Event Hubs đúng vùng và quyền.
- Giới hạn categories cần thiết, tránh logs quá mức.
- Kiểm soát PII trong payloads/diagnostics và retention.
- Thử một hành động lab có correlation ID rồi xác minh ingestion.

### 25.4. KQL minh họa cho command audit logs

Giả sử tổ chức đã tạo custom table **`IoTCommandAudit_CL`** và gửi các records phù hợp (tên cột **chỉ là ví dụ**):

```kusto
IoTCommandAudit_CL
| where TimeGenerated > ago(24h)
| summarize
    Requested=count(),
    Succeeded=countif(Result_s == "SUCCEEDED"),
    Failed=countif(Result_s == "FAILED"),
    Unknown=countif(Result_s == "UNKNOWN_OUTCOME")
    by Mechanism_s
| order by Failed desc
```

**Bảng `IoTCommandAudit_CL` không được IoT Hub tạo sẵn**. Nếu KQL báo bảng/cột không tồn tại, kiểm tra data collection rules/ingestion pipeline, schema và workspace thay vì đổi tên cột theo phỏng đoán.

### 25.5. KQL phân tích thiết bị không hội tụ

Trong một custom table chứa **snapshot reconciliation**:

```kusto
IoTFleetConvergence_CL
| where TimeGenerated > ago(2h)
| where DesiredRevision_s != ReportedRevision_s
| summarize NotConverged=dcount(DeviceId_s)
    by Site_s, Model_s
| order by NotConverged desc
```

Đây là ví dụ minh họa **cần pipeline tạo snapshot và cột trước**; không tự truy vấn IoT Hub twin registry qua KQL. Với hàng triệu thiết bị, thiết kế tần suất snapshot/rate limit để không query IoT Hub quá dày chỉ nhằm xây dashboard.

### 25.6. Alert có ích

Một số tín hiệu:

- Rate direct method timeout tăng đột ngột sau firmware release.
- % reported convergence dưới ngưỡng trong một rollout wave.
- C2D messages hết hạn hoặc **business acknowledgments** trễ.
- Hub throttling tăng, 401/403 auth failures sau key rotation.
- Tỷ lệ thiết bị mất heartbeat tăng theo model/site/carrier.
- Device local command queue backlog cao, pin yếu hoặc disk đầy.
- Lỗi handler/firmware install nhiều hơn canary threshold.

Đặt threshold theo **traffic, cohort size, expected offline windows và SLO**, không đặt “offline devices > 0” cho fleet vốn có thiết bị bảo trì/offline theo lịch.

## 26. Quan sát security và chống giả mạo ACK

Không nên ghi raw twin, payload C2D hoặc method parameters có PII/secrets vào tất cả logs. Một structured audit record có thể gồm:

```json
{
  "commandId": "cmd-20261120-117",
  "deviceId": "fridge-042",
  "site": "hcm-warehouse-02",
  "operation": "setTargetTemperature",
  "mechanism": "directMethod",
  "dispatchAttempt": 1,
  "dispatchResult": "METHOD_RESPONSE_202",
  "businessStatus": "RUNNING",
  "desiredRevision": "config-rev-0049",
  "traceId": "trace-d3a1",
  "observedAtUtc": "2026-11-20T10:00:04Z"
}
```

### 26.1. Phân quyền xem audit

Một operator site A có thể cần xem kết quả của fridge thuộc site A, nhưng không có quyền xem certificates, registry keys hoặc dữ liệu site B. Data lake/log workspace phải có **authorization và data classification**; không chỉ API production mới cần bảo mật.

### 26.2. Correlation ID không phải credential

`commandId` và `traceId` giúp ghép logs, nhưng chúng **không** tự xác thực người gửi. Nếu cloud nhận D2C ACK, phải kiểm tra connection identity, trusted IoT Hub metadata/ingestion context và device authorization. Không để một actor gửi HTTP request `POST /commands/cmd-117/ack` rồi tự ghi `SUCCEEDED` nếu chưa xác thực.

### 26.3. Logs khi lỗi authentication

Nên ghi **mã lỗi, device ID đã giảm nhạy cảm, identity/certificate reference không bí mật và thời điểm**; không log full SAS token, hub connection string, X.509 private key hoặc toàn bộ TLS secret. Sau rotation, kiểm tra chính xác những thiết bị bị ảnh hưởng thay vì tắt authentication toàn hub.

## 27. Runbook 1: desired không được áp dụng

**Tình huống:** cloud đã đặt desired `telemetryIntervalSec=60` cho 500 devices nhưng sau 30 phút có 120 thiết bị vẫn reported `30`.

### 27.1. Điều tra theo thứ tự

1. Xác minh cloud update desired đã thành công trên đúng **IoT Hub/device IDs**.
2. So `desired.$version` với `lastAppliedDesiredVersion`/`configRevision` của reported.
3. Phân nhóm 120 devices theo **offline, firmware version, site, carrier, model**.
4. Kiểm tra device handler có subscribe desired updates và **GET full twin sau reconnect** không.
5. Xem device logs: parse error, range validation, failed local storage, sensor busy.
6. Kiểm tra IoT Hub throttles, network/TLS/DPS/auth errors.
7. Đối chiếu update timestamps và known stale reported state.
8. Với device online, thử controlled diagnostic method **không nguy hiểm** nếu cần.
9. Sửa firmware/config, canary trên số lượng nhỏ và quan sát convergence.
10. Chỉ đánh dấu thành công khi reported khớp desired revision và actual state.

### 27.2. Không làm

- Không gửi 500 desired patches liên tục mỗi 2 giây.
- Không ép thiết bị report `60` trước khi cấu hình thực sự áp dụng.
- Không reset toàn bộ IoT Hub hoặc rotate keys vì một nhóm model lỗi parse.
- Không áp dụng command vượt hardware safety limits.

### 27.3. Root causes có thể

| Dấu hiệu | Nguyên nhân khả dĩ |
|---|---|
| Desired version mới, reported cũ, device offline | Chưa reconnect/chưa đồng bộ |
| Device online nhưng reported error | Validation/hardware/firmware lỗi |
| Chỉ firmware cũ lỗi | Không hiểu schema desired mới |
| Reported same value nhưng revision cũ | Stale success, chưa áp dụng rollout mới |
| Update denied | Cloud RBAC/identity hoặc hub/quota lỗi |

## 28. Runbook 2: direct method timeout hàng loạt

**Tình huống:** dashboard operations báo 35% `captureDiagnostics` invocations timeout.

### 28.1. Phân biệt bốn nhóm lỗi

1. **Device offline/unreachable:** không có connection/handler reachable.
2. **Device busy:** handler callback thread bị block, CPU/storage/pin yếu.
3. **Network instability:** carrier/gateway/IoT Hub connection reset, packet loss.
4. **Cloud throttling/config:** hub tier/quota, credentials, sai method name hoặc deadline quá ngắn.

### 28.2. Điều tra

1. Xác định timeout theo **device model/site/firmware/time window**.
2. Xem error codes từ IoT Hub invocation, không chỉ HTTP status cloud API.
3. Kiểm tra connectivity freshness/heartbeat và connection errors.
4. Đánh giá timeout budget: connection wait vs handler response.
5. Xem device CPU, disk, callback executor/thread starvation.
6. Kiểm tra method contract, payload schema và code paths trả response.
7. Giảm fleet fan-out, retry có jitter cho operations idempotent.
8. Với unknown outcome, **reconcile command ID** trước khi thử lại.
9. Canaries sau fix; tiếp tục rollout có kiểm soát.

### 28.3. Không nâng mọi timeout lên rất lớn

Nếu 10.000 invocation threads cùng chờ 2 phút, backend có thể cạn threads/connections và gây outage dù IoT Hub vẫn khỏe. Đặt **bounded concurrency** và trả accepted + job tracking cho tác vụ dài.

## 29. Runbook 3: C2D đã accepted nhưng không có ACK

**Tình huống:** service gửi maintenance notices cho 800 thiết bị. IoT Hub chấp nhận message, nhưng 200 device không có business acknowledgment sau 4 giờ.

### 29.1. Quy trình

1. Truy xuất command/message store: `deviceId`, `messageId`, TTL, queued/feedback/result.
2. Phân loại device offline vs online; so với **last heartbeat**.
3. Kiểm tra C2D queue/feedback khi service hỗ trợ và đã cấu hình.
4. Xem device callback có nhận/settle message hay không.
5. Nếu message expired, chuyển business state sang `EXPIRED`; không tuyên bố đã xử lý.
6. Nếu device đã nhận nhưng không ACK, kiểm tra local queue/logic xử lý, D2C route/ingestion lag.
7. Dedup theo `messageId` trước khi resend; kiểm tra command có còn hợp lệ.
8. Với action quan trọng, đối chiếu **actual device state** hoặc reported.
9. Bổ sung alert theo cohort/site/offline age và cân nhắc alternate channel nếu business cho phép.

### 29.2. Không đánh đồng feedback và business success

Ngay cả khi hub delivery feedback là positive, đó chưa chắc là maintenance notice đã hiển thị hoặc actuator đã thay đổi trạng thái. Phải thiết kế ACK riêng với `messageId`, timestamp, status và device identity đáng tin cậy.

### 29.3. Tránh resend không giới hạn

Nếu device offline hơn một tuần, gửi lại 1000 lần không tăng xác suất thiết bị nhận trong lúc offline mà làm tăng quota/cost. Một workflow tốt giữ **deadline, maxAttempts, nextRetryAt**, phát cảnh báo và cho operator xử lý. Khi device online lâu sau đó, kiểm tra **command đã expired** trước khi thực thi.

## 30. Tính sẵn sàng, offline-first và xử lý tại biên

**IoT device** thường phải hoạt động với mạng chập chờn. Vì thế hệ thống cần phân biệt:

- **Local control plane:** state, interlocks và safety logic phải hoạt động khi cloud mất kết nối.
- **Cloud desired configuration:** cloud đề xuất mục tiêu; device hội tụ khi kết nối.
- **Short-lived command delivery:** direct method hoặc C2D trong thời hạn.
- **Durable business workflow:** server/database giữ command history và reconciliation.

### 30.1. Offline state machine của device

```text
BOOT
  |
  v
LOAD_LOCAL_CONFIG
  |
  v
CONNECTING ----(timeout)----> OFFLINE_MODE
  |                               |
  | connected                     | run local safe operation
  v                               | queue essential local events
REGISTER_CALLBACKS                |
  |                               |
  v                               |
FETCH_FULL_TWIN <------ reconnect-+
  |
  v
RECONCILE_DESIRED + LOCAL_COMMAND_JOURNAL
  |
  v
ONLINE_OPERATION
  |
  +----(network lost)----> OFFLINE_MODE
```

Trong `OFFLINE_MODE`, thiết bị không được chỉ vì không còn cloud mà bỏ mọi kiểm soát an toàn. Các **local limits và fallback setpoints** phải được thiết kế/kiểm định cho phần cứng. Khi reconnect, tránh “phát lại mọi command một lần” thiếu idempotency.

### 30.2. Cấu hình desired mới nhất vs lịch sử lệnh

Ví dụ service thay interval từ 10 → 20 → 60 khi device offline. Device chỉ cần **áp dụng 60**, không nhất thiết trải qua 10 và 20. Đây là trường hợp **device twin phù hợp**.

Ngược lại, “đếm 3 lần cửa được mở” là lịch sử sự kiện, không thể thay bằng desired `openCount=3` và hy vọng thiết bị thực hiện đúng ba lần. Các sự kiện độc lập cần **durable event/command processing**, idempotency và audit.

### 30.3. Edge gateway và local persistence

Với gateway/IoT Edge, có thể cần lưu local work queue hoặc telemetry khi upstream unavailable, nhưng:

- Storage trên gateway có thể đầy hoặc hỏng.
- Local cache chưa chắc có cùng semantics như IoT Hub C2D queue/twin.
- Đồng bộ lại khi online có thể gây burst.
- Module identity, module twin và device twin có phạm vi khác.
- Software update trên gateway có thể khởi động lại callbacks và local processes.

Kiểm thử **power loss, storage full, corrupted checkpoint, certificate expiration và time drift** như những failure modes bình thường của edge systems.

## 31. Tối ưu độ trễ, khả năng mở rộng và chi phí

### 31.1. Quy trình nào cần real-time?

| Yêu cầu | Cơ chế ưu tiên | Chi phí vận hành cần cân nhắc |
|---|---|---|
| Update interval trên 50k devices | Twin desired/jobs theo waves | Twin updates, reports, quota |
| Diagnostics tức thời trên 100 devices online | Direct method | Connection/response latency, timeout |
| Thông báo không khẩn cấp, có thể offline vài giờ | C2D với TTL | Message units, queue/feedback, eventual ACK |
| Actuator safety-critical | Local controller + validated command | Hardware safety, audit, manual approval |
| Telemetry 1 Hz của hàng nghìn sensors | D2C telemetry/batching theo SLA | IoT Hub throughput, routing, storage/analytics |
| Commands cần lưu vài tuần | Durable command store + phù hợp IoT delivery | Database/Service Bus, worker compute, alerts |

### 31.2. Tránh cập nhật twin quá thường xuyên

Nếu 50.000 devices gửi reported temperature mỗi 5 giây:

```text
50.000 / 5 = 10.000 reported updates/giây
```

Đây có thể là thiết kế kém cả về quota và chi phí. Reported nên biểu diễn **trạng thái quản lý tương đối ổn định**; số đo thường xuyên nên đi qua D2C telemetry và downstream time-series/analytics system.

### 31.3. Batch và compress có chọn lọc

IoT Hub message/payload có giới hạn size; nếu gói hàng trăm measurements trong một D2C event, có thể giảm overhead nhưng tăng latency và rủi ro mất nhiều samples khi một message fail. Thiết kế batching theo network bandwidth, device RAM, power, downstream retention và SLO. Không gửi raw firmware image qua direct method/C2D payload.

### 31.4. Firmware binary nên đi đâu?

Một mẫu:

```text
IoT Hub desired:
  targetFirmwareVersion
  rolloutId
  opaque download reference / package manifest ID
          |
          v
Device obtains authorized download URL/token via secure workflow
          |
          v
Azure Blob Storage/CDN (firmware binary)
          |
          v
Device verifies signature/hash/model
          |
          v
Install + rollback strategy
          |
          v
Reported firmware state / D2C result
```

Không gửi binary vài chục MB qua device twin hoặc direct method payload. Với signed URL/SAS, giới hạn quyền/path/expiry và tránh lưu URL nhạy cảm trong logs/twin nếu vượt policy. **Hash một mình không chứng minh firmware đến từ nhà phát hành tin cậy**; cần chữ ký đáng tin và secure boot/update chain khi phù hợp.

### 31.5. Hóa đơn theo workload

Những chi phí có thể gồm IoT Hub tier/units/message operations, Device Provisioning Service, Azure Functions/Service Bus, Azure SQL/Cosmos DB command store, Event Hubs/stream processing, Blob firmware storage, Log Analytics, mạng/egress, chứng chỉ và đội vận hành. Mỗi dịch vụ có mô hình tính giá riêng. Dùng **Azure Pricing Calculator và Cost Management** theo SKU/region/ngày thực tế, không tự áp một đơn giá cho tất cả message types.

## 32. Kiểm thử đúng semantics của từng cơ chế

Một happy-path demo online không đủ. Cần **positive/negative/failure tests** ở lab hoặc staging với thiết bị mô phỏng và một số thiết bị thật được cho phép.

### 32.1. Ma trận kiểm thử

| Test | Desired twin | Direct method | C2D message |
|---|---|---|---|
| Device online | Report state hội tụ | Handler response đúng | Nhận/ACK theo protocol |
| Device offline vài phút | Desired vẫn lưu | Invoke fail/timeout theo thiết kế | Message có thể chờ trong TTL |
| Reconnect sau nhiều updates | Áp desired mới nhất | Không replay invocation cũ | Nhận message chưa expired |
| Payload/schema lỗi | Device report apply failed | Device trả validation error | Device reject/quarantine/D2C failure theo contract |
| Duplicate send/update | Idempotent apply by revision | Dedup by commandId | Dedup by messageId |
| Crash giữa execution | Reconcile actual state sau reboot | Unknown outcome + journal | Local journal/settlement plan |
| Throttle/quota | Backoff service updates | Bounded retries | Backoff send, expiry budget |
| Credential hết hạn | Reconnect/sync lại | Invocation errors/repair | Delivery delayed/repaired |
| Hub/network outage | Cached desired local rules | Không thể gọi online | Queue behavior chỉ trong TTL/quota |
| Model cũ không hỗ trợ config mới | Report incompatible/failed | Method error | Validation/quarantine/compat fallback |

### 32.2. Test direct method unknown outcome

Kịch bản:

1. Gửi `setTargetTemperature(commandId=cmd-117, target=4)`.
2. Device áp dụng thành công và ghi local journal.
3. Simulate connection loss trước khi cloud nhận response.
4. Cloud nhận timeout và ghi `UNKNOWN_OUTCOME`.
5. Reconcile trạng thái thiết bị; nếu retry cùng command ID, handler trả kết quả đã lưu.
6. Xác minh actuator **không thực thi lại một side effect không idempotent**.

Đây là bài test logic quan trọng hơn việc chỉ tăng timeout.

### 32.3. Test C2D expiry

1. Device offline trong lab.
2. Gửi message có TTL hợp lệ, ghi `messageId`.
3. Chờ quá TTL rồi reconnect.
4. Xác minh handler không tự xử lý message đã expired trong phạm vi IoT Hub/SDK semantics.
5. Command store chuyển `EXPIRED` theo deadline; operator có thể tạo command mới nếu nghiệp vụ cho phép.

Không suy rằng message vẫn tồn tại chỉ vì cloud log từng ghi `send accepted`.

### 32.4. Test twin overwrite/conflict

1. Hai service đọc cùng twin/ETag.
2. Service A cập nhật firmware desired.
3. Service B cập nhật sampling desired dựa trên bản cũ.
4. Dùng conditional update/merge logic thích hợp.
5. Xác minh không làm mất property đã được cập nhật ở bước 2.

Nếu B bị 412, code phải refresh/merge/retry có giới hạn; không dùng wildcard ETag tùy tiện.

### 32.5. Test reboot/reconnect

Sau khi device nhận desired nhưng chưa reported:

- Tắt nguồn an toàn trong lab.
- Khởi động lại từ local state.
- Đăng ký handlers, GET full twin.
- Đối chiếu desired version/rollout ID.
- Áp config/khôi phục job đúng một lần.
- Gửi reported/ACK chính xác.

Không dùng power-cycle test trên thiết bị y tế/công nghiệp đang vận hành mà chưa có quy trình an toàn.

### 32.6. Load test fleet

Thử waves tăng dần:

```text
100 devices -> 1.000 -> 5.000 -> 20.000 simulated devices

Mỗi wave đo:
  twin update/invoke/C2D operations per minute
  throttling/401/5xx
  method p95 latency and timeout
  C2D delivery/business ACK lag
  desired-to-reported convergence p95
  reconnect rate and connection failures
  cloud worker queue depth and cost
```

Nếu test bằng simulators, chúng có thể không tái hiện được **carrier latency, pin yếu, RTC lỗi và CPU hạn chế** của thiết bị thật. Cần một vòng canary phần cứng trước production rollout.

## 33. Tình huống kiến trúc: kho lạnh thông minh

### 33.1. Hệ thống

Một doanh nghiệp có:

- 8.000 tủ lạnh ở nhiều cửa hàng, kết nối LTE/Wi-Fi, một số offline nhiều giờ.
- Cloud Java service trên App Service/AKS.
- Azure IoT Hub để điều khiển và telemetry.
- Azure SQL Database/Cosmos DB để lưu command history và device metadata.
- Azure Blob Storage để lưu firmware và diagnostic bundles.
- Azure Functions/stream processor xử lý business ACK/telemetry.
- Azure Monitor/Log Analytics cho metrics và alerts.

### 33.2. Nhu cầu thứ nhất: thay sampling interval

Yêu cầu: chuyển thiết bị model mới từ 30s xuống 60s sau một ngày, kể cả device offline.

**Giải pháp:** cập nhật **twin desired** theo rollout waves, gắn `configRevision` và `effectiveAfterUtc`. Device GET full twin sau reconnect, validate firmware compatibility, áp dụng và cập nhật reported revision + actual interval. Không gửi liên tục 8.000 direct methods khi một phần fleet offline.

### 33.3. Nhu cầu thứ hai: chẩn đoán thiết bị

Yêu cầu: operator cần xem sensor status ngay trên dashboard cho **thiết bị đang online**.

**Giải pháp:** direct method `captureDiagnostics` với bounded connection/response timeout. Device trả các thông tin an toàn trong response; nếu cần thu thập log lớn, trả `202` + `diagnosticId`, upload file bằng workflow bảo mật và gửi reported/D2C event hoàn tất.

### 33.4. Nhu cầu thứ ba: thông báo bảo trì

Yêu cầu: một thông điệp ngắn cho device có thể đang offline 2 giờ, không cần response ngay.

**Giải pháp:** C2D message có TTL phù hợp và `noticeId`. Device có handler, lưu và hiển thị notice theo state máy. Cloud theo dõi business ACK qua D2C event, không chỉ send accepted.

### 33.5. Nhu cầu thứ tư: cửa kho lạnh mở trái phép

Yêu cầu: khi cửa mở bất thường, hệ thống phải cảnh báo và giữ thực thi an toàn dù mất mạng.

**Giải pháp:** logic **local detection/actuation** trên thiết bị và D2C alert. Không yêu cầu cloud direct method đến kịp trước khi device đóng relay an toàn. Cloud có thể cập nhật thresholds bằng desired, nhưng local firmware kiểm tra giới hạn hợp lệ.

### 33.6. Phân loại trạng thái và kết quả

| Operation | Cloud biết gì ban đầu? | Khi nào đánh dấu hoàn tất? |
|---|---|---|
| Desired update | Hub chấp nhận trạng thái mong muốn | Reported revision + actual value khớp |
| Direct method diagnostics | Handler trả status/payload nếu trong deadline | Với job ngắn: response; với job dài: final ACK |
| C2D notice | Hub accepted/queued | Device D2C business ACK hoặc reported state |
| Firmware rollout | Desired target được ghi | Signed package installed, reported target/version, health checks |
| Safety alarm | Device gửi telemetry | Backend lưu/hiển thị cảnh báo và local controls vẫn hoạt động |

### 33.7. Khi 30% thiết bị mất LTE

Không retry direct methods hàng nghìn lần. **Desired vẫn chờ hội tụ**; C2D chỉ tồn tại trong TTL; các business commands có SLA lâu hơn nằm trong command store. Khi kết nối trở lại, dùng bounded reconnect, twin sync, command reconciliation và rollout waves để tránh message storm.

### 33.8. Tiêu chí nghiệm thu

- Desired config hội tụ theo revision và được device xác minh.
- Direct method không bị lạm dụng cho tác vụ dài hoặc thiết bị offline.
- C2D expiry/duplicate/reconnect được test.
- Commands có ID ổn định, audit và business ACK đáng tin.
- Lỗi transport không tạo side effects nguy hiểm hoặc thực thi lặp.
- Devices có local safety offline.
- Security principal/keys/certs riêng và RBAC đúng quyền.
- Dashboard phân biệt offline, pending, failed, expired, succeeded.
- Fleet rollout có canary, quota headroom và rollback.

## 34. Bài tập thực hành

### Bài tập A – Chọn cơ chế đúng

Với mỗi yêu cầu sau, chọn **device twin / direct method / C2D / phối hợp** và giải thích:

1. Thay interval 15 → 60 giây cho 10.000 devices, nhiều máy offline vài ngày.
2. Lấy nhanh mức pin của một device đang online, muốn response trong 10 giây.
3. Gửi thông báo bảo trì có hạn dùng 6 giờ, device có thể offline một lúc.
4. Yêu cầu nâng firmware mất 30 phút, cần audit mọi bước.
5. Điều khiển emergency shutdown khi mất kết nối Internet.

**Hướng giải:** (1) twin desired/reported, (2) direct method, (3) C2D + business ACK, (4) desired/short method + durable command store/reported/D2C progress, (5) local hardware safety logic – **không** chỉ dựa vào cloud.

### Bài tập B – Desired/reported divergence

Twin hiển thị:

```json
{
  "desired": {
    "telemetryIntervalSec": 60,
    "$version": 19
  },
  "reported": {
    "telemetryIntervalSec": 30,
    "lastAppliedDesiredVersion": 18,
    "applyStatus": "succeeded"
  }
}
```

**Nhiệm vụ:** tại sao không được ghi rollout thành công? Viết điều kiện hội tụ tối thiểu và xác định ít nhất ba nguyên nhân thiết bị chưa lên revision 19.

**Hướng giải:** reported “succeeded” là của version 18; cần `reported.lastAppliedDesiredVersion=19`, actual value 60 và status succeeded. Có thể offline, callback chưa chạy, firmware lỗi parse/hardware busy.

### Bài tập C – Direct method timed out

Cloud gửi `togglePump(commandId=cmd-8)`; device thực thi nhưng response thất lạc. Cloud nhận timeout.

**Nhiệm vụ:** chứng minh vì sao retry ngay có thể nguy hiểm; thiết kế command ID, local journal, state reconciliation và đề xuất thay bằng operation idempotent hơn.

**Hướng giải:** `toggle` lặp hai lần đảo trạng thái, nên thay bằng `setPumpState(target=OFF, revision=N)` với local safety bounds, dedup và result query.

### Bài tập D – C2D expired

Thiết bị offline 3 ngày, service gửi message có TTL 12 giờ, API trả send accepted.

**Nhiệm vụ:** giải thích vì sao thiết bị không nhận khi quay lại, điều gì phải ghi trong command store và khi nào dùng twin thay C2D.

**Hướng giải:** C2D chỉ lưu tới TTL/quota; chuyển state `EXPIRED` và business follow-up. Cấu hình bền vững nên dùng desired state.

### Bài tập E – ETag conflict

Service A và B cùng đọc twin ETag E11. A patch `desired.firmware.targetVersion`; B replace dữ liệu twin cũ E11.

**Nhiệm vụ:** chọn conditional update, xử lý 412, merge có ownership và tránh wildcard ETag.

**Hướng giải:** B refresh twin mới rồi chỉ patch trường thuộc B, kiểm tra ETag/contract và retry có giới hạn; không ghi đè firmware target của A.

### Bài tập F – SDK adapter bằng Java

Tạo interface `IoTHubControlPort` như phần 19 và fake implementation cho tests. Viết unit tests:

- `setSamplingInterval` từ chối interval = 0 và 9.999.
- `setSamplingInterval` gửi đúng patch.
- `captureDiagnostics` truyền đúng method name và bounded timeout.
- `sendNotice` giữ nguyên message ID và TTL.
- Khi hub throw throttling, business command state chuyển vào retry queue có backoff.

**Hướng giải:** mock adapter để unit test business semantics, integration test thực tế riêng theo SDK/tier và credentials lab.

### Bài tập G – Fleet canary

Một tổ chức cần rollout firmware v2 cho 20.000 thiết bị. 0,5% devices model A có lỗi pin khi update.

**Nhiệm vụ:** thiết kế canary/waves, trạng thái reported, success threshold, pause/rollback và chống thổi bùng retry.

**Hướng giải:** rollout theo model/site, dừng khi critical safety threshold vi phạm, không đánh dấu thành công chỉ từ desired update, dùng signed firmware manifest và local rollback.

### Bài tập H – Monitoring và KQL

Thiết kế dashboard theo:

- `device connectivity freshness`.
- `desired-to-reported convergence`.
- `direct-method timeout rate`.
- `C2D business ack latency/expiry`.
- `IoT Hub throttling/auth failures`.

**Nhiệm vụ:** nêu dữ liệu nào có sẵn từ Azure Monitor theo resource và dữ liệu nào **cần tự instrument**. Soạn alert kèm owner/window/runbook.

**Hướng giải:** tìm metric definitions/diagnostic categories trên hub; business ACK/convergence thường phải từ application command store/device events.

### Bài tập I – Device reset giữa lệnh

Device nhận direct method `setTargetTemperature`, ghi journal STARTED, áp dụng phần cứng, reboot trước khi ghi COMPLETED.

**Nhiệm vụ:** sau reboot làm sao biết có cần chạy lại? Tại sao dedup chỉ dựa `findCompleted` chưa đủ? Thiết kế cách đọc actual hardware state và reconcile.

**Hướng giải:** STARTED là trạng thái không chắc chắn, phải kiểm tra actual setpoint, command revision, durable journal và an toàn; chỉ đánh dấu success hoặc retry nếu có bằng chứng phù hợp.

### Bài tập J – Security threat modeling

Một developer đưa connection string có hub-level owner key vào firmware để gửi device-to-cloud telemetry.

**Nhiệm vụ:** mô tả blast radius; đề xuất device-specific identities, DPS, X.509/SAS rotation, server RBAC và cách giữ keys ngoài logs.

**Hướng giải:** hub owner credential có quyền quá rộng; thay bằng per-device identity/credential và scoped cloud service principal/managed identity.

### Bài tập K – Offline gateway

Một IoT Edge gateway mất Internet 36 giờ nhưng vẫn nhận local sensor events; sau reconnect cần đồng bộ lên Azure.

**Nhiệm vụ:** phân biệt local telemetry store-and-forward với C2D queue và twin desired synchronization; xác định quota/disk/ordering/dedup/failure tests.

**Hướng giải:** cần kiểm chứng đúng IoT Edge runtime/store capabilities, không mặc định cloud-to-device messages được giữ qua gateway vô hạn; đặt local disk retention và replay safeguards.

### Bài tập L – Sizing và chi phí

50.000 devices cần report nhiệt độ 1 lần/giây, báo firmware version mỗi ngày và nhận config thay đổi vài lần/tháng.

**Nhiệm vụ:** chọn D2C telemetry cho số đo, reported properties cho firmware/state, desired cho config; ước tính operations và tác động đến IoT Hub tier/units, downstream Storage, Log Analytics.

**Hướng giải:** 50.000 messages/giây là một workload rất lớn; cần batching, capacity planning và pricing theo chính thức, không cập nhật twin mỗi giây.

## 35. Câu hỏi tự kiểm tra

**1. Device twin dùng để làm gì?** Lưu metadata/tags và trạng thái desired/reported của thiết bị, hỗ trợ đồng bộ configuration state.

**2. Ai có thể ghi desired properties?** Cloud/service phía có quyền IoT Hub phù hợp, không phải device client tự ý sửa desired.

**3. Ai ghi reported properties?** Device client được xác thực; cloud đọc để theo dõi trạng thái thiết bị.

**4. Thiết bị có đọc được tags trực tiếp bằng device twin API không?** Không. Tags là metadata phía service.

**5. Desired update accepted có nghĩa thiết bị đã áp dụng?** Không. Phải đợi reported revision/actual state xác nhận.

**6. Khi offline qua nhiều desired changes, thiết bị phải replay mọi delta?** Không; thường đồng bộ **desired latest/full twin** và hội tụ state.

**7. `$version` giúp gì?** Nhận diện thứ tự thay đổi system-managed của desired/reported, phục vụ reconciliation.

**8. ETag dùng để làm gì?** Optimistic concurrency khi update twin, tránh stale writer ghi đè thay đổi mới theo API semantics.

**9. Có nên đưa password vào twin?** Không. Twin là state/metadata được quản lý và có thể được đọc bởi nhiều principals.

**10. Direct method có nhận khi thiết bị offline và chạy lại lúc reconnect không?** Không có durable offline queue của direct method.

**11. Khi direct method timeout, liệu device chắc chưa chạy?** Không; kết quả có thể không chắc chắn nếu response thất lạc.

**12. Vì sao direct method trả 202 có thể hợp lý?** Device đã chấp nhận một job nền; cloud cần final ACK bằng kênh khác.

**13. Direct method nào nguy hiểm khi retry?** Các thao tác không idempotent như `toggle`, `increment`, `openOnce` nếu không có journal/reconciliation.

**14. C2D khác direct method chủ yếu ở đâu?** C2D là thông điệp bất đồng bộ có queue TTL; direct method là request–response online.

**15. C2D accepted có chứng minh thiết bị hiển thị notice?** Không. Cần business acknowledgment từ device.

**16. C2D có lưu message vô thời hạn khi thiết bị offline?** Không; có TTL và quota giới hạn.

**17. MQTT ACK/settlement có tự chứng minh nghiệp vụ hoàn thành?** Không; chỉ mang semantics của transport/client.

**18. C2D duplicate cần xử lý sao?** Stable message/command ID, dedup journal, idempotent handler và revision checks.

**19. IoT Hub service có thay command audit database không?** Không nếu business cần lịch sử/đối soát dài hạn.

**20. Cloud dùng Entra RBAC có đồng nghĩa firmware đã được device authorize?** Không; device còn cần validate payload, revision, safety policies.

**21. Tại sao không nhúng hub owner shared key vào tất cả firmware?** Mất một device có thể lộ quyền toàn hub, blast radius quá lớn.

**22. Device twin có phù hợp lưu nhiệt độ mỗi 100 ms không?** Không; telemetry D2C phù hợp hơn do twin/throttling semantics.

**23. Khi firmware rollout có 5% thiết bị thất bại, hành động đầu tiên?** Pause waves, phân tích cohort và reported trạng thái, sau đó rollback/khắc phục an toàn.

**24. Connected flag có chứng minh actuator đang khỏe?** Không. Cần heartbeat, actual state, error codes và fresh telemetry.

**25. Vì sao need per-device idempotency journal?** Chống repeat sau timeout, reconnect hoặc reboot; bảo vệ side effect.

**26. IoT Edge offline có đồng nghĩa mọi C2D sẽ tự được giữ trên gateway?** Không; kiểm tra runtime/module/tính năng và retention riêng.

**27. Một direct method phản hồi success có bảo đảm binary firmware đã tải xong?** Không nếu method chỉ khởi động background job; cần final state.

**28. Vì sao cần phân quyền operator theo site/tenant ngoài IoT Hub IAM?** Hub data-plane permission không tự biểu diễn mọi business authorization.

**29. KQL `IoTCommandAudit_CL` có được tạo sẵn bởi IoT Hub không?** Không; đây là custom table mẫu do ứng dụng phải ingest.

**30. Tiêu chí rollout thành công quan trọng nhất?** Device đã áp dụng state/job đúng revision và an toàn, có bằng chứng reported/business ACK.

## 36. Checklist đưa luồng cloud-to-device vào production

### 36.1. Cơ chế và contract

- [ ] Đã xác định **IoT Hub tier/SKU** hỗ trợ device twin, direct method và C2D cần dùng; không mặc định mọi Basic/Standard tier có cùng capabilities.
- [ ] Đã tách device twin state, direct method request–response và C2D asynchronous delivery.
- [ ] Desired properties có schema/revision, validation và TTL/expiry policy nếu nghiệp vụ cần.
- [ ] Reported thể hiện **actual applied state** và last applied desired revision.
- [ ] Device GET full twin sau reconnect/reboot, không chỉ dựa vào delta subscriptions.
- [ ] Tags dùng cho grouping/query nhưng không tự là IAM authorization.
- [ ] Có ETag/optimistic concurrency hoặc field ownership để tránh update mất dữ liệu.
- [ ] Direct methods chỉ dùng cho online quick actions hoặc trả accepted cho background job.
- [ ] Direct method timeout/unknown outcome có idempotency/reconciliation.
- [ ] C2D payload có message ID, TTL, contract version và handler phù hợp.
- [ ] Đã phân biệt hub accepted, transport settlement/feedback và business ACK.
- [ ] Không có kỳ vọng C2D lưu commands vô hạn khi device offline.
- [ ] Business command store có unique ID, audit, deadline, retries, status và retention khi cần.

### 36.2. Device Java và an toàn

- [ ] Device SDK/transport versions hỗ trợ callbacks/twin/method/C2D theo hub tier.
- [ ] Device identities riêng, không dùng hub-level owner key trong firmware.
- [ ] TLS certificate/CA hostname validation và credential refresh hoạt động.
- [ ] Callback không block quá lâu, local queue có giới hạn.
- [ ] Handler có schema validation, allowlisted actions, range/safety checks.
- [ ] Non-idempotent commands có durable journal và reconcile sau reboot.
- [ ] Command expiry và clock skew được xử lý, không thực thi lệnh quá cũ.
- [ ] Device local safety hoạt động khi mất cloud/network.
- [ ] Firmware được verify chữ ký/model, có safe rollback khi phù hợp.
- [ ] C2D transport settlement đúng SDK/transport, business ACK riêng.
- [ ] Reported/telemetry không chứa credentials, secrets hay dữ liệu nhạy cảm.

### 36.3. Backend, fleet và bảo mật

- [ ] Backend dùng Entra managed identity/RBAC hoặc service credential được quản lý an toàn.
- [ ] Đã phân biệt Azure control-plane với IoT Hub data-plane quyền.
- [ ] Operator API kiểm tra tenant/site/role/operation trước khi dispatch.
- [ ] Không gửi command vượt hub quota/throttling và không retry storm.
- [ ] Fleet có waves/canary, pause/rollback và convergence checks.
- [ ] Offline cohorts có deadline/recovery plan, không báo thành công giả.
- [ ] Service-side update xử lý conflict/412 theo logic business.
- [ ] Command store, dispatch worker và ACK processor idempotent.
- [ ] IoT Hub có mạng/egress/port/protocol phù hợp và secrets rotation plan.
- [ ] DPS/provisioning, device decommission và revocation có lifecycle rõ.
- [ ] Không bật logs chứa SAS, hub key, private certificate hoặc raw sensitive payload.

### 36.4. Monitoring, testing và chi phí

- [ ] Azure Monitor metrics được khám phá từ đúng IoT Hub resource/tier.
- [ ] Diagnostics, workspace ingestion và log schema đã được thử thực tế.
- [ ] Dashboard có twin convergence, method timeout, C2D business ACK/expiry, reconnect, hub throttling.
- [ ] Các alerts có owner, threshold, evaluation window, action group, runbook.
- [ ] Đã thử device online/offline/reconnect, TTL expiry, method timeout và duplicate messages.
- [ ] Đã thử crash giữa side effect và ACK, full twin resync, ETag conflict.
- [ ] Đã thử credential expiry/rotation, clock drift, firmware schema incompatibility.
- [ ] Đã load-test rollout theo waves trước khi cập nhật fleet.
- [ ] Đã xác định chi phí IoT Hub tier, operations, downstream processing, Storage và monitoring.
- [ ] Không sử dụng thao tác điều khiển phần cứng nguy hiểm trong lab/staging không có phê duyệt an toàn.

## 37. Kết luận

**Device twin, direct method và cloud-to-device message** giải quyết ba nhu cầu khác nhau trong Azure IoT Hub. **Device twin** biểu diễn trạng thái mong muốn và trạng thái được thiết bị báo cáo, hữu ích để đồng bộ cấu hình kể cả khi thiết bị offline; **direct method** phù hợp với hành động ngắn cần response khi thiết bị đang reachable; **C2D message** là kênh bất đồng bộ có hàng đợi và TTL cho thông báo/lệnh được thiết kế phù hợp. Không cơ chế nào tự bảo đảm mọi side effect được thực hiện exactly once, không mất dữ liệu và có audit đầy đủ.

Khi xây dựng hệ thống Java IoT production trên Azure, hãy thiết kế **schema/revision/command ID, ETag concurrency, idempotency journal, business acknowledgment, deadline và local safety**. Phân quyền cloud service và device identity tách bạch, dùng TLS, managed identity/RBAC và bảo vệ secrets. Kết hợp **Azure Monitor, diagnostics, thiết bị báo reported và D2C telemetry**, rollout theo waves và runbook offline/failover để biết không chỉ IoT Hub đã nhận thao tác mà **thiết bị thực sự đã hội tụ về trạng thái an toàn**. Đó là nền tảng cho một hệ thống IoT có thể mở rộng, kiểm toán và vận hành bền vững trên Microsoft Azure.
