# Tạo công cụ soạn thảo

Một dự án thực hành quan trọng khi học ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL) là **tạo công cụ soạn thảo (DSL editor)**. Công cụ này giúp người dùng viết, đọc, kiểm tra và sửa file DSL với sự hỗ trợ tương tự một IDE: tô màu cú pháp, tự động hoàn thành, hiển thị lỗi tại vị trí chính xác, chuyển đến khai báo, định dạng source và có thể xem trước mô hình hoặc kết quả được tạo ra.

Một DSL chỉ có parser và compiler dạng command line vẫn có thể sử dụng được, nhưng người viết thường phải nhớ cú pháp, tự tìm lỗi và chạy lệnh nhiều lần để biết source có hợp lệ hay không. Editor tích hợp parser và semantic analyzer giúp phản hồi ngay khi người dùng gõ. Nó biến ngôn ngữ thành một công cụ thực tế có thể được dùng trong quy trình phát triển hàng ngày.

Dự án nên bắt đầu bằng một editor nhỏ cho một DSL có grammar rõ ràng, ví dụ DSL khai báo service:

~~~text
service orderApi {
    replicas = 3
    port = 8080

    endpoint getOrder {
        path = "/orders/{id}"
        method = GET
    }
}
~~~

Editor cần nhận biết keyword, identifier, string và number; phân tích file thành AST; báo lỗi khi thiếu dấu ngoặc hoặc gán sai kiểu; gợi ý property hợp lệ sau khi người dùng gõ dấu chấm; và cho phép nhảy từ reference đến declaration. Khi nền tảng cơ bản ổn định, có thể bổ sung formatter, rename, refactoring, preview và tích hợp Language Server Protocol (LSP) để dùng cùng một language service trong nhiều editor.

## 1. Mục tiêu của dự án

Mục tiêu là xây dựng một môi trường soạn thảo giúp người dùng viết DSL chính xác và hiểu được cấu trúc cũng như ý nghĩa của source.

### 1.1. Chức năng cốt lõi

Phiên bản đầu nên hỗ trợ mở file, syntax highlighting, parse, diagnostics, completion cơ bản và lưu file.

### 1.2. Chức năng ngôn ngữ

Editor cần hiểu grammar, AST, symbol, scope và type của DSL. Không nên chỉ tô màu bằng regex nếu mục tiêu là hỗ trợ semantic.

### 1.3. Trải nghiệm tương tác

Khi người dùng sửa source, editor cập nhật diagnostic và completion theo document version. Kết quả cũ không được ghi đè trạng thái mới.

### 1.4. Tách UI khỏi language engine

Parser và semantic analyzer nên là thư viện độc lập. UI hoặc language server gọi API của engine, nhờ đó có thể dùng cùng logic trong CLI, IDE và build tool.

### 1.5. Khả năng mở rộng

Thiết kế cho phép thêm navigation, formatting, refactoring, preview và plugin mà không phải viết lại parser.

### 1.6. Tiêu chí hoàn thành MVP

Một người dùng có thể mở file DSL, thấy syntax được tô màu, nhận lỗi có vị trí, được gợi ý property hợp lệ và lưu source mà không làm mất nội dung.

## 2. Xác định phạm vi và người dùng

Trước khi viết code, cần xác định editor phục vụ ai và họ cần hoàn thành công việc nào.

### 2.1. Người dùng mục tiêu

Có thể là developer viết DSL trong project, chuyên gia nghiệp vụ chỉnh rule, người vận hành sửa configuration hoặc người học DSL.

### 2.2. Workflow chính

Ví dụ workflow: mở project, chọn file DSL, sửa declaration, xem lỗi, dùng completion, format file và chạy validation.

### 2.3. Loại file

Xác định extension, encoding, line ending, cách nhận diện project root và cách xử lý file generated.

### 2.4. Project model

Một file có thể tham chiếu declaration ở file khác. Editor cần biết workspace gồm những file nào và cách resolve import.

### 2.5. Non-goals của MVP

Không cần bắt đầu bằng debugger, visual designer, collaborative editing hoặc plugin marketplace. Những phần này có thể bổ sung sau khi language service đã ổn định.

### 2.6. Success criteria

Đặt tiêu chí có thể kiểm tra: parser phản hồi trong thời gian phù hợp, diagnostic đúng source span, completion chỉ đề xuất symbol hợp lệ và editor không mất thay đổi khi analysis chạy đồng thời.

## 3. Kiến trúc tổng thể

Một DSL editor có thể chia thành giao diện soạn thảo, language service và lõi xử lý ngôn ngữ.

~~~mermaid
flowchart TD
    A[Editor UI] --> B[Document synchronization]
    B --> C[Language service]
    C --> D[Lexer and parser]
    C --> E[Semantic analyzer]
    C --> F[Symbol index]
    C --> G[Formatter and refactoring]
    D --> H[AST]
    H --> E
    E --> I[Diagnostics and semantic model]
    F --> J[Completion and navigation]
    I --> K[Editor features]
    J --> K
    G --> K
~~~

### 3.1. Editor UI

UI hiển thị text buffer, gutter, completion popup, diagnostic markers, outline và các thao tác điều hướng.

### 3.2. Document synchronization

Lớp này nhận thay đổi từ editor, quản lý document version và chuyển change event đến language service.

### 3.3. Language service

Language service cung cấp các operation như parse, diagnostics, completion, hover, definition, references và formatting.

### 3.4. Language engine

Engine chứa lexer, parser, AST, symbol resolution, type checking và validation. Đây là phần có thể tái sử dụng ngoài editor.

### 3.5. Workspace service

Workspace service quản lý file, module, import graph, configuration và symbol index trên nhiều file.

### 3.6. Protocol adapter

Adapter chuyển request/response giữa UI và language service. Nếu dùng LSP, adapter ánh xạ sang protocol messages.

### 3.7. Build/preview integration

Một module riêng có thể gọi compiler hoặc interpreter để chạy validation đầy đủ, xem preview hay tạo artifact.

## 4. Chọn công nghệ và cách tích hợp

Có nhiều cách xây editor. Lựa chọn phụ thuộc vào ứng dụng hiện tại, ngôn ngữ implementation và số editor cần hỗ trợ.

### 4.1. Editor component nhúng trong ứng dụng

Có thể dùng một text editor component như Monaco Editor hoặc CodeMirror trong web app hoặc desktop shell. Component cung cấp buffer, selection, decorations và keyboard handling.

### 4.2. Plugin cho editor hiện có

Có thể tạo extension cho một IDE hoặc text editor. Cách này tận dụng UI và workflow có sẵn, nhưng phụ thuộc API của host editor.

### 4.3. Language Server Protocol

LSP tách language intelligence khỏi editor. Một language server có thể phục vụ nhiều client hỗ trợ protocol.

### 4.4. Custom editor

Tự xây text editor hoàn chỉnh thường tốn nhiều công sức về selection, IME, accessibility, undo/redo và performance. Chỉ nên chọn khi sản phẩm có yêu cầu UI đặc thù.

### 4.5. Hybrid approach

Một ứng dụng có thể nhúng editor component và kết nối đến language server qua JSON-RPC. Cách này giữ UI linh hoạt và dùng lại engine.

### 4.6. Chọn theo năng lực nhóm

Ưu tiên công nghệ nhóm có thể bảo trì, có tài liệu và có API extension ổn định. Không chọn chỉ vì một demo ngắn trông đẹp.

## 5. Thiết kế grammar cho DSL mẫu

Để làm editor, cần một ngôn ngữ nhỏ nhưng đủ construct để kiểm tra nhiều tính năng.

Ví dụ grammar khái quát:

~~~ebnf
document       = { declaration } ;
declaration    = serviceDecl | modelDecl ;
serviceDecl    = "service" Identifier "{" { serviceMember } "}" ;
serviceMember  = propertyDecl | endpointDecl ;
propertyDecl   = Identifier "=" value ;
endpointDecl   = "endpoint" Identifier "{" { propertyDecl } "}" ;
value          = String | Number | Boolean | Identifier ;
~~~

### 5.1. Keyword

Chọn keyword như service, model, endpoint, import và type. Keyword nên có semantics ổn định.

### 5.2. Identifier

Quy định identifier bắt đầu bằng ký tự nào, có hỗ trợ Unicode không và phân biệt hoa thường thế nào.

### 5.3. Literal

Định nghĩa string, number, boolean, null, duration hoặc domain-specific literal.

### 5.4. Block và delimiter

Quy định dấu ngoặc, dấu phẩy, dấu chấm phẩy và newline có ý nghĩa hay không.

### 5.5. Comment

Hỗ trợ comment một dòng hoặc nhiều dòng và xác định chúng có thể xuất hiện ở đâu.

### 5.6. Error recovery

Grammar nên cho parser khả năng phục hồi sau lỗi để editor vẫn hiểu phần source còn lại. Recovery behavior cần được tách khỏi compile success.

### 5.7. Grammar version

Nếu DSL có nhiều language version, parser cần nhận version để áp dụng đúng syntax và semantics.

## 6. Lexer và tokenization

Lexer chuyển source text thành chuỗi token có loại và source span.

### 6.1. Token types

Các token cơ bản gồm keyword, identifier, string, number, operator, punctuation, comment, whitespace và end-of-file.

### 6.2. Token span

Mỗi token giữ start/end offset hoặc range. Span là nền tảng cho highlighting, diagnostic, completion context và navigation.

### 6.3. String escaping

Lexer cần xử lý quote, backslash, newline escape và Unicode theo grammar. Token lỗi vẫn nên có span để editor đánh dấu.

### 6.4. Incremental lexing

Với file lớn, lexer có thể lưu checkpoint và tokenize lại vùng thay đổi. MVP có thể tokenize toàn file trước nếu latency đáp ứng được.

### 6.5. Invalid token

Ký tự không hợp lệ nên tạo diagnostic nhưng không khiến toàn bộ language service crash.

### 6.6. Unicode position

Editor protocol có thể biểu diễn position theo UTF-16 code units, trong khi lexer nội bộ dùng byte hoặc Unicode code point. Cần một lớp chuyển đổi position nhất quán.

## 7. Parser và AST

Parser tạo Abstract Syntax Tree (AST) từ token để các tính năng editor có thể hiểu cấu trúc.

### 7.1. AST node

Mỗi node biểu diễn construct như ServiceDeclaration, EndpointDeclaration, PropertyAssignment hoặc LiteralExpression.

### 7.2. Parent-child relationship

AST giữ quan hệ cha-con để xác định context. Ví dụ completion sau dấu bằng trong endpoint block cần biết property đang được khai báo thuộc endpoint.

### 7.3. Source span

Mỗi node nên lưu span của declaration và các thành phần quan trọng. Span giúp diagnostic và refactoring sửa đúng vùng.

### 7.4. Error node

Parser có thể tạo ErrorNode hoặc MissingToken node khi source chưa hoàn chỉnh. Semantic analyzer cần xử lý các node này an toàn.

### 7.5. AST visitor

Visitor giúp các pass như symbol collection, type checking, formatter và outline duyệt AST theo cách thống nhất.

### 7.6. Immutable AST

AST bất biến giúp các request đồng thời đọc snapshot an toàn. Khi document đổi, tạo AST mới hoặc áp dụng incremental tree update theo revision.

### 7.7. Parse result

Parse result nên chứa AST, token stream, syntax diagnostics và document revision.

## 8. Document model và editor buffer

Editor buffer là trạng thái source đang mở, có thể khác file trên disk.

### 8.1. Document identity

Mỗi document có URI hoặc ID ổn định. Không dùng file name đơn lẻ vì nhiều folder có thể chứa cùng tên.

### 8.2. Document version

Tăng version mỗi khi nội dung thay đổi. Request và result cần gắn version để phát hiện stale result.

### 8.3. Unsaved changes

Language service nên phân tích buffer mới nhất ngay cả khi file chưa được lưu. Không tự ghi buffer vào disk để chạy analysis.

### 8.4. Text change event

Change event có thể chứa toàn bộ text hoặc một range edit. Nếu hỗ trợ incremental sync, cần áp dụng edit theo đúng thứ tự và position encoding.

### 8.5. Line map

Duy trì mapping giữa offset và line/column để chuyển source span sang editor range hiệu quả.

### 8.6. Undo/redo

Undo/redo thuộc editor component. Language service chỉ nhận những thay đổi thực tế trong buffer và cập nhật document version.

### 8.7. Close document

Khi document đóng, giải phóng snapshot hoặc giữ cache workspace theo policy. Không giữ vô hạn AST của file đã đóng.

## 9. Syntax highlighting

Syntax highlighting giúp người dùng nhận biết cấu trúc source nhanh hơn.

### 9.1. Lexical highlighting

Có thể bắt đầu bằng TextMate grammar hoặc tokenizer của editor component để tô keyword, string, number, comment và operator.

### 9.2. Semantic highlighting

Semantic highlighting dùng symbol/type information để phân biệt class, function, property, parameter, enum và reference.

### 9.3. Lexical và semantic layer

Lexical highlighting chạy nhanh và không cần project context. Semantic highlighting chính xác hơn nhưng phụ thuộc parser và semantic analysis.

### 9.4. Theme mapping

Định nghĩa token categories và ánh xạ sang theme. Không hardcode màu trong language engine.

### 9.5. Invalid syntax

Editor có thể tô lỗi lexical hoặc syntax bằng decoration. Không nên để theme color thay thế diagnostic message.

### 9.6. Performance

Highlighting cần tránh gửi quá nhiều decoration cho file lớn. Có thể giới hạn vùng visible hoặc dùng incremental tokenization.

## 10. Diagnostics và error reporting

Diagnostics là tính năng có giá trị cao nhất của language-aware editor.

### 10.1. Syntax diagnostics

Báo thiếu token, sai grammar, block chưa đóng hoặc literal không hợp lệ.

### 10.2. Semantic diagnostics

Báo unresolved reference, duplicate declaration, type mismatch, property không được hỗ trợ hoặc dependency cycle.

### 10.3. Diagnostic fields

Một diagnostic nên có code, severity, message, source span, source identity và có thể có related information.

### 10.4. Severity

Phân biệt error, warning, information và hint. Warning không nên chặn compile nếu policy không yêu cầu.

### 10.5. Related information

Một lỗi duplicate có thể trỏ đến declaration đầu tiên. Một unresolved reference có thể gợi ý import hoặc symbol gần giống.

### 10.6. Debounce

Không nhất thiết chạy semantic analysis sau từng keystroke. Có thể debounce một khoảng ngắn, nhưng syntax feedback cơ bản nên nhanh.

### 10.7. Stale diagnostics

Chỉ publish diagnostics cho document revision tương ứng. Kết quả cũ đến muộn phải bị bỏ qua.

### 10.8. Error recovery

Parser phục hồi để báo nhiều lỗi trong một lần phân tích, nhưng compile action cần yêu cầu source hợp lệ theo policy.

## 11. Code completion

Completion đề xuất keyword, property, type, symbol và value hợp lệ theo vị trí con trỏ.

### 11.1. Context detection

Dựa trên token, AST path và semantic scope để biết người dùng đang ở vị trí declaration, property name, value hay expression.

### 11.2. Keyword completion

Ở đầu document có thể gợi ý service, model hoặc import. Trong block có thể gợi ý các member hợp lệ.

### 11.3. Property completion

Sau khi người dùng gõ tên object hoặc dấu chấm, gợi ý property dựa trên type của object.

### 11.4. Symbol completion

Gợi ý declaration trong scope hiện tại và các module đã import.

### 11.5. Value completion

Với enum hoặc boolean, gợi ý giá trị hợp lệ. Với path hoặc resource reference, có thể gợi ý theo workspace index và permission.

### 11.6. Completion item

Item có thể chứa label, detail, documentation, sort text, filter text và text edit. Không chỉ gửi một chuỗi thay thế nếu cần chèn block nhiều dòng.

### 11.7. Snippets

Snippet giúp chèn construct phổ biến như service block hoặc endpoint declaration. Placeholder cần được đặt đúng vị trí để người dùng tiếp tục nhập.

### 11.8. Incomplete context

Nếu source chưa parse được, completion có thể dùng token context và partial AST. Cần tránh gợi ý quá rộng khi semantic information chưa đủ.

## 12. Hover và documentation

Hover hiển thị thông tin về symbol hoặc construct dưới con trỏ.

### 12.1. Symbol documentation

Hiển thị mô tả, type, signature, module và version của declaration.

### 12.2. Property documentation

Giải thích ý nghĩa, default, allowed values và ví dụ của property.

### 12.3. Deprecated information

Nếu symbol deprecated, hover nên nêu since, replacement, removal target và migration guide.

### 12.4. Type information

Với expression, có thể hiển thị inferred type và constraint. Điều này giúp người dùng hiểu vì sao type checker đưa ra diagnostic.

### 12.5. Markdown content

Documentation có thể hỗ trợ Markdown nhưng cần sanitize và giới hạn nội dung từ extension không tin cậy.

### 12.6. Hover range

Range nên bao phủ token hoặc expression phù hợp. Hover không nên nhấp nháy khi con trỏ di chuyển giữa các ký tự trong cùng symbol.

## 13. Go to definition, references và outline

Navigation giúp người dùng hiểu project lớn và tìm quan hệ giữa các declaration.

### 13.1. Go to definition

Từ reference, tìm declaration tương ứng và mở file tại source range.

### 13.2. Find references

Tìm mọi nơi sử dụng symbol. Cần phân biệt reference thật với chuỗi hoặc comment trùng tên.

### 13.3. Document symbols

Outline hiển thị service, model, endpoint, function và declaration trong file hiện tại.

### 13.4. Workspace symbols

Search symbol trên toàn workspace. Cần index và hỗ trợ filter theo tên hoặc loại.

### 13.5. Call hierarchy

Nếu DSL có function hoặc rule dependency, có thể hiển thị caller/callee hoặc dependency hierarchy.

### 13.6. Rename

Rename symbol cần sửa declaration và references đã resolve, không thay text trùng tên không liên quan.

### 13.7. Cross-file navigation

Workspace service cần resolve import và module identity. Nếu dependency chưa tải hoặc file không mở được, trả diagnostic hoặc location unavailable.

## 14. Formatting và code actions

Formatter giúp source nhất quán; code action giúp sửa lỗi và áp dụng refactoring.

### 14.1. Document formatting

Formatter nhận AST hoặc syntax tree và tạo text theo style config.

### 14.2. Range formatting

Chỉ format vùng được chọn. Cần bảo đảm không làm thay đổi cấu trúc ngoài vùng một cách bất ngờ.

### 14.3. Formatter idempotency

Format hai lần phải cho cùng output. Đây là thuộc tính quan trọng để tránh file liên tục bị thay đổi.

### 14.4. Quick fixes

Có thể thêm import, sửa typo, đổi deprecated property hoặc tạo missing block khi transformation đủ chắc chắn.

### 14.5. Refactoring

Extract component, inline variable, move declaration hoặc rename module cần dùng semantic model và cập nhật reference liên quan.

### 14.6. Workspace edit

Refactoring nhiều file nên được gửi dưới dạng workspace edit để editor quản lý undo và file changes.

### 14.7. Preview changes

Với thao tác có phạm vi rộng, hiển thị diff hoặc preview trước khi áp dụng.

### 14.8. Safe failure

Nếu không thể xác định toàn bộ reference hoặc workspace chưa được index, không thực hiện rename một phần như thể đã thành công.

## 15. Semantic analysis và workspace index

Các tính năng nâng cao cần hiểu ý nghĩa DSL vượt ra ngoài một file.

### 15.1. Symbol collection

Duyệt AST để thu thập declaration và tạo symbol table.

### 15.2. Scope resolution

Resolve reference theo local scope, module scope, import và built-in namespace.

### 15.3. Type checking

Kiểm tra expression, assignment, function call và generic constraint.

### 15.4. Cross-file dependency

Xây graph giữa file/module. Khi declaration thay đổi, tìm consumer cần phân tích lại.

### 15.5. Workspace index

Index symbol, import, type và source location để completion/navigation không phải scan mọi file ở mỗi request.

### 15.6. Index invalidation

File rename, delete, configuration change hoặc dependency version change có thể làm index stale. Cần cập nhật incremental.

### 15.7. Partial workspace

Project có thể chưa load hết file hoặc có dependency lỗi. Language service nên cung cấp trạng thái partial và diagnostic phù hợp thay vì crash.

### 15.8. Built-in symbols

DSL thường có built-in type/function. Chúng cần metadata và documentation giống symbol project để hover/completion nhất quán.

## 16. Language Server Protocol

LSP là protocol phổ biến để editor client giao tiếp với language server qua JSON-RPC.

### 16.1. Client và server

Editor là client gửi request/notification; language server xử lý và trả response hoặc publish diagnostic.

### 16.2. Initialize

Client và server thương lượng capability như completion, hover, definition, formatting, semantic tokens và workspace folders.

### 16.3. Document lifecycle

Các notification như didOpen, didChange, didSave và didClose đồng bộ document state.

### 16.4. Diagnostics

Server có thể publish diagnostics khi document hoặc dependency thay đổi.

### 16.5. Completion request

Client gửi document URI và position. Server xác định context rồi trả completion items.

### 16.6. Navigation requests

Definition, references, hover và document symbols là các request phổ biến.

### 16.7. Cancellation

Request có thể bị hủy khi người dùng tiếp tục gõ hoặc chuyển document. Server nên hỗ trợ cancellation và kiểm tra revision trước khi publish.

### 16.8. Position encoding

LSP position encoding cần được xử lý thống nhất, đặc biệt với Unicode và ký tự surrogate pair. Không giả định offset byte bằng character index.

### 16.9. Capability negotiation

Không phải client nào cũng hỗ trợ mọi feature. Server chỉ nên cung cấp capability đã thương lượng.

### 16.10. Transport

LSP thường chạy qua stdio hoặc socket. Với local editor, stdio thường đơn giản; remote workspace có thể cần transport khác.

## 17. Giao tiếp JSON-RPC và xử lý lỗi

Nếu dùng LSP, JSON-RPC là lớp giao tiếp giữa client và server.

### 17.1. Request/response

Request có ID và nhận response tương ứng. Notification không yêu cầu response.

### 17.2. Message framing

Với stdio transport, message framing phải đúng protocol. Không in debug log tùy tiện vào stdout nếu stdout đang dùng cho protocol.

### 17.3. Error response

Trả error code và message phù hợp khi request không hợp lệ hoặc feature không hỗ trợ.

### 17.4. Logging

Ghi log vào stderr hoặc file riêng theo transport policy. Không trộn log vào stream protocol.

### 17.5. Request timeout

Tác vụ nặng cần timeout hoặc cancellation. Client không nên bị treo vì một completion request mất quá lâu.

### 17.6. Concurrency

Server có thể nhận nhiều request đồng thời. Dùng immutable document snapshot hoặc khóa phù hợp để tránh race condition.

### 17.7. Shutdown

Hỗ trợ shutdown/exit đúng lifecycle để editor có thể đóng server sạch và giải phóng resource.

## 18. Incremental analysis và hiệu năng

Editor cần phản hồi nhanh trong khi người dùng sửa liên tục.

### 18.1. Incremental parsing

Parse lại vùng source bị ảnh hưởng nếu parser hỗ trợ. Với MVP, full parse có thể chấp nhận cho file nhỏ.

### 18.2. Debounce và cancellation

Gộp nhiều keystroke và hủy analysis cũ khi revision mới xuất hiện.

### 18.3. Cache

Cache AST, symbol table, type result và documentation theo fingerprint đầy đủ.

### 18.4. Workspace indexing

Xây index nền và cập nhật khi file thay đổi. Completion không nên quét toàn workspace mỗi lần.

### 18.5. Priority

Ưu tiên completion, hover và syntax diagnostics. Whole-workspace validation có thể chạy nền.

### 18.6. Large file handling

Giới hạn chi phí analysis, tránh tạo quá nhiều decoration và cân nhắc partial analysis cho file rất lớn.

### 18.7. Stale result rejection

Mỗi result mang document/workspace revision. Bỏ kết quả cũ trước khi cập nhật UI.

### 18.8. Metrics

Đo latency p50/p95 cho completion, diagnostics, navigation, parse duration, cache hit và memory usage.

## 19. Project structure đề xuất

Tách module theo trách nhiệm để engine có thể tái sử dụng và test độc lập.

~~~text
dsl-editor/
  language-core/
    lexer/
    parser/
    ast/
    symbols/
    types/
    diagnostics/
  language-service/
    documents/
    workspace/
    completion/
    navigation/
    formatting/
    refactoring/
  language-server/
    protocol/
    handlers/
    transport/
  editor-client/
    syntax/
    commands/
    decorations/
    snippets/
  test-fixtures/
    valid/
    invalid/
    completion/
    navigation/
  examples/
    sample-project/
~~~

### 19.1. language-core

Chứa grammar, parser, AST và semantic analysis. Không phụ thuộc UI hoặc protocol.

### 19.2. language-service

Cung cấp API cấp cao cho diagnostics, completion, navigation, formatting và workspace operations.

### 19.3. language-server

Chuyển request protocol thành lời gọi language-service và serialize response.

### 19.4. editor-client

Chứa extension hoặc UI integration, syntax grammar, snippets, commands và decorations.

### 19.5. test-fixtures

Lưu source mẫu và expected diagnostics/completion/navigation results.

### 19.6. examples

Project mẫu giúp developer thử editor với một DSL thực tế.

### 19.7. Shared model

Các module nên chia sẻ source span, document ID, symbol ID và diagnostic model thay vì tự tạo kiểu dữ liệu khác nhau.

## 20. Thiết kế API của language service

Một API nội bộ rõ giúp UI và LSP adapter không phụ thuộc chi tiết parser.

~~~text
interface LanguageService {
    openDocument(uri, text, version)
    changeDocument(uri, edits, version)
    closeDocument(uri)

    getDiagnostics(uri, version)
    getCompletions(uri, position, version)
    getHover(uri, position, version)
    getDefinition(uri, position, version)
    getReferences(uri, position, version)
    formatDocument(uri, options, version)
}
~~~

### 20.1. Document API

Quản lý open/change/close và revision. Không để UI tự giữ một bản source khác với language service mà không có synchronization.

### 20.2. Query API

Completion và navigation nhận URI, position và version. Kết quả cần xác định rõ revision được dùng.

### 20.3. Cancellation

Có thể truyền cancellation token cho operation tốn kém. API cần xác định hành vi khi token bị hủy.

### 20.4. Result type

Dùng result có trạng thái success, incomplete, cancelled hoặc error. Không trả null mơ hồ cho mọi trường hợp.

### 20.5. Thread safety

Xác định API có thể gọi đồng thời không và object nào immutable. Điều này đặc biệt quan trọng với LSP server.

### 20.6. Testability

Cho phép inject filesystem, clock, configuration và workspace resolver để test không phụ thuộc máy developer.

## 21. Thiết kế UI và trải nghiệm người dùng

Language intelligence chỉ hữu ích khi được trình bày rõ trong editor.

### 21.1. Editor pane

Hiển thị source, line number, selection và cursor. Hỗ trợ keyboard navigation và accessibility.

### 21.2. Gutter diagnostics

Dùng marker ở gutter và underline trong source để báo lỗi. Hover diagnostic hiển thị message và code.

### 21.3. Problems panel

Liệt kê diagnostics theo file và severity. Click item đưa cursor đến source span.

### 21.4. Completion popup

Hiển thị label, type/detail, documentation và snippet insertion. Hỗ trợ keyboard selection.

### 21.5. Outline

Hiển thị cấu trúc declaration theo cây để nhảy nhanh trong file.

### 21.6. Hover panel

Hiển thị signature, documentation, type và deprecation status.

### 21.7. Status indicator

Có thể hiển thị analyzing, ready, incomplete hoặc error. Tránh chỉ dùng màu để biểu diễn trạng thái.

### 21.8. Unsaved indicator

Cho biết buffer chưa lưu và revision đang được phân tích.

### 21.9. Preview panel

Với DSL mô tả UI, workflow hoặc deployment, preview có thể hiển thị model/plan. Preview cần đánh dấu khi dữ liệu chưa hợp lệ hoặc chưa được áp dụng.

## 22. Workspace, import và project configuration

Một editor thực tế thường phải hiểu nhiều file và module.

### 22.1. Project root

Xác định project root bằng manifest hoặc configuration file. Không giả định folder đang mở luôn là root.

### 22.2. Import resolution

Resolve import theo search path, module namespace và version. Diagnostic cần chỉ ra import không tìm thấy.

### 22.3. File watcher

Theo dõi file thay đổi bên ngoài editor. Cần tránh xung đột khi buffer đang có unsaved changes.

### 22.4. Workspace folders

LSP có thể hỗ trợ nhiều workspace folder. Symbol index và cache cần namespace theo workspace.

### 22.5. Configuration reload

Khi project config thay đổi, re-evaluate compiler options, plugin list và dependency graph.

### 22.6. Dependency sources

Nếu DSL dùng package bên ngoài, editor có thể đọc metadata đã resolve. Không tự tải và thực thi plugin chỉ vì source có import.

### 22.7. Multi-root behavior

Xác định import có thể tham chiếu giữa các root hay không và cách xử lý duplicate module names.

## 23. Formatter và style configuration

Formatter giúp project giữ style nhất quán.

### 23.1. Formatting rules

Quy định indentation, brace placement, blank lines, quote style, trailing comma và line width.

### 23.2. Configuration

Style có thể được cấu hình ở project hoặc user level. Cần precedence và default rõ.

### 23.3. Formatter implementation

Có thể format AST hoặc concrete syntax tree. CST giữ comment và trivia tốt hơn; AST cần metadata để không làm mất source details.

### 23.4. Comment preservation

Formatter cần giữ comment và gắn chúng với node phù hợp. Comment bị di chuyển sai có thể làm mất ý nghĩa documentation.

### 23.5. Idempotency

Format một lần và hai lần phải cho cùng kết quả.

### 23.6. Range formatting

Không làm hỏng syntax bên ngoài vùng được chọn. Nếu formatter cần mở rộng vùng, editor cần hiểu giới hạn.

### 23.7. Format on save

Cho phép bật/tắt theo project. Không ghi đè file khi formatter thất bại hoặc document revision đã đổi.

## 24. Refactoring và code actions nâng cao

Khi language service đã có semantic model, có thể bổ sung refactoring an toàn.

### 24.1. Rename symbol

Tìm declaration và references theo symbol identity rồi tạo workspace edit.

### 24.2. Add import

Khi reference unresolved nhưng symbol tồn tại trong module khác, gợi ý thêm import phù hợp.

### 24.3. Extract declaration

Chuyển một expression hoặc block thành declaration riêng nếu grammar và scope cho phép.

### 24.4. Inline declaration

Thay reference bằng expression hoặc value gốc. Cần xem xét side effect và evaluation count.

### 24.5. Move declaration

Chuyển declaration sang module khác và cập nhật import. Cần phát hiện circular dependency.

### 24.6. Deprecated migration

Cung cấp quick fix từ element cũ sang replacement khi mapping chắc chắn.

### 24.7. Workspace transaction

Refactoring nhiều file nên được áp dụng như một thay đổi nhất quán. Nếu một file không thể sửa, report partial failure và không giả vờ hoàn tất.

## 25. Preview, validation và execution

Editor có thể cung cấp preview hoặc chạy DSL, nhưng cần tách phân tích tương tác khỏi thao tác có side effect.

### 25.1. Validate command

Chạy semantic validation đầy đủ và hiển thị diagnostics. Validation không nên thay đổi project.

### 25.2. Preview model

Hiển thị effective configuration, dependency graph, generated output hoặc deployment plan.

### 25.3. Run command

Nếu DSL có interpreter, editor có thể gửi request chạy trong môi trường được giới hạn.

### 25.4. Dry run

Với DSL deployment, dry run tạo plan nhưng không apply resource. Người dùng cần biết rõ preview có tạo side effect hay không.

### 25.5. Confirmation

Thao tác có tác động lớn như deploy hoặc delete cần quyền và confirmation theo policy của ứng dụng.

### 25.6. Output panel

Hiển thị kết quả, warning và error có correlation ID. Không đưa secret vào output.

### 25.7. Cancellation

Cho phép hủy build/preview/run dài. Server cần dừng hoặc đánh dấu request cancelled đúng semantics.

## 26. Bảo mật và độ tin cậy

Editor có thể mở file không tin cậy, nạp extension và gọi language server. Cần bảo vệ cả UI lẫn backend.

### 26.1. Untrusted project

Mở project không đồng nghĩa cho phép chạy task hoặc plugin. Có thể yêu cầu trust decision trước khi thực thi code.

### 26.2. Parser resource limits

Giới hạn file size, nesting depth, AST nodes và thời gian parse để tránh input gây cạn tài nguyên.

### 26.3. Plugin isolation

Plugin có thể chạy trong process riêng hoặc sandbox với quyền tối thiểu.

### 26.4. Path safety

Không để import, formatter hoặc generated output ghi ra ngoài workspace được phép.

### 26.5. Secret protection

Không log toàn bộ source hoặc environment. Secret reference cần được redacted trong hover, diagnostic và preview.

### 26.6. Protocol validation

Kiểm tra JSON-RPC request shape, document URI, position và payload size. Không tin client gửi dữ liệu hợp lệ.

### 26.7. Safe preview

Preview không được thực hiện deployment thật hoặc gửi request đến endpoint không được phép.

### 26.8. Crash isolation

Một parser error hoặc plugin crash không nên làm hỏng editor UI. Language server có thể restart và phục hồi document state theo policy.

## 27. Kiểm thử công cụ soạn thảo

Kiểm thử cần bao phủ engine, protocol và trải nghiệm editor.

### 27.1. Lexer/parser unit tests

Kiểm tra token, AST, source span, error recovery và grammar boundary.

### 27.2. Semantic tests

Kiểm tra symbol resolution, type checking, import và diagnostic.

### 27.3. Completion tests

Fixture có marker cursor để xác minh danh sách item, detail và text edit ở từng context.

### 27.4. Navigation tests

Kiểm tra definition và references qua nhiều file, namespace và import.

### 27.5. Formatter tests

Dùng golden output và idempotency test. Kiểm tra comment, string và line ending.

### 27.6. LSP protocol tests

Gửi initialize, open, change, completion, diagnostics, shutdown và xác minh message shape/capability.

### 27.7. Stale result tests

Tạo hai document revision và cho request cũ hoàn tất sau request mới. Kết quả cũ không được publish.

### 27.8. Integration tests

Mở project mẫu qua editor client và kiểm tra workflow từ file open đến completion và diagnostic.

### 27.9. Performance tests

Đo parse latency, completion latency, workspace indexing và memory trên project lớn.

### 27.10. Accessibility tests

Kiểm tra keyboard-only workflow, screen reader labels, contrast và trạng thái không chỉ phân biệt bằng màu.

### 27.11. Security tests

Thử project không tin cậy, file lớn, nesting sâu, URI bất thường, path traversal và plugin không được cấp quyền.

### 27.12. Cross-platform tests

Nếu editor hỗ trợ Windows, macOS và Linux, kiểm tra path, line ending, process launch và file watcher trên từng nền tảng.

## 28. Lộ trình triển khai theo giai đoạn

Chia dự án thành các mốc nhỏ giúp luôn có một editor hoạt động được.

### 28.1. Giai đoạn 1: Language core

Xây lexer, parser, AST và syntax diagnostics. Viết CLI parse/validate để kiểm tra engine độc lập.

### 28.2. Giai đoạn 2: Editor integration

Tích hợp text editor component và syntax highlighting. Mở/lưu file DSL.

### 28.3. Giai đoạn 3: Diagnostics

Kết nối parser và semantic analyzer để hiển thị lỗi tại source span. Thêm document version và cancellation cơ bản.

### 28.4. Giai đoạn 4: Completion và hover

Xây context detection, symbol table và documentation provider.

### 28.5. Giai đoạn 5: Navigation

Thêm definition, references, outline và workspace index.

### 28.6. Giai đoạn 6: LSP

Đưa language service sau protocol adapter để dùng với editor khác.

### 28.7. Giai đoạn 7: Formatting và refactoring

Thêm formatter, rename và quick fixes dựa trên semantic model.

### 28.8. Giai đoạn 8: Preview và tooling

Thêm validation command, model preview, dependency view và execution integration có kiểm soát.

### 28.9. Giai đoạn 9: Hardening

Kiểm thử hiệu năng, bảo mật, cancellation, recovery, packaging và cross-platform behavior.

## 29. Ví dụ workflow sử dụng editor

Giả sử người dùng mở file service DSL và nhập:

~~~text
service orderApi {
    replicas = "three"
    port = 8080
}
~~~

### 29.1. Syntax highlighting

Editor tô keyword service, identifier orderApi, property replicas và string literal.

### 29.2. Parsing

Parser tạo ServiceDeclaration với hai PropertyAssignment. Cấu trúc có thể hợp lệ về syntax dù value sai kiểu.

### 29.3. Semantic validation

Type checker phát hiện replicas yêu cầu Integer nhưng nhận String.

### 29.4. Diagnostic

Editor hiển thị error tại vùng "three", ví dụ: Expected Integer for property replicas.

### 29.5. Completion

Người dùng xóa value và gọi completion; editor gợi ý giá trị hoặc expression kiểu Integer.

### 29.6. Hover

Hover trên replicas hiển thị type Integer, default và range hợp lệ.

### 29.7. Quick fix

Nếu có conversion chắc chắn, tool có thể gợi ý sửa literal. Với "three", không nên tự đoán thành 3 nếu semantics không xác định.

### 29.8. Preview

Sau khi source hợp lệ, người dùng xem effective service model hoặc deployment plan mà không apply.

## 30. Tiêu chí đánh giá và cải tiến

Sau khi có MVP, cần đánh giá theo khả năng sử dụng thực tế thay vì chỉ đếm số feature.

### 30.1. Correctness

Diagnostic, completion và navigation có đúng với source semantics không?

### 30.2. Latency

Completion và diagnostics có phản hồi đủ nhanh trong project đại diện không?

### 30.3. Reliability

Editor có giữ document state khi server restart hoặc request bị cancel không?

### 30.4. Usability

Người dùng có tìm được property, hiểu diagnostic và biết cách sửa lỗi không?

### 30.5. Maintainability

Language core có độc lập UI, có test fixture và API ổn định không?

### 30.6. Extensibility

Có thể thêm một keyword, type hoặc backend mà không sửa nhiều lớp không liên quan không?

### 30.7. Compatibility

Editor và language server có hoạt động với version DSL và client được hỗ trợ không?

### 30.8. Security

Project không tin cậy có thể làm editor chạy code, đọc secret hoặc truy cập filesystem ngoài quyền không?

### 30.9. Feedback loop

Thu thập phản hồi về completion quality, false diagnostics và feature thiếu để ưu tiên cải tiến.

## 31. Những sai lầm thường gặp

### 31.1. Chỉ dùng regex cho mọi tính năng

Regex có thể đủ cho syntax coloring ban đầu nhưng không hiểu scope, type và nested structure. Completion và navigation cần parser/semantic model.

### 31.2. Trộn parser với UI

Parser phụ thuộc editor component khiến khó dùng trong CLI, build tool và test. Giữ language core độc lập.

### 31.3. Không quản lý document version

Analysis cũ có thể ghi đè diagnostics mới. Mọi request/result cần gắn revision.

### 31.4. Không xử lý source chưa hoàn chỉnh

Người dùng thường đang gõ giữa chừng. Parser phải có error recovery và language service cần trả kết quả partial có kiểm soát.

### 31.5. Completion không dựa trên context

Gợi ý mọi keyword ở mọi vị trí làm feature ít hữu ích. Xác định context từ syntax và semantic scope.

### 31.6. Không kiểm tra Unicode position

Offset sai làm diagnostic và edit lệch ký tự, đặc biệt với emoji hoặc ký tự ngoài Basic Multilingual Plane.

### 31.7. Chạy analysis đồng bộ trên UI thread

File lớn có thể làm editor đứng. Chạy tác vụ nặng nền, hỗ trợ cancellation và ưu tiên tương tác.

### 31.8. Không tách protocol logs

Log vào stdout khi dùng stdio LSP có thể phá framing và làm server mất kết nối.

### 31.9. Thực thi project ngay khi mở

Project có thể không tin cậy. Mở file và phân tích nên tách khỏi quyền chạy plugin, task hoặc deployment.

### 31.10. Formatter làm mất comment

AST formatter không giữ trivia có thể xóa hoặc di chuyển comment. Dùng CST hoặc cơ chế gắn comment rõ.

### 31.11. Rename bằng text search

Text search có thể đổi string hoặc comment không liên quan. Rename cần symbol resolution.

### 31.12. Không test trên project lớn

Một editor nhanh với một file nhỏ có thể chậm nghiêm trọng ở workspace nhiều module. Benchmark cần project đại diện.

## 32. Nguyên tắc xây dựng DSL editor

Một công cụ soạn thảo tốt cần đặt language semantics làm nền tảng và cung cấp phản hồi nhanh, đáng tin cậy.

### 32.1. Xây language core độc lập

Lexer, parser, AST, symbol table và type checker không phụ thuộc UI hoặc protocol.

### 32.2. Dùng source span nhất quán

Mọi token, AST node và diagnostic cần giữ source location có thể chuyển đổi đúng sang editor position.

### 32.3. Bắt đầu với MVP hữu ích

Ưu tiên syntax highlighting, diagnostics, completion và open/save trước các tính năng nâng cao.

### 32.4. Tách lexical và semantic features

Syntax coloring có thể chạy nhanh; semantic highlighting, completion và navigation dùng semantic model.

### 32.5. Quản lý revision

Document version, cancellation và stale-result rejection là yêu cầu nền tảng của editor tương tác.

### 32.6. Dùng LSP khi cần nhiều client

LSP giúp tách language server khỏi editor và tái sử dụng language intelligence.

### 32.7. Hỗ trợ source chưa hoàn chỉnh

Error recovery giúp người dùng tiếp tục làm việc trong khi file đang có lỗi tạm thời.

### 32.8. Giữ UI phản hồi nhanh

Chạy analysis nền, debounce hợp lý, cache và incremental update. Không để request cũ chặn request mới.

### 32.9. Dùng semantic model cho refactoring

Rename, references và code action phải dựa vào symbol identity và type information.

### 32.10. Bảo vệ project không tin cậy

Parse có giới hạn, không tự thực thi plugin, kiểm soát path và chỉ cấp quyền khi người dùng chủ động.

### 32.11. Kiểm thử theo protocol và workflow

Kết hợp unit, fixture, LSP protocol, integration, performance, accessibility và security tests.

### 32.12. Đo trước khi tối ưu

Theo dõi latency, memory, index cost và cancellation waste trên project đại diện.

### 32.13. Documentation và onboarding

Cung cấp hướng dẫn cài đặt, cấu hình language server, supported features, troubleshooting và ví dụ project.

## 33. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| DSL Editor | Công cụ soạn thảo có hiểu biết về ngôn ngữ DSL |
| Language Core | Lõi lexer, parser, AST và semantic analysis |
| Language Service | API cung cấp diagnostics, completion, hover và navigation |
| Language Server | Process cung cấp language features qua protocol |
| LSP | Language Server Protocol, giao thức kết nối editor với language server |
| JSON-RPC | Giao thức request/response thường dùng trong LSP |
| Text Buffer | Nội dung document đang mở trong editor |
| Document Version | Số revision của nội dung document |
| Lexer | Thành phần chuyển source thành token |
| Token | Đơn vị lexical như keyword, identifier hoặc literal |
| Parser | Thành phần tạo AST từ token |
| AST | Cây cú pháp trừu tượng của source |
| Source Span | Vị trí bắt đầu/kết thúc của token hoặc node trong source |
| Semantic Analysis | Phân giải tên, kiểm tra kiểu và ràng buộc ngữ nghĩa |
| Symbol Table | Cấu trúc lưu declaration và scope |
| Diagnostics | Lỗi, warning và thông tin phân tích |
| Code Completion | Gợi ý construct hoặc symbol tại vị trí con trỏ |
| Hover | Thông tin về symbol hoặc expression dưới con trỏ |
| Go to Definition | Điều hướng đến declaration của symbol |
| Find References | Tìm các vị trí sử dụng symbol |
| Document Symbols | Outline các declaration trong file |
| Semantic Tokens | Token classification dựa trên semantic model |
| Code Action | Hành động sửa lỗi hoặc refactoring |
| Formatter | Thành phần chuẩn hóa cách trình bày source |
| Workspace Index | Index symbol và dependency trên nhiều file |
| Incremental Analysis | Chỉ cập nhật phần phân tích bị ảnh hưởng |
| Cancellation | Hủy request không còn cần thiết |
| Stale Result | Kết quả thuộc document/workspace revision cũ |
| Completion Item | Một lựa chọn trong danh sách gợi ý |
| Source Mapping | Liên kết generated output hoặc diagnostic với source DSL |
| Error Recovery | Cơ chế parser tiếp tục phân tích sau lỗi |
| Preview | Hiển thị model hoặc plan mà chưa thực thi thay đổi |
| Capability Negotiation | Trao đổi feature mà client và server hỗ trợ |
| Workspace Edit | Thay đổi có cấu trúc trên một hoặc nhiều file |
| Test Fixture | Source và dữ liệu mẫu dùng để kiểm thử editor |

Tạo công cụ soạn thảo là dự án kết hợp ngôn ngữ học, compiler engineering và trải nghiệm developer. Một editor hữu ích không chỉ tô màu source mà còn cần hiểu AST, symbol, type, scope và revision để cung cấp diagnostics, completion, navigation và refactoring chính xác. Khi tách language core khỏi UI, quản lý document snapshot, dùng LSP khi cần nhiều client và kiểm thử cả protocol lẫn workflow thực tế, công cụ có thể phát triển từ một editor nhỏ thành môi trường làm việc đáng tin cậy cho DSL.
