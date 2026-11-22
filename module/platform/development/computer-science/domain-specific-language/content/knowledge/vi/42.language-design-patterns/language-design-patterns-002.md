# Thiết kế phân tầng

**Thiết kế phân tầng** (*layered design*) là cách tổ chức một hệ thống thành các lớp có trách nhiệm riêng, trong đó mỗi lớp cung cấp dịch vụ cho lớp phía trên thông qua một contract rõ ràng. Với một ngôn ngữ đặc tả miền (*Domain Specific Language – DSL*), thiết kế phân tầng giúp tách cú pháp, phân tích, kiểm tra ngữ nghĩa, biểu diễn chương trình, thực thi và tích hợp với hệ thống chủ.

Một DSL có thể bắt đầu từ parser đơn giản và phát triển thành compiler, runtime, plugin system, editor tooling và deployment integration. Nếu mọi chức năng được đặt trong một thành phần duy nhất, thay đổi grammar có thể ảnh hưởng execution engine, thay đổi host API có thể làm hỏng parser và việc kiểm thử từng phần trở nên khó khăn.

Một kiến trúc phân tầng điển hình:

~~~text
User / IDE / CLI
       |
       v
Presentation and Tooling
       |
       v
Language Frontend
  Lexer -> Parser -> AST
       |
       v
Semantic Analysis
       |
       v
Intermediate Representation
       |
       v
Execution / Code Generation
       |
       v
Runtime Services
       |
       v
Domain Adapters / Host APIs
       |
       v
External Systems
~~~

Đây là mô hình khái niệm. Một DSL nhỏ có thể gộp một số lớp; một compiler lớn có thể chia mỗi lớp thành nhiều module. Mục tiêu là giữ trách nhiệm, dependency và contract đủ rõ để từng phần có thể thay đổi, kiểm thử và mở rộng độc lập.

## 1. Vì sao cần thiết kế phân tầng?

DSL thường kết hợp nhiều loại công việc khác nhau:

- Đọc source text và nhận diện token.
- Parse token thành cấu trúc cú pháp.
- Kiểm tra tên, type, scope và constraint.
- Chuyển chương trình sang representation phù hợp.
- Tối ưu hoặc tạo execution plan.
- Thực thi logic và quản lý state.
- Gọi API của host application.
- Hiển thị diagnostics, completion và documentation.

Những công việc này có vòng đời và yêu cầu kỹ thuật khác nhau. Thiết kế phân tầng giúp giảm coupling giữa parser, compiler và runtime; giữ grammar độc lập với chi tiết thực thi; thay execution engine mà không phải viết lại language frontend; tái sử dụng semantic model trong IDE và command-line tooling; kiểm thử từng lớp với input/output xác định; cô lập dependency bên ngoài qua adapter; quản lý version và compatibility rõ ràng; hạn chế thay đổi lan truyền khi thêm feature.

### 1.1. Separation of concerns

Mỗi lớp nên giải quyết một nhóm vấn đề. Parser quan tâm source có đúng grammar không; semantic analyzer quan tâm chương trình có ý nghĩa hợp lệ không; runtime quan tâm cách thực hiện chương trình đã được kiểm tra.

### 1.2. Independent evolution

Grammar có thể thêm cú pháp mới trong khi giữ nguyên semantics. Runtime có thể thay đổi cách tối ưu execution mà không đổi syntax. Adapter có thể hỗ trợ host API mới mà không cần sửa parser.

### 1.3. Testability

Khi contract rõ, có thể test parser bằng source và AST, test semantic analyzer bằng AST và symbol environment, test executor bằng IR và runtime context.

### 1.4. Team ownership

Các nhóm có thể chịu trách nhiệm cho language frontend, runtime, domain integration hoặc developer tooling mà không phải sửa cùng một khối code.

## 2. Layer, module và component

Layer, module và component có liên quan nhưng không đồng nghĩa.

| Khái niệm | Ý nghĩa |
|---|---|
| Layer | Nhóm trách nhiệm ở một mức kiến trúc |
| Module | Đơn vị tổ chức source code, package hoặc namespace |
| Component | Đơn vị có contract và hành vi tương đối độc lập |
| Service | Chức năng được cung cấp qua interface |
| Adapter | Thành phần chuyển đổi giữa contract nội bộ và hệ thống bên ngoài |

Một layer có thể gồm nhiều module và component. Một module không nên tùy tiện truy cập mọi module của layer khác chỉ vì chúng nằm trong cùng repository.

### 2.1. Logical layer và physical module

Logical layer mô tả trách nhiệm. Physical module là cách trách nhiệm đó được đóng gói trong project. Một layer có thể được triển khai trong một module hoặc nhiều package.

### 2.2. Layer boundary

Boundary là ranh giới nơi dữ liệu và control flow đi qua một contract. Boundary tốt giảm việc lớp này biết chi tiết nội bộ của lớp khác.

### 2.3. Public API và internal implementation

Mỗi module nên công bố phần API cần thiết cho consumer. Các class helper, cache hoặc internal representation không cần trở thành public.

### 2.4. Dependency direction

Quy tắc phụ thuộc xác định lớp nào được gọi lớp nào. Nếu dependency direction không rõ, các lớp có thể tạo vòng phụ thuộc và khó thay thế.

## 3. Các tầng chính của DSL

Một kiến trúc DSL có thể chia thành những tầng sau:

| Tầng | Trách nhiệm |
|---|---|
| Presentation | CLI, IDE, editor, diagnostics view |
| Language frontend | Lexer, parser, syntax tree |
| Semantic analysis | Name resolution, type checking, validation |
| Intermediate representation | Mô hình chương trình đã chuẩn hóa |
| Optimization | Simplification, planning, specialization |
| Execution | Interpreter, VM hoặc code generator |
| Runtime services | Context, state, scheduling, resource management |
| Domain integration | Adapter và host API |
| Infrastructure | File, network, storage, telemetry, secrets |

Không bắt buộc phải có một module riêng cho từng dòng. Điều quan trọng là các trách nhiệm và dependency được phân định.

## 4. Presentation và tooling layer

Presentation layer cung cấp cách người dùng tương tác với DSL. Nó không nên chứa grammar hoặc business semantics riêng.

Các thành phần thường gặp:

- Command-line interface.
- IDE plugin.
- Language server.
- Editor integration.
- Documentation browser.
- Configuration UI.
- Debugger và execution inspector.

### 4.1. Command-line interface

CLI nhận command, option và file path, sau đó gọi service tương ứng của compiler hoặc runtime.

~~~text
dsl parse workflow.dsl
dsl check workflow.dsl
dsl run workflow.dsl
dsl explain workflow.dsl
~~~

CLI không nên tự parse grammar theo một cách riêng. Nó nên gọi cùng language frontend được dùng bởi IDE hoặc build tool.

### 4.2. Language server

Language server cung cấp diagnostics, completion, hover, symbol navigation và formatting. Nó có thể tái sử dụng parser và semantic model.

### 4.3. Diagnostics presentation

Core layer tạo diagnostic có source span, code và message. Presentation layer quyết định hiển thị thành terminal text, editor underline hoặc report.

### 4.4. Debugger

Debugger dùng execution metadata để hiển thị breakpoint, variable, call stack và current instruction. Debug UI không nên tự quyết định semantics của runtime.

### 4.5. Dependency rule

Presentation layer được phụ thuộc vào public API của core. Core không nên phụ thuộc CLI hoặc IDE framework.

## 5. Language frontend layer

Language frontend chuyển source text thành cấu trúc chương trình mà các tầng sau có thể xử lý.

~~~text
Source text
    |
    v
Lexer
    |
    v
Token stream
    |
    v
Parser
    |
    v
AST
~~~

### 5.1. Lexer

Lexer nhận diện identifier, keyword, literal, operator, delimiter và comment. Nó quản lý source position để parser và diagnostics có thể trỏ đến đúng vị trí.

### 5.2. Parser

Parser áp dụng grammar để tạo abstract syntax tree. Parser nên tập trung vào cấu trúc cú pháp và không gọi host service hoặc thực thi expression.

### 5.3. Abstract syntax tree

AST biểu diễn cấu trúc chương trình theo node có kiểu:

~~~text
IfStatement
├── Condition
├── ThenBlock
└── ElseBlock
~~~

AST nên giữ đủ source span và node identity để phục vụ semantic analysis, diagnostics và tooling.

### 5.4. Error recovery

Parser có thể cố gắng tiếp tục sau lỗi để báo nhiều diagnostic trong một lần. Recovery cần tránh tạo AST giả khiến semantic layer báo thêm hàng loạt lỗi khó hiểu.

### 5.5. Grammar ownership

Grammar là contract của ngôn ngữ. Syntax change cần được versioning và cập nhật tài liệu.

### 5.6. Frontend independence

Parser có thể thay implementation hoặc grammar notation miễn là output AST contract được giữ hoặc được version hóa rõ.

## 6. Semantic analysis layer

Một chương trình parse thành công chưa chắc hợp lệ. Semantic analysis kiểm tra ý nghĩa và các ràng buộc ngoài grammar.

Các nhiệm vụ phổ biến:

- Name resolution.
- Scope analysis.
- Type checking.
- Overload resolution.
- Constant validation.
- Access control.
- Constraint checking.
- Dependency resolution.
- Import resolution.

### 6.1. Name resolution

Resolve identifier đến declaration, symbol hoặc host binding tương ứng.

### 6.2. Scope analysis

Kiểm tra biến có tồn tại trong scope hiện tại, shadowing có hợp lệ và visibility có được tuân thủ không.

### 6.3. Type checking

Kiểm tra type của expression, parameter, return value và assignment.

### 6.4. Constraint validation

Kiểm tra điều kiện như range, uniqueness, cardinality hoặc quan hệ giữa nhiều field.

### 6.5. Symbol table

Symbol table lưu declaration và metadata để name resolution, type checking và tooling dùng chung.

### 6.6. Semantic model

Semantic model có thể chứa symbol đã resolve, inferred type, constant value và diagnostics. Nó thường giàu thông tin hơn AST thuần cú pháp.

### 6.7. Không thực thi trong semantic analysis

Semantic analysis nên kiểm tra tính hợp lệ. Nếu cần giá trị phụ thuộc runtime hoặc external service, nên biểu diễn dependency thay vì thực thi side effect lúc compile.

## 7. Intermediate representation layer

Intermediate representation (IR) là mô hình trung gian giữa language frontend và execution/code generation.

### 7.1. Vì sao cần IR?

AST phản ánh syntax. IR phản ánh operations hoặc semantics cần thiết cho execution. IR giúp nhiều syntax khác nhau được chuẩn hóa thành cùng một representation.

### 7.2. AST và IR

| AST | IR |
|---|---|
| Gần với source syntax | Gần với computation |
| Có node theo grammar | Có operation chuẩn hóa |
| Phù hợp diagnostics và tooling | Phù hợp optimization và execution |
| Có thể giữ sugar syntax | Thường đã desugar |

### 7.3. Desugaring

Syntax sugar có thể được chuyển thành construct cơ bản:

~~~text
when condition then action
~~~

Có thể được chuyển thành conditional IR tương đương.

### 7.4. Typed IR

Typed IR gắn type vào value và operation. Điều này giúp optimizer và code generator chọn operation phù hợp.

### 7.5. Source mapping

IR nên giữ source mapping để runtime error hoặc debugger có thể trỏ về dòng DSL gốc.

### 7.6. IR stability

IR là contract giữa frontend và backend. Nếu nhiều backend cùng dùng, thay đổi IR cần có compatibility hoặc migration plan.

## 8. Optimization layer

Optimization cải thiện execution plan hoặc generated code mà vẫn giữ semantics.

### 8.1. Constant folding

Tính biểu thức hằng số trước runtime.

### 8.2. Dead code elimination

Loại bỏ nhánh không thể chạy khi compiler chứng minh an toàn.

### 8.3. Common subexpression elimination

Tái sử dụng kết quả của biểu thức thuần có cùng input.

### 8.4. Inlining

Thay function call bằng body đã mở rộng khi phù hợp. Inlining có thể giảm call overhead nhưng tăng code size.

### 8.5. Query planning

Với query DSL, optimizer chọn operator, join strategy, filter pushdown và index.

### 8.6. Optimization correctness

Optimizer cần bảo toàn evaluation order, side effect, exception và precision theo semantics DSL.

### 8.7. Optimization boundary

Optimization nên nhận IR và trả IR đã tối ưu. Không nên sửa AST gốc theo cách khiến tooling mất source structure.

## 9. Execution và code generation layer

Execution layer biến IR thành hành vi thực thi.

Các lựa chọn:

- Tree-walking interpreter.
- Bytecode compiler và virtual machine.
- Native code generator.
- Source-to-source compiler.
- Query execution engine.
- Workflow scheduler.

### 9.1. Interpreter

Interpreter đánh giá node hoặc instruction. Nó có thể phù hợp DSL cần linh hoạt và thời gian compile thấp.

### 9.2. Bytecode VM

VM thực thi instruction đã chuẩn hóa. Nó có thể cache compiled program và hỗ trợ nhiều runtime backend.

### 9.3. Native backend

Native backend tạo machine code hoặc source code cho compiler bên ngoài. Nó có thể cải thiện throughput nhưng tăng chi phí build và debugging.

### 9.4. Execution plan

Query hoặc workflow DSL có thể tạo plan gồm operator/task thay vì thực thi trực tiếp AST.

### 9.5. Execution result

Execution layer nên trả kết quả hoặc error theo contract rõ. Presentation layer sẽ quyết định hiển thị; domain adapter sẽ chuyển đổi kết quả nếu cần.

### 9.6. Backend independence

Nếu IR ổn định, có thể thay interpreter bằng VM hoặc thêm backend mới mà không cần thay parser.

## 10. Runtime services layer

Runtime services cung cấp hạ tầng dùng chung cho execution engine.

Thành phần có thể gồm:

- Execution context.
- Variable environment.
- State store.
- Scheduler.
- Cancellation.
- Resource manager.
- Clock và random provider.
- Logging và tracing.
- Quota và execution budget.

### 10.1. Execution context

Context chứa dữ liệu của một lần chạy như variables, tenant identity, deadline, correlation ID và capability.

### 10.2. State management

State service quản lý mutable state, transaction hoặc persistence theo semantics của DSL.

### 10.3. Scheduler

Scheduler lập lịch task, parallel execution và timer. Nó không nên phụ thuộc cú pháp cụ thể của một DSL statement.

### 10.4. Cancellation

Cancellation truyền yêu cầu dừng qua execution, host call và asynchronous task.

### 10.5. Resource management

Runtime quản lý lifetime của connection, stream, file, transaction và temporary buffer.

### 10.6. Observability

Logging, metrics và tracing cần có abstraction để runtime dùng được nhiều telemetry backend.

## 11. Domain integration và adapter layer

DSL thường mô hình hóa một miền nghiệp vụ nhưng cần gọi hệ thống hiện có. Adapter chuyển đổi giữa domain model của DSL và contract của host application.

### 11.1. Domain service

Domain service cung cấp operation có ý nghĩa nghiệp vụ như calculatePrice, approveOrder hoặc reserveInventory.

### 11.2. Adapter

Adapter chuyển input DSL thành host type, gọi host API và chuyển output hoặc error trở lại DSL.

### 11.3. Anti-corruption layer

Anti-corruption layer ngăn model của hệ thống ngoài lan vào core domain model. Nó ánh xạ tên, type và error theo semantics của DSL.

### 11.4. Port and adapter

Core định nghĩa port hoặc interface. Adapter cụ thể triển khai interface đó cho database, HTTP service hoặc host application.

### 11.5. Permission boundary

Adapter kiểm tra capability và quyền cần thiết trước khi thực hiện host operation.

### 11.6. External failure

Adapter chuyển timeout, network failure hoặc host exception thành error model nhất quán mà DSL runtime hiểu được.

## 12. Infrastructure layer

Infrastructure chứa chi tiết kỹ thuật như filesystem, network client, database driver, secret store và telemetry exporter.

### 12.1. Infrastructure abstraction

Core nên dùng interface hoặc port, không phụ thuộc trực tiếp một database driver hay HTTP library.

### 12.2. Configuration

Infrastructure nhận cấu hình từ composition root hoặc host application. Không tự đọc global environment ở mọi module nếu điều đó làm khó kiểm thử.

### 12.3. Secret management

Credential được resolve từ secret provider và chỉ truyền đến thành phần cần sử dụng.

### 12.4. Observability backend

Có thể thay logging hoặc metrics provider mà không sửa language frontend.

### 12.5. Failure isolation

Infrastructure adapter cần timeout, retry và circuit breaker phù hợp để lỗi hệ thống ngoài không làm runtime mất kiểm soát.

## 13. Dependency direction

Thiết kế phân tầng cần quy định chiều phụ thuộc. Một nguyên tắc thường dùng là policy và domain model ở phía trong; framework và infrastructure ở phía ngoài.

~~~text
Presentation
     |
     v
Application services
     |
     v
Core language and domain
     ^
     |
Ports / interfaces
     ^
     |
Infrastructure adapters
~~~

Sơ đồ thể hiện adapter bên ngoài triển khai port do core định nghĩa. Chi tiết framework không nên được import ngược vào core.

### 13.1. Dependency rule

Lớp phía trong không nên biết lớp phía ngoài. Core có thể định nghĩa interface cho persistence hoặc host function; infrastructure cung cấp implementation.

### 13.2. Compile-time dependency

Dependency direction có thể được kiểm soát qua module graph và visibility. Build system có thể cấm module core import package presentation hoặc infrastructure implementation.

### 13.3. Runtime dependency

Runtime dependency có thể được cung cấp qua constructor injection, registry hoặc composition root. Không nên dùng global service locator ở mọi nơi nếu nó làm dependencies ẩn.

### 13.4. Circular dependency

Vòng phụ thuộc giữa module thường cho thấy trách nhiệm chưa được phân tách tốt. Có thể tách interface vào module core hoặc tạo module contract dùng chung.

### 13.5. Dependency inversion

Module cấp cao định nghĩa abstraction mà nó cần. Module cấp thấp triển khai abstraction đó. Điều này giúp thay database, HTTP client hoặc host API mà không thay business logic.

## 14. Contract giữa các layer

Layer boundary cần contract rõ về input, output, error, lifecycle và ownership.

### 14.1. Data contract

Ví dụ parser trả ParseResult gồm AST và diagnostics. Semantic analyzer nhận AST cùng compilation context và trả SemanticModel.

~~~text
parse(source) -> ParseResult
analyze(parseResult.ast, context) -> SemanticResult
lower(semanticModel) -> IRModule
execute(irModule, runtimeContext) -> ExecutionResult
~~~

### 14.2. Error contract

Mỗi layer nên có cách biểu diễn lỗi nhất quán. Parser error khác type error, runtime error và infrastructure error.

### 14.3. Source location

Source span cần được giữ qua các layer để diagnostics, debugger và trace có thể liên kết về source.

### 14.4. Versioned contract

Nếu layer được phát triển hoặc deploy độc lập, contract cần versioning. Nếu cùng một process và repository, vẫn cần kiểm soát API compatibility giữa module.

### 14.5. Ownership và mutability

Contract cần nói object được chia sẻ hay chuyển ownership, có immutable không và ai được phép thay đổi state.

## 15. Composition root và dependency injection

Composition root là nơi ứng dụng tạo object graph và nối các implementation vào interface.

Ví dụ:

~~~text
application startup {
    parser = createParser(grammar)
    analyzer = createSemanticAnalyzer(symbolRegistry)
    executor = createExecutor(runtimeServices)
    hostAdapter = createCatalogAdapter(httpClient)

    runtime = createRuntime(executor, hostAdapter)
    cli = createCli(parser, analyzer, runtime)
}
~~~

### 15.1. Constructor injection

Dependency được truyền qua constructor giúp module khai báo rõ những gì nó cần.

### 15.2. Interface binding

Composition root chọn implementation cụ thể cho interface như Clock, FileStore, SecretProvider hoặc DomainPort.

### 15.3. Environment-specific wiring

Development có thể dùng in-memory adapter; production dùng database hoặc remote service adapter. Core logic vẫn dùng cùng interface.

### 15.4. Avoid service locator sprawl

Một global registry giúp truy cập nhanh nhưng làm dependencies ẩn và khó biết lifecycle. Nếu dùng registry, nên giới hạn ở composition hoặc plugin boundary.

### 15.5. Lifecycle management

Composition root chịu trách nhiệm start và dispose các resource như thread pool, connection pool và telemetry exporter.

## 16. Data flow qua các layer

Một lần compile và execute có thể đi qua các lớp như sau:

~~~text
Source file
   |
   v
Lexer and parser
   |
   v
AST + source spans
   |
   v
Semantic model
   |
   v
Typed IR
   |
   v
Optimized IR
   |
   v
Execution engine
   |
   v
Runtime context
   |
   v
Domain adapter
   |
   v
Host application / external service
~~~

### 16.1. Parse result

Parser tạo AST và syntax diagnostics. Nó không cần biết host database hoặc HTTP endpoint.

### 16.2. Semantic result

Semantic analyzer bổ sung type, symbol binding và validation result.

### 16.3. IR result

Lowering chuyển semantic model sang representation mà backend có thể thực thi.

### 16.4. Execution result

Execution engine trả value, state transition hoặc structured error.

### 16.5. Presentation result

CLI hoặc IDE biến diagnostics và execution result thành output phù hợp với người dùng.

## 17. Error handling xuyên tầng

Lỗi cần được phân loại và chuyển tiếp mà không làm mất ngữ cảnh.

### 17.1. Syntax error

Phát sinh ở lexer/parser, ví dụ token không hợp lệ hoặc thiếu delimiter.

### 17.2. Semantic error

Phát sinh khi name, type, scope hoặc constraint không hợp lệ.

### 17.3. Compilation error

Phát sinh khi lowering, optimization hoặc code generation không thể tạo output hợp lệ.

### 17.4. Runtime error

Phát sinh khi thực thi, ví dụ division by zero, timeout hoặc execution budget exceeded.

### 17.5. Domain error

Adapter hoặc domain service có thể trả lỗi nghiệp vụ như order not eligible. Nó cần được phân biệt với lỗi kỹ thuật.

### 17.6. Infrastructure error

Database unavailable, network timeout hoặc credential failure nên được giữ loại lỗi để caller có thể retry hoặc báo đúng.

### 17.7. Error mapping

Không nên biến mọi exception thành một thông báo chung. Mapping cần giữ error code, source location, correlation ID và cause an toàn.

## 18. Configuration và extension theo layer

Mỗi layer chỉ nên nhận configuration thuộc trách nhiệm của nó.

### 18.1. Frontend configuration

Có thể gồm language version, grammar option, parser limit và import path.

### 18.2. Semantic configuration

Có thể gồm strictness, type inference mode, allowed capability và validation policy.

### 18.3. Execution configuration

Có thể gồm interpreter mode, instruction budget, optimization level và concurrency limit.

### 18.4. Runtime configuration

Có thể gồm scheduler, cache size, timeout, memory quota và telemetry.

### 18.5. Infrastructure configuration

Có thể gồm endpoint, database connection, credential provider và network policy.

### 18.6. Extension point

Extension nên được gắn vào layer phù hợp. Parser extension bổ sung grammar; semantic extension bổ sung type hoặc validation; runtime adapter bổ sung host operation.

### 18.7. Plugin isolation

Plugin không nên truy cập trực tiếp internal state của mọi layer. Dùng extension API có version và capability rõ.

## 19. Các kiểu kiến trúc phân tầng

Không có một sơ đồ phân tầng duy nhất phù hợp cho mọi DSL. Có thể kết hợp layered architecture với hexagonal architecture, clean architecture hoặc compiler pipeline.

### 19.1. Traditional layered architecture

Các lớp được xếp theo trách nhiệm và thường gọi lớp ngay bên dưới:

~~~text
Presentation
    |
Application
    |
Domain
    |
Infrastructure
~~~

Mô hình này dễ hiểu và phù hợp hệ thống vừa phải. Cần tránh để domain phụ thuộc trực tiếp infrastructure nếu muốn giữ domain độc lập.

### 19.2. Hexagonal architecture

Core nằm ở trung tâm và giao tiếp với bên ngoài qua ports. Adapters triển khai các port đó.

~~~text
        CLI adapter
             |
             v
Database --> Core DSL <-- Host API
             ^
             |
        IDE adapter
~~~

Mô hình này phù hợp DSL có nhiều cách tương tác hoặc nhiều backend.

### 19.3. Clean architecture

Các policy ở trong không phụ thuộc framework ở ngoài. Dependency inversion giúp domain và application logic không bị ràng buộc với database, web framework hoặc UI.

### 19.4. Compiler pipeline

Compiler pipeline mô hình hóa các bước chuyển đổi liên tiếp:

~~~text
Source
  |
  v
AST
  |
  v
Typed AST
  |
  v
IR
  |
  v
Optimized IR
  |
  v
Backend output
~~~

Pipeline đặc biệt phù hợp language frontend và code generation.

### 19.5. Chọn và kết hợp mô hình

Có thể dùng compiler pipeline bên trong core, hexagonal boundary cho host integration và layered presentation cho CLI/IDE. Kiến trúc nên phản ánh dependency thực tế thay vì ép mọi thành phần vào một sơ đồ duy nhất.

## 20. Modularization và package structure

Layer chỉ hữu ích khi source code được tổ chức để phản ánh boundary.

Ví dụ cấu trúc module:

~~~text
dsl-platform/
├── language-api/
├── language-frontend/
├── semantic/
├── ir/
├── optimizer/
├── execution/
├── runtime-core/
├── domain-adapters/
├── infrastructure/
├── cli/
└── ide-support/
~~~

### 20.1. Cohesion

Một module nên tập trung vào một nhóm trách nhiệm có liên quan. Các thành phần thường thay đổi cùng nhau có thể thuộc cùng module.

### 20.2. Coupling

Giảm coupling bằng interface, immutable model và data contract. Tránh import internal class xuyên module.

### 20.3. API surface

Public API càng nhỏ càng dễ bảo trì. Chỉ export type và service cần thiết cho consumer.

### 20.4. Package by layer hay package by feature

Package by layer nhóm code theo kỹ thuật như parser, runtime và adapter. Package by feature nhóm code theo domain như order, pricing hoặc inventory.

Một hệ thống có thể dùng package by layer cho compiler core và package by feature cho domain module.

### 20.5. Module ownership

Mỗi module nên có owner, README hoặc API documentation và quy tắc thay đổi contract.

## 21. Cross-cutting concerns

Một số chức năng đi qua nhiều layer nhưng không nên bị triển khai rải rác.

### 21.1. Logging

Core có thể phát structured event qua logging abstraction. Adapter chọn logger cụ thể.

### 21.2. Metrics

Metric name và semantic nên ổn định. Backend exporter thuộc infrastructure.

### 21.3. Tracing

Correlation ID và trace context cần được truyền qua parse, compile, execution và host calls khi cần điều tra.

### 21.4. Security

Authentication có thể nằm ở presentation hoặc host boundary; authorization và capability cần được kiểm tra tại nơi thực hiện hành động.

### 21.5. Validation

Validation có thể xuất hiện ở syntax, semantic, configuration và runtime. Mỗi tầng kiểm tra điều kiện phù hợp với thông tin nó sở hữu.

### 21.6. Caching

Cache nên có owner và scope rõ: parse cache, compiled program cache, metadata cache hoặc domain cache. Tránh một global cache không rõ invalidation.

### 21.7. Localization

Core nên tạo diagnostic code và structured arguments; presentation layer chọn ngôn ngữ và render message.

## 22. Testing theo layer

Thiết kế phân tầng tạo điều kiện kiểm thử từng phần và kiểm tra contract giữa các phần.

### 22.1. Lexer test

Kiểm tra token, literal, comment, source position và lỗi lexical.

### 22.2. Parser test

Kiểm tra source hợp lệ tạo AST mong đợi; source sai tạo diagnostics phù hợp.

### 22.3. Semantic test

Dùng AST hoặc source fixture để kiểm tra type, scope, resolution và constraint.

### 22.4. IR test

Kiểm tra lowering tạo đúng operation và source mapping.

### 22.5. Optimizer test

So sánh semantics trước/sau optimization, bao gồm side effect và error behavior.

### 22.6. Execution test

Chạy IR với runtime context được kiểm soát và kiểm tra result, state transition hoặc error.

### 22.7. Adapter contract test

Kiểm tra adapter thực hiện đúng interface, chuyển đổi type và mapping lỗi.

### 22.8. Integration test

Kiểm tra toàn bộ luồng từ source đến host API với dependency test hoặc sandbox.

### 22.9. Architecture test

Có thể kiểm tra module dependency để ngăn presentation import infrastructure implementation hoặc core phụ thuộc framework.

## 23. Ví dụ end-to-end: DSL xử lý đơn hàng

Giả sử DSL mô tả workflow xử lý đơn:

~~~text
workflow ApproveOrder {
    input order: Order

    validate order

    if order.total >= 1000 {
        requireApproval("manager")
    }

    reserveInventory(order)
    createShipment(order)
}
~~~

Một kiến trúc phân tầng xử lý chương trình này:

### 23.1. Presentation

CLI hoặc IDE nhận file workflow và hiển thị diagnostics.

### 23.2. Frontend

Lexer và parser chuyển source thành AST gồm workflow, validate, if và function call.

### 23.3. Semantic analysis

Analyzer kiểm tra Order type, field total, function signature và quyền gọi reserveInventory.

### 23.4. IR

Workflow được hạ thành sequence operation, branch và host call đã resolve.

### 23.5. Execution

Runtime đánh giá điều kiện và điều phối từng bước theo workflow semantics.

### 23.6. Domain adapter

Adapter gọi order service, inventory service và shipping service.

### 23.7. Infrastructure

HTTP client, database, credentials, logging và tracing được cung cấp qua infrastructure adapter.

### 23.8. Error path

Nếu inventory service timeout, adapter trả structured error. Runtime áp dụng retry hoặc failure policy. Presentation hiển thị error code cùng source location của call tương ứng.

## 24. Ví dụ contract giữa các module

Một interface semantic analyzer có thể nhận AST và compilation context:

~~~text
interface SemanticAnalyzer {
    analyze(
        ast: ProgramNode,
        context: CompilationContext
    ) -> SemanticResult
}
~~~

Execution backend nhận IR:

~~~text
interface ExecutionBackend {
    execute(
        module: IRModule,
        context: RuntimeContext
    ) -> ExecutionResult
}
~~~

Domain port:

~~~text
interface InventoryPort {
    reserve(orderId: OrderId, items: List<Item>)
        -> ReservationResult
}
~~~

Adapter cụ thể có thể dùng HTTP hoặc database, nhưng DSL runtime chỉ phụ thuộc vào contract InventoryPort.

## 25. Thiết kế phân tầng và versioning

Các layer có thể phát triển với tốc độ khác nhau. Versioning giúp giữ compatibility khi contract thay đổi.

### 25.1. Language version

Version ngôn ngữ xác định grammar và semantics mà source DSL tuân theo.

### 25.2. IR version

Nếu IR được lưu thành artifact hoặc truyền qua process boundary, cần version schema và migration.

### 25.3. Runtime API version

Host binding và extension API cần versioning để plugin biết contract nào được hỗ trợ.

### 25.4. Configuration schema version

Configuration có thể cần migration khi field, default hoặc type thay đổi.

### 25.5. Compatibility adapter

Adapter có thể chuyển contract cũ sang contract mới trong giai đoạn migration, giúp giảm thay đổi đồng thời ở mọi consumer.

### 25.6. Deprecation

API cũ nên được đánh dấu deprecated, cung cấp replacement và có kế hoạch removal rõ ràng.

## 26. Hiệu năng trong kiến trúc phân tầng

Mỗi layer thêm boundary và có thể phát sinh overhead. Phân tầng cần giữ abstraction hữu ích mà không tạo quá nhiều chuyển đổi.

### 26.1. Avoid excessive copying

AST, semantic model và IR có thể chia sẻ immutable metadata hoặc source buffer thay vì copy toàn bộ dữ liệu.

### 26.2. Batch boundary calls

Adapter nên hỗ trợ batch khi host API có thể xử lý nhiều item trong một request.

### 26.3. Cache prepared artifacts

Compiled IR hoặc execution plan có thể được cache theo source và compiler version.

### 26.4. Avoid repeated resolution

Name resolution và host function binding nên được thực hiện trước hot execution path khi có thể.

### 26.5. Profile before flattening

Không gộp các layer chỉ vì dự đoán overhead. Đo latency, allocation và call frequency trước khi thay đổi boundary.

### 26.6. Inline stable hot paths

Một số call nhỏ, ổn định có thể được inline hoặc specialize bởi compiler mà vẫn giữ API layer rõ.

## 27. Security boundary trong kiến trúc phân tầng

Phân tầng có thể giúp cô lập quyền và giảm bề mặt tấn công.

### 27.1. Untrusted source

Source DSL là input không tin cậy nếu người dùng có thể upload hoặc sửa. Parser và semantic analyzer cần giới hạn kích thước, nesting và resource usage.

### 27.2. Capability model

Runtime chỉ cung cấp host operation mà chương trình được phép dùng. Không expose toàn bộ host object graph.

### 27.3. Adapter authorization

Adapter kiểm tra tenant, principal và capability tại điểm thực hiện hành động.

### 27.4. Secret boundary

Secret provider chỉ cấp credential cho adapter cần dùng. Parser, AST và diagnostics không được giữ hoặc in secret.

### 27.5. Resource limits

Execution budget, memory quota, timeout và concurrency limit bảo vệ host application khỏi chương trình tiêu tốn quá nhiều tài nguyên.

### 27.6. Plugin trust

Plugin cần được xác minh nguồn, version và quyền. Không mặc nhiên cho plugin truy cập internal API.

## 28. Khi nào nên gộp hoặc tách layer?

Không phải mọi DSL đều cần nhiều module hoặc nhiều process. Số layer nên phù hợp độ phức tạp và tốc độ thay đổi.

### 28.1. DSL nhỏ

Một DSL cấu hình đơn giản có thể dùng parser, validator và configuration model trong một library. Vẫn nên giữ các interface nội bộ rõ ràng.

### 28.2. DSL có runtime riêng

Khi DSL có state, function call, concurrency hoặc resource management, nên tách language frontend khỏi runtime.

### 28.3. DSL có nhiều host

Nếu cùng language core chạy trên nhiều host application, domain adapter và infrastructure nên được tách khỏi core.

### 28.4. DSL có IDE và tooling

Parser, semantic model và diagnostics cần API tái sử dụng để CLI, IDE và documentation generator dùng chung.

### 28.5. Tách module theo thay đổi

Nếu hai nhóm thành phần thường thay đổi độc lập, có contract ổn định và owner khác nhau, có thể cân nhắc tách module.

### 28.6. Tránh over-layering

Không tạo interface và module cho mọi class nhỏ nếu chúng không tạo boundary có ích. Abstraction không cần thiết làm tăng indirection và khó tìm luồng thực thi.

## 29. Anti-patterns trong thiết kế phân tầng

### 29.1. Big ball of mud

Parser, semantic analysis, runtime và host calls nằm trong một khối code với dependency hai chiều. Thay đổi nhỏ dễ gây regression ở nơi khác.

### 29.2. Layer skipping

Một presentation component gọi thẳng database driver hoặc một parser gọi host API. Điều này bỏ qua boundary và làm trách nhiệm bị trộn.

### 29.3. Leaky abstraction

API của layer trên buộc consumer phải hiểu chi tiết internal implementation của layer dưới. Contract không che được complexity cần che.

### 29.4. Anemic core

Core chỉ chứa data object, còn mọi policy nằm trong infrastructure hoặc presentation. Business semantics trở nên phân tán.

### 29.5. God service

Một service quản lý parser, cache, execution, host integration và diagnostics. Nó có quá nhiều trách nhiệm và trở thành điểm thay đổi tập trung.

### 29.6. Circular imports

Hai module import lẫn nhau khiến build order, testing và deployment khó kiểm soát.

### 29.7. Shared mutable global state

Nhiều layer cùng thay đổi global registry hoặc singleton state. Điều này gây race condition và test order dependency.

### 29.8. Framework leakage

Core model chứa annotation hoặc type phụ thuộc trực tiếp web framework, database driver hoặc IDE SDK.

### 29.9. Duplicate semantics

Parser, CLI và runtime mỗi nơi tự diễn giải một quy tắc. Cùng source có thể được hiểu khác nhau giữa tooling và execution.

### 29.10. Abstraction without contract

Interface không mô tả error, lifecycle, ownership hoặc version. Consumer vẫn phải biết chi tiết implementation.

## 30. Nguyên tắc thiết kế phân tầng

Khi xây dựng DSL, có thể dùng các nguyên tắc sau:

1. Mỗi layer có một nhóm trách nhiệm dễ giải thích.
2. Public contract nhỏ và có kiểu rõ ràng.
3. Dependency direction được quy định và kiểm tra.
4. Core không phụ thuộc framework hoặc infrastructure cụ thể.
5. Parser không thực thi business side effect.
6. Semantic analysis không gọi hệ thống bên ngoài để thực hiện hành động.
7. IR được chuẩn hóa và giữ source mapping.
8. Runtime không phụ thuộc presentation.
9. Host integration đi qua adapter và capability boundary.
10. Error model giữ nguyên source location và cause cần thiết.
11. Configuration và lifecycle được nối ở composition root.
12. Mỗi layer có unit test và contract test phù hợp.
13. Version hóa contract khi consumer có thể cập nhật độc lập.
14. Chỉ tách module khi boundary tạo lợi ích thực tế.
15. Đo hiệu năng trước khi gộp hoặc bỏ abstraction.

## 31. Ví dụ package structure và dependency rule

Một project DSL có thể tổ chức:

~~~text
com.example.dsl
├── api
│   ├── LanguageService
│   ├── CompilationResult
│   └── ExecutionRequest
├── frontend
│   ├── lexer
│   ├── parser
│   └── ast
├── semantic
│   ├── resolver
│   ├── typecheck
│   └── validation
├── ir
│   ├── model
│   └── lowering
├── optimizer
├── runtime
│   ├── interpreter
│   ├── context
│   └── scheduler
├── domain
│   └── ports
├── adapters
│   ├── http
│   └── database
├── infrastructure
└── cli
~~~

Dependency rule khái niệm:

~~~text
cli -> api
api -> frontend, semantic, runtime
frontend -> language model
semantic -> language model
runtime -> ir, domain ports
adapters -> domain ports
infrastructure -> adapters
~~~

Chi tiết thực tế có thể khác. Điều quan trọng là frontend không cần import database adapter và domain port không phụ thuộc implementation cụ thể.

## 32. Quy trình thiết kế kiến trúc phân tầng

Một quy trình có thể thực hiện theo các bước:

1. Xác định use case của DSL và các loại consumer.
2. Liệt kê trách nhiệm từ source parsing đến host integration.
3. Xác định data model đi qua từng giai đoạn.
4. Vẽ dependency graph và chỉ ra boundary.
5. Định nghĩa public contract cho mỗi boundary.
6. Chọn nơi đặt domain policy và infrastructure detail.
7. Thiết kế composition root và lifecycle.
8. Tạo test cho từng layer và contract.
9. Kiểm tra module dependency bằng tooling.
10. Đo performance trên luồng thực tế.
11. Điều chỉnh số layer theo thay đổi và chi phí vận hành.

### 32.1. Bắt đầu từ luồng dữ liệu

Theo dõi một DSL file từ source đến kết quả thường giúp phát hiện boundary tự nhiên hơn là bắt đầu bằng việc tạo package.

### 32.2. Bắt đầu từ dependency

Liệt kê thành phần nào cần gọi thành phần nào. Nếu một core component phải import framework, hãy xem có thể đảo dependency qua interface hay không.

### 32.3. Kiểm tra thay đổi điển hình

Thử mô phỏng các thay đổi: thêm syntax, thêm type, thay interpreter, thêm host adapter hoặc thay database. Kiến trúc tốt giúp thay đổi tập trung ở layer liên quan.

### 32.4. Kiểm tra failure path

Vẽ đường đi của parse error, type error, runtime error và host failure. Nếu lỗi bị mất source location hoặc bị chuyển thành generic exception, contract cần được cải thiện.

## 33. Ghi nhớ

- Thiết kế phân tầng tách DSL thành các lớp có trách nhiệm và contract rõ.
- Các layer thường gặp gồm presentation, frontend, semantic analysis, IR, optimization, execution, runtime services, domain adapter và infrastructure.
- AST phản ánh syntax; semantic model bổ sung symbol/type; IR chuẩn hóa computation cho backend.
- Presentation phụ thuộc core API; core không nên phụ thuộc CLI, IDE hoặc framework.
- Domain adapter chuyển đổi giữa DSL model và host contract.
- Dependency inversion giúp core định nghĩa port còn infrastructure cung cấp implementation.
- Composition root nối dependency và quản lý lifecycle.
- Source location và structured error cần được giữ qua các layer.
- Layer boundary cần quy định data contract, error contract, ownership và versioning.
- Testing có thể chia thành lexer, parser, semantic, IR, optimizer, execution, adapter và integration test.
- Layered, hexagonal, clean architecture và compiler pipeline có thể kết hợp.
- Tách layer quá mức tạo indirection; gộp quá mức tạo coupling.
- Security boundary cần giới hạn host capability, secret và resource usage.
- Kiến trúc nên được kiểm tra bằng luồng dữ liệu, dependency graph và các thay đổi thực tế.

## 34. Câu hỏi tự kiểm tra

1. Thiết kế phân tầng là gì và giải quyết vấn đề nào khi xây dựng DSL?
2. Phân biệt layer, module, component, service và adapter.
3. Một DSL compiler/runtime thường có những layer chính nào?
4. Vì sao presentation layer không nên phụ thuộc trực tiếp infrastructure?
5. Lexer, parser và AST có trách nhiệm gì?
6. Semantic analysis khác parsing như thế nào?
7. AST và IR khác nhau ở mục đích và mức trừu tượng nào?
8. Vì sao optimizer nên làm việc trên IR thay vì sửa AST gốc?
9. Runtime services cung cấp những chức năng gì cho execution engine?
10. Domain adapter và anti-corruption layer giúp cô lập host API ra sao?
11. Dependency inversion và dependency direction được áp dụng như thế nào?
12. Composition root có vai trò gì trong dependency injection và lifecycle?
13. Một layer contract cần mô tả input, output, error và ownership ra sao?
14. Làm thế nào giữ source location xuyên qua lowering và execution?
15. Phân biệt layered architecture, hexagonal architecture và compiler pipeline.
16. Những anti-pattern nào thường xuất hiện khi thiết kế DSL phân tầng?
17. Làm thế nào test riêng từng layer và kiểm tra dependency rule?
18. Khi nào nên gộp layer và khi nào nên tách module?
19. Hãy mô tả data flow từ một file DSL đến một host API call.
20. Hãy đề xuất kiến trúc phân tầng cho một DSL workflow có CLI, IDE, runtime và nhiều domain adapter.
