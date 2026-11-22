# Trình gỡ lỗi

Khi một chương trình viết bằng ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL) cho kết quả không như mong đợi, người phát triển cần biết chương trình đã đi qua những bước nào, giá trị của các biến thay đổi ra sao và điều kiện nào khiến một nhánh được chọn. Đọc lại mã nguồn hoặc thêm các câu lệnh ghi log có thể giúp tìm nguyên nhân, nhưng thường mất thời gian và khó theo dõi khi chương trình có nhiều bước, scope lồng nhau hoặc lời gọi dịch vụ bên ngoài. **Trình gỡ lỗi (debugger)** là công cụ cho phép quan sát và điều khiển quá trình thực thi một cách có hệ thống.

Với DSL, debugger cần hiểu cấu trúc và ngữ nghĩa của ngôn ngữ. Nó phải liên kết vị trí trong mã DSL với node AST hoặc lệnh đã biên dịch, hiển thị biến theo scope, giải thích bước thực thi, quản lý breakpoint và trình bày lỗi tại đúng vị trí nguồn. Nếu DSL mô tả workflow, query, quy tắc nghiệp vụ hoặc mô hình dữ liệu, debugger còn cần thể hiện các khái niệm miền như entity, step, action, event và transaction.

Debugger không chỉ dành cho người viết interpreter. Nó là một phần của bộ công cụ phát triển DSL, phối hợp với parser, runtime, source map, symbol table, editor và giao thức debug. Một debugger tốt giúp người dùng hiểu được vì sao chương trình có hành vi hiện tại, tái hiện lỗi và xác minh cách sửa.

Bài học này trình bày vai trò và kiến trúc của debugger cho DSL, breakpoint, stepping, call stack, inspection, watch expression, source mapping, debug adapter, xử lý lỗi, thực thi workflow, bảo mật, hiệu năng và cách kiểm thử công cụ.

## 1. Trình gỡ lỗi là gì?

Debugger là công cụ hỗ trợ quan sát trạng thái chương trình khi chạy và điều khiển tiến trình thực thi để tìm nguyên nhân của lỗi hoặc hành vi không mong muốn.

Các chức năng cơ bản thường gồm:

- Đặt và gỡ breakpoint.
- Chạy, tạm dừng và tiếp tục chương trình.
- Thực thi từng bước.
- Quan sát call stack hoặc execution stack.
- Xem giá trị biến và biểu thức.
- Theo dõi thay đổi trạng thái.
- Xem lỗi, exception và diagnostic runtime.
- Điều hướng từ trạng thái runtime về mã nguồn.
- Tiếp tục thực thi sau khi kiểm tra.

Với DSL, các chức năng này cần phản ánh mô hình thực thi riêng. Ví dụ, một workflow có thể có step đang chạy, step chờ, step đã hoàn tất và step thất bại. Một debugger cho DSL workflow nên hiển thị những trạng thái này thay vì chỉ trình bày một stack frame chung chung.

### 1.1. Debugging khác với logging

Logging ghi lại sự kiện hoặc giá trị khi chương trình chạy. Debugger cho phép người dùng dừng tại một điểm, kiểm tra trạng thái hiện tại và điều khiển bước tiếp theo.

| Công cụ | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| Logging | Ghi sự kiện và dữ liệu vào log | Theo dõi môi trường production, lịch sử chạy |
| Tracing | Ghi quan hệ thời gian và luồng qua nhiều thành phần | Phân tích workflow hoặc hệ thống phân tán |
| Debugger | Tạm dừng, kiểm tra và điều khiển thực thi | Điều tra lỗi có thể tái hiện, hiểu logic |
| Profiler | Đo thời gian, CPU, bộ nhớ và tài nguyên | Tìm nút thắt hiệu năng |

Các công cụ có thể bổ sung cho nhau. Log cho biết điều gì đã xảy ra trước đó; trace cho thấy quan hệ giữa các bước; debugger cho phép dừng và xem trạng thái tại một thời điểm cụ thể.

### 1.2. Debugger cho DSL khác debugger cho ngôn ngữ host

Một DSL thường chạy bên trong interpreter, runtime hoặc engine được viết bằng Java, Kotlin, JavaScript hay ngôn ngữ khác. Nếu chỉ dùng debugger của host language, người dùng có thể nhìn thấy stack frame của interpreter nhưng không hiểu dòng DSL nào đang được đánh giá.

Ví dụ, debugger Java có thể dừng tại phương thức evaluateBinaryExpression. Người dùng DSL cần biết rằng chương trình đang thực hiện biểu thức:

~~~text
order.total * taxRate
~~~

và giá trị hiện tại của order.total là 250000, taxRate là 0.1.

Debugger DSL cần cung cấp lớp trừu tượng phù hợp với người viết DSL, đồng thời có thể giữ khả năng đi sâu vào runtime host khi cần cho nhà phát triển công cụ.

### 1.3. Debugging và tính đúng đắn của chương trình

Debugger giúp quan sát và điều tra, nhưng không tự chứng minh chương trình đúng. Một chương trình chạy qua breakpoint mà không có exception vẫn có thể vi phạm quy tắc nghiệp vụ. Cần kết hợp debugging với validation, test, assertion và kiểm tra dữ liệu.

## 2. Kiến trúc debugger cho DSL

Một kiến trúc debugger thường gồm editor hoặc debug client, debug adapter, runtime instrumented và nguồn thông tin ánh xạ về DSL.

~~~text
Người dùng
    |
    v
DSL Editor / Debug UI
    |
    v
Debug Client
    |
    | Debug Protocol
    v
Debug Adapter
    |
    +--> Breakpoint Manager
    +--> Stack / Scope Inspector
    +--> Variable Evaluator
    +--> Source Mapper
    |
    v
DSL Runtime / Interpreter
    |
    +--> Execution Controller
    +--> Runtime Frames
    +--> Event and Error Hooks
    +--> Source Locations
    |
    v
DSL Program
~~~

Editor hiển thị giao diện. Debug client gửi yêu cầu như launch, set breakpoint, step và inspect. Debug adapter chuyển yêu cầu thành thao tác của runtime. Runtime phát sự kiện khi đến điểm dừng, tạo frame hoặc phát sinh lỗi.

### 2.1. Thành phần của hệ thống

**Debug client:** giao diện người dùng, thường là IDE hoặc editor. Nó hiển thị breakpoint, call stack, biến, watch expressions và trạng thái chạy.

**Debug adapter:** lớp chuyển đổi giữa giao thức debug và API riêng của runtime. Nó quản lý phiên debug, yêu cầu của client và sự kiện từ runtime.

**Execution controller:** thành phần có thể tạm dừng, tiếp tục hoặc chạy từng bước. Nó cần phối hợp với scheduler nếu DSL có workflow hoặc async execution.

**Breakpoint manager:** lưu breakpoint theo source location, điều kiện, hit count và trạng thái đã xác minh.

**Frame và scope inspector:** cung cấp stack frame, biến cục bộ, tham số, biến môi trường và đối tượng hiện tại.

**Source mapper:** ánh xạ mã thực thi, node AST hoặc mã sinh về file và range trong DSL.

**Variable evaluator:** định dạng và lấy giá trị biến hoặc biểu thức trong context của frame được chọn.

### 2.2. Interpreter và debugger

Interpreter thường duyệt AST và đánh giá node. Đây là vị trí tự nhiên để phát debug event:

~~~text
evaluate(node, context):
  notifyBeforeNode(node, context)
  result = evaluateNode(node, context)
  notifyAfterNode(node, context, result)
  return result
~~~

Không nhất thiết phải phát event ở mọi node. Debugger có thể chỉ dừng tại statement, action hoặc vị trí có thể thực thi. Phát event quá dày có thể làm runtime chậm đáng kể.

### 2.3. Debugger cho mã được biên dịch

Nếu DSL được biên dịch thành bytecode hoặc mã host, debugger cần source map hoặc debug metadata để liên kết instruction với mã DSL. Nếu mã sinh ra không giữ thông tin nguồn, breakpoint có thể dừng ở dòng Java hoặc JavaScript mà người dùng DSL không nhìn thấy.

### 2.4. Phiên debug

Một phiên debug có thể có các trạng thái:

~~~text
Created
  |
  v
Initialized
  |
  v
Running <------+
  |            |
  v            |
Paused         |
  |            |
  +-- Resume --+
  |
  v
Terminated
~~~

Phiên cần quản lý process hoặc runtime instance, breakpoint, thread/task, frame, source map và trạng thái kết thúc. Khi phiên bị hủy, tài nguyên liên quan phải được giải phóng.

## 3. Chuẩn bị runtime để hỗ trợ debugging

Debugger chỉ hoạt động tốt nếu runtime cung cấp đủ điểm quan sát và điều khiển.

### 3.1. Execution event

Runtime có thể phát các sự kiện:

- StatementStarted.
- StatementCompleted.
- ExpressionEvaluated.
- FunctionEntered.
- FunctionExited.
- StepStarted.
- StepCompleted.
- BreakpointReached.
- ExceptionRaised.
- WorkflowSuspended.
- WorkflowResumed.
- ExecutionTerminated.

Không phải sự kiện nào cũng cần gửi đến client. Adapter có thể lọc và tổng hợp để tránh tạo quá nhiều thông điệp.

### 3.2. Source location trên node

Parser nên giữ source span cho AST node:

~~~text
SourceSpan
  documentUri
  startLine
  startColumn
  endLine
  endColumn
~~~

Runtime mang source span theo node hoặc instruction. Khi dừng, debugger dùng thông tin này để highlight đoạn DSL tương ứng.

Cần thống nhất cách đánh số dòng, cột, encoding và range với editor hoặc debug protocol. Một số giao thức dùng chỉ số bắt đầu từ 0 và cột theo UTF-16 code unit; không được tự giả định quy ước.

### 3.3. Execution frame

Một frame có thể lưu:

~~~text
ExecutionFrame
  frameId
  functionOrStep
  sourceLocation
  localEnvironment
  parentFrame
  currentObject
  instructionPosition
~~~

Frame đại diện cho một lần gọi function, operation hoặc một đơn vị thực thi tương đương. Nó cho phép debugger hiển thị biến và vị trí đang chạy.

### 3.4. Debug hooks

Có thể định nghĩa interface để runtime không phụ thuộc trực tiếp vào giao diện editor:

~~~java
interface DebugHooks {
    void beforeStatement(
        RuntimeFrame frame,
        SourceLocation location
    );

    void afterStatement(
        RuntimeFrame frame,
        SourceLocation location
    );

    void onException(
        RuntimeFrame frame,
        Throwable error,
        SourceLocation location
    );
}
~~~

Khi không có debugger, implementation có thể là no-op. Khi bật debug mode, runtime gắn adapter hoặc listener phù hợp.

### 3.5. Chỉ bật instrumentation cần thiết

Một runtime có thể chạy ở chế độ thông thường và chế độ debug. Debug mode có thể giữ nhiều metadata hơn, tạo frame snapshot hoặc phát event chi tiết. Nên tránh chi phí này trong mọi lần chạy nếu ứng dụng không cần debugging.

## 4. Breakpoint

Breakpoint là điểm mà runtime sẽ tạm dừng khi quá trình thực thi đi đến vị trí được chỉ định và điều kiện breakpoint được thỏa mãn.

Người dùng thường đặt breakpoint bằng cách nhấp vào lề editor cạnh một dòng có thể thực thi.

Ví dụ DSL:

~~~text
workflow processOrder(order) {
  validate(order)
  reserveInventory(order)
  chargePayment(order)
  publishConfirmation(order)
}
~~~

Nếu đặt breakpoint tại chargePayment, debugger tạm dừng trước hoặc tại thời điểm action này bắt đầu, theo semantics đã định nghĩa.

### 4.1. Breakpoint theo dòng và theo node

Breakpoint theo dòng gắn với line number. Tuy nhiên, một dòng có thể chứa nhiều statement hoặc không chứa statement nào.

Ví dụ:

~~~text
if order.total > 0 { chargePayment(order) }
~~~

Một dòng có cả điều kiện và action. Debugger cần ánh xạ breakpoint đến node thực thi cụ thể hoặc chọn vị trí gần nhất có thể dừng.

Breakpoint theo node hoặc source range chính xác hơn vì nó gắn với một AST node hoặc instruction. Editor vẫn có thể hiển thị biểu tượng ở lề dòng.

### 4.2. Breakpoint được xác minh

Khi người dùng đặt breakpoint, adapter cần xác minh vị trí đó có thể dừng được không.

Breakpoint có thể ở các trạng thái:

- Verified: runtime đã gắn được breakpoint.
- Pending: tài liệu hoặc source map chưa sẵn sàng.
- Unverified: vị trí không thực thi được hoặc không ánh xạ được.
- Disabled: breakpoint bị tắt.

Editor nên cho biết breakpoint không được xác minh thay vì hiển thị như thể nó hoạt động.

### 4.3. Conditional breakpoint

Conditional breakpoint chỉ dừng khi một biểu thức điều kiện đúng.

Ví dụ, chỉ dừng khi đơn hàng có tổng tiền lớn hơn 1.000.000:

~~~text
order.total > 1000000
~~~

Điều kiện được đánh giá trong context của frame tại breakpoint. Nó nên là biểu thức thuần hoặc có giới hạn tác động phụ. Nếu điều kiện gọi action hoặc thay đổi trạng thái, chính debugger có thể làm thay đổi chương trình đang quan sát.

### 4.4. Hit count

Hit count cho phép dừng sau một số lần vị trí được thực thi.

Ví dụ:

- Dừng ở lần thứ 10.
- Dừng khi số lần chạy lớn hơn 100.
- Dừng mỗi 50 lần.

Hit count hữu ích khi lỗi chỉ xuất hiện sau nhiều vòng lặp hoặc một số lần xử lý bản ghi.

### 4.5. Logpoint

Logpoint ghi một thông điệp khi chương trình đi qua vị trí, nhưng không tạm dừng. Nó kết hợp tính tiện lợi của logging với vị trí được xác định bằng source mapping.

Ví dụ:

~~~text
Order {order.id} total={order.total}
~~~

Logpoint nên hỗ trợ placeholder có kiểm soát và không thực thi biểu thức có tác động phụ ngoài ý muốn.

### 4.6. Breakpoint theo exception hoặc diagnostic

Debugger có thể dừng khi exception được ném, khi một loại diagnostic runtime xuất hiện hoặc khi một workflow step thất bại.

Có thể cho phép chọn:

- Dừng khi mọi exception được ném.
- Chỉ dừng với exception chưa được xử lý.
- Dừng với một loại domain error cụ thể.
- Dừng khi constraint bị vi phạm.
- Dừng khi action trả về trạng thái thất bại.

Cần phân biệt exception được bắt bên trong chương trình với exception thoát ra ngoài.

### 4.7. Breakpoint trong mã sinh tự động

Nếu DSL sinh mã, breakpoint nên gắn với source DSL. Mã sinh có thể có nhiều dòng cho một node nguồn hoặc một dòng nguồn sinh nhiều instruction. Source map phải xác định vị trí nào có thể dừng và cách highlight.

## 5. Điều khiển thực thi: Continue và Step

Debugger cung cấp các lệnh điều khiển để người dùng đi qua chương trình.

### 5.1. Continue

Continue tiếp tục thực thi cho đến breakpoint tiếp theo, exception được cấu hình hoặc kết thúc chương trình.

Nếu runtime có nhiều task, continue có thể tiếp tục tất cả task hoặc chỉ task đang được chọn tùy execution model.

### 5.2. Step Over

Step Over thực thi statement hiện tại. Nếu statement gọi một function, debugger không đi vào từng statement bên trong function mà dừng ở vị trí tiếp theo trong caller.

Ví dụ:

~~~text
calculateTotal(order)
publishResult()
~~~

Step Over tại calculateTotal sẽ chạy function đó và dừng ở publishResult, nếu không có breakpoint hoặc exception bên trong.

### 5.3. Step Into

Step Into đi vào function hoặc operation được gọi tại vị trí hiện tại.

Nếu đang ở:

~~~text
calculateTotal(order)
~~~

Step Into có thể mở frame của calculateTotal để người dùng xem các phép tính bên trong.

Nếu lời gọi đi vào thư viện hoặc action native không có source DSL, debugger cần chọn cách xử lý: hiển thị frame native, bỏ qua implementation hoặc dừng ở ranh giới lời gọi.

### 5.4. Step Out

Step Out tiếp tục cho đến khi frame hiện tại kết thúc và quay về caller.

Nó hữu ích khi người dùng đã đi sâu vào một function nhưng muốn quay lại luồng chính.

### 5.5. Step Back

Step Back cho phép quay lại trạng thái thực thi trước đó. Đây là tính năng khó hơn stepping thông thường vì runtime cần lưu snapshot hoặc lịch sử sự kiện đủ để khôi phục.

Không phải runtime nào cũng hỗ trợ reverse debugging. Nếu không có khả năng khôi phục trạng thái, UI không nên hiển thị Step Back như một lệnh có thể thực hiện.

### 5.6. Step theo khái niệm DSL

Một DSL workflow có thể cung cấp stepping ở mức domain:

- Step Into Action.
- Step Over Workflow Step.
- Step Out of Sub-workflow.
- Continue to Next Event.
- Pause Before Commit.

Đây là mức trừu tượng hữu ích hơn việc chỉ đi qua từng node AST, đặc biệt khi người dùng quan tâm đến tiến trình nghiệp vụ.

## 6. Call stack và execution stack

Call stack hiển thị chuỗi lời gọi đang hoạt động tại thời điểm tạm dừng.

Ví dụ:

~~~text
processOrder(order)
  -> calculateTotal(order)
      -> calculateTax(total, rate)
~~~

Frame trên cùng thường là vị trí đang thực thi. Người dùng có thể chọn frame khác để xem biến trong scope của frame đó.

### 6.1. Nội dung của một frame

Một frame có thể hiển thị:

- Tên function, operation hoặc workflow step.
- File và dòng nguồn.
- Tham số.
- Biến cục bộ.
- Đối tượng hiện tại.
- Caller frame.
- Trạng thái async hoặc suspended.
- Giá trị trả về nếu runtime giữ được.

### 6.2. Frame của interpreter

Nếu DSL chạy trong interpreter, host stack có thể chỉ có vài phương thức lặp lại:

~~~text
Interpreter.evaluate
Interpreter.evaluate
Interpreter.invoke
Interpreter.evaluate
~~~

Đây không phải stack có ích cho người viết DSL. Runtime nên duy trì logical frame riêng, phản ánh function và workflow trong chương trình DSL.

### 6.3. Frame của workflow

Workflow có thể không tương ứng trực tiếp với call stack truyền thống. Một step có thể được lên lịch, tạm dừng chờ sự kiện rồi tiếp tục sau đó.

Debugger có thể hiển thị execution tree:

~~~text
processOrder
  |
  +-- validateOrder       Completed
  |
  +-- reserveInventory    Completed
  |
  +-- chargePayment      Paused
  |
  +-- publishReceipt      Pending
~~~

Execution tree giúp người dùng hiểu tiến trình ngay cả khi không có call stack tuyến tính.

### 6.4. Stack frame và async task

Một workflow có thể tạo task song song. Mỗi task có logical stack riêng và có thể có quan hệ parent-child.

Debugger cần cho người dùng chọn task đang quan sát, hiển thị trạng thái của các task khác và tránh nhầm lẫn giữa frame của task này với task khác.

### 6.5. Stack depth

Đệ quy hoặc gọi lồng sâu có thể tạo stack lớn. UI có thể giới hạn số frame hiển thị ban đầu, cho phép mở rộng khi cần. Runtime cần có giới hạn độ sâu hoặc cơ chế phát hiện recursion runaway nếu DSL có thể chạy chương trình không tin cậy.

## 7. Quan sát biến và scope

Variable inspection cho phép người dùng xem giá trị hiện tại của biến, tham số và thuộc tính trong frame đã chọn.

Ví dụ:

~~~text
Locals
  orderId: "ORD-1024"
  subtotal: 250000
  taxRate: 0.1
  total: 275000

Current object
  Order
    status: "PENDING"
    items: 3
~~~

### 7.1. Local variables

Biến cục bộ chỉ tồn tại trong scope hoặc frame hiện tại. Khi chọn frame khác, danh sách locals phải thay đổi theo frame đó.

### 7.2. Closure và captured variables

Một function có thể sử dụng biến từ scope khai báo. Debugger nên phân biệt local variables với captured variables nếu DSL hỗ trợ closure.

Ví dụ:

~~~text
function makeThreshold(limit) {
  return function(order) {
    return order.total >= limit
  }
}
~~~

Trong closure, limit có thể không phải local của function con nhưng vẫn được giữ trong captured environment.

### 7.3. Global và module variables

Biến ở scope module hoặc môi trường runtime có thể được hiển thị riêng. Không nên trộn mọi binding thành một danh sách không phân biệt vì người dùng khó hiểu biến được khai báo ở đâu.

### 7.4. Current object

Với DSL có this hoặc context receiver, debugger nên hiển thị đối tượng hiện tại. Người dùng cần biết property được truy cập từ object nào khi có nhiều context lồng nhau.

### 7.5. Lazy value và computed property

Một số giá trị chỉ được tính khi truy cập. Khi debugger mở rộng một biến, việc gọi getter có thể kích hoạt tính toán hoặc I/O. Runtime cần phân biệt:

- Giá trị đã có sẵn.
- Giá trị được tính thuần.
- Giá trị lazy chưa đánh giá.
- Property cần gọi service hoặc truy cập dữ liệu.

Debugger nên tránh kích hoạt tác động phụ chỉ vì người dùng mở rộng cây biến.

### 7.6. Object graph lớn

Một biến có thể tham chiếu đến object lớn hoặc collection hàng nghìn phần tử. UI nên hỗ trợ lazy expansion, phân trang và giới hạn số phần tử hiển thị. Không nên serialize toàn bộ object graph trong một phản hồi.

### 7.7. Giá trị nhạy cảm

Debugger có thể hiển thị email, token, thông tin cá nhân hoặc dữ liệu thanh toán. Runtime và adapter cần áp dụng chính sách che giấu hoặc từ chối inspection theo quyền của người dùng.

## 8. Watch expressions và Evaluate

Watch expression cho phép người dùng theo dõi một biểu thức trong khi chương trình chạy hoặc khi đang tạm dừng.

Ví dụ:

~~~text
order.total
order.items.size()
order.total + shippingFee
~~~

Khi debugger tạm dừng, các biểu thức được đánh giá trong context của frame đã chọn.

### 8.1. Watch expression

Watch list thường giữ các biểu thức do người dùng thêm. Mỗi lần dừng, debugger có thể cập nhật kết quả.

Một watch có thể có trạng thái:

- Evaluated: đã tính được giá trị.
- Error: biểu thức không hợp lệ hoặc phát sinh lỗi.
- Unavailable: không có context phù hợp.
- Pending: đang chờ kết quả.
- Disabled: người dùng tạm tắt watch.

### 8.2. Evaluate trong console

Debug console cho phép nhập biểu thức hoặc câu lệnh để đánh giá trong context hiện tại.

Cần phân biệt:

- Evaluate expression: chỉ tính giá trị.
- Execute statement: có thể thay đổi trạng thái.
- REPL command: lệnh điều khiển riêng của debugger.

Không nên coi mọi nội dung nhập vào console là expression thuần. Một câu lệnh gán hoặc action có thể thay đổi chương trình đang debug.

### 8.3. Side effects trong Evaluate

Ví dụ:

~~~text
order.total = 0
sendPayment(order)
~~~

Nếu debugger cho phép thực thi các câu lệnh này, trạng thái chương trình có thể thay đổi. Một số debugger cung cấp chế độ read-only evaluation; số khác cho phép mutation có cảnh báo hoặc xác nhận.

Chính sách cần rõ ràng và nhất quán. Watch expressions nên ưu tiên biểu thức thuần; console có thể cung cấp khả năng thay đổi trạng thái riêng biệt.

### 8.4. Context của Evaluate

Biểu thức phải được đánh giá trong frame và scope người dùng đang chọn. Nếu frame đã kết thúc hoặc task đã bị hủy, debugger cần báo context không còn khả dụng.

### 8.5. Timeout và giới hạn

Một watch expression có thể gọi hàm tốn thời gian hoặc duyệt collection lớn. Debugger nên giới hạn thời gian, độ sâu và tài nguyên cho evaluate. Không để một watch làm treo toàn bộ phiên debug.

## 9. Source mapping và debug metadata

Source mapping liên kết vị trí thực thi với vị trí trong mã DSL. Đây là thành phần đặc biệt quan trọng khi DSL được biên dịch hoặc chuyển đổi sang mã host.

### 9.1. AST interpreter

Với interpreter duyệt AST, mỗi node có source span. Khi node bắt đầu được đánh giá, runtime có thể phát vị trí đó trực tiếp.

### 9.2. Generated code

Giả sử DSL:

~~~text
workflow processOrder(order) {
  chargePayment(order)
}
~~~

được sinh thành Java:

~~~java
public void processOrder(Order order) {
    paymentService.charge(order);
}
~~~

Một lỗi tại dòng gọi paymentService cần được hiển thị ở dòng chargePayment trong DSL. Debug metadata có thể ánh xạ range của Java hoặc instruction về source span của DSL.

### 9.3. Source map

Một mapping record có thể có dạng:

~~~text
GeneratedLocation
  generatedFile
  generatedRange
  sourceFile
  sourceRange
  sourceNodeId
~~~

Một source node có thể sinh nhiều đoạn mã; nhiều node nguồn có thể cùng đóng góp vào một đoạn generated code. Mapping vì vậy có thể là quan hệ một-nhiều hoặc nhiều-một.

### 9.4. Breakpoint resolution

Khi client gửi breakpoint tại dòng DSL, adapter cần:

1. Xác định node có thể thực thi ở dòng đó.
2. Tìm instruction hoặc runtime location tương ứng.
3. Gắn breakpoint.
4. Trả về trạng thái verified và vị trí thực tế nếu khác yêu cầu.

Nếu dòng chỉ có comment hoặc declaration không tạo instruction, adapter có thể chuyển breakpoint đến statement tiếp theo theo quy tắc được tài liệu hóa, hoặc đánh dấu không hợp lệ.

### 9.5. Source map và phiên bản

Source map cần khớp chính xác với mã được thực thi. Nếu DSL file thay đổi sau khi biên dịch nhưng runtime vẫn chạy artifact cũ, breakpoint có thể dừng sai dòng.

Có thể gắn source hash hoặc build ID vào debug metadata để phát hiện mismatch.

### 9.6. Macro và expansion

Nếu DSL hỗ trợ macro hoặc template expansion, một đoạn mã nguồn có thể sinh nhiều node. Debugger có thể cần hiển thị cả vị trí call site và vị trí macro definition.

Người dùng có thể muốn step vào expansion hoặc coi macro như một đơn vị. Đây là quyết định giao diện và cần giữ traceability của cả hai vị trí.

## 10. Debugging trong editor và Language Server

Editor cần giao diện và giao thức để điều khiển phiên debug. Language Server Protocol chủ yếu phục vụ tính năng ngôn ngữ như completion và diagnostics; debugging thường dùng Debug Adapter Protocol (DAP) hoặc tích hợp riêng.

### 10.1. Debug Adapter Protocol

DAP là giao thức JSON-based để editor và debug adapter trao đổi các yêu cầu như:

- Initialize.
- Launch hoặc Attach.
- SetBreakpoints.
- ConfigurationDone.
- Continue.
- Next.
- StepIn.
- StepOut.
- Pause.
- StackTrace.
- Scopes.
- Variables.
- Evaluate.
- Disconnect.

Tên request và khả năng cụ thể phụ thuộc phiên bản giao thức và client.

### 10.2. Debug adapter

Adapter chuyển DAP request thành API của DSL runtime:

~~~text
DAP Continue
    |
    v
Adapter
    |
    v
runtime.resume()

DAP StackTrace
    |
    v
Adapter
    |
    v
runtime.getLogicalFrames()
~~~

Adapter cũng chuyển runtime event thành stopped, continued, output, breakpoint hoặc terminated event cho editor.

### 10.3. Launch và Attach

Launch yêu cầu adapter khởi chạy chương trình DSL trong debug mode.

Attach kết nối vào một runtime hoặc process đã chạy và được cấu hình cho phép debugging.

Với DSL trong ứng dụng server, attach có thể hữu ích để điều tra một execution cụ thể. Cần xác thực và giới hạn quyền vì debugger có thể quan sát dữ liệu nhạy cảm hoặc điều khiển thực thi.

### 10.4. Debug configuration

Editor có thể dùng cấu hình:

~~~json
{
  "type": "dsl",
  "request": "launch",
  "name": "Debug order workflow",
  "program": "workflows/process-order.dsl",
  "arguments": {
    "orderId": "ORD-1024"
  },
  "stopOnEntry": true
}
~~~

Đây là cấu hình minh họa. Adapter cần xác định schema cấu hình, validate đường dẫn và tham số, rồi tạo execution context phù hợp.

### 10.5. Debug Console và Variables view

Editor thường có các khu vực:

- Breakpoints.
- Call Stack.
- Variables.
- Watch.
- Debug Console.
- Output.
- Threads hoặc Tasks.

Debugger DSL nên cung cấp tên và cấu trúc phù hợp với ngôn ngữ, ví dụ Workflow Steps hoặc Current Entity thay vì chỉ dùng khái niệm host runtime.

### 10.6. Khác biệt giữa Language Server và Debug Adapter

Language Server trả lời câu hỏi về mã nguồn: symbol này là gì, kiểu nào, diagnostics nào, completion nào.

Debug Adapter trả lời câu hỏi về lần chạy: đang dừng ở đâu, frame nào hoạt động, biến có giá trị gì, bước tiếp theo là gì.

Hai thành phần có thể dùng chung parser, symbol index và source map, nhưng có vòng đời và giao thức khác nhau.

## 11. Debugging DSL biểu thức và truy vấn

Một DSL biểu thức hoặc truy vấn có thể không có call stack sâu. Debugger cần cung cấp khả năng quan sát các bước đánh giá và giá trị trung gian.

Ví dụ:

~~~text
query expensiveOrders {
  from Order
  where status == PAID
    and total >= minimumAmount
  select {
    id,
    totalWithTax: total * (1 + taxRate)
  }
}
~~~

### 11.1. Step theo pipeline query

Debugger có thể hiển thị pipeline:

~~~text
Source: Order
   |
   v
Filter: status == PAID
   |
   v
Filter: total >= minimumAmount
   |
   v
Projection: id, totalWithTax
   |
   v
Result rows
~~~

Người dùng có thể xem số record trước và sau từng bước, giá trị predicate và một số row mẫu.

### 11.2. Quan sát predicate

Khi predicate trả false, debugger có thể giải thích phần điều kiện nào không thỏa mãn:

~~~text
status == PAID       true
total >= minimum     false
overall predicate    false
~~~

Điều này hữu ích hơn việc chỉ dừng ở một dòng query mà không cho biết vì sao record bị loại.

### 11.3. Dữ liệu lớn và lazy evaluation

Query có thể xử lý nhiều record hoặc stream. Debugger không nên materialize toàn bộ kết quả chỉ để hiển thị. Có thể giới hạn số row mẫu, dùng pagination và cung cấp thống kê.

### 11.4. Data privacy

Row mẫu có thể chứa thông tin cá nhân. Debugger cần tuân theo data access policy và mask các trường nhạy cảm trước khi gửi đến UI.

## 12. Debugging workflow và action

Workflow DSL thường có nhiều step, nhánh điều kiện, retry, wait và lời gọi dịch vụ.

Ví dụ:

~~~text
workflow processOrder(order) {
  step validate {
    validateOrder(order)
  }

  step reserve {
    reserveInventory(order)
  }

  step charge {
    chargePayment(order)
  }

  step notify {
    publishConfirmation(order)
  }
}
~~~

### 12.1. Workflow timeline

Debugger có thể hiển thị timeline:

| Step | Trạng thái | Thời điểm |
| --- | --- | --- |
| validate | Completed | 10:00:01 |
| reserve | Completed | 10:00:02 |
| charge | Paused | 10:00:03 |
| notify | Pending | — |

Thời điểm chỉ là ví dụ. UI thực tế cần phân biệt thời gian bắt đầu, thời gian kết thúc và thời lượng.

### 12.2. Breakpoint trước và sau action

Một action có thể có breakpoint trước khi gọi, sau khi trả kết quả hoặc khi thất bại.

- Before action: kiểm tra input và quyền.
- After action: kiểm tra output.
- On failure: xem lỗi và trạng thái retry.
- Before commit: kiểm tra dữ liệu chuẩn bị ghi.

Không phải action nào cũng có thể tạm dừng an toàn ở giữa. Một action đang giữ transaction hoặc lock có thể cần giới hạn thời gian pause.

### 12.3. Async wait và external event

Nếu workflow đang chờ message hoặc timer, debugger có thể hiển thị trạng thái Waiting và lý do chờ. Người dùng cần phân biệt chương trình bị treo với chương trình đang chờ một sự kiện hợp lệ.

### 12.4. Retry và compensation

Debugger nên hiển thị attempt number, lỗi của lần trước, delay và trạng thái compensation nếu workflow có retry hoặc saga-like behavior.

Khi resume, cần biết đang tiếp tục cùng attempt hay bắt đầu một attempt mới. Không nên cho phép thao tác Step làm phát lại một action có side effect mà không có cảnh báo hoặc cơ chế an toàn.

### 12.5. Breakpoint trong workflow song song

Nếu hai nhánh chạy song song, breakpoint ở một nhánh có thể tạm dừng task đó hoặc toàn workflow. Chính sách phải rõ để người dùng hiểu các nhánh còn lại có tiếp tục hay không.

## 13. Exception, lỗi runtime và xử lý dừng

Debugger có thể dừng khi runtime phát hiện lỗi. Việc phân loại exception giúp người dùng tìm đúng nguyên nhân.

### 13.1. Exception breakpoints

Có thể cấu hình dừng khi:

- Exception được ném.
- Exception không được bắt.
- Domain error thuộc một nhóm cụ thể.
- Assertion thất bại.
- Constraint violation xảy ra.
- Action trả về failure.

### 13.2. Exception đã được xử lý

Nếu DSL có try/catch, người dùng có thể muốn dừng tại nơi exception được ném ngay cả khi nó sẽ được bắt, hoặc chỉ dừng khi exception thoát khỏi mọi handler.

Debugger nên cung cấp lựa chọn phù hợp với runtime semantics.

### 13.3. Runtime diagnostic

Một số lỗi không phải exception host. Ví dụ, DSL có thể trả về Result.Error, workflow step có trạng thái Failed hoặc validator phát domain diagnostic.

Runtime nên cung cấp một abstraction chung cho failure event nhưng giữ loại và cause cụ thể để UI trình bày chính xác.

### 13.4. Source location của lỗi

Khi một action host ném exception, stack trace host có thể chỉ ra adapter hoặc thư viện. Debugger nên giữ source location của call site DSL và hiển thị cả thông tin native khi người dùng cần điều tra sâu.

### 13.5. Error detail và dữ liệu nhạy cảm

Thông báo cho người dùng có thể ngắn gọn, trong khi diagnostic nội bộ chứa cause, correlation ID và stack trace. Không nên gửi secret, credential hoặc toàn bộ payload nhạy cảm đến UI hay log không được bảo vệ.

## 14. Logging, tracing và debugger phối hợp

Trong hệ thống DSL chạy qua nhiều service, một phiên debug đơn lẻ không thể cho thấy toàn bộ lịch sử. Logging và tracing bổ sung thông tin ngoài tiến trình đang tạm dừng.

### 14.1. Correlation ID

Mỗi lần thực thi có thể có execution ID hoặc correlation ID. Khi workflow gọi service bên ngoài, ID được truyền qua request để liên kết log và trace.

### 14.2. Distributed trace

Trace có thể hiển thị span cho:

- DSL workflow.
- Workflow step.
- Action invocation.
- Database query.
- HTTP request.
- Message publish hoặc consume.

Debugger có thể hiển thị trace link hoặc correlation ID để người dùng chuyển sang công cụ quan sát hệ thống.

### 14.3. Logpoint và structured logging

Logpoint nên tạo structured event nếu có thể:

~~~json
{
  "executionId": "exec-42",
  "step": "charge",
  "orderId": "ORD-1024",
  "total": 275000
}
~~~

Định dạng này dễ lọc và tổng hợp hơn một câu text không có cấu trúc. Dữ liệu nhạy cảm vẫn cần được mask.

### 14.4. Production debugging

Dừng một execution production có thể ảnh hưởng người dùng và giữ transaction hoặc tài nguyên. Vì vậy, production thường ưu tiên tracing, snapshot hoặc diagnostic có giới hạn. Nếu cho phép live debugging, cần quyền, audit, timeout và cơ chế cách ly rõ ràng.

## 15. Reverse debugging và execution history

Reverse debugging cho phép xem trạng thái trước đó và đi lùi qua các bước đã thực thi.

### 15.1. Record và replay

Một cách tiếp cận là ghi lại các event và input cần thiết:

~~~text
Execution History
  1. WorkflowStarted
  2. OrderLoaded
  3. ValidationPassed
  4. InventoryReserved
  5. PaymentRequested
~~~

Khi replay, runtime tái tạo trạng thái từ lịch sử. Tuy nhiên, nếu action gọi dịch vụ bên ngoài, replay không được thực hiện side effect lần nữa. Cần dùng recorded result hoặc mock adapter.

### 15.2. Snapshot

Runtime có thể lưu snapshot của environment, stack và trạng thái workflow tại một số checkpoint. Khi người dùng đi lùi, nó khôi phục snapshot gần nhất rồi replay các event tiếp theo.

### 15.3. Deterministic replay

Để replay đúng, cần ghi nhận hoặc kiểm soát:

- Input.
- Thời gian.
- Random values.
- Kết quả service call.
- Event nhận từ bên ngoài.
- Thứ tự scheduling.
- Transaction boundary.
- Phiên bản DSL và runtime.

Nếu thiếu một trong các yếu tố ảnh hưởng kết quả, replay có thể khác lần chạy ban đầu.

### 15.4. Chi phí và giới hạn

Lịch sử thực thi có thể lớn và chứa dữ liệu nhạy cảm. Cần giới hạn thời gian lưu, dung lượng, quyền truy cập và chính sách mask. Reverse debugging phù hợp với môi trường phát triển hoặc một số workflow có khả năng replay được thiết kế từ đầu.

## 16. Debugger cho DSL được biên dịch và generated runtime

Một số DSL được biên dịch thành Java, JavaScript, bytecode hoặc một dạng IR trước khi chạy.

### 16.1. Giữ debug metadata

Compiler có thể tạo metadata gồm:

- Source file và source range.
- Node ID.
- Generated instruction range.
- Logical function name.
- Parameter và local variable mapping.
- Type metadata.
- Inline hoặc macro expansion mapping.

Metadata này có thể được lưu cùng artifact hoặc trong file phụ.

### 16.2. Logical variable mapping

Compiler có thể tối ưu hoặc đổi tên biến. Debugger cần ánh xạ biến DSL sang vị trí lưu trữ trong generated runtime.

Một biến DSL có thể nằm trong register, stack slot, closure cell hoặc field. Debug adapter nên trình bày tên DSL và giá trị tương ứng thay vì lộ tên compiler-generated.

### 16.3. Inlining và optimization

Compiler có thể inline function hoặc loại bỏ biến không còn cần thiết. Khi đó, debugger cần quyết định có thể hiển thị frame logic ban đầu hay không.

Debug build có thể giảm một số tối ưu để giữ khả năng stepping và variable inspection chính xác. Tuy nhiên, behavior giữa debug build và production build cần được kiểm soát để tránh khác biệt ngoài ý muốn.

### 16.4. Generated code view

Có thể cho phép mở mã sinh để nhà phát triển công cụ điều tra, nhưng người viết DSL nên mặc định thấy source DSL. UI có thể cung cấp chuyển đổi giữa source view và generated view khi có metadata.

## 17. Debugging trong môi trường đồng thời

Một DSL có thể chạy nhiều thread, task hoặc workflow execution cùng lúc.

### 17.1. Thread và task view

Debugger cần hiển thị các execution thread hoặc logical task. Một task có thể đang chạy, chờ, tạm dừng hoặc kết thúc.

Tên task nên có ngữ cảnh miền, ví dụ order-1024/charge, thay vì chỉ là thread-17.

### 17.2. Pause all và pause selected task

Khi dừng tại breakpoint, debugger có thể:

- Chỉ tạm dừng task đạt breakpoint.
- Tạm dừng toàn bộ execution.
- Tạm dừng các task có quan hệ với task hiện tại.

Lựa chọn phụ thuộc runtime. Dừng một task có thể làm task khác tiếp tục thay đổi dữ liệu mà người dùng đang quan sát.

### 17.3. Race condition

Một lỗi có thể chỉ xuất hiện khi hai task cập nhật cùng một state. Tạm dừng một task có thể làm thay đổi timing và khiến lỗi biến mất.

Debugger có thể hỗ trợ event trace, task history và synchronization view để điều tra. Không nên coi việc lỗi biến mất khi debug là bằng chứng lỗi đã được sửa.

### 17.4. Deadlock và wait state

Với runtime có lock hoặc transaction, debugger có thể hiển thị task đang chờ tài nguyên nào. Nếu runtime có lock graph, UI có thể giúp nhận diện chu trình chờ.

### 17.5. Pause safety

Không phải điểm nào cũng an toàn để pause. Runtime cần xác định safe point, đặc biệt trong lúc cập nhật cấu trúc dữ liệu hoặc giữ lock. Breakpoint có thể chỉ được kích hoạt ở safe point kế tiếp.

## 18. Bảo mật và quyền khi debugging

Debugger thường có quyền quan sát nhiều dữ liệu và điều khiển execution. Đây là một năng lực nhạy cảm.

### 18.1. Xác thực và phân quyền

Cần xác định ai được phép:

- Khởi chạy phiên debug.
- Attach vào execution đang chạy.
- Xem biến và payload.
- Đánh giá expression.
- Thay đổi giá trị.
- Tiếp tục hoặc hủy execution.
- Xem stack trace và log nhạy cảm.

Quyền debug không nhất thiết giống quyền đọc mã nguồn hoặc quyền thực thi workflow.

### 18.2. Tenant isolation

Trong môi trường multi-tenant, một người dùng chỉ được attach vào execution thuộc tenant và phạm vi được cấp. Không nên dựa vào execution ID do client gửi mà không kiểm tra quyền sở hữu.

### 18.3. Mask dữ liệu

Có thể đánh dấu biến hoặc field là secret, personal data hoặc restricted:

~~~text
property accessToken: Secret
property customerEmail: PersonalData
~~~

Debugger có thể hiển thị giá trị đã che hoặc chỉ hiển thị trạng thái có giá trị. Chính sách mask cần áp dụng cả trong Variables, Watch, Evaluate, logpoint và export.

### 18.4. Expression evaluation

Cho phép nhập expression tùy ý có thể mở đường gọi action, truy cập file hoặc thực thi mã host nếu evaluator không giới hạn.

Một chế độ read-only nên chỉ cho phép expression thuần. Chế độ mutation hoặc command cần quyền riêng và audit.

### 18.5. Debug port và remote attach

Debug endpoint không nên mở công khai. Cần authentication, TLS hoặc kênh bảo mật tương đương, network restriction, session timeout và audit log.

### 18.6. Giới hạn tài nguyên

Watch expression, object expansion hoặc step execution có thể tiêu thụ nhiều CPU và bộ nhớ. Cần giới hạn số request đồng thời, thời gian evaluate, số phần tử hiển thị và kích thước payload.

## 19. Hiệu năng và trải nghiệm người dùng

Debugger làm thay đổi đặc tính thời gian của chương trình. Một số runtime có thể chậm hơn đáng kể khi bật instrumentation.

### 19.1. Chi phí debug event

Phát event ở mọi node AST tạo overhead. Có thể chỉ instrument statement, function boundary, action và breakpoint candidate. Khi người dùng cần stepping chi tiết, runtime bật chế độ chi tiết hơn.

### 19.2. Lazy inspection

Không tải mọi biến và toàn bộ object graph ngay khi dừng. Chỉ lấy danh sách cấp đầu, sau đó mở rộng theo yêu cầu.

### 19.3. Batching

Nếu UI cần nhiều giá trị, adapter có thể gom yêu cầu theo frame hoặc scope để giảm round trip. Tuy nhiên, cần giữ giới hạn kích thước phản hồi.

### 19.4. Phản hồi nhanh

Breakpoint và pause cần được phản hồi trong thời gian hợp lý. Các thao tác lấy object graph lớn hoặc evaluate phức tạp có thể chạy bất đồng bộ và có trạng thái tiến trình.

### 19.5. Thông báo trạng thái rõ ràng

UI nên phân biệt:

- Running.
- Paused at breakpoint.
- Paused by user.
- Waiting for external event.
- Evaluating watch.
- Terminated.
- Disconnected.
- Failed to attach.

Điều này tránh người dùng nhầm execution đang chờ với execution bị treo.

## 20. Kiểm thử debugger

Debugger là công cụ phức hợp, cần kiểm thử giao thức, runtime, source mapping và trải nghiệm.

### 20.1. Breakpoint tests

Kiểm tra:

- Breakpoint ở statement hợp lệ.
- Breakpoint ở dòng không thực thi.
- Conditional breakpoint true và false.
- Hit count.
- Breakpoint trong function.
- Breakpoint trong nested workflow.
- Breakpoint ở generated code có source map.

### 20.2. Stepping tests

Kiểm tra Continue, Step Over, Step Into và Step Out với:

- Function call.
- Nested block.
- Loop.
- Exception.
- Async task.
- Workflow step.
- Action native.

Xác minh vị trí dừng và frame hiện tại.

### 20.3. Variable inspection tests

Kiểm tra:

- Local variable.
- Parameter.
- Closure capture.
- Global/module variable.
- Current object.
- Null và uninitialized.
- Collection lớn.
- Object graph có chu trình.
- Giá trị nhạy cảm được mask.

### 20.4. Source mapping tests

Với từng node nguồn, kiểm tra generated location hoặc instruction map. Thử trường hợp một node sinh nhiều đoạn mã, nhiều node cùng sinh một instruction và macro expansion.

### 20.5. Protocol tests

Kiểm tra request/response, event ordering, cancellation, reconnect và client capability. Adapter cần xử lý request không hợp lệ mà không làm sập runtime.

### 20.6. Security tests

Xác minh người không có quyền không thể attach, inspect tenant khác, đánh giá expression có tác động phụ hoặc đọc secret. Kiểm tra timeout và giới hạn payload.

### 20.7. Performance tests

So sánh thời gian thực thi khi tắt debug, bật instrumentation và dừng tại breakpoint. Kiểm tra việc mở rộng object lớn và nhiều watch expressions không làm UI hoặc runtime mất phản hồi.

### 20.8. End-to-end tests

Tạo một fixture DSL, khởi chạy qua editor hoặc debug adapter, đặt breakpoint, inspect variable, step và kết thúc phiên. Kiểm tra cả nội dung hiển thị lẫn trạng thái runtime.

## 21. Ví dụ: điều tra lỗi tính tổng đơn hàng

Giả sử workflow DSL:

~~~text
workflow calculateOrder(order) {
  let subtotal = order.items.sum(item.price)
  let tax = subtotal * taxRate
  let total = subtotal + tax + shippingFee

  if total > creditLimit {
    rejectOrder(order)
  } else {
    approveOrder(order)
  }
}
~~~

Người dùng nhận thấy một đơn hàng bị từ chối dù tổng tiền dự kiến thấp hơn creditLimit.

### 21.1. Đặt breakpoint

Đặt breakpoint tại dòng tính total hoặc tại điều kiện if. Chạy workflow với một order cụ thể.

Khi dừng, debugger hiển thị:

~~~text
Frame: calculateOrder
Locals:
  subtotal = 500000
  tax = 50000
  shippingFee = 30000
  total = 580000
  creditLimit = 550000
~~~

Giá trị cho thấy điều kiện total > creditLimit là đúng. Vấn đề có thể không nằm ở nhánh if mà ở nguồn của creditLimit hoặc quy tắc nghiệp vụ.

### 21.2. Inspect biểu thức

Thêm watch:

~~~text
order.customer.creditLimit
subtotal + tax
subtotal + tax + shippingFee
~~~

Nếu creditLimit trong object khác với giá trị người dùng mong đợi, có thể điều tra bước load dữ liệu hoặc mapping.

### 21.3. Step Into

Step Into lời gọi lấy order hoặc tính subtotal để xem từng item. Debugger có thể hiển thị:

~~~text
items:
  [0] price = 200000
  [1] price = 300000
sum = 500000
~~~

Nếu một item bị tính sai, tiếp tục vào function hoặc query chịu trách nhiệm đọc giá.

### 21.4. Kiểm tra source và runtime

Nếu giá trị trong DSL khác dữ liệu database, source map giúp xác định call site và runtime trace giúp theo dõi service đã trả dữ liệu. Debugger không tự sửa dữ liệu; nó cung cấp bằng chứng để xác định tầng gây lỗi.

### 21.5. Xác minh sau khi sửa

Sau khi sửa mapping hoặc công thức, chạy lại cùng input. Có thể giữ breakpoint và watch để so sánh. Sau đó bổ sung test regression để lỗi không tái xuất hiện.

Ví dụ này cho thấy debugger giúp đi từ triệu chứng đến trạng thái cụ thể và lần theo nguồn dữ liệu, thay vì chỉ nhìn kết quả cuối cùng.

## 22. Những lỗi thiết kế thường gặp

**Chỉ dùng debugger của host language.** Người viết DSL phải đọc stack frame của interpreter và khó tìm dòng nguồn. Hãy cung cấp logical frame và source mapping theo DSL.

**Không giữ source location.** Breakpoint và runtime error không thể điều hướng chính xác về mã nguồn. Hãy lưu source span trên AST hoặc debug metadata.

**Breakpoint luôn được coi là hợp lệ.** Dòng comment hoặc declaration không có instruction có thể không dừng được. Hãy xác minh breakpoint và báo trạng thái.

**Step Over và Step Into có semantics mơ hồ.** Người dùng không biết đang bước qua function hay workflow step. Hãy định nghĩa mức stepping của DSL.

**Watch expression gây side effect.** Việc xem biến có thể thay đổi trạng thái chương trình. Hãy ưu tiên evaluate thuần và tách chế độ mutation.

**Tải toàn bộ object graph.** Một collection lớn có thể làm runtime chậm hoặc gửi quá nhiều dữ liệu. Hãy dùng lazy expansion, pagination và giới hạn.

**Không phân biệt logical frame với host frame.** Người dùng DSL thấy các phương thức interpreter lặp lại. Hãy trình bày frame theo function, operation và step của DSL.

**Source map không khớp artifact.** Breakpoint có thể dừng sai dòng khi source thay đổi sau khi compile. Hãy gắn source hash hoặc build ID.

**Pause ở thời điểm không an toàn.** Dừng giữa transaction hoặc thao tác giữ lock có thể gây treo hệ thống. Hãy xác định safe point và timeout.

**Cho phép remote debugging không kiểm soát.** Người dùng có thể xem secret hoặc thay đổi execution. Hãy xác thực, phân quyền, mask và audit.

**Không hỗ trợ async task.** Debugger có thể hiển thị stack tuyến tính không phản ánh workflow song song. Hãy cung cấp task view và logical execution tree.

**Không kiểm thử protocol và lifecycle.** Phiên debug có thể để lại process hoặc resource. Hãy kiểm thử launch, attach, disconnect, terminate và cancellation.

## 23. Quy trình xây dựng debugger cho DSL

Có thể triển khai theo các giai đoạn sau:

### Bước 1: Xác định mô hình thực thi

Làm rõ statement, expression, function, action, workflow step, async task và transaction. Xác định điểm nào có thể pause an toàn.

### Bước 2: Giữ source metadata

Parser hoặc compiler cần lưu source span, node ID và mapping đến instruction. Nếu có macro hoặc generated code, xác định quy tắc ánh xạ về nguồn.

### Bước 3: Thiết kế logical frame

Định nghĩa frame, scope, local variable, parameter, captured variable và current object. Tách logical frame của DSL khỏi stack host.

### Bước 4: Thêm execution hooks

Runtime phát event ở statement, function boundary, action, exception và workflow transition. Có thể bật mức instrumentation theo debug configuration.

### Bước 5: Xây breakpoint manager

Hỗ trợ line hoặc node breakpoint, condition, hit count và trạng thái verified. Xác định hành vi khi source hoặc artifact thay đổi.

### Bước 6: Xây execution controller

Triển khai continue, pause, step over, step into và step out. Nếu hỗ trợ reverse debugging, thiết kế event history hoặc snapshot ngay từ đầu.

### Bước 7: Xây inspection API

Cung cấp stack trace, scopes, variables và evaluate. Dùng lazy loading, giới hạn payload và chính sách read-only.

### Bước 8: Tích hợp editor và debug protocol

Dùng DAP hoặc giao thức phù hợp. Kiểm tra capability của client, version tài liệu, launch/attach và lifecycle của phiên.

### Bước 9: Xử lý security và concurrency

Xác thực attach, kiểm tra tenant, mask dữ liệu, giới hạn tài nguyên và định nghĩa pause behavior cho task song song.

### Bước 10: Kiểm thử end-to-end

Kiểm thử breakpoint, stepping, source mapping, variables, exceptions, workflow, protocol, security và hiệu năng với các chương trình DSL đại diện.

## 24. Kết luận

Trình gỡ lỗi là công cụ giúp quan sát và điều khiển quá trình thực thi DSL. Nó cho phép đặt breakpoint, chạy từng bước, xem stack, kiểm tra biến, đánh giá biểu thức và điều tra exception. Để cung cấp trải nghiệm đúng với ngôn ngữ, debugger cần hiểu AST, scope, symbol, type, workflow và runtime semantics thay vì chỉ phơi bày stack của ngôn ngữ host.

Một kiến trúc đáng tin cậy cần source mapping, logical execution frame, breakpoint manager, execution controller, inspection API và debug adapter. Với DSL được biên dịch, debug metadata phải khớp artifact; với workflow bất đồng bộ, debugger cần hiển thị task và trạng thái chờ; với chương trình chạy trên dữ liệu nhạy cảm, inspection và remote attach cần được phân quyền và giới hạn.

Hãy bắt đầu từ breakpoint và stepping ở các statement có source location rõ ràng, sau đó bổ sung inspection, watch, workflow view và các khả năng nâng cao. Khi runtime cung cấp trạng thái có cấu trúc và editor trình bày đúng khái niệm của DSL, debugger giúp người dùng tìm nguyên nhân lỗi nhanh hơn và hiểu sâu hơn cách chương trình thực sự vận hành.

