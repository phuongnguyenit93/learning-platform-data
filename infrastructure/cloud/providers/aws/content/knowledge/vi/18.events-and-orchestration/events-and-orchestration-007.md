# Amazon States Language và các loại state

> **Chương:** Sự kiện và điều phối  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá AWS qua Region/AZ, IAM, VPC, tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn khả năng thiết kế ứng dụng an toàn, giám sát được, có thể phục hồi và kiểm soát chi phí.

Giả sử một đơn hàng cần thực hiện các bước: kiểm tra dữ liệu, giữ hàng trong kho, chờ phản hồi thanh toán, gửi xác nhận và cập nhật hệ thống vận chuyển. Nếu viết tất cả bằng một lời gọi HTTP hoặc một Lambda duy nhất, ứng dụng phải tự nhớ **đang ở bước nào**, điều gì xảy ra khi timeout, bước nào cần retry, và làm sao tiếp tục sau khi worker bị dừng.

**AWS Step Functions** là dịch vụ điều phối workflow được quản lý. Ta mô tả workflow dưới dạng một **state machine** bằng **Amazon States Language (ASL)**. Từng **state** thể hiện một quyết định, bước xử lý, nhánh song song, chờ đợi hoặc kết thúc; Step Functions theo dõi tiến độ và chuyển trạng thái dựa trên định nghĩa đó.

ASL là một **ngôn ngữ khai báo dựa trên JSON**, không phải ngôn ngữ lập trình thay cho Java, JavaScript hoặc Lambda. State machine xác định **thứ tự điều phối và cách chuyển dữ liệu**, còn nghiệp vụ có thể chạy trong Lambda, ECS, AWS Batch, các dịch vụ AWS khác hoặc ở hệ thống bên ngoài theo cơ chế callback.

Bài học tập trung vào **cấu trúc ASL và các loại state**; đồng thời minh họa JSONPath/JSONata, xử lý lỗi, tích hợp dịch vụ và những giới hạn cần cân nhắc khi thiết kế production. Các ARN, tài khoản AWS, tên queue và payload đều là dữ liệu minh họa.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Đọc và viết một định nghĩa ASL hợp lệ với `StartAt`, `States`, `Type`, `Next` và `End`.
2. Phân biệt đủ **tám loại state**: **Task, Pass, Choice, Wait, Succeed, Fail, Parallel, Map**.
3. Giải thích sự khác nhau giữa **state**, **transition**, **execution**, **task** và **service integration**.
4. Chuyển dữ liệu qua các state bằng **JSONPath** (`InputPath`, `Parameters`, `ResultSelector`, `ResultPath`, `OutputPath`) hoặc **JSONata** (`Arguments`, `Assign`, `Output`, `Condition`).
5. Thiết kế `Retry`, `Catch`, timeout, heartbeat và **fallback/compensation** có giới hạn.
6. Chọn **Standard** hoặc **Express Workflow** theo thời lượng, độ tin cậy, tính chất workload và mô hình chi phí.
7. Áp dụng `Parallel` và `Map` cho phân nhánh/xử lý nhiều phần tử, biết giới hạn concurrency và side effects.
8. Kiểm tra state machine qua AWS Console/CLI, quan sát execution history, IAM và chi phí.

## 2. ASL là bản thiết kế workflow, không phải code chạy trong một container

### 2.1. Các khái niệm cơ bản

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **State machine** | Định nghĩa workflow gồm các state và quy tắc chuyển state |
| **State** | Một bước có kiểu xác định như `Task`, `Choice` hoặc `Wait` |
| **Execution** | Một lần chạy của state machine với input và execution context riêng |
| **Transition** | Việc workflow chuyển từ state này sang state khác |
| **Task** | Một state gọi công việc hoặc AWS service integration |
| **Input / Output** | JSON đi vào / đi ra một state, có thể được biến đổi |
| **Execution history** | Thông tin các bước đã chạy, kết quả/lỗi và thời điểm, tùy workflow type và logging |
| **State machine role** | IAM execution role Step Functions dùng để gọi các dịch vụ tích hợp |

Một state machine có thể nhận input:

~~~json
{
  "orderId": "order-101",
  "customerId": "customer-42",
  "amount": 350000,
  "currency": "VND"
}
~~~

State `ReserveInventory` xử lý và tạo output, sau đó `CheckReservation` chọn nhánh. Không phải Step Functions sẽ tự cấp cho mọi task quyền truy cập database: **IAM role**, networking, endpoint và ứng dụng phải được cấu hình riêng.

### 2.2. Ví dụ nhỏ nhất có ý nghĩa

~~~json
{
  "Comment": "Ví dụ ASL không gọi dịch vụ bên ngoài",
  "StartAt": "PrepareGreeting",
  "States": {
    "PrepareGreeting": {
      "Type": "Pass",
      "Result": {
        "message": "Xin chào AWS Step Functions"
      },
      "End": true
    }
  }
}
~~~

Đọc theo thứ tự:

1. `StartAt` chỉ tên state bắt đầu: `PrepareGreeting`.
2. `States` là object chứa **các state với tên duy nhất trong phạm vi đó**.
3. `Type: "Pass"` nghĩa là bước này không gọi Lambda hay API ngoài.
4. `Result` cung cấp JSON kết quả cố định cho Pass state ở cách viết **JSONPath**.
5. `End: true` đánh dấu kết thúc thành công nhánh đang chạy; workflow không có state kế tiếp.

Đây là **JSON thực**, không được thêm comment `//...` vào file định nghĩa ASL JSON. ASL có thuộc tính `Comment` để ghi chú; không đồng nhất với JSON comment.

### 2.3. Luồng chuyển trạng thái

~~~mermaid
flowchart LR
    START(["StartAt"]) --> A["State A"]
    A -->|"Next"| B["State B"]
    B -->|"Next"| C{"Choice"}
    C -->|"Đúng"| D["Task"]
    C -->|"Sai"| F["Fail"]
    D --> E(["Succeed / End=true"])
~~~

Các state chuyển tiếp thông thường dùng **`Next`** hoặc đánh dấu **`End: true`**; **không đặt cả hai ở cùng một state**. Một số loại state có cơ chế kết thúc riêng:

- **`Choice`** chuyển theo các rules và `Default`, không dùng `End` như Task/Pass.
- **`Succeed`** và **`Fail`** là trạng thái kết thúc; không cần `Next` hoặc `End`.
- Một **branch** bên trong `Parallel` hoặc `Map` có điểm bắt đầu/kết thúc riêng.

### 2.4. Các trường top-level thường gặp

| Thuộc tính | Chức năng |
| --- | --- |
| `Comment` | Mô tả tùy chọn cho state machine |
| `StartAt` | Tên state đầu tiên; bắt buộc |
| `States` | Tập định nghĩa state; bắt buộc |
| `Version` | Phiên bản ASL (thường `"1.0"` nếu khai báo) |
| `TimeoutSeconds` | Giới hạn thời gian cho execution khi được hỗ trợ |
| `QueryLanguage` | `"JSONPath"` (mặc định) hoặc `"JSONata"` theo cấu hình |

Không được tự suy rằng các field có tiền tố `Parameters`/`ResultPath` tồn tại hợp lệ trong **mọi** state/QueryLanguage. Tính hợp lệ phụ thuộc **loại state**, **chế độ JSONPath/JSONata** và tài liệu dịch vụ hiện hành.

## 3. Tám loại state trong ASL

| Loại state | Chức năng chính | Thuộc tính nổi bật | Ví dụ |
| --- | --- | --- | --- |
| **Task** | Thực hiện công việc qua service integration / activity | `Resource`, `Parameters`/`Arguments`, `Retry`, `Catch` | Gọi Lambda kiểm tra kho |
| **Pass** | Truyền hoặc biến đổi JSON không gọi dịch vụ ngoài | `Result`, `Parameters`, `ResultPath` hoặc `Output` | Chuẩn hóa dữ liệu |
| **Choice** | Rẽ nhánh theo điều kiện | `Choices`, `Default` | Phê duyệt / từ chối |
| **Wait** | Chờ khoảng thời gian hoặc thời điểm | `Seconds`, `Timestamp` và các biến thể Path/JSONata | Chờ thời điểm gửi email |
| **Succeed** | Kết thúc nhánh/execution thành công | `Type: "Succeed"` | Hoàn tất đơn hàng |
| **Fail** | Kết thúc nhánh/execution thất bại | `Error`, `Cause` hoặc biểu thức được hỗ trợ | Dữ liệu đầu vào không hợp lệ |
| **Parallel** | Chạy nhiều nhánh song song, tổng hợp kết quả | `Branches` | Kiểm tra kho và chống gian lận |
| **Map** | Chạy một bộ xử lý trên từng phần tử của collection | `ItemsPath`, `ItemProcessor`, `MaxConcurrency` | Xử lý từng item trong đơn |

Các state phục vụ các mục đích **khác nhau**. `Parallel` không tự tạo hai Lambda functions; nó điều phối các nhánh mà bạn định nghĩa. `Map` không tự chẻ message SQS hoặc xử lý dữ liệu lớn mà không tính giới hạn. `Choice` chỉ so điều kiện, không thay thế việc xác thực giá trị nghiệp vụ ở backend.

## 4. Task: gọi Lambda và các AWS service integrations

**Task** là state để thực hiện công việc. Thuộc tính cốt lõi là **`Resource`** — ARN hoặc mã tích hợp do Step Functions hiểu.

### 4.1. Task gọi Lambda theo dạng optimized integration

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Parameters": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:check-stock",
    "Payload.$": "$"
  },
  "ResultSelector": {
    "stock.$": "$.Payload"
  },
  "ResultPath": "$.stockCheck",
  "Next": "DecideStock"
}
~~~

Với **JSONPath**:

- `Resource` chọn **optimized Lambda integration**.
- `FunctionName` là Lambda function ARN cần gọi.
- `Payload.$: "$"` chuyển **toàn bộ input của Task** làm payload cho Lambda.
- Lambda optimized integration trả response gồm `Payload` và metadata; `ResultSelector` giữ lại payload nghiệp vụ dưới tên `stock`.
- `ResultPath: "$.stockCheck"` đưa kết quả vào trường `stockCheck` mà vẫn giữ những field input khác.
- `Next` chọn state tiếp theo.

Ví dụ Task input:

~~~json
{"orderId":"order-101","qty":2}
~~~

Lambda payload kết quả (giả sử):

~~~json
{"available":true,"warehouse":"A"}
~~~

Output sau `ResultSelector` và `ResultPath`:

~~~json
{
  "orderId": "order-101",
  "qty": 2,
  "stockCheck": {
    "stock": {
      "available": true,
      "warehouse": "A"
    }
  }
}
~~~

**Nếu bỏ `ResultPath`**, mặc định result có thể **thay thế toàn bộ input**; state sau đó sẽ không còn `orderId` tại đường `$.orderId` như mong đợi. Đây là lỗi thiết kế ASL khá phổ biến.

### 4.2. Các kiểu tích hợp Task

Step Functions hỗ trợ các mẫu tích hợp tùy dịch vụ và API:

| Mẫu | Cách hiểu | Khi phù hợp |
| --- | --- | --- |
| **Request-response** | Gửi lời gọi service API rồi tiếp tục khi nhận kết quả của lời gọi | Lambda synchronous invoke, gửi SQS message, gọi một AWS API |
| **Run a job (`.sync`)** | Chờ công việc dịch vụ được hỗ trợ hoàn tất | ECS task, Batch job hoặc job dài theo integration được hỗ trợ |
| **Wait for callback (`.waitForTaskToken`)** | Giao task token cho hệ thống ngoài, đợi callback hợp lệ | Phê duyệt con người, worker bên ngoài |

Không phải mọi AWS service/API hỗ trợ đủ cả ba mẫu. Phải kiểm tra **supported integration patterns** của Resource cụ thể.

Ví dụ service integrations thường gặp:

~~~text
arn:aws:states:::lambda:invoke        (Lambda optimized)
arn:aws:states:::sqs:sendMessage     (SQS)
arn:aws:states:::sns:publish         (SNS)
arn:aws:states:::events:putEvents    (EventBridge)
arn:aws:states:::ecs:runTask.sync    (chạy và chờ ECS task theo hỗ trợ)
~~~

Một Task gọi SQS `SendMessage` trả thành công khi **SQS chấp nhận message**, không phải khi consumer xử lý xong business job. Nếu cần **chờ downstream hoàn tất**, phải dùng pattern callback/job completion hoặc một workflow khác — không hiểu response 200 của enqueue là công việc hoàn tất.

### 4.3. Task có timeout và heartbeat

Các thuộc tính `TimeoutSeconds` và `HeartbeatSeconds` có thể áp dụng cho **Task** theo mode/tích hợp, giúp Step Functions phát hiện task quá thời gian hoặc không có heartbeat khi task chờ callback/activity.

- **Timeout**: giới hạn task execution.
- **Heartbeat**: kiểm tra sự sống của công việc trong những tích hợp có cơ chế báo tiến độ thích hợp.
- **`HeartbeatSeconds` không tự biến Lambda invoke thành tác vụ có heartbeat**; cần service/pattern hỗ trợ.
- Task có thể đã thực hiện side effect ở hệ thống ngoài trước khi workflow nhận lỗi timeout. Retry **phải idempotent**.

Ví dụ callback task sẽ được trình bày ở phần mẫu nâng cao.

## 5. Pass: biến đổi dữ liệu không gọi backend

**Pass state** hữu ích khi muốn dựng cấu trúc input mới, gắn metadata, debug luồng hoặc mô phỏng kết quả mà không tạo một Lambda chỉ để di chuyển JSON.

Ví dụ dùng **`Parameters`** ở ASL JSONPath:

~~~json
{
  "Type": "Pass",
  "Parameters": {
    "orderId.$": "$.orderId",
    "source": "web",
    "priority": "normal"
  },
  "ResultPath": "$.normalized",
  "Next": "CheckStock"
}
~~~

Với input:

~~~json
{"orderId":"order-101","amount":350000}
~~~

Output có thêm:

~~~json
{
  "orderId": "order-101",
  "amount": 350000,
  "normalized": {
    "orderId": "order-101",
    "source": "web",
    "priority": "normal"
  }
}
~~~

Nhận diện hậu tố **`.$`** trong JSONPath:

- `"orderId.$": "$.orderId"` lấy **giá trị từ JSONPath**.
- `"source": "web"` là giá trị **literal**, không truy cập dữ liệu input.
- `"priority": "normal"` cũng là literal.

Một giá trị JSONPath không tồn tại có thể gây lỗi runtime thay vì im lặng gán `null`; hãy kiểm tra với `Choice IsPresent` hoặc thiết kế default.

### 5.1. `ResultPath: null` để bỏ kết quả

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Parameters": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:audit-only",
    "Payload.$": "$"
  },
  "ResultPath": null,
  "Next": "ContinueProcessing"
}
~~~

Ở chế độ JSONPath, `ResultPath: null` giúp **bỏ qua Task result** và chuyển input ban đầu tới state kế tiếp. Dùng khi chỉ cần side effect (như ghi audit), nhưng vẫn phải xử lý lỗi/catch; bỏ result **không** có nghĩa side effect đã xảy ra chính xác một lần.

## 6. Choice: rẽ nhánh và xử lý điều kiện không khớp

**Choice state** đọc giá trị input, so sánh bằng các **choice rules** và chuyển tới một trong những state đã định nghĩa.

~~~json
{
  "Type": "Choice",
  "Choices": [
    {
      "Variable": "$.amount",
      "NumericGreaterThan": 0,
      "Next": "ProcessPayment"
    },
    {
      "Variable": "$.amount",
      "NumericEquals": 0,
      "Next": "ProcessFreeOrder"
    }
  ],
  "Default": "RejectAmount"
}
~~~

Các điều kiện được xét theo thứ tự và chọn nhánh phù hợp đầu tiên. Nếu không rule nào khớp **và không có `Default`**, state machine có thể thất bại vì không tìm được transition hợp lệ.

### 6.1. Kiểm tra field trước khi so sánh

Không giả định `$.amount` luôn tồn tại hoặc là số. Có thể dùng operator phối hợp:

~~~json
{
  "Type": "Choice",
  "Choices": [
    {
      "And": [
        { "Variable": "$.amount", "IsPresent": true },
        { "Variable": "$.amount", "IsNumeric": true },
        { "Variable": "$.amount", "NumericGreaterThan": 0 }
      ],
      "Next": "ProcessPayment"
    }
  ],
  "Default": "RejectAmount"
}
~~~

Các operator JSONPath hỗ trợ kiểu so sánh như StringEquals, NumericGreaterThan, BooleanEquals, IsPresent, IsNull, IsString, Timestamp... và tổ hợp `And`, `Or`, `Not` tùy schema. Với input có type không đồng nhất, nên validate thêm ở application boundary thay vì dựa hoàn toàn vào Choice.

### 6.2. Choice không tự tạo error handling

`Choice` chỉ điều hướng:

~~~mermaid
flowchart TB
    V{"Choice\namount > 0?"}
    V -->|"Có"| PAY["Task: ChargePayment"]
    V -->|"Không"| FAIL["Fail: InvalidAmount"]
~~~

Nó không bắt exception từ `ChargePayment`. Nếu Task đó có thể lỗi, dùng **`Retry` / `Catch` trong Task** (hoặc trong các state được hỗ trợ), sau đó điều hướng tới bước bù trừ/thông báo tương ứng.

## 7. Wait: chờ theo khoảng thời gian hoặc thời điểm

**Wait state** là cách diễn đạt một khoảng dừng rõ ràng trong workflow, không cần dùng vòng lặp `Thread.sleep` trong một Lambda đang bị tính thời gian chạy.

Ví dụ chờ **10 giây**:

~~~json
{
  "Type": "Wait",
  "Seconds": 10,
  "Next": "RecheckStatus"
}
~~~

Ví dụ chờ tới một thời điểm cố định UTC:

~~~json
{
  "Type": "Wait",
  "Timestamp": "2027-01-15T09:00:00Z",
  "Next": "SendReminder"
}
~~~

Trong JSONPath, có thể lấy thời gian chờ từ input qua `SecondsPath` hoặc `TimestampPath`, ví dụ:

~~~json
{
  "Type": "Wait",
  "SecondsPath": "$.retryDelaySeconds",
  "Next": "RetryBusinessCheck"
}
~~~

**Chỉ dùng một** trong các cấu hình wait tương ứng. Chú ý thời gian tối đa một execution khác nhau giữa Standard và Express; đừng dùng Wait nhiều giờ trong một Express execution có giới hạn ngắn. Với thời gian chờ rất dài hoặc lịch định kỳ, đánh giá EventBridge Scheduler và loại workflow phù hợp.

### 7.1. Wait không thay thế retry

Một loop:

~~~text
CheckStatus Task → Choice
  Completed  → Succeed
  Pending    → Wait 10s → CheckStatus Task
  Failed     → Fail
~~~

có thể hữu ích khi một API chỉ cung cấp trạng thái polling. Nhưng cần giới hạn **số lần kiểm tra/tổng thời gian**, lưu cancellation state và có timeout toàn workflow để tránh vòng lặp vô hạn tốn phí.

Nếu một Task chỉ gặp transient error và có thể retry cùng request, **`Retry`** thường ngắn gọn hơn một loop Choice/Wait tự viết. Nếu nghiệp vụ yêu cầu kiểm tra trạng thái `PENDING` (không phải lỗi kỹ thuật), loop có Wait có thể phù hợp hơn.

## 8. Succeed và Fail: cách kết thúc có chủ đích

### 8.1. Kết thúc thành công

~~~json
{
  "Type": "Succeed"
}
~~~

`Succeed` kết thúc nhánh hoặc execution tương ứng thành công. Nếu một branch trong Parallel đi tới Succeed, **chỉ branch đó hoàn tất**; Parallel còn chờ các branch khác theo semantics của nó.

### 8.2. Kết thúc thất bại

~~~json
{
  "Type": "Fail",
  "Error": "InvalidOrderAmount",
  "Cause": "Order amount must be a positive number"
}
~~~

`Fail` đánh dấu lỗi có chủ đích, ví dụ không thể chấp nhận dữ liệu. Nó khác Task lỗi không được catch, nhưng kết quả chung có thể là **execution failed**.

Một bước bù trừ trong workflow (ví dụ hủy giữ hàng thành công) không có nghĩa đơn hàng được xử lý thành công. Có thể kết thúc bằng Fail để hệ thống upstream biết rằng **business transaction đã bị từ chối**, hoặc kết thúc Succeed với output `status: REJECTED` nếu contract cố ý định nghĩa như vậy. Cần thống nhất metric và API contract.

### 8.3. Không dùng Fail để giấu lỗi tạm thời

Nếu Lambda trả 429 hoặc upstream 503, nên phân loại lỗi, retry giới hạn và có fallback/queue/DLQ phù hợp. Đưa ngay mọi transient error tới Fail có thể làm giảm tỉ lệ thành công; ngược lại retry vô hạn có thể làm downstream quá tải.

## 9. Parallel: chạy nhiều nhánh độc lập

**Parallel state** điều phối nhiều **branches**, mỗi branch là một state machine con có `StartAt` và `States`. Các branches được chạy song song ở mức workflow; Step Functions chờ những nhánh theo semantics của Parallel trước khi đi tiếp.

Ví dụ kiểm tra hai điều kiện độc lập (mẫu chạy được với Pass):

~~~json
{
  "Type": "Parallel",
  "Branches": [
    {
      "StartAt": "CheckStock",
      "States": {
        "CheckStock": {
          "Type": "Pass",
          "Result": { "stockAvailable": true },
          "End": true
        }
      }
    },
    {
      "StartAt": "CheckFraud",
      "States": {
        "CheckFraud": {
          "Type": "Pass",
          "Result": { "risk": "LOW" },
          "End": true
        }
      }
    }
  ],
  "ResultPath": "$.checks",
  "Next": "DecideOrder"
}
~~~

Result của Parallel thông thường là **một array**, tương ứng với outputs của branches theo thứ tự khai báo:

~~~json
{
  "checks": [
    { "stockAvailable": true },
    { "risk": "LOW" }
  ]
}
~~~

Vì dùng `ResultPath: "$.checks"`, khi input có thêm `orderId` thì output còn giữ `orderId` cùng trường `checks` mới.

### 9.1. Khi một branch lỗi

Nếu một branch thất bại mà không có cơ chế catch thích hợp, **Parallel state có thể thất bại và không đợi các branch còn lại thành công như luồng bình thường**. Những việc đã được branch khác gọi trước đó (email, ghi DB, gọi API ngoài) **không tự được rollback**.

Do đó:

- Những side effects trong branches phải **idempotent**.
- Khi cần compensation, thiết kế riêng Task bù trừ theo kết quả đã commit, không dựa vào rollback tự động.
- Cần hiểu Retry/Catch đặt tại **Task con** khác với Retry/Catch bao quanh **Parallel**: retry toàn Parallel có thể khởi chạy lại nhiều nhánh, bao gồm nhánh đã từng thành công.

### 9.2. Khi nào nên dùng Parallel?

**Phù hợp:** kiểm tra tín dụng và tồn kho độc lập trước khi quyết định; gọi hai hệ thống có latency đáng kể mà dữ liệu không phụ thuộc lẫn nhau. **Không phù hợp:** một nhánh tạo mã đặt hàng còn nhánh kia cần chính mã đó — đây là phụ thuộc tuần tự.

## 10. Map: chạy một workflow con trên từng phần tử

**Map state** giống vòng lặp có điều phối. Nó nhận một collection, tạo một **iteration** cho mỗi phần tử và thực hiện các state bên trong `ItemProcessor`.

~~~mermaid
flowchart TB
    INPUT["Input: items = [A, B, C]"] --> MAP["Map state"]
    MAP --> A["ItemProcessor(A)"]
    MAP --> B["ItemProcessor(B)"]
    MAP --> C["ItemProcessor(C)"]
    A --> ARR["Array of iteration outputs"]
    B --> ARR
    C --> ARR
    ARR --> NEXT["Next state"]
~~~

### 10.1. Inline Map với `ItemsPath` và `ItemSelector`

Ví dụ hợp lệ theo kiểu **JSONPath**, xử lý các phần tử trong `$.items`:

~~~json
{
  "Type": "Map",
  "ItemsPath": "$.items",
  "MaxConcurrency": 3,
  "ItemSelector": {
    "orderId.$": "$.orderId",
    "item.$": "$$.Map.Item.Value",
    "itemIndex.$": "$$.Map.Item.Index"
  },
  "ItemProcessor": {
    "ProcessorConfig": {
      "Mode": "INLINE"
    },
    "StartAt": "MakeItemResult",
    "States": {
      "MakeItemResult": {
        "Type": "Pass",
        "Parameters": {
          "itemId.$": "$.item.id",
          "processed": true,
          "itemIndex.$": "$.itemIndex"
        },
        "End": true
      }
    }
  },
  "ResultPath": "$.itemResults",
  "Next": "SummarizeOrder"
}
~~~

Input:

~~~json
{
  "orderId": "order-101",
  "items": [
    { "id": "sku-A" },
    { "id": "sku-B" },
    { "id": "sku-C" }
  ]
}
~~~

Với `ItemSelector`, mỗi iteration nhận cả thông tin đơn hàng và một item cụ thể. Kết quả của Map là một **array** được đặt vào `$.itemResults`:

~~~json
{
  "orderId": "order-101",
  "items": [
    { "id": "sku-A" },
    { "id": "sku-B" },
    { "id": "sku-C" }
  ],
  "itemResults": [
    { "itemId": "sku-A", "processed": true, "itemIndex": 0 },
    { "itemId": "sku-B", "processed": true, "itemIndex": 1 },
    { "itemId": "sku-C", "processed": true, "itemIndex": 2 }
  ]
}
~~~

**`ItemSelector`** biến đổi input được đưa vào từng iteration; còn **`ItemsPath`** chọn collection đầu vào. **`ItemProcessor`** định nghĩa workflow con, không phải ARN Lambda duy nhất. Ví dụ này chỉ dùng Pass nên không có side effect.

### 10.2. Map khác Parallel

| Tiêu chí | Parallel | Map |
| --- | --- | --- |
| Nhánh | Các branch được **định nghĩa tường minh** trong `Branches` | Một `ItemProcessor` được lặp trên collection |
| Số lượng | Số branch xác định trong định nghĩa | Số iteration dựa theo data input hoặc reader |
| Kết quả | Array theo outputs của branches | Array của iterations (hoặc cách ghi kết quả cho Distributed Map) |
| Mục đích | Nhiều phép kiểm tra **khác loại** độc lập | Lặp cùng logic trên **nhiều phần tử cùng dạng** |
| Concurrency | Các branches có thể chạy song song | Điều khiển qua `MaxConcurrency` và giới hạn mode |

Nếu cần kiểm tra `creditRisk` và `stock` bằng hai logic khác nhau, chọn Parallel. Nếu cần kiểm tra 500 order line items theo cùng logic, chọn Map; kiểm tra quy mô để chọn mode phù hợp.

### 10.3. Inline và Distributed Map

Step Functions có hai kiểu xử lý Map với đặc tính khác nhau:

- **Inline Map:** iterations chạy như một phần của parent execution; phù hợp collections nhỏ, giới hạn concurrency và event history của execution.
- **Distributed Map:** tạo **child workflow executions** để xử lý datasets lớn theo hỗ trợ; có thể đọc nguồn như S3, dùng `ItemReader`, `ItemBatcher`, `ResultWriter` và các cấu hình chuyên biệt tùy use case.

**Đừng đưa hàng trăm nghìn records thẳng vào JSON input** của một state machine: có giới hạn payload và execution history. Distributed Map có thể đọc collection từ S3 và lưu output ra S3 theo khả năng dịch vụ, nhưng cần IAM, quota, kiểm soát child execution failures và **chi phí số lượng execution/transitions**.

### 10.4. Concurrency và downstream capacity

Nếu Map chạy 500 iterations cùng lúc mà mỗi iteration gọi database, DB có thể cạn connection pool. Không chọn `MaxConcurrency` chỉ theo số phần tử; cần căn cứ:

1. Giới hạn connections/requests của downstream.
2. Mức parallelism an toàn của Lambda/ECS/third-party APIs.
3. Bản chất input: có cần giữ thứ tự/cùng một entity không?
4. Ngân sách, retry count và quota Step Functions.

Map **không tự bảo đảm exactly-once side effects**; iteration có thể được retry và dữ liệu bên ngoài có thể đã được ghi. Idempotency vẫn cần thiết.

### 10.5. Một iteration thất bại ảnh hưởng thế nào?

Với Inline Map, lỗi một iteration không được xử lý có thể làm **Map state thất bại**. Đặt `Catch` ở Task bên trong khi muốn ghi nhận lỗi từng item rồi tiếp tục, hoặc dùng Catch ở Map khi muốn xử lý thất bại của toàn Map.

Với Distributed Map, có thêm các cấu hình **failure tolerance** (tỷ lệ/số item thất bại được phép theo khả năng) và quản lý Map Run. Chọn kỹ: “tiếp tục dù 5% item lỗi” chỉ phù hợp khi nghiệp vụ **thực sự chấp nhận** mất/chậm các item đó và có lộ trình khắc phục.

## 11. Luồng dữ liệu JSONPath: đường đi qua một state

Trong ASL mặc định dùng **`QueryLanguage: JSONPath`**, Step Functions có những trường hỗ trợ điều khiển dữ liệu:

~~~mermaid
flowchart LR
    IN["State input"] --> IP["InputPath\nlọc input"]
    IP --> PARAM["Parameters\nchuẩn bị task payload"]
    PARAM --> TASK["Task/State work"]
    TASK --> RS["ResultSelector\nchọn result"]
    RS --> RP["ResultPath\nhợp nhất input + result"]
    RP --> OP["OutputPath\nlọc output"]
    OP --> OUT["Next state input"]
~~~

*Thứ tự trong sơ đồ mô tả các trường liên quan ở những state được hỗ trợ, không phải mọi trường đều hợp lệ trong tất cả các state types. Với JSONata, mô hình trường khác.*

### 11.1. Bốn path dễ nhầm

| Thuộc tính | Dùng để làm gì? | Ví dụ |
| --- | --- | --- |
| **`InputPath`** | Chọn phần JSON input đi vào state xử lý | `"$.order"` |
| **`Parameters`** | Dựng payload/arguments cho công việc từ literals, paths, intrinsics | `"orderId.$": "$.id"` |
| **`ResultSelector`** | Biến đổi/chọn subset kết quả raw của Task, Parallel hoặc Map theo hỗ trợ | `"data.$": "$.Payload"` |
| **`ResultPath`** | Gắn result vào input, thay input hoặc bỏ result | `"$.result"`, `"$"`, `null` |
| **`OutputPath`** | Chọn phần JSON đầu ra chuyển cho state tiếp theo | `"$.response"` |

Không có `ResultPath` tương đương “gộp input + result tự động”. Mặc định của nó thường là `"$"`, **result thay toàn bộ input**. Đó là lý do nhiều ví dụ cần chỉ rõ `"ResultPath": "$.something"`.

### 11.2. Ví dụ từng bước

Giả sử Task có input:

~~~json
{
  "order": {
    "id": "order-101",
    "amount": 350000
  },
  "requestMeta": {
    "source": "web"
  }
}
~~~

Nếu đặt `InputPath: "$.order"`, Task chỉ thấy:

~~~json
{"id":"order-101","amount":350000}
~~~

Sau đó `Parameters` có thể tạo request:

~~~json
{
  "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:calculate-discount",
  "Payload": {
    "orderId": "order-101",
    "amount": 350000
  }
}
~~~

Giả sử Lambda trả `Payload: {"discount":10000}` và ResultSelector chọn phần đó. Nếu dùng `ResultPath: "$.discountData"`, output được gắn vào **input đã qua `InputPath`**:

~~~json
{
  "id": "order-101",
  "amount": 350000,
  "discountData": {
    "discount": 10000
  }
}
~~~

Field `requestMeta` không trở lại vì đã bị cắt bởi `InputPath` ở đầu state. Nếu cần giữ nó, **đừng bỏ đi trước**, hoặc cấu trúc `Parameters`/`ResultPath` khác theo mục tiêu.

### 11.3. JSONPath và `.$` trong Parameters

~~~json
{
  "Parameters": {
    "fixed": "constant",
    "orderId.$": "$.order.id",
    "executionId.$": "$$.Execution.Id",
    "firstItem.$": "$.items[0]"
  }
}
~~~

Đây là **fragment Parameters**, không phải định nghĩa state độc lập. Các giá trị:

- `$` đại diện input JSON hiện tại.
- `$$` truy cập **Context object** (ví dụ `$$.Execution.Id`).
- Hậu tố key `.$` nghĩa là giá trị lấy theo path hoặc intrinsic được hỗ trợ, **không phải literal string**.

**Context object** còn có thông tin về state, execution, task và Map item tùy tình huống. Tránh lưu tràn lan context vào logs vì có thể chứa định danh/tokens nội bộ.

### 11.4. Intrinsic functions trong JSONPath

ASL hỗ trợ các intrinsic functions cho một số field JSONPath, ví dụ:

~~~json
{
  "Parameters": {
    "orderId.$": "$.orderId",
    "uniqueExecutionId.$": "$$.Execution.Id",
    "itemCount.$": "States.ArrayLength($.items)",
    "serializedOrder.$": "States.JsonToString($.order)"
  }
}
~~~

Đây cũng là **fragment**. Intrinsics giúp dựng chuỗi, mảng, JSON, toán học và một số biến đổi đơn giản mà không cần tạo Lambda cho mỗi thao tác nhỏ. **Không áp dụng `States.*` intrinsics vào các trường JSONata**, vì hai ngôn ngữ diễn đạt dữ liệu khác nhau.

### 11.5. Payload size và dữ liệu nhạy cảm

Mỗi state truyền JSON theo các giới hạn payload của Step Functions. Những dữ liệu lớn như ảnh, file báo cáo hoặc hàng triệu bản ghi nên được đặt trong **Amazon S3**, rồi chuyển **S3 bucket/key/metadata** giữa các state.

Không gửi token truy cập, secret, dữ liệu thẻ thanh toán hoặc PII không cần thiết vào state input/output; execution history/logs có thể chứa dữ liệu đó tùy cấu hình. Áp dụng encryption, IAM, redaction và retention thích hợp.

## 12. JSONata: viết biểu thức mà không dùng bộ trường JSONPath

ASL hỗ trợ **JSONata** làm query language để biến đổi JSON và biểu diễn điều kiện linh hoạt hơn. Việc chọn ngôn ngữ là **quyết định cú pháp**, không chỉ thay tên trường.

### 12.1. JSONPath và JSONata khác nhau thế nào?

| Chủ đề | ASL JSONPath | ASL JSONata |
| --- | --- | --- |
| Default | Có nếu không đặt `QueryLanguage` | Cần đặt `QueryLanguage: "JSONata"` ở cấp state machine hoặc state hợp lệ |
| Data paths | `InputPath`, `Parameters`, `ResultSelector`, `ResultPath`, `OutputPath` | Thường dùng `Arguments`, `Assign`, `Output`; JSONata expressions |
| Điều kiện Choice | `Variable` + toán tử `StringEquals` / `NumericGreaterThan` ... | `Condition` chứa JSONata expression |
| Tham chiếu input/result | `$` và `$$` context | `$states.input`, `$states.result`, `$states.context` theo phạm vi trường |
| Biểu thức | JSONPath/intrinsic functions như `States.ArrayLength` | JSONata functions, toán tử và `{% ... %}` |
| Phù hợp | Workflow quen thuộc, paths đơn giản | Biến đổi/phép tính/điều kiện phức tạp có cấu trúc |

**Không phối hợp tùy tiện các trường hai chế độ trong cùng state.** Ví dụ một Task state dùng JSONata không nên đồng thời chứa JSONPath-only `Parameters` hoặc `ResultPath`.

### 12.2. Một workflow JSONata đơn giản

~~~json
{
  "QueryLanguage": "JSONata",
  "StartAt": "CalculateGross",
  "States": {
    "CalculateGross": {
      "Type": "Pass",
      "Output": {
        "orderId": "{% $states.input.orderId %}",
        "gross": "{% $states.input.unitPrice * $states.input.quantity %}"
      },
      "End": true
    }
  }
}
~~~

Input:

~~~json
{"orderId":"order-101","unitPrice":100000,"quantity":3}
~~~

Output:

~~~json
{"orderId":"order-101","gross":300000}
~~~

Phần `{% ... %}` được Step Functions xem là **JSONata expression** trong những field hỗ trợ. Kết quả `gross` là số vì expression đánh giá phép nhân, không phải chuỗi literal chứa dấu ngoặc.

### 12.3. JSONata Choice

~~~json
{
  "Type": "Choice",
  "QueryLanguage": "JSONata",
  "Choices": [
    {
      "Condition": "{% $states.input.amount > 0 %}",
      "Next": "AcceptOrder"
    }
  ],
  "Default": "RejectOrder"
}
~~~

Đây là fragment được đặt trong state machine có các state đích. Với JSONata, điều kiện là một biểu thức trả **Boolean**, không dùng `Variable` và `NumericGreaterThan` như JSONPath.

### 12.4. `Arguments` và `Output` trong JSONata Task

~~~json
{
  "Type": "Task",
  "QueryLanguage": "JSONata",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Arguments": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:check-stock",
    "Payload": "{% $states.input %}"
  },
  "Output": {
    "orderId": "{% $states.input.orderId %}",
    "stock": "{% $states.result.Payload %}"
  },
  "Next": "DecideStock"
}
~~~

Ở đây:

- `$states.input` là input của state.
- `Arguments` dựng request cho tích hợp Lambda.
- `$states.result` là kết quả Task trong ngữ cảnh mà field `Output` được phép truy cập.
- `Output` quyết định JSON được chuyển sang state kế tiếp, thay vì dùng bộ `ResultSelector/ResultPath/OutputPath`.

**Nếu Task thất bại**, không thể lấy `$states.result` như thể nó chứa output thành công; cần dùng `Catch`/error handling tương thích. Ví dụ cũng giả định IAM role gọi được Lambda và function trả JSON có schema dự kiến.

### 12.5. `Assign` và variables

JSONata hỗ trợ khai báo state machine **variables** bằng `Assign` để lưu giá trị dùng ở những state theo quy tắc scope. Ví dụ:

~~~json
{
  "Type": "Pass",
  "QueryLanguage": "JSONata",
  "Assign": {
    "savedOrderId": "{% $states.input.orderId %}"
  },
  "Output": {
    "validated": true
  },
  "Next": "DoWork"
}
~~~

State sau có thể đọc variable `$savedOrderId` trong scope hợp lệ. Biến ASL không tự giống một database lâu dài hay shared memory giữa **hai executions** khác nhau. Phạm vi visibility khi dùng **Parallel/Map** và đánh giá đồng thời `Assign`/`Output` cần tuân theo ASL variable scoping/assignment rules; không suy rằng mọi nhánh có thể ghi một biến global chung tùy ý.

### 12.6. Chuyển dần từ JSONPath sang JSONata

Ở state machine có **top-level JSONPath**, một số state có thể khai báo `QueryLanguage: "JSONata"` riêng để chuyển từng phần. Nếu top-level đã chọn **JSONata**, không tùy tiện chuyển state con về JSONPath. Khi migrate:

1. Viết unit test về input/output trước.
2. Chuyển các field JSONPath sang JSONata tương ứng.
3. Xác minh Retry/Catch, Choice, Map và variable scopes.
4. Chạy workflow ở môi trường thử, so kết quả trước/sau.
5. Không deploy cùng lúc thay đổi cú pháp và schema nghiệp vụ nếu có thể tránh.

## 13. Retry và Catch: định nghĩa cách đi qua lỗi

### 13.1. Retry cho lỗi tạm thời

Nhiều Task có thể thất bại do throttling, service unavailable hoặc network transient. **`Retry`** cho phép Step Functions thực hiện lại state theo policy:

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Parameters": {
    "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:reserve-inventory",
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
      "MaxAttempts": 3,
      "BackoffRate": 2,
      "MaxDelaySeconds": 30,
      "JitterStrategy": "FULL"
    }
  ],
  "Catch": [
    {
      "ErrorEquals": ["States.ALL"],
      "ResultPath": "$.error",
      "Next": "HandleInventoryFailure"
    }
  ],
  "Next": "CheckReservation"
}
~~~

**Diễn giải:**

- `ErrorEquals` chọn **loại lỗi** được retry.
- `IntervalSeconds` là khoảng chờ cơ bản ban đầu; `BackoffRate` làm khoảng chờ tăng theo số lần.
- `MaxAttempts` giới hạn số lần **thử lại** theo policy; cần đọc semantics của service, không nhầm với tổng số calls chắc chắn.
- `JitterStrategy: "FULL"` giúp tránh nhiều executions cùng retry đồng loạt.
- `MaxDelaySeconds` giới hạn khoảng chờ tăng tối đa theo quy tắc.
- `Catch` chạy khi lỗi không được Retry xử lý hoặc khi số lần retry hết, rồi chuyển sang state thích hợp.

Không retry mọi lỗi bằng `States.ALL` vô hạn. Nếu body thiếu trường bắt buộc, quyền IAM bị từ chối hoặc schema sai, retry thông thường chỉ tốn tiền và đẩy cùng lỗi tới downstream.

### 13.2. Bắt lỗi vào input bằng `Catch.ResultPath`

Giả sử input trước Task:

~~~json
{"orderId":"order-101","attempt":1}
~~~

Task thất bại và Catch dùng `ResultPath: "$.error"`. State `HandleInventoryFailure` có thể nhận:

~~~json
{
  "orderId": "order-101",
  "attempt": 1,
  "error": {
    "Error": "Lambda.ServiceException",
    "Cause": "Failure details supplied by integration"
  }
}
~~~

`Error` và `Cause` là thông tin phục vụ chẩn đoán; Cause có thể chứa chi tiết kỹ thuật hoặc dữ liệu nhạy cảm tùy integration, nên **không gửi thẳng toàn bộ Cause tới client**.

### 13.3. Những tên lỗi quan trọng

| Error name | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| **`States.Timeout`** | State/task vượt giới hạn thời gian phù hợp | Kiểm tra timeout; quyết định retry/cancel/compensate |
| **`States.HeartbeatTimeout`** | Task chờ heartbeat nhưng quá hạn | Kiểm tra worker/callback, timeout/retry |
| **`States.TaskFailed`** | Match nhóm lỗi task (không bao gồm mọi timeout) | Catch fallback theo ngữ cảnh |
| **`States.Permissions`** | Quyền gọi dịch vụ không phù hợp | Sửa IAM, không retry vô hạn |
| **`States.DataLimitExceeded`** | Payload vượt giới hạn Step Functions | Giảm data trong state, chuyển file sang S3 |
| **`States.Runtime`** | Lỗi xử lý runtime như path/input không hợp lệ | Sửa định nghĩa/schema |
| **`States.ALL`** | Catch-all cho nhiều loại lỗi xử lý được | Đặt sau các catcher chuyên biệt |

**Điểm dễ bỏ sót:** `States.ALL` **không bắt được mọi lỗi trong mọi tình huống**, đặc biệt có các terminal errors như `States.DataLimitExceeded` và `States.Runtime` không thể bị catch theo cách thông thường. Do đó không dùng “Catch ALL” để chứng minh workflow sẽ không bao giờ fail.

### 13.4. Thứ tự và phạm vi Retry/Catch

- Retry rules được xét theo thứ tự để tìm policy phù hợp.
- `States.ALL` phải được dùng theo ràng buộc syntax và cuối danh sách phù hợp, không trộn tùy ý với các error names khác trong cùng `ErrorEquals`.
- Catchers cũng được xét theo thứ tự; đặt specific errors trước catch-all.
- Retry của **Task bên trong Map/Parallel** khác Retry của **Map/Parallel state** bao ngoài: retry nguyên Map/Parallel có thể chạy lại nhiều side effects.
- Không coi Retry là **transaction rollback**.

### 13.5. Phân biệt technical error và business rejection

Ví dụ:

~~~text
Inventory API trả "not enough stock" (câu trả lời hợp lệ)
  → Choice rẽ nhánh RejectOrder

Inventory API timeout hoặc Lambda throttled (lỗi kỹ thuật)
  → Retry có giới hạn
  → Catch sang một nhánh xử lý outage
~~~

Nếu trộn hai loại thành cùng một `throw Error`, workflow dễ retry vô ích những đơn hàng hết hàng, tăng latency và chi phí.

## 14. Một state machine hoàn chỉnh: kiểm tra và xếp hàng thông báo đơn hàng

Ví dụ này dùng **JSONPath** và đủ những thành phần để giải thích một workflow liền mạch: validate input, gọi Lambda, kiểm tra kết quả, dựng payload, gửi SQS và kết thúc. Không thực hiện thanh toán hoặc giữ hàng thật.

### 14.1. Đầu vào

~~~json
{
  "orderId": "order-101",
  "amount": 350000,
  "currency": "VND",
  "items": [
    { "sku": "A-100", "quantity": 2 }
  ]
}
~~~

### 14.2. Định nghĩa ASL

~~~json
{
  "Comment": "Minh họa ASL: validate, check stock, queue notification",
  "StartAt": "ValidateOrder",
  "States": {
    "ValidateOrder": {
      "Type": "Choice",
      "Choices": [
        {
          "And": [
            { "Variable": "$.orderId", "IsPresent": true },
            { "Variable": "$.amount", "IsNumeric": true },
            { "Variable": "$.amount", "NumericGreaterThan": 0 },
            { "Variable": "$.items", "IsPresent": true }
          ],
          "Next": "CheckStock"
        }
      ],
      "Default": "RejectInvalidInput"
    },
    "CheckStock": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:123456789012:function:check-stock",
        "Payload.$": "$"
      },
      "ResultSelector": {
        "availability.$": "$.Payload"
      },
      "ResultPath": "$.inventory",
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
          "ResultPath": "$.inventoryError",
          "Next": "FailDependency"
        }
      ],
      "Next": "RouteByStock"
    },
    "RouteByStock": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.inventory.availability.available",
          "BooleanEquals": true,
          "Next": "PrepareNotification"
        }
      ],
      "Default": "RejectOutOfStock"
    },
    "PrepareNotification": {
      "Type": "Pass",
      "Parameters": {
        "orderId.$": "$.orderId",
        "status": "STOCK_CHECK_PASSED"
      },
      "ResultPath": "$.notification",
      "Next": "SendNotification"
    },
    "SendNotification": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sqs:sendMessage",
      "Parameters": {
        "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/123456789012/order-events-lab",
        "MessageBody.$": "States.JsonToString($.notification)"
      },
      "ResultPath": "$.sendResult",
      "Retry": [
        {
          "ErrorEquals": ["States.TaskFailed"],
          "IntervalSeconds": 2,
          "MaxAttempts": 2,
          "BackoffRate": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.sendError",
          "Next": "FailDependency"
        }
      ],
      "Next": "Completed"
    },
    "Completed": {
      "Type": "Succeed"
    },
    "RejectInvalidInput": {
      "Type": "Fail",
      "Error": "InvalidOrder",
      "Cause": "Required fields or amount are invalid"
    },
    "RejectOutOfStock": {
      "Type": "Fail",
      "Error": "OutOfStock",
      "Cause": "Stock is not available"
    },
    "FailDependency": {
      "Type": "Fail",
      "Error": "UpstreamServiceFailure",
      "Cause": "A dependency failed after retry or recovery was not possible"
    }
  }
}
~~~

Ví dụ gồm **Choice, Task, Pass, Succeed và Fail**. Các state `Wait`, `Parallel`, `Map` được minh họa riêng ở những phần trước; không cần dùng mọi loại state trong cùng một workflow để định nghĩa hợp lệ.

### 14.3. Sơ đồ workflow

~~~mermaid
flowchart TD
    A(["StartAt: ValidateOrder"]) --> V{"Required fields hợp lệ?"}
    V -->|"Không"| BAD["Fail: RejectInvalidInput"]
    V -->|"Có"| INV["Task: CheckStock\nLambda + Retry/Catch"]
    INV -->|"Unrecoverable error"| DEP["Fail: FailDependency"]
    INV --> CHECK{"available == true?"}
    CHECK -->|"Không"| OUT["Fail: RejectOutOfStock"]
    CHECK -->|"Có"| P["Pass: PrepareNotification"]
    P --> SEND["Task: SendNotification\nSQS + Retry/Catch"]
    SEND -->|"Unrecoverable error"| DEP
    SEND -->|"Thành công"| OK(["Succeed: Completed"])
~~~

### 14.4. Đọc luồng output

Giả sử Lambda `check-stock` trả:

~~~json
{"available":true,"warehouse":"SG-01"}
~~~

Sau `CheckStock` và `ResultPath: "$.inventory"`, state có:

~~~json
{
  "orderId": "order-101",
  "amount": 350000,
  "currency": "VND",
  "items": [
    { "sku": "A-100", "quantity": 2 }
  ],
  "inventory": {
    "availability": {
      "available": true,
      "warehouse": "SG-01"
    }
  }
}
~~~

Sau `PrepareNotification`, có thêm:

~~~json
{
  "notification": {
    "orderId": "order-101",
    "status": "STOCK_CHECK_PASSED"
  }
}
~~~

*JSON trên chỉ rút gọn phần mới, không phải toàn output.* Sau `SendNotification`, `$.sendResult` chứa response của SQS integration; `Completed` kết thúc execution thành công.

**Điểm quan trọng về semantics:** `SendNotification` thành công nghĩa là **SQS đã nhận yêu cầu enqueue theo integration**, không phải khách hàng đã nhận email. Nếu producer/Step Functions không chắc request đã thành công và retry, SQS Standard có thể có duplicate messages. Consumer phải idempotent.

### 14.5. Điều kiện để chạy ví dụ

State machine JSON này là định nghĩa workflow, **không tự tạo** các tài nguyên phụ thuộc:

1. Lambda `check-stock` thực sự tồn tại trong Region và trả schema `{"available": true/false}`.
2. SQS `order-events-lab` đã được tạo, có queue URL/ARN đúng.
3. Step Functions execution role có `lambda:InvokeFunction` cho Lambda và `sqs:SendMessage` cho queue.
4. Producer/consumer, dữ liệu, retries, CloudWatch logging và IAM bảo mật được cấu hình phù hợp.
5. Caller có quyền `states:StartExecution` nếu cần bắt đầu execution.
6. Đã thống nhất với hệ thống order rằng chỉ **kiểm tra tồn kho** không đồng nghĩa đã **giữ hàng**; nếu cần reservation thực sự, phải bổ sung nghiệp vụ và compensation theo mô hình transaction.

## 15. Callback pattern với task token: chờ hệ thống bên ngoài

Không phải mọi bước cần chạy ngay. Một quy trình yêu cầu trưởng bộ phận duyệt đơn giá trị lớn có thể cần chờ vài giờ. Step Functions **Standard Workflow** có thể dùng pattern **wait for callback**, giao một **task token** cho worker/ứng dụng ngoài.

~~~mermaid
sequenceDiagram
    participant SF as Step Functions
    participant Q as SQS approval queue
    participant W as Approval worker/service
    participant H as Human reviewer
    SF->>Q: SendMessage kèm taskToken
    Note over SF: Workflow chờ callback
    Q->>W: Worker nhận work item
    W->>H: Yêu cầu phê duyệt
    H-->>W: Approve / Reject
    alt Hoàn tất
        W->>SF: SendTaskSuccess(token, JSON output)
        SF-->>SF: Tiếp tục Next state
    else Lỗi hoặc timeout
        W->>SF: SendTaskFailure hoặc task hết hạn
        SF-->>SF: Retry/Catch/Fail theo định nghĩa
    end
~~~

### 15.1. Task gửi SQS và chờ callback

~~~json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
  "Parameters": {
    "QueueUrl": "https://sqs.ap-southeast-1.amazonaws.com/123456789012/approvals-lab",
    "MessageBody": {
      "orderId.$": "$.orderId",
      "taskToken.$": "$$.Task.Token"
    }
  },
  "TimeoutSeconds": 3600,
  "ResultPath": "$.approval",
  "Next": "CheckApproval"
}
~~~

Đây là **fragment Task**, sử dụng integration pattern `.waitForTaskToken` được hỗ trợ cho SQS. Hệ thống ngoài phải lấy token rồi gọi API Step Functions **`SendTaskSuccess`** hoặc **`SendTaskFailure`** với IAM phù hợp. Nếu không có callback trước timeout, Task lỗi và cần nhánh xử lý.

**Bảo mật:** task token là một **capability có quyền hoàn tất task**. Không gửi token vào email công khai, không log nó ở nơi mọi nhân viên có thể đọc, không cho client chưa xác thực tự gọi SendTaskSuccess. Worker phải xác minh kết quả duyệt và lưu audit trước khi callback. Có những ràng buộc về **tài khoản/Region và cách sử dụng token**; kiểm tra tài liệu callback workflow trước khi xây approval cross-account.

### 15.2. Heartbeat so với timeout

Với activity/callback-style task có cơ chế heartbeat:

- `HeartbeatSeconds` đặt khoảng thời gian tối đa giữa các heartbeat `SendTaskHeartbeat`.
- `TimeoutSeconds` giới hạn tổng thời gian Task theo nghĩa tương ứng; heartbeat không phải cách vô hiệu hóa thời hạn tổng.
- Nếu callback đến sau khi token hết hạn hoặc đã được sử dụng, việc hoàn tất có thể thất bại; backend phải nhận diện và xử lý kết quả trễ.
- Task token **không phải idempotency key cho side effect nghiệp vụ**; dùng business ID và trạng thái giao dịch riêng.

### 15.3. Standard vs Express cho callback

Các mẫu **`.sync`** và **`.waitForTaskToken`** thuộc những integration patterns **Standard Workflows** được hỗ trợ, không nên áp dụng nguyên xi cho Express chỉ vì đều dùng ASL. Express thường dùng **request-response** integrations; với công việc dài cần chờ, thiết kế Standard, workflow lồng nhau hoặc event/callback kiến trúc phù hợp.

## 16. Khi nào chọn Standard và Express Workflows?

AWS Step Functions có hai loại workflow với đặc điểm thực thi, quan sát và chi phí khác nhau:

| Tiêu chí | **Standard** | **Express** |
| --- | --- | --- |
| Thời lượng | Workflow chạy dài, thường được dùng cho chờ đợi nhiều giờ/ngày theo giới hạn dịch vụ | Workflow thời lượng ngắn, giới hạn phổ biến **5 phút** |
| Semantics | Workflow orchestration có lịch sử và độ bền theo semantics Standard; chú ý Task retries | Async Express thường at-least-once, sync Express có semantics khác; phải thiết kế idempotency |
| Execution history | Có history trên Step Functions API/Console theo hỗ trợ | Quan sát chủ yếu qua CloudWatch Logs/metrics và cấu hình logging |
| Tích hợp | Request-response; các mẫu `.sync` và callback hỗ trợ theo dịch vụ | Chủ yếu request-response; không giả định hỗ trợ callback/job-run |
| Chi phí chủ đạo | **State transitions** và cấu phần liên quan | **Số execution, thời lượng/tài nguyên** theo mô hình giá |
| Phù hợp | Approval, order saga, batch dài, quy trình cần audit | Event processing ngắn, API orchestration ngắn, traffic lớn |

**Không đồng nhất Standard exactly-once workflow orchestration với exactly-once business side effects.** Ví dụ một Lambda đã ghi DB rồi timeout, Retry có thể gọi Lambda lần nữa. Hệ thống thanh toán, cấp voucher, gửi email và ghi tồn kho vẫn cần **business idempotency**.

### 16.1. Một vài tiêu chí chọn nhanh

- Có bước **chờ người duyệt** đến ngày hôm sau: thường chọn **Standard**.
- Quy trình **xử lý 3 Lambda liên tục** với tải cao, mỗi lần vài giây: cân nhắc **Express** hoặc Standard tùy chi phí/observability.
- Cần **execution history chi tiết** để kiểm toán từng giao dịch: Standard có lợi thế.
- Cần xử lý một loạt ảnh lớn qua **Distributed Map**: đánh giá workflow/Map Run theo hỗ trợ của Standard và chi phí child executions.
- Có **động tác tài chính khó đảo ngược**: xác định transaction semantics và idempotency, không chọn type chỉ vì “exactly once” trong marketing.

## 17. Patterns orchestration: Saga, fan-out/fan-in và async workflow

### 17.1. Saga / compensation

Một giao dịch trải qua Inventory, Payment và Shipping khó thực hiện bằng **một ACID transaction** xuyên mọi hệ thống. Một pattern là **Saga**:

~~~mermaid
flowchart TD
    I["Reserve inventory"] --> P["Charge payment"]
    P --> S["Create shipment"]
    S --> DONE(["Order succeeded"])
    P -->|"Payment failed"| RI["Release inventory reservation"]
    S -->|"Shipment failed"| REF["Refund / void payment"]
    REF --> RI
    RI --> FAILED(["Order failed / needs review"])
~~~

**Compensation không phải rollback tự động của Step Functions**:

- Mỗi Task xác nhận đã thực hiện side effect nào và lưu **business state**.
- Compensating Task phải idempotent (ví dụ hủy reservation hai lần không gây lỗi dữ liệu).
- Khi compensation thất bại, có thể cần retry, DLQ, runbook và can thiệp của người vận hành.
- Một số hành động không thể “undo” hoàn toàn, như email đã gửi hoặc thông báo SMS. Cần thiết kế trạng thái bù trừ đúng nghĩa nghiệp vụ.
- Step Functions execution history không phải database duy nhất lưu giao dịch; hệ thống Order/Payment vẫn cần source of truth và audit.

### 17.2. Fan-out/fan-in

**Parallel** dùng khi các nhánh khác nhau, ví dụ phân tích rủi ro và kiểm tồn kho. **Map** dùng khi lặp cùng logic trên collection các line items hoặc file S3. Sau khi tất cả nhánh/iteration hoàn tất theo policy, một Task tổng hợp kết quả có thể thực hiện **fan-in**.

~~~text
Order input
  → Map: calculate each line item
  → array of item results
  → Task: summarize bill
  → Choice: allow payment?
~~~

Nếu data đầu vào quá lớn, không chuyển mọi kết quả qua JSON execution. Để outputs ở S3/DynamoDB và chuyển **references** cho bước tổng hợp.

### 17.3. Choreography và orchestration

| Mô hình | Cách hoạt động | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| **Choreography** (EventBridge/SNS/SQS) | Dịch vụ tự phản ứng với events | Coupling thời gian thấp, fan-out tốt | Khó thấy toàn bộ tiến trình, business flow phân tán |
| **Orchestration** (Step Functions) | State machine điều phối thứ tự, lỗi, nhánh, chờ | Trực quan, dễ quan sát từng execution, retry/catch rõ | State machine có thể trở thành điểm coupling giữa services |

Hai mô hình **có thể kết hợp**: EventBridge nhận event `OrderPlaced`, khởi động Step Functions execution, rồi workflow publish event `OrderCompleted` hoặc enqueue SQS cho downstream. Không bắt mọi hệ thống vào một workflow khổng lồ nếu ranh giới ownership không phù hợp.

### 17.4. Khi nào không nên dùng Step Functions?

Step Functions không nhất thiết là lựa chọn tốt cho:

- Một HTTP handler rất đơn giản không có nhiều bước/nhánh hoặc yêu cầu workflow bền vững.
- Vòng lặp tính toán CPU nội bộ cực dày ở mức milliseconds per operation, khi hàng loạt state transitions không kinh tế.
- Streaming liên tục với trạng thái mỗi packet; phù hợp Kafka/Kinesis/stream processor hơn.
- Các giao dịch cần atomic commit xuyên database nội bộ và không chấp nhận Saga semantics.

Để chọn dịch vụ, cân nhắc **mục tiêu nghiệp vụ, latency SLO, độ dài workflow, failure semantics và chi phí**.

## 18. IAM, networking và bảo vệ dữ liệu

### 18.1. IAM execution role cho state machine

Step Functions cần một **execution IAM role** với trust phù hợp cho service `states.amazonaws.com`, cùng permissions chính xác để gọi Lambda/SQS/ECS/other integrations.

Ví dụ policy minh họa cho workflow ở mục 14:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeInventoryFunction",
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:check-stock"
    },
    {
      "Sid": "SendOrderNotification",
      "Effect": "Allow",
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:order-events-lab"
    }
  ]
}
~~~

Đây chỉ là **identity policy** minh họa, không phải cấu hình IAM role/trust hoàn chỉnh. Nếu state machine cần `StartExecution` cho nested workflows, `ecs:RunTask`, `iam:PassRole` hoặc KMS permissions, phải xem chính sách chính xác của integration. **Không thêm `AdministratorAccess` chỉ để sửa lỗi “AccessDenied”.**

### 18.2. Caller IAM role khác execution role

- Người/API khởi chạy workflow cần quyền như **`states:StartExecution`** trên state machine ARN phù hợp.
- Step Functions service dùng **state machine execution role** để invoke Lambda, SendMessage, v.v.
- Lambda function có **execution role của Lambda riêng** để truy cập DB, Secrets Manager hoặc các AWS APIs phục vụ nghiệp vụ.
- ECS Task cũng có task role/execution role riêng. Không coi Step Functions role tự cấp quyền bên trong container.

Một người có thể khởi chạy workflow nhưng không cần trực tiếp có quyền gọi `sqs:SendMessage`; Step Functions sẽ thực hiện theo role được cấu hình nếu policy cho phép.

### 18.3. Những chi tiết networking thường bị bỏ quên

Step Functions là dịch vụ điều phối được quản lý, **không phải một EC2 instance tự nằm trong private subnet do bạn chọn**. Task Lambda/ECS có thể cần cấu hình VPC networking khi gọi RDS, PrivateLink hoặc ứng dụng nội bộ. Service integrations sử dụng cơ chế endpoint/IAM tương ứng, không suy luận rằng “state machine ở VPC A” nên truy cập trực tiếp mọi private IP.

Nếu một Lambda ở private subnet cần gọi API Internet, nó có thể cần NAT Gateway hoặc VPC endpoint thích hợp; đó là nhu cầu của **Lambda networking**, không đơn thuần do Task JSON. Tương tự callback worker cần truy cập Step Functions API theo đường mạng/IAM được phép.

### 18.4. Bảo mật input/output và execution history

- Không đưa raw access tokens/credentials hoặc thông tin nhạy cảm không cần thiết vào state input.
- Dùng **Secrets Manager/SSM** theo cơ chế được hỗ trợ, chỉ chuyển secret reference khi phù hợp.
- Bật CloudWatch Logs và kiểm soát **retention/access**, lưu ý cấu hình include execution data có thể chứa input/output nhạy cảm.
- Dùng KMS encryption và quyền truy cập phù hợp theo yêu cầu.
- Giới hạn ai được `DescribeExecution`, `GetExecutionHistory`, `StopExecution`, `UpdateStateMachine` và `StartExecution`.
- Dùng CloudTrail, IAM change review và audit để theo dõi chỉnh sửa definition/role.

Mục tiêu của execution history là giúp điều tra tiến trình, không phải kho lưu vĩnh viễn toàn bộ dữ liệu khách hàng.

## 19. Quan sát state machine và đo hiệu năng

### 19.1. Metrics theo ba lớp

| Lớp | Tín hiệu cần quan sát | Ý nghĩa |
| --- | --- | --- |
| **Workflow** | Executions started/succeeded/failed/timed out/aborted | Tỷ lệ thành công và thời gian xử lý end-to-end |
| **State/task** | Thời gian Task, lỗi Retry/Catch, số transitions | Bước nào làm workflow chậm hoặc đắt |
| **Downstream** | Lambda errors/throttles, SQS age, ECS tasks, RDS latency | Lỗi thật nằm ở service thực hiện |

Step Functions cung cấp **CloudWatch metrics**, console execution views và logging/tracing theo cấu hình và loại workflow. Những tên metric phổ biến gồm `ExecutionsStarted`, `ExecutionsSucceeded`, `ExecutionsFailed`, `ExecutionsTimedOut`, `ExecutionsAborted` và metric throttling theo khả năng. Nhưng **một execution Succeeded không bảo đảm downstream consumer của SQS đã xử lý xong message**.

### 19.2. Gắn business correlation ID

Một state machine nhận:

~~~json
{
  "orderId": "order-101",
  "correlationId": "trace-abc-123",
  "customerId": "customer-42"
}
~~~

Nên chuyển `orderId`/`correlationId` tới Lambda/SQS hoặc application logs theo nhu cầu và chính sách dữ liệu. CloudWatch/X-Ray và application logs có thể cùng dùng ID này để đối chiếu lỗi. **Không tạo workflow chỉ lưu cả payload nhạy cảm vào log**; nên redaction và phân quyền quan sát.

### 19.3. Theo dõi output shape, không chỉ HTTP 200

Các lỗi Step Functions thường đến từ **schema mismatch**:

- Lambda trả `{"approved":true}` nhưng Choice tìm `$.Payload.approved` sau khi ResultSelector đã đổi kết quả sang `$.verification.data.approved`.
- JSONPath tham chiếu field không tồn tại → lỗi xử lý runtime.
- `ResultPath` mặc định thay input → bước sau mất `orderId`.
- SQS sendMessage đã thành công nhưng state sau mong input vẫn giữ nguyên; thiếu `ResultPath`.
- Một branch Parallel trả array/object khác schema mà bước tổng hợp dự kiến.

Trong staging, hãy đưa **expected JSON schema** cho input/output của từng Task, kiểm thử cả success, business rejection và technical failure.

### 19.4. Alarms gắn với SLO

Ví dụ dịch vụ yêu cầu **99% đơn hàng được chấp nhận điều phối trong 2 phút**:

~~~text
Workflow:
  99% executions đạt trạng thái kết thúc hợp lệ < 2 phút

Failure alarm:
  ExecutionsFailed / ExecutionsStarted tăng vượt ngưỡng đã định

Latency alarm:
  End-to-end duration p95/p99 tăng vượt SLO

Downstream alarm:
  Lambda errors/throttles hoặc SQS oldest message age tăng
~~~

Các ngưỡng là ví dụ. Cần phân biệt execution bị **Fail** vì đơn hàng không hợp lệ (business rejection bình thường) với error do Lambda/throttling. Nếu mọi business rejection dùng Fail, metric `ExecutionsFailed` có thể cao dù hạ tầng khỏe; bổ sung business status metric và dashboard riêng.

## 20. AWS CLI: đọc và kiểm tra state machine an toàn

Các lệnh ở đây chủ yếu **chỉ đọc**, trừ khi được ghi chú rõ là validate local definition (không deploy). Thay ARN, account và Region bằng tài nguyên bạn được phép xem. Không chạy `start-execution`, `stop-execution`, `update-state-machine` hoặc `delete-state-machine` vào production ngoài quy trình thay đổi.

### 20.1. Liệt kê state machines

~~~bash
aws stepfunctions list-state-machines \
  --region ap-southeast-1 \
  --query "stateMachines[].{Name:name,Arn:stateMachineArn,Type:type}" \
  --output table
~~~

Tên `stateMachineArn` là định danh đầy đủ, không chỉ tên hiển thị. Dùng ARN đúng Region/account để tránh xem nhầm workflow cùng tên.

### 20.2. Đọc definition, IAM role và workflow type

~~~bash
aws stepfunctions describe-state-machine \
  --region ap-southeast-1 \
  --state-machine-arn arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderWorkflowLab \
  --query "{Name:name,Type:type,Role:roleArn,Definition:definition,Logging:loggingConfiguration}" \
  --output json
~~~

Đối chiếu `StartAt`, `States`, `QueryLanguage`, Task `Resource`, Retry/Catch và IAM role. Đừng sửa thẳng JSON trong Console rồi quên đồng bộ IaC/Git.

### 20.3. Xem executions của Standard state machine

~~~bash
aws stepfunctions list-executions \
  --region ap-southeast-1 \
  --state-machine-arn arn:aws:states:ap-southeast-1:123456789012:stateMachine:OrderWorkflowLab \
  --max-results 20

aws stepfunctions describe-execution \
  --region ap-southeast-1 \
  --execution-arn arn:aws:states:ap-southeast-1:123456789012:execution:OrderWorkflowLab:example-execution-id
~~~

`DescribeExecution` có thể trả input/output cùng trạng thái, thời gian, error/cause tùy execution; những dữ liệu đó cần quyền đọc và bảo vệ tương ứng. Đối với **Express**, cách xem history khác Standard; thường dùng CloudWatch Logs/metrics và cơ chế hỗ trợ dành riêng cho Express thay vì dựa vào `GetExecutionHistory`.

### 20.4. Xem event history của Standard execution

~~~bash
aws stepfunctions get-execution-history \
  --region ap-southeast-1 \
  --execution-arn arn:aws:states:ap-southeast-1:123456789012:execution:OrderWorkflowLab:example-execution-id \
  --max-results 30 \
  --query "events[].{Id:id,Type:type,Timestamp:timestamp,Previous:previousEventId}" \
  --output table
~~~

Tập trung vào các event như **TaskStateEntered**, service integration scheduled/started/succeeded/failed và Retry/Catch transition theo event types thực tế. Để xem root cause, cần đọc event detail tương ứng; không suy ra nguyên nhân chỉ từ một dòng `TaskFailed`.

### 20.5. Validate định nghĩa ASL trước khi deploy

Nếu đã lưu một definition mẫu vào file riêng ở môi trường làm việc được phép, có thể gọi **API validate**:

~~~bash
aws stepfunctions validate-state-machine-definition \
  --region ap-southeast-1 \
  --definition file://order-workflow.asl.json
~~~

Đây là **kiểm tra định nghĩa**, không tạo execution hay sửa state machine. API có thể trả **OK/FAIL và diagnostics** theo phiên bản AWS CLI/Step Functions hỗ trợ. Một definition **valid syntax** vẫn có thể thất bại khi chạy vì Lambda ARN không tồn tại, IAM sai, JSON input không khớp hoặc downstream 503; cần integration tests.

### 20.6. Tại sao không chạy bừa `StartExecution`?

Một state machine có Task gửi email, trừ tồn kho, gọi thanh toán hoặc xóa file. **Bắt đầu execution là hành động thay đổi trạng thái nghiệp vụ và có thể phát sinh tiền**. Khi cần thử nghiệm:

1. Tạo môi trường lab/staging.
2. Dùng Lambda/SQS mock hoặc test account có dữ liệu giả.
3. Chạy với `orderId` và correlation ID không thuộc khách hàng thật.
4. Kiểm tra output/history, cleanup/compensation và chi phí.
5. Chỉ cho phép production execution theo quyền và quy trình đã phê duyệt.

## 21. Xử lý sự cố theo loại lỗi ASL

| Triệu chứng | Khả năng chính | Cách điều tra |
| --- | --- | --- |
| **Validation failed** | `StartAt` trỏ tên không tồn tại; `Next` sai; trường không được hỗ trợ | Validate ASL, kiểm tra state names/QueryLanguage |
| **State chuyển sai nhánh** | Choice rules xét theo thứ tự; thiếu `Default`; type khác dự kiến | So input JSON và choice operators |
| **No Choice matched / execution failed** | Không rule nào match và không có Default | Thêm nhánh fallback có chủ đích |
| **ResultPath overwrite input** | Mặc định result thay input | Đặt `ResultPath` đúng hoặc dùng `null` khi cần |
| **States.Runtime** | JSONPath/JSONata expression tham chiếu dữ liệu sai, sai type | Xem event history, test input/output ở state |
| **States.DataLimitExceeded** | Payload trong workflow vượt giới hạn | Đặt dữ liệu lớn vào S3, truyền reference |
| **Lambda Task access denied** | State machine role thiếu `lambda:InvokeFunction` hoặc policy khác chặn | IAM role, resource ARN, CloudTrail |
| **Task timeout** | Lambda/ECS/worker chạy lâu hoặc callback không đến | `TimeoutSeconds`, downstream logs, token expiry |
| **States.HeartbeatTimeout** | Worker không gửi heartbeat theo chính sách | Kiểm tra health, timeout và callback mode |
| **Retry storm / downstream 429** | Retry quá nhiều, thiếu jitter/giới hạn concurrency | Backoff, `MaxAttempts`, throttles, service quotas |
| **Map execution thất bại ở một item** | Unhandled error, sai schema, threshold failure vượt giới hạn | ItemProcessor events/Map Run, item input, Catch |
| **Parallel Task đã gửi email hai lần** | Retry toàn Parallel chạy lại branch có side effect | Chuyển retry về Task cần thiết, idempotency |
| **$.field không còn sau Lambda** | `ResultPath`/`OutputPath` hoặc `InputPath` xóa field | Truy vết data flow từng state |
| **Callback không tiếp tục execution** | Token sai/hết hạn/khác account hoặc IAM thiếu | Callback worker logs, token lifecycle, SendTaskSuccess status |
| **Workflow thành công nhưng business chưa xong** | SQS enqueue là request-response; downstream xử lý async | Xem queue/consumer, đổi contract hoặc dùng callback |
| **Hóa đơn lớn khi workload tăng** | Nhiều state transitions/Map child executions/retries/logs | Ước lượng cost, giới hạn concurrency, tối ưu workflow |

### 21.1. Quy trình chẩn đoán nhanh

1. **Định nghĩa**: JSON hợp lệ? `StartAt` và mọi `Next`/`Default` tồn tại? QueryLanguage đúng?
2. **Input/output**: event nào vào state, biểu thức đã chọn đúng field chưa, payload quá lớn không?
3. **Integration**: Step Functions role có quyền? ARN/Region/account và backend có chạy?
4. **Retry/Catch**: error code nào, có bị retry quá nhiều hoặc catch nhầm? Có side effect cần idempotency/compensation?
5. **Downstream**: Lambda/DB/SQS/third-party logs, throttling, timeout và giới hạn concurrency.
6. **Recovery**: Có thể redrive execution, retry workflow hoặc bù trừ thủ công an toàn không? Không replay bừa giao dịch tài chính.

### 21.2. Lỗi do sửa definition giữa các executions

Một tổ chức có thể cập nhật state machine khi executions đang chạy. Không nên giả định mọi execution đang chạy tự chuyển sang **definition mới** mà bạn vừa deploy. Quản lý versions/aliases khi tính năng được hỗ trợ, ghi lại **definition version** cho execution và dùng release workflow có review. Nếu cần migrate trạng thái đang chạy, đó là một kế hoạch nghiệp vụ riêng.

## 22. Hiệu năng, concurrency và kiểm soát chi phí

### 22.1. Công thức chi phí định hướng

Với **Standard Workflows**, phí chủ yếu liên quan **số state transitions**. Ví dụ một execution đơn giản đi qua:

~~~text
ValidateOrder (Choice)
  → CheckStock (Task)
  → RouteByStock (Choice)
  → PrepareNotification (Pass)
  → SendNotification (Task)
  → Completed (Succeed)

≈ 6 lượt chuyển trạng thái (mô hình đếm minh họa)
~~~

Nếu một ngày có **20.000 executions**, một ước lượng ban đầu là:

~~~text
20.000 executions/ngày × 6 transitions/execution
  = 120.000 transitions/ngày
~~~

Số lượng thực tế có thể tăng do **Retry, Map/Parallel branches và các chuyển trạng thái khác** theo cách tính phí hiện hành. Phải tra bảng giá AWS và kiểm tra usage metrics để có số tiền chính xác; ở đây không gán đơn giá giả định.

### 22.2. Express và thời lượng

Với **Express**, mô hình tính phí thường dựa trên **số request/execution và tài nguyên-thời lượng**, bên cạnh logs và các dịch vụ tích hợp. Một workflow chờ lâu bằng `Wait` có thể ảnh hưởng chi phí/thời lượng Express theo cách khác Standard. Chọn type theo tổng workload, không chỉ một dòng giá.

### 22.3. Các nguồn chi phí ngoài Step Functions

| Thành phần | Chi phí có thể phát sinh |
| --- | --- |
| **Lambda** | Invocation, duration, memory, concurrency |
| **SQS/SNS/EventBridge** | API requests, payload/throughput, message volume |
| **ECS/Fargate/Batch** | vCPU/RAM/runtime, job attempts |
| **DynamoDB/RDS/S3** | Request/compute/storage, backups và data transfer |
| **CloudWatch/X-Ray** | Log ingestion/retention, metrics, tracing |
| **KMS/Network** | Encryption requests, NAT/VPC endpoints/data transfer khi có |
| **Workflow** | Transitions/Map child runs/retries hoặc Express duration |

**Wait không phải “miễn phí mọi thứ”.** Một workflow chờ approval dài tuy không chạy Lambda liên tục nhưng vẫn chiếm một execution đang mở, chịu thời hạn/quota và có thể làm tăng cost/monitoring tùy loại workflow.

### 22.4. Concurrency và các nút nghẽn

Khi workflow gọi nhiều Tasks cùng lúc:

- `Parallel` tạo fan-out theo số branches.
- `Map MaxConcurrency` hoặc Distributed Map tạo nhiều iterations/child executions.
- `Retry` có thể nhân số lần gọi Lambda/ECS/API.
- Khi downstream trả 429/503, scale workflow lên có thể tạo **retry storm**.

Thiết kế backpressure:

1. Giới hạn concurrency Map phù hợp năng lực DB/API.
2. Đưa công việc dài hoặc không khẩn sang SQS/Batch với queue capacity.
3. Retry với exponential backoff/jitter và MaxAttempts.
4. Chọn DLQ/exception workflow cho poison items.
5. Có CloudWatch alarms về số executions thất bại, duration p99 và downstream saturation.

## 23. Bài tập củng cố

### Bài tập 1 — Chọn state

Một workflow cần (a) gọi Lambda xử lý đơn, (b) rẽ nhánh theo giá trị `approved`, (c) chờ 15 phút, (d) kết thúc thành công.

**Gợi ý:** dùng lần lượt **Task → Choice → Wait → Succeed**. Không tạo bốn Lambda functions chỉ để diễn đạt rẽ nhánh/chờ/kết thúc.

### Bài tập 2 — `Next` và `End`

Một Pass state khai báo cả `"Next":"B"` và `"End":true`.

**Gợi ý:** cấu trúc chuyển trạng thái mâu thuẫn; một state thông thường chọn **Next hoặc End**, không cả hai. Kiểm tra thêm state B có tồn tại.

### Bài tập 3 — Task output làm mất orderId

Input: `{"orderId":"o-1","qty":2}`. Task Lambda optimized integration trả metadata và `Payload`. State sau muốn đọc `$.orderId` nhưng không tìm thấy.

**Gợi ý:** Task mặc định có thể thay input bằng result. Dùng `ResultSelector` để chỉ giữ phần cần và `ResultPath: "$.stock"` để gắn kết quả vào input.

### Bài tập 4 — Choice field có thể thiếu

Bạn viết `"Variable":"$.amount","NumericGreaterThan":0` nhưng input đôi khi thiếu `amount` hoặc là string.

**Gợi ý:** kiểm tra `IsPresent` và `IsNumeric` trong rule phù hợp hoặc chuẩn hóa/validate input trước, rồi có nhánh `Default`.

### Bài tập 5 — Parallel hay Map?

Một workflow cần kiểm tra độc lập Fraud Risk và Inventory. Workflow khác cần tạo thumbnail cho 200 hình trong S3.

**Gợi ý:** Fraud/Inventory là hai loại việc khác nhau → **Parallel**. Thumbnail lặp một xử lý trên nhiều file → **Map**; đánh giá Inline/Distributed theo số item và payload.

### Bài tập 6 — Retry gây double charge

Task gọi payment API đã charge thành công nhưng Step Functions nhận timeout và retry Task, khiến khách hàng bị charge thêm lần nữa.

**Gợi ý:** Task timeout không tự rollback side effect. Dùng payment-level **idempotency key** và nguồn dữ liệu ghi trạng thái bền vững, đối soát kết quả trước khi thực hiện lại; giới hạn Retry và thiết kế compensation.

### Bài tập 7 — SQS Task thành công nghĩa là gì?

Workflow dùng `arn:aws:states:::sqs:sendMessage`, sau đó Succeed. Email worker không hoạt động nên khách chưa nhận email.

**Gợi ý:** SQS sendMessage chỉ xác nhận **enqueue**, không xác nhận consumer gửi email thành công. Đổi business contract thành `ACCEPTED_FOR_PROCESSING`, hoặc dùng callback/event bổ sung khi cần chờ kết quả thật.

### Bài tập 8 — JSONPath hay JSONata?

Bạn muốn tính `gross = unitPrice × quantity` ngay trong state không gọi Lambda, và muốn trả output mới chứa `orderId`, `gross`.

**Gợi ý:** một **Pass state JSONata** với `Output` và expression `{% $states.input.unitPrice * $states.input.quantity %}` phù hợp; với JSONPath cũng có thể cân nhắc intrinsics theo phép biến đổi được hỗ trợ, nhưng không trộn syntax.

### Bài tập 9 — Chờ phê duyệt ba ngày

Nhân sự có thể phê duyệt một yêu cầu trong vòng ba ngày và backend cần tiếp tục đúng execution sau callback.

**Gợi ý:** đánh giá **Standard Workflow + waitForTaskToken** thay vì Express ngắn hạn; bảo vệ task token, đặt timeout/heartbeat phù hợp và có nhánh quá hạn.

### Bài tập 10 — Map xử lý nhiều phần tử

Map chạy 1.000 iterations, mỗi iteration gọi một database cho phép tối đa 30 kết nối đồng thời. Bạn định `MaxConcurrency=1000`.

**Gợi ý:** không phù hợp; giới hạn concurrency theo downstream throughput/connection pool và quota Step Functions/Lambda. Nếu dữ liệu lớn, đánh giá Distributed Map và S3, nhưng vẫn cần backpressure.

### Bài tập 11 — Catch ALL không xử lý được mọi thứ

Một Task có `Catch ErrorEquals=["States.ALL"]` nhưng execution vẫn fail vì `States.DataLimitExceeded`.

**Gợi ý:** `States.ALL` không catch mọi terminal error. Giảm payload, chuyển dữ liệu sang S3, sửa schema/definition; không thể giải quyết mọi failure chỉ bằng một Catch.

### Bài tập 12 — Chọn workflow type

Một nhóm cần orchestrate một luồng API gồm hai Lambda dưới 3 giây, lưu lượng hàng triệu execution/ngày. Nhóm khác có approval kéo dài vài ngày.

**Gợi ý:** nhóm đầu **đánh giá Express** theo yêu cầu delivery/cost/observability; nhóm sau thường dùng **Standard** cho thời lượng dài và callback. Cần benchmark và kiểm tra quotas/các integration patterns thực tế.

## 24. Checklist triển khai production

- [ ] Có workflow business diagram, xác định input/output schema và mục tiêu thành công/thất bại rõ ràng.
- [ ] ASL đã validate; `StartAt`, tên states, `Next`/`End`/`Default` và branches được khai báo hợp lệ.
- [ ] Mọi state dùng đúng syntax **JSONPath hoặc JSONata**, không trộn trường không tương thích.
- [ ] Task `Resource`/`Parameters`/`Arguments` khớp service integration và IAM role.
- [ ] `ResultPath`/`Output` giữ lại dữ liệu cần thiết; không làm mất business ID sau Lambda.
- [ ] Choice rules kiểm tra kiểu/null/field thiếu và có Default fallback.
- [ ] Task timeout và Retry/Catch phân biệt transient error, permanent error và business rejection.
- [ ] Side effects nhạy cảm có idempotency/outbox; compensation có audit và kế hoạch thất bại.
- [ ] Map/Parallel concurrency phù hợp downstream; không retry toàn nhánh tạo duplicate side effects.
- [ ] Workflow type Standard/Express, duration, callback support và pricing đã được so sánh.
- [ ] Payload lớn chuyển qua S3 hoặc datastore; input/output/logs không chứa secrets không cần thiết.
- [ ] Có CloudWatch alerts, logs, traces/correlation IDs và workflow execution metrics.
- [ ] Roles được giới hạn theo Lambda/SQS/ECS/Service ARN, caller permissions tách execution role.
- [ ] Có test cho success, business rejection, IAM error, timeout, throttling, Map item failure và compensation.
- [ ] Quản lý definition bằng IaC/Git, versions/aliases và quy trình rollout/rollback phù hợp.
- [ ] Đã tính đến state transitions, retries, Map child executions, Lambda/ECS/SQS và logs trong ngân sách.

## 25. Ghi nhớ

**Amazon States Language** là ngôn ngữ khai báo **workflow state machine** của AWS Step Functions:

1. **`StartAt`** chọn state bắt đầu, **`States`** định nghĩa các state. Từng state xác định hướng đi bằng **`Next`, `End` hoặc logic riêng** của loại state.
2. Có **tám loại state**: **Task, Pass, Choice, Wait, Succeed, Fail, Parallel, Map**. Chọn đúng loại giảm việc viết Lambda không cần thiết.
3. **JSONPath** dùng InputPath/Parameters/ResultSelector/ResultPath/OutputPath; **JSONata** dùng các trường/biểu thức phù hợp như Arguments/Assign/Output/Condition. Không nhầm cú pháp.
4. **Retry/Catch** hỗ trợ khôi phục lỗi kỹ thuật, nhưng **không tự rollback side effects**. Idempotency và compensation là trách nhiệm thiết kế ứng dụng.
5. **Parallel/Map** giúp fan-out, nhưng phải kiểm soát concurrency, payload, dữ liệu nhất quán và lỗi từng nhánh/iteration.
6. **Standard/Express** khác nhau về thời lượng, execution semantics, tích hợp và chi phí; chọn theo SLO và nhu cầu audit.
7. **Step Functions điều phối, không thay thế business source of truth**. Database, queues, IAM, logging và hệ thống downstream phải được thiết kế cùng workflow.

### Tài liệu AWS chính thức

- [What is AWS Step Functions?](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) — dịch vụ và khái niệm.
- [Amazon States Language specification](https://states-language.net/spec.html) — định nghĩa ngôn ngữ, syntax, states, data flow và errors.
- [State types in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-states.html) — Task, Pass, Choice, Wait, Succeed, Fail, Parallel, Map.
- [Using JSONPath paths in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/amazon-states-language-paths.html) — JSONPath và data selection.
- [Processing input and output in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-input-output-filtering.html) — InputPath, Parameters, ResultSelector, ResultPath, OutputPath.
- [Transforming data with JSONata](https://docs.aws.amazon.com/step-functions/latest/dg/transforming-data.html) — JSONata, Arguments/Assign/Output.
- [State machine context object](https://docs.aws.amazon.com/step-functions/latest/dg/input-output-contextobject.html) — `$$` và `$states.context`.
- [Error handling in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html) — Retry, Catch, timeout và error names.
- [Integrating services with Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/integrate-services.html) — request-response, `.sync`, task tokens.
- [Lambda integration in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-lambda.html) — optimized Lambda Task.
- [SQS integration in Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-sqs.html) — SendMessage và callback pattern.
- [Map state processing modes](https://docs.aws.amazon.com/step-functions/latest/dg/state-map.html) — Inline/Distributed Map và concurrency.
- [Standard vs Express Workflows](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html) — thời lượng, semantics và quan sát.
- [Validating state machine definitions](https://docs.aws.amazon.com/step-functions/latest/apireference/API_ValidateStateMachineDefinition.html) — kiểm tra cú pháp/diagnostics.
- [AWS Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) — state transitions, executions và các chi phí liên quan.
