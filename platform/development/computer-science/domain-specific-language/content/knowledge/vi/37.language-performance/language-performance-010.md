# Đánh đổi hiệu năng

## 1. Đánh đổi hiệu năng trong DSL là gì?

Đánh đổi hiệu năng (performance trade-offs) là việc lựa chọn giữa các đặc tính có thể cạnh tranh nhau khi thiết kế, biên dịch và thực thi một DSL (Domain-Specific Language). Một lựa chọn giúp chương trình chạy nhanh hơn có thể làm compiler phức tạp hơn, tăng bộ nhớ, kéo dài thời gian khởi động, giảm tính linh hoạt hoặc khiến việc debug khó hơn.

DSL thường bổ sung một lớp trừu tượng giữa người viết chương trình và hệ thống thực thi. Lớp này có thể cung cấp cú pháp gần với nghiệp vụ, type checking, optimizer, query planner, workflow scheduler hoặc code generator. Mỗi lớp có chi phí riêng và cũng tạo cơ hội tối ưu.

Ví dụ, một query DSL có thể cho phép:

~~~text
from Orders
where status == APPROVED
  and total > threshold
select orderId, total
order by total descending
limit 100
~~~

Engine có thể parse query, kiểm tra schema, xây dựng logical plan, chọn index, đẩy filter xuống database và chỉ lấy hai field cần thiết. Những bước phân tích làm tăng chi phí trước khi thực thi, nhưng có thể giảm lượng dữ liệu đọc và tổng thời gian chạy.

Đánh đổi hiệu năng không có một đáp án tối ưu cho mọi DSL. Cần xác định mục tiêu như latency, throughput, memory, startup time, build time, chi phí hạ tầng, khả năng mở rộng và độ dễ bảo trì; sau đó đo trên workload đại diện để lựa chọn.

## 2. Vì sao DSL cần xem xét đánh đổi hiệu năng?

Một DSL có thể phục vụ nhiều mục tiêu:

- Giúp người dùng biểu đạt logic nghiệp vụ dễ đọc.
- Phát hiện lỗi trước khi chạy.
- Cho phép optimizer hiểu ý định của chương trình.
- Hỗ trợ nhiều backend hoặc runtime.
- Tạo code hoặc artifact tối ưu.
- Cung cấp tooling như completion, diagnostics và debugger.
- Bảo vệ hệ thống bằng giới hạn tài nguyên.

Những mục tiêu đó có thể xung đột. Chẳng hạn, type inference phong phú giúp giảm annotation nhưng làm compile time tăng. JIT compilation có thể tăng throughput sau warm-up nhưng làm startup chậm và dùng thêm memory. Caching giảm thời gian xử lý lặp lại nhưng cần RAM và invalidation chính xác.

Phân tích trade-off giúp nhóm:

1. Chọn đúng mục tiêu hiệu năng theo use case.
2. Tránh tối ưu một chỉ số làm suy giảm trải nghiệm tổng thể.
3. Hiểu chi phí của abstraction và runtime services.
4. Quyết định phần nào nên xử lý lúc compile và phần nào lúc runtime.
5. Xác định giới hạn an toàn cho input và workload.
6. Ưu tiên tối ưu dựa trên dữ liệu đo được.
7. Duy trì tính dễ hiểu và khả năng tiến hóa của DSL.

## 3. Các chỉ số hiệu năng cần phân biệt

Không nên dùng một con số duy nhất để đánh giá hiệu năng. Các chỉ số phản ánh những khía cạnh khác nhau:

| Chỉ số | Ý nghĩa | Ví dụ |
|---|---|---|
| Startup time | Thời gian từ lúc khởi chạy tới khi sẵn sàng | Runtime bắt đầu xử lý workflow |
| Parse time | Thời gian phân tích cú pháp | Parse một file DSL |
| Compile time | Thời gian tạo artifact | Build toàn bộ module |
| Time to first result | Thời gian tới kết quả đầu tiên | Query stream trả record đầu |
| Latency | Thời gian hoàn thành một request | Một query mất 120 ms |
| Throughput | Số request hoặc đơn vị công việc mỗi thời gian | 2.000 query/giây |
| CPU usage | Lượng thời gian xử lý của CPU | CPU seconds mỗi query |
| Memory footprint | Bộ nhớ cần dùng | Heap của language server |
| Allocation rate | Tốc độ tạo object | MB allocation/giây |
| GC pause | Thời gian dừng do garbage collection | p99 pause |
| I/O volume | Lượng dữ liệu đọc/ghi | MB từ database |
| Cost per operation | Chi phí tài nguyên cho mỗi thao tác | CPU, storage hoặc cloud cost |

Latency và throughput không đồng nghĩa. Một hệ thống có thể xử lý nhiều request hơn mỗi giây nhưng latency của từng request lại tăng khi tải cao. Startup time cũng khác steady-state throughput: lựa chọn tốt cho service chạy liên tục có thể không phù hợp với CLI khởi động rồi thoát ngay.

### 3.1. Percentile thay vì chỉ average

Average latency có thể che giấu những request rất chậm. Nên xem các percentile như p50, p95 và p99 cùng với maximum khi phù hợp.

- p50 phản ánh trải nghiệm của request điển hình.
- p95 cho biết nhóm request chậm hơn đáng kể.
- p99 giúp nhìn tail latency và các trường hợp hiếm nhưng ảnh hưởng lớn.

Một DSL runtime có average execution 20 ms nhưng p99 là 4 giây có thể gây timeout trong hệ thống workflow. Tối ưu average mà không hiểu tail latency có thể không giải quyết được vấn đề thực tế.

### 3.2. Hiệu năng theo workload

Một benchmark chỉ có ý nghĩa trong phạm vi workload được đo. Cần mô tả:

- Kích thước source hoặc query.
- Số lượng module và dependency.
- Độ sâu AST hoặc workflow.
- Số record và phân bố dữ liệu.
- Tỷ lệ cache hit.
- Số request đồng thời.
- Warm-up state.
- Phần cứng và runtime version.

Không nên kết luận compiler nhanh hơn chỉ từ một chương trình nhỏ nếu workload thực tế chứa hàng nghìn module và dependency lớn.

## 4. Hiệu năng và tính biểu đạt của ngôn ngữ

Một DSL càng biểu đạt mạnh thì càng có nhiều cấu trúc cần phân tích và thực thi. Macro, generic, overload, reflection, dynamic dispatch và type inference làm ngôn ngữ linh hoạt hơn nhưng có thể tăng chi phí compiler hoặc runtime.

Ví dụ, một biểu thức miền:

~~~text
where invoice.isOverdue(asOf = currentBusinessDate())
~~~

có thể dễ đọc hơn biểu thức so sánh nhiều field. Tuy nhiên, compiler cần resolve function, kiểm tra kiểu và runtime phải xác định semantics của business calendar.

Các lựa chọn:

- Cú pháp ngắn gọn giúp người dùng viết nhanh nhưng có thể cần inference phức tạp.
- Cú pháp tường minh có thể giảm công việc suy luận nhưng làm source dài hơn.
- Abstraction cấp cao giúp tái sử dụng nhưng có thể che chi phí thực thi.
- Cú pháp chuyên biệt cho phép tối ưu nhưng tăng số quy tắc grammar cần duy trì.

Không nên loại bỏ abstraction chỉ vì nó có overhead lý thuyết. Cần đo xem overhead có đáng kể trong workload hay không và cân nhắc lợi ích về khả năng đọc, an toàn và bảo trì.

## 5. Compile-time work và runtime work

Một quyết định quan trọng là thực hiện công việc ở thời điểm biên dịch hay thời điểm chạy.

### 5.1. Đưa công việc về compile time

Compiler có thể:

- Resolve tên và module.
- Kiểm tra kiểu.
- Tính constant expression.
- Tạo query plan tĩnh.
- Sinh code cho target runtime.
- Phát hiện lỗi có thể xác định trước.

Ưu điểm:

- Giảm công việc runtime.
- Phát hiện lỗi sớm.
- Có thể tạo artifact chuyên biệt.
- Runtime đơn giản hơn.

Đánh đổi:

- Build lâu hơn.
- Compiler cần nhiều memory.
- Thay đổi schema hoặc dependency có thể buộc compile lại.
- Tính linh hoạt runtime giảm nếu nhiều giá trị chỉ biết lúc chạy.

### 5.2. Đưa công việc về runtime

Runtime có thể resolve dynamic value, chọn backend, kiểm tra policy hoặc tạo plan theo dữ liệu thực tế.

Ưu điểm:

- Linh hoạt khi cấu hình và dữ liệu thay đổi.
- Không cần compile lại cho mọi thay đổi nhỏ.
- Có thể chọn chiến lược theo trạng thái runtime.

Đánh đổi:

- Tăng startup hoặc request latency.
- Có thể lặp lại công việc ở mỗi execution.
- Lỗi chỉ xuất hiện khi chạy.
- Cần cache hoặc tối ưu bổ sung.

### 5.3. Hybrid

Một kiến trúc phổ biến là phân tích tĩnh phần có thể biết trước, rồi để runtime hoàn tất phần phụ thuộc vào dữ liệu và môi trường:

~~~text
DSL source
    |
    v
Parse and type check at build time
    |
    v
Compiled query template
    |
    v
Bind runtime parameters
    |
    v
Execute against selected backend
~~~

Hybrid thường cân bằng giữa an toàn, tốc độ và tính linh hoạt.

## 6. Interpreter, bytecode và native code

DSL có thể được thực thi bằng interpreter, bytecode virtual machine hoặc code được biên dịch sang native code.

| Cách thực thi | Ưu điểm | Đánh đổi |
|---|---|---|
| Tree-walking interpreter | Dễ triển khai, linh hoạt, lỗi gắn với AST | Mỗi node cần dispatch; overhead có thể cao |
| Bytecode VM | Instruction compact, dispatch thống nhất | Cần compiler bytecode và VM |
| JIT compilation | Tối ưu theo hành vi runtime | Warm-up, memory và độ phức tạp |
| Ahead-of-time compilation | Startup nhanh, không cần JIT lúc chạy | Build target-specific, artifact lớn hoặc ít linh hoạt |
| Transpilation | Tận dụng compiler/runtime khác | Phụ thuộc target và mapping semantics |

### 6.1. Tree-walking interpreter

Interpreter đi qua AST và thực thi từng node. Đây là cách phù hợp để tạo prototype, DSL nhỏ hoặc môi trường cần tương tác nhanh.

Khi chương trình lớn, chi phí virtual dispatch, object allocation và truy cập cấu trúc AST có thể đáng kể. Có thể giảm overhead bằng visitor chuyên biệt, compact node representation hoặc compile AST sang bytecode.

### 6.2. Bytecode

Bytecode chuyển cấu trúc DSL thành tập instruction nhỏ:

~~~text
LOAD_FIELD total
LOAD_CONST threshold
GREATER_THAN
JUMP_IF_FALSE 18
CALL approveOrder
~~~

VM có thể dispatch instruction hiệu quả và cache thông tin đã resolve. Đổi lại, cần thiết kế instruction set, verifier, stack model, source map và version format.

### 6.3. JIT

JIT có thể tối ưu code nóng dựa trên kiểu và hành vi quan sát được. Nó phù hợp với workload dài hoặc lặp nhiều lần.

Chi phí gồm:

- Compilation warm-up.
- Code cache.
- Profiling overhead.
- Memory cho machine code.
- Deoptimization khi giả định không còn đúng.
- Khó tái lập hiệu năng trong benchmark ngắn.

### 6.4. AOT

Ahead-of-time compilation chuyển code trước khi triển khai. Nó có thể giảm startup và loại bỏ JIT overhead. Nhưng target platform, runtime ABI và native dependency cần được quản lý; build có thể chậm hơn và artifact cần được tạo riêng cho từng target.

## 7. Tối ưu parser và AST

Parser là một trong những bước đầu tiên của toolchain. Với file lớn hoặc language server xử lý liên tục, parse time và memory của AST có thể ảnh hưởng rõ tới trải nghiệm.

Các đánh đổi:

- Parser đơn giản dễ bảo trì nhưng có thể tạo nhiều object.
- Parser generator tăng tính nhất quán nhưng generated code có thể lớn.
- AST giàu metadata hỗ trợ diagnostics và tooling nhưng tốn memory.
- CST giữ punctuation và trivia tốt hơn nhưng thường lớn hơn AST tối giản.

### 7.1. AST compact

Có thể dùng node kind dạng enum, source span dạng integer và child array liên tục thay cho mỗi node là một object có nhiều field riêng.

Ưu điểm:

- Giảm object overhead.
- Tăng locality của memory.
- Có thể cải thiện cache CPU.

Đánh đổi:

- Code truy cập node phức tạp hơn.
- Khó lưu metadata tùy biến.
- Cần quản lý lifetime của source buffer và node arena.

### 7.2. Arena allocation

Arena cấp phát nhiều node từ một vùng memory và giải phóng cả vùng khi document version bị thay thế. Cách này có thể giảm chi phí allocation nhỏ lẻ.

Nó phù hợp với AST có vòng đời gắn với một lần parse. Tuy nhiên, nếu một node cần tồn tại lâu hơn arena hoặc được chia sẻ giữa nhiều document version, cần ownership rõ ràng để tránh dangling reference.

### 7.3. Incremental parsing

Thay vì parse lại toàn bộ file sau mỗi ký tự, parser incremental cập nhật vùng bị ảnh hưởng. Nó có thể cải thiện language server khi file lớn và người dùng sửa thường xuyên.

Đánh đổi:

- Cần theo dõi source range và node reuse.
- Edit ở đầu file có thể làm thay đổi trạng thái nhiều dòng phía sau.
- Cache parse tree cần invalidation chính xác.
- Debug parser incremental phức tạp hơn full parse.

Nên dùng incremental parsing khi profiling cho thấy full parse là bottleneck hoặc độ trễ editor không đáp ứng mục tiêu.

## 8. Type checking và type inference

Type checking tĩnh phát hiện lỗi trước runtime nhưng có thể làm compile time tăng, đặc biệt với generic, overload, union type và biểu thức lồng nhau.

Ví dụ:

~~~text
let total = calculateTotal(order)
let tax = total * taxRate
~~~

Type inference có thể suy ra kiểu mà không cần annotation cho mọi biến. Tuy nhiên, thuật toán inference phức tạp có thể tạo constraint graph lớn và thời gian giải constraint tăng nhanh với biểu thức phức tạp.

### 8.1. Annotation và inference

| Lựa chọn | Lợi ích | Chi phí |
|---|---|---|
| Annotation tường minh | Dễ đọc type contract, giảm suy luận | Source dài hơn |
| Inference cục bộ | Ít annotation, thường dễ kiểm soát | Compiler phải suy luận |
| Inference toàn cục | Linh hoạt cao | Có thể tăng thời gian và memory đáng kể |

Một DSL có thể ưu tiên inference cục bộ và yêu cầu annotation ở ranh giới function hoặc module để giữ compile time có thể dự đoán.

### 8.2. Incremental type checking

Khi một declaration thay đổi, compiler có thể chỉ kiểm tra lại module phụ thuộc. Điều này giảm thời gian feedback nhưng cần dependency graph chính xác và cache type result có version.

Nếu public signature thay đổi, các module tham chiếu có thể phải kiểm tra lại. Nếu chỉ đổi comment, type checking có thể không cần chạy lại.

## 9. Optimization và compile time

Compiler optimizer có thể cải thiện runtime nhưng làm build lâu hơn.

Các tối ưu hóa thường gặp:

- Constant folding.
- Dead code elimination.
- Common subexpression elimination.
- Inlining.
- Loop optimization.
- Specialization.
- Escape analysis.
- Query plan optimization.
- Function fusion.

### 9.1. Optimization level

Có thể cung cấp các mức:

| Mức | Mục tiêu | Trade-off |
|---|---|---|
| O0 | Compile nhanh, debug dễ | Runtime có thể chậm |
| O1 | Tối ưu cơ bản | Chi phí compile vừa phải |
| O2 | Tối ưu sâu hơn | Compile lâu hơn, artifact có thể lớn |
| O3 | Tối ưu mạnh cho throughput | Có thể tăng code size và warm-up |
| Size | Giảm kích thước artifact | Có thể giảm tốc độ thực thi |

Tên mức chỉ là convention. Mỗi compiler cần tài liệu hóa chính xác những pass được bật.

### 9.2. Inlining

Inlining thay lời gọi function bằng thân function tại call site. Nó có thể giảm call overhead và giúp optimizer nhìn xuyên qua abstraction.

Đánh đổi:

- Code size tăng.
- Instruction cache có thể kém hiệu quả.
- Compile time tăng.
- Debug stack và source mapping phức tạp hơn.

Inlining nên dựa trên kích thước, tần suất gọi và profiling thay vì áp dụng vô điều kiện.

### 9.3. Constant folding

Biểu thức chỉ gồm giá trị hằng có thể được tính lúc compile:

~~~text
let threshold = 100 * 10
~~~

Compiler có thể thay bằng 1000. Tuy nhiên, phép tính có overflow, rounding hoặc semantics phụ thuộc runtime cần được xử lý theo đúng quy tắc của DSL.

### 9.4. Optimization budget

Một compiler có thể đặt giới hạn thời gian hoặc độ sâu cho pass tối ưu. Khi vượt budget, nó có thể giữ plan ít tối ưu hơn nhưng vẫn hợp lệ. Điều này giúp compile time có giới hạn và tránh một query đặc biệt làm kẹt toàn bộ build.

## 10. Query planning và pushdown

Với query DSL, optimizer thường chuyển query thành logical plan rồi physical plan. Nó có thể chọn cách đọc dữ liệu và thứ tự thực hiện phép toán.

Ví dụ:

~~~text
from Orders
where region == "NORTH"
  and status == APPROVED
select orderId, total
~~~

Một plan kém có thể tải toàn bộ Orders rồi lọc trong memory. Một plan tốt có thể push predicate xuống database, dùng index và chỉ đọc hai field cần thiết.

### 10.1. Predicate pushdown

Đẩy filter tới backend giảm dữ liệu truyền qua network và lượng xử lý ở tầng ứng dụng. Nhưng chỉ an toàn khi semantics của phép so sánh giống nhau giữa DSL và backend.

Ví dụ, collation hoặc null semantics khác nhau có thể khiến predicate được pushdown trả tập kết quả khác. Engine cần biết capability và chỉ push phép toán tương đương.

### 10.2. Projection pushdown

Chỉ đọc các field được query sử dụng giúp giảm I/O và memory. Tuy nhiên, engine vẫn cần lấy field phục vụ join, filter, authorization hoặc ordering nếu các bước đó chưa được thực hiện tại backend.

### 10.3. Join reordering

Đổi thứ tự join có thể giảm intermediate result. Optimizer cần cardinality estimate và thống kê dữ liệu; nếu estimate sai, plan được chọn có thể chậm hơn.

### 10.4. Cost-based optimization

Optimizer có thể ước lượng:

- Số row.
- Kích thước dữ liệu.
- Selectivity của predicate.
- Chi phí network.
- Chi phí CPU và memory.
- Khả năng dùng index.

Statistics cần được cập nhật. Statistics cũ có thể dẫn đến plan kém dù query source không đổi.

## 11. Lazy evaluation và eager evaluation

Lazy evaluation chỉ tính giá trị khi thực sự cần; eager evaluation tính ngay khi biểu thức được tạo hoặc bước được gọi.

Ví dụ:

~~~text
let activeOrders = lazy {
    from Orders
    where status == APPROVED
}
~~~

Lazy query có thể trì hoãn việc đọc dữ liệu cho tới khi có consumer. Nếu nhiều bước nối tiếp được hợp nhất thành một query plan, engine có thể push filter và projection xuống nguồn.

### 11.1. Lợi ích của lazy evaluation

- Không tính toán dữ liệu không được sử dụng.
- Có thể hợp nhất nhiều phép biến đổi.
- Giảm intermediate collection.
- Hữu ích cho stream hoặc dữ liệu lớn.

### 11.2. Đánh đổi

- Lỗi có thể xuất hiện muộn hơn.
- Thời điểm thực thi khó nhận biết.
- Một query có thể bị chạy nhiều lần nếu không materialize.
- Resource có thể được giữ lâu hơn.
- Debug và đo latency từng bước khó hơn.

### 11.3. Eager materialization

Eager evaluation tạo kết quả ngay và có thể cache trong collection. Nó phù hợp khi dữ liệu nhỏ, cần snapshot ổn định hoặc kết quả được dùng nhiều lần.

Đổi lại, nó có thể đọc nhiều dữ liệu hơn cần thiết và giữ memory lâu hơn.

Lựa chọn lazy hay eager cần dựa trên kích thước dữ liệu, số lần dùng lại, yêu cầu consistency và khả năng pushdown.

## 12. Streaming và materialization

Streaming xử lý dữ liệu từng phần thay vì tải toàn bộ vào memory:

~~~text
from LargeEvents
where severity >= WARN
map to Alert
emit
~~~

Ưu điểm:

- Memory footprint thấp hơn.
- Có thể trả kết quả đầu sớm.
- Phù hợp dữ liệu lớn hoặc không giới hạn.
- Có thể tạo backpressure.

Đánh đổi:

- Một số phép toán cần giữ state như sort toàn bộ hoặc global aggregation.
- Error có thể xuất hiện sau khi đã phát một phần kết quả.
- Retry và replay phức tạp hơn.
- Consumer chậm có thể làm pipeline bị nghẽn.

### 12.1. Materialization

Materialization lưu kết quả trung gian để sử dụng lại. Nó có thể giảm việc tính toán lặp lại nhưng tiêu tốn memory hoặc storage.

Nên materialize khi:

- Một query con được dùng nhiều lần.
- Cần snapshot nhất quán.
- Chi phí tính toán lại cao.
- Kết quả phù hợp với giới hạn cache.

Không nên materialize mọi intermediate result vì nó có thể làm tăng I/O, memory và thời gian.

### 12.2. Backpressure

Backpressure cho phép consumer báo cho producer giảm tốc độ. Nếu không có backpressure, producer có thể tạo dữ liệu nhanh hơn consumer xử lý và làm queue tăng vô hạn.

DSL hoặc runtime streaming cần định nghĩa buffer size, overflow policy, cancellation và cách xử lý khi consumer chậm.

## 13. Caching và invalidation

Caching lưu kết quả đã tính để tránh làm lại công việc. DSL có thể cache:

- Parse tree.
- Symbol resolution.
- Type-check result.
- Compiled artifact.
- Query plan.
- Query result.
- Schema metadata.
- Workflow definition.

### 13.1. Lợi ích

- Giảm CPU và I/O.
- Tăng tốc feedback của editor.
- Giảm compile time cho module không đổi.
- Giảm latency cho query lặp lại.

### 13.2. Chi phí

- Memory hoặc storage tăng.
- Cache key phức tạp.
- Invalidation khó khi dependency thay đổi.
- Kết quả cũ có thể gây sai semantics.
- Cache contention khi concurrency cao.

### 13.3. Cache key

Cache key phải chứa mọi yếu tố ảnh hưởng kết quả:

~~~text
key = hash(
    sourceContent,
    compilerVersion,
    schemaVersion,
    dependencyVersion,
    compileOptions
)
~~~

Với query result, còn có thể cần parameter, principal/security scope, policy version và data snapshot. Cache kết quả giữa hai tenant mà không phân biệt security context có thể gây rò dữ liệu.

### 13.4. Invalidation

Khi schema, compiler, dependency hoặc policy thay đổi, cache liên quan phải được làm mới. Một cache miss thường tốn thời gian nhưng an toàn; một cache hit sai có thể trả kết quả không đúng hoặc vi phạm quyền.

## 14. Incremental compilation và dependency graph

Incremental compilation chỉ build lại phần bị ảnh hưởng khi source thay đổi. Nó đặc biệt hữu ích với workspace lớn và language server.

Ví dụ:

~~~text
module app
  -> module domain
  -> module shared

module domain
  -> module shared
~~~

Nếu chỉ sửa một function private trong app, không nhất thiết phải compile lại domain hoặc shared. Nếu public API của shared thay đổi, các module phụ thuộc có thể cần recompile hoặc revalidate.

### 14.1. Lợi ích

- Giảm thời gian build lặp lại.
- Tăng tốc feedback khi sửa code.
- Giảm CPU trong CI nếu cache được chia sẻ.

### 14.2. Đánh đổi

- Cần dependency graph chính xác.
- Cache invalidation phức tạp.
- Có thể phát sinh stale result nếu version không được quản lý.
- Debug build logic khó hơn full clean build.

Nên duy trì clean build path để xác minh incremental build không che giấu lỗi. Khi kết quả incremental khác clean build, cần xem đó là lỗi correctness của build system.

## 15. Parallelism và concurrency

Compiler hoặc runtime có thể xử lý nhiều module, query hoặc workflow song song.

Parallelism giúp tận dụng nhiều core và tăng throughput, nhưng có chi phí:

- Thread scheduling.
- Synchronization.
- Lock contention.
- Memory duplication.
- Context switching.
- Non-deterministic completion order.
- Resource contention với các service khác.

### 15.1. Parallel compilation

Các module độc lập có thể compile song song. Dependency graph xác định module nào có thể chạy đồng thời.

Nếu mọi task cùng ghi vào một output directory hoặc cập nhật shared state không đồng bộ, có thể tạo race condition và build không xác định.

### 15.2. Parallel query execution

Query engine có thể chia partition hoặc shard để xử lý song song. Điều này tăng throughput nhưng cần cân nhắc network shuffle, memory và skew dữ liệu.

Một partition lớn hơn hẳn các partition khác có thể trở thành straggler và quyết định latency tổng.

### 15.3. Parallel workflow

Workflow có thể chạy nhiều branch cùng lúc. Parallelism giảm thời gian wall-clock khi các bước độc lập, nhưng tăng số worker, connection và side effect đồng thời.

Nên có concurrency limit theo workflow, tenant và dependency để tránh một workflow chiếm toàn bộ capacity.

### 15.4. Amdahl's Law

Tăng số core không làm toàn bộ chương trình nhanh lên nếu vẫn có phần tuần tự. Nếu tỷ lệ tuần tự là s, speedup lý tưởng với N processor bị giới hạn:

\[
S(N) = \frac{1}{s + \frac{1-s}{N}}
\]

Ví dụ, nếu 20% công việc không thể song song, dù có rất nhiều core thì speedup vẫn bị giới hạn bởi phần tuần tự đó.

## 16. Memory, allocation và garbage collection

Một DSL runtime có thể tạo nhiều object cho AST, environment, value, closure, intermediate collection và result. Allocation rate cao có thể làm tăng GC pressure.

Các lựa chọn:

- Object model giàu tính năng dễ mở rộng nhưng tốn memory.
- Compact representation giảm footprint nhưng khó thao tác hơn.
- Object pooling giảm allocation nhưng cần quản lý lifetime và contention.
- Arena allocation phù hợp với dữ liệu có vòng đời theo batch.
- Streaming giảm intermediate collection nhưng yêu cầu pipeline semantics.

### 16.1. Object pooling

Pool có thể tái sử dụng buffer hoặc object đắt tạo. Tuy nhiên, pool không phải lúc nào cũng nhanh hơn allocator hiện đại. Nó có thể giữ memory lâu, gây contention hoặc trả object với trạng thái cũ nếu reset không đầy đủ.

Chỉ dùng pooling khi profiling cho thấy allocation là bottleneck và có test về lifecycle.

### 16.2. Garbage collection

GC giúp quản lý memory tự động nhưng có thể tạo pause hoặc tăng CPU. Cần đo allocation rate, heap size, pause time và live object set.

Không nên tối ưu GC bằng cách giảm heap tùy ý mà không xem throughput và tail latency. Heap quá nhỏ có thể làm GC chạy liên tục; heap quá lớn có thể làm pause hoặc memory pressure nghiêm trọng hơn.

### 16.3. Memory retention

Cache, closure, listener hoặc workflow state có thể giữ reference lâu hơn cần thiết. Memory leak trong môi trường GC thường là object không còn cần nhưng vẫn reachable.

Nên có giới hạn cache, lifecycle rõ và khả năng giải phóng state khi document hoặc workflow hoàn tất.

## 17. Startup time và warm-up

Một runtime JIT hoặc service có nhiều metadata có thể cần thời gian khởi động trước khi đạt throughput ổn định.

Các yếu tố:

- Class loading hoặc module loading.
- Parse grammar và schema.
- Khởi tạo plugin.
- JIT warm-up.
- Kết nối database.
- Nạp cache.
- Load workflow definition.

Có thể giảm startup bằng:

- Lazy initialization.
- Precompiled artifact.
- Ahead-of-time compilation.
- Cache đã xác minh.
- Giảm plugin và dependency không cần thiết.
- Khởi tạo song song các thành phần độc lập.

Đánh đổi là lazy initialization có thể đẩy latency sang request đầu tiên. Preloading làm startup lâu hơn nhưng steady-state latency tốt hơn.

Với CLI chạy một lần, startup có thể chiếm phần lớn tổng thời gian. Với server chạy nhiều ngày, throughput và tail latency sau warm-up có thể quan trọng hơn.

## 18. Reflection, dynamic dispatch và specialization

Reflection cho phép runtime kiểm tra type và gọi thành phần theo tên. Dynamic dispatch chọn implementation khi chạy. Chúng tăng tính linh hoạt nhưng có thể làm giảm khả năng tối ưu tĩnh.

Ví dụ:

~~~text
call functionByName("calculateTax", order)
~~~

Runtime cần tìm function và kiểm tra signature. Nếu call site được biết trước, compiler có thể resolve trực tiếp:

~~~text
call sales.tax.calculateTax(order)
~~~

### 18.1. Specialization

Compiler có thể tạo implementation chuyên biệt theo type hoặc constant parameter. Điều này giảm dynamic checks và giúp optimizer tối ưu sâu hơn.

Đánh đổi:

- Code size tăng.
- Compile time tăng.
- Số specialization có thể bùng nổ.
- Cache code cần quản lý.

Có thể giới hạn specialization theo type phổ biến hoặc hot path thay vì sinh mọi tổ hợp.

## 19. Abstraction overhead và inlining

DSL thường cung cấp abstraction như pipeline, closure, decorator, query operator hoặc workflow activity. Abstraction giúp source dễ hiểu nhưng có thể tạo object hoặc call layer.

Ví dụ pipeline:

~~~text
Orders
    |> filter(isApproved)
    |> map(toSummary)
    |> take(100)
~~~

Nếu mỗi operator tạo collection mới, pipeline có thể tốn memory và CPU. Engine có thể fuse các operator thành một vòng lặp:

~~~text
for order in Orders:
    if isApproved(order):
        emit toSummary(order)
        stop after 100 results
~~~

Fusion giảm intermediate allocation nhưng làm execution engine phức tạp hơn và có thể ảnh hưởng stack trace hoặc debugging.

Không nên mặc định mọi abstraction đều có overhead đáng kể. Compiler có thể inline hoặc fuse khi chứng minh được phép biến đổi bảo toàn semantics.

## 20. Dynamic configuration và khả năng tối ưu

Một DSL có thể cho phép thay đổi configuration hoặc rule mà không cần deploy lại code. Đây là lợi thế lớn trong hệ thống nghiệp vụ.

Đánh đổi:

- Runtime cần resolve cấu hình.
- Cache có thể bị invalidated thường xuyên.
- Query plan có thể phải xây dựng lại.
- Version và consistency phức tạp hơn.
- Lỗi cấu hình chỉ xuất hiện khi runtime load.

Có thể phân loại:

- Static configuration: biết lúc build, có thể specialize.
- Deployment configuration: biết lúc triển khai, có thể tạo artifact/config snapshot.
- Runtime parameter: thay đổi theo request, nên bind vào execution.
- Dynamic policy: có thể thay đổi độc lập, cần version và cache invalidation.

Phân loại rõ giúp tránh compile lại toàn bộ project cho mỗi parameter nhỏ, đồng thời không cache nhầm kết quả qua những thay đổi có ý nghĩa.

## 21. Bảo mật và hiệu năng

Một số kiểm soát bảo mật tạo thêm chi phí:

- Authorization check.
- Input validation.
- Signature verification.
- Encryption.
- Audit logging.
- Sandbox isolation.
- Resource accounting.
- Tenant policy filtering.

Không nên bỏ kiểm soát bảo mật chỉ để giảm vài millisecond mà chưa đo và đánh giá rủi ro.

Có thể tối ưu bằng:

- Cache policy decision với key có principal/resource/policy version phù hợp.
- Batch authorization cho nhiều resource.
- Push row policy xuống database.
- Verify artifact một lần rồi dùng immutable handle.
- Async audit pipeline có durability phù hợp.
- Giới hạn sandbox ở mức capability cần thiết.

Cache authorization cần cẩn thận với revocation và policy update. Nếu cache quá lâu, quyền đã thu hồi vẫn có thể được dùng.

## 22. Portability và backend-specific optimization

Một DSL có thể chạy trên nhiều backend để tăng tính di động. Tuy nhiên, mỗi backend có khả năng tối ưu và semantics riêng.

Ví dụ:

- SQL backend hỗ trợ index, join và window function.
- Document database hỗ trợ nested aggregation.
- Search engine có inverted index và relevance scoring.
- Stream processor hỗ trợ event time và window.
- In-memory engine tối ưu cho dữ liệu nhỏ và latency thấp.

Một portable subset giúp query chạy nhất quán nhưng có thể không tận dụng mọi khả năng của backend. Dialect hoặc capability-specific feature tăng hiệu năng nhưng làm giảm khả năng chuyển backend.

Nên:

1. Xác định semantics lõi portable.
2. Công bố capability của từng backend.
3. Chỉ dùng extension khi có lý do hiệu năng hoặc nghiệp vụ.
4. Có conformance test cho các semantics dùng chung.
5. Cung cấp explain plan theo backend.

## 23. Batch processing và request granularity

Gọi service hoặc database cho từng record có thể tạo nhiều round trip:

~~~text
for order in orders:
    customer = customerService.get(order.customerId)
~~~

Nếu có 10.000 order, có thể tạo 10.000 request. Batch loading có thể giảm round trip:

~~~text
customers = customerService.getMany(uniqueCustomerIds)
~~~

Batching giảm network overhead nhưng có thể:

- Tăng payload size.
- Làm một request batch thất bại ảnh hưởng nhiều record.
- Tăng memory.
- Tạo latency chờ gom batch.
- Gặp giới hạn số phần tử của backend.

Batch size nên được đo và cấu hình theo giới hạn service. Với streaming, micro-batching có thể cân bằng throughput và time-to-first-result.

## 24. Retry, timeout và backpressure

Retry có thể cải thiện khả năng chịu lỗi nhưng làm tăng tải và latency. Nếu một service chậm, nhiều caller retry đồng thời có thể tạo retry storm.

Các cơ chế phối hợp:

- Timeout giới hạn thời gian mỗi request.
- Deadline giới hạn tổng thời gian.
- Retry budget giới hạn số lần thử và elapsed time.
- Exponential backoff và jitter phân tán lần retry.
- Circuit breaker ngăn gọi dependency đang lỗi.
- Bulkhead giới hạn concurrency.
- Backpressure giảm tốc độ producer khi consumer chậm.

Một DSL workflow nên mô tả hoặc kế thừa các giới hạn này từ connector policy. Không nên cho mỗi step tự retry vô hạn.

## 25. Concurrency limit và fairness

Tăng concurrency có thể tăng throughput cho tới khi CPU, database hoặc external service trở thành bottleneck. Sau điểm đó, thêm concurrency có thể làm latency và error rate tăng.

Có thể giới hạn:

- Concurrent workflow per tenant.
- Concurrent activity per connector.
- Query concurrency per user.
- Build task parallelism.
- Queue consumer count.

Fairness giúp một tenant hoặc job lớn không chiếm toàn bộ capacity. Scheduling có thể dùng weighted fair queue hoặc quota theo tenant.

Đánh đổi là giới hạn thấp làm giảm throughput tổng; giới hạn cao làm tăng nguy cơ quá tải. Cần đo saturation và queue wait time để chọn.

## 26. Observability và profiling

Không thể lựa chọn trade-off chính xác nếu không biết thời gian và tài nguyên được tiêu ở đâu.

Các công cụ:

- Compiler phase timing.
- CPU và memory profiler.
- Allocation profiler.
- Query explain plan.
- Runtime trace.
- Workflow step duration.
- GC metrics.
- I/O metrics.
- Flame graph.
- Sampling profiler.

Một compiler có thể đo riêng:

~~~text
parse:             120 ms
name resolution:    80 ms
type checking:     210 ms
optimization:      340 ms
code generation:   150 ms
total:             900 ms
~~~

Nếu optimization chiếm 38% tổng thời gian, đó có thể là nơi đáng nghiên cứu. Nhưng cần xem output có thực sự cần mức tối ưu đó và runtime có cải thiện đủ để bù compile time hay không.

### 26.1. Instrumentation overhead

Tracing và profiling cũng tiêu tốn tài nguyên. Có thể dùng sampling hoặc bật chi tiết cao trong môi trường benchmark/diagnostic. Không nên ghi toàn bộ payload nhạy cảm để phục vụ profiling.

### 26.2. Explain và profile

Explain cho biết engine dự định thực thi như thế nào; profile cho biết điều gì thực sự xảy ra. Hai dữ liệu bổ sung cho nhau.

Estimated cost có thể sai vì statistics cũ hoặc data skew. Cần so sánh estimate với actual rows, duration và I/O.

## 27. Benchmark và phương pháp đo

Benchmark cần trả lời một câu hỏi cụ thể, chẳng hạn:

- Parser incremental có giảm latency khi sửa file lớn không?
- Bytecode VM có nhanh hơn interpreter không?
- Query pushdown giảm bytes đọc bao nhiêu?
- Cache cải thiện p95 nhưng tăng memory thế nào?
- JIT warm-up có được bù bởi throughput sau vài phút không?

### 27.1. Microbenchmark

Đo một thao tác nhỏ như parse expression hoặc dispatch instruction. Microbenchmark giúp so sánh implementation nhưng có thể không phản ánh overhead của hệ thống đầy đủ.

### 27.2. Macrobenchmark

Đo một use case hoàn chỉnh như compile workspace, chạy query hoặc thực thi workflow. Macrobenchmark thể hiện tương tác giữa các thành phần nhưng khó cô lập nguyên nhân.

### 27.3. Warm-up

Với JIT hoặc runtime có cache, cần phân biệt cold run và warm run. Không nên chỉ báo cáo kết quả warm-up nếu người dùng thực tế thường chạy chương trình ngắn.

### 27.4. Repetition và variance

Chạy nhiều lần, ghi median và percentile, kiểm soát background load và sử dụng cùng môi trường. Báo cáo cả variance thay vì chỉ chọn lần chạy nhanh nhất.

### 27.5. Baseline và regression

Giữ baseline có version và workload rõ ràng. Một thay đổi chỉ nên được coi là cải thiện khi so sánh cùng điều kiện và không làm suy giảm chỉ số quan trọng khác ngoài ngưỡng cho phép.

## 28. Cost model và lựa chọn tối ưu

Performance không chỉ là tốc độ. Trong môi trường cloud, chi phí CPU, memory, network, storage và số worker có thể quan trọng ngang latency.

Một cost model đơn giản:

~~~text
totalCost =
    cpuCost
  + memoryCost
  + networkCost
  + storageCost
  + operationalCost
~~~

Ví dụ:

- Cache tăng memory nhưng giảm database query.
- JIT tăng CPU lúc warm-up nhưng giảm CPU cho request sau.
- Batch giảm network round trip nhưng tăng payload.
- Precompute tăng storage và build time nhưng giảm query latency.
- Parallelism giảm wall-clock nhưng tăng peak resource usage.

Nên đo cost per successful operation, không chỉ cost per attempted request. Retry hoặc query thất bại vẫn có thể tiêu tốn tài nguyên.

## 29. Precomputation và runtime flexibility

Precomputation tính trước dữ liệu hoặc plan để giảm latency lúc chạy.

Ví dụ:

- Compile query template khi deploy.
- Tạo index trước.
- Materialize view.
- Precompute rule dependency.
- Load schema và symbol metadata vào cache.

Ưu điểm:

- Runtime ít việc hơn.
- Latency ổn định hơn.
- Có thể phát hiện lỗi trước deploy.

Đánh đổi:

- Build/deploy lâu hơn.
- Storage tăng.
- Dữ liệu có thể stale.
- Thay đổi config hoặc schema cần rebuild/recompute.

Dynamic computation linh hoạt hơn nhưng có thể làm tăng latency và tạo nhiều cache miss. Cần chọn theo tần suất thay đổi và yêu cầu freshness.

## 30. Hiệu năng của language server và developer tooling

Developer experience cũng là một phần của hiệu năng DSL. Editor cần phản hồi nhanh khi người dùng gõ, mở file, yêu cầu completion hoặc tìm symbol.

Các kỹ thuật:

- Incremental parsing.
- Debounce request.
- Cancel request cũ.
- Cache symbol và type information.
- Lazy load workspace index.
- Partial result cho workspace lớn.
- Giới hạn diagnostics theo vùng.
- Dùng background worker cho tác vụ nặng.

Đánh đổi:

- Cache tăng memory.
- Debounce giảm tải nhưng tăng thời gian phản hồi.
- Lazy indexing giảm startup nhưng query đầu tiên chậm.
- Partial result cải thiện time-to-first-result nhưng kết quả đầy đủ đến sau.

Language server cần ưu tiên thao tác tương tác có latency thấp và tránh để một request workspace nặng chặn completion của document đang mở.

## 31. Kích thước artifact và startup

Compiler có thể sinh artifact lớn để tối ưu tốc độ chạy hoặc nhỏ để giảm tải phân phối.

Inlining, specialization và debug metadata có thể tăng kích thước. Strip metadata hoặc giảm code duplication có thể giảm size nhưng làm debug khó hơn hoặc tăng runtime dispatch.

Kích thước artifact ảnh hưởng:

- Thời gian download.
- Cold start.
- Image size.
- Storage và cache.
- Memory mapping.
- Thời gian load class/module.

Cần đo cả artifact size và runtime performance. Một artifact nhỏ hơn chưa chắc chạy nhanh hơn; một artifact lớn hơn chưa chắc tạo latency tốt hơn nếu code không nằm trên hot path.

## 32. Compatibility và optimization correctness

Tối ưu phải bảo toàn semantics của DSL. Một optimizer nhanh nhưng thay đổi kết quả là sai.

Các rủi ro:

- Đổi thứ tự phép toán gây khác rounding.
- Pushdown predicate có null semantics khác.
- Loại bỏ expression có side effect.
- Inlining làm thay đổi exception behavior.
- Constant folding khác overflow semantics.
- Parallel aggregation làm thay đổi thứ tự cộng floating point.

### 32.1. Floating-point

Phép cộng số thực không luôn associative do rounding:

\[
(a+b)+c \ne a+(b+c)
\]

Optimizer đổi thứ tự aggregation có thể tạo sai khác nhỏ. Với dữ liệu tài chính, nên dùng decimal/fixed-point type có semantics rõ thay vì dựa vào floating-point khi không phù hợp.

### 32.2. Side effects

Nếu function có side effect, optimizer không thể tự do loại bỏ hoặc thực hiện lại nó. DSL nên đánh dấu effect hoặc giới hạn query expression ở pure function.

### 32.3. Differential testing

Có thể chạy cùng input qua interpreter và compiled backend rồi so sánh kết quả. Đây là cách phát hiện sai khác giữa các execution mode.

## 33. Những lỗi tối ưu thường gặp

### Tối ưu trước khi đo

Code phức tạp hơn nhưng bottleneck thật nằm ở network hoặc database. Bắt đầu từ profiling và workload đại diện.

### Chỉ đo average latency

Tail latency và timeout bị bỏ qua. Theo dõi p95/p99 và error rate.

### Tối ưu compile time nhưng làm runtime chậm

Bỏ optimization có thể phù hợp cho development nhưng không phải production. Tách profile theo môi trường và mục đích.

### Tăng concurrency vô hạn

Throughput có thể tăng lúc đầu nhưng cuối cùng gây saturation và queueing. Đặt giới hạn và đo điểm bão hòa.

### Cache không có invalidation

Kết quả cũ làm sai semantics hoặc policy. Thiết kế cache key và version rõ ràng.

### Materialize quá nhiều

Intermediate data chiếm memory/storage. Chỉ materialize khi có lợi ích đo được.

### Dùng JIT cho workload ngắn

Warm-up có thể lớn hơn thời gian tiết kiệm được. Đánh giá cold-start và lifetime thực tế.

### Parallel hóa phần không phù hợp

Synchronization và data transfer vượt lợi ích. Xem Amdahl's Law, contention và data locality.

### Bỏ qua security overhead

Tắt authorization hoặc audit để tăng tốc tạo rủi ro nghiêm trọng. Tối ưu implementation và batching thay vì bỏ kiểm soát.

### Không kiểm tra semantics sau optimization

Query hoặc compiler nhanh hơn nhưng trả kết quả khác. Dùng conformance và differential tests.

## 34. Quy trình lựa chọn trade-off hiệu năng

Một quy trình có thể áp dụng:

1. **Xác định workload.** Chọn source, query, workflow và kích thước dữ liệu đại diện.
2. **Đặt mục tiêu.** Latency, throughput, startup, memory, build time hay cost.
3. **Đo baseline.** Dùng profiler, trace và benchmark có thể lặp lại.
4. **Tìm bottleneck.** Parse, type check, optimizer, runtime, I/O, queue hay network?
5. **Liệt kê lựa chọn.** Compile-time/runtime, eager/lazy, cache/no-cache, sequential/parallel.
6. **Đánh giá tác động phụ.** Memory, code size, complexity, correctness và security.
7. **Thử thay đổi nhỏ.** Giữ một biến chính để so sánh.
8. **Kiểm tra semantics.** Regression, differential và conformance tests.
9. **Đo lại trên workload đầy đủ.** Bao gồm cold/warm, tải bình thường và peak.
10. **Ghi quyết định.** Lý do, số đo, phạm vi áp dụng và giới hạn.
11. **Theo dõi production.** Quan sát regression và điều chỉnh khi workload thay đổi.

### 34.1. Performance budget

Có thể phân bổ budget cho từng giai đoạn:

~~~text
request budget: 500 ms
  authentication: 20 ms
  parse/validate: 30 ms
  planning: 40 ms
  backend execution: 350 ms
  serialization: 20 ms
  reserve: 40 ms
~~~

Đây là ví dụ minh họa. Budget giúp xác định giai đoạn nào được phép tiêu thời gian và nơi cần tối ưu. Nếu backend đã chiếm 90% latency, tối ưu parser có thể không tạo khác biệt đáng kể cho người dùng.

### 34.2. Decision record

Một quyết định trade-off nên ghi:

- Vấn đề và workload.
- Các lựa chọn đã cân nhắc.
- Chỉ số trước và sau.
- Ảnh hưởng tới memory/cost/complexity.
- Rủi ro correctness.
- Điều kiện áp dụng.
- Thời điểm xem xét lại.

Điều này giúp nhóm hiểu vì sao một tối ưu tồn tại và tránh lặp lại tranh luận khi người phụ trách thay đổi.

## 35. Ví dụ end-to-end: tối ưu query DSL

Giả sử query sau chạy chậm trên tập Orders lớn:

~~~text
let orders =
    from Orders
    select *

let approved =
    orders
    where status == APPROVED

approved
    where region == "NORTH"
    select orderId, total
    order by total descending
    limit 100
~~~

Một execution plan chưa tối ưu có thể:

1. Đọc mọi field của Orders.
2. Tạo collection trung gian orders.
3. Lọc status.
4. Tạo collection approved.
5. Lọc region.
6. Sort toàn bộ kết quả.
7. Chỉ giữ 100 dòng.

Một optimizer có thể hợp nhất filter, projection pushdown và limit-aware top-N:

~~~text
scan Orders
  predicate:
    status == APPROVED
    and region == "NORTH"
  projection:
    orderId, total
  topN:
    100 by total descending
~~~

Các trade-off:

- Query fusion giảm intermediate allocation nhưng plan phức tạp hơn.
- Projection pushdown giảm I/O nhưng cần giữ field nội bộ cho policy hoặc join.
- Top-N giảm memory so với sort toàn bộ nếu backend hỗ trợ.
- Cache plan giúp query lặp nhanh hơn nhưng phải invalidated khi schema hoặc policy version đổi.

Nhóm đo:

| Chỉ số | Plan cũ | Plan tối ưu |
|---|---:|---:|
| Rows đọc | 2.000.000 | 180.000 |
| Bytes đọc | 900 MB | 24 MB |
| Intermediate allocation | 420 MB | 18 MB |
| Latency p95 | 2.8 s | 410 ms |

Các số liệu chỉ minh họa cách so sánh. Trong thực tế, cần đo trên cùng snapshot dữ liệu, cùng backend và cùng tải. Sau tối ưu, phải xác nhận kết quả giống nhau, bao gồm null semantics, ordering và security filter.

## 36. Kết luận

Đánh đổi hiệu năng trong DSL là lựa chọn giữa tốc độ, latency, throughput, memory, startup, build time, chi phí, tính linh hoạt và độ phức tạp. Không có một kỹ thuật luôn tốt hơn: interpreter đơn giản nhưng có thể chậm hơn bytecode; JIT tăng throughput nhưng có warm-up; lazy evaluation giảm tính toán thừa nhưng làm thời điểm thực thi khó dự đoán; cache tăng tốc nhưng cần invalidation; parallelism tăng throughput nhưng có thể tạo contention.

Một quyết định đúng bắt đầu từ workload và mục tiêu đo được. Compiler/runtime cần phân chia hợp lý công việc compile time và runtime; query engine cần tối ưu plan nhưng bảo toàn semantics; workflow cần giới hạn concurrency, retry và tài nguyên; developer tooling cần phản hồi nhanh mà vẫn kiểm soát memory.

Hãy đo cả cold và warm behavior, p95/p99, memory, I/O và cost; dùng profiling để tìm bottleneck; kiểm tra correctness bằng regression và differential tests; rồi ghi lại lý do và giới hạn của lựa chọn. Tối ưu hiệu năng chỉ có giá trị khi kết quả vẫn đúng, an toàn và dễ vận hành trong workload thực tế.
