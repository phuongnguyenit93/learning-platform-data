# Tích hợp client Kafka với Event Hubs

> **Chương:** Sự kiện và dữ liệu streaming  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Hoàn thành bài này, bạn có thể:

1. Giải thích vì sao **Azure Event Hubs có endpoint tương thích giao thức Apache Kafka** và phân biệt với việc tự vận hành một Kafka cluster.
2. Ánh xạ **Event Hubs namespace, event hub, partition, consumer group, Kafka topic, producer, consumer và offset** thành một kiến trúc streaming có thể vận hành.
3. Kết nối Kafka client qua **SASL_SSL/PLAIN với connection string**, hiểu lựa chọn xác thực bằng Microsoft Entra ID và tránh lộ credentials.
4. Tạo tài nguyên Event Hubs phù hợp, cấu hình **bootstrap server, topic, group.id**, gửi và đọc sự kiện bằng **Python confluent-kafka**.
5. Phân biệt **at-least-once**, **consumer offset commit**, **ordering theo partition**, khả năng xử lý lặp, retention và replay.
6. Thiết kế partition key, concurrency, backpressure, batching, quota và theo dõi consumer lag.
7. Hiểu các **giới hạn tương thích Kafka API**: quản trị broker, topic creation, log compaction, transactions và tính năng phụ thuộc Kafka cluster.
8. Chẩn đoán authentication/TLS/network, unknown topic, rebalances, offset-out-of-range, throttling và latency; vận dụng bảo mật và tối ưu chi phí.

## 1. Tình huống thực tế: dùng thư viện Kafka nhưng không vận hành Kafka brokers

Một nền tảng thương mại điện tử có ứng dụng Java/Python phát sự kiện mua hàng. Nhóm phát triển đã dùng các thư viện Kafka để publish và consume sự kiện. Nhóm vận hành muốn giảm công việc quản lý:

- Broker instances, phân bố partitions và ổ lưu trữ.
- Cài đặt, cập nhật phiên bản và theo dõi Kafka controllers/brokers.
- Tự xây monitoring, failover và bảo đảm khả dụng hạ tầng Kafka.
- Quản lý kết nối giữa nhiều consumer teams.

**Azure Event Hubs** là dịch vụ streaming ingestion được Azure quản lý. Một **Event Hubs namespace** thuộc tier hỗ trợ có **Kafka-compatible endpoint**, cho phép nhiều Kafka clients kết nối theo giao thức Kafka mà **không cần tạo Kafka cluster** riêng.

Ví dụ:

~~~mermaid
flowchart LR
    P1["Order service\nKafka producer"]
    P2["Checkout gateway\nKafka producer"]
    EP["Event Hubs namespace\nKafka endpoint :9093"]
    EH["Event Hub: orders-events\nKafka topic"]
    PT["Partitions: 0,1,2,3"]
    C1["Analytics\nConsumer group A"]
    C2["Fraud detection\nConsumer group B"]
    DB["Databases / Data Lake"]
    P1 -->|"SASL_SSL"| EP
    P2 -->|"SASL_SSL"| EP
    EP --> EH --> PT
    PT --> C1 --> DB
    PT --> C2 --> DB
~~~

Điểm mấu chốt: **Event Hubs là dịch vụ Event Hubs**, không phải một bộ Kafka brokers ẩn mà bạn toàn quyền điều khiển. Giao thức Kafka giúp tái sử dụng một phần lớn client code, nhưng **không có nghĩa mọi Kafka API/tính năng quản trị broker đều hoạt động giống Apache Kafka**.

### Một số lựa chọn thay thế cần nhận biết

| Nhu cầu | Giải pháp nên đánh giá |
| --- | --- |
| Ingest sự kiện/telemetry tốc độ cao bằng Kafka producer/consumer | **Azure Event Hubs Kafka endpoint** |
| Gửi lệnh nghiệp vụ cần queue, dead-letter, sessions, message lock | **Azure Service Bus** |
| Phân phối sự kiện Azure/CloudEvents tới handlers, webhook hoặc Functions | **Azure Event Grid** |
| Cần kiểm soát Kafka brokers, log compaction, advanced Kafka internals | **Apache Kafka/managed Kafka service** với hỗ trợ phù hợp |
| Phân tích streaming sau khi ingest | **Stream Analytics, Spark, Fabric hoặc consumer framework** tương thích |
| Cần vận hành consumer từ một ngôn ngữ không có Kafka SDK phù hợp | Xem **Event Hubs native AMQP SDK** và khả năng tích hợp |

**Không đổi một queue xử lý đơn hàng trong Service Bus thành Event Hubs chỉ vì cả hai đều truyền message.** Service Bus và Event Hubs có cách lưu, nhận, settlement và retention khác nhau.

## 2. Ánh xạ khái niệm Kafka sang Event Hubs

### 2.1. Các đối tượng tương ứng

| Apache Kafka | Azure Event Hubs | Diễn giải |
| --- | --- | --- |
| Kafka cluster/brokers | **Event Hubs namespace và endpoint do Azure quản lý** | Không truy cập hoặc cấu hình brokers như Kafka tự quản lý |
| Kafka topic | **Event Hub** | Topic name trong Kafka client là tên event hub đã tạo |
| Partition | **Event Hub partition** | Đơn vị phân chia log có thứ tự và tiêu thụ song song |
| Kafka producer | **Kafka-compatible producer client** | Gửi records tới event hub qua cổng Kafka |
| Kafka consumer | **Kafka-compatible consumer client** | Poll records từ các partitions |
| Kafka consumer group | **Nhóm đọc/consumer group theo khả năng tương thích** | Dùng `group.id` để phối hợp consumers và offset; kiểm tra group mapping/authorization của cấu hình Event Hubs |
| Kafka record key | **Partition routing key theo giao thức client** | Cùng key có thể được route nhất quán tới cùng partition trong điều kiện cấu hình ổn định |
| Kafka offset | **Vị trí record trong partition** | Dùng để checkpoint/replay; không phải MessageId nghiệp vụ |
| Kafka bootstrap server | **Namespace Kafka endpoint** | Có dạng `<namespace>.servicebus.windows.net:9093` |
| Kafka broker administration | **Azure portal/CLI/ARM/Bicep/Terraform** | Tạo event hub, partitions, retention, throughput và network trên Azure |

Một namespace chứa nhiều Event Hubs, mỗi Event Hub đại diện cho một dòng sự kiện riêng. Ví dụ:

~~~text
Event Hubs namespace: ehns-shop-dev
  Kafka endpoint: ehns-shop-dev.servicebus.windows.net:9093

  Event Hub: orders-events
    partitions: 0, 1, 2, 3

  Event Hub: payment-events
    partitions: 0, 1

  Event Hub: telemetry
    partitions: 0, 1, 2, 3, ...
~~~

Các số partition chỉ để minh họa. **Không nên để Kafka client tự tạo topic**; Event Hub được tạo và cấu hình trước qua **Azure management plane**.

### 2.2. Endpoint Kafka là namespace-level

Kafka client không kết nối vào địa chỉ dạng `kafka-1.example:9092` hay chuỗi bootstrap của các brokers do bạn vận hành. Thay vào đó:

~~~text
bootstrap.servers = ehns-shop-dev.servicebus.windows.net:9093
topic             = orders-events
security.protocol = SASL_SSL
sasl.mechanisms   = PLAIN
~~~

Port **9093** ở endpoint Kafka sử dụng TLS; **không bỏ TLS** để “test nhanh” khi gặp lỗi. Một số hạn chế kết nối từ firewall/proxy/VNet yêu cầu kiểm tra cổng này. Event Hubs native AMQP endpoint dùng mô hình giao thức/cổng khác; không thay Kafka bootstrap bằng một AMQP connection URI.

### 2.3. Kafka group.id và Event Hubs consumer groups

Kafka client thường khai báo:

~~~properties
group.id=orders-analytics-lab
~~~

Các client cùng `group.id` phối hợp việc chia partitions của topic trong cùng nhóm, theo khả năng hỗ trợ. Nhóm fraud khác ID với analytics để **đọc độc lập toàn bộ các sự kiện**. Event Hubs cũng có khái niệm **consumer group** ở phía dịch vụ; cần thiết lập/mapping group name/permission đúng với phiên bản giao thức, SDK và chính sách namespace.

Để lab dễ kiểm soát, ta sẽ **tạo consumer group trong Azure** với tên phù hợp `group.id`, sau đó xác minh hành vi của Kafka client thực tế. Không giả định tên nhóm Kafka bất kỳ sẽ tự có đầy đủ quyền/data-plane hoặc quy tắc tự tạo resource trên mọi môi trường.

### 2.4. Partition không phải consumer group

Ví dụ `orders-events` có bốn partitions và nhóm `analytics-lab` có:

- **Một consumer instance:** consumer có thể được gán cả bốn partitions.
- **Hai consumer instances:** hai consumers chia partitions, mỗi partition được một member trong nhóm xử lý theo group assignment.
- **Sáu consumer instances:** không thể có hơn bốn members cùng xử lý bốn partitions đó song song theo nguyên tắc mỗi partition chỉ gán một member trong group ở một thời điểm; có thể có idle members.

**Thêm consumer replicas không tạo partitions mới** và cũng không tăng throughput vô hạn. Nhóm `fraud-lab` riêng có thể đọc cùng các partitions **độc lập** với `analytics-lab`.

### 2.5. Offset không đồng nghĩa xóa record

Kafka consumer đọc tới offset 105 và commit thành công không làm các records offset 0–105 biến mất khỏi Event Hub. Sự kiện được giữ theo **retention policy**; consumer lưu **vị trí đã xử lý** để lần sau tiếp tục.

Khác với Service Bus PeekLock/Complete: Event Hubs không xóa event khỏi stream chỉ vì một consumer đã xử lý. Hãy chọn Event Hubs khi cần **replay trong cửa sổ retention** và nhiều nhóm đọc độc lập.

## 3. Record, key, partition, offset và thứ tự sự kiện

### 3.1. Hình dung một partition log

~~~text
Topic / Event Hub: orders-events

Partition 0:
  offset 0: OrderCreated(orderId=ORD-101)
  offset 1: OrderPaid(orderId=ORD-101)
  offset 2: OrderShipped(orderId=ORD-101)

Partition 1:
  offset 0: OrderCreated(orderId=ORD-202)
  offset 1: OrderCancelled(orderId=ORD-202)
~~~

Trong một partition, records có thứ tự ghi/đọc theo offset. **Không có tổng thứ tự tuyệt đối giữa partition 0 và partition 1.**

### 3.2. Thiết kế message contract

Ví dụ value là JSON:

~~~json
{
  "eventId": "evt-ORD-101-created",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "ORD-101",
  "occurredAt": "2026-11-20T09:00:00Z",
  "amount": 2500000,
  "currency": "VND"
}
~~~

Kafka record nên có:

~~~text
topic:   orders-events
key:     ORD-101
value:   JSON UTF-8 bên trên
headers: eventType=OrderCreated, schemaVersion=1
timestamp: producer/broker timestamp theo cấu hình và khả năng hỗ trợ
~~~

**Kafka record key không phải encryption key**. Nó là khóa dữ liệu, thường dùng cho partitioning và có thể ảnh hưởng thứ tự xử lý. Đừng đặt secrets hoặc thông tin cá nhân nhạy cảm vào key hoặc headers.

### 3.3. Chọn key theo entity cần giữ thứ tự

Với dòng sự kiện thay đổi trạng thái đơn hàng, dùng `orderId` làm key là một lựa chọn hợp lý. Khi partition count và partitioner/serialization ổn định, các records cùng key thường đến cùng partition, giúp giữ thứ tự trong partition.

Tuy nhiên:

- Nếu thay **partition count**, thuật toán partitioning hoặc producer implementation, routing của cùng key có thể thay đổi; cần đánh giá khả năng giữ thứ tự xuyên giai đoạn thay đổi.
- Nếu publisher gửi nhiều luồng đồng thời, retry/out-of-order hoặc application sequencing có thể làm thứ tự nghiệp vụ khác kỳ vọng.
- Một key quá phổ biến, ví dụ `region=VN` cho 95% traffic, tạo **hot partition**.
- Consumer side effects sang database phải tự bảo đảm thứ tự cần thiết; broker không biến toàn hệ thống thành transaction serial.

### 3.4. Không phụ thuộc offset như ID nghiệp vụ

Offset chỉ có ý nghĩa trong **một partition** của topic tại một thời điểm; offset 10 của partition 0 không bằng offset 10 của partition 1. Để deduplicate và truy vết, dùng `eventId`/`orderId` trong payload, cùng topic/partition/offset cho mục đích kỹ thuật.

Một record có thể được nhận nhiều lần nếu consumer xử lý xong nhưng commit chưa thành công. Do đó consumer phải **idempotent**.

## 4. Các yêu cầu để dùng Kafka endpoint của Event Hubs

### 4.1. Kiểm tra tier và hỗ trợ

Khả năng Kafka endpoint có trên **Event Hubs tiers hỗ trợ Kafka, chẳng hạn Standard, Premium và Dedicated**. Không xây lab trên một namespace **Basic** rồi kỳ vọng Kafka client hoạt động đầy đủ. Chính sách tier, region, limits và tính năng có thể thay đổi; kiểm tra cấu hình thực của namespace khi triển khai.

### 4.2. Những tiền điều kiện của lab

- Azure subscription có quyền sử dụng và tạo tài nguyên cần thiết.
- Namespace Event Hubs tier hỗ trợ Kafka, cùng Event Hub `orders-events`.
- Một consumer group dành riêng cho lab, ví dụ `orders-analytics-lab`.
- Kafka client có hỗ trợ **TLS + SASL PLAIN** (ví dụ Python `confluent-kafka`).
- SAS policy/connection string cấp **Send** cho producer và **Listen** cho consumer, hoặc cơ chế Entra OAuth phù hợp.
- Máy chạy client có thể kết nối TCP **9093** tới namespace endpoint.
- Azure Monitor và log ứng dụng để xác minh throughput, errors và lag.
- Không dùng namespace production hoặc data thật để chạy test nếu chưa được phê duyệt.

### 4.3. Đường kết nối

~~~mermaid
flowchart LR
    APP["Kafka client\nlaptop/VM/AKS"]
    DNS["DNS namespace FQDN"]
    TLS["TLS + SASL authentication\nport 9093"]
    NS["Event Hubs namespace\nKafka front end"]
    EH["Event Hub / Kafka topic\norders-events"]
    APP --> DNS --> TLS --> NS --> EH
~~~

TLS kiểm tra chứng chỉ namespace; SASL xác thực người dùng/credential theo cơ chế đang dùng. Network routing và authorization **là hai bước riêng biệt**: kết nối TCP/TLS thông không bảo đảm client có quyền Publish/Consume.

### 4.4. Lưu ý chi phí

Tạo namespace/event hub có thể phát sinh phí theo tier, throughput/capacity, retained data, capture, network và observability. **Không cung cấp số giá cố định** vì giá, quota và khả năng thay đổi theo region/subscription. Dùng Azure Pricing Calculator và Cost Management trước khi tạo lab.

## 5. Tạo Event Hubs resources qua portal hoặc Azure CLI

### 5.1. Quy trình portal

1. Trong Azure portal, xác nhận đúng **subscription** và **resource group**.
2. Tạo **Event Hubs namespace** ở region được phép, chọn tier hỗ trợ Kafka.
3. Tạo **Event Hub** tên `orders-events` với partition count đã được phê duyệt, ví dụ 4 trong lab.
4. Thiết lập retention theo nhu cầu và giới hạn tier, không mặc định sự kiện tồn tại vô hạn.
5. Tạo **consumer group** tên `orders-analytics-lab` theo mô hình được dùng.
6. Thiết lập SAS policies có quyền tối thiểu hoặc Entra ID/RBAC theo phương án client hỗ trợ.
7. Kiểm tra namespace status, networking/firewall/private endpoint và khả năng TCP 9093.
8. Bật metrics/alerts/diagnostic settings phù hợp trước khi test tải.

### 5.2. Tạo bằng CLI trong lab được phép

Các lệnh sau là **thao tác ghi tạo tài nguyên và có thể phát sinh chi phí**. Chỉ chạy trên subscription/resource group lab đã được phê duyệt.

~~~bash
az login

az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Thay giá trị bằng subscription thực của lab.
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-eventhubs-kafka-lab"
LOCATION="southeastasia"
EHNS="ehns-kafka-unique-demo"
EVENTHUB="orders-events"
GROUP="orders-analytics-lab"

az group create \
  --name "$RG" \
  --location "$LOCATION"

# Phải thay EHNS bằng một namespace name hợp lệ, duy nhất.
az eventhubs namespace create \
  --resource-group "$RG" \
  --name "$EHNS" \
  --location "$LOCATION" \
  --sku Standard

az eventhubs eventhub create \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --name "$EVENTHUB" \
  --partition-count 4

az eventhubs eventhub consumer-group create \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --eventhub-name "$EVENTHUB" \
  --name "$GROUP"
~~~

**Cần xác minh khi thực thi:** CLI version và Azure policy có thể yêu cầu thêm tham số hoặc không cho tạo theo region/tier. Trước khi thay đổi, dùng `az eventhubs namespace create --help` và `az eventhubs eventhub create --help` để xác nhận tùy chọn hiện hành. Không tự sửa quota hoặc chọn tier đắt hơn để vượt lỗi không rõ nguyên nhân.

### 5.3. Readback tài nguyên

~~~bash
az eventhubs namespace show \
  --resource-group "$RG" \
  --name "$EHNS" \
  --query "{name:name, location:location, sku:sku, status:status}" \
  --output json

az eventhubs eventhub show \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --name "$EVENTHUB" \
  --output json

az eventhubs eventhub consumer-group list \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --eventhub-name "$EVENTHUB" \
  --output table
~~~

Lệnh quản trị Azure nói chuyện với **management plane**, không tạo/tự động chứng minh Kafka producer có thể kết nối data plane qua TCP 9093.

### 5.4. Không dùng Kafka AdminClient để tự tạo Event Hub

Kafka clients thường có khả năng tự tạo topic khi Kafka broker cho phép. Với Event Hubs, **Event Hub là tài nguyên Azure** nên phải được provision qua portal/CLI/ARM/Bicep/Terraform hoặc API quản trị hỗ trợ. Không dựa vào `auto.create.topics.enable=true` của Kafka broker.

Nếu producer báo `UnknownTopicOrPartition`, trước tiên kiểm tra **tên Event Hub thật** và namespace, không vội tạo topic bằng Kafka API không được hỗ trợ.


## 6. Xác thực Kafka client: SASL_SSL, SAS và Microsoft Entra ID

### 6.1. SASL_SSL/PLAIN với Event Hubs connection string

Một cách cấu hình ban đầu phổ biến cho Kafka client:

~~~properties
bootstrap.servers=<namespace>.servicebus.windows.net:9093
security.protocol=SASL_SSL
sasl.mechanisms=PLAIN
sasl.username=$ConnectionString
sasl.password=<EVENT_HUBS_NAMESPACE_CONNECTION_STRING>
~~~

Đây là **cấu hình minh họa**, không phải tệp có thể dùng nguyên văn. Thay hostname và connection string bằng giá trị thật, bảo vệ secrets và kiểm tra quyền truy cập.

- Giá trị `sasl.username` phải là literal `$ConnectionString`, không phải username Entra.
- `sasl.password` phải là **toàn bộ connection string** Event Hubs được Kafka endpoint hỗ trợ, không phải chỉ `SharedAccessKey`.
- Connection string thường chứa `Endpoint=sb://<namespace>.servicebus.windows.net/;SharedAccessKeyName=...;SharedAccessKey=...`.
- Dùng **namespace-level connection string phù hợp Kafka endpoint** theo hướng dẫn giao thức/tier; đừng sao chép mù quáng chuỗi có `EntityPath` theo cách native Event Hubs SDK.
- `SASL_SSL` dùng kênh TLS. `PLAIN` là cơ chế SASL gửi credential qua **kết nối đã mã hóa**, không phải tắt TLS.
- Đừng thử `SASL_PLAINTEXT` hoặc bỏ xác minh TLS để khắc phục lỗi mạng/xác thực.

### 6.2. Quyền tối thiểu cho producer và consumer

~~~text
orders-producer:
  SAS policy / principal có quyền Send

analytics-consumer:
  SAS policy / principal có quyền Listen
~~~

Không phát `RootManageSharedAccessKey` cho mọi workload. Publisher, consumer và người quản lý Event Hub là các **vai trò khác nhau**. Khi dùng SAS:

1. Tách credential Send và Listen theo khả năng policy/scope được Kafka endpoint hỗ trợ.
2. Giữ secret trong Key Vault, secret manager hoặc CI/CD secret injection.
3. Không đặt connection string trong source code, Docker image hoặc log.
4. Có kế hoạch rotation và kiểm thử client reconnect.
5. Kiểm tra chính sách entity/namespace-level vì không phải mọi loại connection string có hành vi giống nhau giữa Kafka và native AMQP SDK.

### 6.3. Microsoft Entra ID / OAuth

Event Hubs hỗ trợ xác thực bằng **Microsoft Entra ID** trên những mô hình Kafka client/OAuth phù hợp. Khi dùng managed identity hoặc workload identity trên Azure, đây là phương án đáng đánh giá để tránh duy trì SAS key lâu dài.

Quy trình thiết kế:

1. Chọn identity/principal được phép.
2. Cấp data-plane role đúng, ví dụ **Azure Event Hubs Data Sender** hoặc **Azure Event Hubs Data Receiver** ở scope tối thiểu.
3. Chọn Kafka SDK hỗ trợ OAuth/SASL tương ứng, cấu hình acquisition/refresh token theo hướng dẫn của SDK và Event Hubs.
4. Xác minh token audience/scope, thời hạn và quy trình refresh trước expiry.
5. Không ghi access token vào logs.

**Không thể giữ nguyên `PLAIN` rồi thay `sasl.password` bằng một OAuth access token tùy ý.** Kafka Java, librdkafka/confluent-kafka và các framework có OAuth callback khác nhau. Bài lab sử dụng SASL_SSL/PLAIN để làm rõ giao thức; production có thể chọn Entra/OAuth nếu client và môi trường hỗ trợ.

### 6.4. Authentication khác network

~~~text
DNS namespace FQDN
  → TCP 9093
    → TLS trust + SNI
      → SASL authentication
        → Send/Listen authorization
          → Event Hub topic
            → Consumer group / offsets
~~~

- DNS phân giải đúng không chứng minh TCP 9093 thông.
- TLS handshake đúng không chứng minh SAS credential hợp lệ.
- Có credential hợp lệ không bảo đảm có quyền Send/Listen.
- Có quyền đọc không bảo đảm consumer đã cấu hình đúng group/offset.

## 7. Network, firewall, private endpoint và TLS

### 7.1. Public Kafka endpoint

Nếu namespace cho phép public network access theo chính sách:

~~~text
<namespace>.servicebus.windows.net:9093
~~~

Client phải được phép kết nối tới endpoint/cổng **9093**. Không mở tất cả Internet chỉ để xử lý một lần timeout. Lưu ý Kafka dùng TCP/TLS với metadata/heartbeat, không nhất thiết hoạt động qua HTTP proxy thông thường.

### 7.2. Kiểm tra DNS, TCP và TLS

Linux/macOS nếu đã có các công cụ:

~~~bash
nslookup ehns-kafka-unique-demo.servicebus.windows.net

nc -vz ehns-kafka-unique-demo.servicebus.windows.net 9093

openssl s_client \
  -connect ehns-kafka-unique-demo.servicebus.windows.net:9093 \
  -servername ehns-kafka-unique-demo.servicebus.windows.net \
  -brief
~~~

Windows PowerShell:

~~~powershell
Resolve-DnsName ehns-kafka-unique-demo.servicebus.windows.net

Test-NetConnection ehns-kafka-unique-demo.servicebus.windows.net -Port 9093
~~~

Đây là **kiểm tra chỉ đọc** của DNS/network/TLS, **chưa chứng minh SAS authorization**. Nếu kiểm tra TLS thành công nhưng client báo authentication failed, quay sang quyền và connection string thay vì tắt TLS.

### 7.3. Private endpoint và DNS

Nếu namespace dùng Private Endpoint:

- Namespace/tier phải hỗ trợ lựa chọn private connectivity.
- Client cần route tới private IP qua VNet, VPN hoặc ExpressRoute theo thiết kế.
- Private DNS Zone/forwarding phải phân giải **namespace hostname** tới private endpoint theo cơ chế Azure hỗ trợ.
- Firewall/NSG/UDR/proxy không chặn port 9093 hoặc đường trả lời.
- TLS SNI/certificate tiếp tục dùng FQDN hợp lệ, **không thay bằng private IP** rồi bỏ validation.
- Managed identity/RBAC hoặc SAS authorization vẫn là yêu cầu riêng, không được thay thế bởi private networking.

### 7.4. Proxy, idle timeouts và NAT

Kafka clients có thể duy trì TCP connections dài, heartbeats và metadata fetches. HTTP proxy truyền thống chưa chắc hỗ trợ đúng Kafka TCP/TLS. Với AKS/container workloads cần kiểm tra egress NAT/SNAT, idle timeout, DNS, proxy TCP passthrough và network quotas. Mất kết nối sau một khoảng idle có thể là vấn đề mạng, không phải lỗi offset.

### 7.5. Không hard-code địa chỉ IP frontend

TLS xác thực hostname namespace. Không dựa vào IP hiện tại của Azure front end hoặc tắt certificate validation vì IP có thể thay đổi và làm giảm bảo mật. Hãy sửa DNS/routing đúng theo mô hình Event Hubs.


## 8. Ví dụ Python với confluent-kafka

### 8.1. Tệp và dependency

Tạo thư mục riêng ở máy lab, không thêm tệp khác vào module:

~~~text
eventhubs-kafka-lab/
  requirements.txt
  kafka_settings.py
  producer.py
  consumer.py
~~~

`requirements.txt`:

~~~text
confluent-kafka
~~~

~~~bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
~~~

Trên PowerShell dùng lệnh kích hoạt virtual environment riêng. Khi đưa vào production, pin versions trong lockfile và kiểm tra compatibility của librdkafka.

### 8.2. Configuration và secrets

Cấp hai environment variables từ secret manager hoặc cơ chế tương đương:

~~~text
EH_KAFKA_BOOTSTRAP=ehns-kafka-unique-demo.servicebus.windows.net:9093
EH_KAFKA_CONNECTION_STRING=<INJECT_SECRET_AT_RUNTIME>
~~~

**Không commit, echo hoặc ghi vào log** connection string. Với production, cấp riêng quyền Send và Listen theo workload; lab có thể dùng một policy đủ quyền khi được quản trị cho phép.

`kafka_settings.py`:

~~~python
import os


def kafka_base_config() -> dict:
    bootstrap = os.environ["EH_KAFKA_BOOTSTRAP"]
    connection_string = os.environ["EH_KAFKA_CONNECTION_STRING"]

    return {
        "bootstrap.servers": bootstrap,
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "PLAIN",
        "sasl.username": "$ConnectionString",
        "sasl.password": connection_string,
        "client.id": "orders-kafka-lab",
    }
~~~

Đây là **Event Hubs namespace connection string**, không phải Azure Storage string hay URL HTTP. Nếu dùng Entra/OAuth thì thay cả cơ chế authentication tương ứng, không dùng cấu hình `PLAIN` này.

### 8.3. Producer: gửi record có key và kiểm tra delivery

`producer.py`:

~~~python
import json
import uuid

from confluent_kafka import Producer
from kafka_settings import kafka_base_config


TOPIC = "orders-events"

config = kafka_base_config()
config.update({
    "client.id": "orders-producer-lab",
    "acks": "all",
    "compression.type": "none",
})

producer = Producer(config)
delivered = 0
failed = 0


def on_delivery(error, message):
    global delivered, failed

    if error is not None:
        failed += 1
        print("Delivery failed:", str(error))
    else:
        delivered += 1
        print(
            "Delivered:",
            message.topic(),
            "partition=", message.partition(),
            "offset=", message.offset(),
        )


for n in range(6):
    order_id = f"ORD-{1000 + n}"
    payload = {
        "eventId": str(uuid.uuid4()),
        "eventType": "OrderCreated",
        "schemaVersion": 1,
        "orderId": order_id,
        "amount": (n + 1) * 1000000,
    }

    producer.poll(0)

    producer.produce(
        topic=TOPIC,
        key=order_id.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
        headers=[
            ("eventType", b"OrderCreated"),
            ("schemaVersion", b"1"),
        ],
        on_delivery=on_delivery,
    )

pending = producer.flush(timeout=30)
print("delivered=", delivered, "failed=", failed, "pending=", pending)

if failed or pending:
    raise RuntimeError("Batch chưa được xác nhận gửi thành công hoàn toàn")
~~~

Ý nghĩa:

- `produce()` chủ yếu đặt record vào local buffer, **không đồng nghĩa broker đã lưu ngay**.
- `on_delivery` báo acknowledgment hoặc lỗi; `flush` đợi pending messages.
- `key=order_id` giúp records cùng đơn đến cùng partition khi partitioner và số partition ổn định.
- `acks=all` không bảo đảm **exactly-once processing** ở consumer.
- `compression.type=none` làm bài lab ít phụ thuộc Kafka codec support.
- Production cần xử lý local buffer full, retry/backoff, idempotent event IDs, batching, rate limiting và metrics.

Kết quả minh họa:

~~~text
Delivered: orders-events partition= 2 offset= 10
Delivered: orders-events partition= 1 offset= 13
...
delivered= 6 failed= 0 pending= 0
~~~

Partition/offset cụ thể không cố định. Message ID nghiệp vụ nên nằm trong payload; không dùng offset làm business identifier.

### 8.4. Producer errors

| Hiện tượng | Khả năng | Cách xử lý |
| --- | --- | --- |
| Client buffer đầy | Produce nhanh hơn network có thể gửi | Backpressure, `poll`, điều chỉnh batch |
| Authentication failed | SAS username/password hoặc policy sai | Kiểm tra secret và quyền |
| Authorization failed | Thiếu Send hoặc scope không đúng | RBAC/SAS policy |
| Unknown topic | Event Hub chưa được tạo, tên sai | Kiểm tra Azure resource |
| Request timeout | Network/throttling hoặc server chậm | Monitoring, retry có giới hạn |
| Record too large | Payload vượt limit tier/API | Giảm size, lưu Blob và gửi reference |
| Unsupported API/codec | Client yêu cầu tính năng không hỗ trợ | Thay cấu hình hoặc kiến trúc |

**Không in toàn bộ producer configuration khi debug** vì `sasl.password` có thể chứa khóa.

## 9. Consumer: poll, xử lý rồi mới commit offset

### 9.1. Consumer group dành riêng lab

Nếu chưa có group:

~~~bash
az eventhubs eventhub consumer-group create \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --eventhub-name "$EVENTHUB" \
  --name "orders-analytics-lab"
~~~

Đặt `group.id=orders-analytics-lab` trong Kafka client. Fraud consumer nên dùng ID khác để đọc độc lập. Xác minh mapping group ở SDK/namespace thực tế và không dùng production group để test vì commit sẽ thay vị trí đọc được chia sẻ.

### 9.2. Consumer Python commit thủ công

`consumer.py`:

~~~python
import json
import time

from confluent_kafka import Consumer, KafkaException
from kafka_settings import kafka_base_config


TOPIC = "orders-events"
MAX_MESSAGES = 6
DEADLINE_SECONDS = 90

config = kafka_base_config()
config.update({
    "client.id": "orders-analytics-consumer-lab",
    "group.id": "orders-analytics-lab",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
})

consumer = Consumer(config)
count = 0
deadline = time.monotonic() + DEADLINE_SECONDS

try:
    consumer.subscribe([TOPIC])

    while count < MAX_MESSAGES and time.monotonic() < deadline:
        message = consumer.poll(timeout=5.0)

        if message is None:
            print("Chưa có sự kiện trong 5 giây")
            continue

        if message.error() is not None:
            raise KafkaException(message.error())

        payload = json.loads(message.value().decode("utf-8"))
        event_id = payload["eventId"]
        order_id = payload["orderId"]

        # Chỉ in trong demo; production cần durable write/idempotency.
        print(
            "Processed", event_id, order_id,
            "partition=", message.partition(),
            "offset=", message.offset(),
        )

        # Chỉ commit sau khi xử lý thành công.
        consumer.commit(message=message, asynchronous=False)
        count += 1

finally:
    consumer.close()

print("Processed count:", count)
~~~

**Điểm quan trọng:**

- `enable.auto.commit=False` tránh client tự commit theo chu kỳ trước khi nghiệp vụ hoàn tất.
- `commit(message=message, asynchronous=False)` commit vị trí sau record đã xử lý thành công.
- Code demo chỉ in, chưa ghi dữ liệu. Production phải ghi state bền vững **trước commit**.
- Nếu parse hoặc xử lý lỗi, exception thoát vòng lặp mà không commit record đang lỗi.
- `consumer.close()` giải phóng session/group membership khi script kết thúc.
- Deadline 90 giây giúp bài lab không chạy vô hạn nếu ít hơn sáu records đến.

### 9.3. Manual commit chưa phải exactly-once

~~~text
Record received
    ↓
Validate + idempotency check
    ↓
Database write succeeds
    ↓
Worker crashes BEFORE offset commit
    ↓
Same record can be received again
~~~

Vì vậy cần idempotency, ví dụ unique constraint trên `eventId` và transaction nghiệp vụ. Kafka offset dùng cho tiến độ đọc, không phải transaction duy nhất với Azure SQL/Cosmos DB.

### 9.4. Không commit nhảy qua record xử lý lỗi

Trong **cùng một partition**:

~~~text
offset 10: xử lý lỗi, không commit
offset 11: xử lý thành công và commit vị trí sau offset 11
~~~

Nếu commit offset cao hơn, lần chạy lại có thể **không đọc lại offset 10**. Không nuốt exception ở record lỗi rồi tiếp tục commit record phía sau trong partition. Với production:

1. Phân loại transient vs malformed events.
2. Retry có giới hạn, có backoff.
3. Quarantine/poison event vào nơi lưu bền vững khi quyết định bỏ qua.
4. Chỉ commit khi công việc hoặc việc xử lý lỗi bền vững đã hoàn tất.
5. Quản lý tiến độ commit theo từng partition khi có concurrency.

### 9.5. `auto.offset.reset=earliest` chỉ tác động lúc nào?

Nó có tác dụng chủ yếu **khi group chưa có committed offset phù hợp** hoặc offset nằm ngoài retention theo semantics client. Nếu group đã commit offset hợp lệ, đổi config thành `earliest` không tự đọc lại từ đầu.

Để replay trong lab, dùng **group mới** hoặc quy trình reset offset được phép; chỉ replay được phần dữ liệu **còn trong retention**. Không reset production group tùy tiện.

### 9.6. Consumer group và partition assignment

~~~text
orders-events (4 partitions)
  group analytics-lab:
    consumer A → partition 0, 1
    consumer B → partition 2, 3

  group fraud-lab:
    consumer C → partition 0, 1, 2, 3
~~~

Sơ đồ minh họa. Members trong **cùng group** phối hợp chia partitions, còn khác groups đọc độc lập. Khi join/leave, **rebalance** có thể đổi assignments và cần xử lý dữ liệu in-flight/offset an toàn.


## 10. Tích hợp Java Kafka client

Nếu ứng dụng Java đã dùng `org.apache.kafka.clients.producer.KafkaProducer` hoặc `KafkaConsumer`, phần lớn logic xử lý records có thể được tái sử dụng. Cần thay **bootstrap, authentication, broker-specific settings** và kiểm tra API features thực sự được Event Hubs hỗ trợ.

### 10.1. Java client.properties

~~~properties
bootstrap.servers=<namespace>.servicebus.windows.net:9093
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="$ConnectionString" password="<FULL_NAMESPACE_CONNECTION_STRING>";
client.id=orders-java-client
~~~

Đây là cấu hình **minh họa** có placeholder secret. Không commit file có connection string thật vào Git, không in JAAS config trong logs. Với Java, tên property thường là `sasl.mechanism` (số ít), trong khi ví dụ `confluent-kafka` dùng `sasl.mechanisms` (số nhiều). **Kiểm tra chính xác tên được SDK sử dụng**.

### 10.2. Ý tưởng producer Java

~~~java
Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap);
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
          StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
          StringSerializer.class.getName());

// Nạp security.protocol, sasl.mechanism, sasl.jaas.config
// từ cấu hình bí mật được quản trị.

try (Producer<String, String> producer = new KafkaProducer<>(props)) {
    ProducerRecord<String, String> record = new ProducerRecord<>(
        "orders-events",
        "ORD-101",
        "{\"eventType\":\"OrderCreated\",\"orderId\":\"ORD-101\"}"
    );
    producer.send(record).get();
    producer.flush();
}
~~~

Đây là **đoạn minh họa**, chưa có imports/main/secret loading hoàn chỉnh. Lệnh `send(record).get()` cho phép quan sát result/exception trong lab, nhưng production thường dùng async batching và delivery callbacks. Không coi `flush` tự thay thế việc kiểm tra lỗi từng record.

### 10.3. Consumer Java

Cấu hình logic:

~~~properties
group.id=orders-analytics-lab
enable.auto.commit=false
auto.offset.reset=earliest
key.deserializer=org.apache.kafka.common.serialization.StringDeserializer
value.deserializer=org.apache.kafka.common.serialization.StringDeserializer
~~~

Consumer gọi `poll`, xử lý durable state rồi `commitSync` hoặc API tương ứng. Khi xử lý song song, không commit vượt record trước chưa được xử lý trên cùng partition. Thêm rebalance listener khi có yêu cầu graceful partition revocation và flush pending work.

### 10.4. Kafka Connect và Kafka Streams

Có những Kafka ecosystem tools dùng được với Event Hubs Kafka endpoint trong cấu hình thích hợp, nhưng **không phải mọi Kafka Connect connector hoặc Kafka Streams topology đều tương thích hoàn toàn**. Trước khi chọn, kiểm tra:

- Connector có phụ thuộc Kafka Admin API để tạo topics tự động không?
- Có yêu cầu **log compaction** hoặc internal changelog/repartition topics không?
- Có phụ thuộc Kafka transactional APIs/idempotent producer modes được hỗ trợ ở Kafka broker gốc không?
- Có yêu cầu Schema Registry protocol tương thích Confluent hay một endpoint riêng không?
- Framework đọc/commit offsets và metrics theo kiểu Kafka group hay một cơ chế khác?
- SDK version, SASL/OAuth, mạng 9093 và throughput thực đã qua integration tests chưa?

**KafkaProducer kết nối thành công không chứng minh mọi Kafka Connect/Streams feature đều được hỗ trợ.** Chạy thử topology với chính framework/version và workload định dùng.

## 11. Consumer lag, retention và replay

### 11.1. Consumer lag là khoảng cách offset

\[
\text{Lag}_{p}\approx\text{LatestOffset}_{p}-\text{CommittedOffset}_{p}
\]

Ví dụ:

~~~text
Partition 0 latest offset:      10000
Committed offset group A:        9600
Lag xấp xỉ:                       400
~~~

Lag là khoảng cách records/offsets, **không tự tương đương 400 giây chậm**. Để đánh giá mức trễ nghiệp vụ cần tính event timestamps, tốc độ nguồn và thời gian xử lý.

### 11.2. Retention là cửa sổ có giới hạn

Event Hubs giữ records theo retention policy và giới hạn của tier. Consumer commit không xóa sự kiện khỏi stream. Nhưng khi một group nghỉ quá lâu, offset cũ có thể không còn trong retention.

Khi đó:

- `earliest` chỉ đưa consumer tới record **sớm nhất còn giữ**, không phục hồi dữ liệu đã hết hạn.
- `latest` có thể bắt đầu từ cuối khi không có offset hợp lệ, bỏ qua dữ liệu trước đó.
- `none` có thể báo lỗi khi không có offset hợp lệ.

Không dùng retention ngắn như **event store vĩnh viễn**. Nếu cần replay dài hạn, thiết kế dữ liệu lưu trữ riêng như Event Hubs Capture/Data Lake/Blob và quy trình replay có kiểm toán.

### 11.3. Nhiều groups và vị trí độc lập

~~~text
orders-events partitions
  group analytics-lab:  p0=950, p1=1200, ...
  group fraud-lab:      p0=900, p1=800, ...
~~~

Group fraud chậm không đồng nghĩa group analytics chậm, vì offsets độc lập. Tuy nhiên cả hai đều dùng capacity của namespace/Event Hub; thêm groups tăng tổng lượt đọc và có thể tăng chi phí xử lý.

### 11.4. Tại sao lag tăng?

- Consumer CPU/RAM thiếu hoặc business logic nặng.
- Database/API downstream bị throttling, lock hoặc rate limit.
- Số partitions nhỏ hơn số consumer replicas.
- Hot partition do key skew.
- Group rebalance liên tục, heartbeat/poll không đáp ứng.
- Message lớn, serialization/schema validation nặng.
- Event Hubs namespace throughput bị throttled.
- Network latency, packet loss, NAT idle timeout/SNAT exhaustion.

Đừng tăng consumers lên vô hạn: với bốn partitions, tám members trong cùng group không thể cùng xử lý tám partitions, vì chỉ có bốn partitions.

### 11.5. Broker metrics không thay client lag

Azure Monitor có namespace/Event Hub metrics như incoming/outgoing messages, errors hoặc throttling theo khả năng và tier. Nhưng metric tổng incoming messages **không tự biết group analytics đã commit tới offset nào**. Đo lag theo consumer group/partition qua Kafka client/framework metrics và kết hợp Azure Monitor.

## 12. Giới hạn tương thích giao thức Kafka

### 12.1. Event Hubs không phải Kafka brokers do bạn quản trị

Event Hubs cung cấp **Kafka-compatible API subset** và service model Azure. Không có quyền truy cập nội bộ Kafka brokers, ZooKeeper/KRaft hoặc broker disk logs.

| Giả định từ Kafka tự quản lý | Điều cần làm với Event Hubs |
| --- | --- |
| Producer tự tạo topic khi chưa tồn tại | Tạo Event Hub trước qua Azure management plane |
| Kafka AdminClient chỉnh broker configs/replicas | Dùng Azure portal/CLI/IaC và tier capabilities |
| `cleanup.policy=compact` luôn có | Không dựa vào Kafka log compaction |
| Kafka transactional producer hoạt động đầy đủ | Kiểm tra compatibility; không giả định exactly-once |
| Kafka Streams internal topics tự được tạo | Kiểm thử và provision entities theo cơ chế Azure |
| Mọi Kafka client API versions đều hoạt động | Kiểm tra supported versions/APIs |
| Tăng partition count không ảnh hưởng ordering | Đánh giá key routing và key skew, tier support |
| Có thể giữ dữ liệu vô hạn | Event Hubs retention là giới hạn hữu hạn |
| Native Kafka ACL/broker users | Azure SAS/Entra RBAC và network controls |
| Kafka broker JMX metrics có sẵn | Azure Monitor + client/app metrics |

### 12.2. Log compaction khác retention

Kafka broker với `cleanup.policy=compact` có thể lưu record mới nhất theo key. **Không thiết kế Event Hubs Kafka endpoint như một compacted changelog Kafka broker** nếu chưa có sản phẩm/tính năng bảo đảm semantics đó. Event Hubs hướng tới event ingestion và retention theo chính sách dịch vụ.

Nếu ứng dụng cần bảng trạng thái mới nhất, dựng materialized view/state store riêng bằng database/cache và cập nhật qua stream processor, với idempotency và replay strategy.

### 12.3. Transactions và exactly-once

Kafka SDK có thể hỗ trợ idempotent producer hoặc transactional ID ở Kafka brokers tự quản lý. **Không mặc định mọi transactional/idempotent Kafka API đều được Event Hubs hỗ trợ** theo đúng semantics ấy. Phải xác minh compatibility matrix cho tier/API/client version.

Kể cả trong hệ thống Kafka hỗ trợ transactions, cập nhật Azure SQL/Cosmos DB và commit offset không tự thành một transaction chung. Consumer vẫn cần idempotent durable processing và/hoặc outbox.

### 12.4. Record size, headers và compression

- Chọn payload phù hợp event/message-size limits của tier.
- Dùng compression/codec khi endpoint hỗ trợ; không giả định mọi codec của librdkafka được chấp nhận.
- Với sự kiện rất lớn, cân nhắc lưu Blob và phát event chứa **reference có authorization**.
- Headers là metadata, không nên chứa credentials/PII.
- Batching, linger và retry giúp throughput nhưng có thể tăng latency hoặc duplicate risks.

### 12.5. Schema Registry không tự tương đương Kafka REST API

Azure Event Hubs có **Azure Schema Registry** để quản lý schema theo khả năng dịch vụ. Nhưng **không được mặc định** nó cung cấp mọi endpoint/compatibility behavior như Confluent Schema Registry REST API. Khi dùng Avro/Protobuf/JSON serializers, kiểm tra SDK/plugin, registration, schema IDs và format/version compatibility.

## 13. Throughput, partitions và backpressure

### 13.1. Chọn partition key để tránh hot partition

Nếu 80% sự kiện có `region=VN` và dùng `region` làm key, phần lớn lưu lượng có thể dồn vào một partition. Khi đó một consumer member gánh quá nhiều, các members khác idle dù có đủ CPU.

Nếu nghiệp vụ yêu cầu sự kiện **cùng đơn hàng** theo thứ tự, chọn `orderId`; distribution thường tốt hơn `region`. Nhưng cần kiểm thử key skew với đơn hàng/khách hàng cực lớn và không thay đổi partitioner/partition count tùy tiện.

### 13.2. Ước lượng raw ingress

Giả sử:

~~~text
Incoming:            10.000 events/giây
Average payload:          2 KiB
Raw payload ingress:   19,53 MiB/s
~~~

Phép tính:

\[
10{,}000\times2/1024\approx19{,}53\text{ MiB/s}
\]

Đây là **raw payload** trước protocol overhead, Kafka headers, compression và network retry. Nếu hai groups đều đọc tất cả records, total egress có thể cao hơn nhiều so với một group. Dùng dữ liệu thực, Azure tier capacity và pricing để sizing.

### 13.3. Batching và latency

`linger.ms` và batch settings có thể tăng throughput do gom records nhưng tăng thời gian chờ. Chọn dựa trên:

- Record size, peak traffic và number of partitions.
- p95/p99 publish-to-consume latency mục tiêu.
- Broker/namespace throttling, producer buffer capacity.
- Codec/version được hỗ trợ.
- Retry/backoff, message size và fault tolerance.

Không tối ưu events/s đơn lẻ rồi phá vỡ latency SLO.

### 13.4. Consumer backpressure

Khi consumer đọc nhanh hơn database xử lý, có nguy cơ memory pressure và deadline/rebalance errors. Có thể:

1. Giới hạn concurrency và inflight database operations.
2. Dùng `pause()/resume()` partition consumption theo API client khi phù hợp.
3. Batch database writes với transaction semantics an toàn.
4. Retry transient errors bằng exponential backoff + jitter.
5. Quarantine poison events trước khi commit skip.
6. Scale consumers theo partitions, node/app resources và downstream quotas.

### 13.5. Tier/capacity

Standard và Premium/Dedicated có mô hình throughput/capacity khác nhau. Khi thấy throttling, kiểm tra Azure Monitor namespace metrics, tier, ingress/egress, số partitions/groups và quota trước khi tăng timeout client.

### 13.6. Thay partition count là thay đổi kiến trúc

Số partitions ảnh hưởng concurrency, ordering theo key, hotspot và khả năng scale. Không mặc định tăng/giảm được trên mọi tier. Nếu tier hỗ trợ thay đổi, cần kiểm tra sự thay đổi partition routing và cách giữ thứ tự business events trong giai đoạn cutover.

## 14. Bảo mật và cấu hình production

### 14.1. Tách publisher, consumer và administrator

| Principal | Quyền nên được cấp | Không nên mặc định có |
| --- | --- | --- |
| Producer | Azure Event Hubs Data Sender/SAS Send ở scope phù hợp | Listen, Manage, Owner |
| Consumer analytics | Azure Event Hubs Data Receiver/SAS Listen | Send/Manage |
| CI/CD tạo namespace/Event Hub | Azure control-plane role phù hợp | Quyền dữ liệu nghiệp vụ không cần |
| SRE/Monitoring | Read metrics/logs và quyền xử lý sự cố | Full SAS keys theo mặc định |
| Network administrator | Private Endpoint/firewall/DNS | Truy cập message contents nếu không cần |

### 14.2. Secrets, TLS và network

- Dùng Key Vault/secret injection; ưu tiên identity-based auth khi Kafka client/SDK hỗ trợ.
- Không ghi `sasl.password`, JAAS config hay token vào logs/ticket.
- Bắt buộc mã hóa TLS và xác minh certificate.
- Giới hạn public access hoặc cấu hình private endpoint theo threat model.
- Kiểm tra DNS private resolution từ AKS, VMs và on-premises.
- Tách Dev/Staging/Prod namespaces khi cần isolation.
- Rotation keys phải có kế hoạch rollback và test reconnect.

### 14.3. Authorization không phải partitioning

Một record có key `tenant-A` không được coi là đã phân quyền tenant. Kafka partition key chỉ chọn luồng lưu trữ/ordering, **không phải access control list**. Khi nhiều tenants có yêu cầu dữ liệu riêng tư, kiểm soát principals, namespaces/event hubs, RBAC, encryption và producer validation; không dùng record key để ngăn consumer đọc dữ liệu tenant khác.

### 14.4. Không coi Kafka client headers là trusted identity

Header `tenantId` hoặc `eventType` có thể do publisher tự điền. Consumer phải validate event contract và xác thực nguồn ở broker/identity layer. Không cho client Internet gửi tùy ý key/headers rồi dùng chúng làm cơ sở cấp quyền hoặc thực thi thay đổi tài chính.


## 15. Giám sát: Azure Monitor kết hợp Kafka client metrics

### 15.1. Một dashboard cần hai góc nhìn

**Azure Event Hubs metrics** cho biết dịch vụ đang nhận/gửi và có bị throttling/lỗi không. **Kafka client metrics** cho biết từng producer/consumer đang thực sự kết nối, send/poll/commit ra sao và group lag ở mức nào.

| Lớp | Tín hiệu quan trọng | Câu hỏi |
| --- | --- | --- |
| Producer | Delivery success/error, retry, queue depth, latency | Broker có xác nhận đủ events chưa? |
| Network/TLS | Connection failures, reconnects, DNS/TLS errors | Client có kết nối ổn định? |
| Event Hubs namespace | Incoming/outgoing messages, requests, errors, throttling | Tier/capacity có đủ? |
| Event Hub/partitions | Partition distribution, end offset, event volume | Có partition nào quá nóng? |
| Consumer group | Offset committed, lag theo partition, rebalance count | Group có theo kịp producer? |
| Consumer business logic | Processed/error count, durable writes, retry/quarantine | Event được xử lý hay chỉ đọc? |
| Downstream | SQL/Cosmos DB latency, throttling, pool usage | Điểm nghẽn ở đâu? |
| Cost | Tier/capacity, data movement, logging, retained data | Giải pháp có trong ngân sách? |

Metric names/dimensions khác nhau theo tier và chế độ dịch vụ. **Đọc metric definitions thực tế trước khi viết dashboard** thay vì sao chép một biểu đồ từ môi trường khác.

### 15.2. Azure CLI đọc metrics được hỗ trợ

~~~bash
NS_ID=$(az eventhubs namespace show \
  --resource-group "$RG" \
  --name "$EHNS" \
  --query id \
  --output tsv)

# Liệt kê những metric definitions hiện khả dụng.
az monitor metrics list-definitions \
  --resource "$NS_ID" \
  --output table

# Xem cấu hình namespace, không sửa tài nguyên.
az eventhubs namespace show \
  --resource-group "$RG" \
  --name "$EHNS" \
  --output json
~~~

Đây là lệnh **chỉ đọc**. Khi chọn metric cụ thể, dùng đúng tên/tần suất/đơn vị/dimensions từ output của namespace. Không lấy số incoming/outgoing toàn namespace làm bằng chứng một consumer group đã xử lý xong.

### 15.3. Logging có correlation ID

Ví dụ log producer:

~~~json
{
  "service": "orders-producer",
  "topic": "orders-events",
  "eventId": "evt-ORD-101-created",
  "orderId": "ORD-101",
  "result": "delivered",
  "partition": 2,
  "offset": 341
}
~~~

Ví dụ log consumer:

~~~json
{
  "service": "analytics-consumer",
  "groupId": "orders-analytics-lab",
  "eventId": "evt-ORD-101-created",
  "topic": "orders-events",
  "partition": 2,
  "offset": 341,
  "result": "processed-and-committed"
}
~~~

Dùng `eventId` để liên kết nghiệp vụ; dùng topic/partition/offset để điều tra kỹ thuật. Không ghi SAS connection string, OAuth token hoặc thông tin nhạy cảm vào logs.

### 15.4. Trace và thời gian xử lý

Với pipeline:

~~~text
HTTP request
  → producer (eventId=E1)
  → Event Hub orders-events
  → consumer group analytics
  → database write
~~~

Nếu cần tracing xuyên async boundary, truyền correlation/trace context ở record headers hoặc payload theo chuẩn như W3C Trace Context, và kiểm tra SDK có tự propagate hay phải bổ sung logic. Không cho rằng Kafka client tự nối trace với mọi Azure SDK.

### 15.5. Cảnh báo đề xuất

- Delivery failures hoặc producer retry rate tăng.
- Namespace throttled requests/availability errors tăng.
- Consumer group lag vượt ngưỡng trong nhiều phút.
- Lag age vượt retention safety margin.
- Rebalances liên tục, consumer heartbeats/timeouts tăng.
- Có partition nóng trong khi partitions khác rất ít traffic.
- Downstream DB throttling, consumer error/quarantine tăng.
- Không còn sự kiện nhận được dù business traffic vẫn tăng.
- Chi phí/capacity utilization vượt forecast.

Alert cần **owner, SLO, severity và runbook**. Lag tăng trong một lần batch peak ngắn có thể được chấp nhận nếu consumer phục hồi và nằm trong retention.

## 16. Playbook chẩn đoán Kafka client không kết nối hoặc không nhận dữ liệu

### 16.1. Bảng lỗi nhanh

| Triệu chứng | Tầng nghi vấn | Kiểm tra đầu tiên |
| --- | --- | --- |
| DNS không phân giải | DNS/public-private zone | Namespace FQDN, VNet DNS, forwarding |
| TCP 9093 timeout | Network/firewall/proxy | NSG, outbound rules, NAT, Public Network Access |
| TLS handshake failed | TLS/SNI/trust | FQDN, certificate CA, clock, proxy interception |
| SASL authentication failed | Username/password | Literal `$ConnectionString`, secret/key rotation |
| Authorization error | SAS policy hoặc Entra RBAC | Send vs Listen, role scope, propagation |
| Unknown topic or partition | Event Hub name hoặc resource | Azure Event Hub tồn tại đúng namespace |
| Producer enqueue thành công nhưng không delivery | Buffer/retry/network/ack | Delivery callbacks và `flush` result |
| Consumer chạy nhưng không có records | Offset/group/retention | Group ID, committed offset, `auto.offset.reset` |
| Consumer nhận lại dữ liệu | Commit chưa thành công, rebalance, crash | Manual commit và idempotency |
| Records sai thứ tự | Nhiều partitions, keys khác hoặc retry | Key selection, partition assignment |
| Consumer lag tăng | Downstream hoặc capacity | SQL/API latency, partitions, throttling |
| Rebalance liên tục | Membership/heartbeat/poll | Poll processing time và group metrics |
| Kafka AdminClient tạo topic thất bại | Không hỗ trợ Kafka topic admin APIs | Tạo Event Hub qua Azure management plane |
| Kafka Streams stateful topology lỗi | Internal topics/compaction/transactions | Feature compatibility của Event Hubs |
| Azure Event Hub có records nhưng Kafka group đọc rỗng | Group offset, retention hoặc auth | Group ID, test mới, client logs |
| Giá tăng dù test ít | Tier/capacity hoặc logging | Cost Management và tài nguyên lab còn tồn tại |

### 16.2. Bước 1 — Xác nhận đích

Ghi lại **subscription/resource group, namespace, event hub name, tier, client library/version** và thời gian UTC. Không ghi connection string vào ticket.

~~~bash
az eventhubs namespace show \
  --resource-group "$RG" \
  --name "$EHNS" \
  --query "{name:name, sku:sku, status:status}" \
  --output json

az eventhubs eventhub show \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --name "$EVENTHUB" \
  --output json
~~~

Nếu Event Hub không tồn tại, không sửa `bootstrap.servers` sang một broker IP ngẫu nhiên: tạo đúng resource qua quy trình quản trị trước.

### 16.3. Bước 2 — DNS, TCP và TLS

~~~bash
nslookup ehns-kafka-unique-demo.servicebus.windows.net

nc -vz ehns-kafka-unique-demo.servicebus.windows.net 9093

openssl s_client \
  -connect ehns-kafka-unique-demo.servicebus.windows.net:9093 \
  -servername ehns-kafka-unique-demo.servicebus.windows.net \
  -brief
~~~

Chỉ khi TCP/TLS thông mới cần chuyển sang SASL/authorization. Nếu Private Endpoint được dùng, kiểm tra địa chỉ DNS trả về và đường routing thực, không disable TLS.

### 16.4. Bước 3 — SASL và quyền

Kiểm tra một cách an toàn:

- `security.protocol=SASL_SSL` và `sasl.mechanisms=PLAIN`.
- `sasl.username` đúng literal `$ConnectionString`.
- `sasl.password` là toàn connection string namespace phù hợp.
- Policy/role được cấp đúng Send/Listen cho workload.
- Connection string chưa bị rotate/revoke.
- Khi dùng OAuth, token flow/refresh/role được cấu hình đúng.

**Không paste connection string vào terminal debug output để nhờ phân tích.** Có thể kiểm tra secret tồn tại, độ dài hoặc metadata mà không lộ giá trị.

### 16.5. Bước 4 — Producer delivery và Event Hub availability

Nếu `produce()` không ném exception nhưng không có data:

1. Đã gọi `poll()/flush()` để nhận callbacks chưa?
2. Delivery callback có lỗi không?
3. Event Hub có đang active?
4. Message vượt kích thước tối đa không?
5. Namespace bị throttled do capacity không?
6. Có codec/API feature không được hỗ trợ không?

Không dùng việc `produce()` return bình thường làm bằng chứng backend đã lưu record.

### 16.6. Bước 5 — Consumer group và offset

Khi consumer `poll()` rỗng:

1. Xác minh đang subscribe đúng **Event Hub/topic name**.
2. Kiểm tra `group.id` đúng consumer group đã được dự kiến.
3. Đọc committed offset và end offset từ client/framework nếu hỗ trợ.
4. Xem `auto.offset.reset` khi group chưa có offset.
5. Kiểm tra dữ liệu còn retention.
6. Xem assignment/rebalance logs và số partitions/members.
7. Đảm bảo không có consumer cùng group đang đọc hết records trước đó.

Với bài lab, **tạo một group mới và gửi eventId mới** là phép thử dễ kiểm soát. Không reset offsets production chỉ để thử.

### 16.7. Bước 6 — Downstream và lag

Nếu consumer nhận nhưng commit chậm:

- Đo thời gian xử lý từng event, SQL/API latency.
- Kiểm tra CPU/RAM/GC của consumer, kết nối network.
- Xem hot partitions và việc phân bổ keys.
- Kiểm tra rebalances và `max.poll.interval.ms` theo client.
- Giảm concurrency khi backend bị throttled.
- Dùng backpressure/retry có giới hạn, không chạy tăng replicas vô hạn.

### 16.8. Bước 7 — Xác minh phục hồi

Sau khi sửa:

- Producer callback xác nhận delivery.
- Event Hub metrics có incoming data theo thời điểm phù hợp.
- Consumer group nhận events mới, process durable state và commit.
- Event IDs đúng, không có duplicate side effects.
- Consumer lag giảm và ở mức chấp nhận.
- Không có connection string/secret bị lộ.
- Chi phí/capacity và alerts nằm trong giới hạn.

## 17. Chi phí và trách nhiệm vận hành

### 17.1. Thành phần chi phí

| Thành phần | Yếu tố cần tính |
| --- | --- |
| Event Hubs namespace | Tier Standard/Premium/Dedicated và capacity |
| Event Hubs traffic | Ingress/egress/requests theo pricing của tier |
| Retention | Giới hạn lưu trữ và phí theo chính sách |
| Event Hubs Capture | Lưu dữ liệu xuống Blob/Data Lake khi bật |
| Client compute | AKS/VM/Container Apps/Functions chạy producer/consumer |
| Network | Egress/VNet/Private Endpoint/NAT theo cấu hình |
| Monitoring | Azure Monitor, Log Analytics ingestion/retention |
| Data processing | Spark, Stream Analytics, Fabric, database hoặc storage |
| Security infrastructure | Key Vault, identity/network services khi phát sinh phí |

**Không dùng một con số USD/tháng cố định** trong bài này. Dùng Pricing Calculator và Cost Management theo region/tier, cùng dữ liệu load test.

### 17.2. Scale groups có thể tăng egress

Một topic có 2 triệu records/ngày, nếu ba consumer groups đều đọc toàn bộ dữ liệu, tổng lượng event consumption tương ứng cao hơn một group. Tăng groups mang lại **fan-out độc lập** nhưng không miễn phí về bandwidth/processing.

### 17.3. Giảm phí mà không phá SLO

- Lưu record nhỏ và metadata đủ dùng.
- Chọn retention theo nhu cầu replay/tuân thủ, không mặc định tối đa.
- Dùng batching trong giới hạn latency cho phép.
- Cân bằng partition key, tránh hot partitions.
- Chọn consumer concurrency theo downstream capacity.
- Không tạo quá nhiều consumer groups không có chủ sở hữu.
- Điều chỉnh log sampling/retention hợp lý nhưng vẫn có tín hiệu incident.
- Tắt/dọn môi trường lab khi được phép và xác minh chi phí còn phát sinh.

## 18. Thực hành tổng hợp: producer, consumer và replay

### 18.1. Kịch bản

Một hệ thống gửi events:

~~~text
Event Hubs namespace: ehns-kafka-unique-demo
Event Hub / Kafka topic: orders-events
Partitions: 4

Consumer groups:
  orders-analytics-lab
  orders-fraud-lab
~~~

Mục tiêu:

- Producer gửi 6 events có `orderId` làm key.
- Analytics group nhận và commit sau xử lý.
- Fraud group dùng group khác để đọc độc lập.
- Có thể xem topic/partition/offset trong logs.
- Thực hành replay an toàn bằng group lab mới, trong retention.

### 18.2. Bảng kiểm tra

| Bước | Thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Xem namespace tier và Event Hub tồn tại | Standard/Premium/Dedicated phù hợp, `orders-events` đúng |
| 2 | Kiểm tra TCP/TLS 9093 | DNS/TCP/TLS thông, certificate hợp lệ |
| 3 | Cấp SAS hoặc Entra quyền tối thiểu | Producer Send, consumer Listen |
| 4 | Nạp secret qua môi trường bảo mật | Không hard-code/log connection string |
| 5 | Chạy `producer.py` | 6 delivery callbacks thành công |
| 6 | Chạy `consumer.py` với group mới | Nhận các events còn retention |
| 7 | Kiểm tra key/topic/partition/offset | Có metadata hữu ích để trace |
| 8 | Chạy lại consumer với cùng group | Không mặc định đọc lại records đã commit |
| 9 | Dùng group lab mới để replay | Đọc lại records còn retention |
| 10 | Tắt consumer giữa xử lý và commit | Nhận lại record, không tạo side effects trùng |
| 11 | Theo dõi lag/capacity | Lag phù hợp và không có throttling |
| 12 | Dọn resource lab có phê duyệt | Không xóa namespace/consumer groups của production |

### 18.3. Bài A — Số consumers và partitions

Event Hub có 4 partitions. Nhóm Analytics có 6 consumer processes.

**Câu hỏi:** có thể có 6 consumers đều xử lý 6 partitions khác nhau không?

**Đáp án:** Không, có tối đa bốn partitions để phân công song song trong nhóm. Các members dư có thể idle, tùy assignment. Nếu đang nghẽn ở một hot partition, tăng thêm consumers không giải quyết gốc.

### 18.4. Bài B — Chọn partition key

Bạn muốn giữ thứ tự event `OrderCreated → OrderPaid → OrderShipped` cho cùng một đơn hàng.

**Câu hỏi:** nên dùng key là `region` hay `orderId`?

**Đáp án:** `orderId` thường phù hợp hơn vì giữ records cùng đơn vào một partition (với cấu hình partitioner/partitions ổn định) và phân tán hơn `region`. Vẫn phải xử lý publisher concurrency/retry và schema nghiệp vụ.

### 18.5. Bài C — Auto commit và mất dữ liệu logic

Consumer bật auto commit. Offset được commit trước khi ghi database; process crash.

**Câu hỏi:** có thể xảy ra điều gì?

**Đáp án:** Consumer restart từ offset đã commit và có thể bỏ qua record chưa cập nhật database. Thiết kế manual commit sau durable processing và idempotency.

### 18.6. Bài D — Crash giữa database và commit

Worker đã ghi DB thành công rồi crash trước commit offset.

**Câu hỏi:** có thể nhận lại event không? Có nên gửi email lần hai không?

**Đáp án:** Có thể nhận lại; không được tạo tác dụng phụ lần hai khi event đã xử lý. Dùng stable `eventId`, unique constraint, outbox/deduplication hoặc cơ chế idempotent tương ứng.

### 18.7. Bài E — Earliest không replay

Group Analytics đã commit tới offset cuối. Bạn đổi `auto.offset.reset=earliest` và restart, vẫn không nhận các events cũ.

**Đáp án:** vì group đã có committed offsets hợp lệ. `earliest` không ép rewind. Dùng group mới hoặc reset có kiểm soát và bảo đảm dữ liệu chưa hết retention.

### 18.8. Bài F — Private Endpoint

DNS namespace phân giải tới private IP, nhưng Kafka client báo timeout 9093.

**Đáp án:** kiểm tra VNet routing, NSG/UDR, firewall, VPN/ExpressRoute, NAT/proxy và TCP 9093. Không tự thay bootstrap bằng private IP và tắt certificate validation.

### 18.9. Bài G — Kafka Streams và internal topics

Một Kafka Streams topology yêu cầu tạo internal changelog topic và log compaction, nhưng Event Hubs Kafka endpoint không đáp ứng khả năng đã giả định.

**Đáp án:** cần kiểm tra feature compatibility và lựa chọn nền tảng Kafka khác hoặc điều chỉnh kiến trúc/state store; không coi đây chỉ là lỗi SASL password.

### 18.10. Bài H — Ước lượng raw throughput

Producer gửi 5.000 events/giây, mỗi event 4 KiB.

\[
5{,}000\times4/1024=19{,}53\text{ MiB/s}
\]

**Đáp án:** raw payload khoảng 19,53 MiB/s, chưa tính overhead, compression, số groups và peak. Dùng số liệu này làm đầu vào sizing, **không phải hóa đơn hoặc quota chính thức**.

## 19. Dọn tài nguyên lab an toàn

### 19.1. Kiểm kê trước khi xóa

~~~bash
az resource list \
  --resource-group "$RG" \
  --output table
~~~

Không xóa khi `RG` chứa resource chung. Một consumer group/namespace có thể có nhiều ứng dụng phụ thuộc mà bạn không nhìn thấy chỉ từ thông tin task.

### 19.2. Chỉ xóa nếu resource group hoàn toàn thuộc lab

~~~bash
# THAO TÁC PHÁ HỦY: chỉ chạy với approval và đã xác minh RG chỉ chứa lab.
az group delete --name "$RG" --yes
~~~

Bài học **không yêu cầu thực thi lệnh này**. Nếu namespace dùng chung, xóa từng entity lab đã được định danh và kiểm tra consumers/retention trước. Giữ lại telemetry/lesson findings theo chính sách bảo mật của tổ chức.

### 19.3. Kiểm tra sau dọn dẹp

- Không còn namespace hoặc compute lab không mong muốn.
- Không có secrets/connection strings bị lưu trong Git, logs hoặc tickets.
- Role assignments cấp cho lab được rà soát.
- Các dashboards/alerts không còn hướng tới resource đã xóa.
- Cost Management không còn chi phí lab phát sinh bất thường.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Kafka topic ánh xạ với đối tượng nào trong Event Hubs?

**Đáp án:** Event Hub (entity) được tạo sẵn trong Event Hubs namespace.

**Câu 2.** Kafka bootstrap endpoint có dạng gì?

**Đáp án:** FQDN namespace, thường `<namespace>.servicebus.windows.net:9093`, sử dụng TLS và cơ chế SASL phù hợp.

**Câu 3.** Với SASL/PLAIN, username thường dùng là gì?

**Đáp án:** Literal `$ConnectionString`; password là connection string Event Hubs phù hợp.

**Câu 4.** Có thể tự động tạo Event Hub bằng Kafka AdminClient createTopics như Kafka broker không?

**Đáp án:** Không nên giả định. Provision Event Hub bằng Azure management plane/IaC.

**Câu 5.** Producer `produce()` return mà chưa có delivery callback nghĩa là gì?

**Đáp án:** Record có thể mới nằm trong local buffer; cần callback/flush và kiểm tra lỗi để xác nhận broker đã nhận.

**Câu 6.** Kafka offset có xóa event sau khi consumer commit không?

**Đáp án:** Không. Offset là vị trí đọc; records được giữ theo retention của Event Hub.

**Câu 7.** Hai consumers ở cùng group có cùng đọc mọi partition từ đầu độc lập không?

**Đáp án:** Không. Chúng phối hợp chia partitions. Muốn đọc độc lập, dùng group khác với offset riêng.

**Câu 8.** `auto.offset.reset=earliest` có bắt một group đang có offset hợp lệ quay lại từ đầu không?

**Đáp án:** Không.

**Câu 9.** Vì sao cần idempotent consumer dù đã manual commit?

**Đáp án:** Có thể crash sau durable write nhưng trước commit, dẫn tới đọc lại event.

**Câu 10.** Ordering của Event Hubs Kafka được đảm bảo ở cấp nào?

**Đáp án:** Trong một partition theo offset; không có global order giữa mọi partitions.

**Câu 11.** Event Hubs Kafka endpoint có thể được dùng như Kafka compacted changelog lưu bản mới nhất theo key không?

**Đáp án:** Không mặc định; phải xem feature compatibility và thiết kế state store riêng khi cần.

**Câu 12.** TCP 9093 đã thông nhưng SASL auth thất bại, nên làm gì?

**Đáp án:** Kiểm tra username, toàn bộ connection string, policy/role và secret rotation; không tắt TLS.

**Câu 13.** Tại sao lag cao không luôn được sửa bằng cách thêm replicas?

**Đáp án:** Có thể do hot partition, ít partitions, DB throttling, network hoặc capacity Event Hubs.

**Câu 14.** Khi records cũ đã hết retention, group mới có replay chúng không?

**Đáp án:** Không. Cần nguồn lưu lịch sử khác như Data Lake/Capture nếu đã thiết kế.

**Câu 15.** Event Hubs Kafka endpoint có phù hợp cho mọi tính năng Kafka Streams/Connect không?

**Đáp án:** Không mặc định. Phải kiểm thử API support, internal topics, compaction, transactions và framework/version cụ thể.

## Ghi nhớ

- **Azure Event Hubs Kafka endpoint** cho phép Kafka-compatible producers/consumers sử dụng một dịch vụ streaming do Azure quản lý, **không phải Kafka broker cluster toàn quyền quản trị**.
- **Kafka topic tương ứng Event Hub**; bootstrap FQDN ở **port 9093** với **SASL_SSL**, còn topic/partition/retention được quản trị qua Azure.
- Producer cần **delivery callback/ack**, consumer cần **xử lý bền vững rồi commit offset** và **idempotency** để chống redelivery.
- **Partition key** ảnh hưởng phân bố và thứ tự; chỉ có ordering trong partition, không có global order giữa partitions.
- **Consumer group offsets** độc lập theo nhóm; `auto.offset.reset=earliest` không tự rewind group đã có committed offset.
- **Retention hữu hạn** và **Kafka API compatibility có giới hạn**. Đừng mặc định có Kafka log compaction, full broker admin APIs hoặc exactly-once transactions.
- Kết hợp **Azure Monitor + Kafka client metrics + business logs** để theo dõi ingestion, lag, throttling, errors và chi phí.
- Bảo vệ **SAS credentials/OAuth tokens, TLS, RBAC, Private Endpoint/DNS** và kiểm thử cả failure/replay trước production.
