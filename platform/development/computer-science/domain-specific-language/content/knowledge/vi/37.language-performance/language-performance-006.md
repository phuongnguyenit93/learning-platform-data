# Tối ưu mã sinh trong DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vì sao hiệu năng của chương trình được sinh ra là một phần quan trọng trong thiết kế DSL.
- Mô tả pipeline từ source DSL qua AST, semantic analysis, intermediate representation (IR), optimization passes đến code generation.
- Phân biệt tối ưu ở cấp DSL, IR, compiler backend và runtime.
- Giữ nguyên semantics của chương trình khi áp dụng các phép biến đổi tối ưu.
- Áp dụng constant folding, constant propagation, dead-code elimination, common subexpression elimination và strength reduction.
- Hiểu inlining, specialization, loop optimization, allocation reduction, boxing elimination và data layout.
- Cân bằng tốc độ thực thi, kích thước mã, thời gian biên dịch, bộ nhớ và khả năng debug.
- Đo hiệu năng bằng benchmark có kiểm soát và đọc kết quả profiling.
- Thiết kế optimization pass có điều kiện, có thể bật tắt và kiểm chứng được.
- Xây dựng chiến lược tối ưu mã sinh cho nhiều target như JVM, native code, JavaScript hoặc SQL.

## 1. Tối ưu mã sinh là gì?

DSL (Domain Specific Language) cho phép người dùng mô tả một tác vụ trong ngôn ngữ phù hợp với miền nghiệp vụ. Compiler hoặc interpreter của DSL chuyển mô tả đó thành chương trình có thể thực thi. Mã đầu ra có thể là Java, Kotlin, C, bytecode JVM, JavaScript, SQL, query plan hoặc một dạng instruction riêng.

Tối ưu mã sinh (generated-code optimization) là quá trình cải thiện chương trình hoặc biểu diễn được tạo ra để đạt mục tiêu như:

- Thực thi nhanh hơn.
- Dùng ít CPU hoặc bộ nhớ hơn.
- Giảm số lần cấp phát object.
- Giảm số lời gọi hàm hoặc dispatch động.
- Tạo mã nhỏ hơn và tải nhanh hơn.
- Tăng throughput hoặc giảm latency.
- Giảm chi phí tương tác với database, network hoặc runtime.
- Giữ khả năng debug, quan sát và bảo trì.

Ví dụ, một DSL biểu diễn biểu thức tính giá:

~~~text
price = (unitPrice * quantity) + 0
~~~

Mã sinh trực tiếp có thể là:

~~~java
int price = (unitPrice * quantity) + 0;
~~~

Sau tối ưu, compiler có thể bỏ phép cộng với 0:

~~~java
int price = unitPrice * quantity;
~~~

Biến đổi này có vẻ đơn giản, nhưng compiler chỉ được thực hiện nếu nó bảo toàn kiểu dữ liệu, overflow behavior, exception behavior và semantics của phép toán trong DSL.

Tối ưu mã sinh không đơn thuần là làm cho code trông ngắn hơn. Một đoạn mã ít dòng hơn chưa chắc chạy nhanh hơn; một đoạn code có nhiều phép tính nhìn thấy được có thể được JIT compiler tối ưu tốt hơn một đoạn code phức tạp. Mục tiêu phải được đo trên target runtime thực tế.

## 2. Pipeline tạo mã và vị trí của tối ưu hóa

Một pipeline DSL phổ biến có thể gồm các bước:

~~~text
DSL Source
    |
    v
Lexer / Parser
    |
    v
AST
    |
    v
Name Resolution
    |
    v
Type Checking
    |
    v
Semantic Analysis
    |
    v
Intermediate Representation
    |
    v
Optimization Passes
    |
    v
Target Lowering
    |
    v
Code Generation
    |
    v
Generated Program / Bytecode / Query
    |
    v
Runtime
~~~

### 2.1. Lexer và parser

Lexer nhận diện token; parser xây dựng AST. Thông thường đây chưa phải nơi thực hiện tối ưu runtime, nhưng parser có thể chuẩn hóa cú pháp hoặc xây node phù hợp để các pass sau dễ xử lý.

### 2.2. AST

AST phản ánh cấu trúc cú pháp và ý nghĩa gần với source DSL. Một số tối ưu đơn giản có thể được thực hiện trực tiếp trên AST, nhưng tối ưu sâu thường cần biểu diễn có thông tin kiểu, control flow và data flow.

### 2.3. Semantic analysis

Compiler xác định tên, kiểu, phạm vi biến, overload, quyền truy cập và các quy tắc ngữ nghĩa. Thông tin này rất quan trọng vì không thể tối ưu đúng nếu compiler không biết chính xác một phép toán có thể gây side effect hoặc ném exception hay không.

### 2.4. Intermediate representation

IR là biểu diễn trung gian giữa DSL và target. IR có thể là tree, graph, control-flow graph, SSA form hoặc một dạng instruction riêng.

Một IR tốt giúp tách semantics của DSL khỏi chi tiết của từng target. Compiler có thể tối ưu một lần rồi sinh code cho nhiều backend.

### 2.5. Optimization passes

Mỗi pass thực hiện một nhóm biến đổi có mục tiêu rõ. Ví dụ constant folding, dead-code elimination, inlining hoặc loop optimization.

### 2.6. Lowering và code generation

Lowering chuyển các khái niệm cấp cao thành thao tác mà target hỗ trợ. Code generator chọn instruction, API runtime, calling convention và cách biểu diễn dữ liệu.

### 2.7. Runtime optimization

Một số tối ưu được thực hiện lúc chạy, ví dụ JIT compilation, inline cache, profile-guided optimization hoặc adaptive specialization. Compiler DSL cần tránh cản trở những cơ chế này bằng cách sinh mã khó phân tích hoặc quá động.

## 3. Các tầng tối ưu

Có nhiều nơi có thể cải thiện hiệu năng, và mỗi tầng có thông tin khác nhau.

| Tầng | Ví dụ | Lợi ích chính |
|---|---|---|
| DSL source | Rút gọn expression, chọn operation phù hợp | Mã nguồn dễ hiểu, tránh công việc thừa |
| AST | Loại node dư, chuẩn hóa biểu thức | Giảm độ phức tạp trước semantic lowering |
| IR | Constant folding, DCE, CSE | Tối ưu độc lập target |
| Target backend | Instruction selection, register allocation | Tận dụng kiến trúc và runtime |
| Runtime | JIT, inline cache, adaptive optimization | Dựa trên hành vi thực tế |
| Data access | Batch, pushdown, projection | Giảm I/O và truyền dữ liệu |

### 3.1. Tối ưu ở tầng cao

Tầng DSL hiểu ý nghĩa nghiệp vụ. Ví dụ một biểu thức tổng hợp có thể được chuyển thành một phép aggregate thay vì sinh vòng lặp xử lý từng phần tử. Tầng cao có thể nhìn thấy cơ hội mà backend không hiểu.

### 3.2. Tối ưu ở tầng thấp

Backend hiểu target architecture và có thể chọn instruction phù hợp, bố trí register hoặc tận dụng intrinsic. Nó không nhất thiết hiểu ý nghĩa nghiệp vụ của DSL.

### 3.3. Tránh tối ưu trùng lặp

Một số phép biến đổi có thể do nhiều tầng thực hiện. Nên xác định pass nào sở hữu biến đổi để tránh tăng thời gian compile hoặc làm mất thông tin có ích cho pass sau.

## 4. Bảo toàn semantics

Mọi tối ưu hợp lệ phải giữ hành vi mà DSL cam kết. Hai chương trình có thể tính cùng kết quả với dữ liệu thông thường nhưng khác nhau ở overflow, null, exception, side effect hoặc thứ tự đánh giá.

### 4.1. Quan sát được của chương trình

Semantics cần bảo toàn có thể gồm:
- Giá trị trả về.
- Thay đổi trạng thái.
- Thứ tự side effect.
- Exception được ném.
- Thời điểm hoặc số lần gọi external operation.
- Thứ tự phát event.
- Quyền truy cập và kiểm tra bảo mật.
- Quy tắc null và missing value.

### 4.2. Ví dụ phép cộng với 0

Với số nguyên toán học, x + 0 = x. Nhưng nếu DSL dùng một kiểu số đặc biệt có operator overload, phép cộng có thể ghi log hoặc có side effect. Nếu phép toán có thể ném exception, compiler cũng cần biết điều đó trước khi bỏ node.

### 4.3. Thứ tự đánh giá

Giả sử DSL có biểu thức:

~~~text
checkA() and checkB()
~~~

Nếu AND có short-circuit, checkB chỉ chạy khi checkA đúng. Compiler không được đổi thứ tự hoặc đánh giá cả hai nếu điều đó làm thay đổi side effect hoặc exception.

### 4.4. Số thực và precision

Phép toán số thực không luôn có tính kết hợp do rounding:

\[
(a+b)+c \ne a+(b+c)
\]

Vì vậy, reassociation có thể làm kết quả khác đi. Chỉ áp dụng khi DSL cho phép relaxed floating-point semantics hoặc chứng minh biến đổi an toàn.

### 4.5. Null và three-valued logic

Nếu DSL có logic TRUE, FALSE và UNKNOWN, các phép biến đổi Boolean phải giữ semantics đó. Ví dụ, việc đẩy NOT qua biểu thức hoặc thay phép so sánh có thể làm thay đổi kết quả khi một operand là null.

### 4.6. Integer overflow

Một DSL có thể định nghĩa overflow là wraparound, exception hoặc checked arithmetic. Constant folding và strength reduction phải tuân theo cùng quy tắc.

### 4.7. Purity và side effect

Compiler cần biết function nào thuần (pure), function nào có side effect. Một biểu thức thuần có thể được tính trước hoặc dùng lại; một function gửi email không được tự ý xóa hoặc chạy thêm.

## 5. Constant folding

Constant folding tính trước biểu thức chỉ phụ thuộc vào hằng số.

Ví dụ:

~~~text
limit = 60 * 60
timeout = limit + 5
~~~

IR trước tối ưu:

~~~text
t1 = multiply 60, 60
t2 = add t1, 5
timeout = t2
~~~

IR sau tối ưu:

~~~text
timeout = 3605
~~~

### 5.1. Điều kiện áp dụng

Một biểu thức có thể constant-fold nếu:
- Mọi operand đều là compile-time constant.
- Phép toán được xác định trong DSL.
- Không có side effect.
- Không phụ thuộc locale, timezone hoặc môi trường runtime.
- Không tạo exception khác với semantics được yêu cầu.

### 5.2. Constant folding với kiểu dữ liệu

Compiler phải xử lý đúng:
- Integer width.
- Signed và unsigned.
- Decimal scale.
- Floating-point rounding.
- String encoding.
- Date/time zone.
- Enum và bit flags.

### 5.3. Compile-time error và runtime error

Nếu biểu thức hằng chắc chắn chia cho 0, DSL có thể báo lỗi lúc compile hoặc giữ lỗi ở runtime theo language semantics. Quyết định phải nhất quán và được mô tả.

### 5.4. Tránh đánh giá constant không an toàn

Một hàm tưởng như hằng có thể phụ thuộc vào thời gian, random seed, environment variable hoặc locale. Không nên gọi nó trong compiler chỉ vì đối số là literal.

## 6. Constant propagation

Constant propagation truyền giá trị hằng đã biết đến các vị trí sử dụng.

Trước:

~~~text
let taxRate = 0.1
let subtotal = 1000
let tax = subtotal * taxRate
let total = subtotal + tax
~~~

Sau propagation và folding:

~~~text
let tax = 100
let total = 1100
~~~

### 6.1. Data-flow analysis

Compiler theo dõi giá trị của biến qua control flow. Nếu mọi đường đi đến một điểm đều gán cùng một hằng, giá trị đó có thể được thay bằng hằng.

### 6.2. Merge tại nhánh

~~~text
if condition:
    x = 10
else:
    x = 10

use(x)
~~~

Tại điểm hợp nhất, x vẫn là 10.

Nếu nhánh đầu gán 10 và nhánh sau gán 20, compiler không thể coi x là một hằng duy nhất.

### 6.3. SSA form

Static Single Assignment (SSA) biểu diễn mỗi biến bằng một định nghĩa duy nhất. Khi control flow hợp nhất, phi node chọn giá trị đến từ nhánh tương ứng. Điều này làm constant propagation và các phân tích data-flow dễ triển khai hơn.

### 6.4. Scope và closure

Biến captured bởi closure hoặc có thể bị sửa qua alias cần được phân tích cẩn thận. Compiler không thể thay một biến bằng hằng nếu một tham chiếu khác có thể thay đổi nó.

## 7. Dead-code elimination

Dead-code elimination (DCE) loại bỏ phép tính hoặc nhánh không ảnh hưởng đến kết quả quan sát được.

Ví dụ:

~~~text
let temporary = calculateSomething()
let answer = 42
return answer
~~~

Nếu calculateSomething thuần và không ném exception, temporary không được sử dụng và phép tính có thể bị loại bỏ.

### 7.1. Dead assignment

Một giá trị bị ghi đè trước khi được đọc có thể được bỏ:

~~~text
x = 10
x = 20
print(x)
~~~

Lệnh gán x = 10 là dead store nếu không có quan sát trung gian.

### 7.2. Unreachable code

~~~text
return result
log("unreachable")
~~~

Nếu return kết thúc block, lời gọi log sau đó không thể chạy và có thể được loại bỏ.

### 7.3. Side-effect analysis

Không thể loại bỏ function call chỉ vì kết quả không được dùng nếu function có side effect, ghi log, cập nhật state, gửi event hoặc có thể ném exception quan sát được.

### 7.4. Dead branch

Nếu condition là compile-time constant, compiler có thể giữ lại nhánh có thể chạy và loại nhánh còn lại, với điều kiện đánh giá condition không có side effect.

### 7.5. Dead store elimination

Compiler có thể loại store vào biến hoặc vùng nhớ nếu giá trị không được đọc trước khi bị ghi đè. Phân tích alias là yếu tố quan trọng khi có pointer hoặc reference.

## 8. Common subexpression elimination

Common subexpression elimination (CSE) phát hiện biểu thức giống nhau được tính nhiều lần và dùng chung kết quả.

Trước:

~~~text
a = customer.age * customer.age
b = customer.age * customer.age + 10
~~~

Sau:

~~~text
ageSquared = customer.age * customer.age
a = ageSquared
b = ageSquared + 10
~~~

### 8.1. Điều kiện dùng lại

CSE an toàn khi:
- Operand có cùng giá trị.
- Biểu thức có semantics giống nhau.
- Không có side effect.
- Không có thao tác ghi làm thay đổi operand giữa hai lần tính.
- Kết quả không phụ thuộc trạng thái bên ngoài.

### 8.2. Global value numbering

Global value numbering (GVN) gán định danh cho các biểu thức tương đương trong control-flow graph. Nó có thể phát hiện biểu thức trùng ngay cả khi chúng nằm ở block khác nhau nhưng cùng giá trị đầu vào.

### 8.3. Alias và mutable state

Nếu customer.age có thể thay đổi giữa hai lần đọc hoặc getter có side effect, compiler không thể mặc định hai lần đọc giống nhau.

### 8.4. Chi phí của việc lưu kết quả

CSE giảm phép tính nhưng có thể làm tăng thời gian sống của biến và tăng register pressure. Trên một số target, tính lại một biểu thức nhỏ có thể rẻ hơn giữ nhiều giá trị trong register.

## 9. Strength reduction

Strength reduction thay một phép toán tương đối đắt bằng phép toán rẻ hơn khi có thể chứng minh tương đương.

Ví dụ, trong vòng lặp:

~~~text
for i from 0 to n:
    address = base + i * 8
    use(address)
~~~

Có thể chuyển thành dạng tăng dần:

~~~text
address = base
for i from 0 to n:
    use(address)
    address = address + 8
~~~

### 9.1. Các phép biến đổi thường gặp

- Nhân với lũy thừa của hai thành shift nếu semantics kiểu số cho phép.
- Tính địa chỉ tăng dần thay vì nhân index mỗi vòng.
- Thay phép modulo có điều kiện phù hợp bằng bit mask.
- Tái sử dụng giá trị loop invariant.

### 9.2. Không phải lúc nào shift cũng nhanh hơn

Compiler backend thường đã biết cách chọn instruction tốt. Tự thay phép nhân bằng shift ở tầng DSL có thể làm code khó đọc hoặc cản trở tối ưu backend.

### 9.3. Overflow và signedness

Biến đổi với shift, multiply và modulo phải xét signed integer, width và overflow. Không được giả định số học vô hạn.

## 10. Inlining

Inlining thay lời gọi hàm bằng phần thân của hàm tại vị trí gọi.

Trước:

~~~text
function double(x):
    return x * 2

result = double(value)
~~~

Sau inlining:

~~~text
result = value * 2
~~~

### 10.1. Lợi ích

Inlining có thể:
- Loại call overhead.
- Mở ra cơ hội constant propagation.
- Giúp DCE loại nhánh không cần thiết.
- Tạo cơ hội specialization.
- Giúp compiler phân tích control flow xuyên qua lời gọi.

### 10.2. Chi phí

Inlining quá nhiều làm:
- Tăng code size.
- Tăng thời gian compile.
- Tăng instruction cache pressure.
- Làm stack trace và debug khó hơn.
- Tăng register pressure.

### 10.3. Heuristic

Compiler có thể cân nhắc:
- Kích thước function.
- Số lượng call site.
- Tần suất gọi nếu có profile.
- Khả năng constant argument.
- Độ sâu inlining.
- Code size budget.

### 10.4. Recursive function

Inlining đệ quy cần giới hạn độ sâu hoặc áp dụng một chiến lược riêng. Nếu không, code size có thể tăng không kiểm soát.

### 10.5. Dynamic dispatch

Inlining virtual call cần biết target có thể được xác định an toàn hay không. Devirtualization có thể biến dispatch động thành call trực tiếp nếu compiler chứng minh chỉ có một implementation khả thi trong ngữ cảnh.

## 11. Function specialization và partial evaluation

Specialization tạo phiên bản chuyên biệt của function cho một kiểu hoặc một số đối số đã biết.

Ví dụ:

~~~text
function format(value, locale):
    ...
~~~

Nếu locale là hằng số "vi-VN" tại call site, compiler có thể tạo phiên bản chuyên biệt:

~~~text
format_vi(value):
    ...
~~~

### 11.1. Type specialization

Generic function có thể được chuyên biệt theo kiểu dữ liệu để tránh boxing hoặc dynamic dispatch.

### 11.2. Value specialization

Compiler có thể chuyên biệt theo một số giá trị hằng, ví dụ fixed precision, mode hoặc algorithm option.

### 11.3. Partial evaluation

Partial evaluation thực hiện trước phần tính toán phụ thuộc vào input đã biết ở compile time, để runtime chỉ làm phần còn lại.

### 11.4. Code explosion

Quá nhiều tổ hợp type hoặc constant có thể tạo hàng trăm phiên bản function. Compiler cần giới hạn specialization count và có fallback generic implementation.

### 11.5. Cache specialization

Compiler có thể cache phiên bản đã sinh theo specialization key. Key cần chứa đủ thông tin để không tái sử dụng code sai kiểu hoặc sai semantics.

## 12. Loop optimization

Vòng lặp thường là phần tiêu tốn nhiều CPU, đặc biệt khi xử lý collection lớn.

### 12.1. Loop-invariant code motion

Di chuyển phép tính không đổi qua các vòng ra ngoài loop.

Trước:

~~~text
for item in items:
    threshold = config.limit * 2
    if item.score > threshold:
        process(item)
~~~

Sau:

~~~text
threshold = config.limit * 2
for item in items:
    if item.score > threshold:
        process(item)
~~~

Chỉ hợp lệ nếu config.limit không thay đổi trong vòng lặp và phép tính không có side effect.

### 12.2. Loop unrolling

Unrolling mở rộng thân vòng lặp để giảm branch overhead:

~~~text
for i from 0 to n step 4:
    process(i)
    process(i + 1)
    process(i + 2)
    process(i + 3)
~~~

Cần xử lý phần tử còn dư và kiểm tra giới hạn mảng.

### 12.3. Loop fusion

Hai vòng lặp cùng duyệt collection có thể được gộp nếu semantics cho phép:

~~~text
for item in items:
    calculateA(item)

for item in items:
    calculateB(item)
~~~

Sau fusion:

~~~text
for item in items:
    calculateA(item)
    calculateB(item)
~~~

Fusion giảm số lần duyệt và cải thiện locality, nhưng có thể thay đổi thứ tự side effect giữa hai pass.

### 12.4. Loop interchange

Đổi thứ tự các vòng lặp lồng nhau để cải thiện locality của bộ nhớ. Tác dụng phụ thuộc data layout và thứ tự truy cập.

### 12.5. Vectorization

Vectorization xử lý nhiều phần tử trong một instruction vector thay vì từng phần tử. Điều kiện phụ thuộc alignment, kiểu dữ liệu, dependency giữa iteration và khả năng vector instruction của target.

### 12.6. Auto-vectorization

Compiler có thể tự nhận diện vòng lặp phù hợp. Code sinh cần thể hiện dữ liệu liên tục, ít alias và control flow đơn giản để backend có cơ hội vectorize.

### 12.7. Parallel loop

Một loop có thể được chia thành nhiều task. Nhưng song song hóa đòi hỏi xác định race condition, reduction, thứ tự side effect, cancellation và giới hạn concurrency. Không phải loop nào cũng an toàn để parallelize.

## 13. Allocation reduction và object lifetime

Việc tạo nhiều object ngắn hạn có thể gây áp lực lên garbage collector hoặc allocator.

### 13.1. Temporary object

Ví dụ, DSL có thể sinh nhiều object trung gian khi nối chuỗi hoặc biến đổi collection. Có thể tối ưu bằng builder, buffer tái sử dụng hoặc biểu diễn lazy nếu semantics cho phép.

### 13.2. Escape analysis

Escape analysis xác định object có thoát khỏi phạm vi tạo ra nó hay không. Nếu object không escape, runtime hoặc compiler có thể:
- Scalar replacement.
- Stack allocation nếu target hỗ trợ.
- Loại bỏ allocation hoàn toàn.
- Giữ các field thành local value.

### 13.3. Scalar replacement

Một object nhỏ có thể được thay bằng các scalar field riêng lẻ nếu identity của object không được quan sát.

### 13.4. Object pooling

Pooling tái sử dụng object nhưng không phải lúc nào cũng tốt. Pool có thể gây contention, giữ bộ nhớ lâu và tạo bug do trạng thái cũ. Chỉ dùng khi profiling cho thấy allocation là bottleneck.

### 13.5. Buffer reuse

Với parser hoặc serializer, tái sử dụng buffer có thể giảm allocation. Cần xác định ownership và lifetime để không dùng lại buffer khi consumer vẫn còn tham chiếu.

### 13.6. Lazy evaluation

Lazy collection có thể tránh tạo collection trung gian. Nhưng nó có thể làm tăng chi phí mỗi phần tử, giữ reference lâu hoặc khiến computation chạy nhiều lần nếu không cache.

## 14. Boxing, unboxing và representation của kiểu

Boxing bọc primitive value thành object. Unboxing lấy primitive từ object.

Ví dụ trên JVM, một DSL có thể sinh:

~~~java
Integer total = Integer.valueOf(0);
total = total + Integer.valueOf(item.quantity());
~~~

Mỗi thao tác có thể cần unboxing và boxing tùy context.

### 14.1. Primitive specialization

Nếu kiểu DSL là integer, backend có thể dùng int hoặc long thay vì wrapper object khi không cần null hoặc object identity.

### 14.2. Generic collection

Một collection generic có thể buộc primitive được boxing. Có thể dùng primitive collection hoặc specialization nếu target và API cho phép.

### 14.3. Nullability

Nếu DSL cho phép null, primitive target không thể trực tiếp biểu diễn null. Backend có thể dùng wrapper, tagged representation hoặc nullable primitive encoding.

### 14.4. Boxing trong hot loop

Boxing lặp lại trong loop có thể tạo nhiều allocation và giảm hiệu năng. Profiling giúp xác định trường hợp cần tối ưu.

### 14.5. Không hy sinh semantics

Nếu DSL cho phép quan sát object identity, wrapper caching hoặc null, chuyển sang primitive có thể làm thay đổi hành vi. Cần chứng minh tương đương.

## 15. Data layout và locality

Cách dữ liệu được bố trí trong bộ nhớ ảnh hưởng đến cache locality và throughput.

### 15.1. Array of Structures (AoS)

Mỗi phần tử chứa nhiều field:

~~~text
Customer[] {
    {age, score, active},
    {age, score, active},
    ...
}
~~~

Phù hợp khi xử lý toàn bộ field của một record.

### 15.2. Structure of Arrays (SoA)

Mỗi field có một array riêng:

~~~text
ages[]
scores[]
activeFlags[]
~~~

Phù hợp khi xử lý một field trên nhiều phần tử và có thể hỗ trợ vectorization tốt hơn.

### 15.3. DSL và data-oriented code generation

DSL xử lý analytics, simulation hoặc query có thể sinh SoA hoặc columnar representation. DSL hướng object model có thể phù hợp với AoS.

### 15.4. Cache locality

Truy cập dữ liệu liên tục thường tận dụng cache tốt hơn truy cập pointer rời rạc. Code generator có thể chọn layout hoặc traversal order phù hợp với workload.

### 15.5. Alignment và padding

Native backend cần cân nhắc alignment, field padding và ABI. Layout không tương thích có thể gây lỗi khi gọi thư viện native hoặc đọc binary data.

### 15.6. Không đổi layout tùy tiện

Layout có thể là một phần của serialization, reflection, FFI hoặc public ABI. Chỉ tối ưu layout nội bộ khi không làm phá vỡ contract.

## 16. Tối ưu dispatch và lời gọi hàm

Dynamic dispatch linh hoạt nhưng có thể tốn chi phí và cản trở inlining.

### 16.1. Devirtualization

Nếu compiler chứng minh call target duy nhất, có thể chuyển virtual call thành direct call.

### 16.2. Inline cache

Runtime có thể ghi nhớ target gần đây tại một call site. Nếu kiểu receiver ổn định, dispatch có thể nhanh hơn.

### 16.3. Monomorphic và polymorphic call site

Call site monomorphic thường gặp một kiểu target; polymorphic gặp nhiều kiểu. Compiler có thể tối ưu trường hợp monomorphic và giữ fallback cho trường hợp khác.

### 16.4. Dispatch table

Một DSL có nhiều action hoặc rule có thể sinh dispatch table thay cho chuỗi if/else dài. Lựa chọn phụ thuộc số lượng case, tính ổn định và branch prediction.

### 16.5. Branch prediction

Thứ tự điều kiện có thể ảnh hưởng branch prediction, nhưng thay đổi thứ tự chỉ hợp lệ nếu không làm đổi semantics và có dữ liệu profile hỗ trợ. Không nên đoán điều kiện nào phổ biến chỉ từ source.

## 17. Tối ưu string, serialization và collection

DSL thường sinh code chuyển đổi dữ liệu. Các thao tác này có thể tạo nhiều allocation và copy.

### 17.1. String concatenation

Nối chuỗi lặp trong loop có thể tạo nhiều string tạm. Backend có thể dùng StringBuilder hoặc một cơ chế buffer phù hợp.

### 17.2. Serialization

Tối ưu serializer có thể gồm:
- Sinh code đọc field trực tiếp.
- Tránh reflection ở hot path.
- Tái sử dụng buffer.
- Dùng streaming thay vì tạo toàn bộ document.
- Tránh chuyển đổi kiểu nhiều lần.
- Cache metadata schema.

### 17.3. Collection pipeline

Các phép map, filter và reduce có thể tạo collection trung gian. Fusion có thể kết hợp chúng thành một traversal:

~~~text
items
  .filter(isActive)
  .map(calculateValue)
  .sum()
~~~

Có thể sinh một loop duy nhất nếu semantics của lazy/eager evaluation và exception order được giữ.

### 17.4. Pre-size collection

Nếu biết số phần tử dự kiến, compiler có thể sinh collection với capacity phù hợp để giảm resize và copy.

### 17.5. Batch operation

Nếu DSL gọi service hoặc database cho từng phần tử, code generator có thể gom thành batch nếu API và transaction semantics cho phép.

## 18. Tối ưu truy vấn và pushdown

Với DSL truy vấn dữ liệu, tối ưu mã sinh có thể gồm chuyển phép tính xuống database hoặc engine xử lý dữ liệu.

### 18.1. Predicate pushdown

Thay vì tải mọi record rồi lọc trong ứng dụng, compiler đẩy điều kiện WHERE xuống database.

### 18.2. Projection pushdown

Chỉ lấy các cột cần dùng thay vì SELECT toàn bộ. Điều này giảm I/O, network transfer và memory.

### 18.3. Aggregation pushdown

Có thể chuyển SUM, COUNT hoặc GROUP BY xuống hệ thống dữ liệu nếu semantics tương thích.

### 18.4. Join strategy

Backend có thể chọn hash join, merge join hoặc nested-loop join dựa trên statistics và capability của target. DSL compiler có thể truyền metadata để query optimizer quyết định.

### 18.5. Không phải expression nào cũng pushdown được

Function tùy chỉnh, timezone semantics, collation hoặc kiểu dữ liệu đặc biệt có thể không tương thích với database. Khi đó cần giữ computation ở application layer hoặc dùng mapping tương đương đã kiểm chứng.

### 18.6. Parameterization

Sinh query có parameter thay vì nối chuỗi literal giúp an toàn và hỗ trợ plan cache. Tối ưu không được làm mất cơ chế parameter binding.

## 19. Code size, compile time và runtime trade-off

Tối ưu thường đánh đổi giữa nhiều mục tiêu.

| Mục tiêu | Tác động có thể xảy ra |
|---|---|
| Inlining mạnh | Runtime nhanh hơn nhưng code lớn hơn |
| Specialization nhiều | Ít dispatch hơn nhưng tăng compile time và code size |
| Unrolling | Giảm loop overhead nhưng tăng instruction count |
| CSE | Giảm phép tính nhưng tăng register lifetime |
| Debug instrumentation | Dễ debug hơn nhưng tăng runtime overhead |
| Aggressive constant folding | Runtime ít việc hơn nhưng compile time có thể tăng |
| Generated helper reuse | Code nhỏ hơn nhưng thêm call overhead |

### 19.1. Code bloat

Code bloat làm tăng binary size, class loading, instruction cache miss và thời gian triển khai. Tối ưu nên có code-size budget.

### 19.2. Compile-time budget

Một DSL được compile trong CI hoặc lúc khởi động cần thời gian compile hợp lý. Pass quá tốn kém có thể làm chậm developer feedback hoặc startup.

### 19.3. Cold start và steady state

Một chương trình có thể chạy nhanh sau JIT warmup nhưng khởi động chậm. Cần đo cả cold start và steady-state nếu cả hai quan trọng.

### 19.4. Memory footprint

Tối ưu runtime có thể giữ cache, specialized code hoặc object lâu hơn. Đánh giá heap, native memory và metaspace, không chỉ CPU.

### 19.5. Target-specific optimization

Không nên giả định một tối ưu có lợi trên mọi target. JVM, native CPU, JavaScript engine và database optimizer có đặc điểm khác nhau.

## 20. Profile-guided optimization

Profile-guided optimization (PGO) dùng dữ liệu thực thi để hướng dẫn compiler.

### 20.1. Thu thập profile

Có thể thu:
- Tần suất gọi function.
- Tỷ lệ nhánh.
- Kiểu receiver tại call site.
- Hot loop.
- Allocation site.
- Branch miss.
- Cache miss.
- Function latency.

### 20.2. Dùng profile

Compiler có thể:
- Inline function hot.
- Devirtualize call site có kiểu ổn định.
- Đặt hot path gần nhau.
- Chọn branch layout.
- Specialize function.
- Giữ cold path riêng.

### 20.3. Profile phải đại diện

Profile từ một workload không đại diện có thể làm tối ưu sai cho workload khác. Cần thu dữ liệu từ nhiều nhóm input và kiểm tra tính ổn định.

### 20.4. Profile drift

Hành vi production thay đổi theo thời gian. PGO cần quy trình cập nhật và kiểm soát phiên bản profile.

### 20.5. Không để dữ liệu profile quyết định semantics

Profile chỉ hướng dẫn lựa chọn implementation. Nó không được thay đổi kết quả, thứ tự side effect hoặc quy tắc nghiệp vụ.

## 21. Kiến trúc optimization pass

Compiler nên chia tối ưu thành các pass nhỏ, có input/output và invariant rõ ràng.

### 21.1. Pass manager

Pass manager điều phối thứ tự pass, dependency, analysis result và invalidation.

Ví dụ pipeline:

~~~text
Build Typed IR
    |
    v
Normalize Expressions
    |
    v
Constant Folding
    |
    v
Constant Propagation
    |
    v
Simplify Control Flow
    |
    v
Dead Code Elimination
    |
    v
Common Subexpression Elimination
    |
    v
Loop Optimizations
    |
    v
Inlining / Specialization
    |
    v
Target Lowering
    |
    v
Backend Optimization
~~~

Thứ tự thực tế phụ thuộc compiler. Một pass có thể tạo cơ hội cho pass khác, nên có thể cần chạy lại một số pass đến fixed point hoặc theo giới hạn vòng lặp.

### 21.2. Pass độc lập

Mỗi pass nên:
- Có mục tiêu cụ thể.
- Xác định IR version hoặc invariant cần có.
- Giữ source location hoặc debug metadata.
- Không sửa input nếu dùng immutable IR.
- Trả diagnostics khi không thể tối ưu.
- Có thể bật/tắt trong cấu hình compiler.

### 21.3. Analysis pass

Một số pass chỉ tính thông tin:
- Control-flow graph.
- Dominator tree.
- Alias analysis.
- Liveness.
- Type facts.
- Loop structure.
- Call graph.

Các pass tối ưu có thể dùng lại analysis result. Nếu một pass thay đổi IR, nó phải thông báo analysis nào không còn hợp lệ.

### 21.4. Fixed-point iteration

Constant propagation và simplification có thể tạo cơ hội lặp lại. Compiler có thể chạy đến khi không còn thay đổi hoặc đạt iteration limit để tránh compile vô hạn.

### 21.5. Pass ordering

DCE chạy sau constant folding thường loại được nhánh vừa trở thành unreachable. Inlining có thể mở ra constant propagation mới. Pass manager cần sắp thứ tự theo các dependency này.

## 22. IR và SSA cho tối ưu

IR cần thể hiện rõ data dependency và control flow.

Ví dụ SSA:

~~~text
entry:
    a1 = load inputA
    b1 = const 10
    c1 = add a1, b1
    branch condition, thenBlock, elseBlock

thenBlock:
    x1 = const 20
    jump merge

elseBlock:
    x2 = const 20
    jump merge

merge:
    x3 = phi(x1, x2)
    return x3
~~~

Ở merge, compiler biết cả hai nhánh đều tạo 20 nên có thể thay phi bằng constant 20.

### 22.1. SSA lợi ích

SSA giúp:
- Mỗi giá trị có một definition.
- Dễ phân tích data-flow.
- Phát hiện constant.
- Xác định use-def chain.
- Thực hiện DCE và CSE.
- Phân tích liveness.

### 22.2. Memory SSA và alias

Khi có load/store, compiler cần biểu diễn dependency bộ nhớ. Nếu không biết hai địa chỉ có alias hay không, nó phải bảo thủ và tránh biến đổi có thể sai.

### 22.3. Source mapping

IR nên giữ source span để lỗi compile, debugger và profiler có thể liên kết code sinh với vị trí DSL gốc.

## 23. Debuggability và observability của mã sinh

Tối ưu có thể làm code sinh khó đọc hơn. DSL compiler cần cân bằng hiệu năng và khả năng chẩn đoán.

### 23.1. Source map

Source map ánh xạ đoạn code sinh về source DSL. Khi runtime exception xảy ra, người dùng có thể thấy tên operation hoặc dòng DSL thay vì chỉ thấy một method nội bộ.

### 23.2. Debug mode

Compiler có thể hỗ trợ chế độ debug:
- Ít inlining.
- Giữ tên biến.
- Thêm source location.
- Tắt một số tối ưu khó debug.
- Sinh metadata cho profiler.

Debug mode nên giữ semantics, dù performance có thể thấp hơn.

### 23.3. Optimization remarks

Compiler có thể giải thích:
- Pass nào đã thay đổi code.
- Vì sao một call được inline.
- Vì sao loop không được vectorize.
- Vì sao một expression không constant-fold được.
- Vì sao một function không được specialize.

### 23.4. Generated source output

Cho phép xuất code sinh hoặc IR ở chế độ diagnostic giúp developer kiểm tra compiler. Không nhất thiết phải xuất code sinh trong production.

### 23.5. Không xóa metadata quá sớm

Source location, type information và debug metadata có thể cần cho pass sau hoặc toolchain. Chỉ loại bỏ khi không còn cần và không phá khả năng debug được cam kết.

## 24. Đo hiệu năng và benchmark

Tối ưu phải được chứng minh bằng phép đo.

### 24.1. Chọn metric

Tùy mục tiêu, có thể đo:
- Throughput: số operation mỗi giây.
- Latency: thời gian cho một operation.
- p50, p95, p99 latency.
- CPU time.
- Allocation rate.
- Peak memory.
- Generated code size.
- Compile time.
- Startup time.
- Database query count hoặc bytes transferred.

### 24.2. Microbenchmark và macrobenchmark

Microbenchmark đo một đoạn nhỏ như function hoặc loop. Macrobenchmark đo workload gần với ứng dụng thật. Cả hai đều cần thiết vì tối ưu cục bộ có thể không cải thiện toàn hệ thống.

### 24.3. Warmup

JIT runtime cần warmup để profile và compile hot method. Đo ngay lần chạy đầu có thể không phản ánh steady state.

### 24.4. Nhiễu đo

Kết quả có thể bị ảnh hưởng bởi CPU frequency scaling, background task, garbage collection, JIT compilation, filesystem cache và network. Chạy nhiều lần và báo median hoặc percentile.

### 24.5. Baseline

Lưu baseline trước tối ưu. So sánh cùng input, cùng runtime, cùng hardware và cùng cấu hình. Không so sánh số đo từ môi trường khác nhau mà không ghi rõ.

### 24.6. Statistical significance

Một cải thiện nhỏ có thể chỉ là nhiễu. Dùng nhiều sample, confidence interval hoặc phương pháp thống kê phù hợp.

### 24.7. Benchmark không thay thế profiling

Benchmark nói rằng chương trình nhanh hay chậm. Profiler giúp giải thích thời gian nằm ở đâu và nguyên nhân là gì.

## 25. Profiling và tìm bottleneck

Profiling quan sát hành vi runtime để tìm phần tốn tài nguyên.

### 25.1. CPU profiling

CPU sampling cho biết function hoặc call stack nào chiếm nhiều CPU. Nếu thời gian tập trung ở generated evaluator, có thể cần tối ưu dispatch hoặc expression evaluation.

### 25.2. Allocation profiling

Allocation profiler cho biết object nào được tạo nhiều. Nếu DSL sinh collection trung gian, string hoặc boxed primitive, đây là nơi cần xem xét.

### 25.3. Memory profiling

Heap dump hoặc allocation timeline giúp phát hiện retained object, cache không giới hạn hoặc closure giữ reference lớn.

### 25.4. I/O profiling

Nếu generated code gọi database hoặc network, CPU profiling có thể không cho thấy bottleneck chính. Cần đo query latency, số request, payload size và connection wait.

### 25.5. Flame graph

Flame graph biểu diễn call stack theo lượng sample. Một khối rộng thường cho thấy phần code chiếm nhiều CPU. Cần đọc theo stack context, không chỉ nhìn tên function lớn.

### 25.6. Profiling generated code

Generated symbol nên có tên hoặc metadata có thể liên kết về DSL node. Nếu mọi function đều tên generic, việc xác định operation gây bottleneck sẽ khó.

## 26. Kiểm tra hiệu quả từng optimization pass

Mỗi pass nên được đánh giá bằng cả tính đúng đắn và tác động hiệu năng.

### 26.1. Correctness test

So sánh kết quả của chương trình trước và sau tối ưu trên nhiều input. Kiểm tra exception, side effect và edge case theo semantics.

### 26.2. IR test

Có thể viết test cho IR đầu vào và IR đầu ra mong đợi. Test giúp xác nhận pass thực hiện đúng phép biến đổi.

### 26.3. Differential testing

Chạy cùng chương trình trên interpreter tham chiếu và generated code rồi so sánh kết quả. Cần chuẩn hóa nondeterminism và external effect.

### 26.4. Property-based testing

Sinh nhiều input theo property như constant expression, integer boundary, null và nested branch. Điều này giúp tìm lỗi ở các trường hợp biên.

### 26.5. Performance regression test

Chọn benchmark đại diện và theo dõi xu hướng. Performance test cần ngưỡng phù hợp để tránh báo lỗi do nhiễu nhỏ.

### 26.6. Compile-time regression

Một pass có thể tăng runtime speed nhưng làm compile time tăng rất lớn. Cần đo cả hai và chọn trade-off phù hợp.

## 27. Tối ưu theo target backend

Một DSL có thể sinh code cho nhiều nền tảng. Mỗi backend có đặc tính riêng.

### 27.1. JVM

Backend JVM cần cân nhắc:
- Primitive và boxed type.
- Object allocation và garbage collection.
- Method size và JIT inlining limit.
- Class loading và startup.
- Escape analysis.
- Dynamic dispatch và inline cache.

Code Java dễ đọc không nhất thiết là bytecode tối ưu nhất. Nên kiểm tra bytecode và profile runtime.

### 27.2. Native code

Native backend cần quan tâm:
- Register allocation.
- Instruction selection.
- Calling convention.
- SIMD.
- Cache locality.
- ABI và data alignment.
- Link-time optimization.

### 27.3. JavaScript

JavaScript backend cần tránh:
- Thay đổi object shape liên tục.
- Megamorphic property access.
- Allocation dư thừa.
- Deoptimization do kiểu dữ liệu không ổn định.
- Bundle quá lớn làm tăng tải trang.

### 27.4. SQL

SQL backend cần:
- Predicate và projection pushdown.
- Parameterization.
- Join order.
- Index usage.
- Query plan stability.
- Tránh N+1 query.
- Giảm round trip.

### 27.5. Backend capability

Compiler nên mô tả capability của target, ví dụ vectorization, tail call, native decimal hoặc transaction. Pass chỉ được dùng capability nếu backend hỗ trợ.

### 27.6. Không nhúng giả định target vào semantics DSL

Ngữ nghĩa DSL nên ổn định giữa target. Backend có thể chọn implementation khác nhau nhưng phải giữ kết quả và side effect đã cam kết.

## 28. Cấu hình optimization level

Một compiler có thể cung cấp các mức tối ưu:

| Mức | Mục tiêu | Ví dụ |
|---|---|---|
| O0 | Debug, compile nhanh | Tối thiểu biến đổi |
| O1 | Tối ưu an toàn, chi phí thấp | Constant folding, DCE |
| O2 | Tối ưu cân bằng | CSE, inlining có giới hạn, loop optimization |
| O3 | Tối ưu mạnh | Specialization, vectorization, PGO |
| Os | Giảm kích thước | Inlining hạn chế, code deduplication |
| Oz | Ưu tiên binary nhỏ | Loại bỏ code và giảm helper |
| Custom | Theo workload | Bật/tắt từng pass |

Đây là cách đặt tên minh họa. DSL có thể dùng profile như debug, balanced, throughput hoặc low-latency.

### 28.1. Optimization level không thay semantics

O0 và O3 phải cho kết quả tương đương theo language contract. Khác biệt chỉ nằm ở cách triển khai và hiệu năng.

### 28.2. Per-operation configuration

Một số DSL cho phép annotation ở function hoặc operation để yêu cầu no-inline, inline hint hoặc specialization. Annotation cần được giới hạn để người dùng không phá vỡ runtime.

### 28.3. Feature flag

Pass mới có thể được bật theo feature flag để thử nghiệm trên workload nhỏ, so sánh và rollback nếu có regression.

### 28.4. Reproducible build

Cùng source, compiler version, flags và target nên tạo artifact có thể tái hiện theo mức deterministic mà toolchain cam kết. Profile data và environment cần được ghi lại nếu ảnh hưởng code generation.

## 29. Tối ưu mã sinh trong DSL biểu thức và quy tắc

Một DSL biểu thức thường sinh evaluator để tính điều kiện hoặc giá trị.

Ví dụ:

~~~text
rule "eligible_customer" {
    when customer.active
      and customer.age >= 18
      and customer.balance > 0
    then approve(customer)
}
~~~

### 29.1. Compile expression thành evaluator

Compiler có thể sinh function chuyên biệt thay vì interpreter duyệt từng node AST ở runtime. Điều này giảm dispatch và boxing nhưng tăng compile cost.

### 29.2. Short-circuit

Điều kiện AND có thể dừng ngay khi một operand false. Compiler có thể sinh branch code thay vì tính tất cả biểu thức, nếu semantics quy định short-circuit.

### 29.3. Cache compiled rule

Nếu cùng rule được dùng nhiều lần, cache generated evaluator theo rule version và compiler configuration. Cache key cần chứa đủ thông tin để tránh dùng code cũ sau khi rule thay đổi.

### 29.4. Specialize theo schema

Nếu schema của customer đã biết, compiler có thể sinh truy cập field trực tiếp thay vì lookup theo tên ở runtime. Khi schema thay đổi, cache hoặc compiled artifact cần được invalidated.

### 29.5. Không tối ưu sai thứ tự luật

Nếu DSL quy định rule order hoặc side effect, compiler không được reorder rule chỉ để giảm branch. Cần semantics về independence và priority trước khi đổi thứ tự.

## 30. Tối ưu code sinh cho workflow

Workflow DSL thường có nhiều step, branch, retry và handler.

### 30.1. State machine generation

Một workflow có thể được sinh thành state machine thay vì chuỗi callback lồng nhau. State machine giúp quản lý transition rõ và có thể giảm allocation của closure.

### 30.2. Eliminate empty transition

Transition không có action và không mang metadata có thể được gộp nếu không ảnh hưởng tracing, audit hoặc breakpoint.

### 30.3. Inline local transition

Một transition nội bộ nhỏ có thể được inline vào state machine. Tuy nhiên, giữ boundary đôi khi cần thiết cho observability và checkpoint.

### 30.4. Hoist invariant

Expression dùng trong nhiều step và không thay đổi có thể được tính một lần, nếu không phụ thuộc thời gian hoặc external state.

### 30.5. Async state

Với workflow bất đồng bộ, code generator cần tránh block thread khi chờ I/O. Continuation hoặc coroutine state có thể được sinh để resume khi event đến.

### 30.6. Không xóa checkpoint boundary

Một boundary có thể có ý nghĩa durability. Gộp step vượt qua checkpoint có thể làm mất khả năng resume sau crash.

## 31. Tối ưu code sinh cho truy vấn dữ liệu

DSL truy vấn thường có cơ hội tối ưu lớn vì compiler có thể biến đổi toàn bộ query plan.

### 31.1. Projection pruning

Loại cột không được sử dụng trong phần còn lại của query.

### 31.2. Predicate simplification

Rút gọn điều kiện logic dựa trên type và constant, nhưng phải giữ null semantics.

### 31.3. Join elimination

Một join có thể bị loại nếu không dùng field từ bảng liên quan và constraint chứng minh join không làm thay đổi số dòng. Không thể loại chỉ vì không chọn cột của bảng đó; join có thể lọc hoặc nhân bản row.

### 31.4. Common subquery elimination

Một subquery giống nhau có thể được tính một lần nếu deterministic và không phụ thuộc trạng thái thay đổi.

### 31.5. Plan caching

Query có cùng cấu trúc nhưng khác parameter có thể dùng prepared statement hoặc plan cache. Parameterization giúp giảm compile overhead và tránh injection.

### 31.6. Explain output

DSL nên có cách xem query plan hoặc generated SQL để developer hiểu vì sao optimizer chọn một chiến lược.

## 32. Các giới hạn và rủi ro

### 32.1. Undefined behavior

Nếu DSL không định nghĩa rõ overflow, evaluation order hoặc aliasing, optimizer khó biết biến đổi nào an toàn. Language specification cần xác định semantics.

### 32.2. Nondeterminism

Random, current time, concurrent state và external calls có thể làm kết quả thay đổi. Compiler không được constant-fold hoặc reorder chúng như expression thuần.

### 32.3. Reflection và dynamic feature

Reflection, dynamic property lookup hoặc runtime code loading có thể che giấu call target và làm giảm cơ hội tối ưu. Có thể cung cấp annotation hoặc schema để compiler có thêm thông tin.

### 32.4. Debugging và stack trace

Inlining và code fusion có thể làm stack trace khác source structure. Source map và debug metadata cần được duy trì.

### 32.5. Security checks

Compiler không được loại bỏ authorization check hoặc validation chỉ vì một nhánh có vẻ dư nếu check đó là security boundary hoặc có side effect được quan sát.

### 32.6. Compile resource exhaustion

Input DSL lớn hoặc biểu thức lồng sâu có thể khiến optimizer tiêu tốn quá nhiều CPU/memory. Cần giới hạn độ sâu, số pass, số specialization và thời gian compile.

### 32.7. Optimization bug

Một pass sai có thể tạo lỗi khó tái hiện. Compiler cần differential test, IR verifier và cơ chế tắt pass để chẩn đoán.

## 33. Quy trình tối ưu có căn cứ

Một quy trình hiệu quả:

1. Xác định mục tiêu: latency, throughput, memory, code size hay compile time.
2. Chọn workload và input đại diện.
3. Đo baseline trước khi thay đổi.
4. Dùng profiler xác định bottleneck.
5. Kiểm tra generated code hoặc IR tại vị trí nóng.
6. Xác định biến đổi có thể áp dụng và semantics cần bảo toàn.
7. Triển khai một pass nhỏ với invariant rõ.
8. Chạy correctness và differential tests.
9. Đo lại cùng workload và môi trường.
10. Kiểm tra code size, allocation, compile time và memory.
11. Lưu optimization remark và benchmark result.
12. Bật rollout có kiểm soát và theo dõi regression.
13. Giữ khả năng rollback hoặc tắt pass.

Không nên tối ưu dựa trên cảm giác rằng một đoạn code trông phức tạp. Hãy bắt đầu từ dữ liệu đo được.

## 34. Ví dụ tổng hợp: DSL tính giá đơn hàng

Giả sử DSL mô tả:

~~~text
function calculateTotal(order):
    let unitPrice = order.product.price
    let quantity = order.quantity
    let taxRate = 0.1
    let subtotal = unitPrice * quantity
    let tax = subtotal * taxRate
    let unusedLabel = "order-total"
    let fee = 0
    return subtotal + tax + fee
~~~

### 34.1. Source-level facts

Compiler biết taxRate là hằng, fee là 0, unusedLabel không được dùng. Nếu các biểu thức thuần và không có side effect, có thể đơn giản hóa.

### 34.2. Sau constant propagation và DCE

~~~text
function calculateTotal(order):
    let unitPrice = order.product.price
    let quantity = order.quantity
    let subtotal = unitPrice * quantity
    let tax = subtotal * 0.1
    return subtotal + tax
~~~

### 34.3. Sau lowering

Một backend JVM có thể sinh code dùng primitive decimal representation hoặc gọi Decimal API tùy semantics tiền tệ. Một native backend có thể chọn decimal library hoặc fixed-point integer nếu precision và rounding rules cho phép.

### 34.4. Specialization

Nếu compiler biết currency và scale tại compile time, nó có thể sinh function chuyên biệt cho scale đó, miễn là không thay đổi rounding rule hoặc overflow behavior.

### 34.5. Profiling

Nếu profiling cho thấy thời gian chủ yếu nằm trong Decimal multiplication, việc loại một biến tạm không đem lại nhiều lợi ích. Cần đo đúng hot operation trước khi thay đổi representation.

### 34.6. Kiểm tra tính đúng

So sánh kết quả với interpreter tham chiếu cho:
- Giá trị bằng 0.
- Số lượng lớn.
- Giá trị sát giới hạn.
- Giá trị có nhiều chữ số thập phân.
- Currency có scale khác nhau.
- Null hoặc thiếu giá nếu DSL cho phép.

## 35. Bài tập tự kiểm tra

### Bài 1: Pipeline

Vẽ pipeline từ DSL source đến generated code và chỉ ra vị trí phù hợp cho type checking, IR optimization và target lowering.

### Bài 2: Semantics

Một expression gọi function có side effect nhưng kết quả không được dùng. Hãy giải thích vì sao DCE không được loại function call đó.

### Bài 3: Constant folding

Rút gọn biểu thức hằng có phép cộng, nhân và chia. Nêu các điều kiện cần kiểm tra về kiểu số, overflow và exception.

### Bài 4: Constant propagation

Một biến được gán cùng một hằng ở cả hai nhánh if/else. Hãy mô tả cách compiler có thể thay các lần đọc biến bằng hằng.

### Bài 5: CSE

Hai expression giống nhau xuất hiện trong một function. Hãy nêu điều kiện để dùng chung kết quả và một tình huống alias khiến CSE không an toàn.

### Bài 6: Inlining

Một function nhỏ được gọi ở hàng nghìn call site. Phân tích lợi ích và nguy cơ code bloat khi inline tất cả call site.

### Bài 7: Loop optimization

Một vòng lặp tính một giá trị không đổi ở mỗi iteration. Hãy áp dụng loop-invariant code motion và nêu điều kiện bảo toàn semantics.

### Bài 8: Allocation

Một DSL sinh nhiều object tạm trong pipeline map/filter. Hãy so sánh collection fusion, lazy evaluation và object pooling.

### Bài 9: Target backend

Một optimization pass cải thiện JVM nhưng làm JavaScript chậm hơn. Hãy đề xuất cách tổ chức target capability và backend-specific pass.

### Bài 10: Benchmark

Thiết kế benchmark để so sánh generated code trước và sau optimization. Nêu baseline, warmup, metric, profiling và cách giảm nhiễu.

## Kết luận

Tối ưu mã sinh giúp chương trình được tạo từ DSL sử dụng tài nguyên hiệu quả hơn, nhưng mọi biến đổi phải bảo toàn semantics mà ngôn ngữ cam kết. Một pipeline có IR rõ ràng và optimization pass độc lập giúp compiler áp dụng constant folding, propagation, dead-code elimination, CSE, inlining, specialization, loop optimization và giảm allocation một cách có kiểm soát. Hiệu quả phụ thuộc target backend, data layout, runtime và workload thực tế; vì vậy cần benchmark, profiling, correctness test và theo dõi compile-time, code size cùng memory. Khi compiler giữ source mapping, optimization remarks và khả năng bật tắt pass, người dùng có thể hiểu chương trình được sinh ra, điều tra regression và tiếp tục cải thiện hiệu năng dựa trên bằng chứng.
