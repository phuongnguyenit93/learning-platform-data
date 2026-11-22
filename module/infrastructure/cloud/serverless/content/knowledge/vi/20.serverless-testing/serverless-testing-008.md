# Kiểm thử workflow với timeout, callback và tác vụ bù

Một workflow serverless thường điều phối nhiều Java Lambda hoặc dịch vụ bên ngoài. Một bước có thể hoàn tất nhanh, bước khác có thể chờ đối tác phản hồi trong nhiều giờ. Khi lỗi xảy ra sau khi một bước đã tạo side effect, workflow còn phải thực hiện tác vụ bù để đưa nghiệp vụ về trạng thái an toàn.

Kiểm thử kiểu workflow này cần đi xa hơn việc xác nhận từng Lambda trả về đúng kết quả. Cần kiểm tra cả luồng trạng thái, thời gian chờ, retry, callback, timeout, tác vụ bù, khả năng chạy lại và những tình huống kết quả không rõ ràng. Với AWS Step Functions, có thể kết hợp unit test Java, kiểm thử từng state, mô phỏng cục bộ và integration test trong một AWS environment cô lập.

Bài học tập trung vào cách xây dựng test plan cho workflow có timeout, callback task token và Saga compensation; cách tạo lỗi có kiểm soát; và cách xác minh execution history cùng trạng thái nghiệp vụ.

## 1. Vì sao phải kiểm thử workflow như một hệ thống?

Một Lambda có thể hoạt động đúng khi được gọi độc lập nhưng workflow vẫn thất bại vì:

- State truyền sai payload hoặc ghi kết quả đè lên input cần thiết.
- Tên lỗi Java không khớp với ErrorEquals trong Retry/Catch.
- Retry tạo side effect trùng khi lần gọi trước đã thành công nhưng response bị timeout.
- Callback không đến trước deadline.
- Callback đến sau khi task đã timeout hoặc workflow đã kết thúc.
- Task token bị gửi nhầm, bị lộ hoặc được dùng hai lần.
- Compensation chạy sai thứ tự hoặc chạy cả khi bước tương ứng chưa thành công.
- Compensation thất bại nhưng workflow vẫn bị đánh dấu như đã rollback hoàn toàn.
- Một execution mới xử lý lại dữ liệu mà execution trước đã commit.
- Workflow hoàn tất về mặt kỹ thuật nhưng trạng thái nghiệp vụ trong database không nhất quán.

Do đó, cần kiểm tra hai lớp kết quả:

1. **Workflow result:** execution thành công, thất bại, timeout hoặc đang chờ ở state nào.
2. **Business result:** order, payment, reservation hoặc shipment thực tế đang ở trạng thái nào sau khi workflow kết thúc.

Execution FAILED không tự chứng minh mọi side effect đã được hoàn tác. Execution SUCCEEDED cũng không tự chứng minh dữ liệu nghiệp vụ đúng nếu một Lambda nuốt exception hoặc trả kết quả sai.

## 2. Mô hình workflow dùng trong bài kiểm thử

Xét quy trình đặt hàng gồm các bước:

1. Giữ tồn kho.
2. Thu tiền.
3. Tạo vận đơn.
4. Gửi thông báo.
5. Nếu một bước thất bại, chạy các tác vụ bù phù hợp.

Một nhánh lỗi có thể cần hoàn tiền rồi giải phóng tồn kho. Nếu payment chưa được thu, chỉ cần giải phóng tồn kho. Nếu trạng thái payment không rõ do timeout, workflow phải tra cứu giao dịch bằng idempotency key trước khi quyết định hoàn tiền.

~~~mermaid
flowchart TD
    A["Start order workflow"] --> B["Reserve inventory"]
    B --> C["Charge payment"]
    C --> D["Create shipment"]
    D --> E["Notify customer"]
    E --> F["Succeed"]
    C -->|Failure| G["Release inventory"]
    D -->|Failure| H["Refund payment"]
    H --> G
    G --> I["Mark order failed"]
    I --> J["Fail"]
    H -->|Compensation failure| K["Manual recovery"]
    G -->|Compensation failure| K
~~~

Đây là một Saga: mỗi bước nghiệp vụ có thể có một hành động bù. Compensation không phải transaction rollback phân tán. Nó là một thao tác nghiệp vụ mới, có thể thất bại và cần được theo dõi riêng.

Một workflow có callback có thể chờ payment provider hoặc người phê duyệt. Khi đó, một Task state gửi yêu cầu và task token cho một thành phần đáng tin cậy; workflow tạm dừng cho đến khi thành phần đó gọi SendTaskSuccess hoặc SendTaskFailure.

## 3. Các tầng timeout cần phân biệt

Timeout có thể xuất hiện ở nhiều lớp. Nếu chỉ nhìn thấy một thông báo timeout mà không biết lớp nào hết hạn, việc điều tra và thiết kế retry rất dễ sai.

| Tầng | Timeout kiểm soát | Điều cần kiểm thử |
|---|---|---|
| HTTP client/API | Thời gian caller chờ response | Caller có retry khi response timeout không? |
| Lambda | Thời gian tối đa một invocation chạy | Function dừng đúng hạn và đóng tài nguyên thế nào? |
| Step Functions Task | Thời gian Task được phép hoàn tất | State chuyển sang Catch hay làm execution thất bại? |
| Callback heartbeat | Khoảng thời gian tối đa giữa các heartbeat | Worker có gửi heartbeat đều và đúng task token không? |
| Workflow/business deadline | Tổng thời gian quy trình được phép kéo dài | Có thể dừng hoặc chuyển sang xử lý thủ công không? |
| Downstream service | Thời gian chờ database, payment provider hoặc API | Timeout có tạo kết quả không rõ ràng hay side effect dở dang? |

### 3.1. Lambda timeout và Task timeout

Lambda timeout giới hạn thời gian invocation. Step Functions Task TimeoutSeconds giới hạn thời gian state chờ tác vụ hoàn tất. Cần đặt quan hệ hợp lý giữa hai giới hạn.

Nếu Task timeout ngắn hơn Lambda timeout, Step Functions có thể ngừng chờ trong khi Lambda vẫn đang chạy. Lambda có thể tiếp tục tạo side effect sau khi workflow đã chuyển sang nhánh lỗi. Nếu Lambda timeout ngắn hơn Task timeout, Step Functions có thể nhận lỗi từ Lambda trước khi Task timeout.

Trong test, kiểm tra cả hai trường hợp:

- Lambda trả lỗi trước khi Task timeout.
- Task hết thời gian chờ trong khi downstream operation chưa có kết quả rõ ràng.

Đừng giả định Task timeout tự dừng mọi hoạt động bên ngoài đã được Lambda khởi chạy. Mỗi side effect cần timeout, idempotency và cách tra cứu trạng thái riêng.

### 3.2. Heartbeat timeout

Với callback hoặc task pattern cần worker chạy lâu, HeartbeatSeconds giới hạn khoảng thời gian giữa các tín hiệu heartbeat. Worker có thể gửi heartbeat bằng API SendTaskHeartbeat để báo rằng công việc vẫn đang tiến triển.

Cần kiểm thử:

- Heartbeat đến trước deadline.
- Heartbeat bị trễ hơn HeartbeatSeconds.
- Worker gửi heartbeat bằng token sai.
- Worker dừng đột ngột và không còn gửi heartbeat.
- Heartbeat đến sau khi task đã timeout.

Heartbeat không thay thế TimeoutSeconds. Heartbeat phát hiện worker ngừng tiến triển; task timeout vẫn đặt giới hạn tổng thời gian state được phép chạy.

### 3.3. Business deadline

Một quy trình có thể có deadline nghiệp vụ dài hơn một invocation, ví dụ payment phải được xác nhận trong 30 phút. Không nên giữ một Lambda chạy suốt 30 phút chỉ để chờ.

Dùng Wait state, callback task hoặc một workflow stateful để chờ. Khi deadline đến, workflow có thể truy vấn trạng thái provider, hủy yêu cầu hoặc chuyển sang nhánh xử lý ngoại lệ.

Test phải xác minh deadline được tính theo thời gian nghiệp vụ và timezone thống nhất. Tránh dựa vào đồng hồ local của container nếu workflow và provider dùng timestamp UTC.

## 4. Thiết kế timeout có thể kiểm thử

Timeout quá dài khiến test suite chậm và khó tái hiện lỗi. Timeout quá ngắn có thể tạo race condition không giống production. Hãy tách cấu hình theo môi trường nhưng giữ nguyên logic chuyển trạng thái.

Ví dụ Task state chờ callback:

~~~json
{
  "WaitForApproval": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
    "Parameters": {
      "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:request-approval:test",
      "Payload": {
        "taskToken.$": "$$.Task.Token",
        "orderId.$": "$.orderId",
        "correlationId.$": "$.correlationId"
      }
    },
    "TimeoutSeconds": 30,
    "HeartbeatSeconds": 10,
    "Next": "ProcessApproval",
    "Catch": [
      {
        "ErrorEquals": ["States.Timeout"],
        "ResultPath": "$.approvalTimeout",
        "Next": "ExpireApproval"
      }
    ]
  }
}
~~~

Các giá trị 30 và 10 giây chỉ phù hợp với test fixture. Production cần deadline theo SLA và giới hạn của dịch vụ. Callback integration pattern này dành cho Standard workflows; Express workflows không hỗ trợ callback task token integration.

Một test nên dùng state machine definition riêng cho test hoặc parameter hóa timeout để rút ngắn thời gian. Không sửa trực tiếp timeout production chỉ để test chạy nhanh.

### 4.1. Test timeout theo ranh giới

Tạo các tình huống ở gần deadline:

- Callback đến sớm hơn timeout một khoảng nhỏ.
- Callback đến đúng lúc timeout có thể xảy ra.
- Callback đến sau timeout.
- Worker gửi heartbeat ngay trước deadline.
- Worker gửi heartbeat sau deadline.
- Lambda hoàn tất ngay trước Task timeout.
- Downstream response đến sau khi caller đã timeout.

Các trường hợp sát ranh giới giúp phát hiện race giữa callback, retry và timeout. Khi chạy integration test, lưu timestamp UTC, execution ARN, task token reference đã được che giấu và state transition để tái dựng thứ tự sự kiện.

## 5. Retry và Catch phải được kiểm thử cùng timeout

Retry có thể biến một lỗi tạm thời thành thành công, nhưng cũng có thể lặp side effect. Catch quyết định nhánh xử lý sau khi retry hết hoặc lỗi không khớp policy.

Ví dụ Task thanh toán:

~~~json
{
  "ChargePayment": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke",
    "Parameters": {
      "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:charge-payment:test",
      "Payload.$": "$"
    },
    "Retry": [
      {
        "ErrorEquals": [
          "Lambda.ServiceException",
          "Lambda.AWSLambdaException",
          "Lambda.SdkClientException",
          "Lambda.TooManyRequestsException"
        ],
        "IntervalSeconds": 1,
        "BackoffRate": 2.0,
        "MaxAttempts": 2
      }
    ],
    "Catch": [
      {
        "ErrorEquals": ["Payment.Declined"],
        "ResultPath": "$.paymentError",
        "Next": "ReleaseInventory"
      },
      {
        "ErrorEquals": ["States.Timeout"],
        "ResultPath": "$.paymentTimeout",
        "Next": "ReconcilePayment"
      },
      {
        "ErrorEquals": ["States.ALL"],
        "ResultPath": "$.unexpectedError",
        "Next": "ManualRecovery"
      }
    ],
    "Next": "CreateShipment"
  }
}
~~~

Tên lỗi trong ErrorEquals phải khớp với error name thực tế mà Lambda integration trả về. Không chỉ kiểm tra message text trong exception Java. Hãy xem execution history hoặc test response để xác minh error name và cause.

MaxAttempts là số lần retry thêm sau lần thử ban đầu. Với MaxAttempts bằng 2, Task có thể được thực hiện tối đa ba lần: một lần đầu và hai lần retry. Khi test, ghi số lần handler được gọi để tránh hiểu nhầm.

### 5.1. Test lỗi tạm thời và lỗi vĩnh viễn

| Tình huống | Kết quả mong đợi |
|---|---|
| Throttling một lần rồi thành công | Retry rồi đi tiếp |
| Service unavailable đến hết retry | Chuyển Catch tương ứng |
| Payment declined | Không retry lỗi nghiệp vụ; giải phóng reservation |
| Thiếu quyền IAM | Thất bại và báo lỗi cấu hình |
| Timeout nhưng payment có thể đã thành công | Reconcile bằng payment reference/idempotency key |
| Input sai schema | Đi nhánh từ chối hoặc xử lý lỗi dữ liệu |
| Lỗi compensation | Chuyển manual recovery và phát cảnh báo |

Không dùng States.ALL như bảo đảm bắt được mọi lỗi trong mọi hoàn cảnh. Một số lỗi đặc biệt của Step Functions có quy tắc bắt riêng. Hãy kiểm tra error name thực tế và thiết kế state machine theo loại lỗi cần xử lý.

### 5.2. Exponential backoff và test thời gian

Với IntervalSeconds và BackoffRate, khoảng chờ tăng qua các lần retry. Test không chỉ xác minh số lần gọi mà còn cần kiểm tra policy được cấu hình đúng. Nếu có MaxDelaySeconds hoặc JitterStrategy trong phiên bản dịch vụ đang dùng, kiểm tra giới hạn và độ phân tán của thời gian retry.

Không nên viết unit test phụ thuộc vào sleep thật dài. Kiểm tra cấu trúc ASL và dùng integration test với interval ngắn. Đo thời điểm invocation trong test để phát hiện retry xảy ra quá sớm hoặc quá dày.

## 6. Callback task token: luồng hoạt động

Callback pattern phù hợp khi Step Functions cần chờ một thành phần bên ngoài hoàn tất công việc. Một Lambda khởi tạo công việc, nhận task token trong payload, lưu token ở backend đáng tin cậy rồi gửi yêu cầu cho worker hoặc đối tác. Khi hoàn tất, callback service gọi Step Functions.

~~~mermaid
sequenceDiagram
    participant SF as Step Functions
    participant L as Request Lambda
    participant Q as Queue / Approval store
    participant W as External worker
    SF->>L: Invoke với task token
    L->>Q: Lưu yêu cầu + token bảo vệ
    L-->>SF: Lambda invocation kết thúc
    SF->>SF: Task chờ callback
    Q->>W: Chuyển công việc
    W->>W: Xử lý hoặc chờ phê duyệt
    W->>SF: SendTaskSuccess / SendTaskFailure
    SF->>SF: Tiếp tục state tiếp theo
~~~

Task token là credential dạng bearer: ai có token và quyền gọi callback API phù hợp có thể cố gắng hoàn tất task. Không gửi token ra trình duyệt hoặc cho người dùng cuối. Không ghi token vào log, metric, URL hay event công khai.

Callback service cần xác thực người gửi, kiểm tra approval/job ID, kiểm tra quyền và ánh xạ kết quả về đúng task token. Token nên được lưu có kiểm soát, mã hóa khi lưu và xóa sau khi task kết thúc.

## 7. Kiểm thử callback success và failure

Với một callback task, cần ít nhất các tình huống:

1. Worker gửi SendTaskSuccess với output hợp lệ.
2. Worker gửi SendTaskFailure với error/cause có cấu trúc.
3. Worker không gửi callback và Task timeout.
4. Worker gửi callback bằng token không hợp lệ.
5. Worker gửi callback hai lần.
6. Callback đến sau khi execution đã kết thúc.
7. Hai worker cùng cố hoàn tất một approval.
8. Callback service lưu kết quả thành công nhưng gặp lỗi trước khi gọi Step Functions.
9. Step Functions đã nhận callback nhưng callback service mất response.
10. Callback output vượt giới hạn payload hoặc sai schema.

### 7.1. Kiểm thử callback trùng

Callback có thể được gửi lại khi client không nhận được response của SendTaskSuccess. Callback service cần lưu trạng thái xử lý và thiết kế hành động idempotent.

Ví dụ trạng thái approval:

~~~text
approval_id
execution_arn
task_token_reference
status: PENDING | APPROVED | REJECTED | CALLBACK_SENT
decision_id
updated_at
~~~

Khi nhận quyết định:

1. Kiểm tra approval còn PENDING.
2. Lưu quyết định và chuyển trạng thái bằng conditional update/transaction.
3. Gửi callback tới Step Functions.
4. Ghi nhận callback đã gửi hoặc xử lý trường hợp token đã được tiêu thụ.
5. Nếu process chết giữa bước 2 và 3, worker retry có thể tiếp tục gửi callback từ trạng thái đã lưu.

Không tạo task token mới khi retry callback. Token gắn với một Task execution cụ thể.

### 7.2. Heartbeat và worker còn sống

Nếu task cần heartbeat, worker phải gửi SendTaskHeartbeat bằng đúng token trước khi HeartbeatSeconds hết hạn. Test:

- Worker đang làm việc và heartbeat đều.
- Worker treo nhưng process vẫn sống.
- Heartbeat API bị lỗi tạm thời.
- Worker gửi heartbeat cho token đã hết hạn.
- Worker hoàn tất sau khi heartbeat timeout.

Khi heartbeat timeout, Step Functions có thể đánh dấu Task timeout. Hệ thống cần xác định worker còn chạy hay không và tránh để worker tiếp tục side effect sau khi workflow đã chuyển sang compensation. Có thể dùng lease hoặc cancellation flag ở backend để phối hợp dừng công việc.

## 8. Kiểm thử callback token an toàn

Token không nên được dùng làm khóa nghiệp vụ hoặc hiển thị trong báo cáo. Hãy lưu reference có kiểm soát và gắn token với execution ARN, approval ID và deadline.

Các test bảo mật cần có:

- Người dùng không có quyền không thể lấy token từ API.
- Một approval ID không thể được ghép với token của execution khác.
- Token hết hạn hoặc bị tiêu thụ không thể hoàn tất task lần nữa.
- Token không xuất hiện trong stdout, CloudWatch Logs hoặc tracing attribute.
- Token không được đưa vào URL hoặc query string.
- Callback endpoint xác thực caller và chống replay.
- Callback service chỉ có các quyền callback cần thiết như states:SendTaskSuccess, states:SendTaskFailure và states:SendTaskHeartbeat; áp dụng điều kiện IAM mà API hỗ trợ và không cấp quyền sửa state machine hoặc quản trị Step Functions nếu không cần.

Nếu token bị lộ, cần xem nó như credential bị xâm phạm. Giới hạn quyền IAM của callback service và thời gian sống của Task giúp giảm tác động.

## 9. Saga compensation: xác định điều gì cần bù

Compensation chỉ chạy cho những bước đã tạo side effect và cần được bù theo trạng thái thực tế.

Ví dụ:

| Forward action | Side effect | Compensation |
|---|---|---|
| Reserve inventory | Giữ số lượng hàng | Release reservation |
| Authorize payment | Tạo payment authorization | Void authorization |
| Capture payment | Thu tiền | Refund nếu nghiệp vụ cho phép |
| Create shipment | Tạo vận đơn | Cancel shipment nếu provider hỗ trợ |
| Send email | Email đã được gửi | Không thể thu hồi; có thể gửi thông báo đính chính |

Không phải mọi side effect đều có thể đảo ngược hoàn toàn. Compensation có thể tạo một trạng thái nghiệp vụ mới, ví dụ payment REFUNDED, thay vì xóa lịch sử payment.

Một workflow nên lưu ID của từng side effect ngay sau khi bước forward thành công. Compensation dùng ID đó để tác động đúng tài nguyên. Không tìm đối tượng cần bù chỉ bằng thông tin không ổn định như timestamp hoặc thứ tự log.

### 9.1. Thứ tự compensation

Với Saga tuần tự, compensation thường chạy theo thứ tự ngược của các bước đã hoàn tất:

~~~text
Reserve inventory
    -> Authorize payment
        -> Create shipment (fails)

Compensation:
    Cancel shipment nếu đã tạo một phần
    -> Void/refund payment
        -> Release inventory
~~~

Thứ tự thực tế phụ thuộc quan hệ nghiệp vụ. Ví dụ, có thể cần hủy shipment trước khi refund payment. Hãy xác định dependency và trạng thái provider thay vì mặc định đảo ngược máy móc.

Test các điểm lỗi sau mỗi forward step:

- Reserve thất bại: không được release reservation chưa tạo.
- Payment thất bại: release reservation nếu reservation đã thành công.
- Shipment thất bại: bù payment và reservation.
- Notification thất bại: quyết định notification có phải bước bắt buộc hay được retry riêng.
- Compensation thất bại: giữ trạng thái COMPENSATION_REQUIRED và chuyển recovery.

## 10. Compensation phải idempotent

Một compensation có thể được retry khi API ngoài timeout hoặc callback bị gửi lại. Vì vậy, compensation cũng phải idempotent.

Ví dụ, gọi releaseReservation(reservationId) hai lần không được giải phóng hai lần hoặc làm sai số lượng tồn kho. Hệ thống tồn kho có thể trả kết quả đã giải phóng nếu reservation đã ở trạng thái RELEASED.

Dùng khóa ổn định cho từng hành động bù:

~~~text
saga_id = order-1042
compensation_key = release-inventory:order-1042
resource_id = reservation-771
~~~

Lưu trạng thái compensation:

~~~text
saga_id
step_name
compensation_key
resource_id
status: PENDING | RUNNING | SUCCEEDED | FAILED
attempt_count
last_error
updated_at
~~~

Dùng unique constraint hoặc conditional update để hai worker không thực hiện compensation cùng lúc. Nếu provider hỗ trợ idempotency key, truyền cùng một key qua mọi lần retry.

### 10.1. Java compensation handler

Ví dụ interface nghiệp vụ:

~~~java
public interface InventoryClient {
    void releaseReservation(String reservationId, String idempotencyKey);
}

public interface CompensationStore {
    boolean claim(String compensationKey);
    void markSucceeded(String compensationKey);
    void markRetryableFailure(String compensationKey, String reason);
}

public final class ReleaseInventoryHandler {

    private final InventoryClient inventory;
    private final CompensationStore store;

    public ReleaseInventoryHandler(
            InventoryClient inventory,
            CompensationStore store) {
        this.inventory = inventory;
        this.store = store;
    }

    public void release(String sagaId, String reservationId) {
        String key = "release-inventory:" + sagaId;

        if (!store.claim(key)) {
            return; // Đã hoàn tất hoặc một worker khác đang sở hữu.
        }

        try {
            inventory.releaseReservation(reservationId, key);
            store.markSucceeded(key);
        } catch (RuntimeException error) {
            store.markRetryableFailure(key, error.getClass().getSimpleName());
            throw error;
        }
    }
}
~~~

Đây là ví dụ rút gọn. Trong production, claim cần phân biệt đã thành công, đang có lease hợp lệ và lease đã hết hạn; không thể chỉ trả boolean nếu caller cần xử lý các trạng thái khác nhau. Nếu inventory update và ghi compensation status nằm cùng database, dùng transaction. Nếu gọi provider ngoài, dựa vào idempotency key và quy trình reconcile khi kết quả không rõ.

Không đánh dấu compensation thành công trước khi provider xác nhận. Nếu ghi SUCCEEDED trước rồi process chết trước side effect, workflow sẽ bỏ qua bước bù dù reservation vẫn còn.

## 11. Kiểm thử compensation thành công và thất bại

Một test matrix tối thiểu:

| Tình huống | Kết quả mong đợi |
|---|---|
| Forward step lỗi trước side effect | Không gọi compensation tương ứng |
| Forward step thành công, bước sau lỗi | Gọi compensation theo thứ tự đã thiết kế |
| Compensation thành công | Ghi trạng thái SUCCEEDED |
| Compensation timeout sau khi provider đã thực hiện | Retry với cùng idempotency key, không bù hai lần |
| Compensation trả lỗi tạm thời | Retry có giới hạn |
| Compensation lỗi vĩnh viễn | Manual recovery và alert |
| Compensation được gọi hai lần | Kết quả nghiệp vụ không đổi sau lần đầu |
| Hai execution cùng bù một resource | Chỉ một hành động bù được commit |
| Worker chết sau provider success trước khi lưu status | Retry/reconcile nhận ra side effect đã hoàn tất |
| Một compensation trong chuỗi thất bại | Ghi rõ bước nào còn cần phục hồi |

Test phải kiểm tra cả trạng thái trong database và số lần gọi provider. Chỉ verify lời gọi releaseReservation là chưa đủ nếu không kiểm tra kết quả nghiệp vụ cuối cùng.

## 12. Reconcile khi kết quả không rõ ràng

Một tình huống khó là provider đã thực hiện side effect nhưng response bị mất. Ví dụ payment provider đã thu tiền, Lambda timeout trước khi nhận response. Workflow không biết payment thành công hay thất bại.

Không được mặc định timeout đồng nghĩa thao tác thất bại. Cần một bước reconcile:

1. Tạo idempotency key ổn định trước khi gọi provider.
2. Gọi provider với key đó.
3. Nếu response rõ ràng, lưu provider transaction ID và trạng thái.
4. Nếu timeout, truy vấn provider theo idempotency key hoặc transaction reference.
5. Nếu đã thành công, tiếp tục workflow hoặc chạy compensation phù hợp.
6. Nếu chưa có giao dịch, retry với cùng key.
7. Nếu trạng thái vẫn không rõ, chuyển manual recovery thay vì tạo giao dịch mới.

Reconcile là một phần của workflow và phải được test. Mô phỏng mất response sau side effect là một trong những fault injection quan trọng nhất.

## 13. Unit test Java cho idempotency và compensation

Unit test kiểm tra logic handler mà không cần khởi chạy Step Functions. Có thể dùng JUnit 5 và Mockito để mô phỏng inventory/payment provider cùng store.

Ví dụ kiểm tra compensation chỉ gọi provider khi claim thành công:

~~~java
import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.*;

class ReleaseInventoryHandlerTest {

    @Test
    void releasesInventoryWhenClaimSucceeds() {
        InventoryClient inventory = mock(InventoryClient.class);
        CompensationStore store = mock(CompensationStore.class);

        when(store.claim("release-inventory:order-1042"))
                .thenReturn(true);

        ReleaseInventoryHandler handler =
                new ReleaseInventoryHandler(inventory, store);

        handler.release("order-1042", "reservation-771");

        verify(inventory).releaseReservation(
                "reservation-771",
                "release-inventory:order-1042");
        verify(store).markSucceeded("release-inventory:order-1042");
    }

    @Test
    void skipsProviderWhenCompensationIsAlreadyClaimed() {
        InventoryClient inventory = mock(InventoryClient.class);
        CompensationStore store = mock(CompensationStore.class);

        when(store.claim("release-inventory:order-1042"))
                .thenReturn(false);

        ReleaseInventoryHandler handler =
                new ReleaseInventoryHandler(inventory, store);

        handler.release("order-1042", "reservation-771");

        verifyNoInteractions(inventory);
        verify(store, never()).markSucceeded(anyString());
    }
}
~~~

Test thứ hai chỉ phù hợp nếu claim=false được định nghĩa là đã hoàn tất hoặc đang được worker khác xử lý và handler có thể an toàn bỏ qua. Trong implementation thật, nên dùng kết quả claim rõ ràng như ALREADY_SUCCEEDED, CLAIMED_BY_OTHER hoặc LEASE_EXPIRED để không vô tình bỏ qua compensation còn pending.

Bổ sung test khi provider ném lỗi:

- Store ghi trạng thái retryable failure.
- Exception được ném lại để Step Functions thấy Task thất bại.
- Retry dùng cùng idempotency key.
- Lỗi permanent không bị retry vô hạn.

## 14. Kiểm thử state machine theo từng lớp

Không có một công cụ duy nhất kiểm chứng mọi phần của workflow. Hãy dùng nhiều lớp test với phạm vi rõ ràng.

| Lớp kiểm thử | Công cụ/cách làm | Kiểm chứng |
|---|---|---|
| Java unit test | JUnit, Mockito, fake clock | Logic nghiệp vụ, retry classification, idempotency và compensation |
| ASL validation | Step Functions definition validation | Cú pháp và cấu trúc state machine |
| State-level test | Step Functions TestState API | Một state với input và mock integration |
| Local simulation | Step Functions Local hoặc emulator phù hợp | Một phần state transition và luồng điều khiển |
| AWS integration test | State machine thật trong account test | IAM, Lambda integration, callback, timeout và execution history |
| End-to-end test | API/event đầu vào đến trạng thái nghiệp vụ cuối | Hành vi toàn quy trình và dependency thực |

TestState giúp kiểm thử một state mà không cần chạy toàn bộ execution. Có thể dùng mock integration để mô phỏng response/error của một số service integration. Nó không thay thế integration test cho toàn state machine.

Step Functions Local hữu ích cho mô phỏng cục bộ nhưng không có đầy đủ parity với dịch vụ AWS thật và có thể không hỗ trợ mọi integration hoặc tính năng mới. Không dùng kết quả local làm bằng chứng rằng IAM, callback token, heartbeat hoặc timeout trên AWS đã đúng.

### 14.1. Validate ASL trước khi chạy

Trước khi deploy, kiểm tra định nghĩa state machine bằng validation API/CLI hoặc công cụ IaC. Các lỗi cần phát hiện:

- StartAt trỏ đến state không tồn tại.
- Next trỏ đến state không tồn tại.
- State thiếu trường bắt buộc.
- Retry hoặc Catch có cấu trúc sai.
- Path JSONPath không khớp input.
- ResultPath ghi đè dữ liệu cần thiết.
- Callback resource ARN sai.
- Task timeout hoặc heartbeat không hợp lệ.

Validation cấu trúc không chứng minh Lambda payload hoặc business contract đúng. Cần test input/output riêng cho từng Task.

### 14.2. TestState và mock integration

Với TestState, có thể truyền state definition, input và mock service integration để kiểm tra:

- Task nhận đúng payload.
- ResultSelector lấy đúng phần output.
- ResultPath lưu kết quả đúng vị trí.
- Choice đi đúng nhánh.
- Retry/Catch phản ứng đúng với error mock.
- State trả output như dự kiến.

Mock giúp test deterministic và nhanh. Tuy nhiên, mock không chứng minh downstream service thật trả cùng schema hoặc error name. Hãy bổ sung contract test hoặc integration test với dependency thật ở môi trường cô lập.

## 15. Integration test với AWS Step Functions

Một integration test đầy đủ có thể:

1. Deploy một state machine test và các Lambda test.
2. Gắn IAM role chỉ có quyền cần thiết.
3. Tạo input với execution ID hoặc test correlation ID riêng.
4. Gọi StartExecution.
5. Theo dõi DescribeExecution hoặc execution history.
6. Xác minh trạng thái cuối và các state đã chạy.
7. Đọc database/provider sandbox để xác minh side effect.
8. Dọn dữ liệu test sau khi xác nhận.

Không dùng production payment, customer hoặc inventory thật trong test timeout/compensation. Dùng sandbox provider, database riêng hoặc stub có fault injection.

Đặt execution name duy nhất cho mỗi test run. Gắn correlation ID vào input để tìm execution và log. Không đưa token hoặc secret vào execution input.

Với Standard workflow, execution history có thể giúp xác định state nào đã chạy, retry bao nhiêu lần và lỗi nào xảy ra. Log và history có thể chứa input/output tùy cấu hình; không đưa secret hoặc task token vào dữ liệu dễ truy cập.

## 16. Fault injection cho workflow

Fault injection tạo lỗi có kiểm soát để kiểm tra hệ thống phục hồi. Có thể dùng test Lambda nhận scenario trong input hoặc mock integration để tạo các lỗi như:

~~~text
scenario=PAYMENT_THROTTLED_ONCE
scenario=PAYMENT_DECLINED
scenario=PAYMENT_SIDE_EFFECT_THEN_TIMEOUT
scenario=CALLBACK_NEVER_ARRIVES
scenario=CALLBACK_DUPLICATED
scenario=REFUND_TIMEOUT_AFTER_SUCCESS
scenario=RELEASE_INVENTORY_DENIED
~~~

Các scenario phải chỉ tồn tại trong test environment và không được bật bằng input công khai ở production.

Test các lỗi tại từng ranh giới:

- Trước khi side effect bắt đầu.
- Sau khi side effect thành công nhưng trước khi response được ghi nhận.
- Sau khi callback service lưu quyết định nhưng trước khi gọi Step Functions.
- Sau khi callback được chấp nhận nhưng trước khi client nhận response.
- Trong lúc compensation chạy.
- Sau khi compensation thành công nhưng trước khi trạng thái được lưu.

Các điểm lỗi này giúp phát hiện những khoảng trống giữa hai hệ thống không chia sẻ transaction.

## 17. Bộ test case đề xuất

| ID | Kịch bản | Kiểm tra chính |
|---|---|---|
| WF-01 | Happy path | Tất cả state hoàn tất theo đúng thứ tự |
| WF-02 | Lambda lỗi tạm thời một lần | Retry rồi tiếp tục |
| WF-03 | Lambda lỗi hết retry | Catch chuyển đúng nhánh |
| WF-04 | Task timeout | Execution đi nhánh timeout hoặc thất bại đúng policy |
| WF-05 | Callback success | Workflow tiếp tục state sau callback |
| WF-06 | Callback failure | Catch xử lý lỗi callback |
| WF-07 | Callback không đến | Task timeout theo deadline |
| WF-08 | Callback đến trễ | Token bị từ chối; không tạo side effect mới |
| WF-09 | Callback trùng | Một quyết định nghiệp vụ được commit |
| WF-10 | Heartbeat bị mất | Task timeout theo heartbeat policy |
| WF-11 | Payment timeout không rõ kết quả | Reconcile trước khi retry hoặc refund |
| WF-12 | Shipment thất bại | Refund/void payment rồi release inventory |
| WF-13 | Compensation lỗi | Chuyển manual recovery và alert |
| WF-14 | Compensation được gọi lại | Idempotency giữ nguyên trạng thái nghiệp vụ |
| WF-15 | Hai worker bù đồng thời | Chỉ một compensation được commit |
| WF-16 | Execution mới chạy lại batch | Không lặp side effect đã hoàn tất |
| WF-17 | IAM thiếu quyền callback | Lỗi được phát hiện và audit rõ |
| WF-18 | Payload callback không hợp lệ | Không chuyển workflow sang success |
| WF-19 | Execution bị dừng khi đang chờ | Worker xử lý token hết hiệu lực an toàn |
| WF-20 | Secret/token trong log | Không có credential nhạy cảm bị ghi ra |

Không nhất thiết chạy mọi test trong mỗi pull request. Có thể chia thành unit/state tests chạy thường xuyên và integration/fault tests chạy theo pipeline, nightly hoặc trước release. Những test liên quan đến payment, token và compensation cần có trong release gate phù hợp với mức rủi ro.

## 18. Xác minh execution history và business state

Sau mỗi integration test, kiểm tra:

- State nào bắt đầu và kết thúc.
- Input/output của state có đúng contract không.
- Retry count và khoảng thời gian retry.
- Error name, cause và Catch result.
- Task token callback có tiếp tục đúng state không.
- Task timeout hay heartbeat timeout xảy ra ở lớp nào.
- Compensation nào đã chạy và theo thứ tự nào.
- State cuối là SUCCEEDED, FAILED, TIMED_OUT hay trạng thái khác.
- Database có reservation/payment/shipment đúng trạng thái không.

Không chỉ kiểm tra DescribeExecution.status. Cần đối chiếu business store:

~~~text
Order: FAILED
Reservation: RELEASED
Payment: REFUNDED
Shipment: NOT_CREATED
Compensation:
  refund-payment: SUCCEEDED
  release-inventory: SUCCEEDED
~~~

Đây là một kết quả mẫu cho tình huống shipment thất bại sau khi payment đã được thu. Nếu refund thất bại, order có thể ở trạng thái COMPENSATION_REQUIRED và cần người vận hành can thiệp; không ghi thành FAILED_CLEANLY.

## 19. Tránh test flaky và cô lập dữ liệu

Workflow bất đồng bộ dễ tạo test flaky nếu test chỉ sleep một khoảng cố định rồi giả định execution đã hoàn tất.

Nên:

- Poll trạng thái execution với deadline và backoff ngắn.
- Chờ một state/condition cụ thể thay vì sleep cố định.
- Dùng execution name, batch ID và correlation ID riêng cho từng test.
- Tạo dữ liệu fixture có prefix riêng và dọn dẹp sau test.
- Không chạy song song test dùng chung order ID, payment reference hoặc reservation ID.
- Dùng clock abstraction trong Java khi logic nghiệp vụ tự tính deadline.
- Dùng timeout ngắn trong state machine test, nhưng giữ cấu trúc state tương đương production.
- Ghi lại execution ARN khi test fail để điều tra.

Polling cần có deadline tổng. Nếu hết deadline mà execution chưa kết thúc, test phải fail với execution ARN và trạng thái cuối quan sát được, không treo vô hạn.

## 20. Quy trình kiểm thử trước production

1. **Xác định state machine và business invariant.** Ghi rõ trạng thái hợp lệ của order, payment, inventory và shipment.
2. **Viết unit test cho Java handlers.** Kiểm tra input validation, error classification, idempotency và compensation.
3. **Validate ASL.** Kiểm tra state reference, JSONPath, Retry/Catch và callback resource.
4. **Test từng state.** Dùng TestState và mock integration cho payload/error branch.
5. **Test local.** Dùng local simulator cho luồng điều khiển được hỗ trợ.
6. **Deploy test stack.** Dùng IAM role, Lambda và database sandbox riêng.
7. **Test timeout/callback.** Kiểm tra success, failure, heartbeat, duplicate, late callback và token invalid.
8. **Fault injection.** Tạo lỗi trước/sau side effect và kiểm tra reconcile.
9. **Test compensation.** Xác minh thứ tự, idempotency, retry và manual recovery.
10. **Đối chiếu business state.** Kiểm tra database và provider sandbox cùng execution history.
11. **Kiểm tra observability.** Đảm bảo log có correlation ID nhưng không có token/secret.
12. **Chạy regression và release.** Lưu execution ARN, test report và release ID để truy nguyên.

Một workflow chỉ sẵn sàng khi cả luồng thành công lẫn các nhánh lỗi quan trọng đều có kết quả xác định. Với timeout và callback, cần chứng minh hệ thống xử lý được kết quả đến muộn hoặc trùng. Với compensation, cần chứng minh side effect được bù đúng một cách an toàn hoặc được chuyển sang manual recovery có thể quan sát.

## 21. Câu hỏi tự kiểm tra

- Vì sao kiểm thử riêng từng Lambda chưa đủ để xác minh workflow?
- Lambda timeout và Step Functions Task timeout khác nhau như thế nào?
- HeartbeatSeconds phát hiện loại sự cố nào?
- Vì sao timeout không chứng minh payment provider chưa thu tiền?
- Retry và Catch được áp dụng theo thứ tự nào?
- MaxAttempts bằng 2 có thể tạo tổng cộng bao nhiêu lần invocation?
- Callback task token có vai trò gì và vì sao cần bảo vệ như credential?
- Làm thế nào kiểm thử callback duplicate và callback đến trễ?
- Vì sao callback task token chỉ dùng được với Standard workflows?
- Compensation khác transaction rollback ở điểm nào?
- Làm sao bảo đảm compensation idempotent?
- Khi nào workflow cần reconcile thay vì retry ngay?
- TestState và Step Functions Local có giới hạn gì?
- Vì sao integration test cần kiểm tra business state ngoài execution status?
- Những điểm nào nên fault-inject để tìm race condition?

