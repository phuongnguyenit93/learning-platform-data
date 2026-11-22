# Quản lý trạng thái khi thực thi DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích trạng thái (state) trong quá trình thực thi một DSL và phân biệt nó với cú pháp, mô hình tĩnh và dữ liệu đầu vào.
- Xác định các loại trạng thái: biến cục bộ, ngữ cảnh thực thi, trạng thái phiên, trạng thái quy trình và trạng thái bền vững.
- Thiết kế phạm vi, vòng đời và quyền sở hữu của trạng thái.
- Phân biệt trạng thái mutable và immutable, cũng như cách tổ chức các phép chuyển trạng thái.
- Quản lý trạng thái qua nhiều lần thực thi, giao dịch, lưu trữ và khôi phục.
- Xử lý trạng thái khi có thực thi đồng thời, lỗi, retry hoặc tạm dừng.
- Thiết kế cách truy vết, kiểm soát quyền truy cập và bảo vệ dữ liệu trạng thái.
- Xây dựng runtime DSL có hành vi xác định, dễ kiểm thử và vận hành.

## 1. Trạng thái trong thực thi DSL là gì?

Một chương trình DSL mô tả các quy tắc, phép tính, truy vấn hoặc quy trình. Khi runtime thực thi chương trình đó, nó cần ghi nhớ những thông tin đang có hiệu lực tại thời điểm hiện tại. Tập thông tin này được gọi là **trạng thái (state)**.

Ví dụ, một DSL mô tả quy trình phê duyệt:

~~~text
workflow "purchase_approval" {
    state = "SUBMITTED"

    when amount <= 1000000:
        state = "APPROVED"

    when amount > 1000000:
        state = "WAITING_MANAGER"
}
~~~

Trong lúc chạy, runtime cần biết giá trị amount, trạng thái hiện tại của workflow, người gửi yêu cầu và các biến được tạo trong từng nhánh. Khi một điều kiện đúng, trạng thái có thể được cập nhật để phản ánh bước tiếp theo.

Quản lý trạng thái (state management) là tập hợp cơ chế mà runtime dùng để:

- Tạo trạng thái ban đầu.
- Xác định nơi và thời gian một giá trị có hiệu lực.
- Đọc và cập nhật giá trị trong khi thực thi.
- Kiểm soát những thành phần được phép thay đổi trạng thái.
- Lưu trạng thái để dùng lại ở lần thực thi sau.
- Đồng bộ trạng thái khi nhiều tác vụ cùng hoạt động.
- Khôi phục trạng thái khi có lỗi hoặc hệ thống khởi động lại.
- Ghi lại lịch sử thay đổi để kiểm tra và truy vết.

Trạng thái không chỉ là biến. Nó có thể gồm dữ liệu đầu vào, biến cục bộ, kết quả trung gian, trạng thái phiên, trạng thái workflow, thông tin giao dịch, bộ đếm retry và metadata phục vụ runtime.

## 2. Vì sao DSL runtime cần quản lý trạng thái?

Một DSL chỉ tính biểu thức thuần túy có thể không cần trạng thái mutable. Ví dụ, biểu thức:

~~~text
subtotal = quantity * unitPrice
~~~

có thể được tính từ đầu vào mà không cần ghi nhớ lần chạy trước. Nhưng nhiều DSL được dùng để mô tả quy trình kéo dài, quy tắc có tác dụng phụ, tương tác với người dùng hoặc tích hợp hệ thống bên ngoài. Những chương trình đó cần trạng thái.

Các tình huống điển hình:

- **Quy tắc nghiệp vụ:** ghi nhận kết quả kiểm tra, số lần áp dụng hoặc trạng thái xử lý.
- **Workflow:** lưu bước hiện tại, người chịu trách nhiệm và các dữ liệu đã thu thập.
- **Truy vấn tương tác:** giữ bộ lọc, phân trang hoặc cursor qua nhiều yêu cầu.
- **Mô phỏng:** lưu vị trí, năng lượng, thời gian và trạng thái của các đối tượng.
- **Điều khiển thiết bị:** lưu trạng thái cảm biến, chế độ hoạt động và lịch sử sự kiện.
- **Template:** giữ biến ngữ cảnh và kết quả tính toán trong khi dựng nội dung.
- **Phiên người dùng:** lưu lựa chọn hoặc dữ liệu tạm trong một phiên làm việc.

Nếu trạng thái không được quản lý rõ ràng, runtime có thể gặp các lỗi như biến của lần chạy trước rò sang lần chạy sau, hai phiên ghi đè dữ liệu của nhau, cập nhật bị mất, retry thực hiện tác dụng phụ hai lần hoặc khôi phục một quy trình về trạng thái không nhất quán.

## 3. Phân biệt mô hình, đầu vào và trạng thái runtime

Ba loại thông tin thường cùng xuất hiện nhưng có vai trò khác nhau.

| Loại thông tin | Ý nghĩa | Ví dụ |
|---|---|---|
| DSL model | Cấu trúc chương trình được mô tả | Rule, workflow, expression, action |
| Input data | Dữ liệu được cung cấp cho một lần chạy | order, customer, amount |
| Runtime state | Thông tin được tạo hoặc thay đổi trong lúc chạy | currentStep, retryCount, approvalStatus |

Ví dụ, mô hình workflow quy định một quy trình có bước SUBMITTED và APPROVED. Input data chứa đơn hàng có amount bằng 500000. Runtime state cho biết quy trình cụ thể này đã được phê duyệt hay vẫn đang chờ.

Không nên ghi trạng thái của một lần chạy vào chính DSL model dùng chung cho mọi lần chạy. Nếu làm vậy, hai yêu cầu chạy cùng một workflow có thể ảnh hưởng lẫn nhau.

### 3.1. Model thường bất biến trong lúc chạy

Một thiết kế phổ biến là biên dịch hoặc chuẩn hóa DSL model thành một artifact dùng chung, sau đó tạo execution context riêng cho mỗi lần chạy. Model mô tả logic; context giữ dữ liệu và trạng thái của lần thực thi.

~~~text
             DSL source
                 |
                 v
          Compiled DSL model
                 |
          +------+------+
          |             |
          v             v
      Run A           Run B
    Context A       Context B
    State A         State B
~~~

Việc tách này giúp runtime tái sử dụng model đã biên dịch mà vẫn cô lập dữ liệu của từng lần chạy.

### 3.2. Input có thể trở thành state

Input ban đầu có thể được sao chép hoặc tham chiếu vào execution context. Nếu DSL cho phép thay đổi dữ liệu đầu vào, cần xác định thay đổi đó chỉ tồn tại trong lần chạy hay phải được ghi ngược về hệ thống sở hữu dữ liệu.

Không nên mặc định rằng gán lại một biến trong DSL sẽ cập nhật cơ sở dữ liệu hoặc object bên ngoài. Hành vi ghi ra ngoài cần được thể hiện bằng action hoặc API có hợp đồng rõ ràng.

## 4. Các phạm vi trạng thái thường gặp

Trạng thái nên được chia theo phạm vi (scope) và vòng đời (lifetime). Mỗi loại có thời điểm tạo, chủ sở hữu và thời điểm giải phóng khác nhau.

### 4.1. Trạng thái biểu thức

Đây là giá trị trung gian trong khi đánh giá một biểu thức:

~~~text
total = quantity * unitPrice + shippingFee
~~~

Runtime có thể lưu kết quả của quantity * unitPrice trong stack frame hoặc vùng nhớ tạm. Giá trị thường chỉ cần tồn tại trong thời gian đánh giá biểu thức.

### 4.2. Trạng thái cục bộ

Biến cục bộ được tạo trong một block hoặc hàm:

~~~text
function calculateDiscount(order):
    let rate = 5%
    let discount = order.total * rate
    return discount
~~~

Biến rate và discount có phạm vi trong lời gọi hàm. Khi hàm kết thúc, runtime có thể giải phóng vùng lưu trữ nếu không có closure hoặc cơ chế khác giữ chúng lại.

### 4.3. Trạng thái của một lần thực thi

Execution state tồn tại trong toàn bộ một lần chạy DSL. Nó có thể chứa input đã được kiểm tra, biến toàn cục của lần chạy, kết quả các bước trước, danh sách action đã thực hiện, lỗi và thông tin chẩn đoán, trạng thái hủy hoặc timeout.

Khi lần chạy kết thúc, state có thể được giải phóng hoặc lưu thành kết quả.

### 4.4. Trạng thái phiên

Session state tồn tại qua nhiều tương tác trong cùng một phiên:

~~~text
session.cart.items
session.currentPage
session.lastSearch
~~~

Runtime cần xác định phiên được tạo và hết hạn như thế nào, dữ liệu nào được lưu, ai có quyền truy cập và cách xử lý khi người dùng mở nhiều phiên.

### 4.5. Trạng thái quy trình

Workflow state có thể tồn tại hàng giờ, hàng ngày hoặc lâu hơn. Nó thường cần được lưu bền vững để có thể tiếp tục sau khi runtime dừng.

~~~text
workflowInstance {
    id = "WF-2048"
    currentState = "WAITING_MANAGER"
    assignedTo = "manager-17"
    retryCount = 1
}
~~~

### 4.6. Trạng thái toàn cục của runtime

Một số dữ liệu được chia sẻ bởi nhiều lần chạy, chẳng hạn registry hàm, cache schema hoặc cấu hình hệ thống. Đây là trạng thái ở phạm vi runtime hoặc process.

Không nên đặt dữ liệu riêng của người dùng hoặc workflow vào global mutable state. Global state có thể được nhiều luồng cùng truy cập và khó cô lập.

### 4.7. Bảng tổng hợp vòng đời

| Phạm vi | Bắt đầu | Kết thúc | Ví dụ |
|---|---|---|---|
| Biểu thức | Khi đánh giá biểu thức | Khi tính xong | Giá trị trung gian |
| Block/hàm | Khi vào block hoặc gọi hàm | Khi rời block hoặc trả về | Biến cục bộ |
| Execution | Khi bắt đầu một lần chạy | Khi hoàn tất hoặc hủy | Context của rule |
| Session | Khi mở phiên | Khi đóng hoặc hết hạn | Giỏ hàng tạm |
| Workflow | Khi tạo instance | Khi kết thúc hoặc lưu trữ | Trạng thái phê duyệt |
| Runtime/process | Khi runtime khởi động | Khi runtime dừng | Cache schema |

## 5. Execution context

Execution context là đối tượng hoặc cấu trúc chứa thông tin cần thiết để thực thi một chương trình DSL trong một lần chạy.

Ví dụ khái niệm:

~~~text
ExecutionContext {
    executionId
    model
    input
    variables
    currentScope
    currentStep
    stateStore
    permissions
    deadline
    diagnostics
}
~~~

Không phải runtime nào cũng cần mọi trường trên. Điều quan trọng là xác định rõ context chứa dữ liệu nào và dữ liệu nào thuộc dịch vụ khác.

### 5.1. Execution ID

Mỗi lần chạy nên có định danh duy nhất để liên kết log, metric, trạng thái và tác dụng phụ. Khi một workflow được retry hoặc resume, cần xác định đó là cùng một execution hay một attempt mới thuộc cùng workflow instance.

### 5.2. Model và input

Model thường được chia sẻ bất biến. Input có thể là snapshot hoặc tham chiếu đến dữ liệu bên ngoài. Nếu input thay đổi trong khi thực thi, runtime cần có chính sách nhất quán: dùng snapshot ban đầu, đọc dữ liệu mới mỗi lần hay kiểm tra phiên bản.

### 5.3. Variable environment

Variable environment ánh xạ tên biến hoặc symbol đến giá trị hiện tại. Ví dụ:

~~~text
variables = {
    "amount": 750000,
    "approved": false,
    "retryCount": 0
}
~~~

Trong implementation thực tế, có thể dùng symbol ID thay cho tên chuỗi để tránh xung đột tên và tăng tốc tra cứu.

### 5.4. Scope stack

Khi đi vào block hoặc hàm, runtime có thể đẩy một scope frame mới lên stack. Khi rời block, frame được lấy ra.

~~~text
Global scope
    |
    +-- Workflow scope
            |
            +-- Function scope
                    |
                    +-- Block scope
~~~

Tra cứu biến thường bắt đầu ở scope gần nhất rồi đi ra scope bên ngoài theo quy tắc lexical scope. Khi block kết thúc, biến cục bộ không còn truy cập được trừ khi được capture bởi closure hoặc được lưu vào state có vòng đời dài hơn.

### 5.5. Context không nên là túi dữ liệu tùy tiện

Một context chứa mọi thứ dưới dạng map không kiểu có thể dễ mở rộng nhưng làm khó kiểm tra quyền truy cập, kiểu và vòng đời. Nên phân nhóm rõ input, variables, workflow state, service capabilities và diagnostics. Với dữ liệu quan trọng, dùng schema hoặc kiểu xác định.

## 6. Variable scope và vòng đời biến

Scope xác định nơi tên biến có thể được truy cập. Lifetime xác định giá trị tồn tại bao lâu. Hai khái niệm liên quan nhưng không đồng nhất.

### 6.1. Lexical scope

Trong lexical scope, phạm vi biến được xác định bởi cấu trúc mã nguồn:

~~~text
let status = "NEW"

if order.total > 100000:
    let message = "High value"
    log(message)

log(status)
~~~

message chỉ tồn tại trong block if, còn status có thể được dùng ở phần sau của phạm vi chứa nó.

### 6.2. Shadowing

Một DSL có thể cho phép khai báo biến cục bộ trùng tên biến bên ngoài:

~~~text
let status = "NEW"

if urgent:
    let status = "PRIORITY"
    process(status)

log(status)
~~~

Nếu shadowing được hỗ trợ, status trong block là biến khác với status bên ngoài. Runtime phải dùng symbol hoặc scope frame để phân biệt.

Một DSL cũng có thể cấm shadowing để giảm nhầm lẫn. Dù chọn cách nào, quy tắc phải nhất quán giữa parser, semantic analysis và runtime.

### 6.3. Biến capture trong closure

Một hàm hoặc lambda có thể sử dụng biến của scope bên ngoài:

~~~text
let threshold = 100
let predicate = item => item.total > threshold
~~~

Nếu predicate được lưu để gọi sau khi block ban đầu kết thúc, runtime cần giữ giá trị threshold theo cơ chế capture. Có thể capture theo giá trị hoặc theo tham chiếu tùy semantics DSL.

### 6.4. Stack frame

Mỗi lời gọi hàm thường tạo một stack frame chứa tham số, biến cục bộ và thông tin trả về. Khi hàm kết thúc, frame được thu hồi. Đệ quy tạo nhiều frame độc lập.

Nếu DSL hỗ trợ workflow tạm dừng và resume, không thể chỉ dựa vào stack frame thông thường vì stack có thể đã bị giải phóng. Runtime cần serialize continuation hoặc lưu trạng thái đủ để tái tạo điểm tiếp tục.

## 7. Mutable và immutable state

Trạng thái mutable có thể thay đổi sau khi được tạo. Trạng thái immutable không thay đổi; một cập nhật tạo ra giá trị mới.

### 7.1. Mutable state

Ví dụ:

~~~text
counter = 0
counter = counter + 1
counter = counter + 1
~~~

Runtime cập nhật cùng một vị trí lưu trữ. Mutable state tiện cho các thuật toán tuần tự nhưng cần kiểm soát khi có nhiều tác vụ cùng truy cập.

### 7.2. Immutable state

Ví dụ:

~~~text
state1 = { count: 0 }
state2 = state1 with { count: 1 }
state3 = state2 with { count: 2 }
~~~

Mỗi phiên bản là một giá trị mới. Các phiên bản trước có thể được giữ lại để audit, undo hoặc so sánh.

### 7.3. So sánh

| Tiêu chí | Mutable | Immutable |
|---|---|---|
| Cập nhật | Thay đổi đối tượng hiện tại | Tạo phiên bản mới |
| Bộ nhớ | Có thể tiết kiệm nếu sửa tại chỗ | Có thể cần allocation, nhưng có thể dùng structural sharing |
| Đồng thời | Cần đồng bộ hoặc cô lập | Dễ chia sẻ an toàn hơn |
| Lịch sử | Cần tự ghi lại thay đổi | Có thể giữ nhiều phiên bản |
| Debug | Khó biết thời điểm giá trị đổi nếu thiếu log | Dễ so sánh snapshot |
| Tích hợp runtime | Phù hợp với API imperative | Phù hợp với reducer và event-based model |

### 7.4. Chọn mô hình phù hợp

Không cần biến toàn bộ DSL thành immutable nếu runtime hoặc hệ thống tích hợp dựa trên mutable object. Tuy nhiên, state dài hạn hoặc state chia sẻ giữa nhiều tác vụ thường có lợi khi dùng snapshot bất biến hoặc cập nhật thông qua một API có kiểm soát.

Một cách kết hợp là dùng biến cục bộ mutable trong một execution frame, nhưng mọi thay đổi workflow state phải đi qua một state transition API.

## 8. State transition và state machine

State transition là phép chuyển một trạng thái từ giá trị hiện tại sang giá trị tiếp theo. State machine định nghĩa các trạng thái và chuyển đổi được phép.

Ví dụ, một đơn hàng có các trạng thái:

~~~text
NEW -> SUBMITTED -> APPROVED -> SHIPPED -> COMPLETED
                  |
                  +-> REJECTED
~~~

Không phải mọi chuyển đổi đều hợp lệ. Một đơn hàng đã SHIPPED có thể không được quay lại NEW.

### 8.1. Khai báo trạng thái

DSL có thể khai báo:

~~~text
state OrderStatus {
    NEW
    SUBMITTED
    APPROVED
    REJECTED
    SHIPPED
    COMPLETED
}
~~~

### 8.2. Khai báo chuyển đổi

~~~text
transition SUBMITTED -> APPROVED
    when manager.approves

transition SUBMITTED -> REJECTED
    when manager.rejects

transition APPROVED -> SHIPPED
    when payment.isConfirmed
~~~

Runtime kiểm tra trạng thái hiện tại và điều kiện trước khi áp dụng chuyển đổi.

### 8.3. Guard

Guard là điều kiện phải đúng trước khi chuyển trạng thái:

~~~text
transition APPROVED -> SHIPPED
    guard payment.status == "PAID"
~~~

Guard nên được đánh giá trong ngữ cảnh nhất quán với thao tác cập nhật. Nếu trạng thái payment có thể thay đổi giữa lúc kiểm tra và lúc ghi, cần transaction hoặc cơ chế kiểm tra phiên bản.

### 8.4. Entry và exit action

Một state machine có thể hỗ trợ hành động khi vào hoặc rời trạng thái:

~~~text
state APPROVED {
    onEnter:
        notifyWarehouse(order)
}
~~~

Các action này có tác dụng phụ. Runtime cần xác định khi transition thất bại hoặc retry, onEnter có thể được thực hiện lại hay không.

### 8.5. Transition nguyên tử

Việc kiểm tra guard, thay trạng thái và ghi sự kiện liên quan nên được xử lý như một thao tác nguyên tử nếu hệ thống yêu cầu. Nếu chỉ cập nhật một phần, workflow có thể rơi vào trạng thái không nhất quán.

## 9. State store và API truy cập trạng thái

Runtime có thể cung cấp một State Store để đọc và cập nhật state. Việc truy cập nên đi qua API có hợp đồng rõ ràng.

Ví dụ khái niệm:

~~~text
stateStore.read(executionId, key)
stateStore.write(executionId, key, value)
stateStore.compareAndSet(executionId, key, expectedVersion, value)
stateStore.appendEvent(executionId, event)
~~~

### 9.1. Đọc trạng thái

Đọc state cần xác định phạm vi dữ liệu, quyền truy cập, phiên bản hoặc snapshot được đọc, hành vi khi key chưa tồn tại và kiểu dữ liệu được trả về.

Nếu key chưa tồn tại, runtime có thể trả về Optional, giá trị default hoặc lỗi. Không nên để mỗi backend xử lý khác nhau.

### 9.2. Ghi trạng thái

Ghi state cần xác định có cho phép ghi key đó không, giá trị có đúng kiểu và schema không, có cần kiểm tra transition không, ghi có được thực hiện ngay hay chỉ khi commit, và có cần ghi lịch sử thay đổi không.

### 9.3. Compare-and-set

Compare-and-set (CAS) chỉ cập nhật nếu phiên bản hiện tại vẫn bằng phiên bản mà caller đã đọc. Cơ chế này giúp tránh ghi đè cập nhật mới hơn.

~~~text
read state version 7
compute next state
compareAndSet(expectedVersion = 7, newState)
~~~

Nếu một tác vụ khác đã cập nhật lên version 8, thao tác CAS thất bại và caller cần đọc lại, tính lại hoặc báo conflict.

### 9.4. Tách state logic khỏi storage

DSL nên mô tả ý nghĩa của trạng thái. Runtime hoặc adapter quyết định lưu trong memory, database, distributed store hay event log. Tách hai lớp giúp cùng một DSL chạy trên nhiều môi trường.

## 10. Trạng thái tạm thời và trạng thái bền vững

Trạng thái tạm thời (ephemeral state) chỉ tồn tại trong bộ nhớ hoặc trong một lần chạy. Trạng thái bền vững (persistent state) được lưu để tồn tại qua lần chạy hoặc lần khởi động lại.

### 10.1. Ephemeral state

Ví dụ là giá trị trung gian của biểu thức, biến cục bộ, bộ đếm trong một lần tính toán và cache ngắn hạn của một execution. Khi execution kết thúc, runtime có thể giải phóng dữ liệu này.

### 10.2. Persistent state

Ví dụ là trạng thái workflow instance, lịch sử phê duyệt, kết quả checkpoint, cursor của tiến trình xử lý dài hạn và dữ liệu session cần khôi phục sau reconnect.

Persistent state cần schema, version, chính sách lưu trữ và cơ chế kiểm soát truy cập.

### 10.3. Snapshot

Snapshot lưu toàn bộ hoặc một phần trạng thái tại một thời điểm:

~~~text
WorkflowSnapshot {
    instanceId = "WF-2048"
    version = 12
    currentState = "WAITING_MANAGER"
    variables = {
        amount = 750000
        retryCount = 1
    }
}
~~~

Snapshot giúp khôi phục nhanh mà không phải phát lại toàn bộ lịch sử. Tuy nhiên, snapshot cần được ghi nhất quán với version và event tương ứng.

### 10.4. Event log

Thay vì chỉ lưu trạng thái hiện tại, hệ thống có thể ghi các sự kiện:

~~~text
OrderSubmitted
ManagerAssigned
ManagerApproved
PaymentConfirmed
OrderShipped
~~~

State hiện tại được suy ra bằng cách áp dụng các event theo thứ tự. Đây là ý tưởng nền tảng của event sourcing.

### 10.5. Snapshot kết hợp event log

Để tránh phát lại quá nhiều event, hệ thống có thể lưu snapshot định kỳ và chỉ phát lại các event sau snapshot.

~~~text
Event 1 -> Event 2 -> Event 3 -> Event 4 -> Event 5
                         |
                         v
                    Snapshot 3
                         |
                         +-> Replay Event 4, Event 5
~~~

### 10.6. Chọn cách lưu

| Nhu cầu | Cách lưu có thể phù hợp |
|---|---|
| Giá trị tạm trong một lần chạy | Memory |
| Workflow cần resume | Database hoặc durable state store |
| Audit đầy đủ từng thay đổi | Event log |
| Khôi phục nhanh trạng thái lớn | Snapshot kết hợp event log |
| Cache kết quả tính toán | Cache có TTL và invalidation |

## 11. Transaction và tính nhất quán

Một thao tác DSL có thể đọc nhiều giá trị, kiểm tra điều kiện và cập nhật nhiều phần state. Nếu lỗi xảy ra giữa chừng, hệ thống cần quyết định có giữ các cập nhật một phần hay rollback.

### 11.1. Transaction

Transaction gom một nhóm thao tác thành một đơn vị:

~~~text
transaction:
    accountA.balance = accountA.balance - amount
    accountB.balance = accountB.balance + amount
    transfer.status = "COMPLETED"
~~~

Nếu một cập nhật thất bại, transaction có thể rollback toàn bộ thay đổi để không làm mất cân bằng.

### 11.2. Atomicity

Atomicity nghĩa là giao dịch được xem như hoàn tất toàn bộ hoặc không hoàn tất. Với state store hỗ trợ transaction, runtime có thể ghi nhiều thay đổi trong một commit.

### 11.3. Consistency

Consistency yêu cầu các invariant của hệ thống vẫn đúng sau transaction. Ví dụ, tổng số dư trong một chuyển khoản nội bộ phải được bảo toàn theo quy tắc nghiệp vụ.

### 11.4. Isolation

Isolation xác định các transaction đồng thời nhìn thấy thay đổi của nhau như thế nào. Nếu hai execution cùng đọc số dư 100 rồi mỗi execution trừ 80, cả hai có thể cùng nghĩ thao tác hợp lệ nếu không có isolation hoặc kiểm tra version.

### 11.5. Durability

Durability bảo đảm dữ liệu đã commit vẫn tồn tại sau sự cố theo cam kết của storage.

### 11.6. Transaction boundary trong DSL

Không phải mọi DSL đều cần cú pháp transaction. Runtime có thể cung cấp transaction boundary ở mức action hoặc workflow step. Điều quan trọng là người thiết kế phải biết chính xác phần nào được commit cùng nhau.

## 12. Tác dụng phụ và giao dịch với hệ thống bên ngoài

Một transaction database không thể tự động rollback email đã gửi hoặc yêu cầu HTTP đã tới hệ thống khác.

Ví dụ:

~~~text
transaction:
    order.status = "APPROVED"
    sendEmail(customer.email, "Order approved")
~~~

Nếu database commit thất bại sau khi email đã gửi, người nhận vẫn có thể nhận email dù đơn hàng chưa được cập nhật.

### 12.1. Outbox pattern

Một cách phổ biến là ghi trạng thái và thông điệp cần gửi vào cùng transaction:

~~~text
transaction:
    order.status = "APPROVED"
    outbox.append(OrderApproved(order.id))
~~~

Một worker riêng đọc outbox và gửi thông báo. Nếu gửi thất bại, nó có thể retry theo chính sách. Điều này giúp tránh trạng thái đã commit nhưng thông điệp bị mất.

### 12.2. Idempotency key

Khi retry một action, runtime có thể gửi cùng idempotency key để hệ thống đích nhận biết đó là cùng một yêu cầu logic. Hệ thống đích cần hỗ trợ và lưu kết quả tương ứng.

### 12.3. Saga và compensating action

Với workflow nhiều dịch vụ, không thể giữ một transaction phân tán mở trong thời gian dài. Saga chia quy trình thành các bước có commit riêng và có hành động bù (compensating action) khi bước sau thất bại.

Ví dụ:
1. Giữ chỗ hàng.
2. Thu tiền.
3. Tạo vận đơn.

Nếu tạo vận đơn thất bại, hệ thống có thể hoàn tiền và giải phóng chỗ hàng. Đây là hành động bù nghiệp vụ, không phải rollback vật lý của mọi hệ thống.

### 12.4. Phân biệt retry và compensation

Retry thử lại cùng một hành động khi lỗi có khả năng tạm thời. Compensation thực hiện một hành động khác để đưa hệ thống về trạng thái nghiệp vụ chấp nhận được. Dùng nhầm hai cơ chế có thể tạo tác dụng phụ lặp hoặc làm mất dữ liệu.

## 13. Thực thi đồng thời và cô lập trạng thái

Một runtime có thể xử lý nhiều execution cùng lúc. Nếu chúng chia sẻ state mutable, cần kiểm soát truy cập.

### 13.1. Race condition

Race condition xảy ra khi kết quả phụ thuộc thứ tự xen kẽ của các thao tác đồng thời.

Ví dụ:

~~~text
current = state.counter
state.counter = current + 1
~~~

Hai tác vụ có thể cùng đọc counter = 4, cùng tính 5 và cùng ghi 5. Kết quả cuối là 5 thay vì 6. Đây là lost update.

### 13.2. Lock

Mutex hoặc lock có thể bảo vệ vùng đọc-cập nhật:

~~~text
lock(state.counter):
    state.counter = state.counter + 1
~~~

Lock giúp tuần tự hóa truy cập nhưng có thể làm giảm thông lượng hoặc gây deadlock nếu thứ tự lấy lock không nhất quán.

### 13.3. Atomic operation

Nếu chỉ cần tăng bộ đếm, một phép atomic increment có thể phù hợp hơn đọc rồi ghi riêng lẻ. API nên cung cấp thao tác nguyên tử cho các cập nhật phổ biến.

### 13.4. Optimistic concurrency

Optimistic concurrency cho phép nhiều execution tính toán đồng thời, nhưng khi commit sẽ kiểm tra version. Nếu state đã thay đổi, một execution phải retry hoặc báo conflict.

### 13.5. Isolation theo execution

Một cách an toàn là mỗi execution có context riêng. Dữ liệu chia sẻ chỉ được truy cập qua state store hoặc service API. Không dùng biến global mutable để giữ dữ liệu riêng của một request.

### 13.6. Actor hoặc mailbox

Với workflow hoặc entity có state riêng, mô hình actor có thể đảm bảo mỗi instance xử lý message tuần tự. Các message được xếp hàng, và chỉ một handler thay đổi state của instance tại một thời điểm.

### 13.7. State immutable và concurrency

Snapshot bất biến có thể được nhiều tác vụ đọc đồng thời. Khi cập nhật, runtime tạo phiên bản mới và dùng CAS hoặc transaction để công bố phiên bản mới. Cách này giảm nguy cơ một tác vụ nhìn thấy object đang bị sửa dở.

## 14. Tạm dừng, tiếp tục và khôi phục thực thi

Workflow DSL thường cần tạm dừng để chờ phê duyệt, sự kiện hoặc thời điểm tương lai. Runtime phải lưu đủ thông tin để tiếp tục đúng vị trí.

### 14.1. Checkpoint

Checkpoint là điểm lưu trạng thái thực thi:

~~~text
Checkpoint {
    workflowInstanceId
    modelVersion
    currentStep
    variables
    pendingActions
    stateVersion
}
~~~

Khi resume, runtime nạp checkpoint, kiểm tra phiên bản model và tiếp tục từ currentStep.

### 14.2. Continuation

Continuation mô tả phần công việc còn lại sau điểm tạm dừng. Interpreter có thể lưu program counter và các frame cần thiết, hoặc chuyển workflow thành các step tường minh để dễ serialize.

Không phải stack frame của mọi ngôn ngữ chủ đều có thể serialize. Vì vậy, runtime workflow thường thiết kế trạng thái tiếp tục riêng thay vì cố lưu nguyên call stack.

### 14.3. Model version

Nếu DSL source thay đổi trong khi workflow instance đang tạm dừng, runtime cần biết instance tiếp tục theo model version cũ hay được migrate sang version mới.

Các lựa chọn:
- Giữ artifact đã biên dịch của phiên bản cũ cho đến khi instance kết thúc.
- Chuyển state bằng migration được kiểm soát.
- Hủy hoặc yêu cầu xử lý thủ công nếu migration không an toàn.

Không nên âm thầm chạy state cũ trên model mới nếu cấu trúc biến hoặc ý nghĩa bước đã thay đổi.

### 14.4. Recovery sau crash

Sau khi runtime khởi động lại, nó có thể:
1. Tìm workflow instance chưa kết thúc.
2. Đọc snapshot gần nhất.
3. Phát lại event sau snapshot nếu dùng event log.
4. Kiểm tra action đang chờ hoặc trạng thái outbox.
5. Khôi phục execution context.
6. Tiếp tục từ checkpoint hoặc chuyển sang trạng thái lỗi cần can thiệp.

### 14.5. Exactly-once và thực tế phân tán

Trong hệ thống phân tán, bảo đảm một action chỉ thực hiện đúng một lần trên mọi tình huống là khó. Thông thường runtime dùng at-least-once delivery kết hợp idempotency, deduplication và transaction để đạt kết quả nghiệp vụ an toàn.

Không nên tuyên bố action là exactly-once nếu hệ thống đích không cung cấp cơ chế tương ứng.

## 15. Xử lý lỗi và trạng thái không nhất quán

Khi thực thi thất bại, runtime cần quyết định trạng thái được giữ, rollback hay chuyển sang trạng thái lỗi.

### 15.1. Phân loại lỗi

- Lỗi đầu vào: dữ liệu không hợp lệ.
- Lỗi DSL: tham chiếu, kiểu hoặc cấu trúc không hợp lệ.
- Lỗi thực thi: phép toán hoặc action thất bại.
- Lỗi hạ tầng: database, network hoặc service không khả dụng.
- Lỗi cạnh tranh: version conflict hoặc lock timeout.
- Lỗi hệ thống: process crash hoặc hết tài nguyên.

Mỗi loại lỗi có thể cần chính sách retry và phục hồi khác nhau.

### 15.2. Error state

Một workflow có thể có trạng thái FAILED, CANCELLED hoặc COMPENSATING. Không nên chỉ lưu một cờ boolean nếu hệ thống cần phân biệt nguyên nhân và bước xử lý.

~~~text
WorkflowState {
    status = "FAILED"
    failedStep = "CHARGE_PAYMENT"
    errorCode = "PAYMENT_TIMEOUT"
    retryCount = 2
    lastUpdatedAt = timestamp
}
~~~

### 15.3. Retry policy

Retry policy có thể xác định loại lỗi nào được retry, số lần tối đa, khoảng chờ giữa các lần, backoff tuyến tính hoặc exponential, jitter để tránh nhiều tác vụ retry cùng lúc và điều kiện dừng hoặc chuyển sang manual review.

Ví dụ:

~~~text
retry {
    maxAttempts = 4
    initialDelay = 2 seconds
    backoff = exponential
    retryOn = [TIMEOUT, TEMPORARY_UNAVAILABLE]
}
~~~

Retry chỉ an toàn khi action idempotent hoặc có cơ chế deduplication.

### 15.4. Dead-letter hoặc manual intervention

Sau khi hết số lần retry, workflow có thể chuyển vào dead-letter queue hoặc trạng thái cần người vận hành xử lý. Cần giữ lỗi cuối, lịch sử attempt và dữ liệu cần thiết để điều tra.

### 15.5. Không giữ lock khi chờ lâu

Nếu workflow chờ người phê duyệt nhiều giờ, không nên giữ database transaction hoặc lock trong suốt thời gian chờ. Hãy commit trạng thái chờ, giải phóng tài nguyên và mở transaction mới khi có sự kiện tiếp theo.

## 16. Tính xác định và khả năng tái hiện

Một chương trình DSL có tính xác định nếu cùng model, input và trạng thái ban đầu tạo ra cùng hành vi theo hợp đồng ngôn ngữ.

### 16.1. Nguồn gây không xác định

- Thời gian hệ thống.
- Số ngẫu nhiên.
- Dữ liệu bên ngoài thay đổi.
- Thứ tự xử lý message đồng thời.
- Thứ tự duyệt collection không được định nghĩa.
- Locale hoặc timezone mặc định.
- Trạng thái global thay đổi.

### 16.2. Inject clock và random source

Thay vì để DSL tự gọi clock toàn cục, runtime có thể cung cấp Clock interface. Khi kiểm thử, dùng clock giả với thời điểm cố định. Random source cũng có thể nhận seed để tái hiện.

~~~text
context.clock.now()
context.random.nextInt()
~~~

### 16.3. Snapshot input

Nếu input đọc từ hệ thống ngoài trong nhiều thời điểm, cùng một lần chạy có thể thấy dữ liệu khác nhau. Có thể chụp snapshot hoặc ghi lại phiên bản dữ liệu đã đọc để tái hiện kết quả.

### 16.4. Execution trace

Trace có thể ghi execution ID và model version, input reference hoặc input hash, state transition, event nhận được, action bắt đầu và kết thúc, thời gian và kết quả, lỗi và retry.

Trace cần cân bằng giữa khả năng điều tra và chi phí lưu trữ, đồng thời tránh ghi dữ liệu nhạy cảm không cần thiết.

## 17. Quyền truy cập và bảo vệ trạng thái

State có thể chứa dữ liệu cá nhân, thông tin tài chính, token hoặc kết quả nghiệp vụ. Runtime phải kiểm soát ai có thể đọc và thay đổi từng phần.

### 17.1. Phân quyền theo capability

Thay vì cung cấp toàn bộ context cho mọi hàm DSL, runtime có thể truyền các capability cụ thể:

~~~text
capabilities = [
    ReadOrder,
    UpdateOrderStatus,
    SendNotification
]
~~~

Một rule chỉ có capability ReadOrder không thể tự ý ghi trạng thái đơn hàng.

### 17.2. Least privilege

Mỗi execution chỉ nên có quyền tối thiểu cần thiết. Không nên để một DSL script có thể truy cập mọi biến môi trường hoặc state store chỉ vì runtime đang giữ chúng.

### 17.3. Tenant isolation

Trong hệ thống nhiều khách hàng, mọi key hoặc truy vấn state phải được ràng buộc với tenant. Không dựa vào việc DSL tự truyền tenant ID đúng; runtime cần xác thực quyền ở tầng truy cập dữ liệu.

### 17.4. Secret state

Thông tin bí mật như access token không nên được đưa vào biến DSL thông thường nếu script không cần. Nếu cần, nên dùng secret reference hoặc capability để truy cập trong phạm vi được phép.

### 17.5. Log và dữ liệu nhạy cảm

Không ghi toàn bộ state vào log một cách mặc định. Có thể che, băm hoặc bỏ qua các trường nhạy cảm. Audit cần lưu đủ thông tin để giải thích hành động nhưng phải tuân theo chính sách dữ liệu.

### 17.6. Giới hạn tài nguyên

State có thể tăng không giới hạn qua vòng lặp hoặc session. Runtime cần giới hạn kích thước state, số biến và số phần tử collection, số event lưu, thời gian tồn tại session, số lần retry và dung lượng checkpoint.

## 18. State management trong interpreter

Interpreter thường đánh giá AST hoặc bytecode bằng một execution context. Mỗi lần thực thi biểu thức, nó đọc và cập nhật môi trường biến.

### 18.1. Environment

Một environment đơn giản có thể là map:

~~~text
Environment {
    parent
    bindings
}
~~~

Tra cứu biến:

~~~text
function lookup(environment, symbol):
    if symbol exists in environment.bindings:
        return environment.bindings[symbol]
    if environment.parent exists:
        return lookup(environment.parent, symbol)
    raise UnknownVariable(symbol)
~~~

### 18.2. Gán biến

~~~text
function assign(environment, symbol, value):
    binding = resolveWritableBinding(environment, symbol)
    checkType(binding.type, value.type)
    binding.value = value
~~~

Hàm gán cần biết binding thuộc scope nào và có cho phép ghi hay không. Nếu biến là immutable hoặc read-only input, runtime phải từ chối cập nhật.

### 18.3. Evaluation stack

Interpreter có thể dùng stack để lưu giá trị trung gian:

~~~text
PUSH order.quantity
PUSH order.unitPrice
MULTIPLY
STORE subtotal
~~~

Stack này khác với workflow state. Nó chỉ phục vụ quá trình đánh giá bytecode và thường không cần lưu bền vững.

### 18.4. State store bên ngoài

Nếu DSL hỗ trợ lưu workflow state, interpreter gọi API của state store thay vì giữ mọi thứ trong environment. Điều này cho phép lưu bền vững, transaction và concurrency control.

### 18.5. Giữ interpreter reentrant

Interpreter có thể được dùng đồng thời cho nhiều execution nếu model và các bảng tra cứu dùng chung là immutable. Mọi dữ liệu mutable của lần chạy phải nằm trong execution context riêng hoặc state store có đồng bộ.

## 19. Thiết kế API trạng thái cho DSL

Một DSL nên cung cấp cú pháp và API phản ánh rõ phạm vi cũng như tác dụng của thao tác state.

### 19.1. Biến cục bộ

~~~text
let subtotal = order.quantity * order.unitPrice
~~~

Biến chỉ tồn tại trong scope hiện tại.

### 19.2. State của workflow

~~~text
workflow.state.status = "WAITING_MANAGER"
workflow.state.retryCount = workflow.state.retryCount + 1
~~~

API này thể hiện dữ liệu có vòng đời dài hơn biến cục bộ. Runtime có thể yêu cầu transaction hoặc transition hợp lệ.

### 19.3. Đọc state có kiểu

~~~text
let retryCount: Integer = state.get("retryCount", default = 0)
~~~

Một API tốt nên cung cấp kiểu mong đợi hoặc schema để tránh đọc giá trị không kiểu.

### 19.4. Cập nhật qua transition

~~~text
workflow.transition(to = "APPROVED", reason = "Manager accepted")
~~~

Thay vì cho phép ghi tùy ý currentState, transition API có thể kiểm tra trạng thái nguồn, guard, quyền và ghi lịch sử.

### 19.5. Phân biệt lệnh và biểu thức

Đọc state thường là biểu thức tạo giá trị. Ghi state là câu lệnh hoặc action có tác dụng phụ. Phân biệt này giúp type checker và optimizer hiểu điều gì có thể được tính lại hoặc loại bỏ.

## 20. Quan sát và vận hành trạng thái

Quản lý state không kết thúc ở lúc code chạy. Người vận hành cần biết instance đang ở đâu, vì sao nó bị dừng và cách can thiệp an toàn.

### 20.1. State dashboard

Một giao diện vận hành có thể hiển thị workflow instance ID, trạng thái hiện tại, bước đang chờ, thời điểm cập nhật cuối, người hoặc dịch vụ chịu trách nhiệm, số lần retry và lỗi gần nhất.

### 20.2. Audit trail

Audit trail ghi ai hoặc thành phần nào đã thay đổi trạng thái, thay đổi gì, khi nào và theo lý do nào. Với quy trình phê duyệt, audit có thể là yêu cầu nghiệp vụ hoặc pháp lý.

### 20.3. Metrics

Các metric hữu ích:

- Số workflow ở mỗi trạng thái.
- Thời gian trung bình ở một trạng thái.
- Số lần retry.
- Tỷ lệ transition thất bại.
- Số conflict khi cập nhật state.
- Kích thước state store.
- Số execution bị treo hoặc quá hạn.

### 20.4. Correlation ID

Một workflow có thể gọi nhiều dịch vụ và tạo nhiều log. Correlation ID giúp liên kết các sự kiện thuộc cùng một quy trình. Execution ID, workflow instance ID và request ID có thể là các định danh khác nhau, cần phân biệt rõ.

### 20.5. Manual intervention

Nếu người vận hành có thể sửa state trực tiếp, thao tác đó cần quyền rõ ràng, lý do và người thực hiện, kiểm tra invariant, audit event và cơ chế rollback hoặc compensation nếu cần.

Không nên cho phép sửa tùy ý một field trạng thái quan trọng mà bỏ qua state machine.

## 21. Những lỗi thiết kế thường gặp

### 21.1. Dùng global mutable state cho mọi execution

Các lần chạy có thể ghi đè dữ liệu của nhau. Hãy tạo execution context riêng và chỉ chia sẻ những thành phần được thiết kế an toàn.

### 21.2. Không phân biệt biến cục bộ và workflow state

Biến tạm có thể bị mất khi runtime dừng, trong khi workflow state cần được lưu. Hãy quy định vòng đời và storage riêng.

### 21.3. Cập nhật trạng thái mà không kiểm tra transition

Một workflow có thể nhảy từ NEW thẳng sang COMPLETED dù các bước bắt buộc chưa chạy. Dùng state machine và guard để kiểm soát chuyển đổi.

### 21.4. Ghi nhiều phần state không nguyên tử

Nếu một phần cập nhật thành công và phần khác thất bại, state có thể không nhất quán. Xác định transaction boundary và invariant.

### 21.5. Retry action không idempotent

Gửi tiền hoặc gửi email lặp lại có thể gây hậu quả. Cần idempotency key, deduplication hoặc compensation.

### 21.6. Giữ lock trong lúc chờ sự kiện dài hạn

Lock và transaction bị giữ quá lâu gây nghẽn hệ thống. Hãy lưu trạng thái chờ rồi giải phóng tài nguyên.

### 21.7. Không version hóa state

Model thay đổi nhưng state cũ không được migrate hoặc xác định version, khiến resume diễn giải dữ liệu sai.

### 21.8. Lưu toàn bộ context mà không lọc

Context có thể chứa secret hoặc dữ liệu lớn. Chỉ serialize những trường cần cho resume và áp dụng chính sách bảo vệ.

### 21.9. Thiếu audit và trace

Khi state thay đổi bất ngờ, không có lịch sử thì khó xác định nguyên nhân. Ghi transition và correlation ID phù hợp.

### 21.10. Cho phép ghi state qua mọi API

Nếu hàm bất kỳ có thể thay đổi state, optimizer và người viết DSL khó dự đoán tác dụng phụ. Tách capability và phân loại API đọc/ghi.

## 22. Kiểm thử quản lý trạng thái

Kiểm thử state cần bao phủ vòng đời, tính nhất quán, lỗi và thực thi đồng thời.

### 22.1. Kiểm thử scope

- Biến cục bộ không truy cập được ngoài block.
- Shadowing tuân thủ quy tắc.
- Biến capture có giá trị đúng khi closure chạy sau.
- Biến của execution A không rò sang execution B.

### 22.2. Kiểm thử transition

- Transition hợp lệ được áp dụng.
- Transition không hợp lệ bị từ chối.
- Guard false không thay đổi state.
- Entry/exit action được thực hiện đúng số lần.
- Lỗi giữa transition không để state ở trạng thái nửa cập nhật.

### 22.3. Kiểm thử persistence

- State đã commit vẫn tồn tại sau restart.
- Snapshot có version phù hợp.
- Replay event tạo lại cùng state.
- Migration chuyển state cũ đúng quy tắc.

### 22.4. Kiểm thử transaction

- Commit ghi đủ mọi thay đổi.
- Rollback không để lại cập nhật một phần.
- Conflict được phát hiện.
- Outbox event được ghi cùng transaction với state liên quan.

### 22.5. Kiểm thử đồng thời

- Hai execution cùng cập nhật counter.
- Nhiều message đến cùng workflow instance.
- CAS thất bại khi version thay đổi.
- Lock timeout và deadlock được xử lý.
- State của tenant này không đọc được từ tenant khác.

### 22.6. Kiểm thử retry và recovery

- Retry không lặp tác dụng phụ.
- Hết retry chuyển sang trạng thái lỗi phù hợp.
- Resume từ checkpoint tiếp tục đúng bước.
- Crash sau commit nhưng trước acknowledgment không tạo xử lý trùng.

### 22.7. Kiểm thử tính xác định

Với cùng model, input, snapshot và clock giả, kết quả phải có thể tái hiện. Nếu runtime phụ thuộc dữ liệu ngoài, kiểm thử cần mock hoặc ghi lại dữ liệu đó.

### 22.8. Property-based testing

Có thể sinh chuỗi transition ngẫu nhiên và kiểm tra invariant, ví dụ state luôn thuộc tập trạng thái đã khai báo, không có transition ngoài danh sách, retry count không vượt giới hạn và một execution không có hai phiên bản current state cùng được commit.

### 22.9. Kiểm thử tải

Đo thông lượng, độ trễ, kích thước state, số conflict và thời gian khôi phục khi có nhiều execution. Một thiết kế đúng ở tải thấp có thể gặp race hoặc nghẽn ở tải cao.

## 23. Ví dụ tổng hợp: workflow phê duyệt đơn hàng

Xét DSL:

~~~text
workflow "purchase_approval" {
    initialState = "SUBMITTED"

    state SUBMITTED
    state WAITING_MANAGER
    state APPROVED
    state REJECTED
    state COMPLETED

    on event Submit:
        set request.submittedAt = clock.now()
        transition to SUBMITTED

    in SUBMITTED:
        if request.amount <= 1000000:
            transition to APPROVED
        else:
            transition to WAITING_MANAGER

    in WAITING_MANAGER:
        wait for event ManagerDecision

        if event.approved:
            transition to APPROVED
        else:
            transition to REJECTED

    in APPROVED:
        transaction:
            reserveBudget(request.amount)
            createPurchaseOrder(request)
            transition to COMPLETED

    in REJECTED:
        notify(request.owner, "Request rejected")
}
~~~

### 23.1. Model và instance state

Workflow model mô tả các trạng thái và transition. Mỗi yêu cầu mua hàng tạo một workflow instance có:

~~~text
instanceId = "WF-2048"
currentState = "SUBMITTED"
variables = {
    requestId = "REQ-2048",
    amount = 750000,
    owner = "user-17"
}
version = 1
~~~

Hai yêu cầu khác nhau dùng cùng workflow model nhưng có state riêng.

### 23.2. Tạo và cập nhật state

Khi Submit, runtime tạo instance và ghi event. Nếu amount không vượt 1000000, workflow chuyển sang APPROVED. Nếu lớn hơn, nó chuyển sang WAITING_MANAGER.

### 23.3. Chờ sự kiện

Ở WAITING_MANAGER, workflow có thể tạm dừng. Runtime lưu checkpoint, giải phóng worker và chờ event ManagerDecision. Khi event đến, execution được khôi phục với state mới nhất.

### 23.4. Transaction

Trong APPROVED, reserveBudget và createPurchaseOrder cần có transaction boundary hoặc quy trình bù phù hợp. Nếu một dịch vụ ngoài không tham gia transaction, cần dùng outbox hoặc saga.

### 23.5. Retry

Nếu createPurchaseOrder timeout, runtime cần biết request đã được tạo ở hệ thống đích hay chưa. Idempotency key dựa trên workflow instance và action ID có thể ngăn tạo đơn trùng.

### 23.6. Audit

Mỗi transition ghi lại trạng thái trước và sau, event kích hoạt, actor hoặc service, thời điểm, version và lý do hoặc correlation ID.

Nhờ đó, người vận hành có thể giải thích vì sao yêu cầu chuyển từ WAITING_MANAGER sang APPROVED.

## 24. Quy trình thiết kế state management cho DSL

Khi xây runtime, có thể thực hiện theo các bước:

1. Liệt kê mọi loại state mà DSL cần: local, execution, session, workflow và runtime.
2. Xác định scope, lifetime và owner cho từng loại.
3. Phân biệt dữ liệu chỉ đọc, mutable state và immutable snapshot.
4. Thiết kế execution context và scope stack.
5. Định nghĩa state machine, transition và guard nếu có quy trình.
6. Chọn state store và API đọc/ghi có kiểu.
7. Xác định transaction boundary và invariant cần bảo vệ.
8. Thiết kế concurrency control: isolation, lock, CAS hoặc actor.
9. Quy định persistence, snapshot, event log, checkpoint và migration.
10. Xác định retry, idempotency, compensation và recovery.
11. Thiết kế quyền truy cập, tenant isolation và chính sách log.
12. Bổ sung trace, audit và metric.
13. Viết kiểm thử scope, transition, concurrency, crash và resume.
14. Đo hiệu năng, dung lượng state và thời gian khôi phục trên workload đại diện.

## 25. Bài tập tự kiểm tra

### Bài 1: Phân loại trạng thái

Một DSL workflow có biến total, currentStep, retryCount và schemaCache. Hãy phân loại phạm vi và vòng đời phù hợp cho từng giá trị. Giải thích vì sao schemaCache không nên chứa dữ liệu riêng của workflow.

### Bài 2: Execution context

Hãy đề xuất cấu trúc ExecutionContext cho một lần chạy rule. Phân biệt model, input, local variables, diagnostics và quyền truy cập.

### Bài 3: Scope và shadowing

Cho đoạn DSL:

~~~text
let status = "NEW"
if urgent:
    let status = "PRIORITY"
    process(status)
log(status)
~~~

Nếu DSL hỗ trợ lexical scope và shadowing, mỗi lời gọi đọc giá trị nào? Runtime cần lưu binding ra sao?

### Bài 4: State transition

Một đơn hàng có các trạng thái NEW, PAID, SHIPPED và CANCELLED. Hãy đề xuất transition hợp lệ và guard cho thao tác chuyển sang SHIPPED.

### Bài 5: Mutable và immutable

Một workflow state được nhiều worker đọc đồng thời. Hãy so sánh cập nhật mutable tại chỗ với snapshot immutable và CAS. Nêu ưu và nhược điểm.

### Bài 6: Transaction

Một action cập nhật số dư hai tài khoản. Hãy giải thích vì sao hai phép ghi cần cùng transaction và điều gì có thể xảy ra nếu chỉ một phép ghi thành công.

### Bài 7: Retry và idempotency

Một action gửi yêu cầu thanh toán bị timeout. Runtime không biết hệ thống thanh toán đã xử lý hay chưa. Hãy thiết kế cách retry an toàn.

### Bài 8: Checkpoint và resume

Một workflow chờ người quản lý phê duyệt trong nhiều giờ. Hãy xác định state nào cần lưu, resource nào cần giải phóng và cách tiếp tục khi event đến.

### Bài 9: Concurrency

Hai execution cùng tăng một bộ đếm. Hãy minh họa lost update và đề xuất ít nhất hai cách ngăn lỗi.

### Bài 10: Kiểm thử và audit

Hãy lập kế hoạch kiểm thử cho workflow phê duyệt gồm transition, persistence, retry, crash recovery và audit trail. Nêu invariant quan trọng cần kiểm tra.

## Kết luận

Quản lý trạng thái là trách nhiệm cốt lõi của runtime DSL khi chương trình cần giữ dữ liệu qua nhiều bước hoặc nhiều lần tương tác. Thiết kế tốt phân biệt model, input và runtime state; xác định rõ scope, lifetime và owner; dùng execution context riêng cho mỗi lần chạy; và kiểm soát thay đổi thông qua state transition hoặc API có kiểu. Với quy trình kéo dài, runtime cần persistence, transaction, checkpoint, retry và recovery. Khi nhiều execution hoạt động đồng thời, phải có isolation và cơ chế chống lost update. State cũng cần được bảo vệ bằng quyền tối thiểu, tenant isolation, audit và giới hạn tài nguyên. Những quy tắc này giúp DSL thực thi ổn định, có thể khôi phục và dễ giải thích ngay cả khi quy trình phức tạp hoặc hệ thống gặp sự cố.
