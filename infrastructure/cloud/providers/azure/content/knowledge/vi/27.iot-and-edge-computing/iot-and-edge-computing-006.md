# Azure IoT Edge và triển khai module tại thiết bị

Một nhà máy có hàng trăm bộ điều khiển, cảm biến nhiệt độ và camera. Mạng ra Internet đôi khi mất vài giờ, trong khi cảnh báo nhiệt độ cao cần xuất hiện ngay tại xưởng, không thể đợi dữ liệu đi lên cloud rồi mới có kết quả. Doanh nghiệp muốn xử lý telemetry cục bộ, chỉ chuyển dữ liệu đã lọc lên **Azure IoT Hub**, giám sát phiên bản phần mềm trên từng gateway và cập nhật chức năng phân tích mà không phải cài thủ công trên từng máy.

**Azure IoT Edge** giải quyết nhóm bài toán này bằng cách chạy những **container modules** trên thiết bị biên dưới sự điều phối của một runtime. IoT Hub giữ cấu hình mong muốn và nhận dữ liệu; thiết bị tải images, khởi chạy modules, định tuyến messages qua edgeHub và báo trạng thái triển khai. Khi mất kết nối, thiết bị có thể tiếp tục xử lý tại chỗ; dữ liệu gửi cloud có thể được **lưu tạm và chuyển tiếp** theo chính sách, trong giới hạn dung lượng, thời gian lưu và khả năng kết nối.

Bài nằm trong chương **IoT và xử lý tại biên**, thuộc module **CLOUD_PROVIDERS_AZURE**: khám phá Microsoft Azure từ subscription/resource group, Microsoft Entra ID, networking, compute, storage và dữ liệu tới triển khai, giám sát, bảo mật và chi phí kiến trúc ứng dụng. Trọng tâm là **Azure IoT Edge và triển khai module tại thiết bị**, không đánh đồng với Azure IoT Operations (dịch vụ cho những kiến trúc Azure Arc-enabled Kubernetes), Azure Functions hoặc Kubernetes nói chung.

Sau bài học, bạn có thể:

- Giải thích **IoT device, IoT Edge device, IoT Hub, Device Provisioning Service (DPS), edgeAgent, edgeHub, modules và module twins**.
- Quyết định khi nào nên đưa xử lý xuống edge thay vì đẩy mọi raw data lên cloud.
- Chuẩn bị điều kiện **Linux/CPU architecture, container runtime, disk, DNS, ports, device identity và IoT Hub**.
- Xây dựng một module Python/container có nhiệm vụ lọc telemetry và gửi output mới.
- Đọc/viết **deployment manifest** với `$edgeAgent`, `$edgeHub`, image references, create options, environment và routes.
- Phân biệt **triển khai lên một thiết bị** với **automatic deployments/layered deployments** theo device twins/tags.
- Thiết kế **edgeHub store-and-forward**, offline operation, retry/idempotency và local routing.
- Kiểm tra thực tế qua **IoT Edge CLI, IoT Hub twins, module logs và metrics**, xử lý lỗi image pull, network, route và identity.
- Áp dụng **TLS/X.509, bảo vệ registry credentials, least privilege, pinning/digest, update/rollback**, HA/DR và quản trị chi phí.

## 1. Khi nào cần tính toán tại biên?

Trong hệ IoT thuần cloud, cảm biến gửi mọi bản ghi đến nền tảng phân tích ở Azure. Mô hình này đơn giản khi mạng tốt, tốc độ và chi phí truyền dữ liệu chấp nhận được. Tuy nhiên, các điều kiện sau khiến **edge computing** có giá trị:

| Nhu cầu | Chỉ cloud | Có IoT Edge |
|---|---|---|
| Phản ứng nhanh tại xưởng | Phụ thuộc round-trip cloud và mạng | Lọc/phân tích/sinh cảnh báo local |
| Internet không ổn định | Raw messages có thể mất/đợi trên thiết bị | edgeHub có thể lưu-tạm và chuyển tiếp |
| Camera/sensor tạo rất nhiều dữ liệu | Uplink lớn, tốn băng thông | Tiền xử lý, tổng hợp hoặc chỉ gửi sự kiện |
| Điều khiển dữ liệu nhạy cảm | Raw data rời nhà máy | Có thể giữ dữ liệu gốc local, chỉ gửi kết quả phù hợp |
| Cập nhật ứng dụng trên nhiều gateway | Cài thủ công khó kiểm soát | Module deployment từ IoT Hub |
| Vận hành thiết bị từ xa | Cần công cụ riêng | Device/module twins, telemetry và health logs |

Ví dụ: camera phát ra 30 khung hình/giây, nhưng mục tiêu chỉ là phát hiện “vùng nguy hiểm có người” và đếm sự kiện theo phút. Module AI/vision tại edge có thể chuyển về cloud **metadata có kiểm soát** thay vì đẩy mọi video thô. Điều này không tự loại bỏ nghĩa vụ bảo vệ dữ liệu: metadata/ảnh cắt vẫn có thể chứa thông tin nhạy cảm.

### 1.1. IoT Edge không biến gateway thành cloud thu nhỏ

IoT Edge không tự cấp mọi tính năng của Azure: nó không thay database giao dịch, mô hình backup hoặc hệ thống giám sát cloud. Các modules phải được thiết kế để chạy **trên tài nguyên CPU/RAM/disk hữu hạn**, chịu được thiết bị bị rút điện, mạng gián đoạn và nâng cấp có kiểm soát.

Với tác vụ an toàn công nghiệp, đường **fail-safe/control loop** quan trọng cần do phần cứng/PLC và cơ chế được chứng nhận chịu trách nhiệm. Không dựa vào một container/IoT Hub command qua Internet làm bộ điều khiển duy nhất của hệ thống có rủi ro tới người hoặc tài sản.

### 1.2. Bộ tiêu chí lựa chọn

Trước khi chọn Azure IoT Edge, đo:

1. **Latency** cần phản ứng: vài milliseconds, vài giây hay vài phút?
2. **Offline duration** và tính chất uplink: mạng liên tục hay gián đoạn nhiều giờ?
3. **Volume**: bytes/message, messages/second, số devices, compression.
4. **Hardware**: CPU architecture, RAM, storage, GPU/accelerator, nhiệt độ hoạt động.
5. **Tính chất dữ liệu**: có thể mất/duplicate/trễ, có chứa PII hoặc dữ liệu bí mật?
6. **Mức độ phân tán**: một gateway hay hàng nghìn sites; cần rollout/rollback theo nhóm?
7. **Security/operability**: identity, certificate, physical access, update process, logging.
8. **Chi phí vòng đời**: phần cứng, IoT Hub messages, container registry, băng thông, monitor, nhân sự tại chỗ.

Chỉ sử dụng IoT Edge nếu module container/gateway phù hợp. Với embedded MCU không chạy được Linux container runtime, dùng thiết bị **downstream leaf** kết nối một IoT Edge gateway hoặc mô hình IoT Hub trực tiếp; không cố cài container runtime lên phần cứng không hỗ trợ.

## 2. Kiến trúc tổng thể: IoT Hub, thiết bị và xử lý local

~~~mermaid
flowchart LR
    S1[Sensor / PLC A] -->|MQTT/industrial adapter| G[IoT Edge gateway]
    S2[Sensor / PLC B] --> G
    subgraph EDGE[Thiết bị biên Linux]
      A[edgeAgent]
      H[edgeHub]
      M1[sensorSimulator / protocol adapter]
      M2[telemetryFilter / local analytics]
      M1 -->|module output| H
      H -->|module input route| M2
      M2 -->|filtered output| H
      A -. run/restart containers .-> M1
      A -. run/restart containers .-> M2
    end
    G --- EDGE
    H -->|TLS, store-and-forward| HUB[Azure IoT Hub]
    HUB -->|routing/export| BUS[Event Hubs / Functions / Storage]
    BUS --> ADX[Analytics / Azure Data Explorer]
    DPS[Device Provisioning Service] -. initial identity / assignment .-> A
    REG[Azure Container Registry] -. pull signed/approved images .-> A
    OPS[Platform/SRE] -. desired deployment / twins .-> HUB
    HUB -. desired properties/status .-> A
~~~

**Hình là mô hình logic**: nhiều cảm biến/PLC có thể dùng adapter phù hợp, không nhất thiết nói MQTT trực tiếp đến một container. Device → cloud và cloud → device sử dụng những kênh/chức năng IoT Hub khác nhau, có ràng buộc quota, quyền và kết nối.

### 2.1. Vai trò từng thành phần

| Thành phần | Vai trò | Không tự làm gì |
|---|---|---|
| **IoT Hub** | Registry danh tính, giao tiếp devices/modules, twins, routing và quản lý deployments | Không tự chạy application containers ở thiết bị |
| **DPS** | Bootstrap/provision số lượng lớn devices vào IoT Hub theo enrollment | Không thay edgeAgent chạy modules |
| **IoT Edge runtime** | Dịch vụ hệ thống trên host, kết nối danh tính và quản lý containers | Không tự có business logic cho telemetry |
| **edgeAgent** | Theo dõi desired deployment, pull/start/stop/restart modules, báo trạng thái | Không phải module lọc nhiệt độ |
| **edgeHub** | Local message broker/router, giao tiếp module/device với IoT Hub, store-and-forward | Không phải message broker bền vững với exactly-once guarantee |
| **Custom modules** | Docker/OCI container chạy business logic, protocol adapters, AI inference | Không tự được cấp quyền truy cập tất cả resources trong Azure |
| **Device twin** | Desired/reported properties và tags ở cấp device | Không thay local database hoặc sensor history |
| **Module twin** | Desired/reported properties cho từng module | Không tự biến application thành resilient nếu code không xử lý updates |
| **Azure Container Registry** | Lưu images theo tag/digest và access policies | Không mặc nhiên cấp Edge device quyền pull private images |

### 2.2. Data plane và control plane

- **Control/management flow:** platform thiết lập deployment trong IoT Hub; `edgeAgent` đồng bộ desired state và báo reported status. Việc sửa manifest có thể làm device thay images/containers.
- **Data plane:** sensors/modules phát telemetry đến `edgeHub`, hub định tuyến nội bộ hoặc ra upstream IoT Hub. Tùy route, dữ liệu có thể dừng ở local module hoặc được forward.
- **Identity plane:** Edge runtime, edgeAgent, edgeHub, modules và IoT Hub dùng danh tính/credentials riêng theo mô hình IoT Edge; Azure RBAC của người quản trị khác với device identity.

Một container running không có nghĩa đã nhận được sensor data; một device `Connected` trên Portal không có nghĩa module business logic đúng. Phải quan sát **cả desired/reported state, routing và end-to-end message flow**.

## 3. edgeAgent, edgeHub và runtime thực sự hoạt động thế nào?

### 3.1. edgeAgent: cơ chế hòa giải desired state

Khi IoT Hub gửi deployment:

~~~text
IoT Hub stores desired module configuration
     ↓
Device syncs its Edge Agent twin
     ↓
edgeAgent reads target images, env, createOptions, restart policy
     ↓
Container engine pulls images / starts or stops modules
     ↓
edgeAgent reports running state and errors
~~~

Nếu desired manifest chứa version mới `telemetryFilter:2.0` nhưng thiết bị không pull được image, **device desired state đã đổi** còn runtime vẫn có thể chạy version cũ hoặc module không chạy. Muốn đánh giá rollout, kiểm tra **reported state** và test business outputs chứ không chỉ deployment accepted.

edgeAgent phải có quyền truy cập container runtime và thông tin registry phù hợp. Module image nên pin bằng **immutable digest** hoặc tag immutable có kiểm soát; mutable `latest` dễ gây hai thiết bị nhận khác binaries dù cùng manifest.

### 3.2. edgeHub: local broker và upstream

edgeHub cung cấp **local routing** giữa modules/connected downstream devices và upstream IoT Hub. Với cấu hình `storeAndForwardConfiguration.timeToLiveSecs`, messages đủ điều kiện có thể được **lưu trên disk local** khi mất mạng rồi gửi tiếp sau khi uplink phục hồi.

Những giới hạn phải hiểu:

- Store-and-forward có **TTL**, không lưu vĩnh viễn.
- Disk cần đủ capacity và filesystem phải có quyền/bảo mật phù hợp.
- Khi thiết bị hỏng hoàn toàn, local store cũng có thể mất; đây **không phải backup**.
- Khi reconnect/retry, duplicates có thể xảy ra; backend phải idempotent khi cần.
- Không bảo đảm thứ tự toàn cục khi nhiều modules/devices phát cùng lúc.
- Nếu backlog > disk hoặc TTL, dữ liệu có thể bị loại và cần alert.

### 3.3. Runtime host services và các phiên bản

Trên IoT Edge phiên bản hiện đại, host có các dịch vụ identity/management (ví dụ **Azure IoT Identity Service**) và công cụ `aziotctl`/`iotedge` tùy phiên bản. Thành phần/thư mục cấu hình và package names thay đổi giữa IoT Edge 1.4, 1.5 và các bản cập nhật. **Không dùng tutorial 1.0/1.1 cũ rồi mặc định lệnh/cấu hình đúng cho device mới.**

Với production, chọn **phiên bản còn được Microsoft hỗ trợ** phù hợp OS/architecture của thiết bị, kiểm tra release/support lifecycle và chính sách vá lỗi. Các tag image `:1.5` trong bài chỉ minh họa dòng runtime; hãy xác minh các image/version tags hiện hành trước triển khai thật.

### 3.4. Các trạng thái cần phân biệt

| Dấu hiệu | Ý nghĩa | Việc cần xác nhận thêm |
|---|---|---|
| IoT Hub device identity tồn tại | Đã đăng ký device ID | Thiết bị có provision/key/cert đúng chưa? |
| IoT Hub thấy device connected | Có kết nối device/cloud | edgeAgent và app modules có khỏe không? |
| edgeAgent running | Agent container chạy | Có reconcile desired config không? |
| edgeHub running | Local broker chạy | Có routes, upstream và local store khỏe không? |
| Custom module running | Container process còn sống | Có đọc/sinh đúng message và ack/error không? |
| Deployment đã gán | Desired config được lưu | Reported runtime khớp image/digest phiên bản không? |
| edgeHub upstream connected | Kênh cloud hoạt động | Messages có tới đúng consumer/route không? |

## 4. Chuẩn bị thiết bị: OS, CPU, disk và mạng

IoT Edge thường vận hành trên **Linux-compatible host**, với container runtime thích hợp và phiên bản được hỗ trợ. Tùy tình huống có nền tảng ảo hóa/Windows hosting được hỗ trợ theo tài liệu, nhưng bài lab này giả định **Linux x86_64** hoặc ARM64 được IoT Edge runtime và image hỗ trợ.

### 4.1. Preflight phần cứng và hệ điều hành

| Hạng mục | Cần kiểm tra |
|---|---|
| **CPU architecture** | `amd64` hay `arm64`; module image manifest đúng kiến trúc |
| **Operating system** | Distro/kernel/container runtime được bản IoT Edge chọn hỗ trợ |
| **RAM/CPU** | Đủ edgeAgent, edgeHub, 2+ app modules, peak inference/decoder |
| **Disk** | Root image layers, local store-and-forward, logs, model files, update rollback |
| **Clock/NTP** | UTC thời gian chuẩn cho TLS certificates, SAS/token expiry, telemetry |
| **Networking** | DNS, outbound TLS đến IoT Hub/DPS/ACR, proxy/firewall; local ports |
| **Identity** | Device ID và enrollment/credentials được cấp phép |
| **Storage protection** | Quyền filesystem, disk encryption nếu rủi ro mất cắp thiết bị |
| **Physical security** | Tamper protection, secure boot/TPM khi có, disable unused services |
| **Observability** | Remote health/log metrics, disk space, offline queue depth |

**Đừng định lượng chỉ theo RAM của edgeHub**: camera/AI module có thể cần GPU, driver/device passthrough và memory gấp nhiều lần những ứng dụng lọc JSON. Benchmark trên chính loại gateway production.

### 4.2. Các đường mạng

~~~text
Edge device outbound:
  -> IoT Hub (MQTT over TLS / AMQP over TLS / HTTPS as configured)
  -> DPS global endpoint if using DPS
  -> Container Registry over HTTPS for image pulls
  -> Optional Azure Monitor/Key Vault/backend endpoints as authorized

Local:
  sensor/protocol adapter -> module/edgeHub
  edgeHub -> local modules
  downstream leaf devices -> edgeHub gateway endpoints if enabled
~~~

Các cổng IoT Hub phổ biến gồm **8883/MQTT**, **5671/AMQP** và **443/HTTPS/WebSocket** theo protocol/feature; module image pull thường cần **443** tới registry. Không mở **mọi inbound port** chỉ vì một tutorial ghi danh sách giao thức. Xác định protocol mà device/leaf thực dùng, certificate, firewall/proxy requirements và site security.

### 4.3. Kiểm tra từ host

~~~bash
# Chỉ xem thông tin, không cài đặt/gỡ runtime trong ví dụ này.
uname -a
uname -m
df -h
free -h
date -u

# Thay hostname bằng đúng hub của tổ chức.
nslookup "<iot-hub-name>.azure-devices.net"
~~~

Kết quả DNS/TCP thông **không chứng minh** device authentication hoặc TLS handshake đúng. Azure CLI ở laptop quản trị cũng không tự đo được network của gateway trong nhà máy.

### 4.4. Container runtime

IoT Edge cần container engine tương thích theo bảng hỗ trợ (thường dùng **Moby** trong hệ sinh thái IoT Edge). Runtime service cần quyền quản lý containers; **không** cấp Docker socket cho mọi custom module nếu không cần. Expose Docker socket có thể cho container quyền mạnh trên host.

Ứng dụng container nên dùng user không đặc quyền, giới hạn resources, read-only filesystem khi khả thi, bind mounts tối thiểu và log rotation. Đừng coi thiết bị biên là “máy nội bộ đáng tin” chỉ vì không trực tiếp mở ra Internet.

## 5. IoT Hub và DPS: nhận diện thiết bị trước khi chạy modules

IoT Hub cần biết **thiết bị biên là ai**. Có hai hướng phổ biến:

- **Manual provisioning:** gán IoT Hub hostname, device identity và authentication material cụ thể; thích hợp lab/số lượng nhỏ nhưng khó quản lý secrets ở quy mô lớn.
- **DPS provisioning:** đăng ký enrollment/attestation để thiết bị được gán vào IoT Hub phù hợp; hữu ích khi triển khai số lượng lớn, chuyển hub/region theo chính sách. DPS **không** tự cài module; vẫn cần IoT Edge runtime và desired deployment.

### 5.1. Quan hệ giữa Azure RBAC và IoT identity

| Danh tính/quyền | Mục đích |
|---|---|
| **Azure RBAC** của admin/automation | Tạo IoT Hub, quản lý identities/deployments theo scope cho phép |
| **Device identity** tại IoT Hub | Thiết bị xác thực với IoT Hub |
| **DPS enrollment attestation** | Thiết bị chứng minh danh tính khi được provision |
| **Module identity** | Container module giao tiếp theo ranh giới module/IoT Hub |
| **ACR pull identity/credentials** | Device/container engine được phép tải image |
| **Backend identity** | Consumer như Function/Service Bus reader được cấp quyền riêng |

**Azure RBAC Contributor không tự trở thành device credential**. Cũng không đưa access token Azure Portal của nhân viên vào file cấu hình IoT Edge để làm khóa thiết bị.

### 5.2. Đăng ký IoT Edge device cho lab

Giả sử IoT Hub đã tồn tại trong **subscription lab được cấp phép**:

~~~bash
az login
az extension add --name azure-iot

SUBSCRIPTION_ID="<approved-subscription-id>"
HUB_NAME="<approved-iot-hub-name>"
DEVICE_ID="edge-gateway-lab-001"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{name:name,id:id}" -o table

# Chỉ tạo khi device ID chưa tồn tại và bạn được phép.
az iot hub device-identity create \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --edge-enabled

az iot hub device-identity show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --output json
~~~

Những lệnh trên chỉ là **lab tham khảo**, không được thực thi khi soạn bài. `azure-iot` extension và options có thể đổi theo phiên bản CLI; kiểm tra `az iot hub device-identity create --help` tại thời điểm thực hành. Một số mô hình dùng service principal cần data-plane RBAC/IoT Hub permissions riêng ngoài Azure Reader.

### 5.3. Certificate và hardware trust

Trong production, ưu tiên **X.509 certificate với cơ chế lưu private key an toàn/TPM/HSM** hoặc kiểu attestation được phê duyệt, thay vì chép một symmetric key chung cho hàng nghìn gateways. Mỗi device cần danh tính riêng để **thu hồi/rotate/điều tra** mà không ảnh hưởng cả fleet.

Nếu dùng symmetric key trong lab, không in connection string có key ra terminal chia sẻ, không commit vào Git, không gửi vào logs/tickets. Dùng cơ chế provisioning/secret injection và filesystem permissions phù hợp; cấu hình chính xác của `/etc/aziot/config.toml` tùy IoT Edge runtime version và loại authentication, nên dựa trên hướng dẫn dành cho phiên bản đã chọn.

### 5.4. Provision runtime tại thiết bị

Luồng triển khai thực tế:

1. Đảm bảo host OS/architecture được phiên bản IoT Edge hỗ trợ.
2. Cài **Azure IoT Identity Service, IoT Edge runtime và container engine** đúng version từ nguồn tin cậy.
3. Cấu hình manual/DPS provisioning tại host bằng phương thức bảo vệ secrets.
4. Apply cấu hình, xác minh kết nối IoT Hub và chứng chỉ/clock.
5. Khởi chạy/kiểm tra edgeAgent và edgeHub.
6. Chỉ khi runtime ổn mới đẩy custom module deployment.

Các lệnh kiểm tra hữu ích (trên thiết bị đã cài runtime):

~~~bash
# Cần quyền quản trị host phù hợp; đây là read-only diagnostics.
sudo aziotctl check
sudo iotedge system status
sudo iotedge list
sudo iotedge logs edgeAgent --tail 100
sudo iotedge logs edgeHub --tail 100
~~~

**Không chạy script cài đặt ngẫu nhiên từ Internet** trên gateway production; dùng image/base OS do team thiết bị phê duyệt, pinned packages và quy trình OTA/maintenance window. Không paste private key/connection string vào chat.

## 6. Module là container, nhưng module identity khác container image

Một IoT Edge module gồm nhiều yếu tố:

~~~text
Module logical ID:    telemetryFilter
Container image:      <acr>.azurecr.io/iot/telemetry-filter:1.0.0
Image architecture:   linux/amd64 (or linux/arm64)
Desired configuration: thresholds, input/output routes, restart policy
Runtime credentials:  IoT Edge module environment / identity
Module twin:          desired and reported properties
Resource limits:      CPU, memory, storage, device mounts if needed
Logs/metrics:         stdout/stderr, app metrics, edgeAgent status
~~~

**Module ID không phải image name**. Một image có thể được nhiều devices/modules chạy, nhưng mỗi module identity/twin và cấu hình riêng. Một container chạy được ngoài Docker host chưa chắc chạy được trên IoT Edge nếu nó đòi Edge-provided environment/identity mà không có.

### 6.1. Hai cách tích hợp với edgeHub

- **Module SDK:** ứng dụng dùng Azure IoT Device SDK để nhận message ở input và gửi đến named output. IoT Edge runtime cung cấp context/module identity.
- **Adapter/process tùy biến:** container đọc camera/serial/OPC UA/local network, chuyển thành telemetry chuẩn rồi phát lên edgeHub qua module SDK.

Mỗi module nên có hợp đồng rõ:

| Hạng mục | Ví dụ |
|---|---|
| Input | JSON nhiệt độ `temperatureC` từ `sensorSimulator/temperatureOutput` |
| Output | JSON cảnh báo/hệ số tổng hợp từ `telemetryFilter/filtered` |
| Failures | Bad payload → log/error counter, không làm container restart vô hạn |
| Configuration | `TEMP_THRESHOLD_C` hoặc module twin desired property |
| Security | Không đọc camera/USB nếu không cần; không có cloud secret tĩnh |
| Recovery | Idempotent trên event ID, kiểm tra replay khi reconnect |

### 6.2. Container lifecycle và restart policy

edgeAgent dùng desired configuration để đảm bảo modules ở trạng thái mong muốn. Một module `restartPolicy: always` có thể tự được khởi chạy lại sau crash, nhưng **restart liên tục không chữa lỗi cấu hình**: image sai architecture, secret thiếu, route hỏng hoặc process exit ngay sẽ tạo crash loop.

Đưa lỗi có thể xử lý (malformed message, HTTP timeout) vào business error handling; để process exit khi không thể khôi phục một trạng thái cần thiết và có alert. Đừng nuốt mọi exception rồi trả message “đã xử lý” dù dữ liệu bị bỏ.

## 7. Bài thực hành: hai Python modules tạo và lọc telemetry

Ta xây một ví dụ **tự chứa ở mức source code**:

~~~text
sensorSimulator
  └── output: temperatureOutput
            ↓ route của edgeHub
telemetryFilter
  └── input: input1
       └── Nếu temperatureC >= 35°C
             └── output: filtered
                       ↓ route của edgeHub
                   Azure IoT Hub
~~~

Hai modules dùng **Azure IoT Device SDK for Python**, giao tiếp qua **edgeHub**, không gọi trực tiếp HTTP đến IoT Hub. Nhiệt độ và sự kiện là dữ liệu **giả**; không dùng code này để điều khiển máy móc. Dấu `>=35°C` chỉ là quy tắc minh họa, không phải ngưỡng an toàn công nghiệp.

### 7.1. Cấu trúc project minh họa

~~~text
edge-telemetry-demo/
  sensorSimulator/
    app.py
    requirements.txt
    Dockerfile
  telemetryFilter/
    app.py
    requirements.txt
    Dockerfile
  deployment.template.json
~~~

Đây là **layout minh họa cho người học tạo tại repo riêng**, không phải yêu cầu worker ghi thêm files. Bài STEP 4 chỉ ghi vào Markdown được giao.

### 7.2. Module phát dữ liệu giả

Nội dung `sensorSimulator/app.py`:

~~~python
import asyncio
import json
import os
import random
import uuid
from datetime import datetime, timezone

from azure.iot.device import Message
from azure.iot.device.aio import IoTHubModuleClient


async def main():
    interval = max(1, int(os.getenv("SENSOR_INTERVAL_SECS", "10")))
    client = IoTHubModuleClient.create_from_edge_environment()
    await client.connect()
    try:
        while True:
            payload = {
                "eventId": str(uuid.uuid4()),
                "deviceId": "simulated-sensor-01",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "temperatureC": round(31.0 + random.random() * 10.0, 2)
            }
            message = Message(json.dumps(payload))
            message.content_type = "application/json"
            message.content_encoding = "utf-8"
            await client.send_message_to_output(
                message, "temperatureOutput"
            )
            print("Emitted synthetic temperature event", flush=True)
            await asyncio.sleep(interval)
    finally:
        await client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
~~~

**Giải thích:**

- `create_from_edge_environment()` dùng module context được IoT Edge runtime cấp; đây **không phải** cách tạo client trực tiếp trên laptop thiếu Edge environment.
- `send_message_to_output(..., "temperatureOutput")` đặt message lên **named output** cho edgeHub route.
- Mỗi event có `eventId` và UTC timestamp để backend phát hiện duplicates/late arrivals.
- `print` không chứa raw secret/payload nhạy cảm; ở production thêm structured logs, metrics và shutdown handling.
- Ví dụ là simulator vô hại; sensor thật phải đọc qua giao thức/adapter phù hợp (serial, Modbus, OPC UA...) và validate đơn vị đo/độ tin cậy.

### 7.3. Module lọc nhiệt độ

Nội dung `telemetryFilter/app.py`:

~~~python
import asyncio
import json
import os
from datetime import datetime, timezone

from azure.iot.device import Message
from azure.iot.device.aio import IoTHubModuleClient


async def main():
    threshold_c = float(os.getenv("TEMP_THRESHOLD_C", "35.0"))
    client = IoTHubModuleClient.create_from_edge_environment()

    async def on_message_received(message):
        try:
            raw = message.data
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
            temperature_c = float(payload["temperatureC"])
            event_id = str(payload["eventId"])
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
            # Production: send safe metric / quarantine event,
            # never leak credentials or the entire untrusted payload.
            print("Invalid input telemetry:", type(exc).__name__, flush=True)
            return

        if temperature_c < threshold_c:
            return  # Local filtering; no upstream data for normal readings.

        filtered = {
            "eventId": event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "originalTimestamp": payload.get("timestamp"),
            "deviceId": payload.get("deviceId"),
            "temperatureC": temperature_c,
            "alert": "HighTemperature"
        }
        outgoing = Message(json.dumps(filtered))
        outgoing.content_type = "application/json"
        outgoing.content_encoding = "utf-8"
        await client.send_message_to_output(outgoing, "filtered")
        print("Forwarded high-temperature alert", flush=True)

    client.on_message_received = on_message_received
    await client.connect()
    try:
        await asyncio.Event().wait()  # Receive via callback until shutdown.
    finally:
        await client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
~~~

**Lưu ý về code:**

- `message.data` có thể là bytes/string tùy phiên bản SDK; ví dụ chuyển đổi rõ ràng.
- Callback ở IoT Device SDK phiên bản được hỗ trợ có thể cần cập nhật theo API cụ thể; xác minh `on_message_received` và `send_message_to_output` trong bộ SDK đã pin khi build.
- Dữ liệu không đạt ngưỡng được xử lý local rồi bỏ; **không gửi từng bản ghi** lên IoT Hub.
- Khi output thất bại, SDK/module phải có chính sách timeout/retry và metrics; ví dụ đơn giản chưa có **durable local transaction log**.
- Nếu nguồn phát cùng `eventId` hai lần, downstream phải deduplicate nếu business yêu cầu.
- Không coi quy tắc so sánh số thực này là validation sensor an toàn; cần quality flags, calibration và plausibility checks.

### 7.4. Dockerfile cho từng module

Cùng một template Dockerfile trong **mỗi thư mục module**, với file `app.py` tương ứng:

~~~dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Non-root execution in the container.
RUN useradd --system --uid 10001 edgeapp
USER 10001

CMD ["python", "app.py"]
~~~

`requirements.txt` cho bài lab:

~~~text
azure-iot-device>=2.0,<3.0
~~~

Đây là **ràng buộc phiên bản để minh họa**, không phải lockfile production. Với CI/CD thật, chọn SDK version đã kiểm thử, pin exact version/hashes, scan CVEs và pin base image bằng digest. `python:3.11-slim` cũng cần kiểm tra hỗ trợ kiến trúc phần cứng và vòng đời bảo mật.

### 7.5. Build images theo kiến trúc thiết bị

Trên máy build được phép có Docker/BuildKit và registry lab:

~~~bash
ACR_LOGIN_SERVER="<approved-acr-name>.azurecr.io"
VERSION="1.0.0"

# Cú pháp giả định chạy từ thư mục edge-telemetry-demo.
docker build --platform linux/amd64 \
  -t "$ACR_LOGIN_SERVER/iot/sensor-simulator:$VERSION" \
  ./sensorSimulator

docker build --platform linux/amd64 \
  -t "$ACR_LOGIN_SERVER/iot/telemetry-filter:$VERSION" \
  ./telemetryFilter
~~~

Nếu gateway ARM64, build **`linux/arm64`** hoặc multi-architecture manifest theo quy trình hỗ trợ; không deploy image amd64 lên ARM64 rồi cho rằng lỗi là IoT Hub. Việc build cross-platform có thể cần Buildx/QEMU hoặc runner kiến trúc phù hợp; nên dùng native/multi-arch CI và test trên thiết bị thật.

### 7.6. Đưa images vào private registry

~~~bash
# Chỉ trong lab đã được phép; lệnh push ảnh hưởng registry.
az acr login --name "<approved-acr-name>"

docker push "$ACR_LOGIN_SERVER/iot/sensor-simulator:$VERSION"
docker push "$ACR_LOGIN_SERVER/iot/telemetry-filter:$VERSION"
~~~

Không đưa ACR admin username/password vào Git hoặc manifest plaintext. **Device ở nhà máy phải có cơ chế authentication/registry credentials riêng được cấp và rotate đúng**. Với private ACR, push thành công từ developer laptop không chứng minh gateway có quyền pull; điều đó cần kiểm thử riêng trên device.

### 7.7. Hợp đồng events và xử lý dữ liệu lỗi

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `eventId` | string UUID | Phân biệt event để dedup |
| `deviceId` | string | Device nguồn logic |
| `timestamp` | UTC ISO 8601 | Event time |
| `temperatureC` | number | Nhiệt độ °C |
| `alert` | string | Có sau khi lọc, ví dụ `HighTemperature` |
| `originalTimestamp` | UTC ISO 8601 | Thời gian đọc sensor ban đầu |

**Không log toàn bộ message trong production nếu payload có PII/PII-like sensor data**. Schema phải có versioning khi thay tên field, thay đơn vị °F/°C hoặc thêm loại cảm biến.

## 8. Deployment manifest: hợp đồng điều khiển module trên device

Một **deployment manifest** mô tả **desired modules và routes** mà edgeAgent/edgeHub phải áp dụng. Bản mẫu bên dưới dùng schema tương ứng dòng IoT Edge 1.x phổ biến; hãy kiểm tra CLI/runtime/IoT Hub version thực khi áp dụng.

### 8.1. Ví dụ manifest hoàn chỉnh

Ví dụ `deployment.template.json`:

~~~json
{
  "modulesContent": {
    "$edgeAgent": {
      "properties.desired": {
        "schemaVersion": "1.1",
        "runtime": {
          "type": "docker",
          "settings": {
            "minDockerVersion": "v1.25",
            "loggingOptions": "",
            "registryCredentials": {}
          }
        },
        "systemModules": {
          "edgeAgent": {
            "type": "docker",
            "settings": {
              "image": "mcr.microsoft.com/azureiotedge-agent:1.5",
              "createOptions": "{}"
            }
          },
          "edgeHub": {
            "type": "docker",
            "status": "running",
            "restartPolicy": "always",
            "settings": {
              "image": "mcr.microsoft.com/azureiotedge-hub:1.5",
              "createOptions": "{}"
            }
          }
        },
        "modules": {
          "sensorSimulator": {
            "version": "1.0.0",
            "type": "docker",
            "status": "running",
            "restartPolicy": "always",
            "settings": {
              "image": "<approved-acr-name>.azurecr.io/iot/sensor-simulator:1.0.0",
              "createOptions": "{\"HostConfig\":{\"Memory\":268435456}}"
            },
            "env": {
              "SENSOR_INTERVAL_SECS": {
                "value": "10"
              }
            }
          },
          "telemetryFilter": {
            "version": "1.0.0",
            "type": "docker",
            "status": "running",
            "restartPolicy": "always",
            "settings": {
              "image": "<approved-acr-name>.azurecr.io/iot/telemetry-filter:1.0.0",
              "createOptions": "{\"HostConfig\":{\"Memory\":268435456}}"
            },
            "env": {
              "TEMP_THRESHOLD_C": {
                "value": "35.0"
              }
            }
          }
        }
      }
    },
    "$edgeHub": {
      "properties.desired": {
        "schemaVersion": "1.2",
        "routes": {
          "sensorToFilter": "FROM /messages/modules/sensorSimulator/outputs/temperatureOutput INTO BrokeredEndpoint(\"/modules/telemetryFilter/inputs/input1\")",
          "filteredToCloud": "FROM /messages/modules/telemetryFilter/outputs/filtered INTO $upstream"
        },
        "storeAndForwardConfiguration": {
          "timeToLiveSecs": 7200
        }
      }
    },
    "telemetryFilter": {
      "properties.desired": {
        "schemaVersion": "1.0",
        "configurationNote": "demo; threshold uses env in this lesson"
      }
    }
  }
}
~~~

**Những điều kiện để manifest trên hoạt động:**

- Thay `<approved-acr-name>` bằng registry đã cấp phép và **device thật có quyền pull image**. Trường `registryCredentials: {}` chỉ dùng khi image public hoặc có **cơ chế registry authentication khác được hỗ trợ**; với private ACR thông thường phải bổ sung registry auth **an toàn**, không ghi password tĩnh vào bài/Git.
- IoT Edge runtime có đúng system module images/versions được hỗ trợ; `:1.5` là **tag ví dụ**, không phải khẳng định bản cập nhật mới nhất.
- Máy Edge có container engine, DNS/egress và disk đủ.
- `createOptions` là **JSON encoded dưới dạng string** trong JSON tổng; sai escape sẽ khiến deployment thất bại.
- Sơ đồ route tương ứng chính xác **case-sensitive module IDs và output names** trong code.
- Không mở host ports vì demo chỉ dùng **module-to-module**; leaf devices từ bên ngoài cần thiết lập edgeHub ports/TLS riêng.
- Cấu trúc JSON đã đầy đủ để dạy những trường chính, nhưng deployment production còn có thể yêu cầu policy/configuration như runtime registry auth, certificate, logging, volume mounts và metadata khác.

### 8.2. Đọc manifest từ ngoài vào trong

| Path | Ý nghĩa |
|---|---|
| `modulesContent` | Tập desired module twin updates |
| `$edgeAgent.properties.desired` | Desired module inventory/runtime |
| `runtime.type/settings` | Container runtime, minimum engine/properties |
| `systemModules.edgeAgent/edgeHub` | Images và lifecycle của modules hệ thống |
| `modules.sensorSimulator` | Image và môi trường của simulator |
| `modules.telemetryFilter` | Image, threshold env và restart |
| `$edgeHub.properties.desired.routes` | Định tuyến qua edgeHub |
| `storeAndForwardConfiguration.timeToLiveSecs` | TTL cho messages giữ chờ uplink |
| `telemetryFilter.properties.desired` | Module twin desired data cho app nếu dùng |

**Đổi field environment variable trong edgeAgent** không giống **đổi module twin desired property**. Container env thường cần reconcile/restart/update để tiến trình thấy giá trị mới. Module twin có thể cập nhật desired property và module code phải **subscribe/handle update callback** mới phản ứng ngay; ví dụ Python này lấy threshold từ env khi khởi động, nên `configurationNote` trong twin không thay đổi ngưỡng.

### 8.3. Vì sao dùng output route có tên rõ ràng?

Giả sử bạn viết một route quá rộng:

~~~text
FROM /messages/* INTO BrokeredEndpoint("/modules/telemetryFilter/inputs/input1")
~~~

Nếu filter cũng phát messages là một phần của `/messages/*`, route không được giới hạn có thể vô tình chuyển cả output đã lọc **trở lại input**, tạo vòng lặp và tăng traffic vô hạn. Bản demo dùng **nguồn là module/output cụ thể**:

~~~text
FROM /messages/modules/sensorSimulator/outputs/temperatureOutput
INTO BrokeredEndpoint("/modules/telemetryFilter/inputs/input1")
~~~

và chỉ forward output lọc:

~~~text
FROM /messages/modules/telemetryFilter/outputs/filtered
INTO $upstream
~~~

Các expression route phải tuân cú pháp edgeHub; đừng trộn với **Azure IoT Hub message routing queries** ở cloud hay cú pháp SQL/KQL. Module input name `input1`, output names `temperatureOutput`/`filtered` phải trùng code và config.

### 8.4. Local flow vs cloud flow

~~~mermaid
sequenceDiagram
    participant S as sensorSimulator
    participant H as edgeHub
    participant F as telemetryFilter
    participant I as Azure IoT Hub
    S->>H: message on output temperatureOutput
    H->>F: route to input1
    F->>F: validate temperature and eventId
    alt Temperature below threshold
        F-->>F: local only; no cloud message
    else Temperature above threshold
        F->>H: message on output filtered
        alt Internet available
            H->>I: forward telemetry
        else Internet offline
            H->>H: buffer eligible message until TTL/capacity
        end
    end
~~~

**Không suy rằng message đã gọi `send_message_to_output` là chắc chắn đến cloud.** Tùy edgeHub store/disk/offline/retry/expiry, message có thể tới sau hoặc không tới; cần end-to-end monitoring, correlation IDs, loss accounting và acknowledgements theo nghiệp vụ.

## 9. Triển khai trực tiếp lên một IoT Edge device

Với lab chỉ có một gateway, bạn có thể gán manifest qua **Azure Portal** hoặc **Azure IoT extension của CLI**. Trong production, dùng pipeline có kiểm duyệt, image digest/approval và chiến lược rollout theo ring.

### 9.1. Quy trình trong Azure Portal

1. Mở đúng **subscription → IoT Hub → Devices**.
2. Chọn device identity có **IoT Edge capability** và đúng device ID.
3. Chọn thao tác **Set modules / deployment** theo UI hiện tại.
4. Thiết lập images cho `sensorSimulator` và `telemetryFilter`; cập nhật registry auth bằng cơ chế được phép.
5. Cấu hình **environment variables, createOptions/resource limits**.
6. Định nghĩa routes trong `$edgeHub` và store-and-forward TTL.
7. Xem review/validation rồi apply cho đúng device.
8. Kiểm tra edgeAgent reported status, `iotedge list` và module logs từ **gateway thật**.
9. Test event nhiệt độ cao, xác nhận message đi qua filter rồi tới IoT Hub upstream.

Portal nhận desired configuration, nhưng **không chứng minh pull image thành công**: phải kiểm tra device runtime khi thiết bị có kết nối.

### 9.2. Azure CLI: gán manifest

Giả sử bạn đã có file manifest **được tạo tại workspace lab riêng của người học**, đúng cấu trúc `modulesContent` và đã xác nhận registry access:

~~~bash
az login
az extension add --name azure-iot

SUBSCRIPTION_ID="<approved-subscription-id>"
HUB_NAME="<approved-iot-hub>"
DEVICE_ID="edge-gateway-lab-001"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id,name:name}" --output table

# Hành động WRITE: thay desired modules của đúng thiết bị lab.
az iot edge set-modules \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --content "./deployment.template.json"
~~~

**Lệnh `set-modules` là thay đổi remote deployment**, không phải lệnh kiểm tra. Không áp lên gateway production hay một thiết bị đang nhận **automatic/layered deployment** mà chưa hiểu precedence. Tùy phiên bản CLI extension, tên tham số hoặc cách xác thực IoT Hub data plane có thể khác; kiểm tra `az iot edge set-modules --help`.

### 9.3. Xác minh device và module twins

~~~bash
# Các lệnh chỉ đọc để theo dõi sau deploy.
az iot hub device-identity show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --output json

az iot hub device-twin show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --output json

# Trong Bash, quote để giữ nguyên ký tự $.
az iot hub module-twin show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --module-id '$edgeAgent' \
  --output json

az iot hub module-twin show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --module-id '$edgeHub' \
  --output json
~~~

Ở shell PowerShell, dùng single quotes tương ứng để không expand tên module bắt đầu bằng `$`. Không đưa **IoT Hub connection string/service policy keys** vào lệnh được log hoặc CI output. Ưu tiên Microsoft Entra identity/least-privilege service permissions khi CLI/operation hỗ trợ.

### 9.4. Kiểm tra trên thiết bị

~~~bash
sudo iotedge system status
sudo iotedge list

sudo iotedge logs sensorSimulator --tail 100
sudo iotedge logs telemetryFilter --tail 100
sudo iotedge logs edgeHub --tail 100
sudo iotedge logs edgeAgent --tail 100
~~~

Kỳ vọng `sensorSimulator` phát sự kiện đều, `telemetryFilter` ghi log cho sự kiện vượt ngưỡng, edgeHub có tuyến upstream, và IoT Hub nhận telemetry tương ứng trong môi trường lab. **Lỗi không có telemetry** có thể ở route, input/output name, module callback, IoT Hub routing hoặc thiết bị offline, dù containers đều `running`.

### 9.5. Đo kết quả thay vì chỉ nhìn container trạng thái `running`

| Mốc | Bằng chứng nên thu thập |
|---|---|
| Desired config applied | Manifest/device twin có version mong muốn |
| edgeAgent reconcile | Reported modules/images/status tương ứng |
| Image pull succeeds | Không có registry auth/architecture/pull errors |
| Simulator emits | Local logs/metrics có `temperatureOutput` traffic |
| Filter receives | Message receive counters/logs an toàn |
| Route works | Module input/output counters, edgeHub diagnostics |
| IoT Hub receives | Test consumer của hub nhận `filtered` messages |
| Offline resilience | Test mất uplink có backlog, reconnect gửi lại trong TTL |
| End-to-end accuracy | Event IDs, timestamp và payload schema được giữ đúng |

## 10. Triển khai hàng loạt bằng automatic và layered deployments

Với 5 gateway trong lab, chọn một device và `set-modules` có thể đủ. Với 5.000 gateways ở nhiều nhà máy, cần **fleet management** bằng targeted deployments, tags, priority, device rings và quy trình rollback.

### 10.1. Deployment theo target condition

IoT Hub có thể nhắm thiết bị dựa trên **device twin tags/properties**. Ví dụ định hướng:

~~~json
{
  "tags": {
    "environment": "lab",
    "site": "factory-a",
    "ring": "canary",
    "hardware": "gateway-amd64-v2"
  }
}
~~~

Đây là **fragment** minh họa phần tags trong device twin, không phải entire IoT Hub device twin payload. Tags thường do phía service/admin quản lý, không phải device tự báo tùy ý như reported properties; cần Azure/IoT Hub quyền ghi phù hợp.

Một automatic deployment có thể target:

~~~text
tags.environment='lab' AND tags.ring='canary'
~~~

Kết quả là những thiết bị thuộc **ring canary** được gán desired module configuration. Đảm bảo cú pháp target condition đúng theo IoT Hub API/CLI và tags thực của từng thiết bị; đừng giả định chỉ cần folder name “canary” là Azure biết group.

### 10.2. Azure CLI tự động deploy (lab)

~~~bash
DEPLOYMENT_ID="telemetry-filter-canary-v1"

# Hành động WRITE tới fleet match target condition.
az iot edge deployment create \
  --hub-name "$HUB_NAME" \
  --deployment-id "$DEPLOYMENT_ID" \
  --content "./deployment.template.json" \
  --target-condition "tags.environment='lab' AND tags.ring='canary'" \
  --priority 20

# Chỉ đọc deployment metadata, target và metrics.
az iot edge deployment show \
  --hub-name "$HUB_NAME" \
  --deployment-id "$DEPLOYMENT_ID" \
  --output json
~~~

**Cảnh báo:** target condition sai có thể tác động nhiều thiết bị. Trước khi chạy, liệt kê/audit các device twins match condition và thực hành với **ring lab nhỏ**. Lệnh này không được thực thi khi viết bài; option support phụ thuộc Azure IoT extension version. Lúc báo thành công, kiểm tra **reported deployed/running states trên devices**, không chỉ response từ IoT Hub.

### 10.3. Base và layered deployments

**Layered deployments** dùng để thêm/cập nhật các phần cấu hình trên một base deployment mà không copy toàn bộ cấu hình mỗi lần. Ví dụ:

~~~text
Base deployment:
  edgeAgent + edgeHub
  telemetryFilter, basic routes, logging policy

Layer for factory-a:
  extra protocolAdapter module
  related routes and settings

Layer for canary ring:
  tuned threshold / experimental module
~~~

Các lớp/overrides và priorities có quy tắc merge/precedence riêng của IoT Edge deployment. **Không tùy tiện khai báo hai deployments sửa cùng một module twin field rồi giả định thiết bị chọn ngẫu nhiên hoặc chọn bản mới nhất**. Thiết kế base/layers tách trách nhiệm và test effective desired configuration trên một device thử nghiệm.

### 10.4. Rollout theo rings

~~~mermaid
flowchart LR
    B[Build and scan image] --> TEST[Lab gateways 1-3]
    TEST --> CANARY[Canary site: 1-5% devices]
    CANARY --> PILOT[Pilot sites: 10-20%]
    PILOT --> FLEET[Remaining fleet]
    CANARY -. Fail .-> R[Rollback approved image/manifest]
    PILOT -. Fail .-> R
    FLEET -. Fail .-> R
    R --> OBS[Verify reported state and telemetry]
~~~

Lộ trình nên có **promotion gates**:

- % devices áp dụng manifest đúng.
- Tỷ lệ modules `running`, crash loops và lỗi image pull.
- Telemetry lag/drop, throughput và CPU/RAM/disk peak.
- Độ chính xác event/alert (false positives/false negatives).
- Số gateways offline không thể xác minh sau deploy.
- Khả năng rollback trên thiết bị thật.

**Không triển khai đồng loạt image lớn qua uplink giới hạn**: có thể làm nghẽn mạng nhà máy, khiến edgeHub không đẩy telemetry và disk cache hết chỗ.

### 10.5. Offline devices nhận thay đổi muộn

Thiết bị offline không thể thấy desired configuration mới ngay lập tức. Khi reconnect, edgeAgent sẽ sync trạng thái và thử reconcile theo chiến lược/runtime. Vì thế:

- Một bản deployment `v2` có thể đang chạy ở 90% fleet, còn 10% chưa cập nhật.
- Đánh giá **observed/reporting status** với khoảng thời gian thiết bị offline.
- Định nghĩa fleet rollout deadline, policy xử lý thiết bị mất liên lạc lâu dài.
- Duy trì backward-compatible message schemas trong thời gian có **nhiều module versions** cùng hoạt động.
- Không xóa image/tag cũ khỏi registry khi còn thiết bị offline có thể cần pull/rollback.

### 10.6. Tránh xung đột giữa direct và automatic deployments

Nếu quản trị viên vừa `set-modules` trực tiếp trên device vừa có automatic deployment targeting device, desired properties có thể được xử lý theo thứ tự/priority khiến kết quả không như mong đợi. Hãy chọn **một source of truth và chiến lược quản lý nhất quán** cho mỗi fleet, ghi deployment IDs và intended effective config.

## 11. Module twins: desired vs reported và cập nhật cấu hình

IoT Hub cung cấp **device twins và module twins** để lưu metadata/configuration/observed state. Đây không phải hệ thống database transactions bảo đảm mọi value được apply tức thì.

### 11.1. Desired và reported properties

~~~json
{
  "properties": {
    "desired": {
      "thresholdC": 35.0,
      "samplingIntervalSecs": 10
    },
    "reported": {
      "appliedThresholdC": 35.0,
      "configVersion": "v3",
      "lastAppliedUtc": "2026-11-20T09:10:00Z"
    }
  }
}
~~~

Đây là **minh họa hai mặt của một twin**. Trong thực tế IoT Hub còn quản lý metadata, `$version` và other fields; không tự xây một request update twin bằng JSON này mà thiếu cách patch/version kiểm soát.

- **Desired:** cloud mong muốn module áp dụng ngưỡng 35°C.
- **Reported:** module cho biết nó đã thật sự áp dụng hay chưa (do code cập nhật).
- **Versioning/ack:** tránh xem desired value mới là proof runtime đã áp dụng.

### 11.2. Module twin không tự restart process

Manifest ở phần 8 đặt ngưỡng trong `env.TEMP_THRESHOLD_C`. Code filter đọc env **một lần khi khởi động**. Nếu thay `telemetryFilter.properties.desired.thresholdC`, code hiện tại **không thay đổi hành vi** vì chưa đăng ký callback xử lý twin desired changes.

Để hỗ trợ dynamic configuration:

1. Định nghĩa schema desired properties và validation ranges.
2. Khi start, đọc current desired twin (từ SDK) và apply default hợp lệ.
3. Đăng ký callback nhận desired changes.
4. Apply cấu hình an toàn, tránh trạng thái nửa chừng.
5. Update reported properties với version/ack/error.
6. Có fallback nếu config invalid/out-of-range.
7. Khi offline, dùng last known valid configuration; reconcile sau reconnect.

**Đừng đưa secret vào module twin desired properties**: đây không phải kho bí mật chuyên dụng. Dùng cơ chế secrets/host provisioning được phê duyệt.

### 11.3. Direct methods vs cloud-to-device messages

| Cơ chế | Phù hợp | Rủi ro |
|---|---|---|
| **Desired properties** | Cấu hình trạng thái mong muốn (threshold, interval) | Device offline áp dụng trễ |
| **Reported properties** | Health/state, firmware/module version đã áp dụng | Device phải tự báo; dữ liệu có thể cũ |
| **Direct methods** | Yêu cầu thao tác theo request-response khi device/module online | Timeout/offline; không xem lời gọi là durable command |
| **Cloud-to-device messages** | Thông điệp từ cloud đến device theo API/hạn chế IoT Hub | TTL/queue/offline semantics cần thiết kế |
| **Telemetry D2C** | Events từ device lên cloud | Có thể trễ/trùng, không là transaction commit ack |

Không dùng direct method để điều khiển cơ cấu công nghiệp an toàn khi device có thể offline hoặc timeout; local control cần cơ chế fail-safe riêng.

### 11.4. Theo dõi desired/reported config drift

Một fleet khỏe cần chỉ số:

~~~text
Expected image:      telemetry-filter@sha256:abc...
Reported image:      telemetry-filter@sha256:abc...
Expected threshold:  35.0 °C
Reported threshold:  35.0 °C
Last report:         within health window
Recent errors:       0
~~~

Nếu desired mới 35°C nhưng reported vẫn 37°C suốt nhiều giờ, hãy kiểm tra offline status, callback handling, module version và update failures trước khi tuyên bố cấu hình đã áp dụng.

## 12. edgeHub routing: cloud telemetry, local processing và leaf devices

### 12.1. Hướng dữ liệu

| Nguồn | Đích | Mục đích |
|---|---|---|
| Simulator module output | Filter module input | Tiền xử lý local |
| Filter module output | `$upstream` | Chỉ gửi events phù hợp lên IoT Hub |
| Leaf device telemetry | Edge module input | Adapter/gateway lọc dữ liệu leaf |
| Module output | Module input khác | Chuỗi local modules, ví dụ decode → detect → aggregate |
| Module output | Local storage | Durable queue/buffer tự triển khai khi cần |

**edgeHub route name** chỉ là ID cấu hình; điều quyết định data đi đâu là expression `FROM ... INTO ...` và output/input path chính xác. Đặt tên rõ: `rawToFilter`, `filteredToCloud`, `failedToQuarantine`.

### 12.2. Input/output names

~~~text
FROM /messages/modules/sensorSimulator/outputs/temperatureOutput
INTO BrokeredEndpoint("/modules/telemetryFilter/inputs/input1")

FROM /messages/modules/telemetryFilter/outputs/filtered
INTO $upstream
~~~

**Module ID và output name có phân biệt chữ hoa/thường trong routing** theo cách chúng được khai báo; cần nhất quán. IoT Edge message routing expression không phải SQL query; nếu dùng `WHERE` để lọc theo message properties, hãy kiểm tra cú pháp và xem properties đã gắn vào message hay chưa.

### 12.3. Leaf devices sau gateway

Một thiết bị nhỏ không thể chạy IoT Edge có thể kết nối như **downstream device** qua gateway. Khi đó:

- Gateway cần hỗ trợ client protocol/endpoints và certificate chain phù hợp.
- Leaf device phải tin gateway certificate theo cơ chế hợp lệ, không tắt certificate validation.
- Child/parent relationship hoặc gateway setup ở IoT Hub cần cấu hình chính xác theo mô hình được hỗ trợ.
- Network inbound đến edgeHub từ local devices phải được giới hạn ở site network.
- Parent gateway mất nguồn điện có thể làm tất cả leaf devices mất kết nối cloud.

**Không mở 8883/5671/443 toàn Internet tới gateway** chỉ vì downstream devices cần MQTT/AMQP/HTTPS. Local segmentation, TLS, device identity và firewalls là bắt buộc theo threat model.

### 12.4. Route design và privacy

Nếu dữ liệu có video frames hoặc identifiers nhạy cảm, chỉ forward một tập fields đã phân loại. Ví dụ:

~~~json
{
  "eventId": "evt-001",
  "site": "factory-a",
  "deviceId": "sensor-01",
  "timestamp": "2026-11-20T09:20:00Z",
  "eventType": "HighTemperature",
  "temperatureC": 39.1
}
~~~

Đây là event tổng hợp, không chứa raw video/audio. Nhưng `site`/`deviceId` vẫn có thể là thông tin vận hành nhạy cảm; áp retention và authorization phía cloud.

## 13. Hoạt động offline và store-and-forward

Một nhà máy không thể phụ thuộc việc IoT Hub luôn truy cập được. **Offline-first design** là khác biệt quan trọng giữa ứng dụng edge và dịch vụ cloud thông thường.

### 13.1. Ba tình trạng mạng

| Trạng thái | Điều gì xảy ra? | Thiết kế cần có |
|---|---|---|
| **Online** | Module phát, edgeHub forward lên IoT Hub | TLS/auth, routes, monitoring |
| **Offline ngắn** | edgeHub có thể lưu eligible messages; modules local tiếp tục chạy | TTL và disk đủ, retries, graceful degraded mode |
| **Offline dài** | Backlog tăng; TTL hết, disk đầy, identity/clock/cert có thể gặp vấn đề | Drop policy, local retention, alerts, maintenance và manual recovery |

**Store-and-forward không làm IoT Edge trở thành durable message broker vô hạn**. Với sự kiện phải giữ lâu hơn TTL hoặc không thể mất, ứng dụng cần **local durable store** (ví dụ SQLite có transaction, hàng đợi local bền vững) và cơ chế phát lại/idempotency được kiểm chứng riêng.

### 13.2. Tính kích thước backlog

Giả sử một gateway sau khi lọc phát:

~~~text
10 messages/second
1 KiB encoded payload mỗi message
Offline window: 6 hours
~~~

Ước tính payload thô:

\[
10 \times 1024 \times 6 \times 3600
=221{,}184{,}000\ \text{bytes}\approx211\ \text{MiB}.
\]

Con số này **chưa tính** message headers/properties, MQTT/AMQP protocol overhead, edgeHub storage metadata, filesystem, logs hoặc số lần gửi lại. Dự toán disk cần dựa vào **đo đạc thực**, có headroom cho image pulls/updates và log rotation. Nếu ba modules khác cũng giữ backlog, phải tính **tổng disk usage**.

### 13.3. TTL không tương đương disk quota

Trong manifest:

~~~json
{
  "storeAndForwardConfiguration": {
    "timeToLiveSecs": 7200
  }
}
~~~

TTL `7200` là **2 giờ**. Nếu muốn giữ đến 6 giờ, cần tăng theo yêu cầu (ví dụ 21600 giây) và **đảm bảo storage capacity**; chỉ tăng TTL không tạo thêm disk. Một số runtime/storage implementation có limits khác; khi offline dài hơn TTL, messages có thể hết hạn.

**Ví dụ cấu hình trên chỉ là fragment** bên trong `$edgeHub.properties.desired`, không phải manifest đầy đủ. Không suy rằng TTL 2 giờ bảo đảm delivery đúng thời điểm reconnect nếu thiết bị không có disk đủ hoặc backend không nhận.

### 13.4. Giữ local storage ổn định

Với edgeHub persistence, cấu hình storage/bind mount/volume phải theo đúng **IoT Edge runtime version** và filesystem permission của host/container:

- Chọn dedicated path/volume có đủ dung lượng và độ bền phù hợp.
- Đảm bảo container user có quyền đọc/ghi nhưng không root toàn host.
- Đặt log rotation để log không chiếm hết partition buffer.
- Giám sát free disk, inode, errors và write latency.
- Xem xét SSD wear, mất nguồn đột ngột, journal/file corruption.
- Bảo vệ dữ liệu lưu cục bộ nếu thiết bị có thể bị mất cắp.

**Không copy một ví dụ Docker bind mount của IoT Edge 1.1** vào runtime mới mà không xem storage-folder contract. Một volume mount sai có thể khiến messages không được persist như kỳ vọng.

### 13.5. Offline không đồng nghĩa mất khả năng xử lý local

Nếu route module-to-module không cần cloud thì:

~~~text
sensorSimulator -> edgeHub -> telemetryFilter
WAN / Internet disconnected
telemetryFilter vẫn có thể phân loại nhiệt độ và sinh cảnh báo local,
miễn runtime/containers và local dependencies vẫn khỏe.
~~~

Đây là điểm mạnh của edge, nhưng cần **test thật trên thiết bị**: cloud SDK có thể bị block khi xác thực/khởi tạo, DNS đến local broker sai hoặc application code có dependency tới cloud. Không chỉ tháo dây mạng rồi thấy container vẫn chạy mà kết luận logic đang xử lý đủ.

### 13.6. Thiết kế event idempotency

Khi uplink phục hồi, một event có thể được gửi lại. Consumer ở Azure nên nhận diện duplicate:

~~~json
{
  "eventId": "sensor-01/2026-11-20T09:20:01.123Z/42",
  "deviceId": "sensor-01",
  "originalTimestamp": "2026-11-20T09:20:01.123Z",
  "processedTimestamp": "2026-11-20T09:25:03.456Z",
  "type": "HighTemperature",
  "temperatureC": 38.7
}
~~~

Ví dụ đặt `eventId` dạng composite; cần thiết kế để **unique qua reboot/clock skew**, có thể dùng sequence persist/UUID. Downstream dùng dedup store có TTL đủ, tránh đếm hai lần alert/tạo hai phiếu bảo trì. **`eventId` là field ứng dụng, edgeHub không tự tạo idempotency bảo đảm exactly-once end-to-end.**

### 13.7. Khi không thể mất event

Một sự kiện kiểm toán hoặc ghi nhận an toàn có yêu cầu pháp lý nên:

1. Ghi vào **local durable append log/queue** có checksums.
2. Chỉ đánh dấu “đã gửi” sau khi nhận **application-level acknowledgement** theo contract.
3. Persist offset/checkpoint và retry khi reconnect.
4. Dedupe ở cloud theo event ID.
5. Có quy trình reconcile/replay/khôi phục local disk.
6. Định nghĩa RPO/RTO và kiểm thử mất điện, không chỉ ngắt Internet.

EdgeHub TTL đơn lẻ không bảo đảm yêu cầu này. Với điều khiển an toàn, cần local fail-safe systems độc lập.

## 14. Bảo mật IoT Edge theo nhiều lớp

**Thiết bị Edge thường nằm ngoài datacenter**: nhân viên bảo trì, nhà thầu hoặc đối tượng tấn công có thể có tiếp cận vật lý. Do đó bảo mật không dừng ở việc “IoT Hub dùng TLS”.

### 14.1. Chuỗi tin cậy

~~~mermaid
flowchart TB
    ROOT[Secure boot / hardware trust when available] --> OS[Patched host OS and container engine]
    OS --> ID[Device identity and certificate/key store]
    ID --> RUNTIME[IoT Edge runtime]
    RUNTIME --> IMAGES[Approved signed/scanned module images]
    IMAGES --> PERMS[Least-privilege container isolation]
    PERMS --> DATA[Encrypted/authenticated local and cloud data paths]
    DATA --> AUDIT[Health, audit, rotation, incident response]
~~~

**Không có một công tắc Azure Policy duy nhất bảo vệ tất cả lớp**. Azure RBAC, IoT Hub identity, local OS users, ACR pull access, app secrets và network segmentation phải có owner rõ.

### 14.2. Device identity và certificate rotation

- Mỗi device có **identity riêng** với IoT Hub hoặc DPS enrollment phù hợp.
- Ưu tiên attestation **X.509/TPM/HSM** khi hỗ trợ và có vận hành PKI; không chia sẻ symmetric key giữa sites.
- Có kế hoạch certificate expiry/rotation trước thời hạn.
- Quản lý clock/NTP; lệch giờ có thể khiến TLS/SAS signatures không hợp lệ.
- Thu hồi identity của thiết bị bị đánh cắp, hỏng hoặc chuyển quyền sở hữu.
- Cập nhật parent/leaf certificates nếu thiết kế downstream gateway.

**Đổi certificate/IoT Hub assignment có thể làm mất kết nối hàng loạt** nếu rollout sai. Kiểm tra canary và duy trì fallback/maintenance procedure có bảo mật.

### 14.3. Registry và module supply chain

| Rủi ro | Kiểm soát |
|---|---|
| Image bị thay sau khi tag reuse | Pin **digest sha256**, dùng immutable tags và release approvals |
| Secrets nhúng vào image | CI secrets scanning, không `COPY .env` vào Docker build context |
| Image có CVE | SBOM, image vulnerability scans, rebuild base image định kỳ |
| ACR credentials bị lộ | Least-privilege pull, rotate credentials, secure delivery to edgeAgent |
| Module vượt quyền host | Non-root, no privileged mode, hạn chế capabilities/mounts |
| Thiết bị ARM dùng image AMD64 | Multi-arch builds/manifest và native hardware tests |
| Cập nhật phá schema | Versioned messages, backward compatibility, staged rollout |
| Image quá lớn | Layer optimization, bandwidth budgets, local cache sizing |

Trong manifest minh họa sử dụng image tag dễ đọc. Ở production, nên khóa image bằng **digest** theo cách container runtime/manifest hỗ trợ. Khi rollback, digest giúp phân biệt release chính xác thay vì phụ thuộc tag đã được ghi lại.

### 14.4. Environment variables và secrets

`env` trong deployment manifest hữu ích cho **không nhạy cảm** như threshold, sampling interval hoặc feature flag. Nó **không phải secret vault**; người có quyền xem desired configuration hoặc inspect container có thể thấy giá trị. Không đặt:

- IoT Hub device connection string;
- ACR admin password;
- Database connection string kèm mật khẩu;
- Azure service principal client secret;
- API token dài hạn;
- Private key/certificate plaintext.

Với secret thật, dùng giải pháp **host secret provisioning/encrypted storage, identity access hoặc cơ chế injection được phê duyệt và hỗ trợ cho runtime**. Không tuyên bố IoT Edge có cùng Kubernetes Secret API hoặc luôn có Azure Key Vault network path.

### 14.5. Least privilege container runtime

Nên:

- Chạy app bằng **non-root UID**.
- Chỉ bind mount những thư mục/thiết bị thật sự cần.
- Dùng resource limits để một module không lấy hết RAM/CPU của edgeHub.
- Hạn chế network egress tới các endpoints hợp lệ; không mở Docker API.
- Tránh `privileged: true` và `--network host` trừ khi có review bắt buộc.
- Tách module đọc camera khỏi module đẩy cloud nếu cần ranh giới dữ liệu.
- Bật log rotation và không log raw credentials/frames chứa PII.

**Một module bị compromise có thể gây ảnh hưởng toàn gateway** nếu được cấp Docker socket hoặc privileged mounts. Coi gateway là môi trường đa thành phần cần isolation, không phải “mọi container đều đáng tin”.

### 14.6. Mạng và TLS

Với Internet uplink, IoT Hub/DPS/ACR thường sử dụng TLS. Proxy/firewall của nhà máy có thể chặn SNI, certificate chain, DNS và shard connection. Không tắt certificate verification hoặc mở toàn bộ outbound Internet chỉ vì thiếu route.

Với leaf devices, bật TLS/client authentication phù hợp, phân đoạn VLAN/subnets và chặn inbound từ Internet. Nếu data cần đi qua private network/ExpressRoute/VPN, thiết kế từ gateway đến Azure endpoints và các giới hạn dịch vụ cụ thể; một Edge container không tự biến tất cả IoT Hub traffic thành Private Link.

### 14.7. Module code nhận dữ liệu không tin cậy

Dữ liệu sensor cũng có thể bị giả mạo hoặc hỏng:

~~~json
{
  "eventId": "fake-001",
  "temperatureC": 9999999,
  "timestamp": "2100-01-01T00:00:00Z"
}
~~~

Đừng cho phép payload này kích hoạt thao tác nguy hiểm mà không có validation bounds, sensor identity, calibration và local safety checks. Với thiết bị công nghiệp, **business alarm và safety-critical shutdown** cần được tách và kiểm chứng theo tiêu chuẩn ứng dụng.

## 15. Monitoring edge runtime, modules và IoT Hub

Nếu một module “running” nhưng không sinh dữ liệu trong 2 giờ, dashboard chỉ nhìn container status có thể báo xanh sai. Monitoring nên quan sát **fleet, runtime, messages, cloud connection và business outputs**.

### 15.1. Các tầng health

| Tầng | Signals | Ví dụ alert |
|---|---|---|
| **Device host** | CPU, RAM, disk, NTP, filesystem errors, nhiệt độ gateway | Disk còn dưới ngưỡng, clock drift |
| **edgeAgent** | Running modules, restart count, desired/reported drift | Module crash loop/image pull failed |
| **edgeHub** | Local messages routed, upstream status, queue/backlog/drop | Offline backlog tăng, expired messages |
| **Application modules** | Input/output counts, invalid payload rate, processing latency | Filter không nhận messages dù sensor chạy |
| **IoT Hub** | Connected devices, device-to-cloud messages, throttling | Fleet disconnected, quota gần giới hạn |
| **Consumer pipeline** | Event Hubs/Function/ADX ingestion lag, errors | Device phát nhưng cloud không nhận |
| **Business** | Alert timeliness, false positives/missed events | Cảnh báo nhiệt độ chậm hơn SLO |

### 15.2. Các lệnh chẩn đoán trên thiết bị

~~~bash
# Trên gateway lab, quyền phù hợp. Tập trung read-only.
sudo aziotctl check
sudo iotedge system status
sudo iotedge list
sudo iotedge logs edgeAgent --tail 100
sudo iotedge logs edgeHub --tail 100
sudo iotedge logs sensorSimulator --tail 100
sudo iotedge logs telemetryFilter --tail 100
~~~

Nếu có thể, kiểm tra cả **container engine** theo chính sách (ví dụ xem disk/image state), nhưng không tự chạy prune mọi images trong production. Runtime logs có thể chứa connection details hoặc identifiers; lọc secrets trước khi chia sẻ.

### 15.3. Metrics collector và Azure Monitor

Một số phiên bản IoT Edge có hỗ trợ **edgeAgent/edgeHub metrics endpoints** và giải pháp metrics collector để đưa metrics vào Azure Monitor/Log Analytics. Việc cấu hình metric collector, endpoints, authentication và outbound cost **không mặc nhiên có sẵn**; phải triển khai/duyệt theo version, network và bảo mật.

Metrics nên có:

~~~text
device_online
module_running
module_restart_count
edgehub_upstream_connected
edgehub_messages_sent_total
edgehub_messages_dropped_or_expired_total
edgehub_store_queue_depth
local_disk_free_bytes
module_input_messages_total
module_output_messages_total
last_telemetry_event_age_seconds
deployment_reported_version
~~~

**Đây là danh sách metric mục tiêu**, không phải khẳng định mọi tên trên tồn tại y nguyên trong endpoint của IoT Edge. Một số phải được app modules tự instrument hoặc suy ra ở backend. Kiểm tra tên Prometheus metrics/dimensions thực của runtime.

### 15.4. Cloud monitoring có thể thiếu khi offline

Khi gateway mất mạng, IoT Hub/Azure Monitor thấy **không có dữ liệu mới**, không tự nhìn được đầy đủ trạng thái local. Cần:

- Local log/metrics retention và remote shipping sau reconnect.
- Last-seen timestamp và xác định “offline” riêng với “module hỏng”.
- Alert theo **expected reporting cadence** từng thiết bị.
- Fleet maintenance procedures nếu không reconnect lâu ngày.
- Phân biệt **clock skew** làm timestamp nhìn “tương lai” với thiết bị thực đang khỏe.

**Không coi “0 alerts” là chắc chắn thiết bị không nóng** khi uplink offline và edgeHub queue tràn. Monitor cả **sự im lặng**.

### 15.5. Correlation IDs end-to-end

Ví dụ:

~~~text
EventId:    site-a/sensor-01/sequence-000042
DeviceId:   edge-gateway-lab-001
ModuleId:   telemetryFilter
Version:    1.0.0
EventTime:  2026-11-20T09:20:01Z
SentTime:   2026-11-20T09:20:02Z
IngestTime: 2026-11-20T09:27:15Z
~~~

Nếu uplink offline 7 phút, analytics dùng `EventTime` để hiểu lúc sensor đo, còn `IngestTime - EventTime` đo tổng trễ end-to-end. Không tính latency sensor bằng khoảng thời gian từ alert gửi đến Azure nếu nghiệp vụ yêu cầu **local reaction**.

### 15.6. Kịch bản kiểm thử health

1. **Tắt riêng uplink cloud**, xác minh local sensor → filter tiếp tục chạy.
2. **Reconnect** trong TTL, xác nhận backlog được forward và duplicates xử lý.
3. **Dừng custom module** trong môi trường test, xác minh edgeAgent restart/report.
4. **Chặn image pull** với registry test, kiểm tra deployment reported error.
5. **Gửi malformed JSON**, xác nhận module không crash loop.
6. **Giả lập disk pressure có kiểm soát** trên gateway lab, không làm đầy disk production.
7. **Nâng module version**, xác nhận rollout/reporting và rollback.
8. **Thử invalid cert/clock skew trong lab**, xác minh device báo lỗi auth thay vì bỏ TLS check.

Mỗi test cần bằng chứng: event IDs/metrics/logs trước–sau, người phụ trách, mức ảnh hưởng và cách khôi phục.

## 16. Troubleshooting: deployment accepted nhưng module không chạy

### 16.1. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| IoT Hub device identity có nhưng runtime không connect | Provisioning/cert/key/DPS/clock sai, firewall | `aziotctl check`, host DNS, IoT Hub name, expiry |
| edgeAgent container không chạy | Moby/runtime service lỗi, image pull host, disk | `iotedge system status`, runtime logs, disk |
| Module trạng thái `Backoff/Failed` | Container exit, command/permissions sai | `iotedge logs <module>`, createOptions |
| `manifest unknown`/`image not found` | Tag/digest sai hoặc image chưa push | ACR image references, registry endpoint |
| `unauthorized: authentication required` | Gateway thiếu registry pull permission | Credentials/ACR access, rotate secret |
| `exec format error` | CPU architecture khác image | `uname -m`, Docker manifest `linux/arm64`/`amd64` |
| Module running nhưng input rỗng | Route path/output name khác code | `$edgeHub.routes`, message counters |
| Module nhận input nhưng không forward | Temperature dưới threshold hoặc lỗi callback/output | App logs, sample payload, output route |
| EdgeHub online nhưng IoT Hub không có event | Route tới `$upstream` thiếu, cloud routing/consumer sai | edgeHub logs, IoT Hub monitor consumer |
| TLS/401/SAS expired | Certificate chain/clock/key/identity sai | Host time, cert trust, provisioning |
| IoT Hub throttled | IoT Hub tier/quota, burst traffic | Hub metrics, aggregate/scale/right-size |
| Disk usage tăng khi offline | TTL/backlog/host logs/images | Free space, retention, message rate |
| Mất dữ liệu sau offline lâu | TTL expire, disk full, reboot/storage không persistent | edgeHub storage policies, local durable store |
| Config twin đổi nhưng module không đổi hành vi | Code chỉ đọc env lúc start, không có twin callback | Desired vs reported/app behavior |
| Update chỉ đến một số devices | Offline/target tag/priority/old CLI trạng thái | Targeted deployments + reported state |
| Module crash sau rolling update | Module schema incompatible, required env missing | Versioned contract, canary logs, rollback |
| KPI 0 messages khi site mất Internet | Cloud thiếu data, không chứng minh sensor inactive | Local logs, last-seen/queue health |

### 16.2. Runbook tám lớp

**1. Scope/ownership:** đúng subscription, IoT Hub, device ID, deployment ID, target condition, ring, hardware architecture chưa?

**2. Device identity:** device provisioned/connected đúng hub; certificate/clock/DPS assignment có hợp lệ?

**3. Host/runtime:** OS/Moby/IoT Edge services, CPU/RAM/disk, edgeAgent/edgeHub running?

**4. Image:** image URI/tag/digest, ACR pull credentials, registry DNS/HTTPS, architecture compatible?

**5. Container config:** env, mounts, createOptions, startup command, user permissions, logs?

**6. Local routing:** edgeHub routes, named module outputs/inputs, app callback và payload schema?

**7. Cloud delivery:** edgeHub upstream connection, store queue, IoT Hub routing/consumer, quota/ingest lag?

**8. Business verification:** sensor event đến đúng thời điểm, filter không bỏ cảnh báo, duplicates xử lý, dashboards không dựa vào dữ liệu cũ?

### 16.3. Tình huống: image không tương thích ARM64

~~~text
Desired:
  telemetryFilter image: ...:2.0.0
Gateway:
  architecture: linux/arm64
Built image:
  linux/amd64 only
Observed:
  container cannot execute binary / exec format error
~~~

**Khắc phục:** build multi-platform image đúng kiến trúc, scan, push tag/digest mới, rollout canary. Không thay image registry về public bừa hoặc bật privileged mode để sửa kiến trúc sai.

### 16.4. Tình huống: route sai một ký tự

~~~text
App emits:  temperatureOutput
Route:      .../outputs/temperatureoutput
Result:     no messages delivered to filter input1
~~~

Module `sensorSimulator` và `telemetryFilter` có thể đều running. Khắc phục ở **route/output name**, không tăng CPU hoặc xóa IoT Hub. Thêm contract test/manifest lint để phát hiện lệch tên trước production.

### 16.5. Tình huống: offline 4 giờ, TTL chỉ 2 giờ

Nếu edgeHub chỉ giữ messages hợp lệ 2 giờ trong khi mạng mất 4 giờ, events cũ có thể bị loại. Nâng TTL sau sự cố **không phục hồi messages đã hết hạn**. Cần đánh giá data loss, local backup nếu có, tối ưu uplink và tăng TTL/disk theo RPO đã phê duyệt trước lần tiếp theo.

### 16.6. Tình huống: sensor chạy nhưng cloud không còn cập nhật

Tách:

- Local sensor → module: có events không?
- Filter → edgeHub: có outputs không?
- edgeHub → IoT Hub: upstream connected hay backlog?
- IoT Hub → Event Hubs/Functions: routing và consumer còn hoạt động?
- Azure Data Explorer/Monitor: dữ liệu có đang ingest hay dashboard query khoảng thời gian sai?

Không thay module khi lỗi ở consumer cuối; điều tra từng chặng bằng eventId/timestamp và metrics.

## 17. CI/CD và chính sách thay đổi module an toàn

Một module mới cần qua **source control, build, security scan, kiểm thử môi trường biên, review manifest và rollout**. Việc đổi `docker tag` trên cloud không đơn giản như thay image của App Service vì thiết bị Edge có thể offline, CPU architecture khác nhau và uplink chậm.

### 17.1. Pipeline tổng quan

~~~mermaid
flowchart LR
    PR[Pull request source + deployment manifest] --> TEST[Unit tests and schema/route tests]
    TEST --> BUILD[Build multi-architecture container]
    BUILD --> SCAN[SBOM / vulnerabilities / image provenance]
    SCAN --> ACR[Push immutable image/digest to ACR]
    ACR --> LAB[Deploy lab gateway]
    LAB --> OFF[Offline/reconnect and load tests]
    OFF --> APPROVE[Security and Operations approval]
    APPROVE --> CANARY[Target small device ring]
    CANARY --> SCALE[Progressively target fleet]
    CANARY -. Unexpected errors .-> ROLLBACK[Restore last approved manifest/digest]
~~~

Đầu vào pipeline:

- Code module và tests.
- Dockerfile, lockfile/requirements.
- Message schema có version và backward compatibility.
- Deployment template có routes/env/createOptions theo mỗi site.
- Device target condition/priority hoặc list IDs đã phê duyệt.
- Image digest approved sau scan.
- Rollback artifact và monitoring thresholds.

### 17.2. Golden tests ở 3 lớp

| Test | Điều kiểm tra |
|---|---|
| **Unit** | Nhiệt độ ≥35 được forward, dưới 35 không forward, JSON lỗi được xử lý |
| **Integration local** | edgeHub route output → input → upstream, module identities |
| **End-to-end device** | Trên gateway đúng architecture, offline/reconnect, disk/CPU, cloud event |

Unit test của hàm so sánh nhiệt độ không thay được **tích hợp IoT Edge SDK và edgeHub**. Nếu test Docker container chạy trên laptop không có IoT Edge runtime, cần mocks/Edge test environment và không coi đó là chứng minh device đã có credentials.

### 17.3. Rollback module

Khi `telemetryFilter:2.0` tạo false positives:

1. Tạm dừng promotion sang rings tiếp theo.
2. Xác định affected devices và build digest thực đã deploy.
3. Khôi phục desired image/config từ **last known good manifest** được lưu trong Git.
4. Chờ device reconnect và edgeAgent reconcile; không giả định rollback tức thì khi offline.
5. Kiểm tra running/reporting version và actual high-temp event behavior.
6. Theo dõi schema compatibility của events đã gửi trong thời gian version lỗi.
7. Xác định data recovery/reconciliation nếu alert pipeline đã tạo ticket/action sai.

**Rollback container không tự “undo” dữ liệu/sự kiện đã được gửi** hoặc thiết bị bị điều khiển sai trong thời gian lỗi. Với dữ liệu quan trọng cần event versioning, dedup và compensating actions.

### 17.4. Không tự prune toàn bộ images

Gateway có disk hạn chế. Cần cleanup images cũ sau rollout, nhưng **không xóa last-known-good image trước khi tất cả sites đã xác nhận khả năng khôi phục**. Disk pressure có thể đến từ image layers, logs, edgeHub store và model weights; dùng inventory để quyết định, không chạy `docker system prune -a` trên fleet theo lịch mù quáng.

### 17.5. Dev, staging và production khác nhau

- **Dev:** có thể dùng local Edge test/devices lab, simulator và test registry.
- **Staging:** hardware giống production, mạng proxy/TLS/telemetry load tương đương.
- **Production:** pinned images/digests, staged rollout, offline recovery, change window và audit.

Không dùng cùng IoT Hub service policies hoặc cùng production certificates trong mọi môi trường. Nếu vì vận hành cần dùng chung Hub, phải có device tagging/RBAC/quota isolation và approval rõ ràng.

## 18. Tính sẵn sàng và khả năng phục hồi của gateway

Một IoT Edge gateway không tự có HA giống Azure zone-redundant service. Nếu gateway duy nhất mất nguồn điện, các leaf devices phụ thuộc có thể mất đường lên cloud dù IoT Hub vẫn khỏe.

### 18.1. Failure modes

| Failure | Ảnh hưởng | Mitigation |
|---|---|---|
| **Mất Internet** | Cloud events trễ | Local processing + store-and-forward TTL/disk |
| **Mất điện gateway** | Runtime dừng, local queue có thể bị ảnh hưởng | UPS, durable storage, khởi động lại an toàn |
| **Disk hỏng** | Mất cached messages/images/logs | Backup/careful rebuild, durable events nếu cần |
| **Host OS lỗi** | Tất cả modules mất | Golden OS image, immutable config, spare gateway |
| **edgeHub lỗi** | Module routes/upstream bị ảnh hưởng | Monitoring, restart policy, rollback runtime |
| **ACR unavailable** | Không pull được image mới | Pin/cached good image, stage updates trước khi cần |
| **IoT Hub quota/throttling** | Upstream chậm/thất bại | Capacity planning, backoff, aggregate/filter |
| **Device identity revoked/expired** | Không xác thực cloud | Identity rotation/re-provisioning plan |
| **Sensor hỏng** | Sai dữ liệu dù edge vẫn running | Device calibration, range checks và sensor health |

### 18.2. RPO/RTO phụ thuộc use case

Ví dụ:

~~~text
Temperature dashboard:
  Accept up to 5 minutes cloud lag.
  Raw normal readings may be summarized.
  Alerts require local audible signal even offline.

Industrial audit log:
  No intentional loss within 48 hours of WAN outage.
  Requires durable local log, checksums, replay, acknowledgments.
~~~

Hai use case không thể dùng cùng một câu “edgeHub TTL 2 giờ là đủ”. RPO/RTO phải được xác định theo tính chất dữ liệu, khả năng local storage và chính sách an toàn.

### 18.3. Redundant gateways

Một số hệ thống triển khai **spare gateway/hot standby** ở site. Nhưng hai gateway cùng đọc một sensor/đẩy cùng event có thể tạo duplicates, race và ownership conflict. Cần:

- Quản lý primary/secondary và lease/fencing theo thiết kế site.
- Sensor connection failover rõ, không vừa điều khiển vừa phát cảnh báo trùng.
- Device identities riêng, IoT Hub routing và dedup.
- Đồng bộ cấu hình, image digests/certificates và local data recovery.
- Test failover thật với uplink và local switch/PLC.

**Không mặc định “deploy cùng module lên hai Edge devices” là tự động có high availability**. Azure IoT Edge không thay hệ thống HA công nghiệp cần thiết kế riêng.

### 18.4. Disaster recovery cloud

Nếu IoT Hub hoặc region Azure có sự cố:

1. Edge local processing có tiếp tục không?
2. Module có hardcode một cloud endpoint bị hỏng không?
3. DPS/provisioning/multi-region strategy có được thiết kế/test không?
4. Data replay từ local store có đủ thời gian không?
5. Khi chuyển hub, device identities/registrations và cloud consumers đã sẵn sàng chưa?
6. Có bảo đảm no cross-site duplicate không?

Không coi DPS tự động chuyển mọi thiết bị qua region khác mà không cần enrollment/configuration/business recovery plan. Recovery phải được diễn tập với số devices/vùng đại diện.

## 19. Chi phí và capacity planning: tiết kiệm băng thông nhưng không miễn phí

Azure IoT Edge runtime là thành phần chạy ở thiết bị, nhưng giải pháp tổng thể có thể tạo chi phí từ **IoT Hub, DPS/identity operations, ACR, dữ liệu gửi/nhận, Event Hubs, Storage/ADX, monitoring, network và phần cứng**. Edge filtering giúp giảm băng thông và ingestion nếu được thiết kế đúng; nó **không mặc định giảm tổng chi phí**.

### 19.1. Những thành phần cần dự toán

| Chi phí | Ghi chú |
|---|---|
| **Hardware gateway** | CPU/RAM/SSD/TPM, nhiệt độ công nghiệp, bảo hành, spare device |
| **OS/operations** | Cài đặt, vá lỗi, bảo mật, remote maintenance, onsite support |
| **IoT Hub tier/units** | Số messages, quotas, device identities/features và throughput |
| **DPS (nếu dùng)** | Provisioning/enrollment/các thao tác có phí tùy mô hình |
| **Container Registry** | Storage, pull traffic/network, scanning và CI builds |
| **Networking** | WAN, VPN/ExpressRoute, firewall/proxy, egress/inter-region |
| **Streaming/processing** | Event Hubs, Functions/Container Apps, Service Bus nếu dùng |
| **Data/analytics** | Blob, Azure Data Explorer, Log Analytics và retention |
| **Monitoring/DR** | Metrics/logs, alerts, backup/replay, test fleet và spare hardware |

Không đưa giá cố định USD/GB hoặc USD/message vào bài vì **giá/quotas phụ thuộc region, tier, date và pricing model**. Kiểm tra Azure Pricing Calculator và quota documents ở thời điểm quyết định.

### 19.2. Dự toán số sự kiện trước và sau lọc

Giả sử:

~~~text
100 gateways
5 leaf sensors / gateway
1 event / second / sensor
Payload raw average 500 bytes / event
Edge filtering retains 5% events as alerts/summary
Seconds / day: 86,400
~~~

Số raw events/ngày:

\[
100 \times 5 \times 1 \times 86{,}400
=43{,}200{,}000 \ \text{events/ngày}.
\]

Tổng raw bytes/ngày:

\[
43{,}200{,}000 \times 500
=21{,}600{,}000{,}000 \ \text{bytes}
\approx21.6 \ \text{GB/ngày}.
\]

Nếu chỉ **5%** events đi cloud, số sự kiện:

\[
43{,}200{,}000 \times 0.05
=2{,}160{,}000 \ \text{events/ngày}.
\]

Raw payload logic giảm khoảng **95%**, nhưng **không suy** billing của IoT Hub là 2.16 triệu messages/ngày: IoT Hub có định nghĩa billable messages/size blocks và các loại operations/tier khác nhau. Cần tính theo **size thực sau encoding, rounding/quotas, routes, retries và pricing tier**. Cũng không quên messages dùng cho system/control, diagnostics và module deployment.

### 19.3. Băng thông upload trong giờ reconnect

Giả sử một site backlog 1 GiB, WAN upload ổn định thực tế 2 Mbps. Thời gian lý thuyết chưa overhead:

\[
\frac{1\ \text{GiB}\times8}{2\ \text{Mb/s}}
\approx 4{,}295\ \text{giây}\approx72\ \text{phút}.
\]

Đây là phép tính **gần đúng** với sự khác biệt GiB/Mb và không xét traffic mới, ACK/retries, quota IoT Hub hoặc network protocol. Nếu thiết bị tiếp tục gửi 0.8 Mbps dữ liệu mới thì băng thông còn lại để xả backlog nhỏ hơn nhiều. **TTL 2 giờ có thể không đủ** nếu WAN gián đoạn dài và catch-up chậm.

### 19.4. Hiệu năng của hardware

Module lọc JSON đơn giản có thể chạy trên CPU nhỏ; video analytics/AI inference có thể cần GPU/NPU và model optimization. Cần benchmark:

1. **Messages/second** xử lý local và output sau lọc.
2. CPU/RAM từng container, edgeHub và host.
3. p95/p99 **local processing latency**, không chỉ cloud ingest lag.
4. Disk write throughput và wear khi offline.
5. Băng thông/nén và chi phí Event Hubs/analytics sau lọc.
6. Khả năng pull image mới khi WAN chậm và disk gần đầy.
7. Nhiệt độ nguồn điện/thermal throttling theo môi trường thực.

Đừng chọn gateway chỉ vừa đủ chạy demo; cần capacity headroom cho system modules, retries, log collection, certificate rotation và cập nhật song song.

### 19.5. FinOps guardrails

- Dùng **resource tags** và owner cho IoT Hub/ACR/analytics.
- Theo dõi IoT Hub messages/quotas/throttling thực tế.
- Xác định **cost per active device/site** và cost per useful alert.
- Không gửi video/log raw không cần thiết lên cloud.
- Giới hạn debug log volume/retention.
- Tắt/xóa **tài nguyên cloud lab** đã được phê duyệt sau buổi học.
- Không xóa module/identity của thiết bị đang hoạt động chỉ để giảm phí.
- Theo dõi budget alerts; chúng **không** là spending hard cap.

**Bài toán tối ưu đúng:** giảm tổng chi phí và rủi ro vận hành **trên mỗi business event đáng tin**, không chỉ số bytes truyền lên IoT Hub.

## 20. Chọn Azure IoT Edge hay mô hình khác?

Trong hệ sinh thái Azure hiện có nhiều kiểu xử lý IoT. **Không phải mọi edge workload đều cần IoT Edge runtime.**

| Mô hình | Điểm mạnh | Khi nên cân nhắc |
|---|---|---|
| **IoT device → IoT Hub trực tiếp** | Cấu hình đơn giản, ít edge host cần quản trị | Thiết bị có thể tự kết nối, telemetry nhỏ và mạng ổn |
| **Azure IoT Edge modules** | Container modules, remote deployments, local routing/offline processing | Gateways Linux, cần local compute + fleet updates |
| **Azure IoT Operations trên Azure Arc-enabled Kubernetes** | Kiến trúc IoT edge dựa trên Kubernetes/Arc, có mô hình quản lý khác | Tổ chức đã dùng Arc/Kubernetes hoặc yêu cầu stack tương ứng |
| **Custom gateway service** | Kiểm soát chính xác hardware/protocol | IoT Edge không hỗ trợ OS/runtime hoặc yêu cầu rất đặc thù |
| **Cloud-only Event Hubs/Functions/ADX** | Compute/phân tích tập trung, dễ thay đổi cloud code | WAN tốt, không cần xử lý/decision offline |
| **PLC/RTOS local controller** | Bounded latency và safety logic theo phần cứng | Tác vụ real-time/safety-critical không phù hợp container/Linux |

### 20.1. IoT Edge khác Azure IoT Operations

Azure IoT Edge triển khai container modules do **edgeAgent/edgeHub** quản lý, dùng desired deployment/twins của IoT Hub.

Azure IoT Operations triển khai trên **Azure Arc-enabled Kubernetes**, quản trị các thành phần và giao thức theo kiến trúc khác. Hai sản phẩm có mục đích edge processing tương đồng nhưng **không dùng manifest/module twin và runtime giống nhau**. Không sao chép `modulesContent/$edgeAgent` rồi áp vào Azure IoT Operations.

### 20.2. Khi nào không cần container module?

- Một cảm biến đơn giản gửi vài events/phút và không cần xử lý local.
- Kết nối site luôn online, business latency chấp nhận cloud round-trip.
- Không có gateway/host đủ điều kiện cập nhật bảo mật.
- Đội ngũ chưa có năng lực vận hành OS/PKI/container images ở hàng nghìn sites.
- Tác vụ cần RTOS/PLC determinism hoặc certification.

Edge computing có giá trị khi **lợi ích cục bộ/offline/giảm băng thông vượt chi phí fleet operations và hardware**.

## 21. Case study: nhà máy có 200 gateways và hàng nghìn cảm biến

**Bối cảnh giả định:** Một doanh nghiệp sản xuất có 10 nhà máy, tổng cộng **200 IoT Edge gateways**. Mỗi gateway kết nối 30 cảm biến qua adapter công nghiệp. WAN giữa nhà máy và Azure có thể mất kết nối 2–6 giờ. Ban điều hành muốn thống kê xu hướng nhiệt độ/vibration theo vùng và cảnh báo bất thường, còn đội vận hành cần cập nhật module lọc trên từng ring của devices.

Yêu cầu:

- Local alarms hoạt động trong vòng vài giây kể cả khi Internet mất.
- Raw telemetry thông thường được tổng hợp 1 phút/lần; chỉ gửi sự kiện vượt ngưỡng hoặc summary.
- Không gửi dữ liệu chứa nhân dạng người/lộ camera raw lên cloud.
- Mỗi thiết bị có identity riêng, thu hồi được khi bị mất.
- Deployment theo **lab → canary → pilot → fleet**, có rollback.
- Offline queue 6 giờ với disk headroom, **không được coi là backup vĩnh viễn**.
- Azure cloud analytics tính p95 ingest lag và tỷ lệ alerts/site.
- Mọi thay đổi module/schema/threshold đều có version và owner.

### 21.1. Kiến trúc

~~~mermaid
flowchart TB
    subgraph SITE[Factory site]
      S[30 leaf sensors] --> ADAPT[Protocol adapter module]
      ADAPT --> HUB[edgeHub]
      HUB --> FILTER[Telemetry filter / aggregation module]
      FILTER --> HUB
      ALARM[Local alarm controller] <-->|Validated local event| FILTER
      AGENT[edgeAgent] -. manages .-> FILTER
      AGENT -. manages .-> ADAPT
      DISK[(Local disk / durable log)] -. offline buffer .-> HUB
    end
    HUB -->|HTTPS/MQTT TLS when online| IOT[Azure IoT Hub]
    DPS[DPS / device identity] -. provisioning .-> AGENT
    ACR[Azure Container Registry] -. image pull .-> AGENT
    IOT --> EH[Event Hubs / Function]
    EH --> ADX[Azure Data Explorer]
    EH --> BLOB[Blob archive]
    MON[Azure Monitor / SRE] -. diagnostics .-> IOT
    MON -. diagnostics .-> ADX
~~~

**Local alarm controller** trong hình là một hệ thống được thiết kế/cấp chứng nhận riêng; module telemetry filter chỉ có thể cung cấp **thông tin** cho nó theo contract, không thay cơ chế ngắt an toàn của nhà máy.

### 21.2. Device identity và phân nhóm

Mỗi gateway được gán tags:

~~~json
{
  "tags": {
    "environment": "prod",
    "site": "factory-b",
    "ring": "canary",
    "hardware": "arm64-v2",
    "dataClassification": "industrial-telemetry"
  }
}
~~~

Tags do cloud admin quản trị, không đặt các khóa bí mật vào tags. Deployment target chỉ những `hardware=arm64-v2` có image ARM64 tương ứng. Việc sử dụng tag `site` giúp kiểm tra mục tiêu rollout; vẫn phải inventory devices match condition trước apply.

### 21.3. Schema cho module output

~~~json
{
  "schemaVersion": 2,
  "eventId": "factory-b/gateway-17/seq-90873",
  "site": "factory-b",
  "gatewayId": "gateway-17",
  "sensorId": "motor-temp-07",
  "originalTimestamp": "2026-11-20T09:20:01Z",
  "processedTimestamp": "2026-11-20T09:20:02Z",
  "eventType": "HighTemperature",
  "temperatureC": 38.7,
  "quality": "validated"
}
~~~

Cloud consumer dùng `schemaVersion`, `eventId` và UTC timestamps để parse, dedup và đo độ trễ. Event schema thay đổi phải **tương thích với modules cũ** khi fleet rollout kéo dài nhiều ngày vì devices có thể offline.

### 21.4. Thiết kế store-and-forward

Mạng có thể mất 6 giờ; lựa chọn `timeToLiveSecs` phải xét 6 giờ **cộng thời gian bắt kịp backlog**, không chỉ đúng 21600 giây nếu ingestion sau reconnect chậm. Nhưng tăng TTL mà không tăng disk capacity/giảm message rate thì queue vẫn tràn. Với những events phải giữ không mất, thêm **local durable log và replay ack**.

Ở cloud, dashboard IoT Hub messages là **không đủ**: cần last-seen per gateway, offline queue/backlog/drop metrics và ingestion lag per site.

### 21.5. Rollout theo rings

~~~text
Ring 0: 2 lab gateways (1 amd64 + 1 arm64)
Ring 1: 10 canary gateways across several sites
Ring 2: 40 pilot gateways
Ring 3: 148 remaining gateways
~~~

Các con số chỉ minh họa nhóm 200 thiết bị. Mỗi bước kiểm tra:

1. Image pull success và module uptime.
2. Dữ liệu upstream đúng schema/tỷ lệ drop.
3. CPU/RAM/disk không vượt giới hạn.
4. Độ trễ local alert và cloud ingest lag.
5. Không có bất thường ở thiết bị/firmware/architecture khác.
6. Reconnect và **rollback** trên ít nhất một gateway đã update.

### 21.6. Sự cố: cập nhật filter khiến Cloud thấy 0 alerts

Một module phiên bản v2 đổi output name từ `filtered` thành `alerts` nhưng deployment vẫn giữ route `.../outputs/filtered INTO $upstream`.

Triệu chứng:

~~~text
edgeAgent reports: module running
module logs:       "HighTemperature forwarded" 
edgeHub route:     still expects output "filtered"
IoT Hub:           0 new alerts from affected devices
~~~

**Root cause:** output contract/route mismatch, không phải Azure SQL/IoT Hub quota. Mitigation là sửa route hoặc rollback image/manifest **cùng nhau**, sau đó xác minh event IDs đến cloud. Cần **manifest/schema contract tests** trong CI trước lần release tiếp theo.

### 21.7. Sự cố: WAN offline làm backlog vượt disk

Site A có uplink đứt 8 giờ, TTL chỉ 2 giờ và flash disk gần đầy. Sau reconnect, cloud chỉ nhận một phần events.

**Không thể sửa bằng cách kéo dài TTL sau sự cố.** Cần ghi incident data loss, đánh giá dữ liệu còn ở local durable store/raw sensors, ưu tiên gửi alerts hơn debug events trong tương lai, resize disk và thiết kế threshold/replay theo RPO.

### 21.8. Kết luận case study

Một hệ IoT Edge đáng tin là **thiết kế toàn chuỗi**:

~~~text
Device identity
  -> trusted host/runtime
  -> approved module images
  -> local adapter/edgeHub/filter routes
  -> bounded offline storage
  -> secure IoT Hub delivery
  -> cloud ingestion and analytics
  -> SLO/incident evidence and rollback
~~~

Nếu chỉ có manifest được IoT Hub chấp nhận mà không chứng minh route, offline behavior, image architecture và business SLO thì chưa thể coi site đã triển khai thành công.

## 22. Bài thực hành tổng hợp: triển khai và xác minh một module tại thiết bị

**Đề bài:** Bạn được cấp **một IoT Hub lab, một IoT Edge device Linux, một ACR lab và một subscription được phê duyệt**. Hãy triển khai `sensorSimulator` và `telemetryFilter` ở phần 7, đặt threshold 35°C, chỉ gửi cảnh báo qua edgeHub lên cloud. Nếu không có device thật, có thể hoàn thành phần **phân tích manifest/thiết kế/diễn giải kết quả** mà không tự tạo Azure resources hoặc đăng ký thiết bị ngoài quyền của mình.

### 22.1. Các nhiệm vụ

1. **Kiến trúc:** vẽ sensor → adapter/module → edgeHub → filter → IoT Hub → Event Hubs/ADX, phân biệt data plane và control plane.
2. **Thiết bị:** lập bảng xác minh Linux/CPU architecture/RAM/disk/clock/ports và runtime version.
3. **Identity:** giải thích khác nhau giữa device identity, DPS enrollment, IoT Hub RBAC, module identity và ACR pull credentials.
4. **Mã nguồn:** dùng `sensorSimulator` phát JSON có `eventId`, timestamp UTC và temperature °C; filter kiểm tra schema/bounds.
5. **Container:** viết Dockerfile chạy non-root, build đúng architecture và pin dependencies trong production.
6. **Registry:** push hai images có tags/digests rõ; xác minh device có quyền pull từ private ACR qua phương thức an toàn.
7. **Manifest:** xây `modulesContent` chứa `$edgeAgent` và `$edgeHub`, hai modules, routes và TTL.
8. **Route:** mô tả input `input1`/output `temperatureOutput`/`filtered`; chứng minh không có loop.
9. **Deployment:** dùng Portal hoặc `az iot edge set-modules` trên đúng device lab và ghi change ID.
10. **Readback:** kiểm tra `edgeAgent` reported state, `iotedge list` và logs từng module.
11. **Message validation:** với 34°C, không gửi cảnh báo cloud; với 39°C, gửi đúng event.
12. **Bad payload:** gửi JSON thiếu `temperatureC`, chứng minh module không crash.
13. **Offline:** ngắt Internet 15 phút, kiểm tra local processing và backlog cloud.
14. **Reconnect:** xác minh messages trong TTL được gửi tiếp; ghi evidence về duplicates/late arrivals.
15. **TTL/disk:** tính backlog 10 msg/s × 1 KiB × 6 giờ; quyết định disk headroom.
16. **Twin:** đổi desired `thresholdC` nhưng code chỉ đọc env; giải thích vì sao reported/behavior chưa đổi.
17. **Fleet:** tạo target condition cho tag `ring=canary`; giải thích cách tránh chọn nhầm production.
18. **Rollout:** mô tả stages lab/canary/pilot/fleet, success metrics và rollback criterion.
19. **Security:** liệt kê 5 secrets không được đặt trong manifest env và quy trình rotation.
20. **Monitoring:** dashboard ít nhất 8 metrics gồm host/disk, runtime, route, upstream, last-seen, cloud lag.
21. **Troubleshooting:** giải thích `exec format error`, `unauthorized` image pull và route sai output name.
22. **Resilience:** nếu gateway mất điện, dữ liệu gì có thể mất và vì sao edgeHub TTL không là backup?
23. **Cost:** tính sự kiện/ngày cho 100 gateways × 5 sensors × 1 message/s, nếu filter giữ 5%.
24. **Cleanup:** xác định tài nguyên cloud lab nào có thể xóa, tài nguyên shared nào không thể chạm.

### 22.2. Các kết quả tham khảo

**Câu 8 — route không lặp:**

~~~text
sensorSimulator.temperatureOutput → telemetryFilter.input1
telemetryFilter.filtered → $upstream
~~~

Nếu dùng `FROM /messages/*` chuyển tới filter input, có nguy cơ chuyển cả output do filter phát quay lại filter theo route rộng; nên chọn source module/output rõ.

**Câu 11 — lọc đúng:** giả sử threshold 35.0°C; `temperatureC=34.0` bị lọc, `temperatureC=39.0` tạo output `filtered`. Không dùng logic này như chứng nhận điều khiển an toàn.

**Câu 15 — buffer:** 10 × 1024 × 6 × 3600 = 221.184.000 bytes ≈ **211 MiB payload** trước overhead/replication/logs. Cần đo dung lượng thực và headroom, không cấu hình volume chính xác 211 MiB.

**Câu 16 — twin drift:** nếu code chỉ lấy `os.getenv("TEMP_THRESHOLD_C")` lúc start, desired twin update `thresholdC` không được tự áp. Phải thêm desired-properties callback/report ack hoặc rollout thay env/container.

**Câu 17 — target canary:**

~~~text
tags.environment='lab' AND tags.ring='canary'
~~~

Kiểm tra các twins match condition và quyền quản lý IoT Hub trước khi chạy automation. Nếu chưa có ring tags, query này có thể match 0 devices; đừng mở condition thành true để “có kết quả”.

**Câu 19 — secrets:** IoT Hub connection string, device private key, registry password, service principal client secret, database password, access token. Đây là sáu ví dụ, mọi thứ cần cơ chế bảo vệ và rotation tương ứng.

**Câu 21 — lỗi:**

- `exec format error` → kiểm tra image CPU architecture/entrypoint.
- `unauthorized` khi pull ACR → xác minh registry identity/credentials/permissions, không bật admin user bừa.
- Route output name mismatch → sửa `$edgeHub.routes`/SDK output contract, không mở firewall.

**Câu 23 — số liệu:** 100 × 5 × 86.400 = **43.200.000 raw events/ngày**; 5% còn **2.160.000 filtered events/ngày**. IoT Hub billed messages có thể khác event count theo size/tier/operations.

### 22.3. Test matrix đề xuất

| Case | Input/điều kiện | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| A | Temperature 30°C | Không có cloud alert | Local receive count tăng, output không tăng |
| B | Temperature 39°C | Một cloud alert hợp lệ | Filter output và IoT Hub consumer eventId |
| C | Missing temperature field | Module không crash | Invalid payload metric + process alive |
| D | WAN offline 15 phút | Local processing tiếp tục | Local logs, queue/backlog counters |
| E | WAN reconnect trong TTL | Eligible events eventually arrive | Timestamp/eventId/dedup evidence |
| F | Bad ACR credentials | Pull/reconcile error, no false success | edgeAgent logs/reported status |
| G | Wrong CPU architecture | Module không start | Device architecture + image manifest |
| H | Wrong route output name | Modules chạy nhưng no upstream event | edgeHub route/counters |
| I | New deployment to canary | Chỉ đúng devices đổi image | Target twin tags and reported version |
| J | Rollback to previous digest | App behavior phục hồi | Runtime image digest and business telemetry |
| K | Disk pressure in lab | Alert và controlled degradation | Disk/edgeHub queue metrics |
| L | Expired cert/clock skew lab | Auth failure được phát hiện | Device checks/cert audit |

**Không chạy test mất điện/đầy disk hoặc revoked credentials trên thiết bị production**. Những test có thể gây gián đoạn phải ở lab/staging có owner và recovery plan.

### 22.4. Tiêu chí hoàn thành

Bài thực hành đạt khi:

- Manifest **parse JSON hợp lệ** và mô tả đầy đủ two modules/routes.
- Module images tồn tại và đúng platform, device pull được theo quyền.
- IoT Hub desired và edgeAgent reported state khớp với thực tế.
- Input/output route có bằng chứng từ local và cloud events.
- 15 phút offline local processing tiếp tục; store-and-forward hoạt động trong điều kiện test, có giới hạn được ghi nhận.
- Tường minh dữ liệu nào có thể mất, cách xử lý duplicate/replay và bảo mật secrets.
- Có canary/rollback/metrics/FinOps và cleanup plan.

## 23. Checklist triển khai production

### 23.1. Trước khi đăng ký thiết bị

- [ ] Xác định use case thật sự cần edge computing, không phải chỉ một sensor gửi vài events.
- [ ] Xác minh OS/IoT Edge runtime version/CPU arch được hỗ trợ.
- [ ] Có benchmark CPU/RAM/disk cho tải peak, store-and-forward và image update.
- [ ] Thiết lập thời gian UTC/NTP đáng tin, filesystem permissions và log rotation.
- [ ] Thiết kế IoT Hub/DPS/device IDs/attestation/certificate rotation.
- [ ] Có network egress/DNS/proxy/TLS và local leaf-device segmentation phù hợp.
- [ ] Chỉ cấp cloud/admin RBAC và secrets ở phạm vi cần thiết.
- [ ] Ghi device/site/hardware/ring tags do owner quản trị.

### 23.2. Trước khi tạo deployment

- [ ] Image build theo `linux/amd64`/`linux/arm64` phù hợp, scan CVEs/SBOM.
- [ ] Tag/digest immutable đã được approved; base image có kế hoạch vá.
- [ ] Container chạy non-root, resource limits và mounts tối thiểu.
- [ ] Không có credentials/token/password hardcoded trong image/env/manifest.
- [ ] `$edgeAgent`/`$edgeHub` schema versions và images phù hợp runtime.
- [ ] module IDs/inputs/outputs/routes thống nhất, tránh vòng lặp.
- [ ] `createOptions` escape JSON đúng và dùng filesystem permissions được kiểm chứng.
- [ ] Store-and-forward TTL/disk dựa trên RPO, WAN outage và backlog rate.
- [ ] Desired/reported twin behavior và dynamic config có contract/ack/version.
- [ ] Fleet target condition/ring/priority được review; không match nhầm devices.

### 23.3. Sau khi deploy

- [ ] Module desired state và reported state khớp; image digest đúng.
- [ ] edgeAgent/edgeHub/custom modules chạy ổn, không có crash loop.
- [ ] Sensor events đi đúng named routes, filter outputs đúng schema.
- [ ] End-to-end IoT Hub consumer nhận test message, có eventId/timestamp.
- [ ] Offline/reconnect behavior được kiểm chứng trên gateway đại diện.
- [ ] Module reject malformed payload và không gửi PII/secret.
- [ ] Local disk/queue/backlog/drop metrics và last-seen monitor hoạt động.
- [ ] Cảnh báo có owner, change ticket và runbook incident.
- [ ] Canary metrics đạt trước khi mở rộng fleet.
- [ ] Còn image/digest cũ và phương án rollback được thử nghiệm.

### 23.4. Vận hành thường xuyên

- [ ] Theo dõi host CPU/RAM/disk, certificate expiry/clock, edgeAgent restarts.
- [ ] Theo dõi IoT Hub quotas/throttling, upstream connectivity, cloud ingestion lag.
- [ ] Rà soát device identities không còn sử dụng và quyền registry.
- [ ] Rotate secrets/certificates theo lịch và test trên canary.
- [ ] Cập nhật OS/container engine/IoT Edge runtime theo phiên bản được hỗ trợ.
- [ ] Kiểm tra nguồn điện, mạng site, hardware spare và bảo trì.
- [ ] Duy trì backward-compatible message schema khi rollout không đồng loạt.
- [ ] Diễn tập WAN outage, reboot, rollback và device re-provisioning.
- [ ] Review data retention/PII, cost per site và nguồn events có giá trị.

### 23.5. Xử lý incident

- [ ] Xác nhận IoT Hub/device/site và phạm vi affected devices.
- [ ] Phân biệt host failure, device identity failure, image pull, module crash, route, upstream, consumer.
- [ ] Không bật public inbound ports hoặc tắt TLS để sửa network.
- [ ] Xem offline TTL/backlog/disk trước khi kết luận mất events.
- [ ] Không xóa toàn bộ container images/logs nếu chưa lưu bằng chứng/rollback.
- [ ] Nếu rollback, xác minh actual module digest và nghiệp vụ chứ không chỉ desired status.
- [ ] Nếu cloud thấy 0 events, xác minh local sensor và **ingestion freshness**.
- [ ] Ghi impact, data loss/duplicates, recovery và preventive actions.

## 24. Dọn dẹp lab an toàn

Một bài thực hành có thể tạo IoT Hub device identity, ACR images, deployment configurations và tài nguyên cloud riêng. Tuy nhiên, một IoT Hub/ACR/resource group có thể **dùng chung** cho nhiều team, vì vậy không được xóa bừa.

### 24.1. Kiểm kê

~~~bash
az account show --query "{id:id,name:name}" -o table

az iot hub device-identity show \
  --hub-name "$HUB_NAME" \
  --device-id "$DEVICE_ID" \
  --output json

az iot edge deployment list \
  --hub-name "$HUB_NAME" \
  --output table

az resource list \
  --resource-group "<approved-lab-resource-group>" \
  --output table
~~~

Đây là những lệnh **chỉ đọc**, áp dụng khi các biến đã được xác nhận và người dùng có permission. CLI extension versions có thể thay đổi syntax/available subcommands.

### 24.2. Quy trình cleanup

1. Xác nhận đúng subscription, IoT Hub và **device lab** đã ngừng hoạt động.
2. Kiểm tra device/automatic deployment có đang target production hay dùng IoT Hub shared không.
3. Lưu logs/test evidence cần retention, **không** lưu private keys/access tokens.
4. Nếu có data quan trọng, thiết kế export/backfill/retention trước khi xóa.
5. Xóa **chỉ lab-specific deployments/device identity/images** sau owner approval.
6. Không xóa ACR registry hoặc IoT Hub dùng chung chỉ vì đã tạo images ở đó.
7. Đánh giá Private Endpoints/Log Analytics/Event Hubs/Blob nếu lab tạo riêng.
8. Tắt/reimage/thu hồi hardware demo đúng quy trình bảo mật thiết bị.
9. Kiểm tra Cost Management để xác nhận không còn tài nguyên tính phí ngoài dự kiến.

Các hành động xóa sau chỉ là **mẫu được comment**, không phải yêu cầu chạy:

~~~bash
# KHÔNG TỰ CHẠY nếu chưa có owner approval và dependency review:
# az iot hub device-identity delete \
#   --hub-name "$HUB_NAME" --device-id "$DEVICE_ID"

# Xóa resource group là phá hủy TẤT CẢ tài nguyên trong group;
# chỉ phù hợp nếu 100% group dùng riêng cho lab.
# az group delete --name "<approved-lab-resource-group>" --yes
~~~

**Không xóa Edge identity đang dùng bởi một gateway offline lâu ngày** chỉ vì nó không báo online trong hôm nay; gateway đó có thể đang xử lý local và cần reconnect.

## 25. Tài liệu tham khảo và ghi nhớ

Khi triển khai thực tế, xem tài liệu Microsoft đúng **IoT Edge runtime version/OS/architecture** trước khi chọn package, image tag, CLI extension hoặc device provisioning workflow:

- [Azure IoT Edge overview](https://learn.microsoft.com/azure/iot-edge/about-iot-edge?view=iotedge-1.5) — runtime, modules, edgeAgent/edgeHub.
- [Deploy modules with Azure Portal](https://learn.microsoft.com/azure/iot-edge/how-to-deploy-modules-portal?view=iotedge-1.5) — manifest, custom images và routes.
- [Develop and deploy modules](https://learn.microsoft.com/azure/iot-edge/module-composition?view=iotedge-1.5) — module identity, communication và composition.
- [Operate IoT Edge offline](https://learn.microsoft.com/azure/iot-edge/how-to-configure-offline?view=iotedge-1.5) — local store, TTL và lưu trữ.
- [Monitor and troubleshoot IoT Edge](https://learn.microsoft.com/azure/iot-edge/how-to-monitor-iot-edge?view=iotedge-1.5) — device/module metrics/diagnostics.
- [IoT Edge troubleshooting](https://learn.microsoft.com/azure/iot-edge/troubleshoot?view=iotedge-1.5) — runtime checks và lỗi triển khai.
- [IoT Hub device twins](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-device-twins) — tags, desired/reported properties.
- [Azure IoT Device Provisioning Service](https://learn.microsoft.com/azure/iot-dps/about-iot-dps) — enrollment/attestation/assignment.
- [Azure IoT Hub quotas and throttling](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-quotas-throttling) — capacity planning.

**Lưu ý tính thời điểm:** những tính năng, bản runtime và tên command cụ thể có thể đổi; hình thức `:1.5` trong ví dụ không phải thông báo “latest”. Bài không khẳng định rằng IoT Edge thay được PLC/RTOS hoặc mọi SDK/registry credential feature đều hỗ trợ theo cách giống Kubernetes.

**Mười điều cần nhớ:**

1. **IoT Edge phục vụ local container processing** khi latency, băng thông, offline và quản trị fleet là vấn đề quan trọng.
2. **edgeAgent quản desired state**, còn **edgeHub định tuyến và lưu-tạm messages**; cả hai khác custom business modules.
3. **Device identity, module identity, registry auth và Azure RBAC** có phạm vi khác nhau.
4. **Module là container image + deployment contract + module twin**, không chỉ một Dockerfile.
5. **Routes phải trùng module/output/input names** và tránh route vòng lặp; không thấy cloud telemetry chưa chứng minh module crash.
6. **Store-and-forward có TTL/disk limits**; không là durable queue hay backup đảm bảo exactly-once.
7. **Offline-first cần design và test thật**: clock, network, disk, retry, replay, idempotency và local safety.
8. **Deploy theo rings và rollback có kiểm chứng**; devices offline có thể nhận desired version trễ.
9. **Bảo mật toàn chuỗi:** OS/cert/hardware, pinned images, non-root containers, secrets, TLS, network và least privilege.
10. **Đo kết quả cuối:** local reaction SLO, actual module version, upstream delivery, ingest freshness, data loss và total cost per useful event.

Một triển khai **Azure IoT Edge và module tại thiết bị** chỉ được coi là hoàn tất khi có bằng chứng rằng **thiết bị được nhận diện đúng, image được pull và chạy trên đúng hardware, edgeHub routes xử lý chính xác, modules vẫn hoạt động khi mất mạng trong phạm vi thiết kế, dữ liệu được forward/giám sát đúng sau reconnect và toàn bộ quá trình nâng cấp hoặc rollback được kiểm soát an toàn**.
