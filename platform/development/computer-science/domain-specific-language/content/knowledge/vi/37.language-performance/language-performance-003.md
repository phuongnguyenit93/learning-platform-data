# Mô hình lớn

Trong các dự án sử dụng ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL), mô hình (model) là biểu diễn có cấu trúc của hệ thống, quy trình, dữ liệu hoặc quy tắc mà DSL mô tả. Một mô hình nhỏ có thể chỉ gồm vài thực thể và quan hệ; một mô hình lớn có thể chứa hàng trăm nghìn phần tử, nhiều module, nhiều loại quan hệ, thư viện dùng chung và dependency xuyên dự án. Khi kích thước tăng, những thao tác từng rất nhanh như parse, resolve tên, kiểm tra kiểu, tìm tham chiếu, hiển thị sơ đồ hoặc sinh mã có thể trở thành nút thắt về CPU, bộ nhớ, I/O và thời gian phản hồi.

**Mô hình lớn (large models)** trong hiệu năng DSL là vấn đề thiết kế cách biểu diễn, nạp, phân tích, truy vấn, cập nhật và sinh đầu ra cho mô hình có quy mô lớn. Mục tiêu không chỉ là làm một lần build chạy nhanh hơn. Một công cụ DSL tốt cần duy trì trải nghiệm tương tác, kết quả chính xác, khả năng mở rộng và mức tiêu thụ tài nguyên có thể dự đoán khi dự án phát triển.

Giải pháp thường kết hợp nhiều kỹ thuật: mô hình dữ liệu gọn, indexing, lazy loading, incremental computation, partitioning, dependency graph, cache có version, xử lý song song, truy vấn có giới hạn và lưu trữ theo nhu cầu. Các kỹ thuật này phải phối hợp với semantics của DSL. Nếu tối ưu làm thay đổi kết quả phân tích hoặc bỏ sót dependency, hệ thống có thể nhanh nhưng không còn đúng.

## 1. Thế nào là mô hình lớn?

Không có một ngưỡng cố định để gọi một model là lớn. Quy mô phụ thuộc vào số phần tử, độ phức tạp quan hệ, lượng metadata, số module, số file nguồn và loại thao tác cần thực hiện.

Một mô hình DSL có thể lớn theo nhiều chiều:

- **Số lượng phần tử:** entity, class, rule, node, field, operation hoặc event.
- **Độ sâu:** object lồng nhau, cây biểu thức hoặc cây kế thừa sâu.
- **Mật độ quan hệ:** số reference, dependency, association hoặc edge giữa các phần tử.
- **Kích thước nguồn:** số file, tổng số dòng và dung lượng văn bản.
- **Số module:** số package, project hoặc namespace độc lập.
- **Lượng metadata:** source span, documentation, annotation, diagnostic và trace.
- **Biến động:** tần suất người dùng sửa model và phạm vi ảnh hưởng của mỗi thay đổi.

Ví dụ một DSL mô tả hệ thống thương mại có thể chứa:

| Thành phần | Quy mô minh họa |
|---|---:|
| Module | 240 |
| Entity và value object | 18.000 |
| Field | 210.000 |
| Operation | 42.000 |
| Reference | 380.000 |
| Rule và constraint | 65.000 |
| Source file | 9.000 |

Các con số chỉ minh họa. Một model có ít node nhưng nhiều edge có thể tốn tài nguyên hơn model có nhiều node độc lập. Vì vậy, không nên đo quy mô chỉ bằng số dòng DSL.

## 2. Những vấn đề hiệu năng thường gặp

Khi model tăng, các triệu chứng có thể xuất hiện ở nhiều giai đoạn:

| Giai đoạn | Triệu chứng |
|---|---|
| Workspace loading | Mở project lâu, dùng nhiều memory |
| Parsing | CPU cao, parse lặp lại nhiều file |
| Name resolution | Lookup chậm, quét toàn bộ symbol |
| Type checking | Kiểm tra lại vùng không thay đổi |
| Validation | Diagnostic xuất hiện muộn hoặc UI bị treo |
| Navigation | Go-to-definition và find references chậm |
| Visualization | Render sơ đồ lớn mất thời gian |
| Generation | Sinh lại toàn bộ output sau một thay đổi nhỏ |
| Build | Task graph lớn, cache miss hoặc nhiều I/O |
| Persistence | Lưu và tải model tốn thời gian |

Cần xác định thao tác nào là bottleneck trước khi tối ưu. Tối ưu parser sẽ không giải quyết được việc render một graph quá lớn; tăng heap có thể che triệu chứng memory nhưng không khắc phục việc giữ nhiều bản sao của cùng một model.

## 3. Kiến trúc xử lý model quy mô lớn

Một pipeline điển hình:

~~~mermaid
flowchart TD
    A[DSL source files] --> B[Source index]
    B --> C[Parser]
    C --> D[Compact syntax representation]
    D --> E[Symbol index]
    E --> F[Semantic model]
    F --> G[Dependency graph]
    G --> H[Incremental analysis]
    H --> I[Query and visualization]
    H --> J[Code generation]
    H --> K[Diagnostics and navigation]
~~~

Các tầng nên có trách nhiệm rõ:

- Source index quản lý file và revision.
- Parser tạo biểu diễn cú pháp.
- Symbol index hỗ trợ tra cứu định danh.
- Semantic model lưu thông tin đã resolve và type.
- Dependency graph mô tả quan hệ ảnh hưởng.
- Incremental analysis chỉ tính lại phần bị tác động.
- Consumer như editor, validator và generator đọc model qua API truy vấn.

Không nhất thiết mọi tầng đều phải được materialize đầy đủ trong memory. Một phần có thể được tính khi cần, lưu trên đĩa hoặc nạp theo module.

## 4. Chọn cấu trúc biểu diễn phù hợp

Cách lưu model ảnh hưởng trực tiếp tới memory và tốc độ truy cập.

Một cây object hướng đối tượng dễ xây dựng và thuận tiện cho traversal, nhưng có thể tạo nhiều object nhỏ, pointer và overhead của runtime. Với model rất lớn, overhead object có thể lớn hơn dữ liệu thực.

Một số cách biểu diễn:

- **Object graph:** mỗi node là object có reference tới node khác.
- **Compact node table:** node được lưu trong mảng hoặc bảng liên tục, reference dùng integer ID.
- **Columnar storage:** thuộc tính cùng loại được lưu thành các mảng riêng.
- **Persistent data structure:** cập nhật tạo phiên bản mới và chia sẻ cấu trúc không đổi.
- **External index/store:** dữ liệu ít dùng nằm trên đĩa hoặc database.
- **Hybrid model:** phần đang hoạt động ở memory, phần còn lại được nạp theo nhu cầu.

Ví dụ node table:

~~~text
NodeTable:
  nodeId[]       -> integer
  kind[]         -> enum
  nameId[]       -> string-table index
  parentId[]     -> integer
  sourceFileId[] -> integer
  startOffset[]  -> integer
  endOffset[]    -> integer
~~~

Reference có thể lưu thành cặp source node ID và target node ID. Việc dùng ID nhỏ giúp giảm chi phí pointer và hỗ trợ serialization/indexing.

Không có cấu trúc nào tốt cho mọi thao tác. Object graph thuận tiện cho truy vấn sâu; columnar layout có lợi cho quét hàng loạt một thuộc tính. Cần chọn dựa trên workload thực tế.

## 5. Tách syntax model và semantic model

Syntax model biểu diễn cấu trúc được viết trong file DSL. Semantic model biểu diễn ý nghĩa sau khi resolve symbol, type và constraint.

Ví dụ nguồn:

~~~text
entity Order {
    customer: Customer
    total: Money
}
~~~

Syntax model có thể lưu token, node declaration và source span. Semantic model có thể lưu rằng Customer trỏ tới entity ID cụ thể, Money là type đã resolve và field total có type đầy đủ.

Tách hai model có lợi ích:

- Syntax tree có thể giữ nguyên source structure và comment.
- Semantic model không phải lưu toàn bộ trivia không cần cho type checking.
- Một syntax node có thể được phân tích lại mà không dựng lại toàn bộ semantic graph.
- Diagnostics có thể ánh xạ về source span.
- Generator có thể tiêu thụ semantic model mà không cần parse text lần nữa.

Không nên giữ các bản sao đầy đủ không cần thiết. Có thể để semantic node tham chiếu syntax node bằng stable ID hoặc source location.

## 6. Compact syntax tree và giảm overhead

Parser thường tạo nhiều node. Với model lớn, cần chú ý:
- Mỗi node có bao nhiêu object.
- Có lưu token text trùng lặp không.
- Có tạo list riêng cho từng node không.
- Có lưu parent và child reference hai chiều không cần thiết không.
- Có giữ source substring trong từng node không.
- Có lưu metadata debug trong production model không.

Một syntax node compact có thể lưu kind, offset, length và chỉ số con. Text được lấy từ source buffer thay vì sao chép chuỗi nhiều lần.

Ví dụ khái niệm:

~~~java
record SyntaxNode(
    NodeKind kind,
    int startOffset,
    int endOffset,
    int firstChild,
    int nextSibling
) {}
~~~

Biểu diễn này dùng index để liên kết node, có thể giảm object allocation. Tuy nhiên, nó làm API traversal phức tạp hơn; có thể cung cấp facade để consumer không phải biết chi tiết storage.

## 7. String interning và symbol identity

Tên module, type, field và function thường được lặp lại nhiều lần. Nếu mỗi lần xuất hiện đều tạo một String riêng, memory usage tăng.

String interning hoặc string table có thể lưu một bản cho mỗi chuỗi duy nhất:

~~~text
StringTable:
  0 -> "Order"
  1 -> "Customer"
  2 -> "Money"
  3 -> "total"

Node:
  nameId = 0
~~~

Cần phân biệt string value với symbol identity. Hai module có thể cùng khai báo tên Customer nhưng là hai symbol khác nhau. Symbol ID cần chứa hoặc liên kết namespace/module identity.

Không nên dùng một global interning table không giới hạn cho input có thể chứa chuỗi tùy ý, vì nó có thể giữ dữ liệu mãi trong memory. Nên giới hạn lifetime theo workspace/model snapshot hoặc dùng cơ chế weak/evictable phù hợp.

## 8. Symbol table và indexing

Name resolution là thao tác thường xuyên. Nếu mỗi reference đều quét toàn bộ model để tìm tên, chi phí có thể tăng gần O(N) cho mỗi lần lookup.

Symbol table tạo chỉ mục:

~~~text
SymbolIndex:
  qualifiedName -> SymbolId
  simpleName    -> [SymbolId]
  moduleId      -> [SymbolId]
  kind          -> [SymbolId]
~~~

Với hash map, lookup trung bình có thể gần O(1); với tree index, lookup có thể O(log N) và hỗ trợ prefix/range query.

Cần xác định quy tắc scope:
- Local scope.
- Module scope.
- Imported namespace.
- Parent/inheritance scope.
- Global built-in scope.
- Alias và re-export.

Index phải phản ánh chính xác precedence và ambiguity rules của DSL. Nếu hai symbol cùng tên, resolver cần báo ambiguity hoặc áp dụng import precedence đã định nghĩa, không lấy phần tử đầu tiên ngẫu nhiên.

## 9. Qualified name và namespace

Trong model lớn, tên ngắn dễ va chạm. Qualified name giúp phân biệt:

~~~text
sales.order.Order
billing.invoice.Invoice
identity.customer.Customer
~~~

Một symbol có thể được nhận diện bằng tuple:

~~~text
SymbolId = (workspaceId, moduleId, localSymbolId)
~~~

Không nhất thiết phải nối chuỗi qualified name ở mọi lookup. Có thể dùng hierarchical index hoặc ID tuple để tránh tạo chuỗi tạm liên tục.

Rename symbol cần cập nhật index và các reference phụ thuộc. Stable symbol ID giúp rename không làm mất identity của phần tử nếu semantics cho phép.

## 10. Lazy loading

Không phải mọi phần của model đều cần trong mọi thao tác. Lazy loading chỉ nạp phần dữ liệu khi consumer yêu cầu.

Ví dụ:
- Mở một module chỉ nạp syntax và symbol index của module đó.
- Hover một type mới nạp documentation hoặc hierarchy cần thiết.
- Mở diagram chỉ nạp các node trong phạm vi view.
- Generator cho target Java chỉ nạp metadata cần cho Java backend.
- Find references truy vấn index mà không dựng toàn bộ object graph.

Một mô hình lazy:

~~~mermaid
flowchart TD
    A[Workspace metadata] --> B[Module index]
    B --> C{Module requested?}
    C -->|No| D[Keep unloaded]
    C -->|Yes| E[Load syntax]
    E --> F[Resolve symbols]
    F --> G[Load dependent modules on demand]
~~~

Lazy loading giảm memory và thời gian khởi động, nhưng cần quản lý trạng thái unloaded/loading/loaded/failed. Nhiều consumer cùng yêu cầu một module nên chia sẻ một load operation thay vì nạp trùng.

## 11. Eager và lazy loading

| Tiêu chí | Eager loading | Lazy loading |
|---|---|---|
| Startup | Có thể chậm | Thường nhanh hơn |
| Memory ban đầu | Cao | Thấp hơn |
| Truy cập lần đầu | Thường nhanh | Có thể có độ trễ |
| Dependency handling | Đơn giản hơn khi mọi thứ đã nạp | Cần quản lý load chain |
| Phù hợp | Model nhỏ hoặc batch analysis | Workspace lớn, tương tác theo vùng |
| Failure | Phát hiện sớm khi load | Có thể xuất hiện lúc truy cập |

Một hệ thống có thể dùng hybrid: nạp eager symbol index và metadata nhẹ, còn AST đầy đủ hoặc documentation được nạp lazy.

Lazy loading không nên làm kết quả phân tích phụ thuộc vào thứ tự truy cập. Cùng một truy vấn cần cho cùng kết quả dù module được nạp trước hay sau.

## 12. Partitioning theo module hoặc vùng

Partitioning chia model thành những phần có thể xử lý độc lập. Ranh giới thường dựa trên:
- Module/package.
- Bounded context.
- Service hoặc subsystem.
- Namespace.
- File group.
- Graph community.
- Deployment target.

Ví dụ:

~~~text
Workspace
  identity/
  catalog/
  ordering/
  billing/
  fulfillment/
  analytics/
~~~

Mỗi partition có thể có:
- Source files.
- Symbol index.
- Semantic model.
- Dependency summary.
- Revision/fingerprint.
- Diagnostics.
- Cache entries.

Khi thay đổi trong billing, hệ thống trước tiên xử lý partition billing và những partition phụ thuộc trực tiếp hoặc gián tiếp.

Partition cần có boundary rõ. Nếu mọi module phụ thuộc lẫn nhau, partitioning không giảm được nhiều công việc. Có thể cần tách interface/schema ổn định và giảm dependency vòng.

## 13. Dependency graph của model

Một phần tử thay đổi có thể ảnh hưởng phần tử khác. Dependency graph mô tả quan hệ này.

Ví dụ:

~~~mermaid
flowchart TD
    A[Customer entity] --> B[Order.customer field]
    A --> C[Customer API schema]
    B --> D[Order validator]
    B --> E[Order Java generator]
    C --> F[Client SDK generator]
~~~

Nếu Customer đổi field, hệ thống có thể xác định consumer nào cần phân tích lại hoặc regenerate.

Graph cần phân biệt loại cạnh:
- Reference/name resolution.
- Type dependency.
- Inheritance.
- Import/module dependency.
- Validation dependency.
- Generator dependency.
- Documentation dependency.

Không phải mọi cạnh đều có cùng quy tắc invalidation. Thay đổi comment có thể chỉ ảnh hưởng documentation; thay đổi type có thể ảnh hưởng validator, compiler và client generator.

## 14. Tránh dependency graph quá dày

Graph quá dày khiến một thay đổi nhỏ invalidates phần lớn model. Một số cách giảm coupling:

- Phụ thuộc vào interface hoặc contract thay vì implementation detail.
- Tách module theo domain responsibility.
- Hạn chế import toàn module khi chỉ cần một symbol.
- Dùng stable schema boundary.
- Tránh cyclic dependency.
- Tạo dependency summary thay vì liên kết mọi node với mọi node.
- Phân biệt dependency compile-time và runtime.

Nếu một module import toàn bộ module khác, thay đổi một symbol không liên quan vẫn có thể làm invalidation rộng. Symbol-level dependency giúp chính xác hơn nhưng cần chi phí index và bookkeeping.

## 15. Incremental parsing

Khi người dùng sửa một file, parse lại toàn bộ workspace thường không cần thiết. Incremental parsing cập nhật phần cây cú pháp bị ảnh hưởng.

Một quy trình có thể là:

1. Nhận text edit với range và document version.
2. Xác định vùng cú pháp bị ảnh hưởng.
3. Tái sử dụng node ngoài vùng thay đổi.
4. Parse lại vùng nhỏ hoặc file tương ứng.
5. Cập nhật source span và syntax index.
6. Phát ra delta cho semantic analysis.

Incremental parser cần xử lý trường hợp edit làm thay đổi cấu trúc lớn như thêm hoặc xóa dấu ngoặc bao trùm nhiều dòng. Khi không thể tái sử dụng an toàn, parser có thể fallback parse toàn file.

Tái sử dụng node cần bảo đảm source offset được điều chỉnh đúng và không giữ reference tới buffer cũ đã giải phóng.

## 16. Incremental semantic analysis

Sau parsing, semantic analysis có thể gồm name resolution, type checking, constraint validation và rule analysis.

Thay vì chạy toàn bộ, engine dùng dependency graph để xác định phần bị ảnh hưởng:

- Symbol được thêm hoặc xóa làm thay đổi scope index.
- Type signature thay đổi làm invalidates consumer.
- Body expression thay đổi có thể chỉ ảnh hưởng local type result.
- Documentation thay đổi có thể chỉ ảnh hưởng hover/docs.
- Import thay đổi có thể ảnh hưởng resolution của module.

Một pipeline:

~~~mermaid
flowchart TD
    A[Text change] --> B[Incremental parse]
    B --> C[Changed syntax nodes]
    C --> D[Update symbol index]
    D --> E[Find affected dependencies]
    E --> F[Recompute semantic facts]
    F --> G[Update diagnostics and consumers]
~~~

Incremental analysis cần có dependency tracking đủ chính xác. Nếu không chắc một phần có bị ảnh hưởng không, có thể invalidates phạm vi rộng hơn để bảo toàn correctness.

## 17. Stable ID và structural sharing

Khi tạo model snapshot mới, không nhất thiết sao chép toàn bộ node. Persistent data structures hoặc structural sharing cho phép snapshot mới tái sử dụng phần không đổi.

Ví dụ:

~~~text
Snapshot A:
  Module 1 -> Node set X
  Module 2 -> Node set Y
  Module 3 -> Node set Z

Snapshot B after editing Module 2:
  Module 1 -> reuse X
  Module 2 -> new Y'
  Module 3 -> reuse Z
~~~

Stable ID giúp giữ liên kết giữa revision cũ và mới. Nhưng ID phải có quy tắc khi node bị split, merge hoặc thay đổi identity. Không nên suy luận identity chỉ từ vị trí dòng vì thêm một dòng đầu file có thể làm mọi ID thay đổi.

Structural sharing giảm copy cost nhưng tăng độ phức tạp về lifetime và memory retention. Snapshot cũ cần được giải phóng khi không còn editor, task hoặc query nào tham chiếu.

## 18. Cache theo từng tầng

Có thể cache kết quả ở nhiều tầng:

- Source content hash.
- Parsed syntax tree.
- Symbol index.
- Resolved reference.
- Type inference result.
- Validation result.
- Query result.
- Generated artifact.
- Visualization layout.

Mỗi cache cần key và invalidation policy phù hợp. Ví dụ type inference cache phụ thuộc syntax node, symbol environment và type system version. Generated output còn phụ thuộc generator version, target options và dependency artifacts.

Không nên dùng một global cache key chỉ dựa trên file path. Nội dung file có thể thay đổi; cùng path không có nghĩa cùng revision.

## 19. Fingerprint và cache invalidation

Fingerprint là dấu vân tay được tính từ các yếu tố ảnh hưởng kết quả:

~~~text
fingerprint = hash(
    sourceContent
    + importedSymbolVersions
    + languageVersion
    + analyzerVersion
    + configuration
)
~~~

Nếu fingerprint không đổi, có thể tái sử dụng kết quả cache. Nếu một dependency thay đổi, fingerprint của consumer cần thay đổi theo dependency summary.

Các nguyên tắc:
- Bao gồm mọi input ảnh hưởng kết quả.
- Loại bỏ yếu tố không ổn định như absolute workspace path nếu không cần.
- Có version cho thuật toán hash hoặc serialization khi cần migration.
- Kiểm tra checksum của cache entry.
- Không dùng cache entry từ schema/engine version không tương thích.
- Có giới hạn dung lượng và eviction policy.

Cache invalidation sai là rủi ro correctness. Cache miss chỉ làm chậm; cache hit sai có thể khiến compiler hoặc validator sử dụng model cũ.

## 20. Cache phân tán và build cache

Với team hoặc CI, cache có thể được chia sẻ giữa nhiều máy. Cache key cần độc lập với môi trường cục bộ nếu output có thể tái sử dụng.

Cần xem xét:
- Toolchain và OS/architecture.
- Locale, timezone và encoding.
- Path sensitivity.
- Compiler flags.
- Plugin/generator versions.
- Dependency checksums.
- Access control và tenant isolation.
- Cache poisoning.
- Artifact integrity.
- Eviction và retention.

Không nên chia sẻ cache output có chứa secret hoặc dữ liệu riêng của một tenant cho người dùng khác. Cache phân tán cần xác thực nguồn và kiểm tra integrity.

## 21. Parallel analysis

Các module độc lập có thể được parse, resolve hoặc validate song song.

Ví dụ:

~~~mermaid
flowchart TD
    A[Workspace index] --> B[Module identity]
    A --> C[Module catalog]
    A --> D[Module billing]
    B --> E[Merge diagnostics]
    C --> E
    D --> E
    E --> F[Workspace result]
~~~

Parallelism có thể giảm wall-clock time nhưng làm tăng memory đồng thời. Nếu mọi module cùng nạp dependency lớn, peak memory có thể vượt giới hạn.

Cần:
- Giới hạn số worker.
- Chia task theo kích thước ước lượng.
- Tránh lock contention trên global symbol table.
- Dùng immutable snapshot cho read-heavy analysis.
- Gom kết quả theo deterministic order.
- Hủy công việc không còn cần sau khi user edit mới.
- Đảm bảo plugin extension thread-safe nếu được gọi song song.

Không nên song song hóa các thao tác có dependency dữ liệu chưa được giải quyết. Build graph hoặc analysis graph phải mô tả quan hệ trước khi lập lịch.

## 22. Scheduling và backpressure

Editor có thể tạo nhiều yêu cầu khi người dùng gõ liên tục. Nếu mỗi keystroke tạo một analysis job và tất cả đều được xếp hàng, hệ thống sẽ xử lý cả những revision đã lỗi thời.

Backpressure và cancellation giúp:
- Gộp nhiều thay đổi gần nhau.
- Hủy analysis của document version cũ.
- Ưu tiên request tương tác như completion hoặc hover.
- Hạ ưu tiên full validation.
- Giới hạn queue size.
- Chỉ chạy full workspace analysis khi idle hoặc theo yêu cầu.

Một scheduler có thể ưu tiên:
1. Parse phần file đang mở.
2. Completion/hover/navigation.
3. Local diagnostics.
4. Cross-module analysis.
5. Full workspace validation.
6. Background indexing hoặc documentation.

Ưu tiên phải tránh starvation: tác vụ nền quan trọng vẫn cần có cơ hội hoàn tất.

## 23. Query model thay vì duyệt toàn bộ graph

Consumer thường chỉ cần một phần model. Thay vì trả toàn bộ object graph, cung cấp API truy vấn:

~~~text
findSymbol(qualifiedName)
findReferences(symbolId, scope)
getChildren(nodeId, page, pageSize)
getDependencies(moduleId)
queryElements(kind, predicate, limit)
getSourceLocation(symbolId)
~~~

Query API có thể dùng index để tránh traversal toàn graph. Với danh sách lớn, hỗ trợ pagination, cursor hoặc streaming.

Một query cần có:
- Filter rõ.
- Limit hoặc pagination.
- Cancellation.
- Snapshot/revision.
- Ordering semantics.
- Projection để chỉ lấy field cần thiết.

Không nên trả hàng trăm nghìn node cho UI chỉ để hiển thị một danh sách. UI nên yêu cầu page hoặc subset theo viewport.

## 24. Visualization cho graph lớn

Sơ đồ của model lớn có thể chứa hàng nghìn node và edge. Render tất cả cùng lúc thường không hữu ích cho người dùng và có thể làm browser/IDE chậm.

Các kỹ thuật:
- Overview và drill-down.
- Collapse module/package.
- Cluster theo domain hoặc dependency.
- Search và filter.
- Virtualized rendering.
- Level of detail.
- Lazy expansion.
- Edge aggregation.
- Viewport culling.
- Giới hạn số node/edge hiển thị.
- Tách layout computation khỏi UI thread.

Ví dụ, overview chỉ hiển thị module và dependency giữa module. Khi người dùng mở module, mới tải entity và quan hệ bên trong.

Visualization nên phân biệt:
- Tổng số phần tử trong model.
- Số phần tử đang hiển thị.
- Số phần tử đã được load.
- Phạm vi filter đang áp dụng.

Không nên làm người dùng hiểu nhầm sơ đồ đã lọc là toàn bộ model.

## 25. Persistence và workspace database

Model lớn có thể cần lưu index hoặc semantic facts trên đĩa để giảm startup cost. Một workspace store có thể chứa:
- File inventory.
- Content hashes.
- Symbol index.
- Dependency summaries.
- Semantic metadata.
- Cache entries.
- Schema/version metadata.

Persistence giúp mở lại project mà không cần tính lại mọi thứ. Nhưng store cần có invalidation khi source, analyzer hoặc DSL version thay đổi.

Có thể dùng embedded database, key-value store, serialized index hoặc file partition. Chọn theo workload và yêu cầu transaction/concurrency.

Không nên xem persistent cache là nguồn sự thật. DSL source và configuration vẫn là dữ liệu gốc; index có thể bị xóa và tái tạo.

## 26. Memory management

Memory pressure thường đến từ:
- Nhiều AST node.
- Nhiều String trùng lặp.
- Reference object và collection overhead.
- Source buffer giữ lâu.
- Duplicate semantic model.
- Diagnostics và trace tích lũy.
- Snapshot cũ còn được tham chiếu.
- Cache không có eviction.
- Parallel tasks tạo peak memory cao.

Biện pháp:
- Dùng compact representation và ID.
- Giảm duplicate text/metadata.
- Nạp lazy.
- Giải phóng source buffer không còn cần.
- Giới hạn cache và diagnostic retention.
- Dùng weak/soft reference chỉ khi semantics cho phép.
- Đo retained heap và allocation rate.
- Giới hạn concurrency theo memory budget.
- Dọn snapshot cũ khi không còn consumer.

Không nên tối ưu bằng cách dùng weak reference cho mọi thứ. Một semantic fact bị thu hồi giữa một thao tác có thể gây reload liên tục hoặc kết quả không nhất quán. Lifetime nên được quản lý rõ bằng workspace/session/snapshot.

## 27. Garbage collection và allocation pressure

Trong runtime có garbage collector, lượng object allocation lớn có thể gây GC pause và throughput giảm. Một thao tác tạo hàng triệu object tạm rồi bỏ ngay vẫn có thể gây áp lực đáng kể.

Cần đo:
- Allocation rate.
- Young/old generation behavior.
- Pause time.
- Retained heap.
- Object count theo loại.
- Frequency của full GC.
- Peak memory trong full analysis.

Object pooling đôi khi giúp nhưng cũng có thể làm code phức tạp và giữ memory lâu hơn. Chỉ dùng sau khi profiling chứng minh allocation cụ thể là bottleneck và pool không gây contention.

## 28. I/O và source access

Model lớn thường gồm hàng nghìn file. I/O có thể là bottleneck nếu tool đọc file tuần tự hoặc đọc lại nội dung nhiều lần.

Các kỹ thuật:
- File inventory và metadata cache.
- Content hash incremental.
- Batched reads.
- Memory-mapped file khi phù hợp.
- Asynchronous I/O.
- Watch service/file system events.
- Ignore generated/build/vendor directories theo policy.
- Giới hạn file size.
- Tránh scan toàn bộ filesystem ở mỗi thao tác.

File watcher có thể mất event hoặc gộp nhiều event. Hệ thống nên có cơ chế reconcile bằng scan/hash định kỳ hoặc khi phát hiện event gap, thay vì tin watcher là nguồn tuyệt đối.

## 29. Chỉ mục tham chiếu và find references

Find references trên model lớn không nên quét mọi file mỗi lần. Khi semantic analysis resolve reference, có thể xây reverse index:

~~~text
ReferenceIndex:
  targetSymbolId -> [
    sourceFileId,
    sourceNodeId,
    sourceSpan
  ]
~~~

Khi người dùng yêu cầu find references, hệ thống tra index và chỉ đọc các source span liên quan.

Index cần được cập nhật khi:
- Reference được thêm/xóa.
- Symbol bị rename.
- Scope/import thay đổi làm target resolve khác.
- Module bị xóa.
- File được move hoặc đổi namespace.

Reference index phải gắn với snapshot/version để tránh trả vị trí của revision cũ.

## 30. Incremental diagnostics

Diagnostics của model lớn có thể lên tới hàng chục nghìn. Cần quản lý theo file hoặc partition thay vì một danh sách global được tạo lại toàn bộ.

Mỗi diagnostic nên có:
- Stable code.
- Source URI và span.
- Severity.
- Message.
- Owner/analyzer.
- Document version hoặc model snapshot.
- Optional related locations.

Khi một file thay đổi, có thể xóa và tính lại diagnostics thuộc file hoặc dependency region bị ảnh hưởng. Diagnostics cross-file cần có dependency tracking để không bị giữ stale.

UI nên giới hạn số diagnostic hiển thị hoặc hỗ trợ grouping theo module, severity và code. Có thể giữ tổng count riêng với danh sách page.

## 31. Generation trên model lớn

Generator có thể tiêu thụ semantic model và tạo hàng nghìn artifact. Một số chiến lược:

- Generate theo module hoặc target.
- Chỉ generate phần bị ảnh hưởng.
- Streaming output thay vì giữ mọi nội dung trong memory.
- Dùng template đã compile.
- Tái sử dụng output khi fingerprint không đổi.
- Tách generation planning khỏi file writing.
- Ghi staging rồi publish theo batch.
- Ghi manifest và checksum.
- Giới hạn parallel workers theo I/O và memory.

Nếu generator tạo một file tổng hợp lớn, incremental generation có thể khó hơn. Có thể chia output theo symbol/module hoặc tạo intermediate artifact rồi merge bằng task riêng.

Không nên ghi trực tiếp output cuối trong lúc generation chưa hoàn tất nếu consumer có thể đọc tập file nửa mới nửa cũ.

## 32. Parallel generation và deterministic output

Nhiều module có thể generate song song nếu output độc lập. Nhưng thứ tự ghi file, iteration qua map hoặc merge diagnostics có thể không ổn định.

Để output deterministic:
- Sort module/symbol theo key ổn định.
- Không dựa vào hash map iteration order.
- Dùng encoding/newline cố định.
- Không ghi timestamp thay đổi nếu không cần.
- Chuẩn hóa path separator.
- Định nghĩa collision policy.
- Merge partial outputs theo thứ tự ổn định.
- Đảm bảo plugin generator tuân thủ thread safety.

Kết quả cần giống nhau khi chạy một worker hoặc nhiều worker, ngoại trừ metadata được chủ ý cho phép thay đổi.

## 33. Model lớn và distributed processing

Khi một workspace vượt giới hạn một process hoặc cần xử lý trên nhiều máy, có thể phân tán phân tích hoặc generation.

Một kiến trúc có thể gồm:
- Coordinator tạo execution plan.
- Worker nhận partition và input fingerprint.
- Worker tải dependency artifact cần thiết.
- Worker trả semantic summary hoặc generated artifact.
- Coordinator merge kết quả và diagnostics.

Phân tán phù hợp với batch analysis hoặc CI. Với thao tác editor yêu cầu latency thấp, network round-trip có thể lớn hơn lợi ích; local incremental analysis thường tốt hơn.

Cần xử lý:
- Partition ownership.
- Serialization/versioning.
- Retry và idempotency.
- Worker failure.
- Cache locality.
- Data transfer size.
- Consistency giữa snapshot.
- Security và tenant isolation.

Không nên chia model tùy tiện nếu symbol resolution hoặc dependency xuyên partition cần nhiều round-trip. Interface summary hoặc symbol index được chia sẻ có thể giảm chi phí.

## 34. Đo hiệu năng: latency, throughput và memory

Tối ưu cần số đo. Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa |
|---|---|
| Cold startup | Thời gian mở workspace khi chưa có cache |
| Warm startup | Thời gian mở lại với index/cache |
| Parse time | Thời gian parse source |
| Resolution time | Thời gian resolve symbol/reference |
| Analysis time | Thời gian type checking và validation |
| Incremental latency | Thời gian phản hồi sau một edit |
| Navigation latency | Thời gian go-to-definition/find references |
| Generation time | Thời gian sinh artifact |
| Peak heap | Bộ nhớ tối đa |
| Retained heap | Bộ nhớ còn giữ sau thao tác |
| Allocation rate | Tốc độ tạo object |
| Cache hit rate | Tỷ lệ kết quả được tái sử dụng |
| CPU utilization | Mức sử dụng CPU |
| I/O throughput | Tốc độ đọc/ghi |

Nên đo p50, p95 và p99 cho thao tác tương tác. Một thao tác trung bình 50 ms nhưng thỉnh thoảng mất 5 giây vẫn gây trải nghiệm khó chịu.

## 35. Benchmark và workload thực tế

Benchmark cần phản ánh model thực tế:
- Số file và kích thước phân bố.
- Số symbol/reference.
- Dependency depth và graph density.
- Tỷ lệ file thay đổi.
- Tần suất editor edit.
- Số consumer query đồng thời.
- Cache cold/warm.
- Module lớn nhất.
- Generator target và output size.

Nên có nhiều workload:
1. Cold full workspace load.
2. Warm workspace reopen.
3. Sửa một field local.
4. Đổi public type được nhiều module tham chiếu.
5. Rename symbol.
6. Find references trên symbol phổ biến.
7. Full validation.
8. Generate một module.
9. Full generation.
10. Visualization overview và drill-down.

Một benchmark chỉ chạy một lần trên model tổng hợp có thể không phản ánh bottleneck thật. Cần lưu dataset, tool version và cấu hình để so sánh giữa các phiên bản.

## 36. Profiling và tìm bottleneck

Một quy trình profiling:

1. Xác định thao tác chậm cụ thể.
2. Tạo workload tái lập.
3. Đo baseline và phân tách thời gian theo phase.
4. Thu CPU profile, allocation profile và memory snapshot.
5. Tìm hot path hoặc retained object.
6. Đưa ra giả thuyết tối ưu.
7. Thay đổi một yếu tố.
8. Chạy lại workload và so sánh.
9. Kiểm tra correctness và cache invalidation.
10. Ghi lại kết quả.

CPU profile trả lời hàm nào tiêu tốn CPU. Allocation profile cho biết object nào được tạo nhiều. Heap dump giúp tìm object còn được giữ. I/O trace cho biết thời gian chờ disk hoặc network.

Không nên tối ưu dựa trên cảm giác hoặc chỉ nhìn tổng thời gian build. Một build chậm có thể dành phần lớn thời gian tải dependency, không phải xử lý model.

## 37. Độ phức tạp thuật toán

Các thao tác trên model lớn cần xem xét complexity:

- Quét toàn bộ N node: O(N).
- Lookup qua hash index: trung bình O(1).
- Lookup qua balanced tree: O(log N).
- Sort N phần tử: O(N log N).
- So sánh mọi cặp: O(N²).
- Traversal graph: O(V + E).
- Recompute toàn workspace sau mỗi edit: O(N) mỗi lần.
- Incremental update: có thể gần O(K) với K là phần bị ảnh hưởng, nếu dependency index chính xác.

Một vòng lặp lồng nhau trên toàn bộ node có thể trở thành O(N²). Ví dụ, tìm parent bằng cách quét tất cả node cho mỗi node con sẽ rất đắt; map parent ID có thể giảm xuống gần tuyến tính.

Tuy nhiên, complexity lý thuyết không thay thế profiling. Constant factor, allocation, cache locality và I/O có thể chi phối thực tế.

## 38. Giới hạn truy vấn và kiểm soát workload

API query trên model lớn nên có giới hạn:
- Page size tối đa.
- Result count limit.
- Timeout.
- Cancellation.
- Traversal depth.
- Maximum graph expansion.
- Filter requirement cho truy vấn rộng.
- Rate limit theo consumer.
- Projection để giảm payload.

Ví dụ:

~~~text
query references(symbolId)
    pageSize 100
    timeout 2s
    includeLocations true
~~~

Nếu client muốn tất cả kết quả, có thể dùng cursor hoặc streaming API. Tránh trả một collection khổng lồ trong một response và giữ tất cả object trong memory.

Các truy vấn đặc biệt nặng như “tìm mọi dependency xuyên workspace” có thể chạy background và trả job ID thay vì chặn editor thread.

## 39. Concurrency và consistency của snapshot

Trong khi user sửa DSL, background analyzer có thể đang đọc model. Nếu analyzer thấy một nửa trạng thái cũ và một nửa trạng thái mới, kết quả có thể không nhất quán.

Một cách là immutable snapshot:
- Mỗi edit tạo model revision mới.
- Reader giữ snapshot cụ thể.
- Writer tạo snapshot kế tiếp.
- Khi hoàn tất, consumer chuyển sang revision mới.
- Snapshot cũ được giải phóng khi không còn reader.

Cần gắn diagnostics, index và generated artifacts với revision tương ứng. Nếu kết quả từ snapshot cũ hoàn tất sau snapshot mới, scheduler cần bỏ qua hoặc đánh dấu stale.

Không nên khóa toàn workspace trong suốt một lần analysis dài nếu editor cần tiếp tục phản hồi. Read snapshot và publish delta thường giúp giảm lock contention.

## 40. Quản lý model bị lỗi hoặc không hoàn chỉnh

Khi người dùng đang gõ, DSL có thể tạm thời không hợp lệ. Một model lớn không nên mất toàn bộ khả năng hỗ trợ chỉ vì một file có syntax error.

Có thể:
- Giữ syntax tree gần nhất hợp lệ cho phần không đổi.
- Tạo error node cho vùng parse lỗi.
- Đánh dấu semantic fact chưa xác định.
- Tiếp tục phân tích module độc lập.
- Tránh sinh output production từ model chưa hợp lệ.
- Hiển thị diagnostics theo file.
- Phân biệt stale result và current result.

Partial model hữu ích cho editor, completion và navigation. Nhưng generator hoặc deployment cần yêu cầu model ở trạng thái validated phù hợp.

## 41. Incremental invalidation chính xác

Một hệ thống incremental cần biết phần nào bị ảnh hưởng. Nếu invalidation quá rộng, hiệu năng kém. Nếu quá hẹp, kết quả sai.

Ví dụ đổi tên field:
- Symbol index của module khai báo thay đổi.
- References tới symbol có thể cần resolve lại.
- Validator phụ thuộc field name cần chạy lại.
- Generator tạo class/schema có thể bị ảnh hưởng.
- Documentation không liên quan có thể được giữ cache.

Có thể phân loại dependency theo loại thay đổi:
- Syntax-only.
- Public signature.
- Type.
- Value/constant.
- Documentation.
- Annotation/metadata.
- Import/namespace.
- Generator configuration.

Một dependency summary có thể lưu loại fact mà consumer sử dụng, giúp invalidation chính xác hơn.

## 42. Giới hạn và degrade gracefully

Model có thể lớn hơn mức mà máy hiện tại xử lý mượt. Thay vì treo hoặc hết memory, công cụ nên degrade có kiểm soát:

- Chỉ index module đang mở.
- Tạm hoãn full validation.
- Giới hạn graph visualization.
- Tắt expensive analysis theo cấu hình.
- Chạy background với progress.
- Cho phép người dùng chọn scope.
- Báo rõ phần nào chưa được phân tích.
- Giữ thao tác cơ bản như parse local và navigation hoạt động.

Không được hiển thị trạng thái “valid” khi thực tế validator đã bị bỏ qua do giới hạn tài nguyên. Trạng thái partial/deferred phải được thể hiện rõ.

## 43. Kiểm thử hiệu năng và correctness

Tối ưu model lớn cần test cả kết quả lẫn tài nguyên.

### 43.1. Correctness tests

- Name resolution giống giữa full và incremental analysis.
- Diagnostics không bị stale.
- Reference index trả đủ vị trí.
- Cache hit cho cùng kết quả với compute mới.
- Lazy và eager loading cho cùng semantics.
- Parallel và sequential analysis cho cùng kết quả.
- Snapshot cũ không bị trộn với snapshot mới.
- Partition merge không mất symbol hoặc edge.

### 43.2. Performance tests

- Cold/warm startup.
- Full parse và incremental parse.
- Full/incremental type checking.
- Find references.
- Graph query và visualization.
- Generation theo module và toàn workspace.
- Peak/retained heap.
- Allocation rate.
- Cache hit/miss.
- Concurrent editor requests.

### 43.3. Stress tests

- Model lớn hơn bình thường nhiều lần.
- Graph dày và nhiều dependency cycle.
- File cực lớn.
- Deeply nested structures.
- Rapid edits.
- Nhiều module thay đổi đồng thời.
- Cache corruption.
- Worker cancellation/failure.
- Disk gần đầy.
- Memory pressure.

Test hiệu năng nên có threshold hoặc trend report, nhưng cần chạy trên môi trường tương đối ổn định để tránh noise.

## 44. Quy trình tối ưu model lớn

Có thể áp dụng theo thứ tự:

1. **Định nghĩa workload:** xác định model lớn ở khía cạnh node, edge, file hay update rate.
2. **Đo baseline:** latency, throughput, memory và I/O.
3. **Profile bottleneck:** parse, index, resolution, validation, query hay generation.
4. **Chọn biểu diễn:** compact node, ID, string table hoặc hybrid storage.
5. **Xây index:** symbol, reference và dependency.
6. **Phân vùng:** module hoặc bounded context có boundary rõ.
7. **Nạp theo nhu cầu:** metadata eager, AST/semantic detail lazy.
8. **Tính incremental:** parse, resolve, validate và generate theo phần thay đổi.
9. **Cache theo fingerprint:** version mọi dependency và configuration.
10. **Lập lịch song song:** giới hạn worker và backpressure.
11. **Giới hạn query/visualization:** pagination, cancellation và level of detail.
12. **Quản lý snapshot và memory:** giải phóng dữ liệu cũ, giới hạn cache.
13. **Kiểm tra correctness:** so sánh full/incremental, cache/non-cache và parallel/sequential.
14. **Đo lại:** so sánh cùng workload và ghi nhận trade-off.

## 45. Nguyên tắc thiết kế

- **Đo trước khi tối ưu:** xác định bottleneck bằng workload tái lập.
- **Chọn biểu diễn theo workload:** object graph, node table và columnar layout có trade-off khác nhau.
- **Tách syntax khỏi semantic facts:** tránh giữ metadata trùng lặp.
- **Dùng stable ID:** không phụ thuộc vị trí dòng hoặc thứ tự parse.
- **Index cho thao tác thường dùng:** symbol, reference và dependency lookup không nên quét toàn model.
- **Nạp lazy có kiểm soát:** cùng truy vấn phải cho cùng semantics bất kể thứ tự nạp.
- **Partition theo boundary có ý nghĩa:** module cần có dependency rõ và đủ độc lập.
- **Incremental theo dependency:** chỉ tính lại phần bị ảnh hưởng, nhưng ưu tiên correctness khi không chắc.
- **Cache gắn fingerprint:** cache hit phải tương đương compute mới.
- **Giới hạn concurrency theo memory:** chạy song song quá nhiều có thể làm peak heap tăng.
- **Hủy công việc stale:** editor không nên xử lý hàng đợi của revision đã cũ.
- **Query có pagination và cancellation:** không materialize kết quả khổng lồ cho UI.
- **Visualization theo level of detail:** overview, cluster và drill-down giúp người dùng hiểu model.
- **Quản lý snapshot nhất quán:** diagnostics và artifact phải gắn với đúng model revision.
- **Degrade minh bạch:** partial analysis phải được đánh dấu rõ, không báo valid giả.
- **Kiểm thử correctness song song với hiệu năng:** tối ưu không được làm mất reference hoặc diagnostics.
- **Giữ source là nguồn sự thật:** persistent index và cache có thể tái tạo, không thay thế DSL gốc.

Mô hình lớn đòi hỏi DSL tooling được thiết kế như một hệ thống dữ liệu có index, dependency, snapshot và chiến lược tính toán gia tăng. Khi biểu diễn gọn, tra cứu có index, nạp và phân tích theo nhu cầu, cache dựa trên fingerprint, query có giới hạn và tác vụ được lập lịch theo tài nguyên, công cụ có thể xử lý workspace lớn mà vẫn giữ trải nghiệm tương tác và tính đúng đắn.
