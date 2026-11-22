# Phát hành phiên bản workflow mới và xử lý phiên đang chạy

## 1. Vì sao phải quản lý phiên bản workflow?

Một workflow nghiệp vụ có thể chạy trong vài giây, vài giờ hoặc nhiều ngày. Ví dụ quy trình xử lý đơn hàng có thể xác thực yêu cầu, giữ tồn kho, chờ thanh toán, chờ đối tác xác nhận giao hàng rồi mới hoàn tất. Trong lúc một execution đang chờ, nhóm phát triển có thể cần sửa definition, thay đổi thứ tự task, bổ sung bước kiểm tra, đổi timeout hoặc nâng cấp Lambda được gọi.

Nếu cập nhật workflow mà không có chiến lược phiên bản, nhóm dễ gặp các tình huống:

- Execution cũ bắt đầu bằng logic cũ nhưng tiếp tục gọi dependency đã thay đổi.
- Execution mới dùng definition mới trong khi execution cũ vẫn chạy.
- Một lỗi production cần rollback nhưng alias chỉ chuyển được execution mới.
- Input/state đã lưu không tương thích với workflow definition mới.
- Redrive một execution lỗi lại chạy task cũ hoặc tạo side effect lặp.
- Không thể xác định version nào gây lỗi, latency hoặc chi phí tăng.

Với AWS Step Functions, **state machine version** và **alias** giúp phát hành workflow có kiểm soát. Version là snapshot bất biến của state machine; alias là tên ổn định để định tuyến execution mới đến một hoặc hai version. Tuy nhiên, đổi alias không chuyển execution đang chạy sang version mới. Vì vậy, release workflow cần quản lý cả execution mới, execution cũ, dữ liệu state, Lambda/task dependency và side effect bên ngoài.

Trong module CLOUD_SERVERLESS, nội dung này áp dụng cho Java function được kích hoạt bởi HTTP, message hoặc event, đặc biệt khi Step Functions điều phối nhiều bước có retry, timeout, state và thời gian sống dài.

## 2. Phân biệt revision, version, alias và execution

Các khái niệm này liên quan nhưng không thay thế nhau.

| Khái niệm | Ý nghĩa | Có thể chạy execution trực tiếp? |
|---|---|---|
| State machine revision | Snapshot chỉ đọc của definition/config sau một lần cập nhật | Không; revision không có ARN để StartExecution |
| State machine version | Bản snapshot được publish, có số version và ARN riêng | Có |
| State machine alias | ARN ổn định trỏ đến một hoặc tối đa hai version | Có; Step Functions chọn version theo routing config |
| State machine ARN không qualifier | Địa chỉ state machine không kèm version/alias | Có; dùng revision mới nhất tại thời điểm start |
| Execution | Một lần chạy cụ thể với input, history và trạng thái riêng | Là instance của workflow, không phải version |

Ví dụ:

```text
State machine: OrderFulfillment

Revision: r-7d2...       # snapshot nội bộ, không dùng StartExecution
Version 12: ...:OrderFulfillment:12
Version 13: ...:OrderFulfillment:13
Alias PROD: ...:OrderFulfillment:PROD
  95% -> Version 12
   5% -> Version 13

Execution A -> Version 12 (đã chạy từ trước)
Execution B -> Version 13 (được alias chọn khi start)
```

Một version là snapshot bất biến của state machine definition và một số cấu hình như IAM role ARN, logging và tracing configuration. Alias là con trỏ có thể cập nhật để route traffic. Execution là một lần chạy cụ thể và giữ liên kết với version/alias được dùng khi bắt đầu nếu StartExecution dùng qualified ARN.

Tài liệu: [State machine versions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-version.html), [State machine aliases](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-alias.html).

## 3. Điều gì xảy ra với execution đang chạy khi cập nhật definition?

Khi gọi `UpdateStateMachine` để sửa definition hoặc role ARN, execution đang chạy tiếp tục dùng definition và role ARN cũ. Việc cập nhật không thay đổi state machine definition giữa chừng cho những execution đã bắt đầu.

Điều đó có nghĩa:

- Execution đang ở `Wait` vẫn tiếp tục theo workflow cũ khi hết thời gian chờ.
- Execution đang chạy `Task` sẽ tiếp tục theo definition cũ.
- Execution cũ có thể tiếp tục nhiều giờ/ngày sau khi version mới được publish.
- Execution mới bắt đầu bằng unqualified state machine ARN sẽ dùng revision mới nhất sau khi cập nhật có hiệu lực.
- Execution mới bắt đầu bằng version ARN hoặc alias ARN sẽ được gắn với version/alias tương ứng.

Không cần dừng tất cả execution cũ chỉ vì đã publish workflow version mới. Tuy nhiên, dependency bên ngoài mà workflow cũ gọi có thể thay đổi độc lập. Đây là rủi ro quan trọng: state machine giữ definition cũ, nhưng nếu definition gọi Lambda qua alias `orders-worker:PROD`, việc di chuyển alias Lambda có thể làm execution cũ gọi code mới ở bước tiếp theo.

Muốn giữ hành vi nhất quán, cần quản lý phiên bản dependency cùng workflow version hoặc duy trì contract tương thích ngược trong giai đoạn execution cũ còn tồn tại.

Tài liệu API: [UpdateStateMachine](https://docs.aws.amazon.com/step-functions/latest/apireference/API_UpdateStateMachine.html).

## 4. Version mới chỉ áp dụng cho execution mới

State machine version không phải cơ chế nâng cấp execution đang chạy. Khi một execution đã bắt đầu, Step Functions không tự chuyển nó sang version khác khi alias được cập nhật.

Có ba nhóm execution cần phân biệt:

1. **Execution đang chạy từ version/alias cũ:** tiếp tục với definition đã gắn lúc start.
2. **Execution mới sau release:** được route qua alias/version mới theo ARN được caller sử dụng.
3. **Execution lỗi được redrive:** với Standard Workflow, redrive tiếp tục execution gốc bằng definition và version/alias gốc, không tự lấy target mới nhất của alias.

Vì vậy, kế hoạch release cần có chính sách rõ cho execution đang chạy: để hoàn tất theo version cũ, chờ drain, dừng và bù trừ, hoặc tạo execution mới từ checkpoint nghiệp vụ đã được chuyển đổi. Không có thao tác “đổi version tại chỗ” an toàn cho một execution bất kỳ.

## 5. Tạo state machine version và alias

### Publish version

Sau khi cập nhật definition, có thể publish version từ revision hiện tại. Ví dụ AWS CLI:

```bash
aws stepfunctions update-state-machine \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --definition file://order-workflow.asl.json \
  --role-arn "$STATE_MACHINE_ROLE_ARN" \
  --publish
```

Lệnh trả về `stateMachineVersionArn` nếu publish thành công. Một cách khác là cập nhật definition trước rồi gọi `publish-state-machine-version`. Version number tăng tuần tự và không được tái sử dụng cho cùng state machine.

Nên ghi lại:

- Git commit SHA của workflow definition.
- Hash của ASL/JSON/YAML đã deploy.
- Version ARN được publish.
- IAM role ARN và cấu hình logging/tracing.
- Version ARN của Lambda/task dependency nếu đã pin.
- Input schema version và event schema version liên quan.

### Tạo alias production

Ví dụ alias `PROD` ban đầu route 100% đến version 12:

```bash
aws stepfunctions create-state-machine-alias \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --name PROD \
  --routing-configuration '[
    {
      "stateMachineVersionArn": "arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderFulfillment:12",
      "weight": 100
    }
  ]'
```

Sau này alias có thể được cập nhật để route giữa version 12 và 13. Alias chỉ trỏ đến version, không trỏ đến alias khác; một alias có thể route tối đa hai version và tổng weight phải bằng 100.

### Bắt đầu execution bằng alias

```bash
aws stepfunctions start-execution \
  --state-machine-arn "$STATE_MACHINE_PROD_ALIAS_ARN" \
  --name "order-9381-fulfillment" \
  --input file://execution-input.json
```

Production caller nên gọi alias ARN thay vì unqualified state machine ARN nếu cần kiểm soát release và quan sát theo version. Unqualified ARN dùng revision mới nhất nhưng execution không được gắn với version/alias, kể cả khi revision đó trùng với một version đã publish.

## 6. Alias routing và canary deployment

Alias cho phép phân phối execution mới giữa tối đa hai version. Ví dụ:

```text
PROD alias
  Version 12: 95%
  Version 13:  5%
```

Khi caller gọi `StartExecution` bằng alias ARN, Step Functions chọn một version theo weight đã cấu hình. Đây là routing cho **lần bắt đầu execution**. Nó không chuyển các execution cũ giữa hai version khi alias thay đổi.

Ví dụ cập nhật alias:

```bash
aws stepfunctions update-state-machine-alias \
  --state-machine-alias-arn "$STATE_MACHINE_PROD_ALIAS_ARN" \
  --routing-configuration '[
    {
      "stateMachineVersionArn": "arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderFulfillment:12",
      "weight": 95
    },
    {
      "stateMachineVersionArn": "arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderFulfillment:13",
      "weight": 5
    }
  ]'
```

Quy trình tăng dần có thể là 1%, 5%, 10%, 25%, 50% rồi 100%. Chỉ tăng khi execution mới ở version 13 đạt ngưỡng error rate, timeout, latency và business correctness.

Weighted routing là phân phối theo execution start; không mặc định nó bảo đảm sticky routing theo tenant hoặc customer. Nếu mọi execution của cùng một order/customer phải dùng cùng version, cần route bằng policy ở caller hoặc lưu version lựa chọn vào operation record rồi start execution theo version ARN cụ thể.

Tài liệu: [State machine aliases and routing](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-alias.html).

## 7. Những execution đã chạy trước khi có version/alias

Một hệ thống có thể đã có hàng nghìn execution được start bằng unqualified state machine ARN trước khi bật versioning. Những execution đó không được Step Functions gắn ngược vào một version chỉ vì definition của chúng giống với version mới publish.

Khi kiểm kê, chia thành:

- Execution đang chạy từ unqualified ARN.
- Execution đang chạy từ version ARN.
- Execution đang chạy từ alias ARN.
- Execution đã hoàn tất hoặc thất bại.
- Execution đang chờ ở `Wait`, callback task token hoặc external integration.

Với execution unqualified, dùng execution ARN, start time, history và revision/definition metadata sẵn có để xác định release tương ứng nếu hệ thống có lưu. Nếu trước đây không ghi commit/version trong input hoặc log, có thể không tái dựng chính xác release chỉ từ tên state machine.

Từ release mới, hãy truyền `workflowRelease`, `inputSchemaVersion`, `businessOperationId` và correlation ID vào execution input hoặc metadata để tra cứu dễ hơn.

## 8. Chọn chính sách cho execution đang chạy

Không phải execution cũ nào cũng cần xử lý giống nhau. Chọn chính sách theo thời gian chạy, trạng thái nghiệp vụ và rủi ro side effect.

| Chính sách | Khi phù hợp | Việc cần làm |
|---|---|---|
| Let old version finish | Execution có thể hoàn tất và dependency cũ vẫn tương thích | Giữ version/dependency cũ, theo dõi số execution còn lại |
| Drain before switch | Workflow ngắn, có thể chờ hết execution trước khi chuyển alias | Tạm ngừng nhận execution mới hoặc route sang hàng đợi, chờ active count về 0 |
| Stop and compensate | Workflow lỗi hoặc không an toàn nếu tiếp tục | Stop execution, chạy compensation idempotent và cập nhật operation state |
| Restart as new execution | Cần áp dụng logic mới cho phần công việc chưa hoàn tất | Tạo checkpoint, chuyển đổi input/state, tạo execution mới với correlation đến execution cũ |
| Keep old version for long tail | Workflow có thể chờ nhiều ngày/tháng | Giữ version và task dependencies cần thiết đến khi execution hoàn tất hoặc hết redrive window |

Không chọn “restart all” như thao tác mặc định. Một workflow có thể đã capture payment hoặc gửi hàng; khởi động lại từ đầu có thể tạo side effect trùng. Restart cần xác định checkpoint nghiệp vụ và bước nào đã commit.

## 9. Drain execution cũ

Drain là quá trình ngừng tạo execution mới trên version cũ và chờ các execution đã bắt đầu hoàn tất.

Quy trình:

1. Chuyển alias hoặc caller sang version mới cho execution mới.
2. Ghi nhận thời điểm cutover và version ARN.
3. Liệt kê execution đang chạy theo version/alias cũ.
4. Theo dõi execution đang ở trạng thái `RUNNING`, `WAITING` hoặc chờ callback.
5. Đặt deadline drain dựa trên SLA và maximum workflow duration.
6. Xử lý execution vượt thời gian: điều tra, tiếp tục, stop/compensate hoặc migrate có kiểm soát.
7. Chỉ gỡ dependency cũ khi không còn execution cần gọi nó và redrive policy đã được xem xét.

Với Step Functions, có thể dùng `ListExecutions` theo state machine/version/alias để kiểm kê. Với execution start bằng alias, API có thể cho biết alias ARN và version được chọn. Với execution unqualified trước đó, cần dựa vào thời điểm và metadata đã lưu.

Đừng chỉ nhìn số execution đang `RUNNING`. Một execution có thể đang chờ callback hoặc Wait state trong thời gian dài; nó vẫn cần definition/version và dependency tương thích khi tiếp tục.

## 10. Redrive execution thất bại sau khi phát hành version mới

Step Functions Standard Workflow hỗ trợ redrive một số execution thất bại, bị abort hoặc timeout trong cửa sổ redrive. Redrive tiếp tục từ state thất bại, dùng cùng input, giữ kết quả/history của các state đã thành công và dùng lại definition/ARN của execution gốc.

Điểm quan trọng:

- Redrive không tự động dùng version mới nhất.
- Nếu execution gốc gắn với version hoặc alias, redrive tiếp tục gắn với version/alias của execution đó.
- Dù alias đã được chuyển sang version mới, redrive vẫn dùng version gốc.
- Nếu muốn chạy bằng definition mới, cần tạo execution mới và chuyển đổi input/checkpoint có chủ đích.
- Task bị chạy lại có thể lặp side effect nếu không idempotent.

Theo tài liệu hiện hành, Standard Workflow có cửa sổ redrive 14 ngày cho execution đủ điều kiện; redrive không áp dụng trực tiếp cho Express Workflow. Kiểm tra eligibility, execution history quota và điều kiện cụ thể trước khi vận hành.

Ví dụ:

```text
Execution E-100 started by alias PROD -> Version 12
Version 13 is released
Alias PROD now points 100% -> Version 13
E-100 fails at CapturePayment

Redrive E-100:
  resumes failed state using Version 12
  does not switch to Version 13

Start a new execution with Version 13:
  requires a new execution ARN/name and migrated business input
```

Tài liệu: [Redrive executions](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html).

## 11. Phân biệt redrive và migration sang execution mới

Redrive là tiếp tục execution cũ theo definition cũ. Migration là tạo một execution mới bằng definition mới, có liên kết với operation/execution cũ và checkpoint đã chuyển đổi.

| Tiêu chí | Redrive | New execution migration |
|---|---|---|
| Definition | Definition của execution gốc | Definition/version mới |
| Execution ARN | Giữ execution ARN gốc | ARN mới |
| Successful states | Giữ kết quả, không chạy lại theo redrive behavior | Phải chuyển checkpoint hoặc tính lại có kiểm soát |
| Input | Input gốc | Input đã chuyển đổi/version hóa |
| Side effects | Task lỗi được chạy lại; cần idempotency | Chỉ chạy phần chưa hoàn tất theo checkpoint |
| Use case | Lỗi transient hoặc dependency đã phục hồi | Cần áp dụng logic/schema/workflow mới |

Không sửa trực tiếp execution history để giả vờ execution đã đi qua state mới. Hãy lưu migration record gồm old execution ARN, new execution ARN, source version, target version, checkpoint, operator/reason và timestamp.

## 12. Workflow version không tự pin Lambda và service dependency

Một version của state machine lưu definition/config của state machine, nhưng không đóng băng toàn bộ tài nguyên bên ngoài mà definition tham chiếu.

Ví dụ ASL gọi Lambda qua alias:

```json
{
  "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:ReserveInventory:PROD"
}
```

Nếu alias `PROD` của Lambda được chuyển từ function version 8 sang 9, một execution đang chạy workflow version cũ nhưng chưa đến state `ReserveInventory` có thể gọi code version 9. Definition Step Functions không đổi, nhưng dependency thực thi đã đổi.

Để bảo đảm reproducibility:

- Pin Lambda function version ARN trong workflow definition khi cần behavior bất biến.
- Hoặc duy trì alias dependency backward-compatible cho đến khi execution cũ drain xong.
- Ghi lại version của API/service ngoài trong release manifest.
- Giữ event schema và database contract tương thích với cả workflow cũ/mới.
- Không xóa Lambda version, layer hoặc container image mà execution cũ còn cần.

Một state machine version cũng không đóng băng policy document được gắn vào IAM role ARN nếu policy đó bị sửa bên ngoài. Version lưu role ARN, nhưng quyền hiệu lực vẫn chịu ảnh hưởng từ IAM policies/resource policies hiện hành. Nếu cần bảo đảm release, quản lý IAM policy như artifact versioned và tránh sửa quyền theo cách làm thay đổi bất ngờ execution đang chạy.

## 13. Quản lý input schema và workflow state qua nhiều version

Execution input được lưu theo từng execution. Workflow version mới có thể mong đợi field mới hoặc kiểu dữ liệu khác. Nếu event/API producer đã chuyển sang schema mới trong khi execution cũ vẫn chạy, state cũ có thể gặp dữ liệu không tương thích ở bước tiếp theo.

Đưa `schemaVersion` vào input:

```json
{
  "workflowRelease": "orders-2026.11.17.3",
  "inputSchemaVersion": 2,
  "operationId": "op-7f1a",
  "order": {
    "orderId": "order-9381",
    "customerId": "customer-42"
  }
}
```

Nguyên tắc tương thích:

- Ưu tiên thay đổi additive: thêm field optional trước khi bắt buộc sử dụng.
- Consumer cũ bỏ qua field không biết nếu contract cho phép.
- Không đổi nghĩa field đang tồn tại mà không tăng schema version.
- Giữ field cũ trong giai đoạn execution cũ còn chạy.
- Dùng adapter/normalizer ở đầu workflow để chuyển input về canonical model.
- Tách schema event khỏi schema state nội bộ của workflow.
- Ghi version và migration path rõ ràng.

Nếu workflow mới cần một field không có trong input cũ, có thể derive từ database hoặc adapter. Nếu không thể derive an toàn, cần giữ workflow cũ hoặc tạo quy trình migration có người kiểm soát.

## 14. Expand-contract cho database schema

Workflow cũ và mới có thể cùng đọc/ghi database trong thời gian dài. Không triển khai schema breaking change cùng lúc với cutover workflow nếu execution cũ còn hoạt động.

Một trình tự expand-contract:

1. **Expand:** thêm cột/table mới, giữ field cũ.
2. Deploy service có thể đọc cả schema cũ và mới.
3. Deploy workflow version mới ghi dữ liệu mới theo cách tương thích.
4. Backfill dữ liệu cũ nếu cần.
5. Chờ execution cũ drain và kiểm tra mọi consumer đã nâng cấp.
6. **Contract:** ngừng ghi/đọc field cũ và chỉ sau đó mới xóa schema cũ.

Không xóa cột mà execution cũ có thể truy cập ở bước tiếp theo. Workflow có thể chờ một callback hoặc timer nhiều ngày; việc không thấy query trong vài phút không chứng minh cột đã an toàn để xóa.

## 15. Thiết kế state machine cho khả năng nâng cấp

Workflow nên có state boundary ổn định và dữ liệu đủ để tiếp tục sau thời gian dài.

Gợi ý:

- Mỗi operation có business ID và workflow execution ARN.
- Lưu checkpoint nghiệp vụ sau các side effect quan trọng.
- State output chỉ chứa dữ liệu cần cho bước tiếp theo, không lưu payload lớn hoặc secret.
- Dùng `Choice` để xử lý schema version hoặc trạng thái nghiệp vụ khác nhau.
- Dùng `Retry` cho lỗi transient và `Catch` cho lỗi cần compensation.
- Task side effect phải idempotent theo operation/step.
- Dùng Wait/callback cho thời gian chờ, không giữ Lambda chạy.
- Có timeout tổng và deadline nghiệp vụ.
- Ghi rõ state nào có thể redrive/restart an toàn.

Ví dụ ASL rút gọn:

```json
{
  "Comment": "Order workflow with versioned input contract",
  "StartAt": "NormalizeInput",
  "TimeoutSeconds": 86400,
  "States": {
    "NormalizeInput": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:NormalizeOrder:7",
      "Next": "CheckSchemaVersion"
    },
    "CheckSchemaVersion": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.inputSchemaVersion",
          "NumericEquals": 2,
          "Next": "ReserveInventory"
        }
      ],
      "Default": "UnsupportedInputVersion"
    },
    "ReserveInventory": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:ReserveInventory:12",
      "Retry": [
        {
          "ErrorEquals": ["TransientDependencyError"],
          "IntervalSeconds": 2,
          "BackoffRate": 2,
          "MaxAttempts": 3
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.failure",
          "Next": "Compensate"
        }
      ],
      "Next": "Complete"
    },
    "Compensate": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:CompensateOrder:4",
      "End": true
    },
    "UnsupportedInputVersion": {
      "Type": "Fail",
      "Error": "UnsupportedInputVersion"
    },
    "Complete": {
      "Type": "Succeed"
    }
  }
}
```

Ví dụ dùng Lambda version ARN cụ thể để minh họa pin dependency. Trong production, thay ARN bằng artifact được pipeline tạo ra; không hardcode account/Region ở nhiều file. `TimeoutSeconds`, retry và state flow cần phù hợp nghiệp vụ. `States.ALL` trong `Catch` là ví dụ đơn giản; thực tế nên phân loại lỗi và không chạy compensation cho lỗi không cần thiết.

## 16. Idempotency khi workflow retry hoặc chạy song song hai version

Canary có thể khiến execution mới của cùng loại nghiệp vụ chạy trên version cũ hoặc mới. Retry trong một execution cũng có thể gọi task nhiều lần. Vì vậy, idempotency key nên dựa trên business operation, không chỉ dựa vào workflow version.

Ví dụ:

```text
operationId = order-9381
stepKey = order-9381:reserve-inventory
paymentKey = order-9381:capture-payment
notificationKey = order-9381:send-confirmation
```

Không thêm workflow version vào idempotency key nếu mục tiêu là ngăn side effect lặp giữa version cũ và mới. Nếu version 12 và 13 cùng xử lý một order, chúng cần cùng nhận diện một business effect. Chỉ tạo key mới khi đó là một hành động nghiệp vụ mới có chủ đích.

Các bước side effect cần:

- Unique constraint/conditional write ở database.
- Inbox/outbox khi publish event.
- Provider idempotency key cho payment/email API nếu được hỗ trợ.
- State transition có version/expected status.
- Reconciliation cho kết quả không rõ sau timeout.
- Audit trail để biết version nào đã thực hiện effect.

## 17. Workflow release cần version hóa dependency

Một workflow release không chỉ là file ASL. Nó là tập hợp các thành phần có thể ảnh hưởng đến execution.

Release manifest ví dụ:

```yaml
release: orders-workflow-2026.11.17.3
stateMachine:
  versionArn: arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderFulfillment:13
  alias: PROD
inputSchemaVersion: 2
tasks:
  normalizeOrder: arn:aws:lambda:ap-southeast-1:123456789012:function:NormalizeOrder:7
  reserveInventory: arn:aws:lambda:ap-southeast-1:123456789012:function:ReserveInventory:12
  compensateOrder: arn:aws:lambda:ap-southeast-1:123456789012:function:CompensateOrder:4
events:
  orderAcceptedSchema: 3
database:
  schemaCompatibility: expand-contract-v5
```

Manifest này là ví dụ khái niệm, không phải cấu hình Step Functions trực tiếp. Lưu nó cùng artifact/release metadata để biết execution version 13 đã gọi task version nào và yêu cầu schema nào.

Nếu workflow gọi Lambda alias, container tag mutable hoặc API endpoint không có version contract, release manifest cần ghi rõ đó là dependency mutable và cách giữ tương thích.

## 18. Quy trình CI/CD để phát hành workflow version mới

Một pipeline có thể chia thành các bước:

1. Validate ASL definition và schema input/output.
2. Chạy unit test cho Java task và contract test giữa các bước.
3. Chạy integration test trong sandbox với mock/sandbox dependency.
4. Build, publish và ghi lại immutable Lambda function versions.
5. Cập nhật state machine definition/role/configuration.
6. Publish state machine version và lưu version ARN.
7. Kiểm tra definition, IAM role ARN, logging/tracing và dependency references.
8. Cập nhật alias test/staging để trỏ 100% vào version mới.
9. Chạy workflow smoke test và failure test.
10. Cập nhật production alias theo canary weight.
11. Theo dõi metrics theo version/alias và business outcome.
12. Tăng traffic hoặc rollback alias.
13. Theo dõi/drain execution cũ và chỉ gỡ dependency khi an toàn.

Không deploy task Lambda alias trước khi đã xác định ảnh hưởng đến workflow execution cũ. Một pipeline nên publish Lambda versions bất biến trước, sau đó tạo state machine version tham chiếu đúng Lambda version ARN.

## 19. Kiểm tra definition trước khi publish

Có thể dùng Step Functions `ValidateStateMachineDefinition` hoặc AWS CLI tương ứng để phát hiện lỗi cú pháp/validation trước khi update.

```bash
aws stepfunctions validate-state-machine-definition \
  --definition file://order-workflow.asl.json \
  --type STANDARD
```

Validation không thay thế integration test. Một definition hợp lệ vẫn có thể gọi sai Lambda ARN, thiếu IAM permission, truyền payload sai schema hoặc tạo side effect không idempotent.

Kiểm tra thêm:

- `StartAt` trỏ đến state tồn tại.
- Mọi `Next`/`Default` trỏ đúng state.
- `Retry`/`Catch` có phân loại lỗi phù hợp.
- `TimeoutSeconds` và heartbeat phù hợp.
- Payload không vượt giới hạn Step Functions.
- Lambda/resource ARN trỏ đến version mong muốn.
- Role có quyền tối thiểu cho đúng task.
- Logging/tracing và encryption đúng môi trường.
- Input schema mới tương thích với producer đang chạy.

## 20. Canary theo alias và tiêu chí tăng traffic

Canary cần tiêu chí định lượng trước khi bắt đầu. Ví dụ:

| Metric/indicator | Điều kiện tiếp tục |
|---|---|
| `ExecutionsFailed` | Không tăng bất thường so với baseline version cũ |
| `ExecutionsTimedOut` | Không tăng và không vượt ngưỡng SLO |
| `ExecutionTime` | p95/p99 không xấu hơn mức cho phép |
| Business success rate | Tỷ lệ hoàn tất nghiệp vụ đạt ngưỡng |
| Compensation rate | Không tăng bất thường |
| Duplicate/idempotency conflict | Không tạo side effect trùng |
| Downstream throttling | Database/API provider vẫn trong capacity |
| Cost per successful operation | Trong budget dự kiến |

Step Functions phát metric theo version/alias khi execution được start bằng qualified ARN. Dùng dimension version/alias để so sánh version cũ và mới. Không chỉ nhìn tổng metric của state machine vì traffic cũ/mới có thể bị trộn.

Canary 5% có thể không đủ mẫu để đánh giá workflow ít traffic hoặc lỗi hiếm. Kéo dài thời gian quan sát hoặc chạy synthetic test có kiểm soát trước khi tăng tỷ lệ.

## 21. Rollback alias không rollback execution đã bắt đầu

Nếu version 13 gây lỗi, chuyển alias `PROD` về version 12:

```bash
aws stepfunctions update-state-machine-alias \
  --state-machine-alias-arn "$STATE_MACHINE_PROD_ALIAS_ARN" \
  --routing-configuration '[
    {
      "stateMachineVersionArn": "arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderFulfillment:12",
      "weight": 100
    }
  ]'
```

Sau rollback:

- Execution mới qua alias sẽ dùng version 12.
- Execution đã bắt đầu trên version 13 vẫn tiếp tục theo version 13.
- Execution version 13 cần được đánh giá: để hoàn tất, stop/compensate hoặc migrate sang execution mới.
- Redrive execution version 13 vẫn dùng definition/version gốc.
- Dependency Lambda/API/database phải tiếp tục tương thích với execution version 13 còn sống.

Rollback alias chỉ đổi route cho execution mới. Nó không đảo ngược database writes, payment, email hoặc event đã phát. Nếu cần dừng execution, `StopExecution` không tự động undo side effect đã xảy ra; compensation/reconciliation vẫn cần thiết.

## 22. Dừng execution và compensation

Chỉ dừng execution khi đã hiểu trạng thái nghiệp vụ và tác động của các task đã hoàn tất.

Trước khi stop:

1. Xác định execution đang ở state nào và đã commit side effect nào.
2. Kiểm tra task bên ngoài có đang chạy hay không.
3. Kiểm tra operation ID/idempotency record và trạng thái database.
4. Xác định compensation cần thiết (release inventory, void authorization, cancel shipment...).
5. Dừng execution nếu không còn đường tiếp tục an toàn.
6. Chạy compensation bằng command idempotent và lưu audit.
7. Cập nhật operation state sang `CANCELLED`, `COMPENSATING` hoặc `MANUAL_REVIEW` theo thực tế.

Stop execution không bảo đảm Lambda invocation hoặc API call bên ngoài đã bị hủy ngay lập tức. Một task có thể đã gửi request và provider vẫn xử lý. Luôn xác minh kết quả side effect trước khi compensation.

## 23. Migration execution sang version mới

Một số workflow dài cần chuyển execution đang chạy sang logic mới. Vì không thể đổi definition của execution tại chỗ, hãy dùng quy trình migration nghiệp vụ.

Một cách tiếp cận:

1. Xác định các state/checkpoint có thể serialize an toàn.
2. Lưu business state bền vững ngoài workflow history nếu cần tiếp tục lâu dài.
3. Xác định side effect đã commit và những bước còn lại.
4. Tạo input schema mới từ checkpoint cũ bằng migration adapter.
5. Tạo execution mới bằng version ARN/alias mong muốn.
6. Gắn `supersedesExecutionArn`/correlation ID đến execution cũ.
7. Dùng idempotency để ngăn chạy lại side effect đã hoàn tất.
8. Chuyển operation record sang execution mới theo conditional update.
9. Stop execution cũ khi xác nhận execution mới đã nhận quyền sở hữu công việc.
10. Đối soát kết quả và lưu migration audit.

Không chạy đồng thời cả execution cũ và mới trên cùng business operation nếu chưa có lease/fencing hoặc single-owner rule. Nếu không thể chứng minh checkpoint an toàn, để execution cũ hoàn tất hoặc xử lý thủ công có kiểm soát.

## 24. Quản lý execution dài và phiên bản cũ

Workflow có Wait state, callback token hoặc bước chờ đối tác có thể tồn tại lâu hơn thời gian deploy. Lập báo cáo execution theo:

- Version/alias được dùng khi start.
- State hiện tại và thời gian ở state.
- Thời gian dự kiến còn lại.
- Dependency version cần thiết ở các state tiếp theo.
- Input schema version.
- Business status và side effect đã commit.
- Khả năng redrive và deadline redrive.

Giữ version cũ và Lambda dependency tương ứng đến khi:

- Không còn execution đang chạy trên version đó.
- Không còn execution có thể redrive cần version đó, hoặc đã hết redrive window.
- Không còn event/queue message cũ có thể khởi động workflow version cũ.
- Không còn caller nào start bằng version ARN cũ.
- Audit/retention policy cho phép xóa artifact.

Không xóa version chỉ vì alias đã chuyển sang version mới. Version cũ có thể vẫn được execution đang chạy hoặc redrive cần đến.

## 25. Ví dụ Java: StartExecution qua alias

Java producer nên dùng alias ARN từ cấu hình, không hardcode unqualified state machine ARN. Ví dụ AWS SDK for Java 2.x:

```java
import software.amazon.awssdk.services.sfn.SfnClient;
import software.amazon.awssdk.services.sfn.model.StartExecutionRequest;
import software.amazon.awssdk.services.sfn.model.StartExecutionResponse;

public final class WorkflowStarter {
    private final SfnClient sfn;
    private final String productionAliasArn;

    public WorkflowStarter(SfnClient sfn, String productionAliasArn) {
        this.sfn = sfn;
        this.productionAliasArn = productionAliasArn;
    }

    public String start(String operationId, String workflowInputJson) {
        StartExecutionRequest request = StartExecutionRequest.builder()
                .stateMachineArn(productionAliasArn)
                .name(toExecutionName(operationId))
                .input(workflowInputJson)
                .build();

        StartExecutionResponse response = sfn.startExecution(request);
        return response.executionArn();
    }

    private String toExecutionName(String operationId) {
        // Chuẩn hóa theo giới hạn ký tự/độ dài của Step Functions.
        return "op-" + operationId.replaceAll("[^A-Za-z0-9_-]", "-");
    }
}
```

Ví dụ rút gọn; cần validate độ dài/tính duy nhất của execution name và serialize input bằng JSON library. Lưu execution ARN cùng operation record để truy vấn trạng thái. Cấu hình alias ARN theo environment qua parameter/config management.

`StartExecution` có semantics idempotency khác nhau theo loại workflow: với Standard, cùng execution name và input khi execution đang chạy sẽ trả lại kết quả start ban đầu; nếu execution đã đóng hoặc input khác, API trả `ExecutionAlreadyExists`. Tên execution có thể được tái sử dụng sau 90 ngày kể từ khi execution đóng. Express không có idempotency của API `StartExecution`. Dù Standard có idempotency, không dùng execution name thay cho business idempotency. Cùng một order có thể bị gửi lại sau khi execution đã đóng, hoặc một request mới có tên khác vẫn tạo side effect trùng.

## 26. Kiểm tra execution được chạy bằng version nào

Khi start bằng version ARN hoặc alias ARN, Step Functions gắn execution với qualifier được dùng. `DescribeExecution`/`ListExecutions` có thể cung cấp thông tin alias/version tương ứng. Dùng thông tin này trong dashboard và incident triage.

Ví dụ inventory release:

```text
operationId: order-9381
executionArn: arn:...:execution:OrderFulfillment:op-order-9381
stateMachineAliasArn: arn:...:stateMachine:OrderFulfillment:PROD
stateMachineVersionArn: arn:...:stateMachine:OrderFulfillment:13
workflowRelease: orders-2026.11.17.3
inputSchemaVersion: 2
```

Không chỉ ghi alias `PROD`: alias có thể được cập nhật nhiều lần. Cần lưu version được chọn cho từng execution để điều tra chính xác.

CloudWatch metrics theo version/alias có thể giúp so sánh `ExecutionsStarted`, `ExecutionsSucceeded`, `ExecutionsFailed`, `ExecutionsTimedOut` và `ExecutionTime`. Tránh tạo metric dimensions tùy ý từ execution ID vì cardinality cao.

## 27. Quy trình release hoàn chỉnh

Một release có thể theo trình tự:

1. **Source control:** review ASL, task code, schema và release manifest.
2. **Compatibility check:** xác minh workflow mới đọc được input/state cần hỗ trợ và dependency cũ vẫn hoạt động.
3. **Build tasks:** build Java artifact/container, test và publish Lambda function versions bất biến.
4. **Validate definition:** gọi `ValidateStateMachineDefinition` và contract tests.
5. **Update state machine:** cập nhật definition/role/configuration có kiểm soát.
6. **Publish version:** tạo version ARN và lưu artifact metadata.
7. **Smoke test:** start execution bằng version ARN trong staging.
8. **Alias canary:** route tỷ lệ nhỏ execution mới đến version mới.
9. **Observe:** so sánh metrics theo version, business success và downstream impact.
10. **Promote:** tăng weight đến 100% nếu đạt tiêu chí.
11. **Drain old:** theo dõi execution cũ và giữ dependency cần thiết.
12. **Retire:** gỡ code/schema/resource cũ khi không còn execution cần.

Trong pipeline, không chạy `UpdateStateMachine` và lập tức đổi alias mà không chờ publish/version ARN và xác minh trạng thái. AWS lưu ý các `StartExecution` gọi ngay sau `UpdateStateMachine` trong vài giây có thể còn sử dụng definition/role cũ; qualified version/alias giúp release rõ ràng hơn.

## 28. Các failure scenario cần diễn tập

| Scenario | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Version mới lỗi ở canary | Tạo lỗi có kiểm soát trong task test | Rollback alias chỉ ảnh hưởng execution mới |
| Execution cũ đang chờ | Giữ Wait/callback rồi publish version mới | Execution cũ tiếp tục theo definition cũ |
| Dependency alias bị đổi | Chuyển Lambda alias trong khi workflow cũ chưa đến task | Phát hiện dependency drift; pin version hoặc giữ compatibility |
| Redrive sau release | Làm execution cũ thất bại rồi redrive | Redrive dùng definition/version gốc |
| Input schema đổi | Start execution cũ rồi deploy producer schema mới | Adapter/compatibility giúp execution cũ tiếp tục |
| Rollback sau side effect | Task đã reserve inventory rồi version mới lỗi | Compensation/reconciliation không tạo side effect lặp |
| Alias canary lệch lỗi | Tạo lỗi chỉ ở version mới | Metric version-specific phát hiện và rollback |
| Workflow mới thiếu IAM | Bỏ quyền ở role test | Validation/integration test chặn trước production |
| Migration execution | Tạo checkpoint và start version mới | Single-owner/idempotency ngăn hai execution cùng xử lý |
| Xóa version cũ quá sớm | Thử retire khi còn execution/redrive | Release gate chặn xóa dependency còn cần |

## 29. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Cho rằng update definition chuyển execution cũ | Kỳ vọng sai về logic đang chạy | Execution cũ giữ definition/role cũ; lập chính sách drain/migrate |
| Start execution bằng unqualified ARN | Khó truy vết version/alias và kiểm soát release | Dùng alias/version ARN cho production |
| Chỉ version hóa state machine | Lambda alias/dependency vẫn đổi bên dưới | Pin task versions hoặc giữ compatibility |
| Chuyển alias rồi xóa version cũ | Execution cũ/redrive có thể không còn dependency | Drain và kiểm tra redrive trước retire |
| Dùng redrive để áp definition mới | Redrive tiếp tục definition cũ | Tạo execution mới với input/checkpoint đã chuyển đổi |
| Restart toàn bộ workflow từ đầu | Side effect cũ có thể lặp | Checkpoint, idempotency và compensation |
| Không version hóa input schema | Execution cũ không đọc được field mới | Additive change, adapter và expand-contract |
| Canary nhưng chỉ xem tổng metric | Lỗi version mới bị lẫn vào baseline | Dùng metrics dimension version/alias |
| Cho rằng alias routing sticky theo tenant | Cùng tenant có thể đi vào nhiều version | Route/pin version theo business ID nếu cần |
| Sửa IAM policy của role đang dùng | Execution cũ có thể bị thay đổi quyền hiệu lực | Quản lý policy như artifact và review compatibility |
| Không lưu workflow release metadata | Incident không biết execution dùng release nào | Ghi version ARN, commit, schema và dependency manifest |

## 30. Checklist trước khi phát hành

- [ ] Definition được review, validate và lưu trong source control.
- [ ] State machine version mới được publish và có version ARN.
- [ ] Alias production trỏ đến version đã kiểm thử.
- [ ] Caller dùng alias/version ARN thay vì unqualified ARN.
- [ ] Workflow/task dependency được pin hoặc có compatibility window.
- [ ] Input/event schema có version và migration path.
- [ ] Database schema dùng expand-contract nếu execution cũ còn chạy.
- [ ] Execution cũ được phân loại theo version/alias và state hiện tại.
- [ ] Có drain deadline và chính sách cho execution dài.
- [ ] Redrive policy hiểu rõ redrive dùng definition gốc.
- [ ] Idempotency key không phụ thuộc riêng vào workflow version.
- [ ] Side effect có compensation/reconciliation khi cần.
- [ ] Canary có weight, duration và ngưỡng promote/rollback.
- [ ] Metrics/logs cho phép phân biệt version/alias.
- [ ] Rollback alias đã được diễn tập; hiểu execution mới của version lỗi vẫn còn chạy.
- [ ] Version/dependency cũ chưa bị xóa khi còn execution hoặc redrive cần.
- [ ] Release manifest lưu commit, workflow version, task versions và schema versions.
- [ ] IAM role/policy, logging, tracing và encryption được kiểm tra.
- [ ] Có runbook xử lý in-flight execution và migration sang execution mới.

## Tài liệu tham khảo

- [Step Functions state machine versions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-version.html)
- [Step Functions state machine aliases](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-alias.html)
- [Continuous deployments with versions and aliases](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-cd-aliasing-versioning.html)
- [Associating executions with versions and aliases](https://docs.aws.amazon.com/step-functions/latest/dg/execution-alias-version-associate.html)
- [UpdateStateMachine API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_UpdateStateMachine.html)
- [StartExecution API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_StartExecution.html)
- [PublishStateMachineVersion API](https://docs.aws.amazon.com/step-functions/latest/apireference/API_PublishStateMachineVersion.html)
- [Redrive executions](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html)
- [Step Functions error handling](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)
- [AWS Lambda function versions and aliases](https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html)

## Kết luận

Phát hành workflow version mới không tự chuyển các execution đang chạy. Step Functions giữ definition và role ARN của execution cũ; version và alias quyết định phiên bản cho execution mới. Hãy publish version bất biến, dùng alias để canary, pin Lambda/task dependencies khi cần reproducibility, và duy trì input/database contract tương thích trong thời gian drain. Khi rollback, alias chỉ đổi route cho execution mới; execution đã chạy trên version lỗi cần được để hoàn tất, stop/compensate hoặc migrate sang execution mới bằng checkpoint có kiểm soát. Redrive Standard Workflow tiếp tục definition gốc, vì vậy phải kết hợp idempotency, release manifest, version-specific observability và chính sách retire dependency rõ ràng.
