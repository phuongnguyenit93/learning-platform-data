# Hiệu năng runtime

**Hiệu năng runtime** (*runtime performance*) mô tả tốc độ và mức tiêu thụ tài nguyên của một chương trình khi nó đang thực thi. Với một DSL, hiệu năng runtime không chỉ phụ thuộc vào cú pháp hay kích thước source. Nó còn phụ thuộc cách DSL được phân tích, biên dịch hoặc thông dịch, cách runtime biểu diễn chương trình, cách gọi host function, quản lý bộ nhớ, lập lịch công việc và tương tác với hệ thống bên ngoài.

Một DSL có thể rất dễ viết nhưng tạo ra chương trình chạy chậm nếu mỗi biểu thức đều được diễn giải lặp lại, mỗi lần truy cập thuộc tính đều tra cứu động hoặc runtime tạo quá nhiều object tạm. Ngược lại, DSL có thể cung cấp abstraction cấp cao mà vẫn chạy nhanh nếu compiler tối ưu biểu thức, runtime dùng cấu trúc dữ liệu phù hợp và các điểm giao tiếp được thiết kế rõ.

Ví dụ, một DSL truy vấn có thể mô tả:

~~~text
query ActiveCustomers {
    from customers
    where status == "ACTIVE"
    and lastOrderDate >= date("2026-01-01")
    select id, name, totalSpent
}
~~~

Hiệu năng phụ thuộc cách query engine lọc dữ liệu, dùng index, đánh giá điều kiện, tạo kết quả và truyền dữ liệu qua các lớp runtime. Cùng một chương trình logic có thể có thời gian chạy rất khác nhau giữa một interpreter đơn giản và một execution plan được tối ưu.

## 1. Hiểu hiệu năng runtime

Hiệu năng runtime là tập hợp nhiều thuộc tính. Không thể chỉ nhìn một con số thời gian chạy rồi kết luận hệ thống nhanh hay chậm.

Các chỉ số thường được quan tâm:

| Chỉ số | Ý nghĩa |
|---|---|
| Latency | Thời gian hoàn thành một thao tác |
| Throughput | Số thao tác hoàn thành trong một đơn vị thời gian |
| CPU utilization | Mức sử dụng CPU |
| Memory footprint | Lượng bộ nhớ đang được sử dụng |
| Allocation rate | Tốc độ tạo object hoặc vùng nhớ mới |
| GC pause | Thời gian chương trình bị dừng để garbage collection |
| I/O wait | Thời gian chờ disk, network hoặc thiết bị |
| Contention | Thời gian chờ lock hoặc tài nguyên dùng chung |
| Startup time | Thời gian từ khi khởi động đến khi sẵn sàng |
| Tail latency | Độ trễ ở các percentile cao như p95 hoặc p99 |

### 1.1. Latency và throughput

Latency đo thời gian của một request. Throughput đo số request mà hệ thống xử lý được trong một khoảng thời gian.

Một runtime có thể có latency thấp khi chỉ có một request nhưng throughput giảm mạnh khi nhiều request chạy đồng thời do lock contention hoặc giới hạn connection pool.

### 1.2. Average và percentile

Average latency có thể che giấu các request rất chậm. Ví dụ, phần lớn request mất 10 ms nhưng một số request mất vài giây. Với hệ thống tương tác, p95 và p99 thường hữu ích hơn để hiểu trải nghiệm ở phần đuôi phân phối.

### 1.3. Startup và steady-state

Runtime có thể cần thời gian khởi động để load module, parse DSL, compile expression, tạo connection pool hoặc warm cache. Startup performance và steady-state performance cần được đo riêng.

### 1.4. Hiệu năng của DSL và hiệu năng của host

Một DSL chạy trong ứng dụng chủ có thể tiêu tốn thời gian ở parser, evaluator hoặc runtime bridge. Nhưng tổng thời gian cũng có thể bị chi phối bởi database, network, filesystem hoặc service bên ngoài.

Khi đo, cần phân tách thời gian của DSL engine khỏi thời gian của host application và dependency.

## 2. Các giai đoạn thực thi của DSL

Một DSL thường đi qua nhiều giai đoạn trước và trong runtime:

~~~text
DSL source
    |
    v
Lexing and parsing
    |
    v
AST / Intermediate representation
    |
    v
Semantic analysis
    |
    v
Compile or prepare
    |
    v
Runtime execution
    |
    v
Host APIs / External systems
~~~

Mỗi giai đoạn có chi phí riêng.

### 2.1. Parse time

Parser chuyển source thành cấu trúc cú pháp. Nếu ứng dụng parse cùng một DSL file mỗi request, chi phí parse có thể trở thành overhead đáng kể.

### 2.2. Semantic analysis

Compiler có thể resolve tên, kiểm tra type, tìm overload, kiểm tra quyền hoặc xây dựng symbol table. Phần lớn công việc này nên thực hiện trước khi chạy chương trình nếu thông tin đã có sẵn.

### 2.3. Preparation và compilation

Runtime có thể chuyển AST sang bytecode, instruction sequence hoặc execution plan. Chi phí chuẩn bị có thể được amortize qua nhiều lần chạy nếu chương trình được tái sử dụng.

### 2.4. Runtime execution

Execution engine đọc instruction, đánh giá expression, gọi function, thao tác dữ liệu và tạo output. Đây thường là phần cần tối ưu khi một chương trình chạy lặp lại nhiều lần.

### 2.5. Host integration

DSL có thể gọi API của host application. Chi phí chuyển đổi kiểu, reflection, serialization, context switching và network call có thể lớn hơn chi phí đánh giá DSL.

## 3. Interpreter, bytecode và native compilation

Chiến lược thực thi ảnh hưởng trực tiếp đến hiệu năng và độ phức tạp của runtime.

### 3.1. Tree-walking interpreter

Tree-walking interpreter duyệt AST và thực thi từng node:

~~~text
BinaryExpression
├── Identifier("price")
├── Operator("+")
└── Literal(10)
~~~

Khi chạy, evaluator lần lượt đánh giá hai operand rồi áp dụng phép cộng.

Ưu điểm:

- Dễ xây dựng và gỡ lỗi.
- AST giữ gần với cấu trúc source.
- Phù hợp DSL nhỏ hoặc chạy không thường xuyên.

Hạn chế:

- Mỗi node có thể tạo một lời gọi evaluator.
- Có nhiều nhánh dispatch và kiểm tra kiểu lặp lại.
- Cấu trúc object của AST có thể gây pointer chasing.
- Khó áp dụng một số tối ưu ở cấp instruction.

### 3.2. Bytecode interpreter

Compiler chuyển AST thành chuỗi instruction:

~~~text
LOAD_LOCAL 0
LOAD_CONST 10
ADD
RETURN
~~~

Bytecode có thể nhỏ hơn AST, giảm chi phí dispatch và dễ cache. Interpreter vẫn cần thực thi instruction, nhưng representation tuyến tính có thể thân thiện với instruction cache hơn.

### 3.3. Register-based và stack-based VM

Stack VM dùng operand stack:

~~~text
PUSH 5
PUSH 7
ADD
~~~

Register VM dùng các slot hoặc virtual register:

~~~text
LOAD r0, 5
LOAD r1, 7
ADD r2, r0, r1
~~~

Stack VM thường đơn giản hóa compiler. Register VM có thể giảm số instruction nhưng instruction encoding và allocator phức tạp hơn. Hiệu năng thực tế phụ thuộc workload và implementation.

### 3.4. Native compilation

Compiler có thể chuyển DSL thành machine code hoặc source code của ngôn ngữ host rồi dùng compiler hiện có. Cách này có thể tạo code nhanh nhưng tăng chi phí compile, yêu cầu toolchain và phức tạp hóa debugging.

### 3.5. JIT compilation

Just-in-time compiler biên dịch một phần chương trình trong lúc chạy. Runtime có thể bắt đầu bằng interpreter rồi biên dịch các đoạn được thực thi thường xuyên.

JIT có thể tăng tốc steady-state nhưng cần thời gian warm-up, profiling và quản lý code cache. Với chương trình chạy một lần, chi phí JIT có thể lớn hơn lợi ích.

### 3.6. Chọn chiến lược thực thi

| Workload | Chiến lược có thể phù hợp |
|---|---|
| DSL nhỏ, chạy ít lần | Interpreter đơn giản |
| Rule chạy lặp nhiều lần | Bytecode hoặc compiled expression |
| Query workload lớn | Execution plan và operator specialization |
| Script dài hạn, hot path rõ | JIT hoặc native compilation |
| Cấu hình khai báo | Parse một lần, tạo immutable model |

Không có chiến lược tốt nhất cho mọi DSL. Cần đo startup, warm-up, throughput, memory và chi phí phát triển.

## 4. Chi phí dispatch và biểu diễn instruction

Interpreter cần chọn hành động cho mỗi node hoặc instruction. Dispatch quá tốn kém có thể làm chậm chương trình có nhiều thao tác nhỏ.

### 4.1. Virtual dispatch

Nếu mỗi AST node là một object với method evaluate riêng, runtime có thể thực hiện nhiều virtual method call. Với expression đơn giản, chi phí dispatch đôi khi lớn so với phép toán thực tế.

### 4.2. Opcode dispatch

Bytecode interpreter có thể dùng opcode và switch:

~~~text
while (running) {
    instruction = code[programCounter]
    switch instruction.opcode:
        case LOAD_CONST:
            ...
        case ADD:
            ...
        case CALL:
            ...
}
~~~

Đây là mô hình khái niệm. Compiler/runtime thực tế có thể dùng computed dispatch, threaded code hoặc kỹ thuật khác tùy ngôn ngữ implementation.

### 4.3. Instruction fusion

Một chuỗi instruction thường gặp có thể được gộp thành một instruction lớn hơn. Ví dụ load local rồi so sánh có thể thành một operation chuyên biệt. Fusion giảm dispatch và intermediate value.

### 4.4. Superinstruction

Superinstruction là instruction đại diện cho một pattern nhiều instruction cơ bản. Runtime có thể tạo sẵn các pattern thường gặp để giảm overhead.

### 4.5. Trade-off

Quá nhiều opcode chuyên biệt làm tăng kích thước interpreter và code cache. Chỉ nên tạo specialization dựa trên profile và benchmark có ý nghĩa.

## 5. Tối ưu biểu thức

Biểu thức trong DSL thường được đánh giá nhiều lần. Compiler có thể tối ưu trước khi runtime thực thi.

### 5.1. Constant folding

Biểu thức chỉ chứa hằng số có thể được tính lúc compile:

~~~text
timeout = 2 * 30 seconds
~~~

Compiler có thể thay biểu thức bằng giá trị 60 seconds.

### 5.2. Constant propagation

Nếu compiler biết biến không đổi trong một vùng chương trình, nó có thể thay việc đọc biến bằng giá trị đã biết.

### 5.3. Dead code elimination

Nhánh không thể chạy có thể được loại bỏ:

~~~text
if false {
    performExpensiveOperation()
}
~~~

Việc loại bỏ chỉ hợp lệ khi compiler chứng minh nhánh không có side effect cần giữ.

### 5.4. Common subexpression elimination

Nếu cùng một biểu thức thuần được tính nhiều lần với cùng input, compiler có thể tính một lần rồi dùng lại:

~~~text
tax = price * taxRate
total = price + price * taxRate
~~~

Có thể tái sử dụng phép tính price nhân taxRate nếu semantics và khả năng thay đổi dữ liệu cho phép.

### 5.5. Short-circuit evaluation

Với AND và OR, runtime có thể dừng ngay khi kết quả đã xác định:

~~~text
isAuthorized && hasRequiredRole
~~~

Nếu isAuthorized là false, vế phải không cần đánh giá. DSL cần định nghĩa rõ short-circuit và side effect để người viết không phụ thuộc vào thứ tự không được bảo đảm.

### 5.6. Expression specialization

Nếu expression đã được type-check và operand type không thay đổi, runtime có thể dùng phép toán chuyên biệt thay vì kiểm tra type động mỗi lần.

### 5.7. Purity và optimization

Compiler chỉ được loại bỏ, gộp hoặc di chuyển biểu thức khi semantics cho phép. Một function đọc đồng hồ, gọi network hoặc thay đổi state không thể được xem như biểu thức thuần.

## 6. Type system và hiệu năng

Thông tin type có thể giúp compiler tạo code hiệu quả hơn.

### 6.1. Static typing

Với static typing, compiler biết type của biểu thức trước khi chạy. Nó có thể chọn phép toán cụ thể, layout dữ liệu và cách gọi function.

### 6.2. Dynamic typing

Dynamic typing cho phép một biến giữ nhiều loại giá trị. Runtime cần kiểm tra type hoặc dispatch theo type khi thực thi. Điều này linh hoạt nhưng có thể tăng overhead.

### 6.3. Type inference

Type inference suy ra type từ cách dùng và giá trị. Nếu inference thành công, DSL có thể giữ cú pháp ngắn mà vẫn cho compiler nhiều thông tin tối ưu.

### 6.4. Boxing và unboxing

Một primitive như integer có thể bị đóng gói thành object để đi qua API generic. Boxing có thể tạo allocation và tăng áp lực garbage collector. Unboxing lại cần kiểm tra và chuyển đổi.

### 6.5. Specialized collection

Collection dành riêng cho integer hoặc floating-point có thể lưu dữ liệu liên tục, giảm object allocation so với collection chứa object generic.

### 6.6. Type stability

Một expression có output type ổn định dễ tối ưu hơn expression liên tục trả về nhiều type không liên quan. DSL có thể hỗ trợ type annotation hoặc inference để làm rõ điều này.

## 7. Function call và host interop

Gọi function thường có chi phí lớn hơn một phép toán primitive, đặc biệt khi gọi qua reflection hoặc ranh giới runtime.

### 7.1. Function call trong DSL

Một function call có thể gồm:

1. Resolve tên function.
2. Tìm overload phù hợp.
3. Đánh giá argument.
4. Chuyển đổi kiểu.
5. Tạo call frame hoặc context.
6. Thực thi function.
7. Chuyển kết quả về DSL value.

Nếu việc resolve và kiểm tra signature lặp lại ở mỗi lần gọi, runtime có thể cache call target sau khi chương trình được prepare.

### 7.2. Reflection

Reflection giúp DSL gọi method của host application một cách linh hoạt. Tuy nhiên, lookup method, kiểm tra access và chuyển đổi argument có thể tốn kém.

Có thể resolve method một lần khi compile hoặc khởi tạo binding, rồi dùng call handle hoặc adapter đã chuẩn bị cho các lần gọi sau.

### 7.3. Generated adapter

Generated adapter là lớp bridge được tạo trước để chuyển DSL value sang host type và ngược lại. Nó có thể nhanh hơn reflection tổng quát và giúp kiểm tra signature sớm.

### 7.4. Boundary crossing

Mỗi lần chuyển giữa DSL runtime và host runtime có thể phát sinh:

- Boxing/unboxing.
- Object allocation.
- Thread context switch.
- Exception translation.
- Serialization.
- Security check.

Giảm số lần crossing thường hiệu quả hơn tối ưu một phép toán nhỏ bên trong DSL.

### 7.5. Batch API

Thay vì gọi host API cho từng item, runtime có thể gom nhiều item vào một batch:

~~~text
for item in items {
    host.save(item)
}
~~~

Nếu host hỗ trợ bulk operation, một lời gọi batch có thể giảm overhead call, lock và network round trip.

### 7.6. Async interop

Khi host API trả future hoặc promise, DSL runtime cần định nghĩa cách await, propagate cancellation và xử lý exception. Không nên chặn thread chỉ để đợi một thao tác I/O bất đồng bộ.

## 8. Memory allocation và object lifetime

Allocation rate cao có thể làm tăng CPU usage và tần suất garbage collection.

### 8.1. Temporary object

Một expression evaluator có thể tạo object trung gian cho mỗi phép toán:

~~~text
value = add(
    multiply(a, b),
    multiply(c, d)
)
~~~

Nếu mọi intermediate value đều là object riêng, allocation có thể tăng nhanh trong vòng lặp lớn.

### 8.2. Object reuse

Một số object như parser context, execution frame hoặc buffer có thể được tái sử dụng nếu ownership và concurrency được quản lý đúng.

### 8.3. Escape analysis

Compiler có thể xác định object chỉ tồn tại trong phạm vi một method hoặc expression. Khi an toàn, runtime có thể tránh heap allocation hoặc scalar-replace object.

### 8.4. Arena và region allocation

Với dữ liệu có vòng đời rõ, arena allocator có thể cấp phát nhiều object trong một region rồi giải phóng cả region cùng lúc. Cách này giảm chi phí quản lý từng object, nhưng cần tránh giữ reference vượt vòng đời region.

### 8.5. Buffer pooling

Buffer pooling hữu ích khi có nhiều thao tác serialization hoặc I/O lặp lại. Pool cần giới hạn dung lượng và tránh giữ buffer quá lớn sau một request bất thường.

### 8.6. Object retention

Cache hoặc closure có thể vô tình giữ object lớn lâu hơn cần thiết. Memory leak trong managed runtime thường là object vẫn reachable do reference còn tồn tại, không nhất thiết là quên gọi free.

## 9. Garbage collection

Garbage collector tự động thu hồi object không còn reachable. Nó giảm gánh nặng quản lý bộ nhớ nhưng vẫn có chi phí CPU và có thể tạo pause.

### 9.1. Allocation pressure

Nhiều object ngắn hạn làm tăng công việc của collector. Runtime DSL có thể tạo allocation ở AST node, value wrapper, argument array, map, string và execution context.

### 9.2. Generational collection

Generational GC dựa trên quan sát rằng nhiều object chết sớm. Object mới được thu gom thường xuyên hơn; object sống lâu được chuyển sang vùng khác.

### 9.3. Pause time

Stop-the-world pause có thể làm tăng tail latency. Một số collector giảm pause bằng cách thực hiện nhiều công việc concurrent, đổi lại có thể dùng thêm CPU hoặc memory.

### 9.4. Heap sizing

Heap quá nhỏ làm GC chạy thường xuyên. Heap quá lớn có thể tăng footprint và thời gian một số pha collection. Cần đo trên workload đại diện.

### 9.5. GC metrics

Theo dõi allocation rate, collection count, pause duration, heap occupancy và promotion rate. Một metric đơn lẻ không đủ để kết luận nguyên nhân.

### 9.6. Giảm allocation đúng chỗ

Trước tiên xác định object nào được tạo nhiều qua allocation profiler. Tối ưu object có tác động lớn thay vì viết lại toàn bộ runtime theo phỏng đoán.

## 10. Data structure và memory layout

Cấu trúc dữ liệu ảnh hưởng số lần truy cập bộ nhớ, allocation và độ phức tạp của thao tác.

### 10.1. Array và linked structure

Array thường lưu phần tử liên tiếp, hỗ trợ truy cập theo index nhanh và tận dụng cache locality. Linked list cần đi qua các node và có thể gây pointer chasing.

Với instruction stream hoặc constant pool, array có thể phù hợp hơn cấu trúc node liên kết nếu workload chủ yếu duyệt tuần tự.

### 10.2. Hash map và symbol table

Symbol table thường ánh xạ tên biến hoặc function đến slot, symbol ID hoặc metadata. Hash map giúp lookup trung bình nhanh, nhưng lookup theo tên chuỗi ở mỗi lần thực thi có thể tạo overhead.

Compiler có thể resolve identifier thành slot index để runtime truy cập trực tiếp.

### 10.3. Dense identifier

Thay vì lưu string name trong mỗi instruction, compiler có thể gán integer ID:

~~~text
symbol "customerId" -> slot 4
symbol "total"      -> slot 5
~~~

Runtime đọc slot trực tiếp và chỉ cần tên khi hiển thị diagnostics.

### 10.4. Cache locality

CPU cache hoạt động hiệu quả khi dữ liệu được truy cập gần nhau về địa chỉ và thời gian. Một representation tuyến tính, compact có thể giảm cache miss so với nhiều object phân tán trên heap.

### 10.5. Data-oriented design

Data-oriented design bắt đầu từ cách dữ liệu được truy cập trong workload rồi chọn layout phù hợp. Ví dụ, nếu evaluator thường đọc cùng một field của hàng nghìn record, columnar layout có thể hiệu quả hơn nhiều object record riêng biệt.

### 10.6. Immutable data

Immutable AST, compiled plan và metadata có thể được chia sẻ giữa nhiều execution mà không cần lock cho mỗi lần đọc. Điều này giúp giảm contention và đơn giản hóa concurrency.

## 11. Caching trong DSL runtime

Cache có thể tránh lặp lại công việc tốn kém. Tuy nhiên, cache cần key, lifetime, invalidation và giới hạn memory rõ ràng.

### 11.1. Parse cache

Nếu nhiều request dùng cùng DSL source, runtime có thể cache parsed representation theo source identity và content hash.

### 11.2. Compiled program cache

Một chương trình đã compile có thể được dùng lại nhiều lần. Cache key cần bao gồm source revision, compiler version, language options, imported module version và những cấu hình ảnh hưởng code generation.

### 11.3. Function binding cache

Method hoặc host function đã resolve có thể được lưu trong call site để tránh reflection lookup ở mỗi lần gọi.

### 11.4. Constant và metadata cache

Metadata không thay đổi như schema, field mapping hoặc enum table có thể được cache ở scope phù hợp.

### 11.5. Result cache

Cache kết quả function hoặc query chỉ an toàn khi input và dependency được xác định, kết quả không phụ thuộc state ẩn và invalidation có semantics rõ.

### 11.6. Cache invalidation

Cache có thể bị stale khi source, policy, schema hoặc external data thay đổi. Một số chiến lược:

- Versioned key: version mới tạo cache entry mới.
- Time-to-live: entry hết hạn sau thời gian xác định.
- Explicit invalidation: sự kiện thay đổi xóa entry liên quan.
- Bounded cache: giới hạn entry và dùng eviction policy.

### 11.7. Cache stampede

Khi một entry hết hạn, nhiều request có thể đồng thời tính lại cùng dữ liệu. Single-flight hoặc request coalescing cho phép một request tính, các request khác chờ kết quả.

### 11.8. Cache memory budget

Cache cần giới hạn số entry hoặc byte sử dụng. Cache không giới hạn có thể làm tăng heap và gây GC pressure.

## 12. Concurrency và parallel execution

Concurrency cho phép nhiều tác vụ tiến triển chồng lấp. Parallelism là thực thi nhiều tác vụ cùng lúc trên nhiều core.

### 12.1. Thread per request

Mô hình một thread cho mỗi request dễ hiểu nhưng có thể tiêu tốn nhiều stack và context-switch khi số request đồng thời lớn.

### 12.2. Thread pool

Thread pool tái sử dụng worker thread và giới hạn concurrency. Pool quá nhỏ tạo queue dài; pool quá lớn có thể làm CPU oversubscription hoặc tăng contention.

### 12.3. Work stealing

Worker có thể lấy task từ queue của worker khác khi rảnh. Work stealing phù hợp với task nhỏ và graph có thể chia nhánh, nhưng cần kiểm soát task granularity và scheduling overhead.

### 12.4. Parallel map

DSL có thể cung cấp phép biến đổi song song:

~~~text
results = parallelMap(records) {
    calculateScore(record)
}
~~~

Parallel map chỉ có lợi khi mỗi phần tử có đủ lượng công việc để bù chi phí scheduling và dữ liệu có thể xử lý độc lập.

### 12.5. Race condition

Nếu nhiều worker cập nhật cùng mutable state, kết quả có thể phụ thuộc thứ tự thực thi. DSL cần xác định semantics của shared state, synchronization và side effect.

### 12.6. Lock contention

Một lock toàn cục cho symbol table, cache hoặc object registry có thể trở thành điểm nghẽn. Có thể dùng immutable snapshot, partitioned lock, concurrent structure hoặc giảm phạm vi critical section.

### 12.7. False sharing

Hai thread cập nhật các biến khác nhau nhưng nằm trên cùng cache line có thể làm cache coherence traffic tăng. Đây là vấn đề ở mức layout bộ nhớ và thường cần profiling chuyên sâu mới xác định được.

### 12.8. Determinism

Parallel execution có thể thay đổi thứ tự hoàn thành. Nếu DSL cần output xác định, có thể thu thập kết quả theo input order hoặc áp dụng deterministic reduction.

### 12.9. Backpressure

Producer không nên tạo task nhanh hơn khả năng consumer xử lý vô hạn. Queue cần giới hạn và có policy chờ, từ chối hoặc giảm tốc producer.

## 13. Asynchronous execution và I/O

Nhiều chương trình DSL dành phần lớn thời gian chờ network, database hoặc file. Asynchronous I/O giúp thread không bị giữ chỉ để chờ kết quả.

### 13.1. Blocking I/O

Trong blocking I/O, thread gọi API và chờ đến khi có kết quả hoặc timeout. Cách này đơn giản nhưng số thread có thể tăng theo số request đang chờ.

### 13.2. Non-blocking I/O

Non-blocking I/O đăng ký callback hoặc continuation khi dữ liệu sẵn sàng. Một thread có thể quản lý nhiều connection, nhưng code và error propagation phức tạp hơn.

### 13.3. Future và promise

Future biểu diễn kết quả sẽ có trong tương lai. DSL có thể await future hoặc kết hợp nhiều future để chạy các thao tác độc lập đồng thời.

### 13.4. Structured concurrency

Structured concurrency nhóm task con trong một scope có lifetime rõ. Khi scope kết thúc hoặc bị cancel, runtime có thể hủy task con và chờ chúng kết thúc theo policy.

### 13.5. Cancellation

Cancellation cần được truyền qua DSL runtime đến host API. Nếu task bị cancel nhưng network request tiếp tục chạy, hệ thống vẫn tiêu tốn tài nguyên và có thể tạo side effect không mong muốn.

### 13.6. I/O batching

Gộp nhiều thao tác nhỏ thành batch có thể giảm round trip. Tuy nhiên, batch quá lớn làm tăng memory, latency và chi phí retry.

### 13.7. Connection reuse

Tái sử dụng connection hoặc session có thể giảm handshake và setup cost. Cần giới hạn pool và loại bỏ connection stale.

## 14. Query execution và data processing

Một DSL truy vấn hoặc biến đổi dữ liệu thường tạo execution plan gồm nhiều operator.

### 14.1. Operator pipeline

~~~text
Source
  |
  v
Filter
  |
  v
Map
  |
  v
Aggregate
  |
  v
Sink
~~~

Thứ tự operator ảnh hưởng số record được xử lý và lượng dữ liệu trung gian.

### 14.2. Filter pushdown

Nếu nguồn dữ liệu hỗ trợ filter, engine có thể đẩy điều kiện xuống gần nơi dữ liệu được đọc để giảm lượng dữ liệu truyền về.

### 14.3. Projection pushdown

Chỉ lấy các field cần thiết giúp giảm I/O và memory. Nếu DSL chỉ dùng id và status, không cần tải toàn bộ record có nhiều field lớn.

### 14.4. Join strategy

Nested-loop join có thể phù hợp với một tập nhỏ. Hash join hoặc sort-merge join thường phù hợp hơn với tập dữ liệu lớn trong các điều kiện nhất định.

### 14.5. Index

Index giúp tìm record theo key hoặc predicate hiệu quả hơn so với scan toàn bộ dữ liệu. Index cần được chọn theo workload và có chi phí cập nhật, storage.

### 14.6. Streaming và materialization

Streaming xử lý dữ liệu từng phần tử hoặc theo batch nhỏ. Materialization giữ toàn bộ kết quả trung gian trong memory. Streaming có thể giảm memory footprint nhưng cần quản lý backpressure và lifetime.

### 14.7. Cardinality estimation

Optimizer có thể ước lượng số dòng sau mỗi operator để chọn execution plan. Ước lượng sai có thể dẫn đến join strategy hoặc memory allocation kém.

### 14.8. Lazy evaluation

Lazy evaluation trì hoãn computation đến khi kết quả được yêu cầu. Nó tránh tính phần không dùng nhưng có thể khiến chi phí xuất hiện ở thời điểm truy cập và giữ resource lâu hơn.

## 15. Startup performance và warm-up

Startup time quan trọng với command-line DSL, serverless function, plugin host và workload tạo process ngắn hạn.

### 15.1. Chi phí khởi động

Startup có thể gồm:

- Load runtime và dependency.
- Scan module hoặc plugin.
- Parse DSL.
- Resolve symbol và schema.
- Compile expression.
- Khởi tạo cache.
- Tạo connection pool.
- Load certificate hoặc secret.

### 15.2. Eager và lazy initialization

Eager initialization tạo resource ngay lúc startup, giúp request đầu tiên nhanh hơn nhưng kéo dài thời gian khởi động và có thể tạo resource không dùng.

Lazy initialization tạo resource khi cần, giảm startup cost nhưng làm request đầu tiên chậm hơn.

### 15.3. Warm-up

Runtime JIT có thể cần chạy workload warm-up để compile hot method. Benchmark cần tách thời gian warm-up khỏi steady-state và phản ánh deployment thực tế.

### 15.4. Precompilation

DSL có thể được parse/compile trước khi deploy rồi lưu compiled artifact. Runtime load artifact đó để giảm startup, nhưng cần kiểm tra compiler/runtime compatibility.

### 15.5. Lazy module loading

Chỉ load module khi được tham chiếu có thể giảm startup và memory. Cần tránh nhiều request đồng thời cùng kích hoạt load một module mà không có cơ chế đồng bộ.

## 16. Profiling và tìm bottleneck

Profiling đo nơi runtime dành thời gian hoặc sử dụng tài nguyên.

### 16.1. CPU profiling

CPU profiler cho biết method, function hoặc instruction nào tiêu tốn CPU. Có thể dùng sampling profiler để giảm overhead đo.

### 16.2. Allocation profiling

Allocation profiler chỉ ra nơi tạo nhiều object và loại object chiếm memory. Đây là công cụ quan trọng khi GC pressure cao.

### 16.3. Heap profiling

Heap snapshot giúp tìm object đang được giữ lại, reference path và cấu trúc chiếm dung lượng lớn.

### 16.4. Lock profiling

Lock profiler cho biết thread nào chờ lock và lock nào có contention. Kết quả giúp xác định shared state cần partition hoặc thay đổi ownership.

### 16.5. I/O profiling

Theo dõi thời gian DNS, connect, TLS handshake, database query, file read/write và remote API.

### 16.6. Flame graph

Flame graph thể hiện stack frame và tỷ lệ sample. Frame rộng cho biết phần code chiếm nhiều sample hơn; nó không trực tiếp thể hiện thứ tự thời gian của một request.

### 16.7. Distributed tracing

Tracing liên kết thời gian của các span qua nhiều service. Nó giúp xác định DSL engine chậm ở nội bộ hay đang chờ một dependency bên ngoài.

### 16.8. Instrumentation overhead

Profiler, tracing và logging có thể làm thay đổi workload. Cần đo overhead và dùng sampling hoặc mức chi tiết phù hợp.

## 17. Benchmark runtime

Benchmark giúp so sánh implementation hoặc xác nhận thay đổi hiệu năng.

### 17.1. Microbenchmark

Microbenchmark đo một operation nhỏ như expression evaluation hoặc symbol lookup. Nó hữu ích khi cô lập overhead, nhưng dễ bị ảnh hưởng bởi JIT, dead-code elimination và CPU cache.

### 17.2. Macrobenchmark

Macrobenchmark đo workload gần với ứng dụng thực tế: parse, compile, execute, gọi host API và xử lý dữ liệu.

### 17.3. Representative workload

Benchmark cần đại diện cho workload thật về:

- Kích thước DSL program.
- Số lần thực thi.
- Số biến và function call.
- Kích thước dữ liệu.
- Tỷ lệ cache hit/miss.
- Concurrency.
- Tỷ lệ CPU và I/O.

### 17.4. Warm-up và iteration

Chạy warm-up đủ để runtime ổn định, sau đó đo nhiều iteration. Báo cáo median và percentile thay vì chỉ một lần chạy.

### 17.5. Dead-code elimination

Compiler có thể loại bỏ computation nếu kết quả không được sử dụng. Benchmark phải tiêu thụ kết quả hoặc dùng cơ chế harness phù hợp để tránh đo một chương trình đã bị tối ưu mất.

### 17.6. Environment control

Ghi CPU model, memory, OS, runtime version, power mode, background load và configuration. So sánh trên môi trường khác nhau có thể gây kết luận sai.

### 17.7. Benchmark correctness

Một implementation nhanh hơn nhưng tính kết quả khác không phải tối ưu hợp lệ. Cần xác nhận semantics giống nhau trước khi so thời gian.

## 18. Hiểu và tối ưu tail latency

Tail latency phản ánh các request chậm nhất trong một tập lớn request.

### 18.1. Nguồn tail latency

Tail latency có thể tăng do GC pause, queueing, lock contention, cache miss, DNS lookup, connection establishment, slow database query hoặc retry.

### 18.2. Queueing

Khi request đến nhanh hơn khả năng xử lý, chúng chờ trong queue. Dù service time không đổi, latency tổng vẫn tăng.

### 18.3. Bounded queue

Queue không giới hạn có thể giữ quá nhiều request, tăng memory và khiến hệ thống phục hồi chậm sau overload. Bounded queue giúp tạo backpressure hoặc từ chối sớm.

### 18.4. Deadline

Request nên có deadline tổng. Khi deadline đã hết, tiếp tục thực thi các bước downstream có thể lãng phí tài nguyên.

### 18.5. Hedged request

Trong một số hệ thống đọc có thể retry an toàn, gửi bản sao request đến replica khác sau một khoảng chờ có thể giảm tail latency. Cần hủy request thừa khi một kết quả đã đủ và cân nhắc tải tăng thêm.

## 19. Performance contract cho DSL

DSL có thể mô tả performance expectation để runtime hoặc compiler áp dụng policy.

Ví dụ:

~~~text
execution "pricing-rule" {
    maxDuration = 50ms
    maxMemory = 16MB
    maxCallDepth = 64
    maxIterations = 10000
}
~~~

Các giới hạn này có thể được kiểm tra ở compile time, runtime hoặc cả hai.

### 19.1. Execution budget

Execution budget giới hạn CPU steps, instruction count, memory, recursion depth hoặc thời gian. Nó giúp bảo vệ host application trước script chạy quá lâu.

### 19.2. Cancellation và timeout

Timeout nên dẫn đến cancellation thực sự nếu runtime hỗ trợ. Chỉ ngừng chờ kết quả mà để computation tiếp tục chạy sẽ không giải phóng tài nguyên.

### 19.3. Quota theo tenant

Multi-tenant runtime có thể giới hạn concurrency, CPU budget hoặc request rate theo tenant để một tenant không chiếm hết tài nguyên.

### 19.4. Fair scheduling

Scheduler có thể phân phối thời gian CPU giữa tenant hoặc task class. Fairness giúp tránh starvation nhưng có thể giảm throughput tối đa của một workload đơn lẻ.

### 19.5. Resource accounting

Runtime cần định nghĩa cách tính resource: wall-clock time, CPU time, số instruction, bytes allocated hay số host call. Mỗi metric phản ánh một loại chi phí khác nhau.

## 20. Tối ưu runtime an toàn

Hiệu năng không được đánh đổi semantics, security hoặc khả năng quan sát.

### 20.1. Giữ semantics

Constant folding, expression reordering hoặc parallelization chỉ hợp lệ khi bảo toàn kết quả và side effect theo semantics DSL.

### 20.2. Giới hạn cache

Cache không có giới hạn có thể làm hệ thống hết memory. Mỗi cache cần owner, capacity, invalidation và metric.

### 20.3. Không chia sẻ mutable object tùy tiện

Object được chia sẻ giữa thread cần immutable hoặc có synchronization rõ ràng. Tái sử dụng object có thể tạo data race nếu ownership không được xác định.

### 20.4. Giữ security checks

Không bỏ qua authorization, tenant isolation hoặc input validation chỉ để giảm vài phép kiểm tra. Có thể cache quyết định bảo mật nếu key, scope và invalidation đúng.

### 20.5. Không tối ưu từ một benchmark duy nhất

Thay đổi có thể cải thiện một microbenchmark nhưng làm tăng memory, startup hoặc tail latency của workload khác. Đo nhiều tình huống đại diện.

## 21. Runtime performance trong các loại DSL

Mỗi loại DSL có hot path và bottleneck riêng. Cần chọn metric theo cách DSL được sử dụng.

### 21.1. Rule DSL

Rule engine thường đánh giá nhiều điều kiện trên nhiều record. Hiệu năng phụ thuộc:

- Số rule và số điều kiện.
- Cách index dữ liệu và match rule.
- Thứ tự và priority.
- Short-circuit.
- Cách xử lý state và activation.
- Số lần gọi host function.

Nếu nhiều rule cùng kiểm tra một field, runtime có thể chuẩn hóa hoặc index dữ liệu để giảm lookup lặp.

### 21.2. Query DSL

Query DSL chịu ảnh hưởng của query plan, index, join, filter pushdown, projection, cardinality và network round trip. Tối ưu query thường cần xem execution plan và số dòng thực tế, không chỉ đếm expression trong DSL.

### 21.3. Workflow DSL

Workflow thường dành thời gian chờ I/O, message hoặc timer. Cần quan tâm scheduling, persistence, queue, retry, state serialization và khả năng phục hồi sau restart.

### 21.4. Template DSL

Template engine có thể render nhiều đoạn text. Hot path thường gồm lookup variable, escape, function call, partial/template resolution và string allocation. Compile template một lần và tái sử dụng thường giúp giảm overhead.

### 21.5. Build DSL

Build DSL cần quản lý task graph, incremental execution, dependency resolution, cache và parallel scheduling. Runtime performance thể hiện qua thời gian build tổng, task execution time và mức tái sử dụng cache.

### 21.6. Configuration DSL

Configuration DSL thường parse và validate khi startup. Parse once, immutable configuration model và lazy creation resource có thể giảm startup cost và memory.

## 22. Incremental execution

Incremental execution chỉ tính lại phần bị ảnh hưởng bởi input thay đổi.

### 22.1. Dependency graph

Compiler hoặc build engine xây dựng graph giữa input, expression, task và output. Khi một node thay đổi, engine xác định những node downstream cần chạy lại.

### 22.2. Change detection

Có thể dùng file timestamp, content hash, version hoặc explicit change event. Timestamp nhanh nhưng có thể không phát hiện nội dung thay đổi trong một số trường hợp; hash chính xác hơn nhưng tốn CPU đọc dữ liệu.

### 22.3. Fine-grained invalidation

Nếu chỉ một module thay đổi, không nhất thiết phải compile lại toàn bộ chương trình. Tuy nhiên, dependency graph cần đủ chính xác để tránh giữ kết quả stale.

### 22.4. Incremental state

Runtime có thể lưu intermediate state giữa các lần chạy. State cần version và có cơ chế invalidation khi schema hoặc semantics thay đổi.

### 22.5. Trade-off

Incremental execution giảm computation nhưng tăng complexity của dependency tracking, cache và invalidation. Với chương trình nhỏ, chạy lại toàn bộ có thể đơn giản và đủ nhanh.

## 23. Compilation cache và code cache

Runtime có thể lưu compiled representation để dùng lại.

### 23.1. Cache key đầy đủ

Cache key cần phản ánh mọi yếu tố ảnh hưởng compiled output:

- DSL source content hoặc source revision.
- Language/compiler version.
- Compiler options.
- Imported module versions.
- Host API signature.
- Type schema.
- Target runtime hoặc architecture nếu cần.

Thiếu một thành phần có thể khiến runtime load compiled program không tương thích.

### 23.2. Cache persistence

In-memory cache mất khi process restart. Disk cache hoặc remote cache giúp tái sử dụng qua nhiều lần khởi động, nhưng cần versioning, integrity check và access control.

### 23.3. Cache warm-up

Có thể precompile chương trình quan trọng khi deploy hoặc startup. Cần cân nhắc chi phí warm-up và thời điểm readiness được báo thành công.

### 23.4. Code cache eviction

JIT code và compiled program chiếm memory. Runtime cần giới hạn cache, theo dõi hit rate và loại bỏ entry ít dùng hoặc không còn hợp lệ.

## 24. Runtime isolation và multi-tenancy

Một runtime có thể chạy chương trình từ nhiều tenant hoặc nhiều nhóm. Hiệu năng cần được xem cùng khả năng cô lập tài nguyên.

### 24.1. Shared runtime

Shared runtime tiết kiệm memory và startup vì nhiều program dùng chung engine. Tuy nhiên, tenant có thể cạnh tranh CPU, memory, thread pool và cache.

### 24.2. Isolated runtime

Isolated runtime tách process hoặc worker theo tenant. Isolation tốt hơn nhưng tăng memory, startup và vận hành.

### 24.3. Per-tenant quota

Có thể giới hạn CPU time, memory, concurrent execution, host call và queue length theo tenant.

### 24.4. Noisy neighbor

Một tenant chạy vòng lặp nặng hoặc tạo nhiều request có thể làm các tenant khác chậm. Fair scheduler, bounded queue và quota giúp giảm tác động.

### 24.5. Cache isolation

Cache chứa kết quả hoặc metadata theo tenant cần partition key rõ ràng. Không dùng cache key thiếu tenant identity nếu kết quả có thể phụ thuộc tenant.

### 24.6. Resource leak

Runtime cần đảm bảo cancellation và cleanup cho execution context, stream, transaction, connection và temporary file sau khi task kết thúc hoặc lỗi.

## 25. Kiểm soát vòng lặp và recursion

DSL cho phép người dùng viết loop hoặc recursion cần có giới hạn để tránh chương trình chạy vô hạn.

### 25.1. Loop bound

Có thể đặt giới hạn số iteration hoặc instruction:

~~~text
execution {
    maxIterations = 10000
    maxInstructions = 500000
}
~~~

### 25.2. Recursion depth

Recursion sâu có thể gây stack overflow. Runtime có thể giới hạn call depth hoặc chuyển một số dạng tail recursion thành loop.

### 25.3. Infinite loop detection

Instruction budget hoặc execution deadline có thể dừng loop không tiến triển. Phát hiện loop lặp state phức tạp hơn và không nên được giả định luôn chính xác.

### 25.4. Cooperative cancellation

Một đoạn code chạy lâu cần kiểm tra cancellation ở điểm an toàn. Nếu runtime chỉ kiểm tra timeout bên ngoài mà không thể ngắt execution, tài nguyên vẫn tiếp tục bị sử dụng.

### 25.5. Error semantics

Khi vượt budget, runtime nên trả lỗi có loại riêng như instruction limit exceeded hoặc execution deadline exceeded. Không nên trả kết quả một phần như thể thành công nếu semantics không cho phép.

## 26. String processing và serialization

DSL thường xử lý tên, path, JSON, XML hoặc text template. String operation có thể tạo nhiều allocation và copy dữ liệu.

### 26.1. Repeated concatenation

Nối chuỗi lặp trong loop có thể tạo nhiều intermediate string. Builder hoặc buffer có thể giảm số lần cấp phát và copy.

### 26.2. Encoding

UTF-8, UTF-16 và các encoding khác có chi phí chuyển đổi. Nếu dữ liệu đi qua nhiều lớp, tránh encode/decode lặp không cần thiết.

### 26.3. JSON và XML

Parser streaming có thể xử lý document lớn mà không cần materialize toàn bộ tree. DOM dễ thao tác nhưng có memory footprint lớn hơn.

### 26.4. Schema-aware serialization

Nếu schema đã biết, serializer có thể dùng field index và type đã compile thay vì lookup tên field động.

### 26.5. Buffer size

Buffer quá nhỏ gây nhiều lần grow/copy; buffer quá lớn gây lãng phí memory. Cần chọn theo phân phối kích thước dữ liệu thực tế.

## 27. Performance testing và regression tracking

Hiệu năng cần được theo dõi qua nhiều phiên bản runtime, không chỉ ở thời điểm phát triển.

### 27.1. Baseline

Lưu baseline cho startup, parse, compile, execution, memory và throughput trên workload chuẩn.

### 27.2. Regression threshold

Có thể cảnh báo khi latency hoặc allocation tăng vượt ngưỡng. Ngưỡng cần tính đến độ nhiễu benchmark và khác biệt môi trường.

### 27.3. Separate test suites

Tách microbenchmark, integration benchmark và end-to-end benchmark. Mỗi loại trả lời câu hỏi khác nhau.

### 27.4. Compare distributions

So sánh median, p95, p99 và throughput. Không chỉ so một lần chạy hoặc một average.

### 27.5. Track memory

Theo dõi heap peak, allocation rate, retained heap và GC pause. Một bản release nhanh hơn nhưng tăng gấp đôi memory có thể không phù hợp môi trường giới hạn.

### 27.6. Performance budget

Có thể đặt budget cho các thao tác quan trọng, chẳng hạn startup dưới một ngưỡng, p95 evaluation dưới một ngưỡng hoặc allocation trên mỗi rule evaluation không vượt giới hạn.

## 28. Quy trình tối ưu runtime có hệ thống

Một quy trình tối ưu nên bắt đầu từ mục tiêu và dữ liệu đo:

1. Xác định user-visible symptom hoặc resource constraint.
2. Chọn workload đại diện và metric liên quan.
3. Đo baseline trong môi trường ổn định.
4. Profile để tìm bottleneck thực tế.
5. Xác định nguyên nhân và giả thuyết.
6. Thay đổi một yếu tố có phạm vi rõ.
7. Kiểm tra semantics và correctness.
8. Benchmark lại trên cùng workload.
9. So sánh latency, throughput, memory và startup.
10. Theo dõi regression sau khi đưa vào sử dụng.

### 28.1. Amdahl's law

Amdahl's law mô tả giới hạn tăng tốc khi chỉ một phần chương trình được cải thiện. Nếu phần có thể tối ưu chỉ chiếm tỷ lệ nhỏ tổng thời gian, tăng tốc rất lớn ở phần đó vẫn chỉ tạo cải thiện nhỏ cho toàn hệ thống.

~~~text
Speedup = 1 / ((1 - P) + P / S)
~~~

Trong đó P là tỷ lệ thời gian có thể cải thiện và S là mức tăng tốc của phần đó.

### 28.2. Ví dụ

Nếu parser chỉ chiếm 5% thời gian request, làm parser nhanh gấp 10 lần chỉ giảm một phần nhỏ latency tổng. Nếu 70% thời gian đang chờ database, tối ưu evaluator có thể không tạo thay đổi đáng kể.

### 28.3. Tránh premature optimization

Tối ưu quá sớm có thể làm code khó hiểu và tăng chi phí bảo trì. Trước khi có profile, ưu tiên semantics rõ, representation đơn giản và instrumentation đủ dùng.

## 29. Ví dụ: tối ưu một rule evaluator

Giả sử DSL có rule:

~~~text
rule EligibleCustomer {
    when customer.active
     and customer.balance >= 100
     and customer.region in allowedRegions
    then approve()
}
~~~

Một evaluator đơn giản có thể thực hiện:

1. Lookup tên customer.
2. Lookup field active.
3. Convert value sang boolean.
4. Lookup balance.
5. Convert balance sang numeric.
6. So sánh với 100.
7. Lookup allowedRegions.
8. Thực hiện membership test.
9. Resolve function approve.
10. Gọi host function.

Nếu rule chạy hàng triệu lần, các lookup và conversion lặp lại có thể tạo overhead.

### 29.1. Compile identifier thành slot

Compiler resolve customer.active thành field accessor hoặc slot đã biết thay vì lookup string name ở mỗi lần chạy.

### 29.2. Specialize comparison

Nếu balance có type Decimal, compiler có thể tạo phép so sánh Decimal chuyên biệt và tránh dynamic type dispatch.

### 29.3. Short-circuit

Nếu customer.active là false, không cần đọc balance hoặc allowedRegions.

### 29.4. Precompute membership structure

Nếu allowedRegions không đổi trong nhiều lần đánh giá, có thể chuẩn bị hash set một lần thay vì quét list ở mỗi evaluation.

### 29.5. Resolve call target

Nếu approve luôn trỏ đến cùng host function, resolve binding lúc prepare thay vì tìm tên function mỗi lần.

### 29.6. Đo kết quả

Benchmark cần đo số rule evaluation mỗi giây, latency percentile, allocation trên mỗi evaluation và memory của compiled program. Chỉ giữ specialization nếu kết quả có cải thiện trên workload đại diện.

## 30. Ví dụ: tối ưu query pipeline

DSL:

~~~text
query LargeOrders {
    from orders
    map enrichWithCustomer
    where total >= 10000
    select id, total, customerName
}
~~~

Nếu enrichWithCustomer gọi database cho từng order, query có thể tạo N+1 query.

Một execution plan tốt hơn có thể:

1. Đẩy điều kiện total xuống nguồn dữ liệu.
2. Chỉ chọn id, total và customer key cần thiết.
3. Batch load customer data.
4. Join dữ liệu trong memory hoặc tại database.
5. Chỉ materialize các field được chọn.

~~~text
Orders source
    |
    v
Filter total >= 10000
    |
    v
Project required fields
    |
    v
Batch customer lookup
    |
    v
Join and select
    |
    v
Result stream
~~~

Điểm cải thiện đến từ giảm round trip và giảm dữ liệu xử lý, không nhất thiết từ việc thay đổi tốc độ của một expression.

## 31. Các sai lầm thường gặp

**Chỉ đo average latency.** Average có thể che giấu p95/p99 rất cao và request bị timeout.

**Tối ưu parser trong khi runtime chậm vì I/O.** Cần profile tổng luồng để tìm phần chiếm thời gian thực tế.

**Parse hoặc compile lại ở mỗi request.** Nếu source không đổi, có thể chuẩn bị một lần và tái sử dụng representation.

**Resolve tên động ở hot path.** Compile identifier và function binding thành reference đã resolve khi semantics cho phép.

**Tạo quá nhiều object tạm.** Allocation rate cao làm tăng GC pressure; dùng allocation profiler để tìm nguồn.

**Cache không có invalidation.** Cache stale có thể tạo kết quả sai và cache không giới hạn có thể làm cạn memory.

**Tăng thread pool để chữa mọi vấn đề.** Pool lớn có thể tăng context switch, contention và overload dependency.

**Parallelize công việc quá nhỏ.** Scheduling overhead có thể lớn hơn thời gian xử lý mỗi task.

**Retry không giới hạn.** Retry có thể khuếch đại sự cố và tạo side effect lặp.

**Dùng blocking I/O trong worker pool nhỏ.** Thread có thể bị giữ khi chờ network và làm queue tăng.

**Bỏ qua cancellation.** Task đã hết deadline nhưng vẫn chạy sẽ tiếp tục chiếm CPU, memory hoặc connection.

**Benchmark không warm-up.** JIT, class loading và cache state có thể làm kết quả không đại diện.

**Benchmark không tiêu thụ kết quả.** Compiler có thể loại bỏ computation và làm số đo sai.

**Đánh đổi correctness để lấy tốc độ.** Optimization phải giữ nguyên semantics, security và side-effect guarantees.

## 32. Ghi nhớ

- Runtime performance gồm latency, throughput, CPU, memory, allocation, GC, I/O và tail latency.
- Tách parse, semantic analysis, preparation, execution và host integration khi phân tích chi phí.
- Interpreter, bytecode VM, native compilation và JIT có trade-off khác nhau về startup, throughput và complexity.
- Dispatch, function lookup và boundary crossing có thể tạo overhead đáng kể trong hot path.
- Constant folding, constant propagation, dead code elimination và common subexpression elimination giúp giảm công việc runtime khi semantics cho phép.
- Type information và specialized data representation có thể giảm dynamic dispatch, boxing và allocation.
- Object lifetime, memory layout và GC ảnh hưởng latency cũng như footprint.
- Cache cần key đầy đủ, invalidation, capacity và metric.
- Concurrency cần bounded queue, backpressure, cancellation và semantics rõ cho shared state.
- Async I/O giúp thread không bị giữ trong lúc chờ, nhưng cần quản lý future, cancellation và resource lifetime.
- Query optimizer có thể dùng filter/projection pushdown, index, join strategy và streaming.
- Startup, warm-up và steady-state cần được đo riêng.
- Profiling giúp tìm CPU, allocation, lock, I/O và memory bottleneck.
- Benchmark phải dùng workload đại diện, warm-up, nhiều iteration và kiểm tra correctness.
- Performance budget và resource quota giúp bảo vệ host application và multi-tenant runtime.
- Tối ưu cần dựa trên profile, đo lại và theo dõi regression.

## 33. Câu hỏi tự kiểm tra

1. Runtime performance gồm những chỉ số nào? Phân biệt latency và throughput.
2. Vì sao p95 và p99 có thể hữu ích hơn average latency?
3. Phân biệt parse time, compilation time, startup time và steady-state execution.
4. So sánh tree-walking interpreter, bytecode VM và JIT compilation.
5. Stack VM và register VM có trade-off nào?
6. Dispatch overhead là gì? Instruction fusion giúp giảm chi phí như thế nào?
7. Constant folding, dead code elimination và short-circuit evaluation có tác dụng gì?
8. Type stability và specialized collection ảnh hưởng hiệu năng ra sao?
9. Vì sao reflection và host interop có thể làm chậm runtime?
10. Allocation rate cao ảnh hưởng garbage collection như thế nào?
11. Cache key và invalidation cần được thiết kế ra sao?
12. Phân biệt concurrency và parallelism. Vì sao thread pool quá lớn có thể làm hiệu năng giảm?
13. Backpressure và bounded queue giúp bảo vệ runtime như thế nào?
14. Blocking I/O khác non-blocking I/O ở điểm nào?
15. Filter pushdown và projection pushdown giảm chi phí query ra sao?
16. CPU profiler, allocation profiler và lock profiler cung cấp thông tin gì?
17. Microbenchmark và macrobenchmark khác nhau như thế nào?
18. Tail latency có thể tăng vì những nguyên nhân nào?
19. Performance budget giúp bảo vệ host application và multi-tenant runtime ra sao?
20. Hãy đề xuất quy trình đo và tối ưu một rule evaluator đang chạy chậm.
