# Đánh đổi giữa biên dịch và thông dịch

## 1. Hai cách thực thi trong DSL

Khi thiết kế một ngôn ngữ chuyên biệt miền (*Domain-Specific Language — DSL*), nhóm phát triển phải chọn cách chuyển chương trình nguồn thành hành vi thực thi. Hai chiến lược truyền thống là **biên dịch (*compilation*)** và **thông dịch (*interpretation*)**.

- **Biên dịch:** một compiler phân tích chương trình nguồn, kiểm tra các quy tắc cần thiết rồi chuyển chương trình thành một dạng đích, chẳng hạn mã máy, bytecode, mã trung gian hoặc mã của một ngôn ngữ khác. Dạng đích sau đó được thực thi bởi phần cứng, máy ảo hoặc runtime tương ứng.
- **Thông dịch:** một interpreter đọc cấu trúc chương trình và trực tiếp điều khiển việc đánh giá biểu thức, câu lệnh hoặc thao tác của DSL trong môi trường chạy.

Hai cách này là hai đầu của một phổ thiết kế. Nhiều hệ thống thực tế kết hợp chúng: parser tạo AST, compiler chuyển AST thành bytecode, rồi virtual machine thông dịch bytecode; hoặc runtime biên dịch các đoạn mã thường dùng sang mã máy bằng JIT (*Just-in-Time compilation*).

Ví dụ, cùng một DSL quy tắc:

~~~text
rule "large-order" {
    when order.total >= 1000000
    then applyDiscount(order, 0.05)
}
~~~

Một interpreter có thể duyệt AST, đánh giá điều kiện rồi gọi hàm thực thi tương ứng. Một compiler có thể chuyển rule thành bytecode hoặc mã máy, sau đó runtime chạy kết quả đã biên dịch.

Mục tiêu của bài toán không phải tìm một cách luôn tốt hơn cách còn lại. Cần chọn kiến trúc phù hợp với quy mô chương trình, số lần chạy, môi trường triển khai, yêu cầu phản hồi lỗi, tính linh hoạt và rủi ro vận hành của DSL.

## 2. Pipeline biên dịch và thông dịch

### 2.1. Pipeline của compiler

Một compiler điển hình có các bước:

~~~text
DSL source
    |
    v
Lexer
    |
    v
Parser
    |
    v
AST / semantic model
    |
    v
Semantic analysis
    |
    v
Intermediate representation (IR)
    |
    v
Optimization
    |
    v
Code generation
    |
    v
Machine code / bytecode / target source
    |
    v
Execution
~~~

Tùy hệ thống, một số bước có thể được gộp hoặc lặp lại. Ví dụ compiler có thể sinh bytecode cho VM thay vì mã máy trực tiếp. Một compiler-to-source có thể sinh Java, JavaScript hoặc SQL rồi giao việc thực thi cho nền tảng đích.

### 2.2. Pipeline của interpreter

Một interpreter truyền thống thường có pipeline:

~~~text
DSL source
    |
    v
Lexer
    |
    v
Parser
    |
    v
AST / semantic model
    |
    v
Interpreter
    |
    v
Evaluation environment
    |
    v
Result / side effects
~~~

Interpreter vẫn cần lexer, parser và thường cần semantic analysis. Khác biệt chính nằm ở bước thực thi: thay vì tạo một chương trình đích độc lập, interpreter duyệt cấu trúc chương trình và thực hiện hành vi tương ứng.

Một interpreter có thể phân tích source mỗi lần chạy hoặc lưu AST đã parse để chạy nhiều lần. Vì vậy, không nên đồng nhất “thông dịch” với việc đọc từng ký tự và thực hiện ngay lập tức.

### 2.3. Pipeline lai

Một DSL có thể dùng bytecode VM:

~~~text
DSL source
    |
    v
Lexer / Parser / Semantic analysis
    |
    v
Bytecode compiler
    |
    v
Bytecode
    |
    v
Virtual machine
    |
    +----> Interpreter for bytecode
    |
    +----> JIT compiler for hot code
                 |
                 v
             Native code
~~~

Cách này giữ được tính linh hoạt của runtime và có thể đạt hiệu năng cao khi các đoạn mã được thực thi thường xuyên. Đổi lại, hệ thống cần quản lý bytecode format, VM, profiling, cache và nhiều lớp chẩn đoán.

## 3. So sánh tổng quan

| Tiêu chí | Biên dịch | Thông dịch |
|---|---|---|
| Thời điểm chuyển đổi | Trước khi chạy hoặc khi build/deploy | Trong lúc chạy hoặc ngay trước khi đánh giá |
| Kết quả trung gian | Mã máy, bytecode, IR hoặc mã đích | AST, semantic model hoặc instruction được interpreter xử lý |
| Thời gian khởi động | Có thể thấp nếu artifact đã sẵn sàng; build có thể tốn thời gian | Có thể nhanh với script nhỏ, nhưng parse/analysis lúc chạy làm tăng startup |
| Hiệu năng lặp lại | Thường tốt khi mã đích được tối ưu | Có thể thấp hơn do dispatch và kiểm tra lúc chạy |
| Tối ưu hóa | Có thể tối ưu toàn chương trình hoặc theo module | Có thể tối ưu động, nhưng phụ thuộc interpreter/JIT |
| Phản hồi lỗi | Có thể phát hiện nhiều lỗi trước khi chạy | Có thể phát hiện lỗi khi đường thực thi đi qua |
| Tính linh hoạt | Thay đổi thường cần biên dịch lại artifact | Có thể nạp hoặc thay rule trong runtime |
| Triển khai | Có thể cần artifact riêng cho nền tảng đích | Cần interpreter/runtime tương thích |
| Debug source | Cần source map hoặc metadata | AST/source location thường gần với source hơn |
| Bảo mật | Artifact có thể khó đọc hơn nhưng vẫn cần sandbox và kiểm tra | Runtime có thể kiểm soát capability tập trung; source dễ kiểm tra hơn |
| Phụ thuộc nền tảng | Mã máy thường phụ thuộc kiến trúc; bytecode phụ thuộc VM | Phụ thuộc interpreter và runtime |
| Phù hợp | Chương trình ổn định, chạy nhiều, yêu cầu throughput cao | Rule thay đổi thường xuyên, tác vụ ngắn, cần tương tác và kiểm soát động |

Các xu hướng trong bảng không phải bảo đảm tuyệt đối. Một interpreter có JIT tốt có thể nhanh hơn một compiler đơn giản; một compiler có thể tạo bytecode portable; một interpreter có thể cache AST và không parse lại mỗi lần chạy. Phải đo trên workload thật.

## 4. Đánh đổi về hiệu năng

### 4.1. Chi phí thực thi

Interpreter thường phải thực hiện một vòng dispatch cho mỗi node hoặc instruction. Ví dụ, khi đánh giá biểu thức:

~~~text
total = subtotal + tax
~~~

Interpreter có thể:
1. Đọc node Add.
2. Gọi hàm đánh giá toán hạng trái.
3. Gọi hàm đánh giá toán hạng phải.
4. Kiểm tra kiểu và thực hiện phép cộng.
5. Gán kết quả vào môi trường.

Nếu biểu thức được chạy hàng triệu lần, chi phí dispatch, lookup biến và kiểm tra động có thể đáng kể.

Compiler có thể chuyển biểu thức thành instruction hoặc mã máy gần với phép tính đích. Nhiều bước điều phối đã được xử lý trước. Compiler cũng có thể inline hàm, loại bỏ phép tính dư hoặc tối ưu truy cập dữ liệu nếu ngữ nghĩa cho phép.

### 4.2. Chi phí biên dịch

Biên dịch có chi phí trước khi chạy:
- Phân tích và kiểm tra chương trình.
- Xây dựng IR.
- Tối ưu hóa.
- Sinh mã đích.
- Lưu hoặc tải artifact.

Với một rule chỉ chạy một lần, thời gian biên dịch có thể lớn hơn thời gian thực thi tiết kiệm được. Với một chương trình chạy hàng triệu lần, chi phí biên dịch ban đầu có thể được phân bổ trên nhiều lần chạy.

### 4.3. Break-even point

Có thể mô hình hóa tổng thời gian theo số lần chạy N:

~~~text
T_interpreter(N) = T_parse + N * T_eval

T_compiler(N) = T_parse + T_compile + N * T_native
~~~

Trong đó:
- T_parse là chi phí parse và phân tích dùng chung.
- T_compile là chi phí biên dịch bổ sung.
- T_eval là chi phí mỗi lần chạy qua interpreter.
- T_native là chi phí mỗi lần chạy artifact đã biên dịch.

Nếu T_eval lớn hơn T_native, số lần chạy hòa vốn xấp xỉ:

~~~text
N_break_even = T_compile / (T_eval - T_native)
~~~

Đây là mô hình đơn giản. Nó chưa tính cache, JIT warm-up, garbage collection, I/O, thời gian tải runtime và chi phí tối ưu. Tuy vậy, nó giúp đặt câu hỏi đúng: chương trình sẽ chạy bao nhiêu lần và chi phí biên dịch có được bù lại không?

### 4.4. Throughput và latency

Hai hệ thống có thể có mục tiêu hiệu năng khác nhau:

- **Throughput:** số lượng rule hoặc giao dịch xử lý được trong một đơn vị thời gian.
- **Latency:** thời gian phản hồi cho một lần đánh giá.

Compiler thường có lợi thế throughput khi artifact được chạy lặp lại. Interpreter đơn giản có thể có latency tốt cho một script rất nhỏ vì không cần build artifact riêng. JIT có thể cải thiện throughput sau warm-up nhưng làm latency ban đầu tăng.

Nếu DSL dùng cho API cần phản hồi ổn định trong vài mili giây, thời gian khởi động và độ biến thiên latency có thể quan trọng hơn benchmark throughput trung bình.

### 4.5. Memory footprint

Compiler có thể tạo artifact lớn, IR, metadata debug và cache mã máy. Interpreter cần AST, environment, runtime và có thể lưu nhiều object node. JIT có thể giữ cả bytecode lẫn mã native.

Không thể kết luận cách nào luôn dùng ít bộ nhớ hơn. Cần đo:
- Kích thước source và AST.
- Kích thước bytecode hoặc native artifact.
- Bộ nhớ cache.
- Số chương trình đồng thời.
- Bộ nhớ tạm trong compile/optimization.
- Chi phí runtime dùng chung.

## 5. Đánh đổi về thời gian khởi động và vòng đời chương trình

### 5.1. Chạy một lần

Với script nhỏ chạy một lần, interpreter có thể phù hợp vì tránh bước build riêng. Tuy nhiên, interpreter vẫn cần parse source và có thể thực hiện semantic analysis trước khi đánh giá.

Nếu compiler hỗ trợ compile nhanh hoặc artifact đã được build trước, khác biệt startup có thể rất nhỏ.

### 5.2. Chạy lặp lại

Với rule hoặc workflow được gọi liên tục, biên dịch một lần rồi tái sử dụng artifact có thể giảm chi phí mỗi lần chạy.

Ví dụ, một pricing rule được đánh giá cho hàng nghìn đơn hàng mỗi phút. Việc compile rule khi cấu hình thay đổi, sau đó thực thi artifact cho từng đơn, có thể phù hợp hơn parse và interpret lại liên tục.

### 5.3. Nạp nóng và cập nhật rule

Interpreter có thể dễ dàng nạp AST mới khi người quản trị cập nhật rule. Nhưng compiler cũng có thể hỗ trợ hot reload:
1. Nhận source mới.
2. Compile ở background.
3. Kiểm tra artifact.
4. Atomically chuyển phiên bản rule đang hoạt động.
5. Giữ phiên bản cũ cho các request đã bắt đầu.

Vấn đề không chỉ là compiler hay interpreter. Nó còn liên quan đến transaction, versioning, cache invalidation và cách xử lý các lần chạy đang diễn ra.

### 5.4. Cold start và warm start

Serverless hoặc môi trường scale-to-zero nhạy cảm với cold start. Interpreter cần nạp runtime và có thể parse source; compiler cần tải artifact, VM hoặc native library. Nếu JIT được dùng, thời gian warm-up có thể ảnh hưởng request đầu tiên.

Nên đo riêng:
- Cold start.
- Warm start.
- Thời gian compile.
- Thời gian nạp artifact.
- Thời gian đánh giá lần đầu.
- Thời gian sau khi cache/JIT đã ổn định.

## 6. Đánh đổi về phát hiện lỗi và diagnostics

### 6.1. Lỗi phát hiện trước khi chạy

Compiler thường có thể thực hiện nhiều kiểm tra trước execution:
- Name resolution.
- Type checking.
- Kiểm tra overload.
- Kiểm tra cấu trúc và ràng buộc.
- Kiểm tra một số điều kiện không thể thực hiện.

Điều này giúp người dùng nhận lỗi sớm. Tuy nhiên, chỉ những lỗi có thể xác định tĩnh mới được phát hiện; lỗi phụ thuộc dữ liệu runtime vẫn có thể xuất hiện khi chạy.

### 6.2. Lỗi phát hiện khi chạy

Interpreter có thể kiểm tra điều kiện khi đánh giá node. Ví dụ, nếu một nhánh không được thực hiện thì lỗi trong biểu thức của nhánh đó có thể không xuất hiện trong lần chạy hiện tại.

Đây là hành vi có thể mong muốn với DSL động, nhưng có thể khiến lỗi chỉ xuất hiện khi một dữ liệu hoặc đường thực thi hiếm gặp được sử dụng.

### 6.3. Static checking và dynamic checking

Biên dịch không đồng nghĩa mọi lỗi đều được phát hiện tĩnh; thông dịch cũng không đồng nghĩa không có static checking.

Một interpreter vẫn có thể parse, resolve symbol, kiểm tra kiểu và validate constraint trước khi chạy. Một compiler có thể tạo mã và để nhiều kiểm tra kiểu hoặc null safety diễn ra ở runtime.

Cần tách hai quyết định:
- DSL có những quy tắc nào được kiểm tra tĩnh?
- Runtime thực thi theo chiến lược biên dịch hay thông dịch?

### 6.4. Source mapping

Compiler thường chuyển source thành IR hoặc mã đích, nên diagnostics và stack trace cần source map:
- IR instruction tương ứng với đoạn source nào.
- Mã native tương ứng với node DSL nào.
- Inline function hoặc tối ưu hóa đã thay đổi vị trí ra sao.

Interpreter thường giữ liên hệ trực tiếp giữa AST node và source span, nên có thể chỉ dòng và cột dễ hơn. Tuy nhiên, interpreter vẫn cần quản lý mapping khi macro, template hoặc code generation được dùng.

### 6.5. Debugging và trace

Interpreter có thể ghi trace ở cấp AST:
- Node nào được đánh giá.
- Giá trị trung gian.
- Nhánh điều kiện được chọn.
- Hàm nào được gọi.
- Biến nào thay đổi.

Compiler có thể cung cấp debug metadata và instrumentation, nhưng thường cần thêm công việc để ánh xạ mã đã tối ưu về source. Ngược lại, compiler có thể tận dụng debugger của nền tảng đích nếu sinh mã cho một runtime quen thuộc.

## 7. Đánh đổi về tối ưu hóa

### 7.1. Tối ưu hóa tĩnh

Compiler có thể phân tích nhiều phần chương trình trước khi chạy:
- Constant folding.
- Dead code elimination.
- Common subexpression elimination.
- Inlining.
- Loop optimization.
- Specialization dựa trên kiểu đã biết.
- Loại bỏ kiểm tra dư thừa khi có chứng minh hợp lệ.

Ví dụ:

~~~text
let threshold = 10 * 100
if order.total > threshold then
    allow()
end
~~~

Compiler có thể tính trước threshold thành 1000. Tuy nhiên, chỉ được tối ưu nếu không thay đổi hành vi quan sát được, bao gồm lỗi, overflow, thứ tự tác dụng phụ và độ chính xác số.

### 7.2. Tối ưu hóa động

Interpreter có thể tối ưu bằng:
- Cache kết quả resolve tên.
- Inline cache cho property access.
- Cache parse tree hoặc compiled expression.
- Specialization theo kiểu dữ liệu thường gặp.
- Memoization cho biểu thức thuần.

JIT có thể dùng profiling để nhận diện đoạn code nóng và biên dịch chuyên biệt dựa trên kiểu hoặc dữ liệu thực tế. Nếu giả định tối ưu không còn đúng, runtime cần deoptimization để quay lại đường thực thi tổng quát.

### 7.3. Chi phí và độ phức tạp

Tối ưu hóa có thể làm tăng:
- Thời gian compile.
- Bộ nhớ IR và cache.
- Độ phức tạp debugger.
- Khó khăn khi giải thích trace.
- Rủi ro bug trong optimizer.
- Thời gian warm-up và deoptimization.

Với DSL quy tắc nhỏ, tối ưu hóa đơn giản hoặc interpreter có cache có thể đủ. Không nên thêm JIT chỉ vì kỳ vọng lý thuyết; cần benchmark chứng minh lợi ích.

## 8. Đánh đổi về tính linh hoạt và tính động

### 8.1. Dynamic behavior

Interpreter thường thuận tiện khi DSL hỗ trợ:
- Nạp rule từ database.
- Tạo expression trong runtime.
- Thay đổi cấu hình theo tenant.
- Khai báo hàm hoặc biến động.
- Reflection hoặc truy cập metadata.
- Mở rộng bằng plugin.

Vì AST có thể được tạo và đánh giá ngay, hệ thống có thể hỗ trợ các cấu trúc chưa biết trước khi build ứng dụng.

### 8.2. Compile-time validation

Compiler phù hợp khi muốn:
- Từ chối chương trình sai trước khi deploy.
- Tạo artifact có thể kiểm tra và ký.
- Cố định dependency và kiểu.
- Xác định capability được yêu cầu.
- Tối ưu theo schema hoặc context đã biết.
- Tạo manifest mô tả tài nguyên cần thiết.

Các tính năng này cũng có thể được xây trên interpreter thông qua một bước validation riêng.

### 8.3. Dynamic loading trong hệ biên dịch

Compiler không bắt buộc chương trình phải được biên dịch cùng ứng dụng. Có thể compile từng rule khi người dùng cập nhật, lưu artifact rồi tải vào runtime.

Điều cần thiết là xác định:
- Artifact tương thích với runtime version nào.
- Schema và symbol nào được bind.
- Khi nào cache cần bị vô hiệu hóa.
- Làm sao rollback về artifact trước.
- Các request đang chạy dùng phiên bản nào.

## 9. Đánh đổi về khả năng di động và nền tảng

### 9.1. Native compilation

Compiler sinh mã máy thường phải quan tâm:
- CPU architecture.
- Operating system.
- ABI.
- Calling convention.
- Runtime library.
- Instruction set và feature phần cứng.

Nếu phân phối native artifact, có thể cần build riêng cho từng nền tảng. Đổi lại, artifact có thể tích hợp trực tiếp với hệ điều hành và thư viện native.

### 9.2. Bytecode và virtual machine

Compiler sinh bytecode cho VM có thể đạt tính di động cao hơn native code. Artifact chạy được trên mọi môi trường có VM tương thích.

Đổi lại, cần phân phối VM và quản lý:
- Bytecode version.
- VM runtime version.
- Compatibility.
- Security verification.
- Runtime library.

### 9.3. Interpreter đa nền tảng

Một interpreter được viết bằng ngôn ngữ portable có thể chạy trên nhiều nền tảng. Người dùng phân phối source DSL và runtime tương thích.

Điều này đơn giản hóa artifact nhưng tạo phụ thuộc vào phiên bản interpreter. Cùng một source có thể cho hành vi khác nếu runtime thay đổi ngữ nghĩa hoặc thư viện miền.

### 9.4. Transpilation

Compiler có thể chuyển DSL thành một ngôn ngữ đích như Java, JavaScript, SQL hoặc WebAssembly. Khi đó:
- Tận dụng compiler/runtime của nền tảng đích.
- Dễ tích hợp vào hệ sinh thái có sẵn.
- Cần ánh xạ diagnostics và semantics của DSL sang semantics đích.
- Phải kiểm soát khác biệt kiểu, null, concurrency, exception và numeric behavior.

Sinh code đích không tự động bảo đảm ngữ nghĩa tương đương. Compiler phải giữ đúng hợp đồng của DSL.

## 10. Đánh đổi về triển khai và vận hành

### 10.1. Phân phối source hay artifact

Interpreter thường cần source DSL và runtime. Điều này thuận tiện cho chỉnh sửa và audit, nhưng source có thể tiết lộ logic nghiệp vụ.

Compiler có thể phân phối bytecode hoặc native artifact. Artifact không nhất thiết bảo vệ bí mật; bytecode có thể được reverse engineer và native binary vẫn có thể bị phân tích. Nếu cần bảo vệ logic, phải xem xét kiểm soát truy cập, mã hóa, ký artifact và threat model thay vì dựa vào việc biên dịch.

### 10.2. Build pipeline

Compiler thường thêm bước:
- Compile.
- Validate artifact.
- Package dependency.
- Ký và lưu artifact.
- Kiểm tra tương thích runtime.
- Quản lý cache và rollback.

Interpreter có thể bỏ bước build artifact nhưng vẫn cần:
- Validate source.
- Quản lý version.
- Nạp runtime.
- Kiểm tra capability.
- Cache parse tree hoặc semantic model.
- Giám sát execution.

### 10.3. Cập nhật và rollback

Với compiler, có thể triển khai artifact versioned và rollback về bản trước. Với interpreter, có thể rollback source hoặc AST version. Cả hai đều cần đảm bảo request đang chạy không bị đổi semantics giữa chừng.

Một pattern phổ biến:
1. Compile hoặc validate phiên bản mới.
2. Chạy thử trên test fixtures.
3. Đưa phiên bản vào trạng thái ready.
4. Chuyển traffic hoặc rule evaluation sang phiên bản mới.
5. Theo dõi lỗi và latency.
6. Rollback nếu vượt ngưỡng.

### 10.4. Quan sát và audit

DSL nghiệp vụ có thể cần audit:
- Ai thay đổi rule.
- Source hoặc artifact version nào được chạy.
- Context đầu vào nào được dùng.
- Kết quả và side effect nào xảy ra.
- Runtime version nào xử lý.
- Diagnostic hoặc exception nào xuất hiện.

Interpreter có thể dễ trace ở mức node; compiler có thể dùng artifact hash và execution metadata. Dù chọn cách nào, audit cần gắn với phiên bản bất biến để có thể tái dựng sự kiện.

## 11. Đánh đổi về bảo mật và cách ly

### 11.1. Interpreter không tự động an toàn

Một interpreter cho phép gọi mọi hàm của host application có thể nguy hiểm như bất kỳ cơ chế thực thi code nào. DSL cần giới hạn capability:
- Chỉ expose API cần thiết.
- Giới hạn file/network access.
- Kiểm soát reflection.
- Giới hạn thời gian và bộ nhớ.
- Kiểm soát số lần gọi dịch vụ.
- Cô lập dữ liệu giữa tenant.

### 11.2. Compiler không tự động an toàn

Compiler sinh native code hoặc bytecode vẫn có thể tạo chương trình thực hiện hành động nguy hiểm nếu DSL cho phép. Compiler cần:
- Validate construct được phép.
- Không sinh lời gọi ngoài capability.
- Kiểm tra artifact và metadata.
- Ký artifact nếu cần bảo đảm nguồn gốc.
- Chạy trong sandbox phù hợp.
- Áp dụng resource limits ở runtime.

### 11.3. Static validation và runtime enforcement

Static checking có thể phát hiện một số hành vi không được phép trước khi chạy. Tuy nhiên, quyền có thể thay đổi, dữ liệu có thể không tin cậy và dependency bên ngoài có thể bị thay thế.

Vì vậy, thao tác nhạy cảm cần được kiểm tra quyền tại runtime hoặc ở lớp service đích, kể cả khi compiler đã kiểm tra trước đó.

### 11.4. Multi-tenant DSL

Nếu mỗi tenant có rule riêng:
- Interpreter có thể tạo environment riêng và dễ nạp rule động.
- Compiler có thể compile theo tenant hoặc theo nhóm rule, sau đó cache artifact theo tenant và version.
- Cache phải cách ly để không dùng nhầm artifact hoặc context giữa các tenant.
- Log và diagnostics không được tiết lộ source hoặc dữ liệu của tenant khác.

Lựa chọn cần xét số tenant, tần suất thay rule, số lần chạy và mức độ cách ly cần thiết.

## 12. Chi phí phát triển và bảo trì

### 12.1. Interpreter đơn giản

Một interpreter AST cơ bản có thể dễ xây dựng:
- Mỗi loại node có một hàm evaluate.
- Runtime environment quản lý biến và scope.
- Các phép toán gọi hàm xử lý tương ứng.
- Có thể trace từng node.

Đối với DSL nhỏ, đây là cách nhanh để tạo prototype và xác nhận ngữ nghĩa với người dùng miền.

### 12.2. Compiler

Compiler có thể cần thêm:
- IR ổn định.
- Type lowering.
- Code generation.
- Register hoặc stack model.
- Runtime ABI.
- Optimization passes.
- Debug metadata.
- Artifact versioning.

Độ phức tạp tăng đáng kể nếu target là nhiều nền tảng hoặc cần tối ưu mạnh.

### 12.3. Interpreter phức tạp

Một interpreter production cũng có thể rất lớn nếu hỗ trợ:
- Type inference.
- Closures.
- Concurrency.
- Transaction.
- Sandboxing.
- Incremental evaluation.
- Profiling.
- Caching.
- Hot reload.
- Debugger.

Do đó, so sánh chi phí cần dựa trên feature set thực tế, không phải giả định mọi interpreter đều nhỏ và mọi compiler đều lớn.

### 12.4. Chi phí tương thích

Compiler artifact cần tương thích với runtime và target. Interpreter cần duy trì hành vi giữa các phiên bản engine. Cả hai đều phải quản lý:
- Version của DSL.
- Version của standard library.
- Schema hoặc domain model.
- Deprecation.
- Migration.
- Regression tests.

## 13. Mô hình lai: bytecode, VM và JIT

### 13.1. Bytecode VM

Một compiler có thể chuyển AST thành bytecode:

~~~text
DSL:
total = subtotal + tax
~~~

Bytecode minh họa:

~~~text
LOAD subtotal
LOAD tax
ADD
STORE total
~~~

VM đọc từng instruction và thực hiện. Đây là thông dịch ở cấp bytecode, dù DSL đã trải qua bước biên dịch.

Ưu điểm:
- Instruction set nhỏ và ổn định.
- Dễ kiểm soát capability.
- Artifact gọn hơn AST trong một số hệ thống.
- Có thể cache và tái sử dụng.
- Dễ thêm verifier cho bytecode.

Hạn chế:
- Cần thiết kế và bảo trì VM.
- Cần version bytecode.
- Hiệu năng phụ thuộc interpreter dispatch và tối ưu.
- Debug source cần mapping từ instruction về source.

### 13.2. Just-in-Time compilation

JIT biên dịch code trong lúc chạy. Một chiến lược thường gặp:
1. Bắt đầu bằng interpreter hoặc bytecode VM.
2. Thu thập profiling data.
3. Xác định function hoặc rule được gọi thường xuyên.
4. Compile đoạn nóng sang mã native.
5. Chạy mã native.
6. Deoptimize nếu giả định tối ưu không còn đúng.

JIT phù hợp khi có đoạn code chạy lặp nhiều lần nhưng không thể hoặc không muốn compile toàn bộ trước khi deploy.

### 13.3. Ahead-of-Time compilation

AOT (*Ahead-of-Time compilation*) biên dịch trước khi chương trình chạy. Nó có thể giảm startup và tránh chi phí JIT warm-up, đồng thời tạo artifact có thể kiểm tra và triển khai.

AOT có thể làm mất một số lợi ích specialization theo dữ liệu thực tế. Một số hệ thống kết hợp AOT cho phần ổn định với JIT cho phần động.

### 13.4. Khi nào chọn mô hình lai?

Mô hình lai hữu ích khi:
- Rule cần nạp động nhưng được chạy nhiều lần.
- Cần startup nhanh và throughput cao sau warm-up.
- Cần kiểm tra tĩnh nhưng vẫn hỗ trợ một phần động.
- Muốn phân phối bytecode portable và tối ưu các đoạn nóng.
- Workload có độ lệch lớn: một số rule rất nóng, nhiều rule chỉ chạy ít lần.

Chi phí là kiến trúc phức tạp hơn, cần profiling, cache, invalidation, deoptimization và công cụ debug nhiều tầng.

## 14. Ví dụ lựa chọn cho các loại DSL

### 14.1. DSL cấu hình

Ví dụ:

~~~text
service "billing" {
    timeout = 5s
    retries = 3
    endpoint = "https://billing.example"
}
~~~

Cấu hình thường được parse và validate rồi chuyển thành object hoặc model. Không nhất thiết cần interpreter đầy đủ hay compiler native.

Một cách phù hợp có thể là:
- Parse source thành model.
- Validate kiểu, trường bắt buộc và constraint.
- Chuyển model thành cấu hình runtime.
- Cache kết quả đã validate.

Nếu cấu hình chứa expression động, có thể dùng interpreter nhỏ cho expression đó.

### 14.2. DSL quy tắc nghiệp vụ

Ví dụ:

~~~text
rule "vip-customer" {
    when customer.totalSpent > 10000000
    then customer.level = "VIP"
}
~~~

Nếu người dùng thường xuyên thay rule và cần áp dụng ngay, interpreter hoặc bytecode compiler với hot reload có thể phù hợp.

Nếu rule được đánh giá hàng triệu lần, có thể compile một lần sau khi cập nhật rồi cache artifact. Nên đo số rule, số lần chạy, kích thước context và độ phức tạp biểu thức.

### 14.3. DSL truy vấn

DSL truy vấn có thể được compile sang SQL hoặc một query plan. Compiler giúp:
- Kiểm tra tên bảng và cột theo schema.
- Bind parameter.
- Tối ưu predicate.
- Tạo query plan.
- Giới hạn câu truy vấn được phép.

Một interpreter có thể hữu ích cho expression filter hoặc môi trường không có backend query compiler. Nhưng nếu mục tiêu là tận dụng optimizer của database, compilation sang SQL/query plan thường tự nhiên hơn.

### 14.4. DSL workflow

Workflow thường cần trạng thái bền vững, retry, timeout, event và compensation. Interpreter có thể điều phối từng step từ workflow model. Compiler có thể chuyển workflow thành state machine hoặc execution plan.

Một engine workflow thường là mô hình lai: parse/validate workflow, compile thành plan, sau đó runtime engine diễn giải plan và lưu trạng thái. Đây là ví dụ cho thấy hai chiến lược có thể cùng tồn tại ở các tầng khác nhau.

### 14.5. DSL tính toán số hoặc biến đổi dữ liệu

Nếu biểu thức được chạy lặp trên lượng dữ liệu lớn, compiler hoặc vectorized execution có thể có lợi thế. Nếu biểu thức nhỏ, thay đổi liên tục và cần kiểm soát linh hoạt, interpreter có thể đơn giản hơn.

## 15. Ma trận quyết định

Có thể đánh giá theo các câu hỏi sau:

| Câu hỏi | Nghiêng về thông dịch | Nghiêng về biên dịch |
|---|---|---|
| Rule có thay đổi thường xuyên không? | Có, cần áp dụng ngay | Ít thay đổi, có thể build artifact |
| Mỗi chương trình chạy bao nhiêu lần? | Ít lần hoặc không dự đoán được | Nhiều lần, workload ổn định |
| Có yêu cầu throughput cao không? | Có thể cần JIT/cache | Thường phù hợp compile trước |
| Cần báo lỗi tĩnh trước deploy? | Có thể thêm static validation | Compiler thuận tiện cho pipeline này |
| Cần nạp expression động? | Tự nhiên | Có thể compile khi nạp |
| Target có nhiều nền tảng? | Phân phối source và runtime | Bytecode/VM hoặc nhiều native target |
| Cần tận dụng optimizer nền tảng? | Thường ít trực tiếp hơn | Compile sang target phù hợp |
| Có cần trace từng node? | Thường thuận tiện | Cần debug metadata/instrumentation |
| Runtime có bị giới hạn tài nguyên? | Có thể quản lý qua evaluator | Có thể quản lý qua verifier và sandbox |
| Nhóm có năng lực xây compiler? | Interpreter dễ bắt đầu hơn | Cần đầu tư IR/codegen/tooling |

Bảng này dùng để định hướng, không thay thế benchmark hoặc đánh giá rủi ro.

## 16. Cách đo trước khi quyết định

Không nên chọn compiler chỉ dựa trên giả định "compiled code luôn nhanh hơn", hoặc chọn interpreter chỉ vì code ít hơn. Hãy tạo benchmark theo workload thực tế.

### 16.1. Xác định workload

Thu thập:
- Số lượng DSL program/rule.
- Kích thước source trung bình và lớn nhất.
- Tần suất cập nhật.
- Số lần đánh giá mỗi version.
- Độ phức tạp biểu thức.
- Số lần gọi hàm host hoặc service.
- Kích thước context.
- Tỷ lệ rule được chạy và không được chạy.
- Số tenant hoặc workspace đồng thời.

### 16.2. Đo các chỉ số

| Chỉ số | Cách đo |
|---|---|
| Parse time | Thời gian tạo AST/model |
| Compile time | Thời gian tạo bytecode/native artifact |
| First-run latency | Thời gian lần chạy đầu |
| Warm latency | Thời gian sau cache/JIT warm-up |
| Throughput | Số lần đánh giá mỗi giây |
| Memory | Heap, native memory, artifact cache |
| Update latency | Thời gian từ sửa rule đến khi áp dụng |
| Error latency | Thời gian phát hiện và trả diagnostic |
| Tail latency | P95/P99 thay vì chỉ trung bình |

### 16.3. Benchmark công bằng

So sánh phải dùng cùng:
- Input và semantics.
- Data context.
- Side effects.
- Runtime limits.
- Chính sách cache.
- Mức tối ưu hóa phù hợp.
- Điều kiện máy và concurrency.

Nếu interpreter được phép cache AST còn compiler phải compile lại mỗi request, phép so sánh không phản ánh kiến trúc production. Ngược lại, nếu compiler được compile trước nhưng interpreter phải parse mỗi lần, cũng không công bằng nếu production có thể cache parse tree.

### 16.4. Đo cả correctness

Tốc độ không đủ. Hai implementation phải tạo kết quả tương đương:
- Giá trị trả về.
- Thay đổi trạng thái.
- Thứ tự side effect.
- Exception/diagnostics.
- Quy tắc null và numeric precision.
- Hành vi khi timeout hoặc cancellation.

Tối ưu hóa chỉ hợp lệ khi bảo toàn semantics đã công bố.

## 17. Những hiểu lầm thường gặp

1. **Ngôn ngữ biên dịch thì luôn nhanh hơn:** hiệu năng phụ thuộc compiler, runtime, workload và chi phí gọi host.
2. **Ngôn ngữ thông dịch không có compile step:** interpreter có thể compile sang bytecode hoặc dùng JIT.
3. **Compiler phát hiện mọi lỗi trước khi chạy:** lỗi phụ thuộc dữ liệu và môi trường vẫn có thể chỉ xuất hiện lúc runtime.
4. **Interpreter không thể kiểm tra kiểu tĩnh:** interpreter có thể dùng type checker và semantic validator đầy đủ.
5. **Bytecode là thông dịch thuần túy:** bytecode thường là đầu ra của compiler, sau đó VM có thể thông dịch hoặc JIT.
6. **Biên dịch làm source an toàn hoặc bí mật:** artifact vẫn có thể reverse engineer và hành vi vẫn cần sandbox.
7. **Interpreter luôn dễ bảo trì hơn:** interpreter production có thể cần nhiều hệ thống cache, profiling, transaction và security.
8. **Compiler luôn khó debug hơn:** source mapping, debug metadata và tooling tốt có thể cung cấp trải nghiệm debug tốt.
9. **JIT luôn cải thiện hiệu năng:** workload ngắn hoặc biến động có thể không bù được warm-up và compile overhead.
10. **Có thể tối ưu mà không đổi kết quả:** numeric behavior, exception, evaluation order và side effects có thể khiến phép biến đổi không tương đương.

## 18. Quy trình chọn kiến trúc cho DSL

Một quy trình thực tế:

1. **Xác định mục đích DSL:** cấu hình, rule, query, workflow, scripting hay tính toán.
2. **Xác định vòng đời source:** được viết lúc build, bởi developer, hay do người dùng thay đổi trong production.
3. **Mô tả semantics:** kiểu, thứ tự đánh giá, side effect, error và capability.
4. **Xác định tần suất chạy:** số lần chạy mỗi version và phân bố hot/cold rule.
5. **Đặt yêu cầu latency và throughput:** bao gồm cold start và tail latency.
6. **Xác định target:** native, VM, browser, database, serverless hoặc nhiều nền tảng.
7. **Chọn mức kiểm tra tĩnh:** quyết định lỗi nào phải chặn trước deploy.
8. **Thử interpreter baseline:** đo chi phí parse, evaluate, lookup và host calls.
9. **Thử compiler hoặc bytecode prototype:** đo compile overhead, artifact size và tốc độ chạy.
10. **Đánh giá vận hành:** hot reload, rollback, audit, source mapping, sandbox và versioning.
11. **Chọn kiến trúc nhỏ nhất đáp ứng yêu cầu:** chỉ thêm JIT hoặc optimizer phức tạp khi số liệu chứng minh cần thiết.
12. **Giữ conformance tests chung:** xác nhận interpreter và compiler có cùng hành vi nếu cùng hỗ trợ một DSL.

Một thiết kế tốt thường bắt đầu bằng semantics và workload. Khi đã biết hành vi phải bảo đảm và cách chương trình được sử dụng, việc chọn interpreter, compiler hay mô hình lai sẽ có cơ sở hơn.

## 19. Kết luận

Biên dịch và thông dịch là hai chiến lược thực thi có những đánh đổi khác nhau. Biên dịch thường có lợi thế khi chương trình chạy lặp lại, cần tối ưu mạnh, cần artifact được kiểm soát hoặc cần tích hợp với một nền tảng đích. Thông dịch thường thuận tiện khi DSL cần nạp động, thay đổi nhanh, trace trực tiếp theo AST hoặc có workload nhỏ và linh hoạt.

Các hệ thống DSL thực tế thường kết hợp cả hai: parse và validate trước, compile sang bytecode, dùng VM để thực thi và có thể JIT các đoạn nóng. Lựa chọn nên dựa trên vòng đời rule, số lần chạy, latency, throughput, portability, diagnostics, bảo mật và chi phí vận hành. Dù chọn cách nào, interpreter và compiler phải tuân theo cùng một đặc tả ngữ nghĩa để chương trình DSL cho kết quả nhất quán.

