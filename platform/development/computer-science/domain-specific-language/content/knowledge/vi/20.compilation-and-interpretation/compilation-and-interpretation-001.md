# Thông dịch DSL

## 1. Thông dịch DSL là gì?

Thông dịch DSL (Domain-Specific Language) là quá trình đọc một chương trình viết bằng ngôn ngữ chuyên biệt, phân tích cấu trúc của nó và thực hiện các thao tác tương ứng trong môi trường chạy. Thành phần thực hiện công việc này thường được gọi là **interpreter** (bộ thông dịch).

Ví dụ, một DSL dùng để mô tả quy tắc xét duyệt đơn hàng có thể viết:

~~~text
rule large-order {
    when order.total > money(10000000, VND)
    then requireManualReview(order.id)
}
~~~

Interpreter tiếp nhận văn bản trên, nhận diện rule, điều kiện và hành động, rồi đánh giá điều kiện bằng dữ liệu của đơn hàng. Nếu điều kiện đúng, nó gọi hành động yêu cầu xét duyệt thủ công.

Thông dịch không đơn giản là đọc từng dòng văn bản rồi thực hiện ngay. Một interpreter hoàn chỉnh thường có các giai đoạn:

1. Đọc nguồn DSL và nhận diện token.
2. Phân tích token thành cây cú pháp hoặc biểu diễn trung gian.
3. Kiểm tra tên, kiểu và ràng buộc tĩnh nếu ngôn ngữ hỗ trợ.
4. Liên kết các hàm, module và capability mà chương trình được phép sử dụng.
5. Đánh giá biểu thức và thực thi câu lệnh trong runtime.
6. Thu thập kết quả, lỗi và thông tin phục vụ debug hoặc audit.

Interpreter là một phần quan trọng của kiến trúc DSL vì nó quyết định ý nghĩa thực tế của chương trình, cách truy cập dữ liệu, cách gọi hành động và giới hạn an toàn khi thực thi.

## 2. Thông dịch và biên dịch khác nhau thế nào?

Biên dịch (compilation) chuyển chương trình nguồn sang một dạng đích trước khi chương trình được chạy. Dạng đích có thể là mã máy, mã bytecode, mã của ngôn ngữ chủ hoặc một biểu diễn trung gian. Thông dịch thường đánh giá biểu diễn của chương trình trong một runtime thay vì tạo một executable độc lập trước.

| Tiêu chí | Thông dịch | Biên dịch |
|---|---|---|
| Thời điểm xử lý | Có thể phân tích và thực thi trong cùng quy trình chạy | Thường có bước chuyển đổi trước khi chạy |
| Đầu ra | Kết quả thực thi, trạng thái runtime hoặc bytecode tạm | Mã máy, bytecode, mã nguồn đích hoặc artifact |
| Tính linh hoạt | Có thể nhận chương trình mới và chạy ngay | Cần biên dịch lại khi nguồn hoặc phụ thuộc thay đổi |
| Phát hiện lỗi | Có thể phát hiện khi parse, kiểm tra hoặc đi vào nhánh thực thi | Có thể phát hiện nhiều lỗi trước khi chạy |
| Hiệu năng | Phụ thuộc interpreter, tối ưu hóa và chi phí runtime | Mã đích có thể được tối ưu mạnh trước hoặc trong lúc chạy |
| Tính di động | Runtime cần có mặt trên môi trường đích | Artifact phụ thuộc vào loại mã đích và runtime tương ứng |

Sự phân biệt này không tuyệt đối. Một interpreter có thể biên dịch DSL thành bytecode rồi thực thi bằng virtual machine. Một hệ thống biên dịch cũng có thể dùng interpreter để chạy một số biểu thức hoặc giai đoạn đánh giá.

Vì vậy, cần phân biệt **mô hình thực thi** với **các bước triển khai**. Một hệ thống được gọi là thông dịch DSL nếu runtime chịu trách nhiệm diễn giải ý nghĩa chương trình và điều phối việc thực thi, ngay cả khi nó có bước chuyển AST sang bytecode nội bộ.

## 3. Pipeline của một interpreter

Một pipeline thông dịch điển hình:

~~~mermaid
flowchart TD
    A["DSL source"] --> B["Lexer"]
    B --> C["Parser"]
    C --> D["AST"]
    D --> E["Static checks"]
    E --> F["Link functions and modules"]
    F --> G["Interpreter / VM"]
    G --> H["Runtime context"]
    H --> I["Results and diagnostics"]
~~~

### 3.1. Đọc và phân tích nguồn

Lexer chuyển ký tự thành token. Parser sử dụng grammar để tạo AST (Abstract Syntax Tree). AST biểu diễn cấu trúc có ý nghĩa của chương trình, chẳng hạn khai báo rule, biểu thức so sánh, lời gọi hàm và hành động.

Ví dụ:

~~~text
let payable = subtotal - discount;
~~~

có thể được biểu diễn khái quát thành:

~~~text
VariableDeclaration
  name: payable
  initializer:
    BinaryExpression
      operator: SUBTRACT
      left: Identifier(subtotal)
      right: Identifier(discount)
~~~

Interpreter làm việc với cấu trúc này thay vì phải phân tích lại chuỗi ký tự mỗi lần thực thi.

### 3.2. Kiểm tra và liên kết

Trước khi chạy, hệ thống có thể kiểm tra tên đã khai báo, kiểu biểu thức, chữ ký hàm và quyền truy cập. Sau đó, linker hoặc registry liên kết tên hàm trong AST với implementation thực tế.

Ví dụ, lời gọi requireManualReview có thể được liên kết với một function handle do ứng dụng chủ đăng ký. Nếu hàm không tồn tại hoặc không được phép dùng trong policy hiện tại, hệ thống nên báo lỗi trước khi thực thi rule.

### 3.3. Thực thi

Interpreter duyệt AST hoặc chạy bytecode trong một runtime context. Context cung cấp biến, dữ liệu đầu vào, hàm tích hợp, cấu hình, quyền và giới hạn tài nguyên. Kết quả có thể là một giá trị, một tập thay đổi hoặc một chuỗi hành động.

## 4. Các kiến trúc thông dịch phổ biến

### 4.1. Tree-walk interpreter

Tree-walk interpreter duyệt trực tiếp AST. Mỗi loại node có một quy tắc đánh giá riêng. Ví dụ:

- Literal trả về giá trị tương ứng.
- Identifier tra cứu giá trị trong môi trường hiện tại.
- Binary expression đánh giá hai toán hạng rồi áp dụng toán tử.
- Function call đánh giá đối số rồi gọi hàm tương ứng.
- If statement đánh giá điều kiện và chạy nhánh phù hợp.

Một cách tổ chức thường gặp là dùng visitor:

~~~java
interface ExpressionVisitor<T> {
    T visitLiteral(LiteralExpr expression);
    T visitVariable(VariableExpr expression);
    T visitBinary(BinaryExpr expression);
    T visitCall(CallExpr expression);
}

interface Expression {
    <T> T accept(ExpressionVisitor<T> visitor);
}
~~~

Interpreter triển khai visitor để đánh giá từng node. Kiểu trả về T có thể là Value hoặc một kiểu giá trị runtime cụ thể.

Ưu điểm:

- Kiến trúc đơn giản, dễ triển khai cho DSL nhỏ.
- Dễ ánh xạ lỗi runtime về node nguồn.
- Dễ thêm loại biểu thức và quy tắc đánh giá.
- Không cần tạo mã đích hoặc máy ảo riêng.

Đánh đổi:

- Mỗi lần chạy thường phải duyệt AST.
- Nhiều lớp node và lời gọi visitor có thể tạo overhead.
- Tối ưu hóa trên luồng lệnh khó hơn so với bytecode.
- Cần chú ý quản lý đệ quy khi biểu thức hoặc block lồng sâu.

Tree-walk phù hợp với DSL cấu hình, rule engine, biểu thức nghiệp vụ hoặc ngôn ngữ có tập câu lệnh vừa phải.

### 4.2. Bytecode interpreter và virtual machine

Thay vì duyệt AST trực tiếp, hệ thống có thể chuyển AST thành bytecode. Bytecode là tập lệnh cấp cao được thiết kế cho một máy ảo riêng.

Ví dụ biểu thức:

~~~text
total = subtotal - discount
~~~

có thể được chuyển thành các lệnh giả định:

~~~text
LOAD subtotal
LOAD discount
SUBTRACT
STORE total
~~~

Virtual machine (VM) đọc và thực hiện từng lệnh. VM thường có:

- Instruction set: tập lệnh được hỗ trợ.
- Program counter: vị trí lệnh tiếp theo.
- Operand stack hoặc register: nơi lưu giá trị trung gian.
- Call stack: thông tin lời gọi hàm và khung thực thi.
- Runtime values: mô hình giá trị của DSL.
- Exception hoặc error mechanism: cơ chế xử lý lỗi.

Ưu điểm của bytecode:

- Biểu diễn gọn và có thể thực thi nhiều lần.
- Có thể tối ưu hóa trước khi chạy.
- Tách parser khỏi engine thực thi.
- Dễ lưu cache hoặc đóng gói chương trình đã phân tích.
- Có thể áp dụng giới hạn số lệnh và kiểm tra bytecode trước khi chạy.

Đánh đổi:

- Phải thiết kế instruction set và VM.
- Debug cần ánh xạ lệnh bytecode về node hoặc vị trí nguồn.
- Cần quản lý tương thích phiên bản bytecode.
- Việc kiểm thử và tối ưu VM phức tạp hơn tree-walk.

### 4.3. Interpreter kết hợp (hybrid)

Một hệ thống có thể dùng tree-walk cho giai đoạn đầu, sau đó biên dịch những biểu thức hoặc rule được gọi thường xuyên thành bytecode. Cách này giữ được sự đơn giản khi phát triển và mở đường cho tối ưu hóa khi cần.

Một kiến trúc hybrid có thể:

1. Parse DSL thành AST.
2. Thực thi trực tiếp AST cho chương trình nhỏ hoặc lần chạy đầu.
3. Theo dõi tần suất sử dụng node hoặc rule.
4. Biên dịch vùng nóng thành bytecode.
5. Cache bytecode theo source version và runtime version.
6. Chạy bytecode cho những lần thực thi sau.

Không phải DSL nào cũng cần hybrid. Chỉ nên bổ sung nhiều tầng thực thi khi có yêu cầu hiệu năng hoặc khả năng triển khai cụ thể.

## 5. Môi trường thực thi (runtime environment)

Runtime environment là tập hợp trạng thái và dịch vụ mà chương trình DSL nhìn thấy khi chạy. Nó có thể chứa:

- Biến cục bộ và biến toàn cục.
- Dữ liệu đầu vào, chẳng hạn order hoặc customer.
- Hàm tích hợp và operator.
- Module, type và object registry.
- Cấu hình theo tenant hoặc môi trường.
- Clock, locale và timezone nếu DSL cần.
- Quyền truy cập capability.
- Budget thời gian, bộ nhớ và số bước thực thi.

Ví dụ một rule sử dụng dữ liệu đơn hàng:

~~~text
rule priority-customer {
    when customer.membership == "GOLD"
    then setPriority(order.id, HIGH)
}
~~~

Interpreter cần có cách cung cấp customer, order và hàm setPriority vào runtime. Không nên để các tên này tự động truy cập mọi dữ liệu trong ứng dụng chủ. Context nên chỉ cung cấp đúng dữ liệu và hành động mà chương trình được phép sử dụng.

## 6. Môi trường biến và scope

Interpreter cần theo dõi giá trị của các biến trong khi chương trình chạy. Cấu trúc thường dùng là environment (môi trường), ánh xạ tên hoặc symbol sang giá trị.

Ví dụ:

~~~text
let threshold = 100;

function isLarge(value) {
    let minimum = threshold;
    return value > minimum;
}
~~~

Khi gọi isLarge, interpreter tạo môi trường cho tham số value và biến minimum. Hàm có thể truy cập threshold từ scope bên ngoài nếu DSL dùng lexical scoping.

### 6.1. Lexical scope

Lexical scope xác định phạm vi biến dựa trên vị trí khai báo trong mã nguồn. Hàm hoặc block có thể nhìn thấy các khai báo trong scope bao quanh theo quy tắc của ngôn ngữ.

Ví dụ:

~~~text
let rate = 5;

function calculate(amount) {
    let fee = amount * rate / 100;
    return fee;
}
~~~

Trong hàm calculate, rate được tìm trong scope bên ngoài nếu không có khai báo cục bộ cùng tên.

### 6.2. Dynamic scope

Dynamic scope xác định biến dựa trên chuỗi lời gọi hàm tại thời điểm chạy. Cách này ít phổ biến hơn trong DSL hiện đại vì cùng một hàm có thể nhận giá trị khác nhau tùy caller, khiến hành vi khó dự đoán.

Nếu DSL hỗ trợ dynamic scope, quy tắc tra cứu phải được mô tả rõ và có kiểm thử. Với rule và policy nghiệp vụ, lexical scope thường dễ hiểu và dễ phân tích hơn.

### 6.3. Shadowing

Shadowing xảy ra khi khai báo bên trong che khuất tên ở scope bên ngoài:

~~~text
let limit = 100;

function evaluate() {
    let limit = 50;
    return limit;
}
~~~

Trong hàm, limit tham chiếu tới giá trị 50. Interpreter cần lưu môi trường theo scope để phân giải đúng tên. DSL cũng cần quyết định có cho phép shadowing hay báo lỗi khi tên bị khai báo lại.

## 7. Mô hình giá trị runtime

Interpreter cần một mô hình biểu diễn giá trị của DSL. Một tập giá trị phổ biến gồm:

- Boolean.
- Integer và Decimal.
- String.
- Date, Time và Duration.
- List, Map và Tuple.
- Object hoặc record theo schema.
- Null, None hoặc Option.
- Function hoặc callable.
- Giá trị miền như Money, CustomerId hoặc OrderStatus.

Có thể dùng một kiểu Value tổng quát:

~~~java
sealed interface Value
        permits BooleanValue, NumberValue, StringValue,
                ListValue, RecordValue, NullValue {
}

record BooleanValue(boolean value) implements Value {}
record NumberValue(BigDecimal value) implements Value {}
record StringValue(String value) implements Value {}
record NullValue() implements Value {}
~~~

Đây là mô hình minh họa. Một implementation thực tế có thể dùng tagged union, class hierarchy hoặc kiểu dữ liệu của ngôn ngữ chủ.

Việc dùng một mô hình giá trị thống nhất giúp interpreter định nghĩa rõ cách so sánh, chuyển kiểu, tuần tự hóa và báo lỗi. Tránh để mọi biểu thức trả về Object tùy ý nếu runtime cần kiểm soát kiểu và quyền truy cập.

### 7.1. Null và giá trị thiếu

DSL cần phân biệt giá trị null, trường không tồn tại và dữ liệu chưa được cung cấp nếu những trạng thái này có ý nghĩa khác nhau. Ví dụ, trường discountRate có thể:

- Không tồn tại trong schema.
- Tồn tại nhưng không có giá trị.
- Có giá trị bằng 0.

Nếu gộp cả ba thành null, rule có thể đưa ra quyết định sai. Mô hình Option, Maybe hoặc kết quả tra cứu có trạng thái rõ ràng giúp giảm nhập nhằng.

## 8. Đánh giá biểu thức

Interpreter đánh giá biểu thức theo quy tắc của DSL. Ví dụ:

~~~text
let payable = subtotal - discount;
let approved = payable <= creditLimit and customer.isActive;
~~~

Để đánh giá biểu thức thứ hai, interpreter cần:

1. Tra cứu payable và creditLimit.
2. Thực hiện phép so sánh và nhận Boolean.
3. Đánh giá customer.isActive theo quy tắc truy cập thuộc tính.
4. Kết hợp hai Boolean bằng toán tử and.

### 8.1. Thứ tự đánh giá

DSL cần quy định thứ tự đánh giá toán hạng và đối số hàm. Ví dụ, với phép cộng, thông thường vế trái được đánh giá trước vế phải. Với lời gọi hàm, các đối số có thể được đánh giá từ trái sang phải.

Thứ tự rõ ràng quan trọng khi biểu thức có side effect. Nếu một biểu thức ghi log hoặc cập nhật trạng thái, thay đổi thứ tự có thể làm kết quả khác nhau.

### 8.2. Short-circuit evaluation

Với toán tử and và or, DSL có thể dùng short-circuit:

- Với A and B, nếu A là false thì không cần đánh giá B.
- Với A or B, nếu A là true thì không cần đánh giá B.

Ví dụ:

~~~text
customer != null and customer.isActive
~~~

Nếu vế trái false, interpreter không đánh giá customer.isActive. Điều này có thể tránh truy cập thuộc tính trên giá trị null. Nếu DSL chọn đánh giá cả hai vế, hành vi và yêu cầu kiểm tra null sẽ khác; cần quy định rõ.

### 8.3. So sánh và số học

Runtime phải định nghĩa các phép toán hợp lệ cho từng kiểu. Ví dụ, phép cộng hai Money chỉ hợp lệ nếu cùng loại tiền hoặc có quy tắc chuyển đổi được chỉ định. Phép chia có thể trả về Decimal hoặc một kiểu tỷ lệ tùy DSL.

Không nên dùng phép tính floating point cho các đại lượng tài chính nếu yêu cầu độ chính xác thập phân. Cần quy định độ chính xác, làm tròn và cách xử lý chia cho 0.

## 9. Thực thi câu lệnh và điều khiển luồng

Ngoài biểu thức, interpreter phải xử lý câu lệnh và luồng điều khiển:

- Khai báo biến.
- Gán giá trị.
- If/else.
- Vòng lặp.
- Return, break và continue.
- Gọi hàm.
- Khai báo hoặc thực thi rule.
- Xử lý lỗi.

Ví dụ:

~~~text
if order.total > threshold {
    requireManualReview(order.id);
} else {
    approveAutomatically(order.id);
}
~~~

Interpreter đánh giá điều kiện, sau đó thực thi một nhánh theo kết quả. Với vòng lặp, cần có cơ chế giới hạn số vòng hoặc số bước để chương trình không chạy vô hạn.

### 9.1. Return và luồng điều khiển

Một lệnh return làm kết thúc hàm hiện tại và trả giá trị về caller. Trong interpreter, có thể biểu diễn return bằng một control signal riêng thay vì dùng exception chung. Tương tự, break và continue cần được xử lý tại vòng lặp gần nhất theo quy tắc scope.

Điều này giúp luồng điều khiển lồng nhau có thể được thực thi đúng mà không làm lẫn lỗi runtime với tín hiệu điều khiển bình thường.

## 10. Hàm tích hợp và liên kết với ngôn ngữ chủ

DSL thường cần gọi các hàm do ứng dụng chủ cung cấp, chẳng hạn:

- Đọc thuộc tính từ dữ liệu nghiệp vụ.
- Tính toán hoặc chuyển đổi giá trị.
- Gửi thông báo.
- Tạo yêu cầu phê duyệt.
- Ghi nhận sự kiện.
- Truy vấn một nguồn dữ liệu được cấp quyền.

Các hàm này thường được đăng ký trong function registry:

~~~java
public interface DslFunction {
    String name();
    Value invoke(List<Value> arguments, EvaluationContext context);
}
~~~

Khi interpreter gặp function call, nó tra cứu tên trong registry, kiểm tra số lượng và kiểu đối số, sau đó gọi implementation.

Không nên để DSL gọi tùy ý mọi phương thức public của ứng dụng chủ. Một registry tường minh tạo ranh giới API, giúp kiểm soát quyền, ghi log và thay đổi implementation mà không làm DSL phụ thuộc trực tiếp vào cấu trúc ứng dụng.

### 10.1. Binding và adapter

Binding là cơ chế ánh xạ một hàm hoặc kiểu trong DSL tới implementation ở runtime. Adapter có thể chuyển kiểu dữ liệu giữa DSL và ngôn ngữ chủ.

Ví dụ, DSL dùng Money<VND> trong khi ứng dụng chủ dùng một class Money riêng. Adapter chịu trách nhiệm chuyển đổi và kiểm tra tính hợp lệ. Ranh giới này cần xác định rõ:

- Kiểu đầu vào và đầu ra.
- Quy tắc chuyển đổi.
- Exception được ánh xạ thành lỗi DSL nào.
- Side effect có thể xảy ra.
- Quyền và budget được áp dụng.

## 11. Hàm người dùng và call stack

Nếu DSL cho phép người dùng định nghĩa hàm, interpreter cần xử lý lời gọi lồng nhau và đệ quy.

Mỗi lần gọi hàm thường tạo một **call frame** chứa:

- Tham số và biến cục bộ.
- Môi trường lexical hoặc tham chiếu tới closure.
- Vị trí lệnh hoặc node đang thực thi.
- Địa chỉ quay về sau khi hàm kết thúc.
- Thông tin phục vụ debug và trace.

Ví dụ:

~~~text
function calculateFee(order) {
    let subtotal = order.total;
    return subtotal * 0.02;
}

let fee = calculateFee(currentOrder);
~~~

Khi gọi calculateFee, interpreter tạo frame với order được gán đối số currentOrder. Biến subtotal nằm trong frame đó. Khi return, frame được tháo khỏi call stack và kết quả được trả về nơi gọi.

Đệ quy cần giới hạn độ sâu hoặc sử dụng kỹ thuật thực thi phù hợp để tránh stack overflow. Nếu DSL không cần đệ quy, có thể cấm hoặc giới hạn để giảm rủi ro.

## 12. Closure và hàm bậc cao

Closure là hàm đi kèm môi trường tại nơi nó được tạo ra. Closure cho phép hàm sử dụng biến bên ngoài ngay cả khi scope tạo hàm đã kết thúc.

Ví dụ:

~~~text
function makeThresholdChecker(limit) {
    return value -> value > limit;
}

let isLargeOrder = makeThresholdChecker(1000000);
let result = isLargeOrder(order.total);
~~~

Lambda giữ lại giá trị limit từ lần gọi makeThresholdChecker. Interpreter cần biểu diễn closure bằng:

- Mã hoặc AST của thân hàm.
- Tham số.
- Environment được capture.
- Thông tin kiểu hoặc chữ ký nếu DSL hỗ trợ kiểm tra kiểu.

Nếu closure capture biến có thể thay đổi, cần quy định capture theo giá trị hay theo tham chiếu. Quy tắc này ảnh hưởng hành vi khi biến ngoài thay đổi sau khi closure được tạo.

## 13. Lỗi runtime trong quá trình thông dịch

Một chương trình có thể parse thành công và vượt qua kiểm tra tĩnh nhưng vẫn gặp lỗi khi chạy:

- Chia cho 0.
- Truy cập trường không tồn tại trong dữ liệu thực tế.
- Chuyển kiểu thất bại.
- Gọi hàm tích hợp với dữ liệu không hợp lệ.
- Vượt giới hạn vòng lặp hoặc độ sâu đệ quy.
- Dịch vụ ngoài timeout hoặc từ chối yêu cầu.
- Thiếu quyền truy cập capability.

Interpreter nên phân biệt lỗi do chương trình DSL với lỗi hạ tầng hoặc lỗi từ ứng dụng chủ. Ví dụ, lỗi gọi một hàm không tồn tại có thể là lỗi liên kết chương trình; timeout khi gọi dịch vụ thanh toán là lỗi tích hợp runtime.

### 13.1. Diagnostic runtime

Thông tin lỗi runtime nên gồm:

- Mã lỗi ổn định.
- Thông điệp dễ hiểu.
- Vị trí nguồn của biểu thức hoặc câu lệnh.
- Rule, function hoặc action đang chạy.
- Call stack hoặc execution trace nếu có.
- Correlation ID để liên kết với log của ứng dụng chủ.

Ví dụ:

~~~text
RUNTIME-014: Division by zero.
  at pricing.dsl:18:22
  function calculateAverage(order)
  called from rule monthly-report
~~~

Stack trace nên được giới hạn và loại bỏ thông tin nhạy cảm. Với lỗi tích hợp, có thể đính kèm nguyên nhân gốc nhưng không đưa token, thông tin xác thực hoặc dữ liệu cá nhân vào message.

### 13.2. Xử lý lỗi trong DSL

DSL có thể cung cấp cấu trúc try/catch hoặc result type để người viết xử lý lỗi có thể dự đoán. Tuy nhiên, không nên cho phép chương trình bắt và che giấu mọi lỗi hệ thống. Các lỗi bảo mật, lỗi cấu hình runtime hoặc vi phạm giới hạn có thể cần dừng thực thi ngay.

## 14. Tính xác định và side effect

Một interpreter có thể chạy cùng một chương trình nhiều lần. Để kết quả dễ dự đoán, cần quy định cách xử lý thời gian, số ngẫu nhiên, dữ liệu ngoài và side effect.

### 14.1. Deterministic execution

Thực thi xác định (deterministic execution) có nghĩa cùng chương trình và cùng đầu vào theo hợp đồng sẽ tạo cùng kết quả quan sát được.

Điều này dễ đạt hơn nếu:

- Hàm DSL thuần không thay đổi trạng thái.
- Clock và random được truyền vào như dependency tường minh.
- Thứ tự duyệt collection được xác định.
- Quy tắc số học và làm tròn ổn định.
- Dữ liệu ngoài được snapshot hoặc version hóa.

Không phải DSL nào cũng cần hoàn toàn deterministic. Workflow có side effect thường cần gọi dịch vụ bên ngoài. Nhưng các side effect nên được khai báo hoặc kiểm soát qua capability thay vì phát sinh ngầm từ mọi biểu thức.

### 14.2. Side effect và transaction

Một action có thể cập nhật đơn hàng, gửi email hoặc tạo yêu cầu phê duyệt. Nếu chương trình thất bại giữa chừng, hệ thống cần quyết định thay đổi nào được giữ lại.

Các lựa chọn gồm:

- Thực thi trong transaction nếu mọi thao tác nằm trong một hệ thống hỗ trợ transaction.
- Tạo execution plan trước, sau đó ứng dụng chủ quyết định commit.
- Dùng outbox hoặc workflow state để xử lý side effect phân tán.
- Thiết kế action idempotent để có thể thử lại an toàn.

Interpreter không tự tạo được transaction phân tán chỉ bằng cách bao các lời gọi hàm trong một block. Hợp đồng transaction cần do runtime và hệ thống tích hợp phối hợp thực hiện.

## 15. Bảo mật khi thông dịch DSL

Nếu người dùng có thể gửi chương trình DSL để thực thi, interpreter phải xem mã nguồn là đầu vào không tin cậy. Việc chạy trong process của ứng dụng chủ có thể tạo rủi ro nếu DSL được phép truy cập class, file, network hoặc reflection tùy ý.

Một interpreter an toàn nên:

1. Chỉ export các hàm và kiểu được phê duyệt.
2. Không cho DSL gọi tùy ý API hoặc reflection của ngôn ngữ chủ.
3. Áp dụng capability cho file, mạng, database và các tài nguyên khác.
4. Giới hạn số bước, thời gian, bộ nhớ, call depth và kích thước dữ liệu.
5. Kiểm tra input và output ở ranh giới binding.
6. Cô lập tenant và execution context.
7. Ghi audit event cho các hành động nhạy cảm.
8. Có cơ chế dừng hoặc hủy một lần thực thi.

### 15.1. Resource limits

Một vòng lặp không kết thúc có thể chiếm CPU:

~~~text
while true {
    doWork();
}
~~~

Runtime có thể dùng instruction budget, deadline hoặc cancellation token để dừng chương trình. Giới hạn cần được kiểm tra thường xuyên trong vòng lặp và các lời gọi hàm.

### 15.2. Cô lập

Nếu một chương trình DSL không đáng tin cậy có thể chạy mã host tùy ý, giới hạn trong interpreter không còn đủ. Khi cần chạy extension hoặc mã tùy ý, nên dùng process/container isolation và chính sách hệ điều hành phù hợp.

Một DSL chỉ cung cấp biểu thức và hàm tích hợp có allowlist sẽ dễ kiểm soát hơn nhiều so với việc cho phép truy cập toàn bộ runtime của ngôn ngữ chủ.

## 16. Hiệu năng và tối ưu hóa

Hiệu năng thông dịch phụ thuộc vào kích thước AST, số lần thực thi, chi phí tra cứu biến, lời gọi hàm và tương tác với hệ thống bên ngoài.

Một số tối ưu hóa phổ biến:

- **Parse cache:** lưu AST theo source hash và phiên bản grammar.
- **Compiled-plan cache:** lưu bytecode hoặc execution plan theo chương trình và cấu hình tương thích.
- **Constant folding:** tính trước biểu thức chỉ chứa hằng số.
- **Inline hoặc specialize:** tối ưu một số lời gọi hoặc kiểu thường dùng.
- **Index symbol:** dùng symbol ID thay vì tra cứu chuỗi tên ở mỗi lần đánh giá.
- **Reuse runtime structures:** tái sử dụng cấu trúc bất biến giữa các lần chạy.

Ví dụ:

~~~text
let minimum = 100 * 10;
when order.total > minimum {
    approve();
}
~~~

Nếu 100 và 10 là hằng số, compiler hoặc interpreter có thể tính trước minimum thành 1000. Việc tối ưu cần bảo toàn ngữ nghĩa, bao gồm kiểu số, overflow và quy tắc làm tròn.

Không nên cache kết quả của một biểu thức phụ thuộc dữ liệu hoặc trạng thái thay đổi nếu không có key và invalidation policy chính xác. Cache AST thường an toàn hơn cache kết quả runtime.

## 17. Debugging, tracing và quan sát thực thi

Interpreter nên cung cấp thông tin để hiểu chương trình đã chạy như thế nào:

- Breakpoint tại rule hoặc câu lệnh.
- Step into, step over và step out nếu runtime hỗ trợ.
- Xem giá trị biến trong scope hiện tại.
- Theo dõi call stack.
- Trace các rule đã được đánh giá và kết quả điều kiện.
- Đo thời gian của từng bước.
- Correlate execution với request hoặc workflow.

Ví dụ trace:

~~~text
Execution: exec-42
Rule: large-order
Condition: order.total > 10000000
Result: true
Action: requireManualReview(order.id)
Status: completed
~~~

Trace giúp người vận hành hiểu tại sao một rule kích hoạt. Cần kiểm soát mức chi tiết để tránh ghi quá nhiều dữ liệu, làm chậm runtime hoặc lộ thông tin nhạy cảm.

## 18. Đóng gói và triển khai interpreter

Interpreter có thể được triển khai theo nhiều mô hình:

### 18.1. Embedded interpreter

Interpreter chạy bên trong ứng dụng chủ dưới dạng thư viện. Ứng dụng cung cấp dữ liệu và hàm tích hợp qua API.

Phù hợp khi:

- DSL cần truy cập dữ liệu của ứng dụng.
- Số lượng chương trình thực thi được kiểm soát.
- Cần độ trễ thấp và tích hợp trực tiếp.

Rủi ro chính là mã DSL chạy cùng process với ứng dụng, nên phải giới hạn API và tài nguyên.

### 18.2. Interpreter service

Interpreter chạy như một dịch vụ riêng. Ứng dụng gửi chương trình hoặc định danh chương trình cùng dữ liệu đầu vào qua API.

Ưu điểm:

- Có thể scale và quản lý runtime độc lập.
- Dễ cô lập tiến trình.
- Có thể áp dụng quota, authentication và audit ở ranh giới dịch vụ.

Đánh đổi:

- Tăng độ trễ mạng.
- Cần version API và schema dữ liệu.
- Phải xử lý timeout, retry và lỗi dịch vụ.

### 18.3. Offline validation và runtime execution

Một mô hình khác là kiểm tra chương trình trước khi publish, sau đó runtime chỉ thực thi artifact đã được xác nhận. Cách này giúp phát hiện lỗi sớm và giảm chi phí parse khi chạy.

Artifact cần gắn với phiên bản DSL, schema, function registry và runtime tương thích. Nếu các thành phần này thay đổi, hệ thống cần kiểm tra lại hoặc biên dịch lại artifact.

## 19. Kiểm thử interpreter

Interpreter cần được kiểm thử theo từng tầng và theo hành vi quan sát được.

### 19.1. Unit test cho biểu thức

Kiểm tra literal, toán tử, so sánh, truy cập thuộc tính, lời gọi hàm và short-circuit. Mỗi test xác nhận giá trị và kiểu runtime mong đợi.

### 19.2. Test câu lệnh và luồng điều khiển

Kiểm tra if/else, vòng lặp, return, break, continue và các block lồng nhau.

### 19.3. Test scope và closure

Kiểm tra lexical scope, shadowing, biến capture và vòng đời của môi trường.

### 19.4. Test tích hợp binding

Xác nhận hàm host nhận đúng đối số, chuyển đổi kiểu đúng, lỗi được ánh xạ chính xác và capability được kiểm soát.

### 19.5. Test giới hạn và hủy

Chạy chương trình lặp vô hạn, đệ quy sâu hoặc tạo dữ liệu lớn để xác nhận budget, deadline và cancellation hoạt động.

### 19.6. Test tính xác định và hồi quy

Với chương trình không có side effect hoặc dependency biến động, chạy nhiều lần cùng đầu vào và xác nhận kết quả giống nhau. Lưu các chương trình DSL đại diện làm test hồi quy khi thay đổi interpreter.

## 20. Quy trình thực thi một chương trình DSL

Một quy trình thực tế có thể được mô tả như sau:

1. **Nhận chương trình.** Xác định source, phiên bản DSL và nguồn cung cấp.
2. **Parse.** Tạo AST và báo lỗi từ vựng hoặc cú pháp nếu có.
3. **Validate.** Kiểm tra tên, kiểu, cấu trúc và ràng buộc tĩnh.
4. **Resolve dependencies.** Liên kết module, hàm, kiểu và phiên bản thư viện.
5. **Authorize.** Xác nhận chương trình được phép dùng capability cần thiết.
6. **Prepare runtime context.** Cung cấp input, biến, clock, cấu hình và budget.
7. **Execute.** Duyệt AST hoặc chạy bytecode, ghi nhận trace và side effect.
8. **Handle result.** Trả kết quả, diagnostic hoặc execution status.
9. **Audit and cleanup.** Ghi nhận hành động cần thiết và giải phóng tài nguyên.

Với chương trình được chạy nhiều lần, có thể tách parse/validate khỏi execute và cache artifact bất biến. Tuy nhiên, mỗi lần chạy vẫn cần context, quyền và dữ liệu đầu vào riêng.

## 21. Những lỗi thiết kế thường gặp

### Thực thi trực tiếp từ chuỗi nguồn

Nếu mỗi lần chạy đều tìm kiếm chuỗi và thực hiện thao tác ngay, logic phân tích, kiểm tra và thực thi bị trộn lẫn. Hãy tạo AST hoặc biểu diễn trung gian để có ranh giới rõ ràng.

### Cho phép truy cập tùy ý API của host

Điều này khiến DSL có thể vượt khỏi miền nghiệp vụ và gây rủi ro bảo mật. Dùng function registry, capability và allowlist.

### Không có giới hạn tài nguyên

Vòng lặp vô hạn, đệ quy sâu hoặc dữ liệu lớn có thể làm cạn CPU và bộ nhớ. Áp dụng budget, deadline và cancellation.

### Không định nghĩa thứ tự đánh giá

Biểu thức có side effect có thể cho kết quả khác nếu thứ tự không rõ. Hãy quy định thứ tự toán hạng, đối số và short-circuit.

### Không ánh xạ lỗi về mã nguồn

Lỗi trong AST hoặc bytecode khó sửa nếu không biết vị trí DSL ban đầu. Giữ source span và source map xuyên suốt pipeline.

### Cache sai phạm vi

Cache kết quả phụ thuộc user, tenant hoặc dữ liệu thay đổi có thể trả về kết quả cũ hoặc rò rỉ dữ liệu giữa người dùng. Phân biệt cache parse artifact với cache kết quả thực thi.

### Không quản lý side effect

Nếu một action cập nhật hệ thống rồi lần chạy thất bại, trạng thái có thể không nhất quán. Xác định transaction, idempotency và retry policy tại ranh giới tích hợp.

### Trộn lỗi chương trình với lỗi hạ tầng

Một lỗi kiểu hoặc thiếu hàm khác với timeout của dịch vụ ngoài. Phân loại lỗi giúp retry và thông báo cho người dùng đúng cách.

## 22. Kết luận

Thông dịch DSL là quá trình phân tích một chương trình chuyên biệt và thực hiện ý nghĩa của nó trong runtime. Interpreter có thể duyệt trực tiếp AST, chạy bytecode trên virtual machine hoặc kết hợp nhiều cách tiếp cận. Dù chọn kiến trúc nào, hệ thống cần có mô hình giá trị, môi trường biến, quy tắc đánh giá biểu thức, cơ chế gọi hàm và cách xử lý lỗi rõ ràng.

Một interpreter dùng trong ứng dụng thực tế còn phải quản lý scope, closure, side effect, tính xác định, giới hạn tài nguyên, capability và khả năng quan sát thực thi. Các ranh giới giữa DSL và ứng dụng chủ nên được thể hiện bằng binding hoặc function registry có hợp đồng ổn định.

Khi xây dựng interpreter, hãy bắt đầu từ ngữ nghĩa cần hỗ trợ, chọn kiến trúc đơn giản đáp ứng được yêu cầu, giữ liên kết từ runtime về vị trí nguồn và bổ sung giới hạn an toàn ngay trong thiết kế. Điều đó giúp DSL có thể thực thi nhất quán, dễ debug và kiểm soát được khi được dùng trong hệ thống lớn.
