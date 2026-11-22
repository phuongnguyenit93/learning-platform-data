# Event Hubs namespace, partition và consumer group

Một công ty có 50.000 thiết bị IoT liên tục gửi nhiệt độ, tọa độ và trạng thái hoạt động. Dữ liệu cần được đưa vào hệ thống phân tích thời gian gần thực, đồng thời một nhóm khác lưu bản gốc để phân tích lịch sử và bộ phận vận hành kiểm tra cảnh báo bất thường. Nếu mọi thiết bị gọi trực tiếp tới từng ứng dụng xử lý, mạng lưới phụ thuộc sẽ phức tạp và dễ quá tải khi lưu lượng tăng đột biến.

**Azure Event Hubs** là nền tảng **thu nhận và phân phối luồng sự kiện (event streaming)** với thông lượng lớn. Producer ghi các event vào một Event Hub; dữ liệu được tổ chức trong những **partition** có thứ tự riêng. Những ứng dụng downstream dùng các **consumer group** để đọc cùng một luồng một cách độc lập, theo vị trí đã đọc của từng partition.

Bài này thuộc chương **Sự kiện và dữ liệu streaming** của module `CLOUD_PROVIDERS_AZURE`. Module giới thiệu hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu; tiếp đó hướng dẫn triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng trên Azure. Ở đây, mục tiêu là thiết kế đúng ba cấp **namespace – partition – consumer group**, đồng thời hiểu những hệ quả về **ordering, scaling, retention, checkpoint, replay, quyền truy cập và chi phí**.

> Các ví dụ sử dụng tên và dữ liệu giả lập. SKU, tính năng networking, retention, throughput, giới hạn partition/consumer group và cú pháp Azure CLI có thể thay đổi theo tier, API và region. Kiểm tra tính năng trên namespace thật và chỉ chạy lệnh tạo tài nguyên trong subscription/lab được phê duyệt.

## 1. Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

1. Mô tả **Event Hubs namespace**, **Event Hub**, **partition**, **consumer group** và **event producer/consumer**.
2. Vẽ đường đi event từ thiết bị tới nhiều nhóm phân tích đọc cùng một Event Hub.
3. Phân biệt **Azure subscription** với **Event Hubs consumer group**.
4. Giải thích **partition key**, partition ID, offset, sequence number và enqueued time.
5. Biết vì sao chỉ kỳ vọng **thứ tự trong một partition**, không phải trên toàn Event Hub.
6. Chọn số partition dựa trên tính song song, khóa phân vùng và yêu cầu dài hạn.
7. Thiết kế nhiều consumer groups độc lập, hiểu cách chia partition giữa những consumer cùng nhóm.
8. Phân biệt **retention** của Event Hubs với **checkpoint** của ứng dụng; thực hiện replay khi dữ liệu còn lưu.
9. Chọn mô hình throughput capacity theo Basic/Standard/Premium/Dedicated ở mức khái quát.
10. Sử dụng Azure Portal, Azure CLI và Python SDK để tạo/kiểm tra Event Hub và gửi/nhận event trong môi trường lab.
11. Áp dụng Microsoft Entra ID/managed identity, Azure RBAC, private networking và giám sát.
12. Chẩn đoán các lỗi phổ biến như consumer lag, hot partition, checkpoint sai, throttling và event không đến downstream.

## 2. Khi nào cần Event Hubs?

Một event có thể là một điểm đo từ cảm biến, hành vi clickstream, log ứng dụng, thay đổi trạng thái thiết bị hoặc bản ghi giao dịch dùng cho analytics.

Ví dụ:

```json
{
  "deviceId": "sensor-1024",
  "eventType": "TemperatureMeasured",
  "occurredAtUtc": "2026-11-20T09:00:00Z",
  "temperatureCelsius": 27.4,
  "site": "factory-hcm"
}
```

Đặc điểm của streaming:

- Producer phát event liên tục, thường với tần suất cao.
- Consumer có thể xử lý ngay hoặc đọc lại từ một vị trí trong lịch sử còn retention.
- Một luồng dữ liệu có nhiều cách sử dụng: phân tích, lưu trữ, phát hiện bất thường.
- Việc producer gửi được event **không có nghĩa** một downstream consumer đã xử lý.
- Các consumer có thể tạm ngừng rồi bắt kịp khi hoạt động trở lại, miễn dữ liệu chưa bị loại khỏi thời hạn lưu giữ.

Event Hubs hữu ích với **telemetry, clickstream, log ingestion, analytics pipeline, stream processing** và các luồng dữ liệu lớn. Nếu công việc cần queue, dead-letter, settlement/lock, retry theo từng command, thứ tự nghiệp vụ đặc biệt hoặc transaction-based messaging, cần đánh giá **Azure Service Bus**. Hai dịch vụ có mô hình xử lý khác nhau.

## 3. Bốn khái niệm phải phân biệt

| Thành phần | Bản chất | Tác dụng |
|---|---|---|
| **Namespace** | Ranh giới tài nguyên Event Hubs, region, tier, endpoint, auth và networking. | Chứa một hoặc nhiều Event Hubs, quản lý quyền, chi phí và capacity. |
| **Event Hub** | Luồng sự kiện logic được ghi vào dịch vụ. | Producer gửi event đến tên hub; consumer đọc từ hub. |
| **Partition** | Một log có thứ tự trong Event Hub. | Chia tải ghi/đọc và cung cấp sequence/offset theo partition. |
| **Consumer group** | Góc nhìn tiêu thụ độc lập trên cùng Event Hub. | Cho các ứng dụng đọc cùng dữ liệu theo tiến độ riêng. |

Một kiến trúc minh họa:

```text
Azure subscription: Production
└── Resource group: rg-streaming-prod
    └── Event Hubs namespace: evh-platform-prod
        ├── Event Hub: device-telemetry
        │   ├── Partition 0: E0, E4, E9, ...
        │   ├── Partition 1: E1, E5, ...
        │   ├── Partition 2: E2, E6, ...
        │   └── Partition 3: E3, E7, E8, ...
        │
        │   Consumer group: realtime-analytics
        │   Consumer group: raw-archiver
        │   Consumer group: alert-engine
        │
        └── Event Hub: application-events
            ├── Partition 0
            ├── Partition 1
            └── Consumer group: diagnostics
```

**Không nhầm** Azure subscription — đối tượng thanh toán và quản trị Azure — với Event Hubs consumer group. Consumer group chỉ tổ chức cách đọc stream của **một Event Hub**, không phải subscription Azure và cũng không phải bản sao vật lý của event.

## 4. Namespace: điểm vào và ranh giới quản trị

Một Event Hubs namespace có tên và endpoint dạng:

```text
<namespace-name>.servicebus.windows.net
```

Namespace xác định các chính sách quan trọng:

1. **Pricing tier, region và capacity:** loại SKU và mức tài nguyên đáp ứng tốc độ gửi/nhận.
2. **Authentication/authorization:** Microsoft Entra ID/managed identity và/hoặc SAS theo cấu hình.
3. **Networking:** public access, network rules, Private Endpoint khi SKU hỗ trợ.
4. **Giới hạn dịch vụ:** throughput, số Event Hubs, số consumer groups, partitions, connections, event size...
5. **Monitoring:** metrics, diagnostic settings, alerts, resource logs.
6. **Môi trường và blast radius:** Production/Development có nên dùng namespace riêng?
7. **Recovery:** yêu cầu tính sẵn sàng, DR, phụ thuộc vùng và phương án lưu dữ liệu lịch sử.

### Namespace không phải Event Hub

Tạo namespace thành công **không tạo một luồng telemetry mặc định** cho mọi ứng dụng. Bạn cần tạo một **Event Hub entity** với số partition và retention phù hợp. Producer kết nối đúng namespace nhưng chỉ định tên Event Hub không tồn tại sẽ vẫn thất bại.

### Tách namespace theo môi trường

Ví dụ:

```text
evh-iot-dev       → thiết bị giả lập, log và quyền thử nghiệm
evh-iot-staging   → kiểm thử tải / schema / consumer deployment
evh-iot-prod      → dữ liệu thật, logging/budget/access nghiêm ngặt
```

Không bắt buộc một namespace cho từng microservice. Hãy quyết định theo phạm vi chia sẻ quota/capacity, security boundaries, quyền sở hữu, vị trí dữ liệu, chi phí và hậu quả nếu có lỗi. Nếu nhiều đội cùng namespace, cần đo tổng ingress/egress và kiểm soát tác động của một producer quá tải đối với các luồng khác.

## 5. Event Hub entity: luồng dữ liệu chứ không phải queue công việc

Event Hub là một tập các partition append-only theo semantics streaming. Mỗi event mới được ghi vào một partition, được gắn **sequence number** và **offset** của partition đó, cùng thời điểm được dịch vụ tiếp nhận.

```text
Producer A ─────┐
                │
Producer B ─────┼──> Event Hub: device-telemetry
                │         |
Producer C ─────┘         +-- Partition 0: [event][event][event]
                          +-- Partition 1: [event][event]
                          +-- Partition 2: [event][event][event]
                          +-- Partition 3: [event]
```

Producer không gửi riêng tới từng consumer group. **Một bản event được ghi vào luồng**, và các nhóm đọc dữ liệu đã lưu tùy vị trí của chính chúng.

### Event có bị xóa sau khi consumer đọc không?

**Không theo mô hình queue work item.** Việc một consumer group đọc đến offset cuối không làm event biến mất khỏi Event Hub. Event vẫn có thể được nhóm khác đọc lại trong khoảng **retention** còn hiệu lực.

Đây là khác biệt lớn với Service Bus Queue:

- Queue/Peek-Lock: consumer xử lý rồi Complete để message rời queue.
- Event Hubs: consumer đọc một vị trí trong stream; event được giữ theo retention, không có Complete/Abandon/DeadLetter chuẩn cho từng event theo kiểu Service Bus Queue.

Event Hubs không tạo DLQ per consumer group tự động như Service Bus. Nếu cần cách ly event sai schema, ứng dụng nên thiết kế **quarantine stream, Storage hoặc hệ thống xử lý lỗi riêng**, với chính sách bảo mật và replay.

## 6. Partition là gì?

Một **partition** là đơn vị chia dữ liệu và mở rộng mức độ song song trong một Event Hub. Trong mỗi partition, những event đã được tiếp nhận có **thứ tự xác định**.

Ví dụ hai thiết bị:

```text
Partition 0:
  seq=0 device-A 08:00
  seq=1 device-A 08:01
  seq=2 device-A 08:02

Partition 1:
  seq=0 device-B 08:00
  seq=1 device-B 08:01
```

Ở sơ đồ, sequence number được minh họa bắt đầu từ 0 trong từng partition; số thật do broker cấp và không nên tự đoán. **Sequence number của partition 0 và partition 1 không tạo thành một sequence duy nhất trên toàn hub.**

### Partition ảnh hưởng ba điều

- **Write distribution:** event từ producers được phân vào các partition.
- **Read parallelism:** một ứng dụng có thể xử lý nhiều partition song song.
- **Ordering scope:** có thể giữ thứ tự theo các event trong **cùng partition**, nhưng không bảo đảm thứ tự toàn cục giữa partitions.

Hãy tránh khẳng định “Event Hubs luôn bảo toàn thứ tự sự kiện gửi từ mọi producer”. Điều đó không đúng khi dữ liệu đi qua nhiều partitions, producers song song, retries hoặc khi ứng dụng downstream xử lý đồng thời.

## 7. Partition key: đưa event liên quan vào cùng partition

Producer có thể chỉ định **partition key** để các event có cùng giá trị khóa thường được hash/route tới cùng partition theo cơ chế dịch vụ.

Ví dụ yêu cầu giữ thứ tự theo thiết bị:

```text
Event(deviceId="sensor-101", sample=1) ─┐
Event(deviceId="sensor-101", sample=2) ─┼──> same partition
Event(deviceId="sensor-101", sample=3) ─┘

Event(deviceId="sensor-205", sample=1) ────> another partition,
                                               hoặc cũng có thể cùng partition
```

**Partition key không tạo một partition riêng cho mỗi deviceId.** Nhiều khóa khác nhau có thể được hash vào cùng partition.

### Chọn khóa thế nào?

| Partition key | Khi hữu ích | Rủi ro |
|---|---|---|
| `deviceId` | Giữ thứ tự các bản ghi của một thiết bị. | Thiết bị cực kỳ “nóng” có thể tạo hot partition. |
| `customerId` | Phân tích chuỗi hành động theo khách hàng. | Một số khách hàng có lưu lượng cao bất thường. |
| `orderId` | Xử lý event của cùng đơn hàng theo thứ tự của partition. | Một đơn hàng bất thường phát lượng lớn event. |
| Không chỉ định key | Khi cần phân phối tải và không cần gom event theo khóa. | Không có cam kết các event liên quan ở cùng partition. |
| Chỉ định partition ID trực tiếp | Workload rất đặc thù cần mapping explicit. | Gắn cứng topology, khó scale và dễ mất cân bằng. |

Không thể kỳ vọng một partition key giải quyết mọi bài toán ordering. Ứng dụng phải bảo đảm phát event đúng trình tự khi quan trọng; một retry muộn có thể khiến event được ghi **sau** các event tiếp theo dù chúng mang thời gian nghiệp vụ cũ hơn.

### Cạm bẫy khi đổi partition count

Nếu số partition tăng và dịch vụ/tier hỗ trợ thay đổi, kết quả hash mapping của partition keys **có thể thay đổi**. Event mang cùng key ở các thời điểm trước/sau thay đổi không nhất thiết tiếp tục ở cùng một partition. Vì vậy cần đánh giá rủi ro đối với các workflow yêu cầu thứ tự theo key, việc replay và consumer checkpoint trước khi mở rộng partition count.

## 8. Hot partition: tại sao có nhiều partition vẫn chậm?

Một **hot partition** xuất hiện khi phần lớn event bị gửi vào một hoặc vài partition thay vì được phân phối tương đối đều.

Ví dụ:

- Event Hub có 8 partitions.
- Khoảng 80% event mang partition key `global`.
- Các event cùng key tập trung vào một partition.
- Những partition còn lại ít tải, trong khi một reader xử lý hot partition bị nghẽn.

Tăng số consumer instances **không nhất thiết** làm một partition có thể được xử lý đồng thời bởi hàng chục consumer trong cùng consumer group; thông thường một partition có một owner tại một thời điểm trong mô hình processor cân bằng. Bản chất hot partition nằm ở **key distribution và tốc độ xử lý của partition đó**.

Biện pháp:

1. Đo số event/bytes/lag theo partition nếu công cụ hỗ trợ.
2. Kiểm tra top partition keys và độ lệch tải.
3. Nếu không cần ordering theo khóa hiện tại, chọn key có độ phân tán tốt hơn.
4. Với một key quá nóng, cân nhắc sharding key có kiểm soát **chỉ khi chấp nhận mất ordering toàn key** hoặc có lớp tái sắp thứ tự downstream.
5. Tối ưu consumer processing và batch/vectorization.
6. Chỉ đổi partition count sau khi cân nhắc tính năng, capacity và tác động mapping.

**Không dùng random key** nếu nghiệp vụ cần thứ tự theo từng thiết bị/đơn hàng; randomization có thể cải thiện cân bằng tải nhưng làm mất ranh giới thứ tự cần thiết.

## 9. Offset, sequence number, enqueued time

Ba trường thường thấy trong metadata của event đã được Event Hubs tiếp nhận:

| Trường | Ý nghĩa | Phạm vi |
|---|---|---|
| **Partition ID** | Partition chứa event. | Trong Event Hub. |
| **Sequence number** | Vị trí số nguyên tăng dần do broker cấp theo partition. | **Từng partition**. |
| **Offset** | Vị trí trong log partition, do dịch vụ cung cấp dưới dạng metadata. | **Từng partition**. |
| **Enqueued time** | Thời điểm Event Hubs tiếp nhận event. | Metadata của event; khác timestamp nghiệp vụ trong body. |

Ví dụ:

```text
Event Hub: device-telemetry
Partition 2:
  [seq 304, offset X] sensor-101 at 08:00
  [seq 305, offset Y] sensor-205 at 08:01
  [seq 306, offset Z] sensor-101 at 08:02
```

Offset `X/Y/Z` là ký hiệu minh họa. Trong chương trình, hãy dùng offset/sequence number do SDK trả về, không tự suy ra bằng cách cộng độ dài payload.

### Enqueued time khác occurredAtUtc

Một thiết bị có thể tạo event lúc 08:00 nhưng vì mất mạng đến 08:15 mới gửi lên Event Hubs.

- `occurredAtUtc = 08:00` là thời điểm do thiết bị/ứng dụng đưa vào payload.
- `enqueued_time = 08:15` là thời điểm dịch vụ nhận event.
- Consumer xử lý lúc 08:17.

Các mốc này phục vụ những phép đo khác nhau: độ trễ mạng/producer, queueing/processing lag và event-time watermark. Không dùng enqueued time thay thế hoàn toàn event time khi phân tích những sự kiện đến muộn.

## 10. Retention: dữ liệu tồn tại trong cửa sổ thời gian

Azure Event Hubs lưu event trong một **cửa sổ retention** tùy cấu hình và tier. Event không bị xóa ngay khi một consumer đọc, nhưng event cũ có thể được loại khỏi phạm vi đọc khi hết thời hạn được giữ.

```text
Time  ──────────────────────────────────────────────>
             |<------ retention window ------>|
             Old events                Newest events
             |
             +-- Sau khi hết retention, replay không còn
                 những event đã bị loại khỏi luồng nguồn
```

### Những kết luận quan trọng

- Consumer nhóm A có thể đọc chậm hơn nhóm B mà không ảnh hưởng trực tiếp vị trí đọc của B.
- Nếu nhóm A ngừng quá lâu và offset cần đọc đã vượt ra ngoài retention, **không thể chỉ nhờ Event Hubs để replay lại các event đó**.
- Retention là thuộc tính lưu dữ liệu của Event Hub, **không phải deadline của một consumer group**.
- Tăng retention giúp có thêm thời gian recovery, nhưng có chi phí/hạn mức và không tự phục hồi dữ liệu đã quá thời hạn trước khi thay đổi.
- Một hệ thống yêu cầu giữ dữ liệu trong nhiều tháng/năm nên **xuất/lưu dữ liệu** sang nền tảng lưu trữ dài hạn phù hợp.

### Capture và lưu lịch sử

**Event Hubs Capture**, khi tier và cấu hình hỗ trợ, có thể tự động ghi stream nhận được vào Azure Blob Storage hoặc ADLS Gen2 theo định dạng/đích được hỗ trợ (thường gặp là Avro). Tính năng hữu ích để xây kho dữ liệu thô và hỗ trợ replay lịch sử từ Storage.

**Capture không tự tạo một consumer group mới** và cũng không thay đổi nguyên tắc đọc offset của ứng dụng. Cần thiết kế riêng workflow đọc lại dữ liệu đã capture nếu vượt retention gốc hoặc phải nạp lại vào pipeline.

## 11. Consumer group: nhiều góc nhìn trên một stream

**Consumer group** đại diện cho một tập consumer cùng phối hợp đọc Event Hub dưới một **góc nhìn logic**.

Ví dụ:

```text
Event Hub: device-telemetry
   P0 ─ P1 ─ P2 ─ P3
    |    |    |    |
    +----+----+----+--> Consumer group: realtime-analytics
    |    |    |    |       Worker A / Worker B
    |    |    |    |
    +----+----+----+--> Consumer group: raw-archiver
    |    |    |    |       Worker C
    |    |    |    |
    +----+----+----+--> Consumer group: anomaly-detector
                           Worker D / Worker E / Worker F
```

Mỗi group có thể đọc cùng events nhưng ở tiến độ khác nhau:

- `realtime-analytics` đọc gần đầu stream hiện tại, tạo dashboard.
- `raw-archiver` đọc và ghi event vào Storage, tạm chậm vài phút.
- `anomaly-detector` phân tích window khác, có thể cần replay trong retention.

### Consumer group có tạo bản sao message không?

**Không theo nghĩa dữ liệu được nhân bản vật lý cho mỗi group như topic subscription của Service Bus.** Các group là những góc nhìn đọc trên **các partition có cùng dữ liệu gốc**. Có thể có nhiều nhóm đọc độc lập, nhưng dữ liệu được giữ chung trong Event Hub theo retention.

Mỗi group vẫn làm tăng **read operations, egress và chi phí xử lý downstream**, nên nhiều groups không hoàn toàn “miễn phí”. Quyền truy cập và giới hạn số consumer groups phụ thuộc tier/cấu hình.

## 12. Một consumer group, nhiều consumers: cách chia partition

Trong nhóm sử dụng EventProcessor-style SDK có phối hợp ownership/checkpoint, các active consumers trong **cùng group** sẽ phân chia partition để xử lý song song.

Ví dụ Event Hub có 4 partitions:

| Số consumer instances hoạt động cùng group | Phân công logic kỳ vọng | Hệ quả |
|---:|---|---|
| 1 | Một instance xử lý cả P0–P3. | Dễ vận hành, parallelism giới hạn bởi một instance. |
| 2 | Mỗi instance có thể giữ khoảng 2 partitions. | Tăng khả năng xử lý song song. |
| 4 | Mỗi instance có thể giữ khoảng 1 partition. | Có thể khai thác tối đa 4 partitions ở mức ownership. |
| 6 | Tối đa 4 instances giữ partition tại cùng thời điểm; còn lại không có partition để xử lý. | Thêm instance không tự tăng parallelism theo partition. |

Phân công là **ví dụ kỳ vọng**; sự cân bằng thực tế phụ thuộc SDK, partition ownership, liveness, thời gian rebalance và tốc độ xử lý. Trong một số loại protocol hoặc client đơn giản, cơ chế điều phối khác nhau; không nên mặc định mọi receiver sẽ tự cân bằng chỉ vì cùng consumer group.

### Nếu hai consumers đọc cùng group nhưng dùng checkpoint riêng?

Điều này có thể dẫn đến **xử lý trùng, tranh chấp ownership, không đồng bộ vị trí** hoặc hành vi ngoài ý muốn, tùy SDK và giao thức. Khi dùng EventProcessorClient/Blob checkpoint, hãy bảo đảm:

- Các instances **cùng một application group** chia sẻ checkpoint store theo cấu hình phối hợp.
- Các **consumer groups khác nhau** nên dùng checkpoint scope/container hoặc cơ chế cách ly rõ ràng.
- Một application không vô tình chạy cả hai phiên bản dùng chung consumer group/checkpoint store theo cách gây tranh chấp ngoài kế hoạch.
- Khi rollout, có thời gian rebalance, thông báo trạng thái và idempotency.

## 13. Checkpoint là gì và nằm ở đâu?

**Checkpoint** lưu thông tin **consumer đã xử lý đến vị trí nào** trong mỗi partition, để sau khi restart hoặc rebalance có thể tiếp tục từ một vị trí hợp lý.

```text
Event Hub P0:  [100][101][102][103][104][105][106]
                               ^
                               |
Consumer processed through 103, checkpoint at 103

Restart → đọc tiếp theo cơ chế SDK/checkpoint position,
          tránh bắt đầu lại toàn bộ partition
```

Event Hubs **không tự lưu checkpoint của mọi ứng dụng consumer** như một trạng thái xử lý nghiệp vụ mặc định. Với **Azure Event Hubs SDK event processor**, một cách thông dụng là dùng **Azure Blob Storage checkpoint store** cho partition ownership và checkpoints. Các giải pháp khác (Spark, Kafka compatibility, Stream Analytics...) có cơ chế lưu trạng thái riêng.

### Phân biệt offset và checkpoint

- **Offset/sequence number:** do Event Hubs gắn cho event trong partition.
- **Checkpoint:** do **consumer/application** ghi, cho biết vị trí có thể tiếp tục.
- **Consumer lag:** khoảng cách giữa vị trí gần đầu hiện tại của partition và tiến độ tiêu thụ được quan sát/checkpoint, tùy cách đo.

**Checkpoint không xóa event** khỏi Event Hub. Nó cũng không tự đảm bảo mọi side effect của ứng dụng đã commit.

### Khi nào ghi checkpoint?

Cách an toàn thông thường:

1. Nhận event hoặc một batch từ partition.
2. Xử lý và ghi kết quả nghiệp vụ/analytics thành công.
3. Chỉ sau đó mới checkpoint vị trí tương ứng.
4. Nếu xử lý thất bại, giữ khả năng retry và tránh checkpoint bỏ qua dữ liệu chưa xử lý.
5. Khi restart, ứng dụng có thể đọc lại một số event gần checkpoint; handler nên idempotent.

Nếu checkpoint **trước khi ghi kết quả** rồi tiến trình crash, dữ liệu có thể bị đánh dấu đã xử lý trong khi thực tế chưa được ghi downstream. Nếu checkpoint quá thưa, restart có thể đọc lại nhiều event và mất thêm thời gian.

## 14. Consumer group không phải cơ chế exactly-once

Một consumer đọc event X, ghi vào database thành công nhưng crash trước checkpoint. Khi khởi động lại, event X có thể được đọc lại.

```text
Read X → Write DB success → crash → no checkpoint
                                      |
                                      v
                                  Restart
                                      |
                                      v
                                  Read X again
```

Do đó, một consumer đáng tin cậy cần:

- **Idempotent processing**: không tạo side effect lặp khi đọc lại.
- **Event ID hoặc business key** ổn định; unique constraint khi lưu database.
- **Checkpoint sau khi commit** kết quả quan trọng.
- **Retry/backoff** cho lỗi tạm thời.
- **Quarantine** cho event không thể parse hoặc sai schema.
- **Đối soát** để phát hiện dữ liệu thiếu hoặc kết quả sai.

Đừng suy diễn một consumer group tương đương một subscription queue với cơ chế Complete hoặc một guarantee exactly-once cho giao dịch bên ngoài. Consumer group tổ chức **đọc stream**, không giải quyết giao dịch distributed end-to-end.

## 15. Điểm bắt đầu đọc: earliest, latest, offset, time

Khi ứng dụng chưa có checkpoint hoặc muốn replay có kiểm soát, SDK thường cho phép chọn điểm bắt đầu đọc:

| Ý định | Cách định hướng | Hệ quả |
|---|---|---|
| Đọc từ đầu dữ liệu còn retention | Earliest / bắt đầu retained partition. | Có thể phải xử lý khối lượng lớn và event cũ. |
| Chỉ đọc event mới sau khi chạy | Latest. | Có thể bỏ qua event đã tồn tại trước lúc consumer bắt đầu. |
| Replay từ một offset/sequence | Chọn vị trí cụ thể theo API/SDK hỗ trợ. | Phụ thuộc offset còn trong retention. |
| Replay từ thời điểm | Chọn enqueued time / time offset nếu SDK hỗ trợ. | Dựa trên thời gian broker nhận, không hẳn business event time. |
| Resume có checkpoint | EventProcessor đọc lại theo checkpoint đã lưu. | Điểm bắt đầu cấu hình thường áp dụng khi không có checkpoint hợp lệ. |

**Nếu consumer có checkpoint**, cấu hình `starting_position="-1"` trong code có thể **không đưa ứng dụng về đầu stream**: processor sẽ ưu tiên checkpoint đã lưu theo cách SDK triển khai. Muốn replay từ đầu phải thiết kế **consumer group/checkpoint store hoặc offset reset workflow riêng**, có kiểm soát tránh gây duplicate side effects.

### Cẩn thận khi reset

Xóa checkpoint hoặc đổi tên checkpoint container để “đọc lại hết” có thể làm:

- Cả nhóm reprocess nhiều ngày dữ liệu.
- Ghi trùng vào database/lake.
- Tăng throughput egress và chi phí.
- Trigger nhiều cảnh báo/nghiệp vụ ngoài dự kiến.

Chỉ reset sau khi đã xác định retention, phạm vi, hiệu ứng downstream, idempotency và ngân sách.

## 16. Consumer group khác Service Bus topic subscription thế nào?

| Khía cạnh | Event Hubs consumer group | Service Bus topic subscription |
|---|---|---|
| Mục tiêu chính | Đọc cùng stream theo các ứng dụng độc lập. | Gửi message pub/sub tới từng subscription với delivery/settlement. |
| Dữ liệu | Stream giữ chung trong các partitions theo retention. | Mỗi subscription có backlog message tương ứng theo filter. |
| Tiến độ | Consumer quản lý checkpoint/offset. | Broker quản lý message state, lock/settlement theo entity. |
| Sau khi đọc | Event vẫn có trong retention. | Message có thể bị Complete và rời subscription. |
| Ordering | Theo partition. | Tùy sessions và cơ chế Service Bus. |
| Retry/poison | Ứng dụng/processor xây workflow riêng. | Có Abandon, DeadLetter và DLQ subqueue. |
| Replay | Đọc lại offset còn retention. | Không tự replay message đã Complete. |
| Scaling | Giới hạn song song tự nhiên bởi số partitions trong nhóm. | Competing consumers, lock/session và broker semantics. |

Một hệ thống có thể dùng **Event Hubs cho telemetry high throughput** và **Service Bus cho business commands**, không cần chọn một dịch vụ để giải mọi tình huống.

## 17. Chọn số partition khi thiết kế

Số partition là quyết định quan trọng vì ảnh hưởng khả năng đọc song song và ordering.

Cân nhắc những câu hỏi:

1. Có bao nhiêu ứng dụng consumer cần xử lý song song mỗi group?
2. Tốc độ vào/ra dự kiến theo event/s và MB/s?
3. Có key nào cần giữ thứ tự không?
4. Số lượng khóa có đủ đa dạng để tải phân bố đều?
5. Kích thước payload/logic consumer có gây chậm một partition?
6. Có cần dự phòng tăng tải trong 6–12 tháng?
7. Tier/region có cho phép tạo/tăng partition count không, và giới hạn cụ thể là gì?
8. Ứng dụng có chịu được mapping của partition keys thay đổi khi mở rộng không?

### Ví dụ minh họa

Một Event Hub dự kiến 40.000 events/giây. Mỗi consumer instance có thể xử lý khoảng 8.000 events/giây **trong điều kiện đo thật**, và các key phân bố đều.

```text
Số instance tối thiểu theo processing rate ≈ 40.000 / 8.000 = 5
```

Tuy nhiên đây mới là ước lượng compute. Nếu muốn một consumer group chạy tối thiểu 5 workers với mỗi worker có partition ownership, Event Hub cần đủ partition song song và throughput capacity; lựa chọn có thể là 8 hoặc 12 partitions **nếu tier hỗ trợ và kiểm thử chứng minh cần thiết**. Không suy ra “8 partitions mặc định xử lý 64.000 event/s”: throughput còn bị giới hạn bởi namespace capacity, ingress bytes, SDK, network, serialization, data distribution và hệ thống downstream.

### Tăng partitions có phải lúc nào cũng an toàn?

Không. Trong những tier hỗ trợ tăng partition count, cần cân nhắc:

- Khả năng thay đổi **partition-key → partition-ID mapping**.
- Logic checkpoint và rebalance.
- Ordering của những key đã tồn tại.
- Giới hạn tối đa và không phải mọi SKU đều hỗ trợ giảm partition count sau khi tạo.
- Thời gian rollout, sản phẩm downstream phụ thuộc số partition.
- Partition count tăng không tự tăng throughput units/processing units của namespace.

**Hãy chọn số partition có dự phòng hợp lý ngay từ thiết kế**, nhưng không tạo quá nhiều nếu không có nhu cầu vì việc điều phối và monitoring cũng phức tạp hơn.

## 18. Throughput capacity khác partition count

Một lỗi kiến trúc phổ biến là coi **số partition = số đơn vị throughput**. Chúng là hai chiều khác nhau.

| Thành phần | Quyết định | Không quyết định |
|---|---|---|
| **Partition count** | Mức song song logic, scope ordering, phân phối khóa. | Tổng capacity namespace tự động tăng tương ứng. |
| **Throughput Units (TU)** trên tier áp dụng | Năng lực ingress/egress theo mô hình tính phí/quota. | Không tạo thêm partitions. |
| **Processing Units (PU)** hoặc mức tài nguyên chuyên dụng trên tier áp dụng | Năng lực xử lý/cấp phát chuyên dụng hơn. | Không đảm bảo ứng dụng downstream nhanh. |
| **Capacity Units (CU)** trên mô hình Dedicated | Năng lực cluster/dedicated tier tương ứng. | Không thay thế benchmark. |
| **Consumer instances** | Xử lý song song theo partition ownership. | Không vượt được giới hạn số partitions nếu một instance/partition. |

Trong các tier của Event Hubs, cần đối chiếu mô hình **Basic/Standard, Premium, Dedicated** và các khả năng liên quan. Tốc độ, throughput limits, tính năng auto-inflate và số partitions có khác nhau, không lấy một con số TU chung cho mọi tier.

### Auto-inflate

Một số tier/mô hình namespace hỗ trợ **Auto-inflate** để tăng throughput capacity theo ngưỡng cấu hình. Tuy nhiên:

- Không phải cơ chế tự động tăng **partition count**.
- Không tự bảo đảm consumer scale và downstream đủ năng lực.
- Không bảo đảm gửi sự kiện không bị throttling trong mọi tình huống peak.
- Có thể tăng chi phí khi throughput capacity tăng.
- Cần kiểm tra giới hạn và hướng scale-down phù hợp với tier.

Với yêu cầu latency nghiêm ngặt, phải đo throughput thực tế theo payload và batch size chứ không chỉ nhìn cấu hình Auto-inflate.

## 19. Batch gửi event và mô hình producer

Producer có thể gửi event riêng lẻ hoặc gom nhiều event vào **batch** theo giới hạn kích thước và API của SDK.

```text
Sensors
   |
   +-- E1 E2 E3 E4
   |
   v
Producer SDK
   |
   +-- EventDataBatch [E1 E2 E3 E4] (trong giới hạn size)
   |
   v
Event Hub → partition(s) theo routing/partition key
```

Ưu điểm của batching có thể gồm giảm network overhead, tăng throughput. Tuy nhiên:

- Batch phải tuân thủ **giới hạn kích thước** của tier/API.
- Các event trong một batch có thể chịu một quyết định partition routing theo cách SDK/producer cấu hình.
- Khi gửi cùng partition key, hiểu rằng tất cả events trong batch có thể bị route vào cùng partition.
- Một producer bắn batch quá lớn/tần suất cao có thể bị throttling.
- SDK retry có thể gửi lại khi kết quả send không chắc chắn; ứng dụng cần event IDs/idempotent downstream.

**Không tự nối hàng nghìn JSON records thành một event lớn** mà không kiểm tra kích thước, nhu cầu replay từng record và downstream parser. Batch ở mức SDK và payload chứa nhiều sự kiện nghiệp vụ là hai thiết kế khác nhau.

## 20. Azure Portal: quy trình tạo và xác minh

### Giai đoạn A — Tạo namespace

1. Mở [Azure Portal](https://portal.azure.com/) và xác nhận tenant/subscription.
2. Tìm **Event Hubs**, chọn **Create** hoặc tạo namespace theo giao diện.
3. Chọn resource group, region, tên namespace duy nhất, tier phù hợp.
4. Chọn capacity/throughput theo nhu cầu thực tế và ngân sách.
5. Kiểm tra networking và yêu cầu private access; lưu ý một số tính năng giới hạn theo tier.
6. Tạo namespace rồi xác minh endpoint/trạng thái.

### Giai đoạn B — Tạo Event Hub

1. Mở namespace vừa tạo, tìm **Event Hubs** → **Create Event Hub**.
2. Đặt tên `device-telemetry`.
3. Chọn partition count đủ nhu cầu song song dự kiến.
4. Chọn retention theo thời gian chấp nhận gián đoạn và khả năng replay.
5. Kiểm tra Capture, schema/feature settings nếu phù hợp và được hỗ trợ.
6. Tạo rồi đọc lại số partitions, retention và health.

### Giai đoạn C — Tạo consumer groups

1. Trong Event Hub `device-telemetry` mở mục **Consumer groups**.
2. Giữ `$Default` cho mục đích phù hợp hoặc tạo group riêng cho từng ứng dụng.
3. Tạo `realtime-analytics`, `raw-archiver` và `anomaly-detector`.
4. Kết nối các ứng dụng bằng group name tương ứng, không dùng chung `$Default` một cách tùy tiện.
5. Kiểm thử các ứng dụng đều thấy event mới theo tiến độ độc lập.
6. Kiểm tra checkpoint store và processing ownership của từng group.

### Giai đoạn D — Vận hành

1. Cấp role Sender/Receiver đúng phạm vi cho identities.
2. Cấu hình public/private networking, TLS và DNS.
3. Bật metrics, diagnostic logs và cảnh báo.
4. Đặt budget cho Event Hubs capacity, Storage checkpoint/Capture và processing compute.
5. Chạy bài test restart/rebalance/retention trong môi trường lab trước khi mở rộng Production.

## 21. Azure CLI: đọc namespace, hub, partitions và groups

Các lệnh dưới đây **chỉ đọc thông tin tài nguyên**. Thay placeholder bằng tên thật đã được phê duyệt.

### Kiểm tra subscription và tenant

```bash
az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table
```

### Xem namespace

```bash
az eventhubs namespace show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<NAMESPACE_NAME>" \
  --query "{Name:name,Location:location,Sku:sku.name,State:provisioningState}" \
  --output json
```

### Liệt kê Event Hubs trong namespace

```bash
az eventhubs eventhub list \
  --resource-group "<RESOURCE_GROUP>" \
  --namespace-name "<NAMESPACE_NAME>" \
  --output table
```

### Xem cấu hình Event Hub

```bash
az eventhubs eventhub show \
  --resource-group "<RESOURCE_GROUP>" \
  --namespace-name "<NAMESPACE_NAME>" \
  --name "device-telemetry" \
  --output json
```

Trong output, kiểm tra những trường như `partitionCount`, `messageRetentionInDays` hoặc các thuộc tính retention tương đương theo API, cùng trạng thái/tên entity. **Output ARM thường không thay thế hoàn toàn runtime partition metrics**; nếu cần thông tin sequence đầu/cuối partition, dùng Event Hubs SDK runtime partition properties với quyền phù hợp.

### Liệt kê consumer groups

```bash
az eventhubs eventhub consumer-group list \
  --resource-group "<RESOURCE_GROUP>" \
  --namespace-name "<NAMESPACE_NAME>" \
  --eventhub-name "device-telemetry" \
  --output table
```

Lệnh chỉ xác minh **group tồn tại**, không chứng minh đã có consumer chạy, checkpoints được lưu đúng hoặc consumer đang theo kịp stream.

## 22. Azure CLI: tạo tài nguyên lab

**Các lệnh sau tạo resource và có thể phát sinh phí.** Chỉ chạy khi được cấp phép trong resource group lab, không áp dụng trực tiếp vào Production. Tên namespace phải duy nhất theo quy tắc Azure.

### Namespace Standard

```bash
az eventhubs namespace create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --name "<UNIQUE_NAMESPACE_NAME>" \
  --location southeastasia \
  --sku Standard
```

### Event Hub với bốn partitions

```bash
az eventhubs eventhub create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --name device-telemetry \
  --partition-count 4
```

Sau khi tạo, kiểm tra retention thật trong Portal/CLI và điều chỉnh theo yêu cầu bằng cơ chế được hỗ trợ, **không mặc định dùng retention của môi trường lab cho Production**.

### Consumer groups cho ba ứng dụng

```bash
az eventhubs eventhub consumer-group create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --eventhub-name device-telemetry \
  --name realtime-analytics

az eventhubs eventhub consumer-group create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --eventhub-name device-telemetry \
  --name raw-archiver

az eventhubs eventhub consumer-group create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --eventhub-name device-telemetry \
  --name anomaly-detector
```

Tạo xong nên chạy lại lệnh `consumer-group list`, kiểm tra tier, số groups và quyền truy cập. Chưa cần gửi event thật để xác minh resources.

### Cảnh báo về $Default

Event Hub thường có consumer group mặc định `$Default`. Trong shell Unix, ký tự `$` có thể bị hiểu là khai báo biến môi trường nếu dùng không đúng quoting. Nếu phải chỉ định tên nhóm này trong CLI/SDK, bảo đảm truyền nguyên văn `$Default` (ví dụ dùng single quotes trong Bash). Không để nhiều ứng dụng Production dùng chung `$Default` mà không có kế hoạch checkpoint/ownership.

## 23. Python SDK: gửi event bằng identity

Trong runtime hỗ trợ Microsoft Entra authentication, dùng SDK và DefaultAzureCredential thay cho việc đưa connection string có khóa vào mã nguồn.

Lệnh cài thư viện trong môi trường thử nghiệm:

```bash
python -m pip install azure-eventhub azure-identity
```

Ví dụ producer:

```python
import json
import os
from datetime import datetime, timezone

from azure.eventhub import EventData, EventHubProducerClient
from azure.identity import DefaultAzureCredential

namespace = os.environ["EVENTHUB_NAMESPACE"]
hub_name = "device-telemetry"

credential = DefaultAzureCredential()

producer = EventHubProducerClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    eventhub_name=hub_name,
    credential=credential,
)

with producer:
    batch = producer.create_batch(partition_key="sensor-1024")

    event = EventData(json.dumps({
        "deviceId": "sensor-1024",
        "temperatureCelsius": 27.4,
        "occurredAtUtc": datetime.now(timezone.utc).isoformat(),
    }))
    event.properties = {"eventType": "TemperatureMeasured"}
    batch.add(event)
    producer.send_batch(batch)

print("Đã gửi event lab tới Event Hubs.")
```

### Giải thích

- `fully_qualified_namespace` là FQDN dạng `<name>.servicebus.windows.net`.
- `eventhub_name` chọn entity trong namespace.
- `DefaultAzureCredential` lấy token từ nguồn danh tính có sẵn trong môi trường chạy.
- `partition_key="sensor-1024"` hướng các event cùng key vào cùng partition theo chính sách mapping của dịch vụ.
- `create_batch()` giúp SDK tính giới hạn kích thước batch; `batch.add()` có thể báo lỗi khi event không vừa.
- `send_batch()` xác nhận thao tác gửi lên broker theo SDK, **không** xác nhận downstream đã xử lý.

Chạy với biến môi trường **không chứa secret**:

```bash
export EVENTHUB_NAMESPACE="<UNIQUE_NAMESPACE_NAME>"
python send_event.py
```

Dòng `export` dành cho shell Unix. Trên Windows PowerShell, cần dùng cú pháp biến môi trường phù hợp. Producer cần role **Azure Event Hubs Data Sender** ở scope thích hợp và quyền kết nối mạng đến namespace.

### Khi batch quá lớn

Thay vì ép gửi một batch vượt giới hạn, có thể:

1. Tạo batch mới.
2. Thử thêm event.
3. Nếu không còn chỗ, gửi batch hiện tại.
4. Tạo batch tiếp theo rồi thêm event vừa bị từ chối.
5. Nếu **một event đơn lẻ** đã vượt giới hạn, thay đổi schema/payload hoặc lưu object ngoài rồi gửi tham chiếu.

Không cắt chuỗi JSON bừa bãi để cho vừa batch vì có thể làm sai nội dung nghiệp vụ.

## 24. Python SDK: consumer group đọc event

Một consumer có thể nghe từ đầu dữ liệu retention hoặc từ event mới nhất, tùy starting position và checkpoint.

Ví dụ đơn giản:

```python
import os
from azure.eventhub import EventHubConsumerClient
from azure.identity import DefaultAzureCredential

namespace = os.environ["EVENTHUB_NAMESPACE"]
hub_name = "device-telemetry"
group_name = "realtime-analytics"

def on_event(partition_context, event):
    if event is None:
        return

    print(
        "partition=", partition_context.partition_id,
        "sequence=", event.sequence_number,
        "offset=", event.offset,
        "enqueued=", event.enqueued_time,
    )
    # Không in toàn bộ body nếu chứa dữ liệu cá nhân/nhạy cảm.
    # Mẫu này chỉ quan sát, chưa xử lý/checkpoint bền vững.

credential = DefaultAzureCredential()

with EventHubConsumerClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    eventhub_name=hub_name,
    consumer_group=group_name,
    credential=credential,
) as client:
    # "@latest": chỉ theo dõi event mới kể từ vị trí bắt đầu;
    # không phải replay mọi event cũ.
    client.receive(on_event=on_event, starting_position="@latest")
```

Đây là **consumer chạy liên tục** cho tới khi dừng bằng cơ chế của tiến trình; không chạy trong Terminal Production khi chưa biết cách dừng. Nó chưa cấu hình checkpoint store, scale coordination, retry hoặc graceful shutdown, nên **không phải mẫu processor Production**.

### Khi muốn đọc từ đầu dữ liệu còn retention

Một số API SDK dùng `starting_position="-1"` để bắt đầu từ đầu retained partition. Tuy nhiên:

- Cần kiểm tra API/SDK version và đặc điểm `EventPosition`.
- Không thể đọc dữ liệu đã vượt ra ngoài retention.
- Khi có checkpoint store, processor có thể ưu tiên checkpoint hơn starting position.
- Đọc lại có thể tạo duplicate side effects; nên dùng consumer group lab riêng.

### Vì sao dùng group riêng?

Nếu ứng dụng analytics và một script thử nghiệm cùng consumer group nhưng không phối hợp ownership/checkpoint đúng, kết quả có thể khó đoán hoặc gây xử lý trùng/gián đoạn. Một nhóm thực hành nên dùng consumer group riêng và chính sách quyền phù hợp, không chiếm partition của ứng dụng Production.

## 25. Event processor và Blob checkpoint store

Khi chạy nhiều consumers cùng group trong Production, nên dùng mô hình processor có **partition ownership và checkpointing**.

Cách thiết kế tham khảo:

```text
Event Hub: device-telemetry
    |
    +-- P0 ----┐
    +-- P1 ----┤
    +-- P2 ----┤
    +-- P3 ----┘
           |
           v
Consumer group: realtime-analytics
    |
    +-- Consumer instance A
    |      ├── xử lý P0, P1
    |      └── ghi checkpoints / ownership
    |
    +-- Consumer instance B
           ├── xử lý P2, P3
           └── ghi checkpoints / ownership
                   |
                   v
          Azure Blob Storage
          container: checkpoints-analytics
```

### Tại sao Blob checkpoint store?

Một số thư viện Azure Event Hubs Event Processor sử dụng Azure Blob Storage như nơi lưu:

- Partition ownership/claim giữa những instances.
- Last processed position/checkpoint.
- Metadata cần thiết để cân bằng lại partition.

**Blob Storage ở đây là nơi lưu trạng thái của ứng dụng consumer**, không phải bản copy đầy đủ stream. Nếu xóa container checkpoint, ứng dụng có thể phải bắt đầu từ starting position hoặc xử lý lại, tùy cấu hình.

### Yêu cầu vận hành

- Storage account/container phải tồn tại và có đường mạng đúng từ consumers.
- Managed identity có quyền data-plane Blob phù hợp, thường cần **Storage Blob Data Contributor** cho checkpoint store khi cơ chế ghi/lease yêu cầu.
- Tách checkpoint container theo ứng dụng/consumer group hoặc dùng cách ly tương đương theo SDK, không vô tình trộn môi trường.
- Không đặt checkpoint store ở vị trí quá xa, độ trễ cao hoặc mất khả năng ghi thường xuyên.
- Theo dõi lỗi Storage/permission/lease và lag sau rebalance.
- Chỉ ghi checkpoint sau khi dữ liệu đã được xử lý thành công theo semantics của ứng dụng.

### Pseudocode của handler

```text
on_event(partition_context, event):
    if event is None:
        return

    event_id = extract_business_id(event)
    if not already_processed(event_id):
        persist_result_and_dedupe_marker(event_id, event)

    partition_context.update_checkpoint(event)
```

Đây là **pseudocode**, không phải Python hoàn chỉnh. Với SDK cụ thể, API `update_checkpoint` yêu cầu checkpoint store hỗ trợ và có thể là hàm async trong bản asynchronous. Cần tra đúng signature của phiên bản thư viện đang dùng.

**Không checkpoint mỗi event một cách máy móc nếu throughput rất cao và Storage checkpoint writes thành bottleneck.** Có thể checkpoint theo batch, số event hoặc khoảng thời gian, nhưng phải chấp nhận replay window khi crash.

## 26. Retention, checkpoint và replay: tình huống thực tế

Giả sử Event Hub giữ dữ liệu **5 ngày** theo cấu hình minh họa. Consumer Analytics xử lý đến 12:00 ngày thứ Hai rồi dừng 2 ngày. Khi chạy lại vào thứ Tư:

- Nếu checkpoint vẫn trỏ tới event còn retention, consumer có thể đọc tiếp từ vị trí đã lưu và bắt kịp.
- Nếu consumer dừng quá thời hạn retention, checkpoint có thể trỏ đến vị trí không còn trong stream.
- Nếu checkpoint không hợp lệ/mất, hành vi bắt đầu phụ thuộc SDK/starting position, có thể gây đọc lại nhiều dữ liệu hoặc bỏ qua dữ liệu.
- Nếu dữ liệu quan trọng đã bị loại khỏi retention, cần nguồn lịch sử riêng như Capture/Storage hoặc event archive.

### Replay để tính toán lại kết quả

Ví dụ nhóm ML cần tính lại thống kê từ 09:00 đến 10:00:

1. Xác nhận event còn trong retention.
2. Tạo **consumer group replay riêng** hoặc checkpoint scope riêng theo phương án an toàn.
3. Bắt đầu từ thời gian/offset phù hợp.
4. Đọc event, ghi output vào **dataset/version mới** thay vì ghi đè Production ngay.
5. So sánh record count, checksum, schema và dữ liệu nghiệp vụ.
6. Nếu đúng, chuyển downstream sang bản kết quả đã kiểm tra.
7. Dọn consumer group/checkpoint lab theo quy trình.

Không reset checkpoint của nhóm đang phục vụ dashboard Production để làm một phân tích offline nếu có thể tách nhóm riêng.

## 27. Event Hubs Capture và kiến trúc dữ liệu dài hạn

Một kiến trúc streaming thường có hai nhu cầu trái ngược:

- **Phân tích nhanh** các event mới.
- **Lưu lâu dài** dữ liệu nguồn cho phân tích lại/đào tạo mô hình hoặc kiểm toán.

Kiến trúc tham khảo:

```text
IoT devices / App logs / Producers
             |
             v
       Event Hubs namespace
             |
       Event Hub: telemetry
       P0 | P1 | P2 | P3
             |
       +-----+----------+
       |                |
       v                v
CG: realtime        Capture / archival
    analytics           |
       |                v
       v           Blob Storage / ADLS
Dashboard / Alerts      |
                        v
                 Batch analytics / ML
```

Nếu dùng Event Hubs Capture, dữ liệu được ghi thành tệp theo cấu hình window/size, đích và định dạng hỗ trợ. Không coi Capture là một cơ chế **exactly-once transactional data lake** tự động: phải kiểm tra những trường hợp file trễ, dữ liệu trùng khi pipeline ingest lại, partitioning ở Storage và cách validate dữ liệu.

### Capture có thay thế checkpoint không?

Không. Capture là đường lưu trữ event dài hạn; còn consumer groups/processor checkpoints là trạng thái đọc của từng ứng dụng. Một worker analytics vẫn cần quản lý offset/checkpoint riêng, dù Capture đã bật.

## 28. Azure Event Hubs và Kafka compatibility

Azure Event Hubs hỗ trợ **giao thức Apache Kafka** ở những tier/thiết lập được hỗ trợ để các Kafka clients có thể kết nối với Event Hubs endpoint theo cấu hình tương thích. Đây là **giao thức tương thích**, không có nghĩa người dùng nhận toàn bộ tính năng/semantics của một Kafka cluster tự quản lý.

Điểm tương đồng ở mức khái niệm:

| Event Hubs | Thuật ngữ gần với Kafka |
|---|---|
| Event Hub | Topic |
| Partition | Topic partition |
| Consumer group | Kafka consumer group |
| Offset | Vị trí đọc trong partition |
| Namespace endpoint | Broker endpoint trong lớp tương thích |

Cần cẩn trọng:

- Không phải toàn bộ Kafka APIs/admin operations được hỗ trợ giống cluster Kafka riêng.
- SASL/TLS/authentication, broker endpoint/port và namespace config khác môi trường Kafka thường.
- Không dùng Kafka client và Event Hubs SDK chung một consumer group để tùy tiện thay đổi offset/checkpoint mà chưa hiểu hành vi.
- Cách Kafka clients commit offset khác cơ chế Blob checkpoint store trong Event Hubs SDK.
- Nếu đang chuyển từ Kafka, cần kiểm tra Producer acknowledgments, retries, ordering, topic configuration và retention.

**Một consumer group Kafka không mặc nhiên sử dụng Blob Storage checkpoint store** giống ứng dụng EventProcessorClient Python. Hệ thống phải được thiết kế theo thư viện/giao thức đang dùng, không trộn hai mô hình quản lý vị trí đọc.

## 29. Microsoft Entra ID, managed identity và Azure RBAC

Một ứng dụng gửi/nhận Event Hubs cần **quyền data-plane** trên namespace hoặc Event Hub phù hợp.

| Azure role | Mục đích |
|---|---|
| **Azure Event Hubs Data Sender** | Cho producer gửi event. |
| **Azure Event Hubs Data Receiver** | Cho consumer nhận event. |
| **Azure Event Hubs Data Owner** | Quyền data-plane rộng hơn; chỉ cấp khi thực sự cần quản trị tương ứng. |

Nên dùng **managed identity** cho VM, AKS, Functions hoặc Container Apps khi cách tích hợp hỗ trợ. Nếu chạy local lab, `DefaultAzureCredential` có thể dùng identity của phiên Azure CLI/IDE được cấp quyền.

### Ví dụ role assignment

```bash
az role assignment create \
  --assignee-object-id "<PRODUCER_PRINCIPAL_ID>" \
  --assignee-principal-type ServicePrincipal \
  --role "Azure Event Hubs Data Sender" \
  --scope "<EVENT_HUB_RESOURCE_ID>"
```

**Đây là lệnh thay đổi quyền Azure RBAC**; chỉ thực hiện khi có phê duyệt. Client ID và principal/object ID của managed identity không giống nhau. Khi tạo role assignment, xác nhận chính xác principal, role và scope.

### Quyền management khác data plane

Một người có Azure RBAC quản lý namespace (control plane) **không mặc nhiên** có quyền đọc mọi payload event qua SDK. Ngược lại, Data Receiver không mặc nhiên được thay đổi SKU hoặc xóa Event Hub.

Khi dùng **Storage checkpoint**, consumer identity còn cần **quyền Blob Storage** riêng; quyền Azure Event Hubs Data Receiver không tự cho phép ghi Blob checkpoint.

## 30. SAS keys và cách giảm rủi ro credential

Một số Event Hubs clients dùng **Shared Access Signature (SAS)** hoặc connection strings. Đây là phương án được dịch vụ hỗ trợ nhưng phải hạn chế quyền và vòng đời khóa.

Nguyên tắc:

- Không đưa connection string, SAS token hoặc primary/secondary key vào Git, manifest plaintext hay logs.
- Không dùng policy có quyền quá rộng cho mọi ứng dụng nếu chỉ cần Send hoặc Listen.
- Ưu tiên Microsoft Entra ID/managed identity khi khả thi.
- Lưu credential bắt buộc trong Azure Key Vault hoặc cơ chế secret management được phê duyệt.
- Rotate định kỳ hoặc khi nghi ngờ lộ; theo dõi toàn bộ consumers/producers trước khi thu hồi bản cũ.
- Hạn chế quyền list keys và thay đổi authorization rules.
- Bật cảnh báo thay đổi policy/role và kiểm tra audit logs.

**Một SAS policy có quyền Listen trên namespace không nên tự trở thành tài khoản chung cho hàng chục đội**. Scope rộng khiến khó thu hồi đúng ứng dụng bị xâm nhập và mở rộng blast radius.

## 31. Networking: TLS, firewall và Private Endpoint

Để kết nối Event Hubs, client cần:

1. Phân giải đúng namespace hostname.
2. Có route và traffic outbound tới endpoint.
3. Thiết lập TLS và giao thức được SDK hỗ trợ.
4. Có token/credential được chấp nhận.
5. Có quyền Send hoặc Listen đúng Event Hub.

Một số Azure Event Hubs SDK dùng **AMQP over TLS** (thường port 5671) hoặc **AMQP over WebSockets** (thường port 443). Kafka-compatible clients có yêu cầu endpoint/TLS/port riêng, thường dùng 9093 trong các cấu hình Kafka TLS. **Không suy ra mọi client tự chuyển từ 5671 sang 443** khi firewall chặn port — transport cần được cấu hình trong SDK.

### Private Endpoint

Khi tier và cấu hình hỗ trợ:

- Private Endpoint đưa đường truy cập namespace qua private IP trong VNet theo mô hình dịch vụ.
- Private DNS phải phân giải namespace hostname theo private routing.
- NSG, firewall, UDR và route/return path vẫn phải cho phép kết nối.
- Microsoft Entra authorization/SAS vẫn bắt buộc.
- Trên AKS/Container Apps, kiểm tra DNS từ **Pod/runtime thật**, không chỉ từ laptop quản trị.

**Private Endpoint không làm dữ liệu tự có thứ tự, không tăng retention, và không cho phép đọc event không có quyền.** Nó chỉ thay đổi đường mạng và phạm vi tiếp xúc.

## 32. Metrics, lag và cảnh báo

Azure Monitor hỗ trợ metrics và diagnostic logs cho Event Hubs theo khả năng tính năng/cấu hình. Những chỉ số phổ biến ở namespace/entity gồm:

| Tín hiệu | Ý nghĩa | Cần phản ứng |
|---|---|---|
| **Incoming messages** | Số event được gửi vào trong khoảng đo. | So với tốc độ dự kiến, phát hiện producer ngừng. |
| **Incoming bytes** | Lưu lượng dữ liệu đến. | So với capacity, payload size và ngân sách. |
| **Outgoing messages / bytes** | Lưu lượng consumer đọc. | Không mặc định đồng nghĩa nghiệp vụ đã xử lý thành công. |
| **Throttled requests** | Request gặp giới hạn capacity/throughput theo model. | Xem TU/PU/CU, batching, retry, quota. |
| **Server errors** | Lỗi phía dịch vụ/kết nối tùy metric. | Đối chiếu Azure status, client SDK logs và phạm vi ảnh hưởng. |
| **User errors** | Request lỗi cấu hình, auth, tên entity, kích thước... | Kiểm tra code/config/RBAC/network. |
| **Active connections** | Mức kết nối theo metric có sẵn. | Phát hiện client churn/quá nhiều connections. |
| **Capture/archival errors** | Capture pipeline có thể gặp lỗi đích Storage/quyền. | Kiểm tra destination, identity và logs. |
| **Consumer lag** | Khoảng cách giữa tốc độ vào/vị trí đầu stream và tiến độ consumer. | Cần đo theo group/partition qua processor metadata và checkpoint. |

### Lag không phải lúc nào là built-in metric của namespace

Một namespace có thể báo tổng incoming/outgoing tốt, nhưng **chỉ một consumer group** bị chậm. Để đo lag thật cho nhóm đó:

1. Lấy **latest sequence/offset** theo từng partition qua runtime properties/API được hỗ trợ.
2. Lấy **checkpoint/last processed position** của consumer group.
3. Tính chênh lệch sequence/offset theo partition (khi tương thích cách biểu diễn).
4. Quan sát **age** của event đang xử lý hoặc thời gian từ enqueued time đến processed time.
5. Đặt ngưỡng theo SLO, kết hợp số lỗi và backlog recovery time.

Không cộng offsets như các số liên tục trên toàn hub hoặc lấy outgoing/incoming messages của namespace làm chính xác 100% consumer lag của từng group.

### Cảnh báo nên có

- Producer đột ngột không gửi event trong khung giờ lẽ ra có traffic.
- Throttled requests tăng liên tục.
- Consumer lag/processing delay của group quan trọng vượt ngưỡng.
- Nhiều checkpoint failures/ownership churn.
- Partition skew lớn hoặc hot partition khiến dữ liệu đến chậm.
- Capture mất khả năng ghi Storage hoặc output file quá trễ.
- Unauthorized errors, token expiry và network connection errors.
- Budget vượt mức cho Event Hubs throughput/capture/checkpoint/compute.

## 33. Troubleshooting: event gửi được nhưng nhóm không xử lý

Một lỗi “không thấy event” cần phân lớp:

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| `EventHubNotFound` / entity not found | Sai hub name/namespace hoặc chưa tạo entity. | ARM list, client FQDN và eventhub_name. |
| `Unauthorized` | Identity không có Sender/Receiver hoặc SAS sai. | Role/scope, token, quyền. |
| Timeout kết nối | DNS, firewall, private endpoint, TLS/transport. | Client network path và SDK error. |
| Send bị throttled | Vượt throughput capacity/quota. | Incoming bytes, throttling, tier và batching. |
| Producer báo success nhưng consumer không thấy | Chọn sai group/hub, start ở latest sau khi gửi, checkpoint trỏ sau event. | Timeline, starting position, checkpoint store. |
| Một group được, group khác không | App/identity/processor/checkpoint riêng bị lỗi. | Compare group, receiver logs, Blob permissions. |
| Chỉ một partition lag cao | Hot partition hoặc consumer xử lý chậm trên partition đó. | Key distribution, partition owner, processing time. |
| Hai consumers xử lý trùng | Retry/replay/ownership conflict hoặc checkpoint lỗi. | Event ID, checkpoint, handler idempotency. |
| Event có dữ liệu cũ khi restart | Bắt đầu từ earliest hoặc checkpoint lùi. | Starting position, checkpoint store và retention. |
| Event quá cũ không replay được | Đã vượt retention. | Retention settings, Capture/Storage archive. |
| Kafka consumer không commit offset | Protocol/client config, quyền và group offset management. | Kafka client logs, compatibility support. |
| Consumer đọc nhưng sink không có dữ liệu | App crash sau read, ghi sink lỗi, checkpoint sai thứ tự. | App logs, DB/storage transaction, checkpoint position. |
| Capture không có file mới | Destination config, storage network/permissions, capture window và lỗi nền tảng. | Capture config, Storage destination, logs/metrics. |

### Quy trình điều tra

1. **Đúng subscription/resource group/namespace/hub?** Không dùng gần giống tên môi trường.
2. **Producer được broker chấp nhận?** Ghi Message ID/application event ID và UTC time.
3. **Event nằm ở partition nào?** Dùng runtime metadata hoặc log của producer nếu có.
4. **Group đúng và tồn tại?** Kiểm tra consumer_group và quyền.
5. **Có checkpoint trước/sau event?** Xác định starting position thực tế.
6. **Partition ownership có ổn định?** Có rebalance hoặc nhiều app tranh chấp?
7. **Ứng dụng xử lý thành công?** Logs và output sink, không chỉ SDK callback.
8. **Có lỗi ở sink?** DB, Blob, Spark job, schema, quota.
9. **Còn retention/replay được?** Nếu không, dùng archive/nguồn gốc đã thiết kế.
10. **Có thể khôi phục an toàn?** Tách group replay, output version và đối soát.

Không xóa consumer group hoặc checkpoint container trên Production để “thử lại từ đầu” khi chưa có kế hoạch chống ghi trùng.

## 34. Tình huống A: consumer group mới không thấy event cũ

**Bối cảnh:** nhóm Audit tạo consumer group `audit-review` lúc 15:00. Họ muốn đọc một event lúc 14:00 và nói rằng “Event Hub bị mất message” vì ứng dụng chỉ thấy event mới.

Có hai khả năng:

- Event lúc 14:00 **còn retention** nhưng ứng dụng đặt `starting_position="@latest"` nên bắt đầu từ điểm gần hiện tại.
- Event đã **quá retention** hoặc producer gửi sang hub/namespace khác.

Quy trình:

1. Kiểm tra event có được accepted và thuộc Event Hub nào.
2. Xác định retention và thời điểm broker tiếp nhận.
3. Kiểm tra consumer group, SDK starting position, checkpoint store.
4. Nếu event còn retention, chạy **replay có kiểm soát** với starting position phù hợp.
5. Nếu event đã hết retention, kiểm tra Capture/raw archive.
6. Giữ output replay riêng; chống duplicate effects trước khi nhập lại Production.

**Bài học:** tạo group sau **không cản việc đọc dữ liệu cũ còn retention**, nhưng cũng không tự khiến application đọc lại lịch sử; vị trí bắt đầu và checkpoint quyết định.

## 35. Tình huống B: consumer lag tăng dù đã thêm instances

**Bối cảnh:** một Event Hub có 4 partitions, nhóm analytics từ 4 instances mở rộng lên 10 instances. Lag vẫn tăng.

Điều tra:

1. Một group với 4 partitions **không thể có 10 partition owners xử lý độc lập** theo mô hình một-owner-per-partition của EventProcessor.
2. Xem partition nào có lag cao: có thể chỉ P2.
3. Kiểm tra partition keys: producer dùng `partition_key="global"` cho phần lớn traffic.
4. Consumer trên P2 đang chờ một database sink chậm.
5. Namespace có thể đủ throughput nhưng downstream không kịp.

Hướng xử lý:

- Chỉnh keying strategy theo yêu cầu ordering.
- Tối ưu batch/DB writes, không chỉ tăng worker count.
- Kiểm tra concurrency bên trong processing workflow mà không làm mất thứ tự cần thiết.
- Đánh giá partition count và capacity nếu thật sự là giới hạn, có kế hoạch migration/ordering.
- Theo dõi lag từng partition và cost/event.

**Bài học:** số consumer instances vượt số partitions không tự tăng khả năng xử lý song song theo partition.

## 36. Tình huống C: phân tích bị ghi trùng sau restart

**Bối cảnh:** analytics processor ghi hàng nghìn dòng vào SQL, sau đó một node crash. Khi restart, những event cuối cùng bị đọc lại và báo cáo doanh thu tăng gấp đôi.

Nguyên nhân:

- Worker ghi thành công vào SQL nhưng **chưa checkpoint**.
- Khi restart, processor đọc lại từ checkpoint cũ.
- Sink không có idempotent event handling.

Khắc phục:

1. Dừng tác động sai tiếp tục xảy ra; giữ logs và event IDs.
2. Xác định checkpoint cuối trước crash và khoảng replay.
3. Đối soát kết quả dựa trên business ID/event ID.
4. Thêm unique constraint/inbox marker và transaction phù hợp.
5. Chỉ checkpoint sau khi persist thành công.
6. Replay vào output test để xác minh; sửa dữ liệu Production có phê duyệt.
7. Bổ sung alert checkpoint failure/duplicate event.

**Bài học:** checkpoint giúp resume, **không** đồng nghĩa exactly-once cho dữ liệu bên ngoài Event Hubs.

## 37. Bài thực hành: telemetry cho nhiều nhóm xử lý

**Bối cảnh:** nhà máy có 6.000 cảm biến gửi event nhiệt độ; công ty muốn dashboard theo phút, lưu dữ liệu thô và phát hiện cảm biến bất thường.

| Thành phần | Giá trị minh họa |
|---|---|
| Resource group | `rg-stream-lab` |
| Namespace | `evh-factory-lab-unique` |
| Event Hub | `device-telemetry` |
| Tier lab | Standard |
| Partitions | 4 |
| Partition key | `deviceId` |
| Consumer group 1 | `realtime-analytics` |
| Consumer group 2 | `raw-archiver` |
| Consumer group 3 | `anomaly-detector` |
| Checkpoint | Azure Blob Storage container tách biệt theo group |
| Retention | Theo cửa sổ thực hành và giới hạn tier |
| Quyền producer | Azure Event Hubs Data Sender |
| Quyền consumers | Azure Event Hubs Data Receiver |

### Yêu cầu thực hành

1. Vẽ sơ đồ namespace → Event Hub → 4 partitions → 3 consumer groups.
2. Phân biệt Azure subscription với consumer group.
3. Giải thích cách partition key `deviceId` ảnh hưởng ordering.
4. Nêu vì sao các sensor IDs khác nhau **có thể** vào cùng partition.
5. Ước lượng parallelism tối đa theo partition ownership khi có 2, 4 và 6 consumer instances.
6. Tạo resource lab (nếu được cấp quyền), đọc cấu hình với CLI.
7. Gửi 10 event giả lập bằng Python SDK, ghi application property `eventType`.
8. Chạy consumer ở `realtime-analytics` để quan sát metadata event.
9. Chạy consumer ở `raw-archiver` và xác nhận có thể đọc **cùng event IDs**.
10. Tạo checkpoint store và giải thích quyền Blob Storage cần thiết.
11. Tạm ngừng consumer, gửi event mới, bật lại và quan sát resume/replay.
12. Thử start từ latest so với earliest trên group lab riêng; giải thích khác biệt.
13. Giả sử một partition nhận 90% event, đề xuất cách tìm và giảm hot partition.
14. Giả sử nhóm analytics bị ngừng lâu hơn retention, đề xuất phương án lấy dữ liệu lịch sử.
15. Thiết kế 3 alerts: throttling, consumer lag và checkpoint failure.
16. Đánh giá các khoản chi phí Event Hubs, checkpoint/Capture Storage và processing compute.
17. Mô tả cách dọn tài nguyên lab mà không xóa nhầm namespace dùng chung.

### Lời giải định hướng

**Kiến trúc:**

```text
6.000 sensors
     |
     v
Event Hubs: device-telemetry
     |
P0 -- P1 -- P2 -- P3
 |     |     |     |
 +-----+-----+-----+------> CG realtime-analytics → dashboard
 |     |     |     |
 +-----+-----+-----+------> CG raw-archiver     → Blob archive
 |     |     |     |
 +-----+-----+-----+------> CG anomaly-detector → alerts
```

**Ordering:** với partition key `deviceId`, event cùng key được định tuyến vào một partition theo mapping hiện hành; thứ tự được giữ ở log partition, không ở toàn Event Hub. Nhiều keys có thể dùng cùng partition.

**Parallelism:** với 4 partitions, nhóm có 2 instances có thể chia gần 2 partitions mỗi instance; 4 instances có thể giữ 1 partition/instance; 6 instances không có thêm 2 partitions để xử lý độc lập theo ownership model.

**Groups:** mỗi group đọc cùng event mà không “ăn mất” event của nhóm khác, miễn event còn retention và vị trí bắt đầu/checkpoint phù hợp.

**Checkpoint:** lưu tiến độ riêng, thường qua Blob checkpoint store; không tự được Event Hubs lưu cho mọi application. Cần quyền Blob riêng bên cạnh Event Hubs Data Receiver.

**Khôi phục:** nếu event đã hết retention, lấy từ archive/Capture hoặc nguồn dữ liệu gốc nếu có; không reset checkpoint rồi kỳ vọng broker còn toàn bộ lịch sử.

**Nghiệm thu:** các consumer groups nhận đúng events, có thể dừng/tiếp tục theo checkpoint; không ghi lặp vào sink khi replay; monitoring nhìn thấy lỗi và chi phí nằm trong giới hạn lab.

## 38. Tự kiểm tra kiến thức

**Câu 1.** Một namespace và một Event Hub khác nhau như thế nào?

**Đáp án:** Namespace quản lý endpoint, tier, quyền, network và capacity; Event Hub là entity chứa stream phân thành các partitions.

**Câu 2.** Một consumer đọc event xong thì event bị xóa khỏi Event Hubs ngay không?

**Đáp án:** Không. Event vẫn nằm trong stream cho tới khi hết thời hạn retention hoặc theo hành vi dịch vụ phù hợp; các groups khác có thể đọc độc lập.

**Câu 3.** Có thể bảo đảm thứ tự toàn cục trên tất cả partitions của một Event Hub không?

**Đáp án:** Không. Event Hubs cung cấp thứ tự theo từng partition; các partitions khác nhau không có một tổng thứ tự duy nhất được bảo đảm.

**Câu 4.** Partition key `deviceId` có tạo một partition riêng cho mỗi thiết bị không?

**Đáp án:** Không. Nhiều deviceIds được hash vào cùng một số hữu hạn partitions.

**Câu 5.** Tăng số partitions có tự tăng throughput capacity của namespace không?

**Đáp án:** Không. Partition parallelism và throughput capacity (TU/PU/CU tùy tier) là những chiều khác nhau.

**Câu 6.** Có 4 partitions và 10 worker instances cùng một consumer group. Có thể có 10 partition owners cùng lúc theo EventProcessor không?

**Đáp án:** Không. Trong mô hình một owner mỗi partition, tối đa 4 owners đang xử lý 4 partitions tại cùng thời điểm; instances dư có thể không được phân công.

**Câu 7.** Consumer group có giữ một bản dữ liệu vật lý riêng như topic subscription queue không?

**Đáp án:** Không. Các consumer groups đọc cùng các partition dữ liệu của Event Hub với tiến độ độc lập.

**Câu 8.** Tạo group mới có mặc định replay mọi event từ đầu lịch sử không?

**Đáp án:** Không. Starting position và checkpoint quyết định; chỉ đọc lại được event còn retention.

**Câu 9.** Checkpoint có được Event Hubs tự lưu cho mọi consumer group/app không?

**Đáp án:** Không. Các ứng dụng/SDK cần quản lý checkpoint theo cơ chế tương ứng, ví dụ Azure Blob checkpoint store cho Event Processor.

**Câu 10.** Vì sao checkpoint trước khi ghi output có thể làm mất kết quả?

**Đáp án:** Nếu crash sau checkpoint nhưng trước khi output commit, ứng dụng khi resume có thể bỏ qua event chưa xử lý xong.

**Câu 11.** Nếu ghi SQL thành công nhưng crash trước checkpoint, sự cố gì có thể xảy ra?

**Đáp án:** Event được đọc lại, có thể ghi trùng nếu sink không idempotent.

**Câu 12.** `occurredAtUtc` khác `enqueued_time` ở đâu?

**Đáp án:** occurredAtUtc là thời điểm do thiết bị/ứng dụng ghi trong payload; enqueued_time là thời điểm Event Hubs tiếp nhận event.

**Câu 13.** Event Hubs có dead-letter queue tự động cho từng consumer group như Service Bus không?

**Đáp án:** Không. Hệ thống downstream phải thiết kế xử lý lỗi/quarantine phù hợp.

**Câu 14.** Nếu muốn replay dữ liệu 6 tháng trước nhưng retention chỉ vài ngày, làm thế nào?

**Đáp án:** Cần archive/Storage/Capture hoặc nguồn gốc khác đã được thiết kế; Event Hubs không giữ dữ liệu vượt retention.

**Câu 15.** Vì sao một hot partition có thể làm lag dù có nhiều worker?

**Đáp án:** Một partition tập trung phần lớn traffic và theo mô hình ownership thường chỉ có một processor owner tại một thời điểm trong group; tăng workers dư không chia nhỏ partition đó.

**Câu 16.** Azure RBAC Data Sender có tự cho phép đọc event không?

**Đáp án:** Không. Vai trò gửi và nhận tách biệt; consumer cần Data Receiver phù hợp.

**Câu 17.** Private Endpoint có thay thế quyền Microsoft Entra hoặc SAS không?

**Đáp án:** Không. Private Endpoint quản lý đường mạng, còn authentication/authorization vẫn cần có.

**Câu 18.** Kafka consumer group có mặc nhiên dùng Blob checkpoint store của Event Hubs SDK không?

**Đáp án:** Không. Kafka clients có cơ chế quản lý offsets riêng trong lớp tương thích; không trộn tùy tiện với EventProcessor checkpoint store.

**Câu 19.** Vì sao consumer lag cần theo dõi từng group/partition?

**Đáp án:** Incoming/Outgoing totals của namespace không cho biết một nhóm riêng đang xử lý chậm; lag có thể chỉ nằm trên một partition nóng.

**Câu 20.** Gửi thành công event đồng nghĩa analytics đã tính đúng chưa?

**Đáp án:** Chưa. Producer chỉ xác nhận gửi lên Event Hubs; consumer, checkpoint, sink và validation quyết định kết quả downstream.

**Câu 21.** Có nên đưa thông tin thẻ thanh toán hoặc access token đầy đủ vào telemetry events không?

**Đáp án:** Không. Event có thể nằm trong retention, Capture, logs và analytics; cần tối thiểu hóa, mã hóa/ẩn dữ liệu phù hợp và quản lý quyền.

**Câu 22.** Một consumer group bị lỗi checkpoint nhưng vẫn đọc event, có thể có rủi ro nào?

**Đáp án:** Sau restart/rebalance, có thể đọc lại nhiều event, ghi trùng hoặc thất bại khi chia lại partition; cần quan sát và xử lý checkpoint store.

**Câu 23.** Tăng partition count có thể làm thay đổi partition key routing không?

**Đáp án:** Có. Tùy tier và cơ chế mapping, cùng một key có thể được định tuyến vào partition khác sau thay đổi, ảnh hưởng ordering assumptions.

**Câu 24.** Event Hubs Capture có thay thế consumer checkpoint của ứng dụng không?

**Đáp án:** Không. Capture lưu dữ liệu sang Storage, còn checkpoint của từng ứng dụng ghi nhận tiến độ xử lý của consumer.

**Tóm lại:** **Event Hubs namespace** định nghĩa ranh giới tài nguyên, quyền, mạng và capacity; **partition** quyết định cách phân phối stream và scope của ordering; **consumer group** cho phép nhiều ứng dụng đọc cùng dữ liệu theo tiến độ riêng. Muốn vận hành ổn định phải thiết kế **partition key hợp lý, số partition đủ song song, checkpoint sau khi xử lý, retention/replay có kế hoạch, quyền tối thiểu và giám sát lag theo từng nhóm**. Streaming đáng tin cậy không chỉ là gửi được event mà còn là **biết event đi vào partition nào, ai đã xử lý tới đâu và làm sao khôi phục kết quả đúng khi có sự cố**.
