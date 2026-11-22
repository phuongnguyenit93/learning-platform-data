# Mức sử dụng bộ nhớ

## 1. Mức sử dụng bộ nhớ trong hiệu năng DSL

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) thường có nhiều thành phần cùng tiêu thụ bộ nhớ: source text, token, abstract syntax tree (AST), symbol table, type information, intermediate representation (IR), generated code, runtime object, cache và dữ liệu đầu vào. Khi DSL được dùng trong editor, compiler service, build pipeline hoặc runtime xử lý lượng lớn dữ liệu, memory footprint có thể ảnh hưởng trực tiếp đến latency, throughput, khả năng mở rộng và độ ổn định của ứng dụng.

**Mức sử dụng bộ nhớ (memory usage)** mô tả lượng bộ nhớ mà một tiến trình hoặc thành phần cần trong một khoảng thời gian để lưu dữ liệu, trạng thái và cấu trúc phục vụ xử lý. Với DSL, cần quan sát cả bộ nhớ cực đại, mức sử dụng ổn định, tốc độ tăng theo kích thước chương trình và khả năng giải phóng bộ nhớ sau khi một tác vụ kết thúc.

Ví dụ, compiler xử lý một file DSL có thể lần lượt tạo:

~~~text
Source Text
    |
    v
Tokens
    |
    v
AST
    |
    v
Symbol Table + Type Information
    |
    v
Intermediate Representation
    |
    v
Generated Output
~~~

Nếu compiler giữ đồng thời mọi biểu diễn mà không cần thiết, một file đầu vào 5 MB có thể tạo ra hàng chục hoặc hàng trăm MB object trong heap. Điều này không nhất thiết là lỗi: các biểu diễn có thể cần cho semantic analysis, diagnostics hoặc code generation. Tuy nhiên, phải hiểu vòng đời của từng cấu trúc để giải phóng hoặc tái sử dụng đúng thời điểm.

Mục tiêu quản lý memory không đơn giản là làm heap nhỏ nhất. Một thiết kế tốt cân bằng giữa bộ nhớ, CPU, latency, khả năng debug, độ rõ ràng của code và chi phí vận hành.

## 2. Các loại bộ nhớ cần phân biệt

Khi đo memory usage, cần biết đang đo loại bộ nhớ nào và công cụ báo cáo đại lượng gì.

### 2.1. Stack memory

Stack lưu thông tin phục vụ lời gọi hàm như local primitive, reference và call frame. Mỗi thread có stack riêng với giới hạn cấu hình. Đệ quy sâu hoặc chuỗi lời gọi quá dài có thể gây StackOverflowError.

### 2.2. Heap memory

Heap là vùng lưu object và array được cấp phát động trong JVM. Garbage collector quản lý vòng đời của phần lớn object trên heap.

### 2.3. Metaspace

Metaspace lưu metadata của class trong JVM. Ứng dụng DSL có thể tăng metaspace nếu liên tục sinh hoặc nạp nhiều class, classloader không được giải phóng hoặc tạo class động cho từng mapping.

### 2.4. Direct và native memory

Một số thư viện sử dụng bộ nhớ ngoài heap, ví dụ direct ByteBuffer, native library, TLS implementation hoặc parser hiệu năng cao. Heap dump không thể hiện đầy đủ mọi vùng native memory.

### 2.5. Memory-mapped files

File có thể được ánh xạ vào không gian địa chỉ tiến trình. Cách này hữu ích khi đọc file lớn hoặc index, nhưng cần hiểu page fault, file lifetime và giới hạn hệ điều hành.

### 2.6. Resident Set Size

RSS là lượng trang bộ nhớ của tiến trình đang nằm trong RAM theo cách đo của hệ điều hành. RSS không đồng nghĩa với Java heap used; nó còn có thể gồm metaspace, code cache, thread stack và native allocation.

### 2.7. Virtual memory

Virtual memory là không gian địa chỉ mà tiến trình có thể nhìn thấy. Kích thước virtual memory không phản ánh trực tiếp lượng RAM thực sự đang dùng.

### 2.8. Memory limit của container

Trong container, tiến trình có thể bị giới hạn memory bởi cgroup hoặc nền tảng điều phối. JVM cần nhận diện giới hạn container phù hợp; cấu hình heap chỉ chiếm một phần tổng memory budget.

## 3. Memory footprint của một DSL

Một DSL có thể tiêu thụ bộ nhớ ở nhiều giai đoạn khác nhau.

### 3.1. Source buffer

Editor hoặc compiler service có thể giữ nội dung file trong String, byte array, rope hoặc piece table. Với file lớn, việc tạo nhiều bản sao String khi chỉnh sửa hoặc normalize có thể tốn đáng kể bộ nhớ.

### 3.2. Token stream

Lexer tạo token cho identifier, keyword, literal, operator và dấu phân cách. Mỗi token có thể giữ kind, offset, length và reference tới source. Nếu mỗi token tạo nhiều String riêng, overhead object có thể lớn hơn nội dung token.

### 3.3. AST

AST biểu diễn cấu trúc cú pháp. Mỗi node có object header, reference, field và có thể có collection con. Một AST nhiều node nhỏ có thể dùng nhiều bộ nhớ hơn đáng kể so với kích thước source.

### 3.4. Symbol table

Symbol table lưu tên, scope, declaration, type và quan hệ tham chiếu. Việc giữ cả tên đã copy, object wrapper và map entry cho mọi symbol có thể tạo overhead.

### 3.5. Type graph

Type inference, generic instantiation và constraint solving có thể tạo nhiều object trung gian. Type graph có thể tăng nhanh khi chương trình chứa nhiều generic hoặc biểu thức phức tạp.

### 3.6. Intermediate representation

IR có thể giữ control flow, data flow, source location và metadata. Nếu AST và IR cùng tồn tại trong toàn bộ compile, peak memory có thể cao.

### 3.7. Generated output

Code generation có thể tạo StringBuilder, byte buffer hoặc danh sách instruction. Ghép chuỗi lặp lại bằng cách tạo String mới có thể làm tăng allocation.

### 3.8. Runtime state

Runtime có thể giữ execution context, variable environment, object graph, event queue, workflow state và result cache. Những cấu trúc này có vòng đời khác với compiler structures.

### 3.9. Editor services

Language server có thể giữ nhiều phiên bản AST, diagnostics, completion index và project graph để phản hồi nhanh khi người dùng gõ. Cần giới hạn dữ liệu cũ sau mỗi lần thay đổi.

## 4. Heap usage và object overhead

Kích thước logic của dữ liệu không bằng kích thước thực tế trên heap.

### 4.1. Object header

Mỗi object JVM có header phục vụ nhận diện class, locking hoặc garbage collection. Kích thước cụ thể phụ thuộc JVM, kiến trúc và cấu hình.

### 4.2. Reference

Field reference trỏ tới object khác. Compressed oops có thể giảm kích thước reference trong một số cấu hình JVM, nhưng không nên giả định một kích thước cố định cho mọi môi trường.

### 4.3. Alignment

Object thường được căn chỉnh theo boundary nhất định. Padding có thể khiến object chiếm nhiều byte hơn tổng kích thước field.

### 4.4. Collection overhead

ArrayList có object list, backing array và capacity có thể lớn hơn số phần tử hiện tại. HashMap có table, node, key, value và bucket overhead.

### 4.5. Small object overhead

Một triệu object nhỏ có thể tiêu thụ nhiều bộ nhớ hơn một vài array lớn chứa cùng lượng dữ liệu. Vì vậy, object count là một chỉ số quan trọng bên cạnh byte count.

### 4.6. Duplicate representation

Nếu source text, token text, AST identifier và symbol name đều copy cùng một chuỗi, memory usage tăng do dữ liệu trùng. Có thể dùng source slice hoặc interning có kiểm soát.

## 5. Allocation rate và peak memory

Không chỉ lượng object còn sống mới ảnh hưởng hiệu năng.

### 5.1. Allocation rate

Allocation rate là tốc độ cấp phát bộ nhớ mới, thường đo bằng bytes per second. Một ứng dụng có heap used thấp nhưng allocation rate cao vẫn có thể gây nhiều garbage collection.

### 5.2. Live set

Live set là tập object còn được giữ tham chiếu và chưa thể thu hồi tại một thời điểm. Nó gần với lượng dữ liệu đang cần dùng, nhưng cách đo cụ thể phụ thuộc công cụ.

### 5.3. Peak memory

Peak memory là mức sử dụng cao nhất trong một tác vụ hoặc chu kỳ. Compiler có thể dùng memory rất cao trong phase chuyển AST sang IR rồi giảm sau đó.

### 5.4. Retained size

Retained size ước lượng lượng bộ nhớ sẽ được giải phóng nếu một object hoặc nhóm object không còn reachable. Nó giúp tìm object giữ lại cả một graph lớn.

### 5.5. Allocation churn

Allocation churn là lượng object được tạo rồi nhanh chóng trở thành garbage. Churn cao làm GC phải làm việc thường xuyên dù live set không lớn.

### 5.6. Peak so với steady state

Một lần compile đầu tiên có thể tạo cache và class metadata. Các lần sau dùng lại nên memory khác. Khi benchmark, cần tách cold start và steady state.

## 6. Vòng đời dữ liệu trong compiler

Quản lý memory hiệu quả bắt đầu bằng việc xác định phase nào cần giữ cấu trúc nào.

### 6.1. Lexing

Lexer đọc source và tạo token. Token thường chỉ cần giữ loại token và vị trí trong source. Nếu literal lớn, có thể trì hoãn parse giá trị cho đến khi semantic phase cần.

### 6.2. Parsing

Parser tạo AST. Nếu AST giữ source range thay vì copy text, diagnostics vẫn có thể trỏ về source mà không nhân bản chuỗi.

### 6.3. Name resolution

Resolver tạo scope và symbol reference. Sau khi resolve, một số cấu trúc lookup tạm thời có thể được giải phóng nếu không cần cho IDE hoặc diagnostics.

### 6.4. Type checking

Type checker có thể tạo constraint, substitution và inferred type. Các constraint đã giải xong không cần được giữ nếu không phục vụ debug hoặc incremental compilation.

### 6.5. Lowering

Lowering chuyển AST sang IR. Nếu các phase sau không cần AST, compiler có thể giải phóng reference tới AST hoặc chỉ giữ source map tối thiểu.

### 6.6. Optimization

Optimization có thể tạo nhiều bản IR tạm. Có thể áp dụng in-place transformation hoặc tạo IR mới theo từng pass, tùy yêu cầu rollback và parallelism.

### 6.7. Code generation

Code generator nên stream output ra writer hoặc buffer có giới hạn khi có thể, tránh giữ nhiều bản sao toàn bộ output.

### 6.8. Diagnostics

Diagnostics có thể cần source text và symbol context. Nên giữ reference tới source snapshot có vòng đời rõ thay vì để mọi diagnostic vô tình giữ cả project graph.

## 7. AST và lựa chọn cấu trúc dữ liệu

AST là một trong những nguồn memory footprint lớn của compiler.

### 7.1. Node class hierarchy

Một node class cho mỗi loại cú pháp giúp code rõ và type-safe. Tuy nhiên, nhiều node nhỏ có thể tạo object overhead đáng kể.

### 7.2. Compact node representation

Có thể lưu node trong array hoặc arena với integer index. Cách này giảm object count nhưng làm API truy cập phức tạp hơn.

### 7.3. Source span

Thay vì lưu chuỗi source cho từng identifier, node có thể giữ start offset và end offset vào source buffer. Cần giữ snapshot tương ứng còn sống trong suốt thời gian node được sử dụng.

### 7.4. Parent pointer

Parent pointer giúp navigation nhưng tạo reference hai chiều và có thể làm object graph khó giải phóng từng phần. Nếu không cần, hãy cân nhắc dùng traversal context hoặc side table.

### 7.5. Immutable AST

AST bất biến giúp chia sẻ an toàn giữa phase và thread. Tuy nhiên, mỗi lần sửa có thể tạo node mới; persistent structure hoặc copy-on-write có thể giảm chi phí khi chỉ thay đổi một phần.

### 7.6. Optional child

Nhiều nullable field trong node có thể làm object lớn hơn cần thiết. Có thể dùng node variant hoặc compact flags nếu profile cho thấy đây là điểm nóng.

### 7.7. AST pruning

Sau khi phân tích, có thể loại bỏ trivia hoặc node không cần cho runtime. Với IDE, vẫn cần giữ comment và source mapping nếu tính năng yêu cầu.

## 8. Arena allocation và region-based memory

Arena là vùng cấp phát nhiều object có cùng vòng đời và giải phóng cả vùng cùng lúc.

### 8.1. Nguyên lý

Thay vì để từng object có vòng đời độc lập, compiler cấp phát node vào một region. Khi compile unit kết thúc, region được reset hoặc giải phóng.

~~~text
Compile Unit
   |
   v
 [Arena]
   |-- AST node
   |-- temporary type
   |-- parse metadata
   |-- IR node
   |
   v
 Release whole region
~~~

### 8.2. Ưu điểm

- Giảm chi phí quản lý từng object.
- Giải phóng nhanh khi toàn bộ dữ liệu cùng hết vòng đời.
- Tăng locality trong một số thiết kế.
- Hạn chế rò rỉ do reference còn sót giữa các node trong region.

### 8.3. Hạn chế

- Không phù hợp khi object cần sống lâu hơn region.
- Khó chia sẻ object giữa các compile unit.
- Cần kiểm soát reference không được giữ sau khi region giải phóng.
- Có thể giữ nhiều memory chưa dùng nếu arena không được thu nhỏ.

### 8.4. Region lifetime

Có thể có arena cho parse phase, type checking và IR. Không nên reset arena chứa symbol hoặc source metadata nếu phase sau vẫn tham chiếu.

### 8.5. Java implementation

Java heap không cung cấp arena object thông thường theo semantics native region. Có thể mô phỏng bằng object pool hoặc primitive arrays, nhưng cần cân nhắc GC và độ phức tạp. Foreign Memory API ở các phiên bản Java mới cung cấp abstraction cho native memory segment; cần dùng đúng phiên bản và lifecycle scope.

## 9. String interning và symbol storage

Tên biến, keyword và identifier thường lặp lại trong DSL.

### 9.1. Duplicate strings

Nếu mỗi lần xuất hiện của customerId tạo một String object riêng, cùng nội dung sẽ chiếm nhiều memory.

### 9.2. Interning

Interning giữ một đại diện canonical cho chuỗi giống nhau. Các reference cùng nội dung có thể trỏ đến cùng object hoặc symbol ID.

### 9.3. JVM String.intern

String.intern có thể dùng để canonicalize String, nhưng không nên gọi bừa bãi cho mọi input vì pool lifecycle và chi phí lookup có thể không phù hợp với dữ liệu lớn hoặc không tin cậy.

### 9.4. Compiler-level symbol interning

Một symbol table riêng có thể ánh xạ tên thành integer ID. AST node lưu ID thay vì String. Cách này giúp so sánh và lookup nhanh, đồng thời tránh lặp chuỗi.

### 9.5. Hashing

Có thể lưu hash để tăng tốc lookup nhưng vẫn cần xử lý collision bằng equality. Không dùng hash đơn độc làm identity.

### 9.6. Source slice

Token có thể giữ offset/length vào source buffer. Khi cần hiển thị text, lấy substring hoặc slice. Cần chú ý substring implementation và source buffer lifetime của phiên bản runtime đang dùng.

## 10. Symbol table và scope memory

Symbol table thường tồn tại trong suốt semantic analysis và đôi khi được giữ cho language server.

### 10.1. Scope tree

Mỗi scope có thể chứa symbol được khai báo trực tiếp và reference tới parent scope. Khi scope kết thúc, có thể giải phóng map nếu không cần cho diagnostics hoặc IDE.

### 10.2. Flat symbol table

Một bảng phẳng với scope ID và symbol ID có thể giảm object graph và hỗ trợ lookup theo index.

### 10.3. Duplicate name storage

Nếu symbol giữ tên riêng trong khi interner đã có chuỗi, memory bị nhân đôi. Có thể lưu symbol ID và truy xuất tên từ interner.

### 10.4. Cross-reference index

IDE có thể lưu danh sách nơi symbol được tham chiếu. Index này hữu ích cho find references nhưng cần cập nhật và loại bỏ khi file thay đổi.

### 10.5. Incremental scope update

Khi một file sửa, không nhất thiết xây lại toàn bộ project symbol table. Có thể thay scope của file bị đổi và cập nhật dependency liên quan.

## 11. Type system và constraint memory

Type inference và generic resolution có thể tạo nhiều object tạm.

### 11.1. Type interning

Các type structurally equal có thể được canonicalize để tránh tạo nhiều bản sao. Cần phân biệt nominal identity và structural equality.

### 11.2. Type variables

Mỗi type variable có ID, constraint và substitution. Sau khi giải quyết, có thể compact graph hoặc lưu kết quả cuối thay vì giữ toàn bộ lịch sử.

### 11.3. Constraint queue

Type checker có thể dùng worklist thay vì đệ quy tạo nhiều frame. Sau khi constraint được giải, loại bỏ entry đã hoàn tất.

### 11.4. Generic instantiation

Một generic type được instantiate với nhiều type argument có thể tạo nhiều bản thể. Cache instantiation theo canonical type argument có thể tránh tính lại, nhưng cần giới hạn cache.

### 11.5. Recursive type

Recursive type hoặc constraint cycle cần được biểu diễn bằng reference ID để tránh mở rộng đệ quy vô hạn.

### 11.6. Error recovery

Compiler có thể tạo ErrorType để tiếp tục phân tích sau lỗi. Không nên tạo một ErrorType mới ở mọi node nếu có thể dùng canonical error marker phù hợp.

## 12. Runtime memory của DSL

Compiler và runtime có đặc điểm memory khác nhau. Runtime thường xử lý nhiều instance dữ liệu và có vòng đời dài.

### 12.1. Execution context

Execution context giữ variable, scope, function state, current node và cancellation token. Khi execution kết thúc, context phải không còn bị callback hoặc cache giữ lại ngoài ý muốn.

### 12.2. Environment frame

Mỗi scope có thể tạo frame chứa local variable. Frame stack hoặc indexed slot có thể tiết kiệm memory so với map String-to-Object cho mọi biến.

### 12.3. Value representation

Runtime có thể dùng boxed object cho mọi value hoặc tagged union/slot array để giảm allocation. Lựa chọn ảnh hưởng type safety và tốc độ.

### 12.4. Closure capture

Closure có thể giữ toàn bộ environment nếu implementation không phân tích capture. Chỉ capture biến được sử dụng giúp giảm object graph được giữ sống.

### 12.5. Event queue

Workflow hoặc rule engine có thể tạo queue chứa event. Queue cần giới hạn kích thước và có backpressure hoặc dead-letter policy.

### 12.6. Result retention

Không giữ toàn bộ kết quả của mọi task nếu caller chỉ cần summary hoặc output cuối. Có thể lưu bền vững, stream ra consumer hoặc giữ một cửa sổ kết quả giới hạn.

### 12.7. Long-lived execution

Execution kéo dài nhiều giờ hoặc ngày cần lưu state bền vững và khôi phục context khi cần, thay vì giữ toàn bộ object graph trong heap suốt thời gian chờ.

## 13. Streaming và xử lý dữ liệu lớn

Streaming giúp xử lý dữ liệu từng phần thay vì nạp toàn bộ vào memory.

### 13.1. Eager loading

Eager loading đọc toàn bộ input vào một collection. Cách này đơn giản nhưng memory tăng theo kích thước dữ liệu.

### 13.2. Streaming

Streaming đọc và xử lý một record hoặc chunk tại một thời điểm:

~~~text
Read chunk
    |
    v
Parse record
    |
    v
Transform
    |
    v
Write output
    |
    v
Release temporary state
~~~

### 13.3. Backpressure

Nếu producer nhanh hơn consumer, buffer có thể tăng vô hạn. Cần giới hạn queue, block producer, pause source hoặc drop theo policy rõ ràng.

### 13.4. Chunk size

Chunk nhỏ giảm memory nhưng tăng overhead I/O và scheduling. Chunk lớn tăng throughput trong một số trường hợp nhưng tiêu thụ memory nhiều hơn.

### 13.5. Streaming parser

Parser kiểu event hoặc pull có thể đọc JSON/XML lớn mà không tạo toàn bộ object tree. DSL runtime có thể ánh xạ trực tiếp record sang output.

### 13.6. Batch processing

Batch giới hạn số record được giữ cùng lúc. Nên chọn batch size theo kích thước record, latency và memory budget.

### 13.7. Resource cleanup

Stream, file handle, response body và native buffer cần được đóng đúng cách, kể cả khi parse hoặc transformation ném exception.

## 14. Cache và memory retention

Cache giúp giảm CPU và I/O nhưng là nguồn memory retention phổ biến.

### 14.1. Compiler cache

Compiler có thể cache parsed file, symbol index, type result và generated artifact. Mỗi entry cần có key, version và invalidation policy.

### 14.2. Unbounded cache

Cache không giới hạn có thể tăng mãi khi người dùng mở nhiều project hoặc file. Đặt maximum size hoặc memory-aware eviction.

### 14.3. TTL

Time-to-live giới hạn tuổi của entry. TTL không đảm bảo entry được giải phóng đúng lúc nếu cache vẫn giữ reference hoặc có object graph bên ngoài.

### 14.4. LRU và LFU

LRU ưu tiên giữ entry được dùng gần đây; LFU ưu tiên entry có tần suất sử dụng cao. Mỗi policy có trade-off và overhead metadata.

### 14.5. Cache key

Key phải bao gồm mọi yếu tố ảnh hưởng kết quả như DSL version, compiler version, dependency version và configuration. Thiếu một yếu tố có thể trả kết quả cũ sai.

### 14.6. Cache value size

Giới hạn số entry chưa đủ nếu mỗi entry có kích thước rất khác nhau. Có thể cần weight-based eviction theo ước lượng byte.

### 14.7. Weak và soft references

Weak reference phù hợp với một số canonicalization map khi không muốn map giữ object sống. Soft reference không phải cơ chế cache có giới hạn đáng tin cậy; hành vi phụ thuộc GC và memory pressure.

### 14.8. Classloader retention

Cache giữ Class, Method hoặc ClassLoader có thể ngăn classloader được thu hồi. Điều này đáng chú ý với plugin, hot reload hoặc generated class.

## 15. Object pooling và tái sử dụng

Object pooling giữ sẵn object để tái sử dụng thay vì tạo mới.

### 15.1. Khi nào pooling hữu ích

Pooling có thể hữu ích với resource đắt như connection, native buffer hoặc object có chi phí khởi tạo cao.

### 15.2. Pooling object nhỏ

Với object Java nhỏ, allocation và garbage collection hiện đại thường rất nhanh. Pooling không đúng cách có thể làm tăng synchronization, giữ memory lâu và phức tạp hóa lifecycle.

### 15.3. Reset state

Object được tái sử dụng phải reset đầy đủ. Một field cũ bị sót có thể làm rò dữ liệu giữa request hoặc tenant.

### 15.4. Pool size

Pool cần giới hạn kích thước và có policy khi hết resource: wait, reject hoặc tạo mới trong budget.

### 15.5. Thread safety

Không chia sẻ object mutable từ pool giữa nhiều thread nếu không có synchronization hoặc ownership rõ ràng.

### 15.6. Benchmark trước khi dùng

Chỉ dùng pooling khi profile chứng minh allocation cụ thể là bottleneck. So sánh throughput, latency, GC và retained heap.

## 16. Garbage collection trên JVM

Garbage collector (GC) thu hồi object không còn reachable từ các GC root.

### 16.1. Reachability

Object có thể được thu hồi khi không còn đường tham chiếu từ GC root như thread stack, static field hoặc JNI reference.

### 16.2. Generational hypothesis

Nhiều object có vòng đời ngắn, trong khi một số object sống lâu. JVM GC thường tận dụng đặc tính này bằng cách tổ chức heap theo vùng hoặc thế hệ tùy collector.

### 16.3. Young collection

Object mới cấp phát thường bắt đầu ở vùng trẻ. Collection vùng này thu hồi object ngắn hạn.

### 16.4. Old generation

Object sống lâu có thể được promote sang vùng già. Live set lớn ở vùng này có thể làm chu kỳ GC tốn kém hơn.

### 16.5. GC pause

Một số collector có pause để thực hiện công việc cần đồng bộ. Pause ảnh hưởng latency, đặc biệt với language server hoặc runtime tương tác.

### 16.6. Collector selection

Serial, Parallel, G1, ZGC và Shenandoah có mục tiêu và trade-off khác nhau tùy phiên bản JVM. Không có collector tối ưu cho mọi workload.

### 16.7. Allocation pressure

Tốc độ tạo object cao có thể khiến GC chạy thường xuyên. Giảm allocation churn đôi khi hiệu quả hơn tăng heap.

### 16.8. GC không sửa memory leak

Nếu object vẫn reachable qua cache, listener, static field hoặc thread local, GC không thể thu hồi. Cần tìm và loại bỏ reference giữ object không cần thiết.

## 17. Memory leak và retention trong DSL tools

Memory leak trong ứng dụng managed thường xuất hiện khi object không còn cần nhưng vẫn được giữ tham chiếu.

### 17.1. Static collection

Static map lưu project hoặc compilation result mà không có eviction có thể giữ dữ liệu vô thời hạn.

### 17.2. Listener không được unregister

Editor hoặc plugin đăng ký listener nhưng không hủy đăng ký khi document đóng. Listener có thể giữ document, AST và project graph.

### 17.3. ThreadLocal

ThreadLocal giữ context theo thread. Thread pool dùng thread lâu dài có thể giữ request data sau khi request kết thúc nếu không remove.

### 17.4. Callback retention

Future hoặc callback giữ lambda capture toàn bộ execution context. Khi operation hoàn tất, tham chiếu không cần thiết phải được giải phóng.

### 17.5. Cache key/value cycle

Cache value có thể giữ project hoặc classloader, trong khi project lại giữ cache. Cần xác định ownership và lifecycle.

### 17.6. Incremental compilation leak

Mỗi lần sửa file tạo AST mới nhưng index vẫn giữ AST cũ. Cần invalidation theo document version và giải phóng snapshot cũ.

### 17.7. Diagnostic retention

Diagnostic có thể giữ source buffer lớn. Nếu chỉ cần hiển thị line/column và message, cân nhắc lưu source ID và range thay vì giữ toàn bộ document.

### 17.8. Plugin lifecycle

Plugin reload cần giải phóng classloader, cache, executor, thread và listener thuộc plugin cũ.

## 18. Thiết kế memory-aware cho language server

Language server phục vụ tương tác liên tục nên phải cân bằng memory và responsiveness.

### 18.1. Open document set

Chỉ giữ đầy đủ state của document đang mở hoặc gần đây theo policy. Document đóng có thể giữ summary/index nhỏ thay vì toàn AST.

### 18.2. Incremental parsing

Khi người dùng sửa một vùng nhỏ, incremental parser có thể tái sử dụng node ngoài vùng bị ảnh hưởng. Cần đảm bảo source range và node identity được cập nhật đúng.

### 18.3. Debounce analysis

Không chạy toàn bộ semantic analysis cho mỗi keystroke nếu người dùng đang gõ nhanh. Debounce hoặc cancel task cũ giúp tránh nhiều compilation snapshot cùng tồn tại.

### 18.4. Cancellation

Khi document version mới xuất hiện, hủy analysis cũ nếu không còn cần. Cancellation phải giải phóng queue và temporary state.

### 18.5. Project index

Index nên lưu thông tin cần cho completion và navigation. Tránh giữ cả AST nếu index compact đủ cho phần lớn truy vấn.

### 18.6. Memory budget

Có thể đặt budget cho mỗi workspace, project hoặc document. Khi vượt ngưỡng, giảm cache, loại bỏ snapshot cũ hoặc chuyển sang chế độ phân tích ít chi tiết hơn.

### 18.7. Workspace isolation

Đóng workspace cần giải phóng symbol index, file snapshot, diagnostics và background task thuộc workspace đó.

## 19. Memory-aware runtime và DSL semantics

Thiết kế ngôn ngữ có thể ảnh hưởng trực tiếp đến số object và vòng đời dữ liệu.

### 19.1. Lazy evaluation

Lazy evaluation chỉ tính biểu thức khi cần, có thể tránh tạo dữ liệu không dùng. Tuy nhiên, thunk hoặc closure có thể giữ nhiều biến môi trường và làm tăng retention.

### 19.2. Eager evaluation

Eager evaluation đơn giản hơn và có thể giải phóng intermediate value sớm, nhưng có thể tạo collection lớn ngay cả khi consumer chỉ cần vài phần tử.

### 19.3. Sequence và collection

DSL có thể phân biệt stream/sequence lazy với list eager để người viết hiểu chi phí materialization.

### 19.4. Materialization boundary

Khi một sequence được chuyển thành list, toàn bộ phần tử có thể cùng sống trong memory. DSL nên làm rõ thao tác materialize.

### 19.5. Copy semantics

Gán biến có thể copy value, copy reference hoặc tạo immutable snapshot. Semantics rõ giúp tránh copy object graph lớn ngoài ý muốn.

### 19.6. Value types

Value type hoặc compact representation có thể giảm object allocation nếu runtime và ngôn ngữ hỗ trợ. Cần xem xét boxing khi value đi qua generic hoặc interface.

### 19.7. Bounded collection

DSL có thể cho phép khai báo maximum size cho buffer, queue hoặc collection do người dùng tạo.

### 19.8. Resource scope

File, stream, cursor và native buffer cần scope rõ để tự động đóng khi block kết thúc hoặc khi exception xảy ra.

## 20. Memory budget và admission control

Một hệ thống phục vụ nhiều compile hoặc workflow đồng thời cần giới hạn tổng memory.

### 20.1. Per-task budget

Mỗi compile job có thể có giới hạn memory ước lượng. Job vượt budget có thể bị hủy với diagnostic rõ ràng.

### 20.2. Global budget

Compiler service cần giới hạn tổng số job chạy đồng thời theo memory capacity.

### 20.3. Admission control

Trước khi nhận job lớn, scheduler có thể kiểm tra available budget và queue job thay vì cho tất cả chạy cùng lúc.

### 20.4. Backpressure

Nếu consumer hoặc compiler chậm, producer phải giảm tốc hoặc queue có giới hạn. Queue không giới hạn là một nguồn memory exhaustion.

### 20.5. Graceful degradation

Khi gần chạm budget, language server có thể tắt một số cache hoặc giảm mức phân tích. Không nên âm thầm trả kết quả sai.

### 20.6. Per-tenant quota

Trong dịch vụ multi-tenant, giới hạn memory theo tenant giúp một workspace lớn không chiếm hết tài nguyên của các tenant khác.

## 21. Đo lường memory usage

Tối ưu cần bắt đầu bằng số liệu có thể tái lập.

### 21.1. Heap metrics

Theo dõi heap used, committed, max và occupancy sau GC. Đọc các giá trị cùng thời điểm và hiểu semantics của từng metric.

### 21.2. Allocation profiling

Allocation profiler cho biết class hoặc call site nào tạo nhiều object nhất. Đây là cách tốt để tìm allocation churn.

### 21.3. Heap dump

Heap dump ghi lại object graph tại một thời điểm. Có thể dùng để phân tích dominator tree, retained size và reference path.

### 21.4. GC logs

GC log cho biết thời điểm collection, pause, heap occupancy và một số chi tiết collector. Dùng log để phân biệt heap pressure với allocation spike.

### 21.5. Native memory tracking

JVM Native Memory Tracking có thể giúp phân tích một số vùng native memory nếu được bật. Nó có overhead và không thay thế mọi công cụ hệ điều hành.

### 21.6. Process metrics

Quan sát RSS, virtual memory, thread count, file descriptor và container memory. Một tiến trình có thể vượt memory limit dù heap chưa đầy.

### 21.7. Object histogram

Histogram thống kê số lượng và dung lượng theo class, giúp nhận ra String, AST node, map entry hoặc byte array chiếm ưu thế.

### 21.8. Profiling trong môi trường tương đồng

Chạy profiling với kích thước project, số file, concurrency và dữ liệu gần workload thật. Microbenchmark quá nhỏ có thể không tái hiện retention hoặc peak memory.

## 22. Công cụ và kỹ thuật quan sát trên JVM

Một số công cụ phổ biến hỗ trợ phân tích memory:

| Công cụ | Mục đích chính |
|---|---|
| Java Flight Recorder (JFR) | Ghi allocation, GC, thread và runtime events |
| Java Mission Control (JMC) | Phân tích JFR recording |
| jcmd | Lấy heap info, histogram, dump và VM diagnostics |
| jmap | Hỗ trợ heap dump và histogram trên các JVM phù hợp |
| VisualVM | Quan sát heap, thread và profiling |
| Eclipse MAT | Phân tích heap dump, dominator và retained set |
| async-profiler | Profiling CPU và allocation trong nhiều môi trường JVM |

Lệnh ví dụ:

~~~bash
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump /tmp/dsl-heap.hprof
~~~

Các lệnh cần được chạy trong môi trường có quyền truy cập tiến trình. Heap dump có thể chứa source, secret hoặc dữ liệu người dùng; phải bảo vệ file và xóa theo retention policy.

## 23. Tối ưu memory theo từng giai đoạn

Không nên tối ưu toàn bộ compiler cùng lúc. Hãy xác định phase gây peak hoặc churn rồi chọn thay đổi phù hợp.

### 23.1. Lexer

- Dùng token kind và source range thay vì copy lexeme khi không cần.
- Tránh tạo substring cho mọi token.
- Parse literal lớn theo nhu cầu.
- Reuse buffer có giới hạn nếu benchmark chứng minh có lợi.

### 23.2. Parser

- Tránh tạo node trung gian không cần.
- Dùng compact representation khi object count là bottleneck.
- Giữ source snapshot có lifecycle rõ.
- Cân nhắc incremental parsing cho editor.

### 23.3. Semantic analysis

- Intern symbol và canonical type có kiểm soát.
- Loại bỏ constraint đã giải.
- Dùng index phù hợp thay vì map lồng quá sâu.
- Giải phóng scope tạm sau phase.

### 23.4. IR

- Dùng arena theo compile unit nếu lifetime phù hợp.
- Tránh duplicate metadata.
- Compact source location.
- Hạn chế giữ AST nếu IR đã đủ cho phase tiếp theo.

### 23.5. Code generation

- Stream output khi có thể.
- Dùng StringBuilder hoặc byte buffer hợp lý.
- Tránh nối chuỗi tạo nhiều intermediate String.
- Giải phóng reference tới IR sau khi artifact được tạo.

### 23.6. Runtime

- Dùng bounded queue và collection.
- Tránh giữ execution context sau khi hoàn tất.
- Stream dữ liệu lớn.
- Giới hạn cache và result retention.
- Dùng resource scope để đóng stream và buffer.

## 24. Ví dụ Java: theo dõi và giảm allocation

Ví dụ sau minh họa hai cách tạo output văn bản. Khi nối chuỗi trong vòng lặp, nhiều intermediate String có thể được tạo.

### 24.1. Cách tạo nhiều intermediate String

~~~java
String output = "";
for (Token token : tokens) {
    output = output + token.text();
}
~~~

### 24.2. Dùng StringBuilder

~~~java
StringBuilder output = new StringBuilder();
for (Token token : tokens) {
    output.append(token.text());
}
String result = output.toString();
~~~

StringBuilder giảm số intermediate String trong vòng lặp. Tuy nhiên, nếu output rất lớn, vẫn cần giới hạn kích thước hoặc ghi trực tiếp ra Writer.

### 24.3. Stream token ra Writer

~~~java
try (java.io.BufferedWriter writer =
         java.nio.file.Files.newBufferedWriter(path)) {
    for (Token token : tokens) {
        writer.write(token.text());
    }
}
~~~

Streaming tránh giữ toàn bộ output trong một String nếu consumer có thể nhận dữ liệu tuần tự.

### 24.4. Source span thay vì copy lexeme

~~~java
public record SourceSpan(int start, int end) {
    public String textOf(String source) {
        return source.substring(start, end);
    }
}
~~~

Span giữ hai số nguyên thay vì một String riêng cho mỗi node. Source buffer phải còn tồn tại khi gọi textOf. Với nhiều phiên bản document trong IDE, span phải gắn với đúng snapshot.

### 24.5. Giới hạn collection

~~~java
public final class BoundedBuffer<T> {
    private final int capacity;
    private final java.util.ArrayDeque<T> values = new java.util.ArrayDeque<>();

    public BoundedBuffer(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
    }

    public void add(T value) {
        if (values.size() == capacity) {
            values.removeFirst();
        }
        values.addLast(value);
    }
}
~~~

Buffer giới hạn số phần tử được giữ. Policy loại bỏ phần tử cũ chỉ phù hợp với use case dạng rolling window; queue nghiệp vụ cần backpressure hoặc persistence thay vì âm thầm bỏ dữ liệu.

## 25. Thiết kế memory-safe cho DSL

Một DSL có thể cung cấp construct giúp người dùng kiểm soát tài nguyên.

### 25.1. Bounded buffer

~~~text
buffer "pending-events" {
    capacity = 10000
    on_overflow = backpressure
}
~~~

### 25.2. Streaming pipeline

~~~text
source read_orders()
    |> map(normalize_order)
    |> filter(order -> order.is_valid)
    |> write_orders()
~~~

Pipeline nên có semantics lazy hoặc streaming được định nghĩa rõ. Nếu mỗi stage materialize thành list, lợi ích memory có thể biến mất.

### 25.3. Resource scope

~~~text
using file = open(path) {
    parse(file)
}
~~~

DSL có thể bảo đảm file được đóng khi block kết thúc, kể cả khi có exception hoặc cancellation.

### 25.4. Memory limit

~~~text
execution "large-import" {
    memory_budget = 256MB
    max_records_in_flight = 500
}
~~~

Runtime cần xác định cách đo budget và hành vi khi vượt giới hạn. Một con số khai báo không có enforcement không tạo ra bảo vệ thực tế.

### 25.5. Lazy collection

~~~text
orders = query_orders().as_sequence()
first_ten = orders.take(10)
~~~

Nếu as_sequence chỉ là wrapper nhưng query đã tải toàn bộ dữ liệu, API vẫn eager. Contract phải nêu rõ thời điểm materialization.

## 26. Memory và concurrency

Chạy nhiều compile hoặc workflow đồng thời có thể làm memory tăng gần theo số tác vụ đang hoạt động.

### 26.1. Per-request state

State của request nên có ownership riêng. Không lưu mutable request context trong singleton hoặc static field.

### 26.2. Shared immutable data

Schema, grammar hoặc type metadata bất biến có thể được chia sẻ giữa các thread để giảm bản sao.

### 26.3. Thread-local state

ThreadLocal có thể tránh truyền context qua nhiều hàm nhưng dễ giữ dữ liệu lâu trong thread pool. Phải remove khi kết thúc.

### 26.4. Queue capacity

Executor với unbounded queue có thể tích lũy job và giữ payload lớn. Đặt queue capacity và rejection/backpressure policy.

### 26.5. Parallel compilation

Compile file độc lập có thể chạy song song, nhưng project-wide symbol graph hoặc shared cache cần đồng bộ và giới hạn.

### 26.6. Memory-based scheduling

Scheduler có thể giới hạn concurrency dựa trên estimated input size hoặc memory profile của job. Ước lượng cần được hiệu chỉnh từ quan sát thực tế.

## 27. Memory limit, container và JVM configuration

JVM chạy trong container cần được cấu hình theo tổng memory budget của container.

### 27.1. Heap maximum

Tham số JVM Xmx giới hạn Java heap tối đa. Đặt Xmx bằng toàn bộ container limit có thể không còn chỗ cho metaspace, thread stack, direct buffer và native library.

### 27.2. Initial heap

Tham số Xms xác định heap ban đầu. Giá trị lớn có thể giảm resize nhưng làm tăng memory cam kết ngay từ đầu.

### 27.3. Metaspace

MaxMetaspaceSize có thể đặt giới hạn metaspace. Nếu ứng dụng dùng plugin hoặc generated class, cần theo dõi classloader và class unloading.

### 27.4. Direct memory

MaxDirectMemorySize có thể giới hạn một số direct buffer allocation. Không phải mọi native allocation đều nằm trong giới hạn này.

### 27.5. Thread stack

Mỗi thread tiêu thụ stack native. Tăng số thread có thể làm RSS tăng dù heap không đổi.

### 27.6. Container headroom

Để lại headroom cho native memory, code cache, JIT, thread, TLS và hệ điều hành. Xác định Xmx bằng benchmark và đo RSS trong container thực tế.

### 27.7. OOM behavior

OutOfMemoryError có thể xảy ra do heap, metaspace, direct buffer hoặc native resource. Cần phân biệt loại lỗi và thu thập diagnostics an toàn.

## 28. Quy trình đo và tối ưu

Một quy trình có thể áp dụng cho compiler hoặc runtime DSL:

1. **Xác định workload.** Chọn project nhỏ/lớn, số file, độ sâu AST, số symbol, concurrency và kích thước dữ liệu runtime.
2. **Định nghĩa chỉ số.** Theo dõi heap used, live set, peak RSS, allocation rate, GC pause và object count.
3. **Tạo baseline.** Ghi lại kết quả ở cold start và steady state.
4. **Xác định phase.** Đo riêng lexing, parsing, semantic analysis, lowering, code generation và execution.
5. **Tìm allocation hotspot.** Dùng JFR hoặc allocation profiler để tìm class và call site tạo nhiều object.
6. **Tìm retention path.** Dùng heap dump và dominator tree để xác định object không còn cần nhưng vẫn reachable.
7. **Chọn thay đổi nhỏ.** Ví dụ source span, interning, streaming, bounded cache hoặc giải phóng snapshot.
8. **Đo lại cùng workload.** So sánh memory, latency, throughput và CPU; tránh kết luận từ một chỉ số.
9. **Kiểm tra concurrency.** Đo khi nhiều compile hoặc workflow chạy đồng thời.
10. **Xác nhận container behavior.** Đo RSS và memory limit trong môi trường gần production.
11. **Đặt budget và alert.** Giới hạn queue, cache, in-flight job và memory theo tenant.
12. **Theo dõi sau triển khai.** Quan sát xu hướng, peak và GC thay vì chỉ xem một lần đo.

## 29. Những sai lầm thường gặp

### 29.1. Chỉ nhìn heap used

RSS có thể cao do native memory, thread stack hoặc metaspace. Theo dõi cả process và JVM metrics.

### 29.2. Cho rằng GC sẽ giải quyết mọi vấn đề

Object còn reachable sẽ không được thu hồi. Tìm reference path và lifecycle của cache, listener, thread local hoặc callback.

### 29.3. Tăng heap ngay khi gặp OOM

Tăng heap có thể trì hoãn lỗi nhưng không giải quyết leak, unbounded queue hoặc retention. Xác định vùng memory cạn trước.

### 29.4. Dùng cache không giới hạn

Cache tăng theo số project hoặc input có thể làm tiến trình hết memory. Đặt giới hạn theo số entry và byte ước lượng.

### 29.5. Copy source text nhiều lần

Token và AST có thể giữ nhiều bản sao cùng nội dung. Dùng source span hoặc symbol interning khi phù hợp.

### 29.6. Materialize dữ liệu lớn

Chuyển stream thành list khiến toàn bộ dữ liệu cùng tồn tại. Dùng streaming hoặc batch có giới hạn.

### 29.7. Pool mọi object

Pooling object nhỏ có thể giữ memory lâu và tăng contention. Chỉ pool khi profiling chứng minh có lợi.

### 29.8. Bỏ qua native memory

Heap dump không thể hiện đầy đủ direct buffer hoặc native library. Dùng process metrics và native memory diagnostics.

### 29.9. Giữ AST cũ trong IDE

Document version cũ có thể còn được listener hoặc index giữ. Invalidate và giải phóng snapshot theo lifecycle.

### 29.10. Queue không giới hạn

Khi producer nhanh hơn consumer, queue tích lũy payload. Dùng bounded queue và backpressure.

### 29.11. Chia sẻ mutable context

Shared state có thể gây race và giữ dữ liệu tenant/request ngoài ý muốn. Dùng ownership rõ và immutable shared data.

### 29.12. Tối ưu trước khi đo

Compact representation hoặc arena làm code phức tạp. Đo trước để xác định thay đổi có tác động thực tế.

## 30. Câu hỏi tự kiểm tra

1. Memory usage trong DSL bao gồm những cấu trúc nào ở compiler và runtime?
2. Phân biệt stack, heap, metaspace, direct memory, RSS và virtual memory.
3. Vì sao kích thước source không phản ánh trực tiếp heap footprint của AST?
4. Allocation rate, live set, peak memory và retained size khác nhau thế nào?
5. Vòng đời dữ liệu thay đổi ra sao qua lexing, parsing, semantic analysis, lowering và code generation?
6. Source span và symbol interning giúp giảm memory như thế nào?
7. Arena allocation phù hợp với loại dữ liệu nào và có giới hạn gì?
8. Type graph và generic instantiation có thể tạo memory pressure ra sao?
9. Runtime environment, closure capture và event queue ảnh hưởng retention thế nào?
10. Streaming và backpressure giúp kiểm soát memory của pipeline ra sao?
11. Cache cần giới hạn và invalidation theo những yếu tố nào?
12. Vì sao object pooling không phải lúc nào cũng cải thiện hiệu năng Java?
13. GC quản lý object reachable như thế nào và vì sao GC không tự sửa memory leak?
14. Nêu các nguyên nhân memory leak phổ biến trong language server và plugin.
15. Incremental parsing cần quản lý document snapshot và AST version như thế nào?
16. Memory budget, admission control và per-tenant quota hỗ trợ hệ thống ra sao?
17. JFR, heap dump, GC log và RSS metrics giúp tìm các vấn đề khác nhau thế nào?
18. Vì sao Xmx không nên chiếm toàn bộ memory limit của container?
19. Hãy thiết kế một pipeline DSL xử lý file lớn theo streaming với bounded buffer và resource scope.
20. Hãy mô tả quy trình tìm nguyên nhân memory tăng dần trong language server sau nhiều lần chỉnh sửa file.
