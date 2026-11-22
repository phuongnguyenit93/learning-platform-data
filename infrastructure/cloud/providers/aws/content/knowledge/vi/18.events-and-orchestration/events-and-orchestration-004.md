# EventBridge Pipes và kết nối nguồn với đích

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **Amazon EventBridge Pipes** và phân biệt rõ **source**, **filter**, **input transformation**, **enrichment** và **target**.
- Nhận diện các loại nguồn mà Pipes có thể chủ động đọc, như **Amazon SQS**, **DynamoDB Streams**, **Kinesis Data Streams**, **Amazon MQ**, **Amazon MSK** và **self-managed Apache Kafka**.
- Thiết kế tích hợp **một nguồn → một đích**, biết khi nào cần chuyển sự kiện vào **EventBridge event bus** để fanout sang nhiều consumers thay vì nối nhiều Pipes vào cùng một queue.
- Viết filter pattern cho message body SQS, phân biệt **lọc** với **biến đổi payload** và **enrichment** bằng Lambda/Step Functions Express/API Gateway/API Destination.
- Chọn target thích hợp như **Lambda**, **Step Functions**, **SQS**, **SNS**, **event bus**, **ECS task** hoặc **API Destination**, hiểu hành vi đồng bộ/bất đồng bộ.
- Cấu hình batching, concurrency, retry, DLQ, idempotency và kiểm soát độ trễ, đặc biệt với nguồn **SQS FIFO** hoặc **Kinesis/DynamoDB Streams** đòi hỏi thứ tự.
- Cấp đúng **IAM execution role** cho Pipes với trust `pipes.amazonaws.com`, quyền source/enrichment/target, KMS và kết nối VPC/broker khi cần.
- Tạo một Pipe với **AWS CLI**, thử sự kiện match/non-match, quan sát trạng thái, logs và metrics, xử lý các lỗi cấu hình thường gặp.
- So sánh Pipes với **EventBridge rules**, **Lambda event source mapping**, **Step Functions** và consumer tự polling để chọn giải pháp vừa đủ.
- Ước tính chi phí theo số sự kiện **sau filter**, kích thước payload, batch và các dịch vụ liên quan; đặt cảnh báo, backup/replay và kế hoạch phục hồi.

**Ngữ cảnh học phần:** Bài thuộc chương **Sự kiện và điều phối** của module **CLOUD_PROVIDERS_AWS**. Người học đã gặp Region/AZ, IAM, VPC, compute, lưu trữ, cơ sở dữ liệu, tích hợp và serverless. EventBridge Pipes kết nối các mảnh đó theo kiến trúc hướng sự kiện, giúp giảm code glue nhưng **không thay nhiệm vụ thiết kế semantics, bảo mật, giám sát, khả năng phục hồi và ngân sách**.

> **Phạm vi:** Ví dụ chính là **SQS queue → EventBridge Pipe → AWS Lambda Java** tại một Region trong account lab. Các đoạn ARN, queue URL, tên role, API ID và tài nguyên đều minh họa. Trước khi dùng production, kiểm tra danh sách nguồn/đích và giới hạn theo **Region, account, thời điểm, loại source/target** trong tài liệu AWS hiện hành.

## 1. Tình huống thực tế: đưa sự kiện tới đúng nơi mà không viết poller

Một hệ thống đặt hàng phát nhiều sự kiện vào SQS:

~~~json
{
  "eventId": "evt-order-501",
  "eventType": "OrderPaid",
  "orderId": "ORD-501",
  "customerId": "C-42",
  "occurredAt": "2026-11-20T04:00:00Z"
}
~~~

Các consumer có nhu cầu khác nhau:

- `OrderPaid`: tạo hóa đơn ở Lambda hoặc kích hoạt workflow hoàn tất đơn hàng.
- `OrderCancelled`: gọi logic hoàn tiền.
- `OrderViewed`: chỉ phục vụ analytics, không cần gọi Lambda tạo hóa đơn.

Nếu tự triển khai, nhóm phải viết code gọi `ReceiveMessage`, filter JSON, gọi API đích, quản lý visibility, retry, rate/concurrency, log, metrics và xóa message khi phù hợp. **EventBridge Pipes** làm phần kết nối và vận chuyển này thành **cấu hình**.

~~~mermaid
flowchart LR
    Producer[Order API / producer] --> Queue[(SQS orders-events)]
    Queue --> Pipe[EventBridge Pipe]
    Pipe --> Filter{Filter eventType=OrderPaid}
    Filter -->|Khớp| Enrich[Enrichment tùy chọn]
    Enrich --> Target[Lambda / Step Functions / SQS]
    Filter -->|Không khớp| Drop[Không gửi tới target]
    Target --> Data[(S3 / DynamoDB / RDS)]
    Pipe --> Obs[CloudWatch logs & metrics]
~~~

Với nguồn **SQS**, message **không khớp filter sẽ được Pipes loại khỏi queue**, không tiếp tục chờ một consumer khác chọn nó. Đây là điểm cực kỳ quan trọng khi thiết kế: **SQS không phải event bus fanout**.

## 2. Pipes là gì và không phải là gì?

**Amazon EventBridge Pipes** cung cấp tích hợp theo mô hình **point-to-point**:

\[
\text{Source} \rightarrow [\text{Filter}] \rightarrow [\text{Enrichment}] \rightarrow \text{Target}
\]

Trong đó:

| Thành phần | Nhiệm vụ | Bắt buộc? |
| --- | --- | --- |
| **Source** | Nguồn mà Pipes nhận/poll sự kiện | Có |
| **Filter** | Chọn events đáp ứng event pattern | Không |
| **Enrichment** | Gọi dịch vụ thêm dữ liệu/kiểm tra/điều chỉnh trước target | Không |
| **Target** | Đích cuối cùng mà Pipe chuyển dữ liệu hoặc kích hoạt API | Có |
| **Execution role** | Quyền cho Pipes đọc nguồn, gọi enrichment và target | Có |
| **Logging/metrics** | Quan sát vận hành, lỗi, throttling và throughput | Cấu hình theo nhu cầu |

Một Pipe có **một nguồn và một đích**. Nhiều Pipes có thể cùng gửi vào một target, nhưng **không phải** một Pipe có nhiều targets.

Pipes **không phải**:

- Một hàng đợi bền vững mới thay SQS.
- Một EventBridge rule phát sự kiện từ event bus tới nhiều targets.
- Một hệ thống transaction bảo đảm đúng một lần ghi DB/S3.
- Một công cụ điều phối nghiệp vụ nhiều bước có wait/choice/compensation như **Step Functions**.
- Một engine ETL tùy biến không giới hạn: filter/transform có giới hạn, enrichment phải dùng dịch vụ được hỗ trợ.
- Một container worker do bạn phải chạy 24/7: Pipes tự quản cơ chế nhận/đẩy từ nguồn được hỗ trợ.

**Câu hỏi chọn dịch vụ:** Bạn cần **đưa sự kiện của một nguồn được hỗ trợ tới một target với filter/enrich**? Pipes rất phù hợp. Cần **fanout**? Dùng event bus/SNS hoặc nhiều queue. Cần **workflow nhiều bước/stateful**? Dùng Step Functions, có thể được Pipes kích hoạt.

## 3. So sánh Pipes, EventBridge rules, Scheduler và Lambda ESM

| Tiêu chí | **EventBridge Pipes** | **EventBridge event bus + rules** | **EventBridge Scheduler** | **Lambda event source mapping (ESM)** |
| --- | --- | --- | --- | --- |
| Điểm bắt đầu | SQS/streams/brokers được hỗ trợ | Event được publish lên bus | Lịch/one-time schedule | Nguồn tương thích Lambda poller |
| Mục tiêu | Một source → một target, có filter/enrichment | Match và route events tới nhiều targets | Gọi target tại thời điểm/chu kỳ | Invoke một Lambda từ source |
| Filter | Event patterns trên source records | Event patterns trên bus events | Không phải lọc stream events | Filter criteria ở ESM theo source |
| Enrichment | Lambda, API Gateway, API Destination, Express workflow | Thường dùng target Lambda/Step Functions cho enrichment | Không phải pipeline enrichment | Logic enrichment viết trong Lambda |
| Fanout | Không trực tiếp; có thể gửi vào bus | Phù hợp | Không | Không trực tiếp |
| Retry/DLQ | Phụ thuộc source và target invocation | Event bus target retry/DLQ theo rule | Scheduler retry/DLQ theo lịch | Theo ESM + source |
| Phù hợp | Hợp nhất data source và target với ít glue code | Định tuyến domain events | Tác vụ chạy theo giờ/ngày | Chỉ cần Lambda tiêu thụ SQS/stream |

**Ví dụ chọn:**

- **SQS → Step Functions** với lọc và enrichment: khảo sát **Pipes**.
- **Một `OrderPaid` event → 5 hệ thống**: dùng **EventBridge bus/rules** hoặc **SNS fanout → nhiều queues**, không cho 5 Pipes tranh giành cùng SQS queue.
- **Job lúc 02:00**: dùng **Scheduler**.
- **Chỉ có SQS → Lambda và logic nằm hoàn toàn trong Lambda**: **Lambda ESM** có thể đơn giản hơn một Pipe.

## 4. Các nguồn hỗ trợ và semantics khác nhau

Theo danh mục nguồn EventBridge Pipes, những nguồn chính:

| Source | Loại dữ liệu | Điểm cần nhớ |
| --- | --- | --- |
| **Amazon SQS** | Queue message, standard hoặc FIFO | Pipes poll và **xóa message khi xử lý pipe thành công**; visibility, source DLQ |
| **DynamoDB Streams** | Change data capture records | Stream checkpoint/retention, starting position, shard ordering |
| **Kinesis Data Streams** | Streaming records theo shard/partition key | Shard positions, throughput, parallelization factor |
| **Amazon MQ** | Broker messages | Broker/network/auth, acknowledgment theo loại broker |
| **Amazon MSK** | Managed Kafka topics | Partitions, offsets, networking, broker auth |
| **Self-managed Apache Kafka** | Kafka topics từ cụm tự vận hành hoặc bên thứ ba | Bootstrap brokers, VPC/connectivity, secrets, offset semantics |

**Không coi `S3 bucket`, `RDS database` hay `EventBridge event bus` là nguồn Pipes trực tiếp chỉ vì chúng là dịch vụ AWS.** Nếu muốn kích hoạt Pipes từ dữ liệu S3, thường phải thiết kế bước **S3 notification → SQS** hoặc **EventBridge event bus → target** theo kiến trúc phù hợp. Với dữ liệu RDS, cần sự kiện/CDC publish ra nguồn được hỗ trợ.

### Chọn source theo tính chất dữ liệu

- **Queue (SQS):** thích hợp chia việc cho consumers, message bị xóa sau khi xử lý thành công; retry dựa trên visibility.
- **Stream (Kinesis/DynamoDB):** record còn trong stream theo retention và consumers/iterators có checkpoint; có thể replay trong cửa sổ retention.
- **Broker (MQ/Kafka):** có message acknowledgment hoặc offsets/partitions, cần thiết kế network/auth và thứ tự riêng.

**Không sao chép nguyên retry/DLQ config của SQS sang Kinesis hay Kafka.** Mỗi source có chế độ commit/checkpoint, retention và lỗi khác nhau.

## 5. Thiết kế kiến trúc một source → một target

Một Pipe nên gắn với một hợp đồng dữ liệu rõ ràng:

~~~text
Producer: Order Service
  source: SQS orders-events-lab
  event contract: OrderEvent v1

EventBridge Pipe: paid-orders-pipe
  filter: eventType == OrderPaid
  transform/enrichment: optional
  target: Lambda process-paid-order

Target:
  validate eventId/orderId
  check idempotency & tenant
  write state/S3 and commit

Operations:
  SQS DLQ, CloudWatch alerts, IAM role & KMS
  logs without secrets, retry/rollback strategy
~~~

Phải quyết định sớm:

1. **Ai sở hữu message không khớp filter?** Với SQS source, Pipes sẽ xóa nó khỏi queue; tốt nhất queue đã dành riêng đúng loại sự kiện, hoặc producer route trước.
2. **Nếu target trả thành công nhưng business chưa hoàn tất thì sao?** Chọn invocation semantics, idempotency và cơ chế durable handoff phù hợp.
3. **Nếu enrichment không sẵn sàng?** Pipe có thể retry và giữ/chặn tiến độ source theo đặc tính nguồn.
4. **Nếu source mất retention hoặc bị xóa?** Có backup/replay/outbox và runbook.
5. **Nếu downstream yếu hơn tốc độ source?** Có quota/concurrency/backpressure hay queue trung gian.

**Một Pipe cấu hình đúng không có nghĩa hệ thống đã đạt HA/DR theo yêu cầu.** Phải xét nguồn dữ liệu, target, database và tài nguyên tại mỗi AZ/Region.

## 6. Source SQS: Receive, visibility và acknowledgment do ai quản lý?

Với nguồn **SQS**, EventBridge Pipes hoạt động gần như một consumer được quản lý:

1. Poll SQS và lấy một message/batch.
2. Message trở thành **in-flight**, bị ẩn trong **queue visibility timeout**.
3. Đánh giá filter.
4. Nếu match, tùy chọn transform/enrich rồi invoke target.
5. Khi Pipe xử lý batch thành công theo semantics của target, Pipes **xóa các messages** tương ứng khỏi source queue.
6. Nếu thất bại, messages thường được giao lại khi visibility hết; DLQ của **source queue** áp dụng sau số lần nhận theo redrive policy.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant SQS as Source SQS
    participant Pipe as EventBridge Pipes
    participant T as Target Lambda
    P->>SQS: SendMessage
    Pipe->>SQS: ReceiveMessage
    SQS-->>Pipe: Message + receipt handle
    Pipe->>Pipe: Filter / transform / enrichment
    alt Target invocation thành công
      Pipe->>T: Invoke
      T-->>Pipe: Success
      Pipe->>SQS: DeleteMessage
    else Target hoặc enrichment lỗi
      Pipe->>T: Invoke hoặc enrichment failed
      T-->>Pipe: Error
      Note over SQS: Message được thử lại theo visibility/retry
    end
~~~

**Với nguồn SQS, không viết thêm một consumer thủ công trên cùng queue để “giúp Pipe”** trừ khi bạn chủ ý chia tải giữa các consumers. Hai consumer/pipe cùng queue **tranh message**, không sao chép message.

### Cảnh báo về lọc SQS

Nếu filter pattern không khớp, Pipes **tự xóa message không khớp** khỏi source queue. Đây không phải *put back for another filter*. Ví dụ một Pipe chỉ nhận `OrderPaid` từ queue chung có thể bỏ mất `OrderCancelled` trên queue đó. Nếu cả hai đều cần xử lý, phải **thiết kế producer routing/fanout hoặc dùng event bus/SNS**.

### SQS visibility timeout khi có enrichment

AWS khuyến nghị đặt source queue visibility **ít nhất khoảng 6 lần tổng thời gian chạy enrichment và target** để Pipe còn thời gian retry khi bị throttling, kèm margin và batching window phù hợp. Đây là **guideline**, không phải bảo đảm message sẽ không bị nhận trùng. Một Pipe execution có giới hạn thời gian xử lý riêng (xem mục batching), còn business side effect phải idempotent.

## 7. Stream sources: Kinesis, DynamoDB và vị trí bắt đầu

### DynamoDB Streams

Pipes đọc record thay đổi từ DynamoDB Stream. Bạn cấu hình:

- **StartingPosition**: `TRIM_HORIZON` hoặc `LATEST`;
- batch size/window, parallelization factor;
- retry attempts và maximum record age;
- DLQ theo chức năng stream source;
- IAM `DescribeStream`, `GetShardIterator`, `GetRecords`, `ListStreams`.

DynamoDB Streams thường giữ record **24 giờ**. Nếu target lỗi kéo dài hơn retention, record có thể hết hạn trước khi Pipe xử lý. **DLQ và retry age phải được chọn nhỏ hơn retention thực** nếu cần quan sát dữ liệu thất bại.

### Kinesis Data Streams

Kinesis có shards và partition keys, ảnh hưởng throughput/ordering. Pipe có thể tăng concurrency trên shard bằng `ParallelizationFactor` (giới hạn thường 1–10 theo hỗ trợ), nhưng vẫn cần bảo toàn thứ tự ở mức partition key.

**Đừng giả định nhiều shards đồng nghĩa tất cả events đến target theo một thứ tự toàn cục.** Ordering chỉ có ý nghĩa theo shard/partition key và semantics nguồn.

### LATEST vs TRIM_HORIZON

| Vị trí | Hành vi | Khi phù hợp |
| --- | --- | --- |
| `LATEST` | Bắt đầu gần các records mới nhất | Không cần xử lý lịch sử; chấp nhận rủi ro khi tạo/update |
| `TRIM_HORIZON` | Bắt đầu từ record sớm nhất chưa hết retention | Muốn tránh bỏ sót sự kiện đã xuất hiện trước khi poller hoạt động |

**Cảnh báo eventual consistency:** AWS ghi rõ khi tạo/cập nhật Pipe stream source, poller có thể mất một khoảng thời gian để bắt đầu; dùng `LATEST` **có nguy cơ bỏ lỡ các records phát trong cửa sổ tạo/update**. Nếu tính đầy đủ sự kiện là bắt buộc, đánh giá `TRIM_HORIZON`, idempotency và thời gian retention.

### Stream không phải SQS

Record Kinesis/DynamoDB không bị xóa bởi `DeleteMessage`; Pipe quản lý checkpoint/iterator và records được xóa khi hết retention. Không mô tả retry của stream bằng “chờ visibility timeout 30 giây”.

## 8. Nguồn Amazon MQ, MSK và self-managed Kafka

Đối với nguồn broker:

- **Amazon MQ**: broker có queue/topic theo engine, acknowledgment phụ thuộc broker; Pipe cần kết nối broker, credentials và những quyền mô tả/network phù hợp.
- **Amazon MSK**: đọc records từ Kafka partitions, xử lý offsets và ordering trong partition.
- **Self-managed Kafka**: cần bootstrap brokers, auth (ví dụ SASL credentials/TLS theo cấu hình), reachability và vận hành cluster ngoài AWS nếu có.

### Network là thành phần kiến trúc, không phải tùy chọn

Broker thường nằm trong private subnets hoặc private network. Pipe có thể cần:

- VPC subnets và security groups phù hợp với broker;
- ENIs và quyền mô tả/tạo/xóa network interface theo hướng dẫn;
- route/DNS tới endpoints, port Kafka/MQ đúng;
- Secrets Manager/KMS policies nếu dùng credentials;
- NAT hoặc **VPC endpoint `pipes-data`** trong trường hợp kết nối quản lý Pipes cần thiết theo mô hình AWS.

**Phân biệt**: SQS source dùng AWS-managed SQS API và không yêu cầu bạn đặt một “Pipe compute node” trong VPC; broker source private có yêu cầu VPC/network khác. Không mở broker ports ra Internet chỉ để Pipe đọc được.

### Thứ tự, parallelism và retry

Kafka partitions và MQ source có giới hạn concurrency khác SQS standard. Một partition/group gặp lỗi có thể ảnh hưởng tiến độ. Hãy đo **consumer lag**, throughput và thời gian xử lý; chỉ tăng partitions hoặc Pipe concurrency khi business ordering và broker capacity cho phép.

## 9. FilterCriteria: quyết định event nào đi tiếp

Filter trong Pipes dùng **EventBridge event patterns**; có thể kiểm tra metadata hoặc các trường trong JSON payload được parse/decode theo nguồn. Với SQS, message body có thể là JSON string:

~~~json
{
  "eventId": "evt-2001",
  "eventType": "OrderPaid",
  "orderId": "ORD-2001",
  "amount": 150000
}
~~~

Khi SQS message body là JSON hợp lệ, filter pattern để chỉ nhận `OrderPaid`:

~~~json
{
  "body": {
    "eventType": ["OrderPaid"]
  }
}
~~~

**Vị trí `body` rất quan trọng**. Filter được đánh giá trên **SQS record envelope**; `eventType` nằm trong JSON của `body`, không phải ở root của record SQS.

### Cấu trúc FilterCriteria trong API Pipes

~~~json
{
  "Filters": [
    {
      "Pattern": "{\"body\":{\"eventType\":[\"OrderPaid\"]}}"
    }
  ]
}
~~~

`Pattern` trong AWS API là **một JSON string chứa event pattern**, không phải JSON object được gắn trực tiếp vào trường này. Nhiều Filters trong FilterCriteria được sử dụng theo semantics của dịch vụ; cần kiểm tra test cases thay vì giả định kết hợp điều kiện theo JavaScript `&&`.

### Thêm điều kiện amount

~~~json
{
  "body": {
    "eventType": ["OrderPaid"],
    "amount": [
      {
        "numeric": [">=", 100000]
      }
    ]
  }
}
~~~

Ví dụ trên chỉ gửi những events `OrderPaid` có amount ≥ 100.000 khi input là JSON numeric phù hợp. Nếu amount là chuỗi `"150000"`, numeric filter có thể không khớp; cần schema contract ở producer.

### Filter không thay validation nghiệp vụ

- Filter là điều kiện chọn/loại bỏ sự kiện, không xác nhận DB transaction.
- Filter không biết customer có quyền nhận hàng hay thẻ tín dụng đã charge đúng.
- Với SQS source, **non-matching messages bị loại khỏi queue**; filter sai có thể mất events.
- Nếu body không phải JSON đúng dạng mong đợi, filter kiểu JSON có thể loại message đó; cần canary/test payload trước khi bật.
- **EventBridge Pipes tính phí cho events match filter**, nhưng còn chi phí SQS/broker/source và downstream liên quan.

## 10. Vì sao không đặt hai Pipes lọc khác nhau lên cùng SQS queue?

Tưởng tượng:

~~~text
SQS orders-events
   ├── Pipe A lọc eventType=OrderPaid  → invoice Lambda
   └── Pipe B lọc eventType=OrderCancelled → refund Lambda
~~~

Đây **không phải fanout**. Hai Pipes là các consumers cạnh tranh. Nếu Pipe A nhận `OrderCancelled`, filter A không khớp và Pipes **xóa message**, Pipe B không có cơ hội nhận nó.

### Kiến trúc đúng cho fanout

~~~mermaid
flowchart TB
    Producer[Order Service] --> Bus[(EventBridge event bus)]
    Bus --> Rule1[Rule: OrderPaid]
    Bus --> Rule2[Rule: OrderCancelled]
    Rule1 --> Invoice[Invoice Lambda / SQS]
    Rule2 --> Refund[Refund Lambda / SQS]
    Bus --> Rule3[Rule: All business events]
    Rule3 --> Analytics[Analytics destination]
~~~

Hoặc:

~~~text
Order Service → SNS topic → SQS invoice queue
                          → SQS refund queue
                          → SQS analytics queue

Mỗi queue có riêng Pipe / Lambda ESM / worker.
~~~

Nếu bắt đầu từ một nguồn stream duy nhất cần fanout, có thể đặt **Pipe → EventBridge event bus đích được hỗ trợ**, sau đó dùng **rules** để gửi tới nhiều target. Tài liệu targets của Pipes nêu giới hạn cụ thể về bus cùng account/Region và loại bus, vì vậy cần kiểm tra ARN/loại bus của đích trước khi triển khai; **không giả định mọi custom/cross-account bus đều dùng trực tiếp được**.

## 11. Input transformation: đổi hình dạng payload mà không chạy code

Sau khi filter, có thể dùng **InputTemplate** để chuẩn hóa dữ liệu gửi tới enrichment hoặc target.

Ví dụ SQS envelope có:

~~~json
{
  "messageId": "msg-123",
  "body": "{\"eventId\":\"evt-2001\",\"orderId\":\"ORD-2001\",\"eventType\":\"OrderPaid\"}",
  "attributes": {
    "ApproximateReceiveCount": "1"
  }
}
~~~

Nếu target chỉ cần `eventId`, `orderId`, `eventType`, InputTemplate có thể là:

~~~text
{
  "eventId": "<$.body.eventId>",
  "orderId": "<$.body.orderId>",
  "eventType": "<$.body.eventType>"
}
~~~

Pipes có khả năng **parse JSON body** của SQS khi nội dung hợp lệ, nên JSONPath có thể tham chiếu `$.body.eventId`. Chú ý format của InputTemplate và quote khi biến tham chiếu scalar/JSON object; **không dùng string replace tùy ý làm hỏng JSON escaping**.

### InputTemplate nằm ở đâu?

| Vị trí | Input được biến đổi | Đầu ra gửi tới |
| --- | --- | --- |
| **EnrichmentParameters.InputTemplate** | Event lấy từ source | Dịch vụ enrichment |
| **TargetParameters.InputTemplate** | Kết quả enrichment nếu có, nếu không thì source event | Target |

**Nếu enrichment trả một object mới**, target input transformer thường nhìn thấy **object từ enrichment**, không còn mọi trường metadata của source. Nếu target cần `messageId`, `eventId` hoặc correlation ID cho idempotency, **enrichment phải giữ chúng trong response**.

### Reserved variables

Pipes có các biến do dịch vụ cung cấp trong InputTemplate, chẳng hạn:

- `<aws.pipes.pipe-name>`: tên Pipe;
- `<aws.pipes.pipe-arn>`: ARN của Pipe;
- `<aws.pipes.source-arn>`: ARN nguồn;
- `<aws.pipes.event.ingestion-time>`: thời điểm sự kiện đi vào stage transform;
- `<aws.pipes.event>` và `<aws.pipes.event.json>`: payload thô/JSON theo điều kiện.

Không dùng `<aws.pipes.event.json>` trong nơi đòi JSON string khi object có thể được đưa vào không có escape phù hợp; hãy đối chiếu tài liệu transform và thử payload thực.

### Cạm bẫy dữ liệu

Một InputTemplate chỉ lấy `orderId` mà **bỏ `eventId`** có thể khiến downstream không còn khóa idempotency. Ngược lại, đưa toàn bộ message metadata và PII/secret vào target không cần thiết làm tăng **payload, logs, chi phí và surface rò rỉ**. Chọn **minimum necessary fields**.

## 12. Enrichment: bổ sung thông tin trước khi gửi target

**Enrichment** là một bước tùy chọn gọi một dịch vụ để biến event thô thành dữ liệu có ngữ cảnh hơn. Ví dụ nguồn có `orderId`, enrichment đọc DynamoDB để bổ sung nhóm khách hàng, trạng thái thanh toán hoặc thông tin cần thiết cho target.

Các loại enrichment được AWS hỗ trợ gồm:

- **AWS Lambda function**;
- **API Gateway**;
- **EventBridge API Destination**;
- **AWS Step Functions Express workflow**.

**Không dùng Standard Step Functions workflow làm enrichment**: enrichment cần **response đồng bộ** để Pipe biết phải gửi gì tới target, trong khi Step Functions **Express** có khả năng synchronous integration phù hợp.

~~~mermaid
sequenceDiagram
    participant S as SQS source
    participant P as Pipe
    participant E as Enrichment Lambda
    participant T as Target
    S->>P: Message OrderPaid
    P->>P: Filter match
    P->>E: Sync invoke(orderId, eventId)
    E->>E: Lookup customer/DB
    E-->>P: Enriched event + eventId
    P->>T: Enriched payload
    T-->>P: Ack / response theo integration
    P->>S: Delete source message nếu toàn pipe thành công
~~~

### Những giới hạn enrichment cần nhớ

1. Enrichment được gọi **đồng bộ**; Pipe chờ response trước khi gọi target.
2. Response enrichment tối đa **6 MB** theo giới hạn AWS.
3. Một pipe execution (bao gồm enrichment và target) có giới hạn khoảng **5 phút**; không chọn Pipes để đồng bộ chờ một workflow nhiều giờ.
4. **Partial batch failure handling của enrichment không được hỗ trợ** theo batch semantics được AWS công bố; nếu enrichment thất bại, có thể phải retry lại toàn bộ batch.
5. Enrichment được dùng như **filter bổ sung** có thể trả payload rỗng để Pipe bỏ qua target theo quy tắc dịch vụ; cần kiểm tra các trường hợp `""`, `{}`, `[]`, `[{}]` để tránh gọi target ngoài ý muốn.
6. Nếu target partial-fails, quá trình retry có thể **đi lại qua enrichment**, làm enrichment bị gọi lần nữa. Enrichment phải tránh side effects không idempotent.

**Ưu tiên enrichment dạng read/transform**. Nếu enrichment vừa charge payment rồi target thất bại, retry sẽ tạo rủi ro thanh toán trùng. Business side effects nên đặt trong một workflow có idempotency/transaction/recovery rõ ràng.

## 13. Lambda enrichment thực hành: giữ correlation và schema

Ví dụ Lambda Java (mang tính minh họa) nhận JSON một sự kiện và bổ sung `priority`. Code không gọi DB để giữ tập trung vào shape:

~~~java
package com.example.events;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

import java.util.LinkedHashMap;
import java.util.Map;

public final class OrderEnrichmentHandler
    implements RequestHandler<Map<String, Object>, Map<String, Object>> {

    @Override
    public Map<String, Object> handleRequest(
        Map<String, Object> event, Context context) {

        String eventId = String.valueOf(event.getOrDefault("eventId", ""));
        String orderId = String.valueOf(event.getOrDefault("orderId", ""));

        if (eventId.isBlank() || orderId.isBlank()) {
            throw new IllegalArgumentException("eventId and orderId required");
        }

        Map<String, Object> enriched = new LinkedHashMap<>(event);
        enriched.put("priority", "NORMAL");
        enriched.put("enrichedBy", "orders-enrichment-v1");
        return enriched;
    }
}
~~~

**Lưu ý:** Đây là ví dụ **cho một JSON object**, không phải handler xử lý mọi dạng SQS record/batch của Pipes. Nếu bật batching, enrichment Lambda có thể nhận **mảng events**, kể cả batch size bằng 1 theo cơ chế Pipes. Cần viết handler nhận `List<...>` hoặc xử lý `Object`, trả kết quả phù hợp batch và test trực tiếp payload trước khi bật production.

### Chọn retry behavior

- Lỗi dữ liệu vĩnh viễn: xem lại filter/schema và DLQ, không retry vô hạn.
- Lỗi DynamoDB throttling/transient: dùng retry có backoff/jitter ở SDK và Pipe retry trong giới hạn.
- Timeout: giảm I/O, tăng timeout Lambda trong giới hạn Pipe execution, không tăng lên vô hạn.
- Thiếu quyền: sửa IAM/enrichment role và KMS; thêm retry không giải quyết AccessDenied vĩnh viễn.

## 14. Target: Pipe có thể kích hoạt dịch vụ nào?

Targets AWS hỗ trợ gồm các nhóm sau (cần kiểm tra Region và giới hạn cụ thể):

| Target | Trường hợp dùng | Cạm bẫy |
| --- | --- | --- |
| **AWS Lambda** | Business logic, validation, transformations hoặc writes | Sync/async invocation, lỗi batch, function concurrency |
| **Step Functions Express / Standard** | Workflow thực hiện nhiều bước | Standard target phải invoke **async**; Express có chế độ sync/async |
| **SQS queue** | Durable handoff sang worker khác | Target queue policy, DLQ, dedup FIFO và message attributes |
| **SNS topic** | Thông báo/fanout đến subscribers | Quy tắc hỗ trợ SNS standard/FIFO theo loại target |
| **EventBridge event bus được hỗ trợ** | Chuyển events sang bus rules/fanout | Giới hạn cùng account/Region và loại event bus; cần format event phù hợp |
| **Kinesis stream** | Ghi records streaming | Partition key, payload/batch limits và throughput |
| **Firehose delivery stream** | Giao dữ liệu tới S3/đích analytics | Batching, response/latency |
| **CloudWatch Logs group** | Ghi sự kiện/log/audit ở lab | Không xem logs là database nghiệp vụ |
| **ECS task** | Kích hoạt tác vụ container theo sự kiện | Task definition, cluster, network và quyền `RunTask`/`PassRole` |
| **AWS Batch** | Chạy batch job | Queue, job definition, quota |
| **API Gateway / API Destination** | Gọi REST API hay SaaS | Auth, payload transform, rate limit/retry |
| **Redshift Data API, SageMaker AI Pipeline, Timestream** | Phân tích, ML, metrics | Payload/schema/permissions và service-specific parameters |

**Một Pipe một target**. Nếu business cần cùng một event vào Lambda, SQS, SNS và analytics, hãy dùng **bus rules** hoặc **SNS fanout**, không giả định có mảng `Targets` trong một Pipe.

### Target parameters

Tùy target, `TargetParameters` có thể chứa:

- `InputTemplate` để định hình dữ liệu gửi đi;
- `LambdaFunctionParameters.InvocationType` cho Lambda;
- `StepFunctionStateMachineParameters.InvocationType` cho Step Functions;
- `SqsQueueParameters` khi gửi tới FIFO queue;
- `EventBridgeEventBusParameters` như source/detail-type theo loại đích;
- `EcsTaskParameters` với task definition/network/launch settings;
- các API-specific parameters khác.

**Dynamic JSONPath trong target parameters** có giới hạn cú pháp và một số trường ngoại lệ; không coi nó là JavaScript template có thể nối chuỗi tùy ý. Khi mapping phức tạp, dùng InputTemplate/enrichment có kiểm thử.

## 15. Target invocation: synchronous vs asynchronous

Pipes có hai khái niệm invocation:

- **REQUEST_RESPONSE / synchronous**: Pipe đợi target trả response. Nếu target báo lỗi, Pipe có cơ sở để retry source event/batch theo semantics.
- **FIRE_AND_FORGET / asynchronous**: Pipe gửi yêu cầu tới target và không chờ target **xử lý nghiệp vụ xong**. Thành công khi dịch vụ target **chấp nhận** request không đồng nghĩa business commit.

| Tình huống | Cách chọn |
| --- | --- |
| SQS → Lambda tạo hóa đơn; chỉ xóa source khi Lambda xử lý xong | **Sync invoke** với xử lý lỗi phù hợp |
| SQS → target SQS khác để handoff bền vững | Target API chấp nhận message, sau đó worker đích chịu trách nhiệm DLQ/idempotency |
| SQS → Standard Step Functions workflow | **Async StartExecution**; nguồn có thể được ack khi workflow bắt đầu được chấp nhận |
| Stream có ordering chặt | Dùng sync theo yêu cầu source/target để giữ sequencing |
| API/third-party trả 202 nhưng job vẫn xử lý nền | Phải coi là **handoff accepted**, không phải nghiệp vụ đã hoàn thành |

AWS mặc định gọi target **đồng bộ** đối với các nguồn cần duy trì thứ tự; một số target hỗ trợ chọn kiểu invocation. **Step Functions Standard chỉ có target async** trong Pipes, còn **Express** hỗ trợ sync/async theo khả năng.

### Quy tắc dữ liệu quan trọng

Nếu Pipe xóa SQS source message sau khi target chỉ trả **202 Accepted**, bước nghiệp vụ sau đó thất bại có thể không còn source message để tự retry. Cần target tự có **durable queue/state machine retry/DLQ** hoặc dùng sync business commit và idempotency.

## 16. Batching: không phải mọi source-target đều nhận cùng batch size

Pipes hỗ trợ gom nhiều source records thành một pipe execution khi enrichment/target tương thích. Batch size tối đa bị ràng buộc bởi **cả nguồn lẫn đích**.

Ví dụ, Kinesis source có thể hỗ trợ batch tới **10.000 records**, nhưng nếu target là **SQS**, batch API gửi tối đa **10 messages**. Không cấu hình Pipe `BatchSize=1000` rồi tin target SQS sẽ xử lý được.

| Target hỗ trợ batch | Giới hạn tối đa minh họa từ tài liệu |
| --- | --- |
| **SQS** | **10** messages |
| **SNS** | **10** entries |
| **EventBridge event bus** | **10** events |
| **Kinesis** | **500** records |
| **Firehose** | **500** records |
| **CloudWatch Logs** | **10.000** log events |
| **Lambda / Step Functions** | Ràng buộc bởi payload/giới hạn invoke và cấu hình |

**Các giới hạn này là kiến thức cần đối chiếu tài liệu khi triển khai**, không nên hardcode mà không kiểm tra loại target/Region.

### Khi bật batching: payload thường là array

Nếu source batching được bật và target/enrichment nhận payload JSON đầy đủ (như Lambda), Pipes gửi **mảng records**, có thể vẫn là **array một phần tử** khi batch size = 1.

~~~json
[
  {
    "messageId": "msg-1",
    "body": "{\"eventId\":\"evt-1\",\"eventType\":\"OrderPaid\"}"
  }
]
~~~

Nếu Java handler chỉ nhận `Map<String,Object>` nhưng Pipes gửi `List`, có thể lỗi deserialization/cast. **Kiểm tra event shape thật trong môi trường lab trước khi triển khai**.

### Batching window

Pipes có thể đợi thêm thời gian để gom events khi source hỗ trợ. Với nguồn SQS lưu lượng thấp, AWS lưu ý Pipe có thể chờ tới **khoảng 20 giây** ngay cả khi batching window cấu hình ngắn hơn. Không đặt window vài giây rồi hứa latency cuối–cuối chắc chắn dưới vài giây.

### Pipe execution duration

Một Pipe execution bị giới hạn khoảng **5 phút**, gồm enrichment và target processing. Nếu task cần vài giờ, hãy kích hoạt Step Functions Standard **bất đồng bộ** hoặc ECS/Batch job; Pipe là bước **định tuyến/handoff**, không phải nơi chờ job dài kết thúc.

## 17. Partial batch failures và việc retry lại enrichment

Trong một batch, có thể chỉ một số records thất bại. Pipes có cơ chế xử lý partial failures cho những **source/target tương thích**.

Ví dụ target Lambda nhận 3 records, M1 và M3 thành công, M2 thất bại. Response được định nghĩa theo kiểu:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "M2"
    }
  ]
}
~~~

**Chỉ trả response này khi target/pipe source đã hỗ trợ partial batch semantics và cấu hình xử lý phù hợp**. `itemIdentifier` phải tương ứng **ID của record ở nguồn gốc**, không phải một UUID do enrichment tự tạo:

- **SQS**: `messageId`.
- **Kinesis/DynamoDB**: `eventID` của record tương ứng.

Nếu enrichment làm mất `messageId`/`eventID` trong mảng trả về, Pipe có thể **không xác định đúng records cần retry**. Khi source FIFO/ordered stream, phải kiểm tra cách trả failed/unprocessed records để không phá ordering nghiệp vụ.

### Phân biệt partial failure ở target và enrichment

- **Target partial failure:** khi target/loại response hỗ trợ, Pipes có thể retry những records thất bại.
- **Enrichment partial failure:** không có cơ chế partial batch acknowledgment tương đương; một enrichment lỗi có thể khiến **toàn batch** phải retry.
- Khi target partial-fails và Pipes retry, **enrichment có thể được gọi lại** đối với records thất bại; enrichment cần idempotent.

### Nếu target tự nhận batch nhưng trả HTTP 200?

Đừng tự suy “status 200 là mọi record trong batch đã ghi thành công” nếu target có thể ghi thành công một phần. Với các target AWS hỗ trợ native batch API, Pipes xử lý response partial failure theo cơ chế dịch vụ. Với Lambda/Step Functions custom logic, bạn phải **trả format lỗi hợp lệ** khi cần, không nuốt exceptions rồi trả success.

## 18. Retry, DLQ và backpressure theo source

| Source | Retry/DLQ trọng tâm | Nguy cơ |
| --- | --- | --- |
| **SQS** | **SQS visibility timeout**, source queue **redrive policy** và DLQ | Message được giao lại, xử lý trùng; visibility hết trước khi target hoàn tất |
| **Kinesis** | MaximumRetryAttempts/MaximumRecordAge, checkpoint, source stream retention, DLQ hỗ trợ | Shard bị chặn bởi record lỗi; records hết hạn |
| **DynamoDB Streams** | Retry, maximum age, **24 giờ retention** thường gặp, DLQ | Mất records khi retry quá chậm so với retention |
| **Kafka/MSK** | Partition/offset semantics và broker retention, retry theo tính năng nguồn | Consumer lag/offset, permission/network |
| **Amazon MQ** | Broker acknowledgment/requeue/DLQ theo engine | Poison message làm nghẽn hàng đợi |

### DLQ của SQS source không giống Pipe DLQ của stream

AWS hướng dẫn: với **SQS source**, hãy cấu hình **dead-letter queue trên chính SQS source queue**. Đừng tưởng khai báo một Pipe-level DLQ dùng cho stream retry là tự quản redrive của message SQS.

Với **Kinesis/DynamoDB stream source**, có thể cấu hình **DeadLetterConfig** theo loại nguồn và giới hạn API; stream DLQ hỗ trợ SQS standard hoặc SNS target theo quy định, có những ràng buộc riêng. Chọn `MaximumRecordAgeInSeconds` đủ nhỏ so với retention để còn khả năng gửi record thất bại vào DLQ.

### Idempotency là bắt buộc

Kể cả Pipe retry chính xác, vẫn có thể xảy ra:

~~~text
1. Target ghi hóa đơn vào S3/DB thành công.
2. Response từ target tới Pipe bị timeout/mất.
3. Pipe coi invocation thất bại và retry.
4. Target xử lý lại cùng eventId.
~~~

Chọn **eventId** ổn định, unique condition trong DB hoặc idempotency store. ReceiptHandle SQS **thay đổi sau mỗi lần receive**, nên không phải khóa idempotency nghiệp vụ. Một Pipe quản lý việc giao sự kiện, **không tạo transaction nguyên tử giữa SQS ack và DB commit**.

### Backpressure

Giới hạn concurrency/throughput đến từ:

- Số SQS in-flight messages, visibility và capacity quota;
- Kinesis shards/parallelization factor;
- FIFO `MessageGroupId`;
- Kafka partitions;
- enrichment Lambda/API rate limits;
- target Lambda reserved concurrency, ECS capacity, Step Functions quota;
- DB/API downstream.

Nếu target chậm, **đừng chỉ tăng Pipe concurrency**. Cần đo source backlog/iterator age và giới hạn downstream thực, áp dụng batching hoặc queue trung gian có backpressure.

## 19. IAM execution role: Pipes làm việc nhân danh ai?

Pipes sử dụng **IAM execution role** để đọc nguồn và invoke enrichment/target. Trust policy cho phép principal **`pipes.amazonaws.com`** assume role.

Ví dụ file `pipe-trust-policy.json`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "pipes.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

**Giảm confused deputy:** Trên production, xem hướng dẫn AWS về điều kiện `aws:SourceAccount`/`aws:SourceArn` khi khả thi. Đừng sao chép trust cho `lambda.amazonaws.com` hoặc `ecs-tasks.amazonaws.com` rồi kỳ vọng Pipes assume được.

### Quyền nguồn SQS và target Lambda

Identity policy minh họa cho Pipe chỉ đọc một queue và invoke một function:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadSourceQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events-lab"
    },
    {
      "Sid": "InvokeTargetLambda",
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:111122223333:function:process-orderpaid-lab"
    }
  ]
}
~~~

Đây **chỉ là policy cho SQS→Lambda không enrichment**. Nếu có enrichment Lambda riêng, cần thêm `lambda:InvokeFunction` cho enrichment ARN. Nếu target là event bus, SQS, ECS hoặc Step Functions, dùng đúng API actions/ARN/PassRole của target tương ứng.

### Ba lớp role khác nhau

| Role / principal | Quyền |
| --- | --- |
| **Pipes execution role** | Nhận SQS/Kinesis records, gọi enrichment/target, logs theo config |
| **Lambda target execution role** | Quyền mã Java bên trong Lambda gọi DynamoDB/S3/KMS |
| **Deployer role/user** | `pipes:CreatePipe`/`UpdatePipe`, `iam:PassRole` với Pipes role, thay deployment |

**Pipe role không tự cấp quyền S3 cho Lambda business code**. Ngược lại, Lambda role có `s3:PutObject` không giúp Pipe sửa lỗi `sqs:ReceiveMessage AccessDenied`.

### IAM cho stream/broker source

- DynamoDB Streams: `DescribeStream`, `GetRecords`, `GetShardIterator`, `ListStreams`.
- Kinesis: các API mô tả stream/shards và đọc records/subscribe theo chế độ.
- Amazon MQ/MSK/self-managed Kafka: các API describe/network, Secrets Manager, KMS, broker auth và đôi khi CloudWatch Logs.
- Customer-managed KMS key: principal/Pipe role cần quyền decrypt/key policy/grants phù hợp, không chỉ IAM allow trên source.

**Nguyên tắc:** Cấp quyền tối thiểu theo từng nguồn/đích; không dùng `pipes:*`, `sqs:*`, `kms:*` trên `*` chỉ để sửa lỗi.

## 20. KMS, VPC và quản lý dữ liệu trong pipeline

### 20.1. Mã hóa và quyền truy cập

Dữ liệu sự kiện có thể đi qua SQS SSE-KMS, DynamoDB Streams/Kinesis encrypted, TLS, log destinations và target DB/S3. Pipes có các tùy chọn encryption/configuration tùy resource.

Phải kiểm tra:

- **SQS queue policy** hoặc resource policy cho phép đúng role/source.
- **KMS key policy** cho Pipe role đọc nguồn encrypted bằng customer managed key.
- **Enrichment target** có quyền API riêng; Pipe role chỉ invoke, Lambda role mới gọi DB/S3.
- **Log destinations** có quyền ghi, retention và KMS access phù hợp.
- **Event payload** không đưa plaintext secret, thẻ thanh toán hoặc PII dư thừa.

### 20.2. Private broker/VPC

Nếu source là MQ/MSK/Kafka private, Pipe cần connectivity tới brokers theo config hỗ trợ. Kiểm tra:

~~~text
VPC / subnets / route / SG / NACL
    ↓
DNS phân giải broker endpoints
    ↓
TCP/TLS broker connection và authentication
    ↓
Pipes poller / consumer
    ↓
Target invoke qua service integration
~~~

Một số lỗi kết nối cần NAT hoặc interface endpoint đến **`pipes-data`** theo tài liệu hỗ trợ. Đừng áp dụng cấu hình network của Lambda chạy trong private subnet cho toàn bộ Pipes: **không phải mọi Pipe phải gắn một ENI trong VPC của người dùng**.

### 20.3. Payload schema và PII

Một record có thể chứa dữ liệu không phù hợp target. Hãy chuẩn hóa:

- `eventId`, `eventType`, `schemaVersion`, `occurredAt`, `correlationId`;
- business resource ID thay cho dữ liệu cá nhân chi tiết khi có thể;
- transformation để bỏ token, email, địa chỉ không cần thiết;
- retention của source, DLQ và log data theo quy định;
- kiểm soát truy cập vào cả **execution logs** khi bật TRACE.

**Bật “Include execution data” có thể log cả payload nguồn, request enrichment và response target.** Chỉ dùng khi có cơ sở bảo mật, masking/retention và người được cấp quyền đọc phù hợp.

## 21. Lab từng bước: SQS → EventBridge Pipe → Lambda Java

> **Điều kiện:** Account/Region lab có quyền IAM, SQS, Lambda, Pipes và CloudWatch tương ứng. Có thể phát sinh phí SQS, Pipes, Lambda và Logs. Sử dụng AWS CLI v2 với IAM role/profile, không hardcode access key. Chuẩn bị một **Lambda Java 21 function** có tên `process-orderpaid-lab` và handler thực sự xử lý **mảng record source** hoặc một event được transform theo config. Phần code ở mục kế tiếp chỉ là mô hình tham khảo.

### 21.1. Chuẩn bị queue

~~~bash
aws sts get-caller-identity --profile lab

aws sqs create-queue \
  --queue-name orders-events-lab \
  --attributes VisibilityTimeout=180,ReceiveMessageWaitTimeSeconds=20 \
  --region ap-southeast-1 \
  --profile lab
~~~

Lấy queue URL và ARN:

~~~bash
aws sqs get-queue-url \
  --queue-name orders-events-lab \
  --region ap-southeast-1 \
  --profile lab

aws sqs get-queue-attributes \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events-lab" \
  --attribute-names QueueArn VisibilityTimeout \
  --region ap-southeast-1 \
  --profile lab
~~~

**Lý do chọn visibility 180 giây trong lab:** Có margin cho một target Lambda xử lý ngắn và retry. Với production, đặt theo tổng thời gian target/enrichment, SLA, latency, batching window và khuyến nghị **ít nhất 6 lần runtime** cho SQS source, chứ không sao chép 180 cho mọi ứng dụng.

### 21.2. Tạo IAM role cho Pipes

Giả sử file `pipe-trust-policy.json` và `pipe-role-policy.json` chứa JSON đúng như mục 19, tạo role:

~~~bash
aws iam create-role \
  --role-name orders-pipe-role-lab \
  --assume-role-policy-document file://pipe-trust-policy.json \
  --profile lab

aws iam put-role-policy \
  --role-name orders-pipe-role-lab \
  --policy-name orders-pipe-policy-lab \
  --policy-document file://pipe-role-policy.json \
  --profile lab
~~~

Cần đợi IAM propagation và bảo đảm **role ARN/account** trùng giá trị sẽ dùng trong Pipe. Principal đang chạy lệnh phải có `iam:PassRole` với role này, được ràng buộc service phù hợp.

### 21.3. Tạo Pipe configuration JSON

File `pipe.json`:

~~~json
{
  "Name": "orders-paid-pipe-lab",
  "Description": "Filter OrderPaid from SQS into Lambda in lab",
  "DesiredState": "STOPPED",
  "RoleArn": "arn:aws:iam::111122223333:role/orders-pipe-role-lab",
  "Source": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events-lab",
  "SourceParameters": {
    "FilterCriteria": {
      "Filters": [
        {
          "Pattern": "{\"body\":{\"eventType\":[\"OrderPaid\"]}}"
        }
      ]
    },
    "SqsQueueParameters": {
      "BatchSize": 1
    }
  },
  "Target": "arn:aws:lambda:ap-southeast-1:111122223333:function:process-orderpaid-lab",
  "TargetParameters": {
    "LambdaFunctionParameters": {
      "InvocationType": "REQUEST_RESPONSE"
    }
  },
  "Tags": {
    "environment": "lab",
    "application": "orders"
  }
}
~~~

**Giải thích cấu hình:**

- `Source` là **SQS ARN**, không phải Queue URL.
- `Target` là Lambda function ARN; `TargetParameters` chọn sync invoke để Pipe nhận kết quả xử lý.
- `FilterCriteria.Filters[0].Pattern` là **string chứa JSON**.
- `BatchSize=1` giúp lab dễ kiểm tra thứ tự; **handler vẫn phải hỗ trợ shape array** theo batch semantics đã cấu hình.
- `DesiredState=STOPPED` giúp inspect Pipe trước khi bắt đầu consume những messages có thể bị xóa do filter.

### 21.4. Tạo Pipe và xem trạng thái

~~~bash
aws pipes create-pipe \
  --cli-input-json file://pipe.json \
  --region ap-southeast-1 \
  --profile lab

aws pipes describe-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

Chờ trạng thái phù hợp và kiểm tra `CurrentState`, `DesiredState`, `StateReason`, `Source`, `Target`, role. **CreatePipe là operation có trạng thái chuyển tiếp** (`CREATING`, `STARTING`, `RUNNING`, `STOPPED`...), không thể coi việc API trả 200 đã chứng minh Pipe chạy và đọc queue.

### 21.5. Gửi message match và không match

Tạo lần lượt:

~~~bash
aws sqs send-message \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events-lab" \
  --message-body '{"eventId":"evt-2001","eventType":"OrderPaid","orderId":"ORD-2001"}' \
  --region ap-southeast-1 \
  --profile lab

aws sqs send-message \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events-lab" \
  --message-body '{"eventId":"evt-2002","eventType":"OrderCancelled","orderId":"ORD-2002"}' \
  --region ap-southeast-1 \
  --profile lab
~~~

Bắt đầu Pipe:

~~~bash
aws pipes start-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab

aws pipes describe-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

**Kỳ vọng:**

- `evt-2001` khớp filter và được gửi tới Lambda.
- `evt-2002` **không khớp** và **bị loại khỏi SQS source queue**.
- Khi Lambda xử lý thành công theo Pipe invocation, SQS message phù hợp được xóa.
- Nếu Lambda xử lý lỗi, message có thể được nhận lại theo visibility/retention và cuối cùng DLQ nếu queue được cấu hình redrive.

**Không dùng một nguồn queue chứa sự kiện thật chưa phân loại** để thử filter xóa message như thế này.

## 22. Lambda Java target: xử lý payload đúng kiểu và idempotency

Ví dụ handler Java nhận **Object** để minh họa cách xử lý nguồn truyền **mảng SQS records hoặc object đơn**; cần dependency `aws-lambda-java-core` và `jackson-databind` phù hợp trong JAR/ZIP/image.

~~~java
package com.example.events;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;
import java.util.Map;

public final class OrderPaidTarget
    implements RequestHandler<Object, String> {

    private static final ObjectMapper JSON = new ObjectMapper();

    @Override
    public String handleRequest(Object event, Context context) {
        List<?> records =
            event instanceof List<?> list ? list : List.of(event);

        for (Object raw : records) {
            if (!(raw instanceof Map<?, ?> record)) {
                throw new IllegalArgumentException("Unexpected record shape");
            }

            Object body = record.get("body");
            if (body == null) {
                throw new IllegalArgumentException("Missing SQS body");
            }

            try {
                JsonNode payload = body instanceof String s
                    ? JSON.readTree(s)
                    : JSON.valueToTree(body);

                String eventId = payload.path("eventId").asText("");
                String orderId = payload.path("orderId").asText("");
                String eventType = payload.path("eventType").asText("");

                if (eventId.isBlank() || orderId.isBlank()
                    || !"OrderPaid".equals(eventType)) {
                    throw new IllegalArgumentException("Invalid event");
                }

                // Production: conditional write theo eventId, commit
                // business transaction, cập nhật S3/DB, rồi mới return.
                context.getLogger().log(
                    "Processed event " + eventId + " for " + orderId);
            } catch (Exception ex) {
                context.getLogger().log(
                    "Target processing failed: "
                    + ex.getClass().getSimpleName());
                throw new IllegalStateException(
                    "Target invocation failed; allow Pipe retry", ex);
            }
        }
        return "OK";
    }
}
~~~

**Đây là code minh họa, chưa thực hiện idempotency bền vững.** `println/log` thành công không chứng minh nghiệp vụ đã commit. Ở production phải dùng **DynamoDB conditional put, SQL unique constraint hoặc inbox/outbox** và bảo đảm downstream side effects an toàn khi retry.

### Vì sao handler phải xử lý array?

Một Pipe bật batching có thể gửi `[record1, record2]`, **thậm chí batch chỉ một record vẫn có thể là array**. Một handler Java trông đợi duy nhất `Map<String,String>` có thể throw `ClassCastException` trước khi business logic chạy.

**Nếu bật InputTemplate ở target**, payload có thể không còn SQS envelope với `body`. Khi đó phải điều chỉnh handler cho **schema đầu ra của transform**, không tiếp tục `record.get("body")` một cách mù quáng.

### Handler success vs failure

- Xử lý hoàn tất và return success: Pipe có thể ack nguồn theo target invocation mode.
- Throw exception: Pipe có thể retry event/batch, nên **idempotency** cần có.
- Swallow exception, chỉ log lỗi rồi return `"OK"`: Pipe có thể **xóa SQS message mặc dù business thất bại**, là anti-pattern nghiêm trọng.

## 23. Thay đổi Pipe và dọn lab an toàn

### Kiểm tra và tạm dừng

~~~bash
aws pipes describe-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab

aws pipes stop-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

Chờ `CurrentState=STOPPED` trước khi thay cấu hình quan trọng, và theo dõi trạng thái `STOPPING`/stop failures. API stop là thao tác asynchronous; không nên tin rằng request đã hoàn thành toàn bộ ngay khi CLI trả kết quả.

### Thay filter/source/target

Có thể dùng `update-pipe` cho các trường được API hỗ trợ và phải kiểm tra restrictions/side effects khi Pipe đang chạy. Với thay đổi có nguy cơ **xóa non-matching SQS messages**, nên:

1. Tạo cấu hình trong môi trường lab/canary queue riêng;
2. Tạo fixture payload match và non-match;
3. Validate target schema, ID mapping và IAM role;
4. Dừng/đổi Pipe theo quy trình đã review;
5. Bắt đầu lại và theo dõi `StateReason`, logs, source backlog, DLQ;
6. Có kế hoạch rollback configuration **nhưng hiểu rằng messages đã bị lọc/xóa không được tự phục hồi**.

### Dọn tài nguyên lab

~~~bash
aws pipes delete-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

Chỉ xóa queue, Lambda, IAM role và log group **nếu được tạo riêng cho lab và không còn phụ thuộc**, sau khi đã giữ lại event/diagnostic data cần thiết. **Không dùng `PurgeQueue` để dọn production** hoặc để che sự cố lọc sai.

## 24. CloudFormation/IaC: khai báo Pipe có thể review

Infrastructure as Code giúp review source/target ARN, IAM least privilege và lifecycle cùng application code. Ví dụ CloudFormation **rút gọn** (IAM role/queue/Lambda là tài nguyên hiện hữu được truyền qua parameters):

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Pipe from lab SQS OrderPaid events to Lambda
Parameters:
  SourceQueueArn:
    Type: String
  TargetFunctionArn:
    Type: String
  PipeRoleArn:
    Type: String
Resources:
  OrdersPaidPipe:
    Type: AWS::Pipes::Pipe
    Properties:
      Name: orders-paid-pipe-lab
      Description: Route OrderPaid messages to Lambda
      DesiredState: STOPPED
      RoleArn: !Ref PipeRoleArn
      Source: !Ref SourceQueueArn
      SourceParameters:
        SqsQueueParameters:
          BatchSize: 1
        FilterCriteria:
          Filters:
            - Pattern: '{"body":{"eventType":["OrderPaid"]}}'
      Target: !Ref TargetFunctionArn
      TargetParameters:
        LambdaFunctionParameters:
          InvocationType: REQUEST_RESPONSE
~~~

**Cần lưu ý:**

- Mẫu này chưa định nghĩa IAM role, source queue, target Lambda, source queue DLQ và logging; deploy hoàn chỉnh cần thêm.
- CloudFormation `Pattern` là **string**, dù YAML single quotes khiến nhìn giống JSON object.
- Tách `DesiredState: STOPPED` khỏi thao tác bật sau khi đã kiểm thử.
- Kiểm tra drift, IAM policy, resource replacement/updates và rollback plan; **IaC rollback không khôi phục message bị filter xóa**.
- Tags, LogConfiguration và KMS có thể được đưa vào IaC theo chính sách tổ chức.

## 25. Logging và CloudWatch monitoring cho Pipes

Pipes có **CloudWatch metrics** và logging vào các đích được AWS hỗ trợ như **CloudWatch Logs**, **Firehose** hoặc **S3**. Khi bật logs, một Pipe có thể phát log theo các execution stages.

### Mức logging

| Mức | Có gì? | Khi dùng |
| --- | --- | --- |
| **OFF** | Không phát execution logs qua config này | Hệ thống chỉ cần metrics, nhưng giảm khả năng debug |
| **ERROR** | Records liên quan lỗi, timeout, throttling | Mặc định hợp lý cho production |
| **INFO** | Lỗi và một số stage transition/success | Phục vụ vận hành/điều tra |
| **TRACE** | Nhiều chi tiết của các bước execution | Chỉ bật có thời hạn khi debug |

**Lưu ý:** Console và API/CLI có thể có default config khác nhau. Nếu tạo Pipe qua CLI/IaC mà **không cấu hình LogConfiguration**, không giả định có CloudWatch execution logs. Ngoài ra Pipe logging **khác** CloudWatch logs của Lambda target.

### Include execution data

Nếu bật, log có thể chứa:

- Payload của source event/batch;
- request gửi tới enrichment/target;
- response trả về.

Đây có thể là **PII, tài liệu nội bộ, token hoặc business data**. Chỉ bật khi đã xem data classification, retention, encryption và người có quyền xem log. Với CloudWatch Logs, bản ghi log Pipe có giới hạn kích thước và có thể bị truncate.

### Các tín hiệu cần theo dõi

| Nguồn metric/log | Tín hiệu | Diễn giải |
| --- | --- | --- |
| **Pipes** | Execution started/succeeded/failed/partially failed, throttled, duration | Pipe có hoạt động và target có nhận đúng không? |
| **SQS source** | Visible/NotVisible, age of oldest, DLQ visible | Backlog, visibility/failed processing |
| **Kinesis/DynamoDB Streams** | Iterator age/lag, shard throughput, retry errors | Stream bị chậm hoặc checkpoint bị chặn |
| **Lambda enrichment/target** | Invocations, Errors, Duration, Throttles | Lỗi xảy ra ở code hay quá quota? |
| **Event bus/target downstream** | Failed invocations, DLQ, workflow failures | Handoff accepted nhưng business chưa hoàn thành |
| **IAM/CloudTrail** | CreatePipe, UpdatePipe, Start/StopPipe, policy edits | Ai thay đổi routing/filter/role? |
| **CloudWatch Logs** | Pipe StateReason, error records, correlationId | Chẩn đoán lỗi cụ thể |

CloudWatch metrics gửi theo **best effort**. Một điểm dữ liệu thiếu hoặc đến muộn không phải chứng cứ tuyệt đối rằng không có event. Dùng cả **business metrics**, ví dụ `orders_paid_received`, `invoices_created`, `duplicates_ignored`, `dlq_count`.

### Correlation ID xuyên pipeline

~~~text
Producer eventId
  → SQS messageId / body eventId
  → Pipe execution logs / pipe ARN
  → Enrichment request/response có eventId
  → Target invocation logs có eventId
  → DB/S3 commit record có eventId
~~~

**Giữ `eventId` qua mọi transformation/enrichment** để đối chiếu dữ liệu và xác định lost/duplicated business operations.

## 26. Các tình huống kiến trúc và cách chọn Pipes

### A. SQS hóa đơn: lọc và gọi Lambda

**Yêu cầu:** Chỉ `OrderPaid` mới cần tạo hóa đơn.

**Khuyến nghị:** Nếu producer có thể gửi vào **queue riêng cho OrderPaid**, Pipe dùng SQS→Lambda, có optional transform; tránh dùng filter phá hủy trên queue chia sẻ sự kiện cho nghiệp vụ khác. Lambda làm conditional write theo `eventId`, ghi S3, xử lý lỗi/timeout đúng; source SQS có DLQ.

### B. DynamoDB Streams → EventBridge event bus

**Yêu cầu:** DynamoDB có thay đổi Order, nhiều subscribers cần biết `OrderShipped`.

~~~mermaid
flowchart TB
    Table[(DynamoDB Orders)] --> Stream[DynamoDB Streams]
    Stream --> Pipe[EventBridge Pipe]
    Pipe --> Filter[Filter MODIFY + status SHIPPED]
    Filter --> Bus[(EventBridge event bus được hỗ trợ)]
    Bus --> Rule1[Rule: Logistics]
    Bus --> Rule2[Rule: Notifications]
    Rule1 --> Queue1[(Logistics SQS)]
    Rule2 --> Queue2[(Email SQS)]
~~~

**Chú ý:** DynamoDB Streams có retention hạn chế và record format `dynamodb.NewImage` chứa AttributeValue wrappers. Filter phải viết cho đúng shape `{"S":"SHIPPED"}`, không chỉ `"SHIPPED"` ở root. Sử dụng source starting position `TRIM_HORIZON` nếu yêu cầu không bỏ record trong giai đoạn Pipe bắt đầu; dùng idempotency ở consumers.

### C. Kinesis telemetry → Firehose/analytics

**Yêu cầu:** Hệ thống thu nhiều records sensor, chỉ chuyển những measurements có nhiệt độ vượt ngưỡng.

**Khuyến nghị:** Kinesis source, filter trên decoded `data`, transform rút gọn payload, target Firehose/S3 analytics theo hỗ trợ; chọn batch size/window, shard/partition concurrency và metric iterator age. Không đẩy quá nhiều metadata không cần vào target.

### D. MSK Kafka → Step Functions

**Yêu cầu:** Một event từ Kafka kích hoạt workflow nhiều bước.

**Khuyến nghị:** Pipe từ MSK source, filter, optional enrichment, target Step Functions Express/Standard theo invocation type hỗ trợ. Với Standard **async**, việc bắt đầu workflow thành công **không chứng minh toàn bộ workflow thành công**; cần monitoring state machine, retries/DLQ và business idempotency riêng. Chú ý partition ordering và consumer lag.

### E. EventBridge Pipes không thay workflow

**Yêu cầu:** Thanh toán → chờ phê duyệt 48 giờ → gửi thông báo → hoàn tiền nếu bị từ chối.

**Không nên:** Gọi enrichment Lambda rồi giữ kết nối đồng bộ 48 giờ. Pipe execution có giới hạn thời gian.

**Nên:** Pipe kích hoạt **Step Functions Standard** bất đồng bộ; workflow có Wait, Choice, Retry/Catch, compensation, persistence và observability thích hợp.

## 27. Troubleshooting: từ StateReason đến nguồn và đích

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
| --- | --- | --- |
| Pipe `CREATE_FAILED` / `START_FAILED` | Source/target ARN sai, IAM PassRole/trust sai, source bị vô hiệu | `describe-pipe`, `StateReason`, CloudTrail |
| `AccessDenied` khi nhận SQS | Role thiếu `ReceiveMessage/DeleteMessage/GetQueueAttributes`, queue policy hoặc KMS | Pipe role, SourceArn, resource policy, KMS |
| Message không đến Lambda nhưng mất khỏi SQS | **Filter không khớp** → Pipes loại message | FilterCriteria body/JSON type, logging, source events |
| Hai Pipes cùng đọc SQS nhưng mỗi target thiếu event | Competing consumers, nonmatching message bị xóa | Thiết kế lại fanout với bus/SNS hoặc queue riêng |
| Source backlog tăng | Pipe STOPPED, target bị throttled/lỗi, thiếu capacity | CurrentState, metrics, SQS visible/not visible |
| Target Lambda trả lỗi liên tục | Handler sai batch shape, timeout, thiếu role/data | Lambda logs, event payload, target role, retry/DLQ |
| Handler return success nhưng đơn chưa được xử lý | Code swallow exception, target async handoff | Business commit/idempotency, InvocationType, downstream logs |
| Pipe nhận sai payload | InputTemplate JSON quote sai, enrichment đổi schema | Sample transformed event, template paths, logs |
| Batch target báo lỗi một phần | Sai itemIdentifier, mất metadata trong enrichment | `messageId`/`eventID`, partial response shape |
| Enrichment bị gọi nhiều lần | Target retry khiến Pipe chạy lại enrichment | Idempotency, pure lookup, duplicate metrics |
| SQS message xử lý lại | Visibility quá ngắn, worker/target lỗi, network timeout | Visibility 6× guidance, retries, idempotency |
| SQS DLQ trống dù Pipe thất bại | Chưa cấu hình source redrive, chưa đạt maxReceiveCount | Queue RedrivePolicy/DLQ, receive count |
| DynamoDB stream records bị bỏ sót | `LATEST` trong creation/update window | TRIM_HORIZON, stream retention, replay |
| Kinesis iterator age tăng | Shard bottleneck, slow target/enrichment | ParallelizationFactor, batch/throughput, target latency |
| Kafka source lỗi kết nối | SG, DNS, broker port, IAM/SASL secret, endpoint | VPC subnet/SG, `pipes-data`, broker logs |
| Pipe STOPPED do source disabled | Source stream đã bị tắt/xóa | StateReason, source lifecycle, tạo/reconfigure mới theo docs |
| Log trống | Chưa bật LogConfiguration hoặc Level OFF | Pipe logging, destination IAM, CloudWatch retention |
| Chi phí đột biến | Nhiều matched events/batches, large payload, retries, verbose logging | Pipes metrics, Pricing Calculator, KMS/SQS/logs |
| SQS FIFO group bị chặn | Một message/group lỗi, processing theo thứ tự | MessageGroupId, visibility/retry, DLQ runbook |

### Quy trình điều tra có thứ tự

~~~text
1. Xác nhận account, Region, Pipe name/ARN và source/target ARN.
2. DescribePipe: CurrentState, DesiredState, StateReason, role, filter,
   enrichment, target parameters, LogConfiguration.
3. Kiểm tra source:
   SQS Visible/NotVisible/DLQ hoặc Kinesis/DDB iterator lag,
   Kafka/MQ broker state và network.
4. Nếu records biến mất: kiểm tra filter, nhất là SQS non-matching drop.
5. Kiểm tra role trust pipes.amazonaws.com, IAM actions, KMS/key policy.
6. Xem enrichment logs/latency; kiểm tra payload input/output schema.
7. Xem target logs/response, sync/async invocation, batch/partial failures.
8. Kiểm tra business eventId: đã commit chưa, duplicate hay lost data?
9. Sửa một nguyên nhân trong lab, replay fixture có kiểm soát,
   xác nhận CloudWatch metrics, DLQ và idempotency.
~~~

**Đừng chữa lỗi bằng** `AdministratorAccess`, mở broker SG `0.0.0.0/0`, bỏ filter không kiểm tra, bật TRACE chứa PII lâu dài hoặc tăng retry vô hạn. Những thay đổi đó che lỗi, tăng rủi ro bảo mật và có thể làm queue/stream hết retention.

## 28. Hiệu năng và chi phí: tính sau lọc, có tính batching

EventBridge Pipes thường được tính phí theo **requests sau filtering** và kích thước payload/batch, theo biểu giá từng Region. Tài liệu AWS mô tả **mỗi phần 64 KB payload** được tính như một request cho Pipes; ngoài ra source, enrichment và target có bảng giá riêng.

### Ví dụ ước lượng

Giả sử trong 30 ngày:

- SQS có **10.000.000** messages;
- Filter khớp **25%** = 2.500.000 events;
- Trung bình **5 events/batch**, payload mỗi batch không vượt một đơn vị 64 KB theo giả định;
- Không tính retry/empty batches.

\[
N_{\text{billable Pipe requests}}
\approx
\frac{10{,}000{,}000\times 25\%}{5}
=
500{,}000
\]

Nếu giá minh họa là **0,40 USD/triệu requests** theo bảng giá ví dụ của AWS, phần Pipes khoảng:

\[
0.5 \times \$0.40=\$0.20
\]

**Đây là ví dụ từ mô hình pricing, không phải báo giá cố định theo mọi Region/thời điểm**. Nếu batch payload **256 KB**, mỗi batch có thể được tính như **4 đơn vị 64 KB**, nên phải xét cả **bytes**, không chỉ đếm batch.

### Tổng chi phí kiến trúc

\[
C_{\text{total}}
\approx C_{\text{Pipes}}
+ C_{\text{source}}
+ C_{\text{enrichment}}
+ C_{\text{target}}
+ C_{\text{data/KMS}}
+ C_{\text{network}}
+ C_{\text{logs/monitoring}}
\]

Ví dụ:

- **SQS:** requests, data transfer, KMS tùy encryption.
- **Lambda enrichment/target:** invocations, duration × memory, concurrency, CloudWatch Logs.
- **API Destination:** external API fees và quota.
- **Kinesis/MSK:** shards/stream capacity, storage, broker network.
- **VPC endpoints/NAT:** connection và data processing theo kiến trúc.
- **CloudWatch Logs/S3/Firehose:** logging size/retention, storage, transfer.
- **Retries:** có thể tăng số executions và chi phí downstream, dù eventId business duy nhất.

### Giảm chi phí nhưng không làm hỏng semantics

- Filter sớm nhưng **không loại mất dữ liệu trên queue chia sẻ**.
- Giảm kích thước payload qua transformation, giữ eventId.
- Batch theo giới hạn source/target và SLO latency.
- Tránh enrichment Lambda chỉ để copy/rename vài fields đã làm được bằng InputTemplate.
- Đặt CloudWatch Logs level/retention hợp lý, tránh TRACE payload nhạy cảm.
- Đặt **AWS Budgets**, tags và cảnh báo anomalies; đo chi phí trên một business event được xử lý thành công.

## 29. Bài tập áp dụng và câu hỏi tự kiểm tra

### Bài tập 1 — Chọn Pipes hay event bus

Một queue SQS `orders` có ba event types: `OrderPaid`, `OrderCancelled`, `OrderShipped`. Ba nhóm cần nhận độc lập mỗi loại và có retry/DLQ riêng.

**Yêu cầu:** Giải thích vì sao tạo ba Pipes đọc cùng queue có thể **mất message**. Đề xuất thiết kế **event bus + rules** hoặc SNS fanout → queues riêng; chỉ ra nơi đặt idempotency và DLQ.

### Bài tập 2 — Filter đúng cấu trúc body

SQS message body:

~~~json
{
  "eventId": "evt-501",
  "eventType": "OrderPaid",
  "amount": 90000
}
~~~

Hãy viết filter cho `OrderPaid` với amount ≥ 100.000. Dự đoán record này có được gửi tới target không và **điều gì xảy ra với message** trên source SQS sau khi filter loại bỏ. Phân biệt với Kinesis stream filtering.

### Bài tập 3 — Enrichment và idempotency

Pipe SQS → enrichment Lambda đọc DynamoDB → target Lambda tạo hóa đơn. Target ghi S3 xong nhưng response timeout; Pipe retry.

Hãy mô tả:

1. Vì sao enrichment có thể được invoke lại.
2. Vì sao `eventId` phải được giữ qua payload enrichment.
3. Cách dùng conditional put để ngăn tạo hóa đơn hai lần.
4. Cách phân biệt target đã commit nhưng chưa ack với target chưa chạy.

### Bài tập 4 — Batching và target limits

Kinesis source cho phép batch rất lớn, target là SQS.

Hãy giải thích vì sao không thể cấu hình tùy ý batch 1.000 records khi target SQS chỉ nhận tối đa 10 entries/batch theo giới hạn hiện hành. Nếu target là Lambda, cần kiểm tra **payload 6 MB**, array shape, execution duration và retry semantics nào?

### Bài tập 5 — SQS visibility và DLQ

Enrichment tối đa 8 giây, target Lambda tối đa 22 giây, tổng runtime thông thường ≤30 giây.

1. Áp dụng guideline **6 × (8 + 22) = 180 giây** cho source queue visibility.
2. Nếu target bị throttled hoặc thời gian xử lý vượt 30 giây, cần kiểm thử gì?
3. Vì sao DLQ phải cấu hình ở **SQS source queue**?
4. Vì sao kể cả 180 giây vẫn cần idempotency?

### Bài tập 6 — LATEST có thể mất dữ liệu

DynamoDB Streams đang có ghi liên tục. Nhóm tạo Pipe mới với StartingPosition `LATEST`, nhưng polling bắt đầu chậm vài phút.

Hãy giải thích eventual consistency và nguy cơ mất records, khi nào chọn `TRIM_HORIZON`, cách giới hạn retry age so với retention 24 giờ và cách kiểm tra no-loss bằng business event IDs.

### Bài tập 7 — Async target không chứng minh business hoàn tất

Pipe gửi event sang **Step Functions Standard** với invocation **async**. `StartExecution` trả thành công, nhưng workflow lỗi sau 15 phút.

Ai có trách nhiệm retry/recovery? Source SQS còn giữ message không? Hãy thiết kế state machine retry/Catch, alert, DLQ/compensation, business correlation và quy trình replay mà không gây duplicate side effects.

### Bài tập 8 — IAM và VPC

Pipe dùng MSK broker private, enrichment Lambda, target SQS queue được mã hóa SSE-KMS.

Hãy liệt kê IAM actions theo **Pipe execution role**, **Lambda execution role** và **deployer**, VPC subnets/SG/DNS/broker authentication, KMS key policies, queue resource policies và các kiểm thử network cần làm. Giải thích vì sao cấp `sqs:SendMessage` cho Lambda role không tự giúp Pipe gọi target SQS.

### Bài tập 9 — Quan sát và chi phí

Một Pipe xử lý 1 triệu events/ngày nhưng target chỉ ghi được 200 nghìn business records, đồng thời `ExecutionFailed` tăng.

Hãy đề xuất dashboard gồm source backlog/iterator age, Pipe failures/throttles, enrichment/target errors, DLQ, eventId commit/duplicate rate và payload size. Ước lượng các nguồn phí khi retry liên tục và lập runbook ưu tiên dữ liệu trước chi phí.

### Câu hỏi ngắn

1. **Một Pipe có bao nhiêu sources và targets?** Một source và một target.
2. **Filter có bắt buộc không?** Không.
3. **Enrichment có chạy sau filter không?** Có, với events đi qua filter.
4. **SQS message không khớp filter còn nằm trong queue chờ Pipe khác không?** Không; Pipes loại bỏ message khỏi source queue.
5. **SQS source successful pipe invocation ai xóa message?** Pipes quản lý DeleteMessage.
6. **DynamoDB Streams có visibility timeout 30 giây như SQS không?** Không; dùng iterator/checkpoint và retention.
7. **Kinesis `LATEST` có nguy cơ bỏ records lúc tạo Pipe không?** Có, vì poller eventual consistency.
8. **Step Functions Standard có làm enrichment sync được không?** Không; enrichment hỗ trợ Express sync.
9. **Target Standard workflow async được không?** Có, theo integration được hỗ trợ.
10. **Enrichment partial batch failure được hỗ trợ như target không?** Không.
11. **Target partial failure cần ID nào với SQS?** `messageId` của source event.
12. **Bật batching size 1 có luôn bảo đảm target Lambda nhận object thay vì array không?** Không; phải kiểm tra batch event shape.
13. **Execution role principal của Pipe là gì?** `pipes.amazonaws.com`.
14. **Pipe role cấp S3 PutObject có tự cho Java code trong Lambda target quyền đó không?** Không.
15. **Pipe execution có thể đồng bộ chờ 2 giờ không?** Không; có execution duration limit, dùng async workflow.
16. **Pipes thay thế idempotency không?** Không.
17. **Pipe target trả 202 có chứng minh DB commit không?** Không.
18. **SQS queue không trống nhưng Pipes không tiêu thụ là do gì?** Có thể STOPPED, IAM/KMS, filter, throttling, visibility, target lỗi hoặc network theo source.

## 30. Checklist triển khai production

- [ ] Đã xác định **một source, một target**; yêu cầu fanout dùng bus/SNS/queues đúng mô hình.
- [ ] Chọn đúng loại source **SQS, Kinesis, DynamoDB Streams, MQ, MSK hoặc self-managed Kafka** và hiểu retention/ack/checkpoint.
- [ ] Phân loại message body/schema version, giữ **eventId** và correlation ID xuyên Pipe.
- [ ] Filter pattern đã test với payload match, non-match, malformed, metadata và type.
- [ ] Với **SQS source**, hiểu rõ **message không khớp filter bị xóa**, không đặt nhiều Pipes tranh queue nếu muốn fanout.
- [ ] InputTemplate valid JSON theo target contract, không làm mất idempotency key hoặc mang thừa PII.
- [ ] Enrichment dùng sync integration hỗ trợ (Lambda/API Gateway/API Destination/Express), timeout dưới Pipe execution limit và idempotent khi retry.
- [ ] Target được chọn đúng service/API mode, business commit vs handoff semantics đã document.
- [ ] Source/target batch size và window phù hợp payload limits, latency SLO và ordering.
- [ ] Target Lambda/Step Functions xử lý array event/batch response đúng format; partial failures được thử.
- [ ] SQS source visibility có margin theo tổng runtime và retry, source queue có redrive/DLQ/maxReceiveCount.
- [ ] Stream source starting position, shard/partition ordering, retry age và retention được thiết kế.
- [ ] IAM Pipe execution role trust `pipes.amazonaws.com`, least privilege source/enrichment/target và KMS.
- [ ] IAM của Lambda/Step Functions target tách khỏi Pipe role, deployer có `iam:PassRole` theo phạm vi.
- [ ] Broker/VPC subnets/SG/DNS/TLS, Secrets Manager và `pipes-data` endpoint khi cần đều được kiểm chứng.
- [ ] Không bật TRACE include execution data chứa PII/secret lâu dài; có retention/masking/encryption.
- [ ] Có CloudWatch metrics/logs, StateReason, source backlog/iterator age, DLQ alarms và business success metrics.
- [ ] Có kiểm thử các lỗi: IAM deny, KMS deny, target timeout, enrichment fail, partial batch, FIFO block, stream retention.
- [ ] Có replay/restore/idempotency, audit route changes, IaC/change review/rollback plan.
- [ ] Dự toán Pipes pricing theo matched events, **64 KB units**, batch, retries và phí source/enrichment/target.
- [ ] Có AWS Budgets, cost allocation tags, dashboard, runbooks và môi trường canary riêng.
- [ ] Khi thay/xóa Pipe, kiểm tra dữ liệu tồn đọng và tránh purge nguồn hoặc vô tình loại messages production.

## 31. Tổng kết

**EventBridge Pipes kết nối một nguồn sự kiện với một đích**, cho phép thêm **filter, input transformation và enrichment** mà không phải viết mã polling/định tuyến. Nó đặc biệt hữu ích cho **SQS/streams/brokers → Lambda, Step Functions, event bus hoặc các targets được hỗ trợ**.

Điểm cần nhớ nhất:

- **Pipes không tự fanout**; nhiều Pipes đọc cùng SQS queue có thể **tranh giành và loại message không khớp**.
- **Filter** chọn events, **transform** đổi payload, **enrichment** gọi dịch vụ bổ sung dữ liệu; ba bước có trách nhiệm khác nhau.
- **SQS source** dùng visibility/ack và source DLQ; **Kinesis/DynamoDB Streams** dùng iterator/checkpoint/retention; broker có semantics riêng.
- **Enrichment synchronous**, partial batch failure chủ yếu thuộc stage target; Pipe execution có thời gian giới hạn, không thay Step Functions workflow.
- **IAM execution role, KMS/VPC, idempotency, logging/metrics và cost** là một phần của thiết kế, không phải công việc phụ sau khi Pipe chạy.

Khi triển khai một kiến trúc AWS an toàn và có khả năng phục hồi, hãy kiểm tra **eventId, ordering, duplicate side effects, payload schema, target completion semantics, replay và ngân sách** trên môi trường lab trước khi chạy production.

### Tài liệu AWS chính thức để đối chiếu

- [Amazon EventBridge Pipes overview](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes.html)
- [Concepts: source, filter, enrichment, target](https://docs.aws.amazon.com/eventbridge/latest/userguide/pipes-concepts.html)
- [Supported Pipes sources](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-event-source.html)
- [Supported Pipes targets](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-event-target.html)
- [Event filtering in Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-event-filtering.html)
- [Input transformations for Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-input-transformation.html)
- [Enrichment in EventBridge Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/pipes-enrichment.html)
- [Pipes batching and concurrency](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-batching-concurrency.html)
- [Amazon SQS source for Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-sqs.html)
- [DynamoDB Streams source for Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-dynamodb.html)
- [Kinesis source for Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-kinesis.html)
- [Pipes event source permissions](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-permissions.html)
- [Pipes error handling and troubleshooting](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-error-troubleshooting.html)
- [Pipes logging](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-logs.html)
- [Pipes monitoring via CloudWatch](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-monitoring.html)
- [AWS CLI pipes create-pipe](https://docs.aws.amazon.com/cli/latest/reference/pipes/create-pipe.html)
- [AWS CLI pipes describe-pipe](https://docs.aws.amazon.com/cli/latest/reference/pipes/describe-pipe.html)
- [AWS CloudFormation AWS::Pipes::Pipe](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-pipes-pipe.html)
- [EventBridge Pipes pricing](https://aws.amazon.com/eventbridge/pricing/)

**Lưu ý vận hành:** Giá, quota, danh mục source/target, behavior invocation và giao diện AWS CLI/Console có thể thay đổi theo Region/account/thời điểm. Luôn đối chiếu tài liệu đang áp dụng, diễn tập retry/lỗi filter, và test dữ liệu thật đã ẩn thông tin nhạy cảm trước khi phát hành.
