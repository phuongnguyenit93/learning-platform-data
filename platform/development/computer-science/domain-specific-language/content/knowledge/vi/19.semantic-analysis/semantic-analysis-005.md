# Bất biến liên nút

## 1. Khái niệm bất biến liên nút

Trong một DSL (*Domain-Specific Language*), sau khi lexer và parser xử lý văn bản nguồn, hệ thống thường xây dựng một cây cú pháp trừu tượng (*Abstract Syntax Tree — AST*) hoặc một mô hình đối tượng. Mỗi phần tử trong cấu trúc đó được biểu diễn bằng một **node**; quan hệ chứa, tham chiếu hoặc phụ thuộc giữa các phần tử được biểu diễn bằng cạnh (*edge*), liên kết hoặc reference.

**Bất biến liên nút (*cross-node invariant*)** là điều kiện ngữ nghĩa phải đúng khi xem xét đồng thời từ hai node trở lên hoặc một nhóm node có quan hệ với nhau. Điều kiện này không thể được xác nhận chỉ bằng cách kiểm tra riêng lẻ từng node.

Ví dụ trong DSL tính biểu thức:

~~~text
let taxRate: Decimal = 0.08
let subtotal: Money = order.subtotal
let tax: Money = subtotal * taxRate
let total: Money = subtotal + tax
~~~

Một node khai báo biến có thể hợp lệ khi xét riêng: tên biến đúng quy tắc, kiểu dữ liệu hợp lệ và biểu thức khởi tạo có cú pháp đúng. Nhưng khi kiểm tra toàn bộ mô hình, hệ thống còn phải xác nhận:

- Mỗi lần sử dụng một biến đều tham chiếu đến đúng một khai báo có thể nhìn thấy.
- Kiểu của biểu thức gán tương thích với kiểu của biến đích.
- Biểu thức cộng tiền phải có các toán hạng phù hợp.
- Một khai báo không tạo ra xung đột tên trong cùng phạm vi.
- Nếu DSL yêu cầu, biến được dùng phải được khởi tạo trước khi đọc.

Các điều kiện trên liên kết nhiều node: node khai báo với node sử dụng, node biểu thức với node toán hạng, hoặc nhiều khai báo trong cùng scope.

Bất biến liên nút thường xuất hiện trong semantic checking, model validation, type checking, symbol resolution, kiểm tra đồ thị và kiểm tra luồng dữ liệu. Nó giúp bảo đảm tài liệu DSL không chỉ có cấu trúc hợp lệ mà còn nhất quán trên toàn bộ phạm vi liên quan.

## 2. Vì sao kiểm tra từng node là chưa đủ?

Một node đơn lẻ chỉ cung cấp một phần thông tin. Ví dụ node tham chiếu identifier có thể chứa tên `customer` và source location. Từ node đó, hệ thống chưa thể kết luận tên có được khai báo, có nằm trong scope hiện tại hay có kiểu phù hợp hay không.

Tương tự, node transition có thể chứa tên trạng thái đích `Approved`. Chỉ khi so sánh với tập trạng thái được khai báo trong cùng state machine, semantic analyzer mới biết đích đó có tồn tại và có thuộc đúng state machine không.

| Kiểm tra cục bộ | Kiểm tra liên nút |
|---|---|
| Tên identifier có đúng quy tắc từ vựng không? | Identifier có tham chiếu đến đúng một symbol trong scope không? |
| Literal có kiểu Decimal không? | Literal có tương thích với kiểu của thuộc tính nhận giá trị không? |
| Node transition có đủ trường source và target không? | Source và target có thuộc cùng state machine không? |
| Một rule có điều kiện Boolean không? | Các rule có thứ tự ưu tiên và quan hệ loại trừ nhất quán không? |
| Một node khai báo có tên không rỗng không? | Có node khai báo nào khác trùng tên trong phạm vi cấm trùng không? |
| Một node workflow có danh sách successor không? | Đồ thị workflow có trạng thái kết thúc và không có chu trình bị cấm không? |

Kiểm tra cục bộ vẫn cần thiết và thường được thực hiện trước. Tuy nhiên, nhiều quy tắc ngữ nghĩa chỉ có thể xác định sau khi xây dựng quan hệ giữa các node.

## 3. Mô hình node và quan hệ trong AST hoặc model

### 3.1. Node

Node đại diện cho một phần tử của ngôn ngữ, chẳng hạn:

- Khai báo biến.
- Biểu thức literal.
- Biểu thức truy cập thuộc tính.
- Lời gọi hàm.
- Rule hoặc workflow.
- Trạng thái và transition.
- Khai báo kiểu hoặc namespace.

Một node thường chứa loại node, thuộc tính, các node con, source span và metadata ngữ nghĩa có thể được gắn thêm trong các giai đoạn phân tích.

### 3.2. Các dạng quan hệ

Bất biến liên nút có thể dựa trên nhiều loại quan hệ:

1. **Parent-child:** một block chứa nhiều statement; một biểu thức nhị phân chứa hai toán hạng.
2. **Reference:** một identifier tham chiếu đến khai báo hoặc phần tử khác.
3. **Dependency:** một bước workflow phụ thuộc vào bước khác.
4. **Control-flow:** một statement có thể chuyển đến các statement kế tiếp.
5. **Data-flow:** giá trị được tạo ở node này và được đọc ở node khác.
6. **Containment:** một phần tử thuộc về đúng một container hoặc một model root.
7. **Association:** hai phần tử miền liên kết với nhau, ví dụ Order và Customer.

Cần xác định rõ loại quan hệ vì mỗi loại có quy tắc duyệt và kiểm tra khác nhau.

### 3.3. Cây và đồ thị

AST thường có cấu trúc cây cho quan hệ cú pháp. Tuy nhiên, reference giữa các node có thể tạo thành đồ thị có chu trình. Ví dụ hai khai báo kiểu có thể tham chiếu lẫn nhau, hoặc hai workflow step có thể tạo vòng lặp.

Một mô hình ngữ nghĩa vì vậy thường được xem là đồ thị:

~~~text
Declaration(customer)
       ^
       |
IdentifierUse(customer) ----> Property(tier)
                                  |
                                  v
                             Comparison(==)
                                  |
                                  v
                              RuleCondition
~~~

Cây cú pháp cho biết node nằm ở đâu trong source; đồ thị tham chiếu cho biết node có liên hệ ngữ nghĩa với phần tử nào. Nhiều bất biến liên nút được kiểm tra trên đồ thị đã được semantic analyzer xây dựng từ AST.

## 4. Phân loại bất biến liên nút

### 4.1. Bất biến tên và symbol resolution

Các node sử dụng tên phải tham chiếu đến khai báo hợp lệ.

Ví dụ:

~~~text
let customerId: String = "C-100"

rule "check-customer" {
    when customerId != ""
    then allow()
}
~~~

Node identifier trong điều kiện phải resolve đến node khai báo `customerId` nếu scope cho phép truy cập.

Các điều kiện thường gặp:

- Mỗi reference phải resolve được.
- Reference phải resolve đến đúng loại symbol.
- Không có nhiều khai báo cùng tên trong phạm vi cấm trùng.
- Reference không được trỏ đến symbol không được export hoặc không được import.
- Reference không được truy cập biến trước thời điểm cho phép nếu DSL có quy tắc initialization order.
- Alias phải trỏ đến module hoặc symbol tồn tại.

### 4.2. Bất biến kiểu giữa các node

Các node kết nối qua phép toán, phép gán hoặc lời gọi hàm phải có kiểu tương thích.

Ví dụ:

~~~text
let quantity: Integer = 3
let unitPrice: Money = product.price
let lineTotal: Money = unitPrice * quantity
~~~

Semantic analyzer phải kiểm tra:
- Kiểu của quantity được phép nhân với Money.
- Kết quả phép nhân có kiểu Money.
- Kiểu kết quả tương thích với kiểu của lineTotal.
- Nếu có generic hoặc overload, node lời gọi được gắn với đúng kiểu hàm.

Đây là quan hệ giữa node toán tử, node toán hạng, node khai báo và node nhận kết quả.

### 4.3. Bất biến uniqueness

Một tập node có thể phải có giá trị định danh duy nhất trong một phạm vi.

Ví dụ:

~~~text
workflow "payment" {
    step "validate" { ... }
    step "charge" { ... }
    step "notify" { ... }
}
~~~

Nếu step ID phải duy nhất trong workflow, validator cần thu thập tất cả node step rồi kiểm tra các ID. Việc kiểm tra từng step riêng lẻ không phát hiện được hai step cùng tên.

Phạm vi uniqueness phải được xác định: toàn tài liệu, module, workflow, block, namespace hay một aggregate nghiệp vụ.

### 4.4. Bất biến reference và quan hệ sở hữu

Các liên kết phải trỏ đến node tồn tại và đúng loại.

Ví dụ, transition trong state machine:

~~~text
state Draft
state Approved
transition Draft -> Approved
~~~

Hai đầu transition phải tham chiếu đến state trong cùng state machine. Một tên state có thể tồn tại ở module khác nhưng không nhất thiết được phép dùng trong state machine này.

### 4.5. Bất biến cấu trúc giữa nhiều node

Một nhóm node có thể phải thỏa điều kiện về số lượng hoặc tổ hợp.

Ví dụ:
- Một workflow phải có đúng một start node.
- Một transaction block phải có một commit hoặc rollback path theo chính sách.
- Một rule group phải có ít nhất một rule được bật.
- Một khai báo class không được chứa hai member có cùng signature.
- Một node switch phải có nhánh default nếu DSL yêu cầu exhaustive handling.

### 4.6. Bất biến thứ tự và phụ thuộc

Một số node chỉ hợp lệ khi node khác đã xuất hiện hoặc đã được thực hiện trước.

Ví dụ:

~~~text
step reserveInventory
step capturePayment dependsOn reserveInventory
step shipOrder dependsOn capturePayment
~~~

Validator phải xác nhận dependency target tồn tại, không phụ thuộc vào chính nó và thỏa các quy tắc thứ tự. Nếu workflow không cho phép chu trình, đồ thị dependency phải là DAG (*Directed Acyclic Graph*).

### 4.7. Bất biến luồng điều khiển và luồng dữ liệu

Các node có thể được nối bởi control-flow graph hoặc data-flow graph.

Ví dụ một biến chỉ được đọc sau khi có phép gán trên mọi đường đi đến điểm đọc. Quy tắc này cần phân tích nhiều node và nhiều đường đi, không thể xác định chỉ từ node khai báo hoặc node sử dụng.

### 4.8. Bất biến theo trạng thái và vòng đời

Trong DSL mô tả quy trình, một node hành động chỉ được xuất hiện hoặc thực hiện khi các node trạng thái liên quan thỏa điều kiện.

Ví dụ:
- Hành động ship chỉ được thực hiện sau khi payment đã captured.
- Trạng thái terminal không có outgoing transition.
- Một event không được xử lý hai lần trong cùng một transaction nếu DSL yêu cầu exactly-once semantics.
- Một node compensation phải tương ứng với một hành động có thể được bù trừ.

## 5. Ví dụ: khai báo và sử dụng biến

Xét DSL:

~~~text
let subtotal: Money = order.subtotal
let taxRate: Decimal = 0.08
let tax: Money = subtotal * taxRate
let total: Money = subtotal + tax
~~~

### 5.1. Các node liên quan

Có thể biểu diễn đơn giản:

~~~text
VariableDeclaration(subtotal)
  └── PropertyAccess(order, subtotal)

VariableDeclaration(taxRate)
  └── DecimalLiteral(0.08)

VariableDeclaration(tax)
  └── Multiply
      ├── IdentifierUse(subtotal)
      └── IdentifierUse(taxRate)

VariableDeclaration(total)
  └── Add
      ├── IdentifierUse(subtotal)
      └── IdentifierUse(tax)
~~~

### 5.2. Những bất biến cần kiểm tra

**Reference resolution:** mỗi IdentifierUse phải trỏ đến khai báo hợp lệ.

**Type compatibility:** phép nhân Money với Decimal phải được hỗ trợ và trả về Money; phép cộng phải nhận hai toán hạng Money tương thích.

**Uniqueness:** các tên subtotal, taxRate, tax và total phải duy nhất trong scope nếu DSL cấm khai báo trùng.

**Initialization:** subtotal và taxRate phải được khởi tạo trước khi được đọc nếu DSL sử dụng quy tắc tuần tự.

**Scope:** các khai báo phải nằm trong phạm vi mà những node sử dụng có thể nhìn thấy.

### 5.3. Ví dụ lỗi

~~~text
let subtotal: Money = order.subtotal
let tax: Money = subtotal * taxRate
~~~

Nếu không có khai báo taxRate và không có binding trong context, node IdentifierUse(taxRate) không resolve được. Diagnostic nên gắn với vị trí sử dụng, đồng thời có thể nêu rằng không tìm thấy khai báo tương ứng.

Một trường hợp khác:

~~~text
let taxRate: String = "0.08"
let tax: Money = subtotal * taxRate
~~~

Mỗi khai báo riêng lẻ có thể hợp lệ, nhưng node Multiply có hai toán hạng không tương thích theo type system. Đây là bất biến kiểu liên nút bị vi phạm.

## 6. Ví dụ: bất biến giữa các node trong state machine

Một state machine có thể được mô tả:

~~~text
stateMachine "OrderLifecycle" {
    state Draft
    state Confirmed
    state Shipped
    state Cancelled

    initial Draft

    transition Draft -> Confirmed
    transition Confirmed -> Shipped
    transition Draft -> Cancelled
}
~~~

Semantic checker có thể áp dụng các bất biến:

- Mỗi transition có source và target tồn tại.
- Source và target thuộc cùng state machine.
- Chỉ có một initial state nếu mô hình yêu cầu duy nhất.
- Initial state phải nằm trong tập state đã khai báo.
- Không có hai state cùng ID.
- Transition không được trùng theo định nghĩa của DSL.
- Trạng thái terminal không có outgoing transition nếu quy tắc yêu cầu.
- Tất cả state cần reachable từ initial state nếu DSL yêu cầu không có state chết.

### 6.1. Kiểm tra reference

Tập state là:

~~~text
S = {Draft, Confirmed, Shipped, Cancelled}
~~~

Mỗi transition là một cặp có hướng:

~~~text
T = {
    (Draft, Confirmed),
    (Confirmed, Shipped),
    (Draft, Cancelled)
}
~~~

Điều kiện endpoint hợp lệ:

~~~text
For every (source, target) in T:
    source belongs to S
    target belongs to S
~~~

Nếu có transition `Confirmed -> Archived` nhưng Archived không nằm trong S, validator phát lỗi unresolved target.

### 6.2. Kiểm tra khả năng đạt tới

Từ initial state Draft, có thể duyệt các outgoing edges để tìm tập state reachable.

Với đồ thị trên:
- Draft reachable ngay từ đầu.
- Confirmed reachable từ Draft.
- Cancelled reachable từ Draft.
- Shipped reachable qua Confirmed.

Nếu state Archived được khai báo nhưng không có đường đi đến, nó là unreachable state. Tùy DSL, đây có thể là error hoặc warning.

### 6.3. Kiểm tra chu trình

Không phải mọi chu trình đều sai. Workflow có thể có vòng lặp retry hoặc trạng thái chờ. Bất biến phải mô tả chính xác chu trình nào bị cấm.

Ví dụ, nếu một state machine chỉ cho phép DAG, có thể dùng topological sort hoặc DFS để phát hiện cycle. Nếu vòng lặp được phép nhưng cần giới hạn, validator phải kiểm tra metadata retry hoặc điều kiện thoát.

## 7. Ví dụ: bất biến giữa các node workflow

Xét workflow:

~~~text
workflow "fulfillment" {
    step validateOrder
    step reserveStock dependsOn validateOrder
    step capturePayment dependsOn reserveStock
    step shipOrder dependsOn capturePayment
    step notifyCustomer dependsOn shipOrder
}
~~~

Các node step tạo thành dependency graph.

Bất biến có thể gồm:

1. Mỗi dependency trỏ đến một step tồn tại.
2. Step không phụ thuộc trực tiếp vào chính nó.
3. Không có dependency cycle nếu DSL yêu cầu thứ tự thực thi hữu hạn.
4. Mỗi step ID duy nhất trong workflow.
5. Step bắt buộc có đúng loại cấu hình tương ứng.
6. Step shipOrder chỉ có thể thực hiện sau capturePayment thành công.
7. Nếu có step kết thúc, không còn dependency bắt buộc phía sau nó.

### 7.1. Dependency graph

~~~text
validateOrder
      |
      v
 reserveStock
      |
      v
capturePayment
      |
      v
  shipOrder
      |
      v
notifyCustomer
~~~

Một validator có thể xây adjacency list:

~~~text
validateOrder   -> reserveStock
reserveStock    -> capturePayment
capturePayment  -> shipOrder
shipOrder       -> notifyCustomer
notifyCustomer  -> []
~~~

Nếu thêm `validateOrder dependsOn notifyCustomer`, đồ thị tạo chu trình. Topological sort không thể sắp xếp toàn bộ node; validator có thể phát diagnostic chỉ ra một chu trình phụ thuộc.

### 7.2. Kiểm tra dependency target

Nếu một step khai báo phụ thuộc vào tên không tồn tại, lỗi cần được gắn tại reference trong node phụ thuộc. Nếu tên tồn tại ở workflow khác, validator vẫn phải kiểm tra quy tắc phạm vi; không tự động coi reference là hợp lệ chỉ vì tìm được tên ở nơi khác.

## 8. Xây dựng symbol graph để kiểm tra liên nút

### 8.1. Symbol table và symbol graph

Semantic analyzer thường xây symbol table để ánh xạ tên đến symbol. Khi có nhiều scope, namespace và reference, có thể xây symbol graph gồm:

- Node khai báo.
- Node sử dụng.
- Node scope hoặc module.
- Edge từ reference đến declaration.
- Edge containment giữa scope lồng nhau.
- Edge import/export giữa module.

Ví dụ:

~~~text
Module A
  └── Scope A
       ├── Declaration customerId
       └── Rule check
            └── IdentifierUse customerId
                    |
                    +---- references ----> Declaration customerId
~~~

### 8.2. Quy trình resolve

Một quy trình thường gồm:

1. Tạo scope cho module, block, function hoặc rule.
2. Thu thập các declaration hợp lệ.
3. Xác định scope cha và quan hệ import.
4. Duyệt các node sử dụng tên.
5. Tìm symbol theo quy tắc ưu tiên scope.
6. Gắn reference edge đến symbol được chọn.
7. Phát lỗi nếu không tìm thấy hoặc có nhiều ứng viên mơ hồ.
8. Kiểm tra loại symbol và quyền truy cập.

Nếu ngôn ngữ hỗ trợ forward reference, cần tách bước thu thập declaration khỏi bước resolve use. Nếu chỉ cho phép khai báo trước khi dùng, semantic checker cần xét vị trí và thứ tự.

### 8.3. Shadowing và ambiguity

Giả sử:

~~~text
let status = "GLOBAL"

rule "check" {
    let status = order.status
    return status
}
~~~

Node sử dụng status bên trong rule có thể resolve đến khai báo cục bộ, che khuất khai báo toàn cục. Đây là shadowing.

Nếu hai import cùng đưa vào một tên không được phân biệt bằng namespace hoặc alias, reference có thể mơ hồ. Validator phải báo ambiguity thay vì tùy tiện chọn một symbol.

## 9. Kiểm tra uniqueness và tập node

### 9.1. Uniqueness trong scope

Với một scope S chứa tập declaration D, điều kiện tên duy nhất có thể mô tả:

~~~text
For all distinct d1, d2 in D:
    normalize(d1.name) != normalize(d2.name)
~~~

Hàm normalize phải tuân theo chính sách case sensitivity và Unicode normalization của DSL.

### 9.2. Uniqueness theo signature

Với function overload, chỉ tên giống nhau chưa chắc là lỗi. Hai function có thể cùng tên nhưng khác kiểu hoặc số lượng tham số.

Ví dụ:

~~~text
function format(value: Date): String
function format(value: Money): String
~~~

Nếu DSL cho overload theo kiểu tham số, validator phải kiểm tra uniqueness theo signature chứ không chỉ theo tên.

### 9.3. Uniqueness theo khóa ghép

Trong một mô hình dữ liệu, một nhóm thuộc tính có thể tạo thành khóa duy nhất:

~~~text
Customer {
    countryCode
    localId
}
~~~

Điều kiện duy nhất có thể áp dụng cho cặp (countryCode, localId), không phải từng thuộc tính riêng. Validator cần thu thập các node thuộc cùng tập và so sánh khóa ghép.

### 9.4. Hiệu quả kiểm tra

Với tập node lớn, dùng hash map theo khóa chuẩn hóa thường cho phép kiểm tra uniqueness trong thời gian trung bình tuyến tính O(n). So sánh mọi cặp node có thể tốn O(n²) và chỉ phù hợp với tập rất nhỏ hoặc quy tắc cần so sánh cặp phức tạp.

## 10. Kiểm tra kiểu liên nút

### 10.1. Kiểu của node và kiểu của biểu thức

Type checker gán hoặc suy luận kiểu cho từng node. Bất biến kiểu yêu cầu các node liên kết qua toán tử, assignment, argument hoặc return phải thỏa type rules.

Ví dụ:

~~~text
let age: Integer = 20
let message: String = "Age: " + age
~~~

Nếu DSL không hỗ trợ chuyển Integer sang String khi nối chuỗi, biểu thức cộng vi phạm type rule. Việc kiểm tra cần xem cả operator node và hai operand nodes.

### 10.2. Assignment compatibility

Với assignment:

~~~text
target = expression
~~~

cần xác định:
- Kiểu target.
- Kiểu expression.
- Có subtype hoặc widening conversion nào được phép không.
- Có implicit conversion không.
- Có thể gán null không.
- Kiểu kết quả có bị giới hạn bởi generic hoặc refinement type không.

Một hàm tương thích kiểu có thể được mô tả:

~~~text
isAssignable(sourceType, targetType)
~~~

Semantic checker chỉ chấp nhận assignment nếu hàm này trả true theo quy tắc của type system.

### 10.3. Function call và overload resolution

Lời gọi hàm liên kết node call với một declaration cụ thể. Kiểm tra cần bảo đảm:

- Hàm tồn tại và được truy cập.
- Số lượng đối số hợp lệ.
- Kiểu từng argument tương thích với parameter.
- Generic type parameters được suy luận nhất quán.
- Chỉ có một overload phù hợp nhất hoặc có quy tắc chọn rõ.
- Kiểu trả về tương thích với nơi sử dụng kết quả.

### 10.4. Generic constraints

Với generic:

~~~text
function max<T extends Comparable<T>>(a: T, b: T): T
~~~

các node argument phải có kiểu thống nhất và thỏa constraint của T. Nếu một argument là Integer còn argument kia là Date, lời gọi chỉ hợp lệ nếu type system định nghĩa một kiểu chung đáp ứng Comparable.

## 11. Bất biến về thứ tự khai báo và khởi tạo

Một số DSL quy định tên phải được khai báo trước khi sử dụng; một số cho phép forward reference.

Ví dụ:

~~~text
let total = subtotal + tax
let subtotal = 100
let tax = 8
~~~

Nếu DSL yêu cầu declaration-before-use, node use subtotal và tax vi phạm vì declaration nằm sau. Nếu DSL hỗ trợ forward reference, tài liệu vẫn cần xác định cách xử lý chu trình khởi tạo.

### 11.1. Definite assignment

Trong ngôn ngữ có biến thay đổi được:

~~~text
let result: Integer
if condition then
    result = 10
end
print(result)
~~~

Nếu condition false, result chưa được gán khi print được thực hiện. Definite-assignment analysis kiểm tra trên control-flow graph xem mọi đường đi đến một điểm đọc đều đã gán biến hay chưa.

### 11.2. Data-flow equations

Có thể dùng hai tập:
- IN[n]: biến chắc chắn đã được gán trước node n.
- OUT[n]: biến chắc chắn đã được gán sau node n.

Với node gán x:
- OUT[n] = IN[n] ∪ {x}

Với node điều kiện có nhiều predecessor, tập definite-assigned thường là giao các OUT của predecessor:
- IN[n] = intersection(OUT[p]) với mọi predecessor p.

Thuật toán lặp đến khi các tập ổn định (*fixed point*). Đây là ví dụ điển hình về invariant liên nút cần phân tích toàn graph.

### 11.3. Unreachable code

Nếu một node statement không thể được đi tới từ entry node, nó có thể là unreachable. Điều này thường là warning, nhưng DSL có thể quy định một số cấu trúc unreachable là error, ví dụ bước workflow không thể được kích hoạt.

## 12. Bất biến trên control-flow graph

### 12.1. Control-flow graph là gì?

Control-flow graph (*CFG*) biểu diễn các điểm thực thi và các đường chuyển tiếp có thể xảy ra.

- Node đại diện block hoặc statement.
- Edge biểu diễn khả năng chuyển từ node này sang node khác.
- Entry node là điểm bắt đầu.
- Exit node là điểm kết thúc.

Ví dụ:

~~~text
          [entry]
             |
        [check amount]
          /       \
       true       false
        |           |
   [approve]     [reject]
        \           /
          [exit]
~~~

### 12.2. Các bất biến phổ biến

- Mỗi node thực thi phải có loại successor phù hợp.
- Mọi edge phải nối đến node thuộc cùng graph.
- Mọi node reachable phải có đường đến exit nếu DSL không cho phép vòng lặp vô hạn.
- Return node không có successor thông thường.
- Break/continue chỉ được dùng trong loop hợp lệ.
- Mọi đường đi đến điểm đọc biến phải bảo đảm definite assignment.
- Mọi đường đi đến một operation nhạy cảm phải thỏa precondition.

### 12.3. Dominance và post-dominance

Một node A *dominates* node B nếu mọi đường đi từ entry đến B đều đi qua A. Ví dụ kiểm tra null trước khi truy cập thuộc tính có thể yêu cầu node kiểm tra null dominate node truy cập.

Một node P *post-dominates* node B nếu mọi đường đi từ B đến exit đều đi qua P. Khái niệm này hữu ích để kiểm tra cleanup hoặc finally-like operation luôn được thực hiện.

Các quan hệ dominance có thể giúp xác nhận một số bất biến an toàn mà kiểm tra cục bộ không đủ.

## 13. Bất biến trên dependency graph

### 13.1. Dependency graph

Dependency graph mô tả node nào cần node nào hoàn thành hoặc tồn tại trước.

Ví dụ build DSL:

~~~text
task compile dependsOn generateSources
task test dependsOn compile
task package dependsOn test
~~~

Các bất biến thường gặp:

- Dependency target tồn tại.
- Không có self-dependency.
- Không có cycle nếu graph phải có thứ tự topo.
- Node dependency thuộc đúng project hoặc module.
- Task được tham chiếu phải được bật hoặc export.
- Dependency không tạo ra xung đột tài nguyên nếu DSL quy định.

### 13.2. Topological sort

Nếu dependency graph phải không chu trình, có thể dùng Kahn's algorithm hoặc DFS để sắp xếp topo.

Kahn's algorithm:
1. Tính indegree của mỗi node.
2. Đưa các node indegree bằng 0 vào queue.
3. Lấy một node, thêm vào kết quả.
4. Giảm indegree của các successor.
5. Thêm successor mới có indegree bằng 0.
6. Nếu số node kết quả nhỏ hơn tổng số node, graph có cycle.

Thuật toán có độ phức tạp O(V + E), với V là số node và E là số edge.

### 13.3. Chu trình và chẩn đoán

Khi phát hiện cycle, diagnostic nên hiển thị một đường đi khép kín có liên quan thay vì chỉ báo "dependency cycle". Ví dụ:

~~~text
compile -> test -> package -> compile
~~~

Thông tin này giúp người viết xác định các dependency cần sửa.

Không phải cycle nào cũng sai. Workflow có retry loop hoặc state machine có vòng lặp có thể hợp lệ. Bất biến cần gắn với loại graph và quy tắc của DSL.

## 14. Bất biến về quan hệ containment và ownership

Một model có thể yêu cầu mỗi node con thuộc về đúng một parent hoặc một aggregate.

Ví dụ:
- Mỗi OrderLine thuộc đúng một Order.
- Mỗi WorkflowStep thuộc đúng một Workflow.
- Mỗi local variable thuộc một scope.
- Một AST node không được xuất hiện dưới hai parent nếu cấu trúc yêu cầu cây thuần.

Các bất biến có thể gồm:
- Parent của node tồn tại.
- Child nằm trong tập con được phép của parent.
- Không có node containment cycle.
- Node không bị gắn vào hai container loại exclusive ownership.
- Reference không nhầm lẫn với containment.

Cần phân biệt containment và reference. Một state có thể được transition tham chiếu đến nhiều lần nhưng không có nghĩa state đó bị sở hữu bởi nhiều transition.

## 15. Bất biến liên nút trong type hierarchy

Với DSL hỗ trợ class, record hoặc kiểu dữ liệu tùy biến, quan hệ kế thừa tạo ra các bất biến giữa nhiều node type.

Ví dụ:

~~~text
type Animal
type Dog extends Animal
type Cat extends Animal
~~~

Các điều kiện có thể gồm:
- Supertype tồn tại.
- Không có inheritance cycle nếu DSL cấm.
- Một type không kế thừa chính nó.
- Override có signature và visibility tương thích.
- Interface được triển khai đầy đủ.
- Member không vi phạm quy tắc xung đột.
- Generic bound được thỏa mãn.

### 15.1. Kiểm tra cycle kế thừa

Nếu A extends B, B extends C và C extends A, đồ thị kế thừa có chu trình. Một hierarchy thông thường yêu cầu DAG, vì không có type nào đứng trên cùng theo quan hệ kế thừa.

DFS với ba trạng thái:
- WHITE: chưa thăm.
- GRAY: đang nằm trên recursion stack.
- BLACK: đã xử lý xong.

Nếu duyệt đến node GRAY, đã tìm thấy cycle. Có thể lưu parent chain để hiển thị đường cycle trong diagnostic.

### 15.2. Override consistency

Khi method ở subtype override method của supertype, validator cần so sánh hai declaration:
- Tên và signature.
- Kiểu tham số.
- Kiểu trả về theo covariance/contravariance được phép.
- Visibility.
- Modifier như final, abstract hoặc static.
- Contract precondition/postcondition nếu DSL có quy tắc tương ứng.

Đây là kiểm tra liên nút vì phải so sánh member ở hai type khác nhau.

## 16. Bất biến trong DSL dữ liệu và mô hình miền

Không phải mọi DSL đều mô tả chương trình thực thi. Một DSL có thể mô tả schema, workflow nghiệp vụ hoặc cấu hình. Bất biến liên nút khi đó thường kiểm tra quan hệ giữa các thực thể.

Ví dụ mô hình đặt hàng:

~~~text
customer C100
product P01 price 100
order O500 customer C100 {
    line product P01 quantity 2
}
~~~

Các bất biến:
- Order.customer tham chiếu đến Customer tồn tại.
- Mỗi OrderLine.product tham chiếu đến Product tồn tại.
- Mỗi product ID là duy nhất trong catalog.
- Quantity dương.
- Tổng order bằng tổng line theo quy tắc tiền tệ.
- Không có line tham chiếu sản phẩm đã bị vô hiệu hóa nếu quy tắc miền cấm.

Một constraint liên nút có thể liên kết Order, Customer, Product, OrderLine và thuộc tính của chúng. Validator nên có context chứa model root hoặc repository cần thiết để tra cứu.

### 16.1. Referential integrity

Đối với mỗi reference r từ node nguồn s đến node đích t:
- t phải tồn tại.
- t phải thuộc tập đối tượng được phép tham chiếu.
- Kiểu của t phải tương thích với loại reference.
- Quyền truy cập hoặc visibility phải được thỏa.
- Nếu reference có cardinality, số lượng target phải nằm trong giới hạn.

### 16.2. Cross-document invariants

Một project có thể gồm nhiều file DSL. Bất biến có thể vượt qua ranh giới file:
- Import phải trỏ đến module có trong project.
- Exported symbol phải có tên duy nhất trong namespace.
- Các file phải dùng phiên bản DSL tương thích.
- Một cấu hình environment phải cung cấp mọi key bắt buộc được rule tham chiếu.

Cần xác định phạm vi validation là file, module, project hay workspace. Không thể kết luận một reference bị thiếu nếu các module liên quan chưa được nạp.

## 17. Cách tổ chức semantic checker

### 17.1. Tách các phase

Một semantic checker có thể được chia thành nhiều phase:

~~~text
AST / Model
    |
    v
1. Collect declarations
    |
    v
2. Build scopes and symbol graph
    |
    v
3. Resolve references
    |
    v
4. Infer and check types
    |
    v
5. Build control/dependency graphs
    |
    v
6. Check cross-node invariants
    |
    v
Diagnostics + semantic metadata
~~~

Tách phase giúp các invariant có dependency rõ. Ví dụ type compatibility cần reference resolution hoàn tất trước. Cycle detection cần graph đã được xây dựng.

### 17.2. Validation context

Checker thường cần một context dùng chung:

~~~text
ValidationContext {
    modelRoot
    scopeGraph
    symbolTable
    resolvedReferences
    typeEnvironment
    controlFlowGraphs
    dependencyGraphs
    diagnostics
}
~~~

Context không nhất thiết là một object duy nhất trong implementation. Đây là mô hình khái niệm về dữ liệu các phase cần chia sẻ.

### 17.3. Registry của invariant

Có thể định nghĩa từng checker riêng:

~~~java
interface InvariantChecker {
    String id();
    boolean supports(ModelNode node);
    void check(ModelNode node, ValidationContext context);
}
~~~

Một checker có thể xử lý một node làm điểm bắt đầu nhưng duyệt các node liên quan trong context. Ví dụ checker uniqueness được gọi cho scope node và xét tất cả declaration bên trong.

### 17.4. Đừng gộp mọi quy tắc vào một vòng lặp

Nếu một hàm duyệt AST vừa resolve symbol, vừa kiểm tra kiểu, vừa phát hiện cycle, vừa kiểm tra workflow state, thứ tự phụ thuộc sẽ khó hiểu. Chia phase theo loại quan hệ giúp dễ kiểm soát, test và cập nhật.

Với DSL nhỏ, các phase có thể chạy trong một lần duyệt nếu thứ tự và dữ liệu được quản lý rõ. Mục tiêu là trách nhiệm có thể hiểu và kiểm chứng, không phải bắt buộc tạo nhiều module.

## 18. Thuật toán kiểm tra các bất biến phổ biến

### 18.1. Duplicate detection

Để phát hiện tên trùng trong một scope:

~~~text
seen = map from normalized name to first declaration

for declaration in scope.declarations:
    key = normalize(declaration.name)

    if key exists in seen:
        report duplicate with both source locations
    else:
        seen[key] = declaration
~~~

Dùng hash map thường có thời gian trung bình O(n) với n declaration. Nếu cần gợi ý tên gần giống, có thể chạy bước riêng để tránh làm chậm đường kiểm tra chính.

### 18.2. Reference resolution

~~~text
for reference in allReferences:
    candidates = lookup(reference.name, reference.scope)

    if candidates is empty:
        report unresolved reference
    else if candidates has more than one best match:
        report ambiguous reference
    else:
        bind reference to candidates[0]
~~~

Lookup cần tuân theo thứ tự scope, namespace, import và visibility được định nghĩa cho DSL.

### 18.3. Cycle detection

DFS có thể phát hiện cycle trong directed graph. Cần lưu recursion stack hoặc predecessor map để khôi phục đường đi gây cycle.

Đối với dependency graph lớn, thuật toán Tarjan hoặc Kosaraju có thể tìm strongly connected components. Một component có nhiều node hoặc self-loop cho biết có chu trình.

### 18.4. Reachability

BFS hoặc DFS từ initial/entry node có thể tìm tập node reachable. So sánh với toàn bộ node:
- Node không reachable có thể là dead state hoặc dead code.
- Node reachable không có đường đến exit có thể là path không kết thúc.
- Node kết thúc không reachable có thể cho thấy cấu hình sai.

Cách diễn giải phụ thuộc ngữ nghĩa DSL; validator không nên coi mọi node unreachable đều là lỗi nếu tài liệu cho phép thư viện chứa cấu trúc chưa được sử dụng.

### 18.5. Fixed-point analysis

Một số bất biến data-flow yêu cầu lặp đến khi không còn thay đổi. Ví dụ definite assignment hoặc live-variable analysis dùng các tập IN/OUT cho từng node.

Với graph hữu hạn và transfer functions đơn điệu trên lattice hữu hạn, quá trình lặp sẽ hội tụ. Implementation có thể dùng worklist để chỉ xử lý lại node có predecessor thay đổi.

## 19. Diagnostics cho lỗi liên nút

Một lỗi liên nút thường liên quan đến nhiều vị trí. Diagnostic nên chỉ ra cả node hiện tại và node liên quan.

Ví dụ khai báo trùng:

~~~text
rules.dsl:12:5: error SEM-DUPLICATE-001
Duplicate declaration 'status'.
Previous declaration is at rules.dsl:4:5.
~~~

Ví dụ reference không hợp lệ:

~~~text
workflow.dsl:18:24: error SEM-REFERENCE-002
Unknown workflow step 'sendReceipt'.
No step with this identifier exists in workflow 'checkout'.
~~~

Ví dụ cycle:

~~~text
build.dsl:8:1: error SEM-DEPENDENCY-003
Dependency cycle detected:
compile -> test -> package -> compile
~~~

Một diagnostic tốt nên chứa:
- Mã lỗi ổn định.
- Severity.
- Source range của node phát hiện.
- Related locations của các node liên quan.
- Tên invariant bị vi phạm.
- Mô tả phạm vi kiểm tra.
- Gợi ý sửa nếu có thể xác định.
- Dữ liệu cấu trúc cho editor hoặc IDE.

Không nên chỉ báo một câu chung như "model invalid". Người dùng cần biết những node nào tạo nên vi phạm.

## 20. Incremental semantic checking

Trong editor, một thay đổi nhỏ có thể làm một số bất biến mất hiệu lực. Ví dụ đổi tên declaration có thể ảnh hưởng hàng chục reference; xóa một state có thể làm nhiều transition trở thành dangling reference.

Incremental checker cần theo dõi dependency giữa:
- Node nguồn.
- Symbol được tham chiếu.
- Scope và namespace.
- Kiểu của biểu thức.
- Các node trong graph liên quan.
- Kết quả validation trước đó.

Khi một node thay đổi:
1. Xác định các node và invariant phụ thuộc vào nó.
2. Vô hiệu hóa kết quả cũ tương ứng.
3. Resolve lại reference nếu tên hoặc scope thay đổi.
4. Tính lại kiểu và graph bị ảnh hưởng.
5. Chạy lại invariant liên quan.
6. Cập nhật diagnostics, loại bỏ lỗi đã được sửa.

Một số bất biến toàn cục như uniqueness toàn project hoặc cycle trong dependency graph có thể cần tính lại trên phạm vi rộng. Có thể dùng index và dependency tracking để giảm phần công việc, nhưng cần ưu tiên kết quả đúng trước khi tối ưu.

## 21. Bất biến liên nút và refactoring

Refactoring như rename, move declaration hoặc extract block có thể thay đổi nhiều node cùng lúc.

Ví dụ đổi tên symbol:
- Declaration node đổi tên.
- Mọi reference node đến declaration cần được cập nhật.
- Import alias có thể cần đổi.
- Các tên khác trong scope không được bị thay thế nhầm.
- Uniqueness invariant phải được kiểm tra lại.

Semantic model giúp xác định đúng các node tham chiếu cùng một symbol. Thay thế chuỗi văn bản đơn giản không đủ an toàn vì có thể đổi comment, string literal hoặc identifier khác cùng cách viết.

Sau refactoring, semantic checker nên xác nhận các reference vẫn resolve và các invariant liên quan còn đúng trước khi ghi thay đổi.

## 22. Kiểm thử bất biến liên nút

Một invariant cần test trên nhóm node và quan hệ, không chỉ test một node riêng.

### 22.1. Positive và negative cases

Với uniqueness:
- Hai declaration có tên khác nhau trong cùng scope: hợp lệ.
- Hai declaration cùng tên trong scope cấm trùng: lỗi.
- Hai declaration cùng tên ở hai scope độc lập: theo chính sách shadowing.

Với transition:
- Source và target tồn tại trong cùng state machine: hợp lệ.
- Target không tồn tại: lỗi.
- Target tồn tại ở state machine khác: lỗi nếu không được phép cross-machine reference.

### 22.2. Boundary cases

Kiểm thử:
- Scope rỗng.
- Một declaration.
- Nhiều declaration cùng tên nhưng khác case.
- Tên khác nhau trước normalization nhưng giống nhau sau normalization.
- Graph không có edge.
- Graph có self-loop.
- Graph có một cycle nhỏ.
- Graph có nhiều component.
- Reference qua nhiều tầng import.

### 22.3. Graph fixtures

Nên lưu fixture biểu diễn graph và kết quả kỳ vọng. Ví dụ dependency graph có cycle:

~~~text
A -> B
B -> C
C -> A
D -> E
~~~

Test cần xác nhận checker phát hiện cycle A-B-C-A nhưng không đánh dấu component D-E là có cycle.

### 22.4. Property-based testing

Có thể sinh graph ngẫu nhiên để kiểm tra:
- Mọi edge đều trỏ đến node tồn tại sau khi graph được xây dựng.
- Topological sort chỉ thành công với DAG.
- Nếu thêm một edge đóng chu trình, cycle detector phát hiện.
- Mỗi reference resolved phải trỏ đến symbol thuộc tập visibility hợp lệ.
- Kết quả kiểm tra không phụ thuộc thứ tự duyệt node nếu đặc tả không quy định thứ tự.

### 22.5. Regression tests

Mỗi lỗi liên nút từng được phát hiện trong thực tế nên trở thành fixture. Khi thay đổi scope resolution, type system hoặc graph algorithm, chạy lại các fixture để ngăn lỗi quay trở lại.

## 23. Hiệu năng và giới hạn khi kiểm tra graph lớn

Một mô hình DSL có thể chứa hàng nghìn hoặc hàng triệu node. Các bước semantic checking cần được thiết kế theo kích thước thực tế.

Các nguyên tắc:
- Dùng index theo tên và scope để lookup nhanh.
- Cache type của node nếu dependency không đổi.
- Dùng adjacency list khi graph thưa.
- Dùng worklist cho data-flow fixed-point analysis.
- Chỉ kiểm tra lại invariant bị ảnh hưởng khi có dependency tracking đáng tin cậy.
- Đặt giới hạn độ sâu hoặc số node khi xử lý input không tin cậy.
- Tránh duyệt toàn bộ graph lặp lại cho từng node nếu có thể gom theo scope hoặc component.
- Giới hạn số diagnostics và nhóm lỗi trùng lặp.

Độ phức tạp tham khảo:

| Phép kiểm tra | Thuật toán thường dùng | Độ phức tạp điển hình |
|---|---|---|
| Duplicate names | Hash map theo scope | O(n) trung bình |
| Reachability | BFS/DFS | O(V + E) |
| Cycle detection | DFS hoặc SCC | O(V + E) |
| Topological sort | Kahn hoặc DFS | O(V + E) |
| Reference lookup | Index theo scope/name | Phụ thuộc số ứng viên, thường gần O(1) trung bình |
| Data-flow | Worklist fixed point | Phụ thuộc graph và số lần hội tụ |

Các con số này giả định cấu trúc dữ liệu phù hợp và thao tác trên node/edge có chi phí hằng số hoặc được index. Không nên suy diễn rằng mọi checker đều tuyến tính nếu quy tắc yêu cầu so sánh cặp hoặc giải quyết constraint phức tạp.

## 24. Quy trình thiết kế và triển khai bất biến liên nút

Có thể áp dụng quy trình sau:

1. **Xác định node types:** liệt kê các loại node có ý nghĩa trong AST hoặc model.
2. **Xác định quan hệ:** containment, reference, dependency, control-flow và data-flow.
3. **Viết invariant bằng ngôn ngữ rõ ràng:** nêu context, tập node áp dụng và điều kiện phải đúng.
4. **Phân loại phạm vi:** node pair, scope, module, model root, project hay runtime graph.
5. **Xác định prerequisite:** invariant cần symbol resolution, type inference hoặc graph construction trước không.
6. **Chọn thuật toán:** index, traversal, uniqueness check, reachability, cycle detection hoặc fixed-point analysis.
7. **Thiết kế diagnostics:** chỉ ra node gây lỗi và các node liên quan.
8. **Tích hợp theo phase:** chạy checker sau khi dữ liệu cần thiết đã sẵn sàng.
9. **Hỗ trợ incremental update:** theo dõi dependency và vô hiệu hóa kết quả cũ.
10. **Viết test:** positive, negative, boundary, graph fixtures, property-based và regression.
11. **Đo hiệu năng:** kiểm tra trên model có kích thước và cấu trúc đại diện.

Một invariant được đặc tả tốt cần trả lời được: kiểm tra node nào, quan hệ nào, trong phạm vi nào, ở giai đoạn nào, khi vi phạm thì báo ở đâu và các bước sau có được tiếp tục không.

## 25. Những sai lầm thường gặp

- **Chỉ kiểm tra từng node:** bỏ sót duplicate declaration, unresolved reference hoặc type mismatch giữa các node.
- **Không định nghĩa phạm vi:** uniqueness hoặc reference có thể bị áp dụng nhầm toàn cục thay vì trong scope.
- **Nhầm containment với reference:** một node được tham chiếu nhiều lần không có nghĩa nó có nhiều parent sở hữu.
- **Giả định mọi cycle đều sai:** workflow retry hoặc state machine có thể cần chu trình.
- **Không xây graph rõ ràng:** checker phải tìm quan hệ bằng cách quét lại AST nhiều lần và dễ bỏ sót cạnh.
- **Resolve reference quá sớm:** module hoặc declaration cần thiết có thể chưa được nạp.
- **Báo lỗi thiếu related location:** người dùng không biết node nào xung đột với node hiện tại.
- **Chạy lại toàn bộ không cần thiết:** editor chậm khi một thay đổi nhỏ làm validation toàn model.
- **Tối ưu incremental quá sớm:** cache cũ có thể khiến checker bỏ sót lỗi mới.
- **Không kiểm thử graph bất thường:** self-loop, cycle nhiều node và component rời rạc dễ bị xử lý sai.

## 26. Kết luận

Bất biến liên nút là những điều kiện ngữ nghĩa phải đúng khi xem xét nhiều node và quan hệ giữa chúng trong AST hoặc model của DSL. Chúng bao gồm symbol resolution, uniqueness, type compatibility, reference integrity, containment, dependency ordering, control-flow, data-flow, reachability và các quy tắc theo trạng thái.

Để kiểm tra hiệu quả, semantic analyzer cần xây dựng scope, symbol graph và các đồ thị liên quan, sau đó chạy các checker theo thứ tự phụ thuộc rõ ràng. Diagnostics phải chỉ ra node gây lỗi và những node liên quan; kiểm thử cần bao phủ cả trường hợp hợp lệ, vi phạm, graph cycle và cập nhật incremental. Nhờ đó, DSL có thể bảo đảm tính nhất quán trên toàn mô hình thay vì chỉ xác nhận từng thành phần riêng lẻ.

