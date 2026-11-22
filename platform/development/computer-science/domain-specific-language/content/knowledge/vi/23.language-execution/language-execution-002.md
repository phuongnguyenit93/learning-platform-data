# Bối cảnh đánh giá

Khi thực thi một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), một biểu thức hoặc câu lệnh không thể được hiểu chỉ từ văn bản của nó. Hệ thống còn cần biết các tên đang tham chiếu đến giá trị nào, kiểu dữ liệu của những giá trị đó, đối tượng nào đang được xử lý, những hàm hoặc dịch vụ nào được phép gọi và trạng thái thực thi hiện tại ra sao. Tập hợp thông tin mà bộ đánh giá sử dụng tại một thời điểm được gọi là **bối cảnh đánh giá (evaluation context)**.

Ví dụ, DSL có biểu thức:

~~~text
order.total * taxRate
~~~

Để tính được biểu thức, runtime cần tìm giá trị của order, đọc thuộc tính total từ đối tượng đó và tìm taxRate trong môi trường hiện tại. Nếu order.total là 1.000.000 và taxRate là 0,1, kết quả có thể là 100.000 theo quy tắc số học của DSL.

Nếu cùng biểu thức được đánh giá trong một workflow khác, taxRate có thể có giá trị khác. Cấu trúc biểu thức không đổi nhưng kết quả thay đổi vì bối cảnh đánh giá khác nhau.

Bối cảnh đánh giá giúp runtime xác định ý nghĩa của biểu thức tại thời điểm thực thi. Nó thường chứa môi trường biến, tham số, hàm, kiểu, đối tượng hiện tại, dịch vụ được cấp quyền và thông tin điều khiển cần thiết. Thiết kế đúng bối cảnh đánh giá giúp DSL hỗ trợ phạm vi lồng nhau, hàm, closure, workflow, biểu thức phụ thuộc ngữ cảnh và thực thi an toàn.

## 1. Bối cảnh đánh giá là gì?

Bối cảnh đánh giá là tập hợp dữ liệu và dịch vụ mà evaluator cần truy cập để tính giá trị của một biểu thức hoặc thực hiện một câu lệnh.

Một mô hình khái quát:

~~~text
EvaluationContext
  variableEnvironment
  functionEnvironment
  typeEnvironment
  currentObject
  runtimeServices
  executionMetadata
~~~

Các thành phần có thể gồm:

- **Variable environment:** ánh xạ tên biến và tham số đến giá trị hiện tại.
- **Function environment:** tập hàm, action hoặc operation có thể gọi.
- **Type environment:** thông tin kiểu và các quy tắc chuyển đổi.
- **Current object:** đối tượng hoặc thực thể đang được xử lý, nếu DSL có khái niệm này.
- **Runtime services:** đồng hồ, bộ truy cập dữ liệu, dịch vụ miền hoặc capability được cấp cho chương trình.
- **Execution metadata:** vị trí nguồn, định danh workflow, thông tin trace, giới hạn thực thi và dữ liệu điều khiển.

Không phải DSL nào cũng cần tất cả thành phần. Một DSL biểu thức số học có thể chỉ cần môi trường biến và hàm toán học. Một DSL workflow có thể cần biến, action, đối tượng hiện tại, transaction và thông tin thực thi.

### 1.1. Bối cảnh phụ thuộc vào thời điểm đánh giá

Cùng một biểu thức có thể cho kết quả khác nhau trong hai bối cảnh:

~~~text
Expression:
  price * quantity

Context A:
  price = 100
  quantity = 2

Context B:
  price = 150
  quantity = 3
~~~

Kết quả:

| Bối cảnh | price | quantity | Kết quả |
| --- | ---: | ---: | ---: |
| A | 100 | 2 | 200 |
| B | 150 | 3 | 450 |

Bối cảnh không nhất thiết là một bản sao của toàn bộ trạng thái ứng dụng. Nó chỉ cần cung cấp những gì biểu thức được phép quan sát và sử dụng.

### 1.2. Bối cảnh không phải bản thân biểu thức

Biểu thức mô tả phép tính; bối cảnh cung cấp các giá trị và dịch vụ để phép tính đó có thể diễn ra.

~~~text
Expression + Evaluation Context
              |
              v
           Evaluator
              |
              v
          Result / Error
~~~

Việc tách hai khái niệm này cho phép cùng một AST được đánh giá nhiều lần với dữ liệu khác nhau mà không cần parse lại biểu thức.

### 1.3. Bối cảnh có thể thay đổi hoặc bất biến

Một DSL có thể dùng bối cảnh bất biến, tạo bối cảnh con khi vào scope mới, hoặc dùng môi trường có thể cập nhật khi câu lệnh gán chạy.

- Bối cảnh bất biến giúp việc đánh giá dễ dự đoán và an toàn khi chạy đồng thời.
- Môi trường có thể cập nhật phù hợp với ngôn ngữ có biến thay đổi.
- Bối cảnh kết hợp có thể giữ metadata bất biến nhưng cho phép một vùng lưu trữ biến được cập nhật.

Lựa chọn phụ thuộc semantics của DSL. Điều quan trọng là phải xác định rõ thao tác nào tạo bối cảnh mới và thao tác nào thay đổi trạng thái.

## 2. Bối cảnh đánh giá trong pipeline thực thi DSL

Bối cảnh đánh giá thường được tạo sau khi chương trình đã được phân tích và kiểm tra ở mức phù hợp.

~~~text
Văn bản DSL
    |
    v
Lexer và Parser
    |
    v
AST
    |
    v
Phân giải tên và kiểm tra kiểu
    |
    v
Chương trình đã liên kết
    |
    v
Tạo Evaluation Context
    |
    v
Evaluator / Interpreter
    |
    v
Kết quả hoặc lỗi thực thi
~~~

Ví dụ, parser tạo AST cho biểu thức:

~~~text
customer.address.city
~~~

Name resolver xác định customer là biến hoặc tham số hợp lệ, address là thuộc tính của kiểu Customer và city là thuộc tính của kiểu Address. Khi chạy, evaluator dùng bối cảnh hiện tại để lấy giá trị customer rồi truy cập từng thuộc tính.

Nếu customer chưa có giá trị, evaluator cần áp dụng chính sách của DSL: báo lỗi, trả về giá trị null, dùng phép truy cập an toàn hoặc dừng biểu thức. Đây là quyết định ngữ nghĩa, không nên để mỗi node AST tự chọn cách xử lý khác nhau.

### 2.1. Bối cảnh được tạo ở đâu?

Một runtime có thể tạo bối cảnh ở các cấp:

- Khi bắt đầu chạy một chương trình DSL.
- Khi bắt đầu một workflow.
- Khi gọi một operation.
- Khi vào một block hoặc nhánh điều kiện.
- Khi gọi một hàm.
- Khi đánh giá một biểu thức con.
- Khi xử lý một sự kiện hoặc một bản ghi dữ liệu.

Bối cảnh cấp cao thường cung cấp cấu hình và dịch vụ chung. Bối cảnh cấp thấp bổ sung biến cục bộ, tham số hoặc đối tượng hiện tại.

### 2.2. Bối cảnh và AST

AST thường không lưu giá trị runtime của biến. Một node tham chiếu tên có thể giữ liên kết đến symbol đã phân giải, còn evaluator tra giá trị của symbol trong environment tại thời điểm chạy.

Ví dụ, AST có thể chứa một NameReference trỏ đến symbol của taxRate. Bối cảnh lần chạy thứ nhất ánh xạ symbol đó thành 0,1; lần chạy thứ hai ánh xạ thành 0,08.

Cách này giữ AST độc lập với từng lần chạy và hỗ trợ tái sử dụng chương trình đã biên dịch.

## 3. Phân biệt evaluation context, environment và execution context

Các tài liệu có thể dùng những thuật ngữ này theo cách khác nhau. Khi thiết kế DSL, nên định nghĩa rõ phạm vi của từng khái niệm.

### 3.1. Environment

Environment thường là cấu trúc lưu các binding: tên hoặc symbol liên kết với giá trị.

~~~text
Environment
  taxRate -> 0.1
  currency -> "VND"
  order -> OrderObject(...)
~~~

Environment tập trung vào việc phân giải tên và lấy giá trị.

### 3.2. Evaluation context

Evaluation context là đối tượng rộng hơn, có thể bao gồm environment cùng các thành phần cần thiết để đánh giá:

~~~text
EvaluationContext
  environment
  currentObject
  functions
  runtimeServices
  typeSystem
~~~

Một evaluator có thể nhận context thay vì nhận riêng từng map và dịch vụ.

### 3.3. Execution context

Execution context thường mô tả lần chạy hoặc luồng điều khiển:

~~~text
ExecutionContext
  executionId
  workflowId
  cancellationToken
  deadline
  transaction
  trace
~~~

Nó có thể chứa thông tin theo dõi, giới hạn thời gian, trạng thái hủy và transaction. Những thông tin này không nhất thiết tham gia vào việc phân giải biến.

### 3.4. Cách tổ chức trong một runtime

Một thiết kế có thể kết hợp các khái niệm:

~~~text
ExecutionSession
  |
  +-- ExecutionContext
  |
  +-- EvaluationContext
        |
        +-- Environment
        +-- FunctionRegistry
        +-- RuntimeCapabilities
        +-- CurrentObject
~~~

Không cần tạo ba lớp riêng nếu DSL nhỏ. Tuy nhiên, tách trách nhiệm về mặt khái niệm giúp tránh một đối tượng context trở thành nơi chứa mọi trạng thái của hệ thống.

## 4. Binding và môi trường biến

**Binding** là mối liên kết giữa một tên hoặc symbol và giá trị của nó trong một môi trường.

Ví dụ:

~~~text
variable customerName = "An"
variable orderTotal = 250000
~~~

Môi trường có thể chứa:

| Symbol | Giá trị |
| --- | --- |
| customerName | "An" |
| orderTotal | 250000 |

Trong một interpreter đơn giản, map từ chuỗi sang giá trị có thể đủ. Trong DSL có name resolution, overload hoặc shadowing, nên dùng symbol identity làm khóa để tránh nhầm các khai báo trùng tên ở những scope khác nhau.

### 4.1. Binding theo tên và binding theo symbol

Binding theo tên:

~~~text
Map<String, Value>
~~~

Cách này dễ triển khai nhưng có thể gặp vấn đề khi hai scope cùng có biến tên status.

Binding theo symbol:

~~~text
Map<SymbolId, Value>
~~~

Mỗi khai báo có một định danh riêng. AST đã được phân giải giữ SymbolId, vì vậy evaluator truy cập đúng binding dù tên hiển thị giống nhau.

Một runtime nhỏ có thể bắt đầu bằng tên; runtime lớn nên cân nhắc symbol identity để hỗ trợ scope và closure chính xác.

### 4.2. Giá trị và trạng thái chưa khởi tạo

Một biến có thể ở nhiều trạng thái:

- Chưa được khai báo.
- Đã khai báo nhưng chưa khởi tạo.
- Đã khởi tạo với giá trị.
- Đã gán null nếu DSL hỗ trợ null.
- Đã bị hủy hoặc không còn hợp lệ nếu DSL có lifecycle.

Không nên dùng một giá trị null duy nhất để biểu diễn tất cả trạng thái này. Nếu null là giá trị hợp lệ, runtime cần một sentinel hoặc kiểu binding riêng cho trạng thái chưa khởi tạo.

### 4.3. Gán giá trị

Khi DSL có câu lệnh gán:

~~~text
set total = price * quantity
~~~

Evaluator thực hiện:

1. Đánh giá biểu thức bên phải.
2. Kiểm tra kiểu và khả năng gán.
3. Tìm binding đích.
4. Cập nhật binding theo semantics của DSL.
5. Trả kết quả hoặc trạng thái câu lệnh theo quy ước.

Cần xác định gán có được tạo biến mới hay chỉ cập nhật biến đã khai báo. Nhiều DSL yêu cầu khai báo trước để tránh lỗi chính tả vô tình tạo biến mới.

## 5. Phạm vi và chuỗi môi trường lồng nhau

DSL thường có scope lồng nhau. Một block có thể tạo biến cục bộ mà không làm thay đổi biến cùng tên ở phạm vi cha.

Ví dụ:

~~~text
variable rate = 0.05

workflow calculate {
  variable rate = 0.1
  evaluate price * rate
}
~~~

Nếu DSL cho phép shadowing, biểu thức trong workflow dùng rate cục bộ có giá trị 0,1. Binding bên ngoài vẫn tồn tại.

### 5.1. Environment chain

Một cách triển khai phổ biến là mỗi environment có tham chiếu đến environment cha:

~~~text
Global Environment
  rate = 0.05
       |
       v
Workflow Environment
  rate = 0.1
       |
       v
Step Environment
  order = currentOrder
~~~

Khi tra cứu tên, runtime tìm ở môi trường hiện tại trước rồi lần lượt đi lên môi trường cha.

~~~text
lookup(name):
  if current environment contains name:
    return local binding
  if parent exists:
    return parent.lookup(name)
  return unresolved
~~~

Đây là lexical lookup nếu chuỗi môi trường phản ánh cấu trúc khai báo trong chương trình.

### 5.2. Tạo scope mới khi vào block

Khi vào một block, evaluator có thể tạo environment con:

~~~text
parent = currentEnvironment
currentEnvironment = Environment(parent)

evaluate block statements

currentEnvironment = parent
~~~

Trong triển khai thực tế, việc khôi phục scope nên được bảo đảm kể cả khi biểu thức phát sinh lỗi hoặc có lệnh return. Có thể dùng try/finally hoặc một cơ chế scope guard.

### 5.3. Rời scope

Khi rời block, các binding cục bộ không còn được phân giải từ môi trường bên ngoài. Nếu một closure giữ tham chiếu đến environment đó, dữ liệu cần thiết có thể tiếp tục tồn tại theo quy tắc closure.

Điều này cho thấy scope logic và vòng đời bộ nhớ là hai vấn đề liên quan nhưng khác nhau.

### 5.4. Shadowing và khai báo trùng

Shadowing là khai báo cùng tên ở scope con che khuất khai báo scope cha. Duplicate declaration là hai khai báo cùng tên trong một scope khi DSL không cho phép.

Bối cảnh đánh giá cần tuân theo quy tắc đã được name resolver xác định. Runtime không nên tự quyết định lại một cách khác với lúc phân tích ngữ nghĩa.

## 6. Lexical scope và dynamic scope

Cách xác định môi trường cha ảnh hưởng đến ý nghĩa của chương trình.

### 6.1. Lexical scope

Lexical scope xác định phạm vi dựa trên cấu trúc khai báo trong văn bản DSL. Hàm thường nhìn thấy các binding ở nơi hàm được định nghĩa, cùng các binding cục bộ và tham số của nó.

Ví dụ:

~~~text
variable rate = 0.05

function calculate(price) {
  return price * rate
}

workflow run {
  variable rate = 0.2
  return calculate(100)
}
~~~

Với lexical scope, hàm calculate được định nghĩa khi rate ở phạm vi ngoài có giá trị 0,05. Lời gọi từ workflow không tự thay đổi binding mà hàm nhìn thấy. Kết quả là 5 nếu hàm đóng trên environment khai báo.

### 6.2. Dynamic scope

Dynamic scope tìm biến theo chuỗi lời gọi đang hoạt động. Trong ví dụ trên, hàm có thể nhìn thấy rate của caller là 0,2, tùy quy tắc dynamic scoping.

Dynamic scope đôi khi hữu ích cho một số context tạm thời, nhưng làm cho kết quả phụ thuộc đường gọi hàm và khó suy luận hơn.

### 6.3. Lựa chọn cho DSL

Phần lớn DSL có hàm và biến cục bộ nên ưu tiên lexical scope vì:

- Kết quả ít phụ thuộc caller.
- Dễ phân tích tĩnh.
- Dễ tái sử dụng hàm.
- Hỗ trợ closure rõ ràng.
- Dễ điều hướng từ tham chiếu đến khai báo.

Nếu cần context động như current user hoặc transaction hiện tại, nên cung cấp chúng qua một runtime service rõ ràng thay vì âm thầm thay đổi quy tắc phân giải mọi biến.

## 7. Tham số hàm và stack frame

Khi gọi hàm, runtime cần tạo một môi trường chứa tham số và biến cục bộ của lần gọi đó. Môi trường này thường được gọi là activation record hoặc stack frame về mặt khái niệm.

Ví dụ:

~~~text
function addTax(amount, rate) {
  variable tax = amount * rate
  return amount + tax
}

addTax(1000, 0.1)
~~~

Khi gọi hàm, runtime tạo frame:

| Binding | Giá trị |
| --- | ---: |
| amount | 1000 |
| rate | 0.1 |
| tax | Chưa khởi tạo |

Sau khi tính biểu thức, tax có giá trị 100 và hàm trả về 1100.

### 7.1. Tạo frame khi gọi

Quy trình khái quát:

1. Đánh giá các đối số theo thứ tự được DSL quy định.
2. Kiểm tra số lượng và kiểu đối số.
3. Tạo environment cho lần gọi.
4. Gắn giá trị đối số vào tham số.
5. Liên kết environment với lexical parent hoặc closure environment.
6. Đánh giá thân hàm.
7. Xử lý return hoặc lỗi.
8. Kết thúc frame và trả kết quả.

### 7.2. Đệ quy

Mỗi lần gọi đệ quy cần frame riêng để các tham số và biến cục bộ không ghi đè nhau.

Ví dụ factorial:

~~~text
function factorial(n) {
  if n <= 1 {
    return 1
  }
  return n * factorial(n - 1)
}
~~~

Các lần gọi factorial(3), factorial(2), factorial(1) có môi trường riêng với n lần lượt là 3, 2 và 1.

Runtime cần giới hạn độ sâu gọi nếu DSL có thể nhận đầu vào không tin cậy, để tránh stack overflow hoặc tiêu thụ tài nguyên không kiểm soát.

### 7.3. Return và exception

Kết quả hàm có thể được biểu diễn bằng control signal:

~~~text
Normal(value)
Return(value)
Break
Continue
Throw(error)
~~~

Evaluator cần phân biệt giá trị trả về với lỗi và tín hiệu điều khiển. Khi một hàm return, frame hiện tại kết thúc và kết quả được trả về caller. Khi có exception, runtime áp dụng quy tắc bắt lỗi và giải phóng tài nguyên đã định nghĩa.

## 8. Closure và môi trường được giữ lại

**Closure** là một hàm kết hợp với môi trường lexical nơi nó được tạo ra. Nhờ closure, hàm có thể tiếp tục truy cập biến bên ngoài ngay cả khi block khai báo đã kết thúc.

Ví dụ:

~~~text
function makeCounter() {
  variable count = 0

  return function() {
    count = count + 1
    return count
  }
}

variable next = makeCounter()
next()
next()
~~~

Hai lần gọi next có thể trả về 1 rồi 2 vì closure giữ môi trường chứa count.

### 8.1. Closure cần lưu gì?

Một closure thường gồm:

~~~text
Closure
  functionCode
  capturedEnvironment
~~~

Function code là AST hoặc mã đã biên dịch của thân hàm. Captured environment chứa các binding mà hàm cần truy cập theo semantics của DSL.

Không nhất thiết phải sao chép toàn bộ environment. Runtime có thể giữ tham chiếu đến environment hoặc chỉ capture những biến được sử dụng.

### 8.2. Capture theo giá trị và theo tham chiếu

Nếu DSL cho phép biến thay đổi, cần xác định closure giữ giá trị tại thời điểm tạo hay giữ một cell có thể quan sát cập nhật sau đó.

- **Capture by value:** closure giữ bản sao giá trị.
- **Capture by reference/cell:** closure và scope gốc chia sẻ một binding có thể thay đổi.

Ví dụ:

~~~text
variable rate = 0.1
variable calculate = function(price) {
  return price * rate
}
rate = 0.2
calculate(100)
~~~

Kết quả là 10 hay 20 phụ thuộc capture semantics. DSL phải quy định rõ và runtime phải triển khai nhất quán.

### 8.3. Vòng đời và bộ nhớ

Closure có thể giữ environment sống lâu hơn block tạo ra nó. Nếu environment giữ nhiều đối tượng lớn hoặc dịch vụ, closure có thể kéo dài vòng đời của những đối tượng đó.

Runtime cần tránh giữ tham chiếu không cần thiết và cân nhắc chu trình tham chiếu nếu cơ chế quản lý bộ nhớ không tự xử lý được.

## 9. Đối tượng hiện tại và context receiver

DSL mô hình miền thường có khái niệm đối tượng hiện tại, chẳng hạn this, self hoặc current.

Ví dụ:

~~~text
entity Order {
  property total: Decimal

  operation isLarge {
    return this.total > 1000000
  }
}
~~~

Trong operation, this tham chiếu đến instance Order đang được xử lý.

### 9.1. Current object

Bối cảnh có thể giữ:

~~~text
currentObject = currentOrder
~~~

Khi evaluator gặp this.total, nó đọc thuộc tính total của currentObject theo quy tắc truy cập thuộc tính.

Nếu không có đối tượng hiện tại, biểu thức dùng this cần báo lỗi ngữ nghĩa hoặc lỗi đánh giá theo thiết kế DSL.

### 9.2. Context receiver trong block

Một DSL có thể cho phép block được đánh giá trong context của một đối tượng:

~~~text
with order {
  total = total + shippingFee
}
~~~

Trong block, tên thuộc tính có thể được phân giải tương đối với order. Runtime cần xác định thứ tự ưu tiên giữa thuộc tính của context receiver và biến cùng tên trong environment.

Một quy tắc rõ ràng có thể là:
1. Tham chiếu cục bộ đã được phân giải.
2. Thành viên của context receiver nếu cú pháp cho phép implicit member access.
3. Environment cha.

Tuy nhiên, quy tắc thực tế phải do ngôn ngữ đặc tả; tránh lookup mơ hồ giữa biến và property.

### 9.3. Nhiều context receiver

Nếu một biểu thức có nhiều context object, cùng một tên property có thể xuất hiện ở nhiều nơi. DSL cần yêu cầu qualifier, ưu tiên rõ ràng hoặc báo lỗi mơ hồ.

Không nên chọn object đầu tiên theo thứ tự map hoặc thứ tự runtime tình cờ.

## 10. Hàm, action và dịch vụ trong bối cảnh

Ngoài biến, evaluator có thể cần gọi hàm dựng sẵn, hàm người dùng hoặc action được cung cấp bởi ứng dụng.

Ví dụ:

~~~text
if order.total > 0 {
  call paymentService.charge(order)
}
~~~

Bối cảnh có thể chứa registry:

~~~text
FunctionEnvironment
  abs -> math.abs
  round -> math.round
  paymentService.charge -> approved action
~~~

### 10.1. Function registry

Registry ánh xạ tên hoặc symbol đến implementation có chữ ký:

~~~text
FunctionDefinition
  symbol
  parameterTypes
  returnType
  implementation
  effects
~~~

Evaluator cần xác nhận lời gọi có đúng số lượng và kiểu đối số. Kết quả trả về phải phù hợp kiểu được khai báo.

### 10.2. Hàm thuần và hàm có tác động phụ

Hàm thuần (pure function) chỉ phụ thuộc đối số và không làm thay đổi trạng thái bên ngoài. Cùng đối số luôn cho cùng kết quả.

Hàm có tác động phụ có thể đọc đồng hồ, truy cập dữ liệu, ghi trạng thái hoặc gọi dịch vụ bên ngoài.

Phân biệt này quan trọng cho:

- Tối ưu biểu thức.
- Memoization.
- Kiểm thử.
- Tái lập kết quả.
- Phân quyền.
- Thực thi song song.

Không nên memoize một hàm có tác động phụ như thể nó là hàm thuần.

### 10.3. Runtime service và dependency injection

Thay vì cho evaluator truy cập singleton toàn cục, có thể truyền dịch vụ qua context:

~~~text
RuntimeServices
  clock
  repository
  logger
  eventPublisher
~~~

Cách này giúp kiểm thử bằng service giả, giới hạn quyền và dùng các cấu hình khác nhau cho từng lần chạy.

### 10.4. Capability-based context

Với DSL thực thi action, bối cảnh có thể chỉ cung cấp những capability mà chương trình được phép dùng.

Ví dụ, một workflow chỉ được đọc dữ liệu khách hàng và phát sự kiện; nó không có quyền xóa tài khoản hoặc gửi yêu cầu thanh toán. Evaluator chỉ đăng ký các action được cấp phép.

Đây là ranh giới quan trọng khi chạy DSL do người dùng hoặc tenant tạo ra. Không nên xem việc một hàm tồn tại trong runtime là lý do để mọi chương trình DSL đều được gọi hàm đó.

## 11. Context và kiểu dữ liệu

Bối cảnh không chỉ lưu giá trị mà còn cần cung cấp đủ thông tin kiểu để evaluator thực hiện phép toán hợp lệ.

Ví dụ:

~~~text
price: Decimal = 120.50
quantity: Integer = 2
~~~

Khi đánh giá price * quantity, evaluator cần biết phép nhân Decimal với Integer được hỗ trợ hay cần chuyển đổi.

### 11.1. Typed value

Một runtime có thể biểu diễn giá trị bằng:

~~~text
Value
  type
  payload
  nullState
~~~

Hoặc dùng các lớp giá trị riêng:

~~~text
IntegerValue
DecimalValue
StringValue
BooleanValue
ObjectValue
ListValue
NullValue
~~~

Cấu trúc cụ thể tùy implementation. Điều quan trọng là không dựa hoàn toàn vào kiểu host language nếu DSL có type system riêng.

### 11.2. Type environment

Type environment có thể lưu:

- Khai báo kiểu.
- Quan hệ subtype.
- Kiểu thuộc tính.
- Chữ ký hàm.
- Quy tắc chuyển đổi.
- Kiểu generic hoặc collection.

Một số thông tin kiểu có thể được giải quyết tĩnh trước khi chạy. Runtime vẫn cần giữ type metadata để kiểm tra giá trị động hoặc thực thi những biểu thức có kiểu phụ thuộc dữ liệu.

### 11.3. Coercion và conversion

Nếu DSL cho phép chuyển kiểu ngầm định, evaluator cần quy tắc rõ:

~~~text
Decimal + Integer
String + Integer
Date + Duration
~~~

Không nên tự gọi phép chuyển đổi của JavaScript hoặc Java vì semantics host language có thể khác DSL.

Có thể định nghĩa conversion registry và chỉ cho phép các chuyển đổi được đặc tả. Chuyển đổi mất dữ liệu nên được xử lý riêng hoặc yêu cầu tường minh.

## 12. Giá trị null, absent và lỗi khi truy cập

Bối cảnh đánh giá cần phân biệt biến không tồn tại với biến tồn tại nhưng mang null.

Ví dụ:

~~~text
customer = null
~~~

Nếu evaluator tra cứu customer và tìm thấy binding có giá trị null, đó khác với trường hợp không có binding customer.

Một mô hình kết quả tra cứu:

~~~text
LookupResult
  Found(value)
  Uninitialized
  NotFound
~~~

Trong đó value có thể là NullValue nếu DSL hỗ trợ null.

### 12.1. Truy cập thuộc tính

Với biểu thức customer.address.city, có thể xảy ra:

- customer không được khai báo.
- customer chưa khởi tạo.
- customer là null.
- customer không có thuộc tính address.
- address là null.
- address không có thuộc tính city.

Mỗi trường hợp có nguyên nhân khác nhau và nên có diagnostic phù hợp.

### 12.2. Safe navigation

Một DSL có thể hỗ trợ toán tử truy cập an toàn:

~~~text
customer?.address?.city
~~~

Nếu một phần tử trung gian là null, biểu thức có thể trả về null thay vì ném lỗi. Cần quy định toán tử có xử lý cả absent hay chỉ null, và kiểu kết quả được suy ra như thế nào.

### 12.3. Defaulting operator

Một toán tử mặc định có thể cung cấp giá trị thay thế:

~~~text
customer.nickname ?? "Guest"
~~~

Evaluator cần xác định toán tử xem null, absent hay cả hai là trường hợp dùng giá trị bên phải. Điều này phải thống nhất với semantics của biến và thuộc tính.

## 13. Thứ tự đánh giá và tính xác định

Bối cảnh có thể thay đổi trong khi một biểu thức được đánh giá nếu DSL cho phép tác động phụ. Vì vậy, thứ tự đánh giá cần được đặc tả.

Ví dụ:

~~~text
charge(account) + updateBalance(account)
~~~

Nếu hai lời gọi có tác động phụ, thay đổi thứ tự có thể làm kết quả khác hoặc gây hành vi không mong muốn.

### 13.1. Thứ tự đối số

Với lời gọi:

~~~text
calculate(nextValue(), currentValue())
~~~

DSL cần quy định đối số được đánh giá từ trái sang phải, từ phải sang trái hay theo quy tắc khác. Một runtime không nên phụ thuộc vào thứ tự duyệt danh sách do cấu trúc dữ liệu cung cấp.

### 13.2. Short-circuit

Toán tử logic thường có short-circuit:

~~~text
isAuthorized && chargePayment()
~~~

Nếu vế trái false, vế phải có thể không được đánh giá. Đây vừa là quy tắc hiệu năng vừa ảnh hưởng tác động phụ và bảo mật.

Tương tự, với toán tử OR, nếu vế trái true thì vế phải có thể bị bỏ qua.

### 13.3. Tái lập kết quả

Nếu biểu thức phụ thuộc currentTime, random hoặc dữ liệu bên ngoài, cùng AST và biến có thể cho kết quả khác giữa các lần chạy.

Có thể truyền Clock, RandomSource hoặc DataAccess qua context để kiểm thử có thể kiểm soát và để runtime ghi nhận nguồn dữ liệu.

### 13.4. Snapshot context

Một số phép đánh giá cần nhìn thấy trạng thái nhất quán trong suốt biểu thức hoặc transaction. Runtime có thể tạo snapshot context hoặc transaction-bound context để tránh đọc các phiên bản dữ liệu khác nhau giữa các bước.

## 14. Context trong workflow và các bước thực thi

DSL workflow thường có context xuyên suốt nhiều step. Mỗi step có thể nhận input, tạo output và chia sẻ một số dữ liệu với bước sau.

Ví dụ:

~~~text
workflow placeOrder(orderId) {
  step load {
    output order = repository.findOrder(orderId)
  }

  step calculate {
    output total = order.items.sum(item.price)
  }

  step charge {
    paymentService.charge(order, total)
  }
}
~~~

Bối cảnh workflow có thể chứa:

~~~text
WorkflowContext
  inputs
  sharedVariables
  stepResults
  currentStep
  executionMetadata
~~~

### 14.1. Input và output của step

Một step có thể nhận binding từ input của workflow và output của step trước. Cần xác định:

- Output có được thêm vào scope chung không?
- Tên output có thể trùng với input không?
- Step có đọc được output của step chưa chạy không?
- Khi step thất bại, output cũ có còn không?
- Có cho phép ghi đè binding đã tồn tại không?

Một workflow có dependency graph nên chỉ cho step đọc output từ các bước đã hoàn thành hoặc được khai báo là dependency.

### 14.2. Context theo step

Có thể tạo context con cho từng step:

~~~text
Workflow Context
    |
    +-- Load Step Context
    |
    +-- Calculate Step Context
    |
    +-- Charge Step Context
~~~

Mỗi step có thể có biến cục bộ riêng, trong khi workflow context giữ dữ liệu chia sẻ. Khi step kết thúc, chỉ những output được công bố mới được đưa trở lại workflow context.

### 14.3. Retry

Khi retry một step, cần xác định context được khôi phục thế nào:

- Dùng input ban đầu.
- Dùng snapshot trước lần chạy đầu.
- Giữ một số output đã tạo.
- Tạo context mới hoàn toàn.

Nếu step có tác động phụ, retry còn cần idempotency key hoặc cơ chế bảo đảm không thực hiện cùng hành động hai lần ngoài ý muốn.

## 15. Context trong biểu thức truy vấn và xử lý tập dữ liệu

Một DSL truy vấn thường đánh giá biểu thức theo từng bản ghi. Bối cảnh có thể thay đổi current row trong khi giữ các binding bên ngoài.

Ví dụ:

~~~text
from Order as order
where order.total > minimumTotal
select order.id
~~~

Context có thể gồm:

- minimumTotal: biến bên ngoài query.
- order: bản ghi hiện tại.
- Các hàm truy vấn được phép.
- Schema hoặc type metadata của nguồn dữ liệu.

### 15.1. Row context

Khi xử lý mỗi bản ghi, evaluator tạo hoặc cập nhật row context:

~~~text
QueryContext
  outerEnvironment
  currentRow
  aliasBindings
  queryFunctions
~~~

Nếu query chạy trên nhiều bản ghi, mỗi lần đánh giá predicate cần dùng đúng row. Không nên lưu currentRow trong một biến toàn cục dùng chung giữa các luồng.

### 15.2. Correlated subquery

Một subquery có thể tham chiếu binding của query bên ngoài:

~~~text
from Customer as customer
where exists (
  from Order as order
  where order.customerId == customer.id
)
~~~

Subquery có environment riêng nhưng liên kết với outer environment. Resolver cần xác định tên customer trong subquery có được phép tham chiếu ra ngoài hay không.

### 15.3. Aggregate context

Các hàm như sum, count, min và max có thể cần tập dữ liệu hoặc accumulator. Có thể xem chúng là function invocation có state riêng của phép aggregate, thay vì thêm mọi giá trị trung gian vào environment chung.

Điều này giúp tránh xung đột tên và quản lý vòng đời accumulator rõ ràng.

## 16. Context trong thực thi bất đồng bộ và song song

Một số DSL hỗ trợ action bất đồng bộ, workflow song song hoặc xử lý sự kiện. Khi đó, việc chia sẻ context cần được thiết kế cẩn thận.

### 16.1. Context propagation

Khi một step gọi tác vụ bất đồng bộ, runtime có thể cần truyền theo:

- Execution ID và trace.
- User hoặc tenant identity.
- Deadline và cancellation.
- Locale hoặc cấu hình định dạng nếu cần.
- Transaction hoặc correlation metadata.
- Những binding được phép chia sẻ.

Không nên truyền toàn bộ context một cách mặc định. Một số thành phần như mutable environment hoặc transaction không thể an toàn khi chia sẻ qua thread hoặc process.

### 16.2. Immutable context

Context bất biến có thể được chia sẻ an toàn hơn giữa các nhánh song song:

~~~text
baseContext
   |
   +-- branch A context
   |
   +-- branch B context
~~~

Mỗi nhánh tạo environment con riêng và chỉ công bố kết quả khi hoàn thành.

### 16.3. Tránh race condition

Nếu hai nhánh cùng ghi biến total trong một environment dùng chung, kết quả có thể phụ thuộc thứ tự hoàn thành. Có thể:

- Cấm ghi binding chung từ nhánh song song.
- Dùng output riêng cho từng nhánh.
- Dùng reducer hoặc merge function tường minh.
- Dùng primitive đồng bộ nếu DSL thực sự cần trạng thái chia sẻ.

Không nên để hành vi phụ thuộc vào timing của thread.

### 16.4. Cancellation và deadline

Execution context có thể chứa cancellation token và deadline. Evaluator cần kiểm tra chúng ở các điểm an toàn, chẳng hạn giữa các step hoặc trước lời gọi dịch vụ.

Một biểu thức thuần rất ngắn có thể không cần kiểm tra ở từng node; một vòng lặp dài hoặc truy vấn lớn cần cơ chế kiểm tra để runtime có thể dừng đúng lúc.

## 17. Context, transaction và tính nhất quán dữ liệu

Nếu DSL có thao tác đọc ghi dữ liệu, bối cảnh có thể gắn với transaction hiện tại.

Ví dụ:

~~~text
transaction {
  account.balance = account.balance - amount
  ledger.record(account.id, amount)
}
~~~

Runtime cần biết các thao tác thuộc cùng transaction nào, commit hoặc rollback khi nào và cách xử lý lỗi.

### 17.1. Transaction context

Có thể chứa:

~~~text
TransactionContext
  transactionId
  dataSession
  isolationLevel
  commitPolicy
~~~

Evaluator hoặc action adapter nhận transaction từ context thay vì tự mở một transaction mới cho mỗi thao tác.

### 17.2. Context lồng nhau

Một workflow có thể mở transaction, trong đó một operation gọi function khác. Cần xác định function dùng transaction hiện tại, tạo transaction con hay không được phép quản lý transaction.

Các lựa chọn khác nhau có semantics khác nhau. Nếu tạo transaction lồng nhau, cần quy định savepoint hoặc propagation mode.

### 17.3. Lỗi và rollback

Khi một step phát sinh lỗi, runtime cần biết:

- Có rollback transaction không?
- Có chạy compensation action không?
- Có giữ context để phục hồi workflow không?
- Có retry không?
- Những output nào được xem là đã commit?

Context giúp mang theo trạng thái cần thiết, nhưng chính sách transaction phải được định nghĩa ở execution semantics.

## 18. Security boundary và quyền trong evaluation context

Evaluation context là nơi runtime cấp cho chương trình khả năng truy cập biến, hàm và dịch vụ. Vì vậy, nó cũng là một ranh giới bảo mật.

### 18.1. Không đưa mọi dịch vụ vào context

Nếu DSL chỉ cần tính giá trị đơn hàng, không nên cung cấp quyền đọc toàn bộ cơ sở dữ liệu hoặc gọi mọi API nội bộ.

Chỉ đăng ký những capability cần thiết cho chương trình hoặc tenant.

### 18.2. Tách dữ liệu người dùng và dữ liệu hệ thống

Một binding như currentUser có thể là dữ liệu hệ thống đáng tin cậy. Biến do DSL khai báo là dữ liệu chương trình. Không nên cho phép chương trình ghi đè currentUser nếu đó là nguồn xác thực.

Có thể đặt các namespace riêng:

~~~text
user variables
system context
approved services
~~~

Hoặc dùng symbol kind và quyền ghi để ngăn việc gán vào binding hệ thống.

### 18.3. Tenant isolation

Trong hệ thống multi-tenant, context cần mang tenant identity và mọi data access service phải thực thi phạm vi tenant. Không nên chỉ dựa vào một biến tenantId có thể bị DSL thay đổi.

Tenant identity nên được cung cấp qua capability hoặc context metadata không thể ghi từ chương trình.

### 18.4. Resource limits

Context có thể giữ giới hạn:

- Thời gian chạy.
- Số bước.
- Độ sâu đệ quy.
- Số lần gọi action.
- Bộ nhớ hoặc kích thước dữ liệu.
- Số lượng truy vấn.

Evaluator cần kiểm tra các giới hạn này ở những điểm phù hợp. Việc chỉ đặt timeout cho toàn bộ process có thể không đủ nếu một DSL được chạy trong shared service.

## 19. Error handling và diagnostic từ bối cảnh đánh giá

Lỗi trong quá trình đánh giá thường phụ thuộc vào giá trị hoặc binding của context.

Ví dụ:

- Không tìm thấy biến.
- Biến chưa được khởi tạo.
- Truy cập thuộc tính trên null.
- Gọi hàm không có trong context.
- Sai số lượng hoặc kiểu tham số.
- Hàm bị từ chối do thiếu capability.
- Deadline đã hết.
- Transaction không còn hợp lệ.

### 19.1. Evaluation result

Một evaluator có thể trả về kết quả có kiểu:

~~~text
EvaluationResult
  Success(value)
  Failure(diagnostic)
  ControlSignal(signal)
~~~

Không nên dùng null để biểu diễn cả kết quả hợp lệ, lỗi và return. Các trạng thái cần được phân biệt rõ.

### 19.2. Diagnostic có source location

Mỗi node AST nên giữ source span. Khi lookup thất bại, evaluator có thể phát diagnostic tại đúng NameReference thay vì chỉ báo chung rằng chương trình không chạy được.

Ví dụ:

~~~text
Unknown variable taxRtae.
Did you mean taxRate?
Source: pricing.dsl, line 12, column 18.
~~~

Gợi ý có thể được tạo từ symbol table, còn message có thể được bản địa hóa ở lớp trình bày.

### 19.3. Giữ nguyên nguyên nhân

Nếu một action gọi dịch vụ bên ngoài thất bại, runtime nên giữ cause hoặc mã lỗi kỹ thuật phù hợp. Message người dùng có thể nói “Không thể hoàn tất thao tác thanh toán”, trong khi log nội bộ giữ correlation ID và lỗi của adapter.

Không đưa stack trace hoặc dữ liệu nhạy cảm vào message người dùng nếu không phù hợp.

## 20. Thiết kế API EvaluationContext

Một API đơn giản có thể dùng environment cha-con và một tập runtime service.

Ví dụ Java:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

final class Environment {
    private final Environment parent;
    private final Map<String, Object> values = new HashMap<>();

    Environment(Environment parent) {
        this.parent = parent;
    }

    void define(String name, Object value) {
        if (values.containsKey(name)) {
            throw new IllegalArgumentException(
                "Duplicate binding: " + name
            );
        }
        values.put(name, value);
    }

    Optional<Object> lookup(String name) {
        if (values.containsKey(name)) {
            return Optional.ofNullable(values.get(name));
        }
        return parent == null
            ? Optional.empty()
            : parent.lookup(name);
    }
}
~~~

Lớp context:

~~~java
record EvaluationContext(
    Environment environment,
    Object currentObject,
    RuntimeServices services
) {}
~~~

Evaluator:

~~~java
interface Expression {
    Object evaluate(EvaluationContext context);
}
~~~

Node tham chiếu tên:

~~~java
record NameExpression(String name) implements Expression {
    @Override
    public Object evaluate(EvaluationContext context) {
        return context.environment()
            .lookup(name)
            .orElseThrow(() ->
                new IllegalStateException(
                    "Unknown variable: " + name
                )
            );
    }
}
~~~

Đây là minh họa tối giản. Có một điểm cần lưu ý: Optional không thể phân biệt binding không tồn tại với binding tồn tại có giá trị null. Một implementation đầy đủ nên dùng LookupResult riêng và kiểu Value của DSL thay vì Object.

### 20.1. Kết quả lookup rõ ràng

Có thể mô hình hóa:

~~~java
sealed interface LookupResult {
    record Found(Value value) implements LookupResult {}
    record Uninitialized() implements LookupResult {}
    record NotFound() implements LookupResult {}
}
~~~

Khi đó, evaluator có thể đưa ra diagnostic khác nhau cho biến chưa khai báo và biến chưa được khởi tạo.

### 20.2. Context bất biến với environment con

Một cách khác là tạo environment mới thay vì cập nhật map đang dùng:

~~~java
EvaluationContext child =
    context.withEnvironment(
        context.environment().child()
    );
~~~

API bất biến giúp việc chia sẻ context và chạy song song an toàn hơn. Tuy nhiên, nếu DSL có mutable variable, cần biểu diễn cell hoặc store riêng để giữ semantics gán.

### 20.3. Không dùng global mutable state

Không nên đặt current user, current order hoặc biến của workflow trong static map dùng chung. Hai lần chạy DSL có thể ghi đè dữ liệu của nhau.

Context nên được tạo cho từng execution hoặc từng evaluation session, với vòng đời và quyền truy cập rõ ràng.

## 21. Đánh giá biểu thức với context

Một evaluator có thể triển khai mỗi loại AST node thành một hàm nhận EvaluationContext.

Ví dụ, biểu thức cộng:

~~~java
record AddExpression(
    Expression left,
    Expression right
) implements Expression {
    @Override
    public Object evaluate(EvaluationContext context) {
        Object leftValue = left.evaluate(context);
        Object rightValue = right.evaluate(context);

        return numericAdd(leftValue, rightValue);
    }
}
~~~

Trong một DSL có type system, numericAdd cần dùng Value và quy tắc toán học của DSL thay vì dựa vào toán tử hoặc ép kiểu của host language.

### 21.1. Truy cập thuộc tính

Node PropertyAccess có thể:

1. Đánh giá receiver.
2. Kiểm tra null và kiểu receiver.
3. Tra metadata thuộc tính.
4. Đọc giá trị từ object hoặc adapter.
5. Trả Value theo type system.

Nếu receiver là một đối tượng proxy hoặc dữ liệu từ nguồn bên ngoài, việc đọc property có thể cần capability và có thể phát sinh lỗi truy cập.

### 21.2. Gọi hàm

Node FunctionCall có thể:

1. Phân giải function symbol.
2. Đánh giá đối số theo thứ tự đã định.
3. Kiểm tra kiểu.
4. Kiểm tra capability hoặc quyền.
5. Gọi implementation.
6. Chuẩn hóa kết quả thành Value.
7. Chuyển lỗi thành diagnostic hoặc runtime failure.

### 21.3. Context truyền xuyên suốt

Các node con thường nhận cùng context hiện tại. Những node tạo scope hoặc gọi hàm tạo context con theo quy tắc của chúng.

Không nên tạo một context hoàn toàn mới cho mọi node nếu không cần, vì việc đó có thể tốn chi phí và vô tình làm mất binding cha.

## 22. Kiểm thử bối cảnh đánh giá

Context là nền tảng của semantics runtime, nên cần kiểm thử các trường hợp phân giải và vòng đời.

### 22.1. Kiểm thử lookup

- Tìm binding trong scope hiện tại.
- Tìm binding ở scope cha.
- Binding con shadow binding cha.
- Không tìm thấy tên.
- Phân biệt null với không tồn tại.
- Phân biệt chưa khởi tạo với đã khởi tạo.

### 22.2. Kiểm thử hàm và frame

- Truyền đúng tham số.
- Thiếu hoặc thừa tham số.
- Kiểu đối số không hợp lệ.
- Hai lần gọi có frame độc lập.
- Đệ quy giữ binding riêng.
- Return và exception kết thúc frame đúng cách.

### 22.3. Kiểm thử closure

- Closure truy cập binding ở scope khai báo.
- Capture by value hoặc by reference theo đặc tả.
- Closure sống sau khi block kết thúc.
- Nhiều closure có environment riêng.
- Không giữ tài nguyên quá vòng đời cần thiết.

### 22.4. Kiểm thử current object và workflow

- this trỏ đúng instance.
- Context receiver có ưu tiên đúng.
- Step chỉ đọc được output hợp lệ.
- Retry khôi phục context đúng.
- Hai workflow chạy đồng thời không chia sẻ binding ngoài ý muốn.

### 22.5. Kiểm thử bảo mật và tài nguyên

- Không gọi được capability không được cấp.
- Tenant không thể đọc dữ liệu tenant khác.
- Deadline và cancellation được tôn trọng.
- Giới hạn đệ quy và số bước được thực thi.
- Diagnostic không làm lộ secret.

### 22.6. Kiểm thử tính xác định

Dùng clock, random source và service giả để kết quả kiểm thử có thể lặp lại. Với cùng AST và context tương đương, các hàm thuần phải cho kết quả giống nhau.

## 23. Những lỗi thiết kế thường gặp

**Dùng một map toàn cục cho mọi lần chạy.** Các workflow có thể ghi đè binding của nhau. Hãy tạo context theo execution và scope.

**Đồng nhất context với environment.** Environment lưu binding; evaluation context có thể còn cần current object, function registry và runtime service. Phân chia trách nhiệm giúp API dễ hiểu.

**Không quy định lexical hay dynamic scope.** Cùng một hàm có thể cho kết quả khác tùy caller. Hãy chọn và tài liệu hóa quy tắc lookup.

**Dùng null để biểu diễn mọi trạng thái thiếu dữ liệu.** Binding không tồn tại, chưa khởi tạo và có giá trị null là các trường hợp khác nhau.

**Không tạo frame riêng cho lời gọi hàm.** Tham số và biến cục bộ của các lần gọi có thể ghi đè nhau, đặc biệt trong đệ quy.

**Capture closure không rõ semantics.** Người dùng không biết hàm giữ giá trị cũ hay quan sát cập nhật mới. Hãy định nghĩa capture by value hoặc by reference.

**Cho phép mọi function và service trong context.** Chương trình có thể thực hiện hành động ngoài dự kiến. Hãy cấp capability tối thiểu.

**Chia sẻ mutable context giữa các nhánh song song.** Kết quả có thể phụ thuộc timing. Hãy dùng context bất biến, output riêng hoặc merge rule tường minh.

**Để host language quyết định semantics.** Quy tắc null, phép toán và chuyển kiểu của Java hoặc JavaScript có thể khác DSL. Hãy triển khai type/value semantics riêng.

**Không giữ source location.** Lỗi runtime khó liên kết với biểu thức nguồn. Hãy giữ source span trên AST và truyền vào diagnostic.

## 24. Quy trình thiết kế bối cảnh đánh giá

Khi xây dựng runtime cho DSL, có thể thực hiện theo trình tự:

### Bước 1: Liệt kê dữ liệu cần khi đánh giá

Xác định biến, tham số, hàm, kiểu, đối tượng hiện tại, dịch vụ và metadata nào thực sự cần thiết.

### Bước 2: Định nghĩa semantics của binding

Quy định biến được khai báo và gán ra sao; phân biệt absent, uninitialized, null và value; xác định biến nào có thể thay đổi.

### Bước 3: Xác định scope và lookup

Chọn lexical hoặc dynamic scope, quy tắc shadowing, cách tạo scope con và cách kết thúc scope.

### Bước 4: Định nghĩa lời gọi hàm

Quy định thứ tự đánh giá đối số, cách tạo frame, return, exception, đệ quy và closure.

### Bước 5: Xác định current object và context receiver

Quy định this/self, truy cập thuộc tính ngầm định và xử lý khi có nhiều context object.

### Bước 6: Tách runtime service và capability

Đưa đồng hồ, repository, action hoặc dịch vụ vào context theo quyền được cấp. Xác định dịch vụ nào thuần và dịch vụ nào có tác động phụ.

### Bước 7: Thiết kế lifecycle và concurrency

Xác định context tồn tại bao lâu, cách truyền qua step, async task, retry và transaction. Tránh chia sẻ mutable state ngoài ý muốn.

### Bước 8: Thiết kế lỗi và giới hạn

Quy định diagnostic cho lookup, null, kiểu, quyền và timeout. Xác định giới hạn độ sâu, số bước, thời gian và tài nguyên.

### Bước 9: Kiểm thử semantics

Kiểm thử lookup, shadowing, frame, closure, current object, workflow, concurrency, bảo mật và tính tái lập.

## 25. Ví dụ tổng hợp: đánh giá biểu thức trong DSL đơn hàng

Giả sử DSL khai báo:

~~~text
entity Order {
  property subtotal: Decimal
  property taxRate: Decimal
}

workflow calculateOrder(order) {
  variable shippingFee = 30000

  evaluate order.subtotal * (1 + order.taxRate) + shippingFee
}
~~~

Khi workflow chạy với order có subtotal là 500000 và taxRate là 0,1, runtime tạo bối cảnh:

~~~text
EvaluationContext
  environment:
    order -> Order(subtotal=500000, taxRate=0.1)
    shippingFee -> 30000

  currentObject:
    workflow instance

  functions:
    decimal arithmetic functions

  services:
    approved runtime services
~~~

Evaluator xử lý biểu thức theo cấu trúc AST:

1. Tra cứu order trong environment.
2. Đọc order.subtotal và nhận 500000.
3. Đọc order.taxRate và nhận 0,1.
4. Đánh giá 1 + 0,1 thành 1,1 theo quy tắc Decimal.
5. Nhân 500000 với 1,1, được 550000.
6. Tra cứu shippingFee và nhận 30000.
7. Cộng hai kết quả, được 580000.

Nếu workflow khác dùng shippingFee là 50000, cùng AST sẽ cho kết quả 600000 vì context khác.

Nếu order là null, evaluator phát lỗi truy cập thuộc tính hoặc áp dụng safe navigation theo semantics. Nếu shippingFee chưa được khai báo, lỗi lookup được phát tại NameReference. Nếu biểu thức chạy trong một tenant, các service trong context chỉ được phép đọc dữ liệu thuộc tenant đó.

Ví dụ này cho thấy bối cảnh đánh giá quyết định dữ liệu và capability mà biểu thức có thể quan sát, trong khi AST mô tả cấu trúc phép tính.

## 26. Kết luận

Bối cảnh đánh giá là tập hợp môi trường, binding và dịch vụ mà evaluator sử dụng để xác định giá trị của biểu thức hoặc thực hiện câu lệnh DSL. Nó có thể chứa environment biến, tham số, hàm, kiểu, đối tượng hiện tại, runtime service và metadata của lần thực thi.

Một runtime được thiết kế tốt cần quy định rõ cách tạo và tra cứu binding, scope lồng nhau, lexical hay dynamic scope, stack frame, closure, current object, null, thứ tự đánh giá và context propagation. Với workflow hoặc hệ thống bất đồng bộ, cần quản lý output, retry, transaction, concurrency và vòng đời context. Khi chạy DSL không tin cậy, context còn là ranh giới cấp capability và giới hạn tài nguyên.

Hãy giữ AST độc lập với dữ liệu của từng lần chạy, tạo context theo execution, dùng quy tắc lookup nhất quán và phân biệt trạng thái dữ liệu rõ ràng. Khi context được tổ chức tốt, cùng một chương trình DSL có thể được đánh giá trong nhiều môi trường khác nhau mà vẫn giữ semantics dự đoán được, dễ kiểm thử và an toàn.

