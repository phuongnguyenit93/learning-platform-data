# Chất lượng tooling

**Tooling** là tập hợp công cụ hỗ trợ người dùng tạo, kiểm tra, hiểu, gỡ lỗi và duy trì chương trình. Với một DSL, tooling có thể gồm command-line interface (CLI), IDE plugin, language server, syntax highlighting, code completion, formatter, diagnostics, debugger, documentation generator, schema validator và build integration.

**Chất lượng tooling** (*tooling quality*) mô tả mức độ các công cụ này giúp người dùng làm việc chính xác, nhanh, dễ hiểu và đáng tin cậy. Một DSL có grammar tốt nhưng không có diagnostics rõ ràng, completion sai hoặc formatter làm thay đổi semantics vẫn tạo trải nghiệm phát triển kém.

Chất lượng tooling là một phần của chất lượng thiết kế DSL. Nó ảnh hưởng thời gian học, tốc độ phát triển, khả năng phát hiện lỗi, chi phí bảo trì và mức độ tin cậy của hệ thống.

Ví dụ, khi người dùng viết:

~~~text
service "catalog" {
    timeout = "five seconds"
    endpoint = "https://catalog.example.com"
}
~~~

Tooling tốt có thể phát hiện timeout cần kiểu Duration, chỉ rõ vị trí lỗi, đề xuất cách sửa và liên kết đến reference của field timeout. Người dùng không cần đợi đến runtime mới biết cấu hình sai.

## 1. Tooling trong hệ sinh thái DSL

Tooling không chỉ là editor plugin. Nó bao gồm toàn bộ công cụ trong vòng đời tạo và vận hành chương trình DSL.

| Tool | Vai trò |
|---|---|
| CLI | Parse, validate, compile, run và inspect |
| Syntax highlighter | Tô màu token và cấu trúc |
| Language server | Completion, hover, diagnostics và navigation |
| Formatter | Chuẩn hóa cách trình bày source |
| Linter | Phát hiện vấn đề về style, maintainability hoặc policy |
| Debugger | Theo dõi execution, breakpoint và state |
| Documentation tool | Sinh và tra cứu reference |
| Schema validator | Kiểm tra cấu hình theo schema |
| Build integration | Kết nối DSL với build pipeline |
| Migration tool | Chuyển đổi source hoặc configuration giữa version |

### 1.1. CLI

CLI là điểm vào phổ biến để parse, check, compile, execute, format hoặc inspect chương trình.

### 1.2. IDE và editor

IDE cung cấp syntax highlighting, completion, navigation, quick fix và hiển thị diagnostics ngay khi người dùng sửa source.

### 1.3. Language server

Language server chuẩn hóa các chức năng ngôn ngữ để nhiều editor có thể dùng chung backend.

### 1.4. Debugging và observability

Debugger và execution inspector giúp hiểu chương trình chạy như thế nào, vì sao một nhánh được chọn và dữ liệu đi qua các bước ra sao.

### 1.5. Tooling cho CI/CD

Build integration chạy formatter check, validation, compilation và policy check trong pipeline.

## 2. Các chiều chất lượng tooling

Chất lượng tooling có nhiều chiều và đôi khi chúng xung đột.

| Chiều chất lượng | Câu hỏi đánh giá |
|---|---|
| Correctness | Tool có hiểu đúng syntax và semantics không? |
| Accuracy | Diagnostics và completion có chính xác không? |
| Responsiveness | Tool phản hồi đủ nhanh khi project lớn không? |
| Consistency | CLI, IDE và compiler có cùng cách hiểu không? |
| Discoverability | Người dùng có tìm thấy chức năng cần thiết không? |
| Usability | Kết quả có dễ hiểu và dễ hành động không? |
| Reliability | Tool có ổn định khi file lỗi hoặc dependency thiếu không? |
| Compatibility | Tool có tương thích editor, OS và DSL version không? |
| Accessibility | Tool có hỗ trợ keyboard và assistive technology không? |
| Maintainability | Tool có dễ phát triển và cập nhật không? |

### 2.1. Correctness

Tooling phải phản ánh semantics của DSL. Completion không được đề xuất field không hợp lệ trong context hiện tại; formatter không được thay đổi thứ tự có ý nghĩa.

### 2.2. Responsiveness

Người dùng thường kỳ vọng editor phản hồi gần như tức thời. Tool cần incremental processing, cancellation và giới hạn công việc trên mỗi request.

### 2.3. Consistency

Một file được IDE chấp nhận nhưng CLI từ chối sẽ làm người dùng mất niềm tin. Các công cụ nên dùng chung parser, semantic model và version configuration.

### 2.4. Reliability

Tool phải xử lý được source chưa hoàn chỉnh, file lớn, dependency thiếu và project đang thay đổi mà không crash.

### 2.5. Maintainability

Tooling cần có API rõ, test phù hợp và cơ chế tương thích khi grammar hoặc compiler thay đổi.

## 3. CLI quality

CLI thường được dùng trong local development, scripting và CI.

### 3.1. Command design

Command và option cần tên nhất quán, predictable và help đầy đủ.

~~~text
dsl parse project.dsl
dsl check project.dsl
dsl format --check project.dsl
dsl compile project.dsl --output build/
dsl run project.dsl --environment staging
~~~

### 3.2. Exit code

CLI nên trả exit code ổn định. CI cần dựa vào exit code thay vì parse message tự do. Có thể phân biệt parse, validation, compilation và execution failure nếu contract của CLI quy định.

### 3.3. Standard output và standard error

Kết quả thành công hoặc machine-readable output có thể đi qua stdout. Diagnostics và progress thường đi qua stderr để script có thể capture kết quả.

### 3.4. Machine-readable output

JSON hoặc structured output giúp CI, editor và automation tiêu thụ diagnostics mà không phải parse text.

### 3.5. Stable output

Không nên thay đổi format output machine-readable mà không version hóa. Human-readable message có thể cải thiện, nhưng automation cần schema ổn định.

### 3.6. Help và examples

CLI cần có help theo command, ví dụ hoàn chỉnh, option default và link đến reference.

### 3.7. Offline behavior

Các lệnh parse và format thường nên hoạt động offline nếu không cần resolve remote dependency. Nếu command cần network, thông báo rõ.

### 3.8. Configuration precedence

CLI cần hiển thị hoặc giải thích precedence giữa command-line option, config file, environment variable và default.

## 4. Syntax highlighting

Syntax highlighting giúp người dùng nhận diện cấu trúc source nhanh hơn.

### 4.1. Token categories

Highlighter có thể phân biệt keyword, identifier, string, number, operator, comment, type và annotation.

### 4.2. Lexical accuracy

Highlighter nên dựa trên lexer hoặc grammar có cùng quy tắc với parser. Regex đơn giản có thể tô màu sai khi có multiline string hoặc nested syntax.

### 4.3. Incomplete source

Editor thường chứa source chưa hoàn chỉnh. Highlighter cần xử lý được dấu ngoặc chưa đóng, string chưa kết thúc hoặc block đang được nhập.

### 4.4. Theme compatibility

Token scope cần rõ để theme khác nhau có thể trình bày phù hợp. Không nên dựa vào màu cố định.

### 4.5. Performance

Highlighting nên cập nhật theo vùng thay đổi và không parse lại toàn bộ project cho mỗi ký tự nếu không cần thiết.

## 5. Language server

Language server cung cấp các dịch vụ ngôn ngữ cho editor thông qua một protocol chung.

Các chức năng phổ biến:

- Diagnostics.
- Completion.
- Hover information.
- Go to definition.
- Find references.
- Rename symbol.
- Document symbols.
- Formatting.
- Code actions.
- Semantic tokens.

### 5.1. Shared language core

Language server nên dùng cùng frontend và semantic analyzer với CLI/compiler. Nó có thể xây dựng thêm index hoặc cache cho trải nghiệm tương tác.

### 5.2. Document lifecycle

Server nhận thông báo mở, thay đổi, lưu và đóng document. Cần quản lý document version để không áp dụng kết quả cũ lên nội dung mới.

### 5.3. Incremental update

Editor thường gửi text changes. Server có thể cập nhật syntax tree hoặc invalidation theo phạm vi thay đổi.

### 5.4. Request cancellation

Completion hoặc diagnostics cũ có thể bị hủy khi người dùng tiếp tục gõ. Server cần hỗ trợ cancellation để tránh lãng phí CPU.

### 5.5. Workspace awareness

Language server cần hiểu project root, module, import path và dependency để resolve symbol xuyên file.

### 5.6. Capability negotiation

Editor có thể hỗ trợ một số tính năng khác nhau. Server cần thương lượng capability thay vì giả định mọi client giống nhau.

### 5.7. Server lifecycle

Server cần xử lý startup, shutdown, restart và crash recovery. Log và protocol message cần tách biệt để không làm hỏng giao tiếp.

## 6. Code completion

Completion đề xuất construct, field, symbol hoặc value hợp lệ tại vị trí con trỏ.

### 6.1. Context-aware completion

Gợi ý cần phụ thuộc vị trí:

- Top-level: module, service hoặc workflow.
- Trong block endpoint: scheme, hostname, port và timeout.
- Trong expression: variable, function và operator.
- Sau import: module hoặc package có thể truy cập.

### 6.2. Type-aware completion

Nếu field yêu cầu Duration, completion nên ưu tiên duration literal hoặc expression có type tương thích.

### 6.3. Scope-aware completion

Chỉ đề xuất biến và function đang visible trong scope hiện tại.

### 6.4. Ranking

Đề xuất phù hợp nhất nên xuất hiện trước. Ranking có thể dựa trên context, prefix, symbol kind và usage history nếu được phép.

### 6.5. Snippet

Snippet có thể chèn một block hoàn chỉnh với placeholder:

~~~text
service "name" {
    endpoint = "https://..."
    timeout = 5s
}
~~~

### 6.6. Completion không hợp lệ

Không nên đề xuất field deprecated hoặc inaccessible mà không có label rõ. Nếu vẫn đề xuất để hỗ trợ migration, cần phân biệt với API hiện hành.

## 7. Hover, navigation và symbol index

Các tính năng navigation giúp người dùng hiểu chương trình lớn.

### 7.1. Hover

Hover có thể hiển thị symbol type, documentation, default value, deprecation và source location.

### 7.2. Go to definition

Từ reference, người dùng có thể đi đến declaration trong cùng file hoặc module khác.

### 7.3. Find references

Cho biết symbol được sử dụng ở đâu. Kết quả cần phân biệt read, write, import và call nếu có.

### 7.4. Rename

Rename phải dựa trên symbol identity, không chỉ thay chuỗi giống nhau. Cần tránh đổi string literal hoặc identifier không liên quan.

### 7.5. Symbol index

Project index lưu symbol, type, file location và dependency. Index cần được cập nhật incremental khi file thay đổi.

### 7.6. Cross-file resolution

Import và module resolution cần dùng cùng quy tắc với compiler để navigation không dẫn đến symbol sai.

## 8. Diagnostics và error presentation

Diagnostics giúp người dùng phát hiện và sửa lỗi trong source hoặc configuration.

### 8.1. Diagnostic structure

Một diagnostic nên có:

- Error hoặc warning code.
- Severity.
- Message.
- Source range.
- Related location nếu có.
- Suggested action hoặc documentation link.

### 8.2. Precise source range

Underline nên trỏ đến token hoặc expression gây lỗi, không tô cả file nếu có thể xác định vị trí cụ thể.

### 8.3. Actionable message

Message nên nói điều gì sai và gợi ý cách sửa. Ví dụ, unknown property có thể đề xuất property gần giống nếu việc gợi ý đủ tin cậy.

### 8.4. Related information

Khi lỗi phát sinh do hai declaration xung đột, diagnostics có thể chỉ ra cả vị trí khai báo hiện tại và vị trí khai báo trước.

### 8.5. Severity

Phân biệt error, warning, information và hint. Không biến mọi vấn đề style thành compile error.

### 8.6. Error recovery

Tooling cần tiếp tục phân tích phần source còn lại sau lỗi cú pháp để người dùng nhận được nhiều diagnostics hữu ích.

### 8.7. Avoid diagnostic cascades

Một lỗi parse có thể tạo nhiều lỗi semantic giả. Analyzer cần nhận biết node không hợp lệ và hạn chế báo lỗi thứ cấp gây nhiễu.

### 8.8. Quick fix

Quick fix có thể thêm field, sửa tên, import symbol hoặc thay syntax deprecated. Chỉ đề xuất thay đổi khi có thể xác định kết quả an toàn.

### 8.9. Diagnostic stability

Error code và structured output cần ổn định để IDE, CI và automation có thể dựa vào.

## 9. Formatter quality

Formatter chuẩn hóa source để giảm khác biệt không cần thiết trong code review.

### 9.1. Deterministic formatting

Cùng source và cùng formatter version nên tạo cùng output. Điều này giúp tránh diff ngẫu nhiên giữa các máy.

### 9.2. Idempotence

Format một lần rồi format lần nữa không nên tiếp tục thay đổi file:

~~~text
format(format(source)) = format(source)
~~~

### 9.3. Semantics preservation

Formatter chỉ thay đổi presentation. Nó không được thay đổi thứ tự statement nếu thứ tự có ý nghĩa, không đổi literal hoặc loại bỏ comment có ý nghĩa.

### 9.4. Configuration

Các option như indent width, line width, brace style và trailing comma cần có default nhất quán. Quá nhiều option làm tăng chi phí hỗ trợ.

### 9.5. Comment preservation

Formatter cần giữ comment và liên kết comment với node phù hợp. Comment gắn với declaration có thể cần được giữ vị trí.

### 9.6. Partial formatting

Editor có thể yêu cầu format một range. Formatter cần tránh làm thay đổi phần ngoài range ngoài những điều chỉnh bắt buộc về cấu trúc.

### 9.7. Format check

CLI có thể hỗ trợ check-only mode để CI phát hiện source chưa được format mà không sửa file.

## 10. Linter và static analysis

Linter phát hiện vấn đề về style, maintainability, reliability hoặc policy mà grammar và type checker không nhất thiết bắt được.

### 10.1. Rule categories

Rule có thể chia thành:

- Style.
- Correctness.
- Performance.
- Security.
- Maintainability.
- Compatibility.

### 10.2. Static analysis

Analyzer có thể phát hiện unused variable, unreachable branch, deprecated function, risky operation hoặc dependency không được phép.

### 10.3. Rule severity

Mỗi rule nên có severity và khả năng override có kiểm soát. Một policy bảo mật bắt buộc không nên bị tắt bởi config thông thường.

### 10.4. Suppression

Suppression cần có scope nhỏ, lý do và có thể có expiration. Tránh tắt toàn bộ rule chỉ để che một cảnh báo.

### 10.5. False positive

False positive làm người dùng mất niềm tin. Rule cần dựa trên dữ liệu semantic đủ chính xác và có cơ chế báo lỗi analyzer.

### 10.6. Rule configuration

Linter config nên có version, default profile và cách override theo project hoặc directory.

## 11. Refactoring và code actions

Refactoring giúp thay đổi cấu trúc chương trình mà giữ behavior.

Các thao tác thường gặp:

- Rename symbol.
- Extract variable.
- Extract function.
- Inline variable.
- Organize imports.
- Convert deprecated syntax.
- Add missing field.
- Change type annotation.

### 11.1. Semantic refactoring

Refactoring phải dựa trên symbol và type information. Thay thế chuỗi văn bản đơn giản có thể sửa nhầm identifier hoặc literal.

### 11.2. Preview

Với thay đổi nhiều file, tooling nên cho phép xem diff trước khi áp dụng.

### 11.3. Atomic edit

Một refactoring cần áp dụng các edit như một đơn vị để tránh trạng thái nửa hoàn thành nếu một file không ghi được.

### 11.4. Code action

Code action có thể gắn với diagnostic hoặc vùng code được chọn. Mô tả action cần nói rõ thay đổi sẽ xảy ra.

### 11.5. Behavior preservation

Refactoring cần giữ semantics, evaluation order, comments và source mapping ở mức phù hợp.

## 12. Debugger và execution tooling

Debugger giúp quan sát execution thay vì chỉ xem output cuối.

### 12.1. Breakpoint

Breakpoint có thể gắn với source line, statement hoặc DSL node. Runtime cần map breakpoint đến instruction hoặc execution plan.

### 12.2. Step execution

Debugger có thể hỗ trợ step into, step over, step out và continue.

### 12.3. Variable inspection

Người dùng có thể xem giá trị biến, type và scope hiện tại. Secret hoặc dữ liệu nhạy cảm cần được redacted.

### 12.4. Call stack

Call stack cần thể hiện DSL function và host call theo cách dễ hiểu, đồng thời liên kết đến source location.

### 12.5. Source map

Nếu DSL được compile sang bytecode hoặc code khác, source map liên kết generated instruction với dòng DSL gốc.

### 12.6. Execution trace

Trace có thể ghi rule, task, branch hoặc host operation đã chạy. Cần giới hạn dung lượng và tránh ghi dữ liệu nhạy cảm.

### 12.7. Deterministic replay

Với DSL workflow hoặc rule, replay có thể giúp tái dựng lỗi nếu runtime lưu input, dependency version và external response cần thiết.

### 12.8. Debug mode overhead

Debug instrumentation có thể làm execution chậm. Cần phân biệt debug build và production behavior.

## 13. Documentation tooling

Documentation tooling giúp tạo, kiểm tra và tra cứu tài liệu DSL.

### 13.1. API reference generator

Có thể sinh signature, type, default và deprecation metadata từ symbol registry.

### 13.2. Example runner

Code examples có thể được chạy trong pipeline để phát hiện syntax hoặc API đã lỗi thời.

### 13.3. Link checker

Kiểm tra internal anchor, reference link và URL bên ngoài.

### 13.4. Versioned documentation

Người dùng cần xem reference phù hợp với language/compiler version đang sử dụng.

### 13.5. Search

Search nên index keyword, symbol, field, error code và alias.

### 13.6. IDE integration

Hover và completion có thể lấy documentation metadata từ cùng source với website reference.

## 14. Schema validation và configuration tooling

Với configuration DSL, tooling có thể dùng schema để hỗ trợ editor và CI.

### 14.1. Schema

Schema mô tả property, type, required condition, default, enum và nested object.

### 14.2. Completion từ schema

Editor có thể gợi ý property và value hợp lệ.

### 14.3. Validation

Validator kiểm tra type, range, unknown property và cross-field constraint.

### 14.4. Schema version

Schema cần gắn với DSL/runtime version để tránh validate file theo quy tắc khác với deployment target.

### 14.5. Custom validation

Một số constraint phụ thuộc domain hoặc host context, không thể biểu diễn đầy đủ bằng schema tĩnh. Có thể gọi semantic validation service.

### 14.6. Secret-aware tooling

Editor và CLI không nên yêu cầu tải secret thật chỉ để hiển thị completion hoặc validate cấu trúc. Secret resolution cần được tách khỏi static analysis khi có thể.

## 15. Shared language services

Một trong những quyết định kiến trúc quan trọng là dùng chung language core giữa compiler, CLI và IDE.

### 15.1. Single source of truth

Lexer, parser, type checker và symbol resolver nên có implementation chung. Nếu IDE có parser riêng, syntax acceptance có thể khác compiler.

### 15.2. Shared diagnostics

Diagnostic code, severity và source span nên được tạo ở core. Mỗi client chỉ chuyển thành presentation phù hợp.

### 15.3. Shared semantic model

Completion, hover, navigation và validation cần dùng cùng symbol/type model để kết quả nhất quán.

### 15.4. Different execution modes

IDE có thể chạy analyzer ở chế độ incomplete hoặc tolerant; compiler chạy strict mode. Hai chế độ vẫn nên dùng chung grammar và semantics nền tảng.

### 15.5. API boundary

Tooling API cần tránh expose internal mutable AST nếu consumer có thể giữ reference lâu. Immutable snapshot hoặc query API giúp quản lý lifecycle rõ hơn.

## 16. Incremental analysis và project indexing

Project lớn không thể parse và analyze lại toàn bộ sau mỗi thay đổi nhỏ.

### 16.1. Document-level cache

Giữ parse result và semantic result của từng document, kèm document version.

### 16.2. Incremental parsing

Khi một vùng source thay đổi, parser có thể tái sử dụng node không bị ảnh hưởng nếu implementation hỗ trợ.

### 16.3. Dependency invalidation

Nếu module A import module B và B thay đổi, semantic result của A có thể cần được tính lại. Dependency graph giúp xác định phạm vi invalidation.

### 16.4. Project index

Index lưu symbol và import graph để navigation và completion không phải scan toàn bộ file mỗi lần.

### 16.5. Cancellation và stale result

Khi document version mới xuất hiện, request cũ có thể bị cancel. Nếu kết quả cũ hoàn tất muộn, server cần bỏ qua nó.

### 16.6. Background work

Index toàn workspace hoặc resolve remote dependency có thể chạy nền. UI cần thể hiện trạng thái chưa hoàn tất mà không chặn thao tác nhập.

### 16.7. Cache invalidation

Cache key cần bao gồm language version, compiler version, dependency revision và config ảnh hưởng semantics.

## 17. Performance và responsiveness

Tooling thường chạy song song với thao tác nhập liệu. Độ trễ nhỏ nhưng lặp lại có thể ảnh hưởng đáng kể trải nghiệm.

### 17.1. Latency budget

Đặt mục tiêu phản hồi riêng cho highlighting, completion, hover và full workspace indexing. Không phải mọi request cần cùng mức latency.

### 17.2. Fast path

Completion theo prefix hoặc syntax highlighting có thể dùng thông tin lexical trước khi semantic analysis hoàn tất.

### 17.3. Lazy resolution

Không resolve mọi remote dependency nếu người dùng chỉ đang sửa một file không liên quan. Resolve khi feature cần thông tin đó.

### 17.4. Bounded work

Giới hạn kích thước file, recursion, number of diagnostics và thời gian cho request để tránh editor bị treo.

### 17.5. Background indexing

Index lớn nên chạy nền với progress và cancellation.

### 17.6. Memory management

Document snapshot, AST và symbol index có thể chiếm memory lớn. Cần eviction policy và quản lý reference lifecycle.

### 17.7. Measure real workload

Benchmark project lớn, nhiều module, dependency graph sâu và file đang incomplete. Microbenchmark parser riêng không phản ánh toàn bộ trải nghiệm.

## 18. Compatibility và portability

Tooling cần hoạt động trên nhiều editor, hệ điều hành và version DSL.

### 18.1. Editor protocol

Language server giúp tái sử dụng backend giữa editor, nhưng cần kiểm tra capability và khác biệt implementation.

### 18.2. OS portability

Path separator, file watcher, case sensitivity và process behavior khác nhau giữa OS. Tooling cần xử lý theo platform abstraction.

### 18.3. Runtime version

IDE có thể hỗ trợ nhiều DSL version. Workspace cần xác định version mục tiêu và language server phải dùng đúng grammar.

### 18.4. Plugin compatibility

IDE plugin và language server có thể release độc lập. Cần version matrix hoặc protocol negotiation.

### 18.5. Offline development

Tooling trong môi trường hạn chế mạng cần cache package, reference và compiler artifact theo policy.

### 18.6. Graceful degradation

Nếu một feature không được editor hỗ trợ, server vẫn nên cung cấp các chức năng cơ bản như diagnostics và completion nếu có thể.

## 19. Accessibility và user experience

Tooling tốt cần phục vụ nhiều cách làm việc và khả năng sử dụng khác nhau.

### 19.1. Keyboard navigation

Các chức năng chính nên truy cập được bằng keyboard và shortcut có thể tùy chỉnh.

### 19.2. Screen reader

Diagnostics, completion và navigation cần label có ý nghĩa, không chỉ dựa vào màu hoặc icon.

### 19.3. Color contrast

Syntax theme cần đủ contrast và không dựa duy nhất vào màu để phân biệt token.

### 19.4. Clear messages

Thông báo lỗi nên dùng ngôn ngữ dễ hiểu, tránh chỉ hiển thị stack trace hoặc internal class name.

### 19.5. Progressive disclosure

Hiển thị thông tin quan trọng trước; chi tiết stack, trace hoặc raw metadata có thể mở rộng khi người dùng cần.

### 19.6. Predictable interaction

Quick fix, formatter và refactoring nên có kết quả có thể dự đoán, có preview khi thay đổi lớn.

## 20. Security của tooling

Tooling có thể đọc source, load plugin, resolve dependency và gọi external service. Nó cần cùng nguyên tắc bảo mật như compiler/runtime.

### 20.1. Untrusted project

Không tự động thực thi build script hoặc plugin từ project không tin cậy chỉ vì người dùng mở folder trong IDE.

### 20.2. Plugin permissions

Plugin cần khai báo quyền và được cấp theo nguyên tắc tối thiểu.

### 20.3. Secret redaction

Diagnostics, logs, hover và debug inspection không được vô tình hiển thị token hoặc credential.

### 20.4. Dependency resolution

Package registry và dependency metadata cần được xác thực. Không để tooling tải và chạy code từ nguồn không tin cậy mà không có policy.

### 20.5. Resource exhaustion

File rất lớn, nesting sâu hoặc expression phức tạp có thể làm language server dùng quá nhiều CPU/memory. Cần limit và cancellation.

### 20.6. Workspace trust

Có thể yêu cầu người dùng xác nhận workspace trước khi bật chức năng có side effect như task execution hoặc plugin activation.

## 21. Testing và quality assurance cho tooling

Tooling cần được kiểm thử ở mức function, protocol và trải nghiệm.

### 21.1. Unit tests

Test lexer, parser, completion ranking, formatter và diagnostic mapping.

### 21.2. Golden tests

Lưu input và expected output cho formatter, diagnostics hoặc generated documentation. Golden update cần được review khi semantics thay đổi.

### 21.3. Protocol tests

Kiểm tra language server request/response, cancellation, document version và lifecycle.

### 21.4. Editor integration tests

Kiểm tra behavior thực tế trong editor được hỗ trợ, bao gồm completion, hover, rename và code action.

### 21.5. Large workspace tests

Test workspace có nhiều file, dependency sâu và thay đổi liên tục để phát hiện vấn đề performance.

### 21.6. Fault injection

Mô phỏng compiler crash, dependency unavailable, file watcher failure và network timeout.

### 21.7. Accessibility tests

Kiểm tra keyboard flow, screen reader label và contrast.

### 21.8. Regression tests

Giữ fixture cho lỗi tooling đã được báo cáo để bảo đảm không tái xuất hiện.

## 22. Metrics đánh giá chất lượng tooling

Chất lượng tooling có thể được theo dõi bằng metrics kỹ thuật và feedback người dùng.

### 22.1. Responsiveness

Theo dõi p50, p95 và p99 latency của completion, hover, diagnostics và formatting.

### 22.2. Reliability

Theo dõi crash rate, request failure, restart và cancellation failure.

### 22.3. Accuracy

Đo tỷ lệ false positive/false negative của diagnostics và completion theo bộ fixture hoặc feedback đã xác minh.

### 22.4. Adoption

Theo dõi mức sử dụng formatter, language server, quick fix và documentation search nếu telemetry được phép thu thập.

### 22.5. User feedback

Theo dõi báo lỗi, thời gian giải quyết issue và các điểm người dùng thường bị mắc kẹt.

### 22.6. Privacy

Telemetry cần thu thập tối thiểu, tránh gửi source code hoặc identifier nhạy cảm nếu không có consent và policy rõ.

## 23. Trade-off trong thiết kế tooling

Tooling tốt cần cân bằng độ chính xác, tốc độ, tính năng và chi phí bảo trì.

### 23.1. Parser chính xác và parser tolerant

Parser strict phù hợp compiler. Parser tolerant phù hợp editor đang có source chưa hoàn chỉnh. Có thể dùng chung grammar nhưng khác recovery strategy.

### 23.2. Full analysis và incremental analysis

Full analysis đơn giản và dễ đảm bảo consistency. Incremental analysis nhanh hơn ở project lớn nhưng phức tạp về invalidation và stale result.

### 23.3. Local và remote language service

Local server giảm network dependency và bảo vệ source khỏi gửi ra ngoài. Remote service có thể chia sẻ index hoặc compute, nhưng tăng yêu cầu về privacy, latency và availability.

### 23.4. Rich diagnostics và noise

Nhiều cảnh báo có thể hữu ích nhưng cũng làm người dùng bỏ qua diagnostics. Chọn severity và suppression policy rõ.

### 23.5. Configurability và consistency

Quá nhiều option formatter hoặc linter khiến project khó thống nhất. Một default tốt và số override hạn chế thường dễ quản trị hơn.

### 23.6. Plugin extensibility và safety

Plugin tăng khả năng mở rộng nhưng tạo trust boundary, compatibility và support cost.

### 23.7. Feature breadth và maintainability

Thêm debugger, refactoring hoặc semantic index có chi phí lớn. Ưu tiên theo nhu cầu người dùng và mức ảnh hưởng đến workflow.

## 24. Ví dụ end-to-end: diagnostics trong IDE

Người dùng viết cấu hình:

~~~text
service "catalog" {
    port = "eighty"
    timeout = 5s
}
~~~

Một chuỗi tooling có thể hoạt động như sau:

1. Syntax highlighter nhận diện block service, string literal và duration literal.
2. Language server nhận text document version mới.
3. Frontend parse source thành AST.
4. Semantic analyzer xác định port yêu cầu Integer.
5. Analyzer phát diagnostic tại string literal.
6. IDE hiển thị lỗi cùng message và source range.
7. Completion hoặc quick fix có thể gợi ý giá trị số hợp lệ.
8. Khi người dùng sửa thành 8080, server phân tích lại document và xóa diagnostic cũ.

Diagnostic mẫu:

~~~text
DSL-TYPE-004:
Expected Integer for property 'port', found String.
~~~

Điểm quan trọng là IDE và CLI cần dùng cùng type rule. Nếu IDE không báo lỗi nhưng CLI từ chối source, người dùng phải đối mặt với hai cách hiểu khác nhau.

## 25. Ví dụ formatter và format check

Input:

~~~text
service "catalog"{port=8080
timeout=5s}
~~~

Formatted output:

~~~text
service "catalog" {
    port = 8080
    timeout = 5s
}
~~~

Formatter nên tạo output xác định và giữ nguyên semantics. CI có thể chạy:

~~~bash
dsl format --check .
~~~

Nếu file chưa theo format chuẩn, command trả exit code khác 0 và chỉ rõ file cần cập nhật. Nó không nên tự sửa file trong check-only mode.

## 26. Ví dụ completion theo context

Trong block:

~~~text
endpoint "catalog" {
    |
}
~~~

Tool có thể gợi ý:

- scheme
- hostname
- port
- basePath
- tls
- timeout

Trong expression:

~~~text
if customer.
~~~

Tool nên gợi ý field của type Customer theo semantic model. Nó không nên gợi ý mọi symbol trong workspace nếu chúng không nằm trong scope.

## 27. Ví dụ architecture cho tooling

Một thiết kế có thể chia:

~~~text
Editor
  |
  v
Language Server
  |
  +----> Document Manager
  |
  +----> Workspace Index
  |
  +----> Language Core
             |
             +----> Lexer / Parser
             |
             +----> Semantic Analyzer
             |
             +----> Formatter
             |
             +----> Documentation Registry
~~~

CLI có thể dùng chung Language Core:

~~~text
CLI
 |
 v
Language Core
~~~

Nhờ dùng chung core, parser, diagnostics và semantic rules nhất quán giữa editor và CI.

## 28. Quy trình phát triển tooling

Một quy trình thực tế có thể gồm:

1. Thu thập workflow và pain point của người dùng DSL.
2. Chọn capability có tác động lớn nhất.
3. Xác định language core API dùng chung.
4. Định nghĩa protocol và document lifecycle.
5. Xây dựng diagnostics và source mapping trước các tính năng nâng cao.
6. Thêm completion, hover và navigation.
7. Thêm formatter, linter và code action.
8. Đo latency và memory trên workspace đại diện.
9. Kiểm tra compatibility với editor và DSL version.
10. Thu thập feedback và cải thiện theo dữ liệu.

### 28.1. Start with diagnostics

Diagnostics chính xác thường tạo giá trị lớn vì giúp người dùng phát hiện lỗi sớm.

### 28.2. Reuse before duplicate

Trước khi tạo parser hoặc type checker riêng cho tooling, kiểm tra xem compiler core có thể cung cấp service phù hợp không.

### 28.3. Optimize measured bottlenecks

Đo request latency và allocation trước khi tối ưu. Completion chậm có thể do workspace indexing chứ không phải parser.

### 28.4. Ship incrementally

Có thể phát hành từng nhóm tính năng để giảm rủi ro và nhận feedback sớm.

## 29. Anti-patterns trong tooling

**IDE parser khác compiler parser.** Hai công cụ có thể chấp nhận syntax khác nhau và tạo lỗi chỉ xuất hiện khi build.

**Dùng regex cho mọi semantic task.** Regex phù hợp lexical hint đơn giản nhưng không thay thế parser và symbol resolver.

**Full workspace analysis trên mỗi phím gõ.** Điều này làm editor lag khi project lớn.

**Không hủy request cũ.** Kết quả diagnostics cũ có thể ghi đè kết quả mới và tiếp tục tiêu tốn tài nguyên.

**Diagnostic message chỉ có internal exception.** Người dùng không biết phải sửa gì.

**Formatter không idempotent.** File thay đổi ở mỗi lần format và tạo diff nhiễu.

**Rename bằng text replacement.** Tool có thể đổi nhầm string literal hoặc symbol trùng tên ở scope khác.

**Quick fix không có preview cho thay đổi lớn.** Người dùng khó biết tool sẽ sửa những file nào.

**Language server ghi log vào protocol channel.** Output debug có thể làm hỏng message framing.

**Không version hóa schema output.** CI và plugin có thể bị hỏng khi structured diagnostics thay đổi.

**Bỏ qua accessibility.** Tool chỉ dùng được bằng mouse hoặc màu sắc có thể loại trừ người dùng.

**Thu thập source telemetry quá mức.** Điều này tạo rủi ro riêng tư và làm giảm niềm tin.

**Quá nhiều formatter option.** Mỗi project tạo một style riêng và làm tăng chi phí hỗ trợ.

## 30. Nguyên tắc xây dựng tooling chất lượng

1. Dùng chung grammar và semantic core với compiler.
2. Coi diagnostics là API có cấu trúc, không chỉ là text.
3. Giữ source span và document version qua mọi bước.
4. Hỗ trợ incomplete source và error recovery.
5. Dùng incremental analysis, cancellation và stale-result protection.
6. Completion phải context-aware, scope-aware và type-aware.
7. Formatter phải deterministic, idempotent và bảo toàn semantics.
8. Refactoring phải dựa trên symbol identity.
9. Debugger cần source mapping và execution metadata.
10. CLI cần exit code và machine-readable output ổn định.
11. Tách secret và dữ liệu nhạy cảm khỏi diagnostics, logs và telemetry.
12. Kiểm thử protocol, large workspace, compatibility và accessibility.
13. Theo dõi latency, reliability, accuracy và feedback.
14. Cân bằng feature breadth với chi phí bảo trì.

## 31. Ghi nhớ

- Tooling gồm CLI, IDE, language server, formatter, linter, debugger, documentation và build integration.
- Chất lượng tooling được đánh giá qua correctness, responsiveness, consistency, reliability, compatibility, accessibility và maintainability.
- CLI cần command rõ, exit code ổn định, structured output và behavior offline có thể dự đoán.
- Syntax highlighting nên dùng lexer/grammar phù hợp và hỗ trợ source chưa hoàn chỉnh.
- Language server cần quản lý document lifecycle, incremental update, cancellation và workspace index.
- Completion phải dựa trên context, type và scope.
- Diagnostics cần source range chính xác, message có thể hành động và error code ổn định.
- Formatter cần deterministic, idempotent và giữ semantics.
- Linter và static analysis cần severity, suppression và kiểm soát false positive.
- Refactoring phải dựa trên symbol identity và có preview khi thay đổi lớn.
- Debugger cần breakpoint, source map, variable inspection và execution trace.
- Shared language core giúp CLI, IDE và compiler hiểu DSL nhất quán.
- Tooling cần đo performance, kiểm tra compatibility, bảo mật workspace và hỗ trợ accessibility.
- Thiết kế tooling là một chuỗi trade-off giữa độ chính xác, tốc độ, tính năng và chi phí bảo trì.

## 32. Câu hỏi tự kiểm tra

1. Tooling của DSL gồm những công cụ nào và chúng hỗ trợ giai đoạn nào của vòng đời phát triển?
2. Những chiều chất lượng tooling quan trọng là gì?
3. Vì sao CLI cần exit code và structured output ổn định?
4. Syntax highlighting nên dùng lexer hay regex? Vì sao?
5. Language server cần quản lý document version và cancellation như thế nào?
6. Completion context-aware, type-aware và scope-aware khác nhau ra sao?
7. Một diagnostic hữu ích nên có những trường nào?
8. Formatter cần bảo đảm deterministic, idempotence và semantics preservation như thế nào?
9. Linter khác compiler type checker ở mục tiêu nào?
10. Vì sao rename symbol không thể chỉ là text replacement?
11. Source map giúp debugger làm gì khi DSL được compile sang IR hoặc bytecode?
12. Documentation tooling có thể dùng chung metadata với IDE ra sao?
13. Incremental analysis và project indexing giúp workspace lớn phản hồi nhanh như thế nào?
14. Những rủi ro bảo mật nào xuất hiện khi mở project hoặc plugin không tin cậy?
15. Nên đo những metrics nào để đánh giá responsiveness và reliability?
16. Phân tích trade-off giữa parser strict và parser tolerant.
17. Hãy thiết kế luồng diagnostics từ parser đến IDE khi một field có sai type.
18. Hãy đề xuất kiến trúc tooling dùng chung language core cho CLI, IDE và CI.
