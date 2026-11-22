# Điều phối Lambda bằng AWS Step Functions

Một ứng dụng serverless thường gồm nhiều Lambda function và dịch vụ AWS. Một yêu cầu nghiệp vụ có thể cần xác thực dữ liệu, kiểm tra tồn kho, thu tiền, tạo vận đơn và gửi thông báo. Nếu một function gọi tuần tự tất cả bước, nó sẽ phải tự quản lý thứ tự, timeout, retry, trạng thái và cách phục hồi khi một bước giữa chừng thất bại.

AWS Step Functions cung cấp workflow orchestration để điều phối các bước này bằng một state machine. State machine lưu tiến trình thực thi, gọi Lambda hoặc dịch vụ AWS khác, rẽ nhánh, chạy song song, chờ sự kiện và xử lý lỗi theo định nghĩa. Java function tập trung vào logic của từng bước, còn Step Functions quản lý luồng điều khiển và trạng thái workflow.

Bài học này trình bày cách thiết kế state machine, tích hợp Java Lambda, xử lý lỗi và chọn loại workflow phù hợp với workload thực tế.

## 1. Step Functions giải quyết vấn đề gì?

Khi nhiều function phối hợp với nhau, ứng dụng cần trả lời các câu hỏi:

- Bước nào chạy trước, bước nào chỉ chạy khi điều kiện được đáp ứng?
- Nếu một bước lỗi tạm thời, có nên retry và retry bao nhiêu lần?
- Nếu một bước thất bại sau khi bước trước đã tạo side effect, làm sao hoàn tác hoặc bù trừ?
- Làm thế nào chạy các bước độc lập song song?
- Làm thế nào chờ người duyệt hoặc hệ thống đối tác trong nhiều giờ mà không giữ Lambda chạy?
- Làm thế nào theo dõi một đơn hàng qua nhiều function?
- Khi workflow chạy lại, làm sao tránh tạo giao dịch hoặc gửi thông báo trùng?

Step Functions mô hình hóa các câu trả lời này thành state machine. Mỗi state thực hiện một hành động hoặc điều khiển luồng, rồi chuyển sang state tiếp theo.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu đặt hàng"] --> B["ValidateOrder Lambda"]
    B --> C{"Dữ liệu hợp lệ?"}
    C -->|Không| X["RejectOrder"]
    C -->|Có| D["ReserveInventory Lambda"]
    D --> E["ChargePayment Lambda"]
    E --> F{"Thanh toán thành công?"}
    F -->|Có| G["CreateShipment Lambda"]
    F -->|Không| H["ReleaseInventory Lambda"]
    H --> X
    G --> I["NotifyCustomer Lambda"]
    I --> J["Succeed"]
~~~

Không cần một Lambda duy nhất giữ toàn bộ luồng điều khiển. Mỗi Task state có thể gọi một function chuyên trách. Step Functions ghi nhận kết quả và quyết định state kế tiếp theo định nghĩa.

### 1.1. Orchestration và choreography

Có hai cách phổ biến để phối hợp dịch vụ:

- **Orchestration:** một bộ điều phối trung tâm biết các bước, thứ tự và trạng thái. Step Functions là dịch vụ orchestration.
- **Choreography:** các dịch vụ phát và nhận event; mỗi dịch vụ tự quyết định phản ứng với event mà không có một luồng điều khiển tập trung.

Orchestration phù hợp khi quy trình có thứ tự rõ, nhiều nhánh, timeout, retry, phê duyệt hoặc cần xem trạng thái đầu-cuối. Choreography phù hợp với các thành phần độc lập phản ứng với event và ít cần một luồng điều khiển tập trung.

Có thể kết hợp cả hai: Step Functions điều phối một quy trình nghiệp vụ lớn, còn một bước trong workflow phát event để các dịch vụ khác xử lý độc lập.

## 2. Thành phần của AWS Step Functions

Một workflow thường có các thành phần:

- **State machine:** định nghĩa quy trình và các state.
- **Execution:** một lần chạy cụ thể của state machine, có input, output, trạng thái và lịch sử.
- **State:** một bước hoặc một điểm điều khiển trong workflow.
- **Task:** gọi Lambda, tích hợp dịch vụ AWS hoặc thực hiện công việc bên ngoài.
- **Choice:** chọn nhánh dựa trên dữ liệu.
- **Parallel:** chạy nhiều nhánh đồng thời.
- **Map:** lặp qua một tập phần tử và xử lý từng phần tử.
- **Wait:** tạm dừng đến một khoảng thời gian hoặc thời điểm.
- **Succeed/Fail:** kết thúc workflow thành công hoặc thất bại.
- **Retry/Catch:** định nghĩa cách xử lý lỗi tại một state.

Định nghĩa state machine được viết bằng Amazon States Language (ASL), thường biểu diễn dưới dạng JSON. Có thể tạo và triển khai state machine bằng AWS Console, AWS CLI, CloudFormation, AWS CDK hoặc Terraform.

Một state machine có StartAt để chỉ state đầu tiên và States chứa định nghĩa các state. Mỗi state có Type và các trường tương ứng với loại state đó. State chuyển tiếp bằng Next, kết thúc bằng End: true, hoặc chọn nhánh bằng cấu trúc riêng.

## 3. Các loại state thường dùng

| Loại state | Vai trò | Ví dụ |
|---|---|---|
| Task | Thực hiện công việc hoặc gọi dịch vụ | Gọi Java Lambda kiểm tra đơn hàng |
| Choice | Rẽ nhánh theo điều kiện | Thanh toán thành công hay thất bại |
| Pass | Chuyển dữ liệu hoặc tạo dữ liệu tĩnh | Gắn metadata vào input |
| Wait | Chờ một khoảng thời gian hoặc đến thời điểm | Chờ 15 phút trước khi kiểm tra lại |
| Parallel | Chạy nhiều nhánh độc lập | Tính thuế và kiểm tra địa chỉ cùng lúc |
| Map | Lặp qua danh sách phần tử | Xử lý từng dòng trong đơn hàng |
| Succeed | Kết thúc thành công | Đơn hàng đã hoàn tất |
| Fail | Kết thúc thất bại | Dữ liệu đầu vào không hợp lệ |

Task thường là state kết nối Step Functions với Lambda hoặc một dịch vụ AWS. Choice điều khiển luồng mà không cần viết một function chỉ để kiểm tra điều kiện. Parallel và Map giúp khai thác xử lý đồng thời, nhưng cần giới hạn concurrency và cân nhắc tải lên dịch vụ phụ thuộc.

## 4. Gọi Java Lambda bằng optimized integration

Step Functions có optimized integration cho Lambda. Với request-response, state machine gọi Lambda và chờ invocation trả kết quả trước khi chuyển sang state tiếp theo.

Resource thường dùng:

~~~text
arn:aws:states:::lambda:invoke
~~~

Một Task state có thể truyền input workflow vào payload của Lambda:

~~~json
{
  "StartAt": "ValidateOrder",
  "States": {
    "ValidateOrder": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:validate-order:prod",
        "Payload.$": "$"
      },
      "ResultSelector": {
        "validation.$": "$.Payload"
      },
      "ResultPath": "$.validationResult",
      "Next": "CheckValidation"
    },
    "CheckValidation": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.validationResult.validation.valid",
          "BooleanEquals": true,
          "Next": "OrderAccepted"
        }
      ],
      "Default": "OrderRejected"
    },
    "OrderAccepted": {
      "Type": "Succeed"
    },
    "OrderRejected": {
      "Type": "Fail",
      "Error": "Order.Invalid",
      "Cause": "Order validation failed"
    }
  }
}
~~~

Ví dụ dùng cú pháp JSONPath và chỉ minh họa cấu trúc. Thay REGION, ACCOUNT và tên function bằng giá trị trong môi trường triển khai. Trường FunctionName có thể tham chiếu function, version hoặc alias. Dùng alias như prod giúp workflow gắn với phiên bản triển khai có chủ đích.

Khi dùng optimized integration, kết quả invoke được Step Functions biểu diễn trong response object, trong đó payload Lambda nằm ở Payload. ResultSelector chọn phần dữ liệu cần giữ, còn ResultPath xác định nơi gắn kết quả vào state input. Nếu không chọn lọc, workflow có thể mang theo metadata không cần thiết qua nhiều state.

### 4.1. Request-response và gọi Lambda bất đồng bộ

Mặc định optimized Lambda integration chờ Lambda hoàn tất và nhận kết quả. Đây là lựa chọn phù hợp khi bước tiếp theo cần output của function.

Nếu muốn phát invocation bất đồng bộ, có thể cấu hình tham số invocation phù hợp với API Lambda, chẳng hạn InvocationType: Event trong Parameters theo integration contract. Khi đó Step Functions chỉ biết yêu cầu invoke đã được gửi đi, không chờ kết quả nghiệp vụ cuối cùng của function. Nếu cần theo dõi hoàn tất, hãy dùng callback, queue, event hoặc workflow khác để báo kết quả.

Đừng dùng bất đồng bộ chỉ để tránh timeout mà không có cơ chế theo dõi. Nếu workflow cần biết tác vụ đã hoàn tất hay thất bại, phải có một tín hiệu tiếp tục rõ ràng.

## 5. Java Lambda làm một bước trong workflow

Java function nên nhận một input có schema rõ ràng và trả về một kết quả nhỏ, có cấu trúc. Không cần biết toàn bộ state machine nếu function chỉ phụ trách một nghiệp vụ.

Ví dụ một Lambda xác thực đơn hàng:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

public class ValidateOrderHandler
        implements RequestHandler<OrderInput, ValidationResult> {

    @Override
    public ValidationResult handleRequest(
            OrderInput input,
            Context context) {

        if (input == null || input.getOrderId() == null
                || input.getItems() == null || input.getItems().isEmpty()) {
            return new ValidationResult(false, "INVALID_ORDER");
        }

        return new ValidationResult(true, "OK");
    }
}
~~~

OrderInput và ValidationResult là các POJO do ứng dụng định nghĩa, có constructor/getter/setter phù hợp với serializer đang dùng. Ví dụ không bao gồm toàn bộ class model để tập trung vào contract của function.

Một input có thể chứa:

~~~json
{
  "orderId": "order-2026-00421",
  "customerId": "customer-42",
  "items": [
    {
      "sku": "book-101",
      "quantity": 2
    }
  ],
  "correlationId": "req-7d2a"
}
~~~

Output nên chỉ chứa dữ liệu cần cho bước sau, ví dụ valid, reasonCode hoặc một resource ID. Tránh đưa binary lớn, dữ liệu nhạy cảm hoặc toàn bộ bản ghi database vào state input/output.

### 5.1. Không phụ thuộc vào trạng thái trong memory

Một Task có thể được retry hoặc chạy trên execution environment khác. Vì vậy, không lưu trạng thái nghiệp vụ quan trọng chỉ trong biến static hoặc field của object handler. Hãy lưu vào database hoặc dịch vụ bền vững.

Có thể tái sử dụng HTTP client hoặc AWS SDK client thread-safe ở phạm vi process để giảm khởi tạo, nhưng dữ liệu riêng của execution phải nằm trong input hoặc kho trạng thái có kiểm soát. Đừng giả định một Lambda instance luôn xử lý cùng một workflow hoặc chỉ có một invocation.

## 6. Chuyển dữ liệu giữa các state

State machine truyền JSON input/output qua từng state. Với JSONPath, một số trường thường dùng:

- InputPath: chọn phần input đưa vào state.
- Parameters: tạo input cho Task hoặc state từ dữ liệu hiện có.
- ResultSelector: chọn phần kết quả trả về.
- ResultPath: đặt kết quả vào input hiện tại.
- OutputPath: chọn dữ liệu đưa sang state tiếp theo.

Ví dụ, input ban đầu có thông tin đơn hàng và metadata. Lambda chỉ cần phần order, nên có thể truyền một object con thay vì toàn bộ input. Sau khi Lambda trả kết quả, workflow có thể lưu kết quả vào validationResult và vẫn giữ orderId để dùng ở bước tiếp theo.

~~~text
Input workflow
    |
    +-- order
    +-- customer
    +-- correlationId
          |
          v
Parameters -> Lambda Payload
          |
          v
Lambda result
          |
          v
ResultSelector -> ResultPath
          |
          v
Output state tiếp theo
~~~

Nếu không kiểm soát kích thước dữ liệu, state input/output có thể tăng qua từng bước. Step Functions có giới hạn payload cho state input/output (hiện phổ biến là 256 KiB cho mỗi state/execution payload; hãy kiểm tra quota hiện hành của dịch vụ). Với file hoặc dữ liệu lớn, lưu nội dung trong S3 rồi truyền object key, version và metadata cần thiết.

Không đưa secret, access token hoặc dữ liệu cá nhân không cần thiết vào execution input vì dữ liệu có thể xuất hiện trong execution history và log tùy cấu hình. Dùng Secrets Manager, Parameter Store hoặc IAM role để lấy thông tin bí mật khi cần.

## 7. Rẽ nhánh với Choice

Choice state chọn bước tiếp theo dựa trên dữ liệu. Ví dụ, sau khi kiểm tra đơn hàng, workflow chỉ tiếp tục nếu valid là true.

~~~json
{
  "CheckPayment": {
    "Type": "Choice",
    "Choices": [
      {
        "Variable": "$.payment.status",
        "StringEquals": "SUCCEEDED",
        "Next": "CreateShipment"
      },
      {
        "Variable": "$.payment.status",
        "StringEquals": "PENDING",
        "Next": "WaitForPayment"
      }
    ],
    "Default": "PaymentFailed"
  }
}
~~~

Choice không tự thực hiện nghiệp vụ; nó chỉ quyết định state tiếp theo. Nên luôn có Default để xử lý giá trị thiếu hoặc không khớp. Nếu không, workflow có thể lỗi khi dữ liệu không đúng giả định.

Không dùng Choice để thay thế authorization. Việc một field trong input có giá trị approved=true không chứng minh người dùng có quyền phê duyệt. Kết quả phải được tạo bởi bước xác thực có thẩm quyền và lưu bền vững.

## 8. Retry và Catch khi Lambda lỗi

Trong hệ thống phân tán, Lambda có thể gặp lỗi tạm thời như throttling, service unavailable, network timeout hoặc lỗi phụ thuộc. Step Functions cho phép định nghĩa Retry để thử lại Task và Catch để chuyển sang nhánh xử lý lỗi.

~~~json
{
  "ChargePayment": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke",
    "Parameters": {
      "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:charge-payment:prod",
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
        "IntervalSeconds": 2,
        "BackoffRate": 2.0,
        "MaxAttempts": 3
      }
    ],
    "Catch": [
      {
        "ErrorEquals": ["States.ALL"],
        "ResultPath": "$.taskError",
        "Next": "HandlePaymentError"
      }
    ],
    "End": true
  }
}
~~~

Các error name cần khớp với lỗi được integration/runtime trả về. Retry được đánh giá trước Catch: Step Functions thử lại theo policy, sau khi hết lần thử hoặc gặp lỗi không khớp mới chuyển sang catcher phù hợp.

Một số thuộc tính quan trọng:

- IntervalSeconds: thời gian chờ trước lần retry đầu tiên.
- BackoffRate: hệ số tăng thời gian chờ giữa các lần thử.
- MaxAttempts: số lần thử lại tối đa theo định nghĩa retrier.
- MaxDelaySeconds: giới hạn thời gian chờ nếu được hỗ trợ.
- JitterStrategy: thêm ngẫu nhiên vào backoff nếu được hỗ trợ.
- ErrorEquals: nhóm lỗi áp dụng policy.

Không retry mọi lỗi. Lỗi validation, thiếu quyền hoặc trạng thái nghiệp vụ không hợp lệ thường không tự hết khi thử lại. Chỉ retry lỗi có khả năng tạm thời và đặt giới hạn để tránh retry storm.

### 8.1. Idempotency khi retry

Step Functions có thể gọi lại Task theo policy. Một lần Lambda có thể đã tạo side effect rồi bị timeout trước khi Step Functions nhận được kết quả. Nếu retry mà không có idempotency, function có thể trừ tiền hoặc tạo đơn hàng hai lần.

Với thao tác không idempotent:

- Truyền executionId, orderId hoặc một idempotency key ổn định.
- Lưu kết quả thao tác cùng khóa trong database.
- Dùng unique constraint hoặc conditional write để chỉ một lần được thực hiện.
- Khi nhận lại cùng key, trả kết quả đã ghi trước đó.
- Không tạo key mới cho mỗi lần retry.

Context object của Step Functions có thể cung cấp execution ID để dùng trong ASL. Tuy nhiên, một execution có thể có nhiều thao tác nghiệp vụ; nên kết hợp execution ID với step hoặc resource ID để tạo khóa đủ chi tiết.

### 8.2. Catch và nhánh bù trừ

Nếu đã giữ tồn kho nhưng thanh toán thất bại, workflow cần gọi bước giải phóng tồn kho. Đây là một hành động bù trừ (compensation), không phải rollback transaction tự động xuyên qua nhiều dịch vụ.

~~~mermaid
flowchart TD
    A["ReserveInventory"] --> B["ChargePayment"]
    B -->|Thành công| C["CreateShipment"]
    B -->|Thất bại| D["ReleaseInventory"]
    D --> E["MarkOrderFailed"]
    C --> F["MarkOrderConfirmed"]
~~~

Bước bù trừ cũng có thể thất bại. Cần retry có giới hạn, lưu trạng thái cần phục hồi và đưa workflow vào nhánh xử lý thủ công hoặc recovery process nếu không thể hoàn tất tự động.

## 9. Parallel và Map cho xử lý đồng thời

### 9.1. Parallel state

Parallel chạy nhiều branch cùng lúc. Ví dụ, sau khi tạo đơn, hệ thống có thể kiểm tra địa chỉ và tính thuế độc lập.

~~~json
{
  "EnrichOrder": {
    "Type": "Parallel",
    "Branches": [
      {
        "StartAt": "ValidateAddress",
        "States": {
          "ValidateAddress": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:validate-address:prod",
              "Payload.$": "$"
            },
            "End": true
          }
        }
      },
      {
        "StartAt": "CalculateTax",
        "States": {
          "CalculateTax": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:calculate-tax:prod",
              "Payload.$": "$"
            },
            "End": true
          }
        }
      }
    ],
    "Next": "ContinueOrder"
  }
}
~~~

Parallel đợi các branch hoàn tất theo ngữ nghĩa của state. Nếu một branch lỗi, workflow cần policy để xử lý lỗi của cả Parallel state. Không nên dùng Parallel nếu các bước phụ thuộc kết quả của nhau.

### 9.2. Map state

Map lặp qua danh sách phần tử và chạy một state machine con hoặc một chuỗi state cho mỗi phần tử. Ví dụ, xử lý từng item trong một batch hoặc từng file trong manifest.

Có thể cấu hình concurrency để giới hạn số phần tử chạy đồng thời. Với tập dữ liệu lớn, Distributed Map có thể xử lý dữ liệu ở quy mô lớn hơn và đọc item từ nguồn như S3, tùy chế độ và cấu hình.

Cần lưu ý:

- Giới hạn concurrency để không làm quá tải database hoặc API ngoài.
- Thiết kế từng item idempotent.
- Xác định xử lý khi một item lỗi: dừng toàn bộ, retry, ghi lỗi riêng hay tiếp tục item khác.
- Không truyền payload lớn cho từng item nếu chỉ cần object key.
- Theo dõi số item thành công, thất bại và retry.

Parallel và Map có thể làm số Lambda invocation tăng nhanh. Hãy tính tổng concurrency của workflow cùng các nguồn gọi function khác trong tài khoản.

## 10. Chờ một công việc bất đồng bộ bằng callback token

Một số tác vụ không thể hoàn tất ngay trong một Lambda invocation, ví dụ chờ đối tác xác nhận, chờ phê duyệt hoặc đợi một job bên ngoài. Step Functions hỗ trợ callback pattern với task token.

Callback task token là mẫu chờ dành cho Standard workflows. Express workflows không hỗ trợ callback integration pattern này; nếu cần chờ xác nhận trong Express, hãy thiết kế một cơ chế event/queue khác phù hợp với giới hạn thời gian ngắn của workflow.

Resource tích hợp Lambda callback thường có dạng:

~~~text
arn:aws:states:::lambda:invoke.waitForTaskToken
~~~

Ví dụ state:

~~~json
{
  "WaitForApproval": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
    "Parameters": {
      "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:request-approval:prod",
      "Payload": {
        "taskToken.$": "$$.Task.Token",
        "order.$": "$"
      }
    },
    "TimeoutSeconds": 86400,
    "Next": "ProcessApproval"
  }
}
~~~

Lambda request-approval nhận task token và thông tin đơn hàng. Function có thể lưu yêu cầu approval, gửi thông báo và kết thúc invocation. Workflow vẫn ở trạng thái chờ cho đến khi một thành phần được phép gọi API Step Functions để gửi task success hoặc task failure cùng token.

Token là dữ liệu nhạy cảm. Không gửi token cho trình duyệt hoặc người dùng cuối. Hãy lưu và chuyển token qua backend có xác thực, giới hạn quyền đọc, không ghi vào log và liên kết token với approval ID. Khi người duyệt quyết định, callback service xác minh danh tính/quyền, lưu kết quả và gọi API hoàn tất task.

Task token chỉ có hiệu lực cho task đang chờ và có thể hết hạn hoặc bị vô hiệu khi workflow kết thúc. Callback trùng hoặc đến muộn cần được xử lý an toàn. Có thể dùng transactional outbox để bảo đảm quyết định approval đã lưu sẽ được gửi đến Step Functions ngay cả khi callback service gặp lỗi.

## 11. Standard và Express workflows

Step Functions có hai loại workflow chính: Standard và Express. Việc chọn loại ảnh hưởng thời gian chạy, ngữ nghĩa thực thi, quan sát và chi phí.

| Tiêu chí | Standard | Express |
|---|---|---|
| Thời lượng tối đa | Có thể chạy đến một năm | Tối đa vài phút (hiện là 5 phút) |
| Workload | Quy trình dài, có chờ, phê duyệt hoặc điều phối nhiều bước | Lưu lượng lớn, xử lý ngắn và thông lượng cao |
| Execution history | Lịch sử thực thi được lưu trong Step Functions | Thường dựa nhiều hơn vào CloudWatch Logs để quan sát chi tiết |
| Ngữ nghĩa giao nhận | Exactly-once workflow execution theo mô hình Standard; vẫn cần idempotency cho side effect và retry được cấu hình | Express có hai chế độ: asynchronous at-least-once và synchronous at-most-once |
| Chi phí | Chủ yếu theo số state transition | Chủ yếu theo số execution và thời lượng/tài nguyên |
| Callback/wait dài | Phù hợp hơn cho workflow chờ lâu | Không phù hợp với tác vụ chờ vượt giới hạn thời gian |

Các ngữ nghĩa exactly-once/at-least-once/at-most-once mô tả việc thực thi workflow theo loại và chế độ, không tự bảo đảm một side effect ở dịch vụ ngoài chỉ xảy ra đúng một lần. Khi có retry, timeout không rõ kết quả hoặc callback từ hệ thống khác, idempotency ở tầng nghiệp vụ vẫn cần thiết.

Chọn Standard khi quy trình cần chạy lâu, có human approval, cần execution history và phục hồi từng bước. Chọn Express khi workflow ngắn, tần suất lớn và phù hợp với giới hạn thời gian. Với Express, cần chọn chế độ synchronous hay asynchronous theo yêu cầu giao nhận và phản hồi.

Giới hạn và cách tính phí có thể thay đổi theo dịch vụ và vùng. Kiểm tra quota và bảng giá AWS hiện hành trước khi chốt kiến trúc.

## 12. Saga và compensation cho quy trình nhiều dịch vụ

Một workflow nhiều bước thường cập nhật nhiều hệ thống độc lập. Không có một transaction ACID duy nhất bao trùm Lambda, DynamoDB, payment provider và hệ thống giao hàng.

Saga chia quy trình thành các transaction cục bộ. Mỗi bước có thể có một hành động bù trừ để đưa nghiệp vụ về trạng thái chấp nhận được khi bước sau thất bại.

Ví dụ đặt hàng:

| Bước thành công | Compensation có thể dùng |
|---|---|
| Reserve inventory | Release inventory |
| Authorize payment | Void authorization |
| Capture payment | Refund payment, nếu nghiệp vụ cho phép |
| Create shipment | Cancel shipment nếu hãng vận chuyển hỗ trợ |
| Send notification | Gửi thông báo đính chính; không thể thu hồi email đã gửi |

Compensation không phải lúc nào cũng đảo ngược hoàn toàn side effect. Một email đã gửi không thể thu hồi; một khoản hoàn tiền có thể cần thời gian xử lý. Vì vậy, thiết kế Saga cần xác định trạng thái cuối cùng, audit và quy trình xử lý ngoại lệ.

Step Functions có thể điều phối cả luồng chính lẫn compensation branch. Dùng Catch để chuyển sang nhánh bù trừ và ghi rõ kết quả từng bước. Nếu compensation thất bại, không đánh dấu workflow như đã rollback hoàn toàn; lưu trạng thái cần can thiệp và phát cảnh báo.

## 13. IAM và bảo mật workflow

Có hai nhóm quyền quan trọng:

1. **Step Functions execution role:** quyền mà state machine sử dụng để gọi Lambda, ghi log hoặc gọi dịch vụ AWS khác.
2. **Lambda execution role:** quyền của code trong function khi truy cập database, S3, queue hoặc dịch vụ khác.

Step Functions execution role chỉ nên cho phép invoke đúng function/version/alias cần thiết. Lambda execution role chỉ nên có quyền truy cập tài nguyên nghiệp vụ mà function cần. Không dùng một role quá rộng cho mọi workflow và mọi function nếu có thể tách theo trách nhiệm.

Nếu Lambda cần gọi SendTaskSuccess, SendTaskFailure hoặc SendTaskHeartbeat, cấp quyền Step Functions tương ứng cho callback service. Không để người dùng cuối gọi trực tiếp các API này bằng task token.

Dữ liệu workflow có thể chứa thông tin khách hàng, payment reference hoặc dữ liệu nội bộ. Hãy:

- Chỉ truyền dữ liệu cần cho state tiếp theo.
- Không đưa secret vào execution input/output.
- Dùng Secrets Manager hoặc Parameter Store cho credential.
- Giới hạn quyền xem execution history và CloudWatch Logs.
- Mã hóa dữ liệu theo yêu cầu của tổ chức.
- Dùng audit cho thao tác start, stop, redrive hoặc thay đổi workflow.
- Không log task token, access token hoặc dữ liệu nhạy cảm.

## 14. Giới hạn payload, timeout và concurrency

Workflow input/output được truyền qua state transition. Payload lớn làm tăng chi phí, tăng thời gian serialize và có thể vượt giới hạn của Step Functions. Giới hạn payload state input/output hiện phổ biến là 256 KiB; hãy xác nhận quota hiện hành trước khi triển khai.

Với file lớn hoặc dữ liệu lớn:

1. Lưu file trong S3.
2. Truyền bucket, object key, version ID và checksum trong state.
3. Lambda đọc dữ liệu theo luồng hoặc theo batch.
4. Lưu kết quả lớn về S3 hoặc database.
5. Chỉ truyền reference và metadata sang state kế tiếp.

Mỗi Lambda Task còn chịu timeout của Lambda. Task timeout của Step Functions cần được cấu hình phù hợp với thời gian tối đa của function và deadline nghiệp vụ. Nếu Step Functions timeout trong khi Lambda vẫn thực hiện side effect, retry hoặc xử lý lỗi có thể tạo thao tác trùng.

Parallel/Map có thể làm concurrency tăng mạnh. Đặt giới hạn concurrency trong Map khi cần, cấu hình reserved concurrency cho Lambda nếu muốn bảo vệ dependency, và giới hạn connection pool. Theo dõi backlog, throttling và thời gian chờ để điều chỉnh.

## 15. Theo dõi workflow và xử lý sự cố

Step Functions cung cấp execution history cho Standard workflows và tích hợp với CloudWatch Logs, metrics và tracing theo cấu hình. Khi một workflow thất bại, cần xác định state nào lỗi, input nào được truyền, lỗi từ Lambda hay từ service integration, và state machine đã retry bao nhiêu lần.

Metric nên theo dõi:

- Số execution bắt đầu, hoàn tất, thất bại, timeout và bị abort.
- Thời gian execution tổng thể.
- Thời gian và số lần retry ở từng Task.
- Lambda errors, throttles, duration và concurrency.
- Số workflow đang chờ callback.
- Số lỗi compensation hoặc workflow cần can thiệp thủ công.
- Payload size và số state transition.
- Chi phí theo loại workflow và tần suất chạy.

Dùng execution name và correlation ID để nối workflow với log của Lambda và dịch vụ phía sau. Tránh ghi toàn bộ state input/output nếu chứa dữ liệu nhạy cảm. Cấu hình log level và data inclusion theo yêu cầu quan sát và bảo mật.

Khi cần chạy lại workflow thất bại, xem xét liệu state đã thực hiện side effect hay chưa. Với Standard workflows, khả năng redrive có thể giúp tiếp tục từ trạng thái lỗi theo tính năng và điều kiện dịch vụ hỗ trợ. Redrive không thay thế idempotency; cần xác minh các bước đã hoàn tất và trạng thái bên ngoài trước khi chạy lại.

## 16. Triển khai state machine bằng IaC

Nên quản lý state machine và quyền IAM dưới dạng code để có thể review, version hóa và triển khai nhất quán. Các lựa chọn phổ biến gồm:

- AWS CloudFormation.
- AWS CDK.
- AWS SAM trong các cấu hình hỗ trợ Step Functions.
- Terraform.
- AWS CLI cho thao tác triển khai hoặc kiểm tra có kiểm soát.

Một quy trình triển khai thường gồm:

1. Build và kiểm thử các Java Lambda.
2. Đóng gói artifact và triển khai version/alias.
3. Tạo hoặc cập nhật state machine definition.
4. Cấu hình execution role với quyền tối thiểu.
5. Cấu hình log, tracing và alarm.
6. Chạy integration test với dữ liệu giả lập.
7. Kiểm tra retry, timeout, callback và compensation.
8. Triển khai theo môi trường dev/test/prod.
9. Theo dõi execution đầu tiên và xác minh rollback.

Dùng Lambda alias hoặc version ARN trong state machine để kiểm soát phiên bản function. Nếu state machine tham chiếu $LATEST, hành vi có thể thay đổi khi function được cập nhật mà không có thay đổi state machine. Chọn chiến lược release có thể truy vết và rollback.

## 17. Kiểm thử workflow

Một workflow không chỉ cần test từng Lambda riêng lẻ. Cần kiểm tra cả chuyển trạng thái và cách xử lý lỗi:

1. Input hợp lệ đi qua toàn bộ luồng.
2. Input không hợp lệ đi đúng nhánh từ chối.
3. Lambda lỗi tạm thời và retry thành công.
4. Lambda lỗi liên tục và Catch chuyển sang nhánh lỗi.
5. Timeout xảy ra sau khi side effect đã hoàn tất.
6. Hai nhánh Parallel có kết quả đúng và xử lý lỗi theo policy.
7. Map xử lý danh sách rỗng, danh sách lớn và một item lỗi.
8. Callback token được gửi đúng và callback đến trùng.
9. Callback đến sau timeout hoặc workflow đã kết thúc.
10. Compensation thành công và compensation thất bại.
11. Payload tiến gần giới hạn state input/output.
12. Execution role thiếu quyền và báo lỗi rõ ràng.
13. Lambda concurrency bị throttled.
14. Redrive hoặc chạy lại không tạo side effect trùng.

AWS Step Functions Local và các công cụ kiểm thử state machine có thể hỗ trợ một số tình huống, nhưng hành vi tích hợp thật với IAM, Lambda, callback và service quota cần được xác minh trong môi trường AWS kiểm thử.

## 18. Quy trình thiết kế workflow cho Java Lambda

1. **Mô tả quy trình nghiệp vụ.** Xác định bước, điều kiện, nhánh lỗi và trạng thái cuối.
2. **Chọn orchestration hay choreography.** Dùng Step Functions khi cần điều phối tập trung, chờ hoặc theo dõi tiến trình.
3. **Chia trách nhiệm cho Lambda.** Mỗi function thực hiện một bước có input/output rõ ràng.
4. **Định nghĩa state machine.** Dùng Task, Choice, Parallel, Map, Wait, Succeed và Fail đúng mục đích.
5. **Thiết kế retry và catch.** Phân loại lỗi tạm thời, lỗi nghiệp vụ và lỗi không thể phục hồi.
6. **Bảo đảm idempotency.** Mỗi side effect có khóa ổn định và trạng thái lưu bền vững.
7. **Thiết kế compensation.** Xác định cách xử lý khi một bước sau thất bại.
8. **Chọn Standard hoặc Express.** Dựa trên thời gian chạy, throughput, semantics và chi phí.
9. **Giới hạn dữ liệu và concurrency.** Truyền reference cho dữ liệu lớn, giới hạn Map và bảo vệ dependency.
10. **Cấu hình IAM và quan sát.** Quyền tối thiểu, log, metric, tracing và cảnh báo.
11. **Kiểm thử sự cố và triển khai.** Mô phỏng retry, timeout, duplicate, callback và rollback.

Step Functions phù hợp khi quy trình có nhiều bước cần điều phối và trạng thái rõ ràng. Java Lambda vẫn là nơi thực thi logic nghiệp vụ; state machine điều khiển cách các bước kết nối, chờ, retry và phục hồi.

## 19. Câu hỏi tự kiểm tra

- Step Functions khác việc một Lambda gọi tuần tự nhiều Lambda khác như thế nào?
- Task state và Choice state có trách nhiệm gì?
- Optimized Lambda integration trả kết quả cho state machine theo cấu trúc nào?
- ResultSelector và ResultPath giúp kiểm soát state data ra sao?
- Vì sao cần idempotency dù Standard workflow có semantics exactly-once?
- Khi nào dùng Parallel và khi nào dùng Map?
- Callback task token được dùng để chờ công việc bất đồng bộ như thế nào?
- Standard và Express khác nhau về thời lượng, semantics và chi phí ra sao?
- Saga compensation khác rollback transaction thông thường như thế nào?
- Vì sao không nên truyền file lớn hoặc secret trong state input/output?
- Step Functions execution role khác Lambda execution role như thế nào?
- Cần kiểm tra điều gì trước khi redrive một workflow thất bại?

AWS Step Functions giúp biến một tập hợp Java Lambda thành quy trình có trạng thái, có thể quan sát và phục hồi theo định nghĩa. Hãy dùng state machine để quản lý luồng điều khiển, thiết kế mỗi Lambda idempotent, chọn retry theo loại lỗi và bổ sung compensation cho side effect nhiều dịch vụ. Khi quy trình được mô hình hóa rõ, hệ thống dễ theo dõi và xử lý sự cố hơn khi lưu lượng tăng hoặc một dịch vụ phụ thuộc gặp lỗi.

