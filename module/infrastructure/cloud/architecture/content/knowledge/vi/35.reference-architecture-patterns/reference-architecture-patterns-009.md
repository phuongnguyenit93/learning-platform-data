# Thu thập dữ liệu IoT kết hợp xử lý tại biên

Một nhà máy có hàng nghìn cảm biến đo nhiệt độ, độ rung và điện năng. Nếu mọi mẫu đo đều gửi trực tiếp lên đám mây, chi phí truyền và lưu dữ liệu có thể lớn, cảnh báo phụ thuộc đường truyền Internet, còn nhà máy mất khả năng giám sát khi kết nối gián đoạn. Ngược lại, nếu chỉ giữ dữ liệu tại nhà máy, doanh nghiệp khó đối chiếu nhiều cơ sở, huấn luyện mô hình trên dữ liệu dài hạn và quản trị thiết bị tập trung.

**Kiến trúc IoT kết hợp xử lý tại biên (edge–cloud IoT)** đặt một phần thu thập, chuẩn hóa, phân tích và lưu đệm gần thiết bị, đồng thời dùng cloud cho tiếp nhận quy mô lớn, lưu trữ lâu dài, phân tích liên cơ sở và quản lý đội thiết bị. Đây là một **mẫu kiến trúc tham chiếu**, không phải sơ đồ áp dụng nguyên xi: thiết kế cần xuất phát từ mục tiêu nghiệp vụ, mức chịu gián đoạn, phân vùng tin cậy, tính chất dữ liệu và giới hạn vận hành.

Trong phạm vi thiết kế kiến trúc ứng dụng đám mây, bài học đi từ yêu cầu đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai, rồi đánh giá theo các khía cạnh của Well-Architected: vận hành, độ tin cậy, bảo mật, hiệu năng, chi phí và tính bền vững.

## 1. Hiểu đúng các thành phần và trách nhiệm

| Thành phần | Vai trò điển hình | Điều cần làm rõ |
|---|---|---|
| **Thiết bị/cảm biến** | Đo dữ liệu vật lý, gửi trạng thái hoặc nhận cấu hình | Giao thức, tần suất đo, độ chính xác, nguồn điện, danh tính |
| **Bộ điều khiển cục bộ (PLC/RTU)** | Điều khiển máy theo quy trình được kiểm định | Giới hạn an toàn, phản ứng thời gian thực, trách nhiệm của hệ OT |
| **Edge gateway** | Kết nối thiết bị, đổi giao thức, gom dữ liệu, xác thực và lưu đệm | Năng lực CPU/RAM/đĩa, số kết nối, khả năng nâng cấp |
| **Edge processing** | Lọc nhiễu, tính đặc trưng, tổng hợp, suy luận mô hình, tạo cảnh báo | Độ trễ mục tiêu, tính đúng, tài nguyên và hành vi khi offline |
| **Cloud ingestion** | Nhận telemetry từ nhiều gateway qua kênh được kiểm soát | Danh tính, hạn mức, chịu tải, xử lý dữ liệu trùng |
| **Stream processing** | Định tuyến, kiểm tra schema, enrich, tính toán gần thời gian thực | Trễ sự kiện, thứ tự, lỗi, replay và version |
| **Kho dữ liệu** | Lưu time series, lịch sử thô, phân tích, báo cáo | Retention, truy vấn, phân lớp nóng/lạnh, quyền truy cập |
| **Device/fleet management** | Đăng ký, cấp quyền, cấu hình, cập nhật phần mềm và theo dõi sức khỏe | Chứng chỉ, phiên bản, rollout, rollback, audit |
| **Ứng dụng nghiệp vụ** | Dashboard, cảnh báo, bảo trì dự đoán, phân tích công suất | Người dùng, hành động cần thực hiện, chỉ số thành công |

**Edge** có thể là vi điều khiển, gateway công nghiệp, máy tính cạnh dây chuyền hoặc cụm máy tại nhà máy. Cách đặt tính toán phụ thuộc khả năng chạy liên tục và giới hạn phần cứng. **Cloud** không nhất thiết là một dịch vụ cụ thể của nhà cung cấp: nên xác định chức năng logic trước khi chọn sản phẩm triển khai.

### 1.1. Phân biệt telemetry và control

- **Telemetry (đường dữ liệu đi lên):** cảm biến/gateway gửi số đo, trạng thái và sự kiện cho phân tích.
- **Control/command (đường điều khiển đi xuống):** hệ quản trị gửi cấu hình, yêu cầu chẩn đoán hoặc lệnh được phép xuống thiết bị.
- **Local safety control:** các liên động bảo vệ máy, dừng khẩn cấp và điều khiển yêu cầu tính xác định theo thời gian thuộc lớp điều khiển tại chỗ đã được đánh giá an toàn.

Không đặt vòng điều khiển an toàn phụ thuộc vào cloud hoặc một mô hình AI từ xa khi đường truyền và cơ chế xử lý không đáp ứng yêu cầu an toàn. Lệnh từ cloud cần đi qua lớp kiểm tra quyền, trạng thái, giới hạn vận hành và người/thiết bị có thẩm quyền tại địa điểm.

## 2. Xác định yêu cầu trước khi vẽ kiến trúc

Thiết kế nên có **quality attribute scenarios**: trong bối cảnh nào, hệ thống gặp tác nhân gì, phải phản hồi ra sao và kiểm chứng bằng chỉ số nào.

| Nhóm yêu cầu | Câu hỏi kiến trúc | Ví dụ tiêu chí cần xác nhận |
|---|---|---|
| **Độ trễ** | Cảnh báo phải xuất hiện ở đâu và sau bao lâu kể từ lúc cảm biến đo? | Cảnh báo tại edge trong một ngưỡng do nghiệp vụ định nghĩa |
| **Mất kết nối** | Nhà máy cần hoạt động mấy giờ/ngày khi không có WAN? | Tiếp tục thu thập ưu tiên và chuyển bù sau khi nối lại |
| **Quy mô** | Bao nhiêu thiết bị, mẫu/giây, kích thước mẫu, số site và tốc độ tăng trưởng? | Ingestion và bộ đệm có khoảng dư tải |
| **Tính đúng dữ liệu** | Có chấp nhận thiếu/trùng/đảo thứ tự dữ liệu? | Sự kiện trọng yếu được đối soát theo ID và thứ tự nguồn |
| **Bảo mật** | Thiết bị nằm trong mạng nào, khóa đặt ở đâu, ai được ra lệnh? | Danh tính riêng cho thiết bị, quyền tối thiểu, audit đầy đủ |
| **Quyền riêng tư** | Dữ liệu nào được rời nhà máy? | Lọc hoặc ẩn định danh tại edge theo yêu cầu đã duyệt |
| **Tính sẵn sàng** | Mất gateway, nguồn điện, vùng cloud ảnh hưởng thế nào? | RTO/RPO và cơ chế degrade được kiểm thử |
| **Vận hành** | Ai cập nhật gateway ở nhiều địa điểm? | Có inventory, canary rollout, quan sát và rollback |
| **Chi phí** | Phải trả cho băng thông, tin nhắn, lưu trữ, tính toán và nhân sự bao nhiêu? | TCO theo thời gian, tính cả gateway và bảo trì |

Các con số SLO/SLA, RTO/RPO, thời gian lưu giữ và mức an toàn phải được **chủ sở hữu nghiệp vụ, OT, an ninh và vận hành** chấp thuận. Không nên mặc định “gần thời gian thực” luôn là một giây, hoặc mọi telemetry cần độ bền như giao dịch tài chính.

### 2.1. Ba câu hỏi quyết định đặt tính toán ở đâu

1. **Quyết định có cần thực hiện dù mất Internet không?** Nếu có, phần tối thiểu của quyết định và trạng thái liên quan phải nằm ở edge/local controller.
2. **Phải xử lý bao nhiêu dữ liệu trước khi gửi đi?** Nếu dữ liệu thô lớn, dùng edge để lọc, tổng hợp, nén hoặc trích đặc trưng; giữ khả năng gửi dữ liệu thô theo điều kiện khi cần.
3. **Quyết định có cần phối hợp nhiều địa điểm hoặc lịch sử dài hạn không?** Nếu có, cloud phù hợp cho phân tích tổng hợp, đào tạo mô hình và quản trị toàn cục.

## 3. Kiến trúc tham chiếu: data plane và control plane

~~~mermaid
flowchart TB
  subgraph Site["Nhà máy / mạng OT"]
    Sensors["Cảm biến / máy móc"]
    PLC["PLC / điều khiển an toàn tại chỗ"]
    Adapter["Gateway: adapter giao thức + xác thực"]
    Edge["Edge: lọc, aggregate, rule / ML inference"]
    Buffer[("Durable queue / store-and-forward")]
    Local["Dashboard / cảnh báo cục bộ"]
    Sensors --> Adapter
    Sensors --> PLC
    Adapter --> Edge
    Edge --> Local
    Edge --> Buffer
  end
  subgraph Cloud["Cloud / mạng ứng dụng"]
    Ingest["IoT broker / ingestion endpoint"]
    Stream["Stream processing + schema validation"]
    TSDB[("Time-series / operational store")]
    Lake[("Object storage / data lake")]
    Analytics["Dashboard, báo cáo, phân tích, ML training"]
    Fleet["Registry, IAM, cấu hình, OTA orchestration"]
    Ingest --> Stream
    Stream --> TSDB
    Stream --> Lake
    TSDB --> Analytics
    Lake --> Analytics
  end
  Buffer -->|"MQTT/HTTPS qua TLS, retry"| Ingest
  Fleet -.->|"Kênh quản trị xác thực, update ký số"| Adapter
  Fleet -.->|"Cấu hình và model version"| Edge
~~~

Sơ đồ là một **logical reference architecture**. Trên thực tế, cần thêm các biên tin cậy: mạng OT, vùng gateway/DMZ công nghiệp, Internet hoặc private WAN, lớp tiếp nhận cloud, vùng xử lý và vùng lưu trữ. Không kết nối trực tiếp PLC vào endpoint Internet chỉ vì sơ đồ có đường telemetry.

### 3.1. Data plane: đường đi dữ liệu

**Bước 1 — Thu thập:** gateway lấy số đo từ thiết bị qua adapter phù hợp. Với OT, adapter chỉ đọc những biến được cho phép; rate limiting để không làm quá tải PLC. Những dữ liệu nhạy cảm có thể cần lọc ngay tại điểm thu.

**Bước 2 — Chuẩn hóa:** quy đổi đơn vị, gắn danh tính thiết bị, timestamp đo, phiên bản schema và quality flag. Giữ nguyên phép đo quan trọng hoặc lưu tham chiếu tới dữ liệu gốc khi cần kiểm toán.

**Bước 3 — Tính toán tại edge:** kiểm tra ngưỡng, loại nhiễu, tổng hợp cửa sổ, phát hiện bất thường, chạy mô hình suy luận hoặc sinh cảnh báo cục bộ. Tách luồng cảnh báo ưu tiên cao khỏi luồng thống kê nền.

**Bước 4 — Lưu đệm bền vững:** ghi sự kiện cần chuyển vào hàng đợi/nhật ký có giới hạn trước khi xác nhận nhận dữ liệu ở gateway. Chỉ loại bỏ bản ghi khi chính sách giao nhận và bằng chứng nhận từ downstream cho phép.

**Bước 5 — Truyền an toàn:** gateway chủ động tạo kết nối ra qua TLS/mTLS tới broker hoặc HTTPS endpoint. Khi WAN phục hồi, gửi bù có kiểm soát tốc độ để không làm nghẽn môi trường cloud.

**Bước 6 — Xử lý trên cloud:** xác thực tenant/site/device, kiểm tra schema, deduplicate, enrich với metadata tài sản, tính toán sự kiện và phân luồng tới kho phù hợp.

**Bước 7 — Phục vụ nghiệp vụ:** dashboard vận hành đọc dữ liệu gần thời gian thực; hệ dữ liệu dài hạn hỗ trợ dự báo lỗi và so sánh nhiều nhà máy; cảnh báo có cơ chế xác nhận và xử lý.

### 3.2. Control plane: quản lý đội thiết bị

Tách luồng quản trị khỏi luồng telemetry để dễ kiểm soát quyền và tránh gây nghẽn dữ liệu nghiệp vụ. Control plane quản lý **onboarding, danh tính, chứng chỉ, cấu hình, policy, phiên bản ứng dụng/model, cập nhật firmware, rollout theo nhóm, thu hồi thiết bị và audit**.

Quy trình cập nhật an toàn nên có: bản phát hành được ký; kiểm tra nguồn và phiên bản; triển khai thử trên nhóm nhỏ; kiểm tra sức khỏe; mở rộng theo đợt; khả năng quay về phiên bản trước đã được kiểm thử. Với thiết bị có chức năng an toàn, mọi thay đổi phải tuân theo quy trình OT riêng và không tự thay đổi logic điều khiển ngoài phạm vi được phê duyệt.

## 4. Chia trách nhiệm edge và cloud

| Tác vụ | Nên đặt tại edge khi… | Nên đặt tại cloud khi… |
|---|---|---|
| Thu thập protocol OT | Thiết bị chỉ giao tiếp trong LAN/serial hoặc mạng cách ly | Thiết bị có kết nối Internet an toàn và hỗ trợ giao thức phù hợp |
| Lọc dữ liệu, tổng hợp | Muốn giảm lưu lượng, cần loại dữ liệu nhạy cảm trước khi rời site | Cần tính toán thống nhất nhiều nguồn hoặc muốn giữ dữ liệu gốc |
| Cảnh báo vận hành | Phải hoạt động khi offline, yêu cầu độ trễ thấp | Dựa vào lịch sử dài hoặc cần tương quan nhiều site |
| Suy luận ML | Cần phản hồi nhanh, có giới hạn dữ liệu truyền hoặc cần bảo mật dữ liệu tại chỗ | Mô hình quá nặng cho phần cứng edge hoặc yêu cầu thông tin tập trung |
| Huấn luyện ML | Có máy chủ edge chuyên dụng và lý do dữ liệu phải ở tại chỗ | Có tập dữ liệu lớn, khả năng tính toán và pipeline quản trị mô hình |
| Lưu trữ ngắn hạn | Cần store-and-forward và phân tích cục bộ khi mất WAN | Cần đồng bộ nhiều site với thời gian lưu giữ dài |
| Lưu trữ lâu dài, báo cáo liên cơ sở | Có ràng buộc dữ liệu không được rời địa điểm | Cần truy vấn hợp nhất và phân tích lịch sử đa cơ sở |
| Điều khiển an toàn | Cần tính xác định và quy trình chứng nhận phù hợp tại chỗ | Không phù hợp làm vòng điều khiển an toàn trực tiếp |

**Ví dụ:** cảm biến rung gửi nhiều mẫu mỗi giây. Edge tính RMS và phổ tần số trong cửa sổ ngắn, phát cảnh báo ngay tại xưởng, gửi chỉ số tổng hợp đều đặn lên cloud, nhưng lưu hoặc gửi dữ liệu sóng thô khi phát hiện bất thường để chuyên gia phân tích. Không phải mọi bộ lọc/tổng hợp đều giữ nguyên thông tin: phải ghi rõ những dữ liệu bị mất và khả năng tái phân tích.

## 5. Giao thức và lớp kết nối

Không có một giao thức tối ưu cho mọi tầng:

| Giao thức/kiểu kết nối | Vị trí hợp lý | Điểm cần đánh giá |
|---|---|---|
| **Modbus RTU/TCP** | Gateway đọc thiết bị công nghiệp cũ trong mạng OT | Bản gốc thiếu xác thực/mã hóa đầu cuối; cô lập mạng và kiểm soát adapter |
| **OPC UA** | Tích hợp dữ liệu thiết bị/máy công nghiệp có cấu trúc | Mô hình thông tin, bảo mật endpoint, chứng chỉ và khả năng của server |
| **MQTT** | Gateway/thiết bị gửi telemetry qua kết nối bền | QoS, phiên, keepalive, giới hạn topic/payload, backpressure, retain policy |
| **CoAP** | Thiết bị hạn chế tài nguyên trong môi trường thích hợp | Mạng không ổn định, bảo vệ DTLS/OSCORE phù hợp, proxy/gateway |
| **HTTPS** | Batch upload, API quản lý hoặc ingestion yêu cầu request/response | Chi phí thiết lập kết nối, retry, idempotency và giới hạn kích thước |
| **Private WAN / VPN / dedicated link** | Kết nối site-cloud có yêu cầu cách ly hoặc ổn định cao | Băng thông, độ trễ, định tuyến, failover và chi phí |

Đối với thiết bị trong mạng OT, mô hình thường an toàn hơn là **gateway chủ động kết nối ra** qua vùng trung gian được kiểm soát, thay vì cloud mở kết nối tùy ý vào thiết bị.

### 5.1. MQTT QoS không thay thế kiểm soát dữ liệu đầu cuối

- **QoS 0:** gửi kiểu best effort; có thể mất.
- **QoS 1:** cơ chế gửi ít nhất một lần trong phạm vi kết nối MQTT; có thể phát lại và tạo bản sao.
- **QoS 2:** trao đổi đúng một lần ở phạm vi protocol hop MQTT liên quan; không bảo đảm tự động “xử lý đúng một lần” qua adapter, queue, stream processor và database.

Vì vậy, ngay cả khi dùng MQTT QoS 1 hoặc 2, logic downstream vẫn cần **idempotency** và xử lý phát lại. ACK từ broker không đồng nghĩa dữ liệu đã được ghi bền vững vào mọi kho downstream. Quyết định thời điểm xóa dữ liệu tại edge dựa trên mức bền vững yêu cầu và hợp đồng cụ thể của nền tảng.

### 5.2. Phân đoạn và quyền mạng

Thiết kế tách ít nhất ba vùng: **OT/thiết bị**, **DMZ/gateway**, **IT/cloud**. Chỉ cho phép các luồng cần thiết theo nguyên tắc quyền tối thiểu, ghi log luồng bị chặn và kiểm thử đường dự phòng. Nếu gateway cần đọc nhiều protocol, chỉ mở quyền tới từng subnet, cổng và thiết bị được duyệt; không cấp quyền truy cập phẳng tới toàn bộ mạng nhà máy.

## 6. Thiết kế hợp đồng dữ liệu IoT

Một thông điệp telemetry nên đủ ngữ cảnh để giải thích và xử lý lại, ngay cả khi cloud nhận muộn. Mẫu tối thiểu:

~~~json
{
  "schemaVersion": "1.0",
  "eventId": "site-a/pump-17/boot-42/seq-109813",
  "tenantId": "factory-group",
  "siteId": "site-a",
  "deviceId": "pump-17",
  "bootId": "boot-42",
  "sequence": 109813,
  "observedAt": "2026-11-18T08:15:12.340Z",
  "gatewayReceivedAt": "2026-11-18T08:15:12.370Z",
  "metric": "vibration.rms",
  "value": 2.74,
  "unit": "mm/s",
  "quality": "good",
  "processing": {
    "type": "window_aggregate",
    "windowSeconds": 10,
    "edgeAppVersion": "3.2.1"
  }
}
~~~

Đây là **payload minh họa**, không phải schema bắt buộc. Cấu trúc chuẩn thực tế có thể dùng JSON, Protobuf, Avro hoặc định dạng nhị phân tùy thiết bị và pipeline. Trường nào là nhạy cảm cũng cần được đánh giá trước khi truyền hoặc lưu.

Các quyết định cần nêu trong data contract:

- **Danh tính:** tổ hợp tenant/site/device là duy nhất trong phạm vi nào; đăng ký và thu hồi ra sao?
- **Event time và processing time:** thời điểm đo tại thiết bị khác thời điểm gateway nhận và cloud xử lý; dùng thời điểm nào để tính cửa sổ?
- **Định danh sự kiện:** eventId duy nhất, sequence theo thiết bị và bootId hỗ trợ phát hiện trùng/mất. Nếu reset counter, phải tránh va chạm ID.
- **Đơn vị và quality:** nhiệt độ Celsius hay Fahrenheit; số đo lỗi, vượt dải, mất hiệu chuẩn biểu diễn thế nào?
- **Schema evolution:** thay đổi field theo phiên bản có tương thích với gateway chưa cập nhật và người tiêu thụ cũ không?
- **Retention/lineage:** raw, aggregate, alert lưu bao lâu; có truy vết được kết quả phân tích về nguồn hay không?

### 6.1. Trùng lặp, sai thứ tự và bản ghi đến muộn

Hệ IoT thường thiên về **at-least-once delivery** trong các đoạn mạng không ổn định; cần dự kiến:

1. Gateway phát lại sau khi không nhận ACK, làm cùng event đến nhiều lần.
2. Bản ghi sequence 102 tới cloud trước sequence 101.
3. Thiết bị mất đồng bộ đồng hồ, tạo timestamp sai.
4. Điểm kết nối WAN hồi phục khiến dữ liệu của nhiều giờ trước đến cùng một lúc.
5. Đợt triển khai schema mới tạo hai phiên bản payload cùng tồn tại.

Hướng xử lý gồm: khóa deduplicate theo tenantId/deviceId/eventId; xử lý idempotent ở storage/sink; dùng **event-time window** và ngưỡng lateness/watermark có chủ đích; lưu quality flag; theo dõi đồng hồ bằng NTP/PTP phù hợp yêu cầu; và có quy trình sửa/ghi bổ sung dữ liệu đến muộn. Sự kiện báo động quan trọng cần quy tắc riêng, không được loại bỏ vì một cửa sổ thống kê đã đóng.

Một cách mô tả việc ghi dữ liệu ở đích:

~~~text
onTelemetry(message):
    validateIdentityAndSchema(message)
    if alreadyProcessed(message.eventId):
        acknowledgeWithoutApplyingAgain()
        return
    applyIdempotently(message)        # upsert/transaction hoặc cơ chế tương đương
    markProcessed(message.eventId)    # đồng bộ tính nhất quán với bước apply
    acknowledgeAccordingToDurabilityPolicy()
~~~

Nếu applyIdempotently và markProcessed tách biệt mà không có ràng buộc giao dịch hoặc cơ chế khôi phục phù hợp, vẫn có khe hở gây xử lý lặp/mất dữ liệu. Không nên hiểu pseudocode này là bảo đảm exactly-once tự động.

## 7. Thiết kế store-and-forward khi mất kết nối

**Store-and-forward** là khả năng giữ các sự kiện cần thiết tại edge khi cloud không tiếp nhận được, rồi truyền bù khi kết nối hồi phục. Để hoạt động thực sự, cần ít nhất:

- Hàng đợi/nhật ký ghi bền vững trên thiết bị lưu trữ thích hợp, giới hạn dung lượng theo từng loại dữ liệu.
- Cơ chế ưu tiên: cảnh báo, trạng thái sự cố, telemetry định kỳ, raw sample; xác định loại nào được phép giảm mẫu hoặc loại bỏ.
- Tự quản lý áp lực: bounded queue, backpressure tới producer khi có thể, nén/batch và chính sách khi bộ đệm đầy.
- Retry với exponential backoff và jitter, tránh retry storm sau khi WAN hồi phục.
- Checkpoint/offset và trạng thái ACK để nối tiếp từ phần chưa được xác nhận.
- Theo dõi backlog theo **số bản ghi, dung lượng và tuổi bản ghi cũ nhất**, không chỉ tỷ lệ kết nối.

### 7.1. Bài toán dung lượng bộ đệm

Giả sử mỗi gateway nhận **100 cảm biến × 1 mẫu/giây × 300 byte/mẫu**. Chỉ tính payload:

\[
D_{\text{ngày}} = 100 \times 1 \times 300 \times 86\,400
= 2\,592\,000\,000\ \text{byte} \approx 2{,}59\ \text{GB/ngày}.
\]

Nếu muốn giữ **72 giờ** không có WAN, cần khoảng **7,78 GB payload**. Dung lượng thực tế còn phải cộng metadata, chỉ mục hàng đợi, hệ số ghi, dữ liệu retransmit, overhead filesystem, headroom, tốc độ xả backlog và tuổi thọ bộ nhớ flash. Con số ví dụ không phải khuyến nghị mua đĩa 8 GB.

Giả sử gateway lưu 72 giờ rồi đường truyền phục hồi, nếu băng thông chỉ vừa đủ tải hiện tại thì **backlog không bao giờ được xả hết**. Băng thông khả dụng cho catch-up phải lớn hơn tốc độ phát sinh mới; chẳng hạn tốc độ gửi hữu ích gấp đôi tốc độ vào sẽ cần xấp xỉ thêm 72 giờ để xả 72 giờ backlog, chưa kể overhead và áp lực cloud.

Khi storage đầy, chính sách phải rõ ràng: giữ sự kiện an toàn/cảnh báo lâu hơn; giảm tần suất raw; ngừng một luồng không thiết yếu; thông báo trạng thái **data loss/degraded**, không lặng lẽ báo hệ thống khỏe.

### 7.2. Khả năng phục hồi ở edge

Không chỉ mất WAN: gateway có thể mất điện, disk hỏng, ứng dụng crash hoặc thiết bị đo trả số vô nghĩa. Với mỗi lỗi, xác định: điều khiển cục bộ còn an toàn không; dữ liệu nào mất; có thể khởi động lại và gửi bù không; có thiết bị dự phòng hay không; làm sao phát hiện gateway im lặng so với máy thực sự không hoạt động.

Đối với hệ cần khả năng sẵn sàng cao, cân nhắc gateway dự phòng và cơ chế leader/fencing để tránh hai gateway cùng phát lệnh hoặc tạo dữ liệu trùng mất kiểm soát. **HA tại edge** không mặc nhiên được giải quyết chỉ bằng việc chạy hai container.

## 8. Tính toán băng thông và lựa chọn dữ liệu gửi cloud

Ví dụ một nhà máy có **2.000 cảm biến**, mỗi cảm biến gửi **1 bản ghi/giây**, mỗi bản ghi có **250 byte payload**:

\[
2\,000 \times 1 \times 250 \times 86\,400
= 43{,}2\ \text{GB/ngày}
\]

Nếu chỉ gửi **một bản tổng hợp mỗi phút cho mỗi cảm biến**, giả sử bản tổng hợp vẫn 250 byte, phần thống kê định kỳ còn:

\[
2\,000 \times \frac{1}{60} \times 250 \times 86\,400
= 0{,}72\ \text{GB/ngày}.
\]

Như vậy có thể giảm khoảng **98,3% payload thống kê định kỳ** trong tình huống giả định. Đây **không phải** tổng chi phí cloud tiết kiệm được 98,3%: còn gói tin/protocol overhead, event/cảnh báo bổ sung, raw upload khi có bất thường, lưu trữ phân tích, compute, dịch vụ quản trị và chi phí mua/vận hành gateway.

Lưu ý về chất lượng thông tin:

- Mean/median theo phút không giữ được mọi đỉnh rung/ngưỡng an toàn; cần chỉ số **min/max, count, percentile, quality, anomaly flag** hoặc dữ liệu thô có điều kiện.
- Nếu phải làm điều tra nguyên nhân sau sự cố, cần cơ chế lưu raw theo vòng đệm trước/sau sự kiện và chính sách tải lên có chọn lọc.
- Nếu dữ liệu phục vụ kiểm toán/pháp lý bắt buộc đầy đủ, không tự ý loại mẫu để giảm phí.
- Dữ liệu nén/tổng hợp có thể kém hữu ích khi đào tạo lại mô hình; thiết kế retention theo giá trị từng loại.

### 8.1. Tách các đường dữ liệu theo tính khẩn cấp

| Luồng | Đặc tính | Ưu tiên xử lý |
|---|---|---|
| Cảnh báo an toàn/thiết bị | Ít bản ghi, trễ thấp, không được mất theo mục tiêu đã chốt | Cao nhất; phản ứng cục bộ không phụ thuộc cloud |
| Trạng thái vận hành | Định kỳ, phục vụ dashboard | Ưu tiên trung bình; cho phép đến muộn có đánh dấu |
| Aggregate theo phút | Lưu lượng vừa phải, quan trọng cho báo cáo | Có thể batch và gửi bù |
| Raw waveform / ảnh / video | Dung lượng lớn, tải theo yêu cầu hoặc sự kiện | Rate limit, nén, retention và chính sách riêng |
| Log chẩn đoán | Phục vụ bảo trì, có thể chứa thông tin nhạy cảm | Lấy mẫu, che dữ liệu, kiểm soát quyền |

Điều này giúp **đánh đổi chi phí – độ chi tiết – độ trễ** một cách có chủ đích, tránh áp dụng cùng QoS, cùng retention và cùng mức ưu tiên cho mọi dữ liệu.

## 9. Lựa chọn lưu trữ và xử lý trên cloud

Không phải một database duy nhất có thể phục vụ tốt mọi kiểu truy vấn:

| Nhu cầu | Lựa chọn kiến trúc phổ biến | Lưu ý |
|---|---|---|
| Trạng thái mới nhất của thiết bị | Key-value/state store hoặc device shadow/twin | Phải phân biệt desired state, reported state và thời điểm cập nhật |
| Dashboard giám sát theo thời gian | Time-series store/OLAP được thiết kế cho ghi và truy vấn theo thời gian | Cardinality theo labels, TTL, downsampling, index và chi phí |
| Lưu trữ dữ liệu thô dài hạn | Object storage phân vùng theo tenant/site/ngày | Định dạng cột, schema evolution, lifecycle và quyền dữ liệu |
| Cảnh báo streaming | Stream processor + rule engine | Event time, dedupe, window, xử lý muộn và thứ tự |
| Phân tích liên nhà máy/ML | Warehouse/lakehouse, batch training | Data quality, lineage, kiểm soát tập huấn luyện |
| Điều phối thiết bị và cấu hình | Registry/metadata store có audit | Tránh để luồng trạng thái phụ thuộc trực tiếp vào database phân tích |

Thông thường, telemetry đi qua **ingestion/broker → stream processing → các sink**, mỗi sink có retention và quyền phù hợp. Nếu broker/queue hoặc stream processor chịu tải kém, cần partition theo tenant/site/device sao cho giữ thứ tự cần thiết trong từng khóa, nhưng vẫn cân bằng tải. Một thiết bị phát lưu lượng quá lớn có thể tạo hot partition: thiết kế khóa phân vùng và xử lý ngoại lệ trước khi mở rộng.

### 9.1. Đặt giới hạn đa thuê bao và quản lý vòng đời dữ liệu

Trong mô hình phục vụ nhiều nhà máy/khách hàng, kiểm soát **tenant isolation** ở identity, topic, quyền đọc/ghi, key mã hóa, partition, truy vấn và dashboard. Không dựa duy nhất vào trường tenantId do client tự gửi để cấp quyền: danh tính đã xác thực cần xác định phạm vi tenant hợp lệ.

Định nghĩa vòng đời: dữ liệu raw có thời hạn riêng; aggregate dùng cho báo cáo lâu hơn; cảnh báo và audit có chính sách riêng; dữ liệu không cần thiết phải được xóa theo quy định. Với dữ liệu nhạy cảm, quản trị cả bản sao lưu, bản xuất, log và dữ liệu dùng huấn luyện.

## 10. Bảo mật từ thiết bị tới cloud

IoT có bề mặt tấn công đặc biệt: thiết bị đặt tại nhiều cơ sở vật lý, có tuổi thọ dài, firmware cũ và đôi khi thiếu cơ chế cập nhật. Một thiết kế tốt cần **identity, transport, software supply chain, mạng và quyền truy cập vật lý**.

### 10.1. Danh tính và khởi tạo tin cậy

Quy trình tối thiểu:

1. Đăng ký thiết bị/gateway vào inventory với serial, owner, site, loại thiết bị và trạng thái.
2. Cấp danh tính riêng cho thiết bị và khóa/chứng chỉ; ưu tiên bảo vệ khóa bằng TPM/secure element nếu phần cứng hỗ trợ.
3. Thiết bị xác thực máy chủ và được máy chủ xác thực, ví dụ **mTLS** khi phù hợp; không chia sẻ một bí mật cố định giữa toàn bộ fleet.
4. Áp dụng quyền nhỏ nhất trên topic, API, lệnh, dữ liệu và phạm vi site; giới hạn tốc độ.
5. Hỗ trợ xoay vòng/thu hồi chứng chỉ, đổi chủ sở hữu và loại thiết bị khỏi hệ thống một cách có audit.

**Bootstrap** là giai đoạn nhạy cảm: thiết bị mới phải xác minh nó đang liên hệ đúng dịch vụ trước khi nhận cấu hình bí mật hoặc chấp nhận phần mềm mới. Không đặt mã truy cập dài hạn trong firmware công khai.

### 10.2. Bảo vệ thiết bị và chuỗi cập nhật

Khi nền tảng hỗ trợ, dùng secure boot, firmware/application ký số, kiểm tra toàn vẹn, mã hóa dữ liệu nhạy cảm lưu cục bộ và cơ chế A/B update hoặc rollback an toàn. Thiết lập patch policy, vòng đời phiên bản, quản lý lỗ hổng, quản lý tài sản EOL và cách xử lý thiết bị đã mất liên lạc nhiều tháng.

Phân tách người có quyền **xem số đo**, **đổi cấu hình**, **đẩy firmware** và **gửi lệnh điều khiển**. Lệnh có tác động vật lý cần được giới hạn theo trạng thái thiết bị, thời gian hiệu lực, người duyệt và quy trình safety phù hợp.

### 10.3. Quyền riêng tư và tính toàn vẹn

Luồng camera, âm thanh, vị trí, định danh người vận hành hoặc dữ liệu sản xuất nhạy cảm có thể cần xử lý tại edge hoặc ẩn thông tin trước khi tải lên. Kiểm soát truyền và lưu theo luật/quy định áp dụng; giữ audit quyết định xuất dữ liệu. Bảo mật TLS ngăn nghe lén trên đường truyền nhưng **không xác minh cảm biến đo đúng**: vẫn cần kiểm tra chất lượng, hiệu chuẩn và phát hiện giả mạo bất thường.

## 11. Lệnh hai chiều và trạng thái thiết bị

Một số hệ thống chỉ cần telemetry. Nếu cần điều khiển từ xa, không gộp lệnh vào cùng xử lý “best effort” của dữ liệu đo.

Một command envelope nên có:

~~~json
{
  "commandId": "cmd-20261118-0142",
  "targetDeviceId": "pump-17",
  "type": "set_sampling_rate",
  "parameters": { "intervalSeconds": 10 },
  "issuedAt": "2026-11-18T08:30:00Z",
  "expiresAt": "2026-11-18T08:35:00Z",
  "requestedBy": "maintenance-operator",
  "expectedConfigVersion": "cfg-28"
}
~~~

Device/gateway phải kiểm tra danh tính người gửi, quyền thực hiện, danh sách loại lệnh được phép, phiên bản hiện tại, thời hạn, điều kiện vận hành và idempotency theo commandId. Trả về trạng thái **accepted → applied → verified/failed**, phân biệt “cloud đã gửi” với “thiết bị đã thực hiện”. Sau khi reconnect, **không chạy lệnh hết hạn**. Với lệnh nguy hiểm, cân nhắc yêu cầu xác nhận tại chỗ và độc lập với kết nối cloud.

Đối với trạng thái dạng digital twin/shadow, nên phân biệt:

- **Desired state:** cấu hình mong muốn từ control plane.
- **Reported state:** trạng thái thiết bị thực sự báo lại cùng timestamp và version.
- **Observed telemetry:** số đo/sự kiện thực tế, không nhất thiết trùng với trạng thái cấu hình.

Tránh hiểu desired state là bằng chứng việc thay đổi đã hoàn tất.

## 12. Triển khai, mở rộng và vận hành fleet

### 12.1. Lựa chọn mô hình triển khai

| Mô hình | Phù hợp khi | Đánh đổi |
|---|---|---|
| **MCU xử lý đơn giản** | Cảm biến tự lọc/thống kê với tài nguyên rất hạn chế | Tiết kiệm điện, nhưng khó chạy pipeline phức tạp |
| **Một gateway cho một cell/line** | Có nhiều thiết bị OT và cần adapter giao thức | Dễ triển khai, nhưng gateway có thể là điểm lỗi đơn |
| **Cụm edge server tại site** | Xử lý video/ML nặng, nhiều nguồn dữ liệu, cần HA cục bộ | Chi phí phần cứng, quản lý cụm, điện và làm mát |
| **Hybrid edge + cloud** | Cần hoạt động cục bộ và quản trị/analytics tập trung | Phức tạp đồng bộ, mạng, quan sát và quản trị phiên bản |
| **Cloud-centric telemetry** | Thiết bị có kết nối an toàn, dữ liệu nhỏ, không cần offline processing | Đơn giản hơn, phụ thuộc WAN và chi phí truyền |

Nếu dùng container tại edge, cần kiểm tra năng lực thiết bị, orchestration có cần không, persistence nằm ở đâu, độ ổn định sau mất điện và cơ chế phân phối artifact khi mất mạng. Không bắt buộc dùng Kubernetes cho một gateway nhỏ; cũng không nên dùng các script thủ công khó quan sát cho đội fleet hàng nghìn thiết bị.

### 12.2. Các chỉ số vận hành bắt buộc

Giám sát theo **device → gateway → đường truyền → cloud ingestion → pipeline → kho dữ liệu → ứng dụng**:

- **Device:** heartbeat, phiên bản firmware, pin/nguồn, clock skew, quality flag, tỷ lệ mất mẫu.
- **Gateway:** CPU/RAM, nhiệt độ, dung lượng/tuổi backlog, tốc độ vào/ra, lỗi adapter, disk wear nếu quan trọng.
- **Network:** trạng thái WAN, RTT, packet loss, reconnect, TLS/certificate expiry, lượng retry.
- **Ingestion/stream:** accepted/rejected, duplicate rate, partition lag, event-time lag, schema validation failures, dead-letter queue.
- **Data & business:** chênh lệch bản ghi, độ trễ dashboard/cảnh báo, tỷ lệ thiết bị báo cáo đúng kỳ, tỷ lệ cảnh báo được xử lý.
- **Deployment:** phần trăm thiết bị theo phiên bản, tỷ lệ lỗi rollout, canary health, số thiết bị không liên lạc kéo dài.

Một gateway không gửi dữ liệu có thể vì **máy ngừng hoạt động**, **mất nguồn**, **mạng đứt**, **cert hết hạn** hoặc **dịch vụ collector lỗi**. Cần phân biệt bằng heartbeat nhiều tầng và log có correlation ID; không suy ra mọi thiết bị đều khỏe chỉ vì broker vẫn hoạt động.

### 12.3. Khả năng mở rộng và vận hành nhiều site

Thiết kế ingestion theo mức tải cao điểm và tình huống **hàng trăm gateway reconnect đồng loạt**. Đặt quota theo tenant, rate limiting, retry jitter, cơ chế tách luồng ưu tiên và năng lực mở rộng sink. Đồng thời cần quy trình onboarding/offboarding site, cấu hình theo nhóm, chuẩn hóa nhãn thiết bị, runbook sự cố tại chỗ và hỗ trợ nhân viên vận hành ngoài giờ.

Khi dùng nhiều vùng cloud, xác định dữ liệu nào được replica, tác động về độ trễ/truy cập và ngân sách; nhiều vùng không tự động bảo đảm ingestion không mất dữ liệu. Nếu cloud mất dịch vụ, edge phải có cơ chế degradation đủ để hoàn thành trách nhiệm cục bộ đã cam kết.

## 13. Thiết kế các tình huống lỗi và kịch bản kiểm thử

| Sự cố giả định | Hành vi mong muốn | Phép thử cần thực hiện |
|---|---|---|
| WAN mất 24–72 giờ | Edge xử lý cục bộ, lưu dữ liệu ưu tiên, báo backlog | Ngắt WAN thật và đo dữ liệu còn/thiếu sau reconnect |
| Gateway reboot giữa batch upload | Không mất dữ liệu đã cam kết; bản ghi lặp được dedupe | Cắt điện/kill process ở điểm gửi và ở điểm ACK |
| Đồng hồ thiết bị sai 10 phút | Dữ liệu có quality flag, không phá window và cảnh báo | Inject clock skew, dữ liệu đến muộn và sai thứ tự |
| Cloud ingestion quá tải | Backoff, queue có hạn mức, cảnh báo vận hành | Load test reconnect storm và quota enforcement |
| Update ứng dụng edge lỗi | Thiết bị còn khả năng phục hồi/rollback phiên bản | Diễn tập rollout canary và rollback |
| Chứng chỉ thiết bị hết hạn/bị thu hồi | Không nhận dữ liệu/lệnh trái phép; có phương án khôi phục có kiểm soát | Kiểm thử xoay vòng, revoke, audit và trường hợp offline lâu |
| Một sensor bị nhiễu/sai hiệu chuẩn | Trạng thái đo không được chấp nhận vô điều kiện | Inject giá trị ngoài dải, missing/duplicate samples |
| Mất một site hoặc vùng cloud | Khả năng tại chỗ giữ an toàn; cloud phục hồi theo RTO/RPO | Diễn tập restore/replay và kiểm tra đối soát dữ liệu |

**RTO** (thời gian khôi phục mục tiêu) và **RPO** (mức mất dữ liệu tối đa theo thời gian) nên được xác định **riêng cho điều khiển tại chỗ, telemetry, cảnh báo và báo cáo**. Một dashboard có thể chịu mất kết nối vài giờ, nhưng cảnh báo nguy hiểm tại dây chuyền có thể không.

## 14. Đánh đổi theo Well-Architected

| Trụ cột đánh giá | Câu hỏi kiểm tra | Đánh đổi thường gặp |
|---|---|---|
| **Operational Excellence** | Quản lý phiên bản, quan sát và xử lý sự cố fleet thế nào? | Thêm fleet management tăng độ phức tạp ban đầu nhưng giảm thao tác tay |
| **Reliability** | Edge hoạt động và khôi phục thế nào khi cloud/WAN lỗi? | Thêm local queue và gateway HA tăng chi phí nhưng cải thiện tính liên tục |
| **Security** | Thiết bị và đường truyền được xác thực, phân vùng, cập nhật và thu hồi ra sao? | Kết nối kín, mTLS và signed update đòi hỏi quản lý khóa, cert và rollout |
| **Performance Efficiency** | Xử lý nào cần độ trễ thấp và nơi nào có compute phù hợp? | Chạy inference tại edge giảm trễ nhưng bị giới hạn CPU/RAM/điện |
| **Cost Optimization** | Raw/aggregate, băng thông, lưu trữ và vận hành có TCO nào? | Lọc tại edge giảm tải cloud nhưng thêm phần cứng và bảo trì |
| **Sustainability** | Có giảm truyền/lưu dữ liệu vô ích và tài nguyên nhàn rỗi? | Lấy mẫu thông minh giảm tài nguyên nhưng phải giữ dữ liệu có giá trị |

**Không có lựa chọn tối ưu cho mọi workload.** Đưa tất cả lên cloud đơn giản hóa quản lý compute nhưng phụ thuộc mạng. Đưa quá nhiều chức năng xuống edge tạo gánh nặng cập nhật, quan sát và đồng nhất phiên bản. Quyết định cần dựa trên bằng chứng đo tại site và mục tiêu nghiệp vụ.

## 15. Ví dụ thiết kế: bảo trì dự đoán cho dây chuyền sản xuất

Giả sử một doanh nghiệp vận hành **3 nhà máy**, mỗi nhà máy có **2.000 cảm biến rung/nhiệt**. Từ một số thiết bị, gateway nhận dữ liệu tần suất cao; đội bảo trì cần cảnh báo tại xưởng khi có bất thường, còn ban vận hành muốn so sánh xu hướng toàn bộ nhà máy trong 12 tháng. Mỗi site đôi khi mất WAN vài giờ.

### 15.1. Phân rã yêu cầu

| Yêu cầu | Hệ quả kiến trúc |
|---|---|
| Cảnh báo bất thường phải xuất hiện tại site dù WAN mất | Rule engine hoặc inference tại edge; local alert channel |
| Phân tích xu hướng nhiều site trong 12 tháng | Kho cloud có retention, metadata chuẩn và phân quyền |
| Mất WAN không gây bỏ toàn bộ dữ liệu | Durable queue, chính sách ưu tiên, sizing buffer và catch-up |
| Đối chiếu tín hiệu trước khi hỏng | Local raw ring buffer + upload theo sự kiện, metadata truy vết |
| Nhân sự tại mỗi site không rành lập trình | Quản trị/rollout tập trung, dashboard sức khỏe, runbook tại chỗ |
| Không cho cloud điều khiển trực tiếp PLC | Phân mạng và policy tách telemetry khỏi local control |

### 15.2. Lựa chọn thiết kế

**Tại nhà máy:** gateway công nghiệp đọc dữ liệu qua adapter được duyệt, chuẩn hóa đơn vị, tính đặc trưng và phát cảnh báo tại chỗ; giữ raw trong cửa sổ trượt; ghi thống kê/sự kiện quan trọng vào durable queue; chuyển HTTPS/MQTT ra cloud bằng kết nối xác thực. Có thể dùng một gateway dự phòng cho nhóm thiết bị cần độ sẵn sàng cao.

**Trên cloud:** broker/ingestion nhận dữ liệu, xác thực tenant/site, ghi event log có chính sách bền vững, stream processor tính dữ liệu theo thời gian sự kiện, lưu time series cho dashboard và object storage cho lịch sử/training. Control plane giữ inventory, OTA, config/model version riêng với ingestion.

**Mô hình phân tích:** huấn luyện từ dữ liệu nhiều nhà máy trên cloud, sau khi đánh giá độ chính xác và chất lượng dữ liệu sẽ đóng gói model ký số để suy luận tại edge. Mô hình được version hóa, canary và giám sát drift; quy tắc an toàn tại chỗ vẫn độc lập với đầu ra ML.

### 15.3. Một số ADR cần ghi

- **ADR-01 — Vị trí cảnh báo:** tại edge vì cần hoạt động khi WAN mất; cloud tổng hợp trạng thái cảnh báo.
- **ADR-02 — Dữ liệu gửi cloud:** chỉ số theo phút và raw theo sự kiện; xác nhận có đủ chi tiết để phân tích lỗi.
- **ADR-03 — Giao nhận:** at-least-once với eventId/dedupe thay vì giả định dữ liệu đến đúng một lần.
- **ADR-04 — Quản lý thiết bị:** identity riêng, mTLS, ký OTA, rollout có canary và khả năng phục hồi.
- **ADR-05 — Giới hạn hạ tầng:** đo tải collector/gateway và cloud trước khi nhân rộng sang cả 3 nhà máy.

Mỗi ADR cần ghi bối cảnh, lựa chọn thay thế, lý do, hệ quả, giả định và thời điểm xem xét lại. Ví dụ, nếu đo thực tế thấy dữ liệu thô cần phục vụ một yêu cầu pháp lý, ADR-02 phải đổi retention/chính sách tải lên.

## 16. Các anti-pattern phổ biến

**Gửi thẳng PLC/sensor lên Internet:** phơi bày thiết bị OT và làm luồng điều khiển chịu phụ thuộc WAN. Khắc phục bằng gateway/DMZ, giao thức đọc được kiểm soát và giữ safety logic tại chỗ.

**Không có local buffer vì “cloud luôn sẵn sàng”:** dữ liệu mất mỗi khi site gián đoạn. Thiết kế store-and-forward có sizing, giới hạn và bài thử ngắt mạng.

**Tin rằng QoS 2 là exactly-once của toàn pipeline:** xử lý trùng tại sink hoặc chênh lệch dashboard vẫn có thể xảy ra. Dùng eventId, idempotent sink, transactional boundary phù hợp và đối soát.

**Gửi toàn bộ raw vào một cơ sở dữ liệu duy nhất:** tăng phí và gây áp lực truy vấn, retention khó quản lý. Phân tầng dữ liệu theo giá trị và access pattern.

**Cấu hình hoặc chứng chỉ chung cho toàn bộ thiết bị:** mất một credential ảnh hưởng diện rộng, khó cô lập site. Cần danh tính riêng, quyền tối thiểu, thu hồi/rotate.

**Không version hóa schema và model:** một đợt OTA làm payload thay đổi khiến cloud và báo cáo hỏng. Xây dựng hợp đồng tương thích, canary và theo dõi rollout.

**Không kiểm soát lệnh cũ:** gateway reconnect rồi thực hiện lệnh đã hết thời hạn, gây thay đổi trạng thái không mong đợi. Lệnh phải có TTL, commandId, kiểm tra trạng thái và ACK thực thi.

**Chỉ theo dõi trạng thái broker:** ingestion vẫn chạy nhưng gateway backlog đầy hoặc sensor im lặng nhiều ngày. Cần quan sát xuyên suốt từ thiết bị đến người sử dụng dữ liệu.

## 17. Bài tập kiến trúc

Một công ty logistic có **500 xe tải**, mỗi xe gửi vị trí/độ rung/nhiệt độ hàng hóa mỗi 5 giây qua mạng di động. Trong một số hầm hoặc vùng xa, mạng mất 30–90 phút. Nhiệt độ hàng lạnh vượt ngưỡng cần phát âm báo ngay cho tài xế; phòng điều hành cần theo dõi đội xe và truy vết sự cố giao hàng trong 6 tháng.

Hãy thực hiện:

1. Vẽ đường telemetry và đường lệnh quản lý riêng, xác định **biên tin cậy** trên xe và cloud.
2. Chọn các xử lý phải nằm trên xe và các xử lý ở cloud; giải thích vì sao cảnh báo nhiệt không phụ thuộc Internet.
3. Tính payload/ngày nếu **500 xe × 1 bản ghi/5 giây × 200 byte** và đề xuất dung lượng buffer cho một xe khi mất mạng 90 phút (chưa tính overhead).
4. Mô tả xử lý dữ liệu trùng, tới muộn và việc thiết bị bị sai giờ.
5. Nêu ít nhất ba kiểm thử failover và ba chỉ số dashboard để đánh giá rollout.

**Gợi ý giải:**

- Trên xe: collector + quy tắc nhiệt, âm báo cục bộ, durable queue và kết nối di động; cloud: ingestion, time-series, lưu lịch sử, dashboard, fleet management. Không gửi lệnh gây nguy hiểm cho xe qua đường telemetry.
- Số bản ghi mỗi ngày toàn đội là \(500 \times 86\,400 / 5 = 8\,640\,000\). Payload toàn đội là \(8\,640\,000 \times 200 = 1{,}728\ \text{GB/ngày}\) (hệ thập phân). Một xe trong 90 phút tạo \(90 \times 60 / 5 = 1\,080\) bản ghi, tức khoảng **216 KB payload**. Bộ đệm thực tế cần thêm overhead, headroom, replay và chính sách dữ liệu khác.
- Dùng deviceId + bootId + sequence hoặc eventId để dedupe; phân biệt observedAt với thời điểm cloud nhận; cảnh báo ngay tại xe và đánh dấu dữ liệu đến muộn.
- Diễn tập ngắt sóng, reboot khi đang gửi, bộ đệm đầy; theo dõi tuổi backlog, số xe offline, lag cloud và tỷ lệ cảnh báo xác nhận.

Không nên chỉ lấy dung lượng 216 KB làm cấu hình storage: bản ghi thực tế có thể lớn hơn, có log/ảnh và cần bảo đảm an toàn dữ liệu khi thiết bị bị ngắt nguồn đột ngột.

## 18. Checklist đánh giá kiến trúc trước khi triển khai

- [ ] Các kịch bản nghiệp vụ được diễn đạt thành chỉ số cụ thể: độ trễ, mất WAN, retention, RTO/RPO, giá trị dữ liệu.
- [ ] Đã phân định rõ local safety control, telemetry và remote command; không tạo đường tác động vật lý thiếu kiểm soát.
- [ ] Có inventory thiết bị, sơ đồ vùng OT/DMZ/cloud, luồng mạng và người chịu trách nhiệm từng thành phần.
- [ ] Giao thức/adapter được chọn theo tính chất thiết bị, bảo mật và tải; không truy cập trực tiếp thiết bị nhạy cảm từ Internet.
- [ ] Thiết kế edge có giới hạn CPU/RAM/storage, kiểm soát backpressure, store-and-forward và quan sát backlog.
- [ ] Đã tính tải bình thường, tải cao điểm và reconnect storm; đủ băng thông để gửi bù sau thời gian offline.
- [ ] Có schema/version, eventId, đồng hồ/quality flag, dedupe và xử lý dữ liệu tới muộn.
- [ ] Dữ liệu raw/aggregate/alert có retention, quyền truy cập, chính sách dữ liệu nhạy cảm và mục đích rõ ràng.
- [ ] Có thiết bị identity, xác thực hai chiều khi phù hợp, quản lý khóa/chứng chỉ, ký phần mềm, canary OTA và rollback.
- [ ] Dashboard có đường quan sát từ cảm biến đến ingestion và sink; cảnh báo khi mất dữ liệu hoặc gateway im lặng.
- [ ] Đã diễn tập mất mạng, mất điện, failover, khôi phục dữ liệu và nâng cấp lỗi trong điều kiện tương tự thực tế.
- [ ] Có ADR ghi rõ vì sao đặt từng tính toán ở edge/cloud và các đánh đổi độ tin cậy, bảo mật, hiệu năng, chi phí, vận hành.

**Kết luận thiết kế:** một hệ IoT edge–cloud tốt duy trì được chức năng cục bộ cần thiết ngay cả khi cloud/WAN không sẵn sàng, gửi dữ liệu có ngữ nghĩa và khả năng đối soát rõ ràng, đồng thời khai thác cloud cho phân tích và quản trị ở quy mô lớn. Phân định trách nhiệm, đo lường lưu lượng, kiểm chứng lỗi và bảo vệ vòng đời thiết bị là các quyết định quan trọng hơn việc chọn tên một dịch vụ cloud cụ thể.
