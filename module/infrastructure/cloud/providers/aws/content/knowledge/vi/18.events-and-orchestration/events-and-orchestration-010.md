# Callback task token và thiết kế saga trên AWS

Trong một hệ thống thương mại điện tử, một đơn hàng có thể cần giữ tồn kho, xác thực thanh toán, chờ nhân viên phê duyệt rủi ro, tạo vận đơn và gửi thông báo. Những hành động này diễn ra trên các dịch vụ khác nhau như **AWS Lambda, Amazon ECS, Amazon RDS, DynamoDB, SQS** hoặc cổng thanh toán bên ngoài; chúng không chia sẻ một transaction database. Nếu một bước đã commit nhưng bước sau lỗi, hệ thống không thể giả định mọi thay đổi được rollback nguyên tử.

**AWS Step Functions** cho phép mô tả các bước dưới dạng **state machine**. Với công việc phải chờ bên ngoài trả lời, **callback task token** cho phép state machine tạm dừng tại một Task cho đến khi worker gọi `SendTaskSuccess` hoặc `SendTaskFailure` bằng token đang hợp lệ. Kết hợp callback với **saga pattern** giúp điều phối các **local transactions**, retry, timeout và **compensating transactions** để khôi phục trạng thái nghiệp vụ một cách có kiểm soát.

Bài học thuộc chương **Sự kiện và điều phối**, mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung liên hệ Region/AZ, IAM, VPC, Lambda/ECS, SQS/SNS, EventBridge, DynamoDB/RDS, CloudWatch và yêu cầu chọn dịch vụ, bảo mật, giám sát, khả năng phục hồi, kiểm soát chi phí trên AWS.

> **Ba khái niệm khác nhau:** Callback token giải quyết **khi nào một Task được tiếp tục**; saga giải quyết **những gì phải bù trừ khi chuỗi giao dịch không thể hoàn tất**; business idempotency key ngăn **tác động bị thực hiện lại** khi request, callback hoặc workflow được retry.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **request-response**, **Run a Job (`.sync`)** và **Wait for Callback (`.waitForTaskToken`)**.
2. Giải thích vì sao callback token chỉ hỗ trợ **Step Functions Standard Workflows**, không hỗ trợ Express Workflows.
3. Truy xuất task token qua `$$.Task.Token` (JSONPath) hoặc `$states.context.Task.Token` (JSONata).
4. Viết một Task gửi SQS message kèm token và xử lý kết quả bằng `ResultPath`, `Choice`, `Retry`, `Catch`.
5. Gọi `SendTaskSuccess`, `SendTaskFailure` và `SendTaskHeartbeat` từ AWS SDK for Java 2.x.
6. Biết giới hạn callback **cùng AWS account**, IAM quyền `states:SendTask*` và bảo mật token.
7. Phân biệt timeout tổng với heartbeat timeout, xử lý token hết hạn hoặc callback đến muộn.
8. Thiết kế saga có forward steps, compensations, state machine và tình huống outcome không xác định.
9. Triển khai idempotency/outbox/inbox để giảm double charge, double reservation khi retry/redrive.
10. So sánh Step Functions orchestration với EventBridge/SNS choreography.
11. Thiết kế human approval qua API Gateway/Lambda không công khai raw token.
12. Chẩn đoán lỗi và thiết kế giám sát, DLQ, redrive, SLA và chi phí.

## 2. Kiến trúc Step Functions phối hợp các dịch vụ

~~~mermaid
flowchart LR
    API["API Gateway / Order API"] --> SF["Step Functions Standard saga"]
    SF --> INV["Reserve inventory"]
    INV --> PAY["Authorize payment"]
    PAY --> WAIT["Wait for approval token"]
    WAIT --> Q["SQS approval request"]
    Q --> W["Worker / Human approval"]
    W -->|"SendTaskSuccess/Failure"| WAIT
    WAIT --> CONF["Confirm order"]
    CONF --> E["EventBridge OrderConfirmed"]
    WAIT -->|"Declined/Timeout"| COMP["Compensation"]
    COMP --> R["Void payment / Release inventory"]
~~~

Hệ thống Step Functions điều phối, **không tạo transaction ACID chung** giữa RDS, cổng thanh toán và kho hàng. Các services vẫn phải quản lý business invariants, idempotency, auth, logs, retry và reconciliation.

Một quy trình có thể diễn ra:

~~~text
09:00:00  ReserveInventory: OK
09:00:04  AuthorizePayment: OK
09:00:05  SQS thông báo yêu cầu kiểm tra rủi ro, workflow tạm dừng
09:27:41  Nhân viên đồng ý, worker gọi SendTaskSuccess
09:27:42  ConfirmOrder: OK
09:27:43  EventBridge phát OrderConfirmed
~~~

Không cần giữ Lambda invocation chạy 27 phút. Step Functions Standard giữ state trong lúc chờ callback và chỉ tiếp tục khi nhận quyết định phù hợp hoặc timeout.

## 3. Ba service integration patterns

| Pattern | Điều kiện bước được xem hoàn tất | Ví dụ | Workflow |
|---|---|---|---|
| **Request Response** | Service/API trả kết quả | `arn:aws:states:::lambda:invoke` | Standard và Express khi integration hỗ trợ |
| **Run a Job `.sync`** | Job tích hợp hoàn tất | ECS/Fargate/Batch/Glue với `.sync` khi hỗ trợ | **Standard** |
| **Wait for Callback `.waitForTaskToken`** | Worker gửi token cùng `SendTaskSuccess/Failure` | SQS → worker, human approval, external job | **Standard** |

Không phải mọi AWS service action hỗ trợ cả ba patterns. **Callback chỉ có ở những integrations có chỗ truyền token** trong request/payload/header. Luôn tham khảo bảng hỗ trợ của AWS thay vì nối hậu tố `.waitForTaskToken` vào mọi Resource ARN.

### 3.1. Standard hay Express?

| Khía cạnh | Standard Workflows | Express Workflows |
|---|---|---|
| Callback token | **Có** | **Không** |
| Tích hợp `.sync` | Có với service hỗ trợ | Không |
| Thời lượng execution tối đa | **1 năm** | **5 phút** |
| Billing | **State transitions** | Execution count, duration, memory |
| Phù hợp | Saga kéo dài, human approval, multi-service audit | High-volume, ngắn hạn, event transform |

Giới hạn **1 năm** là service quota, **không phải** timeout hợp lý cho một approval. Nếu không đặt deadline, execution có thể mắc kẹt rất lâu.

### 3.2. Callback khác Wait State và Activity

- `Wait` State tiếp tục theo số giây/timestamp, không cần actor gọi callback.
- `.waitForTaskToken` dừng ở Task cho tới callback hợp lệ hoặc timeout.
- `.sync` chờ một job integration có quản lý trạng thái, không yêu cầu worker tự gửi callback.
- **Step Functions Activity** dùng `GetActivityTask` polling và cũng có task token, nhưng khác việc Task chủ động `sqs:sendMessage.waitForTaskToken`.

Nếu một công việc kéo dài cả giờ, đừng cho Lambda sleep tới khi hoàn tất; dùng callback, `.sync` hoặc event-driven workflow tùy service.

## 4. Vòng đời task token

Step Functions phát **token riêng cho lần vào Task đang chờ**. Workflow chèn token vào SQS message hoặc request integration. Worker nhận việc và khi hoàn thành gửi callback.

~~~mermaid
sequenceDiagram
    participant SF as Step Functions Standard
    participant Q as SQS queue
    participant W as Java/ECS worker
    participant DB as Business database
    SF->>Q: SendMessage {orderId,taskToken}
    Note over SF: Tạm dừng tại Task
    W->>Q: ReceiveMessage
    Q-->>W: Payload + token
    W->>DB: Business update, commit
    DB-->>W: OK
    W->>SF: SendTaskSuccess(token, output JSON)
    SF-->>W: API response
    W->>Q: DeleteMessage sau xử lý
    SF->>SF: Merge callback output, chuyển Next state
~~~

| Giá trị | Mục đích |
|---|---|
| `stateMachineArn` | Định danh definition của state machine |
| `executionArn` | Định danh một lần thực thi saga |
| **`taskToken`** | Cho phép hoàn tất **một Task attempt đang chờ** |
| `sagaId`/`orderId` | Định danh nghiệp vụ và audit |
| **`operationId`** | Chống tác động nghiệp vụ bị retry |
| `eventId` | Chống lặp consumer khi event re-publish/redeliver |
| `receiptHandle` | Định danh lần receive SQS dùng để delete/thay visibility |

**Không dùng task token làm idempotency key hoặc saga ID.** Khi Task retry/redrive có thể sinh token khác nhưng nghiệp vụ vẫn cùng `orderId` và cùng operation.

### 4.1. Giới hạn AWS account

Tài liệu AWS quy định task tokens phải được gọi callback từ **IAM principal trong cùng AWS account** với execution. Worker ở account B dùng credentials B **không thể trực tiếp** gửi token cho Step Functions execution account A.

Nếu tổ chức có multi-account: worker có thể **assume một role ở account A** được ủy quyền qua STS và gọi callback bằng principal của A; hoặc gọi một **callback bridge** tại account A qua API đã xác thực. IAM policies, token distribution, business approval và network vẫn phải được kiểm soát.

### 4.2. Token cũ không thay thế token mới

Token gắn với một lần chờ. Khi Task đã success/fail, timeout, workflow stop hoặc Task được chạy lại sau retry/redrive, token cũ không thể hoàn tất lần chờ mới. AWS có thể phát token mới khi retry Task timeout. Không lấy token từ execution lịch sử rồi dùng cho một Task mới.

## 5. State machine callback SQS với JSONPath

Ví dụ **Standard Workflow** gửi yêu cầu duyệt đơn hàng vào SQS Standard queue `order-approvals`, giữ state input và chờ quyết định. Queue/account/Region là minh họa.

~~~json
{
  "Comment": "Callback approval on a Standard workflow",
  "StartAt": "RequestApproval",
  "States": {
    "RequestApproval": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
      "Parameters": {
        "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/111122223333/order-approvals",
        "MessageBody": {
          "orderId.$": "$.orderId",
          "taskToken.$": "$$.Task.Token"
        }
      },
      "TimeoutSeconds": 86400,
      "ResultPath": "$.approval",
      "Catch": [
        {
          "ErrorEquals": ["States.Timeout"],
          "ResultPath": "$.approvalError",
          "Next": "ApprovalUnavailable"
        },
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.approvalError",
          "Next": "ApprovalUnavailable"
        }
      ],
      "Next": "ChooseApproval"
    },
    "ChooseApproval": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.approval.approved",
          "BooleanEquals": true,
          "Next": "Approved"
        }
      ],
      "Default": "ApprovalUnavailable"
    },
    "Approved": {
      "Type": "Succeed"
    },
    "ApprovalUnavailable": {
      "Type": "Fail",
      "Error": "ApprovalDeclinedOrExpired",
      "Cause": "Approval declined, failed or timed out"
    }
  }
}
~~~

Điều kiện để chạy thật: queue đúng URL, state machine execution role có `sqs:SendMessage`, worker có callback IAM permission, input chứa `orderId`, cùng account token và approval logic.

### 5.1. Hiểu cú pháp Context

- `"taskToken.$": "$$.Task.Token"` lấy token từ **Step Functions Context object**, không phải chuỗi literal.
- `"orderId.$": "$.orderId"` lấy từ input.
- `"ResultPath": "$.approval"` giữ input, gắn callback JSON output vào `approval`.
- `"TimeoutSeconds": 86400` là hạn **24 giờ**.
- `Catch` nhận Task errors; `States.ALL` không bắt mọi terminal error, ví dụ `States.Runtime`/`States.DataLimitExceeded`.

Nếu không có `ResultPath`, task result có thể **ghi đè input** (mặc định `$`), khiến những state sau mất `orderId`.

### 5.2. Cùng Task nhưng dùng JSONata

Với `QueryLanguage: JSONata`, dùng `Arguments` và Context expression `$states.context.Task.Token` thay vì JSONPath `Parameters` và `.$`:

~~~json
{
  "Type": "Task",
  "QueryLanguage": "JSONata",
  "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
  "Arguments": {
    "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/111122223333/order-approvals",
    "MessageBody": {
      "orderId": "{% $states.input.orderId %}",
      "taskToken": "{% $states.context.Task.Token %}"
    }
  },
  "TimeoutSeconds": 86400,
  "End": true
}
~~~

Đây là **Task fragment**, chưa phải state machine. Không trộn `ResultPath` JSONPath với `Output/Assign` JSONata một cách tùy tiện.

### 5.3. Callback output

Worker có thể gửi output JSON như:

~~~json
{
  "approved": true,
  "decisionId": "dec-101",
  "reviewedBy": "risk-team"
}
~~~

**`SendTaskSuccess.output` phải là chuỗi JSON hợp lệ**, không phải một object chưa serialize và không phải string `APPROVED` thiếu dấu quote JSON. Giới hạn output là **256 KiB UTF-8**, cùng giới hạn Step Functions task/state payloads. Không nhúng file lớn hoặc raw PII vào callback; lưu ở S3 và trả key/URI khi cần.

## 6. Callback API, timeout và heartbeat

| API | Ý nghĩa |
|---|---|
| `SendTaskSuccess` | Hoàn thành Task thành công, chuyển state với output JSON |
| `SendTaskFailure` | Báo lỗi `error/cause`, kích hoạt `Retry/Catch` nếu cấu hình |
| `SendTaskHeartbeat` | Reset **heartbeat clock**, không kết thúc Task |
| `DescribeExecution` | Chỉ đọc execution status, không thay callback |
| `StopExecution` | Dừng workflow, không dùng token cũ để tiếp tục |
| `RedriveExecution` | Chạy lại failed step của Standard execution đủ điều kiện; có thể phát token mới |

### 6.1. Hai loại đồng hồ

`TimeoutSeconds` là **giới hạn tổng** cho Task. `HeartbeatSeconds` giới hạn thời gian không nhận heartbeat từ worker. **`SendTaskHeartbeat` chỉ reset heartbeat clock, không kéo dài TimeoutSeconds tổng.**

Với human approval kéo dài nhiều giờ, đặt deadline qua `TimeoutSeconds` và nhắc việc; không cần heartbeat liên tục từ con người.

Với job dài đang xử lý trên ECS, đặt chẳng hạn:

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
  "Parameters": {
    "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/111122223333/long-jobs",
    "MessageBody": {
      "jobId.$": "$.jobId",
      "taskToken.$": "$$.Task.Token"
    }
  },
  "HeartbeatSeconds": 120,
  "TimeoutSeconds": 3600,
  "End": true
}
~~~

Đây là Task fragment có heartbeat 2 phút và thời hạn tổng 1 giờ. Worker gửi `SendTaskHeartbeat` trước khi quá 120 giây. Nếu worker chết, Task có thể fail `States.Timeout` sớm. Dù gửi heartbeat liên tục, Task vẫn hết hạn sau một giờ.

### 6.2. Token errors

| Error | Giải thích thường gặp |
|---|---|
| `InvalidToken` | Token không hợp lệ, sai giá trị, bị sửa/truncated |
| `TaskTimedOut` | Token đã expire hoặc Task đã đóng |
| `TaskDoesNotExist` | Task không còn tồn tại trong ngữ cảnh API |
| `AccessDenied` | IAM principal thiếu `states:SendTask*` hoặc account sai |
| `InvalidOutput` | `SendTaskSuccess.output` không phải JSON hợp lệ |
| `KmsAccessDeniedException` | KMS key policy/caller permissions không đủ khi execution mã hóa theo cấu hình |

Nếu worker đã **commit business operation** nhưng callback trả `TaskTimedOut`, đừng suy business operation đã bị rollback. Trước khi retry/compensate, phải đối chiếu outcome thực tế.

## 7. SQS worker: hai ACK độc lập

Trong flow SQS → worker → Step Functions có **hai acknowledgements**:

1. `SendTaskSuccess/Failure` hoàn tất **Step Functions Task**.
2. `DeleteMessage` hoàn tất **SQS message consumption**.

Nếu `SendTaskSuccess` thành công nhưng worker crash trước khi `DeleteMessage`, SQS có thể redeliver message. Nếu worker retry callback với token cũ, Step Functions có thể báo token đã đóng. **Consumer phải idempotent theo business operation ID**, không thực hiện business effect lần hai.

Nếu callback HTTP response bị mất, worker **không biết chắc** Step Functions đã nhận hay chưa. Cần lưu callback outcome/correlation, xử lý các lỗi token closed và reconcile khi không xác định.

### 7.1. Visibility timeout, DLQ và token hết hạn

SQS `ReceiveMessage` chỉ làm message tạm invisible, không tự xóa. Khi quá visibility timeout mà chưa `DeleteMessage`, message có thể đến lại; việc này không phải lỗi dịch vụ. Worker có thể gia hạn bằng `ChangeMessageVisibility` khi xử lý dài.

Nếu message vào DLQ trước khi callback, Step Functions vẫn chờ tới task timeout. Khi redrive từ DLQ, token có thể đã hết hạn. **Không** gửi token đã hết hạn cho một execution mới; đối chiếu `orderId/operationId` và active Task attempt.

## 8. Java AWS SDK for Java 2.x gọi callback

Dùng `software.amazon.awssdk:sfn`, IAM role trong account của state machine và credentials provider chain của SDK. Các đoạn sau là ví dụ API, **không tự chạy nếu chưa có token được cấp quyền**.

### 8.1. `SendTaskSuccess`

~~~java
import software.amazon.awssdk.services.sfn.SfnClient;
import software.amazon.awssdk.services.sfn.model.SendTaskSuccessRequest;

public final class ApproveTask {
    public static void approve(SfnClient sfn, String taskToken, String decisionId) {
        // Serialize response object bằng Jackson ObjectMapper ở production.
        String safeId = decisionId.replaceAll("[^a-zA-Z0-9_-]", "");
        String output = "{\"approved\":true,\"decisionId\":\"" + safeId + "\"}";
        sfn.sendTaskSuccess(SendTaskSuccessRequest.builder()
                .taskToken(taskToken)
                .output(output)
                .build());
    }
}
~~~

Không đưa taskToken vào log/exceptions hoặc ghép JSON từ input chưa validate. Với production, dùng Jackson để serialize output có schema cố định. SfnClient cần Region đúng execution.

### 8.2. `SendTaskFailure`

~~~java
import software.amazon.awssdk.services.sfn.SfnClient;
import software.amazon.awssdk.services.sfn.model.SendTaskFailureRequest;

public final class RejectTask {
    public static void reject(SfnClient sfn, String taskToken) {
        sfn.sendTaskFailure(SendTaskFailureRequest.builder()
                .taskToken(taskToken)
                .error("ApprovalRejected")
                .cause("Rejected by authorized reviewer")
                .build());
    }
}
~~~

`error` là mã máy đọc được để Catch, `cause` không chứa PII hoặc token. Với từ chối nghiệp vụ, cũng có thể trả `SendTaskSuccess` với `{"approved":false}` rồi rẽ nhánh bằng `Choice`.

### 8.3. `SendTaskHeartbeat`

~~~java
import software.amazon.awssdk.services.sfn.SfnClient;
import software.amazon.awssdk.services.sfn.model.SendTaskHeartbeatRequest;

public final class WorkerHeartbeat {
    public static void ping(SfnClient sfn, String token) {
        sfn.sendTaskHeartbeat(SendTaskHeartbeatRequest.builder()
                .taskToken(token)
                .build());
    }
}
~~~

Heartbeat phù hợp worker thực sự đang xử lý, không dùng vòng heartbeat vô hạn để che giấu job đã chết. Dừng scheduler khi Task kết thúc.

## 9. IAM permissions và bảo vệ token

### 9.1. State machine execution role

Với `sqs:sendMessage.waitForTaskToken`, execution role của Step Functions cần `sqs:SendMessage` trên đúng queue:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SubmitApprovalRequest",
      "Effect": "Allow",
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:order-approvals"
    }
  ]
}
~~~

Execution role trust `states.amazonaws.com`. Thêm `lambda:InvokeFunction` và các resource permissions khác khi state machine gọi chúng; không cấp `AdministratorAccess`.

### 9.2. Worker callback IAM role

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CallbackOnly",
      "Effect": "Allow",
      "Action": [
        "states:SendTaskSuccess",
        "states:SendTaskFailure",
        "states:SendTaskHeartbeat"
      ],
      "Resource": "*"
    }
  ]
}
~~~

**Vì sao `Resource:"*"`?** AWS Service Authorization Reference cho biết các actions `states:SendTask*` **không hỗ trợ resource-level permissions**. Do đó **token distribution chính là một ranh giới bảo mật then chốt**: ai có token và IAM callback role có thể hoàn tất task tương ứng. Hạn chế callback role, endpoint, token store và môi trường có quyền đọc messages.

Worker poll SQS còn cần `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` và `sqs:ChangeMessageVisibility` trên queue ARN cụ thể, tách riêng với callback permissions.

### 9.3. Token là dữ liệu nhạy cảm

- Không ghi token vào CloudWatch logs, trace spans, URL query parameters, Slack/email hoặc dashboards.
- Mã hóa SQS messages at rest (SSE-SQS/SSE-KMS theo yêu cầu), TLS khi truyền, queue policy/KMS permissions hạn chế.
- Bảo vệ quyền `GetExecutionHistory`/`DescribeExecution` và CloudWatch Logs vì execution data có thể vô tình chứa token.
- Dùng callback bridge/authentication thay vì để người duyệt cầm raw token.
- Dùng `TimeoutSeconds` hợp lý, approvalId một lần, kiểm tra business state/version trước callback.

### 9.4. Private network

Worker ECS/EC2 trong private subnet không NAT có thể dùng AWS PrivateLink Interface Endpoints:

~~~text
com.amazonaws.ap-southeast-1.sqs
com.amazonaws.ap-southeast-1.states
~~~

`sqs` cho worker poll/delete; `states` cho `SendTaskSuccess/Failure/Heartbeat`. Kiểm tra endpoint Security Group inbound TCP 443, Private DNS, route/NACL, IAM và endpoint policy. `Step Functions → SQS` qua service integration không đòi worker phải triển khai VPC Link hoặc Step Functions vào private subnet.

## 10. Saga pattern: local transactions và bù trừ

Một saga chia business transaction thành các bước độc lập:

~~~text
T1 ReserveInventory
T2 AuthorizePayment
T3 WaitRiskApproval
T4 ConfirmOrder
~~~

Nếu T3 bị từ chối, có thể chạy bù trừ **theo thứ tự ngược**:

~~~text
C2 VoidPaymentAuthorization
C1 ReleaseInventoryReservation
~~~

**Compensation không phải distributed database rollback ACID.** Một khoản đã capture có thể phải **refund** chứ không void; một email đã gửi không thể unsend; một shipment đã giao không thể được “rollback” như SQL transaction.

### 10.1. Saga orchestration và choreography

| Tiêu chí | **Orchestration: Step Functions** | **Choreography: EventBridge/SNS/SQS** |
|---|---|---|
| Ai quyết định bước tiếp? | State machine tập trung | Mỗi subscriber theo event |
| Quan sát | Execution graph/history | Correlation/tracing nhiều services |
| Retry/Catch | Khai báo ASL | Từng consumer tự retry/DLQ |
| Bù trừ | Nhánh compensation rõ ràng | Event compensation do services nhận |
| Độ coupling | Orchestrator biết steps/targets | Services phụ thuộc event contracts |
| Hợp với | Approval, saga tuần tự, rollback phức tạp | Fan-out, các reactions độc lập |

Nhiều hệ thống chọn **Step Functions cho core order saga** và **EventBridge cho post-confirmation effects** (email, analytics, loyalty). Tránh để lỗi email khiến thanh toán đã hoàn tất bị hủy không cần thiết.

### 10.2. Saga khác 2PC

**Two-phase commit** tìm cách phối hợp các participants để commit nguyên tử, có thể giữ resource locks/trạng thái prepare lâu. **Saga** không giữ DB locks trong thời gian nhân viên duyệt 30 phút; nó cho phép **eventual consistency** và sử dụng compensations. Đổi lại, cần business invariants, idempotency, intermediate status và reconciliation.

## 11. Thiết kế một saga đơn hàng theo từng bước

Ví dụ nghiệp vụ có bốn hành động chính:

~~~mermaid
flowchart TD
    START["Order PENDING"] --> INV["T1 ReserveInventory"]
    INV -->|"OK"| PAY["T2 AuthorizePayment"]
    INV -->|"Outcome unknown"| RECON["Reconcile / manual"]
    PAY -->|"OK"| APP["T3 WaitRiskApproval"]
    PAY -->|"Outcome unknown"| RECON
    APP -->|"Approved"| CONF["T4 ConfirmOrder"]
    APP -->|"Denied / Timeout"| VOID["C2 VoidAuthorization"]
    VOID --> REL["C1 ReleaseInventory"]
    REL --> CANCEL["Order CANCELLED"]
    CONF -->|"OK"| DONE["Order CONFIRMED"]
    CONF -->|"Outcome unknown"| RECON
~~~

| Forward action | Durable effect | Stable operation key | Compensation |
|---|---|---|---|
| `ReserveInventory` | Tạo reservation cho order | `orderId:reserve:1` | `ReleaseInventory(reservationId)` |
| `AuthorizePayment` | Tạo payment authorization | `orderId:auth:1` | `VoidAuthorization(authId)` |
| `WaitRiskApproval` | Tạo approval request | `orderId:approval:1` | Expire/close approval |
| `ConfirmOrder` | Ghi status confirmed | `orderId:confirm:1` | Cancel/correction nếu được phép |
| `PublishOrderConfirmed` | Gửi event cho downstream | `eventId` | Không thể thu hồi event; dùng correction |

Các bước **local transactions** có thể commit độc lập. Một compensation không thể “rollback” mọi external effect: khoản tiền captured có thể phải refund; email không thể unsend. Đặc biệt, **timeout không chứng minh local transaction thất bại**; trước khi bù trừ, phải kiểm tra outcome.

### 11.1. State transitions nghiệp vụ

~~~text
PENDING
INVENTORY_RESERVED
PAYMENT_AUTHORIZED
AWAITING_APPROVAL
CONFIRMED
COMPENSATING
CANCELLED
RECONCILIATION_REQUIRED
~~~

Lưu `sagaId`/`orderId`, current business status, operation IDs, reservation/auth references, versions, timestamps và compensation outcome trong dữ liệu nghiệp vụ. Step Functions execution history hỗ trợ vận hành nhưng **không thay thế ledger** cho payments hay stock.

### 11.2. Thứ tự compensation và ranh giới

Thông thường bù trừ theo thứ tự ngược các bước đã thành công: **void authorization → release inventory**. Nhưng nếu payment đã captured thì void không còn phù hợp; cần refund, có thể mất vài ngày và bị lỗi. Bù trừ phải có **retry, own idempotency key, trạng thái `COMPENSATION_PENDING` và owner**.

## 12. State machine Standard: một saga tối thiểu có callback

Ví dụ sau tập trung vào **ReserveInventory → WaitForApproval → ConfirmOrder**, có nhánh **ReleaseInventory** khi bị từ chối hoặc timeout. Chúng ta cố tình **chưa thêm bước payment** vào ASL vì cần xây API/compensation payment có khả năng tra cứu outcome trước khi tự động dùng trong production.

~~~json
{
  "Comment": "Minimal saga: reserve, await approval, confirm or release",
  "StartAt": "ReserveInventory",
  "States": {
    "ReserveInventory": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:ReserveInventory",
        "Payload": {
          "orderId.$": "$.orderId",
          "operationId.$": "$.reserveOperationId"
        }
      },
      "ResultSelector": {
        "reservationId.$": "$.Payload.reservationId"
      },
      "ResultPath": "$.reservation",
      "Retry": [
        {
          "ErrorEquals": [
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException"
          ],
          "IntervalSeconds": 2,
          "MaxAttempts": 3,
          "BackoffRate": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.reserveError",
          "Next": "NeedsReconciliation"
        }
      ],
      "Next": "WaitForApproval"
    },
    "WaitForApproval": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
      "Parameters": {
        "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/111122223333/order-approvals",
        "MessageBody": {
          "orderId.$": "$.orderId",
          "reservationId.$": "$.reservation.reservationId",
          "taskToken.$": "$$.Task.Token"
        }
      },
      "TimeoutSeconds": 86400,
      "ResultPath": "$.approval",
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.approvalError",
          "Next": "ReleaseInventory"
        }
      ],
      "Next": "ApprovalDecision"
    },
    "ApprovalDecision": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.approval.approved",
          "BooleanEquals": true,
          "Next": "ConfirmOrder"
        }
      ],
      "Default": "ReleaseInventory"
    },
    "ConfirmOrder": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:ConfirmOrder",
        "Payload": {
          "orderId.$": "$.orderId",
          "reservationId.$": "$.reservation.reservationId",
          "operationId.$": "$.confirmOperationId"
        }
      },
      "ResultPath": "$.confirmation",
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.confirmError",
          "Next": "NeedsReconciliation"
        }
      ],
      "Next": "SagaSucceeded"
    },
    "ReleaseInventory": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:ReleaseInventory",
        "Payload": {
          "orderId.$": "$.orderId",
          "reservationId.$": "$.reservation.reservationId",
          "operationId.$": "$.releaseOperationId"
        }
      },
      "ResultPath": null,
      "Retry": [
        {
          "ErrorEquals": [
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException"
          ],
          "IntervalSeconds": 2,
          "MaxAttempts": 4,
          "BackoffRate": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.compensationError",
          "Next": "NeedsReconciliation"
        }
      ],
      "Next": "SagaCancelled"
    },
    "SagaSucceeded": {
      "Type": "Succeed"
    },
    "SagaCancelled": {
      "Type": "Fail",
      "Error": "BusinessOrderCancelled",
      "Cause": "Inventory released after decline or timeout"
    },
    "NeedsReconciliation": {
      "Type": "Fail",
      "Error": "ManualReconciliationRequired",
      "Cause": "Task or compensation outcome could not be confirmed"
    }
  }
}
~~~

### 12.1. Giải thích điểm quan trọng

- `ReserveInventory` gọi optimized Lambda integration, dùng `ResultSelector` lấy `reservationId` từ `Payload` và `ResultPath` để không mất `orderId`.
- `WaitForApproval` có callback token, chờ tối đa 24 giờ, đưa output vào `$.approval`.
- Output `{"approved":true}` làm Choice tới ConfirmOrder. Từ chối/timeout dẫn đến ReleaseInventory.
- `ReleaseInventory` có retry transient. Nếu compensation không thành công, execution vào `NeedsReconciliation`.
- `ConfirmOrder` fail không tự động hoàn kho vì có thể DB commit xong rồi Lambda timeout.
- `SagaCancelled` là kết thúc **failure của orchestration**, còn application cần cập nhật order business status/audit theo quy trình riêng.

### 12.2. Input cần có

~~~json
{
  "orderId": "ord-101",
  "reserveOperationId": "ord-101:reserve:1",
  "confirmOperationId": "ord-101:confirm:1",
  "releaseOperationId": "ord-101:release:1"
}
~~~

Đây là ví dụ **có thể phân tích cấu trúc ASL**, chưa phải stack deploy được: cần đúng Lambda functions, SQS queue, role permissions, IAM/KMS, application code, sự đồng thuận về schema, concurrency và monitor. Ví dụ chỉ tự động release khi approval worker **không tự làm irreversible side effect**; nếu worker đã charge/ship thì phải kiểm tra state trước khi compensate.

## 13. Idempotency: task token không đủ để chống trùng nghiệp vụ

| Key | Ai tạo? | Dùng cho |
|---|---|---|
| `taskToken` | Step Functions cho từng Task attempt | Tiếp tục đúng Task đang đợi |
| `operationId` | Ứng dụng tạo ổn định theo order/step | Chống lặp reservation/payment/compensation |
| `eventId` | Producer/outbox tạo | Chống downstream duplicate event |
| `sagaId` | Application | Liên kết các operations/correlation |

Nếu Step Functions retry `ReserveInventory`, Lambda có thể bị gọi hai lần. Business operation phải **idempotent theo operationId**. Khi task token đổi sau timeout/redrive, operationId vẫn giữ nguyên vì nghiệp vụ không thay.

### 13.1. Transactional operation log

~~~sql
CREATE TABLE operation_log (
  operation_id VARCHAR(160) PRIMARY KEY,
  order_id VARCHAR(100) NOT NULL,
  operation_type VARCHAR(80) NOT NULL,
  outcome_json JSONB,
  completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE inventory_reservations (
  reservation_id VARCHAR(100) PRIMARY KEY,
  order_id VARCHAR(100) UNIQUE NOT NULL,
  status VARCHAR(30) NOT NULL
);
~~~

Trong **cùng PostgreSQL transaction**:

1. Kiểm tra/tạo `operationId` với **unique constraint**.
2. Nếu đã completed, trả lại stored outcome, không thực hiện side effect lần nữa.
3. Nếu mới, thực hiện reservation/update và lưu outcome **atomic**.
4. Commit rồi mới báo thành công cho Step Functions/callback.

Không chỉ `SELECT processed` rồi `INSERT`: hai requests có thể cùng thấy chưa tồn tại. Dùng unique constraint/locks phù hợp. Với operation `IN_PROGRESS/UNKNOWN`, cần lease/outcome-check, không trả success giả.

### 13.2. DynamoDB hoặc external payment

Với DynamoDB có thể dùng `TransactWriteItems` để ghi dedup marker và business item trong cùng transaction, với condition `attribute_not_exists(pk)`. Nếu business update ở RDS/external payment gateway thì marker DynamoDB **không atomic** với side effect đó.

Cổng thanh toán nên nhận **provider idempotency key** ổn định như `orderId:authorize:attempt1`. Nếu request timeout nhưng provider đã charge, không retry với key mới; query outcome và reconcile. Refund/cancel cũng có idempotency riêng.

## 14. Transactional outbox, inbox và EventBridge

### 14.1. Producer outbox

Nếu Order service commit DB rồi mới publish `OrderConfirmed`:

~~~text
DB COMMIT success
Process crash trước EventBridge PutEvents
→ Order confirmed nhưng subscribers không nhận event
~~~

Dùng **transactional outbox**: cùng local transaction cập nhật order và insert `outbox_events(eventId, orderId, version, payload)`. Relay/CDC publish sang EventBridge/SNS/SQS. Relay có thể publish lặp nếu mất ACK; downstream consumer vẫn cần **inbox idempotency**.

~~~mermaid
flowchart LR
    API["Order API"] --> TX["PostgreSQL transaction"]
    TX --> ORD["orders"]
    TX --> OUT["outbox_events"]
    OUT --> REL["Relay/CDC"]
    REL --> BUS["EventBridge"]
    BUS --> CON["Idempotent consumers"]
~~~

### 14.2. Consumer inbox

Consumer dùng unique key **`(consumerName,eventId)`** và lưu processed marker **cùng transaction** với business write. Nếu event redeliver, phát hiện duplicate và no-op. Inbox không atomic với một external payment gateway; cần provider idempotency key/reconciliation.

### 14.3. Orchestration + choreography

Một order saga có approval, compensation rõ ràng nên do Step Functions điều phối. Khi `CONFIRMED`, outbox phát event và các subscribers như notification/analytics/loyalty có thể dùng choreography độc lập. Không nên tự hủy payment chỉ vì email service gặp lỗi.

## 15. Compensations cần idempotent và có trạng thái riêng

| Forward effect | Compensation | Bảo vệ |
|---|---|---|
| Inventory RESERVED | Release | Chỉ chuyển `RESERVED → RELEASED` một lần |
| Payment AUTHORIZED | Void | Kiểm tra authorization chưa CAPTURED |
| Payment CAPTURED | Refund | Không xóa lịch sử, reconciliation phí |
| Shipment CREATED | Cancel | Nếu carrier chưa giao |
| Email đã gửi | Correction | Không thể unsend |
| Resource AWS tạo ra | Delete owned resource | Ownership tags, không xóa shared resource |

### 15.1. Compensation lỗi cũng không phải success

~~~text
sagaId              = saga-ord-101
businessStatus      = COMPENSATION_PENDING
compensationStep    = VOID_PAYMENT
lastError           = ProviderUnavailable
nextRetryAt         = ...
owner               = payments-ops
~~~

Retry với backoff/jitter; nếu hết giới hạn, alert/manual intervention. Đừng tiếp tục bù trừ bước tiếp theo khi business policy yêu cầu đợi payment refund xong.

## 16. Retry, Catch và các race conditions

### 16.1. Retry lỗi tạm thời, Catch outcome chưa rõ

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Parameters": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:ReserveInventory",
    "Payload.$": "$"
  },
  "Retry": [
    {
      "ErrorEquals": [
        "Lambda.ServiceException",
        "Lambda.SdkClientException",
        "Lambda.TooManyRequestsException"
      ],
      "IntervalSeconds": 2,
      "MaxAttempts": 3,
      "BackoffRate": 2,
      "JitterStrategy": "FULL"
    }
  ],
  "Catch": [
    {
      "ErrorEquals": ["States.ALL"],
      "ResultPath": "$.error",
      "Next": "NeedsReconciliation"
    }
  ],
  "Next": "NextBusinessStep"
}
~~~

Đây là một **Task fragment**; các Next states phải tồn tại khi tạo workflow. Step Functions dùng **Retry trước Catch**. `States.TaskFailed` không match `States.Timeout`; `States.ALL` không catch lỗi terminal như `States.Runtime`. Đặt MaxAttempts, backoff và jitter để giảm retry storm, nhưng cần stable idempotency keys.

### 16.2. Callback muộn sau timeout

~~~text
10:00:00  Task chờ token T1
10:30:00  Task timeout, saga đi vào bù trừ
10:30:02  Nhân viên duyệt, gửi SendTaskSuccess(T1)
10:30:03  Step Functions trả TaskTimedOut / InvalidToken
10:30:10  Inventory được release
~~~

**Approval service chỉ nên ghi quyết định rồi callback**, không tự động ship order hoặc charge trước khi saga xác nhận status. Nếu user cancel/approve cạnh tranh, dùng optimistic version/conditional write trên order: chỉ một transition từ `PENDING_APPROVAL` thắng.

### 16.3. Callback ACK bị mất

Worker gửi callback, Step Functions nhận thành công, nhưng worker không nhận HTTP ACK. Retry bằng token T1 có thể trả `TaskTimedOut` vì Task đã đóng. Worker không được sinh token khác hoặc thực hiện payment lại; cần đối chiếu callback status/decisionId/execution status và business state.

### 16.4. Local operation timeout sau commit

Nếu Lambda cập nhật DB thành công rồi timeout khi trả response, Step Functions không biết local operation đã commit. **Không tự động release/void mù**. Query operation log theo stable operationId; nếu vẫn unknown, đặt `RECONCILIATION_REQUIRED`, alert owner và ngừng các bước làm tăng tác động.

## 17. Human approval qua API Gateway và callback bridge

**Không gửi raw task token trong email hay URL**. Task token cho phép hoàn tất pending Task khi đi cùng IAM principal có callback permission. Thiết kế an toàn hơn là tạo một **opaque approval ID** và giữ token trong protected store.

~~~mermaid
flowchart TD
    SF["Step Functions: waitForTaskToken"] --> Q["SQS {orderId, token}"]
    Q --> W["Approval worker"]
    W --> DB["DynamoDB: approvalId → encrypted token / status / expiry"]
    W --> NOTICE["Notification: signed short-lived approval link"]
    NOTICE --> HUMAN["Nhân viên phê duyệt"]
    HUMAN --> AUTH["API Gateway + JWT/Cognito/IAM auth"]
    AUTH --> BRIDGE["Lambda callback bridge"]
    BRIDGE --> DB
    BRIDGE -->|"SendTaskSuccess/Failure from same-account role"| SF
~~~

### 17.1. Callback bridge cần xác thực gì?

1. **Người duyệt** đã đăng nhập qua cơ chế thích hợp, không chỉ có URL.
2. Người duyệt có vai trò/quyền xét duyệt `orderId`/tenant/amount này.
3. `approvalId` hợp lệ, chưa hết hạn và chưa dùng.
4. Business order còn `AWAITING_APPROVAL` và version đúng.
5. Quyết định được ghi durable với `decisionId` duy nhất.
6. Từ chối/đồng ý cạnh tranh được xử lý bằng **conditional write**, chỉ một quyết định thắng.
7. Worker lấy đúng active token từ store và callback bằng IAM role cùng account.

### 17.2. Approval decision và callback không atomic

DynamoDB conditional write từ `PENDING` → `APPROVED` có thể thành công, nhưng Lambda crash trước `SendTaskSuccess`. Ngược lại, callback có thể thành công nhưng response mất, nên DB chưa ghi `CALLBACK_SENT`. Dùng trạng thái:

~~~text
PENDING
DECISION_RECORDED
CALLBACK_SENT
CALLBACK_UNKNOWN
EXPIRED
RECONCILIATION_REQUIRED
~~~

Một job retry/reconcile quyết định nào đã được callback và execution còn chờ hay không. **Không đánh dấu order `CONFIRMED` chỉ vì reviewer bấm Approve**; Step Functions còn phải chạy `ConfirmOrder` dưới business guardrails.

### 17.3. Token, encryption và network

Token lưu ở DynamoDB/S3 protected record với encryption, IAM least privilege và TTL hợp lý; TTL cleanup không phải security authorization — phải kiểm tra `expiresAt` tại thời điểm request. Không đặt token trong access logs, email hay analytics. API Gateway có authorization và WAF/rate limiting theo threat model. Callback Lambda chạy trong VPC private subnet thì cần network path tới `states` endpoint, nhưng bản thân Step Functions không phải một container trong customer VPC.

## 18. Redrive Standard executions, retry counter và token mới

**`RedriveExecution`** hỗ trợ chạy lại các execution **Standard** đã `FAILED`, `TIMED_OUT` hoặc `ABORTED` trong cửa sổ đủ điều kiện (AWS hiện nêu **14 ngày sau khi execution kết thúc**, cùng các quota khác).

- Redrive tiếp tục từ **bước không thành công** và **giữ output/history của các bước đã thành công**, thay vì chạy lại toàn bộ từ đầu theo mặc định.
- Nếu redrive chạy lại một Task/Parallel/Inline Map có `Retry`, **retry count reset về 0** cho lần redrive đó.
- Callback Task được thực hiện lại có thể nhận **task token mới**. Message cũ chứa token cũ không thể hoàn tất Task mới.
- Một local action có thể đã commit trong lần trước nhưng Step Functions không nhận response; redrive có thể **gọi lại action**. Chỉ an toàn nếu dùng stable operationId.
- Redrive không phải “hoàn tác tất cả rồi thực hiện lại”; nó cũng không chứng minh các compensations đã thành công.

**Không tự redrive toàn bộ compensation failures không qua review.** Nếu payment đã capture/refund và logs không rõ, cần reconciliation trước khi lặp lại action.

### 18.1. Re-execution khác redrive

Tạo một execution mới với cùng `orderId` nhưng operation IDs mới có thể tạo reservation/charge thứ hai. Nếu nghiệp vụ cho phép “retry đặt hàng”, cần định nghĩa **new attempt number** và idempotency policy; không dùng lại những effects cũ mù quáng.

## 19. Giám sát workflow, callback backlog và business consistency

| Thành phần | Signals nên theo dõi | Lý do |
|---|---|---|
| Step Functions | `ExecutionsStarted`, `ExecutionsFailed`, `ExecutionsTimedOut`, `ExecutionsAborted` | Sức khỏe workflow |
| Step Functions | `OpenExecutionCount`, `ExecutionTime`, execution history | Stuck approvals và quotas |
| Callback workers | Callback success/failure/timeout, processing latency, heartbeats | Worker sống không? |
| SQS approval queue | `ApproximateNumberOfMessagesVisible`, `ApproximateAgeOfOldestMessage`, DLQ | Backlog và poison messages |
| ECS/Lambda | Errors, throttles, CPU/memory, duration | Compute health |
| Business DB | Pending approvals, reservations TTL, compensation count | Độ đúng nghiệp vụ |
| Payment provider | Auth holds, settled captures, refund pending | Sai lệch external money flow |

### 19.1. CloudWatch, history và CloudTrail

- **Execution history:** transitions, Task started/succeeded/failed/timed-out, Retry/Catch, callback resolution.
- **CloudWatch metrics/alarms:** failed/timed-out executions, backlog, worker error rate, số compensation pending.
- **CloudTrail:** audit các API Step Functions `StartExecution`, `StopExecution`, `SendTask*` và các thay đổi IAM/definition theo cấu hình logging.
- **App logs:** `sagaId`, `orderId`, `operationId`, `decisionId`, `correlationId`, không in raw token.
- **DB audit:** local transaction result và business version.
- **Distributed tracing:** nối API Gateway → Step Functions → Lambda/ECS/RDS qua correlation.

Một execution `SUCCEEDED` không chứng minh tất cả email downstream chỉ gửi một lần; cần **business ledger/reconciliation**. CloudWatch metrics/SQS counts có thể ước lượng hoặc có độ trễ.

### 19.2. Nhạy cảm của execution history

Task token có thể xuất hiện trong SQS payload hoặc execution data nếu workflow đưa vào integration request. Giới hạn quyền đọc `GetExecutionHistory`, `DescribeExecution`, CloudWatch Logs, SQS payload, KMS keys. Có thể tắt hoặc hạn chế include-execution-data ở logging/CLI nếu cần. Không gửi full history có token lên public ticket.

### 19.3. Runbook/ownership

Xây dashboard theo `sagaId/orderId` có current step, elapsed time, business status, timeout deadline, compensation owner và last failure. Alert khi approval quá SLA, lost heartbeat, DLQ backlog, compensation retry vượt ngưỡng. Quy trình can thiệp phải xác định ai được **retry, compensate, stop/redrive hoặc manually reconcile** và lưu audit.

## 20. Availability, quotas và tổng chi phí

### 20.1. Giới hạn quan trọng

| Giới hạn | Standard | Express |
|---|---|---|
| Maximum execution duration | **1 năm** | **5 phút** |
| Callback integration | Có | Không |
| Execution history events | Tối đa **25.000** events | Không lưu cùng dạng Standard execution history |
| Task/input/output payload | **256 KiB UTF-8** | **256 KiB UTF-8** |
| Redrive Standard failed executions | Có khi đủ điều kiện | Không theo cùng cơ chế |
| Task token length | **1–2048 ký tự** theo `SendTaskSuccess` API | Không áp dụng callback |

Kiểm tra thêm quotas API throttling, open executions, state transitions, SQS messages, Lambda concurrency và KMS theo Region. Workflow mặc định không có timeout Task cụ thể không có nghĩa nó an toàn chờ vô hạn.

### 20.2. Cost drivers

| Hạng mục | Chi phí/đánh đổi |
|---|---|
| **Step Functions Standard** | Tính theo **state transitions**; đợi callback không phải Lambda duration |
| **SQS/EventBridge/SNS** | Messages/requests, event delivery, retries, DLQ |
| **Lambda/ECS** | Invocation/duration, compute capacity, auto scaling |
| **RDS/DynamoDB** | Idempotency/approval/outbox storage và transactions |
| **CloudWatch/CloudTrail** | Logs, retention, alarms và audit |
| **KMS** | Key management/cryptographic requests |
| **PrivateLink/NAT** | Interface endpoint-hour, data processing/egress |
| **Payment/external provider** | Authorization/refund/charge fees và rủi ro vận hành |

Đừng cố giảm một state transition bằng cách bỏ qua reconciliation/catch nếu làm tăng nguy cơ double charge hoặc compensation sai. So sánh **tổng TCO**, SLO, failure modes và audit requirements, không chỉ phí Step Functions.

### 20.3. Phục hồi và Region

Step Functions là managed service trong Region; multi-AZ cho worker/data backend phải được thiết kế riêng. Database backup/Multi-AZ, IAM/KMS, queue retention, DLQ, stable IDs và callback bridge availability đều ảnh hưởng saga. **Cross-Region recovery** không đơn giản copy token sang state machine mới ở Region khác; cần migration/cancel/reconcile business operations và execution attempt IDs mới.

## 21. CLI chỉ đọc: kiểm tra workflow mà không gửi callback

Các lệnh dưới đây **chỉ đọc** và không start/stop/redrive execution. Dùng AWS CLI v2, profile `dev`, Region `ap-southeast-1`. Thay ARNs/URLs minh họa khi có quyền.

### 21.1. Caller và state machine type

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws stepfunctions list-state-machines \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws stepfunctions describe-state-machine \
  --state-machine-arn arn:aws:states:ap-southeast-1:111122223333:stateMachine:OrdersSaga \
  --profile dev \
  --region ap-southeast-1 \
  --query '{Type:type,Status:status,Role:roleArn,Definition:definition}' \
  --output json
~~~

Đọc `type` phải là `STANDARD` đối với callback; tìm Resource `.waitForTaskToken` và token expression trong definition. **Definition có thể chứa tài nguyên nhạy cảm**, không tự paste lên kênh công khai.

### 21.2. Đọc executions

~~~bash
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:ap-southeast-1:111122223333:stateMachine:OrdersSaga \
  --status-filter RUNNING \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws stepfunctions describe-execution \
  --execution-arn arn:aws:states:ap-southeast-1:111122223333:execution:OrdersSaga:sample-run \
  --profile dev \
  --region ap-southeast-1 \
  --query '{Status:status,Start:startDate,Stop:stopDate,Error:error,Cause:cause,RedriveCount:redriveCount}' \
  --output json
~~~

### 21.3. History không hiện raw execution data

~~~bash
aws stepfunctions get-execution-history \
  --execution-arn arn:aws:states:ap-southeast-1:111122223333:execution:OrdersSaga:sample-run \
  --max-results 20 \
  --reverse-order \
  --no-include-execution-data \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

`--no-include-execution-data` tránh in nhiều input/output bodies chứa token hoặc PII. Metadata vẫn cần được xử lý theo data classification. Nếu muốn xem chi tiết để debug, thực hiện trong môi trường bảo mật với đúng quyền.

### 21.4. SQS backlog mà không ReceiveMessage

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/order-approvals \
  --attribute-names QueueArn VisibilityTimeout RedrivePolicy ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

`ReceiveMessage` không phải chỉ đọc vô hại: nó làm message invisible và tăng receive count. Không dùng production queue để “xem token” cho lab.

## 22. Lệnh có tác động: chỉ dành cho sandbox đã duyệt

### 22.1. StartExecution tạo nghiệp vụ thật

~~~bash
# CÓ TÁC ĐỘNG: bắt đầu workflow, có thể gọi Lambda/SQS và ghi DB.
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:ap-southeast-1:111122223333:stateMachine:OrdersSaga \
  --name lab-order-101 \
  --input '{"orderId":"ord-101","reserveOperationId":"ord-101:reserve:1","confirmOperationId":"ord-101:confirm:1","releaseOperationId":"ord-101:release:1"}' \
  --profile dev \
  --region ap-southeast-1
~~~

Tất cả tài nguyên/credentials phải trỏ đến **sandbox** khi chạy. Nếu tên execution trùng, AWS có các quy tắc idempotency theo status/input Standard workflows; không dùng lại execution name mà không nắm rõ.

### 22.2. Callback success hoặc failure

~~~bash
# CÓ TÁC ĐỘNG: chỉ khi có token thật đang active và approval hợp lệ.
aws stepfunctions send-task-success \
  --task-token "$TASK_TOKEN" \
  --task-output '{"approved":true,"decisionId":"dec-101"}' \
  --profile dev \
  --region ap-southeast-1

# LỰA CHỌN THAY THẾ: không chạy cả hai trên cùng token.
aws stepfunctions send-task-failure \
  --task-token "$TASK_TOKEN" \
  --error ApprovalRejected \
  --cause "Rejected by authorized reviewer" \
  --profile dev \
  --region ap-southeast-1
~~~

Ví dụ cú pháp Bash; PowerShell dùng cách truyền biến/quoting khác. `TASK_TOKEN` phải được lấy an toàn, không đưa token vào logs/shell history/ticket. Trong production, ưu tiên callback bridge/SDK.

### 22.3. Heartbeat không phải lệnh kiểm tra vô hại

~~~bash
# CÓ TÁC ĐỘNG lên heartbeat clock của pending task.
aws stepfunctions send-task-heartbeat \
  --task-token "$TASK_TOKEN" \
  --profile dev \
  --region ap-southeast-1
~~~

Không gọi heartbeat chỉ để xem token còn hợp lệ vì chính thao tác này có thể gia hạn heartbeat timer.

## 23. Troubleshooting callback và saga

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `.waitForTaskToken` không dùng được | Workflow type Express | `describe-state-machine.type` |
| Execution chờ rất lâu | Worker chưa callback, không có deadline | Timeout, SQS backlog, worker health |
| `InvalidToken` | Token sai, truncated, được copy lỗi | Token store/serialization, không log raw token |
| `TaskTimedOut` | Task đã timeout/closed hoặc callback đến muộn | History/timeouts, business outcome |
| Callback `AccessDenied` | Role thiếu `states:SendTask*` hoặc account không khớp | `sts get-caller-identity`, IAM, same-account rule |
| Worker B callback execution A | Không được dùng principal B trực tiếp | Assume role A hoặc bridge A |
| `InvalidOutput` | Output không phải JSON hợp lệ | Serialize JSON, payload 256 KiB |
| `KmsAccessDeniedException` | KMS permissions/key policy sai | KMS key state/grants |
| Approval được ghi DB nhưng Step Functions chưa tiếp tục | Callback thất bại/response ambiguous | Callback status, execution history, retry reconcile |
| Task success làm mất `orderId` | ResultPath mặc định overwrite input | Chọn `ResultPath` phù hợp |
| Worker xử lý lại message | Crash sau callback trước SQS DeleteMessage | Inbox/operationId và receipt handle |
| Payment double-charge | Retry với payment key khác | Stable provider idempotency key |
| Inventory released hai lần | Compensation không idempotent | Reservation state/conditional transition |
| Timeout nhưng operation đã commit | Outcome unknown bị coi failed | Business query/reconciliation |
| DLQ chứa token hết hạn | Queue redrive sau task timeout | Không dùng token cũ, reconcile active Task |
| Retry storm | `Retry` quá rộng/không backoff | MaxAttempts, jitter, phân loại transient |
| Execution failed nhưng payment hold còn | Compensation lỗi/chưa chạy | `COMPENSATION_PENDING`, manual owner |
| Worker private subnet không gọi Step Functions | Thiếu `states` VPC endpoint/NAT, SG/DNS sai | Private DNS/TCP 443/IAM |
| Redrive làm lặp side effect | Stable operationId không được giữ | Idempotency store, redrive review |

### 23.1. Runbook chẩn đoán theo tầng

1. Xác định account, Region, execution ARN và **STANDARD** type.
2. Đọc history **không in token**: Task đang chờ, success, fail hay timeout?
3. Kiểm tra `.waitForTaskToken` và syntax `$$.Task.Token`/`$states.context.Task.Token`.
4. Kiểm tra worker nhận SQS message, IAM callback principal cùng account, network `states` endpoint.
5. Kiểm tra Task deadline/heartbeat và token có bị thay do retry/redrive không.
6. Đọc business operation log và provider outcome trước khi bù trừ/retry.
7. Kiểm tra DLQ, compensation states, CloudWatch metrics và owner để khôi phục có audit.

**Không mở IAM `states:*` hoặc cho phép bypass approval để “thử cho chạy”**. Lỗi IAM/token/network phải giải quyết ở tầng đúng.

## 24. Bài thực hành chỉ đọc và tình huống nghiệp vụ

### 24.1. Lab không tạo tài nguyên

Có AWS CLI v2 profile `dev` chỉ đọc Step Functions/SQS, hoặc dùng JSON mẫu nếu không có AWS account.

1. Dùng `list-state-machines` và `describe-state-machine` để tìm type **STANDARD** và execution role.
2. Xác định states dùng `.waitForTaskToken`, cách lấy Context token, Task timeouts.
3. Dùng `list-executions --status-filter RUNNING`, `describe-execution` để xem tuổi execution.
4. Dùng `get-execution-history --no-include-execution-data` để tìm TaskStarted/TimedOut/Failed, không đọc raw token.
5. Dùng `get-queue-attributes` kiểm tra backlog, visibility, DLQ.
6. Viết bảng `Task → operationId → compensation → owner/alert`.
7. Giải thích khi nào **retry**, **compensate**, **manual reconcile**, **redrive**.

### 24.2. Tình huống A — Human approval

Order cần review trong tối đa 24 giờ. Nhân viên approve sau 45 phút.

- Step Functions chờ callback SQS với `TimeoutSeconds=86400`.
- Approval service lưu token protected, chỉ đưa `approvalId` trong link, xác thực reviewer.
- Callback success JSON `{"approved":true}`; saga tiếp tục `ConfirmOrder`.
- Sau timeout, callback bị từ chối/không tiếp tục; inventory release idempotently.

### 24.3. Tình huống B — Job ECS 20 phút

Job video processing chạy ECS; timeout tổng 30 phút, heartbeat 2 phút:

- Worker gửi `SendTaskHeartbeat` theo lịch khi còn thực sự xử lý.
- Kết thúc thì `SendTaskSuccess` với `jobId`/`s3ArtifactKey`.
- Không trả video bytes vào output; giới hạn 256 KiB.
- Worker chết → heartbeat timeout, có retry/compensation theo application policy.

### 24.4. Tình huống C — Payment response mất

Provider đã capture nhưng payment service timeout:

- Query provider với stable payment operationId.
- Nếu captured, tiếp tục xử lý hoặc refund theo policy.
- Nếu chưa captured, retry cùng provider idempotency key khi hỗ trợ.
- Nếu unknown, `RECONCILIATION_REQUIRED`; không tự charge lại với key mới.

### 24.5. Tình huống D — Redrive một ngày sau

Một Standard execution đã reserve stock rồi fail khi gửi approval request. Redrive có thể tạo token mới. Worker phải loại request/token cũ còn trong queue. `reserveOperationId` giữ nguyên để không reserve lần hai. Operator kiểm tra reservation expiry/outcome và quyết định có an toàn redrive không.

### 24.6. Bảng tự kiểm

| Tình trạng | Quyết định ưu tiên |
|---|---|
| Task waiting, chưa thấy SQS message | Kiểm tra SQS/access/network và Task status |
| Task waiting, worker chạy nhưng mất heartbeat | Check worker health, heartbeat timeout/retry |
| Token expired, business chưa có effect | Đóng approval cũ, xử lý timeout/compensation |
| Token expired, business đã commit | **Reconcile** trước khi bù trừ |
| Callback response mất | Check execution/decision; không assume failure |
| Compensation lỗi | Retry idempotent, alert, giữ pending status |
| Redrive failed execution | Review history, stable IDs, token mới |
| SQS redelivery | Inbox no-op, callback outcome check, delete theo policy |

## 25. Câu hỏi tự đánh giá

1. Vì sao `.waitForTaskToken` yêu cầu Standard workflow?
2. Callback khác `.sync` và `Wait` state như thế nào?
3. Trong JSONPath, token nằm ở `$$.Task.Token` hay `$.taskToken` mặc định?
4. JSONata truy cập token bằng biểu thức nào?
5. `SendTaskSuccess.output` có bắt buộc là JSON hợp lệ?
6. Vì sao token không được dùng làm `orderId/operationId`?
7. IAM principal ở account B có thể trực tiếp callback execution account A không?
8. Vì sao IAM `SendTaskSuccess` thường cần `Resource:"*"`?
9. Heartbeat có kéo dài `TimeoutSeconds` tổng không?
10. Khi nào dùng heartbeat, khi nào dùng deadline cho human approval?
11. Worker đã callback success nhưng SQS message redeliver thì phải làm gì?
12. `ResultPath` giúp giữ input khi nhận callback output như thế nào?
13. Saga khác distributed ACID transaction ở điểm gì?
14. Tại sao compensation của payment captured có thể là refund thay vì void?
15. Vì sao compensation cũng phải idempotent?
16. Timeout của một Lambda action có chứng minh DB transaction chưa commit không?
17. Outbox giải quyết lỗi gì giữa DB commit và EventBridge publish?
18. Redrive có chạy lại mọi successful step hay không?
19. Vì sao raw task token không nên xuất hiện trong approval URL?
20. Những metrics nào phản ánh stuck executions và compensation backlog?
21. CloudTrail và Step Functions execution history hỗ trợ điều tra khác nhau thế nào?
22. Khi nào choreography qua EventBridge có lợi hơn orchestration?

### Đáp án định hướng

- **Callback:** Standard Task `.waitForTaskToken` tạo token, worker trong cùng account gửi `SendTaskSuccess/Failure`; heartbeat reset heartbeat clock, không gia hạn task timeout tổng.
- **Saga:** Các local commits độc lập; compensation không phải ACID rollback, cần reconcile khi outcome unknown.
- **Idempotency:** Stable operationId/eventId, database uniqueness, outbox/inbox và payment provider idempotency key; token không phải business key.
- **Security:** Hạn chế phân phối token, IAM callback role, API approval auth và không log token.
- **Operations:** Retry/Catch, DLQ, timeout, redrive có review, CloudWatch/CloudTrail và business ledger.

## 26. Tài liệu AWS chính thức

1. [Step Functions integration patterns](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html) — Request-response, `.sync`, callback, same-account token.
2. [SQS integration with Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-sqs.html) — `sqs:sendMessage.waitForTaskToken`.
3. [Lambda integration with Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-lambda.html) — Lambda callback patterns.
4. [Step Functions Context object](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-contextobject.html) — JSONPath/JSONata token.
5. [JSONata data transformations](https://docs.aws.amazon.com/step-functions/latest/dg/transforming-data.html) — `Arguments`, `Output`, Context.
6. [Step Functions Task state](https://docs.aws.amazon.com/step-functions/latest/dg/state-task.html) — Timeouts, `Retry`, `Catch`.
7. [Step Functions error handling](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html) — Error names, retry/backoff/jitter.
8. [Step Functions best practices](https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html) — Timeouts, heartbeats, execution management.
9. [SendTaskSuccess API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_SendTaskSuccess.html) — Token/output constraints.
10. [SendTaskFailure API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_SendTaskFailure.html) — Failure details.
11. [SendTaskHeartbeat API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_SendTaskHeartbeat.html) — Reset heartbeat, not overall timeout.
12. [Step Functions IAM authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_stepfunctions.html) — `SendTask*` IAM resource support.
13. [Choosing workflow types](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html) — Standard vs Express.
14. [Step Functions quotas](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html) — Durations, payload/history limits.
15. [Saga pattern — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-data-persistence/saga-pattern.html) — Local transactions and compensation.
16. [Saga orchestration pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-orchestration.html) — Order saga on Step Functions.
17. [Redrive executions](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html) — Resuming failed Standard execution.
18. [Troubleshooting Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/troubleshooting.html) — Tokens, roles, timeouts.
19. [Activities in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-activities.html) — Polling activities vs callbacks.
20. [AWS CLI get-execution-history](https://docs.aws.amazon.com/cli/latest/reference/stepfunctions/get-execution-history.html) — Omit execution data.
21. [AWS CLI send-task-success](https://docs.aws.amazon.com/cli/latest/reference/stepfunctions/send-task-success.html) — Callback API syntax.
22. [Step Functions VPC endpoints](https://docs.aws.amazon.com/step-functions/latest/dg/vpc-endpoints.html) — Private AWS API connectivity.
23. [Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) — Standard transitions/Express.
24. [Amazon SQS pricing](https://aws.amazon.com/sqs/pricing/) — Requests and delivery.

> **Ghi nhớ:** Callback token là cơ chế **chờ một Task hoàn tất**, còn saga là cơ chế **phối hợp các local transactions và compensations**. Với Step Functions Standard, hãy đặt timeout/heartbeat hợp lý, bảo vệ token, dùng callback principal cùng account, giữ business operation IDs ổn định, xử lý idempotent, tra cứu outcome chưa rõ và giám sát compensation/recovery đến khi toàn bộ nghiệp vụ nhất quán.



