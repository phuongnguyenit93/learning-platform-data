# Giới hạn quy mô

## 1. Giới hạn quy mô trong DSL là gì?

Một DSL (*Domain-Specific Language*) có thể được dùng để mô tả cấu hình, biểu thức, quy tắc, workflow, truy vấn hoặc chương trình chạy trong một ứng dụng. Khi số lượng người dùng, chương trình, dữ liệu và execution tăng lên, hệ thống cần kiểm soát lượng tài nguyên mà mỗi hoạt động có thể tiêu thụ.

**Giới hạn quy mô (*scale limits*)** là tập hợp các ngưỡng và chính sách giới hạn kích thước, độ phức tạp, tốc độ, mức đồng thời và mức tiêu thụ tài nguyên của DSL toolchain và runtime. Mục tiêu là giữ cho hệ thống có thể dự đoán, công bằng, an toàn và duy trì chất lượng dịch vụ khi tải tăng hoặc khi một chương trình có hành vi bất thường.

Một DSL có thể đặt giới hạn ở nhiều giai đoạn:

~~~text
Source input
    |
    v
Parsing and AST construction
    |
    v
Compilation / validation
    |
    v
Runtime evaluation
    |
    v
Data access and external calls
    |
    v
Result serialization
~~~

Mỗi giai đoạn có loại chi phí và giới hạn riêng. Ví dụ:
- Source quá lớn có thể làm parser tiêu thụ nhiều memory.
- Expression lồng quá sâu có thể làm tăng stack usage.
- Vòng lặp không có điều kiện dừng có thể chiếm CPU vô hạn.
- Một rule có thể tạo hàng triệu activation.
- Một workflow có thể mở quá nhiều nhánh song song.
- Một DSL program có thể gọi service bên ngoài liên tục.
- Kết quả quá lớn có thể làm cạn memory hoặc băng thông.

Giới hạn quy mô không chỉ là cấu hình một con số tối đa. Một thiết kế tốt cần định nghĩa giới hạn áp dụng ở đâu, cách đo, phạm vi tính quota, hành vi khi chạm ngưỡng, cách giải phóng tài nguyên và cách quan sát việc sử dụng.

## 2. Các chiều quy mô cần kiểm soát

Có thể chia scale limits thành các nhóm:

| Chiều quy mô | Ví dụ giới hạn | Rủi ro nếu không kiểm soát |
|---|---|---|
| Source size | Số byte, ký tự, file, dòng | Parser và editor quá tải |
| Syntax/model complexity | Token, AST node, nesting depth | Compile chậm, stack overflow |
| Compilation | Thời gian, memory, số module | Build queue bị nghẽn |
| Evaluation | Instruction count, CPU time, deadline | Một chương trình chiếm CPU quá lâu |
| Memory | Heap, stack, object count | Out-of-memory |
| Iteration | Loop count, recursion depth | Vòng lặp vô hạn |
| Data size | Collection size, payload, result size | Memory và serialization tăng đột biến |
| Concurrency | Execution, thread, task đang chạy | Saturation và starvation |
| External resources | HTTP, database, filesystem, plugin calls | Cạn connection hoặc quota downstream |
| Throughput | Request per second, operation rate | Quá tải hệ thống |
| Queueing | Queue depth, wait time | Latency tăng và backlog không giới hạn |
| Tenant usage | Quota theo tenant/project | Một tenant ảnh hưởng tenant khác |

Không phải mọi DSL đều cần mọi giới hạn. Một DSL chỉ dùng để validate file cấu hình có profile khác với DSL cho phép chạy workflow, gọi API hoặc xử lý tập dữ liệu lớn.

### 2.1. Giới hạn theo từng lớp

Nên tách:
- **Editor limits:** giữ giao diện phản hồi nhanh khi người dùng đang gõ.
- **Parser/compiler limits:** ngăn source hoặc model quá lớn làm cạn tài nguyên build.
- **Runtime limits:** giới hạn một execution.
- **Service limits:** giới hạn tổng tải trên một process hoặc cluster.
- **Tenant limits:** bảo đảm một tenant không chiếm hết capacity.
- **Platform limits:** bảo vệ hạ tầng và các service dùng chung.

Một giới hạn ở lớp runtime không thể bảo vệ parser nếu source đã làm parser cạn memory trước khi execution bắt đầu. Mỗi giai đoạn cần ngưỡng phù hợp.

## 3. Hard limits, soft limits, quotas và budgets

Các loại giới hạn khác nhau về mục đích và hành vi.

### 3.1. Hard limit

Hard limit là ngưỡng không được vượt qua. Khi chạm giới hạn, hệ thống từ chối thao tác, dừng execution hoặc yêu cầu chia nhỏ công việc.

Ví dụ:
- Source file tối đa 2 MB.
- Recursion depth tối đa 100.
- Một execution tối đa 10 giây CPU.
- Một tenant tối đa 50 execution đồng thời.

Hard limit bảo vệ tài nguyên nhưng có thể làm gián đoạn công việc hợp lệ nếu ngưỡng quá thấp.

### 3.2. Soft limit và warning threshold

Soft limit là ngưỡng cảnh báo hoặc kích hoạt hành vi giảm tải trước hard limit.

Ví dụ:
- Cảnh báo khi execution dùng 80% memory budget.
- Hiển thị warning khi process graph có hơn 500 node.
- Gợi ý pagination khi query trả hơn 1.000 record.
- Cảnh báo tenant dùng 80% quota ngày.

Soft limit không nhất thiết dừng operation. Nó giúp người dùng và operator có thời gian điều chỉnh.

### 3.3. Quota

Quota giới hạn lượng tài nguyên được phép tiêu thụ trong một phạm vi hoặc khoảng thời gian:
- 10.000 execution mỗi ngày.
- 100.000 external API calls mỗi tháng.
- 5 GB artifact storage mỗi project.
- 500.000 rule evaluations mỗi giờ.

Quota thường được tính cộng dồn và có chu kỳ reset hoặc refill.

### 3.4. Budget

Budget là ngân sách tài nguyên dành cho một execution hoặc một đơn vị công việc. Budget có thể gồm nhiều loại chi phí:

~~~text
Execution budget
  wall-clock time: 30 seconds
  CPU time:        5 seconds
  memory:          128 MB
  instructions:    2,000,000
  external calls:  20
  result size:     5 MB
~~~

Khi một loại budget cạn, runtime có thể dừng execution ngay cả khi các budget khác còn dư.

### 3.5. Rate limit

Rate limit giới hạn tốc độ request hoặc operation trong một cửa sổ thời gian. Nó khác quota tổng: một client có thể còn quota tháng nhưng vẫn bị giới hạn burst trong một giây.

### 3.6. Concurrency limit

Concurrency limit giới hạn số hoạt động đang chạy đồng thời. Nó không giới hạn tổng số hoạt động có thể chạy trong ngày, mà kiểm soát capacity tại một thời điểm.

### 3.7. Phân biệt các khái niệm

| Cơ chế | Đo cái gì? | Phạm vi điển hình |
|---|---|---|
| Hard limit | Ngưỡng tối đa | Một file, execution hoặc request |
| Soft limit | Ngưỡng cảnh báo | Một execution hoặc tenant |
| Quota | Tổng lượng được dùng | Tenant/project theo kỳ |
| Budget | Chi phí của một đơn vị công việc | Một execution/job |
| Rate limit | Tốc độ | Principal, tenant hoặc endpoint |
| Concurrency limit | Số hoạt động đang chạy | Worker, tenant hoặc cluster |

Một hệ thống thường kết hợp các cơ chế này. Ví dụ một tenant có quota 100.000 execution mỗi ngày, rate limit 20 request mỗi giây và concurrency limit 10 execution.

## 4. Giới hạn source và đầu vào

Giới hạn đầu vào là lớp bảo vệ đầu tiên vì parser và compiler phải xử lý dữ liệu trước khi biết semantics đầy đủ.

### 4.1. Source size

Có thể giới hạn:
- Byte size của mỗi file.
- Tổng byte size của project.
- Số file được import.
- Số dòng hoặc ký tự.
- Kích thước một literal.
- Kích thước comment hoặc metadata.
- Tổng kích thước nội dung được include.

Cần phân biệt byte size với số ký tự. UTF-8 dùng số byte khác nhau cho các ký tự Unicode; một file có 1 MB không nhất thiết có một triệu ký tự.

### 4.2. File count và include depth

Một DSL cho phép include/import file cần giới hạn:
- Số file import trực tiếp.
- Tổng số file trong dependency graph.
- Độ sâu include.
- Kích thước tổng source sau khi resolve include.
- Số lần một module được tham chiếu.
- Số vòng dependency.

Nếu không có giới hạn, một project có thể tạo graph include rất lớn hoặc chuỗi import sâu làm tăng thời gian compile.

### 4.3. Token và AST size

Parser có thể giới hạn:
- Tổng token.
- Số AST node.
- Số child trên một node.
- Độ sâu cây.
- Số declaration.
- Số expression.
- Số annotation hoặc metadata entries.

AST node count thường là chỉ số hữu ích hơn source length khi dự đoán memory và semantic analysis cost, nhưng không phải node nào cũng có chi phí bằng nhau.

### 4.4. Nesting depth

Ví dụ một expression có thể lồng nhiều tầng:

~~~text
((((((((value))))))))
~~~

Hoặc object literal có nhiều cấp. Nesting depth lớn có thể gây stack overflow trong parser, visitor hoặc serializer đệ quy.

Nên có giới hạn nesting riêng cho:
- Parentheses.
- Object/array literals.
- Blocks.
- Function calls.
- Type declarations.
- Import/include graph.
- Nested workflow/subprocess.

### 4.5. Literal size

Một string hoặc binary literal cực lớn có thể chiếm memory ngay khi parser tạo token hoặc AST node. Nên giới hạn:
- String length.
- Numeric literal digits.
- Binary/encoded data size.
- Regex pattern length.
- Inline document size.

Với dữ liệu lớn, nên dùng external reference hoặc file upload có streaming thay vì nhúng trực tiếp vào DSL source.

### 4.6. Input validation trước parsing

Có thể kiểm tra byte limit, encoding và file count trước khi khởi tạo parser. Không nên đọc toàn bộ input vào memory rồi mới kiểm tra kích thước nếu nguồn có thể rất lớn.

## 5. Giới hạn compilation và semantic analysis

Compile phase có thể tiêu thụ CPU và memory để parse, resolve symbols, infer types, build dependency graph và generate artifacts.

### 5.1. Compilation time

Có thể đặt deadline cho:
- Parse.
- Name resolution.
- Type checking.
- Dependency analysis.
- Optimization.
- Code generation.

Nên đo từng phase để biết bottleneck. Một tổng timeout duy nhất có thể dừng compilation nhưng không giải thích phase nào tốn thời gian.

### 5.2. Module graph size

Một project DSL có thể chứa nhiều module và dependency. Giới hạn nên xét:
- Số module.
- Số dependency edges.
- Dependency depth.
- Số symbol.
- Số reference.
- Số generated artifact.
- Số lần generic/type instantiation nếu có.

### 5.3. Cycle và recursive definitions

Một số dependency cycle là hợp lệ, một số không. Ví dụ function recursion có thể được hỗ trợ, nhưng import cycle có thể bị cấm.

Cần phân loại cycle theo semantics:
- Import cycle.
- Type reference cycle.
- Function call cycle.
- Data dependency cycle.
- Workflow cycle.

Không nên dùng một quy tắc cycle chung cho mọi graph.

### 5.4. Complexity budgets

Compiler có thể giới hạn số phép so sánh, số bước type inference, số lần overload resolution hoặc số node phải tối ưu. Một expression có rất nhiều overload candidate có thể tốn thời gian lớn dù source không dài.

### 5.5. Incremental compilation

Khi một file thay đổi, compiler có thể chỉ phân tích lại module bị ảnh hưởng. Incremental compilation giảm latency nhưng cần dependency tracking chính xác và invalidation đúng.

Cache compile result cần gắn với:
- Source content hash.
- Compiler version.
- DSL language version.
- Dependency versions.
- Compilation options.
- Relevant environment configuration.

### 5.6. Compile cache limits

Cache cũng tiêu thụ memory và disk. Cần giới hạn:
- Tổng cache size.
- Số entry.
- TTL hoặc eviction policy.
- Kích thước một entry.
- Số compilation đồng thời.

Cache không được giữ artifact lỗi thời hoặc dùng lẫn kết quả giữa tenant có policy khác nhau.

## 6. Giới hạn độ phức tạp của biểu thức

Không phải mọi expression có cùng chi phí. Một biểu thức đơn giản có thể được đánh giá nhanh, trong khi biểu thức chứa nhiều phép biến đổi, regex hoặc truy vấn lồng nhau có thể tốn tài nguyên đáng kể.

### 6.1. Expression node count

Có thể giới hạn số node trong một expression hoặc tổng expression nodes trong một program.

### 6.2. Call depth

Function hoặc operation call có thể lồng nhau. Cần giới hạn call depth và phát hiện recursion cycle nếu ngôn ngữ không hỗ trợ recursion an toàn.

### 6.3. Recursion depth

Nếu DSL cho phép recursive function, giới hạn recursion depth hoặc dùng execution budget để tránh stack growth không kiểm soát.

Có thể dùng iterative evaluation hoặc explicit stack để giảm phụ thuộc vào call stack của host runtime.

### 6.4. Regex complexity

Regex có thể có worst-case runtime rất lớn với một số pattern và input. Cần:
- Giới hạn pattern length.
- Giới hạn input length.
- Dùng engine có timeout hoặc complexity guarantees phù hợp.
- Tránh cho phép feature nguy hiểm nếu không cần.
- Không chạy regex không giới hạn trên request thread.

### 6.5. Sorting và aggregation

Sorting thường có chi phí tăng theo số phần tử; aggregation có thể tạo intermediate collection lớn. Nên giới hạn input cardinality, số group và kích thước intermediate result.

### 6.6. Query complexity

Nếu DSL hỗ trợ query, cần kiểm soát:
- Join count.
- Join fan-out.
- Scan size.
- Nested query depth.
- Sort và group-by.
- Result rows.
- Query execution time.
- Query plan cost nếu database hỗ trợ.

Một câu query ngắn vẫn có thể scan hàng tỷ record. Source length không phải thước đo đủ cho runtime cost.

## 7. Giới hạn runtime evaluation

Runtime cần kiểm soát lượng công việc mà một chương trình được phép thực hiện.

### 7.1. Wall-clock timeout

Wall-clock timeout giới hạn thời gian thực tế từ lúc bắt đầu đến khi kết thúc, bao gồm thời gian chờ I/O và scheduler.

Ví dụ một execution có deadline 30 giây. Khi deadline hết, runtime yêu cầu hủy các task đang chạy và trả trạng thái timeout.

### 7.2. CPU time

CPU time đo thời gian processor thực sự dành cho execution. Nó khác wall-clock time: chương trình có thể chờ network 20 giây nhưng chỉ dùng CPU vài millisecond.

CPU budget hữu ích để phát hiện computation quá nặng mà không nhầm với I/O latency.

### 7.3. Instruction/fuel budget

Một interpreter có thể đếm số instruction hoặc evaluation steps:

~~~text
remainingFuel = initialFuel

before each instruction:
    remainingFuel -= instructionCost

    if remainingFuel < 0:
        stop with RESOURCE_LIMIT_EXCEEDED
~~~

Fuel model giúp giới hạn computation độc lập với tốc độ máy. Tuy nhiên, instruction có chi phí khác nhau; một operation native có thể tốn nhiều CPU hơn một instruction đơn giản.

### 7.4. Per-operation cost

Operation có thể khai báo cost hoặc budget riêng:
- String transformation.
- Regex match.
- Database query.
- Network request.
- Image/document processing.
- Graph traversal.

Một phép gọi external service cần tính cả latency, retry và response processing.

### 7.5. Cooperative cancellation

Runtime cần cho phép execution kiểm tra cancellation/deadline tại các điểm an toàn. Nếu operation native chạy lâu mà không hỗ trợ interruption, timeout bên ngoài không đảm bảo tài nguyên được giải phóng ngay.

### 7.6. Cancellation propagation

Khi execution bị hủy, cancellation cần lan tới:
- Child tasks.
- Async operations.
- Database queries.
- HTTP requests.
- Workflow timers nếu có thể hủy.
- Temporary resources.

Không nên chỉ trả timeout cho client trong khi background operation vẫn chạy vô thời hạn.

## 8. Giới hạn vòng lặp và số lần thực thi

Vòng lặp là nguồn tiêu thụ CPU và memory phổ biến.

### 8.1. Maximum iterations

Có thể giới hạn số lần lặp của một loop:

~~~text
for each item in items
    limit 10000
{
    process(item)
}
~~~

Cú pháp minh họa. Nếu vượt ngưỡng, runtime phải trả diagnostic hoặc execution error có vị trí source phù hợp.

### 8.2. Nested loops

Hai vòng lặp mỗi vòng 10.000 lần có thể tạo tới 100 triệu lần lặp. Vì vậy cần xét tổng work budget, không chỉ giới hạn riêng từng loop.

### 8.3. Unbounded while loops

Một vòng lặp while phụ thuộc dữ liệu runtime có thể không kết thúc. Nên kết hợp:
- Loop iteration limit.
- Execution deadline.
- Fuel budget.
- Cancellation.
- Static warning khi điều kiện không có dấu hiệu tiến triển nếu phân tích được.

### 8.4. Retry loops

Retry khác loop nghiệp vụ. Cần giới hạn:
- Maximum attempts.
- Total retry duration.
- Backoff.
- Jitter.
- Retryable error classes.
- Idempotency.
- Retry budget theo request hoặc tenant.

Nếu nhiều tầng cùng retry, số lần gọi downstream có thể nhân lên. Cần có một retry budget tổng.

### 8.5. Rule firing và workflow transitions

Rule engine có thể fire lặp; workflow có thể tạo transition liên tục. Cần giới hạn:
- Maximum rule firings.
- Maximum transitions per instance.
- Maximum event reprocessing.
- Maximum retries per task.
- Maximum loop iterations per workflow run.

### 8.6. Infinite-loop detection

Có thể phát hiện một số loop không tiến triển, chẳng hạn state không đổi sau mỗi iteration. Tuy nhiên, static detection không thể chứng minh mọi loop sẽ kết thúc. Runtime budget vẫn cần thiết.

## 9. Giới hạn memory và object allocation

Memory limit bảo vệ runtime khỏi một execution hoặc tenant chiếm toàn bộ heap.

### 9.1. Per-execution memory budget

Có thể giới hạn:
- Tổng allocated bytes.
- Số object.
- Collection size.
- Buffer size.
- AST hoặc runtime object retention.
- Maximum stack depth.

Nếu nhiều execution dùng chung process heap, cần có cơ chế accounting hoặc isolation đủ tin cậy. Một counter ở mức DSL không thể tự đo chính xác mọi allocation của host code.

### 9.2. Collection limits

Các collection có thể phát triển rất nhanh:
- Array/list length.
- Map entries.
- Set elements.
- Group-by buckets.
- Result rows.
- Queue messages.
- Workflow child instances.

Nên giới hạn cardinality và có API pagination/streaming cho dữ liệu lớn.

### 9.3. String và buffer limits

String concatenation lặp có thể tạo nhiều intermediate objects. Binary buffer có thể giữ memory ngoài heap. Cần giới hạn cả logical length và byte allocation.

### 9.4. Stack depth

Deep recursion hoặc nested evaluation có thể gây stack overflow. Giới hạn call depth và nesting depth nên được áp dụng trước khi host runtime gặp lỗi nghiêm trọng.

### 9.5. Memory reservation và accounting

Nếu runtime hỗ trợ, có thể reserve budget trước một operation lớn. Với native operation không thể đo chính xác, có thể dùng estimate cộng với hard process/container memory limit.

### 9.6. Memory release

Khi execution kết thúc hoặc bị hủy, runtime cần:
- Giải phóng reference tới context.
- Hủy child tasks.
- Đóng stream.
- Trả buffer về pool.
- Release semaphore/connection.
- Xóa temporary artifacts theo lifecycle.

Không giữ execution context lâu hơn cần thiết chỉ vì trace hoặc cache.

## 10. Giới hạn dữ liệu và payload

Kích thước dữ liệu có thể lớn hơn source nhiều lần.

### 10.1. Input payload

API hoặc workflow input nên có:
- Maximum body size.
- Maximum field length.
- Maximum array length.
- Maximum nesting depth.
- Maximum file count.
- Maximum upload size.

### 10.2. Result size

Một query hoặc expression có thể trả collection rất lớn. Cần giới hạn:
- Tổng response bytes.
- Số result items.
- Một item tối đa bao nhiêu bytes.
- Số nested levels.
- Serialization time.

Nếu kết quả vượt ngưỡng, có thể yêu cầu pagination, streaming hoặc lưu artifact rồi trả reference.

### 10.3. Intermediate data

Một pipeline có thể tạo intermediate dataset lớn hơn input. Chỉ giới hạn input và output cuối chưa đủ. Cần budget cho:
- Intermediate collection.
- Join result.
- Sort buffer.
- Temporary file.
- Materialized view.
- Aggregation state.

### 10.4. Streaming

Streaming xử lý dữ liệu theo chunk thay vì giữ toàn bộ trong memory. Cần quy định:
- Chunk size.
- Maximum stream duration.
- Backpressure.
- Cancellation.
- Maximum total bytes.
- Idle timeout.
- Error behavior sau khi đã gửi một phần kết quả.

### 10.5. Compression

Compressed payload nhỏ có thể bung ra rất lớn. Cần giới hạn cả compressed size và decompressed size để tránh compression bomb.

## 11. Concurrency và parallelism limits

Concurrency controls số công việc đồng thời, trong khi parallelism là số công việc thực sự chạy song song.

### 11.1. Per-execution parallelism

Một DSL workflow có thể fork nhiều nhánh. Cần giới hạn số child task đồng thời để tránh một instance tạo hàng nghìn worker.

### 11.2. Global concurrency

Runtime có thể đặt giới hạn tổng execution đang chạy. Khi đạt ngưỡng, request mới có thể được queue, rejected hoặc shed theo policy.

### 11.3. Per-tenant concurrency

Quota theo tenant ngăn một khách hàng chiếm toàn bộ worker pool.

Ví dụ:
- Global: 500 execution đồng thời.
- Tenant A: tối đa 20.
- Tenant B: tối đa 50.
- Background jobs: tối đa 100 trong pool riêng.

Các con số chỉ là minh họa; giới hạn thực tế cần dựa trên capacity và service objective.

### 11.4. Thread và task creation

Không nên cho DSL program tạo thread tùy ý. Runtime nên quản lý task thông qua bounded executor hoặc scheduler có queue limit.

### 11.5. Fan-out

Một operation gọi nhiều child operation có thể tạo fan-out lớn. Nếu mỗi tầng nhân số child, tổng request downstream tăng theo cấp số nhân.

Cần giới hạn:
- Fan-out per node.
- Total child tasks.
- Maximum workflow depth.
- Total downstream calls.
- Maximum parallel branches.

### 11.6. Deadlock và resource contention

Concurrency cao có thể tạo lock contention hoặc deadlock. Runtime cần timeout, lock ordering hoặc cơ chế concurrency control phù hợp. Chỉ tăng thread count không giải quyết được contention.

## 12. Giới hạn external calls và tài nguyên dùng chung

DSL có thể gọi database, HTTP service, filesystem, message broker hoặc plugin. Đây là các tài nguyên có capacity độc lập.

### 12.1. Network calls

Cần giới hạn:
- Số outbound calls mỗi execution.
- Số calls đồng thời.
- Request/response bytes.
- Connect timeout.
- Read timeout.
- Total deadline.
- Retry count.
- Allowed destinations.

### 12.2. Database operations

Cần giới hạn:
- Query count.
- Query duration.
- Rows scanned/returned nếu đo được.
- Connection pool usage.
- Transaction duration.
- Lock wait.
- Batch size.
- Write volume.

Không nên cho DSL tùy ý tạo connection mới hoặc chạy query không giới hạn.

### 12.3. Filesystem

Có thể giới hạn:
- Root directories được phép.
- Số file mở đồng thời.
- Tổng bytes đọc/ghi.
- File size.
- Temporary storage.
- Directory traversal depth.
- Operation count.

### 12.4. Plugin và host operations

Mỗi plugin operation nên có:
- Timeout.
- Concurrency cap.
- Input/output size.
- Resource cost.
- Permission requirement.
- Retry policy.
- Cancellation support.

Một plugin chậm hoặc lỗi không nên giữ worker của toàn runtime vô thời hạn.

### 12.5. Circuit breaker

Circuit breaker tạm ngừng gọi downstream khi lỗi vượt ngưỡng. Nó giúp tránh tiếp tục gửi request đến dependency đang suy giảm.

Circuit breaker không thay thế timeout, retry budget hoặc rate limit. Cần xác định state closed/open/half-open và cách phục hồi.

## 13. Rate limiting và quota management

Rate limiting bảo vệ service trước burst và giữ fairness giữa client.

### 13.1. Token bucket

Token bucket cho phép burst trong giới hạn bucket và refill theo tốc độ xác định.

~~~text
bucket capacity = 100 tokens
refill rate     = 10 tokens/second

each request:
    if enough tokens:
        consume token
        allow
    else:
        reject or queue
~~~

### 13.2. Leaky bucket

Leaky bucket xử lý request theo tốc độ tương đối ổn định, giúp làm phẳng burst. Phù hợp khi downstream cần throughput đều.

### 13.3. Fixed window

Fixed window đếm request trong từng cửa sổ thời gian. Đơn giản nhưng có thể tạo burst ở ranh giới giữa hai cửa sổ.

### 13.4. Sliding window

Sliding window tính lượng request trong một khoảng thời gian trượt. Kết quả mượt hơn nhưng có thể tốn state hoặc compute hơn.

### 13.5. Rate limit dimensions

Có thể áp dụng theo:
- Principal.
- API key.
- Tenant.
- Project.
- DSL operation.
- Endpoint.
- Resource.
- IP/network zone.
- Global service.

Cần tránh dùng IP đơn lẻ làm identity duy nhất trong hệ thống có proxy hoặc NAT.

### 13.6. Quota accounting

Quota cần xác định:
- Đơn vị đo.
- Chu kỳ reset.
- Thời điểm ghi nhận usage.
- Có tính request thất bại không.
- Có refund quota khi cancel không.
- Cách xử lý race khi nhiều worker cùng consume.
- Cách xử lý quota update hoặc rollover.

### 13.7. Atomic quota consumption

Nếu hai request đồng thời cùng đọc còn một token rồi đều được phép, quota có thể bị vượt. Quota consumption cần atomic hoặc dùng reservation/lease phù hợp.

## 14. Giới hạn theo tenant và fairness

Multi-tenancy làm cho scale limits trở thành vấn đề công bằng và isolation.

### 14.1. Tenant budget

Mỗi tenant có thể có:
- Execution count.
- CPU budget.
- Memory budget.
- Concurrent jobs.
- API call quota.
- Storage quota.
- Workflow instance quota.
- External integration quota.

### 14.2. Fair scheduling

Một scheduler có thể chia worker theo tenant hoặc dùng weighted fair queueing. Mục tiêu là tránh một tenant có queue lớn chiếm hết capacity.

### 14.3. Noisy neighbor

Noisy neighbor xảy ra khi một tenant hoặc program tiêu thụ tài nguyên quá lớn và làm latency của tenant khác tăng.

Biện pháp:
- Per-tenant concurrency cap.
- Separate queues hoặc pools.
- Resource accounting.
- Fair scheduling.
- Per-tenant rate limits.
- Workload isolation.
- Usage alerts.

### 14.4. Tiered limits

Có thể có tier khác nhau theo subscription hoặc workload class. Cần công bố rõ quota, burst, concurrency và behavior khi vượt ngưỡng.

### 14.5. Quota không phải security boundary duy nhất

Tenant quota giúp phân bổ capacity, nhưng không thay thế tenant authorization và data isolation. Một tenant không được đọc dữ liệu tenant khác dù còn quota.

## 15. Backpressure, queue limits và overload control

Khi tốc độ tạo việc lớn hơn tốc độ xử lý, queue sẽ tăng. Queue không giới hạn có thể làm memory cạn và latency tăng vô hạn.

### 15.1. Bounded queue

Queue nên có giới hạn:
- Số item.
- Tổng bytes.
- Thời gian chờ tối đa.
- Số item theo tenant.
- Priority class.

Khi queue đầy, hệ thống cần từ chối, shed load hoặc chuyển sang durable storage nếu phù hợp.

### 15.2. Backpressure

Backpressure truyền tín hiệu ngược về producer rằng consumer đang quá tải. Producer có thể giảm tốc độ, pause hoặc chỉ gửi thêm khi có demand.

Với streaming DSL, backpressure cần được propagate qua từng stage để tránh buffer vô hạn giữa các bước.

### 15.3. Load shedding

Load shedding loại bỏ công việc có thể trì hoãn hoặc ít ưu tiên khi hệ thống quá tải. Policy cần rõ:
- Loại workload được giữ.
- Loại workload bị từ chối.
- Có retry được không.
- Có thông báo client không.
- Có ưu tiên job đã bắt đầu không.

### 15.4. Admission control

Admission control quyết định có nhận một execution mới hay không dựa trên capacity hiện tại, tenant quota và workload estimate.

Nên kiểm tra trước khi cấp worker hoặc tạo tài nguyên lớn.

### 15.5. Queue age và deadline

Queue depth thấp vẫn có thể gây vấn đề nếu một item chờ quá lâu. Theo dõi queue age và deadline miss bên cạnh queue length.

## 16. Hierarchical budgets và truyền budget

Một execution có thể tạo child task, gọi plugin hoặc gọi service khác. Nếu mỗi child nhận budget mới không giới hạn, tổng chi phí có thể vượt xa ngân sách ban đầu.

### 16.1. Budget inheritance

Child execution nên nhận budget được chia từ parent hoặc dùng chung deadline. Ví dụ parent còn 10 giây thì child không được tự nhận timeout 60 giây.

### 16.2. Budget partitioning

Có thể chia budget:
- Parent orchestration: 20%.
- Child tasks: 60%.
- Serialization/finalization: 10%.
- Safety reserve: 10%.

Tỷ lệ chỉ là ví dụ. Phân bổ cần dựa vào workload và khả năng dự đoán.

### 16.3. Aggregate budget

Một execution có 10 child, mỗi child được phép gọi 10 external APIs. Nếu không có aggregate cap, tổng có thể lên tới 100 calls. Cần giới hạn cả per-child và per-execution.

### 16.4. Deadline propagation

Deadline nên được truyền qua HTTP headers, RPC metadata hoặc task context. Downstream cần biết còn bao nhiêu thời gian để tránh tiếp tục xử lý sau khi caller đã timeout.

### 16.5. Budget reservation

Với operation tốn kém, có thể reserve quota trước khi chạy và settle theo usage thực tế sau đó. Reservation cần có expiry và cơ chế release khi execution bị hủy.

## 17. Xử lý khi chạm giới hạn

Một hệ thống cần behavior nhất quán khi limit bị vượt.

### 17.1. Reject trước khi chạy

Nếu có thể ước lượng trước, reject admission trước khi cấp tài nguyên. Ví dụ source vượt max size hoặc tenant hết quota.

### 17.2. Stop trong khi chạy

Nếu chỉ phát hiện khi runtime thực thi, cần dừng an toàn:
- Cancel child tasks.
- Đóng stream và connection.
- Rollback transaction nếu còn trong transaction boundary.
- Ghi execution status.
- Lưu diagnostic.
- Release budget và semaphore.

### 17.3. Partial result

Một số operation có thể trả partial result nếu semantics cho phép. Cần đánh dấu rõ kết quả chưa đầy đủ và không giả vờ thành success hoàn chỉnh.

### 17.4. Retry semantics

Limit error có thể là:
- Permanent: source quá lớn, recursion vượt hard limit.
- Temporary: rate limit hoặc concurrency capacity tạm thời.
- Tenant quota: chờ chu kỳ reset hoặc nâng quota.
- Dependency overload: retry theo backoff nếu idempotent.

Client cần phân biệt để không retry liên tục một lỗi permanent.

### 17.5. Error model

Một error model có thể gồm:

~~~json
{
  "code": "RESOURCE_LIMIT_EXCEEDED",
  "limit": "execution.cpuTime",
  "configured": 5000,
  "observed": 5001,
  "unit": "milliseconds",
  "scope": "execution",
  "retryable": false,
  "requestId": "exec-42"
}
~~~

Không nên trả thông tin nội bộ nhạy cảm như host memory layout hoặc tenant usage của khách hàng khác.

### 17.6. Source location

Nếu limit liên quan một loop, expression hoặc operation cụ thể, diagnostic nên có source range để người phát triển biết vị trí gây tiêu thụ tài nguyên.

## 18. Khai báo limits trong DSL và runtime configuration

Có thể cho phép định nghĩa profile giới hạn:

~~~text
executionProfile "standard" {
    sourceBytes: 2MB
    astNodes: 100000
    nestingDepth: 100
    wallClock: 30s
    cpuTime: 5s
    memory: 128MB
    loopIterations: 100000
    externalCalls: 20
    parallelTasks: 10
    resultBytes: 5MB
}
~~~

Cú pháp chỉ minh họa cách tổ chức. Một số giới hạn nên được quản trị ở platform/runtime config thay vì cho từng program tự tăng.

### 18.1. Platform maximum

Platform đặt absolute maximum mà tenant hoặc project không thể vượt. Đây là lớp bảo vệ hạ tầng.

### 18.2. Tenant profile

Tenant profile có thể đặt giới hạn thấp hơn platform maximum dựa trên plan, workload hoặc hợp đồng.

### 18.3. Program-level budget

Program có thể yêu cầu budget thấp hơn hoặc khai báo expected cost. Không nên cho source tự nâng giới hạn vượt policy của host.

### 18.4. Precedence

Cần quy định rõ giới hạn nào thắng khi nhiều lớp cùng cấu hình. Một mô hình an toàn:

~~~text
effective limit = minimum(
    platform maximum,
    tenant quota,
    workload profile,
    operation-specific cap
)
~~~

Đối với một số dimension, policy có thể dùng phép kết hợp khác; cần đặc tả tường minh.

### 18.5. Versioning

Limit profile cần version và được gắn vào execution record. Khi giới hạn thay đổi, cần biết execution cũ đã chạy theo profile nào.

## 19. Static analysis và ước lượng chi phí

Một số vấn đề có thể phát hiện trước khi runtime.

### 19.1. Static checks

Có thể phát hiện:
- Literal vượt kích thước.
- Nesting quá sâu.
- Import graph quá lớn.
- Loop có bound tĩnh vượt ngưỡng.
- Recursive call không được phép.
- Query thiếu giới hạn.
- Fan-out khai báo quá lớn.
- Regex pattern vượt policy.
- Operation không có timeout.

### 19.2. Cost estimation

Compiler có thể ước lượng:
- AST size.
- Số lần lặp tối đa nếu bound tĩnh.
- Số child task tối đa.
- Số external calls.
- Query cost estimate.
- Kích thước output dự kiến.

Estimate không thay thế runtime metering vì dữ liệu thực tế và nhánh điều kiện có thể thay đổi.

### 19.3. Complexity class

Có thể phân tích một số construct theo độ phức tạp như O(n), O(n log n) hoặc O(n²). Tuy nhiên, DSL thường gọi host operation và external services nên không thể suy ra toàn bộ runtime cost chỉ từ syntax.

### 19.4. Static warning và runtime guard

Static analysis cảnh báo trước; runtime guard bảo vệ khi estimate sai hoặc input khác dự kiến. Cần dùng cả hai.

## 20. Isolation và sandboxing

Giới hạn quy mô là một phần của isolation.

### 20.1. Process isolation

Chạy untrusted DSL program trong process riêng giúp giới hạn memory/CPU ở mức OS/container. Có thể dùng cgroup/job object hoặc container resource limits tùy nền tảng.

### 20.2. Runtime isolation

Interpreter có thể có:
- Instruction meter.
- Memory quota.
- Deadline.
- Capability restrictions.
- Bounded executor.
- Cancellation token.

### 20.3. Tenant isolation

Có thể tách queue, worker pool hoặc runtime pool theo tenant class. Tách hoàn toàn tăng chi phí vận hành; chia sẻ hoàn toàn tăng nguy cơ noisy neighbor.

### 20.4. Defense in depth

Nên kết hợp:
- Input limits.
- Static analysis.
- Runtime budget.
- OS/container limits.
- Network and filesystem restrictions.
- Monitoring and alerting.

Một bộ đếm trong DSL runtime không thể bảo vệ process khỏi lỗi native code hoặc memory allocation ngoài cơ chế accounting.

## 21. Observability cho scale limits

Không thể điều chỉnh giới hạn hợp lý nếu không biết tài nguyên được sử dụng ra sao.

### 21.1. Usage metrics

Có thể theo dõi:
- Source bytes.
- Token/AST node count.
- Compile duration.
- CPU time.
- Wall-clock duration.
- Peak memory.
- Loop iterations.
- External calls.
- Result bytes.
- Concurrent executions.
- Queue depth và age.
- Quota consumption.
- Limit exceeded count.

### 21.2. Utilization ratio

Một metric hữu ích là tỷ lệ usage so với limit:

~~~text
utilization = observed_usage / configured_limit
~~~

Nếu nhiều execution thường xuyên dùng 95% budget, có thể limit quá thấp hoặc workload sắp tăng vượt capacity. Nếu mọi execution chỉ dùng 1%, limit có thể quá rộng, nhưng cần xem xét worst-case chứ không chỉ average.

### 21.3. Histograms và percentiles

Theo dõi p50, p95, p99 để thấy tail behavior. Average có thể che giấu một nhóm execution rất chậm.

### 21.4. Limit events

Mỗi lần chạm hard limit nên ghi event có:
- Execution ID.
- Tenant/project.
- Limit name.
- Configured value.
- Observed value.
- Source location nếu có.
- Workload profile version.
- Cancellation outcome.

Không ghi raw payload hoặc secret vào metric/log.

### 21.5. Cardinality

Không nên dùng execution ID, raw user ID hoặc resource ID làm metric labels nếu số lượng lớn. Dùng trace/log cho chi tiết theo từng execution; metric nên dùng dimensions có cardinality kiểm soát.

### 21.6. Alerts

Có thể cảnh báo:
- Tenant thường xuyên chạm quota.
- Queue age tăng.
- Worker saturation.
- Timeout rate tăng.
- Memory gần platform maximum.
- Downstream calls vượt budget.
- Limit rejection tăng đột ngột.

## 22. Capacity planning và load testing

Giới hạn cần dựa trên capacity thực tế và mục tiêu chất lượng dịch vụ.

### 22.1. Workload profile

Phân loại workload:
- Interactive editor evaluation.
- Short synchronous request.
- Background compilation.
- Long-running workflow.
- Batch processing.
- Streaming pipeline.
- Untrusted user program.

Mỗi profile có latency target và resource budget khác nhau.

### 22.2. Load testing

Test cần mô phỏng:
- Typical load.
- Peak load.
- Burst.
- Tenant skew.
- Large input.
- Worst-case graph.
- Slow dependency.
- Retry storm.
- Cancellation.
- Recovery sau overload.

### 22.3. Stress testing

Stress test tăng tải vượt capacity để xác định:
- Điểm bắt đầu degradation.
- Behavior của admission control.
- Queue saturation.
- Load shedding.
- Recovery time.
- Tác động tới tenant khác.

### 22.4. Soak testing

Soak test chạy tải ổn định trong thời gian dài để tìm:
- Memory leak.
- Queue growth.
- Cache growth.
- Resource handle leak.
- Quota accounting drift.
- Background task không kết thúc.

### 22.5. Headroom

Không nên đặt hard limits sát mức capacity tối đa của hạ tầng. Cần headroom cho burst, garbage collection, deployment, failover và workload variance.

## 23. Testing giới hạn và hành vi biên

### 23.1. Boundary tests

Với mỗi limit, test:
- Ngay dưới ngưỡng.
- Đúng bằng ngưỡng.
- Vượt một đơn vị.
- Input rỗng.
- Input cực nhỏ.
- Input malformed.
- Unicode/multibyte.
- Concurrent requests cùng consume quota.

### 23.2. Budget exhaustion tests

Xác nhận khi budget cạn:
- Execution dừng đúng.
- Child tasks được cancel.
- Resource được release.
- Diagnostic đúng limit.
- Không trả success giả.
- Audit/usage accounting nhất quán.

### 23.3. Quota race tests

Nhiều request đồng thời cùng consume quota phải không vượt ngưỡng do race condition. Test cần chạy trên implementation storage thực tế hoặc một model concurrency phù hợp.

### 23.4. Tenant fairness tests

Tạo một tenant tải rất cao và tenant khác tải thấp. Kiểm tra tenant tải thấp vẫn đạt service objective theo fairness policy.

### 23.5. Dependency failure tests

Mô phỏng downstream chậm, timeout, retry, circuit breaker open và cancellation. Xác nhận tổng external calls vẫn trong budget.

### 23.6. Regression tests

Khi đổi compiler/runtime version hoặc limit profile, chạy lại workload corpus để phát hiện thay đổi usage bất thường.

## 24. Những sai lầm thường gặp

1. **Chỉ giới hạn source bytes:** source ngắn vẫn có thể tạo computation rất lớn.
2. **Chỉ đặt timeout:** execution có thể tiêu thụ quá nhiều memory trước khi timeout.
3. **Không giới hạn nesting:** parser hoặc visitor có thể stack overflow.
4. **Giới hạn từng loop riêng lẻ:** nested loops vẫn tạo tổng work quá lớn.
5. **Retry không có tổng budget:** nhiều tầng retry tạo amplification.
6. **Queue không bounded:** backlog làm memory tăng vô hạn.
7. **Không giới hạn fan-out:** một workflow tạo quá nhiều child tasks.
8. **Dùng một quota toàn cục:** tenant lớn có thể làm tenant nhỏ bị ảnh hưởng.
9. **Cache không có eviction:** cache trở thành nguồn memory leak.
10. **Không truyền deadline:** downstream tiếp tục chạy sau khi caller timeout.
11. **Chỉ đo average:** tail latency và worst-case bị che khuất.
12. **Không tính decompressed size:** compressed payload nhỏ có thể bung ra rất lớn.
13. **Cho program tự tăng budget:** người viết DSL có thể vượt platform policy.
14. **Không phân biệt permanent và temporary limit errors:** client retry vô ích hoặc bỏ cuộc quá sớm.
15. **Không release tài nguyên khi cancel:** timeout không giải phóng worker/connection.
16. **Chỉ dựa vào runtime counter:** native/plugin code có thể tiêu thụ tài nguyên ngoài accounting.
17. **Không test concurrency quota:** race condition làm vượt quota.
18. **Không gắn profile version:** khó giải thích vì sao cùng program có behavior khác.

## 25. Quy trình thiết kế giới hạn quy mô

Một quy trình triển khai có thể gồm:

1. **Phân loại workload:** editor, compile, interactive runtime, batch, workflow và untrusted execution.
2. **Lập resource model:** source bytes, AST nodes, CPU, memory, time, I/O, concurrency và storage.
3. **Xác định scope:** per file, program, execution, principal, tenant, worker và cluster.
4. **Chọn cơ chế:** hard limit, warning, quota, budget, rate limit và concurrency cap.
5. **Đặt platform maximum:** bảo vệ capacity và security boundary.
6. **Thiết kế tenant/workload profile:** phân bổ công bằng và phù hợp service tier.
7. **Giới hạn parser/compiler:** source size, token, nesting, dependency graph và compile time.
8. **Giới hạn runtime:** fuel, CPU, wall-clock, memory, loops, recursion và result size.
9. **Giới hạn I/O:** network, database, filesystem, plugin, retry và fan-out.
10. **Thiết kế queue/backpressure:** bounded queue, admission control, cancellation và load shedding.
11. **Truyền budget:** child task dùng chung deadline và aggregate budget với parent.
12. **Định nghĩa limit errors:** reason code, retryability, source range và cleanup behavior.
13. **Thêm observability:** usage metrics, percentiles, limit events và alerts.
14. **Capacity planning:** benchmark, stress, soak và headroom.
15. **Kiểm thử biên:** threshold, race, tenant fairness, cancellation và dependency failure.
16. **Version limit profiles:** gắn profile version vào compile/execution records.
17. **Điều chỉnh theo dữ liệu:** thay đổi ngưỡng có kiểm soát và theo dõi tác động.

Bắt đầu với một profile an toàn, đo usage thực tế trên workload đại diện, rồi điều chỉnh ngưỡng dựa trên capacity và service objective. Không nên tăng mọi limit chỉ để loại bỏ lỗi quota; cần tìm nguyên nhân workload tăng và xác định hệ thống có đủ capacity hay không.

## 26. Kết luận

Giới hạn quy mô trong DSL kiểm soát kích thước đầu vào, độ phức tạp của chương trình, chi phí compile/evaluation, memory, vòng lặp, dữ liệu, concurrency và tài nguyên bên ngoài. Một hệ thống bền vững kết hợp hard limits, warning thresholds, quotas, per-execution budgets, rate limits và concurrency controls ở đúng lớp.

Giới hạn cần có scope, đơn vị đo, precedence, version và hành vi khi bị vượt. Runtime phải truyền deadline và budget xuống child tasks, cancel công việc đúng cách, release tài nguyên và trả diagnostics có thể giải thích. Per-tenant fairness, bounded queues, backpressure, observability và load testing giúp hệ thống duy trì chất lượng khi tải tăng. Khi scale limits được thiết kế từ parser đến runtime và platform, DSL có thể phục vụ workload lớn mà vẫn bảo vệ tính ổn định và công bằng của hệ thống.

