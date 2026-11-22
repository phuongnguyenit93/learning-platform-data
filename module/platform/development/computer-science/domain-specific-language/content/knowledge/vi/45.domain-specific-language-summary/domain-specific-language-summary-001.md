# Bản đồ khái niệm

Một **ngôn ngữ đặc tả miền** (*Domain Specific Language – DSL*) là ngôn ngữ được thiết kế để mô tả một lĩnh vực hoặc nhóm tác vụ cụ thể. DSL cung cấp vocabulary, cấu trúc và semantics phù hợp với domain, giúp người dùng biểu đạt ý định ở mức trừu tượng cao hơn so với việc gọi trực tiếp API hoặc viết mã tổng quát.

**Bản đồ khái niệm** (*concept map*) trình bày các khái niệm chính và mối quan hệ giữa chúng. Với DSL, bản đồ giúp nhìn toàn bộ hệ sinh thái từ domain model, syntax và semantics đến parser, compiler, runtime, host integration, versioning và tooling.

~~~text
                         DOMAIN
                           |
                           v
                    Domain Model
                           |
                           v
                     DSL Language
                   /       |       \
                  v        v        v
              Syntax   Semantics  Type System
                  \        |        /
                   \       v       /
                    Language Frontend
                    Lexer -> Parser
                           |
                           v
                          AST
                           |
                           v
                   Semantic Analysis
                           |
                           v
                          IR
                           |
                  Optimization / Planning
                           |
                           v
                 Execution / Code Generation
                           |
                           v
                       Runtime
                           |
                           v
                  Domain Adapters / Host
                           |
                           v
                  External Systems

      Tooling <------> Language Core <------> Documentation
                           |
                           v
             Versioning / Migration / Governance
~~~

Bản đồ này thể hiện quan hệ khái niệm, không bắt buộc mọi DSL phải có đủ mọi thành phần hoặc triển khai theo đúng một pipeline. DSL cấu hình nhỏ có thể chỉ parse và validate; DSL thực thi có thể cần compiler, IR và runtime; DSL tích hợp có thể cần adapter, workflow engine và tooling.

## 1. DSL và domain

Domain là lĩnh vực mà DSL muốn mô tả. Domain có thể là định giá, xử lý đơn hàng, truy vấn dữ liệu, workflow, cấu hình hạ tầng, kiểm thử hoặc triển khai phần mềm.

### 1.1. Domain model

Domain model mô tả khái niệm, đối tượng, thuộc tính, quan hệ và quy tắc nghiệp vụ trong lĩnh vực đó.

Ví dụ domain thương mại:

~~~text
Customer
Order
OrderItem
Product
Price
Discount
Payment
Shipment
~~~

Một DSL order có thể dùng trực tiếp các khái niệm này:

~~~text
order "ORD-1001" {
    customer = customer("C-42")
    item("BOOK-1", quantity = 2)
    applyDiscount("MEMBER")
}
~~~

### 1.2. Ubiquitous language

Ubiquitous language là vocabulary thống nhất giữa chuyên gia domain, developer và người dùng DSL. Tên construct nên phản ánh ngôn ngữ nghiệp vụ thay vì chi tiết kỹ thuật nội bộ.

### 1.3. Domain boundary

Domain boundary xác định DSL chịu trách nhiệm mô tả phần nào. Một DSL pricing có thể quyết định giá nhưng không nhất thiết quản lý thanh toán hoặc vận chuyển.

### 1.4. Abstraction level

DSL nên biểu đạt ý định ở mức phù hợp. Nếu người dùng phải viết quá nhiều thao tác kỹ thuật, DSL chưa cung cấp abstraction đủ hữu ích. Nếu DSL che giấu mọi chi tiết và không cho kiểm soát các trường hợp quan trọng, abstraction có thể quá cao.

### 1.5. Domain-specific và general-purpose

General-purpose language có phạm vi sử dụng rộng. DSL tập trung vào một domain và thường có vocabulary, type và construct chuyên biệt. DSL có thể được embedded trong ngôn ngữ tổng quát hoặc được triển khai thành standalone language.

## 2. Mục tiêu và loại DSL

DSL có thể được phân loại theo mục tiêu và cách thực thi.

| Loại DSL | Mục đích | Ví dụ |
|---|---|---|
| Declarative | Mô tả trạng thái hoặc kết quả mong muốn | Infrastructure configuration |
| Imperative | Mô tả các bước thực hiện | Workflow script |
| Query | Truy vấn và biến đổi dữ liệu | Data query |
| Rule | Mô tả điều kiện và hành động | Eligibility rules |
| Configuration | Khai báo tham số và resource | Service configuration |
| Build | Mô tả task và dependency | Build pipeline |
| Template | Sinh text hoặc document | Report template |
| Testing | Mô tả scenario và assertion | Test specification |

### 2.1. Declarative

Người viết mô tả điều muốn đạt được; engine quyết định cách thực hiện.

~~~text
service "catalog" {
    replicas = 3
    public = true
}
~~~

### 2.2. Imperative

Người viết mô tả thứ tự thao tác:

~~~text
step createDatabase
step migrateSchema
step startService
~~~

### 2.3. Hybrid DSL

Một DSL có thể kết hợp khai báo và điều khiển luồng. Cần định nghĩa rõ phần nào mô tả state, phần nào tạo side effect.

### 2.4. Embedded và standalone

Embedded DSL dùng syntax hoặc host language để biểu đạt domain. Standalone DSL có lexer/parser và tooling riêng. Lựa chọn ảnh hưởng độ phức tạp compiler, trải nghiệm editor và khả năng tích hợp.

## 3. Language design: syntax, semantics và type

Một DSL không chỉ là tập keyword. Ngôn ngữ cần syntax, semantics và type system có quan hệ nhất quán.

~~~text
Language Design
├── Syntax
│   ├── Tokens
│   ├── Grammar
│   ├── Statements
│   └── Expressions
├── Semantics
│   ├── Evaluation order
│   ├── Scope
│   ├── State
│   └── Side effects
└── Type System
    ├── Primitive types
    ├── Domain types
    ├── Collections
    └── Conversion rules
~~~

### 3.1. Syntax

Syntax quy định source được viết thế nào: keyword, identifier, literal, expression, statement, block và grammar.

### 3.2. Semantics

Semantics quy định source có nghĩa gì và runtime phải làm gì. Cùng một cú pháp có thể có behavior khác nếu semantics khác.

### 3.3. Type system

Type system quy định loại giá trị, phép toán hợp lệ, conversion và cách kiểm tra lỗi kiểu.

### 3.4. Scope và binding

Scope xác định nơi symbol có thể được truy cập. Binding liên kết identifier với declaration, value hoặc function.

### 3.5. Evaluation order

Evaluation order quy định thứ tự đánh giá expression và side effect. Cần rõ ràng để compiler có thể tối ưu mà không đổi behavior.

### 3.6. Error semantics

Ngôn ngữ cần quy định parse error, type error, validation error và runtime error được biểu diễn và truyền đi thế nào.

## 4. Language frontend

Frontend chuyển source thành representation có cấu trúc.

~~~text
Source
  |
  v
Lexer
  |
  v
Tokens
  |
  v
Parser
  |
  v
AST
~~~

### 4.1. Lexer

Lexer nhận diện token và source position.

### 4.2. Parser

Parser áp dụng grammar để tạo AST.

### 4.3. AST

AST biểu diễn cấu trúc cú pháp dưới dạng node có kiểu. AST nên giữ source span để diagnostics và tooling trỏ đúng vị trí.

### 4.4. Error recovery

Parser có thể tiếp tục sau lỗi để báo nhiều diagnostic, đặc biệt trong editor.

### 4.5. Parser reuse

CLI, IDE và compiler nên dùng chung frontend để tránh khác biệt syntax.

## 5. Semantic analysis

Semantic analysis xác định chương trình có ý nghĩa hợp lệ trong context hay không.

~~~text
AST
 |
 v
Name resolution
 |
 v
Scope analysis
 |
 v
Type checking
 |
 v
Constraint validation
 |
 v
Semantic model
~~~

### 5.1. Name resolution

Tìm declaration tương ứng với identifier.

### 5.2. Type checking

Kiểm tra type của field, expression, function argument và return value.

### 5.3. Constraint validation

Kiểm tra range, uniqueness, cardinality và quan hệ giữa các field.

### 5.4. Symbol table

Lưu symbol, type, visibility và declaration location.

### 5.5. Semantic model

Semantic model chứa thông tin đã resolve, phục vụ lowering, execution, completion và navigation.

### 5.6. Static và runtime validation

Static validation kiểm tra điều có thể biết trước khi chạy. Runtime validation kiểm tra điều phụ thuộc input, environment hoặc external system.

## 6. Intermediate representation và optimization

IR là mô hình trung gian để chuẩn hóa chương trình trước execution hoặc code generation.

~~~text
AST
 |
 v
Lowering / Desugaring
 |
 v
Typed IR
 |
 v
Optimization
 |
 v
Execution Plan / Bytecode / Native Code
~~~

### 6.1. Desugaring

Chuyển syntax tiện dụng thành construct cơ bản có semantics tương đương.

### 6.2. Typed IR

Gắn type và binding đã resolve vào operation.

### 6.3. Optimization

Constant folding, dead code elimination, common subexpression elimination, inlining hoặc query planning.

### 6.4. Source mapping

Giữ liên kết giữa IR/instruction và source DSL để debugger, diagnostics và trace có thể chỉ ra vị trí gốc.

### 6.5. IR contract

IR là contract giữa frontend và backend. Nếu được lưu hoặc truyền giữa process, cần versioning.

## 7. Execution model và runtime

Runtime thực hiện chương trình đã được parse, kiểm tra và chuẩn bị.

Các chiến lược phổ biến:

- Tree-walking interpreter.
- Bytecode virtual machine.
- Native code generation.
- JIT compilation.
- Query execution engine.
- Workflow scheduler.

### 7.1. Execution context

Context chứa variables, tenant, deadline, correlation ID, capability và runtime state.

### 7.2. State và lifecycle

Runtime quản lý state, transaction, resource, cancellation và cleanup.

### 7.3. Concurrency

Scheduler có thể hỗ trợ async, parallel execution, queue và backpressure.

### 7.4. Resource budget

Execution budget giới hạn thời gian, memory, instruction count, recursion depth hoặc host call.

### 7.5. Observability

Runtime phát log, metrics, trace và structured error để điều tra behavior.

## 8. Host integration và domain adapter

DSL thường không hoạt động độc lập. Nó kết nối với host application hoặc external system thông qua adapter và API contract.

~~~text
DSL Program
    |
    v
Runtime
    |
    v
Domain Port
    |
    v
Adapter
    |
    v
Host Application / Database / API
~~~

### 8.1. Host application

Host application cung cấp môi trường chạy, service, lifecycle, configuration và security context cho DSL.

### 8.2. Domain port

Port định nghĩa operation mà domain cần, ví dụ reserveInventory hoặc calculatePrice.

### 8.3. Adapter

Adapter chuyển DSL value thành host type, gọi API và ánh xạ kết quả hoặc lỗi trở lại runtime.

### 8.4. Anti-corruption layer

Lớp chuyển đổi ngăn model và naming của external system làm rò rỉ vào DSL domain model.

### 8.5. Capability

Runtime chỉ cung cấp operation mà chương trình được phép sử dụng. Adapter là một điểm thực thi policy và authorization.

### 8.6. Failure handling

Timeout, network failure, domain rejection và permission error cần được phân loại rõ để runtime chọn retry, fallback hoặc fail.

## 9. Kiến trúc và thiết kế

Một DSL có thể dùng nhiều pattern kiến trúc:

~~~text
Presentation
    |
Application services
    |
Core language / domain
    ^
Ports and interfaces
    ^
Infrastructure adapters
~~~

### 9.1. Layered architecture

Tách presentation, application, domain và infrastructure theo trách nhiệm.

### 9.2. Hexagonal architecture

Core giao tiếp với bên ngoài qua ports; adapter triển khai các port đó.

### 9.3. Compiler pipeline

Chia quá trình xử lý thành lexer, parser, semantic analysis, IR, optimization và backend.

### 9.4. Dependency inversion

Core định nghĩa abstraction cần thiết. Infrastructure cung cấp implementation mà không buộc core phụ thuộc framework.

### 9.5. Composition root

Composition root nối parser, analyzer, runtime, adapter và infrastructure implementation; đồng thời quản lý lifecycle.

### 9.6. Design trade-off

Tách nhiều layer giúp độc lập và testability nhưng tăng indirection. Gộp layer giảm ceremony nhưng có thể tăng coupling. Số layer cần phù hợp quy mô và tốc độ thay đổi.

## 10. Versioning và migration

DSL và hệ thống sử dụng nó thay đổi theo thời gian. Versioning giúp xác định contract nào đang được dùng và cách chuyển đổi an toàn.

### 10.1. Language version

Xác định grammar và semantics áp dụng cho source.

### 10.2. Compiler và runtime version

Compiler/runtime version xác định implementation, optimization và host API behavior.

### 10.3. Module và dependency version

Import package hoặc extension cần version constraint và dependency resolution rõ ràng.

### 10.4. Configuration schema version

Configuration schema có thể thay đổi field, type hoặc default. Cần migration path cho cấu hình cũ.

### 10.5. Deprecation

Construct cũ cần thông báo since, replacement và version removal dự kiến nếu đã xác định.

### 10.6. Compatibility

Compatibility matrix mô tả compiler, runtime, plugin và module version nào có thể kết hợp.

### 10.7. Expand-and-contract

Migration dữ liệu thường thêm schema mới trước, chuyển consumer và dữ liệu, sau đó mới loại bỏ schema cũ.

## 11. Feature flag và rollout

Feature flag điều khiển hành vi tại runtime và giúp tách deploy khỏi release.

### 11.1. Boolean và multi-variant

Flag có thể trả enabled/disabled hoặc một trong nhiều variant.

### 11.2. Targeting

Flag có thể áp dụng theo environment, tenant, user, region hoặc attribute đáng tin cậy.

### 11.3. Percentage rollout

Stable identity và deterministic bucketing giúp một đối tượng giữ cùng assignment.

### 11.4. Kill switch

Kill switch cho phép tắt nhanh tính năng hoặc dependency gặp sự cố. Cần default an toàn và đường propagation đáng tin cậy.

### 11.5. Migration flag

Flag có thể chuyển read/write path giữa implementation cũ và mới, hỗ trợ shadow read, dual write và cutover.

### 11.6. Lifecycle

Flag cần owner, category, review date, audit history và cleanup sau rollout để tránh flag debt.

## 12. Tooling và developer experience

Tooling giúp người dùng tạo, kiểm tra, hiểu và duy trì chương trình DSL.

~~~text
Developer Tooling
├── CLI
├── Syntax highlighting
├── Language server
│   ├── Completion
│   ├── Hover
│   ├── Diagnostics
│   └── Navigation
├── Formatter / Linter
├── Refactoring
├── Debugger
└── Documentation tools
~~~

### 12.1. CLI

CLI cung cấp parse, check, compile, run, format và inspect với exit code ổn định.

### 12.2. Language server

Language server hỗ trợ completion, hover, rename, navigation và diagnostics.

### 12.3. Formatter và linter

Formatter chuẩn hóa presentation. Linter phát hiện vấn đề style, correctness, performance hoặc security.

### 12.4. Debugger

Debugger dùng source map và execution metadata để hiển thị breakpoint, variable, call stack và trace.

### 12.5. Shared language core

CLI, IDE và compiler nên dùng chung parser và semantic model để giữ consistency.

### 12.6. Incremental analysis

Document version, cache, dependency invalidation và cancellation giúp tooling phản hồi nhanh trong workspace lớn.

### 12.7. Quality dimensions

Tooling được đánh giá qua correctness, responsiveness, reliability, discoverability, compatibility, accessibility và maintainability.

## 13. Documentation và knowledge model

Tài liệu giúp người dùng hiểu và tra cứu DSL.

### 13.1. Tutorial

Hướng dẫn người mới hoàn thành một tác vụ theo từng bước.

### 13.2. How-to

Hướng dẫn giải quyết một vấn đề cụ thể.

### 13.3. Explanation

Giải thích khái niệm, lý do và trade-off thiết kế.

### 13.4. Reference

Mô tả chính xác syntax, field, type, function, default, constraints và runtime behavior.

### 13.5. Examples

Ví dụ cần chạy được, gắn đúng DSL version và minh họa một khái niệm rõ ràng.

### 13.6. Documentation as code

Tài liệu được version control, review và phát hành cùng compiler/runtime release.

### 13.7. Generated documentation

Grammar và symbol metadata có thể sinh syntax table hoặc API signature; semantics và ví dụ vẫn cần nội dung biên tập.

## 14. Chất lượng, hiệu năng và vận hành

Một DSL tốt cần được đánh giá trong toàn bộ vòng đời, không chỉ lúc parse thành công.

### 14.1. Correctness

Syntax, semantics, type checking và runtime behavior phải nhất quán.

### 14.2. Performance

Đo parse time, compile time, execution latency, throughput, memory, allocation và tail latency.

### 14.3. Reliability

Xử lý lỗi, timeout, cancellation, retry, recovery và dependency failure.

### 14.4. Observability

Structured logs, metrics, traces, source mapping và correlation ID giúp điều tra behavior.

### 14.5. Security

Input validation, capability boundary, authorization, secret handling, plugin trust và resource quota bảo vệ host.

### 14.6. Maintainability

Layer boundary, API contract, testability, documentation và versioning giúp hệ thống phát triển bền vững.

### 14.7. Governance

Owner, change approval, deprecation, audit và compatibility policy giúp quản lý DSL khi có nhiều team sử dụng.

## 15. Testing và quality gates

Testing kiểm tra từng tầng và toàn bộ đường đi từ source đến kết quả.

~~~text
Lexer tests
    |
Parser tests
    |
Semantic tests
    |
IR / optimizer tests
    |
Execution tests
    |
Adapter contract tests
    |
Integration / end-to-end tests
~~~

### 15.1. Lexer và parser tests

Kiểm tra token, grammar, source span, syntax hợp lệ và error recovery.

### 15.2. Semantic tests

Kiểm tra name resolution, scope, type, constraint và diagnostics.

### 15.3. IR và optimizer tests

Kiểm tra lowering, source mapping và việc tối ưu không làm thay đổi semantics.

### 15.4. Runtime tests

Kiểm tra result, state transition, error propagation, cancellation và resource cleanup.

### 15.5. Adapter contract tests

Kiểm tra mapping type, authorization, timeout, retry và external failure.

### 15.6. Tooling tests

Kiểm tra completion, formatter, diagnostics, protocol lifecycle và large workspace.

### 15.7. Compatibility tests

Kiểm tra source/config cũ với compiler/runtime mới và migration path.

### 15.8. Quality gates

CI có thể chạy format check, static analysis, compile, tests, dependency checks và policy validation trước khi release.

## 16. Một ví dụ xuyên suốt

Giả sử xây dựng DSL cho quy trình phê duyệt đơn hàng.

### 16.1. Domain

Domain có Order, Customer, Item, Amount, RiskLevel và Approval.

### 16.2. Source DSL

~~~text
workflow ApproveOrder {
    input order: Order

    validate order

    if order.total >= 1000 {
        requireApproval("manager")
    }

    if order.customer.risk == HIGH {
        reject("HIGH_RISK")
    } else {
        reserveInventory(order)
        approve(order)
    }
}
~~~

### 16.3. Frontend

Lexer tạo token; parser tạo AST gồm workflow, input, validate, if và function call.

### 16.4. Semantic analysis

Analyzer kiểm tra Order type, field total, function signature và quyền gọi reserveInventory.

### 16.5. IR

Workflow được chuyển thành operation sequence, branch và host call đã resolve.

### 16.6. Runtime

Runtime tạo execution context, đánh giá điều kiện và điều phối các operation.

### 16.7. Domain adapter

Adapter gọi inventory service và approval service, ánh xạ response thành DSL value hoặc structured error.

### 16.8. Tooling

IDE cung cấp completion cho Order field, hover cho function, diagnostics cho type mismatch và navigation đến declaration.

### 16.9. Versioning

Khi Order schema thay đổi, compiler có thể hỗ trợ version mới trong khi adapter hoặc migration layer chuyển đổi dữ liệu cũ.

### 16.10. Observability

Trace liên kết source location, workflow execution ID, host call và error code để điều tra một lần phê duyệt.

## 17. Bản đồ quan hệ giữa các khái niệm

Bảng sau tóm tắt quan hệ giữa các nhóm khái niệm.

| Khái niệm A | Quan hệ | Khái niệm B |
|---|---|---|
| Domain model | Cung cấp vocabulary cho | DSL |
| Syntax | Quy định hình thức của | Source |
| Semantics | Quy định ý nghĩa của | Construct |
| Type system | Ràng buộc giá trị và operation của | Expression |
| Parser | Chuyển source thành | AST |
| Semantic analyzer | Bổ sung type và symbol vào | AST |
| Lowering | Chuyển semantic model thành | IR |
| Optimizer | Biến đổi có bảo toàn semantics | IR |
| Backend | Thực thi hoặc sinh code từ | IR |
| Runtime | Quản lý execution và resource của | Program |
| Adapter | Nối domain contract với | Host API |
| Tooling | Hỗ trợ viết và hiểu | DSL source |
| Documentation | Giải thích contract của | Language/API |
| Versioning | Quản lý thay đổi của | Syntax/IR/API/config |
| Migration | Chuyển từ contract hoặc data model | Cũ sang mới |
| Governance | Kiểm soát thay đổi và trách nhiệm của | DSL ecosystem |

## 18. Bản đồ quyết định khi thiết kế DSL

Khi bắt đầu hoặc mở rộng DSL, có thể dùng các câu hỏi sau để xác định kiến trúc:

~~~text
Domain đã rõ chưa?
      |
      v
Chỉ khai báo hay cần thực thi?
      |
      v
Embedded hay standalone?
      |
      v
Grammar và type model là gì?
      |
      v
Cần semantic analysis ở mức nào?
      |
      v
AST có đủ hay cần IR?
      |
      v
Interpreter, VM hay code generation?
      |
      v
Host integration qua adapter nào?
      |
      v
Tooling cần hỗ trợ workflow nào?
      |
      v
Versioning, migration và governance ra sao?
~~~

### 18.1. Chọn mức compiler

DSL cấu hình nhỏ có thể chỉ cần parser và validator. DSL có expression hoặc control flow cần semantic analysis. DSL có tối ưu hoặc nhiều backend thường cần IR.

### 18.2. Chọn runtime

Nếu chương trình chỉ mô tả state, có thể tạo configuration model. Nếu chương trình có behavior, cần interpreter, VM hoặc execution engine.

### 18.3. Chọn integration boundary

Nếu DSL gọi nhiều hệ thống, xác định domain port và adapter trước khi đưa host object trực tiếp vào language core.

### 18.4. Chọn tooling scope

Bắt đầu từ diagnostics, formatter và CLI; mở rộng language server, debugger và refactoring theo nhu cầu người dùng.

### 18.5. Chọn versioning policy

Xác định language version, runtime compatibility, deprecation period và migration process trước khi DSL có nhiều consumer.

## 19. Những đánh đổi tổng quát

Thiết kế DSL luôn có trade-off. Bản đồ khái niệm giúp thấy quyết định ở một tầng có thể ảnh hưởng các tầng khác.

| Quyết định | Lợi ích | Chi phí hoặc rủi ro |
|---|---|---|
| Syntax đơn giản | Dễ học và đọc | Có thể hạn chế biểu đạt |
| Type system mạnh | Phát hiện lỗi sớm | Tăng độ phức tạp compiler |
| Standalone DSL | Kiểm soát syntax/tooling | Phải xây dựng parser và ecosystem |
| Embedded DSL | Tái sử dụng host language | Bị giới hạn bởi host syntax |
| IR | Tối ưu và nhiều backend | Thêm representation và maintenance |
| JIT/native backend | Có thể tăng throughput | Compile cost và debugging phức tạp |
| Plugin system | Mở rộng domain | Trust boundary và compatibility |
| Remote configuration | Quản trị tập trung | Network dependency và latency |
| Rich tooling | Tăng năng suất | Chi phí phát triển và support |
| Strict compatibility | Hành vi ổn định | Chậm đổi semantics |

### 19.1. Simplicity và expressiveness

Ngôn ngữ càng nhiều construct càng có thể biểu đạt nhiều trường hợp, nhưng càng khó học, parse, document và maintain.

### 19.2. Flexibility và safety

Dynamic extension tăng linh hoạt nhưng có thể giảm khả năng kiểm tra tĩnh và mở rộng attack surface.

### 19.3. Performance và observability

Optimization có thể giảm overhead nhưng làm trace khó hiểu hơn. Cần giữ source mapping và diagnostic metadata.

### 19.4. Compatibility và evolution

Giữ syntax cũ giúp consumer nâng cấp dễ hơn nhưng tạo technical debt. Deprecation và migration cần có kế hoạch.

## 20. Glossary các khái niệm chính

| Thuật ngữ | Ý nghĩa ngắn |
|---|---|
| DSL | Ngôn ngữ đặc tả miền |
| Domain model | Mô hình khái niệm nghiệp vụ |
| Syntax | Quy tắc hình thức của source |
| Semantics | Ý nghĩa và hành vi của construct |
| Grammar | Quy tắc tạo cấu trúc cú pháp |
| Lexer | Thành phần nhận diện token |
| Parser | Thành phần tạo cấu trúc cú pháp |
| AST | Cây cú pháp trừu tượng |
| Symbol | Định danh cho declaration hoặc member |
| Scope | Phạm vi truy cập symbol |
| Type system | Quy tắc type và operation |
| Semantic analysis | Kiểm tra ý nghĩa và ràng buộc |
| IR | Biểu diễn trung gian |
| Lowering | Chuyển representation xuống mức thấp hơn |
| Optimization | Biến đổi có bảo toàn semantics |
| Backend | Thành phần thực thi hoặc sinh code |
| Runtime | Môi trường thực thi chương trình |
| Adapter | Cầu nối giữa contract và hệ thống ngoài |
| Port | Interface mà core yêu cầu |
| Tooling | Bộ công cụ hỗ trợ phát triển |
| Language server | Dịch vụ ngôn ngữ cho editor |
| Diagnostics | Thông tin lỗi, warning và vị trí source |
| Feature flag | Cờ điều khiển hành vi runtime |
| Artifact | Sản phẩm được tạo từ build hoặc packaging |
| Provenance | Nguồn gốc và lịch sử tạo artifact |
| Migration | Quá trình chuyển đổi schema, code hoặc data |
| Compatibility | Khả năng tương thích giữa version |
| Governance | Quản trị thay đổi và trách nhiệm |

## 21. Checklist tư duy khi đọc một DSL

Khi gặp một DSL mới, có thể lần lượt xác định:

1. Domain nào đang được mô hình hóa?
2. Người dùng DSL là ai và họ muốn hoàn thành tác vụ nào?
3. Source được tổ chức thành file, module hay project ra sao?
4. Syntax và grammar có những construct chính nào?
5. Semantics, type và scope được định nghĩa thế nào?
6. Compiler hoặc interpreter xử lý source qua các bước nào?
7. Runtime quản lý state, error và resource ra sao?
8. DSL gọi host application hoặc external system bằng cách nào?
9. Tooling hỗ trợ viết, kiểm tra và debug đến đâu?
10. Documentation và reference được version hóa thế nào?
11. Thay đổi language/API/data được migration ra sao?
12. Ai chịu trách nhiệm governance, release và compatibility?

## 22. Ghi nhớ

- DSL được xây dựng quanh domain model và vocabulary của một lĩnh vực cụ thể.
- Một ngôn ngữ cần syntax, semantics và type system nhất quán.
- Frontend chuyển source thành AST; semantic analysis bổ sung symbol, type và validation.
- IR chuẩn hóa computation để optimizer và backend sử dụng.
- Runtime quản lý execution context, state, concurrency, resource và error.
- Adapter kết nối DSL domain với host application và external system.
- Layered, hexagonal và compiler pipeline là các góc nhìn kiến trúc có thể kết hợp.
- Versioning, deprecation và migration quản lý thay đổi của language, runtime, module và data.
- Feature flag hỗ trợ rollout, experiment, kill switch và migration có kiểm soát.
- Tooling và documentation là một phần của ecosystem, không phải phần phụ sau compiler.
- Testing, performance, security, observability và governance quyết định DSL có thể vận hành lâu dài hay không.
- Các trade-off giữa simplicity, expressiveness, safety, performance và compatibility cần được quyết định có chủ đích.

## 23. Câu hỏi tự kiểm tra

1. DSL là gì và domain model đóng vai trò gì trong việc thiết kế vocabulary?
2. Phân biệt syntax, semantics và type system.
3. Mô tả pipeline từ source text qua lexer, parser và AST.
4. Semantic analysis bổ sung những thông tin nào cho AST?
5. Vì sao cần IR và optimization layer?
6. Interpreter, bytecode VM, JIT và native backend khác nhau như thế nào?
7. Runtime context, state và resource lifecycle có vai trò gì?
8. Domain port và adapter kết nối DSL với host application ra sao?
9. Layered architecture và hexagonal architecture có thể kết hợp như thế nào?
10. Language version, runtime version và module version khác nhau ở điểm nào?
11. Feature flag hỗ trợ rollout và migration ra sao?
12. Vì sao CLI, IDE và compiler nên dùng chung language core?
13. Documentation reference khác tutorial và explanation như thế nào?
14. Những chiều chất lượng tooling quan trọng là gì?
15. Testing theo layer giúp khoanh vùng lỗi như thế nào?
16. Những rủi ro security nào cần được kiểm soát trong DSL runtime và plugin system?
17. Hãy mô tả quan hệ giữa AST, semantic model, IR và execution backend.
18. Hãy vẽ bản đồ khái niệm cho một DSL workflow có domain model, compiler, runtime, adapter và tooling.
19. Nêu các trade-off khi chọn embedded DSL hay standalone DSL.
20. Hãy giải thích cách một thay đổi language version có thể ảnh hưởng documentation, tooling, runtime và migration.
