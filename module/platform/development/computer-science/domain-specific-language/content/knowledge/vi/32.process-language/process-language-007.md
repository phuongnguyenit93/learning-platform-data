# Timeout

## 1. Timeout trong DSL quy trình là gì?

Timeout là giới hạn thời gian cho phép một hoạt động hoặc toàn bộ quy trình tiếp tục thực thi trước khi hệ thống kết thúc, hủy hoặc chuyển trạng thái xử lý. Trong DSL quy trình, timeout giúp bảo đảm một workflow không chờ vô hạn khi service bên ngoài không phản hồi, worker bị treo, queue bị nghẽn hoặc một bước không thể hoàn thành.

Ví dụ:

~~~text
workflow approveOrder {
    timeout 10 minutes

    step validate {
        call orderService.validate(orderId)
        timeout 5 seconds
    }

    step requestApproval {
        call approvalService.request(orderId)
        timeout 30 seconds
    }
}
~~~

Ở đây workflow có thời gian tối đa 10 phút, còn mỗi bước có giới hạn riêng. Nếu bước validate mất hơn 5 giây, engine phải áp dụng chính sách timeout của bước đó. Nếu workflow chạm deadline tổng, các bước chưa hoàn thành cũng phải được xử lý theo quy tắc đã định nghĩa.

Timeout là một phần của semantics thực thi, không chỉ là một tham số cấu hình kỹ thuật. Nó ảnh hưởng tới trạng thái workflow, retry, cancellation, compensation, thông báo lỗi và tính nhất quán của dữ liệu.

## 2. Vì sao workflow cần timeout?

Workflow thường điều phối nhiều hoạt động có thời gian hoàn thành khác nhau:

- Gọi API hoặc microservice.
- Đọc hoặc ghi database.
- Chờ message từ queue.
- Chờ người dùng phê duyệt.
- Chạy tác vụ nền hoặc batch job.
- Chờ một event từ hệ thống bên ngoài.
- Thực hiện bước tính toán hoặc xử lý file.

Nếu không có timeout, một bước có thể chờ mãi. Điều đó có thể giữ worker, connection, lock hoặc tài nguyên khác; làm workflow không bao giờ kết thúc; và khiến các bước phía sau không được thực hiện.

Timeout giúp:

1. Giới hạn thời gian chiếm dụng tài nguyên.
2. Ngăn workflow bị mắc kẹt vô thời hạn.
3. Tạo giới hạn rõ cho trải nghiệm người dùng và SLA.
4. Phát hiện service chậm hoặc không khả dụng.
5. Cho phép retry hoặc chuyển sang nhánh xử lý lỗi.
6. Bảo vệ hệ thống khỏi hàng đợi tác vụ tồn đọng.
7. Giúp lập kế hoạch deadline cho các bước phụ thuộc.
8. Cung cấp tín hiệu quan sát và cảnh báo vận hành.

Timeout không bảo đảm một hoạt động đã dừng ở hệ thống bên ngoài. Nó chỉ cho biết caller không còn chờ kết quả sau một thời điểm. Nếu request đã tới service đích, service đó vẫn có thể tiếp tục xử lý trừ khi có cơ chế cancellation hoặc idempotency riêng.

## 3. Timeout, deadline và duration

Ba khái niệm cần được phân biệt:

- **Timeout:** khoảng thời gian tối đa một hoạt động được phép chờ hoặc chạy.
- **Deadline:** thời điểm tuyệt đối mà hoạt động phải hoàn thành hoặc bị coi là hết hạn.
- **Duration:** khoảng thời gian được đo hoặc cấu hình, ví dụ 5 giây.

Ví dụ, một workflow bắt đầu lúc 09:00 và có timeout 10 phút thì deadline là 09:10. Nếu bước thứ hai bắt đầu lúc 09:08, nó chỉ còn khoảng 2 phút theo deadline workflow, kể cả khi timeout riêng của bước là 5 phút.

Deadline thường phù hợp hơn khi nhiều bước nối tiếp nhau vì nó giới hạn tổng thời gian của cả chuỗi. Nếu mỗi bước chỉ có timeout riêng và mỗi lần retry lại được cấp lại toàn bộ thời gian, tổng thời gian workflow có thể vượt xa dự kiến.

### 3.1. Relative timeout

Relative timeout được tính từ thời điểm một hoạt động bắt đầu:

~~~text
step callPayment {
    timeout 3 seconds
}
~~~

Mỗi lần bước bắt đầu, engine tạo mốc hết hạn mới theo chính sách của bước. Nếu bước được retry, cần xác định timeout được cấp lại cho từng attempt hay được tính trong một budget tổng.

### 3.2. Absolute deadline

Absolute deadline là thời điểm cụ thể:

~~~text
workflow processClaim {
    deadline claim.expiresAt
}
~~~

Deadline có thể đến từ yêu cầu nghiệp vụ, chẳng hạn hồ sơ phải được xử lý trước ngày hết hạn. Engine cần kiểm tra giá trị deadline hợp lệ và xác định timezone nếu deadline được biểu diễn bằng thời gian lịch.

### 3.3. Monotonic clock và wall clock

Đo elapsed time nên dùng monotonic clock vì đồng hồ hệ thống có thể được đồng bộ hoặc điều chỉnh. Wall clock phù hợp để biểu diễn thời điểm lịch và deadline được lưu bền vững. Engine có thể chuyển deadline wall-clock thành thời lượng còn lại bằng monotonic clock trong lúc process đang chạy.

Không nên dùng phép trừ hai timestamp wall-clock làm cơ chế duy nhất để đo timeout trong một tác vụ dài nếu hệ thống có thể thay đổi giờ.

## 4. Các phạm vi timeout

Một workflow có thể có nhiều lớp timeout:

| Phạm vi | Áp dụng cho | Ví dụ |
|---|---|---|
| Workflow timeout | Toàn bộ instance workflow | Quy trình xử lý đơn tối đa 10 phút |
| Stage timeout | Một nhóm bước hoặc phase | Giai đoạn xác minh tối đa 2 phút |
| Step timeout | Một bước logic | Validate đơn hàng tối đa 5 giây |
| Task timeout | Một task hoặc worker execution | Tác vụ tính phí tối đa 30 giây |
| Attempt timeout | Một lần thực hiện trước retry | Mỗi lần gọi API tối đa 3 giây |
| Queue timeout | Thời gian chờ được worker nhận | Không chờ queue quá 1 phút |
| Connection timeout | Thời gian thiết lập kết nối | Mở kết nối tới service tối đa 2 giây |
| Read/write timeout | Thời gian chờ thao tác I/O | Đọc response tối đa 5 giây |
| Human task timeout | Thời gian chờ người dùng phản hồi | Chờ phê duyệt tối đa 2 ngày |

Các phạm vi này không thay thế lẫn nhau. Một HTTP request có thể có connection timeout và read timeout, trong khi step gọi HTTP đó có một timeout tổng và workflow có deadline lớn hơn.

## 5. Kế thừa và ghi đè timeout

DSL cần định nghĩa timeout được kế thừa từ scope cha như thế nào. Một mô hình phổ biến:

1. Workflow đặt deadline hoặc timeout tổng.
2. Stage có thể đặt giới hạn nhỏ hơn cho nhóm bước.
3. Step có thể đặt timeout riêng.
4. Connector có timeout kỹ thuật cho connection và I/O.
5. Effective deadline của một hoạt động là giới hạn sớm nhất trong các deadline đang áp dụng.

Ví dụ:

~~~text
workflow onboarding {
    timeout 15 minutes

    stage identityCheck {
        timeout 3 minutes

        step verifyDocument {
            call documentService.verify()
            timeout 20 seconds
        }
    }
}
~~~

Nếu bước verifyDocument bắt đầu sau 2 phút 50 giây kể từ khi stage bắt đầu, nó chỉ còn 10 giây theo deadline stage, dù timeout riêng của bước là 20 giây.

Một công thức khái niệm:

~~~text
effectiveDeadline =
    min(
        workflowDeadline,
        stageDeadline,
        stepDeadline,
        attemptDeadline
    )
~~~

Engine phải định nghĩa rõ timeout tương đối được chuyển thành deadline tại thời điểm nào. Không nên để mỗi connector tự tính lại timeout độc lập rồi vô tình vượt deadline tổng.

### 5.1. Có cho phép tăng timeout ở scope con không?

Thông thường, scope con không nên kéo dài deadline của scope cha. Nếu workflow còn 10 giây, một step không thể tự cấp thêm 1 phút mà vẫn bảo đảm workflow timeout. Có thể cho phép cấu hình timeout riêng lớn hơn deadline cha, nhưng effective deadline vẫn là deadline cha.

### 5.2. Giá trị mặc định

Nếu không khai báo timeout, engine cần có policy mặc định:

- Dùng default theo loại connector.
- Dùng default theo workflow runtime.
- Yêu cầu khai báo với thao tác có nguy cơ chờ lâu.
- Dùng deadline của workflow nếu đã có.

Giá trị mặc định nên được tài liệu hóa và có thể quan sát. Timeout ngầm định quá lớn có thể che giấu lỗi; timeout quá nhỏ có thể gây thất bại giả khi hệ thống tải cao.

## 6. Đơn vị và cú pháp thời lượng

DSL nên dùng đơn vị rõ ràng để tránh nhầm giữa mili giây, giây và phút.

Ví dụ:

~~~text
timeout 500 milliseconds
timeout 5 seconds
timeout 2 minutes
timeout 1 hour
~~~

Có thể hỗ trợ dạng rút gọn như 500ms, 5s, 2m hoặc 1h nếu grammar quy định rõ. Nên tránh số không có đơn vị vì 500 có thể được hiểu là milliseconds hoặc seconds tùy implementation.

### 6.1. Kiểm tra giá trị

Các giá trị thường cần bị từ chối:

- Duration âm.
- Duration không hợp lệ hoặc tràn số.
- Giá trị bằng 0 nếu runtime không định nghĩa rõ zero-timeout.
- Giá trị vượt giới hạn nền tảng.
- Deadline không thể chuyển đổi do timezone hoặc định dạng sai.

Zero-timeout có thể có nghĩa là hết hạn ngay, không chờ, hoặc dùng default trong một số API. DSL nên chọn một semantics duy nhất và không để zero mang nghĩa mơ hồ.

### 6.2. Precision

Nếu engine chỉ hỗ trợ độ chính xác milliseconds, khai báo microseconds cần được làm tròn hoặc từ chối theo quy tắc công bố. Việc làm tròn nên tránh vô tình kéo dài giới hạn vượt deadline.

## 7. Timeout của workflow và trạng thái instance

Khi workflow chạm deadline, engine cần chuyển instance sang trạng thái đã định nghĩa. Các trạng thái có thể gồm:

- Running.
- Waiting.
- TimedOut.
- Cancelling.
- Cancelled.
- Failed.
- Compensating.
- Compensated.
- Completed.

Không phải workflow nào cũng cần mọi trạng thái. Quan trọng là phân biệt timeout với lỗi nghiệp vụ, cancellation do người dùng và lỗi hệ thống.

Ví dụ:

~~~text
workflow payment {
    timeout 2 minutes

    on timeout {
        cancel pending steps
        emit PaymentTimedOut
        mark status TIMED_OUT
    }
}
~~~

Một workflow timeout không nhất thiết có nghĩa mọi side effect đã được đảo ngược. Nếu bước charge card đã hoàn tất ở payment provider nhưng response bị trễ, engine có thể không biết giao dịch đã thành công hay chưa. Cần cơ chế tra cứu trạng thái, idempotency hoặc compensation.

## 8. Timeout của step và task

Step timeout giới hạn một đơn vị logic trong workflow. Step có thể gọi một function, gửi message, thực thi query hoặc chờ một kết quả.

~~~text
step reserveInventory {
    call inventory.reserve(orderId)
    timeout 4 seconds
}
~~~

Nếu step không hoàn tất trong 4 giây, engine chuyển nó sang nhánh timeout hoặc trạng thái lỗi theo cấu hình.

Task timeout có thể được áp dụng ở worker khi một task được giao cho process hoặc máy khác. Engine cần theo dõi thời gian từ lúc task được nhận hoặc bắt đầu, và phân biệt thời gian chờ queue với thời gian xử lý.

Nếu chỉ tính thời gian xử lý sau khi worker nhận task, một task có thể chờ queue rất lâu mà không bị timeout. Vì vậy, queue timeout và execution timeout thường cần được cấu hình riêng.

## 9. Connection, request và I/O timeout

Một bước gọi service thường bao gồm nhiều giai đoạn:

1. Chờ connection pool cấp connection.
2. Thiết lập kết nối mạng.
3. Gửi request.
4. Chờ response headers.
5. Đọc response body.
6. Parse và xử lý kết quả.

Mỗi giai đoạn có thể có giới hạn riêng:

| Timeout | Ý nghĩa |
|---|---|
| Pool acquisition timeout | Chờ connection khả dụng |
| Connect timeout | Thiết lập kết nối |
| TLS handshake timeout | Hoàn tất bắt tay bảo mật |
| Request/write timeout | Gửi request |
| Response/read timeout | Chờ hoặc đọc response |
| Overall request timeout | Tổng thời gian cho request |

Ví dụ:

~~~text
connector paymentApi {
    connectTimeout 2 seconds
    readTimeout 5 seconds
    requestTimeout 8 seconds
}
~~~

Request timeout tổng nên không nhỏ hơn các giai đoạn một cách vô lý. Nếu connection timeout là 2 giây, read timeout 5 giây và tổng request timeout 4 giây, deadline tổng có thể kết thúc trước khi read timeout có ý nghĩa.

## 10. Queue timeout và thời gian chờ worker

Trong hệ thống bất đồng bộ, task có thể được tạo và đưa vào queue trước khi worker xử lý. Cần phân biệt:

- Queue wait time: thời gian task chờ worker.
- Execution time: thời gian worker thực hiện.
- End-to-end time: từ lúc workflow phát sinh task tới khi nhận kết quả.

Ví dụ:

~~~text
step generateReport {
    dispatch reportWorker
    queueTimeout 1 minute
    executionTimeout 5 minutes
}
~~~

Nếu không có worker nhận task trong 1 phút, bước có thể thất bại do queue timeout. Nếu worker nhận task nhưng xử lý quá 5 phút, đó là execution timeout.

Queue timeout giúp phát hiện thiếu capacity hoặc worker không hoạt động. Nó cũng giúp tránh task cũ được thực thi sau khi workflow đã hết hạn.

Khi worker nhận task, cần kiểm tra deadline còn hiệu lực trước khi bắt đầu side effect. Message cũ có thể vẫn còn trong queue sau khi workflow đã bị timeout.

## 11. Human task và event timeout

Workflow có thể chờ người dùng hoặc một event bên ngoài trong thời gian dài:

~~~text
step waitForApproval {
    wait for event ApprovalReceived
    timeout 2 days
}
~~~

Khi hết hạn, engine có thể:

- Chuyển sang nhánh escalation.
- Gửi nhắc nhở trước khi timeout.
- Đóng yêu cầu phê duyệt.
- Đánh dấu workflow expired.
- Chuyển công việc cho người khác.

Ví dụ:

~~~text
step managerApproval {
    wait for approval
    timeout 24 hours

    on timeout {
        notify escalationTeam
        route to backupApprover
    }
}
~~~

Human task timeout thường là deadline nghiệp vụ, không phải timeout network. Nó có thể cần lịch làm việc, ngày nghỉ, timezone và business calendar. Ví dụ 2 ngày làm việc khác với 48 giờ liên tục.

DSL nên phân biệt elapsed duration với business duration:

~~~text
timeout 48 hours
timeout 2 business days
~~~

Business calendar cần xác định timezone, ngày nghỉ và khung giờ làm việc. Nếu không, kết quả có thể khác giữa môi trường.

## 12. Timeout propagation

Khi một workflow gọi service A, rồi service A gọi service B, deadline cần được truyền xuống để toàn bộ chuỗi không vượt quá giới hạn tổng.

Ví dụ:

~~~text
workflow checkout {
    timeout 10 seconds

    step authorizePayment {
        call paymentService.authorize()
    }
}
~~~

Nếu paymentService còn 3 giây trước deadline, request tiếp theo tới bank gateway không nên được cấp lại 10 giây. Nó chỉ nên nhận phần thời gian còn lại hoặc một giới hạn nhỏ hơn.

Một mô hình:

~~~text
remaining = deadline - monotonicNow()

childTimeout = min(
    configuredChildTimeout,
    remaining
)
~~~

Deadline có thể được truyền qua RPC metadata hoặc request context. Nếu chuyển qua hệ thống khác, cần định dạng và cơ chế xác thực phù hợp để caller không thể tùy ý kéo dài thời gian bằng cách sửa deadline.

### 12.1. Budget theo chuỗi gọi

Giả sử workflow có deadline 8 giây:

| Hoạt động | Thời gian dự kiến |
|---|---:|
| Validate order | 1 giây |
| Authorize payment | 3 giây |
| Reserve inventory | 2 giây |
| Persist result | 1 giây |
| Dự phòng | 1 giây |

Nếu validate mất 2 giây, các bước sau chỉ còn tổng cộng 6 giây. Deadline propagation giúp các service nhận biết budget thực tế thay vì dùng timeout mặc định độc lập.

### 12.2. Không đặt timeout của child lớn hơn budget còn lại

Một child có thể được cấu hình timeout 30 giây nhưng parent chỉ còn 4 giây. Effective timeout phải bị giới hạn bởi parent deadline. Nếu không, workflow có thể báo timeout trong khi child vẫn tiếp tục chạy và tạo side effect sau khi parent đã kết thúc.

## 13. Cancellation khi timeout

Khi timeout xảy ra, engine thường cần yêu cầu hủy hoạt động đang chạy. Cancellation có thể là:

- Cooperative cancellation: task kiểm tra cancellation token và tự dừng.
- Interrupt: runtime gửi interrupt hoặc tín hiệu tới worker.
- Transport cancellation: đóng request hoặc hủy RPC.
- Process termination: kết thúc process bị treo nếu có cơ chế cô lập.
- Logical cancellation: đánh dấu kết quả không còn được chấp nhận dù hoạt động bên ngoài có thể vẫn chạy.

Ví dụ pseudocode:

~~~text
token = cancellationToken()

start task(token)

when deadline reached:
    token.cancel()
    wait cancellationGracePeriod
    mark task timed out
~~~

### 13.1. Cancellation không đồng nghĩa rollback

Hủy một request không tự động hoàn tác side effect đã xảy ra. Nếu payment provider đã ghi nhận giao dịch, đóng kết nối không làm giao dịch biến mất.

Workflow cần biết hoạt động nào:

- Có thể hủy an toàn.
- Có thể dừng nhưng cần cleanup.
- Không thể hủy sau khi đã commit.
- Cần compensation hoặc reconciliation.

### 13.2. Grace period

Một số task cần thời gian ngắn để giải phóng tài nguyên sau cancellation. Engine có thể cho grace period:

~~~text
on timeout {
    cancel active task
    wait cancellationGrace 2 seconds
    finalize as TIMED_OUT
}
~~~

Grace period phải có giới hạn. Nếu chờ cleanup vô hạn, timeout lại không còn bảo vệ được workflow.

## 14. Timeout và retry

Timeout thường kích hoạt retry, nhưng không phải mọi timeout đều có thể retry an toàn.

Ví dụ:

~~~text
step callInventory {
    call inventory.reserve(orderId)
    timeout 3 seconds

    retry {
        maxAttempts 3
        backoff exponential
    }
}
~~~

Trước khi retry, engine cần xác định:

- Timeout có phải lỗi tạm thời không?
- Request trước có thể đã thành công nhưng response bị mất không?
- Thao tác có idempotent không?
- Còn đủ thời gian trong workflow deadline không?
- Có retry budget và giới hạn tải không?

### 14.1. Attempt timeout và overall retry budget

Giả sử mỗi attempt tối đa 3 giây, có 3 lần thử và backoff 1 giây rồi 2 giây. Tổng thời gian có thể lên tới 12 giây hoặc hơn nếu tính scheduling overhead.

Nếu workflow chỉ còn 5 giây, engine không nên bắt đầu một attempt mà không thể hoàn thành trong budget còn lại.

Một mô hình:

~~~text
retryPolicy:
  attemptTimeout: 3 seconds
  maxAttempts: 3
  maxElapsedTime: 8 seconds
  backoff: exponential
~~~

maxElapsedTime giới hạn tổng thời gian của cả chuỗi retry. Nó cần được kết hợp với deadline của parent.

### 14.2. Backoff và jitter

Exponential backoff tăng khoảng chờ sau mỗi lần thất bại. Jitter thêm biến thiên ngẫu nhiên để nhiều worker không đồng loạt retry cùng lúc.

Ví dụ:

~~~text
delay(attempt) =
    random(0, min(maxDelay, baseDelay * 2^attempt))
~~~

Jitter giúp giảm retry storm khi một service vừa phục hồi. Tổng thời gian backoff vẫn phải nằm trong retry budget.

### 14.3. Phân loại lỗi

Không nên retry mọi timeout hoặc mọi exception:

- Connect timeout có thể retry nếu service chưa nhận request.
- Read timeout có thể không rõ request đã được xử lý hay chưa.
- Validation error thường không retry.
- Authorization denied không nên retry liên tục.
- Rate limit có thể retry theo thời gian server yêu cầu.
- Deadline exceeded của workflow thường không còn budget để retry.

Error classification nên được định nghĩa trong connector hoặc activity contract.

## 15. Idempotency và side effect

Một timeout xảy ra sau khi request được gửi nhưng trước khi response nhận về tạo ra trạng thái không chắc chắn. Caller không biết thao tác đã thành công hay chưa.

Ví dụ:

1. Workflow gửi yêu cầu charge payment.
2. Payment service xử lý và ghi nhận charge.
3. Response bị trễ hoặc mất.
4. Workflow timeout.
5. Workflow retry và gửi charge lần nữa.

Nếu không có idempotency, khách hàng có thể bị charge hai lần.

Có thể dùng idempotency key:

~~~text
call payment.charge(
    orderId,
    amount,
    idempotencyKey = workflow.id + ":charge"
)
~~~

Service đích lưu kết quả theo key và trả lại kết quả cũ nếu cùng thao tác được gửi lại. Key phải ổn định giữa các retry của cùng một logical operation nhưng khác nhau giữa hai operation độc lập.

Idempotency không thay thế timeout; nó làm cho retry sau timeout an toàn hơn.

## 16. Compensation và saga

Workflow dài có thể gồm nhiều bước đã tạo side effect. Nếu bước sau timeout, engine có thể cần compensation để đưa hệ thống về trạng thái nghiệp vụ chấp nhận được.

Ví dụ:

~~~text
workflow placeOrder {
    step reserveInventory {
        call inventory.reserve(orderId)
        compensate inventory.release(orderId)
    }

    step chargePayment {
        call payment.charge(orderId)
        compensate payment.refund(orderId)
        timeout 10 seconds
    }

    step confirmOrder {
        call order.confirm(orderId)
    }
}
~~~

Nếu chargePayment timeout, engine cần biết payment có thực sự được charge hay không trước khi gọi refund. Có thể tra cứu trạng thái bằng idempotency key hoặc transaction reference.

Compensation không phải rollback database tự động. Nó là hành động nghiệp vụ ngược hoặc bù trừ, có thể thất bại và cần retry riêng.

Timeout policy nên xác định:

- Có chạy compensation không?
- Thứ tự compensation là gì?
- Compensation có deadline riêng không?
- Nếu compensation timeout thì trạng thái workflow là gì?
- Có cần chuyển sang manual recovery không?

## 17. Timeout trong parallel và branch

Workflow có thể chạy nhiều nhánh song song:

~~~text
parallel {
    branch checkCredit {
        call creditService.check(customerId)
        timeout 4 seconds
    }

    branch checkFraud {
        call fraudService.score(orderId)
        timeout 6 seconds
    }
}
timeout 8 seconds
~~~

Engine cần xác định cách xử lý khi một nhánh timeout:

- Fail-fast: hủy các nhánh còn lại.
- Wait-all: chờ nhánh khác hoàn tất trong deadline.
- Continue-on-error: ghi nhận lỗi của nhánh và tiếp tục.
- Quorum: tiếp tục khi đủ số nhánh thành công.

### 17.1. Timeout của parallel group

Parallel group có deadline riêng hoặc dùng deadline workflow. Nếu một nhánh chậm, các nhánh khác có thể đã hoàn tất. Khi group timeout, không nên giả định mọi nhánh đều ở cùng trạng thái.

### 17.2. Race và first-completed

Một workflow có thể chờ nhánh đầu tiên hoàn thành:

~~~text
race {
    branch primaryProvider {
        call providerA.lookup()
    }
    branch backupProvider {
        call providerB.lookup()
    }
}
timeout 5 seconds
~~~

Khi một nhánh thắng, engine có thể hủy nhánh còn lại. Nhưng nhánh thua có thể đã tạo side effect; cần cancellation và idempotency phù hợp.

## 18. Timeout trong loop và polling

Workflow có thể lặp cho tới khi điều kiện đạt:

~~~text
repeat until payment.status == SETTLED {
    wait 2 seconds
    refresh payment.status
    timeout 1 minute
}
~~~

Loop cần có giới hạn thời gian hoặc số lần lặp để tránh chạy vô hạn. Có thể kết hợp:

- Overall loop timeout.
- Maximum iterations.
- Poll interval.
- Per-poll request timeout.
- Backoff khi lỗi tạm thời.

Nếu poll interval dài hơn thời gian còn lại, engine nên kết thúc theo deadline thay vì chờ thêm một chu kỳ không thể hoàn tất.

Polling dày có thể gây tải lớn. Event-driven wait hoặc subscription có thể hiệu quả hơn khi hệ thống hỗ trợ.

## 19. Timeout và event/message correlation

Khi workflow chờ message, cần correlation ID để xác định message thuộc instance nào. Timeout của wait state phải được phối hợp với việc nhận message trễ.

Ví dụ:

~~~text
step waitForShipment {
    wait for ShipmentDispatched
    where event.orderId == orderId
    timeout 3 days
}
~~~

Nếu event đến sau deadline, engine cần quy định:

- Bỏ qua event.
- Đưa vào dead-letter hoặc late-event queue.
- Ghi nhận nhưng không mở lại workflow.
- Chuyển sang quy trình xử lý muộn.

Message đến trễ không nên tự động làm sống lại workflow đã kết thúc nếu không có semantics reopen rõ ràng.

### 19.1. Timer persistence

Workflow engine bền vững cần lưu timer hoặc deadline để tiếp tục sau khi process restart. Không nên chỉ dùng timer trong bộ nhớ mà không có state durable nếu workflow có thể tồn tại lâu.

Khi khôi phục, engine tính thời gian còn lại từ deadline đã lưu. Cần xử lý clock skew và downtime theo chính sách đã định nghĩa.

## 20. Timeout và transaction

Timeout trong transaction cần đặc biệt cẩn thận:

- Transaction timeout giới hạn thời gian transaction giữ lock hoặc tài nguyên.
- Statement timeout giới hạn một câu lệnh.
- Connection timeout giới hạn việc lấy hoặc mở kết nối.
- Workflow timeout giới hạn toàn bộ quy trình.

Nếu một statement timeout, database có thể rollback statement hoặc transaction tùy engine và isolation mode. Workflow cần biết trạng thái commit có chắc chắn hay không.

Một response timeout khi commit có thể tạo trạng thái không xác định: database có thể đã commit nhưng client chưa nhận được ACK. Cần transaction ID, idempotency hoặc trạng thái có thể tra cứu.

Không nên giữ một database transaction mở trong lúc workflow chờ người dùng nhiều giờ hoặc nhiều ngày. Với quy trình dài, dùng transaction ngắn theo từng bước và saga/compensation nếu cần.

## 21. Timeout và circuit breaker

Timeout giới hạn thời gian chờ của một request. Circuit breaker theo dõi tỷ lệ lỗi hoặc độ trễ và tạm ngăn request mới tới service đang gặp sự cố.

Hai cơ chế bổ trợ nhau:

- Timeout ngăn một request chờ quá lâu.
- Circuit breaker giảm request gửi tới dependency đang lỗi.
- Retry xử lý lỗi tạm thời trong budget.
- Bulkhead giới hạn số request đồng thời để lỗi không lan rộng.

Ví dụ:

~~~text
connector customerService {
    timeout 3 seconds
    circuitBreaker {
        failureThreshold 5
        openDuration 20 seconds
    }
    bulkhead {
        maxConcurrent 30
    }
}
~~~

Các giá trị là minh họa. Cấu hình cần dựa trên latency thực tế, capacity và SLA của dependency. Retry quá nhiều trong khi circuit breaker đang mở có thể làm tăng tải và log noise.

## 22. Timeout và SLA/SLO

Timeout có thể được chọn dựa trên yêu cầu dịch vụ:

- SLA: cam kết dịch vụ với người dùng hoặc khách hàng.
- SLO: mục tiêu độ tin cậy hoặc latency nội bộ.
- SLI: chỉ số đo thực tế như tỷ lệ hoàn tất trong thời gian mục tiêu.

Ví dụ, nếu SLO yêu cầu 99% workflow hoàn thành trong 30 giây, deadline workflow có thể được đặt cao hơn hoặc bằng budget phù hợp sau khi phân bổ thời gian cho từng dependency.

Không nên chọn timeout chỉ dựa trên một giá trị tùy ý. Cần xem latency percentile, tải cao điểm, thời gian queue, retry và thời gian xử lý ở các bước phía sau.

### 22.1. Timeout quá ngắn

Timeout quá ngắn gây lỗi giả khi hệ thống có tải cao, mạng dao động hoặc dependency có tail latency. Nó có thể làm tăng retry, khiến service càng quá tải.

### 22.2. Timeout quá dài

Timeout quá dài giữ tài nguyên lâu, làm chậm phát hiện lỗi và tích lũy tác vụ chờ. Nó cũng có thể khiến người dùng chờ lâu hơn SLA.

### 22.3. Tail latency

Average latency không đủ để chọn timeout. Cần xem percentile như p95 hoặc p99, phân bố theo endpoint và điều kiện tải. Timeout nên cân bằng xác suất hoàn thành hợp lệ với giới hạn thời gian của workflow.

## 23. Observability cho timeout

Timeout cần được quan sát như một loại kết quả riêng, không gộp chung với mọi lỗi.

Các metric hữu ích:

- Timeout count theo workflow, step và connector.
- Timeout rate.
- Execution duration.
- Queue wait duration.
- Remaining deadline khi bắt đầu step.
- Retry count và retry delay.
- Cancellation success rate.
- Late completion count.
- Compensation duration.
- Workflow age.

Log hoặc trace nên chứa:

- Workflow instance ID.
- Step ID và attempt number.
- Configured timeout.
- Effective deadline.
- Elapsed time.
- Remaining budget.
- Timeout source hoặc scope.
- Cancellation outcome.
- Correlation ID của request bên ngoài.

### 23.1. Phân biệt timeout ở các lớp

Thông báo "timeout" chung chung không đủ để chẩn đoán. Cần phân biệt:

- Queue timeout.
- Connection timeout.
- Read timeout.
- Attempt timeout.
- Step timeout.
- Workflow deadline exceeded.
- Human task expired.

Phân loại chính xác giúp xác định lỗi nằm ở capacity của worker, network, service đích hay cấu hình workflow.

### 23.2. Trace span

Mỗi step hoặc external call có thể tạo span riêng. Khi workflow timeout, trace giúp biết thời gian đã tiêu ở đâu và bước nào còn hoạt động. Span nên ghi deadline và attempt number dưới dạng metadata, nhưng tránh đưa dữ liệu nhạy cảm vào trace.

## 24. Error handling khi timeout

DSL nên cho phép định nghĩa nhánh xử lý timeout riêng:

~~~text
step fetchCustomer {
    call customerService.get(customerId)
    timeout 2 seconds

    on timeout {
        retry
        then useCachedCustomer
        otherwise fail workflow
    }
}
~~~

Một policy timeout có thể chọn:

- Retry trong budget.
- Fallback sang cache hoặc service dự phòng.
- Chuyển sang manual review.
- Phát event và tiếp tục nhánh khác.
- Hủy workflow.
- Bắt đầu compensation.
- Đánh dấu trạng thái cần reconciliation.

Timeout nên có error code riêng để nhánh catch có thể phân biệt với validation failure hoặc authorization failure.

### 24.1. Fallback

Fallback chỉ an toàn khi dữ liệu thay thế đáp ứng yêu cầu nghiệp vụ. Ví dụ dùng cache có thể phù hợp cho dữ liệu tham khảo ít thay đổi nhưng không phù hợp cho số dư tài khoản cần chính xác tức thời.

DSL hoặc connector nên cho phép đánh dấu fallback có stale data và thời điểm cập nhật cuối.

### 24.2. Manual recovery

Một số timeout tạo ra trạng thái không xác định. Workflow có thể chuyển sang manual recovery queue thay vì tự retry vô hạn. Operator cần thấy request ID, trạng thái bên ngoài và các bước đã hoàn tất.

## 25. Semantics khi timeout xảy ra đồng thời với completion

Một race phổ biến: kết quả hoàn tất gần như cùng lúc với deadline. Engine cần quy tắc xác định trạng thái cuối.

Ví dụ:

- Completion được ghi nhận trước deadline: Completed.
- Deadline được xử lý trước completion: TimedOut, kết quả đến sau được xem là late.
- Hai event có timestamp gần nhau: dùng thứ tự commit hoặc sequence number do engine quản lý.

Không nên chỉ dựa vào thứ tự callback đến thread vì nó có thể khác giữa các lần chạy.

Với workflow bền vững, state transition cần atomic hoặc dùng optimistic concurrency/version để chỉ một transition thắng. Kết quả đến muộn cần được ghi nhận và xử lý riêng, không ghi đè trạng thái terminal một cách tùy tiện.

## 26. Timeout và workflow bền vững

Workflow có thể tồn tại lâu hơn process đang chạy. Engine cần lưu:

- Workflow deadline.
- Step deadline.
- Attempt start và attempt deadline.
- Retry state và next retry time.
- Timer registration.
- Cancellation state.
- Kết quả hoặc trạng thái chưa xác định của side effect.

Khi process restart, engine khôi phục timer và tiếp tục tính thời gian còn lại. Nếu deadline đã qua trong thời gian downtime, workflow cần được chuyển sang timeout handling khi phục hồi.

Timer scheduler nên có tính durable và xử lý duplicate delivery. Nếu cùng một timeout event được phát nhiều lần, state transition phải idempotent để workflow không chạy compensation hai lần.

## 27. Cấu hình timeout theo môi trường

Development, test, staging và production có thể có latency khác nhau. Tuy nhiên, nếu thay đổi timeout theo môi trường, semantics nghiệp vụ không nên bị thay đổi ngoài ý muốn.

Có thể tách:

- Workflow deadline mang ý nghĩa nghiệp vụ.
- Connector timeout mang ý nghĩa kỹ thuật.
- Test clock hoặc fake scheduler chỉ dùng trong test.
- Operational override có giới hạn và được audit.

Ví dụ:

~~~yaml
workflow:
  approvalDeadline: 2 business days

connectors:
  inventory:
    requestTimeout: 3s
  payment:
    requestTimeout: 5s
~~~

Không nên để production override kéo dài deadline vô hạn hoặc vô hiệu hóa timeout mà không có kiểm soát. Thay đổi cấu hình cần version và được ghi nhận.

## 28. Kiểm thử timeout

Timeout test cần xác nhận cả thời gian lẫn trạng thái workflow.

### 28.1. Unit test với fake clock

Không nên bắt test phải chờ thật nhiều giây. Dùng fake clock hoặc virtual time để tiến thời gian và xác nhận timer kích hoạt đúng.

### 28.2. Step timeout test

Giả lập task không hoàn tất trước deadline. Kiểm tra step chuyển trạng thái, cancellation được gửi và nhánh timeout chạy đúng.

### 28.3. Workflow deadline test

Tạo nhiều bước có thời gian khác nhau. Xác nhận tổng thời gian không vượt deadline và child step không được gia hạn parent.

### 28.4. Retry budget test

Giả lập nhiều lần timeout và backoff. Xác nhận maxAttempts, maxElapsedTime và overall deadline đều được tôn trọng.

### 28.5. Late completion test

Cho task hoàn tất sau khi workflow đã timeout. Xác nhận kết quả không ghi đè trạng thái terminal và được xử lý theo late-result policy.

### 28.6. Cancellation test

Xác nhận task cooperative dừng, resource được giải phóng và grace period có giới hạn. Với external request, kiểm tra hệ thống không giả định cancellation đã rollback side effect.

### 28.7. Idempotency test

Gửi lại request với cùng idempotency key sau timeout. Xác nhận side effect không bị thực hiện hai lần.

### 28.8. Persistence/restart test

Lưu workflow đang chờ, restart engine và xác nhận deadline được khôi phục đúng, kể cả khi deadline đã qua trong downtime.

### 28.9. Load test

Tăng tải để quan sát timeout rate, queue delay, retry storm và tài nguyên. Kiểm tra hệ thống không tự khuếch đại sự cố khi dependency chậm.

## 29. Những lỗi thiết kế thường gặp

### Chỉ đặt timeout ở HTTP client

Workflow có thể chờ queue hoặc các bước khác vô hạn. Đặt deadline ở nhiều lớp và có workflow-level budget.

### Mỗi retry được cấp lại toàn bộ timeout

Tổng thời gian có thể vượt xa giới hạn. Dùng maxElapsedTime và truyền deadline còn lại.

### Timeout nhưng không hủy task

Workflow kết thúc nhưng worker tiếp tục chạy và tạo side effect. Gửi cancellation, giới hạn grace period và xử lý late result.

### Giả định timeout đồng nghĩa request thất bại

Service có thể đã hoàn tất nhưng response bị mất. Dùng idempotency key và trạng thái có thể tra cứu.

### Retry thao tác không idempotent

Có thể charge, gửi email hoặc tạo record nhiều lần. Phân loại lỗi và thiết kế idempotency/compensation.

### Không phân biệt queue wait và execution

Không biết chậm do thiếu worker hay do task xử lý lâu. Đo và cấu hình hai loại timeout riêng.

### Timeout child vượt deadline parent

Child tiếp tục chạy sau khi workflow đã hết hạn. Dùng effective deadline là giới hạn sớm nhất.

### Timer chỉ tồn tại trong bộ nhớ

Restart làm mất timeout của workflow dài hạn. Lưu deadline và timer state bền vững.

### Không xử lý completion đến muộn

Kết quả cũ ghi đè trạng thái timeout hoặc kích hoạt side effect lặp. Dùng state version và late-result policy.

### Dùng timeout quá ngắn hoặc quá dài

Timeout ngắn gây retry storm; timeout dài giữ tài nguyên và che giấu lỗi. Chọn dựa trên latency percentile, SLA và budget tổng.

## 30. Quy trình thiết kế timeout cho DSL quy trình

Khi thiết kế timeout semantics, có thể thực hiện theo trình tự:

1. **Xác định giới hạn nghiệp vụ.** Workflow phải hoàn thành trong bao lâu?
2. **Phân rã budget.** Chia thời gian cho queue, từng step, dependency và dự phòng.
3. **Định nghĩa scope.** Workflow, stage, step, task, attempt, connector và human task.
4. **Chọn clock semantics.** Relative duration, absolute deadline, monotonic clock và business calendar.
5. **Định nghĩa kế thừa.** Effective deadline và quy tắc ghi đè.
6. **Thiết kế cancellation.** Cooperative cancellation, transport cancellation và grace period.
7. **Thiết kế retry.** Attempt timeout, max elapsed time, backoff, jitter và retryable errors.
8. **Bảo vệ side effect.** Idempotency, status lookup và compensation.
9. **Xử lý parallel và event.** Branch timeout, late event, timer persistence và race với completion.
10. **Tích hợp observability.** Metric, log, trace và error code riêng.
11. **Kiểm thử thời gian.** Fake clock, restart, late completion, load và retry storm.
12. **Tài liệu hóa mặc định.** Timeout default, giới hạn tối đa và hành vi khi không khai báo.

Timeout policy nên được xem là một phần của hợp đồng activity/connector. Người viết workflow cần biết thời gian tối đa, khả năng cancellation, tính idempotent và cách xử lý lỗi của mỗi hoạt động.

## 31. Ví dụ end-to-end: xử lý đơn hàng có deadline

Giả sử quy trình xác nhận đơn hàng cần hoàn thành trong 20 giây. Nó gồm kiểm tra đơn, giữ hàng, thanh toán và xác nhận:

~~~text
workflow checkout {
    timeout 20 seconds

    step validateOrder {
        call orderService.validate(orderId)
        timeout 2 seconds
    }

    step reserveInventory {
        call inventory.reserve(
            orderId,
            idempotencyKey = workflow.id + ":reserve"
        )
        timeout 4 seconds
        retry {
            maxAttempts 2
            maxElapsedTime 6 seconds
            backoff exponential
        }
        compensate inventory.release(orderId)
    }

    step chargePayment {
        call payment.charge(
            orderId,
            idempotencyKey = workflow.id + ":charge"
        )
        timeout 5 seconds
        on timeout {
            lookup payment.status by idempotencyKey
            if status == UNKNOWN {
                move to manualRecovery
            }
        }
        compensate payment.refund(orderId)
    }

    step confirmOrder {
        call orderService.confirm(orderId)
        timeout 2 seconds
    }
}
~~~

Khi chạy:

1. Engine tạo workflow deadline tại thời điểm bắt đầu.
2. Mỗi step nhận effective deadline không vượt quá deadline workflow.
3. Inventory retry dùng cùng idempotency key và không vượt maxElapsedTime.
4. Nếu payment timeout, engine tra cứu trạng thái trước khi quyết định retry hoặc compensation.
5. Nếu workflow hết deadline, engine gửi cancellation cho các task còn chạy.
6. Side effect đã commit được xử lý bằng compensation hoặc manual recovery.
7. Timer và state transition được lưu bền vững để restart không làm mất deadline.
8. Trace ghi lại thời gian queue, từng attempt, remaining budget và nguyên nhân timeout.

Ví dụ này cho thấy timeout không chỉ là số giây đặt cạnh một step. Nó cần phối hợp với deadline tổng, retry, idempotency, cancellation, compensation và khả năng khôi phục.

## 32. Kết luận

Timeout trong DSL quy trình giới hạn thời gian chờ và thực thi của workflow, stage, step, task, attempt, connector hoặc human task. Thiết kế đúng cần phân biệt timeout tương đối với deadline, thời gian chờ queue với thời gian xử lý, và lỗi timeout với trạng thái không xác định của side effect.

Một workflow engine nên truyền deadline xuống các bước con, giới hạn retry theo budget tổng, hỗ trợ cancellation, xử lý kết quả đến muộn và lưu timer bền vững. Với hoạt động có side effect, idempotency và compensation giúp xử lý an toàn khi response bị mất hoặc tác vụ kết thúc không rõ kết quả.

Timeout nên được chọn từ SLA/SLO, latency thực tế và ngân sách thời gian của cả quy trình. Khi có error code, metric, trace và kiểm thử bằng fake clock, timeout trở thành một cơ chế vận hành có thể dự đoán thay vì một giới hạn thời gian tùy ý.
