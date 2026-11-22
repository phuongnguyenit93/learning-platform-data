# Thực hành tiếp nhận telemetry bằng Event Hubs và xử lý streaming

Hàng nghìn cảm biến gửi nhiệt độ, độ ẩm và trạng thái liên tục có thể tạo ra hàng triệu bản ghi mỗi ngày. Nếu tất cả thiết bị ghi trực tiếp vào một database ứng dụng, database dễ bị quá tải khi thiết bị gửi dồn sau mất mạng; việc phân tích cửa sổ thời gian hoặc để nhiều hệ thống đọc độc lập cũng trở nên khó khăn. **Azure Event Hubs** cung cấp lớp tiếp nhận dòng sự kiện có thể mở rộng, tách tốc độ phát dữ liệu khỏi tốc độ xử lý.

Trong chương **Kiến trúc và thực hành tổng hợp** thuộc lộ trình **CLOUD_PROVIDERS_AZURE**, bài học này kết nối kiến thức về subscription, resource group, Microsoft Entra ID, mạng ảo, tính toán, lưu trữ, dữ liệu, giám sát, bảo mật và kiểm soát chi phí. Chúng ta sẽ xây một pipeline: **Java producer → Event Hubs → Azure Stream Analytics → Blob Storage**, đồng thời thử **Java EventProcessorClient** đọc độc lập và lưu checkpoint.

Một pipeline đáng tin không dừng ở việc gửi thành công một JSON. Nó còn phải xử lý sự kiện đến trễ, gửi trùng, payload sai schema, giới hạn throughput, consumer lag, lỗi kết nối và thời hạn retention; đồng thời có bằng chứng nghiệm thu và cách dọn tài nguyên.

> **Phạm vi:** Các tên tài nguyên, số liệu và chi phí trong bài là giả định hoặc ví dụ lab, không phải giá Azure hoặc quota cố định. SDK, CLI, SKU, quyền và tính năng có thể khác theo region/tier/phiên bản. Lệnh tạo tài nguyên có thể phát sinh phí; chỉ chạy trong subscription được phép. Bài học không khẳng định đã triển khai hoặc kiểm thử trực tiếp trên tài khoản Azure của người học.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Event Hubs, Azure Service Bus, IoT Hub, Stream Analytics và Blob Storage.
2. Giải thích namespace, event hub, partition, partition key, consumer group, offset, sequence number, retention và checkpoint.
3. Thiết kế sự kiện telemetry có event ID, device ID, event time, sequence và schema version.
4. Tạo tài nguyên lab qua Azure CLI và dùng Microsoft Entra ID/RBAC để phân quyền producer/consumer.
5. Viết Java producer gửi event có partition key và hiểu batching, retry, duplicate.
6. Tạo Stream Analytics query tổng hợp nhiệt độ theo cửa sổ một phút.
7. Dùng EventProcessorClient và BlobCheckpointStore, thiết kế sink idempotent.
8. Giám sát ingestion, throttling, lag, late events, lỗi đầu ra và chi phí.
9. Thực hiện kiểm thử end-to-end, recovery và cleanup an toàn.

## 2. Kịch bản capstone: kho lạnh thông minh

Doanh nghiệp có ba khu vực kho, mỗi khu có nhiều thiết bị đo nhiệt độ. Gateway đáng tin cậy nhận dữ liệu từ thiết bị rồi gửi lên Azure. Vận hành cần:

- Tiếp nhận telemetry liên tục, chịu được burst khi thiết bị gửi bù.
- Tính **nhiệt độ trung bình, cực đại và số mẫu của từng thiết bị mỗi phút**.
- Cho phép consumer phân tích đọc cùng dữ liệu nhưng không chặn consumer cảnh báo.
- Đọc lại dữ liệu còn trong retention; lưu raw archive nếu cần truy xuất dài hạn.
- Phát hiện duplicate, invalid payload, mất sequence và thiết bị ngừng gửi.
- Theo dõi throughput, latency, backlog, lỗi, bảo mật và chi phí.

~~~mermaid
flowchart LR
    DEV["Thiết bị / dữ liệu giả lập"] --> GW["Java producer / gateway"]
    GW --> EH["Azure Event Hubs namespace + hub"]
    EH --> ASA["Azure Stream Analytics"]
    ASA --> OUT["Blob Storage: aggregates"]
    EH --> PROC["Java EventProcessorClient"]
    PROC --> SINK["Sink / cảnh báo tùy biến"]
    PROC --> CP["Blob checkpoint store"]
    EH -. "Capture tùy chọn" .-> RAW["Blob/ADLS: raw events"]
    EH -. "Metrics" .-> MON["Azure Monitor"]
    ASA -. "Job metrics" .-> MON
~~~

Hai nhánh là **consumer độc lập** khi có consumer group và tiến độ đọc phù hợp. Stream Analytics tổng hợp theo event time; Java consumer minh họa processing tùy biến và checkpoint. Việc một nhánh đã đọc không làm event biến mất khỏi nhánh còn lại.

Với thiết bị vật lý cần danh tính riêng, provisioning, quản lý thiết bị hay truyền lệnh hai chiều, hãy đánh giá **Azure IoT Hub** hoặc gateway phù hợp. Không phát SAS key cấp namespace cho thiết bị không đáng tin cậy.

## 3. Phân biệt các dịch vụ

| Dịch vụ | Vai trò | Không nên nhầm |
| --- | --- | --- |
| **Event Hubs** | Ingestion stream tốc độ cao, nhiều consumer đọc độc lập | Queue có Complete/Abandon từng message |
| **Service Bus** | Queue/pub-sub cho công việc, settlement và dead-letter theo dịch vụ | Firehose telemetry cần replay theo offset |
| **IoT Hub** | Quản lý kết nối, danh tính và khả năng giao tiếp thiết bị IoT | Công cụ tổng hợp time-window đa mục đích |
| **Stream Analytics** | SQL-like streaming, window, event time và output | Kho lưu trữ event thô vô hạn |
| **Blob Storage / ADLS** | Output, checkpoint, archive | Bộ xử lý event-time tự động |
| **EventProcessorClient** | Consumer tùy biến với checkpoint và partition ownership | Exactly-once transaction cho mọi sink |
| **Azure Monitor** | Metrics, logs, alerts | Bằng chứng business sink đã ghi dữ liệu đúng |

Nếu một đơn hàng cần được worker Complete hoặc chuyển Dead-letter Queue khi lỗi, Service Bus đáng cân nhắc. Với telemetry nhiều consumer và replay trong retention, Event Hubs là lựa chọn hợp lý để khảo sát.

## 4. Namespace, partition, consumer group và retention

### 4.1. Namespace và hub

**Namespace** quản lý các event hub, networking, authentication và năng lực throughput theo tier. **Event hub** là một stream logic nằm trong namespace. Dữ liệu được lưu trong các **partition**, mỗi partition có trình tự sự kiện và metadata riêng.

~~~mermaid
flowchart TB
    P["Producers"] --> H["telemetry-events"]
    H --> A["Partition 0: e1 → e2 → e3"]
    H --> B["Partition 1: e4 → e5"]
    H --> C["Partition 2: e6 → e7"]
    H --> D["Partition 3: e8 → e9"]
    A --> CA["Consumer group ASA"]
    B --> CA
    C --> CA
    D --> CA
    A --> CJ["Consumer group Java"]
    B --> CJ
    C --> CJ
    D --> CJ
~~~

**Thứ tự được xác định trong một partition, không phải toàn bộ hub.** Hai event thuộc hai partitions có thể được xử lý xen kẽ, dù producer sinh ở những thời điểm khác nhau.

### 4.2. Partition key

Producer có thể đặt **partition key = deviceId** để event cùng thiết bị được định tuyến nhất quán theo cơ chế của dịch vụ. Cách này thuận tiện khi phải bảo toàn thứ tự từng thiết bị. Nhưng nếu một deviceId phát nhiều event hơn hẳn, nó có thể tạo **hot partition**. Không giả định mapping deviceId → partition ID bất biến nếu có thay đổi cấu hình, hoặc số partition có thể thay đổi tùy ý ở mọi tier.

### 4.3. Consumer group

**Consumer group** tạo góc nhìn đọc logic độc lập. Job Stream Analytics và ứng dụng Java nên có **consumer group riêng**. Nhiều replica của cùng một processor application có thể dùng chung consumer group và cùng hệ checkpoint store để phối hợp ownership partitions. Consumer group không phải ranh giới bảo mật mạnh để phân tách tenant: phải dùng RBAC, tài nguyên và network phù hợp.

### 4.4. Những loại thời gian và vị trí

| Khái niệm | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| **Sequence number** | Thứ tự event trong cùng partition | So thứ tự giữa hai partition |
| **Offset** | Vị trí trong partition | Xem offset là ID toàn namespace |
| **Enqueued time** | Thời điểm Event Hubs nhận event | Nhầm với thời điểm thiết bị đo |
| **Event time** | Thời điểm phát sinh ở nguồn | Không xử lý clock skew |
| **Processing time** | Thời gian consumer thực sự xử lý | Dùng thay event time trong mọi báo cáo |
| **Checkpoint** | Tiến độ consumer đã xác nhận xử lý | Lưu trước khi dữ liệu được ghi bền vững |
| **Retention** | Khoảng event còn được lưu và replay | Coi Event Hubs là kho archive vô hạn |

Việc consumer đọc xong **không xóa event**. Nếu processor chậm quá thời hạn retention, các event chưa đọc có thể không còn sẵn để replay. Khi cần dữ liệu raw lâu dài, thiết kế **Event Hubs Capture** nếu tier/cấu hình hỗ trợ hoặc một consumer archive sang Blob/ADLS theo chính sách.

## 5. Schema telemetry có thể phát triển

Sự kiện JSON minh họa:

~~~json
{
  "schemaVersion": 1,
  "eventId": "7f02e2ac-0e89-4e8a-88c3-59c584b663d4",
  "deviceId": "device-101",
  "siteId": "warehouse-north",
  "eventTime": "2026-11-20T08:15:30.000Z",
  "temperatureC": 6.4,
  "humidityPercent": 68.2,
  "batteryPercent": 93,
  "sequence": 1051
}
~~~

| Trường | Vai trò | Kiểm tra |
| --- | --- | --- |
| schemaVersion | Phiên bản hợp đồng dữ liệu | Cần có chính sách evolution |
| eventId | ID logic cho một lần đo | Khi retry, giữ nguyên ID |
| deviceId | Định danh và partition key | Không rỗng, không chứa secret |
| siteId | Kho/khu vực | Giá trị hợp lệ |
| eventTime | Timestamp ISO 8601 UTC | Parse được, kiểm tra clock skew |
| temperatureC | Nhiệt độ độ C | Số hữu hạn, đúng đơn vị |
| humidityPercent | Độ ẩm phần trăm | Dải giá trị được phép |
| batteryPercent | Pin còn lại | 0–100 |
| sequence | Số tăng theo device khi nguồn hỗ trợ | Kiểm tra trùng/thiếu mẫu |

**Điều quan trọng nhất khi retry:** cùng phép đo phải giữ nguyên eventId. Nếu mỗi lần gửi lại tạo eventId mới, downstream không thể nhận diện cùng sự kiện logic một cách đáng tin.

### 5.1. Event time khác enqueued time

Thiết bị đo lúc **08:15:30Z**, mất mạng, đến **08:17:00Z** mới gửi; consumer xử lý lúc **08:17:03Z**. Event time là 08:15:30Z; enqueued time khoảng 08:17:00Z; processing time khoảng 08:17:03Z. Báo cáo “nhiệt độ trong phút 08:15” cần dựa trên event time và chính sách late arrival, không đơn giản lấy giờ consumer nhận.

### 5.2. Schema evolution

Thêm field tùy chọn thường dễ tương thích hơn đổi tên/đơn vị field bắt buộc. Đổi từ temperatureC sang Fahrenheit hoặc chuỗi mà không đổi schema có thể phá truy vấn. Cần quản lý version, kiểm thử producer/consumer, validate type, đưa event sai vào quarantine và không đưa PII/token/password không cần thiết vào telemetry.

## 6. Sizing và SLO

| Tham số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Số thiết bị | 10.000 | Nguồn phát |
| Tần suất | 1 event/10 giây/thiết bị | Arrival rate |
| Kích thước | 500 byte/event | Byte rate |
| Burst | 3× trong vài phút | Dư địa khi gửi dồn |
| Partitions | 4 cho lab | Parallelism và phân phối key |
| Retention | 1 ngày cho lab | Replay window |
| Latency objective | Ví dụ p95 kết quả trong 2 phút | Tiêu chí xử lý end-to-end |
| Sink | Blob aggregates và consumer riêng | Khả năng ghi downstream |

Số event/giây:

\[
\lambda=10.000/10=1.000\ \text{events/s}
\]

Lượng payload thô:

\[
1.000\times500=500.000\ \text{byte/s}\approx0{,}5\ \text{MB/s}
\]

Trong một ngày:

\[
1.000\times500\times86.400=43.200.000.000\ \text{byte}
\approx43{,}2\ \text{GB}
\]

Burst 3× tương ứng **3.000 events/s** và khoảng **1,5 MB/s**, chưa tính protocol overhead, retry và biến động kích thước payload. Phải kiểm tra **cả event count rate và byte rate**, cùng partition skew và năng lực sink.

Các tier Event Hubs có mô hình năng lực khác nhau, ví dụ **Throughput Units** ở một số tier, **Processing Units** hoặc capacity chuyên dụng ở tier khác. Quota, khả năng tăng capacity tự động và pricing thay đổi theo tier/region, nên không chọn con số cố định nếu chưa xác minh.

## 7. Chuẩn bị bảo mật và tài nguyên lab

Yêu cầu: subscription được phép tạo Event Hubs, Storage và Stream Analytics; Azure CLI/Cloud Shell; JDK 17+; Maven/Gradle; quyền hạ tầng và data-plane được cấp đúng chính sách.

| Thành phần | Role/cơ chế cần xem xét |
| --- | --- |
| Java producer | Azure Event Hubs Data Sender |
| Java processor | Azure Event Hubs Data Receiver |
| Azure Stream Analytics input | Event Hubs Data Receiver hoặc xác thực được connector hỗ trợ |
| Blob checkpoint | Storage Blob Data Contributor |
| Stream Analytics Blob output | Quyền ghi Blob theo phương thức được hỗ trợ |
| Người tạo hạ tầng | Quyền quản lý resource được phê duyệt |

**Management-plane role không tự cấp data-plane Send/Receive.** Vai trò của developer local cũng không tự áp dụng cho managed identity của Stream Analytics job. Trong production ưu tiên Microsoft Entra ID/managed identity khi connector hỗ trợ, với least privilege. Bảo vệ TLS, network, private endpoint/DNS và không commit SAS connection string có quyền rộng vào mã nguồn.

### 7.1. Tài nguyên sẽ tạo

| Loại | Tên minh họa | Mục đích |
| --- | --- | --- |
| Resource group | rg-telemetry-lab | Cô lập bài học |
| Namespace | eh-telemetry-[suffix] | Event Hubs scope |
| Event hub | telemetry-events | Ingestion |
| Consumer group A | telemetry-asa-cg | Stream Analytics |
| Consumer group B | telemetry-java-cg | Java processor |
| Storage Account | sttelemetry[suffix] | Output/checkpoint |
| Blob container A | telemetry-aggregates | Tổng hợp |
| Blob container B | telemetry-checkpoints | Checkpoint |
| Stream Analytics job | asa-telemetry-lab | Window processing |

Chọn **suffix riêng hợp lệ**, không dùng nguyên ký tự dấu ngoặc. Namespace và Storage Account có quy tắc tên, tính duy nhất riêng; tên Storage Account chỉ gồm chữ thường và số.

## 8. Bước 1 — Tạo Event Hubs và Blob Storage

Ví dụ dành cho **Bash/Azure Cloud Shell**, không phải PowerShell. Thay subscription ID, suffix, kiểm tra quyền và giá trước khi chạy:

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --query "{id:id,name:name,tenant:tenantId}" -o json

RG="rg-telemetry-lab"
LOC="southeastasia"
SUFFIX="<unique-lowercase-alphanumeric>"
NS="eh-telemetry-$SUFFIX"
HUB="telemetry-events"
CG_ASA="telemetry-asa-cg"
CG_JAVA="telemetry-java-cg"
ST="sttelemetry$SUFFIX"
OUT="telemetry-aggregates"
CK="telemetry-checkpoints"

az group create --name "$RG" --location "$LOC"

az eventhubs namespace create \
  --resource-group "$RG" --name "$NS" \
  --location "$LOC" --sku Standard

az eventhubs eventhub create \
  --resource-group "$RG" --namespace-name "$NS" \
  --name "$HUB" --partition-count 4 --message-retention 1

az eventhubs eventhub consumer-group create \
  --resource-group "$RG" --namespace-name "$NS" \
  --eventhub-name "$HUB" --name "$CG_ASA"

az eventhubs eventhub consumer-group create \
  --resource-group "$RG" --namespace-name "$NS" \
  --eventhub-name "$HUB" --name "$CG_JAVA"

az storage account create \
  --resource-group "$RG" --name "$ST" \
  --location "$LOC" --sku Standard_LRS --kind StorageV2

az storage container create \
  --account-name "$ST" --name "$OUT" --auth-mode login

az storage container create \
  --account-name "$ST" --name "$CK" --auth-mode login
~~~

**Điều kiện:** CLI phải có nhóm lệnh eventhubs và tham số của phiên bản đang dùng; nếu retention flag khác phiên bản, xem CLI help thay vì bỏ qua lỗi. Tạo container bằng login yêu cầu quyền Storage data-plane. Standard namespace, Stream Analytics và các tài nguyên có thể phát sinh phí dù producer đã dừng.

Xác minh cấu hình:

~~~bash
az eventhubs namespace show \
  --resource-group "$RG" --name "$NS" \
  --query "{name:name,location:location,sku:sku.name}" -o json

az eventhubs eventhub show \
  --resource-group "$RG" --namespace-name "$NS" --name "$HUB" \
  --query "{name:name,partitionCount:partitionCount}" -o json

az eventhubs eventhub consumer-group list \
  --resource-group "$RG" --namespace-name "$NS" \
  --eventhub-name "$HUB" -o table
~~~

## 9. Bước 2 — Cấp quyền đọc/ghi

Ví dụ dùng người Azure CLI đang đăng nhập, **chỉ khi được ủy quyền tự cấp role trong lab**:

~~~bash
SUB_ID=$(az account show --query id -o tsv)
USER_OID=$(az ad signed-in-user show --query id -o tsv)
EH_SCOPE="/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.EventHub/namespaces/$NS"
ST_SCOPE="/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.Storage/storageAccounts/$ST"

az role assignment create \
  --assignee-object-id "$USER_OID" --assignee-principal-type User \
  --role "Azure Event Hubs Data Sender" --scope "$EH_SCOPE"

az role assignment create \
  --assignee-object-id "$USER_OID" --assignee-principal-type User \
  --role "Azure Event Hubs Data Receiver" --scope "$EH_SCOPE"

az role assignment create \
  --assignee-object-id "$USER_OID" --assignee-principal-type User \
  --role "Storage Blob Data Contributor" --scope "$ST_SCOPE"
~~~

Nếu không có quyền role assignment hoặc đang dùng service principal thay vì user, nhờ quản trị viên cấp quyền theo quy trình. Scope có thể giới hạn hơn nữa ở hub/container. Chờ RBAC propagation nếu vừa cấp role. Stream Analytics job phải được cấu hình credential/identity và quyền **riêng**.

## 10. Bước 3 — Java producer gửi telemetry

Các dependency Maven căn bản, chọn version tương thích của SDK:

~~~text
com.azure:azure-messaging-eventhubs
com.azure:azure-identity
~~~

Biến môi trường theo quy ước bài lab:

~~~bash
export AZURE_EVENTHUBS_FQDN="$NS.servicebus.windows.net"
export AZURE_EVENTHUB_NAME="$HUB"
~~~

**TelemetryProducer.java** (JDK 17+):

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventDataBatch;
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubProducerClient;
import com.azure.messaging.eventhubs.models.CreateBatchOptions;

import java.time.Instant;
import java.util.Locale;
import java.util.UUID;

public class TelemetryProducer {
    public static void main(String[] args) throws InterruptedException {
        String fqdn = requiredEnv("AZURE_EVENTHUBS_FQDN");
        String hub = requiredEnv("AZURE_EVENTHUB_NAME");

        try (EventHubProducerClient producer = new EventHubClientBuilder()
                .credential(
                    fqdn, hub, new DefaultAzureCredentialBuilder().build())
                .buildProducerClient()) {

            String[] devices = {"device-101", "device-202", "device-303"};

            // Lab: 3 thiết bị, mỗi thiết bị 1 event/giây trong 90 giây.
            // Production nên buffer/batch theo throughput và latency mục tiêu.
            for (int second = 0; second < 90; second++) {
                for (int i = 0; i < devices.length; i++) {
                    String deviceId = devices[i];
                    double temp = 4.0 + 2 * i + (second % 10) * 0.1;

                    String json = String.format(Locale.ROOT, """
                        {
                          "schemaVersion": 1,
                          "eventId": "%s",
                          "deviceId": "%s",
                          "siteId": "warehouse-north",
                          "eventTime": "%s",
                          "temperatureC": %.2f,
                          "humidityPercent": 68.0,
                          "batteryPercent": 90,
                          "sequence": %d
                        }
                        """, UUID.randomUUID(), deviceId,
                        Instant.now(), temp, second + 1);

                    EventDataBatch batch = producer.createBatch(
                        new CreateBatchOptions().setPartitionKey(deviceId));

                    if (!batch.tryAdd(new EventData(json))) {
                        throw new IllegalStateException(
                            "Event vượt giới hạn kích thước batch");
                    }

                    producer.send(batch);
                    System.out.printf(
                        "Sent device=%s sequence=%d%n",
                        deviceId, second + 1);
                }
                Thread.sleep(1_000L);
            }
        }
    }

    private static String requiredEnv(String key) {
        String v = System.getenv(key);
        if (v == null || v.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return v;
    }
}
~~~

**Dự kiến 270 sự kiện** nếu mọi lần gửi thành công. Cố ý dùng một event/batch để dễ theo dõi, nhưng cách này không tối ưu khi lưu lượng cao. Việc ba deviceId nằm ở ba partition riêng biệt là **không được bảo đảm**.

### 10.1. Batch, retry và gửi trùng

Ở production, tạo batch với partition key hợp lý; thử thêm từng event bằng tryAdd; khi đầy, gửi batch hiện tại, tạo batch mới và thử lại event. Nếu một event không thể thêm vào batch rỗng thì nó quá lớn với cấu hình hiện tại, cần xử lý riêng/quarantine, không tự chia JSON nếu consumer không hỗ trợ reassembly.

**Send timeout không chứng minh event chưa được dịch vụ nhận.** Retry có thể khiến một event được gửi hơn một lần. Hãy giữ nguyên eventId của cùng phép đo logic, dùng sink idempotent và không chồng nhiều tầng retry vô hạn lên retry policy của SDK.

## 11. Bước 4 — Azure Stream Analytics: tổng hợp một phút

Trong Azure Portal:

1. Tạo **Stream Analytics job** trong resource group lab, chọn region/capacity phù hợp.
2. Tạo **Event Hubs input**, alias **eh-telemetry-input**, chọn hub **telemetry-events**, group **telemetry-asa-cg**, JSON/UTF-8.
3. Tạo **Blob Storage output**, alias **blob-aggregates-output**, container **telemetry-aggregates**, output JSON.
4. Cấu hình identity/credential của job và quyền đọc input/ghi output theo connector được hỗ trợ.
5. Cấu hình policy out-of-order và late-arrival; lưu query rồi start job trước producer.

Truy vấn Stream Analytics:

~~~sql
SELECT
    deviceId,
    siteId,
    System.Timestamp() AS windowEnd,
    COUNT(*) AS sampleCount,
    AVG(temperatureC) AS avgTemperatureC,
    MAX(temperatureC) AS maxTemperatureC
INTO [blob-aggregates-output]
FROM [eh-telemetry-input] TIMESTAMP BY eventTime
GROUP BY
    deviceId,
    siteId,
    TumblingWindow(minute, 1)
~~~

**TIMESTAMP BY eventTime** chọn thời gian đo ở nguồn. **TumblingWindow(minute, 1)** chia các cửa sổ một phút không chồng. **COUNT/AVG/MAX** tạo số mẫu, trung bình và cực đại theo deviceId/siteId. **System.Timestamp()** đưa timestamp logic liên quan đến window lên kết quả.

Một output **minh họa về hình dạng**, không phải kết quả đã chạy:

~~~json
{
  "deviceId": "device-101",
  "siteId": "warehouse-north",
  "windowEnd": "2026-11-20T08:16:00Z",
  "sampleCount": 60,
  "avgTemperatureC": 4.45,
  "maxTemperatureC": 4.9
}
~~~

Số mẫu và thời điểm xuất thực phụ thuộc event-time policy, start position, timestamp sự kiện, việc window đóng và input/output configuration. Nếu chưa thấy Blob ngay sau event đầu tiên, kiểm tra **job Running, Input Events, Output Events, watermark, input alias, query, quyền Blob** thay vì kết luận job hỏng.

## 12. Xử lý event time, watermark và late arrivals

| Hiện tượng | Ví dụ | Rủi ro |
| --- | --- | --- |
| **Late arrival** | Thiết bị offline gửi mẫu của 2 phút trước | Window đã đóng hoặc dữ liệu bị giới hạn |
| **Out-of-order** | Mẫu 08:15:10 tới sau 08:15:20 | Sai thứ tự theo thời gian đo |
| **Duplicate** | Producer retry cùng eventId | COUNT/AVG bị lệch nếu không xử lý |
| **Clock skew** | Đồng hồ nhanh hơn 10 phút | Event bị đưa vào window tương lai |
| **Missing event** | Thiết bị mất mạng và bỏ mẫu | Thiếu sequence nhưng tổng vẫn có thể trông hợp lý |

Azure Stream Analytics cho phép cấu hình chính sách event đến sai thứ tự và đến trễ. Khoảng cho phép rộng giúp nhận nhiều dữ liệu chậm nhưng tăng thời gian chờ kết quả; khoảng quá nhỏ có thể khiến event bị bỏ hoặc timestamp bị điều chỉnh theo chính sách. **Không được khẳng định event rất cũ luôn cập nhật lại window đã xuất.**

| Window | Nguyên tắc | Ví dụ |
| --- | --- | --- |
| Tumbling | Cửa sổ liên tiếp không chồng | Báo cáo mỗi phút |
| Hopping | Cửa sổ trượt theo bước, có thể chồng | Trung bình 5 phút cập nhật mỗi phút |
| Session | Nhóm theo khoảng im lặng | Phiên thiết bị hoạt động |

Không cộng COUNT của những hopping windows để suy ra tổng event duy nhất: cùng một event có thể đóng góp cho nhiều cửa sổ.

## 13. Bước 5 — Java consumer và BlobCheckpointStore

Stream Analytics phù hợp với truy vấn cửa sổ thời gian. Trong một ứng dụng cần quy tắc nghiệp vụ đặc thù, có thể dùng **EventProcessorClient** để đọc raw event. Processor có thể phối hợp ownership các partition trong cùng consumer group và lưu checkpoint vào Blob Storage.

### 13.1. Thư viện và cấu hình

Các tọa độ Maven cần thiết, dùng version tương thích theo bộ Azure SDK của dự án:

~~~text
com.azure:azure-messaging-eventhubs
com.azure:azure-messaging-eventhubs-checkpointstore-blob
com.azure:azure-storage-blob
com.azure:azure-identity
~~~

Biến môi trường dành cho consumer của bài lab:

~~~bash
export AZURE_EVENTHUBS_FQDN="$NS.servicebus.windows.net"
export AZURE_EVENTHUB_NAME="$HUB"
export AZURE_EVENTHUB_CONSUMER_GROUP="$CG_JAVA"
export AZURE_STORAGE_ACCOUNT_NAME="$ST"
export AZURE_CHECKPOINT_CONTAINER="$CK"
~~~

Consumer cần Data Receiver trên Event Hubs và quyền Storage Blob Data Contributor lên container hoặc account phù hợp. Khi triển khai trên Azure, có thể dùng managed identity thay cho người dùng local được Azure CLI xác thực.

### 13.2. TelemetryProcessor.java

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobContainerClientBuilder;

public class TelemetryProcessor {
    public static void main(String[] args) throws InterruptedException {
        String fqdn = requiredEnv("AZURE_EVENTHUBS_FQDN");
        String hub = requiredEnv("AZURE_EVENTHUB_NAME");
        String group = requiredEnv("AZURE_EVENTHUB_CONSUMER_GROUP");
        String account = requiredEnv("AZURE_STORAGE_ACCOUNT_NAME");
        String checkpointContainer =
            requiredEnv("AZURE_CHECKPOINT_CONTAINER");

        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        BlobContainerAsyncClient container =
            new BlobContainerClientBuilder()
                .endpoint("https://" + account + ".blob.core.windows.net")
                .containerName(checkpointContainer)
                .credential(credential)
                .buildAsyncClient();

        EventProcessorClient processor = new EventProcessorClientBuilder()
            .credential(fqdn, hub, credential)
            .consumerGroup(group)
            .checkpointStore(new BlobCheckpointStore(container))
            .processEvent(context -> {
                String partition =
                    context.getPartitionContext().getPartitionId();
                long sequence = context.getEventData().getSequenceNumber();
                String payload =
                    context.getEventData().getBodyAsString();

                // Chỉ demo với dữ liệu synthetic không nhạy cảm.
                System.out.printf(
                    "partition=%s sequence=%d payload=%s%n",
                    partition, sequence, payload);

                // Lab: chỉ minh họa API checkpoint.
                // Production phải commit sink bền vững trước khi checkpoint.
                context.updateCheckpoint();
            })
            .processError(errorContext -> {
                System.err.printf(
                    "Processor error: %s%n",
                    errorContext.getThrowable().getMessage());
            })
            .buildEventProcessorClient();

        processor.start();
        try {
            Thread.sleep(120_000L);
        } finally {
            processor.stop();
        }
    }

    private static String requiredEnv(String key) {
        String v = System.getenv(key);
        if (v == null || v.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return v;
    }
}
~~~

**Quan trọng:** Console output không phải durable sink. Chỉ dùng ví dụ trên để quan sát event giả lập và cách gọi checkpoint. Trong production, xử lý phải theo thứ tự **validate → deduplicate → ghi sink thành công → checkpoint**. Nếu checkpoint trước khi ghi bền vững và process bị crash, event có thể bị bỏ qua trong lần tiếp tục. Ngược lại, nếu ghi sink xong nhưng crash trước checkpoint, một số event có thể được đọc lại.

Checkpoint quá thường xuyên tăng số thao tác Blob Storage; checkpoint quá thưa làm tăng lượng replay sau sự cố. Chọn khoảng theo throughput, thời gian xử lý, khả năng idempotent và mục tiêu recovery.

### 13.3. Tạo consumer group mới không tự bảo đảm đọc lại từ đầu

Vị trí bắt đầu khi chưa có checkpoint phụ thuộc **API và cấu hình start position** của processor/SDK. Không mặc định event sẽ được đọc từ đầu retention. Nếu cần replay, hãy thiết lập vị trí nhận phù hợp hoặc dùng ứng dụng/consumer group/checkpoint store riêng theo đúng khả năng SDK, đảm bảo event vẫn còn trong retention.

Không xóa checkpoint production chỉ để chạy lại demo: làm vậy có thể xử lý trùng toàn bộ khoảng dữ liệu và gây tác dụng phụ nếu sink không idempotent.

## 14. Checkpoint, at-least-once và sink idempotent

Event Hubs lưu stream và EventProcessor đọc theo checkpoint, nhưng hai hành động **ghi database đích** và **lưu checkpoint** thường không nằm trong một giao dịch nguyên tử xuyên hệ thống.

Giả sử consumer:

1. Đọc event có eventId = evt-1001.
2. Ghi thành công vào database đích.
3. Bị crash trước khi cập nhật checkpoint.
4. Khởi động lại và đọc lại evt-1001.
5. Nếu thực hiện INSERT không kiểm tra, nó có thể ghi trùng.

Vì vậy kiến trúc phải dự kiến **duplicate có thể xảy ra** và xây idempotency ở sink.

~~~mermaid
flowchart TD
    A["Nhận event từ partition"] --> B["Validate schema và eventId"]
    B --> C{"Payload hợp lệ?"}
    C -->|"Không"| D["Lưu quarantine bền vững"]
    C -->|"Có"| E{"eventId đã commit?"}
    E -->|"Có"| F["Bỏ qua tác dụng phụ trùng"]
    E -->|"Chưa"| G["Upsert/transaction theo eventId"]
    G --> H{"Commit sink thành công?"}
    H -->|"Không"| I["Không checkpoint, retry/alert"]
    H -->|"Có"| J["Checkpoint theo policy"]
    F --> J
    D --> K{"Quarantine ghi thành công?"}
    K -->|"Có"| J
    K -->|"Không"| I
~~~

### 14.1. Thiết kế sink

- Dùng khóa duy nhất **eventId** hoặc cặp **deviceId + sequence** nếu nguồn thực sự bảo đảm uniqueness.
- Upsert hoặc transactional deduplication trong database/Storage phù hợp.
- Phân biệt cùng eventId/cùng payload với cùng eventId nhưng payload khác: trường hợp sau là lỗi dữ liệu phải điều tra.
- Với aggregate theo cửa sổ, dùng khóa logic như **(deviceId, windowEnd, aggregationVersion)** và cách cập nhật phù hợp, không tự giả định eventId đủ cho mọi kết quả tổng hợp.
- Chỉ xác nhận checkpoint sau durable write/quarantine; khi sink lỗi, giữ khả năng replay.

### 14.2. Quarantine không phải DLQ tự động

**Event Hubs không có per-message Complete, Abandon hay Dead-letter Queue mặc định như Service Bus.** Nếu nhận event sai schema, processor có thể ghi bản ghi quarantine vào Blob hoặc hàng đợi lỗi riêng của ứng dụng:

~~~json
{
  "reason": "INVALID_EVENT_TIME",
  "source": "telemetry-events",
  "partitionId": "2",
  "sequenceNumber": 18842,
  "eventId": "unknown",
  "observedAt": "2026-11-20T08:19:01Z",
  "payloadReference": "quarantine/2026-11-20/18842.json"
}
~~~

Blob quarantine phải được bảo vệ bằng RBAC, retention và mã hóa phù hợp. Không in raw payload nhạy cảm vào log. Chỉ checkpoint event lỗi sau khi việc lưu quarantine đã được xác nhận bền vững theo quy tắc nghiệp vụ.

## 15. Consumer lag và giới hạn parallelism

Một consumer group với **N partition** có tối đa N đơn vị partition độc lập theo mô hình ownership tại cùng thời điểm. Tăng từ 4 lên 20 process trong cùng group khi chỉ có 4 partition không biến thành 20 partitions.

Độ trễ tiêu thụ cần xem theo **từng partition**: sequence/offset mới nhất, sequence đã xử lý hoặc checkpoint, tốc độ xử lý, lỗi và thời gian chậm. Một ước lượng:

\[
\text{Lag events} \approx
\text{latest sequence} - \text{last processed sequence}
\]

Phải so các giá trị **trong cùng một partition**; checkpoint không luôn bằng vị trí event vừa được xử lý gần nhất.

### 15.1. Ví dụ backlog

Producer vào **1.000 events/s**, consumer chỉ xử lý **800 events/s**:

\[
\Delta backlog=1.000-800=200\ \text{events/s}
\]

Sau 10 phút backlog lý thuyết tăng:

\[
200\times600=120.000\ \text{events}
\]

Nếu sau đó producer giảm xuống 700/s, consumer xử lý 900/s, tốc độ giảm tồn là 200/s. Trong điều kiện lý tưởng cần khoảng **600 giây** để giảm hết 120.000 event. Thực tế còn phụ thuộc burst, restart, retry và sink.

Nếu không catch up trước khi event hết retention, consumer có thể không còn đọc được các event đó. Cần cảnh báo lag, tăng capacity có căn cứ hoặc archive raw event ngay từ đầu.

### 15.2. Hot partition, throttling và backpressure

- **Hot partition:** phân phối deviceId/key lệch; xem throughput từng partition và workload skew.
- **Throttling ingress:** capacity namespace/tier không đủ, quota hoặc giới hạn dịch vụ; tăng consumer chưa giải quyết.
- **Throttling sink:** database/Storage không ghi kịp; thêm producer chỉ làm backlog tăng.
- **Backpressure:** giới hạn concurrency/buffer in-process, không để queue RAM phình vô hạn.
- **Retry:** có backoff, jitter và tổng deadline, không chồng nhiều tầng retry vô hạn.

Mức độ sẵn sàng của dữ liệu tùy retention, buffer tại gateway và archive. Một gateway cần bảo toàn dữ liệu khi mất mạng phải có **buffer bền vững có giới hạn/chiến lược overflow rõ**, không chỉ dùng một queue RAM.

## 16. Quan sát bằng Azure Monitor và Application Insights

| Nhóm | Chỉ số cần xem | Mục đích |
| --- | --- | --- |
| Event Hubs ingestion | Incoming Messages/Bytes | Bao nhiêu dữ liệu thực sự đến hub |
| Event Hubs read | Outgoing Messages/Bytes | Có consumer nhận dữ liệu hay không |
| Event Hubs errors | Throttled Requests, server/user errors theo metrics khả dụng | Capacity, networking hoặc auth |
| Stream Analytics | Input Events, Output Events, watermark/latency, input/output errors | Job xử lý có đúng không |
| Java producer | Attempted/sent events, retry, batch size, latency | Phát hiện lỗi SDK/gateway |
| Java consumer | Processed events, duplicates, checkpoint age, lag | Độ trễ, replay, mất tiến độ |
| Blob | Transactions, authorization failures, output growth | Checkpoint/output hoạt động |
| Business | Thiết bị im lặng, missing sequence, nhiệt độ vượt ngưỡng | Đo hiệu quả nghiệp vụ |

Tên metric có thể thay đổi theo tier, loại tài nguyên, version và phạm vi Azure Monitor. **IncomingMessages không đồng nghĩa số giao dịch được sink ghi thành công**: sự kiện có thể lỗi schema, bị duplicate, bị lọc hoặc đợi xử lý.

### 16.1. KQL ví dụ khi đã xuất metrics về Log Analytics

~~~kusto
AzureMetrics
| where TimeGenerated >= ago(1h)
| where MetricName in (
    "IncomingMessages",
    "OutgoingMessages",
    "ThrottledRequests")
| summarize total = sum(Total)
    by MetricName, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Đây là ví dụ theo schema **AzureMetrics**. Metrics trong Azure Monitor **không mặc định luôn được lưu ở Log Analytics**. Cần cấu hình xuất/diagnostic settings phù hợp, xác minh tên metric/column và kiểu aggregation. Nếu workspace không có những bản ghi này, dùng **Metrics explorer** hoặc API hỗ trợ; không kết luận dịch vụ không ghi dữ liệu.

### 16.2. Thiết kế cảnh báo

- Ingestion giảm bất thường so với baseline cùng giờ.
- Throttled requests và lỗi gửi tăng vượt ngưỡng vận hành.
- Stream Analytics job dừng, input/output lỗi hoặc không xuất kết quả đúng kỳ.
- Consumer lag/checkpoint age tăng liên tục.
- Tỷ lệ event lỗi schema/quarantine tăng sau release.
- Thiết bị không gửi event quá thời hạn nghiệp vụ.
- Chi phí Log Analytics, Storage hoặc capacity tăng khác thường.

Không đặt cảnh báo bắt buộc **OutgoingMessages == IncomingMessages mỗi phút**, vì consumer đọc theo nhiều group, replay và aggregate làm số lượng bản ghi ở các lớp khác nhau.

### 16.3. Correlation và telemetry an toàn

Gắn eventId, deviceId theo chính sách, eventTime, partition/sequence để truy vết khi cần. Không đặt mỗi eventId thành một metric label vì cardinality rất cao. Không log raw payload chứa PII, token hay thông tin nhạy cảm; dùng trace/log có retention, sampling và quyền xem phù hợp.

## 17. Bảo mật, network và governance cho production

Với production:

1. Chỉ cấp **Data Sender** cho producer, **Data Receiver** cho consumer, quyền Blob riêng cho checkpoint/output.
2. Dùng managed identity khi dịch vụ hỗ trợ, hạn chế SAS key dùng chung và có kế hoạch rotation.
3. Xác minh TLS, firewall, private endpoints, DNS, outbound access và cấu hình region.
4. Phân loại dữ liệu; không gửi secret, credential hay PII không cần thiết.
5. Xác định retention của Event Hubs, raw archive, output và quarantine **riêng biệt**.
6. Đặt policy/audit cho thay đổi namespace, consumer group, job, RBAC và schema.
7. Theo dõi chi phí mạng/cross-region và vùng dữ liệu; đảm bảo quy định lưu trú nếu có.
8. Kiểm thử backup/DR hoặc multi-region theo RTO/RPO thay vì chỉ dựa vào retention.

**Consumer group không phải ranh giới bảo mật đa tenant.** Nếu cần phân tách dữ liệu khách hàng với quyền truy cập mạnh, đánh giá tách hub/namespace và các nguồn dữ liệu khác theo mô hình bảo mật thực tế.

## 18. Các tình huống lỗi và cách phục hồi

| Sự cố | Hành vi có thể gặp | Hướng bảo vệ |
| --- | --- | --- |
| Gateway mất mạng | Event chưa đến hub | Buffer bền vững, retry/backoff và giới hạn dung lượng |
| Producer send timeout | Không rõ dịch vụ đã nhận event | Giữ eventId, downstream dedup |
| Stream Analytics job dừng | Aggregate không cập nhật | Alert, restart, replay còn retention |
| Consumer crash sau ghi sink | Event đọc lại | Sink idempotent, checkpoint sau commit |
| Consumer lag kéo dài | Event chưa đọc có thể hết retention | Capacity/alert và raw archive |
| JSON sai schema | Parser/query lỗi hoặc event bị bỏ | Validation, quarantine, metrics |
| Hot partition | Một consumer quá tải | Kiểm tra key distribution và partition capacity |
| Storage checkpoint 403 | Processor không lưu tiến độ | Kiểm tra RBAC/network, không báo thành công giả |
| Database sink throttling | Backpressure và lag | Giới hạn concurrency, batch, retry/budget |
| Region gián đoạn | Ingestion/processing gián đoạn | Kiến trúc DR/multi-region riêng, kiểm tra RTO/RPO |

**Event Hubs không tự bảo đảm exactly-once end-to-end** qua producer, stream, processor và database. Mục tiêu đáng tin cậy là retry có giới hạn, dữ liệu có thể replay trong retention, idempotent sink, checkpoint bền vững và đường xử lý lỗi.

### 18.1. Replay có kiểm soát

Khi phát hiện lỗi trong logic tổng hợp:

1. Xác định thời gian bị ảnh hưởng, consumer group và nguồn dữ liệu còn trong retention/archive.
2. Dùng processor/consumer group riêng để không làm thay đổi tiến độ production.
3. Chạy phiên bản logic đã sửa ra **output version mới** hoặc staging.
4. Đối soát số lượng, khóa unique, kết quả window và chênh lệch với báo cáo cũ.
5. Chỉ thay kết quả chính thức khi được phê duyệt và có đường quay lui.

Nếu dữ liệu đã hết retention và không có archive, **không thể tự suy luận vẫn replay được**.

## 19. Tính chi phí toàn pipeline

| Thành phần | Driver chi phí | Biện pháp |
| --- | --- | --- |
| Event Hubs namespace/capacity | Tier, throughput/capacity theo offer | Right-size và cảnh báo throttling |
| Event Hubs retention/Capture | Lưu raw event, capture/Storage theo tier | Retention/lifecycle hợp lý |
| Stream Analytics | Năng lực/job runtime và cấu hình dịch vụ | Dừng job lab khi hoàn tất |
| Blob output/checkpoint | Storage bytes và operations | Batch/checkpoint interval, cleanup |
| Consumer compute | VM/container/App Service/Functions | Scale theo lag và SLO |
| Monitor | Ingestion, retention và tính năng workspace | Không log mỗi payload không cần thiết |
| Network | Egress/cross-region transfer | Thiết kế topology/region phù hợp |

Ví dụ payload **43,2 GB/ngày** không đồng nghĩa hóa đơn sẽ chỉ tính phí lưu 43,2 GB. Pipeline còn có throughput/capacity, processor runtime, output, checkpoint, monitoring và có thể data transfer.

### 19.1. Ví dụ chi phí giả định

| Khoản | Số tiền minh họa |
| --- | ---: |
| Event Hubs capacity | 8,00 USD |
| Stream Analytics runtime | 5,00 USD |
| Blob output/checkpoint | 0,80 USD |
| Monitoring | 0,70 USD |
| Network/phần khác | 0,50 USD |
| **Tổng giả định** | **15,00 USD** |

Đây **không phải giá Azure hoặc ngân sách mặc định**. Hãy dùng Pricing Calculator, giá hợp đồng, cấu hình/tier thực và Cost Management để dự toán. Kiểm tra việc tăng throughput và tài nguyên vẫn chạy khi producer đã dừng.

## 20. Kế hoạch kiểm thử end-to-end

Một capstone tốt cần test matrix với dữ liệu đầu vào, kết quả mong đợi và bằng chứng:

| Test | Điều kiện | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- | --- |
| Ingestion | Producer gửi 270 event | Metrics tăng, gửi không lỗi | Producer log, Event Hubs metrics |
| Partition key | Ba deviceId | Thứ tự mỗi device trong partition theo quy tắc | Partition ID, sequence |
| Aggregation | Gửi qua ranh giới phút | Output theo device/site/window | Blob output, Stream Analytics metrics |
| Invalid JSON | Thiếu/sai eventTime hoặc temperatureC | Có lỗi/loại bỏ/quarantine theo policy | Diagnostics và sink lỗi |
| Duplicate | Gửi lại cùng eventId | Sink không nhân đôi business effect | Unique key/dedup checks |
| Late event | Event time lùi đáng kể | Xử lý theo cấu hình late policy | Watermark/data errors/output |
| Consumer restart | Dừng/start processor | Tiếp tục checkpoint, có thể replay đoạn sau | Checkpoint blobs, sequence |
| Independent consumer | Chạy ASA và Java song song | Hai nhóm đọc độc lập | Consumer group config |
| Throttling | Burst test có guardrail | Không retry vô hạn hoặc cạn RAM | Error metrics, retry/lag |
| Authorization | Producer thiếu Sender | Bị từ chối theo policy | Error và role scope |
| Cleanup | Xóa tài nguyên sau nghiệm thu | Không còn lab ngoài phạm vi | Inventory và Cost Management |

### 20.1. Thử late event

Gửi sự kiện eventTime hiện tại, sau đó gửi eventTime lùi **2 phút**, rồi thử lùi **20 phút** chỉ trong môi trường lab. Quan sát output, data errors và policy out-of-order/late arrival. Ghi chính xác sự kiện bị bỏ, timestamp bị điều chỉnh hay được chấp nhận vào window nào. Không tự coi dữ liệu cũ bị bỏ là lỗi dịch vụ nếu policy yêu cầu như vậy.

### 20.2. Thử restart và duplicate

Cho consumer ghi một batch vào sink, cố tình kết thúc tiến trình trước checkpoint trong môi trường test. Sau restart, kiểm tra có event bị xử lý lại không và xem unique-key/upsert đã ngăn duplicate chưa. Không thực hiện chaos test trên production hoặc thay đổi checkpoint production khi chưa được phê duyệt.

### 20.3. Tiêu chí nghiệm thu

- Producer gửi event hợp lệ và Event Hubs nhận đúng theo metrics đã đối chiếu.
- Stream Analytics tạo output có device/site/window, số mẫu và aggregate hợp lý.
- Consumer Java đọc độc lập theo group; có checkpoint và handling lỗi.
- Event duplicate không tạo tác dụng phụ trùng ở sink bền vững.
- Invalid event được phát hiện/quarantine, không làm pipeline dừng vô hạn.
- Consumer lag, watermark, throttling và output errors có cách giám sát.
- Tính toán throughput, retention, khả năng replay và chi phí được ghi với giả định rõ.
- Quy trình phân quyền và cleanup không ảnh hưởng tài nguyên ngoài lab.

## 21. Dọn tài nguyên sau thực hành

1. Dừng Java producer/processor, **Stop Stream Analytics job**.
2. Lưu bằng chứng nghiệm thu không chứa secret, lưu raw/aggregate nếu cần theo chính sách.
3. Kiểm tra resource group có đúng chỉ tài nguyên lab đã được phép xóa hay không.
4. Xem cost và nguồn phí còn tồn tại (namespace, job, Storage, logs).
5. Chỉ khi chủ sở hữu chấp thuận, xóa các tài nguyên lab và thu hồi role assignment tạm.

Lệnh chỉ để **kiểm tra** trước khi xóa:

~~~bash
az resource list --resource-group "$RG" -o table

# NGUY HIỂM: xóa toàn bộ resource group. Chỉ dùng sau phê duyệt
# và kiểm tra không có tài nguyên dùng chung:
# az group delete --name "$RG" --yes
~~~

Không giả định xóa resource group sẽ kết thúc mọi khoản phí từ commitment hoặc tài nguyên nằm ở phạm vi khác. Ngay cả khi không gửi thêm event, namespace/job vẫn có thể phát sinh chi phí theo mô hình dịch vụ.

## 22. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Producer 401/403 | Credential sai, thiếu Sender, RBAC propagation | Kiểm tra tenant, role, scope, endpoint |
| Producer timeout | DNS, firewall, TLS, network hoặc throttling | SDK diagnostics, FQDN, network rules |
| Stream Analytics không nhận event | Sai hub/group, job chưa chạy, start position | Input config, job status, metrics |
| Job Running nhưng Blob rỗng | Window chưa đóng, output permission/query lỗi | Watermark, Output Events, Blob auth |
| AVG không có giá trị | temperatureC bị gửi thành chuỗi | Schema validation/typing |
| Thiếu event cũ trong aggregate | Late policy hoặc start position | Event time, enqueued time, policy |
| Java checkpoint 403 | Thiếu Storage Blob Data Contributor/network | Checkpoint container, token và RBAC |
| Restart consumer đọc trùng | Checkpoint cũ hơn sink commit | Unique key, idempotent sink |
| Hot partition | Key phân phối lệch | Metrics theo key/partition, cách phân vùng |
| Lag tăng | CPU/sink chậm, throttling hoặc consumer thiếu năng lực | Per-partition lag, sink latency, errors |
| Replay không thấy event | Retention hết, không có raw archive | Kiểm tra retention và Capture |
| Chi phí tăng khi producer đã dừng | Namespace/job/storage/log vẫn hoạt động | Inventory và Cost Management |
| Không thấy metrics trong KQL | Chưa xuất Azure Monitor Metrics vào Logs | Diagnostic settings hoặc Metrics explorer |

Không khắc phục bằng cách bật quyền Owner toàn subscription, đưa SAS keys vào Git hoặc tắt network security production. Tìm chính xác lớp gây lỗi và thực hiện thay đổi tối thiểu có thể thu hồi.

## 23. Bài tập capstone

### Bài A — Kiến trúc và hợp đồng dữ liệu

Vẽ lại sơ đồ Event Hubs → Stream Analytics → Blob và EventProcessorClient → checkpoint/sink. Đánh dấu role Sender/Receiver/Blob Contributor, consumer groups, event time, partition key, dedup key và điểm lưu raw archive. Nêu lý do không sử dụng chung consumer group của hai ứng dụng độc lập.

**Đầu ra:** sơ đồ có data path, security boundary, các loại event và kế hoạch quan sát.

### Bài B — Dựng pipeline

Tạo các tài nguyên bằng CLI, cấu hình Stream Analytics input/output, chạy producer Java, quan sát Event Hubs metrics, xem Blob aggregates, rồi chạy EventProcessorClient. Ghi lại namespace/hub và tên consumer groups (không ghi secret), query, số event, output JSON và trạng thái checkpoint.

**Đầu ra:** bằng chứng có dữ liệu thực của môi trường lab và ghi rõ những mục chưa kiểm chứng.

### Bài C — Capacity

Với **10.000 thiết bị**, mỗi thiết bị gửi một event/10 giây, payload 500 byte:

1. Tính tổng **1.000 events/s**.
2. Tính raw ingress **0,5 MB/s**.
3. Tính raw payload ngày **43,2 GB**.
4. Với burst 3×, tính **3.000 events/s**.
5. Nêu ít nhất bốn giới hạn còn phải kiểm tra: tier event/byte rate, partition skew, retention, sink/consumer throughput, storage/network cost.

**Đầu ra:** bảng sizing có giả định và hạn chế, không phải chỉ một con số Throughput Units.

### Bài D — Duplicate và invalid event

Các sự kiện rút gọn:

~~~json
{"eventId":"evt-1","deviceId":"device-101","eventTime":"2026-11-20T10:00:01Z","temperatureC":5.2}
{"eventId":"evt-1","deviceId":"device-101","eventTime":"2026-11-20T10:00:01Z","temperatureC":5.2}
{"eventId":"evt-3","deviceId":"device-101","eventTime":"not-a-time","temperatureC":"hot"}
~~~

Trả lời: sự kiện nào duplicate, sự kiện nào sai type/time, vì sao cần quarantine trước checkpoint và nếu dùng schema đầy đủ phần 5 thì còn thiếu những trường bắt buộc nào?

**Định hướng:** hai dòng đầu trùng eventId; dòng ba sai eventTime/nhiệt độ; cả ba là mẫu rút gọn chưa có đủ field theo schema đầy đủ. Cần phiên bản schema rút gọn riêng hoặc bổ sung field trước khi cho dữ liệu production.

### Bài E — Crash và checkpoint

Consumer đã ghi 100 event vào database nhưng checkpoint mới ở event thứ 80, rồi crash:

1. Những event nào có thể được đọc lại sau restart?
2. Vì sao database cần unique key/upsert?
3. Nên đặt checkpoint theo mỗi event hay theo batch/chu kỳ nào, và vì sao?
4. Nếu dữ liệu sau checkpoint đã hết retention, làm sao khôi phục?

**Định hướng:** đoạn từ sau checkpoint có thể được replay nếu còn retention; sink phải idempotent; chọn checkpoint theo throughput/chi phí/khả năng chấp nhận replay; dùng raw archive nếu cần khôi phục dữ liệu ngoài retention.

### Bài F — Phân tích vận hành

Chọn ba tình huống: hot partition, ASA output trễ do watermark, và Storage tăng phí vì raw capture. Với mỗi tình huống, ghi metric, giả thuyết, cách xác minh, tác động SLO và phương án thay đổi có rollback.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Event Hubs có xóa event sau khi một consumer đọc không?  
**Đáp án:** Không. Event tồn tại trong retention; các consumer groups có thể đọc độc lập.

**Câu 2.** Vì sao dùng deviceId làm partition key?  
**Đáp án:** Giúp định tuyến nhất quán và hỗ trợ thứ tự trong một partition, nhưng phải xem skew.

**Câu 3.** Event Hubs có thứ tự toàn cục giữa các partition không?  
**Đáp án:** Không. Thứ tự gắn với từng partition.

**Câu 4.** Checkpoint khác retention thế nào?  
**Đáp án:** Checkpoint lưu tiến độ consumer; retention quyết định sự kiện còn đọc lại được bao lâu.

**Câu 5.** Vì sao send timeout có thể gây duplicate?  
**Đáp án:** Dịch vụ có thể đã nhận event trước khi phản hồi bị mất; producer retry.

**Câu 6.** Event time khác enqueued time thế nào?  
**Đáp án:** Event time là lúc nguồn đo; enqueued time là lúc hub nhận.

**Câu 7.** TIMESTAMP BY eventTime trong Stream Analytics dùng để làm gì?  
**Đáp án:** Dùng thời gian nguồn đo để gán cửa sổ xử lý.

**Câu 8.** Sự kiện đến sau 20 phút có chắc cập nhật window đã đóng không?  
**Đáp án:** Không. Phụ thuộc late-arrival/out-of-order policy, watermark và job.

**Câu 9.** Consumer crash sau ghi database nhưng trước checkpoint gây ra điều gì?  
**Đáp án:** Event có thể được đọc lại; sink cần idempotency.

**Câu 10.** Event Hubs có DLQ theo từng event như Service Bus không?  
**Đáp án:** Không. Phải thiết kế quarantine riêng khi cần.

**Câu 11.** Có 4 partitions và 20 consumer instances trong một group, có 20 partition xử lý song song không?  
**Đáp án:** Không. Số partitions giới hạn song song theo partition ownership.

**Câu 12.** 10.000 thiết bị gửi mỗi 10 giây tạo bao nhiêu event/s?  
**Đáp án:** 1.000 event/s, trước burst và retry.

**Câu 13.** Vì sao output Stream Analytics ít record hơn input là bình thường?  
**Đáp án:** Window aggregation gom nhiều raw events thành một bản tổng hợp.

**Câu 14.** Cấp Sender cho người tạo job có tự cấp Receiver cho Stream Analytics không?  
**Đáp án:** Không. Job dùng identity/credential riêng.

**Câu 15.** Muốn replay khi Event Hubs retention đã hết cần gì?  
**Đáp án:** Raw archive đã được thiết kế trước và kế hoạch xử lý lại có kiểm soát.

## 25. Checklist nghiệm thu

- [ ] Có sơ đồ Event Hubs → Stream Analytics → Blob và nhánh consumer Java độc lập.
- [ ] Schema có eventId, deviceId, eventTime UTC, đơn vị đo, version và validation.
- [ ] Namespace/hub, partitions, retention, tier và region đã xác minh.
- [ ] Producer/consumer/job có role và network access đúng, không lộ secret.
- [ ] Java producer gửi thành công synthetic events và có metrics ingress.
- [ ] Stream Analytics có consumer group riêng, query một phút và output kiểm tra được.
- [ ] Phân biệt event time, enqueued time, processing time và late-arrival policy.
- [ ] Java EventProcessorClient có Blob checkpoint và quy trình sink bền vững.
- [ ] Event trùng không tạo tác dụng phụ trùng; event lỗi được quarantine đúng cách.
- [ ] Đã thử restart, duplicate, invalid payload, late event và burst trong lab.
- [ ] Có metrics/alert cho ingress, throttling, lag, processing errors, output và business data.
- [ ] Có capacity estimates theo events/s, bytes/s, partitions, burst, retention và throughput.
- [ ] Có dự toán cho Event Hubs, Stream Analytics, Storage, network và monitoring.
- [ ] Có giới hạn chi phí, người chịu trách nhiệm và cleanup plan không ảnh hưởng production.
- [ ] Báo cáo cuối ghi rõ điều đã được thử thật và điều vẫn chỉ là giả định.

**Kết luận:** Azure Event Hubs cung cấp lớp tiếp nhận telemetry có thể mở rộng, cho phép nhiều consumer đọc độc lập theo partition và consumer group. Azure Stream Analytics giúp xử lý cửa sổ thời gian; EventProcessorClient cung cấp khả năng xử lý tùy biến và lưu checkpoint. Một pipeline đáng tin cần **schema đúng, phân quyền phù hợp, xử lý duplicate và late event, sink idempotent, quan sát lag, dự trù capacity và kiểm soát chi phí**. Sau khi kiểm chứng đầy đủ những điều kiện đó, đội phát triển có nền tảng vững chắc để mở rộng bài lab thành một hệ thống streaming trên Azure.
