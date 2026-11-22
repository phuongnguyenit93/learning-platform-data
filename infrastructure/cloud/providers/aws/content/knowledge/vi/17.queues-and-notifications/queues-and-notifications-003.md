# Visibility timeout, long polling và cơ chế acknowledgment trong Amazon SQS

## Mục tiêu học tập

Sau bài học, người học có thể:

- Mô tả đầy đủ **vòng đời một SQS message**: producer gửi, message chờ, consumer nhận, message chuyển sang *in-flight*, xử lý thành công/thất bại và được xóa hoặc được giao lại.
- Giải thích **visibility timeout** là khoảng thời gian tạm ẩn message **sau khi nhận**, không phải thời gian lưu trữ hay một khóa bảo đảm xử lý duy nhất.
- Chọn thời gian visibility dựa trên **p95/p99 processing time**, thời gian shutdown, retry, batch size và mục tiêu phục hồi.
- Sử dụng `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility` với **ReceiptHandle**, bao gồm mở rộng timeout bằng heartbeat và thả message sớm bằng timeout 0.
- Phân biệt **short polling** với **long polling**, cấu hình `WaitTimeSeconds` từ 0 đến 20 giây, hiểu *empty receive*, HTTP client timeout và ảnh hưởng chi phí.
- Thiết kế **acknowledgment** sau khi side effect đã được lưu bền vững, bảo đảm **idempotency** khi message bị giao lại; phân biệt `MessageId` và `ReceiptHandle`.
- Xử lý **batch**, **dead-letter queue (DLQ)**, **FIFO message group**, giới hạn in-flight và lỗi *poison message*.
- Phân biệt **consumer tự polling** với **AWS Lambda event source mapping**: ai nhận, ai xóa message, vì sao batch error có thể gây xử lý lại bản ghi đã thành công.
- Kiểm thử luồng nhận/xóa bằng AWS CLI, viết consumer Java bằng **AWS SDK for Java v2**, giám sát bằng CloudWatch và chẩn đoán message bị lặp hoặc tồn đọng.
- Liên hệ SQS với **SNS fanout**, IAM, VPC endpoints, KMS, Lambda/ECS/EC2, Region/AZ, chi phí và kế hoạch phục hồi của ứng dụng AWS.

**Bối cảnh:** Bài thuộc chương **Hàng đợi và thông báo** của module **CLOUD_PROVIDERS_AWS**. Trong một hệ thống bán hàng, API có thể tạo đơn hàng ở RDS/DynamoDB rồi phát sự kiện; SQS làm bộ đệm tách biệt hệ thống nhận yêu cầu và hệ thống xử lý. Dù ứng dụng chạy trên **EC2, ECS, EKS hay Lambda**, việc chọn đúng polling/visibility/ack quyết định liệu đơn hàng được xử lý an toàn, backlog có giảm và hệ thống có chịu được lỗi hay không.

> **Phạm vi:** Bài tập trung vào **Amazon Simple Queue Service (Amazon SQS)**. Amazon SNS là dịch vụ thông báo/phân phối sự kiện có cơ chế delivery/retry khác; một SNS topic có thể fanout vào các SQS queues, nhưng **acknowledgment sau xử lý message tại SQS** không phải acknowledgement của SNS. Các lệnh và ARN bên dưới là **mẫu lab**, phải thay bằng account/Region tài nguyên được phép sử dụng.

## 1. Bài toán: nếu consumer chết sau khi nhận đơn hàng thì sao?

Giả sử một ứng dụng tạo sự kiện:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "orderId": "ORD-1001",
  "occurredAt": "2026-11-20T03:00:00Z"
}
~~~

Producer gửi event đến SQS; worker lấy event để tạo hóa đơn, lưu S3 và cập nhật trạng thái đơn hàng.

Các tình huống có thể xảy ra:

1. Worker nhận message rồi **xử lý thành công** và xóa message: công việc hoàn tất.
2. Worker nhận message nhưng **crash trước khi ghi hóa đơn**: SQS cần cho consumer khác thử lại.
3. Worker **ghi hóa đơn thành công rồi crash trước khi xóa message**: một consumer khác có thể xử lý lại, gây ghi/trả thông báo trùng nếu ứng dụng không idempotent.
4. Worker nhận message, xử lý **lâu hơn visibility timeout**: message có thể được giao cho consumer khác trong khi worker đầu vẫn chạy.
5. Worker xử lý dữ liệu **không hợp lệ vĩnh viễn**: cần giới hạn số lần retry, đưa vào DLQ để không làm bão lỗi hoặc chặn các message khác.

SQS giải quyết một phần bằng **lưu trữ bền vững và cơ chế giao lại message**. Nhưng **SQS không biết giao dịch kinh doanh đã commit hay chưa**. Ứng dụng phải quyết định khi nào công việc đủ điều kiện để **acknowledge bằng cách xóa message**.

~~~mermaid
flowchart LR
    P[Producer / Order API] -->|SendMessage| Q[(SQS queue)]
    Q -->|ReceiveMessage| C[Consumer]
    C --> B{Xử lý và commit thành công?}
    B -->|Có| D[DeleteMessage bằng ReceiptHandle]
    D --> X[Message được xóa]
    B -->|Không / crash| V[Không xóa]
    V --> T[Visibility timeout hết]
    T --> Q
    Q -. Vượt retry threshold .-> DLQ[(Dead-letter queue)]
~~~

**Ý chính:** *ReceiveMessage* không xác nhận xử lý thành công. Với SQS consumer chủ động dùng SDK/CLI, “ack” theo nghĩa nghiệp vụ thường tương ứng **`DeleteMessage` sau thành công**.

## 2. Vòng đời message: visible, in-flight, deleted

Một message SQS cần được hiểu qua các trạng thái:

| Trạng thái | Khi nào? | Consumer khác có thể nhận? |
| --- | --- | --- |
| **Sent / stored / available** | Producer gửi thành công, message không bị delay hay visibility đang ẩn | Có, nếu các điều kiện FIFO và quota cho phép |
| **Delayed** | Có queue delay/message timer chưa hết | Chưa |
| **In-flight / not visible** | Consumer đã nhận, message chưa xóa và visibility chưa hết | Thông thường chưa; standard queue vẫn có ngoại lệ do at-least-once delivery |
| **Visible again** | Visibility hết hoặc được đặt 0, message chưa xóa | Có |
| **Deleted** | `DeleteMessage` thành công theo handle hiện hành và message được xóa | Không còn trong queue theo hành vi bình thường; standard queue vẫn cần idempotency trước bản sao hiếm |
| **Moved to DLQ** | Redrive policy đạt ngưỡng số lần nhận khi message vẫn thất bại | Được xử lý riêng ở DLQ |

**Cần phân biệt ba bộ đếm thời gian:**

- **Delivery delay**: ẩn message **ngay sau khi gửi**, trước lần nhận đầu tiên; tối đa 15 phút theo tính năng queue/message timer.
- **Visibility timeout**: ẩn message **sau khi ReceiveMessage trả nó cho consumer**; mặc định 30 giây, giới hạn tối đa 12 giờ từ lần nhận tương ứng.
- **Message retention period**: thời gian SQS có thể giữ message chưa xóa trước khi hết hạn; mặc định 4 ngày, cấu hình tối đa 14 ngày.

Một message còn trong retention nhưng visibility đã hết có thể được giao lại. **Retention không phải thời gian worker được phép xử lý một lần**.

## 3. Visibility timeout thực sự có nghĩa gì?

**Visibility timeout** là khoảng thời gian một message đã nhận được SQS **tạm ẩn khỏi các lượt nhận khác** để consumer có cơ hội xử lý và xóa message.

Giả sử queue có visibility timeout **60 giây**:

~~~text
T = 00s  Consumer A ReceiveMessage → nhận M1 + ReceiptHandle A.
         M1 thành in-flight; bắt đầu đếm visibility 60 giây.

T = 10s  Consumer B long poll; thông thường chưa nhận M1.

T = 40s  A vẫn đang gọi dịch vụ tạo PDF.

T = 60s  A chưa DeleteMessage → M1 có thể visible trở lại.

T = 65s  Consumer B ReceiveMessage → nhận lại M1,
         có ReceiptHandle B mới.

T = 70s  A cuối cùng hoàn tất; nếu A còn cố xóa bằng handle A
         thì không thể giả định thao tác này xóa được bản đã giao lại.
~~~

### Visibility timeout không phải distributed lock tuyệt đối

Với **standard queue**, AWS SQS sử dụng mô hình **at-least-once delivery**. Do cơ chế lưu trữ phân tán, message có thể được giao lại ngay cả trong một số tình huống không mong đợi, kể cả khi visibility đang còn. Vì vậy:

- Không thiết kế code dựa vào giả định **“một MessageId chỉ được xử lý một lần”**.
- Không coi visibility như một **lease có fencing token** để bảo vệ giao dịch trong database.
- Nếu side effect phải duy nhất (trừ tiền, tạo hóa đơn, gửi email), cần **idempotency** và điều kiện commit ở dữ liệu đích.
- Nếu worker cũ xử lý quá hạn, hệ thống cần tránh nó ghi đè kết quả của worker mới.

**Mối quan hệ quan trọng:** Visibility hỗ trợ giảm xử lý đồng thời, còn **correctness** của dữ liệu phải được bảo vệ ở tầng ứng dụng/database.

## 4. Các mốc cấu hình visibility: mặc định, override và giới hạn

Các giá trị AWS SQS cần nhớ:

| Thuộc tính | Giá trị/giới hạn thông thường | Phạm vi |
| --- | --- | --- |
| Visibility mặc định của queue | **30 giây** | Các message được nhận khi không override |
| Visibility tối thiểu | **0 giây** | Message có thể được làm visible ngay |
| Visibility tối đa | **43.200 giây (12 giờ)** | Tính theo giới hạn từ lần message được nhận |
| `VisibilityTimeout` queue attribute | Cấu hình cấp queue | Áp dụng cho các lượt nhận theo cơ chế queue |
| `ReceiveMessage.VisibilityTimeout` | Override trên **các message được trả bởi lần ReceiveMessage** đó | Không đổi giá trị cấu hình chung của queue |
| `ChangeMessageVisibility` | Đổi thời hạn ẩn cho một message **đã được nhận** | Cần receipt handle hợp lệ |
| Message retention | Mặc định **4 ngày**, tối đa **14 ngày** | Giới hạn tồn tại của message trong queue |

Điểm dễ nhầm: **`ChangeMessageVisibility(120)` đặt lại khoảng visibility 120 giây tính từ thời điểm gọi**, nhưng **không đặt lại mốc tối đa 12 giờ tính từ lần ReceiveMessage**. Nếu chỉ còn 10 phút trước mốc 12 giờ mà yêu cầu thêm 60 phút, SQS trả lỗi; nó **không tự giảm về 10 phút**.

**Thay đổi visibility riêng cho một lần nhận không được ghi nhớ cho lượt nhận sau của cùng message.** Nếu message không bị xóa, lần `ReceiveMessage` mới sử dụng queue default hoặc override mới, chứ không vĩnh viễn mang theo số giây đã được `ChangeMessageVisibility` ở lần xử lý trước.

### Visibility trong batch

Một lần `ReceiveMessage` có thể trả **tối đa 10 messages**. Thông số visibility áp dụng cho những message trong kết quả đó. Nếu xử lý **tuần tự**, message cuối có thể đợi quá lâu và hết visibility **trước khi bắt đầu xử lý**. Vì vậy số message nhận mỗi lần phải được chọn theo concurrency, service time, giới hạn worker và chiến lược gia hạn.

## 5. Chọn visibility timeout theo thời gian xử lý

Không có một timeout tốt cho mọi workload. Chọn quá ngắn dễ xử lý trùng; quá dài khiến retry sau crash chậm.

### 5.1. Một công thức khởi đầu

Với worker xử lý một message tại một thời điểm:

\[
V_{\text{initial}} \gtrsim T_{\text{processing p99}} + T_{\text{commit/delete}} + T_{\text{safety}}
\]

Trong đó:

- `T_processing p99`: thời gian xử lý gần mức cao nhất khi hệ thống còn bình thường;
- `T_commit/delete`: thời gian commit tác vụ và gọi `DeleteMessage`;
- `T_safety`: dự phòng network jitter, GC pause, retries ngắn và scheduler delay.

**Đây là quy tắc thiết kế, không phải thuật toán bắt buộc của AWS**. Phải dùng dữ liệu đo thực và kiểm tra độ phân tán latency.

Ví dụ:

~~~text
Thời gian xử lý p99:           42 giây
Commit và xóa message:         3 giây
Dự phòng:                     15 giây
Visibility ban đầu tham khảo: 60 giây
~~~

Nếu job thường mất 2 phút nhưng đôi lúc mất 10 phút, không nhất thiết đặt visibility 12 giờ cho mọi message. Có thể chọn **2–3 phút ban đầu**, sau đó dùng **heartbeat** để gia hạn khi thực sự còn làm.

### 5.2. Chọn theo mục tiêu phục hồi

| Kịch bản | Visibility quá ngắn | Visibility quá dài |
| --- | --- | --- |
| Worker xử lý ảnh trong 90 giây | Message có thể được giao lại khi worker còn tạo ảnh | Khi worker crash, message có thể nằm ẩn quá lâu |
| Xử lý giao dịch trong 1 giây | Có thể vẫn đủ, nhưng dễ lỗi khi DB chậm bất thường | Retry sau crash chậm hơn cần thiết |
| Long-running job không biết thời gian | Timeout cố định khó chọn | Heartbeat thường thích hợp hơn, nhưng giới hạn 12 giờ vẫn tồn tại |
| FIFO message group có message lỗi | Có thể nhiều lần xử lý trùng | **Cả nhóm** có thể bị trì hoãn lâu trước khi retry |
| Lambda batch xử lý 30 giây | Timeout 10 giây gây lỗi/duplicate | Timeout không cân với timeout Lambda/DLQ |

### 5.3. Tính theo batch

Nếu nhận 10 messages và xử lý tuần tự, mỗi message tối đa 20 giây, message thứ 10 có thể bị xử lý sau gần 180 giây kể từ khi nhận; tổng batch gần 200 giây. Visibility 30 giây là rõ ràng không phù hợp.

Các phương án:

- Nhận ít message hơn (ví dụ `maxNumberOfMessages=1` khi processing dài).
- Dùng worker pool có giới hạn, bảo đảm mỗi message được gia hạn riêng.
- Tăng visibility theo **thời gian hàng đợi nội bộ** cộng processing, không chỉ thời gian handler.
- Nếu batch độc lập, dùng `DeleteMessageBatch` sau khi từng message hoàn tất, xử lý **partial failures của API batch**.
- Tránh prefetch hàng nghìn messages khiến chúng nằm **in-flight** mà chưa có worker thực sự xử lý.

## 6. ChangeMessageVisibility và heartbeat

Khi một worker còn đang xử lý nhưng gần hết thời gian ẩn, gọi:

~~~text
ChangeMessageVisibility(
  QueueUrl = queue URL,
  ReceiptHandle = receipt handle hiện hành,
  VisibilityTimeout = số giây còn muốn ẩn kể từ lúc gọi
)
~~~

Ví dụ:

~~~text
T = 00s  Nhận message, visibility = 60 giây.
T = 40s  Worker vẫn xử lý và biết còn công việc.
         Gọi ChangeMessageVisibility(60).
         Mốc hiện tại kéo tới khoảng T = 100s.
T = 75s  Gọi lại ChangeMessageVisibility(60) khi vẫn có tiến triển.
         Mốc hiện tại kéo tới khoảng T = 135s.
T = 88s  Hoàn tất side effect và DeleteMessage thành công.
~~~

### Nguyên tắc heartbeat đúng

1. Tạo heartbeat chỉ khi consumer **thật sự sở hữu receipt handle của lần nhận hiện tại**.
2. Gia hạn **trước khi timeout cũ hết**, có khoảng dự phòng cho network/GC.
3. Chỉ gia hạn nếu công việc **vẫn đang tiến triển**; nếu worker treo vô hạn, heartbeat không nên giữ message mãi.
4. **Dừng heartbeat** sau khi message được xóa hoặc worker ngừng sở hữu message.
5. Giới hạn tổng thời gian xử lý và chuyển tình huống quá lâu sang mô hình có checkpoint.
6. Log số lần gia hạn, elapsed time, attempts và reason nếu cần điều tra.

**Không dùng `ChangeMessageVisibility` như bảo đảm exactly-once.** Nếu worker sau timeout đã nhận message và có receipt handle mới, việc gia hạn bằng handle cũ có thể thất bại hoặc không còn hiệu lực theo mong đợi.

### Trả message về queue sớm

Khi worker nhận message nhưng chủ động từ chối xử lý ngay (ví dụ host sắp shutdown, tài nguyên local không đủ), có thể đặt:

~~~bash
aws sqs change-message-visibility \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --receipt-handle "RECEIPT_HANDLE_MOI_NHAT" \
  --visibility-timeout 0 \
  --region ap-southeast-1 \
  --profile lab
~~~

Lệnh này làm message **có thể nhận lại ngay**. Nó **không ghi nhận đã xử lý thất bại vĩnh viễn** và cũng **không tự đưa vào DLQ**. Đừng thực hiện trong vòng lặp tốc độ cao khi lỗi backend chưa khắc phục, vì có thể tạo **hot-loop retry** tốn request và làm tăng tải downstream.

## 7. Acknowledgment trong SQS là DeleteMessage

SQS không có API mang tên `AckMessage` như một số message brokers. Với **consumer tự polling**, cách xác nhận đã xử lý là:

1. `ReceiveMessage` lấy message và receipt handle.
2. Thực hiện logic, ghi dữ liệu và **commit** thành công.
3. Gọi `DeleteMessage` bằng **receipt handle của lượt nhận hiện hành**.
4. Nếu delete thất bại hoặc status không chắc chắn, **không giả định message đã biến mất**; retry có kiểm soát và bảo đảm xử lý idempotent.

### Phân biệt MessageId và ReceiptHandle

| Trường | Do ai cấp / khi nào? | Dùng để làm gì? |
| --- | --- | --- |
| **MessageId** | SQS trả khi message được gửi | Nhận diện/log/correlation một message được enqueue |
| **ReceiptHandle** | SQS trả mỗi lần `ReceiveMessage` thành công | **DeleteMessage**, `ChangeMessageVisibility` cho lượt nhận |
| **eventId/orderId** | Ứng dụng định nghĩa trong message body/attributes | Idempotency/business correlation |
| **MessageGroupId** (FIFO) | Producer cấp | Giữ thứ tự trong nhóm và giới hạn parallelism |
| **MessageDeduplicationId** (FIFO) | Producer cấp hoặc SQS tính từ body khi bật content-based | Khử trùng lần gửi theo cửa sổ deduplication |
| **ApproximateReceiveCount** | SQS system attribute | Hỗ trợ quan sát số lần nhận/retry, không thay idempotency key |

Một message có thể được nhận lần 1 với `ReceiptHandle=A` và lần 2 với `ReceiptHandle=B`. Dùng `A` để xóa sau lần 2 **có thể trả HTTP 200 nhưng message không bị xóa**. Luôn dùng receipt handle mới nhất và tránh để nhiều workers cùng xử lý side effect không có cơ chế chống trùng.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as Amazon SQS
    participant A as Consumer A
    participant B as Consumer B
    participant DB as Database
    P->>Q: SendMessage(eventId=evt-1001)
    Q-->>P: MessageId=M1
    A->>Q: ReceiveMessage
    Q-->>A: M1, ReceiptHandle=H1
    A->>DB: Xử lý/commit nghiệp vụ
    alt A xử lý thành công trong visibility
      A->>Q: DeleteMessage(H1)
      Q-->>A: Thành công
    else A crash trước khi delete
      Note over Q: Hết visibility, M1 visible trở lại
      B->>Q: ReceiveMessage
      Q-->>B: M1, ReceiptHandle=H2
      B->>DB: Xử lý idempotent
      B->>Q: DeleteMessage(H2)
    end
~~~

**Ack sau commit, không ack trước commit.** Nhưng việc “commit rồi delete” vẫn có **khoảng không nguyên tử giữa DB và SQS**, vì vậy cần idempotency/outbox/inbox phù hợp ở tầng dữ liệu.

## 8. At-least-once và vì sao phải idempotent

Với standard queue, nhận message nhiều lần là một tình huống cần **thiết kế trước**:

~~~text
1. Consumer xử lý đơn hàng ORD-1001 và ghi DB thành công.
2. Consumer mất kết nối ngay trước hoặc sau khi gọi DeleteMessage.
3. SQS vẫn có thể giao lại message.
4. Consumer khác nhận cùng event và cố ghi/thu tiền/gửi mail lần nữa.
~~~

### 8.1. Idempotency key

Ưu tiên một **business event ID** bất biến:

~~~json
{
  "eventId": "evt-order-created-1001-v1",
  "orderId": "ORD-1001",
  "eventType": "OrderCreated",
  "schemaVersion": 1
}
~~~

Không dùng **ReceiptHandle** làm idempotency key vì nó **thay đổi qua mỗi lượt nhận**. `MessageId` ổn định cho một lần enqueue nhưng business event có thể được publish lại thành một SQS message mới; trong trường hợp đó **eventId** của nghiệp vụ thường phù hợp hơn.

### 8.2. Conditional write / inbox

Một cách phổ biến là lưu dấu sự kiện đã xử lý trong **DynamoDB** hoặc bảng SQL với **unique constraint**:

~~~text
processed_events
  event_id (primary/unique)
  state (PROCESSING | COMPLETED)
  lease_owner
  lease_expires_at
  updated_at
~~~

Luồng khái niệm:

1. Claim `eventId` bằng conditional write hoặc transaction phù hợp.
2. Nếu đã `COMPLETED`, bỏ qua side effect và xóa message bằng receipt handle hiện tại.
3. Nếu một worker đang `PROCESSING` nhưng lease còn hiệu lực, tránh chạy trùng; quyết định retry/visibility theo policy.
4. Thực hiện các thao tác nghiệp vụ có thể retry, với **unique business keys** ở hệ thống đích.
5. Commit trạng thái `COMPLETED` chỉ khi side effects đã bền vững theo quy tắc nghiệp vụ.
6. `DeleteMessage` sau đó.

**Thận trọng:** Chỉ tạo record `PROCESSING` rồi bỏ qua mọi lần nhận sau **có thể làm mất việc xử lý** nếu worker chết giữa chừng. Cần **lease hết hạn, takeover an toàn và recovery**. Nếu có side effects ở nhiều hệ thống không chung transaction (DB, email, thanh toán), cần thiết kế outbox, idempotency ở bên nhận và các bước bù trừ.

### 8.3. Không có transaction nguyên tử giữa SQS Delete và DB commit

`DeleteMessage` không nằm trong cùng ACID transaction với PostgreSQL/DynamoDB. Bạn không thể bảo đảm exactly-once business side effect chỉ bằng cách gọi `DeleteMessage` “đúng lúc”.

**Mục tiêu thực tế:** *At-least-once delivery + idempotent processing* tạo hành vi **effectively once** cho một nghiệp vụ được thiết kế đúng, không có nghĩa hạ tầng bảo đảm mỗi lần handler chỉ chạy đúng một lần.

## 9. Long polling: chờ message thay vì hỏi liên tục

SQS có hai cách polling qua `ReceiveMessage`:

| Đặc tính | **Short polling** | **Long polling** |
| --- | --- | --- |
| `WaitTimeSeconds` | **0** | **1–20 giây** |
| Cách truy vấn | Lấy mẫu một phần máy chủ SQS | Xem trên các server theo cơ chế long poll |
| Khi queue trống | Trả về ngay với danh sách rỗng | Đợi tới khi có message hoặc hết thời gian |
| Khi ít message | Có thể có **false empty response** | Giảm false empty và empty responses |
| Số API calls khi idle | Có thể rất nhiều nếu loop liên tục | Thường giảm đáng kể |
| Latency nhận message mới | Phụ thuộc polling frequency | Có thể trả ngay khi message đến, không phải luôn đợi đủ 20 giây |
| Chi phí request | Có thể cao khi poll quá thường xuyên | Thường tiết kiệm khi workload thưa |
| Timeout client | Thời gian chờ ngắn | **HTTP read/response timeout phải dài hơn WaitTimeSeconds** |

**Điểm chính:** Long polling **không làm message trở nên vô hình**; visibility timeout mới áp dụng **sau khi message được nhận**. `WaitTimeSeconds=20` không có nghĩa consumer được phép xử lý chỉ trong 20 giây.

### 9.1. Tại sao có “false empty”?

Short polling lấy mẫu một phần storage servers. Một lượt `ReceiveMessage` có thể không tìm được message trên những server được kiểm tra, dù queue thực tế còn message có thể nhận. Long polling giảm tình trạng này nhưng không biến API thành một snapshot nhất quán tức thời của toàn queue.

**Không xóa queue hoặc tuyên bố backlog bằng 0 chỉ vì một lần ReceiveMessage trả danh sách rỗng.** Cần xem metrics xấp xỉ, in-flight, delayed, FIFO group blocking và thời gian retention.

### 9.2. Tại sao thường chọn 20 giây?

AWS thường khuyến nghị long polling tối đa **20 giây** khi yêu cầu không có lý do phải ngắn hơn. Nếu queue thường ít message, thay vì gửi hàng chục nghìn empty receives, consumer giữ một request chờ tới khi có việc.

Ví dụ **mang tính minh họa** cho một queue liên tục rỗng:

\[
\text{Short poll mỗi giây} = 86{,}400\ \text{requests/ngày}
\]

\[
\text{Long poll 20 giây} = 4{,}320\ \text{requests/ngày}
\]

Lý thuyết giảm \(\approx95\%\) số receive requests khi **hoàn toàn không có message**, bỏ qua network overhead/reconnect/retries. Khi messages xuất hiện liên tục, long polls có thể trả sớm và số request khác đi. Chi phí còn phụ thuộc pricing theo Region và yêu cầu billing của SQS.

### 9.3. Một request đợi không chặn mọi queue khác

Nếu consumer dùng một thread để long poll lần lượt **queue A, queue B**, một lượt đợi 20 giây ở queue A có thể làm nhận message queue B chậm. Có thể dùng **mỗi queue một polling worker** hoặc async clients, với backpressure/connection pool phù hợp.

## 10. Cấu hình long polling ở queue hay từng ReceiveMessage

Có hai cách:

1. **Queue-level** `ReceiveMessageWaitTimeSeconds`: áp dụng mặc định cho các lượt receive không chỉ định `WaitTimeSeconds`.
2. **Per-request** `ReceiveMessage.WaitTimeSeconds`: override cho lần gọi cụ thể.

| Cấu hình | Ví dụ | Hành vi |
| --- | --- | --- |
| Queue wait = 0, receive không đặt wait | `0` | Short polling |
| Queue wait = 20, receive không đặt wait | `20` | Long polling tới 20 giây |
| Queue wait = 20, receive đặt wait = 5 | `5` | Long polling tới 5 giây |
| Queue wait = 20, receive đặt wait = 0 | `0` | Short polling cho lần gọi này |
| Receive wait = 30 | Không hợp lệ | Vượt giới hạn 20 giây |

### Chọn timeout của HTTP client

Nếu `WaitTimeSeconds=20`, cần để **HTTP response/socket timeout > 20 giây**, có dự phòng cho network/service latency. Nếu HTTP client timeout đúng 10 giây, long poll có thể bị phía client hủy trước khi SQS trả kết quả.

Phân biệt:

- **`WaitTimeSeconds`**: SQS chờ một message mới xuất hiện.
- **HTTP read timeout**: client chịu chờ response tới khi nào.
- **VisibilityTimeout**: sau khi nhận được message, nó bị ẩn bao lâu.
- **Lambda timeout**: handler Lambda chạy tối đa bao lâu.

**Bốn timeout này phục vụ bốn mục tiêu khác nhau**; không dùng một biến `timeout=30` để cấu hình tất cả.

## 11. Message batching, in-flight quota và backpressure

Một lần `ReceiveMessage` yêu cầu `MaxNumberOfMessages` từ 1 đến **10**. SQS **có thể trả ít hơn** số đã yêu cầu.

### Thiết kế batch theo capacity thực

Một worker chỉ có thể chạy 2 jobs đồng thời mà lại prefetch 10 messages sẽ làm 8 messages còn lại nằm trong in-flight state, bị ẩn khỏi các workers khác mà chưa xử lý. Nếu job dài, visibility của 8 messages có thể hết trong hàng chờ nội bộ.

**Nên:**

- Giới hạn số messages nhận theo **free worker slots**;
- dùng bounded queue/semaphore, không nhận vô hạn rồi xếp hàng local;
- định thời gian visibility theo processing + waiting;
- xóa **từng message khi hoàn tất**, hoặc dùng batch delete nhưng phải xử lý partial failure;
- đo `ApproximateNumberOfMessagesNotVisible` và worker utilization.

### In-flight quota

Với standard SQS queue, ngưỡng in-flight thường **xấp xỉ 120.000 messages**, phụ thuộc quota/traffic. Khi đạt ngưỡng:

- **Short polling** có thể nhận lỗi `OverLimit`.
- **Long polling** thường **không báo OverLimit**, nhưng không trả message mới cho tới khi số in-flight giảm.

Với FIFO, giới hạn/đặc tính cũng phụ thuộc quota và **active message groups**. Không đoán “queue rỗng” khi long polling trả trống nhưng `NotVisible` đang cao.

**Cách cải thiện:** Giảm prefetch, xóa sau commit, sửa worker treo, kiểm soát visibility/heartbeat, tách queue nếu bài toán cần và xem xét quota khi có căn cứ.

### DeleteMessageBatch có thể thành công một phần

`DeleteMessageBatch` nhận tối đa **10 entries**. Response batch có thể có **`Successful` và `Failed` cùng lúc**, kể cả khi HTTP request thành công. Code cần đối chiếu ID của từng entry, retry những handle thất bại hợp lệ và tránh coi “HTTP 200” là tất cả messages đã ack.

**Không nên trì hoãn xóa tất cả 10 messages tới khi job dài nhất xong** nếu các message độc lập và đã hoàn tất trước đó.

## 12. FIFO, MessageGroupId và visibility timeout

**Standard queue** cung cấp throughput linh hoạt và mô hình at-least-once; không bảo đảm thứ tự message chặt chẽ. **FIFO queue** hỗ trợ thứ tự theo **`MessageGroupId`** và deduplication của **lần gửi**.

Ví dụ:

~~~text
FIFO queue: orders-events.fifo

Message group ORD-1001:
  M1 = OrderCreated
  M2 = PaymentCaptured
  M3 = InvoiceRequested

Message group ORD-1002:
  N1 = OrderCreated
  N2 = PaymentCaptured
~~~

Nếu `M1` của group ORD-1001 đang in-flight, SQS **không trả thêm messages tiếp theo của group đó cho một lượt nhận khác** cho tới khi các messages in-flight thuộc group được xóa hoặc visibility hết. Trong một **batch ReceiveMessage**, SQS vẫn có thể trả **nhiều messages của cùng group**, theo thứ tự; consumer phải xử lý chúng phù hợp, không giả định FIFO chỉ gửi một message mỗi lần.

~~~mermaid
flowchart TB
    Q[(FIFO queue)] --> G1[Group ORD-1001]
    Q --> G2[Group ORD-1002]
    G1 --> A[M1 đang in-flight]
    A --> B{Đã Delete hoặc visibility hết?}
    B -->|Chưa| W[M2/M3 chờ trong group]
    B -->|Rồi| C[Group có thể tiếp tục]
    G2 --> D[N1/N2 có thể xử lý song song với group 1]
~~~

**Hệ quả performance:** Một group có message xử lý lâu sẽ chặn tiến độ của chính group đó. Nếu tất cả sự kiện dùng **một MessageGroupId**, hệ thống khó tăng throughput bằng cách thêm nhiều consumers. Cần chọn group key theo trật tự thật sự cần bảo đảm (ví dụ `orderId`, `accountId`) và biết giới hạn concurrency theo nhóm.

### FIFO deduplication != exactly-once business side effect

FIFO dùng **`MessageDeduplicationId`** hoặc **content-based deduplication** theo cửa sổ khoảng **5 phút**. Điều này giảm khả năng gửi trùng message vào queue khi producer retry. Nó **không thay idempotency consumer**, vì:

- Consumer có thể chết sau khi commit nhưng trước khi delete;
- Visibility có thể hết, message được giao lại;
- Một business event có thể được phát lại ngoài cửa sổ dedup 5 phút;
- Nhiều side effects ở các hệ thống khác nhau không nằm trong một transaction.

Tuy AWS mô tả FIFO bằng những thuật ngữ bảo đảm giao nhận mạnh hơn standard, **đúng một lần nghiệp vụ** vẫn phải được thiết kế ở tầng dữ liệu.

## 13. Dead-letter queue: không retry mãi một poison message

Một **dead-letter queue (DLQ)** lưu messages đã bị nhận nhưng không xử lý thành công đủ số lần theo **redrive policy** của source queue.

Ví dụ:

~~~text
Source queue: orders-work-lab
DLQ: orders-work-dlq-lab
maxReceiveCount: 5

Mỗi lần message được nhận mà không xóa:
  visibility hết → message có thể bị nhận lại.
Khi đạt ngưỡng redrive theo SQS:
  SQS chuyển message sang DLQ để phân tích.
~~~

### Vì sao cần DLQ?

- Message sai schema vĩnh viễn (`quantity="abc"`).
- Số phiên bản consumer không tương thích với payload cũ.
- Hệ thống bên ngoài từ chối dữ liệu do lỗi business, không thể retry mãi.
- Dependency liên tục lỗi vượt chính sách retry.

DLQ cho phép vận hành tiếp tục **mà không xóa message lỗi khỏi hệ thống quan sát**. Nhưng cần có **alarm, owner, runbook và quy trình re-drive**; DLQ im lặng trong nhiều tuần vẫn là thất bại vận hành.

### maxReceiveCount và retention

| Cấu hình | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `maxReceiveCount` | Ngưỡng số lần consumer nhận trước khi SQS chuyển sang DLQ theo redrive | Quá thấp dễ gửi DLQ khi lỗi transient; với Lambda thường bắt đầu từ ≥5 theo AWS guidance |
| Source retention | Thời gian tối đa ở source queue | Không đồng nghĩa retry budget |
| DLQ retention | Thời gian lưu tại DLQ | Thường đặt **lớn hơn source retention** với standard queue |
| Redrive allow policy | Queue nào có quyền dùng DLQ | Tránh nguồn không được phép đẩy messages |
| DLQ type | Standard ↔ standard, FIFO ↔ FIFO | Phải phù hợp queue type |

**Nuance retention:** Với **standard queue**, tuổi message ở DLQ vẫn chịu **thời điểm enqueue ban đầu** khi xét retention; nên chọn DLQ retention lớn hơn nguồn. Với **FIFO**, enqueue timestamp được reset khi chuyển DLQ. **Đừng dựa một mình vào metric `ApproximateAgeOfOldestMessage` của DLQ để suy tuổi dữ liệu gốc**.

### FIFO với DLQ có thể ảnh hưởng thứ tự nghiệp vụ

Nếu một message quan trọng bị chuyển ra DLQ để các message sau tiếp tục, thứ tự end-to-end của workflow có thể không còn ý nghĩa nghiệp vụ mong muốn. Với các giao dịch đòi **đúng thứ tự tuyệt đối**, phải thiết kế cách xử lý lỗi chặn, bù trừ, quarantine cả group hoặc thủ tục re-drive có kiểm soát.

## 14. SNS fanout đến SQS: acknowledgment thuộc lớp nào?

**Amazon SNS topic** có thể gửi một notification đến nhiều subscriptions: SQS queues, Lambda, HTTP endpoints hoặc hình thức hỗ trợ khác.

~~~mermaid
flowchart TD
    OrderAPI[Order API] --> SNS[(SNS topic: order-events)]
    SNS --> Q1[(SQS invoice queue)]
    SNS --> Q2[(SQS analytics queue)]
    SNS --> Q3[(SQS email queue)]
    Q1 --> W1[Invoice worker]
    Q2 --> W2[Analytics worker]
    Q3 --> W3[Email worker]
    W1 -->|DeleteMessage sau commit| Q1
    W2 -->|DeleteMessage sau commit| Q2
    W3 -->|DeleteMessage sau commit| Q3
~~~

Mỗi SQS queue có **visibility, polling, DLQ và DeleteMessage độc lập**. Invoice worker xóa message ở queue invoice **không xác nhận hoặc xóa** bản sao nằm trong queue analytics/email.

Phân biệt:

- **SNS publish acknowledgment:** SNS xác nhận request publish theo API/return, không chứng minh mỗi consumer đã hoàn tất nghiệp vụ.
- **SNS delivery/retry:** SNS có delivery policy theo loại subscription, khác thời gian visibility của queue.
- **Subscription confirmation:** Một số loại endpoint cần xác nhận subscription; thao tác này **không phải ack cho từng notification**.
- **SQS consumer acknowledgement:** `DeleteMessage` bằng receipt handle sau khi xử lý bền vững.

Khi fanout SNS vào SQS, cần **queue resource policy** cho phép principal SNS gửi message, thường ràng buộc `aws:SourceArn` vào topic ARN cụ thể. Cẩn thận **SNS envelope vs raw message delivery**: nếu không bật raw delivery, SQS body có thể chứa JSON envelope SNS, không chỉ JSON nghiệp vụ gốc.

## 15. SQS consumer trên EC2/ECS/EKS và Lambda: khác ai quản lý ack?

| Consumer model | Ai thực hiện ReceiveMessage? | Ai gọi DeleteMessage? | Nên lưu ý |
| --- | --- | --- | --- |
| **Ứng dụng Java trên EC2** | Ứng dụng dùng AWS SDK | Ứng dụng sau commit | IAM instance role, shutdown/heartbeat |
| **ECS task/worker** | Code trong container | Code trong container | ECS task role, task draining, autoscale |
| **EKS Pod** | Code trong Pod | Code trong Pod | Pod Identity/IRSA, node termination, visibility |
| **AWS Lambda SQS event source mapping** | **Lambda service poller** | **Lambda tự xóa batch messages khi xử lý thành công**, hoặc theo cơ chế partial batch | Batch semantics, visibility >= Lambda timeout |
| **Một thư viện client có auto-ack/auto-delete riêng** | SDK/framework theo cấu hình | Có thể tự động | Phải kiểm tra **thời điểm auto-delete**, không giả định mọi SDK giống nhau |

**Điểm dễ nhầm:** Nếu Lambda được trigger **trực tiếp từ SQS qua event source mapping**, handler **không cần tự polling SQS**. Nó nhận event đã gồm `Records`; Lambda quản lý việc poll/batch và xóa message theo success/failure. Với consumer Java chạy ECS/EC2, chính code phải thực hiện receive và delete.

Tuy một số SDK/framework hỗ trợ auto-delete, **mô hình SQS API nền tảng vẫn là receive → xử lý → delete**; đừng lấy tiện ích thư viện làm bảo đảm giao dịch nguyên tử.

## 16. Thực hành CLI: tạo queue và kiểm tra attributes

> **Lab có thể phát sinh chi phí SQS requests, CloudWatch Logs, KMS hoặc tài nguyên worker.** Chỉ tạo queues trong account được phép, gắn tags và dọn sau khi đã xác minh không còn message cần giữ. Không purge hoặc delete queue production để làm demo. Sử dụng AWS CLI v2 và AWS profile/role tạm thời.

### 16.1. Kiểm tra AWS identity

~~~bash
aws sts get-caller-identity --profile lab

aws configure get region --profile lab
~~~

Trong ví dụ, sử dụng Region **`ap-southeast-1`** và account giả định **`111122223333`**. Hãy thay cho đúng của người thực hành.

### 16.2. Tạo standard source queue

~~~bash
aws sqs create-queue \
  --queue-name orders-work-lab \
  --attributes VisibilityTimeout=60,ReceiveMessageWaitTimeSeconds=20,MessageRetentionPeriod=345600 \
  --region ap-southeast-1 \
  --profile lab
~~~

Giải thích:

- `VisibilityTimeout=60`: 60 giây sau khi message được nhận.
- `ReceiveMessageWaitTimeSeconds=20`: long polling mặc định 20 giây.
- `MessageRetentionPeriod=345600`: 4 ngày tính bằng giây.

Lệnh `create-queue` trả **QueueUrl**. Mẫu:

~~~text
https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab
~~~

### 16.3. Đọc cấu hình queue

~~~bash
aws sqs get-queue-url \
  --queue-name orders-work-lab \
  --region ap-southeast-1 \
  --profile lab

aws sqs get-queue-attributes \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --attribute-names VisibilityTimeout ReceiveMessageWaitTimeSeconds MessageRetentionPeriod ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --region ap-southeast-1 \
  --profile lab
~~~

**Lưu ý:** `ApproximateNumberOfMessages` từ SQS queue API và `ApproximateNumberOfMessagesVisible` trong CloudWatch là các biểu diễn liên quan nhưng **khác tên**, và đều là các giá trị xấp xỉ. Không lấy con số đơn lẻ làm nguồn đếm nghiệp vụ tuyệt đối.

### 16.4. Thay đổi queue-level defaults

~~~bash
aws sqs set-queue-attributes \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --attributes VisibilityTimeout=90,ReceiveMessageWaitTimeSeconds=20 \
  --region ap-southeast-1 \
  --profile lab
~~~

Ví dụ đổi default queue visibility từ 60 thành 90 giây. Việc thay đổi các thuộc tính queue có thể cần một khoảng thời gian để lan truyền theo quy tắc AWS; luôn đọc lại và kiểm tra thực nghiệm. **Per-message visibility đang active không nên được hiểu tự động kéo dài chỉ vì queue attribute đổi**.

## 17. Thực hành CLI: send, receive, delete và chứng minh acknowledgment

### 17.1. Gửi message

~~~bash
aws sqs send-message \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --message-body '{"eventId":"evt-1001","orderId":"ORD-1001","eventType":"OrderCreated"}' \
  --region ap-southeast-1 \
  --profile lab
~~~

Phản hồi có `MessageId` và các giá trị xác nhận theo API. **MessageId không dùng để DeleteMessage**.

### 17.2. Long poll và nhận ReceiptHandle

~~~bash
aws sqs receive-message \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --max-number-of-messages 1 \
  --wait-time-seconds 20 \
  --visibility-timeout 60 \
  --message-system-attribute-names ApproximateReceiveCount SentTimestamp \
  --region ap-southeast-1 \
  --profile lab
~~~

Kết quả minh họa (receipt handle dưới đây chỉ là placeholder):

~~~json
{
  "Messages": [
    {
      "MessageId": "message-id-example",
      "ReceiptHandle": "ACTUAL_HANDLE_RETURNED_BY_RECEIVE",
      "Body": "{\"eventId\":\"evt-1001\",\"orderId\":\"ORD-1001\",\"eventType\":\"OrderCreated\"}",
      "Attributes": {
        "ApproximateReceiveCount": "1",
        "SentTimestamp": "1795143600000"
      }
    }
  ]
}
~~~

**Đặt `--visibility-timeout 60`** trong receive override default queue visibility cho **messages trả về lần này**. Nếu queue đang có một consumer khác, bạn có thể không nhận đúng message vừa gửi vì SQS có thể phân phối nó cho consumer khác.

### 17.3. Thử nhận ngay lần nữa

Trong khoảng 60 giây sau lần nhận đầu, chạy cùng lệnh receive lần nữa (bỏ `--visibility-timeout` nếu chỉ muốn kiểm tra queue default). Nếu không còn message nào khác, thường nhận **danh sách trống hoặc không có trường Messages** sau thời gian long polling.

Điều này không chứng minh message đã bị xóa; nó vẫn nằm **in-flight**. Sau khi visibility hết mà **chưa delete**, lần receive tiếp theo có thể trả **cùng MessageId nhưng một ReceiptHandle mới** và ApproximateReceiveCount tăng.

### 17.4. Acknowledge sau khi xử lý xong

Chỉ khi đã giả lập xử lý và xác nhận thành công, dùng receipt handle **mới nhất**:

~~~bash
aws sqs delete-message \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --receipt-handle "ACTUAL_HANDLE_FROM_LATEST_RECEIVE" \
  --region ap-southeast-1 \
  --profile lab
~~~

**Không chạy literal placeholder** `ACTUAL_HANDLE_FROM_LATEST_RECEIVE`. Hãy copy giá trị `ReceiptHandle` thật từ kết quả receive gần nhất, không copy `MessageId`.

### 17.5. Chứng minh lỗi khi quên xóa

Gửi một message test thứ hai, nhận với visibility 10 giây, **không gọi delete**, rồi nhận lại sau khi timeout. Cùng một business event có thể trở lại; đây chính là cơ chế retry khi consumer chết.

**Không chạy lab này trên queue production**: nếu đang có worker khác, bạn có thể làm tăng retry/DLQ không mong muốn.

## 18. Thực hành CLI: gia hạn hoặc thả message sớm

### 18.1. Gia hạn khi xử lý lâu

Giả sử bạn vừa nhận message và còn thời gian visibility:

~~~bash
aws sqs change-message-visibility \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --receipt-handle "ACTUAL_HANDLE_FROM_LATEST_RECEIVE" \
  --visibility-timeout 120 \
  --region ap-southeast-1 \
  --profile lab
~~~

Từ thời điểm gọi, SQS đặt khoảng ẩn mới **120 giây**, trong giới hạn tối đa kể từ lần nhận ban đầu. Đọc lại điều kiện timer qua hành vi nhận message và logs; API **không phải lệnh xem được số giây visibility còn lại**.

### 18.2. Thả message sớm

~~~bash
aws sqs change-message-visibility \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --receipt-handle "ACTUAL_HANDLE_FROM_LATEST_RECEIVE" \
  --visibility-timeout 0 \
  --region ap-southeast-1 \
  --profile lab
~~~

Consumer khác có thể nhận lại message ngay (theo điều kiện queue). `visibility=0` giống **release/NACK-with-immediate-requeue theo ý nghĩa thiết kế**, nhưng không phải một API `NackMessage` chính thức, và không chứa thông tin lý do lỗi. Nếu cần lý do, hãy ghi log/metric hoặc cập nhật trạng thái nghiệp vụ trong hệ thống quan sát.

### 18.3. Cần chờ vài giây trước khi tái thử?

`ChangeMessageVisibility` có thể đặt một thời gian dương nhỏ như 10 giây để trì hoãn lượt nhận tiếp theo trong **lần xử lý đang có**. Nhưng SQS **không phải delayed job scheduler tùy ý vượt 12 giờ**. Với delayed workflows phức tạp, đánh giá **EventBridge Scheduler**, Step Functions hoặc kỹ thuật requeue có kiểm soát theo idempotency.

## 19. Java SDK v2: long polling và manual acknowledgment

Ví dụ worker Java chạy độc lập trên **EC2/ECS/EKS**. Giả sử project dùng Maven/Gradle với dependency AWS SDK for Java v2 module `software.amazon.awssdk:sqs` và BOM đã được nhóm kiểm chứng.

### Code mẫu một message mỗi lần

~~~java
package com.example.worker;

import java.util.Objects;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageResponse;

public final class OrderSqsConsumer {

    public static void main(String[] args) {
        String queueUrl = Objects.requireNonNull(
            System.getenv("ORDERS_QUEUE_URL"),
            "ORDERS_QUEUE_URL is required"
        );

        try (SqsClient sqs = SqsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            while (!Thread.currentThread().isInterrupted()) {
                ReceiveMessageRequest receive = ReceiveMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .maxNumberOfMessages(1)
                    .waitTimeSeconds(20)
                    .visibilityTimeout(90)
                    .build();

                ReceiveMessageResponse result = sqs.receiveMessage(receive);

                for (Message message : result.messages()) {
                    try {
                        processOrderIdempotently(message.body());

                        // Ack chỉ sau khi side effect/commit đã thành công.
                        sqs.deleteMessage(DeleteMessageRequest.builder()
                            .queueUrl(queueUrl)
                            .receiptHandle(message.receiptHandle())
                            .build());

                        System.out.println("Acknowledged: " + message.messageId());
                    } catch (Exception error) {
                        System.err.println(
                            "Processing failed for message "
                            + message.messageId()
                            + ", reason=" + error.getClass().getSimpleName()
                        );
                        // Không delete; sau visibility message có thể trở lại.
                        // Production: alert/trace/retry policy + DLQ.
                    }
                }
            }
        }
    }

    private static void processOrderIdempotently(String body) {
        // DEMO: thay bằng parse JSON + business validation + transaction,
        // inbox/idempotency key + S3/DB side effects + commit bền vững.
        // Không log raw body nếu có PII/secrets.
        System.out.println("Processing demo order event");
    }
}
~~~

**Cần điều chỉnh khi chạy thật:**

- `processOrderIdempotently` ở đây là **stub**, chỉ in log, **chưa bảo đảm idempotency**. Production phải hiện thực đúng tại DB/side effects trước khi xóa message.
- Trong lab, môi trường cần biến `ORDERS_QUEUE_URL`, IAM identity hợp lệ, quyền `sqs:ReceiveMessage`/`DeleteMessage`, và đường mạng tới SQS endpoint.
- Một lần receive lấy **1 message** nên không để nhiều messages chờ trong bộ đệm nội bộ; tăng batch/concurrency chỉ sau khi đo.
- `visibilityTimeout(90)` chỉ hợp lý nếu thời gian xử lý + delete của một message thường nhỏ hơn 90 giây. Job dài cần heartbeat.
- HTTP client của SDK phải cho phép read/response timeout **dài hơn 20 giây**; nếu config khác mặc định, điều chỉnh.
- Nếu `DeleteMessage` thất bại sau commit, message có thể đến lại; idempotency phải bao phủ cả trường hợp này.
- Nên thêm graceful shutdown và xử lý thread interruption/SDK exceptions phù hợp trong code production.

### IAM permissions cho consumer

Identity policy minh họa gắn vào **EC2 instance role / ECS task role / EKS Pod Identity** của worker:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConsumeOrdersQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-work-lab"
    }
  ]
}
~~~

**Không gắn policy `sqs:*` cho mọi queues** chỉ để xử lý lỗi. Producer chỉ cần quyền như `sqs:SendMessage`; consumer không tự động cần send. Nếu queue dùng **SSE-KMS customer managed key**, phải xem thêm KMS permissions/key policy của consumer và cấu hình queue tương ứng.

## 20. Heartbeat worker Java: thiết kế an toàn

Code Java ở mục trước phù hợp job ngắn. Với job dài, cần **heartbeat chạy song song** để gia hạn visibility trước khi hết. Một thiết kế gọn:

~~~text
receive = SQS.ReceiveMessage(wait=20s, visibility=120s)
handle = receive.ReceiptHandle
startedAt = now
heartbeatInterval = 60s
maxJobTime = 45min

start heartbeat:
    mỗi 60 giây:
        nếu job vẫn đang chạy và có tiến triển
           và thời gian xử lý chưa vượt maxJobTime:
              SQS.ChangeMessageVisibility(handle, 120s)
        nếu mất ownership, handle hết hiệu lực,
           hoặc quá giới hạn: dừng gia hạn và cảnh báo

process:
    validate eventId
    claim idempotency lease trong DB
    thực hiện công việc với timeout/retry
    commit trạng thái bền vững
    stop heartbeat
    SQS.DeleteMessage(handle)

on failure:
    stop heartbeat
    không delete
    log/metric và để message được retry/DLQ
~~~

**Đây là pseudocode**, không phải thư viện heartbeat được AWS tự bật khi bạn dùng `SqsClient`. Cần quản lý thread scheduler, deadline, shutdown, lỗi `ChangeMessageVisibility`, phân biệt exception *không còn handle hợp lệ* với lỗi network tạm thời.

### Race condition quan trọng

Nếu heartbeat và delete chạy đồng thời, có thể:

1. Worker commit và gọi delete.
2. Thread heartbeat đang gửi ChangeMessageVisibility với handle đó.
3. Một call thành công, call còn lại báo lỗi hoặc đến muộn.

Giải pháp: đồng bộ trạng thái `PROCESSING → COMMITTED → ACKNOWLEDGED`, **dừng heartbeat trước delete**, không cho heartbeat gia hạn sau khi job bị cancel/ownership không còn. Có fencing/idempotency ở DB khi cần ngăn worker cũ ghi sau lease hết hạn.

**Không gia hạn tới hết 12 giờ rồi tiếp tục vô hạn.** Nếu công việc quá dài, chia job, checkpoint vào DB/S3 hoặc dùng Step Functions/ECS Batch phù hợp.

## 21. Lambda trigger từ SQS: acknowledgment tự động khác thế nào?

Với **AWS Lambda event source mapping (ESM)**, Lambda service **poll SQS**, gom một batch messages và invoke function. Bạn viết handler nhận event gồm `Records`, **không tự gọi ReceiveMessage** trong handler này.

~~~mermaid
sequenceDiagram
    participant Q as SQS Queue
    participant ESM as Lambda event source mapping
    participant F as Java Lambda handler
    ESM->>Q: ReceiveMessage (poll)
    Q-->>ESM: Batch [M1, M2, ...] + receipt handles
    ESM->>F: Invoke batch event
    alt Handler trả success hợp lệ
      F-->>ESM: Success
      ESM->>Q: Delete messages trong batch
    else Handler throw error / failed batch
      F-->>ESM: Error
      Note over Q: Visibility hết, records có thể nhận lại
    end
~~~

### 21.1. Visibility timeout khi dùng Lambda

AWS hướng dẫn:

- **Queue visibility timeout phải ≥ timeout của Lambda function**; AWS Lambda xác thực điều kiện này khi tạo/cập nhật ESM.
- **Khuyến nghị** visibility timeout của source queue **ít nhất khoảng 6 lần function timeout** để có thời gian cho retry trong tình huống throttling.
- Nếu ESM có **batching window**, AWS khuyến nghị tính thêm khoảng window vào visibility:

\[
V_{\text{queue}} \gtrsim 6 \times T_{\text{Lambda timeout}} + T_{\text{batching window}}
\]

Đây là **guidance cho ESM**, không phải công thức thay thế hoàn toàn SLO/processing time. Ví dụ Lambda timeout 30 giây, batching window 5 giây → chọn visibility khoảng **185 giây hoặc hơn** và kiểm tra các điều kiện dịch vụ. Hãy xem tối đa 12 giờ và retention/DLQ.

### 21.2. Vì sao Lambda batch bị retry toàn bộ?

Giả sử batch có 5 records: M1, M2, M3, M4, M5. Handler xử lý M1–M4 xong, nhưng throw exception ở M5.

**Mặc định**, Lambda coi **cả invocation/batch thất bại**. Sau visibility timeout, các messages trong batch có thể visible lại, dẫn đến M1–M4 cũng được xử lý lại. Vì vậy mọi handler dùng SQS cần **idempotency**, kể cả khi dữ liệu có vẻ chỉ xuất hiện một lần.

### 21.3. Khi nào nên tự DeleteMessage trong Lambda?

AWS hỗ trợ một số phương án xóa từng record thành công trong handler, nhưng **không phải mặc định cần tự xóa** khi dùng ESM. Với đa số workload, nên dùng **ESM batch acknowledgment** hoặc **partial batch response** để tránh code phải tự quản lý receipts/permissions ngoài luồng chuẩn.

## 22. Lambda partial batch failure: tránh retry records đã thành công

Bật tính năng **`ReportBatchItemFailures`** trên ESM. Handler trả một danh sách **message IDs thất bại**, không trả receipt handles.

Ví dụ với batch M1–M5, M2/M4 thất bại:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "M2"},
    {"itemIdentifier": "M4"}
  ]
}
~~~

Lambda coi các records **không nằm trong danh sách lỗi** là thành công và quản lý việc xóa chúng; records lỗi được xử lý lại theo cơ chế SQS khi visibility hết.

**Điểm rất quan trọng:**

- Nếu handler **throw exception** ra ngoài, Lambda vẫn coi **toàn bộ batch thất bại** dù bạn đã xử lý một phần.
- Nếu trả sai format hoặc itemIdentifier không thuộc batch, cả batch có thể bị coi thất bại.
- Nếu service trả **empty `batchItemFailures`**, Lambda coi batch thành công; đừng trả empty khi thực tế đã có records lỗi.
- Với **FIFO**, cần dừng xử lý sau lỗi đầu tiên và đánh dấu **cả messages thất bại lẫn chưa xử lý** là failed để bảo toàn thứ tự.

### Java Lambda handler minh họa

Project cần `aws-lambda-java-core` và `aws-lambda-java-events` tương thích để dùng `SQSEvent`:

~~~java
package com.example.lambda;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;

public final class OrderBatchHandler
    implements RequestHandler<SQSEvent, Map<String, Object>> {

    @Override
    public Map<String, Object> handleRequest(
        SQSEvent event, Context context) {

        List<Map<String, String>> failures = new ArrayList<>();

        for (SQSEvent.SQSMessage msg : event.getRecords()) {
            try {
                processIdempotently(msg.getBody());
            } catch (Exception ex) {
                context.getLogger().log(
                    "Failed messageId=" + msg.getMessageId());
                failures.add(Map.of(
                    "itemIdentifier", msg.getMessageId()
                ));
            }
        }

        return Map.of("batchItemFailures", failures);
    }

    private void processIdempotently(String jsonBody) {
        // Production: parse/validate, durable idempotency + side effects.
        // Stub để người học thay bằng code nghiệp vụ thật.
    }
}
~~~

**Với FIFO**, ví dụ trên cần sửa để **dừng sau lỗi đầu tiên** và đưa **mọi messages còn lại chưa xử lý** vào `batchItemFailures`; nếu tiếp tục xử lý một số records sau record thất bại, bạn có thể vi phạm business ordering. Có thể dùng **AWS Lambda Powertools Batch Processor for Java** để giảm lỗi thao tác từng record.

### Bật ReportBatchItemFailures bằng AWS CLI

~~~bash
aws lambda update-event-source-mapping \
  --uuid "a1b2c3d4-5678-90ab-cdef-11111example111" \
  --function-response-types ReportBatchItemFailures \
  --region ap-southeast-1 \
  --profile lab
~~~

`UUID` chỉ là ví dụ; lấy mapping thật bằng `aws lambda list-event-source-mappings`, xác nhận đúng function/queue trước khi sửa. Thay đổi failure behavior có thể ảnh hưởng retry/chi phí, cần kiểm thử failure một record và theo dõi DLQ.

## 23. IAM, KMS, network và bảo mật khi polling

### 23.1. Principal cần những quyền nào?

| Principal | Quyền thường gặp | Điều kiện thêm |
| --- | --- | --- |
| **Producer** | `sqs:SendMessage` | Queue resource policy/cross-account, KMS khi dùng SSE-KMS |
| **Manual consumer** | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `sqs:GetQueueAttributes` khi cần | IAM role, resource policy, KMS Decrypt nếu phù hợp |
| **Lambda SQS consumer** | Execution role có quyền đọc/xóa SQS và CloudWatch Logs | ESM configuration, queue policy, KMS Decrypt cho encrypted queue theo loại khóa |
| **SNS fanout producer** | Queue policy `sqs:SendMessage` cho SNS service | `aws:SourceArn` topic, policy cross-account/KMS |
| **Quản trị DLQ/redrive** | `sqs:StartMessageMoveTask` và các API/quyền liên quan theo tác vụ | Tách quyền vận hành với quyền app, review trước re-drive |

**Encryption:** SQS hỗ trợ mã hóa phía server bằng cơ chế SQS-managed hoặc AWS KMS theo cấu hình. Nếu dùng customer managed KMS key, principal liên quan cần quyền KMS phù hợp; **mã hóa at rest không thay quyền SQS**. Khi SNS → SQS encrypted queue, cần xem chính sách khóa KMS cho **SNS service principal** theo kiến trúc hỗ trợ.

### 23.2. VPC endpoints cho worker ở private subnet

Worker ECS/EC2/EKS trong private subnet muốn gọi SQS API cần:

- Kết nối đến SQS public endpoint thông qua đường outbound phù hợp **hoặc**
- **Interface VPC endpoint cho Amazon SQS** với Private DNS, SG endpoint cho inbound TLS/443 từ worker SG, endpoint policy và DNS/route đúng.

**SQS API traffic dùng HTTPS/443**, không phải TCP/2049 như EFS hay port database. Không mở inbound từ Internet vào worker để SQS gửi message; **consumer là phía chủ động gọi ReceiveMessage**.

**Lambda SQS ESM** được dịch vụ Lambda quản lý việc polling, không phải một vòng `ReceiveMessage` do code trong function VPC gửi. Function chỉ cần mạng/VPC endpoints/NAT cho **các AWS APIs mà code chủ động gọi** hoặc kết nối private DB.

### 23.3. Kiểm soát dữ liệu và policy

- Không gửi password, token, thông tin thẻ hoặc PII nhạy cảm vào message body nếu không có yêu cầu/bảo vệ phù hợp.
- Nếu body chứa ID dẫn đến dữ liệu nhạy cảm, IAM và encryption vẫn phải giới hạn theo principal/queue.
- Dùng AWS temporary credentials từ IAM instance profile/ECS task role/EKS Pod Identity/Lambda execution role thay static access keys.
- Dùng queue policy hạn chế cross-account/SNS source ARN, KMS key policy và SCP/VPC endpoint policy theo môi trường.
- Không ghi **ReceiptHandle** hoặc đầy đủ message body chứa dữ liệu nhạy cảm vào logs công khai; receipt handle là token thao tác nhận/xóa trong ngữ cảnh quyền SQS.

## 24. Monitoring: nhìn backlog, in-flight và lỗi ack cùng nhau

Amazon SQS phát nhiều metrics trong namespace **`AWS/SQS`** của CloudWatch. Các chỉ số backlog là **xấp xỉ** vì SQS là hệ thống phân tán.

| Metric | Nghĩa | Tình huống nên cảnh báo |
| --- | --- | --- |
| **`ApproximateNumberOfMessagesVisible`** | Số messages đang có thể nhận | Backlog tăng liên tục, consumer thiếu capacity |
| **`ApproximateNumberOfMessagesNotVisible`** | Số messages in-flight | Worker giữ messages quá lâu, prefetch hoặc không ack |
| **`ApproximateNumberOfMessagesDelayed`** | Messages đang bị delivery delay | Nhầm queue chưa có message vì delay |
| **`ApproximateAgeOfOldestMessage`** | Tuổi message chưa xử lý theo semantics SQS | Có nguy cơ vi phạm thời gian chờ nghiệp vụ; cần hiểu poison-pill/FIFO nuance |
| **`NumberOfMessagesReceived`** | Số messages được trả trong các receive calls | Nhận lại nhiều, không phải số unique business events |
| **`NumberOfMessagesDeleted`** | Số delete operations SQS ghi nhận | Không đồng nghĩa unique successful business transactions |
| **`NumberOfEmptyReceives`** | Calls nhận không có message | Short polling quá thường xuyên, long polling/empty behavior |
| **`NumberOfMessagesSent`** | Messages gửi vào queue qua API tương ứng | Nguồn gửi tăng, sai traffic, anomalies |
| **`ApproximateNumberOfGroupsWithInflightMessages`** (FIFO) | Số groups đang có in-flight | Backlog lớn nhưng active groups ít, giới hạn parallelism |
| **DLQ `ApproximateNumberOfMessagesVisible`** | Số messages có thể nhận từ DLQ | Bắt đầu có poison messages hoặc retries vượt ngưỡng |

### Không đọc metric sai

- `NumberOfMessagesReceived` có thể lớn hơn `NumberOfMessagesSent` vì **cùng message được nhận lại**.
- `NumberOfMessagesDeleted` đếm các delete requests hợp lệ; **không phải số eventId duy nhất được commit**.
- `ApproximateAgeOfOldestMessage` của standard queue có quy tắc đặc thù với **poison-pill messages được nhận nhiều lần**; không tự suy ra mọi lỗi từ một điểm age.
- DLQ auto-redrive không nhất thiết làm tăng `NumberOfMessagesSent` của DLQ như khi producer gửi trực tiếp; giám sát **DLQ visible count** và age.

### Alarms tối thiểu

1. **DLQ messages > 0** trong khoảng thời gian có ý nghĩa.
2. **Backlog visible** tăng liên tục hoặc vượt SLO backlog/time-to-process.
3. **Oldest message age** tăng vượt ngưỡng xử lý đơn hàng.
4. **In-flight cao** mà delete/success rate không tăng.
5. **NumberOfEmptyReceives cao** so với traffic thực, cân nhắc long polling.
6. Worker errors/timeouts/throttles, Lambda Errors/Duration/ConcurrentExecutions hoặc ECS task health.
7. Chi phí SQS/KMS/NAT/CloudWatch tăng bất thường.

**CloudWatch không tự thay application metrics**. Bổ sung `orders_processed_success`, `orders_duplicate_ignored`, `processing_duration_p99`, `delete_error_count`, `heartbeat_extensions` và `side_effect_commit_failures` từ chính worker.

## 25. Hiệu năng và chi phí: số request không phải số đơn hàng

SQS có pricing theo requests, message payload size/tier, queue type và Region; ngoài ra còn có KMS, data transfer, VPC endpoints, Lambda invocations, logs và workers. Vì thế cần theo dõi:

\[
C_{\text{approx}} \approx
C_{\text{SQS API}}
+ C_{\text{worker compute}}
+ C_{\text{KMS/requests}}
+ C_{\text{network}}
+ C_{\text{logging}}
+ C_{\text{DLQ/re-drive}}
\]

### 25.1. Batch giảm overhead nhưng tăng rủi ro in-flight

Nếu cần xử lý 1.000 events và mỗi receive trả đúng 10 messages, số `ReceiveMessage` calls tối thiểu theo ví dụ khoảng 100 thay vì 1.000. Nhưng thực tế SQS có thể trả **ít hơn requested** và batch delete có lỗi partial. Không coi số API calls là bằng 1.000/10 trong mọi trường hợp.

### 25.2. Long polling giảm empty receives

Queue thưa workload: dùng `WaitTimeSeconds=20` và timeout client đủ dài thường tiết kiệm hơn gọi receive mỗi vài trăm mili giây. Nhưng:

- Chờ 20 giây trong client thread có chi phí tài nguyên worker/connection;
- Retry quá nhanh khi HTTP timeout làm tăng request và log;
- Khi có nhiều message sẵn, long poll trả sớm, không bắt buộc đợi đủ 20 giây;
- Lambda ESM tự quản polling; đừng thêm một vòng long poll thứ hai trong handler.

### 25.3. Visibility dài hay ngắn cũng tác động chi phí

- **Quá ngắn** → duplicate processing, thêm S3/DB/API calls, DLQ/retry và năng lực worker không cần thiết.
- **Quá dài** → khi worker chết, message bị ẩn lâu, backlog/SLO xấu, có thể tăng nhu cầu worker/concurrency dự phòng.
- **Gia hạn heartbeat nhiều lần** → thêm SQS API calls, nhưng có thể đáng giá nếu tránh làm lại job dài.

**Thước đo phù hợp:** chi phí trên **một event xử lý thành công duy nhất** và độ trễ từ enqueue tới commit, thay vì chỉ nhìn số lần receive.

## 26. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hành động kiểm tra |
| --- | --- | --- |
| Message xử lý hai lần | Visibility quá ngắn, consumer crash sau commit trước delete, standard at-least-once | Theo dõi eventId, ReceiptHandle qua từng receive (ẩn giá trị nhạy cảm), DB idempotency |
| Queue có backlog nhưng ReceiveMessage trống | Short polling false empty, messages in-flight/delayed, FIFO group blocking | Wait=20, Visible/NotVisible/Delayed, FIFO group count |
| Worker không thể xóa message | Dùng MessageId thay ReceiptHandle, handle cũ, IAM deny | Copy latest ReceiptHandle, `sqs:DeleteMessage`, queue policy |
| DeleteMessage trả 200 nhưng message còn | ReceiptHandle không mới nhất, distributed duplicate, xử lý race | Idempotency + logs/metrics; dùng handle lượt nhận hiện tại |
| Message mất tạm ẩn quá lâu sau worker crash | Visibility quá dài | Đo processing, giảm default/heartbeat đúng, alarm age |
| Message cứ quay lại | Không delete sau success, handler throw, timeout, poisoned data | App logs, DLQ, receive count, commit/ack sequence |
| `ChangeMessageVisibility` báo lỗi | Handle hết hiệu lực, đã vượt thời gian tối đa còn lại, IAM deny | Thời gian từ receive, last handle, `sqs:ChangeMessageVisibility` |
| Consumer bị `OverLimit` | Quá nhiều in-flight standard messages | Giảm prefetch, xóa nhanh, kiểm tra worker treo, quota |
| Long poll im lặng dù còn nhiều messages | Chạm giới hạn in-flight; FIFO group khóa; visibility/delay | CloudWatch NotVisible/FIFO groups, status workers |
| Long poll thường bị socket/read timeout | HTTP client timeout <= WaitTimeSeconds | Timeout client > wait, SDK settings, proxy/network |
| FIFO throughput thấp dù thêm workers | Quá ít MessageGroupIds, một message chặn group | Phân tách group key phù hợp, kiểm tra ordering requirements |
| Lambda success nhưng message được xử lý lại | Batch chứa record khác thất bại, throw exception, timeout | ESM batch error, ReportBatchItemFailures, idempotency |
| Lambda mapping bị từ chối khi cấu hình | Function timeout > queue visibility | Tăng visibility, xem guidance 6x và batching window |
| Lambda không poll encrypted queue | Execution role/KMS key policy không đủ | `sqs:ReceiveMessage`, `kms:Decrypt`, queue/key policy |
| DLQ tăng nhanh | Business validation fail, schema mismatch, dependency lỗi | Sample message an toàn, classify retryable, fix source trước re-drive |
| DLQ có message bị hết hạn | DLQ retention quá ngắn; original age standard queue | Retention strategy, alarm và runbook |
| SNS fanout không tới queue | Queue policy thiếu SNS `sqs:SendMessage`, SourceArn sai, KMS policy | Subscription, SNS delivery metrics, SQS queue/KMS policies |
| Consumer trong private VPC timeout | Không có NAT/SQS interface endpoint, DNS hoặc SG endpoint sai | Route/VPC endpoint, HTTPS 443, endpoint policy |
| DB bị ghi nhiều lần từ cùng event | Thiếu idempotency/atomic constraint | Inbox/outbox, unique key, conditional write, reconciliation |

### Quy trình điều tra tuần tự

~~~text
1. Xác nhận account, Region, queue URL/ARN, standard hay FIFO.
2. Đọc queue attrs: VisibilityTimeout, ReceiveMessageWaitTimeSeconds,
   MessageRetentionPeriod, RedrivePolicy, encryption và delay.
3. Xem CloudWatch Visible, NotVisible, Delayed, OldestAge, EmptyReceives.
4. Kiểm tra worker thực: EC2/ECS/EKS/Lambda mapping, IAM, KMS và network.
5. Xem eventId, MessageId, ApproximateReceiveCount, processing duration.
6. Nếu lỗi ack: kiểm tra latest ReceiptHandle, DeleteMessage result,
   timing so với visibility, batch delete partial errors.
7. Nếu retry: phân loại transient vs permanent, DLQ maxReceiveCount,
   visibility/heartbeat, idempotency và business transaction.
8. Nếu FIFO: MessageGroupId, group blocking và thứ tự các records.
9. Sửa nguyên nhân nhỏ nhất, chạy happy-path + failure-path lab,
   theo dõi backlog/success/duplicates và lập runbook.
~~~

**Không chữa lỗi bằng cách** đặt visibility 12 giờ cho mọi message, bỏ DLQ, purge queue, mở IAM `sqs:*`/KMS `*`, hoặc disable idempotency để tăng tốc. Những biện pháp đó thường làm lỗi khó phát hiện hơn và tăng rủi ro mất dữ liệu.

## 27. Kiến trúc gợi ý theo tình huống

### A. Tạo hóa đơn sau khi nhận đơn hàng

**Yêu cầu:** Website đặt hàng nhanh, tạo PDF có thể mất 10–90 giây, hệ thống dùng S3/DynamoDB.

**Thiết kế:**

- API Gateway/Lambda hoặc ECS Order API commit đơn hàng rồi gửi `OrderCreated` qua transactional outbox/event bridge phù hợp.
- SQS standard queue `invoices`, long polling 20 giây cho ECS workers hoặc Lambda ESM.
- Visibility ban đầu khoảng p99 processing + margin; gia hạn heartbeat nếu job dài không đoán được.
- Worker ghi hóa đơn với key idempotent `invoices/{orderId}.pdf` và trạng thái DynamoDB có condition.
- Chỉ **DeleteMessage sau khi S3/DB commit thành công**; DLQ với maxReceiveCount theo retry budget.
- CloudWatch DLQ alarm, age, worker errors, S3/KMS permissions và backup/versioning.

**Bài học:** Cùng một event có thể được xử lý lại; idempotency nằm ở dữ liệu, không ở việc đặt visibility thật cao.

### B. Chuỗi sự kiện thanh toán phải theo đúng thứ tự mỗi đơn

**Yêu cầu:** `OrderCreated → PaymentCaptured → InvoiceIssued` không được đảo thứ tự trong từng đơn, nhưng đơn khác có thể chạy song song.

**Thiết kế:**

- SQS FIFO `order-events.fifo`, `MessageGroupId=orderId`.
- Producer đặt `MessageDeduplicationId` ổn định trong 5 phút khi retry gửi.
- Consumer xử lý theo thứ tự, ghi trạng thái nghiệp vụ có version/optimistic locking.
- Một message đang in-flight trong group có thể chặn những message tiếp theo; chọn visibility và retry/DLQ cẩn trọng.
- Nếu dùng Lambda batch partial failure trên FIFO, **dừng ở lỗi đầu** và trả failed/unprocessed IDs.

**Bài học:** FIFO giải quyết delivery ordering trong nhóm, không thay transaction, điều kiện chuyển trạng thái và idempotency.

### C. Fanout thông báo cho nhiều nhóm độc lập

**Yêu cầu:** Khi đơn tạo, cần cùng lúc gửi email, cập nhật BI và tạo hóa đơn.

**Thiết kế:**

- SNS topic `orders-events` fanout sang ba SQS queues riêng.
- Mỗi consumer có visibility, long polling, DLQ và retry policy theo thời gian xử lý riêng.
- Email worker ghi idempotency trước/đồng bộ với email provider để giảm gửi trùng.
- SNS topic/queue/KMS policies đúng principal, kiểm soát SourceArn.
- Không dùng một queue cho ba independent services rồi mong mọi service đều nhận được một bản sao: **SQS consumers trên một queue cạnh tranh nhận, không phải fanout**.

### D. Job cực dài hơn 12 giờ

**Yêu cầu:** Xử lý video hoặc phân tích dữ liệu nhiều giờ/ngày.

**Không phù hợp:** Giữ một SQS message in-flight vô hạn bằng heartbeat; **giới hạn tối đa 12 giờ** vẫn áp dụng.

**Thiết kế khác:** Dùng **Step Functions**, AWS Batch/ECS jobs theo khả năng workload, lưu checkpoint ở S3/DB, chia thành nhiều phần/tác vụ và phát message tiếp theo sau khi checkpoint thành công. SQS đóng vai trò kích hoạt công việc, không phải khóa chạy kéo dài vô hạn.

## 28. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1 — Tính visibility với p99 processing

Worker xử lý 99% messages trong 38 giây; commit + DeleteMessage thường mất 2 giây; cần dự phòng 20 giây.

1. Chọn visibility ban đầu theo công thức khởi đầu: **38 + 2 + 20 = 60 giây**.
2. Nếu 1% jobs mất 4 phút, giải thích vì sao cần heartbeat hoặc queue/job tách riêng.
3. Nếu worker crash ở giây 3, visibility 60 so với 10 phút làm retry chậm khác nhau thế nào?
4. Đề xuất metrics đo **trùng xử lý** và **thời gian từ enqueue tới commit**.

### Bài tập 2 — Nhận thành công nhưng không delete

Một consumer nhận `MessageId=M1`, `ReceiptHandle=H1` lúc 10:00:00, visibility 30 giây. Worker ghi DB thành công lúc 10:00:25 nhưng crash trước delete. Consumer khác nhận lúc 10:00:35, lấy `ReceiptHandle=H2`.

**Yêu cầu:** Cho biết trạng thái message tại 10:00:15, 10:00:31; giải thích H1/H2 khác nhau; thiết kế idempotency để không tạo hai hóa đơn; chỉ ra lúc nào delete an toàn.

### Bài tập 3 — Lỗi “đã xóa nhưng vẫn thấy message”

Worker A giữ handle cũ sau khi visibility hết. B nhận cùng M1 bằng handle mới; A gọi `DeleteMessage` với handle cũ được HTTP 200 nhưng message xuất hiện lại.

Hãy giải thích **DeleteMessage dùng receipt handle mới nhất**, status 200 không đủ để kết luận unique event đã xử lý, và cách dùng eventId/conditional write để đạt hiệu ứng nghiệp vụ duy nhất.

### Bài tập 4 — Long polling và chi phí

Một worker idle liên tục, mỗi giây gọi `ReceiveMessage` short poll một lần. Đề xuất long polling 20 giây và tính số calls lý thuyết/ngày:

- Short: **86.400**.
- Long idle: **4.320**.
- Chênh lệch: **82.080** calls/ngày.

Nêu giả định: không có message, không reconnect/retry; kết quả thật khác nếu queue có traffic. Cần điều chỉnh **HTTP read timeout** và theo dõi **NumberOfEmptyReceives**.

### Bài tập 5 — Lambda SQS batch

Batch có M1–M5, M3 thất bại:

1. Mặc định Lambda ESM làm gì nếu handler throw?
2. Nếu bật `ReportBatchItemFailures`, response tối thiểu cần trả là gì?
3. Với standard queue, vì sao M1/M2/M4/M5 có thể tránh retry khi partial response hợp lệ?
4. Với FIFO, vì sao handler phải dừng ở M3 và trả **M3, M4, M5** là failed/unprocessed?
5. Tại sao tất cả records vẫn cần idempotency dù đã bật partial batch failures?

### Bài tập 6 — Quá nhiều in-flight

Một ECS service có 500 workers, mỗi worker prefetch 10 messages nhưng chỉ xử lý một message đồng thời. Processing trung bình 2 phút, visibility 60 giây.

Phân tích:

- Số messages tối đa bị giữ in-flight khoảng **5.000** nếu mỗi worker đã nhận đủ 10.
- Vì sao 9 messages/worker có thể hết visibility trong hàng chờ local?
- Cách thay đổi `MaxNumberOfMessages`, worker pool, heartbeat và `DeleteMessage`.
- Metric nào cho biết in-flight cao nhưng successful throughput thấp?

### Bài tập 7 — FIFO message group

Queue FIFO có 1.000 messages nhưng **chỉ một MessageGroupId**. Tăng consumer từ 2 lên 50 mà throughput không cải thiện.

Hãy giải thích group blocking/ordering; đề xuất chia MessageGroupId theo `orderId` hoặc loại khóa phù hợp, đồng thời thảo luận những trường hợp **không được** chia nhóm vì business ordering toàn cục.

### Bài tập 8 — DLQ và retry policy

Đơn hàng có lỗi `InvalidSku` vĩnh viễn, được nhận nhiều lần rồi vào DLQ.

Hãy đặt `maxReceiveCount` theo độ tin cậy và thời gian retry cho phép; phân loại lỗi transient/permanent; lập runbook xem mẫu message an toàn, sửa dữ liệu hoặc code, rồi re-drive có kiểm soát. Giải thích vì sao **DLQ không phải nơi xóa bỏ trách nhiệm xử lý message lỗi**.

### Câu hỏi ngắn

1. **`ReceiveMessage` có xóa message không?** Không; message chuyển in-flight và được tạm ẩn.
2. **Ack API chính của SQS consumer tự polling là gì?** `DeleteMessage` bằng latest ReceiptHandle sau thành công.
3. **MessageId có dùng làm ReceiptHandle không?** Không.
4. **Visibility hết thì message bị xóa?** Không; message có thể visible để nhận lại.
5. **`WaitTimeSeconds=20` có nghĩa visibility 20 giây?** Không; đó là long polling wait.
6. **Long polling có luôn đợi đủ 20 giây?** Không; có thể trả sớm khi có message.
7. **`ChangeMessageVisibility` có kéo vô hạn không?** Không; tổng giới hạn 12 giờ từ lần nhận.
8. **Standard queue có đảm bảo không nhận trùng trong visibility?** Không tuyệt đối; cần idempotency.
9. **FIFO deduplication có thay idempotency business không?** Không.
10. **Lambda SQS ESM mặc định ai xóa messages sau batch success?** Lambda service.
11. **Batch Lambda failure mặc định ảnh hưởng records đã thành công?** Có thể retry cả batch.
12. **Một SNS topic fanout vào ba SQS queues thì worker invoice xóa message có ảnh hưởng analytics queue?** Không.
13. **DLQ tự sửa message poison không?** Không; cần điều tra/re-drive.
14. **Một lần ReceiveMessage trống chứng minh queue không còn message?** Không.

## 29. Checklist trước production

- [ ] Đã chọn **standard/FIFO** theo ordering, dedup và throughput thực; không chọn FIFO chỉ để “tránh mọi duplicate”.
- [ ] Producer phát event có **business eventId** ổn định và schema version; không lẫn eventId với ReceiptHandle.
- [ ] Có quy trình publish/transactional outbox phù hợp để tránh DB commit nhưng event bị mất.
- [ ] Consumer biết rõ **receive → xử lý → commit → delete** và retry khi delete không chắc chắn.
- [ ] Có **idempotency** bền vững, unique constraints/conditional writes và recovery khi worker chết giữa chừng.
- [ ] Visibility timeout được chọn theo processing p99 + margin, có kiểm thử long-tail jobs và crash recovery.
- [ ] Nếu cần heartbeat, gia hạn trước hạn, dừng khi xong, giới hạn job duration và không vượt 12 giờ.
- [ ] `WaitTimeSeconds` long polling có lý do; HTTP client timeout lớn hơn wait.
- [ ] Số messages prefetch không vượt thực tế processing slots; có backpressure và xử lý batch delete partial errors.
- [ ] Với FIFO, MessageGroupId đảm bảo đúng ordering domain, đủ groups để đạt desired throughput.
- [ ] Có **DLQ**, maxReceiveCount/retention, alert và runbook re-drive; dữ liệu lỗi được phân loại.
- [ ] Nếu dùng Lambda ESM, queue visibility phù hợp Lambda timeout/batch window; đã kiểm thử full/partial batch failures.
- [ ] Khi dùng SNS fanout, queue policy/KMS policy, raw-vs-envelope body và mỗi queue retry/ack độc lập được hiểu rõ.
- [ ] IAM least privilege: producer `SendMessage`, consumer `Receive/Delete/ChangeVisibility`; không mở wildcard tùy tiện.
- [ ] Các workers trong VPC có NAT hoặc **SQS interface endpoint** đúng HTTPS/443, DNS và endpoint policy.
- [ ] Có SSE-SQS hoặc SSE-KMS theo yêu cầu; quản lý KMS key policy/lifecycle và quyền consumer/producer.
- [ ] SQS metrics và application metrics/alerts có backlog visible/not visible, oldest age, empty receives, successful commits và DLQ.
- [ ] Dự toán SQS requests/batching, Lambda/ECS/EC2 compute, KMS, VPC endpoints/NAT, logs và chi phí retry.
- [ ] Diễn tập worker crash **trước commit**, **sau commit trước delete**, visibility expiry, FIFO poison message và re-drive.
- [ ] Có IaC, tags, staging/prod separation, rollback và quy trình cleanup lab không xóa dữ liệu quan trọng.

## 30. Tổng kết

**Visibility timeout, long polling và acknowledgment là ba cơ chế khác nhau nhưng phối hợp chặt chẽ:**

- **Visibility timeout** ẩn message sau khi nhận, cho consumer thời gian xử lý; hết hạn mà chưa xóa sẽ có thể nhận lại. Nó **không phải khóa bảo đảm exactly-once**.
- **Long polling** cho `ReceiveMessage` chờ đến khi có message hoặc hết thời gian tối đa 20 giây, giúp giảm empty receives và thường giảm chi phí khi queue ít tải.
- **Acknowledgment** trong SQS consumer dùng SDK/CLI là **`DeleteMessage` với ReceiptHandle mới nhất sau khi đã commit side effect**. Với **Lambda SQS event source mapping**, Lambda quản lý xóa messages theo kết quả batch/partial batch.

Khi kết hợp **DLQ, idempotency, FIFO message groups, IAM/KMS, VPC networking, CloudWatch và kiểm soát ngân sách**, một hàng đợi đơn giản có thể trở thành nền tảng xử lý sự kiện đáng tin cậy cho ứng dụng AWS chạy trên **Lambda, ECS, EC2 hoặc EKS**. Mục tiêu không phải “mỗi handler chỉ chạy đúng một lần”, mà là **mỗi hiệu ứng nghiệp vụ quan trọng được kiểm soát khi retry, xử lý đúng và có thể phục hồi khi có lỗi**.

### Tài liệu AWS chính thức

- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [ChangeMessageVisibility API](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_ChangeMessageVisibility.html)
- [DeleteMessage API và receipt handles](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_DeleteMessage.html)
- [SQS short và long polling](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-short-and-long-polling.html)
- [Best practices: setting up long polling](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/best-practices-setting-up-long-polling.html)
- [SQS best practices: processing messages in a timely manner](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/best-practices-processing-messages-timely-manner.html)
- [FIFO queue delivery logic](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-understanding-logic.html)
- [FIFO exactly-once processing/deduplication](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [SQS CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [AWS Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Configure Lambda SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Lambda SQS error handling và partial batch responses](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [AWS CLI sqs receive-message](https://docs.aws.amazon.com/cli/latest/reference/sqs/receive-message.html)
- [AWS SDK for Java v2 SQS examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sqs_code_examples.html)
- [SQS with SNS subscriptions](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-subscribe-queue-sns-topic.html)
- [SQS pricing](https://aws.amazon.com/sqs/pricing/) và [Lambda pricing](https://aws.amazon.com/lambda/pricing/)

**Lưu ý vận hành:** Pricing, AWS quotas, SDK/API parameters và hành vi tích hợp có thể thay đổi theo Region, account và thời điểm. Đối chiếu tài liệu hiện hành và kiểm chứng trên môi trường lab trước khi dùng với dữ liệu production.
