# Đo đạc và profiling

Hiệu năng là một thuộc tính quan trọng của ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL). Một DSL có thể có cú pháp ngắn gọn và biểu đạt nghiệp vụ tốt, nhưng nếu phân tích chậm, biên dịch tốn nhiều tài nguyên hoặc runtime thực thi kém hiệu quả thì trải nghiệm người dùng và khả năng mở rộng của hệ thống đều bị ảnh hưởng.

**Đo đạc hiệu năng (performance measurement)** là quá trình thu thập các số liệu có thể định lượng về thời gian, tài nguyên và thông lượng của hệ thống. **Profiling** là kỹ thuật quan sát chi tiết hoạt động của chương trình trong lúc chạy để xác định hàm, đoạn mã, call path hoặc loại tài nguyên đang tiêu tốn chi phí. Hai hoạt động này bổ sung cho nhau: đo đạc cho biết vấn đề tồn tại ở đâu và nghiêm trọng đến mức nào; profiling giúp giải thích vì sao vấn đề xảy ra.

Với DSL, cần quan sát cả toolchain và chương trình được viết bằng DSL. Toolchain có thể gồm parser, symbol resolver, type checker, validator, optimizer, code generator, compiler và runtime. Một chương trình DSL có thể chạy chậm vì biểu thức phức tạp, truy vấn dữ liệu lớn, gọi dịch vụ bên ngoài, cấp phát object quá nhiều hoặc thực hiện một thuật toán không phù hợp. Nếu chỉ đo thời gian tổng thể, những nguyên nhân này dễ bị trộn lẫn.

Một quy trình tối ưu hiệu năng đáng tin cậy cần bắt đầu từ workload đại diện, xác định chỉ số cần cải thiện, đo baseline, profiling để tìm bottleneck, thay đổi một nguyên nhân cụ thể và đo lại trong cùng điều kiện. Không nên tối ưu dựa trên cảm giác hoặc một lần chạy đơn lẻ. Cũng cần xác minh kết quả vẫn đúng ngữ nghĩa của DSL và chi phí instrumentation không làm sai lệch kết luận.

Bài học này trình bày các khái niệm đo đạc và profiling, mô hình hiệu năng của DSL, thiết kế benchmark, latency và throughput, profiling CPU và memory, allocation và garbage collection, profiling compiler phase, runtime và query, tracing, sampling, flame graph, công cụ JVM, phân tích bottleneck, tối ưu có kiểm chứng và cách xây dựng quy trình đo đạc lâu dài.

## 1. Đo đạc hiệu năng và profiling

Đo đạc và profiling đều quan sát hệ thống nhưng trả lời các câu hỏi khác nhau.

### 1.1. Performance measurement

Đo đạc hiệu năng thu thập các chỉ số như:
- Thời gian hoàn thành.
- Số thao tác mỗi giây.
- Thời gian chờ.
- CPU time.
- Memory usage.
- Allocation rate.
- Garbage collection time.
- I/O và network latency.
- Kích thước output.
- Tỷ lệ lỗi và timeout.

Ví dụ, một benchmark có thể cho biết compiler biên dịch 500 file DSL trong 2,4 giây và dùng tối đa 420 MB heap. Đây là số liệu tổng hợp để so sánh giữa các phiên bản.

### 1.2. Profiling

Profiling quan sát hoạt động nội bộ để xác định chi phí tập trung ở đâu. Một CPU profile có thể cho thấy 35% sample nằm trong type inference, 25% nằm trong AST traversal và 18% nằm trong string formatting.

Một memory profile có thể chỉ ra một loại node AST chiếm phần lớn retained heap, hoặc một cache giữ lại nhiều workspace object hơn dự kiến.

### 1.3. Monitoring

Monitoring theo dõi hệ thống liên tục trong môi trường thật. Nó thường sử dụng metric, log, trace và alert để phát hiện xu hướng hoặc sự cố.

| Hoạt động | Phạm vi | Câu hỏi chính |
| --- | --- | --- |
| Measurement | Một workload hoặc một khoảng đo | Nhanh đến mức nào? |
| Profiling | Bên trong một lần chạy | Chi phí nằm ở đâu? |
| Monitoring | Hệ thống đang vận hành | Hiệu năng hiện tại có bất thường không? |
| Benchmarking | So sánh các phiên bản hoặc cấu hình | Thay đổi có cải thiện không? |

### 1.4. Benchmark không thay profiling

Benchmark cho biết phiên bản B nhanh hơn phiên bản A bao nhiêu trong một workload cụ thể. Nó không tự giải thích nguyên nhân. Profiling giúp tìm nguyên nhân nhưng một profile riêng lẻ không thay thế phép đo so sánh có kiểm soát.

### 1.5. Tối ưu không có số liệu

Một thay đổi có vẻ đơn giản hơn có thể làm chương trình chậm hơn do allocation, cache miss hoặc algorithmic complexity. Vì vậy, mọi tuyên bố cải thiện hiệu năng cần có baseline và phép đo sau thay đổi.

## 2. Mô hình hiệu năng của một DSL

Một DSL có nhiều giai đoạn. Cần xác định phạm vi đo trước khi so sánh.

~~~text
Source Files
    |
    v
Load Workspace
    |
    v
Parse
    |
    v
Resolve Symbols
    |
    v
Type Check
    |
    v
Validate
    |
    v
Optimize IR
    |
    v
Generate Code
    |
    v
Load / Link
    |
    v
Execute
    |
    v
External Services and Data
~~~

### 2.1. Front end

Front end thường gồm:
- Lexing.
- Parsing.
- AST construction.
- Name resolution.
- Type checking.
- Semantic validation.

Các giai đoạn này phụ thuộc kích thước source, số declaration, số symbol, độ sâu expression và độ phức tạp type.

### 2.2. Middle end

Middle end có thể chuẩn hóa hoặc tối ưu intermediate representation (IR):
- Constant folding.
- Dead code elimination.
- Common subexpression elimination.
- Control-flow simplification.
- Query rewrite.
- Inline hoặc specialization.

Một optimizer có thể làm compile time tăng nhưng runtime giảm. Vì vậy cần đo cả hai phía.

### 2.3. Back end

Back end tạo bytecode, source code, SQL, schema hoặc artifact khác. Chi phí phụ thuộc target, số node IR, template generation, serialization và output size.

### 2.4. Runtime

Runtime có thể gồm:
- Load artifact.
- Resolve function.
- Interpret hoặc execute bytecode.
- Allocate object.
- Call host API.
- Query data.
- Perform I/O.
- Schedule workflow.
- Persist result.

### 2.5. External dependency

Một chương trình DSL có thể nhanh ở phần tính toán nhưng chậm do database, API hoặc message broker. Cần tách thời gian xử lý nội bộ khỏi thời gian chờ bên ngoài.

### 2.6. Cold path và warm path

Cold path gồm khởi động runtime, load metadata, parse lần đầu hoặc tạo cache. Warm path tận dụng cache, JIT compilation hoặc prepared query.

Cần đo cả hai nếu sản phẩm có workload ngắn hạn và workload dài hạn. Không nên chỉ benchmark warm path nếu người dùng thường xuyên chạy một biểu thức một lần.

## 3. Xác định workload đại diện

Kết quả đo chỉ có ý nghĩa khi workload gần với cách hệ thống được sử dụng.

### 3.1. Workload theo kích thước

Có thể chia:
- Nhỏ: expression hoặc file đơn.
- Vừa: module có nhiều declaration và dependency.
- Lớn: workspace nhiều file, type và query.
- Rất lớn: dự án nhiều module hoặc hàng triệu record runtime.

Không nên dùng duy nhất một file nhỏ để đại diện cho toàn bộ hệ thống.

### 3.2. Workload theo cấu trúc

Với DSL compiler, hãy tạo workload có:
- AST nông và sâu.
- Nhiều symbol và scope.
- Type generic và union phức tạp.
- Nhiều overload.
- Nhiều dependency.
- Expression dài.
- Nhiều diagnostic.
- Macro hoặc expansion nếu DSL hỗ trợ.

### 3.3. Workload runtime

Với runtime, cần có:
- Input nhỏ và lớn.
- Collection rỗng, trung bình và lớn.
- Branch thường và hiếm.
- Function call lặp.
- Query có và không có index.
- Host API nhanh và chậm.
- Async operation.
- Error và retry path.

### 3.4. Production workload

Nếu được phép, dùng dữ liệu đã ẩn danh hoặc workload tổng hợp dựa trên phân bố production. Không sao chép dữ liệu nhạy cảm vào benchmark. Giữ tỷ lệ kích thước, cấu trúc và tần suất tương tự thực tế.

### 3.5. Representative suite

Một benchmark suite nên gồm nhiều trường hợp có mục đích rõ:
- Parser throughput.
- Semantic analysis scaling.
- Incremental compilation.
- Code generation.
- Runtime expression evaluation.
- Query execution.
- Memory footprint.
- Startup latency.

### 3.6. Tránh benchmark chỉ có happy path

Workload có nhiều lỗi có thể tốn chi phí khác do diagnostic construction và recovery. Workload có cache miss hoặc dependency unavailable cũng cần được xem xét nếu đó là tình huống vận hành thường gặp.

## 4. Các chỉ số hiệu năng quan trọng

Không có một chỉ số duy nhất mô tả đầy đủ hiệu năng.

### 4.1. Latency

Latency là thời gian từ lúc một thao tác bắt đầu đến khi hoàn tất. Có thể đo:
- End-to-end latency.
- Stage latency.
- Queue wait.
- Host call latency.
- Database latency.
- Time to first result.

Latency nên được báo cáo với phân bố, không chỉ trung bình.

### 4.2. Throughput

Throughput là số lượng công việc hoàn thành trong một đơn vị thời gian, ví dụ:
- File DSL mỗi giây.
- AST node mỗi giây.
- Query mỗi giây.
- Workflow transition mỗi giây.
- Record được xử lý mỗi giây.

Throughput phụ thuộc concurrency và mức độ tranh chấp tài nguyên.

### 4.3. CPU time và wall-clock time

Wall-clock time là thời gian thực tế trôi qua. CPU time là thời gian CPU được dùng bởi process hoặc thread.

Nếu wall-clock cao nhưng CPU time thấp, chương trình có thể đang chờ I/O, lock, queue hoặc scheduler. Nếu cả hai cao, có thể bottleneck là tính toán.

### 4.4. Memory footprint

Memory footprint có thể gồm:
- Heap used.
- Heap committed.
- Resident set size (RSS).
- Native memory.
- Metaspace hoặc class metadata.
- Direct buffer.
- Memory của worker con.

Không nên nhầm heap usage với toàn bộ memory của process.

### 4.5. Allocation rate

Allocation rate đo lượng object được tạo trong một đơn vị thời gian. Allocation cao có thể làm garbage collection thường xuyên dù live heap không lớn.

### 4.6. GC pause và GC overhead

Theo dõi:
- Tổng thời gian GC.
- Số lần collection.
- Pause duration.
- Allocation pressure.
- Promotion.
- Heap after collection.

Một ứng dụng có throughput tốt nhưng pause dài có thể gây latency spike.

### 4.7. Scalability

Scalability đo cách chi phí thay đổi khi workload tăng. Ví dụ, nếu số file tăng gấp đôi thì compile time có tăng gần gấp đôi hay tăng theo bình phương?

### 4.8. Resource efficiency

Có thể đo số công việc hoàn thành trên một đơn vị CPU, memory hoặc chi phí hạ tầng. Hiệu năng tốt không chỉ là nhanh mà còn sử dụng tài nguyên hợp lý.

## 5. Latency distribution và percentile

Latency thường có phân bố lệch. Một số request chậm có thể bị che khuất nếu chỉ nhìn average.

### 5.1. Mean

Mean là trung bình số học. Nó hữu ích cho tổng chi phí nhưng nhạy với outlier.

### 5.2. Median và percentile

- p50: một nửa thao tác hoàn tất trong thời gian này hoặc nhanh hơn.
- p90: 90% thao tác hoàn tất trong thời gian này hoặc nhanh hơn.
- p95: 95% thao tác hoàn tất trong thời gian này hoặc nhanh hơn.
- p99: 99% thao tác hoàn tất trong thời gian này hoặc nhanh hơn.

p95 và p99 giúp hiểu tail latency, đặc biệt với dịch vụ nhiều request.

### 5.3. Ví dụ

Giả sử thời gian thực thi 1000 expression có phân bố:

| Chỉ số | Thời gian |
| --- | ---: |
| p50 | 4 ms |
| p90 | 9 ms |
| p95 | 18 ms |
| p99 | 75 ms |
| Max | 210 ms |

Median thấp nhưng một số expression rất chậm. Cần điều tra workload thuộc tail thay vì chỉ tối ưu trường hợp phổ biến.

### 5.4. Percentile và sample size

Percentile cao cần đủ mẫu. p99 từ 20 lần chạy không đáng tin cậy. Ghi số lượng sample và cửa sổ thời gian cùng percentile.

### 5.5. Coordinated omission

Nếu benchmark chỉ gửi request mới sau khi request trước hoàn tất, lúc hệ thống chậm nó sẽ tự giảm tải và bỏ qua một phần latency mà hệ thống sẽ gặp dưới tải cố định. Đây là coordinated omission.

Dùng load generator có lịch phát request phù hợp với mục tiêu đo, đồng thời ghi nhận cả thời gian chờ trong generator.

## 6. Thiết kế benchmark có kiểm soát

Benchmark là phép đo có thể lặp lại để so sánh thay đổi.

### 6.1. Xác định giả thuyết

Ví dụ: cache symbol resolution sẽ giảm thời gian semantic analysis khi nhiều file dùng chung declaration.

Giả thuyết cần chỉ ra:
- Workload nào bị ảnh hưởng.
- Chỉ số nào sẽ thay đổi.
- Vì sao thay đổi có thể cải thiện.
- Tác dụng phụ có thể xảy ra.

### 6.2. Baseline

Chạy benchmark trước khi sửa. Lưu:
- Commit hoặc revision.
- Compiler version.
- Runtime version.
- Machine profile.
- OS và JVM version.
- Workload version.
- Cấu hình.
- Kết quả raw.

### 6.3. Controlled environment

Giữ ổn định:
- CPU model và frequency policy.
- Memory.
- OS.
- JVM flags.
- Background load.
- Disk cache state.
- Network condition.
- Dataset.
- Warmup.

Nếu không thể giữ ổn định, ghi lại yếu tố khác biệt.

### 6.4. Warmup

Trên JVM, JIT compilation và class loading có thể làm các lần chạy đầu chậm hơn. Benchmark cần warmup đủ để đạt trạng thái đại diện, nhưng cũng cần đo cold startup riêng nếu startup quan trọng.

### 6.5. Repetitions

Chạy nhiều lần và báo median, percentile hoặc khoảng tin cậy. Tránh chọn một lần chạy đẹp nhất.

### 6.6. A/B comparison

So sánh phiên bản cũ và mới trên cùng máy và cùng input. Nếu có thể, chạy xen kẽ A-B-B-A để giảm ảnh hưởng nhiệt độ, tải hoặc thay đổi môi trường theo thời gian.

### 6.7. Benchmark harness

Một harness nên:
- Chuẩn bị input trước khi bắt đầu timer nếu không muốn đo setup.
- Warmup theo cấu hình.
- Đo nhiều iteration.
- Ghi kết quả raw.
- Kiểm tra output correctness.
- Dọn state hoặc cache theo policy.
- Báo environment metadata.

### 6.8. Tránh dead-code elimination

Với microbenchmark, compiler hoặc JIT có thể loại bỏ phép tính nếu kết quả không được sử dụng. Harness cần tiêu thụ kết quả hoặc dùng cơ chế benchmark framework để ngăn tối ưu sai lệch.

## 7. Microbenchmark và macrobenchmark

Hai cấp benchmark trả lời những câu hỏi khác nhau.

### 7.1. Microbenchmark

Microbenchmark đo một thao tác nhỏ:
- Tokenize một đoạn source.
- Lookup symbol.
- Evaluate một arithmetic node.
- Allocate một AST node.
- Serialize một IR instruction.

Ưu điểm là dễ khoanh vùng. Nhược điểm là có thể không phản ánh tương tác của hệ thống thực tế.

### 7.2. Macrobenchmark

Macrobenchmark đo một luồng gần thực tế:
- Mở workspace.
- Compile module.
- Chạy query.
- Deploy workflow.
- Xử lý một batch event.
- Tạo artifact từ source đến package.

Macrobenchmark bao gồm nhiều thành phần và phù hợp đánh giá trải nghiệm tổng thể.

### 7.3. Benchmark theo phase

Một benchmark compiler nên tách:
- Parse only.
- Resolve only trên AST đã có.
- Type check only.
- Optimize only.
- Generate only.
- End-to-end compile.

Việc tách phase giúp xác định stage gây regression.

### 7.4. Overhead của setup

Nếu mục tiêu là đo parser, không tính thời gian đọc file từ disk trừ khi đó là một phần workload. Nếu mục tiêu là đo startup end-to-end, setup lại phải được tính.

### 7.5. Khi nào dùng loại nào?

Dùng microbenchmark để kiểm tra một giả thuyết hẹp. Dùng macrobenchmark để xác nhận cải thiện có giá trị với người dùng. Cả hai thường cần thiết trước khi chấp nhận một tối ưu lớn.

## 8. Profiling CPU

CPU profiling xác định nơi process hoặc thread tiêu thụ thời gian xử lý.

### 8.1. Instrumentation profiling

Instrumentation thêm bộ đếm hoặc timer quanh function hoặc block. Ví dụ:

~~~java
long start = System.nanoTime();
try {
    return typeChecker.check(module);
} finally {
    metrics.recordTypeCheck(System.nanoTime() - start);
}
~~~

Ưu điểm là biết chính xác thời gian của operation được instrument. Nhược điểm là overhead, code noise và khả năng bỏ sót các call path chưa instrument.

### 8.2. Sampling profiling

Sampling profiler định kỳ lấy mẫu stack trace của thread đang chạy. Nếu một function xuất hiện nhiều trong sample, nó có thể đang chiếm nhiều CPU.

Sampling thường có overhead thấp hơn instrumentation toàn diện và phù hợp với ứng dụng đang chạy lâu.

### 8.3. Self time và total time

- Self time: thời gian nằm trực tiếp trong function, không tính function con.
- Total time: thời gian trong function và các function được gọi từ nó.

Một function có total time cao nhưng self time thấp có thể chỉ là điểm đi qua tới bottleneck nằm sâu hơn.

### 8.4. Hot method

Hot method là method xuất hiện thường xuyên trong CPU profile. Nhưng một method có nhiều sample chưa chắc là nơi cần sửa; nó có thể là công việc thiết yếu hoặc nằm trên đường xử lý chính.

### 8.5. Call tree

Call tree cho biết function nào gọi function nào và thời gian tích lũy qua từng nhánh. Đây là cách tốt để hiểu vì sao parser hoặc type checker gọi một routine quá nhiều lần.

### 8.6. Thread state

Ngoài RUNNABLE, cần xem thread có đang:
- BLOCKED trên monitor.
- WAITING.
- TIMED_WAITING.
- Parked.
- Chờ I/O.

CPU profile có thể không hiển thị bottleneck nếu thread chủ yếu chờ lock hoặc external call.

## 9. Flame graph

Flame graph là cách trực quan hóa stack sample. Trục ngang biểu diễn số sample hoặc tỷ trọng; trục dọc biểu diễn độ sâu call stack.

~~~text
                 executeWorkflow
              /        |          \
        evaluate      hostCall    persist
        /     \          |           |
     parse   typeCheck  httpClient  database
                |
           resolveSymbol
~~~

Sơ đồ trên chỉ minh họa quan hệ call stack, không phải flame graph được đo.

### 9.1. Đọc flame graph

- Khối rộng biểu thị nhiều sample.
- Khối cao biểu thị stack sâu.
- Một nhánh rộng ở đáy thường là đường xử lý tiêu tốn nhiều CPU.
- Một method rộng ở giữa hoặc trên có thể được gọi nhiều lần từ nhiều path.

### 9.2. Inclusive width

Độ rộng của frame thường bao gồm thời gian trong các function con. Không cộng tất cả chiều rộng của các frame theo chiều dọc vì sẽ đếm trùng.

### 9.3. Flame graph không phải timeline

Flame graph tổng hợp sample, không thể hiện chính xác thứ tự thời gian. Dùng trace hoặc timeline profiler để điều tra race, pause hoặc latency spike.

### 9.4. Differential flame graph

So sánh profile trước và sau thay đổi có thể cho thấy stack nào giảm hoặc tăng. Cần cùng workload, cùng sampling settings và môi trường tương đương.

### 9.5. On-CPU và off-CPU

On-CPU flame graph thể hiện thời gian thread đang chạy trên CPU. Off-CPU profiling giúp hiểu thời gian chờ lock, I/O hoặc scheduler. Một hệ thống chậm có thể không có CPU hotspot rõ ràng.

## 10. Profiling memory và allocation

Memory profiling tìm nguyên nhân sử dụng heap hoặc native memory quá cao.

### 10.1. Heap usage

Heap usage là phần bộ nhớ heap đang được sử dụng. Cần phân biệt:
- Used heap.
- Committed heap.
- Maximum heap.

Heap committed lớn không đồng nghĩa toàn bộ đang được object sử dụng.

### 10.2. Allocation profile

Allocation profile cho biết loại object và call path tạo ra object. Với DSL compiler, các đối tượng thường gặp:
- AST node.
- Token.
- Symbol.
- Type object.
- Diagnostic.
- String.
- Collection.
- IR node.

Nếu một loại object được tạo hàng triệu lần, có thể cần giảm số lần tạo hoặc tái sử dụng dữ liệu bất biến phù hợp.

### 10.3. Retained heap

Retained heap ước lượng lượng bộ nhớ sẽ được giải phóng nếu một object và các object chỉ được nó giữ tham chiếu không còn reachable. Nó hữu ích để tìm cache hoặc workspace object bị giữ quá lâu.

### 10.4. Object graph

Heap dump cho phép xem object reference graph. Cần tìm:
- Dominator.
- Collection quá lớn.
- Cache không có eviction.
- Listener không unregister.
- Static reference giữ workspace.
- Classloader leak.

### 10.5. Allocation rate và GC

Một ứng dụng có heap nhỏ nhưng allocation rate rất cao vẫn có thể chạy GC liên tục. Hãy so sánh allocation rate, GC time và latency.

### 10.6. Native memory

Một số thư viện dùng direct buffer, JNI hoặc native allocation. Heap dump Java có thể không giải thích được toàn bộ RSS. Dùng native memory tracking hoặc OS-level tools khi cần.

### 10.7. Memory leak và high allocation

Memory leak là object không còn cần nhưng vẫn reachable. High allocation là tạo nhiều object ngắn hạn. Hai vấn đề cần cách xử lý khác nhau.

## 11. Garbage collection và latency

GC ảnh hưởng đến throughput và tail latency của ứng dụng JVM.

### 11.1. Allocation pressure

Khi tốc độ tạo object vượt khả năng thu gom hoặc heap quá nhỏ, GC chạy thường xuyên hơn.

### 11.2. Pause time

Stop-the-world pause có thể làm mọi thread ứng dụng dừng tạm thời. Với interactive editor hoặc runtime phục vụ request, pause dài ảnh hưởng trực tiếp latency.

### 11.3. GC logs

GC log có thể cho biết:
- Collection type.
- Heap before/after.
- Pause duration.
- Allocation failure.
- Promotion.
- Concurrent phase.
- Humongous allocation nếu collector có khái niệm đó.

### 11.4. Tối ưu allocation trước khi đổi collector

Nếu DSL tạo quá nhiều object tạm, hãy xem xét:
- Tránh tạo String trung gian.
- Giảm boxing.
- Dùng primitive representation khi hợp lý.
- Tránh copy collection không cần thiết.
- Dùng immutable shared metadata.
- Giới hạn cache.

Đổi GC không sửa được mọi nguyên nhân allocation.

### 11.5. GC tuning

Chỉ điều chỉnh heap và collector sau khi có số liệu. Tăng heap có thể giảm tần suất GC nhưng tăng memory footprint hoặc pause. Chọn collector theo latency, throughput và memory budget thực tế.

## 12. Profiling compiler của DSL

Compiler cần instrumentation theo phase để xác định chi phí từng bước.

### 12.1. Parse profiling

Đo:
- Tokenization time.
- Parser time.
- AST construction time.
- Số token.
- Số AST node.
- Peak memory.
- Error recovery cost.

Có thể đo riêng file nhỏ, file lớn và file có nhiều lỗi cú pháp.

### 12.2. Name resolution profiling

Đo:
- Symbol lookup count.
- Scope depth.
- Import resolution.
- Dependency traversal.
- Cache hit/miss.
- Số symbol được tạo.

Nếu lookup tuyến tính trong scope lớn, hash map hoặc indexed symbol table có thể giúp giảm chi phí.

### 12.3. Type checking profiling

Đo:
- Số expression được kiểm tra.
- Constraint generation.
- Constraint solving.
- Overload resolution.
- Generic instantiation.
- Type substitution.
- Type cache hit/miss.

Type inference có thể tăng chi phí mạnh với biểu thức lồng hoặc nhiều overload. Profile giúp xác định algorithmic hotspot.

### 12.4. Validation profiling

Mỗi rule validator có thể ghi duration và số node đã kiểm tra. Một rule duyệt lại toàn bộ AST nhiều lần có thể gây chi phí lớn.

### 12.5. Optimization profiling

Đo thời gian và số node trước/sau mỗi optimization pass. Một pass có thể không đáng chạy cho chương trình nhỏ hoặc không làm giảm runtime cost đủ bù compile cost.

### 12.6. Code generation profiling

Đo:
- Số IR node.
- Số output instruction.
- String building.
- Template expansion.
- Serialization.
- File writing.
- Source map generation.

String concatenation lặp có thể gây copy lớn; builder hoặc streaming writer có thể phù hợp hơn.

### 12.7. Incremental compilation

Đo:
- Số file invalidated.
- Số dependency bị đánh dấu dirty.
- Số node được tái sử dụng.
- Recompile duration.
- Cache hit.
- Dependency graph traversal.

Incremental compiler cần tránh invalidating toàn bộ workspace khi chỉ một declaration nhỏ thay đổi.

## 13. Profiling runtime DSL

Runtime profiling tập trung vào chi phí khi chương trình DSL thực thi.

### 13.1. Interpreter

Đo:
- AST dispatch.
- Opcode dispatch.
- Environment lookup.
- Variable access.
- Function call.
- Type conversion.
- Allocation.
- Exception path.

Nếu mỗi node AST dùng nhiều virtual call hoặc map lookup, interpreter có thể chịu overhead đáng kể.

### 13.2. Bytecode hoặc generated code

Nếu DSL biên dịch thành bytecode hoặc host code, đo:
- Class loading.
- Linkage.
- JIT compilation.
- Deoptimization.
- Generated method execution.
- Code cache.
- Compilation warmup.

### 13.3. Function call overhead

Một DSL có thể gọi host function rất thường xuyên. Cần phân biệt chi phí dispatch với chi phí thực sự của function.

### 13.4. Environment lookup

Dynamic scope hoặc environment chain sâu có thể khiến lookup biến chậm. Có thể cân nhắc slot index hoặc lexical binding nếu semantics cho phép.

### 13.5. Branch behavior

Expression có nhiều nhánh hoặc pattern matching có thể có hiệu năng khác theo phân bố input. Benchmark nên dùng input có tỷ lệ nhánh đại diện.

### 13.6. Exception path

Exception thường đắt hơn nhánh điều khiển bình thường. Không dùng exception làm flow control cho trường hợp phổ biến nếu DSL có thể biểu diễn kết quả bằng value hoặc diagnostic.

### 13.7. Runtime context

Tạo context, bind host capability và load metadata cũng có thể chiếm nhiều thời gian. Đo startup riêng với execution steady-state.

## 14. Profiling query và data access

DSL truy vấn thường chịu chi phí ở query planner, database và truyền dữ liệu.

### 14.1. Tách thời gian query

Đo riêng:
- Parse query.
- Validate query.
- Build logical plan.
- Optimize plan.
- Generate SQL hoặc request.
- Queue wait.
- Database execution.
- Fetch result.
- Map result.
- Projection trong runtime.

### 14.2. Query plan

Query plan giúp xem scan, filter, join, sort, aggregate và projection. Đo thời gian và cardinality ở từng operator nếu engine hỗ trợ.

### 14.3. Cardinality estimate

Sai estimate có thể dẫn đến join order hoặc algorithm không phù hợp. So sánh estimated rows với actual rows khi có thể.

### 14.4. N+1 query

Một projection gọi data access cho từng record có thể tạo N+1 query. Trace và query count giúp nhận ra pattern này.

### 14.5. Over-fetching

Nếu DSL lấy toàn bộ entity nhưng chỉ dùng hai field, băng thông và mapping cost tăng. Projection pushdown có thể giảm dữ liệu đọc.

### 14.6. Cache

Đo cache hit, miss, lookup duration và invalidation. Cache có thể giảm latency nhưng tăng memory và tạo stale result nếu key hoặc invalidation sai.

### 14.7. Connection pool

Nếu query chờ connection, database execution time có thể thấp nhưng end-to-end latency cao. Theo dõi pool active, idle, pending và acquisition time.

## 15. Profiling I/O và network

Một chương trình DSL có thể dành phần lớn thời gian chờ external system.

### 15.1. I/O wait

Đo thời gian đọc file, database, queue và remote service. Phân biệt wait time với CPU processing.

### 15.2. Network latency

Theo dõi DNS, connection setup, TLS handshake, request, response và retry nếu client hỗ trợ instrumentation.

### 15.3. Payload size

Request hoặc response lớn làm tăng serialization, network transfer và memory. Đo byte count cùng duration.

### 15.4. Batching

Nhiều lời gọi nhỏ có thể tốn round trip. Batching giúp giảm latency nhưng có thể tăng payload hoặc thời gian chờ gom batch.

### 15.5. Timeout và retry

Retry có thể làm tăng throughput thành công nhưng cũng kéo dài tail latency và gây tải lên dependency. Đo attempt count và cumulative wait.

### 15.6. Async execution

Async không tự làm công việc nhanh hơn. Nó giúp dùng thread hiệu quả khi chờ I/O. Cần đo queue delay, event loop lag và concurrency.

## 16. Profiling concurrency và contention

Khi nhiều thread hoặc workflow cùng chạy, lock và scheduling có thể trở thành bottleneck.

### 16.1. Lock contention

Theo dõi:
- Monitor blocked time.
- Lock wait.
- Contended lock.
- Number of waiters.
- Hold duration.

Một lock toàn cục trong symbol cache có thể serialize nhiều compile task.

### 16.2. Thread pool saturation

Nếu task queue tăng trong khi worker đều bận, pool có thể thiếu capacity hoặc có task bị block lâu. Nếu tăng thread quá nhiều, context switching và memory stack cũng tăng.

### 16.3. False sharing

Các thread cập nhật biến gần nhau trong memory có thể tranh chấp cache line. Đây là vấn đề cấp thấp, chỉ nên điều tra khi profile và hardware counter cho thấy dấu hiệu phù hợp.

### 16.4. Work stealing

Một scheduler có thể phân phối task giữa worker. Đo queue imbalance, steal count và idle time để biết task có được phân phối hợp lý không.

### 16.5. Parallelism overhead

Chia một tác vụ nhỏ thành quá nhiều task có thể tốn scheduling và synchronization nhiều hơn phần công việc. Chọn kích thước task theo workload.

### 16.6. Deadlock và starvation

Thread dump và trace có thể giúp phát hiện deadlock hoặc task không bao giờ được schedule. Starvation có thể xảy ra khi một nhóm task liên tục chiếm worker.

## 17. Profiling trong JVM

Nếu compiler hoặc runtime DSL chạy trên JVM, có nhiều công cụ hỗ trợ profiling.

### 17.1. Java Flight Recorder

Java Flight Recorder (JFR) thu thập sự kiện JVM như CPU samples, allocation, GC, thread park, monitor contention và class loading. JFR thường phù hợp để quan sát ứng dụng trong thời gian chạy với overhead có thể kiểm soát theo cấu hình.

### 17.2. Java Mission Control

Java Mission Control (JMC) giúp phân tích recording của JFR, xem event, thread, allocation và latency. Có thể dùng để xác định khoảng thời gian xảy ra vấn đề.

### 17.3. async-profiler

async-profiler có thể lấy CPU, allocation, lock và wall-clock profile trên JVM. Nó thường tạo flame graph và hỗ trợ phân tích native stack tùy môi trường.

### 17.4. JDK Mission Control và JFR events

Các event như execution sample, allocation sample, monitor enter, thread park và GC pause giúp phân tích nhiều loại bottleneck. Cần chọn event phù hợp để tránh thu thập quá nhiều dữ liệu.

### 17.5. JMH

Java Microbenchmark Harness (JMH) phù hợp để viết microbenchmark JVM. Nó xử lý nhiều vấn đề như warmup, fork, measurement iteration và dead-code elimination.

### 17.6. JFR command line

Có thể bắt đầu recording bằng công cụ JDK:

~~~bash
jcmd <pid> JFR.start name=dsl-profile settings=profile duration=60s filename=dsl-profile.jfr
~~~

Lệnh minh họa cần điều chỉnh theo JDK, quyền truy cập và process thực tế.

### 17.7. Heap dump

Khi cần điều tra retained heap, có thể tạo heap dump rồi phân tích bằng công cụ tương thích. Heap dump có thể chứa dữ liệu nhạy cảm trong memory, vì vậy cần bảo vệ file và xóa theo retention policy.

### 17.8. Native memory tracking

Nếu RSS lớn hơn nhiều so với heap, native memory tracking hoặc OS-level profiler có thể giúp phân tích direct buffer, thread stack, code cache và native allocation.

## 18. Công cụ profiling ở các tầng khác

Không phải mọi bottleneck đều nằm trong JVM.

### 18.1. OS tools

Công cụ hệ điều hành có thể cho biết:
- CPU utilization.
- Context switch.
- Page fault.
- Disk I/O.
- Network I/O.
- Process RSS.
- Thread state.

### 18.2. Linux perf

perf có thể thu thập hardware counter, CPU sample và call stack ở mức hệ điều hành. Nó hữu ích khi cần tìm cache miss, branch misprediction hoặc native hotspot.

### 18.3. eBPF-based profiling

Một số profiler dùng eBPF để quan sát process và kernel với overhead thấp trong nhiều tình huống. Cần kiểm tra kernel support, quyền và chính sách bảo mật.

### 18.4. Database profiler

Database execution plan, slow query log và wait statistics giúp xác định query nào gây tải. Cần liên kết query fingerprint với DSL query ID, tránh log literal nhạy cảm.

### 18.5. Distributed tracing backend

Trace viewer giúp so sánh các span và dependency latency. Có thể dùng trace để tìm service chậm trước khi mở CPU profile của service đó.

### 18.6. Application metrics

Metric trong compiler và runtime nên dùng tên, đơn vị và label thống nhất. Có thể export qua OpenTelemetry hoặc hệ thống metrics sẵn có.

## 19. Instrumentation trong compiler và runtime

Instrumentation được đặt tại ranh giới có ý nghĩa và không nên làm thay đổi semantics.

### 19.1. Phase timer

Có thể tạo timer quanh từng compiler phase:

~~~java
try (var ignored = profiler.start("dsl.typeCheck")) {
    typeChecker.check(module);
}
~~~

Profiler có thể ghi elapsed time, count và outcome.

### 19.2. Nested span

Một phase có thể tạo span con cho symbol resolution, constraint solving và overload resolution. Không cần tạo span cho mọi AST node trong production.

### 19.3. Counters

Đếm:
- Số token.
- Số AST node.
- Số symbol lookup.
- Số constraint.
- Số generated instruction.
- Số cache hit.
- Số diagnostic.

Các counter giúp giải thích vì sao workload lớn hơn hoặc algorithm thực hiện nhiều công việc hơn.

### 19.4. Histograms

Histogram phù hợp với:
- Parse duration.
- Type-check duration.
- Host-call latency.
- Query duration.
- Workflow execution time.
- Allocation size nếu backend hỗ trợ.

### 19.5. Context propagation

Giữ run ID, trace ID, project ID và artifact version qua các stage. Không đưa giá trị có cardinality cao vào metric label.

### 19.6. Sampling và overhead

Instrumentation chi tiết có thể gây overhead. Có thể:
- Tắt debug instrumentation mặc định.
- Sampling một tỷ lệ execution.
- Bật profile khi vượt ngưỡng.
- Giới hạn số event.
- Ghi summary thay vì mỗi operation.

### 19.7. Measurement boundary

Dùng monotonic clock cho duration. Tránh tính elapsed time bằng wall clock vì đồng hồ có thể thay đổi.

## 20. Phân tích bottleneck

Một bottleneck là thành phần giới hạn hiệu năng của toàn hệ thống trong workload cụ thể.

### 20.1. CPU-bound

Dấu hiệu:
- CPU utilization cao.
- Thread chủ yếu RUNNABLE.
- CPU profile có hotspot rõ.
- Throughput tăng ít khi thêm I/O concurrency.

Hướng điều tra: algorithmic complexity, allocation, repeated traversal, expensive conversion hoặc JIT behavior.

### 20.2. I/O-bound

Dấu hiệu:
- CPU utilization thấp.
- Wall-clock cao.
- Trace có span chờ database hoặc API.
- Thread ở WAITING hoặc socket read.

Hướng điều tra: batching, connection pool, network latency, query plan và timeout.

### 20.3. Memory-bound

Dấu hiệu:
- Allocation rate cao.
- GC thường xuyên.
- RSS hoặc heap gần giới hạn.
- Latency spike trùng GC.
- OOM hoặc swapping.

Hướng điều tra: object churn, retained object, cache, collection size và heap configuration.

### 20.4. Lock-bound

Dấu hiệu:
- Nhiều thread BLOCKED hoặc parked trên cùng lock.
- CPU không cao nhưng throughput thấp.
- Contention profile có monitor hotspot.

Hướng điều tra: lock scope, shared mutable state, cache synchronization và parallelism.

### 20.5. Queue-bound

Dấu hiệu:
- Queue depth tăng.
- Worker bận hoặc thiếu.
- Queue wait chiếm phần lớn latency.
- Execution time của task không tăng tương ứng.

Hướng điều tra: worker capacity, scheduling, backpressure và tenant fairness.

### 20.6. Algorithmic bottleneck

Một thuật toán O(n²) có thể hoạt động tốt với input nhỏ nhưng chậm đột ngột khi kích thước tăng. Hãy benchmark nhiều kích thước để xem scaling curve.

### 20.7. Amdahl’s law

Amdahl’s law cho biết giới hạn tăng tốc khi chỉ tối ưu một phần chương trình. Nếu 20% thời gian là phần có thể tăng tốc vô hạn, tổng speedup tối đa chỉ là:

\[
S = \frac{1}{(1 - P) + \frac{P}{N}}
\]

Trong đó P là tỷ lệ thời gian được cải thiện và N là hệ số tăng tốc của phần đó.

Nếu chỉ tối ưu một đoạn chiếm 10% tổng thời gian, dù đoạn đó nhanh hơn 10 lần, cải thiện tổng thể vẫn bị giới hạn.

## 21. Tối ưu compiler và DSL runtime

Sau khi xác định bottleneck, có thể chọn tối ưu phù hợp.

### 21.1. Giảm repeated traversal

Nếu nhiều phase duyệt toàn bộ AST để tìm cùng thông tin, có thể xây index hoặc annotation cache. Cần invalidation đúng khi AST thay đổi.

### 21.2. Symbol table

Dùng cấu trúc dữ liệu phù hợp cho lookup. Hash map có average lookup tốt, nhưng cần cân nhắc memory, collision và thứ tự deterministic nếu semantics yêu cầu.

### 21.3. Type cache

Cache kết quả type inference hoặc substitution có thể giảm công việc lặp. Cache key phải phản ánh type environment và version; cache sai có thể tạo lỗi correctness.

### 21.4. Incremental compilation

Chỉ compile lại phần bị ảnh hưởng bởi thay đổi. Dependency graph cần chính xác để tránh invalidating quá rộng hoặc giữ kết quả stale.

### 21.5. IR optimization

Chạy optimization pass có chọn lọc theo target và workload. Đo compile cost và runtime benefit riêng.

### 21.6. Code generation

Giảm string copy, dùng writer hoặc buffer phù hợp, tránh serialize cùng một metadata nhiều lần và cân nhắc streaming output cho artifact lớn.

### 21.7. Runtime dispatch

Nếu interpreter dispatch node qua nhiều tầng virtual call, có thể cân nhắc opcode representation hoặc specialized evaluator. Cần đo trước và sau để tránh tăng độ phức tạp không có lợi.

### 21.8. Object layout

Giảm object wrapper và boxing khi profile cho thấy allocation hotspot. Dùng primitive array hoặc compact representation nếu phù hợp với semantics và maintainability.

### 21.9. Cache

Cache immutable metadata hoặc compiled artifact khi có key ổn định. Cần eviction, size limit, invalidation và tenant scope.

### 21.10. Query optimization

Push filter xuống nguồn, project đúng field, tránh N+1, batch request và dùng index phù hợp. Luôn xác minh query plan và semantics của null, ordering, collation.

## 22. Tối ưu mà không làm sai ngữ nghĩa

Một tối ưu chỉ có giá trị nếu giữ nguyên kết quả quan sát được theo contract của DSL.

### 22.1. Correctness first

Sau mỗi thay đổi, chạy test tương đương, regression test và workload đại diện. Với compiler, so sánh output hoặc semantic behavior.

### 22.2. Floating-point

Reordering phép cộng số thực có thể thay đổi rounding. Constant folding cần tuân theo numeric semantics của DSL.

### 22.3. Evaluation order

Lazy evaluation, short-circuit và side effect có thể làm thay đổi kết quả nếu optimizer đổi thứ tự biểu thức.

### 22.4. Exception behavior

Loại bỏ expression hoặc đẩy predicate có thể làm thay đổi thời điểm exception xuất hiện. Cần đặc tả error semantics.

### 22.5. Cache invalidation

Cache phải gắn với source version, compiler version, dependency và relevant configuration. Nếu key thiếu một yếu tố, output stale có thể được tái sử dụng.

### 22.6. Concurrency

Một tối ưu dùng shared cache hoặc parallel phase có thể tạo race. Kiểm thử thread safety và deterministic output.

### 22.7. Resource limits

Tối ưu có thể làm một workload tiêu thụ ít CPU hơn nhưng tăng memory. Đánh giá nhiều chỉ số thay vì chỉ một.

## 23. So sánh và diễn giải kết quả

Kết quả benchmark cần được trình bày cùng bối cảnh.

### 23.1. Absolute và relative change

Nếu thời gian giảm từ 200 ms xuống 160 ms:
- Absolute improvement: 40 ms.
- Relative reduction: 20%.
- Speedup: 1,25 lần.

Nêu rõ đang dùng cách diễn đạt nào.

### 23.2. Noise

Các yếu tố gây noise:
- Background process.
- CPU frequency scaling.
- JIT compilation.
- GC timing.
- File system cache.
- Network variance.
- Thermal throttling.
- Shared CI worker.

Lặp lại phép đo và dùng môi trường ổn định.

### 23.3. Confidence

Báo số lần chạy, độ phân tán hoặc confidence interval khi có thể. Không tuyên bố cải thiện 1% nếu noise của benchmark lớn hơn mức đó.

### 23.4. Regression budget

Một thay đổi có thể làm compile time tăng nhẹ nhưng runtime giảm mạnh. Nhóm cần xác định trade-off chấp nhận được theo use case và SLO.

### 23.5. So sánh cùng workload

Không so sánh hai kết quả có input size, cache state, toolchain hoặc machine khác nhau mà không hiệu chỉnh.

### 23.6. Kết quả không cải thiện

Nếu thay đổi không cải thiện, hãy ghi nhận và bỏ hoặc thiết kế lại. Không giữ tối ưu chỉ vì nó có vẻ tinh vi.

## 24. Theo dõi performance regression

Performance regression là suy giảm hiệu năng sau một thay đổi source, dependency, cấu hình hoặc hạ tầng.

### 24.1. Benchmark trong CI

Có thể chạy một bộ benchmark nhỏ trong CI và một bộ đầy đủ theo lịch hoặc trước release. CI benchmark cần đủ ổn định để không tạo false alarm.

### 24.2. Threshold

Đặt threshold theo baseline và noise. Ví dụ, cảnh báo khi p95 tăng hơn một tỷ lệ nhất định qua nhiều lần chạy hoặc khi memory footprint vượt budget.

### 24.3. Trend

Lưu kết quả theo commit và compiler version để nhìn xu hướng. Một regression nhỏ lặp lại qua nhiều commit có thể trở thành vấn đề lớn.

### 24.4. Baseline update

Chỉ cập nhật baseline khi đã hiểu thay đổi và chấp nhận trade-off. Không tự động chấp nhận mọi kết quả mới làm baseline.

### 24.5. Environment consistency

CI benchmark nên dùng worker có cấu hình ổn định, hoặc ít nhất ghi machine metadata và phân nhóm kết quả theo loại máy.

### 24.6. Performance test failure

Khi vượt threshold, lưu raw data, trace hoặc profile tương ứng nếu có thể. Một con số đỏ mà không có bằng chứng bổ sung sẽ khó điều tra.

## 25. Ví dụ: đo đạc parser DSL

Giả sử parser có nhiệm vụ chuyển source thành AST.

### 25.1. Câu hỏi đo

- Parser xử lý bao nhiêu byte mỗi giây?
- Thời gian tăng thế nào theo số token?
- AST allocation chiếm bao nhiêu memory?
- Error recovery làm chi phí tăng bao nhiêu?
- Cache có cải thiện repeated parse không?

### 25.2. Workload

Tạo các file:
- 1 KB với expression đơn giản.
- 50 KB với nhiều declaration.
- 500 KB với nhiều nested expression.
- File lỗi cú pháp ở đầu, giữa và cuối.
- Nhiều file import chung module.

### 25.3. Instrumentation

~~~java
long start = System.nanoTime();
ParseResult result = parser.parse(source);
long elapsed = System.nanoTime() - start;

metrics.recordParseDuration(elapsed);
metrics.recordTokenCount(result.tokenCount());
metrics.recordAstNodeCount(result.nodeCount());
metrics.recordDiagnosticCount(result.diagnostics().size());
~~~

Trong production, instrumentation cần được thiết kế để không tạo object hoặc log quá nhiều cho mỗi node.

### 25.4. Kết quả minh họa

| Source size | Parse time | AST nodes | Peak heap delta |
| ---: | ---: | ---: | ---: |
| 1 KB | 0,8 ms | 120 | 0,2 MB |
| 50 KB | 14 ms | 6.800 | 4,5 MB |
| 500 KB | 210 ms | 72.000 | 41 MB |

Các số liệu chỉ minh họa. Nếu thời gian tăng nhanh hơn kích thước source, hãy profile tokenization, lookahead, backtracking, error recovery và AST allocation.

### 25.5. Profiling

CPU profile có thể cho thấy parser dành nhiều thời gian ở lookahead hoặc string comparison. Allocation profile có thể cho thấy mỗi token tạo nhiều substring.

### 25.6. Tối ưu và xác nhận

Sau khi thay đổi tokenizer hoặc AST representation, chạy lại cùng workload, xác minh AST tương đương và so sánh latency, allocation, memory và error recovery.

## 26. Ví dụ: profiling type checker

Type checker có thể chậm khi chương trình có generic, overload hoặc biểu thức lồng nhau.

### 26.1. Chỉ số cần đo

- Số expression.
- Số type constraint.
- Số lần unify.
- Số overload candidate.
- Số substitution.
- Cache hit/miss.
- Thời gian resolve symbol.
- Thời gian solve constraint.

### 26.2. Trace theo phase

~~~text
semantic.check
  resolve.imports
  resolve.symbols
  infer.expression
    collect.constraints
    solve.constraints
    resolve.overload
  validate.assignments
~~~

### 26.3. Tìm hotspot

Nếu resolve.overload chiếm phần lớn CPU, hãy xem số candidate, cách lọc theo arity và type compatibility. Nếu collect.constraints tăng nhanh theo độ sâu, xem xét memoization hoặc representation.

### 26.4. Scaling experiment

Tăng số declaration theo các mức 100, 500, 1000 và 5000. Ghi thời gian, memory và số constraint. Quan sát scaling curve để phát hiện algorithmic complexity.

### 26.5. Cache experiment

So sánh cold run và warm run, nhưng kiểm tra cache invalidation khi thay đổi type declaration. Không đánh đổi correctness để có cache hit cao.

## 27. Ví dụ: profiling DSL runtime

Giả sử một rule được chạy cho 100.000 record.

### 27.1. End-to-end measurement

Đo:
- Input loading.
- Rule loading.
- Evaluation.
- Host function.
- Result serialization.
- Total duration.

### 27.2. Throughput

~~~text
throughput = completed_records / elapsed_seconds
~~~

Ghi cả số record lỗi và record bị bỏ qua để throughput không che giấu kết quả thiếu.

### 27.3. CPU profile

Nếu evaluator chiếm nhiều CPU, xem dispatch và environment lookup. Nếu host function chiếm phần lớn, kiểm tra database hoặc API.

### 27.4. Allocation profile

Nếu mỗi record tạo một map, list và wrapper object, allocation rate có thể cao. Xem có thể dùng record layout compact hoặc tái sử dụng immutable metadata không.

### 27.5. Concurrency

Chạy với 1, 2, 4 và 8 worker. Ghi throughput, p95 latency, CPU, memory và contention. Throughput không tăng tuyến tính có thể do lock, memory bandwidth hoặc dependency saturation.

### 27.6. Correctness

Sau mỗi tối ưu, so sánh output trên tập input cố định, bao gồm null, boundary value, error case và side effect policy.

## 28. Quy trình profiling và tối ưu

Một quy trình có thể lặp lại:

1. Xác định triệu chứng và phạm vi.
2. Chọn workload đại diện.
3. Đặt giả thuyết và chỉ số.
4. Đo baseline.
5. Thu profile phù hợp.
6. Tìm bottleneck lớn nhất có thể tác động.
7. Thay đổi một yếu tố.
8. Chạy test correctness.
9. Đo lại trong cùng điều kiện.
10. Ghi kết quả và quyết định giữ hoặc bỏ tối ưu.

### 28.1. Chọn profiler theo triệu chứng

| Triệu chứng | Công cụ hoặc dữ liệu phù hợp |
| --- | --- |
| CPU cao | CPU sampling, flame graph |
| Heap tăng liên tục | Heap dump, retained heap |
| GC nhiều | GC log, allocation profile |
| Thread chờ lâu | Thread dump, lock profile, trace |
| Query chậm | Query plan, database statistics |
| Network latency | Distributed trace, network metrics |
| Startup chậm | Startup trace, class loading profile |
| RSS cao hơn heap | Native memory tracking, OS profiler |

### 28.2. Tối ưu từng bottleneck

Ưu tiên bottleneck có tỷ trọng lớn, ảnh hưởng nhiều workload và có giải pháp rủi ro thấp. Tránh tối ưu code hiếm khi chạy chỉ vì nó dễ sửa.

### 28.3. Ghi lại kết quả

Mỗi tối ưu nên lưu:
- Vấn đề ban đầu.
- Workload.
- Baseline.
- Profile evidence.
- Thay đổi.
- Kết quả sau thay đổi.
- Correctness evidence.
- Trade-off.
- Machine và toolchain metadata.

## 29. Những lỗi thường gặp khi đo đạc và profiling

**Chỉ đo thời gian tổng thể.** Không biết phase nào gây chậm. Hãy tách compiler, runtime, I/O và queue wait.

**Chỉ dùng average.** Tail latency có thể rất xấu dù average thấp. Hãy báo median và percentile cùng sample count.

**Benchmark không có warmup.** JIT và class loading làm kết quả JVM không ổn định. Hãy đo cold và warm path riêng.

**Dùng workload quá nhỏ.** Overhead và algorithmic scaling không lộ ra. Hãy đo nhiều kích thước và cấu trúc.

**Profile với instrumentation quá nặng.** Công cụ có thể thay đổi hành vi cần đo. Hãy hiểu overhead và dùng sampling hoặc mức chi tiết phù hợp.

**Tối ưu theo một flame graph.** Profile chỉ phản ánh workload và thời điểm cụ thể. Hãy xác nhận bằng benchmark lặp lại.

**Nhầm wall-clock với CPU time.** Chờ I/O bị hiểu nhầm là tính toán chậm. Hãy xem thread state và trace.

**Nhầm high allocation với memory leak.** Object churn và retained object cần cách xử lý khác nhau. Hãy dùng allocation profile và heap dump.

**Không kiểm tra correctness.** Tối ưu có thể đổi thứ tự evaluation hoặc null semantics. Hãy chạy regression test và so sánh output.

**Không lưu environment metadata.** Khó tái lập và so sánh. Hãy ghi machine, JVM, flags, source revision và workload version.

**Chỉ tối ưu compile time.** Có thể làm runtime chậm hơn hoặc ngược lại. Hãy đo cả chi phí compile và execute.

**Bỏ qua external dependency.** Compiler hoặc runtime có thể chỉ đang chờ database hay service. Hãy tách dependency latency.

**Không theo dõi regression.** Một cải thiện hôm nay có thể bị mất trong commit sau. Hãy duy trì benchmark suite và trend.

## 30. Xây dựng chiến lược performance engineering cho DSL

Để đo đạc trở thành hoạt động liên tục, cần kết hợp benchmark, profiling, monitoring và ngân sách hiệu năng.

### 30.1. Định nghĩa performance budget

Có thể đặt budget cho:
- Editor response khi validate.
- Cold compile.
- Incremental compile.
- Runtime expression.
- Query execution.
- Memory per worker.
- Startup.
- Deployment pipeline.

Budget cần dựa trên trải nghiệm và tải thực tế, không chỉ khả năng máy phát triển.

### 30.2. Tạo benchmark suite ổn định

Giữ workload version trong repository hoặc artifact riêng. Mỗi benchmark cần mô tả mục đích, input, setup, warmup và output correctness.

### 30.3. Theo dõi production

Thu metric và trace với cardinality hợp lý. Chọn sampling để điều tra request chậm hoặc lỗi mà không tạo chi phí telemetry quá lớn.

### 30.4. Performance review

Với thay đổi ảnh hưởng compiler hoặc runtime, xem xét:
- Độ phức tạp thuật toán.
- Allocation.
- Cache behavior.
- Concurrency.
- Compatibility.
- Correctness.
- Performance impact trên workload đại diện.

### 30.5. Incident learning

Sau sự cố hiệu năng, bổ sung benchmark tái hiện regression, metric hoặc trace còn thiếu và alert phù hợp. Không chỉ sửa một case mà bỏ qua cách phát hiện lần sau.

### 30.6. Không tối ưu quá sớm

Tối ưu nên dựa trên profile và yêu cầu. Code đơn giản, dễ hiểu thường là lựa chọn tốt cho đến khi số liệu chứng minh có bottleneck cần giải quyết.

## 31. Kết luận

Đo đạc và profiling giúp hiểu hiệu năng của DSL từ parser, semantic analysis, optimizer và code generator đến runtime, query engine và dịch vụ bên ngoài. Measurement cho biết latency, throughput, CPU, memory và allocation; profiling chỉ ra call path và tài nguyên gây ra chi phí. Benchmark có kiểm soát cho phép so sánh các phiên bản, còn monitoring theo dõi hành vi trong môi trường vận hành.

Một quy trình hiệu quả cần workload đại diện, baseline có thể tái lập, percentile và sample count phù hợp, profiler được chọn theo triệu chứng và kiểm tra correctness sau tối ưu. Với JVM, JFR, JMC, async-profiler và JMH là những công cụ hữu ích; OS profiler, database plan và distributed trace bổ sung góc nhìn khi bottleneck nằm ngoài Java code.

Hãy đo trước khi tối ưu, dùng profile để tìm nguyên nhân, thay đổi có mục tiêu và đo lại trong cùng điều kiện. Khi benchmark và telemetry trở thành một phần của vòng đời phát triển DSL, nhóm có thể phát hiện regression sớm, sử dụng tài nguyên hiệu quả và cải thiện trải nghiệm mà vẫn giữ đúng semantics của ngôn ngữ.

