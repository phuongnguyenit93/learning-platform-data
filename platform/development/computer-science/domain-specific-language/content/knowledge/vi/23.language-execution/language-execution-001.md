# Engine thực thi

Trong một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), chương trình được viết bằng cú pháp gần với lĩnh vực sử dụng, chẳng hạn quy tắc nghiệp vụ, workflow, truy vấn dữ liệu, cấu hình hạ tầng hoặc mô hình quy trình. Sau khi văn bản được phân tích và kiểm tra, hệ thống cần một thành phần có thể thực hiện các chỉ thị đó. Thành phần này được gọi là **engine thực thi** (*execution engine*).

Engine thực thi tiếp nhận chương trình DSL đã được phân tích, xác định cách diễn giải các cấu trúc, quản lý trạng thái chạy, gọi các thao tác được phép và trả về kết quả hoặc lỗi. Nó là cầu nối giữa mô hình khai báo của DSL và các dịch vụ, dữ liệu, tài nguyên hoặc hành động thực tế của hệ thống.

Ví dụ, một DSL workflow có thể mô tả:

~~~text
workflow ProcessOrder(order: Order) {
    validateOrder(order);

    if order.paymentStatus == ACCEPTED {
        reserveInventory(order);
        createShipment(order);
    } else {
        requestPayment(order);
    }
}
~~~

Engine thực thi phải hiểu cấu trúc workflow, đánh giá điều kiện, gọi đúng action, truyền đúng dữ liệu, xử lý lỗi và xác định workflow kết thúc khi nào. Nếu `reserveInventory` thất bại, engine cần áp dụng chính sách lỗi đã định nghĩa; nếu hai bước được khai báo song song, engine cần quản lý lịch chạy và trạng thái hoàn tất của chúng.

Engine không chỉ là vòng lặp đọc từng câu lệnh. Trong một hệ thống DSL hoàn chỉnh, nó thường gồm bộ nạp chương trình, bộ xác thực, interpreter hoặc virtual machine, môi trường thực thi, bộ điều phối tác vụ, lớp tích hợp dịch vụ, cơ chế quản lý trạng thái, xử lý lỗi, bảo mật và công cụ quan sát. Cách tổ chức phụ thuộc vào loại DSL: engine tính biểu thức có thể rất nhỏ, trong khi engine workflow dài hạn cần lưu trạng thái bền vững, retry và phục hồi sau sự cố.

## 1. Engine thực thi là gì?

Engine thực thi là runtime chịu trách nhiệm biến một biểu diễn DSL đã được chấp nhận thành hành vi cụ thể. Đầu vào của engine thường là AST, IR, bytecode hoặc một mô hình đã được biên dịch; đầu ra có thể là giá trị, trạng thái mới, sự kiện, artifact hoặc kết quả của một workflow.

Một engine có thể thực hiện các công việc sau:

- Nạp và kiểm tra phiên bản chương trình, schema và dependency.
- Tạo execution context cho một lần chạy.
- Đánh giá biểu thức và điều kiện.
- Điều khiển luồng bằng sequence, branch, loop, call và return.
- Gọi function, action, connector hoặc dịch vụ bên ngoài.
- Quản lý biến, scope, giá trị và trạng thái workflow.
- Điều phối tác vụ đồng bộ, bất đồng bộ hoặc song song.
- Áp dụng transaction, retry, timeout và compensation theo hợp đồng.
- Phát diagnostic, execution trace, event và kết quả cuối.
- Áp dụng quyền truy cập, giới hạn tài nguyên và chính sách an toàn.

### Phân biệt engine, interpreter và compiler

Các khái niệm này có liên quan nhưng không đồng nghĩa:

| Thành phần | Vai trò chính | Ví dụ |
|---|---|---|
| Compiler | Chuyển DSL sang AST/IR/bytecode/mã đích và kiểm tra tĩnh. | Biên dịch workflow thành IR. |
| Interpreter | Đọc một biểu diễn chương trình và đánh giá trực tiếp. | Duyệt AST để thực hiện từng node. |
| Virtual machine (VM) | Thực thi một tập lệnh trung gian có quy tắc và trạng thái máy xác định. | Chạy bytecode của DSL. |
| Execution engine | Điều phối toàn bộ quá trình thực thi và các dịch vụ runtime. | Quản lý context, interpreter, action, scheduler và trạng thái. |
| Runtime library | Cung cấp kiểu dữ liệu, hàm và dịch vụ mà chương trình dùng khi chạy. | `Money`, `Date`, `OrderRepository`. |

Một engine có thể chứa interpreter, VM hoặc gọi mã đã được compiler sinh. Vì vậy, khi nói engine thực thi, cần nhìn vào toàn bộ runtime chứ không chỉ thuật toán đánh giá biểu thức.

## 2. Vị trí của engine trong kiến trúc DSL

Một kiến trúc tổng quát có thể được chia thành hai giai đoạn: chuẩn bị chương trình và thực thi chương trình.

~~~mermaid
flowchart TD
    A[DSL source] --> B[Lexer and parser]
    B --> C[AST]
    C --> D[Name and type analysis]
    D --> E[Validation and lowering]
    E --> F[Executable IR / bytecode]
    F --> G[Execution engine]
    G --> H[Runtime context]
    G --> I[Scheduler]
    G --> J[Action and service adapters]
    H --> K[Result / state / events]
    I --> K
    J --> K
~~~

Engine thường nhận một chương trình đã được xác thực. Tuy nhiên, với DSL tương tác hoặc DSL có dữ liệu động, một số kiểm tra vẫn có thể diễn ra lúc chạy. Ví dụ, compiler có thể xác nhận `order` có kiểu `Order`, còn engine phải kiểm tra đối tượng `Order#O100` thực tế có tồn tại và người gọi có quyền thao tác hay không.

### Giai đoạn chuẩn bị

Trước khi chạy, hệ thống có thể:

1. Đọc source và dependency.
2. Phân tích cú pháp thành AST.
3. Phân giải tên và kiểm tra kiểu.
4. Kiểm tra ràng buộc miền và quyền cần thiết.
5. Hạ cấp AST thành IR hoặc bytecode.
6. Tạo executable artifact gắn với phiên bản compiler và dependency.

### Giai đoạn thực thi

Engine thường:

1. Nạp executable artifact.
2. Xác thực input và tạo execution context.
3. Khởi tạo trạng thái và frame.
4. Đánh giá instruction hoặc node theo semantics DSL.
5. Điều phối action và tác vụ bất đồng bộ.
6. Ghi nhận kết quả, lỗi và sự kiện.
7. Hoàn tất, tạm dừng hoặc lưu trạng thái để tiếp tục sau.

Việc tách hai giai đoạn giúp compiler và runtime có thể phát triển độc lập. Một chương trình có thể được compile một lần và thực thi nhiều lần với các context khác nhau, nếu artifact không phụ thuộc vào dữ liệu chạy cụ thể.

## 3. Các mô hình xây dựng engine

Không có một mô hình thực thi phù hợp với mọi DSL. Lựa chọn phụ thuộc vào độ phức tạp ngôn ngữ, yêu cầu hiệu năng, khả năng mở rộng, độ an toàn và nhu cầu debug.

### Interpreter trên AST

Interpreter duyệt trực tiếp AST và xử lý từng loại node. Ví dụ, khi gặp `AddExpr`, interpreter đánh giá hai toán hạng rồi thực hiện phép cộng.

~~~text
evaluate(node, context):
    match node:
        Number(value): return value
        Name(name): return context.lookup(name)
        Add(left, right):
            a = evaluate(left, context)
            b = evaluate(right, context)
            return add(a, b)
~~~

Ưu điểm:

- Dễ triển khai và phù hợp với DSL nhỏ.
- AST có thể giữ source span để diagnostic trực tiếp.
- Dễ mở rộng khi thêm loại node.
- Không cần bước sinh bytecode riêng.

Hạn chế:

- Việc dispatch node lặp lại có thể tốn chi phí.
- AST thường chứa nhiều metadata không cần cho runtime.
- Khó tối ưu sâu nếu interpreter xử lý trực tiếp cấu trúc cấp cao.
- Cần thiết kế cẩn thận để tránh đệ quy quá sâu.

### Interpreter trên IR

Compiler chuyển AST sang IR có cấu trúc đơn giản hơn. Interpreter chỉ cần hiểu tập lệnh IR, chẳng hạn `LOAD`, `CALL`, `JUMP_IF_FALSE`, `STORE` và `RETURN`.

IR giúp chuẩn hóa nhiều cú pháp DSL về một số thao tác cốt lõi. Nó cũng tạo ranh giới rõ giữa ngôn ngữ nguồn và engine.

### Virtual machine

VM thực thi bytecode hoặc instruction stream trên một máy trừu tượng. VM thường quản lý program counter, operand stack, call stack, local variables và heap hoặc value store.

Ví dụ bytecode khái niệm:

~~~text
LOAD_LOCAL 0
GET_PROPERTY "total"
PUSH_NUMBER 1000
GREATER_THAN
JUMP_IF_FALSE 12
CALL_ACTION "approveOrder", 1
RETURN
~~~

VM phù hợp khi DSL có nhiều chương trình, cần runtime thống nhất hoặc muốn kiểm soát instruction và tài nguyên. Đổi lại, cần thiết kế bytecode format, verifier, debugger và phiên bản tương thích.

### Sinh mã sang ngôn ngữ chủ

Compiler có thể sinh Java, JavaScript, SQL hoặc một ngôn ngữ khác. Engine khi đó có thể đóng vai trò quản lý việc biên dịch, nạp class/module, cung cấp runtime library và thu thập kết quả.

Ưu điểm là tận dụng compiler và runtime của nền tảng đích. Hạn chế là semantics DSL có thể bị ảnh hưởng bởi khác biệt của ngôn ngữ chủ, stack trace có thể khó ánh xạ và việc sandbox mã sinh cần được xem xét kỹ.

### Mô hình lai

Một hệ thống có thể dùng interpreter cho development, compile thành bytecode cho production, hoặc thực thi biểu thức bằng interpreter nhưng giao action cho service runtime. Mô hình lai cho phép cân bằng tốc độ phát triển và hiệu năng.

## 4. Kiến trúc bên trong của execution engine

Một engine thực tế thường được chia thành các thành phần có hợp đồng riêng.

~~~mermaid
flowchart TB
    A[Execution request] --> B[Program loader]
    B --> C[Verifier]
    C --> D[Execution session]
    D --> E[Evaluator / VM]
    E --> F[Value and scope manager]
    E --> G[Control-flow manager]
    E --> H[Action dispatcher]
    H --> I[Connectors and host services]
    G --> J[Scheduler]
    E --> K[Error and cancellation manager]
    D --> L[State store]
    D --> M[Tracing and metrics]
~~~

### Program loader

Nạp executable artifact, kiểm tra format version, dependency và cấu hình runtime. Loader có thể đọc artifact từ file, memory cache hoặc remote repository.

### Verifier

Kiểm tra artifact có hợp lệ trước khi chạy: instruction có opcode được hỗ trợ, jump target nằm trong phạm vi, stack usage hợp lệ, type metadata tương thích và các action được tham chiếu có thể được resolve.

### Execution session

Đại diện cho một lần chạy. Nó quản lý execution ID, input, context, trạng thái, cancellation token, deadline, trace và kết quả.

### Evaluator hoặc VM

Thực hiện semantics của biểu thức và instruction. Đây là phần chịu trách nhiệm xác định cách các node hoặc opcode chuyển trạng thái máy.

### Value và scope manager

Quản lý giá trị runtime, biến cục bộ, binding, closure, object reference và kiểu động nếu có.

### Control-flow manager

Quản lý branch, loop, function call, return, exception, workflow transition và các trạng thái điều khiển.

### Action dispatcher

Chuyển lời gọi DSL thành thao tác của host runtime hoặc connector. Dispatcher kiểm tra chữ ký, quyền, timeout và cách truyền dữ liệu.

### Scheduler

Quản lý tác vụ bất đồng bộ, timer, queue, retry và các nhánh chạy song song.

### State store

Giữ trạng thái execution. Với tác vụ ngắn, state có thể nằm trong memory; với workflow dài hạn, state thường cần được lưu bền vững.

### Error, cancellation và observability

Quản lý exception, timeout, hủy chạy, diagnostic, trace, log và metrics. Các thành phần này giúp engine có thể vận hành và gỡ lỗi trong môi trường thực tế.

## 5. Vòng đời một lần thực thi

Engine cần một lifecycle rõ ràng để phân biệt lúc chuẩn bị, đang chạy, tạm dừng và kết thúc.

Một lifecycle khái quát:

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Validating
    Validating --> Ready: input and program valid
    Validating --> Failed: validation error
    Ready --> Running
    Running --> Suspended: wait / checkpoint
    Suspended --> Running: resume
    Running --> Completed: normal return
    Running --> Failed: unhandled error
    Running --> Cancelled: cancellation
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
~~~

Các trạng thái thực tế có thể nhiều hơn, nhưng cần tránh trạng thái mơ hồ như vừa `Completed` vừa `Running`.

### Created

Execution request đã được nhận và được gán ID. Chưa có action nghiệp vụ nào được thực hiện.

### Validating

Engine xác thực executable, input, quyền và các điều kiện runtime ban đầu.

### Ready

Context và trạng thái ban đầu đã được tạo. Engine có thể bắt đầu thực thi.

### Running

Interpreter hoặc VM đang xử lý instruction, gọi action hoặc chờ scheduler phân phối công việc.

### Suspended

Execution đang chờ sự kiện, timer, callback, approval hoặc tài nguyên. Với workflow dài hạn, trạng thái cần được checkpoint để có thể tiếp tục sau khi process khởi động lại.

### Completed, Failed và Cancelled

- `Completed`: chương trình kết thúc theo đường đi bình thường.
- `Failed`: lỗi không được xử lý hoặc chính sách lỗi quyết định dừng execution.
- `Cancelled`: execution được hủy theo yêu cầu hoặc deadline.

Các trạng thái kết thúc nên bất biến, trừ khi hệ thống có mô hình compensation hoặc trạng thái hậu xử lý riêng.

## 6. Execution context

**Execution context** là tập thông tin mà chương trình có thể đọc trong một lần chạy. Nó tạo ranh giới giữa chương trình DSL và môi trường host.

Context có thể gồm:

- Input parameters.
- Biến và scope runtime.
- Principal hoặc danh tính người gọi.
- Tenant và security claims.
- Clock, timezone và locale.
- Correlation ID và execution ID.
- Dependency versions hoặc snapshot ID.
- Cancellation token và deadline.
- Service registry và các capability được cấp.
- Trace context và metadata kiểm toán.

Ví dụ mô hình:

~~~java
record ExecutionContext(
    String executionId,
    String tenantId,
    String principalId,
    java.time.Instant startedAt,
    java.time.ZoneId zoneId,
    Map<String, Object> inputs,
    Map<String, Object> services
) {}
~~~

Đây chỉ là mô hình khái niệm. Hệ thống thực tế nên tránh một map không kiểu cho mọi thứ nếu cần kiểm tra chặt chẽ. Có thể tách `ExecutionIdentity`, `RuntimeEnvironment`, `InputBindings`, `ServiceCapabilities` và `ExecutionControl` thành các kiểu riêng.

### Không dùng global mutable state cho context

Nếu nhiều execution dùng chung một biến toàn cục có thể thay đổi, dữ liệu của execution này có thể ảnh hưởng execution khác. Context nên được tạo riêng cho mỗi lần chạy hoặc chia sẻ qua các thành phần bất biến và được kiểm soát.

### Context propagation

Khi engine gọi tác vụ bất đồng bộ hoặc chuyển thread, execution ID, tenant, principal, trace context và cancellation token cần được truyền đúng. Không nên dựa vào thread-local nếu tác vụ có thể chuyển sang thread khác mà không có cơ chế propagation.

## 7. Giá trị và môi trường biến

Interpreter hoặc VM cần một mô hình giá trị runtime nhất quán. DSL có thể hỗ trợ số, chuỗi, boolean, ngày giờ, collection, entity reference, function và giá trị null.

Một tập kiểu khái niệm:

~~~text
Value =
    Null
  | Boolean
  | Integer
  | Decimal
  | Text
  | DateTime
  | List<Value>
  | Map<Key, Value>
  | EntityReference
  | FunctionValue
  | DomainValue
~~~

### Value semantics

Đặc tả cần quy định equality, conversion, arithmetic, null handling và cách biểu diễn số. Ví dụ, `Money` có thể chứa amount và currency; cộng hai giá trị khác currency có thể bị từ chối thay vì tự động chuyển đổi.

### Environment và scope frame

Mỗi block hoặc function call có thể tạo một frame chứa binding cục bộ. Frame có liên kết đến frame cha để lookup biến theo lexical scope.

~~~text
Environment
  currentFrame
    local bindings
    parentFrame
~~~

Khi rời block, frame được pop hoặc trở nên không còn nhìn thấy. Closure có thể giữ frame hoặc các binding được capture theo semantics DSL.

### Phân biệt biến và tham chiếu entity

Một biến `order` có thể chứa object reference đến entity được lưu trong repository. Việc đọc `order.total` có thể chỉ truy cập object đã có trong memory hoặc kích hoạt lazy loading. Engine cần quy định điều gì xảy ra khi entity không tồn tại, quyền truy cập bị từ chối hoặc dữ liệu đã lỗi thời.

## 8. Đánh giá biểu thức

Engine thực thi biểu thức theo quy tắc ngữ nghĩa của DSL. Với AST, evaluator thường có một nhánh xử lý cho mỗi loại expression; với VM, các phép toán tương ứng với opcode.

### Literal và tên

Literal tạo giá trị trực tiếp. Name expression tra binding trong environment hoặc symbol đã được resolve.

~~~text
evaluate(NumberLiteral(42)) -> Decimal(42)
evaluate(Name("threshold")) -> environment.lookup("threshold")
~~~

Nếu tên chưa được phân giải tĩnh, engine có thể phát runtime error. Tuy nhiên, với DSL có static analysis, phần lớn lỗi tên nên được phát hiện trước khi chạy.

### Phép toán

Với biểu thức `a + b`, evaluator:

1. Đánh giá `a` theo thứ tự được quy định.
2. Đánh giá `b`.
3. Kiểm tra kiểu hoặc dispatch phép cộng phù hợp.
4. Trả giá trị hoặc phát lỗi.

Thứ tự này quan trọng nếu một biểu thức có tác dụng phụ. DSL có thể cấm side effect trong expression hoặc quy định thứ tự từ trái sang phải.

### Short-circuit logic

Với `A and B`, DSL có thể quy định nếu `A` là false thì không đánh giá `B`. Điều này vừa ảnh hưởng hiệu năng vừa ảnh hưởng tác dụng phụ và lỗi. Engine phải thực thi đúng semantics; không được tối ưu thành đánh giá cả hai vế nếu điều đó làm thay đổi hành vi.

### Property access

`order.customer.name` có thể yêu cầu nhiều lần truy cập thuộc tính. Engine cần xác định:

- `null` ở một bước được xử lý thế nào.
- Thuộc tính có thể lazy-load không.
- Mỗi lần truy cập có thể gọi service không.
- Có kiểm tra quyền theo từng thuộc tính không.
- Getter có được phép có tác dụng phụ không.

### Function call

Lời gọi hàm cần kiểm tra số lượng và kiểu đối số, tạo frame hoặc invocation context, thực thi thân hàm và trả kết quả. Engine phải quản lý recursion depth, call stack và giới hạn thời gian nếu chương trình có thể đệ quy.

## 9. Điều khiển luồng

Engine cần thực thi các cấu trúc điều khiển được DSL hỗ trợ.

### Sequence

Các câu lệnh trong sequence thường chạy theo thứ tự khai báo. Nếu một câu lệnh thất bại, engine cần áp dụng chính sách dừng, bắt lỗi hoặc tiếp tục.

~~~text
validateOrder(order);
reserveInventory(order);
createShipment(order);
~~~

### Conditional branch

~~~text
if order.total >= approvalThreshold {
    requestManagerApproval(order);
} else {
    approveAutomatically(order);
}
~~~

Engine đánh giá điều kiện một lần theo semantics được quy định rồi thực thi nhánh tương ứng. Với điều kiện có trạng thái thay đổi, cần xác định liệu giá trị có được tính lại khi quay lại node hay không.

### Loop

~~~text
for each item in order.items {
    validateItem(item);
}
~~~

Engine cần quản lý iterator, biến vòng lặp, giới hạn số lần lặp và hành vi khi collection thay đổi trong lúc duyệt. Với vòng lặp không có giới hạn tĩnh, có thể cần instruction budget hoặc timeout.

### Function call và return

Khi gọi function, engine tạo invocation frame, gán tham số, chạy thân hàm rồi khôi phục caller frame. Return kết thúc invocation hiện tại và chuyển giá trị trả về cho caller.

### Exception và control transfer

Các cấu trúc như `try/catch`, `throw`, `break`, `continue` hoặc `cancel` cần được biểu diễn rõ trong control-flow model. Engine phải xác định thứ tự unwind frame, giải phóng tài nguyên và thực hiện cleanup.

## 10. Action dispatcher và tích hợp hệ thống chủ

DSL thường cung cấp cú pháp nghiệp vụ nhưng dựa vào host application để thực hiện hành động thật. **Action dispatcher** ánh xạ lời gọi DSL đến implementation được đăng ký.

Ví dụ DSL:

~~~text
reserveInventory(order);
~~~

Runtime có thể ánh xạ `reserveInventory` đến một service adapter gọi hệ thống kho.

### Action descriptor

Một action có thể được đăng ký cùng metadata:

~~~text
ActionDescriptor
  name
  parameterTypes
  returnType
  requiredCapabilities
  timeoutPolicy
  retryPolicy
  effectCategory
~~~

Metadata giúp compiler hoặc engine kiểm tra chữ ký, quyền và chính sách thực thi trước khi gọi implementation.

### Binding action

Action có thể được bind theo tên, symbol ID hoặc registry key. Nên dùng identity ổn định thay vì chỉ tra chuỗi tên mỗi lần chạy, đặc biệt khi có namespace, version hoặc overload.

### Kiểm tra đối số

Trước khi dispatch, engine cần xác nhận số lượng và kiểu đối số. Nếu action nhận `Order` nhưng expression trả `Customer`, engine nên phát lỗi có source span của lời gọi và thông tin chữ ký mong đợi.

### Host function và capability

Không nên cho DSL gọi tùy ý mọi phương thức của host process. Engine nên chỉ công bố một tập function/action được cho phép, gắn capability và kiểm tra quyền trước khi thực thi.

## 11. Đồng bộ và bất đồng bộ

Một số action hoàn tất ngay; một số action chờ mạng, timer, người dùng hoặc hệ thống khác. Engine cần mô hình hóa rõ hai kiểu này.

### Synchronous action

Lời gọi đồng bộ trả kết quả trước khi engine tiếp tục câu lệnh tiếp theo.

~~~text
customer = loadCustomer(customerId);
validateCustomer(customer);
~~~

### Asynchronous action

Một action bất đồng bộ có thể trả future, promise hoặc một handle tác vụ. Engine có thể chờ kết quả mà không chiếm một thread trong suốt thời gian chờ.

~~~text
payment = await authorizePayment(order);
if payment.accepted {
    continueWorkflow(order);
}
~~~

DSL cần quy định `await` có thể xuất hiện ở đâu, exception được truyền như thế nào và cancellation được xử lý ra sao.

### Callback và event

Một workflow có thể tạm dừng để chờ sự kiện:

~~~text
wait for event ManagerApproved(order.id)
    timeout 2 days;
~~~

Engine cần lưu trạng thái chờ, subscription hoặc correlation key, deadline và cách resume khi event đến. Nếu process khởi động lại, trạng thái này cần được khôi phục.

### Không chặn thread không cần thiết

Nếu một workflow chờ nhiều dịch vụ ngoài, giữ một thread cho mỗi execution có thể tiêu tốn tài nguyên. Scheduler bất đồng bộ giúp engine quản lý nhiều execution với ít thread hơn, nhưng cần bảo đảm context propagation và thứ tự xử lý state.

## 12. Thực thi song song

DSL có thể mô tả các nhánh độc lập chạy đồng thời:

~~~text
parallel {
    verifyAddress(order);
    checkInventory(order);
    authorizePayment(order);
}

join all;
createShipment(order);
~~~

Engine cần xác định semantics của `parallel` và `join`.

Các chính sách thường gặp:

- **Join all:** chờ tất cả nhánh hoàn tất.
- **First completed:** tiếp tục khi nhánh đầu tiên hoàn tất.
- **First successful:** tiếp tục khi có nhánh thành công đầu tiên.
- **Quorum:** chờ một số lượng nhánh tối thiểu thành công.
- **Fail fast:** hủy các nhánh còn lại khi một nhánh lỗi.
- **Collect all errors:** chờ tất cả rồi tổng hợp lỗi.

### Race condition

Nếu các nhánh cùng sửa một đối tượng hoặc collection, thứ tự xen kẽ có thể làm kết quả khác nhau. Engine cần dùng transaction, lock, immutable data hoặc quy tắc merge để kiểm soát xung đột.

### Giới hạn concurrency

Không nên tạo số lượng thread hoặc task không giới hạn từ một chương trình DSL. Engine cần giới hạn số nhánh đồng thời, queue depth, thời gian chờ và lượng bộ nhớ.

### Hủy nhánh

Khi một nhánh thất bại hoặc workflow bị hủy, các nhánh còn lại có thể cần cancellation. Cancellation là tín hiệu hợp tác; một action host không hỗ trợ hủy có thể vẫn tiếp tục chạy. Engine phải ghi nhận trạng thái thực tế và xử lý tác dụng phụ có thể đã xảy ra.

## 13. Quản lý trạng thái workflow

Với DSL workflow, engine thường duy trì trạng thái qua nhiều bước và có thể qua nhiều process restart.

### Execution state

Một execution record có thể chứa:

~~~text
ExecutionState
  executionId
  programId
  programVersion
  status
  currentNode
  variableState
  pendingTasks
  eventSubscriptions
  retryCounters
  createdAt
  updatedAt
~~~

Các trường cụ thể phụ thuộc engine. Điều quan trọng là state phải đủ để tiếp tục đúng semantics sau khi pause hoặc restart.

### In-memory và durable execution

**In-memory execution** giữ state trong bộ nhớ process. Nó phù hợp với tác vụ ngắn, có thể chạy lại nếu process chết hoặc không cần phục hồi.

**Durable execution** lưu checkpoint và state bền vững. Nó phù hợp với workflow kéo dài hàng giờ hoặc hàng ngày, chờ approval hoặc event ngoài.

### Checkpoint

Checkpoint ghi lại trạng thái tại một điểm an toàn. Khi resume, engine nạp checkpoint, xác minh program version và dependency, rồi tiếp tục từ node hoặc instruction kế tiếp.

Checkpoint không nên lưu object Java tùy ý mà không có schema/version. Nên dùng state model có thể serialize, xác định rõ kiểu và tương thích phiên bản.

### Program version khi resume

Nếu workflow bắt đầu bằng version `v3` nhưng khi resume version hiện tại đã là `v4`, engine cần chính sách:

- Tiếp tục bằng executable version `v3` đã pin.
- Thực hiện migration state sang `v4` bằng quy tắc rõ ràng.
- Từ chối resume và yêu cầu xử lý thủ công.

Không nên tự động chạy phần còn lại của workflow bằng code mới nếu state được tạo theo semantics cũ.

## 14. Transaction và quản lý tác dụng phụ

Engine có thể điều phối các action thay đổi trạng thái hoặc tương tác với hệ thống bên ngoài. Cần xác định ranh giới transaction và hành vi khi một bước thất bại.

### Transaction cục bộ

~~~text
transaction {
    updateOrderStatus(order, APPROVED);
    recordApproval(order, reviewer);
}
~~~

Nếu các thao tác dùng cùng một database transaction, engine có thể commit tất cả hoặc rollback khi lỗi.

### Distributed transaction và saga

Một workflow có thể gọi nhiều dịch vụ độc lập:

1. Giữ hàng.
2. Thu tiền.
3. Tạo vận đơn.

Không phải hệ thống nào cũng hỗ trợ transaction phân tán nguyên tử. Engine có thể dùng saga: mỗi action có một compensation tương ứng để xử lý khi bước sau thất bại.

~~~text
saga {
    reserveInventory(order)
        compensate releaseInventory(order);

    capturePayment(order)
        compensate refundPayment(order);

    createShipment(order);
}
~~~

Compensation là một hành động nghiệp vụ mới, không nhất thiết hoàn tác chính xác mọi tác dụng phụ đã xảy ra. DSL cần quy định thứ tự compensation, xử lý khi compensation thất bại và cách vận hành tiếp theo.

### Idempotency

Một action có thể được gọi lại do retry hoặc phục hồi sau sự cố. Engine nên truyền execution ID hoặc idempotency key để service adapter có thể nhận diện yêu cầu trùng nếu hợp đồng action hỗ trợ.

Không nên giả định mọi action đều idempotent. Gửi email, thu tiền hoặc tạo vận đơn có thể tạo tác dụng phụ lặp nếu retry không được thiết kế đúng.

## 15. Xử lý lỗi và exception

Engine cần một mô hình lỗi thống nhất cho lỗi DSL, lỗi dữ liệu, lỗi action và lỗi hạ tầng.

### Nhóm lỗi

| Nhóm | Ví dụ | Cách xử lý thường gặp |
|---|---|---|
| Program error | Opcode không hợp lệ, lỗi runtime invariant | Dừng execution và ghi lỗi hệ thống. |
| Input error | Thiếu tham số hoặc sai kiểu | Từ chối trước khi chạy hoặc phát validation error. |
| DSL evaluation error | Chia cho 0, null dereference | Có thể catch theo semantics DSL hoặc dừng. |
| Action failure | Dịch vụ kho từ chối giữ hàng | Retry, branch lỗi hoặc compensation theo policy. |
| Timeout | Dịch vụ hoặc workflow quá thời hạn | Hủy, retry hoặc chuyển trạng thái timeout. |
| Authorization error | Principal không có capability | Từ chối action và ghi audit. |
| Infrastructure error | Database hoặc message broker không khả dụng | Retry có giới hạn hoặc đánh dấu failed. |
| Cancellation | Người dùng hoặc hệ thống yêu cầu hủy | Dừng an toàn và xử lý tác dụng phụ đang chạy. |

### Error propagation

Nếu một function ném exception, engine cần xác định exception được truyền lên caller, được bắt tại `try/catch`, được chuyển thành workflow failure hay được chuyển đến error handler toàn cục.

### Error boundary

Một workflow có thể định nghĩa boundary:

~~~text
try {
    reserveInventory(order);
    createShipment(order);
} catch InventoryUnavailable as error {
    notifyCustomer(order);
} catch error {
    escalateToOperations(error);
}
~~~

Engine phải xác định loại lỗi được match, thứ tự handler và hành vi nếu handler cũng thất bại.

### Retry policy

Retry policy có thể quy định số lần thử, khoảng chờ, backoff, loại lỗi có thể retry và deadline. Chỉ retry lỗi phù hợp; không nên retry lỗi validation hoặc authorization như thể đó là lỗi mạng tạm thời.

### Error source location

Execution error nên giữ source span của action hoặc expression gây lỗi, cùng call stack DSL. Nếu action gọi service bên ngoài, có thể lưu mã lỗi từ service và correlation ID riêng.

## 16. Timeout, cancellation và giới hạn tài nguyên

DSL có thể cho phép vòng lặp vô hạn, đệ quy sâu hoặc tạo nhiều tác vụ. Engine cần bảo vệ process và các dịch vụ host.

### Deadline và timeout

Deadline có thể áp dụng cho toàn execution; timeout có thể áp dụng riêng cho từng action. Khi deadline toàn cục hết hạn, engine có thể gửi cancellation đến các tác vụ đang chạy và đánh dấu execution là timed out.

### Instruction budget

VM có thể đếm số instruction đã thực hiện. Khi vượt giới hạn, engine dừng chương trình với lỗi resource limit. Cách này hữu ích để ngăn script chạy quá lâu.

### Giới hạn khác

- Maximum recursion depth.
- Maximum loop iterations.
- Maximum parallel tasks.
- Maximum memory hoặc collection size.
- Maximum output/event count.
- Maximum external calls.
- Maximum execution duration.
- Maximum serialized state size.

### Cooperative cancellation

Engine có thể kiểm tra cancellation token tại các điểm an toàn như giữa instruction, trước action hoặc trong scheduler. Action host dài hạn cần hỗ trợ cancellation riêng nếu muốn dừng thực sự.

### Giới hạn không thay thế sandbox

Instruction budget và timeout giúp kiểm soát tài nguyên nhưng không đủ để cô lập mã không tin cậy. Engine vẫn cần kiểm soát quyền truy cập file, mạng, process, reflection, class loading và các API host.

## 17. Bảo mật và sandbox

DSL có thể được viết bởi người dùng nghiệp vụ, khách hàng hoặc plugin bên ngoài. Engine phải giả định chương trình có thể chứa hành vi không mong muốn và giới hạn những gì nó được phép làm.

### Capability-based execution

Thay vì cấp toàn bộ quyền của host process, engine cung cấp tập capability cụ thể:

~~~text
ExecutionCapabilities
  readOrder
  updateOrderStatus
  reserveInventory
  emitAuditEvent
~~~

Một execution chỉ có thể gọi action được cấp. Dispatcher kiểm tra capability trước khi gọi host service.

### Principle of least privilege

Mỗi chương trình chỉ nên nhận quyền tối thiểu cần thiết. Một policy chỉ đọc dữ liệu không cần quyền gửi email hoặc ghi database. Quyền nên được gắn với principal, tenant, môi trường và mục tiêu action.

### Không thực thi mã tùy ý

Không nên triển khai DSL bằng cách ghép văn bản người dùng vào `eval`, shell command hoặc source code rồi chạy trực tiếp nếu không có sandbox mạnh và kiểm soát đầy đủ. Một interpreter hoặc VM có tập instruction giới hạn thường dễ kiểm soát hơn.

### Resource isolation

Engine có thể giới hạn CPU, memory, thread, I/O, network call và thời gian chạy. Với môi trường nhiều tenant, quota cần được áp dụng theo execution hoặc tenant để một chương trình không chiếm hết tài nguyên của hệ thống.

### Data access control

Quyền cần được kiểm tra tại thời điểm action hoặc data access thực hiện, không chỉ khi compile. Quyền có thể thay đổi giữa lúc tạo workflow và lúc chạy.

### Audit

Các thao tác nhạy cảm cần ghi nhận ai chạy, chương trình/version nào được dùng, action nào được gọi, tài nguyên nào bị tác động và kết quả ra sao. Audit record cần tuân theo chính sách bảo vệ dữ liệu.

## 18. Scheduler và quản lý tác vụ

Scheduler quyết định khi nào một execution hoặc task được tiếp tục. Nó đặc biệt quan trọng với workflow bất đồng bộ và engine xử lý nhiều execution đồng thời.

### Queue

Một execution có thể được đưa vào queue trước khi chạy. Queue giúp giới hạn concurrency, áp dụng priority và phân phối công việc cho nhiều worker.

### Timer

DSL có thể yêu cầu chờ đến một thời điểm hoặc trong một khoảng thời gian. Scheduler cần quản lý timer bền vững nếu workflow phải sống qua process restart.

### Event subscription

Workflow có thể chờ event theo correlation key. Scheduler hoặc event router cần bảo đảm event được chuyển đến đúng execution và xử lý duplicate theo semantics đã chọn.

### Fairness và priority

Nếu execution có priority, engine cần quy định cách xử lý khi nhiều task cùng mức. Nếu không, một task có thể bị starvation. Fair scheduling hoặc quota theo tenant có thể giúp hệ thống công bằng hơn.

### Worker pool

Worker pool giới hạn số task đồng thời. Kích thước pool cần dựa trên loại công việc: CPU-bound và I/O-bound có đặc tính khác nhau. Không nên tạo thread mới cho mỗi DSL execution mà không có giới hạn.

## 19. Engine thực thi cho các loại DSL khác nhau

Kiến trúc engine phụ thuộc loại DSL và semantics mà ngôn ngữ cung cấp.

| Loại DSL | Trọng tâm engine | Ví dụ năng lực |
|---|---|---|
| Expression DSL | Đánh giá biểu thức và kiểu giá trị | Arithmetic, boolean, function call. |
| Rule DSL | Match điều kiện và chọn rule | Agenda, priority, conflict resolution. |
| Workflow DSL | Điều phối trạng thái qua nhiều bước | Wait, retry, timer, event, compensation. |
| Query DSL | Tạo và thực thi truy vấn | Query plan, parameter binding, result streaming. |
| Configuration DSL | Chuyển cấu hình thành resource hoặc action | Validation, dependency ordering, apply/rollback. |
| Model transformation DSL | Duyệt và biến đổi mô hình | Transformation passes, traceability, transaction. |
| Infrastructure DSL | Provision và quản lý tài nguyên | Plan, apply, drift detection, state backend. |
| Simulation DSL | Chạy mô hình theo thời gian hoặc sự kiện | Clock, random seed, event queue, reproducibility. |

### Rule engine

Rule engine thường cần cơ chế match dữ kiện, agenda, priority, activation và xử lý xung đột. Engine cần xác định rule được chạy một lần hay nhiều lần khi dữ kiện thay đổi.

### Workflow engine

Workflow engine cần state persistence, scheduler, event correlation, timeout, retry, versioning và recovery. Nó thường quản lý execution dài hạn thay vì chỉ trả một giá trị.

### Query engine

Query engine cần parser, logical plan, optimizer, physical plan, connector và result streaming. Một query có thể chạy trên database hoặc nhiều nguồn dữ liệu.

### Configuration/infrastructure engine

Engine có thể tạo execution plan từ desired state, so sánh với actual state rồi áp dụng thay đổi. Nó cần dependency ordering, rollback hoặc reconciliation và quản lý quyền trên tài nguyên.

## 20. Phiên bản chương trình và tương thích runtime

Một executable artifact cần gắn với phiên bản ngôn ngữ, compiler và runtime tương thích.

### Program identity

Có thể định danh chương trình bằng:

- Program ID.
- Program version hoặc content hash.
- DSL language version.
- Compiler/IR version.
- Dependency fingerprint.
- Runtime capability requirements.

### Runtime compatibility check

Trước khi chạy, engine cần kiểm tra artifact có yêu cầu opcode, type hoặc runtime capability mà engine hiện tại không hỗ trợ hay không. Không nên cố chạy artifact sai phiên bản rồi để lỗi xuất hiện giữa workflow.

### Workflow đang chạy khi chương trình được cập nhật

Một workflow có thể đã chạy bằng version cũ trong khi version mới được publish. Engine cần chính sách pin version, migration hoặc dừng. Các execution đã bắt đầu thường nên giữ version rõ ràng để có thể giải thích và replay.

### Migration

Nếu cần chuyển state sang version mới, migration phải xác định cách đổi tên biến, chuyển node hiện tại, ánh xạ trạng thái và xử lý các action đã hoàn tất. Không phải mọi workflow đều có thể migrate an toàn.

## 21. Persistence và phục hồi sau sự cố

Engine workflow dài hạn cần phục hồi sau process crash, mất kết nối hoặc triển khai phiên bản mới.

### Durable state

Trạng thái cần lưu đủ để tiếp tục:

- Execution status và current node.
- Biến và dữ liệu cần thiết.
- Các action đã hoàn tất và kết quả.
- Các task đang chờ hoặc timer.
- Retry counter và deadline.
- Program version và dependency snapshot.
- Correlation ID và metadata cần cho audit.

### Checkpoint frequency

Checkpoint sau mỗi bước giúp phục hồi chính xác nhưng tăng I/O. Checkpoint thưa giảm chi phí nhưng có thể phải chạy lại nhiều công việc sau sự cố. Cần cân bằng theo độ dài workflow và mức độ tác dụng phụ.

### At-least-once và exactly-once

Một worker có thể thực hiện action rồi crash trước khi ghi nhận hoàn tất. Khi khôi phục, engine không biết action đã thành công hay chưa và có thể gọi lại. Nhiều hệ thống thực tế cung cấp at-least-once delivery; exactly-once end-to-end rất khó nếu action bên ngoài không hỗ trợ idempotency hoặc transaction chung.

Engine nên mô tả guarantee thực tế và thiết kế action adapter để xử lý duplicate. Không nên tuyên bố exactly-once chỉ vì state store có transaction.

### Recovery procedure

Khi worker khởi động lại, engine có thể:

1. Đọc execution đang hoạt động.
2. Xác minh program version và schema state.
3. Xác định action nào đã commit và action nào còn pending.
4. Khôi phục timer/event subscription.
5. Tiếp tục từ checkpoint an toàn.
6. Phát hiện execution không thể phục hồi và chuyển sang trạng thái cần can thiệp.

## 22. Kết quả, sự kiện và execution trace

Engine có thể tạo nhiều loại đầu ra:

- Giá trị trả về của chương trình.
- Trạng thái workflow cuối.
- Sự kiện nghiệp vụ.
- Kết quả từng action.
- Diagnostic hoặc lỗi runtime.
- Execution trace và audit record.

### Return value

Với expression DSL hoặc function DSL, kết quả có thể là một giá trị có kiểu.

### Event output

Một workflow có thể phát `OrderApproved` hoặc `ShipmentCreated`. Engine cần xác định event được phát khi nào, có nằm trong transaction hay không và cách xử lý publish failure.

### Execution trace

Trace có thể ghi nhận:

~~~text
Execution E-100
  1. Enter workflow ProcessOrder
  2. Call validateOrder -> success
  3. Evaluate paymentStatus == ACCEPTED -> true
  4. Call reserveInventory -> success
  5. Call createShipment -> success
  6. Complete workflow
~~~

Trace giúp hiểu đường đi thực tế của chương trình. Trong môi trường nhiều tenant, cần tránh ghi trực tiếp dữ liệu nhạy cảm vào trace nếu không cần thiết.

### Correlation và causation

Execution ID liên kết log và state của cùng một lần chạy. Correlation ID có thể liên kết nhiều execution thuộc cùng một nghiệp vụ. Causation ID giúp xác định event hoặc action nào đã kích hoạt bước tiếp theo.

## 23. Observability: log, metrics và tracing

Một engine cần được quan sát khi chạy trong môi trường thật. Chỉ log “execution failed” thường không đủ để tìm nguyên nhân.

### Logging

Log nên chứa execution ID, program/version, node hoặc action, trạng thái, duration và mã lỗi. Không nên ghi toàn bộ input hoặc secret một cách mặc định.

### Metrics

Các metrics hữu ích:

- Số execution đang chạy, chờ, thành công và thất bại.
- Thời gian thực thi tổng và theo action.
- Queue wait time và scheduler delay.
- Số lần retry, timeout và cancellation.
- Số instruction hoặc node đã xử lý.
- Memory và CPU usage.
- Số action call và lỗi theo connector.
- Độ trễ checkpoint và persistence.

### Distributed tracing

Nếu action gọi nhiều service, trace có thể tạo span cho từng bước và truyền trace context qua connector. Điều này giúp phân biệt thời gian engine xử lý với thời gian chờ dịch vụ ngoài.

### DSL-level trace

Trace nên dùng tên rule, workflow, action và source location của DSL. Stack trace Java hoặc stack trace của host runtime vẫn hữu ích cho lỗi implementation, nhưng không thay thế góc nhìn của người viết DSL.

## 24. Debugger cho engine thực thi

Debugger giúp người dùng quan sát và điều khiển execution ở mức khái niệm của DSL.

Các khả năng phổ biến:

- Breakpoint tại rule, action, statement hoặc node workflow.
- Step over, step into và step out.
- Pause, resume và cancel.
- Xem giá trị biến và scope hiện tại.
- Xem node hoặc instruction tiếp theo.
- Xem call stack DSL.
- Xem các nhánh điều kiện và rule đã match.
- Xem action request/response theo quyền.
- Điều hướng từ runtime error về source span.

### Breakpoint theo source mapping

Nếu engine chạy IR hoặc bytecode, breakpoint cần ánh xạ source location sang instruction range. Một câu lệnh DSL có thể sinh nhiều instruction; breakpoint nên dừng ở ranh giới phù hợp và hiển thị source statement gốc.

### Debug execution bất đồng bộ

Với workflow chờ event, debugger cần hiển thị trạng thái `Suspended`, nguyên nhân chờ, deadline và subscription. Khi event đến, debugger tiếp tục trace từ điểm resume.

### Điều khiển có kiểm soát

Pause hoặc step có thể làm thay đổi timing của hệ thống. Debugger production cần quyền truy cập và chính sách rõ ràng, đặc biệt khi execution có tác dụng phụ.

## 25. Thiết kế API của execution engine

API engine nên tách thao tác chuẩn bị chương trình khỏi thao tác tạo execution.

Ví dụ API khái niệm:

~~~java
interface ExecutionEngine {
    ExecutableProgram load(ProgramId programId, ProgramVersion version);

    ExecutionHandle start(
        ExecutableProgram program,
        ExecutionInput input,
        ExecutionOptions options
    );

    ExecutionStatus getStatus(ExecutionId id);

    ExecutionResult getResult(ExecutionId id);

    void cancel(ExecutionId id);
}
~~~

`ExecutionHandle` có thể cung cấp future, stream event hoặc ID để truy vấn trạng thái. Với engine workflow bền vững, `start` có thể trả về ngay execution ID thay vì chờ toàn bộ workflow kết thúc.

### Execution options

Options có thể gồm deadline, priority, locale, timezone, resource budget, trace level và policy version. Các tùy chọn ảnh hưởng semantics phải được xác định và ghi nhận.

### API action registry

Host application có thể đăng ký action descriptor và implementation. Engine cần kiểm tra registry phù hợp với program artifact trước khi chạy, đặc biệt khi action version thay đổi.

### Tách API quản trị

Các thao tác xem trace, retry, resume, terminate hoặc sửa state nên có API quản trị riêng với quyền kiểm soát chặt chẽ. Không nên để một chương trình DSL tự cấp quyền cho chính nó.

## 26. Ví dụ interpreter biểu thức bằng Java

Giả sử DSL hỗ trợ literal số, biến và phép cộng. Có thể mô hình hóa AST:

~~~java
sealed interface Expr
    permits NumberExpr, NameExpr, AddExpr {}

record NumberExpr(java.math.BigDecimal value) implements Expr {}

record NameExpr(String name) implements Expr {}

record AddExpr(Expr left, Expr right) implements Expr {}
~~~

Một evaluator đơn giản:

~~~java
final class ExpressionEvaluator {
    private final Map<String, java.math.BigDecimal> variables;

    ExpressionEvaluator(Map<String, java.math.BigDecimal> variables) {
        this.variables = Map.copyOf(variables);
    }

    java.math.BigDecimal evaluate(Expr expr) {
        return switch (expr) {
            case NumberExpr number -> number.value();
            case NameExpr name -> {
                java.math.BigDecimal value = variables.get(name.name());
                if (value == null) {
                    throw new IllegalArgumentException(
                        "Unknown variable: " + name.name()
                    );
                }
                yield value;
            }
            case AddExpr add -> evaluate(add.left())
                .add(evaluate(add.right()));
        };
    }
}
~~~

Đây là interpreter tối giản để minh họa. Engine thực tế cần xử lý kiểu giá trị phong phú hơn, scope lồng nhau, source span, diagnostic có cấu trúc, giới hạn recursion và cancellation. Nếu DSL có nhiều kiểu số, phép cộng cũng cần dispatch theo type system thay vì giả định mọi giá trị đều là `BigDecimal`.

### Mở rộng thành execution context

Thay vì truyền map biến trực tiếp, có thể dùng `Environment` quản lý frame cha–con, function binding và runtime values. Cách này giúp hỗ trợ block scope, function call và closure mà không làm evaluator phụ thuộc vào cấu trúc map đơn giản.

## 27. Ví dụ engine thực thi workflow

Giả sử workflow:

~~~text
workflow OrderFulfillment(order: Order) {
    validateOrder(order);

    reserveInventory(order) retry 3 times;

    try {
        capturePayment(order);
    } catch PaymentDeclined {
        releaseInventory(order);
        rejectOrder(order);
        return;
    }

    createShipment(order);
    emit OrderFulfilled(order.id);
}
~~~

Engine có thể thực hiện theo trình tự:

1. Kiểm tra `OrderFulfillment` đã được compile và version tương thích.
2. Xác thực input `order` và quyền thực thi.
3. Tạo execution ID, context và state ban đầu.
4. Dispatch `validateOrder`.
5. Dispatch `reserveInventory` với retry policy tối đa ba lần.
6. Ghi nhận kết quả giữ hàng.
7. Dispatch `capturePayment` trong error boundary.
8. Nếu payment bị từ chối, chạy nhánh catch, giải phóng hàng và từ chối đơn.
9. Nếu payment thành công, tạo shipment.
10. Phát event `OrderFulfilled` theo semantics publish đã định nghĩa.
11. Đánh dấu execution hoàn tất và lưu kết quả.

Trong workflow thật, mỗi action có thể là một dịch vụ bên ngoài. Engine cần xử lý timeout, retry, duplicate, process crash và khả năng compensation. Một dòng DSL không nhất thiết tương ứng với một transaction duy nhất.

## 28. Hiệu năng của engine

Hiệu năng phụ thuộc vào chi phí dispatch, biểu diễn giá trị, allocation, call host service, scheduling và persistence.

### Giảm chi phí dispatch

VM có thể dùng opcode compact hoặc dispatch table. Interpreter AST có thể dùng visitor, pattern matching hoặc node-specific evaluator. Cần đo workload thực tế trước khi chọn kỹ thuật.

### Compile trước

Nếu cùng chương trình được chạy nhiều lần, compile AST sang IR/bytecode một lần rồi tái sử dụng có thể giảm chi phí chuẩn bị. Artifact phải được version hóa và xác minh.

### Cache runtime metadata

Engine có thể cache action descriptor, resolved symbol hoặc property accessor nếu dependency và quyền được quản lý đúng. Không cache kết quả phụ thuộc dữ liệu động chỉ vì lookup metadata có thể cache.

### Streaming và backpressure

Với DSL xử lý nhiều bản ghi hoặc event, engine nên hỗ trợ streaming và backpressure thay vì nạp toàn bộ dữ liệu vào memory. Consumer chậm cần làm producer giảm tốc hoặc buffer có giới hạn.

### Batching

Nhiều action cùng loại có thể được gom thành batch nếu semantics cho phép. Batching giảm network round trips nhưng cần xác định thứ tự, lỗi từng phần tử và cách retry.

### Profiling

Profiler nên phân biệt thời gian evaluator, scheduler, persistence và service call. Nếu 95% thời gian chờ database, tối ưu dispatch AST sẽ không cải thiện đáng kể tổng latency.

## 29. Tính xác định và khả năng tái lập

Engine nên làm rõ điều kiện để cùng chương trình và cùng input tạo cùng hành vi. Kết quả có thể phụ thuộc clock, random seed, thứ tự collection, dữ liệu ngoài hoặc lịch chạy song song.

Để tăng khả năng tái lập:

- Ghi nhận program version và dependency fingerprint.
- Truyền clock và random seed qua execution context khi cần.
- Quy định thứ tự đánh giá và conflict resolution.
- Dùng snapshot dữ liệu hoặc ghi nhận version đã đọc.
- Ghi execution trace và action result cần thiết.
- Không dựa vào thứ tự của collection không có thứ tự.
- Xác định semantics của concurrency và event ordering.

Không phải DSL nào cũng cần deterministic execution hoàn toàn. DSL mô phỏng có thể cần ngẫu nhiên; workflow phân tán có thể có nhiều lịch hợp lệ. Trong trường hợp đó, engine cần lưu đủ thông tin để giải thích hoặc tái hiện lần chạy cụ thể.

## 30. Tương tác với cache và artifact

Engine thường dùng artifact cache để tránh load/compile lại chương trình. Runtime result cache hoặc memoization có thể được sử dụng riêng cho các phép tính thuần.

### Executable artifact cache

Key có thể gồm source fingerprint, compiler version, language version, target và dependency fingerprint. Engine chỉ nạp artifact nếu verifier xác nhận tương thích.

### Không cache toàn bộ execution một cách tùy tiện

Execution có tác dụng phụ, đọc dữ liệu động hoặc phụ thuộc quyền. Việc trả lại kết quả của lần chạy trước có thể bỏ qua hành động cần thực hiện. Chỉ cache kết quả của phép tính có hợp đồng rõ ràng về purity, dependency và freshness.

### Cache và program version

Một execution nên gắn với executable version cụ thể. Nếu chương trình được cập nhật trong lúc execution đang chạy, engine không nên âm thầm thay instruction còn lại bằng version mới trừ khi có cơ chế migration được thiết kế rõ.

## 31. Kiểm thử engine thực thi

Engine cần được kiểm thử ở nhiều cấp: semantics của biểu thức, control flow, action integration, persistence, concurrency và khả năng phục hồi.

### Unit test cho evaluator

Kiểm tra literal, variable lookup, arithmetic, comparison, short-circuit, null handling và type error.

### Control-flow test

Kiểm tra branch, loop, function call, recursion, return, exception và cancellation.

### Action dispatch test

Xác nhận đúng action được gọi, đúng tham số, capability được kiểm tra và timeout/retry được áp dụng.

### Workflow integration test

Chạy một workflow hoàn chỉnh với fake service hoặc test environment. Kiểm tra state transition, event output và kết quả cuối.

### Persistence and recovery test

Checkpoint execution, dừng process mô phỏng, khởi động lại engine và xác nhận workflow resume đúng node, không lặp tác dụng phụ ngoài hợp đồng.

### Concurrency test

Chạy nhiều execution và nhiều branch song song, kiểm tra race condition, quota, isolation và state consistency.

### Security test

Thử gọi action không có capability, truy cập dữ liệu tenant khác, vượt resource budget và thực hiện API host không được phép. Engine phải từ chối tại ranh giới runtime.

### Differential test

Nếu có AST interpreter và VM bytecode, chạy cùng chương trình trên hai engine và so sánh kết quả quan sát được. Đây là cách phát hiện khác biệt semantics giữa hai backend.

## 32. Ví dụ bộ kiểm thử cho workflow

Với workflow `OrderFulfillment`, có thể xây dựng các tình huống:

| Tình huống | Kết quả mong đợi |
|---|---|
| Đơn hợp lệ, payment thành công | Giữ hàng, thu tiền, tạo shipment, phát event và complete. |
| Validate thất bại | Dừng trước khi gọi action tiếp theo. |
| Reserve thất bại tạm thời | Retry theo giới hạn và backoff. |
| Reserve thất bại vĩnh viễn | Chuyển execution sang failed hoặc error branch. |
| Payment bị từ chối | Chạy compensation/nhánh từ chối theo đặc tả. |
| Shipment service timeout | Áp dụng timeout/retry policy; không tạo event hoàn tất sai. |
| Execution bị cancel | Ngừng các bước tiếp theo và xử lý action đang chạy theo hợp đồng. |
| Process crash sau action | Recovery không lặp tác dụng phụ nếu action có idempotency guarantee. |
| Principal thiếu quyền | Từ chối trước action nhạy cảm và ghi audit. |
| Program version thay đổi | Execution tiếp tục theo version đã pin hoặc migration được phê duyệt. |

Các test cần xác nhận cả state cuối, action call count, event trace và diagnostic, không chỉ kiểm tra một giá trị trả về.

## 33. Những lỗi thiết kế thường gặp

**Đồng nhất engine với interpreter.** Engine còn quản lý context, action, scheduler, persistence, security và lifecycle. Chỉ có evaluator là chưa đủ cho workflow production.

**Để semantics phụ thuộc vào host runtime một cách ngầm định.** Thứ tự đánh giá, số học, null, exception và concurrency phải được DSL định nghĩa.

**Cho phép DSL gọi tùy ý API host.** Điều này làm mất ranh giới bảo mật và khiến chương trình khó kiểm soát. Nên dùng action registry và capability.

**Dùng global mutable state giữa các execution.** Dữ liệu có thể rò rỉ giữa người dùng hoặc tenant. Context và state cần ownership rõ ràng.

**Không giới hạn tài nguyên.** Vòng lặp vô hạn, recursion sâu hoặc task fan-out có thể làm cạn CPU, memory và thread.

**Retry mọi lỗi.** Lỗi validation hoặc authorization thường không thể khắc phục bằng retry; retry action có tác dụng phụ có thể tạo thao tác trùng.

**Giả định transaction phân tán là nguyên tử.** Nhiều service không cùng một database transaction. Cần saga, compensation hoặc semantics lỗi rõ ràng.

**Không lưu program version trong execution.** Workflow đang chạy có thể tiếp tục bằng semantics khác sau khi publish phiên bản mới.

**Không quản lý trạng thái chờ bền vững.** Workflow dài hạn có thể mất timer, subscription hoặc current node sau restart.

**Không truyền context qua async boundary.** Principal, tenant, trace và cancellation có thể bị mất khi task đổi thread.

**Không ánh xạ lỗi về source DSL.** Người dùng chỉ thấy stack trace nội bộ mà không biết rule hoặc action nào gây lỗi.

**Tuyên bố exactly-once thiếu cơ sở.** Action ngoài có thể đã thành công trước khi worker crash; cần idempotency và recovery protocol.

**Tối ưu trước khi đo.** Giảm chi phí AST dispatch không có ích nếu bottleneck là network hoặc persistence.

## 34. Quy trình thiết kế execution engine

Một quy trình thực tế có thể gồm:

1. **Xác định loại DSL:** expression, rule, workflow, query, configuration hay model transformation.
2. **Đặc tả semantics:** giá trị, thứ tự đánh giá, control flow, lỗi, tác dụng phụ và concurrency.
3. **Chọn execution model:** AST interpreter, IR interpreter, VM, generated code hoặc mô hình lai.
4. **Định nghĩa runtime values:** kiểu dữ liệu, equality, null, conversion và entity reference.
5. **Thiết kế execution context:** input, principal, tenant, clock, services, deadline và trace.
6. **Thiết kế control-flow model:** sequence, branch, loop, call, return, exception và suspension.
7. **Thiết kế action registry:** chữ ký, capability, timeout, retry và effect category.
8. **Thiết kế scheduler:** queue, worker pool, timer, event và concurrency limits.
9. **Quản lý state:** frame, execution state, checkpoint, persistence và version pinning.
10. **Xử lý transaction:** commit, rollback, saga, compensation và idempotency.
11. **Bảo mật:** sandbox, least privilege, resource budget và tenant isolation.
12. **Observability:** log, metrics, trace, source mapping và debugger.
13. **Kiểm thử:** evaluator, workflow, failure, recovery, concurrency và security.
14. **Đo hiệu năng:** profile evaluator, scheduler, connector và persistence trên workload thực tế.

## 35. Checklist cho một engine mới

Trước khi đưa engine vào sử dụng, cần trả lời:

- Engine nhận AST, IR, bytecode hay artifact nào?
- Artifact được version hóa và xác minh trước khi chạy ra sao?
- Ngữ nghĩa expression và control flow có được định nghĩa đầy đủ không?
- Execution context chứa những đầu vào và capability nào?
- Biến, scope, closure và runtime value được quản lý thế nào?
- Action được resolve và dispatch bằng identity nào?
- Quyền được kiểm tra ở thời điểm nào?
- Async, parallel, timer và event được điều phối ra sao?
- Có giới hạn CPU, memory, recursion, task và thời gian không?
- Lỗi, retry, timeout, cancellation và compensation hoạt động thế nào?
- Execution state có cần durable persistence không?
- Workflow resume bằng program version nào?
- Action có idempotency contract không?
- Diagnostic có ánh xạ về source DSL không?
- Log, trace và audit có đủ để điều tra nhưng không lộ dữ liệu nhạy cảm không?
- Engine được kiểm thử bằng các backend hoặc interpreter khác nhau như thế nào?

## 36. Kết quả cần có sau khi thiết kế engine thực thi

Một thiết kế execution engine đầy đủ thường tạo ra:

- **Execution model:** AST interpreter, IR interpreter, VM, generated code hoặc kiến trúc lai.
- **Runtime architecture:** loader, verifier, evaluator, value manager, dispatcher, scheduler và state store.
- **Execution lifecycle:** created, validating, ready, running, suspended, completed, failed và cancelled.
- **Execution context:** input, scope, principal, tenant, clock, service capabilities, deadline và trace context.
- **Semantics runtime:** expression evaluation, control flow, function call, exception và concurrency.
- **Action contract:** chữ ký, quyền, timeout, retry, side effects và idempotency.
- **State/persistence model:** checkpoint, durable execution, version pinning và recovery.
- **Failure model:** error propagation, cancellation, compensation và operational recovery.
- **Security model:** sandbox, least privilege, resource quota và isolation.
- **Observability model:** log, metrics, distributed trace, DSL trace và debugger.
- **Test strategy:** evaluator, integration, recovery, concurrency, security và differential testing.
- **Performance strategy:** profiling, batching, streaming, cache và giới hạn tài nguyên.

Engine thực thi là thành phần biến semantics của DSL thành hành vi thực tế. Một engine đáng tin cậy cần xác định rõ cách đánh giá biểu thức, điều khiển luồng, quản lý context, gọi action, xử lý bất đồng bộ và duy trì trạng thái. Với workflow dài hạn hoặc hệ thống phân tán, nó còn phải giải quyết persistence, retry, compensation, versioning và phục hồi sau sự cố. Khi runtime có ranh giới bảo mật, giới hạn tài nguyên, diagnostic gắn với source DSL và khả năng quan sát đầy đủ, chương trình DSL mới có thể được thực thi an toàn, dự đoán được và vận hành ổn định trong ứng dụng thực tế.
