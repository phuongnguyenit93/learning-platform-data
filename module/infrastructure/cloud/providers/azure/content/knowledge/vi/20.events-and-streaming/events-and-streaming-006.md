# Partition key, checkpoint và cân bằng tải consumer

## 1. Vì sao kiến trúc streaming cần ba khái niệm này?

Hãy tưởng tượng một nền tảng bán hàng phát các sự kiện **OrderCreated**, **OrderPaid**, **OrderShipped** đến Azure Event Hubs. Một nhóm consumer cập nhật bảng doanh thu, nhóm thứ hai phân tích gian lận, nhóm thứ ba xuất dữ liệu sang kho phân tích. Mỗi phút hệ thống nhận hàng chục nghìn sự kiện, và số lượng tăng mạnh vào giờ cao điểm.

Khi đội kỹ thuật tăng số consumer instances từ hai lên sáu, ba hiện tượng bất thường xuất hiện:

- Một số đơn hàng có **OrderPaid** được xử lý trước **OrderCreated**.
- Một sự kiện được cập nhật vào database hai lần sau khi worker bị restart.
- Có thêm nhiều worker nhưng một worker vẫn quá tải và consumer lag tiếp tục tăng.

Vấn đề không chỉ là thiếu CPU. Ba khái niệm quyết định thiết kế:

**Partition key** giúp định tuyến các sự kiện có liên quan về một partition để quản lý thứ tự. **Checkpoint** ghi lại vị trí xử lý đã hoàn thành an toàn. **Cân bằng tải consumer** phân chia quyền xử lý partitions giữa nhiều consumer instances để sử dụng năng lực tính toán.

Đây là bài học thuộc chương **Sự kiện và dữ liệu streaming** trong module khám phá hệ sinh thái Microsoft Azure, kết nối Event Hubs với subscription, resource group, Microsoft Entra ID, mạng ảo, compute, Azure Functions, AKS, Blob Storage, bảo mật, giám sát và kiểm soát chi phí.

> Quy tắc nền tảng: **Event Hubs là một luồng log phân vùng, không phải queue tự xóa message ngay sau khi consumer đọc.** Partition key, checkpoint và consumer group giải quyết ba nhu cầu khác nhau nhưng phải được thiết kế đồng bộ.

## 2. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Giải thích namespace, event hub, partition, consumer group và consumer instance.
2. Phân biệt partition key, partition ID, offset, sequence number và event time.
3. Chọn partition key theo đơn vị cần bảo đảm thứ tự nghiệp vụ.
4. Giải thích tại sao hai keys khác nhau vẫn có thể cùng nằm ở một partition.
5. Nhận biết hot partition và tải phân bố lệch.
6. Chọn số partitions dựa trên parallelism, throughput và khả năng mở rộng.
7. Phân biệt việc consumer đọc sự kiện với việc checkpoint đã xử lý xong.
8. Thiết kế checkpoint chỉ sau khi ghi kết quả bền vững và không bỏ qua lỗ hổng xử lý.
9. Hiểu cơ chế partition ownership và rebalance trong EventProcessorClient.
10. Dùng Java producer, Java EventProcessorClient và Azure Blob checkpoint store.
11. Xử lý crash, duplicate, retry, idempotency, retention và replay.
12. Thiết kế Azure Functions hoặc AKS consumers, giám sát consumer lag và chi phí.

## 3. Kiến trúc tổng thể của Azure Event Hubs

Azure Event Hubs tiếp nhận một luồng sự kiện và lưu các sự kiện vào nhiều **partitions**. Producer ghi dữ liệu, còn consumer đọc một hoặc nhiều partitions thông qua SDK hoặc môi trường xử lý được hỗ trợ.

~~~mermaid
flowchart LR
    P1[Orders API] --> EH[Azure Event Hub]
    P2[Telemetry Gateway] --> EH
    EH --> A[Partition 0]
    EH --> B[Partition 1]
    EH --> C[Partition 2]
    EH --> D[Partition 3]
    A --> G1[Consumer group: analytics]
    B --> G1
    C --> G1
    D --> G1
    A --> G2[Consumer group: fraud]
    B --> G2
    C --> G2
    D --> G2
    G1 --> OUT1[(Analytics Database)]
    G2 --> OUT2[(Fraud Store)]
~~~

Các consumer groups đọc từ **cùng dữ liệu lưu trong Event Hub** nhưng có tiến độ và ứng dụng độc lập. Không phải mỗi consumer group tạo ra một bản sao vật lý của toàn bộ log.

### 3.1. Những lớp thường có trong ứng dụng thật

| Lớp | Thành phần Azure hoặc Kubernetes | Trách nhiệm |
|---|---|---|
| Producer | Azure Functions, App Service, AKS, VM | Gửi events theo contract |
| Ingestion | Azure Event Hubs | Nhận, chia partition và lưu events trong retention |
| Consumer orchestration | EventProcessorClient hoặc Event Hubs trigger | Đọc và phân phối ownership |
| Checkpoint store | Azure Blob Storage | Ghi tiến độ và ownership |
| Processing | Java/Python/.NET workers | Validate, transform, aggregate, ghi dữ liệu |
| Sink | Azure SQL, Cosmos DB, Blob, ADLS | Lưu kết quả bền vững |
| Identity | Microsoft Entra ID, managed identity | Cấp quyền gửi/nhận/checkpoint |
| Observability | Azure Monitor, Application Insights | Theo dõi lag, lỗi và chi phí |

Việc producer send thành công chưa chứng minh consumer đã xử lý thành công. Việc consumer đọc thành công cũng chưa chứng minh database đã commit.

## 4. Event Hubs khác Azure Service Bus queue ở đâu?

| Đặc tính | Event Hubs | Service Bus queue thông thường |
|---|---|---|
| Mô hình | Append-only partitioned event log | Broker quản lý message và settlement |
| Sau khi consumer đọc | Event vẫn được giữ theo retention | Message được Complete/settle theo cơ chế nhận |
| Tiến độ | Offset/sequence và checkpoint của consumer | Lock, Complete, Abandon, DeadLetter |
| Nhiều nhóm độc lập | Consumer groups đọc cùng log | Thường dùng topic subscriptions hoặc topology riêng |
| Bảo đảm thứ tự | Theo partition, với điều kiện producer/consumer phù hợp | Tùy entity và sessions |
| Xử lý event lỗi | Ứng dụng thiết kế retry/quarantine | Có cơ chế DLQ tích hợp |
| Điểm mạnh | Telemetry, sự kiện streaming, ingest tốc độ cao | Command/workflow, message processing, giao dịch |

Đừng áp dụng tư duy “Complete event để xóa khỏi Event Hubs” như Service Bus. **Checkpoint không phải thao tác xóa hoặc ACK từ broker.**

## 5. Partition: đơn vị log và đơn vị song song hóa

Mỗi Event Hub có một số partitions. Broker ghi events vào từng partition theo một thứ tự xác định trong partition ấy.

~~~text
Partition 0: seq 100 -> 101 -> 102 -> 103 -> ...
Partition 1: seq  30 ->  31 ->  32 ->  33 -> ...
Partition 2: seq 240 -> 241 -> 242 -> 243 -> ...
Partition 3: seq  80 ->  81 ->  82 ->  83 -> ...
~~~

**Sequence number** được hiểu trong phạm vi partition. Sequence 100 ở partition 0 không nhất thiết xảy ra trước sequence 240 ở partition 2.

Một processor thường được giao một hoặc nhiều partitions để xử lý. Số partitions là giới hạn quan trọng của số consumers có thể đồng thời sở hữu và xử lý các partition streams độc lập trong cùng consumer group.

### 5.1. Có bảo đảm global ordering không?

Không. Event Hubs không cung cấp một thứ tự duy nhất giữa mọi partitions. Nếu event A và event B nằm hai partitions khác nhau, chúng có thể được xử lý ở bất kỳ thứ tự tương đối nào.

### 5.2. Thứ tự theo partition cũng cần producer đúng

Event Hubs bảo toàn thứ tự các sự kiện **được ghi vào** một partition theo sequence. Nhưng nếu hai producers gửi OrderPaid và OrderCreated không phối hợp hoặc network retry khiến OrderPaid tới broker trước, log sẽ phản ánh thứ tự tới broker, không tự sửa thứ tự nghiệp vụ.

Nếu cần order đúng theo nghiệp vụ, hãy thiết kế event version/sequence và producer serialization phù hợp.

## 6. Partition key là gì?

**Partition key** là khóa producer chỉ định để các events có cùng khóa được định tuyến một cách nhất quán vào cùng partition khi cấu hình partitions và routing không đổi.

Ví dụ:

~~~text
Event A: OrderCreated, orderId=ORD-1001, key=ORD-1001
Event B: OrderPaid,    orderId=ORD-1001, key=ORD-1001
Event C: OrderShipped, orderId=ORD-1001, key=ORD-1001

Event D: OrderCreated, orderId=ORD-1002, key=ORD-1002
~~~

Trong cấu hình partition ổn định, A/B/C sẽ có cùng partition key và được đưa tới cùng partition. D có thể vào partition khác, **nhưng cũng có thể cùng partition** do nhiều keys có thể được ánh xạ vào một partition.

Partition key là thông tin **routing**, không phải eventId, business operation key, unique constraint hoặc cơ chế idempotency.

### 6.1. Khi nào dùng partition key?

Khi cần giữ các sự kiện của cùng aggregate/entity trong một partition, chẳng hạn:

- **orderId** cho trạng thái đơn hàng.
- **accountId** cho luồng biến động một tài khoản.
- **deviceId** cho readings của một thiết bị.
- **customerId** nếu yêu cầu thứ tự thực sự theo khách hàng.
- **aggregateId** trong mô hình event sourcing.

### 6.2. Khi nào không cần key?

Nếu các events độc lập và không yêu cầu thứ tự theo entity, có thể để SDK/broker phân phối theo cơ chế không chỉ định key. Điều này có thể giúp phân tán lưu lượng, nhưng không bảo đảm các events của cùng entity về cùng partition.

## 7. Partition key khác Partition ID như thế nào?

| Thuộc tính | Partition key | Partition ID |
|---|---|---|
| Ý nghĩa | Khóa logic của dữ liệu | Định danh vật lý của partition |
| Ai thường chọn? | Producer theo nghiệp vụ | Broker đã tạo, producer có thể chỉ rõ qua một số API |
| Ví dụ | ORD-1001 | 0, 1, 2 |
| Phụ thuộc topology vật lý | Ít hơn | Nhiều hơn |
| Phù hợp giữ thứ tự theo entity | Thường có | Có thể, nhưng phải tự quản lý routing nhất quán |
| Khi partition count đổi | Mapping có thể thay | Cần kiểm tra topology và migration |

Không tự giả định công thức ánh xạ key sang ID là **hash(key) % partitionCount** trong mọi phiên bản. Mô hình hashing giúp hiểu ý tưởng, nhưng chi tiết của SDK/broker không nên trở thành hợp đồng nghiệp vụ nếu dịch vụ không bảo đảm công thức đó.

### 7.1. Cùng key không bảo đảm tồn tại mãi ở cùng Partition ID

Khi partition count thay đổi trong những SKU/tính năng cho phép, cách ánh xạ một key có thể thay đổi. Vì vậy, thứ tự lịch sử của cùng key qua hai cấu hình topology khác nhau cần được kiểm soát ở tầng nghiệp vụ hoặc qua kế hoạch migration.

### 7.2. Không chỉ định mâu thuẫn

Khi dùng API tạo batch, thông thường bạn chọn partition key **hoặc** partition ID theo quy tắc SDK. Không mặc định có thể gán cả hai cùng lúc vào một batch.

## 8. Chọn khóa theo đơn vị cần thứ tự, không theo trực giác

| Loại sự kiện | Khóa đề xuất | Điều kiện cần xác nhận |
|---|---|---|
| Order lifecycle | orderId | Chỉ cần thứ tự trong từng order |
| Wallet transactions | walletId | Có cần thứ tự toàn bộ giao dịch của một ví? |
| IoT readings | deviceId | Đọc cùng device cần đi theo thứ tự ghi |
| Customer notifications | customerId | Có nguy cơ một khách hàng cực lớn gây hot partition? |
| Telemetry không phụ thuộc | Có thể không chỉ định key | Thứ tự theo entity không cần thiết |
| Bank ledger | accountId hoặc một thiết kế chuyên biệt | Tính đúng giao dịch cần transaction/ordering ngoài broker |

### 8.1. Khóa quá thô

Dùng **tenantId** khi một tenant chiếm 60–80% traffic có thể dồn phần lớn events vào một partition.

### 8.2. Khóa quá chi tiết

Dùng random UUID khác nhau cho từng event có thể phân tán tốt hơn nhưng phá khả năng giữ OrderCreated/OrderPaid cùng một partition.

### 8.3. Khóa chứa dữ liệu nhạy cảm

Không dùng email, số điện thoại, tên người dùng hoặc số thẻ trực tiếp làm partition key nếu không cần thiết. Key có thể hiện diện trong metadata/logs. Ưu tiên ID nội bộ hoặc giá trị token hóa theo chính sách bảo mật.

### 8.4. Khóa thay đổi theo thời điểm

Đừng thêm timestamp vào key của mỗi event nếu yêu cầu cùng entity luôn cùng partition. Điều này tự vô hiệu hóa chiến lược đặt key ổn định.

## 9. Hot partition và key skew

**Hot partition** là partition có incoming events/bytes hoặc công việc xử lý vượt trội so với các partitions khác.

~~~text
Ví dụ Event Hub có 4 partitions:

Partition 0: ████████████████████████   70%
Partition 1: ████                       10%
Partition 2: ████                       10%
Partition 3: ████                       10%
~~~

Nếu 70% sự kiện đều có partition key **tenant-giant**, chúng có thể cùng vào partition 0. Dù có bốn consumers, consumer sở hữu partition 0 vẫn xử lý phần lớn tải.

### 9.1. Dấu hiệu

- Consumer lag tập trung ở một partition.
- Một processor CPU cao và các processors khác nhàn rỗi.
- Tăng số consumer instances không cải thiện tốc độ hết backlog.
- Một số entity keys tạo quá nhiều events.
- Thời gian xử lý riêng partition nóng vượt SLO.

### 9.2. Khắc phục

1. Thống kê phân phối partition keys tại producer/telemetry.
2. Kiểm tra mức độ strict ordering thật sự cần.
3. Thu hẹp khóa từ **tenantId** thành **orderId** nếu nghiệp vụ chỉ yêu cầu thứ tự theo đơn.
4. Tối ưu consumer, DB batch writes và network I/O.
5. Cân nhắc subkeys/sharding nếu được chấp thuận phá strict order ở cấp rộng hơn.
6. Lập kế hoạch topology/partition count theo tính năng SKU và nhu cầu thực.

**Không tùy tiện thêm random suffix vào partition key** nếu ứng dụng phụ thuộc thứ tự trên toàn entity; cách đó có thể cải thiện phân tán nhưng làm sai nghiệp vụ.

## 10. Lựa chọn số partitions cho Event Hub

Số partitions quyết định một giới hạn quan trọng về song song hóa và khả năng phân phối khóa.

| Số partitions | Số consumer instances | Phân phối gần đúng sau rebalance | Ý nghĩa |
|---:|---:|---|---|
| 4 | 1 | 4 | Một consumer xử lý tất cả |
| 4 | 2 | 2 + 2 | Hai processors chia tải |
| 4 | 3 | 2 + 1 + 1 | Phân bố có thể không đều |
| 4 | 4 | 1 + 1 + 1 + 1 | Một partition mỗi processor |
| 4 | 6 | 4 processors có partition; 2 có thể rỗi | Thêm Pods chưa chắc tăng throughput |
| 12 | 4 | Khoảng 3 + 3 + 3 + 3 | Có dư địa tăng consumers |

Đây là mô hình điển hình của **partition ownership** với EventProcessorClient khi hoạt động ổn định, không phải cam kết chính xác ở mọi thời điểm.

### 10.1. Thêm partitions có luôn tăng throughput?

Không. Namespace/tier của Event Hubs còn có giới hạn ingress/egress/capacity, và consumer có thể bị database giới hạn. Thêm partitions chỉ có ích nếu tạo thêm tính song song thực và nguồn tài nguyên phía dưới đáp ứng.

### 10.2. Có đổi partition count sau khi tạo không?

Khả năng tăng hoặc điều chỉnh partitions tùy SKU, tính năng và thời điểm hỗ trợ. Không mặc định có thể giảm partitions hoặc giữ nguyên routing của mọi key sau thay đổi. Nên thiết kế capacity và migration ngay từ đầu.

### 10.3. Nhiều partitions cũng có chi phí vận hành

Mỗi partition có processor context, checkpoint, ownership và telemetry. Chọn số lượng phù hợp thay vì chọn rất lớn khi workload chưa có nhu cầu.

## 11. Consumer group là một góc nhìn đọc độc lập

Consumer group cho phép nhiều ứng dụng xử lý cùng một log nhưng có **tiến độ độc lập**.

Ví dụ:

~~~text
Event Hub: order-events
├── Consumer group: analytics-prod
│   ├── analytics-worker-1
│   ├── analytics-worker-2
│   └── analytics-worker-3
├── Consumer group: fraud-prod
│   ├── fraud-worker-1
│   └── fraud-worker-2
└── Consumer group: archive-prod
    └── archive-worker-1
~~~

Analytics bị lỗi và phải đọc lại events không nhất thiết khiến fraud hoặc archive đọc lại. Mỗi consumer group cần cấu hình và trạng thái tiến độ phù hợp.

### 11.1. Consumer group không phải một bản sao message

Event Hubs vẫn lưu log theo retention, không nhân bản mỗi event riêng cho từng consumer group.

### 11.2. Consumer group khác ứng dụng thì nên tách

Các pipelines khác nhau cần policy checkpoint, schemas và trách nhiệm độc lập thì dùng consumer groups riêng. Không để dashboard thử nghiệm ghi/checkpoint làm ảnh hưởng consumer production.

### 11.3. Replicas của cùng ứng dụng thường chia sẻ group

Ba AKS Pods cùng thực hiện pipeline analytics nên dùng cùng group **analytics-prod** và cùng checkpoint/ownership coordination để chia partitions.

### 11.4. Không lạm dụng $Default

Nếu nhiều ứng dụng độc lập dùng chung consumer group **$Default**, rất dễ nhầm quyền, tiến độ và ownership. Nên đặt tên rõ ràng theo pipeline và môi trường.

## 12. Offset, sequence number và timestamp

Mỗi event trong partition có metadata:

| Thuộc tính | Ý nghĩa | Lưu ý |
|---|---|---|
| **Partition ID** | Partition chứa event | Không so sánh ID như thứ tự |
| **Sequence number** | Thứ tự do broker gán trong partition | Không phải sequence toàn cục |
| **Offset** | Vị trí trên partition log | Dùng cho resume/start position |
| **Enqueued time** | Thời điểm broker nhận event | Khác event time ở producer |
| **Partition key** | Routing key nếu producer đặt | Không nhất thiết là eventId |
| **Event ID** | Business/application identifier | Tùy event contract |
| **Aggregate version** | Thứ tự nghiệp vụ của một aggregate | Ứng dụng tự bảo đảm |

Ví dụ:

~~~text
Partition 2:
  seq 150 -> OrderCreated(ORD-1001, version=1)
  seq 151 -> OrderCreated(ORD-1002, version=1)
  seq 152 -> OrderPaid(ORD-1001, version=2)
  seq 153 -> OrderShipped(ORD-1001, version=3)
~~~

Sequence 150, 152 và 153 không liên tiếp cho ORD-1001 vì partition còn chứa events của đơn khác.

### 12.1. Event time khác enqueue time

Thiết bị có thể ghi event lúc 10:00 nhưng mạng mất kết nối và gửi tới Event Hubs lúc 10:10. Thời gian nghiệp vụ khác thời gian broker tiếp nhận; không lấy enqueue time để suy luận thứ tự xảy ra tuyệt đối giữa các thiết bị.

## 13. Checkpoint là gì?

**Checkpoint** lưu lại vị trí consumer đã xử lý an toàn trong mỗi partition. Khi processor restart, nó có thể tiếp tục từ vị trí sau checkpoint theo SDK.

~~~text
Partition 0: 100 -> 101 -> 102 -> 103 -> 104 -> 105
                           ^
                    checkpoint 102

Restart: đọc tiếp từ vùng sau 102 theo cơ chế processor.
~~~

Checkpoint không xóa event khỏi Event Hubs. Event cũ tiếp tục tồn tại cho đến khi quá retention hoặc chịu chính sách dữ liệu của dịch vụ.

### 13.1. Phân biệt checkpoint với Service Bus Complete

- **Service Bus Complete:** settlement message trong queue.
- **Azure Queue Storage Delete:** xóa message.
- **Event Hubs checkpoint:** lưu vị trí xử lý đã cam kết, không xóa event.
- **Kafka offset commit:** tương tự ý tưởng tiến độ nhưng theo giao thức Kafka, không tự đồng nghĩa Blob checkpoint store của Event Hubs SDK.

### 13.2. Checkpoint được ghi cho từng partition

Consumer group có nhiều partitions cần tiến độ tương ứng từng partition. Một checkpoint của partition 0 không làm partition 1 tiến lên.

## 14. Vì sao cần checkpoint store?

Nếu checkpoints chỉ nằm trong RAM của một process, khi process chết thì tiến độ mất. Do đó, khi dùng **Azure EventProcessorClient** với SDK Java, ứng dụng thường dùng **Azure Blob Storage checkpoint store**.

Store phục vụ hai loại thông tin:

1. **Checkpoint:** vị trí đã xử lý của mỗi partition.
2. **Partition ownership:** processor instance nào đang claim/điều phối partition.

~~~mermaid
flowchart TD
    EH[(Event Hub: 4 partitions)] --> A[Processor A]
    EH --> B[Processor B]
    A <--> ST[(Azure Blob checkpoint store)]
    B <--> ST
    A --> DB[(Business database)]
    B --> DB
~~~

### 14.1. Store không chứa toàn bộ event payload

Checkpoint Blob chứa thông tin tiến độ/ownership cần cho processor, không phải archive mọi sự kiện. Nếu muốn lưu sự kiện dài hạn, cần Event Hubs Capture hoặc một pipeline archive riêng.

### 14.2. Store cần quyền dữ liệu thực

Một application identity có quyền đọc Event Hubs nhưng không có quyền ghi Blob checkpoints vẫn có thể gặp lỗi ownership/checkpoint. Cần xác minh quyền trên **cả Event Hubs lẫn Storage**.

### 14.3. Vì sao không chia checkpoint store tùy tiện?

Hai processors của cùng pipeline dùng checkpoint stores khác nhau sẽ không chia sẻ ownership metadata đúng cách; chúng có thể xử lý trùng những partitions. Phải thống nhất store logic cho các replicas.

## 15. Checkpoint nên được ghi lúc nào?

Quy trình an toàn phổ biến:

1. Nhận event từ Event Hubs.
2. Parse và validate schema.
3. Thực hiện xử lý nghiệp vụ.
4. Ghi kết quả bền vững vào database/storage.
5. Chờ transaction/operation commit thành công.
6. Sau đó **update checkpoint**.

~~~mermaid
sequenceDiagram
    participant EH as Event Hubs
    participant C as Consumer
    participant DB as Database
    participant CS as Blob checkpoint store
    EH-->>C: Event seq 200
    C->>C: Validate
    C->>DB: Ghi kết quả với idempotency key
    DB-->>C: Commit thành công
    C->>CS: Checkpoint seq 200
    CS-->>C: Ghi nhận thành công
~~~

**Checkpoint trước DB commit** có thể làm mất sự kiện trong luồng xử lý bình thường sau crash. **Commit trước checkpoint** có thể tạo duplicate processing sau crash, vì vậy bắt buộc phải có idempotency.

### 15.1. Checkpoint không có nghĩa vừa nhận xong

Việc callback được gọi chỉ chứng minh event đã được nhận bởi consumer, không chứng minh nghiệp vụ đã hoàn tất.

### 15.2. Checkpoint không được vượt lỗi chưa giải quyết

Nếu seq 201 lỗi và seq 202 thành công, checkpoint 202 sẽ khiến seq 201 có nguy cơ bị bỏ qua khi restart. Chỉ checkpoint đến **vị trí liên tiếp cao nhất đã xử lý an toàn**.

## 16. Tần suất checkpoint: mỗi event, mỗi batch hay theo thời gian?

| Chiến lược | Ưu điểm | Nhược điểm |
|---|---|---|
| Checkpoint mỗi event | Ít sự kiện cần xử lý lại sau crash | Nhiều Blob writes/overhead |
| Checkpoint mỗi N events | Giảm I/O và chi phí checkpoint | Khi crash có thể replay một phần batch |
| Checkpoint theo thời gian | Dễ giới hạn khoảng lâu không ghi | Vẫn phải kiểm tra contiguous processed state |
| Checkpoint sau durable batch transaction | Khớp kết quả commit theo lô | Cần thiết kế batch/transaction phù hợp |

Ví dụ:

~~~text
Checkpoint tại sequence 500
Consumer xử lý thành công 501..550 nhưng chưa checkpoint
Consumer crash
Processor mới resume sau 500
=> Events 501..550 có thể được đọc lại
~~~

Nếu consumer đã ghi kết quả vào database, duplicate replay chỉ an toàn khi có unique constraint, idempotent upsert hoặc xử lý giao dịch phù hợp.

### 16.1. Đừng tối ưu Blob operations bằng cách làm mất dữ liệu

Checkpoint quá thưa tiết kiệm writes nhưng tăng replay cost. Checkpoint sai vị trí có thể làm mất sự kiện nghiệp vụ, nghiêm trọng hơn nhiều so với một số Blob operations.

### 16.2. Cân bằng theo RTO và idempotency

Chọn tần suất dựa trên throughput, thời gian xử lý lại chấp nhận được, chi phí I/O và độ tin cậy của downstream sink.

## 17. Xử lý song song trong một partition và nguy cơ mất event

Giả sử consumer xử lý song song các sự kiện trong partition:

~~~text
seq 100: hoàn tất
seq 101: CHƯA hoàn tất
seq 102: hoàn tất
seq 103: hoàn tất
~~~

Nếu cập nhật checkpoint 103 vì đó là sequence lớn nhất đã hoàn thành, sự kiện 101 có thể không được đọc lại sau restart.

### 17.1. High-water mark an toàn

Checkpoint chỉ nên tiến tới **highest contiguous processed sequence**. Trong ví dụ, nếu 100 đã hoàn tất nhưng 101 chưa, checkpoint an toàn vẫn chỉ đến 100.

### 17.2. Giữ thứ tự khi nghiệp vụ cần

Với OrderCreated → OrderPaid, xử lý song song events cùng partition có thể làm event sau hoàn tất trước event trước. Nếu thứ tự rất quan trọng, xử lý tuần tự theo partition hoặc dùng cơ chế theo aggregate key có kiểm soát.

### 17.3. Song song giữa partitions là hướng đơn giản hơn

Một consumer instance có thể xử lý nhiều partitions, mỗi partition theo thứ tự nội bộ. Đây thường là mô hình dễ lập luận hơn việc tạo thread pool tùy ý trong mỗi partition.

## 18. EventProcessorClient và cơ chế ownership

**EventProcessorClient** trong Azure SDK giúp:

- Tự phát hiện/đọc partitions của Event Hub.
- Phối hợp nhiều processor instances trong cùng consumer group.
- Claim và cập nhật partition ownership qua checkpoint store.
- Chia số partitions giữa processors.
- Đọc từ vị trí checkpoint khi bắt đầu.
- Gọi callback cho events/lỗi.
- Cho phép cập nhật checkpoint sau khi nghiệp vụ thành công.

Điều này giảm nhu cầu tự viết mã quản lý partitions và failover.

### 18.1. Ownership không có nghĩa quyền nghiệp vụ độc quyền tuyệt đối

Một partition thường chỉ có một processor owner trong nhóm được điều phối ổn định. Nhưng network delay, worker crash hoặc ownership handoff vẫn có thể gây xử lý trùng trong một khoảng. **Đừng dùng ownership thay idempotency.**

### 18.2. Checkpoint store điều phối bằng trạng thái chia sẻ

Mỗi processor thấy records ownership và cố claim phân vùng phù hợp. Nó không cần một danh sách Pod IP cố định.

### 18.3. Cùng consumer group chưa đủ

Nếu các processors của cùng pipeline dùng **hai checkpoint stores không phối hợp**, chúng có thể đọc cùng partition. Cần cùng group và store phù hợp, không chỉ trùng tên group.

## 19. Rebalance khi thêm hoặc mất consumer

Ví dụ Event Hub có 6 partitions, hai processors:

~~~text
Trước:
  Processor A: P0 P1 P2
  Processor B: P3 P4 P5

Sau khi có Processor C:
  A: P0 P1
  B: P2 P3
  C: P4 P5
~~~

Nếu B chết:

~~~text
Sau khi phát hiện ownership B không còn hợp lệ:
  A: P0 P1 P2
  C: P3 P4 P5
~~~

Đây là một sơ đồ minh họa. Thuật toán và thời gian rebalance phụ thuộc SDK, thời điểm claim, trạng thái checkpoint store và môi trường vận hành.

### 19.1. Handoff có thể đọc lại một đoạn

B đã ghi database nhưng chưa checkpoint; C lấy lại partition và đọc từ checkpoint cũ. Đây là tình huống bình thường trong mô hình **at-least-once**.

### 19.2. Rebalance quá thường xuyên là vấn đề

Nếu Pods restart liên tục hoặc checkpoint store mất kết nối, partition ownership dao động. Điều này có thể tạo read lại, warm-up và tăng lag. Theo dõi số lần ownership changes cùng health của processors.

### 19.3. Graceful shutdown giúp nhưng không hoàn toàn loại trừ duplicate

Khi Pod được shutdown hợp lệ, ứng dụng nên dừng nhận công việc mới, hoàn thành/checkpoint phần đang chạy khi an toàn rồi dừng processor. Node crash bất ngờ vẫn có thể xảy ra.

## 20. Vì sao cân bằng số partitions chưa chắc cân bằng CPU?

Giả sử Event Hub có 4 partitions và 4 consumers:

~~~text
P0: 75% events -> Consumer A, CPU 95%
P1:  8% events -> Consumer B, CPU 15%
P2:  9% events -> Consumer C, CPU 18%
P3:  8% events -> Consumer D, CPU 16%
~~~

Thuật toán sở hữu partition đã chia đều số partitions nhưng workload vẫn lệch. Điều này thường xảy ra khi **partition key skew**.

### 20.1. Cần đo per-partition

- Incoming events/bytes theo partition nếu khả dụng.
- Last enqueued sequence.
- Last processed/checkpointed sequence.
- Checkpoint age và consumer lag.
- CPU/memory/latency của processor sở hữu partition.
- Phân phối business keys, không log dữ liệu nhạy cảm.

### 20.2. Khi nào tăng consumers có ích?

Khi một processor đang sở hữu nhiều partitions có tải đáng kể. Tăng processors giúp chia các partitions đó sang instances khác.

### 20.3. Khi nào không có ích?

Khi bottleneck ở một partition đơn lẻ hoặc database chung. Tăng Pods vượt số partitions có thể chỉ tăng chi phí và quá trình rebalance.

## 21. Java producer: gửi theo partition key

Ví dụ Java sử dụng **azure-messaging-eventhubs** và **azure-identity** để gửi các events của cùng đơn hàng qua một partition key.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventDataBatch;
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubProducerClient;
import com.azure.messaging.eventhubs.models.CreateBatchOptions;

public class OrderProducer {
    public static void main(String[] args) {
        String namespace = System.getenv("EVENTHUB_NAMESPACE");
        String eventHub = System.getenv("EVENTHUB_NAME");
        String orderId = "ORD-1001";

        try (EventHubProducerClient producer =
                 new EventHubClientBuilder()
                     .credential(
                         namespace, eventHub,
                         new DefaultAzureCredentialBuilder().build())
                     .buildProducerClient()) {

            EventDataBatch batch = producer.createBatch(
                new CreateBatchOptions().setPartitionKey(orderId));

            boolean first = batch.tryAdd(new EventData(
                "{\"eventType\":\"OrderCreated\",\"orderId\":\"ORD-1001\"}"));
            boolean second = first && batch.tryAdd(new EventData(
                "{\"eventType\":\"OrderPaid\",\"orderId\":\"ORD-1001\"}"));

            if (!first || !second) {
                throw new IllegalStateException("Batch vuot kich thuoc");
            }

            producer.send(batch);
            System.out.println("Sent key=" + orderId);
        }
    }
}
~~~

### 21.1. Chuẩn bị đúng môi trường

- **EVENTHUB_NAMESPACE**: fully qualified namespace như **ehns-name.servicebus.windows.net**.
- **EVENTHUB_NAME**: tên Event Hub, không phải namespace.
- Danh tính producer cần **Azure Event Hubs Data Sender** hoặc role tương ứng.
- Events phải đáp ứng giới hạn kích thước theo SDK/SKU.
- Dùng Maven/Gradle dependencies phiên bản tương thích với runtime Java.

### 21.2. Cùng key chưa đủ bảo đảm business order

Nếu nhiều producers gửi song song hoặc retry không có sequence control, broker lưu events theo thứ tự nhận được. Nên có **aggregateVersion** và điều phối producer khi nghiệp vụ cần order nghiêm ngặt.

### 21.3. Send timeout có thể tạo duplicate

Nếu broker nhận event nhưng producer không nhận được acknowledgment do mất mạng, retry send có thể tạo một event tương đương nữa. Consumer vẫn cần idempotency theo eventId.

## 22. Java consumer: EventProcessorClient và BlobCheckpointStore

Các dependencies cần thiết:

- **azure-messaging-eventhubs**
- **azure-messaging-eventhubs-checkpointstore-blob**
- **azure-storage-blob**
- **azure-identity**

Ví dụ minh họa cấu hình processor với **Blob checkpoint container đã tồn tại**:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobContainerClientBuilder;

public class EventHubConsumer {
    public static void main(String[] args)
            throws InterruptedException {

        String namespace = System.getenv("EVENTHUB_NAMESPACE");
        String hubName = System.getenv("EVENTHUB_NAME");
        String group = System.getenv("EVENTHUB_CONSUMER_GROUP");
        String blobEndpoint = System.getenv("CHECKPOINT_BLOB_ENDPOINT");
        String container = System.getenv("CHECKPOINT_CONTAINER");

        TokenCredential identity =
            new DefaultAzureCredentialBuilder().build();

        BlobContainerAsyncClient blobClient =
            new BlobContainerClientBuilder()
                .endpoint(blobEndpoint)
                .containerName(container)
                .credential(identity)
                .buildAsyncClient();

        EventProcessorClient processor =
            new EventProcessorClientBuilder()
                .credential(namespace, hubName, identity)
                .consumerGroup(group)
                .checkpointStore(new BlobCheckpointStore(blobClient))
                .processEvent(context -> {
                    String partition =
                        context.getPartitionContext().getPartitionId();
                    long sequence =
                        context.getEventData().getSequenceNumber();

                    try {
                        // Demo: thay bằng ghi database bền vững và idempotent.
                        processDurably(
                            context.getEventData().getBodyAsString());

                        // Checkpoint sau khi nghiệp vụ commit.
                        context.updateCheckpoint();

                        System.out.printf(
                            "Processed partition=%s seq=%d%n",
                            partition, sequence);
                    } catch (Exception ex) {
                        System.err.printf(
                            "FAILED partition=%s seq=%d error=%s%n",
                            partition, sequence, ex.getClass().getName());

                        // Không checkpoint event lỗi.
                        // Production phải dừng/retry/quarantine theo policy.
                    }
                })
                .processError(error -> {
                    System.err.println(
                        "Processor error: " + error.getThrowable());
                })
                .buildEventProcessorClient();

        processor.start();
        Thread.sleep(60_000); // Chỉ là demo local.
        processor.stop();
    }

    private static void processDurably(String body) {
        // Placeholder: KHÔNG phải durable storage write thật.
        if (body == null || body.isEmpty()) {
            throw new IllegalArgumentException("Empty event");
        }
    }
}
~~~

### 22.1. Điều kiện quan trọng

- **CHECKPOINT_BLOB_ENDPOINT** có dạng **https://storage-name.blob.core.windows.net**.
- Blob container phải được tạo trước và identity có quyền đọc/ghi dữ liệu blob.
- Event Hub consumer identity cần quyền nhận events.
- Mọi instances của cùng pipeline dùng cùng consumer group và checkpoint store logic.
- **processDurably** chỉ là placeholder. Phải thay bằng transaction/commit thật trước production.
- Ghi checkpoint **mỗi event** giúp bài lab dễ hiểu nhưng có thể tốn nhiều Blob writes.

### 22.2. Lưu ý về bắt lỗi trong callback

Nếu bắt exception, không checkpoint event lỗi nhưng callback vẫn tiếp tục, event sau có thể được checkpoint và bỏ qua event lỗi. Trong production cần **dừng tiến độ partition, retry hoặc quarantine event lỗi bền vững** trước khi cho phép checkpoint cao hơn.

### 22.3. SDK version

Đối chiếu imports/methods và dependencies với phiên bản Azure SDK trong dự án. Một bản code minh họa không thay thế việc biên dịch và kiểm thử trên phiên bản cụ thể.

## 23. Thiết kế consumer idempotent

Kịch bản:

~~~text
Event sequence 600
-> Consumer ghi dữ liệu thành công
-> Worker chết trước khi ghi checkpoint
-> Processor mới đọc lại event sequence 600
~~~

Nếu consumer gửi email hai lần hoặc ghi hai hóa đơn, hệ thống có lỗi nghiệp vụ.

### 23.1. Sử dụng eventId

Ví dụ event:

~~~json
{
  "eventId": "evt-600",
  "aggregateId": "ORD-1001",
  "aggregateVersion": 3,
  "eventType": "OrderPaid",
  "occurredAt": "2026-11-20T10:20:00Z"
}
~~~

Trong database, đặt unique constraint hoặc **inbox table** theo eventId/business operation key:

1. Kiểm tra event đã xử lý chưa.
2. Nếu chưa, ghi dữ liệu nghiệp vụ và trạng thái processed trong transaction.
3. Commit.
4. Sau khi commit, checkpoint.
5. Nếu eventId đã tồn tại ở trạng thái completed, coi đây là replay hợp lệ và checkpoint khi an toàn.

### 23.2. Side effects bên ngoài transaction

Payment API, email hoặc gửi message vào broker khác có thể không cùng transaction với database. Dùng **transactional outbox**, idempotency key ở API ngoài hoặc cơ chế đối soát phù hợp.

### 23.3. Không dựa vào Event Hubs để đảm bảo exactly-once

Event Hubs, consumer group và Blob checkpoint store không tự bảo đảm exactly-once end-to-end cho database, mail hoặc thanh toán. Phải chứng minh tính đúng bằng thiết kế idempotent.

## 24. Xử lý lỗi, retry và quarantine

Một event sai schema có thể làm consumer lỗi mãi; khác với Service Bus, **Event Hubs không có dead-letter subqueue tích hợp** để tự chuyển event lỗi.

~~~mermaid
flowchart TD
    EV[Event] --> P{Validate và process}
    P -->|Thành công| DB[Commit kết quả]
    DB --> CP[Checkpoint khi an toàn]
    P -->|Lỗi tạm thời| RETRY[Retry có giới hạn và backoff]
    RETRY --> P
    P -->|Lỗi dữ liệu vĩnh viễn| Q[Quarantine vào Storage/Service Bus]
    Q --> DONE{Đã lưu bền vững?}
    DONE -->|Có| CP
    DONE -->|Không| STOP[Dừng partition, không checkpoint]
~~~

### 24.1. Lỗi tạm thời

Timeout, HTTP 503, database failover: retry có giới hạn và exponential backoff/jitter, kết hợp circuit breaker để tránh retry storm.

### 24.2. Lỗi vĩnh viễn

Schema không hỗ trợ, business rule không thể khắc phục: ghi event và metadata vào một **quarantine store** có kiểm soát, sau đó chỉ checkpoint nếu workflow chấp nhận event đã được phân loại và lưu bền vững.

### 24.3. Lỗi chưa xác định

Đừng chỉ ghi log rồi tiếp tục checkpoint event sau. Dừng/giảm consumer phù hợp, gửi cảnh báo và điều tra nguyên nhân.

### 24.4. Event ordering và lỗi

Nếu một event OrderPaid chưa được xử lý, checkpoint qua OrderShipped sẽ bỏ mất cơ hội xử lý theo thứ tự. Cần cân nhắc bảo toàn ordering theo aggregate và cách xử lý quarantine/replay.

## 25. At-least-once, duplicate và giới hạn của checkpoint

Cơ chế checkpoint sau xử lý bền vững dẫn tới một lựa chọn an toàn:

- **Nếu DB commit thành công nhưng checkpoint thất bại:** có thể đọc lại, cần idempotency.
- **Nếu checkpoint thành công nhưng DB commit thất bại:** có nguy cơ bỏ mất event, khó phục hồi.

Vì thế quy trình phổ biến ưu tiên **at-least-once processing với idempotent sink**.

### 25.1. Checkpoint không phải transaction với database

Azure Blob checkpoint write và database transaction không tự động là một distributed ACID transaction.

### 25.2. Có thể tăng an toàn bằng bảng processed events

Lưu eventId và business result trong cùng database transaction. Khi đọc lại, consumer biết event đã xử lý.

### 25.3. Trường hợp cần strict ordering

Nếu một event lỗi ngăn tất cả events sau trong cùng aggregate, cần quyết định rõ: tạm dừng xử lý partition, xử lý một nhánh quarantine có sequence gap tracking hoặc áp dụng state machine chịu out-of-order. Không có cách “vừa bỏ qua lỗi, vừa giữ thứ tự tuyệt đối” miễn phí.

## 26. Starting position và checkpoint cũ

Một consumer có thể đọc từ:

- **Checkpoint còn hợp lệ** đã lưu.
- **Earliest event còn trong retention**.
- **Latest/new events** khi không muốn backlog.
- **Một offset/sequence/time cụ thể** theo SDK và kế hoạch replay.

### 26.1. Earliest không phải từ lúc Event Hub được tạo

Earliest chỉ là event cũ nhất **còn được giữ**. Events đã hết retention không thể đọc lại từ Event Hubs dù checkpoint còn lưu vị trí cũ.

### 26.2. Latest có thể làm mất backlog

Nếu checkpoint bị mất và consumer khởi động ở latest, các events còn tồn tại nhưng chưa xử lý có thể bị bỏ qua. Cần lựa chọn starting position theo RPO và nghiệp vụ.

### 26.3. Mất checkpoint store

Nếu Blob checkpoint container bị xóa, processor không còn tiến độ cũ. Không tự xóa store để “reset lỗi” khi chưa xác minh retention, archive và kế hoạch replay.

## 27. Retention và Event Hubs Capture

Event Hubs lưu events theo **retention window** của SKU/cấu hình. Tiến độ consumer không làm sự kiện ở lại lâu hơn.

Ví dụ:

~~~text
Earliest retained ---------- Checkpoint -------- Latest retained
        |                         |                      |
  Có thể đọc lại          Đã xử lý đến đây        Events mới
~~~

Khi consumer dừng lâu hơn retention, có thể có một khoảng dữ liệu không còn sẵn để xử lý từ Event Hub.

### 27.1. Capture không phải checkpoint

**Event Hubs Capture** có thể đưa luồng dữ liệu ra Blob Storage hoặc ADLS Gen2 theo tính năng/SKU được hỗ trợ. Đây là archive dữ liệu, không phải tiến độ xử lý của từng consumer group.

### 27.2. Xây dựng kế hoạch replay

1. Xác định partition, khoảng thời gian và offsets.
2. Kiểm tra dữ liệu còn trong retention.
3. Nếu không, xem archive đã được cấu hình trước đó chưa.
4. Chọn consumer group/process riêng cho replay khi cần tách production.
5. Bảo đảm target sink idempotent.
6. Đo backlog, chi phí và kết quả.
7. Không ghi đè checkpoints production khi chưa có phê duyệt.

## 28. Consumer lag và tiến độ xử lý

**Consumer lag** mô tả consumer còn cách dữ liệu mới nhất bao xa.

Một cách ước lượng theo sequence cho mỗi partition:

\[
\text{Lag}_{p} \approx
\text{LatestEnqueuedSequence}_{p}
-
\text{CheckpointSequence}_{p}
\]

Ví dụ:

| Partition | Latest seq | Checkpoint seq | Lag gần đúng |
|---|---:|---:|---:|
| P0 | 1200 | 1180 | 20 |
| P1 | 900 | 899 | 1 |
| P2 | 1400 | 980 | 420 |
| P3 | 560 | 558 | 2 |

P2 đang chậm đáng kể so với các partitions khác.

### 28.1. Checkpoint lag khác processing lag

Nếu checkpoint theo batch 100 events, consumer có thể xử lý 99 events kể từ checkpoint nhưng chưa cập nhật vị trí lưu. Dựa chỉ vào checkpoint sẽ ước tính lag lớn hơn phần công việc chưa xử lý thực tế.

### 28.2. Lag theo thời gian

Một metric bổ sung là **event age**, ví dụ khoảng chênh giữa thời điểm broker enqueue và thời điểm event được xử lý thành công. Nó thường dễ gắn với SLO hơn số lượng events.

### 28.3. Không cộng sequence numbers giữa partitions để suy thứ tự

Sequence chỉ có ý nghĩa theo partition. Nên đo **max lag theo partition**, consumer processing delay và throughput riêng thay vì chỉ lấy một số trung bình tổng.

## 29. Consumer group, ownership và checkpoint store cần nhất quán

Một pipeline production hợp lý:

~~~text
Pipeline: orders-analytics-prod
Event Hub: order-events
Consumer group: analytics-prod
Blob container: analytics-prod-checkpoints

AKS Pod A -> EventProcessorClient
AKS Pod B -> EventProcessorClient
AKS Pod C -> EventProcessorClient

Tất cả pods dùng cùng group và cùng checkpoint store logic.
~~~

### 29.1. Vì sao tách dev và prod?

Nếu staging và production dùng chung consumer group/store ngoài ý muốn, staging có thể tranh ownership hoặc thay đổi checkpoint của production.

### 29.2. Blob checkpoint store có thể tổ chức nhiều pipelines không?

SDK có cơ chế tổ chức metadata theo namespace/hub/group. Tuy vậy, phân tách container hoặc quyền theo pipeline/môi trường thường làm việc vận hành rõ ràng hơn. Điều quan trọng là **các replicas cùng pipeline phải chia sẻ đúng store**, còn pipelines độc lập không dùng nhầm tiến độ/ownership.

### 29.3. Không lưu business state chỉ trong memory của Pod

Partition ownership có thể chuyển Pod sau rebalance. Cần lưu kết quả/checkpoint vào nơi bền vững.

## 30. Azure Functions Event Hubs trigger

Với **Azure Functions Event Hubs trigger**, Functions runtime/extension hỗ trợ điều phối event processing, checkpoint và partition ownership theo khả năng của extension.

Ví dụ logic:

~~~text
Event Hub: telemetry, 8 partitions
Function App: processTelemetry

Instance 1: P0 P1
Instance 2: P2 P3
Instance 3: P4 P5
Instance 4: P6 P7
~~~

Khi instance tăng/giảm, ownership có thể được điều phối lại.

### 30.1. Có cần tự tạo EventProcessorClient trong handler?

Thông thường **không**. Event Hubs trigger đã điều phối việc nhận events. Nếu bạn tự tạo một processor bên trong Function handler, dễ tạo readers/ownership không cần thiết và khó quản lý lifecycle.

### 30.2. Host.json và extension versions

Batching, checkpoint frequency, concurrency và scaling có thể phụ thuộc Azure Functions runtime, Event Hubs extension version và hosting plan. Không copy một cấu hình cũ rồi khẳng định luôn đúng.

### 30.3. Xử lý function lỗi

Không mặc định throw exception sẽ đưa event vào DLQ vì Event Hubs không có native DLQ như Service Bus. Cần xác định extension retry/checkpoint behavior và cách quarantine ứng dụng.

### 30.4. Scale-out vẫn bị chi phối bởi partitions

Thêm hàng chục Function instances khi chỉ có bốn partitions không tự tạo thêm bốn mươi luồng phân vùng độc lập.

## 31. AKS consumers và autoscaling

Với Java EventProcessorClient chạy trong AKS:

~~~mermaid
flowchart LR
    EH[(Event Hubs)] --> A[Consumer Pod A]
    EH --> B[Consumer Pod B]
    EH --> C[Consumer Pod C]
    A <--> CK[(Blob checkpoint store)]
    B <--> CK
    C <--> CK
    A --> DB[(Database)]
    B --> DB
    C --> DB
~~~

Mỗi Pod cần:

- Event Hubs identity/receiver rights.
- Blob checkpoint store data rights.
- Cùng consumer group và store logic.
- Requests/limits phù hợp memory/CPU.
- Startup và graceful shutdown.
- Structured telemetry theo partition.
- Idempotent database write.

### 31.1. HPA/KEDA nên quan sát điều gì?

CPU một Pod không đủ để hiểu backlog. Nếu AKS/KEDA version hỗ trợ scaler cho Event Hubs, cần cấu hình đúng checkpoint/consumer group/identity và hiểu cách scaler ước lượng lag.

### 31.2. Spot eviction

Nếu dùng Spot nodes cho worker có khả năng retry, phải chấp nhận Pods có thể bị dừng bất ngờ. Checkpoint và idempotency giúp phục hồi, nhưng không bảo đảm latency liên tục.

### 31.3. Pod count vượt partition count

HPA có thể tăng Pod count trong khi nhiều Pods không nhận partition. Đặt min/max và autoscaling policy theo số partitions và downstream capacity thực tế.

## 32. Bảo mật: Event Hubs và Azure Blob là hai data planes

Một consumer đọc Event Hubs và ghi Blob checkpoint store cần quyền trên **hai dịch vụ**:

| Identity | Vai trò minh họa | Trách nhiệm |
|---|---|---|
| Producer identity | Azure Event Hubs Data Sender | Gửi events |
| Consumer identity | Azure Event Hubs Data Receiver | Đọc events |
| Consumer trên Blob container | Storage Blob Data Contributor | Ghi checkpoints/ownership |
| Platform admin | Quyền quản lý Azure resources được giới hạn | Tạo/sửa config, không mặc định đọc mọi dữ liệu |

### 32.1. Managed identity/Workload Identity

Azure Functions có thể dùng managed identity. Với AKS có thể dùng **Microsoft Entra Workload ID** để pod lấy token cho Azure SDK. **DefaultAzureCredential** phải được cấu hình để dùng đúng identity mong muốn.

### 32.2. Private networking

Nếu Event Hubs namespace và Storage account sử dụng private endpoints, consumers cần DNS, routing và outbound đến **cả hai** endpoint.

### 32.3. Không cấp Owner để sửa lỗi 403

Phân biệt Azure Resource Manager role và **data-plane role**. Azure Reader trên resource group không tự cho phép đọc events hoặc ghi Blob.

### 32.4. Không log secrets/PII

Partition key, payload và checkpoint metadata có thể được log. Tránh ghi email, token, số thẻ hoặc raw body chứa dữ liệu cá nhân nếu không có cơ chế bảo vệ.

## 33. Azure CLI: tạo Event Hub cho lab

**Chỉ dùng trên subscription/resource group được cấp phép và có ngân sách.** Lệnh cần được kiểm tra theo phiên bản Azure CLI, SKU và region.

~~~bash
az login
az account set --subscription "<subscription-id>"

az group create \
  --name rg-stream-lab \
  --location southeastasia

az eventhubs namespace create \
  --resource-group rg-stream-lab \
  --name ehns-stream-lab-unique \
  --location southeastasia \
  --sku Standard
~~~

Tạo Event Hub:

~~~bash
az eventhubs eventhub create \
  --resource-group rg-stream-lab \
  --namespace-name ehns-stream-lab-unique \
  --name order-events \
  --partition-count 4
~~~

Tạo consumer group:

~~~bash
az eventhubs eventhub consumer-group create \
  --resource-group rg-stream-lab \
  --namespace-name ehns-stream-lab-unique \
  --eventhub-name order-events \
  --name analytics-lab
~~~

Xem metadata:

~~~bash
az eventhubs eventhub show \
  --resource-group rg-stream-lab \
  --namespace-name ehns-stream-lab-unique \
  --name order-events \
  --output json
~~~

**ehns-stream-lab-unique** là tên minh họa, chưa chắc còn khả dụng. Event Hubs CLI options hoặc pricing features có thể thay đổi theo phiên bản; không dùng lệnh lab để thay đổi tài nguyên production.

### 33.1. Blob checkpoint store tạo riêng

Chuẩn bị Azure Storage account và một Blob container, ví dụ **analytics-lab-checkpoints**. Azure CLI tạo Event Hub **không tự tạo checkpoint container** cho Java EventProcessorClient. Cần cấp quyền Blob Data Contributor tương ứng.

### 33.2. Consumer groups không đồng nghĩa có checkpoint

Tạo consumer group chỉ thiết lập một góc nhìn đọc độc lập. Checkpoint/ownership store là một thành phần khác khi dùng EventProcessorClient.

## 34. Bài toán: một tenant chiếm phần lớn tải

Giả sử Event Hub có 8 partitions và 4 AKS consumers. Mỗi phút có 100.000 events; 60% của một tenant duy nhất.

### Phương án A — Partition key là tenantId

Khoảng 60% events cùng một key có thể tập trung ở một partition. Một Pod sở hữu partition đó quá tải, các Pods khác còn rảnh.

### Phương án B — Partition key là orderId

Nếu thứ tự chỉ cần theo từng order, các orders của tenant lớn được trải trên nhiều partitions. Điều này có thể cải thiện độ cân bằng.

### Khi nào không được đổi key?

Nếu nghiệp vụ yêu cầu tất cả events của tenant phải được xử lý tuần tự tuyệt đối, chuyển sang orderId có thể phá yêu cầu. Lúc đó phải chọn chiến lược ordering/aggregate khác, tối ưu single-partition processing hoặc thương lượng lại SLO.

### Kết luận

**Chọn key dựa trên đơn vị nghiệp vụ cần giữ thứ tự trước, phân tán tải sau.** Không có key hoàn hảo cho mọi loại sự kiện.

## 35. Bài toán tính throughput và số consumers

Giả sử 6 partitions, mỗi partition khi xử lý tuần tự có khả năng hoàn thành 180 events/giây trong điều kiện đo đạc.

Thông lượng lý thuyết:

\[
6 \times 180 = 1.080\ \text{events/giây}
\]

Tăng từ 3 lên 6 processors có thể giúp phân phối partitions tốt hơn, nhưng nếu giới hạn là 180 events/giây **mỗi partition**, tăng lên 10 processors không làm tăng giới hạn logic đó.

Ví dụ phân phối không đều:

~~~text
P0: 180 events/s
P1: 180 events/s
P2: 180 events/s
P3:  60 events/s  <-- partition bị nghẽn
P4: 180 events/s
P5: 180 events/s

Tổng = 960 events/s
~~~

Nếu P3 nhận 400 events/giây, riêng P3 vẫn tích tụ lag dù tổng throughput có vẻ lớn.

### 35.1. Điều gì làm năng lực thực thấp hơn lý thuyết?

- JSON parsing và schema validation.
- Database write latency và locks.
- Network round trips.
- Connection pool/throttling.
- Checkpoint writes.
- Rebalance/startup.
- Partition key skew và sự kiện lớn.

Phải chạy load test với dữ liệu đại diện, không lấy phép nhân đơn giản làm SLA.

## 36. Thử nghiệm rebalance có kiểm soát

1. Chuẩn bị Event Hub lab 4 partitions.
2. Tạo consumer group riêng và Blob checkpoint store riêng.
3. Chạy một EventProcessorClient instance.
4. Ghi lại các partitions mà instance sở hữu.
5. Khởi động một instance thứ hai với **cùng group và store**.
6. Quan sát ownership sau khi rebalance.
7. Đẩy events liên tục với partition keys cố định.
8. Dừng một instance giữa quá trình xử lý.
9. Quan sát instance còn lại claim partition sau khi ownership cũ hết hiệu lực.
10. Xác minh database không có duplicate dù một số events có thể được nhận lại.

### 36.1. Không giả định failover tức thì

Ownership detection và claim có độ trễ phụ thuộc SDK, Blob store và điều kiện mạng. Hãy đo thay vì hứa một giá trị thời gian cố định.

### 36.2. Kết quả cần báo cáo

- Thời điểm dừng worker.
- Thời điểm partition được claim lại.
- Last checkpoint trước và sau failover.
- Events xử lý trùng.
- Số business records cuối cùng.
- Consumer lag tăng trong giai đoạn rebalance.

## 37. Lỗi thường gặp và hướng điều tra

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Thêm Pods nhưng lag không giảm | Số partitions ít, hot partition, downstream nghẽn | Ownership, per-partition lag, DB latency |
| Events xử lý hai lần | Crash trước checkpoint, replay, store không phối hợp | EventId/inbox, checkpoint timeline |
| Consumer bắt đầu đọc từ đầu | Không tìm được checkpoint, nhầm group/store | Cấu hình namespace/hub/group/container |
| Consumer bỏ qua backlog | Starting position latest, checkpoint quá sớm | Checkpoints, earliest/latest, retention |
| Một partition lag rất lớn | Key skew, payload nặng, handler chậm | Partition-level metrics và key distribution |
| Checkpoint Blob lỗi 403 | RBAC sai scope/identity | Data-plane role và identity principal |
| Checkpoint Blob timeout | Private DNS/route/firewall | Kiểm tra endpoint và VNet |
| Ownership thay đổi liên tục | Pods crash, network flapping, Blob errors | Processor errors và deployment events |
| Processing xong nhưng checkpoint đứng yên | UpdateCheckpoint lỗi hoặc checkpoint theo batch | SDK logs và store |
| Replay không còn dữ liệu | Event đã hết retention | Archive/Capture và RPO |
| Events sai thứ tự | Khác key, nhiều producers, app parallelism | PartitionId, business sequence, producer logs |

### 37.1. Quy trình điều tra ưu tiên

1. Xác minh đúng namespace/Event Hub/consumer group.
2. Kiểm tra partitions, ownership và checkpoint store.
3. Tính lag theo từng partition.
4. Kiểm tra producer key distribution.
5. Kiểm tra consumer exceptions và downstream dependencies.
6. Đối chiếu checkpoint update với durable commit.
7. Xác nhận retention còn đủ để recovery.
8. Thử sửa/rollback trên môi trường staging trước.

## 38. Monitoring bằng Azure Monitor và telemetry ứng dụng

Những tín hiệu quan trọng:

| Cấp | Metric/log cần xem | Mục đích |
|---|---|---|
| Event Hubs namespace | Incoming/Outgoing messages, bytes, errors, throttling | Kiểm tra ingestion và egress |
| Partition | Last enqueued sequence/time, workload distribution | Phát hiện hot partitions |
| Checkpoint store | Last checkpointed sequence/time, Blob errors | Phát hiện tiến độ bị kẹt |
| Consumer | Processing duration, success/failure, retry count | Đánh giá chất lượng handler |
| Ownership | Partitions mỗi processor, claim/rebalance events | Hiểu load balancing |
| Database | Latency, timeouts, connection limits | Tìm bottleneck downstream |
| End-to-end | Event age, processing latency, duplicate rate | Đánh giá SLO |
| Cost | Event Hubs capacity, Blob operations, compute, logs | Kiểm soát ngân sách |

**Không phải mọi metric per-partition/ownership đều có sẵn trực tiếp trong Azure Monitor mặc định.** Có thể cần instrument SDK hoặc xuất custom metrics theo partitionId.

### 38.1. Alert gợi ý

- Max per-partition lag vượt SLO.
- Checkpoint không tiến trong khi ingress tăng.
- Rebalance quá thường xuyên.
- Blob checkpoint write errors liên tục.
- Event Hubs throttling.
- Database latency tăng cùng consumer backlog.
- Consumer Pods tăng nhưng usable partition ownership không tăng.
- Retention window sắp không đủ để consumer bắt kịp.

### 38.2. Đừng chỉ nhìn average lag

Một partition có lag một triệu events còn ba partitions không lag; average có thể che vấn đề. Sử dụng **max lag** hoặc biểu đồ từng partition.

## 39. Quản lý chi phí và capacity

Các khoản chi phí có thể bao gồm:

- Event Hubs namespace/tier, capacity/throughput, ingress/egress.
- Dung lượng/retention và khả năng Capture theo SKU.
- Azure Blob Storage checkpoint container và số operations.
- Azure Functions executions hoặc AKS/VM compute.
- Networking: Private Link, firewall, egress.
- Database và storage sink.
- Azure Monitor/Log Analytics ingestion, retention.
- Vận hành và replay khi có sự cố.

### 39.1. Checkpoint mỗi event có giá

Nếu 20 partitions cùng xử lý hàng nghìn events/giây, checkpoint quá thường xuyên làm tăng Blob operations. Chọn tần suất phù hợp với RTO và duplicate replay cost.

### 39.2. Nhiều consumer groups tiêu thụ tài nguyên đọc

Mỗi pipeline đọc riêng và thực thi riêng. Các nhóm test không sử dụng nên được quản lý/dọn theo quy trình.

### 39.3. Nhiều Pods không phải lúc nào tốt hơn

Khi số Pods vượt số partitions hoặc phần lớn events nằm một hot partition, tăng compute thường không tăng throughput tương ứng.

### 39.4. Retention và archive

Retention phải phù hợp thời gian gián đoạn chấp nhận được. Nếu cần replay lâu hơn, xem xét archive/Capture thay vì giả định Event Hubs giữ sự kiện vô hạn.

## 40. Bài thực hành end-to-end

**Bối cảnh:** đội phát triển cần xử lý các order events theo đúng thứ tự từng đơn, mở rộng lên nhiều consumers, rồi khôi phục sau khi một worker crash.

### Phần A — Chuẩn bị

1. Xác nhận tài khoản Azure, subscription lab và quyền cần thiết.
2. Tạo Event Hub **order-events** với bốn partitions.
3. Tạo consumer group **analytics-lab**.
4. Tạo Azure Blob checkpoint container riêng.
5. Cấp receiver role cho consumer và Blob Data Contributor cho checkpoint.
6. Chuẩn bị Java SDK dependencies và môi trường thử nghiệm.
7. Đặt giới hạn chi phí và không dùng database production.

### Phần B — Tạo và gửi events

1. Định nghĩa eventId, orderId, aggregateVersion và eventType.
2. Gửi OrderCreated → OrderPaid → OrderShipped cho **ORD-1001** cùng partition key.
3. Gửi một số orders khác với keys khác nhau.
4. Quan sát partition ID, sequence number và enqueue time.
5. Kiểm tra các events của ORD-1001 nằm trong cùng partition.
6. Không kết luận keys khác nhau luôn có partition khác nhau.

### Phần C — Checkpoint

1. Chạy một EventProcessorClient.
2. Ghi dữ liệu thử nghiệm theo eventId với unique constraint.
3. Chỉ checkpoint sau transaction commit.
4. Đo sequence đã xử lý và checkpoint sequence.
5. Thử checkpoint mỗi event và mỗi N events trên dữ liệu giả.
6. Đo số events có thể phải xử lý lại sau crash.

### Phần D — Rebalance

1. Khởi động processor thứ hai cùng group/store.
2. Quan sát partition ownership.
3. Dừng processor đầu.
4. Xem processor còn lại nhận partitions.
5. Khởi động lại processor đầu.
6. Ghi thời gian rebalance và trạng thái lag.

### Phần E — Crash sau DB commit, trước checkpoint

1. Gửi event có eventId cố định.
2. Cho consumer commit kết quả rồi mô phỏng crash trước checkpoint.
3. Khởi động lại.
4. Quan sát event được đọc lại.
5. Xác minh consumer idempotent không tạo business record thứ hai.
6. Ghi rõ đây là tình huống at-least-once.

### Phần F — Hot partition

1. Gửi nhiều events dùng cùng partition key **tenant-giant**.
2. Gửi events của các tenants/đơn hàng nhỏ khác.
3. So sánh per-partition lag và processing throughput.
4. Thêm consumer instances tới 4 rồi 6.
5. Quan sát số partitions vẫn là 4.
6. Thảo luận vì sao chuyển key từ tenantId sang orderId chỉ đúng khi nghiệp vụ cho phép.

### Phần G — Replay và quarantine

1. Gửi một event sai schema.
2. Cấu hình consumer ghi quarantine an toàn.
3. Chỉ checkpoint sau khi quarantine đã commit.
4. Dùng consumer group lab riêng để thử replay trong retention.
5. Không xóa hoặc chỉnh checkpoints production.
6. Kiểm tra không tạo duplicate side effect.

### Phần H — Báo cáo và cleanup

Ghi lại:

| Chỉ số | Trước | Sau/quan sát |
|---|---|---|
| Số partitions | 4 | 4 |
| Số processors | 1 | 2, 4, 6 |
| Ownership per processor | Đo thực | Đo thực |
| Max partition lag | Đo thực | Đo thực |
| Last checkpoint | Đo thực | Đo thực |
| Duplicates sau failover | Đo thực | Kỳ vọng 0 business duplicates |
| Throughput | Đo thực | Đo thực |
| Blob checkpoint operations | Đo thực | Đo thực |
| Chi phí | Đo thực | Đo thực |

Dừng processors và producers, rồi chỉ dọn tài nguyên thuộc bài lab khi có quyền và đã xác minh không còn phụ thuộc.

**Tiêu chí hoàn thành:** bạn giải thích được cơ chế partition routing, chứng minh checkpoint diễn ra sau durable write, quan sát rebalance và thấy idempotency ngăn duplicate sau crash.

## 41. Checklist trước khi dùng production

- [ ] Xác định entity/aggregate cần giữ thứ tự.
- [ ] Partition key đúng nghiệp vụ, không lộ dữ liệu nhạy cảm.
- [ ] Đã phân tích hot keys và key skew.
- [ ] Số partitions được thiết kế theo throughput/SLO và khả năng scale.
- [ ] Không dựa vào global ordering giữa partitions.
- [ ] Producer có eventId, aggregateVersion, schemaVersion và correlationId.
- [ ] Không phụ thuộc công thức hashing chưa được bảo đảm.
- [ ] Có kế hoạch khi partition count/topology thay đổi.
- [ ] Mỗi pipeline độc lập có consumer group phù hợp.
- [ ] Tất cả replicas cùng pipeline chia sẻ checkpoint/ownership store.
- [ ] Blob checkpoint store có container, RBAC và network đúng.
- [ ] Checkpoint chỉ được ghi sau durable commit.
- [ ] Không checkpoint qua events chưa xử lý.
- [ ] Xử lý song song trong partition không phá ordering.
- [ ] Consumer idempotent khi crash/rebalance/replay.
- [ ] Lỗi tạm thời có retry budget/backoff, không loop vô hạn.
- [ ] Event lỗi vĩnh viễn có quarantine store, không bỏ qua âm thầm.
- [ ] Hiểu Event Hubs không có native Service Bus-like DLQ.
- [ ] Retention đủ cho outage/recovery, có archive nếu cần.
- [ ] Có alert per-partition lag, checkpoint age và rebalance.
- [ ] Có giám sát Blob permission/network failures.
- [ ] Có metrics cho downstream database latency/throughput.
- [ ] Scaling không vượt quá số partitions một cách thiếu kiểm soát.
- [ ] Có kế hoạch graceful shutdown cho Functions/AKS/VM workers.
- [ ] Có runbook replay không chạm nhầm tiến độ production.
- [ ] Có chi phí và ngân sách Event Hubs, Blob, compute, telemetry.
- [ ] Đã thử crash sau DB commit nhưng trước checkpoint.
- [ ] Đã kiểm tra business outcome chứ không chỉ số events đọc.

## 42. Câu hỏi tự kiểm tra

1. Event Hubs partition khác Service Bus queue ở điểm nào?
2. Partition key và Partition ID khác nhau ra sao?
3. Những events có cùng key có chắc cùng một partition trong cấu hình ổn định không?
4. Hai keys khác nhau có thể cùng partition không?
5. Vì sao không có global ordering giữa partitions?
6. Cùng partition key có tự đảm bảo producer business order đúng không?
7. Khi nào chọn orderId thay tenantId làm partition key?
8. Hot partition là gì và phát hiện như thế nào?
9. Vì sao thêm 10 consumers cho 4 partitions thường không tăng song song theo tỷ lệ?
10. Consumer group mang lại loại độc lập nào?
11. Vì sao replicas cùng pipeline phải phối hợp checkpoint/ownership store?
12. Sequence number có thể so sánh giữa partitions không?
13. Checkpoint khác Complete của Service Bus như thế nào?
14. Khi checkpoint trước DB commit, rủi ro gì có thể xảy ra?
15. Khi DB commit trước checkpoint, vì sao cần idempotency?
16. Vì sao không nên checkpoint event 102 nếu event 101 chưa xong?
17. Rebalance xảy ra khi nào và tại sao có thể đọc lại events?
18. EventProcessorClient có bảo đảm exactly-once end-to-end không?
19. Blob checkpoint store có lưu toàn bộ event payload không?
20. Khi mất checkpoint, earliest/latest có tác động gì?
21. Retention giới hạn khả năng replay như thế nào?
22. Capture có thay checkpoint không?
23. Consumer lag nên đo trong phạm vi nào?
24. Vì sao checkpoint lag có thể cao hơn processing lag?
25. Azure Functions Event Hubs trigger có cần tạo EventProcessorClient thủ công trong handler không?
26. Dùng AKS/HPA/KEDA để tăng consumers cần xét giới hạn nào?
27. Cần role nào để đọc Event Hubs và ghi Blob checkpoint?
28. Khi Blob checkpoint 403, nên kiểm tra gì?
29. Event Hubs có dead-letter subqueue tích hợp giống Service Bus không?
30. Bài lab failover cần chứng minh gì ngoài việc Pods chạy trở lại?

## 43. Tổng kết

Trong Azure Event Hubs, **partition key** xác định cách phân phối các sự kiện và khả năng giữ thứ tự theo entity; **checkpoint** lưu tiến độ xử lý đã an toàn mà không xóa dữ liệu khỏi log; **consumer load balancing** phân phối ownership partitions giữa nhiều processors trong một consumer group.

Thiết kế tốt phải hiểu rằng **cùng key có thể cùng partition nhưng không có global ordering**, **checkpoint sau durable commit vẫn có khả năng xử lý lại**, và **thêm consumers không thể vượt qua giới hạn của số partitions hoặc hot partition**. EventProcessorClient kết hợp Azure Blob checkpoint store giúp điều phối ownership và phục hồi sau restart, nhưng không tự đảm bảo exactly-once cho database hay API ngoài.

Khi triển khai production, hãy kết hợp **partition key theo aggregate, eventId/aggregateVersion, checkpoint theo contiguous progress, idempotency, retry/quarantine, per-partition lag monitoring, Microsoft Entra identity/RBAC, networking, retention/archive và Cost Management**. Mục tiêu cuối không phải là số events đọc mỗi giây đơn thuần mà là **xử lý đúng dữ liệu, theo dõi được tiến độ, khôi phục sau sự cố và kiểm soát chi phí**.
