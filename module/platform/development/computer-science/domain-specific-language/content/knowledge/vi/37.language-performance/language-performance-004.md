# Phân tích tăng dần

Trong hiệu năng của ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), **phân tích tăng dần (incremental analysis)** là kỹ thuật chỉ phân tích lại phần dữ liệu bị ảnh hưởng sau một thay đổi, đồng thời tái sử dụng kết quả phân tích trước đó ở những phần không đổi. Thay vì mỗi lần người dùng sửa một dòng DSL đều phải đọc, phân tích cú pháp, phân giải tên, kiểm tra kiểu và xây dựng toàn bộ mô hình từ đầu, toolchain xác định chính xác phần nào đã thay đổi, phần nào phụ thuộc vào nó và chỉ tính lại những kết quả cần thiết.

Ví dụ, một project DSL có 300 module. Người dùng chỉ sửa một biểu thức trong module billing. Nếu thay đổi đó không ảnh hưởng đến module catalog hoặc reporting, IDE và compiler có thể giữ nguyên kết quả phân tích của các module độc lập. Chỉ module billing và những phần thực sự phụ thuộc vào interface hoặc kết quả của nó cần được cập nhật. Điều này giúp phản hồi nhanh hơn, giảm CPU và memory, đồng thời cải thiện trải nghiệm khi làm việc với project lớn.

Incremental analysis không đơn giản là lưu kết quả cũ rồi bỏ qua các bước tiếp theo. Hệ thống phải theo dõi dependency, xác định input nào ảnh hưởng đến output nào, phát hiện thay đổi chính xác, vô hiệu hóa cache khi cần và bảo đảm kết quả cuối tương đương với một lần phân tích đầy đủ trên cùng snapshot đầu vào. Nếu bỏ sót một dependency, toolchain có thể hiển thị kết quả cũ dù source đã thay đổi. Nếu invalidation quá rộng, hệ thống vẫn đúng nhưng mất lợi ích hiệu năng.

## 1. Phân tích tăng dần là gì?

Phân tích tăng dần là cách duy trì kết quả phân tích qua nhiều phiên bản của input. Mỗi thay đổi tạo ra một phiên bản mới; engine xác định phần bị ảnh hưởng rồi cập nhật những kết quả liên quan.

### 1.1. Full analysis

Full analysis xử lý toàn bộ input như một đơn vị. Với compiler DSL, quy trình có thể gồm đọc source, lexing, parsing, tạo AST, phân giải symbol, type checking, validation và sinh intermediate representation. Cách này đơn giản và thường là baseline để so sánh tính đúng đắn.

### 1.2. Incremental analysis

Incremental analysis nhận biết phần thay đổi và cập nhật một phần các kết quả. Những node không bị ảnh hưởng có thể tiếp tục sử dụng kết quả cũ nếu fingerprint và dependency của chúng vẫn hợp lệ.

### 1.3. Phân tích theo phiên bản

Mỗi lần chỉnh sửa tạo một snapshot hoặc revision. Kết quả phân tích cần gắn với revision tương ứng để tránh trộn AST, symbol table và diagnostic từ các trạng thái source khác nhau.

### 1.4. Tính đúng đắn

Một triển khai incremental đúng phải cho kết quả tương đương full analysis đối với cùng input snapshot, cùng cấu hình và cùng toolchain semantics. Sự khác biệt có thể chỉ nằm ở thời gian thực hiện hoặc metadata không ảnh hưởng ngữ nghĩa.

### 1.5. Incremental không có nghĩa là bỏ qua kiểm tra

Nếu một thay đổi có thể ảnh hưởng đến kết quả, phần liên quan phải được tính lại. Tối ưu chỉ hợp lệ khi engine có đủ bằng chứng rằng kết quả cũ vẫn đúng.

## 2. Vì sao DSL cần incremental analysis?

DSL thường được sử dụng trong IDE, build system, configuration editor, rule engine và công cụ mô hình hóa. Người dùng thay đổi source liên tục, nên phân tích toàn bộ project sau mỗi thao tác có thể tạo độ trễ lớn.

### 2.1. Phản hồi nhanh trong editor

Khi người dùng gõ một ký tự, IDE có thể cập nhật syntax highlight, completion và diagnostic cho vùng liên quan mà không chờ toàn bộ project được phân tích lại.

### 2.2. Giảm thời gian build

Nếu chỉ một module hoặc một file thay đổi, build tool có thể tránh compile hoặc validate những phần không bị ảnh hưởng.

### 2.3. Tiết kiệm tài nguyên

Project lớn có thể chứa nhiều module, schema, rule và dependency. Tái sử dụng kết quả hợp lệ giúp giảm CPU, memory, I/O và network.

### 2.4. Hỗ trợ tương tác liên tục

Các công cụ DSL có thể cần phân tích sau mỗi lần sửa, khi người dùng đổi profile, chọn target hoặc thay đổi một tham số. Incremental analysis giữ trải nghiệm tương tác ổn định.

### 2.5. Phân tích project nhiều module

Một thay đổi trong module độc lập không nên bắt buộc phân tích lại toàn bộ workspace. Dependency graph cho phép giới hạn phạm vi tính toán.

### 2.6. Tăng khả năng mở rộng

Khi project tăng từ vài file lên hàng nghìn file, full analysis có thể trở nên quá chậm. Incremental architecture giúp chi phí mỗi thay đổi gần với kích thước vùng bị ảnh hưởng thay vì toàn bộ project.

## 3. Phân biệt incremental analysis với các kỹ thuật liên quan

Các khái niệm này thường đi cùng nhau nhưng giải quyết những vấn đề khác nhau.

| Kỹ thuật | Mục tiêu |
|---|---|
| Incremental parsing | Cập nhật cấu trúc cú pháp sau khi source thay đổi |
| Incremental semantic analysis | Cập nhật symbol, type và semantic result bị ảnh hưởng |
| Incremental compilation | Chỉ compile phần cần thiết |
| Incremental build | Chỉ chạy lại task có input hoặc prerequisite thay đổi |
| Caching | Tái sử dụng kết quả đã tính |
| Memoization | Ghi nhớ kết quả của phép tính theo input key |
| Live analysis | Cập nhật kết quả khi người dùng đang chỉnh sửa |
| Change detection | Xác định input nào đã thay đổi |

### 3.1. Incremental parsing

Incremental parsing tập trung vào việc cập nhật parse tree hoặc AST khi một đoạn source được sửa. Nó không tự giải quyết dependency giữa các module hoặc type checking.

### 3.2. Incremental semantic analysis

Semantic analysis xác định ý nghĩa của AST, chẳng hạn phân giải tên, kiểm tra kiểu và ràng buộc miền. Incremental semantic analysis tính lại những kết quả phụ thuộc vào phần AST hoặc symbol đã thay đổi.

### 3.3. Incremental compilation

Incremental compilation quyết định phần source nào cần biên dịch lại. Nó có thể dùng kết quả của incremental parsing và semantic analysis nhưng còn phải xét compiler options, dependency ABI và generated output.

### 3.4. Incremental build

Incremental build hoạt động ở mức task graph. Nó xác định task nào cần chạy lại dựa trên input, output, dependency và cache state. Một task có thể gọi compiler incremental hoặc compiler full.

### 3.5. Caching

Caching lưu kết quả để tái sử dụng. Nếu cache key thiếu input hoặc dependency quan trọng, cache có thể trả kết quả cũ không hợp lệ. Incremental analysis cần một chiến lược invalidation chính xác.

### 3.6. Live analysis

Live analysis là trải nghiệm cập nhật gần thời gian thực. Nó thường dùng incremental analysis nhưng còn phải quản lý debounce, cancellation, stale result và ưu tiên tác vụ tương tác.

## 4. Mô hình dữ liệu cho incremental analysis

Để biết phần nào cần tính lại, engine cần biểu diễn input, kết quả và quan hệ phụ thuộc.

### 4.1. Input node

Input node có thể là file DSL, schema, cấu hình, dependency descriptor, plugin metadata hoặc một giá trị môi trường đã được đưa vào snapshot.

### 4.2. Analysis node

Analysis node đại diện cho một phép tính như parse file, tạo symbol table, resolve import, infer type hoặc validate rule set.

### 4.3. Output node

Output node có thể là AST, symbol index, type result, diagnostic, intermediate representation hoặc generated artifact.

### 4.4. Dependency edge

Edge mô tả output của node này phụ thuộc vào input hoặc output của node khác. Khi một node thay đổi, engine đi theo dependency graph để tìm các kết quả có thể bị ảnh hưởng.

### 4.5. Revision

Revision nhận diện một snapshot source hoặc workspace. Nó có thể là document version trong editor, commit ID, build invocation ID hoặc một revision nội bộ.

### 4.6. Fingerprint

Fingerprint là dấu nhận diện được tính từ input liên quan. Nó có thể là content hash, normalized syntax, configuration hash hoặc tổ hợp nhiều thành phần.

### 4.7. Analysis record

Một analysis record có thể lưu node ID, input fingerprint, dependency fingerprints, tool version, output reference, diagnostic và trạng thái hoàn tất.

## 5. Pipeline của incremental analysis

Một pipeline điển hình gồm phát hiện thay đổi, xác định vùng ảnh hưởng, tính lại và cập nhật snapshot.

~~~mermaid
flowchart TD
    A[New source or configuration snapshot] --> B[Detect changes]
    B --> C[Find affected dependency nodes]
    C --> D[Invalidate stale results]
    D --> E[Recompute affected analysis]
    E --> F[Update semantic and diagnostic state]
    F --> G[Publish consistent snapshot]
    G --> H[Reuse valid results next time]
~~~

### 5.1. Nhận snapshot mới

Engine nhận source và configuration mới. Các file cần được đọc theo một revision nhất quán để tránh phân tích file A trước thay đổi và file B sau thay đổi trong cùng một kết quả.

### 5.2. Phát hiện thay đổi

So sánh revision, timestamp, file metadata hoặc content hash để xác định input thay đổi. Với editor, change event có thể chỉ rõ range được sửa.

### 5.3. Tìm vùng ảnh hưởng

Dựa trên dependency graph, engine xác định analysis node nào phụ thuộc trực tiếp hoặc gián tiếp vào input thay đổi.

### 5.4. Invalidate kết quả cũ

Kết quả không còn hợp lệ được đánh dấu stale. Không nên xóa cache ngay nếu còn cần giữ snapshot cũ cho request đang chạy hoặc rollback.

### 5.5. Tính lại

Scheduler tính lại node bị ảnh hưởng theo thứ tự dependency. Các node độc lập có thể chạy song song nếu không có xung đột tài nguyên hoặc state.

### 5.6. Hợp nhất kết quả

Kết quả mới được kết hợp với kết quả cũ còn hợp lệ. Việc hợp nhất phải tạo một snapshot nhất quán, không để consumer nhìn thấy trạng thái nửa cũ nửa mới.

### 5.7. Công bố snapshot

Khi phân tích hoàn tất theo policy, engine công bố revision mới cho IDE, build tool hoặc caller. Kết quả cần mang revision để consumer nhận biết tính mới.

## 6. Phát hiện thay đổi đầu vào

Change detection là bước đầu tiên. Nếu phát hiện sai, mọi bước incremental phía sau đều có thể sai.

### 6.1. Timestamp

Timestamp file có chi phí thấp nhưng không đủ tin cậy làm bằng chứng duy nhất. Một số công cụ có thể giữ timestamp, filesystem có độ phân giải thời gian khác nhau và nội dung có thể thay đổi mà timestamp không phản ánh đúng như kỳ vọng.

### 6.2. File size

Kích thước giúp nhận biết một số thay đổi nhưng hai nội dung khác nhau có thể có cùng kích thước. Không dùng size làm fingerprint duy nhất.

### 6.3. Content hash

Hash nội dung cho biết file có thay đổi hay không với xác suất va chạm rất thấp tùy thuật toán. Hash cần được tính trên bytes hoặc normalized representation được quy định rõ.

### 6.4. Version counter

Editor hoặc document store có thể cung cấp version tăng dần mỗi lần sửa. Version hữu ích cho stale-result detection nhưng cần được gắn với document identity.

### 6.5. Version control revision

Build trong CI có thể dùng commit ID hoặc diff giữa hai revision. Cần xét generated files, submodule và uncommitted changes nếu build từ working tree.

### 6.6. File watcher

File watcher giúp phát hiện thay đổi nhanh nhưng có thể gộp event, bỏ sót event khi buffer đầy hoặc báo nhiều event cho cùng một thao tác. Nên có cơ chế rescan hoặc đối chiếu fingerprint.

### 6.7. Rename và delete

Rename có thể tương đương xóa file cũ và thêm file mới, nhưng IDE có thể giữ document identity. Delete cần invalidate mọi dependency vào file, symbol và resource do file cung cấp.

### 6.8. Configuration changes

Thay đổi compiler option, DSL version, target platform, profile hoặc plugin có thể làm nhiều kết quả stale dù source file không đổi. Các yếu tố này phải là input của fingerprint.

## 7. Dependency tracking

Dependency tracking ghi lại quan hệ giữa input và kết quả phân tích. Đây là nền tảng để biết thay đổi nào cần tính lại.

### 7.1. Explicit dependency

Dependency được khai báo trực tiếp, ví dụ module A import module B hoặc task compile phụ thuộc generated source.

### 7.2. Implicit dependency

Một phép tính có thể đọc dữ liệu mà source không thể hiện trực tiếp. Ví dụ macro đọc file schema, compiler plugin đọc configuration hoặc generator lấy environment. Những input này cũng cần được ghi nhận.

### 7.3. Fine-grained dependency

Theo dõi ở mức file, declaration, symbol hoặc expression giúp giảm phạm vi invalidation. Tuy nhiên, granularity càng nhỏ thì metadata và quản lý dependency càng phức tạp.

### 7.4. Coarse-grained dependency

Theo dõi theo module hoặc project đơn giản hơn nhưng có thể tính lại nhiều phần không cần thiết. Đây là lựa chọn hợp lý ở giai đoạn đầu hoặc khi chi phí phân tích graph chi tiết quá cao.

### 7.5. Dependency theo symbol

Một file có thể khai báo nhiều symbol. Nếu consumer chỉ dùng một symbol, thay đổi ở declaration không liên quan có thể không cần làm consumer phân tích lại, miễn interface mà consumer dùng không đổi.

### 7.6. Negative dependency

Kết quả có thể phụ thuộc vào việc một symbol hoặc file không tồn tại. Nếu một file mới xuất hiện làm tên trước đây unresolved trở nên hợp lệ, những kết quả đã dựa vào sự vắng mặt đó phải được cập nhật.

### 7.7. Dynamic dependency

Plugin hoặc macro có thể xác định dependency trong lúc chạy. Engine cần ghi nhận những input thực tế đã được đọc hoặc buộc plugin khai báo dependency đầy đủ.

### 7.8. Dependency invalidation

Khi một input đổi, engine duyệt reverse dependency graph để tìm các consumer cần tính lại. Cần tránh bỏ sót cạnh và tránh invalidation không cần thiết.

## 8. Dependency graph và vùng ảnh hưởng

Một graph phân tích có thể mô hình hóa chuỗi quan hệ từ source đến kết quả.

~~~mermaid
flowchart TD
    A[common.dsl] --> C[Symbol table]
    B[orders.dsl] --> D[Orders AST]
    C --> D
    D --> E[Orders type analysis]
    E --> F[API validation]
    G[api.dsl] --> F
    H[logging.dsl] --> I[Logging analysis]
~~~

Nếu common.dsl thay đổi, orders AST hoặc semantic result có thể cần cập nhật tùy cách import. logging.dsl nằm ở nhánh độc lập nên có thể giữ kết quả cũ.

### 8.1. Forward dependency

Forward dependency mô tả node cần những node nào. Nó giúp tính toán prerequisite và thứ tự phân tích.

### 8.2. Reverse dependency

Reverse dependency cho biết node nào đang dùng kết quả của node hiện tại. Nó hỗ trợ impact analysis và invalidation.

### 8.3. Transitive impact

Thay đổi ở node A có thể ảnh hưởng B, rồi B ảnh hưởng C. Engine cần duyệt toàn bộ đường phụ thuộc liên quan, không chỉ direct consumers.

### 8.4. Impact boundary

Một thay đổi có thể làm AST đổi nhưng public interface không đổi. Nếu consumer chỉ phụ thuộc public interface, engine có thể dừng invalidation ở ranh giới đó.

### 8.5. Dependency summary

Lưu summary của dependency như public symbol set hoặc ABI fingerprint giúp xác định consumer có thật sự cần phân tích lại hay không.

### 8.6. Graph snapshot

Graph cần gắn với revision và configuration snapshot. Không trộn cạnh được tạo từ hai revision khác nhau nếu điều đó làm kết quả không nhất quán.

## 9. Incremental lexing và parsing

Parser có thể cập nhật một phần cây cú pháp khi người dùng chỉnh sửa một đoạn source.

### 9.1. Lexical state

Lexer có thể lưu trạng thái tại các điểm đồng bộ như đầu dòng hoặc đầu block. Khi một vùng thay đổi, lexer bắt đầu từ checkpoint gần nhất trước vùng đó và tiếp tục đến khi trạng thái token ổn định.

### 9.2. Token range

Editor thường cung cấp range thay đổi. Lexer có thể chỉ tokenize lại vùng đó và một vùng lân cận cần thiết để xử lý token bị nối hoặc tách.

### 9.3. Parser checkpoint

Parser có thể lưu trạng thái tại các boundary an toàn như declaration hoặc statement. Sau chỉnh sửa, parser phục hồi từ checkpoint trước vùng thay đổi.

### 9.4. Reparse region

Chỉ subtree có thể bị ảnh hưởng được parse lại. Nếu thay đổi làm mất dấu ngoặc hoặc delimiter bao quanh, vùng reparse có thể mở rộng đến parent block hoặc toàn file.

### 9.5. Stable node identity

Node identity ổn định giúp giữ diagnostic, symbol reference và editor selection qua các lần parse. Không nên dùng source offset đơn lẻ làm ID vì offset thay đổi khi chèn text phía trước.

### 9.6. Error recovery

Trong lúc người dùng gõ, source có thể tạm thời không hợp lệ. Parser IDE có thể tạo error node và giữ phần cây còn đọc được, nhưng execution/compiler release path phải yêu cầu parse hợp lệ.

### 9.7. Parser complexity

Incremental parser cần tránh trường hợp một chỉnh sửa nhỏ khiến parse lại gần như toàn bộ file thường xuyên. Tuy nhiên, khi cấu trúc bao ngoài thay đổi, reparse lớn có thể là cần thiết để bảo đảm đúng.

### 9.8. Grammar changes

Nếu DSL grammar hoặc parser version thay đổi, các checkpoint và AST cache cũ có thể không còn hợp lệ. Grammar version phải là một phần cache key.

## 10. AST diff và node identity

AST diff so sánh cây cú pháp trước và sau thay đổi để nhận diện node được thêm, xóa hoặc sửa.

### 10.1. Structural comparison

Có thể so sánh loại node, tên, child structure và normalized content. So sánh cấu trúc giúp tránh coi mọi offset change là thay đổi semantics.

### 10.2. Source position

Source span hỗ trợ liên kết node với text editor và diagnostic. Position có thể thay đổi mà node semantics vẫn giữ nguyên.

### 10.3. Stable identity strategy

Có thể dùng declaration name kết hợp parent scope, persistent node ID hoặc matching heuristic. Không có một chiến lược duy nhất phù hợp mọi grammar.

### 10.4. Insert và delete

Khi declaration được thêm hoặc xóa, symbol table và mọi reference có thể bị ảnh hưởng. Engine cần invalidate các lookup phụ thuộc vào scope đó.

### 10.5. Rename

Rename symbol thường cần cập nhật declaration, references, import và diagnostic. Rename refactoring có thể dùng symbol identity thay vì chỉ tìm chuỗi trùng tên.

### 10.6. Semantic equivalence

Hai đoạn source có thể khác text nhưng tương đương về semantics, chẳng hạn thay đổi whitespace hoặc comment. Normalized AST hoặc semantic fingerprint có thể tránh invalidation không cần thiết.

### 10.7. Matching ambiguity

Khi nhiều node giống nhau, matching heuristic có thể gán nhầm identity. Nếu không chắc chắn, engine nên tạo node mới hoặc mở rộng phạm vi phân tích thay vì tái sử dụng kết quả sai.

## 11. Incremental symbol resolution

Symbol resolution tìm declaration tương ứng với identifier trong scope hiện tại. Kết quả có thể được tái sử dụng nếu các scope và declaration liên quan không đổi.

### 11.1. Symbol table

Symbol table lưu tên, loại, scope, declaration location, visibility và metadata. Có thể tổ chức theo module hoặc namespace.

### 11.2. Import dependency

Nếu file A import module B, thay đổi export của B có thể ảnh hưởng A. Nếu chỉ phần implementation nội bộ của B đổi, A có thể không cần resolve lại.

### 11.3. Scope invalidation

Thêm declaration vào scope có thể làm thay đổi kết quả lookup trước đó, kể cả những lookup từng unresolved. Vì vậy, dependency tracking cần ghi nhận scope được truy vấn, không chỉ symbol được tìm thấy.

### 11.4. Public interface fingerprint

Tạo fingerprint từ public declarations, exported types và signature. Consumer chỉ cần phân tích lại khi fingerprint của interface mà nó sử dụng thay đổi.

### 11.5. Namespace changes

Đổi namespace hoặc package path có thể ảnh hưởng nhiều import và generated reference. Engine cần theo dõi cả mapping namespace-to-module.

### 11.6. Ambiguous reference

Nếu thêm một declaration khiến reference trước đây duy nhất trở nên ambiguous, các consumer phụ thuộc vào scope cần được phân tích lại.

### 11.7. Unresolved reference

Khi một module mới xuất hiện hoặc import path thay đổi, unresolved reference có thể trở thành resolved. Negative dependency giúp phát hiện thay đổi này.

## 12. Incremental type checking

Type checking xác định các biểu thức và declaration có kiểu tương thích. Kết quả type có thể phụ thuộc vào declaration và type environment ở nhiều module.

### 12.1. Type environment

Type environment ánh xạ symbol sang type, constraint và generic parameter. Nó là input của phép kiểm tra biểu thức.

### 12.2. Local type result

Một expression có thể được type check độc lập nếu các type của operand không đổi. Engine có thể giữ lại result khi AST node và type environment fingerprint còn hợp lệ.

### 12.3. Type dependency

Nếu function signature đổi, caller có thể cần type check lại. Nếu chỉ body function đổi và signature không đổi, caller có thể không cần cập nhật type result.

### 12.4. Generic inference

Generic inference có thể phụ thuộc nhiều call site hoặc constraint. Khi một constraint thay đổi, vùng invalidation có thể lớn hơn expression đang sửa.

### 12.5. Overload resolution

Thêm overload mới có thể làm call expression trước đó chọn function khác hoặc trở nên ambiguous. Lookup set của overload group phải được theo dõi.

### 12.6. Type alias và schema changes

Đổi type alias hoặc field type trong schema có thể ảnh hưởng mọi consumer tham chiếu. Public type fingerprint giúp xác định phạm vi này.

### 12.7. Constraint propagation

Một thay đổi có thể làm constraint truyền qua nhiều biểu thức. Engine có thể dùng worklist để tiếp tục tính cho đến khi không còn kết quả thay đổi.

### 12.8. Error recovery

Trong editor, một type chưa xác định có thể được biểu diễn bằng error/unknown type để tiếp tục phân tích các phần khác. Không nên xem unknown type là bằng chứng chương trình hợp lệ.

## 13. Incremental semantic analysis cho DSL có domain model

Nhiều DSL không chỉ có type checking mà còn có các quy tắc miền như workflow, policy, schema mapping hoặc deployment model.

### 13.1. Domain model node

Một declaration có thể tạo node trong model, ví dụ service, endpoint, rule, resource hoặc event. Semantic analyzer xây quan hệ giữa các node.

### 13.2. Rule dependency

Một rule có thể tham chiếu field, constant hoặc rule khác. Khi một dependency đổi, chỉ rule và consumer liên quan cần được đánh giá lại.

### 13.3. Cross-reference

Các reference giữa file hoặc module cần index để tìm consumer nhanh. Khi declaration đổi, engine truy vấn reverse index để xác định affected set.

### 13.4. Constraint validation

Ràng buộc như unique name, allowed transition hoặc resource compatibility có thể phụ thuộc vào toàn bộ tập declaration trong một scope. Thay đổi một phần tử có thể làm validation của các phần tử khác đổi.

### 13.5. Global invariant

Một số invariant chỉ có thể kiểm tra trên toàn model, chẳng hạn không có hai resource dùng cùng external identifier. Engine có thể dùng index và summary để kiểm tra lại invariant liên quan thay vì duyệt toàn bộ nếu có thể chứng minh phạm vi.

### 13.6. Dependency summary

Mỗi module có thể công bố summary như exported service, event type, endpoint hoặc resource. Consumer dựa vào summary thay vì parse lại toàn bộ source của producer.

### 13.7. Dynamic model

Nếu plugin hoặc macro tạo declaration động, cần ghi lại nguồn và dependency của declaration được sinh. Thay đổi plugin hoặc input generator có thể invalidate toàn bộ phần generated model liên quan.

## 14. Invalidation và recomputation

Invalidation xác định kết quả nào không còn đáng tin. Recomputation tính lại những kết quả đó.

### 14.1. Direct invalidation

Khi input node thay đổi, các analysis node đọc trực tiếp input đó bị invalidate.

### 14.2. Transitive invalidation

Nếu output của analysis node A đổi, mọi consumer phụ thuộc vào output đó có thể cần invalidate tiếp. Quá trình tiếp tục đến khi đạt các boundary không bị ảnh hưởng.

### 14.3. Change propagation

Không phải mọi node downstream đều phải invalidate khi upstream source thay đổi. Nếu public summary không đổi, consumer phụ thuộc summary có thể tiếp tục dùng kết quả cũ.

### 14.4. Worklist algorithm

Engine có thể dùng hàng đợi các node cần xử lý. Khi output của một node đổi, thêm consumer của output đó vào worklist. Kết thúc khi worklist rỗng và trạng thái đạt ổn định.

### 14.5. Equality of results

Cần định nghĩa equality cho output. Với AST, có thể so structural fingerprint; với type result, so type identity và constraints; với generated artifact, so content hash.

### 14.6. Avoid unnecessary propagation

Nếu output mới tương đương output cũ, không cần tiếp tục invalidation downstream nếu consumer chỉ phụ thuộc giá trị đó. Đây là một tối ưu quan trọng.

### 14.7. Conservative invalidation

Khi không thể chứng minh output không đổi, invalidate rộng hơn là lựa chọn an toàn. Hệ thống có thể chậm hơn nhưng không trả kết quả stale.

### 14.8. Recompute ordering

Recompute theo dependency order để consumer chỉ dùng output đã cập nhật. Node độc lập có thể chạy song song.

## 15. Fixed-point analysis và dataflow

Một số phân tích không thể cập nhật bằng một lượt topo đơn giản vì các giá trị được truyền qua nhiều node hoặc có quan hệ lặp.

### 15.1. Dataflow analysis

Dataflow analysis truyền thông tin qua graph, ví dụ variable liveness, reachability, permission propagation hoặc abstract state. Mỗi node nhận input từ predecessor và tạo output cho successor.

### 15.2. Fixed point

Fixed point là trạng thái mà việc áp dụng tiếp transfer function không làm thay đổi kết quả. Engine lặp đến khi mọi node ổn định hoặc đạt giới hạn.

### 15.3. Monotonicity

Một số thuật toán hội tụ dễ dự đoán nếu transfer function đơn điệu trên lattice phù hợp. Semantics của analysis cần được xác định để bảo đảm hội tụ.

### 15.4. Worklist update

Khi input của một node thay đổi, đưa node đó vào worklist. Nếu output mới khác output cũ, đưa successor vào để tính lại.

### 15.5. Strongly connected regions

Cycle trong dataflow graph có thể được xử lý bằng fixed-point iteration nếu thuật toán hỗ trợ. Điều này khác với task build prerequisite, nơi cycle thường là lỗi.

### 15.6. Widening và convergence limit

Với domain vô hạn hoặc chuỗi giá trị tăng không dừng, có thể cần widening hoặc giới hạn iteration. Khi không hội tụ trong budget, báo analysis incomplete thay vì công bố kết quả cuối giả định.

## 16. Fingerprint, cache key và tính hợp lệ của cache

Cache giúp tái sử dụng kết quả nhưng chỉ an toàn khi key phản ánh đủ input ảnh hưởng.

### 16.1. Content fingerprint

Hash source bytes hoặc normalized content. Nếu chỉ dùng timestamp, thay đổi nội dung có thể không được phát hiện trong một số trường hợp.

### 16.2. Dependency fingerprint

Kết quả có thể phụ thuộc vào output hoặc public interface của dependency. Fingerprint của dependency cần được đưa vào cache key.

### 16.3. Toolchain fingerprint

Parser version, compiler version, plugin version và rule engine version có thể thay đổi semantics. Chúng phải là một phần của cache key.

### 16.4. Configuration fingerprint

Profile, target platform, feature flags, compiler options và schema version cũng ảnh hưởng kết quả. Không được bỏ qua chúng chỉ vì source không đổi.

### 16.5. Environment inputs

Nếu analysis đọc environment variable hoặc file ngoài, input đó phải được khai báo hoặc được chụp thành snapshot. Tránh phụ thuộc ngầm vào environment của máy chạy.

### 16.6. Cache namespace

Cache key cần phân biệt project, tenant, toolchain và trust domain. Không dùng cache của workspace khác nếu chưa xác minh quyền và input identity.

### 16.7. Cache corruption

Kiểm tra checksum hoặc content digest của cache artifact. Nếu cache hỏng, loại bỏ và tính lại từ input đáng tin cậy.

### 16.8. Cache eviction

Cache có thể được giới hạn theo dung lượng, tuổi hoặc tần suất sử dụng. Eviction ảnh hưởng hiệu năng nhưng không được ảnh hưởng tính đúng đắn.

### 16.9. Cache hit và miss

Metrics nên phân biệt cache hit, miss, invalidation và recomputation. Tỷ lệ hit cao không có ý nghĩa nếu kết quả sai; cần correctness checks phù hợp.

## 17. Incremental build và task execution

Build engine dùng dependency graph để xác định task cần chạy lại.

### 17.1. Task input/output

Task khai báo input và output để engine biết điều gì quyết định kết quả. Input cần bao gồm file, configuration, tool version và dependency cần thiết.

### 17.2. Task fingerprint

Fingerprint của task có thể kết hợp input hashes, dependency output hashes và task implementation version.

### 17.3. Up-to-date check

Nếu fingerprint không đổi và output tồn tại, task có thể được đánh dấu up-to-date. Kiểm tra này chỉ hợp lệ khi input/output declaration đầy đủ.

### 17.4. Generated source

Nếu DSL compiler sinh source, thay đổi ở một module có thể chỉ yêu cầu generate lại file liên quan. Các task compile phía sau chỉ cần chạy lại khi generated output thay đổi.

### 17.5. ABI-based invalidation

Thay đổi implementation không làm thay public ABI có thể không cần recompile consumer. Cách này đòi hỏi compiler tạo ABI fingerprint chính xác và xét các thuộc tính ảnh hưởng binary compatibility.

### 17.6. Test selection

Một số build system có thể chọn test dựa trên source hoặc dependency bị thay đổi. Cần bảo đảm mapping từ code đến test đủ tin cậy; nếu không, chạy full test suite vẫn là lựa chọn an toàn.

### 17.7. Remote cache

CI runner có thể tải output từ remote cache khi task fingerprint khớp. Cache phải được xác minh integrity và phân tách theo trust domain.

### 17.8. Non-hermetic task

Task đọc file tùy ý, clock hoặc network mà không khai báo input sẽ làm incremental build không đáng tin. Cần làm task hermetic hoặc vô hiệu hóa cache/incremental cho task đó.

## 18. Incremental analysis trong IDE và language server

IDE thường cần kết quả nhanh hơn compiler release vì người dùng liên tục sửa source.

### 18.1. Document version

Mỗi document có version tăng dần. Analysis request và result phải gắn version để client bỏ qua kết quả cũ đến muộn.

### 18.2. Debounce

Khi người dùng gõ liên tục, có thể đợi một khoảng ngắn trước khi chạy phân tích tốn kém. Debounce cần cân bằng độ trễ và mức sử dụng CPU.

### 18.3. Cancellation

Nếu document thay đổi trong lúc phân tích, hủy request cũ khi có thể. Cancellation không bảo đảm task dừng tức thời, nên result vẫn phải được kiểm tra revision trước khi publish.

### 18.4. Priority

Syntax diagnostics và completion thường cần phản hồi nhanh; whole-workspace validation có thể chạy nền. Scheduler nên ưu tiên tác vụ tương tác.

### 18.5. Partial result

IDE có thể hiển thị syntax tree hoặc diagnostics một phần trong lúc semantic analysis đang chạy. UI cần thể hiện trạng thái incomplete nếu kết quả chưa đầy đủ.

### 18.6. Workspace index

Symbol index dùng chung giúp completion và go-to-definition tìm kiếm nhanh. Index cần cập nhật incremental khi file, module hoặc import thay đổi.

### 18.7. Open document và disk state

Nội dung trong editor có thể khác file trên disk. Engine cần ưu tiên document snapshot mới nhất cho phân tích tương tác và tránh ghi đè thay đổi chưa lưu.

### 18.8. Workspace reload

Khi đổi branch, đổi project configuration hoặc thêm/xóa module, một phần lớn index có thể stale. Language server cần phát hiện và tái tạo phần phù hợp.

## 19. Diagnostic incremental

Diagnostics gồm lỗi, cảnh báo và thông tin được tạo từ source hoặc model.

### 19.1. Gắn diagnostic với revision

Mỗi diagnostic cần mang document/workspace revision. IDE không nên hiển thị lỗi từ revision cũ như thể nó thuộc source hiện tại.

### 19.2. Replace theo document

Khi phân tích lại file, có thể thay toàn bộ diagnostics của file đó bằng tập mới. Nếu diagnostics cross-file, cần xác định owner và cách cập nhật khi dependency đổi.

### 19.3. Diagnostic identity

ID ổn định có thể giúp UI giữ trạng thái hoặc tránh nhấp nháy. Identity nên dựa vào rule, source span và semantic context phù hợp, không chỉ message text.

### 19.4. Stale diagnostics

Nếu một file chưa được phân tích lại nhưng dependency của nó đã đổi, diagnostic liên quan có thể stale. Dependency graph cần cho biết file nào cần refresh.

### 19.5. Diagnostic suppression

Suppression hoặc baseline có thể phụ thuộc source location và rule ID. Khi node di chuyển hoặc rule version thay đổi, suppression cần được xác minh lại.

### 19.6. Partial diagnostics

Nếu engine hủy phân tích giữa chừng, không được xóa toàn bộ diagnostics cũ rồi chỉ công bố một phần mới mà không đánh dấu trạng thái incomplete.

## 20. Concurrency và snapshot consistency

Incremental analysis thường chạy đồng thời nhiều request. Cần quản lý revision và cache để tránh kết quả trộn lẫn.

### 20.1. Immutable snapshot

Phân tích một snapshot bất biến giúp mỗi task nhìn thấy cùng một phiên bản source và configuration.

### 20.2. Versioned cache entries

Cache entry cần gắn fingerprint hoặc revision. Không ghi đè entry mới bằng kết quả của request cũ chạy chậm hơn.

### 20.3. Stale result rejection

Trước khi publish result, so sánh revision với revision hiện hành. Nếu result cũ, bỏ qua hoặc giữ riêng cho consumer đang cần snapshot đó.

### 20.4. Cancellation token

Truyền cancellation token qua parser, semantic analyzer và task graph. Các bước tốn kém nên kiểm tra token tại điểm an toàn.

### 20.5. Atomic publish

Công bố một analysis snapshot sau khi các thành phần cần thiết đã hoàn tất. Consumer không nên đọc symbol table revision mới cùng type result revision cũ.

### 20.6. Locking

Lock có thể bảo vệ shared index hoặc cache mutation, nhưng lock rộng làm giảm concurrency. Ưu tiên immutable data, versioning và atomic swap khi phù hợp.

### 20.7. Parallel recomputation

Các node độc lập có thể tính song song. Scheduler cần tôn trọng dependency và tránh hai task cùng sửa một mutable structure.

### 20.8. Memory lifecycle

Giữ nhiều revision có thể tiêu tốn memory. Có thể reference-count snapshot, giới hạn số revision và giải phóng kết quả không còn consumer sử dụng.

## 21. Tính đúng đắn và giới hạn của incremental analysis

Tối ưu incremental cần ưu tiên correctness. Một kết quả nhanh nhưng stale có thể gây lỗi build, sai diagnostic hoặc deployment sai.

### 21.1. Sound invalidation

Khi một thay đổi có thể ảnh hưởng output, engine phải invalidate node đó. Bỏ sót dependency tạo false cache hit.

### 21.2. Precision

Precision đo mức độ tránh tính lại phần không bị ảnh hưởng. Invalidation quá rộng vẫn đúng nhưng giảm hiệu năng.

### 21.3. Full analysis as oracle

Có thể dùng full analysis làm oracle trong test để so sánh với incremental result. Đây là cách phát hiện lỗi dependency tracking và cache invalidation.

### 21.4. Conservative fallback

Nếu engine không hiểu dependency động hoặc metadata không đầy đủ, chuyển sang phân tích lại module hoặc project lớn hơn. Không đoán rằng phần đó không bị ảnh hưởng.

### 21.5. Unknown dependency

Plugin có thể truy cập input ngoài graph. Nếu không thể theo dõi, đánh dấu task non-incremental hoặc yêu cầu plugin khai báo input/output.
 
### 21.6. Nondeterministic analysis

Phân tích phụ thuộc thời gian, randomness hoặc external service cần snapshot các giá trị đó hoặc không cache kết quả. Nếu không, cùng fingerprint có thể tạo output khác.

### 21.7. Semantic versioning của analyzer

Khi thuật toán phân tích thay đổi, kết quả cũ có thể không còn tương thích. Analyzer version cần được đưa vào cache key và snapshot metadata.

### 21.8. Fail-safe behavior

Nếu cache corrupt, graph thiếu cạnh hoặc snapshot không nhất quán, engine nên bỏ cache và phân tích lại theo đường an toàn.

## 22. Chiến lược fallback và full rebuild

Incremental analysis không phải lúc nào cũng có lợi. Có những trường hợp full analysis đơn giản và nhanh hơn.

### 22.1. Thay đổi toàn cục

Đổi DSL language version, compiler semantics, global configuration hoặc plugin có thể làm gần như mọi node stale.

### 22.2. Dependency graph không đầy đủ

Nếu một plugin không khai báo input hoặc dependency, engine không thể chứng minh phần nào còn hợp lệ. Full analysis hoặc invalidate module chứa plugin là lựa chọn an toàn.

### 22.3. Thay đổi quá lớn

Nếu số node bị ảnh hưởng gần bằng toàn graph, chi phí tính affected set và hợp nhất cache có thể lớn hơn full analysis.

### 22.4. Cache schema thay đổi

Khi cache format hoặc analyzer version không tương thích, xóa cache liên quan và tạo lại.

### 22.5. Recovery sau lỗi

Sau crash hoặc process interruption, snapshot có thể ở trạng thái không hoàn chỉnh. Engine cần kiểm tra commit marker hoặc trạng thái transaction trước khi reuse.

### 22.6. User-requested clean build

Người dùng có thể yêu cầu clean build để xác minh kết quả không phụ thuộc cache. Clean mode nên bỏ qua hoặc xóa cache theo phạm vi được chọn.

### 22.7. Threshold policy

Engine có thể đặt threshold: nếu affected set vượt một tỷ lệ hoặc chi phí ước tính, chọn full analysis. Threshold cần dựa trên metrics thực tế và không làm thay đổi kết quả.

## 23. Hiệu năng và đo lường

Cần đo cả thời gian tính lại lẫn chi phí duy trì graph và cache.

### 23.1. Analysis latency

Đo thời gian từ khi nhận thay đổi đến khi kết quả có thể sử dụng. Với IDE, p50/p95 latency thường hữu ích hơn một con số trung bình.

### 23.2. Recomputed node count

Đếm số node được tính lại so với tổng số node. Tỷ lệ thấp cho thấy invalidation có độ chính xác tốt, nhưng cần đối chiếu correctness.

### 23.3. Cache hit rate

Theo dõi cache hit, miss, stale rejection và eviction. Cache hit cao nhưng phải kiểm tra fingerprint có đầy đủ hay không.

### 23.4. Dependency graph cost

Đo thời gian xây graph, cập nhật reverse index và tìm affected set. Với graph lớn, chi phí quản lý metadata có thể trở thành nút thắt.

### 23.5. Memory usage

Theo dõi AST, symbol index, semantic result và các revision đang được giữ. Tái sử dụng quá nhiều snapshot có thể làm tăng memory đáng kể.

### 23.6. Cancellation waste

Đo công việc bị hủy do người dùng sửa tiếp trước khi analysis hoàn tất. Debounce và priority có thể giảm phần tính toán bị bỏ phí.

### 23.7. Critical path

Trong build graph, đo task trên critical path và thời gian chờ dependency. Tối ưu một task không nằm trên critical path có thể không giảm tổng build time.

### 23.8. Benchmark workload

Dùng project nhỏ, project lớn, thay đổi một dòng, đổi interface, thêm file, đổi cấu hình toàn cục và thay dependency. Benchmark phải phản ánh cách người dùng thực sự sửa project.

## 24. Kiểm thử incremental analysis

Kiểm thử cần chứng minh incremental result đúng và phạm vi recomputation hợp lý.

### 24.1. Compare with full analysis

Với mỗi fixture, chạy full analysis trên revision mới và so sánh AST/semantic result/diagnostics với incremental analysis.

### 24.2. Single-file edit

Sửa một biểu thức cục bộ và xác minh chỉ node liên quan bị tính lại nếu dependency cho phép.

### 24.3. Public interface edit

Đổi public signature và xác minh consumer phụ thuộc được invalidate.

### 24.4. Implementation-only edit

Đổi implementation nhưng giữ interface không đổi; kiểm tra consumer không bị phân tích lại nếu semantics cho phép.

### 24.5. Add/remove/rename file

Kiểm tra symbol index, import, unresolved reference và negative dependency được cập nhật.

### 24.6. Configuration changes

Đổi compiler flag, DSL version, profile hoặc plugin và xác minh đúng phạm vi cache bị invalidate.

### 24.7. Dynamic dependency

Dùng fixture plugin đọc file hoặc resource động và kiểm tra engine theo dõi dependency hoặc chọn fallback an toàn.

### 24.8. Concurrent edits

Tạo hai revision liên tiếp, cho analysis revision cũ hoàn tất sau revision mới và xác minh result cũ không ghi đè snapshot mới.

### 24.9. Cancellation

Hủy task giữa parse hoặc semantic analysis và kiểm tra không publish partial result như kết quả hoàn chỉnh.

### 24.10. Cache corruption

Làm hỏng cache entry và xác minh engine loại bỏ entry rồi tính lại thay vì dùng dữ liệu không hợp lệ.

### 24.11. Property-based tests

Sinh các thay đổi source ngẫu nhiên trong giới hạn, so sánh incremental với full analysis để tìm trường hợp invalidation bị thiếu.

### 24.12. Performance regression tests

Theo dõi thời gian và node recomputation trên fixture ổn định. Không chỉ tối ưu một microbenchmark không đại diện workload.

## 25. Thiết kế API cho incremental analyzer

API cần làm rõ revision, change set, snapshot và cancellation.

### 25.1. Analysis request

Request có thể chứa workspace ID, document versions, source snapshot, configuration fingerprint và cancellation token.

### 25.2. Change set

Change set mô tả file thêm, sửa, xóa, rename hoặc configuration thay đổi. Nó có thể chứa text range khi làm việc với editor.

### 25.3. Result metadata

Result nên có revision, analyzer version, diagnostics, output references, affected node count và trạng thái complete/incomplete.

### 25.4. Snapshot API

Consumer có thể yêu cầu snapshot cụ thể hoặc snapshot mới nhất. Không nên trả một phần dữ liệu thuộc nhiều revision.

### 25.5. Cancellation API

Caller có thể hủy request cũ khi có revision mới. Engine cần xác nhận trạng thái cancellation và tránh publish kết quả cũ.

### 25.6. Full analysis mode

API có thể cung cấp chế độ full để clean build, debugging hoặc đối chiếu correctness.

### 25.7. Observability hooks

Có thể phát event về cache hit, invalidation, recomputation và analysis completion để IDE hoặc telemetry hiển thị trạng thái.

## 26. Ví dụ DSL khai báo incremental analysis

Một DSL build có thể khai báo các task với input/output và dependency để engine xác định phần cần tính lại.

~~~text
module common {
    source = "modules/common"
    analysis {
        granularity = declaration
        cache = enabled
    }
}

module billing {
    source = "modules/billing"
    depends-on common
    analysis {
        granularity = symbol
        invalidate-on = public-api-change
    }
}

task analyzeBilling {
    input = files("modules/billing/**/*.dsl")
    depends-on analyzeCommon
    output = file("build/analysis/billing.bin")
    incremental = true
}

task analyzeCommon {
    input = files("modules/common/**/*.dsl")
    output = file("build/analysis/common.bin")
    incremental = true
}
~~~

Cú pháp trên chỉ minh họa một khả năng. DSL thực tế cần định nghĩa chính xác granularity, public API fingerprint và quan hệ task để tránh khai báo không đầy đủ.

### 26.1. Source revision

Khi một file trong common thay đổi, engine tạo revision mới và tính fingerprint cho file đó.

### 26.2. Common analysis

Engine parse và phân tích declaration bị ảnh hưởng trong common. Nếu public interface fingerprint không đổi, billing có thể tiếp tục dùng semantic result trước đó.

### 26.3. Public API change

Nếu một public signature đổi, consumer phụ thuộc vào signature đó được đưa vào affected set. Billing được phân tích lại theo dependency graph.

### 26.4. Implementation-only change

Nếu chỉ body nội bộ đổi và public interface không đổi, module consumer không cần type check lại, nhưng artifact của common vẫn có thể cần build lại.

### 26.5. Full fallback

Nếu compiler version đổi hoặc plugin không cung cấp dependency metadata, engine invalidate phạm vi rộng hơn hoặc chạy full analysis.

## 27. Ví dụ: sửa một declaration trong project nhiều module

Giả sử project có ba module:

~~~text
module common {
    export type CustomerId = UUID
    export function normalizeId(value: String): CustomerId
}

module orders {
    depends-on common
    export function createOrder(id: CustomerId)
}

module reports {
    depends-on common
    export function customerSummary(id: CustomerId)
}
~~~

### 27.1. Thay đổi implementation

Người dùng sửa thân hàm normalizeId nhưng giữ nguyên signature. Analysis của common cần cập nhật implementation; orders và reports có thể giữ type result nếu chúng chỉ phụ thuộc public signature.

### 27.2. Thay đổi signature

Nếu normalizeId đổi từ String sang một kiểu input khác, consumer gọi hàm này cần được type check lại. Các module chỉ dùng CustomerId có thể không bị ảnh hưởng nếu alias và contract đó không đổi.

### 27.3. Thay đổi type alias

Nếu CustomerId đổi từ UUID sang String, cả orders và reports có thể bị ảnh hưởng vì type được dùng trong public API của chúng.

### 27.4. Thêm declaration

Nếu thêm một overload normalizeId, call expression có thể đổi kết quả overload resolution hoặc trở nên ambiguous. Các call site trong dependency scope cần được kiểm tra lại.

### 27.5. Xóa module

Nếu common bị xóa hoặc đổi module path, import của orders và reports trở thành unresolved. Negative dependency và module index cần cập nhật.

### 27.6. Phạm vi recomputation

Engine dùng dependency summary để phân biệt consumer phụ thuộc implementation, signature hoặc type. Điều này giảm recomputation nhưng vẫn bảo đảm kết quả phù hợp với source mới.

## 28. Những sai lầm thường gặp

### 28.1. Chỉ so sánh timestamp

Timestamp không đủ chứng minh nội dung không đổi. Dùng content fingerprint hoặc revision đáng tin cậy.

### 28.2. Không theo dõi dependency ngầm

Plugin, macro hoặc generator có thể đọc file ngoài khai báo. Nếu không ghi nhận input, cache có thể trả kết quả stale.

### 28.3. Invalidate quá ít

Bỏ sót consumer của symbol hoặc scope tạo kết quả cũ. Khi không chắc chắn, mở rộng phạm vi recomputation.

### 28.4. Invalidate quá nhiều

Mỗi thay đổi đều làm lại toàn project khiến incremental analysis không có lợi. Dùng dependency summary và granularity phù hợp.

### 28.5. Dùng source offset làm node ID

Chèn một dòng đầu file làm offset của mọi node phía sau thay đổi. Dùng stable identity hoặc matching dựa trên cấu trúc.

### 28.6. Không xử lý negative dependency

Một reference chưa resolve có thể trở nên hợp lệ khi file hoặc symbol mới xuất hiện. Cần theo dõi cả kết quả lookup thất bại.

### 28.7. Trộn revision

AST của revision mới kết hợp symbol table của revision cũ có thể tạo kết quả không nhất quán. Dùng immutable snapshot và revision tagging.

### 28.8. Publish stale result

Analysis cũ có thể hoàn tất sau analysis mới. Kiểm tra revision trước khi publish và bỏ kết quả lỗi thời.

### 28.9. Cache thiếu compiler options

Cùng source nhưng khác target, flag hoặc plugin có thể tạo semantics khác. Đưa toàn bộ configuration liên quan vào cache key.

### 28.10. Không kiểm thử với full analysis

Một incremental engine có thể nhanh nhưng sai ở trường hợp dependency hiếm. Dùng full analysis làm oracle trong test.

### 28.11. Cache task có side effect

Publish, deploy hoặc gọi API không thể được cache như một phép tính thuần nếu chưa có semantics idempotency rõ.

### 28.12. Giữ quá nhiều revision

Giữ AST, index và output của mọi revision có thể làm cạn memory. Cần lifecycle và eviction policy.

### 28.13. Không có fallback

Khi graph hoặc metadata không đáng tin, engine cần có đường full analysis hoặc invalidate rộng. Tiếp tục dùng cache không chắc chắn là rủi ro.

## 29. Nguyên tắc thiết kế incremental analysis cho DSL

Một incremental analyzer tốt cần cân bằng tính đúng đắn, độ chi tiết của dependency và chi phí duy trì trạng thái.

### 29.1. Xác định đơn vị phân tích

Chọn granularity phù hợp như file, module, declaration, symbol hoặc expression. Không cần dùng granularity cực nhỏ nếu overhead lớn hơn lợi ích.

### 29.2. Theo dõi mọi input có ảnh hưởng

Source, import, configuration, plugin, compiler option, dependency version và environment snapshot cần được đưa vào dependency model khi chúng ảnh hưởng output.

### 29.3. Dùng fingerprint đầy đủ

Cache key phải phản ánh content, dependency result và toolchain semantics. Thiếu input có thể gây stale result.

### 29.4. Xây reverse dependency index

Cho phép tìm consumer của node thay đổi mà không phải quét toàn graph ở mọi lần chỉnh sửa.

### 29.5. Dùng public interface boundary

Phân biệt implementation với public contract để tránh làm consumer phân tích lại khi interface không đổi.

### 29.6. Snapshot nhất quán

Mỗi analysis chạy trên một revision rõ ràng. Không hợp nhất kết quả thuộc nhiều revision thành một snapshot.

### 29.7. Hủy và ưu tiên tác vụ

Trong IDE, hủy request lỗi thời và ưu tiên syntax/completion trước tác vụ toàn workspace. Kiểm tra revision trước khi publish.

### 29.8. Fallback an toàn

Nếu dependency động, cache hỏng hoặc graph không đầy đủ, invalidate rộng hoặc chạy full analysis.

### 29.9. Đo hiệu năng thực tế

Theo dõi latency, affected node count, cache hit, memory, cancellation và critical path. Tối ưu dựa trên workload đại diện.

### 29.10. So sánh với full analysis

Dùng full analysis làm chuẩn trong kiểm thử để bảo đảm incremental result tương đương.

### 29.11. Quản lý lifecycle cache

Đưa analyzer version, schema version và configuration vào cache identity. Giải phóng revision và cache entry không còn sử dụng.

### 29.12. Diagnostic có revision

Mọi diagnostic và semantic result cần gắn revision để IDE không hiển thị kết quả cũ như trạng thái hiện tại.

## 30. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Incremental Analysis | Chỉ phân tích lại phần bị ảnh hưởng bởi thay đổi |
| Full Analysis | Phân tích lại toàn bộ input |
| Incremental Parsing | Cập nhật parse tree/AST theo vùng source thay đổi |
| Incremental Semantic Analysis | Cập nhật symbol, type và semantic result bị ảnh hưởng |
| Incremental Compilation | Chỉ biên dịch lại phần cần thiết |
| Incremental Build | Chỉ chạy lại task có input hoặc dependency thay đổi |
| Change Detection | Phát hiện file, cấu hình hoặc revision đã thay đổi |
| Dependency Tracking | Ghi nhận quan hệ giữa input và kết quả phân tích |
| Reverse Dependency Graph | Graph cho biết node nào tiêu thụ output của node khác |
| Invalidation | Đánh dấu kết quả cũ không còn hợp lệ |
| Recomputation | Tính lại kết quả đã bị invalidate |
| AST Diff | So sánh cấu trúc AST giữa các revision |
| Stable Node Identity | Định danh node không phụ thuộc đơn thuần vào source offset |
| Symbol Table | Bảng ánh xạ tên đến declaration và metadata |
| Public Interface Fingerprint | Dấu nhận diện của phần contract được consumer sử dụng |
| Negative Dependency | Dependency vào việc một symbol hoặc resource chưa tồn tại |
| Fingerprint | Dấu nhận diện input hoặc kết quả theo nội dung và metadata |
| Cache Key | Khóa xác định kết quả cache có thể tái sử dụng hay không |
| Cache Invalidation | Loại bỏ hoặc đánh dấu cache không còn hợp lệ |
| Worklist | Hàng đợi các node cần xử lý hoặc tính lại |
| Fixed Point | Trạng thái không đổi sau khi áp dụng tiếp phép phân tích |
| Dataflow Analysis | Phân tích truyền thông tin qua graph |
| Snapshot | Bản dữ liệu nhất quán gắn với một revision |
| Stale Result | Kết quả thuộc revision cũ hoặc input không còn hiện hành |
| Debounce | Trì hoãn tác vụ một khoảng ngắn để gộp nhiều thay đổi liên tiếp |
| Cancellation | Hủy công việc không còn cần thiết |
| Critical Path | Đường task quyết định thời gian hoàn tất build |
| Hermetic Task | Task chỉ phụ thuộc input được khai báo và kiểm soát |
| Full Analysis Oracle | Kết quả phân tích đầy đủ dùng làm chuẩn đối chiếu |
| Incremental Analyzer | Thành phần quản lý dependency, invalidation và recomputation |

Phân tích tăng dần giúp DSL toolchain phản hồi nhanh bằng cách tái sử dụng những kết quả còn hợp lệ và chỉ tính lại vùng bị ảnh hưởng. Để đạt được điều đó, hệ thống cần change detection đáng tin cậy, dependency tracking đầy đủ, fingerprint bao quát mọi input, invalidation chính xác và snapshot nhất quán. Khi kết hợp incremental parsing, symbol resolution, type checking, build scheduling, cache management và kiểm thử đối chiếu với full analysis, DSL có thể mở rộng đến project lớn mà vẫn giữ được tính đúng đắn và trải nghiệm tương tác tốt.
